from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_scanner():
    scanner_path = Path(__file__).parent / "tools" / "check_qml_contract_coverage.py"
    spec = importlib.util.spec_from_file_location("check_qml_contract_coverage", scanner_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_qml_contract_registry_covers_calls_events_exports_and_bridge_usage() -> None:
    scanner = _load_scanner()

    assert scanner.coverage_errors() == []
