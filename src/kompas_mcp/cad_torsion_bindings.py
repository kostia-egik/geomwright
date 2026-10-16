"""Shared contract for the existing engineering torsion-spring generator."""
from __future__ import annotations

from typing import Literal
import math

from pydantic import BaseModel, ConfigDict, Field

from .parametric import preview_part_scenario
from .cad_extension_bindings import inspect_extension_module


class TorsionSpringParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    wire_diameter: float = Field(gt=0)
    mean_diameter: float | None = Field(default=None, gt=0)
    outer_diameter: float | None = Field(default=None, gt=0)
    turns: float = Field(gt=0, description="Body turns before the free-angle contribution.")
    leg_length: float | None = Field(default=None, gt=0)
    left_leg_length: float | None = Field(default=None, gt=0)
    right_leg_length: float | None = Field(default=None, gt=0)
    end_type: Literal["tangent_legs", "radial_legs", "axial_transition_legs"] = "tangent_legs"
    turn_direction: Literal["right", "left"] = "right"
    gap: float = Field(default=.01, gt=0)
    minimum_gap: float = Field(default=.01, gt=0)
    free_angle_degrees: float = 0
    start_phase_degrees: float = 0
    transition_fillet_radius: float | None = Field(default=None, gt=0)


def torsion_plan(parameters: dict, *, name: str) -> dict:
    if len({"mean_diameter", "outer_diameter"} & parameters.keys()) != 1:
        raise ValueError("Specify exactly one of mean_diameter and outer_diameter")
    if "leg_length" in parameters:
        if {"left_leg_length", "right_leg_length"} & parameters.keys():
            raise ValueError("Specify leg_length or both per-end lengths, not both conventions")
    elif not {"left_leg_length", "right_leg_length"}.issubset(parameters):
        raise ValueError("Specify leg_length or both left_leg_length and right_leg_length")
    if parameters["gap"] < parameters["minimum_gap"]:
        raise ValueError("gap must be at least minimum_gap; no silent increment is applied")
    if parameters["end_type"] == "tangent_legs" and "transition_fillet_radius" in parameters:
        raise ValueError("transition_fillet_radius applies only to radial/axial transitions")
    preview = preview_part_scenario("torsion_spring", {**parameters, "name": name})
    p = preview["params"]
    p.update(name=name, profile_name="spring_wire_profile", sweep_name="spring_body")
    body = next(s for s in p["segment_plan"] if s["role"] == "body")
    recipe = {"schema": "geomwright.torsion.recipe", "version": 1, "parameters": parameters,
              "name": name, "profile_name": p["profile_name"], "sweep_name": p["sweep_name"],
              "body_path_name": body["path_name"]}
    recipe["leg_path_names"] = {s["role"]: s["path_name"] for s in p["segment_plan"] if s["path_type"] == "line_segment"}
    return {"module_id": "torsion_spring", "preview": preview, "recipe": recipe,
            "verification": {"single_solid": True, "positive_volume": True,
                             "native_coil_dimensions": True, "saved_recipe": True,
                             "save_reopen_required": True}}


def torsion_plan_data(plan: dict) -> dict:
    p = plan["preview"]["params"]
    return {"name": plan["recipe"]["name"], "summary": {k: p[k] for k in
            ("mean_diameter", "outer_diameter", "wire_diameter", "pitch", "height", "turns",
             "body_turns", "free_angle_degrees", "start_phase_degrees", "end_type", "turn_direction")},
            "geometry": {"axis": "global_x", "height_reference": "coil_only_not_leg_extents"},
            "creation_policy": "saved_unique_export_then_open",
            "warnings": ["Engineering geometry only; no torque, stiffness, strength or fatigue certification."]}


def torsion_preview(parameters: dict) -> dict:
    return {"success": True, "summary": torsion_plan_data(torsion_plan(parameters, name="Geomwright torsion spring"))}


def inspect_torsion_module(adapter, document_id: str) -> dict:
    return inspect_extension_module(adapter, document_id, family="torsion",
                                    parameter_model=TorsionSpringParameters, planner=torsion_plan,
                                    required={"wire_diameter", "turns", "gap", "minimum_gap", "end_type",
                                              "turn_direction", "free_angle_degrees", "start_phase_degrees"})


def create_torsion_module(adapter, plan: dict, visible: bool) -> dict:
    from .cad_spring_bindings import create_spring_module
    return create_spring_module(adapter, plan, visible)


def verify_torsion_legs(params: dict, readback: dict) -> None:
    for segment in params["segment_plan"]:
        if segment["path_type"] != "line_segment":
            continue
        points = readback["legs"][segment["role"]]
        if not points or len(points) != 2:
            raise RuntimeError("Native torsion leg endpoints are missing")
        expected = [segment["start_point"], segment["end_point"]]
        error = min(max(math.dist(a, b) for a, b in zip(points, expected)),
                    max(math.dist(a, b) for a, b in zip(points[::-1], expected)))
        if error > 1e-6:
            raise RuntimeError("Native torsion leg endpoints differ from the plan: " + segment["role"])
