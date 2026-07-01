from __future__ import annotations

import pytest
from contracts.qml_registry import validate_api_response, validate_event_payload
from qml_contract_helpers import (
    DEFAULT_CHAT_ID,
    DEFAULT_GROUP_ID,
    DEFAULT_SENDER_ID,
    make_mention_span,
    seed_chat,
    seed_draft,
    seed_group_profile,
    seed_sender_identity,
)

import daemon_types
import main
from greenline.contracts.kv import GreenlineKV
from greenline.contracts.validation import BoundaryValidationError
from greenline.store.identity import canonicalize_contact_jid
from ut_components.kv import KV


def _last_event(fake_pyotherside, name: str):
    for event_name, payload in reversed(fake_pyotherside.sent):
        if event_name == name:
            return payload
    raise AssertionError(f"missing event {name}")


def _write_vcard(tmp_path, content: str) -> str:
    path = tmp_path / "contact.vcf"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_get_chat_list_contract_filters_active_and_archived_chats() -> None:
    active_chat = seed_chat(DEFAULT_CHAT_ID, muted=True, photo="file:///tmp/photo.jpg")
    archived_chat = seed_chat("archived@s.whatsapp.net", archived=True, muted=False)
    seed_draft(active_chat.id, "Draft text", [])

    active_result = main.get_chat_list()
    archived_result = main.get_chat_list(True)

    validate_api_response("get_chat_list", active_result)
    validate_api_response("get_chat_list", archived_result)
    assert [chat["id"] for chat in active_result["chats"]] == [active_chat.id]
    assert active_result["chats"][0]["photo"] == "file:///tmp/photo.jpg"
    assert active_result["chats"][0]["muted"] is True
    assert active_result["chats"][0]["archived"] is False
    assert active_result["chats"][0]["has_draft"] is True
    assert [chat["id"] for chat in archived_result["chats"]] == [archived_chat.id]
    assert archived_result["chats"][0]["archived"] is True
    assert archived_result["chats"][0]["has_draft"] is False


def test_get_chat_list_contract_rejects_malformed_chat() -> None:
    with KV() as kv:
        kv.put("chat:broken", {"id": "broken"})

    with pytest.raises(Exception):
        main.get_chat_list()


def test_prioritize_chat_avatars_contract_filters_missing_photos_in_input_order(fake_daemon_rpc) -> None:
    missing_first = seed_chat("missing-first@s.whatsapp.net", photo="")
    seed_chat("has-photo@s.whatsapp.net", photo="file:///tmp/existing.jpg")
    seed_chat("news@newsletter", photo="")
    missing_second = seed_chat("missing-second@s.whatsapp.net", photo="")

    result = main.prioritize_chat_avatars(
        ["has-photo@s.whatsapp.net", missing_first.id, "news@newsletter", missing_second.id]
    )

    validate_api_response("prioritize_chat_avatars", result)
    assert fake_daemon_rpc.prioritize_avatars_calls == [[missing_first.id, missing_second.id]]


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


def test_get_contact_list_contract_raises_boundary_validation_error(
    fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_contacts(self):
        raise BoundaryValidationError("bad contacts reply")

    monkeypatch.setattr(fake_daemon_rpc, "get_contacts", fail_contacts)

    with pytest.raises(BoundaryValidationError, match="bad contacts reply"):
        main.get_contact_list()


def test_canonicalize_contact_jid_preserves_empty_daemon_resolution(
    fake_daemon_rpc,
) -> None:
    fake_daemon_rpc.ensure_jid_map["lid-user@lid"] = ""

    assert canonicalize_contact_jid("lid-user@lid", rpc=fake_daemon_rpc()) == ""


def test_get_chat_info_contract_returns_direct_chat_defaults() -> None:
    seed_chat(
        DEFAULT_CHAT_ID,
        photo="file:///tmp/photo.jpg",
        muted=True,
        first_unread_message_id="incoming-1",
    )

    success = main.get_chat_info(DEFAULT_CHAT_ID)
    validate_api_response("get_chat_info", success)
    assert success["photo"] == "file:///tmp/photo.jpg"
    assert success["muted"] is True
    assert success["first_unread_message_id"] == "incoming-1"
    assert success["description"] == ""
    assert success["member_count"] == 0
    assert success["members"] == []


def test_start_chat_by_phone_contract_returns_existing_chat_metadata() -> None:
    chat_id = "5511999999999@s.whatsapp.net"
    seed_chat(
        chat_id,
        name="Alice",
        photo="file:///tmp/alice.jpg",
        muted=True,
        archived=False,
        unread_count=3,
        first_unread_message_id="incoming-1",
    )

    result = main.start_chat_by_phone("5511999999999")

    validate_api_response("start_chat_by_phone", result)
    assert result["success"] is True
    assert result["chat"]["id"] == chat_id
    assert result["chat"]["name"] == "Alice"
    assert result["chat"]["photo"] == "file:///tmp/alice.jpg"
    assert result["chat"]["muted"] is True
    assert result["chat"]["unread_count"] == 3
    assert result["chat"]["first_unread_message_id"] == "incoming-1"


def test_start_chat_by_phone_contract_returns_fallback_chat_payload() -> None:
    result = main.start_chat_by_phone("5511888888888")

    validate_api_response("start_chat_by_phone", result)
    assert result == {
        "success": True,
        "chat": {
            "id": "5511888888888@s.whatsapp.net",
            "name": "5511888888888",
            "photo": "",
            "last_message": "",
            "date": "",
            "last_message_timestamp": 0,
            "read_receipt": "",
            "unread_count": 0,
            "is_group": False,
            "first_unread_message_id": "",
            "last_message_mentioned_jids": [],
            "last_message_type": "",
            "muted": False,
            "archived": False,
            "full_name": "",
            "push_name": "",
            "business_name": "",
            "name_updated_at": 0,
        },
        "message": "",
    }
    with GreenlineKV() as kv:
        assert kv.get_record("chat:5511888888888@s.whatsapp.net") is None


def test_start_chat_by_phone_contract_rejects_invalid_phone_number() -> None:
    result = main.start_chat_by_phone("0551199999999")

    validate_api_response("start_chat_by_phone", result)
    assert result == {
        "success": False,
        "chat": None,
        "message": "Enter digits only, no leading zero (e.g. 5511999999999)",
    }


def test_start_chat_by_phone_contract_handles_empty_resolution(fake_daemon_rpc) -> None:
    fake_daemon_rpc.ensure_jid_map["5511777777777@s.whatsapp.net"] = ""

    result = main.start_chat_by_phone("5511777777777")

    validate_api_response("start_chat_by_phone", result)
    assert result == {
        "success": False,
        "chat": None,
        "message": "Failed to resolve phone number",
    }


def test_start_chat_by_phone_contract_handles_ensure_jid_failure(
    fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_ensure_jid(self, jid: str):
        raise RuntimeError("jid unavailable")

    monkeypatch.setattr(fake_daemon_rpc, "ensure_jid", fail_ensure_jid)

    result = main.start_chat_by_phone("5511666666666")

    validate_api_response("start_chat_by_phone", result)
    assert result == {
        "success": False,
        "chat": None,
        "message": "jid unavailable",
    }


def test_start_chat_from_contact_contract_uses_vcard_phone_number(tmp_path) -> None:
    vcard_path = _write_vcard(
        tmp_path,
        "BEGIN:VCARD\nFN:Alice\nTEL;TYPE=CELL:+55 11 99999-9999\nEND:VCARD\n",
    )

    result = main.start_chat_from_contact(vcard_path)

    validate_api_response("start_chat_from_contact", result)
    assert result == {
        "success": True,
        "chat": {
            "id": "5511999999999@s.whatsapp.net",
            "name": "5511999999999",
            "photo": "",
            "last_message": "",
            "date": "",
            "last_message_timestamp": 0,
            "read_receipt": "",
            "unread_count": 0,
            "is_group": False,
            "first_unread_message_id": "",
            "last_message_mentioned_jids": [],
            "last_message_type": "",
            "muted": False,
            "archived": False,
            "full_name": "",
            "push_name": "",
            "business_name": "",
            "name_updated_at": 0,
        },
        "message": "",
    }
    with GreenlineKV() as kv:
        assert kv.get_record("chat:5511999999999@s.whatsapp.net") is None


def test_start_chat_from_contact_contract_accepts_grouped_tel_property(tmp_path) -> None:
    vcard_path = _write_vcard(
        tmp_path,
        "BEGIN:VCARD\nFN:Grouped\nitem1.TEL;TYPE=CELL:tel:+55 11 97777-7777\nEND:VCARD\n",
    )

    result = main.start_chat_from_contact(vcard_path)

    validate_api_response("start_chat_from_contact", result)
    assert result["success"] is True
    assert result["chat"]["id"] == "5511977777777@s.whatsapp.net"


def test_start_chat_from_contact_contract_reuses_existing_chat(tmp_path) -> None:
    chat_id = "5511888888888@s.whatsapp.net"
    seed_chat(chat_id, name="Bob", photo="file:///tmp/bob.jpg", muted=True)
    vcard_path = _write_vcard(
        tmp_path,
        "BEGIN:VCARD\nFN:Bob\nTEL;TYPE=CELL:(+55) 11 88888-8888\nEND:VCARD\n",
    )

    result = main.start_chat_from_contact(vcard_path)

    validate_api_response("start_chat_from_contact", result)
    assert result["success"] is True
    assert result["chat"]["id"] == chat_id
    assert result["chat"]["name"] == "Bob"
    assert result["chat"]["photo"] == "file:///tmp/bob.jpg"
    assert result["chat"]["muted"] is True


def test_start_chat_from_contact_contract_rejects_missing_phone(tmp_path) -> None:
    vcard_path = _write_vcard(tmp_path, "BEGIN:VCARD\nFN:No Phone\nEND:VCARD\n")

    result = main.start_chat_from_contact(vcard_path)

    validate_api_response("start_chat_from_contact", result)
    assert result == {
        "success": False,
        "chat": None,
        "message": "Contact does not contain a valid phone number",
    }


def test_start_chat_from_contact_contract_rejects_invalid_normalized_phone(tmp_path) -> None:
    vcard_path = _write_vcard(tmp_path, "BEGIN:VCARD\nFN:Short\nTEL:+00 12\nEND:VCARD\n")

    result = main.start_chat_from_contact(vcard_path)

    validate_api_response("start_chat_from_contact", result)
    assert result == {
        "success": False,
        "chat": None,
        "message": "Contact does not contain a valid phone number",
    }


def test_get_chat_info_contract_returns_group_profile_members() -> None:
    seed_chat(DEFAULT_GROUP_ID, name="Project Group", photo="file:///tmp/group.jpg", muted=False, is_group=True)
    seed_sender_identity(DEFAULT_SENDER_ID, name="Alice", photo="file:///tmp/alice.jpg")
    seed_sender_identity("999@s.whatsapp.net", name="Bob", photo="")
    seed_group_profile(
        DEFAULT_GROUP_ID,
        description="Roadmap updates",
        member_count=2,
        members=[
            {"jid": "999@s.whatsapp.net", "display_name": "Zed Raw"},
            {"jid": DEFAULT_SENDER_ID, "display_name": "Alpha Raw"},
        ],
    )

    success = main.get_chat_info(DEFAULT_GROUP_ID)
    validate_api_response("get_chat_info", success)
    assert success["description"] == "Roadmap updates"
    assert success["member_count"] == 2
    assert success["members"] == [
        {"jid": DEFAULT_SENDER_ID, "name": "Alice", "photo": "file:///tmp/alice.jpg"},
        {"jid": "999@s.whatsapp.net", "name": "Bob", "photo": ""},
    ]


def test_get_chat_info_contract_missing_and_malformed() -> None:
    missing = main.get_chat_info("missing@s.whatsapp.net")
    validate_api_response("get_chat_info", missing)
    assert missing == {"success": False}

    with KV() as kv:
        kv.put("chat:broken", {"id": "broken"})
    with pytest.raises(Exception):
        main.get_chat_info("broken")

    seed_chat(DEFAULT_GROUP_ID, is_group=True)
    with KV() as kv:
        kv.put(f"group_profile:{DEFAULT_GROUP_ID}", {"description": "oops", "member_count": "two", "members": []})
    with pytest.raises(Exception):
        main.get_chat_info(DEFAULT_GROUP_ID)


def test_get_group_mention_candidates_contract_success_and_failure(
    fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_daemon_rpc.group_participants = {
        "group@g.us": [
            daemon_types.GroupParticipant(
                jid=DEFAULT_SENDER_ID,
                phone_number_jid=DEFAULT_SENDER_ID,
                lid_jid="",
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


def test_get_group_mention_candidates_contract_raises_boundary_validation_error(
    fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_participants(self, chat_id: str):
        raise BoundaryValidationError("bad participants reply")

    monkeypatch.setattr(fake_daemon_rpc, "get_group_participants", fail_participants)

    with pytest.raises(BoundaryValidationError, match="bad participants reply"):
        main.get_group_mention_candidates("group@g.us")


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
    assert fake_daemon_rpc.set_muted_calls == []
    event_payload = _last_event(fake_pyotherside_module, "chat-list-update")
    validate_event_payload("chat-list-update", event_payload)
    assert event_payload[0]["muted"] is True
    assert event_payload[0]["photo"] == "file:///tmp/photo.jpg"


def test_toggle_mute_contract_missing_chat() -> None:
    result = main.toggle_mute("missing@s.whatsapp.net")

    validate_api_response("toggle_mute", result)
    assert result == {"success": False, "message": "Chat not found"}


def test_toggle_archive_contract_persists_and_emits_full_chat_update(fake_pyotherside_module) -> None:
    chat = seed_chat(DEFAULT_CHAT_ID, archived=False, muted=True)

    result = main.toggle_archive(chat.id)

    validate_api_response("toggle_archive", result)
    event_payload = _last_event(fake_pyotherside_module, "chat-list-update")
    validate_event_payload("chat-list-update", event_payload)
    assert event_payload[0]["archived"] is True
    assert event_payload[0]["muted"] is True
    with GreenlineKV() as kv:
        stored_chat = kv.get_record(f"chat:{chat.id}")
    assert stored_chat is not None
    assert stored_chat.archived is True
    assert main.get_chat_list()["chats"] == []
    assert [entry["id"] for entry in main.get_chat_list(True)["chats"]] == [chat.id]
