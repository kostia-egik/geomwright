"""Typed adapter for the existing standalone external-cone constructor."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cad_shaft_bindings import create_rotational_module, inspect_rotational_module
from .parametric import preview_part_scenario


class ExternalConeParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    definition_mode: Literal["diameters_length","diameters_angle","diameters_conicity",
                             "one_diameter_length_angle","one_diameter_length_conicity"]
    start_diameter: float | None = Field(default=None,gt=0)
    end_diameter: float | None = Field(default=None,gt=0)
    length: float | None = Field(default=None,gt=0)
    cone_angle_degrees: float | None = Field(default=None,gt=0,lt=90,description="Half-angle between cone generator and axis.")
    conicity: float | None = Field(default=None,gt=0,description="Absolute diameter difference / axial length.")
    slope_direction: Literal["inward","outward"] | None = None

    @model_validator(mode="after")
    def mode_inputs(self):
        required = {
            "diameters_length":{"start_diameter","end_diameter","length"},
            "diameters_angle":{"start_diameter","end_diameter","cone_angle_degrees"},
            "diameters_conicity":{"start_diameter","end_diameter","conicity"},
            "one_diameter_length_angle":{"length","cone_angle_degrees","slope_direction"},
            "one_diameter_length_conicity":{"length","conicity","slope_direction"},
        }[self.definition_mode]
        diameter_fields = {"start_diameter","end_diameter"}
        if self.definition_mode.startswith("one_diameter"):
            present = {key for key in diameter_fields if getattr(self,key) is not None}
            if len(present) != 1:
                raise ValueError("One-diameter mode requires exactly one end diameter")
            required |= present
        else:
            # Two diameters already define the direction: do not accept a second source of truth.
            if self.slope_direction is not None:
                raise ValueError("slope_direction is derived in two-diameter modes")
        for field in {"start_diameter","end_diameter","length","cone_angle_degrees","conicity","slope_direction"}:
            if field in required and getattr(self,field) is None:
                raise ValueError(f"{self.definition_mode} requires {field}")
            if field not in required and getattr(self,field) is not None:
                raise ValueError(f"{field} is derived or inapplicable to {self.definition_mode}")
        return self


def cone_plan(parameters: dict, *, name: str) -> dict:
    preview = preview_part_scenario("external_conical_step",{**parameters,"name":name,
        "parameter_prefix":"CONE"})
    preview["params"].update(sketch_name="External cone profile",fix_sketch_placement=True,require_fully_defined=True)
    for operation in preview["operations"]:
        if operation["operation"] == "add_dimensions":
            operation["dimensions"][0] = {"kind":"line_length","target":"axis","expression":"CONE_L1",
                                          "driving":True,"label":"axial cone length"}
    p = preview["params"]
    start, end = p["start_diameter"], p["end_diameter"]
    volume = math.pi*p["length"]*(start*start+start*end+end*end)/12000
    if not math.isfinite(volume) or volume <= 0 or not all(math.isfinite(p[k]) for k in ("length","start_diameter","end_diameter")):
        raise ValueError("Cone must have finite positive dimensions and volume")
    return {"module_id":"external_conical_step","preview":preview,"expected_volume_cm3":volume,
        "recipe":{"schema":"geomwright.external_conical_step.recipe","version":1,"name":name,
                  "parameters":parameters,"profile_name":"External cone profile","body_name":"External cone body"},
        "verification":{"single_solid":True,"analytic_volume":True,"end_diameters":True,"axial_bounds":True,"save_reopen_required":True}}


def cone_plan_data(plan: dict) -> dict:
    p = plan["preview"]["params"]
    return {"name":plan["recipe"]["name"],"summary":{key:p[key] for key in
        ("definition_mode","start_diameter","end_diameter","length","cone_angle_degrees","conicity","slope_direction")},
        "geometry":{"axis":"global_x","axial_interval_mm":[0,p["length"]],"volume_cm3":plan["expected_volume_cm3"]},
        "creation_policy":"saved_unique_export_then_open",
        "warnings":["Standalone full rotational body, no internal cone, threads, external-body application or new Studio block.",
                    "Input definition mode is retained for recreation. Inspect is recipe recognition, not a geometry/driving audit or in-place editing."]}


def cone_preview(parameters: dict) -> dict:
    return {"success":True,"summary":cone_plan_data(cone_plan(parameters,name="Geomwright external cone"))}


def inspect_cone_module(adapter, document_id: str) -> dict:
    return inspect_rotational_module(adapter,document_id,family="external_conical_step",parameter_model=ExternalConeParameters,
                                     planner=cone_plan,required={"definition_mode"})


def verify_cone_geometry(plan: dict, bounds: list, faces: list, volume: float) -> None:
    p = plan["preview"]["params"]
    length, start, end = p["length"],p["start_diameter"]/2,p["end_diameter"]/2
    r = max(start,end)
    if len(bounds) != 6 or not all(math.isfinite(v) for v in bounds) or max(abs(a-b) for a,b in zip(bounds,[0,-r,-r,length,r,r]))>1e-5:
        raise RuntimeError("Cone bounds differ from resolved input")
    expected = plan["expected_volume_cm3"]
    if not math.isfinite(volume) or volume <= 0 or abs(volume-expected)>max(1e-7,expected*1e-5):
        raise RuntimeError("Cone volume differs from analytic frustum")
    cones = [face for face in faces if face["surface_type"] == "cone"]
    if len(cones) != 1:
        raise RuntimeError("Cone must have exactly one native conical surface")
    face = cones[0]
    if not all(math.isfinite(face[key]) for key in ("axial_min","axial_max","start_radius_mm","end_radius_mm")):
        raise RuntimeError("Cone native dimensions are incomplete or non-finite")
    if any(abs(face[key]-expected)>1e-5 for key,expected in
           (("axial_min",0),("axial_max",length),("start_radius_mm",start),("end_radius_mm",end))):
        raise RuntimeError("Cone trimmed end radii or axial span differ")


def create_cone_module(adapter, plan: dict, visible: bool) -> dict:
    return create_rotational_module(adapter,plan,visible,inspector=inspect_cone_module,verifier=verify_cone_geometry)
