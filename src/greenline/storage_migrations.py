from __future__ import annotations

from typing import Any, Callable

from greenline.contracts.kv import GreenlineKV
from greenline.store.records import KVSchemaVersionRecord

SCHEMA_VERSION_KEY = "kv.schema_version"
Migration = Callable[[Any], None]


def initialize_storage_schema(_raw_kv: Any) -> None:
    return None


def remove_gallery_images_field(raw_kv: Any) -> None:
    cursor: str | None = None

    while True:
        rows, cursor = raw_kv.get_partial_page("message:", cursor=cursor)
        wrote_changes = False
        for key, value in rows:
            if not isinstance(value, dict) or "images" not in value:
                continue
            updated_value = dict(value)
            updated_value.pop("images", None)
            raw_kv.put_cached(key, updated_value)
            wrote_changes = True
        if wrote_changes:
            raw_kv.commit_cached()
        if cursor is None:
            break


MIGRATIONS: list[Migration] = [initialize_storage_schema, remove_gallery_images_field]


def run_storage_migrations() -> None:
    with GreenlineKV() as kv:
        current_version = kv.get_record(
            SCHEMA_VERSION_KEY,
            default=KVSchemaVersionRecord(value=0),
        ).value
        latest_version = len(MIGRATIONS)
        if current_version > latest_version:
            raise RuntimeError(f"KV schema version {current_version} is newer than supported {latest_version}")
        raw_kv = getattr(kv, "raw")

        for version, migration in enumerate(MIGRATIONS, start=1):
            if version <= current_version:
                continue
            migration(raw_kv)
            kv.put_record(SCHEMA_VERSION_KEY, KVSchemaVersionRecord(value=version))
            current_version = version
