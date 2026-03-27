from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from constants import GROUP_JID_SUFFIX
from models import ChatListItem, Message, MessageType, ReadReceipt
from ut_components.kv import KV
from whatsmeow_types import MessageEvent


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
    )
    if is_protocol_only:
        return None

    msg_type = _derive_message_type(info.Type, info.MediaType)
    if msg_type is None:
        return None

    text = ""
    caption = ""

    if content.conversation:
        text = content.conversation
    elif content.extendedTextMessage:
        text = content.extendedTextMessage.text

    if content.imageMessage and content.imageMessage.caption:
        caption = content.imageMessage.caption

    if msg_type == MessageType.TEXT and info.MediaType == "video":
        text = text or "[Video]"

    ts = datetime.fromisoformat(info.Timestamp)
    timestamp_unix = int(ts.timestamp())
    timestamp_display = ts.strftime("%H:%M")

    read_receipt = ReadReceipt.SENT if info.IsFromMe else ReadReceipt.NONE

    return Message(
        id=info.ID,
        chat_id=info.Chat,
        type=msg_type,
        is_outgoing=info.IsFromMe,
        timestamp=timestamp_display,
        timestamp_unix=timestamp_unix,
        read_receipt=read_receipt,
        text=text,
        caption=caption,
    )


def _derive_message_type(info_type: str, media_type: str) -> Optional[MessageType]:
    if info_type == "text":
        return MessageType.TEXT
    if info_type == "media":
        if media_type == "image":
            return MessageType.IMAGE
        if media_type == "video":
            return MessageType.TEXT
        return None
    return None


def _message_preview(msg: Message) -> str:
    if msg.text:
        return msg.text
    if msg.caption:
        return msg.caption
    if msg.type == MessageType.IMAGE:
        return "📷 Photo"
    return msg.type


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


def store_message(evt: MessageEvent, raw: Optional[Dict[str, Any]] = None) -> Optional[StoredMessage]:
    msg = message_event_to_message(evt)
    if msg is None:
        return None

    key = f"message:{msg.chat_id}:{msg.timestamp_unix}:{msg.id}"
    data = asdict(msg)
    data["raw"] = raw
    with KV() as kv:
        kv.put(key, data)

    chat = upsert_chat(msg, evt.Info.PushName)
    return StoredMessage(message=msg, chat=chat)
