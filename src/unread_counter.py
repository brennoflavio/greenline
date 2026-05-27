from typing import cast

from greenline.contracts.kv import GreenlineKV
from greenline.store.records import UnreadTotalRecord
from models import ChatListItem

UNREAD_TOTAL_KEY = "unread_total"


def get_unread_total() -> int:
    with GreenlineKV() as kv:
        return kv.get_record(UNREAD_TOTAL_KEY, default=UnreadTotalRecord(0)).value


def increment_unread_total(amount: int = 1) -> int:
    with GreenlineKV() as kv:
        total = kv.get_record(UNREAD_TOTAL_KEY, default=UnreadTotalRecord(0)).value
        total = max(0, total + amount)
        kv.put_record(UNREAD_TOTAL_KEY, UnreadTotalRecord(total))
    return total


def decrement_unread_total(amount: int = 1) -> int:
    return increment_unread_total(-amount)


def reconcile_unread_total() -> int:
    with GreenlineKV() as kv:
        entries = kv.get_partial_records("chat:")
        total = sum(cast(ChatListItem, chat).unread_count for _, chat in entries)
        kv.put_record(UNREAD_TOTAL_KEY, UnreadTotalRecord(total))
    return total
