from __future__ import annotations

from dataclasses import asdict

from greenline import qml_payloads
from greenline.store.mentions import mention_transport_payload, validate_mention_spans
from greenline.ui import inflate_dataclass
from models import MentionSpan, Message, MessageType, ReadReceipt


def _message(span: MentionSpan) -> Message:
    return Message(
        id="m1",
        chat_id="chat@s.whatsapp.net",
        type=MessageType.TEXT,
        is_outgoing=True,
        timestamp="10:00",
        timestamp_unix=1,
        read_receipt=ReadReceipt.NONE,
        text="Hello @Sender",
        mentioned_jids=[span.jid],
        mention_spans=[span],
    )


def test_qml_dict_input_validates_to_typed_mention_spans() -> None:
    spans = validate_mention_spans(
        "Hello @Sender",
        [{"jid": "sender@s.whatsapp.net", "label": "Sender", "start": 6, "length": 7}],
    )

    assert spans == [MentionSpan("sender@s.whatsapp.net", "Sender", 6, 7)]
    assert isinstance(spans[0], MentionSpan)


def test_typed_input_validates_to_typed_mention_spans() -> None:
    span = MentionSpan("sender@s.whatsapp.net", "Sender", 6, 7)

    spans = validate_mention_spans("Hello @Sender", [span])

    assert spans == [span]
    assert isinstance(spans[0], MentionSpan)


def test_mention_transport_payload_preserves_behavior_with_typed_spans() -> None:
    span = MentionSpan("sender@s.whatsapp.net", "Sender", 6, 7)

    transport_text, transport_spans, mentioned_jids = mention_transport_payload("Hello @Sender", [span])

    assert transport_text == "Hello @sender"
    assert transport_spans == [span]
    assert isinstance(transport_spans[0], MentionSpan)
    assert mentioned_jids == ["sender@s.whatsapp.net"]


def test_qml_payload_shape_remains_plain_mention_span_dicts() -> None:
    span = MentionSpan("sender@s.whatsapp.net", "Sender", 6, 7)

    payload = qml_payloads.ui_message(_message(span))

    assert payload["mention_spans"] == [{"jid": "sender@s.whatsapp.net", "label": "Sender", "start": 6, "length": 7}]


def test_inflate_dataclass_rebuilds_nested_mention_spans() -> None:
    span = MentionSpan("sender@s.whatsapp.net", "Sender", 6, 7)

    inflated = inflate_dataclass(Message, asdict(_message(span)))

    assert inflated.mention_spans == [span]
    assert isinstance(inflated.mention_spans[0], MentionSpan)
