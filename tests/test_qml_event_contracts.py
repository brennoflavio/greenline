from __future__ import annotations

import time

from contracts.qml_registry import EVENT_CONTRACTS, validate_event_payload
from daemon_event_helpers import load_fixtures, seed_prerequisite_kv
from qml_contract_helpers import DEFAULT_CHAT_ID, seed_chat, seed_message

import daemon_types
import main
from models import ReadReceipt

FIXTURE_BY_PATH = {fixture.relative_path: fixture for fixture in load_fixtures()}


def _payloads(fake_pyotherside, name: str) -> list[object]:
    return [payload for event_name, payload in fake_pyotherside.sent if event_name == name]


def _validate_captured(fake_pyotherside) -> None:
    for event_name, payload in fake_pyotherside.sent:
        validate_event_payload(event_name, payload)


def test_session_status_event_contract(fake_daemon_rpc, fake_pyotherside_module) -> None:
    from greenline.events.session import SessionStatusEvent
    from ut_components.event import EventDispatcher

    fake_daemon_rpc.session_status = daemon_types.SessionStatusReply(LoggedIn=True, QRCode="", QRImage="")
    dispatcher = EventDispatcher()
    dispatcher.register_event(SessionStatusEvent())
    dispatcher.schedule("session-status")

    dispatcher._process()

    payload = _payloads(fake_pyotherside_module, "session-status")[-1]
    validate_event_payload("session-status", payload)


def test_daemon_event_handler_contracts_for_sync_message_chat_photo_presence(
    fake_daemon_rpc, fake_pyotherside_module
) -> None:
    from greenline.events.chat_sync import DaemonEventHandler

    picture_fixture = FIXTURE_BY_PATH["event/picture_update.json"]
    seed_prerequisite_kv(picture_fixture)
    fake_daemon_rpc.queue_events(
        [
            FIXTURE_BY_PATH["message/conversation.json"].stored_event(),
            FIXTURE_BY_PATH["event/picture_update.json"].stored_event(),
            FIXTURE_BY_PATH["event/presence_online.json"].stored_event(),
            FIXTURE_BY_PATH["event/chatpresence.json"].stored_event(),
        ],
        [],
    )

    DaemonEventHandler()._do_trigger()

    _validate_captured(fake_pyotherside_module)
    for event_name in (
        "sync-status",
        "message-upsert",
        "chat-list-update",
        "sender-photo-update",
        "presence-update",
        "chat-presence",
    ):
        assert _payloads(fake_pyotherside_module, event_name), event_name


def test_message_reaction_update_event_contract(fake_daemon_rpc, fake_pyotherside_module) -> None:
    from greenline.events.chat_sync import DaemonEventHandler

    reaction_fixture = FIXTURE_BY_PATH["message/reaction_ignored.json"]
    seed_prerequisite_kv(reaction_fixture)
    fake_daemon_rpc.queue_events([reaction_fixture.stored_event()], [])

    DaemonEventHandler()._do_trigger()

    _validate_captured(fake_pyotherside_module)
    assert _payloads(fake_pyotherside_module, "message-reaction-update")
    assert _payloads(fake_pyotherside_module, "message-upsert")


def test_chat_draft_update_event_contract(fake_pyotherside_module) -> None:
    main.set_chat_draft(DEFAULT_CHAT_ID, "Draft", [])

    _validate_captured(fake_pyotherside_module)
    assert _payloads(fake_pyotherside_module, "chat-draft-update")


def test_chat_list_update_event_contract_from_mute_mark_read_edit_delete_and_pending(
    fake_pyotherside_module,
) -> None:
    now = int(time.time())
    seed_chat(DEFAULT_CHAT_ID, unread_count=1, muted=False)
    seed_message(DEFAULT_CHAT_ID, "incoming", is_outgoing=False, read_receipt=ReadReceipt.NONE, timestamp_unix=now - 2)
    seed_message(DEFAULT_CHAT_ID, "editable", is_outgoing=True, read_receipt=ReadReceipt.SENT, timestamp_unix=now - 1)
    seed_message(DEFAULT_CHAT_ID, "deletable", is_outgoing=True, read_receipt=ReadReceipt.SENT, timestamp_unix=now)

    main.start_event_loop()
    main.toggle_mute(DEFAULT_CHAT_ID)
    main.mark_messages_as_read(DEFAULT_CHAT_ID)
    main.edit_text_message(DEFAULT_CHAT_ID, "editable", "Edited")
    main.delete_message(DEFAULT_CHAT_ID, "deletable")
    main.send_text_message(DEFAULT_CHAT_ID, "Pending", "pending-event")

    _validate_captured(fake_pyotherside_module)
    assert len(_payloads(fake_pyotherside_module, "chat-list-update")) >= 5
    assert _payloads(fake_pyotherside_module, "message-upsert")


def test_message_upsert_event_contract_from_download_and_audio_failure(tmp_path, fake_pyotherside_module) -> None:
    from qml_contract_helpers import raw_downloadable_media

    from models import MessageType

    seed_chat(DEFAULT_CHAT_ID)
    seed_message(
        DEFAULT_CHAT_ID,
        "downloadable",
        message_type=MessageType.IMAGE,
        is_outgoing=False,
        raw=raw_downloadable_media("image"),
        reply_to_id="",
    )

    main.download_media(DEFAULT_CHAT_ID, "downloadable", "image")
    main.send_audio_message(DEFAULT_CHAT_ID, str(tmp_path / "missing.ogg"), 5, "failed-audio", None)

    _validate_captured(fake_pyotherside_module)
    assert len(_payloads(fake_pyotherside_module, "message-upsert")) >= 2


def test_all_registered_events_have_contract_tests() -> None:
    expected = {
        "session-status",
        "sync-status",
        "message-upsert",
        "message-reaction-update",
        "chat-list-update",
        "sender-photo-update",
        "presence-update",
        "chat-presence",
        "chat-draft-update",
    }

    assert set(EVENT_CONTRACTS) == expected
