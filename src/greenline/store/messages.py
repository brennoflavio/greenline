from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from constants import GROUP_JID_SUFFIX
from greenline.contracts.kv import GreenlineKV
from greenline.store.identity import (
    canonicalize_contact_jid,
    remember_chat,
    update_chat_name,
    upsert_identity_chat,
)
from greenline.store.media import (
    _contact_preview,
    extract_thumbnail_from_message_content,
    location_preview,
    normalized_location_fields,
    persist_contact_vcard,
    resolve_media_message_content,
    template_message_button,
    template_message_caption,
    template_message_text,
)
from greenline.store.mentions import (
    _template_text_from_context_info,
    quoted_message_template,
)
from greenline.store.reactions import apply_message_reactions_flag
from greenline.store.records import message_from_record, stored_message_record
from greenline.store.repository import (
    _find_message_entry,
    message_storage_key,
    put_message_index,
)
from models import ChatListItem, Message, MessageType, ReadReceipt
from unread_counter import increment_unread_total
from whatsmeow_types import (
    MessageContent,
    MessageEvent,
    MessageInfo,
    UndecryptableMessageEvent,
)


def _extract_context_info(content: MessageContent) -> tuple[str, str, str, bool, str, List[str]]:
    ctx = None
    for sub in (
        content.extendedTextMessage,
        content.imageMessage,
        content.videoMessage,
        content.audioMessage,
        content.documentMessage,
        content.contactMessage,
        content.locationMessage,
        content.liveLocationMessage,
        content.stickerMessage,
    ):
        if sub is not None and getattr(sub, "contextInfo", None) is not None:
            ctx = sub.contextInfo
            break

    if ctx is None or not ctx.stanzaID:
        return "", "", "", False, "", []

    reply_to_sender_raw = str(ctx.participant) if ctx.participant else ""
    reply_to_sender_id = canonicalize_contact_jid(reply_to_sender_raw) if reply_to_sender_raw else ""
    reply_to_text, reply_to_mentioned_jids = quoted_message_template(ctx.quotedMessage)
    return ctx.stanzaID, reply_to_sender_id, reply_to_sender_raw, False, reply_to_text, reply_to_mentioned_jids


def message_event_to_message(evt: MessageEvent, raw: Optional[Dict[str, Any]] = None) -> Optional[Message]:
    info = evt.Info
    content = evt.Message
    raw_info = raw.get("Info", {}) if raw else {}
    raw_content = raw.get("Message", {}) if raw else {}
    chat_id = canonicalize_contact_jid(str(info.Chat or "")) if info.Chat else ""
    template_image = resolve_media_message_content(raw_content, "imageMessage")
    raw_location = raw_content.get("locationMessage") if isinstance(raw_content.get("locationMessage"), dict) else None
    raw_live_location = (
        raw_content.get("liveLocationMessage") if isinstance(raw_content.get("liveLocationMessage"), dict) else None
    )

    if info.Type == "reaction":
        return None

    is_protocol_only = (
        content.protocolMessage is not None
        and not content.conversation
        and content.extendedTextMessage is None
        and content.imageMessage is None
        and content.videoMessage is None
        and content.audioMessage is None
        and content.documentMessage is None
        and content.contactMessage is None
        and content.locationMessage is None
        and content.liveLocationMessage is None
        and content.stickerMessage is None
    )
    if is_protocol_only:
        return None

    template_text = template_message_text(raw_content)
    has_supported_content = any(
        (
            content.conversation,
            content.extendedTextMessage is not None,
            content.imageMessage is not None,
            content.videoMessage is not None,
            content.audioMessage is not None,
            content.documentMessage is not None,
            content.contactMessage is not None,
            content.locationMessage is not None,
            content.liveLocationMessage is not None,
            content.stickerMessage is not None,
            template_image is not None,
            raw_location is not None,
            raw_live_location is not None,
            template_text,
        )
    )
    if info.Edit == "1" and not has_supported_content:
        return None

    msg_type = _derive_message_type_from_content(content, raw_content)
    if msg_type is None:
        msg_type = _derive_message_type(info.Type, info.MediaType)
    if msg_type is None:
        return None

    text = ""
    caption = ""
    mentioned_jids: List[str] = []
    duration = ""
    button_text = ""
    button_url = ""

    if content.conversation:
        text = content.conversation
    elif content.extendedTextMessage:
        text, mentioned_jids = _template_text_from_context_info(
            content.extendedTextMessage.text,
            content.extendedTextMessage.contextInfo,
        )
    elif msg_type == MessageType.TEXT:
        text = template_text
        button_text, button_url = template_message_button(raw_content)

    mimetype = ""
    file_name = ""
    media_path = ""
    link_title = ""
    link_description = ""
    link_url = ""

    if content.imageMessage:
        if content.imageMessage.caption:
            caption, mentioned_jids = _template_text_from_context_info(
                content.imageMessage.caption,
                content.imageMessage.contextInfo,
            )
        mimetype = content.imageMessage.mimetype
    elif template_image:
        caption = template_message_caption(raw_content)
        mimetype = str(template_image.get("mimetype", ""))
        button_text, button_url = template_message_button(raw_content)
    elif content.videoMessage:
        if content.videoMessage.caption:
            caption, mentioned_jids = _template_text_from_context_info(
                content.videoMessage.caption,
                content.videoMessage.contextInfo,
            )
        mimetype = content.videoMessage.mimetype
        secs = content.videoMessage.seconds or 0
        duration = f"{secs // 60}:{secs % 60:02d}"
    elif content.audioMessage:
        mimetype = content.audioMessage.mimetype
        secs = content.audioMessage.seconds or 0
        duration = f"{secs // 60}:{secs % 60:02d}"
    elif content.documentMessage:
        if content.documentMessage.caption:
            caption, mentioned_jids = _template_text_from_context_info(
                content.documentMessage.caption,
                content.documentMessage.contextInfo,
            )
        mimetype = content.documentMessage.mimetype
        file_name = content.documentMessage.fileName
    elif content.contactMessage:
        file_name = content.contactMessage.displayName
        mimetype = "text/x-vcard"
        media_path = persist_contact_vcard(chat_id, info.ID, file_name, content.contactMessage.vcard)
    elif (
        content.locationMessage
        or content.liveLocationMessage
        or (msg_type == MessageType.LOCATION and (raw_location is not None or raw_live_location is not None))
    ):
        location_source = content.locationMessage or raw_location
        live_location_source = content.liveLocationMessage or raw_live_location
        text, caption, link_url = normalized_location_fields(location_source, live_location_source)
    elif content.stickerMessage:
        mimetype = content.stickerMessage.mimetype

    if msg_type == MessageType.LINK_PREVIEW and content.extendedTextMessage:
        ext = content.extendedTextMessage
        link_title = ext.title
        link_description = ext.description
        link_url = ext.matchedText

    reply_to_id, reply_to_sender_id, reply_to_sender_raw, reply_to_from_me, reply_to_text, reply_to_mentioned_jids = (
        _extract_context_info(content)
    )

    ts = datetime.fromisoformat(info.Timestamp)
    timestamp_unix = int(ts.timestamp())
    timestamp_display = ts.strftime("%H:%M")

    read_receipt = ReadReceipt.SENT if info.IsFromMe else ReadReceipt.NONE

    sender_raw = str(raw_info.get("SenderAlt") or raw_info.get("Sender") or info.Sender or "")
    sender = canonicalize_contact_jid(sender_raw) if sender_raw else ""

    return Message(
        id=info.ID,
        chat_id=chat_id,
        type=msg_type,
        is_outgoing=info.IsFromMe,
        timestamp=timestamp_display,
        timestamp_unix=timestamp_unix,
        read_receipt=read_receipt,
        edited=evt.IsEdit or info.Edit == "1",
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
        thumbnail_path=extract_thumbnail_from_message_content(raw_content, info.ID),
    )


def _derive_message_type_from_content(
    content: MessageContent,
    raw_content: Optional[Dict[str, Any]] = None,
) -> Optional[MessageType]:
    raw_content = raw_content or {}
    raw_location = raw_content.get("locationMessage") if isinstance(raw_content.get("locationMessage"), dict) else None
    raw_live_location = (
        raw_content.get("liveLocationMessage") if isinstance(raw_content.get("liveLocationMessage"), dict) else None
    )

    if content.imageMessage or resolve_media_message_content(raw_content, "imageMessage"):
        return MessageType.IMAGE
    if template_message_text(raw_content):
        return MessageType.TEXT
    if content.videoMessage:
        return MessageType.VIDEO
    if content.audioMessage:
        return MessageType.AUDIO
    if content.documentMessage:
        return MessageType.DOCUMENT
    if content.contactMessage:
        return MessageType.CONTACT
    if content.locationMessage or raw_location or content.liveLocationMessage or raw_live_location:
        return MessageType.LOCATION
    if content.stickerMessage:
        return MessageType.STICKER
    if content.extendedTextMessage:
        ext = content.extendedTextMessage
        if ext.matchedText or ext.title:
            return MessageType.LINK_PREVIEW
        return MessageType.TEXT
    if content.conversation:
        return MessageType.TEXT
    return None


def _derive_message_type(info_type: str, media_type: str) -> Optional[MessageType]:
    if info_type == "text":
        return MessageType.TEXT
    if info_type == "media":
        if media_type == "image":
            return MessageType.IMAGE
        if media_type == "video":
            return MessageType.VIDEO
        if media_type == "audio" or media_type == "ptt":
            return MessageType.AUDIO
        if media_type == "document":
            return MessageType.DOCUMENT
        if media_type == "vcard":
            return MessageType.CONTACT
        if media_type == "location" or media_type == "livelocation":
            return MessageType.LOCATION
        if media_type in ("sticker", "user_created_sticker"):
            return MessageType.STICKER
        if media_type == "url":
            return MessageType.LINK_PREVIEW
        return None
    return None


def undecryptable_event_to_message(
    evt: UndecryptableMessageEvent,
    raw: Optional[Dict[str, Any]] = None,
) -> Optional[Message]:
    if not evt.IsUnavailable or evt.UnavailableType != MessageType.VIEW_ONCE:
        return None

    info = evt.Info
    raw_info = raw.get("Info", {}) if raw else {}
    chat_id = canonicalize_contact_jid(str(info.Chat or "")) if info.Chat else ""
    ts = datetime.fromisoformat(info.Timestamp)
    timestamp_unix = int(ts.timestamp())
    timestamp_display = ts.strftime("%H:%M")
    read_receipt = ReadReceipt.SENT if info.IsFromMe else ReadReceipt.NONE

    sender_raw = str(raw_info.get("SenderAlt") or raw_info.get("Sender") or info.Sender or "")
    sender = canonicalize_contact_jid(sender_raw) if sender_raw else ""

    return Message(
        id=info.ID,
        chat_id=chat_id,
        type=MessageType.VIEW_ONCE,
        is_outgoing=info.IsFromMe,
        timestamp=timestamp_display,
        timestamp_unix=timestamp_unix,
        read_receipt=read_receipt,
        sender=sender,
        sender_raw=sender_raw,
        text="",
    )


def _message_preview_data(msg: Message) -> tuple[str, List[str]]:
    if msg.type == MessageType.DELETED:
        return "Deleted message", []
    if msg.type == MessageType.LOCATION:
        return location_preview(msg.text, msg.caption), []
    if msg.text:
        return msg.text, list(msg.mentioned_jids)
    if msg.caption:
        return msg.caption, list(msg.mentioned_jids)
    if msg.type == MessageType.CONTACT:
        return _contact_preview(msg.file_name), []
    previews = {
        MessageType.IMAGE: "📷 Photo",
        MessageType.VIDEO: "🎥 Video",
        MessageType.AUDIO: "🎵 Audio",
        MessageType.DOCUMENT: "📄 Document",
        MessageType.STICKER: "🏷️ Sticker",
        MessageType.LINK_PREVIEW: "🔗 Link",
        MessageType.LOCATION: "📍 Location",
    }
    return previews.get(msg.type, msg.type), []


def _message_preview(msg: Message) -> str:
    preview, _ = _message_preview_data(msg)
    return preview


def upsert_chat(msg: Message, info: MessageInfo, *, count_unread: bool = True) -> ChatListItem:
    chat_key = f"chat:{msg.chat_id}"
    with GreenlineKV() as kv:
        existing = cast(ChatListItem | None, kv.get_record(chat_key))

    preview, preview_mentioned_jids = _message_preview_data(msg)
    is_group = msg.chat_id.endswith(GROUP_JID_SUFFIX)

    push_name = info.PushName
    direct_push_name = "" if msg.is_outgoing else push_name
    business_name = ""
    if info.VerifiedName and info.VerifiedName.Details:
        business_name = info.VerifiedName.Details.verifiedName
    direct_business_name = "" if msg.is_outgoing else business_name

    if existing is not None:
        chat = existing
        if msg.timestamp_unix >= chat.last_message_timestamp:
            chat.last_message = preview
            chat.last_message_mentioned_jids = preview_mentioned_jids
            chat.last_message_type = str(msg.type)
            chat.date = msg.timestamp
            chat.last_message_timestamp = msg.timestamp_unix
            if msg.is_outgoing:
                chat.read_receipt = msg.read_receipt
            else:
                chat.read_receipt = ReadReceipt.NONE
                if count_unread:
                    chat.unread_count += 1
                    increment_unread_total()
        if not is_group:
            update_chat_name(
                chat,
                msg.timestamp_unix,
                push_name=direct_push_name,
                business_name=direct_business_name,
            )
    else:
        display_name = msg.chat_id
        if not is_group:
            display_name = direct_push_name or direct_business_name or msg.chat_id
        chat = ChatListItem(
            id=msg.chat_id,
            name=display_name,
            photo="",
            last_message=preview,
            date=msg.timestamp,
            last_message_timestamp=msg.timestamp_unix,
            read_receipt=msg.read_receipt if msg.is_outgoing else ReadReceipt.NONE,
            unread_count=0 if msg.is_outgoing or not count_unread else 1,
            is_group=is_group,
            last_message_mentioned_jids=preview_mentioned_jids,
            last_message_type=str(msg.type),
            push_name=direct_push_name if not is_group else "",
            business_name=direct_business_name if not is_group else "",
            name_updated_at=msg.timestamp_unix,
        )
        if not msg.is_outgoing and count_unread:
            increment_unread_total()

    with GreenlineKV() as kv:
        kv.put_record(chat_key, chat)
    remember_chat(chat)
    return chat


@dataclass
class StoredMessage:
    message: Message
    chat: ChatListItem


def _deleted_message_target_id(evt: MessageEvent, raw: Optional[Dict[str, Any]]) -> str:
    target_id = evt.Info.MsgBotInfo.EditTargetID or evt.Info.MsgMetaInfo.TargetID
    if target_id:
        return str(target_id)

    protocol_message = (raw or {}).get("Message", {}).get("protocolMessage") or {}
    if not isinstance(protocol_message, dict):
        return ""

    key = protocol_message.get("key") or {}
    if not isinstance(key, dict):
        return ""

    return str(key.get("ID") or key.get("id") or "")


def _merge_edited_message(existing: Message, updated: Message) -> Message:
    return replace(
        existing,
        type=updated.type,
        edited=True,
        sender=updated.sender or existing.sender,
        sender_raw=updated.sender_raw or existing.sender_raw,
        text=updated.text,
        mentioned_jids=list(updated.mentioned_jids),
        mention_spans=list(updated.mention_spans),
        image_source=updated.image_source or existing.image_source,
        caption=updated.caption,
        images=list(updated.images) or list(existing.images),
        duration=updated.duration or existing.duration,
        sticker_source=updated.sticker_source or existing.sticker_source,
        media_path=updated.media_path or existing.media_path,
        thumbnail_path=updated.thumbnail_path or existing.thumbnail_path,
        mimetype=updated.mimetype or existing.mimetype,
        file_name=updated.file_name or existing.file_name,
        reply_to_id=updated.reply_to_id,
        reply_to_sender_id=updated.reply_to_sender_id,
        reply_to_sender_raw=updated.reply_to_sender_raw,
        reply_to_from_me=updated.reply_to_from_me,
        reply_to_text=updated.reply_to_text,
        reply_to_mentioned_jids=list(updated.reply_to_mentioned_jids),
        button_text=updated.button_text,
        button_url=updated.button_url,
        link_title=updated.link_title,
        link_description=updated.link_description,
        link_url=updated.link_url,
    )


def _merge_deleted_message(existing: Message, sender: str, sender_raw: str = "") -> Message:
    return replace(
        existing,
        type=MessageType.DELETED,
        edited=False,
        sender=sender or existing.sender,
        sender_raw=sender_raw or existing.sender_raw,
        text="",
        mentioned_jids=[],
        mention_spans=[],
        image_source="",
        caption="",
        images=[],
        duration="",
        sticker_source="",
        media_path="",
        thumbnail_path="",
        mimetype="",
        file_name="",
        send_status="",
        temp_id="",
        button_text="",
        button_url="",
        link_title="",
        link_description="",
        link_url="",
    )


def _update_chat_after_edit(kv: GreenlineKV, msg: Message, info: MessageInfo) -> ChatListItem:
    chat_key = f"chat:{msg.chat_id}"
    chat = cast(ChatListItem | None, kv.get_record(chat_key))
    if chat is None:
        return upsert_chat(msg, info, count_unread=False)

    latest_entries, _ = kv.get_partial_page_records(f"message:{msg.chat_id}:", page_size=1, reverse=True)
    latest_id = latest_entries[0][1].id if latest_entries else ""

    if latest_id == msg.id:
        preview, preview_mentioned_jids = _message_preview_data(msg)
        chat.last_message = preview
        chat.last_message_mentioned_jids = preview_mentioned_jids
        chat.last_message_type = str(msg.type)
        kv.put_record(chat_key, chat)
        remember_chat(chat)

    return chat


def store_message(evt: MessageEvent, raw: Optional[Dict[str, Any]] = None) -> Optional[StoredMessage]:
    if evt.Info.Edit == "7":
        target_id = _deleted_message_target_id(evt, raw)
        if not target_id:
            return None

        chat_id = canonicalize_contact_jid(str(evt.Info.Chat or "")) if evt.Info.Chat else ""
        with GreenlineKV() as kv:
            existing_key, existing_value = _find_message_entry(kv, chat_id, target_id)
            if existing_key is None or existing_value is None:
                return None
            existing_msg = message_from_record(existing_value)
            deleted_msg = _merge_deleted_message(
                existing_msg,
                canonicalize_contact_jid(str(evt.Info.Sender or "")),
                str(evt.Info.Sender or ""),
            )
            deleted_msg = apply_message_reactions_flag(deleted_msg, kv)
            kv.put_record(existing_key, stored_message_record(deleted_msg, raw))
            chat = _update_chat_after_edit(kv, deleted_msg, evt.Info)
            return StoredMessage(message=deleted_msg, chat=chat)

    msg = message_event_to_message(evt, raw)
    if msg is None:
        return None

    business_name = ""
    if evt.Info.VerifiedName and evt.Info.VerifiedName.Details:
        business_name = evt.Info.VerifiedName.Details.verifiedName
    if msg.sender and not msg.is_outgoing:
        upsert_identity_chat(
            msg.sender,
            msg.timestamp_unix,
            push_name=evt.Info.PushName,
            business_name=business_name,
        )

    with GreenlineKV() as kv:
        if msg.edited:
            existing_key, existing_value = _find_message_entry(kv, msg.chat_id, msg.id)
            if existing_key is None or existing_value is None:
                return None
            existing_msg = message_from_record(existing_value)
            msg = _merge_edited_message(existing_msg, msg)
            msg = apply_message_reactions_flag(msg, kv)
            kv.put_record(existing_key, stored_message_record(msg, raw))
            put_message_index(kv, msg.chat_id, msg.id, existing_key)
            chat = _update_chat_after_edit(kv, msg, evt.Info)
            return StoredMessage(message=msg, chat=chat)

        key = message_storage_key(msg.chat_id, msg.timestamp_unix, msg.id)
        already_stored = kv.get_record(key) is not None
        msg = apply_message_reactions_flag(msg, kv)
        kv.put_record(key, stored_message_record(msg, raw))
        put_message_index(kv, msg.chat_id, msg.id, key)

    chat = upsert_chat(msg, evt.Info, count_unread=not already_stored)
    return StoredMessage(message=msg, chat=chat)


def store_undecryptable_message(
    evt: UndecryptableMessageEvent,
    raw: Optional[Dict[str, Any]] = None,
) -> Optional[StoredMessage]:
    msg = undecryptable_event_to_message(evt, raw=raw)
    if msg is None:
        return None

    if msg.sender and not msg.is_outgoing:
        upsert_identity_chat(
            msg.sender,
            msg.timestamp_unix,
            push_name=evt.Info.PushName,
        )

    key = message_storage_key(msg.chat_id, msg.timestamp_unix, msg.id)
    with GreenlineKV() as kv:
        already_stored = kv.get_record(key) is not None
        msg = apply_message_reactions_flag(msg, kv)
        kv.put_record(key, stored_message_record(msg, raw))
        put_message_index(kv, msg.chat_id, msg.id, key)

    chat = upsert_chat(msg, evt.Info, count_unread=not already_stored)
    return StoredMessage(message=msg, chat=chat)
