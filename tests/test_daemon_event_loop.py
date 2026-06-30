from __future__ import annotations

import json
from typing import Any

from conftest import fake_pyotherside
from contracts.qml_payloads import assert_event_payload
from daemon_event_helpers import (
    load_fixtures,
    normalize_snapshot_value,
    seed_prerequisite_kv,
)
from qml_contract_helpers import DEFAULT_SENDER_ID, seed_chat, seed_message

import daemon_types
from greenline.contracts.kv import GreenlineKV
from greenline.store.records import DaemonLastEventIDRecord

LAST_EVENT_ID_KEY = "daemon:last_event_id"

FIXTURE_BY_PATH = {fixture.relative_path: fixture for fixture in load_fixtures()}


def _fixture_event(path: str, *, event_id: int | None = None):
    event = FIXTURE_BY_PATH[path].stored_event()
    if event_id is not None:
        event.id = event_id
    return event


def _ignored_events(start: int, count: int):
    import daemon_types

    return [
        daemon_types.StoredEvent(id=start + offset, event_type="AppState", payload="{}", created_at=0)
        for offset in range(count)
    ]


def _payloads_for(event_name: str) -> list[Any]:
    return [normalize_snapshot_value(payload) for name, payload in fake_pyotherside.sent if name == event_name]


def test_process_events_once_advances_and_deletes_processed_events(fake_daemon_rpc) -> None:
    from greenline.events.chat_sync import process_events_once

    fake_daemon_rpc.queue_events(
        [
            _fixture_event("message/conversation.json"),
            _fixture_event("event/presence_online.json"),
        ]
    )

    process_events_once(batch_limit=7)

    assert fake_daemon_rpc.list_events_calls == [{"after_id": 0, "limit": 7}]
    assert fake_daemon_rpc.delete_events_calls == [39]
    with GreenlineKV() as kv:
        assert kv.get_record(LAST_EVENT_ID_KEY) == DaemonLastEventIDRecord(39)
        assert kv.get_record("chat:fixture-chat-1@s.whatsapp.net") is not None
        assert kv.get_record("message:fixture-chat-1@s.whatsapp.net:1735732800:fixture-message-001") is not None


def test_daemon_event_handler_emits_batched_qml_payloads(fake_daemon_rpc) -> None:
    from greenline.events.chat_sync import DaemonEventHandler

    avatar_fixture = FIXTURE_BY_PATH["event/avatar_sync.json"]
    seed_prerequisite_kv(avatar_fixture)
    fake_daemon_rpc.queue_events(
        [
            _fixture_event("message/conversation.json"),
            _fixture_event("event/avatar_sync.json", event_id=36),
            *_ignored_events(100, 498),
        ],
        [
            _fixture_event("event/presence_online.json", event_id=598),
            _fixture_event("event/chatpresence.json", event_id=599),
            *_ignored_events(600, 498),
        ],
        [],
    )

    DaemonEventHandler()._do_trigger()

    assert fake_daemon_rpc.list_events_calls == [
        {"after_id": 0, "limit": 500},
        {"after_id": 597, "limit": 500},
        {"after_id": 1097, "limit": 500},
    ]
    assert fake_daemon_rpc.delete_events_calls == [597, 1097]
    assert fake_pyotherside.sent[0] == ("sync-status", True)
    assert fake_pyotherside.sent[-1] == ("sync-status", False)

    emitted_names = [name for name, _ in fake_pyotherside.sent]
    for expected_name in (
        "message-upsert",
        "chat-list-update",
        "sender-photo-update",
        "presence-update",
        "chat-presence",
    ):
        assert expected_name in emitted_names
        for payload in _payloads_for(expected_name):
            assert_event_payload(expected_name, payload)

    assert _payloads_for("message-upsert")[0][0]["id"] == "fixture-message-001"
    assert any(chat["id"] == "fixture-chat-1@s.whatsapp.net" for chat in _payloads_for("chat-list-update")[0])
    assert _payloads_for("sender-photo-update")[0] == [
        {
            "jid": "fixture-chat-43@s.whatsapp.net",
            "photo": "file://<CACHE>/greenline.tests/avatars/fixture-chat-43@s.whatsapp.net.jpg",
        }
    ]
    assert _payloads_for("presence-update")[0] == [{"jid": "fixture-user-46@s.whatsapp.net", "status": "online"}]
    assert _payloads_for("chat-presence")[0] == [
        {
            "chat": "fixture-chat-1@s.whatsapp.net",
            "is_group": False,
            "media": "",
            "sender": "fixture-user-29@lid",
            "state": "composing",
        }
    ]
    with GreenlineKV() as kv:
        assert kv.get_record(LAST_EVENT_ID_KEY) == DaemonLastEventIDRecord(1097)


def test_picture_event_is_parse_only_for_avatar_updates(fake_daemon_rpc) -> None:
    from greenline.events.handlers import dispatch_event

    chat = seed_chat(DEFAULT_SENDER_ID, photo="file:///tmp/existing.jpg", muted=False)

    event = daemon_types.StoredEvent(
        id=9000,
        event_type="Picture",
        payload=json.dumps(
            {
                "JID": DEFAULT_SENDER_ID,
                "Author": "",
                "Timestamp": "2026-01-01T00:00:00Z",
                "Remove": False,
                "PictureID": "new-picture",
            }
        ),
        created_at=0,
    )

    chat_updates = {}
    photo_updates = []
    dispatch_event(event, chat_updates, [], [], photo_updates, [], [])

    assert chat_updates == {}
    assert photo_updates == []
    with GreenlineKV() as kv:
        assert kv.get_record(f"chat:{chat.id}").photo == "file:///tmp/existing.jpg"


def test_chat_list_update_event_does_not_clear_existing_photo_on_empty_avatar_path(fake_daemon_rpc) -> None:
    from greenline.events.chat_sync import ChatListUpdateEvent

    chat = seed_chat(
        DEFAULT_SENDER_ID,
        name="Full Name",
        photo="file:///tmp/existing.jpg",
        muted=False,
        full_name="Full Name",
        push_name="Push Name",
        business_name="Business Name",
    )
    fake_daemon_rpc.contacts = [
        daemon_types.Contact(
            jid=DEFAULT_SENDER_ID,
            display_name="Full Name",
            first_name="Full",
            full_name="Full Name",
            push_name="Push Name",
            business_name="Business Name",
            avatar_path="",
        )
    ]

    ChatListUpdateEvent().trigger(None)

    assert _payloads_for("chat-list-update") == []
    assert _payloads_for("sender-photo-update") == []
    with GreenlineKV() as kv:
        assert kv.get_record(f"chat:{chat.id}").photo == "file:///tmp/existing.jpg"


def test_history_sync_event_prioritizes_recent_missing_avatars(fake_daemon_rpc) -> None:
    from greenline.events.handlers import dispatch_event

    event = _fixture_event("history_sync/conversation_text.json", event_id=9001)

    dispatch_event(event, {}, [], [], [], [], [])

    assert fake_daemon_rpc.prioritize_avatars_calls == [["fixture-chat-47@s.whatsapp.net"]]


def test_avatar_sync_remove_event_still_clears_existing_photo(fake_daemon_rpc) -> None:
    from greenline.events.handlers import dispatch_event

    chat = seed_chat(DEFAULT_SENDER_ID, photo="file:///tmp/existing.jpg", muted=False)

    event = daemon_types.StoredEvent(
        id=9002,
        event_type="AvatarSync",
        payload=json.dumps(
            {
                "JID": DEFAULT_SENDER_ID,
                "AvatarPath": "",
                "Remove": True,
            }
        ),
        created_at=0,
    )

    chat_updates = {}
    photo_updates = []
    dispatch_event(event, chat_updates, [], [], photo_updates, [], [])

    assert photo_updates == [{"jid": DEFAULT_SENDER_ID, "photo": ""}]
    assert chat_updates[chat.id]["photo"] == ""
    with GreenlineKV() as kv:
        assert kv.get_record(f"chat:{chat.id}").photo == ""


def test_reaction_event_uses_info_chat_to_update_direct_chat_message(fake_daemon_rpc) -> None:
    import main
    from greenline.events.chat_sync import DaemonEventHandler

    chat_id = "peer@s.whatsapp.net"
    sender_id = "peer@s.whatsapp.net"
    seed_chat(chat_id, unread_count=0, is_group=False, muted=False)
    seed_message(chat_id, "outgoing-1", is_outgoing=True, sender="", sender_raw="", text="Hello", reply_to_id="")

    payload = json.loads(json.dumps(FIXTURE_BY_PATH["message/reaction_ignored.json"].payload))
    payload["Info"]["Chat"] = "peer@lid"
    payload["Info"]["IsGroup"] = False
    payload["Info"]["Sender"] = "peer@lid"
    payload["Info"]["SenderAlt"] = sender_id
    payload["Info"]["PushName"] = "Peer"
    payload["Message"]["reactionMessage"]["key"]["ID"] = "outgoing-1"
    payload["Message"]["reactionMessage"]["key"]["remoteJID"] = "self@s.whatsapp.net"
    payload["Message"]["reactionMessage"]["key"]["participant"] = sender_id
    payload["Message"]["reactionMessage"]["text"] = "👍"

    fake_daemon_rpc.ensure_jid_map = {
        "peer@lid": chat_id,
        sender_id: sender_id,
        "self@s.whatsapp.net": "self@s.whatsapp.net",
    }
    fake_daemon_rpc.queue_events(
        [daemon_types.StoredEvent(id=9001, event_type="Message", payload=json.dumps(payload), created_at=0)]
    )

    DaemonEventHandler()._do_trigger()

    emitted = _payloads_for("message-upsert")
    assert emitted
    assert any(
        message["id"] == "outgoing-1" and message["has_reactions"] is True for batch in emitted for message in batch
    )

    messages = main.get_messages(chat_id)
    assert any(message["id"] == "outgoing-1" and message["has_reactions"] is True for message in messages["messages"])

    with GreenlineKV() as kv:
        assert kv.get_record(f"message_reaction:{chat_id}:outgoing-1:{sender_id}") is not None
        assert kv.get_record(f"message_reaction:self@s.whatsapp.net:outgoing-1:{sender_id}") is None
