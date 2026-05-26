from __future__ import annotations

from typing import Any

from conftest import fake_pyotherside
from contracts.qml_payloads import assert_event_payload
from daemon_event_helpers import (
    load_fixtures,
    normalize_snapshot_value,
    seed_prerequisite_kv,
)

from ut_components.kv import KV

LAST_EVENT_ID_KEY = "daemon:last_event_id"

FIXTURE_BY_PATH = {fixture.relative_path: fixture for fixture in load_fixtures()}


def _fixture_event(path: str, *, event_id: int | None = None):
    event = FIXTURE_BY_PATH[path].stored_event()
    if event_id is not None:
        event.id = event_id
    return event


def _ignored_events(start: int, count: int):
    import daemon_types

    return [daemon_types.StoredEvent(id=start + offset, event_type="AppState", payload="{}") for offset in range(count)]


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
    with KV() as kv:
        assert kv.get(LAST_EVENT_ID_KEY) == 39
        assert kv.get("chat:fixture-chat-1@s.whatsapp.net") is not None
        assert kv.get("message:fixture-chat-1@s.whatsapp.net:1735732800:fixture-message-001") is not None


def test_daemon_event_handler_emits_batched_qml_payloads(fake_daemon_rpc) -> None:
    from greenline.events.chat_sync import DaemonEventHandler

    picture_fixture = FIXTURE_BY_PATH["event/picture_update.json"]
    seed_prerequisite_kv(picture_fixture)
    fake_daemon_rpc.queue_events(
        [
            _fixture_event("message/conversation.json"),
            _fixture_event("event/picture_update.json", event_id=36),
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
    with KV() as kv:
        assert kv.get(LAST_EVENT_ID_KEY) == 1097
