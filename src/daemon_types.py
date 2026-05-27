from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class SessionStatusReply:
    LoggedIn: bool
    QRCode: str
    QRImage: str


@dataclass
class VersionReply:
    GitCommit: str


@dataclass
class Contact:
    jid: str
    display_name: str
    first_name: str
    full_name: str
    push_name: str
    business_name: str
    avatar_path: str


@dataclass
class GetContactsReply:
    Contacts: List[Contact]


@dataclass
class Group:
    jid: str
    name: str
    topic: str
    avatar_path: str


@dataclass
class GetGroupsReply:
    Groups: List[Group]


@dataclass
class GroupParticipant:
    jid: str
    phone_number_jid: str
    lid_jid: str
    display_name: str
    is_admin: bool
    is_super_admin: bool


@dataclass
class GetGroupParticipantsReply:
    Participants: List[GroupParticipant]


@dataclass
class StoredEvent:
    id: int
    event_type: str
    payload: str
    created_at: int


@dataclass
class ListEventsReply:
    Events: List[StoredEvent]


@dataclass
class SendMessageReply:
    MessageID: str
    Timestamp: int


@dataclass
class SyncAvatarReply:
    AvatarPath: str


@dataclass
class GetChatSettingsReply:
    MutedUntil: int


@dataclass
class PairPhoneReply:
    Code: str
