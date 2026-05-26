from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import daemon_types


class FakePyOtherSide(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("pyotherside")
        self.sent: list[tuple[str, Any]] = []

    def send(self, event_id: str, payload: Any = None) -> None:
        self.sent.append((event_id, payload))


fake_pyotherside = FakePyOtherSide()
sys.modules["pyotherside"] = fake_pyotherside


class FakeDaemonRPC:
    list_event_batches: list[list[daemon_types.StoredEvent]] = []
    list_events_calls: list[dict[str, int]] = []
    delete_events_calls: list[int] = []
    ensure_jid_map: dict[str, str] = {}
    download_media_calls: list[dict[str, Any]] = []
    sync_avatar_calls: list[str] = []
    sync_avatar_paths: dict[str, str] = {}

    @classmethod
    def reset(cls) -> None:
        cls.list_event_batches = []
        cls.list_events_calls = []
        cls.delete_events_calls = []
        cls.ensure_jid_map = {}
        cls.download_media_calls = []
        cls.sync_avatar_calls = []
        cls.sync_avatar_paths = {}

    @classmethod
    def queue_events(cls, *batches: list[daemon_types.StoredEvent]) -> None:
        cls.list_event_batches.extend(batches)

    def list_events(self, *, after_id: int, limit: int) -> daemon_types.ListEventsReply:
        self.__class__.list_events_calls.append({"after_id": after_id, "limit": limit})
        if self.__class__.list_event_batches:
            return daemon_types.ListEventsReply(Events=self.__class__.list_event_batches.pop(0))
        return daemon_types.ListEventsReply()

    def delete_events(self, *, up_to_id: int) -> None:
        self.__class__.delete_events_calls.append(up_to_id)

    def ensure_jid(self, jid: str) -> str:
        if not jid:
            return ""
        mapped = self.__class__.ensure_jid_map.get(jid)
        if mapped is not None:
            return mapped
        if jid.endswith("@lid"):
            return jid[: -len("@lid")] + "@s.whatsapp.net"
        return jid

    def download_media(
        self,
        *,
        direct_path: str,
        media_key: str,
        file_enc_sha256: str,
        file_sha256: str,
        file_length: int,
        media_type: str,
        mimetype: str,
        message_id: str,
        chat_id: str,
        file_name: str = "",
    ) -> str:
        call = {
            "direct_path": direct_path,
            "media_key": media_key,
            "file_enc_sha256": file_enc_sha256,
            "file_sha256": file_sha256,
            "file_length": file_length,
            "media_type": media_type,
            "mimetype": mimetype,
            "message_id": message_id,
            "chat_id": chat_id,
            "file_name": file_name,
        }
        self.__class__.download_media_calls.append(call)
        cache_root = Path(os.environ["XDG_CACHE_HOME"]) / "greenline.tests" / "daemon-media"
        cache_root.mkdir(parents=True, exist_ok=True)
        suffix = ".webp" if media_type == "sticker" else ".bin"
        path = cache_root / f"{chat_id.replace('/', '_')}__{message_id}{suffix}"
        path.write_bytes(b"")
        return str(path)

    def sync_avatar(self, jid: str) -> str:
        self.__class__.sync_avatar_calls.append(jid)
        configured = self.__class__.sync_avatar_paths.get(jid)
        if configured is not None:
            return configured
        cache_root = Path(os.environ["XDG_CACHE_HOME"]) / "greenline.tests" / "avatars"
        cache_root.mkdir(parents=True, exist_ok=True)
        path = cache_root / f"{jid.replace('/', '_')}.jpg"
        path.write_bytes(b"")
        return str(path)


@pytest.fixture(autouse=True)
def isolated_greenline_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_home = tmp_path / "config"
    cache_home = tmp_path / "cache"
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))
    monkeypatch.setenv("APP_DIR", str(app_dir))
    monkeypatch.setenv("TZ", "UTC")
    if hasattr(time, "tzset"):
        time.tzset()

    import ut_components

    ut_components.setup("greenline.tests", None)

    import ut_components.config as ut_config

    monkeypatch.setattr(ut_components, "APP_NAME_", "greenline.tests")
    monkeypatch.setattr(ut_config, "APP_NAME_", "greenline.tests")

    fake_pyotherside.sent.clear()
    FakeDaemonRPC.reset()

    import greenline.events.chat_sync as chat_sync
    import greenline.events.handlers as handlers
    import greenline.store.identity as identity
    import greenline.store.mentions as mentions
    import history_sync
    import rpc

    identity.clear_chat_runtime_cache()
    monkeypatch.setattr(rpc, "DaemonRPC", FakeDaemonRPC)
    monkeypatch.setattr(chat_sync, "DaemonRPC", FakeDaemonRPC)
    monkeypatch.setattr(handlers, "DaemonRPC", FakeDaemonRPC)
    monkeypatch.setattr(identity, "DaemonRPC", FakeDaemonRPC)
    monkeypatch.setattr(mentions, "DaemonRPC", FakeDaemonRPC)
    monkeypatch.setattr(history_sync, "DaemonRPC", FakeDaemonRPC)

    yield

    identity.clear_chat_runtime_cache()


@pytest.fixture
def fake_daemon_rpc() -> type[FakeDaemonRPC]:
    return FakeDaemonRPC
