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
OUTPUT_SNAPSHOT_ROOT = Path(__file__).parent / "fixtures" / "daemon_event_output_snapshots"

EVENT_DATACLASSES: dict[str, type[Any] | None] = {
    "Blocklist": whatsmeow_types.BlocklistEvent,
    "BusinessName": whatsmeow_types.BusinessNameEvent,
    "CallReject": whatsmeow_types.CallRejectEvent,
    "ChatPresence": whatsmeow_types.ChatPresenceEvent,
    "Contact": whatsmeow_types.ContactEvent,
    "GroupInfo": whatsmeow_types.GroupInfoEvent,
    "HistorySync": whatsmeow_types.HistorySyncEvent,
    "IdentityChange": whatsmeow_types.IdentityChangeEvent,
    "JoinedGroup": whatsmeow_types.JoinedGroupEvent,
    "Message": whatsmeow_types.MessageEvent,
    "Mute": None,
    "Picture": whatsmeow_types.PictureEvent,
    "Presence": whatsmeow_types.PresenceEvent,
    "PushName": whatsmeow_types.PushNameEvent,
    "Receipt": whatsmeow_types.ReceiptEvent,
    "UndecryptableMessage": whatsmeow_types.UndecryptableMessageEvent,
    "UserAbout": whatsmeow_types.UserAboutEvent,
}


@dataclass(frozen=True)
class DispatchResult:
    chat_updates: dict[str, dict[str, Any]]
    message_upserts: list[dict[str, Any]]
    message_updates: list[dict[str, Any]]
    photo_updates: list[dict[str, str]]
    presence_updates: list[dict[str, Any]]
    chat_presence_updates: list[dict[str, Any]]

    def as_snapshot(self) -> dict[str, Any]:
        return normalize_snapshot_value(asdict(self))


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
    def data_class(self) -> type[Any] | None:
        return EVENT_DATACLASSES[self.event_type]

    def parse_payload(self) -> Any:
        data_class = self.data_class
        if data_class is None:
            return self.payload
        return from_dict(data_class=data_class, data=self.payload)

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


def _parse_timestamp_unix(timestamp: str) -> int:
    return int(datetime.fromisoformat(timestamp).timestamp()) if timestamp else 0


def _event_timestamp_unix(fixture: DaemonEventFixture) -> int:
    timestamp = fixture.payload.get("Info", {}).get("Timestamp", "")
    return _parse_timestamp_unix(timestamp)


def seed_chat(
    chat_id: str,
    *,
    name: str | None = None,
    photo: str = "",
    muted: bool = False,
    read_receipt: ReadReceipt = ReadReceipt.NONE,
    unread_count: int = 0,
    timestamp_unix: int = 1,
    last_message: str = "Seed message",
) -> ChatListItem:
    chat = ChatListItem(
        id=chat_id,
        name=name or chat_id,
        photo=photo,
        last_message=last_message,
        date="11:59",
        last_message_timestamp=timestamp_unix,
        read_receipt=read_receipt,
        unread_count=unread_count,
        is_group=chat_id.endswith("@g.us"),
        last_message_type=str(MessageType.TEXT),
        muted=muted,
        name_updated_at=timestamp_unix,
    )
    with KV() as kv:
        kv.put(f"chat:{chat_id}", asdict(chat))
    return chat


def seed_message(
    chat_id: str,
    message_id: str,
    *,
    text: str = "Seed message",
    read_receipt: ReadReceipt = ReadReceipt.SENT,
    timestamp_unix: int = 1,
    is_outgoing: bool = True,
) -> Message:
    message = Message(
        id=message_id,
        chat_id=chat_id,
        type=MessageType.TEXT,
        is_outgoing=is_outgoing,
        timestamp="11:59",
        timestamp_unix=timestamp_unix,
        read_receipt=read_receipt,
        text=text,
    )
    storage_key = message_storage_key(chat_id, timestamp_unix, message_id)
    with KV() as kv:
        kv.put(storage_key, asdict(message))
        put_message_index(kv, chat_id, message_id, storage_key)
    return message


def seed_chat_with_message(
    chat_id: str,
    message_id: str,
    *,
    chat_read_receipt: ReadReceipt = ReadReceipt.NONE,
    message_read_receipt: ReadReceipt = ReadReceipt.SENT,
    unread_count: int = 0,
    timestamp_unix: int = 1,
    text: str = "Seed message",
    is_outgoing: bool = True,
) -> tuple[ChatListItem, Message]:
    chat = seed_chat(
        chat_id,
        read_receipt=chat_read_receipt,
        unread_count=unread_count,
        timestamp_unix=timestamp_unix,
        last_message=text,
    )
    message = seed_message(
        chat_id,
        message_id,
        text=text,
        read_receipt=message_read_receipt,
        timestamp_unix=timestamp_unix,
        is_outgoing=is_outgoing,
    )
    return chat, message


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


def output_snapshot_path_for_fixture(fixture: DaemonEventFixture) -> Path:
    relative = _safe_relative_path(fixture.relative_path)
    path = (OUTPUT_SNAPSHOT_ROOT / relative.with_suffix(".output.json")).resolve()
    assert path.is_relative_to(
        OUTPUT_SNAPSHOT_ROOT.resolve()
    ), f"output snapshot path escapes snapshot root: {fixture.relative_path}"
    return path


def dispatch_daemon_fixture_with_buckets(fixture: DaemonEventFixture) -> DispatchResult:
    from greenline.events.handlers import dispatch_event

    chat_updates: dict[str, dict[str, Any]] = {}
    message_upserts: list[dict[str, Any]] = []
    message_updates: list[dict[str, Any]] = []
    photo_updates: list[dict[str, str]] = []
    presence_updates: list[dict[str, Any]] = []
    chat_presence_updates: list[dict[str, Any]] = []

    dispatch_event(
        fixture.stored_event(),
        chat_updates,
        message_upserts,
        message_updates,
        photo_updates,
        presence_updates,
        chat_presence_updates,
    )
    return DispatchResult(
        chat_updates=normalize_snapshot_value(chat_updates),
        message_upserts=normalize_snapshot_value(message_upserts),
        message_updates=normalize_snapshot_value(message_updates),
        photo_updates=normalize_snapshot_value(photo_updates),
        presence_updates=normalize_snapshot_value(presence_updates),
        chat_presence_updates=normalize_snapshot_value(chat_presence_updates),
    )


def dispatch_daemon_fixture(fixture: DaemonEventFixture) -> None:
    dispatch_daemon_fixture_with_buckets(fixture)


def _seed_delete_prerequisites(fixture: DaemonEventFixture) -> None:
    info = fixture.payload.get("Info", {})
    if info.get("Edit") != "7":
        return

    chat_id = str(info.get("Chat") or "")
    target_id = _delete_target_id(fixture)
    if not chat_id or not target_id:
        return

    timestamp_unix = max(_event_timestamp_unix(fixture) - 1, 0)
    seed_chat_with_message(
        chat_id,
        target_id,
        message_read_receipt=ReadReceipt.NONE,
        unread_count=1,
        timestamp_unix=timestamp_unix,
        text="Seed message before delete",
        is_outgoing=False,
    )


def _seed_receipt_prerequisites(fixture: DaemonEventFixture) -> None:
    chat_id = str(fixture.payload.get("Chat") or "")
    message_ids = fixture.payload.get("MessageIDs") or []
    if not chat_id or not message_ids:
        return

    timestamp_unix = max(_parse_timestamp_unix(str(fixture.payload.get("Timestamp") or "")) - 1, 1)
    seed_chat(
        chat_id,
        read_receipt=ReadReceipt.DELIVERED,
        unread_count=2,
        timestamp_unix=timestamp_unix,
    )
    with KV() as kv:
        kv.put("unread_total", 2)
    for offset, message_id in enumerate(message_ids):
        seed_message(
            chat_id,
            str(message_id),
            read_receipt=ReadReceipt.SENT,
            timestamp_unix=timestamp_unix + offset,
        )


def _seed_chat_update_prerequisites(fixture: DaemonEventFixture) -> None:
    if fixture.event_type in {"Mute", "Picture", "PushName", "BusinessName"}:
        chat_id = str(fixture.payload.get("JID") or "")
        if chat_id:
            seed_chat(chat_id, name="Old Fixture Name", timestamp_unix=1)


def seed_prerequisite_kv(fixture: DaemonEventFixture) -> None:
    if fixture.event_type == "Message":
        _seed_delete_prerequisites(fixture)
    elif fixture.event_type == "Receipt":
        _seed_receipt_prerequisites(fixture)
    else:
        _seed_chat_update_prerequisites(fixture)


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


def write_output_snapshot(fixture: DaemonEventFixture, result: DispatchResult) -> None:
    write_snapshot(output_snapshot_path_for_fixture(fixture), result.as_snapshot())


def load_output_snapshot(fixture: DaemonEventFixture) -> dict[str, Any]:
    return load_snapshot(output_snapshot_path_for_fixture(fixture))


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
