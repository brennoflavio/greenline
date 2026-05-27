from dataclasses import asdict
from typing import Any, Optional, Tuple

from greenline.contracts.kv import GreenlineKV
from greenline.store.identity import resolve_sender_name, resolve_sender_photo
from greenline.store.mentions import render_message_mentions
from greenline.store.records import (
    MessageIndexRecord,
    StoredMessageRecord,
    message_from_record,
)
from models import Message, MessageType, UiMessage

_DELETED_MESSAGE_PREVIEW = "Deleted message"


def message_storage_key(chat_id: str, timestamp_unix: int, message_id: str) -> str:
    return f"message:{chat_id}:{timestamp_unix}:{message_id}"


def message_index_key(chat_id: str, message_id: str) -> str:
    return f"message_index:{chat_id}:{message_id}"


def _greenline_kv(kv: Any) -> GreenlineKV:
    if isinstance(kv, GreenlineKV):
        return kv
    return GreenlineKV(kv)


def put_message_index(kv: Any, chat_id: str, message_id: str, storage_key: str) -> None:
    if not chat_id or not message_id or not storage_key:
        return
    _greenline_kv(kv).put_record(message_index_key(chat_id, message_id), MessageIndexRecord(storage_key))


def delete_message_index(kv: Any, chat_id: str, message_id: str) -> None:
    if not chat_id or not message_id:
        return
    _greenline_kv(kv).delete(message_index_key(chat_id, message_id))


def get_message_entry_with_key(
    kv: Any,
    chat_id: str,
    message_id: str,
) -> Tuple[str, StoredMessageRecord] | tuple[None, None]:
    if not chat_id or not message_id:
        return None, None

    typed_kv = _greenline_kv(kv)
    index_record = typed_kv.get_record(message_index_key(chat_id, message_id))
    if not isinstance(index_record, MessageIndexRecord) or not index_record.value:
        return None, None

    indexed_key = index_record.value
    indexed_value = typed_kv.get_record(indexed_key)
    if (
        indexed_key.startswith(f"message:{chat_id}:")
        and isinstance(indexed_value, StoredMessageRecord)
        and indexed_value.id == message_id
        and indexed_value.chat_id == chat_id
    ):
        return indexed_key, indexed_value

    delete_message_index(typed_kv, chat_id, message_id)
    return None, None


def _find_message_entry(kv: Any, chat_id: str, message_id: str) -> Tuple[str, StoredMessageRecord] | tuple[None, None]:
    return get_message_entry_with_key(kv, chat_id, message_id)


def _get_stored_message(chat_id: str, message_id: str) -> Optional[Message]:
    if not chat_id or not message_id:
        return None

    with GreenlineKV() as kv:
        _, value = _find_message_entry(kv, chat_id, message_id)
    if value is None:
        return None

    return message_from_record(value)


def _resolve_reply_preview_text(message: Message) -> str:
    if not message.reply_to_id:
        return message.reply_to_text

    replied_to = _get_stored_message(message.chat_id, message.reply_to_id)
    if replied_to is None or replied_to.type != MessageType.DELETED:
        return message.reply_to_text

    return _DELETED_MESSAGE_PREVIEW


def to_ui_message(message: Message) -> UiMessage:
    rendered = render_message_mentions(message)

    sender_name = ""
    sender_photo = ""
    if rendered.sender and not rendered.is_outgoing:
        sender_name = resolve_sender_name(rendered.sender)
        sender_photo = resolve_sender_photo(rendered.sender)

    reply_to_sender = ""
    if rendered.reply_to_from_me:
        reply_to_sender = "You"
    elif rendered.reply_to_sender_id:
        reply_to_sender = resolve_sender_name(rendered.reply_to_sender_id)

    payload = asdict(rendered)
    payload["reply_to_text"] = _resolve_reply_preview_text(rendered)

    return UiMessage(
        **payload,
        sender_name=sender_name,
        sender_photo=sender_photo,
        reply_to_sender=reply_to_sender,
    )
