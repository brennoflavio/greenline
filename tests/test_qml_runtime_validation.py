from __future__ import annotations

import logging

import pytest

from greenline.contracts.qml import (
    PairPhoneRequest,
    ReplyContextRequest,
    SendTextMessageRequest,
    decode_qml_request,
    qml_api,
    validate_qml_event,
    validate_qml_response,
)
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


def test_decode_qml_request_returns_typed_dataclass() -> None:
    request = decode_qml_request(
        "send_text_message",
        (
            "chat@s.whatsapp.net",
            "Hello",
            "pending-1",
            {"id": "reply-1", "sender": "Alice", "text": "Quoted", "participant": "alice@s.whatsapp.net"},
            [{"jid": "alice@s.whatsapp.net", "label": "Alice", "start": 0, "length": 5}],
        ),
        {},
    )

    assert isinstance(request, SendTextMessageRequest)
    assert request.chat_id == "chat@s.whatsapp.net"
    assert request.reply_context == ReplyContextRequest(
        id="reply-1",
        sender="Alice",
        text="Quoted",
        participant="alice@s.whatsapp.net",
    )
    assert len(request.mention_spans) == 1
    assert request.mention_spans[0].jid == "alice@s.whatsapp.net"


def test_decode_qml_request_normalizes_integer_valued_floats() -> None:
    request = decode_qml_request(
        "send_text_message",
        (
            "chat@s.whatsapp.net",
            "Hello",
            "pending-1",
            None,
            [{"jid": "alice@s.whatsapp.net", "label": "Alice", "start": 0.0, "length": 5.0}],
        ),
        {},
    )

    assert isinstance(request, SendTextMessageRequest)
    assert request.mention_spans[0].start == 0
    assert request.mention_spans[0].length == 5


def test_decode_qml_request_logs_invalid_primitive_type(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with pytest.raises(BoundaryValidationError):
        decode_qml_request("send_presence", ("true",), {})

    _assert_contract_log(caplog, boundary="qml_api", contract="send_presence", direction="decode")


def test_decode_qml_request_logs_missing_required_args(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with pytest.raises(BoundaryValidationError):
        decode_qml_request("get_chat_info", (), {})

    _assert_contract_log(caplog, boundary="qml_api", contract="get_chat_info", direction="decode")


def test_decode_qml_request_logs_extra_args(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with pytest.raises(BoundaryValidationError):
        decode_qml_request("toggle_mute", ("chat@s.whatsapp.net", "extra"), {})

    _assert_contract_log(caplog, boundary="qml_api", contract="toggle_mute", direction="decode")


def test_decode_qml_request_logs_malformed_reply_context(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with pytest.raises(BoundaryValidationError):
        decode_qml_request(
            "send_text_message",
            ("chat@s.whatsapp.net", "Hello", "pending-1", {"id": "reply-1", "sender": "Alice", "text": "Quoted"}),
            {},
        )

    _assert_contract_log(caplog, boundary="qml_api", contract="send_text_message", direction="decode")


def test_decode_qml_request_logs_malformed_mention_spans(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with pytest.raises(BoundaryValidationError):
        decode_qml_request(
            "send_text_message",
            (
                "chat@s.whatsapp.net",
                "Hello",
                "pending-1",
                None,
                [{"jid": "alice@s.whatsapp.net", "label": "Alice", "start": "0", "length": 5}],
            ),
            {},
        )

    _assert_contract_log(caplog, boundary="qml_api", contract="send_text_message", direction="decode")


def test_decode_qml_request_logs_unknown_contract(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with pytest.raises(BoundaryValidationError):
        decode_qml_request("unknown_api", (), {})

    _assert_contract_log(caplog, boundary="qml_api", contract="unknown_api", direction="decode")


def test_qml_api_wrapper_passes_decoded_dataclass_before_output_validation() -> None:
    seen: list[PairPhoneRequest] = []

    @qml_api("pair_phone")
    def pair_phone(request: PairPhoneRequest) -> object:
        seen.append(request)
        return {"success": True, "code": "12345678", "message": ""}

    result = pair_phone("+15551234567")

    assert result == {"success": True, "code": "12345678", "message": ""}
    assert seen == [PairPhoneRequest(phone_number="+15551234567")]


def test_qml_api_wrapper_rejects_invalid_input_before_calling_business_logic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")
    called = False

    @qml_api("send_presence")
    def send_presence(_request) -> object:
        nonlocal called
        called = True
        return None

    with pytest.raises(BoundaryValidationError):
        send_presence("true")

    assert called is False
    _assert_contract_log(caplog, boundary="qml_api", contract="send_presence", direction="decode")
