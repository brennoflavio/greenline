from dataclasses import asdict, dataclass, field

from daemon_types import Contact as DaemonContact
from greenline.api.common import SuccessResponse, ui_chat, ui_chat_dict
from greenline.store.identity import canonicalize_contact_jid
from greenline.store.mentions import build_mention_candidate, validate_mention_spans
from models import (
    ChatListEntry,
    ChatListItem,
    ChatListResponse,
    ContactItem,
    ContactListResponse,
)
from rpc import DaemonRPC
from ut_components.crash import crash_reporter
from ut_components.kv import KV
from ut_components.utils import dataclass_to_dict


@dataclass
class ChatDraftResponse:
    success: bool
    text: str
    mention_spans: list[dict[str, object]] = field(default_factory=list)


@dataclass
class GroupMentionCandidatesResponse:
    success: bool
    candidates: list[dict[str, object]] = field(default_factory=list)
    message: str = ""


def _build_contact_item(contact: DaemonContact) -> ContactItem:
    jid = canonicalize_contact_jid(contact.jid)
    photo = ""
    if contact.avatar_path:
        photo = "file://" + contact.avatar_path
    return ContactItem(
        jid=jid,
        display_name=contact.display_name or jid,
        first_name=contact.first_name,
        full_name=contact.full_name,
        push_name=contact.push_name,
        business_name=contact.business_name,
        photo=photo,
    )


@crash_reporter
@dataclass_to_dict
def get_contact_list() -> ContactListResponse:
    try:
        reply = DaemonRPC().get_contacts()
        contacts = [_build_contact_item(contact) for contact in reply.Contacts]
        return ContactListResponse(success=True, contacts=contacts, message="")
    except Exception as error:
        return ContactListResponse(success=False, contacts=[], message=str(error))


@crash_reporter
@dataclass_to_dict
def get_chat_list() -> ChatListResponse:
    try:
        with KV() as kv:
            entries = kv.get_partial("chat:")
            drafts = {key.removeprefix("draft:"): str(value or "") for key, value in kv.get_partial("draft:")}

        chats = []
        for _, value in entries:
            chat = ui_chat(ChatListItem(**value))
            draft = drafts.get(chat.id, "")
            chats.append(ChatListEntry(**asdict(chat), draft=draft, has_draft=draft != ""))
        chats.sort(key=lambda chat: chat.last_message_timestamp, reverse=True)
        return ChatListResponse(success=True, chats=chats, message="")
    except Exception as error:
        return ChatListResponse(success=False, chats=[], message=str(error))


@crash_reporter
def get_chat_info(chat_id: str) -> dict[str, object]:
    with KV() as kv:
        data = kv.get(f"chat:{chat_id}")
    if not data:
        return {"success": False}
    try:
        chat = ChatListItem(**data)
    except (TypeError, KeyError):
        return {"success": False}
    return {
        "success": True,
        "id": chat.id,
        "name": chat.name,
        "photo": chat.photo,
        "is_group": chat.is_group,
        "unread_count": chat.unread_count,
    }


@crash_reporter
@dataclass_to_dict
def get_group_mention_candidates(chat_id: str) -> GroupMentionCandidatesResponse:
    try:
        participants = DaemonRPC().get_group_participants(chat_id).Participants
        candidates = []
        for participant in participants:
            candidate = build_mention_candidate(participant.jid, participant.display_name)
            candidate["is_admin"] = participant.is_admin
            candidate["is_super_admin"] = participant.is_super_admin
            candidates.append(candidate)
        candidates.sort(key=lambda candidate: str(candidate.get("label") or "").lower())
        return GroupMentionCandidatesResponse(success=True, candidates=candidates)
    except Exception as error:
        return GroupMentionCandidatesResponse(success=False, message=str(error))


@crash_reporter
@dataclass_to_dict
def get_chat_draft(chat_id: str) -> ChatDraftResponse:
    with KV() as kv:
        draft = kv.get(f"draft:{chat_id}", default="")
        draft_mentions = kv.get(f"draft_mentions:{chat_id}", default=[])

    draft_text = str(draft or "")
    mention_spans = validate_mention_spans(
        draft_text,
        draft_mentions if isinstance(draft_mentions, list) else None,
    )
    return ChatDraftResponse(success=True, text=draft_text, mention_spans=mention_spans)


@crash_reporter
@dataclass_to_dict
def set_chat_draft(
    chat_id: str,
    text: str,
    mention_spans: list[dict[str, object]] | None = None,
) -> SuccessResponse:
    import pyotherside

    draft_text = str(text)
    validated_spans = validate_mention_spans(draft_text, mention_spans)
    with KV() as kv:
        if draft_text != "":
            kv.put(f"draft:{chat_id}", draft_text)
            if validated_spans:
                kv.put(f"draft_mentions:{chat_id}", validated_spans)
            else:
                kv.delete(f"draft_mentions:{chat_id}")
        else:
            kv.delete(f"draft:{chat_id}")
            kv.delete(f"draft_mentions:{chat_id}")
    pyotherside.send(
        "chat-draft-update",
        [{"id": chat_id, "draft": draft_text, "has_draft": draft_text != ""}],
    )
    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def toggle_mute(chat_id: str) -> SuccessResponse:
    import pyotherside

    with KV() as kv:
        data = kv.get(f"chat:{chat_id}")
        if data is None:
            return SuccessResponse(success=False, message="Chat not found")
        chat = ChatListItem(**data)
        new_muted = not chat.muted

    DaemonRPC().set_muted(chat_id, new_muted)

    with KV() as kv:
        data = kv.get(f"chat:{chat_id}")
        if data is not None:
            chat = ChatListItem(**data)
            chat.muted = new_muted
            kv.put(f"chat:{chat_id}", asdict(chat))
            pyotherside.send("chat-list-update", [ui_chat_dict(chat)])

    return SuccessResponse(success=True, message="")
