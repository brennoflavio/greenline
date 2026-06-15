from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from dacite import from_dict
from daemon_event_helpers import load_fixtures, seed_prerequisite_kv

from greenline.contracts.kv import GreenlineKV
from greenline.store.messages import (
    message_event_to_message,
    store_message,
    store_undecryptable_message,
    undecryptable_event_to_message,
)
from greenline.store.repository import message_index_key
from models import MessageType

MESSAGE_FIXTURES = [fixture for fixture in load_fixtures() if fixture.event_type in {"Message", "UndecryptableMessage"}]

FIELD_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "message/conversation.json": {"text": "Fixture message text."},
    "message/extended_text.json": {"text": "Fixture text."},
    "message/link_preview.json": {"link_title": "Fixture text.", "link_url": "Fixture text."},
    "message/image.json": {"mimetype": "image/jpeg"},
    "message/video.json": {"mimetype": "video/mp4", "duration": "0:11"},
    "message/audio.json": {"mimetype": "audio/ogg; codecs=opus", "duration": "0:05"},
    "message/voice.json": {"mimetype": "audio/ogg; codecs=opus", "duration": "0:13"},
    "message/document.json": {"mimetype": "application/pdf", "file_name": "fixture-document.pdf"},
    "message/contact.json": {"mimetype": "text/x-vcard", "file_name": "Fixture text."},
    "message/location.json": {
        "text": "Fixture Place",
        "caption": "1600 Amphitheatre Parkway, Mountain View, CA",
        "link_url": "geo:37.4219999,-122.0840575",
    },
    "message/sticker.json": {"mimetype": "image/webp"},
    "message/template_message.json": {"text": "Fixture text.\n\nFixture text."},
    "message/unhandled_media_gif.json": {"mimetype": "video/mp4", "duration": "0:01"},
    "event/message.json": {"text": "Fixture message text."},
}


def _mapped_message(fixture):
    evt = fixture.parse_payload()
    if fixture.event_type == "UndecryptableMessage":
        return undecryptable_event_to_message(evt, raw=fixture.payload)
    return message_event_to_message(evt, raw=fixture.payload)


@pytest.mark.parametrize("fixture", MESSAGE_FIXTURES, ids=[fixture.param_id for fixture in MESSAGE_FIXTURES])
def test_message_event_to_message_maps_fixture_variants(fixture) -> None:
    message = _mapped_message(fixture)
    source_family = fixture.manifest_entry.get("source_family")
    expected_type = fixture.manifest_entry.get("stored_message_type")

    if source_family in {"unhandled_message", "reaction"} or expected_type == "deleted":
        assert message is None
        return

    assert message is not None
    assert message.id
    assert message.chat_id
    assert "@" in message.chat_id
    assert message.type == MessageType(expected_type)
    assert "@lid" not in message.sender

    for field, expected in FIELD_EXPECTATIONS.get(fixture.relative_path, {}).items():
        assert getattr(message, field) == expected


def test_location_message_marked_live_stays_unhandled() -> None:
    location_fixture = next(fixture for fixture in MESSAGE_FIXTURES if fixture.relative_path == "message/location.json")
    payload = deepcopy(location_fixture.payload)
    payload["Message"]["locationMessage"]["isLive"] = True
    payload["RawMessage"]["locationMessage"]["isLive"] = True

    evt = from_dict(data_class=location_fixture.data_class, data=payload)

    assert message_event_to_message(evt, raw=payload) is None
    assert store_message(evt, raw=payload) is None


@pytest.mark.parametrize("fixture", MESSAGE_FIXTURES, ids=[fixture.param_id for fixture in MESSAGE_FIXTURES])
def test_store_message_fixture_variants_write_expected_kv(fixture) -> None:
    seed_prerequisite_kv(fixture)
    evt = fixture.parse_payload()
    if fixture.event_type == "UndecryptableMessage":
        stored = store_undecryptable_message(evt, raw=fixture.payload)
    else:
        stored = store_message(evt, raw=fixture.payload)

    source_family = fixture.manifest_entry.get("source_family")
    expected_type = fixture.manifest_entry.get("stored_message_type")

    if source_family in {"unhandled_message", "reaction"}:
        assert stored is None
        return

    assert stored is not None
    assert stored.message.type == MessageType(expected_type)
    assert stored.chat.id == stored.message.chat_id

    with GreenlineKV() as kv:
        index_key = message_index_key(stored.message.chat_id, stored.message.id)
        index_record = kv.get_record(index_key)
        assert index_record is not None
        stored_payload = kv.get_record(index_record.value)
        chat_payload = kv.get_record(f"chat:{stored.chat.id}")

    assert stored_payload is not None
    assert stored_payload.type == MessageType(expected_type)
    assert stored_payload.raw == fixture.payload
    assert chat_payload is not None
