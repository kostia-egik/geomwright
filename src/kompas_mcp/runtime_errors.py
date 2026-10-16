from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeErrorClassification:
    code: str
    category: str
    message: str
    exception_type: str | None = None
    stage: str | None = None
    retryable: bool = False
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.exception_type:
            payload["exception_type"] = self.exception_type
        if self.stage:
            payload["stage"] = self.stage
        if self.hint:
            payload["hint"] = self.hint
        return payload


def classify_runtime_error(
    error: BaseException | str | None,
    *,
    stage: str | None = None,
    exception_type: str | None = None,
) -> dict[str, Any]:
    text = _error_message(error)
    type_name = exception_type or (type(error).__name__ if isinstance(error, BaseException) else None)
    lowered = text.casefold()

    if "cad_diagnostics_required:" in lowered:
        return RuntimeErrorClassification(
            code="CAD_DIAGNOSTICS_REQUIRED", category="session", message=text,
            exception_type=type_name, stage=stage,
            hint="The handler finished. Read get_cad_session_guard, then call recover_cad_session with its token, a reason and confirm_idle=false for automatic audit. No user confirmation is needed unless the audit reports a blocker. Inspect the affected model before writing; never replay blindly.",
        ).to_dict()

    for code in ("CAD_SESSION_POLICY_REQUIRED", "CAD_SESSION_POLICY_ERROR", "CAD_SESSION_CHANGED",
                 "CAD_SESSION_NOT_VISIBLE", "CAD_SESSION_AMBIGUOUS", "CAD_SESSION_IDENTITY_UNAVAILABLE",
                 "CAD_MODE_MISMATCH", "CAD_MODE_UNSUPPORTED_ACTION", "CAD_HIDDEN_SESSION_ACTIVE",
                 "CAD_HIDDEN_SESSION_NOT_OWNED", "CAD_HIDDEN_SESSION_NOT_ISOLATED"):
        if "cad_session_blocked:" not in lowered and code.casefold() + ":" in lowered:
            return RuntimeErrorClassification(
                code=code, category="session", message=text, exception_type=type_name, stage=stage,
                hint="Read get_cad_work_mode and get_cad_session_guard without COM. Resolve the selected mode/window explicitly; never substitute another instance. A settled_failure permits automatic recover_cad_session; unknown outcomes require user idle confirmation.",
            ).to_dict()

    if "cad_session_blocked:" in lowered:
        return RuntimeErrorClassification(
            code="CAD_SESSION_BLOCKED",
            category="session",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Read get_cad_session_guard without COM. Wait for KOMPAS and obtain the user's explicit idle UI/partial-document confirmation before recover_cad_session. Do not retry, inspect or close through COM while blocked.",
        ).to_dict()

    if "cad_runtime_invalid:" in lowered:
        return RuntimeErrorClassification(
            code="CAD_RUNTIME_INVALID", category="environment", message=text,
            exception_type=type_name, stage=stage,
            hint="Configure KOMPAS_PYTHON with a compatible modern Python and pywin32, then repeat host-only preflight. The failed call did not launch CAD, but earlier workflow steps may have written a partial document. Check the guard; do not recover an independently blocked session without user confirmation.",
        ).to_dict()

    if "cad_self_intersection:" in lowered:
        return RuntimeErrorClassification(
            code="CAD_SELF_INTERSECTION",
            category="geometry",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Review the spring geometry and transition dimensions; do not retry the same inputs or silently change them.",
        ).to_dict()

    if "cad_busy:" in lowered:
        return RuntimeErrorClassification(
            code="CAD_BUSY",
            category="session",
            message=text,
            exception_type=type_name,
            stage=stage,
            retryable=True,
            hint="Wait for the owning MCP/Studio request to finish, then retry sequentially. Do not start another CAD worker.",
        ).to_dict()

    if "selector is stale" in lowered or "body geometry changed" in lowered:
        return RuntimeErrorClassification(
            code="STALE_GEOMETRY_SELECTOR",
            category="target_resolution",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Run list_model_bodies and list_body_faces/list_body_edges again; do not reuse topology selectors after rebuild or reopen.",
        ).to_dict()

    if _contains_any(lowered, ("no active document", "active document missing", "активн")):
        return RuntimeErrorClassification(
            code="NO_ACTIVE_DOCUMENT",
            category="document_state",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Open or activate a KOMPAS document before running the operation.",
        ).to_dict()

    if _contains_any(lowered, ("document not found", "not found or no active document", "документ не найден")):
        return RuntimeErrorClassification(
            code="DOCUMENT_NOT_FOUND",
            category="document_state",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Pass a valid document id/path/name or run list_documents first.",
        ).to_dict()

    if _contains_any(lowered, ("wrong document type", "unsupported document type", "document_type", "не тот тип")):
        return RuntimeErrorClassification(
            code="WRONG_DOCUMENT_TYPE",
            category="document_state",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Check the active document type with preflight_document_context.",
        ).to_dict()

    if _contains_any(lowered, ("invalid input", "must contain exactly", "must be greater than zero", "malformed payload")):
        return RuntimeErrorClassification(
            code="INVALID_INPUT",
            category="input",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Fix the tool arguments before retrying.",
        ).to_dict()

    if _contains_any(lowered, ("ambiguous target", "multiple target", "provide sketch_ref or create_new_sketch")):
        return RuntimeErrorClassification(
            code="AMBIGUOUS_TARGET",
            category="target_resolution",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Select exactly one target sketch/plane strategy.",
        ).to_dict()

    if _contains_any(lowered, ("unsupported com shape", "does not expose", "not implemented for this com")):
        return RuntimeErrorClassification(
            code="UNSUPPORTED_COM_SHAPE",
            category="com_shape",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Run probe_model_object_collections or probe_document_readback to inspect available COM surfaces.",
        ).to_dict()

    if _contains_any(lowered, ("kompas python not found", "python not found")):
        return RuntimeErrorClassification(
            code="KOMPAS_PYTHON_NOT_FOUND",
            category="environment",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Configure KOMPAS_PYTHON or install the KOMPAS automation Python runtime.",
        ).to_dict()

    if _contains_any(lowered, ("kompas", "компас")) and _contains_any(
        lowered,
        ("not running", "unavailable", "server execution failed", "class not registered", "не запущ"),
    ):
        return RuntimeErrorClassification(
            code="KOMPAS_SESSION_UNAVAILABLE",
            category="session",
            message=text,
            exception_type=type_name,
            stage=stage,
            retryable=True,
            hint="Start KOMPAS and retry the session/preflight call.",
        ).to_dict()

    if _contains_any(lowered, ("com", "dispatch", "ole", "pywintypes")):
        return RuntimeErrorClassification(
            code="COM_CALL_FAILED",
            category="com",
            message=text,
            exception_type=type_name,
            stage=stage,
            retryable=True,
            hint="Retry after preflight; if it repeats, capture the bridge stderr/stdout.",
        ).to_dict()

    if _contains_any(lowered, ("returned none", "returned null", "operation returned none")):
        return RuntimeErrorClassification(
            code="EMPTY_OPERATION_RESULT",
            category="operation_result",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Verify the primitive operation selected the expected document/object.",
        ).to_dict()

    if _contains_any(lowered, ("readback empty", "empty readback", "no readback", "tree empty", "empty payload")):
        return RuntimeErrorClassification(
            code="EMPTY_READBACK",
            category="readback",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Run probe_document_readback to see which tree/items surfaces are available.",
        ).to_dict()

    if _contains_any(lowered, ("file not found", "does not exist", "no such file", "cannot find the file")):
        return RuntimeErrorClassification(
            code="FILE_NOT_FOUND",
            category="filesystem",
            message=text,
            exception_type=type_name,
            stage=stage,
            hint="Check the path on the KOMPAS host and prefer an absolute path.",
        ).to_dict()

    return RuntimeErrorClassification(
        code="UNKNOWN_RUNTIME_ERROR",
        category="unknown",
        message=text,
        exception_type=type_name,
        stage=stage,
        retryable=True,
        hint="Capture preflight, operation result, and readback manifest for triage.",
    ).to_dict()


def _error_message(error: BaseException | str | None) -> str:
    if error is None:
        return ""
    return str(error)


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)
