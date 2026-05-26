from __future__ import annotations

from dataclasses import asdict

import pytest
from contracts.qml_payloads import assert_ui_message
from qml_contract_helpers import (
    DEFAULT_CHAT_ID,
    DEFAULT_SENDER_ID,
    seed_chat,
    seed_message,
    seed_sender_identity,
)

from greenline import qml_events, qml_payloads
from greenline.api.common import ui_message_dict
from greenline.events.handlers import render_message_payload
from models import MessageType


@pytest.mark.parametrize("message_type", list(MessageType))
def test_message_serializers_match_initial_load_for_every_type(message_type: MessageType) -> None:
    seed_sender_identity(DEFAULT_SENDER_ID, name="Alice", photo="file:///tmp/alice.jpg")
    seed_chat(DEFAULT_CHAT_ID)
    seed_message(DEFAULT_CHAT_ID, "reply-1", is_outgoing=True, text="Reply", timestamp_unix=1)
    message = seed_message(
        DEFAULT_CHAT_ID,
        f"message-{message_type.value}",
        message_type=message_type,
        is_outgoing=False,
        timestamp_unix=2,
    )

    expected = qml_payloads.ui_message(message)
    api_common = ui_message_dict(message)
    daemon_render = render_message_payload(asdict(message))
    bridge_render = qml_events.message_upsert_payload([asdict(message)])[0]
    import main

    initial_load = main.get_messages(DEFAULT_CHAT_ID)["messages"][-1]

    for payload in (expected, api_common, daemon_render, bridge_render, initial_load):
        assert_ui_message(payload)
        assert set(payload) == set(expected)

    assert api_common == expected
    assert daemon_render == expected
    assert bridge_render == expected
    assert initial_load == expected
    assert expected["sender_name"] == "Alice"
    assert expected["sender_photo"] == "file:///tmp/alice.jpg"
    assert expected["reply_to_sender"] == "Alice"


def test_message_bridge_payload_accepts_stored_dict_without_dropping_reply_or_sender_fields() -> None:
    seed_sender_identity(DEFAULT_SENDER_ID, name="Alice", photo="file:///tmp/alice.jpg")
    seed_chat(DEFAULT_CHAT_ID)
    message = seed_message(DEFAULT_CHAT_ID, "message-1", is_outgoing=False)

    payload = qml_events.message_upsert_payload([asdict(message)])[0]

    assert_ui_message(payload)
    assert payload["sender_name"] == "Alice"
    assert payload["sender_photo"] == "file:///tmp/alice.jpg"
    assert payload["reply_to_sender"] == "Alice"
