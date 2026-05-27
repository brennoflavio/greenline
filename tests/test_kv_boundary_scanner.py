from __future__ import annotations

import importlib.util
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parent / "tools" / "check_kv_boundary.py"
spec = importlib.util.spec_from_file_location("check_kv_boundary", TOOL_PATH)
assert spec is not None and spec.loader is not None
check_kv_boundary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_kv_boundary)


def _errors(source: str) -> list[str]:
    return check_kv_boundary.kv_boundary_errors_for_source(source, Path("src/app.py"))


def test_scanner_allows_greenline_kv_wrapper_usage() -> None:
    assert (
        _errors(
            """
from greenline.contracts.kv import GreenlineKV

with GreenlineKV() as kv:
    kv.get_record("chat:1")
"""
        )
        == []
    )


def test_scanner_flags_direct_kv_import_and_construction() -> None:
    errors = _errors(
        """
from ut_components.kv import KV

with KV() as kv:
    pass
"""
    )

    assert any("direct KV import" in error for error in errors)
    assert any("direct KV() construction" in error for error in errors)


def test_scanner_flags_star_imports() -> None:
    errors = _errors("from ut_components.kv import *\n")

    assert any("direct star import" in error for error in errors)


def test_scanner_flags_module_attribute_access() -> None:
    errors = _errors(
        """
import ut_components.kv as raw_kv

raw_kv.KV()
"""
    )

    assert any("direct ut_components.kv.KV access" in error for error in errors)
    assert any("direct ut_components.kv.KV() construction" in error for error in errors)


def test_scanner_flags_from_ut_components_kv_alias() -> None:
    errors = _errors(
        """
from ut_components import kv

kv.KV()
"""
    )

    assert any("direct ut_components.kv.KV access" in error for error in errors)
    assert any("direct ut_components.kv.KV() construction" in error for error in errors)


def test_scanner_flags_ut_components_attribute_access() -> None:
    errors = _errors(
        """
import ut_components

ut_components.kv.KV()
"""
    )

    assert any("direct ut_components.kv.KV access" in error for error in errors)
    assert any("direct ut_components.kv.KV() construction" in error for error in errors)


def test_scanner_passes_on_migrated_tree() -> None:
    assert check_kv_boundary.kv_boundary_errors() == []
