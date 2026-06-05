from __future__ import annotations

from typing import Any, Callable

from .relink import build_file_relink_map_plan as build_file_relink_map_plan_payload
from .relink import build_file_relink_plan as build_file_relink_plan_payload
from .relink import preview_file_relink_map_paths as build_file_relink_map_preview
from .relink import preview_file_relink_paths as build_file_relink_preview
from .relink import relink_file_from_map_to_output as run_relink_file_from_map_to_output
from .relink import relink_file_to_output as run_relink_file_to_output
from .relink import relink_from_map as run_relink_from_map
from .relink import relink_from_map_to_export as run_relink_from_map_to_export
from .relink import relink_project_root as run_relink_project_root
from .relink import relink_to_export as run_relink_to_export
from .workflow import cleanup_to_export as run_cleanup_to_export


def register_workflow_tools(mcp: Any, adapter: Any, rules_loader: Callable[[str | None], dict]) -> None:
    """Register cleanup/export and relink workflow tools."""

    @mcp.tool()
    def cleanup_to_export(document_id: str | None = None, suffix: str = "clean", rules_path: str | None = None) -> dict:
        """Apply the current cleanup rules, export a working copy, and write a report next to it."""
        return run_cleanup_to_export(adapter, rules_loader(rules_path), document_id=document_id, suffix=suffix)

    @mcp.tool()
    def preview_relink_paths(document_id: str | None = None, search_root: str = "", relink_all: bool = False) -> dict:
        """Find candidate component path updates by searching for matching filenames under a new root."""
        composition_payload = adapter.get_document_composition(document_id=document_id)
        return {
            "document": composition_payload["document"],
            "assembly_path": composition_payload["assembly_path"],
            **build_file_relink_preview(composition_payload["assembly_path"], search_root, relink_all=relink_all),
        }

    @mcp.tool()
    def preview_file_relink_paths(assembly_path: str, search_root: str, relink_all: bool = False) -> dict:
        """Preview persistent relinks by reading the Sources entry of an assembly file directly."""
        return build_file_relink_preview(assembly_path=assembly_path, search_root=search_root, relink_all=relink_all)

    @mcp.tool()
    def preview_file_relink_map_paths(assembly_path: str, mapping_path: str) -> dict:
        """Preview relinks for a file assembly from an explicit mapping file."""
        return build_file_relink_map_preview(assembly_path=assembly_path, mapping_path=mapping_path)

    @mcp.tool()
    def build_file_relink_plan(assembly_path: str, search_root: str, relink_all: bool = False) -> dict:
        """Build a grouped actionable relink plan for an assembly file."""
        return build_file_relink_plan_payload(
            assembly_path=assembly_path,
            search_root=search_root,
            relink_all=relink_all,
        )

    @mcp.tool()
    def build_file_relink_map_plan(assembly_path: str, mapping_path: str) -> dict:
        """Build a grouped actionable relink plan from an explicit mapping file."""
        return build_file_relink_map_plan_payload(
            assembly_path=assembly_path,
            mapping_path=mapping_path,
        )

    @mcp.tool()
    def preview_relink_map_paths(document_id: str | None = None, mapping_path: str = "") -> dict:
        """Preview relinks from an explicit old->new mapping file, useful when files were also renamed."""
        composition_payload = adapter.get_document_composition(document_id=document_id)
        return {
            "document": composition_payload["document"],
            "assembly_path": composition_payload["assembly_path"],
            **build_file_relink_map_preview(composition_payload["assembly_path"], mapping_path),
        }

    @mcp.tool()
    def build_relink_plan(document_id: str | None = None, search_root: str = "", relink_all: bool = False) -> dict:
        """Build a grouped actionable relink plan for the selected or active document."""
        composition_payload = adapter.get_document_composition(document_id=document_id)
        return {
            "document": composition_payload["document"],
            **build_file_relink_plan_payload(
                assembly_path=composition_payload["assembly_path"],
                search_root=search_root,
                relink_all=relink_all,
            ),
        }

    @mcp.tool()
    def build_relink_map_plan(document_id: str | None = None, mapping_path: str = "") -> dict:
        """Build a grouped actionable relink plan for the selected or active document from a mapping file."""
        composition_payload = adapter.get_document_composition(document_id=document_id)
        return {
            "document": composition_payload["document"],
            **build_file_relink_map_plan_payload(
                assembly_path=composition_payload["assembly_path"],
                mapping_path=mapping_path,
            ),
        }

    @mcp.tool()
    def apply_relink_paths(
        changes: list[dict],
        document_id: str | None = None,
        save: bool = False,
        close_after_save: bool = False,
    ) -> dict:
        """Apply component source-path relinks to the selected or active assembly."""
        return adapter.apply_relink_paths(
            changes=changes,
            document_id=document_id,
            save=save,
            close_after_save=close_after_save,
        )

    @mcp.tool()
    def apply_file_relink_paths(
        assembly_path: str,
        changes: list[dict],
        output_path: str | None = None,
    ) -> dict:
        """Apply relinks to an assembly file through KOMPAS itself and save the result to the target path."""
        return adapter.relink_document_file(assembly_path=assembly_path, changes=changes, output_path=output_path)

    @mcp.tool()
    def relink_project_root(
        search_root: str,
        document_id: str | None = None,
        relink_all: bool = False,
        save: bool = False,
    ) -> dict:
        """Preview and apply assembly relinks by matching component filenames under a new root."""
        return run_relink_project_root(
            adapter,
            search_root=search_root,
            document_id=document_id,
            relink_all=relink_all,
            save=save,
        )

    @mcp.tool()
    def relink_from_map(
        mapping_path: str,
        document_id: str | None = None,
        save: bool = False,
    ) -> dict:
        """Preview and apply assembly relinks from an explicit mapping file."""
        return run_relink_from_map(
            adapter,
            mapping_path=mapping_path,
            document_id=document_id,
            save=save,
        )

    @mcp.tool()
    def relink_to_export(
        search_root: str,
        document_id: str | None = None,
        relink_all: bool = False,
        suffix: str = "relinked",
    ) -> dict:
        """Preview and apply assembly relinks, then save a safe exported copy with a relink report."""
        return run_relink_to_export(
            adapter,
            search_root=search_root,
            document_id=document_id,
            relink_all=relink_all,
            suffix=suffix,
        )

    @mcp.tool()
    def relink_from_map_to_export(
        mapping_path: str,
        document_id: str | None = None,
        suffix: str = "relinked",
    ) -> dict:
        """Apply relinks from an explicit mapping file and save a safe exported copy with a report."""
        return run_relink_from_map_to_export(
            adapter,
            mapping_path=mapping_path,
            document_id=document_id,
            suffix=suffix,
        )

    @mcp.tool()
    def relink_file_to_output(
        assembly_path: str,
        search_root: str,
        output_path: str,
        relink_all: bool = False,
    ) -> dict:
        """Preview and apply assembly relinks to a copied file through KOMPAS itself."""
        return run_relink_file_to_output(
            adapter,
            assembly_path=assembly_path,
            search_root=search_root,
            output_path=output_path,
            relink_all=relink_all,
        )

    @mcp.tool()
    def relink_file_from_map_to_output(
        assembly_path: str,
        mapping_path: str,
        output_path: str,
    ) -> dict:
        """Apply relinks from an explicit mapping file to a copied assembly through KOMPAS itself."""
        return run_relink_file_from_map_to_output(
            adapter,
            assembly_path=assembly_path,
            mapping_path=mapping_path,
            output_path=output_path,
        )
