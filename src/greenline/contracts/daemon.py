from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from daemon_types import (
    GetChatSettingsReply,
    GetContactsReply,
    GetGroupParticipantsReply,
    GetGroupsReply,
    ListEventsReply,
    PairPhoneReply,
    SendMessageReply,
    SessionStatusReply,
    SyncAvatarReply,
    VersionReply,
)
from greenline.contracts.codecs import decode_dataclass, encode_dataclass
from greenline.contracts.validation import (
    BoundaryValidationError,
    report_validation_failure,
)
from rpc import DaemonRPC


@dataclass
class ListEventsRequest:
    AfterID: int = 0
    Limit: int = 100


@dataclass
class DeleteEventsRequest:
    UpToID: int


@dataclass
class EnsureJIDRequest:
    JID: str


@dataclass
class EnsureJIDReply:
    JID: str = ""


@dataclass
class GetGroupParticipantsRequest:
    ChatJID: str


@dataclass
class SyncAvatarRequest:
    JID: str


@dataclass
class GetChatSettingsRequest:
    ChatJID: str


@dataclass
class MarkReadRequest:
    ChatJID: str
    SenderJID: str
    MessageIDs: list[str]


@dataclass
class SendMessageRequest:
    ChatJID: str
    Type: str
    Text: str = ""
    FilePath: str = ""
    Caption: str = ""
    DurationSeconds: int = 0
    PTT: bool = False
    ReplyToMessageID: str | None = None
    ReplyParticipantJID: str | None = None
    ReplyQuotedMessage: Any | None = None
    MentionedJIDs: list[str] | None = None


@dataclass
class EditMessageRequest:
    ChatJID: str
    MessageID: str
    Text: str
    ReplyToMessageID: str | None = None
    ReplyParticipantJID: str | None = None
    ReplyQuotedMessage: Any | None = None


@dataclass
class DeleteMessageRequest:
    ChatJID: str
    MessageID: str


@dataclass
class SetMutedRequest:
    ChatJID: str
    Muted: bool


@dataclass
class DownloadMediaRequest:
    DirectPath: str
    MediaKey: str
    FileEncSHA256: str
    FileSHA256: str
    FileLength: int
    MediaType: str
    Mimetype: str
    MessageID: str
    ChatID: str
    FileName: str = ""


@dataclass
class DownloadMediaReply:
    FilePath: str = ""


@dataclass
class SetNotificationCounterRequest:
    Count: int
    Visible: bool


@dataclass
class ClearChatNotificationsRequest:
    Tags: list[str]


@dataclass
class PairPhoneRequest:
    Phone: str


@dataclass
class SendPresenceRequest:
    Available: bool


@dataclass
class SubscribePresenceRequest:
    JID: str


class DaemonClientProtocol(Protocol):
    def ping(self) -> str: ...

    def get_version(self) -> VersionReply: ...

    def get_session_status(self) -> SessionStatusReply: ...

    def get_contacts(self) -> GetContactsReply: ...

    def get_groups(self) -> GetGroupsReply: ...

    def get_group_participants(self, chat_jid: str) -> GetGroupParticipantsReply: ...

    def sync_avatar(self, jid: str) -> SyncAvatarReply: ...

    def list_events(self, after_id: int = 0, limit: int = 100) -> ListEventsReply: ...

    def delete_events(self, up_to_id: int) -> None: ...

    def ensure_jid(self, jid: str) -> str: ...

    def get_phone_number(self, jid: str) -> str: ...

    def mark_read(self, chat_jid: str, message_ids: list[str], sender_jid: str = "") -> None: ...

    def send_message(
        self,
        chat_jid: str,
        msg_type: str,
        text: str = "",
        file_path: str = "",
        caption: str = "",
        reply_context: Optional[dict[str, Any]] = None,
        mentioned_jids: Optional[list[str]] = None,
        duration_seconds: int = 0,
        ptt: bool = False,
    ) -> SendMessageReply: ...

    def edit_message(
        self,
        chat_jid: str,
        message_id: str,
        text: str,
        reply_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]: ...

    def delete_message(self, chat_jid: str, message_id: str) -> dict[str, Any]: ...

    def get_chat_settings(self, chat_jid: str) -> GetChatSettingsReply: ...

    def send_presence(self, available: bool) -> None: ...

    def subscribe_presence(self, jid: str) -> None: ...

    def logout(self) -> None: ...

    def set_muted(self, chat_jid: str, muted: bool) -> None: ...

    def download_media(
        self,
        direct_path: str,
        media_key: str,
        file_enc_sha256: str,
        file_sha256: str,
        file_length: int,
        media_type: str,
        mimetype: str,
        message_id: str,
        chat_id: str,
        file_name: str = "",
    ) -> str: ...

    def set_notification_counter(self, count: int, visible: bool) -> None: ...

    def clear_chat_notifications(self, tags: list[str]) -> None: ...

    def pair_phone(self, phone: str) -> PairPhoneReply: ...


DaemonClientFactory = Callable[[], DaemonClientProtocol]
_daemon_client_factory: DaemonClientFactory | None = None


def _without_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _reply_context_fields(reply_context: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not reply_context:
        return {}
    fields: dict[str, Any] = {
        "ReplyToMessageID": str(reply_context.get("id") or ""),
        "ReplyParticipantJID": str(reply_context.get("participant") or ""),
    }
    quoted_message = reply_context.get("quoted_message")
    if quoted_message is not None:
        fields["ReplyQuotedMessage"] = quoted_message
    return fields


def _with_empty_list(data: Any, key: str) -> Any:
    if isinstance(data, dict) and data.get(key) is None:
        data = dict(data)
        data[key] = []
    return data


def _decode_send_message_reply(data: Any) -> SendMessageReply:
    reply = decode_dataclass(SendMessageReply, data, boundary="daemon.reply.Service.SendMessage")
    if not reply.MessageID or reply.Timestamp <= 0:
        error = BoundaryValidationError("Service.SendMessage reply requires non-empty MessageID and positive Timestamp")
        report_validation_failure("daemon.reply.Service.SendMessage", error, payload=data)
        raise error
    return reply


class GreenlineDaemon:
    def __init__(self, transport: DaemonRPC | None = None) -> None:
        self._transport = transport or DaemonRPC()

    def _call(self, method: str, request: Any | None = None) -> Any:
        params = None
        if request is not None:
            params = _without_none(encode_dataclass(request, boundary=f"daemon.request.{method}"))
        return self._transport._call(method, params)

    def ping(self) -> str:
        result: str = self._call("Service.Ping")
        return result

    def get_version(self) -> VersionReply:
        return decode_dataclass(
            VersionReply,
            self._call("Service.GetVersion"),
            boundary="daemon.reply.Service.GetVersion",
        )

    def get_session_status(self) -> SessionStatusReply:
        return decode_dataclass(
            SessionStatusReply,
            self._call("Service.GetSessionStatus"),
            boundary="daemon.reply.Service.GetSessionStatus",
        )

    def get_contacts(self) -> GetContactsReply:
        return decode_dataclass(
            GetContactsReply,
            self._call("Service.GetContacts"),
            boundary="daemon.reply.Service.GetContacts",
        )

    def get_groups(self) -> GetGroupsReply:
        data = _with_empty_list(self._call("Service.GetGroups"), "Groups")
        return decode_dataclass(GetGroupsReply, data, boundary="daemon.reply.Service.GetGroups")

    def get_group_participants(self, chat_jid: str) -> GetGroupParticipantsReply:
        data = _with_empty_list(
            self._call(
                "Service.GetGroupParticipants",
                GetGroupParticipantsRequest(ChatJID=chat_jid),
            ),
            "Participants",
        )
        return decode_dataclass(
            GetGroupParticipantsReply,
            data,
            boundary="daemon.reply.Service.GetGroupParticipants",
        )

    def sync_avatar(self, jid: str) -> SyncAvatarReply:
        data = self._call("Service.SyncAvatar", SyncAvatarRequest(JID=jid))
        return decode_dataclass(SyncAvatarReply, data, boundary="daemon.reply.Service.SyncAvatar")

    def list_events(self, after_id: int = 0, limit: int = 100) -> ListEventsReply:
        data = _with_empty_list(
            self._call("Service.ListEvents", ListEventsRequest(AfterID=after_id, Limit=limit)),
            "Events",
        )
        return decode_dataclass(ListEventsReply, data, boundary="daemon.reply.Service.ListEvents")

    def delete_events(self, up_to_id: int) -> None:
        self._call("Service.DeleteEvents", DeleteEventsRequest(UpToID=up_to_id))

    def ensure_jid(self, jid: str) -> str:
        data = self._call("Service.EnsureJID", EnsureJIDRequest(JID=jid))
        reply = decode_dataclass(EnsureJIDReply, data, boundary="daemon.reply.Service.EnsureJID")
        return reply.JID

    def get_phone_number(self, jid: str) -> str:
        resolved = self.ensure_jid(jid)
        user = resolved.split("@")[0]
        if user.startswith("lid:"):
            return ""
        return "+" + user if user else ""

    def mark_read(self, chat_jid: str, message_ids: list[str], sender_jid: str = "") -> None:
        self._call(
            "Service.MarkRead",
            MarkReadRequest(ChatJID=chat_jid, SenderJID=sender_jid, MessageIDs=list(message_ids)),
        )

    def send_message(
        self,
        chat_jid: str,
        msg_type: str,
        text: str = "",
        file_path: str = "",
        caption: str = "",
        reply_context: Optional[dict[str, Any]] = None,
        mentioned_jids: Optional[list[str]] = None,
        duration_seconds: int = 0,
        ptt: bool = False,
    ) -> SendMessageReply:
        request = SendMessageRequest(
            ChatJID=chat_jid,
            Type=msg_type,
            Text=text,
            FilePath=file_path,
            Caption=caption,
            DurationSeconds=int(duration_seconds),
            PTT=bool(ptt),
            MentionedJIDs=list(mentioned_jids) if mentioned_jids else None,
            **_reply_context_fields(reply_context),
        )
        data = self._call("Service.SendMessage", request)
        return _decode_send_message_reply(data)

    def edit_message(
        self,
        chat_jid: str,
        message_id: str,
        text: str,
        reply_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        request = EditMessageRequest(
            ChatJID=chat_jid,
            MessageID=message_id,
            Text=text,
            **_reply_context_fields(reply_context),
        )
        result: dict[str, Any] = self._call("Service.EditMessage", request)
        return result

    def delete_message(self, chat_jid: str, message_id: str) -> dict[str, Any]:
        result: dict[str, Any] = self._call(
            "Service.DeleteMessage",
            DeleteMessageRequest(ChatJID=chat_jid, MessageID=message_id),
        )
        return result

    def get_chat_settings(self, chat_jid: str) -> GetChatSettingsReply:
        data = self._call("Service.GetChatSettings", GetChatSettingsRequest(ChatJID=chat_jid))
        return decode_dataclass(GetChatSettingsReply, data, boundary="daemon.reply.Service.GetChatSettings")

    def send_presence(self, available: bool) -> None:
        self._call("Service.SendPresence", SendPresenceRequest(Available=available))

    def subscribe_presence(self, jid: str) -> None:
        self._call("Service.SubscribePresence", SubscribePresenceRequest(JID=jid))

    def logout(self) -> None:
        self._call("Service.Logout")

    def set_muted(self, chat_jid: str, muted: bool) -> None:
        self._call("Service.SetMuted", SetMutedRequest(ChatJID=chat_jid, Muted=muted))

    def download_media(
        self,
        direct_path: str,
        media_key: str,
        file_enc_sha256: str,
        file_sha256: str,
        file_length: int,
        media_type: str,
        mimetype: str,
        message_id: str,
        chat_id: str,
        file_name: str = "",
    ) -> str:
        data = self._call(
            "Service.DownloadMedia",
            DownloadMediaRequest(
                DirectPath=direct_path,
                MediaKey=media_key,
                FileEncSHA256=file_enc_sha256,
                FileSHA256=file_sha256,
                FileLength=file_length,
                MediaType=media_type,
                Mimetype=mimetype,
                MessageID=message_id,
                ChatID=chat_id,
                FileName=file_name,
            ),
        )
        reply = decode_dataclass(DownloadMediaReply, data, boundary="daemon.reply.Service.DownloadMedia")
        return reply.FilePath

    def set_notification_counter(self, count: int, visible: bool) -> None:
        self._call(
            "Service.SetNotificationCounter",
            SetNotificationCounterRequest(Count=count, Visible=visible),
        )

    def clear_chat_notifications(self, tags: list[str]) -> None:
        self._call(
            "Service.ClearChatNotifications",
            ClearChatNotificationsRequest(Tags=list(tags)),
        )

    def pair_phone(self, phone: str) -> PairPhoneReply:
        data = self._call("Service.PairPhone", PairPhoneRequest(Phone=phone))
        return decode_dataclass(PairPhoneReply, data, boundary="daemon.reply.Service.PairPhone")


def set_daemon_client_factory(factory: DaemonClientFactory | None) -> None:
    global _daemon_client_factory
    _daemon_client_factory = factory


def daemon_client() -> DaemonClientProtocol:
    if _daemon_client_factory is not None:
        return _daemon_client_factory()
    return GreenlineDaemon()
