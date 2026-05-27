from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from dacite import from_dict

from constants import (
    GROUP_JID_SUFFIX,
    NEWSLETTER_SERVER,
    STATUS_BROADCAST_JID,
    WHATSAPP_JID_SUFFIX,
)
from greenline.contracts.daemon import daemon_client
from greenline.contracts.kv import GreenlineKV
from greenline.store.identity import canonicalize_contact_jid, remember_chat
from greenline.store.media import (
    _contact_preview,
    _extract_thumbnail,
    persist_contact_vcard,
    resolve_media_message_content,
    template_message_button,
    template_message_caption,
    template_message_text,
)
from greenline.store.mentions import quoted_message_template, template_mention_text
from greenline.store.records import (
    LidMapRecord,
    MessageIndexRecord,
    stored_message_record,
)
from greenline.store.repository import message_index_key, message_storage_key
from models import ChatListItem, Message, MessageType, ReadReceipt
from ut_components.utils import enum_to_str as _enum_to_str
from whatsmeow_types import (
    HistorySyncConversation,
    HistorySyncEvent,
    HistorySyncInnerMessage,
    HistorySyncPushname,
    PhoneNumberToLidMapping,
)

_STATUS_TO_RECEIPT = {
    0: ReadReceipt.NONE,
    1: ReadReceipt.SENT,
    2: ReadReceipt.DELIVERED,
    3: ReadReceipt.READ,
    4: ReadReceipt.READ,
    5: ReadReceipt.READ,
}


def handle_history_sync(event: Any) -> Dict[str, Dict[str, Any]]:
    """Parse a HistorySync event and populate KV with chats and messages.

    Returns a dict mapping chat JID to serialized ChatListItem for UI updates.
    """
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=HistorySyncEvent, data=raw)

    conversations = evt.Data.conversations or []
    pushnames = evt.Data.pushnames or []
    lid_mappings = evt.Data.phoneNumberToLidMappings or []

    if not conversations and not pushnames:
        return {}

    jid_map = _build_jid_map(evt)
    chat_updates: Dict[str, Dict[str, Any]] = {}

    with GreenlineKV() as kv:
        for conv in conversations:
            chat_jid = canonicalize_contact_jid(conv.ID, jid_map=jid_map) if conv.ID else ""
            if not chat_jid:
                continue
            if chat_jid == STATUS_BROADCAST_JID:
                continue
            if chat_jid.endswith(NEWSLETTER_SERVER):
                continue

            _process_messages(kv, conv, chat_jid, jid_map)
            chat_dict = _process_conversation(kv, conv, chat_jid, jid_map)
            if chat_dict is not None:
                chat_updates[chat_jid] = chat_dict

        _process_pushnames(kv, pushnames, jid_map, chat_updates)
        _process_lid_mappings(kv, lid_mappings)

        kv.commit_cached()

    return chat_updates


def _build_jid_map(evt: HistorySyncEvent) -> Dict[str, str]:
    lid_to_pn: Dict[str, str] = {}
    for mapping in evt.Data.phoneNumberToLidMappings or []:
        if mapping.lidJID and mapping.pnJID:
            canonical_lid = canonicalize_contact_jid(mapping.lidJID, jid_map={mapping.lidJID: mapping.lidJID})
            lid_to_pn[canonical_lid] = canonicalize_contact_jid(mapping.pnJID)

    jids: Set[str] = set()
    for conv in evt.Data.conversations or []:
        jids.add(conv.ID)
        for msg_wrap in conv.messages or []:
            if msg_wrap.message.participant:
                jids.add(msg_wrap.message.participant)
    for pn in evt.Data.pushnames or []:
        if pn.ID:
            jids.add(pn.ID)

    jid_map: Dict[str, str] = dict(lid_to_pn)
    rpc = daemon_client()
    for jid in jids:
        jid_map[jid] = canonicalize_contact_jid(jid, jid_map=lid_to_pn, rpc=rpc)

    return jid_map


def _derive_type_from_content(content: Dict[str, Any]) -> Optional[MessageType]:
    ext = content.get("extendedTextMessage")
    if ext and (ext.get("matchedText") or ext.get("title")):
        return MessageType.LINK_PREVIEW
    if resolve_media_message_content(content, "imageMessage"):
        return MessageType.IMAGE
    if content.get("conversation") or ext or template_message_text(content):
        return MessageType.TEXT
    if content.get("videoMessage"):
        return MessageType.VIDEO
    if content.get("audioMessage"):
        return MessageType.AUDIO
    if content.get("documentMessage"):
        return MessageType.DOCUMENT
    if content.get("contactMessage"):
        return MessageType.CONTACT
    if content.get("stickerMessage"):
        return MessageType.STICKER
    return None


def _extract_content_fields(
    content: Dict[str, Any], chat_id: str, message_id: str, jid_map: Dict[str, str]
) -> Tuple[str, List[str], str, str, str, str, str]:
    """Returns (text, mentioned_jids, caption, mimetype, file_name, duration, media_path)."""
    text = ""
    mentioned_jids: List[str] = []
    caption = ""
    mimetype = ""
    file_name = ""
    duration = ""
    media_path = ""

    img = resolve_media_message_content(content, "imageMessage")

    if content.get("conversation"):
        text = content["conversation"]
    elif content.get("extendedTextMessage"):
        ext = content["extendedTextMessage"]
        text, mentioned_jids = template_mention_text(
            ext.get("text", ""),
            (ext.get("contextInfo") or {}).get("mentionedJID"),
            jid_map=jid_map,
        )
    elif not img:
        text = template_message_text(content)
    vid = content.get("videoMessage")
    aud = content.get("audioMessage")
    doc = content.get("documentMessage")
    contact = content.get("contactMessage")
    stk = content.get("stickerMessage")

    if img:
        raw_img = content.get("imageMessage")
        if raw_img:
            caption, mentioned_jids = template_mention_text(
                raw_img.get("caption", ""),
                (raw_img.get("contextInfo") or {}).get("mentionedJID"),
                jid_map=jid_map,
            )
        else:
            caption = template_message_caption(content)
        mimetype = img.get("mimetype", "")
    elif vid:
        caption, mentioned_jids = template_mention_text(
            vid.get("caption", ""),
            (vid.get("contextInfo") or {}).get("mentionedJID"),
            jid_map=jid_map,
        )
        mimetype = vid.get("mimetype", "")
        secs = vid.get("seconds", 0) or 0
        if secs:
            duration = f"{secs // 60}:{secs % 60:02d}"
    elif aud:
        mimetype = aud.get("mimetype", "")
        secs = aud.get("seconds", 0) or 0
        if secs:
            duration = f"{secs // 60}:{secs % 60:02d}"
    elif doc:
        caption, mentioned_jids = template_mention_text(
            doc.get("caption", ""),
            (doc.get("contextInfo") or {}).get("mentionedJID"),
            jid_map=jid_map,
        )
        mimetype = doc.get("mimetype", "")
        file_name = doc.get("fileName", "")
    elif contact:
        file_name = contact.get("displayName", "")
        mimetype = "text/x-vcard"
        media_path = persist_contact_vcard(chat_id, message_id, file_name, contact.get("vcard", ""))
    elif stk:
        mimetype = stk.get("mimetype", "")

    return text, mentioned_jids, caption, mimetype, file_name, duration, media_path


def _extract_link_preview_fields(content: Dict[str, Any]) -> Tuple[str, str, str]:
    ext = content.get("extendedTextMessage")
    if not ext:
        return "", "", ""
    return ext.get("title", ""), ext.get("description", ""), ext.get("matchedText", "")


def _message_preview(content: Dict[str, Any], jid_map: Dict[str, str]) -> Tuple[str, List[str]]:
    if content.get("conversation"):
        return str(content["conversation"]), []
    ext = content.get("extendedTextMessage")
    if ext and ext.get("text"):
        return template_mention_text(
            str(ext["text"]),
            (ext.get("contextInfo") or {}).get("mentionedJID"),
            jid_map=jid_map,
        )
    img = resolve_media_message_content(content, "imageMessage")
    if img:
        raw_img = content.get("imageMessage")
        if raw_img:
            return template_mention_text(
                raw_img.get("caption") or "📷 Photo",
                (raw_img.get("contextInfo") or {}).get("mentionedJID"),
                jid_map=jid_map,
            )
        return template_message_caption(content) or "📷 Photo", []
    vid = content.get("videoMessage")
    if vid:
        return template_mention_text(
            vid.get("caption") or "🎥 Video",
            (vid.get("contextInfo") or {}).get("mentionedJID"),
            jid_map=jid_map,
        )
    if content.get("audioMessage"):
        return "🎵 Audio", []
    doc = content.get("documentMessage")
    if doc:
        return template_mention_text(
            doc.get("caption") or "📄 Document",
            (doc.get("contextInfo") or {}).get("mentionedJID"),
            jid_map=jid_map,
        )
    contact = content.get("contactMessage")
    if contact:
        return _contact_preview(contact.get("displayName", "")), []
    if content.get("stickerMessage"):
        return "🏷️ Sticker", []
    template_text = template_message_text(content)
    if template_text:
        return template_text, []
    return "", []


def _find_latest_message(
    conv: HistorySyncConversation,
) -> Optional[HistorySyncInnerMessage]:
    latest: Optional[HistorySyncInnerMessage] = None
    latest_ts = 0
    for msg_wrap in conv.messages or []:
        inner = msg_wrap.message
        if not inner.message or inner.messageStubType:
            continue
        if _derive_type_from_content(inner.message) is None:
            continue
        if inner.messageTimestamp > latest_ts:
            latest_ts = inner.messageTimestamp
            latest = inner
    return latest


def _extract_context_info_from_dict(
    content: Dict[str, Any], jid_map: Dict[str, str]
) -> Tuple[str, str, str, bool, str, List[str]]:
    for field_name in (
        "extendedTextMessage",
        "imageMessage",
        "videoMessage",
        "audioMessage",
        "documentMessage",
        "contactMessage",
        "stickerMessage",
    ):
        sub = content.get(field_name)
        if sub and isinstance(sub, dict):
            ctx = sub.get("contextInfo")
            if ctx and ctx.get("stanzaID"):
                reply_to_id = ctx["stanzaID"]
                reply_to_sender_raw = str(ctx.get("participant") or "")
                participant = (
                    canonicalize_contact_jid(reply_to_sender_raw, jid_map=jid_map) if reply_to_sender_raw else ""
                )
                reply_to_text, reply_to_mentioned_jids = quoted_message_template(
                    ctx.get("quotedMessage"),
                    jid_map=jid_map,
                )
                return reply_to_id, participant, reply_to_sender_raw, False, reply_to_text, reply_to_mentioned_jids
    return "", "", "", False, "", []


def _process_messages(
    kv: GreenlineKV,
    conv: HistorySyncConversation,
    chat_jid: str,
    jid_map: Dict[str, str],
) -> None:
    messages = conv.messages or []
    if not messages:
        return

    existing_entries = kv.get_partial_records(f"message:{chat_jid}:")
    existing_ids: Set[str] = {v.id for _, v in existing_entries}

    for msg_wrap in messages:
        inner = msg_wrap.message
        msg_id = inner.key.ID
        if not msg_id or msg_id in existing_ids:
            continue

        content = inner.message
        if not content or inner.messageStubType:
            continue

        msg_type = _derive_type_from_content(content)
        if msg_type is None:
            continue

        ts_unix = inner.messageTimestamp
        if not ts_unix:
            continue

        ts_display = datetime.fromtimestamp(ts_unix).strftime("%H:%M")
        text, mentioned_jids, caption, mimetype, file_name, duration, media_path = _extract_content_fields(
            content,
            chat_jid,
            msg_id,
            jid_map,
        )

        is_outgoing = inner.key.fromMe
        read_receipt = ReadReceipt.NONE
        if is_outgoing:
            read_receipt = _STATUS_TO_RECEIPT.get(inner.status, ReadReceipt.SENT)

        sender_raw = str(inner.participant or "") if not is_outgoing else ""
        sender = canonicalize_contact_jid(sender_raw, jid_map=jid_map) if sender_raw else ""

        (
            reply_to_id,
            reply_to_sender_id,
            reply_to_sender_raw,
            reply_to_from_me,
            reply_to_text,
            reply_to_mentioned_jids,
        ) = _extract_context_info_from_dict(content, jid_map)

        link_title, link_description, link_url = (
            _extract_link_preview_fields(content) if msg_type == MessageType.LINK_PREVIEW else ("", "", "")
        )

        button_text, button_url = (
            template_message_button(content) if msg_type in (MessageType.IMAGE, MessageType.TEXT) else ("", "")
        )

        msg = Message(
            id=msg_id,
            chat_id=chat_jid,
            type=msg_type,
            is_outgoing=is_outgoing,
            timestamp=ts_display,
            timestamp_unix=ts_unix,
            read_receipt=read_receipt,
            sender=sender,
            sender_raw=sender_raw,
            text=text,
            mentioned_jids=mentioned_jids,
            caption=caption,
            media_path=media_path,
            mimetype=mimetype,
            file_name=file_name,
            duration=duration,
            reply_to_id=reply_to_id,
            reply_to_sender_id=reply_to_sender_id,
            reply_to_sender_raw=reply_to_sender_raw,
            reply_to_from_me=reply_to_from_me,
            reply_to_text=reply_to_text,
            reply_to_mentioned_jids=reply_to_mentioned_jids,
            button_text=button_text,
            button_url=button_url,
            link_title=link_title,
            link_description=link_description,
            link_url=link_url,
        )

        msg.thumbnail_path = _extract_thumbnail({"Message": content}, msg_id)

        key = message_storage_key(chat_jid, ts_unix, msg_id)
        kv.put_cached_record(key, stored_message_record(msg, {"Message": content}))
        kv.put_cached_record(message_index_key(chat_jid, msg_id), MessageIndexRecord(key))


def _process_conversation(
    kv: GreenlineKV,
    conv: HistorySyncConversation,
    chat_jid: str,
    jid_map: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    is_group = chat_jid.endswith(GROUP_JID_SUFFIX)
    latest_msg = _find_latest_message(conv)

    chat_key = f"chat:{chat_jid}"
    existing = kv.get_record(chat_key)

    if existing is not None:
        chat = existing
        changed = False

        if latest_msg is not None and latest_msg.messageTimestamp > chat.last_message_timestamp:
            preview, latest_preview_mentioned_jids = _message_preview(latest_msg.message or {}, jid_map)
            msg_type = _derive_type_from_content(latest_msg.message or {}) if latest_msg.message else None
            if preview:
                chat.last_message = preview
                chat.last_message_mentioned_jids = latest_preview_mentioned_jids
                chat.last_message_type = str(msg_type or "")
                chat.date = datetime.fromtimestamp(latest_msg.messageTimestamp).strftime("%H:%M")
                chat.last_message_timestamp = latest_msg.messageTimestamp
                if latest_msg.key.fromMe:
                    chat.read_receipt = _STATUS_TO_RECEIPT.get(latest_msg.status, ReadReceipt.SENT)
                changed = True

        if is_group and conv.name and conv.name != chat.name:
            chat.name = conv.name
            changed = True

        if not changed:
            return None

        kv.put_cached_record(chat_key, chat)
        remember_chat(chat)
        return _enum_to_str(asdict(chat))  # type: ignore[no-any-return, no-untyped-call]

    last_ts = conv.conversationTimestamp or 0
    if latest_msg is None and not last_ts:
        return None

    preview = ""
    date = ""
    read_receipt = ReadReceipt.NONE

    last_message_type = ""
    preview_mentioned_jids: List[str] = []
    if latest_msg is not None:
        preview, preview_mentioned_jids = _message_preview(latest_msg.message or {}, jid_map)
        last_message_type = str(_derive_type_from_content(latest_msg.message or {}) or "")
        last_ts = latest_msg.messageTimestamp
        date = datetime.fromtimestamp(last_ts).strftime("%H:%M")
        if latest_msg.key.fromMe:
            read_receipt = _STATUS_TO_RECEIPT.get(latest_msg.status, ReadReceipt.SENT)
    elif last_ts:
        date = datetime.fromtimestamp(last_ts).strftime("%H:%M")

    name = conv.name if conv.name else chat_jid
    if not is_group and not conv.name:
        name = chat_jid.replace(WHATSAPP_JID_SUFFIX, "")

    chat = ChatListItem(
        id=chat_jid,
        name=name,
        photo="",
        last_message=preview,
        date=date,
        last_message_timestamp=last_ts,
        read_receipt=read_receipt,
        unread_count=conv.unreadCount,
        is_group=is_group,
        last_message_mentioned_jids=preview_mentioned_jids,
        last_message_type=last_message_type,
    )

    kv.put_cached_record(chat_key, chat)
    remember_chat(chat)
    return _enum_to_str(asdict(chat))  # type: ignore[no-any-return, no-untyped-call]


def _process_pushnames(
    kv: GreenlineKV,
    pushnames: List[HistorySyncPushname],
    jid_map: Dict[str, str],
    chat_updates: Dict[str, Dict[str, Any]],
) -> None:
    for pn in pushnames:
        if not pn.pushname or not pn.ID:
            continue
        jid = canonicalize_contact_jid(pn.ID, jid_map=jid_map)
        chat_key = f"chat:{jid}"
        existing = kv.get_record(chat_key)
        if existing is None:
            chat = ChatListItem(
                id=jid,
                name=pn.pushname,
                photo="",
                last_message="",
                date="",
                last_message_timestamp=0,
                read_receipt=ReadReceipt.NONE,
                unread_count=0,
                is_group=False,
                push_name=pn.pushname,
            )
        else:
            chat = existing
            if chat.push_name:
                continue
            chat.push_name = pn.pushname
            if chat.name == jid or chat.name == jid.replace(WHATSAPP_JID_SUFFIX, ""):
                chat.name = pn.pushname
        kv.put_cached_record(chat_key, chat)
        remember_chat(chat)
        chat_updates[jid] = _enum_to_str(asdict(chat))  # type: ignore[no-untyped-call]


def _process_lid_mappings(
    kv: GreenlineKV,
    mappings: List[PhoneNumberToLidMapping],
) -> None:
    for mapping in mappings:
        if mapping.lidJID and mapping.pnJID:
            canonical_lid = canonicalize_contact_jid(mapping.lidJID, jid_map={mapping.lidJID: mapping.lidJID})
            kv.put_cached_record(f"lid_map:{canonical_lid}", LidMapRecord(canonicalize_contact_jid(mapping.pnJID)))
