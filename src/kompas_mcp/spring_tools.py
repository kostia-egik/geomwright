from __future__ import annotations

from typing import Any


def register_spring_tools(mcp: Any, adapter: Any) -> None:
    """Register spring-specific parametric generation tools."""

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
