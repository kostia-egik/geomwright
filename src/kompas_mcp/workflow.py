from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .adapter import KompasAdapter
from .analyzers import analyze_naming_issues, analyze_spec_issues
from .changesets import preview_changeset


def cleanup_to_export(
    adapter: KompasAdapter,
    rules: dict[str, Any],
    *,
    document_id: str | None = None,
    suffix: str = "clean",
) -> dict[str, Any]:
    before = adapter.get_document_tree(document_id=document_id)
    preview = preview_changeset(before["document"], before["tree"], rules)
    apply_result = adapter.apply_changeset(
        preview["changes"],
        document_id=before["document"]["id"],
        save=False,
    )
    after = adapter.get_document_tree(document_id=before["document"]["id"])
    export_result = adapter.save_export_copy(
        document_id=before["document"]["id"],
        suffix=suffix,
        close_after_save=True,
    )

    after_document = dict(after["document"])
    after_document["path"] = export_result["export_path"]
    after_document["id"] = export_result["export_path"]
    after_document["active"] = False

    report = {
        "document_before": before["document"],
        "document_after": after_document,
        "preview_summary": preview["summary"],
        "applied": {
            "applied_count": apply_result["applied_count"],
            "failed_count": apply_result["failed_count"],
        },
        "issues_before": {
            "naming": analyze_naming_issues(before["tree"], rules).to_dict()["summary"],
            "spec": analyze_spec_issues(before["tree"], rules).to_dict()["summary"],
        },
        "issues_after": {
            "naming": analyze_naming_issues(after["tree"], rules).to_dict()["summary"],
            "spec": analyze_spec_issues(after["tree"], rules).to_dict()["summary"],
        },
        "changes": preview["changes"],
        "export_path": export_result["export_path"],
    }

    export_path = Path(export_result["export_path"])
    json_report_path = export_path.with_suffix(".cleanup.json")
    md_report_path = export_path.with_suffix(".cleanup.md")
    json_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_report_path.write_text(_markdown_report(report), encoding="utf-8")

    return {
        "document": after_document,
        "export_path": str(export_path),
        "json_report_path": str(json_report_path),
        "markdown_report_path": str(md_report_path),
        "preview_summary": preview["summary"],
        "applied": report["applied"],
        "issues_before": report["issues_before"],
        "issues_after": report["issues_after"],
    }


def _markdown_report(report: dict[str, Any]) -> str:
    before = report["document_before"]
    after = report["document_after"]
    preview = report["preview_summary"]
    naming_before = report["issues_before"]["naming"]
    spec_before = report["issues_before"]["spec"]
    naming_after = report["issues_after"]["naming"]
    spec_after = report["issues_after"]["spec"]

    lines = [
        "# Cleanup Report",
        "",
        "## Document",
        f"- Source: `{before['path']}`",
        f"- Export: `{report['export_path']}`",
        f"- Active after export: `{after['path']}`",
        "",
        "## Changes",
        f"- Total changes: `{preview['total_changes']}`",
        f"- Name changes: `{preview['name_changes']}`",
        f"- Designation changes: `{preview['designation_changes']}`",
        f"- Applied: `{report['applied']['applied_count']}`",
        f"- Failed: `{report['applied']['failed_count']}`",
        "",
        "## Issues Before",
        f"- Naming: `{naming_before}`",
        f"- Spec: `{spec_before}`",
        "",
        "## Issues After",
        f"- Naming: `{naming_after}`",
        f"- Spec: `{spec_after}`",
        "",
        "## First Changes",
    ]

    for change in report["changes"][:10]:
        lines.append(
            f"- `{change['item_id']}` `{change['field']}`: `{change['before']}` -> `{change['after']}`"
        )

    return "\n".join(lines) + "\n"
