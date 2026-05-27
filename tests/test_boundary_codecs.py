from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import pytest

from greenline.contracts.codecs import decode_dataclass, encode_dataclass, to_json_like
from greenline.contracts.validation import (
    BoundaryValidationError,
    assert_json_like,
    validate_json_like,
)


class SampleKind(StrEnum):
    TEXT = "text"


@dataclass
class NestedPayload:
    kind: SampleKind = SampleKind.TEXT


@dataclass
class SamplePayload:
    chat_id: str
    tags: list[SampleKind] = field(default_factory=lambda: [SampleKind.TEXT])
    nested: NestedPayload = field(default_factory=NestedPayload)


@dataclass
class InvalidJsonPayload:
    path: Path


def test_encode_dataclass_returns_json_like_payload() -> None:
    payload = encode_dataclass(SamplePayload(chat_id="chat-1"), boundary="test.request")

    assert payload == {"chat_id": "chat-1", "tags": ["text"], "nested": {"kind": "text"}}


def test_invalid_encode_is_logged_before_reraising(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(TypeError):
        encode_dataclass({"chat_id": "chat-1"}, boundary="test.request")

    assert "test.request validation failed" in caplog.text


def test_non_json_like_encode_is_logged_before_reraising(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(BoundaryValidationError):
        encode_dataclass(InvalidJsonPayload(path=Path("avatar.jpg")), boundary="test.request")

    assert "test.request validation failed" in caplog.text


def test_decode_dataclass_casts_strings_to_enums() -> None:
    payload = decode_dataclass(
        SamplePayload,
        {"chat_id": "chat-1", "tags": ["text"], "nested": {"kind": "text"}},
        boundary="test.reply",
    )

    assert payload == SamplePayload(chat_id="chat-1")


def test_invalid_decode_is_logged_before_reraising(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(BoundaryValidationError):
        decode_dataclass(SamplePayload, {"tags": ["text"]}, boundary="test.reply")

    assert "test.reply validation failed" in caplog.text


def test_validation_failure_logs_boundary_contract_and_direction(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(BoundaryValidationError):
        decode_dataclass(
            SamplePayload,
            {"tags": ["text"]},
            boundary="daemon_rpc",
            contract="Service.SendMessage",
            direction="decode",
        )

    record = caplog.records[-1]
    assert "daemon_rpc contract=Service.SendMessage direction=decode validation failed" in caplog.text
    assert record.boundary == "daemon_rpc"
    assert record.contract == "Service.SendMessage"
    assert record.direction == "decode"


def test_to_json_like_converts_nested_enums_and_tuples() -> None:
    assert to_json_like({"kind": SampleKind.TEXT, "items": (SampleKind.TEXT,)}) == {
        "kind": "text",
        "items": ["text"],
    }


def test_json_like_validator_logs_by_default(caplog: pytest.LogCaptureFixture) -> None:
    assert not validate_json_like({"path": Path("avatar.jpg")}, boundary="test.payload")

    assert "test.payload validation failed" in caplog.text


def test_json_like_validator_logs_metadata(caplog: pytest.LogCaptureFixture) -> None:
    assert not validate_json_like(
        {"path": Path("avatar.jpg")},
        boundary="daemon_rpc",
        contract="Service.SyncAvatar",
        direction="encode",
    )

    assert "daemon_rpc contract=Service.SyncAvatar direction=encode validation failed" in caplog.text


def test_json_like_assertion_raises_after_logging(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(BoundaryValidationError):
        assert_json_like(SamplePayload(chat_id="chat-1"), boundary="test.payload")

    assert "test.payload validation failed" in caplog.text
