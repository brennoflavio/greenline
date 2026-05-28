from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from greenline.reporting import (
    capture_stack_summary,
    current_error_trace,
    post_error_report,
)

LOGGER = logging.getLogger("greenline.contracts")


class BoundaryValidationError(ValueError):
    """Raised by strict boundary validators."""


def _format_validation_scope(boundary: str, contract: str | None, direction: str | None) -> str:
    parts = [boundary]
    if contract is not None:
        parts.append(f"contract={contract}")
    if direction is not None:
        parts.append(f"direction={direction}")
    return " ".join(parts)


def _normalize_validation_payload(value: Any, *, seen: set[int] | None = None) -> Any:
    if value is None or type(value) in (str, int, float, bool):
        return value

    if seen is None:
        seen = set()

    if isinstance(value, (dict, list, tuple, set, frozenset)) or (is_dataclass(value) and not isinstance(value, type)):
        identity = id(value)
        if identity in seen:
            return "<recursive>"
        seen = set(seen)
        seen.add(identity)

    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_validation_payload(asdict(value), seen=seen)
    if isinstance(value, Enum):
        return _normalize_validation_payload(value.value, seen=seen)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseException):
        return {"type": type(value).__name__, "message": str(value)}
    if isinstance(value, dict):
        return {str(key): _normalize_validation_payload(item, seen=seen) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_normalize_validation_payload(item, seen=seen) for item in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return repr(bytes(value))
    if isinstance(value, type):
        return value.__name__
    return repr(value)


def report_validation_failure(
    boundary: str,
    error: BaseException | str,
    *,
    payload: Any | None = None,
    contract: str | None = None,
    direction: str | None = None,
    dataclass_name: str | None = None,
) -> None:
    message = str(error)
    scope = _format_validation_scope(boundary, contract, direction)
    LOGGER.warning(
        "%s validation failed: %s",
        scope,
        message,
        extra={
            "payload": payload,
            "boundary": boundary,
            "contract": contract,
            "direction": direction,
            "dataclass": dataclass_name,
        },
    )
    trace = current_error_trace()
    stack = capture_stack_summary(skip=1)
    try:
        post_error_report(
            f"{scope} validation failed: {message}",
            failure=message,
            data=_normalize_validation_payload(payload),
            dataclass=dataclass_name,
            boundary=boundary,
            contract=contract,
            direction=direction,
            trace=trace,
            stack=stack,
        )
    except Exception:
        pass


def _json_like_error(value: Any, path: str) -> str | None:
    if is_dataclass(value) and not isinstance(value, type):
        return f"{path} is a dataclass, not JSON-like data"
    if isinstance(value, Enum):
        return f"{path} is an enum, not JSON-like data"
    if isinstance(value, Path):
        return f"{path} is a Path, not JSON-like data"
    if value is None or type(value) in (str, int, float, bool):
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            error = _json_like_error(item, f"{path}[{index}]")
            if error is not None:
                return error
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return f"{path} has non-string key {key!r}"
            error = _json_like_error(item, f"{path}.{key}")
            if error is not None:
                return error
        return None
    return f"{path} is not JSON-like data: {type(value).__name__}"


def validate_json_like(
    value: Any,
    *,
    boundary: str,
    path: str = "payload",
    raise_on_error: bool = False,
    contract: str | None = None,
    direction: str | None = None,
) -> bool:
    error = _json_like_error(value, path)
    if error is None:
        return True
    report_validation_failure(boundary, error, payload=value, contract=contract, direction=direction)
    if raise_on_error:
        raise BoundaryValidationError(error)
    return False


def assert_json_like(
    value: Any,
    *,
    boundary: str,
    path: str = "payload",
    contract: str | None = None,
    direction: str | None = None,
) -> None:
    validate_json_like(
        value,
        boundary=boundary,
        path=path,
        raise_on_error=True,
        contract=contract,
        direction=direction,
    )
