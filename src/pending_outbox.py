import os
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable

from daemon_types import SendMessageReply
from greenline import qml_events
from greenline.contracts.daemon import daemon_client
from greenline.contracts.kv import GreenlineKV
from greenline.store.mentions import mention_transport_payload
from greenline.store.messages import upsert_chat
from greenline.store.records import (
    PendingOutboxRecord,
    StoredMessageRecord,
    message_from_record,
    stored_message_record,
)
from greenline.store.repository import (
    delete_message_index,
)
from greenline.store.repository import (
    get_message_entry_with_key as _lookup_message_entry_with_key,
)
from greenline.store.repository import message_storage_key as _message_storage_key
from greenline.store.repository import (
    put_message_index,
)
from models import ChatListItem, Message, MessageType, ReadReceipt
from ut_components.event import Event
from whatsmeow_types import MessageInfo

PENDING_RETRY_INTERVAL_SECONDS = 5
PENDING_RETRY_MAX_BACKOFF_SECONDS = 300
PENDING_OUTBOX_KEY_PREFIX = "pending-outbox:"
_PENDING_SEND_LOCK = threading.Lock()
_PENDING_SEND_IN_FLIGHT: set[str] = set()

ReplyContextResolver = Callable[[str, dict[str, object] | None], dict[str, object] | None]


class UnsupportedPendingMessageTypeError(ValueError):
    pass


def _pending_outbox_key(chat_id: str, message_id: str) -> str:
    return f"{PENDING_OUTBOX_KEY_PREFIX}{chat_id}:{message_id}"


def _pending_send_token(chat_id: str, message_id: str) -> str:
    return f"{chat_id}:{message_id}"


def _get_message_entry_with_key(chat_id: str, message_id: str) -> tuple[str, StoredMessageRecord] | tuple[None, None]:
    with GreenlineKV() as kv:
        return _lookup_message_entry_with_key(kv, chat_id, message_id)


def _local_media_path(media_path: str) -> str:
    if media_path.startswith("file://"):
        return media_path[7:]
    return media_path


def _message_storage_record(message: Message) -> StoredMessageRecord:
    raw = None

    if message.type == MessageType.CONTACT and message.media_path:
        contact_path = _local_media_path(message.media_path)
        if contact_path and os.path.exists(contact_path):
            try:
                with open(contact_path, encoding="utf-8-sig") as f:
                    vcard = f.read()
                raw = {
                    "Message": {
                        "contactMessage": {
                            "displayName": message.file_name or "Contact",
                            "vcard": vcard,
                        }
                    }
                }
            except Exception:
                pass

    return stored_message_record(message, raw)


def _parse_duration_seconds(duration: str) -> int:
    parts = duration.split(":", 1)
    if len(parts) != 2:
        return 0

    try:
        minutes = int(parts[0])
        seconds = int(parts[1])
    except ValueError:
        return 0

    return max(0, minutes * 60 + seconds)


def _pending_reply_context(
    message: Message,
    resolve_reply_context: ReplyContextResolver,
) -> dict[str, object] | None:
    if not message.reply_to_id:
        return None

    return resolve_reply_context(
        message.chat_id,
        {
            "id": message.reply_to_id,
            "participant": message.reply_to_sender_raw or message.reply_to_sender_id,
            "participant_raw": message.reply_to_sender_raw,
            "participant_canonical": message.reply_to_sender_id,
            "from_me": message.reply_to_from_me,
            "text": message.reply_to_text,
        },
    )


def _emit_message_change(message: Message, chat: ChatListItem | None = None) -> None:
    qml_events.emit_message_upsert([message])
    if chat is not None:
        qml_events.emit_chat_list_update([chat])


def _store_pending_message(message: Message) -> ChatListItem:
    storage_key = _message_storage_key(message.chat_id, message.timestamp_unix, message.id)
    with GreenlineKV() as kv:
        kv.put_record(storage_key, _message_storage_record(message))
        put_message_index(kv, message.chat_id, message.id, storage_key)
        kv.put_record(
            _pending_outbox_key(message.chat_id, message.id),
            PendingOutboxRecord(
                chat_id=message.chat_id,
                message_id=message.id,
                attempt_count=0,
                next_attempt_at=0,
            ),
        )

    return upsert_chat(message, MessageInfo())


def _begin_pending_send(chat_id: str, message_id: str) -> bool:
    token = _pending_send_token(chat_id, message_id)
    with _PENDING_SEND_LOCK:
        if token in _PENDING_SEND_IN_FLIGHT:
            return False
        _PENDING_SEND_IN_FLIGHT.add(token)
    return True


def _finish_pending_send(chat_id: str, message_id: str) -> None:
    with _PENDING_SEND_LOCK:
        _PENDING_SEND_IN_FLIGHT.discard(_pending_send_token(chat_id, message_id))


def _clear_pending_outbox_entry(chat_id: str, message_id: str) -> None:
    with GreenlineKV() as kv:
        kv.delete(_pending_outbox_key(chat_id, message_id))


def _schedule_pending_retry(chat_id: str, message_id: str) -> None:
    key = _pending_outbox_key(chat_id, message_id)
    with GreenlineKV() as kv:
        existing = kv.get_record(key, default=PendingOutboxRecord(chat_id, message_id, 0, 0))
        attempt_count = existing.attempt_count + 1
        delay_seconds = min(
            PENDING_RETRY_MAX_BACKOFF_SECONDS,
            PENDING_RETRY_INTERVAL_SECONDS * (2 ** min(attempt_count - 1, 5)),
        )
        kv.put_record(
            key,
            PendingOutboxRecord(
                chat_id=chat_id,
                message_id=message_id,
                attempt_count=attempt_count,
                next_attempt_at=int(time.time()) + delay_seconds,
            ),
        )


def _mark_pending_message_failed(entry_key: str, entry: StoredMessageRecord) -> None:
    failed_message = message_from_record(entry)
    failed_message.send_status = "failed"
    failed_message.read_receipt = ReadReceipt.NONE

    with GreenlineKV() as kv:
        kv.put_record(entry_key, _message_storage_record(failed_message))
        kv.delete(_pending_outbox_key(failed_message.chat_id, failed_message.id))

    chat = upsert_chat(failed_message, MessageInfo())
    _emit_message_change(failed_message, chat)


def _send_pending_message_via_rpc(
    message: Message,
    resolve_reply_context: ReplyContextResolver,
) -> SendMessageReply:
    reply_context = _pending_reply_context(message, resolve_reply_context)
    rpc = daemon_client()

    if message.type == MessageType.TEXT:
        transport_text, _, mentioned_jids = mention_transport_payload(message.text, message.mention_spans)
        return rpc.send_message(
            message.chat_id,
            "text",
            text=transport_text,
            reply_context=reply_context,
            mentioned_jids=mentioned_jids,
        )

    file_path = _local_media_path(message.media_path)
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(file_path or "Missing cached outgoing media")

    if message.type == MessageType.IMAGE:
        return rpc.send_message(
            message.chat_id,
            "image",
            file_path=file_path,
            caption=message.caption,
            reply_context=reply_context,
        )

    if message.type == MessageType.VIDEO:
        return rpc.send_message(
            message.chat_id,
            "video",
            file_path=file_path,
            caption=message.caption,
            reply_context=reply_context,
        )

    if message.type == MessageType.DOCUMENT:
        return rpc.send_message(
            message.chat_id,
            "document",
            file_path=file_path,
            file_name=message.file_name,
            caption=message.caption,
            reply_context=reply_context,
        )

    if message.type == MessageType.AUDIO:
        return rpc.send_message(
            message.chat_id,
            "audio",
            file_path=file_path,
            reply_context=reply_context,
            duration_seconds=_parse_duration_seconds(message.duration),
            ptt=True,
        )

    if message.type == MessageType.STICKER:
        return rpc.send_message(
            message.chat_id,
            "sticker",
            file_path=file_path,
            reply_context=reply_context,
        )

    if message.type == MessageType.CONTACT:
        return rpc.send_message(
            message.chat_id,
            "contact",
            text=message.file_name,
            file_path=file_path,
            reply_context=reply_context,
        )

    raise UnsupportedPendingMessageTypeError(f"Unsupported pending message type: {message.type}")


def _complete_pending_send(entry_key: str, pending_message: Message, result: SendMessageReply) -> None:
    timestamp_unix = int(result.Timestamp)
    sent_message = replace(
        pending_message,
        id=str(result.MessageID),
        timestamp=datetime.fromtimestamp(timestamp_unix).strftime("%H:%M"),
        timestamp_unix=timestamp_unix,
        read_receipt=ReadReceipt.SENT,
        send_status="",
        temp_id=pending_message.id,
    )

    sent_storage_key = _message_storage_key(sent_message.chat_id, sent_message.timestamp_unix, sent_message.id)
    with GreenlineKV() as kv:
        kv.delete(entry_key)
        delete_message_index(kv, pending_message.chat_id, pending_message.id)
        kv.delete(_pending_outbox_key(pending_message.chat_id, pending_message.id))
        kv.put_record(sent_storage_key, _message_storage_record(sent_message))
        put_message_index(kv, sent_message.chat_id, sent_message.id, sent_storage_key)

    chat = upsert_chat(sent_message, MessageInfo())
    _emit_message_change(sent_message, chat)


def _attempt_pending_send(
    chat_id: str,
    message_id: str,
    resolve_reply_context: ReplyContextResolver,
) -> bool:
    if not _begin_pending_send(chat_id, message_id):
        return False

    try:
        entry_key, entry = _get_message_entry_with_key(chat_id, message_id)
        if entry_key is None or entry is None:
            _clear_pending_outbox_entry(chat_id, message_id)
            return False

        if entry.send_status != "pending":
            _clear_pending_outbox_entry(chat_id, message_id)
            return False

        pending_message = message_from_record(entry)
        try:
            result = _send_pending_message_via_rpc(pending_message, resolve_reply_context)
        except (FileNotFoundError, UnsupportedPendingMessageTypeError):
            _mark_pending_message_failed(entry_key, entry)
            return False
        except Exception:
            _schedule_pending_retry(chat_id, message_id)
            return False

        _complete_pending_send(entry_key, pending_message, result)
        return True
    finally:
        _finish_pending_send(chat_id, message_id)


def queue_and_attempt_send(message: Message, resolve_reply_context: ReplyContextResolver) -> None:
    chat = _store_pending_message(message)
    _emit_message_change(message, chat)
    _attempt_pending_send(message.chat_id, message.id, resolve_reply_context)


class PendingMessageRetryEvent(Event):
    def __init__(self, resolve_reply_context: ReplyContextResolver) -> None:
        super().__init__(
            id="pending-message-retry",
            execution_interval=timedelta(seconds=PENDING_RETRY_INTERVAL_SECONDS),
        )
        self._resolve_reply_context = resolve_reply_context

    def trigger(self, metadata: dict[str, object] | None) -> None:
        with GreenlineKV() as kv:
            pending_entries = kv.get_partial_records(PENDING_OUTBOX_KEY_PREFIX)

        now = int(time.time())
        for key, value in pending_entries:
            chat_id = value.chat_id
            message_id = value.message_id
            if not chat_id or not message_id:
                with GreenlineKV() as kv:
                    kv.delete(key)
                continue
            if value.next_attempt_at > now:
                continue
            _attempt_pending_send(chat_id, message_id, self._resolve_reply_context)
