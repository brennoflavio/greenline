from __future__ import annotations

from pathlib import Path
from typing import Any

from greenline.contracts.kv import GreenlineKV
from greenline.store.identity import remember_chat
from greenline.store.records import (
    DraftMentionsRecord,
    DraftRecord,
    stored_message_record,
)
from greenline.store.repository import message_storage_key, put_message_index
from models import ChatListItem, MentionSpan, Message, MessageType, ReadReceipt

DEFAULT_CHAT_ID = "111@s.whatsapp.net"
DEFAULT_SENDER_ID = "222@s.whatsapp.net"
DEFAULT_GROUP_ID = "333@g.us"


def _mention_span(span: MentionSpan | dict[str, object]) -> MentionSpan:
    if isinstance(span, MentionSpan):
        return span
    return MentionSpan(
        jid=str(span.get("jid") or ""),
        label=str(span.get("label") or ""),
        start=int(span.get("start") or 0),
        length=int(span.get("length") or 0),
    )


def seed_chat(
    chat_id: str = DEFAULT_CHAT_ID,
    *,
    name: str | None = None,
    photo: str = "file:///tmp/chat.jpg",
    last_message: str = "Seed message",
    date: str = "12:34",
    last_message_timestamp: int = 1_700_000_000,
    read_receipt: ReadReceipt = ReadReceipt.SENT,
    unread_count: int = 2,
    is_group: bool | None = None,
    last_message_mentioned_jids: list[str] | None = None,
    last_message_type: str = MessageType.TEXT.value,
    muted: bool = True,
    full_name: str = "Full Name",
    push_name: str = "Push Name",
    business_name: str = "Business Name",
    name_updated_at: int = 1_700_000_000,
) -> ChatListItem:
    chat = ChatListItem(
        id=chat_id,
        name=name or full_name or chat_id,
        photo=photo,
        last_message=last_message,
        date=date,
        last_message_timestamp=last_message_timestamp,
        read_receipt=read_receipt,
        unread_count=unread_count,
        is_group=chat_id.endswith("@g.us") if is_group is None else is_group,
        last_message_mentioned_jids=last_message_mentioned_jids or [],
        last_message_type=last_message_type,
        muted=muted,
        full_name=full_name,
        push_name=push_name,
        business_name=business_name,
        name_updated_at=name_updated_at,
    )
    with GreenlineKV() as kv:
        kv.put_record(f"chat:{chat_id}", chat)
    remember_chat(chat)
    return chat


def seed_sender_identity(
    sender_id: str = DEFAULT_SENDER_ID,
    *,
    name: str = "Sender Name",
    photo: str = "file:///tmp/sender.jpg",
) -> ChatListItem:
    return seed_chat(
        sender_id,
        name=name,
        photo=photo,
        last_message="",
        last_message_timestamp=0,
        read_receipt=ReadReceipt.NONE,
        unread_count=0,
        is_group=False,
        muted=False,
        full_name=name,
        push_name="",
        business_name="",
        name_updated_at=1_700_000_000,
    )


def seed_message(
    chat_id: str = DEFAULT_CHAT_ID,
    message_id: str = "message-1",
    *,
    message_type: MessageType = MessageType.TEXT,
    is_outgoing: bool = False,
    timestamp: str = "12:34",
    timestamp_unix: int = 1_700_000_000,
    read_receipt: ReadReceipt = ReadReceipt.DELIVERED,
    has_reactions: bool = False,
    sender: str = DEFAULT_SENDER_ID,
    sender_raw: str = DEFAULT_SENDER_ID,
    text: str = "Seed message",
    mentioned_jids: list[str] | None = None,
    mention_spans: list[MentionSpan | dict[str, object]] | None = None,
    reply_to_id: str = "reply-1",
    reply_to_sender_id: str = DEFAULT_SENDER_ID,
    reply_to_sender_raw: str = DEFAULT_SENDER_ID,
    reply_to_from_me: bool = False,
    reply_to_text: str = "Reply preview",
    reply_to_mentioned_jids: list[str] | None = None,
    media_path: str = "file:///tmp/media.bin",
    raw: dict[str, Any] | None = None,
    send_status: str = "",
    temp_id: str = "",
) -> Message:
    message = Message(
        id=message_id,
        chat_id=chat_id,
        type=message_type,
        is_outgoing=is_outgoing,
        timestamp=timestamp,
        timestamp_unix=timestamp_unix,
        read_receipt=read_receipt,
        has_reactions=has_reactions,
        sender=sender if not is_outgoing else "",
        sender_raw=sender_raw if not is_outgoing else "",
        text=(
            text
            if message_type in (MessageType.TEXT, MessageType.LINK_PREVIEW)
            else ("Fixture Location" if message_type == MessageType.LOCATION else "")
        ),
        mentioned_jids=mentioned_jids or [],
        mention_spans=[_mention_span(span) for span in mention_spans or []],
        image_source=media_path if message_type in (MessageType.IMAGE, MessageType.VIEW_ONCE) else "",
        caption=(
            "Caption"
            if message_type in (MessageType.IMAGE, MessageType.VIDEO, MessageType.DOCUMENT)
            else ("Fixture Address" if message_type == MessageType.LOCATION else "")
        ),
        duration="0:07" if message_type == MessageType.AUDIO else "",
        sticker_source=media_path if message_type == MessageType.STICKER else "",
        media_path=(
            media_path if message_type not in (MessageType.TEXT, MessageType.LINK_PREVIEW, MessageType.LOCATION) else ""
        ),
        thumbnail_path=(
            "file:///tmp/thumb.jpg"
            if message_type in (MessageType.VIDEO, MessageType.DOCUMENT, MessageType.LOCATION)
            else ""
        ),
        mimetype=(
            "application/octet-stream"
            if message_type not in (MessageType.TEXT, MessageType.LINK_PREVIEW, MessageType.LOCATION)
            else ""
        ),
        file_name="file.bin" if message_type in (MessageType.DOCUMENT, MessageType.CONTACT) else "",
        send_status=send_status,
        temp_id=temp_id,
        reply_to_id=reply_to_id,
        reply_to_sender_id=reply_to_sender_id,
        reply_to_sender_raw=reply_to_sender_raw,
        reply_to_from_me=reply_to_from_me,
        reply_to_text=reply_to_text,
        reply_to_mentioned_jids=reply_to_mentioned_jids or [],
        button_text="Open" if message_type == MessageType.LINK_PREVIEW else "",
        button_url="https://example.test" if message_type == MessageType.LINK_PREVIEW else "",
        link_title="Example" if message_type == MessageType.LINK_PREVIEW else "",
        link_description="Description" if message_type == MessageType.LINK_PREVIEW else "",
        link_url=(
            "https://example.test"
            if message_type == MessageType.LINK_PREVIEW
            else ("geo:1,2" if message_type == MessageType.LOCATION else "")
        ),
    )
    storage_key = message_storage_key(chat_id, timestamp_unix, message_id)
    with GreenlineKV() as kv:
        kv.put_record(storage_key, stored_message_record(message, raw))
        put_message_index(kv, chat_id, message_id, storage_key)
    return message


def seed_chat_with_message(
    chat_id: str = DEFAULT_CHAT_ID,
    message_id: str = "message-1",
    **message_kwargs: Any,
) -> tuple[ChatListItem, Message]:
    seed_sender_identity()
    message = seed_message(chat_id, message_id, **message_kwargs)
    chat = seed_chat(
        chat_id,
        last_message=message.text or message.caption or message.file_name or message.type.value,
        last_message_timestamp=message.timestamp_unix,
        read_receipt=message.read_receipt,
        last_message_type=message.type.value,
    )
    return chat, message


def seed_draft(
    chat_id: str = DEFAULT_CHAT_ID,
    text: str = "Hello @Sender",
    mention_spans: list[MentionSpan | dict[str, object]] | None = None,
) -> None:
    if mention_spans is None:
        mention_spans = [{"jid": DEFAULT_SENDER_ID, "label": "Sender", "start": 6, "length": 7}]
    with GreenlineKV() as kv:
        kv.put_record(f"draft:{chat_id}", DraftRecord(text))
        kv.put_record(f"draft_mentions:{chat_id}", DraftMentionsRecord([_mention_span(span) for span in mention_spans]))


def make_mention_span(
    jid: str = DEFAULT_SENDER_ID,
    label: str = "Sender",
    start: int = 0,
    length: int | None = None,
) -> dict[str, object]:
    return {"jid": jid, "label": label, "start": start, "length": length if length is not None else len(label) + 1}


def make_media_file(tmp_path: Path, name: str = "media.bin", content: bytes = b"greenline") -> str:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path)


def raw_downloadable_media(media_type: str = "image") -> dict[str, Any]:
    field_name = {
        "image": "imageMessage",
        "video": "videoMessage",
        "audio": "audioMessage",
        "document": "documentMessage",
        "sticker": "stickerMessage",
    }[media_type]
    return {
        "Message": {
            field_name: {
                "directPath": "/v/t62.7118/test",
                "mediaKey": "media-key",
                "fileEncSHA256": "enc-sha",
                "fileSHA256": "sha",
                "fileLength": 10,
                "mimetype": "application/octet-stream",
                "fileName": "file.bin",
            }
        }
    }


def seed_pending_message(chat_id: str = DEFAULT_CHAT_ID, message_id: str = "pending-1") -> Message:
    return seed_message(
        chat_id,
        message_id,
        is_outgoing=True,
        read_receipt=ReadReceipt.NONE,
        send_status="pending",
        temp_id=message_id,
    )


def seed_failed_message(chat_id: str = DEFAULT_CHAT_ID, message_id: str = "failed-1") -> Message:
    return seed_message(
        chat_id,
        message_id,
        is_outgoing=True,
        read_receipt=ReadReceipt.NONE,
        send_status="failed",
        temp_id=message_id,
    )


def assert_formatted_message_fields(payload: dict[str, Any]) -> None:
    assert isinstance(payload["formatted_text"], str)
    assert isinstance(payload["formatted_caption"], str)
    assert isinstance(payload["formatted_reply_to_text"], str)
