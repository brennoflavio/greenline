import json
import socket
from typing import Any, Dict, Optional

from constants import DAEMON_SOCKET_PATH


class RateLimitError(Exception):
    pass


class DaemonNotReadyError(Exception):
    pass


class DaemonTimeoutError(Exception):
    pass


class DaemonRPC:
    def __init__(self, socket_path: str = DAEMON_SOCKET_PATH) -> None:
        self._socket_path = socket_path
        self._id = 0

    def _call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self._id += 1
        request = {"method": method, "params": [params or {}], "id": self._id}
        return self._call_once(request)

    def _call_once(self, request: Dict[str, Any]) -> Any:
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
            raise DaemonNotReadyError("Daemon returned empty response")
        response = json.loads(data.decode())
        if response.get("error"):
            error_msg = response["error"]
            error_msg_lower = str(error_msg).lower()
            if "429" in str(error_msg) or "rate" in error_msg_lower:
                raise RateLimitError(error_msg)
            if error_msg == "not logged in":
                raise DaemonNotReadyError(error_msg)
            if (
                "timed out" in error_msg_lower
                or "timeout" in error_msg_lower
                or "deadline exceeded" in error_msg_lower
                or "context deadline" in error_msg_lower
            ):
                raise DaemonTimeoutError(error_msg)
            raise Exception(error_msg)
        return response.get("result")
