from __future__ import annotations

from typing import Any, Protocol

from .native_modules import preview_native_module_launch
from .runtime_errors import classify_runtime_error


class NativeModuleResultAdapter(Protocol):
    def get_session_state(self) -> dict[str, Any]: ...

    def list_documents(self) -> dict[str, Any]: ...

    def get_active_document_state(
        self,
        document_id: str | None = None,
        *,
        require_active_document: bool = True,
        include_tree: bool = False,
        include_items: bool = False,
        max_items: int = 25,
    ) -> dict[str, Any]: ...

    def launch_native_module_command(
        self,
        *,
        module: str = "Spring",
        command_id: int | str | None = 101,
        command_title: str | None = None,
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        post: bool = True,
        visible: bool = True,
        allow_interactive: bool = False,
    ) -> dict[str, Any]: ...


def capture_native_module_result(
    adapter: NativeModuleResultAdapter,
    *,
    module: str = "Spring",
    command_id: int | str | None = 101,
    command_title: str | None = None,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
    document_id: str | None = None,
    require_active_document: bool = False,
    include_tree: bool = True,
    include_items: bool = True,
    max_items: int = 25,
) -> dict[str, Any]:
    """Read bounded document state after a native module command has run interactively."""
    preview = preview_native_module_launch(
        module,
        command_id=command_id,
        command_title=command_title,
        kompas_root=kompas_root,
        libs_dir=libs_dir,
    )
    if not preview.get("ok"):
        return {
            "ok": False,
            "module": module,
            "command_id": command_id,
            "command_title": command_title,
            "stage": "resolve_native_module_command",
            "preview": preview,
            "error": preview.get("error", "Native module command was not resolved"),
        }

    session = _capture_payload("session_state", adapter.get_session_state)
    documents_payload = _capture_payload("list_documents", adapter.list_documents)
    documents = _documents_from_payload(documents_payload.get("payload"))
    selected = _select_document(session.get("payload"), documents, document_id)
    selected_ref = _document_ref(selected, document_id)

    active_state: dict[str, Any] | None = None
    if selected_ref is not None:
        active_state = _capture_payload(
            "active_document_state",
            lambda: adapter.get_active_document_state(
                document_id=selected_ref,
                require_active_document=require_active_document,
                include_tree=include_tree,
                include_items=include_items,
                max_items=max_items,
            ),
        )

    state_payload = active_state.get("payload") if isinstance(active_state, dict) else None
    state_ok = bool(state_payload.get("ok")) if isinstance(state_payload, dict) else False
    document_detected = selected is not None
    ok = bool(preview.get("ok")) and bool(session.get("ok")) and bool(documents_payload.get("ok"))
    if active_state is not None or require_active_document:
        ok = ok and state_ok

    status = "document_readback_captured" if document_detected else "no_document_readback_available"
    result_assumption = (
        "selected document is not proven to have been created by the native module"
        if document_detected
        else "no selected document is available for native module result readback"
    )
    next_step = (
        "If this is the document produced by the native module, inspect tree_preview/items_preview or capture a full document snapshot."
        if document_detected
        else "Finish the native module dialog with model/drawing creation, then run this readback again."
    )

    return {
        "ok": ok,
        "module": preview["module"],
        "command": preview["command"],
        "status": status,
        "result_assumption": result_assumption,
        "readback_only": True,
        "launch_attempted": False,
        "preview": preview,
        "session": session,
        "documents": {
            "ok": documents_payload.get("ok"),
            "count": len(documents),
            "selected": _document_preview(selected),
            "payload": documents_payload.get("payload"),
        },
        "active_document_state": state_payload if isinstance(state_payload, dict) else None,
        "steps": [
            _step_from_capture(session),
            _step_from_capture(documents_payload),
            {
                "step": "select_document",
                "ok": document_detected,
                "expected": {"document_id": document_id or "<active>"},
                "actual": _document_preview(selected),
            },
            _step_from_capture(active_state) if active_state is not None else {
                "step": "active_document_state",
                "ok": not require_active_document,
                "expected": "selected document",
                "actual": None,
            },
        ],
        "next_step": next_step,
    }


def start_native_module_result_probe(
    adapter: NativeModuleResultAdapter,
    *,
    module: str = "Spring",
    command_id: int | str | None = 101,
    command_title: str | None = None,
    kompas_root: str | None = None,
    libs_dir: str | None = None,
    include_tree: bool = True,
    include_items: bool = True,
    max_items: int = 25,
    post: bool = True,
    visible: bool = True,
    allow_interactive: bool = False,
) -> dict[str, Any]:
    """Capture before-state and optionally launch an interactive native command."""
    before = capture_native_module_result(
        adapter,
        module=module,
        command_id=command_id,
        command_title=command_title,
        kompas_root=kompas_root,
        libs_dir=libs_dir,
        require_active_document=False,
        include_tree=include_tree,
        include_items=include_items,
        max_items=max_items,
    )
    if not before.get("ok"):
        return {
            "ok": False,
            "module": before.get("module", module),
            "command": before.get("command") or {"id": command_id, "title": command_title},
            "status": "before_capture_failed",
            "before_capture": before,
            "launch_attempted": False,
            "next_step": "Fix the before capture error, then start the native module result probe again.",
        }

    launch = adapter.launch_native_module_command(
        module=module,
        command_id=command_id,
        command_title=command_title,
        kompas_root=kompas_root,
        libs_dir=libs_dir,
        post=post,
        visible=visible,
        allow_interactive=allow_interactive,
    )
    launch_attempted = bool(launch.get("launch_attempted"))
    launch_ok = bool(launch.get("ok"))
    status = (
        "waiting_for_manual_native_workflow_completion"
        if launch_attempted and launch_ok
        else "preview_only"
        if not launch_attempted and launch_ok
        else "launch_failed"
    )
    return {
        "ok": launch_ok,
        "module": before.get("module"),
        "command": before.get("command"),
        "status": status,
        "workflow": {
            "mode": "manual_native_module_probe",
            "parameter_automation": False,
            "before_capture_done": True,
            "launch_attempted": launch_attempted,
            "requires_user_to_complete_native_ui": launch_attempted and launch_ok,
        },
        "before_capture": before,
        "launch": launch,
        "next_calls": {
            "after_capture": {
                "tool": "capture_native_module_result",
                "arguments": {
                    "module": module,
                    "command_id": command_id,
                    "command_title": command_title,
                    "include_tree": include_tree,
                    "include_items": include_items,
                    "max_items": max_items,
                },
            },
            "diff": {
                "tool": "diff_native_module_results",
                "arguments": {
                    "before": "<before_capture from this payload>",
                    "after": "<after capture payload>",
                },
            },
        },
        "next_step": _native_probe_next_step(status),
    }


def diff_native_module_results(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    max_documents: int = 10,
) -> dict[str, Any]:
    """Compare two native module readbacks captured around an interactive workflow."""
    before_documents = _documents_from_capture(before)
    after_documents = _documents_from_capture(after)
    before_by_ref = {_document_identity(item, offset): item for offset, item in enumerate(before_documents)}
    after_by_ref = {_document_identity(item, offset): item for offset, item in enumerate(after_documents)}
    before_refs = set(before_by_ref)
    after_refs = set(after_by_ref)
    added_refs = sorted(after_refs - before_refs)
    removed_refs = sorted(before_refs - after_refs)
    selected_before = _document_preview(_selected_from_capture(before))
    selected_after = _document_preview(_selected_from_capture(after))
    selected_changed = _document_ref(selected_before, None) != _document_ref(selected_after, None)
    counts_before = _active_counts_from_capture(before)
    counts_after = _active_counts_from_capture(after)
    counts_delta = _counts_delta(counts_before, counts_after)
    active_state_changed = bool(counts_delta) or selected_changed
    detected = bool(added_refs or removed_refs or active_state_changed)
    evidence_level = _native_result_evidence_level(
        added=bool(added_refs),
        removed=bool(removed_refs),
        active_state_changed=active_state_changed,
        before=before,
        after=after,
    )
    return {
        "ok": isinstance(before, dict) and isinstance(after, dict),
        "status": "native_result_delta_detected" if detected else "no_native_result_delta_detected",
        "module": _module_from_captures(before, after),
        "command": _command_from_captures(before, after),
        "readback_diff_only": True,
        "summary": {
            "before_documents": len(before_documents),
            "after_documents": len(after_documents),
            "added_documents": len(added_refs),
            "removed_documents": len(removed_refs),
            "selected_document_changed": selected_changed,
            "active_counts_changed": bool(counts_delta),
        },
        "documents": {
            "selected_before": selected_before,
            "selected_after": selected_after,
            "added": [_document_preview(after_by_ref[key]) for key in added_refs[:max_documents]],
            "removed": [_document_preview(before_by_ref[key]) for key in removed_refs[:max_documents]],
            "truncated": {
                "added": max(0, len(added_refs) - max_documents),
                "removed": max(0, len(removed_refs) - max_documents),
            },
        },
        "active_document_counts": {
            "before": counts_before,
            "after": counts_after,
            "delta": counts_delta,
        },
        "evidence_level": evidence_level,
        "result_assumption": _native_result_assumption(evidence_level),
        "steps": [
            {
                "step": "before_capture",
                "ok": bool(before.get("ok")) if isinstance(before, dict) else False,
                "expected": "capture_native_module_result payload",
                "actual": type(before).__name__,
            },
            {
                "step": "after_capture",
                "ok": bool(after.get("ok")) if isinstance(after, dict) else False,
                "expected": "capture_native_module_result payload",
                "actual": type(after).__name__,
            },
            {
                "step": "detect_delta",
                "ok": detected,
                "expected": "document or active state delta",
                "actual": {"added": len(added_refs), "removed": len(removed_refs), "counts_delta": counts_delta},
            },
        ],
        "next_step": _native_result_next_step(evidence_level),
    }


def _capture_payload(stage: str, callback: Any) -> dict[str, Any]:
    try:
        payload = callback()
    except Exception as exc:
        return {
            "stage": stage,
            "ok": False,
            "payload": None,
            "error": str(exc),
            "exception_type": exc.__class__.__name__,
            "classification": classify_runtime_error(exc, stage=stage),
        }
    return {
        "stage": stage,
        "ok": isinstance(payload, dict),
        "payload": payload if isinstance(payload, dict) else None,
        "actual": type(payload).__name__,
    }


def _step_from_capture(capture: dict[str, Any] | None) -> dict[str, Any]:
    if capture is None:
        return {"step": "capture", "ok": False, "expected": "payload", "actual": None}
    return {
        "step": capture.get("stage"),
        "ok": bool(capture.get("ok")),
        "expected": "dict payload",
        "actual": capture.get("actual") or capture.get("exception_type"),
    }


def _documents_from_payload(payload: Any) -> list[dict[str, Any]]:
    documents = payload.get("documents") if isinstance(payload, dict) else []
    return [item for item in documents if isinstance(item, dict)] if isinstance(documents, list) else []


def _select_document(session: Any, documents: list[dict[str, Any]], document_id: str | None) -> dict[str, Any] | None:
    if document_id:
        for document in documents:
            if document_id in {str(document.get("id")), str(document.get("path")), str(document.get("name"))}:
                return document
    active = session.get("active_document") if isinstance(session, dict) else None
    if isinstance(active, dict):
        active_ref = _document_ref(active, None)
        for document in documents:
            if active_ref and active_ref in {str(document.get("id")), str(document.get("path")), str(document.get("name"))}:
                return document
        return active
    return documents[0] if documents else None


def _document_ref(document: Any, fallback: str | None) -> str | None:
    if isinstance(document, dict):
        for key in ("id", "path", "name"):
            value = document.get(key)
            if value:
                return str(value)
    return fallback


def _document_preview(document: Any) -> dict[str, Any] | None:
    if not isinstance(document, dict):
        return None
    return {
        key: document.get(key)
        for key in ("id", "name", "path", "type", "changed", "active")
        if key in document
    }


def _documents_from_capture(capture: Any) -> list[dict[str, Any]]:
    documents = capture.get("documents") if isinstance(capture, dict) else None
    return _documents_from_payload(documents.get("payload") if isinstance(documents, dict) else None)


def _selected_from_capture(capture: Any) -> dict[str, Any] | None:
    documents = capture.get("documents") if isinstance(capture, dict) else None
    selected = documents.get("selected") if isinstance(documents, dict) else None
    return selected if isinstance(selected, dict) else None


def _document_identity(document: dict[str, Any], offset: int) -> str:
    for key in ("id", "path", "name"):
        value = document.get(key)
        if value:
            return f"{key}:{value}"
    return f"offset:{offset}"


def _active_counts_from_capture(capture: Any) -> dict[str, Any]:
    state = capture.get("active_document_state") if isinstance(capture, dict) else None
    payload = state.get("state") if isinstance(state, dict) else None
    counts = payload.get("counts") if isinstance(payload, dict) else None
    return counts if isinstance(counts, dict) else {}


def _counts_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        before_value = before.get(key)
        after_value = after.get(key)
        if isinstance(before_value, (int, float)) and isinstance(after_value, (int, float)):
            if before_value != after_value:
                delta[key] = after_value - before_value
        elif before_value != after_value:
            delta[key] = {"before": before_value, "after": after_value}
    return delta


def _module_from_captures(before: dict[str, Any], after: dict[str, Any]) -> Any:
    return after.get("module") or before.get("module")


def _command_from_captures(before: dict[str, Any], after: dict[str, Any]) -> Any:
    return after.get("command") or before.get("command")


def _native_result_evidence_level(
    *,
    added: bool,
    removed: bool,
    active_state_changed: bool,
    before: dict[str, Any],
    after: dict[str, Any],
) -> str:
    if added:
        return "new_document_detected"
    if active_state_changed:
        return "active_document_state_changed"
    if not before.get("active_document_state") or not after.get("active_document_state"):
        return "insufficient_document_readback"
    if removed:
        return "document_removed"
    return "no_detected_delta"


def _native_result_assumption(evidence_level: str) -> str:
    if evidence_level == "new_document_detected":
        return "new document appeared between captures; treat it as a candidate native module result until inspected"
    if evidence_level == "active_document_state_changed":
        return "active document readback changed between captures; inspect added/changed tree items before attributing it to the native module"
    if evidence_level == "document_removed":
        return "document set changed, but this does not prove native module output"
    if evidence_level == "insufficient_document_readback":
        return "captures do not include enough document readback to prove a native module result"
    return "no document or active state delta was detected between captures"


def _native_result_next_step(evidence_level: str) -> str:
    if evidence_level in {"new_document_detected", "active_document_state_changed"}:
        return "Run capture_native_module_result on the candidate document with include_tree/include_items enabled, then inspect feature names and counts."
    return "Capture before launching the native command, complete the native workflow, then capture after and diff again."


def _native_probe_next_step(status: str) -> str:
    if status == "waiting_for_manual_native_workflow_completion":
        return "Complete the native module UI manually, create the model or drawing, then run capture_native_module_result and diff_native_module_results with the saved before_capture."
    if status == "preview_only":
        return "Set allow_interactive=true to capture before-state and launch the native KOMPAS command."
    return "Inspect the launch error and retry the probe only after the native command can be launched."
