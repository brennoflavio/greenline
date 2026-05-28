from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import pytest

import greenline.reporting as reporting
from greenline.contracts.codecs import decode_dataclass, encode_dataclass, to_json_like
from greenline.contracts.validation import (
    BoundaryValidationError,
    assert_json_like,
    report_validation_failure,
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


def test_invalid_decode_posts_structured_validation_report(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[dict[str, object]] = []
    monkeypatch.setenv("GREENLINE_ENABLE_REPORTING_IN_TESTS", "1")
    reporting.set_error_reporting(True)
    monkeypatch.setattr(reporting, "CRASH_REPORT_URL", "https://example.test/report")

    def fake_post(*, url: str, json: dict[str, object]):
        posts.append({"url": url, "json": json})
        return object()

    monkeypatch.setattr(reporting.http, "post", fake_post)

    with pytest.raises(BoundaryValidationError, match="chat_id"):
        decode_dataclass(
            SamplePayload,
            {"tags": ["text"]},
            boundary="daemon_rpc",
            contract="Service.SendMessage",
            direction="decode",
        )

    assert len(posts) == 1
    assert posts[0]["url"] == "https://example.test/report"
    payload = posts[0]["json"]
    assert isinstance(payload, dict)
    assert payload["failure"] == 'missing value for field "chat_id"'
    assert payload["data"] == {"tags": ["text"]}
    assert payload["dataclass"] == "SamplePayload"
    assert payload["boundary"] == "daemon_rpc"
    assert payload["contract"] == "Service.SendMessage"
    assert payload["direction"] == "decode"
    assert str(payload["report"]).startswith(
        "daemon_rpc contract=Service.SendMessage direction=decode validation failed:"
    )


def test_validation_failure_normalizes_non_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[dict[str, object]] = []
    monkeypatch.setenv("GREENLINE_ENABLE_REPORTING_IN_TESTS", "1")
    reporting.set_error_reporting(True)
    monkeypatch.setattr(reporting, "CRASH_REPORT_URL", "https://example.test/report")

    def fake_post(*, url: str, json: dict[str, object]):
        posts.append(json)
        return object()

    monkeypatch.setattr(reporting.http, "post", fake_post)

    report_validation_failure(
        "daemon_rpc",
        BoundaryValidationError("bad payload"),
        payload={
            "sample": SamplePayload(chat_id="chat-1"),
            "path": Path("avatar.jpg"),
            "items": (SampleKind.TEXT,),
            "error": RuntimeError("boom"),
        },
        contract="Service.SendMessage",
        direction="decode",
        dataclass_name="SamplePayload",
    )

    assert posts == [
        {
            "report": "daemon_rpc contract=Service.SendMessage direction=decode validation failed: bad payload",
            "failure": "bad payload",
            "data": {
                "sample": {"chat_id": "chat-1", "tags": ["text"], "nested": {"kind": "text"}},
                "path": "avatar.jpg",
                "items": ["text"],
                "error": {"type": "RuntimeError", "message": "boom"},
            },
            "dataclass": "SamplePayload",
            "boundary": "daemon_rpc",
            "contract": "Service.SendMessage",
            "direction": "decode",
        }
    ]


def test_validation_failure_does_not_post_when_reporting_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[dict[str, object]] = []
    reporting.set_error_reporting(False)
    monkeypatch.setattr(reporting, "CRASH_REPORT_URL", "https://example.test/report")

    def fake_post(*, url: str, json: dict[str, object]):
        posts.append(json)
        return object()

    monkeypatch.setattr(reporting.http, "post", fake_post)

    report_validation_failure("daemon_rpc", "bad payload", payload={"chat_id": "chat-1"})

    assert posts == []


def test_validation_failure_without_url_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[dict[str, object]] = []
    reporting.set_error_reporting(True)
    monkeypatch.setattr(reporting, "CRASH_REPORT_URL", "")

    def fake_post(*, url: str, json: dict[str, object]):
        posts.append(json)
        return object()

    monkeypatch.setattr(reporting.http, "post", fake_post)

    report_validation_failure("daemon_rpc", "bad payload", payload={"chat_id": "chat-1"})

    assert posts == []


def test_validation_failure_does_not_post_during_pytest_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[dict[str, object]] = []
    reporting.set_error_reporting(True)
    monkeypatch.delenv("GREENLINE_ENABLE_REPORTING_IN_TESTS", raising=False)
    monkeypatch.setattr(reporting, "CRASH_REPORT_URL", "https://example.test/report")

    def fake_post(*, url: str, json: dict[str, object]):
        posts.append(json)
        return object()

    monkeypatch.setattr(reporting.http, "post", fake_post)

    report_validation_failure("daemon_rpc", "bad payload", payload={"chat_id": "chat-1"})

    assert posts == []


def test_crash_reporter_posts_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[dict[str, object]] = []
    monkeypatch.setenv("GREENLINE_ENABLE_REPORTING_IN_TESTS", "1")
    reporting.set_error_reporting(True)
    monkeypatch.setattr(reporting, "CRASH_REPORT_URL", "https://example.test/report")

    def fake_post(*, url: str, json: dict[str, object]):
        posts.append(json)
        return object()

    monkeypatch.setattr(reporting.http, "post", fake_post)

    @reporting.crash_reporter
    def explode() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        explode()

    assert len(posts) == 1
    assert "RuntimeError: boom" in str(posts[0]["report"])


@pytest.mark.parametrize(
    ("enabled", "url"),
    [
        (False, "https://example.test/report"),
        (True, ""),
    ],
)
def test_crash_reporter_skips_upload_when_disabled_or_url_missing(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    url: str,
) -> None:
    posts: list[dict[str, object]] = []
    reporting.set_error_reporting(enabled)
    monkeypatch.setattr(reporting, "CRASH_REPORT_URL", url)

    def fake_post(*, url: str, json: dict[str, object]):
        posts.append(json)
        return object()

    monkeypatch.setattr(reporting.http, "post", fake_post)

    @reporting.crash_reporter
    def explode() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        explode()

    assert posts == []


def test_crash_reporter_reraises_original_exception_when_upload_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GREENLINE_ENABLE_REPORTING_IN_TESTS", "1")
    reporting.set_error_reporting(True)
    monkeypatch.setattr(reporting, "CRASH_REPORT_URL", "https://example.test/report")

    def fail_post(*, url: str, json: dict[str, object]):
        raise RuntimeError("upload failed")

    monkeypatch.setattr(reporting.http, "post", fail_post)

    @reporting.crash_reporter
    def explode() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        explode()
