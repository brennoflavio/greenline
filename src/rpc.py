import json
import socket
from typing import Any, Dict, Optional

from dacite import from_dict

from constants import DAEMON_SOCKET_PATH
from daemon_types import (
    GetContactInfoReply,
    GetContactsReply,
    GetProfilePictureReply,
    ListEventsReply,
    SessionStatusReply,
    VersionReply,
)


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
            raise Exception(response["error"])
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

    def get_contact_info(self, jid: str) -> GetContactInfoReply:
        return from_dict(data_class=GetContactInfoReply, data=self._call("Service.GetContactInfo", {"JID": jid}))

    def get_profile_picture(self, jid: str, existing_id: str = "") -> GetProfilePictureReply:
        return from_dict(
            data_class=GetProfilePictureReply,
            data=self._call("Service.GetProfilePicture", {"JID": jid, "ExistingID": existing_id}),
        )

    def list_events(self, after_id: int = 0, limit: int = 100) -> ListEventsReply:
        data = self._call("Service.ListEvents", {"AfterID": after_id, "Limit": limit})
        if data.get("Events") is None:
            data["Events"] = []
        return from_dict(data_class=ListEventsReply, data=data)

    def delete_events(self, up_to_id: int) -> None:
        self._call("Service.DeleteEvents", {"UpToID": up_to_id})
