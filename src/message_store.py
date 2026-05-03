import base64
import os
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from constants import GROUP_JID_SUFFIX, WHATSAPP_JID_SUFFIX
from models import ChatListItem, Message, MessageType, ReadReceipt
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
    with KV() as kv:
        data = kv.get(f"chat:{sender_jid}")
    if data is not None:
        name = str(data.get("name", ""))
        if name and name != sender_jid:
            return name
    if push_name:
        return push_name
    return sender_jid.replace(WHATSAPP_JID_SUFFIX, "")


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

    normalized: List[str] = []
    rpc: Optional[DaemonRPC] = None
    with KV() as kv:
        for jid in mentioned_jids:
            resolved = jid_map.get(jid) if jid_map is not None else None
            if not resolved and "@lid" in jid:
                cached = kv.get(f"lid_map:{jid}")
                if cached:
                    resolved = str(cached)
            if not resolved:
                try:
                    if rpc is None:
                        rpc = DaemonRPC()
                    resolved = rpc.ensure_jid(jid)
                except Exception:
                    resolved = jid
            normalized.append(str(resolved or jid))
    return normalized


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


def _extract_context_info(content: MessageContent) -> tuple[str, str, str, List[str]]:
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
        return "", "", "", []

    reply_to_id = ctx.stanzaID
    reply_to_sender = resolve_sender_name(ctx.participant) if ctx.participant else ""
    reply_to_text, reply_to_mentioned_jids = quoted_message_template(ctx.quotedMessage)
    return reply_to_id, reply_to_sender, reply_to_text, reply_to_mentioned_jids


def message_event_to_message(evt: MessageEvent) -> Optional[Message]:
    info = evt.Info
    content = evt.Message

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

    msg_type = _derive_message_type(info.Type, info.MediaType)
    if msg_type is None:
        return None

    if msg_type == MessageType.TEXT and content.extendedTextMessage:
        ext = content.extendedTextMessage
        if ext.matchedText or ext.title:
            msg_type = MessageType.LINK_PREVIEW

    text = ""
    caption = ""
    mentioned_jids: List[str] = []
    duration = ""

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
        media_path = persist_contact_vcard(info.Chat, info.ID, file_name, content.contactMessage.vcard)
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

    reply_to_id, reply_to_sender, reply_to_text, reply_to_mentioned_jids = _extract_context_info(content)

    ts = datetime.fromisoformat(info.Timestamp)
    timestamp_unix = int(ts.timestamp())
    timestamp_display = ts.strftime("%H:%M")

    read_receipt = ReadReceipt.SENT if info.IsFromMe else ReadReceipt.NONE

    sender_name = ""
    if not info.IsFromMe and info.Sender:
        sender_name = resolve_sender_name(info.Sender, info.PushName)

    return Message(
        id=info.ID,
        chat_id=info.Chat,
        type=msg_type,
        is_outgoing=info.IsFromMe,
        timestamp=timestamp_display,
        timestamp_unix=timestamp_unix,
        read_receipt=read_receipt,
        sender=info.Sender,
        sender_name=sender_name,
        text=text,
        mentioned_jids=mentioned_jids,
        caption=caption,
        media_path=media_path,
        mimetype=mimetype,
        file_name=file_name,
        duration=duration,
        reply_to_id=reply_to_id,
        reply_to_sender=reply_to_sender,
        reply_to_text=reply_to_text,
        reply_to_mentioned_jids=reply_to_mentioned_jids,
        link_title=link_title,
        link_description=link_description,
        link_url=link_url,
    )


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


def undecryptable_event_to_message(evt: UndecryptableMessageEvent) -> Optional[Message]:
    if not evt.IsUnavailable or evt.UnavailableType != MessageType.VIEW_ONCE:
        return None

    info = evt.Info
    ts = datetime.fromisoformat(info.Timestamp)
    timestamp_unix = int(ts.timestamp())
    timestamp_display = ts.strftime("%H:%M")
    read_receipt = ReadReceipt.SENT if info.IsFromMe else ReadReceipt.NONE

    sender_name = ""
    if not info.IsFromMe and info.Sender:
        sender_name = resolve_sender_name(info.Sender, info.PushName)

    return Message(
        id=info.ID,
        chat_id=info.Chat,
        type=MessageType.VIEW_ONCE,
        is_outgoing=info.IsFromMe,
        timestamp=timestamp_display,
        timestamp_unix=timestamp_unix,
        read_receipt=read_receipt,
        sender=info.Sender,
        sender_name=sender_name,
        text="",
    )


def _message_preview_data(msg: Message) -> tuple[str, List[str]]:
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
    business_name = ""
    if info.VerifiedName and info.VerifiedName.Details:
        business_name = info.VerifiedName.Details.verifiedName

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
                push_name=push_name,
                business_name=business_name,
            )
    else:
        display_name = msg.chat_id
        if not is_group:
            display_name = push_name or business_name or msg.chat_id
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
            push_name=push_name if not is_group else "",
            business_name=business_name if not is_group else "",
            name_updated_at=msg.timestamp_unix,
        )
        if not msg.is_outgoing and count_unread:
            increment_unread_total()

    with KV() as kv:
        kv.put(chat_key, asdict(chat))
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
        sub = msg_content.get(field_name)
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


def store_message(evt: MessageEvent, raw: Optional[Dict[str, Any]] = None) -> Optional[StoredMessage]:
    msg = message_event_to_message(evt)
    if msg is None:
        return None

    msg.thumbnail_path = _extract_thumbnail(raw, msg.id)

    key = f"message:{msg.chat_id}:{msg.timestamp_unix}:{msg.id}"
    data = asdict(msg)
    data["raw"] = raw
    with KV() as kv:
        already_stored = kv.get(key) is not None
        kv.put(key, data)

    chat = upsert_chat(msg, evt.Info, count_unread=not already_stored)
    return StoredMessage(message=msg, chat=chat)


def store_undecryptable_message(
    evt: UndecryptableMessageEvent, raw: Optional[Dict[str, Any]] = None
) -> Optional[StoredMessage]:
    msg = undecryptable_event_to_message(evt)
    if msg is None:
        return None

    key = f"message:{msg.chat_id}:{msg.timestamp_unix}:{msg.id}"
    data = asdict(msg)
    data["raw"] = raw
    with KV() as kv:
        already_stored = kv.get(key) is not None
        kv.put(key, data)

    chat = upsert_chat(msg, evt.Info, count_unread=not already_stored)
    return StoredMessage(message=msg, chat=chat)
