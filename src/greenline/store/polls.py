from __future__ import annotations

import hashlib

from typing import Any

from greenline.contracts.kv import GreenlineKV
from greenline.store.records import PollVoteRecord
from greenline.store.repository import get_message_entry_with_key
from greenline.store.records import (
    message_from_record,
    updated_stored_message_record,
)


def poll_vote_key(chat_id: str, poll_id: str, sender_jid: str) -> str:
    return f"poll_vote:{chat_id}:{poll_id}:{sender_jid}"


def poll_vote_prefix(chat_id: str, poll_id: str) -> str:
    return f"poll_vote:{chat_id}:{poll_id}:"


def list_poll_votes(
    kv: Any,
    chat_id: str,
    poll_id: str,
) -> list[PollVoteRecord]:
    if not chat_id or not poll_id:
        return []

    typed_kv = kv if isinstance(kv, GreenlineKV) else GreenlineKV(kv)
    return [
        record
        for _, record in typed_kv.get_partial_records(
            poll_vote_prefix(chat_id, poll_id)
        )
    ]


def put_poll_vote(
    kv: Any,
    chat_id: str,
    poll_id: str,
    sender_jid: str,
    selected_options: list[str],
    timestamp_ms: int,
) -> bool:
    if not chat_id or not poll_id or not sender_jid:
        return False

    typed_kv = kv if isinstance(kv, GreenlineKV) else GreenlineKV(kv)
    key = poll_vote_key(chat_id, poll_id, sender_jid)
    previous = typed_kv.get_record(key)

    if previous is not None and timestamp_ms <= previous.timestamp_ms:
        return False

    typed_kv.put_record(
        key,
        PollVoteRecord(
            chat_id=chat_id,
            poll_id=poll_id,
            sender_jid=sender_jid,
            selected_options=list(selected_options),
            timestamp_ms=timestamp_ms,
        ),
    )
    return True


def count_poll_votes(
    votes: list[PollVoteRecord],
    options: list[str],
) -> list[int]:
    """Count each voter's latest selections for each poll option."""
    hashes = [
        hashlib.sha256(option.encode("utf-8")).hexdigest()
        for option in options
    ]
    counts = [0] * len(options)

    latest: dict[str, PollVoteRecord] = {}
    for vote in votes:
        previous = latest.get(vote.sender_jid)
        if previous is None or vote.timestamp_ms > previous.timestamp_ms:
            latest[vote.sender_jid] = vote

    for vote in latest.values():
        selected = set(vote.selected_options)
        for index, option_hash in enumerate(hashes):
            if option_hash in selected:
                counts[index] += 1

    return counts


def refresh_poll_vote_counts(
    kv: Any,
    chat_id: str,
    poll_id: str,
):
    """Update the original poll message with current vote counts."""
    typed_kv = kv if isinstance(kv, GreenlineKV) else GreenlineKV(kv)

    storage_key, stored = get_message_entry_with_key(
        typed_kv, chat_id, poll_id
    )
    if stored is None:
        return None

    message = message_from_record(stored)
    if not message.poll_options:
        return None

    votes = list_poll_votes(typed_kv, chat_id, poll_id)
    counts = count_poll_votes(votes, message.poll_options)

    if message.poll_vote_counts != counts:
        message.poll_vote_counts = counts
        typed_kv.put_record(
            storage_key,
            updated_stored_message_record(stored, message),
        )

    return message


def own_poll_selected_indices(kv, chat_id, poll_id, own_jid, options):
    """Return indices selected by the current user in a poll."""
    if not own_jid or not options:
        return []

    typed_kv = kv if isinstance(kv, GreenlineKV) else GreenlineKV(kv)
    vote = typed_kv.get_record(poll_vote_key(chat_id, poll_id, own_jid))

    if not isinstance(vote, PollVoteRecord):
        return []

    selected = set(vote.selected_options)

    return [
        index
        for index, option in enumerate(options)
        if hashlib.sha256(option.encode("utf-8")).hexdigest() in selected
    ]
