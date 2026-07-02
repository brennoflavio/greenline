from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from typing import Any

from greenline.contracts.codecs import to_json_like
from models import MentionSpan, Message


@dataclass
class MediaDownloadRecord:
    media_type: str = ""
    direct_path: str = ""
    media_key: str = ""
    file_enc_sha256: str = ""
    file_sha256: str = ""
    file_length: int = 0
    mimetype: str = ""
    file_name: str = ""


@dataclass
class StoredMessageRecord(Message):
    media_download: MediaDownloadRecord = field(default_factory=MediaDownloadRecord)
    reply_quote_payload_json: str = ""
    raw: dict[str, Any] | None = None


@dataclass
class MessageReactionRecord:
    chat_id: str
    message_id: str
    sender_jid: str
    emoji: str


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
class DraftMentionsRecord:
    value: list[MentionSpan]


@dataclass
class GroupProfileMemberRecord:
    jid: str
    display_name: str = ""


@dataclass
class GroupProfileRecord:
    description: str = ""
    member_count: int = 0
    members: list[GroupProfileMemberRecord] = field(default_factory=list)


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
class ErrorReportingRecord:
    value: bool


@dataclass
class StopDaemonOnExitRecord:
    value: bool


@dataclass
class LidMapRecord:
    value: str


@dataclass
class StickerCacheRecord:
    value: str


@dataclass
class OwnJIDRecord:
    value: str


@dataclass
class KVSchemaVersionRecord:
    value: int


_MEDIA_DOWNLOAD_FIELDS = (
    ("image", "imageMessage"),
    ("video", "videoMessage"),
    ("audio", "audioMessage"),
    ("document", "documentMessage"),
    ("sticker", "stickerMessage"),
)


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _media_download_record(raw: dict[str, Any]) -> MediaDownloadRecord:
    from greenline.store.media import resolve_media_message_content

    raw_message = raw.get("Message")
    if not isinstance(raw_message, dict):
        return MediaDownloadRecord()

    for media_type, field_name in _MEDIA_DOWNLOAD_FIELDS:
        media = resolve_media_message_content(raw_message, field_name)
        if not isinstance(media, dict):
            continue
        return MediaDownloadRecord(
            media_type=media_type,
            direct_path=str(media.get("directPath") or ""),
            media_key=str(media.get("mediaKey") or ""),
            file_enc_sha256=str(media.get("fileEncSHA256") or ""),
            file_sha256=str(media.get("fileSHA256") or ""),
            file_length=_int_value(media.get("fileLength")),
            mimetype=str(media.get("mimetype") or ""),
            file_name=str(media.get("fileName") or ""),
        )
    return MediaDownloadRecord()


def _typed_mention_spans(value: Any) -> list[MentionSpan]:
    return [span if isinstance(span, MentionSpan) else MentionSpan(**span) for span in value]


def with_text_render_fields(message: Message) -> Message:
    from greenline.qml_text import TEXT_RENDER_MODE_RICH, build_text_render_data

    if message.mentioned_jids:
        return replace(
            message,
            rendered_text="",
            rendered_formatted_text="",
            text_render_mode=TEXT_RENDER_MODE_RICH,
        )

    render_data = build_text_render_data(message.text, message.mentioned_jids)
    return replace(
        message,
        rendered_text=render_data.plain_text,
        rendered_formatted_text=render_data.rich_text,
        text_render_mode=render_data.render_mode,
    )


def needs_text_render_backfill(record: StoredMessageRecord) -> bool:
    if not record.text or record.mentioned_jids:
        return False
    return record.rendered_text == "" or record.rendered_formatted_text == ""


def backfilled_stored_message_record(record: StoredMessageRecord) -> StoredMessageRecord:
    return updated_stored_message_record(record, message_from_record(record))


def stored_message_record(message: Message, raw: dict[str, Any] | None = None) -> StoredMessageRecord:
    payload = asdict(with_text_render_fields(message))
    payload["mention_spans"] = _typed_mention_spans(payload["mention_spans"])
    if raw is not None:
        raw_message = raw.get("Message")
        if isinstance(raw_message, dict):
            payload["reply_quote_payload_json"] = json.dumps(to_json_like(raw_message), separators=(",", ":"))
        payload["media_download"] = _media_download_record(raw)
        payload["raw"] = raw
    return StoredMessageRecord(**payload)


def updated_stored_message_record(record: StoredMessageRecord, message: Message) -> StoredMessageRecord:
    payload = asdict(with_text_render_fields(message))
    payload["mention_spans"] = _typed_mention_spans(payload["mention_spans"])
    payload["media_download"] = record.media_download
    payload["reply_quote_payload_json"] = record.reply_quote_payload_json
    payload["raw"] = record.raw
    return StoredMessageRecord(**payload)


def message_from_record(record: StoredMessageRecord) -> Message:
    payload = asdict(record)
    payload["mention_spans"] = _typed_mention_spans(payload["mention_spans"])
    payload.pop("media_download", None)
    payload.pop("reply_quote_payload_json", None)
    payload.pop("raw", None)
    return Message(**payload)


def is_history_sync_protocol_message(record: StoredMessageRecord, chat_id: str) -> bool:
    if not record.is_outgoing or not record.sender or record.sender != chat_id:
        return False

    raw = record.raw if isinstance(record.raw, dict) else None
    if raw is None:
        return False

    raw_message = raw.get("Message")
    if not isinstance(raw_message, dict):
        return False

    protocol_message = raw_message.get("protocolMessage")
    if not isinstance(protocol_message, dict):
        return False

    return protocol_message.get("type") == 5 and isinstance(protocol_message.get("historySyncNotification"), dict)


def record_payload_without_none(record: Any) -> dict[str, Any]:
    if not (is_dataclass(record) and not isinstance(record, type)):
        raise TypeError(f"expected dataclass instance, got {type(record).__name__}")
    payload = to_json_like(asdict(record))
    return {key: value for key, value in payload.items() if value is not None}
