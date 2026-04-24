from dataclasses import dataclass, field
from enum import StrEnum
from typing import List


class MessageType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    IMAGE_GALLERY = "image_gallery"
    VIDEO = "video"
    VOICE = "voice"
    AUDIO = "audio"
    DOCUMENT = "document"
    CONTACT = "contact"
    STICKER = "sticker"
    LINK_PREVIEW = "link_preview"


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
    muted: bool = False
    full_name: str = ""
    push_name: str = ""
    business_name: str = ""
    name_updated_at: int = 0


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
    sender: str = ""
    sender_name: str = ""
    sender_photo: str = ""
    text: str = ""
    image_source: str = ""
    caption: str = ""
    images: List[str] = field(default_factory=list)
    duration: str = ""
    sticker_source: str = ""
    media_path: str = ""
    thumbnail_path: str = ""
    mimetype: str = ""
    file_name: str = ""
    send_status: str = ""
    temp_id: str = ""
    reply_to_id: str = ""
    reply_to_sender: str = ""
    reply_to_text: str = ""
    link_title: str = ""
    link_description: str = ""
    link_url: str = ""


@dataclass
class MessagesResponse:
    success: bool
    messages: List[Message]
    message: str


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
