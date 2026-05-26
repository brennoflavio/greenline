from __future__ import annotations

from typing import Any

import pytest
from daemon_event_helpers import load_fixtures, seed_prerequisite_kv

from greenline.store.messages import (
    message_event_to_message,
    store_message,
    store_undecryptable_message,
    undecryptable_event_to_message,
)
from greenline.store.repository import message_index_key
from models import MessageType
from ut_components.kv import KV

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

    if source_family == "unhandled_message" or expected_type == "deleted":
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

    if source_family == "unhandled_message":
        assert stored is None
        return

    assert stored is not None
    assert stored.message.type == MessageType(expected_type)
    assert stored.chat.id == stored.message.chat_id

    with KV() as kv:
        index_key = message_index_key(stored.message.chat_id, stored.message.id)
        storage_key = kv.get(index_key)
        assert isinstance(storage_key, str)
        stored_payload = kv.get(storage_key)
        chat_payload = kv.get(f"chat:{stored.chat.id}")

    assert stored_payload is not None
    assert stored_payload["type"] == expected_type
    assert stored_payload["raw"] == fixture.payload
    assert chat_payload is not None
