from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import ut_components
import ut_components.config as ut_config

ut_components.setup("greenline.tests", None)
ut_config.APP_NAME_ = "greenline.tests"

import daemon_types
from greenline.contracts.daemon import (
    DeleteMessageReply,
    DownloadMediaReply,
    EditMessageReply,
    EmptyReply,
    EnsureJIDReply,
    PingReply,
)


class FakePyOtherSide(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("pyotherside")
        self.sent: list[tuple[str, Any]] = []

    def send(self, event_id: str, payload: Any = None) -> None:
        self.sent.append((event_id, payload))


fake_pyotherside = FakePyOtherSide()
sys.modules["pyotherside"] = fake_pyotherside


class FakeDaemonService:
    installed = True
    active = True
    restarted = False
    install_calls = 0
    uninstall_calls = 0
    subprocess_calls: list[list[str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.installed = True
        cls.active = True
        cls.restarted = False
        cls.install_calls = 0
        cls.uninstall_calls = 0
        cls.subprocess_calls = []

    @classmethod
    def ensure_daemon_version(cls) -> bool:
        return cls.restarted

    @classmethod
    def install_background_service_files(cls) -> None:
        cls.install_calls += 1
        cls.installed = True
        cls.active = True

    @classmethod
    def remove_background_service_files(cls) -> None:
        cls.uninstall_calls += 1
        cls.installed = False
        cls.active = False

    @classmethod
    def is_daemon_installed(cls) -> bool:
        return cls.installed

    @classmethod
    def is_daemon_active(cls) -> bool:
        return cls.active

    @classmethod
    def run_subprocess(cls, args: list[str]) -> types.SimpleNamespace:
        cls.subprocess_calls.append(list(args))
        if args[:3] == ["systemctl", "--user", "start"]:
            cls.active = True
        return types.SimpleNamespace(returncode=0, stdout="")


class FakeDaemonRPC:
    list_event_batches: list[list[daemon_types.StoredEvent]] = []
    list_events_calls: list[dict[str, int]] = []
    delete_events_calls: list[int] = []
    ensure_jid_map: dict[str, str] = {}
    contacts: list[daemon_types.Contact] = []
    groups: list[daemon_types.Group] = []
    group_participants: dict[str, list[daemon_types.GroupParticipant]] = {}
    session_status: daemon_types.SessionStatusReply = daemon_types.SessionStatusReply(
        LoggedIn=False, QRCode="", QRImage=""
    )
    pair_phone_code: str = "12345678"
    pair_phone_calls: list[str] = []
    ping_result: str = "pong"
    version: daemon_types.VersionReply = daemon_types.VersionReply(GitCommit="test")
    phone_numbers: dict[str, str] = {}
    get_phone_number_calls: list[str] = []
    muted_until: dict[str, int] = {}
    set_muted_calls: list[dict[str, Any]] = []
    mark_read_calls: list[dict[str, Any]] = []
    clear_chat_notifications_calls: list[list[str]] = []
    set_notification_counter_calls: list[dict[str, Any]] = []
    send_message_calls: list[dict[str, Any]] = []
    send_message_result: daemon_types.SendMessageReply = daemon_types.SendMessageReply(
        MessageID="sent-message", Timestamp=1_700_000_000
    )
    send_message_exception: BaseException | None = None
    edit_message_calls: list[dict[str, Any]] = []
    delete_message_calls: list[dict[str, Any]] = []
    send_presence_calls: list[bool] = []
    subscribe_presence_calls: list[str] = []
    logout_calls: int = 0
    download_media_calls: list[dict[str, Any]] = []
    download_media_result: str = ""
    sync_avatar_calls: list[str] = []
    sync_avatar_paths: dict[str, str] = {}

    @classmethod
    def reset(cls) -> None:
        cls.list_event_batches = []
        cls.list_events_calls = []
        cls.delete_events_calls = []
        cls.ensure_jid_map = {}
        cls.contacts = []
        cls.groups = []
        cls.group_participants = {}
        cls.session_status = daemon_types.SessionStatusReply(LoggedIn=False, QRCode="", QRImage="")
        cls.pair_phone_code = "12345678"
        cls.pair_phone_calls = []
        cls.ping_result = "pong"
        cls.version = daemon_types.VersionReply(GitCommit="test")
        cls.phone_numbers = {}
        cls.get_phone_number_calls = []
        cls.muted_until = {}
        cls.set_muted_calls = []
        cls.mark_read_calls = []
        cls.clear_chat_notifications_calls = []
        cls.set_notification_counter_calls = []
        cls.send_message_calls = []
        cls.send_message_result = daemon_types.SendMessageReply(MessageID="sent-message", Timestamp=1_700_000_000)
        cls.send_message_exception = None
        cls.edit_message_calls = []
        cls.delete_message_calls = []
        cls.send_presence_calls = []
        cls.subscribe_presence_calls = []
        cls.logout_calls = 0
        cls.download_media_calls = []
        cls.download_media_result = ""
        cls.sync_avatar_calls = []
        cls.sync_avatar_paths = {}

    @classmethod
    def queue_events(cls, *batches: list[daemon_types.StoredEvent]) -> None:
        cls.list_event_batches.extend(batches)

    def list_events(self, after_id: int = 0, limit: int = 100) -> daemon_types.ListEventsReply:
        self.__class__.list_events_calls.append({"after_id": after_id, "limit": limit})
        if self.__class__.list_event_batches:
            return daemon_types.ListEventsReply(Events=self.__class__.list_event_batches.pop(0))
        return daemon_types.ListEventsReply(Events=[])

    def delete_events(self, up_to_id: int) -> EmptyReply:
        self.__class__.delete_events_calls.append(up_to_id)
        return EmptyReply()

    def get_contacts(self) -> daemon_types.GetContactsReply:
        return daemon_types.GetContactsReply(Contacts=list(self.__class__.contacts))

    def get_groups(self) -> daemon_types.GetGroupsReply:
        return daemon_types.GetGroupsReply(Groups=list(self.__class__.groups))

    def get_group_participants(self, chat_id: str) -> daemon_types.GetGroupParticipantsReply:
        return daemon_types.GetGroupParticipantsReply(
            Participants=list(self.__class__.group_participants.get(chat_id, []))
        )

    def get_session_status(self) -> daemon_types.SessionStatusReply:
        return self.__class__.session_status

    def pair_phone(self, phone_number: str) -> daemon_types.PairPhoneReply:
        self.__class__.pair_phone_calls.append(phone_number)
        return daemon_types.PairPhoneReply(Code=self.__class__.pair_phone_code)

    def ping(self) -> PingReply:
        return PingReply(Message=self.__class__.ping_result)

    def get_version(self) -> daemon_types.VersionReply:
        return self.__class__.version

    def get_phone_number(self, jid: str) -> str:
        self.__class__.get_phone_number_calls.append(jid)
        return self.__class__.phone_numbers.get(jid, "")

    def get_chat_settings(self, jid: str) -> daemon_types.GetChatSettingsReply:
        return daemon_types.GetChatSettingsReply(MutedUntil=self.__class__.muted_until.get(jid, 0))

    def set_muted(self, chat_id: str, muted: bool) -> EmptyReply:
        self.__class__.set_muted_calls.append({"chat_id": chat_id, "muted": muted})
        self.__class__.muted_until[chat_id] = 1 if muted else 0
        return EmptyReply()

    def mark_read(self, chat_id: str, message_ids: list[str], sender_jid: str = "") -> EmptyReply:
        self.__class__.mark_read_calls.append(
            {
                "chat_id": chat_id,
                "message_ids": list(message_ids),
                "sender_jid": sender_jid,
            }
        )
        return EmptyReply()

    def clear_chat_notifications(self, chat_ids: list[str]) -> EmptyReply:
        self.__class__.clear_chat_notifications_calls.append(list(chat_ids))
        return EmptyReply()

    def set_notification_counter(self, count: int, visible: bool) -> EmptyReply:
        self.__class__.set_notification_counter_calls.append({"count": count, "visible": visible})
        return EmptyReply()

    def send_message(self, chat_id: str, message_type: str, **kwargs: Any) -> daemon_types.SendMessageReply:
        self.__class__.send_message_calls.append({"chat_id": chat_id, "message_type": message_type, **kwargs})
        if self.__class__.send_message_exception is not None:
            raise self.__class__.send_message_exception
        return self.__class__.send_message_result

    def edit_message(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        reply_context: dict[str, object] | None = None,
    ) -> EditMessageReply:
        self.__class__.edit_message_calls.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_context": reply_context,
            }
        )
        return EditMessageReply(MessageID=message_id, Timestamp=1_700_000_000)

    def delete_message(self, chat_id: str, message_id: str) -> DeleteMessageReply:
        self.__class__.delete_message_calls.append({"chat_id": chat_id, "message_id": message_id})
        return DeleteMessageReply(MessageID=message_id, Timestamp=1_700_000_000)

    def send_presence(self, available: bool) -> EmptyReply:
        self.__class__.send_presence_calls.append(available)
        return EmptyReply()

    def subscribe_presence(self, chat_id: str) -> EmptyReply:
        self.__class__.subscribe_presence_calls.append(chat_id)
        return EmptyReply()

    def logout(self) -> EmptyReply:
        self.__class__.logout_calls += 1
        return EmptyReply()

    def ensure_jid(self, jid: str) -> EnsureJIDReply:
        if not jid:
            return EnsureJIDReply(JID="")
        mapped = self.__class__.ensure_jid_map.get(jid)
        if mapped is not None:
            return EnsureJIDReply(JID=mapped)
        if jid.endswith("@lid"):
            return EnsureJIDReply(JID=jid[: -len("@lid")] + "@s.whatsapp.net")
        return EnsureJIDReply(JID=jid)

    def download_media(
        self,
        *,
        direct_path: str,
        media_key: str,
        file_enc_sha256: str,
        file_sha256: str,
        file_length: int,
        media_type: str,
        mimetype: str,
        message_id: str,
        chat_id: str,
        file_name: str = "",
    ) -> DownloadMediaReply:
        call = {
            "direct_path": direct_path,
            "media_key": media_key,
            "file_enc_sha256": file_enc_sha256,
            "file_sha256": file_sha256,
            "file_length": file_length,
            "media_type": media_type,
            "mimetype": mimetype,
            "message_id": message_id,
            "chat_id": chat_id,
            "file_name": file_name,
        }
        self.__class__.download_media_calls.append(call)
        if self.__class__.download_media_result:
            return DownloadMediaReply(FilePath=self.__class__.download_media_result)
        cache_root = Path(os.environ["XDG_CACHE_HOME"]) / "greenline.tests" / "daemon-media"
        cache_root.mkdir(parents=True, exist_ok=True)
        suffix = ".webp" if media_type == "sticker" else ".bin"
        path = cache_root / f"{chat_id.replace('/', '_')}__{message_id}{suffix}"
        path.write_bytes(b"")
        return DownloadMediaReply(FilePath=str(path))

    def sync_avatar(self, jid: str) -> daemon_types.SyncAvatarReply:
        self.__class__.sync_avatar_calls.append(jid)
        configured = self.__class__.sync_avatar_paths.get(jid)
        if configured is not None:
            return daemon_types.SyncAvatarReply(AvatarPath=configured)
        cache_root = Path(os.environ["XDG_CACHE_HOME"]) / "greenline.tests" / "avatars"
        cache_root.mkdir(parents=True, exist_ok=True)
        path = cache_root / f"{jid.replace('/', '_')}.jpg"
        path.write_bytes(b"")
        return daemon_types.SyncAvatarReply(AvatarPath=str(path))


@pytest.fixture(autouse=True)
def isolated_greenline_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_home = tmp_path / "config"
    cache_home = tmp_path / "cache"
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))
    monkeypatch.setenv("APP_DIR", str(app_dir))
    monkeypatch.setenv("TZ", "UTC")
    if hasattr(time, "tzset"):
        time.tzset()

    import ut_components

    ut_components.setup("greenline.tests", None)

    import ut_components.config as ut_config

    monkeypatch.setattr(ut_components, "APP_NAME_", "greenline.tests")
    monkeypatch.setattr(ut_config, "APP_NAME_", "greenline.tests")

    fake_pyotherside.sent.clear()
    FakeDaemonRPC.reset()
    FakeDaemonService.reset()

    import greenline.api.daemon as api_daemon
    import greenline.contracts.daemon as daemon_boundary
    import greenline.store.identity as identity

    identity.clear_chat_runtime_cache()
    daemon_boundary.set_daemon_client_factory(lambda: FakeDaemonRPC())
    monkeypatch.setattr(api_daemon, "ensure_daemon_version", FakeDaemonService.ensure_daemon_version)
    monkeypatch.setattr(
        api_daemon,
        "install_background_service_files",
        FakeDaemonService.install_background_service_files,
    )
    monkeypatch.setattr(
        api_daemon,
        "remove_background_service_files",
        FakeDaemonService.remove_background_service_files,
    )
    monkeypatch.setattr(api_daemon, "is_daemon_installed", FakeDaemonService.is_daemon_installed)
    monkeypatch.setattr(api_daemon, "is_daemon_active", FakeDaemonService.is_daemon_active)
    monkeypatch.setattr(api_daemon, "run_subprocess", FakeDaemonService.run_subprocess)

    yield

    daemon_boundary.set_daemon_client_factory(None)
    identity.clear_chat_runtime_cache()


@pytest.fixture
def fake_daemon_rpc() -> type[FakeDaemonRPC]:
    return FakeDaemonRPC


@pytest.fixture
def fake_daemon_service() -> type[FakeDaemonService]:
    return FakeDaemonService


@pytest.fixture
def fake_pyotherside_module() -> FakePyOtherSide:
    return fake_pyotherside
