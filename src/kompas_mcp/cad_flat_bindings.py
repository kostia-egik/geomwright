"""Create-only adapter for the legacy cylinder with one or two opposing flats."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cad_shaft_bindings import create_legacy_body_module, inspect_rotational_module
from .parametric import preview_part_scenario


class ExternalFlatParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    diameter: float = Field(gt=0)
    length: float = Field(gt=0)
    flat_depth: float = Field(gt=0)
    flats_count: int = Field(default=1, ge=1, le=2)
    axial_direction: Literal["forward", "backward"] = "forward"

    @model_validator(mode="after")
    def valid_depth(self):
        if not self.flat_depth < self.diameter / 2:
            raise ValueError("flat_depth must be strictly less than diameter / 2")
        return self


def flat_plan(parameters: dict, *, name: str) -> dict:
    parameters = ExternalFlatParameters.model_validate(parameters).model_dump()
    radius = parameters["diameter"] / 2
    depth = parameters["flat_depth"]
    offset = radius - depth
    chord_half = math.sqrt(depth * (2 * radius - depth))
    if not (0 < offset < radius and math.isfinite(chord_half) and chord_half > 0):
        raise ValueError("Flat profile is not representable at these dimensions")
    # Retained strip area avoids cancellation from subtracting two deep caps.
    half_strip_area = offset * chord_half + radius * radius * math.asin(offset / radius)
    area = math.pi * radius * radius / 2 + half_strip_area if parameters["flats_count"] == 1 else 2 * half_strip_area
    volume = area * parameters["length"] / 1000
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("Flat prism must have finite positive area and volume")
    preview = preview_part_scenario("external_flat_step", {**parameters, "name": name, "parameter_prefix": "FLAT"})
    # Legacy seeds use shortened lines; analytical endpoints describe the solved body.
    if not math.isclose(preview["params"]["chord_half"], chord_half, rel_tol=1e-9, abs_tol=0):
        raise ValueError("Legacy flat-profile chord loses precision; native construction not certified")
    preview["params"]["sketch_name"] = "External flat profile"
    side = 1 if parameters["axial_direction"] == "forward" else 2
    bindings = [{"target": "extrusion", "parameter_note": f"Distance {side}",
        "parameter_note_aliases": [f"Distance {side}", f"Расстояние {side}"],
        "expression": "FLAT_L1", "role": "extrusion_length"}]
    preview["params"]["operation_variable_bindings"] = bindings
    for operation in preview["operations"]:
        if operation["operation"] == "boss_extrusion":
            operation["operation_variable_bindings"] = bindings
    end_x = -parameters["length"] if parameters["axial_direction"] == "forward" else parameters["length"]
    # Verified flat-builder frame: positive local flat offset maps to negative Y.
    upper_y = radius if parameters["flats_count"] == 1 else offset
    levels = [-offset] if parameters["flats_count"] == 1 else [-offset, offset]
    chord_vertices = [[x, y, z] for x in (0, end_x) for y in levels for z in (-chord_half, chord_half)]
    return {"module_id": "external_flat_step", "preview": preview,
        "expected_volume_cm3": volume, "expected_area_mm2": area,
        "expected_bounds_mm": [min(0, end_x), -offset, -radius, max(0, end_x), upper_y, radius],
        "expected_chord_vertices_mm": chord_vertices,
        "expected_cylinder_radius_mm": radius, "expected_flat_levels_y_mm": levels,
        "recipe": {"schema": "geomwright.external_flat_step.recipe", "version": 1, "name": name,
            "parameters": parameters, "profile_name": "External flat profile", "body_name": "External flat body"},
        "verification": {"single_solid": True, "analytic_volume": True, "trimmed_cylinder_and_flat_faces": True,
            "native_chord_vertices": True, "profile_fully_defined": True, "save_reopen_required": True}}


def flat_plan_data(plan: dict) -> dict:
    return {"name": plan["recipe"]["name"], "summary": plan["recipe"]["parameters"],
        "geometry": {"axis": "global_x", "bounds_mm": plan["expected_bounds_mm"],
            "volume_cm3": plan["expected_volume_cm3"], "profile_area_mm2": plan["expected_area_mm2"]},
        "creation_policy": "saved_unique_export_then_open",
        "warnings": ["Standalone cylinder with one or two opposite flats only; no foreign-body application, internal cut, finishing or new Studio block.",
            "FLAT_D1/FLAT_L1/FLAT_F1 drive diameter, length and depth; flats count and direction require recreation. No public in-place editing.",
            "Inspect recognizes the creation recipe, not current geometry or manual driver changes.",
            "Interactive common MCP create/inspect/explicit reopen has representative evidence for one-flat forward and two-flat backward D30/L25/F4; hidden isolation and every numeric boundary are not certified."]}


def flat_preview(parameters: dict) -> dict:
    return {"success": True, "summary": flat_plan_data(flat_plan(parameters, name="Geomwright external flat"))}


def inspect_flat_module(adapter, document_id: str) -> dict:
    return inspect_rotational_module(adapter, document_id, family="external_flat_step",
        parameter_model=ExternalFlatParameters, planner=flat_plan,
        required={"diameter", "length", "flat_depth", "flats_count", "axial_direction"})


def verify_flat_geometry(plan: dict, bounds: list, faces: list, volume: float) -> None:
    tolerance = 1e-5  # Native readback tolerance in mm, not a manufacturing tolerance.
    if len(bounds) != 6 or not all(math.isfinite(v) for v in bounds) or max(abs(a-b) for a, b in zip(bounds, plan["expected_bounds_mm"])) > tolerance:
        raise RuntimeError("Flat bounds/orientation differ from plan")
    expected = plan["expected_volume_cm3"]
    if not math.isfinite(volume) or volume <= 0 or abs(volume-expected) > max(1e-7, expected*1e-5):
        raise RuntimeError("Flat volume differs from analytical prism")
    count = plan["recipe"]["parameters"]["flats_count"]
    cylinders = [face for face in faces if face["surface_type"] == "cylinder"]
    planes = [face for face in faces if face["surface_type"] == "plane"]
    if len(cylinders) != count or len(planes) != count + 2 or len(faces) != 2*count + 2:
        raise RuntimeError("Flat trimmed face count/types differ")
    vertices = []
    for face in faces:
        points = face["points_mm"]
        if not points or not all(len(p) == 3 and all(math.isfinite(v) for v in p) for p in points):
            raise RuntimeError("Flat boundary vertices unavailable or non-finite")
        for point in points:
            if not any(max(abs(a-b) for a, b in zip(point, p)) < 1e-7 for p in vertices):
                vertices.append(point)
    if len(vertices) != len(plan["expected_chord_vertices_mm"]):
        raise RuntimeError("Flat native vertex count differs")
    for expected_point in plan["expected_chord_vertices_mm"]:
        match = next((p for p in vertices if max(abs(a-b) for a, b in zip(p, expected_point)) < tolerance), None)
        if match is None:
            raise RuntimeError("Flat chord endpoint differs")
        vertices.remove(match)
    radius = plan["expected_cylinder_radius_mm"]
    low, high = bounds[0], bounds[3]
    for face in cylinders:
        r = face["radius_mm"]
        points = face["points_mm"]
        if not math.isfinite(r) or abs(r-radius) > tolerance or any(abs(math.hypot(p[1], p[2])-radius) > tolerance for p in points):
            raise RuntimeError("Flat cylinder radius differs")
        if abs(min(p[0] for p in points)-low) > tolerance or abs(max(p[0] for p in points)-high) > tolerance:
            raise RuntimeError("Flat cylinder axial interval differs")
    # Distinguish flat planes from the two trimmed end caps by boundary coordinates.
    remaining = list(planes)
    for level in plan["expected_flat_levels_y_mm"]:
        match = next((face for face in remaining if all(abs(p[1]-level) < tolerance for p in face["points_mm"])
            and abs(min(p[0] for p in face["points_mm"])-low) < tolerance
            and abs(max(p[0] for p in face["points_mm"])-high) < tolerance), None)
        if match is None:
            raise RuntimeError("Flat planar level/trimmed interval differs")
        remaining.remove(match)
    for end in (low, high):
        match = next((face for face in remaining if all(abs(p[0]-end) < tolerance for p in face["points_mm"])), None)
        if match is None:
            raise RuntimeError("Flat end plane differs")
        remaining.remove(match)


def create_flat_module(adapter, plan: dict, visible: bool) -> dict:
    return create_legacy_body_module(adapter, plan, visible, inspector=inspect_flat_module, verifier=verify_flat_geometry)
