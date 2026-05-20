from __future__ import annotations

from collections import Counter
from typing import Any

from .models import AnalysisResult, Issue
from .rules import clean_text


def flatten_tree(root: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def walk(node: dict[str, Any]) -> None:
        items.append(node)
        for child in node.get("children", []):
            walk(child)

    walk(root)
    return items


def analyze_naming_issues(tree: dict[str, Any], rules: dict[str, Any]) -> AnalysisResult:
    items = flatten_tree(tree)
    issues: list[Issue] = []

    for item in items:
        current_name = item.get("name") or ""
        suggested_name = clean_text(current_name, rules)

        if not current_name.strip():
            issues.append(
                Issue(
                    code="empty_name",
                    severity="error",
                    message="Пустое имя компонента",
                    item_id=item["id"],
                    field="name",
                    current_value=current_name,
                    suggested_value=suggested_name or "UNNAMED",
                )
            )
            continue

        if suggested_name != current_name:
            issues.append(
                Issue(
                    code="dirty_name",
                    severity="warning",
                    message="Имя требует нормализации",
                    item_id=item["id"],
                    field="name",
                    current_value=current_name,
                    suggested_value=suggested_name,
                )
            )

    summary = {
        "items_checked": len(items),
        "issues_found": len(issues),
        "errors": sum(1 for issue in issues if issue.severity == "error"),
        "warnings": sum(1 for issue in issues if issue.severity == "warning"),
    }
    return AnalysisResult(summary=summary, issues=issues)


def analyze_spec_issues(tree: dict[str, Any], rules: dict[str, Any]) -> AnalysisResult:
    items = flatten_tree(tree)
    issues: list[Issue] = []
    designations = Counter()

    for item in items:
        designation = (item.get("designation") or "").strip()
        title = (item.get("title") or item.get("name") or "").strip()
        material = (item.get("material") or "").strip()

        if designation:
            designations[designation] += 1
        else:
            issues.append(
                Issue(
                    code="missing_designation",
                    severity="warning",
                    message="Не заполнено обозначение",
                    item_id=item["id"],
                    field="designation",
                    current_value=item.get("designation"),
                )
            )

        if not title:
            issues.append(
                Issue(
                    code="missing_title",
                    severity="warning",
                    message="Не заполнено наименование",
                    item_id=item["id"],
                    field="title",
                    current_value=item.get("title"),
                )
            )

        if rules.get("warn_if_missing_material", True) and not material:
            issues.append(
                Issue(
                    code="missing_material",
                    severity="info",
                    message="Не заполнен материал",
                    item_id=item["id"],
                    field="material",
                    current_value=item.get("material"),
                )
            )

    for item in items:
        designation = (item.get("designation") or "").strip()
        if designation and designations[designation] > 1:
            issues.append(
                Issue(
                    code="duplicate_designation",
                    severity="warning",
                    message="Повторяющееся обозначение",
                    item_id=item["id"],
                    field="designation",
                    current_value=designation,
                )
            )

    summary = {
        "items_checked": len(items),
        "issues_found": len(issues),
        "duplicate_designations": sum(1 for count in designations.values() if count > 1),
    }
    return AnalysisResult(summary=summary, issues=issues)
