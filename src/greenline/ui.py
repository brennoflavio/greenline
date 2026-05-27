"""Shared helpers for UI/dataclass serialization."""

from dataclasses import asdict
from typing import Any, Mapping, TypeVar

from greenline.contracts.codecs import decode_dataclass
from ut_components.utils import enum_to_str as _enum_to_str

T = TypeVar("T")


def enum_to_str(obj: dict[str, Any]) -> dict[str, Any]:
    return _enum_to_str(obj)  # type: ignore[no-untyped-call, no-any-return]


def dataclass_to_ui_dict(value: Any) -> dict[str, Any]:
    return enum_to_str(asdict(value))


def filter_dataclass_payload(data_class: type[T], payload: Mapping[str, Any]) -> dict[str, Any]:
    fields = getattr(data_class, "__dataclass_fields__", {})
    return {key: value for key, value in payload.items() if key in fields}


def inflate_dataclass(data_class: type[T], payload: Mapping[str, Any]) -> T:
    return decode_dataclass(data_class, filter_dataclass_payload(data_class, payload), boundary="ui")
