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
