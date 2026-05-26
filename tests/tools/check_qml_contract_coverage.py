from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from contracts.qml_registry import API_CONTRACTS, EVENT_CONTRACTS

QML_CALL_RE = re.compile(r"(?:python\.)?call\(\s*['\"]main\.([A-Za-z_][A-Za-z0-9_]*)['\"]")
QML_HANDLER_RE = re.compile(r"setHandler\(\s*['\"]([^'\"]+)['\"]")
PYOTHERSIDE_SEND_RE = re.compile(r"\bpyotherside\.send\s*\(")
APPROVED_PYOTHERSIDE_PATHS = {
    Path("src/greenline/qml_events.py"),
    Path("src/ut_components/event.py"),
}


def qml_used_main_calls() -> set[str]:
    calls: set[str] = set()
    for path in (ROOT / "qml").rglob("*.qml"):
        calls.update(QML_CALL_RE.findall(path.read_text()))
    return calls


def qml_handlers() -> set[str]:
    handlers: set[str] = set()
    for path in (ROOT / "qml").rglob("*.qml"):
        handlers.update(QML_HANDLER_RE.findall(path.read_text()))
    return handlers


def exported_main_callables() -> set[str]:
    module = ast.parse((SRC / "main.py").read_text())
    exported_names: set[str] = set()
    imported_callables: set[str] = set()
    module_defs: set[str] = set()

    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_defs.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_callables.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    exported_names = set(ast.literal_eval(node.value))

    return {
        name
        for name in exported_names
        if (name in imported_callables or name in module_defs) and name[:1].islower() and name != "setup"
    }


def bridge_event_names() -> set[str]:
    module = ast.parse((SRC / "greenline" / "qml_events.py").read_text())
    event_names: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "_send":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            continue
        event_names.add(node.args[0].value)
    return event_names


def _raw_pyotherside_ast_usages(path: Path) -> list[str]:
    module = ast.parse(path.read_text())
    violations: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pyotherside" or alias.name.startswith("pyotherside."):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: import {alias.name}")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module == "pyotherside" or node.module.startswith("pyotherside."))
        ):
            violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: from {node.module} import ...")
    return violations


def raw_pyotherside_usages() -> list[str]:
    violations: list[str] = []
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if relative in APPROVED_PYOTHERSIDE_PATHS:
            continue
        violations.extend(_raw_pyotherside_ast_usages(path))
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if PYOTHERSIDE_SEND_RE.search(line):
                violations.append(f"{relative}:{line_number}: {line.strip()}")
    return violations


def _format_missing(title: str, missing: set[str]) -> list[str]:
    if not missing:
        return []
    return [title, *[f"  - {item}" for item in sorted(missing)]]


def coverage_errors() -> list[str]:
    errors: list[str] = []
    qml_calls = qml_used_main_calls()
    handlers = qml_handlers()
    exported = exported_main_callables()
    api_contracts = set(API_CONTRACTS)
    event_contracts = set(EVENT_CONTRACTS)

    errors.extend(_format_missing("QML main.* calls missing API contracts:", qml_calls - api_contracts))
    errors.extend(_format_missing("src/main.py exported callables missing API contracts:", exported - api_contracts))
    errors.extend(_format_missing("API contracts for functions not exported by src/main.py:", api_contracts - exported))
    errors.extend(_format_missing("QML setHandler events missing event contracts:", handlers - event_contracts))
    errors.extend(_format_missing("Event contracts not used by QML setHandler:", event_contracts - handlers))
    bridge_events = bridge_event_names()
    errors.extend(
        _format_missing("QML bridge _send event names missing event contracts:", bridge_events - event_contracts)
    )

    raw_usages = raw_pyotherside_usages()
    if raw_usages:
        errors.append("Raw pyotherside usage outside the Greenline QML bridge/framework exemption:")
        errors.extend(f"  - {usage}" for usage in raw_usages)

    return errors


def main() -> int:
    errors = coverage_errors()
    if errors:
        print("QML contract coverage check failed:")
        print("\n".join(errors))
        return 1
    print("QML contract coverage check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
