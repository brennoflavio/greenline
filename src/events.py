import base64
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Optional

from rpc import DaemonRPC
from ut_components.config import get_cache_path
from ut_components.event import Event

QR_IMAGE_PATH = os.path.join(get_cache_path(), "qr.png")


@dataclass
class SessionStatusResponse:
    logged_in: bool
    qr_image_path: str


class SessionStatusEvent(Event):
    def __init__(self):
        super().__init__(
            id="session-status",
            execution_interval=timedelta(seconds=2),
        )

    def trigger(self, metadata):
        try:
            result = DaemonRPC().get_session_status()
            logged_in = result.get("LoggedIn", False)
            qr_image_b64 = result.get("QRImage", "")
            qr_image_path = ""

            if not logged_in and qr_image_b64:
                os.makedirs(os.path.dirname(QR_IMAGE_PATH), exist_ok=True)
                with open(QR_IMAGE_PATH, "wb") as f:
                    f.write(base64.b64decode(qr_image_b64))
                qr_image_path = "file://" + QR_IMAGE_PATH

            return SessionStatusResponse(
                logged_in=logged_in,
                qr_image_path=qr_image_path,
            )
        except Exception:
            return SessionStatusResponse(logged_in=False, qr_image_path="")


class NewMessageEvent(Event):
    def __init__(self):
        super().__init__(id="new-message", execution_interval=timedelta(seconds=2))

    def trigger(self, metadata: Optional[Dict]):
        pass


class MessageStatusUpdateEvent(Event):
    def __init__(self):
        super().__init__(id="message-status-update", execution_interval=timedelta(seconds=5))

    def trigger(self, metadata: Optional[Dict]):
        pass


class ChatListUpdateEvent(Event):
    def __init__(self):
        super().__init__(id="chat-list-update", execution_interval=timedelta(seconds=30))

    def trigger(self, metadata: Optional[Dict]):
        pass
