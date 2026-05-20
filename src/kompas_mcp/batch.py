from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_MODEL_EXTENSIONS = (".a3d", ".m3d")


def normalize_extensions(extensions: list[str] | tuple[str, ...] | None = None) -> tuple[str, ...]:
    values = extensions or DEFAULT_MODEL_EXTENSIONS
    normalized: list[str] = []
    for value in values:
        item = str(value or "").strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = f".{item}"
        if item not in normalized:
            normalized.append(item)
    return tuple(normalized or DEFAULT_MODEL_EXTENSIONS)


def scan_model_files(
    root: str,
    *,
    recursive: bool = True,
    extensions: list[str] | tuple[str, ...] | None = None,
    include_locks: bool = False,
    max_files: int | None = None,
) -> dict[str, Any]:
    base = Path(root)
    allowed_extensions = normalize_extensions(extensions)
    files: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    if not base.exists():
        return _scan_result(
            root=base,
            recursive=recursive,
            extensions=allowed_extensions,
            files=[],
            skipped=[{"path": str(base), "reason": "root_not_found"}],
            max_files=max_files,
        )

    candidates = [base] if base.is_file() else base.rglob("*") if recursive else base.glob("*")
    for candidate in candidates:
        if candidate.is_dir():
            continue

        reason = _skip_reason(candidate, allowed_extensions, include_locks=include_locks)
        if reason:
            skipped.append({"path": str(candidate), "reason": reason})
            continue

        files.append(_file_entry(candidate))
        if max_files is not None and max_files > 0 and len(files) >= max_files:
            break

    return _scan_result(
        root=base,
        recursive=recursive,
        extensions=allowed_extensions,
        files=files,
        skipped=skipped,
        max_files=max_files,
    )


def build_file_list(
    paths: list[str],
    *,
    extensions: list[str] | tuple[str, ...] | None = None,
    include_locks: bool = False,
) -> dict[str, Any]:
    allowed_extensions = normalize_extensions(extensions)
    files: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for value in paths:
        candidate = Path(value)
        if not candidate.exists():
            skipped.append({"path": str(candidate), "reason": "file_not_found"})
            continue
        if candidate.is_dir():
            skipped.append({"path": str(candidate), "reason": "is_directory"})
            continue

        reason = _skip_reason(candidate, allowed_extensions, include_locks=include_locks)
        if reason:
            skipped.append({"path": str(candidate), "reason": reason})
            continue
        files.append(_file_entry(candidate))

    return _scan_result(
        root=None,
        recursive=False,
        extensions=allowed_extensions,
        files=files,
        skipped=skipped,
        max_files=None,
    )


def summarize_batch_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(result.get("status") for result in results)
    return {
        "processed_count": len(results),
        "ok_count": statuses.get("ok", 0),
        "error_count": statuses.get("error", 0),
        "dry_run_count": statuses.get("dry_run", 0),
        "stopped_count": statuses.get("stopped", 0),
    }


def _skip_reason(path: Path, extensions: tuple[str, ...], *, include_locks: bool) -> str | None:
    if not include_locks and path.name.startswith("~$"):
        return "lock_file"
    if path.suffix.lower() not in extensions:
        return "unsupported_extension"
    return None


def _file_entry(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "extension": path.suffix.lower(),
        "size": stat.st_size,
        "modified_time": stat.st_mtime,
    }


def _scan_result(
    *,
    root: Path | None,
    recursive: bool,
    extensions: tuple[str, ...],
    files: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    max_files: int | None,
) -> dict[str, Any]:
    by_extension = Counter(file["extension"] for file in files)
    skipped_by_reason = Counter(item["reason"] for item in skipped)
    return {
        "root": str(root) if root is not None else None,
        "recursive": recursive,
        "extensions": list(extensions),
        "files": files,
        "skipped": skipped,
        "summary": {
            "file_count": len(files),
            "skipped_count": len(skipped),
            "by_extension": dict(sorted(by_extension.items())),
            "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
            "max_files": max_files,
            "truncated": bool(max_files is not None and max_files > 0 and len(files) >= max_files),
        },
    }
