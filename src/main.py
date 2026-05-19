"""
Copyright (C) 2025  Brenno Almeida

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; version 3.

greenline is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
 along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from constants import APP_NAME, CRASH_REPORT_URL
from ut_components import mimetypes as mime_types
from ut_components import setup

setup(APP_NAME, CRASH_REPORT_URL)

import base64
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime

from daemon import (
    ensure_daemon_version,
    install_background_service_files,
    is_daemon_active,
    is_daemon_installed,
    remove_background_service_files,
    run_subprocess,
)
from daemon_types import Contact as DaemonContact
from events import (
    LAST_EVENT_ID_KEY,
    QR_IMAGE_PATH,
    ChatListUpdateEvent,
    DaemonEventHandler,
    SessionStatusEvent,
    SessionStatusResponse,
)
from message_store import (
    _merge_deleted_message,
    _message_preview,
    _update_chat_after_edit,
    build_mention_candidate,
    canonicalize_contact_jid,
    clear_chat_runtime_cache,
)
from message_store import get_message_entry_with_key as _lookup_message_entry_with_key
from message_store import (
    render_chat_mentions,
    resolve_media_message_content,
    sanitize_message_payload,
    to_ui_message,
    validate_mention_spans,
)
from models import (
    ChatListEntry,
    ChatListItem,
    ChatListResponse,
    ContactItem,
    ContactListResponse,
    Message,
    MessagesResponse,
    MessageType,
    ReadReceipt,
    UiMessage,
)
from pending_outbox import PendingMessageRetryEvent, queue_and_attempt_send
from rpc import DaemonRPC
from unread_counter import decrement_unread_total, reconcile_unread_total
from ut_components.config import get_cache_path, get_config_path
from ut_components.crash import crash_reporter
from ut_components.event import get_event_dispatcher
from ut_components.kv import KV
from ut_components.utils import dataclass_to_dict
from ut_components.utils import enum_to_str as _enum_to_str
from whatsmeow_types import MessageInfo


@dataclass
class EnsureDaemonVersionResponse:
    restarted: bool


@crash_reporter
@dataclass_to_dict
def check_daemon_version() -> EnsureDaemonVersionResponse:
    restarted = ensure_daemon_version()
    return EnsureDaemonVersionResponse(restarted=restarted)


def get_sync_status() -> bool:
    try:
        with KV() as kv:
            last_id = kv.get(LAST_EVENT_ID_KEY, default=0)
        reply = DaemonRPC().list_events(after_id=last_id, limit=1)
        return bool(reply.Events)
    except Exception:
        return False


def start_event_loop() -> None:
    reconcile_unread_total()
    dispatcher = get_event_dispatcher()
    dispatcher.register_event(SessionStatusEvent())
    dispatcher.register_event(DaemonEventHandler())
    dispatcher.register_event(ChatListUpdateEvent())
    dispatcher.register_event(PendingMessageRetryEvent(_resolve_reply_context))
    dispatcher.start()


@dataclass
class SuccessResponse:
    success: bool
    message: str


EDIT_WINDOW_SECONDS = 20 * 60


@dataclass
class DaemonStatusResponse:
    installed: bool
    active: bool


@dataclass
class ClearDataResponse:
    success: bool


@dataclass
class ChatDraftResponse:
    success: bool
    text: str
    mention_spans: list[dict[str, object]] = field(default_factory=list)


@dataclass
class GroupMentionCandidatesResponse:
    success: bool
    candidates: list[dict[str, object]] = field(default_factory=list)
    message: str = ""


@crash_reporter
@dataclass_to_dict
def ping_daemon() -> SuccessResponse:
    try:
        result = DaemonRPC().ping()
        return SuccessResponse(success=True, message=result)
    except Exception as e:
        return SuccessResponse(success=False, message=str(e))


@crash_reporter
@dataclass_to_dict
def check_daemon_status() -> DaemonStatusResponse:
    installed = is_daemon_installed()
    if installed and not is_daemon_active():
        run_subprocess(["systemctl", "--user", "start", "greenline.service"])
        for _ in range(10):
            time.sleep(0.5)
            try:
                DaemonRPC().ping()
                break
            except Exception:
                continue
    return DaemonStatusResponse(
        installed=installed,
        active=is_daemon_active(),
    )


@crash_reporter
@dataclass_to_dict
def get_session_status() -> SessionStatusResponse:
    try:
        result = DaemonRPC().get_session_status()
        qr_image_path = ""

        if not result.LoggedIn and result.QRImage:
            os.makedirs(os.path.dirname(QR_IMAGE_PATH), exist_ok=True)
            with open(QR_IMAGE_PATH, "wb") as f:
                f.write(base64.b64decode(result.QRImage))
            qr_image_path = "file://" + QR_IMAGE_PATH

        return SessionStatusResponse(
            logged_in=result.LoggedIn,
            qr_image_path=qr_image_path,
        )
    except Exception:
        return SessionStatusResponse(logged_in=False, qr_image_path="")


@dataclass
class PairPhoneResponse:
    success: bool
    code: str
    message: str


@crash_reporter
@dataclass_to_dict
def pair_phone(phone_number: str) -> PairPhoneResponse:
    try:
        reply = DaemonRPC().pair_phone(phone_number)
        return PairPhoneResponse(success=True, code=reply.Code, message="")
    except Exception as e:
        return PairPhoneResponse(success=False, code="", message=str(e))


@crash_reporter
@dataclass_to_dict
def install_daemon() -> SuccessResponse:
    try:
        install_background_service_files()
        return SuccessResponse(success=True, message="Daemon installed.")
    except Exception as e:
        return SuccessResponse(success=False, message=str(e))


@crash_reporter
@dataclass_to_dict
def uninstall_daemon() -> SuccessResponse:
    try:
        remove_background_service_files()
        return SuccessResponse(success=True, message="Daemon uninstalled.")
    except Exception as e:
        return SuccessResponse(success=False, message=str(e))


def _build_contact_item(contact: DaemonContact) -> ContactItem:
    jid = canonicalize_contact_jid(contact.jid)
    photo = ""
    if contact.avatar_path:
        photo = "file://" + contact.avatar_path
    return ContactItem(
        jid=jid,
        display_name=contact.display_name or jid,
        first_name=contact.first_name,
        full_name=contact.full_name,
        push_name=contact.push_name,
        business_name=contact.business_name,
        photo=photo,
    )


@crash_reporter
@dataclass_to_dict
def get_contact_list() -> ContactListResponse:
    try:
        reply = DaemonRPC().get_contacts()
        contacts = [_build_contact_item(c) for c in reply.Contacts]
        return ContactListResponse(success=True, contacts=contacts, message="")
    except Exception as e:
        return ContactListResponse(success=False, contacts=[], message=str(e))


@dataclass
class SettingsResponse:
    success: bool
    notifications_suppressed: bool


@crash_reporter
@dataclass_to_dict
def get_settings() -> SettingsResponse:
    try:
        reply = DaemonRPC().get_notifications_suppressed()
        return SettingsResponse(success=True, notifications_suppressed=reply.Suppressed)
    except Exception:
        return SettingsResponse(success=False, notifications_suppressed=False)


@crash_reporter
@dataclass_to_dict
def set_notifications_suppressed(suppressed: bool) -> SuccessResponse:
    try:
        DaemonRPC().set_notifications_suppressed(suppressed)
        return SuccessResponse(success=True, message="")
    except Exception as e:
        return SuccessResponse(success=False, message=str(e))


@crash_reporter
@dataclass_to_dict
def clear_data() -> ClearDataResponse:
    dispatcher = get_event_dispatcher()
    dispatcher.stop()  # type: ignore[no-untyped-call]

    try:
        DaemonRPC().logout()
    except Exception:
        pass

    config_path = get_config_path()
    if os.path.exists(config_path):
        shutil.rmtree(config_path)

    cache_path = get_cache_path()
    if os.path.exists(cache_path):
        shutil.rmtree(cache_path)

    clear_chat_runtime_cache()

    remove_background_service_files()

    return ClearDataResponse(success=True)


@dataclass
class PhoneNumberResponse:
    success: bool
    phone_number: str


@crash_reporter
@dataclass_to_dict
def get_phone_number(jid: str) -> PhoneNumberResponse:
    try:
        phone = DaemonRPC().get_phone_number(jid)
        return PhoneNumberResponse(success=True, phone_number=phone)
    except Exception:
        return PhoneNumberResponse(success=True, phone_number="")


def _ui_message(message: Message) -> UiMessage:
    return to_ui_message(message)


def _ui_chat(chat: ChatListItem) -> ChatListItem:
    return render_chat_mentions(chat)


def _ui_message_dict(message: Message) -> dict[str, object]:
    return _enum_to_str(asdict(_ui_message(message)))  # type: ignore[no-untyped-call, no-any-return]


def _ui_chat_dict(chat: ChatListItem) -> dict[str, object]:
    return _enum_to_str(asdict(_ui_chat(chat)))  # type: ignore[no-untyped-call, no-any-return]


@crash_reporter
@dataclass_to_dict
def get_chat_list() -> ChatListResponse:
    try:
        with KV() as kv:
            entries = kv.get_partial("chat:")
            drafts = {key.removeprefix("draft:"): str(value or "") for key, value in kv.get_partial("draft:")}

        chats = []
        for _, value in entries:
            chat = _ui_chat(ChatListItem(**value))
            draft = drafts.get(chat.id, "")
            chats.append(ChatListEntry(**asdict(chat), draft=draft, has_draft=draft != ""))
        chats.sort(key=lambda c: c.last_message_timestamp, reverse=True)
        return ChatListResponse(success=True, chats=chats, message="")
    except Exception as e:
        return ChatListResponse(success=False, chats=[], message=str(e))


@crash_reporter
def get_chat_info(chat_id: str) -> dict[str, object]:
    with KV() as kv:
        data = kv.get(f"chat:{chat_id}")
    if not data:
        return {"success": False}
    try:
        chat = ChatListItem(**data)
    except (TypeError, KeyError):
        return {"success": False}
    return {
        "success": True,
        "id": chat.id,
        "name": chat.name,
        "photo": chat.photo,
        "is_group": chat.is_group,
        "unread_count": chat.unread_count,
    }


@crash_reporter
@dataclass_to_dict
def get_group_mention_candidates(chat_id: str) -> GroupMentionCandidatesResponse:
    try:
        participants = DaemonRPC().get_group_participants(chat_id).Participants
        candidates = []
        for participant in participants:
            candidate = build_mention_candidate(participant.jid, participant.display_name)
            candidate["is_admin"] = participant.is_admin
            candidate["is_super_admin"] = participant.is_super_admin
            candidates.append(candidate)
        candidates.sort(key=lambda candidate: str(candidate.get("label") or "").lower())
        return GroupMentionCandidatesResponse(success=True, candidates=candidates)
    except Exception as e:
        return GroupMentionCandidatesResponse(success=False, message=str(e))


@crash_reporter
@dataclass_to_dict
def get_chat_draft(chat_id: str) -> ChatDraftResponse:
    with KV() as kv:
        draft = kv.get(f"draft:{chat_id}", default="")
        draft_mentions = kv.get(f"draft_mentions:{chat_id}", default=[])

    draft_text = str(draft or "")
    mention_spans = validate_mention_spans(
        draft_text,
        draft_mentions if isinstance(draft_mentions, list) else None,
    )
    return ChatDraftResponse(success=True, text=draft_text, mention_spans=mention_spans)


@crash_reporter
@dataclass_to_dict
def set_chat_draft(
    chat_id: str,
    text: str,
    mention_spans: list[dict[str, object]] | None = None,
) -> SuccessResponse:
    import pyotherside

    draft_text = str(text)
    validated_spans = validate_mention_spans(draft_text, mention_spans)
    with KV() as kv:
        if draft_text != "":
            kv.put(f"draft:{chat_id}", draft_text)
            if validated_spans:
                kv.put(f"draft_mentions:{chat_id}", validated_spans)
            else:
                kv.delete(f"draft_mentions:{chat_id}")
        else:
            kv.delete(f"draft:{chat_id}")
            kv.delete(f"draft_mentions:{chat_id}")
    pyotherside.send(
        "chat-draft-update",
        [{"id": chat_id, "draft": draft_text, "has_draft": draft_text != ""}],
    )
    return SuccessResponse(success=True, message="")


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

        msg_fields = {f.name for f in Message.__dataclass_fields__.values()}
        messages = [Message(**{k: v for k, v in value.items() if k in msg_fields}) for _, value in entries]
        messages.sort(key=lambda m: (m.timestamp_unix, m.id))
        rendered_messages = [_ui_message(m) for m in messages]

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
    import pyotherside

    with KV() as kv:
        entries = kv.get_partial(f"message:{chat_id}:")
        unread_by_sender: dict[str, list[str]] = {}
        for _key, value in entries:
            if value.get("is_outgoing") or value.get("read_receipt") == ReadReceipt.READ:
                continue
            sender = str(value.get("sender_raw") or value.get("sender") or "")
            unread_by_sender.setdefault(sender, []).append(value["id"])

    if not unread_by_sender:
        return SuccessResponse(success=True, message="")

    rpc = DaemonRPC()
    for sender, ids in unread_by_sender.items():
        rpc.mark_read(chat_id, ids, sender_jid=sender)

    with KV() as kv:
        existing = kv.get(f"chat:{chat_id}")
        if existing:
            chat = ChatListItem(**existing)
            prev_unread = chat.unread_count
            chat.unread_count = 0
            kv.put(f"chat:{chat_id}", asdict(chat))
            pyotherside.send("chat-list-update", [_ui_chat_dict(chat)])
            if prev_unread > 0:
                decrement_unread_total(prev_unread)

    try:
        rpc.clear_chat_notifications([chat_id])
    except Exception:
        pass

    return SuccessResponse(success=True, message="")


def send_presence(available: bool) -> None:
    try:
        DaemonRPC().send_presence(available)
    except Exception:
        pass


def subscribe_presence(chat_id: str) -> None:
    if "@g.us" in chat_id:
        return
    try:
        DaemonRPC().subscribe_presence(chat_id)
    except Exception:
        pass


@crash_reporter
@dataclass_to_dict
def toggle_mute(chat_id: str) -> SuccessResponse:
    import pyotherside

    with KV() as kv:
        data = kv.get(f"chat:{chat_id}")
        if data is None:
            return SuccessResponse(success=False, message="Chat not found")
        chat = ChatListItem(**data)
        new_muted = not chat.muted

    DaemonRPC().set_muted(chat_id, new_muted)

    with KV() as kv:
        data = kv.get(f"chat:{chat_id}")
        if data is not None:
            chat = ChatListItem(**data)
            chat.muted = new_muted
            kv.put(f"chat:{chat_id}", asdict(chat))
            pyotherside.send("chat-list-update", [_ui_chat_dict(chat)])

    return SuccessResponse(success=True, message="")


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

    msg_fields = {f.name for f in Message.__dataclass_fields__.values()}
    stored_msg = Message(**{k: v for k, v in entry.items() if k in msg_fields})  # type: ignore[arg-type]
    rendered_msg = _ui_message(stored_msg)

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
    import pyotherside

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
    except Exception as e:
        return SuccessResponse(success=False, message=str(e))

    msg_fields = {f.name for f in Message.__dataclass_fields__.values()}
    updated_msg = Message(**{k: v for k, v in entry.items() if k in msg_fields})  # type: ignore[arg-type]
    updated_msg.text = normalized_text
    updated_msg.edited = True

    updated_entry = dict(entry)
    updated_entry.update(asdict(updated_msg))
    with KV() as kv:
        kv.put(entry_key, updated_entry)
        chat = _update_chat_after_edit(kv, updated_msg, MessageInfo())

    pyotherside.send("message-upsert", [_ui_message_dict(updated_msg)])
    pyotherside.send("chat-list-update", [_ui_chat_dict(chat)])

    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def delete_message(chat_id: str, message_id: str) -> SuccessResponse:
    import pyotherside

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
    except Exception as e:
        return SuccessResponse(success=False, message=str(e))

    msg_fields = {f.name for f in Message.__dataclass_fields__.values()}
    existing_msg = Message(**{k: v for k, v in entry.items() if k in msg_fields})  # type: ignore[arg-type]
    deleted_msg = _merge_deleted_message(existing_msg, existing_msg.sender)

    updated_entry = dict(entry)
    updated_entry.update(asdict(deleted_msg))
    with KV() as kv:
        kv.put(entry_key, updated_entry)
        chat = _update_chat_after_edit(kv, deleted_msg, MessageInfo())

    pyotherside.send("message-upsert", [_ui_message_dict(deleted_msg)])
    pyotherside.send("chat-list-update", [_ui_chat_dict(chat)])

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
    import pyotherside

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
    except Exception as e:
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
        pyotherside.send("message-upsert", [_ui_message_dict(failed_msg)])
        return SuccessResponse(success=False, message=str(e) or "Failed to prepare audio")

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

    with open(file_path, encoding="utf-8-sig") as f:
        vcard = f.read()

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


@crash_reporter
@dataclass_to_dict
def download_media(chat_id: str, message_id: str, media_type: str) -> DownloadMediaResponse:
    import pyotherside

    entry_key, entry = _get_message_entry_with_key(chat_id, message_id)

    if entry is None or entry.get("raw") is None:
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
    except Exception as e:
        return DownloadMediaResponse(success=False, media_path="", message=str(e))

    if not file_path:
        return DownloadMediaResponse(success=False, media_path="", message="Failed to download media")

    media_path = "file://" + file_path
    entry["media_path"] = media_path
    with KV() as kv:
        kv.put(entry_key, sanitize_message_payload(entry))

    msg_fields = {f.name for f in Message.__dataclass_fields__.values()}
    msg = Message(**{k: v for k, v in entry.items() if k in msg_fields})  # type: ignore[arg-type]
    pyotherside.send("message-upsert", [_ui_message_dict(msg)])

    return DownloadMediaResponse(success=True, media_path=media_path, message="")
