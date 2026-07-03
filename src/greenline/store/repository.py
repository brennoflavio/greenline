from dataclasses import replace
from typing import Any, Optional, Tuple

from greenline.contracts.kv import GreenlineKV
from greenline.qml_text import (
    TEXT_RENDER_MODE_SIMPLE,
    TextRenderData,
    build_text_render_data,
    format_qml_text,
)
from greenline.store.identity import resolve_sender_name, resolve_sender_photo
from greenline.store.mentions import render_mention_text
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
    if message.text and (message.rendered_text or message.rendered_formatted_text):
        text_render_data = TextRenderData(
            plain_text=message.rendered_text or render_mention_text(message.text, message.mentioned_jids),
            rich_text=message.rendered_formatted_text
            or format_qml_text(message.text, message.mentioned_jids, message.mention_spans),
            render_mode=message.text_render_mode or TEXT_RENDER_MODE_SIMPLE,
        )
    else:
        text_render_data = build_text_render_data(message.text, message.mentioned_jids, message.mention_spans)

    formatted_caption = format_qml_text(message.caption, message.mentioned_jids)
    reply_preview_text = _resolve_reply_preview_text(message)
    rendered_reply_to_text = render_mention_text(reply_preview_text, message.reply_to_mentioned_jids)
    formatted_reply_to_text = format_qml_text(reply_preview_text, message.reply_to_mentioned_jids)
    rendered = replace(
        message,
        text=text_render_data.plain_text,
        rendered_text=text_render_data.plain_text,
        rendered_formatted_text=text_render_data.rich_text,
        text_render_mode=text_render_data.render_mode,
        caption=render_mention_text(message.caption, message.mentioned_jids),
        reply_to_text=rendered_reply_to_text,
    )

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

    payload = dict(vars(rendered))
    payload["formatted_text"] = text_render_data.rich_text
    payload["formatted_caption"] = formatted_caption
    payload["reply_to_text"] = rendered_reply_to_text
    payload["formatted_reply_to_text"] = formatted_reply_to_text

    return UiMessage(
        **payload,
        sender_name=sender_name,
        sender_photo=sender_photo,
        reply_to_sender=reply_to_sender,
    )
