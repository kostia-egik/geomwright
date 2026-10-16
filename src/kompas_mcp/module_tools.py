"""MCP transport for the shared CAD-module contract."""
from __future__ import annotations

from typing import Any
from typing import Literal

from .cad_modules import CadModuleRequest, get_cad_module_contract as describe, run_cad_module as run
from .construction_chains import (
    ConstructionChain, get_construction_chain_contract as describe_chain,
    run_construction_chain as run_chain,
)


def register_module_tools(mcp: Any, adapter: Any) -> None:
    @mcp.tool()
    def get_construction_chain_contract() -> dict:
        """Discover supported chain modules, recipe schema, placement and limits without CAD."""
        return describe_chain()

    @mcp.tool()
    def run_construction_chain(
        action: Literal["plan", "create", "inspect", "rebuild", "continue"],
        chain: ConstructionChain | None = None,
        document_id: str | None = None,
        confirm_write: bool = False,
        visible: bool = True,
    ) -> dict:
        """Plan or build one coaxial part from ordered modules in one bounded CAD job.

        Discover inputs with get_construction_chain_contract. Plan never accesses
        CAD. Create/rebuild/continue require confirm_write=true. Inspect/rebuild select an
        exact opened document_id; rebuild creates a new part and preserves its
        source. Inspect recognizes ordinary recipes; terminal input splines and metric threads also
        receive a fresh ownership/geometry/driver audit at creation inputs.
        To change inputs, edit the inspected recipe and use create, not rebuild.
        Continue requires an exact opened saved construction-chain document_id and
        chain containing only NEW steps (optional name). It audits the immutable
        prefix before writing, appends in that document, and saves the same file.
        Standalone models and old-step edits are unsupported.
        Straight spline input/remove requires one explicit +X cylinder of uncut
        rotational stock, placement from target start with a positive offset and
        positive smooth stock beyond length_mm. Require include_tip_chamfer=false.
        For body=hub, select the explicit bore of one +X cylindrical stock with
        zero offset. Omit exit_mode or use through to cover the full through bore
        and link its length driver. Blind uses an independent shorter length from
        open entry in a flat-bottom bore, with positive smooth tail and bottom stock.
        The input bore
        and outside diameter are immutable; outside diameter is inherited from
        stock. Only corrected nominal counterpart revision2 is used. No arbitrary
        partial/interior span, tool runout, functional-length certification, reverse or
        subsequent operations. Numeric cross-profile is recreate-only. Initial
        own/create shaft splines are unchanged; own/create hubs are unsupported.
        External metric threads must be terminal on an explicit +X cylinder with
        no prior cuts; no later steps may be appended. Optional entry_mode=through
        requires a free start face or adjacent stock inside the root core.
        Optional exit_mode=blind makes length the last cut trace and requires a
        positive smooth carrier tail; incomplete end projection is audited, not
        certified functional length. Optional exit_mode=through covers the whole
        carrier and requires free exit space or adjacent stock inside the root
        core; two top and two root-tangent boundaries must cover the full span.
        No gradual runout or exit groove. Omitting
        ending fields preserves legacy complete exposed-carrier behavior.
        Internal metric threads require method_version=1, through entry and one
        cylindrical blank plus its explicit +X cylindrical bore target. Diameter
        is nominal; the bore is immutable. Through exit requires a full through
        bore and four full-span boundaries without a material cap. Blind exit
        uses length as the last cut trace, shorter than the bore depth; it audits
        the partial terminal section and positive smooth tail. A flat-bottom bore
        also protects the bottom/rear disks and stock behind the bottom. No drill
        point, controlled runout, functional-length certification or later operations.
        Plan returns sections and verification expectations, without native previews.
        A failure may retain a partial document; never retry an unknown write.
        """
        try:
            result = run_chain(adapter, action,
                chain.model_dump(by_alias=True, exclude_none=True, exclude_unset=action == "continue") if chain else None,
                document_id, confirm_write, visible)
        except RuntimeError as exc:
            partial = getattr(exc, "partial_result", None)
            if partial is None:
                raise
            return {"ok": False, "executed": partial.get("executed"), "verified": False,
                    "error": str(exc)[:2000], "partial_result": partial}
        if action == "plan":
            return {**{key: value for key, value in result.items() if key not in ("thread_prefix_plan", "spline_prefix_plan")}, "steps": [{key: value for key, value in step.items() if key not in ("preview", "gear_plan", "family_plan", "spline_application")}
                                       for step in result["steps"]]}
        return result

    @mcp.tool()
    def get_cad_module_contract(module_id: str | None = None) -> dict:
        """List implemented CAD modules, or get one module's schemas, defaults and examples.

        No CAD access or Studio needed. Capabilities distinguish creation,
        recognition and editing; use the returned module IDs, not display names.
        """
        return describe(module_id)

    @mcp.tool()
    def run_cad_module(request: CadModuleRequest) -> dict:
        """Preview, plan, create or inspect using a discovered module contract.

        Parameters follow get_cad_module_contract's parameter_schema. Preview and
        plan never call CAD. Create requires confirm_write=true and creates a new
        part using the module's creation_policy. Inspect needs the exact opened document_id; it recognizes a
        recipe, not fresh geometry. Runtime failures may leave a partial document;
        executed=null means write completion is unknown. Never retry blindly.
        """
        return run(request, adapter)
