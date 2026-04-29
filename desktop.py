"""Desktop launcher for Matokeo RMS.

The desktop build runs the Django app on localhost and opens it in a
native desktop window. User data lives beside the installed app in a
``data`` folder so offline work stays on the user's machine.
"""

from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path


APP_NAME = "Matokeo RMS"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


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


def configure_environment() -> Path:
    data_root = Path(os.getenv("MATOKEO_DATA_DIR", _app_root() / "data")).resolve()
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


def initialize_local_data() -> None:
    import django
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.management import call_command

    django.setup()
    call_command("migrate", database="default", interactive=False, verbosity=0)

    user_model = get_user_model()
    if not user_model.objects.exists():
        user_model.objects.create_superuser(
            username=DEFAULT_ADMIN_USERNAME,
            email="",
            password=DEFAULT_ADMIN_PASSWORD,
        )

    from accounts.views import _ensure_class_data_schema, _ensure_settings_schema

    school_db_path = settings.DATABASES["school_data"]["NAME"]
    conn = sqlite3.connect(school_db_path)
    try:
        _ensure_class_data_schema(conn)
        _ensure_settings_schema(conn)
        conn.commit()
    finally:
        conn.close()


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
