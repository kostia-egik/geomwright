"""MCP tools for the straight-sided spline family (ГОСТ 1139-80).

Layer 2/3 core lives in `kompas_mcp.connections`: catalog, profile geometry,
fits and the create-only CAD plan. These tools expose the same core with the
plan/execute/verify boundary used by the gear and sprocket families.
"""
from __future__ import annotations

from typing import Any

from .connections import (
    StraightSplineCreateRequest,
    StraightSplineRequest,
    build_straight_spline_plan,
    build_straight_spline_preview,
    list_straight_spline_sizes,
)


def register_spline_tools(mcp: Any, adapter: Any) -> None:
    @mcp.tool()
    def list_spline_sizes(
        series: str | None = None,
        query: str | None = None,
        limit: int = 200,
    ) -> dict:
        """List ГОСТ 1139-80 straight spline sizes for light, medium and heavy series."""
        return list_straight_spline_sizes(series, query, limit=limit)

    @mcp.tool()
    def preview_spline(request: StraightSplineRequest) -> dict:
        """Preview one straight-sided spline shaft or hub; no CAD write.

        Returns the exact numeric tooth-space contour (segments and arcs), the
        standard dimensions, the ГОСТ 1139-80 fits and preflight checks. The
        radius cutter runout and the rolled execution-1 groove are outside this
        slice.
        """
        return build_straight_spline_preview(request.model_dump(exclude_none=True))

    @mcp.tool()
    def create_spline(request: StraightSplineCreateRequest) -> dict:
        """Plan (execute=false) or create one verified create-only spline part.

        The plan builds a shaft section (cylinder with tip chamfers and one
        through tooth-space cut per pattern instance) or a hub ring (bore plus
        the internal space cut). Creation stores a checksummed recipe so a
        reopened block restores the Studio form for a new build.
        """
        profile = request.model_dump(
            exclude={"name", "execute", "confirm_write", "visible"},
            exclude_none=True,
        )
        plan = build_straight_spline_plan(profile, name=request.name)
        return adapter.create_spline(
            plan,
            execute=request.execute,
            confirm_write=request.confirm_write,
            visible=request.visible,
        )

    @mcp.tool()
    def inspect_spline(document_id: str) -> dict:
        """Read one saved managed straight-sided spline block with its recipe."""
        result = adapter.inspect_spline(document_id=document_id)
        if result.get("module") != "straight_spline":
            raise ValueError("The exact document does not contain a recognized spline block")
        return result
