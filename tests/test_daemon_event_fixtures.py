from __future__ import annotations

from typing import Any

import pytest
from daemon_event_helpers import (
    EVENT_DATACLASSES,
    FIXTURE_ROOT,
    SNAPSHOT_ROOT,
    load_fixtures,
    manifest_entries,
)

FIXTURES = load_fixtures()

JID_FIELD_NAMES = {
    "broadcastlistowner",
    "callcreator",
    "callcreatoralt",
    "chat",
    "destinationjid",
    "from",
    "groupid",
    "groupjid",
    "jid",
    "jidalt",
    "lid",
    "namesetby",
    "namesetbypn",
    "ownerjid",
    "ownerpn",
    "participant",
    "phonenumber",
    "recipientalt",
    "remotejid",
    "sender",
    "senderalt",
    "senderpn",
    "targetchat",
    "targetsender",
    "threadmessagesenderjid",
    "topicsetby",
    "topicsetbypn",
}
JID_LIST_FIELD_NAMES = {"broadcastrecipients", "join", "leave", "promote"}
ALLOWED_JIDS = {"status@broadcast"}


def _is_jid_field(key: str) -> bool:
    lower = key.lower()
    return lower in JID_FIELD_NAMES or lower.endswith("jid") or lower.endswith("pn")


def _valid_fixture_jid(value: str) -> bool:
    if value == "" or value in ALLOWED_JIDS:
        return True
    return value.startswith("fixture-") and "@" in value


def _assert_valid_jid_value(fixture_path: str, key_path: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        assert _valid_fixture_jid(value), f"{fixture_path}:{key_path} has non-fixture JID value {value!r}"
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_valid_jid_value(fixture_path, f"{key_path}[{index}]", item)
        return
    assert value in ({}, []), f"{fixture_path}:{key_path} has non-string JID value {value!r}"


def _assert_fixture_jids(fixture_path: str, value: Any, key_path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{key_path}.{key}"
            lower = key.lower()
            if _is_jid_field(key) or lower in JID_LIST_FIELD_NAMES:
                _assert_valid_jid_value(fixture_path, child_path, child)
            _assert_fixture_jids(fixture_path, child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_fixture_jids(fixture_path, child, f"{key_path}[{index}]")


def test_manifest_entries_match_loaded_fixtures() -> None:
    entries = manifest_entries()
    assert len(FIXTURES) == len(entries)
    assert [fixture.relative_path for fixture in FIXTURES] == [entry["path"] for entry in entries]


def test_manifest_covers_every_fixture_json() -> None:
    manifest_paths = {entry["path"] for entry in manifest_entries()}
    fixture_paths = {
        path.relative_to(FIXTURE_ROOT).as_posix()
        for path in FIXTURE_ROOT.rglob("*.json")
        if path.name != "manifest.json"
    }
    assert fixture_paths == manifest_paths


def test_manifest_and_kv_snapshots_match() -> None:
    expected_snapshots = {fixture.relative_path.replace(".json", ".kv.json") for fixture in FIXTURES}
    actual_snapshots = {path.relative_to(SNAPSHOT_ROOT).as_posix() for path in SNAPSHOT_ROOT.rglob("*.json")}
    assert actual_snapshots == expected_snapshots


@pytest.mark.parametrize("fixture", FIXTURES, ids=[fixture.param_id for fixture in FIXTURES])
def test_fixture_file_shape_and_payload_parse(fixture) -> None:
    assert fixture.path.exists(), f"missing fixture {fixture.relative_path}"
    assert fixture.path.is_file(), f"fixture is not a file {fixture.relative_path}"
    assert fixture.path.parent.is_relative_to(FIXTURE_ROOT)

    assert isinstance(fixture.data.get("id"), int), fixture.relative_path
    assert fixture.event_type in EVENT_DATACLASSES, fixture.relative_path
    assert isinstance(fixture.data.get("payload"), dict), fixture.relative_path
    assert isinstance(fixture.data.get("_meta"), dict), fixture.relative_path
    assert fixture.data["event_type"] == fixture.manifest_entry["event_type"], fixture.relative_path

    fixture.parse_payload()


@pytest.mark.parametrize("fixture", FIXTURES, ids=[fixture.param_id for fixture in FIXTURES])
def test_fixture_jid_fields_are_sanitized(fixture) -> None:
    _assert_fixture_jids(fixture.relative_path, fixture.payload)
