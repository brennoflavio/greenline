from __future__ import annotations

import ast
import inspect
from collections import defaultdict

from daemon_event_helpers import manifest_entries

from greenline.events import handlers

DAEMON_EVENT_CONTRACTS: dict[str, str] = {
    "Message": "handled",
    "Receipt": "handled",
    "UndecryptableMessage": "handled",
    "Contact": "handled",
    "Mute": "handled",
    "Picture": "parse-only",
    "AvatarSync": "handled",
    "PushName": "handled",
    "BusinessName": "handled",
    "Presence": "handled",
    "ChatPresence": "handled",
    "HistorySync": "handled",
    "GroupInfo": "parse-only",
    "Blocklist": "parse-only",
    "CallReject": "parse-only",
    "IdentityChange": "parse-only",
    "JoinedGroup": "parse-only",
    "UserAbout": "parse-only",
    "AppState": "ignored",
    "AppStateSyncComplete": "ignored",
    "AppStateSyncError": "ignored",
    "CallAccept": "ignored",
    "CallOffer": "ignored",
    "CallOfferNotice": "ignored",
    "CallRelayLatency": "ignored",
    "CallTerminate": "ignored",
    "Connected": "ignored",
    "KeepAliveRestored": "ignored",
    "KeepAliveTimeout": "ignored",
    "OfflineSyncCompleted": "ignored",
    "OfflineSyncPreview": "ignored",
    "PairError": "ignored",
    "PairSuccess": "ignored",
    "QR": "ignored",
}


def _event_type_constants_from_dispatcher() -> set[str]:
    tree = ast.parse(inspect.getsource(handlers._dispatch_event_inner))
    constants: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not isinstance(node.left, ast.Attribute) or node.left.attr != "event_type":
            continue
        if len(node.ops) != 1 or len(node.comparators) != 1:
            continue

        comparator = node.comparators[0]
        if isinstance(node.ops[0], ast.Eq) and isinstance(comparator, ast.Constant):
            constants.add(str(comparator.value))
        elif isinstance(node.ops[0], ast.In) and isinstance(comparator, ast.Tuple):
            constants.update(str(item.value) for item in comparator.elts if isinstance(item, ast.Constant))

    return constants


def test_daemon_event_contracts_match_dispatcher_branches() -> None:
    assert _event_type_constants_from_dispatcher() == set(DAEMON_EVENT_CONTRACTS)


def test_all_handled_and_parse_only_event_types_have_fixtures() -> None:
    fixture_event_types: dict[str, list[str]] = defaultdict(list)
    for entry in manifest_entries():
        fixture_event_types[entry["event_type"]].append(entry["path"])

    required = {
        event_type
        for event_type, classification in DAEMON_EVENT_CONTRACTS.items()
        if classification in {"handled", "parse-only"}
    }
    missing = sorted(event_type for event_type in required if not fixture_event_types[event_type])

    assert not missing, f"missing daemon event fixtures for: {missing}"
