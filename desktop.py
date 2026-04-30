"""Desktop launcher for Matokeo RMS.

The desktop build runs the Django app on localhost and opens it in a
desktop-style window. Installed Windows builds store offline data in the
current user's app-data folder because Program Files is not writable by
normal users.
"""

from __future__ import annotations

import os
import hashlib
import json
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
import webbrowser


APP_NAME = "Matokeo RMS"
APP_VERSION = "0.1.3"
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/felixfelix332/matokeo-rms/main/releases/latest.json"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _code_root() -> Path:
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent


def _app_root() -> Path:
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _user_data_root() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if base:
        return Path(base) / "MunTech" / APP_NAME / "data"
    return Path.home() / ".matokeo-rms" / "data"


def _default_data_root() -> Path:
    data_dir = os.getenv("MATOKEO_DATA_DIR")
    if data_dir:
        return Path(data_dir)
    if _is_frozen():
        return _user_data_root()
    return _app_root() / "data"


def configure_environment() -> Path:
    data_root = _default_data_root().resolve()
    data_root.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ["MATOKEO_CODE_ROOT"] = str(_code_root())
    os.environ["MATOKEO_DATA_DIR"] = str(data_root)
    os.environ.setdefault("DJANGO_DEBUG", "1")
    os.environ.setdefault("MATOKEO_DESKTOP", "1")
    return data_root


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(port: int, timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError("Matokeo RMS did not finish starting in time.")


def _version_parts(version: str) -> tuple[int, ...]:
    parts = tuple(int(part) for part in re.findall(r"\d+", str(version)))
    return parts or (0,)


def _is_newer_version(candidate: str, current: str) -> bool:
    candidate_parts = _version_parts(candidate)
    current_parts = _version_parts(current)
    length = max(len(candidate_parts), len(current_parts))
    return candidate_parts + (0,) * (length - len(candidate_parts)) > current_parts + (0,) * (length - len(current_parts))


def _show_desktop_message(title: str, message: str) -> None:
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showinfo(title, message)
        root.destroy()
    except Exception:
        print(f"{title}\n{message}")


def _confirm_desktop_action(title: str, message: str) -> bool:
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        confirmed = messagebox.askyesno(title, message)
        root.destroy()
        return bool(confirmed)
    except Exception:
        print(f"{title}\n{message}")
        return False


def _download_update_installer(installer_url: str, version: str, expected_sha256: str = "") -> Path:
    update_dir = Path(tempfile.gettempdir()) / "MunTech" / APP_NAME / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    installer_path = update_dir / f"Matokeo-RMS-Setup-{version}.exe"

    with urllib.request.urlopen(installer_url, timeout=120) as response:
        with installer_path.open("wb") as output:
            shutil.copyfileobj(response, output)

    if expected_sha256:
        digest = hashlib.sha256(installer_path.read_bytes()).hexdigest()
        if digest.lower() != expected_sha256.lower():
            installer_path.unlink(missing_ok=True)
            raise RuntimeError("The downloaded update did not match the expected checksum.")

    return installer_path


def maybe_start_update() -> bool:
    if not _is_frozen() or os.getenv("MATOKEO_DISABLE_UPDATES") == "1":
        return False

    manifest_url = os.getenv("MATOKEO_UPDATE_MANIFEST_URL", UPDATE_MANIFEST_URL)
    try:
        with urllib.request.urlopen(manifest_url, timeout=5) as response:
            manifest = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False

    latest_version = str(manifest.get("version", "")).strip()
    installer_url = str(manifest.get("installer_url", "")).strip()
    if not latest_version or not installer_url or not _is_newer_version(latest_version, APP_VERSION):
        return False

    notes = str(manifest.get("notes", "")).strip()
    prompt = (
        f"Matokeo RMS {latest_version} is available.\n\n"
        f"Installed version: {APP_VERSION}\n\n"
        "Download and start the installer now?"
    )
    if notes:
        prompt += f"\n\nWhat's new:\n{notes}"

    if not _confirm_desktop_action("Matokeo RMS Update", prompt):
        return False

    try:
        installer_path = _download_update_installer(
            installer_url,
            latest_version,
            str(manifest.get("sha256", "")).strip(),
        )
    except Exception as exc:
        _show_desktop_message(
            "Matokeo RMS Update",
            f"The update could not be downloaded.\n\n{exc}\n\nYou can continue using the current version.",
        )
        return False

    subprocess.Popen([str(installer_path)])
    return True


def initialize_local_data() -> None:
    import django
    from django.conf import settings
    from django.core.management import call_command

    django.setup()
    call_command("migrate", database="default", interactive=False, verbosity=0)

    from accounts.auth_defaults import ensure_default_admin_user

    ensure_default_admin_user()

    from accounts.views import _ensure_class_data_schema, _ensure_settings_schema

    school_db_path = settings.DATABASES["school_data"]["NAME"]
    conn = sqlite3.connect(school_db_path)
    try:
        _ensure_class_data_schema(conn)
        _ensure_settings_schema(conn)
        conn.commit()
    finally:
        conn.close()


def reset_desktop_admin_password() -> None:
    configure_environment()

    import django
    from django.core.management import call_command

    django.setup()
    call_command("migrate", database="default", interactive=False, verbosity=0)

    from accounts.auth_defaults import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME, reset_default_admin_password

    reset_default_admin_password()
    message = (
        f"Matokeo RMS admin password has been reset.\n\n"
        f"Username: {DEFAULT_ADMIN_USERNAME}\n"
        f"Password: {DEFAULT_ADMIN_PASSWORD}\n\n"
        "Change this password after signing in."
    )
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showinfo(APP_NAME, message)
        root.destroy()
    except Exception:
        print(message)


def run_server(port: int) -> None:
    from waitress import serve
    from config.wsgi import application

    serve(application, host="127.0.0.1", port=port, threads=8)


def open_desktop_window(url: str) -> None:
    try:
        import webview
    except ImportError:
        edge_paths = [
            Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]
        for edge_path in edge_paths:
            if edge_path.exists():
                subprocess.Popen([str(edge_path), f"--app={url}", "--new-window"])
                break
        else:
            webbrowser.open(url)

        print(f"{APP_NAME} is running at {url}")
        print("Close this launcher window to stop Matokeo RMS.")
        while True:
            time.sleep(3600)

    webview.create_window(APP_NAME, url, width=1366, height=768, min_size=(1024, 640))
    webview.start()


def main() -> None:
    if "--reset-admin-password" in sys.argv:
        reset_desktop_admin_password()
        return

    if maybe_start_update():
        return

    configure_environment()
    initialize_local_data()
    port = _find_free_port()
    url = f"http://127.0.0.1:{port}/"

    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()
    _wait_for_server(port)
    open_desktop_window(url)


if __name__ == "__main__":
    main()
