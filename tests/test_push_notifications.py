from __future__ import annotations

import json
from pathlib import Path

from greenline.push import notifications


class _Daemon:
    def clear_chat_notifications(self, tags: list[str]) -> None:
        return None


def test_notification_counter_uses_total_after_processing_pending_events(monkeypatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures/daemon_events/message/conversation.json"
    fixture = json.loads(fixture_path.read_text())
    processed = False

    def process_events() -> None:
        nonlocal processed
        processed = True

    def unread_total() -> int:
        assert processed
        return 3

    monkeypatch.setattr(notifications, "process_events_once", process_events)
    monkeypatch.setattr(notifications, "get_unread_total", unread_total)
    monkeypatch.setattr(notifications, "daemon_client", _Daemon)

    result = notifications.build_postal_output(json.dumps({"event_type": "Message", "event": fixture["payload"]}))

    assert result["notification"]["emblem-counter"] == {"count": 3, "visible": True}
