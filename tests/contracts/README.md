# Python → QML contract workflow

Greenline exposes Python data to QML through `main.*` calls and async `setHandler(...)` events. These paths must all use the same documented contracts so live updates cannot drop fields that are present after an app reload, such as `sender_photo`, `photo`, reply fields, mute/name fields, or mention metadata.

## Source-side rules

- Serialize QML-facing messages and chats through `src/greenline/qml_payloads.py`.
- Emit app-level QML events through `src/greenline/qml_events.py`.
- Do not call `pyotherside.send(...)` directly in app code. The only raw `pyotherside` exemptions are:
  - `src/greenline/qml_events.py` (Greenline bridge)
  - `src/ut_components/event.py` (framework dispatcher)
- `get_messages()` and `message-upsert` must satisfy the same full `UiMessage` schema.
- `get_chat_list().chats[]` and `chat-list-update` must satisfy the same base `ChatListItem` schema; `get_chat_list()` may add `draft` and `has_draft`.

## Test-side contracts

- Full payload validators live in `tests/contracts/qml_payloads.py`.
- The registry of all QML-facing APIs/events lives in `tests/contracts/qml_registry.py`.
- Static coverage scanning lives in `tests/tools/check_qml_contract_coverage.py` and is also covered by `tests/test_qml_contract_coverage.py`.

## Adding a new `main.*` API

1. Implement the Python function and export it from `src/main.py` only if QML must call it.
2. Add or reuse a validator in `tests/contracts/qml_payloads.py`.
3. Add an `ApiContract` entry in `tests/contracts/qml_registry.py`.
4. Add direct API contract tests that call the function and validate the response through the registry.
5. If the API emits events, emit through `greenline.qml_events` and validate emitted payloads in tests.
6. Run:

```bash
uv run python tests/tools/check_qml_contract_coverage.py
uv run pytest
```

## Adding a new async QML event

1. Add an event payload helper/emitter to `src/greenline/qml_events.py`.
2. Add or reuse a strict validator in `tests/contracts/qml_payloads.py`.
3. Add an `EventContract` entry in `tests/contracts/qml_registry.py`.
4. Add an event contract test from a real emitter path.
5. Register the QML handler with a literal `setHandler('event-name', ...)` so the scanner can discover it.

## Daemon RPC boundary workflow

App code must not instantiate `DaemonRPC()` or import the low-level transport directly. The only runtime owner of daemon socket access is `src/greenline/contracts/daemon.py`; `src/rpc.py` remains the low-level socket implementation and exception source.

When adding or changing a daemon RPC:

1. Add a daemon-shaped request dataclass to `src/greenline/contracts/daemon.py` for every `Service.*` call. Use `EmptyRequest` for calls with no daemon payload.
2. Reuse reply dataclasses from `src/daemon_types.py` when they already exist, or add a small reply dataclass in the boundary for simple daemon results. Empty command replies must decode to `EmptyReply`; scalar daemon replies must be wrapped in a reply dataclass such as `PingReply`.
3. Encode every request with `greenline.contracts.codecs.encode_dataclass(...)` and decode every reply with `decode_dataclass(...)` or a dedicated boundary helper. Pass `boundary="daemon_rpc"`, `contract="Service.<Method>"`, and `direction="encode"` or `"decode"` so validation logs include all daemon boundary metadata.
4. Expose the method on `GreenlineDaemon` and `DaemonClientProtocol` with a dataclass return type. Do not expose raw daemon `dict`, `Any`, primitive `str`, or ignored `None` replies from direct daemon wrappers.
5. Convenience helpers may return primitives only when they are clearly derived from dataclass-returning wrappers, e.g. `get_phone_number()` derives from `ensure_jid(...).JID` instead of representing a separate daemon reply.
6. Call daemon methods from app code through `greenline.contracts.daemon.daemon_client()`. Direct `DaemonRPC` imports/construction remain restricted to `src/rpc.py` and `src/greenline/contracts/daemon.py`.
7. Update `tests/conftest.py`'s fake daemon client state if high-level tests need the method, keeping fake returns aligned with `DaemonClientProtocol` dataclasses.
8. Add or extend focused boundary tests in `tests/test_daemon_boundary.py` for request shape, reply decoding, malformed reply logging, and the contract completeness guard.
9. Run `uv run python tests/tools/check_daemon_rpc_boundary.py` and `uv run pytest`.

Only update the scanner allowlist in `tests/tools/check_daemon_rpc_boundary.py` for true low-level boundary code or scanner/fake infrastructure. Do not allowlist normal app modules to work around the guard.

## KV boundary workflow

Greenline-owned KV storage must go through `src/greenline/contracts/kv.py`. The low-level `ut_components.kv.KV` remains framework storage only; app code gets a dataclass guarantee from `GreenlineKV`.

When adding or changing a Greenline KV key:

1. Add or reuse a dataclass record in `src/greenline/store/records.py`. Object keys store dict-shaped records; scalar/list keys use single-field `value` wrappers so the on-disk JSON shape stays unchanged.
2. Register the key or prefix in `KV_CONTRACTS` with the expected record type and storage mode.
3. Read/write through `GreenlineKV.get_record()`, `put_record()`, `get_partial_records()`, or cached variants. Do not use raw `KV()` in app modules.
4. Decode failures and invalid writes are strict in production. Missing keys may use explicit typed defaults, but malformed stored rows should raise after boundary logging with `boundary="kv"`.
5. Convert dataclasses to dicts only at API/QML serializer boundaries or raw snapshot assertions.
6. Add focused tests for the new record shape and update fixture/snapshot validation when a new key family is introduced.
7. Run `uv run python tests/tools/check_kv_boundary.py` and the affected pytest targets.

Only update the KV scanner allowlist for true framework or boundary code (`src/ut_components/*`, `src/greenline/contracts/kv.py`) or intentionally raw test snapshot infrastructure. Do not allowlist normal app modules to work around the guard.

## Pre-commit enforcement

Pre-commit runs the contract scanners and pytest. It fails when:

- QML calls a `main.*` function with no API contract.
- `src/main.py` exports a QML-facing function with no API contract.
- QML registers a handler with no event contract.
- A registry entry exists for a removed API/event.
- App code bypasses the QML bridge with raw `pyotherside.send(...)`.
- App code bypasses the daemon boundary with direct `DaemonRPC` imports, `DaemonRPC()` construction, or `rpc.DaemonRPC` access.
- App code bypasses the KV boundary with raw `ut_components.kv.KV` imports, `KV()` construction, or `ut_components.kv.KV` access.

Use the scanner failure output as the checklist for what contract or boundary update is missing.
