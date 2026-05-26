from __future__ import annotations

from typing import Any

from models import MessageType, ReadReceipt

MESSAGE_TYPES = {item.value for item in MessageType}
READ_RECEIPTS = {item.value for item in ReadReceipt}


def assert_json_like(value: Any, path: str = "payload") -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
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


def _assert_list_of_dicts(payload: Any, event_name: str) -> list[dict[str, Any]]:
    assert_json_like(payload, event_name)
    assert isinstance(payload, list), f"{event_name} payload must be a list"
    for index, item in enumerate(payload):
        assert isinstance(item, dict), f"{event_name}[{index}] must be an object"
    return payload


def _assert_str(payload: dict[str, Any], key: str, event_name: str) -> None:
    assert isinstance(payload.get(key), str), f"{event_name} payload missing string {key!r}"


def assert_message_upsert_payload(payload: Any) -> None:
    messages = _assert_list_of_dicts(payload, "message-upsert")
    required = {"id", "chat_id", "type", "is_outgoing", "timestamp", "timestamp_unix", "read_receipt"}
    for index, message in enumerate(messages):
        missing = required - set(message)
        assert not missing, f"message-upsert[{index}] missing keys: {sorted(missing)}"
        assert message["type"] in MESSAGE_TYPES, f"message-upsert[{index}] has unknown type {message['type']!r}"
        assert (
            message["read_receipt"] in READ_RECEIPTS
        ), f"message-upsert[{index}] has unknown read_receipt {message['read_receipt']!r}"
        assert isinstance(message["is_outgoing"], bool), f"message-upsert[{index}].is_outgoing must be bool"
        assert isinstance(message["timestamp_unix"], int), f"message-upsert[{index}].timestamp_unix must be int"
        for key in ("id", "chat_id", "timestamp"):
            _assert_str(message, key, f"message-upsert[{index}]")


def assert_chat_list_update_payload(payload: Any) -> None:
    chats = _assert_list_of_dicts(payload, "chat-list-update")
    required = {
        "id",
        "name",
        "photo",
        "last_message",
        "date",
        "last_message_timestamp",
        "read_receipt",
        "unread_count",
        "is_group",
    }
    for index, chat in enumerate(chats):
        missing = required - set(chat)
        assert not missing, f"chat-list-update[{index}] missing keys: {sorted(missing)}"
        assert (
            chat["read_receipt"] in READ_RECEIPTS
        ), f"chat-list-update[{index}] has unknown read_receipt {chat['read_receipt']!r}"
        assert isinstance(
            chat["last_message_timestamp"], int
        ), f"chat-list-update[{index}].last_message_timestamp must be int"
        assert isinstance(chat["unread_count"], int), f"chat-list-update[{index}].unread_count must be int"
        assert isinstance(chat["is_group"], bool), f"chat-list-update[{index}].is_group must be bool"
        for key in ("id", "name", "photo", "last_message", "date"):
            _assert_str(chat, key, f"chat-list-update[{index}]")


def assert_sender_photo_update_payload(payload: Any) -> None:
    updates = _assert_list_of_dicts(payload, "sender-photo-update")
    for index, update in enumerate(updates):
        assert set(update) == {"jid", "photo"}, f"sender-photo-update[{index}] has unexpected keys"
        _assert_str(update, "jid", f"sender-photo-update[{index}]")
        _assert_str(update, "photo", f"sender-photo-update[{index}]")


def assert_presence_update_payload(payload: Any) -> None:
    updates = _assert_list_of_dicts(payload, "presence-update")
    for index, update in enumerate(updates):
        assert set(update) == {"jid", "status"}, f"presence-update[{index}] has unexpected keys"
        _assert_str(update, "jid", f"presence-update[{index}]")
        _assert_str(update, "status", f"presence-update[{index}]")


def assert_chat_presence_payload(payload: Any) -> None:
    updates = _assert_list_of_dicts(payload, "chat-presence")
    required = {"chat", "sender", "state", "media", "is_group"}
    for index, update in enumerate(updates):
        assert set(update) == required, f"chat-presence[{index}] has unexpected keys"
        for key in ("chat", "sender", "state", "media"):
            _assert_str(update, key, f"chat-presence[{index}]")
        assert isinstance(update["is_group"], bool), f"chat-presence[{index}].is_group must be bool"


EVENT_PAYLOAD_VALIDATORS = {
    "message-upsert": assert_message_upsert_payload,
    "chat-list-update": assert_chat_list_update_payload,
    "sender-photo-update": assert_sender_photo_update_payload,
    "presence-update": assert_presence_update_payload,
    "chat-presence": assert_chat_presence_payload,
}


def assert_event_payload(event_name: str, payload: Any) -> None:
    validator = EVENT_PAYLOAD_VALIDATORS.get(event_name)
    if validator is None:
        assert_json_like(payload, event_name)
        return
    validator(payload)
