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
    handle_application_exit,
    install_daemon,
    pair_phone,
    ping_daemon,
    send_presence,
    set_error_reporting,
    set_notifications_suppressed,
    set_stop_daemon_on_exit,
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
    get_message_reactions,
    get_messages,
    mark_messages_as_read,
    send_audio_message,
    send_contact_message,
    send_document_message,
    send_image_message,
    send_sticker_message,
    send_text_message,
    send_video_message,
)
from greenline.contracts.qml import qml_api

check_daemon_status = qml_api("check_daemon_status")(check_daemon_status)
check_daemon_version = qml_api("check_daemon_version")(check_daemon_version)
clear_data = qml_api("clear_data")(clear_data)
delete_message = qml_api("delete_message")(delete_message)
download_media = qml_api("download_media")(download_media)
edit_text_message = qml_api("edit_text_message")(edit_text_message)
get_cached_stickers = qml_api("get_cached_stickers")(get_cached_stickers)
get_chat_draft = qml_api("get_chat_draft")(get_chat_draft)
get_chat_info = qml_api("get_chat_info")(get_chat_info)
get_chat_list = qml_api("get_chat_list")(get_chat_list)
get_contact_list = qml_api("get_contact_list")(get_contact_list)
get_group_mention_candidates = qml_api("get_group_mention_candidates")(get_group_mention_candidates)
get_message_reactions = qml_api("get_message_reactions")(get_message_reactions)
get_messages = qml_api("get_messages")(get_messages)
get_phone_number = qml_api("get_phone_number")(get_phone_number)
get_session_status = qml_api("get_session_status")(get_session_status)
get_settings = qml_api("get_settings")(get_settings)
get_sync_status = qml_api("get_sync_status")(get_sync_status)
install_daemon = qml_api("install_daemon")(install_daemon)
mark_messages_as_read = qml_api("mark_messages_as_read")(mark_messages_as_read)
pair_phone = qml_api("pair_phone")(pair_phone)
ping_daemon = qml_api("ping_daemon")(ping_daemon)
send_audio_message = qml_api("send_audio_message")(send_audio_message)
send_contact_message = qml_api("send_contact_message")(send_contact_message)
send_document_message = qml_api("send_document_message")(send_document_message)
send_image_message = qml_api("send_image_message")(send_image_message)
handle_application_exit = qml_api("handle_application_exit")(handle_application_exit)
send_presence = qml_api("send_presence")(send_presence)
send_sticker_message = qml_api("send_sticker_message")(send_sticker_message)
send_text_message = qml_api("send_text_message")(send_text_message)
send_video_message = qml_api("send_video_message")(send_video_message)
set_chat_draft = qml_api("set_chat_draft")(set_chat_draft)
set_error_reporting = qml_api("set_error_reporting")(set_error_reporting)
set_notifications_suppressed = qml_api("set_notifications_suppressed")(set_notifications_suppressed)
set_stop_daemon_on_exit = qml_api("set_stop_daemon_on_exit")(set_stop_daemon_on_exit)
start_event_loop = qml_api("start_event_loop")(start_event_loop)
subscribe_presence = qml_api("subscribe_presence")(subscribe_presence)
toggle_mute = qml_api("toggle_mute")(toggle_mute)
uninstall_daemon = qml_api("uninstall_daemon")(uninstall_daemon)

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
    "handle_application_exit",
    "send_presence",
    "set_error_reporting",
    "set_notifications_suppressed",
    "set_stop_daemon_on_exit",
    "start_event_loop",
    "subscribe_presence",
    "uninstall_daemon",
    "EDIT_WINDOW_SECONDS",
    "DownloadMediaResponse",
    "delete_message",
    "download_media",
    "edit_text_message",
    "get_cached_stickers",
    "get_message_reactions",
    "get_messages",
    "mark_messages_as_read",
    "send_audio_message",
    "send_contact_message",
    "send_document_message",
    "send_image_message",
    "send_sticker_message",
    "send_text_message",
    "send_video_message",
]
