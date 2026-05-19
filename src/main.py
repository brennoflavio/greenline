"""
Copyright (C) 2025  Brenno Almeida

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; version 3.

greenline is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
 along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from constants import APP_NAME, CRASH_REPORT_URL
from ut_components import setup

setup(APP_NAME, CRASH_REPORT_URL)

from greenline.api.chats import (
    ChatDraftResponse,
    GroupMentionCandidatesResponse,
    get_chat_draft,
    get_chat_info,
    get_chat_list,
    get_contact_list,
    get_group_mention_candidates,
    set_chat_draft,
    toggle_mute,
)
from greenline.api.common import SuccessResponse
from greenline.api.daemon import (
    ClearDataResponse,
    DaemonStatusResponse,
    EnsureDaemonVersionResponse,
    PairPhoneResponse,
    PhoneNumberResponse,
    SettingsResponse,
    check_daemon_status,
    check_daemon_version,
    clear_data,
    get_phone_number,
    get_session_status,
    get_settings,
    get_sync_status,
    install_daemon,
    pair_phone,
    ping_daemon,
    send_presence,
    set_notifications_suppressed,
    start_event_loop,
    subscribe_presence,
    uninstall_daemon,
)
from greenline.api.messages import (
    EDIT_WINDOW_SECONDS,
    DownloadMediaResponse,
    delete_message,
    download_media,
    edit_text_message,
    get_cached_stickers,
    get_messages,
    mark_messages_as_read,
    send_audio_message,
    send_contact_message,
    send_image_message,
    send_sticker_message,
    send_text_message,
    send_video_message,
)

__all__ = [
    "APP_NAME",
    "CRASH_REPORT_URL",
    "setup",
    "ChatDraftResponse",
    "GroupMentionCandidatesResponse",
    "get_chat_draft",
    "get_chat_info",
    "get_chat_list",
    "get_contact_list",
    "get_group_mention_candidates",
    "set_chat_draft",
    "toggle_mute",
    "SuccessResponse",
    "ClearDataResponse",
    "DaemonStatusResponse",
    "EnsureDaemonVersionResponse",
    "PairPhoneResponse",
    "PhoneNumberResponse",
    "SettingsResponse",
    "check_daemon_status",
    "check_daemon_version",
    "clear_data",
    "get_phone_number",
    "get_session_status",
    "get_settings",
    "get_sync_status",
    "install_daemon",
    "pair_phone",
    "ping_daemon",
    "send_presence",
    "set_notifications_suppressed",
    "start_event_loop",
    "subscribe_presence",
    "uninstall_daemon",
    "EDIT_WINDOW_SECONDS",
    "DownloadMediaResponse",
    "delete_message",
    "download_media",
    "edit_text_message",
    "get_cached_stickers",
    "get_messages",
    "mark_messages_as_read",
    "send_audio_message",
    "send_contact_message",
    "send_image_message",
    "send_sticker_message",
    "send_text_message",
    "send_video_message",
]
