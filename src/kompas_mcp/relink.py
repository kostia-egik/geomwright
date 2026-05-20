from __future__ import annotations

import ctypes
import html
import json
import os
import re
import shutil
import tempfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from zipfile import ZipFile, ZipInfo

from .analyzers import flatten_tree
from .composition import read_file_composition


def _lower_parts(path: Path) -> tuple[str, ...]:
    return tuple(part.lower() for part in path.parts)


def _normalized_path(value: str) -> str:
    if not value:
        return ""
    normalized = os.path.abspath(os.path.normpath(value))
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.kernel32.GetLongPathNameW(normalized, buffer, len(buffer))
        if result:
            normalized = buffer.value
    except Exception:
        pass
    return os.path.normcase(normalized)


def _common_suffix_len(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    score = 0
    for left_part, right_part in zip(reversed(left), reversed(right)):
        if left_part != right_part:
            break
        score += 1
    return score


def _short_name(path: Path) -> str | None:
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
        if result:
            return Path(buffer.value).name.lower()
    except Exception:
        return None
    return None


def _choose_best_match(source_path: str, matches: list[Path]) -> tuple[Path | None, list[dict[str, Any]]]:
    source = Path(source_path)
    source_parts = _lower_parts(source)
    ranked: list[dict[str, Any]] = []

    for match in matches:
        match_parts = _lower_parts(match)
        ranked.append(
            {
                "path": match,
                "suffix_score": _common_suffix_len(source_parts, match_parts),
                "parent_suffix_score": _common_suffix_len(source_parts[:-1], match_parts[:-1]),
            }
        )

    ranked.sort(
        key=lambda item: (
            item["suffix_score"],
            item["parent_suffix_score"],
            len(_lower_parts(item["path"])),
        ),
        reverse=True,
    )

    if not ranked:
        return None, []

    best = ranked[0]
    if len(ranked) == 1:
        return best["path"], ranked

    second = ranked[1]
    if (
        best["suffix_score"],
        best["parent_suffix_score"],
        len(_lower_parts(best["path"])),
    ) == (
        second["suffix_score"],
        second["parent_suffix_score"],
        len(_lower_parts(second["path"])),
    ):
        return None, ranked

    return best["path"], ranked


def _build_file_index(root: Path) -> dict[str, list[Path]]:
    file_index: dict[str, list[Path]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        keys = {path.name.lower()}
        short_name = _short_name(path)
        if short_name:
            keys.add(short_name)
        for key in keys:
            file_index.setdefault(key, []).append(path)
    return file_index


def _preview_composition_relink_items(
    items: list[dict[str, Any]],
    search_root: str,
    *,
    relink_all: bool = False,
) -> dict[str, Any]:
    root = Path(search_root)
    if not root.exists():
        raise RuntimeError(f"Search root does not exist: {search_root}")

    file_index = _build_file_index(root)
    candidates: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for item in items:
        if item.get("reference_type") == "embedded":
            continue

        source_path = item.get("resolved_path") or ""
        if not source_path:
            unresolved.append(
                {
                    "item_id": item["item_id"],
                    "name": item.get("name"),
                    "old_path": item.get("stored_path") or "",
                    "reason": "missing_resolved_path",
                }
            )
            continue

        current = Path(source_path)
        if current.exists() and not relink_all:
            continue

        matches = file_index.get(current.name.lower(), [])
        if len(matches) == 1:
            new_path = str(matches[0])
            if _normalized_path(new_path) != _normalized_path(source_path):
                candidates.append(
                    {
                        "item_id": item["item_id"],
                        "name": item.get("name"),
                        "old_path": source_path,
                        "new_path": new_path,
                        "reason": "single_filename_match",
                        "reference_type": item.get("reference_type"),
                    }
                )
        elif len(matches) > 1:
            best_match, ranked = _choose_best_match(source_path, matches)
            if best_match is not None and _normalized_path(str(best_match)) != _normalized_path(source_path):
                candidates.append(
                    {
                        "item_id": item["item_id"],
                        "name": item.get("name"),
                        "old_path": source_path,
                        "new_path": str(best_match),
                        "reason": "best_suffix_match",
                        "reference_type": item.get("reference_type"),
                        "match_score": {
                            "suffix_score": ranked[0]["suffix_score"],
                            "parent_suffix_score": ranked[0]["parent_suffix_score"],
                        },
                    }
                )
            else:
                ambiguous.append(
                    {
                        "item_id": item["item_id"],
                        "name": item.get("name"),
                        "old_path": source_path,
                        "matches": [
                            {
                                "path": str(match["path"]),
                                "suffix_score": match["suffix_score"],
                                "parent_suffix_score": match["parent_suffix_score"],
                            }
                            for match in ranked[:20]
                        ],
                    }
                )
        else:
            unresolved.append(
                {
                    "item_id": item["item_id"],
                    "name": item.get("name"),
                    "old_path": source_path,
                }
            )

    return {
        "search_root": str(root),
        "summary": {
            "candidates": len(candidates),
            "ambiguous": len(ambiguous),
            "unresolved": len(unresolved),
        },
        "candidates": candidates,
        "ambiguous": ambiguous,
        "unresolved": unresolved,
    }


def _preview_composition_relink_map_items(
    items: list[dict[str, Any]],
    mapping_path: str,
) -> dict[str, Any]:
    mapping_index = _load_relink_map(mapping_path)
    candidates: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for item in items:
        if item.get("reference_type") == "embedded":
            continue

        source_path = item.get("resolved_path") or ""
        if not source_path:
            unresolved.append(
                {
                    "item_id": item["item_id"],
                    "name": item.get("name"),
                    "old_path": item.get("stored_path") or "",
                    "reason": "missing_resolved_path",
                }
            )
            continue

        matches = mapping_index.get(Path(source_path).name.lower(), [])
        if not matches:
            unresolved.append(
                {
                    "item_id": item["item_id"],
                    "name": item.get("name"),
                    "old_path": source_path,
                }
            )
            continue

        best, ranked = _choose_best_mapping(source_path, matches)
        if best is None:
            ambiguous.append(
                {
                    "item_id": item["item_id"],
                    "name": item.get("name"),
                    "old_path": source_path,
                    "matches": [
                        {
                            "old_ref": match["old_ref"],
                            "new_path": match["new_path"],
                            "suffix_score": match["suffix_score"],
                            "parent_suffix_score": match["parent_suffix_score"],
                        }
                        for match in ranked[:20]
                    ],
                }
            )
            continue

        if _normalized_path(best["new_path"]) == _normalized_path(source_path):
            continue

        candidates.append(
            {
                "item_id": item["item_id"],
                "name": item.get("name"),
                "old_path": source_path,
                "new_path": best["new_path"],
                "reason": "mapping_suffix_match",
                "reference_type": item.get("reference_type"),
                "match_score": {
                    "suffix_score": best["suffix_score"],
                    "parent_suffix_score": best["parent_suffix_score"],
                },
                "mapping_ref": best["old_ref"],
            }
        )

    return {
        "mapping_path": str(Path(mapping_path)),
        "summary": {
            "candidates": len(candidates),
            "ambiguous": len(ambiguous),
            "unresolved": len(unresolved),
        },
        "candidates": candidates,
        "ambiguous": ambiguous,
        "unresolved": unresolved,
    }


def _index_by_item_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        item["item_id"]: item
        for item in items
        if item.get("item_id")
    }


def _merge_plan_item(
    item: dict[str, Any],
    *,
    status: str,
    reason: str | None = None,
    new_path: str | None = None,
    matches: list[dict[str, Any]] | None = None,
    mapping_ref: str | None = None,
    match_score: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "item_id": item.get("item_id"),
        "name": item.get("name"),
        "status": status,
        "reason": reason,
        "stored_path": item.get("stored_path"),
        "resolved_path": item.get("resolved_path"),
        "relative_to_assembly": item.get("relative_to_assembly"),
        "reference_type": item.get("reference_type"),
        "location_type": item.get("location_type"),
        "exists": item.get("exists"),
        "new_path": new_path,
        "matches": matches or [],
        "mapping_ref": mapping_ref,
        "match_score": match_score,
    }


def _build_relink_plan(
    composition: dict[str, Any],
    preview: dict[str, Any],
    *,
    relink_source: str,
) -> dict[str, Any]:
    items = composition["items"]
    item_index = _index_by_item_id(items)
    plan_items: list[dict[str, Any]] = []
    covered_ids: set[str] = set()

    for candidate in preview["candidates"]:
        item = item_index.get(candidate["item_id"])
        if item is None:
            continue
        covered_ids.add(candidate["item_id"])
        plan_items.append(
            _merge_plan_item(
                item,
                status="candidate",
                reason=candidate.get("reason"),
                new_path=candidate.get("new_path"),
                mapping_ref=candidate.get("mapping_ref"),
                match_score=candidate.get("match_score"),
            )
        )

    for ambiguous in preview["ambiguous"]:
        item = item_index.get(ambiguous["item_id"])
        if item is None:
            continue
        covered_ids.add(ambiguous["item_id"])
        plan_items.append(
            _merge_plan_item(
                item,
                status="ambiguous",
                reason="multiple_matches",
                matches=ambiguous.get("matches"),
            )
        )

    for unresolved in preview["unresolved"]:
        item = item_index.get(unresolved["item_id"])
        if item is None:
            continue
        covered_ids.add(unresolved["item_id"])
        plan_items.append(
            _merge_plan_item(
                item,
                status="unresolved",
                reason=unresolved.get("reason") or "no_match_found",
            )
        )

    for item in items:
        if item["item_id"] in covered_ids:
            continue

        reference_type = item.get("reference_type")
        location_type = item.get("location_type")
        exists = bool(item.get("exists"))

        if reference_type == "embedded":
            status = "embedded"
            reason = "stored_inside_assembly"
        elif exists and location_type == "local":
            status = "ok_local"
            reason = "already_local"
        elif exists:
            status = "ok_external"
            reason = "existing_external_reference"
        else:
            status = "missing"
            reason = "missing_reference"

        plan_items.append(_merge_plan_item(item, status=status, reason=reason))

    grouped = {
        "candidate": [],
        "ambiguous": [],
        "unresolved": [],
        "embedded": [],
        "ok_local": [],
        "ok_external": [],
        "missing": [],
    }
    for item in plan_items:
        grouped.setdefault(item["status"], []).append(item)

    summary = {
        "total": len(plan_items),
        "candidate": len(grouped["candidate"]),
        "ambiguous": len(grouped["ambiguous"]),
        "unresolved": len(grouped["unresolved"]),
        "embedded": len(grouped["embedded"]),
        "ok_local": len(grouped["ok_local"]),
        "ok_external": len(grouped["ok_external"]),
        "missing": len(grouped["missing"]),
        "actionable": len(grouped["candidate"]),
        "blocked": len(grouped["ambiguous"]) + len(grouped["unresolved"]) + len(grouped["missing"]),
    }

    return {
        "assembly_path": composition["assembly_path"],
        "assembly_dir": composition["assembly_dir"],
        "relink_source": relink_source,
        "composition_summary": composition["summary"],
        "preview_summary": preview["summary"],
        "summary": summary,
        "candidate": grouped["candidate"],
        "ambiguous": grouped["ambiguous"],
        "unresolved": grouped["unresolved"],
        "embedded": grouped["embedded"],
        "ok_local": grouped["ok_local"],
        "ok_external": grouped["ok_external"],
        "missing": grouped["missing"],
        "items": plan_items,
    }


def _load_relink_map(mapping_path: str) -> dict[str, list[dict[str, Any]]]:
    path = Path(mapping_path)
    if not path.exists():
        raise RuntimeError(f"Mapping file does not exist: {mapping_path}")

    index: dict[str, list[dict[str, Any]]] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "->" not in raw_line:
            continue
        left, right = (part.strip() for part in raw_line.split("->", 1))
        if not left or not right:
            continue

        target = Path(right)
        if not target.exists():
            continue

        old_ref = left.replace("/", "\\")
        key = Path(old_ref).name.lower()
        if not key:
            continue

        index.setdefault(key, []).append(
            {
                "old_ref": old_ref,
                "old_parts": tuple(part.lower() for part in Path(old_ref).parts),
                "new_path": str(target),
            }
        )
    return index


def _choose_best_mapping(source_path: str, matches: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    source = Path(source_path)
    source_parts = _lower_parts(source)
    ranked: list[dict[str, Any]] = []

    for match in matches:
        old_parts = match["old_parts"]
        ranked.append(
            {
                **match,
                "suffix_score": _common_suffix_len(source_parts, old_parts),
                "parent_suffix_score": _common_suffix_len(source_parts[:-1], old_parts[:-1]),
            }
        )

    ranked.sort(
        key=lambda item: (
            item["suffix_score"],
            item["parent_suffix_score"],
            len(item["old_parts"]),
        ),
        reverse=True,
    )

    if not ranked:
        return None, []
    if len(ranked) == 1:
        return ranked[0], ranked

    best = ranked[0]
    second = ranked[1]
    if (
        best["suffix_score"],
        best["parent_suffix_score"],
        len(best["old_parts"]),
    ) == (
        second["suffix_score"],
        second["parent_suffix_score"],
        len(second["old_parts"]),
    ):
        return None, ranked

    return best, ranked


def _stored_path_to_absolute(assembly_path: Path, stored_path: str) -> str | None:
    if not stored_path or stored_path.startswith(">"):
        return None
    source = Path(stored_path)
    if source.is_absolute():
        return str(source)
    return str((assembly_path.parent / source).resolve(strict=False))


def _absolute_to_stored_path(assembly_path: Path, absolute_path: str) -> str:
    try:
        relative = os.path.relpath(absolute_path, assembly_path.parent)
    except ValueError:
        relative = absolute_path
    return relative.replace("/", "\\")


def _read_sources_text(assembly_path: str) -> str:
    with ZipFile(assembly_path, "r") as archive:
        return archive.read("Sources").decode("utf-16")


_PATH_PATTERN = re.compile(r"<path>(.*?)</path>", re.S)


def _parse_sources(assembly_path: str) -> dict[str, Any]:
    source_text = _read_sources_text(assembly_path)
    assembly = Path(assembly_path)
    sources: list[dict[str, Any]] = []

    for index, match in enumerate(_PATH_PATTERN.finditer(source_text)):
        stored_path = html.unescape(match.group(1))
        resolved_path = _stored_path_to_absolute(assembly, stored_path)
        sources.append(
            {
                "item_id": "source/%s" % index,
                "index": index,
                "stored_path": stored_path,
                "resolved_path": resolved_path,
                "span": match.span(1),
            }
        )

    return {"text": source_text, "sources": sources}


def _clone_zip_info(info: ZipInfo) -> ZipInfo:
    cloned = ZipInfo(filename=info.filename, date_time=info.date_time)
    cloned.compress_type = info.compress_type
    cloned.comment = info.comment
    cloned.extra = info.extra
    cloned.internal_attr = info.internal_attr
    cloned.external_attr = info.external_attr
    cloned.create_system = info.create_system
    cloned.create_version = info.create_version
    cloned.extract_version = info.extract_version
    cloned.flag_bits = info.flag_bits
    cloned.volume = info.volume
    return cloned


def persist_relink_paths_to_file(
    assembly_path: str,
    changes: list[dict[str, Any]],
    *,
    output_path: str | None = None,
) -> dict[str, Any]:
    source_path = Path(assembly_path)
    target_path = Path(output_path or assembly_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    parsed = _parse_sources(str(source_path))
    source_text = parsed["text"]
    sources = parsed["sources"]
    change_by_id = {change.get("item_id"): change for change in changes if change.get("item_id")}
    old_path_queues: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for change in changes:
        old_path = change.get("old_path")
        if old_path:
            old_path_queues[_normalized_path(old_path)].append(change)

    applied: list[dict[str, Any]] = []
    untouched = 0
    replacements: list[tuple[int, int, str]] = []
    for source in sources:
        change = change_by_id.get(source["item_id"])
        if change is None and source["resolved_path"]:
            queue = old_path_queues.get(_normalized_path(source["resolved_path"]))
            if queue:
                change = queue.popleft()

        if change is None or not change.get("new_path"):
            untouched += 1
            continue

        stored_path = html.escape(_absolute_to_stored_path(target_path, change["new_path"]))
        replacements.append((source["span"][0], source["span"][1], stored_path))
        applied.append(
            {
                "item_id": source["item_id"],
                "old_path": source["resolved_path"] or source["stored_path"],
                "new_path": change["new_path"],
                "stored_path": stored_path,
            }
        )

    pieces: list[str] = []
    cursor = 0
    for start, end, replacement in replacements:
        pieces.append(source_text[cursor:start])
        pieces.append(replacement)
        cursor = end
    pieces.append(source_text[cursor:])
    updated_sources = "".join(pieces).encode("utf-16")
    with tempfile.NamedTemporaryFile(prefix="kompas-relink-", suffix=target_path.suffix, delete=False) as handle:
        temp_output = Path(handle.name)

    try:
        with ZipFile(source_path, "r") as source_archive, ZipFile(temp_output, "w") as target_archive:
            for info in source_archive.infolist():
                data = source_archive.read(info.filename)
                if info.filename == "Sources":
                    data = updated_sources
                target_archive.writestr(_clone_zip_info(info), data)
        shutil.copyfile(temp_output, target_path)
    finally:
        if temp_output.exists():
            temp_output.unlink()

    return {
        "assembly_path": str(target_path),
        "applied_count": len(applied),
        "untouched_count": untouched,
        "applied": applied,
    }


def preview_relink_paths(
    tree: dict[str, Any],
    search_root: str,
    *,
    relink_all: bool = False,
) -> dict[str, Any]:
    items = [
        {
            "item_id": item["id"],
            "name": item.get("name"),
            "resolved_path": item.get("source_path"),
            "stored_path": item.get("source_path"),
            "reference_type": "unknown",
        }
        for item in flatten_tree(tree)[1:]
        if item.get("source_path")
    ]
    return _preview_composition_relink_items(items, search_root, relink_all=relink_all)


def preview_relink_map_paths(
    tree: dict[str, Any],
    mapping_path: str,
) -> dict[str, Any]:
    items = [
        {
            "item_id": item["id"],
            "name": item.get("name"),
            "resolved_path": item.get("source_path"),
            "stored_path": item.get("source_path"),
            "reference_type": "unknown",
        }
        for item in flatten_tree(tree)[1:]
        if item.get("source_path")
    ]
    return _preview_composition_relink_map_items(items, mapping_path)


def preview_file_relink_paths(
    assembly_path: str,
    search_root: str,
    *,
    relink_all: bool = False,
) -> dict[str, Any]:
    composition = read_file_composition(assembly_path)
    return {
        "assembly_path": composition["assembly_path"],
        **_preview_composition_relink_items(composition["items"], search_root, relink_all=relink_all),
    }


def preview_file_relink_map_paths(
    assembly_path: str,
    mapping_path: str,
) -> dict[str, Any]:
    composition = read_file_composition(assembly_path)
    return {
        "assembly_path": composition["assembly_path"],
        **_preview_composition_relink_map_items(composition["items"], mapping_path),
    }


def build_file_relink_plan(
    assembly_path: str,
    search_root: str,
    *,
    relink_all: bool = False,
) -> dict[str, Any]:
    composition = read_file_composition(assembly_path)
    preview = _preview_composition_relink_items(composition["items"], search_root, relink_all=relink_all)
    return _build_relink_plan(composition, preview, relink_source=str(Path(search_root)))


def build_file_relink_map_plan(
    assembly_path: str,
    mapping_path: str,
) -> dict[str, Any]:
    composition = read_file_composition(assembly_path)
    preview = _preview_composition_relink_map_items(composition["items"], mapping_path)
    return _build_relink_plan(composition, preview, relink_source=str(Path(mapping_path)))


def relink_file_to_output(
    adapter,
    *,
    assembly_path: str,
    search_root: str,
    output_path: str,
    relink_all: bool = False,
) -> dict[str, Any]:
    preview = preview_file_relink_paths(assembly_path, search_root, relink_all=relink_all)
    apply_result = adapter.relink_document_file(
        assembly_path=assembly_path,
        changes=preview["candidates"],
        output_path=output_path,
    )
    report = {
        "assembly_path": preview["assembly_path"],
        "search_root": preview["search_root"],
        "output_path": apply_result["output_path"],
        "summary": {
            **preview["summary"],
            "applied": apply_result["applied_count"],
            "failed": apply_result["failed_count"],
            "output_path": apply_result["output_path"],
        },
        "applied": apply_result["applied"],
        "failed": apply_result["failed"],
        "ambiguous": preview["ambiguous"],
        "unresolved": preview["unresolved"],
    }
    report_path = Path(output_path).with_suffix(".relink.json")
    markdown_path = Path(output_path).with_suffix(".relink.md")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_relink_report(report), encoding="utf-8")
    return {
        "output_path": apply_result["output_path"],
        "json_report_path": str(report_path),
        "markdown_report_path": str(markdown_path),
        "summary": report["summary"],
    }


def relink_file_from_map_to_output(
    adapter,
    *,
    assembly_path: str,
    mapping_path: str,
    output_path: str,
) -> dict[str, Any]:
    preview = preview_file_relink_map_paths(assembly_path, mapping_path)
    apply_result = adapter.relink_document_file(
        assembly_path=assembly_path,
        changes=preview["candidates"],
        output_path=output_path,
    )
    report = {
        "assembly_path": preview["assembly_path"],
        "mapping_path": preview["mapping_path"],
        "output_path": apply_result["output_path"],
        "summary": {
            **preview["summary"],
            "applied": apply_result["applied_count"],
            "failed": apply_result["failed_count"],
        },
        "applied": apply_result["applied"],
        "failed": apply_result["failed"],
        "ambiguous": preview["ambiguous"],
        "unresolved": preview["unresolved"],
    }

    report_path = Path(output_path).with_suffix(".relink.json")
    markdown_path = Path(output_path).with_suffix(".relink.md")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_relink_report(report), encoding="utf-8")
    return {
        "output_path": apply_result["output_path"],
        "json_report_path": str(report_path),
        "markdown_report_path": str(markdown_path),
        "summary": report["summary"],
    }


def relink_project_root(
    adapter,
    *,
    search_root: str,
    document_id: str | None = None,
    relink_all: bool = False,
    save: bool = False,
) -> dict[str, Any]:
    before = adapter.get_document_composition(document_id=document_id)
    preview = _preview_composition_relink_items(before["items"], search_root, relink_all=relink_all)
    apply_result = adapter.apply_relink_paths(
        preview["candidates"],
        document_id=before["document"]["id"],
        save=save,
        close_after_save=save,
    )
    after = None if save else adapter.get_document_composition(document_id=apply_result["document"]["id"])

    return {
        "document_before": before["document"],
        "document_after": apply_result["document"] if save else after["document"],
        "search_root": preview["search_root"],
        "summary": {
            **preview["summary"],
            "applied": apply_result["applied_count"],
            "failed": apply_result["failed_count"],
            "saved": apply_result["saved"],
        },
        "applied": apply_result["applied"],
        "failed": apply_result["failed"],
        "ambiguous": preview["ambiguous"],
        "unresolved": preview["unresolved"],
    }


def relink_to_export(
    adapter,
    *,
    search_root: str,
    document_id: str | None = None,
    relink_all: bool = False,
    suffix: str = "relinked",
) -> dict[str, Any]:
    result = relink_project_root(
        adapter,
        search_root=search_root,
        document_id=document_id,
        relink_all=relink_all,
        save=False,
    )
    export_result = adapter.save_export_copy(
        document_id=result["document_after"]["id"],
        suffix=suffix,
        close_after_save=True,
    )

    after_export_document = dict(result["document_after"])
    after_export_document["path"] = export_result["export_path"]
    after_export_document["id"] = export_result["export_path"]
    after_export_document["active"] = False

    report = {
        "document_before": result["document_before"],
        "document_after_relink": result["document_after"],
        "document_after_export": after_export_document,
        "search_root": result["search_root"],
        "summary": result["summary"],
        "applied": result["applied"],
        "failed": result["failed"],
        "ambiguous": result["ambiguous"],
        "unresolved": result["unresolved"],
        "export_path": export_result["export_path"],
    }

    export_path = Path(export_result["export_path"])
    json_report_path = export_path.with_suffix(".relink.json")
    md_report_path = export_path.with_suffix(".relink.md")
    json_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_report_path.write_text(_markdown_relink_report(report), encoding="utf-8")

    return {
        "document": after_export_document,
        "export_path": str(export_path),
        "json_report_path": str(json_report_path),
        "markdown_report_path": str(md_report_path),
        "summary": result["summary"],
    }


def relink_from_map(
    adapter,
    *,
    mapping_path: str,
    document_id: str | None = None,
    save: bool = False,
) -> dict[str, Any]:
    before = adapter.get_document_composition(document_id=document_id)
    preview = _preview_composition_relink_map_items(before["items"], mapping_path)
    apply_result = adapter.apply_relink_paths(
        preview["candidates"],
        document_id=before["document"]["id"],
        save=save,
        close_after_save=save,
    )
    after = None if save else adapter.get_document_composition(document_id=apply_result["document"]["id"])

    return {
        "document_before": before["document"],
        "document_after": apply_result["document"] if save else after["document"],
        "mapping_path": preview["mapping_path"],
        "summary": {
            **preview["summary"],
            "applied": apply_result["applied_count"],
            "failed": apply_result["failed_count"],
            "saved": apply_result["saved"],
        },
        "applied": apply_result["applied"],
        "failed": apply_result["failed"],
        "ambiguous": preview["ambiguous"],
        "unresolved": preview["unresolved"],
    }


def relink_from_map_to_export(
    adapter,
    *,
    mapping_path: str,
    document_id: str | None = None,
    suffix: str = "relinked",
) -> dict[str, Any]:
    result = relink_from_map(
        adapter,
        mapping_path=mapping_path,
        document_id=document_id,
        save=False,
    )
    export_result = adapter.save_export_copy(
        document_id=result["document_after"]["id"],
        suffix=suffix,
        close_after_save=True,
    )

    after_export_document = dict(result["document_after"])
    after_export_document["path"] = export_result["export_path"]
    after_export_document["id"] = export_result["export_path"]
    after_export_document["active"] = False

    report = {
        "document_before": result["document_before"],
        "document_after_relink": result["document_after"],
        "document_after_export": after_export_document,
        "mapping_path": result["mapping_path"],
        "summary": result["summary"],
        "applied": result["applied"],
        "failed": result["failed"],
        "ambiguous": result["ambiguous"],
        "unresolved": result["unresolved"],
        "export_path": export_result["export_path"],
    }

    export_path = Path(export_result["export_path"])
    json_report_path = export_path.with_suffix(".relink.json")
    md_report_path = export_path.with_suffix(".relink.md")
    json_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_report_path.write_text(_markdown_relink_report(report), encoding="utf-8")

    return {
        "document": after_export_document,
        "export_path": str(export_path),
        "json_report_path": str(json_report_path),
        "markdown_report_path": str(md_report_path),
        "summary": result["summary"],
    }


def _markdown_relink_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    source_label = report.get("document_before", {}).get("path") or report.get("assembly_path") or ""
    export_label = report.get("export_path") or report.get("output_path") or ""
    root_label = report.get("search_root") or report.get("mapping_path") or ""
    lines = [
        "# Relink Report",
        "",
        "## Document",
        f"- Source: `{source_label}`",
        f"- Export: `{export_label}`",
        f"- Relink source: `{root_label}`",
        "",
        "## Summary",
        f"- Candidates: `{summary['candidates']}`",
        f"- Applied: `{summary.get('applied', 0)}`",
        f"- Failed: `{summary.get('failed', 0)}`",
        f"- Ambiguous: `{summary['ambiguous']}`",
        f"- Unresolved: `{summary['unresolved']}`",
        "",
        "## First Applied",
    ]

    for change in report["applied"][:10]:
        lines.append(f"- `{change['item_id']}`: `{change['old_path']}` -> `{change['new_path']}`")

    if not report["applied"]:
        lines.append("- No applied relinks")

    return "\n".join(lines) + "\n"
