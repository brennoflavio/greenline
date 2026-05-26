# Daemon event fixtures

These fixtures are sanitized daemon-shaped JSON events. Most early fixtures were generated from a real `kv.db`; for the ones we could not capture we wrote stubs.

Each JSON file contains:

- `id`: deterministic fixture event id
- `event_type`: daemon event type as consumed by Python dispatch
- `payload`: sanitized daemon JSON payload object
- `_meta`: non-sensitive source notes

`manifest.json` is the fixture index. Its `source_family` declares the expected behavior category, such as `message`, `unhandled_message`, `parse_only`, `receipt`, `chat_update`, `photo_update`, `presence`, `chat_presence`, `history_sync`, or `unknown_event`.

## Behavior contract

The daemon → Python contract is covered at multiple levels:

- `tests/test_daemon_event_coverage.py` defines `DAEMON_EVENT_CONTRACTS` for every `_dispatch_event_inner()` branch and classifies event types as `handled`, `parse-only`, or `ignored`.
- Every `handled` and `parse-only` event type must have at least one manifest fixture.
- `tests/test_daemon_event_kv_snapshots.py` dispatches every fixture, validates KV datatypes, checks manifest intent, compares KV diffs, and compares dispatch output buckets.
- `tests/test_daemon_event_ignored_unknown.py` protects intentionally ignored events and unknown fallback storage.
- `tests/test_message_type_mapping.py` covers direct message mapping and store behavior for each message fixture variant.
- `tests/test_daemon_event_loop.py` covers `process_events_once()` and `DaemonEventHandler._do_trigger()` batching, deletion, last-id advancement, and QML emissions.
- `tests/contracts/qml_payloads.py` validates QML-safe payload schemas for event-loop emissions.

## Snapshots

KV snapshots live in `tests/fixtures/daemon_event_kv_snapshots/` and output snapshots live in `tests/fixtures/daemon_event_output_snapshots/`. Both mirror fixture paths. For example:

- Fixture: `tests/fixtures/daemon_events/message/conversation.json`
- KV snapshot: `tests/fixtures/daemon_event_kv_snapshots/message/conversation.kv.json`
- Output snapshot: `tests/fixtures/daemon_event_output_snapshots/message/conversation.output.json`

KV snapshots contain `added`, `changed`, and `deleted` keys. Output snapshots contain normalized dispatch buckets: `chat_updates`, `message_upserts`, `message_updates`, `photo_updates`, `presence_updates`, and `chat_presence_updates`.

The test runtime isolates `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, app dirs, daemon RPC, and `pyotherside`. Volatile paths are normalized to `<CONFIG>` and `<CACHE>`. Some fixtures seed prerequisite KV state before capturing the `before` snapshot, so dependent behavior such as receipt updates, mute/photo/name updates, and delete events is tested without seed data appearing as newly added output.

> **Review warning:** KV snapshots and output snapshots together define the daemon → Python behavior contract. Only update them for intentional behavior changes, and review both `*.kv.json` and `*.output.json` diffs before committing.

## Running tests

```bash
uv run pytest
```

## Updating snapshots

Regenerate all KV and output snapshots with the explicit updater:

```bash
uv run python tests/tools/update_daemon_event_kv_snapshots.py
```

The snapshot test also supports the explicit pytest guard:

```bash
UPDATE_DAEMON_EVENT_KV_SNAPSHOTS=1 uv run pytest tests/test_daemon_event_kv_snapshots.py
```

After updating, review changed `*.kv.json` and `*.output.json` files, then rerun the tests above.

## Adding a fixture

1. Add sanitized fixture JSON under this directory.
2. Add an entry to `manifest.json` with the correct `event_type`, `path`, and `source_family`.
3. If it is a new dispatcher branch, update `DAEMON_EVENT_CONTRACTS` in `tests/test_daemon_event_coverage.py`.
4. Add or adjust seed behavior in `tests/daemon_event_helpers.py` if the event needs prior chat/message state.
5. Regenerate snapshots with `uv run python tests/tools/update_daemon_event_kv_snapshots.py`.
6. Review snapshot diffs and rerun the daemon event tests.

Sensitive data that was sanitized includes JIDs/phone-like identifiers, names, message text/captions, media URLs/paths/keys/hashes, thumbnails, vcards, and opaque IDs.
