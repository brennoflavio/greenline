import html
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple
from urllib.parse import quote

from greenline.store.identity import resolve_sender_name
from greenline.store.mentions import render_mention_text
from models import MentionSpan

_MENTION_PLACEHOLDER_RE = re.compile(r"\ue000(\d+)\ue001")
_TOKEN_RE = re.compile(r"(?P<url>https?://[^\s<]+)|(?P<mention>\ue000(?P<mention_index>\d+)\ue001)")
_BOLD_RE = re.compile(r"\*(?=\S)(.+?)(?<=\S)\*")
_LIST_ITEM_RE = re.compile(r"^(?P<marker>[-*])\s+(?P<content>.*)$")
_SIMPLE_URL_TRAILING_PUNCTUATION = ".,!?:;"
TEXT_RENDER_MODE_SIMPLE = "simple"
TEXT_RENDER_MODE_RICH = "rich"


@dataclass(frozen=True)
class TextRenderData:
    plain_text: str
    rich_text: str
    render_mode: str


def _escape_plain_text(text: str) -> str:
    return html.escape(text).replace("\n", "<br/>")


def _trim_url_trailing_punctuation(url: str) -> Tuple[str, str]:
    trimmed = url
    trailing = ""

    while trimmed:
        last_char = trimmed[-1]
        if last_char in _SIMPLE_URL_TRAILING_PUNCTUATION:
            trailing = last_char + trailing
            trimmed = trimmed[:-1]
            continue
        if last_char == ")" and trimmed.count("(") < trimmed.count(")"):
            trailing = last_char + trailing
            trimmed = trimmed[:-1]
            continue
        break

    return trimmed, trailing


def _format_plain_segment(text: str) -> str:
    if not text:
        return ""

    parts: List[str] = []
    last_end = 0
    for match in _BOLD_RE.finditer(text):
        parts.append(_escape_plain_text(text[last_end : match.start()]))
        parts.append(f"<b>{_escape_plain_text(match.group(1))}</b>")
        last_end = match.end()
    parts.append(_escape_plain_text(text[last_end:]))
    return "".join(parts)


def _format_url(url: str) -> str:
    href, trailing = _trim_url_trailing_punctuation(url)
    if not href:
        return _escape_plain_text(url)
    escaped_href = html.escape(href, quote=True)
    return f'<a href="{escaped_href}">{html.escape(href)}</a>{_escape_plain_text(trailing)}'


def _format_mention(match: re.Match[str], mentioned_jids: Sequence[str]) -> str:
    index = int(match.group("mention_index")) - 1
    if index < 0 or index >= len(mentioned_jids):
        return _escape_plain_text(match.group(0))

    jid = mentioned_jids[index]
    if not jid:
        return _escape_plain_text(match.group(0))

    label = resolve_sender_name(jid)
    href = html.escape(f"greenline://chat/{quote(jid, safe='')}", quote=True)
    return f'<a href="{href}">@{html.escape(label)}</a>'


def _format_span_mention(span_text: str, jid: str) -> str:
    if not jid:
        return _escape_plain_text(span_text)

    href = html.escape(f"greenline://chat/{quote(jid, safe='')}", quote=True)
    return f'<a href="{href}">{html.escape(span_text)}</a>'


def _utf16_boundary_map(text: str) -> dict[int, int]:
    boundaries = {0: 0}
    offset = 0
    for index, char in enumerate(text):
        offset += 2 if ord(char) > 0xFFFF else 1
        boundaries[offset] = index + 1
    return boundaries


def _mention_span_bounds(text: str, span: MentionSpan) -> tuple[int, int] | tuple[None, None]:
    if span.start < 0 or span.length <= 0:
        return None, None

    boundaries = _utf16_boundary_map(text)
    start_index = boundaries.get(span.start)
    end_index = boundaries.get(span.start + span.length)
    if start_index is None or end_index is None or end_index <= start_index:
        return None, None
    return start_index, end_index


def _utf16_offsets_by_index(text: str) -> list[int]:
    offsets = [0]
    offset = 0
    for char in text:
        offset += 2 if ord(char) > 0xFFFF else 1
        offsets.append(offset)
    return offsets


def _segment_mention_spans(
    text: str,
    mention_spans: Sequence[MentionSpan],
    start_index: int,
    end_index: int,
    utf16_offsets: Sequence[int],
) -> list[MentionSpan]:
    if start_index >= end_index:
        return []

    segment_start_utf16 = utf16_offsets[start_index]
    segment_spans: list[MentionSpan] = []
    for span in mention_spans:
        span_start_index, span_end_index = _mention_span_bounds(text, span)
        if span_start_index is None or span_end_index is None:
            continue
        if span_start_index < start_index or span_end_index > end_index:
            continue
        segment_spans.append(
            MentionSpan(
                jid=span.jid,
                label=span.label,
                start=span.start - segment_start_utf16,
                length=span.length,
            )
        )
    return segment_spans


def _is_mention_boundary_char(char: str) -> bool:
    return char == "" or not (char.isalnum() or char == "_")


def _has_valid_mention_boundaries(text: str, start_index: int, end_index: int) -> bool:
    before = text[start_index - 1] if start_index > 0 else ""
    after = text[end_index] if end_index < len(text) else ""
    return _is_mention_boundary_char(before) and _is_mention_boundary_char(after)


def _format_plain_text_with_urls(text: str) -> str:
    if not text:
        return ""

    parts: List[str] = []
    last_end = 0
    for match in re.finditer(r"https?://[^\s<]+", text):
        parts.append(_format_plain_segment(text[last_end : match.start()]))
        parts.append(_format_url(match.group(0)))
        last_end = match.end()
    parts.append(_format_plain_segment(text[last_end:]))
    return "".join(parts)


def _format_text_with_mention_spans(text: str, mention_spans: Sequence[MentionSpan]) -> str:
    parts: List[str] = []
    last_end = 0
    for span in sorted(mention_spans, key=lambda item: item.start):
        start_index, end_index = _mention_span_bounds(text, span)
        if start_index is None or end_index is None or start_index < last_end:
            continue

        span_text = text[start_index:end_index]
        if span_text != f"@{span.label}" or not _has_valid_mention_boundaries(text, start_index, end_index):
            continue

        parts.append(_format_plain_text_with_urls(text[last_end:start_index]))
        parts.append(_format_span_mention(span_text, span.jid))
        last_end = end_index

    parts.append(_format_plain_text_with_urls(text[last_end:]))
    return "".join(parts)


def _format_inline_text(
    text: str,
    mentioned_jids: Optional[Sequence[str]] = None,
    mention_spans: Optional[Sequence[MentionSpan]] = None,
) -> str:
    normalized_mentioned_jids = list(mentioned_jids or [])
    if normalized_mentioned_jids and _MENTION_PLACEHOLDER_RE.search(text):
        parts: List[str] = []
        last_end = 0

        for match in _TOKEN_RE.finditer(text):
            parts.append(_format_plain_segment(text[last_end : match.start()]))
            if match.group("url"):
                parts.append(_format_url(match.group("url")))
            else:
                parts.append(_format_mention(match, normalized_mentioned_jids))
            last_end = match.end()

        parts.append(_format_plain_segment(text[last_end:]))
        return "".join(parts)

    normalized_mention_spans = list(mention_spans or [])
    if normalized_mention_spans:
        return _format_text_with_mention_spans(text, normalized_mention_spans)

    return _format_plain_text_with_urls(text)


def format_qml_text(
    text: str,
    mentioned_jids: Optional[Sequence[str]] = None,
    mention_spans: Optional[Sequence[MentionSpan]] = None,
) -> str:
    if not text:
        return ""

    normalized_mentioned_jids = list(mentioned_jids or [])
    normalized_mention_spans = list(mention_spans or [])
    utf16_offsets = _utf16_offsets_by_index(text)
    formatted_lines: list[str] = []
    line_start = 0

    for line in text.split("\n"):
        line_end = line_start + len(line)
        list_match = _LIST_ITEM_RE.match(line)
        if list_match:
            content_start = line_start + list_match.start("content")
            content_spans = _segment_mention_spans(
                text,
                normalized_mention_spans,
                content_start,
                line_end,
                utf16_offsets,
            )
            formatted_lines.append(
                f"• {_format_inline_text(list_match.group('content'), normalized_mentioned_jids, content_spans)}"
            )
        else:
            line_spans = _segment_mention_spans(text, normalized_mention_spans, line_start, line_end, utf16_offsets)
            formatted_lines.append(_format_inline_text(line, normalized_mentioned_jids, line_spans))
        line_start = line_end + 1

    return "<br/>".join(formatted_lines)


def build_text_render_data(
    text: str,
    mentioned_jids: Optional[Sequence[str]] = None,
    mention_spans: Optional[Sequence[MentionSpan]] = None,
) -> TextRenderData:
    if not text:
        return TextRenderData(plain_text="", rich_text="", render_mode=TEXT_RENDER_MODE_SIMPLE)

    normalized_mentioned_jids = list(mentioned_jids or [])
    plain_text = render_mention_text(text, normalized_mentioned_jids)
    rich_text = format_qml_text(text, normalized_mentioned_jids, mention_spans)
    render_mode = TEXT_RENDER_MODE_RICH if rich_text != _escape_plain_text(plain_text) else TEXT_RENDER_MODE_SIMPLE
    return TextRenderData(plain_text=plain_text, rich_text=rich_text, render_mode=render_mode)


__all__ = [
    "TextRenderData",
    "TEXT_RENDER_MODE_RICH",
    "TEXT_RENDER_MODE_SIMPLE",
    "build_text_render_data",
    "format_qml_text",
]
