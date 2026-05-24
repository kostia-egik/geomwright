from __future__ import annotations

from pathlib import Path
from typing import Any

from .document_preflight import preflight_document_context
from .document_probe import probe_document_readback
from .document_readback import KompasDocumentReader
from .operation_executor import execute_primitive_operation


def capture_document_snapshot(
    adapter: KompasDocumentReader,
    *,
    model_path: str | None = None,
    document_id: str | None = None,
    output_path: str | Path | None = None,
    require_active_document: bool = True,
    visible: bool = False,
    read_only: bool = True,
    close_after_probe: bool = True,
    include_manifest: bool = False,
    stage: str = "document_snapshot",
) -> dict[str, Any]:
    preflight = None
    if not model_path:
        preflight = preflight_document_context(
            adapter,
            document_id=document_id,
            require_active_document=require_active_document,
        )

    snapshot: dict[str, Any] | None = None
    artifacts = {"snapshot": str(output_path)} if output_path else None

    def run_operation() -> dict[str, Any]:
        nonlocal snapshot
        probe = probe_document_readback(
            adapter,
            model_path=model_path,
            document_id=document_id,
            output_path=output_path,
            visible=visible,
            read_only=read_only,
            close_after_probe=close_after_probe,
            stage=f"{stage}_probe",
        )
        snapshot = _snapshot_from_probe(probe, include_manifest=include_manifest)
        return snapshot

    envelope = execute_primitive_operation(
        "capture_document_snapshot",
        run_operation,
        preflight=preflight,
        artifacts=artifacts,
        stage=stage,
        require_result=True,
    )
    if snapshot is not None:
        envelope["snapshot"] = snapshot
    return envelope


def _snapshot_from_probe(probe: dict[str, Any], *, include_manifest: bool) -> dict[str, Any]:
    manifest = probe.get("manifest") if isinstance(probe.get("manifest"), dict) else {}
    item_index = manifest.get("item_index") if isinstance(manifest.get("item_index"), dict) else {}
    snapshot = {
        "ok": bool(probe.get("ok")),
        "probe": probe.get("probe") if isinstance(probe.get("probe"), dict) else {},
        "document": manifest.get("document") if isinstance(manifest.get("document"), dict) else {},
        "summary": probe.get("summary") if isinstance(probe.get("summary"), dict) else {},
        "counts": manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {},
        "index_counts": item_index.get("counts") if isinstance(item_index.get("counts"), dict) else {},
        "tree_root": manifest.get("tree_root") if isinstance(manifest.get("tree_root"), dict) else {},
        "artifact": probe.get("artifact") if isinstance(probe.get("artifact"), dict) else None,
        "steps": _failure_steps(manifest),
    }
    if include_manifest:
        snapshot["manifest"] = manifest
    return snapshot


def _failure_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    failures = manifest.get("failures")
    if not isinstance(failures, list):
        return []
    steps: list[dict[str, Any]] = []
    for item in failures:
        if not isinstance(item, dict):
            continue
        steps.append(
            {
                "step": str(item.get("name") or "readback"),
                "ok": False,
                "expected": item.get("expected"),
                "actual": item.get("actual"),
            }
        )
    return steps
