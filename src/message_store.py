import base64
import os
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from constants import GROUP_JID_SUFFIX, WHATSAPP_JID_SUFFIX
from models import ChatListItem, Message, MessageType, ReadReceipt, UiMessage
from rpc import DaemonRPC
from unread_counter import increment_unread_total
from ut_components.config import get_cache_path
from ut_components.kv import KV
from whatsmeow_types import (
    MessageContent,
    MessageEvent,
    MessageInfo,
    UndecryptableMessageEvent,
)


def _get_thumbnail_dir() -> str:
    return os.path.join(get_cache_path(), "thumbnails")


def _get_contact_dir(chat_id: str) -> str:
    return os.path.join(get_cache_path(), "contacts", chat_id)


def _contact_preview(display_name: str) -> str:
    name = display_name.strip()
    return f"👤 {name}" if name else "👤 Contact"


def persist_contact_vcard(chat_id: str, message_id: str, display_name: str, vcard: str) -> str:
    if not vcard:
        return ""
    contact_dir = _get_contact_dir(chat_id)
    os.makedirs(contact_dir, exist_ok=True)
    file_path = os.path.join(contact_dir, f"{message_id or 'contact'}.vcf")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(vcard)
    return "file://" + file_path


_CHAT_RUNTIME_CACHE: Dict[str, Dict[str, Any]] = {}
_MESSAGE_FIELDS = set(Message.__dataclass_fields__.keys())
_DELETED_MESSAGE_PREVIEW = "Deleted message"


def clear_chat_runtime_cache() -> None:
    _CHAT_RUNTIME_CACHE.clear()


def remember_chat(chat: ChatListItem) -> None:
    _CHAT_RUNTIME_CACHE[chat.id] = asdict(chat)


def sanitize_message_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = {k: v for k, v in payload.items() if k in _MESSAGE_FIELDS}
    if "raw" in payload:
        sanitized["raw"] = payload["raw"]
    return sanitized


def message_storage_key(chat_id: str, timestamp_unix: int, message_id: str) -> str:
    return f"message:{chat_id}:{timestamp_unix}:{message_id}"


def message_index_key(chat_id: str, message_id: str) -> str:
    return f"message_index:{chat_id}:{message_id}"


def put_message_index(kv: KV, chat_id: str, message_id: str, storage_key: str) -> None:
    if not chat_id or not message_id or not storage_key:
        return
    kv.put(message_index_key(chat_id, message_id), storage_key)


def delete_message_index(kv: KV, chat_id: str, message_id: str) -> None:
    if not chat_id or not message_id:
        return
    kv.delete(message_index_key(chat_id, message_id))


def get_message_entry_with_key(kv: KV, chat_id: str, message_id: str) -> Tuple[str, Dict[str, Any]] | tuple[None, None]:
    if not chat_id or not message_id:
        return None, None

    indexed_key = kv.get(message_index_key(chat_id, message_id))
    if not isinstance(indexed_key, str) or not indexed_key:
        return None, None

    indexed_value = kv.get(indexed_key)
    if (
        indexed_key.startswith(f"message:{chat_id}:")
        and isinstance(indexed_value, dict)
        and indexed_value.get("id") == message_id
        and indexed_value.get("chat_id") == chat_id
    ):
        return indexed_key, indexed_value

    delete_message_index(kv, chat_id, message_id)
    return None, None


def _get_chat_data(chat_jid: str) -> Optional[Dict[str, Any]]:
    if not chat_jid:
        return None

    cached = _CHAT_RUNTIME_CACHE.get(chat_jid)
    if cached is not None:
        return cached

    with KV() as kv:
        data = kv.get(f"chat:{chat_jid}")
    if data is None:
        return None

    cached_data = dict(data)
    _CHAT_RUNTIME_CACHE[chat_jid] = cached_data
    return cached_data


def update_chat_name(
    chat: ChatListItem,
    timestamp: int,
    *,
    full_name: str = "",
    push_name: str = "",
    business_name: str = "",
) -> bool:
    if timestamp < chat.name_updated_at:
        return False
    changed = False
    if full_name and chat.full_name != full_name:
        chat.full_name = full_name
        changed = True
    if push_name and chat.push_name != push_name:
        chat.push_name = push_name
        changed = True
    if business_name and chat.business_name != business_name:
        chat.business_name = business_name
        changed = True
    if changed:
        chat.name_updated_at = timestamp
        chat.name = chat.full_name or chat.push_name or chat.business_name or chat.id
    return changed


def resolve_sender_name(sender_jid: str, push_name: str = "") -> str:
    data = _get_chat_data(sender_jid)
    if data is not None:
        name = str(data.get("name", ""))
        if name and name != sender_jid:
            return name
    if push_name:
        return push_name
    return sender_jid.replace(WHATSAPP_JID_SUFFIX, "")


def resolve_sender_photo(sender_jid: str) -> str:
    data = _get_chat_data(sender_jid)
    if data is None:
        return ""
    return str(data.get("photo", "") or "")


def upsert_identity_chat(
    chat_id: str,
    timestamp: int,
    *,
    full_name: str = "",
    push_name: str = "",
    business_name: str = "",
) -> None:
    if not chat_id:
        return

    chat_id = canonicalize_contact_jid(chat_id)
    chat_key = f"chat:{chat_id}"
    with KV() as kv:
        existing = kv.get(chat_key)
        if existing is not None:
            chat = ChatListItem(**existing)
            changed = update_chat_name(
                chat,
                timestamp,
                full_name=full_name,
                push_name=push_name,
                business_name=business_name,
            )
            if changed:
                kv.put(chat_key, asdict(chat))
        else:
            display_name = full_name or push_name or business_name or chat_id.replace(WHATSAPP_JID_SUFFIX, "")
            chat = ChatListItem(
                id=chat_id,
                name=display_name,
                photo="",
                last_message="",
                date="",
                last_message_timestamp=0,
                read_receipt=ReadReceipt.NONE,
                unread_count=0,
                is_group=chat_id.endswith(GROUP_JID_SUFFIX),
                full_name=full_name,
                push_name=push_name,
                business_name=business_name,
                name_updated_at=timestamp,
            )
            kv.put(chat_key, asdict(chat))

    remember_chat(chat)


_MENTION_TOKEN_RE = re.compile(r"@([0-9][0-9A-Za-z:._-]*)")
_MENTION_PLACEHOLDER_RE = re.compile("\ue000(\\d+)\ue001")
_STATUS_BROADCAST_JID = "status@broadcast"
_NEWSLETTER_JID_SUFFIX = "@newsletter"
_LID_JID_SUFFIX = "@lid"


def _mention_placeholder(index: int) -> str:
    return f"\ue000{index}\ue001"


def _is_contact_identity_jid(jid: str) -> bool:
    return (
        bool(jid)
        and jid != _STATUS_BROADCAST_JID
        and not jid.endswith(GROUP_JID_SUFFIX)
        and not jid.endswith(_NEWSLETTER_JID_SUFFIX)
    )


def _strip_device_suffix(jid: str) -> str:
    if not jid or "@" not in jid:
        return jid

    user, server = jid.split("@", 1)
    base_user, separator, device = user.rpartition(":")
    if separator and base_user and device.isdigit():
        user = base_user
    return f"{user}@{server}"


def canonicalize_contact_jid(
    jid: str,
    *,
    jid_map: Optional[Dict[str, str]] = None,
    kv: Optional[KV] = None,
    rpc: Optional[DaemonRPC] = None,
) -> str:
    if not _is_contact_identity_jid(jid):
        return jid

    stripped_jid = _strip_device_suffix(str(jid))
    resolved = jid_map.get(stripped_jid) or jid_map.get(jid) if jid_map is not None else None

    if not resolved and stripped_jid.endswith(_LID_JID_SUFFIX):
        cached = None
        if kv is None:
            with KV() as lid_kv:
                cached = lid_kv.get(f"lid_map:{stripped_jid}") or lid_kv.get(f"lid_map:{jid}")
        else:
            cached = kv.get(f"lid_map:{stripped_jid}") or kv.get(f"lid_map:{jid}")
        if cached:
            resolved = str(cached)

    if not resolved and stripped_jid.endswith(_LID_JID_SUFFIX):
        try:
            resolved = rpc.ensure_jid(stripped_jid) if rpc is not None else DaemonRPC().ensure_jid(stripped_jid)
        except Exception:
            resolved = stripped_jid

    return _strip_device_suffix(str(resolved or stripped_jid))


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


def to_ui_message(message: Message) -> UiMessage:
    rendered = render_message_mentions(message)

    sender_name = ""
    sender_photo = ""
    if rendered.sender and not rendered.is_outgoing:
        sender_name = resolve_sender_name(rendered.sender)
        sender_photo = resolve_sender_photo(rendered.sender)

    reply_to_sender = ""
    if rendered.reply_to_from_me:
        reply_to_sender = "You"
    elif rendered.reply_to_sender_id:
        reply_to_sender = resolve_sender_name(rendered.reply_to_sender_id)

    payload = asdict(rendered)
    payload["reply_to_text"] = _resolve_reply_preview_text(rendered)

    return UiMessage(
        **payload,
        sender_name=sender_name,
        sender_photo=sender_photo,
        reply_to_sender=reply_to_sender,
    )


def _template_text_from_context_info(
    text: str,
    context_info: Any,
    *,
    jid_map: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str]]:
    return template_mention_text(text, _context_mentioned_jids(context_info), jid_map=jid_map)


def _hydrated_template(message_content: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not message_content:
        return None
    template = message_content.get("templateMessage")
    if not isinstance(template, dict):
        return None
    hydrated = template.get("hydratedTemplate")
    return hydrated if isinstance(hydrated, dict) else None


def resolve_media_message_content(
    message_content: Optional[Dict[str, Any]],
    field_name: str,
) -> Optional[Dict[str, Any]]:
    if not message_content:
        return None

    media = message_content.get(field_name)
    if isinstance(media, dict):
        return media

    if field_name != "imageMessage":
        return None

    hydrated = _hydrated_template(message_content)
    if not hydrated:
        return None

    title = hydrated.get("Title")
    if not isinstance(title, dict):
        return None

    image = title.get("ImageMessage")
    return image if isinstance(image, dict) else None


def template_message_caption(message_content: Optional[Dict[str, Any]]) -> str:
    hydrated = _hydrated_template(message_content)
    if not hydrated:
        return ""

    parts = []
    for field_name in ("hydratedContentText", "hydratedFooterText"):
        value = str(hydrated.get(field_name) or "").strip()
        if value:
            parts.append(value)
    return "\n\n".join(parts)


def template_message_button(message_content: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    hydrated = _hydrated_template(message_content)
    if not hydrated:
        return "", ""

    buttons = hydrated.get("hydratedButtons")
    if not isinstance(buttons, list):
        return "", ""

    for button in buttons:
        if not isinstance(button, dict):
            continue
        hydrated_button = button.get("HydratedButton")
        if not isinstance(hydrated_button, dict):
            continue
        url_button = hydrated_button.get("UrlButton")
        if not isinstance(url_button, dict):
            continue
        display_text = str(url_button.get("displayText") or "").strip()
        url = str(url_button.get("URL") or url_button.get("url") or "").strip()
        if display_text and url:
            return display_text, url

    return "", ""


def _quoted_message_preview(quoted: Optional[Dict[str, Any]]) -> str:
    if not quoted:
        return ""
    if quoted.get("conversation"):
        return str(quoted["conversation"])
    ext = quoted.get("extendedTextMessage")
    if ext and ext.get("text"):
        return str(ext["text"])
    if quoted.get("imageMessage"):
        return quoted["imageMessage"].get("caption") or "📷 Photo"
    if quoted.get("videoMessage"):
        return quoted["videoMessage"].get("caption") or "🎥 Video"
    if quoted.get("audioMessage"):
        return "🎵 Audio"
    if quoted.get("documentMessage"):
        return quoted["documentMessage"].get("caption") or "📄 Document"
    contact = quoted.get("contactMessage")
    if contact:
        return _contact_preview(contact.get("displayName", ""))
    if quoted.get("stickerMessage"):
        return "🏷️ Sticker"
    template_image = resolve_media_message_content(quoted, "imageMessage")
    if template_image:
        return template_message_caption(quoted) or "📷 Photo"
    return ""


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


def _extract_context_info(content: MessageContent) -> tuple[str, str, str, bool, str, List[str]]:
    ctx = None
    for sub in (
        content.extendedTextMessage,
        content.imageMessage,
        content.videoMessage,
        content.audioMessage,
        content.documentMessage,
        content.contactMessage,
        content.stickerMessage,
    ):
        if sub is not None and getattr(sub, "contextInfo", None) is not None:
            ctx = sub.contextInfo
            break

    if ctx is None or not ctx.stanzaID:
        return "", "", "", False, "", []

    reply_to_sender_raw = str(ctx.participant) if ctx.participant else ""
    reply_to_sender_id = canonicalize_contact_jid(reply_to_sender_raw) if reply_to_sender_raw else ""
    reply_to_text, reply_to_mentioned_jids = quoted_message_template(ctx.quotedMessage)
    return ctx.stanzaID, reply_to_sender_id, reply_to_sender_raw, False, reply_to_text, reply_to_mentioned_jids


def message_event_to_message(evt: MessageEvent, raw: Optional[Dict[str, Any]] = None) -> Optional[Message]:
    info = evt.Info
    content = evt.Message
    raw_info = raw.get("Info", {}) if raw else {}
    raw_content = raw.get("Message", {}) if raw else {}
    chat_id = canonicalize_contact_jid(str(info.Chat or "")) if info.Chat else ""
    template_image = resolve_media_message_content(raw_content, "imageMessage")

    if info.Type == "reaction":
        return None

    is_protocol_only = (
        content.protocolMessage is not None
        and not content.conversation
        and content.extendedTextMessage is None
        and content.imageMessage is None
        and content.videoMessage is None
        and content.audioMessage is None
        and content.documentMessage is None
        and content.contactMessage is None
        and content.stickerMessage is None
    )
    if is_protocol_only:
        return None

    has_supported_content = any(
        (
            content.conversation,
            content.extendedTextMessage is not None,
            content.imageMessage is not None,
            content.videoMessage is not None,
            content.audioMessage is not None,
            content.documentMessage is not None,
            content.contactMessage is not None,
            content.stickerMessage is not None,
            template_image is not None,
        )
    )
    if info.Edit == "1" and not has_supported_content:
        return None

    msg_type = _derive_message_type_from_content(content, raw_content)
    if msg_type is None:
        msg_type = _derive_message_type(info.Type, info.MediaType)
    if msg_type is None:
        return None

    text = ""
    caption = ""
    mentioned_jids: List[str] = []
    duration = ""
    button_text = ""
    button_url = ""

    if content.conversation:
        text = content.conversation
    elif content.extendedTextMessage:
        text, mentioned_jids = _template_text_from_context_info(
            content.extendedTextMessage.text,
            content.extendedTextMessage.contextInfo,
        )

    mimetype = ""
    file_name = ""
    media_path = ""

    if content.imageMessage:
        if content.imageMessage.caption:
            caption, mentioned_jids = _template_text_from_context_info(
                content.imageMessage.caption,
                content.imageMessage.contextInfo,
            )
        mimetype = content.imageMessage.mimetype
    elif template_image:
        caption = template_message_caption(raw_content)
        mimetype = str(template_image.get("mimetype", ""))
        button_text, button_url = template_message_button(raw_content)
    elif content.videoMessage:
        if content.videoMessage.caption:
            caption, mentioned_jids = _template_text_from_context_info(
                content.videoMessage.caption,
                content.videoMessage.contextInfo,
            )
        mimetype = content.videoMessage.mimetype
        secs = content.videoMessage.seconds or 0
        duration = f"{secs // 60}:{secs % 60:02d}"
    elif content.audioMessage:
        mimetype = content.audioMessage.mimetype
        secs = content.audioMessage.seconds or 0
        duration = f"{secs // 60}:{secs % 60:02d}"
    elif content.documentMessage:
        if content.documentMessage.caption:
            caption, mentioned_jids = _template_text_from_context_info(
                content.documentMessage.caption,
                content.documentMessage.contextInfo,
            )
        mimetype = content.documentMessage.mimetype
        file_name = content.documentMessage.fileName
    elif content.contactMessage:
        file_name = content.contactMessage.displayName
        mimetype = "text/x-vcard"
        media_path = persist_contact_vcard(chat_id, info.ID, file_name, content.contactMessage.vcard)
    elif content.stickerMessage:
        mimetype = content.stickerMessage.mimetype

    link_title = ""
    link_description = ""
    link_url = ""
    if msg_type == MessageType.LINK_PREVIEW and content.extendedTextMessage:
        ext = content.extendedTextMessage
        link_title = ext.title
        link_description = ext.description
        link_url = ext.matchedText

    reply_to_id, reply_to_sender_id, reply_to_sender_raw, reply_to_from_me, reply_to_text, reply_to_mentioned_jids = (
        _extract_context_info(content)
    )

    ts = datetime.fromisoformat(info.Timestamp)
    timestamp_unix = int(ts.timestamp())
    timestamp_display = ts.strftime("%H:%M")

    read_receipt = ReadReceipt.SENT if info.IsFromMe else ReadReceipt.NONE

    sender_raw = str(raw_info.get("SenderAlt") or raw_info.get("Sender") or info.Sender or "")
    sender = canonicalize_contact_jid(sender_raw) if sender_raw else ""

    return Message(
        id=info.ID,
        chat_id=chat_id,
        type=msg_type,
        is_outgoing=info.IsFromMe,
        timestamp=timestamp_display,
        timestamp_unix=timestamp_unix,
        read_receipt=read_receipt,
        edited=evt.IsEdit or info.Edit == "1",
        sender=sender,
        sender_raw=sender_raw,
        text=text,
        mentioned_jids=mentioned_jids,
        caption=caption,
        media_path=media_path,
        mimetype=mimetype,
        file_name=file_name,
        duration=duration,
        reply_to_id=reply_to_id,
        reply_to_sender_id=reply_to_sender_id,
        reply_to_sender_raw=reply_to_sender_raw,
        reply_to_from_me=reply_to_from_me,
        reply_to_text=reply_to_text,
        reply_to_mentioned_jids=reply_to_mentioned_jids,
        button_text=button_text,
        button_url=button_url,
        link_title=link_title,
        link_description=link_description,
        link_url=link_url,
    )


def _derive_message_type_from_content(
    content: MessageContent,
    raw_content: Optional[Dict[str, Any]] = None,
) -> Optional[MessageType]:
    if content.imageMessage or resolve_media_message_content(raw_content, "imageMessage"):
        return MessageType.IMAGE
    if content.videoMessage:
        return MessageType.VIDEO
    if content.audioMessage:
        return MessageType.AUDIO
    if content.documentMessage:
        return MessageType.DOCUMENT
    if content.contactMessage:
        return MessageType.CONTACT
    if content.stickerMessage:
        return MessageType.STICKER
    if content.extendedTextMessage:
        ext = content.extendedTextMessage
        if ext.matchedText or ext.title:
            return MessageType.LINK_PREVIEW
        return MessageType.TEXT
    if content.conversation:
        return MessageType.TEXT
    return None


def _derive_message_type(info_type: str, media_type: str) -> Optional[MessageType]:
    if info_type == "text":
        return MessageType.TEXT
    if info_type == "media":
        if media_type == "image":
            return MessageType.IMAGE
        if media_type == "video":
            return MessageType.VIDEO
        if media_type == "audio" or media_type == "ptt":
            return MessageType.AUDIO
        if media_type == "document":
            return MessageType.DOCUMENT
        if media_type == "vcard":
            return MessageType.CONTACT
        if media_type in ("sticker", "user_created_sticker"):
            return MessageType.STICKER
        if media_type == "url":
            return MessageType.LINK_PREVIEW
        return None
    return None


def undecryptable_event_to_message(
    evt: UndecryptableMessageEvent, raw: Optional[Dict[str, Any]] = None
) -> Optional[Message]:
    if not evt.IsUnavailable or evt.UnavailableType != MessageType.VIEW_ONCE:
        return None

    info = evt.Info
    raw_info = raw.get("Info", {}) if raw else {}
    chat_id = canonicalize_contact_jid(str(info.Chat or "")) if info.Chat else ""
    ts = datetime.fromisoformat(info.Timestamp)
    timestamp_unix = int(ts.timestamp())
    timestamp_display = ts.strftime("%H:%M")
    read_receipt = ReadReceipt.SENT if info.IsFromMe else ReadReceipt.NONE

    sender_raw = str(raw_info.get("SenderAlt") or raw_info.get("Sender") or info.Sender or "")
    sender = canonicalize_contact_jid(sender_raw) if sender_raw else ""

    return Message(
        id=info.ID,
        chat_id=chat_id,
        type=MessageType.VIEW_ONCE,
        is_outgoing=info.IsFromMe,
        timestamp=timestamp_display,
        timestamp_unix=timestamp_unix,
        read_receipt=read_receipt,
        sender=sender,
        sender_raw=sender_raw,
        text="",
    )


def _message_preview_data(msg: Message) -> tuple[str, List[str]]:
    if msg.type == MessageType.DELETED:
        return _DELETED_MESSAGE_PREVIEW, []
    if msg.text:
        return msg.text, list(msg.mentioned_jids)
    if msg.caption:
        return msg.caption, list(msg.mentioned_jids)
    if msg.type == MessageType.CONTACT:
        return _contact_preview(msg.file_name), []
    previews = {
        MessageType.IMAGE: "📷 Photo",
        MessageType.VIDEO: "🎥 Video",
        MessageType.AUDIO: "🎵 Audio",
        MessageType.DOCUMENT: "📄 Document",
        MessageType.STICKER: "🏷️ Sticker",
        MessageType.LINK_PREVIEW: "🔗 Link",
    }
    return previews.get(msg.type, msg.type), []


def _message_preview(msg: Message) -> str:
    preview, _ = _message_preview_data(msg)
    return preview


def upsert_chat(msg: Message, info: MessageInfo, *, count_unread: bool = True) -> ChatListItem:
    chat_key = f"chat:{msg.chat_id}"
    with KV() as kv:
        existing = kv.get(chat_key)

    preview, preview_mentioned_jids = _message_preview_data(msg)
    is_group = msg.chat_id.endswith(GROUP_JID_SUFFIX)

    push_name = info.PushName
    direct_push_name = "" if msg.is_outgoing else push_name
    business_name = ""
    if info.VerifiedName and info.VerifiedName.Details:
        business_name = info.VerifiedName.Details.verifiedName
    direct_business_name = "" if msg.is_outgoing else business_name

    if existing is not None:
        chat = ChatListItem(**existing)
        if msg.timestamp_unix >= chat.last_message_timestamp:
            chat.last_message = preview
            chat.last_message_mentioned_jids = preview_mentioned_jids
            chat.last_message_type = str(msg.type)
            chat.date = msg.timestamp
            chat.last_message_timestamp = msg.timestamp_unix
            if msg.is_outgoing:
                chat.read_receipt = msg.read_receipt
            else:
                chat.read_receipt = ReadReceipt.NONE
                if count_unread:
                    chat.unread_count += 1
                    increment_unread_total()
        if not is_group:
            update_chat_name(
                chat,
                msg.timestamp_unix,
                push_name=direct_push_name,
                business_name=direct_business_name,
            )
    else:
        display_name = msg.chat_id
        if not is_group:
            display_name = direct_push_name or direct_business_name or msg.chat_id
        chat = ChatListItem(
            id=msg.chat_id,
            name=display_name,
            photo="",
            last_message=preview,
            date=msg.timestamp,
            last_message_timestamp=msg.timestamp_unix,
            read_receipt=msg.read_receipt if msg.is_outgoing else ReadReceipt.NONE,
            unread_count=0 if msg.is_outgoing or not count_unread else 1,
            is_group=is_group,
            last_message_mentioned_jids=preview_mentioned_jids,
            last_message_type=str(msg.type),
            push_name=direct_push_name if not is_group else "",
            business_name=direct_business_name if not is_group else "",
            name_updated_at=msg.timestamp_unix,
        )
        if not msg.is_outgoing and count_unread:
            increment_unread_total()

    with KV() as kv:
        kv.put(chat_key, asdict(chat))
    remember_chat(chat)
    return chat


@dataclass
class StoredMessage:
    message: Message
    chat: ChatListItem


def _extract_thumbnail(raw: Optional[Dict[str, Any]], message_id: str) -> str:
    if not raw:
        return ""
    msg_content = raw.get("Message", {})
    thumbnail_b64 = ""
    for field_name in ("imageMessage", "videoMessage", "documentMessage", "extendedTextMessage"):
        sub = (
            resolve_media_message_content(msg_content, field_name)
            if field_name == "imageMessage"
            else msg_content.get(field_name)
        )
        if sub and sub.get("JPEGThumbnail"):
            thumbnail_b64 = sub["JPEGThumbnail"]
            break
    if not thumbnail_b64:
        sticker = msg_content.get("stickerMessage")
        if sticker and sticker.get("pngThumbnail"):
            thumbnail_b64 = sticker["pngThumbnail"]
    if not thumbnail_b64:
        return ""
    try:
        data = base64.b64decode(thumbnail_b64)
    except Exception:
        return ""
    thumb_dir = _get_thumbnail_dir()
    os.makedirs(thumb_dir, exist_ok=True)
    ext = "png" if msg_content.get("stickerMessage") else "jpg"
    path = os.path.join(thumb_dir, f"{message_id}.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return "file://" + path


def _find_message_entry(kv: KV, chat_id: str, message_id: str) -> Tuple[str, Dict[str, Any]] | tuple[None, None]:
    return get_message_entry_with_key(kv, chat_id, message_id)


def _get_stored_message(chat_id: str, message_id: str) -> Optional[Message]:
    if not chat_id or not message_id:
        return None

    with KV() as kv:
        _, value = _find_message_entry(kv, chat_id, message_id)
    if value is None:
        return None

    return Message(**{k: v for k, v in value.items() if k in _MESSAGE_FIELDS})


def _resolve_reply_preview_text(message: Message) -> str:
    if not message.reply_to_id:
        return message.reply_to_text

    replied_to = _get_stored_message(message.chat_id, message.reply_to_id)
    if replied_to is None or replied_to.type != MessageType.DELETED:
        return message.reply_to_text

    return _DELETED_MESSAGE_PREVIEW


def _deleted_message_target_id(evt: MessageEvent, raw: Optional[Dict[str, Any]]) -> str:
    target_id = evt.Info.MsgBotInfo.EditTargetID or evt.Info.MsgMetaInfo.TargetID
    if target_id:
        return str(target_id)

    protocol_message = (raw or {}).get("Message", {}).get("protocolMessage") or {}
    if not isinstance(protocol_message, dict):
        return ""

    key = protocol_message.get("key") or {}
    if not isinstance(key, dict):
        return ""

    return str(key.get("ID") or key.get("id") or "")


def _merge_edited_message(existing: Message, updated: Message) -> Message:
    return replace(
        existing,
        type=updated.type,
        edited=True,
        sender=updated.sender or existing.sender,
        sender_raw=updated.sender_raw or existing.sender_raw,
        text=updated.text,
        mentioned_jids=list(updated.mentioned_jids),
        image_source=updated.image_source or existing.image_source,
        caption=updated.caption,
        images=list(updated.images) or list(existing.images),
        duration=updated.duration or existing.duration,
        sticker_source=updated.sticker_source or existing.sticker_source,
        media_path=updated.media_path or existing.media_path,
        thumbnail_path=updated.thumbnail_path or existing.thumbnail_path,
        mimetype=updated.mimetype or existing.mimetype,
        file_name=updated.file_name or existing.file_name,
        reply_to_id=updated.reply_to_id,
        reply_to_sender_id=updated.reply_to_sender_id,
        reply_to_sender_raw=updated.reply_to_sender_raw,
        reply_to_from_me=updated.reply_to_from_me,
        reply_to_text=updated.reply_to_text,
        reply_to_mentioned_jids=list(updated.reply_to_mentioned_jids),
        button_text=updated.button_text,
        button_url=updated.button_url,
        link_title=updated.link_title,
        link_description=updated.link_description,
        link_url=updated.link_url,
    )


def _merge_deleted_message(existing: Message, sender: str, sender_raw: str = "") -> Message:
    return replace(
        existing,
        type=MessageType.DELETED,
        edited=False,
        sender=sender or existing.sender,
        sender_raw=sender_raw or existing.sender_raw,
        text="",
        mentioned_jids=[],
        image_source="",
        caption="",
        images=[],
        duration="",
        sticker_source="",
        media_path="",
        thumbnail_path="",
        mimetype="",
        file_name="",
        send_status="",
        temp_id="",
        button_text="",
        button_url="",
        link_title="",
        link_description="",
        link_url="",
    )


def _update_chat_after_edit(kv: KV, msg: Message, info: MessageInfo) -> ChatListItem:
    chat_key = f"chat:{msg.chat_id}"
    existing = kv.get(chat_key)
    if existing is None:
        return upsert_chat(msg, info, count_unread=False)

    chat = ChatListItem(**existing)
    latest_entries, _ = kv.get_partial_page(f"message:{msg.chat_id}:", page_size=1, reverse=True)
    latest_id = str(latest_entries[0][1].get("id") or "") if latest_entries else ""

    if latest_id == msg.id:
        preview, preview_mentioned_jids = _message_preview_data(msg)
        chat.last_message = preview
        chat.last_message_mentioned_jids = preview_mentioned_jids
        chat.last_message_type = str(msg.type)
        kv.put(chat_key, asdict(chat))
        remember_chat(chat)

    return chat


def store_message(evt: MessageEvent, raw: Optional[Dict[str, Any]] = None) -> Optional[StoredMessage]:
    if evt.Info.Edit == "7":
        target_id = _deleted_message_target_id(evt, raw)
        if not target_id:
            return None

        chat_id = canonicalize_contact_jid(str(evt.Info.Chat or "")) if evt.Info.Chat else ""
        with KV() as kv:
            existing_key, existing_value = _find_message_entry(kv, chat_id, target_id)
            if existing_key is None or existing_value is None:
                return None
            existing_msg = Message(**{k: v for k, v in existing_value.items() if k in _MESSAGE_FIELDS})
            deleted_msg = _merge_deleted_message(
                existing_msg,
                canonicalize_contact_jid(str(evt.Info.Sender or "")),
                str(evt.Info.Sender or ""),
            )
            data = asdict(deleted_msg)
            data["raw"] = raw
            kv.put(existing_key, data)
            chat = _update_chat_after_edit(kv, deleted_msg, evt.Info)
            return StoredMessage(message=deleted_msg, chat=chat)

    msg = message_event_to_message(evt, raw)
    if msg is None:
        return None

    msg.thumbnail_path = _extract_thumbnail(raw, msg.id)

    business_name = ""
    if evt.Info.VerifiedName and evt.Info.VerifiedName.Details:
        business_name = evt.Info.VerifiedName.Details.verifiedName
    if msg.sender and not msg.is_outgoing:
        upsert_identity_chat(
            msg.sender,
            msg.timestamp_unix,
            push_name=evt.Info.PushName,
            business_name=business_name,
        )

    data = asdict(msg)
    data["raw"] = raw
    with KV() as kv:
        if msg.edited:
            existing_key, existing_value = _find_message_entry(kv, msg.chat_id, msg.id)
            if existing_key is None or existing_value is None:
                return None
            existing_msg = Message(**{k: v for k, v in existing_value.items() if k in _MESSAGE_FIELDS})
            msg = _merge_edited_message(existing_msg, msg)
            data = asdict(msg)
            data["raw"] = raw
            kv.put(existing_key, data)
            put_message_index(kv, msg.chat_id, msg.id, existing_key)
            chat = _update_chat_after_edit(kv, msg, evt.Info)
            return StoredMessage(message=msg, chat=chat)

        key = message_storage_key(msg.chat_id, msg.timestamp_unix, msg.id)
        already_stored = kv.get(key) is not None
        kv.put(key, data)
        put_message_index(kv, msg.chat_id, msg.id, key)

    chat = upsert_chat(msg, evt.Info, count_unread=not already_stored)
    return StoredMessage(message=msg, chat=chat)


def store_undecryptable_message(
    evt: UndecryptableMessageEvent, raw: Optional[Dict[str, Any]] = None
) -> Optional[StoredMessage]:
    msg = undecryptable_event_to_message(evt, raw=raw)
    if msg is None:
        return None

    if msg.sender and not msg.is_outgoing:
        upsert_identity_chat(
            msg.sender,
            msg.timestamp_unix,
            push_name=evt.Info.PushName,
        )

    key = message_storage_key(msg.chat_id, msg.timestamp_unix, msg.id)
    data = asdict(msg)
    data["raw"] = raw
    with KV() as kv:
        already_stored = kv.get(key) is not None
        kv.put(key, data)
        put_message_index(kv, msg.chat_id, msg.id, key)

    chat = upsert_chat(msg, evt.Info, count_unread=not already_stored)
    return StoredMessage(message=msg, chat=chat)
