import base64
import json
import os
import traceback
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Dict, Optional

import pyotherside
from dacite import from_dict

from message_store import store_message
from models import ChatListItem, ReadReceipt
from rpc import DaemonRPC
from ut_components.config import get_cache_path
from ut_components.event import Event
from ut_components.kv import KV
from ut_components.utils import enum_to_str as _enum_to_str
from whatsmeow_types import MessageEvent


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


class NewMessageEvent(Event):
    def __init__(self) -> None:
        super().__init__(id="new-message", execution_interval=timedelta(seconds=2))

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> None:
        with KV() as kv:
            last_id = kv.get(LAST_EVENT_ID_KEY, default=0)

        reply = DaemonRPC().list_events(after_id=last_id)
        if not reply.Events:
            return None

        max_id = last_id
        chat_updates: dict[str, dict[str, Any]] = {}
        for event in reply.Events:
            try:
                if event.event_type == "Message":
                    raw = json.loads(event.payload or "{}")
                    evt = from_dict(data_class=MessageEvent, data=raw)
                    if evt.Info.Chat == STATUS_BROADCAST_JID:
                        continue
                    stored = store_message(evt, raw=raw)
                    if stored is not None:
                        pyotherside.send("new-message", enum_to_str(asdict(stored.message)))
                        chat_updates[stored.chat.id] = enum_to_str(asdict(stored.chat))
            except Exception:
                traceback.print_exc()
            finally:
                if event.id > max_id:
                    max_id = event.id

        if chat_updates:
            pyotherside.send("chat-list-update", list(chat_updates.values()))

        if max_id > last_id:
            DaemonRPC().delete_events(up_to_id=max_id)
            with KV() as kv:
                kv.put(LAST_EVENT_ID_KEY, max_id)

        return None


class MessageStatusUpdateEvent(Event):
    def __init__(self) -> None:
        super().__init__(id="message-status-update", execution_interval=timedelta(seconds=5))

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> None:
        pass


class ChatListUpdateEvent(Event):
    def __init__(self) -> None:
        super().__init__(id="chat-list-update", execution_interval=timedelta(seconds=30))

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> None:
        reply = DaemonRPC().get_contacts()
        contacts = {}
        for c in reply.Contacts:
            if c.jid and c.display_name:
                photo = ""
                if c.avatar_path:
                    photo = "file://" + c.avatar_path
                contacts[c.jid] = {"name": c.display_name, "photo": photo}

        if not contacts:
            return None

        chat_updates: list[dict[str, Any]] = []
        with KV() as kv:
            existing = {key: value for key, value in kv.get_partial("chat:")}

            for jid, info in contacts.items():
                key = f"chat:{jid}"
                if key in existing:
                    chat = ChatListItem(**existing[key])
                    changed = False
                    if chat.name != info["name"]:
                        chat.name = info["name"]
                        changed = True
                    if chat.photo != info["photo"]:
                        chat.photo = info["photo"]
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
                        is_group=jid.endswith("@g.us"),
                    )
                    kv.put(key, asdict(chat))
                    chat_updates.append(enum_to_str(asdict(chat)))

        if chat_updates:
            pyotherside.send("chat-list-update", chat_updates)

        return None
