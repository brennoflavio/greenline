from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class SessionStatusReply:
    LoggedIn: bool = False
    QRCode: str = ""
    QRImage: str = ""


@dataclass
class VersionReply:
    GitCommit: str = ""


@dataclass
class Contact:
    jid: str = ""
    display_name: str = ""
    first_name: str = ""
    full_name: str = ""
    push_name: str = ""
    business_name: str = ""


@dataclass
class GetContactsReply:
    Contacts: List[Contact] = field(default_factory=list)


@dataclass
class ContactInfoResult:
    jid: str = ""
    display_name: str = ""
    first_name: str = ""
    full_name: str = ""
    push_name: str = ""
    business_name: str = ""
    profile_pic_url: str = ""
    profile_pic_id: str = ""


@dataclass
class GetContactInfoReply:
    Contact: ContactInfoResult = field(default_factory=ContactInfoResult)
    Found: bool = False


@dataclass
class GetProfilePictureReply:
    URL: str = ""
    ID: str = ""


@dataclass
class StoredEvent:
    id: int = 0
    event_type: str = ""
    payload: str = ""
    created_at: int = 0


@dataclass
class ListEventsReply:
    Events: List[StoredEvent] = field(default_factory=list)
