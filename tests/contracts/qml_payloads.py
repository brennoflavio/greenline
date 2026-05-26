from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from models import (
    ChatListEntry,
    ChatListItem,
    ContactItem,
    MessageType,
    ReadReceipt,
    UiMessage,
)

MESSAGE_TYPES = {item.value for item in MessageType}
READ_RECEIPTS = {item.value for item in ReadReceipt}

Validator = Callable[[Any], None]

UI_MESSAGE_FIELDS = {field.name for field in fields(UiMessage)}
CHAT_LIST_ITEM_FIELDS = {field.name for field in fields(ChatListItem)}
CHAT_LIST_ENTRY_FIELDS = {field.name for field in fields(ChatListEntry)}
CONTACT_ITEM_FIELDS = {field.name for field in fields(ContactItem)}


def assert_json_like(value: Any, path: str = "payload") -> None:
    if is_dataclass(value) and not isinstance(value, type):
        raise AssertionError(f"{path} is a dataclass, not QML-safe JSON-like data")
    if isinstance(value, Enum):
        raise AssertionError(f"{path} is an enum, not QML-safe JSON-like data")
    if isinstance(value, Path):
        raise AssertionError(f"{path} is a Path, not QML-safe JSON-like data")
    if value is None or type(value) in (str, int, float, bool):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            assert_json_like(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str), f"{path} has non-string key {key!r}"
            assert_json_like(item, f"{path}.{key}")
        return
    raise AssertionError(f"{path} is not QML-safe JSON-like data: {type(value).__name__}")


def _assert_dict(payload: Any, path: str) -> dict[str, Any]:
    assert_json_like(payload, path)
    assert isinstance(payload, dict), f"{path} must be an object"
    return payload


def _assert_list_of_dicts(payload: Any, path: str) -> list[dict[str, Any]]:
    assert_json_like(payload, path)
    assert isinstance(payload, list), f"{path} payload must be a list"
    for index, item in enumerate(payload):
        assert isinstance(item, dict), f"{path}[{index}] must be an object"
    return payload


def _assert_keys(payload: dict[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(payload)
    extra = set(payload) - expected
    assert not missing, f"{path} missing keys: {sorted(missing)}"
    assert not extra, f"{path} has unexpected keys: {sorted(extra)}"


def _assert_required_keys(payload: dict[str, Any], required: set[str], path: str) -> None:
    missing = required - set(payload)
    assert not missing, f"{path} missing keys: {sorted(missing)}"


def _assert_type(payload: dict[str, Any], key: str, expected_type: type, path: str) -> None:
    assert type(payload.get(key)) is expected_type, f"{path}.{key} must be {expected_type.__name__}"


def _assert_str(payload: dict[str, Any], key: str, path: str) -> None:
    _assert_type(payload, key, str, path)


def _assert_int(payload: dict[str, Any], key: str, path: str) -> None:
    _assert_type(payload, key, int, path)


def _assert_bool(payload: dict[str, Any], key: str, path: str) -> None:
    _assert_type(payload, key, bool, path)


def _assert_list(payload: dict[str, Any], key: str, path: str) -> list[Any]:
    value = payload.get(key)
    assert isinstance(value, list), f"{path}.{key} must be list"
    return value


def _assert_string_list(payload: dict[str, Any], key: str, path: str) -> None:
    value = _assert_list(payload, key, path)
    for index, item in enumerate(value):
        assert type(item) is str, f"{path}.{key}[{index}] must be str"


def assert_mention_span_payload(payload: Any, path: str = "mention_span") -> None:
    span = _assert_dict(payload, path)
    _assert_keys(span, {"jid", "label", "start", "length"}, path)
    _assert_str(span, "jid", path)
    _assert_str(span, "label", path)
    _assert_int(span, "start", path)
    _assert_int(span, "length", path)


def assert_mention_spans(payload: Any, path: str = "mention_spans") -> None:
    assert_json_like(payload, path)
    assert isinstance(payload, list), f"{path} must be list"
    for index, span in enumerate(payload):
        assert_mention_span_payload(span, f"{path}[{index}]")


def assert_ui_message(payload: Any, path: str = "UiMessage") -> None:
    message = _assert_dict(payload, path)
    _assert_keys(message, UI_MESSAGE_FIELDS, path)
    for key in (
        "id",
        "chat_id",
        "type",
        "timestamp",
        "read_receipt",
        "sender",
        "sender_raw",
        "text",
        "image_source",
        "caption",
        "duration",
        "sticker_source",
        "media_path",
        "thumbnail_path",
        "mimetype",
        "file_name",
        "send_status",
        "temp_id",
        "reply_to_id",
        "reply_to_sender_id",
        "reply_to_sender_raw",
        "reply_to_text",
        "button_text",
        "button_url",
        "link_title",
        "link_description",
        "link_url",
        "sender_name",
        "sender_photo",
        "reply_to_sender",
    ):
        _assert_str(message, key, path)
    for key in ("is_outgoing", "edited", "reply_to_from_me"):
        _assert_bool(message, key, path)
    _assert_int(message, "timestamp_unix", path)
    assert message["type"] in MESSAGE_TYPES, f"{path}.type has unknown value {message['type']!r}"
    assert (
        message["read_receipt"] in READ_RECEIPTS
    ), f"{path}.read_receipt has unknown value {message['read_receipt']!r}"
    _assert_string_list(message, "mentioned_jids", path)
    _assert_string_list(message, "images", path)
    _assert_string_list(message, "reply_to_mentioned_jids", path)
    assert_mention_spans(message["mention_spans"], f"{path}.mention_spans")


def assert_base_chat(payload: Any, path: str = "ChatListItem") -> None:
    chat = _assert_dict(payload, path)
    _assert_keys(chat, CHAT_LIST_ITEM_FIELDS, path)
    for key in (
        "id",
        "name",
        "photo",
        "last_message",
        "date",
        "read_receipt",
        "last_message_type",
        "full_name",
        "push_name",
        "business_name",
    ):
        _assert_str(chat, key, path)
    for key in ("last_message_timestamp", "unread_count", "name_updated_at"):
        _assert_int(chat, key, path)
    for key in ("is_group", "muted"):
        _assert_bool(chat, key, path)
    assert chat["read_receipt"] in READ_RECEIPTS, f"{path}.read_receipt has unknown value {chat['read_receipt']!r}"
    _assert_string_list(chat, "last_message_mentioned_jids", path)


def assert_chat_list_entry(payload: Any, path: str = "ChatListEntry") -> None:
    chat = _assert_dict(payload, path)
    _assert_keys(chat, CHAT_LIST_ENTRY_FIELDS, path)
    base = {key: chat[key] for key in CHAT_LIST_ITEM_FIELDS}
    assert_base_chat(base, path)
    _assert_str(chat, "draft", path)
    _assert_bool(chat, "has_draft", path)


def assert_contact_item(payload: Any, path: str = "ContactItem") -> None:
    contact = _assert_dict(payload, path)
    _assert_keys(contact, CONTACT_ITEM_FIELDS, path)
    for key in CONTACT_ITEM_FIELDS:
        _assert_str(contact, key, path)


def assert_success_response(payload: Any, path: str = "SuccessResponse") -> None:
    response = _assert_dict(payload, path)
    _assert_keys(response, {"success", "message"}, path)
    _assert_bool(response, "success", path)
    _assert_str(response, "message", path)


def assert_chat_list_response(payload: Any) -> None:
    response = _assert_dict(payload, "ChatListResponse")
    _assert_keys(response, {"success", "chats", "message"}, "ChatListResponse")
    _assert_bool(response, "success", "ChatListResponse")
    _assert_str(response, "message", "ChatListResponse")
    chats = _assert_list(response, "chats", "ChatListResponse")
    for index, chat in enumerate(chats):
        assert_chat_list_entry(chat, f"ChatListResponse.chats[{index}]")


def assert_messages_response(payload: Any) -> None:
    response = _assert_dict(payload, "MessagesResponse")
    _assert_keys(response, {"success", "messages", "message", "next_cursor", "has_more"}, "MessagesResponse")
    _assert_bool(response, "success", "MessagesResponse")
    _assert_str(response, "message", "MessagesResponse")
    _assert_str(response, "next_cursor", "MessagesResponse")
    _assert_bool(response, "has_more", "MessagesResponse")
    messages = _assert_list(response, "messages", "MessagesResponse")
    for index, message in enumerate(messages):
        assert_ui_message(message, f"MessagesResponse.messages[{index}]")


def assert_contact_list_response(payload: Any) -> None:
    response = _assert_dict(payload, "ContactListResponse")
    _assert_keys(response, {"success", "contacts", "message"}, "ContactListResponse")
    _assert_bool(response, "success", "ContactListResponse")
    _assert_str(response, "message", "ContactListResponse")
    contacts = _assert_list(response, "contacts", "ContactListResponse")
    for index, contact in enumerate(contacts):
        assert_contact_item(contact, f"ContactListResponse.contacts[{index}]")


def assert_chat_info_response(payload: Any) -> None:
    response = _assert_dict(payload, "ChatInfoResponse")
    if response.get("success") is False:
        _assert_keys(response, {"success"}, "ChatInfoResponse")
        return
    _assert_keys(response, {"success", "id", "name", "photo", "is_group", "unread_count"}, "ChatInfoResponse")
    _assert_bool(response, "success", "ChatInfoResponse")
    for key in ("id", "name", "photo"):
        _assert_str(response, key, "ChatInfoResponse")
    _assert_bool(response, "is_group", "ChatInfoResponse")
    _assert_int(response, "unread_count", "ChatInfoResponse")


def assert_chat_draft_response(payload: Any) -> None:
    response = _assert_dict(payload, "ChatDraftResponse")
    _assert_keys(response, {"success", "text", "mention_spans"}, "ChatDraftResponse")
    _assert_bool(response, "success", "ChatDraftResponse")
    _assert_str(response, "text", "ChatDraftResponse")
    assert_mention_spans(response["mention_spans"], "ChatDraftResponse.mention_spans")


def assert_group_mention_candidate(payload: Any, path: str) -> None:
    candidate = _assert_dict(payload, path)
    _assert_keys(candidate, {"jid", "label", "photo", "is_admin", "is_super_admin"}, path)
    for key in ("jid", "label", "photo"):
        _assert_str(candidate, key, path)
    _assert_bool(candidate, "is_admin", path)
    _assert_bool(candidate, "is_super_admin", path)


def assert_group_mention_candidates_response(payload: Any) -> None:
    response = _assert_dict(payload, "GroupMentionCandidatesResponse")
    _assert_keys(response, {"success", "candidates", "message"}, "GroupMentionCandidatesResponse")
    _assert_bool(response, "success", "GroupMentionCandidatesResponse")
    _assert_str(response, "message", "GroupMentionCandidatesResponse")
    candidates = _assert_list(response, "candidates", "GroupMentionCandidatesResponse")
    for index, candidate in enumerate(candidates):
        assert_group_mention_candidate(candidate, f"GroupMentionCandidatesResponse.candidates[{index}]")


def assert_session_status_response(payload: Any) -> None:
    response = _assert_dict(payload, "SessionStatusResponse")
    _assert_keys(response, {"logged_in", "qr_image_path"}, "SessionStatusResponse")
    _assert_bool(response, "logged_in", "SessionStatusResponse")
    _assert_str(response, "qr_image_path", "SessionStatusResponse")


def assert_daemon_status_response(payload: Any) -> None:
    response = _assert_dict(payload, "DaemonStatusResponse")
    _assert_keys(response, {"installed", "active"}, "DaemonStatusResponse")
    _assert_bool(response, "installed", "DaemonStatusResponse")
    _assert_bool(response, "active", "DaemonStatusResponse")


def assert_ensure_daemon_version_response(payload: Any) -> None:
    response = _assert_dict(payload, "EnsureDaemonVersionResponse")
    _assert_keys(response, {"restarted"}, "EnsureDaemonVersionResponse")
    _assert_bool(response, "restarted", "EnsureDaemonVersionResponse")


def assert_clear_data_response(payload: Any) -> None:
    response = _assert_dict(payload, "ClearDataResponse")
    _assert_keys(response, {"success"}, "ClearDataResponse")
    _assert_bool(response, "success", "ClearDataResponse")


def assert_pair_phone_response(payload: Any) -> None:
    response = _assert_dict(payload, "PairPhoneResponse")
    _assert_keys(response, {"success", "code", "message"}, "PairPhoneResponse")
    _assert_bool(response, "success", "PairPhoneResponse")
    _assert_str(response, "code", "PairPhoneResponse")
    _assert_str(response, "message", "PairPhoneResponse")


def assert_settings_response(payload: Any) -> None:
    response = _assert_dict(payload, "SettingsResponse")
    _assert_keys(response, {"success", "notifications_suppressed"}, "SettingsResponse")
    _assert_bool(response, "success", "SettingsResponse")
    _assert_bool(response, "notifications_suppressed", "SettingsResponse")


def assert_phone_number_response(payload: Any) -> None:
    response = _assert_dict(payload, "PhoneNumberResponse")
    _assert_keys(response, {"success", "phone_number"}, "PhoneNumberResponse")
    _assert_bool(response, "success", "PhoneNumberResponse")
    _assert_str(response, "phone_number", "PhoneNumberResponse")


def assert_download_media_response(payload: Any) -> None:
    response = _assert_dict(payload, "DownloadMediaResponse")
    _assert_keys(response, {"success", "media_path", "message"}, "DownloadMediaResponse")
    _assert_bool(response, "success", "DownloadMediaResponse")
    _assert_str(response, "media_path", "DownloadMediaResponse")
    _assert_str(response, "message", "DownloadMediaResponse")


def assert_cached_stickers_response(payload: Any) -> None:
    response = _assert_dict(payload, "CachedStickersResponse")
    _assert_keys(response, {"success", "stickers"}, "CachedStickersResponse")
    _assert_bool(response, "success", "CachedStickersResponse")
    _assert_string_list(response, "stickers", "CachedStickersResponse")


def assert_sync_status_response(payload: Any) -> None:
    assert type(payload) is bool, "SyncStatus must be bool"


def assert_none_response(payload: Any) -> None:
    assert payload is None, "response must be None"


def assert_message_upsert_payload(payload: Any) -> None:
    messages = _assert_list_of_dicts(payload, "message-upsert")
    for index, message in enumerate(messages):
        assert_ui_message(message, f"message-upsert[{index}]")


def assert_chat_list_update_payload(payload: Any) -> None:
    chats = _assert_list_of_dicts(payload, "chat-list-update")
    for index, chat in enumerate(chats):
        assert_base_chat(chat, f"chat-list-update[{index}]")


def assert_sender_photo_update_payload(payload: Any) -> None:
    updates = _assert_list_of_dicts(payload, "sender-photo-update")
    for index, update in enumerate(updates):
        _assert_keys(update, {"jid", "photo"}, f"sender-photo-update[{index}]")
        _assert_str(update, "jid", f"sender-photo-update[{index}]")
        _assert_str(update, "photo", f"sender-photo-update[{index}]")


def assert_presence_update_payload(payload: Any) -> None:
    updates = _assert_list_of_dicts(payload, "presence-update")
    for index, update in enumerate(updates):
        _assert_keys(update, {"jid", "status"}, f"presence-update[{index}]")
        _assert_str(update, "jid", f"presence-update[{index}]")
        _assert_str(update, "status", f"presence-update[{index}]")


def assert_chat_presence_payload(payload: Any) -> None:
    updates = _assert_list_of_dicts(payload, "chat-presence")
    for index, update in enumerate(updates):
        _assert_keys(update, {"chat", "sender", "state", "media", "is_group"}, f"chat-presence[{index}]")
        for key in ("chat", "sender", "state", "media"):
            _assert_str(update, key, f"chat-presence[{index}]")
        _assert_bool(update, "is_group", f"chat-presence[{index}]")


def assert_chat_draft_update_payload(payload: Any) -> None:
    updates = _assert_list_of_dicts(payload, "chat-draft-update")
    for index, update in enumerate(updates):
        _assert_keys(update, {"id", "draft", "has_draft"}, f"chat-draft-update[{index}]")
        _assert_str(update, "id", f"chat-draft-update[{index}]")
        _assert_str(update, "draft", f"chat-draft-update[{index}]")
        _assert_bool(update, "has_draft", f"chat-draft-update[{index}]")


EVENT_PAYLOAD_VALIDATORS: dict[str, Validator] = {
    "session-status": assert_session_status_response,
    "sync-status": assert_sync_status_response,
    "message-upsert": assert_message_upsert_payload,
    "chat-list-update": assert_chat_list_update_payload,
    "sender-photo-update": assert_sender_photo_update_payload,
    "presence-update": assert_presence_update_payload,
    "chat-presence": assert_chat_presence_payload,
    "chat-draft-update": assert_chat_draft_update_payload,
}


def assert_event_payload(event_name: str, payload: Any) -> None:
    validator = EVENT_PAYLOAD_VALIDATORS.get(event_name)
    if validator is None:
        raise AssertionError(f"No QML event payload validator registered for {event_name!r}")
    validator(payload)
