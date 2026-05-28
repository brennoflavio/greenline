from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional, Protocol, TypeVar

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
    validate_json_like,
)
from greenline.reporting import error_trace_context
from rpc import DaemonRPC

T = TypeVar("T")


@dataclass
class EmptyRequest:
    pass


@dataclass
class EmptyReply:
    pass


@dataclass
class PingReply:
    Message: str


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
    JID: str


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
    ReplyQuotedMessageJSON: str | None = None
    MentionedJIDs: list[str] | None = None


@dataclass
class EditMessageRequest:
    ChatJID: str
    MessageID: str
    Text: str
    ReplyToMessageID: str | None = None
    ReplyParticipantJID: str | None = None
    ReplyQuotedMessageJSON: str | None = None


@dataclass
class DeleteMessageRequest:
    ChatJID: str
    MessageID: str


@dataclass
class EditMessageReply:
    MessageID: str
    Timestamp: int


@dataclass
class DeleteMessageReply:
    MessageID: str
    Timestamp: int


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
    FilePath: str


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
    def ping(self) -> PingReply: ...

    def get_version(self) -> VersionReply: ...

    def get_session_status(self) -> SessionStatusReply: ...

    def get_contacts(self) -> GetContactsReply: ...

    def get_groups(self) -> GetGroupsReply: ...

    def get_group_participants(self, chat_jid: str) -> GetGroupParticipantsReply: ...

    def sync_avatar(self, jid: str) -> SyncAvatarReply: ...

    def list_events(self, after_id: int = 0, limit: int = 100) -> ListEventsReply: ...

    def delete_events(self, up_to_id: int) -> EmptyReply: ...

    def ensure_jid(self, jid: str) -> EnsureJIDReply: ...

    def get_phone_number(self, jid: str) -> str: ...

    def mark_read(self, chat_jid: str, message_ids: list[str], sender_jid: str = "") -> EmptyReply: ...

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
    ) -> EditMessageReply: ...

    def delete_message(self, chat_jid: str, message_id: str) -> DeleteMessageReply: ...

    def get_chat_settings(self, chat_jid: str) -> GetChatSettingsReply: ...

    def send_presence(self, available: bool) -> EmptyReply: ...

    def subscribe_presence(self, jid: str) -> EmptyReply: ...

    def logout(self) -> EmptyReply: ...

    def set_muted(self, chat_jid: str, muted: bool) -> EmptyReply: ...

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
    ) -> DownloadMediaReply: ...

    def set_notification_counter(self, count: int, visible: bool) -> EmptyReply: ...

    def clear_chat_notifications(self, tags: list[str]) -> EmptyReply: ...

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
    quoted_message_json = str(reply_context.get("quoted_message_json") or "")
    if quoted_message_json:
        fields["ReplyQuotedMessageJSON"] = quoted_message_json
    return fields


def _with_empty_list(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and data[key] is None:
        data = dict(data)
        data[key] = []
    return data


def _decode_reply(data_class: type[T], data: Any, *, contract: str) -> T:
    with error_trace_context("daemon_rpc", contract=contract, direction="decode"):
        return decode_dataclass(
            data_class,
            data,
            boundary="daemon_rpc",
            contract=contract,
            direction="decode",
        )


def _decode_empty_reply(data: Any, *, contract: str) -> EmptyReply:
    with error_trace_context("daemon_rpc", contract=contract, direction="decode"):
        if data is None or data == {}:
            return EmptyReply()
        if validate_json_like(data, boundary="daemon_rpc", contract=contract, direction="decode"):
            report_validation_failure(
                "daemon_rpc",
                BoundaryValidationError(f"{contract} reply must be empty"),
                payload=data,
                contract=contract,
                direction="decode",
                dataclass_name=EmptyReply.__name__,
            )
        return EmptyReply()


def _decode_ping_reply(data: Any) -> PingReply:
    with error_trace_context("daemon_rpc", contract="Service.Ping", direction="decode"):
        if isinstance(data, str):
            return PingReply(Message=data)
        error = BoundaryValidationError("Service.Ping reply requires a string message")
        report_validation_failure(
            "daemon_rpc",
            error,
            payload=data,
            contract="Service.Ping",
            direction="decode",
            dataclass_name=PingReply.__name__,
        )
        raise error


def _decode_send_message_reply(data: Any) -> SendMessageReply:
    with error_trace_context("daemon_rpc", contract="Service.SendMessage", direction="decode"):
        reply = decode_dataclass(
            SendMessageReply,
            data,
            boundary="daemon_rpc",
            contract="Service.SendMessage",
            direction="decode",
        )
        if not reply.MessageID or reply.Timestamp <= 0:
            error = BoundaryValidationError(
                "Service.SendMessage reply requires non-empty MessageID and positive Timestamp"
            )
            report_validation_failure(
                "daemon_rpc",
                error,
                payload=data,
                contract="Service.SendMessage",
                direction="decode",
                dataclass_name=SendMessageReply.__name__,
            )
            raise error
        return reply


class GreenlineDaemon:
    def __init__(self, transport: DaemonRPC | None = None) -> None:
        self._transport = transport or DaemonRPC()

    def _call(self, method: str, request: Any | None = None) -> Any:
        with error_trace_context("daemon_rpc", contract=method, direction="encode"):
            params = None
            if request is not None:
                params = _without_none(
                    encode_dataclass(
                        request,
                        boundary="daemon_rpc",
                        contract=method,
                        direction="encode",
                    )
                )
            return self._transport._call(method, params)

    def ping(self) -> PingReply:
        return _decode_ping_reply(self._call("Service.Ping", EmptyRequest()))

    def get_version(self) -> VersionReply:
        return _decode_reply(
            VersionReply, self._call("Service.GetVersion", EmptyRequest()), contract="Service.GetVersion"
        )

    def get_session_status(self) -> SessionStatusReply:
        return _decode_reply(
            SessionStatusReply,
            self._call("Service.GetSessionStatus", EmptyRequest()),
            contract="Service.GetSessionStatus",
        )

    def get_contacts(self) -> GetContactsReply:
        return _decode_reply(
            GetContactsReply, self._call("Service.GetContacts", EmptyRequest()), contract="Service.GetContacts"
        )

    def get_groups(self) -> GetGroupsReply:
        data = _with_empty_list(self._call("Service.GetGroups", EmptyRequest()), "Groups")
        return _decode_reply(GetGroupsReply, data, contract="Service.GetGroups")

    def get_group_participants(self, chat_jid: str) -> GetGroupParticipantsReply:
        data = _with_empty_list(
            self._call(
                "Service.GetGroupParticipants",
                GetGroupParticipantsRequest(ChatJID=chat_jid),
            ),
            "Participants",
        )
        return _decode_reply(GetGroupParticipantsReply, data, contract="Service.GetGroupParticipants")

    def sync_avatar(self, jid: str) -> SyncAvatarReply:
        data = self._call("Service.SyncAvatar", SyncAvatarRequest(JID=jid))
        return _decode_reply(SyncAvatarReply, data, contract="Service.SyncAvatar")

    def list_events(self, after_id: int = 0, limit: int = 100) -> ListEventsReply:
        data = _with_empty_list(
            self._call("Service.ListEvents", ListEventsRequest(AfterID=after_id, Limit=limit)),
            "Events",
        )
        return _decode_reply(ListEventsReply, data, contract="Service.ListEvents")

    def delete_events(self, up_to_id: int) -> EmptyReply:
        data = self._call("Service.DeleteEvents", DeleteEventsRequest(UpToID=up_to_id))
        return _decode_empty_reply(data, contract="Service.DeleteEvents")

    def ensure_jid(self, jid: str) -> EnsureJIDReply:
        data = self._call("Service.EnsureJID", EnsureJIDRequest(JID=jid))
        return _decode_reply(EnsureJIDReply, data, contract="Service.EnsureJID")

    def get_phone_number(self, jid: str) -> str:
        resolved = self.ensure_jid(jid).JID
        user = resolved.split("@")[0]
        if user.startswith("lid:"):
            return ""
        return "+" + user if user else ""

    def mark_read(self, chat_jid: str, message_ids: list[str], sender_jid: str = "") -> EmptyReply:
        data = self._call(
            "Service.MarkRead",
            MarkReadRequest(ChatJID=chat_jid, SenderJID=sender_jid, MessageIDs=list(message_ids)),
        )
        return _decode_empty_reply(data, contract="Service.MarkRead")

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
    ) -> EditMessageReply:
        request = EditMessageRequest(
            ChatJID=chat_jid,
            MessageID=message_id,
            Text=text,
            **_reply_context_fields(reply_context),
        )
        data = self._call("Service.EditMessage", request)
        return _decode_reply(EditMessageReply, data, contract="Service.EditMessage")

    def delete_message(self, chat_jid: str, message_id: str) -> DeleteMessageReply:
        data = self._call(
            "Service.DeleteMessage",
            DeleteMessageRequest(ChatJID=chat_jid, MessageID=message_id),
        )
        return _decode_reply(DeleteMessageReply, data, contract="Service.DeleteMessage")

    def get_chat_settings(self, chat_jid: str) -> GetChatSettingsReply:
        data = self._call("Service.GetChatSettings", GetChatSettingsRequest(ChatJID=chat_jid))
        return _decode_reply(GetChatSettingsReply, data, contract="Service.GetChatSettings")

    def send_presence(self, available: bool) -> EmptyReply:
        data = self._call("Service.SendPresence", SendPresenceRequest(Available=available))
        return _decode_empty_reply(data, contract="Service.SendPresence")

    def subscribe_presence(self, jid: str) -> EmptyReply:
        data = self._call("Service.SubscribePresence", SubscribePresenceRequest(JID=jid))
        return _decode_empty_reply(data, contract="Service.SubscribePresence")

    def logout(self) -> EmptyReply:
        data = self._call("Service.Logout", EmptyRequest())
        return _decode_empty_reply(data, contract="Service.Logout")

    def set_muted(self, chat_jid: str, muted: bool) -> EmptyReply:
        data = self._call("Service.SetMuted", SetMutedRequest(ChatJID=chat_jid, Muted=muted))
        return _decode_empty_reply(data, contract="Service.SetMuted")

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
    ) -> DownloadMediaReply:
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
        return _decode_reply(DownloadMediaReply, data, contract="Service.DownloadMedia")

    def set_notification_counter(self, count: int, visible: bool) -> EmptyReply:
        data = self._call(
            "Service.SetNotificationCounter",
            SetNotificationCounterRequest(Count=count, Visible=visible),
        )
        return _decode_empty_reply(data, contract="Service.SetNotificationCounter")

    def clear_chat_notifications(self, tags: list[str]) -> EmptyReply:
        data = self._call(
            "Service.ClearChatNotifications",
            ClearChatNotificationsRequest(Tags=list(tags)),
        )
        return _decode_empty_reply(data, contract="Service.ClearChatNotifications")

    def pair_phone(self, phone: str) -> PairPhoneReply:
        data = self._call("Service.PairPhone", PairPhoneRequest(Phone=phone))
        return _decode_reply(PairPhoneReply, data, contract="Service.PairPhone")


def set_daemon_client_factory(factory: DaemonClientFactory | None) -> None:
    global _daemon_client_factory
    _daemon_client_factory = factory


def daemon_client() -> DaemonClientProtocol:
    if _daemon_client_factory is not None:
        return _daemon_client_factory()
    return GreenlineDaemon()
