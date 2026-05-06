import json
import time
from typing import Any, Dict, Optional, cast
from urllib.parse import quote

from dacite import from_dict

from constants import GROUP_JID_SUFFIX
from message_store import (
    render_mention_text,
    resolve_sender_name,
    template_mention_text,
)
from rpc import DaemonRPC
from ut_components.kv import KV
from ut_components.notification import Notification
from whatsmeow_types import CallOfferEvent, MessageEvent, UndecryptableMessageEvent

MAX_BODY_LEN = 100
VIEW_ONCE_BODY = "View-once message — open WhatsApp on your primary phone"


def build_postal_output(raw_payload: str) -> Dict[str, Any]:
    try:
        envelope = json.loads(raw_payload or "{}")
    except Exception:
        return {}

    if not isinstance(envelope, dict):
        return {}
    if "notification" in envelope and "event_type" not in envelope:
        return envelope

    event_type = str(envelope.get("event_type", ""))
    event = envelope.get("event") or {}
    if not isinstance(event, dict):
        return {}

    rpc = DaemonRPC()
    if _notifications_suppressed(rpc, envelope):
        return {}

    notification = _build_notification(rpc, event_type, event, envelope)
    if notification is None:
        return {}

    tag = str(notification.get("tag") or "")
    if tag:
        try:
            rpc.clear_chat_notifications([tag])
        except Exception:
            pass

    return {"notification": notification}


def _build_notification(
    rpc: DaemonRPC,
    event_type: str,
    event: Dict[str, Any],
    envelope: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if event_type == "Message":
        return _build_message_notification(rpc, event, envelope)
    if event_type == "UndecryptableMessage":
        return _build_undecryptable_notification(rpc, event, envelope)
    if event_type == "CallOffer":
        return _build_call_notification(event, envelope)
    return None


def _build_message_notification(
    rpc: DaemonRPC,
    event: Dict[str, Any],
    envelope: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    evt = from_dict(data_class=MessageEvent, data=event)
    chat_jid = str(envelope.get("chat_jid") or evt.Info.Chat)
    if chat_jid and _is_muted(rpc, chat_jid, envelope):
        return None

    body = _extract_message_body(event)
    if not body:
        return None

    summary, rendered_body = _message_summary_and_body(
        chat_jid,
        evt.Info.Sender,
        evt.Info.PushName,
        body,
        str(envelope.get("chat_name") or ""),
    )
    return _notification(summary, rendered_body, envelope, chat_jid)


def _build_undecryptable_notification(
    rpc: DaemonRPC,
    event: Dict[str, Any],
    envelope: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    evt = from_dict(data_class=UndecryptableMessageEvent, data=event)
    if not evt.IsUnavailable or evt.UnavailableType != "view_once":
        return None

    chat_jid = str(envelope.get("chat_jid") or evt.Info.Chat)
    if chat_jid and _is_muted(rpc, chat_jid, envelope):
        return None

    summary, body = _message_summary_and_body(
        chat_jid,
        evt.Info.Sender,
        evt.Info.PushName,
        VIEW_ONCE_BODY,
        str(envelope.get("chat_name") or ""),
    )
    return _notification(summary, body, envelope, chat_jid)


def _build_call_notification(
    event: Dict[str, Any],
    envelope: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    evt = from_dict(data_class=CallOfferEvent, data=event)
    chat_jid = str(envelope.get("chat_jid") or evt.CallCreator or evt.From)
    summary = resolve_sender_name(chat_jid) if chat_jid else "Incoming call"
    body = "Incoming audio call — answer on your primary phone"
    if _contains_video_tag(event.get("Data")):
        body = "Incoming video call — answer on your primary phone"
    return _notification(summary, body, envelope, chat_jid)


def _notification(summary: str, body: str, envelope: Dict[str, Any], chat_jid: str) -> Optional[Dict[str, Any]]:
    summary = str(summary or "").strip()
    if not summary:
        return None

    body = _truncate_body(body)
    icon = str(envelope.get("icon") or "") or "message"
    notification = cast(
        Dict[str, Any],
        Notification(
            icon=icon,
            summary=summary,
            body=body,
            popup=True,
            persist=True,
            vibrate=True,
            sound=True,
        ).dict()["notification"],
    )

    card = notification["card"]
    if not body:
        card.pop("body", None)
    if chat_jid:
        card["actions"] = [f"greenline://chat/{quote(chat_jid, safe='')}"]
        notification["tag"] = chat_jid
    return notification


def _message_summary_and_body(
    chat_jid: str,
    sender_jid: str,
    push_name: str,
    body: str,
    chat_name: str = "",
) -> tuple[str, str]:
    sender_name = resolve_sender_name(sender_jid, push_name) if sender_jid else _fallback_name(chat_jid)
    if chat_jid.endswith(GROUP_JID_SUFFIX):
        summary = chat_name or _chat_name(chat_jid)
        if sender_name:
            body = f"{sender_name}: {body}"
        return summary, body
    return sender_name, body


def _chat_name(chat_jid: str) -> str:
    with KV() as kv:
        data = kv.get(f"chat:{chat_jid}")
    if data is not None:
        name = str(data.get("name", "")).strip()
        if name:
            return name
    return _fallback_name(chat_jid)


def _fallback_name(jid: str) -> str:
    user = str(jid or "")
    for suffix in ("@s.whatsapp.net", GROUP_JID_SUFFIX):
        if user.endswith(suffix):
            return user[: -len(suffix)]
    return user


def _extract_message_body(event: Dict[str, Any]) -> str:
    message = event.get("Message") or {}
    if not isinstance(message, dict):
        return ""

    conversation = str(message.get("conversation") or "")
    if conversation:
        return conversation

    extended = message.get("extendedTextMessage")
    if isinstance(extended, dict):
        text = _mention_safe_text(extended.get("text"), extended.get("contextInfo"))
        if text:
            return text

    image = message.get("imageMessage")
    if isinstance(image, dict):
        caption = _mention_safe_text(image.get("caption"), image.get("contextInfo"))
        if caption:
            return f"📷 {caption}"
        return "📷 Photo"

    video = message.get("videoMessage")
    if isinstance(video, dict):
        caption = _mention_safe_text(video.get("caption"), video.get("contextInfo"))
        if caption:
            return f"🎥 {caption}"
        return "🎥 Video"

    if isinstance(message.get("audioMessage"), dict):
        return "🎵 Audio"

    document = message.get("documentMessage")
    if isinstance(document, dict):
        caption = _mention_safe_text(document.get("caption"), document.get("contextInfo"))
        if caption:
            return f"📄 {caption}"
        return "📄 Document"

    if isinstance(message.get("stickerMessage"), dict):
        return "🏷️ Sticker"

    contact = message.get("contactMessage")
    if isinstance(contact, dict):
        display_name = str(contact.get("displayName") or "").strip()
        return f"👤 {display_name}" if display_name else "👤 Contact"

    if isinstance(message.get("locationMessage"), dict):
        return "📍 Location"

    return ""


def _mention_safe_text(text: Any, context_info: Any) -> str:
    raw_text = str(text or "")
    if not raw_text:
        return ""

    mentioned_jids = None
    if isinstance(context_info, dict):
        mentioned_jids = context_info.get("mentionedJID")

    templated_text, normalized_jids = template_mention_text(raw_text, mentioned_jids or [])
    return render_mention_text(templated_text, normalized_jids)


def _contains_video_tag(data: Any) -> bool:
    if isinstance(data, dict):
        tag = data.get("Tag") or data.get("tag")
        if tag == "video":
            return True
        for value in data.values():
            if _contains_video_tag(value):
                return True
        return False
    if isinstance(data, list):
        return any(_contains_video_tag(item) for item in data)
    return False


def _truncate_body(body: str) -> str:
    body = str(body or "")
    if len(body) <= MAX_BODY_LEN:
        return body
    return body[:MAX_BODY_LEN] + "…"


def _notifications_suppressed(rpc: DaemonRPC, envelope: Dict[str, Any]) -> bool:
    if "suppressed" in envelope:
        return bool(envelope.get("suppressed"))
    try:
        return rpc.get_notifications_suppressed().Suppressed
    except Exception:
        return False


def _is_muted(rpc: DaemonRPC, chat_jid: str, envelope: Dict[str, Any]) -> bool:
    if "muted" in envelope:
        return bool(envelope.get("muted"))
    try:
        muted_until = rpc.get_chat_settings(chat_jid).MutedUntil
    except Exception:
        return False
    if muted_until == -1:
        return True
    return muted_until > int(time.time() * 1000)
