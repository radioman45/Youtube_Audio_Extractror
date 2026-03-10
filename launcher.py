from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from app.main import app


def resolve_listen_port(host: str, preferred_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sock.connect_ex((host, preferred_port)) != 0:
            return preferred_port

    for candidate in range(preferred_port + 1, preferred_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex((host, candidate)) != 0:
                return candidate

    raise RuntimeError("No available port was found for the local web app.")


def open_browser_when_ready(base_url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    healthcheck_url = f"{base_url}/api/health"

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(healthcheck_url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(base_url)
                    return
        except Exception:
            time.sleep(0.5)


def main() -> None:
    host = os.getenv("APP_HOST", "127.0.0.1")
    preferred_port = int(os.getenv("PORT", "8000"))
    port = resolve_listen_port(host, preferred_port)
    base_url = f"http://{host}:{port}"
    should_open_browser = os.getenv("APP_OPEN_BROWSER", "1") != "0" and "--no-browser" not in sys.argv

    if port != preferred_port:
        print(f"Port {preferred_port} is already in use. Starting on {base_url} instead.")
    else:
        print(f"Starting YouTube Multi Extractor on {base_url}")

    if should_open_browser:
        threading.Thread(
            target=open_browser_when_ready,
            args=(base_url,),
            daemon=True,
        ).start()

    print("Press Ctrl+C to stop the server.")
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
