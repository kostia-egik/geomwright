from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_KEYS = (
    "success", "ok", "stage", "error", "document", "verification", "body",
    "axial_rounding", "row_layout", "transition_constraint", "final_save",
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Evidence root must be a JSON object")
    return value


def _select(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _object_reference(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: value.get(key)
        for key in ("name", "reference", "valid", "role")
        if value.get(key) is not None
    } or None


def _compact(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        if isinstance(value, list):
            return {"item_count": len(value)}
        if isinstance(value, dict):
            return {"key_count": len(value)}
        return value
    if isinstance(value, list):
        references = [item for item in (_object_reference(item) for item in value) if item]
        return references if references and len(references) == len(value) else {"item_count": len(value)}
    if not isinstance(value, dict):
        return value
    noisy = {
        "steps", "entities", "constraints", "dimensions", "variables",
        "remaining_documents", "owned_references", "sketches", "extrusion_features",
        "rotated_features", "feature_patterns", "connector_steps",
        "rounding_sketch_readback", "reopened_inspection",
    }
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in noisy:
            result[key] = {"item_count": len(item)} if isinstance(item, list) else {"available": bool(item)}
        elif key in DEFAULT_KEYS or depth > 0 or key in {
            "row_count", "row_spacing", "total_width", "pattern_count", "body_count",
            "solid", "volume", "final_rebuild_ok", "save_reopen", "saved_as",
            "runtime_id", "path", "constraints_state_requires_ui_confirmation",
        }:
            result[key] = _compact(item, depth + 1)
    return result


def summarize(evidence: dict[str, Any], selectors: list[str]) -> dict[str, Any]:
    if selectors:
        return {selector: _compact(_select(evidence, selector)) for selector in selectors}
    result: dict[str, Any] = {
        key: evidence.get(key)
        for key in ("success", "ok", "stage", "error")
        if evidence.get(key) is not None
    }
    document = evidence.get("document") or {}
    if isinstance(document, dict):
        result["document"] = {
            key: document.get(key)
            for key in ("runtime_id", "name", "path", "changed")
            if document.get(key) not in (None, "")
        }
    verification = evidence.get("verification") or {}
    if isinstance(verification, dict):
        result["verification"] = {
            key: verification.get(key)
            for key in (
                "ok", "final_rebuild_ok", "single_body", "positive_volume",
                "pattern_count", "row_count", "row_layout_verified",
                "axial_rounding_cut_count", "axial_rounding_volume_decreased",
            )
            if verification.get(key) is not None
        }
    body = evidence.get("body") or {}
    if isinstance(body, dict):
        result["body"] = {
            key: body.get(key)
            for key in ("body_count", "solid", "volume", "face_count")
            if body.get(key) is not None
        }
    rounding = evidence.get("axial_rounding") or {}
    if isinstance(rounding, dict) and rounding:
        result["axial_rounding"] = {
            key: rounding.get(key)
            for key in ("source", "radius_selection", "r3", "h3", "sag", "tip_land_width")
            if rounding.get(key) is not None
        }
    row_layout = evidence.get("row_layout")
    if isinstance(row_layout, dict):
        result["row_layout"] = {
            key: row_layout.get(key)
            for key in ("ok", "row_count", "row_spacing", "total_width", "expected_volume_cm3")
            if row_layout.get(key) is not None
        }
    transition = evidence.get("transition_constraint") or {}
    if isinstance(transition, dict) and transition:
        result["transition_constraint"] = {
            key: transition.get(key)
            for key in (
                "ok", "kind", "closed", "gap_count", "self_intersection_count",
                "constraints_state_requires_ui_confirmation", "apply_call_timed_out",
            )
            if transition.get(key) is not None
        }
    final_save = evidence.get("final_save") or {}
    if isinstance(final_save, dict) and final_save:
        saved_document = final_save.get("document") or {}
        result["final_save"] = {
            "saved_as": final_save.get("saved_as"),
            "closed": final_save.get("closed"),
            "runtime_id": saved_document.get("runtime_id") if isinstance(saved_document, dict) else None,
        }
    reopened = evidence.get("reopened_inspection") or {}
    if isinstance(reopened, dict) and reopened:
        result["reopened_inspection"] = {
            "recognized": reopened.get("recognized"),
            "family": reopened.get("family"),
            "profile_request": reopened.get("profile_request"),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a bounded summary of a JSON evidence artifact")
    parser.add_argument("path", type=Path)
    parser.add_argument("--select", default="", help="Comma-separated dotted paths")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()
    selectors = [item.strip() for item in args.select.split(",") if item.strip()]
    summary = summarize(_load(args.path), selectors)
    text = json.dumps(summary, ensure_ascii=False, indent=args.indent)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "summary": str(args.output)}, ensure_ascii=False))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
