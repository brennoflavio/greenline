from __future__ import annotations

import pytest

import greenline.storage_migrations as storage_migrations
from greenline.contracts.kv import GreenlineKV
from greenline.store.records import KVSchemaVersionRecord


def test_run_storage_migrations_persists_bootstrap_version_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object | None] = []

    def bootstrap(raw_kv) -> None:
        calls.append(raw_kv.get(storage_migrations.SCHEMA_VERSION_KEY))

    monkeypatch.setattr(storage_migrations, "MIGRATIONS", [bootstrap])

    storage_migrations.run_storage_migrations()

    with GreenlineKV() as kv:
        version = kv.get_record(storage_migrations.SCHEMA_VERSION_KEY)

    assert calls == [None]
    assert version == KVSchemaVersionRecord(value=1)


def test_run_storage_migrations_runs_pending_in_order_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object | None]] = []

    def migration_one(raw_kv) -> None:
        calls.append(("one", raw_kv.get(storage_migrations.SCHEMA_VERSION_KEY)))

    def migration_two(raw_kv) -> None:
        calls.append(("two", raw_kv.get(storage_migrations.SCHEMA_VERSION_KEY)))

    monkeypatch.setattr(storage_migrations, "MIGRATIONS", [migration_one, migration_two])

    storage_migrations.run_storage_migrations()

    with GreenlineKV() as kv:
        version = kv.get_record(storage_migrations.SCHEMA_VERSION_KEY)

    assert calls == [("one", None), ("two", 1)]
    assert version == KVSchemaVersionRecord(value=2)

    storage_migrations.run_storage_migrations()

    assert calls == [("one", None), ("two", 1)]


def test_run_storage_migrations_skips_completed_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    with GreenlineKV() as kv:
        kv.put_record(storage_migrations.SCHEMA_VERSION_KEY, KVSchemaVersionRecord(value=1))

    calls: list[tuple[str, object | None]] = []

    def migration_one(_raw_kv) -> None:
        raise AssertionError("completed migrations must be skipped")

    def migration_two(raw_kv) -> None:
        calls.append(("two", raw_kv.get(storage_migrations.SCHEMA_VERSION_KEY)))

    def migration_three(raw_kv) -> None:
        calls.append(("three", raw_kv.get(storage_migrations.SCHEMA_VERSION_KEY)))

    monkeypatch.setattr(storage_migrations, "MIGRATIONS", [migration_one, migration_two, migration_three])

    storage_migrations.run_storage_migrations()

    with GreenlineKV() as kv:
        version = kv.get_record(storage_migrations.SCHEMA_VERSION_KEY)

    assert calls == [("two", 1), ("three", 2)]
    assert version == KVSchemaVersionRecord(value=3)


def test_run_storage_migrations_only_bumps_completed_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object | None]] = []

    def migration_one(raw_kv) -> None:
        calls.append(("one", raw_kv.get(storage_migrations.SCHEMA_VERSION_KEY)))

    def migration_two(raw_kv) -> None:
        calls.append(("two", raw_kv.get(storage_migrations.SCHEMA_VERSION_KEY)))
        raise RuntimeError("boom")

    monkeypatch.setattr(storage_migrations, "MIGRATIONS", [migration_one, migration_two])

    with pytest.raises(RuntimeError, match="boom"):
        storage_migrations.run_storage_migrations()

    with GreenlineKV() as kv:
        version = kv.get_record(storage_migrations.SCHEMA_VERSION_KEY)

    assert calls == [("one", None), ("two", 1)]
    assert version == KVSchemaVersionRecord(value=1)


def test_run_storage_migrations_rejects_newer_schema_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    with GreenlineKV() as kv:
        kv.put_record(storage_migrations.SCHEMA_VERSION_KEY, KVSchemaVersionRecord(value=99))

    monkeypatch.setattr(storage_migrations, "MIGRATIONS", [lambda _raw_kv: None])

    with pytest.raises(RuntimeError, match="newer than supported 1"):
        storage_migrations.run_storage_migrations()
