from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .analyzers import flatten_tree
from .rules import clean_text


def _designation_token(value: str, fallback: str = "DOC") -> str:
    token = value.strip() or fallback
    token = token.replace(" ", "-")
    while "--" in token:
        token = token.replace("--", "-")
    return token


def preview_changeset(
    document: dict[str, Any],
    tree: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, Any]:
    items = flatten_tree(tree)
    changes: list[dict[str, Any]] = []

    root = items[0]
    document_stem = Path(document.get("name") or "DOC").stem
    root_designation = (root.get("designation") or "").strip()
    base_designation = _designation_token(
        clean_text(root_designation or document_stem or root.get("name") or "DOC", rules)
    )

    for item in items:
        current_name = item.get("name") or ""
        suggested_name = clean_text(current_name, rules)
        if suggested_name and suggested_name != current_name:
            changes.append(
                {
                    "item_id": item["id"],
                    "field": "name",
                    "before": current_name,
                    "after": suggested_name,
                    "reason": "normalize_name",
                }
            )

    if not root_designation:
        changes.append(
            {
                "item_id": root["id"],
                "field": "designation",
                "before": root.get("designation") or "",
                "after": base_designation,
                "reason": "fill_root_designation",
            }
        )

    designation_counter = 1
    generated_values = Counter()
    for item in items[1:]:
        current_designation = (item.get("designation") or "").strip()
        if current_designation:
            continue

        proposed = f"{base_designation}-{designation_counter:03d}"
        designation_counter += 1
        generated_values[proposed] += 1
        changes.append(
            {
                "item_id": item["id"],
                "field": "designation",
                "before": item.get("designation") or "",
                "after": proposed,
                "reason": "fill_missing_designation",
            }
        )

    summary = {
        "total_changes": len(changes),
        "name_changes": sum(1 for change in changes if change["field"] == "name"),
        "designation_changes": sum(1 for change in changes if change["field"] == "designation"),
        "base_designation": base_designation,
        "supported_fields": ["name", "designation"],
    }

    return {
        "document": document,
        "summary": summary,
        "changes": changes,
    }
