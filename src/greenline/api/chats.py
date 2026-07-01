import re
from dataclasses import asdict, dataclass, field

from constants import WHATSAPP_JID_SUFFIX
from daemon_types import Contact as DaemonContact
from greenline import qml_events
from greenline.api.common import SuccessResponse, ui_chat
from greenline.contracts.daemon import daemon_client
from greenline.contracts.kv import GreenlineKV
from greenline.contracts.qml import (
    ChatIdRequest,
    GetChatListRequest,
    PrioritizeChatAvatarsRequest,
    SetChatDraftRequest,
    StartChatByPhoneRequest,
    StartChatFromContactRequest,
)
from greenline.contracts.validation import BoundaryValidationError
from greenline.reporting import crash_reporter
from greenline.store.identity import (
    canonicalize_contact_jid,
    get_own_jid,
    prioritize_missing_avatar_chat_ids,
)
from greenline.store.mentions import build_mention_candidate, validate_mention_spans
from greenline.store.records import DraftMentionsRecord, DraftRecord, GroupProfileRecord
from models import (
    ChatListEntry,
    ChatListItem,
    ChatListResponse,
    ContactItem,
    ContactListResponse,
    MentionSpan,
    ReadReceipt,
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


@dataclass
class StartChatByPhoneResponse:
    success: bool
    chat: ChatListItem | None = None
    message: str = ""


_PHONE_NUMBER_REGEX = re.compile(r"^[1-9][0-9]{6,14}$")
_PHONE_NUMBER_ERROR = "Enter digits only, no leading zero (e.g. 5511999999999)"
_CONTACT_PHONE_ERROR = "Contact does not contain a valid phone number"
_RESOLVE_CHAT_ERROR = "Failed to resolve phone number"


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
def get_chat_list(request: GetChatListRequest) -> ChatListResponse:
    try:
        with GreenlineKV() as kv:
            entries = kv.get_partial_records("chat:")
            drafts = {key.removeprefix("draft:"): value.value for key, value in kv.get_partial_records("draft:")}

        own_jid = get_own_jid()
        chats = []
        for _, value in entries:
            if own_jid and value.id == own_jid:
                continue
            chat = ui_chat(value)
            if chat.archived != request.archived:
                continue
            draft = drafts.get(chat.id, "")
            chats.append(ChatListEntry(**asdict(chat), draft=draft, has_draft=draft != ""))
        chats.sort(key=lambda chat: chat.last_message_timestamp, reverse=True)
        return ChatListResponse(success=True, chats=chats, message="")
    except BoundaryValidationError:
        raise
    except Exception as error:
        return ChatListResponse(success=False, chats=[], message=str(error))


def prioritize_chat_avatars(request: PrioritizeChatAvatarsRequest) -> None:
    try:
        prioritize_missing_avatar_chat_ids(request.chat_ids)
    except Exception:
        pass


def _normalize_phone_number(phone_number: str) -> str:
    normalized = str(phone_number or "").strip()
    if not _PHONE_NUMBER_REGEX.fullmatch(normalized):
        return ""
    return normalized


def _normalize_imported_phone_number(phone_number: str) -> str:
    return re.sub(r"\D", "", str(phone_number or ""))


def _unfold_vcard_lines(vcard: str) -> list[str]:
    unfolded_lines: list[str] = []
    for raw_line in vcard.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if (raw_line.startswith(" ") or raw_line.startswith("\t")) and unfolded_lines:
            unfolded_lines[-1] += raw_line[1:]
        else:
            unfolded_lines.append(raw_line)
    return unfolded_lines


def _extract_phone_number_from_vcard(vcard: str) -> str:
    for line in _unfold_vcard_lines(vcard):
        key, separator, value = line.partition(":")
        property_name = key.split(";", 1)[0].rsplit(".", 1)[-1].upper()
        if separator and property_name == "TEL":
            phone_number = _normalize_phone_number(_normalize_imported_phone_number(value))
            if phone_number:
                return phone_number
    return ""


def _fallback_direct_chat(chat_id: str, phone_number: str) -> ChatListItem:
    return ChatListItem(
        id=chat_id,
        name=phone_number,
        photo="",
        last_message="",
        date="",
        last_message_timestamp=0,
        read_receipt=ReadReceipt.NONE,
        unread_count=0,
        is_group=False,
    )


def _start_chat_response(phone_number: str) -> StartChatByPhoneResponse:
    normalized_phone_number = _normalize_phone_number(phone_number)
    if not normalized_phone_number:
        return StartChatByPhoneResponse(success=False, message=_PHONE_NUMBER_ERROR)

    rpc = daemon_client()
    resolved_jid = canonicalize_contact_jid(
        rpc.ensure_jid(f"{normalized_phone_number}{WHATSAPP_JID_SUFFIX}").JID, rpc=rpc
    )
    if not resolved_jid:
        return StartChatByPhoneResponse(success=False, message=_RESOLVE_CHAT_ERROR)

    with GreenlineKV() as kv:
        existing_chat = kv.get_record(f"chat:{resolved_jid}")

    if existing_chat is not None:
        return StartChatByPhoneResponse(success=True, chat=existing_chat, message="")

    return StartChatByPhoneResponse(
        success=True, chat=_fallback_direct_chat(resolved_jid, normalized_phone_number), message=""
    )


@crash_reporter
@dataclass_to_dict
def start_chat_by_phone(request: StartChatByPhoneRequest) -> StartChatByPhoneResponse:
    try:
        return _start_chat_response(request.phone_number)
    except BoundaryValidationError:
        raise
    except Exception as error:
        return StartChatByPhoneResponse(success=False, message=str(error))


@crash_reporter
@dataclass_to_dict
def start_chat_from_contact(request: StartChatFromContactRequest) -> StartChatByPhoneResponse:
    try:
        with open(request.file_path, encoding="utf-8-sig") as file_handle:
            phone_number = _extract_phone_number_from_vcard(file_handle.read())
        if not phone_number:
            return StartChatByPhoneResponse(success=False, message=_CONTACT_PHONE_ERROR)
        return _start_chat_response(phone_number)
    except BoundaryValidationError:
        raise
    except Exception as error:
        return StartChatByPhoneResponse(success=False, message=str(error))


def _chat_info_members(profile: GroupProfileRecord) -> list[dict[str, str]]:
    members = []
    for member in profile.members:
        candidate = build_mention_candidate(member.jid, member.display_name)
        jid = str(candidate.get("jid") or "")
        if not jid:
            continue
        members.append(
            {
                "jid": jid,
                "name": str(candidate.get("label") or jid),
                "photo": str(candidate.get("photo") or ""),
            }
        )
    members.sort(key=lambda member: (member["name"].lower(), member["jid"]))
    return members


@crash_reporter
def get_chat_info(request: ChatIdRequest) -> dict[str, object]:
    with GreenlineKV() as kv:
        chat = kv.get_record(f"chat:{request.chat_id}")
        profile = GroupProfileRecord()
        if chat is not None and chat.is_group:
            profile = kv.get_record(f"group_profile:{chat.id}", default=GroupProfileRecord())
    if chat is None:
        return {"success": False}
    members = _chat_info_members(profile)
    return {
        "success": True,
        "id": chat.id,
        "name": chat.name,
        "photo": chat.photo,
        "is_group": chat.is_group,
        "unread_count": chat.unread_count,
        "first_unread_message_id": chat.first_unread_message_id,
        "muted": chat.muted,
        "description": profile.description,
        "member_count": profile.member_count or len(members),
        "members": members,
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
def toggle_archive(request: ChatIdRequest) -> SuccessResponse:
    with GreenlineKV() as kv:
        chat = kv.get_record(f"chat:{request.chat_id}")
        if chat is None:
            return SuccessResponse(success=False, message="Chat not found")
        chat.archived = not chat.archived
        kv.put_record(f"chat:{request.chat_id}", chat)
        qml_events.emit_chat_list_update([chat])

    return SuccessResponse(success=True, message="")


@crash_reporter
@dataclass_to_dict
def toggle_mute(request: ChatIdRequest) -> SuccessResponse:
    with GreenlineKV() as kv:
        chat = kv.get_record(f"chat:{request.chat_id}")
        if chat is None:
            return SuccessResponse(success=False, message="Chat not found")
        chat.muted = not chat.muted
        kv.put_record(f"chat:{request.chat_id}", chat)
        qml_events.emit_chat_list_update([chat])

    return SuccessResponse(success=True, message="")
