from __future__ import annotations

import pytest
from contracts.qml_registry import validate_api_response
from qml_contract_helpers import DEFAULT_CHAT_ID

import daemon_types
import greenline.api.daemon as api_daemon
import main
from greenline.contracts.validation import BoundaryValidationError


class FakeDispatcher:
    def __init__(self) -> None:
        self.registered: list[str] = []
        self.started = False
        self.stopped = False

    def register_event(self, event) -> None:
        self.registered.append(event.id)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def test_check_daemon_version_contract(fake_daemon_service) -> None:
    fake_daemon_service.restarted = True

    result = main.check_daemon_version()

    validate_api_response("check_daemon_version", result)
    assert result == {"restarted": True}


def test_get_sync_status_contract_success_and_failure(fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_daemon_rpc.queue_events([daemon_types.StoredEvent(id=1, event_type="Presence", payload="{}", created_at=0)])
    success = main.get_sync_status()
    validate_api_response("get_sync_status", success)
    assert success is True

    def fail_list_events(self, *, after_id: int, limit: int):
        raise RuntimeError("daemon offline")

    monkeypatch.setattr(fake_daemon_rpc, "list_events", fail_list_events)
    failure = main.get_sync_status()
    validate_api_response("get_sync_status", failure)
    assert failure is False


def test_start_event_loop_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatcher = FakeDispatcher()
    monkeypatch.setattr(api_daemon, "get_event_dispatcher", lambda: dispatcher)

    result = main.start_event_loop()

    validate_api_response("start_event_loop", result)
    assert {"session-status", "daemon-event", "chat-list-update", "pending-message-retry"} == set(dispatcher.registered)
    assert dispatcher.started is True


def test_ping_daemon_contract_success_and_failure(fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch) -> None:
    success = main.ping_daemon()
    validate_api_response("ping_daemon", success)
    assert success == {"success": True, "message": "pong"}

    def fail_ping(self):
        raise RuntimeError("offline")

    monkeypatch.setattr(fake_daemon_rpc, "ping", fail_ping)
    failure = main.ping_daemon()
    validate_api_response("ping_daemon", failure)
    assert failure == {"success": False, "message": "offline"}


def test_check_daemon_status_contract(fake_daemon_service) -> None:
    fake_daemon_service.installed = True
    fake_daemon_service.active = False

    result = main.check_daemon_status()

    validate_api_response("check_daemon_status", result)
    assert result == {"installed": True, "active": True}
    assert ["systemctl", "--user", "start", "greenline.service"] in fake_daemon_service.subprocess_calls


def test_get_session_status_contract_success_and_failure(fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_daemon_rpc.session_status = daemon_types.SessionStatusReply(LoggedIn=True, QRCode="", QRImage="")
    success = main.get_session_status()
    validate_api_response("get_session_status", success)
    assert success == {"logged_in": True, "qr_image_path": ""}

    def fail_session(self):
        raise RuntimeError("offline")

    monkeypatch.setattr(fake_daemon_rpc, "get_session_status", fail_session)
    failure = main.get_session_status()
    validate_api_response("get_session_status", failure)
    assert failure == {"logged_in": False, "qr_image_path": ""}


def test_pair_phone_contract_success_and_failure(fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch) -> None:
    success = main.pair_phone("+15551234567")
    validate_api_response("pair_phone", success)
    assert success == {"success": True, "code": "12345678", "message": ""}

    def fail_pair(self, phone_number: str):
        raise RuntimeError("pair failed")

    monkeypatch.setattr(fake_daemon_rpc, "pair_phone", fail_pair)
    failure = main.pair_phone("+15551234567")
    validate_api_response("pair_phone", failure)
    assert failure == {"success": False, "code": "", "message": "pair failed"}


def test_get_session_status_contract_raises_boundary_validation_error(
    fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_session(self):
        raise BoundaryValidationError("bad session reply")

    monkeypatch.setattr(fake_daemon_rpc, "get_session_status", fail_session)

    with pytest.raises(BoundaryValidationError, match="bad session reply"):
        main.get_session_status()


def test_pair_phone_contract_raises_boundary_validation_error(fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_pair(self, phone_number: str):
        raise BoundaryValidationError("bad pair reply")

    monkeypatch.setattr(fake_daemon_rpc, "pair_phone", fail_pair)

    with pytest.raises(BoundaryValidationError, match="bad pair reply"):
        main.pair_phone("+15551234567")


def test_install_and_uninstall_daemon_contracts(fake_daemon_service) -> None:
    installed = main.install_daemon()
    validate_api_response("install_daemon", installed)
    assert installed["success"] is True
    assert fake_daemon_service.install_calls == 1

    uninstalled = main.uninstall_daemon()
    validate_api_response("uninstall_daemon", uninstalled)
    assert uninstalled["success"] is True
    assert fake_daemon_service.uninstall_calls == 1


def test_settings_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_daemon, "get_expected_daemon_version", lambda: "deadbeef")

    initial = main.get_settings()
    validate_api_response("get_settings", initial)
    assert initial == {
        "success": True,
        "notifications_suppressed": False,
        "error_reporting": True,
        "build_version": "deadbeef",
    }

    changed_notifications = main.set_notifications_suppressed(True)
    validate_api_response("set_notifications_suppressed", changed_notifications)
    assert changed_notifications == {"success": True, "message": ""}

    changed_reporting = main.set_error_reporting(False)
    validate_api_response("set_error_reporting", changed_reporting)
    assert changed_reporting == {"success": True, "message": ""}

    updated = main.get_settings()
    validate_api_response("get_settings", updated)
    assert updated == {
        "success": True,
        "notifications_suppressed": True,
        "error_reporting": False,
        "build_version": "deadbeef",
    }


def test_clear_data_contract(monkeypatch: pytest.MonkeyPatch, fake_daemon_service) -> None:
    dispatcher = FakeDispatcher()
    monkeypatch.setattr(api_daemon, "get_event_dispatcher", lambda: dispatcher)

    result = main.clear_data()

    validate_api_response("clear_data", result)
    assert result == {"success": True}
    assert dispatcher.stopped is True
    assert fake_daemon_service.uninstall_calls == 1


def test_get_phone_number_contract_success_and_failure(fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_daemon_rpc.phone_numbers = {DEFAULT_CHAT_ID: "+15551234567"}
    success = main.get_phone_number(DEFAULT_CHAT_ID)
    validate_api_response("get_phone_number", success)
    assert success == {"success": True, "phone_number": "+15551234567"}

    def fail_phone(self, jid: str):
        raise RuntimeError("lookup failed")

    monkeypatch.setattr(fake_daemon_rpc, "get_phone_number", fail_phone)
    failure = main.get_phone_number(DEFAULT_CHAT_ID)
    validate_api_response("get_phone_number", failure)
    assert failure == {"success": True, "phone_number": ""}


def test_get_phone_number_contract_boundary_validation_error_stays_soft(
    fake_daemon_rpc, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_phone(self, jid: str):
        raise BoundaryValidationError("bad phone reply")

    monkeypatch.setattr(fake_daemon_rpc, "get_phone_number", fail_phone)
    failure = main.get_phone_number(DEFAULT_CHAT_ID)
    validate_api_response("get_phone_number", failure)
    assert failure == {"success": True, "phone_number": ""}


def test_presence_commands_contract(fake_daemon_rpc) -> None:
    presence_result = main.send_presence(True)
    validate_api_response("send_presence", presence_result)
    assert fake_daemon_rpc.send_presence_calls == [True]

    subscribe_result = main.subscribe_presence(DEFAULT_CHAT_ID)
    validate_api_response("subscribe_presence", subscribe_result)
    assert fake_daemon_rpc.subscribe_presence_calls == [DEFAULT_CHAT_ID]

    group_result = main.subscribe_presence("group@g.us")
    validate_api_response("subscribe_presence", group_result)
    assert fake_daemon_rpc.subscribe_presence_calls == [DEFAULT_CHAT_ID]
