from __future__ import annotations

import math
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

from .thread_profile_geometry import build_v60_thread_geometry
from .thread_profile_geometry import describe_metric_thread_geometry
from .thread_profile_geometry import describe_thread_geometry


DEFAULT_THREAD_STANDARD_TABLE = "cil0_24705-2004 coarse"
METRIC_V1_TABLES = (
    "cil0_24705-2004 coarse",
    "cil0_24705-2004 fine",
    "cil1_24705-2004",
    "cil1_ex_ISO 724 coarse",
    "cil1_ex_ISO 724 fine",
)

THREAD_STANDARD_ALIASES = {
    "metric": DEFAULT_THREAD_STANDARD_TABLE,
    "metric_coarse": DEFAULT_THREAD_STANDARD_TABLE,
    "metric_fine": "cil0_24705-2004 fine",
    "metric_iso": "cil1_24705-2004",
    "pipe_cylindrical": "cil2_6357-81",
    "pipe_conical": "con2_6211-81",
}


def _normalize_standard_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _optional_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return parsed


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except Exception:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _has_columns(columns: set[str] | tuple[str, ...], *required: str) -> bool:
    available = set(columns)
    return all(name in available for name in required)


def assess_thread_standard_for_helical_thread_v1(standard: dict[str, Any]) -> dict[str, Any]:
    """Assess compatibility with the current helical-thread V1 profile implementation.

    Helical-thread V1 in this project targets a symmetric V-profile on a cylindrical carrier
    and is currently scoped to metric 60° threads.
    """

    table_name = str(standard.get("table_name") or "")
    display_name = str(standard.get("display_name") or table_name)
    conical_angle = float(standard.get("conical_thread_angle") or 0.0)
    normalized_name = _normalize_text(display_name)
    normalized_table_name = _normalize_text(table_name)

    if any(token in normalized_name or token in normalized_table_name for token in ("npt", "pipe_conical", "con2")):
        return {
            "compatible": True,
            "profile_family": "pipe_npt_v60",
            "suggested_profile_angle_degrees": 60.0,
            "reason": "Tapered American pipe thread uses a conical 60 degree profile with flat truncation.",
        }

    if abs(conical_angle) > 1e-9:
        return {
            "compatible": False,
            "profile_family": "conical",
            "suggested_profile_angle_degrees": None,
            "reason": "Conical standards require cone-aware geometry; helical-thread V1 is cylindrical-only.",
        }

    if "трапецеид" in normalized_name or "trapez" in normalized_name:
        return {
            "compatible": False,
            "profile_family": "trapezoidal",
            "suggested_profile_angle_degrees": None,
            "reason": "Trapezoidal profile is not a symmetric V-thread; needs a different sketch profile family.",
        }

    if "упорн" in normalized_name or "buttress" in normalized_name:
        return {
            "compatible": False,
            "profile_family": "buttress",
            "suggested_profile_angle_degrees": None,
            "reason": "Buttress profile is asymmetric; needs a dedicated profile family.",
        }

    if "уитворт" in normalized_name or "whitworth" in normalized_name:
        return {
            "compatible": False,
            "profile_family": "whitworth_v",
            "suggested_profile_angle_degrees": None,
            "reason": "Whitworth pipe/inch standards need a non-60° profile and different truncation/rounding defaults.",
        }

    if "метрическ" in normalized_name or "metric" in normalized_name:
        return {
            "compatible": True,
            "profile_family": "metric_v60",
            "suggested_profile_angle_degrees": 60.0,
            "reason": "Metric cylindrical standard matches helical-thread V1 (V-profile 60°, cylinder).",
        }

    if any(
        token in normalized_name or token in normalized_table_name
        for token in ("unified", "unc", "unf", "unef", "uns", "unr", "unj")
    ):
        profile_family = "unified_un_v60"
        if "unr" in normalized_name or "unr" in normalized_table_name:
            profile_family = "unified_unr_v60"
        if "unj" in normalized_name or "unj" in normalized_table_name:
            profile_family = "unified_unj_v60"
        return {
            "compatible": True,
            "profile_family": profile_family,
            "suggested_profile_angle_degrees": 60.0,
            "reason": "Unified inch cylindrical standard matches helical-thread V1 after inch/TPI values are resolved to millimeters.",
        }

    if any(token in normalized_name or token in normalized_table_name for token in ("nps", "npsm", "npsl", "npsc")):
        return {
            "compatible": True,
            "profile_family": "pipe_nps_v60",
            "suggested_profile_angle_degrees": 60.0,
            "reason": "Straight American pipe thread uses a cylindrical 60 degree profile with flat truncation.",
        }

    # Fallback: treat unknown cylindrical standards as incompatible for V1, but keep them discoverable.
    return {
        "compatible": False,
        "profile_family": "unknown",
        "suggested_profile_angle_degrees": None,
        "reason": "Unknown standard family; helical-thread V1 accepts only cylindrical V-profile families for now.",
    }


def _append_metric_thread_geometry(
    entry: dict[str, Any],
    *,
    standard: dict[str, Any],
) -> dict[str, Any]:
    assessment = assess_thread_standard_for_helical_thread_v1(standard)
    if not bool(assessment.get("compatible")):
        return entry
    profile_family = str(assessment.get("profile_family") or "metric_v60")
    diameter = entry.get("d")
    pitch = entry.get("p")
    if not isinstance(diameter, int | float) or not isinstance(pitch, int | float):
        return entry
    if profile_family == "metric_v60":
        geometry = describe_metric_thread_geometry(float(diameter), float(pitch))
    else:
        geometry = describe_thread_geometry(
            build_v60_thread_geometry(float(diameter), float(pitch), profile_family=profile_family)
        )
    return {
        **entry,
        "thread_geometry": geometry,
        "metric_thread_geometry": geometry,
        "d_major": geometry["major_diameter"],
        "d1_minor": geometry["internal_minor_diameter"],
        "d2_pitch": geometry["pitch_diameter"],
        "d3_external_minor": geometry["external_minor_diameter"],
        "fundamental_triangle_height": geometry["fundamental_triangle_height"],
    }


def list_thread_catalog_standards(*, database_path: str | None = None) -> dict[str, Any]:
    resolved_database_path = str(database_path or find_thread_database_path() or "").strip()
    descriptions = _load_standard_descriptions(resolved_database_path) if resolved_database_path else {}
    standards = []
    for payload in sorted(descriptions.values(), key=lambda item: str(item.get("table_name") or "")):
        standard_payload = dict(payload)
        standard_payload.update(_load_table_summary(resolved_database_path, str(standard_payload.get("table_name") or "")))
        assessment = assess_thread_standard_for_helical_thread_v1(standard_payload)
        standard_payload["helical_thread_v1_compatible"] = bool(assessment.get("compatible"))
        standard_payload["helical_thread_v1_profile_family"] = str(assessment.get("profile_family") or "")
        standard_payload["helical_thread_v1_reason"] = str(assessment.get("reason") or "")
        standard_payload["helical_thread_v1_suggested_profile_angle_degrees"] = assessment.get(
            "suggested_profile_angle_degrees"
        )
        standard_payload["helical_thread_v1_metric_table"] = str(standard_payload.get("table_name") or "") in METRIC_V1_TABLES
        standards.append(standard_payload)
    return {
        "database_path": resolved_database_path or None,
        "catalog_found": bool(descriptions),
        "standards": standards,
    }


@lru_cache(maxsize=1)
def find_thread_database_path() -> str | None:
    root = Path(r"C:\ProgramData\ASCON\KOMPAS-3D")
    if not root.exists():
        return None
    candidates = []
    for path in root.glob("*/Databases/thread.db"):
        version_name = path.parent.parent.name
        try:
            version_order = int(version_name)
        except Exception:
            version_order = -1
        candidates.append((version_order, str(path)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


@lru_cache(maxsize=16)
def _load_standard_descriptions(database_path: str) -> dict[str, dict[str, Any]]:
    descriptions: dict[str, dict[str, Any]] = {}
    path = Path(database_path)
    if not path.exists():
        return descriptions
    connection = sqlite3.connect(str(path))
    try:
        cursor = connection.cursor()
        cursor.execute(
            "select displayname, koeff, cone, tablename, note from [description]"
        )
        for display_name, coefficient, cone_angle, table_name, note in cursor.fetchall():
            payload = {
                "display_name": str(display_name or table_name or ""),
                "table_name": str(table_name or ""),
                "internal_diameter_coefficient": float(coefficient or 0.0),
                "conical_thread_angle": float(cone_angle or 0.0),
                "note": int(note or 0),
            }
            descriptions[str(payload["table_name"])] = payload
    finally:
        connection.close()
    return descriptions


@lru_cache(maxsize=128)
def _load_table_columns(database_path: str, table_name: str) -> tuple[str, ...]:
    path = Path(database_path)
    if not path.exists():
        return tuple()
    connection = sqlite3.connect(str(path))
    try:
        cursor = connection.cursor()
        cursor.execute(f"pragma table_info([{table_name}])")
        return tuple(str(row[1]) for row in cursor.fetchall())
    finally:
        connection.close()


@lru_cache(maxsize=128)
def _load_table_summary(database_path: str, table_name: str) -> dict[str, Any]:
    columns = _load_table_columns(database_path, table_name)
    summary: dict[str, Any] = {
        "column_names": list(columns),
        "entry_count": 0,
        "diameter_min": None,
        "diameter_max": None,
        "pitch_min": None,
        "pitch_max": None,
        "sample_designations": [],
    }
    path = Path(database_path)
    if not path.exists() or not _has_columns(columns, "d", "p"):
        return summary

    connection = sqlite3.connect(str(path))
    try:
        cursor = connection.cursor()
        cursor.execute(f"select count(*), min(d), max(d), min(p), max(p) from [{table_name}]")
        row = cursor.fetchone() or (0, None, None, None, None)
        summary.update(
            {
                "entry_count": int(row[0] or 0),
                "diameter_min": float(row[1]) if isinstance(row[1], int | float) else None,
                "diameter_max": float(row[2]) if isinstance(row[2], int | float) else None,
                "pitch_min": float(row[3]) if isinstance(row[3], int | float) else None,
                "pitch_max": float(row[4]) if isinstance(row[4], int | float) else None,
            }
        )
        if "title" in columns:
            cursor.execute(
                f"select title from [{table_name}] where title is not null and trim(title) <> '' order by d, p limit 5"
            )
            summary["sample_designations"] = [str(item[0]) for item in cursor.fetchall() if str(item[0] or "").strip()]
    finally:
        connection.close()
    return summary


def list_thread_standard_entries(
    value: Any,
    *,
    database_path: str | None = None,
    limit: int | None = 200,
    offset: int | None = 0,
    title_query: str | None = None,
    diameter: float | None = None,
    pitch: float | None = None,
    diameter_min: float | None = None,
    diameter_max: float | None = None,
    pitch_min: float | None = None,
    pitch_max: float | None = None,
) -> dict[str, Any]:
    """List rows of one thread standard table, shaped for helical-thread selection."""

    standard = resolve_thread_standard(value, database_path=database_path)
    resolved_database_path = str(standard.get("database_path") or "").strip()
    table_name = str(standard.get("table_name") or "").strip()
    if not resolved_database_path or not table_name:
        return {
            **standard,
            "entries": [],
            "limit": None,
            "offset": None,
            "has_more": False,
        }

    columns = set(_load_table_columns(resolved_database_path, table_name))
    if not _has_columns(columns, "d", "p"):
        return {
            **standard,
            "entries": [],
            "limit": None,
            "offset": None,
            "has_more": False,
        }

    requested_limit = None if limit is None else max(1, _optional_int(limit, default=200))
    requested_offset = max(0, _optional_int(offset, default=0))
    title_query_norm = str(title_query or "").strip()
    diameter_value = _optional_float(diameter)
    pitch_value = _optional_float(pitch)
    diameter_min_value = _optional_float(diameter_min)
    diameter_max_value = _optional_float(diameter_max)
    pitch_min_value = _optional_float(pitch_min)
    pitch_max_value = _optional_float(pitch_max)

    select_cols = ["d", "p"]
    if "d1" in columns:
        select_cols.append("d1")
    if "row" in columns:
        select_cols.append("row")
    if "title" in columns:
        select_cols.append("title")

    where_parts: list[str] = []
    params: list[Any] = []
    if title_query_norm:
        pattern = title_query_norm
        if "%" not in pattern and "_" not in pattern:
            pattern = pattern + "%"
        where_parts.append("title like ?")
        params.append(pattern)
    tol = 1e-6
    if diameter_value is not None:
        where_parts.append("abs(d - ?) < ?")
        params.extend([diameter_value, tol])
    if pitch_value is not None:
        where_parts.append("abs(p - ?) < ?")
        params.extend([pitch_value, tol])
    if diameter_min_value is not None:
        where_parts.append("d >= ?")
        params.append(diameter_min_value)
    if diameter_max_value is not None:
        where_parts.append("d <= ?")
        params.append(diameter_max_value)
    if pitch_min_value is not None:
        where_parts.append("p >= ?")
        params.append(pitch_min_value)
    if pitch_max_value is not None:
        where_parts.append("p <= ?")
        params.append(pitch_max_value)
    where_sql = (" where " + " and ".join(where_parts)) if where_parts else ""

    limit_sql = ""
    query_limit = None
    if requested_limit is not None:
        query_limit = requested_limit + 1
        limit_sql = " limit ? offset ?"
        params.extend([query_limit, requested_offset])

    connection = sqlite3.connect(resolved_database_path)
    try:
        cursor = connection.cursor()
        sql = f"select {', '.join(select_cols)} from [{table_name}]{where_sql} order by d, p{limit_sql}"
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
    finally:
        connection.close()

    has_more = False
    if requested_limit is not None and len(rows) > requested_limit:
        has_more = True
        rows = rows[:requested_limit]

    entries: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(zip(select_cols, row))
        title_value = str(payload.get("title") or "")
        diameter_value = float(payload.get("d") or 0.0)
        pitch_value = float(payload.get("p") or 0.0)
        minor_diameter = float(payload.get("d1")) if isinstance(payload.get("d1"), int | float) else None
        internal_thread_depth = None
        if minor_diameter is not None:
            internal_thread_depth = (diameter_value - minor_diameter) / 2.0
        entries.append(
            _append_metric_thread_geometry(
                {
                "designation": title_value,
                "d": diameter_value,
                "p": pitch_value,
                "d1": minor_diameter,
                "internal_thread_depth": internal_thread_depth,
                },
                standard=standard,
            )
        )

    assessment = assess_thread_standard_for_helical_thread_v1(standard)
    return {
        **standard,
        "helical_thread_v1_compatible": bool(assessment.get("compatible")),
        "helical_thread_v1_profile_family": str(assessment.get("profile_family") or ""),
        "helical_thread_v1_reason": str(assessment.get("reason") or ""),
        "entries": entries,
        "limit": requested_limit,
        "offset": requested_offset,
        "has_more": has_more,
    }


def list_helical_thread_v1_candidates(
    *,
    database_path: str | None = None,
    limit_per_standard: int | None = 20,
    offset: int | None = 0,
    title_query: str | None = None,
    diameter_min: float | None = None,
    diameter_max: float | None = None,
    pitch_min: float | None = None,
    pitch_max: float | None = None,
) -> dict[str, Any]:
    catalog_payload = list_thread_catalog_standards(database_path=database_path)
    standards = []
    for standard in catalog_payload.get("standards") or []:
        if not bool(standard.get("helical_thread_v1_compatible")):
            continue
        entries_payload = list_thread_standard_entries(
            standard.get("table_name"),
            database_path=database_path,
            limit=limit_per_standard,
            offset=offset,
            title_query=title_query,
            diameter_min=diameter_min,
            diameter_max=diameter_max,
            pitch_min=pitch_min,
            pitch_max=pitch_max,
        )
        standards.append(
            {
                "table_name": str(standard.get("table_name") or ""),
                "display_name": str(standard.get("display_name") or ""),
                "entry_count": int(standard.get("entry_count") or 0),
                "diameter_min": standard.get("diameter_min"),
                "diameter_max": standard.get("diameter_max"),
                "pitch_min": standard.get("pitch_min"),
                "pitch_max": standard.get("pitch_max"),
                "sample_designations": list(standard.get("sample_designations") or []),
                "entries": list(entries_payload.get("entries") or []),
                "entries_limit": entries_payload.get("limit"),
                "entries_offset": entries_payload.get("offset"),
                "entries_has_more": bool(entries_payload.get("has_more")),
            }
        )
    return {
        "database_path": catalog_payload.get("database_path"),
        "catalog_found": bool(catalog_payload.get("catalog_found")),
        "standards": standards,
        "standard_count": len(standards),
    }


def resolve_thread_designation_entry(
    designation: Any,
    *,
    standard: Any | None = None,
    thread_type: Any | None = None,
    database_path: str | None = None,
) -> dict[str, Any]:
    """Resolve a catalog entry by its `title`/designation (e.g. `M16`, `M16x1.5`)."""

    resolved_database_path = str(database_path or find_thread_database_path() or "").strip()
    descriptions = _load_standard_descriptions(resolved_database_path) if resolved_database_path else {}
    if not resolved_database_path or not descriptions:
        return {
            "database_path": resolved_database_path or None,
            "catalog_found": bool(descriptions),
            "designation": str(designation or ""),
            "matches": [],
        }

    normalized_designation = str(designation or "").strip().replace("×", "x").replace(" ", "")
    if not normalized_designation:
        raise ValueError("designation is required")

    def _pick_default_table() -> str | None:
        available = set(descriptions.keys())
        if not available:
            return None

        # 1) Prefer the explicit requested standard, if provided.
        if standard is not None:
            resolved = resolve_thread_standard(standard, database_path=resolved_database_path)
            table_name = str(resolved.get("table_name") or "").strip()
            return table_name if table_name in available else table_name or None

        # 2) Otherwise pick a single default per "thread type" (similar variants).
        resolved = resolve_thread_standard(thread_type or "metric", database_path=resolved_database_path)
        default_table = str(resolved.get("table_name") or "").strip()
        if default_table in available:
            return default_table

        # 3) Fallback for custom/trimmed catalogs: pick the first V1-compatible metric standard.
        compatible_metric = [
            name
            for name, payload in descriptions.items()
            if bool(assess_thread_standard_for_helical_thread_v1(payload).get("compatible"))
        ]
        if compatible_metric:
            compatible_metric.sort()
            return compatible_metric[0]

        # 4) Last resort: pick any available table deterministically.
        return sorted(available)[0]

    candidate_tables: list[str] = []
    chosen_table = _pick_default_table()
    if chosen_table:
        candidate_tables = [chosen_table]

    matches: list[dict[str, Any]] = []
    connection = sqlite3.connect(resolved_database_path)
    try:
        cursor = connection.cursor()
        for table_name in candidate_tables:
            columns = set(_load_table_columns(resolved_database_path, table_name))
            if not {"d", "p", "title"}.issubset(columns):
                continue
            select_cols = ["d", "p"]
            if "d1" in columns:
                select_cols.append("d1")
            select_cols.append("title")
            cursor.execute(
                f"select {', '.join(select_cols)} from [{table_name}] where lower(replace(title, ' ', '')) = lower(?)",
                (normalized_designation,),
            )
            for row in cursor.fetchall():
                entry = dict(zip(select_cols, row))
                matches.append(
                    {
                        "table_name": table_name,
                        "display_name": str((descriptions.get(table_name) or {}).get("display_name") or table_name),
                        "d": float(entry.get("d") or 0.0),
                        "p": float(entry.get("p") or 0.0),
                        "d1": float(entry.get("d1")) if isinstance(entry.get("d1"), int | float) else None,
                        "designation": str(entry.get("title") or ""),
                    }
                )
    finally:
        connection.close()

    return {
        "database_path": resolved_database_path or None,
        "catalog_found": True,
        "designation": normalized_designation,
        "thread_type": str(thread_type or "") or None,
        "standard": str(standard or "") or None,
        "searched_tables": list(candidate_tables),
        "matches": matches,
    }


def resolve_thread_standard(
    value: Any,
    *,
    database_path: str | None = None,
) -> dict[str, Any]:
    resolved_database_path = str(database_path or find_thread_database_path() or "").strip()
    normalized_key = _normalize_standard_key(value)
    table_name = THREAD_STANDARD_ALIASES.get(normalized_key)
    descriptions = _load_standard_descriptions(resolved_database_path) if resolved_database_path else {}
    if table_name is None and normalized_key:
        for payload in descriptions.values():
            if normalized_key in {
                _normalize_standard_key(payload["table_name"]),
                _normalize_standard_key(payload["display_name"]),
            }:
                table_name = str(payload["table_name"])
                break
    if table_name is None:
        table_name = DEFAULT_THREAD_STANDARD_TABLE
    payload = dict(descriptions.get(table_name) or {})
    return {
        "database_path": resolved_database_path or None,
        "catalog_found": bool(descriptions),
        "table_name": table_name,
        "display_name": str(payload.get("display_name") or table_name),
        "internal_diameter_coefficient": float(payload.get("internal_diameter_coefficient") or 0.0),
        "conical_thread_angle": float(payload.get("conical_thread_angle") or 0.0),
    }


def resolve_thread_standard_entry(
    value: Any,
    diameter: float,
    pitch: float,
    *,
    database_path: str | None = None,
) -> dict[str, Any]:
    standard = resolve_thread_standard(value, database_path=database_path)
    resolved_database_path = standard.get("database_path")
    table_name = str(standard.get("table_name") or "")
    if not resolved_database_path or not table_name:
        return {
            **standard,
            "entry_found": False,
            "designation": "",
            "entry": {
                "d": float(diameter),
                "p": float(pitch),
            },
        }

    database_path_value = str(resolved_database_path)
    columns = _load_table_columns(database_path_value, table_name)
    if not columns:
        raise ValueError(f"Thread standard table {table_name} is missing in {database_path_value}")

    tol = 1e-6
    connection = sqlite3.connect(database_path_value)
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"select * from [{table_name}] where abs(d - ?) < ? and abs(p - ?) < ? limit 2",
            (float(diameter), tol, float(pitch), tol),
        )
        rows = cursor.fetchall()
        if not rows:
            cursor.execute(
                f"select * from [{table_name}] order by abs(d - ?) + abs(p - ?) limit 1",
                (float(diameter), float(pitch)),
            )
            rows = cursor.fetchall()
            if not rows:
                raise ValueError("Thread standard %s has no rows" % (table_name,))
            candidate = dict(zip(columns, rows[0]))
            candidate_diameter = float(candidate.get("d") or 0.0)
            candidate_pitch = float(candidate.get("p") or 0.0)
            score = abs(candidate_diameter - float(diameter)) + abs(candidate_pitch - float(pitch))
            if score > tol:
                raise ValueError(
                    "Thread standard %s has no row for diameter=%s pitch=%s" % (table_name, diameter, pitch)
                )
            best_row = candidate
        else:
            best_row = dict(zip(columns, rows[0]))
    finally:
        connection.close()

    entry = {key: (float(value) if isinstance(value, int | float) else value) for key, value in best_row.items()}
    entry = _append_metric_thread_geometry(entry, standard=standard)
    return {
        **standard,
        "entry_found": True,
        "designation": str(entry.get("title") or ""),
        "entry": entry,
    }
