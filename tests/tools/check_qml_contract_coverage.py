from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from greenline.contracts.qml import API_CONTRACTS, EVENT_CONTRACTS, request_arg_bounds

QML_MAIN_CALL_RE = re.compile(r"(?:python\.)?call\(\s*['\"]main\.([A-Za-z_][A-Za-z0-9_]*)['\"]")
QML_HANDLER_RE = re.compile(r"setHandler\(\s*['\"]([^'\"]+)['\"]")
PYOTHERSIDE_SEND_RE = re.compile(r"\bpyotherside\.send\s*\(")
APPROVED_PYOTHERSIDE_PATHS = {
    Path("src/greenline/qml_events.py"),
    Path("src/ut_components/event.py"),
}


class QmlMainCall(NamedTuple):
    path: Path
    line: int
    name: str
    arg_count: int


def _find_matching_bracket(text: str, start: int) -> int:
    depth = 0
    quote: str | None = None
    escape = False

    for index in range(start, len(text)):
        char = text[index]
        if quote is not None:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue

        if char in ('"', "'"):
            quote = char
            continue
        if char == "[":
            depth += 1
            continue
        if char == "]":
            depth -= 1
            if depth == 0:
                return index

    raise ValueError("Unterminated QML argument array")


def _count_qml_array_items(array_text: str) -> int:
    inner = array_text[1:-1].strip()
    if not inner:
        return 0

    items: list[str] = []
    start = 0
    square_depth = 0
    curly_depth = 0
    paren_depth = 0
    quote: str | None = None
    escape = False

    for index, char in enumerate(inner):
        if quote is not None:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue

        if char in ('"', "'"):
            quote = char
            continue
        if char == "[":
            square_depth += 1
            continue
        if char == "]":
            square_depth -= 1
            continue
        if char == "{":
            curly_depth += 1
            continue
        if char == "}":
            curly_depth -= 1
            continue
        if char == "(":
            paren_depth += 1
            continue
        if char == ")":
            paren_depth -= 1
            continue
        if char == "," and square_depth == 0 and curly_depth == 0 and paren_depth == 0:
            items.append(inner[start:index].strip())
            start = index + 1

    items.append(inner[start:].strip())
    return len([item for item in items if item])


def _scan_qml_main_calls() -> tuple[list[QmlMainCall], list[str]]:
    calls: list[QmlMainCall] = []
    parse_errors: list[str] = []

    for path in (ROOT / "qml").rglob("*.qml"):
        text = path.read_text()
        relative_path = path.relative_to(ROOT)
        for match in QML_MAIN_CALL_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            cursor = match.end()
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor >= len(text) or text[cursor] != ",":
                parse_errors.append(f"{relative_path}:{line}: main.{match.group(1)} is missing an argument array")
                continue
            cursor += 1
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor >= len(text) or text[cursor] != "[":
                parse_errors.append(
                    f"{relative_path}:{line}: main.{match.group(1)} must use an inline positional argument array"
                )
                continue

            array_start = cursor
            array_end = _find_matching_bracket(text, array_start)
            arg_count = _count_qml_array_items(text[array_start : array_end + 1])
            calls.append(QmlMainCall(relative_path, line, match.group(1), arg_count))

    return calls, parse_errors


def qml_main_calls() -> list[QmlMainCall]:
    calls, _ = _scan_qml_main_calls()
    return calls


def qml_used_main_calls() -> set[str]:
    return {call.name for call in qml_main_calls()}


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


def qml_api_wrapped_main_callables() -> tuple[dict[str, str], list[str]]:
    module = ast.parse((SRC / "main.py").read_text())
    wrapped: dict[str, str] = {}
    invalid: list[str] = []

    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target = node.targets[0].id
        value = node.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Call):
            continue
        decorator_call = value.func
        if not isinstance(decorator_call.func, ast.Name) or decorator_call.func.id != "qml_api":
            continue
        if (
            len(decorator_call.args) != 1
            or not isinstance(decorator_call.args[0], ast.Constant)
            or not isinstance(decorator_call.args[0].value, str)
            or len(value.args) != 1
            or not isinstance(value.args[0], ast.Name)
        ):
            invalid.append(target)
            continue
        contract = decorator_call.args[0].value
        wrapped[target] = contract
        if contract != target or value.args[0].id != target:
            invalid.append(f"{target} = qml_api({contract!r})({value.args[0].id})")

    return wrapped, invalid


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


def framework_validated_event_names() -> set[str]:
    event_names: set[str] = set()
    for path in (SRC / "greenline" / "events").rglob("*.py"):
        module = ast.parse(path.read_text())
        for node in ast.walk(module):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "validate_qml_event":
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


def qml_call_contract_errors() -> list[str]:
    errors: list[str] = []
    for call in qml_main_calls():
        contract = API_CONTRACTS.get(call.name)
        if contract is None:
            continue
        min_args, max_args = request_arg_bounds(contract.request_type)
        if min_args <= call.arg_count <= max_args:
            continue
        errors.append(
            f"{call.path}:{call.line}: main.{call.name} passes {call.arg_count} positional args, "
            f"but contract accepts {min_args}..{max_args}"
        )
    return errors


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
    wrapped, invalid_wrappers = qml_api_wrapped_main_callables()
    errors.extend(_format_missing("src/main.py exported callables missing qml_api wrappers:", exported - set(wrapped)))
    errors.extend(
        _format_missing("qml_api wrappers for functions not exported by src/main.py:", set(wrapped) - exported)
    )
    if invalid_wrappers:
        errors.append("Invalid src/main.py qml_api wrappers:")
        errors.extend(f"  - {wrapper}" for wrapper in sorted(invalid_wrappers))
    _qml_calls, qml_call_parse_errors = _scan_qml_main_calls()
    if qml_call_parse_errors:
        errors.append("QML main.* calls that do not use inline positional argument arrays:")
        errors.extend(f"  - {error}" for error in qml_call_parse_errors)
    qml_call_errors = qml_call_contract_errors()
    if qml_call_errors:
        errors.append("QML main.* calls with positional args outside request contract bounds:")
        errors.extend(f"  - {error}" for error in qml_call_errors)
    errors.extend(_format_missing("QML setHandler events missing event contracts:", handlers - event_contracts))
    errors.extend(_format_missing("Event contracts not used by QML setHandler:", event_contracts - handlers))
    bridge_events = bridge_event_names()
    errors.extend(
        _format_missing("QML bridge _send event names missing event contracts:", bridge_events - event_contracts)
    )
    framework_validated_events = framework_validated_event_names()
    errors.extend(
        _format_missing(
            "Non-bridge QML event contracts missing validate_qml_event calls:",
            event_contracts - bridge_events - framework_validated_events,
        )
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
