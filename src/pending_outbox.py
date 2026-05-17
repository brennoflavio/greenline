import os
import threading
import time
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from typing import Callable

from message_store import (
    delete_message_index,
)
from message_store import get_message_entry_with_key as _lookup_message_entry_with_key
from message_store import message_storage_key as _message_storage_key
from message_store import (
    put_message_index,
    render_chat_mentions,
    to_ui_message,
    upsert_chat,
)
from models import ChatListItem, Message, MessageType, ReadReceipt
from rpc import DaemonRPC
from ut_components.event import Event
from ut_components.kv import KV
from ut_components.utils import enum_to_str as _enum_to_str
from whatsmeow_types import MessageInfo

PENDING_RETRY_INTERVAL_SECONDS = 5
PENDING_RETRY_MAX_BACKOFF_SECONDS = 300
PENDING_OUTBOX_KEY_PREFIX = "pending-outbox:"
_PENDING_SEND_LOCK = threading.Lock()
_PENDING_SEND_IN_FLIGHT: set[str] = set()

ReplyContextResolver = Callable[[str, dict[str, object] | None], dict[str, object] | None]


def _ui_message_dict(message: Message) -> dict[str, object]:
    return _enum_to_str(asdict(to_ui_message(message)))  # type: ignore[no-untyped-call, no-any-return]


def _ui_chat_dict(chat: ChatListItem) -> dict[str, object]:
    return _enum_to_str(asdict(render_chat_mentions(chat)))  # type: ignore[no-untyped-call, no-any-return]


def _pending_outbox_key(chat_id: str, message_id: str) -> str:
    return f"{PENDING_OUTBOX_KEY_PREFIX}{chat_id}:{message_id}"


def _pending_send_token(chat_id: str, message_id: str) -> str:
    return f"{chat_id}:{message_id}"


def _get_message_entry_with_key(chat_id: str, message_id: str) -> tuple[str, dict[str, object]] | tuple[None, None]:
    with KV() as kv:
        return _lookup_message_entry_with_key(kv, chat_id, message_id)


def _message_from_entry(entry: dict[str, object]) -> Message:
    msg_fields = {f.name for f in Message.__dataclass_fields__.values()}
    return Message(**{k: v for k, v in entry.items() if k in msg_fields})  # type: ignore[arg-type]


def _local_media_path(media_path: str) -> str:
    if media_path.startswith("file://"):
        return media_path[7:]
    return media_path


def _message_storage_payload(message: Message) -> dict[str, object]:
    data = asdict(message)

    if message.type == MessageType.CONTACT and message.media_path:
        contact_path = _local_media_path(message.media_path)
        if contact_path and os.path.exists(contact_path):
            try:
                with open(contact_path, encoding="utf-8-sig") as f:
                    vcard = f.read()
                data["raw"] = {
                    "Message": {
                        "contactMessage": {
                            "displayName": message.file_name or "Contact",
                            "vcard": vcard,
                        }
                    }
                }
            except Exception:
                pass

    return data


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
    import pyotherside

    pyotherside.send("message-upsert", [_ui_message_dict(message)])
    if chat is not None:
        pyotherside.send("chat-list-update", [_ui_chat_dict(chat)])


def _store_pending_message(message: Message) -> ChatListItem:
    storage_key = _message_storage_key(message.chat_id, message.timestamp_unix, message.id)
    with KV() as kv:
        kv.put(storage_key, _message_storage_payload(message))
        put_message_index(kv, message.chat_id, message.id, storage_key)
        kv.put(
            _pending_outbox_key(message.chat_id, message.id),
            {
                "chat_id": message.chat_id,
                "message_id": message.id,
                "attempt_count": 0,
                "next_attempt_at": 0,
            },
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
    with KV() as kv:
        kv.delete(_pending_outbox_key(chat_id, message_id))


def _schedule_pending_retry(chat_id: str, message_id: str) -> None:
    key = _pending_outbox_key(chat_id, message_id)
    with KV() as kv:
        existing = kv.get(key) or {}
        attempt_count = int(existing.get("attempt_count") or 0) + 1
        delay_seconds = min(
            PENDING_RETRY_MAX_BACKOFF_SECONDS,
            PENDING_RETRY_INTERVAL_SECONDS * (2 ** min(attempt_count - 1, 5)),
        )
        kv.put(
            key,
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "attempt_count": attempt_count,
                "next_attempt_at": int(time.time()) + delay_seconds,
            },
        )


def _mark_pending_message_failed(entry_key: str, entry: dict[str, object]) -> None:
    failed_message = _message_from_entry(entry)
    failed_message.send_status = "failed"
    failed_message.read_receipt = ReadReceipt.NONE

    with KV() as kv:
        kv.put(entry_key, _message_storage_payload(failed_message))
        kv.delete(_pending_outbox_key(failed_message.chat_id, failed_message.id))

    chat = upsert_chat(failed_message, MessageInfo())
    _emit_message_change(failed_message, chat)


def _send_pending_message_via_rpc(
    message: Message,
    resolve_reply_context: ReplyContextResolver,
) -> dict[str, object]:
    reply_context = _pending_reply_context(message, resolve_reply_context)
    rpc = DaemonRPC()

    if message.type == MessageType.TEXT:
        return rpc.send_message(message.chat_id, "text", text=message.text, reply_context=reply_context)

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
        return rpc.send_message(message.chat_id, "sticker", file_path=file_path, reply_context=reply_context)

    if message.type == MessageType.CONTACT:
        return rpc.send_message(
            message.chat_id,
            "contact",
            text=message.file_name,
            file_path=file_path,
            reply_context=reply_context,
        )

    raise ValueError(f"Unsupported pending message type: {message.type}")


def _complete_pending_send(entry_key: str, pending_message: Message, result: dict[str, object]) -> None:
    raw_timestamp = result.get("Timestamp")
    timestamp_unix = raw_timestamp if isinstance(raw_timestamp, int) else int(str(raw_timestamp or 0))
    sent_message = replace(
        pending_message,
        id=str(result["MessageID"]),
        timestamp=datetime.fromtimestamp(timestamp_unix).strftime("%H:%M"),
        timestamp_unix=timestamp_unix,
        read_receipt=ReadReceipt.SENT,
        send_status="",
        temp_id=pending_message.id,
    )

    sent_storage_key = _message_storage_key(sent_message.chat_id, sent_message.timestamp_unix, sent_message.id)
    with KV() as kv:
        kv.delete(entry_key)
        delete_message_index(kv, pending_message.chat_id, pending_message.id)
        kv.delete(_pending_outbox_key(pending_message.chat_id, pending_message.id))
        kv.put(sent_storage_key, _message_storage_payload(sent_message))
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

        if str(entry.get("send_status") or "") != "pending":
            _clear_pending_outbox_entry(chat_id, message_id)
            return False

        pending_message = _message_from_entry(entry)
        try:
            result = _send_pending_message_via_rpc(pending_message, resolve_reply_context)
        except (FileNotFoundError, ValueError):
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
            id="pending-message-retry", execution_interval=timedelta(seconds=PENDING_RETRY_INTERVAL_SECONDS)
        )
        self._resolve_reply_context = resolve_reply_context

    def trigger(self, metadata: dict[str, object] | None) -> None:
        with KV() as kv:
            pending_entries = kv.get_partial(PENDING_OUTBOX_KEY_PREFIX)

        now = int(time.time())
        for key, value in pending_entries:
            chat_id = str(value.get("chat_id") or "") if isinstance(value, dict) else ""
            message_id = str(value.get("message_id") or "") if isinstance(value, dict) else ""
            raw_next_attempt_at = value.get("next_attempt_at") if isinstance(value, dict) else 0
            next_attempt_at = raw_next_attempt_at if isinstance(raw_next_attempt_at, int) else 0
            if not chat_id or not message_id:
                with KV() as kv:
                    kv.delete(key)
                continue
            if next_attempt_at > now:
                continue
            _attempt_pending_send(chat_id, message_id, self._resolve_reply_context)
