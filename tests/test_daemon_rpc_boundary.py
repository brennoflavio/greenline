from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_scanner():
    scanner_path = Path(__file__).parent / "tools" / "check_daemon_rpc_boundary.py"
    spec = importlib.util.spec_from_file_location("check_daemon_rpc_boundary", scanner_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runtime_code_uses_daemon_boundary_instead_of_daemon_rpc() -> None:
    scanner = _load_scanner()

    assert scanner.daemon_rpc_boundary_errors() == []


def _scanner_violations(source: str) -> list[str]:
    scanner = _load_scanner()
    visitor = scanner.DaemonRPCVisitor(scanner.ROOT / "src" / "example.py")
    visitor.visit(scanner.ast.parse(source))
    return visitor.violations


def test_daemon_rpc_boundary_scanner_flags_direct_import_and_construction() -> None:
    violations = _scanner_violations("from rpc import DaemonRPC\nDaemonRPC()\n")

    assert any("direct DaemonRPC import" in violation for violation in violations)
    assert any("direct DaemonRPC() construction" in violation for violation in violations)


def test_daemon_rpc_boundary_scanner_flags_star_import() -> None:
    violations = _scanner_violations("from rpc import *\n")

    assert any("direct star import from rpc" in violation for violation in violations)


def test_daemon_rpc_boundary_scanner_flags_rpc_attribute_construction() -> None:
    violations = _scanner_violations("import rpc as transport\ntransport.DaemonRPC()\n")

    assert any("direct rpc.DaemonRPC transport access" in violation for violation in violations)
    assert any("direct rpc.DaemonRPC() construction" in violation for violation in violations)
