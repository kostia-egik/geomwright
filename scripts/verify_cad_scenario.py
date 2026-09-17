from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.bridge_runner import BridgeRunner

from summarize_evidence import summarize


def _read_request(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("profile_request"), dict):
        raise ValueError("Request must be an object with profile_request")
    if not str(value.get("family") or "").strip():
        raise ValueError("Request must contain family")
    return value


def _document_id(result: dict[str, Any]) -> str:
    document = result.get("document") or {}
    value = document.get("runtime_id") or document.get("id")
    if not value:
        raise RuntimeError("CAD result does not contain an exact document id")
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or verify one managed CAD scenario with bounded output")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--save-to", type=Path)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--full-result", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    request = _read_request(args.request)
    execute = not args.plan_only
    adapter = KompasAdapter(BridgeRunner(require_visible_kompas=execute, timeout_seconds=args.timeout))
    result = adapter.create_managed_pulley(
        family=str(request["family"]),
        profile_request=dict(request["profile_request"]),
        name=str(request.get("name") or f"Geomwright acceptance {datetime.now():%Y%m%d-%H%M%S}"),
        top_edge_fillet_radius=request.get("top_edge_fillet_radius"),
        include_standard_top_edge_fillet=bool(request.get("include_standard_top_edge_fillet", True)),
        execute=execute,
        confirm_write=execute,
        visible=True,
    )

    if execute and args.save_to:
        args.save_to.parent.mkdir(parents=True, exist_ok=True)
        saved = adapter.save_document_as(
            str(args.save_to.resolve()), document_id=_document_id(result), close_after_save=False, strict=True,
        )
        result["final_save"] = saved
        reopened_id = str((saved.get("document") or {}).get("runtime_id") or saved.get("saved_as") or "")
        if reopened_id:
            result["reopened_inspection"] = adapter.inspect_managed_pulley(document_id=reopened_id)

    args.full_result.parent.mkdir(parents=True, exist_ok=True)
    args.full_result.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = summarize(result, [])
    compact["full_evidence"] = str(args.full_result)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(compact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": bool(result.get("success", result.get("ok"))),
        "stage": result.get("stage"),
        "summary": str(args.summary),
        "full_evidence": str(args.full_result),
        "artifact": str(args.save_to) if args.save_to else None,
    }, ensure_ascii=False))
    return 0 if result.get("success", result.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
