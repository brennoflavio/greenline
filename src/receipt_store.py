from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from models import ChatListItem, ReadReceipt
from ut_components.kv import KV
from whatsmeow_types import ReceiptEvent

RECEIPT_ORDER = {
    ReadReceipt.NONE: 0,
    ReadReceipt.SENT: 1,
    ReadReceipt.DELIVERED: 2,
    ReadReceipt.READ: 3,
}

RECEIPT_TYPE_MAP = {
    "": ReadReceipt.DELIVERED,
    "read": ReadReceipt.READ,
    "read-self": ReadReceipt.READ,
}


def _is_upgrade(current: ReadReceipt, new: ReadReceipt) -> bool:
    return RECEIPT_ORDER.get(new, 0) > RECEIPT_ORDER.get(current, 0)


def process_receipt(
    evt: ReceiptEvent,
) -> Tuple[List[Dict[str, Any]], Optional[ChatListItem]]:
    chat_id = evt.Chat
    message_ids = set(evt.MessageIDs or [])

    new_status = RECEIPT_TYPE_MAP.get(evt.Type)
    if new_status is None:
        return [], None

    updated_messages = _update_messages(chat_id, message_ids, new_status)
    updated_chat = _update_chat(chat_id, new_status, evt.IsFromMe)

    return updated_messages, updated_chat


def _update_messages(chat_id: str, message_ids: set[str], new_status: ReadReceipt) -> List[Dict[str, Any]]:
    updated_messages: List[Dict[str, Any]] = []

    with KV() as kv:
        entries = kv.get_partial(f"message:{chat_id}:")
        for key, value in entries:
            if value["id"] not in message_ids:
                continue
            current = ReadReceipt(value.get("read_receipt", ""))
            if not _is_upgrade(current, new_status):
                continue
            value["read_receipt"] = new_status.value
            kv.put(key, value)
            updated_messages.append(value)

    return updated_messages


def _update_chat(chat_id: str, new_status: ReadReceipt, is_from_me: bool) -> Optional[ChatListItem]:
    chat_key = f"chat:{chat_id}"
    with KV() as kv:
        existing = kv.get(chat_key)
        if existing is None:
            return None

        chat = ChatListItem(**existing)
        changed = False

        if not is_from_me:
            current = chat.read_receipt
            if current != ReadReceipt.NONE and _is_upgrade(current, new_status):
                chat.read_receipt = new_status
                changed = True

        if new_status == ReadReceipt.READ and chat.unread_count > 0:
            chat.unread_count = 0
            changed = True

        if not changed:
            return None

        kv.put(chat_key, asdict(chat))

    return chat
