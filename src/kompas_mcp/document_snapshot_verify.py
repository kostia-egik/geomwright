from __future__ import annotations

from typing import Any

from .document_snapshot_diff import diff_document_snapshots
from .operation_result import normalize_operation_result


def verify_document_snapshot_delta(
    operation: str,
    *,
    before: dict[str, Any] | str | None = None,
    after: dict[str, Any] | str | None = None,
    diff: dict[str, Any] | None = None,
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
    max_items: int = 25,
    ignore_paths: list[str] | tuple[str, ...] | None = None,
    ignore_keys: list[str] | tuple[str, ...] | None = None,
    use_default_volatile_ignores: bool = False,
) -> dict[str, Any]:
    """Verify a bounded before/after readback delta for a primitive operation."""

    checks: list[dict[str, Any]] = []
    delta_error: BaseException | str | None = None
    delta = diff

    if delta is not None and not isinstance(delta, dict):
        checks.append(_check("snapshot_delta_payload_object", False, "dict", type(delta).__name__))
        delta = None
    elif delta is None:
        if before is None or after is None:
            delta = None
            checks.append(_check("snapshot_delta_input_present", False, "diff or before+after", "missing"))
        else:
            try:
                delta = diff_document_snapshots(
                    before,
                    after,
                    max_items=max_items,
                    ignore_paths=ignore_paths,
                    ignore_keys=ignore_keys,
                    use_default_volatile_ignores=use_default_volatile_ignores,
                )
            except Exception as exc:  # pragma: no cover - defensive; exercised through envelope classification.
                delta_error = exc
                delta = None

    if isinstance(delta, dict):
        checks.append(_check("snapshot_delta_ok", bool(delta.get("ok")), True, bool(delta.get("ok"))))
        summary = delta.get("summary") if isinstance(delta.get("summary"), dict) else {}
        checks.extend(
            _summary_checks(
                summary,
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
            )
        )
        checks.extend(_count_delta_checks(delta, expected_counts_delta or {}))

    result = {
        "ok": not any(item.get("ok") is False for item in checks) and delta_error is None,
        "summary": delta.get("summary") if isinstance(delta, dict) else {},
        "counts_delta": delta.get("counts_delta") if isinstance(delta, dict) else {},
        "truncated": delta.get("truncated") if isinstance(delta, dict) else {},
    }
    envelope = normalize_operation_result(
        operation,
        result=result,
        checks=checks,
        error=delta_error,
        stage="snapshot_delta_verification",
        require_result=False,
    )
    envelope["delta"] = _delta_preview(delta)
    return envelope


def _summary_checks(
    summary: dict[str, Any],
    *,
    expected_added: int | None,
    expected_removed: int | None,
    expected_changed: int | None,
    min_added: int | None,
    min_removed: int | None,
    min_changed: int | None,
    max_added: int | None,
    max_removed: int | None,
    max_changed: int | None,
    require_no_removed: bool,
    require_no_changed: bool,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.extend(
        _exact_count_checks(
            summary,
            {
                "added_items": expected_added,
                "removed_items": expected_removed,
                "changed_items": expected_changed,
            },
        )
    )
    checks.extend(
        _range_count_checks(
            summary,
            "min",
            {
                "added_items": min_added,
                "removed_items": min_removed,
                "changed_items": min_changed,
            },
        )
    )
    checks.extend(
        _range_count_checks(
            summary,
            "max",
            {
                "added_items": max_added,
                "removed_items": max_removed,
                "changed_items": max_changed,
            },
        )
    )
    if require_no_removed:
        checks.append(_check("snapshot_delta_no_removed", summary.get("removed_items", 0) == 0, 0, summary.get("removed_items", 0)))
    if require_no_changed:
        checks.append(_check("snapshot_delta_no_changed", summary.get("changed_items", 0) == 0, 0, summary.get("changed_items", 0)))
    return checks


def _exact_count_checks(summary: dict[str, Any], expected: dict[str, int | None]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for field, expected_value in expected.items():
        if expected_value is None:
            continue
        actual = summary.get(field, 0)
        checks.append(_check(f"snapshot_delta_{field}", actual == expected_value, expected_value, actual))
    return checks


def _range_count_checks(summary: dict[str, Any], mode: str, expected: dict[str, int | None]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for field, expected_value in expected.items():
        if expected_value is None:
            continue
        actual = summary.get(field, 0)
        ok = actual >= expected_value if mode == "min" else actual <= expected_value
        checks.append(_check(f"snapshot_delta_{mode}_{field}", ok, {mode: expected_value}, actual))
    return checks


def _count_delta_checks(delta: dict[str, Any], expected_counts_delta: dict[str, int | float]) -> list[dict[str, Any]]:
    counts_delta = delta.get("counts_delta") if isinstance(delta.get("counts_delta"), dict) else {}
    checks: list[dict[str, Any]] = []
    for field, expected_value in expected_counts_delta.items():
        row = counts_delta.get(field) if isinstance(counts_delta.get(field), dict) else {}
        actual = row.get("delta", 0)
        checks.append(_check(f"snapshot_count_delta:{field}", actual == expected_value, expected_value, actual))
    return checks


def _delta_preview(delta: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(delta, dict):
        return {}
    return {
        "summary": delta.get("summary") if isinstance(delta.get("summary"), dict) else {},
        "counts_delta": delta.get("counts_delta") if isinstance(delta.get("counts_delta"), dict) else {},
        "added": delta.get("added") if isinstance(delta.get("added"), list) else [],
        "removed": delta.get("removed") if isinstance(delta.get("removed"), list) else [],
        "changed": delta.get("changed") if isinstance(delta.get("changed"), list) else [],
        "truncated": delta.get("truncated") if isinstance(delta.get("truncated"), dict) else {},
        "ignored": delta.get("ignored") if isinstance(delta.get("ignored"), dict) else {},
    }


def _check(name: str, ok: bool, expected: Any, actual: Any) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "expected": expected, "actual": actual}
