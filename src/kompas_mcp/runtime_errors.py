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
