from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import is_dataclass
from typing import Any, get_args, get_origin, get_type_hints

import pytest

from daemon_types import (
    Contact,
    GetChatSettingsReply,
    GroupParticipant,
    PairPhoneReply,
    SendMessageReply,
    SessionStatusReply,
    SyncAvatarReply,
    VersionReply,
)
from greenline.contracts.daemon import (
    DaemonClientProtocol,
    DeleteMessageReply,
    DownloadMediaReply,
    EditMessageReply,
    EmptyReply,
    EnsureJIDReply,
    GreenlineDaemon,
    PingReply,
    daemon_client,
    set_daemon_client_factory,
)
from greenline.contracts.validation import BoundaryValidationError

RAW_DAEMON_REPLY_EXCEPTIONS = {"get_phone_number"}


def _is_raw_reply_annotation(annotation: Any) -> bool:
    if annotation in (Any, str, None, type(None)):
        return True
    origin = get_origin(annotation)
    if origin is dict:
        return True
    return any(_is_raw_reply_annotation(arg) for arg in get_args(annotation))


def _is_self_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_call"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    )


class FakeTransport:
    def __init__(self, replies: dict[str, Any]) -> None:
        self.replies = replies
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def _call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, params))
        return self.replies.get(method, {})


def test_daemon_protocol_and_wrappers_do_not_expose_raw_daemon_replies() -> None:
    protocol_hints = get_type_hints(DaemonClientProtocol)
    wrapper_hints = get_type_hints(GreenlineDaemon)

    for name, method in inspect.getmembers(DaemonClientProtocol, inspect.isfunction):
        if name.startswith("_") or name in RAW_DAEMON_REPLY_EXCEPTIONS:
            continue
        annotation = get_type_hints(method).get("return")
        assert annotation is not None, name
        assert not _is_raw_reply_annotation(annotation), name
        assert is_dataclass(annotation), name

    for name, method in inspect.getmembers(GreenlineDaemon, inspect.isfunction):
        if name.startswith("_") or name in RAW_DAEMON_REPLY_EXCEPTIONS:
            continue
        annotation = get_type_hints(method).get("return")
        assert annotation is not None, name
        assert not _is_raw_reply_annotation(annotation), name
        assert is_dataclass(annotation), name

    assert protocol_hints == {}
    assert wrapper_hints == {}


def test_daemon_wrappers_do_not_ignore_or_return_raw_transport_calls() -> None:
    for name, method in inspect.getmembers(GreenlineDaemon, inspect.isfunction):
        if name.startswith("_") or name in RAW_DAEMON_REPLY_EXCEPTIONS:
            continue
        source = textwrap.dedent(inspect.getsource(method))
        tree = ast.parse(source)
        assigned_call_names: set[str] = set()
        contains_transport_call = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and _is_self_call(node.value):
                contains_transport_call = True
                assigned_call_names.update(target.id for target in node.targets if isinstance(target, ast.Name))
            elif isinstance(node, ast.AnnAssign) and _is_self_call(node.value):
                contains_transport_call = True
                if isinstance(node.target, ast.Name):
                    assigned_call_names.add(node.target.id)
            elif isinstance(node, ast.Expr) and _is_self_call(node.value):
                pytest.fail(f"{name} ignores raw daemon reply")
            elif isinstance(node, ast.Return):
                if _is_self_call(node.value):
                    pytest.fail(f"{name} returns raw daemon reply")
                if isinstance(node.value, ast.Name) and node.value.id in assigned_call_names:
                    pytest.fail(f"{name} returns raw daemon reply")
        if contains_transport_call:
            assert any(isinstance(node, ast.Return) and node.value is not None for node in ast.walk(tree)), name


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
            "quoted_message_json": '{"conversation":"Hi"}',
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
                "ReplyQuotedMessageJSON": '{"conversation":"Hi"}',
                "MentionedJIDs": ["sender-1"],
            },
        )
    ]


def test_daemon_boundary_normalizes_null_event_list() -> None:
    transport = FakeTransport({"Service.ListEvents": {"Events": None}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    reply = daemon.list_events(after_id=3, limit=4)

    assert reply.Events == []
    assert transport.calls == [("Service.ListEvents", {"AfterID": 3, "Limit": 4})]


def test_daemon_boundary_rejects_missing_event_list() -> None:
    transport = FakeTransport({"Service.ListEvents": {}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    with pytest.raises(BoundaryValidationError):
        daemon.list_events(after_id=3, limit=4)


def test_daemon_boundary_decodes_no_payload_replies() -> None:
    transport = FakeTransport(
        {
            "Service.Ping": "pong",
            "Service.GetVersion": {"GitCommit": "abc123"},
            "Service.GetSessionStatus": {"LoggedIn": True, "QRCode": "qr", "QRImage": "image"},
            "Service.GetContacts": {
                "Contacts": [
                    {
                        "jid": "contact-1@s.whatsapp.net",
                        "display_name": "Contact One",
                        "first_name": "",
                        "full_name": "Contact One",
                        "push_name": "",
                        "business_name": "",
                        "avatar_path": "",
                    }
                ]
            },
        }
    )
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    assert daemon.ping() == PingReply(Message="pong")
    assert daemon.get_version() == VersionReply(GitCommit="abc123")
    assert daemon.get_session_status() == SessionStatusReply(LoggedIn=True, QRCode="qr", QRImage="image")
    assert daemon.get_contacts().Contacts == [
        Contact(
            jid="contact-1@s.whatsapp.net",
            display_name="Contact One",
            first_name="",
            full_name="Contact One",
            push_name="",
            business_name="",
            avatar_path="",
        )
    ]
    assert transport.calls == [
        ("Service.Ping", {}),
        ("Service.GetVersion", {}),
        ("Service.GetSessionStatus", {}),
        ("Service.GetContacts", {}),
    ]


def test_daemon_client_factory_is_injectable() -> None:
    fake = object()
    set_daemon_client_factory(lambda: fake)
    try:
        assert daemon_client() is fake
    finally:
        set_daemon_client_factory(None)


def test_daemon_boundary_normalizes_null_group_list() -> None:
    transport = FakeTransport({"Service.GetGroups": {"Groups": None}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    reply = daemon.get_groups()

    assert reply.Groups == []
    assert transport.calls == [("Service.GetGroups", {})]


def test_daemon_boundary_decodes_group_participants_sync_avatar_settings_and_pair_phone() -> None:
    transport = FakeTransport(
        {
            "Service.GetGroupParticipants": {
                "Participants": [
                    {
                        "jid": "participant@s.whatsapp.net",
                        "phone_number_jid": "participant@s.whatsapp.net",
                        "lid_jid": "",
                        "display_name": "Participant",
                        "is_admin": True,
                        "is_super_admin": False,
                    }
                ]
            },
            "Service.SyncAvatar": {"AvatarPath": "/tmp/avatar.jpg"},
            "Service.GetChatSettings": {"MutedUntil": 12345},
            "Service.PairPhone": {"Code": "12345678"},
        }
    )
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    assert daemon.get_group_participants("group@g.us").Participants == [
        GroupParticipant(
            jid="participant@s.whatsapp.net",
            phone_number_jid="participant@s.whatsapp.net",
            lid_jid="",
            display_name="Participant",
            is_admin=True,
            is_super_admin=False,
        )
    ]
    assert daemon.sync_avatar("contact@s.whatsapp.net") == SyncAvatarReply(AvatarPath="/tmp/avatar.jpg")
    assert daemon.get_chat_settings("chat-1") == GetChatSettingsReply(MutedUntil=12345)
    assert daemon.pair_phone("15551234567") == PairPhoneReply(Code="12345678")
    assert transport.calls == [
        ("Service.GetGroupParticipants", {"ChatJID": "group@g.us"}),
        ("Service.SyncAvatar", {"JID": "contact@s.whatsapp.net"}),
        ("Service.GetChatSettings", {"ChatJID": "chat-1"}),
        ("Service.PairPhone", {"Phone": "15551234567"}),
    ]


def test_daemon_boundary_download_media_decodes_file_path() -> None:
    transport = FakeTransport({"Service.DownloadMedia": {"FilePath": "/tmp/media.webp"}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    reply = daemon.download_media(
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

    assert reply == DownloadMediaReply(FilePath="/tmp/media.webp")
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

    assert daemon.ensure_jid("lid-user@lid") == EnsureJIDReply(JID="15551234567@s.whatsapp.net")
    assert daemon.get_phone_number("lid-user@lid") == "+15551234567"
    assert transport.calls == [
        ("Service.EnsureJID", {"JID": "lid-user@lid"}),
        ("Service.EnsureJID", {"JID": "lid-user@lid"}),
    ]


def test_daemon_boundary_ensure_jid_preserves_explicit_empty_reply() -> None:
    transport = FakeTransport({"Service.EnsureJID": {"JID": ""}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    assert daemon.ensure_jid("lid-user@lid") == EnsureJIDReply(JID="")
    assert daemon.get_phone_number("lid-user@lid") == ""
    assert transport.calls == [
        ("Service.EnsureJID", {"JID": "lid-user@lid"}),
        ("Service.EnsureJID", {"JID": "lid-user@lid"}),
    ]


def test_daemon_boundary_edit_and_delete_message_decode_replies() -> None:
    transport = FakeTransport(
        {
            "Service.EditMessage": {"MessageID": "message-1", "Timestamp": 123},
            "Service.DeleteMessage": {"MessageID": "message-1", "Timestamp": 124},
        }
    )
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    assert daemon.edit_message("chat-1", "message-1", "edited") == EditMessageReply(
        MessageID="message-1", Timestamp=123
    )
    assert daemon.delete_message("chat-1", "message-1") == DeleteMessageReply(MessageID="message-1", Timestamp=124)
    assert transport.calls == [
        (
            "Service.EditMessage",
            {"ChatJID": "chat-1", "MessageID": "message-1", "Text": "edited"},
        ),
        ("Service.DeleteMessage", {"ChatJID": "chat-1", "MessageID": "message-1"}),
    ]


def test_daemon_boundary_empty_reply_commands_encode_expected_payloads() -> None:
    transport = FakeTransport({})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    replies = [
        daemon.delete_events(7),
        daemon.mark_read("chat-1", ["message-1"], sender_jid="sender-1"),
        daemon.send_presence(True),
        daemon.subscribe_presence("chat-1"),
        daemon.logout(),
        daemon.set_muted("chat-1", True),
        daemon.set_notification_counter(3, True),
        daemon.clear_chat_notifications(["chat-1"]),
    ]

    assert replies == [EmptyReply()] * 8
    assert transport.calls == [
        ("Service.DeleteEvents", {"UpToID": 7}),
        (
            "Service.MarkRead",
            {"ChatJID": "chat-1", "SenderJID": "sender-1", "MessageIDs": ["message-1"]},
        ),
        ("Service.SendPresence", {"Available": True}),
        ("Service.SubscribePresence", {"JID": "chat-1"}),
        ("Service.Logout", {}),
        ("Service.SetMuted", {"ChatJID": "chat-1", "Muted": True}),
        ("Service.SetNotificationCounter", {"Count": 3, "Visible": True}),
        ("Service.ClearChatNotifications", {"Tags": ["chat-1"]}),
    ]


def test_daemon_boundary_logs_invalid_typed_reply(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = FakeTransport({"Service.SendMessage": {"MessageID": "message-1", "Timestamp": "later"}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    with pytest.raises(BoundaryValidationError):
        daemon.send_message("chat-1", "text")

    assert "daemon_rpc contract=Service.SendMessage direction=decode validation failed" in caplog.text


def test_daemon_boundary_rejects_missing_send_message_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = FakeTransport({"Service.SendMessage": {"Timestamp": 123}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    with pytest.raises(BoundaryValidationError):
        daemon.send_message("chat-1", "text")

    assert "daemon_rpc contract=Service.SendMessage direction=decode validation failed" in caplog.text
    assert 'missing value for field "MessageID"' in caplog.text


def test_daemon_boundary_logs_invalid_scalar_reply(caplog: pytest.LogCaptureFixture) -> None:
    transport = FakeTransport({"Service.Ping": {"Message": "pong"}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    with pytest.raises(BoundaryValidationError):
        daemon.ping()

    assert "daemon_rpc contract=Service.Ping direction=decode validation failed" in caplog.text
    assert "Service.Ping reply requires a string message" in caplog.text


def test_daemon_boundary_logs_malformed_empty_reply(caplog: pytest.LogCaptureFixture) -> None:
    transport = FakeTransport({"Service.DeleteEvents": {"unexpected": "value"}})
    daemon = GreenlineDaemon(transport=transport)  # type: ignore[arg-type]

    assert daemon.delete_events(7) == EmptyReply()

    assert "daemon_rpc contract=Service.DeleteEvents direction=decode validation failed" in caplog.text
    assert "Service.DeleteEvents reply must be empty" in caplog.text
