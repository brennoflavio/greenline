from __future__ import annotations

from dataclasses import asdict

from contracts.qml_payloads import (
    CHAT_LIST_ITEM_FIELDS,
    assert_base_chat,
    assert_chat_list_entry,
)
from qml_contract_helpers import (
    DEFAULT_CHAT_ID,
    DEFAULT_SENDER_ID,
    seed_chat,
    seed_draft,
)

from greenline import qml_events, qml_payloads
from greenline.api.common import ui_chat_dict
from greenline.events.handlers import render_chat_payload
from models import MessageType, ReadReceipt


def test_chat_serializers_match_initial_load_except_draft_fields() -> None:
    chat = seed_chat(
        DEFAULT_CHAT_ID,
        name="Alice",
        photo="file:///tmp/alice.jpg",
        last_message="Hello @Sender",
        last_message_mentioned_jids=[DEFAULT_SENDER_ID],
        last_message_type=MessageType.TEXT.value,
        read_receipt=ReadReceipt.READ,
        unread_count=5,
        muted=True,
        full_name="Alice Full",
        push_name="Alice Push",
        business_name="Alice Biz",
    )
    seed_draft(DEFAULT_CHAT_ID, "Draft text", [])

    expected = qml_payloads.ui_chat(chat)
    api_common = ui_chat_dict(chat)
    daemon_render = render_chat_payload(asdict(chat))
    bridge_render = qml_events.chat_list_update_payload([asdict(chat)])[0]

    import main

    initial_entry = main.get_chat_list()["chats"][0]
    initial_base = {key: initial_entry[key] for key in CHAT_LIST_ITEM_FIELDS}

    for payload in (expected, api_common, daemon_render, bridge_render, initial_base):
        assert_base_chat(payload)
        assert set(payload) == set(expected)

    assert api_common == expected
    assert daemon_render == expected
    assert bridge_render == expected
    assert initial_base == expected
    assert_chat_list_entry(initial_entry)
    assert initial_entry["draft"] == "Draft text"
    assert initial_entry["has_draft"] is True
    assert expected["photo"] == "file:///tmp/alice.jpg"
    assert expected["muted"] is True
    assert expected["last_message"] == "Hello @Sender"


def test_chat_bridge_payload_accepts_stored_dict_without_dropping_required_fields() -> None:
    chat = seed_chat(DEFAULT_CHAT_ID, photo="file:///tmp/photo.jpg", muted=True)

    payload = qml_events.chat_list_update_payload([asdict(chat)])[0]

    assert_base_chat(payload)
    assert payload["photo"] == "file:///tmp/photo.jpg"
    assert payload["muted"] is True
    assert payload["full_name"] == chat.full_name
    assert payload["name_updated_at"] == chat.name_updated_at
