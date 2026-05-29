from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar, overload

from greenline.contracts.codecs import decode_dataclass, encode_dataclass
from greenline.contracts.validation import (
    BoundaryValidationError,
    report_validation_failure,
)
from greenline.reporting import error_trace_context
from greenline.store.records import (
    DaemonLastEventIDRecord,
    DraftMentionsRecord,
    DraftRecord,
    ErrorReportingRecord,
    LidMapRecord,
    MessageIndexRecord,
    NotificationsSuppressedRecord,
    PendingOutboxRecord,
    StickerCacheRecord,
    StopDaemonOnExitRecord,
    StoredMessageRecord,
    UnhandledMessageRecord,
    UnknownEventRecord,
    UnreadTotalRecord,
)
from models import ChatListItem
from ut_components.kv import KV

T = TypeVar("T")
_MISSING = object()


@dataclass(frozen=True)
class KVContract(Generic[T]):
    name: str
    record_type: type[T]
    storage: str = "object"
    field: str = "value"
    prefix: bool = True


KV_CONTRACTS: tuple[KVContract[Any], ...] = (
    KVContract("daemon:last_event_id", DaemonLastEventIDRecord, "scalar", prefix=False),
    KVContract("unread_total", UnreadTotalRecord, "scalar", prefix=False),
    KVContract("notifications_suppressed", NotificationsSuppressedRecord, "scalar", prefix=False),
    KVContract("crash.enabled", ErrorReportingRecord, "scalar", prefix=False),
    KVContract("daemon.stop_on_exit", StopDaemonOnExitRecord, "scalar", prefix=False),
    KVContract("pending-outbox:", PendingOutboxRecord),
    KVContract("unhandled_message:", UnhandledMessageRecord),
    KVContract("unknown_event:", UnknownEventRecord),
    KVContract("message_index:", MessageIndexRecord, "scalar"),
    KVContract("message:", StoredMessageRecord),
    KVContract("chat:", ChatListItem),
    KVContract("draft_mentions:", DraftMentionsRecord, "scalar"),
    KVContract("draft:", DraftRecord, "scalar"),
    KVContract("lid_map:", LidMapRecord, "scalar"),
    KVContract("sticker_cache:", StickerCacheRecord, "scalar"),
)


def _contract_for(key: str) -> KVContract[Any]:
    for contract in KV_CONTRACTS:
        if (contract.prefix and key.startswith(contract.name)) or (not contract.prefix and key == contract.name):
            return contract
    error = f"no KV contract registered for key {key!r}"
    report_validation_failure("kv", error, payload={"key": key}, contract=key)
    raise KeyError(error)


def _decode_value(contract: KVContract[T], value: Any) -> T:
    payload = {contract.field: value} if contract.storage == "scalar" else value
    try:
        return decode_dataclass(
            contract.record_type,
            payload,
            boundary="kv",
            contract=contract.name,
            direction="decode",
            strict=True,
        )
    except Exception as exc:
        raise BoundaryValidationError(str(exc)) from exc


def _encode_value(contract: KVContract[Any], record: Any) -> Any:
    if not isinstance(record, contract.record_type):
        error = f"expected {contract.record_type.__name__}, got {type(record).__name__}"
        report_validation_failure(
            "kv",
            error,
            payload=record,
            contract=contract.name,
            direction="encode",
            dataclass_name=contract.record_type.__name__,
        )
        raise TypeError(error)

    payload = encode_dataclass(
        record,
        boundary="kv",
        contract=contract.name,
        direction="encode",
    )
    try:
        decode_dataclass(
            contract.record_type,
            payload,
            boundary="kv",
            contract=contract.name,
            direction="encode",
            strict=True,
        )
    except Exception as exc:
        raise BoundaryValidationError(str(exc)) from exc

    if contract.storage == "scalar":
        return payload[contract.field]
    if isinstance(record, StoredMessageRecord) and payload.get("raw") is None:
        payload.pop("raw", None)
    return payload


class GreenlineKV:
    def __init__(self, kv: KV | None = None) -> None:
        self._kv = kv or KV()
        self._owns_kv = kv is None

    def __enter__(self) -> "GreenlineKV":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if self._owns_kv:
            self._kv.close()

    @property
    def raw(self) -> KV:
        return self._kv

    def close(self) -> None:
        self._kv.close()

    def put_record(self, key: str, record: Any, ttl_seconds: int | None = None) -> None:
        with error_trace_context("kv", key=key, direction="encode"):
            contract = _contract_for(key)
            self._kv.put(key, _encode_value(contract, record), ttl_seconds=ttl_seconds)

    def put_cached_record(self, key: str, record: Any, ttl_seconds: int | None = None) -> None:
        with error_trace_context("kv", key=key, direction="encode"):
            contract = _contract_for(key)
            self._kv.put_cached(key, _encode_value(contract, record), ttl_seconds=ttl_seconds)

    @overload
    def get_record(self, key: str, *, required: bool = False) -> Any | None: ...

    @overload
    def get_record(self, key: str, default: T, *, required: bool = False) -> T: ...

    def get_record(self, key: str, default: Any = _MISSING, *, required: bool = False) -> Any | None:
        with error_trace_context("kv", key=key, direction="decode"):
            contract = _contract_for(key)
            value = self._kv.get(key, default=_MISSING)
            if value is _MISSING:
                if default is _MISSING:
                    if required:
                        report_validation_failure(
                            "kv",
                            f"missing KV key {key!r}",
                            payload={"key": key},
                            contract=contract.name,
                            direction="decode",
                            dataclass_name=contract.record_type.__name__,
                        )
                    return None
                if not isinstance(default, contract.record_type):
                    error = f"default for {key!r} must be {contract.record_type.__name__}"
                    report_validation_failure(
                        "kv",
                        error,
                        payload=default,
                        contract=contract.name,
                        direction="decode",
                        dataclass_name=contract.record_type.__name__,
                    )
                    raise TypeError(error)
                return default
            return _decode_value(contract, value)

    def get_partial_records(self, beginning: str) -> list[tuple[str, Any]]:
        with error_trace_context("kv", key=beginning, direction="decode"):
            contract = _contract_for(beginning)
            records: list[tuple[str, Any]] = []
            for key, value in self._kv.get_partial(beginning):
                with error_trace_context("kv", key=key, direction="decode"):
                    records.append((key, _decode_value(contract, value)))
            return records

    def get_partial_page_records(
        self,
        beginning: str,
        page_size: int = 50,
        cursor: str | None = None,
        reverse: bool = False,
    ) -> tuple[list[tuple[str, Any]], str | None]:
        with error_trace_context("kv", key=beginning, direction="decode", cursor=cursor, reverse=reverse):
            contract = _contract_for(beginning)
            rows, next_cursor = self._kv.get_partial_page(
                beginning,
                page_size=page_size,
                cursor=cursor,
                reverse=reverse,
            )
            records: list[tuple[str, Any]] = []
            for key, value in rows:
                with error_trace_context("kv", key=key, direction="decode"):
                    records.append((key, _decode_value(contract, value)))
            return records, next_cursor

    def delete(self, key: str) -> None:
        with error_trace_context("kv", key=key, direction="delete"):
            _contract_for(key)
            self._kv.delete(key)

    def delete_partial(self, beginning: str) -> None:
        with error_trace_context("kv", key=beginning, direction="delete"):
            _contract_for(beginning)
            self._kv.delete_partial(beginning)

    def commit_cached(self) -> None:
        self._kv.commit_cached()
