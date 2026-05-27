from __future__ import annotations

from typing import Any

from greenline.contracts.qml import *  # noqa: F401,F403
from greenline.contracts.qml import EVENT_CONTRACTS


def assert_event_payload(event_name: str, payload: Any) -> None:
    EVENT_CONTRACTS[event_name].validator(payload)
