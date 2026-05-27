from __future__ import annotations

import logging

import pytest

from greenline.contracts.qml import qml_api, validate_qml_event, validate_qml_response
from greenline.contracts.validation import BoundaryValidationError


def _assert_contract_log(
    caplog: pytest.LogCaptureFixture,
    *,
    boundary: str,
    contract: str,
    direction: str = "encode",
) -> None:
    assert any(
        record.boundary == boundary and record.contract == contract and record.direction == direction
        for record in caplog.records
    )


def test_validate_qml_event_logs_and_raises_on_invalid_payload(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with pytest.raises(BoundaryValidationError):
        validate_qml_event("sync-status", {"syncing": True})

    _assert_contract_log(caplog, boundary="qml_event", contract="sync-status")


def test_validate_qml_response_logs_and_raises_on_invalid_payload(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with pytest.raises(BoundaryValidationError):
        validate_qml_response("get_sync_status", {"syncing": True})

    _assert_contract_log(caplog, boundary="qml_api", contract="get_sync_status")


def test_missing_qml_contract_logs_and_raises(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with pytest.raises(BoundaryValidationError):
        validate_qml_event("unknown-event", {})
    with pytest.raises(BoundaryValidationError):
        validate_qml_response("unknown_api", {})

    _assert_contract_log(caplog, boundary="qml_event", contract="unknown-event")
    _assert_contract_log(caplog, boundary="qml_api", contract="unknown_api")


def test_qml_send_rejects_invalid_event_before_pyotherside(fake_pyotherside_module) -> None:
    from greenline import qml_events

    with pytest.raises(BoundaryValidationError):
        qml_events._send("sync-status", {"syncing": True})

    assert fake_pyotherside_module.sent == []


def test_qml_api_wrapper_rejects_invalid_response(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    @qml_api("get_sync_status")
    def invalid_get_sync_status() -> object:
        return {"syncing": True}

    with pytest.raises(BoundaryValidationError):
        invalid_get_sync_status()

    _assert_contract_log(caplog, boundary="qml_api", contract="get_sync_status")
