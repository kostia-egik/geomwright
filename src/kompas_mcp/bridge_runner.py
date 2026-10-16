from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable, Literal
from .session_guard import SessionGuard, SessionGuardError, process_alive, PythonHelperJob
from .cad_session_policy import CadSessionPolicy, CAD_WORK_MODES


DEFAULT_KOMPAS_PYTHON = Path(r"C:\ProgramData\ASCON\KOMPAS-3D\23\Python 3\App\python.exe")
CHECKOUT_BRIDGE_SCRIPT = Path(__file__).resolve().parents[2] / "bridge" / "kompas_bridge.py"
CHECKOUT_KOMPAS_PYTHON = CHECKOUT_BRIDGE_SCRIPT.parent.parent / ".venv" / "cad-bridge" / "Scripts" / "python.exe"
PACKAGED_BRIDGE_SCRIPT = Path(__file__).resolve().parent / "assets" / "bridge" / "kompas_bridge.py"


def default_bridge_script_path() -> Path:
    if CHECKOUT_BRIDGE_SCRIPT.exists():
        return CHECKOUT_BRIDGE_SCRIPT
    return PACKAGED_BRIDGE_SCRIPT


def default_kompas_python_path() -> Path:
    """Prefer the checkout's owned CAD venv; never read private MCP configuration."""
    if CHECKOUT_BRIDGE_SCRIPT.is_file() and CHECKOUT_KOMPAS_PYTHON.is_file():
        return CHECKOUT_KOMPAS_PYTHON
    return DEFAULT_KOMPAS_PYTHON


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
        require_visible_kompas: bool | None = None,
        timeout_seconds: float | None = DEFAULT_NORMAL_TIMEOUT_SECONDS,
        cancel_event: threading.Event | None = None,
        mode: BridgeMode = "normal",
        diagnostic_artifact_dir: str | None = None,
        session_guard_dir: str | None = None,
        cad_mode: str | None = None,
    ) -> None:
        self.kompas_python = Path(kompas_python or os.environ.get("KOMPAS_PYTHON") or default_kompas_python_path())
        self.bridge_script = Path(bridge_script or os.environ.get("KOMPAS_BRIDGE_SCRIPT") or default_bridge_script_path())
        self.require_visible_kompas = (
            os.environ.get("KOMPAS_REQUIRE_VISIBLE", "").strip().lower() in {"1", "true", "yes"}
            if require_visible_kompas is None else bool(require_visible_kompas)
        )
        self.timeout_seconds = timeout_seconds
        self.cancel_event = cancel_event
        self.mode = self._validate_mode(mode)
        self.diagnostic_artifact_dir = Path(
            diagnostic_artifact_dir
            or os.environ.get("KOMPAS_MCP_DIAGNOSTIC_DIR")
            or Path(tempfile.gettempdir()) / "geomwright-bridge-diagnostics"
        )
        self.last_diagnostic_artifacts: dict[str, str] | None = None
        self.session_guard = SessionGuard(session_guard_dir)
        self.cad_mode = cad_mode or os.environ.get("KOMPAS_CAD_MODE") or None
        if require_visible_kompas is True:
            if self.cad_mode == "hidden":
                raise ValueError("require_visible_kompas conflicts with hidden cad_mode")
            self.cad_mode = "interactive"
        if self.cad_mode is not None and self.cad_mode not in CAD_WORK_MODES:
            raise ValueError("cad_mode must be interactive or hidden")
        self.cad_session_policy = CadSessionPolicy(self.session_guard)
        self._cad_context_token = None
        self._cad_selected_mode = None
        self._runtime_validation_key = None

    def _validate_runtime(self) -> None:
        """Compile production sources and import pywin32, without importing CAD code.

        The validation process never loads the bridge or calls KOMPAS. It is not marked as a bridge
        launch, so local configuration failures do not quarantine the CAD session.
        Custom bridge scripts keep their existing independent execution contract.
        """
        script = self.bridge_script.resolve()
        if script not in {CHECKOUT_BRIDGE_SCRIPT.resolve(), PACKAGED_BRIDGE_SCRIPT.resolve()}:
            return
        runtime_dir = PACKAGED_BRIDGE_SCRIPT.parent
        sources = (script, Path(__file__).with_name("session_guard.py"),
                   runtime_dir / "cad_session_runtime.py", runtime_dir / "body_geometry_runtime.py",
                   runtime_dir / "construction_chain_runtime.py", runtime_dir / "chain_prism_runtime.py",
                    runtime_dir / "chain_holes_runtime.py",
                     runtime_dir / "chain_thread_runtime.py",
                     runtime_dir / "chain_spline_runtime.py",
                   runtime_dir / "model_image_runtime.py")
        try:
            paths = (self.kompas_python.resolve(),) + sources
            key = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
        except OSError as exc:
            raise BridgeError(f"CAD_RUNTIME_INVALID: Cannot read runtime files: {exc}. Configure KOMPAS_PYTHON with a modern Python and pywin32.") from exc
        if key == self._runtime_validation_key:
            return
        # This checker itself uses old-Python-compatible syntax so an SDK 3.2
        # interpreter reports the actual bridge syntax error before any COM call.
        code = "import sys; [compile(open(p, 'rb').read(), p, 'exec') for p in sys.argv[1:]]; import win32com.client"
        env = os.environ.copy()
        env["PATH"] = str(self.kompas_python.parent) + os.pathsep + env.get("PATH", "")
        try:
            checked = subprocess.run([str(self.kompas_python), "-c", code, *map(str, sources)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BridgeError(f"CAD_RUNTIME_INVALID: Runtime preflight failed ({type(exc).__name__}). Configure KOMPAS_PYTHON with a modern Python and pywin32; no CAD process was launched.") from exc
        if checked.returncode != 0:
            detail = checked.stderr.decode("utf-8", errors="replace")[-2000:].strip()
            raise BridgeError(f"CAD_RUNTIME_INVALID: Runtime cannot compile/import the production bridge: {detail}. Configure KOMPAS_PYTHON with a modern Python and pywin32; no CAD process was launched.")
        self._runtime_validation_key = key

    def call(
        self, action: str, payload: dict[str, Any] | None = None, *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        timeout_seconds: float | None = None, mode: BridgeMode | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        deadline = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        deadline = DEFAULT_NORMAL_TIMEOUT_SECONDS if deadline is None else deadline
        if not math.isfinite(deadline) or deadline <= 0:
            raise ValueError("A finite positive bridge timeout is required")
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise BridgeError("Bridge call was cancelled")
        # Each request owns its record. A concurrent rejected request or explicit
        # recovery must not replace another call's in-memory ownership token.
        guard = SessionGuard(self.session_guard.directory)
        try:
            with guard.operation(action, payload):
                context = self.cad_session_policy.prepare(self.cad_mode, action=action)
                if self._cad_context_token is not None and context["token"] != self._cad_context_token:
                    raise SessionGuardError("CAD_SESSION_CHANGED: another host selected a different context; explicitly reselect mode/window before continuing")
                self._cad_context_token, self._cad_selected_mode = context["token"], context["mode"]
                payload["_cad_session_context"] = context
                def progress(event):
                    guard.checkpoint(event)
                    if progress_callback is not None:
                        progress_callback(event)
                result = self._call(action, payload, progress_callback=progress,
                                    timeout_seconds=deadline, mode=mode, _guard=guard)
                if result.get("ok") is False:
                    guard.failed("Bridge handler returned failure; inspect its result and affected model")
                return result
        except SessionGuardError as exc:
            raise BridgeError(str(exc)) from exc
        except BridgeError as exc:
            if guard.launched:
                if guard.completion == "no_cad":
                    raise
                if guard.completion == "settled":
                    raise BridgeError(f"CAD_DIAGNOSTICS_REQUIRED: command finished with an error; {exc}. Read get_cad_session_guard and call recover_cad_session with confirm_idle=false for automatic session audit; inspect the affected model before writing.") from exc
                raise BridgeError(f"CAD_SESSION_BLOCKED: unknown CAD outcome; {exc}. Read get_cad_session_guard; do not retry COM before explicit recovery.") from exc
            raise

    def get_session_guard(self) -> dict:
        return self.session_guard.status()

    def recover_session(self, token: str, *, confirm_idle: bool, reason: str) -> dict:
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ValueError("A nonempty recovery reason (max500 chars) is required")
        if confirm_idle is not True and self.get_session_guard().get("state") == "settled_failure":
            guard = SessionGuard(self.session_guard.directory)
            with guard.recovery_audit(token):
                context = self.cad_session_policy.prepare(self.cad_mode, action="audit_session_recovery")
                if self._cad_context_token is not None and context["token"] != self._cad_context_token:
                    raise BridgeError("CAD_SESSION_CHANGED: recovery cannot select a different CAD context")
                binding = context.get("binding") or {}
                if binding.get("process_id") and not process_alive(binding["process_id"]):
                    # The exact previously bound server no longer exists. It
                    # cannot retain outstanding work; never attach a substitute.
                    guard.finished("settled")
                    return guard.finish_recovery_audit({"session_observed_clear": True,
                        "bound_session_exited": True, "com_called": False,
                        "model_verified": False, "documents_changed": False}, reason)
                try:
                    report = self._call("audit_session_recovery", {"_cad_session_context": context},
                                        _guard=guard, progress_callback=guard.checkpoint,
                                        timeout_seconds=15, mode=None)
                except BridgeError as exc:
                    if guard.completion not in ("no_cad", "settled"):
                        raise
                    report = {"session_observed_clear": False,
                              "blockers": ["session_audit_failed"], "error": str(exc)[:1500]}
                if report.get("session_observed_clear") is not True:
                    return {"ok": False, "blocked": True, "state": "settled_failure",
                            "basis": "session_audit_blocked", "audit": report,
                            "next_step": "Resolve the reported UI/edit blocker, then repeat recovery with the same token. Do not replay the failed CAD command."}
                return guard.finish_recovery_audit(report, reason)
        return self.session_guard.recover(token, confirm_idle=confirm_idle, reason=reason)

    def get_cad_work_mode(self) -> dict:
        status = self.cad_session_policy.status()
        return {**status, "host_mode": self._cad_selected_mode,
                "host_selection_stale": self._cad_context_token is not None and self._cad_context_token != status["token"]}

    def set_cad_work_mode(self, mode: str, *, confirm_switch: bool, target_window_handle: int | None = None) -> dict:
        result = self.cad_session_policy.configure(mode, confirm_switch=confirm_switch,
                                                  target_window_handle=target_window_handle)
        self.cad_mode = mode
        self._cad_context_token = self._cad_selected_mode = None
        return result

    def _call(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        _guard: SessionGuard,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        timeout_seconds: float | None = None,
        mode: BridgeMode | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        effective_timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        effective_mode = self.mode if mode is None else self._validate_mode(mode)
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise BridgeError("Bridge call was cancelled")
        if self.require_visible_kompas:
            payload["_require_visible_kompas"] = True

        if not self.kompas_python.exists():
            raise BridgeError(f"KOMPAS Python not found: {self.kompas_python}")
        if not self.bridge_script.exists():
            raise BridgeError(f"Bridge script not found: {self.bridge_script}")
        self._validate_runtime()
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise BridgeError("Bridge call was cancelled")

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
            stdout_path = work_dir / "stdout.txt"
            stderr_path = work_dir / "stderr.txt"
            request_path.write_text(
                json.dumps({"action": action, "payload": payload, "completion_token": _guard.record["token"]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if effective_mode == "diagnostic":
                progress_path.touch()
                self.last_diagnostic_artifacts = {
                    "directory": str(work_dir),
                    "request": str(request_path),
                    "response": str(response_path),
                    "progress": str(progress_path),
                    "stdout": str(stdout_path),
                    "stderr": str(stderr_path),
                }

            env = os.environ.copy()
            kompas_python_dir = str(self.kompas_python.parent)
            env["PATH"] = kompas_python_dir + os.pathsep + env.get("PATH", "")
            if progress_callback is not None or effective_mode == "diagnostic":
                env["KOMPAS_MCP_PROGRESS_FILE"] = str(progress_path)

            # Spool output directly: polling a child with undrained PIPEs can
            # deadlock when either stream fills. Normal errors read only a tail;
            # diagnostic mode retains the complete files, including on failure.
            with PythonHelperJob(_guard) as helper_job, stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
                # Only explicitly enrolled Python helpers join this job. Never
                # put the bridge process tree (which could start COM servers) in it.
                env["KOMPAS_MCP_HELPER_JOB"] = helper_job.name or ""
                env["KOMPAS_MCP_HELPER_GUARD"] = str(Path(__file__).with_name("session_guard.py").resolve())
                env["KOMPAS_MCP_HELPER_RECORD"] = str(_guard.path.resolve())
                _guard.record.update(helper_job_name=helper_job.name, helper_job_open=True)
                _guard._write()
                process = subprocess.Popen(
                    [str(self.kompas_python), str(self.bridge_script), str(request_path), str(response_path)],
                    # The bridge reads JSON files, never the MCP stdin transport.
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    env=env,
                )
                try:
                    _guard.started(process)
                    started_at = time.monotonic()
                    progress_offset = 0
                    last_progress: dict[str, Any] | None = None
                    while process.poll() is None:
                        progress_offset, last_progress = self._report_progress(
                            progress_path, progress_offset, progress_callback, started_at, last_progress
                        )
                        if self.cancel_event is not None and self.cancel_event.is_set():
                            raise BridgeError(self._with_checkpoint("Bridge call was cancelled", last_progress))
                        if effective_timeout is not None and time.monotonic() - started_at > effective_timeout:
                            raise BridgeError(
                                self._with_checkpoint(
                                    f"Bridge call timed out after {effective_timeout:g} seconds", last_progress
                                )
                            )
                        time.sleep(0.05)
                    _, last_progress = self._report_progress(
                        progress_path, progress_offset, progress_callback, started_at, last_progress
                    )
                finally:
                    # Callback/readback errors and KeyboardInterrupt must release
                    # the owned bridge too. Never terminate the KOMPAS server.
                    if process.poll() is None:
                        self._stop_process(process)

            stderr = self._read_output_tail(stderr_path)
            if not response_path.exists():
                if process.poll() != 0:
                    raise BridgeError(self._with_checkpoint(
                        f"Bridge exited with code {process.poll()}: {stderr.strip()}", last_progress))
                raise BridgeError(self._with_checkpoint(stderr.strip() or "Bridge did not produce a response file", last_progress))

            try:
                envelope = json.loads(response_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise BridgeError(f"Invalid bridge response JSON: {exc}") from exc
            if not isinstance(envelope, dict):
                raise BridgeError(f"Bridge response must be an object, got {type(envelope).__name__}")
            if type(envelope.get("ok")) is not bool:
                raise BridgeError("Bridge response ok must be a boolean")
            # Custom scripts, progress and a mere process exit are not terminal
            # CAD evidence. Only our production dispatcher publishes this receipt.
            completion = envelope.get("completion")
            trusted = self.bridge_script.resolve() in {CHECKOUT_BRIDGE_SCRIPT.resolve(), PACKAGED_BRIDGE_SCRIPT.resolve()}
            if (trusted and isinstance(completion, dict) and completion.get("version") == 1
                    and completion.get("token") == _guard.record["token"]
                    and completion.get("action") == action
                    and completion.get("outcome") in ("no_cad", "settled")
                    and ((process.poll() == 0 and envelope.get("ok") is True)
                         or (process.poll() == 1 and envelope.get("ok") is False))
                    and ((envelope["ok"] is True and isinstance(envelope.get("data"), dict))
                         or (envelope["ok"] is False and isinstance(envelope.get("error"), dict)
                             and isinstance(envelope["error"].get("message"), str)
                             and isinstance(envelope["error"].get("type"), str)))):
                _guard.finished(completion["outcome"])
            if process.poll() != 0:
                error = envelope.get("error")
                detail = error.get("message") if isinstance(error, dict) else None
                raise BridgeError(self._with_checkpoint(
                    f"Bridge exited with code {process.poll()}: {detail or stderr.strip()}", last_progress))
            if envelope.get("ok"):
                if "data" not in envelope:
                    raise BridgeError("Bridge response missing data")
                data = envelope["data"]
                if not isinstance(data, dict):
                    raise BridgeError(f"Bridge response data must be an object, got {type(data).__name__}")
                if (trusted or action == "audit_session_recovery") and _guard.completion is None:
                    raise BridgeError("Production bridge response missing a valid terminal completion receipt")
                return data

            error = envelope.get("error") or {}
            message = (
                error.get("message")
                if isinstance(error, dict)
                else str(error)
            ) or stderr.strip() or "Unknown bridge error"
            raise BridgeError(self._with_checkpoint(message, last_progress))

    @staticmethod
    def _read_output_tail(path: Path, limit: int = 16000) -> str:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - limit))
            return stream.read(limit).decode("utf-8", errors="replace")

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
    def _stop_process(process: subprocess.Popen[bytes]) -> None:
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
        consumed_bytes: int,
        callback: Callable[[dict[str, Any]], None] | None,
        started_at: float,
        last_event: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any] | None]:
        if not path.exists():
            return consumed_bytes, last_event
        # Progress is append-only. Seek past complete records rather than
        # re-reading the entire history every 50 ms. Retain incomplete bytes so
        # a writer splitting a UTF-8 character cannot corrupt the next event.
        with path.open("rb") as stream:
            stream.seek(consumed_bytes)
            pending = stream.read()
        complete_end = pending.rfind(b"\n") + 1
        for line in pending[:complete_end].splitlines():
            try:
                event = json.loads(line.decode("utf-8"))
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
            except (OSError, ValueError):
                continue
            if isinstance(event, dict) and callback is not None:
                callback(event)
        return consumed_bytes + complete_end, last_event
