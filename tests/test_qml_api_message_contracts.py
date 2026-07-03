from __future__ import annotations

import time

import pytest
from contracts.qml_registry import validate_api_response, validate_event_payload
from qml_contract_helpers import (
    DEFAULT_CHAT_ID,
    DEFAULT_GROUP_ID,
    DEFAULT_SENDER_ID,
    assert_formatted_message_fields,
    make_media_file,
    raw_downloadable_media,
    seed_chat,
    seed_message,
    seed_sender_identity,
)

import main
from greenline.contracts.kv import GreenlineKV
from greenline.contracts.validation import BoundaryValidationError
from greenline.store.mentions import template_mention_text
from greenline.store.records import (
    MessageReactionRecord,
    OwnJIDRecord,
    PendingOutboxRecord,
    StickerCacheRecord,
    StoredMessageRecord,
)
from greenline.store.repository import message_storage_key
from models import MentionSpan, MessageType, ReadReceipt


def _event_payloads(fake_pyotherside, name: str) -> list[object]:
    return [payload for event_name, payload in fake_pyotherside.sent if event_name == name]


def _assert_all_contract_events(fake_pyotherside) -> None:
    for event_name, payload in fake_pyotherside.sent:
        validate_event_payload(event_name, payload)


def _start_dispatcher() -> None:
    main.start_event_loop()


def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_get_messages_contract_pagination_and_sender_reply_fields() -> None:
    seed_sender_identity(DEFAULT_SENDER_ID, name="Alice", photo="file:///tmp/alice.jpg")
    seed_chat(DEFAULT_CHAT_ID)
    seed_message(DEFAULT_CHAT_ID, "reply-1", is_outgoing=True, text="Original", timestamp_unix=1)
    seed_message(
        DEFAULT_CHAT_ID,
        "message-1",
        is_outgoing=False,
        text="Incoming",
        timestamp_unix=2,
    )
    seed_message(DEFAULT_CHAT_ID, "message-2", is_outgoing=False, text="Next", timestamp_unix=3, has_reactions=True)

    first_page = main.get_messages(DEFAULT_CHAT_ID, "", 1)

    validate_api_response("get_messages", first_page)
    assert first_page["has_more"] is True
    assert first_page["next_cursor"]
    message = first_page["messages"][0]
    assert_formatted_message_fields(message)
    assert message["sender_name"] == "Alice"
    assert message["sender_photo"] == "file:///tmp/alice.jpg"
    assert message["reply_to_sender"] == "Alice"
    assert message["formatted_text"] == "Next"
    assert message["formatted_reply_to_text"] == "Reply preview"
    assert message["has_reactions"] is True

    second_page = main.get_messages(DEFAULT_CHAT_ID, first_page["next_cursor"], 10)
    validate_api_response("get_messages", second_page)


def test_get_message_reactions_contract_resolves_sender_details() -> None:
    seed_sender_identity(DEFAULT_SENDER_ID, name="Alice", photo="file:///tmp/alice.jpg")
    with GreenlineKV() as kv:
        kv.put_record(
            f"message_reaction:{DEFAULT_CHAT_ID}:message-1:{DEFAULT_SENDER_ID}",
            MessageReactionRecord(
                chat_id=DEFAULT_CHAT_ID,
                message_id="message-1",
                sender_jid=DEFAULT_SENDER_ID,
                emoji="👍",
            ),
        )

    result = main.get_message_reactions(DEFAULT_CHAT_ID, "message-1")

    validate_api_response("get_message_reactions", result)
    assert result == {
        "success": True,
        "reactions": [
            {
                "jid": DEFAULT_SENDER_ID,
                "name": "Alice",
                "photo": "file:///tmp/alice.jpg",
                "emoji": "👍",
                "is_self": False,
            }
        ],
        "message": "",
    }


def test_get_messages_backfills_missing_text_render_fields() -> None:
    seed_chat(DEFAULT_CHAT_ID)
    record = StoredMessageRecord(
        id="legacy-message",
        chat_id=DEFAULT_CHAT_ID,
        type=MessageType.TEXT,
        is_outgoing=False,
        timestamp="12:34",
        timestamp_unix=123,
        read_receipt=ReadReceipt.DELIVERED,
        sender=DEFAULT_SENDER_ID,
        sender_raw=DEFAULT_SENDER_ID,
        text="Hello *bold* world",
        rendered_text="",
        rendered_formatted_text="",
        text_render_mode="simple",
        reply_to_id="",
    )
    key = message_storage_key(DEFAULT_CHAT_ID, 123, "legacy-message")
    with GreenlineKV() as kv:
        kv.put_record(key, record)

    result = main.get_messages(DEFAULT_CHAT_ID, "", 10)

    validate_api_response("get_messages", result)
    assert result["messages"][0]["formatted_text"] == "Hello <b>bold</b> world"
    assert result["messages"][0]["text_render_mode"] == "rich"
    with GreenlineKV() as kv:
        updated = kv.get_record(key)
    assert isinstance(updated, StoredMessageRecord)
    assert updated.rendered_text == "Hello *bold* world"
    assert updated.rendered_formatted_text == "Hello <b>bold</b> world"
    assert updated.text_render_mode == "rich"


def test_get_messages_preserves_cached_simple_list_messages() -> None:
    seed_chat(DEFAULT_CHAT_ID)
    record = StoredMessageRecord(
        id="list-message",
        chat_id=DEFAULT_CHAT_ID,
        type=MessageType.TEXT,
        is_outgoing=False,
        timestamp="12:34",
        timestamp_unix=124,
        read_receipt=ReadReceipt.DELIVERED,
        sender=DEFAULT_SENDER_ID,
        sender_raw=DEFAULT_SENDER_ID,
        text="- first\n- second",
        rendered_text="- first\n- second",
        rendered_formatted_text="- first<br/>- second",
        text_render_mode="simple",
        reply_to_id="",
    )
    key = message_storage_key(DEFAULT_CHAT_ID, 124, "list-message")
    with GreenlineKV() as kv:
        kv.put_record(key, record)

    result = main.get_messages(DEFAULT_CHAT_ID, "", 10)

    validate_api_response("get_messages", result)
    assert result["messages"][0]["formatted_text"] == "- first<br/>- second"
    assert result["messages"][0]["text_render_mode"] == "simple"
    with GreenlineKV() as kv:
        updated = kv.get_record(key)
    assert isinstance(updated, StoredMessageRecord)
    assert updated.rendered_text == "- first\n- second"
    assert updated.rendered_formatted_text == "- first<br/>- second"
    assert updated.text_render_mode == "simple"


def test_get_messages_preserves_cached_rich_list_messages() -> None:
    seed_chat(DEFAULT_CHAT_ID)
    record = StoredMessageRecord(
        id="rich-list-message",
        chat_id=DEFAULT_CHAT_ID,
        type=MessageType.TEXT,
        is_outgoing=False,
        timestamp="12:35",
        timestamp_unix=125,
        read_receipt=ReadReceipt.DELIVERED,
        sender=DEFAULT_SENDER_ID,
        sender_raw=DEFAULT_SENDER_ID,
        text="* *bold* https://example.com",
        rendered_text="* *bold* https://example.com",
        rendered_formatted_text='* <b>bold</b> <a href="https://example.com">https://example.com</a>',
        text_render_mode="rich",
        reply_to_id="",
    )
    key = message_storage_key(DEFAULT_CHAT_ID, 125, "rich-list-message")
    with GreenlineKV() as kv:
        kv.put_record(key, record)

    result = main.get_messages(DEFAULT_CHAT_ID, "", 10)

    validate_api_response("get_messages", result)
    assert result["messages"][0]["formatted_text"] == (
        '* <b>bold</b> <a href="https://example.com">https://example.com</a>'
    )
    assert result["messages"][0]["text_render_mode"] == "rich"
    with GreenlineKV() as kv:
        updated = kv.get_record(key)
    assert isinstance(updated, StoredMessageRecord)
    assert updated.rendered_text == "* *bold* https://example.com"
    assert updated.rendered_formatted_text == ('* <b>bold</b> <a href="https://example.com">https://example.com</a>')
    assert updated.text_render_mode == "rich"


def test_get_messages_preserves_cached_list_formatting_when_only_plain_cache_is_missing() -> None:
    seed_chat(DEFAULT_CHAT_ID)
    record = StoredMessageRecord(
        id="partial-list-message",
        chat_id=DEFAULT_CHAT_ID,
        type=MessageType.TEXT,
        is_outgoing=False,
        timestamp="12:36",
        timestamp_unix=126,
        read_receipt=ReadReceipt.DELIVERED,
        sender=DEFAULT_SENDER_ID,
        sender_raw=DEFAULT_SENDER_ID,
        text="- first\n- second",
        rendered_text="",
        rendered_formatted_text="- first<br/>- second",
        text_render_mode="simple",
        reply_to_id="",
    )
    key = message_storage_key(DEFAULT_CHAT_ID, 126, "partial-list-message")
    with GreenlineKV() as kv:
        kv.put_record(key, record)

    result = main.get_messages(DEFAULT_CHAT_ID, "", 10)

    validate_api_response("get_messages", result)
    assert result["messages"][0]["text"] == "- first\n- second"
    assert result["messages"][0]["formatted_text"] == "- first<br/>- second"
    assert result["messages"][0]["text_render_mode"] == "simple"
    with GreenlineKV() as kv:
        updated = kv.get_record(key)
    assert isinstance(updated, StoredMessageRecord)
    assert updated.rendered_text == "- first\n- second"
    assert updated.rendered_formatted_text == "- first<br/>- second"
    assert updated.text_render_mode == "simple"


def test_get_messages_preserves_cached_mention_rendering() -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_sender_identity(DEFAULT_SENDER_ID, name="Alice")
    templated_text, mentioned_jids = template_mention_text("Hello @222", [DEFAULT_SENDER_ID])
    record = StoredMessageRecord(
        id="mention-message",
        chat_id=DEFAULT_CHAT_ID,
        type=MessageType.TEXT,
        is_outgoing=False,
        timestamp="12:34",
        timestamp_unix=124,
        read_receipt=ReadReceipt.DELIVERED,
        sender=DEFAULT_SENDER_ID,
        sender_raw=DEFAULT_SENDER_ID,
        text=templated_text,
        mentioned_jids=mentioned_jids,
        rendered_text="Hello @Alice",
        rendered_formatted_text='Hello <a href="greenline://chat/222%40s.whatsapp.net">@Alice</a>',
        text_render_mode="rich",
        reply_to_id="",
    )
    key = message_storage_key(DEFAULT_CHAT_ID, 124, "mention-message")
    with GreenlineKV() as kv:
        kv.put_record(key, record)
    seed_sender_identity(DEFAULT_SENDER_ID, name="Bob")

    result = main.get_messages(DEFAULT_CHAT_ID, "", 10)

    validate_api_response("get_messages", result)
    assert result["messages"][0]["text"] == "Hello @Alice"
    assert result["messages"][0]["formatted_text"] == 'Hello <a href="greenline://chat/222%40s.whatsapp.net">@Alice</a>'
    with GreenlineKV() as kv:
        updated = kv.get_record(key)
    assert isinstance(updated, StoredMessageRecord)
    assert updated.rendered_text == "Hello @Alice"
    assert updated.rendered_formatted_text == 'Hello <a href="greenline://chat/222%40s.whatsapp.net">@Alice</a>'


def test_get_messages_renders_plain_text_mentions_from_spans_as_rich_links() -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_sender_identity(DEFAULT_SENDER_ID, name="Empório Minatto")
    record = StoredMessageRecord(
        id="mention-span-message",
        chat_id=DEFAULT_CHAT_ID,
        type=MessageType.TEXT,
        is_outgoing=True,
        timestamp="02:40",
        timestamp_unix=124,
        read_receipt=ReadReceipt.READ,
        text="@Empório Minatto ",
        mentioned_jids=[DEFAULT_SENDER_ID],
        mention_spans=[MentionSpan(DEFAULT_SENDER_ID, "Empório Minatto", 0, 16)],
        rendered_text="",
        rendered_formatted_text="",
        text_render_mode="rich",
        reply_to_id="",
        temp_id="pending-mention-span-1",
    )
    key = message_storage_key(DEFAULT_CHAT_ID, 124, "mention-span-message")
    with GreenlineKV() as kv:
        kv.put_record(key, record)

    result = main.get_messages(DEFAULT_CHAT_ID, "", 10)

    validate_api_response("get_messages", result)
    assert result["messages"][0]["text"] == "@Empório Minatto "
    assert result["messages"][0]["formatted_text"] == (
        '<a href="greenline://chat/222%40s.whatsapp.net">@Empório Minatto</a> '
    )
    assert result["messages"][0]["text_render_mode"] == "rich"


def test_get_messages_preserves_cached_mention_span_rendering() -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_sender_identity(DEFAULT_SENDER_ID, name="Empório Minatto")
    record = StoredMessageRecord(
        id="mention-span-stale-cache-message",
        chat_id=DEFAULT_CHAT_ID,
        type=MessageType.TEXT,
        is_outgoing=True,
        timestamp="02:41",
        timestamp_unix=125,
        read_receipt=ReadReceipt.READ,
        text="@Empório Minatto ",
        mentioned_jids=[],
        mention_spans=[MentionSpan(DEFAULT_SENDER_ID, "Empório Minatto", 0, 16)],
        rendered_text="@Empório Minatto ",
        rendered_formatted_text="@Empório Minatto ",
        text_render_mode="simple",
        reply_to_id="",
        temp_id="pending-mention-span-2",
    )
    key = message_storage_key(DEFAULT_CHAT_ID, 125, "mention-span-stale-cache-message")
    with GreenlineKV() as kv:
        kv.put_record(key, record)

    result = main.get_messages(DEFAULT_CHAT_ID, "", 10)

    validate_api_response("get_messages", result)
    assert result["messages"][0]["text"] == "@Empório Minatto "
    assert result["messages"][0]["formatted_text"] == "@Empório Minatto "
    assert result["messages"][0]["text_render_mode"] == "simple"
    with GreenlineKV() as kv:
        updated = kv.get_record(key)
    assert isinstance(updated, StoredMessageRecord)
    assert updated.rendered_text == "@Empório Minatto "
    assert updated.rendered_formatted_text == "@Empório Minatto "
    assert updated.text_render_mode == "simple"


def test_get_message_reactions_contract_prefers_push_name_for_self() -> None:
    own_jid = "5519974236541@s.whatsapp.net"
    seed_chat(
        own_jid,
        name="+55 19 97423-6541",
        full_name="+55 19 97423-6541",
        push_name="Brenno Flávio",
        business_name="",
        unread_count=0,
        muted=False,
    )
    with GreenlineKV() as kv:
        kv.put_record("self.jid", OwnJIDRecord(own_jid))
        kv.put_record(
            f"message_reaction:{DEFAULT_CHAT_ID}:message-1:{own_jid}",
            MessageReactionRecord(
                chat_id=DEFAULT_CHAT_ID,
                message_id="message-1",
                sender_jid=own_jid,
                emoji="👍",
            ),
        )

    result = main.get_message_reactions(DEFAULT_CHAT_ID, "message-1")

    validate_api_response("get_message_reactions", result)
    assert result == {
        "success": True,
        "reactions": [
            {
                "jid": own_jid,
                "name": "Brenno Flávio",
                "photo": "file:///tmp/chat.jpg",
                "emoji": "👍",
                "is_self": True,
            }
        ],
        "message": "",
    }


def test_send_message_reaction_contract_adds_reaction_and_emits_update(
    fake_daemon_rpc,
    fake_pyotherside_module,
) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_sender_identity(DEFAULT_SENDER_ID, name="Alice", photo="file:///tmp/alice.jpg")
    seed_message(DEFAULT_CHAT_ID, "incoming-1", is_outgoing=False, reply_to_id="")

    result = main.send_message_reaction(DEFAULT_CHAT_ID, "incoming-1", "👍")

    validate_api_response("send_message_reaction", result)
    assert fake_daemon_rpc.send_reaction_calls == [
        {
            "chat_id": DEFAULT_CHAT_ID,
            "message_id": "incoming-1",
            "reaction": "👍",
            "sender_jid": DEFAULT_SENDER_ID,
        }
    ]
    with GreenlineKV() as kv:
        reaction = kv.get_record(
            f"message_reaction:{DEFAULT_CHAT_ID}:incoming-1:{fake_daemon_rpc.send_reaction_result.OwnJID}"
        )
        own_jid = kv.get_record("self.jid")
        indexed_key = kv.get_record(f"message_index:{DEFAULT_CHAT_ID}:incoming-1")
        stored_message = kv.get_record(indexed_key.value)
    assert isinstance(reaction, MessageReactionRecord)
    assert isinstance(stored_message, StoredMessageRecord)
    assert own_jid.value == fake_daemon_rpc.send_reaction_result.OwnJID
    assert reaction.emoji == "👍"
    assert stored_message.has_reactions is True
    reactions = main.get_message_reactions(DEFAULT_CHAT_ID, "incoming-1")
    validate_api_response("get_message_reactions", reactions)
    assert reactions["reactions"][0]["is_self"] is True
    _assert_all_contract_events(fake_pyotherside_module)
    message_updates = _event_payloads(fake_pyotherside_module, "message-upsert")
    reaction_updates = _event_payloads(fake_pyotherside_module, "message-reaction-update")
    assert message_updates[-1][0]["id"] == "incoming-1"
    assert message_updates[-1][0]["has_reactions"] is True
    assert reaction_updates[-1][0] == {
        "chat_id": DEFAULT_CHAT_ID,
        "message_id": "incoming-1",
        "jid": fake_daemon_rpc.send_reaction_result.OwnJID,
        "name": "me",
        "photo": "",
        "emoji": "👍",
        "is_self": True,
        "removed": False,
    }


def test_send_message_reaction_contract_falls_back_to_chat_id_for_direct_history_messages(
    fake_daemon_rpc,
    fake_pyotherside_module,
) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_message(DEFAULT_CHAT_ID, "history-1", is_outgoing=False, sender="", sender_raw="", reply_to_id="")

    result = main.send_message_reaction(DEFAULT_CHAT_ID, "history-1", "❤️")

    validate_api_response("send_message_reaction", result)
    assert result == {"success": True, "message": ""}
    assert fake_daemon_rpc.send_reaction_calls == [
        {
            "chat_id": DEFAULT_CHAT_ID,
            "message_id": "history-1",
            "reaction": "❤️",
            "sender_jid": DEFAULT_CHAT_ID,
        }
    ]
    _assert_all_contract_events(fake_pyotherside_module)


def test_send_message_reaction_contract_removes_reaction_and_handles_outgoing_target(
    fake_daemon_rpc,
    fake_pyotherside_module,
) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_message(DEFAULT_CHAT_ID, "outgoing-1", is_outgoing=True, has_reactions=True, reply_to_id="")
    with GreenlineKV() as kv:
        kv.put_record(
            f"message_reaction:{DEFAULT_CHAT_ID}:outgoing-1:{fake_daemon_rpc.send_reaction_result.OwnJID}",
            MessageReactionRecord(
                chat_id=DEFAULT_CHAT_ID,
                message_id="outgoing-1",
                sender_jid=fake_daemon_rpc.send_reaction_result.OwnJID,
                emoji="👍",
            ),
        )

    result = main.send_message_reaction(DEFAULT_CHAT_ID, "outgoing-1", "")

    validate_api_response("send_message_reaction", result)
    assert fake_daemon_rpc.send_reaction_calls == [
        {
            "chat_id": DEFAULT_CHAT_ID,
            "message_id": "outgoing-1",
            "reaction": "",
            "sender_jid": "",
        }
    ]
    with GreenlineKV() as kv:
        reaction = kv.get_record(
            f"message_reaction:{DEFAULT_CHAT_ID}:outgoing-1:{fake_daemon_rpc.send_reaction_result.OwnJID}"
        )
        indexed_key = kv.get_record(f"message_index:{DEFAULT_CHAT_ID}:outgoing-1")
        stored_message = kv.get_record(indexed_key.value)
    assert reaction is None
    assert isinstance(stored_message, StoredMessageRecord)
    assert stored_message.has_reactions is False
    _assert_all_contract_events(fake_pyotherside_module)
    message_updates = _event_payloads(fake_pyotherside_module, "message-upsert")
    reaction_updates = _event_payloads(fake_pyotherside_module, "message-reaction-update")
    assert message_updates[-1][0]["id"] == "outgoing-1"
    assert message_updates[-1][0]["has_reactions"] is False
    assert reaction_updates[-1][0] == {
        "chat_id": DEFAULT_CHAT_ID,
        "message_id": "outgoing-1",
        "jid": fake_daemon_rpc.send_reaction_result.OwnJID,
        "name": "me",
        "photo": "",
        "emoji": "",
        "is_self": True,
        "removed": True,
    }


@pytest.mark.parametrize(
    ("message_id", "seed_kwargs", "expected_message"),
    [
        ("missing", None, "Message not found"),
        (
            "pending-1",
            {"is_outgoing": True, "send_status": "pending", "temp_id": "pending-1"},
            "Message has not been sent yet",
        ),
        (
            "failed-1",
            {"is_outgoing": True, "send_status": "failed", "temp_id": "failed-1"},
            "Message has not been sent yet",
        ),
        ("deleted-1", {"is_outgoing": True, "message_type": MessageType.DELETED}, "Message already deleted"),
    ],
)
def test_send_message_reaction_contract_rejects_invalid_targets(
    message_id,
    seed_kwargs,
    expected_message,
    fake_daemon_rpc,
    fake_pyotherside_module,
) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    if seed_kwargs is not None:
        seed_message(DEFAULT_CHAT_ID, message_id, reply_to_id="", **seed_kwargs)

    result = main.send_message_reaction(DEFAULT_CHAT_ID, message_id, "👍")

    validate_api_response("send_message_reaction", result)
    assert result == {"success": False, "message": expected_message}
    assert fake_daemon_rpc.send_reaction_calls == []
    assert _event_payloads(fake_pyotherside_module, "message-upsert") == []


def test_send_message_reaction_contract_returns_daemon_errors(
    fake_daemon_rpc,
    fake_pyotherside_module,
) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_message(DEFAULT_CHAT_ID, "incoming-error", is_outgoing=False, reply_to_id="")
    fake_daemon_rpc.send_reaction_exception = RuntimeError("send failed")

    result = main.send_message_reaction(DEFAULT_CHAT_ID, "incoming-error", "👍")

    validate_api_response("send_message_reaction", result)
    assert result == {"success": False, "message": "send failed"}
    assert fake_daemon_rpc.send_reaction_calls == [
        {
            "chat_id": DEFAULT_CHAT_ID,
            "message_id": "incoming-error",
            "reaction": "👍",
            "sender_jid": DEFAULT_SENDER_ID,
        }
    ]
    assert _event_payloads(fake_pyotherside_module, "message-upsert") == []


def test_mark_messages_as_read_contract_and_chat_emit(fake_daemon_rpc, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID, unread_count=2, first_unread_message_id="incoming-1")
    seed_message(
        DEFAULT_CHAT_ID,
        "incoming-1",
        is_outgoing=False,
        read_receipt=ReadReceipt.NONE,
        timestamp_unix=1,
    )
    seed_message(
        DEFAULT_CHAT_ID,
        "incoming-2",
        is_outgoing=False,
        read_receipt=ReadReceipt.NONE,
        timestamp_unix=2,
    )

    result = main.mark_messages_as_read(DEFAULT_CHAT_ID)

    validate_api_response("mark_messages_as_read", result)
    assert fake_daemon_rpc.mark_read_calls
    _assert_all_contract_events(fake_pyotherside_module)
    chat_updates = _event_payloads(fake_pyotherside_module, "chat-list-update")
    assert chat_updates[-1][0]["unread_count"] == 0
    assert chat_updates[-1][0]["first_unread_message_id"] == ""

    with GreenlineKV() as kv:
        first = kv.get_record(f"message:{DEFAULT_CHAT_ID}:1:incoming-1")
        second = kv.get_record(f"message:{DEFAULT_CHAT_ID}:2:incoming-2")

    assert first is not None
    assert second is not None
    assert first.read_receipt == ReadReceipt.READ
    assert second.read_receipt == ReadReceipt.READ


def test_mark_messages_as_read_ignores_daemon_failures(fake_daemon_rpc, fake_pyotherside_module, monkeypatch) -> None:
    seed_chat(DEFAULT_CHAT_ID, unread_count=2, first_unread_message_id="incoming-1")
    seed_message(
        DEFAULT_CHAT_ID,
        "incoming-1",
        is_outgoing=False,
        read_receipt=ReadReceipt.NONE,
        timestamp_unix=1,
    )
    seed_message(
        DEFAULT_CHAT_ID,
        "incoming-2",
        is_outgoing=False,
        read_receipt=ReadReceipt.NONE,
        timestamp_unix=2,
    )

    def fail_mark_read(self, chat_id: str, message_ids: list[str], sender_jid: str = ""):
        raise RuntimeError("websocket not connected")

    monkeypatch.setattr(fake_daemon_rpc, "mark_read", fail_mark_read)

    result = main.mark_messages_as_read(DEFAULT_CHAT_ID)

    validate_api_response("mark_messages_as_read", result)
    assert result == {"success": True, "message": ""}
    _assert_all_contract_events(fake_pyotherside_module)
    chat_updates = _event_payloads(fake_pyotherside_module, "chat-list-update")
    assert chat_updates[-1][0]["unread_count"] == 0
    assert chat_updates[-1][0]["first_unread_message_id"] == ""
    assert fake_daemon_rpc.clear_chat_notifications_calls[-1] == [DEFAULT_CHAT_ID]
    assert fake_daemon_rpc.set_notification_counter_calls[-1] == {"count": 0, "visible": False}

    with GreenlineKV() as kv:
        chat = kv.get_record(f"chat:{DEFAULT_CHAT_ID}")

    assert chat is not None
    assert chat.unread_count == 0
    assert chat.first_unread_message_id == ""


def test_send_text_message_contract_and_pending_outbox_emits(fake_daemon_rpc, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_sender_identity(DEFAULT_SENDER_ID)
    _start_dispatcher()

    result = main.send_text_message(DEFAULT_CHAT_ID, "Hello", "pending-text-1")

    validate_api_response("send_text_message", result)
    _wait_for(lambda: len(fake_daemon_rpc.send_message_calls) >= 1)
    _wait_for(
        lambda: any(
            payload[0]["id"] == "sent-message"
            for payload in _event_payloads(fake_pyotherside_module, "message-upsert")
            if payload
        )
    )
    assert fake_daemon_rpc.send_message_calls[0]["message_type"] == "text"
    _assert_all_contract_events(fake_pyotherside_module)
    message_updates = _event_payloads(fake_pyotherside_module, "message-upsert")
    assert message_updates[0][0]["id"] == "pending-text-1"
    assert message_updates[-1][0]["temp_id"] == "pending-text-1"
    assert message_updates[-1][0]["id"] == "sent-message"


def test_send_text_message_reply_to_own_group_message_preserves_stored_sender_participant(
    fake_daemon_rpc,
    fake_pyotherside_module,
) -> None:
    seed_chat(DEFAULT_GROUP_ID)
    seed_message(
        DEFAULT_GROUP_ID,
        "own-group-message",
        is_outgoing=True,
        text="Original",
        timestamp_unix=1_700_000_001,
        reply_to_id="",
    )
    with GreenlineKV() as kv:
        indexed_key = kv.get_record(f"message_index:{DEFAULT_GROUP_ID}:own-group-message")
        stored_message = kv.get_record(indexed_key.value)
        stored_message.sender = "self@s.whatsapp.net"
        stored_message.sender_raw = "self@lid"
        kv.put_record(indexed_key.value, stored_message)
    _start_dispatcher()

    result = main.send_text_message(
        DEFAULT_GROUP_ID,
        "Reply",
        "pending-self-reply",
        {"id": "own-group-message", "sender": "You", "text": "Original", "participant": ""},
    )

    validate_api_response("send_text_message", result)
    _wait_for(lambda: len(fake_daemon_rpc.send_message_calls) >= 1)
    reply_context = fake_daemon_rpc.send_message_calls[0]["reply_context"]
    assert reply_context["id"] == "own-group-message"
    assert reply_context["participant"] == "self@lid"
    assert reply_context["participant_raw"] == "self@lid"
    assert reply_context["participant_canonical"] == "self@s.whatsapp.net"
    assert reply_context["from_me"] is True
    _assert_all_contract_events(fake_pyotherside_module)


def test_send_text_message_boundary_failure_remains_pending(fake_daemon_rpc, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_sender_identity(DEFAULT_SENDER_ID)
    fake_daemon_rpc.send_message_exception = BoundaryValidationError("bad daemon reply")
    _start_dispatcher()

    result = main.send_text_message(DEFAULT_CHAT_ID, "Hello", "pending-boundary-1")

    validate_api_response("send_text_message", result)
    assert result["success"] is True

    def pending_attempt_recorded() -> bool:
        with GreenlineKV() as kv:
            outbox_entry = kv.get_record(f"pending-outbox:{DEFAULT_CHAT_ID}:pending-boundary-1")
        return isinstance(outbox_entry, PendingOutboxRecord) and outbox_entry.attempt_count >= 1

    _wait_for(pending_attempt_recorded)

    with GreenlineKV() as kv:
        outbox_entry = kv.get_record(f"pending-outbox:{DEFAULT_CHAT_ID}:pending-boundary-1")
        indexed_key = kv.get_record(f"message_index:{DEFAULT_CHAT_ID}:pending-boundary-1")
        stored_message = kv.get_record(indexed_key.value)
    assert isinstance(outbox_entry, PendingOutboxRecord)
    assert isinstance(stored_message, StoredMessageRecord)
    assert outbox_entry.attempt_count >= 1
    assert outbox_entry.next_attempt_at >= int(time.time())
    assert stored_message.send_status == "pending"
    _assert_all_contract_events(fake_pyotherside_module)


def test_send_location_message_contract_and_pending_outbox_emits(fake_daemon_rpc, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_sender_identity(DEFAULT_SENDER_ID)
    _start_dispatcher()

    result = main.send_location_message(DEFAULT_CHAT_ID, 12.345, -67.89, "pending-location-1", None)

    validate_api_response("send_location_message", result)
    _wait_for(lambda: len(fake_daemon_rpc.send_message_calls) >= 1)
    _wait_for(
        lambda: any(
            payload[0]["id"] == "sent-message"
            for payload in _event_payloads(fake_pyotherside_module, "message-upsert")
            if payload
        )
    )
    location_call = fake_daemon_rpc.send_message_calls[0]
    assert location_call["message_type"] == "location"
    assert location_call["latitude"] == 12.345
    assert location_call["longitude"] == -67.89
    _assert_all_contract_events(fake_pyotherside_module)
    message_updates = _event_payloads(fake_pyotherside_module, "message-upsert")
    assert message_updates[0][0]["id"] == "pending-location-1"
    assert message_updates[0][0]["type"] == "location"
    assert message_updates[0][0]["text"] == "12.345, -67.89"
    assert message_updates[0][0]["caption"] == ""
    assert message_updates[0][0]["link_url"] == "geo:12.345,-67.89"
    assert message_updates[-1][0]["temp_id"] == "pending-location-1"
    assert message_updates[-1][0]["id"] == "sent-message"


def test_send_location_message_boundary_failure_remains_pending(fake_daemon_rpc, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_sender_identity(DEFAULT_SENDER_ID)
    fake_daemon_rpc.send_message_exception = BoundaryValidationError("bad daemon reply")
    _start_dispatcher()

    result = main.send_location_message(DEFAULT_CHAT_ID, 10.0, 20.0, "pending-location-failure", None)

    validate_api_response("send_location_message", result)
    assert result["success"] is True

    def pending_attempt_recorded() -> bool:
        with GreenlineKV() as kv:
            outbox_entry = kv.get_record(f"pending-outbox:{DEFAULT_CHAT_ID}:pending-location-failure")
        return isinstance(outbox_entry, PendingOutboxRecord) and outbox_entry.attempt_count >= 1

    _wait_for(pending_attempt_recorded)

    with GreenlineKV() as kv:
        outbox_entry = kv.get_record(f"pending-outbox:{DEFAULT_CHAT_ID}:pending-location-failure")
        indexed_key = kv.get_record(f"message_index:{DEFAULT_CHAT_ID}:pending-location-failure")
        stored_message = kv.get_record(indexed_key.value)
    assert isinstance(outbox_entry, PendingOutboxRecord)
    assert isinstance(stored_message, StoredMessageRecord)
    assert outbox_entry.attempt_count >= 1
    assert outbox_entry.next_attempt_at >= int(time.time())
    assert stored_message.type == MessageType.LOCATION
    assert stored_message.text == "10.0, 20.0"
    assert stored_message.link_url == "geo:10.0,20.0"
    assert stored_message.send_status == "pending"
    _assert_all_contract_events(fake_pyotherside_module)


def test_send_location_message_rejects_invalid_coordinates() -> None:
    result = main.send_location_message(DEFAULT_CHAT_ID, 91.0, 20.0, "pending-location-invalid", None)

    validate_api_response("send_location_message", result)
    assert result == {"success": False, "message": "Invalid location coordinates"}


def test_send_media_message_contracts(tmp_path, fake_daemon_rpc, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    _start_dispatcher()
    media_cases = [
        (
            "send_image_message",
            main.send_image_message,
            "image.jpg",
            [DEFAULT_CHAT_ID, "", "", "temp-image", None],
        ),
        (
            "send_video_message",
            main.send_video_message,
            "video.mp4",
            [DEFAULT_CHAT_ID, "", "", "temp-video", None],
        ),
        (
            "send_document_message",
            main.send_document_message,
            "document.pdf",
            [DEFAULT_CHAT_ID, "", "", "temp-document", None],
        ),
        (
            "send_sticker_message",
            main.send_sticker_message,
            "sticker.webp",
            [DEFAULT_CHAT_ID, "", "temp-sticker", None],
        ),
        (
            "send_contact_message",
            main.send_contact_message,
            "contact.vcf",
            [DEFAULT_CHAT_ID, "", "temp-contact", None],
        ),
    ]
    for api_name, function, file_name, args in media_cases:
        if file_name.endswith(".vcf"):
            path = make_media_file(tmp_path, file_name, b"BEGIN:VCARD\nFN:Tester\nEND:VCARD\n")
        else:
            path = make_media_file(tmp_path, file_name)
        args[1] = path
        result = function(*args)
        validate_api_response(api_name, result)

    _wait_for(lambda: len(fake_daemon_rpc.send_message_calls) == 5)

    assert sorted(call["message_type"] for call in fake_daemon_rpc.send_message_calls) == [
        "contact",
        "document",
        "image",
        "sticker",
        "video",
    ]
    document_call = next(call for call in fake_daemon_rpc.send_message_calls if call["message_type"] == "document")
    assert document_call["file_name"] == "document.pdf"
    assert document_call["caption"] == ""

    _assert_all_contract_events(fake_pyotherside_module)
    message_updates = _event_payloads(fake_pyotherside_module, "message-upsert")
    assert any(update[0]["file_name"] == "document.pdf" for update in message_updates if update)


def test_send_audio_message_success_and_move_failure_contracts(tmp_path, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    _start_dispatcher()
    audio_path = make_media_file(tmp_path, "audio.ogg")

    success = main.send_audio_message(DEFAULT_CHAT_ID, audio_path, 7, "temp-audio", None)
    validate_api_response("send_audio_message", success)

    failure = main.send_audio_message(DEFAULT_CHAT_ID, str(tmp_path / "missing.ogg"), 7, "failed-audio", None)
    validate_api_response("send_audio_message", failure)
    assert failure["success"] is False
    _assert_all_contract_events(fake_pyotherside_module)
    message_updates = _event_payloads(fake_pyotherside_module, "message-upsert")
    assert message_updates[-1][0]["send_status"] == "failed"


def test_send_document_message_copy_failure_contracts(tmp_path, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID)

    failure = main.send_document_message(DEFAULT_CHAT_ID, str(tmp_path / "missing.pdf"), "", "failed-document", None)

    validate_api_response("send_document_message", failure)
    assert failure["success"] is False
    _assert_all_contract_events(fake_pyotherside_module)
    message_updates = _event_payloads(fake_pyotherside_module, "message-upsert")
    assert message_updates[-1][0]["send_status"] == "failed"
    assert message_updates[-1][0]["file_name"] == "missing.pdf"


def test_edit_text_message_contract_success_and_failure(fake_daemon_rpc, fake_pyotherside_module) -> None:
    now = int(time.time())
    seed_chat(DEFAULT_CHAT_ID)
    seed_message(
        DEFAULT_CHAT_ID,
        "editable",
        is_outgoing=True,
        read_receipt=ReadReceipt.SENT,
        timestamp_unix=now,
        text="Before",
        reply_to_id="",
    )

    success = main.edit_text_message(DEFAULT_CHAT_ID, "editable", "After")

    validate_api_response("edit_text_message", success)
    assert fake_daemon_rpc.edit_message_calls[0]["text"] == "After"
    _assert_all_contract_events(fake_pyotherside_module)
    message_updates = _event_payloads(fake_pyotherside_module, "message-upsert")
    assert message_updates[-1][0]["text"] == "After"
    assert message_updates[-1][0]["formatted_text"] == "After"
    assert message_updates[-1][0]["text_render_mode"] == "simple"

    missing = main.edit_text_message(DEFAULT_CHAT_ID, "missing", "After")
    validate_api_response("edit_text_message", missing)
    assert missing["success"] is False


def test_delete_message_contract_success_and_failure(fake_daemon_rpc, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_message(
        DEFAULT_CHAT_ID,
        "deletable",
        is_outgoing=True,
        read_receipt=ReadReceipt.SENT,
        reply_to_id="",
    )

    success = main.delete_message(DEFAULT_CHAT_ID, "deletable")

    validate_api_response("delete_message", success)
    assert fake_daemon_rpc.delete_message_calls == [{"chat_id": DEFAULT_CHAT_ID, "message_id": "deletable"}]
    _assert_all_contract_events(fake_pyotherside_module)

    missing = main.delete_message(DEFAULT_CHAT_ID, "missing")
    validate_api_response("delete_message", missing)
    assert missing["success"] is False


def test_get_cached_stickers_contract(tmp_path) -> None:
    sticker_path = make_media_file(tmp_path, "cached.webp")
    with GreenlineKV() as kv:
        kv.put_record("sticker_cache:one", StickerCacheRecord(sticker_path))
        kv.put_record("sticker_cache:missing", StickerCacheRecord(str(tmp_path / "missing.webp")))

    result = main.get_cached_stickers()

    validate_api_response("get_cached_stickers", result)
    assert result == {"success": True, "stickers": ["file://" + sticker_path]}


def test_download_media_contract_success_and_failures(fake_daemon_rpc, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID)
    seed_message(
        DEFAULT_CHAT_ID,
        "downloadable",
        message_type=MessageType.IMAGE,
        is_outgoing=False,
        raw=raw_downloadable_media("image"),
        reply_to_id="",
    )

    success = main.download_media(DEFAULT_CHAT_ID, "downloadable", "image")

    validate_api_response("download_media", success)
    assert success["success"] is True
    _assert_all_contract_events(fake_pyotherside_module)
    message_updates = _event_payloads(fake_pyotherside_module, "message-upsert")
    assert message_updates[-1][0]["media_path"] == success["media_path"]

    invalid_type = main.download_media(DEFAULT_CHAT_ID, "downloadable", "unknown")
    validate_api_response("download_media", invalid_type)
    assert invalid_type["success"] is False

    missing = main.download_media(DEFAULT_CHAT_ID, "missing", "image")
    validate_api_response("download_media", missing)
    assert missing["success"] is False
