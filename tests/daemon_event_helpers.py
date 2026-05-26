from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from dacite import from_dict

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import daemon_types
import whatsmeow_types
from greenline.store.repository import message_storage_key, put_message_index
from models import ChatListItem, Message, MessageType, ReadReceipt
from ut_components.kv import KV

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "daemon_events"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
SNAPSHOT_ROOT = Path(__file__).parent / "fixtures" / "daemon_event_kv_snapshots"

EVENT_DATACLASSES: dict[str, type[Any]] = {
    "Blocklist": whatsmeow_types.BlocklistEvent,
    "CallReject": whatsmeow_types.CallRejectEvent,
    "ChatPresence": whatsmeow_types.ChatPresenceEvent,
    "GroupInfo": whatsmeow_types.GroupInfoEvent,
    "IdentityChange": whatsmeow_types.IdentityChangeEvent,
    "JoinedGroup": whatsmeow_types.JoinedGroupEvent,
    "Message": whatsmeow_types.MessageEvent,
    "UndecryptableMessage": whatsmeow_types.UndecryptableMessageEvent,
    "UserAbout": whatsmeow_types.UserAboutEvent,
}


@dataclass(frozen=True)
class DaemonEventFixture:
    manifest_entry: dict[str, Any]
    path: Path
    data: dict[str, Any]

    @property
    def id(self) -> int:
        return int(self.data["id"])

    @property
    def event_type(self) -> str:
        return str(self.data["event_type"])

    @property
    def payload(self) -> dict[str, Any]:
        return self.data["payload"]

    @property
    def meta(self) -> dict[str, Any]:
        return self.data.get("_meta", {})

    @property
    def relative_path(self) -> str:
        return self.manifest_entry["path"]

    @property
    def param_id(self) -> str:
        return self.relative_path.removesuffix(".json").replace("/", "__")

    @property
    def data_class(self) -> type[Any]:
        return EVENT_DATACLASSES[self.event_type]

    def parse_payload(self) -> Any:
        return from_dict(data_class=self.data_class, data=self.payload)

    def stored_event(self) -> daemon_types.StoredEvent:
        return daemon_types.StoredEvent(
            id=self.id,
            event_type=self.event_type,
            payload=json.dumps(self.payload, sort_keys=True),
            created_at=0,
        )


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text())


def manifest_entries() -> list[dict[str, Any]]:
    return list(load_manifest()["fixtures"])


def _safe_relative_path(path: str) -> Path:
    relative = Path(path)
    assert not relative.is_absolute(), f"fixture path must be relative: {path}"
    assert ".." not in relative.parts, f"fixture path must stay under fixture root: {path}"
    return relative


def fixture_path(entry: dict[str, Any]) -> Path:
    path = (FIXTURE_ROOT / _safe_relative_path(entry["path"])).resolve()
    assert path.is_relative_to(FIXTURE_ROOT.resolve()), f"fixture path escapes fixture root: {entry['path']}"
    return path


def load_fixture(entry: dict[str, Any]) -> DaemonEventFixture:
    path = fixture_path(entry)
    return DaemonEventFixture(
        manifest_entry=entry,
        path=path,
        data=json.loads(path.read_text()),
    )


def load_fixtures() -> list[DaemonEventFixture]:
    return [load_fixture(entry) for entry in manifest_entries()]


def _normalize_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    normalized = value
    replacements = {
        os.environ.get("XDG_CACHE_HOME", ""): "<CACHE>",
        os.environ.get("XDG_CONFIG_HOME", ""): "<CONFIG>",
    }
    for prefix, placeholder in replacements.items():
        if prefix:
            normalized = normalized.replace(prefix, placeholder)
    return normalized


def normalize_snapshot_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_snapshot_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [normalize_snapshot_value(item) for item in value]
    return _normalize_scalar(value)


def _event_timestamp_unix(fixture: DaemonEventFixture) -> int:
    timestamp = fixture.payload.get("Info", {}).get("Timestamp", "")
    return int(datetime.fromisoformat(timestamp).timestamp()) if timestamp else 0


def _delete_target_id(fixture: DaemonEventFixture) -> str:
    info = fixture.payload.get("Info", {})
    target_id = info.get("MsgBotInfo", {}).get("EditTargetID") or info.get("MsgMetaInfo", {}).get("TargetID")
    if target_id:
        return str(target_id)

    protocol_message = fixture.payload.get("Message", {}).get("protocolMessage") or {}
    key = protocol_message.get("key") or {}
    return str(key.get("ID") or key.get("id") or "")


def snapshot_path_for_fixture(fixture: DaemonEventFixture) -> Path:
    relative = _safe_relative_path(fixture.relative_path)
    path = (SNAPSHOT_ROOT / relative.with_suffix(".kv.json")).resolve()
    assert path.is_relative_to(SNAPSHOT_ROOT.resolve()), f"snapshot path escapes snapshot root: {fixture.relative_path}"
    return path


def dispatch_daemon_fixture(fixture: DaemonEventFixture) -> None:
    from greenline.events.handlers import dispatch_event

    dispatch_event(fixture.stored_event(), {}, [], [], [], [], [])


def seed_prerequisite_kv(fixture: DaemonEventFixture) -> None:
    if fixture.event_type != "Message":
        return

    info = fixture.payload.get("Info", {})
    if info.get("Edit") != "7":
        return

    chat_id = str(info.get("Chat") or "")
    target_id = _delete_target_id(fixture)
    if not chat_id or not target_id:
        return

    timestamp_unix = max(_event_timestamp_unix(fixture) - 1, 0)
    seed_message = Message(
        id=target_id,
        chat_id=chat_id,
        type=MessageType.TEXT,
        is_outgoing=False,
        timestamp="11:59",
        timestamp_unix=timestamp_unix,
        read_receipt=ReadReceipt.NONE,
        text="Seed message before delete",
    )
    seed_chat = ChatListItem(
        id=chat_id,
        name=chat_id,
        photo="",
        last_message=seed_message.text,
        date=seed_message.timestamp,
        last_message_timestamp=seed_message.timestamp_unix,
        read_receipt=ReadReceipt.NONE,
        unread_count=1,
        is_group=chat_id.endswith("@g.us"),
        last_message_type=str(seed_message.type),
        name_updated_at=seed_message.timestamp_unix,
    )
    storage_key = message_storage_key(chat_id, timestamp_unix, target_id)
    with KV() as kv:
        kv.put(storage_key, asdict(seed_message))
        put_message_index(kv, chat_id, target_id, storage_key)
        kv.put(f"chat:{chat_id}", asdict(seed_chat))


def read_kv_snapshot() -> dict[str, Any]:
    with KV() as kv:
        kv.cursor.execute("SELECT key, value FROM kv ORDER BY key")
        rows = kv.cursor.fetchall()
        return {key: normalize_snapshot_value(kv._decode_value(value)) for key, value in rows}


def kv_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    added = {key: after[key] for key in sorted(after.keys() - before.keys())}
    changed = {
        key: {"before": before[key], "after": after[key]}
        for key in sorted(before.keys() & after.keys())
        if before[key] != after[key]
    }
    deleted = {key: before[key] for key in sorted(before.keys() - after.keys())}
    return {"added": added, "changed": changed, "deleted": deleted}


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def load_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _message_from_entry(key: str, value: Any) -> Message:
    assert isinstance(value, dict), f"{key} must store an object"
    message_fields = {field.name for field in fields(Message)}
    extra_fields = set(value) - message_fields - {"raw"}
    assert not extra_fields, f"{key} has unknown message fields: {sorted(extra_fields)}"
    data = {field: value[field] for field in message_fields if field in value}
    assert "type" in data, f"{key} missing message type"
    assert "read_receipt" in data, f"{key} missing read receipt"
    data["type"] = MessageType(data["type"])
    data["read_receipt"] = ReadReceipt(data["read_receipt"])
    message = Message(**data)
    raw = value.get("raw")
    assert raw is None or isinstance(raw, dict), f"{key}.raw must be a JSON object"
    return message


def _chat_from_entry(key: str, value: Any) -> ChatListItem:
    assert isinstance(value, dict), f"{key} must store an object"
    assert "read_receipt" in value, f"{key} missing read receipt"
    data = dict(value)
    data["read_receipt"] = ReadReceipt(data["read_receipt"])
    return ChatListItem(**data)


def validate_kv_snapshot(snapshot: dict[str, Any]) -> None:
    for key, value in snapshot.items():
        if key.startswith("message:"):
            _message_from_entry(key, value)
        elif key.startswith("chat:"):
            _chat_from_entry(key, value)
        elif key.startswith("message_index:"):
            assert isinstance(value, str), f"{key} must point to a message key"
            assert value in snapshot, f"{key} points to missing message entry {value!r}"
        elif key.startswith("unhandled_message:"):
            assert isinstance(value, dict), f"{key} must store an object"
            json.loads(value.get("payload", ""))
        elif key.startswith("unknown_event:"):
            assert isinstance(value, dict), f"{key} must store an object"
            json.loads(value.get("payload", ""))
        elif key == "unread_total":
            assert isinstance(value, int), "unread_total must be an integer"
        elif key.startswith("sticker_cache:"):
            assert isinstance(value, str), f"{key} must store a cache path"
        else:
            raise AssertionError(f"unexpected KV key {key}")
