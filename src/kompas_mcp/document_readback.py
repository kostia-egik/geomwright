from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Callable, Protocol


DocumentReadbackCallable = Callable[[str], dict[str, Any]]


class KompasDocumentReader(Protocol):
    def open_document(self, path: str, *, visible: bool, read_only: bool) -> dict[str, Any]: ...

    def get_document_tree(self, *, document_id: str) -> dict[str, Any]: ...

    def get_items(self, *, document_id: str) -> dict[str, Any]: ...

    def list_documents(self) -> dict[str, Any]: ...

    def close_document(self, *, document_id: str, save: bool) -> dict[str, Any]: ...


def readback_saved_document(adapter: KompasDocumentReader, model_path: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    open_payload = _capture_readback_payload(
        "open_document",
        lambda: adapter.open_document(model_path, visible=False, read_only=True),
    )
    payload["open_document"] = open_payload
    document_id = _readback_document_id(open_payload)
    try:
        payload["document_tree"] = _capture_readback_payload(
            "document_tree",
            lambda: adapter.get_document_tree(document_id=document_id),
        )
        payload["items"] = _capture_readback_payload("items", lambda: adapter.get_items(document_id=document_id))
        payload["list_documents"] = _capture_readback_payload("list_documents", adapter.list_documents)
    finally:
        if document_id:
            payload["close_document"] = _capture_readback_payload(
                "close_document",
                lambda: adapter.close_document(document_id=document_id, save=False),
            )
    return payload


def _capture_readback_payload(name: str, callback: Any) -> dict[str, Any]:
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


def _readback_document_id(payload: dict[str, Any]) -> str:
    document = payload.get("document") if isinstance(payload.get("document"), dict) else {}
    return str(document.get("id") or "")


def run_document_readback(
    model_path: str | Path,
    document_readback: DocumentReadbackCallable,
    *,
    stage: str,
) -> dict[str, Any]:
    model = Path(model_path)
    checks: list[dict[str, Any]] = [
        {
            "name": "model_path_exists",
            "ok": model.exists(),
            "expected": True,
            "actual": model.exists(),
            "details": {"path": str(model)},
        }
    ]
    try:
        payload = document_readback(str(model))
        checks.append({"name": "readback_callback", "ok": True, "expected": True, "actual": True})
    except Exception as exc:
        error_payload = _build_exception_payload(exc, stage=stage)
        checks.append(
            {
                "name": "readback_callback",
                "ok": False,
                "expected": True,
                "actual": False,
                "details": error_payload,
            }
        )
        return {
            "stage": stage,
            "ok": False,
            "model_path": str(model),
            "checks": checks,
            "counts": {"documents": 0, "items": 0, "tree_nodes": 0},
            "readback": {},
            "error": error_payload,
        }

    return normalize_document_readback(model, payload, checks=checks, stage=stage)


def normalize_document_readback(
    model_path: str | Path,
    payload: dict[str, Any],
    *,
    checks: list[dict[str, Any]] | None = None,
    stage: str,
) -> dict[str, Any]:
    model = Path(model_path)
    normalized_checks = list(checks or [])
    open_payload = payload.get("open_document") if isinstance(payload.get("open_document"), dict) else {}
    tree_payload = payload.get("document_tree") if isinstance(payload.get("document_tree"), dict) else {}
    items_payload = payload.get("items") if isinstance(payload.get("items"), dict) else {}
    list_payload = payload.get("list_documents") if isinstance(payload.get("list_documents"), dict) else {}
    close_payload = payload.get("close_document") if isinstance(payload.get("close_document"), dict) else {}

    document = open_payload.get("document") or tree_payload.get("document") or {}
    document_path = str(document.get("path") or document.get("id") or "")
    path_matches = bool(document_path) and Path(document_path).name.lower() == model.name.lower()
    tree = tree_payload.get("tree") if isinstance(tree_payload.get("tree"), dict) else {}
    items = items_payload.get("items") if isinstance(items_payload.get("items"), list) else []
    documents = list_payload.get("documents") if isinstance(list_payload.get("documents"), list) else []
    tree_nodes = count_tree_nodes(tree)

    normalized_checks.extend(
        [
            {
                "name": "open_document",
                "ok": bool(open_payload.get("document")),
                "expected": True,
                "actual": bool(open_payload.get("document")),
            },
            {
                "name": "document_path_matches_model_name",
                "ok": path_matches,
                "expected": model.name,
                "actual": document_path,
            },
            {
                "name": "document_tree",
                "ok": bool(tree),
                "expected": True,
                "actual": bool(tree),
            },
            {
                "name": "tree_or_items_non_empty",
                "ok": tree_nodes > 0 or len(items) > 0,
                "expected": {">": 0},
                "actual": {"tree_nodes": tree_nodes, "items": len(items)},
            },
            {
                "name": "close_document",
                "ok": close_payload.get("closed") is True if close_payload else True,
                "expected": True,
                "actual": close_payload.get("closed") if close_payload else "not_requested",
            },
        ]
    )
    failures = [check for check in normalized_checks if not check.get("ok")]
    return {
        "stage": stage,
        "ok": not failures,
        "model_path": str(model),
        "document": document,
        "checks": normalized_checks,
        "failures": failures,
        "counts": {"documents": len(documents), "items": len(items), "tree_nodes": tree_nodes},
        "readback": payload,
    }


def build_document_readback_manifest(
    readback_report: dict[str, Any] | None,
    *,
    stage: str = "com_readback_manifest",
) -> dict[str, Any]:
    report = readback_report or {}
    readback = report.get("readback") if isinstance(report.get("readback"), dict) else {}
    open_payload = readback.get("open_document") if isinstance(readback.get("open_document"), dict) else {}
    tree_payload = readback.get("document_tree") if isinstance(readback.get("document_tree"), dict) else {}
    items_payload = readback.get("items") if isinstance(readback.get("items"), dict) else {}
    list_payload = readback.get("list_documents") if isinstance(readback.get("list_documents"), dict) else {}
    close_payload = readback.get("close_document") if isinstance(readback.get("close_document"), dict) else {}

    document = _compact_document(report.get("document") or open_payload.get("document") or {})
    tree = tree_payload.get("tree") if isinstance(tree_payload.get("tree"), dict) else {}
    tree_nodes = _flatten_tree(tree)
    items = [_compact_item(item) for item in items_payload.get("items", []) if isinstance(item, dict)]
    documents = [_compact_document(item) for item in list_payload.get("documents", []) if isinstance(item, dict)]
    failures = [item for item in report.get("failures", []) if isinstance(item, dict)]
    checks = [item for item in report.get("checks", []) if isinstance(item, dict)]
    item_types = _count_by_key(items, "type")
    item_index = build_document_item_index(tree_nodes=tree_nodes, items=items)

    opened = bool(open_payload.get("document"))
    closed = close_payload.get("closed") is True if close_payload else None
    ok = bool(report.get("ok")) and opened and (closed is not False)
    return {
        "stage": stage,
        "ok": ok,
        "model_path": report.get("model_path"),
        "document": document,
        "open": {
            "ok": opened,
            "visible": open_payload.get("visible"),
            "read_only": open_payload.get("read_only"),
            "attempt_count": len(open_payload.get("open_attempts") or []),
        },
        "close": {
            "ok": closed,
            "closed": close_payload.get("closed") if close_payload else None,
            "save": close_payload.get("save") if close_payload else None,
        },
        "counts": {
            "documents": len(documents),
            "items": len(items),
            "tree_nodes": len(tree_nodes),
            "checks": len(checks),
            "failures": len(failures),
            "item_types": len(item_types),
            "indexed_items": item_index["counts"]["entries"],
            "indexed_ids": item_index["counts"]["ids"],
            "duplicate_ids": item_index["counts"]["duplicate_ids"],
            "same_source_duplicate_ids": item_index["counts"]["same_source_duplicate_ids"],
        },
        "tree_root": _compact_item(tree) if tree else {},
        "tree_nodes": tree_nodes,
        "items": items,
        "item_index": item_index,
        "item_types": item_types,
        "documents": documents,
        "failures": failures,
    }


def build_document_item_index(
    *,
    tree_nodes: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for source, source_items in (("tree", tree_nodes), ("items", items)):
        for source_index, item in enumerate(source_items):
            if not isinstance(item, dict):
                continue
            entry = {
                key: item.get(key)
                for key in (
                    "id",
                    "name",
                    "type",
                    "role",
                    "reference",
                    "path",
                    "parent_id",
                    "parent_path",
                    "hidden",
                    "visible",
                    "active",
                    "changed",
                    "depth",
                    "children_count",
                )
                if item.get(key) is not None
            }
            for key, value in item.items():
                if key not in entry and key not in {"source", "source_index"}:
                    entry[key] = value
            entry["source"] = source
            entry["source_index"] = source_index
            entries.append(entry)

    indexes = {
        "by_id": _build_value_index(entries, "id"),
        "by_name": _build_value_index(entries, "name"),
        "by_type": _build_value_index(entries, "type"),
        "by_role": _build_value_index(entries, "role"),
        "by_reference": _build_value_index(entries, "reference"),
        "by_path": _build_value_index(entries, "path"),
        "by_parent_id": _build_value_index(entries, "parent_id"),
        "by_parent_path": _build_value_index(entries, "parent_path"),
        "by_source": _build_value_index(entries, "source"),
        "by_hidden": _build_value_index(entries, "hidden"),
        "by_visible": _build_value_index(entries, "visible"),
        "by_active": _build_value_index(entries, "active"),
        "by_changed": _build_value_index(entries, "changed"),
        "by_depth": _build_value_index(entries, "depth"),
        "by_children_count": _build_value_index(entries, "children_count"),
    }
    duplicate_ids = {
        key: refs
        for key, refs in indexes["by_id"].items()
        if len(refs) > 1
    }
    same_source_duplicate_ids = {
        key: refs
        for key, refs in duplicate_ids.items()
        if _has_same_source_duplicate(entries, refs)
    }
    return {
        "counts": {
            "entries": len(entries),
            "ids": len(indexes["by_id"]),
            "names": len(indexes["by_name"]),
            "types": len(indexes["by_type"]),
            "roles": len(indexes["by_role"]),
            "references": len(indexes["by_reference"]),
            "paths": len(indexes["by_path"]),
            "parent_ids": len(indexes["by_parent_id"]),
            "parent_paths": len(indexes["by_parent_path"]),
            "sources": len(indexes["by_source"]),
            "hidden_states": len(indexes["by_hidden"]),
            "visible_states": len(indexes["by_visible"]),
            "active_states": len(indexes["by_active"]),
            "changed_states": len(indexes["by_changed"]),
            "depths": len(indexes["by_depth"]),
            "children_counts": len(indexes["by_children_count"]),
            "duplicate_ids": len(duplicate_ids),
            "same_source_duplicate_ids": len(same_source_duplicate_ids),
        },
        "entries": entries,
        "by_id": indexes["by_id"],
        "by_name": indexes["by_name"],
        "by_type": indexes["by_type"],
        "by_role": indexes["by_role"],
        "by_reference": indexes["by_reference"],
        "by_path": indexes["by_path"],
        "by_parent_id": indexes["by_parent_id"],
        "by_parent_path": indexes["by_parent_path"],
        "by_source": indexes["by_source"],
        "by_hidden": indexes["by_hidden"],
        "by_visible": indexes["by_visible"],
        "by_active": indexes["by_active"],
        "by_changed": indexes["by_changed"],
        "by_depth": indexes["by_depth"],
        "by_children_count": indexes["by_children_count"],
        "duplicate_ids": duplicate_ids,
        "same_source_duplicate_ids": same_source_duplicate_ids,
    }


def find_document_items(
    item_index: dict[str, Any],
    *,
    item_id: str | None = None,
    name: str | None = None,
    item_type: str | None = None,
    role: str | None = None,
    reference: str | int | None = None,
    path: str | None = None,
    parent_id: str | None = None,
    parent_path: str | None = None,
    source: str | None = None,
    hidden: bool | None = None,
    visible: bool | None = None,
    active: bool | None = None,
    changed: bool | None = None,
    depth: int | None = None,
    children_count: int | None = None,
    item_id_contains: str | None = None,
    name_contains: str | None = None,
    item_type_contains: str | None = None,
    role_contains: str | None = None,
    reference_contains: str | None = None,
    path_contains: str | None = None,
    parent_id_contains: str | None = None,
    parent_path_contains: str | None = None,
    source_contains: str | None = None,
    field_equals: dict[str, Any] | None = None,
    field_contains: dict[str, Any] | None = None,
    field_has: dict[str, Any] | None = None,
    field_has_contains: dict[str, Any] | None = None,
    field_exists: Any = None,
    field_missing: Any = None,
    numeric_fields: dict[str, Any] | None = None,
    numeric_tolerance: float = 0.0,
) -> list[dict[str, Any]]:
    if not isinstance(item_index, dict):
        return []
    entries = [item for item in item_index.get("entries", []) if isinstance(item, dict)]
    try:
        resolved_numeric_tolerance = float(numeric_tolerance or 0.0)
    except (TypeError, ValueError):
        return []
    selected: set[int] | None = None
    lookups = (
        ("by_id", item_id),
        ("by_name", name),
        ("by_type", item_type),
        ("by_role", role),
        ("by_reference", reference),
        ("by_path", path),
        ("by_parent_id", parent_id),
        ("by_parent_path", parent_path),
        ("by_source", source),
        ("by_hidden", hidden),
        ("by_visible", visible),
        ("by_active", active),
        ("by_changed", changed),
        ("by_depth", depth),
        ("by_children_count", children_count),
    )
    for index_name, value in lookups:
        if value is None:
            continue
        index = item_index.get(index_name, {})
        refs = set(index.get(_index_key(value), []) if isinstance(index, dict) else [])
        selected = refs if selected is None else selected & refs
    if selected is None:
        matches = entries
    else:
        matches = [entries[index] for index in sorted(selected) if 0 <= index < len(entries)]
    contains_filters = (
        ("id", item_id_contains),
        ("name", name_contains),
        ("type", item_type_contains),
        ("role", role_contains),
        ("reference", reference_contains),
        ("path", path_contains),
        ("parent_id", parent_id_contains),
        ("parent_path", parent_path_contains),
        ("source", source_contains),
    )
    for key, needle in contains_filters:
        if needle is None:
            continue
        needle_key = _index_key(needle)
        matches = [item for item in matches if needle_key in _index_key(item.get(key, ""))]
    if field_equals is not None:
        if not isinstance(field_equals, dict):
            return []
        matches = [item for item in matches if _field_equals_match(item, field_equals)]
    if field_contains is not None:
        if not isinstance(field_contains, dict):
            return []
        matches = [item for item in matches if _field_contains_match(item, field_contains)]
    if field_has is not None:
        if not isinstance(field_has, dict):
            return []
        matches = [item for item in matches if _field_has_match(item, field_has)]
    if field_has_contains is not None:
        if not isinstance(field_has_contains, dict):
            return []
        matches = [item for item in matches if _field_has_contains_match(item, field_has_contains)]
    if field_exists:
        matches = [item for item in matches if _field_exists_match(item, field_exists)]
    if field_missing:
        matches = [item for item in matches if _field_missing_match(item, field_missing)]
    if numeric_fields is not None:
        if not isinstance(numeric_fields, dict):
            return []
        matches = [
            item
            for item in matches
            if _numeric_fields_match(item, numeric_fields, default_tolerance=resolved_numeric_tolerance)
        ]
    return matches


def count_tree_nodes(node: Any) -> int:
    if not isinstance(node, dict) or not node:
        return 0
    children = node.get("children")
    child_count = sum(count_tree_nodes(child) for child in children) if isinstance(children, list) else 0
    return 1 + child_count


def _flatten_tree(
    node: Any,
    *,
    depth: int = 0,
    parent_id: str | None = None,
    parent_path: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(node, dict) or not node:
        return []
    children = node.get("children") if isinstance(node.get("children"), list) else []
    current = _compact_item(node)
    current["depth"] = depth
    current["children_count"] = len(children)
    if parent_id is not None:
        current["parent_id"] = parent_id
    if parent_path is not None:
        current["parent_path"] = parent_path
    current_id = str(current.get("id") or "") or None
    current_path = str(current.get("path") or "") or parent_path
    rows = [current]
    for child in children:
        rows.extend(_flatten_tree(child, depth=depth + 1, parent_id=current_id, parent_path=current_path))
    return rows


def _compact_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        return {}
    return {
        key: document.get(key)
        for key in ("id", "name", "path", "active", "changed", "type", "kind")
        if key in document
    }


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    item_type = item.get("type") or item.get("kind") or item.get("class") or item.get("class_name")
    compact = {
        key: value
        for key, value in {
            "id": item.get("id"),
            "name": item.get("name"),
            "type": item_type or "unknown",
            "role": item.get("role"),
            "hidden": item.get("hidden"),
            "visible": item.get("visible"),
            "active": item.get("active"),
            "changed": item.get("changed"),
            "reference": item.get("reference"),
            "path": item.get("path"),
        }.items()
        if value is not None
    }
    base_keys = {
        "id",
        "name",
        "type",
        "kind",
        "class",
        "class_name",
        "role",
        "hidden",
        "visible",
        "active",
        "changed",
        "reference",
        "path",
        "children",
    }
    nested_keys = {
        "properties",
        "attributes",
        "parameters",
        "metrics",
        "bounds",
        "bbox",
        "geometry",
        "position",
        "origin",
        "size",
    }
    for key, value in item.items():
        if key in base_keys:
            continue
        if _is_readback_scalar(value):
            compact[key] = value
            continue
        if key in nested_keys:
            nested = _compact_readback_value(value)
            if nested not in ({}, [], None):
                compact[key] = nested
    return compact


def _count_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _build_value_index(entries: list[dict[str, Any]], key: str) -> dict[str, list[int]]:
    index: dict[str, list[int]] = {}
    for entry_index, entry in enumerate(entries):
        value = entry.get(key)
        if value is None:
            continue
        index.setdefault(_index_key(value), []).append(entry_index)
    return dict(sorted(index.items()))


def _index_key(value: Any) -> str:
    return str(value).strip().casefold()


def _compact_readback_value(value: Any) -> Any:
    if _is_readback_scalar(value):
        return value
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in value.items():
            compact_item = _compact_readback_value(item)
            if compact_item not in ({}, [], None):
                compact[str(key)] = compact_item
        return compact
    if isinstance(value, (list, tuple)):
        compact_items = [_compact_readback_value(item) for item in value]
        return [item for item in compact_items if item not in ({}, [], None)]
    return None


def _is_readback_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) and value is not None


def _numeric_fields_match(
    item: dict[str, Any],
    numeric_fields: dict[str, Any],
    *,
    default_tolerance: float,
) -> bool:
    for field_path, expected in numeric_fields.items():
        actual = _get_dotted_value(item, str(field_path))
        if not _numeric_value_matches(actual, expected, default_tolerance=default_tolerance):
            return False
    return True


def _field_equals_match(item: dict[str, Any], field_equals: dict[str, Any]) -> bool:
    for field_path, expected in field_equals.items():
        actual = _get_dotted_value(item, str(field_path))
        if _index_key(actual) != _index_key(expected):
            return False
    return True


def _field_contains_match(item: dict[str, Any], field_contains: dict[str, Any]) -> bool:
    for field_path, needle in field_contains.items():
        actual = _get_dotted_value(item, str(field_path))
        if actual is None or _index_key(needle) not in _index_key(actual):
            return False
    return True


def _field_has_match(item: dict[str, Any], field_has: dict[str, Any]) -> bool:
    for field_path, expected in field_has.items():
        actual_values = [_index_key(value) for value in _iter_field_values(_get_dotted_value(item, str(field_path)))]
        expected_values = list(expected) if isinstance(expected, (list, tuple, set)) else [expected]
        if any(_index_key(value) not in actual_values for value in expected_values):
            return False
    return True


def _field_has_contains_match(item: dict[str, Any], field_has_contains: dict[str, Any]) -> bool:
    for field_path, expected in field_has_contains.items():
        actual_values = [_index_key(value) for value in _iter_field_values(_get_dotted_value(item, str(field_path)))]
        needles = list(expected) if isinstance(expected, (list, tuple, set)) else [expected]
        if any(not any(_index_key(needle) in value for value in actual_values) for needle in needles):
            return False
    return True


def _field_exists_match(item: dict[str, Any], field_exists: Any) -> bool:
    return all(_dotted_path_exists(item, str(field_path)) for field_path in _field_path_list(field_exists))


def _field_missing_match(item: dict[str, Any], field_missing: Any) -> bool:
    return all(not _dotted_path_exists(item, str(field_path)) for field_path in _field_path_list(field_missing))


def _field_path_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _numeric_value_matches(actual: Any, expected: Any, *, default_tolerance: float) -> bool:
    tolerance = default_tolerance
    expected_value = expected
    if isinstance(expected, dict):
        expected_value = expected.get("expected", expected.get("value"))
        try:
            tolerance = float(expected.get("tolerance", tolerance))
        except (TypeError, ValueError):
            return False
    actual_float = _as_float(actual)
    expected_float = _as_float(expected_value)
    if actual_float is None or expected_float is None:
        return False
    return abs(actual_float - expected_float) <= tolerance


def _get_dotted_value(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


def _dotted_path_exists(payload: Any, path: str) -> bool:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return False
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if not 0 <= index < len(current):
                return False
            current = current[index]
        else:
            return False
    return True


def _iter_field_values(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        values: list[Any] = []
        for item in value:
            values.extend(_iter_field_values(item))
        return values
    if value is None:
        return []
    return [value]


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_same_source_duplicate(entries: list[dict[str, Any]], refs: list[int]) -> bool:
    sources: set[str] = set()
    for ref in refs:
        if not 0 <= ref < len(entries):
            continue
        source = str(entries[ref].get("source") or "")
        if source in sources:
            return True
        sources.add(source)
    return False


def _build_exception_payload(exc: Exception, *, stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "ok": False,
        "error_type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }
