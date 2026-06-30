from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import pytest

import greenline.reporting as reporting
from greenline.contracts.codecs import decode_dataclass, encode_dataclass, to_json_like
from greenline.contracts.daemon import GreenlineDaemon
from greenline.contracts.kv import GreenlineKV
from greenline.contracts.qml import (
    decode_qml_request,
    qml_api,
    validate_qml_event,
    validate_qml_response,
)
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


class FakeTransport:
    def __init__(self, replies: dict[str, object]) -> None:
        self.replies = replies

    def _call(self, method: str, params: dict[str, object] | None = None) -> object:
        return self.replies.get(method, {})


def _capture_reports(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    posts: list[dict[str, object]] = []
    monkeypatch.setenv("GREENLINE_ENABLE_REPORTING_IN_TESTS", "1")
    reporting.set_error_reporting(True)
    monkeypatch.setattr(reporting, "CRASH_REPORT_URL", "https://example.test/report")
    monkeypatch.setattr(reporting, "get_build_version", lambda: "test-commit")

    def fake_post(*, url: str, json: dict[str, object]):
        posts.append({"url": url, "json": json})
        return object()

    monkeypatch.setattr(reporting.http, "post", fake_post)
    return posts


def _report_body(post: dict[str, object]) -> dict[str, object]:
    if "json" in post:
        return post["json"]  # type: ignore[return-value]
    return post


def _report_metadata(post: dict[str, object]) -> dict[str, object]:
    body = _report_body(post)
    report = body["report"]
    assert isinstance(report, str)
    prefix, marker, metadata = report.partition(reporting.REPORT_METADATA_MARKER)
    assert prefix
    assert marker == reporting.REPORT_METADATA_MARKER
    return json.loads(metadata)


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
        contract="Service.PrioritizeAvatars",
        direction="encode",
    )

    assert "daemon_rpc contract=Service.PrioritizeAvatars direction=encode validation failed" in caplog.text


def test_json_like_assertion_raises_after_logging(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(BoundaryValidationError):
        assert_json_like(SamplePayload(chat_id="chat-1"), boundary="test.payload")

    assert "test.payload validation failed" in caplog.text


def test_invalid_decode_posts_structured_validation_report(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = _capture_reports(monkeypatch)

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
    payload = _report_body(posts[0])
    assert payload.keys() == {"report"}
    metadata = _report_metadata(posts[0])
    assert metadata["failure"] == 'missing value for field "chat_id"'
    assert metadata["data"] == {"tags": ["text"]}
    assert metadata["dataclass"] == "SamplePayload"
    assert metadata["boundary"] == "daemon_rpc"
    assert metadata["contract"] == "Service.SendMessage"
    assert metadata["direction"] == "decode"
    assert metadata["build_version"] == "test-commit"
    assert metadata["trace"] == []
    assert isinstance(metadata["stack"], list)
    assert metadata["stack"]
    assert str(payload["report"]).startswith(
        "daemon_rpc contract=Service.SendMessage direction=decode validation failed:"
    )


def test_validation_failure_normalizes_non_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[dict[str, object]] = []

    _capture_reports(monkeypatch)

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

    assert len(posts) == 1
    payload = posts[0]
    metadata = _report_metadata(payload)
    assert str(payload["report"]).startswith(
        "daemon_rpc contract=Service.SendMessage direction=decode validation failed: bad payload"
    )
    assert metadata["failure"] == "bad payload"
    assert metadata["data"] == {
        "sample": {"chat_id": "chat-1", "tags": ["text"], "nested": {"kind": "text"}},
        "path": "avatar.jpg",
        "items": ["text"],
        "error": {"type": "RuntimeError", "message": "boom"},
    }
    assert metadata["dataclass"] == "SamplePayload"
    assert metadata["boundary"] == "daemon_rpc"
    assert metadata["contract"] == "Service.SendMessage"
    assert metadata["direction"] == "decode"
    assert metadata["build_version"] == "test-commit"
    assert metadata["trace"] == []
    assert isinstance(metadata["stack"], list)
    assert metadata["stack"]


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


def test_qml_request_boundary_reports_trace_context(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = _capture_reports(monkeypatch)

    with pytest.raises(BoundaryValidationError):
        decode_qml_request("send_presence", ("true",), {})

    assert len(posts) == 1
    assert _report_body(posts[0]).keys() == {"report"}
    assert _report_metadata(posts[0])["trace"] == [
        {"name": "qml_api", "contract": "send_presence", "direction": "decode"}
    ]


def test_qml_response_boundary_reports_trace_context(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = _capture_reports(monkeypatch)

    with pytest.raises(BoundaryValidationError):
        validate_qml_response("get_sync_status", {"syncing": True})

    assert len(posts) == 1
    assert _report_metadata(posts[0])["trace"] == [
        {"name": "qml_api", "contract": "get_sync_status", "direction": "encode"}
    ]


def test_qml_event_boundary_reports_trace_context(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = _capture_reports(monkeypatch)

    with pytest.raises(BoundaryValidationError):
        validate_qml_event("sync-status", {"syncing": True})

    assert len(posts) == 1
    assert _report_metadata(posts[0])["trace"] == [
        {"name": "qml_event", "contract": "sync-status", "direction": "encode"}
    ]


def test_daemon_boundary_reports_trace_context(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = _capture_reports(monkeypatch)
    transport = FakeTransport({"Service.GetVersion": {"bad": "payload"}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    with pytest.raises(BoundaryValidationError):
        daemon.get_version()

    assert len(posts) == 1
    assert _report_metadata(posts[0])["trace"] == [
        {"name": "daemon_rpc", "contract": "Service.GetVersion", "direction": "decode"}
    ]


def test_kv_boundary_reports_trace_context(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = _capture_reports(monkeypatch)

    with GreenlineKV() as kv:
        with pytest.raises(TypeError):
            kv.put_record("unread_total", 1)

    assert len(posts) == 1
    assert _report_metadata(posts[0])["trace"] == [{"name": "kv", "key": "unread_total", "direction": "encode"}]


def test_qml_api_wrapper_keeps_origin_trace_for_nested_boundary_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = _capture_reports(monkeypatch)

    @qml_api("get_chat_info")
    def get_chat_info(_request: object) -> object:
        with GreenlineKV() as kv:
            kv.put_record("unread_total", 1)
        return {"success": True}

    with pytest.raises(TypeError):
        get_chat_info("chat@s.whatsapp.net")

    assert len(posts) == 1
    assert _report_metadata(posts[0])["trace"] == [
        {"name": "qml_api", "contract": "get_chat_info", "direction": "call"},
        {"name": "kv", "key": "unread_total", "direction": "encode"},
    ]


def test_kv_partial_read_reports_failing_row_key(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = _capture_reports(monkeypatch)

    with GreenlineKV() as kv:
        kv.raw.put("chat:bad", {"id": "chat:bad"})
        with pytest.raises(BoundaryValidationError):
            kv.get_partial_records("chat:")

    assert len(posts) == 1
    assert _report_metadata(posts[0])["trace"] == [
        {"name": "kv", "key": "chat:", "direction": "decode"},
        {"name": "kv", "key": "chat:bad", "direction": "decode"},
    ]


def test_validation_failure_includes_trace_context(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[dict[str, object]] = []

    def fake_post(*, url: str, json: dict[str, object]):
        posts.append(json)
        return object()

    _capture_reports(monkeypatch)
    monkeypatch.setattr(reporting.http, "post", fake_post)

    with reporting.error_trace_context("event", event_type="Message", event_id=42):
        report_validation_failure("daemon_rpc", "bad payload", payload={"chat_id": "chat-1"})

    assert len(posts) == 1
    metadata = _report_metadata(posts[0])
    assert metadata["build_version"] == "test-commit"
    assert metadata["trace"] == [{"name": "event", "event_type": "Message", "event_id": 42}]


def test_crash_reporter_posts_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[dict[str, object]] = []

    def fake_post(*, url: str, json: dict[str, object]):
        posts.append(json)
        return object()

    _capture_reports(monkeypatch)
    monkeypatch.setattr(reporting.http, "post", fake_post)

    @reporting.crash_reporter
    def explode() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        explode()

    assert len(posts) == 1
    metadata = _report_metadata(posts[0])
    assert "RuntimeError: boom" in str(posts[0]["report"])
    assert metadata["build_version"] == "test-commit"
    assert metadata["trace"] == [{"name": "call", "function": f"{explode.__module__}.explode"}]


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
