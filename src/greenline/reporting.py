import functools
import os
import traceback
from typing import Any, Callable, ParamSpec, TypeVar

from constants import CRASH_REPORT_URL
from ut_components import http

ERROR_REPORTING_KEY = "crash.enabled"
P = ParamSpec("P")
R = TypeVar("R")


def get_error_reporting() -> bool:
    from greenline.contracts.kv import GreenlineKV
    from greenline.store.records import ErrorReportingRecord

    with GreenlineKV() as kv:
        return kv.get_record(ERROR_REPORTING_KEY, default=ErrorReportingRecord(True)).value


def set_error_reporting(enabled: bool) -> None:
    from greenline.contracts.kv import GreenlineKV
    from greenline.store.records import ErrorReportingRecord

    with GreenlineKV() as kv:
        kv.put_record(ERROR_REPORTING_KEY, ErrorReportingRecord(enabled))


def _reporting_blocked_for_tests() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) and os.environ.get("GREENLINE_ENABLE_REPORTING_IN_TESTS") != "1"


def post_error_report(report: str, **payload: Any) -> object | None:
    if not CRASH_REPORT_URL or _reporting_blocked_for_tests():
        return None

    try:
        if not get_error_reporting():
            return None
    except Exception:
        return None

    body = {"report": report}
    body.update(payload)
    return http.post(url=CRASH_REPORT_URL, json=body)


def crash_reporter(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except Exception:
            try:
                post_error_report(traceback.format_exc())
            except Exception:
                pass
            raise

    return wrapper
