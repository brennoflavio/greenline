from __future__ import annotations

import pytest
from contracts.qml_registry import validate_api_response, validate_event_payload
from qml_contract_helpers import (
    DEFAULT_CHAT_ID,
    DEFAULT_SENDER_ID,
    make_mention_span,
    seed_chat,
    seed_draft,
)

import daemon_types
import main
from ut_components.kv import KV


def _last_event(fake_pyotherside, name: str):
    for event_name, payload in reversed(fake_pyotherside.sent):
        if event_name == name:
            return payload
    raise AssertionError(f"missing event {name}")


def test_get_chat_list_contract_includes_full_chat_and_draft() -> None:
    chat = seed_chat(DEFAULT_CHAT_ID, muted=True, photo="file:///tmp/photo.jpg")
    with KV() as kv:
        kv.put(f"draft:{chat.id}", "Draft text")

    result = main.get_chat_list()

    validate_api_response("get_chat_list", result)
    assert result["chats"][0]["photo"] == "file:///tmp/photo.jpg"
    assert result["chats"][0]["muted"] is True
    assert result["chats"][0]["has_draft"] is True


def test_get_chat_list_contract_handles_malformed_chat() -> None:
    with KV() as kv:
        kv.put("chat:broken", {"id": "broken"})

    result = main.get_chat_list()

    validate_api_response("get_chat_list", result)
    assert result == {"success": False, "chats": [], "message": result["message"]}


def test_get_contact_list_contract_success_and_failure(fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_daemon_rpc.contacts = [
        daemon_types.Contact(
            jid=DEFAULT_SENDER_ID,
            display_name="Sender",
            first_name="Sender",
            full_name="Sender Full",
            push_name="Sender Push",
            business_name="Sender Biz",
            avatar_path="/tmp/sender.jpg",
        )
    ]
    success = main.get_contact_list()
    validate_api_response("get_contact_list", success)
    assert success["contacts"][0]["photo"] == "file:///tmp/sender.jpg"

    def fail_contacts(self):
        raise RuntimeError("contacts unavailable")

    monkeypatch.setattr(fake_daemon_rpc, "get_contacts", fail_contacts)
    failure = main.get_contact_list()
    validate_api_response("get_contact_list", failure)
    assert failure["success"] is False


def test_get_chat_info_contract_success_missing_and_malformed() -> None:
    seed_chat(DEFAULT_CHAT_ID, photo="file:///tmp/photo.jpg")

    success = main.get_chat_info(DEFAULT_CHAT_ID)
    validate_api_response("get_chat_info", success)
    assert success["photo"] == "file:///tmp/photo.jpg"

    missing = main.get_chat_info("missing@s.whatsapp.net")
    validate_api_response("get_chat_info", missing)
    assert missing == {"success": False}

    with KV() as kv:
        kv.put("chat:broken", {"id": "broken"})
    malformed = main.get_chat_info("broken")
    validate_api_response("get_chat_info", malformed)
    assert malformed == {"success": False}


def test_get_group_mention_candidates_contract_success_and_failure(
    fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_daemon_rpc.group_participants = {
        "group@g.us": [
            daemon_types.GroupParticipant(
                jid=DEFAULT_SENDER_ID,
                display_name="Sender",
                is_admin=True,
                is_super_admin=False,
            )
        ]
    }

    success = main.get_group_mention_candidates("group@g.us")
    validate_api_response("get_group_mention_candidates", success)
    assert success["candidates"][0]["is_admin"] is True

    def fail_participants(self, chat_id: str):
        raise RuntimeError("participants unavailable")

    monkeypatch.setattr(fake_daemon_rpc, "get_group_participants", fail_participants)
    failure = main.get_group_mention_candidates("group@g.us")
    validate_api_response("get_group_mention_candidates", failure)
    assert failure["success"] is False


def test_get_and_set_chat_draft_contracts(fake_pyotherside_module) -> None:
    span = make_mention_span(start=6)
    seed_draft(DEFAULT_CHAT_ID, "Hello @Sender", [span])

    draft = main.get_chat_draft(DEFAULT_CHAT_ID)
    validate_api_response("get_chat_draft", draft)
    assert draft["mention_spans"] == [span]

    result = main.set_chat_draft(DEFAULT_CHAT_ID, "Saved", [span])
    validate_api_response("set_chat_draft", result)
    event_payload = _last_event(fake_pyotherside_module, "chat-draft-update")
    validate_event_payload("chat-draft-update", event_payload)
    assert event_payload == [{"id": DEFAULT_CHAT_ID, "draft": "Saved", "has_draft": True}]

    cleared = main.set_chat_draft(DEFAULT_CHAT_ID, "", [])
    validate_api_response("set_chat_draft", cleared)
    event_payload = _last_event(fake_pyotherside_module, "chat-draft-update")
    validate_event_payload("chat-draft-update", event_payload)
    assert event_payload == [{"id": DEFAULT_CHAT_ID, "draft": "", "has_draft": False}]


def test_toggle_mute_contract_and_emits_full_chat_update(fake_daemon_rpc, fake_pyotherside_module) -> None:
    chat = seed_chat(DEFAULT_CHAT_ID, muted=False, photo="file:///tmp/photo.jpg")

    result = main.toggle_mute(chat.id)

    validate_api_response("toggle_mute", result)
    assert fake_daemon_rpc.set_muted_calls == [{"chat_id": chat.id, "muted": True}]
    event_payload = _last_event(fake_pyotherside_module, "chat-list-update")
    validate_event_payload("chat-list-update", event_payload)
    assert event_payload[0]["muted"] is True
    assert event_payload[0]["photo"] == "file:///tmp/photo.jpg"


def test_toggle_mute_contract_missing_chat() -> None:
    result = main.toggle_mute("missing@s.whatsapp.net")

    validate_api_response("toggle_mute", result)
    assert result == {"success": False, "message": "Chat not found"}
