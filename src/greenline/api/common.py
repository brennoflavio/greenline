from dataclasses import asdict, dataclass

from greenline.store.mentions import render_chat_mentions
from greenline.store.repository import to_ui_message
from models import ChatListItem, Message, UiMessage
from ut_components.utils import enum_to_str as _enum_to_str


@dataclass
class SuccessResponse:
    success: bool
    message: str


def ui_message(message: Message) -> UiMessage:
    return to_ui_message(message)


def ui_chat(chat: ChatListItem) -> ChatListItem:
    return render_chat_mentions(chat)


def ui_message_dict(message: Message) -> dict[str, object]:
    return _enum_to_str(asdict(ui_message(message)))  # type: ignore[no-untyped-call, no-any-return]


def ui_chat_dict(chat: ChatListItem) -> dict[str, object]:
    return _enum_to_str(asdict(ui_chat(chat)))  # type: ignore[no-untyped-call, no-any-return]
