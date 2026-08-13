from __future__ import annotations

import math
from typing import Any, Literal


FlatPulleyProfile = Literal["cylindrical", "crowned"]


def _positive(name: str, value: Any) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def preview_flat_belt_pulley(
    *,
    outer_diameter: float,
    face_width: float,
    profile: FlatPulleyProfile | None = None,
    crown_height: float = 0.0,
) -> dict[str, Any]:
    diameter = _positive("outer_diameter", outer_diameter)
    width = _positive("face_width", face_width)
    mode = str(profile or ("crowned" if float(crown_height) > 0.0 else "cylindrical")).strip().lower()
    if mode not in ("cylindrical", "crowned"):
        raise ValueError("profile must be 'cylindrical' or 'crowned'")
    crown = float(crown_height)
    if not math.isfinite(crown) or crown < 0.0:
        raise ValueError("crown_height must be a non-negative finite number")
    if mode == "cylindrical" and crown > 1e-9:
        raise ValueError("crown_height must be zero for a cylindrical profile")
    if mode == "crowned" and crown <= 0.0:
        raise ValueError("crown_height must be positive for a crowned profile")

    outer_radius = diameter / 2.0
    edge_radius = outer_radius - crown
    if edge_radius <= 0.0:
        raise ValueError("crown_height must leave a positive edge radius")
    if crown >= width / 2.0:
        raise ValueError("crown_height must be less than half the face width")

    entities: list[dict[str, Any]] = [
        {"kind": "line", "target": "axis_closure", "start": [0.0, 0.0], "end": [width, 0.0]},
        {"kind": "line", "target": "right_face", "start": [width, 0.0], "end": [width, edge_radius]},
    ]
    sampled_outer: list[list[float]]
    crown_radius = None
    crown_center = None
    if mode == "crowned":
        half_width = width / 2.0
        crown_radius = (half_width * half_width + crown * crown) / (2.0 * crown)
        crown_center = [half_width, outer_radius - crown_radius]
        right = [width, edge_radius]
        left = [0.0, edge_radius]
        entities.append(
            {
                "kind": "arc",
                "target": "crowned_surface",
                "center": crown_center,
                "radius": crown_radius,
                "start": right,
                "end": left,
                "direction": False,
            }
        )
        sampled_outer = []
        for index in range(25):
            x = width * index / 24.0
            y = crown_center[1] + math.sqrt(max(0.0, crown_radius * crown_radius - (x - half_width) ** 2))
            sampled_outer.append([x, y])
    else:
        entities.append(
            {"kind": "line", "target": "outer_surface", "start": [width, outer_radius], "end": [0.0, outer_radius]}
        )
        sampled_outer = [[0.0, outer_radius], [width, outer_radius]]
    entities.append(
        {"kind": "line", "target": "left_face", "start": [0.0, edge_radius], "end": [0.0, 0.0]}
    )

    closed_profile = [
        [0.0, 0.0],
        [width, 0.0],
        [width, edge_radius],
        *list(reversed(sampled_outer))[1:],
        [0.0, 0.0],
    ]
    volume_mm3 = math.pi * (
        sum(
            (sampled_outer[index][1] ** 2 + sampled_outer[index + 1][1] ** 2) / 2.0
            * (sampled_outer[index + 1][0] - sampled_outer[index][0])
            for index in range(len(sampled_outer) - 1)
        )
    )
    return {
        "success": True,
        "operation": "flat_belt_pulley",
        "inputs": {
            "outer_diameter": diameter,
            "face_width": width,
            "profile": mode,
            "crown_height": crown,
        },
        "derived": {
            "outer_diameter": diameter,
            "face_width": width,
            "outer_radius": outer_radius,
            "edge_diameter": edge_radius * 2.0,
            "crown_radius": crown_radius,
            "volume_mm3": volume_mm3,
        },
        "geometry": {
            "profile_entities": entities,
            "closed_profile": closed_profile,
            "outer_surface": sampled_outer,
            "crown_center": crown_center,
            "coordinate_system": {"x": "axial", "y": "radial"},
        },
        "warnings": [
            "The crown is an explicit circular-arc geometry, not a standards-derived default."
        ] if mode == "crowned" else [],
    }


def build_flat_belt_pulley_plan(preview: dict[str, Any], *, name: str) -> dict[str, Any]:
    if preview.get("operation") != "flat_belt_pulley" or not preview.get("success"):
        raise ValueError("A successful flat_belt_pulley preview is required")
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")
    inputs = dict(preview["inputs"])
    derived = dict(preview["derived"])
    geometry = dict(preview["geometry"])
    profile_label = "crowned" if inputs["profile"] == "crowned" else "cylindrical"
    feature_name = f"Flat-belt pulley {profile_label} rim - {requested_name}"
    sketch_name = f"Flat-belt pulley {profile_label} rim profile - {requested_name}"
    variables = [
        {"name": "PULLEY_D1", "value": inputs["outer_diameter"], "expression": None, "note": "Maximum pulley outer diameter"},
        {"name": "PULLEY_L1", "value": inputs["face_width"], "expression": None, "note": "Pulley face width"},
        {"name": "FP_OR", "value": derived["outer_radius"], "expression": "PULLEY_D1/2", "note": "Maximum functional surface radius"},
        {"name": "FP_CROWN", "value": inputs["crown_height"], "expression": None, "note": "Radial crown height"},
        {"name": "FP_PROFILE", "value": 2 if inputs["profile"] == "crowned" else 1, "expression": None, "note": "1 cylindrical, 2 crowned"},
    ]
    profile_entities = [dict(item) for item in geometry["profile_entities"]]
    constraints = [
        {"kind": "horizontal", "target": "axis_closure"},
        {"kind": "vertical", "target": "right_face"},
        {"kind": "vertical", "target": "left_face"},
    ]
    pre_constraints = [
        {"kind": "fixed_point", "target": "axis", "index": 0},
        {"kind": "fixed_point", "target": "axis", "index": 1},
        {"kind": "fixed_point", "target": "axis_closure", "index": 0},
        {"kind": "merge_points", "target": "axis_closure", "index": 1, "partner": "right_face", "partner_index": 0},
        {"kind": "merge_points", "target": "left_face", "index": 1, "partner": "axis_closure", "partner_index": 0},
    ]
    dimensions = [
        {"kind": "line_length", "target": "axis_closure", "name": "FP_FACE_W_DIM", "variable_name": "PULLEY_L1", "value": inputs["face_width"], "driving": True},
    ]
    construction_lines: list[dict[str, Any]] = []
    if inputs["profile"] == "crowned":
        variables.extend(
            [
                {"name": "FP_ARC_R", "value": derived["crown_radius"], "expression": "(PULLEY_L1^2/4 + FP_CROWN^2)/(2*FP_CROWN)", "note": "Circular crown arc radius"},
                {"name": "FP_CENTER_Y", "value": derived["crown_radius"] - derived["outer_radius"], "expression": "FP_ARC_R - FP_OR", "note": "Crown arc center offset from rotation axis"},
            ]
        )
        pre_constraints.extend(
            [
                {"kind": "merge_points", "target": "right_face", "index": 1, "partner": "crowned_surface", "partner_index": 1},
                {"kind": "merge_points", "target": "crowned_surface", "index": 2, "partner": "left_face", "partner_index": 0},
            ]
        )
        construction_lines.append(
            {
                "id": "crown_centerline",
                "target": "crown_centerline",
                "kind": "line",
                "role": "auxiliary",
                "style": 2,
                "start": [inputs["face_width"] / 2.0, 0.0],
                "end": [inputs["face_width"] / 2.0, float(geometry["crown_center"][1])],
            }
        )
        pre_constraints.extend(
            [
                {"kind": "merge_points", "target": "crown_centerline", "index": 1, "partner": "crowned_surface", "partner_index": 0},
            ]
        )
        constraints.extend(
            [
                {"kind": "vertical", "target": "crown_centerline"},
                {"kind": "point_on_curve_middle", "target": "crown_centerline", "index": 0, "partner": "axis_closure"},
                {"kind": "h_align_points", "target": "right_face", "index": 1, "partner": "left_face", "partner_index": 0},
            ]
        )
        dimensions.extend(
            [
                {"kind": "line_length", "target": "crown_centerline", "name": "FP_CENTER_Y_DIM", "variable_name": "FP_CENTER_Y", "value": abs(float(geometry["crown_center"][1])), "driving": True},
                {"kind": "arc_radius", "target": "crowned_surface", "name": "FP_ARC_R_DIM", "variable_name": "FP_ARC_R", "value": derived["crown_radius"], "driving": True},
            ]
        )
    else:
        pre_constraints.extend(
            [
                {"kind": "merge_points", "target": "right_face", "index": 1, "partner": "outer_surface", "partner_index": 0},
                {"kind": "merge_points", "target": "outer_surface", "index": 1, "partner": "left_face", "partner_index": 0},
            ]
        )
        constraints.append({"kind": "horizontal", "target": "outer_surface"})
        dimensions.append(
            {"kind": "line_length", "target": "right_face", "name": "FP_OR_DIM", "variable_name": "FP_OR", "value": derived["outer_radius"], "driving": True}
        )
    bridge_preview = {
        "geometry": {
            "profile_entities": profile_entities,
            "axis": {"start": [0.0, 0.0], "end": [inputs["face_width"] + max(5.0, inputs["face_width"] * 0.1), 0.0]},
            "construction_entities": construction_lines,
        },
        "variables": variables,
        "pre_constraints": pre_constraints,
        "constraints": constraints,
        "dimensions": dimensions,
        "operations": [
            {"operation": "draw_axis", "start": [0.0, 0.0], "end": [inputs["face_width"] + max(5.0, inputs["face_width"] * 0.1), 0.0]},
            {"operation": "draw_profile", "profile_entities": profile_entities, "construction_lines": construction_lines},
            {"operation": "add_variables", "variables": variables},
            {"operation": "apply_constraints", "constraints": constraints},
            {"operation": "add_dimensions", "dimensions": dimensions},
            {"operation": "base_rotation"},
        ]
    }
    params = {
        "name": feature_name,
        "sketch_name": sketch_name,
        "total_length": inputs["face_width"],
        "angle_degrees": 360.0,
        "plane": "XOY",
        "variables": variables,
        "verify_profile_after_parameterization": True,
        "require_parameterization": True,
        "require_fully_defined": True,
        "require_all_constraints_applied": True,
        "profile_sketch_target_state": "fully_defined",
        "pre_constraints": pre_constraints,
        "constraints": constraints,
        "dimensions": dimensions,
        "sketch": {
            "axis_line_style": 3,
            "profile_line_style": 1,
            "constraints": {"enabled": True},
            "dimensions": {"enabled": True, "driving": True},
            "parameterization_order": "constraints_then_dimensions",
            "preflight_after_update": True,
            "require_exact_counts": True,
            "expected_constraint_count": len(constraints),
            "expected_dimension_count": len(dimensions),
        },
    }
    return {
        "ok": True,
        "stage": "flat_belt_pulley_cad_plan",
        "operation": "boss_rotation",
        "axis": "global_x",
        "params": params,
        "bridge_preview": bridge_preview,
        "entity_names": {"sketch": sketch_name, "feature": feature_name},
        "expected_volume_cm3": float(derived["volume_mm3"]) / 1000.0,
    }
