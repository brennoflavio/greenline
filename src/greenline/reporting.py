import functools
import json
import os
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, ParamSpec, TypeVar

from constants import CRASH_REPORT_URL
from ut_components import http

ERROR_REPORTING_KEY = "crash.enabled"
REPORT_METADATA_MARKER = "\n\n--- greenline metadata ---\n"
_TRACE_CONTEXT: ContextVar[tuple[dict[str, Any], ...]] = ContextVar("greenline_error_trace_context", default=())
P = ParamSpec("P")
R = TypeVar("R")


def get_error_reporting() -> bool:
    from greenline.contracts.kv import GreenlineKV
    from greenline.store.records import ErrorReportingRecord

    with GreenlineKV() as kv:
        return kv.get_record(ERROR_REPORTING_KEY, default=ErrorReportingRecord(False)).value


def set_error_reporting(enabled: bool) -> None:
    from greenline.contracts.kv import GreenlineKV
    from greenline.store.records import ErrorReportingRecord

    with GreenlineKV() as kv:
        kv.put_record(ERROR_REPORTING_KEY, ErrorReportingRecord(enabled))


def _reporting_blocked_for_tests() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) and os.environ.get("GREENLINE_ENABLE_REPORTING_IN_TESTS") != "1"


def current_error_trace() -> list[dict[str, Any]]:
    return [dict(item) for item in _TRACE_CONTEXT.get()]


@contextmanager
def error_trace_context(name: str, **fields: Any) -> Iterator[None]:
    entry = {"name": name}
    entry.update({key: value for key, value in fields.items() if value not in (None, "", [], {}, ())})
    token = _TRACE_CONTEXT.set(_TRACE_CONTEXT.get() + (entry,))
    try:
        yield
    finally:
        _TRACE_CONTEXT.reset(token)


def capture_stack_summary(limit: int = 12, *, skip: int = 0) -> list[dict[str, Any]]:
    frames = traceback.extract_stack()[: -(skip + 1)]
    summary: list[dict[str, Any]] = []
    for frame in frames[-limit:]:
        summary.append(
            {
                "file": os.path.basename(frame.filename),
                "line": frame.lineno,
                "function": frame.name,
                "code": (frame.line or "").strip(),
            }
        )
    return summary


def get_build_version() -> str:
    try:
        from daemon import get_release_build_version

        return get_release_build_version() or ""
    except Exception:
        return ""


def get_build_commit() -> str:
    try:
        from daemon import get_expected_daemon_version

        return get_expected_daemon_version() or ""
    except Exception:
        return ""


def _format_report(report: str, **payload: Any) -> str:
    metadata = dict(payload)
    metadata["build_version"] = get_build_version()
    metadata["build_commit"] = get_build_commit()
    return (
        report.rstrip()
        + REPORT_METADATA_MARKER
        + json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=repr,
        )
    )


def post_error_report(report: str, **payload: Any) -> object | None:
    if not CRASH_REPORT_URL or _reporting_blocked_for_tests():
        return None

    try:
        if not get_error_reporting():
            return None
    except Exception:
        return None

    return http.post(url=CRASH_REPORT_URL, json={"report": _format_report(report, **payload)})


def crash_reporter(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with error_trace_context("call", function=f"{func.__module__}.{func.__name__}"):
            try:
                return func(*args, **kwargs)
            except Exception:
                try:
                    post_error_report(traceback.format_exc(), trace=current_error_trace())
                except Exception:
                    pass
                raise

    return wrapper
