from dataclasses import dataclass, field
from enum import StrEnum
from typing import List


class MessageType(StrEnum):
    TEXT = "text"
    VIEW_ONCE = "view_once"
    DELETED = "deleted"
    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"
    AUDIO = "audio"
    DOCUMENT = "document"
    CONTACT = "contact"
    LOCATION = "location"
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
    last_message_mentioned_jids: List[str] = field(default_factory=list)
    last_message_type: str = ""
    muted: bool = False
    full_name: str = ""
    push_name: str = ""
    business_name: str = ""
    name_updated_at: int = 0


@dataclass
class ChatListEntry(ChatListItem):
    draft: str = ""
    has_draft: bool = False


@dataclass
class ChatListResponse:
    success: bool
    chats: List[ChatListEntry]
    message: str


@dataclass
class MentionSpan:
    jid: str
    label: str
    start: int
    length: int


@dataclass
class Message:
    id: str
    chat_id: str
    type: MessageType
    is_outgoing: bool
    timestamp: str
    timestamp_unix: int
    read_receipt: ReadReceipt
    edited: bool = False
    has_reactions: bool = False
    sender: str = ""
    sender_raw: str = ""
    text: str = ""
    mentioned_jids: List[str] = field(default_factory=list)
    mention_spans: List[MentionSpan] = field(default_factory=list)
    image_source: str = ""
    caption: str = ""
    duration: str = ""
    sticker_source: str = ""
    media_path: str = ""
    thumbnail_path: str = ""
    mimetype: str = ""
    file_name: str = ""
    send_status: str = ""
    temp_id: str = ""
    reply_to_id: str = ""
    reply_to_sender_id: str = ""
    reply_to_sender_raw: str = ""
    reply_to_from_me: bool = False
    reply_to_text: str = ""
    reply_to_mentioned_jids: List[str] = field(default_factory=list)
    button_text: str = ""
    button_url: str = ""
    link_title: str = ""
    link_description: str = ""
    link_url: str = ""


@dataclass
class UiMessage(Message):
    formatted_text: str = ""
    formatted_caption: str = ""
    formatted_reply_to_text: str = ""
    sender_name: str = ""
    sender_photo: str = ""
    reply_to_sender: str = ""


@dataclass
class MessagesResponse:
    success: bool
    messages: List[UiMessage]
    message: str
    next_cursor: str = ""
    has_more: bool = False


@dataclass
class MessageReactionItem:
    jid: str
    name: str
    photo: str
    emoji: str


@dataclass
class MessageReactionsResponse:
    success: bool
    reactions: List[MessageReactionItem]
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
