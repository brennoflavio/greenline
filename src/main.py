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

from dataclasses import asdict, dataclass

from daemon import (
    install_background_service_files,
    is_daemon_active,
    reload_systemd,
)
from events import ChatListUpdateEvent, MessageStatusUpdateEvent, NewMessageEvent
from models import (
    ChatListItem,
    ChatListResponse,
    Message,
    MessagesResponse,
    MessageType,
    ReadReceipt,
)
from ut_components.crash import crash_reporter
from ut_components.event import get_event_dispatcher
from ut_components.kv import KV
from ut_components.utils import dataclass_to_dict


def start_event_loop():
    dispatcher = get_event_dispatcher()
    dispatcher.register_event(NewMessageEvent())
    dispatcher.register_event(MessageStatusUpdateEvent())
    dispatcher.register_event(ChatListUpdateEvent())
    dispatcher.start()


@dataclass
class SuccessResponse:
    success: bool
    message: str


def _seed_mock_data():
    with KV() as kv:
        if kv.get("mock_seeded"):
            return

        chats = [
            ChatListItem(
                id="alice@s.whatsapp.net",
                name="Alice",
                photo="",
                last_message="See you tomorrow!",
                date="10:42",
                last_message_timestamp=1742900520,
                read_receipt=ReadReceipt.READ,
                unread_count=0,
                is_group=False,
            ),
            ChatListItem(
                id="work@g.us",
                name="Work Group",
                photo="",
                last_message="Bob: I'll send the report by EOD",
                date="09:15",
                last_message_timestamp=1742895300,
                read_receipt=ReadReceipt.NONE,
                unread_count=3,
                is_group=True,
            ),
            ChatListItem(
                id="mom@s.whatsapp.net",
                name="Mom",
                photo="",
                last_message="Thanks for calling 😊",
                date="Yesterday",
                last_message_timestamp=1742810400,
                read_receipt=ReadReceipt.DELIVERED,
                unread_count=0,
                is_group=False,
            ),
            ChatListItem(
                id="david@s.whatsapp.net",
                name="David",
                photo="",
                last_message="Can you pick up some groceries?",
                date="Yesterday",
                last_message_timestamp=1742808000,
                read_receipt=ReadReceipt.NONE,
                unread_count=1,
                is_group=False,
            ),
            ChatListItem(
                id="football@g.us",
                name="Football Team",
                photo="",
                last_message="You: Game is at 5pm",
                date="Monday",
                last_message_timestamp=1742724000,
                read_receipt=ReadReceipt.SENT,
                unread_count=0,
                is_group=True,
            ),
            ChatListItem(
                id="sarah@s.whatsapp.net",
                name="Sarah",
                photo="",
                last_message="That's hilarious 😂",
                date="Monday",
                last_message_timestamp=1742720400,
                read_receipt=ReadReceipt.READ,
                unread_count=0,
                is_group=False,
            ),
            ChatListItem(
                id="technews@g.us",
                name="Tech News",
                photo="",
                last_message="5 new messages",
                date="Sunday",
                last_message_timestamp=1742637600,
                read_receipt=ReadReceipt.NONE,
                unread_count=5,
                is_group=True,
            ),
        ]

        for chat in chats:
            kv.put(f"chat:{chat.id}", asdict(chat))

        alice_messages = [
            Message(
                id="msg1",
                chat_id="alice@s.whatsapp.net",
                type=MessageType.TEXT,
                is_outgoing=False,
                timestamp="10:30",
                timestamp_unix=1742899800,
                read_receipt=ReadReceipt.NONE,
                text="Hey! How are you doing?",
            ),
            Message(
                id="msg2",
                chat_id="alice@s.whatsapp.net",
                type=MessageType.TEXT,
                is_outgoing=True,
                timestamp="10:31",
                timestamp_unix=1742899860,
                read_receipt=ReadReceipt.READ,
                text="I'm doing great, thanks! Just got back from the trip 🎉",
            ),
            Message(
                id="msg3",
                chat_id="alice@s.whatsapp.net",
                type=MessageType.IMAGE,
                is_outgoing=True,
                timestamp="10:31",
                timestamp_unix=1742899870,
                read_receipt=ReadReceipt.READ,
                caption="Check out this view from the hotel!",
            ),
            Message(
                id="msg4",
                chat_id="alice@s.whatsapp.net",
                type=MessageType.TEXT,
                is_outgoing=False,
                timestamp="10:32",
                timestamp_unix=1742899920,
                read_receipt=ReadReceipt.NONE,
                text="Wow that looks amazing! 😍",
            ),
            Message(
                id="msg5",
                chat_id="alice@s.whatsapp.net",
                type=MessageType.IMAGE_GALLERY,
                is_outgoing=True,
                timestamp="10:33",
                timestamp_unix=1742899980,
                read_receipt=ReadReceipt.DELIVERED,
                caption="Here are more photos from the trip",
                images=["", "", "", ""],
            ),
            Message(
                id="msg6",
                chat_id="alice@s.whatsapp.net",
                type=MessageType.VOICE,
                is_outgoing=False,
                timestamp="10:35",
                timestamp_unix=1742900100,
                read_receipt=ReadReceipt.NONE,
                duration="0:42",
            ),
            Message(
                id="msg7",
                chat_id="alice@s.whatsapp.net",
                type=MessageType.STICKER,
                is_outgoing=True,
                timestamp="10:36",
                timestamp_unix=1742900160,
                read_receipt=ReadReceipt.READ,
            ),
            Message(
                id="msg8",
                chat_id="alice@s.whatsapp.net",
                type=MessageType.TEXT,
                is_outgoing=False,
                timestamp="10:37",
                timestamp_unix=1742900220,
                read_receipt=ReadReceipt.NONE,
                text="Haha love that sticker! Let's catch up this weekend?",
            ),
            Message(
                id="msg9",
                chat_id="alice@s.whatsapp.net",
                type=MessageType.IMAGE,
                is_outgoing=False,
                timestamp="10:38",
                timestamp_unix=1742900280,
                read_receipt=ReadReceipt.NONE,
            ),
            Message(
                id="msg10",
                chat_id="alice@s.whatsapp.net",
                type=MessageType.TEXT,
                is_outgoing=True,
                timestamp="10:42",
                timestamp_unix=1742900520,
                read_receipt=ReadReceipt.READ,
                text="See you tomorrow!",
            ),
        ]

        david_messages = [
            Message(
                id="dmsg1",
                chat_id="david@s.whatsapp.net",
                type=MessageType.TEXT,
                is_outgoing=False,
                timestamp="14:20",
                timestamp_unix=1742806800,
                read_receipt=ReadReceipt.NONE,
                text="Hey, are you free today?",
            ),
            Message(
                id="dmsg2",
                chat_id="david@s.whatsapp.net",
                type=MessageType.TEXT,
                is_outgoing=True,
                timestamp="14:25",
                timestamp_unix=1742807100,
                read_receipt=ReadReceipt.READ,
                text="Yeah, what's up?",
            ),
            Message(
                id="dmsg3",
                chat_id="david@s.whatsapp.net",
                type=MessageType.VOICE,
                is_outgoing=False,
                timestamp="14:26",
                timestamp_unix=1742807160,
                read_receipt=ReadReceipt.NONE,
                duration="1:15",
            ),
            Message(
                id="dmsg4",
                chat_id="david@s.whatsapp.net",
                type=MessageType.TEXT,
                is_outgoing=False,
                timestamp="14:30",
                timestamp_unix=1742808000,
                read_receipt=ReadReceipt.NONE,
                text="Can you pick up some groceries?",
            ),
        ]

        for msg in alice_messages + david_messages:
            kv.put(f"message:{msg.chat_id}:{msg.id}", asdict(msg))

        kv.put("mock_seeded", True)


@dataclass
class DaemonStatusResponse:
    installed: bool


@dataclass
class ClearDataResponse:
    success: bool


@crash_reporter
@dataclass_to_dict
def check_daemon_status() -> DaemonStatusResponse:
    return DaemonStatusResponse(installed=is_daemon_active())


@crash_reporter
@dataclass_to_dict
def install_daemon() -> SuccessResponse:
    try:
        install_background_service_files()
        reload_systemd()
        return SuccessResponse(success=True, message="Daemon installed.")
    except Exception as e:
        return SuccessResponse(success=False, message=str(e))


@crash_reporter
@dataclass_to_dict
def uninstall_daemon() -> SuccessResponse:
    try:
        reload_systemd()
        return SuccessResponse(success=True, message="Daemon uninstalled.")
    except Exception as e:
        return SuccessResponse(success=False, message=str(e))


@crash_reporter
@dataclass_to_dict
def clear_data() -> ClearDataResponse:
    with KV() as kv:
        kv.delete_partial("chat:")
        kv.delete_partial("message:")
        kv.delete("mock_seeded")
    return ClearDataResponse(success=True)


@crash_reporter
@dataclass_to_dict
def get_chat_list() -> ChatListResponse:
    _seed_mock_data()
    with KV() as kv:
        entries = kv.get_partial("chat:")
        chats = [ChatListItem(**value) for _, value in entries]
        chats.sort(key=lambda c: c.last_message_timestamp, reverse=True)
    return ChatListResponse(success=True, chats=chats, message="")


@crash_reporter
@dataclass_to_dict
def get_messages(chat_id: str) -> MessagesResponse:
    with KV() as kv:
        entries = kv.get_partial(f"message:{chat_id}:")
        messages = [Message(**value) for _, value in entries]
        messages.sort(key=lambda m: m.timestamp_unix)
    return MessagesResponse(success=True, messages=messages, message="")
