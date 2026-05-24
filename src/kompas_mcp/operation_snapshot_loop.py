from __future__ import annotations

from typing import Any, Callable

from .document_snapshot_verify import verify_document_snapshot_delta
from .operation_result import normalize_operation_result


SnapshotCallable = Callable[[], dict[str, Any]]
PrimitiveOperationCallable = Callable[[], dict[str, Any]]


def execute_snapshot_verified_operation(
    operation: str,
    run_operation: PrimitiveOperationCallable,
    *,
    before_snapshot: dict[str, Any] | SnapshotCallable,
    after_snapshot: dict[str, Any] | SnapshotCallable,
    expected_added: int | None = None,
    expected_removed: int | None = None,
    expected_changed: int | None = None,
    min_added: int | None = None,
    min_removed: int | None = None,
    min_changed: int | None = None,
    max_added: int | None = None,
    max_removed: int | None = None,
    max_changed: int | None = None,
    require_no_removed: bool = False,
    require_no_changed: bool = False,
    expected_counts_delta: dict[str, int | float] | None = None,
    ignore_paths: list[str] | tuple[str, ...] | None = None,
    ignore_keys: list[str] | tuple[str, ...] | None = None,
    use_default_volatile_ignores: bool = False,
    checks: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    artifacts: dict[str, str] | None = None,
    stage: str = "snapshot_verified_operation",
    stop_on_before_snapshot_failure: bool = True,
    max_items: int = 25,
) -> dict[str, Any]:
    """Run a primitive operation between two snapshots and verify the readback delta."""

    runtime_checks = list(checks or ())
    execution = {
        "before_snapshot_ran": False,
        "operation_ran": False,
        "after_snapshot_ran": False,
        "delta_verification_ran": False,
    }
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    operation_result: dict[str, Any] | None = None
    delta_verification: dict[str, Any] | None = None

    try:
        before = _resolve_snapshot(before_snapshot)
        execution["before_snapshot_ran"] = True
    except Exception as exc:
        return _envelope(
            operation,
            stage,
            result=None,
            before=before,
            after=after,
            delta_verification=delta_verification,
            checks=runtime_checks,
            error=exc,
            artifacts=artifacts,
            execution=execution,
        )

    if stop_on_before_snapshot_failure and before.get("ok") is False:
        runtime_checks.append(
            {
                "name": "operation_skipped_after_before_snapshot",
                "ok": False,
                "expected": "before_snapshot_ok",
                "actual": "before_snapshot_failed",
            }
        )
        return _envelope(
            operation,
            stage,
            result=None,
            before=before,
            after=after,
            delta_verification=delta_verification,
            checks=runtime_checks,
            artifacts=artifacts,
            execution=execution,
        )

    try:
        operation_result = run_operation()
        execution["operation_ran"] = True
    except Exception as exc:
        return _envelope(
            operation,
            stage,
            result=None,
            before=before,
            after=after,
            delta_verification=delta_verification,
            checks=runtime_checks,
            error=exc,
            artifacts=artifacts,
            execution=execution,
        )

    try:
        after = _resolve_snapshot(after_snapshot)
        execution["after_snapshot_ran"] = True
    except Exception as exc:
        return _envelope(
            operation,
            stage,
            result=operation_result,
            before=before,
            after=after,
            delta_verification=delta_verification,
            checks=runtime_checks,
            error=exc,
            artifacts=artifacts,
            execution=execution,
        )

    delta_verification = verify_document_snapshot_delta(
        operation,
        before=before,
        after=after,
        expected_added=expected_added,
        expected_removed=expected_removed,
        expected_changed=expected_changed,
        min_added=min_added,
        min_removed=min_removed,
        min_changed=min_changed,
        max_added=max_added,
        max_removed=max_removed,
        max_changed=max_changed,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        expected_counts_delta=expected_counts_delta,
        ignore_paths=ignore_paths,
        ignore_keys=ignore_keys,
        use_default_volatile_ignores=use_default_volatile_ignores,
        max_items=max_items,
    )
    execution["delta_verification_ran"] = True

    runtime_checks.append(
        {
            "name": "snapshot_delta_verification_ok",
            "ok": bool(delta_verification.get("ok")),
            "expected": True,
            "actual": bool(delta_verification.get("ok")),
        }
    )
    runtime_checks.extend(_prefixed_failures("snapshot_delta", delta_verification))
    return _envelope(
        operation,
        stage,
        result=operation_result,
        before=before,
        after=after,
        delta_verification=delta_verification,
        checks=runtime_checks,
        artifacts=artifacts,
        execution=execution,
    )


def _resolve_snapshot(snapshot: dict[str, Any] | SnapshotCallable) -> dict[str, Any]:
    payload = snapshot() if callable(snapshot) else snapshot
    if not isinstance(payload, dict):
        raise TypeError(f"snapshot payload must be dict, got {type(payload).__name__}")
    return payload


def _envelope(
    operation: str,
    stage: str,
    *,
    result: dict[str, Any] | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    delta_verification: dict[str, Any] | None,
    checks: list[dict[str, Any]],
    execution: dict[str, bool],
    artifacts: dict[str, str] | None,
    error: BaseException | str | None = None,
) -> dict[str, Any]:
    envelope = normalize_operation_result(
        operation,
        result=result,
        checks=checks,
        error=error,
        exception_type=type(error).__name__ if isinstance(error, BaseException) else None,
        artifacts=artifacts,
        stage=stage,
        require_result=False,
    )
    envelope["execution"] = dict(execution)
    envelope["snapshots"] = {
        "before": _snapshot_preview(before),
        "after": _snapshot_preview(after),
    }
    envelope["delta"] = (
        delta_verification.get("delta")
        if isinstance(delta_verification, dict) and isinstance(delta_verification.get("delta"), dict)
        else {}
    )
    return envelope


def _snapshot_preview(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    payload = snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else snapshot
    return {
        "ok": bool(snapshot.get("ok")),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "counts": payload.get("counts") if isinstance(payload.get("counts"), dict) else {},
        "index_counts": payload.get("index_counts") if isinstance(payload.get("index_counts"), dict) else {},
        "artifact": payload.get("artifact") if isinstance(payload.get("artifact"), dict) else None,
    }


def _prefixed_failures(prefix: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    rows: list[dict[str, Any]] = []
    for item in failures:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["name"] = f"{prefix}:{row.get('name') or 'failure'}"
        rows.append(row)
    return rows
