import os
import shutil
import time
from dataclasses import dataclass

from daemon import (
    ensure_daemon_version,
    install_background_service_files,
    is_daemon_active,
    is_daemon_installed,
    remove_background_service_files,
    run_subprocess,
)
from greenline.api.common import SuccessResponse
from greenline.contracts.daemon import daemon_client
from greenline.contracts.kv import GreenlineKV
from greenline.contracts.validation import BoundaryValidationError
from greenline.events.chat_sync import ChatListUpdateEvent, DaemonEventHandler
from greenline.events.session import LAST_EVENT_ID_KEY, SessionStatusEvent
from greenline.session import SessionStatusResponse, build_session_status_response
from greenline.store.identity import clear_chat_runtime_cache
from greenline.store.records import (
    DaemonLastEventIDRecord,
    NotificationsSuppressedRecord,
)
from pending_outbox import PendingMessageRetryEvent
from unread_counter import reconcile_unread_total
from ut_components.config import get_cache_path, get_config_path
from ut_components.crash import crash_reporter
from ut_components.event import get_event_dispatcher
from ut_components.utils import dataclass_to_dict

NOTIFICATIONS_SUPPRESSED_KEY = "notifications_suppressed"


@dataclass
class EnsureDaemonVersionResponse:
    restarted: bool


@dataclass
class DaemonStatusResponse:
    installed: bool
    active: bool


@dataclass
class ClearDataResponse:
    success: bool


@dataclass
class PairPhoneResponse:
    success: bool
    code: str
    message: str


@dataclass
class SettingsResponse:
    success: bool
    notifications_suppressed: bool


@dataclass
class PhoneNumberResponse:
    success: bool
    phone_number: str


@crash_reporter
@dataclass_to_dict
def check_daemon_version() -> EnsureDaemonVersionResponse:
    restarted = ensure_daemon_version()
    return EnsureDaemonVersionResponse(restarted=restarted)


def get_sync_status() -> bool:
    try:
        with GreenlineKV() as kv:
            last_id = kv.get_record(LAST_EVENT_ID_KEY, default=DaemonLastEventIDRecord(0)).value
        reply = daemon_client().list_events(after_id=last_id, limit=1)
        return bool(reply.Events)
    except BoundaryValidationError:
        raise
    except Exception:
        return False


def start_event_loop() -> None:
    from greenline.api.messages import _resolve_reply_context

    reconcile_unread_total()
    dispatcher = get_event_dispatcher()
    dispatcher.register_event(SessionStatusEvent())
    dispatcher.register_event(DaemonEventHandler())
    dispatcher.register_event(ChatListUpdateEvent())
    dispatcher.register_event(PendingMessageRetryEvent(_resolve_reply_context))
    dispatcher.start()


@crash_reporter
@dataclass_to_dict
def ping_daemon() -> SuccessResponse:
    try:
        result = daemon_client().ping().Message
        return SuccessResponse(success=True, message=result)
    except Exception as error:
        return SuccessResponse(success=False, message=str(error))


@crash_reporter
@dataclass_to_dict
def check_daemon_status() -> DaemonStatusResponse:
    installed = is_daemon_installed()
    if installed and not is_daemon_active():
        run_subprocess(["systemctl", "--user", "start", "greenline.service"])
        for _ in range(10):
            time.sleep(0.5)
            try:
                daemon_client().ping().Message
                break
            except Exception:
                continue
    return DaemonStatusResponse(
        installed=installed,
        active=is_daemon_active(),
    )


@crash_reporter
@dataclass_to_dict
def get_session_status() -> SessionStatusResponse:
    try:
        result = daemon_client().get_session_status()
        return build_session_status_response(
            logged_in=result.LoggedIn,
            qr_image_base64=result.QRImage,
        )
    except Exception:
        return SessionStatusResponse(logged_in=False, qr_image_path="")


@crash_reporter
@dataclass_to_dict
def pair_phone(phone_number: str) -> PairPhoneResponse:
    try:
        reply = daemon_client().pair_phone(phone_number)
        return PairPhoneResponse(success=True, code=reply.Code, message="")
    except Exception as error:
        return PairPhoneResponse(success=False, code="", message=str(error))


@crash_reporter
@dataclass_to_dict
def install_daemon() -> SuccessResponse:
    try:
        install_background_service_files()
        return SuccessResponse(success=True, message="Daemon installed.")
    except Exception as error:
        return SuccessResponse(success=False, message=str(error))


@crash_reporter
@dataclass_to_dict
def uninstall_daemon() -> SuccessResponse:
    try:
        remove_background_service_files()
        return SuccessResponse(success=True, message="Daemon uninstalled.")
    except Exception as error:
        return SuccessResponse(success=False, message=str(error))


@crash_reporter
@dataclass_to_dict
def get_settings() -> SettingsResponse:
    try:
        with GreenlineKV() as kv:
            suppressed = kv.get_record(
                NOTIFICATIONS_SUPPRESSED_KEY,
                default=NotificationsSuppressedRecord(False),
            ).value
        return SettingsResponse(success=True, notifications_suppressed=suppressed)
    except BoundaryValidationError:
        raise
    except Exception:
        return SettingsResponse(success=False, notifications_suppressed=False)


@crash_reporter
@dataclass_to_dict
def set_notifications_suppressed(suppressed: bool) -> SuccessResponse:
    try:
        with GreenlineKV() as kv:
            kv.put_record(NOTIFICATIONS_SUPPRESSED_KEY, NotificationsSuppressedRecord(bool(suppressed)))
        return SuccessResponse(success=True, message="")
    except Exception as error:
        return SuccessResponse(success=False, message=str(error))


@crash_reporter
@dataclass_to_dict
def clear_data() -> ClearDataResponse:
    dispatcher = get_event_dispatcher()
    dispatcher.stop()  # type: ignore[no-untyped-call]

    try:
        daemon_client().logout()
    except Exception:
        pass

    config_path = get_config_path()
    if os.path.exists(config_path):
        shutil.rmtree(config_path)

    cache_path = get_cache_path()
    if os.path.exists(cache_path):
        shutil.rmtree(cache_path)

    clear_chat_runtime_cache()
    remove_background_service_files()
    return ClearDataResponse(success=True)


@crash_reporter
@dataclass_to_dict
def get_phone_number(jid: str) -> PhoneNumberResponse:
    try:
        phone = daemon_client().get_phone_number(jid)
        return PhoneNumberResponse(success=True, phone_number=phone)
    except Exception:
        return PhoneNumberResponse(success=True, phone_number="")


def send_presence(available: bool) -> None:
    try:
        daemon_client().send_presence(available)
    except Exception:
        pass


def subscribe_presence(chat_id: str) -> None:
    if "@g.us" in chat_id:
        return
    try:
        daemon_client().subscribe_presence(chat_id)
    except Exception:
        pass
