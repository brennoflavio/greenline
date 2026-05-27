from datetime import timedelta
from typing import Any, Dict, Optional

from greenline import qml_payloads
from greenline.contracts.daemon import daemon_client
from greenline.contracts.qml import validate_qml_event
from greenline.session import build_session_status_response
from rpc import DaemonNotReadyError, DaemonTimeoutError
from ut_components.event import Event

LAST_EVENT_ID_KEY = "daemon:last_event_id"


class SessionStatusEvent(Event):
    def __init__(self) -> None:
        super().__init__(
            id="session-status",
            execution_interval=timedelta(seconds=2),
        )

    def trigger(self, metadata: Optional[Dict[str, Any]]) -> Optional[dict[str, Any]]:
        try:
            result = daemon_client().get_session_status()
        except (ConnectionRefusedError, DaemonNotReadyError, DaemonTimeoutError):
            return None

        status = build_session_status_response(
            logged_in=result.LoggedIn,
            qr_image_base64=result.QRImage,
        )
        payload = qml_payloads.session_status(status.logged_in, status.qr_image_path)
        validate_qml_event("session-status", payload)
        return payload
