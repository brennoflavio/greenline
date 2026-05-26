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

1. Add daemon-shaped request dataclasses to `src/greenline/contracts/daemon.py` for every request payload field sent to the daemon.
2. Reuse reply dataclasses from `src/daemon_types.py` when they already exist, or add a small reply dataclass in the boundary for simple daemon results.
3. Encode requests with `greenline.contracts.codecs.encode_dataclass(...)` and decode typed replies with `decode_dataclass(...)` so validation failures are logged centrally.
4. Expose the method on `GreenlineDaemon` and call it from app code with `daemon_client()`.
5. Update `tests/conftest.py`'s fake daemon client state if high-level tests need the method.
6. Add or extend focused boundary tests in `tests/test_daemon_boundary.py` for request shape, reply decoding, and malformed reply logging.
7. Run `uv run python tests/tools/check_daemon_rpc_boundary.py` and `uv run pytest`.

Only update the scanner allowlist in `tests/tools/check_daemon_rpc_boundary.py` for true low-level boundary code or scanner/fake infrastructure. Do not allowlist normal app modules to work around the guard.

## Pre-commit enforcement

Pre-commit runs the contract scanners and pytest. It fails when:

- QML calls a `main.*` function with no API contract.
- `src/main.py` exports a QML-facing function with no API contract.
- QML registers a handler with no event contract.
- A registry entry exists for a removed API/event.
- App code bypasses the QML bridge with raw `pyotherside.send(...)`.
- App code bypasses the daemon boundary with direct `DaemonRPC` imports, `DaemonRPC()` construction, or `rpc.DaemonRPC` access.

Use the scanner failure output as the checklist for what contract or boundary update is missing.
