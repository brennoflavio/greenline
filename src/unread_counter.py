from ut_components.kv import KV

UNREAD_TOTAL_KEY = "unread_total"


def get_unread_total() -> int:
    with KV() as kv:
        return int(kv.get(UNREAD_TOTAL_KEY, default=0))


def increment_unread_total(amount: int = 1) -> int:
    with KV() as kv:
        total = int(kv.get(UNREAD_TOTAL_KEY, default=0))
        total = max(0, total + amount)
        kv.put(UNREAD_TOTAL_KEY, total)
    return total


def decrement_unread_total(amount: int = 1) -> int:
    return increment_unread_total(-amount)


def reconcile_unread_total() -> int:
    with KV() as kv:
        entries = kv.get_partial("chat:")
        total = sum(int(v.get("unread_count", 0)) for _, v in entries)
        kv.put(UNREAD_TOTAL_KEY, total)
    return total
