from __future__ import annotations

from typing import Any


def register_part_tools(mcp: Any, adapter: Any) -> None:
    """Register parametric part generation tools."""

    @mcp.tool()
    def preview_part_scenario(scenario: str, params: dict) -> dict:
        """Preview a parametric part scenario without creating a KOMPAS document."""
        return adapter.preview_part_scenario(scenario=scenario, params=params)

    @mcp.tool()
    def create_part_from_scenario(
        scenario: str,
        params: dict,
        output_path: str | None = None,
        visible: bool = False,
        close_after_save: bool | None = None,
        save_partial_on_error: bool = False,
        return_partial_result_on_error: bool = False,
    ) -> dict:
        """Create a KOMPAS part from a supported parametric scenario such as stepped_shaft."""
        return adapter.create_part_from_scenario(
            scenario=scenario,
            params=params,
            output_path=output_path,
            visible=visible,
            close_after_save=close_after_save,
            save_partial_on_error=save_partial_on_error,
            return_partial_result_on_error=return_partial_result_on_error,
        )
