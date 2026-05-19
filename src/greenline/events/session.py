from datetime import timedelta
from typing import Any, Dict, Optional

from greenline.session import SessionStatusResponse, build_session_status_response
from rpc import DaemonNotReadyError, DaemonRPC, DaemonTimeoutError
from ut_components.event import Event

LAST_EVENT_ID_KEY = "daemon:last_event_id"


class SessionStatusEvent(Event):
    def __init__(self) -> None:
        super().__init__(
            id="session-status",
            execution_interval=timedelta(seconds=2),
        )

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> Optional[SessionStatusResponse]:
        try:
            result = DaemonRPC().get_session_status()
        except (ConnectionRefusedError, DaemonNotReadyError, DaemonTimeoutError):
            return None

        return build_session_status_response(
            logged_in=result.LoggedIn,
            qr_image_base64=result.QRImage,
        )
