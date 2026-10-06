"""Bounded MCP surface for the shared numeric silent-chain constructor."""
from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from .bridge_runner import BridgeError
from .transmissions.silent_chain import build_silent_chain_plan
from .transmissions.silent_geometry import (
    SilentChainSelectionRequest, build_silent_chain_preview, silent_chain_selection,
)


def _preview(request: SilentChainSelectionRequest) -> dict:
    result = build_silent_chain_preview(request.model_dump())
    return {"ok": True, "stage": "silent_chain_preview", "request": request.model_dump(),
            "profile": result["profile"], "derived": result["derived"],
            "axial": {k: v for k, v in result["axial"].items() if k != "drawing"},
            "completion": result["completion"], "warnings": result.get("warnings", []),
            "diagnostics": result.get("diagnostics", {}), "conformity_claim": False}


def register_silent_chain_tools(mcp: Any, adapter: Any) -> None:
    @mcp.tool()
    def list_silent_chain_profiles(
        standard: str | None = None, family: str | None = None, query: str = "",
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=100)] = 30,
    ) -> dict:
        """List paginated GOST/DIN silent-chain sizes or ASME pitch/guide choices.

        Standards: gost_13552_81_13576_81, din_8190_8191_open, asme_b29_2m_open.
        Families: GOST type_1/type_2; DIN outer/inner; ASME pitch_and_guide.
        DIN/ASME are open reconstructions, not certified standard profiles.
        ASME values are pitch/guide selectors, not catalog chain designations.
        """
        sources = silent_chain_selection()["standards"]
        if standard is not None and standard not in {s["value"] for s in sources}:
            raise ValueError("Unknown standard; use gost_13552_81_13576_81, din_8190_8191_open or asme_b29_2m_open")
        if not 0 <= offset or not 1 <= limit <= 100:
            raise ValueError("offset must be nonnegative and limit must be 1..100")
        rows, source_info = [], []
        for source in sources:
            if standard is not None and source["value"] != standard:
                continue
            source_info.append({k: v for k, v in source.items() if k != "families"})
            for group in source["families"]:
                if family is not None and group["value"] != family:
                    continue
                for profile in group["profiles"]:
                    if query.casefold() not in profile["value"].casefold():
                        continue
                    rows.append({"standard": source["value"], "family": group["value"], **profile})
        return {"ok": True, "sources": source_info, "profiles": rows[offset:offset+limit],
                "total": len(rows), "offset": offset, "limit": limit,
                "has_more": offset+limit < len(rows), "conformity_claim": False}

    @mcp.tool()
    def preview_silent_chain_sprocket(request: SilentChainSelectionRequest) -> dict:
        """Read-only silent-chain dimensions, source warnings and CAD completeness.

        Missing engineering inputs return completion.fields with suggestions and
        missing_fields; suggestions are not silently accepted. body_depth_mm is
        optional detail-view framing, not a bore or a CAD readiness requirement.
        No sampled contours, COM calls or documents are returned/created.
        """
        return _preview(request)

    @mcp.tool()
    def create_silent_chain_sprocket(
        request: SilentChainSelectionRequest, name: str = "Geomwright silent sprocket",
        execute: bool = False, confirm_write: bool = False, visible: bool = True,
    ) -> dict:
        """Preflight or create a solid silent-chain sprocket in a NEW KOMPAS part.

        Requires catalog selection and explicit missing engineering dimensions;
        call preview_silent_chain_sprocket first. Example DIN request:
        {standard:din_8190_8191_open,family:outer,designation:08-020A,
        physical_tooth_count:23}. GOST additionally requires accuracy_class and
        explicit approximate entrance dimensions; ASME needs tool-floor inputs.
        execute=false never calls COM; execute=true also needs confirm_write=true.
        Global-X blank is solid to the axis, without bore, hub or shaft seat.
        DIN curves use cubic NURBS. Returns exact document ID, semantic references,
        body and actual verification. Failures retain partial-document evidence.
        Numeric create-only: this does NOT replace a body in an existing document.
        """
        if execute and confirm_write is not True:
            raise ValueError("confirm_write=true is required when execute=true")
        preview = build_silent_chain_preview(request.model_dump())
        if not preview["completion"]["ready_for_cad_planning"]:
            return {"ok": False, "success": False, "executed": False, "stage": "needs_input",
                    "completion": preview["completion"],
                    "error": "Supply completion.missing_fields explicitly; preview suggestions are not engineering inputs."}
        plan = build_silent_chain_plan(preview["construction_spec"], request.model_dump(), name=name)
        if not execute:
            return {"ok": True, "success": True, "executed": False, "stage": "planned",
                    "request": request.model_dump(), "name": plan["name"],
                    "target": plan["target"], "verification": plan["verification"],
                    "accuracy": plan["accuracy"], "completion": preview["completion"],
                    "warnings": preview.get("warnings", []), "conformity_claim": False}
        try:
            result = adapter.create_silent_chain_sprocket(
                plan, execute=True, confirm_write=True, visible=visible)
        except BridgeError as exc:
            partial = getattr(exc, "partial_result", None)
            return {"ok": False, "success": False, "error": str(exc),
                    "stage": "failed", "executed": bool(partial and partial.get("document")),
                    "partial_result": partial}
        return {k: result[k] for k in ("ok", "success", "executed", "stage", "saved", "closed",
                "document", "body", "exports", "verification", "accuracy") if k in result} | {
                    "warnings": preview.get("warnings", []), "conformity_claim": False,
                    "body_units": {"bounds_mm": "mm", "volume": "cm3", "surface_area": "cm2", "mass": "g"}}

    @mcp.tool()
    def inspect_silent_chain_sprocket(document_id: str) -> dict:
        """Read ownership and saved silent-chain parameters from an exact opened document.

        Read-only recognition, not a fresh geometry audit. The saved profile can
        be passed as request to preview/create_silent_chain_sprocket. No in-place
        update or body replacement is implemented by this tool.
        """
        return adapter.inspect_silent_chain_sprocket(document_id)
