import html
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple
from urllib.parse import quote

from greenline.store.identity import resolve_sender_name
from greenline.store.mentions import render_mention_text

_MENTION_PLACEHOLDER_RE = re.compile(r"\ue000(\d+)\ue001")
_TOKEN_RE = re.compile(r"(?P<url>https?://[^\s<]+)|(?P<mention>\ue000(?P<mention_index>\d+)\ue001)")
_BOLD_RE = re.compile(r"\*(?=\S)(.+?)(?<=\S)\*")
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


def format_qml_text(text: str, mentioned_jids: Optional[Sequence[str]] = None) -> str:
    if not text:
        return ""

    normalized_mentioned_jids = list(mentioned_jids or [])
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


def build_text_render_data(text: str, mentioned_jids: Optional[Sequence[str]] = None) -> TextRenderData:
    if not text:
        return TextRenderData(plain_text="", rich_text="", render_mode=TEXT_RENDER_MODE_SIMPLE)

    normalized_mentioned_jids = list(mentioned_jids or [])
    plain_text = render_mention_text(text, normalized_mentioned_jids)
    rich_text = format_qml_text(text, normalized_mentioned_jids)
    render_mode = TEXT_RENDER_MODE_RICH if rich_text != _escape_plain_text(plain_text) else TEXT_RENDER_MODE_SIMPLE
    return TextRenderData(plain_text=plain_text, rich_text=rich_text, render_mode=render_mode)


__all__ = [
    "TextRenderData",
    "TEXT_RENDER_MODE_RICH",
    "TEXT_RENDER_MODE_SIMPLE",
    "build_text_render_data",
    "format_qml_text",
]
