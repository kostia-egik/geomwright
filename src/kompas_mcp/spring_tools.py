from __future__ import annotations

from typing import Any

from .spring_catalog import (
    find_spring_catalog_entries,
    list_spring_catalogs,
    recommend_spring_catalog_entries,
    resolve_spring_catalog_entry,
    validate_spring_catalogs,
)


def register_spring_tools(mcp: Any, adapter: Any) -> None:
    """Register spring-specific parametric generation tools."""

    @mcp.tool()
    def list_spring_size_catalogs(spring_type: str | None = None, include_entries: bool = False) -> dict:
        """List available built-in spring size catalogs."""
        return list_spring_catalogs(spring_type=spring_type, include_entries=include_entries)

    @mcp.tool()
    def validate_spring_size_catalogs(include_preview: bool = False) -> dict:
        """Validate built-in spring catalog metadata and optional previews."""
        return validate_spring_catalogs(include_preview=include_preview)

    @mcp.tool()
    def find_spring_sizes(
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
    ) -> dict:
        """Find spring catalog entries by type, size, class, or tag."""
        return find_spring_catalog_entries(
            spring_type=spring_type,
            catalog_id=catalog_id,
            wire_diameter=wire_diameter,
            outer_diameter=outer_diameter,
            standard_length=standard_length,
            height=height,
            turns=turns,
            hook_type=hook_type,
            load_class=load_class,
            tag=tag,
            limit=limit,
        )

    @mcp.tool()
    def recommend_spring_sizes(
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
    ) -> dict:
        """Recommend nearest spring catalog entries for target dimensions."""
        return recommend_spring_catalog_entries(
            spring_type=spring_type,
            catalog_id=catalog_id,
            target_wire_diameter=target_wire_diameter,
            target_outer_diameter=target_outer_diameter,
            target_length=target_length,
            target_standard_length=target_standard_length,
            target_height=target_height,
            target_turns=target_turns,
            target_pitch=target_pitch,
            load_class=load_class,
            hook_type=hook_type,
            tag=tag,
            limit=limit,
        )

    @mcp.tool()
    def resolve_spring_size(
        catalog_id: str,
        entry_id: str,
        overrides: dict | None = None,
        include_preview: bool = False,
    ) -> dict:
        """Resolve one spring catalog entry to generator-ready scenario params."""
        return resolve_spring_catalog_entry(
            catalog_id=catalog_id,
            entry_id=entry_id,
            overrides=overrides,
            include_preview=include_preview,
        )

    @mcp.tool()
    def preview_spring_from_size(
        catalog_id: str,
        entry_id: str,
        overrides: dict | None = None,
    ) -> dict:
        """Preview a supported spring from one resolved catalog entry."""
        return resolve_spring_catalog_entry(
            catalog_id=catalog_id,
            entry_id=entry_id,
            overrides=overrides,
            include_preview=True,
        )

    @mcp.tool()
    def create_spring_from_size(
        catalog_id: str,
        entry_id: str,
        overrides: dict | None = None,
        output_path: str | None = None,
        visible: bool = True,
        close_after_save: bool = True,
    ) -> dict:
        """Create a supported spring from one resolved catalog entry."""
        resolved = resolve_spring_catalog_entry(
            catalog_id=catalog_id,
            entry_id=entry_id,
            overrides=overrides,
            include_preview=False,
        )
        return adapter.create_part_from_scenario(
            resolved["scenario"],
            resolved["params"],
            output_path=output_path,
            visible=visible,
            close_after_save=close_after_save,
        )

    @mcp.tool()
    def preview_compression_spring(params: dict) -> dict:
        """Preview a compression spring scenario without creating a KOMPAS document."""
        return adapter.preview_part_scenario(scenario="compression_spring", params=params)

    @mcp.tool()
    def create_compression_spring(
        params: dict,
        output_path: str | None = None,
        visible: bool = False,
        close_after_save: bool | None = None,
        save_partial_on_error: bool = False,
        return_partial_result_on_error: bool = False,
    ) -> dict:
        """Create a KOMPAS compression spring part from the supported compression_spring scenario."""
        return adapter.create_part_from_scenario(
            scenario="compression_spring",
            params=params,
            output_path=output_path,
            visible=visible,
            close_after_save=close_after_save,
            save_partial_on_error=save_partial_on_error,
            return_partial_result_on_error=return_partial_result_on_error,
        )
