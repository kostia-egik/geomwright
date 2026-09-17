from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable


DEFAULT_KOMPAS_PYTHON = Path(r"C:\ProgramData\ASCON\KOMPAS-3D\23\Python 3\App\python.exe")
CHECKOUT_BRIDGE_SCRIPT = Path(__file__).resolve().parents[2] / "bridge" / "kompas_bridge.py"
PACKAGED_BRIDGE_SCRIPT = Path(__file__).resolve().parent / "assets" / "bridge" / "kompas_bridge.py"


def default_bridge_script_path() -> Path:
    if CHECKOUT_BRIDGE_SCRIPT.exists():
        return CHECKOUT_BRIDGE_SCRIPT
    return PACKAGED_BRIDGE_SCRIPT


DEFAULT_BRIDGE_SCRIPT = default_bridge_script_path()


class BridgeError(RuntimeError):
    pass


class BridgeRunner:
    def __init__(
        self,
        kompas_python: str | None = None,
        bridge_script: str | None = None,
        require_visible_kompas: bool = False,
        timeout_seconds: float | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.kompas_python = Path(kompas_python or os.environ.get("KOMPAS_PYTHON") or DEFAULT_KOMPAS_PYTHON)
        self.bridge_script = Path(bridge_script or os.environ.get("KOMPAS_BRIDGE_SCRIPT") or default_bridge_script_path())
        self.require_visible_kompas = bool(require_visible_kompas)
        self.timeout_seconds = timeout_seconds
        self.cancel_event = cancel_event

    def call(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        effective_timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        if self.require_visible_kompas:
            payload["_require_visible_kompas"] = True

        if not self.kompas_python.exists():
            raise BridgeError(f"KOMPAS Python not found: {self.kompas_python}")
        if not self.bridge_script.exists():
            raise BridgeError(f"Bridge script not found: {self.bridge_script}")

        temp_root = os.environ.get("KOMPAS_MCP_TEMP_DIR", r"C:\Windows\Temp")
        with tempfile.TemporaryDirectory(prefix="kompas-mcp-", dir=temp_root) as temp_dir:
            request_path = Path(temp_dir) / "request.json"
            response_path = Path(temp_dir) / "response.json"
            progress_path = Path(temp_dir) / "progress.jsonl"
            request_path.write_text(
                json.dumps({"action": action, "payload": payload}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            env = os.environ.copy()
            kompas_python_dir = str(self.kompas_python.parent)
            env["PATH"] = kompas_python_dir + os.pathsep + env.get("PATH", "")
            if progress_callback is not None:
                env["KOMPAS_MCP_PROGRESS_FILE"] = str(progress_path)

            process = subprocess.Popen(
                [str(self.kompas_python), str(self.bridge_script), str(request_path), str(response_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            started_at = time.monotonic()
            progress_line_count = 0
            while process.poll() is None:
                if self.cancel_event is not None and self.cancel_event.is_set():
                    self._stop_process(process)
                    raise BridgeError("Bridge call was cancelled")
                if effective_timeout is not None and time.monotonic() - started_at > effective_timeout:
                    self._stop_process(process)
                    raise BridgeError(f"Bridge call timed out after {effective_timeout:g} seconds")
                progress_line_count = self._report_progress(
                    progress_path, progress_line_count, progress_callback
                )
                time.sleep(0.05)
            stdout, stderr = process.communicate()
            self._report_progress(progress_path, progress_line_count, progress_callback)

            if not response_path.exists():
                raise BridgeError(stderr.strip() or "Bridge did not produce a response file")

            try:
                envelope = json.loads(response_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise BridgeError(f"Invalid bridge response JSON: {exc}") from exc
            if not isinstance(envelope, dict):
                raise BridgeError(f"Bridge response must be an object, got {type(envelope).__name__}")
            if envelope.get("ok"):
                if "data" not in envelope:
                    raise BridgeError("Bridge response missing data")
                data = envelope["data"]
                if not isinstance(data, dict):
                    raise BridgeError(f"Bridge response data must be an object, got {type(data).__name__}")
                return data

            error = envelope.get("error") or {}
            message = (
                error.get("message")
                if isinstance(error, dict)
                else str(error)
            ) or stderr.strip() or "Unknown bridge error"
            raise BridgeError(message)

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        try:
            process.terminate()
            process.wait(timeout=2.0)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=2.0)
            except Exception:
                pass

    @staticmethod
    def _report_progress(
        path: Path,
        consumed_lines: int,
        callback: Callable[[dict[str, Any]], None] | None,
    ) -> int:
        if callback is None or not path.exists():
            return consumed_lines
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        complete_line_count = len(lines) if text.endswith(("\n", "\r")) else max(0, len(lines) - 1)
        for line in lines[consumed_lines:complete_line_count]:
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    callback(event)
            except (OSError, ValueError):
                continue
        return complete_line_count
