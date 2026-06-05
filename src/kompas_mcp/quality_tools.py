from __future__ import annotations

from typing import Any, Callable

from .analyzers import analyze_naming_issues as run_naming_analysis
from .analyzers import analyze_spec_issues as run_spec_analysis
from .changesets import preview_changeset as build_preview_changeset


def register_quality_tools(mcp: Any, adapter: Any, rules_loader: Callable[[str | None], dict]) -> None:
    """Register quality analysis and changeset tools."""

    @mcp.tool()
    def analyze_naming_issues(document_id: str | None = None, rules_path: str | None = None) -> dict:
        """Analyze naming issues in the selected or active document."""
        tree_payload = adapter.get_document_tree(document_id=document_id)
        result = run_naming_analysis(tree_payload["tree"], rules_loader(rules_path))
        return {
            "document": tree_payload["document"],
            **result.to_dict(),
        }

    @mcp.tool()
    def analyze_spec_issues(document_id: str | None = None, rules_path: str | None = None) -> dict:
        """Analyze basic specification issues in the selected or active document."""
        tree_payload = adapter.get_document_tree(document_id=document_id)
        result = run_spec_analysis(tree_payload["tree"], rules_loader(rules_path))
        return {
            "document": tree_payload["document"],
            **result.to_dict(),
        }

    @mcp.tool()
    def preview_changeset(document_id: str | None = None, rules_path: str | None = None) -> dict:
        """Build a safe preview of name and designation changes."""
        tree_payload = adapter.get_document_tree(document_id=document_id)
        return build_preview_changeset(tree_payload["document"], tree_payload["tree"], rules_loader(rules_path))

    @mcp.tool()
    def apply_changeset(
        changes: list[dict],
        document_id: str | None = None,
        save: bool = False,
        close_after_save: bool = False,
    ) -> dict:
        """Apply a prepared changeset to writable fields only."""
        return adapter.apply_changeset(
            changes=changes,
            document_id=document_id,
            save=save,
            close_after_save=close_after_save,
        )
