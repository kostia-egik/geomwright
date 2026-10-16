"""Common-interface adapter for the existing diaphragm spring workflow."""
from __future__ import annotations
from .cad_session_policy import lifecycle_verification

import math
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cad_extension_bindings import inspect_extension_module
from .parametric import preview_part_scenario


class DiaphragmSpringParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    tip_variant: Literal["no_bend", "single_bend", "s_bend"]
    outer_diameter: float = Field(gt=0)
    thickness: float = Field(gt=0, description="Normal thickness, mm.")
    cone_height: float = Field(gt=0)
    cone_direction: Literal["up", "down"] = "up"
    inner_diameter: float | None = Field(default=None, gt=0)
    body_inner_diameter: float | None = Field(default=None, gt=0)
    free_height: float | None = Field(default=None, gt=0)
    tip_length: float | None = Field(default=None, gt=0)
    tip_angle_degrees: float | None = Field(default=None, gt=0, le=90)
    tip_bend_inner_radius: float | None = Field(default=None, gt=0)
    second_tip_bend_inner_radius: float | None = Field(default=None, gt=0)
    first_tip_inner_diameter: float | None = Field(default=None, gt=0)
    first_tip_height: float | None = Field(default=None, gt=0)
    slot_end_radius: float = Field(gt=0)
    slot_start_width: float = Field(gt=0)
    slot_end_width: float = Field(gt=0)
    slot_fillet_radius: float = Field(gt=0)
    entry_clearance: float = Field(ge=0)
    relief_variant: Literal["circle", "oval"]
    relief_radius: float = Field(gt=0)
    relief_straight_length: float | None = Field(default=None, gt=0)
    slot_count: int = Field(ge=2)

    @model_validator(mode="after")
    def validate_variants(self):
        bent = {"body_inner_diameter", "free_height", "tip_length", "tip_angle_degrees", "tip_bend_inner_radius"}
        second = {"second_tip_bend_inner_radius", "first_tip_inner_diameter", "first_tip_height"}
        required = {"inner_diameter"} if self.tip_variant == "no_bend" else {"body_inner_diameter", "tip_bend_inner_radius"}
        forbidden = bent | second if self.tip_variant == "no_bend" else second if self.tip_variant == "single_bend" else {"tip_length", "tip_angle_degrees"}
        if self.tip_variant == "single_bend":
            required.add("tip_angle_degrees")
            if (self.free_height is None) == (self.tip_length is None):
                raise ValueError("single_bend requires exactly one of free_height and tip_length")
            # Its final inner diameter is derived by the legacy generator.
            forbidden.add("inner_diameter")
        elif self.tip_variant == "s_bend":
            required |= second | {"inner_diameter", "free_height"}
        for field in required:
            if getattr(self, field) is None:
                raise ValueError(f"{self.tip_variant} requires {field}")
        for field in forbidden:
            if getattr(self, field) is not None:
                raise ValueError(f"{field} is inapplicable to {self.tip_variant}")
        if self.relief_variant == "oval" and self.relief_straight_length is None:
            raise ValueError("oval relief requires relief_straight_length")
        if self.relief_variant == "circle" and self.relief_straight_length is not None:
            raise ValueError("relief_straight_length is inapplicable to circle relief")
        if 2 * self.slot_fillet_radius >= self.slot_end_width:
            raise ValueError("2 * slot_fillet_radius must be smaller than slot_end_width")
        if self.relief_radius <= self.slot_end_width / 2:
            raise ValueError("relief_radius must exceed half slot_end_width")
        return self


_BASE_FIELDS = {"tip_variant", "outer_diameter", "inner_diameter", "body_inner_diameter", "thickness",
                "cone_height", "cone_direction", "free_height", "tip_length", "tip_angle_degrees",
                "tip_bend_inner_radius", "second_tip_bend_inner_radius", "first_tip_inner_diameter", "first_tip_height"}


def diaphragm_plan(parameters: dict, *, name: str) -> dict:
    base = {key: value for key, value in parameters.items() if key in _BASE_FIELDS}
    base.update(name="Diaphragm spring", parameter_prefix="DIA", parameterization_level="constrained")
    base_preview = preview_part_scenario("diaphragm_spring", base)
    inner_radius = base_preview["params"]["inner_diameter"] / 2
    if not inner_radius < parameters["slot_end_radius"] < parameters["outer_diameter"] / 2:
        raise ValueError("slot_end_radius must lie between final inner and outer radii")
    if parameters["entry_clearance"] + parameters["slot_start_width"] / 2 >= inner_radius:
        raise ValueError("Slot entry clearance/width leaves no valid start radius")

    def op(id, scenario, **params):
        return {"id": id, "scenario": scenario, "params": params}

    anchors = {"plane": "tangent.plane", "start_point": "start.point", "end_point": "end.point"}
    operations = [
        op("base", "diaphragm_spring", **base),
        op("tangent", "tangent_plane", face="base.conical_face", base_plane="XOY", name="Diaphragm tangent plane"),
        op("references", "cut_reference_points_sketch", sketch="base.sketch", end_radius=parameters["slot_end_radius"],
           auto_entry_clearance=True, slot_start_width=parameters["slot_start_width"],
           entry_clearance=parameters["entry_clearance"], name="Cut radius references"),
        op("start", "projection_point", surface="tangent.plane", source="references.start_point", axis="base.axis", name="Cut start projection"),
        op("end", "projection_point", surface="tangent.plane", source="references.end_point", axis="base.axis", name="Cut end projection"),
        op("profile", "diaphragm_cut_profile_sketch", **anchors, start_width=parameters["slot_start_width"],
           end_width=parameters["slot_end_width"], fillet_radius=parameters["slot_fillet_radius"],
           terminal_setback=parameters["relief_radius"], name="Cut profile sketch"),
        op("relief", "diaphragm_terminal_relief_sketch", **anchors, variant=parameters["relief_variant"],
           radius=parameters["relief_radius"], slot_end_width=parameters["slot_end_width"],
           straight_length=parameters.get("relief_straight_length", 0), name="Terminal relief sketch"),
        op("slot_cut", "cut_extrusion", sketch="profile.sketch", end_condition="through_all", direction="both", name="Diaphragm slot cut"),
        op("relief_cut", "cut_extrusion", sketch="relief.sketch", end_condition="through_all", direction="both", name="Diaphragm relief cut"),
        op("pattern", "circular_pattern", sources=["slot_cut.feature", "relief_cut.feature"], axis="base.axis",
           count=parameters["slot_count"], span_angle=360, name="Diaphragm cuts"),
    ]
    preview = preview_part_scenario("workflow", {"name": name, "operations": operations})
    return {"module_id": "diaphragm_spring", "preview": preview, "base_preview": base_preview,
            "recipe": {"schema": "geomwright.diaphragm.recipe", "version": 1, "parameters": parameters,
                       "name": name, "profile_name": "Diaphragm spring profile", "sweep_name": "Diaphragm spring body"},
            "verification": {"single_solid": True, "positive_volume": True, "two_pattern_sources": True,
                             "pattern_material_removal": True, "save_reopen_required": True}}


def diaphragm_plan_data(plan: dict) -> dict:
    p = plan["recipe"]["parameters"]
    x = [point[0] for point in plan["base_preview"]["params"]["profile_points"]]
    return {"name": plan["recipe"]["name"], "summary": p,
            "geometry": {"axis": "global_x", "final_inner_diameter": plan["base_preview"]["params"]["inner_diameter"],
                         "operation_count": len(plan["preview"]["params"]["operations"]),
                         "axial_interval_mm": [min(x), max(x)]},
            "creation_policy": "saved_unique_export_then_open",
            "warnings": ["Existing engineering diaphragm workflow; no load/strength or standard conformity certification.",
                         "Create-only integration, without a new Studio block or in-place editing. Per-sketch constraint states are returned after reopen; full definition of every saved sketch is not certified. Recipe recognition is not a geometry audit."]}


def diaphragm_preview(parameters: dict) -> dict:
    return {"success": True, "summary": diaphragm_plan_data(diaphragm_plan(parameters, name="Geomwright diaphragm spring"))}


def inspect_diaphragm_module(adapter, document_id: str) -> dict:
    return inspect_extension_module(adapter, document_id, family="diaphragm", parameter_model=DiaphragmSpringParameters,
        planner=diaphragm_plan, required={"tip_variant", "outer_diameter", "thickness", "cone_height", "cone_direction",
            "slot_end_radius", "slot_start_width", "slot_end_width", "slot_fillet_radius", "entry_clearance",
            "relief_variant", "relief_radius", "slot_count"})


def create_diaphragm_module(adapter, plan: dict, visible: bool) -> dict:
    path = adapter._export_dir() / f"diaphragm-module-{uuid4().hex}.m3d"
    document = None
    checkpoint = {}
    params = dict(plan["preview"]["params"], output_path=adapter._normalize_target_path_for_kompas(str(path)), close_after_save=True)
    try:
        created = adapter.runner.call("create_part_from_scenario", {"scenario": "workflow", "params": params,
            "preview": plan["preview"], "visible": visible, "diaphragm_module_recipe": plan["recipe"]},
            progress_callback=checkpoint.update)
        if not created.get("ok") or not created.get("saved"):
            raise RuntimeError("Diaphragm workflow did not confirm saved creation")
        pattern = next(step for step in created["steps"] if step.get("scenario") == "circular_pattern")
        count = plan["recipe"]["parameters"]["slot_count"]
        if pattern["pattern_report"]["initial_object_count"] != 2 or pattern["count"] != count:
            raise RuntimeError("Diaphragm pattern source/count mismatch")
        expected = pattern["source_volume_removed"] * (count - 1)
        # Never let a relative tolerance conceal one missing repeated group.
        tolerance = min(max(1e-6, expected * .01), pattern["source_volume_removed"] * .25)
        if expected <= 0 or abs(pattern["additional_volume_removed"] - expected) > tolerance:
            raise RuntimeError("Diaphragm pattern did not remove the expected repeated material")
        document = adapter.open_document(str(path), visible=visible, read_only=False)["document"]
        docid = document.get("runtime_id") or document["id"]
        block = inspect_diaphragm_module(adapter, docid)
        if not block.get("recreatable") or block["profile"] != plan["recipe"]["parameters"]:
            raise RuntimeError("Diaphragm recipe/owned roots did not survive reopen")
        native = adapter.runner.call("inspect_diaphragm_module", {"document_id": docid, "creation_body_readback": True})
        body = native["body"]
        before = pattern["body_after"]["volume"]
        if not math.isfinite(body["volume"]) or body["volume"] <= 0 or abs(body["volume"] - before) > max(1e-7, before * 1e-5):
            raise RuntimeError("Diaphragm volume changed during save/reopen")
        bodies = adapter.list_model_bodies(docid, limit=2)
        if bodies["pagination"]["total"] != 1 or not bodies["items"][0]["solid"]:
            raise RuntimeError("Diaphragm must contain one solid body")
        bounds = bodies["items"][0]["bounds_mm"]
        radius = plan["recipe"]["parameters"]["outer_diameter"] / 2
        if max(abs(bounds[i] - target) for i, target in ((1,-radius),(2,-radius),(4,radius),(5,radius))) > 1e-5:
            raise RuntimeError("Diaphragm outside diameter differs from input")
        interval = diaphragm_plan_data(plan)["geometry"]["axial_interval_mm"]
        if abs(bounds[0] - interval[0]) > 1e-5 or abs(bounds[3] - interval[1]) > 1e-5:
            raise RuntimeError("Diaphragm axial bounds differ from the planned profile")
        body["bounds_mm"] = bounds
        return {"ok": True, "executed": True, "saved": True, "closed": False, "document": document,
                "body": body, "block": block, "verification": {"ok": True, "single_solid": True,
                "positive_volume": True, "pattern_material_removal": True,
                "native_pattern_reopened": lifecycle_verification(adapter)["recipe_reopened"],
                "axial_bounds_verified": True, **lifecycle_verification(adapter)},
                "diagnostics": {"base_sketch_state": native["diaphragm"]["sketch_states"][plan["recipe"]["profile_name"]],
                                "native_workflow": native["diaphragm"]}}
    except Exception as exc:
        message = str(checkpoint.get("error") or exc).split(" | steps=", 1)[0]
        marker = "RuntimeError: create_part_from_scenario failed at "
        if marker in message:
            message = "Diaphragm creation failed at " + message.rsplit(marker, 1)[1].split(" | steps=", 1)[0]
        error = RuntimeError(message[:2000])
        error.partial_result = {"document": document, "output_path": str(path), "verified": False,
                                "stage": "diaphragm_creation_or_reopen", "rollback_performed": False,
                                "checkpoint": {key: checkpoint.get(key) for key in ("stage", "target", "elapsed_ms")}}
        raise error from exc
