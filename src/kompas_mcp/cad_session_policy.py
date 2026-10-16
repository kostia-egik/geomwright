"""Shared host policy for visible collaborative and owned hidden CAD sessions."""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from .session_guard import SessionGuard, SessionGuardError, process_alive


CAD_WORK_MODES = ("interactive", "hidden")


def validate_mode_action(mode: str, action: str) -> None:
    unsupported = ({"smoke_check_session", "create_spw_from_rows"} if mode == "interactive"
                   else {"launch_native_module_command", "probe_native_entrypoint_loader_hosted"})
    if action in unsupported:
        raise SessionGuardError(f"CAD_MODE_UNSUPPORTED_ACTION: {action} is not supported in {mode} mode; no automatic mode switch or CAD call was made")


def lifecycle_verification(adapter) -> dict:
    reader = getattr(adapter.runner, "get_cad_work_mode", None)
    selection = reader() if callable(reader) else {}
    mode = selection.get("host_mode") or selection.get("mode") or "interactive"
    reopened = mode == "hidden"
    return {"cad_mode": mode, "recipe_reopened": reopened, "save_reopen_deferred": not reopened,
            "scope": "creation_and_save_reopen" if reopened else "creation_and_visible_saved_readback"}


class CadSessionPolicy:
    def __init__(self, guard: SessionGuard):
        self.guard = guard
        self.path = guard.directory / "cad-session.json"

    def read(self) -> dict:
        try:
            context = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "mode": "interactive", "token": None, "binding": None,
                    "target_window_handle": None}
        except (ValueError, OSError) as exc:
            raise SessionGuardError("CAD_SESSION_POLICY_ERROR: unreadable CAD mode; do not bypass it with another directory") from exc
        if (not isinstance(context, dict) or context.get("version") != 1
                or context.get("mode") not in CAD_WORK_MODES or not context.get("token")):
            raise SessionGuardError("CAD_SESSION_POLICY_ERROR: invalid CAD mode record")
        binding = context.get("binding")
        if binding is not None and (not isinstance(binding, dict) or
                any(type(binding.get(key)) is not int or binding[key] <= 0
                    for key in ("window_handle", "process_id", "process_started_at")) or
                type(binding.get("owned")) is not bool):
            raise SessionGuardError("CAD_SESSION_POLICY_ERROR: invalid selected window/process binding")
        return context

    def status(self) -> dict:
        context = self.read()
        return {**context, "configured": context["token"] is not None,
                "cad_readiness_verified": False,
                "visibility_contract": "visible_document_retained" if context["mode"] == "interactive" else "owned_isolated_hidden_process",
                "per_action_ui_animation_guaranteed": False}

    def _write(self, context: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix("." + uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(context, ensure_ascii=True), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def prepare(self, requested_mode: str | None = None, *, action: str = "") -> dict:
        """Called only while this bridge request owns the durable guard."""
        context = self.read()
        validate_mode_action(requested_mode or context["mode"], action)
        if context.get("shutdown_requested"):
            raise SessionGuardError("CAD_HIDDEN_SESSION_ACTIVE: owned shutdown was requested; explicitly select a new mode/session after its process exits")
        if requested_mode is not None and requested_mode not in CAD_WORK_MODES:
            raise ValueError("cad_mode must be interactive or hidden")
        if context["token"] is None:
            context.update(token=uuid4().hex, mode=requested_mode or "interactive")
            self._write(context)
        elif requested_mode is not None and requested_mode != context["mode"]:
            raise SessionGuardError("CAD_MODE_MISMATCH: selected mode differs from this host's mode; use set_cad_work_mode explicitly, never switch automatically")
        return {**context, "context_path": str(self.path.resolve())}

    def configure(self, mode: str, *, confirm_switch: bool, target_window_handle: int | None = None) -> dict:
        if mode not in CAD_WORK_MODES:
            raise ValueError("mode must be interactive or hidden")
        if confirm_switch is not True:
            raise ValueError("Explicit confirm_switch=true is required; selecting a mode does not recover CAD")
        if target_window_handle is not None and (mode != "interactive" or target_window_handle <= 0):
            raise ValueError("A positive target_window_handle is only supported in interactive mode")
        with self.guard._transition():
            if self.guard.status()["blocked"]:
                raise SessionGuardError("CAD_SESSION_BLOCKED: cannot change mode or binding while CAD is in flight or quarantined")
            current = self.read()
            binding = current.get("binding") or {}
            if current["mode"] == "hidden" and process_alive(binding.get("process_id")):
                raise SessionGuardError("CAD_HIDDEN_SESSION_ACTIVE: explicitly shutdown the owned hidden session before changing mode or binding")
            self._write({"version": 1, "mode": mode, "token": uuid4().hex,
                         "binding": None, "target_window_handle": target_window_handle})
        return {"ok": True, **self.status(), "com_called": False, "documents_closed": False}
