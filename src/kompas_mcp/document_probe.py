from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .document_readback import KompasDocumentReader
from .document_readback import build_document_readback_manifest
from .document_readback import normalize_document_readback


def probe_document_readback(
    adapter: KompasDocumentReader,
    *,
    model_path: str | None = None,
    document_id: str | None = None,
    output_path: str | Path | None = None,
    visible: bool = False,
    read_only: bool = True,
    close_after_probe: bool = True,
    stage: str = "com_readback_probe",
) -> dict[str, Any]:
    if model_path and document_id:
        raise ValueError("model_path and document_id are mutually exclusive")

    payload: dict[str, Any] = {}
    opened_document_id = ""
    if model_path:
        open_payload = _capture_adapter_payload(
            "open_document",
            lambda: adapter.open_document(model_path, visible=visible, read_only=read_only),
        )
        payload["open_document"] = open_payload
        opened_document_id = _payload_document_id(open_payload)
        selected_document_id = opened_document_id
    else:
        selected_document_id = document_id

    try:
        tree_payload = _capture_adapter_payload("document_tree", lambda: adapter.get_document_tree(document_id=selected_document_id))
        payload["document_tree"] = tree_payload
        document = tree_payload.get("document") if isinstance(tree_payload.get("document"), dict) else {}
        if not payload.get("open_document"):
            payload["open_document"] = {
                "document": document,
                "visible": None,
                "read_only": None,
                "probe_source": "active_document",
            }
        active_document_id = str(document.get("id") or selected_document_id or "")
        payload["items"] = _capture_adapter_payload(
            "items",
            lambda: adapter.get_items(document_id=active_document_id or selected_document_id),
        )
        payload["list_documents"] = _capture_adapter_payload("list_documents", adapter.list_documents)
    finally:
        if close_after_probe and opened_document_id:
            payload["close_document"] = _capture_adapter_payload(
                "close_document",
                lambda: adapter.close_document(document_id=opened_document_id, save=False),
            )

    report_path = _probe_model_path(model_path=model_path, payload=payload)
    report = normalize_document_readback(report_path, payload, stage=stage)
    manifest = build_document_readback_manifest(report, stage=f"{stage}_manifest")
    result = {
        "stage": stage,
        "ok": bool(report.get("ok")) and bool(manifest.get("ok")),
        "probe": {
            "mode": "open_file" if model_path else "active_document",
            "model_path": model_path,
            "document_id": document_id,
            "close_after_probe": close_after_probe,
        },
        "summary": {
            "documents": manifest["counts"]["documents"],
            "items": manifest["counts"]["items"],
            "tree_nodes": manifest["counts"]["tree_nodes"],
            "indexed_items": manifest["counts"]["indexed_items"],
            "failures": manifest["counts"]["failures"],
        },
        "manifest": manifest,
    }
    if output_path:
        artifact = _write_probe_artifact(output_path, result)
        result["artifact"] = artifact
        if not artifact["written"]:
            result["ok"] = False
            failure = {
                "name": "artifact_write",
                "ok": False,
                "expected": True,
                "actual": False,
                "details": artifact,
            }
            result.setdefault("checks", []).append(failure)
            result.setdefault("failures", []).append(failure)
            result["summary"]["failures"] = int(result["summary"].get("failures") or 0) + 1
    return result


def _write_probe_artifact(output_path: str | Path, result: dict[str, Any]) -> dict[str, Any]:
    artifact_path = Path(output_path)
    try:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        return {
            "path": str(artifact_path),
            "written": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    return {"path": str(artifact_path), "written": True}


def _probe_model_path(*, model_path: str | None, payload: dict[str, Any]) -> str:
    if model_path:
        return model_path
    tree_payload = payload.get("document_tree") if isinstance(payload.get("document_tree"), dict) else {}
    document = tree_payload.get("document") if isinstance(tree_payload.get("document"), dict) else {}
    return str(document.get("path") or document.get("name") or document.get("id") or "active_document")


def _capture_adapter_payload(name: str, callback: Any) -> dict[str, Any]:
    try:
        payload = callback()
    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "source": name,
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error_type": "TypeError",
            "message": f"{name} returned {type(payload).__name__}, expected dict",
            "actual_type": type(payload).__name__,
            "source": name,
        }
    return payload


def _payload_document_id(payload: dict[str, Any]) -> str:
    document = payload.get("document") if isinstance(payload.get("document"), dict) else {}
    return str(document.get("id") or "")
