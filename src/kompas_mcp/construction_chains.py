"""Bounded host-only coaxial planning (Layer 2) and single-job dispatch (Layer 3).

Legacy previews are adapted, not new EntitySpecs. Native execution, grouping,
readback and persistence belong to the bridge; host planning is not a CAD audit.
"""
from __future__ import annotations

import json
import hashlib
import math
import ntpath
import re
from copy import deepcopy
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cad_cone_bindings import ExternalConeParameters, cone_plan
from .cad_shaft_bindings import SteppedShaftParameters, shaft_plan
from .cad_polygon_bindings import polygon_plan
from .cad_flat_bindings import flat_plan
from .cad_modules import CAD_MODULES
from .gears.spec import SpurGearRequest
from .connections.cad import build_straight_spline_plan
from .connections.splines.spec import StraightSplineRequest
from .parametric import preview_part_scenario

MAX_STEPS = 32
MAX_RECIPE_BYTES = 24_000
MAX_PLAN_BYTES = 256_000
# Keep the new write mode closed until its interrupted live acceptance is settled.
# Native references, sketch state and measured verification are unavailable at
# planning time. Reserve headroom; this is not a guarantee on arbitrary COM data.
PERSISTENCE_OUTPUT_RESERVE = 1536
PERSISTENCE_METADATA_RESERVE = 1024
# Live native IDs are about 50 ASCII characters; allow 64 per stored identity.
# Longer native IDs remain subject to the actual envelope limit before save.
PERSISTENCE_OBJECT_ID_RESERVE = 64
ID = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class BoreParameters(SteppedShaftParameters):
    """Explicit cutter steps; no source scenario or implicit carrier."""


class GrooveParameters(_Model):
    inner_diameter: float = Field(gt=0)
    outer_diameter: float = Field(gt=0)
    depth: float = Field(gt=0)
    inner_wall_angle_degrees: float = Field(default=0, gt=-90, lt=90)
    outer_wall_angle_degrees: float = Field(default=0, gt=-90, lt=90)


class PolygonParameters(_Model):
    diameter: float = Field(gt=0)
    length: float = Field(gt=0)
    side_count: int = Field(ge=3, le=64)
    diameter_mode: Literal["inscribed_circle", "circumscribed_circle"] = "inscribed_circle"
    rotation_angle_degrees: float = 0


class FlatParameters(_Model):
    diameter: float = Field(gt=0)
    length: float = Field(gt=0)
    flat_depth: float = Field(gt=0)
    flats_count: Literal[1, 2] = 1


class BoltCircleParameters(_Model):
    hole_diameter: float = Field(gt=0)
    depth: float = Field(gt=0)
    bolt_circle_diameter: float = Field(gt=0)
    count: int = Field(ge=2, le=64)
    start_angle_degrees: float = 0
    clockwise: bool = False


class PlacementReference(_Model):
    step: ID
    anchor: Literal["start", "end"]


class ChainPlacement(_Model):
    reference: PlacementReference | None = None
    offset_mm: float = 0.0
    direction: Literal[-1, 1] = 1
    axis: Literal["global_x"] = "global_x"
    phase_degrees: Literal[0] = 0


class _Step(_Model):
    id: ID
    basis: Literal["own", "input"]
    material: Literal["create", "add", "remove"]
    target: ID | None = None
    placement: ChainPlacement = Field(default_factory=ChainPlacement)


class ShaftChainStep(_Step):
    module: Literal["stepped_shaft"]
    parameters: SteppedShaftParameters


class ConeChainStep(_Step):
    module: Literal["external_conical_step"]
    parameters: ExternalConeParameters


class BoreChainStep(_Step):
    module: Literal["internal_cylindrical_step"]
    parameters: BoreParameters


class GrooveChainStep(_Step):
    module: Literal["face_ring_groove"]
    parameters: GrooveParameters


class GearChainStep(_Step):
    module: Literal["gear_spur"]
    basis: Literal["own"]
    material: Literal["create"]
    target: None = None
    parameters: SpurGearRequest


class PolygonChainStep(_Step):
    module: Literal["external_polygonal_step"]
    parameters: PolygonParameters


class SplineParameters(StraightSplineRequest):
    """Numeric shaft foundation or terminal shaft/hub input-cylinder cut.

    Tip chamfers must neither meet nor enter the solid root core. Nominal
    geometry is not a machining or standard-conformity claim. Live chain
    evidence covers light 8x36x40 with chamfers/core bore/shaft/continued groove
    and custom z8/d35/D40/b6/r0.3 without chamfers with a shaft continuation.
    Input/remove is terminal on uncut +X cylindrical stock, with positive smooth
    margins at both ends and include_tip_chamfer=false; numeric cross-profile is
    recreate-only, while length drives native finite extrusion.
    A hub requires one cylinder plus its explicit bore at d and zero offset.
    Through covers the entire through bore; blind cuts from open entry into a
    flat-bottom bore with positive smooth tail and stock behind the bottom.
    Outside diameter is inherited from stock, not a default-wall heuristic.
    No tool runout or later operations.
    """
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    body: Literal["shaft", "hub"] = "shaft"
    exit_mode: Literal["through", "blind"] | None = Field(default=None,
        description="Hub only: omit/through covers the full through bore and links its length driver. Blind uses an independent shorter working length from open entry in a flat-bottom bore with positive smooth tail and bottom stock. Flat numeric termination, without tool runout or functional-length certification.")


class SplineChainStep(_Step):
    module: Literal["straight_spline"]
    basis: Literal["own", "input"]
    material: Literal["create", "remove"]
    target: ID | None = None
    parameters: SplineParameters

    @model_validator(mode="after")
    def supported_mode(self):
        if self.parameters.body == "shaft" and self.parameters.exit_mode is not None:
            raise ValueError("Spline exit_mode applies only to input hubs")
        if (self.basis, self.material) == ("own", "create") and self.target is None and self.parameters.body == "shaft":
            return self
        if (self.basis, self.material) == ("input", "remove") and self.target is not None:
            return self
        raise ValueError("Spline requires shaft own/create without target or shaft/hub input/remove with explicit target")


class FlatChainStep(_Step):
    module: Literal["external_flat_step"]
    parameters: FlatParameters


class BoltCircleChainStep(_Step):
    module: Literal["bolt_circle_holes"]
    parameters: BoltCircleParameters


class MetricThreadParameters(_Model):
    """External +X metric cylinder, through entry and explicit blind/through exit."""
    diameter: float = Field(gt=0)
    pitch: float = Field(gt=0)
    length: float = Field(gt=0)
    direction: Literal["right", "left"] = "right"
    entry_mode: Literal["through"] | None = Field(default=None,
        description="Entry at the target start face; adjacent stock must clear the root core. Omit to preserve legacy recipes.")
    exit_mode: Literal["blind", "through"] | None = Field(default=None,
        description="Blind: length ends at the last cut trace with a positive smooth tail. Through: full carrier length, cutter clears its end into free space or root-clear stock. No gradual runout/groove. Omit for legacy complete exposed-carrier behavior.")


class MetricThreadChainStep(_Step):
    module: Literal["external_helical_thread"]
    basis: Literal["input"]
    material: Literal["remove"]
    target: ID
    parameters: MetricThreadParameters


class InternalMetricThreadParameters(_Model):
    """Nominal internal metric diameter; immutable cylindrical bore on +X."""
    diameter: float = Field(gt=0, description="Nominal major thread diameter, not the existing bore diameter")
    pitch: float = Field(gt=0)
    length: float = Field(gt=0, description="Through: full bore length. Blind: distance from entry to last cut trace, shorter than bore depth")
    direction: Literal["right", "left"] = "right"
    method_version: Literal[1] = 1
    entry_mode: Literal["through"] = "through"
    exit_mode: Literal["through", "blind"] = "through"


class InternalMetricThreadChainStep(_Step):
    module: Literal["internal_helical_thread"]
    basis: Literal["input"]
    material: Literal["remove"]
    target: ID
    parameters: InternalMetricThreadParameters


_THREAD_MODULES = ("external_helical_thread", "internal_helical_thread")


ChainStep = Annotated[ShaftChainStep | ConeChainStep | BoreChainStep | GrooveChainStep | GearChainStep | SplineChainStep | PolygonChainStep | FlatChainStep | BoltCircleChainStep | MetricThreadChainStep | InternalMetricThreadChainStep,
                      Field(discriminator="module")]


class ConstructionChain(_Model):
    schema_: Literal["geomwright.construction_chain.recipe"] = Field(
        default="geomwright.construction_chain.recipe", alias="schema")
    version: Literal[1] = 1
    name: str = Field(default="Construction chain", min_length=1, max_length=120)
    steps: list[ChainStep] = Field(min_length=1, max_length=MAX_STEPS)


_LABELS = {"stepped_shaft": "Stepped shaft", "external_conical_step": "External cone",
           "internal_cylindrical_step": "Internal cylindrical bore", "face_ring_groove": "Face ring groove",
            "gear_spur": "External cylindrical gear", "external_polygonal_step": "External polygon",
            "external_flat_step": "External flat", "bolt_circle_holes": "Bolt circle holes",
             "straight_spline": "Straight spline shaft"}


def get_construction_chain_contract() -> dict:
    models = {"stepped_shaft": SteppedShaftParameters, "external_conical_step": ExternalConeParameters,
              "internal_cylindrical_step": BoreParameters, "face_ring_groove": GrooveParameters,
               "gear_spur": CAD_MODULES["gear_spur"].request_model,
               "external_polygonal_step": PolygonParameters, "external_flat_step": FlatParameters,
               "bolt_circle_holes": BoltCircleParameters, "straight_spline": SplineParameters,
                "external_helical_thread": MetricThreadParameters, "internal_helical_thread": InternalMetricThreadParameters}
    return {"schema": "geomwright.construction_chain.contract", "version": 1,
            "recipe_schema": ConstructionChain.model_json_schema(by_alias=True),
            "actions": ["plan", "create", "inspect", "rebuild", "continue"],
            "continuation": {"implemented": True, "cad_verified": True,
                "target": "exact opened saved construction-chain document",
                "inputs": "recipe containing only new steps; optional name",
                "save_policy": "same_selected_file", "old_step_editing": False},
            "limits": {"max_steps": MAX_STEPS, "max_recipe_bytes": MAX_RECIPE_BYTES,
                       "max_persistence_ascii_bytes": MAX_RECIPE_BYTES,
                       "max_plan_ascii_bytes": MAX_PLAN_BYTES,
                        "persistence_output_reserve_per_step": PERSISTENCE_OUTPUT_RESERVE,
                        "persistence_object_id_reserve": PERSISTENCE_OBJECT_ID_RESERVE,
                       "persistence_metadata_reserve": PERSISTENCE_METADATA_RESERVE},
            "modules": {key: {"parameter_schema": model.model_json_schema(),
                "supported_modes": [{"basis": "own", "material": "create"},
                                    {"basis": "own", "material": "add"}] if key in
                                     ("stepped_shaft", "external_conical_step", "external_polygonal_step", "external_flat_step") else
                                     [{"basis": "own", "material": "create"}, {"basis": "input", "material": "remove"}] if key == "straight_spline" else
                                     [{"basis": "own", "material": "create"}] if key == "gear_spur" else
                                    [{"basis": "input", "material": "remove"}],
                "integration": "existing_family_plan" if key == "straight_spline" else "registered_family_plan" if key == "gear_spur" else "legacy_preview_adapter",
                   "cad_chain_verified": True,
                   **({"input_application": {"terminal_only": True, "directions": [1],
                       "carrier": "explicit uncut cylindrical stepped_shaft section at spline D",
                       "end_policy": "positive smooth margins at both ends", "tip_chamfer": False,
                       "tool_runout": False, "cross_profile_editing": "recreate_only",
                       "native_length_driver": True,
                       "hub": {"implemented": True, "profile_geometry_revision": 2,
                            "carrier": "one +X cylindrical stock plus explicit cylindrical bore at spline d",
                            "target": "bore step", "offset_mm": 0,
                            "length_policy": "through_full_bore_or_blind_positive_tail_and_bottom_stock",
                           "outside_diameter": "inherited_immutable_stock", "bore_policy": "immutable",
                            "length_binding": {"through": "native_bore_length_driver", "blind": "independent_native_cut_length_driver"},
                            "blind_end_policy": "flat_numeric_cutter_without_runout",
                            "functional_length_verified": False,
                            "blind_cad_accepted": True,
                            "exit_modes": ["through", "blind"]}}} if key == "straight_spline" else {}),
                   **({"terminal_only": True, "directions": [1], "turn_count_bounds": [2, 64],
                        "entry_modes": ["through"], "exit_modes": ["blind", "through"],
                        "legacy_end_behavior": "complete_exposed_carrier",
                         "volume_reference": "audited_native_terminal_thread"} if key == "external_helical_thread" else {}),
                 **({"terminal_only": True, "directions": [1], "turn_count_bounds": [2, 64],
                     "entry_modes": ["through"], "exit_modes": ["through"], "method_version": 1,
                     "bore_policy": "immutable_input", "diameter_semantics": "nominal_major_diameter",
                     "volume_reference": "audited_native_terminal_thread"} if key == "internal_helical_thread" else {})}
                for key, model in models.items()},
            "placement": {"axis": "global_x", "directions": [-1, 1], "phase_degrees": [0],
                          "offset_frame": "global_x", "references": "earlier step start/end",
                          "editing": "recreate_only", "cad_binding": "numeric_fixed_point"},
             "macro_grouping": {"enabled": True, "ownership": "own roots and auxiliary supports only; no input body or default objects",
                               "identity_after_ungroup": "saved recipe and root references"},
               "limitations": ["Continuation is live-verified on saved gear/hub/bore and shaft/polygon/bore chains with appended face grooves, and shaft/flat/bore with appended bolt-circle holes; no old-step editing or arbitrary orientation.",
                  "Flat sections support one or two opposing flats, own/create or own/add, with an inscribed-core carrier. Live evidence covers D30/F4 in both axial directions, repeated reopen and core bore. No side/corner finishing.",
                  "Bolt-circle holes require input/remove with explicit constructor target; their full depth stays inside that carrier, not automatically through the whole part. Count 2..64 is a cost bound. Disjointness uses conservative radial exclusion envelopes; angularly disjoint overlapping rings are refused. Start angle and shared placement are recreate-only; diameter/depth/PCD/count drive native geometry and angle step derives from count. Live evidence covers four holes and reverse three-hole clockwise placement, core bore, saved-file continue and reopen.",
                  "Polygon uses the existing regular-prism planner; carrier is its inscribed core, not a cylindrical final face. Live chain evidence: D30/L10 hexagon appended to a D40/L20 shaft with D8 bore and ID12/OD20/depth2 end groove; reverse D32/L22 pentagon at X7, angle17 with D20/L8 shaft addition. No polygon finishing or nonzero shared phase.",
                 "Gear foundation: initial own/create at origin 0, direction +1; native span is [-face_width, 0]. Live chain evidence covers m2/z20/b20, spur without tip chamfer; helical/chamfer variants are host-planned, not live chain-certified.",
                    "Straight spline shaft foundation uses the existing GOST 1139-80 plan, numeric recreate-only contour and optional tip chamfers; initial origin 0/direction +1, native span [-length_mm,0]. Terminal input/remove shaft cuts require an uncut +X cylinder with positive smooth margins. Hub cuts require one +X cylinder and its explicit bore at d, zero offset, corrected nominal counterpart revision2 and immutable inherited outside diameter. Omit exit_mode or use through for the entire through bore with linked bore-length driver; blind uses an independent shorter length from open entry in a flat-bottom bore, with positive smooth tail and bottom stock. Source/all removal, tail, flat terminal faces, bottom/rear disks and outer wall are audited. Standard create/continue/rebuild/reopen and custom create/reopen passed; blind length20->22->20/save/reopen passed. Require include_tip_chamfer=false. No arbitrary partial/interior span, runout, functional-length certification, reverse or subsequent operations.",
                  "Gear/spline-chain additions are stepped_shaft cylindrical sections appended at the exposed +X end only; the first spline addition must fit inside the solid core at the joining end.",
                "Gear cuts select only the solid root core, not the teeth; a continuous gear/hub bore uses two explicit nonoverlapping cuts.",
                  "External metric thread is terminal-only input/remove on an explicit +X cylindrical stepped_shaft target at target start/zero offset; diameter must match, 2..64 turns, automatic round root only and no prior cuts. Optional entry_mode=through requires a free face or adjacent stock strictly inside the root core. Optional exit_mode=blind makes length the last cut trace before the carrier end with positive smooth tail and protected rotational exit stock. Explicit exit_mode=through covers the whole carrier and requires free exit space or stock strictly inside the root core; two top and two root-tangent full-span boundaries and no material endcap are audited. Omitted ending fields retain legacy complete exposed-carrier behavior, exact target length and original one-witness criterion. Public lifecycle passed M20x2.5 with D12/L12 entry neck: legacy D20/L20 carrier, blind D30/L12 exit shoulder, through D12/L12 exit neck and free face. Blind entries, arbitrary interior starts, controlled runout, grooves, other thread families, later operations and in-place recipe editing are unsupported; nominal geometry/projection is not a manufacturing or functional full-profile certificate.",
                  "Internal metric thread is terminal-only input/remove on an explicit +X internal_cylindrical_step bore after one single stepped_shaft cylinder; no other prefix cuts or later steps. Nominal diameter is distinct from the immutable bore diameter and must leave a positive wall. Version 1 supports through entry and through/blind exit, automatic round root and 2..64 turns. Through exit requires the full through bore and four full-span boundaries without a material cap. Blind length ends at the last cut trace before the bore end, with a positive smooth tail and audited partial terminal section; a flat-bottom bore also protects bottom/rear disks and binds stock behind the bottom. Inspect requires original recipe inputs. Drill points, controlled runout, functional-length certification, grooves, multi-step bores/stock and other families are unsupported.",
                 "Inspect recognizes ordinary saved recipes; terminal-thread recipes additionally require a fresh ownership/geometry/driver audit at creation inputs. Changed native drivers must be restored before this audit/rebuild; use a new recipe/create for changed inputs.",
                "Additions must attach at an exposed axial end without overlap; cuts may not overlap prior cuts.",
                "Live evidence covers these four families on global +/-X, phase 0, axial offset and repeated shafts; not all parameter combinations.",
                "Nonzero groove wall angles are host-planned, but live chain evidence covers zero wall angles only.",
                "Macro grouping, rebuild, save/reopen and ungroup were verified on the supported rotational chain.",
                "Persistence preflight reserves native-output headroom; native checks the actual envelope before saving."]}


def _bounded(recipe: dict) -> None:
    if len(json.dumps(recipe, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")) > MAX_RECIPE_BYTES:
        raise ValueError("Construction chain recipe exceeds 24000 UTF-8 bytes")


def _ascii_size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def _check_persistence_budget(recipe: dict, steps: list[dict]) -> None:
    # Match native _validate's envelope, not just the user-facing recipe. Keep
    # this projection explicit: previews must never be persisted as expectations.
    keys = ("id", "module", "namespace", "material", "basis", "target", "placement",
            "section", "expected_delta_cm3", "expected_total_volume_cm3", "verification")
    expectations = [{key: step[key] for key in keys} for step in steps]
    envelope = {"schema": recipe["schema"], "version": 1, "recipe": recipe,
                "expectations": expectations, "outputs": []}
    if _ascii_size(envelope) > MAX_RECIPE_BYTES:
        raise ValueError("Construction chain persistence envelope exceeds 24000 ASCII bytes")
    # Account for known output data as well as unknown native readback. Names
    # occur twice (saved/current) after ownership verification.
    outputs = []
    for step in steps:
        operations = (step["spline_application"]["operations"] if "spline_application" in step else
                      (step.get("family_plan") or step.get("gear_plan"))["workflow"]["params"]["operations"]
                      if step["module"] in ("gear_spur", "straight_spline") else step["preview"]["operations"])
        names = [name for op in operations for name in
                  (op.get("name"), op.get("params", {}).get("name"), op.get("params", {}).get("sketch_name")) if name]
        # Ordinary outputs store sketch/feature/macro identities. Gear outputs
        # also store owned roots, including two duplicated primary roots.
        identity_count = 3
        if step["module"] in ("external_polygonal_step", "external_flat_step"):
            identity_count = 7  # point/plane/sketch/extrusion/macro and duplicate primary identities
        if step["module"] == "bolt_circle_holes":
            identity_count = 12
        if step["module"] in _THREAD_MODULES:
            identity_count = 10
        if step["module"] in ("gear_spur", "straight_spline"):
            identity_count = 3 + sum({"cylindrical_blank": 5, "numeric_profile_sketch": 1,
                "cut_extrusion": 1, "helical_cut_evolution": 4, "circular_pattern": 1,
                "rotational_cut": 2}[op["scenario"]] for op in operations)
        outputs.append({"id": step["id"], "namespace": step["namespace"], "section": step["section"],
            "names": names * 2,
            "object_ids": ["x" * PERSISTENCE_OBJECT_ID_RESERVE] * identity_count,
            "variable_names": [v["name"] for op in operations for v in op.get("variables", [])],
            "dimension_names": [d["name"] for op in operations for d in op.get("dimensions", []) if d.get("name")]})
    envelope["outputs"] = outputs
    estimate = _ascii_size(envelope) + PERSISTENCE_METADATA_RESERVE + len(steps)*PERSISTENCE_OUTPUT_RESERVE
    if estimate > MAX_RECIPE_BYTES:
        raise ValueError("Construction chain persistence budget exceeds 24000 ASCII bytes including native-output reserve; split or simplify the chain")


def _adapt_preview(preview: dict, namespace: str, label: str, origin: float, direction: int, *, transverse=False) -> dict:
    """Transform X only, including dimension display and signed coordinate anchors.

    Geometry is already global, so keep native sketch placement identity and the
    original fixed-point anchors, which lock the actual transformed coordinates.
    Placement is numeric and recreate-only, not an inter-step CAD driving link.
    """
    preview = deepcopy(preview)
    old = preview["params"]["parameter_prefix"]
    thread = preview["scenario"] in ("external_helical_thread", "internal_helical_thread")
    if preview["scenario"] == "internal_helical_thread" and not preview["params"].get("internal_metric_method"):
        raise ValueError("Internal thread placement requires the versioned source-free method")
    public_names = {}
    if thread:
        if direction != 1:
            raise ValueError("Initial physical thread placement requires global +X")
        public_names = {preview["params"]["public_"+key+"_variable_name"]: namespace+suffix
                        for key, suffix in (("diameter", "_D1"), ("pitch", "_P1"), ("length", "_L1"))}
    def rename(value):
        if isinstance(value, str):
            value = re.sub(r"\b" + re.escape(old) + r"(?=_|\b)", namespace, value)
            if public_names:
                value = re.sub(r"\b("+"|".join(map(re.escape, public_names))+r")\b",
                               lambda match: public_names[match[0]], value)
            return value
        if isinstance(value, list):
            return [rename(item) for item in value]
        if isinstance(value, dict):
            return {key: rename(item) for key, item in value.items()}
        return value
    preview = rename(preview)
    p = preview["params"]
    p.update(name=label, sketch_name=label + " profile", parameter_prefix=namespace,
             fix_sketch_placement=True, require_fully_defined=True)
    # Cut normalization must never carry a source body into the bridge.
    for key in ("source_scenario", "source_params", "source_preview"):
        p.pop(key, None)
    operations = [op for op in preview["operations"] if op["operation"] != "create_part_document"]
    if thread:
        # Family profile coordinates remain local to their placed LCS. Only the
        # selected working span moves; no legacy source operation may survive.
        operations = [op for op in operations if op["operation"] != "create_source_body"]
        for key in ("source_variable_bindings", "source_selector", "start_selector", "end_selector", "source_origin"):
            p.pop(key, None)
        p.update(start_origin=[origin, 0, 0], end_origin=[origin+p["length"], 0, 0],
                 feature_display_name=label+" cut", profile_display_name=label+" profile",
                 path_display_name=label+" spiral", axis_display_name=label+" axis",
                 start_center_name=label+" start centre", profile_origin_name=label+" profile origin")
    if any(op["operation"] == "create_source_body" for op in operations):
        raise ValueError("Hidden source bodies are forbidden")
    for op in operations:
        kind = op["operation"]
        if kind == "draw_axis" and not transverse:
            for key in ("start", "end"):
                op[key] = [origin + direction * op[key][0], op[key][1]]
        elif kind == "draw_profile" and not transverse:
            op["profile_points"] = [[origin + direction*x, y] for x, y in op["profile_points"]]
        elif kind == "add_dimensions" and not transverse:
            for dim in op["dimensions"]:
                if preview["scenario"] == "face_ring_groove" and dim["kind"] == "circle_diameter":
                    dim.update(kind="line_length", target="axis", label="axial groove depth")
                if "point_x" in dim:
                    dim["point_x"] = origin + direction * dim["point_x"]
                if dim["kind"] == "point_coordinate" and dim.get("orientation") == "horizontal":
                    dim["value"] = origin + direction * dim["value"]
                    dim["expression"] = f"({origin}) + ({direction}) * ({dim['expression']})"
        if kind == "create_sketch":
            op["name"] = label + " profile"
        if kind in ("base_rotation", "cut_rotation"):
            op["name"] = label + (" cut rotation" if kind == "cut_rotation" else " rotation")
    preview["operations"] = operations
    # Legacy interfaces describe local previews, not current global chain sections.
    preview.pop("interface", None)
    preview["chain_placement"] = {"origin_mm": origin, "direction": direction, "frame": "global_x"}
    return preview


def _segment(start: float, end: float, r0: float, r1: float) -> dict:
    if end < start:
        start, end, r0, r1 = end, start, r1, r0
    return {"axial_min": start, "axial_max": end, "start_radius_mm": r0, "end_radius_mm": r1}


def _gear_plan(parameters: dict, namespace: str, label: str) -> dict:
    """Reuse the registered pure family planner; keep workflow-local IDs intact."""
    plan = CAD_MODULES["gear_spur"].plan(parameters, name=label)
    def rename(value):
        if isinstance(value, str):
            return re.sub(r"\b(GEAR|SKETCH)(?=_|\b)",
                          lambda match: namespace if match[0] == "GEAR" else namespace + "_SKETCH", value)
        if isinstance(value, list):
            return [rename(item) for item in value]
        if isinstance(value, dict):
            return {rename(key): rename(item) for key, item in value.items()}
        return value
    plan = rename(plan)
    # Family metadata is installed by native execution, not by the numeric workflow.
    plan["parameter_prefix"] = namespace
    return plan


def _internal_metric_carrier_guard(plan: dict, target: str, params: dict, *, end_plan: dict | None = None, _flat_bottom: bool = False) -> dict:
    """Layer 2 preflight for internal stock and private blind endpoint evidence.

    No COM or public chain registration. Select a complete cylindrical bore in
    one complete cylindrical blank, not the outer constructor or an arbitrary
    cut surface. Flat-bottom stock is reserved for the private endpoint branch;
    the public through contract remains complete-bore only. A native reader
    must still verify those faces and ownership.
    """
    if plan != plan_construction_chain(plan.get("recipe")):
        raise ValueError("Internal thread input plan differs from its canonical recipe")
    if end_plan is not None:
        from .parametric import _plan_internal_metric_end
        physical = plan["steps"][-1]["section"]["axial_interval_mm"]
        full = deepcopy(params)
        full.update(length=physical[1]-physical[0], end_origin=[physical[1], 0, 0],
                    spiral_length=physical[1]-physical[0]+1.3*params["pitch"]+params["profile_outer_half_width"])
        carrier = _internal_metric_carrier_guard(plan, target, full, _flat_bottom=end_plan.get("bore_has_bottom") is True)
        expected = _plan_internal_metric_end(full, exit_mode="blind", thread_length=params["length"],
            bore_span=physical, stock_span=plan["steps"][0]["section"]["axial_interval_mm"])
        if end_plan != expected or params["end_origin"] != [expected["last_cut_trace_mm"], 0, 0]:
            raise ValueError("Internal blind guard differs from its canonical endpoint plan")
        if params["spiral_length"] != expected["spiral_length_mm"] or next(
                b for b in params["operation_variable_bindings"] if b["role"] == "spiral_height") != expected["height_binding"]:
            raise ValueError("Internal blind height differs from the endpoint driver plan")
        return {**carrier, "scope": "blind_internal_metric_cylinder_positive_x",
                "working_span_mm": expected["working_span_mm"], "carrier_span_mm": physical,
                "carrier_guard": carrier, "end_plan": deepcopy(expected),
                "removal_upper_bound_cm3": math.pi*(carrier["major_radius_mm"]**2-carrier["bore_radius_mm"]**2)*params["length"]/1000}
    recipe = plan["recipe"]["steps"]
    if (len(recipe) != 2 or recipe[0]["module"] != "stepped_shaft" or
            recipe[1]["module"] != "internal_cylindrical_step" or target != recipe[1]["id"] or
            recipe[1]["target"] != recipe[0]["id"] or
            any(len(s["parameters"]["steps"]) != 1 for s in recipe)):
        raise ValueError("Internal thread requires one cylindrical blank and one explicit through bore")
    stock, bore = plan["steps"]
    spans = [s["section"]["axial_interval_mm"] for s in (stock, bore)]
    valid_span = (spans[0][0] == spans[1][0] and spans[0][1] > spans[1][1]) if _flat_bottom else spans[0] == spans[1]
    if not valid_span or any(s["section"]["end_mm"] <= s["section"]["start_mm"] for s in (stock, bore)):
        raise ValueError("Internal thread requires a complete +X through bore with free end faces")
    lo, hi = spans[1]
    outer = float(recipe[0]["parameters"]["steps"][0]["diameter"]) / 2
    inner = float(recipe[1]["parameters"]["steps"][0]["diameter"]) / 2
    diameter, pitch, length = (float(params[key]) for key in ("diameter", "pitch", "length"))
    carrier, cut_depth = (float(params[key]) for key in ("carrier_diameter", "radial_cut_depth"))
    method = params.get("internal_metric_method")
    expected_method = {"schema": "geomwright.internal_metric_through.plan", "version": 1,
        "bore_diameter_mm": 2 * inner, "bore_policy": "immutable_input",
        "diameter_driver_semantics": "nominal_major_diameter", "profile_depth_semantics": "actual_radial_cut",
        "native_verification_required": True, "functional_thread_length_verified": False}
    if (method != expected_method or not params.get("internal") or
            params.get("thread_profile_family") != "metric_v60" or
            params.get("carrier_shape") != "cylindrical" or params.get("profile_root_shape") != "round" or
            not all(math.isfinite(v) for v in (diameter, pitch, length, lo, hi, outer, inner, carrier, cut_depth)) or
            pitch <= 0 or length <= 0 or not 2 <= length / pitch <= 64 or
            not 0 < inner < diameter / 2 < outer or abs(length - (hi - lo)) > 1e-6 or
            params.get("start_origin") != [lo, 0, 0] or params.get("end_origin") != [hi, 0, 0] or
            abs(carrier - 2 * inner) > 1e-9):
        raise ValueError("Internal thread profile/working span does not match the explicit bore")
    depth = diameter / 2 - inner
    if abs(cut_depth - depth) > 1e-9:
        raise ValueError("Internal thread depth differs from nominal diameter and immutable bore")
    result = {"schema": "geomwright.internal_metric_carrier.guard", "version": 1,
        "scope": "flat_bottom_internal_metric_cylinder_positive_x" if _flat_bottom else "complete_internal_metric_cylinder_positive_x", "target": target,
        "stock_target": recipe[0]["id"], "axis": "global_x", "body_count": 1,
        "working_span_mm": [lo, hi], "bore_radius_mm": inner, "major_radius_mm": diameter / 2,
        "outer_radius_mm": outer, "root_tangent_radius_mm": diameter / 2 - pitch / (32 * math.cos(math.pi / 6)),
        "expected_blank_volume_cm3": math.pi * (outer**2 - inner**2) * length / 1000,
        "removal_upper_bound_cm3": math.pi * ((diameter / 2)**2 - inner**2) * length / 1000,
        "input_bore_immutable": True, "native_carrier_verified": False,
        "material_preservation_verified": False}
    if _flat_bottom:
        result.update(stock_span_mm=spans[0], bottom_stock_thickness_mm=spans[0][1]-hi,
            expected_blank_volume_cm3=math.pi*(outer**2*(spans[0][1]-lo)-inner**2*length)/1000)
    return result


def _straight_spline_input_carrier_guard(plan: dict, target: str, application: dict, *, exit_mode="through") -> dict:
    """Pure private preflight; never authorizes CAD or exposes a new chain mode."""
    from .connections.cad import _plan_straight_spline_input_shaft
    if application.get("schema") == "geomwright.straight_spline.input_hub.plan":
        return _straight_spline_input_hub_guard(plan,target,application,exit_mode=exit_mode)
    if plan != plan_construction_chain(plan.get("recipe")):
        raise ValueError("Spline input prefix differs from its canonical recipe")
    steps = plan["steps"]
    if any(s["module"] not in ("stepped_shaft", "external_conical_step") or
           s["basis"] != "own" or s["material"] not in ("create", "add") for s in steps):
        raise ValueError("Input spline requires uncut rotational stock; other foundations and prior cuts are unsupported")
    matches = [s for s in steps if s["id"] == target]
    if len(matches) != 1:
        raise ValueError("Input spline requires one explicit constructor target")
    carrier = matches[0]
    section = carrier["section"]
    if (carrier["module"] != "stepped_shaft" or carrier["placement"]["direction"] != 1 or
            section["axis"] != "global_x" or section["phase_degrees"] != 0 or len(section["segments"]) != 1):
        raise ValueError("Input spline target must be one +X cylindrical constructor")
    segment = section["segments"][0]
    radius = segment["start_radius_mm"]
    lo, hi = application["working_span_mm"]
    if (not all(math.isfinite(v) for v in (lo,hi)) or not section["start_mm"] <= lo < hi <= section["end_mm"]):
        raise ValueError("Spline working span must stay within the selected cylinder")
    expected = _plan_straight_spline_input_shaft(application["profile_request"], carrier_diameter_mm=2*radius,
                                               axial_start_mm=lo, name=application["name"])
    if application != expected:
        raise ValueError("Spline input plan differs from the canonical shaft family cutter")
    protected = []
    stock = []
    for step in steps:
        other = step["section"]
        if other["axis"] != "global_x" or other["phase_degrees"] != 0:
            raise ValueError("Input spline stock must share the global X axis")
        stock.extend(other["segments"])
        for row in other["segments"]:
            a, b = row["axial_min"], row["axial_max"]
            if step["id"] != target:
                if min(b,hi) > max(a,lo):
                    raise ValueError("Spline working span overlaps non-target stock")
                protected.append({"step_id": step["id"], "segment": deepcopy(row)})
                continue
            for start, end in ((a,lo),(hi,b)):
                if start < end:
                    protected.append({"step_id": target, "segment": _segment(start,end,radius,radius)})
    return {"schema": "geomwright.straight_spline.input_carrier.guard", "version": 1,
        "scope": "bounded_external_spline_cylinder_positive_x", "target": target,
        "carrier_span_mm": section["axial_interval_mm"], "working_span_mm": [lo,hi],
        "carrier_radius_mm": radius, "root_radius_mm": application["geometry"]["root_radius_mm"],
        "protected_stock": protected, "expected_blank_volume_cm3": _volume(stock),
        "expected_removed_cm3": application["expected_removal_cm3"],
        "expected_final_volume_cm3": _volume(stock)-application["expected_removal_cm3"],
        "body_count": 1, "native_carrier_verified": False, "material_preservation_verified": False}


def _straight_spline_input_hub_guard(plan: dict, target: str, application: dict, *, exit_mode="through") -> dict:
    from .connections.cad import _plan_straight_spline_input_hub
    if plan != plan_construction_chain(plan.get("recipe")):
        raise ValueError("Spline input prefix differs from its canonical recipe")
    steps = plan["steps"]
    if (len(steps)!=2 or steps[0]["module"]!="stepped_shaft" or steps[0]["material"]!="create" or
            steps[1]["module"]!="internal_cylindrical_step" or steps[1]["id"]!=target or
            steps[1]["target"]!=steps[0]["id"] or any(len(s["section"]["segments"])!=1 or
            s["placement"]["direction"]!=1 for s in steps)):
        raise ValueError("Input hub spline requires one +X cylindrical stock and its explicit cylindrical through bore")
    stock,bore = [s["section"] for s in steps]
    lo,hi = application["working_span_mm"]
    if exit_mode == "through":
        if stock["axial_interval_mm"]!=bore["axial_interval_mm"] or [lo,hi]!=bore["axial_interval_mm"]:
            raise ValueError("Through input hub splines must cover the full through bore")
    elif exit_mode == "blind":
        if (lo!=stock["start_mm"] or lo!=bore["start_mm"] or
                not lo < hi < bore["end_mm"]-1e-5 < stock["end_mm"]-2e-5):
            raise ValueError("Blind input hub requires open entry, positive smooth bore tail and stock behind a flat bottom")
    else:
        raise ValueError("Unsupported spline hub exit_mode")
    outside = 2*stock["segments"][0]["start_radius_mm"]
    diameter = 2*bore["segments"][0]["start_radius_mm"]
    expected = _plan_straight_spline_input_hub(application["profile_request"],carrier_outside_diameter_mm=outside,
        bore_diameter_mm=diameter,axial_start_mm=bore["start_mm"],name=application["name"])
    if application!=expected:
        raise ValueError("Input hub cutter differs from the corrected canonical family profile")
    removed = application["expected_removal_cm3"]
    blank = plan["expected_total_volume_cm3"]
    guard = {"schema":"geomwright.straight_spline.input_carrier.guard","version":1,
        "scope":"through_internal_spline_cylinder_positive_x","target":target,"stock_target":steps[0]["id"],
        "carrier_span_mm":bore["axial_interval_mm"],"working_span_mm":[lo,hi],
        "carrier_radius_mm":application["geometry"]["outer_diameter_mm"]/2,"root_radius_mm":diameter/2,
        "stock_outer_radius_mm":outside/2,"bore_length_expression":steps[1]["namespace"]+"_L1",
        "protected_stock":[],"expected_blank_volume_cm3":blank,"expected_removed_cm3":removed,
        "expected_final_volume_cm3":blank-removed,"body_count":1,"native_carrier_verified":False,
        "material_preservation_verified":False}
    if exit_mode == "blind":
        guard["scope"]="blind_internal_spline_cylinder_positive_x"
        guard["bore_depth_expression"]=guard.pop("bore_length_expression")
        guard.update(stock_span_mm=stock["axial_interval_mm"],smooth_tail_span_mm=[hi,bore["end_mm"]],
            bottom_stock_mm=stock["end_mm"]-bore["end_mm"],terminal_end_policy="flat_numeric_cutter_without_runout")
    return guard


def _radius(segment: dict, x: float) -> float:
    t = (x-segment["axial_min"]) / (segment["axial_max"]-segment["axial_min"])
    return segment["start_radius_mm"] + t*(segment["end_radius_mm"]-segment["start_radius_mm"])


def _volume(segments: list[dict]) -> float:
    return math.fsum(math.pi*(s["axial_max"]-s["axial_min"])*
        (s["start_radius_mm"]**2+s["start_radius_mm"]*s["end_radius_mm"]+s["end_radius_mm"]**2)/3000
        for s in segments)


def _overlaps(a: dict, b: dict) -> bool:
    return min(a["axial_max"], b["axial_max"]) > max(a["axial_min"], b["axial_min"])


def _removed_regions(outer, inner):
    return [dict(s, inner_start_radius_mm=inner[i]["start_radius_mm"] if inner else 0,
                 inner_end_radius_mm=inner[i]["end_radius_mm"] if inner else 0)
            for i, s in enumerate(outer)]


def _inner_radius(s, x):
    return _radius(dict(s, start_radius_mm=s.get("inner_start_radius_mm", 0),
                       end_radius_mm=s.get("inner_end_radius_mm", 0)), x)


def _inside_carrier(cutters: list[dict], carrier: dict) -> None:
    lo, hi = carrier["axial_interval_mm"]
    for cutter in cutters:
        if cutter["axial_min"] < lo or cutter["axial_max"] > hi:
            raise ValueError("Cut extends beyond selected carrier section")
        for segment in carrier["segments"]:
            if _overlaps(cutter, segment):
                for x in (max(cutter["axial_min"], segment["axial_min"]),
                          min(cutter["axial_max"], segment["axial_max"])):
                    if _radius(cutter, x) >= _radius(segment, x):
                        raise ValueError("Cut diameter must be smaller than carrier at every span")


def _plan_metric_thread_end(params: dict, exit_mode="blind") -> dict:
    """Plan a metric cutter ending; no carrier acceptance, CAD or recipe writes.

    The +X cylindrical sweep's terminal section is centred P/4 behind its
    nominal end. This local kernel-frame offset is backed by M20 right P2/P2.5
    and left P2.5 readback, not by a thread standard or a manufacturing runout.
    Use the normalized cutter width, not the path endpoint, for the last trace.
    This internal plan does not widen the public terminal-only chain contract.
    """
    tolerance = 1e-6  # geometric consistency, never a machining allowance
    if exit_mode not in ("blind", "through"):
        raise ValueError("Metric end plan supports blind or through exit only")
    kind = exit_mode.title()
    if (params.get("thread_profile_family") != "metric_v60" or params.get("internal") or
            params.get("carrier_shape") != "cylindrical" or params.get("crest_round_pass") or
            params.get("profile_root_shape") != "round" or
            params.get("thread_depth_mode") != "auto" or
            params.get("root_round_radius_mode") != "auto" or
            params.get("profile_entry_offset_mode") != "auto" or
            params.get("profile_surface_offset_applied")):
        raise ValueError(f"{kind} end plan requires the automatic external cylindrical metric round-root profile")
    try:
        pitch, length = float(params["pitch"]), float(params["length"])
        radius = float(params["carrier_radius"])
        half_width = float(params["profile_outer_half_width"])
        entry = float(params["profile_entry_offset"])
        start, end = [list(map(float, params[key])) for key in ("start_origin", "end_origin")]
        points = [list(map(float, point)) for point in params["profile_points"]]
        angle, clearance = float(params["profile_angle_degrees"]), float(params["clearance"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{kind} end plan requires normalized finite dimensions and profile") from exc
    values = [pitch, length, radius, half_width, entry, angle, clearance, *start, *end,
              *(value for point in points for value in point)]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{kind} end plan dimensions must be finite")
    if pitch <= 0 or radius <= 0 or not 2 <= length/pitch <= 64 or not 0 < half_width < pitch/2:
        raise ValueError(f"{kind} end plan requires a positive metric profile and 2..64 turns")
    if (len(start) != 3 or len(end) != 3 or any(abs(v) > tolerance for v in (*start[1:], *end[1:])) or
            abs(end[0]-start[0]-length) > tolerance):
        raise ValueError(f"{kind} end plan requires a consistent global +X requested span")
    if (abs(angle-60) > tolerance or abs(clearance) > tolerance or
            abs(half_width/pitch-7/16) > tolerance or abs(entry/pitch-1.05) > tolerance):
        raise ValueError(f"{kind} end plan excludes modified metric contour or entry allowance")
    if (len(points) != 5 or any(len(point) != 2 for point in points) or
            any(abs(a-b) > tolerance for a, b in zip(points[0], points[-1]))):
        raise ValueError(f"{kind} end plan requires the normalized closed metric cutter contour")
    # Top vertices are the material-envelope witnesses; all other vertices must
    # remain inside this envelope. Root-arc generation still belongs to family.
    if (any(abs(points[index][0]-x) > tolerance or abs(points[index][1]-radius) > tolerance
            for index, x in ((0, -half_width), (3, half_width))) or
            any(abs(x) > half_width+tolerance or not 0 < y <= radius+tolerance for x, y in points)):
        raise ValueError(f"{kind} end plan profile width differs from its cutter envelope")
    bindings = [binding for binding in params.get("operation_variable_bindings", [])
                if binding.get("role") == "spiral_height" and binding.get("target") == "spiral_path"]
    names = [params.get(key) for key in ("public_length_variable_name", "public_pitch_variable_name")]
    if (len(bindings) != 1 or names[0] == names[1] or
            any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names)):
        raise ValueError(f"{kind} end plan requires one height binding and explicit length/pitch drivers")
    phase_offset = pitch/4
    blind = exit_mode == "blind"
    kernel_length = length+phase_offset-half_width if blind else length+phase_offset+half_width
    coefficient = entry/pitch+1/4-half_width/pitch if blind else entry/pitch+1/4+half_width/pitch
    height_binding = deepcopy(bindings[0])
    height_binding["expression"] = f"{names[0]} + {coefficient:.12g} * {names[1]}"
    return {"schema": "geomwright.metric_thread."+exit_mode+"_end.plan", "version": 1,
            "exit_mode": exit_mode, "requested_span_mm": [start[0], end[0]],
            "kernel_length_mm": kernel_length, "spiral_length_mm": kernel_length+entry,
            "last_cut_trace_mm": end[0],
            "terminal_section_projection_mm": [end[0]-2*half_width, end[0]] if blind else [end[0], end[0]+2*half_width],
            "partial_terminal_projection_width_mm": 2*half_width,
            "conservative_profile_projection_end_mm": end[0]-2*half_width if blind else end[0],
            "kernel_phase_offset_mm": phase_offset, "height_binding": height_binding,
            "entry_condition": "requires_free_face_or_root_core_clearance",
            "native_end_section_audit_required": True, "verified": False,
            "functional_thread_length_verified": False, "controlled_runout": False}


def _plan_metric_thread_blind_end(params: dict) -> dict:
    """Compatibility entry point; preserve the existing blind plan byte shape."""
    return _plan_metric_thread_end(params, "blind")


def _metric_thread_carrier_guard(plan: dict, target: str, params: dict, *, end_plan=None, blind_end_plan=None) -> dict:
    """Preflight for the supported complete exposed terminal metric carrier.

    Consume an existing validated chain plan and normalized family parameters.
    Never invoke the legacy source builder or silently resize incoming stock.
    Native carrier selection, actual material preservation and ownership are
    audited separately. An explicit blind-end plan separates the requested cut
    from the physical carrier; omission retains the complete exposed-carrier gate.
    """
    tolerance = 1e-6  # geometric comparison only, not machining clearance
    if blind_end_plan is not None:
        if end_plan is not None:
            raise ValueError("Supply only one metric end plan")
        end_plan = blind_end_plan
    mode = end_plan.get("exit_mode") if end_plan is not None else None
    if plan.get("schema") != "geomwright.construction_chain.plan" or plan.get("version") != 1:
        raise ValueError("Thread carrier guard requires a validated construction chain plan")
    steps = plan.get("steps") or []
    matches = [step for step in steps if step["id"] == target]
    if len(matches) != 1:
        raise ValueError("Thread carrier requires one explicit constructor target")
    if any(step["module"] not in ("stepped_shaft", "external_conical_step") or
           step["material"] not in ("create", "add") or step["basis"] != "own"
           for step in steps):
        raise ValueError("Initial thread carrier scope excludes prior cuts and non-rotational stock")
    carrier = matches[0]
    section = carrier["section"]
    if (carrier["module"] != "stepped_shaft" or carrier["placement"]["direction"] != 1 or
            section["axis"] != "global_x" or section["phase_degrees"] != 0 or
            section["material_role"] != "stock" or len(section["segments"]) != 1):
        raise ValueError("Thread carrier must be one complete +X cylindrical constructor section")
    segment = section["segments"][0]
    start, end = section["start_mm"], section["end_mm"]
    radius = segment["start_radius_mm"]
    if (end <= start or abs(segment["end_radius_mm"]-radius) > tolerance or
            abs(segment["axial_min"]-start) > tolerance or abs(segment["axial_max"]-end) > tolerance):
        raise ValueError("Thread carrier interval and cylindrical segment disagree")
    if (params.get("thread_profile_family") != "metric_v60" or params.get("internal") or
            params.get("carrier_shape") != "cylindrical" or params.get("crest_round_pass")):
        raise ValueError("Initial thread carrier scope is external cylindrical metric, without secondary cuts")
    pitch, length = float(params["pitch"]), float(params["length"])
    depth = float(params["thread_depth"])+float(params.get("clearance") or 0)
    values = (start, end, radius, pitch, length, depth, float(params["carrier_diameter"]), float(params["diameter"]))
    if not all(math.isfinite(v) for v in values) or not 0 < depth < radius or pitch <= 0 or not 2 <= length/pitch <= 64:
        raise ValueError("Thread carrier dimensions require a finite root core and 2..64 turns")
    working_end = end
    if end_plan is not None:
        if end_plan != _plan_metric_thread_end(params, mode):
            raise ValueError("Carrier projection differs from normalized profile")
        working_end = start+length
        if mode == "blind" and working_end >= end-tolerance:
            raise ValueError("Blind carrier requires a positive smooth tail before its end")
        if mode == "through" and abs(working_end-end) > tolerance:
            raise ValueError("Through exit must end at the actual carrier face")
    if (abs(length-(working_end-start)) > tolerance or
            any(abs(float(a)-b) > tolerance for a, b in zip(params["start_origin"], (start, 0, 0))) or
            any(abs(float(a)-b) > tolerance for a, b in zip(params["end_origin"], (working_end, 0, 0))) or
            len(params["start_origin"]) != 3 or len(params["end_origin"]) != 3 or
            not all(math.isfinite(float(v)) for v in (*params["start_origin"], *params["end_origin"]))):
        raise ValueError("Thread must occupy the complete selected carrier span on global X")
    if abs(float(params["carrier_diameter"])-2*radius) > tolerance or abs(float(params["diameter"])-2*radius) > tolerance:
        raise ValueError("Thread nominal/carrier diameter does not match selected stock; no implicit resizing")
    root_radius = radius-depth
    protected = []
    stock = []
    for step in steps:
        other = step["section"]
        if other["axis"] != "global_x" or other["phase_degrees"] != 0 or other["material_role"] != "stock":
            raise ValueError("Thread protection requires rotational stock on the same global axis")
        stock.extend(other["segments"])
        for s in other["segments"]:
            if (not all(math.isfinite(float(s[key])) for key in
                        ("axial_min", "axial_max", "start_radius_mm", "end_radius_mm")) or
                    s["axial_max"] <= s["axial_min"] or min(s["start_radius_mm"], s["end_radius_mm"]) <= 0):
                raise ValueError("Protected stock dimensions are invalid")
            if step["id"] == target:
                continue
            if end_plan is not None and s["axial_min"] >= end-tolerance:
                if mode == "through" and max(s["start_radius_mm"], s["end_radius_mm"]) >= root_radius-tolerance:
                    raise ValueError("Through exit stock must stay strictly inside the root core")
                continue
            if s["axial_max"] > start+tolerance:
                raise ValueError("Thread carrier must be at the exposed +X stock end")
            if max(s["start_radius_mm"], s["end_radius_mm"]) >= root_radius-tolerance:
                raise ValueError("Protected stock must stay strictly inside the thread root core; tangency is unsupported")
        if step["id"] != target:
            protected.append({"step_id": step["id"], "segments": deepcopy(other["segments"])})
    result = {"target_step_id": target, "working_span_mm": [start, working_end],
            "carrier_radius_mm": radius, "root_radius_mm": root_radius,
            "protected_stock": protected, "expected_blank_volume_cm3": _volume(stock),
            "comparison_tolerance_mm": tolerance, "protection_basis": "all_other_stock_inside_root_core",
            "scope": "complete_exposed_external_metric_cylinder_positive_x",
             "native_carrier_verified": False, "material_preservation_verified": False}
    if end_plan is not None:
        result.update(scope=mode+"_external_metric_cylinder_positive_x",
                      protection_basis="rear_root_core_and_unchanged_exit_stock",
                      carrier_span_mm=[start, end], stock_envelope_segments=deepcopy(stock),
                      end_plan=deepcopy(end_plan))
        if mode == "through":
            result["root_tangent_radius_mm"] = float(params["profile_points"][1][1])
    return result


def plan_construction_chain(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Construction chain must be an object")
    _bounded(raw)
    chain = ConstructionChain.model_validate(raw)
    recipe = chain.model_dump(by_alias=True, exclude_none=True)
    _bounded(recipe)
    if any(step.module == "straight_spline" and step.basis == "input" for step in chain.steps):
        return _plan_terminal_input_spline(chain, recipe)
    if any(step.module in _THREAD_MODULES for step in chain.steps):
        return _plan_terminal_metric_thread(chain, recipe)
    planned, by_id, stock, removed = [], {}, [], []
    total = 0.0
    for index, step in enumerate(chain.steps):
        # Prefixes are case-sensitive in JSON but may not be in native variables.
        if step.id.upper() in {key.upper() for key in by_id}:
            raise ValueError("Step IDs must be unique, including case")
        ref = step.placement.reference
        if ref and ref.step not in by_id:
            raise ValueError("Placement reference must select an earlier step")
        if index and not ref:
            raise ValueError("Every subsequent step requires an earlier placement reference")
        origin = step.placement.offset_mm
        if ref:
            origin += by_id[ref.step]["section"][ref.anchor + "_mm"]
        direction = step.placement.direction
        gear = step.module == "gear_spur"
        spline = step.module == "straight_spline"
        foundation = gear or spline
        polygon = step.module == "external_polygonal_step"
        flat = step.module == "external_flat_step"
        holes = step.module == "bolt_circle_holes"
        constructor = step.module in ("stepped_shaft", "external_conical_step", "gear_spur", "straight_spline", "external_polygonal_step", "external_flat_step")
        if foundation and (index != 0 or ref or origin != 0 or direction != 1):
            raise ValueError("Gear/spline foundation requires initial own/create at standard placement origin 0, direction +1")
        if constructor:
            if step.basis != "own" or step.material != ("create" if index == 0 else "add") or step.target:
                raise ValueError("Constructors require own/create first, then own/add without target")
            if index and not ref:
                raise ValueError("Additions require an earlier placement reference")
        elif index == 0 or step.basis != "input" or step.material != "remove" or step.target not in by_id:
            raise ValueError("Cuts require input/remove and an explicit earlier target")
        parameters = step.parameters.model_dump(exclude_none=True)
        label, namespace = _LABELS[step.module] + " [" + step.id + "]", "CH_" + step.id.upper()
        gear_plan = None
        if gear:
            gear_plan = _gear_plan(parameters, namespace, label)
            p = gear_plan["geometry"]
        elif spline:
            gear_plan = build_straight_spline_plan(parameters, name=label)
            gear_plan["parameter_prefix"] = namespace
            p = gear_plan["geometry"]
        elif step.module == "stepped_shaft":
            preview = shaft_plan(parameters, name=label)["preview"]
        elif step.module == "external_conical_step":
            preview = cone_plan(parameters, name=label)["preview"]
        elif polygon:
            polygon_data = polygon_plan({**parameters, "axial_direction": "backward" if direction == 1 else "forward"}, name=label)
            preview = polygon_data["preview"]
        elif flat:
            flat_data = flat_plan({**parameters, "axial_direction": "backward" if direction == 1 else "forward"}, name=label)
            preview = flat_data["preview"]
        else:
            preview = preview_part_scenario(step.module, {**parameters, "name": label, "parameter_prefix": namespace,
                **({"axial_direction": "forward"} if holes else {})})
        if not foundation:
            p = preview["params"]
        segments, inner = [], []
        cursor = origin
        if gear:
            # Semantic start/end follow the native solid, not the YOZ sketch origin.
            origin, cursor = -p["face_width"], 0.0
            core_radius = min(p["root_radius"], p["outside_radius"] - p["tip_chamfer_depth_mm"])
            segments = [_segment(origin, cursor, core_radius, core_radius)]
        elif spline:
            origin, cursor = -p["length_mm"], 0.0
            chamfer = p["chamfer_mm"] if parameters["include_tip_chamfer"] else 0
            if not 0 <= chamfer < min(p["length_mm"]/2, p["outer_radius_mm"]-p["root_radius_mm"]):
                raise ValueError("Spline-chain tip chamfers must not meet or enter the solid root core")
            core_radius = min(p["root_radius_mm"], p["outer_radius_mm"]-chamfer)
            segments = [_segment(origin, cursor, core_radius, core_radius)]
        elif step.module in ("stepped_shaft", "internal_cylindrical_step"):
            for item in p["steps"]:
                end = cursor + direction*item["length"]
                segments.append(_segment(cursor, end, item["diameter"]/2, item["diameter"]/2))
                cursor = end
        elif step.module == "external_conical_step":
            cursor += direction*p["length"]
            segments = [_segment(origin, cursor, p["start_diameter"]/2, p["end_diameter"]/2)]
        elif polygon or flat:
            cursor += direction*p["length"]
            core = p["diameter"]/2-p["flat_depth"] if flat else p["polygon_radius"]*math.cos(math.pi/p["side_count"])
            segments = [_segment(origin, cursor, core, core)]
        elif holes:
            cursor += direction*p["depth"]
            r, pitch = p["hole_diameter"]/2, p["bolt_circle_diameter"]/2
            if pitch*2*math.sin(math.pi/p["count"]) <= 2*r:
                raise ValueError("Bolt-circle holes intersect or touch each other")
            segments = [_segment(origin, cursor, pitch+r, pitch+r)]
            inner = [_segment(origin, cursor, pitch-r, pitch-r)]
        else:
            cursor += direction*p["depth"]
            segments = [_segment(origin, cursor, p["outer_diameter"]/2, p["bottom_outer_diameter"]/2)]
            inner = [_segment(origin, cursor, p["inner_diameter"]/2, p["bottom_inner_diameter"]/2)]
        lo, hi = sorted((origin, cursor))
        if not all(math.isfinite(v) for v in (origin, cursor, lo, hi)) or hi <= lo:
            raise ValueError("Chain dimensions must remain finite with a positive span")
        section = {"axis": "global_x", "phase_degrees": 0, "axial_interval_mm": [lo, hi],
            "start_mm": origin, "end_mm": cursor, "shape": step.module, "segments": segments,
            "material_role": "stock" if constructor else "removed"}
        if inner:
            section["inner_segments"] = inner
        if gear:
            section.update(carrier_role="solid_root_core", root_radius_mm=p["root_radius"],
                           bounding_radius_mm=p["outside_radius"])
        if spline:
            section.update(carrier_role="solid_root_core", root_radius_mm=p["root_radius_mm"],
                           bounding_radius_mm=p["outer_radius_mm"])
        if polygon:
            vertices = [[v, u] for u, v in preview["interface"]["anchors"]["profile_vertices"]]
            section.update(carrier_role="inscribed_core", polygon_vertices_yz_mm=vertices,
                bounding_radius_mm=p["polygon_radius"])
        if flat:
            section.update(carrier_role="inscribed_core", bounding_radius_mm=p["diameter"]/2,
                flat_levels_y_mm=flat_data["expected_flat_levels_y_mm"],
                transverse_bounds_yz_mm=[flat_data["expected_bounds_mm"][i] for i in (1, 2, 4, 5)])
        if holes:
            section["hole_centers_yz_mm"] = [[pitch*math.cos(math.radians(p["start_angle_degrees"])+2*math.pi*j/p["count"]),
                pitch*math.sin(math.radians(p["start_angle_degrees"])+2*math.pi*j/p["count"])] for j in range(p["count"])]
            section["hole_radius_mm"] = r
        if constructor:
            if stock:
                stock_lo = min(s["axial_min"] for s in stock)
                stock_hi = max(s["axial_max"] for s in stock)
                if planned[0]["module"] in ("gear_spur", "straight_spline") and (
                        step.module != "stepped_shaft" or direction != 1 or origin != stock_hi):
                    raise ValueError("Gear/spline-chain additions require stepped_shaft sections at the exposed +X end")
                if planned[0]["module"] == "straight_spline" and stock_hi == 0 and max(
                        max(s["start_radius_mm"], s["end_radius_mm"]) for s in segments) > planned[0]["section"]["segments"][0]["end_radius_mm"]:
                    raise ValueError("Spline joining section must fit within the solid root core")
                if not (hi == stock_lo or lo == stock_hi):
                    raise ValueError("Disconnected or overlapping addition; attach at exposed stock end")
                # Joining onto an already hollow/processed end needs a native contact audit.
                if any(r["axial_min"] <= origin <= r["axial_max"] for r in removed):
                    raise ValueError("Addition at a previously cut face is unsupported")
            stock.extend(segments)
        else:
            carrier = by_id[step.target]["section"]
            if carrier["material_role"] != "stock":
                raise ValueError("Cut target must be a material constructor, not a cutter")
            _inside_carrier(segments, carrier)
            if inner and not holes and origin not in carrier["axial_interval_mm"]:
                raise ValueError("Face groove must start on a selected carrier end")
            regions = _removed_regions(segments, inner)
            for prior in removed:
                for outer in regions:
                    if not _overlaps(prior, outer):
                        continue
                    a, b = max(prior["axial_min"], outer["axial_min"]), min(prior["axial_max"], outer["axial_max"])
                    if not (all(_inner_radius(outer, x) > _radius(prior, x) for x in (a, b)) or
                            all(_inner_radius(prior, x) > _radius(outer, x) for x in (a, b))):
                        raise ValueError("Cut intersects prior bore or groove")
            removed.extend(regions)
        delta = (p["count"]*math.pi*r*r*p["depth"]/1000 if holes else flat_data["expected_volume_cm3"] if flat else polygon_data["expected_volume_cm3"] if polygon else
                 gear_plan["verification"]["expected_volume_mm3"] / 1000 if foundation
                 else _volume(segments) - _volume(inner))
        if not constructor:
            delta = -delta
        total += delta
        if not math.isfinite(total) or total <= 0 or not math.isfinite(delta):
            raise ValueError("Chain expected volume must remain finite and positive")
        item = {"id": step.id, "module": step.module, "namespace": namespace,
            "material": step.material, "basis": step.basis, "target": step.target,
            "placement": {"origin_mm": 0.0 if foundation else origin, "direction": direction},
            "section": section,
            "expected_delta_cm3": delta, "expected_total_volume_cm3": total,
            "verification": {"require_fully_defined": True, "single_solid": True,
                              "geometry_readback_required": True, "verified": False}}
        if foundation:
            item["family_plan" if spline else "gear_plan"] = gear_plan
            entities = next(op["params"]["entities"] for op in gear_plan["workflow"]["params"]["operations"]
                            if op["id"] == "tooth_space_sketch")
            signature = hashlib.sha256(json.dumps(entities, sort_keys=True, ensure_ascii=True,
                allow_nan=False, separators=(",", ":")).encode("ascii")).hexdigest()
            item["verification"].update(require_fully_defined=False,
                family_audit_required=True, family_verification=deepcopy(gear_plan["verification"]),
                profile_entities_sha256=signature, preserve_tooth_zone=True,
                volume_reference="audited_native_foundation_plus_analytic_deltas")
        else:
            item["preview"] = _adapt_preview(preview, namespace, label, origin, direction, transverse=polygon or flat or holes)
            if holes:
                hp = item["preview"]
                hp["params"]["placement"] = {"origin": [origin, 0], "effective_origin": [origin, 0]}
                hp["params"]["axial_direction"] = "forward" if direction == 1 else "backward"
                hp["base_hole_preview"] = _adapt_preview(hp["base_hole_preview"], namespace, label+" base hole", 0, direction)
                for operation in hp["operations"]:
                    for variable in operation.get("variables", []):
                        if variable["name"] == namespace+"_A1":
                            variable.update(expression="360 / "+namespace+"_N1", kind="derived_pattern_angle_step")
        planned.append(item)
        by_id[step.id] = item
    _check_persistence_budget(recipe, planned)
    plan = {"schema": "geomwright.construction_chain.plan", "version": 1,
            "recipe": recipe, "steps": planned, "expected_total_volume_cm3": total,
            "expected_body_count": 1, "verification": {"verified": False, "save_reopen_required": True}}
    if planned[0]["module"] in ("gear_spur", "straight_spline"):
        radius = max(step["section"].get("bounding_radius_mm", max(
            max(s["start_radius_mm"], s["end_radius_mm"]) for s in step["section"]["segments"]))
            for step in planned if step["material"] != "remove")
        plan["expected_bounds_mm"] = [min(s["axial_min"] for s in stock), -radius, -radius,
                                      max(s["axial_max"] for s in stock), radius, radius]
        plan["verification"]["bounds_kind"] = "conservative_radial_envelope"
        plan["verification"].update(foundation_step_id=planned[0]["id"],
            volume_reference="audited_native_foundation_plus_analytic_deltas",
            family_audit_before_additions=True, preserve_tooth_zone_after_each_step=True)
    elif any(step["module"] in ("external_polygonal_step", "external_flat_step") for step in planned):
        footprints = []
        for step in planned:
            if step["material"] == "remove":
                continue
            section = step["section"]
            vertices = section.get("polygon_vertices_yz_mm")
            if "transverse_bounds_yz_mm" in section:
                y0, z0, y1, z1 = section["transverse_bounds_yz_mm"]
                vertices = [[y0, z0], [y1, z1]]
            radius = max(max(s["start_radius_mm"], s["end_radius_mm"]) for s in section["segments"])
            footprints.extend(vertices if vertices else [[-radius, -radius], [radius, radius]])
        plan["expected_bounds_mm"] = [min(s["axial_min"] for s in stock),
            min(v[0] for v in footprints), min(v[1] for v in footprints),
            max(s["axial_max"] for s in stock), max(v[0] for v in footprints), max(v[1] for v in footprints)]
        plan["verification"]["bounds_kind"] = "exact_section_footprints"
    if _ascii_size(plan) > MAX_PLAN_BYTES:
        raise ValueError("Construction chain plan exceeds 256000 ASCII bytes")
    return plan


def _plan_terminal_input_spline(chain: ConstructionChain, recipe: dict) -> dict:
    """One bounded terminal cut; keep the uncut analytic prefix canonical."""
    from .connections.cad import _plan_straight_spline_input_shaft, _plan_straight_spline_input_hub
    step = chain.steps[-1]
    if (len(chain.steps) < 2 or step.module != "straight_spline" or step.basis != "input" or
            any(s.module == "straight_spline" and s.basis == "input" for s in chain.steps[:-1])):
        raise ValueError("Input spline must be the sole terminal step; no subsequent operations")
    prefix = plan_construction_chain({**recipe, "steps": recipe["steps"][:-1]})
    if step.id.upper() in {s["id"].upper() for s in prefix["steps"]}:
        raise ValueError("Step IDs must be unique, including case")
    placement = step.placement
    if (placement.direction != 1 or not placement.reference or
            placement.reference.step != step.target or placement.reference.anchor != "start"):
        raise ValueError("Input spline placement must reference target start on +X")
    target = next((s for s in prefix["steps"] if s["id"] == step.target), None)
    if target is None or len(target["section"]["segments"]) != 1:
        raise ValueError("Input spline requires one explicit cylindrical target")
    origin = target["section"]["start_mm"]+placement.offset_mm
    hub = step.parameters.body == "hub"
    parameters = step.parameters.model_dump(exclude_none=True)
    exit_mode = parameters.pop("exit_mode",None)
    if hub:
        if prefix["steps"][0]["module"] != "stepped_shaft" or placement.offset_mm != 0:
            raise ValueError("Input hub placement must use through bore start on +X without offset")
        application = _plan_straight_spline_input_hub(parameters,
            carrier_outside_diameter_mm=2*prefix["steps"][0]["section"]["segments"][0]["start_radius_mm"],
            bore_diameter_mm=2*target["section"]["segments"][0]["start_radius_mm"],
            axial_start_mm=origin,name="Straight spline input ["+step.id+"]")
        # The outside diameter is inherited explicitly from immutable input stock,
        # never from the standalone family's default-wall heuristic.
        recipe["steps"][-1]["parameters"] = deepcopy(application["profile_request"])
        if exit_mode is not None:recipe["steps"][-1]["parameters"]["exit_mode"]=exit_mode
    else:
        application = _plan_straight_spline_input_shaft(parameters,
            carrier_diameter_mm=2*target["section"]["segments"][0]["start_radius_mm"],
            axial_start_mm=origin, name="Straight spline input ["+step.id+"]")
    guard = _straight_spline_input_carrier_guard(prefix, step.target, application,exit_mode=exit_mode or "through")
    lo, hi = guard["working_span_mm"]
    if not hub and not guard["carrier_span_mm"][0]+1e-5 < lo < hi < guard["carrier_span_mm"][1]-1e-5:
        raise ValueError("Input spline requires positive smooth margins at both carrier ends; open ends unsupported")
    item = {"id": step.id, "module": step.module, "namespace": "CH_"+step.id.upper(),
        "material": "remove", "basis": "input", "target": step.target,
        "placement": {"origin_mm": lo, "direction": 1},
        "section": {"axis": "global_x", "phase_degrees": 0, "axial_interval_mm": [lo, hi],
            "start_mm": lo, "end_mm": hi, "shape": "blind_input_spline_hub" if exit_mode=="blind" else "through_input_spline_hub" if hub else "bounded_input_spline", "material_role": "removed",
            "segments": [_segment(lo, hi, guard["carrier_radius_mm"], guard["carrier_radius_mm"])],
            "inner_segments": [_segment(lo, hi, guard["root_radius_mm"], guard["root_radius_mm"])]},
        "expected_delta_cm3": -guard["expected_removed_cm3"],
        "expected_total_volume_cm3": guard["expected_final_volume_cm3"],
        "verification": {"verified": False, "single_solid": True, "geometry_readback_required": True,
            "volume_reference": "exact_family_space_removal"},
        "spline_application": application, "spline_guard": guard}
    steps = prefix["steps"]+[item]
    _check_persistence_budget(recipe, steps)
    compact = [{k: v for k, v in s.items() if k not in
        ("preview", "gear_plan", "family_plan", "spline_application", "spline_guard")} for s in steps]
    if _ascii_size(recipe)+_ascii_size(compact)+12288 > MAX_RECIPE_BYTES:
        raise ValueError("Spline chain checkpoint persistence budget exceeds 24000 ASCII bytes")
    plan = {**prefix, "recipe": recipe, "steps": steps, "spline_prefix_plan": prefix,
        "expected_total_volume_cm3": guard["expected_final_volume_cm3"],
        "verification": {"verified": False, "save_reopen_required": True,
            "volume_reference": "exact_family_space_removal"}}
    if _ascii_size(plan) > MAX_PLAN_BYTES:
        raise ValueError("Construction chain plan exceeds 256000 ASCII bytes")
    return plan


def _plan_terminal_metric_thread(chain: ConstructionChain, recipe: dict) -> dict:
    """Keep the ordinary analytic prefix intact; thread volume is native-only."""
    if len(chain.steps) < 2 or any(s.module in _THREAD_MODULES for s in chain.steps[:-1]):
        raise ValueError("Metric thread must be the sole terminal step; no subsequent operations")
    step = chain.steps[-1]
    if step.module not in _THREAD_MODULES:
        raise ValueError("Metric thread must be terminal")
    prefix_recipe = {**recipe, "steps": recipe["steps"][:-1]}
    prefix = plan_construction_chain(prefix_recipe)
    if step.id.upper() in {s["id"].upper() for s in prefix["steps"]}:
        raise ValueError("Step IDs must be unique, including case")
    placement = step.placement
    if (placement.direction != 1 or placement.offset_mm != 0 or not placement.reference or
            placement.reference.step != step.target or placement.reference.anchor != "start"):
        raise ValueError("Thread placement must select target start on +X with zero offset")
    target = next((s for s in prefix["steps"] if s["id"] == step.target), None)
    if target is None:
        raise ValueError("Thread requires an explicit earlier carrier target")
    parameters = step.parameters.model_dump(exclude_none=True)
    exit_mode = parameters.pop("exit_mode", None)
    parameters.pop("entry_mode", None)
    parameters.pop("method_version", None)
    label, namespace = "Physical thread ["+step.id+"]", "CH_"+step.id.upper()
    origin = target["section"]["start_mm"]
    internal = step.module == "internal_helical_thread"
    if internal:
        if (len(prefix["steps"]) != 2 or prefix["steps"][0]["module"] != "stepped_shaft" or
                prefix["steps"][1]["id"] != step.target or target["module"] != "internal_cylindrical_step" or
                any(len(s["section"]["segments"]) != 1 for s in prefix["steps"])):
            raise ValueError("Internal thread target must be the explicit complete cylindrical bore")
        from .parametric import _prepare_internal_metric_through_preview
        bore = 2*target["section"]["segments"][0]["start_radius_mm"]
        family_length = target["section"]["end_mm"]-origin if exit_mode == "blind" else parameters["length"]
        family = _prepare_internal_metric_through_preview(preview_part_scenario("internal_helical_thread", {**parameters, "length": family_length,
            "source_scenario": "internal_cylindrical_step", "source_params": {
                "steps": [{"length": family_length, "diameter": bore}],
                "source_scenario": "stepped_shaft", "source_params": {"steps": [{
                    "length": family_length, "diameter": prefix["recipe"]["steps"][0]["parameters"]["steps"][0]["diameter"]}]}}}))
    else:
        family = preview_part_scenario("external_helical_thread", {**parameters,
            "source_scenario": "stepped_shaft", "source_params": {"steps": [{"length": parameters["length"], "diameter": parameters["diameter"]}]}})
    preview = _adapt_preview(family, namespace, label, origin, 1)
    end_plan = _plan_metric_thread_end(preview["params"], exit_mode) if exit_mode and not internal else None
    if internal and exit_mode == "blind":
        from .parametric import _plan_internal_metric_end
        end_plan = _plan_internal_metric_end(preview["params"], exit_mode="blind", thread_length=parameters["length"],
            bore_span=target["section"]["axial_interval_mm"], stock_span=prefix["steps"][0]["section"]["axial_interval_mm"])
        preview["params"].update(length=parameters["length"], end_origin=[end_plan["last_cut_trace_mm"],0,0])
        for variable in preview["params"]["profile_variables"]:
            if variable["name"] == preview["params"]["public_length_variable_name"]:
                variable["value"] = parameters["length"]
    if end_plan is not None:
        preview["params"]["spiral_length"] = end_plan["spiral_length_mm"]
        preview["params"]["operation_variable_bindings"] = [
            deepcopy(end_plan["height_binding"]) if binding.get("role") == "spiral_height" else binding
            for binding in preview["params"]["operation_variable_bindings"]]
    guard = (_internal_metric_carrier_guard(prefix, step.target, preview["params"], end_plan=end_plan) if internal else
             _metric_thread_carrier_guard(prefix, step.target, preview["params"], end_plan=end_plan))
    lo, hi = guard["working_span_mm"]
    radius, root = ((guard["major_radius_mm"], guard["bore_radius_mm"]) if internal else
                    (guard["carrier_radius_mm"], guard["root_radius_mm"]))
    item = {"id": step.id, "module": step.module, "namespace": namespace,
        "material": "remove", "basis": "input", "target": step.target,
        "placement": {"origin_mm": origin, "direction": 1},
        "section": {"axis": "global_x", "phase_degrees": 0, "axial_interval_mm": [lo, hi],
            "start_mm": lo, "end_mm": hi, "shape": step.module, "material_role": "removed",
            "segments": [_segment(lo, hi, radius, radius)], "inner_segments": [_segment(lo, hi, root, root)]},
        "expected_delta_cm3": None, "expected_total_volume_cm3": None,
        "verification": {"require_fully_defined": True, "single_solid": True,
            "geometry_readback_required": True, "verified": False,
            "volume_reference": "audited_native_terminal_thread"}, "preview": preview, "thread_guard": guard}
    steps = prefix["steps"]+[item]
    _check_persistence_budget(recipe, steps)
    # The checkpoint includes IDs, native protected faces and measured volume.
    # Reserve extra headroom; the bridge enforces the actual envelope bound.
    if _ascii_size(recipe)+_ascii_size([{k: v for k, v in s.items() if k not in ("preview", "gear_plan", "family_plan")} for s in steps])+8192 > MAX_RECIPE_BYTES:
        raise ValueError("Thread chain persistence budget exceeds 24000 ASCII bytes")
    plan = {**prefix, "recipe": recipe, "steps": steps, "thread_prefix_plan": prefix,
            "expected_total_volume_cm3": None,
            "verification": {"verified": False, "save_reopen_required": True,
                             "volume_reference": "audited_native_terminal_thread"}}
    if _ascii_size(plan) > MAX_PLAN_BYTES:
        raise ValueError("Construction chain plan exceeds 256000 ASCII bytes")
    return plan


def run_construction_chain(adapter, action, chain=None, document_id=None, confirm=False, visible=True) -> dict:
    """One write call; continuation appends, rebuild preserves its source. No retry."""
    if action not in ("plan", "create", "inspect", "rebuild", "continue"):
        raise ValueError("Unsupported construction chain action")
    if action in ("create", "rebuild", "continue") and confirm is not True:
        raise ValueError("Construction chain writes require confirm=True")
    expected_recipe = None
    if action in ("inspect", "rebuild", "continue"):
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("Exact document_id is required")
        if action == "continue":
            if not isinstance(chain, dict):
                raise ValueError("Continue requires chain containing only new steps")
            append_name = chain.get("name")
            _bounded(chain)
            additions = ConstructionChain.model_validate(chain).model_dump(by_alias=True, exclude_none=True)
        elif chain is not None:
            raise ValueError("Inspect/rebuild reads the exact document recipe; chain override is unsupported")
        result = adapter.runner.call("inspect_construction_chain", {"document_id": document_id})
        if result.get("recipe") and (result["recipe"]["steps"][-1]["module"] in _THREAD_MODULES or
                (result["recipe"]["steps"][-1]["module"] == "straight_spline" and result["recipe"]["steps"][-1]["basis"] == "input")):
            audited_plan = plan_construction_chain(result["recipe"])
            result = adapter.runner.call("inspect_construction_chain", {
                "document_id": document_id, "plan": audited_plan, "verify_geometry": True})
            if result.get("verification", {}).get("verified") is not True:
                raise ValueError("Saved terminal chain failed fresh geometry/ownership audit")
        if action == "inspect":
            return result
        if not result.get("ok") or result.get("recipe_error") or not result.get("recipe"):
            raise ValueError("No recoverable construction chain recipe in selected document")
        chain = deepcopy(result["recipe"])
        if action == "continue":
            output = (result.get("document") or {}).get("path")
            checksum = result.get("recipe_checksum")
            if (result.get("runtime_version") != 1 or not isinstance(checksum, str) or
                    not re.fullmatch(r"[0-9a-f]{64}", checksum)):
                raise ValueError("Continue requires a checksummed version-1 construction-chain envelope; standalone models are unsupported")
            if not isinstance(output, str) or not ntpath.isabs(output) or ntpath.splitext(output)[1].lower() != ".m3d":
                raise ValueError("Continue requires the selected chain's existing saved .m3d path")
            expected_recipe = deepcopy(chain)
            chain["steps"] += additions["steps"]
            if append_name is not None:
                chain["name"] = append_name
    elif document_id is not None:
        raise ValueError("Plan/create do not continue an existing document")
    plan = plan_construction_chain(chain)
    if action == "plan":
        return plan
    if action == "continue":
        if plan["steps"][0]["module"] in ("gear_spur", "straight_spline"):
            expectations = result.get("expectations") or []
            audit = (expectations[0].get("verification", {}).get("foundation_audit")
                     if expectations else None)
            if (not audit or audit.get("verified") is not True or
                    not isinstance(audit.get("volume_cm3"), (int, float)) or
                    isinstance(audit["volume_cm3"], bool) or
                    not math.isfinite(audit["volume_cm3"]) or audit["volume_cm3"] <= 0):
                raise ValueError("Continue requires the saved tooth-family chain's original native foundation audit")
            plan["steps"][0]["verification"]["foundation_audit"] = deepcopy(audit)
            # Keep the analytic plan fields for the native semantic guard. The
            # continuation expectation uses the original audited actual base;
            # native independently restores/checks it from the saved envelope.
            plan["verification"]["expected_total_volume_cm3"] = audit["volume_cm3"] + math.fsum(
                step["expected_delta_cm3"] for step in plan["steps"][1:])
            if _ascii_size(plan) > MAX_PLAN_BYTES:
                raise ValueError("Construction chain plan exceeds 256000 ASCII bytes")
        payload = {"document_id": document_id, "plan": plan, "expected_recipe": expected_recipe,
                   "expected_recipe_checksum": checksum, "output_path": output, "confirm_write": True}
        native_action = "continue_construction_chain"
    else:
        path = adapter._export_dir() / f"construction-chain-{uuid4().hex}.m3d"
        output = adapter._normalize_target_path_for_kompas(str(path))
        payload = {"plan": plan, "visible": visible, "output_path": output}
        if plan["steps"][-1]["module"] in _THREAD_MODULES or "spline_prefix_plan" in plan:
            payload["confirm_write"] = True
        native_action = "create_construction_chain"
    try:
        result = adapter.runner.call(native_action, payload)
        if not result.get("ok"):
            error = RuntimeError(str(result.get("error") or "Construction chain write failed")[:2000])
            error.partial_result = result.get("partial_result") or result
            raise error
        return result
    except Exception as exc:
        error = RuntimeError(str(exc)[:2000])
        error.partial_result = {"stage": "construction_chain_continue" if action == "continue" else "construction_chain_create", "output_path": output,
            "executed": None,
            "source_document_id": document_id, "verified": False, "rollback_performed": False,
            **(getattr(exc, "partial_result", None) or {})}
        raise error from exc
