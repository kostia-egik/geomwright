from __future__ import annotations

import json
import time
import traceback
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from .document_readback import DocumentReadbackCallable, build_document_readback_manifest, run_document_readback
from .operation_runtime import (
    DocumentReadbackContractSpec,
    OperationContractSpec,
    OperationInvariantReport,
    OperationInvariantSpec,
    ThreadGeometryProbeSpec,
    build_diagnostic_bundle,
    build_failure_triage,
    build_human_audit_report,
    build_operation_manifest,
    build_reproducibility_snapshot,
    build_run_ledger,
    compare_run_regression,
    verify_document_readback_contract,
    verify_operation_contract,
    verify_operation_result,
    verify_thread_geometry_probes,
)


CreatePartCallable = Callable[..., dict[str, Any]]


def run_verified_kompas_task(
    *,
    payload: dict[str, Any],
    preflight: dict[str, Any],
    output_base_dir: str | Path,
    create_part: CreatePartCallable,
    invariant_spec: OperationInvariantSpec,
    contract_spec: OperationContractSpec,
    thread_geometry_spec: ThreadGeometryProbeSpec | None = None,
    run_index_name: str | None = None,
    created_elements: tuple[str, ...] = (),
    stage_prefix: str = "verified_kompas_task",
    require_regression_baseline: bool = False,
    require_document_readback: bool = False,
    document_readback_contract_spec: DocumentReadbackContractSpec | None = None,
    document_readback: DocumentReadbackCallable | None = None,
    visible: bool = False,
    close_after_save: bool = True,
) -> dict[str, Any]:
    """Run a KOMPAS scenario and write the standard verified-task report set."""
    preflight = _normalize_preflight_payload(preflight)
    base_dir = Path(output_base_dir)
    output_dir = _next_output_dir(base_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    transaction = _new_transaction(
        stage_prefix=stage_prefix,
        scenario=str(payload.get("scenario") or ""),
        output_dir=output_dir,
    )
    _write_transaction(output_dir, transaction)

    _write_json(output_dir / "01_sketch_runtime_preflight.json", preflight)
    _write_json(output_dir / "02_kompas_task_payload.json", payload)
    _finish_transaction_phase(output_dir, transaction, "prepare", ok=bool(preflight.get("report", {}).get("ok")))

    scenario = str(payload["scenario"])
    params = dict(payload["params"])
    output_name = str(payload["output_name"])
    output_path = output_dir / output_name

    try:
        result = create_part(
            scenario,
            params,
            output_path=str(output_path),
            visible=visible,
            close_after_save=close_after_save,
        )
    except Exception as exc:
        error_payload = _build_exception_payload(exc, stage=f"{stage_prefix}_create_part")
        _write_json(output_dir / "03_kompas_create_error.json", error_payload)
        _finish_transaction_phase(output_dir, transaction, "create", ok=False, details=error_payload)
        raise
    if not isinstance(result, dict):
        result = _build_malformed_payload(
            stage=f"{stage_prefix}_create_part_result",
            source="create_part",
            value=result,
        )
    _write_json(output_dir / "03_kompas_create_result.json", result)
    _finish_transaction_phase(output_dir, transaction, "create", ok=bool(result.get("ok")), details={"saved": bool(result.get("saved"))})

    document_readback_report: dict[str, Any] | None = None
    document_readback_contract_report: OperationInvariantReport | None = None
    document_readback_manifest: dict[str, Any] | None = None
    if document_readback is not None:
        document_readback_report = run_document_readback(
            output_path,
            document_readback,
            stage=f"{stage_prefix}_com_document_readback",
        )
        _write_json(output_dir / "14_com_document_readback.json", document_readback_report)
        document_readback_contract_report = verify_document_readback_contract(
            document_readback_report,
            document_readback_contract_spec or DocumentReadbackContractSpec(),
            stage=f"{stage_prefix}_com_readback_contract",
        )
        _write_json(output_dir / "15_com_readback_contract.json", document_readback_contract_report.to_dict())
        document_readback_manifest = build_document_readback_manifest(
            document_readback_report,
            stage=f"{stage_prefix}_com_readback_manifest",
        )
        _write_json(output_dir / "16_com_readback_manifest.json", document_readback_manifest)

    if invariant_spec.output_path is None:
        invariant_spec = replace(invariant_spec, output_path=str(output_path))
    invariant_report = verify_operation_result(
        result,
        invariant_spec,
        stage=f"{stage_prefix}_operation_invariants",
    )
    _write_json(output_dir / "04_operation_invariants.json", invariant_report.to_dict())

    operation_manifest = build_operation_manifest(result, stage=f"{stage_prefix}_operation_manifest")
    _write_json(output_dir / "05_operation_manifest.json", operation_manifest)

    reports: dict[str, OperationInvariantReport | dict[str, Any]] = {
        "sketch_runtime_preflight": preflight["report"],
        "operation_invariants": invariant_report,
    }
    geometry_probe_report: OperationInvariantReport | None = None
    if thread_geometry_spec is not None:
        geometry_probe_report = verify_thread_geometry_probes(
            result,
            thread_geometry_spec,
            stage=f"{stage_prefix}_thread_geometry_probes",
        )
        _write_json(output_dir / "06_thread_geometry_probes.json", geometry_probe_report.to_dict())
        reports["thread_geometry_probes"] = geometry_probe_report

    diagnostic_bundle = build_diagnostic_bundle(
        scenario=scenario,
        reports=reports,
        artifacts={"model": str(output_path)},
        manifest=operation_manifest,
        stage=f"{stage_prefix}_diagnostics",
    )
    _write_json(output_dir / "07_diagnostic_bundle.json", diagnostic_bundle)

    operation_contract_report = verify_operation_contract(
        diagnostic_bundle,
        operation_manifest,
        contract_spec,
        stage=f"{stage_prefix}_operation_contract",
    )
    _write_json(output_dir / "08_operation_contract.json", operation_contract_report.to_dict())
    _finish_transaction_phase(
        output_dir,
        transaction,
        "verify",
        ok=bool(diagnostic_bundle["ok"]) and operation_contract_report.ok,
        details={
            "diagnostics_ok": bool(diagnostic_bundle["ok"]),
            "operation_contract_ok": operation_contract_report.ok,
        },
    )

    summary = _build_initial_summary(
        payload=payload,
        preflight=preflight,
        result=result,
        output_path=output_path,
        invariant_report=invariant_report,
        operation_manifest=operation_manifest,
        geometry_probe_report=geometry_probe_report,
        diagnostic_bundle=diagnostic_bundle,
        operation_contract_report=operation_contract_report,
        document_readback_report=document_readback_report,
        document_readback_contract_report=document_readback_contract_report,
        document_readback_manifest=document_readback_manifest,
        require_document_readback=require_document_readback,
        created_elements=created_elements,
    )
    _write_json(output_dir / "summary.json", summary)

    run_ledger = build_run_ledger(
        base_dir.parent,
        run_prefix=base_dir.name,
        stage=f"{stage_prefix}_run_ledger",
    )
    _write_json(output_dir / "09_run_ledger.json", run_ledger)
    if run_index_name:
        _write_json(base_dir.parent / run_index_name, run_ledger)

    summary.update(
        {
            "run_ledger_ok": bool(run_ledger["ok"]),
            "run_ledger_total_runs": run_ledger["counts"]["runs"],
            "run_ledger_successful_runs": run_ledger["counts"]["successful_runs"],
            "latest_successful_run": (run_ledger["latest_successful_run"] or {}).get("name"),
        }
    )
    _write_json(output_dir / "summary.json", summary)

    regression_comparison = compare_run_regression(
        output_dir,
        run_ledger,
        stage=f"{stage_prefix}_regression_comparison",
    )
    if not require_regression_baseline and regression_comparison.get("baseline_run") is None:
        regression_comparison = _skip_missing_regression_baseline(regression_comparison)
    _write_json(output_dir / "10_regression_comparison.json", regression_comparison)
    summary.update(
        {
            "regression_comparison_ok": bool(regression_comparison["ok"]),
            "regression_baseline_run": regression_comparison.get("baseline_run"),
            "regression_failed_checks": regression_comparison["counts"]["failed_checks"],
        }
    )
    _write_json(output_dir / "summary.json", summary)

    triage_reports = {
        "sketch_runtime_preflight": preflight["report"],
        "operation_invariants": invariant_report,
        "diagnostic_bundle": diagnostic_bundle,
        "operation_contract": operation_contract_report,
        "run_ledger": run_ledger,
        "regression_comparison": regression_comparison,
    }
    if geometry_probe_report is not None:
        triage_reports["thread_geometry_probes"] = geometry_probe_report
    if document_readback_report is not None:
        triage_reports["com_document_readback"] = document_readback_report
    if document_readback_contract_report is not None:
        triage_reports["com_readback_contract"] = document_readback_contract_report
    if document_readback_manifest is not None:
        triage_reports["com_readback_manifest"] = document_readback_manifest
    failure_triage = build_failure_triage(triage_reports, stage=f"{stage_prefix}_failure_triage")
    _write_json(output_dir / "11_failure_triage.json", failure_triage)
    summary.update(
        {
            "failure_triage_ok": bool(failure_triage["ok"]),
            "failure_triage_items": failure_triage["counts"]["items"],
            "failure_triage_critical": failure_triage["counts"]["critical"],
            "failure_triage_high": failure_triage["counts"]["high"],
            "failure_triage_medium": failure_triage["counts"]["medium"],
            "reproducibility_snapshot": "12_reproducibility_snapshot.json",
        }
    )
    _write_json(output_dir / "summary.json", summary)

    reproducibility_snapshot = build_reproducibility_snapshot(
        output_dir,
        required_files=_snapshot_required_files(include_document_readback=document_readback_report is not None),
        stage=f"{stage_prefix}_reproducibility_snapshot",
    )
    _write_json(output_dir / "12_reproducibility_snapshot.json", reproducibility_snapshot)

    audit_report = build_human_audit_report(output_dir, stage=f"{stage_prefix}_human_audit_report")
    (output_dir / "13_audit_report.md").write_text(audit_report["markdown"] + "\n", encoding="utf-8")
    (output_dir / "README.txt").write_text(
        _render_readme(summary, reproducibility_snapshot, audit_report, output_path.name),
        encoding="utf-8",
    )
    _finish_transaction_phase(
        output_dir,
        transaction,
        "finalize",
        ok=bool(summary["ok"])
        and bool(run_ledger["ok"])
        and bool(regression_comparison["ok"])
        and bool(failure_triage["ok"])
        and (not require_document_readback or bool(document_readback_report and document_readback_report["ok"]))
        and (document_readback_contract_report is None or document_readback_contract_report.ok)
        and (document_readback_manifest is None or bool(document_readback_manifest["ok"]))
        and bool(reproducibility_snapshot["ok"])
        and bool(audit_report["ok"]),
        details={
            "run_ledger_ok": bool(run_ledger["ok"]),
            "regression_comparison_ok": bool(regression_comparison["ok"]),
            "failure_triage_ok": bool(failure_triage["ok"]),
            "document_readback_ok": None if document_readback_report is None else bool(document_readback_report["ok"]),
            "document_readback_contract_ok": None
            if document_readback_contract_report is None
            else document_readback_contract_report.ok,
            "document_readback_manifest_ok": None
            if document_readback_manifest is None
            else bool(document_readback_manifest["ok"]),
            "reproducibility_snapshot_ok": bool(reproducibility_snapshot["ok"]),
            "audit_report_ok": bool(audit_report["ok"]),
        },
    )

    return {
        "ok": bool(summary["ok"])
        and bool(run_ledger["ok"])
        and bool(regression_comparison["ok"])
        and bool(failure_triage["ok"])
        and (not require_document_readback or bool(document_readback_report and document_readback_report["ok"]))
        and (document_readback_contract_report is None or document_readback_contract_report.ok)
        and (document_readback_manifest is None or bool(document_readback_manifest["ok"]))
        and bool(reproducibility_snapshot["ok"])
        and bool(audit_report["ok"]),
        "output_dir": str(output_dir),
        "output_path": str(output_path),
        "summary": summary,
        "run_ledger": run_ledger,
        "regression_comparison": regression_comparison,
        "failure_triage": failure_triage,
        "document_readback": document_readback_report,
        "document_readback_contract": None
        if document_readback_contract_report is None
        else document_readback_contract_report.to_dict(),
        "document_readback_manifest": document_readback_manifest,
        "reproducibility_snapshot": reproducibility_snapshot,
        "audit_report": audit_report,
    }


def _next_output_dir(base: Path) -> Path:
    if not base.exists():
        return base
    for index in range(2, 1000):
        candidate = base.with_name(f"{base.name}_{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to find free output directory near {base}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _snapshot_required_files(*, include_document_readback: bool) -> tuple[str, ...]:
    files = (
        "01_sketch_runtime_preflight.json",
        "02_kompas_task_payload.json",
        "03_kompas_create_result.json",
        "04_operation_invariants.json",
        "05_operation_manifest.json",
        "06_thread_geometry_probes.json",
        "07_diagnostic_bundle.json",
        "08_operation_contract.json",
        "09_run_ledger.json",
        "10_regression_comparison.json",
        "11_failure_triage.json",
        "summary.json",
    )
    if include_document_readback:
        return files + (
            "14_com_document_readback.json",
            "15_com_readback_contract.json",
            "16_com_readback_manifest.json",
        )
    return files


def _new_transaction(*, stage_prefix: str, scenario: str, output_dir: Path) -> dict[str, Any]:
    return {
        "stage": f"{stage_prefix}_transaction",
        "ok": None,
        "scenario": scenario,
        "output_dir": str(output_dir),
        "started_at_unix": time.time(),
        "finished_at_unix": None,
        "phases": [
            {"name": "prepare", "ok": None, "started": True, "finished": False, "details": {}},
            {"name": "create", "ok": None, "started": False, "finished": False, "details": {}},
            {"name": "verify", "ok": None, "started": False, "finished": False, "details": {}},
            {"name": "finalize", "ok": None, "started": False, "finished": False, "details": {}},
        ],
    }


def _finish_transaction_phase(
    output_dir: Path,
    transaction: dict[str, Any],
    phase_name: str,
    *,
    ok: bool,
    details: dict[str, Any] | None = None,
) -> None:
    phases = transaction["phases"]
    phase_index = next(index for index, phase in enumerate(phases) if phase["name"] == phase_name)
    for earlier in phases[: phase_index + 1]:
        earlier["started"] = True
    phase = phases[phase_index]
    phase["ok"] = bool(ok)
    phase["finished"] = True
    if details:
        phase["details"] = details
    if not ok:
        transaction["ok"] = False
        transaction["finished_at_unix"] = time.time()
    elif phase_name == "finalize":
        transaction["ok"] = True
        transaction["finished_at_unix"] = time.time()
    elif phase_index + 1 < len(phases):
        phases[phase_index + 1]["started"] = True
    _write_transaction(output_dir, transaction)


def _write_transaction(output_dir: Path, transaction: dict[str, Any]) -> None:
    _write_json(output_dir / "00_transaction.json", transaction)


def _build_exception_payload(exc: Exception, *, stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "ok": False,
        "error_type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    }


def _normalize_preflight_payload(preflight: Any) -> dict[str, Any]:
    if not isinstance(preflight, dict):
        return {
            "report": _build_malformed_payload(
                stage="sketch_runtime_preflight",
                source="preflight",
                value=preflight,
            )
        }
    normalized = dict(preflight)
    report = normalized.get("report")
    if not isinstance(report, dict):
        normalized["report"] = _build_malformed_payload(
            stage="sketch_runtime_preflight",
            source="preflight.report",
            value=report,
        )
    return normalized


def _build_malformed_payload(*, stage: str, source: str, value: Any) -> dict[str, Any]:
    return {
        "stage": stage,
        "ok": False,
        "error_type": "MalformedPayload",
        "message": f"{source} returned {type(value).__name__}; expected object.",
        "checks": [
            {
                "name": f"{source}_payload_object",
                "ok": False,
                "expected": "object",
                "actual": type(value).__name__,
            }
        ],
    }


def _skip_missing_regression_baseline(comparison: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for check in comparison.get("checks", []):
        if isinstance(check, dict) and check.get("name") == "baseline_available":
            patched = dict(check)
            patched["ok"] = True
            patched["actual"] = "skipped:no_prior_successful_run"
            patched["details"] = {"reason": "No earlier successful run is available yet."}
            checks.append(patched)
        else:
            checks.append(check)
    failures = [check for check in checks if isinstance(check, dict) and not check.get("ok")]
    patched_comparison = dict(comparison)
    patched_comparison.update(
        {
            "ok": not failures,
            "skipped": True,
            "skip_reason": "No earlier successful run is available yet.",
            "checks": checks,
            "counts": {
                **dict(comparison.get("counts") or {}),
                "failed_checks": len(failures),
            },
            "failures": failures,
        }
    )
    return patched_comparison


def _build_initial_summary(
    *,
    payload: dict[str, Any],
    preflight: dict[str, Any],
    result: dict[str, Any],
    output_path: Path,
    invariant_report: OperationInvariantReport,
    operation_manifest: dict[str, Any],
    geometry_probe_report: OperationInvariantReport | None,
    diagnostic_bundle: dict[str, Any],
    operation_contract_report: OperationInvariantReport,
    document_readback_report: dict[str, Any] | None,
    document_readback_contract_report: OperationInvariantReport | None,
    document_readback_manifest: dict[str, Any] | None,
    require_document_readback: bool,
    created_elements: tuple[str, ...],
) -> dict[str, Any]:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    hide_step = next(
        (
            step
            for step in result.get("steps", [])
            if isinstance(step, dict) and step.get("step") == "hide_helical_thread_auxiliary_geometry"
        ),
        {},
    )
    hidden_objects = list(hide_step.get("objects") or [])
    document_readback_ok = None if document_readback_report is None else bool(document_readback_report.get("ok"))
    document_readback_contract_ok = None if document_readback_contract_report is None else document_readback_contract_report.ok
    document_readback_manifest_ok = None if document_readback_manifest is None else bool(document_readback_manifest.get("ok"))
    readback_ok_for_summary = not require_document_readback or bool(document_readback_report and document_readback_report.get("ok"))
    readback_contract_ok_for_summary = document_readback_contract_report is None or document_readback_contract_report.ok
    readback_manifest_ok_for_summary = document_readback_manifest is None or bool(document_readback_manifest.get("ok"))
    return {
        "ok": bool(diagnostic_bundle["ok"])
        and readback_ok_for_summary
        and readback_contract_ok_for_summary
        and readback_manifest_ok_for_summary,
        "preflight_ok": bool(preflight["report"]["ok"]),
        "operation_invariants_ok": invariant_report.ok,
        "operation_manifest_ok": bool(operation_manifest["ok"]),
        "thread_geometry_probes_ok": None if geometry_probe_report is None else geometry_probe_report.ok,
        "diagnostics_ok": bool(diagnostic_bundle["ok"]),
        "operation_contract_ok": operation_contract_report.ok,
        "document_readback_ok": document_readback_ok,
        "document_readback_contract_ok": document_readback_contract_ok,
        "document_readback_manifest_ok": document_readback_manifest_ok,
        "document_readback_required": require_document_readback,
        "document_readback_item_count": None
        if document_readback_report is None
        else int((document_readback_report.get("counts") or {}).get("items") or 0),
        "document_readback_tree_nodes": None
        if document_readback_report is None
        else int((document_readback_report.get("counts") or {}).get("tree_nodes") or 0),
        "diagnostic_failed_checks": diagnostic_bundle["counts"]["failed_checks"],
        "operation_contract_failed_checks": sum(1 for check in operation_contract_report.checks if not check.ok),
        "document_readback_contract_failed_checks": None
        if document_readback_contract_report is None
        else sum(1 for check in document_readback_contract_report.checks if not check.ok),
        "document_readback_manifest_item_types": None
        if document_readback_manifest is None
        else int((document_readback_manifest.get("counts") or {}).get("item_types") or 0),
        "kompas_ok": bool(result.get("ok")),
        "saved": bool(result.get("saved")),
        "geometry_probe_count": 0 if geometry_probe_report is None else len(geometry_probe_report.checks),
        "operation_count": operation_manifest["counts"]["operations"],
        "variable_count": operation_manifest["counts"]["variables"],
        "auxiliary_geometry_hidden_requested": bool(params.get("auxiliary_geometry_hidden")),
        "auxiliary_visibility_ok": bool(hide_step.get("ok")) if hide_step else None,
        "auxiliary_hidden_count": sum(1 for item in hidden_objects if isinstance(item, dict) and item.get("ok")),
        "auxiliary_hidden_roles": [
            str(item.get("role") or "")
            for item in hidden_objects
            if isinstance(item, dict) and item.get("ok")
        ],
        "output_path": str(output_path),
        "output_exists": output_path.exists(),
        "output_size_bytes": output_path.stat().st_size if output_path.exists() else 0,
        "scenario": payload.get("scenario"),
        "designation": params.get("designation"),
        "created_elements": list(created_elements),
    }


def _render_readme(
    summary: dict[str, Any],
    reproducibility_snapshot: dict[str, Any],
    audit_report: dict[str, Any],
    output_name: str,
) -> str:
    lines = [
        "Verified KOMPAS task created after sketch_runtime preflight.",
        f"Output: {output_name}",
        f"Scenario: {summary.get('scenario')}",
        f"Designation: {summary.get('designation')}",
        f"Preflight OK: {summary.get('preflight_ok')}",
        f"KOMPAS saved: {summary.get('saved')}",
        f"Auxiliary visibility OK: {summary.get('auxiliary_visibility_ok')}",
        f"Auxiliary hidden count: {summary.get('auxiliary_hidden_count')}",
        f"Regression comparison OK: {summary.get('regression_comparison_ok')}",
        f"Failure triage items: {summary.get('failure_triage_items')}",
        f"COM document readback OK: {summary.get('document_readback_ok')}",
        f"COM readback manifest OK: {summary.get('document_readback_manifest_ok')}",
        f"Reproducibility snapshot OK: {reproducibility_snapshot.get('ok')}",
        f"Reproducibility fingerprint: {reproducibility_snapshot.get('fingerprint')}",
        f"Human audit report OK: {audit_report.get('ok')}",
        f"File size: {summary.get('output_size_bytes')} bytes",
    ]
    return "\n".join(lines) + "\n"
