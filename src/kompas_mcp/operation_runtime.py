from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .document_readback import build_document_readback_manifest, find_document_items


_AUXILIARY_HIDE_STEP = "hide_helical_thread_auxiliary_geometry"
_DEFAULT_REPRODUCIBILITY_FILES = (
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


@dataclass(frozen=True)
class OperationInvariantSpec:
    scenario: str
    output_path: str | None = None
    min_output_size_bytes: int = 1
    required_steps: tuple[str, ...] = ()
    require_auxiliary_hidden: bool | None = None
    expected_auxiliary_roles: tuple[str, ...] = ()
    expected_operation_values: dict[str, dict[str, Any]] = field(default_factory=dict)
    tolerance: float = 1e-6


@dataclass(frozen=True)
class ThreadGeometryProbeSpec:
    diameter: float
    pitch: float
    length: float
    direction: str = "right"
    depth: float | None = None
    profile_angle_degrees: float = 60.0
    spiral_overrun_pitch_factor: float = 1.05
    min_source_total_length: float | None = None
    tolerance: float = 1e-6


@dataclass(frozen=True)
class OperationContractSpec:
    scenario: str
    required_sections: tuple[str, ...] = ()
    required_artifact_roles: tuple[str, ...] = ()
    min_counts: dict[str, int] = field(default_factory=dict)
    expected_operation_names: tuple[str, ...] = ()
    expected_variable_names: tuple[str, ...] = ()
    expected_auxiliary_roles: tuple[str, ...] = ()
    require_auxiliary_hidden: bool = True


@dataclass(frozen=True)
class DocumentReadbackContractSpec:
    min_documents: int = 1
    min_items: int = 1
    min_tree_nodes: int = 1
    require_open_document: bool = True
    require_path_match: bool = True
    require_close_document: bool = True
    expected_items: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    forbidden_items: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OperationRegressionSpec:
    summary_fields: tuple[str, ...] = (
        "scenario",
        "designation",
        "diagnostics_ok",
        "operation_contract_ok",
        "thread_geometry_probes_ok",
    )
    count_fields: tuple[str, ...] = (
        "geometry_probe_count",
        "operation_count",
        "variable_count",
        "auxiliary_hidden_count",
    )
    manifest_count_fields: tuple[str, ...] = (
        "steps",
        "operations",
        "variables",
        "auxiliary_objects",
        "hidden_auxiliary_objects",
    )
    model_size_tolerance_ratio: float = 0.20


@dataclass(frozen=True)
class OperationCheck:
    name: str
    ok: bool
    expected: Any = None
    actual: Any = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "ok": self.ok,
            "expected": self.expected,
            "actual": self.actual,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True)
class OperationInvariantReport:
    stage: str
    ok: bool
    checks: tuple[OperationCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "checks": [check.to_dict() for check in self.checks],
        }


def verify_operation_result(
    result: dict[str, Any],
    spec: OperationInvariantSpec,
    *,
    stage: str = "operation_postcheck",
) -> OperationInvariantReport:
    checks: list[OperationCheck] = []

    checks.append(OperationCheck("result_ok", bool(result.get("ok")), True, bool(result.get("ok"))))
    checks.append(OperationCheck("saved", bool(result.get("saved")), True, bool(result.get("saved"))))

    if spec.output_path:
        output = Path(spec.output_path)
        size = output.stat().st_size if output.exists() else 0
        checks.append(OperationCheck("output_exists", output.exists(), True, output.exists(), {"path": str(output)}))
        checks.append(
            OperationCheck(
                "output_size",
                size >= spec.min_output_size_bytes,
                {">=": spec.min_output_size_bytes},
                size,
                {"path": str(output)},
            )
        )

    steps = [step for step in result.get("steps", []) if isinstance(step, dict)]
    step_by_name = {str(step.get("step") or ""): step for step in steps}
    for step_name in spec.required_steps:
        step = step_by_name.get(step_name)
        checks.append(
            OperationCheck(
                f"step:{step_name}",
                bool(step and step.get("ok")),
                True,
                bool(step and step.get("ok")),
                {"present": step is not None},
            )
        )

    failed_steps = [str(step.get("step") or "") for step in steps if step.get("ok") is False]
    checks.append(OperationCheck("no_failed_steps", not failed_steps, [], failed_steps))

    if spec.require_auxiliary_hidden is not None:
        checks.extend(_verify_auxiliary_visibility(step_by_name, spec))

    if spec.expected_operation_values:
        checks.extend(_verify_preview_operation_values(result, spec))

    return OperationInvariantReport(stage=stage, ok=all(check.ok for check in checks), checks=tuple(checks))


def build_operation_manifest(
    result: dict[str, Any],
    *,
    stage: str = "operation_manifest",
) -> dict[str, Any]:
    steps = [step for step in result.get("steps", []) if isinstance(step, dict)]
    failed_steps = [str(step.get("step") or "") for step in steps if step.get("ok") is False]
    variables = _collect_variables(steps)
    operations = _collect_preview_operations(result)
    auxiliary_objects = _collect_auxiliary_objects(steps)

    return {
        "stage": stage,
        "ok": bool(result.get("ok")) and not failed_steps,
        "scenario": result.get("scenario"),
        "output_path": result.get("output_path"),
        "saved": bool(result.get("saved")),
        "counts": {
            "steps": len(steps),
            "failed_steps": len(failed_steps),
            "variables": len(variables),
            "operations": len(operations),
            "auxiliary_objects": len(auxiliary_objects),
            "hidden_auxiliary_objects": sum(1 for item in auxiliary_objects if item.get("hidden_after") is True),
        },
        "failed_steps": failed_steps,
        "steps": [
            {
                key: step.get(key)
                for key in ("step", "ok", "api", "hidden", "applied_count", "failed_count")
                if key in step
            }
            for step in steps
        ],
        "variables": variables,
        "operations": operations,
        "auxiliary_objects": auxiliary_objects,
        "documents": result.get("remaining_documents") or [],
        "file_access": result.get("file_access"),
    }


def build_diagnostic_bundle(
    *,
    scenario: str,
    reports: dict[str, OperationInvariantReport | dict[str, Any]],
    artifacts: dict[str, str] | None = None,
    manifest: dict[str, Any] | None = None,
    stage: str = "operation_diagnostics",
) -> dict[str, Any]:
    sections = []
    failures = []

    for name, report in reports.items():
        section = _diagnostic_section(name, report)
        sections.append(section)
        for failed in section["failed_checks"]:
            failures.append(
                {
                    "section": name,
                    "check": failed.get("name"),
                    "expected": failed.get("expected"),
                    "actual": failed.get("actual"),
                }
            )

    artifact_rows = []
    for role, path_text in (artifacts or {}).items():
        path = Path(path_text)
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        artifact_rows.append(
            {
                "role": role,
                "path": str(path),
                "exists": exists,
                "size_bytes": size,
            }
        )
        if not exists:
            failures.append({"section": "artifacts", "check": f"{role}.exists", "expected": True, "actual": False})

    section_ok = all(section["ok"] for section in sections)
    artifacts_ok = all(item["exists"] and item["size_bytes"] > 0 for item in artifact_rows)
    manifest_ok = True if manifest is None else bool(manifest.get("ok"))
    if not manifest_ok:
        failures.append({"section": "manifest", "check": "manifest.ok", "expected": True, "actual": manifest.get("ok") if manifest else None})

    counts = {
        "sections": len(sections),
        "failed_checks": len(failures),
        "artifacts": len(artifact_rows),
    }
    if manifest:
        counts["steps"] = (manifest.get("counts") or {}).get("steps")
        counts["operations"] = (manifest.get("counts") or {}).get("operations")
        counts["variables"] = (manifest.get("counts") or {}).get("variables")
        counts["auxiliary_objects"] = (manifest.get("counts") or {}).get("auxiliary_objects")

    return {
        "stage": stage,
        "ok": section_ok and artifacts_ok and manifest_ok,
        "scenario": scenario,
        "counts": counts,
        "sections": sections,
        "artifacts": artifact_rows,
        "failures": failures,
    }


def verify_operation_contract(
    diagnostic_bundle: dict[str, Any],
    manifest: dict[str, Any],
    spec: OperationContractSpec,
    *,
    stage: str = "operation_contract",
) -> OperationInvariantReport:
    checks: list[OperationCheck] = []

    checks.append(OperationCheck("diagnostics_ok", bool(diagnostic_bundle.get("ok")), True, bool(diagnostic_bundle.get("ok"))))
    checks.append(OperationCheck("manifest_ok", bool(manifest.get("ok")), True, bool(manifest.get("ok"))))
    checks.append(OperationCheck("scenario", diagnostic_bundle.get("scenario") == spec.scenario, spec.scenario, diagnostic_bundle.get("scenario")))

    sections = {str(item.get("name") or ""): item for item in diagnostic_bundle.get("sections", []) if isinstance(item, dict)}
    for section_name in spec.required_sections:
        section = sections.get(section_name)
        checks.append(
            OperationCheck(
                f"section:{section_name}",
                bool(section and section.get("ok")),
                True,
                bool(section and section.get("ok")),
                {"present": section is not None},
            )
        )

    artifacts = {str(item.get("role") or ""): item for item in diagnostic_bundle.get("artifacts", []) if isinstance(item, dict)}
    for role in spec.required_artifact_roles:
        artifact = artifacts.get(role)
        checks.append(
            OperationCheck(
                f"artifact:{role}",
                bool(artifact and artifact.get("exists") and artifact.get("size_bytes", 0) > 0),
                True,
                bool(artifact and artifact.get("exists") and artifact.get("size_bytes", 0) > 0),
                {"present": artifact is not None},
            )
        )

    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    for name, minimum in spec.min_counts.items():
        actual = counts.get(name)
        checks.append(
            OperationCheck(
                f"count:{name}",
                isinstance(actual, int) and actual >= minimum,
                {">=": minimum},
                actual,
            )
        )

    operation_names = _manifest_names(manifest, "operations", "operation")
    for name in spec.expected_operation_names:
        checks.append(OperationCheck(f"operation:{name}", name in operation_names, True, name in operation_names))

    variable_names = _manifest_names(manifest, "variables", "name")
    for name in spec.expected_variable_names:
        checks.append(OperationCheck(f"variable:{name}", name in variable_names, True, name in variable_names))

    auxiliary_objects = [item for item in manifest.get("auxiliary_objects", []) if isinstance(item, dict)]
    auxiliary_roles = tuple(str(item.get("role") or "") for item in auxiliary_objects)
    for role in spec.expected_auxiliary_roles:
        checks.append(OperationCheck(f"auxiliary:{role}", role in auxiliary_roles, True, role in auxiliary_roles))

    if spec.require_auxiliary_hidden and spec.expected_auxiliary_roles:
        visible_roles = [
            str(item.get("role") or "")
            for item in auxiliary_objects
            if item.get("role") in spec.expected_auxiliary_roles and item.get("visible_after") is not False
        ]
        checks.append(OperationCheck("auxiliary_contract_hidden", not visible_roles, [], visible_roles))

    return OperationInvariantReport(stage=stage, ok=all(check.ok for check in checks), checks=tuple(checks))


def verify_document_readback_contract(
    readback_report: dict[str, Any] | None,
    spec: DocumentReadbackContractSpec,
    *,
    stage: str = "com_readback_contract",
) -> OperationInvariantReport:
    report = readback_report or {}
    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    check_by_name = {
        str(check.get("name")): check
        for check in report.get("checks", [])
        if isinstance(check, dict) and check.get("name")
    }
    checks = [
        OperationCheck("readback_report_present", bool(readback_report), True, bool(readback_report)),
        OperationCheck("readback_report_ok", bool(report.get("ok")), True, bool(report.get("ok"))),
        OperationCheck(
            "minimum_documents",
            int(counts.get("documents") or 0) >= spec.min_documents,
            {">=": spec.min_documents},
            int(counts.get("documents") or 0),
        ),
        OperationCheck(
            "minimum_items",
            int(counts.get("items") or 0) >= spec.min_items,
            {">=": spec.min_items},
            int(counts.get("items") or 0),
        ),
        OperationCheck(
            "minimum_tree_nodes",
            int(counts.get("tree_nodes") or 0) >= spec.min_tree_nodes,
            {">=": spec.min_tree_nodes},
            int(counts.get("tree_nodes") or 0),
        ),
    ]
    if spec.require_open_document:
        open_check = check_by_name.get("open_document", {})
        checks.append(OperationCheck("open_document_check", bool(open_check.get("ok")), True, bool(open_check.get("ok"))))
    if spec.require_path_match:
        path_check = check_by_name.get("document_path_matches_model_name", {})
        checks.append(
            OperationCheck(
                "document_path_matches_model_name_check",
                bool(path_check.get("ok")),
                True,
                bool(path_check.get("ok")),
            )
        )
    if spec.require_close_document:
        close_check = check_by_name.get("close_document", {})
        checks.append(OperationCheck("close_document_check", bool(close_check.get("ok")), True, bool(close_check.get("ok"))))
    if spec.expected_items or spec.forbidden_items:
        manifest = build_document_readback_manifest(report, stage=f"{stage}_item_index")
        item_index = manifest.get("item_index") if isinstance(manifest.get("item_index"), dict) else {}
        if spec.expected_items:
            checks.extend(_verify_expected_readback_items(item_index, spec.expected_items))
        if spec.forbidden_items:
            checks.extend(_verify_forbidden_readback_items(item_index, spec.forbidden_items))
    return OperationInvariantReport(stage=stage, ok=all(check.ok for check in checks), checks=tuple(checks))


def _verify_expected_readback_items(
    item_index: dict[str, Any],
    expected_items: tuple[dict[str, Any], ...],
) -> list[OperationCheck]:
    checks: list[OperationCheck] = []
    for index, expected in enumerate(expected_items):
        if not isinstance(expected, dict):
            checks.append(_invalid_readback_item_spec_check("expected", index, expected, "spec must be an object"))
            continue
        try:
            min_count = int(expected.get("min_count") or 1)
            if min_count < 0:
                raise ValueError("min_count must be non-negative")
            matches = _find_readback_items_for_spec(item_index, expected)
        except (TypeError, ValueError) as exc:
            checks.append(_invalid_readback_item_spec_check("expected", index, expected, str(exc)))
            continue
        label = _readback_item_check_label(expected)
        max_count = expected.get("max_count")
        if expected.get("unique") is True and max_count is None:
            max_count = 1
        criteria = _readback_item_criteria(expected)
        checks.append(
            OperationCheck(
                f"readback_item:{label}",
                len(matches) >= min_count,
                {">=": min_count, "criteria": criteria},
                {"count": len(matches), "matches": _readback_item_match_previews(matches)},
            )
        )
        if max_count is not None:
            try:
                max_count_int = int(max_count)
                if max_count_int < 0:
                    raise ValueError("max_count must be non-negative")
            except (TypeError, ValueError) as exc:
                checks.append(_invalid_readback_item_spec_check("expected", index, expected, str(exc)))
                continue
            checks.append(
                OperationCheck(
                    f"readback_item_max:{label}",
                    len(matches) <= max_count_int,
                    {"<=": max_count_int, "criteria": criteria},
                    {"count": len(matches), "matches": _readback_item_match_previews(matches)},
                )
            )
    return checks


def _verify_forbidden_readback_items(
    item_index: dict[str, Any],
    forbidden_items: tuple[dict[str, Any], ...],
) -> list[OperationCheck]:
    checks: list[OperationCheck] = []
    for index, forbidden in enumerate(forbidden_items):
        if not isinstance(forbidden, dict):
            checks.append(_invalid_readback_item_spec_check("forbidden", index, forbidden, "spec must be an object"))
            continue
        try:
            matches = _find_readback_items_for_spec(item_index, forbidden)
        except (TypeError, ValueError) as exc:
            checks.append(_invalid_readback_item_spec_check("forbidden", index, forbidden, str(exc)))
            continue
        label = _readback_item_check_label(forbidden)
        checks.append(
            OperationCheck(
                f"readback_item_absent:{label}",
                len(matches) == 0,
                {"==": 0, "criteria": _readback_item_criteria(forbidden)},
                {"count": len(matches), "matches": _readback_item_match_previews(matches)},
            )
        )
    return checks


def _invalid_readback_item_spec_check(kind: str, index: int, spec: Any, reason: str) -> OperationCheck:
    return OperationCheck(
        f"readback_item_spec:{kind}:{index}",
        False,
        "valid readback item spec",
        {"reason": reason, "spec_type": type(spec).__name__},
    )


def _readback_item_match_previews(matches: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    preview_keys = (
        "id",
        "name",
        "type",
        "role",
        "reference",
        "path",
        "source",
        "parent_id",
        "parent_path",
        "depth",
        "children_count",
        "hidden",
        "visible",
        "active",
        "changed",
    )
    previews: list[dict[str, Any]] = []
    for item in matches[:limit]:
        if not isinstance(item, dict):
            continue
        preview = {key: item[key] for key in preview_keys if key in item}
        extra_keys = sorted(
            key
            for key in item
            if key not in preview_keys and key not in {"children", "raw", "payload", "source_index"}
        )
        if extra_keys:
            preview["extra_keys"] = extra_keys[:8]
        previews.append(preview)
    return previews


def _find_readback_items_for_spec(item_index: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    _validate_readback_item_spec(spec)
    item_type = spec.get("item_type", spec.get("type"))
    return find_document_items(
        item_index,
        item_id=spec.get("id"),
        name=spec.get("name"),
        item_type=item_type,
        role=spec.get("role"),
        reference=spec.get("reference"),
        path=spec.get("path"),
        parent_id=spec.get("parent_id"),
        parent_path=spec.get("parent_path"),
        source=spec.get("source"),
        hidden=spec.get("hidden"),
        visible=spec.get("visible"),
        active=spec.get("active"),
        changed=spec.get("changed"),
        depth=spec.get("depth"),
        children_count=spec.get("children_count"),
        item_id_contains=spec.get("id_contains"),
        name_contains=spec.get("name_contains"),
        item_type_contains=spec.get("type_contains") or spec.get("item_type_contains"),
        role_contains=spec.get("role_contains"),
        reference_contains=spec.get("reference_contains"),
        path_contains=spec.get("path_contains"),
        parent_id_contains=spec.get("parent_id_contains"),
        parent_path_contains=spec.get("parent_path_contains"),
        source_contains=spec.get("source_contains"),
        field_equals=spec.get("field_equals"),
        field_contains=spec.get("field_contains"),
        field_has=spec.get("field_has"),
        field_has_contains=spec.get("field_has_contains"),
        field_exists=spec.get("field_exists"),
        field_missing=spec.get("field_missing"),
        numeric_fields=spec.get("numeric_fields"),
        numeric_tolerance=float(spec.get("numeric_tolerance") or 0.0),
    )


def _validate_readback_item_spec(spec: dict[str, Any]) -> None:
    for key in ("field_equals", "field_contains", "field_has", "field_has_contains", "numeric_fields"):
        value = spec.get(key)
        if value is not None and not isinstance(value, dict):
            raise ValueError(f"{key} must be an object")
    for key in ("field_exists", "field_missing"):
        value = spec.get(key)
        if isinstance(value, dict):
            raise ValueError(f"{key} must be a path or list of paths")
    tolerance = spec.get("numeric_tolerance")
    if tolerance is not None:
        try:
            numeric_tolerance = float(tolerance)
        except (TypeError, ValueError) as exc:
            raise ValueError("numeric_tolerance must be numeric") from exc
        if numeric_tolerance < 0:
            raise ValueError("numeric_tolerance must be non-negative")
    numeric_fields = spec.get("numeric_fields")
    if isinstance(numeric_fields, dict):
        for field_path, expected in numeric_fields.items():
            if field_path in (None, ""):
                raise ValueError("numeric_fields paths must be non-empty")
            if isinstance(expected, dict) and "tolerance" in expected:
                try:
                    field_tolerance = float(expected["tolerance"])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"numeric_fields.{field_path}.tolerance must be numeric") from exc
                if field_tolerance < 0:
                    raise ValueError(f"numeric_fields.{field_path}.tolerance must be non-negative")


def verify_thread_geometry_probes(
    result: dict[str, Any],
    spec: ThreadGeometryProbeSpec,
    *,
    stage: str = "thread_geometry_probes",
) -> OperationInvariantReport:
    operations = [
        item
        for item in ((result.get("preview") or {}).get("operations") or [])
        if isinstance(item, dict)
    ]
    by_name = {str(item.get("operation") or ""): item for item in operations}
    checks: list[OperationCheck] = []

    spiral = by_name.get("create_spiral_path")
    profile = by_name.get("create_thread_profile")
    cut = by_name.get("cut_evolution")
    source = by_name.get("create_source_body")

    for name, operation in (
        ("create_spiral_path", spiral),
        ("create_thread_profile", profile),
        ("cut_evolution", cut),
    ):
        checks.append(OperationCheck(f"probe_operation:{name}", operation is not None, True, operation is not None))

    if spiral:
        checks.extend(
            [
                _numeric_check("spiral.diameter", spiral.get("diameter"), spec.diameter, spec.tolerance),
                _numeric_check("spiral.pitch", spiral.get("pitch"), spec.pitch, spec.tolerance),
                _numeric_check("spiral.length", spiral.get("length"), spec.length, spec.tolerance),
                _numeric_check(
                    "spiral.spiral_length",
                    spiral.get("spiral_length"),
                    spec.length + spec.spiral_overrun_pitch_factor * spec.pitch,
                    spec.tolerance,
                ),
                OperationCheck("spiral.direction", spiral.get("direction") == spec.direction, spec.direction, spiral.get("direction")),
            ]
        )
        checks.append(_source_validation_check("spiral.source_diameter_validation", spiral))

    if profile:
        expected_depth = spec.depth
        checks.extend(
            [
                _numeric_check("profile.major_radius", profile.get("major_radius"), spec.diameter / 2.0, spec.tolerance),
                _numeric_check("profile.angle", profile.get("profile_angle_degrees"), spec.profile_angle_degrees, spec.tolerance),
                _numeric_check("profile.pitch_width", profile.get("profile_outer_half_width"), spec.pitch * 0.4375, spec.tolerance),
            ]
        )
        if expected_depth is not None:
            checks.extend(
                [
                    _numeric_check("profile.depth", profile.get("depth"), expected_depth, spec.tolerance),
                    _numeric_check("profile.root_diameter", profile.get("root_diameter"), spec.diameter - 2.0 * expected_depth, spec.tolerance),
                ]
            )

    if cut:
        checks.extend(
            [
                _numeric_check("cut.diameter", cut.get("diameter"), spec.diameter, spec.tolerance),
                _numeric_check("cut.pitch", cut.get("pitch"), spec.pitch, spec.tolerance),
                _numeric_check("cut.length", cut.get("length"), spec.length, spec.tolerance),
                _numeric_check(
                    "cut.spiral_length",
                    cut.get("spiral_length"),
                    spec.length + spec.spiral_overrun_pitch_factor * spec.pitch,
                    spec.tolerance,
                ),
                OperationCheck("cut.direction", cut.get("direction") == spec.direction, spec.direction, cut.get("direction")),
                OperationCheck("cut.external_thread", cut.get("internal") is False, False, cut.get("internal")),
                _source_validation_check("cut.source_diameter_validation", cut),
            ]
        )
        if spec.depth is not None:
            checks.append(_numeric_check("cut.depth", cut.get("depth"), spec.depth, spec.tolerance))

    if source:
        validation = source.get("source_diameter_validation") if isinstance(source.get("source_diameter_validation"), dict) else {}
        checks.append(
            OperationCheck(
                "source.diameter_validation",
                validation.get("matches") is True,
                True,
                validation.get("matches"),
                {"status": validation.get("status"), "delta": validation.get("delta")},
            )
        )
        summary = source.get("summary") if isinstance(source.get("summary"), dict) else {}
        if spec.min_source_total_length is not None:
            actual_total = summary.get("total_length")
            checks.append(
                OperationCheck(
                    "source.total_length_min",
                    isinstance(actual_total, (int, float)) and float(actual_total) >= spec.min_source_total_length,
                    {">=": spec.min_source_total_length},
                    actual_total,
                )
            )

    return OperationInvariantReport(stage=stage, ok=all(check.ok for check in checks), checks=tuple(checks))


def build_run_ledger(
    generated_dir: str | Path,
    *,
    run_prefix: str,
    stage: str = "operation_run_ledger",
) -> dict[str, Any]:
    root = Path(generated_dir)
    runs = []
    for run_dir in sorted((item for item in root.iterdir() if item.is_dir() and _is_prefixed_run_dir(item.name, run_prefix)), key=lambda item: _run_sort_key(item.name, run_prefix)):
        summary = _read_json_dict(run_dir / "summary.json")
        diagnostics = _read_json_dict(run_dir / "07_diagnostic_bundle.json")
        contract = _read_json_dict(run_dir / "08_operation_contract.json")
        output_path = Path(str(summary.get("output_path") or "")) if summary.get("output_path") else None
        output_exists = output_path.exists() if output_path else False
        output_size = output_path.stat().st_size if output_path and output_exists else 0
        run_ok = bool(summary.get("ok")) and bool(diagnostics.get("ok", True)) and bool(contract.get("ok", True)) and output_exists and output_size > 0
        runs.append(
            {
                "name": run_dir.name,
                "path": str(run_dir),
                "ok": run_ok,
                "scenario": summary.get("scenario"),
                "designation": summary.get("designation"),
                "model_path": str(output_path) if output_path else None,
                "model_exists": output_exists,
                "model_size_bytes": output_size,
                "diagnostics_ok": diagnostics.get("ok"),
                "operation_contract_ok": contract.get("ok"),
                "diagnostic_failed_checks": summary.get("diagnostic_failed_checks"),
                "operation_contract_failed_checks": summary.get("operation_contract_failed_checks"),
                "geometry_probe_count": summary.get("geometry_probe_count"),
                "auxiliary_hidden_count": summary.get("auxiliary_hidden_count"),
            }
        )

    successful = [run for run in runs if run["ok"]]
    latest = runs[-1] if runs else None
    latest_successful = successful[-1] if successful else None
    return {
        "stage": stage,
        "ok": latest_successful is not None,
        "run_prefix": run_prefix,
        "root": str(root),
        "counts": {
            "runs": len(runs),
            "successful_runs": len(successful),
            "failed_runs": len(runs) - len(successful),
        },
        "latest_run": latest,
        "latest_successful_run": latest_successful,
        "runs": runs,
    }


def compare_run_regression(
    current_run_dir: str | Path,
    run_ledger: dict[str, Any],
    spec: OperationRegressionSpec | None = None,
    *,
    baseline_run_name: str | None = None,
    stage: str = "operation_regression_comparison",
) -> dict[str, Any]:
    spec = spec or OperationRegressionSpec()
    current_dir = Path(current_run_dir)
    current_name = current_dir.name
    runs = [run for run in run_ledger.get("runs", []) if isinstance(run, dict)]
    baseline = _select_regression_baseline(runs, current_name, baseline_run_name)

    checks: list[OperationCheck] = [
        OperationCheck("baseline_available", baseline is not None, True, baseline is not None)
    ]
    current_summary = _read_json_dict(current_dir / "summary.json")
    current_manifest = _read_json_dict(current_dir / "05_operation_manifest.json")
    checks.append(OperationCheck("current_summary_available", bool(current_summary), True, bool(current_summary)))
    checks.append(OperationCheck("current_manifest_available", bool(current_manifest), True, bool(current_manifest)))

    baseline_summary: dict[str, Any] = {}
    baseline_manifest: dict[str, Any] = {}
    if baseline is not None:
        baseline_dir = Path(str(baseline.get("path") or ""))
        baseline_summary = _read_json_dict(baseline_dir / "summary.json")
        baseline_manifest = _read_json_dict(baseline_dir / "05_operation_manifest.json")
        checks.append(OperationCheck("baseline_summary_available", bool(baseline_summary), True, bool(baseline_summary)))
        checks.append(OperationCheck("baseline_manifest_available", bool(baseline_manifest), True, bool(baseline_manifest)))

    if current_summary and baseline_summary:
        for field_name in spec.summary_fields:
            checks.append(
                OperationCheck(
                    f"summary:{field_name}",
                    current_summary.get(field_name) == baseline_summary.get(field_name),
                    baseline_summary.get(field_name),
                    current_summary.get(field_name),
                )
            )
        for field_name in spec.count_fields:
            checks.append(
                OperationCheck(
                    f"summary_count:{field_name}",
                    current_summary.get(field_name) == baseline_summary.get(field_name),
                    baseline_summary.get(field_name),
                    current_summary.get(field_name),
                )
            )
        checks.append(
            _model_size_regression_check(
                current_summary.get("output_size_bytes"),
                baseline_summary.get("output_size_bytes"),
                spec.model_size_tolerance_ratio,
            )
        )

    if current_manifest and baseline_manifest:
        current_counts = current_manifest.get("counts") if isinstance(current_manifest.get("counts"), dict) else {}
        baseline_counts = baseline_manifest.get("counts") if isinstance(baseline_manifest.get("counts"), dict) else {}
        for field_name in spec.manifest_count_fields:
            checks.append(
                OperationCheck(
                    f"manifest_count:{field_name}",
                    current_counts.get(field_name) == baseline_counts.get(field_name),
                    baseline_counts.get(field_name),
                    current_counts.get(field_name),
                )
            )
        checks.append(
            OperationCheck(
                "manifest_operations",
                _manifest_names(current_manifest, "operations", "operation") == _manifest_names(baseline_manifest, "operations", "operation"),
                list(_manifest_names(baseline_manifest, "operations", "operation")),
                list(_manifest_names(current_manifest, "operations", "operation")),
            )
        )
        checks.append(
            OperationCheck(
                "manifest_auxiliary_roles",
                _manifest_names(current_manifest, "auxiliary_objects", "role") == _manifest_names(baseline_manifest, "auxiliary_objects", "role"),
                list(_manifest_names(baseline_manifest, "auxiliary_objects", "role")),
                list(_manifest_names(current_manifest, "auxiliary_objects", "role")),
            )
        )

    failed = [check for check in checks if not check.ok]
    return {
        "stage": stage,
        "ok": not failed,
        "current_run": current_name,
        "baseline_run": None if baseline is None else baseline.get("name"),
        "checks": [check.to_dict() for check in checks],
        "counts": {
            "checks": len(checks),
            "failed_checks": len(failed),
        },
        "failures": [check.to_dict() for check in failed],
    }


def build_failure_triage(
    reports: dict[str, OperationInvariantReport | dict[str, Any]],
    *,
    stage: str = "operation_failure_triage",
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    for source, report in reports.items():
        payload = report.to_dict() if isinstance(report, OperationInvariantReport) else report
        for failure in _extract_report_failures(payload):
            check_name = str(failure.get("name") or failure.get("check") or "ok")
            category = _failure_category(source, check_name)
            severity = _failure_severity(source, check_name, category)
            items.append(
                {
                    "source": source,
                    "stage": payload.get("stage"),
                    "check": check_name,
                    "category": category,
                    "severity": severity,
                    "expected": failure.get("expected"),
                    "actual": failure.get("actual"),
                    "details": failure.get("details") or {},
                    "action": _failure_action(category),
                }
            )
        if payload.get("ok") is False and not _extract_report_failures(payload):
            category = _failure_category(source, "ok")
            severity = _failure_severity(source, "ok", category)
            items.append(
                {
                    "source": source,
                    "stage": payload.get("stage"),
                    "check": "ok",
                    "category": category,
                    "severity": severity,
                    "expected": True,
                    "actual": False,
                    "details": {},
                    "action": _failure_action(category),
                }
            )

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    items.sort(key=lambda item: (severity_order.get(str(item["severity"]), 99), str(item["source"]), str(item["check"])))
    counts = {
        "items": len(items),
        "critical": sum(1 for item in items if item["severity"] == "critical"),
        "high": sum(1 for item in items if item["severity"] == "high"),
        "medium": sum(1 for item in items if item["severity"] == "medium"),
        "low": sum(1 for item in items if item["severity"] == "low"),
    }
    return {
        "stage": stage,
        "ok": not items,
        "counts": counts,
        "items": items,
        "next_actions": _triage_next_actions(items),
    }


def build_reproducibility_snapshot(
    run_dir: str | Path,
    *,
    required_files: tuple[str, ...] = _DEFAULT_REPRODUCIBILITY_FILES,
    stage: str = "operation_reproducibility_snapshot",
) -> dict[str, Any]:
    run_path = Path(run_dir)
    checks: list[OperationCheck] = [
        OperationCheck("run_dir_exists", run_path.exists(), True, run_path.exists(), {"path": str(run_path)}),
        OperationCheck("run_dir_is_directory", run_path.is_dir(), True, run_path.is_dir(), {"path": str(run_path)}),
    ]
    files: list[dict[str, Any]] = []
    seen: set[Path] = set()

    for relative_name in required_files:
        file_path = run_path / relative_name
        checks.append(OperationCheck(f"file_exists:{relative_name}", file_path.exists(), True, file_path.exists()))
        if file_path.exists() and file_path.is_file():
            files.append(_snapshot_file(run_path, file_path))
            seen.add(file_path.resolve())
            if file_path.suffix.lower() == ".json":
                checks.append(_json_validity_check(run_path, file_path))

    summary = _read_json_dict(run_path / "summary.json")
    output_path_value = summary.get("output_path")
    if output_path_value:
        model_path = Path(str(output_path_value))
        if not model_path.is_absolute():
            model_path = run_path / model_path
        checks.append(OperationCheck("model_artifact_exists", model_path.exists(), True, model_path.exists(), {"path": str(model_path)}))
        if model_path.exists() and model_path.is_file() and model_path.resolve() not in seen:
            files.append(_snapshot_file(run_path, model_path, role="model"))
            seen.add(model_path.resolve())

    for model_path in sorted(run_path.glob("*.m3d")):
        if model_path.resolve() not in seen:
            files.append(_snapshot_file(run_path, model_path, role="model"))
            seen.add(model_path.resolve())

    files.sort(key=lambda item: str(item["path"]))
    failed = [check for check in checks if not check.ok]
    return {
        "stage": stage,
        "ok": not failed,
        "run_dir": str(run_path),
        "schema_version": 1,
        "counts": {
            "files": len(files),
            "required_files": len(required_files),
            "json_files": sum(1 for item in files if item["kind"] == "json"),
            "model_files": sum(1 for item in files if item["role"] == "model"),
            "failed_checks": len(failed),
            "total_bytes": sum(int(item["size_bytes"]) for item in files),
        },
        "fingerprint": _combined_fingerprint(files),
        "files": files,
        "checks": [check.to_dict() for check in checks],
        "failures": [check.to_dict() for check in failed],
    }


def build_human_audit_report(
    run_dir: str | Path,
    *,
    stage: str = "operation_human_audit_report",
) -> dict[str, Any]:
    run_path = Path(run_dir)
    summary = _read_json_dict(run_path / "summary.json")
    diagnostics = _read_json_dict(run_path / "07_diagnostic_bundle.json")
    contract = _read_json_dict(run_path / "08_operation_contract.json")
    ledger = _read_json_dict(run_path / "09_run_ledger.json")
    regression = _read_json_dict(run_path / "10_regression_comparison.json")
    triage = _read_json_dict(run_path / "11_failure_triage.json")
    snapshot = _read_json_dict(run_path / "12_reproducibility_snapshot.json")

    checks = [
        OperationCheck("summary_present", bool(summary), True, bool(summary)),
        OperationCheck("diagnostics_ok", diagnostics.get("ok") is True, True, diagnostics.get("ok")),
        OperationCheck("contract_ok", contract.get("ok") is True, True, contract.get("ok")),
        OperationCheck("ledger_ok", ledger.get("ok") is True, True, ledger.get("ok")),
        OperationCheck("regression_ok", regression.get("ok") is True, True, regression.get("ok")),
        OperationCheck("triage_ok", triage.get("ok") is True, True, triage.get("ok")),
        OperationCheck("snapshot_ok", snapshot.get("ok") is True, True, snapshot.get("ok")),
    ]
    failed = [check for check in checks if not check.ok]
    triage_items = [item for item in triage.get("items", []) if isinstance(item, dict)]
    markdown = _render_human_audit_markdown(
        run_path,
        summary,
        diagnostics,
        contract,
        ledger,
        regression,
        triage,
        snapshot,
        failed,
    )
    return {
        "stage": stage,
        "ok": not failed and not triage_items,
        "run_dir": str(run_path),
        "counts": {
            "failed_checks": len(failed),
            "triage_items": len(triage_items),
            "critical": int((triage.get("counts") or {}).get("critical") or 0),
            "high": int((triage.get("counts") or {}).get("high") or 0),
            "medium": int((triage.get("counts") or {}).get("medium") or 0),
            "low": int((triage.get("counts") or {}).get("low") or 0),
        },
        "checks": [check.to_dict() for check in checks],
        "failures": [check.to_dict() for check in failed],
        "markdown": markdown,
    }


def _verify_auxiliary_visibility(
    step_by_name: dict[str, dict[str, Any]],
    spec: OperationInvariantSpec,
) -> list[OperationCheck]:
    step = step_by_name.get(_AUXILIARY_HIDE_STEP)
    checks = [
        OperationCheck("auxiliary_step_present", step is not None, True, step is not None),
        OperationCheck(
            "auxiliary_step_ok",
            bool(step and step.get("ok")),
            True,
            bool(step and step.get("ok")),
        ),
        OperationCheck(
            "auxiliary_hidden_flag",
            bool(step and step.get("hidden")) is spec.require_auxiliary_hidden,
            spec.require_auxiliary_hidden,
            bool(step and step.get("hidden")),
        ),
    ]
    objects = [item for item in (step or {}).get("objects", []) if isinstance(item, dict)]
    roles = tuple(str(item.get("role") or "") for item in objects)
    bad_objects = [
        {
            "role": item.get("role"),
            "requested_hidden": item.get("requested_hidden"),
            "hidden_after": item.get("hidden_after"),
            "ok": item.get("ok"),
        }
        for item in objects
        if not (item.get("ok") and bool(item.get("requested_hidden")) is spec.require_auxiliary_hidden and bool(item.get("hidden_after")) is spec.require_auxiliary_hidden)
    ]
    checks.append(OperationCheck("auxiliary_objects_hidden", not bad_objects, [], bad_objects))
    if spec.expected_auxiliary_roles:
        missing = [role for role in spec.expected_auxiliary_roles if role not in roles]
        checks.append(OperationCheck("auxiliary_roles", not missing, list(spec.expected_auxiliary_roles), list(roles), {"missing": missing}))
    return checks


def _render_human_audit_markdown(
    run_path: Path,
    summary: dict[str, Any],
    diagnostics: dict[str, Any],
    contract: dict[str, Any],
    ledger: dict[str, Any],
    regression: dict[str, Any],
    triage: dict[str, Any],
    snapshot: dict[str, Any],
    failed: list[OperationCheck],
) -> str:
    triage_items = [item for item in triage.get("items", []) if isinstance(item, dict)]
    verdict_ok = not failed and not triage_items
    lines = [
        f"# KOMPAS CAD Run Audit: {run_path.name}",
        "",
        "## Verdict",
        "",
        f"- Overall: {_audit_status(verdict_ok)}",
        f"- Scenario: `{summary.get('scenario', '')}`",
        f"- Designation: `{summary.get('designation', '')}`",
        f"- Model: `{Path(str(summary.get('output_path') or '')).name}`",
        f"- Model size: `{summary.get('output_size_bytes', 0)}` bytes",
        f"- Fingerprint: `{snapshot.get('fingerprint', '')}`",
        "",
        "## Checks",
        "",
        "| Check | Status |",
        "| --- | --- |",
        f"| Diagnostics | {_audit_status(diagnostics.get('ok') is True)} |",
        f"| Operation contract | {_audit_status(contract.get('ok') is True)} |",
        f"| Run ledger | {_audit_status(ledger.get('ok') is True)} |",
        f"| Regression comparison | {_audit_status(regression.get('ok') is True)} |",
        f"| Failure triage | {_audit_status(triage.get('ok') is True)} |",
        f"| COM document readback | {_audit_status(summary.get('document_readback_ok') is True) if summary.get('document_readback_ok') is not None else 'SKIPPED'} |",
        f"| COM readback manifest | {_audit_status(summary.get('document_readback_manifest_ok') is True) if summary.get('document_readback_manifest_ok') is not None else 'SKIPPED'} |",
        f"| Reproducibility snapshot | {_audit_status(snapshot.get('ok') is True)} |",
        "",
        "## Counts",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Geometry probes | {summary.get('geometry_probe_count', 0)} |",
        f"| Operations | {summary.get('operation_count', 0)} |",
        f"| Variables | {summary.get('variable_count', 0)} |",
        f"| Hidden auxiliary objects | {summary.get('auxiliary_hidden_count', 0)} |",
        f"| Readback tree nodes | {summary.get('document_readback_tree_nodes') or 0} |",
        f"| Readback items | {summary.get('document_readback_item_count') or 0} |",
        f"| Readback item types | {summary.get('document_readback_manifest_item_types') or 0} |",
        f"| Snapshot files | {(snapshot.get('counts') or {}).get('files', 0)} |",
        f"| Ledger runs | {(ledger.get('counts') or {}).get('runs', 0)} |",
        "",
    ]
    if triage_items:
        lines.extend(
            [
                "## Failure Triage",
                "",
                "| Severity | Category | Source | Check | Action |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in triage_items:
            lines.append(
                "| "
                + " | ".join(
                    _markdown_cell(item.get(key))
                    for key in ("severity", "category", "source", "check", "action")
                )
                + " |"
            )
        lines.append("")
    else:
        lines.extend(["## Failure Triage", "", "No triage items.", ""])
    if failed:
        lines.extend(["## Missing Or Failed Reports", ""])
        for check in failed:
            lines.append(f"- `{check.name}` expected `{check.expected}`, got `{check.actual}`")
        lines.append("")
    return "\n".join(lines)


def _audit_status(ok: bool) -> str:
    return "OK" if ok else "FAIL"


def _markdown_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _collect_variables(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variables: list[dict[str, Any]] = []
    for step in steps:
        if step.get("step") != "part_variables":
            continue
        for item in step.get("applied") or []:
            if not isinstance(item, dict):
                continue
            variable = item.get("variable") if isinstance(item.get("variable"), dict) else {}
            variables.append(
                {
                    "name": item.get("name") or variable.get("name"),
                    "value": item.get("value") if "value" in item else variable.get("value"),
                    "expression": item.get("expression") or variable.get("expression"),
                    "reference": item.get("reference"),
                    "external": variable.get("external"),
                    "kind": variable.get("kind"),
                    "update_ok": item.get("update_ok"),
                }
            )
    return variables


def _collect_preview_operations(result: dict[str, Any]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for item in ((result.get("preview") or {}).get("operations") or []):
        if not isinstance(item, dict):
            continue
        operation = {
            key: value
            for key, value in item.items()
            if _is_manifest_scalar(value) and key not in {"profile_points"}
        }
        operations.append(operation)
    return operations


def _collect_auxiliary_objects(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for step in steps:
        if step.get("step") != _AUXILIARY_HIDE_STEP:
            continue
        for item in step.get("objects") or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "")
            hidden_after = item.get("hidden_after")
            objects.append(
                {
                    "role": role,
                    "kind": _infer_auxiliary_kind(role),
                    "name": item.get("name"),
                    "reference": item.get("reference"),
                    "ok": item.get("ok"),
                    "requested_hidden": item.get("requested_hidden"),
                    "hidden_before": item.get("hidden_before"),
                    "hidden_after": hidden_after,
                    "visible_after": None if hidden_after is None else not bool(hidden_after),
                    "update_ok": item.get("update_ok"),
                    "source_step": _AUXILIARY_HIDE_STEP,
                }
            )
    return objects


def _infer_auxiliary_kind(role: str) -> str:
    if role.endswith("_point") or role == "point":
        return "point"
    if "axis" in role:
        return "axis"
    if "spiral" in role or role.endswith("_path"):
        return "curve"
    if role.endswith("_lcs") or role == "lcs":
        return "coordinate_system"
    if "sketch" in role:
        return "sketch"
    return "object"


def _diagnostic_section(name: str, report: OperationInvariantReport | dict[str, Any]) -> dict[str, Any]:
    payload = report.to_dict() if isinstance(report, OperationInvariantReport) else report
    checks = [check for check in payload.get("checks", []) if isinstance(check, dict)]
    failed_checks = [check for check in checks if not check.get("ok")]
    return {
        "name": name,
        "stage": payload.get("stage"),
        "ok": bool(payload.get("ok")),
        "check_count": len(checks),
        "failed_count": len(failed_checks),
        "failed_checks": failed_checks,
    }


def _manifest_names(manifest: dict[str, Any], collection_name: str, key: str) -> tuple[str, ...]:
    return tuple(
        str(item.get(key) or "")
        for item in manifest.get(collection_name, [])
        if isinstance(item, dict) and item.get(key)
    )


def _readback_item_criteria(expected: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "name",
        "type",
        "item_type",
        "role",
        "reference",
        "path",
        "source",
        "hidden",
        "visible",
        "active",
        "changed",
        "depth",
        "children_count",
        "id_contains",
        "name_contains",
        "type_contains",
        "item_type_contains",
        "role_contains",
        "reference_contains",
        "path_contains",
        "parent_id_contains",
        "parent_path_contains",
        "source_contains",
        "field_equals",
        "field_contains",
        "field_has",
        "field_has_contains",
        "field_exists",
        "field_missing",
        "numeric_fields",
        "numeric_tolerance",
    )
    return {key: expected[key] for key in keys if key in expected}


def _readback_item_check_label(expected: dict[str, Any]) -> str:
    criteria = _readback_item_criteria(expected)
    for key in (
        "role",
        "name",
        "type",
        "item_type",
        "id",
        "reference",
        "path",
        "source",
        "hidden",
        "visible",
        "active",
        "changed",
        "role_contains",
        "name_contains",
        "type_contains",
        "item_type_contains",
        "id_contains",
        "reference_contains",
        "path_contains",
        "source_contains",
        "parent_id",
        "parent_path",
        "depth",
        "children_count",
        "parent_id_contains",
        "parent_path_contains",
        "field_has",
        "field_has_contains",
        "field_exists",
        "field_missing",
        "field_equals",
        "field_contains",
        "numeric_fields",
    ):
        value = criteria.get(key)
        if value not in (None, ""):
            return f"{key}={value}"
    return "unnamed"


def _is_manifest_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _verify_preview_operation_values(
    result: dict[str, Any],
    spec: OperationInvariantSpec,
) -> list[OperationCheck]:
    operations = [
        item
        for item in ((result.get("preview") or {}).get("operations") or [])
        if isinstance(item, dict)
    ]
    checks: list[OperationCheck] = []
    for operation_name, expected_values in spec.expected_operation_values.items():
        operation = next((item for item in operations if item.get("operation") == operation_name), None)
        checks.append(OperationCheck(f"preview_operation:{operation_name}", operation is not None, True, operation is not None))
        if operation is None:
            continue
        for key, expected in expected_values.items():
            actual = operation.get(key)
            checks.append(
                OperationCheck(
                    f"preview_operation:{operation_name}.{key}",
                    _values_match(actual, expected, spec.tolerance),
                    expected,
                    actual,
                )
            )
    return checks


def _values_match(actual: Any, expected: Any, tolerance: float) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(actual) - float(expected)) <= tolerance
    return actual == expected


def _numeric_check(name: str, actual: Any, expected: float, tolerance: float) -> OperationCheck:
    ok = isinstance(actual, (int, float)) and abs(float(actual) - expected) <= tolerance
    return OperationCheck(name, ok, expected, actual)


def _source_validation_check(name: str, operation: dict[str, Any]) -> OperationCheck:
    validation = operation.get("source_diameter_validation")
    if validation is None:
        return OperationCheck(name, True, True, None, {"present": False})
    if not isinstance(validation, dict):
        return OperationCheck(name, False, True, validation)
    return OperationCheck(
        name,
        validation.get("matches") is True,
        True,
        validation.get("matches"),
        {"status": validation.get("status"), "delta": validation.get("delta")},
    )


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _select_regression_baseline(
    runs: list[dict[str, Any]],
    current_name: str,
    baseline_run_name: str | None,
) -> dict[str, Any] | None:
    successful = [run for run in runs if run.get("ok")]
    if baseline_run_name:
        return next((run for run in successful if run.get("name") == baseline_run_name), None)
    current_index = next((index for index, run in enumerate(successful) if run.get("name") == current_name), None)
    if current_index is None:
        return successful[-1] if successful else None
    if current_index == 0:
        return None
    return successful[current_index - 1]


def _model_size_regression_check(
    current_size: Any,
    baseline_size: Any,
    tolerance_ratio: float,
) -> OperationCheck:
    if not isinstance(current_size, (int, float)) or not isinstance(baseline_size, (int, float)) or baseline_size <= 0:
        return OperationCheck(
            "model_size_delta_ratio",
            False,
            {"<=": tolerance_ratio},
            None,
            {"baseline_size": baseline_size, "current_size": current_size},
        )
    delta_ratio = abs(float(current_size) - float(baseline_size)) / float(baseline_size)
    return OperationCheck(
        "model_size_delta_ratio",
        delta_ratio <= tolerance_ratio,
        {"<=": tolerance_ratio},
        delta_ratio,
        {"baseline_size": baseline_size, "current_size": current_size},
    )


def _extract_report_failures(payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures = [item for item in payload.get("failures", []) if isinstance(item, dict)]
    checks = [
        item
        for item in payload.get("checks", [])
        if isinstance(item, dict) and item.get("ok") is False
    ]
    if failures and checks:
        return failures + [check for check in checks if check not in failures]
    if failures:
        return failures
    return checks


def _failure_category(source: str, check_name: str) -> str:
    token = f"{source}:{check_name}".lower()
    if "readback" in token or "document_" in token or "close_document" in token or "open_document" in token:
        return "document_readback"
    if "artifact" in token or "output_" in token or "saved" in token or "result_ok" in token:
        return "model_artifact"
    if "thread" in token or "spiral" in token or "profile" in token or "cut." in token or "diameter" in token or "pitch" in token or "root" in token:
        return "geometry"
    if "auxiliary" in token or "hidden" in token or "visibility" in token:
        return "auxiliary_visibility"
    if "regression" in token or "baseline" in token or "delta" in token:
        return "regression"
    if "contract" in token or "manifest" in token or "count:" in token or "operation:" in token or "variable:" in token:
        return "contract"
    if "preflight" in token or "sketch" in token:
        return "sketch_preflight"
    return "runtime"


def _failure_severity(source: str, check_name: str, category: str) -> str:
    token = f"{source}:{check_name}".lower()
    if category == "model_artifact":
        return "critical"
    if category == "geometry":
        return "high"
    if category in {"auxiliary_visibility", "contract", "sketch_preflight", "document_readback"}:
        return "medium"
    if category == "regression":
        return "medium" if "baseline_available" in token else "high"
    return "low"


def _failure_action(category: str) -> str:
    actions = {
        "model_artifact": "rerun the KOMPAS operation and inspect COM connection, save path, and output file permissions",
        "geometry": "inspect scenario parameters and preview operations before accepting the CAD result",
        "auxiliary_visibility": "check the auxiliary hide step and the roles returned by KOMPAS after model creation",
        "regression": "compare the current run with the selected baseline and decide whether the drift is expected",
        "contract": "update the operation contract only if the pipeline change is intentional; otherwise fix the missing role, operation, or count",
        "document_readback": "inspect the COM document open/tree/items/close calls before trusting the saved model readback",
        "sketch_preflight": "fix the sketch/runtime preflight plan before calling KOMPAS again",
        "runtime": "inspect the source report for the failed check and preserve the generated artifacts for debugging",
    }
    return actions.get(category, actions["runtime"])


def _triage_next_actions(items: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for item in items:
        action = str(item.get("action") or "")
        if action and action not in actions:
            actions.append(action)
    return actions


def _snapshot_file(root: Path, file_path: Path, *, role: str | None = None) -> dict[str, Any]:
    try:
        relative_path = file_path.relative_to(root)
        path_value = relative_path.as_posix()
    except ValueError:
        path_value = str(file_path)
    return {
        "path": path_value,
        "role": role or _snapshot_role(file_path.name),
        "kind": _snapshot_kind(file_path),
        "size_bytes": file_path.stat().st_size,
        "sha256": _sha256_file(file_path),
    }


def _snapshot_role(name: str) -> str:
    if name.endswith(".m3d"):
        return "model"
    if name == "02_kompas_task_payload.json":
        return "input_payload"
    if name == "03_kompas_create_result.json":
        return "kompas_result"
    if name == "summary.json":
        return "summary"
    return "report"


def _snapshot_kind(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".m3d":
        return "kompas_model"
    return suffix.lstrip(".") or "file"


def _sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_validity_check(root: Path, file_path: Path) -> OperationCheck:
    try:
        json.loads(file_path.read_text(encoding="utf-8"))
        return OperationCheck(f"json_valid:{file_path.relative_to(root).as_posix()}", True, True, True)
    except Exception as exc:
        return OperationCheck(
            f"json_valid:{file_path.name}",
            False,
            True,
            False,
            {"error": str(exc)},
        )


def _combined_fingerprint(files: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(str(item["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item["sha256"]).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _is_prefixed_run_dir(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(f"{prefix}_")


def _run_sort_key(name: str, prefix: str) -> tuple[int, str]:
    if name == prefix:
        return (1, name)
    suffix = name.removeprefix(f"{prefix}_")
    if suffix.isdigit():
        return (int(suffix), name)
    return (10_000, name)
