from dataclasses import asdict
from typing import Any, Dict, Optional

from constants import GROUP_JID_SUFFIX, WHATSAPP_JID_SUFFIX
from greenline.contracts.daemon import DaemonClientProtocol, daemon_client
from greenline.contracts.kv import GreenlineKV
from greenline.store.records import LidMapRecord, OwnJIDRecord
from models import ChatListItem, ReadReceipt

_CHAT_RUNTIME_CACHE: Dict[str, Dict[str, Any]] = {}
_OWN_JID = ""
_STATUS_BROADCAST_JID = "status@broadcast"
_NEWSLETTER_JID_SUFFIX = "@newsletter"
_LID_JID_SUFFIX = "@lid"


def clear_chat_runtime_cache() -> None:
    global _OWN_JID
    _CHAT_RUNTIME_CACHE.clear()
    _OWN_JID = ""


def remember_chat(chat: ChatListItem) -> None:
    _CHAT_RUNTIME_CACHE[chat.id] = asdict(chat)


def remember_own_jid(jid: str) -> str:
    global _OWN_JID
    normalized = canonicalize_contact_jid(jid)
    if not normalized:
        return ""
    _OWN_JID = normalized
    with GreenlineKV() as kv:
        kv.put_record("self.jid", OwnJIDRecord(normalized))
    return normalized


def get_own_jid() -> str:
    global _OWN_JID
    if _OWN_JID:
        return _OWN_JID
    with GreenlineKV() as kv:
        record = kv.get_record("self.jid")
    if isinstance(record, OwnJIDRecord):
        _OWN_JID = record.value
    return _OWN_JID


def _get_chat_data(chat_jid: str) -> Optional[Dict[str, Any]]:
    if not chat_jid:
        return None

    cached = _CHAT_RUNTIME_CACHE.get(chat_jid)
    if cached is not None:
        return cached

    with GreenlineKV() as kv:
        chat = kv.get_record(f"chat:{chat_jid}")
    if chat is None:
        return None

    cached_data = asdict(chat)
    _CHAT_RUNTIME_CACHE[chat_jid] = cached_data
    return cached_data


def jid_display_name(jid: str) -> str:
    user = str(jid or "")
    for suffix in (WHATSAPP_JID_SUFFIX, GROUP_JID_SUFFIX):
        if user.endswith(suffix):
            return user[: -len(suffix)]
    return user


def preferred_contact_name(
    jid: str,
    *,
    full_name: str = "",
    push_name: str = "",
    business_name: str = "",
    fallback: str = "",
) -> str:
    if jid and jid == get_own_jid():
        return push_name or full_name or business_name or fallback or jid_display_name(jid)
    return full_name or push_name or business_name or fallback or jid_display_name(jid)


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
        chat.name = preferred_contact_name(
            chat.id,
            full_name=chat.full_name,
            push_name=chat.push_name,
            business_name=chat.business_name,
            fallback=chat.name,
        )
    return changed


def resolve_chat_name(chat_jid: str, fallback: str = "") -> str:
    data = _get_chat_data(chat_jid)
    if data is not None:
        name = str(data.get("name", "") or "").strip()
        if name:
            return name
    fallback_name = str(fallback or "").strip()
    if fallback_name:
        return fallback_name
    return jid_display_name(chat_jid)


def is_jid_fallback_name(name: str, jid: str) -> bool:
    stripped_name = str(name or "").strip()
    return stripped_name == str(jid or "").strip() or stripped_name == jid_display_name(jid)


def resolve_sender_name(sender_jid: str, push_name: str = "") -> str:
    data = _get_chat_data(sender_jid)
    if data is not None:
        name = preferred_contact_name(
            sender_jid,
            full_name=str(data.get("full_name", "") or ""),
            push_name=str(data.get("push_name", "") or ""),
            business_name=str(data.get("business_name", "") or ""),
            fallback=str(data.get("name", "") or ""),
        )
        if name and name != sender_jid:
            return name
    return preferred_contact_name(sender_jid, push_name=push_name)


def resolve_sender_photo(sender_jid: str) -> str:
    data = _get_chat_data(sender_jid)
    if data is None:
        return ""
    return str(data.get("photo", "") or "")


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


def _get_lid_map_record(kv: Any, key: str) -> LidMapRecord | None:
    typed_kv = kv if isinstance(kv, GreenlineKV) else GreenlineKV(kv)
    record = typed_kv.get_record(key)
    return record if isinstance(record, LidMapRecord) else None


def canonicalize_contact_jid(
    jid: str,
    *,
    jid_map: Optional[Dict[str, str]] = None,
    kv: Optional[Any] = None,
    rpc: Optional[DaemonClientProtocol] = None,
) -> str:
    if not _is_contact_identity_jid(jid):
        return jid

    stripped_jid = _strip_device_suffix(str(jid))
    resolved: str | None = None
    if jid_map is not None:
        resolved = jid_map.get(stripped_jid)
        if resolved is None:
            resolved = jid_map.get(jid)

    if resolved is None and stripped_jid.endswith(_LID_JID_SUFFIX):
        cached = None
        if kv is None:
            with GreenlineKV() as lid_kv:
                cached = lid_kv.get_record(f"lid_map:{stripped_jid}")
                if cached is None:
                    cached = lid_kv.get_record(f"lid_map:{jid}")
        else:
            cached = _get_lid_map_record(kv, f"lid_map:{stripped_jid}")
            if cached is None:
                cached = _get_lid_map_record(kv, f"lid_map:{jid}")
        if cached is not None:
            resolved = cached.value

    if resolved is None and stripped_jid.endswith(_LID_JID_SUFFIX):
        try:
            reply = rpc.ensure_jid(stripped_jid) if rpc is not None else daemon_client().ensure_jid(stripped_jid)
            resolved = reply.JID
        except Exception:
            resolved = stripped_jid

    return _strip_device_suffix(str(resolved if resolved is not None else stripped_jid))


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
    with GreenlineKV() as kv:
        chat = kv.get_record(chat_key)
        if chat is not None:
            changed = update_chat_name(
                chat,
                timestamp,
                full_name=full_name,
                push_name=push_name,
                business_name=business_name,
            )
            if changed:
                kv.put_record(chat_key, chat)
        else:
            display_name = preferred_contact_name(
                chat_id,
                full_name=full_name,
                push_name=push_name,
                business_name=business_name,
            )
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
            kv.put_record(chat_key, chat)

    remember_chat(chat)
