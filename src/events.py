import base64
import json
import os
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Dict, Optional

import pyotherside
from dacite import from_dict

from message_store import store_message
from models import ChatListItem, ReadReceipt
from receipt_store import process_receipt
from rpc import DaemonRPC, RateLimitError
from ut_components.config import get_cache_path
from ut_components.event import Event
from ut_components.kv import KV
from ut_components.utils import enum_to_str as _enum_to_str
from whatsmeow_types import MessageEvent, ReceiptEvent


def enum_to_str(obj: Dict[str, Any]) -> Dict[str, Any]:
    return _enum_to_str(obj)  # type: ignore[no-untyped-call, no-any-return]


QR_IMAGE_PATH = os.path.join(get_cache_path(), "qr.png")
STATUS_BROADCAST_JID = "status@broadcast"


@dataclass
class SessionStatusResponse:
    logged_in: bool
    qr_image_path: str


class SessionStatusEvent(Event):
    def __init__(self) -> None:
        super().__init__(
            id="session-status",
            execution_interval=timedelta(seconds=2),
        )

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> Optional[SessionStatusResponse]:
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


LAST_EVENT_ID_KEY = "daemon:last_event_id"


def _handle_message(event: Any, chat_updates: dict[str, dict[str, Any]]) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=MessageEvent, data=raw)
    if evt.Info.Chat == STATUS_BROADCAST_JID:
        return
    evt.Info.Chat = DaemonRPC().ensure_jid(evt.Info.Chat)
    stored = store_message(evt, raw=raw)
    if stored is not None:
        pyotherside.send("message-upsert", enum_to_str(asdict(stored.message)))
        chat_updates[stored.chat.id] = enum_to_str(asdict(stored.chat))


def _handle_receipt(
    event: Any,
    chat_updates: dict[str, dict[str, Any]],
    message_updates: list[dict[str, Any]],
) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=ReceiptEvent, data=raw)
    evt.Chat = DaemonRPC().ensure_jid(evt.Chat)
    updated_messages, updated_chat = process_receipt(evt)
    for msg in updated_messages:
        message_updates.append(enum_to_str(msg))
    if updated_chat is not None:
        chat_updates[updated_chat.id] = enum_to_str(asdict(updated_chat))


def _handle_mute(event: Any, chat_updates: dict[str, dict[str, Any]]) -> None:
    raw = json.loads(event.payload or "{}")
    jid = raw.get("JID", "")
    if not jid:
        return
    action = raw.get("Action") or {}
    muted = action.get("muted", False)

    with KV() as kv:
        key = f"chat:{jid}"
        data = kv.get(key)
        if data is None:
            return
        chat = ChatListItem(**data)
        if chat.muted != muted:
            chat.muted = muted
            kv.put(key, asdict(chat))
            chat_updates[chat.id] = enum_to_str(asdict(chat))


def _handle_unknown(event: Any) -> None:
    with KV() as kv:
        kv.put(
            f"unknown_event:{event.event_type}:{event.id}",
            {
                "event_type": event.event_type,
                "payload": event.payload or "",
            },
        )


class DaemonEventHandler(Event):
    def __init__(self) -> None:
        super().__init__(id="daemon-event", execution_interval=timedelta(seconds=2))

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> None:
        with KV() as kv:
            last_id = kv.get(LAST_EVENT_ID_KEY, default=0)

        reply = DaemonRPC().list_events(after_id=last_id)
        if not reply.Events:
            return None

        max_id = last_id
        chat_updates: dict[str, dict[str, Any]] = {}
        message_updates: list[dict[str, Any]] = []
        for event in reply.Events:
            if event.event_type == "Message":
                _handle_message(event, chat_updates)
            elif event.event_type == "Receipt":
                _handle_receipt(event, chat_updates, message_updates)
            elif event.event_type == "Mute":
                _handle_mute(event, chat_updates)
            else:
                _handle_unknown(event)
            if event.id > max_id:
                max_id = event.id

        for msg in message_updates:
            pyotherside.send("message-upsert", msg)

        if chat_updates:
            pyotherside.send("chat-list-update", list(chat_updates.values()))

        if max_id > last_id:
            DaemonRPC().delete_events(up_to_id=max_id)
            with KV() as kv:
                kv.put(LAST_EVENT_ID_KEY, max_id)

        return None


class ChatListUpdateEvent(Event):
    def __init__(self) -> None:
        super().__init__(id="chat-list-update", execution_interval=timedelta(seconds=30))

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> None:
        chat_updates: list[dict[str, Any]] = []

        try:
            self._sync_contacts(chat_updates)
            self._sync_groups(chat_updates)
        except RateLimitError:
            return None

        if chat_updates:
            pyotherside.send("chat-list-update", chat_updates)

        return None

    @staticmethod
    def _is_muted(jid: str) -> bool:
        try:
            reply = DaemonRPC().get_chat_settings(jid)
            return reply.MutedUntil != 0
        except Exception:
            return False

    def _sync_contacts(self, chat_updates: list[dict[str, Any]]) -> None:
        reply = DaemonRPC().get_contacts()
        contacts = {}
        for c in reply.Contacts:
            if c.jid and c.display_name:
                photo = ""
                if c.avatar_path:
                    photo = "file://" + c.avatar_path
                contacts[c.jid] = {"name": c.display_name, "photo": photo}

        if not contacts:
            return

        with KV() as kv:
            existing = {key: value for key, value in kv.get_partial("chat:")}

            for jid, info in contacts.items():
                key = f"chat:{jid}"
                muted = self._is_muted(jid)
                if key in existing:
                    chat = ChatListItem(**existing[key])
                    changed = False
                    if chat.name != info["name"]:
                        chat.name = info["name"]
                        changed = True
                    if chat.photo != info["photo"]:
                        chat.photo = info["photo"]
                        changed = True
                    if chat.muted != muted:
                        chat.muted = muted
                        changed = True
                    if changed:
                        kv.put(key, asdict(chat))
                        chat_updates.append(enum_to_str(asdict(chat)))
                else:
                    chat = ChatListItem(
                        id=jid,
                        name=info["name"],
                        photo=info["photo"],
                        last_message="",
                        date="",
                        last_message_timestamp=0,
                        read_receipt=ReadReceipt.NONE,
                        unread_count=0,
                        is_group=False,
                        muted=muted,
                    )
                    kv.put(key, asdict(chat))
                    chat_updates.append(enum_to_str(asdict(chat)))

    def _sync_groups(self, chat_updates: list[dict[str, Any]]) -> None:
        reply = DaemonRPC().get_groups()
        groups = {}
        for g in reply.Groups:
            if g.jid and g.name:
                photo = ""
                if g.avatar_path:
                    photo = "file://" + g.avatar_path
                groups[g.jid] = {"name": g.name, "photo": photo}

        if not groups:
            return

        with KV() as kv:
            existing = {key: value for key, value in kv.get_partial("chat:")}

            for jid, info in groups.items():
                key = f"chat:{jid}"
                muted = self._is_muted(jid)
                if key in existing:
                    chat = ChatListItem(**existing[key])
                    changed = False
                    if chat.name != info["name"]:
                        chat.name = info["name"]
                        changed = True
                    if chat.photo != info["photo"]:
                        chat.photo = info["photo"]
                        changed = True
                    if chat.muted != muted:
                        chat.muted = muted
                        changed = True
                    if changed:
                        kv.put(key, asdict(chat))
                        chat_updates.append(enum_to_str(asdict(chat)))
                else:
                    chat = ChatListItem(
                        id=jid,
                        name=info["name"],
                        photo=info["photo"],
                        last_message="",
                        date="",
                        last_message_timestamp=0,
                        read_receipt=ReadReceipt.NONE,
                        unread_count=0,
                        is_group=True,
                        muted=muted,
                    )
                    kv.put(key, asdict(chat))
                    chat_updates.append(enum_to_str(asdict(chat)))
