from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from dacite import from_dict
from daemon_event_helpers import load_fixtures, seed_prerequisite_kv

from greenline.contracts.kv import GreenlineKV
from greenline.store.media import parse_location_coordinates, parse_location_link_url
from greenline.store.messages import (
    message_event_to_message,
    store_message,
    store_undecryptable_message,
    undecryptable_event_to_message,
    unsupported_message_text,
)
from greenline.store.repository import message_index_key
from history_sync import _message_preview, _resolve_type_and_fallback_text
from models import MessageType

MESSAGE_FIXTURES = [fixture for fixture in load_fixtures() if fixture.event_type in {"Message", "UndecryptableMessage"}]

FIELD_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "message/buttons_message.json": {"text": "Unsupported Message type arrived: buttonsMessage"},
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
    "message/livelocation.json": {
        "text": "0.0, 0.0",
        "caption": "",
        "link_url": "geo:0.0,0.0",
    },
    "message/sticker.json": {"mimetype": "image/webp"},
    "message/template_button_reply.json": {"text": "Unsupported Message type arrived: templateButtonReplyMessage"},
    "message/template_message.json": {"text": "Fixture text.\n\nFixture text."},
    "message/unhandled_media_collection.json": {"text": "Unsupported Message type arrived: collection"},
    "message/unhandled_media_contact_array.json": {"text": "Unsupported Message type arrived: contact_array"},
    "message/unhandled_media_gif.json": {"mimetype": "video/mp4", "duration": "0:01"},
    "message/unhandled_medianotify.json": {"text": "Unsupported Message type arrived: medianotify"},
    "message/unhandled_poll.json": {"text": "Unsupported Message type arrived: poll"},
    "message/unhandled_text.json": {"text": "Unsupported Message type arrived: protocolMessage"},
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


def test_live_location_variants_normalize_to_location() -> None:
    location_fixture = next(fixture for fixture in MESSAGE_FIXTURES if fixture.relative_path == "message/location.json")
    payload = deepcopy(location_fixture.payload)
    payload["Message"]["locationMessage"]["isLive"] = True
    payload["RawMessage"]["locationMessage"]["isLive"] = True

    evt = from_dict(data_class=location_fixture.data_class, data=payload)
    mapped_location = message_event_to_message(evt, raw=payload)
    stored_location = store_message(evt, raw=payload)

    assert mapped_location is not None
    assert mapped_location.type == MessageType.LOCATION
    assert mapped_location.text == "37.4219999, -122.0840575"
    assert mapped_location.caption == "1600 Amphitheatre Parkway, Mountain View, CA"
    assert mapped_location.link_url == "geo:37.4219999,-122.0840575"
    assert stored_location is not None
    assert stored_location.message.type == MessageType.LOCATION

    live_fixture = next(fixture for fixture in MESSAGE_FIXTURES if fixture.relative_path == "message/livelocation.json")
    mapped_live = _mapped_message(live_fixture)

    assert mapped_live is not None
    assert mapped_live.type == MessageType.LOCATION
    assert mapped_live.text == "0.0, 0.0"
    assert mapped_live.link_url == "geo:0.0,0.0"


def test_parse_location_link_url_round_trips_coordinates() -> None:
    assert parse_location_coordinates(37.4219999, -122.0840575) == (37.4219999, -122.0840575)
    assert parse_location_link_url("geo:37.4219999,-122.0840575") == (37.4219999, -122.0840575)
    assert parse_location_link_url("geo:37.4219999,-122.0840575;u=35") == (37.4219999, -122.0840575)
    assert parse_location_link_url("geo:37.4219999,-122.0840575?z=15") == (37.4219999, -122.0840575)
    assert parse_location_link_url("geo:91,0") is None
    assert parse_location_link_url("geo:37.4219999") is None
    assert parse_location_link_url("") is None


def test_history_sync_unsupported_message_falls_back_to_text_preview() -> None:
    content = {"protocolMessage": {"type": 9}}

    msg_type, fallback_text = _resolve_type_and_fallback_text(content)
    preview, mentioned_jids = _message_preview(content, {})

    assert msg_type == MessageType.TEXT
    assert fallback_text == "Unsupported Message type arrived: protocolMessage"
    assert preview == fallback_text
    assert mentioned_jids == []


def test_history_sync_ignores_sender_key_distribution_messages() -> None:
    content = {"senderKeyDistributionMessage": {"groupID": "fixture-group-20@g.us"}}

    msg_type, fallback_text = _resolve_type_and_fallback_text(content)
    preview, mentioned_jids = _message_preview(content, {})

    assert msg_type is None
    assert fallback_text == ""
    assert preview == ""
    assert mentioned_jids == []


def test_unsupported_message_text_ignores_supported_metadata_only_events() -> None:
    assert unsupported_message_text(info_type="text") is None
    assert unsupported_message_text({"messageContextInfo": {}}, info_type="text") is None
    assert unsupported_message_text({"senderKeyDistributionMessage": {"groupID": "fixture-group-20@g.us"}}) is None


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
