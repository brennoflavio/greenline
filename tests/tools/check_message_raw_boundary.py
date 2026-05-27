from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

APPROVED_PATHS = {
    Path("src/greenline/contracts/kv.py"),
    Path("src/greenline/store/records.py"),
}


def _is_raw_key(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "raw"


class MessageRawBoundaryVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[str] = []

    def _add(self, node: ast.AST, message: str) -> None:
        self.violations.append(f"{self.path}:{node.lineno}: {message}")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "raw" and isinstance(node.ctx, ast.Load):
            self._add(node, "persisted message raw attribute access")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.ctx, ast.Load) and _is_raw_key(node.slice):
            self._add(node, "raw payload item access")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args and _is_raw_key(node.args[0]):
            self._add(node, "raw payload get access")
        self.generic_visit(node)


def _is_approved(path: Path) -> bool:
    relative = path.relative_to(ROOT) if path.is_absolute() else path
    return relative in APPROVED_PATHS


def _python_paths() -> list[Path]:
    return list(SRC.rglob("*.py"))


def message_raw_boundary_errors_for_source(source: str, path: Path | None = None) -> list[str]:
    display_path = path or Path("src/example.py")
    visitor = MessageRawBoundaryVisitor(display_path)
    visitor.visit(ast.parse(source))
    return visitor.violations


def message_raw_boundary_errors() -> list[str]:
    errors: list[str] = []
    for path in _python_paths():
        if _is_approved(path):
            continue
        relative = path.relative_to(ROOT)
        visitor = MessageRawBoundaryVisitor(relative)
        visitor.visit(ast.parse(path.read_text()))
        errors.extend(visitor.violations)
    return errors


def main() -> int:
    errors = message_raw_boundary_errors()
    if errors:
        print("Message raw boundary check failed:")
        print("App code must not read StoredMessageRecord.raw; raw is only for storage/debugging.")
        print("Use typed message fields or storage/codec helpers instead of persisted raw payloads.")
        print("\n".join(f"  - {error}" for error in errors))
        return 1
    print("Message raw boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
