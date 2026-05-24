from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_VOLATILE_READBACK_KEYS = (
    "captured_at",
    "generated_at",
    "probe_id",
    "read_at",
    "revision",
    "session_id",
    "timestamp",
    "trace_id",
    "transient_id",
    "update_counter",
)


def diff_document_snapshots(
    before: dict[str, Any] | str | Path,
    after: dict[str, Any] | str | Path,
    *,
    max_items: int = 25,
    ignore_paths: list[str] | tuple[str, ...] | None = None,
    ignore_keys: list[str] | tuple[str, ...] | None = None,
    use_default_volatile_ignores: bool = False,
) -> dict[str, Any]:
    ignored_paths = {str(item) for item in (ignore_paths or []) if str(item)}
    ignored_keys = {str(item) for item in (ignore_keys or []) if str(item)}
    if use_default_volatile_ignores:
        ignored_keys.update(DEFAULT_VOLATILE_READBACK_KEYS)
    try:
        before_payload = _load_snapshot_input(before)
    except Exception as exc:
        return _failed_input_diff(
            "before_snapshot_loadable",
            exc,
            ignored_paths=ignored_paths,
            ignored_keys=ignored_keys,
            use_default_volatile_ignores=use_default_volatile_ignores,
        )
    try:
        after_payload = _load_snapshot_input(after)
    except Exception as exc:
        return _failed_input_diff(
            "after_snapshot_loadable",
            exc,
            ignored_paths=ignored_paths,
            ignored_keys=ignored_keys,
            use_default_volatile_ignores=use_default_volatile_ignores,
        )
    before_manifest = _extract_manifest(before_payload)
    after_manifest = _extract_manifest(after_payload)
    before_items = _items_by_identity(before_manifest)
    after_items = _items_by_identity(after_manifest)

    before_keys = set(before_items)
    after_keys = set(after_items)
    added_keys = sorted(after_keys - before_keys)
    removed_keys = sorted(before_keys - after_keys)
    common_keys = sorted(before_keys & after_keys)
    changed = [
        {
            "identity": key,
            "before": _entry_preview(before_items[key]),
            "after": _entry_preview(after_items[key]),
        }
        for key in common_keys
        if _entry_signature(before_items[key], ignored_paths, ignored_keys)
        != _entry_signature(after_items[key], ignored_paths, ignored_keys)
    ]

    checks = [
        _check("before_manifest_present", bool(before_manifest), True, bool(before_manifest)),
        _check("after_manifest_present", bool(after_manifest), True, bool(after_manifest)),
    ]
    failures = [item for item in checks if item.get("ok") is False]
    return {
        "ok": not failures,
        "status": "ok" if not failures else "failed",
        "summary": {
            "added_items": len(added_keys),
            "removed_items": len(removed_keys),
            "changed_items": len(changed),
            "before_items": len(before_items),
            "after_items": len(after_items),
        },
        "counts_delta": _counts_delta(before_manifest, after_manifest),
        "added": [_entry_preview(after_items[key]) for key in added_keys[:max_items]],
        "removed": [_entry_preview(before_items[key]) for key in removed_keys[:max_items]],
        "changed": changed[:max_items],
        "truncated": {
            "added": max(0, len(added_keys) - max_items),
            "removed": max(0, len(removed_keys) - max_items),
            "changed": max(0, len(changed) - max_items),
        },
        "ignored": {
            "paths": sorted(ignored_paths),
            "keys": sorted(ignored_keys),
            "default_volatile": bool(use_default_volatile_ignores),
        },
        "checks": checks,
        "failures": failures,
    }


def _load_snapshot_input(value: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    path = Path(value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Snapshot input must be a JSON object, got {type(payload).__name__}")
    return payload


def _failed_input_diff(
    check_name: str,
    error: BaseException,
    *,
    ignored_paths: set[str],
    ignored_keys: set[str],
    use_default_volatile_ignores: bool,
) -> dict[str, Any]:
    check = _check(check_name, False, True, f"{type(error).__name__}: {error}")
    return {
        "ok": False,
        "status": "failed",
        "summary": {
            "added_items": 0,
            "removed_items": 0,
            "changed_items": 0,
            "before_items": 0,
            "after_items": 0,
        },
        "counts_delta": {},
        "added": [],
        "removed": [],
        "changed": [],
        "truncated": {"added": 0, "removed": 0, "changed": 0},
        "ignored": {
            "paths": sorted(ignored_paths),
            "keys": sorted(ignored_keys),
            "default_volatile": bool(use_default_volatile_ignores),
        },
        "checks": [check],
        "failures": [check],
        "error": {
            "type": type(error).__name__,
            "message": str(error),
        },
    }


def _extract_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("manifest"), dict):
        return payload["manifest"]
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict) and isinstance(snapshot.get("manifest"), dict):
        return snapshot["manifest"]
    if isinstance(payload.get("item_index"), dict) and isinstance(payload.get("counts"), dict):
        return payload
    return {}


def _items_by_identity(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    item_index = manifest.get("item_index") if isinstance(manifest.get("item_index"), dict) else {}
    entries = item_index.get("entries") if isinstance(item_index.get("entries"), list) else []
    items: dict[str, dict[str, Any]] = {}
    for offset, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        key = _entry_identity(entry, offset)
        if key in items:
            key = _deduplicated_identity(key, entry, offset, items)
        items[key] = entry
    return items


def _entry_identity(entry: dict[str, Any], offset: int) -> str:
    for field in ("id", "reference", "path", "name"):
        if entry.get(field) not in (None, ""):
            return f"{field}:{entry[field]}"
    return f"entry:{offset}"


def _deduplicated_identity(
    base_key: str,
    entry: dict[str, Any],
    offset: int,
    existing: dict[str, dict[str, Any]],
) -> str:
    source = entry.get("source")
    source_index = entry.get("source_index")
    suffix_parts = [f"offset:{offset}"]
    if source not in (None, ""):
        suffix_parts.insert(0, f"source:{source}")
    if source_index not in (None, ""):
        suffix_parts.insert(1, f"source_index:{source_index}")
    key = f"{base_key}|" + "|".join(str(item) for item in suffix_parts)
    if key not in existing:
        return key
    counter = 2
    candidate = f"{key}|duplicate:{counter}"
    while candidate in existing:
        counter += 1
        candidate = f"{key}|duplicate:{counter}"
    return candidate


def _entry_signature(
    entry: dict[str, Any],
    ignore_paths: set[str] | None = None,
    ignore_keys: set[str] | None = None,
) -> tuple[tuple[str, Any], ...]:
    ignore_paths = ignore_paths or set()
    ignore_keys = ignore_keys or set()
    return tuple(
        sorted(
            (key, _jsonable_signature(value, key, ignore_paths, ignore_keys))
            for key, value in entry.items()
            if key not in {"source_index"} and key not in ignore_keys and key not in ignore_paths
        )
    )


def _jsonable_signature(value: Any, path: str, ignore_paths: set[str], ignore_keys: set[str]) -> Any:
    if path in ignore_paths:
        return None
    if isinstance(value, dict):
        return tuple(
            sorted(
                (str(key), _jsonable_signature(item, f"{path}.{key}", ignore_paths, ignore_keys))
                for key, item in value.items()
                if str(key) not in ignore_keys and f"{path}.{key}" not in ignore_paths
            )
        )
    if isinstance(value, list):
        return tuple(
            _jsonable_signature(item, f"{path}.{offset}", ignore_paths, ignore_keys)
            for offset, item in enumerate(value)
            if f"{path}.{offset}" not in ignore_paths
        )
    return value


def _entry_preview(entry: dict[str, Any]) -> dict[str, Any]:
    preview = {
        key: entry.get(key)
        for key in (
            "id",
            "name",
            "type",
            "role",
            "reference",
            "path",
            "source",
            "parent_id",
            "depth",
            "children_count",
            "hidden",
            "visible",
            "active",
            "changed",
        )
        if entry.get(key) is not None
    }
    extra_keys = sorted(str(key) for key in entry if key not in preview and key != "source_index")
    if extra_keys:
        preview["extra_keys"] = extra_keys[:12]
    return preview


def _counts_delta(before_manifest: dict[str, Any], after_manifest: dict[str, Any]) -> dict[str, Any]:
    before_counts = before_manifest.get("counts") if isinstance(before_manifest.get("counts"), dict) else {}
    after_counts = after_manifest.get("counts") if isinstance(after_manifest.get("counts"), dict) else {}
    keys = sorted(set(before_counts) | set(after_counts))
    delta: dict[str, Any] = {}
    for key in keys:
        before_value = before_counts.get(key, 0)
        after_value = after_counts.get(key, 0)
        if isinstance(before_value, (int, float)) and isinstance(after_value, (int, float)):
            change = after_value - before_value
            if change:
                delta[key] = {"before": before_value, "after": after_value, "delta": change}
    return delta


def _check(name: str, ok: bool, expected: Any, actual: Any) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "expected": expected, "actual": actual}
