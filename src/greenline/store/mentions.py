import re
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

from greenline.store.identity import (
    _LID_JID_SUFFIX,
    _strip_device_suffix,
    canonicalize_contact_jid,
    resolve_sender_name,
    resolve_sender_photo,
)
from greenline.store.media import _quoted_message_preview
from models import ChatListItem, Message
from rpc import DaemonRPC
from ut_components.kv import KV

_MENTION_TOKEN_RE = re.compile(r"@([0-9][0-9A-Za-z:._-]*)")
_MENTION_PLACEHOLDER_RE = re.compile("\ue000(\\d+)\ue001")


def _mention_placeholder(index: int) -> str:
    return f"\ue000{index}\ue001"


def _context_mentioned_jids(context_info: Any) -> List[str]:
    if context_info is None:
        return []
    if isinstance(context_info, dict):
        mentioned = context_info.get("mentionedJID")
    else:
        mentioned = getattr(context_info, "mentionedJID", None)
    if not mentioned:
        return []
    return [str(jid) for jid in mentioned if jid]


def normalize_mentioned_jids(
    mentioned_jids: Optional[List[str]],
    *,
    jid_map: Optional[Dict[str, str]] = None,
) -> List[str]:
    if not mentioned_jids:
        return []

    needs_rpc = any(_strip_device_suffix(str(jid)).endswith(_LID_JID_SUFFIX) for jid in mentioned_jids if jid)
    rpc = DaemonRPC() if needs_rpc else None
    with KV() as kv:
        return [
            canonicalize_contact_jid(str(jid), jid_map=jid_map, kv=kv, rpc=rpc) if jid else "" for jid in mentioned_jids
        ]


def _utf16_boundary_map(text: str) -> Dict[int, int]:
    boundaries = {0: 0}
    offset = 0
    for index, char in enumerate(text):
        offset += 2 if ord(char) > 0xFFFF else 1
        boundaries[offset] = index + 1
    return boundaries


def _mention_span_text(text: str, start: int, length: int) -> Tuple[int, int, str] | tuple[None, None, None]:
    if start < 0 or length <= 0:
        return None, None, None

    boundaries = _utf16_boundary_map(text)
    start_index = boundaries.get(start)
    end_index = boundaries.get(start + length)
    if start_index is None or end_index is None:
        return None, None, None
    return start_index, end_index, text[start_index:end_index]


def _is_mention_boundary_char(char: str) -> bool:
    return char == "" or not (char.isalnum() or char == "_")


def _mention_span_matches(text: str, label: str, start: int, length: int) -> bool:
    start_index, end_index, span_text = _mention_span_text(text, start, length)
    if start_index is None or end_index is None or span_text != f"@{label}":
        return False

    before = text[start_index - 1] if start_index > 0 else ""
    after = text[end_index] if end_index < len(text) else ""
    return _is_mention_boundary_char(before) and _is_mention_boundary_char(after)


def _mention_transport_token(jid: str) -> str:
    user = _strip_device_suffix(str(jid)).split("@", 1)[0]
    return f"@{user}" if user else ""


def build_mention_candidate(jid: str, push_name: str = "") -> Dict[str, Any]:
    candidate_jid = canonicalize_contact_jid(jid)
    return {
        "jid": candidate_jid,
        "label": resolve_sender_name(candidate_jid, push_name),
        "photo": resolve_sender_photo(candidate_jid),
    }


def validate_mention_spans(
    text: str,
    mention_spans: Optional[List[Dict[str, Any]]],
    *,
    jid_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    if not text or not mention_spans:
        return []

    validated: List[Dict[str, Any]] = []
    for index, span in enumerate(mention_spans):
        if not isinstance(span, dict):
            continue
        jid = str(span.get("jid") or "")
        label = str(span.get("label") or "")
        raw_start = span.get("start")
        raw_length = span.get("length")
        if raw_start is None or raw_length is None:
            continue
        try:
            start = int(raw_start)
            length = int(raw_length)
        except (TypeError, ValueError):
            continue
        if not jid or not label or start < 0 or length <= 0:
            continue
        token = f"@{label}"
        if length != len(token.encode("utf-16-le")) // 2 or not _mention_span_matches(text, label, start, length):
            continue
        validated.append({"jid": jid, "label": label, "start": start, "length": length, "_order": index})

    if not validated:
        return []

    validated.sort(key=lambda span: (int(span["start"]), int(span["_order"])))

    non_overlapping: List[Dict[str, Any]] = []
    last_end = -1
    for span in validated:
        start = int(span["start"])
        end = start + int(span["length"])
        if start < last_end:
            continue
        non_overlapping.append(span)
        last_end = end

    normalized_jids = normalize_mentioned_jids([str(span["jid"]) for span in non_overlapping], jid_map=jid_map)
    return [
        {
            "jid": normalized_jids[index],
            "label": str(span["label"]),
            "start": int(span["start"]),
            "length": int(span["length"]),
        }
        for index, span in enumerate(non_overlapping)
        if normalized_jids[index]
    ]


def mention_transport_payload(
    text: str,
    mention_spans: Optional[List[Dict[str, Any]]],
    *,
    jid_map: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    validated_spans = validate_mention_spans(text, mention_spans, jid_map=jid_map)
    if not validated_spans:
        return text, [], []

    parts: List[str] = []
    transport_spans: List[Dict[str, Any]] = []
    mentioned_jids: List[str] = []
    last_end = 0
    for span in validated_spans:
        start_index, end_index, _ = _mention_span_text(text, int(span["start"]), int(span["length"]))
        token = _mention_transport_token(str(span["jid"]))
        if start_index is None or end_index is None or not token:
            continue
        parts.append(text[last_end:start_index])
        parts.append(token)
        last_end = end_index
        transport_spans.append(dict(span))
        mentioned_jids.append(str(span["jid"]))
    parts.append(text[last_end:])

    if not transport_spans:
        return text, [], []

    return "".join(parts), transport_spans, mentioned_jids


def template_mention_text(
    text: str,
    mentioned_jids: Optional[List[str]],
    *,
    jid_map: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str]]:
    if not text or not mentioned_jids:
        return text, []

    matches = list(_MENTION_TOKEN_RE.finditer(text))
    if len(matches) != len(mentioned_jids):
        return text, []

    normalized_jids = normalize_mentioned_jids(list(mentioned_jids), jid_map=jid_map)
    parts: List[str] = []
    last_end = 0
    for index, match in enumerate(matches, start=1):
        parts.append(text[last_end : match.start()])
        parts.append(_mention_placeholder(index))
        last_end = match.end()
    parts.append(text[last_end:])
    return "".join(parts), normalized_jids


def render_mention_text(text: str, mentioned_jids: Optional[List[str]]) -> str:
    if not text or not mentioned_jids:
        return text

    def replace_placeholder(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        if index < 0 or index >= len(mentioned_jids):
            return match.group(0)
        return f"@{resolve_sender_name(mentioned_jids[index])}"

    return _MENTION_PLACEHOLDER_RE.sub(replace_placeholder, text)


def render_message_mentions(message: Message) -> Message:
    rendered = replace(message)
    rendered.text = render_mention_text(rendered.text, rendered.mentioned_jids)
    rendered.caption = render_mention_text(rendered.caption, rendered.mentioned_jids)
    rendered.reply_to_text = render_mention_text(rendered.reply_to_text, rendered.reply_to_mentioned_jids)
    return rendered


def render_chat_mentions(chat: ChatListItem) -> ChatListItem:
    rendered = replace(chat)
    rendered.last_message = render_mention_text(rendered.last_message, rendered.last_message_mentioned_jids)
    return rendered


def _template_text_from_context_info(
    text: str,
    context_info: Any,
    *,
    jid_map: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str]]:
    return template_mention_text(text, _context_mentioned_jids(context_info), jid_map=jid_map)


def quoted_message_template(
    quoted: Optional[Dict[str, Any]],
    *,
    jid_map: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str]]:
    preview = _quoted_message_preview(quoted)
    if not preview or not quoted:
        return preview, []

    context_info = None
    for field_name in (
        "extendedTextMessage",
        "imageMessage",
        "videoMessage",
        "audioMessage",
        "documentMessage",
        "contactMessage",
        "stickerMessage",
    ):
        sub = quoted.get(field_name)
        if sub and isinstance(sub, dict):
            context_info = sub.get("contextInfo")
            if context_info:
                break

    return _template_text_from_context_info(preview, context_info, jid_map=jid_map)
