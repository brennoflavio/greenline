from __future__ import annotations

import pytest

import greenline.storage_migrations as storage_migrations
from greenline.contracts.codecs import encode_dataclass
from greenline.contracts.kv import GreenlineKV
from greenline.store.records import KVSchemaVersionRecord, stored_message_record
from models import Message, MessageType, ReadReceipt


def _legacy_message_payload(message_id: str) -> dict[str, object]:
    return {
        "chat_id": "chat-1",
        "message_id": message_id,
        "sender": "sender@s.whatsapp.net",
        "body": "hello",
        "caption": "",
        "quoted_message_id": "",
        "quoted_message_sender": "",
        "quoted_message_body": "",
        "footer": "",
        "timestamp": 1,
        "from_me": False,
        "read": False,
        "received": True,
        "sent": False,
        "pending": False,
        "message_type": "text",
        "mime_type": "",
        "media_url": "",
        "media_key": "",
        "media_file_name": "",
        "media_wa_type": "",
        "duration": 0,
        "latitude": None,
        "longitude": None,
        "location_name": "",
        "location_address": "",
        "vcard_data": "",
        "thumbnail_path": None,
        "thumbnail_width": None,
        "thumbnail_height": None,
        "image_width": None,
        "image_height": None,
        "image_size_bytes": None,
        "audio_size_bytes": None,
        "reply_to": None,
        "edited_at": None,
        "deleted": False,
        "media_download": {
            "media_type": "",
            "direct_path": "",
            "media_key": "",
            "file_enc_sha256": "",
            "file_sha256": "",
            "file_length": 0,
            "mimetype": "",
            "file_name": "",
        },
        "reply_quote_payload_json": "",
        "raw": None,
        "images": [],
        "mentions": [],
        "mention_spans": [],
    }


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


def test_remove_gallery_images_field_rewrites_message_records_and_advances_schema() -> None:
    legacy_message = _legacy_message_payload("msg-1")
    untouched_unhandled = {
        "event_id": 1,
        "info_type": "message",
        "media_type": "collection",
        "chat": "chat-1",
        "sender": "sender@s.whatsapp.net",
        "message_id": "msg-2",
        "timestamp": "1",
        "payload": "{}",
        "images": [],
    }

    with GreenlineKV() as kv:
        kv.raw.put(storage_migrations.SCHEMA_VERSION_KEY, 1)
        kv.raw.put("message:msg-1", legacy_message)
        kv.raw.put("unhandled_message:msg-2", untouched_unhandled)

    storage_migrations.run_storage_migrations()

    with GreenlineKV() as kv:
        migrated_message = kv.raw.get("message:msg-1")
        untouched_after = kv.raw.get("unhandled_message:msg-2")
        version = kv.get_record(storage_migrations.SCHEMA_VERSION_KEY)

    assert migrated_message is not None
    assert "images" not in migrated_message
    assert untouched_after == untouched_unhandled
    assert version == KVSchemaVersionRecord(value=3)


def test_remove_gallery_images_field_commits_in_batches_for_large_message_sets() -> None:
    with GreenlineKV() as kv:
        kv.raw.put(storage_migrations.SCHEMA_VERSION_KEY, 1)
        for index in range(400):
            kv.raw.put(f"message:msg-{index:03d}", _legacy_message_payload(f"msg-{index:03d}"))

    storage_migrations.run_storage_migrations()

    with GreenlineKV() as kv:
        first_message = kv.raw.get("message:msg-000")
        last_message = kv.raw.get("message:msg-399")
        version = kv.get_record(storage_migrations.SCHEMA_VERSION_KEY)

    assert first_message is not None
    assert last_message is not None
    assert "images" not in first_message
    assert "images" not in last_message
    assert version == KVSchemaVersionRecord(value=3)


def test_remove_gallery_images_field_preserves_strict_kv_decode_for_current_message_records() -> None:
    legacy_record = stored_message_record(
        Message(
            id="msg-1",
            chat_id="chat-1",
            type=MessageType.TEXT,
            is_outgoing=False,
            timestamp="12:34",
            timestamp_unix=1234,
            read_receipt=ReadReceipt.NONE,
            sender="sender@s.whatsapp.net",
            sender_raw="sender@s.whatsapp.net",
            text="hello",
        )
    )
    legacy_payload = encode_dataclass(legacy_record, boundary="kv", contract="message:", direction="encode")
    legacy_payload["images"] = []

    with GreenlineKV() as kv:
        kv.raw.put(storage_migrations.SCHEMA_VERSION_KEY, 1)
        kv.raw.put("message:msg-1", legacy_payload)

    storage_migrations.run_storage_migrations()

    with GreenlineKV() as kv:
        record = kv.get_record("message:msg-1", required=True)

    assert record is not None
    assert record.id == "msg-1"
    assert record.text == "hello"


def test_remove_legacy_ui_message_fields_preserves_strict_kv_decode() -> None:
    record = stored_message_record(
        Message(
            id="msg-1",
            chat_id="chat-1",
            type=MessageType.TEXT,
            is_outgoing=False,
            timestamp="12:34",
            timestamp_unix=1234,
            read_receipt=ReadReceipt.NONE,
            sender="sender@s.whatsapp.net",
            sender_raw="sender@s.whatsapp.net",
            text="hello",
        )
    )
    payload = encode_dataclass(record, boundary="kv", contract="message:", direction="encode")
    payload["reply_to_sender"] = "Sender Name"
    payload["sender_name"] = "Sender Name"
    payload["sender_photo"] = "/tmp/sender.jpg"

    with GreenlineKV() as kv:
        kv.raw.put(storage_migrations.SCHEMA_VERSION_KEY, 2)
        kv.raw.put("message:msg-1", payload)

    storage_migrations.run_storage_migrations()

    with GreenlineKV() as kv:
        migrated_payload = kv.raw.get("message:msg-1")
        migrated_record = kv.get_record("message:msg-1", required=True)
        version = kv.get_record(storage_migrations.SCHEMA_VERSION_KEY)

    assert migrated_payload is not None
    assert "reply_to_sender" not in migrated_payload
    assert "sender_name" not in migrated_payload
    assert "sender_photo" not in migrated_payload
    assert migrated_record is not None
    assert migrated_record.id == "msg-1"
    assert migrated_record.text == "hello"
    assert version == KVSchemaVersionRecord(value=3)
