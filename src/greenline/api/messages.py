import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from greenline import qml_events
from greenline.api.common import (
    SuccessResponse,
    ui_message,
)
from greenline.contracts.daemon import daemon_client
from greenline.contracts.kv import GreenlineKV
from greenline.store.mentions import validate_mention_spans
from greenline.store.messages import (
    _merge_deleted_message,
    _message_preview,
    _update_chat_after_edit,
)
from greenline.store.records import (
    StoredMessageRecord,
    message_from_record,
    updated_stored_message_record,
)
from greenline.store.repository import (
    get_message_entry_with_key as _lookup_message_entry_with_key,
)
from models import MentionSpan, Message, MessagesResponse, MessageType, ReadReceipt
from pending_outbox import queue_and_attempt_send
from unread_counter import decrement_unread_total, get_unread_total
from ut_components import mimetypes as mime_types
from ut_components.config import get_cache_path
from ut_components.crash import crash_reporter
from ut_components.utils import dataclass_to_dict
from whatsmeow_types import MessageInfo

EDIT_WINDOW_SECONDS = 20 * 60
_MEDIA_TYPE_MAP = {
    "image": "imageMessage",
    "video": "videoMessage",
    "audio": "audioMessage",
    "document": "documentMessage",
    "sticker": "stickerMessage",
}


@dataclass
class DownloadMediaResponse:
    success: bool
    media_path: str
    message: str


def _get_message_entry_with_key(chat_id: str, message_id: str) -> tuple[str, StoredMessageRecord] | tuple[None, None]:
    with GreenlineKV() as kv:
        return _lookup_message_entry_with_key(kv, chat_id, message_id)


def _get_message_entry(chat_id: str, message_id: str) -> StoredMessageRecord | None:
    _, entry = _get_message_entry_with_key(chat_id, message_id)
    return entry


def _is_local_only_message_entry(entry: StoredMessageRecord) -> bool:
    return (
        entry.id.startswith("pending-") or entry.id.startswith("failed-") or entry.send_status in ("pending", "failed")
    )


def _resolve_reply_context(chat_id: str, reply_context: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(reply_context, dict):
        return None

    reply_id = str(reply_context.get("id") or reply_context.get("reply_to_id") or "").strip()
    if not reply_id:
        return None

    participant_raw = str(
        reply_context.get("participant_raw")
        or reply_context.get("reply_participant_raw")
        or reply_context.get("participant")
        or reply_context.get("reply_participant")
        or ""
    )
    participant_canonical = str(
        reply_context.get("participant_canonical")
        or reply_context.get("reply_participant_canonical")
        or reply_context.get("reply_to_sender_id")
        or participant_raw
        or ""
    )
    resolved: dict[str, object] = {
        "id": reply_id,
        "text": str(reply_context.get("text") or reply_context.get("reply_to_text") or ""),
        "participant": participant_raw,
        "participant_raw": participant_raw,
        "participant_canonical": participant_canonical,
        "from_me": bool(reply_context.get("from_me")) or participant_raw == "",
    }

    entry = _get_message_entry(chat_id, reply_id)
    if entry is None:
        return resolved

    stored_msg = message_from_record(entry)
    rendered_msg = ui_message(stored_msg)

    resolved["from_me"] = stored_msg.is_outgoing
    if not stored_msg.is_outgoing and (stored_msg.sender_raw or stored_msg.sender):
        resolved["participant"] = stored_msg.sender_raw or stored_msg.sender
        resolved["participant_raw"] = stored_msg.sender_raw or stored_msg.sender
        resolved["participant_canonical"] = stored_msg.sender
    else:
        resolved["participant"] = ""
        resolved["participant_raw"] = ""
        resolved["participant_canonical"] = ""

    if entry.reply_quote_payload_json:
        resolved["quoted_message_json"] = entry.reply_quote_payload_json

    if stored_msg.type == MessageType.DELETED:
        resolved["text"] = _message_preview(rendered_msg)
    elif not resolved["text"]:
        resolved["text"] = _message_preview(rendered_msg)

    return resolved


def _resolve_message_reply_context(chat_id: str, entry: StoredMessageRecord) -> dict[str, object] | None:
    reply_id = entry.reply_to_id.strip()
    if not reply_id:
        return None

    return _resolve_reply_context(
        chat_id,
        {
            "reply_to_id": reply_id,
            "reply_participant": entry.reply_to_sender_raw or entry.reply_to_sender_id,
            "reply_participant_raw": entry.reply_to_sender_raw,
            "reply_participant_canonical": entry.reply_to_sender_id,
            "reply_to_text": entry.reply_to_text,
            "from_me": entry.reply_to_from_me,
        },
    )


def _apply_reply_context(message: Message, reply_context: dict[str, object] | None) -> None:
    if not reply_context:
        return

    message.reply_to_id = str(reply_context.get("id") or "")
    message.reply_to_sender_id = str(
        reply_context.get("participant_canonical") or reply_context.get("participant") or ""
    )
    message.reply_to_sender_raw = str(reply_context.get("participant_raw") or reply_context.get("participant") or "")
    message.reply_to_from_me = bool(reply_context.get("from_me"))
    message.reply_to_text = str(reply_context.get("text") or "")


def _extract_contact_display_name(vcard: str, file_path: str) -> str:
    unfolded_lines: list[str] = []
    for raw_line in vcard.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if (raw_line.startswith(" ") or raw_line.startswith("\t")) and unfolded_lines:
            unfolded_lines[-1] += raw_line[1:]
        else:
            unfolded_lines.append(raw_line)

    for line in unfolded_lines:
        key, separator, value = line.partition(":")
        if separator and key.split(";", 1)[0].upper() == "FN":
            name = value.strip()
            if name:
                return name

    fallback = os.path.splitext(os.path.basename(file_path))[0].strip()
    return fallback or "Contact"


def _guess_contact_extension(file_path: str) -> str:
    return (
        os.path.splitext(file_path)[1]
        or mime_types.guess_extension("text/x-vcard")  # type: ignore[no-untyped-call]
        or ".vcf"
    )


def _guess_contact_mimetype(file_path: str) -> str:
    guessed = mime_types.guess_type(file_path)[0]  # type: ignore[no-untyped-call]
    return guessed or "text/x-vcard"


def _format_duration(seconds: int) -> str:
    safe_seconds = max(0, int(seconds))
    return f"{safe_seconds // 60}:{safe_seconds % 60:02d}"


def _guess_audio_mimetype(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".ogg", ".oga", ".opus"}:
        return "audio/ogg; codecs=opus"

    guessed = mime_types.guess_type(file_path)[0]  # type: ignore[no-untyped-call]
    return guessed or "audio/ogg; codecs=opus"


@crash_reporter
@dataclass_to_dict
def get_messages(chat_id: str, cursor: str = "", page_size: int = 100) -> MessagesResponse:
    next_cursor = ""
    has_more = False
    cursor_value = cursor or None
    with GreenlineKV() as kv:
        page_entries, _ = kv.get_partial_page_records(
            f"message:{chat_id}:",
            page_size=page_size + 1,
            cursor=cursor_value,
            reverse=True,
        )
        has_more = len(page_entries) > page_size
        entries = page_entries[:page_size]
        if has_more and entries:
            next_cursor = entries[-1][0]

        messages = [message_from_record(value) for _, value in entries]
        messages.sort(key=lambda message: (message.timestamp_unix, message.id))
        rendered_messages = [ui_message(message) for message in messages]

    return MessagesResponse(
        success=True,
        messages=rendered_messages,
        message="",
        next_cursor=next_cursor,
        has_more=has_more,
    )


@crash_reporter
@dataclass_to_dict
def mark_messages_as_read(chat_id: str) -> SuccessResponse:
    with GreenlineKV() as kv:
        entries = kv.get_partial_records(f"message:{chat_id}:")
        unread_by_sender: dict[str, list[str]] = {}
        for _key, value in entries:
            if value.is_outgoing or value.read_receipt == ReadReceipt.READ:
                continue
            sender = value.sender_raw or value.sender
            unread_by_sender.setdefault(sender, []).append(value.id)

    rpc = daemon_client()
    for sender, ids in unread_by_sender.items():
        rpc.mark_read(chat_id, ids, sender_jid=sender)

    with GreenlineKV() as kv:
        chat = kv.get_record(f"chat:{chat_id}")
        if chat is not None:
            prev_unread = chat.unread_count
            if prev_unread > 0:
                chat.unread_count = 0
                kv.put_record(f"chat:{chat_id}", chat)
                qml_events.emit_chat_list_update([chat])
                decrement_unread_total(prev_unread)

    try:
        rpc.clear_chat_notifications([chat_id])
    except Exception:
        pass

    try:
        total = get_unread_total()
        rpc.set_notification_counter(total, total > 0)
    except Exception:
        pass

    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def send_text_message(
    chat_id: str,
    text: str,
    temp_id: str = "",
    reply_context: dict[str, object] | None = None,
    mention_spans: Sequence[MentionSpan | Mapping[str, object]] | None = None,
) -> SuccessResponse:
    resolved_reply_context = _resolve_reply_context(chat_id, reply_context)
    normalized_text = str(text)
    validated_spans = validate_mention_spans(normalized_text, mention_spans)
    now = datetime.now()
    pending_id = temp_id or f"pending-{int(now.timestamp())}"

    pending_msg = Message(
        id=pending_id,
        chat_id=chat_id,
        type=MessageType.TEXT,
        is_outgoing=True,
        timestamp=now.strftime("%H:%M"),
        timestamp_unix=int(now.timestamp()),
        read_receipt=ReadReceipt.NONE,
        text=normalized_text,
        mentioned_jids=[span.jid for span in validated_spans],
        mention_spans=validated_spans,
        send_status="pending",
        temp_id=pending_id,
    )
    _apply_reply_context(pending_msg, resolved_reply_context)
    queue_and_attempt_send(pending_msg, _resolve_reply_context)
    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def edit_text_message(chat_id: str, message_id: str, text: str) -> SuccessResponse:
    normalized_text = str(text)
    if normalized_text.strip() == "":
        return SuccessResponse(success=False, message="Message text cannot be empty")

    entry_key, entry = _get_message_entry_with_key(chat_id, message_id)
    if entry_key is None or entry is None:
        return SuccessResponse(success=False, message="Message not found")

    if not entry.is_outgoing:
        return SuccessResponse(success=False, message="Only sent messages can be edited")

    if _is_local_only_message_entry(entry):
        return SuccessResponse(success=False, message="Message has not been sent yet")

    if entry.type != MessageType.TEXT:
        return SuccessResponse(success=False, message="Only text messages can be edited")

    if entry.mentioned_jids or entry.mention_spans:
        return SuccessResponse(success=False, message="Mention messages cannot be edited yet")

    timestamp_unix = entry.timestamp_unix
    if timestamp_unix <= 0 or int(time.time()) - timestamp_unix > EDIT_WINDOW_SECONDS:
        return SuccessResponse(success=False, message="Message can no longer be edited")

    reply_context = _resolve_message_reply_context(chat_id, entry)

    try:
        rpc = daemon_client()
        rpc.edit_message(chat_id, message_id, normalized_text, reply_context=reply_context)
    except Exception as error:
        return SuccessResponse(success=False, message=str(error))

    updated_msg = message_from_record(entry)
    updated_msg.text = normalized_text
    updated_msg.edited = True

    with GreenlineKV() as kv:
        kv.put_record(entry_key, updated_stored_message_record(entry, updated_msg))
        chat = _update_chat_after_edit(kv, updated_msg, MessageInfo())

    qml_events.emit_message_upsert([updated_msg])
    qml_events.emit_chat_list_update([chat])
    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def delete_message(chat_id: str, message_id: str) -> SuccessResponse:
    entry_key, entry = _get_message_entry_with_key(chat_id, message_id)
    if entry_key is None or entry is None:
        return SuccessResponse(success=False, message="Message not found")

    if not entry.is_outgoing:
        return SuccessResponse(success=False, message="Only sent messages can be deleted")

    if _is_local_only_message_entry(entry):
        return SuccessResponse(success=False, message="Message has not been sent yet")

    if entry.type == MessageType.DELETED:
        return SuccessResponse(success=False, message="Message already deleted")

    try:
        daemon_client().delete_message(chat_id, message_id)
    except Exception as error:
        return SuccessResponse(success=False, message=str(error))

    existing_msg = message_from_record(entry)
    deleted_msg = _merge_deleted_message(existing_msg, existing_msg.sender)

    with GreenlineKV() as kv:
        kv.put_record(entry_key, updated_stored_message_record(entry, deleted_msg))
        chat = _update_chat_after_edit(kv, deleted_msg, MessageInfo())

    qml_events.emit_message_upsert([deleted_msg])
    qml_events.emit_chat_list_update([chat])
    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def send_image_message(
    chat_id: str,
    file_path: str,
    caption: str = "",
    temp_id: str = "",
    reply_context: dict[str, object] | None = None,
) -> SuccessResponse:
    resolved_reply_context = _resolve_reply_context(chat_id, reply_context)

    cache_dir = os.path.join(get_cache_path(), "outgoing")
    os.makedirs(cache_dir, exist_ok=True)
    ext = os.path.splitext(file_path)[1] or ".jpg"
    cached_path = os.path.join(cache_dir, f"{temp_id or int(datetime.now().timestamp())}{ext}")
    shutil.copy2(file_path, cached_path)

    now = datetime.now()
    pending_id = temp_id or f"pending-{int(now.timestamp())}"
    pending_msg = Message(
        id=pending_id,
        chat_id=chat_id,
        type=MessageType.IMAGE,
        is_outgoing=True,
        timestamp=now.strftime("%H:%M"),
        timestamp_unix=int(now.timestamp()),
        read_receipt=ReadReceipt.NONE,
        caption=caption,
        media_path="file://" + cached_path,
        send_status="pending",
        temp_id=pending_id,
    )
    _apply_reply_context(pending_msg, resolved_reply_context)
    queue_and_attempt_send(pending_msg, _resolve_reply_context)
    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def send_video_message(
    chat_id: str,
    file_path: str,
    caption: str = "",
    temp_id: str = "",
    reply_context: dict[str, object] | None = None,
) -> SuccessResponse:
    resolved_reply_context = _resolve_reply_context(chat_id, reply_context)

    cache_dir = os.path.join(get_cache_path(), "outgoing")
    os.makedirs(cache_dir, exist_ok=True)
    ext = os.path.splitext(file_path)[1] or ".mp4"
    cached_path = os.path.join(cache_dir, f"{temp_id or int(datetime.now().timestamp())}{ext}")
    shutil.copy2(file_path, cached_path)

    now = datetime.now()
    pending_id = temp_id or f"pending-{int(now.timestamp())}"
    pending_msg = Message(
        id=pending_id,
        chat_id=chat_id,
        type=MessageType.VIDEO,
        is_outgoing=True,
        timestamp=now.strftime("%H:%M"),
        timestamp_unix=int(now.timestamp()),
        read_receipt=ReadReceipt.NONE,
        caption=caption,
        media_path="file://" + cached_path,
        send_status="pending",
        temp_id=pending_id,
    )
    _apply_reply_context(pending_msg, resolved_reply_context)
    queue_and_attempt_send(pending_msg, _resolve_reply_context)
    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def send_audio_message(
    chat_id: str,
    file_path: str,
    duration_seconds: int = 0,
    temp_id: str = "",
    reply_context: dict[str, object] | None = None,
) -> SuccessResponse:
    resolved_reply_context = _resolve_reply_context(chat_id, reply_context)
    duration_value = max(0, int(duration_seconds))
    duration = _format_duration(duration_value)
    now = datetime.now()

    cache_dir = os.path.join(get_cache_path(), "outgoing")
    os.makedirs(cache_dir, exist_ok=True)
    ext = os.path.splitext(file_path)[1] or ".ogg"
    cached_path = os.path.join(cache_dir, f"{temp_id or int(now.timestamp())}{ext}")

    try:
        if os.path.abspath(file_path) != os.path.abspath(cached_path):
            shutil.move(file_path, cached_path)
    except Exception as error:
        failed_id = temp_id or f"failed-{int(now.timestamp())}"
        failed_msg = Message(
            id=failed_id,
            chat_id=chat_id,
            type=MessageType.AUDIO,
            is_outgoing=True,
            timestamp=now.strftime("%H:%M"),
            timestamp_unix=int(now.timestamp()),
            read_receipt=ReadReceipt.NONE,
            duration=duration,
            media_path="file://" + file_path,
            mimetype=_guess_audio_mimetype(file_path),
            send_status="failed",
            temp_id=failed_id,
        )
        _apply_reply_context(failed_msg, resolved_reply_context)
        qml_events.emit_message_upsert([failed_msg])
        return SuccessResponse(success=False, message=str(error) or "Failed to prepare audio")

    pending_id = temp_id or f"pending-{int(now.timestamp())}"
    pending_msg = Message(
        id=pending_id,
        chat_id=chat_id,
        type=MessageType.AUDIO,
        is_outgoing=True,
        timestamp=now.strftime("%H:%M"),
        timestamp_unix=int(now.timestamp()),
        read_receipt=ReadReceipt.NONE,
        duration=duration,
        media_path="file://" + cached_path,
        mimetype=_guess_audio_mimetype(cached_path),
        send_status="pending",
        temp_id=pending_id,
    )
    _apply_reply_context(pending_msg, resolved_reply_context)
    queue_and_attempt_send(pending_msg, _resolve_reply_context)
    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def send_sticker_message(
    chat_id: str,
    file_path: str,
    temp_id: str = "",
    reply_context: dict[str, object] | None = None,
) -> SuccessResponse:
    resolved_reply_context = _resolve_reply_context(chat_id, reply_context)

    cache_dir = os.path.join(get_cache_path(), "outgoing")
    os.makedirs(cache_dir, exist_ok=True)
    ext = os.path.splitext(file_path)[1] or ".webp"
    cached_path = os.path.join(cache_dir, f"{temp_id or int(datetime.now().timestamp())}{ext}")
    shutil.copy2(file_path, cached_path)

    now = datetime.now()
    pending_id = temp_id or f"pending-{int(now.timestamp())}"
    pending_msg = Message(
        id=pending_id,
        chat_id=chat_id,
        type=MessageType.STICKER,
        is_outgoing=True,
        timestamp=now.strftime("%H:%M"),
        timestamp_unix=int(now.timestamp()),
        read_receipt=ReadReceipt.NONE,
        media_path="file://" + cached_path,
        send_status="pending",
        temp_id=pending_id,
    )
    _apply_reply_context(pending_msg, resolved_reply_context)
    queue_and_attempt_send(pending_msg, _resolve_reply_context)
    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def send_contact_message(
    chat_id: str,
    file_path: str,
    temp_id: str = "",
    reply_context: dict[str, object] | None = None,
) -> SuccessResponse:
    resolved_reply_context = _resolve_reply_context(chat_id, reply_context)

    with open(file_path, encoding="utf-8-sig") as file_handle:
        vcard = file_handle.read()

    cache_dir = os.path.join(get_cache_path(), "outgoing")
    os.makedirs(cache_dir, exist_ok=True)
    ext = _guess_contact_extension(file_path)
    cached_path = os.path.join(cache_dir, f"{temp_id or int(datetime.now().timestamp())}{ext}")
    shutil.copy2(file_path, cached_path)

    now = datetime.now()
    pending_id = temp_id or f"pending-{int(now.timestamp())}"
    pending_msg = Message(
        id=pending_id,
        chat_id=chat_id,
        type=MessageType.CONTACT,
        is_outgoing=True,
        timestamp=now.strftime("%H:%M"),
        timestamp_unix=int(now.timestamp()),
        read_receipt=ReadReceipt.NONE,
        media_path="file://" + cached_path,
        mimetype=_guess_contact_mimetype(cached_path),
        file_name=_extract_contact_display_name(vcard, file_path),
        send_status="pending",
        temp_id=pending_id,
    )
    _apply_reply_context(pending_msg, resolved_reply_context)
    queue_and_attempt_send(pending_msg, _resolve_reply_context)
    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def get_cached_stickers() -> dict[str, object]:
    with GreenlineKV() as kv:
        entries = kv.get_partial_records("sticker_cache:")
    stickers = []
    for _, record in entries:
        if record.value and os.path.exists(record.value):
            stickers.append("file://" + record.value)
    return {"success": True, "stickers": stickers}


@crash_reporter
@dataclass_to_dict
def download_media(chat_id: str, message_id: str, media_type: str) -> DownloadMediaResponse:
    entry_key, entry = _get_message_entry_with_key(chat_id, message_id)
    if entry_key is None or entry is None:
        return DownloadMediaResponse(success=False, media_path="", message="Message not found")

    if media_type not in _MEDIA_TYPE_MAP:
        return DownloadMediaResponse(success=False, media_path="", message=f"Unknown media type: {media_type}")

    media = entry.media_download
    if media.media_type != media_type:
        return DownloadMediaResponse(success=False, media_path="", message="No media content in message")

    if not media.direct_path or not media.media_key:
        return DownloadMediaResponse(success=False, media_path="", message="Missing media download info")

    try:
        file_path = (
            daemon_client()
            .download_media(
                direct_path=media.direct_path,
                media_key=media.media_key,
                file_enc_sha256=media.file_enc_sha256,
                file_sha256=media.file_sha256,
                file_length=media.file_length,
                media_type=media_type,
                mimetype=media.mimetype,
                message_id=message_id,
                chat_id=chat_id,
                file_name=media.file_name,
            )
            .FilePath
        )
    except Exception as error:
        return DownloadMediaResponse(success=False, media_path="", message=str(error))

    if not file_path:
        return DownloadMediaResponse(success=False, media_path="", message="Failed to download media")

    media_path = "file://" + file_path
    msg = message_from_record(entry)
    msg.media_path = media_path
    with GreenlineKV() as kv:
        kv.put_record(entry_key, updated_stored_message_record(entry, msg))
    qml_events.emit_message_upsert([msg])
    return DownloadMediaResponse(success=True, media_path=media_path, message="")
