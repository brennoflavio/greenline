from __future__ import annotations

from qml_contract_helpers import DEFAULT_SENDER_ID, seed_sender_identity

from greenline.qml_text import build_text_render_data, format_qml_text
from greenline.store.mentions import template_mention_text
from models import MentionSpan


def test_format_qml_text_escapes_html() -> None:
    assert format_qml_text("<b>Hello</b>") == "&lt;b&gt;Hello&lt;/b&gt;"


def test_format_qml_text_wraps_http_and_https_links() -> None:
    assert format_qml_text("See https://example.com and http://example.org") == (
        'See <a href="https://example.com">https://example.com</a> and '
        '<a href="http://example.org">http://example.org</a>'
    )


def test_format_qml_text_trims_trailing_punctuation_from_links() -> None:
    assert format_qml_text("Visit https://example.com, now.") == (
        'Visit <a href="https://example.com">https://example.com</a>, now.'
    )
    assert format_qml_text("Paren https://example.com).") == (
        'Paren <a href="https://example.com">https://example.com</a>).'
    )


def test_format_qml_text_converts_newlines() -> None:
    assert format_qml_text("Hello\nWorld") == "Hello<br/>World"


def test_format_qml_text_renders_basic_bold() -> None:
    assert format_qml_text("Hello *bold* world") == "Hello <b>bold</b> world"
    assert format_qml_text("Hello *bold world") == "Hello *bold world"


def test_format_qml_text_handles_mixed_content_without_post_processing_links() -> None:
    assert format_qml_text("Hi *there* https://example.com\nBye") == (
        'Hi <b>there</b> <a href="https://example.com">https://example.com</a><br/>Bye'
    )


def test_format_qml_text_renders_mentions_as_greenline_links() -> None:
    seed_sender_identity(DEFAULT_SENDER_ID, name="Alice")
    templated_text, mentioned_jids = template_mention_text("Hello @222", [DEFAULT_SENDER_ID])

    assert format_qml_text(templated_text, mentioned_jids) == (
        'Hello <a href="greenline://chat/222%40s.whatsapp.net">@Alice</a>'
    )


def test_format_qml_text_keeps_unmatched_or_malformed_mentions_readable() -> None:
    seed_sender_identity(DEFAULT_SENDER_ID, name="Alice")

    assert format_qml_text("Hello \ue0002\ue001", [DEFAULT_SENDER_ID]) == "Hello \ue0002\ue001"
    assert format_qml_text("Hello \ue000oops\ue001", [DEFAULT_SENDER_ID]) == "Hello \ue000oops\ue001"


def test_format_qml_text_renders_plain_text_mentions_from_spans() -> None:
    assert format_qml_text(
        "@Empório Minatto https://example.com",
        [DEFAULT_SENDER_ID],
        [MentionSpan(DEFAULT_SENDER_ID, "Empório Minatto", 0, 16)],
    ) == (
        '<a href="greenline://chat/222%40s.whatsapp.net">@Empório Minatto</a> '
        '<a href="https://example.com">https://example.com</a>'
    )


def test_format_qml_text_ignores_mismatched_plain_text_mention_spans() -> None:
    assert (
        format_qml_text(
            "@Empório Minatto",
            [DEFAULT_SENDER_ID],
            [MentionSpan(DEFAULT_SENDER_ID, "Alice", 0, 16)],
        )
        == "@Empório Minatto"
    )


def test_format_qml_text_ignores_plain_text_mention_spans_with_invalid_prefix_boundary() -> None:
    assert (
        format_qml_text(
            "a@Empório Minatto",
            [DEFAULT_SENDER_ID],
            [MentionSpan(DEFAULT_SENDER_ID, "Empório Minatto", 1, 16)],
        )
        == "a@Empório Minatto"
    )


def test_format_qml_text_ignores_plain_text_mention_spans_with_invalid_suffix_boundary() -> None:
    assert (
        format_qml_text(
            "@Empório Minattox",
            [DEFAULT_SENDER_ID],
            [MentionSpan(DEFAULT_SENDER_ID, "Empório Minatto", 0, 16)],
        )
        == "@Empório Minattox"
    )


def test_build_text_render_data_marks_plain_newline_message_as_simple() -> None:
    render_data = build_text_render_data("Hello\nWorld")

    assert render_data.plain_text == "Hello\nWorld"
    assert render_data.rich_text == "Hello<br/>World"
    assert render_data.render_mode == "simple"


def test_build_text_render_data_marks_formatted_message_as_rich() -> None:
    render_data = build_text_render_data("Hello *bold* world")

    assert render_data.plain_text == "Hello *bold* world"
    assert render_data.rich_text == "Hello <b>bold</b> world"
    assert render_data.render_mode == "rich"
