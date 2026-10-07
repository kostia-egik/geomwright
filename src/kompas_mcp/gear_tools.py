"""MCP tools for the external cylindrical gear family (`gear_spur`).

The Layer 2/3 core lives in `kompas_mcp.gears`: standards, preview analysis, and
the create-only CAD plan. These tools expose that core on the MCP surface with
the same plan/execute/verify boundary as the chain-sprocket tools.
"""
from __future__ import annotations

from typing import Any

from .gears import (
    BevelGearCreateRequest,
    BevelGearRequest,
    InternalGearCreateRequest,
    InternalGearRequest,
    SpurGearCreateRequest,
    SpurGearRequest,
    build_bevel_gear_preview,
    build_internal_gear_preview,
    build_spur_gear_preview,
    gear_selection,
)
from .gears.cad import build_bevel_gear_plan, build_gear_spur_plan, build_internal_gear_plan


def register_gear_tools(mcp: Any, adapter: Any) -> None:
    @mcp.tool()
    def list_gear_standards() -> dict:
        """List basic-rack standards, modifications, module rows, and pin rows."""
        return gear_selection()

    @mcp.tool()
    def preview_cylindrical_gear(request: SpurGearRequest) -> dict:
        """Preview one external cylindrical gear (spur or helical); no CAD write."""
        return build_spur_gear_preview(request.model_dump(exclude_none=True))

    @mcp.tool()
    def create_cylindrical_gear(request: SpurGearCreateRequest) -> dict:
        """Plan (execute=false) or create one verified create-only cylindrical gear part.

        Creation stores a checksummed recipe so a reopened block restores its
        Studio form for a new build.
        """
        profile = request.model_dump(
            exclude={"name", "execute", "confirm_write", "visible"},
            exclude_none=True,
        )
        plan = build_gear_spur_plan(profile, name=request.name)
        return adapter.create_gear_spur(
            plan,
            execute=request.execute,
            confirm_write=request.confirm_write,
            visible=request.visible,
        )

    @mcp.tool()
    def inspect_cylindrical_gear(document_id: str) -> dict:
        """Read one saved managed cylindrical-gear block with its recipe and status."""
        result = adapter.inspect_gear_spur(document_id=document_id)
        if result.get("module") != "gear_spur":
            raise ValueError("The exact document does not contain a recognized gear block")
        return result

    @mcp.tool()
    def preview_internal_gear(request: InternalGearRequest) -> dict:
        """Preview one internal cylindrical gear (ring gear); no CAD write."""
        return build_internal_gear_preview(request.model_dump(exclude_none=True))

    @mcp.tool()
    def create_internal_gear(request: InternalGearCreateRequest) -> dict:
        """Plan (execute=false) or create one verified create-only internal gear part.

        The ring blank outside diameter is explicit; the internal tooth spaces
        are cut from the bore. Creation stores a checksummed recipe so a
        reopened block restores its Studio form for a new build.
        """
        profile = request.model_dump(
            exclude={"name", "execute", "confirm_write", "visible"},
            exclude_none=True,
        )
        plan = build_internal_gear_plan(profile, name=request.name)
        return adapter.create_gear_internal(
            plan,
            execute=request.execute,
            confirm_write=request.confirm_write,
            visible=request.visible,
        )

    @mcp.tool()
    def inspect_internal_gear(document_id: str) -> dict:
        """Read one saved managed internal-gear block with its recipe and status."""
        result = adapter.inspect_gear_internal(document_id=document_id)
        if result.get("module") != "gear_internal":
            raise ValueError("The exact document does not contain a recognized internal gear block")
        return result

    @mcp.tool()
    def preview_bevel_gear(request: BevelGearRequest) -> dict:
        """Preview one straight bevel gear (Tredgold nominal geometry); no CAD write."""
        return build_bevel_gear_preview(request.model_dump(exclude_none=True))

    @mcp.tool()
    def create_bevel_gear(request: BevelGearCreateRequest) -> dict:
        """Plan (execute=false) or create one verified create-only straight bevel gear part.

        The module builds a conical blank and one tooth-space cut lofted between
        two exact projected frontal sections. Creation stores a checksummed
        recipe so a reopened block restores its Studio form for a new build.
        """
        profile = request.model_dump(
            exclude={"name", "execute", "confirm_write", "visible"},
            exclude_none=True,
        )
        plan = build_bevel_gear_plan(profile, name=request.name)
        return adapter.create_gear_bevel(
            plan,
            execute=request.execute,
            confirm_write=request.confirm_write,
            visible=request.visible,
        )

    @mcp.tool()
    def inspect_bevel_gear(document_id: str) -> dict:
        """Read one saved managed bevel-gear block with its recipe and status."""
        result = adapter.inspect_gear_bevel(document_id=document_id)
        if result.get("module") != "gear_bevel":
            raise ValueError("The exact document does not contain a recognized bevel gear block")
        return result
