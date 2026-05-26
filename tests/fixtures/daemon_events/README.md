# Daemon event fixtures

These fixtures were generated from the repository root `kv.db` and sanitized before being written.

Each JSON file contains:

- `id`: deterministic fixture event id
- `event_type`: daemon event type as consumed by Python dispatch
- `payload`: sanitized daemon JSON payload object
- `_meta`: non-sensitive source notes

Tests build a `daemon_types.StoredEvent` with `event_type` and `json.dumps(payload)`, dispatch it through `greenline.events.handlers.dispatch_event(...)`, and compare the resulting isolated KV diff with the committed snapshot in `tests/fixtures/daemon_event_kv_snapshots/`.

## What the KV snapshots mean

Snapshot files mirror fixture paths. For example:

- Fixture: `tests/fixtures/daemon_events/message/conversation.json`
- Snapshot: `tests/fixtures/daemon_event_kv_snapshots/message/conversation.kv.json`

Each snapshot contains:

- `added`: KV keys created by dispatch
- `changed`: KV keys changed by dispatch, with `before` and `after`
- `deleted`: KV keys removed by dispatch

The test runtime isolates `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, and daemon access. Volatile config/cache paths are normalized to `<CONFIG>` and `<CACHE>`.

## Running tests

```bash
uv run pytest tests/test_daemon_event_fixtures.py tests/test_daemon_event_kv_snapshots.py
```

The tests verify that every manifest fixture parses into the current `whatsmeow_types` dataclass, fixture JID fields are sanitized, every fixture has a KV snapshot, and stored KV entries reconstruct valid app datatypes.

## Updating snapshots

Only update snapshots for intentional daemon→Python parsing/storage behavior changes. Snapshot diffs define the current storage contract and must be reviewed before commit.

Regenerate all snapshots with:

```bash
uv run python tests/tools/update_daemon_event_kv_snapshots.py
```

Or update through pytest with the explicit guard:

```bash
UPDATE_DAEMON_EVENT_KV_SNAPSHOTS=1 uv run pytest tests/test_daemon_event_kv_snapshots.py
```

After updating, review the changed `*.kv.json` files and rerun the full command above.

## Adding a fixture

1. Add the sanitized fixture JSON under this directory.
2. Add an entry to `manifest.json`.
3. Run the fixture tests to catch malformed JSON, parse failures, or unsanitized JID fields.
4. Regenerate KV snapshots with one of the explicit update commands.
5. Review the snapshot diff and rerun the full daemon event test command.

Sensitive data that was sanitized includes JIDs/phone-like identifiers, names, message text/captions, media URLs/paths/keys/hashes, thumbnails, vcards, and opaque IDs.
