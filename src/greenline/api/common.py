from dataclasses import dataclass

from greenline import qml_payloads
from greenline.store.mentions import render_chat_mentions
from greenline.store.repository import to_ui_message
from models import ChatListItem, Message, UiMessage


@dataclass
class SuccessResponse:
    success: bool
    message: str


def ui_message(message: Message) -> UiMessage:
    return to_ui_message(message)


def ui_chat(chat: ChatListItem) -> ChatListItem:
    return render_chat_mentions(chat)


def ui_message_dict(message: Message) -> dict[str, object]:
    return qml_payloads.ui_message(message)


def ui_chat_dict(chat: ChatListItem) -> dict[str, object]:
    return qml_payloads.ui_chat(chat)
