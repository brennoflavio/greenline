import base64
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from constants import GROUP_JID_SUFFIX, WHATSAPP_JID_SUFFIX
from models import ChatListItem, Message, MessageType, ReadReceipt
from ut_components.config import get_cache_path
from ut_components.kv import KV
from whatsmeow_types import MessageEvent


def _get_thumbnail_dir() -> str:
    return os.path.join(get_cache_path(), "thumbnails")


def resolve_sender(sender_jid: str, push_name: str = "") -> Tuple[str, str]:
    with KV() as kv:
        data = kv.get(f"chat:{sender_jid}")
    if data is not None:
        name = data.get("name", "")
        photo = data.get("photo", "")
        if name and name != sender_jid:
            return name, photo
    if push_name:
        return push_name, ""
    return sender_jid.replace(WHATSAPP_JID_SUFFIX, ""), ""


def message_event_to_message(evt: MessageEvent) -> Optional[Message]:
    info = evt.Info
    content = evt.Message

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
        and content.stickerMessage is None
    )
    if is_protocol_only:
        return None

    msg_type = _derive_message_type(info.Type, info.MediaType)
    if msg_type is None:
        return None

    text = ""
    caption = ""
    duration = ""

    if content.conversation:
        text = content.conversation
    elif content.extendedTextMessage:
        text = content.extendedTextMessage.text

    mimetype = ""
    file_name = ""

    if content.imageMessage:
        if content.imageMessage.caption:
            caption = content.imageMessage.caption
        mimetype = content.imageMessage.mimetype
    elif content.videoMessage:
        if content.videoMessage.caption:
            caption = content.videoMessage.caption
        mimetype = content.videoMessage.mimetype
        secs = content.videoMessage.seconds or 0
        duration = f"{secs // 60}:{secs % 60:02d}"
    elif content.audioMessage:
        mimetype = content.audioMessage.mimetype
        secs = content.audioMessage.seconds or 0
        duration = f"{secs // 60}:{secs % 60:02d}"
    elif content.documentMessage:
        if content.documentMessage.caption:
            caption = content.documentMessage.caption
        mimetype = content.documentMessage.mimetype
        file_name = content.documentMessage.fileName
    elif content.stickerMessage:
        mimetype = content.stickerMessage.mimetype

    ts = datetime.fromisoformat(info.Timestamp)
    timestamp_unix = int(ts.timestamp())
    timestamp_display = ts.strftime("%H:%M")

    read_receipt = ReadReceipt.SENT if info.IsFromMe else ReadReceipt.NONE

    sender_name = ""
    sender_photo = ""
    if not info.IsFromMe and info.Sender:
        sender_name, sender_photo = resolve_sender(info.Sender, info.PushName)

    return Message(
        id=info.ID,
        chat_id=info.Chat,
        type=msg_type,
        is_outgoing=info.IsFromMe,
        timestamp=timestamp_display,
        timestamp_unix=timestamp_unix,
        read_receipt=read_receipt,
        sender=info.Sender,
        sender_name=sender_name,
        sender_photo=sender_photo,
        text=text,
        caption=caption,
        mimetype=mimetype,
        file_name=file_name,
        duration=duration,
    )


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
        if media_type == "sticker":
            return MessageType.STICKER
        return None
    return None


def _message_preview(msg: Message) -> str:
    if msg.text:
        return msg.text
    if msg.caption:
        return msg.caption
    previews = {
        MessageType.IMAGE: "📷 Photo",
        MessageType.VIDEO: "🎥 Video",
        MessageType.AUDIO: "🎵 Audio",
        MessageType.DOCUMENT: "📄 Document",
        MessageType.STICKER: "🏷️ Sticker",
    }
    return previews.get(msg.type, msg.type)


def upsert_chat(msg: Message, push_name: str) -> ChatListItem:
    chat_key = f"chat:{msg.chat_id}"
    with KV() as kv:
        existing = kv.get(chat_key)

    preview = _message_preview(msg)

    is_group = msg.chat_id.endswith(GROUP_JID_SUFFIX)

    if existing is not None:
        chat = ChatListItem(**existing)
        if msg.timestamp_unix >= chat.last_message_timestamp:
            chat.last_message = preview
            chat.date = msg.timestamp
            chat.last_message_timestamp = msg.timestamp_unix
            if msg.is_outgoing:
                chat.read_receipt = msg.read_receipt
            else:
                chat.read_receipt = ReadReceipt.NONE
                chat.unread_count += 1
        if not is_group and push_name and chat.name == chat.id:
            chat.name = push_name
    else:
        name = msg.chat_id if is_group else (push_name or msg.chat_id)
        chat = ChatListItem(
            id=msg.chat_id,
            name=name,
            photo="",
            last_message=preview,
            date=msg.timestamp,
            last_message_timestamp=msg.timestamp_unix,
            read_receipt=msg.read_receipt if msg.is_outgoing else ReadReceipt.NONE,
            unread_count=0 if msg.is_outgoing else 1,
            is_group=is_group,
        )

    with KV() as kv:
        kv.put(chat_key, asdict(chat))
    return chat


@dataclass
class StoredMessage:
    message: Message
    chat: ChatListItem


def _extract_thumbnail(raw: Optional[Dict[str, Any]], message_id: str) -> str:
    if not raw:
        return ""
    msg_content = raw.get("Message", {})
    thumbnail_b64 = ""
    for field_name in ("imageMessage", "videoMessage", "documentMessage"):
        sub = msg_content.get(field_name)
        if sub and sub.get("JPEGThumbnail"):
            thumbnail_b64 = sub["JPEGThumbnail"]
            break
    if not thumbnail_b64:
        sticker = msg_content.get("stickerMessage")
        if sticker and sticker.get("pngThumbnail"):
            thumbnail_b64 = sticker["pngThumbnail"]
    if not thumbnail_b64:
        return ""
    try:
        data = base64.b64decode(thumbnail_b64)
    except Exception:
        return ""
    thumb_dir = _get_thumbnail_dir()
    os.makedirs(thumb_dir, exist_ok=True)
    ext = "png" if msg_content.get("stickerMessage") else "jpg"
    path = os.path.join(thumb_dir, f"{message_id}.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return "file://" + path


def store_message(evt: MessageEvent, raw: Optional[Dict[str, Any]] = None) -> Optional[StoredMessage]:
    msg = message_event_to_message(evt)
    if msg is None:
        return None

    msg.thumbnail_path = _extract_thumbnail(raw, msg.id)

    key = f"message:{msg.chat_id}:{msg.timestamp_unix}:{msg.id}"
    data = asdict(msg)
    data["raw"] = raw
    with KV() as kv:
        kv.put(key, data)

    chat = upsert_chat(msg, evt.Info.PushName)
    return StoredMessage(message=msg, chat=chat)
