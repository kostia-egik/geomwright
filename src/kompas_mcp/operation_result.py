from __future__ import annotations

from pathlib import Path
from typing import Any

from .runtime_errors import classify_runtime_error


def normalize_operation_result(
    operation: str,
    *,
    result: dict[str, Any] | None = None,
    preflight: dict[str, Any] | None = None,
    readback_contract: dict[str, Any] | None = None,
    checks: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    error: BaseException | str | None = None,
    exception_type: str | None = None,
    artifacts: dict[str, str] | None = None,
    stage: str = "operation_result",
    require_result: bool = True,
) -> dict[str, Any]:
    normalized_checks: list[dict[str, Any]] = []
    error_payload = classify_runtime_error(error, stage=stage, exception_type=exception_type) if error is not None else None

    if result is not None and not isinstance(result, dict):
        normalized_checks.append(_check("result_payload_object", False, "dict", type(result).__name__))
        result = None
    if artifacts is not None and not isinstance(artifacts, dict):
        normalized_checks.append(_check("artifacts_payload_object", False, "dict", type(artifacts).__name__))
        artifacts = None

    if require_result:
        normalized_checks.append(_check("result_present", result is not None, True, result is not None))
    if isinstance(result, dict) and "ok" in result:
        normalized_checks.append(_check("operation_result_ok", bool(result.get("ok")), True, bool(result.get("ok"))))

    if preflight is not None and not isinstance(preflight, dict):
        normalized_checks.append(_check("preflight_payload_object", False, "dict", type(preflight).__name__))
        preflight = None
    if readback_contract is not None and not isinstance(readback_contract, dict):
        normalized_checks.append(_check("readback_contract_payload_object", False, "dict", type(readback_contract).__name__))
        readback_contract = None

    if preflight is not None:
        normalized_checks.append(_check("preflight_ok", bool(preflight.get("ok")), True, bool(preflight.get("ok"))))
        normalized_checks.extend(_prefixed_failed_checks("preflight", preflight))

    if readback_contract is not None:
        normalized_checks.append(
            _check("readback_contract_ok", bool(readback_contract.get("ok")), True, bool(readback_contract.get("ok")))
        )
        normalized_checks.extend(_prefixed_failed_checks("readback", readback_contract))

    for item in checks or ():
        if isinstance(item, dict):
            normalized_checks.append(_normalize_check(item))

    if error_payload is not None:
        normalized_checks.append(_check("runtime_error_absent", False, None, error_payload))

    artifact_rows = _artifact_rows(artifacts or {})
    if artifact_rows:
        for row in artifact_rows:
            normalized_checks.append(_check(f"artifact_exists:{row['role']}", row["exists"], True, row["exists"], row))

    failures = [check for check in normalized_checks if check.get("ok") is False]
    return {
        "stage": stage,
        "operation": operation,
        "ok": not failures and error_payload is None,
        "status": "ok" if not failures and error_payload is None else "failed",
        "error": error_payload,
        "result_preview": _payload_preview(result),
        "checks": normalized_checks,
        "failures": failures,
        "artifacts": artifact_rows,
    }


def _check(name: str, ok: bool, expected: Any, actual: Any, details: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"name": name, "ok": bool(ok), "expected": expected, "actual": actual}
    if details:
        payload["details"] = details
    return payload


def _normalize_check(item: dict[str, Any]) -> dict[str, Any]:
    return _check(
        str(item.get("name") or "check"),
        bool(item.get("ok")),
        item.get("expected"),
        item.get("actual"),
        item.get("details") if isinstance(item.get("details"), dict) else None,
    )


def _prefixed_failed_checks(prefix: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return []
    failed: list[dict[str, Any]] = []
    for item in checks:
        if not isinstance(item, dict) or item.get("ok") is not False:
            continue
        check = _normalize_check(item)
        check["name"] = f"{prefix}:{check['name']}"
        failed.append(check)
    return failed


def _payload_preview(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    preview: dict[str, Any] = {"keys": sorted(str(key) for key in payload.keys())[:16]}
    for key in ("ok", "id", "name", "type", "document_id", "output_path", "saved", "scenario"):
        if key in payload:
            preview[key] = payload.get(key)
    if isinstance(payload.get("steps"), list):
        steps = [step for step in payload["steps"] if isinstance(step, dict)]
        preview["steps"] = len(steps)
        preview["failed_steps"] = [str(step.get("step") or "") for step in steps if step.get("ok") is False][:12]
    if isinstance(payload.get("items"), list):
        preview["items"] = len(payload["items"])
    if isinstance(payload.get("counts"), dict):
        preview["counts"] = payload["counts"]
    return preview


def _artifact_rows(artifacts: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role, path_text in artifacts.items():
        try:
            path = Path(path_text)
            exists = path.exists()
            size_bytes = path.stat().st_size if exists else 0
        except (OSError, TypeError, ValueError) as exc:
            rows.append(
                {
                    "role": str(role),
                    "path": str(path_text),
                    "exists": False,
                    "size_bytes": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        rows.append(
            {
                "role": str(role),
                "path": str(path),
                "exists": exists,
                "size_bytes": size_bytes,
            }
        )
    return rows
