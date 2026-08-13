from __future__ import annotations

import argparse
import json
import socket
import threading
import time
import webbrowser
from collections.abc import Sequence
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765
_PORT_FALLBACK_LIMIT = 100


def _ui_health(base_url: str) -> dict[str, Any] | None:
    try:
        with urlopen(f"{base_url}health", timeout=0.5) as response:
            payload: Any = json.load(response)
    except (OSError, URLError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _ui_is_running(base_url: str) -> bool:
    payload = _ui_health(base_url)
    capabilities = payload.get("capabilities") if payload else None
    return bool(
        payload
        and payload.get("ok") is True
        and payload.get("product") == "geomwright_studio"
        and payload.get("mode") == "managed_cad"
        and payload.get("contract_version") == 2
        and isinstance(capabilities, list)
        and "managed_pulley_create_job" in capabilities
    )


def _legacy_ui_is_running(base_url: str) -> bool:
    payload = _ui_health(base_url)
    return bool(
        payload
        and payload.get("ok") is True
        and (
            payload.get("product") == "geomwright_studio"
            or ("product" not in payload and payload.get("mode") == "preview_only")
        )
        and isinstance(payload.get("module_count"), int)
    )


def _port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((_HOST, port))
        except OSError:
            return False
    return True


def _find_available_port(start_port: int) -> int | None:
    stop_port = min(65535, start_port + _PORT_FALLBACK_LIMIT)
    for port in range(start_port, stop_port + 1):
        if _port_is_available(port):
            return port
    return None


def _schedule_browser_open(base_url: str) -> None:
    def open_when_ready() -> None:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if _ui_is_running(base_url):
                webbrowser.open(base_url, new=2)
                return
            time.sleep(0.1)

    threading.Thread(target=open_when_ready, name="geomwright-studio-browser", daemon=True).start()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local Geomwright Studio preview UI")
    parser.add_argument("--port", type=int, default=None, help=f"local port (default: {_DEFAULT_PORT})")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the UI in the default browser",
    )
    args = parser.parse_args(argv)
    requested_port = args.port
    port = _DEFAULT_PORT if requested_port is None else requested_port
    if not 1 <= port <= 65535:
        parser.error("--port must be between 1 and 65535")

    base_url = f"http://{_HOST}:{port}/"
    if _ui_is_running(base_url):
        print(f"Geomwright Studio is already running: {base_url}")
        if not args.no_browser:
            webbrowser.open(base_url, new=2)
        return
    if not _port_is_available(port):
        if requested_port is not None:
            raise SystemExit(
                f"Port {port} is already in use. "
                "Choose another one with --port."
            )
        fallback_port = _find_available_port(port + 1)
        if fallback_port is None:
            raise SystemExit(
                f"Port {port} and the next {_PORT_FALLBACK_LIMIT} local ports are already in use. "
                "Choose another one with --port."
            )
        occupant = "an older Geomwright Studio instance" if _legacy_ui_is_running(base_url) else "another application"
        print(f"Port {port} is used by {occupant}; using {fallback_port} for the current interface.")
        port = fallback_port
        base_url = f"http://{_HOST}:{port}/"

    try:
        import uvicorn
    except ModuleNotFoundError:
        raise SystemExit("Geomwright Studio requires: pip install 'geomwright[ui]'") from None

    try:
        from .app import app
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None

    if not args.no_browser:
        _schedule_browser_open(base_url)
    print(f"Opening Geomwright Studio at {base_url}")
    uvicorn.run(
        app,
        host=_HOST,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
