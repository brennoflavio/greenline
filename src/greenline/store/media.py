import base64
import os
from typing import Any, Dict, Optional, Tuple

from ut_components.config import get_cache_path


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
    with open(file_path, "w", encoding="utf-8") as file_handle:
        file_handle.write(vcard)
    return "file://" + file_path


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
    with open(path, "wb") as file_handle:
        file_handle.write(data)
    return "file://" + path
