from __future__ import annotations

from dataclasses import replace
from typing import Any

from greenline.contracts.kv import GreenlineKV
from greenline.store.records import (
    MessageReactionRecord,
    message_from_record,
    updated_stored_message_record,
)
from greenline.store.repository import _find_message_entry
from models import Message


def _greenline_kv(kv: Any) -> GreenlineKV:
    if isinstance(kv, GreenlineKV):
        return kv
    return GreenlineKV(kv)


def message_reaction_key(chat_id: str, message_id: str, sender_jid: str) -> str:
    return f"message_reaction:{chat_id}:{message_id}:{sender_jid}"


def message_reaction_prefix(chat_id: str, message_id: str) -> str:
    return f"message_reaction:{chat_id}:{message_id}:"


def list_message_reactions(kv: Any, chat_id: str, message_id: str) -> list[tuple[str, MessageReactionRecord]]:
    if not chat_id or not message_id:
        return []
    typed_kv = _greenline_kv(kv)
    return typed_kv.get_partial_records(message_reaction_prefix(chat_id, message_id))


def has_message_reactions(kv: Any, chat_id: str, message_id: str) -> bool:
    return bool(list_message_reactions(kv, chat_id, message_id))


def put_message_reaction(kv: Any, chat_id: str, message_id: str, sender_jid: str, emoji: str) -> None:
    if not chat_id or not message_id or not sender_jid or not emoji:
        return
    _greenline_kv(kv).put_record(
        message_reaction_key(chat_id, message_id, sender_jid),
        MessageReactionRecord(
            chat_id=chat_id,
            message_id=message_id,
            sender_jid=sender_jid,
            emoji=emoji,
        ),
    )


def delete_message_reaction(kv: Any, chat_id: str, message_id: str, sender_jid: str) -> None:
    if not chat_id or not message_id or not sender_jid:
        return
    _greenline_kv(kv).delete(message_reaction_key(chat_id, message_id, sender_jid))


def apply_message_reactions_flag(message: Message, kv: Any) -> Message:
    has_reactions = has_message_reactions(kv, message.chat_id, message.id)
    if message.has_reactions == has_reactions:
        return message
    return replace(message, has_reactions=has_reactions)


def refresh_message_reactions_flag(kv: Any, chat_id: str, message_id: str) -> Message | None:
    if not chat_id or not message_id:
        return None

    typed_kv = _greenline_kv(kv)
    storage_key, stored_record = _find_message_entry(typed_kv, chat_id, message_id)
    if storage_key is None or stored_record is None:
        return None

    message = message_from_record(stored_record)
    updated_message = apply_message_reactions_flag(message, typed_kv)
    if updated_message != message:
        typed_kv.put_record(storage_key, updated_stored_message_record(stored_record, updated_message))
    return updated_message
