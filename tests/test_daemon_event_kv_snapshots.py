from __future__ import annotations

import os

import pytest
from daemon_event_helpers import (
    dispatch_daemon_fixture,
    kv_diff,
    load_fixtures,
    load_snapshot,
    read_kv_snapshot,
    seed_prerequisite_kv,
    snapshot_path_for_fixture,
    validate_kv_snapshot,
    write_snapshot,
)

FIXTURES = load_fixtures()


def _written_entries(diff: dict):
    for key, value in diff["added"].items():
        yield key, value
    for key, value in diff["changed"].items():
        yield key, value["after"]


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


@pytest.mark.parametrize("fixture", FIXTURES, ids=[fixture.param_id for fixture in FIXTURES])
def test_daemon_event_kv_diff_matches_snapshot(fixture) -> None:
    seed_prerequisite_kv(fixture)
    before = read_kv_snapshot()

    dispatch_daemon_fixture(fixture)

    after = read_kv_snapshot()
    validate_kv_snapshot(after)
    actual = kv_diff(before, after)
    _assert_manifest_storage_intent(fixture, actual)
    snapshot_path = snapshot_path_for_fixture(fixture)

    if os.environ.get("UPDATE_DAEMON_EVENT_KV_SNAPSHOTS") == "1":
        write_snapshot(snapshot_path, actual)

    assert snapshot_path.exists(), f"missing KV snapshot for {fixture.relative_path}: {snapshot_path}"
    assert actual == load_snapshot(snapshot_path)
