from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TESTS = ROOT / "tests"

APPROVED_PATHS = {
    Path("src/rpc.py"),
    Path("src/greenline/contracts/daemon.py"),
}


class DaemonRPCVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.rpc_module_aliases: set[str] = set()
        self.daemon_rpc_aliases: set[str] = set()
        self.violations: list[str] = []

    def _add(self, node: ast.AST, message: str) -> None:
        self.violations.append(f"{self.path.relative_to(ROOT)}:{node.lineno}: {message}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "rpc":
                self.rpc_module_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "rpc":
            for alias in node.names:
                if alias.name == "*":
                    self._add(node, "direct star import from rpc")
                if alias.name == "DaemonRPC":
                    self.daemon_rpc_aliases.add(alias.asname or alias.name)
                    self._add(node, "direct DaemonRPC import from rpc")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "DaemonRPC" and isinstance(node.value, ast.Name) and node.value.id in self.rpc_module_aliases:
            self._add(node, "direct rpc.DaemonRPC transport access")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in self.daemon_rpc_aliases:
            self._add(node, "direct DaemonRPC() construction")
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "DaemonRPC"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.rpc_module_aliases
        ):
            self._add(node, "direct rpc.DaemonRPC() construction")
        self.generic_visit(node)


def _python_paths() -> list[Path]:
    return [*SRC.rglob("*.py"), *TESTS.rglob("*.py")]


def daemon_rpc_boundary_errors() -> list[str]:
    errors: list[str] = []
    for path in _python_paths():
        relative = path.relative_to(ROOT)
        if relative in APPROVED_PATHS:
            continue
        visitor = DaemonRPCVisitor(path)
        visitor.visit(ast.parse(path.read_text()))
        errors.extend(visitor.violations)
    return errors


def main() -> int:
    errors = daemon_rpc_boundary_errors()
    if errors:
        print("Daemon RPC boundary check failed:")
        print("App code must use greenline.contracts.daemon.daemon_client() instead of DaemonRPC directly.")
        print("\n".join(f"  - {error}" for error in errors))
        return 1
    print("Daemon RPC boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
