"""Shared bridge for app-level events emitted from Python to QML."""

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Mapping

from greenline import qml_payloads
from greenline.contracts.qml import validate_qml_event
from greenline.store.identity import get_own_jid
from models import ChatListItem, Message, MessageReactionUpdate


def _send(event_name: str, payload: Any) -> None:
    validate_qml_event(event_name, payload)

    import pyotherside

    pyotherside.send(event_name, payload)


def _mapping_payload(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Unsupported QML payload type: {type(value).__name__}")


def message_upsert_payload(messages: Iterable[Message | Mapping[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in messages:
        if type(message) is Message:
            payloads.append(qml_payloads.ui_message(message))
        else:
            payloads.append(qml_payloads.stored_ui_message(_mapping_payload(message)))
    return payloads


def chat_list_update_payload(chats: Iterable[ChatListItem | Mapping[str, Any]]) -> list[dict[str, Any]]:
    own_jid = get_own_jid()
    payloads: list[dict[str, Any]] = []
    for chat in chats:
        chat_id = chat.id if type(chat) is ChatListItem else str(_mapping_payload(chat).get("id") or "")
        if own_jid and chat_id == own_jid:
            continue
        if type(chat) is ChatListItem:
            payloads.append(qml_payloads.ui_chat(chat))
        else:
            payloads.append(qml_payloads.stored_ui_chat(_mapping_payload(chat)))
    return payloads


def message_reaction_update_payload(
    updates: Iterable[MessageReactionUpdate | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for update in updates:
        if type(update) is MessageReactionUpdate:
            payloads.append(qml_payloads.ui_message_reaction_update(update))
        else:
            payloads.append(qml_payloads.stored_message_reaction_update(_mapping_payload(update)))
    return payloads


def emit_message_upsert(messages: Iterable[Message | Mapping[str, Any]]) -> None:
    _send("message-upsert", message_upsert_payload(messages))


def emit_chat_list_update(chats: Iterable[ChatListItem | Mapping[str, Any]]) -> None:
    _send("chat-list-update", chat_list_update_payload(chats))


def emit_message_reaction_update(updates: Iterable[MessageReactionUpdate | Mapping[str, Any]]) -> None:
    _send("message-reaction-update", message_reaction_update_payload(updates))


def emit_sender_photo_update(updates: Iterable[Mapping[str, Any]]) -> None:
    _send(
        "sender-photo-update",
        [
            qml_payloads.sender_photo_update(str(update.get("jid") or ""), str(update.get("photo") or ""))
            for update in updates
        ],
    )


def emit_presence_update(updates: Iterable[Mapping[str, Any]]) -> None:
    _send(
        "presence-update",
        [
            qml_payloads.presence_update(str(update.get("jid") or ""), str(update.get("status") or ""))
            for update in updates
        ],
    )


def emit_chat_presence(updates: Iterable[Mapping[str, Any]]) -> None:
    _send(
        "chat-presence",
        [
            qml_payloads.chat_presence_update(
                str(update.get("chat") or ""),
                str(update.get("sender") or ""),
                str(update.get("state") or ""),
                str(update.get("media") or ""),
                bool(update.get("is_group")),
            )
            for update in updates
        ],
    )


def emit_chat_draft_update(chat_id: str, draft: str) -> None:
    _send("chat-draft-update", [qml_payloads.chat_draft_update(chat_id, draft)])


def emit_sync_status(syncing: bool) -> None:
    _send("sync-status", bool(syncing))


def session_status_payload(logged_in: bool, qr_image_path: str) -> dict[str, Any]:
    return qml_payloads.session_status(logged_in, qr_image_path)
