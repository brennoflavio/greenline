from dataclasses import asdict
from typing import Any, Dict, Optional

from constants import GROUP_JID_SUFFIX, WHATSAPP_JID_SUFFIX
from greenline.contracts.daemon import DaemonClientProtocol, daemon_client
from greenline.contracts.kv import GreenlineKV
from greenline.store.records import LidMapRecord
from models import ChatListItem, ReadReceipt

_CHAT_RUNTIME_CACHE: Dict[str, Dict[str, Any]] = {}
_STATUS_BROADCAST_JID = "status@broadcast"
_NEWSLETTER_JID_SUFFIX = "@newsletter"
_LID_JID_SUFFIX = "@lid"


def clear_chat_runtime_cache() -> None:
    _CHAT_RUNTIME_CACHE.clear()


def remember_chat(chat: ChatListItem) -> None:
    _CHAT_RUNTIME_CACHE[chat.id] = asdict(chat)


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
            kv.put_record(chat_key, chat)

    remember_chat(chat)
