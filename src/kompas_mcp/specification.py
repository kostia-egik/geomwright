from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any

from .analyzers import flatten_tree

SPEC_FIELD_TO_COLUMN = OrderedDict(
    [
        ("format", "Формат"),
        ("zone", "Зона"),
        ("position", "Позиция"),
        ("designation", "Обозначение"),
        ("title", "Наименование"),
        ("quantity", "Количество"),
        ("comment", "Примечание"),
    ]
)
SPEC_WRITABLE_FIELDS = tuple(SPEC_FIELD_TO_COLUMN.keys())

SPW_DEFAULT_COLUMNS = (
    {"field": "position", "column_type": 3},
    {"field": "designation", "column_type": 4},
    {"field": "title", "column_type": 5},
    {"field": "quantity", "column_type": 6, "skip_unit_value": True},
    {"field": "comment", "column_type": 7},
)
SPW_ENGINEERING_FIELDS = ("material", "mass", "volume", "density", "total_mass", "total_volume")
SPW_FIELD_ALIASES = {
    "name": "title",
    "qty": "quantity",
}
SPW_COLUMN_PRESETS = {
    "default": SPW_DEFAULT_COLUMNS,
    "base": SPW_DEFAULT_COLUMNS,
    "engineering_comment_columns": (
        *SPW_DEFAULT_COLUMNS,
        {"field": "material", "column_type": 7, "block_number": 1, "column_number": 1, "allow_engineering": True},
        {"field": "mass", "column_type": 7, "block_number": 1, "column_number": 2, "allow_engineering": True},
        {"field": "volume", "column_type": 7, "block_number": 1, "column_number": 3, "allow_engineering": True},
    ),
}
SPW_COLUMN_PRESET_DESCRIPTIONS = {
    "default": "Base .spw columns: position, designation, title, quantity, comment.",
    "base": "Alias for default.",
    "engineering_comment_columns": (
        "Base columns plus material, mass, volume mapped to explicit comment/custom "
        "column slots. Adjust block_number/column_number for the target .spw form."
    ),
}


def _column_int(column: dict[str, Any], keys: tuple[str, ...], default: int) -> int:
    for key in keys:
        if key in column and column[key] not in (None, ""):
            return int(column[key])
    return default


def _column_bool(column: dict[str, Any], key: str, default: bool) -> bool:
    if key not in column:
        return default
    value = column[key]
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def normalize_spw_columns(
    columns: list[str | dict[str, Any]] | None = None,
    *,
    include_engineering: bool = False,
    column_preset: str | None = None,
) -> list[dict[str, Any]]:
    return resolve_spw_columns(
        columns,
        include_engineering=include_engineering,
        column_preset=column_preset,
    )["columns"]


def resolve_spw_columns(
    columns: list[str | dict[str, Any]] | None = None,
    *,
    include_engineering: bool = False,
    column_preset: str | None = None,
    include_available_presets: bool = True,
) -> dict[str, Any]:
    """Normalize caller-supplied .spw column mapping.

    KOMPAS .spw templates differ, so engineering fields are opt-in and must
    be mapped explicitly to a target column type/block/number by the caller.
    """
    source_columns: list[str | dict[str, Any]]
    preset_name = (column_preset or "default").strip().lower() if columns is None else None
    if columns is None:
        if preset_name not in SPW_COLUMN_PRESETS:
            raise ValueError("Unknown .spw column preset: %s" % column_preset)
        source_columns = [dict(column) for column in SPW_COLUMN_PRESETS[preset_name]]
    else:
        source_columns = columns

    normalized: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for raw_column in source_columns:
        if isinstance(raw_column, str):
            column = {"field": raw_column}
        else:
            column = dict(raw_column)

        field = str(column.get("field") or "").strip().lower()
        field = SPW_FIELD_ALIASES.get(field, field)
        if not field:
            ignored.append({"column": column, "reason": "missing_field"})
            continue
        allows_engineering = (
            include_engineering
            or _column_bool(column, "include_engineering", False)
            or _column_bool(column, "allow_engineering", False)
            or _column_bool(column, "engineering", False)
        )
        if field in SPW_ENGINEERING_FIELDS and not allows_engineering:
            ignored.append(
                {
                    "field": field,
                    "label": column.get("label") or field,
                    "reason": "engineering_requires_opt_in",
                }
            )
            continue

        normalized.append(
            {
                "field": field,
                "column_type": _column_int(column, ("column_type", "type"), _default_spw_column_type(field)),
                "block_number": _column_int(column, ("block_number", "block"), 1),
                "column_number": _column_int(column, ("column_number", "number"), 0),
                "skip_unit_value": _column_bool(column, "skip_unit_value", field == "quantity"),
                "label": column.get("label") or field,
            }
        )
    engineering_columns = [column for column in normalized if column["field"] in SPW_ENGINEERING_FIELDS]
    return {
        "preset": preset_name,
        "preset_description": SPW_COLUMN_PRESET_DESCRIPTIONS.get(preset_name or ""),
        "columns": normalized,
        "ignored_columns": ignored,
        "requested_count": len(source_columns),
        "normalized_count": len(normalized),
        "engineering_columns": engineering_columns,
        "available_presets": get_spw_column_presets() if include_available_presets else {},
    }


def get_spw_column_presets() -> dict[str, Any]:
    return {
        name: {
            "description": SPW_COLUMN_PRESET_DESCRIPTIONS.get(name, ""),
            "columns": resolve_spw_columns(
                list(columns),
                include_engineering=True,
                include_available_presets=False,
            )["columns"],
        }
        for name, columns in SPW_COLUMN_PRESETS.items()
    }


def _default_spw_column_type(field: str) -> int:
    defaults = {column["field"]: int(column["column_type"]) for column in SPW_DEFAULT_COLUMNS}
    if field in defaults:
        return defaults[field]
    # Standard .spw forms do not have a universal engineering column. The
    # comment column is the safest explicit fallback for custom opt-in fields.
    return 7


def _normalized_source(value: str) -> str:
    if not value:
        return ""
    return os.path.normcase(os.path.abspath(os.path.normpath(value)))


def _row_key(item: dict[str, Any]) -> tuple[str, str, str, str, str]:
    source_path = _normalized_source(item.get("source_path") or "")
    designation = (item.get("designation") or "").strip()
    name = (item.get("name") or "").strip()
    material = (item.get("material") or "").strip()
    kind = (item.get("kind") or "").strip()
    return (source_path, designation, name, material, kind)


def _numeric_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _engineering_snapshot(item: dict[str, Any], quantity: int = 1) -> dict[str, Any]:
    mass = _numeric_or_none(item.get("mass"))
    volume = _numeric_or_none(item.get("volume"))
    density = _numeric_or_none(item.get("density"))
    return {
        "material": item.get("material") or "",
        "mass": mass,
        "volume": volume,
        "density": density,
        "total_mass": mass * quantity if mass is not None else None,
        "total_volume": volume * quantity if volume is not None else None,
    }


def _engineering_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_mass = 0.0
    total_volume = 0.0
    rows_with_mass = 0
    rows_with_volume = 0
    rows_with_nonzero_mass = 0
    rows_with_nonzero_volume = 0

    for row in rows:
        if row.get("mass") is not None:
            rows_with_mass += 1
            if float(row["mass"]) != 0.0:
                rows_with_nonzero_mass += 1
        if row.get("volume") is not None:
            rows_with_volume += 1
            if float(row["volume"]) != 0.0:
                rows_with_nonzero_volume += 1
        if row.get("total_mass") is not None:
            total_mass += float(row["total_mass"])
        if row.get("total_volume") is not None:
            total_volume += float(row["total_volume"])

    return {
        "available_fields": ["material", "mass", "volume", "density"],
        "written_to_spw_columns": [],
        "rows_with_material": sum(1 for row in rows if row.get("material")),
        "rows_with_mass": rows_with_mass,
        "rows_with_nonzero_mass": rows_with_nonzero_mass,
        "rows_with_volume": rows_with_volume,
        "rows_with_nonzero_volume": rows_with_nonzero_volume,
        "total_mass": total_mass if rows_with_mass else None,
        "total_volume": total_volume if rows_with_volume else None,
    }


def build_specification_preview(
    document: dict[str, Any],
    tree: dict[str, Any],
    *,
    include_root: bool = False,
    group_identical: bool = True,
) -> dict[str, Any]:
    items = flatten_tree(tree)
    if not include_root:
        items = items[1:]

    if not group_identical:
        rows = []
        for index, item in enumerate(items, start=1):
            engineering = _engineering_snapshot(item)
            rows.append(
                {
                    "row_id": f"row/{index - 1}",
                    "position": str(index),
                    "designation": item.get("designation") or "",
                    "title": item.get("title") or item.get("name") or "",
                    "quantity": "1",
                    "comment": item.get("comment") or "",
                    **engineering,
                    "kind": item.get("kind") or "",
                    "reference": item.get("reference"),
                    "source_item_ids": [item["id"]],
                    "source_paths": [item.get("source_path") or ""],
                    "section": 10,
                    "attribute_number": 0,
                }
            )
        return {
            "document": document,
            "summary": {
                "total_source_items": len(items),
                "generated_rows": len(rows),
                "skipped_items": 0,
                "include_root": include_root,
                "group_identical": False,
                "engineering": _engineering_summary(rows),
            },
            "rows": rows,
        }

    grouped: OrderedDict[tuple[str, str, str, str, str], dict[str, Any]] = OrderedDict()
    skipped_embedded = 0

    for item in items:
        if not include_root and item.get("id") == "root":
            continue

        key = _row_key(item)
        if not any(key):
            skipped_embedded += 1
            continue

        row = grouped.get(key)
        if row is None:
            grouped[key] = {
                "source_item_ids": [item["id"]],
                "source_paths": [item.get("source_path") or ""],
                "kind": item.get("kind") or "",
                "designation": item.get("designation") or "",
                "title": item.get("title") or item.get("name") or "",
                "material": item.get("material") or "",
                "comment": item.get("comment") or "",
                "mass": _numeric_or_none(item.get("mass")),
                "volume": _numeric_or_none(item.get("volume")),
                "density": _numeric_or_none(item.get("density")),
                "total_mass": _numeric_or_none(item.get("mass")),
                "total_volume": _numeric_or_none(item.get("volume")),
                "quantity": 1,
            }
        else:
            row["source_item_ids"].append(item["id"])
            source_path = item.get("source_path") or ""
            if source_path and source_path not in row["source_paths"]:
                row["source_paths"].append(source_path)
            row["quantity"] += 1
            mass = _numeric_or_none(item.get("mass"))
            volume = _numeric_or_none(item.get("volume"))
            if mass is not None:
                row["total_mass"] = (row.get("total_mass") or 0.0) + mass
            if volume is not None:
                row["total_volume"] = (row.get("total_volume") or 0.0) + volume

    rows: list[dict[str, Any]] = []
    for index, grouped_row in enumerate(grouped.values(), start=1):
        rows.append(
            {
                "row_id": f"row/{index - 1}",
                "position": str(index),
                "designation": grouped_row["designation"],
                "title": grouped_row["title"],
                "quantity": str(grouped_row["quantity"]),
                "comment": grouped_row["comment"],
                "material": grouped_row["material"],
                "mass": grouped_row["mass"],
                "volume": grouped_row["volume"],
                "density": grouped_row["density"],
                "total_mass": grouped_row["total_mass"],
                "total_volume": grouped_row["total_volume"],
                "kind": grouped_row["kind"],
                "reference": None,
                "source_item_ids": grouped_row["source_item_ids"],
                "source_paths": grouped_row["source_paths"],
                "section": 10,
                "attribute_number": 0,
            }
        )

    return {
        "document": document,
        "summary": {
            "total_source_items": len(items),
            "generated_rows": len(rows),
            "skipped_items": skipped_embedded,
            "include_root": include_root,
            "group_identical": True,
            "engineering": _engineering_summary(rows),
        },
        "rows": rows,
    }


def _iter_spec_objects(specification_payload: dict[str, Any]) -> list[dict[str, Any]]:
    specification = specification_payload.get("specification") or {}
    return list(specification.get("base_objects") or []) + list(specification.get("comment_objects") or [])


def _preferred_column(columns: list[dict[str, Any]], column_name: str) -> dict[str, Any] | None:
    candidates = [column for column in columns if (column.get("column_name") or "") == column_name]
    if not candidates:
        return None
    candidates.sort(key=lambda column: (0 if int(column.get("block_number") or 0) == 0 else 1, int(column.get("number") or 0)))
    return candidates[0]


def _column_by_key(columns: list[dict[str, Any]], column_key: str) -> dict[str, Any] | None:
    for column in columns:
        if column.get("column_key") == column_key:
            return column
    return None


def _normalize_preview_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def preview_specification_changes(
    specification_payload: dict[str, Any],
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    specification = specification_payload.get("specification")
    if not specification:
        return {
            "document": specification_payload.get("document"),
            "summary": {
                "requested_updates": len(updates),
                "total_changes": 0,
                "changed_objects": 0,
                "missing_objects": 0,
                "missing_columns": 0,
                "unsupported_fields": 0,
                "supported_writable_fields": list(SPEC_WRITABLE_FIELDS),
                "selected": False,
            },
            "changes": [],
            "missing_objects": [],
            "missing_columns": [],
            "unsupported_fields": [],
            "selected_description": None,
        }

    objects = {obj["object_id"]: obj for obj in _iter_spec_objects(specification_payload)}
    changes: list[dict[str, Any]] = []
    missing_objects: list[dict[str, Any]] = []
    missing_columns: list[dict[str, Any]] = []
    unsupported_fields: list[dict[str, Any]] = []

    for update in updates:
        object_id = update.get("object_id")
        if not object_id or object_id not in objects:
            missing_objects.append({"object_id": object_id, "update": update})
            continue

        obj = objects[object_id]
        columns = list(obj.get("columns") or [])

        direct_columns = update.get("columns") or {}
        for column_key, after in direct_columns.items():
            if after is None:
                continue
            column = _column_by_key(columns, str(column_key))
            if column is None:
                missing_columns.append({"object_id": object_id, "column_key": column_key})
                continue
            before = column.get("text") or ""
            normalized_after = _normalize_preview_value(after)
            if normalized_after == before:
                continue
            changes.append(
                {
                    "object_id": object_id,
                    "column_key": column.get("column_key"),
                    "column_name": column.get("column_name") or "",
                    "block_number": int(column.get("block_number") or 0),
                    "before": before,
                    "after": normalized_after,
                    "reason": "set_spec_column",
                }
            )

        for field, after in update.items():
            if field in ("object_id", "columns") or after is None:
                continue
            if field not in SPEC_FIELD_TO_COLUMN:
                unsupported_fields.append({"object_id": object_id, "field": field, "value": after})
                continue

            column = _preferred_column(columns, SPEC_FIELD_TO_COLUMN[field])
            if column is None:
                missing_columns.append({"object_id": object_id, "field": field, "column_name": SPEC_FIELD_TO_COLUMN[field]})
                continue

            before = column.get("text") or ""
            normalized_after = _normalize_preview_value(after)
            if normalized_after == before:
                continue

            changes.append(
                {
                    "object_id": object_id,
                    "field": field,
                    "column_key": column.get("column_key"),
                    "column_name": column.get("column_name") or "",
                    "block_number": int(column.get("block_number") or 0),
                    "before": before,
                    "after": normalized_after,
                    "reason": "set_spec_field",
                }
            )

    return {
        "document": specification_payload.get("document"),
        "selected_description": {
            "index": specification.get("index"),
            "layout_name": specification.get("layout_name") or "",
            "style_id": specification.get("style_id"),
        },
        "summary": {
            "requested_updates": len(updates),
            "total_changes": len(changes),
            "changed_objects": len({change["object_id"] for change in changes}),
            "missing_objects": len(missing_objects),
            "missing_columns": len(missing_columns),
            "unsupported_fields": len(unsupported_fields),
            "supported_writable_fields": list(SPEC_WRITABLE_FIELDS),
            "selected": True,
        },
        "changes": changes,
        "missing_objects": missing_objects,
        "missing_columns": missing_columns,
        "unsupported_fields": unsupported_fields,
    }


def _normalize_match_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _iter_editable_spec_objects(
    specification_payload: dict[str, Any],
    *,
    skip_zero_quantity: bool = False,
) -> list[dict[str, Any]]:
    editable = []
    for obj in _iter_spec_objects(specification_payload):
        column_texts = obj.get("column_texts") or {}
        if any(column_name in column_texts for column_name in SPEC_FIELD_TO_COLUMN.values()):
            if skip_zero_quantity:
                quantity_text = str(column_texts.get(SPEC_FIELD_TO_COLUMN["quantity"]) or "").strip()
                if quantity_text:
                    try:
                        if int(quantity_text) == 0:
                            continue
                    except Exception:
                        pass
            editable.append(obj)
    return editable


def _unique_object_index(
    objects: list[dict[str, Any]],
    column_name: str,
    *,
    excluded: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    excluded = excluded or set()
    for obj in objects:
        if obj.get("object_id") in excluded:
            continue
        key = _normalize_match_text((obj.get("column_texts") or {}).get(column_name))
        if not key:
            continue
        grouped.setdefault(key, []).append(obj)
    return {key: items[0] for key, items in grouped.items() if len(items) == 1}


def _match_spec_objects_to_preview_rows(
    specification_payload: dict[str, Any],
    preview_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    spec_objects = _iter_editable_spec_objects(specification_payload, skip_zero_quantity=True)
    matched_pairs: list[dict[str, Any]] = []
    matched_object_ids: set[str] = set()
    matched_row_ids: set[str] = set()

    designation_index = _unique_object_index(spec_objects, SPEC_FIELD_TO_COLUMN["designation"])
    title_index = _unique_object_index(spec_objects, SPEC_FIELD_TO_COLUMN["title"])
    reference_index = {
        str(obj.get("reference")): obj
        for obj in spec_objects
        if obj.get("reference") is not None
    }

    for row in preview_rows:
        row_id = row.get("row_id")
        row_reference = row.get("reference")
        row_designation = _normalize_match_text(row.get("designation"))
        row_title = _normalize_match_text(row.get("title"))
        target = None
        matched_by = None
        if row_reference is not None:
            candidate = reference_index.get(str(row_reference))
            if candidate and candidate.get("object_id") not in matched_object_ids:
                target = candidate
                matched_by = "reference"
        if target is None and row_designation:
            candidate = designation_index.get(row_designation)
            if candidate and candidate.get("object_id") not in matched_object_ids:
                target = candidate
                matched_by = "designation"
        if target is None and row_title:
            candidate = title_index.get(row_title)
            if candidate and candidate.get("object_id") not in matched_object_ids:
                target = candidate
                matched_by = "title"
        if target is None:
            continue
        matched_pairs.append({"row": row, "object": target, "matched_by": matched_by})
        matched_object_ids.add(target["object_id"])
        if row_id:
            matched_row_ids.add(str(row_id))

    for row in preview_rows:
        row_id = str(row.get("row_id"))
        if row_id in matched_row_ids:
            continue
        row_title = _normalize_match_text(row.get("title"))
        if not row_title:
            continue
        try:
            row_quantity = max(int(str(row.get("quantity") or "0").strip() or "0"), 0)
        except Exception:
            row_quantity = 0
        if row_quantity <= 1:
            continue
        candidates = [
            obj
            for obj in spec_objects
            if obj.get("object_id") not in matched_object_ids
            and _normalize_match_text((obj.get("column_texts") or {}).get(SPEC_FIELD_TO_COLUMN["title"])) == row_title
        ]
        if len(candidates) != row_quantity:
            continue
        for obj in candidates:
            matched_pairs.append(
                {
                    "row": row,
                    "object": obj,
                    "matched_by": "title_group",
                    "group_size": row_quantity,
                }
            )
            matched_object_ids.add(obj["object_id"])
        matched_row_ids.add(row_id)

    unmatched_rows = [row for row in preview_rows if str(row.get("row_id")) not in matched_row_ids]
    unmatched_objects = [obj for obj in spec_objects if obj.get("object_id") not in matched_object_ids]
    return matched_pairs, unmatched_rows, unmatched_objects


def build_specification_autofill_preview(
    specification_payload: dict[str, Any],
    model_preview_payload: dict[str, Any],
    *,
    fields: list[str] | None = None,
    fill_only: bool = False,
) -> dict[str, Any]:
    selected_fields = [field for field in (fields or ["designation", "title", "quantity", "comment"]) if field in SPEC_WRITABLE_FIELDS]
    preview_rows = list(model_preview_payload.get("rows") or [])
    matched_pairs, unmatched_rows, unmatched_objects = _match_spec_objects_to_preview_rows(specification_payload, preview_rows)

    updates: list[dict[str, Any]] = []
    for pair in matched_pairs:
        row = pair["row"]
        obj = pair["object"]
        column_texts = obj.get("column_texts") or {}
        group_size = int(pair.get("group_size") or 1)
        update: dict[str, Any] = {"object_id": obj["object_id"]}
        for field in selected_fields:
            if field == "quantity" and group_size > 1:
                continue
            column_name = SPEC_FIELD_TO_COLUMN[field]
            desired = str(row.get(field) or "").strip()
            current = str(column_texts.get(column_name) or "").strip()
            if not desired:
                continue
            if fill_only and current:
                continue
            if desired == current:
                continue
            update[field] = desired
        if len(update) > 1:
            updates.append(update)

    preview = preview_specification_changes(specification_payload, updates)
    return {
        "document": specification_payload.get("document"),
        "selected_description": preview.get("selected_description"),
        "model_preview_summary": model_preview_payload.get("summary"),
        "matching_summary": {
            "spec_objects": len(_iter_editable_spec_objects(specification_payload)),
            "active_spec_objects": len(_iter_editable_spec_objects(specification_payload, skip_zero_quantity=True)),
            "model_rows": len(preview_rows),
            "matched_rows": len(matched_pairs),
            "unmatched_rows": len(unmatched_rows),
            "unmatched_spec_objects": len(unmatched_objects),
            "fill_only": bool(fill_only),
            "fields": selected_fields,
        },
        "preview": preview,
        "updates": updates,
        "matched_rows": [
            {
                "object_id": pair["object"].get("object_id"),
                "row_id": pair["row"].get("row_id"),
                "matched_by": pair["matched_by"],
                "group_size": int(pair.get("group_size") or 1),
                "designation": pair["row"].get("designation") or "",
                "title": pair["row"].get("title") or "",
            }
            for pair in matched_pairs
        ],
        "unmatched_rows": unmatched_rows,
        "unmatched_spec_objects": [
            {
                "object_id": obj.get("object_id"),
                "designation": (obj.get("column_texts") or {}).get(SPEC_FIELD_TO_COLUMN["designation"], ""),
                "title": (obj.get("column_texts") or {}).get(SPEC_FIELD_TO_COLUMN["title"], ""),
            }
            for obj in unmatched_objects
        ],
    }
