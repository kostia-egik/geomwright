"""Durable host-side quarantine; process exit is not cancellation of CAD work."""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from uuid import uuid4


class SessionGuardError(RuntimeError):
    pass


def _helper_job_api():
    import ctypes as c
    from ctypes import wintypes as w

    class Limits(c.Structure):
        _fields_ = [("process_time", c.c_longlong), ("job_time", c.c_longlong),
                    ("flags", w.DWORD), ("min_working_set", c.c_size_t),
                    ("max_working_set", c.c_size_t), ("active_limit", w.DWORD),
                    ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]

    class ExtendedLimits(c.Structure):
        _fields_ = [("basic", Limits), ("io", c.c_ulonglong * 6),
                    ("memory", c.c_size_t * 4)]

    class Accounting(c.Structure):
        _fields_ = [("times", c.c_longlong * 4), ("faults", w.DWORD),
                    ("total", w.DWORD), ("active", w.DWORD), ("terminated", w.DWORD)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.OpenJobObjectW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
    kernel.OpenJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.QueryInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.WaitForSingleObject.restype = w.DWORD
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    return c, kernel, ExtendedLimits, Accounting


def helper_job_active(name):
    """Recovery must not release a still-live, explicitly enrolled Python helper."""
    if not name or os.name != "nt":
        return False
    c, kernel, _, accounting_type = _helper_job_api()
    handle = kernel.OpenJobObjectW(4, False, name)  # JOB_OBJECT_QUERY
    if not handle:
        if c.get_last_error() == 2:  # Object no longer exists.
            return False
        raise SessionGuardError("Cannot verify owned Python helper job")
    try:
        accounting = accounting_type()
        if not kernel.QueryInformationJobObject(handle, 1, c.byref(accounting), c.sizeof(accounting), None):
            raise SessionGuardError("Cannot inspect owned Python helper job")
        return accounting.active != 0
    finally:
        kernel.CloseHandle(handle)


def join_helper_job(name, guard_path):
    """Called by the Python helper itself, before importing/attaching CAD.

    Only the caller is enrolled. Children silently break away, so a COM server
    (including a newly started KOMPAS) can never inherit this kill domain.
    Failure, including an already-closed host job, must abort helper startup.
    """
    if os.name != "nt" or not name:
        raise SessionGuardError("Owned Python helper requires a live Windows host job")
    c, kernel, _, _ = _helper_job_api()
    handle = kernel.OpenJobObjectW(1, False, name)  # JOB_OBJECT_ASSIGN_PROCESS
    if not handle:
        raise SessionGuardError("Owned Python helper host job is unavailable")
    try:
        if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
            raise SessionGuardError("Cannot contain owned Python helper before CAD access")
    finally:
        kernel.CloseHandle(handle)
    # The host closes enrollment BEFORE terminating/waiting. A helper that
    # opened the job just as cleanup began must not proceed into COM after the
    # host observed an empty job. Check only after enrollment and handle close.
    record = json.loads(Path(guard_path).read_text(encoding="utf-8"))
    if record.get("helper_job_name") != name or record.get("helper_job_open") is not True:
        raise SessionGuardError("Owned Python helper host closed enrollment")


class PythonHelperJob:
    """Host-owned kill domain for explicitly enrolled helpers, never process trees."""

    def __init__(self, guard):
        self.guard = guard

    def __enter__(self):
        self.name = None
        self.handle = None
        if os.name != "nt":
            return self
        self.c, self.kernel, limits_type, _ = _helper_job_api()
        self.name = "Local\\Geomwright.PythonHelpers." + uuid4().hex
        self.handle = self.kernel.CreateJobObjectW(None, self.name)
        if not self.handle:
            raise SessionGuardError("Cannot create owned Python helper job")
        limits = limits_type()
        limits.basic.flags = 0x2000 | 0x1000  # KILL_ON_JOB_CLOSE | SILENT_BREAKAWAY_OK
        if not self.kernel.SetInformationJobObject(self.handle, 9, self.c.byref(limits), self.c.sizeof(limits)):
            self.kernel.CloseHandle(self.handle)
            raise SessionGuardError("Cannot configure owned Python helper job")
        return self

    def __exit__(self, *_):
        if self.handle is None:
            return
        process_handles = []
        try:
            try:
                self.guard.record["helper_job_open"] = False
                self.guard._write()
            finally:
                try:
                    self._capture_process_handles(process_handles)
                finally:
                    if not self.kernel.TerminateJobObject(self.handle, 1):
                        raise SessionGuardError("Cannot stop owned Python helpers; CAD outcome remains unknown")
                # ActiveProcesses can reach zero before Windows finishes closing
                # process handles/files. Wait on the actual process objects, not
                # just job accounting, before transport-directory cleanup.
                if process_handles:
                    deadline = time.monotonic() + 2
                    for handle in process_handles:
                        remaining = max(0, int((deadline - time.monotonic()) * 1000))
                        if self.kernel.WaitForSingleObject(handle, remaining) != 0:
                            raise SessionGuardError("Owned Python helper termination was not confirmed")
                if helper_job_active(self.name):
                    deadline = time.monotonic() + 2
                    while helper_job_active(self.name):
                        if time.monotonic() >= deadline:
                            raise SessionGuardError("Owned Python helpers did not exit; CAD outcome remains unknown")
                        time.sleep(0.01)
        finally:
            for handle in process_handles:
                self.kernel.CloseHandle(handle)
            self.kernel.CloseHandle(self.handle)

    def _capture_process_handles(self, handles):
        from ctypes import wintypes as w

        class ProcessIds(self.c.Structure):
            _fields_ = [("assigned", w.DWORD), ("count", w.DWORD),
                        ("ids", self.c.c_size_t * 256)]

        ids = ProcessIds()
        if not self.kernel.QueryInformationJobObject(self.handle, 3, self.c.byref(ids), self.c.sizeof(ids), None):
            raise SessionGuardError("Cannot enumerate owned Python helpers before termination")
        if ids.count > 256 or ids.assigned > 256:
            raise SessionGuardError("Owned Python helper inventory exceeds its bound")
        for pid in ids.ids[:ids.count]:
            handle = self.kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
            if handle:
                handles.append(handle)
            elif self.c.get_last_error() != 87:  # Already exited/no such PID.
                raise SessionGuardError("Cannot wait for owned Python helper termination")


def process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            # Access denied is not evidence that a process finished.
            return ctypes.get_last_error() == 5
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class SessionGuard:
    def __init__(self, directory: str | Path | None = None):
        root = Path(os.environ.get("KOMPAS_MCP_TEMP_DIR", r"C:\Windows\Temp"))
        self.directory = Path(directory or os.environ.get("KOMPAS_MCP_SESSION_GUARD_DIR") or root / "geomwright-session-guard")
        self.path = self.directory / "session.json"
        self.record = None
        self.launched = False
        self.completion = None

    @contextmanager
    def _transition(self):
        # OS-owned lock prevents two recoveries from deleting a newly claimed
        # marker. Unlike the marker, this short critical-section lock dies with
        # the host and never represents CAD readiness.
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "transition.lock").open("a+b") as stream:
            stream.seek(0)
            deadline = time.perf_counter() + 0.5
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.perf_counter() >= deadline:
                        raise SessionGuardError("CAD_SESSION_BLOCKED: host guard transition in progress; no new COM request was sent") from exc
                    time.sleep(0.01)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def status(self) -> dict:
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or not record.get("token"):
                raise ValueError("Invalid guard record")
        except FileNotFoundError:
            return {"blocked": False, "state": "unblocked", "cad_readiness_verified": False}
        except (ValueError, OSError) as exc:
            return {"blocked": True, "state": "unreadable", "token": "unreadable",
                    "error": str(exc)[:500], "cad_readiness_verified": False}
        settled = record.get("state") == "settled_failure"
        return {**record, "blocked": True, "cad_readiness_verified": False,
                "automatic_recovery_available": settled,
                "recovery_hint": (
                    "Call recover_cad_session with this token, confirm_idle=false and a reason. "
                    "It audits the bound session without changing documents. After recovery inspect the affected model before writing; never replay the failed command blindly."
                    if settled else
                    "Do not send CAD commands. Wait for KOMPAS, ask the user to confirm idle UI and resolve partial documents, then explicitly recover this token.")}

    def _write(self):
        with self._transition():
            if self.status().get("token") != self.record["token"]:
                raise SessionGuardError("CAD_SESSION_BLOCKED: guard ownership changed; refusing to overwrite another operation")
            self._write_locked()

    def _write_locked(self):
        temporary = self.directory / (self.record["token"] + ".tmp")
        try:
            temporary.write_text(json.dumps(self.record, ensure_ascii=True), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def release(self):
        with self._transition():
            if self.status().get("token") != self.record["token"]:
                raise SessionGuardError("CAD_SESSION_BLOCKED: guard ownership changed; explicit recovery required")
            self.path.unlink()

    def quarantine(self, error):
        self.record.update(state="unknown_outcome", error=str(error)[:1500])
        self._write()

    def finished(self, outcome):
        """Only the runner may accept a matching terminal response, never progress."""
        if outcome not in ("no_cad", "settled"):
            raise ValueError("Invalid terminal CAD outcome")
        self.completion = outcome
        self.record["completion"] = outcome
        self._write()

    def failed(self, error):
        if self.completion == "no_cad":
            return
        if self.completion == "settled":
            self.record.update(state="settled_failure", error=str(error)[:1500])
            self._write()
        else:
            self.quarantine(error)

    @contextmanager
    def recovery_audit(self, token):
        """Exclusively audit a finished failure; no admission for unknown outcomes."""
        with self._transition():
            original = {key: value for key, value in self.status().items() if key not in
                        ("blocked", "cad_readiness_verified", "automatic_recovery_available", "recovery_hint")}
            if token != original.get("token") or original.get("state") != "settled_failure":
                raise SessionGuardError("CAD_SESSION_BLOCKED: automatic recovery needs the current settled-failure token")
            if process_alive(original.get("bridge_pid")) or helper_job_active(original.get("helper_job_name")):
                raise SessionGuardError("CAD_SESSION_BLOCKED: bridge is still running")
            self.record = deepcopy(original)
            self.record.update(state="recovering", owner_pid=os.getpid(), bridge_pid=None)
            self.launched, self.completion = False, None
            self.audit_recovered = False
            self._write_locked()
        try:
            yield self
        except BaseException as exc:
            if self.launched and self.completion not in ("no_cad", "settled"):
                self.quarantine(exc)
                raise
            self.record = dict(original)
            self._write()
            raise
        else:
            if self.audit_recovered:
                return
            if self.launched and self.completion not in ("no_cad", "settled"):
                self.quarantine("Recovery audit returned without trusted terminal completion")
                raise SessionGuardError("CAD_SESSION_BLOCKED: recovery audit outcome is unknown")
            self.record = dict(original)
            self._write()

    def finish_recovery_audit(self, report, reason):
        if self.completion != "settled" or report.get("session_observed_clear") is not True:
            raise SessionGuardError("CAD_SESSION_BLOCKED: automatic session audit did not pass")
        self.release()
        self.audit_recovered = True
        return {"ok": True, "recovered_token": self.record["token"], "blocked": False,
                "basis": "bound_session_exited" if report.get("bound_session_exited") else "completed_handler_and_session_audit", "reason": reason.strip(),
                "cad_readiness_verified": False, "rollback_performed": False,
                "audit": report,
                "next_step": ("Explicitly select the intended CAD window with set_cad_work_mode before any CAD call. The old process exited; no replacement was attached."
                              if report.get("bound_session_exited") else
                              "Inspect the affected model and partial changes before writing. Do not repeat the failed command blindly; this audit does not verify geometry.")}

    def started(self, process):
        self.launched = True
        self.record.update(state="in_flight", bridge_pid=getattr(process, "pid", None))
        self._write()

    def checkpoint(self, event):
        checkpoint = self.record.setdefault("checkpoint", {})
        checkpoint.update({key: (value[:1000] if isinstance(value, str) else value) for key in
                           ("stage", "document_id", "target", "elapsed_ms", "error", "failed_stage", "cad_mode")
                           if key in event and isinstance(value := event[key], (str, int, bool, type(None)))})
        for key, fields in (("partial_document", ("owned_reference_available", "intended_output_path", "document_id")),
                            ("cleanup", ("attempted", "verified_closed", "reason")),
                            ("session_identity", ("window_handle", "process_id", "process_started_at", "owned"))):
            if isinstance(event.get(key), dict):
                checkpoint[key] = {field: (value[:1000] if isinstance(value, str) else value)
                                   for field in fields if (value := event[key].get(field)) is not None
                                   and isinstance(value, (str, bool, int))}
        if "error" in self.record["checkpoint"]:
            self.record["checkpoint"]["error"] = str(self.record["checkpoint"]["error"])[:1500]
        self._write()

    @contextmanager
    def operation(self, action, payload):
        self.directory.mkdir(parents=True, exist_ok=True)
        record = {"token": uuid4().hex, "state": "launching", "action": str(action)[:200],
                       "document_id": str(payload.get("document_id") or "")[:1000],
                       "owner_pid": os.getpid(), "bridge_pid": None, "started_at": time.time()}
        try:
            with self._transition():
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(record, stream, ensure_ascii=True)
                self.record = record
                self.launched = False
                self.completion = None
        except FileExistsError:
            status = self.status()
            if status["state"] == "settled_failure":
                raise SessionGuardError("CAD_DIAGNOSTICS_REQUIRED: previous handler finished with an error; call recover_cad_session with the current token and confirm_idle=false for automatic audit")
            raise SessionGuardError(f"CAD_SESSION_BLOCKED: {status['state']}; use get_cad_session_guard and explicit recovery, not another COM request")
        try:
            yield self
        except BaseException as exc:
            if self.launched:
                if self.completion == "no_cad":
                    self.release()
                else:
                    self.failed(exc)
            else:
                self.release()
            raise
        else:
            if self.record["state"] not in ("unknown_outcome", "settled_failure"):
                try:
                    self.release()
                except SessionGuardError as exc:
                    if self.launched:
                        self.quarantine(exc)
                    raise

    def recover(self, token: str, *, confirm_idle: bool, reason: str) -> dict:
        if confirm_idle is not True or not reason.strip() or len(reason) > 500:
            raise ValueError("Explicit user idle confirmation and a nonempty reason (max500 chars) are required")
        with self._transition():
            return self._recover_locked(token, reason)

    def _recover_locked(self, token, reason):
        status = self.status()
        if not status["blocked"]:
            raise ValueError("No blocked session to recover")
        if token != status.get("token"):
            raise ValueError("Guard token changed; read status and obtain a new confirmation")
        if helper_job_active(status.get("helper_job_name")):
            raise SessionGuardError("CAD_SESSION_BLOCKED: owned Python helper is still running")
        if process_alive(status.get("bridge_pid")) or (status["state"] in {"launching", "in_flight", "recovering"} and process_alive(status.get("owner_pid"))):
            raise SessionGuardError("CAD_SESSION_BLOCKED: bridge/launch is still running; recovery cannot terminate it")
        if self.status().get("token") != token:
            raise SessionGuardError("CAD_SESSION_BLOCKED: state changed during recovery")
        self.path.unlink()
        return {"ok": True, "recovered_token": token, "blocked": False,
                "basis": "explicit_user_idle_confirmation", "reason": reason.strip(),
                "cad_readiness_verified": False, "rollback_performed": False,
                "next_step": "Read session/document state before deciding on a new write; recovery did not call COM or close any document."}
