"""Canonical serializers for Python payloads exposed to QML."""

from dataclasses import asdict
from typing import Any, Mapping, Sequence

from greenline.store.mentions import render_chat_mentions
from greenline.store.repository import to_ui_message
from greenline.ui import dataclass_to_ui_dict, inflate_dataclass
from models import ChatListItem, Message


def ui_message(message: Message) -> dict[str, Any]:
    return dataclass_to_ui_dict(to_ui_message(message))


def stored_ui_message(payload: Mapping[str, Any]) -> dict[str, Any]:
    return ui_message(inflate_dataclass(Message, payload))


def ui_chat(chat: ChatListItem) -> dict[str, Any]:
    return dataclass_to_ui_dict(render_chat_mentions(chat))


def stored_ui_chat(payload: Mapping[str, Any]) -> dict[str, Any]:
    return ui_chat(inflate_dataclass(ChatListItem, payload))


def chat_draft_update(chat_id: str, draft: str) -> dict[str, Any]:
    return {"id": chat_id, "draft": draft, "has_draft": draft != ""}


def sender_photo_update(jid: str, photo: str) -> dict[str, str]:
    return {"jid": jid, "photo": photo}


def presence_update(jid: str, status: str) -> dict[str, str]:
    return {"jid": jid, "status": status}


def chat_presence_update(
    chat: str,
    sender: str,
    state: str,
    media: str,
    is_group: bool,
) -> dict[str, Any]:
    return {
        "chat": chat,
        "sender": sender,
        "state": state,
        "media": media,
        "is_group": is_group,
    }


def session_status(logged_in: bool, qr_image_path: str) -> dict[str, Any]:
    return {"logged_in": logged_in, "qr_image_path": qr_image_path}


def dataclass_payload(value: Any) -> dict[str, Any]:
    return dataclass_to_ui_dict(value)


def dataclass_payloads(values: Sequence[Any]) -> list[dict[str, Any]]:
    return [dataclass_to_ui_dict(value) for value in values]


def dataclass_asdict(value: Any) -> dict[str, Any]:
    return asdict(value)
