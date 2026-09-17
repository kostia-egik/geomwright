from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable, Literal


DEFAULT_KOMPAS_PYTHON = Path(r"C:\ProgramData\ASCON\KOMPAS-3D\23\Python 3\App\python.exe")
CHECKOUT_BRIDGE_SCRIPT = Path(__file__).resolve().parents[2] / "bridge" / "kompas_bridge.py"
PACKAGED_BRIDGE_SCRIPT = Path(__file__).resolve().parent / "assets" / "bridge" / "kompas_bridge.py"


def default_bridge_script_path() -> Path:
    if CHECKOUT_BRIDGE_SCRIPT.exists():
        return CHECKOUT_BRIDGE_SCRIPT
    return PACKAGED_BRIDGE_SCRIPT


DEFAULT_BRIDGE_SCRIPT = default_bridge_script_path()
DEFAULT_NORMAL_TIMEOUT_SECONDS = 300.0
BridgeMode = Literal["normal", "diagnostic"]


class BridgeError(RuntimeError):
    pass


class BridgeRunner:
    def __init__(
        self,
        kompas_python: str | None = None,
        bridge_script: str | None = None,
        require_visible_kompas: bool = False,
        timeout_seconds: float | None = DEFAULT_NORMAL_TIMEOUT_SECONDS,
        cancel_event: threading.Event | None = None,
        mode: BridgeMode = "normal",
        diagnostic_artifact_dir: str | None = None,
    ) -> None:
        self.kompas_python = Path(kompas_python or os.environ.get("KOMPAS_PYTHON") or DEFAULT_KOMPAS_PYTHON)
        self.bridge_script = Path(bridge_script or os.environ.get("KOMPAS_BRIDGE_SCRIPT") or default_bridge_script_path())
        self.require_visible_kompas = bool(require_visible_kompas)
        self.timeout_seconds = timeout_seconds
        self.cancel_event = cancel_event
        self.mode = self._validate_mode(mode)
        self.diagnostic_artifact_dir = Path(
            diagnostic_artifact_dir
            or os.environ.get("KOMPAS_MCP_DIAGNOSTIC_DIR")
            or Path(tempfile.gettempdir()) / "geomwright-bridge-diagnostics"
        )
        self.last_diagnostic_artifacts: dict[str, str] | None = None

    def call(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        timeout_seconds: float | None = None,
        mode: BridgeMode | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        effective_timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        effective_mode = self.mode if mode is None else self._validate_mode(mode)
        if self.require_visible_kompas:
            payload["_require_visible_kompas"] = True

        if not self.kompas_python.exists():
            raise BridgeError(f"KOMPAS Python not found: {self.kompas_python}")
        if not self.bridge_script.exists():
            raise BridgeError(f"Bridge script not found: {self.bridge_script}")

        temp_root = Path(os.environ.get("KOMPAS_MCP_TEMP_DIR", r"C:\Windows\Temp"))
        if effective_mode == "diagnostic":
            self.diagnostic_artifact_dir.mkdir(parents=True, exist_ok=True)
            work_dir = Path(tempfile.mkdtemp(prefix="bridge-", dir=self.diagnostic_artifact_dir))
            directory_context = nullcontext(str(work_dir))
            self.last_diagnostic_artifacts = {"directory": str(work_dir)}
        else:
            directory_context = tempfile.TemporaryDirectory(prefix="kompas-mcp-", dir=temp_root)
            self.last_diagnostic_artifacts = None

        with directory_context as temp_dir:
            work_dir = Path(temp_dir)
            request_path = work_dir / "request.json"
            response_path = work_dir / "response.json"
            progress_path = work_dir / "progress.jsonl"
            request_path.write_text(
                json.dumps({"action": action, "payload": payload}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if effective_mode == "diagnostic":
                progress_path.touch()

            env = os.environ.copy()
            kompas_python_dir = str(self.kompas_python.parent)
            env["PATH"] = kompas_python_dir + os.pathsep + env.get("PATH", "")
            if progress_callback is not None or effective_mode == "diagnostic":
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
            last_progress: dict[str, Any] | None = None
            while process.poll() is None:
                progress_line_count, last_progress = self._report_progress(
                    progress_path, progress_line_count, progress_callback, started_at, last_progress
                )
                if self.cancel_event is not None and self.cancel_event.is_set():
                    self._stop_process(process)
                    raise BridgeError(self._with_checkpoint("Bridge call was cancelled", last_progress))
                if effective_timeout is not None and time.monotonic() - started_at > effective_timeout:
                    self._stop_process(process)
                    raise BridgeError(
                        self._with_checkpoint(
                            f"Bridge call timed out after {effective_timeout:g} seconds", last_progress
                        )
                    )
                time.sleep(0.05)
            stdout, stderr = process.communicate()
            _, last_progress = self._report_progress(
                progress_path, progress_line_count, progress_callback, started_at, last_progress
            )
            if effective_mode == "diagnostic":
                stdout_path = work_dir / "stdout.txt"
                stderr_path = work_dir / "stderr.txt"
                stdout_path.write_text(stdout, encoding="utf-8")
                stderr_path.write_text(stderr, encoding="utf-8")
                self.last_diagnostic_artifacts = {
                    "directory": str(work_dir),
                    "request": str(request_path),
                    "response": str(response_path),
                    "progress": str(progress_path),
                    "stdout": str(stdout_path),
                    "stderr": str(stderr_path),
                }

            if not response_path.exists():
                raise BridgeError(self._with_checkpoint(stderr.strip() or "Bridge did not produce a response file", last_progress))

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
            raise BridgeError(self._with_checkpoint(message, last_progress))

    @staticmethod
    def _validate_mode(mode: str) -> BridgeMode:
        if mode not in ("normal", "diagnostic"):
            raise ValueError("BridgeRunner mode must be 'normal' or 'diagnostic'")
        return mode  # type: ignore[return-value]

    @staticmethod
    def _with_checkpoint(message: str, checkpoint: dict[str, Any] | None) -> str:
        if not checkpoint:
            return message
        compact = {key: checkpoint.get(key) for key in ("stage", "percent", "document_id", "target", "elapsed_ms")}
        return f"{message} | last_progress={json.dumps(compact, ensure_ascii=False, separators=(',', ':'))}"

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
        started_at: float,
        last_event: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any] | None]:
        if not path.exists():
            return consumed_lines, last_event
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        complete_line_count = len(lines) if text.endswith(("\n", "\r")) else max(0, len(lines) - 1)
        for line in lines[consumed_lines:complete_line_count]:
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    operation = str(event.get("stage") or event.get("operation") or "unknown")
                    event = {
                        **event,
                        "stage": operation,
                        "operation": str(event.get("operation") or operation),
                        "percent": max(0, min(100, int(event.get("percent") or 0))),
                        "document_id": event.get("document_id"),
                        "target": event.get("target") or event.get("name"),
                        "elapsed_ms": max(0, int((time.monotonic() - started_at) * 1000)),
                    }
                    last_event = event
                    if callback is not None:
                        callback(event)
            except (OSError, ValueError):
                continue
        return complete_line_count, last_event
