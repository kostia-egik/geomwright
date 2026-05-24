from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter  # noqa: E402
from kompas_mcp.runtime_errors import classify_runtime_error  # noqa: E402
from kompas_mcp.tool_catalog import get_mcp_tool_catalog  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "sample" / "generated" / "live_kompas_low_level_audit_2026_05_20"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run a read-only low-level KOMPAS MCP audit: preflight, probes, "
            "snapshot, stability, catalog. Run one audit at a time; KOMPAS has "
            "a process-global active document."
        )
    )
    parser.add_argument("--model-path", default=None, help="Open this model read-only once, then audit it.")
    parser.add_argument("--document-id", default=None, help="Audit an already opened document id/path/name.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for JSON audit artifacts.")
    parser.add_argument("--expected-type", default=None, help="Expected KOMPAS document type, compared as text.")
    parser.add_argument(
        "--expected-extension",
        action="append",
        default=None,
        help="Allowed extension such as m3d/a3d/cdw. Can be passed more than once.",
    )
    parser.add_argument("--allow-non-active", action="store_true", help="Do not require the selected document to be active.")
    parser.add_argument("--require-tree", action="store_true", help="Require at least one tree node during preflight.")
    parser.add_argument("--require-items", action="store_true", help="Require at least one flat item during preflight.")
    parser.add_argument("--visible", action="store_true", help="Open --model-path visibly.")
    parser.add_argument("--keep-open", action="store_true", help="Leave a document opened by --model-path open.")
    parser.add_argument(
        "--no-default-volatile-ignores",
        action="store_true",
        help="Do not ignore default volatile readback keys during stability diff.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    adapter = KompasAdapter()
    opened_document_id: str | None = None
    audit: dict[str, Any] = {
        "schema": "kompas_mcp.live_low_level_audit.v1",
        "inputs": {
            "model_path": args.model_path,
            "document_id": args.document_id,
            "expected_type": args.expected_type,
            "expected_extension": args.expected_extension,
            "require_active_document": not args.allow_non_active,
            "require_tree": args.require_tree,
            "require_items": args.require_items,
            "use_default_volatile_ignores": not args.no_default_volatile_ignores,
        },
        "steps": [],
    }

    try:
        if args.model_path:
            open_step = _run_step(
                "open_document",
                lambda: adapter.open_document(args.model_path, visible=args.visible, read_only=True),
                ok_predicate=_has_document_payload,
            )
            audit["steps"].append(open_step)
            _record_step_document_id(audit, "opened_document_id", open_step)
            opened_document_id = _extract_document_id(open_step.get("payload"))
            if not opened_document_id:
                _finish(audit, output_dir)
                return

        document_id = args.document_id or opened_document_id
        audit["document_id"] = document_id

        audit["steps"].append(
            _run_step(
                "tool_catalog",
                lambda: get_mcp_tool_catalog(category="low_level_runtime"),
                ok_predicate=_has_catalog_tools,
            )
        )
        audit["steps"].append(
            _run_step(
                "preflight",
                lambda: adapter.preflight_document_context(
                    document_id=document_id,
                    require_active_document=not args.allow_non_active,
                    expected_document_type=args.expected_type,
                    expected_extensions=args.expected_extension,
                    require_tree=args.require_tree,
                    require_items=args.require_items,
                ),
            )
        )
        audit["steps"].append(
            _run_step(
                "probe",
                lambda: adapter.probe_document_readback(
                    document_id=document_id,
                    output_path=str(output_dir / "probe.json"),
                    close_after_probe=False,
                ),
            )
        )
        audit["steps"].append(
            _run_step(
                "model_object_probe",
                lambda: adapter.probe_model_object_collections(
                    document_id=document_id,
                    max_items=5,
                    include_empty=True,
                ),
            )
        )
        audit["steps"].append(
            _run_step(
                "snapshot",
                lambda: adapter.capture_document_snapshot(
                    document_id=document_id,
                    output_path=str(output_dir / "snapshot.json"),
                    close_after_probe=False,
                    include_manifest=False,
                ),
            )
        )
        audit["steps"].append(
            _run_step(
                "stability",
                lambda: adapter.verify_document_readback_stability(
                    document_id=document_id,
                    before_output_path=str(output_dir / "stability_before.json"),
                    after_output_path=str(output_dir / "stability_after.json"),
                    require_active_document=not args.allow_non_active,
                    use_default_volatile_ignores=not args.no_default_volatile_ignores,
                ),
            )
        )
    finally:
        if opened_document_id and not args.keep_open:
            close_step = _run_step(
                "close_document",
                lambda: adapter.close_document(document_id=opened_document_id, save=False),
                ok_predicate=lambda payload: isinstance(payload, dict),
            )
            audit["steps"].append(close_step)
            _record_step_document_id(audit, "closed_document_id", close_step)

    _finish(audit, output_dir)


def _run_step(
    name: str,
    callback: Callable[[], Any],
    *,
    ok_predicate: Callable[[Any], bool] | None = None,
) -> dict[str, Any]:
    try:
        payload = callback()
    except Exception as exc:  # pragma: no cover - exercised only with live COM failures.
        classification = classify_runtime_error(exc)
        return {
            "name": name,
            "ok": False,
            "error": classification,
            "payload": None,
        }
    ok = ok_predicate(payload) if ok_predicate is not None else _payload_ok(payload)
    return {
        "name": name,
        "ok": bool(ok),
        "payload": payload,
        "preview": _preview_payload(payload),
    }


def _payload_ok(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if "ok" in payload:
        return bool(payload["ok"])
    if "status" in payload:
        return str(payload["status"]).lower() not in {"failed", "error"}
    return True


def _has_document_payload(payload: Any) -> bool:
    return bool(_extract_document_id(payload))


def _has_catalog_tools(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    categories = payload.get("categories")
    if not isinstance(categories, list):
        return False
    return any(isinstance(category, dict) and category.get("tools") for category in categories)


def _extract_document_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    document = payload.get("document")
    if isinstance(document, dict):
        for key in ("id", "path", "name"):
            value = document.get(key)
            if value:
                return str(value)
    for key in ("document_id", "id", "path"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _record_step_document_id(audit: dict[str, Any], key: str, step: dict[str, Any]) -> None:
    document_id = _extract_document_id(step.get("payload"))
    if document_id:
        audit[key] = document_id


def _preview_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"type": type(payload).__name__}
    preview: dict[str, Any] = {}
    for key in (
        "ok",
        "status",
        "summary",
        "category_count",
        "tool_count",
        "document",
        "readback",
        "probe",
        "artifact",
        "failures",
        "checks",
    ):
        if key not in payload:
            continue
        value = payload[key]
        if key == "checks" and isinstance(value, list):
            preview["failed_checks"] = [item for item in value if isinstance(item, dict) and not item.get("ok")][:10]
        elif key == "failures" and isinstance(value, list):
            preview[key] = value[:10]
        elif key == "probe" and isinstance(value, dict):
            summary = value.get("summary")
            if summary is not None:
                preview["probe_summary"] = summary
            else:
                preview["probe"] = {
                    item_key: value.get(item_key)
                    for item_key in ("mode", "document_id", "close_after_probe")
                    if item_key in value
                }
        else:
            preview[key] = value
    return preview


def _finish(audit: dict[str, Any], output_dir: Path) -> None:
    audit["ok"] = all(bool(step.get("ok")) for step in audit.get("steps", []))
    audit_path = output_dir / "audit.json"
    _write_json(audit_path, audit)
    print(
        json.dumps(
            {
                "ok": audit["ok"],
                "artifact": str(audit_path),
                "steps": [
                    {
                        "name": step.get("name"),
                        "ok": step.get("ok"),
                        "preview": step.get("preview") or {"error": step.get("error")},
                    }
                    for step in audit.get("steps", [])
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
