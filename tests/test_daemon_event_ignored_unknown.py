from __future__ import annotations

import json

from daemon_event_helpers import (
    DispatchResult,
    kv_diff,
    read_kv_snapshot,
    validate_kv_snapshot,
)
from test_daemon_event_coverage import DAEMON_EVENT_CONTRACTS

import daemon_types
from greenline.events.handlers import dispatch_event

EMPTY_OUTPUT = {
    "chat_presence_updates": [],
    "chat_updates": {},
    "message_updates": [],
    "message_upserts": [],
    "photo_updates": [],
    "presence_updates": [],
}


def _dispatch_stored_event(event: daemon_types.StoredEvent) -> DispatchResult:
    chat_updates = {}
    message_upserts = []
    message_updates = []
    photo_updates = []
    presence_updates = []
    chat_presence_updates = []
    dispatch_event(
        event,
        chat_updates,
        message_upserts,
        message_updates,
        photo_updates,
        presence_updates,
        chat_presence_updates,
    )
    return DispatchResult(
        chat_updates=chat_updates,
        message_upserts=message_upserts,
        message_updates=message_updates,
        photo_updates=photo_updates,
        presence_updates=presence_updates,
        chat_presence_updates=chat_presence_updates,
    )


def test_ignored_event_types_do_not_write_kv_or_outputs() -> None:
    ignored_event_types = [
        event_type for event_type, classification in DAEMON_EVENT_CONTRACTS.items() if classification == "ignored"
    ]

    for index, event_type in enumerate(ignored_event_types, start=1):
        before = read_kv_snapshot()
        result = _dispatch_stored_event(
            daemon_types.StoredEvent(id=1000 + index, event_type=event_type, payload="{}", created_at=0)
        )
        after = read_kv_snapshot()

        assert result.as_snapshot() == EMPTY_OUTPUT, event_type
        assert kv_diff(before, after) == {"added": {}, "changed": {}, "deleted": {}}, event_type


def test_unknown_event_type_stores_json_payload_without_outputs() -> None:
    event = daemon_types.StoredEvent(
        id=2001,
        event_type="FixtureUnknownEvent",
        payload=json.dumps({"fixture": True}),
        created_at=0,
    )

    before = read_kv_snapshot()
    result = _dispatch_stored_event(event)
    after = read_kv_snapshot()
    validate_kv_snapshot(after)
    diff = kv_diff(before, after)

    assert result.as_snapshot() == EMPTY_OUTPUT
    assert diff == {
        "added": {
            "unknown_event:FixtureUnknownEvent:2001": {
                "event_type": "FixtureUnknownEvent",
                "payload": '{"fixture": true}',
            }
        },
        "changed": {},
        "deleted": {},
    }
    json.loads(diff["added"]["unknown_event:FixtureUnknownEvent:2001"]["payload"])
