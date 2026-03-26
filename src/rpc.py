import json
import socket

from constants import DAEMON_SOCKET_PATH


class DaemonRPC:
    def __init__(self, socket_path=DAEMON_SOCKET_PATH):
        self._socket_path = socket_path
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        request = {"method": method, "params": [params or {}], "id": self._id}

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._socket_path)
            sock.sendall(json.dumps(request).encode())
            data = sock.recv(4096)
        finally:
            sock.close()

        response = json.loads(data.decode())
        if response.get("error"):
            raise Exception(response["error"])
        return response.get("result")

    def ping(self):
        return self.call("Service.Ping")

    def get_version(self):
        return self.call("Service.GetVersion")

    def get_session_status(self):
        return self.call("Service.GetSessionStatus")
