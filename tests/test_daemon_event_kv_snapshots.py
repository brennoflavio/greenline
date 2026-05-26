from __future__ import annotations

import os

import pytest
from contracts.qml_payloads import assert_json_like
from daemon_event_helpers import (
    dispatch_daemon_fixture_with_buckets,
    kv_diff,
    load_fixtures,
    load_snapshot,
    output_snapshot_path_for_fixture,
    read_kv_snapshot,
    seed_prerequisite_kv,
    snapshot_path_for_fixture,
    validate_kv_snapshot,
    write_output_snapshot,
    write_snapshot,
)

FIXTURES = load_fixtures()


def _written_entries(diff: dict):
    for key, value in diff["added"].items():
        yield key, value
    for key, value in diff["changed"].items():
        yield key, value["after"]


def _assert_empty_diff(fixture, diff: dict) -> None:
    assert diff == {"added": {}, "changed": {}, "deleted": {}}, fixture.relative_path


def _assert_has_written_key(diff: dict, prefix: str, fixture) -> None:
    assert any(
        key.startswith(prefix) for key, _ in _written_entries(diff)
    ), f"{fixture.relative_path} should write a {prefix!r} entry"


def _assert_manifest_storage_intent(fixture, diff: dict) -> None:
    source_family = fixture.manifest_entry.get("source_family")
    if source_family == "message":
        message_entries = [(key, value) for key, value in _written_entries(diff) if key.startswith("message:")]
        assert message_entries, f"{fixture.relative_path} should store a message entry"
        expected_type = fixture.manifest_entry.get("stored_message_type")
        if expected_type:
            assert any(
                value.get("type") == expected_type for _, value in message_entries
            ), f"{fixture.relative_path} should store message type {expected_type!r}"
    elif source_family == "unhandled_message":
        assert (
            f"unhandled_message:{fixture.id}" in diff["added"]
        ), f"{fixture.relative_path} should store an unhandled_message entry"
    elif source_family == "unknown_event":
        assert (
            f"unknown_event:{fixture.event_type}:{fixture.id}" in diff["added"]
        ), f"{fixture.relative_path} should store an unknown_event entry"
    elif source_family in {"parse_only", "presence", "chat_presence"}:
        _assert_empty_diff(fixture, diff)
    elif source_family in {"chat_update", "photo_update"}:
        _assert_has_written_key(diff, "chat:", fixture)
    elif source_family == "receipt":
        _assert_has_written_key(diff, "message:", fixture)
    elif source_family == "history_sync":
        _assert_has_written_key(diff, "chat:", fixture)
        _assert_has_written_key(diff, "message:", fixture)
    else:
        raise AssertionError(f"{fixture.relative_path} has unknown source_family {source_family!r}")


def _assert_empty_output(fixture, output: dict) -> None:
    assert output == {
        "chat_presence_updates": [],
        "chat_updates": {},
        "message_updates": [],
        "message_upserts": [],
        "photo_updates": [],
        "presence_updates": [],
    }, fixture.relative_path


def _assert_manifest_output_intent(fixture, output: dict) -> None:
    source_family = fixture.manifest_entry.get("source_family")
    if source_family == "message":
        assert output["message_upserts"], f"{fixture.relative_path} should emit message_upserts"
        assert output["chat_updates"], f"{fixture.relative_path} should emit chat_updates"
    elif source_family in {"unhandled_message", "unknown_event", "parse_only"}:
        _assert_empty_output(fixture, output)
    elif source_family == "presence":
        assert output["presence_updates"], f"{fixture.relative_path} should emit presence_updates"
    elif source_family == "chat_presence":
        assert output["chat_presence_updates"], f"{fixture.relative_path} should emit chat_presence_updates"
    elif source_family == "receipt":
        assert output["message_updates"], f"{fixture.relative_path} should emit message_updates"
    elif source_family == "chat_update":
        assert output["chat_updates"], f"{fixture.relative_path} should emit chat_updates"
    elif source_family == "photo_update":
        assert output["chat_updates"], f"{fixture.relative_path} should emit chat_updates"
        assert output["photo_updates"], f"{fixture.relative_path} should emit photo_updates"
    elif source_family == "history_sync":
        assert output["chat_updates"], f"{fixture.relative_path} should emit chat_updates"
    else:
        raise AssertionError(f"{fixture.relative_path} has unknown source_family {source_family!r}")


@pytest.mark.parametrize("fixture", FIXTURES, ids=[fixture.param_id for fixture in FIXTURES])
def test_daemon_event_kv_diff_and_output_match_snapshots(fixture) -> None:
    seed_prerequisite_kv(fixture)
    before = read_kv_snapshot()

    result = dispatch_daemon_fixture_with_buckets(fixture)

    after = read_kv_snapshot()
    validate_kv_snapshot(after)
    actual_kv = kv_diff(before, after)
    actual_output = result.as_snapshot()
    assert_json_like(actual_output)
    _assert_manifest_storage_intent(fixture, actual_kv)
    _assert_manifest_output_intent(fixture, actual_output)

    kv_snapshot_path = snapshot_path_for_fixture(fixture)
    output_snapshot_path = output_snapshot_path_for_fixture(fixture)

    if os.environ.get("UPDATE_DAEMON_EVENT_KV_SNAPSHOTS") == "1":
        write_snapshot(kv_snapshot_path, actual_kv)
        write_output_snapshot(fixture, result)

    assert kv_snapshot_path.exists(), f"missing KV snapshot for {fixture.relative_path}: {kv_snapshot_path}"
    assert output_snapshot_path.exists(), f"missing output snapshot for {fixture.relative_path}: {output_snapshot_path}"
    assert actual_kv == load_snapshot(kv_snapshot_path)
    assert actual_output == load_snapshot(output_snapshot_path)
