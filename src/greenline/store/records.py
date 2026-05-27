from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from greenline.contracts.codecs import to_json_like
from models import Message


@dataclass
class StoredMessageRecord(Message):
    raw: dict[str, Any] | None = None


@dataclass
class PendingOutboxRecord:
    chat_id: str
    message_id: str
    attempt_count: int
    next_attempt_at: int


@dataclass
class UnhandledMessageRecord:
    event_id: int
    info_type: str
    media_type: str
    chat: str
    sender: str
    message_id: str
    timestamp: str
    payload: str


@dataclass
class UnknownEventRecord:
    event_type: str
    payload: str


@dataclass
class MentionSpanRecord:
    jid: str
    label: str
    start: int
    length: int


@dataclass
class DraftMentionsRecord:
    value: list[MentionSpanRecord]


@dataclass
class MessageIndexRecord:
    value: str


@dataclass
class DaemonLastEventIDRecord:
    value: int


@dataclass
class UnreadTotalRecord:
    value: int


@dataclass
class DraftRecord:
    value: str


@dataclass
class NotificationsSuppressedRecord:
    value: bool


@dataclass
class LidMapRecord:
    value: str


@dataclass
class StickerCacheRecord:
    value: str


def stored_message_record(message: Message, raw: dict[str, Any] | None = None) -> StoredMessageRecord:
    payload = asdict(message)
    if raw is not None:
        payload["raw"] = raw
    return StoredMessageRecord(**payload)


def message_from_record(record: StoredMessageRecord) -> Message:
    payload = asdict(record)
    payload.pop("raw", None)
    return Message(**payload)


def record_payload_without_none(record: Any) -> dict[str, Any]:
    if not (is_dataclass(record) and not isinstance(record, type)):
        raise TypeError(f"expected dataclass instance, got {type(record).__name__}")
    payload = to_json_like(asdict(record))
    return {key: value for key, value in payload.items() if value is not None}
