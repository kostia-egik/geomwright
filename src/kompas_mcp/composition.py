from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import Any
from zipfile import ZipFile


_PATH_PATTERN = re.compile(r"<path>(.*?)</path>", re.S)


def _read_sources_text(assembly_path: Path) -> str:
    with ZipFile(assembly_path, "r") as archive:
        return archive.read("Sources").decode("utf-16")


def _stored_path_to_absolute(assembly_path: Path, stored_path: str) -> str | None:
    if not stored_path or stored_path.startswith(">"):
        return None

    candidate = Path(stored_path)
    if candidate.is_absolute():
        return str(candidate)

    return str((assembly_path.parent / candidate).resolve(strict=False))


def _reference_type(stored_path: str) -> str:
    if not stored_path:
        return "empty"
    if stored_path.startswith(">"):
        return "embedded"
    if Path(stored_path).is_absolute():
        return "absolute"
    return "relative"


def _location_type(assembly_dir: Path, stored_path: str, resolved_path: str | None, exists: bool) -> str:
    reference_type = _reference_type(stored_path)
    if reference_type == "embedded":
        return "embedded"
    if resolved_path is None:
        return "unknown"
    if not exists:
        return "missing"

    try:
        Path(resolved_path).relative_to(assembly_dir)
        return "local"
    except ValueError:
        if stored_path.startswith("..\\") or stored_path.startswith("../"):
            return "parent_relative"
        if reference_type == "absolute":
            return "absolute_external"
        return "external"


def _relative_to_assembly(assembly_dir: Path, resolved_path: str | None) -> str | None:
    if resolved_path is None:
        return None

    try:
        return str(Path(resolved_path).relative_to(assembly_dir))
    except ValueError:
        return None


def read_file_composition(assembly_path: str) -> dict[str, Any]:
    assembly = Path(assembly_path)
    if not assembly.exists():
        raise RuntimeError(f"Assembly does not exist: {assembly_path}")

    source_text = _read_sources_text(assembly)
    items: list[dict[str, Any]] = []
    summary = {
        "total": 0,
        "existing": 0,
        "missing": 0,
        "embedded": 0,
        "absolute": 0,
        "relative": 0,
        "local": 0,
        "external": 0,
    }

    for index, match in enumerate(_PATH_PATTERN.finditer(source_text)):
        stored_path = html.unescape(match.group(1))
        resolved_path = _stored_path_to_absolute(assembly, stored_path)
        exists = bool(resolved_path and Path(resolved_path).exists())
        reference_type = _reference_type(stored_path)
        location_type = _location_type(assembly.parent, stored_path, resolved_path, exists)
        relative_to_assembly = _relative_to_assembly(assembly.parent, resolved_path)
        display_name = Path(resolved_path).name if resolved_path else Path(stored_path.lstrip(">")).name

        items.append(
            {
                "item_id": f"source/{index}",
                "name": display_name,
                "stored_path": stored_path,
                "resolved_path": resolved_path,
                "reference_type": reference_type,
                "location_type": location_type,
                "relative_to_assembly": relative_to_assembly,
                "exists": exists,
                "extension": Path(display_name).suffix.lower(),
            }
        )

        summary["total"] += 1
        if exists:
            summary["existing"] += 1
        else:
            summary["missing"] += 1

        if reference_type == "embedded":
            summary["embedded"] += 1
        elif reference_type == "absolute":
            summary["absolute"] += 1
        elif reference_type == "relative":
            summary["relative"] += 1

        if location_type == "local":
            summary["local"] += 1
        elif location_type in {"external", "parent_relative", "absolute_external"}:
            summary["external"] += 1

    return {
        "assembly_path": str(assembly),
        "assembly_dir": str(assembly.parent),
        "summary": summary,
        "items": items,
    }
