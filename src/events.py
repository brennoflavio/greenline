import base64
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pyotherside
from dacite import from_dict

from history_sync import handle_history_sync
from message_store import store_message, update_chat_name
from models import ChatListItem, Message, MessageType, ReadReceipt
from receipt_store import process_receipt
from rpc import DaemonNotReadyError, DaemonRPC, RateLimitError
from ut_components.config import get_cache_path
from ut_components.event import Event
from ut_components.kv import KV
from ut_components.utils import enum_to_str as _enum_to_str
from whatsmeow_types import (
    BusinessNameEvent,
    ContactEvent,
    MessageEvent,
    PictureEvent,
    PresenceEvent,
    PushNameEvent,
    ReceiptEvent,
)


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
        try:
            result = DaemonRPC().get_session_status()
        except (ConnectionRefusedError, DaemonNotReadyError):
            return None
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


def _auto_download_sticker(msg: Message, raw: Dict[str, Any]) -> str:
    msg_content = raw.get("Message", {})
    sticker = msg_content.get("stickerMessage")
    if not sticker:
        return ""

    direct_path = sticker.get("directPath", "")
    media_key = sticker.get("mediaKey", "")
    if not direct_path or not media_key:
        return ""

    file_sha256 = sticker.get("fileSHA256", "")
    if file_sha256:
        cache_key = f"sticker_cache:{file_sha256}"
        with KV() as kv:
            cached_path = kv.get(cache_key)
        if cached_path and os.path.exists(str(cached_path)):
            media_path = "file://" + str(cached_path)
            key = f"message:{msg.chat_id}:{msg.timestamp_unix}:{msg.id}"
            with KV() as kv:
                entry = kv.get(key)
                if entry:
                    entry["media_path"] = media_path
                    kv.put(key, entry)
            return media_path

    try:
        file_path = DaemonRPC().download_media(
            direct_path=direct_path,
            media_key=media_key,
            file_enc_sha256=sticker.get("fileEncSHA256", ""),
            file_sha256=file_sha256,
            file_length=sticker.get("fileLength", 0),
            media_type="sticker",
            mimetype=sticker.get("mimetype", ""),
            message_id=msg.id,
            chat_id=msg.chat_id,
        )
    except Exception:
        return ""

    if file_sha256:
        with KV() as kv:
            kv.put(f"sticker_cache:{file_sha256}", file_path)

    media_path = "file://" + str(file_path)
    key = f"message:{msg.chat_id}:{msg.timestamp_unix}:{msg.id}"
    with KV() as kv:
        entry = kv.get(key)
        if entry:
            entry["media_path"] = media_path
            kv.put(key, entry)

    return media_path


def _handle_message(
    event: Any,
    chat_updates: dict[str, dict[str, Any]],
    message_upserts: list[dict[str, Any]],
) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=MessageEvent, data=raw)
    if evt.Info.Chat == STATUS_BROADCAST_JID:
        return
    evt.Info.Chat = DaemonRPC().ensure_jid(evt.Info.Chat)
    stored = store_message(evt, raw=raw)
    if stored is None:
        _save_unhandled_message(event, raw)
        return
    if stored.message.type == MessageType.STICKER:
        media_path = _auto_download_sticker(stored.message, raw)
        if media_path:
            stored.message.media_path = media_path
    if stored.message.sender and not stored.message.is_outgoing:
        with KV() as kv:
            sender_data = kv.get(f"chat:{stored.message.sender}")
        if sender_data:
            stored.message.sender_photo = sender_data.get("photo", "")
    message_upserts.append(enum_to_str(asdict(stored.message)))
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


def _handle_contact(event: Any, chat_updates: dict[str, dict[str, Any]]) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=ContactEvent, data=raw)
    jid = DaemonRPC().ensure_jid(evt.JID)
    name = evt.Action.fullName
    if not name:
        return

    ts = int(datetime.fromisoformat(evt.Timestamp).timestamp()) if evt.Timestamp else 0

    with KV() as kv:
        key = f"chat:{jid}"
        data = kv.get(key)
        if data is not None:
            chat = ChatListItem(**data)
            if update_chat_name(chat, ts, full_name=name):
                kv.put(key, asdict(chat))
                chat_updates[chat.id] = enum_to_str(asdict(chat))
        else:
            chat = ChatListItem(
                id=jid,
                name=name,
                photo="",
                last_message="",
                date="",
                last_message_timestamp=0,
                read_receipt=ReadReceipt.NONE,
                unread_count=0,
                is_group=False,
                full_name=name,
                name_updated_at=ts,
            )
            kv.put(key, asdict(chat))
            chat_updates[chat.id] = enum_to_str(asdict(chat))


def _handle_push_name(event: Any, chat_updates: dict[str, dict[str, Any]]) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=PushNameEvent, data=raw)
    jid = DaemonRPC().ensure_jid(evt.JID)
    if not evt.NewPushName:
        return

    ts = int(datetime.fromisoformat(evt.Message.Timestamp).timestamp()) if evt.Message.Timestamp else 0

    with KV() as kv:
        key = f"chat:{jid}"
        data = kv.get(key)
        if data is not None:
            chat = ChatListItem(**data)
            if update_chat_name(chat, ts, push_name=evt.NewPushName):
                kv.put(key, asdict(chat))
                chat_updates[chat.id] = enum_to_str(asdict(chat))


def _handle_business_name(event: Any, chat_updates: dict[str, dict[str, Any]]) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=BusinessNameEvent, data=raw)
    jid = DaemonRPC().ensure_jid(evt.JID)
    if not evt.NewBusinessName:
        return

    ts = int(datetime.fromisoformat(evt.Message.Timestamp).timestamp()) if evt.Message.Timestamp else 0

    with KV() as kv:
        key = f"chat:{jid}"
        data = kv.get(key)
        if data is not None:
            chat = ChatListItem(**data)
            if update_chat_name(chat, ts, business_name=evt.NewBusinessName):
                kv.put(key, asdict(chat))
                chat_updates[chat.id] = enum_to_str(asdict(chat))


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


def _handle_picture(
    event: Any,
    chat_updates: dict[str, dict[str, Any]],
    photo_updates: list[dict[str, str]],
) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=PictureEvent, data=raw)
    jid = DaemonRPC().ensure_jid(evt.JID)
    if not jid:
        return

    avatar_path = DaemonRPC().sync_avatar(jid)
    photo = "file://" + avatar_path if avatar_path else ""

    with KV() as kv:
        key = f"chat:{jid}"
        data = kv.get(key)
        if data is None:
            return
        chat = ChatListItem(**data)
        if chat.photo != photo:
            chat.photo = photo
            kv.put(key, asdict(chat))
            chat_updates[chat.id] = enum_to_str(asdict(chat))
            photo_updates.append({"jid": jid, "photo": photo})


def _format_presence_status(available: bool, last_seen: str) -> str:
    if available:
        return "online"
    if not last_seen or last_seen.startswith("0001-01-01"):
        return "offline"
    try:
        dt = datetime.fromisoformat(last_seen)
        now = datetime.now(dt.tzinfo)
        diff = (now - dt).total_seconds()
        if diff < 60:
            return "last seen just now"
        if diff < 3600:
            return f"last seen {int(diff // 60)} min ago"
        if diff < 86400:
            return f"last seen {int(diff // 3600)} h ago"
        return f"last seen {dt.strftime('%b %d')}"
    except (ValueError, TypeError):
        return "offline"


def _handle_presence(
    event: Any,
    presence_updates: list[dict[str, Any]],
) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=PresenceEvent, data=raw)
    jid = DaemonRPC().ensure_jid(evt.From)
    if not jid:
        return
    presence_updates.append(
        {
            "jid": jid,
            "status": _format_presence_status(not evt.Unavailable, evt.LastSeen),
        }
    )


def _save_unhandled_message(event: Any, raw: Dict[str, Any]) -> None:
    info = raw.get("Info", {})
    with KV() as kv:
        kv.put(
            f"unhandled_message:{event.id}",
            {
                "event_id": event.id,
                "info_type": info.get("Type", ""),
                "media_type": info.get("MediaType", ""),
                "chat": info.get("Chat", ""),
                "sender": info.get("Sender", ""),
                "message_id": info.get("ID", ""),
                "timestamp": info.get("Timestamp", ""),
                "payload": event.payload or "",
            },
        )


def _handle_unknown(event: Any) -> None:
    with KV() as kv:
        kv.put(
            f"unknown_event:{event.event_type}:{event.id}",
            {
                "event_type": event.event_type,
                "payload": event.payload or "",
            },
        )


def _dispatch_event(
    event: Any,
    chat_updates: dict[str, dict[str, Any]],
    message_upserts: list[dict[str, Any]],
    message_updates: list[dict[str, Any]],
    photo_updates: list[dict[str, str]],
    presence_updates: list[dict[str, Any]],
) -> None:
    try:
        _dispatch_event_inner(
            event,
            chat_updates,
            message_upserts,
            message_updates,
            photo_updates,
            presence_updates,
        )
    except (ConnectionRefusedError, DaemonNotReadyError):
        raise
    except Exception:
        _handle_unknown(event)


def _dispatch_event_inner(
    event: Any,
    chat_updates: dict[str, dict[str, Any]],
    message_upserts: list[dict[str, Any]],
    message_updates: list[dict[str, Any]],
    photo_updates: list[dict[str, str]],
    presence_updates: list[dict[str, Any]],
) -> None:
    if event.event_type == "Message":
        _handle_message(event, chat_updates, message_upserts)
    elif event.event_type == "Receipt":
        _handle_receipt(event, chat_updates, message_updates)
    elif event.event_type == "Contact":
        _handle_contact(event, chat_updates)
    elif event.event_type == "Mute":
        _handle_mute(event, chat_updates)
    elif event.event_type == "Picture":
        _handle_picture(event, chat_updates, photo_updates)
    elif event.event_type == "PushName":
        _handle_push_name(event, chat_updates)
    elif event.event_type == "BusinessName":
        _handle_business_name(event, chat_updates)
    elif event.event_type == "Presence":
        _handle_presence(event, presence_updates)
    elif event.event_type == "HistorySync":
        updated = handle_history_sync(event)
        chat_updates.update(updated)
    elif event.event_type in (
        "AppState",
        "AppStateSyncComplete",
        "AppStateSyncError",
        "Connected",
        "KeepAliveTimeout",
        "OfflineSyncCompleted",
        "OfflineSyncPreview",
        "PairSuccess",
        "QR",
    ):
        pass
    else:
        _handle_unknown(event)


def process_events_once(batch_limit: int = 50) -> None:
    try:
        with KV() as kv:
            last_id = kv.get(LAST_EVENT_ID_KEY, default=0)

        reply = DaemonRPC().list_events(after_id=last_id, limit=batch_limit)
        if not reply.Events:
            return

        max_id = last_id
        chat_updates: dict[str, dict[str, Any]] = {}
        message_upserts: list[dict[str, Any]] = []
        message_updates: list[dict[str, Any]] = []
        photo_updates: list[dict[str, str]] = []
        presence_updates: list[dict[str, Any]] = []
        for event in reply.Events:
            _dispatch_event(
                event,
                chat_updates,
                message_upserts,
                message_updates,
                photo_updates,
                presence_updates,
            )
            if event.id > max_id:
                max_id = event.id

        if max_id > last_id:
            DaemonRPC().delete_events(up_to_id=max_id)
            with KV() as kv:
                kv.put(LAST_EVENT_ID_KEY, max_id)
    except (ConnectionRefusedError, DaemonNotReadyError):
        return


class DaemonEventHandler(Event):
    def __init__(self) -> None:
        super().__init__(id="daemon-event", execution_interval=timedelta(seconds=2))

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> None:
        try:
            return self._do_trigger()
        except (ConnectionRefusedError, DaemonNotReadyError):
            return None

    def _do_trigger(self) -> None:
        batch_limit = 500
        syncing = False

        with KV() as kv:
            last_id = kv.get(LAST_EVENT_ID_KEY, default=0)

        try:
            while True:
                reply = DaemonRPC().list_events(after_id=last_id, limit=batch_limit)
                if not reply.Events:
                    break

                if not syncing:
                    syncing = True
                    pyotherside.send("sync-status", True)

                max_id = last_id
                chat_updates: dict[str, dict[str, Any]] = {}
                message_upserts: list[dict[str, Any]] = []
                message_updates: list[dict[str, Any]] = []
                photo_updates: list[dict[str, str]] = []
                presence_updates: list[dict[str, Any]] = []
                for event in reply.Events:
                    _dispatch_event(
                        event,
                        chat_updates,
                        message_upserts,
                        message_updates,
                        photo_updates,
                        presence_updates,
                    )
                    if event.id > max_id:
                        max_id = event.id

                all_message_upserts = message_upserts + message_updates
                if all_message_upserts:
                    pyotherside.send("message-upsert", all_message_upserts)

                if chat_updates:
                    pyotherside.send("chat-list-update", list(chat_updates.values()))

                if photo_updates:
                    pyotherside.send("sender-photo-update", photo_updates)

                if presence_updates:
                    pyotherside.send("presence-update", presence_updates)

                if max_id > last_id:
                    DaemonRPC().delete_events(up_to_id=max_id)
                    with KV() as kv:
                        kv.put(LAST_EVENT_ID_KEY, max_id)
                    last_id = max_id

                if len(reply.Events) < batch_limit:
                    break
        finally:
            if syncing:
                pyotherside.send("sync-status", False)

        return None


class ChatListUpdateEvent(Event):
    def __init__(self) -> None:
        super().__init__(id="chat-list-update", execution_interval=timedelta(seconds=30))

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> None:
        chat_updates: list[dict[str, Any]] = []
        photo_updates: list[dict[str, str]] = []

        try:
            self._sync_contacts(chat_updates, photo_updates)
            self._sync_groups(chat_updates, photo_updates)
        except (RateLimitError, ConnectionRefusedError, DaemonNotReadyError):
            return None

        if chat_updates:
            pyotherside.send("chat-list-update", chat_updates)

        if photo_updates:
            pyotherside.send("sender-photo-update", photo_updates)

        return None

    @staticmethod
    def _is_muted(jid: str) -> bool:
        try:
            reply = DaemonRPC().get_chat_settings(jid)
            return reply.MutedUntil != 0
        except Exception:
            return False

    def _sync_contacts(self, chat_updates: list[dict[str, Any]], photo_updates: list[dict[str, str]]) -> None:
        reply = DaemonRPC().get_contacts()
        if not reply.Contacts:
            return

        now = int(time.time())

        with KV() as kv:
            existing = {key: value for key, value in kv.get_partial("chat:")}

            for c in reply.Contacts:
                if not c.jid:
                    continue
                key = f"chat:{c.jid}"
                photo = ("file://" + c.avatar_path) if c.avatar_path else ""
                display_name = c.full_name or c.push_name or c.business_name or c.jid
                muted = self._is_muted(c.jid)

                if key in existing:
                    chat = ChatListItem(**existing[key])
                    changed = update_chat_name(
                        chat,
                        now,
                        full_name=c.full_name,
                        push_name=c.push_name,
                        business_name=c.business_name,
                    )
                    if chat.photo != photo:
                        chat.photo = photo
                        changed = True
                        photo_updates.append({"jid": c.jid, "photo": photo})
                    if chat.muted != muted:
                        chat.muted = muted
                        changed = True
                    if changed:
                        kv.put(key, asdict(chat))
                        chat_updates.append(enum_to_str(asdict(chat)))
                else:
                    chat = ChatListItem(
                        id=c.jid,
                        name=display_name,
                        photo=photo,
                        last_message="",
                        date="",
                        last_message_timestamp=0,
                        read_receipt=ReadReceipt.NONE,
                        unread_count=0,
                        is_group=False,
                        muted=muted,
                        full_name=c.full_name,
                        push_name=c.push_name,
                        business_name=c.business_name,
                        name_updated_at=now,
                    )
                    kv.put(key, asdict(chat))
                    chat_updates.append(enum_to_str(asdict(chat)))

    def _sync_groups(self, chat_updates: list[dict[str, Any]], photo_updates: list[dict[str, str]]) -> None:
        reply = DaemonRPC().get_groups()
        if not reply.Groups:
            return

        now = int(time.time())

        with KV() as kv:
            existing = {key: value for key, value in kv.get_partial("chat:")}

            for g in reply.Groups:
                if not g.jid or not g.name:
                    continue
                key = f"chat:{g.jid}"
                photo = ("file://" + g.avatar_path) if g.avatar_path else ""
                muted = self._is_muted(g.jid)

                if key in existing:
                    chat = ChatListItem(**existing[key])
                    changed = False
                    if chat.name != g.name:
                        chat.name = g.name
                        chat.name_updated_at = now
                        changed = True
                    if chat.photo != photo:
                        chat.photo = photo
                        changed = True
                        photo_updates.append({"jid": g.jid, "photo": photo})
                    if chat.muted != muted:
                        chat.muted = muted
                        changed = True
                    if changed:
                        kv.put(key, asdict(chat))
                        chat_updates.append(enum_to_str(asdict(chat)))
                else:
                    chat = ChatListItem(
                        id=g.jid,
                        name=g.name,
                        photo=photo,
                        last_message="",
                        date="",
                        last_message_timestamp=0,
                        read_receipt=ReadReceipt.NONE,
                        unread_count=0,
                        is_group=True,
                        muted=muted,
                        name_updated_at=now,
                    )
                    kv.put(key, asdict(chat))
                    chat_updates.append(enum_to_str(asdict(chat)))
