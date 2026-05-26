from __future__ import annotations

import logging
from dataclasses import is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

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


def report_validation_failure(
    boundary: str,
    error: BaseException | str,
    *,
    payload: Any | None = None,
    contract: str | None = None,
    direction: str | None = None,
) -> None:
    message = str(error)
    LOGGER.warning(
        "%s validation failed: %s",
        _format_validation_scope(boundary, contract, direction),
        message,
        extra={"payload": payload, "boundary": boundary, "contract": contract, "direction": direction},
    )


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
