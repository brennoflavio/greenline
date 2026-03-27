import os

APP_NAME = "greenline.brennoflavio"
CRASH_REPORT_URL = ""
SERVICE_NAME = "greenline"
SERVICE_DEST_PATH = "/home/phablet/.config/systemd/user/greenline.service"
DAEMON_SOCKET_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "greenline-daemon.sock")
GROUP_JID_SUFFIX = "@g.us"
