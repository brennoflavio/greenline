import base64
import json
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


def _location_coordinate(value: Any) -> str:
    try:
        float(value)
    except (TypeError, ValueError):
        return ""

    if isinstance(value, str):
        return value.strip()
    return str(value)


def location_coordinates(latitude: Any, longitude: Any) -> str:
    lat = _location_coordinate(latitude)
    lng = _location_coordinate(longitude)
    if not lat or not lng:
        return ""
    return f"{lat}, {lng}"


def location_title(name: str, latitude: Any, longitude: Any) -> str:
    title = str(name or "").strip()
    return title or location_coordinates(latitude, longitude)


def location_link_url(url: str, latitude: Any, longitude: Any) -> str:
    location_url = str(url or "").strip()
    if location_url:
        return location_url

    coords = location_coordinates(latitude, longitude)
    if not coords:
        return ""
    return f"geo:{coords.replace(', ', ',')}"


def location_preview(title: str, detail: str) -> str:
    preview_title = str(title or "").strip()
    if preview_title:
        return f"📍 {preview_title}"

    preview_detail = str(detail or "").strip()
    if preview_detail:
        return f"📍 {preview_detail}"

    return "📍 Location"


def _location_value(source: Any, key: str) -> Any:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _first_location_value(key: str, *sources: Any) -> Any:
    for source in sources:
        value = _location_value(source, key)
        if value not in (None, ""):
            return value
    return None


def normalized_location_fields(location: Any = None, live_location: Any = None) -> Tuple[str, str, str]:
    latitude = _first_location_value("degreesLatitude", live_location, location)
    longitude = _first_location_value("degreesLongitude", live_location, location)
    is_live = live_location is not None or bool(_location_value(location, "isLive"))

    if is_live:
        title = location_title("", latitude, longitude)
        caption = str(
            _first_location_value("caption", live_location, location)
            or _first_location_value("address", location)
            or ""
        ).strip()
        url = str(
            _first_location_value("URL", live_location, location)
            or _first_location_value("url", live_location, location)
            or ""
        ).strip()
        return title, caption, location_link_url(url, latitude, longitude)

    title = location_title(str(_first_location_value("name", location) or ""), latitude, longitude)
    caption = str(_first_location_value("address", location) or "").strip()
    url = str(_first_location_value("URL", location) or _first_location_value("url", location) or "").strip()
    return title, caption, location_link_url(url, latitude, longitude)


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


def _interactive_template(message_content: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not message_content:
        return None
    template = message_content.get("templateMessage")
    if not isinstance(template, dict):
        return None
    fmt = template.get("Format")
    if not isinstance(fmt, dict):
        return None
    interactive = fmt.get("InteractiveMessageTemplate")
    return interactive if isinstance(interactive, dict) else None


def _interactive_native_flow(message_content: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    interactive = _interactive_template(message_content)
    if not interactive:
        return None
    message = interactive.get("InteractiveMessage")
    if not isinstance(message, dict):
        return None
    native_flow = message.get("NativeFlowMessage")
    return native_flow if isinstance(native_flow, dict) else None


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


def template_message_text(message_content: Optional[Dict[str, Any]]) -> str:
    hydrated = _hydrated_template(message_content)
    if hydrated:
        parts = []
        for field_name in ("hydratedContentText", "hydratedFooterText"):
            value = str(hydrated.get(field_name) or "").strip()
            if value:
                parts.append(value)
        if parts:
            return "\n\n".join(parts)

    interactive = _interactive_template(message_content)
    if not interactive:
        return ""

    parts = []
    for section_name in ("body", "footer"):
        section = interactive.get(section_name)
        if not isinstance(section, dict):
            continue
        value = str(section.get("text") or "").strip()
        if value:
            parts.append(value)
    return "\n\n".join(parts)


def template_message_caption(message_content: Optional[Dict[str, Any]]) -> str:
    return template_message_text(message_content)


def template_message_button(message_content: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    hydrated = _hydrated_template(message_content)
    if hydrated:
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

    native_flow = _interactive_native_flow(message_content)
    if not native_flow:
        return "", ""

    buttons = native_flow.get("buttons")
    if not isinstance(buttons, list):
        return "", ""

    for button in buttons:
        if not isinstance(button, dict):
            continue
        raw_params = button.get("buttonParamsJSON")
        if isinstance(raw_params, str):
            try:
                params = json.loads(raw_params)
            except Exception:
                continue
        elif isinstance(raw_params, dict):
            params = raw_params
        else:
            continue

        display_text = str(params.get("display_text") or params.get("displayText") or "").strip()
        url = str(params.get("landing_page_url") or params.get("url") or params.get("URL") or "").strip()
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
    location = quoted.get("locationMessage")
    live_location = quoted.get("liveLocationMessage")
    if isinstance(location, dict) or isinstance(live_location, dict):
        title, detail, _ = normalized_location_fields(
            location if isinstance(location, dict) else None,
            live_location if isinstance(live_location, dict) else None,
        )
        return location_preview(title, detail)
    if quoted.get("stickerMessage"):
        return "🏷️ Sticker"
    template_image = resolve_media_message_content(quoted, "imageMessage")
    if template_image:
        return template_message_caption(quoted) or "📷 Photo"
    return ""


def extract_thumbnail_from_message_content(message_content: Optional[Dict[str, Any]], message_id: str) -> str:
    if not message_content:
        return ""
    thumbnail_b64 = ""
    for field_name in ("imageMessage", "videoMessage", "documentMessage", "extendedTextMessage"):
        sub = (
            resolve_media_message_content(message_content, field_name)
            if field_name == "imageMessage"
            else message_content.get(field_name)
        )
        if sub and sub.get("JPEGThumbnail"):
            thumbnail_b64 = sub["JPEGThumbnail"]
            break
    if not thumbnail_b64:
        sticker = message_content.get("stickerMessage")
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
    ext = "png" if message_content.get("stickerMessage") else "jpg"
    path = os.path.join(thumb_dir, f"{message_id}.{ext}")
    with open(path, "wb") as file_handle:
        file_handle.write(data)
    return "file://" + path
