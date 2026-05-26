from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class FakePyOtherSide(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("pyotherside")
        self.sent: list[tuple[str, Any]] = []

    def send(self, event_id: str, payload: Any = None) -> None:
        self.sent.append((event_id, payload))


fake_pyotherside = FakePyOtherSide()
sys.modules["pyotherside"] = fake_pyotherside


class FakeDaemonRPC:
    def ensure_jid(self, jid: str) -> str:
        if not jid:
            return ""
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
        cache_root = Path(os.environ["XDG_CACHE_HOME"]) / "greenline.tests" / "daemon-media"
        cache_root.mkdir(parents=True, exist_ok=True)
        suffix = ".webp" if media_type == "sticker" else ".bin"
        path = cache_root / f"{chat_id.replace('/', '_')}__{message_id}{suffix}"
        path.write_bytes(b"")
        return str(path)

    def sync_avatar(self, jid: str) -> str:
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

    import ut_components

    ut_components.setup("greenline.tests", None)

    import ut_components.config as ut_config

    monkeypatch.setattr(ut_components, "APP_NAME_", "greenline.tests")
    monkeypatch.setattr(ut_config, "APP_NAME_", "greenline.tests")

    fake_pyotherside.sent.clear()

    import greenline.events.handlers as handlers
    import greenline.store.identity as identity
    import greenline.store.mentions as mentions
    import history_sync
    import rpc

    identity.clear_chat_runtime_cache()
    monkeypatch.setattr(rpc, "DaemonRPC", FakeDaemonRPC)
    monkeypatch.setattr(handlers, "DaemonRPC", FakeDaemonRPC)
    monkeypatch.setattr(identity, "DaemonRPC", FakeDaemonRPC)
    monkeypatch.setattr(mentions, "DaemonRPC", FakeDaemonRPC)
    monkeypatch.setattr(history_sync, "DaemonRPC", FakeDaemonRPC)

    yield

    identity.clear_chat_runtime_cache()
