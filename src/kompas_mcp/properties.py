from __future__ import annotations

from typing import Any

from .analyzers import flatten_tree

WRITABLE_FIELDS = ("name", "designation", "material")
READABLE_FIELDS = (
    "name",
    "designation",
    "material",
    "mass",
    "volume",
    "density",
    "comment",
    "title",
    "kind",
    "source_path",
)


def _snapshot(item: dict[str, Any]) -> dict[str, Any]:
    explicit_title = (item.get("title") or "").strip()
    fallback_title = (item.get("name") or "").strip()
    return {
        "item_id": item["id"],
        "kind": item.get("kind"),
        "name": item.get("name") or "",
        "designation": item.get("designation") or "",
        "material": item.get("material") or "",
        "mass": item.get("mass"),
        "volume": item.get("volume"),
        "density": item.get("density"),
        "comment": item.get("comment") or "",
        "title": explicit_title or fallback_title,
        "title_source": "title" if explicit_title else "name",
        "source_path": item.get("source_path") or "",
        "supported_writable_fields": list(WRITABLE_FIELDS),
    }


def get_item_properties(
    document: dict[str, Any],
    tree: dict[str, Any],
    item_ids: list[str] | None = None,
) -> dict[str, Any]:
    items = flatten_tree(tree)
    wanted = set(item_ids or [])
    if wanted:
        items = [item for item in items if item["id"] in wanted]

    return {
        "document": document,
        "count": len(items),
        "supported_writable_fields": list(WRITABLE_FIELDS),
        "readable_fields": list(READABLE_FIELDS),
        "items": [_snapshot(item) for item in items],
    }


def preview_property_changes(
    document: dict[str, Any],
    tree: dict[str, Any],
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    items = {item["id"]: item for item in flatten_tree(tree)}
    changes: list[dict[str, Any]] = []
    missing_items: list[dict[str, Any]] = []
    unsupported_fields: list[dict[str, Any]] = []

    for update in updates:
        item_id = update.get("item_id")
        if not item_id or item_id not in items:
            missing_items.append({"item_id": item_id, "update": update})
            continue

        item = items[item_id]
        for field, after in update.items():
            if field == "item_id" or after is None:
                continue
            if field not in WRITABLE_FIELDS:
                unsupported_fields.append({"item_id": item_id, "field": field, "value": after})
                continue

            before = item.get(field) or ""
            normalized_after = str(after)
            if normalized_after == before:
                continue

            changes.append(
                {
                    "item_id": item_id,
                    "field": field,
                    "before": before,
                    "after": normalized_after,
                    "reason": "set_property",
                }
            )

    return {
        "document": document,
        "summary": {
            "requested_updates": len(updates),
            "total_changes": len(changes),
            "changed_items": len({change["item_id"] for change in changes}),
            "missing_items": len(missing_items),
            "unsupported_fields": len(unsupported_fields),
            "supported_writable_fields": list(WRITABLE_FIELDS),
        },
        "changes": changes,
        "missing_items": missing_items,
        "unsupported_fields": unsupported_fields,
    }
