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
from dataclasses import dataclass

from daemon import (
    ensure_daemon_version,
    install_background_service_files,
    is_daemon_active,
    is_daemon_installed,
    remove_background_service_files,
)
from daemon_types import Contact as DaemonContact
from events import (
    QR_IMAGE_PATH,
    ChatListUpdateEvent,
    MessageStatusUpdateEvent,
    NewMessageEvent,
    SessionStatusEvent,
    SessionStatusResponse,
)
from models import (
    ChatListItem,
    ChatListResponse,
    ContactItem,
    ContactListResponse,
    Message,
    MessagesResponse,
)
from rpc import DaemonRPC
from ut_components.crash import crash_reporter
from ut_components.event import get_event_dispatcher
from ut_components.kv import KV
from ut_components.utils import dataclass_to_dict


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
    dispatcher.register_event(NewMessageEvent())
    dispatcher.register_event(MessageStatusUpdateEvent())
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
    return DaemonStatusResponse(
        installed=is_daemon_installed(),
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
    with KV() as kv:
        kv.delete_partial("chat:")
        kv.delete_partial("message:")
    return ClearDataResponse(success=True)


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
        messages = [Message(**{k: v for k, v in value.items() if k != "raw"}) for _, value in entries]
        messages.sort(key=lambda m: m.timestamp_unix)
    return MessagesResponse(success=True, messages=messages, message="")
