from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any


SPRING_CATALOG_SCHEMA_VERSION = "1.0"
SPRING_CATALOG_DIR_ENV = "KOMPAS_MCP_SPRING_CATALOG_DIR"


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
    source_path: str = ""

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
        if self.source_path:
            result["source_path"] = self.source_path
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


def _torsion_entry(
    entry_id: str,
    *,
    wire_diameter: float,
    outer_diameter: float,
    turns: float,
    leg_length: float,
    end_type: str,
    load_class: str,
    tags: tuple[str, ...],
    start_phase_degrees: float = 0.0,
    turn_direction: str = "right",
) -> SpringCatalogEntry:
    title = "Torsion spring d%s D%s N%s %s" % (
        _format_size_token(wire_diameter),
        _format_size_token(outer_diameter),
        _format_size_token(turns),
        end_type,
    )
    return SpringCatalogEntry(
        id=entry_id,
        spring_type="torsion_spring",
        catalog_id="torsion_metric_preferred_v1",
        title=title,
        load_class=load_class,
        tags=tags,
        params={
            "wire_diameter": float(wire_diameter),
            "outer_diameter": float(outer_diameter),
            "turns": float(turns),
            "leg_length": float(leg_length),
            "end_type": end_type,
            "start_phase_degrees": float(start_phase_degrees),
            "turn_direction": turn_direction,
            "catalog_entry_id": entry_id,
            "catalog_id": "torsion_metric_preferred_v1",
        },
        note="Preferred metric torsion-spring CAD seed entry; verify against the required supplier or official standard table before production release.",
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


_TORSION_METRIC_PREFERRED_ENTRIES: tuple[SpringCatalogEntry, ...] = (
    _torsion_entry("tor-metric-012-140-n4-tangent-light", wire_diameter=1.2, outer_diameter=14.0, turns=4.0, leg_length=25.0, end_type="tangent_legs", load_class="light", tags=("compact", "tangent_legs")),
    _torsion_entry("tor-metric-016-180-n5-tangent-medium", wire_diameter=1.6, outer_diameter=18.0, turns=5.0, leg_length=32.0, end_type="tangent_legs", load_class="medium", tags=("general", "tangent_legs")),
    _torsion_entry("tor-metric-020-220-n5-tangent-medium", wire_diameter=2.0, outer_diameter=22.0, turns=5.0, leg_length=35.0, end_type="tangent_legs", load_class="medium", tags=("general", "tangent_legs")),
    _torsion_entry("tor-metric-025-280-n6-tangent-heavy", wire_diameter=2.5, outer_diameter=28.0, turns=6.0, leg_length=42.0, end_type="tangent_legs", load_class="heavy", tags=("large", "tangent_legs")),
    _torsion_entry("tor-metric-020-220-n5-radial-phase30", wire_diameter=2.0, outer_diameter=22.0, turns=5.0, leg_length=35.0, end_type="radial_legs", load_class="medium", tags=("mechanics_coverage", "radial_legs"), start_phase_degrees=30.0),
    _torsion_entry("tor-metric-020-220-n5-axial-phase30", wire_diameter=2.0, outer_diameter=22.0, turns=5.0, leg_length=35.0, end_type="axial_transition_legs", load_class="medium", tags=("mechanics_coverage", "axial_transition_legs"), start_phase_degrees=30.0),
    _torsion_entry("tor-metric-020-220-n5-radial-left-phase30", wire_diameter=2.0, outer_diameter=22.0, turns=5.0, leg_length=35.0, end_type="radial_legs", load_class="medium", tags=("mechanics_coverage", "radial_legs", "left_hand"), start_phase_degrees=30.0, turn_direction="left"),
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
    SpringCatalog(
        id="torsion_metric_preferred_v1",
        spring_type="torsion_spring",
        title="Torsion Spring Preferred Metric Size Grid",
        standard_family="metric_preferred_stock_grid",
        source_kind="project_seed_catalog",
        source_note=(
            "Seed catalog of preferred metric CAD sizes for the live-verified torsion_spring generator. "
            "It is intentionally source-tagged as project data, not as an official GOST/DIN table."
        ),
        entries=_TORSION_METRIC_PREFERRED_ENTRIES,
    ),
)


def configured_spring_catalog_dir() -> Path | None:
    configured = os.getenv(SPRING_CATALOG_DIR_ENV, "").strip()
    return Path(configured) if configured else None


def load_spring_catalog_directory(catalog_dir: str | None = None) -> dict[str, Any]:
    directory = Path(catalog_dir) if catalog_dir else configured_spring_catalog_dir()
    catalogs = list(SPRING_CATALOGS)
    errors: list[dict[str, Any]] = []
    sources: list[str] = []
    if directory is None:
        return {"catalogs": catalogs, "errors": errors, "sources": sources, "catalog_dir": None}
    if not directory.exists():
        return {
            "catalogs": catalogs,
            "errors": [{"error": "catalog_dir_not_found", "catalog_dir": str(directory)}],
            "sources": sources,
            "catalog_dir": str(directory),
        }
    if not directory.is_dir():
        return {
            "catalogs": catalogs,
            "errors": [{"error": "catalog_dir_is_not_directory", "catalog_dir": str(directory)}],
            "sources": sources,
            "catalog_dir": str(directory),
        }
    known_catalog_ids = {catalog.id for catalog in catalogs}
    known_entry_ids = {entry.id for catalog in catalogs for entry in catalog.entries}
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append({"error": "catalog_json_read_failed", "source_path": str(path), "detail": str(exc)})
            continue
        source_catalogs = payload.get("catalogs") if isinstance(payload, dict) and "catalogs" in payload else [payload]
        if not isinstance(source_catalogs, list):
            errors.append({"error": "catalogs_must_be_list", "source_path": str(path)})
            continue
        for raw_catalog in source_catalogs:
            try:
                catalog = _catalog_from_mapping(raw_catalog, source_path=str(path))
            except ValueError as exc:
                errors.append({"error": "catalog_schema_invalid", "source_path": str(path), "detail": str(exc)})
                continue
            if catalog.id in known_catalog_ids:
                errors.append({"error": "duplicate_catalog_id", "catalog_id": catalog.id, "source_path": str(path)})
                continue
            local_entry_ids = [entry.id for entry in catalog.entries]
            duplicate_local_entry = next((entry_id for entry_id in local_entry_ids if local_entry_ids.count(entry_id) > 1), None)
            if duplicate_local_entry:
                errors.append({"error": "duplicate_entry_id", "catalog_id": catalog.id, "entry_id": duplicate_local_entry, "source_path": str(path)})
                continue
            duplicate_entry = next((entry.id for entry in catalog.entries if entry.id in known_entry_ids), None)
            if duplicate_entry:
                errors.append({"error": "duplicate_entry_id", "catalog_id": catalog.id, "entry_id": duplicate_entry, "source_path": str(path)})
                continue
            known_catalog_ids.add(catalog.id)
            known_entry_ids.update(entry.id for entry in catalog.entries)
            catalogs.append(catalog)
            sources.append(str(path))
    return {"catalogs": catalogs, "errors": errors, "sources": sources, "catalog_dir": str(directory)}


def _catalog_from_mapping(raw_catalog: Any, *, source_path: str) -> SpringCatalog:
    if not isinstance(raw_catalog, dict):
        raise ValueError("catalog must be an object")
    required_catalog_fields = ("id", "spring_type", "title", "standard_family", "source_kind", "source_note", "entries")
    missing_catalog_fields = [field for field in required_catalog_fields if not raw_catalog.get(field)]
    if missing_catalog_fields:
        raise ValueError("missing catalog fields: %s" % ", ".join(missing_catalog_fields))
    raw_entries = raw_catalog.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("entries must be a non-empty list")
    entries: list[SpringCatalogEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError("entry must be an object")
        required_entry_fields = ("id", "title", "load_class", "params")
        missing_entry_fields = [field for field in required_entry_fields if not raw_entry.get(field)]
        if missing_entry_fields:
            raise ValueError("entry missing fields: %s" % ", ".join(missing_entry_fields))
        params = raw_entry.get("params")
        if not isinstance(params, dict):
            raise ValueError("entry params must be an object")
        entry_id = str(raw_entry["id"])
        params = deepcopy(params)
        params["catalog_id"] = str(raw_catalog["id"])
        params["catalog_entry_id"] = entry_id
        entries.append(
            SpringCatalogEntry(
                id=entry_id,
                spring_type=str(raw_catalog["spring_type"]),
                catalog_id=str(raw_catalog["id"]),
                title=str(raw_entry["title"]),
                load_class=str(raw_entry["load_class"]),
                tags=tuple(str(tag) for tag in raw_entry.get("tags") or ()),
                note=str(raw_entry.get("note") or ""),
                params=params,
            )
        )
    return SpringCatalog(
        id=str(raw_catalog["id"]),
        spring_type=str(raw_catalog["spring_type"]),
        title=str(raw_catalog["title"]),
        standard_family=str(raw_catalog["standard_family"]),
        source_kind=str(raw_catalog["source_kind"]),
        source_note=str(raw_catalog["source_note"]),
        entries=tuple(entries),
        source_path=source_path,
    )


def validate_spring_catalogs(*, include_preview: bool = False, catalog_dir: str | None = None) -> dict[str, Any]:
    registry = load_spring_catalog_directory(catalog_dir)
    catalogs = registry["catalogs"]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    catalog_ids: set[str] = set()
    entry_ids: set[str] = set()
    entry_count = 0

    for catalog in catalogs:
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
                    preview = resolve_spring_catalog_entry(catalog.id, entry.id, include_preview=True, catalog_dir=catalog_dir).get("preview") or {}
                except Exception as exc:
                    errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "error": "preview_exception", "detail": str(exc)})
                else:
                    if not preview.get("operations"):
                        errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "error": "preview_missing_operations", "ok": preview.get("ok"), "detail": preview.get("error")})

    return {
        "ok": not registry["errors"] and not errors,
        "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        "catalog_count": len(catalogs),
        "entry_count": entry_count,
        "include_preview": bool(include_preview),
        "catalog_dir": registry["catalog_dir"],
        "sources": registry["sources"],
        "errors": registry["errors"] + errors,
        "warnings": warnings,
    }


def list_spring_catalogs(
    spring_type: str | None = None,
    *,
    include_entries: bool = False,
    catalog_dir: str | None = None,
) -> dict[str, Any]:
    registry = load_spring_catalog_directory(catalog_dir)
    catalogs = [catalog for catalog in registry["catalogs"] if spring_type in (None, "", catalog.spring_type)]
    return {
        "ok": not registry["errors"],
        "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        "catalog_dir": registry["catalog_dir"],
        "sources": registry["sources"],
        "errors": registry["errors"],
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
    end_type: str | None = None,
    leg_length: float | None = None,
    load_class: str | None = None,
    tag: str | None = None,
    limit: int = 50,
    catalog_dir: str | None = None,
) -> dict[str, Any]:
    registry = load_spring_catalog_directory(catalog_dir)
    matches: list[dict[str, Any]] = []
    limit = max(1, min(int(limit or 50), 200))
    for catalog in registry["catalogs"]:
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
            if end_type not in (None, "", params.get("end_type")):
                continue
            if not _matches_float(params.get("leg_length"), leg_length):
                continue
            matches.append(entry.to_dict(include_params=True))
            if len(matches) >= limit:
                break
        if len(matches) >= limit:
            break
    return {
        "ok": not registry["errors"],
        "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        "catalog_dir": registry["catalog_dir"],
        "sources": registry["sources"],
        "errors": registry["errors"],
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
    target_leg_length: float | None = None,
    load_class: str | None = None,
    hook_type: str | None = None,
    end_type: str | None = None,
    tag: str | None = None,
    limit: int = 10,
    catalog_dir: str | None = None,
) -> dict[str, Any]:
    registry = load_spring_catalog_directory(catalog_dir)
    scored: list[dict[str, Any]] = []
    limit = max(1, min(int(limit or 10), 50))
    for catalog in registry["catalogs"]:
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
            if end_type not in (None, "", params.get("end_type")):
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
                target_leg_length=target_leg_length,
            )
            item = entry.to_dict(include_params=True)
            item["score"] = score
            item["score_breakdown"] = breakdown
            scored.append(item)
    scored.sort(key=lambda item: (float(item.get("score") or 0.0), str(item.get("id") or "")))
    return {
        "ok": not registry["errors"],
        "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        "catalog_dir": registry["catalog_dir"],
        "sources": registry["sources"],
        "errors": registry["errors"],
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
    catalog_dir: str | None = None,
) -> dict[str, Any]:
    registry = load_spring_catalog_directory(catalog_dir)
    if registry["errors"]:
        raise ValueError("Spring catalog directory contains invalid files: %s" % registry["errors"])
    catalog, entry = _find_catalog_entry(catalog_id, entry_id, registry["catalogs"])
    params = deepcopy(entry.params)
    params.pop("catalog_id", None)
    params.pop("catalog_entry_id", None)
    params.update(deepcopy(overrides or {}))
    params["catalog_id"] = catalog.id
    params["catalog_entry_id"] = entry.id
    result: dict[str, Any] = {
        "ok": True,
        "schema_version": SPRING_CATALOG_SCHEMA_VERSION,
        "catalog_dir": registry["catalog_dir"],
        "sources": registry["sources"],
        "catalog": catalog.to_dict(include_entries=False),
        "entry": entry.to_dict(include_params=False),
        "scenario": entry.spring_type,
        "params": params,
    }
    if include_preview:
        from .parametric import preview_part_scenario

        result["preview"] = preview_part_scenario(entry.spring_type, params)
    return result


def _find_catalog_entry(
    catalog_id: str,
    entry_id: str,
    catalogs: list[SpringCatalog] | tuple[SpringCatalog, ...] = SPRING_CATALOGS,
) -> tuple[SpringCatalog, SpringCatalogEntry]:
    for catalog in catalogs:
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
    elif catalog.spring_type == "torsion_spring":
        for field_name in ("turns", "leg_length"):
            if not _positive_float(params.get(field_name)):
                errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "field": field_name, "error": "expected_positive_number"})
        if params.get("end_type") not in {"tangent_legs", "radial_legs", "axial_transition_legs"}:
            errors.append({"catalog_id": catalog.id, "entry_id": entry.id, "error": "invalid_torsion_end_type"})
    else:
        warnings.append({"catalog_id": catalog.id, "entry_id": entry.id, "warning": "unknown_spring_type_not_geometry_validated"})


def _score_entry_against_targets(params: dict[str, Any], **targets: float | None) -> tuple[float, list[dict[str, Any]]]:
    comparisons: list[dict[str, Any]] = []
    _append_score(comparisons, "wire_diameter", params.get("wire_diameter"), targets.get("target_wire_diameter"))
    _append_score(comparisons, "outer_diameter", params.get("outer_diameter"), targets.get("target_outer_diameter"))
    _append_score(comparisons, "standard_length", params.get("standard_length"), targets.get("target_standard_length"))
    _append_score(comparisons, "height", params.get("height"), targets.get("target_height"))
    if targets.get("target_length") is not None:
        if params.get("standard_length") is not None:
            length_value = params.get("standard_length")
            length_field = "standard_length"
        elif params.get("height") is not None:
            length_value = params.get("height")
            length_field = "height"
        else:
            length_value = params.get("leg_length")
            length_field = "leg_length"
        _append_score(comparisons, length_field, length_value, targets.get("target_length"), alias="length")
    _append_score(comparisons, "turns", params.get("turns") or params.get("working_turns"), targets.get("target_turns"))
    _append_score(comparisons, "pitch", params.get("pitch"), targets.get("target_pitch"))
    _append_score(comparisons, "leg_length", params.get("leg_length"), targets.get("target_leg_length"))
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
