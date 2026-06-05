from __future__ import annotations

from typing import Any


def register_section_tools(mcp: Any) -> None:
    """Register planning helpers for low-level section/cut operations."""

    @mcp.tool()
    def preview_section_by_surface_operation(
        target_ref: str,
        surface_reference: str,
        offset_expression: str | None = None,
        normal_direction: str = "axis_positive",
        keep_side: str = "positive",
        role: str | None = None,
    ) -> dict:
        """Preview a low-level section-by-surface operation payload."""
        if not str(target_ref).strip():
            raise ValueError("target_ref is required")
        if not str(surface_reference).strip():
            raise ValueError("surface_reference is required")
        return {
            "ok": True,
            "execution_status": "planning_only",
            "bridge_action_required": "section_by_surface",
            "operation": {
                "operation": "section_by_surface",
                "target_ref": str(target_ref),
                "surface_reference": str(surface_reference),
                "offset_expression": str(offset_expression) if offset_expression is not None else None,
                "normal_direction": str(normal_direction),
                "keep_side": str(keep_side),
                "role": str(role) if role is not None else None,
            },
        }
