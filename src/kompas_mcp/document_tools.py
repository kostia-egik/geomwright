from __future__ import annotations

from typing import Any


def register_document_tools(mcp: Any, adapter: Any) -> None:
    """Register model tree and item-property tools."""

    @mcp.tool()
    def get_document_tree(document_id: str | None = None) -> dict:
        """Return the assembly/model tree for the selected or active document."""
        return adapter.get_document_tree(document_id=document_id)

    @mcp.tool()
    def get_items(document_id: str | None = None, item_ids: list[str] | None = None) -> dict:
        """Return selected tree items with their current properties."""
        return adapter.get_items(document_id=document_id, item_ids=item_ids)

    @mcp.tool()
    def get_item_properties(document_id: str | None = None, item_ids: list[str] | None = None) -> dict:
        """Return a practical properties snapshot for selected items."""
        return adapter.get_item_properties(document_id=document_id, item_ids=item_ids)

    @mcp.tool()
    def preview_property_changes(
        updates: list[dict],
        document_id: str | None = None,
    ) -> dict:
        """Preview direct property edits for writable item fields."""
        return adapter.preview_property_changes(updates=updates, document_id=document_id)

    @mcp.tool()
    def set_item_properties(
        updates: list[dict],
        document_id: str | None = None,
        save: bool = False,
        close_after_save: bool = False,
    ) -> dict:
        """Apply direct property edits for writable item fields."""
        return adapter.set_item_properties(
            updates=updates,
            document_id=document_id,
            save=save,
            close_after_save=close_after_save,
        )

    @mcp.tool()
    def find_items(
        document_id: str | None = None,
        query: str = "",
        kinds: list[str] | None = None,
    ) -> dict:
        """Search items by text and optional kinds."""
        return adapter.find_items(document_id=document_id, query=query, kinds=kinds)
