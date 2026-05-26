from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from contracts import qml_payloads

ReturnKind = Literal["dict", "bool", "none"]
Validator = Callable[[Any], None]


@dataclass(frozen=True)
class ApiContract:
    name: str
    validator: Validator
    return_kind: ReturnKind
    notes: str = ""


@dataclass(frozen=True)
class EventContract:
    name: str
    validator: Validator
    notes: str = ""


API_CONTRACTS: dict[str, ApiContract] = {
    "check_daemon_status": ApiContract("check_daemon_status", qml_payloads.assert_daemon_status_response, "dict"),
    "check_daemon_version": ApiContract(
        "check_daemon_version", qml_payloads.assert_ensure_daemon_version_response, "dict"
    ),
    "clear_data": ApiContract("clear_data", qml_payloads.assert_clear_data_response, "dict"),
    "delete_message": ApiContract("delete_message", qml_payloads.assert_success_response, "dict"),
    "download_media": ApiContract("download_media", qml_payloads.assert_download_media_response, "dict"),
    "edit_text_message": ApiContract("edit_text_message", qml_payloads.assert_success_response, "dict"),
    "get_cached_stickers": ApiContract("get_cached_stickers", qml_payloads.assert_cached_stickers_response, "dict"),
    "get_chat_draft": ApiContract("get_chat_draft", qml_payloads.assert_chat_draft_response, "dict"),
    "get_chat_info": ApiContract("get_chat_info", qml_payloads.assert_chat_info_response, "dict"),
    "get_chat_list": ApiContract("get_chat_list", qml_payloads.assert_chat_list_response, "dict"),
    "get_contact_list": ApiContract("get_contact_list", qml_payloads.assert_contact_list_response, "dict"),
    "get_group_mention_candidates": ApiContract(
        "get_group_mention_candidates", qml_payloads.assert_group_mention_candidates_response, "dict"
    ),
    "get_messages": ApiContract("get_messages", qml_payloads.assert_messages_response, "dict"),
    "get_phone_number": ApiContract("get_phone_number", qml_payloads.assert_phone_number_response, "dict"),
    "get_session_status": ApiContract("get_session_status", qml_payloads.assert_session_status_response, "dict"),
    "get_settings": ApiContract("get_settings", qml_payloads.assert_settings_response, "dict"),
    "get_sync_status": ApiContract(
        "get_sync_status",
        qml_payloads.assert_sync_status_response,
        "bool",
        "Returns a bare bool for list backlog state.",
    ),
    "install_daemon": ApiContract("install_daemon", qml_payloads.assert_success_response, "dict"),
    "mark_messages_as_read": ApiContract("mark_messages_as_read", qml_payloads.assert_success_response, "dict"),
    "pair_phone": ApiContract("pair_phone", qml_payloads.assert_pair_phone_response, "dict"),
    "ping_daemon": ApiContract("ping_daemon", qml_payloads.assert_success_response, "dict"),
    "send_audio_message": ApiContract("send_audio_message", qml_payloads.assert_success_response, "dict"),
    "send_contact_message": ApiContract("send_contact_message", qml_payloads.assert_success_response, "dict"),
    "send_image_message": ApiContract("send_image_message", qml_payloads.assert_success_response, "dict"),
    "send_presence": ApiContract(
        "send_presence", qml_payloads.assert_none_response, "none", "Fire-and-forget presence command."
    ),
    "send_sticker_message": ApiContract("send_sticker_message", qml_payloads.assert_success_response, "dict"),
    "send_text_message": ApiContract("send_text_message", qml_payloads.assert_success_response, "dict"),
    "send_video_message": ApiContract("send_video_message", qml_payloads.assert_success_response, "dict"),
    "set_chat_draft": ApiContract("set_chat_draft", qml_payloads.assert_success_response, "dict"),
    "set_notifications_suppressed": ApiContract(
        "set_notifications_suppressed", qml_payloads.assert_success_response, "dict"
    ),
    "start_event_loop": ApiContract(
        "start_event_loop",
        qml_payloads.assert_none_response,
        "none",
        "Registers framework Event instances; events have separate contracts.",
    ),
    "subscribe_presence": ApiContract(
        "subscribe_presence", qml_payloads.assert_none_response, "none", "Fire-and-forget presence subscription."
    ),
    "toggle_mute": ApiContract("toggle_mute", qml_payloads.assert_success_response, "dict"),
    "uninstall_daemon": ApiContract("uninstall_daemon", qml_payloads.assert_success_response, "dict"),
}

EVENT_CONTRACTS: dict[str, EventContract] = {
    "chat-draft-update": EventContract(
        "chat-draft-update", qml_payloads.assert_chat_draft_update_payload, "Lightweight draft update."
    ),
    "chat-list-update": EventContract("chat-list-update", qml_payloads.assert_chat_list_update_payload),
    "chat-presence": EventContract("chat-presence", qml_payloads.assert_chat_presence_payload),
    "message-upsert": EventContract("message-upsert", qml_payloads.assert_message_upsert_payload),
    "presence-update": EventContract("presence-update", qml_payloads.assert_presence_update_payload),
    "sender-photo-update": EventContract("sender-photo-update", qml_payloads.assert_sender_photo_update_payload),
    "session-status": EventContract(
        "session-status",
        qml_payloads.assert_session_status_response,
        "Framework dispatcher emits the dataclass as a dict.",
    ),
    "sync-status": EventContract("sync-status", qml_payloads.assert_sync_status_response),
}


def validate_api_response(name: str, payload: Any) -> None:
    API_CONTRACTS[name].validator(payload)


def validate_event_payload(name: str, payload: Any) -> None:
    EVENT_CONTRACTS[name].validator(payload)
