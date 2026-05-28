from dataclasses import asdict, dataclass, field

from daemon_types import Contact as DaemonContact
from greenline import qml_events
from greenline.api.common import SuccessResponse, ui_chat
from greenline.contracts.daemon import daemon_client
from greenline.contracts.kv import GreenlineKV
from greenline.contracts.qml import ChatIdRequest, SetChatDraftRequest
from greenline.contracts.validation import BoundaryValidationError
from greenline.reporting import crash_reporter
from greenline.store.identity import canonicalize_contact_jid
from greenline.store.mentions import build_mention_candidate, validate_mention_spans
from greenline.store.records import DraftMentionsRecord, DraftRecord
from models import (
    ChatListEntry,
    ChatListResponse,
    ContactItem,
    ContactListResponse,
    MentionSpan,
)
from ut_components.utils import dataclass_to_dict


@dataclass
class ChatDraftResponse:
    success: bool
    text: str
    mention_spans: list[MentionSpan] = field(default_factory=list)


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
        reply = daemon_client().get_contacts()
        contacts = [_build_contact_item(contact) for contact in reply.Contacts]
        return ContactListResponse(success=True, contacts=contacts, message="")
    except BoundaryValidationError:
        raise
    except Exception as error:
        return ContactListResponse(success=False, contacts=[], message=str(error))


@crash_reporter
@dataclass_to_dict
def get_chat_list() -> ChatListResponse:
    try:
        with GreenlineKV() as kv:
            entries = kv.get_partial_records("chat:")
            drafts = {key.removeprefix("draft:"): value.value for key, value in kv.get_partial_records("draft:")}

        chats = []
        for _, value in entries:
            chat = ui_chat(value)
            draft = drafts.get(chat.id, "")
            chats.append(ChatListEntry(**asdict(chat), draft=draft, has_draft=draft != ""))
        chats.sort(key=lambda chat: chat.last_message_timestamp, reverse=True)
        return ChatListResponse(success=True, chats=chats, message="")
    except BoundaryValidationError:
        raise
    except Exception as error:
        return ChatListResponse(success=False, chats=[], message=str(error))


@crash_reporter
def get_chat_info(request: ChatIdRequest) -> dict[str, object]:
    with GreenlineKV() as kv:
        chat = kv.get_record(f"chat:{request.chat_id}")
    if chat is None:
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
def get_group_mention_candidates(request: ChatIdRequest) -> GroupMentionCandidatesResponse:
    try:
        participants = daemon_client().get_group_participants(request.chat_id).Participants
        candidates = []
        for participant in participants:
            candidate = build_mention_candidate(participant.jid, participant.display_name)
            candidate["is_admin"] = participant.is_admin
            candidate["is_super_admin"] = participant.is_super_admin
            candidates.append(candidate)
        candidates.sort(key=lambda candidate: str(candidate.get("label") or "").lower())
        return GroupMentionCandidatesResponse(success=True, candidates=candidates)
    except BoundaryValidationError:
        raise
    except Exception as error:
        return GroupMentionCandidatesResponse(success=False, message=str(error))


@crash_reporter
@dataclass_to_dict
def get_chat_draft(request: ChatIdRequest) -> ChatDraftResponse:
    with GreenlineKV() as kv:
        draft = kv.get_record(f"draft:{request.chat_id}", default=DraftRecord(""))
        draft_mentions = kv.get_record(f"draft_mentions:{request.chat_id}", default=DraftMentionsRecord([]))

    draft_text = draft.value
    mention_spans = validate_mention_spans(draft_text, draft_mentions.value)
    return ChatDraftResponse(success=True, text=draft_text, mention_spans=mention_spans)


@crash_reporter
@dataclass_to_dict
def set_chat_draft(request: SetChatDraftRequest) -> SuccessResponse:
    draft_text = request.text
    validated_spans = validate_mention_spans(draft_text, request.mention_spans)
    with GreenlineKV() as kv:
        if draft_text != "":
            kv.put_record(f"draft:{request.chat_id}", DraftRecord(draft_text))
            if validated_spans:
                kv.put_record(
                    f"draft_mentions:{request.chat_id}",
                    DraftMentionsRecord(validated_spans),
                )
            else:
                kv.delete(f"draft_mentions:{request.chat_id}")
        else:
            kv.delete(f"draft:{request.chat_id}")
            kv.delete(f"draft_mentions:{request.chat_id}")
    qml_events.emit_chat_draft_update(request.chat_id, draft_text)
    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def toggle_mute(request: ChatIdRequest) -> SuccessResponse:
    with GreenlineKV() as kv:
        chat = kv.get_record(f"chat:{request.chat_id}")
        if chat is None:
            return SuccessResponse(success=False, message="Chat not found")
        new_muted = not chat.muted

    daemon_client().set_muted(request.chat_id, new_muted)

    with GreenlineKV() as kv:
        chat = kv.get_record(f"chat:{request.chat_id}")
        if chat is not None:
            chat.muted = new_muted
            kv.put_record(f"chat:{request.chat_id}", chat)
            qml_events.emit_chat_list_update([chat])

    return SuccessResponse(success=True, message="")
