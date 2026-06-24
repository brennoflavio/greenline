from __future__ import annotations

import logging

import pytest

from greenline.contracts.kv import GreenlineKV
from greenline.store.records import (
    DraftMentionsRecord,
    MessageIndexRecord,
    MessageReactionRecord,
    UnreadTotalRecord,
    stored_message_record,
)
from models import ChatListItem, MentionSpan, Message, MessageType, ReadReceipt
from ut_components.kv import KV


def _chat(chat_id: str = "chat@s.whatsapp.net") -> ChatListItem:
    return ChatListItem(
        id=chat_id,
        name="Chat",
        photo="",
        last_message="hello",
        date="10:00",
        last_message_timestamp=1,
        read_receipt=ReadReceipt.NONE,
        unread_count=0,
        is_group=False,
    )


def _message(message_id: str = "m1", timestamp: int = 1) -> Message:
    return Message(
        id=message_id,
        chat_id="chat@s.whatsapp.net",
        type=MessageType.TEXT,
        is_outgoing=False,
        timestamp="10:00",
        timestamp_unix=timestamp,
        read_receipt=ReadReceipt.NONE,
        text="hello",
    )


def test_object_records_round_trip_without_changing_storage_shape() -> None:
    chat = _chat()
    message = stored_message_record(_message(), raw={"Message": {"conversation": "hello"}})

    with GreenlineKV() as kv:
        kv.put_record(f"chat:{chat.id}", chat)
        kv.put_record(f"message:{message.chat_id}:{message.timestamp_unix}:{message.id}", message)

    with KV() as raw_kv:
        assert raw_kv.get(f"chat:{chat.id}") == {
            "id": chat.id,
            "name": "Chat",
            "photo": "",
            "last_message": "hello",
            "date": "10:00",
            "last_message_timestamp": 1,
            "read_receipt": "",
            "unread_count": 0,
            "is_group": False,
            "first_unread_message_id": "",
            "last_message_mentioned_jids": [],
            "last_message_type": "",
            "muted": False,
            "archived": False,
            "full_name": "",
            "push_name": "",
            "business_name": "",
            "name_updated_at": 0,
        }
        raw_message = raw_kv.get(f"message:{message.chat_id}:{message.timestamp_unix}:{message.id}")
        assert raw_message["has_reactions"] is False
        assert raw_message["reply_quote_payload_json"] == '{"conversation":"hello"}'
        assert raw_message["raw"] == {"Message": {"conversation": "hello"}}

    with GreenlineKV() as kv:
        assert kv.get_record(f"chat:{chat.id}") == chat
        assert kv.get_record(f"message:{message.chat_id}:{message.timestamp_unix}:{message.id}") == message


def test_stored_message_promotes_media_download_fields() -> None:
    message = stored_message_record(
        _message(),
        raw={
            "Message": {
                "imageMessage": {
                    "directPath": "/media/path",
                    "mediaKey": "key",
                    "fileEncSHA256": "enc",
                    "fileSHA256": "sha",
                    "fileLength": 123,
                    "mimetype": "image/jpeg",
                    "fileName": "photo.jpg",
                }
            }
        },
    )

    assert message.media_download.media_type == "image"
    assert message.media_download.direct_path == "/media/path"
    assert message.media_download.media_key == "key"
    assert message.media_download.file_enc_sha256 == "enc"
    assert message.media_download.file_sha256 == "sha"
    assert message.media_download.file_length == 123
    assert message.media_download.mimetype == "image/jpeg"
    assert message.media_download.file_name == "photo.jpg"


def test_stored_message_omits_none_raw() -> None:
    message = stored_message_record(_message())

    with GreenlineKV() as kv:
        kv.put_record(f"message:{message.chat_id}:{message.timestamp_unix}:{message.id}", message)

    with KV() as raw_kv:
        assert "raw" not in raw_kv.get(f"message:{message.chat_id}:{message.timestamp_unix}:{message.id}")


def test_stored_message_mention_spans_remain_typed_while_storage_is_json_like() -> None:
    source = _message()
    source.text = "Hello @Sender"
    source.mention_spans = [MentionSpan("sender@s.whatsapp.net", "Sender", 6, 7)]
    message = stored_message_record(source)

    with GreenlineKV() as kv:
        kv.put_record(f"message:{message.chat_id}:{message.timestamp_unix}:{message.id}", message)

    with KV() as raw_kv:
        assert raw_kv.get(f"message:{message.chat_id}:{message.timestamp_unix}:{message.id}")["mention_spans"] == [
            {"jid": "sender@s.whatsapp.net", "label": "Sender", "start": 6, "length": 7}
        ]

    with GreenlineKV() as kv:
        stored = kv.get_record(f"message:{message.chat_id}:{message.timestamp_unix}:{message.id}")
        assert stored.mention_spans == source.mention_spans
        assert isinstance(stored.mention_spans[0], MentionSpan)


def test_scalar_and_list_records_preserve_raw_values() -> None:
    spans = DraftMentionsRecord([MentionSpan("sender@s.whatsapp.net", "Sender", 0, 7)])
    reaction = MessageReactionRecord(
        chat_id="chat@s.whatsapp.net",
        message_id="m1",
        sender_jid="sender@s.whatsapp.net",
        emoji="👍",
    )

    with GreenlineKV() as kv:
        kv.put_record("unread_total", UnreadTotalRecord(3))
        kv.put_record("message_index:chat@s.whatsapp.net:m1", MessageIndexRecord("message:chat@s.whatsapp.net:1:m1"))
        kv.put_record("draft_mentions:chat@s.whatsapp.net", spans)
        kv.put_record("message_reaction:chat@s.whatsapp.net:m1:sender@s.whatsapp.net", reaction)

    with KV() as raw_kv:
        assert raw_kv.get("unread_total") == 3
        assert raw_kv.get("message_index:chat@s.whatsapp.net:m1") == "message:chat@s.whatsapp.net:1:m1"
        assert raw_kv.get("draft_mentions:chat@s.whatsapp.net") == [
            {"jid": "sender@s.whatsapp.net", "label": "Sender", "start": 0, "length": 7}
        ]
        assert raw_kv.get("message_reaction:chat@s.whatsapp.net:m1:sender@s.whatsapp.net") == {
            "chat_id": "chat@s.whatsapp.net",
            "message_id": "m1",
            "sender_jid": "sender@s.whatsapp.net",
            "emoji": "👍",
        }

    with GreenlineKV() as kv:
        assert kv.get_record("unread_total") == UnreadTotalRecord(3)
        assert kv.get_record("message_index:chat@s.whatsapp.net:m1") == MessageIndexRecord(
            "message:chat@s.whatsapp.net:1:m1"
        )
        draft_mentions = kv.get_record("draft_mentions:chat@s.whatsapp.net")
        assert draft_mentions == spans
        assert isinstance(draft_mentions.value[0], MentionSpan)
        assert kv.get_record("message_reaction:chat@s.whatsapp.net:m1:sender@s.whatsapp.net") == reaction


def test_prefix_reads_paged_reads_and_cached_writes() -> None:
    with GreenlineKV() as kv:
        for index in range(3):
            msg = stored_message_record(_message(f"m{index}", index))
            kv.put_cached_record(f"message:{msg.chat_id}:{msg.timestamp_unix}:{msg.id}", msg)
        assert kv.get_partial_records("message:chat@s.whatsapp.net:") == []
        kv.commit_cached()

        records = kv.get_partial_records("message:chat@s.whatsapp.net:")
        assert {record.id for _, record in records} == {"m0", "m1", "m2"}

        page, cursor = kv.get_partial_page_records("message:chat@s.whatsapp.net:", page_size=2)
        assert [record.id for _, record in page] == ["m0", "m1"]
        assert cursor == "message:chat@s.whatsapp.net:1:m1"
        next_page, next_cursor = kv.get_partial_page_records("message:chat@s.whatsapp.net:", page_size=2, cursor=cursor)
        assert [record.id for _, record in next_page] == ["m2"]
        assert next_cursor is None


def test_missing_key_without_default_returns_none_without_logging(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with GreenlineKV() as kv:
        assert kv.get_record("unread_total") is None

    assert not any("missing KV key" in record.message for record in caplog.records)


def test_missing_required_key_logs_kv_metadata(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with GreenlineKV() as kv:
        assert kv.get_record("unread_total", required=True) is None

    assert any(
        record.boundary == "kv"
        and record.contract == "unread_total"
        and record.direction == "decode"
        and "missing KV key" in record.message
        for record in caplog.records
    )


def test_missing_key_returns_typed_default_without_logging(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with GreenlineKV() as kv:
        assert kv.get_record("unread_total", default=UnreadTotalRecord(0)) == UnreadTotalRecord(0)
        with pytest.raises(TypeError):
            kv.get_record("unread_total", default=MessageIndexRecord("bad"))

    assert not any("missing KV key" in record.message for record in caplog.records)


def test_registry_and_encode_failures_log_kv_metadata(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with GreenlineKV() as kv:
        with pytest.raises(TypeError):
            kv.put_record("unread_total", MessageIndexRecord("wrong"))
        with pytest.raises(TypeError):
            kv.put_record("unread_total", 1)

    assert any(
        record.boundary == "kv" and record.contract == "unread_total" and record.direction == "encode"
        for record in caplog.records
    )


def test_extra_stored_fields_are_rejected() -> None:
    chat = _chat()
    with KV() as raw_kv:
        raw_payload = {
            "id": chat.id,
            "name": chat.name,
            "photo": chat.photo,
            "last_message": chat.last_message,
            "date": chat.date,
            "last_message_timestamp": chat.last_message_timestamp,
            "read_receipt": chat.read_receipt.value,
            "unread_count": chat.unread_count,
            "is_group": chat.is_group,
            "unexpected": True,
        }
        raw_kv.put(f"chat:{chat.id}", raw_payload)

    with GreenlineKV() as kv:
        with pytest.raises(Exception):
            kv.get_record(f"chat:{chat.id}")


def test_invalid_write_field_types_are_rejected() -> None:
    chat = _chat()
    chat.name = None  # type: ignore[assignment]

    with GreenlineKV() as kv:
        with pytest.raises(Exception):
            kv.put_record(f"chat:{chat.id}", chat)


def test_exact_key_contracts_do_not_match_prefixed_keys() -> None:
    with GreenlineKV() as kv:
        with pytest.raises(KeyError):
            kv.put_record("unread_total:anything", UnreadTotalRecord(1))


def test_malformed_stored_data_logs_decode_metadata(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="greenline.contracts")

    with KV() as raw_kv:
        raw_kv.put("chat:bad", {"id": "chat:bad"})

    with GreenlineKV() as kv:
        with pytest.raises(Exception):
            kv.get_record("chat:bad")

    assert any(
        record.boundary == "kv" and record.contract == "chat:" and record.direction == "decode"
        for record in caplog.records
    )
