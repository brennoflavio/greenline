import os
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, cast

from greenline import qml_events
from greenline.api.common import (
    SuccessResponse,
    ui_message,
)
from greenline.store.media import resolve_media_message_content
from greenline.store.mentions import validate_mention_spans
from greenline.store.messages import (
    _merge_deleted_message,
    _message_preview,
    _update_chat_after_edit,
)
from greenline.store.repository import (
    get_message_entry_with_key as _lookup_message_entry_with_key,
)
from greenline.store.repository import (
    sanitize_message_payload,
)
from models import ChatListItem, Message, MessagesResponse, MessageType, ReadReceipt
from pending_outbox import queue_and_attempt_send
from rpc import DaemonRPC
from unread_counter import decrement_unread_total, get_unread_total
from ut_components import mimetypes as mime_types
from ut_components.config import get_cache_path
from ut_components.crash import crash_reporter
from ut_components.kv import KV
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


def _get_message_entry_with_key(chat_id: str, message_id: str) -> tuple[str, dict[str, object]] | tuple[None, None]:
    with KV() as kv:
        return _lookup_message_entry_with_key(kv, chat_id, message_id)


def _get_message_entry(chat_id: str, message_id: str) -> dict[str, object] | None:
    _, entry = _get_message_entry_with_key(chat_id, message_id)
    return entry


def _is_local_only_message_entry(entry: dict[str, object]) -> bool:
    message_id = str(entry.get("id") or "")
    send_status = str(entry.get("send_status") or "")
    return message_id.startswith("pending-") or message_id.startswith("failed-") or send_status in ("pending", "failed")


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

    msg_fields = {field.name for field in Message.__dataclass_fields__.values()}
    stored_msg = Message(**{key: value for key, value in entry.items() if key in msg_fields})  # type: ignore[arg-type]
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

    raw = entry.get("raw")
    quoted_message = raw.get("Message") if isinstance(raw, dict) else None
    if isinstance(quoted_message, dict):
        resolved["quoted_message"] = quoted_message

    if stored_msg.type == MessageType.DELETED:
        resolved["text"] = _message_preview(rendered_msg)
    elif not resolved["text"]:
        resolved["text"] = _message_preview(rendered_msg)

    return resolved


def _resolve_message_reply_context(chat_id: str, entry: dict[str, object]) -> dict[str, object] | None:
    reply_id = str(entry.get("reply_to_id") or "").strip()
    if not reply_id:
        return None

    return _resolve_reply_context(
        chat_id,
        {
            "reply_to_id": reply_id,
            "reply_participant": str(entry.get("reply_to_sender_raw") or entry.get("reply_to_sender_id") or ""),
            "reply_participant_raw": str(entry.get("reply_to_sender_raw") or ""),
            "reply_participant_canonical": str(entry.get("reply_to_sender_id") or ""),
            "reply_to_text": str(entry.get("reply_to_text") or ""),
            "from_me": bool(entry.get("reply_to_from_me")),
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
    with KV() as kv:
        page_entries, _ = kv.get_partial_page(
            f"message:{chat_id}:",
            page_size=page_size + 1,
            cursor=cursor_value,
            reverse=True,
        )
        has_more = len(page_entries) > page_size
        entries = page_entries[:page_size]
        if has_more and entries:
            next_cursor = entries[-1][0]

        msg_fields = {field.name for field in Message.__dataclass_fields__.values()}
        messages = [
            Message(**{key: value for key, value in value.items() if key in msg_fields}) for _, value in entries
        ]
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
    with KV() as kv:
        entries = kv.get_partial(f"message:{chat_id}:")
        unread_by_sender: dict[str, list[str]] = {}
        for _key, value in entries:
            if value.get("is_outgoing") or value.get("read_receipt") == ReadReceipt.READ:
                continue
            sender = str(value.get("sender_raw") or value.get("sender") or "")
            unread_by_sender.setdefault(sender, []).append(value["id"])

    rpc = DaemonRPC()
    for sender, ids in unread_by_sender.items():
        rpc.mark_read(chat_id, ids, sender_jid=sender)

    with KV() as kv:
        existing = kv.get(f"chat:{chat_id}")
        if existing:
            chat = ChatListItem(**existing)
            prev_unread = chat.unread_count
            if prev_unread > 0:
                chat.unread_count = 0
                kv.put(f"chat:{chat_id}", asdict(chat))
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
    mention_spans: list[dict[str, object]] | None = None,
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
        mentioned_jids=[str(span["jid"]) for span in validated_spans],
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

    if not entry.get("is_outgoing"):
        return SuccessResponse(success=False, message="Only sent messages can be edited")

    if _is_local_only_message_entry(entry):
        return SuccessResponse(success=False, message="Message has not been sent yet")

    if str(entry.get("type") or "") != MessageType.TEXT.value:
        return SuccessResponse(success=False, message="Only text messages can be edited")

    mentioned_jids = entry.get("mentioned_jids") if isinstance(entry.get("mentioned_jids"), list) else []
    mention_spans = entry.get("mention_spans") if isinstance(entry.get("mention_spans"), list) else []
    if mentioned_jids or mention_spans:
        return SuccessResponse(success=False, message="Mention messages cannot be edited yet")

    raw_timestamp_unix = entry.get("timestamp_unix")
    timestamp_unix = raw_timestamp_unix if isinstance(raw_timestamp_unix, int) else 0
    if timestamp_unix <= 0 or int(time.time()) - timestamp_unix > EDIT_WINDOW_SECONDS:
        return SuccessResponse(success=False, message="Message can no longer be edited")

    reply_context = _resolve_message_reply_context(chat_id, entry)

    try:
        rpc = DaemonRPC()
        rpc.edit_message(chat_id, message_id, normalized_text, reply_context=reply_context)
    except Exception as error:
        return SuccessResponse(success=False, message=str(error))

    msg_fields = {field.name for field in Message.__dataclass_fields__.values()}
    updated_msg = Message(**{key: value for key, value in entry.items() if key in msg_fields})  # type: ignore[arg-type]
    updated_msg.text = normalized_text
    updated_msg.edited = True

    updated_entry = dict(entry)
    updated_entry.update(asdict(updated_msg))
    with KV() as kv:
        kv.put(entry_key, updated_entry)
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

    if not entry.get("is_outgoing"):
        return SuccessResponse(success=False, message="Only sent messages can be deleted")

    if _is_local_only_message_entry(entry):
        return SuccessResponse(success=False, message="Message has not been sent yet")

    if str(entry.get("type") or "") == MessageType.DELETED.value:
        return SuccessResponse(success=False, message="Message already deleted")

    try:
        DaemonRPC().delete_message(chat_id, message_id)
    except Exception as error:
        return SuccessResponse(success=False, message=str(error))

    msg_fields = {field.name for field in Message.__dataclass_fields__.values()}
    existing_msg = Message(**cast(Any, {key: value for key, value in entry.items() if key in msg_fields}))
    deleted_msg = _merge_deleted_message(existing_msg, existing_msg.sender)

    updated_entry = dict(entry)
    updated_entry.update(asdict(deleted_msg))
    with KV() as kv:
        kv.put(entry_key, updated_entry)
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
    with KV() as kv:
        entries = kv.get_partial("sticker_cache:")
    stickers = []
    for _, file_path in entries:
        if file_path and os.path.exists(str(file_path)):
            stickers.append("file://" + str(file_path))
    return {"success": True, "stickers": stickers}


@crash_reporter
@dataclass_to_dict
def download_media(chat_id: str, message_id: str, media_type: str) -> DownloadMediaResponse:
    entry_key, entry = _get_message_entry_with_key(chat_id, message_id)
    if entry_key is None or entry is None or entry.get("raw") is None:
        return DownloadMediaResponse(success=False, media_path="", message="Message not found")

    raw = entry["raw"]
    if not isinstance(raw, dict):
        return DownloadMediaResponse(success=False, media_path="", message="Message not found")

    msg_content = raw.get("Message", {})
    field_name = _MEDIA_TYPE_MAP.get(media_type)
    if not field_name:
        return DownloadMediaResponse(success=False, media_path="", message=f"Unknown media type: {media_type}")

    media_msg = resolve_media_message_content(msg_content, field_name)
    if not media_msg:
        return DownloadMediaResponse(success=False, media_path="", message="No media content in message")

    direct_path = media_msg.get("directPath", "")
    media_key = media_msg.get("mediaKey", "")
    file_enc_sha256 = media_msg.get("fileEncSHA256", "")
    file_sha256 = media_msg.get("fileSHA256", "")
    file_length = media_msg.get("fileLength", 0)
    mimetype = media_msg.get("mimetype", "")
    file_name = media_msg.get("fileName", "")

    if not direct_path or not media_key:
        return DownloadMediaResponse(success=False, media_path="", message="Missing media download info")

    try:
        file_path = DaemonRPC().download_media(
            direct_path=direct_path,
            media_key=media_key,
            file_enc_sha256=file_enc_sha256,
            file_sha256=file_sha256,
            file_length=file_length,
            media_type=media_type,
            mimetype=mimetype,
            message_id=message_id,
            chat_id=chat_id,
            file_name=file_name,
        )
    except Exception as error:
        return DownloadMediaResponse(success=False, media_path="", message=str(error))

    if not file_path:
        return DownloadMediaResponse(success=False, media_path="", message="Failed to download media")

    media_path = "file://" + file_path
    entry["media_path"] = media_path
    with KV() as kv:
        kv.put(entry_key, sanitize_message_payload(entry))

    msg_fields = {field.name for field in Message.__dataclass_fields__.values()}
    msg = Message(**{key: value for key, value in entry.items() if key in msg_fields})  # type: ignore[arg-type]
    qml_events.emit_message_upsert([msg])
    return DownloadMediaResponse(success=True, media_path=media_path, message="")
