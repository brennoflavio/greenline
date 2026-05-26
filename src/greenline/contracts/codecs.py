from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, TypeVar, cast

from dacite import Config, from_dict

from greenline.contracts.validation import report_validation_failure, validate_json_like

T = TypeVar("T")


def to_json_like(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return to_json_like(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): to_json_like(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_json_like(item) for item in value]
    if isinstance(value, tuple):
        return [to_json_like(item) for item in value]
    return value


def encode_dataclass(
    value: Any,
    *,
    boundary: str,
    raise_on_error: bool = False,
    contract: str | None = None,
    direction: str | None = None,
) -> dict[str, Any]:
    if not (is_dataclass(value) and not isinstance(value, type)):
        error = f"expected dataclass instance, got {type(value).__name__}"
        report_validation_failure(boundary, error, payload=value, contract=contract, direction=direction)
        if raise_on_error:
            raise TypeError(error)
        return {}
    payload = cast(dict[str, Any], to_json_like(asdict(value)))
    validate_json_like(
        payload,
        boundary=boundary,
        raise_on_error=raise_on_error,
        contract=contract,
        direction=direction,
    )
    return payload


def decode_dataclass(
    data_class: type[T],
    data: Any,
    *,
    boundary: str,
    contract: str | None = None,
    direction: str | None = None,
) -> T:
    try:
        return from_dict(data_class=data_class, data=data, config=Config(cast=[Enum]))
    except Exception as exc:
        report_validation_failure(boundary, exc, payload=data, contract=contract, direction=direction)
        raise
