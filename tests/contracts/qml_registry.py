from __future__ import annotations

from typing import Any

from greenline.contracts.qml import API_CONTRACTS, EVENT_CONTRACTS


def validate_api_response(name: str, payload: Any) -> None:
    API_CONTRACTS[name].validator(payload)


def validate_event_payload(name: str, payload: Any) -> None:
    EVENT_CONTRACTS[name].validator(payload)
