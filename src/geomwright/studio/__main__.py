from __future__ import annotations

import argparse
import json
import math
import socket
import threading
import time
import webbrowser
from collections.abc import Sequence
from typing import Any
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765
_PORT_FALLBACK_LIMIT = 100


def _ui_health(base_url: str) -> dict[str, Any] | None:
    # Socket timeouts are per read, not an absolute request deadline. A stalled
    # or dripping local HTTP response must not retain the launcher indefinitely.
    complete = threading.Event()
    result: list[dict[str, Any] | None] = []
    def probe() -> None:
        payload = None
        try:
            with urlopen(f"{base_url}health",timeout=0.5) as response:
                content = response.read(65537)
            if len(content)<=65536:
                decoded = json.loads(content)
                payload = decoded if isinstance(decoded,dict) else None
        except (OSError,URLError,ValueError):
            pass
        finally:
            result.append(payload)
            complete.set()
    threading.Thread(target=probe,name="studio-health",daemon=True).start()
    return result[0] if complete.wait(0.5) else None


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
    parser.add_argument("--background", action="store_true",
                        help="launch without a console, wait for readiness, then return")
    parser.add_argument("--startup-timeout",type=float,default=15.0,
                        help="background readiness budget in seconds (default: 15, maximum: 60)")
    parser.add_argument("--log-dir",type=Path,default=None,
                        help="background log directory (default: local Geomwright state)")
    args = parser.parse_args(argv)
    if not math.isfinite(args.startup_timeout) or not 0<args.startup_timeout<=60:
        parser.error("--startup-timeout must be in (0, 60] seconds")
    selection_deadline = time.monotonic()+args.startup_timeout
    requested_port = args.port
    port = _DEFAULT_PORT if requested_port is None else requested_port
    if not 1 <= port <= 65535:
        parser.error("--port must be between 1 and 65535")

    try:
        from .app import _studio_content_version
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None

    expected_version = _studio_content_version()
    base_url = f"http://{_HOST}:{port}/"
    existing = _ui_health(base_url)
    if _ui_is_running(base_url):
        if existing and existing.get("studio_version") == expected_version:
            print(f"Geomwright Studio is already running: {base_url}")
            if not args.no_browser:
                webbrowser.open(base_url, new=2)
            return
        print("A running Geomwright Studio instance is outdated; looking for the current version.")
    if not _port_is_available(port):
        if requested_port is not None:
            raise SystemExit(
                f"Port {port} is already in use. "
                "Choose another one with --port."
            )
        for candidate in range(port + 1, min(65535, port + _PORT_FALLBACK_LIMIT) + 1):
            if args.background and time.monotonic()>=selection_deadline:
                raise SystemExit("Background startup budget expired while selecting a port; no process was launched.")
            if _port_is_available(candidate):
                continue
            candidate_url = f"http://{_HOST}:{candidate}/"
            if _ui_is_running(candidate_url) and (_ui_health(candidate_url) or {}).get("studio_version") == expected_version:
                print(f"Current Geomwright Studio is already running: {candidate_url}")
                if not args.no_browser:
                    webbrowser.open(candidate_url, new=2)
                return
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

    if args.background:
        from .background import launch_background
        remaining = selection_deadline-time.monotonic()
        if remaining<=0:
            raise SystemExit("Background startup budget expired; no process was launched.")
        try:
            result = launch_background(port=port,expected_version=expected_version,
                                       timeout=remaining,health=_ui_health,log_dir=args.log_dir)
        except (OSError,RuntimeError) as exc:
            raise SystemExit(str(exc)) from None
        print(json.dumps(result,ensure_ascii=True))
        if not args.no_browser:
            webbrowser.open(result["url"],new=2)
        return

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
