from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter  # noqa: E402
from kompas_mcp.runtime_errors import classify_runtime_error  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "sample" / "generated" / "live_kompas_write_v2_2026_05_24"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run a manual live Write Operations V2 audit against a copied KOMPAS model: "
            "open, create one sketch with several entities, verify snapshot delta, save manifest, close."
        )
    )
    parser.add_argument("--model-path", required=True, help="Source model to copy before mutation.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for copied model and JSON artifacts.")
    parser.add_argument("--visible", action="store_true", help="Open the copied model visibly.")
    parser.add_argument("--keep-open", action="store_true", help="Leave the copied document open after the audit.")
    parser.add_argument("--save-on-close", action="store_true", help="Save the copied model when closing it.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    copied_model = _copy_model(args.model_path, output_dir)
    adapter = KompasAdapter()

    tool_inputs = {
        "name": "WRITE_V2_AUDIT_SKETCH",
        "plane": "XOY",
        "entities": [
            {"kind": "point", "id": "origin_marker", "point": [0, 0]},
            {"kind": "segment", "id": "base", "start": [0, 0], "end": [50, 0]},
            {"kind": "segment", "id": "upright", "start": [50, 0], "end": [50, 24]},
            {"kind": "polyline", "points": [[0, 24], [12, 34], [24, 24], [36, 34], [48, 24]]},
            {"kind": "arc", "center": [25, 12], "radius": 10, "start": [35, 12], "end": [25, 22]},
            {"kind": "circle", "id": "hole", "center": [25, 12], "radius": 6},
            {"kind": "ellipse", "center": [25, -12], "radius_x": 14, "radius_y": 5},
            {"kind": "rectangle", "corner1": [0, 0], "corner2": [50, 24]},
        ],
        "constraints": [
            {"kind": "horizontal", "target": "base"},
            {"kind": "vertical", "target": "upright"},
            {"kind": "perpendicular", "target": "base", "partner": "upright"},
        ],
        "dimensions": [
            {"kind": "line_length", "target": "base", "value": 50, "driving": False, "point_y": -10},
            {"kind": "circle_diameter", "target": "hole", "value": 12, "driving": False, "angle": 0},
        ],
        "sketch_options": {
            "constraints": {"enabled": True},
            "dimensions": {"enabled": True, "driving": False},
            "readback_geometry": True,
        },
        "min_added": 1,
        "require_no_removed": False,
    }
    audit: dict[str, Any] = {
        "schema": "kompas_mcp.write_operations_v2.live_audit.v1",
        "inputs": {
            "model_path": str(Path(args.model_path)),
            "copied_model": str(copied_model),
            "visible": args.visible,
            "save_on_close": args.save_on_close,
        },
        "tool_inputs": tool_inputs,
        "steps": [],
    }
    opened_document_id: str | None = None

    try:
        open_step = _run_step("open_copied_model", lambda: adapter.open_document(str(copied_model), visible=args.visible, read_only=False))
        audit["steps"].append(open_step)
        opened_document_id = _extract_document_id(open_step.get("payload"))
        audit["document_id"] = opened_document_id
        if not opened_document_id:
            _finish(audit, output_dir)
            return

        audit["steps"].append(
            _run_step(
                "preflight",
                lambda: adapter.preflight_document_context(
                    document_id=opened_document_id,
                    require_active_document=True,
                    require_tree=True,
                ),
            )
        )
        write_step = _run_step(
            "create_sketch_entities",
            lambda: adapter.create_sketch_entities(document_id=opened_document_id, **tool_inputs),
        )
        audit["steps"].append(write_step)
        audit["write_manifest"] = _build_write_manifest(tool_inputs, write_step.get("payload"))
        sketch_ref = _extract_sketch_ref(write_step.get("payload"))
        if sketch_ref not in (None, ""):
            audit["steps"].append(
                _run_step(
                    "list_sketches",
                    lambda: adapter.list_sketches(
                        document_id=opened_document_id,
                        name_contains="WRITE_V2_AUDIT",
                        max_items=25,
                    ),
                )
            )
            audit["steps"].append(
                _run_step(
                    "rename_sketch",
                    lambda: adapter.rename_sketch(
                        document_id=opened_document_id,
                        sketch_ref=sketch_ref,
                        name="WRITE_V2_AUDIT_RENAMED",
                    ),
                )
            )
            list_arcs_step = _run_step(
                "list_existing_sketch_arcs",
                lambda: adapter.list_sketch_entities(
                    document_id=opened_document_id,
                    sketch_ref=sketch_ref,
                    kinds=["arc"],
                    max_items=10,
                ),
            )
            audit["steps"].append(list_arcs_step)
            arc_row = _extract_first_list_item(list_arcs_step.get("payload"), "arc")
            if arc_row is not None:
                audit["steps"].append(
                    _run_step(
                        "update_existing_sketch_arc_geometry",
                        lambda: adapter.update_sketch_entity_geometry(
                            document_id=opened_document_id,
                            sketch_ref=sketch_ref,
                            entity={
                                "kind": "arc",
                                "index": int(arc_row.get("collection_index")),
                                "fingerprint": arc_row.get("fingerprint"),
                            },
                            geometry={
                                "center": [25, 12],
                                "radius": 9,
                                "start": [34, 12],
                                "end": [25, 21],
                                "direction": bool(arc_row.get("geometry", {}).get("direction", False)),
                            },
                        ),
                    )
                )
            append_inputs = {
                "sketch_ref": sketch_ref,
                "create_new_sketch": False,
                "entities": [
                    {"kind": "segment", "id": "tail", "start": [60, 0], "end": [80, 0]},
                    {"kind": "point", "id": "audit_point", "point": [80, 20]},
                ],
                "min_added": 1,
                "require_no_removed": False,
                "require_no_changed": False,
            }
            append_step = _run_step(
                "append_existing_sketch_entities",
                lambda: adapter.create_sketch_entities(document_id=opened_document_id, **append_inputs),
            )
            audit["steps"].append(append_step)
            audit["append_write_manifest"] = _build_write_manifest(append_inputs, append_step.get("payload"))
            tail_index = _extract_item_field(append_step.get("payload"), "tail", "collection_index")
            audit_point_index = _extract_item_field(append_step.get("payload"), "audit_point", "collection_index")
            if audit_point_index not in (None, ""):
                audit["steps"].append(
                    _run_step(
                        "update_existing_sketch_entity_geometry",
                        lambda: adapter.update_sketch_entity_geometry(
                            document_id=opened_document_id,
                            sketch_ref=sketch_ref,
                            entity={"kind": "point", "index": int(audit_point_index)},
                            geometry={"point": [82, 22]},
                        ),
                    )
                )
                audit["steps"].append(
                    _run_step(
                        "delete_existing_sketch_entity",
                        lambda: adapter.delete_sketch_entity(
                            document_id=opened_document_id,
                            sketch_ref=sketch_ref,
                            entity={"kind": "point", "index": int(audit_point_index)},
                        ),
                    )
                )
            list_step = _run_step(
                "list_existing_sketch_entities",
                lambda: adapter.list_sketch_entities(
                    document_id=opened_document_id,
                    sketch_ref=sketch_ref,
                    kinds=["segment"],
                    max_items=50,
                ),
            )
            audit["steps"].append(list_step)
            tail_row = _extract_list_item_by_collection_index(list_step.get("payload"), "segment", tail_index)
            if tail_index not in (None, "") and tail_row is not None:
                inspect_step = _run_step(
                    "inspect_existing_sketch_entity",
                    lambda: adapter.inspect_sketch_entity(
                        document_id=opened_document_id,
                        sketch_ref=sketch_ref,
                        entity={
                            "kind": "segment",
                            "index": int(tail_row.get("collection_index")),
                            "fingerprint": tail_row.get("fingerprint"),
                        },
                    ),
                )
                audit["steps"].append(inspect_step)
                inspected_tail = inspect_step.get("payload", {}).get("item") if isinstance(inspect_step.get("payload"), dict) else None
                if not isinstance(inspected_tail, dict):
                    inspected_tail = tail_row
                style_step = _run_step(
                    "set_existing_sketch_entity_style",
                    lambda: adapter.set_sketch_entity_style(
                        document_id=opened_document_id,
                        sketch_ref=sketch_ref,
                        entity={
                            "kind": "segment",
                            "index": int(inspected_tail.get("collection_index")),
                            "fingerprint": inspected_tail.get("fingerprint"),
                        },
                        line_style=2,
                    ),
                )
                audit["steps"].append(style_step)
                parameterize_inputs = {
                    "sketch_ref": sketch_ref,
                    "entities": [
                        {
                            "id": "tail",
                            "kind": "segment",
                            "index": int(inspected_tail.get("collection_index")),
                            "fingerprint": inspected_tail.get("fingerprint"),
                            "start": [60, 0],
                            "end": [80, 0],
                        },
                    ],
                    "constraints": [
                        {"kind": "horizontal", "target": "tail"},
                    ],
                    "dimensions": [
                        {"kind": "line_length", "target": "tail", "value": 20, "driving": False, "point_y": -18},
                    ],
                    "sketch_options": {
                        "constraints": {"enabled": True},
                        "dimensions": {"enabled": True, "driving": False},
                        "readback_geometry": True,
                    },
                    "require_no_removed": False,
                    "require_no_changed": False,
                }
                parameterize_step = _run_step(
                    "parameterize_existing_sketch",
                    lambda: adapter.parameterize_sketch(document_id=opened_document_id, **parameterize_inputs),
                )
                audit["steps"].append(parameterize_step)
                audit["parameterize_manifest"] = _build_write_manifest(parameterize_inputs, parameterize_step.get("payload"))
                dimension_list_step = _run_step(
                    "list_existing_sketch_dimensions",
                    lambda: adapter.list_sketch_dimensions(
                        document_id=opened_document_id,
                        sketch_ref=sketch_ref,
                        kinds=["line_length"],
                        max_items=25,
                    ),
                )
                audit["steps"].append(dimension_list_step)
                line_dimension = _extract_first_list_item(dimension_list_step.get("payload"), "line")
                if line_dimension is not None:
                    audit["steps"].append(
                        _run_step(
                            "inspect_existing_sketch_dimension",
                            lambda: adapter.inspect_sketch_dimension(
                                document_id=opened_document_id,
                                sketch_ref=sketch_ref,
                                dimension={
                                    "kind": "line_length",
                                    "index": int(line_dimension.get("collection_index")),
                                    "fingerprint": line_dimension.get("fingerprint"),
                                },
                            ),
                        )
                    )
                constraint_list_step = _run_step(
                    "list_existing_sketch_constraints",
                    lambda: adapter.list_sketch_constraints(
                        document_id=opened_document_id,
                        sketch_ref=sketch_ref,
                        kinds=["horizontal"],
                        max_items=25,
                    ),
                )
                audit["steps"].append(constraint_list_step)
                horizontal_constraint = _extract_first_list_item(constraint_list_step.get("payload"), "horizontal")
                if horizontal_constraint is not None:
                    audit["steps"].append(
                        _run_step(
                            "inspect_existing_sketch_constraint",
                            lambda: adapter.inspect_sketch_constraint(
                                document_id=opened_document_id,
                                sketch_ref=sketch_ref,
                                constraint={
                                    "kind": "horizontal",
                                    "index": int(horizontal_constraint.get("collection_index")),
                                    "fingerprint": horizontal_constraint.get("fingerprint"),
                                },
                            ),
                        )
                    )
                repair_operations = [
                    {
                        "operation": "clear_constraints",
                        "entity": {
                            "kind": "segment",
                            "index": int(inspected_tail.get("collection_index")),
                            "fingerprint": inspected_tail.get("fingerprint"),
                        },
                    },
                    {
                        "operation": "update_geometry",
                        "entity": {
                            "kind": "segment",
                            "index": int(inspected_tail.get("collection_index")),
                            "fingerprint": inspected_tail.get("fingerprint"),
                        },
                        "geometry": {"start": [62, 0], "end": [82, 0]},
                    },
                ]
                audit["steps"].append(
                    _run_step(
                        "repair_sketch_plan",
                        lambda: adapter.repair_sketch(
                            document_id=opened_document_id,
                            sketch_ref=sketch_ref,
                            operations=repair_operations,
                            apply=False,
                        ),
                    )
                )
                audit["steps"].append(
                    _run_step(
                        "repair_sketch_apply",
                        lambda: adapter.repair_sketch(
                            document_id=opened_document_id,
                            sketch_ref=sketch_ref,
                            operations=repair_operations,
                            apply=True,
                        ),
                    )
                )
                audit["steps"].append(
                    _run_step(
                        "clear_existing_sketch_entity_constraints",
                        lambda: adapter.clear_sketch_entity_constraints(
                            document_id=opened_document_id,
                            sketch_ref=sketch_ref,
                            entity={
                                "kind": "segment",
                                "index": int(inspected_tail.get("collection_index")),
                                "fingerprint": inspected_tail.get("fingerprint"),
                            },
                        ),
                    )
                )

        audit["steps"].append(
            _run_step(
                "after_snapshot",
                lambda: adapter.capture_document_snapshot(
                    document_id=opened_document_id,
                    output_path=str(output_dir / "after_snapshot.json"),
                    close_after_probe=False,
                    include_manifest=True,
                ),
            )
        )
    finally:
        if opened_document_id and not args.keep_open:
            audit["steps"].append(
                _run_step(
                    "close_copied_model",
                    lambda: adapter.close_document(document_id=opened_document_id, save=args.save_on_close),
                )
            )

    _finish(audit, output_dir)


def _copy_model(model_path: str, output_dir: Path) -> Path:
    source = Path(model_path)
    if not source.exists():
        raise FileNotFoundError(str(source))
    target = output_dir / ("write_v2_copy" + source.suffix)
    shutil.copy2(source, target)
    return target


def _run_step(name: str, callback: Callable[[], Any]) -> dict[str, Any]:
    try:
        payload = callback()
    except Exception as exc:  # pragma: no cover - live COM path.
        return {"name": name, "ok": False, "error": classify_runtime_error(exc), "payload": None}
    return {"name": name, "ok": _payload_ok(payload), "payload": payload, "preview": _preview_payload(payload)}


def _payload_ok(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(payload.get("ok", payload.get("status") != "failed"))


def _build_write_manifest(tool_inputs: dict[str, Any], raw_result: Any) -> dict[str, Any]:
    result = raw_result if isinstance(raw_result, dict) else {}
    snapshots = result.get("snapshots") if isinstance(result.get("snapshots"), dict) else {}
    delta = result.get("delta") if isinstance(result.get("delta"), dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "tool_inputs": tool_inputs,
        "raw_result_preview": result.get("result_preview"),
        "before_summary": _snapshot_summary(snapshots.get("before")),
        "after_summary": _snapshot_summary(snapshots.get("after")),
        "delta_summary": delta.get("summary") if isinstance(delta.get("summary"), dict) else {},
        "counts_delta": delta.get("counts_delta") if isinstance(delta.get("counts_delta"), dict) else {},
        "parameterization": _parameterization_summary(result.get("parameterization")),
        "failures": result.get("failures") if isinstance(result.get("failures"), list) else [],
    }


def _snapshot_summary(snapshot: Any) -> dict[str, Any]:
    return snapshot.get("summary") if isinstance(snapshot, dict) and isinstance(snapshot.get("summary"), dict) else {}


def _parameterization_summary(parameterization: Any) -> dict[str, Any]:
    if not isinstance(parameterization, dict):
        return {}
    constraints = parameterization.get("constraints") if isinstance(parameterization.get("constraints"), dict) else {}
    dimensions = parameterization.get("dimensions") if isinstance(parameterization.get("dimensions"), dict) else {}
    geometry = parameterization.get("geometry_checks") if isinstance(parameterization.get("geometry_checks"), dict) else {}
    return {
        "ok": bool(parameterization.get("ok")),
        "constraints": {
            "live_status": constraints.get("live_status"),
            "applied_count": constraints.get("applied_count"),
            "failed_count": constraints.get("failed_count"),
            "skipped_count": constraints.get("skipped_count"),
        },
        "dimensions": {
            "live_status": dimensions.get("live_status"),
            "applied_count": dimensions.get("applied_count"),
            "failed_count": dimensions.get("failed_count"),
        },
        "geometry_checks": {
            "ok": geometry.get("ok"),
            "checked_count": geometry.get("checked_count"),
            "failed_count": geometry.get("failed_count"),
        },
    }


def _preview_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"type": type(payload).__name__}
    preview: dict[str, Any] = {"keys": sorted(str(key) for key in payload.keys())[:16]}
    for key in ("ok", "status", "operation", "stage", "document_id"):
        if key in payload:
            preview[key] = payload.get(key)
    if isinstance(payload.get("delta"), dict):
        preview["delta_summary"] = payload["delta"].get("summary")
    if isinstance(payload.get("summary"), dict):
        preview["summary"] = payload.get("summary")
    return preview


def _extract_document_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    document = payload.get("document")
    if isinstance(document, dict):
        for key in ("id", "path", "name"):
            if document.get(key):
                return str(document[key])
    return None


def _extract_sketch_ref(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    target = payload.get("target")
    if isinstance(target, dict):
        return target.get("sketch_ref")
    item = payload.get("item")
    if isinstance(item, dict):
        return item.get("sketch_ref") or item.get("reference")
    return None


def _extract_item_field(payload: Any, entity_id: str, field: str) -> Any:
    if not isinstance(payload, dict):
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and str(item.get("id") or "") == str(entity_id):
            return item.get(field)
    return None


def _extract_list_item_by_collection_index(payload: Any, kind: str, collection_index: Any) -> dict[str, Any] | None:
    if collection_index in (None, "") or not isinstance(payload, dict):
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    wanted_index = int(collection_index)
    for item in items:
        if (
            isinstance(item, dict)
            and item.get("kind") == kind
            and item.get("collection_index") == wanted_index
        ):
            return item
    return None


def _extract_first_list_item(payload: Any, kind: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("kind") == kind:
            return item
    return None


def _step_ok(audit: dict[str, Any], name: str) -> bool | None:
    for step in audit.get("steps", []):
        if isinstance(step, dict) and step.get("name") == name:
            return bool(step.get("ok"))
    return None


def _finish(audit: dict[str, Any], output_dir: Path) -> None:
    audit["ok"] = all(step.get("ok") for step in audit.get("steps", []))
    audit["summary"] = {
        "step_count": len(audit.get("steps", [])),
        "failed_steps": [step.get("name") for step in audit.get("steps", []) if not step.get("ok")],
        "write_ok": bool(audit.get("write_manifest", {}).get("ok")),
        "append_write_ok": bool(audit.get("append_write_manifest", {}).get("ok")) if "append_write_manifest" in audit else None,
        "list_sketches_ok": _step_ok(audit, "list_sketches"),
        "rename_sketch_ok": _step_ok(audit, "rename_sketch"),
        "set_sketch_entity_style_ok": _step_ok(audit, "set_existing_sketch_entity_style"),
        "delete_sketch_entity_ok": _step_ok(audit, "delete_existing_sketch_entity"),
        "update_sketch_entity_geometry_ok": _step_ok(audit, "update_existing_sketch_entity_geometry"),
        "update_sketch_arc_geometry_ok": _step_ok(audit, "update_existing_sketch_arc_geometry"),
        "list_sketch_dimensions_ok": _step_ok(audit, "list_existing_sketch_dimensions"),
        "inspect_sketch_dimension_ok": _step_ok(audit, "inspect_existing_sketch_dimension"),
        "list_sketch_constraints_ok": _step_ok(audit, "list_existing_sketch_constraints"),
        "inspect_sketch_constraint_ok": _step_ok(audit, "inspect_existing_sketch_constraint"),
        "clear_sketch_entity_constraints_ok": _step_ok(audit, "clear_existing_sketch_entity_constraints"),
        "repair_sketch_plan_ok": _step_ok(audit, "repair_sketch_plan"),
        "repair_sketch_apply_ok": _step_ok(audit, "repair_sketch_apply"),
        "list_sketch_entities_ok": _step_ok(audit, "list_existing_sketch_entities"),
        "inspect_sketch_entity_ok": _step_ok(audit, "inspect_existing_sketch_entity"),
        "parameterize_ok": bool(audit.get("parameterize_manifest", {}).get("ok")) if "parameterize_manifest" in audit else None,
    }
    manifest_path = output_dir / "write_v2_audit_manifest.json"
    manifest_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": audit["ok"], "manifest_path": str(manifest_path), "summary": audit["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
