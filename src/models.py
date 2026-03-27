from dataclasses import dataclass, field
from enum import StrEnum
from typing import List


class MessageType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    IMAGE_GALLERY = "image_gallery"
    VOICE = "voice"
    STICKER = "sticker"


class ReadReceipt(StrEnum):
    NONE = ""
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


@dataclass
class ChatListItem:
    id: str
    name: str
    photo: str
    last_message: str
    date: str
    last_message_timestamp: int
    read_receipt: ReadReceipt
    unread_count: int
    is_group: bool


@dataclass
class ChatListResponse:
    success: bool
    chats: List[ChatListItem]
    message: str


@dataclass
class Message:
    id: str
    chat_id: str
    type: MessageType
    is_outgoing: bool
    timestamp: str
    timestamp_unix: int
    read_receipt: ReadReceipt
    text: str = ""
    image_source: str = ""
    caption: str = ""
    images: List[str] = field(default_factory=list)
    duration: str = ""
    sticker_source: str = ""


@dataclass
class MessagesResponse:
    success: bool
    messages: List[Message]
    message: str


@dataclass
class StatusUpdate:
    message_id: str
    chat_id: str
    read_receipt: ReadReceipt


@dataclass
class ContactItem:
    jid: str
    display_name: str
    first_name: str
    full_name: str
    push_name: str
    business_name: str
    photo: str


@dataclass
class ContactListResponse:
    success: bool
    contacts: List[ContactItem]
    message: str
