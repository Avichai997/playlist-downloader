"""The desktop window.

The interface is the same React app the API serves, displayed in the system web
view — WKWebView on macOS, WebView2 on Windows. The server listens on a random
loopback port so two copies of the app cannot collide.
"""
from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request

import uvicorn
import webview

from .. import APP_NAME, __version__

STARTUP_TIMEOUT = 30.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _ServerThread(threading.Thread):
    def __init__(self, port: int) -> None:
        super().__init__(daemon=True, name="api-server")
        from ..server.app import app

        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )

    def run(self) -> None:
        self._server.run()

    def stop(self) -> None:
        self._server.should_exit = True


def _wait_until_ready(port: int) -> bool:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.15)
    return False


def main() -> int:
    port = _free_port()
    server = _ServerThread(port)
    server.start()

    if not _wait_until_ready(port):
        print("The local server did not start in time.")
        return 1

    webview.create_window(
        f"{APP_NAME}  ·  v{__version__}",
        f"http://127.0.0.1:{port}/",
        width=1200,
        height=840,
        min_size=(960, 640),
    )
    webview.start()
    server.stop()
    return 0
