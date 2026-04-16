from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from dacite import from_dict

from constants import GROUP_JID_SUFFIX, WHATSAPP_JID_SUFFIX
from message_store import (
    _extract_thumbnail,
    _quoted_message_preview,
    resolve_sender_name,
)
from models import ChatListItem, Message, MessageType, ReadReceipt
from rpc import DaemonRPC
from ut_components.kv import KV
from ut_components.utils import enum_to_str as _enum_to_str
from whatsmeow_types import (
    HistorySyncConversation,
    HistorySyncEvent,
    HistorySyncInnerMessage,
    HistorySyncPushname,
    PhoneNumberToLidMapping,
)

STATUS_BROADCAST_JID = "status@broadcast"
NEWSLETTER_SERVER = "@newsletter"

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

    with KV() as kv:
        for conv in conversations:
            chat_jid = jid_map.get(conv.ID, conv.ID)
            if chat_jid == STATUS_BROADCAST_JID:
                continue
            if chat_jid.endswith(NEWSLETTER_SERVER):
                continue

            _process_messages(kv, conv, chat_jid, jid_map)
            chat_dict = _process_conversation(kv, conv, chat_jid)
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
            lid_to_pn[mapping.lidJID] = mapping.pnJID

    jids: Set[str] = set()
    for conv in evt.Data.conversations or []:
        jids.add(conv.ID)
        for msg_wrap in conv.messages or []:
            if msg_wrap.message.participant:
                jids.add(msg_wrap.message.participant)
    for pn in evt.Data.pushnames or []:
        if pn.ID:
            jids.add(pn.ID)

    jid_map: Dict[str, str] = {}
    rpc = DaemonRPC()
    for jid in jids:
        if jid in lid_to_pn:
            jid_map[jid] = lid_to_pn[jid]
        elif "@lid" in jid:
            try:
                jid_map[jid] = rpc.ensure_jid(jid)
            except Exception:
                jid_map[jid] = jid
        else:
            jid_map[jid] = jid

    return jid_map


def _derive_type_from_content(content: Dict[str, Any]) -> Optional[MessageType]:
    ext = content.get("extendedTextMessage")
    if ext and (ext.get("matchedText") or ext.get("title")):
        return MessageType.LINK_PREVIEW
    if content.get("conversation") or ext:
        return MessageType.TEXT
    if content.get("imageMessage"):
        return MessageType.IMAGE
    if content.get("videoMessage"):
        return MessageType.VIDEO
    if content.get("audioMessage"):
        return MessageType.AUDIO
    if content.get("documentMessage"):
        return MessageType.DOCUMENT
    if content.get("stickerMessage"):
        return MessageType.STICKER
    return None


def _extract_content_fields(content: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    """Returns (text, caption, mimetype, file_name, duration)."""
    text = ""
    caption = ""
    mimetype = ""
    file_name = ""
    duration = ""

    if content.get("conversation"):
        text = content["conversation"]
    elif content.get("extendedTextMessage"):
        text = content["extendedTextMessage"].get("text", "")

    img = content.get("imageMessage")
    vid = content.get("videoMessage")
    aud = content.get("audioMessage")
    doc = content.get("documentMessage")
    stk = content.get("stickerMessage")

    if img:
        caption = img.get("caption", "")
        mimetype = img.get("mimetype", "")
    elif vid:
        caption = vid.get("caption", "")
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
        caption = doc.get("caption", "")
        mimetype = doc.get("mimetype", "")
        file_name = doc.get("fileName", "")
    elif stk:
        mimetype = stk.get("mimetype", "")

    return text, caption, mimetype, file_name, duration


def _extract_link_preview_fields(content: Dict[str, Any]) -> Tuple[str, str, str]:
    ext = content.get("extendedTextMessage")
    if not ext:
        return "", "", ""
    return ext.get("title", ""), ext.get("description", ""), ext.get("matchedText", "")


def _message_preview(content: Dict[str, Any]) -> str:
    if content.get("conversation"):
        return str(content["conversation"])
    ext = content.get("extendedTextMessage")
    if ext and ext.get("text"):
        return str(ext["text"])
    img = content.get("imageMessage")
    if img:
        return img.get("caption") or "📷 Photo"
    vid = content.get("videoMessage")
    if vid:
        return vid.get("caption") or "🎥 Video"
    if content.get("audioMessage"):
        return "🎵 Audio"
    doc = content.get("documentMessage")
    if doc:
        return doc.get("caption") or "📄 Document"
    if content.get("stickerMessage"):
        return "🏷️ Sticker"
    return ""


def _find_latest_message(conv: HistorySyncConversation) -> Optional[HistorySyncInnerMessage]:
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


def _extract_context_info_from_dict(content: Dict[str, Any], jid_map: Dict[str, str]) -> Tuple[str, str, str]:
    for field_name in (
        "extendedTextMessage",
        "imageMessage",
        "videoMessage",
        "audioMessage",
        "documentMessage",
        "stickerMessage",
    ):
        sub = content.get(field_name)
        if sub and isinstance(sub, dict):
            ctx = sub.get("contextInfo")
            if ctx and ctx.get("stanzaID"):
                reply_to_id = ctx["stanzaID"]
                participant = ctx.get("participant", "")
                if participant:
                    participant = jid_map.get(participant, participant)
                reply_to_sender = resolve_sender_name(participant) if participant else ""
                reply_to_text = _quoted_message_preview(ctx.get("quotedMessage"))
                return reply_to_id, reply_to_sender, reply_to_text
    return "", "", ""


def _process_messages(
    kv: KV,
    conv: HistorySyncConversation,
    chat_jid: str,
    jid_map: Dict[str, str],
) -> None:
    messages = conv.messages or []
    if not messages:
        return

    existing_entries = kv.get_partial(f"message:{chat_jid}:")
    existing_ids: Set[str] = {v.get("id", "") for _, v in existing_entries}

    sender_cache: Dict[str, str] = {}

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
        text, caption, mimetype, file_name, duration = _extract_content_fields(content)

        is_outgoing = inner.key.fromMe
        read_receipt = ReadReceipt.NONE
        if is_outgoing:
            read_receipt = _STATUS_TO_RECEIPT.get(inner.status, ReadReceipt.SENT)

        sender = ""
        sender_name = ""
        if not is_outgoing and inner.participant:
            sender = jid_map.get(inner.participant, inner.participant)
            if sender not in sender_cache:
                sender_cache[sender] = resolve_sender_name(sender)
            sender_name = sender_cache[sender]

        reply_to_id, reply_to_sender, reply_to_text = _extract_context_info_from_dict(content, jid_map)

        link_title, link_description, link_url = (
            _extract_link_preview_fields(content) if msg_type == MessageType.LINK_PREVIEW else ("", "", "")
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
            sender_name=sender_name,
            text=text,
            caption=caption,
            mimetype=mimetype,
            file_name=file_name,
            duration=duration,
            reply_to_id=reply_to_id,
            reply_to_sender=reply_to_sender,
            reply_to_text=reply_to_text,
            link_title=link_title,
            link_description=link_description,
            link_url=link_url,
        )

        msg.thumbnail_path = _extract_thumbnail({"Message": content}, msg_id)

        key = f"message:{chat_jid}:{ts_unix}:{msg_id}"
        data = asdict(msg)
        data["raw"] = {"Message": content}
        kv.put_cached(key, data)


def _process_conversation(
    kv: KV,
    conv: HistorySyncConversation,
    chat_jid: str,
) -> Optional[Dict[str, Any]]:
    is_group = chat_jid.endswith(GROUP_JID_SUFFIX)
    latest_msg = _find_latest_message(conv)

    chat_key = f"chat:{chat_jid}"
    existing = kv.get(chat_key)

    if existing is not None:
        chat = ChatListItem(**existing)
        changed = False

        if latest_msg is not None and latest_msg.messageTimestamp > chat.last_message_timestamp:
            preview = _message_preview(latest_msg.message) if latest_msg.message else ""
            if preview:
                chat.last_message = preview
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

        kv.put_cached(chat_key, asdict(chat))
        return _enum_to_str(asdict(chat))  # type: ignore[no-any-return, no-untyped-call]

    last_ts = conv.conversationTimestamp or 0
    if latest_msg is None and not last_ts:
        return None

    preview = ""
    date = ""
    read_receipt = ReadReceipt.NONE

    if latest_msg is not None:
        preview = _message_preview(latest_msg.message or {})
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
    )

    kv.put_cached(chat_key, asdict(chat))
    return _enum_to_str(asdict(chat))  # type: ignore[no-any-return, no-untyped-call]


def _process_pushnames(
    kv: KV,
    pushnames: List[HistorySyncPushname],
    jid_map: Dict[str, str],
    chat_updates: Dict[str, Dict[str, Any]],
) -> None:
    for pn in pushnames:
        if not pn.pushname or not pn.ID:
            continue
        jid = jid_map.get(pn.ID, pn.ID)
        chat_key = f"chat:{jid}"
        existing = kv.get(chat_key)
        if existing is None:
            continue
        chat = ChatListItem(**existing)
        if chat.push_name:
            continue
        chat.push_name = pn.pushname
        if chat.name == jid or chat.name == jid.replace(WHATSAPP_JID_SUFFIX, ""):
            chat.name = pn.pushname
            kv.put_cached(chat_key, asdict(chat))
            chat_updates[jid] = _enum_to_str(asdict(chat))  # type: ignore[no-untyped-call]


def _process_lid_mappings(
    kv: KV,
    mappings: List[PhoneNumberToLidMapping],
) -> None:
    for mapping in mappings:
        if mapping.lidJID and mapping.pnJID:
            kv.put_cached(f"lid_map:{mapping.lidJID}", mapping.pnJID)
