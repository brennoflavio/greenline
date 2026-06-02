from __future__ import annotations

import time

from contracts.qml_registry import validate_api_response, validate_event_payload
from qml_contract_helpers import (
    DEFAULT_CHAT_ID,
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
from greenline.store.records import (
    MessageReactionRecord,
    PendingOutboxRecord,
    StickerCacheRecord,
    StoredMessageRecord,
)
from models import MessageType, ReadReceipt


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
            }
        ],
        "message": "",
    }


def test_mark_messages_as_read_contract_and_chat_emit(fake_daemon_rpc, fake_pyotherside_module) -> None:
    seed_chat(DEFAULT_CHAT_ID, unread_count=2)
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

    assert [call["message_type"] for call in fake_daemon_rpc.send_message_calls] == [
        "image",
        "video",
        "document",
        "sticker",
        "contact",
    ]
    document_call = fake_daemon_rpc.send_message_calls[2]
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
