from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

APPROVED_PATHS = {
    Path("src/greenline/contracts/kv.py"),
}
APPROVED_PREFIXES = (Path("src/ut_components"),)


def _attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attribute_name(node.value)
        if parent is None:
            return node.attr
        return f"{parent}.{node.attr}"
    return None


class KVBoundaryVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.kv_constructor_aliases: set[str] = set()
        self.kv_module_aliases: set[str] = set()
        self.ut_components_aliases: set[str] = set()
        self.violations: list[str] = []

    def _add(self, node: ast.AST, message: str) -> None:
        self.violations.append(f"{self.path}:{node.lineno}: {message}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "ut_components.kv":
                self.kv_module_aliases.add(alias.asname or alias.name)
            elif alias.name == "ut_components":
                self.ut_components_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "ut_components":
            for alias in node.names:
                if alias.name == "kv":
                    self.kv_module_aliases.add(alias.asname or alias.name)
        if node.module == "ut_components.kv":
            for alias in node.names:
                if alias.name == "*":
                    self._add(node, "direct star import from ut_components.kv")
                elif alias.name == "KV":
                    self.kv_constructor_aliases.add(alias.asname or alias.name)
                    self._add(node, "direct KV import from ut_components.kv")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        attr_name = _attribute_name(node)
        if attr_name is not None:
            if any(attr_name == f"{alias}.KV" for alias in self.kv_module_aliases):
                self._add(node, "direct ut_components.kv.KV access")
            for alias in self.ut_components_aliases:
                if attr_name == f"{alias}.kv.KV":
                    self._add(node, "direct ut_components.kv.KV access")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in self.kv_constructor_aliases:
            self._add(node, "direct KV() construction")
        attr_name = _attribute_name(node.func)
        if attr_name is not None:
            if any(attr_name == f"{alias}.KV" for alias in self.kv_module_aliases):
                self._add(node, "direct ut_components.kv.KV() construction")
            for alias in self.ut_components_aliases:
                if attr_name == f"{alias}.kv.KV":
                    self._add(node, "direct ut_components.kv.KV() construction")
        self.generic_visit(node)


def _is_approved(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if relative in APPROVED_PATHS:
        return True
    return any(relative == prefix or prefix in relative.parents for prefix in APPROVED_PREFIXES)


def _python_paths() -> list[Path]:
    return list(SRC.rglob("*.py"))


def kv_boundary_errors_for_source(source: str, path: Path | None = None) -> list[str]:
    display_path = path or Path("src/example.py")
    visitor = KVBoundaryVisitor(display_path)
    visitor.visit(ast.parse(source))
    return visitor.violations


def kv_boundary_errors() -> list[str]:
    errors: list[str] = []
    for path in _python_paths():
        if _is_approved(path):
            continue
        relative = path.relative_to(ROOT)
        visitor = KVBoundaryVisitor(relative)
        visitor.visit(ast.parse(path.read_text()))
        errors.extend(visitor.violations)
    return errors


def main() -> int:
    errors = kv_boundary_errors()
    if errors:
        print("KV boundary check failed:")
        print("Greenline app code must use greenline.contracts.kv.GreenlineKV instead of ut_components.kv.KV directly.")
        print("\n".join(f"  - {error}" for error in errors))
        return 1
    print("KV boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
