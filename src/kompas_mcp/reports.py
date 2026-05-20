from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_REPORT_FORMATS = ("json", "md")


def write_batch_report(
    payload: dict[str, Any],
    *,
    report_dir: str,
    report_name: str | None = None,
    formats: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_formats = _normalize_formats(formats)
    base_name = _report_base_name(payload, report_name)
    files: list[dict[str, Any]] = []

    if "json" in selected_formats:
        path = output_dir / f"{base_name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        files.append(_file_entry(path, "json"))

    if "md" in selected_formats or "markdown" in selected_formats:
        path = output_dir / f"{base_name}.md"
        path.write_text(render_batch_markdown(payload), encoding="utf-8-sig")
        files.append(_file_entry(path, "md"))

    return {
        "ok": bool(files),
        "report_dir": str(output_dir),
        "base_name": base_name,
        "formats": selected_formats,
        "files": files,
    }


def render_batch_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    title = _report_title(payload)
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        f"- OK: `{payload.get('ok')}`",
        f"- Candidates: `{summary.get('candidate_count', 0)}`",
        f"- Selected: `{summary.get('selected_count', summary.get('processed_count', 0))}`",
        f"- Processed: `{summary.get('processed_count', 0)}`",
        f"- Errors: `{summary.get('error_count', 0)}`",
        f"- Stopped: `{summary.get('stopped_count', 0)}`",
    ]

    if "total_issues" in summary:
        lines.append(f"- Total issues: `{summary.get('total_issues', 0)}`")
    if "skipped_count" in summary:
        lines.append(f"- Skipped: `{summary.get('skipped_count', 0)}`")

    lines.extend(["", "## Files", "", "| Status | Issues | Path |", "| --- | ---: | --- |"])
    for result in payload.get("results", []):
        status = result.get("status", "")
        issue_count = result.get("issue_count", "")
        path = _escape_md(str(result.get("path", "")))
        lines.append(f"| `{status}` | `{issue_count}` | `{path}` |")

    skipped = payload.get("skipped") or []
    if skipped:
        lines.extend(["", "## Skipped", "", "| Reason | Path |", "| --- | --- |"])
        for item in skipped[:50]:
            lines.append(f"| `{item.get('reason', '')}` | `{_escape_md(str(item.get('path', '')))}` |")
        if len(skipped) > 50:
            lines.append(f"| `truncated` | `{len(skipped) - 50} more skipped files` |")

    issue_lines = _render_issue_lines(payload)
    if issue_lines:
        lines.extend(["", "## First Issues", ""])
        lines.extend(issue_lines)

    lines.append("")
    return "\n".join(lines)


def _render_issue_lines(payload: dict[str, Any], *, limit: int = 30) -> list[str]:
    lines: list[str] = []
    count = 0
    for result in payload.get("results", []):
        analyses = result.get("analyses") or {}
        for analysis_name, analysis in analyses.items():
            for issue in analysis.get("issues", []):
                count += 1
                if count > limit:
                    lines.append(f"- ... {count - limit} more issues omitted from markdown preview")
                    return lines
                path = _escape_md(str(result.get("path", "")))
                code = issue.get("code", "")
                severity = issue.get("severity", "")
                item_id = issue.get("item_id", "")
                field = issue.get("field", "")
                lines.append(
                    f"- `{severity}` `{analysis_name}` `{code}` in `{field}` for `{item_id}`: {path}"
                )
    return lines


def _normalize_formats(formats: list[str] | tuple[str, ...] | None) -> list[str]:
    values = formats or DEFAULT_REPORT_FORMATS
    normalized: list[str] = []
    for value in values:
        item = str(value or "").strip().lower()
        if item == "markdown":
            item = "md"
        if item in {"json", "md"} and item not in normalized:
            normalized.append(item)
    return normalized or list(DEFAULT_REPORT_FORMATS)


def _report_base_name(payload: dict[str, Any], report_name: str | None) -> str:
    if report_name:
        return _slug(report_name)
    report_type = _slug(str(payload.get("report_type") or "batch-report"))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{report_type}-{stamp}"


def _report_title(payload: dict[str, Any]) -> str:
    report_type = str(payload.get("report_type") or "batch_report")
    title = report_type.replace("_", " ").replace("-", " ").strip().title()
    return title or "Batch Report"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return slug or "batch-report"


def _file_entry(path: Path, format_name: str) -> dict[str, Any]:
    return {
        "format": format_name,
        "path": str(path),
        "size": path.stat().st_size,
    }


def _escape_md(value: str) -> str:
    return value.replace("|", "\\|")
