"""Create-only adapter for the legacy regular-polygon prism constructor."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .cad_shaft_bindings import create_legacy_body_module, inspect_rotational_module
from .parametric import preview_part_scenario


class ExternalPolygonParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    diameter: float = Field(gt=0)
    length: float = Field(gt=0)
    side_count: int = Field(ge=3, le=64, description="Bounded profile/readback size; not a standards limit.")
    diameter_mode: Literal["inscribed_circle", "circumscribed_circle"] = "inscribed_circle"
    rotation_angle_degrees: float = Field(default=0, description=(
        "Initial profile orientation. POLY_A1 drives the native angular branch selected "
        "at creation; crossing that branch requires recreation."))
    axial_direction: Literal["forward", "backward"] = "forward"


def polygon_plan(parameters: dict, *, name: str) -> dict:
    preview = preview_part_scenario("external_polygonal_step", {**parameters, "name": name, "parameter_prefix": "POLY"})
    preview["params"]["sketch_name"] = "External polygon profile"
    preview["params"]["fix_sketch_placement"] = True
    p = preview["params"]
    side = 1 if p["axial_direction"] == "forward" else 2
    p["operation_variable_bindings"] = [{"target": "extrusion", "parameter_note": f"Distance {side}",
        "parameter_note_aliases": [f"Distance {side}", f"Расстояние {side}"],
        "expression": "POLY_L1", "role": "extrusion_length"}]
    angle = (90 - p["rotation_angle_degrees"]) % 360
    # Select the native angular branch; rotation remains a real CAD driver.
    offset = angle + p["rotation_angle_degrees"]
    for operation in preview["operations"]:
        if operation["operation"] == "add_variables":
            operation["variables"].append({"name": "POLY_A1", "value": p["rotation_angle_degrees"],
                "note": "Polygon profile rotation; angular branch selected at creation",
                "external": True, "kind": "driving_orientation"})
            operation["variable_count"] = len(operation["variables"])
            preview["summary"]["planned_variable_count"] = operation["variable_count"]
        elif operation["operation"] == "apply_constraints":
            # Equal chords on a concentric vertex circle define regularity.
            # One tangent sets the incircle radius; n-1 more repeat that equation.
            operation["constraints"] = [row for row in operation["constraints"]
                if row.get("name") != "first_edge_horizontal" and (
                    p["diameter_mode"] != "inscribed_circle" or row["kind"] != "tangent"
                    or row["target"] == "profile_line_1")]
            operation["constraint_count"] = len(operation["constraints"])
            preview["summary"]["planned_constraint_count"] = operation["constraint_count"]
        elif operation["operation"] == "add_dimensions":
            operation["dimensions"].append({"kind": "angle_between_lines", "target": "profile_line_1",
                "partner": "circle_radius_line", "value": angle,
                "expression": f"{offset:g} - POLY_A1", "driving": True})
            operation["dimension_count"] = len(operation["dimensions"])
            preview["summary"]["planned_dimension_count"] = operation["dimension_count"]
    vertices = preview["interface"]["anchors"]["profile_vertices"]
    end_x = -p["length"] if p["axial_direction"] == "forward" else p["length"]
    points = [[x, v, u] for x in (0, end_x) for u, v in vertices]
    volume = p["side_count"] * p["polygon_radius"] * p["polygon_radius"] * math.sin(2 * math.pi / p["side_count"]) * p["length"] / 2000
    if not math.isfinite(volume) or volume <= 0 or not all(math.isfinite(v) for point in points for v in point):
        raise ValueError("Polygon must have finite positive dimensions and volume")
    return {"module_id": "external_polygonal_step", "preview": preview, "expected_volume_cm3": volume,
        "expected_vertices_mm": points,
        "recipe": {"schema": "geomwright.external_polygonal_step.recipe", "version": 1, "name": name,
            "parameters": parameters, "profile_name": "External polygon profile", "body_name": "External polygon body"},
        "verification": {"single_solid": True, "analytic_volume": True, "native_vertices": True,
            "profile_fully_defined": True, "save_reopen_required": True}}


def polygon_plan_data(plan: dict) -> dict:
    points = plan["expected_vertices_mm"]
    return {"name": plan["recipe"]["name"], "summary": plan["recipe"]["parameters"],
        "geometry": {"axis": "global_x", "bounds_mm": [min(p[i] for p in points) for i in range(3)]
            + [max(p[i] for p in points) for i in range(3)], "volume_cm3": plan["expected_volume_cm3"]},
        "creation_policy": "saved_unique_export_then_open",
        "warnings": ["Regular-polygon solid prism only; no internal cut, external-body application, finishing or new Studio block.",
            "POLY_D1/POLY_L1/POLY_A1 drive diameter, length and orientation. Side count, diameter interpretation and direction require recreation; the orientation driver's angular branch is selected at creation.",
            "Recipe recognition restores inputs for a new build, not a fresh geometry or in-place driving audit."]}


def polygon_preview(parameters: dict) -> dict:
    return {"success": True, "summary": polygon_plan_data(polygon_plan(parameters, name="Geomwright external polygon"))}


def inspect_polygon_module(adapter, document_id: str) -> dict:
    return inspect_rotational_module(adapter, document_id, family="external_polygonal_step",
        parameter_model=ExternalPolygonParameters, planner=polygon_plan,
        required={"diameter", "length", "side_count", "diameter_mode", "rotation_angle_degrees", "axial_direction"})


def verify_polygon_geometry(plan: dict, bounds: list, faces: list, volume: float) -> None:
    expected_bounds = polygon_plan_data(plan)["geometry"]["bounds_mm"]
    if len(bounds) != 6 or not all(math.isfinite(v) for v in bounds) or max(abs(a-b) for a, b in zip(bounds, expected_bounds)) > 1e-5:
        raise RuntimeError("Polygon bounds/orientation differ from plan")
    expected_volume = plan["expected_volume_cm3"]
    if not math.isfinite(volume) or volume <= 0 or abs(volume-expected_volume) > max(1e-7, expected_volume*1e-5):
        raise RuntimeError("Polygon native volume differs from analytical prism")
    if len(faces) != 1 or faces[0]["surface_type"] != "prism_vertices":
        raise RuntimeError("Polygon vertex readback unavailable")
    remaining = list(faces[0]["points_mm"])
    if len(remaining) != len(plan["expected_vertices_mm"]) or not all(len(p) == 3 and all(math.isfinite(v) for v in p) for p in remaining):
        raise RuntimeError("Polygon native vertex count/coordinates differ")
    for expected in plan["expected_vertices_mm"]:
        match = next((p for p in remaining if max(abs(a-b) for a, b in zip(p, expected)) < 1e-5), None)
        if match is None:
            raise RuntimeError("Polygon native vertex position differs")
        remaining.remove(match)


def create_polygon_module(adapter, plan: dict, visible: bool) -> dict:
    return create_legacy_body_module(adapter, plan, visible, inspector=inspect_polygon_module, verifier=verify_polygon_geometry)
