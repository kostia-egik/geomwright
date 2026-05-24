from __future__ import annotations

from typing import Any, Callable

from .operation_result import normalize_operation_result
from .operation_runtime import DocumentReadbackContractSpec, verify_document_readback_contract


PrimitiveOperationCallable = Callable[[], dict[str, Any]]
PrimitivePayloadCallable = Callable[[], dict[str, Any]]


def execute_primitive_operation(
    operation: str,
    run_operation: PrimitiveOperationCallable,
    *,
    preflight: dict[str, Any] | PrimitivePayloadCallable | None = None,
    readback: dict[str, Any] | PrimitivePayloadCallable | None = None,
    readback_contract_spec: DocumentReadbackContractSpec | None = None,
    checks: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    artifacts: dict[str, str] | None = None,
    stage: str = "primitive_operation",
    stop_on_preflight_failure: bool = True,
    require_result: bool = True,
) -> dict[str, Any]:
    preflight_report: dict[str, Any] | None = None
    readback_report: dict[str, Any] | None = None
    readback_contract: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    runtime_checks = list(checks or ())
    execution = {
        "preflight_ran": False,
        "operation_ran": False,
        "readback_ran": False,
        "readback_contract_ran": False,
    }

    try:
        preflight_report = _resolve_payload(preflight)
        execution["preflight_ran"] = preflight is not None
    except Exception as exc:
        return _envelope(
            operation,
            stage,
            result=None,
            preflight=preflight_report,
            readback_contract=None,
            checks=runtime_checks,
            error=exc,
            artifacts=artifacts,
            require_result=False,
            execution=execution,
        )

    if stop_on_preflight_failure and preflight_report is not None and preflight_report.get("ok") is False:
        runtime_checks.append(
            {
                "name": "operation_skipped_after_preflight",
                "ok": False,
                "expected": "preflight_ok",
                "actual": "preflight_failed",
            }
        )
        return _envelope(
            operation,
            stage,
            result=None,
            preflight=preflight_report,
            readback_contract=None,
            checks=runtime_checks,
            artifacts=artifacts,
            require_result=False,
            execution=execution,
        )

    try:
        result = run_operation()
        execution["operation_ran"] = True
    except Exception as exc:
        return _envelope(
            operation,
            stage,
            result=None,
            preflight=preflight_report,
            readback_contract=None,
            checks=runtime_checks,
            error=exc,
            artifacts=artifacts,
            require_result=False,
            execution=execution,
        )

    try:
        readback_report = _resolve_payload(readback)
        execution["readback_ran"] = readback is not None
    except Exception as exc:
        return _envelope(
            operation,
            stage,
            result=result,
            preflight=preflight_report,
            readback_contract=None,
            checks=runtime_checks,
            error=exc,
            artifacts=artifacts,
            require_result=require_result,
            execution=execution,
        )

    if readback_report is not None and readback_contract_spec is not None:
        readback_contract = verify_document_readback_contract(
            readback_report,
            readback_contract_spec,
            stage=f"{stage}_readback_contract",
        ).to_dict()
        execution["readback_contract_ran"] = True

    return _envelope(
        operation,
        stage,
        result=result,
        preflight=preflight_report,
        readback_contract=readback_contract,
        checks=runtime_checks,
        artifacts=artifacts,
        require_result=require_result,
        execution=execution,
    )


def _resolve_payload(payload: dict[str, Any] | PrimitivePayloadCallable | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    resolved = payload() if callable(payload) else payload
    if not isinstance(resolved, dict):
        raise TypeError(f"operation payload must be dict, got {type(resolved).__name__}")
    return resolved


def _envelope(
    operation: str,
    stage: str,
    *,
    result: dict[str, Any] | None,
    preflight: dict[str, Any] | None,
    readback_contract: dict[str, Any] | None,
    checks: list[dict[str, Any]],
    artifacts: dict[str, str] | None,
    require_result: bool,
    execution: dict[str, bool],
    error: BaseException | str | None = None,
) -> dict[str, Any]:
    payload = normalize_operation_result(
        operation,
        result=result,
        preflight=preflight,
        readback_contract=readback_contract,
        checks=checks,
        error=error,
        exception_type=type(error).__name__ if isinstance(error, BaseException) else None,
        artifacts=artifacts,
        stage=stage,
        require_result=require_result,
    )
    payload["execution"] = dict(execution)
    return payload
