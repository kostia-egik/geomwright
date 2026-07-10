from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


SPRING_CATALOG_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class SpringCatalogEntry:
    id: str
    spring_type: str
    catalog_id: str
    title: str
    params: dict[str, Any]
    load_class: str
    tags: tuple[str, ...] = ()
    note: str = ""

    def to_dict(self, *, include_params: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "spring_type": self.spring_type,
            "catalog_id": self.catalog_id,
            "title": self.title,
            "load_class": self.load_class,
            "tags": list(self.tags),
        }
        if self.note:
            result["note"] = self.note
        if include_params:
            result["params"] = deepcopy(self.params)
        return result


@dataclass(frozen=True)
class SpringCatalog:
    id: str
    spring_type: str
    title: str
    standard_family: str
    source_kind: str
    source_note: str
    entries: tuple[SpringCatalogEntry, ...]

    def to_dict(self, *, include_entries: bool = False, include_params: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "spring_type": self.spring_type,
            "title": self.title,
            "standard_family": self.standard_family,
            "source_kind": self.source_kind,
            "source_note": self.source_note,
            "entry_count": len(self.entries),
            "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        }
        if include_entries:
            result["entries"] = [entry.to_dict(include_params=include_params) for entry in self.entries]
        return result


def _compression_entry(
    entry_id: str,
    *,
    wire_diameter: float,
    outer_diameter: float,
    standard_length: float,
    working_turns: float,
    load_class: str,
    tags: tuple[str, ...],
) -> SpringCatalogEntry:
    title = "Compression spring d%s D%s L%s" % (
        _format_size_token(wire_diameter),
        _format_size_token(outer_diameter),
        _format_size_token(standard_length),
    )
    return SpringCatalogEntry(
        id=entry_id,
        spring_type="compression_spring",
        catalog_id="compression_metric_preferred_v1",
        title=title,
        load_class=load_class,
        tags=tags,
        params={
            "wire_diameter": float(wire_diameter),
            "outer_diameter": float(outer_diameter),
            "standard_length": float(standard_length),
            "working_turns": float(working_turns),
            "end_turns_per_side": 0.75,
            "ground_turns_per_side": 0.75,
            "catalog_entry_id": entry_id,
            "catalog_id": "compression_metric_preferred_v1",
        },
        note="Preferred metric stock-grid seed entry; verify against the required supplier or official standard table before production release.",
    )


def _extension_entry(
    entry_id: str,
    *,
    wire_diameter: float,
    outer_diameter: float,
    height: float,
    turns: float,
    pitch: float,
    hook_type: str,
    load_class: str,
    tags: tuple[str, ...],
) -> SpringCatalogEntry:
    title = "Extension spring d%s D%s H%s %s" % (
        _format_size_token(wire_diameter),
        _format_size_token(outer_diameter),
        _format_size_token(height),
        hook_type,
    )
    return SpringCatalogEntry(
        id=entry_id,
        spring_type="extension_spring",
        catalog_id="extension_metric_preferred_v1",
        title=title,
        load_class=load_class,
        tags=tags,
        params={
            "wire_diameter": float(wire_diameter),
            "outer_diameter": float(outer_diameter),
            "height": float(height),
            "turns": float(turns),
            "pitch": float(pitch),
            "hook_type": hook_type,
            "catalog_entry_id": entry_id,
            "catalog_id": "extension_metric_preferred_v1",
        },
        note="Preferred metric extension-spring CAD seed entry; verify against the required supplier or official standard table before production release.",
    )


def _format_size_token(value: float) -> str:
    text = ("%.3f" % float(value)).rstrip("0").rstrip(".")
    return text.replace(".", "p")


_COMPRESSION_METRIC_PREFERRED_ENTRIES: tuple[SpringCatalogEntry, ...] = (
    _compression_entry("cmp-metric-008-080-025-light", wire_diameter=0.8, outer_diameter=8.0, standard_length=25.0, working_turns=6.0, load_class="light", tags=("compact", "small")),
    _compression_entry("cmp-metric-010-100-030-light", wire_diameter=1.0, outer_diameter=10.0, standard_length=30.0, working_turns=6.0, load_class="light", tags=("compact", "small")),
    _compression_entry("cmp-metric-012-120-040-light", wire_diameter=1.2, outer_diameter=12.0, standard_length=40.0, working_turns=7.0, load_class="light", tags=("general",)),
    _compression_entry("cmp-metric-012-140-050-medium", wire_diameter=1.2, outer_diameter=14.0, standard_length=50.0, working_turns=8.0, load_class="medium", tags=("general",)),
    _compression_entry("cmp-metric-016-160-050-medium", wire_diameter=1.6, outer_diameter=16.0, standard_length=50.0, working_turns=7.0, load_class="medium", tags=("general",)),
    _compression_entry("cmp-metric-016-180-063-light", wire_diameter=1.6, outer_diameter=18.0, standard_length=63.0, working_turns=9.0, load_class="light", tags=("long",)),
    _compression_entry("cmp-metric-020-200-063-medium", wire_diameter=2.0, outer_diameter=20.0, standard_length=63.0, working_turns=8.0, load_class="medium", tags=("general",)),
    _compression_entry("cmp-metric-020-220-080-light", wire_diameter=2.0, outer_diameter=22.0, standard_length=80.0, working_turns=10.0, load_class="light", tags=("long",)),
    _compression_entry("cmp-metric-025-250-080-medium", wire_diameter=2.5, outer_diameter=25.0, standard_length=80.0, working_turns=8.0, load_class="medium", tags=("general",)),
    _compression_entry("cmp-metric-025-280-100-light", wire_diameter=2.5, outer_diameter=28.0, standard_length=100.0, working_turns=11.0, load_class="light", tags=("long",)),
    _compression_entry("cmp-metric-030-300-100-medium", wire_diameter=3.0, outer_diameter=30.0, standard_length=100.0, working_turns=9.0, load_class="medium", tags=("general",)),
    _compression_entry("cmp-metric-030-320-125-light", wire_diameter=3.0, outer_diameter=32.0, standard_length=125.0, working_turns=12.0, load_class="light", tags=("long",)),
    _compression_entry("cmp-metric-035-350-100-heavy", wire_diameter=3.5, outer_diameter=35.0, standard_length=100.0, working_turns=8.0, load_class="heavy", tags=("compact",)),
    _compression_entry("cmp-metric-040-400-125-medium", wire_diameter=4.0, outer_diameter=40.0, standard_length=125.0, working_turns=10.0, load_class="medium", tags=("general",)),
    _compression_entry("cmp-metric-050-500-160-heavy", wire_diameter=5.0, outer_diameter=50.0, standard_length=160.0, working_turns=10.0, load_class="heavy", tags=("large",)),
    _compression_entry("cmp-metric-060-630-200-heavy", wire_diameter=6.0, outer_diameter=63.0, standard_length=200.0, working_turns=11.0, load_class="heavy", tags=("large",)),
)


_EXTENSION_METRIC_PREFERRED_ENTRIES: tuple[SpringCatalogEntry, ...] = (
    _extension_entry("ext-metric-010-100-040-machine-light", wire_diameter=1.0, outer_diameter=10.0, height=40.0, turns=5.0, pitch=7.0, hook_type="machine_hooks", load_class="light", tags=("compact", "machine_hooks")),
    _extension_entry("ext-metric-012-120-050-machine-light", wire_diameter=1.2, outer_diameter=12.0, height=50.0, turns=5.0, pitch=8.0, hook_type="machine_hooks", load_class="light", tags=("compact", "machine_hooks")),
    _extension_entry("ext-metric-016-160-063-machine-medium", wire_diameter=1.6, outer_diameter=16.0, height=63.0, turns=6.0, pitch=8.0, hook_type="machine_hooks", load_class="medium", tags=("general", "machine_hooks")),
    _extension_entry("ext-metric-020-200-080-machine-medium", wire_diameter=2.0, outer_diameter=20.0, height=80.0, turns=6.0, pitch=10.0, hook_type="machine_hooks", load_class="medium", tags=("general", "machine_hooks")),
    _extension_entry("ext-metric-025-250-100-machine-heavy", wire_diameter=2.5, outer_diameter=25.0, height=100.0, turns=7.0, pitch=11.0, hook_type="machine_hooks", load_class="heavy", tags=("large", "machine_hooks")),
    _extension_entry("ext-metric-012-120-050-open-light", wire_diameter=1.2, outer_diameter=12.0, height=50.0, turns=5.0, pitch=8.0, hook_type="open_loop_hooks", load_class="light", tags=("compact", "open_loop_hooks")),
    _extension_entry("ext-metric-016-180-070-open-medium", wire_diameter=1.6, outer_diameter=18.0, height=70.0, turns=6.0, pitch=8.5, hook_type="open_loop_hooks", load_class="medium", tags=("general", "open_loop_hooks")),
    _extension_entry("ext-metric-020-220-090-open-medium", wire_diameter=2.0, outer_diameter=22.0, height=90.0, turns=7.0, pitch=10.0, hook_type="open_loop_hooks", load_class="medium", tags=("general", "open_loop_hooks")),
    _extension_entry("ext-metric-025-280-110-open-heavy", wire_diameter=2.5, outer_diameter=28.0, height=110.0, turns=8.0, pitch=11.0, hook_type="open_loop_hooks", load_class="heavy", tags=("large", "open_loop_hooks")),
    _extension_entry("ext-metric-016-160-063-center-medium", wire_diameter=1.6, outer_diameter=16.0, height=63.0, turns=6.0, pitch=8.0, hook_type="center_loop_hooks", load_class="medium", tags=("general", "center_loop_hooks")),
    _extension_entry("ext-metric-020-220-090-extended-center-medium", wire_diameter=2.0, outer_diameter=22.0, height=90.0, turns=7.0, pitch=10.0, hook_type="extended_center_loop_hooks", load_class="medium", tags=("general", "extended_center_loop_hooks")),
    _extension_entry("ext-metric-020-240-090-self-wrapping-medium", wire_diameter=2.0, outer_diameter=24.0, height=90.0, turns=7.0, pitch=10.0, hook_type="self_wrapping_hooks", load_class="medium", tags=("mechanics_coverage", "self_wrapping_hooks")),
    _extension_entry("ext-metric-020-240-090-bent-coil-medium", wire_diameter=2.0, outer_diameter=24.0, height=90.0, turns=7.0, pitch=10.0, hook_type="bent_coil_left_spike", load_class="medium", tags=("mechanics_coverage", "bent_coil_left_spike")),
)


SPRING_CATALOGS: tuple[SpringCatalog, ...] = (
    SpringCatalog(
        id="compression_metric_preferred_v1",
        spring_type="compression_spring",
        title="Compression Spring Preferred Metric Size Grid",
        standard_family="metric_preferred_stock_grid",
        source_kind="project_seed_catalog",
        source_note=(
            "Seed catalog of preferred metric CAD sizes for the stabilized compression_spring generator. "
            "It is intentionally source-tagged as project data, not as an official GOST/DIN table."
        ),
        entries=_COMPRESSION_METRIC_PREFERRED_ENTRIES,
    ),
    SpringCatalog(
        id="extension_metric_preferred_v1",
        spring_type="extension_spring",
        title="Extension Spring Preferred Metric Size Grid",
        standard_family="metric_preferred_stock_grid",
        source_kind="project_seed_catalog",
        source_note=(
            "Seed catalog of preferred metric CAD sizes for the stabilized extension_spring generator. "
            "It is intentionally source-tagged as project data, not as an official GOST/DIN table."
        ),
        entries=_EXTENSION_METRIC_PREFERRED_ENTRIES,
    ),
)


def validate_spring_catalogs(*, include_preview: bool = False) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    catalog_ids: set[str] = set()
    entry_ids: set[str] = set()
    entry_count = 0

    for catalog in SPRING_CATALOGS:
        if catalog.id in catalog_ids:
            errors.append({"catalog_id": catalog.id, "error": "duplicate_catalog_id"})
        catalog_ids.add(catalog.id)
        if not catalog.source_kind or not catalog.source_note:
            errors.append({"catalog_id": catalog.id, "error": "missing_source_metadata"})
        for entry in catalog.entries:
            entry_count += 1
            if entry.id in entry_ids:
                errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "error": "duplicate_entry_id"})
            entry_ids.add(entry.id)
            if entry.catalog_id != catalog.id:
                errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "error": "entry_catalog_id_mismatch"})
            if entry.spring_type != catalog.spring_type:
                errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "error": "entry_spring_type_mismatch"})
            if entry.params.get("catalog_id") != catalog.id or entry.params.get("catalog_entry_id") != entry.id:
                errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "error": "param_catalog_metadata_mismatch"})
            _validate_entry_geometry(catalog, entry, errors, warnings)
            if include_preview:
                try:
                    preview = resolve_spring_catalog_entry(catalog.id, entry.id, include_preview=True).get("preview") or {}
                except Exception as exc:
                    errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "error": "preview_exception", "detail": str(exc)})
                else:
                    if not preview.get("operations"):
                        errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "error": "preview_missing_operations", "ok": preview.get("ok"), "detail": preview.get("error")})

    return {
        "ok": not errors,
        "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        "catalog_count": len(SPRING_CATALOGS),
        "entry_count": entry_count,
        "include_preview": bool(include_preview),
        "errors": errors,
        "warnings": warnings,
    }


def list_spring_catalogs(spring_type: str | None = None, *, include_entries: bool = False) -> dict[str, Any]:
    catalogs = [catalog for catalog in SPRING_CATALOGS if spring_type in (None, "", catalog.spring_type)]
    return {
        "ok": True,
        "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        "catalogs": [catalog.to_dict(include_entries=include_entries, include_params=False) for catalog in catalogs],
    }


def find_spring_catalog_entries(
    *,
    spring_type: str | None = None,
    catalog_id: str | None = None,
    wire_diameter: float | None = None,
    outer_diameter: float | None = None,
    standard_length: float | None = None,
    height: float | None = None,
    turns: float | None = None,
    hook_type: str | None = None,
    load_class: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    limit = max(1, min(int(limit or 50), 200))
    for catalog in SPRING_CATALOGS:
        if spring_type not in (None, "", catalog.spring_type):
            continue
        if catalog_id not in (None, "", catalog.id):
            continue
        for entry in catalog.entries:
            params = entry.params
            if load_class not in (None, "", entry.load_class):
                continue
            if tag not in (None, "") and str(tag) not in entry.tags:
                continue
            if not _matches_float(params.get("wire_diameter"), wire_diameter):
                continue
            if not _matches_float(params.get("outer_diameter"), outer_diameter):
                continue
            if not _matches_float(params.get("standard_length"), standard_length):
                continue
            if not _matches_float(params.get("height"), height):
                continue
            if not _matches_float(params.get("turns"), turns):
                continue
            if hook_type not in (None, "", params.get("hook_type"), params.get("left_hook_type"), params.get("right_hook_type")):
                continue
            matches.append(entry.to_dict(include_params=True))
            if len(matches) >= limit:
                break
        if len(matches) >= limit:
            break
    return {
        "ok": True,
        "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        "count": len(matches),
        "entries": matches,
    }


def recommend_spring_catalog_entries(
    *,
    spring_type: str | None = None,
    catalog_id: str | None = None,
    target_wire_diameter: float | None = None,
    target_outer_diameter: float | None = None,
    target_length: float | None = None,
    target_standard_length: float | None = None,
    target_height: float | None = None,
    target_turns: float | None = None,
    target_pitch: float | None = None,
    load_class: str | None = None,
    hook_type: str | None = None,
    tag: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    limit = max(1, min(int(limit or 10), 50))
    for catalog in SPRING_CATALOGS:
        if spring_type not in (None, "", catalog.spring_type):
            continue
        if catalog_id not in (None, "", catalog.id):
            continue
        for entry in catalog.entries:
            params = entry.params
            if load_class not in (None, "", entry.load_class):
                continue
            if tag not in (None, "") and str(tag) not in entry.tags:
                continue
            if hook_type not in (None, "", params.get("hook_type"), params.get("left_hook_type"), params.get("right_hook_type")):
                continue
            score, breakdown = _score_entry_against_targets(
                params,
                target_wire_diameter=target_wire_diameter,
                target_outer_diameter=target_outer_diameter,
                target_length=target_length,
                target_standard_length=target_standard_length,
                target_height=target_height,
                target_turns=target_turns,
                target_pitch=target_pitch,
            )
            item = entry.to_dict(include_params=True)
            item["score"] = score
            item["score_breakdown"] = breakdown
            scored.append(item)
    scored.sort(key=lambda item: (float(item.get("score") or 0.0), str(item.get("id") or "")))
    return {
        "ok": True,
        "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        "count": min(len(scored), limit),
        "total_candidates": len(scored),
        "entries": scored[:limit],
    }


def resolve_spring_catalog_entry(
    catalog_id: str,
    entry_id: str,
    *,
    overrides: dict[str, Any] | None = None,
    include_preview: bool = False,
) -> dict[str, Any]:
    catalog, entry = _find_catalog_entry(catalog_id, entry_id)
    params = deepcopy(entry.params)
    params.pop("catalog_id", None)
    params.pop("catalog_entry_id", None)
    params.update(deepcopy(overrides or {}))
    params["catalog_id"] = catalog.id
    params["catalog_entry_id"] = entry.id
    result: dict[str, Any] = {
        "ok": True,
        "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        "catalog": catalog.to_dict(include_entries=False),
        "entry": entry.to_dict(include_params=False),
        "scenario": entry.spring_type,
        "params": params,
    }
    if include_preview:
        from .parametric import preview_part_scenario

        result["preview"] = preview_part_scenario(entry.spring_type, params)
    return result


def _find_catalog_entry(catalog_id: str, entry_id: str) -> tuple[SpringCatalog, SpringCatalogEntry]:
    for catalog in SPRING_CATALOGS:
        if catalog.id != catalog_id:
            continue
        for entry in catalog.entries:
            if entry.id == entry_id:
                return catalog, entry
        raise ValueError("Unknown spring catalog entry: %s" % entry_id)
    raise ValueError("Unknown spring catalog: %s" % catalog_id)


def _validate_entry_geometry(
    catalog: SpringCatalog,
    entry: SpringCatalogEntry,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    params = entry.params
    for field_name in ("wire_diameter", "outer_diameter"):
        if not _positive_float(params.get(field_name)):
            errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "field": field_name, "error": "expected_positive_number"})
    if catalog.spring_type == "compression_spring":
        for field_name in ("standard_length", "working_turns"):
            if not _positive_float(params.get(field_name)):
                errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "field": field_name, "error": "expected_positive_number"})
    elif catalog.spring_type == "extension_spring":
        for field_name in ("height", "turns", "pitch"):
            if not _positive_float(params.get(field_name)):
                errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "field": field_name, "error": "expected_positive_number"})
        if not params.get("hook_type") and not (params.get("left_hook_type") and params.get("right_hook_type")):
            errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "error": "missing_extension_hook_type"})
    else:
        warnings.append({"catalog_id": catalog.id, "entry_id": entry.id, "warning": "unknown_spring_type_not_geometry_validated"})


def _score_entry_against_targets(params: dict[str, Any], **targets: float | None) -> tuple[float, list[dict[str, Any]]]:
    comparisons: list[dict[str, Any]] = []
    _append_score(comparisons, "wire_diameter", params.get("wire_diameter"), targets.get("target_wire_diameter"))
    _append_score(comparisons, "outer_diameter", params.get("outer_diameter"), targets.get("target_outer_diameter"))
    _append_score(comparisons, "standard_length", params.get("standard_length"), targets.get("target_standard_length"))
    _append_score(comparisons, "height", params.get("height"), targets.get("target_height"))
    if targets.get("target_length") is not None:
        length_value = params.get("standard_length") if params.get("standard_length") is not None else params.get("height")
        length_field = "standard_length" if params.get("standard_length") is not None else "height"
        _append_score(comparisons, length_field, length_value, targets.get("target_length"), alias="length")
    _append_score(comparisons, "turns", params.get("turns") or params.get("working_turns"), targets.get("target_turns"))
    _append_score(comparisons, "pitch", params.get("pitch"), targets.get("target_pitch"))
    if not comparisons:
        return 0.0, []
    return sum(float(item["normalized_delta"]) for item in comparisons) / float(len(comparisons)), comparisons


def _append_score(
    comparisons: list[dict[str, Any]],
    field_name: str,
    actual: Any,
    target: float | None,
    *,
    alias: str | None = None,
) -> None:
    if target is None or actual is None:
        return
    try:
        actual_value = float(actual)
        target_value = float(target)
    except Exception:
        return
    delta = abs(actual_value - target_value)
    denominator = max(abs(target_value), 1.0)
    comparisons.append(
        {
            "field": alias or field_name,
            "source_field": field_name,
            "actual": actual_value,
            "target": target_value,
            "delta": delta,
            "normalized_delta": delta / denominator,
        }
    )


def _matches_float(actual: Any, expected: float | None, *, tolerance: float = 1e-6) -> bool:
    if expected is None:
        return True
    try:
        return abs(float(actual) - float(expected)) <= tolerance
    except Exception:
        return False


def _positive_float(value: Any) -> bool:
    try:
        return float(value) > 0.0
    except Exception:
        return False
