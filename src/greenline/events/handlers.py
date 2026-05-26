import json
import os
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict

from dacite import from_dict

from constants import NEWSLETTER_SERVER, STATUS_BROADCAST_JID
from greenline import qml_payloads
from greenline.contracts.daemon import daemon_client
from greenline.store.identity import (
    canonicalize_contact_jid,
    remember_chat,
    update_chat_name,
)
from greenline.store.messages import store_message, store_undecryptable_message
from greenline.store.repository import sanitize_message_payload
from greenline.ui import dataclass_to_ui_dict, enum_to_str
from history_sync import handle_history_sync
from models import ChatListItem, Message, MessageType, ReadReceipt
from receipt_store import process_receipt
from rpc import DaemonNotReadyError, DaemonTimeoutError
from unread_counter import reconcile_unread_total
from ut_components.kv import KV
from whatsmeow_types import (
    BlocklistEvent,
    BusinessNameEvent,
    CallRejectEvent,
    ChatPresenceEvent,
    ContactEvent,
    GroupInfoEvent,
    IdentityChangeEvent,
    JoinedGroupEvent,
    MessageEvent,
    PictureEvent,
    PresenceEvent,
    PushNameEvent,
    ReceiptEvent,
    UndecryptableMessageEvent,
    UserAboutEvent,
)


def render_message_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return qml_payloads.stored_ui_message(payload)


def render_chat_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return qml_payloads.stored_ui_chat(payload)


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
                    kv.put(key, sanitize_message_payload(entry))
            return media_path

    try:
        file_path = daemon_client().download_media(
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
            kv.put(key, sanitize_message_payload(entry))

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
    if evt.Info.Chat.endswith(NEWSLETTER_SERVER):
        return
    evt.Info.Chat = canonicalize_contact_jid(daemon_client().ensure_jid(evt.Info.Chat))
    if evt.Info.SenderAlt:
        evt.Info.Sender = canonicalize_contact_jid(daemon_client().ensure_jid(evt.Info.SenderAlt))
    elif evt.Info.Sender:
        evt.Info.Sender = canonicalize_contact_jid(daemon_client().ensure_jid(evt.Info.Sender))
    stored = store_message(evt, raw=raw)
    if stored is None:
        _save_unhandled_message(event, raw)
        return
    if stored.message.type == MessageType.STICKER:
        media_path = _auto_download_sticker(stored.message, raw)
        if media_path:
            stored.message.media_path = media_path
    message_upserts.append(dataclass_to_ui_dict(stored.message))
    chat_updates[stored.chat.id] = dataclass_to_ui_dict(stored.chat)


def _handle_undecryptable_message(
    event: Any,
    chat_updates: dict[str, dict[str, Any]],
    message_upserts: list[dict[str, Any]],
) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=UndecryptableMessageEvent, data=raw)
    if evt.Info.Chat == STATUS_BROADCAST_JID:
        return
    if evt.Info.Chat.endswith(NEWSLETTER_SERVER):
        return
    evt.Info.Chat = canonicalize_contact_jid(daemon_client().ensure_jid(evt.Info.Chat))
    if evt.Info.SenderAlt:
        evt.Info.Sender = canonicalize_contact_jid(daemon_client().ensure_jid(evt.Info.SenderAlt))
    elif evt.Info.Sender:
        evt.Info.Sender = canonicalize_contact_jid(daemon_client().ensure_jid(evt.Info.Sender))
    stored = store_undecryptable_message(evt, raw=raw)
    if stored is None:
        _save_unhandled_message(event, raw)
        return
    message_upserts.append(dataclass_to_ui_dict(stored.message))
    chat_updates[stored.chat.id] = dataclass_to_ui_dict(stored.chat)


def _handle_receipt(
    event: Any,
    chat_updates: dict[str, dict[str, Any]],
    message_updates: list[dict[str, Any]],
) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=ReceiptEvent, data=raw)
    evt.Chat = canonicalize_contact_jid(daemon_client().ensure_jid(evt.Chat))
    updated_messages, updated_chat = process_receipt(evt)
    for msg in updated_messages:
        message_updates.append(enum_to_str(msg))
    if updated_chat is not None:
        chat_updates[updated_chat.id] = dataclass_to_ui_dict(updated_chat)


def _handle_contact(event: Any, chat_updates: dict[str, dict[str, Any]]) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=ContactEvent, data=raw)
    jid = canonicalize_contact_jid(daemon_client().ensure_jid(evt.JID))
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
                remember_chat(chat)
                chat_updates[chat.id] = dataclass_to_ui_dict(chat)
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
            remember_chat(chat)
            chat_updates[chat.id] = dataclass_to_ui_dict(chat)


def _handle_push_name(event: Any, chat_updates: dict[str, dict[str, Any]]) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=PushNameEvent, data=raw)
    jid = canonicalize_contact_jid(daemon_client().ensure_jid(evt.JID))
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
                remember_chat(chat)
                chat_updates[chat.id] = dataclass_to_ui_dict(chat)


def _handle_business_name(event: Any, chat_updates: dict[str, dict[str, Any]]) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=BusinessNameEvent, data=raw)
    jid = canonicalize_contact_jid(daemon_client().ensure_jid(evt.JID))
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
                remember_chat(chat)
                chat_updates[chat.id] = dataclass_to_ui_dict(chat)


def _handle_mute(event: Any, chat_updates: dict[str, dict[str, Any]]) -> None:
    raw = json.loads(event.payload or "{}")
    jid = raw.get("JID", "")
    if not jid:
        return
    jid = canonicalize_contact_jid(daemon_client().ensure_jid(jid))
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
            chat_updates[chat.id] = dataclass_to_ui_dict(chat)


def _handle_picture(
    event: Any,
    chat_updates: dict[str, dict[str, Any]],
    photo_updates: list[dict[str, str]],
) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=PictureEvent, data=raw)
    jid = canonicalize_contact_jid(daemon_client().ensure_jid(evt.JID))
    if not jid:
        return

    avatar_path = daemon_client().sync_avatar(jid).AvatarPath
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
            remember_chat(chat)
            chat_updates[chat.id] = dataclass_to_ui_dict(chat)
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
    jid = daemon_client().ensure_jid(evt.From)
    if not jid:
        return
    presence_updates.append(
        {
            "jid": jid,
            "status": _format_presence_status(not evt.Unavailable, evt.LastSeen),
        }
    )


def _handle_chat_presence(
    event: Any,
    chat_presence_updates: list[dict[str, Any]],
) -> None:
    raw = json.loads(event.payload or "{}")
    evt = from_dict(data_class=ChatPresenceEvent, data=raw)
    if evt.IsFromMe:
        return
    jid = daemon_client().ensure_jid(evt.Chat)
    if not jid:
        return
    chat_presence_updates.append(
        {
            "chat": jid,
            "sender": evt.Sender,
            "state": evt.State,
            "media": evt.Media,
            "is_group": evt.IsGroup,
        }
    )


def _handle_group_info(event: Any) -> None:
    _parse_ignored_event(event, GroupInfoEvent)


def _parse_ignored_event(event: Any, data_class: Any) -> None:
    raw = json.loads(event.payload or "{}")
    from_dict(data_class=data_class, data=raw)


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


def dispatch_event(
    event: Any,
    chat_updates: dict[str, dict[str, Any]],
    message_upserts: list[dict[str, Any]],
    message_updates: list[dict[str, Any]],
    photo_updates: list[dict[str, str]],
    presence_updates: list[dict[str, Any]],
    chat_presence_updates: list[dict[str, Any]],
) -> None:
    try:
        _dispatch_event_inner(
            event,
            chat_updates,
            message_upserts,
            message_updates,
            photo_updates,
            presence_updates,
            chat_presence_updates,
        )
    except (ConnectionRefusedError, DaemonNotReadyError, DaemonTimeoutError):
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
    chat_presence_updates: list[dict[str, Any]],
) -> None:
    if event.event_type == "Message":
        _handle_message(event, chat_updates, message_upserts)
    elif event.event_type == "Receipt":
        _handle_receipt(event, chat_updates, message_updates)
    elif event.event_type == "UndecryptableMessage":
        _handle_undecryptable_message(event, chat_updates, message_upserts)
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
    elif event.event_type == "ChatPresence":
        _handle_chat_presence(event, chat_presence_updates)
    elif event.event_type == "HistorySync":
        updated = handle_history_sync(event)
        chat_updates.update(updated)
        reconcile_unread_total()
    elif event.event_type == "GroupInfo":
        _handle_group_info(event)
    elif event.event_type == "Blocklist":
        _parse_ignored_event(event, BlocklistEvent)
    elif event.event_type == "CallReject":
        _parse_ignored_event(event, CallRejectEvent)
    elif event.event_type == "IdentityChange":
        _parse_ignored_event(event, IdentityChangeEvent)
    elif event.event_type == "JoinedGroup":
        _parse_ignored_event(event, JoinedGroupEvent)
    elif event.event_type == "UserAbout":
        _parse_ignored_event(event, UserAboutEvent)
    elif event.event_type in (
        "AppState",
        "AppStateSyncComplete",
        "AppStateSyncError",
        "CallAccept",
        "CallOffer",
        "CallOfferNotice",
        "CallRelayLatency",
        "CallTerminate",
        "Connected",
        "KeepAliveRestored",
        "KeepAliveTimeout",
        "OfflineSyncCompleted",
        "OfflineSyncPreview",
        "PairError",
        "PairSuccess",
        "QR",
    ):
        pass
    else:
        _handle_unknown(event)
