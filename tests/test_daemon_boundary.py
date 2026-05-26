from __future__ import annotations

from typing import Any

import pytest

from daemon_types import SendMessageReply
from greenline.contracts.daemon import (
    GreenlineDaemon,
    daemon_client,
    set_daemon_client_factory,
)
from greenline.contracts.validation import BoundaryValidationError


class FakeTransport:
    def __init__(self, replies: dict[str, Any]) -> None:
        self.replies = replies
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def _call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, params))
        return self.replies.get(method, {})


def test_daemon_boundary_encodes_request_and_decodes_send_message_reply() -> None:
    transport = FakeTransport({"Service.SendMessage": {"MessageID": "message-1", "Timestamp": 123}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    reply = daemon.send_message(
        "chat-1",
        "text",
        text="Hello",
        reply_context={
            "id": "quoted-1",
            "participant": "sender-1",
            "quoted_message": {"text": "Hi"},
        },
        mentioned_jids=["sender-1"],
    )

    assert reply == SendMessageReply(MessageID="message-1", Timestamp=123)
    assert transport.calls == [
        (
            "Service.SendMessage",
            {
                "ChatJID": "chat-1",
                "Type": "text",
                "Text": "Hello",
                "FilePath": "",
                "Caption": "",
                "DurationSeconds": 0,
                "PTT": False,
                "ReplyToMessageID": "quoted-1",
                "ReplyParticipantJID": "sender-1",
                "ReplyQuotedMessage": {"text": "Hi"},
                "MentionedJIDs": ["sender-1"],
            },
        )
    ]


def test_daemon_boundary_normalizes_missing_event_list() -> None:
    transport = FakeTransport({"Service.ListEvents": {"Events": None}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    reply = daemon.list_events(after_id=3, limit=4)

    assert reply.Events == []
    assert transport.calls == [("Service.ListEvents", {"AfterID": 3, "Limit": 4})]


def test_daemon_client_factory_is_injectable() -> None:
    fake = object()
    set_daemon_client_factory(lambda: fake)
    try:
        assert daemon_client() is fake
    finally:
        set_daemon_client_factory(None)


def test_daemon_boundary_normalizes_missing_group_list() -> None:
    transport = FakeTransport({"Service.GetGroups": {"Groups": None}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    reply = daemon.get_groups()

    assert reply.Groups == []
    assert transport.calls == [("Service.GetGroups", None)]


def test_daemon_boundary_download_media_decodes_file_path() -> None:
    transport = FakeTransport({"Service.DownloadMedia": {"FilePath": "/tmp/media.webp"}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    file_path = daemon.download_media(
        direct_path="/direct",
        media_key="key",
        file_enc_sha256="enc",
        file_sha256="plain",
        file_length=12,
        media_type="sticker",
        mimetype="image/webp",
        message_id="message-1",
        chat_id="chat-1",
        file_name="sticker.webp",
    )

    assert file_path == "/tmp/media.webp"
    assert transport.calls == [
        (
            "Service.DownloadMedia",
            {
                "DirectPath": "/direct",
                "MediaKey": "key",
                "FileEncSHA256": "enc",
                "FileSHA256": "plain",
                "FileLength": 12,
                "MediaType": "sticker",
                "Mimetype": "image/webp",
                "MessageID": "message-1",
                "ChatID": "chat-1",
                "FileName": "sticker.webp",
            },
        )
    ]


def test_daemon_boundary_ensure_jid_and_phone_number() -> None:
    transport = FakeTransport({"Service.EnsureJID": {"JID": "15551234567@s.whatsapp.net"}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    assert daemon.ensure_jid("lid-user@lid") == "15551234567@s.whatsapp.net"
    assert daemon.get_phone_number("lid-user@lid") == "+15551234567"
    assert transport.calls == [
        ("Service.EnsureJID", {"JID": "lid-user@lid"}),
        ("Service.EnsureJID", {"JID": "lid-user@lid"}),
    ]


def test_daemon_boundary_ensure_jid_preserves_explicit_empty_reply() -> None:
    transport = FakeTransport({"Service.EnsureJID": {"JID": ""}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    assert daemon.ensure_jid("lid-user@lid") == ""
    assert daemon.get_phone_number("lid-user@lid") == ""
    assert transport.calls == [
        ("Service.EnsureJID", {"JID": "lid-user@lid"}),
        ("Service.EnsureJID", {"JID": "lid-user@lid"}),
    ]


def test_daemon_boundary_noop_commands_encode_expected_payloads() -> None:
    transport = FakeTransport({})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    daemon.delete_events(7)
    daemon.mark_read("chat-1", ["message-1"], sender_jid="sender-1")
    daemon.send_presence(True)
    daemon.subscribe_presence("chat-1")
    daemon.logout()
    daemon.set_notification_counter(3, True)
    daemon.clear_chat_notifications(["chat-1"])

    assert transport.calls == [
        ("Service.DeleteEvents", {"UpToID": 7}),
        (
            "Service.MarkRead",
            {"ChatJID": "chat-1", "SenderJID": "sender-1", "MessageIDs": ["message-1"]},
        ),
        ("Service.SendPresence", {"Available": True}),
        ("Service.SubscribePresence", {"JID": "chat-1"}),
        ("Service.Logout", None),
        ("Service.SetNotificationCounter", {"Count": 3, "Visible": True}),
        ("Service.ClearChatNotifications", {"Tags": ["chat-1"]}),
    ]


def test_daemon_boundary_logs_invalid_typed_reply(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = FakeTransport({"Service.SendMessage": {"MessageID": "message-1", "Timestamp": "later"}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    with pytest.raises(Exception):
        daemon.send_message("chat-1", "text")

    assert "daemon.reply.Service.SendMessage validation failed" in caplog.text


def test_daemon_boundary_rejects_missing_send_message_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = FakeTransport({"Service.SendMessage": {"Timestamp": 123}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    with pytest.raises(BoundaryValidationError):
        daemon.send_message("chat-1", "text")

    assert "Service.SendMessage reply requires non-empty MessageID" in caplog.text
