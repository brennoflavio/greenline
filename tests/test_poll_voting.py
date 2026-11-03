from __future__ import annotations

import main
from qml_contract_helpers import seed_message


def test_group_poll_vote_preserves_original_sender_and_option(
    fake_daemon_rpc,
) -> None:
    chat_id = "fixture-group-1@g.us"
    message_id = "poll-message-1"
    sender_jid = "fixture-user-5@lid"

    seed_message(
        chat_id,
        message_id,
        sender=sender_jid,
        sender_raw=sender_jid,
        raw={
            "Info": {
                "Chat": chat_id,
                "Sender": sender_jid,
                "IsFromMe": False,
            },
            "Message": {
                "pollCreationMessageV3": {
                    "name": "Valitse vaihtoehto",
                    "options": [
                        {"optionName": "Ensimmäinen"},
                        {"optionName": "Toinen"},
                        {"optionName": "Kolmas"},
                    ],
                    "selectableOptionsCount": 1,
                }
            },
        },
    )

    result = main.send_poll_vote(chat_id, message_id, [1])

    assert result["success"] is True, result
    assert fake_daemon_rpc.send_poll_vote_calls == [
        {
            "chat_jid": chat_id,
            "poll_message_id": message_id,
            "poll_sender_jid": sender_jid,
            "poll_from_me": False,
            "option_names": ["Toinen"],
        }
    ]


import pytest


@pytest.mark.parametrize(
    ("indices", "expected_error"),
    [
        ([], "Invalid poll option selection"),
        ([3], "Invalid poll option selection"),
        ([-1], "Invalid poll option selection"),
        ([0, 0], "Invalid poll option selection"),
        ([0, 1], "Too many selected options"),
    ],
)
def test_poll_vote_rejects_invalid_selection(
    fake_daemon_rpc,
    indices,
    expected_error,
) -> None:
    chat_id = "fixture-group-1@g.us"
    message_id = "poll-invalid"

    seed_message(
        chat_id,
        message_id,
        raw={
            "Info": {"Sender": "fixture-user-5@lid"},
            "Message": {
                "pollCreationMessageV3": {
                    "name": "Testikysely",
                    "options": [
                        {"optionName": "Kyllä"},
                        {"optionName": "Ei"},
                        {"optionName": "Ehkä"},
                    ],
                    "selectableOptionsCount": 1,
                }
            },
        },
    )

    result = main.send_poll_vote(chat_id, message_id, indices)

    assert result["success"] is False
    assert result["message"] == expected_error
    assert fake_daemon_rpc.send_poll_vote_calls == []


def test_group_poll_vote_rejects_missing_original_sender(
    fake_daemon_rpc,
) -> None:
    chat_id = "fixture-group-1@g.us"

    seed_message(
        chat_id,
        "poll-no-sender",
        raw={
            "Info": {},
            "Message": {
                "pollCreationMessageV3": {
                    "name": "Testikysely",
                    "options": [{"optionName": "Kyllä"}],
                    "selectableOptionsCount": 1,
                }
            },
        },
    )

    result = main.send_poll_vote(chat_id, "poll-no-sender", [0])

    assert result["success"] is False
    assert result["message"] == "Original group poll sender unavailable"
    assert fake_daemon_rpc.send_poll_vote_calls == []


def test_poll_vote_allows_multiple_options(
    fake_daemon_rpc,
) -> None:
    chat_id = "fixture-group-1@g.us"
    message_id = "poll-multiple"
    sender_jid = "fixture-user-5@lid"

    seed_message(
        chat_id,
        message_id,
        raw={
            "Info": {"Sender": sender_jid},
            "Message": {
                "pollCreationMessageV3": {
                    "name": "Valitse kaksi",
                    "options": [
                        {"optionName": "A"},
                        {"optionName": "B"},
                        {"optionName": "C"},
                    ],
                    "selectableOptionsCount": 2,
                }
            },
        },
    )

    result = main.send_poll_vote(chat_id, message_id, [0, 2])

    assert result["success"] is True
    assert fake_daemon_rpc.send_poll_vote_calls == [
        {
            "chat_jid": chat_id,
            "poll_message_id": message_id,
            "poll_sender_jid": sender_jid,
            "poll_from_me": False,
            "option_names": ["A", "C"],
        }
    ]


def test_poll_vote_reports_daemon_failure(
    fake_daemon_rpc,
) -> None:
    chat_id = "fixture-group-1@g.us"
    message_id = "poll-failure"

    seed_message(
        chat_id,
        message_id,
        raw={
            "Info": {"Sender": "fixture-user-5@lid"},
            "Message": {
                "pollCreationMessageV3": {
                    "name": "Testikysely",
                    "options": [{"optionName": "Kyllä"}],
                    "selectableOptionsCount": 1,
                }
            },
        },
    )

    fake_daemon_rpc.send_poll_vote_exception = RuntimeError(
        "Simulated daemon failure"
    )

    result = main.send_poll_vote(chat_id, message_id, [0])

    assert result["success"] is False
    assert result["message"] == "Simulated daemon failure"
    assert len(fake_daemon_rpc.send_poll_vote_calls) == 1
