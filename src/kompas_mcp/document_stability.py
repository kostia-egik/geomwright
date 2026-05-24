from __future__ import annotations

from pathlib import Path
from typing import Any

from .document_readback import KompasDocumentReader
from .document_snapshot import capture_document_snapshot
from .document_snapshot_verify import verify_document_snapshot_delta
from .operation_result import normalize_operation_result


def verify_document_readback_stability(
    adapter: KompasDocumentReader,
    *,
    document_id: str | None = None,
    before_output_path: str | Path | None = None,
    after_output_path: str | Path | None = None,
    require_active_document: bool = True,
    max_items: int = 25,
    include_manifests: bool = False,
    ignore_paths: list[str] | tuple[str, ...] | None = None,
    ignore_keys: list[str] | tuple[str, ...] | None = None,
    use_default_volatile_ignores: bool = False,
) -> dict[str, Any]:
    """Capture two readback snapshots and verify that the document view is stable."""

    before = capture_document_snapshot(
        adapter,
        document_id=document_id,
        output_path=before_output_path,
        require_active_document=require_active_document,
        include_manifest=True,
        stage="document_readback_stability_before",
    )
    if before.get("ok") is False:
        return _stability_envelope(before=before, after=None, verification=None, include_manifests=include_manifests)

    after = capture_document_snapshot(
        adapter,
        document_id=document_id,
        output_path=after_output_path,
        require_active_document=require_active_document,
        include_manifest=True,
        stage="document_readback_stability_after",
    )

    verification = None
    if after.get("ok") is not False:
        verification = verify_document_snapshot_delta(
            "verify_document_readback_stability",
            before=before,
            after=after,
            expected_added=0,
            expected_removed=0,
            expected_changed=0,
            require_no_removed=True,
            require_no_changed=True,
            max_added=0,
            max_removed=0,
            max_changed=0,
            max_items=max_items,
            ignore_paths=ignore_paths,
            ignore_keys=ignore_keys,
            use_default_volatile_ignores=use_default_volatile_ignores,
        )
    return _stability_envelope(before=before, after=after, verification=verification, include_manifests=include_manifests)


def _stability_envelope(
    *,
    before: dict[str, Any],
    after: dict[str, Any] | None,
    verification: dict[str, Any] | None,
    include_manifests: bool,
) -> dict[str, Any]:
    checks = [
        {"name": "before_snapshot_ok", "ok": bool(before.get("ok")), "expected": True, "actual": bool(before.get("ok"))},
    ]
    if after is not None:
        checks.append({"name": "after_snapshot_ok", "ok": bool(after.get("ok")), "expected": True, "actual": bool(after.get("ok"))})
        checks.extend(_prefixed_failures("after_snapshot", after))
    else:
        checks.append({"name": "after_snapshot_ran", "ok": False, "expected": True, "actual": False})
    checks.extend(_prefixed_failures("before_snapshot", before))
    if verification is not None:
        checks.append(
            {
                "name": "readback_stability_ok",
                "ok": bool(verification.get("ok")),
                "expected": True,
                "actual": bool(verification.get("ok")),
            }
        )
        checks.extend(_prefixed_failures("stability", verification))

    artifacts = _artifact_paths(before, after)
    result = {
        "ok": bool(before.get("ok")) and bool(after and after.get("ok")) and bool(verification and verification.get("ok")),
        "summary": verification.get("delta", {}).get("summary", {}) if isinstance(verification, dict) else {},
    }
    envelope = normalize_operation_result(
        "verify_document_readback_stability",
        result=result,
        checks=checks,
        artifacts=artifacts,
        stage="document_readback_stability",
        require_result=False,
    )
    envelope["snapshots"] = {
        "before": _snapshot_preview(before, include_manifest=include_manifests),
        "after": _snapshot_preview(after, include_manifest=include_manifests),
    }
    envelope["delta"] = verification.get("delta") if isinstance(verification, dict) else {}
    return envelope


def _artifact_paths(before: dict[str, Any], after: dict[str, Any] | None) -> dict[str, str]:
    paths: dict[str, str] = {}
    for role, payload in (("before_snapshot", before), ("after_snapshot", after)):
        artifact = _snapshot_payload(payload).get("artifact") if isinstance(payload, dict) else None
        if isinstance(artifact, dict) and artifact.get("path"):
            paths[role] = str(artifact["path"])
    return paths


def _snapshot_preview(snapshot: dict[str, Any] | None, *, include_manifest: bool) -> dict[str, Any]:
    payload = _snapshot_payload(snapshot)
    preview = {
        "ok": bool(snapshot.get("ok")) if isinstance(snapshot, dict) else False,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "counts": payload.get("counts") if isinstance(payload.get("counts"), dict) else {},
        "index_counts": payload.get("index_counts") if isinstance(payload.get("index_counts"), dict) else {},
        "artifact": payload.get("artifact") if isinstance(payload.get("artifact"), dict) else None,
    }
    if include_manifest and isinstance(payload.get("manifest"), dict):
        preview["manifest"] = payload["manifest"]
    return preview


def _snapshot_payload(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    return snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else {}


def _prefixed_failures(prefix: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    rows: list[dict[str, Any]] = []
    for item in failures:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["name"] = f"{prefix}:{row.get('name') or 'failure'}"
        rows.append(row)
    return rows
