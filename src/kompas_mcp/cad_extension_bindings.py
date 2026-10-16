"""Typed extension-spring adapter over the existing legacy hook generator."""
from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .parametric import preview_part_scenario


Hook = Literal["machine_hooks", "v_hooks", "u_hooks", "open_loop_hooks", "center_loop_hooks", "extended_center_loop_hooks", "self_wrapping_hooks", "bent_coil_left_spike"]


class ExtensionSpringParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    wire_diameter: float = Field(gt=0)
    outer_diameter: float = Field(gt=0)
    turns: float = Field(gt=0)
    gap: float = Field(default=.01, gt=0, description="Requested axial pitch increment; must be at least minimum_gap. Not a certified surface clearance.")
    minimum_gap: float = Field(default=.01, gt=0)
    hook_type: Hook = "machine_hooks"
    left_hook_type: Hook | None = Field(default=None, description="Overrides hook_type on the left end only.")
    right_hook_type: Hook | None = Field(default=None, description="Overrides hook_type on the right end only.")
    turn_direction: Literal["right", "left"] = "right"
    hook_clearance: float | None = Field(default=None, ge=0)
    transition_fillet_radius: float | None = Field(default=None, gt=0)
    v_hook_height: float | None = Field(default=None, gt=0)
    v_hook_fillet_radius: float | None = Field(default=None, gt=0)
    v_hook_end_distance: float | None = Field(default=None, gt=0)
    u_hook_height: float | None = Field(default=None, gt=0)
    u_hook_end_offset: float | None = Field(default=None, gt=0)
    open_loop_height: float | None = Field(default=None, gt=0)
    open_loop_offset: float | None = Field(default=None, gt=0)
    center_loop_height: float | None = Field(default=None, gt=0)
    center_loop_radius: float | None = Field(default=None, gt=0)
    center_loop_offset: float | None = Field(default=None, gt=0)
    extended_center_loop_height: float | None = Field(default=None, gt=0)
    extended_center_loop_fillet_radius: float | None = Field(default=None, gt=0)
    bent_coil_turns: float | None = Field(default=None, gt=0)
    bent_coil_angle_degrees: float | None = Field(default=None, gt=0, le=180)
    self_wrapping_height: float | None = Field(default=None, gt=0)
    self_wrapping_width: float | None = Field(default=None, gt=0)
    self_wrapping_fillet_radius: float | None = Field(default=None, gt=0)
    self_wrapping_tail_length: float | None = Field(default=None, gt=0)


def extension_plan(parameters: dict, *, name: str) -> dict:
    if parameters["gap"] < parameters["minimum_gap"]:
        raise ValueError("gap must be at least minimum_gap; no silent increment is applied")
    hooks = {parameters.get("left_hook_type", parameters["hook_type"]),
             parameters.get("right_hook_type", parameters["hook_type"])}
    if "hook_clearance" in parameters and not hooks & {"machine_hooks", "u_hooks"}:
        raise ValueError("hook_clearance applies only to machine hooks and the default U-hook end offset")
    if "u_hooks" in hooks and "machine_hooks" not in hooks and {"hook_clearance", "u_hook_end_offset"}.issubset(parameters):
        raise ValueError("Specify hook_clearance or u_hook_end_offset, not both")
    for prefix, allowed in (("v_hook_", {"v_hooks"}), ("u_hook_", {"u_hooks"}),
                            ("open_loop_", {"open_loop_hooks"}),
                            ("center_loop_", {"center_loop_hooks", "extended_center_loop_hooks"}),
                            ("extended_center_loop_", {"extended_center_loop_hooks"}),
                            ("bent_coil_", {"bent_coil_left_spike"}),
                            ("self_wrapping_", {"self_wrapping_hooks"})):
        if not hooks & allowed and any(k.startswith(prefix) for k in parameters):
            raise ValueError(f"{prefix} dimensions do not apply to the selected ends")
    if "extended_center_loop_hooks" in hooks and "center_loop_hooks" not in hooks and "center_loop_height" in parameters and "extended_center_loop_height" in parameters:
        raise ValueError("Specify only extended_center_loop_height, not both height aliases")
    profile = {**parameters, "name": name}
    wrapping_variables = {"self_wrapping_height": "SH1", "self_wrapping_width": "SW1",
                          "self_wrapping_fillet_radius": "SFR1", "self_wrapping_tail_length": "HT1"}
    if "self_wrapping_hooks" in hooks:
        profile["variable_plan"] = [{"name": variable, "value": parameters[key], "external": True}
                                    for key, variable in wrapping_variables.items() if key in parameters]
    preview = preview_part_scenario("extension_spring", profile)
    params = preview["params"]
    if params.get("requires_side_specific_hook_builders"):
        raise ValueError("Legacy generator did not resolve the selected mixed-hook composition")
    params.update(name=name, profile_name="spring_wire_profile", sweep_name="spring_body")
    body = next(s for s in params["segment_plan"] if s["role"] == "body")
    recipe = {"schema": "geomwright.extension.recipe", "version": 1,
              "parameters": parameters, "name": name, "profile_name": params["profile_name"],
              "sweep_name": params["sweep_name"], "body_path_name": body["path_name"]}
    if len(json.dumps(recipe, ensure_ascii=True, allow_nan=False)) > 24000:
        raise ValueError("Extension recipe exceeds 24000 characters")
    return {"module_id": "extension_spring", "preview": preview, "recipe": recipe,
            "verification": {"single_solid": True, "positive_volume": True,
                             "saved_recipe": True, "native_coil_dimensions": True,
                             "save_reopen_required": True}}


def extension_plan_data(plan: dict) -> dict:
    p = plan["preview"]["params"]
    return {"name": plan["recipe"]["name"], "summary": {k: p[k] for k in
            ("wire_diameter", "outer_diameter", "turns", "gap", "pitch", "height", "hook_type", "left_hook_type", "right_hook_type", "mixed_hook_types", "turn_direction")},
            "geometry": {"axis": "global_x", "height_reference": "coil_only_not_hook_to_hook"},
            "creation_policy": "saved_unique_export_then_open",
            "warnings": ["Engineering geometry only; no load, initial-tension or strength certification.",
                         "Independent ends use the existing eight-family legacy composer; the historical bent_coil_left_spike identifier denotes final bent-ring geometry."]}


def extension_preview(parameters: dict) -> dict:
    return {"success": True, "summary": extension_plan_data(extension_plan(parameters, name="Geomwright extension spring"))}


def inspect_extension_module(adapter, document_id: str, *, family="extension",
                             parameter_model=ExtensionSpringParameters, planner=extension_plan, required=None) -> dict:
    result = adapter.runner.call(f"inspect_{family}_module", {"document_id": document_id})
    block = result.get("block") or {}
    if not result.get("recognized"):
        return {"module": None}
    recipe = block.get("recipe")
    parameters = None
    error = block.get("recipe_error")
    if recipe:
        try:
            raw = recipe["parameters"]
            required = required or {"wire_diameter", "outer_diameter", "turns", "gap", "minimum_gap", "hook_type", "turn_direction"}
            if not required.issubset(raw):
                raise ValueError("Incomplete saved extension inputs; no default substitution")
            parameters = parameter_model.model_validate(raw).model_dump(exclude_none=True)
            planner(parameters, name=recipe["name"])
        except (ValueError, KeyError, TypeError) as exc:
            error, parameters = str(exc)[:500], None
    return {**block, "module": family + "_spring", "profile": parameters, "verified": None,
            "editable": False, "recreatable": parameters is not None, "recipe_error": error,
            "status": "creation_recipe_recognized" if parameters else "partial_unverified"}


def verify_extension_readback(params: dict, bounds: list, readback: dict) -> None:
    coil = readback["coil"]
    expected = {"diameter": params["mean_diameter"], "pitch": params["pitch"], "height": params["height"],
                "wire_diameter": params["wire_diameter"]}
    for key, value in expected.items():
        if not math.isclose(coil[key], value, rel_tol=1e-8, abs_tol=1e-7):
            raise RuntimeError("Extension native coil dimension differs: " + key)
    if coil["turn_direction"] != (not params["left_hand"]):
        raise RuntimeError("Extension native coil hand differs")
    if bounds[0] > params["wire_diameter"] or bounds[3] < params["height"]-params["wire_diameter"]:
        raise RuntimeError("Extension body does not span the planned coil")


def create_extension_module(adapter, plan: dict, visible: bool) -> dict:
    from .cad_spring_bindings import create_spring_module
    return create_spring_module(adapter, plan, visible)
