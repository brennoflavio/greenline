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
from ut_components import setup

setup(APP_NAME, CRASH_REPORT_URL)

import base64
import os
import shutil
import time
from dataclasses import asdict, dataclass

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
    QR_IMAGE_PATH,
    ChatListUpdateEvent,
    DaemonEventHandler,
    SessionStatusEvent,
    SessionStatusResponse,
)
from message_store import upsert_chat
from models import (
    ChatListItem,
    ChatListResponse,
    ContactItem,
    ContactListResponse,
    Message,
    MessagesResponse,
    MessageType,
    ReadReceipt,
)
from rpc import DaemonRPC
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


def start_event_loop() -> None:
    dispatcher = get_event_dispatcher()
    dispatcher.register_event(SessionStatusEvent())
    dispatcher.register_event(DaemonEventHandler())
    dispatcher.register_event(ChatListUpdateEvent())
    dispatcher.start()


@dataclass
class SuccessResponse:
    success: bool
    message: str


@dataclass
class DaemonStatusResponse:
    installed: bool
    active: bool


@dataclass
class ClearDataResponse:
    success: bool


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
    photo = ""
    if contact.avatar_path:
        photo = "file://" + contact.avatar_path
    return ContactItem(
        jid=contact.jid,
        display_name=contact.display_name or contact.jid,
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


@crash_reporter
@dataclass_to_dict
def get_chat_list() -> ChatListResponse:
    try:
        with KV() as kv:
            entries = kv.get_partial("chat:")

        chats = [ChatListItem(**value) for _, value in entries]
        chats.sort(key=lambda c: c.last_message_timestamp, reverse=True)
        return ChatListResponse(success=True, chats=chats, message="")
    except Exception as e:
        return ChatListResponse(success=False, chats=[], message=str(e))


@crash_reporter
@dataclass_to_dict
def get_messages(chat_id: str) -> MessagesResponse:
    with KV() as kv:
        entries = kv.get_partial(f"message:{chat_id}:")
        msg_fields = {f.name for f in Message.__dataclass_fields__.values()}
        messages = [Message(**{k: v for k, v in value.items() if k in msg_fields}) for _, value in entries]
        messages.sort(key=lambda m: m.timestamp_unix)

        sender_jids = {m.sender for m in messages if m.sender and not m.is_outgoing}
        sender_photos: dict[str, str] = {}
        for jid in sender_jids:
            data = kv.get(f"chat:{jid}")
            if data:
                sender_photos[jid] = data.get("photo", "")

        for m in messages:
            if m.sender and m.sender in sender_photos:
                m.sender_photo = sender_photos[m.sender]

    return MessagesResponse(success=True, messages=messages, message="")


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
            sender = value.get("sender", "")
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
            chat.unread_count = 0
            kv.put(f"chat:{chat_id}", asdict(chat))
            pyotherside.send("chat-list-update", [_enum_to_str(asdict(chat))])  # type: ignore[no-untyped-call]

    return SuccessResponse(success=True, message="")


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
            pyotherside.send("chat-list-update", [_enum_to_str(asdict(chat))])  # type: ignore[no-untyped-call]

    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def send_text_message(chat_id: str, text: str, temp_id: str = "") -> SuccessResponse:
    from datetime import datetime

    import pyotherside

    try:
        rpc = DaemonRPC()
        result = rpc.send_message(chat_id, "text", text=text)
    except Exception:
        now = datetime.now()
        failed_msg = Message(
            id=temp_id or f"failed-{int(now.timestamp())}",
            chat_id=chat_id,
            type=MessageType.TEXT,
            is_outgoing=True,
            timestamp=now.strftime("%H:%M"),
            timestamp_unix=int(now.timestamp()),
            read_receipt=ReadReceipt.NONE,
            text=text,
            send_status="failed",
            temp_id=temp_id,
        )
        pyotherside.send("message-upsert", [_enum_to_str(asdict(failed_msg))])  # type: ignore[no-untyped-call]
        return SuccessResponse(success=False, message="Failed to send message")

    ts = result["Timestamp"]
    msg = Message(
        id=result["MessageID"],
        chat_id=chat_id,
        type=MessageType.TEXT,
        is_outgoing=True,
        timestamp=datetime.fromtimestamp(ts).strftime("%H:%M"),
        timestamp_unix=ts,
        read_receipt=ReadReceipt.SENT,
        text=text,
        temp_id=temp_id,
    )

    key = f"message:{chat_id}:{msg.timestamp_unix}:{msg.id}"
    with KV() as kv:
        kv.put(key, asdict(msg))

    chat = upsert_chat(msg, MessageInfo())
    pyotherside.send("message-upsert", [_enum_to_str(asdict(msg))])  # type: ignore[no-untyped-call]
    pyotherside.send("chat-list-update", [_enum_to_str(asdict(chat))])  # type: ignore[no-untyped-call]

    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def send_image_message(chat_id: str, file_path: str, caption: str = "", temp_id: str = "") -> SuccessResponse:
    import shutil
    from datetime import datetime

    import pyotherside

    cache_dir = os.path.join(get_cache_path(), "outgoing")
    os.makedirs(cache_dir, exist_ok=True)
    ext = os.path.splitext(file_path)[1] or ".jpg"
    cached_path = os.path.join(cache_dir, f"{temp_id or int(datetime.now().timestamp())}{ext}")
    shutil.copy2(file_path, cached_path)

    now = datetime.now()
    hours = now.strftime("%H")
    minutes = now.strftime("%M")

    pending_msg = Message(
        id=temp_id or f"pending-{int(now.timestamp())}",
        chat_id=chat_id,
        type=MessageType.IMAGE,
        is_outgoing=True,
        timestamp=f"{hours}:{minutes}",
        timestamp_unix=int(now.timestamp()),
        read_receipt=ReadReceipt.NONE,
        caption=caption,
        media_path="file://" + cached_path,
        send_status="pending",
        temp_id=temp_id,
    )
    pyotherside.send("message-upsert", [_enum_to_str(asdict(pending_msg))])  # type: ignore[no-untyped-call]

    try:
        rpc = DaemonRPC()
        result = rpc.send_message(chat_id, "image", file_path=cached_path, caption=caption)
    except Exception:
        pending_msg.send_status = "failed"
        pyotherside.send("message-upsert", [_enum_to_str(asdict(pending_msg))])  # type: ignore[no-untyped-call]
        return SuccessResponse(success=False, message="Failed to send image")

    ts = result["Timestamp"]
    msg = Message(
        id=result["MessageID"],
        chat_id=chat_id,
        type=MessageType.IMAGE,
        is_outgoing=True,
        timestamp=datetime.fromtimestamp(ts).strftime("%H:%M"),
        timestamp_unix=ts,
        read_receipt=ReadReceipt.SENT,
        caption=caption,
        media_path="file://" + cached_path,
        temp_id=temp_id,
    )

    key = f"message:{chat_id}:{msg.timestamp_unix}:{msg.id}"
    with KV() as kv:
        kv.put(key, asdict(msg))

    chat = upsert_chat(msg, MessageInfo())
    pyotherside.send("message-upsert", [_enum_to_str(asdict(msg))])  # type: ignore[no-untyped-call]
    pyotherside.send("chat-list-update", [_enum_to_str(asdict(chat))])  # type: ignore[no-untyped-call]

    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def send_video_message(chat_id: str, file_path: str, caption: str = "", temp_id: str = "") -> SuccessResponse:
    import shutil
    from datetime import datetime

    import pyotherside

    cache_dir = os.path.join(get_cache_path(), "outgoing")
    os.makedirs(cache_dir, exist_ok=True)
    ext = os.path.splitext(file_path)[1] or ".mp4"
    cached_path = os.path.join(cache_dir, f"{temp_id or int(datetime.now().timestamp())}{ext}")
    shutil.copy2(file_path, cached_path)

    now = datetime.now()
    hours = now.strftime("%H")
    minutes = now.strftime("%M")

    pending_msg = Message(
        id=temp_id or f"pending-{int(now.timestamp())}",
        chat_id=chat_id,
        type=MessageType.VIDEO,
        is_outgoing=True,
        timestamp=f"{hours}:{minutes}",
        timestamp_unix=int(now.timestamp()),
        read_receipt=ReadReceipt.NONE,
        caption=caption,
        media_path="file://" + cached_path,
        send_status="pending",
        temp_id=temp_id,
    )
    pyotherside.send("message-upsert", [_enum_to_str(asdict(pending_msg))])  # type: ignore[no-untyped-call]

    try:
        rpc = DaemonRPC()
        result = rpc.send_message(chat_id, "video", file_path=cached_path, caption=caption)
    except Exception:
        pending_msg.send_status = "failed"
        pyotherside.send("message-upsert", [_enum_to_str(asdict(pending_msg))])  # type: ignore[no-untyped-call]
        return SuccessResponse(success=False, message="Failed to send video")

    ts = result["Timestamp"]
    msg = Message(
        id=result["MessageID"],
        chat_id=chat_id,
        type=MessageType.VIDEO,
        is_outgoing=True,
        timestamp=datetime.fromtimestamp(ts).strftime("%H:%M"),
        timestamp_unix=ts,
        read_receipt=ReadReceipt.SENT,
        caption=caption,
        media_path="file://" + cached_path,
        temp_id=temp_id,
    )

    key = f"message:{chat_id}:{msg.timestamp_unix}:{msg.id}"
    with KV() as kv:
        kv.put(key, asdict(msg))

    chat = upsert_chat(msg, MessageInfo())
    pyotherside.send("message-upsert", [_enum_to_str(asdict(msg))])  # type: ignore[no-untyped-call]
    pyotherside.send("chat-list-update", [_enum_to_str(asdict(chat))])  # type: ignore[no-untyped-call]

    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def send_sticker_message(chat_id: str, file_path: str, temp_id: str = "") -> SuccessResponse:
    import shutil
    from datetime import datetime

    import pyotherside

    cache_dir = os.path.join(get_cache_path(), "outgoing")
    os.makedirs(cache_dir, exist_ok=True)
    ext = os.path.splitext(file_path)[1] or ".webp"
    cached_path = os.path.join(cache_dir, f"{temp_id or int(datetime.now().timestamp())}{ext}")
    shutil.copy2(file_path, cached_path)

    now = datetime.now()
    hours = now.strftime("%H")
    minutes = now.strftime("%M")

    pending_msg = Message(
        id=temp_id or f"pending-{int(now.timestamp())}",
        chat_id=chat_id,
        type=MessageType.STICKER,
        is_outgoing=True,
        timestamp=f"{hours}:{minutes}",
        timestamp_unix=int(now.timestamp()),
        read_receipt=ReadReceipt.NONE,
        media_path="file://" + cached_path,
        send_status="pending",
        temp_id=temp_id,
    )
    pyotherside.send("message-upsert", [_enum_to_str(asdict(pending_msg))])  # type: ignore[no-untyped-call]

    try:
        rpc = DaemonRPC()
        result = rpc.send_message(chat_id, "sticker", file_path=cached_path)
    except Exception:
        pending_msg.send_status = "failed"
        pyotherside.send("message-upsert", [_enum_to_str(asdict(pending_msg))])  # type: ignore[no-untyped-call]
        return SuccessResponse(success=False, message="Failed to send sticker")

    ts = result["Timestamp"]
    msg = Message(
        id=result["MessageID"],
        chat_id=chat_id,
        type=MessageType.STICKER,
        is_outgoing=True,
        timestamp=datetime.fromtimestamp(ts).strftime("%H:%M"),
        timestamp_unix=ts,
        read_receipt=ReadReceipt.SENT,
        media_path="file://" + cached_path,
        temp_id=temp_id,
    )

    key = f"message:{chat_id}:{msg.timestamp_unix}:{msg.id}"
    with KV() as kv:
        kv.put(key, asdict(msg))

    chat = upsert_chat(msg, MessageInfo())
    pyotherside.send("message-upsert", [_enum_to_str(asdict(msg))])  # type: ignore[no-untyped-call]
    pyotherside.send("chat-list-update", [_enum_to_str(asdict(chat))])  # type: ignore[no-untyped-call]

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

    with KV() as kv:
        entries = kv.get_partial(f"message:{chat_id}:")
        entry = None
        entry_key = ""
        for key, value in entries:
            if value.get("id") == message_id:
                entry = value
                entry_key = key
                break

    if entry is None or entry.get("raw") is None:
        return DownloadMediaResponse(success=False, media_path="", message="Message not found")

    raw = entry["raw"]
    msg_content = raw.get("Message", {})
    field_name = _MEDIA_TYPE_MAP.get(media_type)
    if not field_name:
        return DownloadMediaResponse(success=False, media_path="", message=f"Unknown media type: {media_type}")

    media_msg = msg_content.get(field_name)
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

    media_path = "file://" + file_path
    entry["media_path"] = media_path
    with KV() as kv:
        kv.put(entry_key, entry)

    msg_fields = {f.name for f in Message.__dataclass_fields__.values()}
    msg_dict = _enum_to_str({k: v for k, v in entry.items() if k in msg_fields})  # type: ignore[no-untyped-call]
    pyotherside.send("message-upsert", [msg_dict])

    return DownloadMediaResponse(success=True, media_path=media_path, message="")
