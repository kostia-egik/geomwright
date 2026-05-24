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
            {"kind": "point", "point": [0, 0]},
            {"kind": "segment", "start": [0, 0], "end": [50, 0]},
            {"kind": "polyline", "points": [[0, 24], [12, 34], [24, 24], [36, 34], [48, 24]]},
            {"kind": "arc", "center": [25, 12], "radius": 10, "start": [35, 12], "end": [25, 22]},
            {"kind": "circle", "center": [25, 12], "radius": 6},
            {"kind": "ellipse", "center": [25, -12], "radius_x": 14, "radius_y": 5},
            {"kind": "rectangle", "corner1": [0, 0], "corner2": [50, 24]},
        ],
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
            append_inputs = {
                "sketch_ref": sketch_ref,
                "create_new_sketch": False,
                "entities": [
                    {"kind": "segment", "start": [60, 0], "end": [80, 20]},
                    {"kind": "point", "point": [80, 20]},
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
        "failures": result.get("failures") if isinstance(result.get("failures"), list) else [],
    }


def _snapshot_summary(snapshot: Any) -> dict[str, Any]:
    return snapshot.get("summary") if isinstance(snapshot, dict) and isinstance(snapshot.get("summary"), dict) else {}


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


def _finish(audit: dict[str, Any], output_dir: Path) -> None:
    audit["ok"] = all(step.get("ok") for step in audit.get("steps", []))
    audit["summary"] = {
        "step_count": len(audit.get("steps", [])),
        "failed_steps": [step.get("name") for step in audit.get("steps", []) if not step.get("ok")],
        "write_ok": bool(audit.get("write_manifest", {}).get("ok")),
        "append_write_ok": bool(audit.get("append_write_manifest", {}).get("ok")) if "append_write_manifest" in audit else None,
    }
    manifest_path = output_dir / "write_v2_audit_manifest.json"
    manifest_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": audit["ok"], "manifest_path": str(manifest_path), "summary": audit["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
