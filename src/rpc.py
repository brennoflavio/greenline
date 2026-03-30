import json
import socket
from typing import Any, Dict, Optional

from dacite import from_dict

from constants import DAEMON_SOCKET_PATH
from daemon_types import (
    GetContactsReply,
    GetGroupsReply,
    ListEventsReply,
    SessionStatusReply,
    VersionReply,
)


class RateLimitError(Exception):
    pass


class DaemonRPC:
    def __init__(self, socket_path: str = DAEMON_SOCKET_PATH) -> None:
        self._socket_path = socket_path
        self._id = 0

    def _call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self._id += 1
        request = {"method": method, "params": [params or {}], "id": self._id}

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._socket_path)
            sock.sendall(json.dumps(request).encode())
            sock.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            data = b"".join(chunks)
        finally:
            sock.close()

        if not data:
            raise Exception("Daemon returned empty response")
        response = json.loads(data.decode())
        if response.get("error"):
            error_msg = response["error"]
            if "429" in str(error_msg) or "rate" in str(error_msg).lower():
                raise RateLimitError(error_msg)
            raise Exception(error_msg)
        return response.get("result")

    def ping(self) -> str:
        result: str = self._call("Service.Ping")
        return result

    def get_version(self) -> VersionReply:
        return from_dict(data_class=VersionReply, data=self._call("Service.GetVersion"))

    def get_session_status(self) -> SessionStatusReply:
        return from_dict(data_class=SessionStatusReply, data=self._call("Service.GetSessionStatus"))

    def get_contacts(self) -> GetContactsReply:
        return from_dict(data_class=GetContactsReply, data=self._call("Service.GetContacts"))

    def get_groups(self) -> GetGroupsReply:
        data = self._call("Service.GetGroups")
        if data.get("Groups") is None:
            data["Groups"] = []
        return from_dict(data_class=GetGroupsReply, data=data)

    def list_events(self, after_id: int = 0, limit: int = 100) -> ListEventsReply:
        data = self._call("Service.ListEvents", {"AfterID": after_id, "Limit": limit})
        if data.get("Events") is None:
            data["Events"] = []
        return from_dict(data_class=ListEventsReply, data=data)

    def delete_events(self, up_to_id: int) -> None:
        self._call("Service.DeleteEvents", {"UpToID": up_to_id})

    def ensure_jid(self, jid: str) -> str:
        result = self._call("Service.EnsureJID", {"JID": jid})
        return str(result.get("JID", jid))

    def mark_read(self, chat_jid: str, message_ids: list[str], sender_jid: str = "") -> None:
        self._call(
            "Service.MarkRead",
            {"ChatJID": chat_jid, "SenderJID": sender_jid, "MessageIDs": message_ids},
        )

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
    ) -> str:
        result = self._call(
            "Service.DownloadMedia",
            {
                "DirectPath": direct_path,
                "MediaKey": media_key,
                "FileEncSHA256": file_enc_sha256,
                "FileSHA256": file_sha256,
                "FileLength": file_length,
                "MediaType": media_type,
                "Mimetype": mimetype,
                "MessageID": message_id,
                "ChatID": chat_id,
            },
        )
        return str(result.get("FilePath", ""))
