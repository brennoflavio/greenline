from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
for path in (str(SRC), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from conftest import FakeDaemonRPC, fake_pyotherside
from daemon_event_helpers import (
    dispatch_daemon_fixture,
    kv_diff,
    load_fixtures,
    read_kv_snapshot,
    seed_prerequisite_kv,
    snapshot_path_for_fixture,
    validate_kv_snapshot,
    write_snapshot,
)


def configure_runtime(root: Path) -> None:
    config_home = root / "config"
    cache_home = root / "cache"
    app_dir = root / "app"
    app_dir.mkdir(parents=True, exist_ok=True)

    os.environ["XDG_CONFIG_HOME"] = str(config_home)
    os.environ["XDG_CACHE_HOME"] = str(cache_home)
    os.environ["APP_DIR"] = str(app_dir)

    import ut_components
    import ut_components.config as ut_config

    ut_components.setup("greenline.tests", None)
    ut_components.APP_NAME_ = "greenline.tests"
    ut_config.APP_NAME_ = "greenline.tests"

    fake_pyotherside.sent.clear()

    import greenline.events.handlers as handlers
    import greenline.store.identity as identity
    import greenline.store.mentions as mentions
    import history_sync
    import rpc

    identity.clear_chat_runtime_cache()
    rpc.DaemonRPC = FakeDaemonRPC
    handlers.DaemonRPC = FakeDaemonRPC
    identity.DaemonRPC = FakeDaemonRPC
    mentions.DaemonRPC = FakeDaemonRPC
    history_sync.DaemonRPC = FakeDaemonRPC


def update_snapshots() -> None:
    for fixture in load_fixtures():
        with tempfile.TemporaryDirectory() as directory:
            configure_runtime(Path(directory))
            seed_prerequisite_kv(fixture)
            before = read_kv_snapshot()
            dispatch_daemon_fixture(fixture)
            after = read_kv_snapshot()
            validate_kv_snapshot(after)
            write_snapshot(snapshot_path_for_fixture(fixture), kv_diff(before, after))
            print(snapshot_path_for_fixture(fixture).relative_to(ROOT))


if __name__ == "__main__":
    update_snapshots()
