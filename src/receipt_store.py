from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple, cast

from greenline.contracts.kv import GreenlineKV
from greenline.store.records import record_payload_without_none
from greenline.store.repository import get_message_entry_with_key
from models import ChatListItem, ReadReceipt
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

    with GreenlineKV() as kv:
        for message_id in message_ids:
            key, record = get_message_entry_with_key(kv, chat_id, message_id)
            if key is None or record is None:
                continue
            current = record.read_receipt
            if not _is_upgrade(current, new_status):
                continue
            updated_record = replace(record, read_receipt=new_status)
            kv.put_record(key, updated_record)
            updated_messages.append(record_payload_without_none(updated_record))

    return updated_messages


def _update_chat(chat_id: str, new_status: ReadReceipt, is_from_me: bool) -> Optional[ChatListItem]:
    chat_key = f"chat:{chat_id}"
    with GreenlineKV() as kv:
        chat = cast(ChatListItem | None, kv.get_record(chat_key))
        if chat is None:
            return None

        changed = False

        if not is_from_me:
            current = chat.read_receipt
            if current != ReadReceipt.NONE and _is_upgrade(current, new_status):
                chat.read_receipt = new_status
                changed = True

        if new_status == ReadReceipt.READ and chat.unread_count > 0:
            from unread_counter import decrement_unread_total

            decrement_unread_total(chat.unread_count)
            chat.unread_count = 0
            changed = True

        if not changed:
            return None

        kv.put_record(chat_key, chat)

    return chat
