from __future__ import annotations

from typing import Any


def register_specification_tools(mcp: Any, adapter: Any) -> None:
    """Register composition and specification tools."""

    @mcp.tool()
    def get_file_composition(assembly_path: str) -> dict:
        """Read the stored composition of an assembly file directly from the file itself."""
        return adapter.get_file_composition(assembly_path)


    @mcp.tool()
    def get_document_composition(document_id: str | None = None) -> dict:
        """Read the stored composition of the selected or active saved document."""
        return adapter.get_document_composition(document_id=document_id)


    @mcp.tool()
    def get_specification_descriptions(document_id: str | None = None) -> dict:
        """List available specification descriptions for the selected or active document."""
        return adapter.get_specification_descriptions(document_id=document_id)


    @mcp.tool()
    def get_specification(
        document_id: str | None = None,
        description_index: int | None = None,
        layout_name: str | None = None,
        include_objects: bool = True,
        max_objects: int = 200,
    ) -> dict:
        """Read the active or selected specification description with its objects and columns."""
        return adapter.get_specification(
            document_id=document_id,
            description_index=description_index,
            layout_name=layout_name,
            include_objects=include_objects,
            max_objects=max_objects,
        )


    @mcp.tool()
    def preview_specification_generation(
        document_id: str | None = None,
        include_root: bool = False,
    ) -> dict:
        """Build a practical specification preview from the assembly tree."""
        return adapter.preview_specification_generation(
            document_id=document_id,
            include_root=include_root,
        )


    @mcp.tool()
    def preview_spw_generation(
        document_id: str | None = None,
        include_root: bool = False,
        columns: list[dict] | None = None,
        include_engineering: bool = False,
        column_preset: str | None = None,
    ) -> dict:
        """Build a preview for a separate .spw specification document from the assembly tree.

        columns maps row fields to .spw columns: field, column_type, block_number,
        column_number, skip_unit_value. column_preset can be default/base or
        engineering_comment_columns. Engineering fields require explicit opt-in.
        """
        return adapter.preview_spw_generation(
            document_id=document_id,
            include_root=include_root,
            columns=columns,
            include_engineering=include_engineering,
            column_preset=column_preset,
        )


    @mcp.tool()
    def create_spw_from_model(
        document_id: str | None = None,
        output_path: str | None = None,
        include_root: bool = False,
        layout_name: str = "graphic.lyt",
        style_id: int = 1,
        columns: list[dict] | None = None,
        include_engineering: bool = False,
        column_preset: str | None = None,
    ) -> dict:
        """Create a separate .spw specification document from the current model tree.

        By default writes only position, designation, title, quantity, comment.
        Engineering fields are written only when mapped by columns and opted in.
        """
        return adapter.create_spw_from_model(
            document_id=document_id,
            output_path=output_path,
            include_root=include_root,
            layout_name=layout_name,
            style_id=style_id,
            columns=columns,
            include_engineering=include_engineering,
            column_preset=column_preset,
        )


    @mcp.tool()
    def create_specification(
        document_id: str | None = None,
        include_root: bool = False,
        replace_existing: bool = False,
        save: bool = False,
        close_after_save: bool = False,
        layout_name: str = "",
        style_id: int = 0,
        specification_name: str = "",
    ) -> dict:
        """Create a specification description and fill rows from the current assembly tree."""
        return adapter.create_specification(
            document_id=document_id,
            include_root=include_root,
            replace_existing=replace_existing,
            save=save,
            close_after_save=close_after_save,
            layout_name=layout_name,
            style_id=style_id,
            specification_name=specification_name,
        )


    @mcp.tool()
    def preview_specification_changes(
        updates: list[dict],
        document_id: str | None = None,
        description_index: int | None = None,
        layout_name: str | None = None,
        max_objects: int = 2000,
    ) -> dict:
        """Preview edits for existing specification rows by object_id and standard fields."""
        return adapter.preview_specification_changes(
            updates=updates,
            document_id=document_id,
            description_index=description_index,
            layout_name=layout_name,
            max_objects=max_objects,
        )


    @mcp.tool()
    def apply_specification_changes(
        updates: list[dict],
        document_id: str | None = None,
        description_index: int | None = None,
        layout_name: str | None = None,
        save: bool = False,
        close_after_save: bool = False,
        max_objects: int = 2000,
    ) -> dict:
        """Apply edits to existing specification rows by object_id and standard fields."""
        return adapter.apply_specification_changes(
            updates=updates,
            document_id=document_id,
            description_index=description_index,
            layout_name=layout_name,
            save=save,
            close_after_save=close_after_save,
            max_objects=max_objects,
        )


    @mcp.tool()
    def preview_specification_autofill(
        document_id: str | None = None,
        description_index: int | None = None,
        layout_name: str | None = None,
        include_root: bool = False,
        fields: list[str] | None = None,
        fill_only: bool = False,
        max_objects: int = 2000,
    ) -> dict:
        """Build a safe preview of filling or syncing specification rows from the model tree."""
        return adapter.preview_specification_autofill(
            document_id=document_id,
            description_index=description_index,
            layout_name=layout_name,
            include_root=include_root,
            fields=fields,
            fill_only=fill_only,
            max_objects=max_objects,
        )


    @mcp.tool()
    def apply_specification_autofill(
        document_id: str | None = None,
        description_index: int | None = None,
        layout_name: str | None = None,
        include_root: bool = False,
        fields: list[str] | None = None,
        fill_only: bool = False,
        save: bool = False,
        close_after_save: bool = False,
        max_objects: int = 2000,
    ) -> dict:
        """Apply filling or syncing of specification rows from the model tree."""
        return adapter.apply_specification_autofill(
            document_id=document_id,
            description_index=description_index,
            layout_name=layout_name,
            include_root=include_root,
            fields=fields,
            fill_only=fill_only,
            save=save,
            close_after_save=close_after_save,
            max_objects=max_objects,
        )


    @mcp.tool()
    def refresh_specification_from_model(
        document_id: str | None = None,
        include_root: bool = False,
        replace_existing: bool = True,
        save: bool = False,
        close_after_save: bool = False,
        layout_name: str = "",
        style_id: int = 0,
        specification_name: str = "",
        fields: list[str] | None = None,
        fill_only: bool = False,
        max_objects: int = 2000,
    ) -> dict:
        """Recreate the active specification from the model and then apply safe autofill for supported fields."""
        return adapter.refresh_specification_from_model(
            document_id=document_id,
            include_root=include_root,
            replace_existing=replace_existing,
            save=save,
            close_after_save=close_after_save,
            layout_name=layout_name,
            style_id=style_id,
            specification_name=specification_name,
            fields=fields,
            fill_only=fill_only,
            max_objects=max_objects,
        )
