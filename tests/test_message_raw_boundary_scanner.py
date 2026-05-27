from __future__ import annotations

import importlib.util
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parent / "tools" / "check_message_raw_boundary.py"
spec = importlib.util.spec_from_file_location("check_message_raw_boundary", TOOL_PATH)
assert spec is not None and spec.loader is not None
check_message_raw_boundary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_message_raw_boundary)


def _errors(source: str) -> list[str]:
    return check_message_raw_boundary.message_raw_boundary_errors_for_source(source, Path("src/app.py"))


def test_scanner_allows_storing_local_raw_payload() -> None:
    assert (
        _errors(
            """
from greenline.store.records import stored_message_record

record = stored_message_record(message, raw)
payload["raw"] = raw
"""
        )
        == []
    )


def test_scanner_flags_stored_record_raw_attribute_reads() -> None:
    errors = _errors(
        """
raw = entry.raw
stored_message_record(message, entry.raw)
"""
    )

    assert any("persisted message raw attribute access" in error for error in errors)


def test_scanner_flags_raw_payload_reads() -> None:
    errors = _errors(
        """
raw_value = payload["raw"]
raw_value = payload.get("raw")
"""
    )

    assert any("raw payload item access" in error for error in errors)
    assert any("raw payload get access" in error for error in errors)


def test_scanner_passes_on_migrated_tree() -> None:
    assert check_message_raw_boundary.message_raw_boundary_errors() == []
