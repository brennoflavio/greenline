import filecmp
import os
import shutil
import subprocess
import time

from constants import SERVICE_DEST_PATH, SERVICE_NAME
from ut_components.config import get_app_data_path


def run_subprocess(args):
    return subprocess.run(args, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def reload_systemd(start):
    result = run_subprocess(["systemctl", "--user", "daemon-reload"])
    if result.returncode != 0:
        raise ValueError(f"Error reloading systemd: {result.stdout}")

    if start:
        result = run_subprocess(["systemctl", "--user", "start", f"{SERVICE_NAME}.service"])
        if result.returncode != 0:
            raise ValueError(f"Error starting service: {result.stdout}")

        result = run_subprocess(["systemctl", "--user", "enable", f"{SERVICE_NAME}.service"])
        if result.returncode != 0:
            raise ValueError(f"Error enabling service: {result.stdout}")
    else:
        run_subprocess(["systemctl", "--user", "stop", f"{SERVICE_NAME}.service"])
        run_subprocess(["systemctl", "--user", "disable", f"{SERVICE_NAME}.service"])


def install_background_service_files():
    service_source = os.path.join(get_app_data_path(), "src", "greenline.service")

    dest_dir = os.path.dirname(SERVICE_DEST_PATH)
    os.makedirs(dest_dir, exist_ok=True)

    if os.path.exists(SERVICE_DEST_PATH):
        os.remove(SERVICE_DEST_PATH)

    shutil.copy(service_source, SERVICE_DEST_PATH)
    reload_systemd(start=True)


def remove_background_service_files():
    reload_systemd(start=False)

    if os.path.exists(SERVICE_DEST_PATH):
        os.remove(SERVICE_DEST_PATH)

    run_subprocess(["systemctl", "--user", "daemon-reload"])


def restart_daemon():
    run_subprocess(["systemctl", "--user", "restart", f"{SERVICE_NAME}.service"])


def is_daemon_installed():
    return os.path.exists(SERVICE_DEST_PATH)


def is_daemon_active():
    result = run_subprocess(["systemctl", "--user", "is-active", f"{SERVICE_NAME}.service"])
    return result.returncode == 0


def ensure_service_file():
    if not is_daemon_installed():
        return False

    service_source = os.path.join(get_app_data_path(), "src", "greenline.service")
    if not os.path.exists(service_source):
        return False

    if filecmp.cmp(service_source, SERVICE_DEST_PATH, shallow=False):
        return False

    shutil.copy(service_source, SERVICE_DEST_PATH)
    run_subprocess(["systemctl", "--user", "daemon-reload"])
    restart_daemon()
    return True


def get_expected_version():
    version_path = os.path.join(get_app_data_path(), "src", "version.txt")
    with open(version_path) as f:
        return f.read().strip()


def ensure_daemon_version():
    if not is_daemon_installed():
        return False

    service_updated = ensure_service_file()

    if not is_daemon_active():
        return service_updated

    try:
        expected = get_expected_version()
    except FileNotFoundError:
        return service_updated

    from rpc import DaemonRPC

    try:
        result = DaemonRPC().get_version()
        current = result.GitCommit
    except Exception:
        current = ""

    if current == expected:
        return False

    restart_daemon()
    for _ in range(10):
        time.sleep(0.5)
        try:
            DaemonRPC().ping()
            return True
        except Exception:
            continue
    return True
