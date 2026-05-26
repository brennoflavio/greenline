import time
from dataclasses import asdict
from datetime import timedelta
from typing import Any, Dict, Optional

from greenline import qml_events
from greenline.contracts.daemon import daemon_client
from greenline.events.handlers import dispatch_event
from greenline.events.session import LAST_EVENT_ID_KEY
from greenline.store.identity import (
    canonicalize_contact_jid,
    remember_chat,
    update_chat_name,
)
from greenline.ui import dataclass_to_ui_dict
from models import ChatListItem, ReadReceipt
from rpc import DaemonNotReadyError, DaemonTimeoutError, RateLimitError
from ut_components.event import Event
from ut_components.kv import KV


def process_events_once(batch_limit: int = 50) -> None:
    try:
        with KV() as kv:
            last_id = kv.get(LAST_EVENT_ID_KEY, default=0)

        reply = daemon_client().list_events(after_id=last_id, limit=batch_limit)
        if not reply.Events:
            return

        max_id = last_id
        chat_updates: dict[str, dict[str, Any]] = {}
        message_upserts: list[dict[str, Any]] = []
        message_updates: list[dict[str, Any]] = []
        photo_updates: list[dict[str, str]] = []
        presence_updates: list[dict[str, Any]] = []
        chat_presence_updates: list[dict[str, Any]] = []
        for event in reply.Events:
            dispatch_event(
                event,
                chat_updates,
                message_upserts,
                message_updates,
                photo_updates,
                presence_updates,
                chat_presence_updates,
            )
            if event.id > max_id:
                max_id = event.id

        if max_id > last_id:
            daemon_client().delete_events(up_to_id=max_id)
            with KV() as kv:
                kv.put(LAST_EVENT_ID_KEY, max_id)
    except (ConnectionRefusedError, DaemonNotReadyError, DaemonTimeoutError):
        return


class DaemonEventHandler(Event):
    def __init__(self) -> None:
        super().__init__(id="daemon-event", execution_interval=timedelta(seconds=2))

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> None:
        try:
            return self._do_trigger()
        except (ConnectionRefusedError, DaemonNotReadyError, DaemonTimeoutError):
            return None

    def _do_trigger(self) -> None:
        batch_limit = 500
        syncing = False

        with KV() as kv:
            last_id = kv.get(LAST_EVENT_ID_KEY, default=0)

        try:
            while True:
                reply = daemon_client().list_events(after_id=last_id, limit=batch_limit)
                if not reply.Events:
                    break

                if not syncing:
                    syncing = True
                    qml_events.emit_sync_status(True)

                max_id = last_id
                chat_updates: dict[str, dict[str, Any]] = {}
                message_upserts: list[dict[str, Any]] = []
                message_updates: list[dict[str, Any]] = []
                photo_updates: list[dict[str, str]] = []
                presence_updates: list[dict[str, Any]] = []
                chat_presence_updates: list[dict[str, Any]] = []
                for event in reply.Events:
                    dispatch_event(
                        event,
                        chat_updates,
                        message_upserts,
                        message_updates,
                        photo_updates,
                        presence_updates,
                        chat_presence_updates,
                    )
                    if event.id > max_id:
                        max_id = event.id

                all_message_upserts = message_upserts + message_updates
                if all_message_upserts:
                    qml_events.emit_message_upsert(all_message_upserts)

                if chat_updates:
                    qml_events.emit_chat_list_update(chat_updates.values())

                if photo_updates:
                    qml_events.emit_sender_photo_update(photo_updates)

                if presence_updates:
                    qml_events.emit_presence_update(presence_updates)

                if chat_presence_updates:
                    qml_events.emit_chat_presence(chat_presence_updates)

                if max_id > last_id:
                    daemon_client().delete_events(up_to_id=max_id)
                    with KV() as kv:
                        kv.put(LAST_EVENT_ID_KEY, max_id)
                    last_id = max_id

                if len(reply.Events) < batch_limit:
                    break
        finally:
            if syncing:
                qml_events.emit_sync_status(False)

        return None


class ChatListUpdateEvent(Event):
    def __init__(self) -> None:
        super().__init__(id="chat-list-update", execution_interval=timedelta(seconds=30))

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> None:
        chat_updates: list[dict[str, Any]] = []
        photo_updates: list[dict[str, str]] = []

        try:
            self._sync_contacts(chat_updates, photo_updates)
        except (RateLimitError, ConnectionRefusedError, DaemonNotReadyError, DaemonTimeoutError):
            return None

        try:
            self._sync_groups(chat_updates, photo_updates)
        except (RateLimitError, ConnectionRefusedError, DaemonNotReadyError, DaemonTimeoutError):
            pass

        if chat_updates:
            qml_events.emit_chat_list_update(chat_updates)

        if photo_updates:
            qml_events.emit_sender_photo_update(photo_updates)

        return None

    @staticmethod
    def _is_muted(jid: str) -> bool:
        try:
            reply = daemon_client().get_chat_settings(jid)
            return bool(reply.MutedUntil != 0)
        except Exception:
            return False

    def _sync_contacts(self, chat_updates: list[dict[str, Any]], photo_updates: list[dict[str, str]]) -> None:
        reply = daemon_client().get_contacts()
        if not reply.Contacts:
            return

        now = int(time.time())

        with KV() as kv:
            existing = {key: value for key, value in kv.get_partial("chat:")}

            for contact in reply.Contacts:
                if not contact.jid:
                    continue
                jid = canonicalize_contact_jid(contact.jid)
                key = f"chat:{jid}"
                photo = ("file://" + contact.avatar_path) if contact.avatar_path else ""
                display_name = contact.full_name or contact.push_name or contact.business_name or jid
                muted = self._is_muted(jid)

                if key in existing:
                    chat = ChatListItem(**existing[key])
                    changed = update_chat_name(
                        chat,
                        now,
                        full_name=contact.full_name,
                        push_name=contact.push_name,
                        business_name=contact.business_name,
                    )
                    if chat.photo != photo:
                        chat.photo = photo
                        changed = True
                        photo_updates.append({"jid": jid, "photo": photo})
                    if chat.muted != muted:
                        chat.muted = muted
                        changed = True
                    if changed:
                        kv.put(key, asdict(chat))
                        remember_chat(chat)
                        chat_updates.append(dataclass_to_ui_dict(chat))
                else:
                    chat = ChatListItem(
                        id=jid,
                        name=display_name,
                        photo=photo,
                        last_message="",
                        date="",
                        last_message_timestamp=0,
                        read_receipt=ReadReceipt.NONE,
                        unread_count=0,
                        is_group=False,
                        muted=muted,
                        full_name=contact.full_name,
                        push_name=contact.push_name,
                        business_name=contact.business_name,
                        name_updated_at=now,
                    )
                    kv.put(key, asdict(chat))
                    remember_chat(chat)
                    chat_updates.append(dataclass_to_ui_dict(chat))

    def _sync_groups(self, chat_updates: list[dict[str, Any]], photo_updates: list[dict[str, str]]) -> None:
        reply = daemon_client().get_groups()
        if not reply.Groups:
            return

        now = int(time.time())

        with KV() as kv:
            existing = {key: value for key, value in kv.get_partial("chat:")}

            for group in reply.Groups:
                if not group.jid or not group.name:
                    continue
                jid = canonicalize_contact_jid(group.jid)
                key = f"chat:{jid}"
                photo = ("file://" + group.avatar_path) if group.avatar_path else ""
                muted = self._is_muted(jid)

                if key in existing:
                    chat = ChatListItem(**existing[key])
                    changed = False
                    if chat.name != group.name:
                        chat.name = group.name
                        chat.name_updated_at = now
                        changed = True
                    if chat.photo != photo:
                        chat.photo = photo
                        changed = True
                        photo_updates.append({"jid": jid, "photo": photo})
                    if chat.muted != muted:
                        chat.muted = muted
                        changed = True
                    if changed:
                        kv.put(key, asdict(chat))
                        remember_chat(chat)
                        chat_updates.append(dataclass_to_ui_dict(chat))
                else:
                    chat = ChatListItem(
                        id=jid,
                        name=group.name,
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
                    remember_chat(chat)
                    chat_updates.append(dataclass_to_ui_dict(chat))
