from __future__ import annotations

from greenline import qml_events
from models import Message, MessageType, ReadReceipt


def _message(chat_id: str, message_id: str, *, temp_id: str = "", text: str = "") -> Message:
    return Message(
        id=message_id,
        chat_id=chat_id,
        type=MessageType.TEXT,
        is_outgoing=False,
        timestamp="12:00",
        timestamp_unix=1_700_000_000,
        read_receipt=ReadReceipt.NONE,
        temp_id=temp_id,
        text=text,
    )


def test_message_upsert_payload_keeps_only_final_state_per_message() -> None:
    payload = qml_events.message_upsert_payload(
        [
            _message("chat-1", "message-1", text="first"),
            _message("chat-1", "message-2", text="other"),
            _message("chat-1", "message-1", text="final"),
        ]
    )

    assert [(message["id"], message["text"]) for message in payload] == [
        ("message-1", "final"),
        ("message-2", "other"),
    ]


def test_message_upsert_payload_replaces_pending_alias_without_cross_chat_collisions() -> None:
    payload = qml_events.message_upsert_payload(
        [
            _message("chat-1", "pending-1", temp_id="pending-1", text="pending"),
            _message("chat-2", "pending-1", temp_id="pending-1", text="other chat"),
            _message("chat-1", "server-1", temp_id="pending-1", text="sent"),
            _message("chat-1", "server-1", text="delivered"),
        ]
    )

    assert [(message["chat_id"], message["id"], message["temp_id"], message["text"]) for message in payload] == [
        ("chat-1", "server-1", "pending-1", "delivered"),
        ("chat-2", "pending-1", "pending-1", "other chat"),
    ]
