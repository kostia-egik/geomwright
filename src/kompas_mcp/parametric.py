from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
import math
from pathlib import Path
import re
from typing import Any

from .connect_curve import normalize_connect_curve_params
from .materials import resolve_material_payload
from .sketch import apply_dimension_display_mode
from .sketch import apply_placement_to_points
from .sketch import build_operation_label
from .sketch import build_external_conical_step_constraint_plan
from .sketch import build_external_conical_step_dimension_plan
from .sketch import build_external_conical_step_variable_plan
from .sketch import build_face_ring_groove_constraint_plan
from .sketch import build_face_ring_groove_dimension_plan
from .sketch import build_face_ring_groove_variable_plan
from .sketch import build_flat_step_constraint_plan
from .sketch import build_flat_step_dimension_plan
from .sketch import build_flat_step_variable_plan
from .sketch import build_parameter_name
from .sketch import build_parameter_note
from .sketch import build_polygonal_step_constraint_plan
from .sketch import build_polygonal_step_dimension_plan
from .sketch import build_polygonal_step_variable_plan
from .sketch import build_stepped_shaft_constraint_plan
from .sketch import build_stepped_shaft_dimension_plan
from .sketch import build_stepped_shaft_variable_plan
from .sketch import normalize_placement_options
from .sketch import normalize_sketch_options
from .sketch import normalize_parameter_prefix
from .thread_catalog import assess_thread_standard_for_helical_thread_v1
from .thread_catalog import resolve_thread_standard_entry
from .thread_profile_geometry import resolve_thread_profile_geometry
from .thread_profile_sketch import build_v60_flat_thread_profile_constraints
from .thread_profile_sketch import build_v60_flat_thread_profile_sketch
from .thread_profile_sketch import verify_v60_flat_thread_profile_contract
from .trimmed_curve import normalize_trimmed_curve_params


SUPPORTED_PART_SCENARIOS = (
    "stepped_shaft",
    "external_conical_step",
    "internal_conical_step",
    "internal_cylindrical_step",
    "external_polygonal_step",
    "internal_polygonal_step",
    "external_flat_step",
    "internal_flat_step",
    "external_helical_thread",
    "internal_helical_thread",
    "external_threaded_step",
    "internal_threaded_step",
    "face_ring_groove",
    "bolt_circle_holes",
    "compression_spring",
    "extension_spring",
    "point",
    "lcs",
    "workflow",
)


POINT_SCENARIO_ALIASES = {
    "point": "point",
    "point3d": "point",
    "reference_point": "point",
    "spatial_point": "point",
}


LCS_SCENARIO_ALIASES = {
    "lcs": "lcs",
    "csys": "lcs",
    "local_coordinate_system": "lcs",
    "coordinate_system": "lcs",
}


WORKFLOW_SCENARIO_ALIASES = {
    "workflow": "workflow",
    "chain": "workflow",
    "feature_chain": "workflow",
    "module_chain": "workflow",
}


EXTERNAL_CONICAL_STEP_SCENARIO_ALIASES = {
    "external_conical_step": "external_conical_step",
    "conical_step": "external_conical_step",
    "outer_conical_step": "external_conical_step",
    "external_taper_step": "external_conical_step",
}


INTERNAL_CONICAL_STEP_SCENARIO_ALIASES = {
    "internal_conical_step": "internal_conical_step",
    "inner_conical_step": "internal_conical_step",
    "internal_taper_step": "internal_conical_step",
    "inner_taper_step": "internal_conical_step",
}


INTERNAL_CYLINDRICAL_STEP_SCENARIO_ALIASES = {
    "internal_cylindrical_step": "internal_cylindrical_step",
    "inner_cylindrical_step": "internal_cylindrical_step",
    "internal_cylinder_step": "internal_cylindrical_step",
    "inner_cylinder_step": "internal_cylindrical_step",
    "internal_bore_step": "internal_cylindrical_step",
    "inner_bore_step": "internal_cylindrical_step",
    "internal_stepped_bore": "internal_cylindrical_step",
    "inner_stepped_bore": "internal_cylindrical_step",
    "internal_bore": "internal_cylindrical_step",
}


EXTERNAL_POLYGONAL_STEP_SCENARIO_ALIASES = {
    "external_polygonal_step": "external_polygonal_step",
    "outer_polygonal_step": "external_polygonal_step",
    "external_polygon_step": "external_polygonal_step",
    "outer_polygon_step": "external_polygonal_step",
    "polygonal_step": "external_polygonal_step",
}


INTERNAL_POLYGONAL_STEP_SCENARIO_ALIASES = {
    "internal_polygonal_step": "internal_polygonal_step",
    "inner_polygonal_step": "internal_polygonal_step",
    "internal_polygon_step": "internal_polygonal_step",
    "inner_polygon_step": "internal_polygonal_step",
    "polygonal_bore": "internal_polygonal_step",
    "internal_polygonal_bore": "internal_polygonal_step",
}


EXTERNAL_FLAT_STEP_SCENARIO_ALIASES = {
    "external_flat_step": "external_flat_step",
    "outer_flat_step": "external_flat_step",
    "external_profiled_step": "external_flat_step",
    "flat_step": "external_flat_step",
    "shaft_flat_step": "external_flat_step",
}


INTERNAL_FLAT_STEP_SCENARIO_ALIASES = {
    "internal_flat_step": "internal_flat_step",
    "inner_flat_step": "internal_flat_step",
    "internal_profiled_step": "internal_flat_step",
    "flat_bore": "internal_flat_step",
    "profiled_bore": "internal_flat_step",
}


EXTERNAL_HELICAL_THREAD_SCENARIO_ALIASES = {
    "external_helical_thread": "external_helical_thread",
    "external_physical_thread": "external_helical_thread",
    "physical_external_thread": "external_helical_thread",
    "helical_external_thread": "external_helical_thread",
    "external_real_thread": "external_helical_thread",
}


INTERNAL_HELICAL_THREAD_SCENARIO_ALIASES = {
    "internal_helical_thread": "internal_helical_thread",
    "internal_physical_thread": "internal_helical_thread",
    "physical_internal_thread": "internal_helical_thread",
    "helical_internal_thread": "internal_helical_thread",
    "internal_real_thread": "internal_helical_thread",
}


EXTERNAL_THREADED_STEP_SCENARIO_ALIASES = {
    "external_threaded_step": "external_threaded_step",
    "outer_threaded_step": "external_threaded_step",
    "threaded_step": "external_threaded_step",
    "threaded_shaft_step": "external_threaded_step",
    "external_thread_step": "external_threaded_step",
}


INTERNAL_THREADED_STEP_SCENARIO_ALIASES = {
    "internal_threaded_step": "internal_threaded_step",
    "inner_threaded_step": "internal_threaded_step",
    "threaded_bore": "internal_threaded_step",
    "internal_thread_step": "internal_threaded_step",
    "internal_threaded_bore": "internal_threaded_step",
}


FACE_RING_GROOVE_SCENARIO_ALIASES = {
    "face_ring_groove": "face_ring_groove",
    "ring_groove": "face_ring_groove",
    "annular_groove": "face_ring_groove",
    "end_face_ring_groove": "face_ring_groove",
    "face_groove": "face_ring_groove",
}


BOLT_CIRCLE_HOLES_SCENARIO_ALIASES = {
    "bolt_circle_holes": "bolt_circle_holes",
    "holes_on_bolt_circle": "bolt_circle_holes",
    "bolt_hole_circle": "bolt_circle_holes",
    "pcd_holes": "bolt_circle_holes",
    "hole_circle": "bolt_circle_holes",
}


COMPRESSION_SPRING_SCENARIO_ALIASES = {
    "compression_spring": "compression_spring",
    "spring": "compression_spring",
    "coil_spring": "compression_spring",
    "cylindrical_spring": "compression_spring",
}




EXTERNAL_CONICAL_STEP_DEFINITION_MODE_ALIASES = {
    "diameters_length": "diameters_length",
    "linear": "diameters_length",
    "diameter_length": "diameters_length",
    "diameters_angle": "diameters_angle",
    "two_diameters_angle": "diameters_angle",
    "diameters_conicity": "diameters_conicity",
    "two_diameters_conicity": "diameters_conicity",
    "one_diameter_length_angle": "one_diameter_length_angle",
    "single_diameter_length_angle": "one_diameter_length_angle",
    "one_diameter_length_conicity": "one_diameter_length_conicity",
    "single_diameter_length_conicity": "one_diameter_length_conicity",
}


def preview_stepped_shaft(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_stepped_shaft_params(params)
    steps = normalized["steps"]
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    local_profile_points = _build_shaft_profile_points(steps)
    profile_points = apply_placement_to_points(local_profile_points, normalized["placement"])
    axis_start = [float(profile_points[0][0]), float(profile_points[0][1])]
    axis_end = [axis_start[0] + normalized["total_length"], axis_start[1]]
    dimension_plan = apply_dimension_display_mode(
        build_stepped_shaft_dimension_plan(steps, profile_points, parameter_prefix=parameter_prefix),
        steps,
        mode=normalized["sketch"]["dimension_display"],
    )
    variable_plan = build_stepped_shaft_variable_plan(
        steps,
        parameter_prefix=parameter_prefix,
        operation_label=operation_label,
    )
    constraint_plan = build_stepped_shaft_constraint_plan(steps, profile_points)
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        },
        {
            "operation": "add_variables",
            "enabled": True,
            "variable_count": len(variable_plan),
            "variables": variable_plan,
            "live_status": "planned",
        },
        {
            "operation": "create_sketch",
            "plane": normalized["plane"],
            "placement": normalized["placement"],
            "description": "Create a half-profile sketch for rotation",
        },
        {
            "operation": "draw_axis",
            "start": axis_start,
            "end": axis_end,
            "line_style": normalized["sketch"]["axis_line_style"],
        },
        {
            "operation": "draw_profile",
            "point_count": len(profile_points),
            "profile_points": profile_points,
            "line_style": normalized["sketch"]["profile_line_style"],
        },
        {
            "operation": "apply_constraints",
            "enabled": normalized["sketch"]["constraints"]["enabled"],
            "constraint_count": len(constraint_plan),
            "constraints": constraint_plan,
            "live_status": "planned",
        },
        {
            "operation": "add_dimensions",
            "enabled": normalized["sketch"]["dimensions"]["enabled"],
            "dimension_count": len(dimension_plan),
            "dimensions": dimension_plan,
            "live_status": "planned",
        },
        {
            "operation": "base_rotation",
            "angle_degrees": normalized["angle_degrees"],
        },
    ]

    return {
        "scenario": "stepped_shaft",
        "ok": True,
        "params": normalized,
        "summary": {
            "step_count": len(steps),
            "total_length": normalized["total_length"],
            "min_diameter": min(step["diameter"] for step in steps),
            "max_diameter": max(step["diameter"] for step in steps),
            "profile_point_count": len(profile_points),
            "creation_status": "available",
            "axis_line_style": normalized["sketch"]["axis_line_style"],
            "profile_line_style": normalized["sketch"]["profile_line_style"],
            "dimension_display": normalized["sketch"]["dimension_display"],
            "planned_dimension_count": len(dimension_plan),
            "planned_constraint_count": len(constraint_plan),
            "planned_variable_count": len(variable_plan),
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
        },
        "interface": _build_stepped_shaft_interface(normalized, profile_points),
        "operations": operations,
    }


def preview_external_conical_step(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_external_conical_step_params(params)
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    local_profile_points = _build_external_conical_step_profile_points(normalized)
    profile_points = apply_placement_to_points(local_profile_points, normalized["placement"])
    axis_start = [float(profile_points[0][0]), float(profile_points[0][1])]
    axis_end = [axis_start[0] + normalized["length"], axis_start[1]]
    pseudo_steps = [
        {"diameter": normalized["start_diameter"]},
        {"diameter": normalized["end_diameter"]},
    ]
    dimension_plan = apply_dimension_display_mode(
        build_external_conical_step_dimension_plan(
            normalized,
            profile_points,
            parameter_prefix=parameter_prefix,
        ),
        pseudo_steps,
        mode=normalized["sketch"]["dimension_display"],
    )
    variable_plan = build_external_conical_step_variable_plan(
        normalized,
        parameter_prefix=parameter_prefix,
        operation_label=operation_label,
    )
    constraint_plan = build_external_conical_step_constraint_plan(profile_points)
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        },
        {
            "operation": "add_variables",
            "enabled": True,
            "variable_count": len(variable_plan),
            "variables": variable_plan,
            "live_status": "planned",
        },
        {
            "operation": "create_sketch",
            "plane": normalized["plane"],
            "placement": normalized["placement"],
            "description": "Create a half-profile sketch for rotation",
        },
        {
            "operation": "draw_axis",
            "start": axis_start,
            "end": axis_end,
            "line_style": normalized["sketch"]["axis_line_style"],
        },
        {
            "operation": "draw_profile",
            "point_count": len(profile_points),
            "profile_points": profile_points,
            "line_style": normalized["sketch"]["profile_line_style"],
        },
        {
            "operation": "apply_constraints",
            "enabled": normalized["sketch"]["constraints"]["enabled"],
            "constraint_count": len(constraint_plan),
            "constraints": constraint_plan,
            "live_status": "planned",
        },
        {
            "operation": "add_dimensions",
            "enabled": normalized["sketch"]["dimensions"]["enabled"],
            "dimension_count": len(dimension_plan),
            "dimensions": dimension_plan,
            "live_status": "planned",
        },
        {
            "operation": "base_rotation",
            "angle_degrees": normalized["angle_degrees"],
        },
    ]

    return {
        "scenario": "external_conical_step",
        "ok": True,
        "params": normalized,
        "summary": {
            "length": normalized["length"],
            "start_diameter": normalized["start_diameter"],
            "end_diameter": normalized["end_diameter"],
            "definition_mode": normalized["definition_mode"],
            "cone_angle_degrees": normalized["cone_angle_degrees"],
            "conicity": normalized["conicity"],
            "slope_direction": normalized["slope_direction"],
            "profile_point_count": len(profile_points),
            "creation_status": "available",
            "axis_line_style": normalized["sketch"]["axis_line_style"],
            "profile_line_style": normalized["sketch"]["profile_line_style"],
            "dimension_display": normalized["sketch"]["dimension_display"],
            "planned_dimension_count": len(dimension_plan),
            "planned_constraint_count": len(constraint_plan),
            "planned_variable_count": len(variable_plan),
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
        },
        "interface": _build_external_conical_step_interface(normalized, profile_points),
        "operations": operations,
    }


def preview_internal_conical_step(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_internal_conical_step_params(params)
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    local_profile_points = _build_internal_conical_step_profile_points(normalized)
    profile_points = apply_placement_to_points(local_profile_points, normalized["placement"])
    axis_start = [float(profile_points[0][0]), float(profile_points[0][1])]
    axis_end = [float(profile_points[-2][0]), float(profile_points[-2][1])]
    pseudo_steps = [
        {"diameter": normalized["start_diameter"]},
        {"diameter": normalized["end_diameter"]},
    ]
    dimension_plan = apply_dimension_display_mode(
        build_external_conical_step_dimension_plan(
            normalized,
            profile_points,
            parameter_prefix=parameter_prefix,
        ),
        pseudo_steps,
        mode=normalized["sketch"]["dimension_display"],
    )
    variable_plan = build_external_conical_step_variable_plan(
        normalized,
        parameter_prefix=parameter_prefix,
        operation_label=operation_label,
    )
    constraint_plan = build_external_conical_step_constraint_plan(profile_points)
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        }
    ]
    if normalized["source_preview"] is not None:
        operations.append(
            {
                "operation": "create_source_body",
                "source_scenario": normalized["source_scenario"],
                "summary": normalized["source_preview"]["summary"],
                "description": "Create the source revolved body used for the internal conical cut",
                "live_status": "planned",
            }
        )
    operations.extend(
        [
            {
                "operation": "add_variables",
                "enabled": True,
                "variable_count": len(variable_plan),
                "variables": variable_plan,
                "live_status": "planned",
            },
            {
                "operation": "create_sketch",
                "plane": normalized["plane"],
                "placement": normalized["placement"],
                "description": "Create a half-profile sketch for revolved cut",
            },
            {
                "operation": "draw_axis",
                "start": axis_start,
                "end": axis_end,
                "line_style": normalized["sketch"]["axis_line_style"],
            },
            {
                "operation": "draw_profile",
                "point_count": len(profile_points),
                "profile_points": profile_points,
                "line_style": normalized["sketch"]["profile_line_style"],
            },
            {
                "operation": "apply_constraints",
                "enabled": normalized["sketch"]["constraints"]["enabled"],
                "constraint_count": len(constraint_plan),
                "constraints": constraint_plan,
                "live_status": "planned",
            },
            {
                "operation": "add_dimensions",
                "enabled": normalized["sketch"]["dimensions"]["enabled"],
                "dimension_count": len(dimension_plan),
                "dimensions": dimension_plan,
                "live_status": "planned",
            },
            {
                "operation": "cut_rotation",
                "angle_degrees": normalized["angle_degrees"],
            },
        ]
    )

    return {
        "scenario": "internal_conical_step",
        "ok": True,
        "params": normalized,
        "summary": {
            "length": normalized["length"],
            "start_diameter": normalized["start_diameter"],
            "end_diameter": normalized["end_diameter"],
            "definition_mode": normalized["definition_mode"],
            "cone_angle_degrees": normalized["cone_angle_degrees"],
            "conicity": normalized["conicity"],
            "slope_direction": normalized["slope_direction"],
            "axial_direction": normalized["axial_direction"],
            "source_scenario": normalized["source_scenario"],
            "requires_existing_body": normalized["source_preview"] is None,
            "profile_point_count": len(profile_points),
            "creation_status": "available",
            "axis_line_style": normalized["sketch"]["axis_line_style"],
            "profile_line_style": normalized["sketch"]["profile_line_style"],
            "dimension_display": normalized["sketch"]["dimension_display"],
            "planned_dimension_count": len(dimension_plan),
            "planned_constraint_count": len(constraint_plan),
            "planned_variable_count": len(variable_plan),
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
        },
        "interface": _build_internal_conical_step_interface(normalized, profile_points),
        "operations": operations,
    }


def preview_internal_cylindrical_step(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_internal_cylindrical_step_params(params)
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    local_profile_points = _build_internal_cylindrical_step_profile_points(normalized)
    profile_points = apply_placement_to_points(local_profile_points, normalized["placement"])
    axis_start = [float(profile_points[0][0]), float(profile_points[0][1])]
    axis_end = [float(profile_points[-2][0]), float(profile_points[-2][1])]
    dimension_plan = apply_dimension_display_mode(
        build_stepped_shaft_dimension_plan(
            normalized["steps"],
            profile_points,
            parameter_prefix=parameter_prefix,
        ),
        normalized["steps"],
        mode=normalized["sketch"]["dimension_display"],
    )
    variable_plan = build_stepped_shaft_variable_plan(
        normalized["steps"],
        parameter_prefix=parameter_prefix,
        operation_label=operation_label,
    )
    constraint_plan = build_stepped_shaft_constraint_plan(normalized["steps"], profile_points)
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        }
    ]
    if normalized["source_preview"] is not None:
        operations.append(
            {
                "operation": "create_source_body",
                "source_scenario": normalized["source_scenario"],
                "summary": normalized["source_preview"]["summary"],
                "description": "Create the source revolved body used for the internal cylindrical cut",
                "live_status": "planned",
            }
        )
    operations.extend(
        [
            {
                "operation": "add_variables",
                "enabled": True,
                "variable_count": len(variable_plan),
                "variables": variable_plan,
                "live_status": "planned",
            },
            {
                "operation": "create_sketch",
                "plane": normalized["plane"],
                "placement": normalized["placement"],
                "description": "Create a half-profile sketch for revolved cut",
            },
            {
                "operation": "draw_axis",
                "start": axis_start,
                "end": axis_end,
                "line_style": normalized["sketch"]["axis_line_style"],
            },
            {
                "operation": "draw_profile",
                "point_count": len(profile_points),
                "profile_points": profile_points,
                "line_style": normalized["sketch"]["profile_line_style"],
            },
            {
                "operation": "apply_constraints",
                "enabled": normalized["sketch"]["constraints"]["enabled"],
                "constraint_count": len(constraint_plan),
                "constraints": constraint_plan,
                "live_status": "planned",
            },
            {
                "operation": "add_dimensions",
                "enabled": normalized["sketch"]["dimensions"]["enabled"],
                "dimension_count": len(dimension_plan),
                "dimensions": dimension_plan,
                "live_status": "planned",
            },
            {
                "operation": "cut_rotation",
                "angle_degrees": normalized["angle_degrees"],
            },
        ]
    )

    return {
        "scenario": "internal_cylindrical_step",
        "ok": True,
        "params": normalized,
        "summary": {
            "length": normalized["length"],
            "diameter": normalized["diameter"],
            "radius": normalized["radius"],
            "step_lengths": [float(step["length"]) for step in normalized["steps"]],
            "step_diameters": [float(step["diameter"]) for step in normalized["steps"]],
            "step_radii": [float(step["radius"]) for step in normalized["steps"]],
            "step_count": len(normalized["steps"]),
            "total_length": normalized["total_length"],
            "min_diameter": min(step["diameter"] for step in normalized["steps"]),
            "max_diameter": max(step["diameter"] for step in normalized["steps"]),
            "axial_direction": normalized["axial_direction"],
            "source_scenario": normalized["source_scenario"],
            "requires_existing_body": normalized["source_preview"] is None,
            "profile_point_count": len(profile_points),
            "creation_status": "available",
            "axis_line_style": normalized["sketch"]["axis_line_style"],
            "profile_line_style": normalized["sketch"]["profile_line_style"],
            "dimension_display": normalized["sketch"]["dimension_display"],
            "planned_dimension_count": len(dimension_plan),
            "planned_constraint_count": len(constraint_plan),
            "planned_variable_count": len(variable_plan),
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
        },
        "interface": _build_internal_cylindrical_step_interface(normalized, profile_points),
        "operations": operations,
    }


def preview_face_ring_groove(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_face_ring_groove_params(params)
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    local_profile_points = _build_face_ring_groove_profile_points(normalized)
    profile_points = apply_placement_to_points(local_profile_points, normalized["placement"])
    axis_start = [float(normalized["placement"]["effective_origin"][0]), float(normalized["placement"]["effective_origin"][1])]
    axis_end = [
        float(axis_start[0]) + (-float(normalized["depth"]) if normalized["axial_direction"] == "backward" else float(normalized["depth"])),
        float(axis_start[1]),
    ]
    dimension_plan = build_face_ring_groove_dimension_plan(
        normalized,
        profile_points,
        parameter_prefix=parameter_prefix,
    )
    variable_plan = build_face_ring_groove_variable_plan(
        normalized,
        parameter_prefix=parameter_prefix,
        operation_label=operation_label,
    )
    constraint_plan = build_face_ring_groove_constraint_plan(profile_points)
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        }
    ]
    if normalized["source_preview"] is not None:
        operations.append(
            {
                "operation": "create_source_body",
                "source_scenario": normalized["source_scenario"],
                "summary": normalized["source_preview"]["summary"],
                "description": "Create the source body used for the face ring groove cut",
                "live_status": "planned",
            }
        )
    operations.extend(
        [
            {
                "operation": "add_variables",
                "enabled": True,
                "variable_count": len(variable_plan),
                "variables": variable_plan,
                "live_status": "planned",
            },
            {
                "operation": "create_sketch",
                "plane": normalized["plane"],
                "placement": normalized["placement"],
                "description": "Create a face ring groove half-profile sketch for revolved cut",
            },
            {
                "operation": "draw_axis",
                "start": axis_start,
                "end": axis_end,
                "line_style": normalized["sketch"]["axis_line_style"],
            },
            {
                "operation": "draw_profile",
                "point_count": len(profile_points),
                "profile_points": profile_points,
                "construction_lines": [],
                "line_style": normalized["sketch"]["profile_line_style"],
            },
            {
                "operation": "apply_constraints",
                "enabled": normalized["sketch"]["constraints"]["enabled"],
                "constraint_count": len(constraint_plan),
                "constraints": constraint_plan,
                "live_status": "planned",
            },
            {
                "operation": "add_dimensions",
                "enabled": normalized["sketch"]["dimensions"]["enabled"],
                "dimension_count": len(dimension_plan),
                "dimensions": dimension_plan,
                "live_status": "planned",
            },
            {
                "operation": "cut_rotation",
                "angle_degrees": normalized["angle_degrees"],
            },
        ]
    )

    return {
        "scenario": "face_ring_groove",
        "ok": True,
        "params": normalized,
        "summary": {
            "inner_diameter": normalized["inner_diameter"],
            "outer_diameter": normalized["outer_diameter"],
            "bottom_inner_diameter": normalized["bottom_inner_diameter"],
            "bottom_outer_diameter": normalized["bottom_outer_diameter"],
            "depth": normalized["depth"],
            "inner_wall_angle_degrees": normalized["inner_wall_angle_degrees"],
            "outer_wall_angle_degrees": normalized["outer_wall_angle_degrees"],
            "axial_direction": normalized["axial_direction"],
            "source_scenario": normalized["source_scenario"],
            "requires_existing_body": normalized["source_preview"] is None,
            "profile_point_count": len(profile_points),
            "creation_status": "available",
            "axis_line_style": normalized["sketch"]["axis_line_style"],
            "profile_line_style": normalized["sketch"]["profile_line_style"],
            "planned_dimension_count": len(dimension_plan),
            "planned_constraint_count": len(constraint_plan),
            "planned_variable_count": len(variable_plan),
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
        },
        "interface": _build_face_ring_groove_interface(normalized, profile_points),
        "operations": operations,
    }


def preview_external_polygonal_step(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_external_polygonal_step_params(params)
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    local_vertices = _build_polygonal_step_vertices(normalized)
    vertices = apply_placement_to_points(local_vertices, normalized["placement"])
    axis_start = [float(normalized["placement"]["effective_origin"][0]), float(normalized["placement"]["effective_origin"][1])]
    axis_shift = -float(normalized["length"]) if normalized["axial_direction"] == "backward" else float(normalized["length"])
    axis_end = [float(axis_start[0]) + axis_shift, float(axis_start[1])]
    dimension_plan = build_polygonal_step_dimension_plan(normalized, vertices, parameter_prefix=parameter_prefix)
    variable_plan = build_polygonal_step_variable_plan(
        normalized,
        parameter_prefix=parameter_prefix,
        operation_label=operation_label,
    )
    constraint_plan = build_polygonal_step_constraint_plan(normalized, vertices, parameter_prefix=parameter_prefix)
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        },
        {
            "operation": "add_variables",
            "enabled": True,
            "variable_count": len(variable_plan),
            "variables": variable_plan,
            "live_status": "planned",
        },
        {
            "operation": "create_sketch",
            "plane": normalized["plane"],
            "placement": normalized["placement"],
            "description": "Create a polygonal profile sketch for boss extrusion",
        },
        {
            "operation": "draw_regular_polygon",
            "side_count": normalized["side_count"],
            "diameter_mode": normalized["diameter_mode"],
            "diameter": normalized["diameter"],
            "polygon_radius": normalized["polygon_radius"],
            "rotation_angle_degrees": normalized["rotation_angle_degrees"],
            "vertices": vertices,
            "line_style": normalized["sketch"]["profile_line_style"],
            "construction_line_style": normalize_sketch_options({"profile_line_style": "construction"})["profile_line_style"],
        },
        {
            "operation": "apply_constraints",
            "enabled": normalized["sketch"]["constraints"]["enabled"],
            "constraint_count": len(constraint_plan),
            "constraints": constraint_plan,
            "live_status": "planned",
        },
        {
            "operation": "add_dimensions",
            "enabled": normalized["sketch"]["dimensions"]["enabled"],
            "dimension_count": len(dimension_plan),
            "dimensions": dimension_plan,
            "live_status": "planned",
        },
        {
            "operation": "boss_extrusion",
            "length": normalized["length"],
            "axial_direction": normalized["axial_direction"],
            "operation_variable_bindings": list(normalized.get("operation_variable_bindings") or []),
            "live_status": "planned",
        },
    ]
    return {
        "scenario": "external_polygonal_step",
        "ok": True,
        "params": normalized,
        "summary": {
            "diameter": normalized["diameter"],
            "length": normalized["length"],
            "side_count": normalized["side_count"],
            "diameter_mode": normalized["diameter_mode"],
            "polygon_radius": normalized["polygon_radius"],
            "rotation_angle_degrees": normalized["rotation_angle_degrees"],
            "axial_direction": normalized["axial_direction"],
            "creation_status": "available",
            "planned_dimension_count": len(dimension_plan),
            "planned_constraint_count": len(constraint_plan),
            "planned_variable_count": len(variable_plan),
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
        },
        "interface": _build_external_polygonal_step_interface(normalized, axis_start, axis_end, vertices),
        "operations": operations,
    }


def preview_internal_polygonal_step(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_internal_polygonal_step_params(params)
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    local_vertices = _build_polygonal_step_vertices(normalized)
    vertices = apply_placement_to_points(local_vertices, normalized["placement"])
    axis_start = [float(normalized["placement"]["effective_origin"][0]), float(normalized["placement"]["effective_origin"][1])]
    axis_shift = -float(normalized["length"]) if normalized["axial_direction"] == "backward" else float(normalized["length"])
    axis_end = [float(axis_start[0]) + axis_shift, float(axis_start[1])]
    dimension_plan = build_polygonal_step_dimension_plan(normalized, vertices, parameter_prefix=parameter_prefix)
    variable_plan = build_polygonal_step_variable_plan(
        normalized,
        parameter_prefix=parameter_prefix,
        operation_label=operation_label,
    )
    constraint_plan = build_polygonal_step_constraint_plan(normalized, vertices, parameter_prefix=parameter_prefix)
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        }
    ]
    if normalized["source_preview"] is not None:
        operations.append(
            {
                "operation": "create_source_body",
                "source_scenario": normalized["source_scenario"],
                "summary": normalized["source_preview"]["summary"],
                "description": "Create the source body used for the polygonal cut",
                "live_status": "planned",
            }
        )
    operations.extend(
        [
            {
                "operation": "add_variables",
                "enabled": True,
                "variable_count": len(variable_plan),
                "variables": variable_plan,
                "live_status": "planned",
            },
            {
                "operation": "create_sketch",
                "plane": normalized["plane"],
                "placement": normalized["placement"],
                "description": "Create a polygonal profile sketch for cut extrusion",
            },
            {
                "operation": "draw_regular_polygon",
                "side_count": normalized["side_count"],
                "diameter_mode": normalized["diameter_mode"],
                "diameter": normalized["diameter"],
                "polygon_radius": normalized["polygon_radius"],
                "rotation_angle_degrees": normalized["rotation_angle_degrees"],
                "vertices": vertices,
                "line_style": normalized["sketch"]["profile_line_style"],
                "construction_line_style": normalize_sketch_options({"profile_line_style": "construction"})["profile_line_style"],
            },
            {
                "operation": "apply_constraints",
                "enabled": normalized["sketch"]["constraints"]["enabled"],
                "constraint_count": len(constraint_plan),
                "constraints": constraint_plan,
                "live_status": "planned",
            },
            {
                "operation": "add_dimensions",
                "enabled": normalized["sketch"]["dimensions"]["enabled"],
                "dimension_count": len(dimension_plan),
                "dimensions": dimension_plan,
                "live_status": "planned",
            },
            {
                "operation": "cut_extrusion",
                "length": normalized["length"],
                "axial_direction": normalized["axial_direction"],
                "operation_variable_bindings": list(normalized.get("operation_variable_bindings") or []),
                "live_status": "planned",
            },
        ]
    )
    return {
        "scenario": "internal_polygonal_step",
        "ok": True,
        "params": normalized,
        "summary": {
            "diameter": normalized["diameter"],
            "length": normalized["length"],
            "side_count": normalized["side_count"],
            "diameter_mode": normalized["diameter_mode"],
            "polygon_radius": normalized["polygon_radius"],
            "rotation_angle_degrees": normalized["rotation_angle_degrees"],
            "axial_direction": normalized["axial_direction"],
            "source_scenario": normalized["source_scenario"],
            "requires_existing_body": normalized["source_preview"] is None,
            "creation_status": "available",
            "planned_dimension_count": len(dimension_plan),
            "planned_constraint_count": len(constraint_plan),
            "planned_variable_count": len(variable_plan),
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
        },
        "interface": _build_internal_polygonal_step_interface(normalized, axis_start, axis_end, vertices),
        "operations": operations,
    }


def preview_external_flat_step(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_external_flat_step_params(params)
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    geometry = _build_flat_step_profile_geometry(normalized)
    dimension_plan = build_flat_step_dimension_plan(normalized, parameter_prefix=parameter_prefix)
    variable_plan = build_flat_step_variable_plan(
        normalized,
        parameter_prefix=parameter_prefix,
        operation_label=operation_label,
    )
    constraint_plan = build_flat_step_constraint_plan(normalized)
    axis_start = [float(normalized["placement"]["effective_origin"][0]), float(normalized["placement"]["effective_origin"][1])]
    axis_shift = -float(normalized["length"]) if normalized["axial_direction"] == "backward" else float(normalized["length"])
    axis_end = [float(axis_start[0]) + axis_shift, float(axis_start[1])]
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        },
        {
            "operation": "add_variables",
            "enabled": True,
            "variable_count": len(variable_plan),
            "variables": variable_plan,
            "live_status": "planned",
        },
        {
            "operation": "create_sketch",
            "plane": normalized["plane"],
            "placement": normalized["placement"],
            "description": "Create a flat-step profile sketch for boss extrusion",
        },
        {
            "operation": "draw_flat_profile",
            "diameter": normalized["diameter"],
            "flat_depth": normalized["flat_depth"],
            "flat_offset": normalized["flat_offset"],
            "flats_count": normalized["flats_count"],
            "helper_circle": geometry["helper_circle"],
            "profile_lines": geometry["profile_lines"],
            "profile_arcs": geometry["profile_arcs"],
            "line_style": normalized["sketch"]["profile_line_style"],
            "construction_line_style": normalize_sketch_options({"profile_line_style": "construction"})["profile_line_style"],
        },
        {
            "operation": "apply_constraints",
            "enabled": normalized["sketch"]["constraints"]["enabled"],
            "constraint_count": len(constraint_plan),
            "constraints": constraint_plan,
            "live_status": "planned",
        },
        {
            "operation": "add_dimensions",
            "enabled": normalized["sketch"]["dimensions"]["enabled"],
            "dimension_count": len(dimension_plan),
            "dimensions": dimension_plan,
            "live_status": "planned",
        },
        {
            "operation": "boss_extrusion",
            "length": normalized["length"],
            "axial_direction": normalized["axial_direction"],
            "operation_variable_bindings": list(normalized.get("operation_variable_bindings") or []),
            "live_status": "planned",
        },
    ]
    return {
        "scenario": "external_flat_step",
        "ok": True,
        "params": normalized,
        "summary": {
            "diameter": normalized["diameter"],
            "length": normalized["length"],
            "flat_depth": normalized["flat_depth"],
            "flat_offset": normalized["flat_offset"],
            "flats_count": normalized["flats_count"],
            "axial_direction": normalized["axial_direction"],
            "creation_status": "available",
            "planned_dimension_count": len(dimension_plan),
            "planned_constraint_count": len(constraint_plan),
            "planned_variable_count": len(variable_plan),
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
        },
        "interface": _build_external_flat_step_interface(normalized, axis_start, axis_end),
        "operations": operations,
    }


def preview_internal_flat_step(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_internal_flat_step_params(params)
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    geometry = _build_flat_step_profile_geometry(normalized)
    dimension_plan = build_flat_step_dimension_plan(normalized, parameter_prefix=parameter_prefix)
    variable_plan = build_flat_step_variable_plan(
        normalized,
        parameter_prefix=parameter_prefix,
        operation_label=operation_label,
    )
    constraint_plan = build_flat_step_constraint_plan(normalized)
    axis_start = [float(normalized["placement"]["effective_origin"][0]), float(normalized["placement"]["effective_origin"][1])]
    axis_shift = -float(normalized["length"]) if normalized["axial_direction"] == "backward" else float(normalized["length"])
    axis_end = [float(axis_start[0]) + axis_shift, float(axis_start[1])]
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        }
    ]
    if normalized["source_preview"] is not None:
        operations.append(
            {
                "operation": "create_source_body",
                "source_scenario": normalized["source_scenario"],
                "summary": normalized["source_preview"]["summary"],
                "description": "Create the source body used for the flat-step cut",
                "live_status": "planned",
            }
        )
    operations.extend(
        [
            {
                "operation": "add_variables",
                "enabled": True,
                "variable_count": len(variable_plan),
                "variables": variable_plan,
                "live_status": "planned",
            },
            {
                "operation": "create_sketch",
                "plane": normalized["plane"],
                "placement": normalized["placement"],
                "description": "Create a flat-step profile sketch for cut extrusion",
            },
            {
                "operation": "draw_flat_profile",
                "diameter": normalized["diameter"],
                "flat_depth": normalized["flat_depth"],
                "flat_offset": normalized["flat_offset"],
                "flats_count": normalized["flats_count"],
                "helper_circle": geometry["helper_circle"],
                "profile_lines": geometry["profile_lines"],
                "profile_arcs": geometry["profile_arcs"],
                "line_style": normalized["sketch"]["profile_line_style"],
                "construction_line_style": normalize_sketch_options({"profile_line_style": "construction"})["profile_line_style"],
            },
            {
                "operation": "apply_constraints",
                "enabled": normalized["sketch"]["constraints"]["enabled"],
                "constraint_count": len(constraint_plan),
                "constraints": constraint_plan,
                "live_status": "planned",
            },
            {
                "operation": "add_dimensions",
                "enabled": normalized["sketch"]["dimensions"]["enabled"],
                "dimension_count": len(dimension_plan),
                "dimensions": dimension_plan,
                "live_status": "planned",
            },
            {
                "operation": "cut_extrusion",
                "length": normalized["length"],
                "axial_direction": normalized["axial_direction"],
                "operation_variable_bindings": list(normalized.get("operation_variable_bindings") or []),
                "live_status": "planned",
            },
        ]
    )
    return {
        "scenario": "internal_flat_step",
        "ok": True,
        "params": normalized,
        "summary": {
            "diameter": normalized["diameter"],
            "length": normalized["length"],
            "flat_depth": normalized["flat_depth"],
            "flat_offset": normalized["flat_offset"],
            "flats_count": normalized["flats_count"],
            "axial_direction": normalized["axial_direction"],
            "source_scenario": normalized["source_scenario"],
            "requires_existing_body": normalized["source_preview"] is None,
            "creation_status": "available",
            "planned_dimension_count": len(dimension_plan),
            "planned_constraint_count": len(constraint_plan),
            "planned_variable_count": len(variable_plan),
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
        },
        "interface": _build_internal_flat_step_interface(normalized, axis_start, axis_end),
        "operations": operations,
    }


def preview_external_threaded_step(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_external_threaded_step_params(params)
    return _preview_threaded_step(normalized, scenario="external_threaded_step")


def preview_internal_threaded_step(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_internal_threaded_step_params(params)
    return _preview_threaded_step(normalized, scenario="internal_threaded_step")


def preview_external_helical_thread(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_external_helical_thread_params(params)
    return _preview_helical_thread(normalized, scenario="external_helical_thread")


def preview_internal_helical_thread(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_internal_helical_thread_params(params)
    return _preview_helical_thread(normalized, scenario="internal_helical_thread")


def preview_bolt_circle_holes(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_bolt_circle_holes_params(params)
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    placement_origin = normalized["placement"]["effective_origin"]
    start_angle = math.radians(normalized["start_angle_degrees"])
    pattern_radius = normalized["bolt_circle_diameter"] / 2.0
    first_hole_center = [
        float(placement_origin[0]),
        float(placement_origin[1]) + pattern_radius * math.cos(start_angle),
        pattern_radius * math.sin(start_angle),
    ]
    hole_centers = []
    angle_step = 360.0 / float(normalized["count"])
    for index in range(normalized["count"]):
        angle = math.radians(float(normalized["start_angle_degrees"]) + angle_step * index)
        hole_centers.append(
            [
                float(placement_origin[0]),
                float(placement_origin[1]) + pattern_radius * math.cos(angle),
                pattern_radius * math.sin(angle),
            ]
        )

    base_hole_preview = preview_internal_cylindrical_step(
        {
            "name": normalized["name"],
            "steps": [{"length": normalized["depth"], "diameter": normalized["hole_diameter"]}],
            "axial_direction": normalized["axial_direction"],
            "parameter_prefix": parameter_prefix,
            "placement": {"mode": "global", "origin": [0.0, 0.0]},
            "sketch": normalized["sketch"],
        }
    )
    base_hole_variable_plan = []
    for operation in base_hole_preview.get("operations") or []:
        if operation.get("operation") == "add_variables":
            base_hole_variable_plan = list(operation.get("variables") or [])
            operation["enabled"] = False
            operation["variable_count"] = 0
            operation["variables"] = []
            operation["live_status"] = "moved_to_parent"
            break
    variable_plan = base_hole_variable_plan + list(normalized.get("pattern_variable_plan") or [])
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        }
    ]
    if variable_plan:
        operations.append(
            {
                "operation": "add_variables",
                "enabled": True,
                "variable_count": len(variable_plan),
                "variables": variable_plan,
                "description": "Create external variables for the base hole and bolt-circle pattern geometry",
                "live_status": "planned",
            }
        )
    if normalized["source_preview"] is not None:
        operations.append(
            {
                "operation": "create_source_body",
                "source_scenario": normalized["source_scenario"],
                "summary": normalized["source_preview"]["summary"],
                "description": "Create the source body used for the bolt-circle hole pattern",
                "live_status": "planned",
            }
        )
    operations.extend(
        [
            {
                "operation": "create_pattern_axis_reference",
                "origin": [float(placement_origin[0]), float(placement_origin[1]), 0.0],
                "description": "Use the placement origin as the center of the bolt circle",
                "live_status": "planned",
            },
            {
                "operation": "create_first_hole_lcs",
                "origin": first_hole_center,
                "description": "Create a local coordinate system for the base hole at the first hole center",
                "live_status": "planned",
            },
            {
                "operation": "create_base_hole",
                "scenario": "internal_cylindrical_step",
                "summary": base_hole_preview["summary"],
                "description": "Create the base cylindrical hole feature used as the source operation for the pattern",
                "live_status": "planned",
            },
            {
                "operation": "create_circular_pattern",
                "count": normalized["count"],
                "angle_step_degrees": angle_step,
                "start_angle_degrees": normalized["start_angle_degrees"],
                "pattern_count_expression": normalized["pattern_count_expression"],
                "pattern_step_expression": normalized["pattern_step_expression"],
                "operation_variable_bindings": list(normalized.get("pattern_operation_variable_bindings") or []),
                "save_initial_orientation": True,
                "description": "Copy the base hole operation using the native KOMPAS circular pattern",
                "live_status": "planned",
            },
        ]
    )
    if normalized["auxiliary_geometry_hidden"]:
        operations.append(
            {
                "operation": "hide_auxiliary_geometry",
                "objects": [
                    "pattern_center_point",
                    "pattern_axis_tip_point",
                    "first_hole_center_point",
                    "first_hole_lcs",
                    "pattern_axis",
                ],
                "description": "Hide service geometry created for the bolt-circle pattern",
                "live_status": "planned",
            }
        )

    return {
        "scenario": "bolt_circle_holes",
        "ok": True,
        "params": normalized,
        "base_hole_preview": base_hole_preview,
        "summary": {
            "hole_diameter": normalized["hole_diameter"],
            "depth": normalized["depth"],
            "bolt_circle_diameter": normalized["bolt_circle_diameter"],
            "count": normalized["count"],
            "start_angle_degrees": normalized["start_angle_degrees"],
            "clockwise": normalized["clockwise"],
            "axial_direction": normalized["axial_direction"],
            "auxiliary_geometry_hidden": normalized["auxiliary_geometry_hidden"],
            "source_scenario": normalized["source_scenario"],
            "requires_existing_body": normalized["source_preview"] is None,
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "planned_variable_count": len(variable_plan),
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
            "first_hole_center": first_hole_center,
        },
        "interface": _build_bolt_circle_holes_interface(
            normalized,
            hole_centers,
            first_hole_center,
            variable_plan,
        ),
        "operations": operations,
    }


def preview_compression_spring(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_compression_spring_params(params)
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(
        normalized["name"],
        parameter_prefix=parameter_prefix,
    )
    placement_origin = normalized["placement"]["effective_origin"]
    start_center = [float(placement_origin[0]), float(placement_origin[1]), 0.0]
    end_center = [
        float(placement_origin[0]) + float(normalized["height"]),
        float(placement_origin[1]),
        0.0,
    ]
    selector_points = _build_compression_spring_selector_points(
        normalized,
        start_center,
        end_center,
    )
    start_end_summary = _build_compression_spring_end_summary(normalized, side_name="start")
    finish_end_summary = _build_compression_spring_end_summary(normalized, side_name="finish")
    mean_radius = float(normalized["mean_diameter"]) / 2.0
    profile_phase_degrees = (
        float(normalized["segment_plan"][0]["phase_degrees"])
        if normalized["segment_plan"]
        else 90.0
    )
    profile_phase_radians = math.radians(profile_phase_degrees)
    profile_center = [
        float(placement_origin[0]),
        float(placement_origin[1]) + mean_radius * math.cos(profile_phase_radians),
        mean_radius * math.sin(profile_phase_radians),
    ]
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        },
        {
            "operation": "add_variables",
            "enabled": True,
            "variable_count": len(normalized["variable_plan"]),
            "variables": normalized["variable_plan"],
            "description": "Create external variables for spring geometry",
            "live_status": "planned",
        },
        {
            "operation": "create_spring_axis",
            "start": start_center,
            "end": end_center,
            "description": "Create the spring axis reference",
            "live_status": "planned",
        },
    ]
    for segment in normalized["segment_plan"]:
        operations.append(
            {
                "operation": "create_spiral_path",
                "name": segment["path_name"],
                "role": segment["role"],
                "mean_diameter": normalized["mean_diameter"],
                "pitch": segment["pitch"],
                "height": segment["height"],
                "turns": segment["turns"],
                "start_offset": segment["start_offset"],
                "start_offset_expression": segment.get("start_offset_expression"),
                "phase_degrees": segment["phase_degrees"],
                "turning_angle_degrees": segment["turning_angle_degrees"],
                "orientation_angle_degrees": segment["orientation_angle_degrees"],
                "anchor_rotation_expression": segment.get("anchor_rotation_expression"),
                "angle_application_mode": segment["angle_application_mode"],
                "end_phase_degrees": segment["end_phase_degrees"],
                "left_hand": normalized["left_hand"],
                "operation_variable_bindings": list(segment["operation_variable_bindings"]),
                "description": segment["description"],
                "live_status": "planned",
            }
        )
    for connector in normalized["connector_plan"]:
        if str(connector.get("builder") or "") == "trimmed_connect_curve":
            curve1_trim = dict(connector["curve1_trim"])
            curve2_trim = dict(connector["curve2_trim"])
            connect_curve = dict(connector["connect_curve"])
            operations.extend(
                [
                    {
                        "operation": "create_trimmed_curve_path",
                        "name": curve1_trim["name"],
                        "role": f"{connector['role']}_curve1_trim",
                        "source_curve": connector["curve1_path_name"],
                        "point_name": curve1_trim["point_name"],
                        "offset": curve1_trim["offset"],
                        "offset_expression": connector.get("trim_length_expression"),
                        "offset_type": curve1_trim["offset_type"],
                        "direction": bool(curve1_trim["direction"]),
                        "sense": bool(curve1_trim["sense"]),
                        "point_operation_variable_bindings": list(
                            curve1_trim.get("point_operation_variable_bindings") or []
                        ),
                        "description": "Trim the local end of the previous spring segment near the transition joint",
                        "live_status": "planned",
                    },
                    {
                        "operation": "create_trimmed_curve_path",
                        "name": curve2_trim["name"],
                        "role": f"{connector['role']}_curve2_trim",
                        "source_curve": connector["curve2_path_name"],
                        "point_name": curve2_trim["point_name"],
                        "offset": curve2_trim["offset"],
                        "offset_expression": connector.get("trim_length_expression"),
                        "offset_type": curve2_trim["offset_type"],
                        "direction": bool(curve2_trim["direction"]),
                        "sense": bool(curve2_trim["sense"]),
                        "point_operation_variable_bindings": list(
                            curve2_trim.get("point_operation_variable_bindings") or []
                        ),
                        "description": "Trim the local start of the next spring segment near the transition joint",
                        "live_status": "planned",
                    },
                    {
                        "operation": "create_connect_curve_path",
                        "name": connect_curve["name"],
                        "role": connector["role"],
                        "curve1": curve1_trim["name"],
                        "curve2": curve2_trim["name"],
                        "curve1_connect_vertex": bool(connect_curve["curve1_connect_vertex"]),
                        "curve2_connect_vertex": bool(connect_curve["curve2_connect_vertex"]),
                        "curve1_connect_type": int(connect_curve["curve1_connect_type"]),
                        "curve2_connect_type": int(connect_curve["curve2_connect_type"]),
                        "tension": float(connect_curve["tension"]),
                        "tension_expression": connector.get("tension_expression"),
                        "operation_variable_bindings": list(
                            connect_curve.get("operation_variable_bindings") or []
                        ),
                        "description": connector["description"],
                        "live_status": "planned",
                    },
                ]
            )
            continue
        operations.append(
            {
                "operation": "create_curve_fillet_path",
                "name": connector["path_name"],
                "role": connector["role"],
                "curve1": connector["curve1_path_name"],
                "curve2": connector["curve2_path_name"],
                "radius": connector["radius"],
                "trim_curve1": bool(connector["trim_curve1"]),
                "trim_curve2": bool(connector["trim_curve2"]),
                "joint_point": list(connector["joint_point"]),
                "description": connector["description"],
                "live_status": "planned",
            }
        )
    operations.extend(
        [
            {
                "operation": "create_wire_profile",
                "name": normalized["profile_name"],
                "role": "full_path",
                "profile": "circle",
                "plane": normalized["plane"],
                "center": profile_center,
                "radius": normalized["wire_diameter"] / 2.0,
                "phase_degrees": profile_phase_degrees,
                "sketch_parameterization": {
                    "constraint_count": len(normalized["profile_sketch_constraints"]),
                    "dimension_count": len(normalized["profile_sketch_dimensions"]),
                    "constraints": list(normalized["profile_sketch_constraints"]),
                    "dimensions": list(normalized["profile_sketch_dimensions"]),
                    "target_state": normalized["profile_sketch_target_state"],
                },
                "description": "Create one circular wire profile at the start of the composed spring path",
                "live_status": "planned",
            },
            {
                "operation": "boss_evolution",
                "name": normalized["sweep_name"],
                "role": "full_path",
                "profile": normalized["profile_name"],
                "paths": list(normalized["full_path_sequence"]),
                "path_count": len(normalized["full_path_sequence"]),
                "sweep_alignment": normalized["sweep_alignment_mode"],
                "description": "Sweep one wire profile along the full spring path orthogonally to the trajectory",
                "live_status": "planned",
            },
        ]
    )
    if normalized["auxiliary_geometry_hidden"]:
        operations.append(
            {
                "operation": "hide_auxiliary_geometry",
                "objects": [
                    "spring_axis",
                    *[segment["path_name"] for segment in normalized["segment_plan"]],
                    normalized["profile_name"],
                ],
                "description": "Hide service geometry created for the spring",
                "live_status": "planned",
            }
        )

    return {
        "scenario": "compression_spring",
        "ok": True,
        "params": normalized,
        "summary": {
            "mean_diameter": normalized["mean_diameter"],
            "outer_diameter": normalized["outer_diameter"],
            "inner_diameter": normalized["inner_diameter"],
            "wire_diameter": normalized["wire_diameter"],
            "pitch": normalized["pitch"],
            "height": normalized["height"],
            "turns": normalized["turns"],
            "working_turns": normalized["working_turns"],
            "total_turns": normalized["total_turns"],
            "end_turns_per_side": normalized["end_turns_per_side"],
            "ground_turns_per_side": normalized["ground_turns_per_side"],
            "transition_fillet_radius": normalized["transition_fillet_radius"],
            "transition_trim_length": normalized["transition_trim_length"],
            "transition_trim_length_expression": normalized["transition_trim_length_expression"],
            "transition_trim_length_variable": normalized["transition_trim_length_variable"],
            "transition_connect_tension": normalized["transition_connect_tension"],
            "transition_connect_tension_expression": normalized["transition_connect_tension_expression"],
            "transition_connect_tension_variable": normalized["transition_connect_tension_variable"],
            "end_contract_mode": normalized["end_contract_mode"],
            "end_projection_mode": normalized["end_projection_mode"],
            "start_end_summary": start_end_summary,
            "finish_end_summary": finish_end_summary,
            "left_hand": normalized["left_hand"],
            "auxiliary_geometry_hidden": normalized["auxiliary_geometry_hidden"],
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "planned_variable_count": len(normalized["variable_plan"]),
            "placement_mode": normalized["placement"]["mode"],
            "placement_origin": normalized["placement"]["origin"],
            "placement_base_mode": normalized["placement"]["base"]["mode"],
            "placement_base_origin": normalized["placement"]["base_origin"],
            "placement_local_offset": normalized["placement"]["local_offset"],
            "placement_reference": normalized["placement"]["reference"],
            "live_supported": normalized["live_supported"],
            "profile_plane": normalized["plane"],
            "sweep_alignment": normalized["sweep_alignment_mode"],
            "connector_count": len(normalized["connector_plan"]),
            "contour_ready": bool(normalized["path_verification"]["contour_ready"]),
            "max_joint_gap": float(normalized["path_verification"]["max_joint_gap"]),
        },
        "selectors": selector_points,
        "interface": _build_compression_spring_interface(
            normalized,
            start_center,
            end_center,
            selector_points,
        ),
        "operations": operations,
    }


def preview_point(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_point_params(params)
    point = normalized["origin"]
    operations: list[dict[str, Any]] = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        }
    ]
    if normalized["mode"] == "offset_from_point":
        operations.append(
            {
                "operation": "create_point",
                "role": "reference_point",
                "mode": "global",
                "name": normalized["reference_name"],
                "origin": normalized["reference_origin"],
                "description": "Create an internal base point for offset placement",
                "live_status": "planned",
            }
        )
    elif normalized["mode"] == "center_of_object":
        source_preview = normalized["reference"]["source_preview"]
        operations.append(
            {
                "operation": "create_source_body",
                "source_scenario": normalized["reference"]["source_scenario"],
                "selector": normalized["reference"]["selector"],
                "summary": source_preview["summary"],
                "description": "Create the source revolved body used for object-center point placement",
                "live_status": "planned",
            }
        )
        operations.append(
            {
                "operation": "resolve_reference_object",
                "mode": "center_of_object",
                "reference": normalized["reference"],
                "reference_origin": normalized["reference_origin"],
                "description": "Resolve the selected planar face of the source revolved body",
                "live_status": "planned",
            }
        )
    operations.append(
        {
            "operation": "create_point",
            "mode": normalized["mode"],
            "name": normalized["point_name"],
            "origin": point,
            "reference_origin": normalized["reference_origin"],
            "offset": normalized["offset"],
            "description": "Create a 3D reference point",
            "live_status": "planned" if normalized["live_supported"] else "not_supported_yet",
        }
    )

    return {
        "scenario": "point",
        "ok": True,
        "params": normalized,
        "summary": {
            "mode": normalized["mode"],
            "point_name": normalized["point_name"],
            "origin": point,
            "reference_origin": normalized["reference_origin"],
            "reference_name": normalized["reference_name"],
            "offset": normalized["offset"],
            "reference_selector": normalized["reference_selector"],
            "source_scenario": normalized["source_scenario"],
            "parameter_prefix": normalized["parameter_prefix"],
            "creation_status": "available" if normalized["live_supported"] else "preview_only",
        },
        "interface": {
            "feature_type": "reference.point3d",
            "parameter_namespace": normalized["parameter_prefix"],
            "anchors": {
                "point": point,
            },
            "outputs": {
                "point": {
                    "type": "point",
                    "name": normalized["point_name"],
                    "origin": point,
                    "live_supported": normalized["live_supported"],
                }
            },
            "reference": {
                "type": "point",
                "name": normalized["point_name"],
                "origin": point,
                "mode": normalized["mode"],
                "reference_origin": normalized["reference_origin"],
                "reference_selector": normalized["reference_selector"],
                "source_scenario": normalized["source_scenario"],
                "live_supported": normalized["live_supported"],
            },
        },
        "operations": operations,
    }


def preview_lcs(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_lcs_params(params)
    origin = normalized["origin"]
    operations: list[dict[str, Any]] = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        }
    ]
    if normalized["mode"] == "point" and normalized["reference_origin"] is not None:
        operations.append(
            {
                "operation": "create_point",
                "role": "reference_point",
                "mode": "global",
                "name": normalized["reference_name"],
                "origin": normalized["reference_origin"],
                "description": "Create an internal reference point for the local coordinate system",
                "live_status": "planned",
            }
        )
    elif normalized["mode"] == "object" and isinstance(normalized["reference"], dict) and normalized["reference"].get("source_preview"):
        source_preview = normalized["reference"]["source_preview"]
        operations.append(
            {
                "operation": "create_source_body",
                "source_scenario": normalized["reference"]["source_scenario"],
                "selector": normalized["reference"]["selector"],
                "summary": source_preview["summary"],
                "description": "Create the source revolved body used for object-based local coordinate system placement",
                "live_status": "planned",
            }
        )
        operations.append(
            {
                "operation": "resolve_reference_object",
                "mode": "object",
                "reference": normalized["reference"],
                "reference_origin": normalized["reference_origin"],
                "description": "Resolve the selected planar face of the source revolved body",
                "live_status": "planned",
            }
        )
    operations.append(
        {
            "operation": "create_lcs",
            "mode": normalized["mode"],
            "name": normalized["lcs_name"],
            "origin": origin,
            "rotation": normalized["rotation"],
            "reference": normalized["reference"],
            "reference_origin": normalized["reference_origin"],
            "only_outer_contour": normalized["only_outer_contour"],
            "description": "Create a local coordinate system",
            "live_status": "planned" if normalized["live_supported"] else "not_supported_yet",
        }
    )

    return {
        "scenario": "lcs",
        "ok": True,
        "params": normalized,
        "summary": {
            "mode": normalized["mode"],
            "lcs_name": normalized["lcs_name"],
            "origin": origin,
            "rotation": normalized["rotation"],
            "reference": normalized["reference"],
            "reference_origin": normalized["reference_origin"],
            "reference_name": normalized["reference_name"],
            "parameter_prefix": normalized["parameter_prefix"],
            "only_outer_contour": normalized["only_outer_contour"],
            "creation_status": "available" if normalized["live_supported"] else "preview_only",
        },
        "interface": {
            "feature_type": "reference.lcs",
            "parameter_namespace": normalized["parameter_prefix"],
            "anchors": {
                "origin": origin,
            },
            "outputs": {
                "lcs": {
                    "type": "lcs",
                    "name": normalized["lcs_name"],
                    "origin": origin,
                    "live_supported": normalized["live_supported"],
                }
            },
            "placement_ref": normalized["lcs_name"],
            "reference": {
                "type": "lcs",
                "name": normalized["lcs_name"],
                "mode": normalized["mode"],
                "origin": origin,
                "rotation": normalized["rotation"],
                "reference": normalized["reference"],
            },
        },
        "operations": operations,
    }


def preview_workflow(params: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_workflow_params(params)
    exports = {
        export["name"]: dict(export["output"])
        for export in normalized["exports"]
    }
    operation_previews = [
        {
            "id": operation["id"],
            "scenario": operation["scenario"],
            "depends_on": list(operation["depends_on"]),
            "bindings": dict(operation["bindings"]),
            "summary": dict(operation["preview"]["summary"]),
            "interface": dict(operation["preview"]["interface"]),
        }
        for operation in normalized["operations"]
    ]
    return {
        "scenario": "workflow",
        "ok": True,
        "params": normalized,
        "summary": {
            "operation_count": len(normalized["operations"]),
            "operation_ids": [operation["id"] for operation in normalized["operations"]],
            "export_count": len(normalized["exports"]),
            "export_names": [export["name"] for export in normalized["exports"]],
            "creation_status": "available" if normalized["live_supported"] else "preview_only",
            "live_supported": normalized["live_supported"],
            "output_path": normalized["output_path"],
        },
        "interface": {
            "feature_type": "workflow.chain",
            "operation_ids": [operation["id"] for operation in normalized["operations"]],
            "live_supported": normalized["live_supported"],
            "outputs": exports,
            "exports": exports,
            "results": {
                operation["id"]: {
                    "scenario": operation["scenario"],
                    "summary": dict(operation["preview"]["summary"]),
                    "interface": dict(operation["preview"]["interface"]),
                }
                for operation in normalized["operations"]
            },
        },
        "operations": operation_previews,
    }


def normalize_stepped_shaft_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    steps_payload = params.get("steps")
    if not isinstance(steps_payload, list) or not steps_payload:
        raise ValueError("steps must be a non-empty list")

    steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps_payload):
        if not isinstance(step, dict):
            raise ValueError(f"steps[{index}] must be an object")
        length = _positive_float(step.get("length"), f"steps[{index}].length")
        diameter = _positive_float(step.get("diameter"), f"steps[{index}].diameter")
        steps.append(
            {
                "index": index,
                "length": length,
                "diameter": diameter,
                "radius": diameter / 2.0,
                "name": str(step.get("name") or f"step-{index + 1}"),
            }
        )

    _validate_adjacent_step_diameters(steps)

    total_length = sum(step["length"] for step in steps)
    angle_degrees = float(params.get("angle_degrees") or 360.0)
    if angle_degrees <= 0 or angle_degrees > 360:
        raise ValueError("angle_degrees must be in range (0, 360]")

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    sketch = normalize_sketch_options(params.get("sketch"))
    placement = normalize_placement_options(params.get("placement"))
    if placement["base"]["mode"] in ("csys", "csys_ref") and not placement["rotation_supported"]:
        raise ValueError("placement.axis_direction rotation is not supported yet; use a translated csys with the default axis direction")
    parameter_prefix = normalize_parameter_prefix(
        params.get("parameter_prefix") or params.get("parameter_namespace")
    )
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))

    return {
        "name": str(params.get("name") or "Stepped shaft"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "plane": str(params.get("plane") or "XOY"),
        "axis": str(params.get("axis") or "OX"),
        "angle_degrees": angle_degrees,
        "sketch": sketch,
        "placement": placement,
        "parameter_prefix": parameter_prefix,
        "steps": steps,
        "total_length": total_length,
        "output_path": output_path,
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def normalize_external_conical_step_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    definition_mode = _normalize_external_conical_step_definition_mode(
        params.get("definition_mode") or params.get("cone_definition_mode") or params.get("mode")
    )
    length = _optional_positive_float(params, "length", "length", "l")
    start_diameter = _optional_positive_float(
        params,
        "start_diameter",
        "start_diameter",
        "diameter_start",
        "d1",
    )
    end_diameter = _optional_positive_float(
        params,
        "end_diameter",
        "end_diameter",
        "diameter_end",
        "d2",
    )
    cone_angle_degrees = _normalize_cone_angle_degrees(
        _coalesce_defined(
            params,
            "cone_angle_degrees",
            "taper_angle_degrees",
            "cone_angle",
            "taper_angle",
        )
    )
    conicity = _normalize_conicity_value(
        _coalesce_defined(params, "conicity", "taper_ratio", "cone_ratio")
    )
    slope_direction = _normalize_cone_slope_direction(
        params.get("slope_direction") or params.get("taper_direction") or params.get("slope")
    )
    if definition_mode is None:
        definition_mode = _infer_external_conical_step_definition_mode(
            length=length,
            start_diameter=start_diameter,
            end_diameter=end_diameter,
            cone_angle_degrees=cone_angle_degrees,
            conicity=conicity,
        )
    resolved_geometry = _resolve_external_conical_step_geometry(
        mode=definition_mode,
        length=length,
        start_diameter=start_diameter,
        end_diameter=end_diameter,
        cone_angle_degrees=cone_angle_degrees,
        conicity=conicity,
        slope_direction=slope_direction,
    )
    length = float(resolved_geometry["length"])
    start_diameter = float(resolved_geometry["start_diameter"])
    end_diameter = float(resolved_geometry["end_diameter"])
    cone_angle_degrees = float(resolved_geometry["cone_angle_degrees"])
    conicity = float(resolved_geometry["conicity"])
    slope_direction = str(resolved_geometry["slope_direction"])
    angle_degrees = float(params.get("angle_degrees") or 360.0)
    if angle_degrees <= 0 or angle_degrees > 360:
        raise ValueError("angle_degrees must be in range (0, 360]")

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    sketch = normalize_sketch_options(params.get("sketch"))
    placement = normalize_placement_options(params.get("placement"))
    if placement["base"]["mode"] in ("csys", "csys_ref") and not placement["rotation_supported"]:
        raise ValueError("placement.axis_direction rotation is not supported yet; use a translated csys with the default axis direction")
    parameter_prefix = normalize_parameter_prefix(
        params.get("parameter_prefix") or params.get("parameter_namespace")
    )
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))

    return {
        "name": str(params.get("name") or "External conical step"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "plane": str(params.get("plane") or "XOY"),
        "axis": str(params.get("axis") or "OX"),
        "angle_degrees": angle_degrees,
        "definition_mode": definition_mode,
        "cone_angle_degrees": cone_angle_degrees,
        "conicity": conicity,
        "slope_direction": slope_direction,
        "sketch": sketch,
        "placement": placement,
        "parameter_prefix": parameter_prefix,
        "length": length,
        "start_diameter": start_diameter,
        "end_diameter": end_diameter,
        "start_radius": start_diameter / 2.0,
        "end_radius": end_diameter / 2.0,
        "total_length": length,
        "output_path": output_path,
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def normalize_internal_conical_step_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    definition_mode = _normalize_external_conical_step_definition_mode(
        params.get("definition_mode") or params.get("cone_definition_mode") or params.get("mode")
    )
    length = _optional_positive_float(params, "length", "length", "l")
    start_diameter = _optional_positive_float(
        params,
        "start_diameter",
        "start_diameter",
        "diameter_start",
        "d1",
    )
    end_diameter = _optional_positive_float(
        params,
        "end_diameter",
        "end_diameter",
        "diameter_end",
        "d2",
    )
    cone_angle_degrees = _normalize_cone_angle_degrees(
        _coalesce_defined(
            params,
            "cone_angle_degrees",
            "taper_angle_degrees",
            "cone_angle",
            "taper_angle",
        )
    )
    conicity = _normalize_conicity_value(
        _coalesce_defined(params, "conicity", "taper_ratio", "cone_ratio")
    )
    slope_direction = _normalize_cone_slope_direction(
        params.get("slope_direction") or params.get("taper_direction") or params.get("slope")
    )
    axial_direction = _normalize_internal_conical_step_axial_direction(
        params.get("axial_direction") or params.get("direction") or params.get("axial")
    )
    if definition_mode is None:
        definition_mode = _infer_external_conical_step_definition_mode(
            length=length,
            start_diameter=start_diameter,
            end_diameter=end_diameter,
            cone_angle_degrees=cone_angle_degrees,
            conicity=conicity,
        )
    resolved_geometry = _resolve_internal_conical_step_geometry(
        mode=definition_mode,
        length=length,
        start_diameter=start_diameter,
        end_diameter=end_diameter,
        cone_angle_degrees=cone_angle_degrees,
        conicity=conicity,
        slope_direction=slope_direction,
    )
    length = float(resolved_geometry["length"])
    start_diameter = float(resolved_geometry["start_diameter"])
    end_diameter = float(resolved_geometry["end_diameter"])
    cone_angle_degrees = float(resolved_geometry["cone_angle_degrees"])
    conicity = float(resolved_geometry["conicity"])
    slope_direction = str(resolved_geometry["slope_direction"])
    angle_degrees = float(params.get("angle_degrees") or 360.0)
    if angle_degrees <= 0 or angle_degrees > 360:
        raise ValueError("angle_degrees must be in range (0, 360]")

    source_scenario = params.get("source_scenario") or params.get("base_scenario")
    source_params = params.get("source_params")
    source_preview = None
    if source_scenario is not None:
        source_scenario = _normalize_scenario(str(source_scenario))
        if source_scenario not in ("stepped_shaft", "external_conical_step"):
            raise ValueError("internal_conical_step source_scenario must be stepped_shaft or external_conical_step")
        if not isinstance(source_params, dict):
            raise ValueError("internal_conical_step source_params must be an object when source_scenario is provided")
        source_preview = preview_part_scenario(source_scenario, source_params)
    elif source_params is not None:
        raise ValueError("internal_conical_step source_params requires source_scenario")

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    sketch = normalize_sketch_options(params.get("sketch"))
    placement = normalize_placement_options(params.get("placement"))
    if placement["base"]["mode"] in ("csys", "csys_ref") and not placement["rotation_supported"]:
        raise ValueError("placement.axis_direction rotation is not supported yet; use a translated csys with the default axis direction")
    parameter_prefix = normalize_parameter_prefix(
        params.get("parameter_prefix") or params.get("parameter_namespace")
    )
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))

    return {
        "name": str(params.get("name") or "Internal conical step"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "plane": str(params.get("plane") or "XOY"),
        "axis": str(params.get("axis") or "OX"),
        "angle_degrees": angle_degrees,
        "definition_mode": definition_mode,
        "cone_angle_degrees": cone_angle_degrees,
        "conicity": conicity,
        "slope_direction": slope_direction,
        "axial_direction": axial_direction,
        "sketch": sketch,
        "placement": placement,
        "parameter_prefix": parameter_prefix,
        "length": length,
        "start_diameter": start_diameter,
        "end_diameter": end_diameter,
        "start_radius": start_diameter / 2.0,
        "end_radius": end_diameter / 2.0,
        "total_length": length,
        "source_scenario": source_scenario,
        "source_params": dict(source_params) if isinstance(source_params, dict) else None,
        "source_preview": source_preview,
        "output_path": output_path,
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def normalize_internal_cylindrical_step_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    steps_payload = params.get("steps")
    steps: list[dict[str, Any]] = []
    if steps_payload is not None:
        if not isinstance(steps_payload, list) or not steps_payload:
            raise ValueError("internal_cylindrical_step steps must be a non-empty list")
        for index, step in enumerate(steps_payload):
            if not isinstance(step, dict):
                raise ValueError(f"steps[{index}] must be an object")
            length = _positive_float(step.get("length"), f"steps[{index}].length")
            diameter = _positive_float(step.get("diameter"), f"steps[{index}].diameter")
            steps.append(
                {
                    "index": index,
                    "name": str(step.get("name") or f"step-{index + 1}"),
                    "length": length,
                    "diameter": diameter,
                    "radius": diameter / 2.0,
                }
            )
    else:
        length = _optional_positive_float(params, "length", "length", "l")
        if length is None:
            raise ValueError("internal_cylindrical_step requires steps or length")
        diameter = _optional_positive_float(params, "diameter", "diameter", "d", "d1")
        if diameter is None:
            raise ValueError("internal_cylindrical_step requires steps or diameter")
        steps = [
            {
                "index": 0,
                "name": str(params.get("step_name") or "step-1"),
                "length": float(length),
                "diameter": float(diameter),
                "radius": float(diameter) / 2.0,
            }
        ]

    _validate_adjacent_step_diameters(steps)
    total_length = sum(float(step["length"]) for step in steps)
    first_step = steps[0]
    angle_degrees = float(params.get("angle_degrees") or 360.0)
    if angle_degrees <= 0 or angle_degrees > 360:
        raise ValueError("angle_degrees must be in range (0, 360]")
    axial_direction = _normalize_internal_conical_step_axial_direction(
        params.get("axial_direction") or params.get("direction") or params.get("axial")
    )

    source_scenario = params.get("source_scenario") or params.get("base_scenario")
    source_params = params.get("source_params")
    source_preview = None
    if source_scenario is not None:
        source_scenario = _normalize_scenario(str(source_scenario))
        if source_scenario not in (
            "stepped_shaft",
            "external_conical_step",
            "internal_conical_step",
            "internal_cylindrical_step",
        ):
            raise ValueError(
                "internal_cylindrical_step source_scenario must be stepped_shaft, external_conical_step, internal_conical_step or internal_cylindrical_step"
            )
        if not isinstance(source_params, dict):
            raise ValueError(
                "internal_cylindrical_step source_params must be an object when source_scenario is provided"
            )
        source_preview = preview_part_scenario(source_scenario, source_params)
    elif source_params is not None:
        raise ValueError("internal_cylindrical_step source_params requires source_scenario")

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    sketch = normalize_sketch_options(params.get("sketch"))
    placement = normalize_placement_options(params.get("placement"))
    if placement["base"]["mode"] in ("csys", "csys_ref") and not placement["rotation_supported"]:
        raise ValueError("placement.axis_direction rotation is not supported yet; use a translated csys with the default axis direction")
    parameter_prefix = normalize_parameter_prefix(
        params.get("parameter_prefix") or params.get("parameter_namespace")
    )
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))

    return {
        "name": str(params.get("name") or "Internal cylindrical bore"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "plane": str(params.get("plane") or "XOY"),
        "axis": str(params.get("axis") or "OX"),
        "angle_degrees": angle_degrees,
        "axial_direction": axial_direction,
        "sketch": sketch,
        "placement": placement,
        "parameter_prefix": parameter_prefix,
        "length": float(first_step["length"]),
        "diameter": float(first_step["diameter"]),
        "radius": float(first_step["radius"]),
        "steps": steps,
        "step_count": len(steps),
        "total_length": total_length,
        "source_scenario": source_scenario,
        "source_params": dict(source_params) if isinstance(source_params, dict) else None,
        "source_preview": source_preview,
        "output_path": output_path,
        "visible": bool(params.get("visible", False)),
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def normalize_face_ring_groove_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    inner_diameter = _optional_positive_float(
        params,
        "inner_diameter",
        "inner_diameter",
        "inner_d",
        "id",
        "id1",
    )
    outer_diameter = _optional_positive_float(
        params,
        "outer_diameter",
        "outer_diameter",
        "outer_d",
        "od",
        "od1",
    )
    depth = _optional_positive_float(params, "depth", "depth", "dep", "h", "h1")
    if inner_diameter is None:
        raise ValueError("face_ring_groove requires inner_diameter")
    if outer_diameter is None:
        raise ValueError("face_ring_groove requires outer_diameter")
    if depth is None:
        raise ValueError("face_ring_groove requires depth")
    if float(outer_diameter) <= float(inner_diameter):
        raise ValueError("face_ring_groove requires outer_diameter greater than inner_diameter")

    inner_wall_angle_degrees = _normalize_face_ring_groove_wall_angle(
        params.get("inner_wall_angle_degrees")
        or params.get("inner_angle_degrees")
        or params.get("inner_angle")
    )
    outer_wall_angle_degrees = _normalize_face_ring_groove_wall_angle(
        params.get("outer_wall_angle_degrees")
        or params.get("outer_angle_degrees")
        or params.get("outer_angle")
    )
    inner_radius = float(inner_diameter) / 2.0
    outer_radius = float(outer_diameter) / 2.0
    depth_value = float(depth)
    bottom_inner_radius = inner_radius + depth_value * math.tan(math.radians(inner_wall_angle_degrees))
    bottom_outer_radius = outer_radius - depth_value * math.tan(math.radians(outer_wall_angle_degrees))
    if bottom_inner_radius <= 0.0:
        raise ValueError("face_ring_groove resolved bottom_inner_diameter must stay positive")
    if bottom_outer_radius <= bottom_inner_radius:
        raise ValueError("face_ring_groove resolved bottom_outer_diameter must stay greater than bottom_inner_diameter")

    angle_degrees = float(params.get("angle_degrees") or 360.0)
    if angle_degrees <= 0 or angle_degrees > 360:
        raise ValueError("angle_degrees must be in range (0, 360]")
    axial_direction = _normalize_internal_conical_step_axial_direction(
        params.get("axial_direction") or params.get("direction") or params.get("axial")
    )

    source_scenario = params.get("source_scenario") or params.get("base_scenario")
    source_params = params.get("source_params")
    source_preview = None
    if source_scenario is not None:
        source_scenario = _normalize_scenario(str(source_scenario))
        if source_scenario not in (
            "stepped_shaft",
            "external_conical_step",
            "internal_conical_step",
            "internal_cylindrical_step",
            "face_ring_groove",
        ):
            raise ValueError(
                "face_ring_groove source_scenario must be stepped_shaft, external_conical_step, internal_conical_step, internal_cylindrical_step or face_ring_groove"
            )
        if not isinstance(source_params, dict):
            raise ValueError("face_ring_groove source_params must be an object when source_scenario is provided")
        source_preview = preview_part_scenario(source_scenario, source_params)
    elif source_params is not None:
        raise ValueError("face_ring_groove source_params requires source_scenario")

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    sketch = normalize_sketch_options(params.get("sketch"))
    placement = normalize_placement_options(params.get("placement"))
    if placement["base"]["mode"] in ("csys", "csys_ref") and not placement["rotation_supported"]:
        raise ValueError("placement.axis_direction rotation is not supported yet; use a translated csys with the default axis direction")
    parameter_prefix = normalize_parameter_prefix(
        params.get("parameter_prefix") or params.get("parameter_namespace")
    )
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))

    return {
        "name": str(params.get("name") or "Face ring groove"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "plane": str(params.get("plane") or "XOY"),
        "axis": str(params.get("axis") or "OX"),
        "angle_degrees": angle_degrees,
        "axial_direction": axial_direction,
        "sketch": sketch,
        "placement": placement,
        "parameter_prefix": parameter_prefix,
        "inner_diameter": float(inner_diameter),
        "outer_diameter": float(outer_diameter),
        "bottom_inner_diameter": float(bottom_inner_radius * 2.0),
        "bottom_outer_diameter": float(bottom_outer_radius * 2.0),
        "inner_radius": inner_radius,
        "outer_radius": outer_radius,
        "bottom_inner_radius": float(bottom_inner_radius),
        "bottom_outer_radius": float(bottom_outer_radius),
        "depth": depth_value,
        "inner_wall_angle_degrees": float(inner_wall_angle_degrees),
        "outer_wall_angle_degrees": float(outer_wall_angle_degrees),
        "source_scenario": source_scenario,
        "source_params": dict(source_params) if isinstance(source_params, dict) else None,
        "source_preview": source_preview,
        "output_path": output_path,
        "visible": bool(params.get("visible", False)),
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def normalize_external_polygonal_step_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    diameter = _optional_positive_float(params, "diameter", "diameter", "d", "d1")
    length = _optional_positive_float(params, "length", "length", "l", "h")
    side_count_raw = (
        params.get("side_count")
        or params.get("sides_count")
        or params.get("sides")
        or params.get("faces_count")
        or params.get("n")
    )
    if diameter is None:
        raise ValueError("external_polygonal_step requires diameter")
    if length is None:
        raise ValueError("external_polygonal_step requires length")
    if side_count_raw in (None, ""):
        raise ValueError("external_polygonal_step requires side_count")
    try:
        side_count = int(side_count_raw)
    except Exception as exc:
        raise ValueError("external_polygonal_step side_count must be an integer") from exc
    if side_count < 3:
        raise ValueError("external_polygonal_step side_count must be at least 3")

    diameter_mode = _normalize_polygonal_step_diameter_mode(
        params.get("diameter_mode") or params.get("circle_mode") or params.get("mode")
    )
    axial_direction = _normalize_internal_conical_step_axial_direction(
        params.get("axial_direction") or params.get("direction") or params.get("axial") or "forward"
    )
    rotation_angle_degrees = float(params.get("rotation_angle_degrees") or params.get("rotation_angle") or 0.0)
    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    sketch = normalize_sketch_options(params.get("sketch"))
    placement = normalize_placement_options(params.get("placement"))
    if placement["base"]["mode"] in ("csys", "csys_ref") and not placement["rotation_supported"]:
        raise ValueError("placement.axis_direction rotation is not supported yet; use a translated csys with the default axis direction")
    parameter_prefix = normalize_parameter_prefix(
        params.get("parameter_prefix") or params.get("parameter_namespace")
    )
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))
    polygon_radius = _resolve_polygonal_step_radius(float(diameter), side_count, diameter_mode)

    return {
        "name": str(params.get("name") or "External polygonal step"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "plane": str(params.get("plane") or "YOZ"),
        "axis": str(params.get("axis") or "OX"),
        "sketch": sketch,
        "placement": placement,
        "parameter_prefix": parameter_prefix,
        "diameter": float(diameter),
        "length": float(length),
        "side_count": side_count,
        "diameter_mode": diameter_mode,
        "polygon_radius": polygon_radius,
        "rotation_angle_degrees": rotation_angle_degrees,
        "axial_direction": axial_direction,
        "operation_variable_bindings": _build_extrusion_length_variable_bindings(
            {"parameter_prefix": parameter_prefix}
        ),
        "output_path": output_path,
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def normalize_internal_polygonal_step_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    normalized = normalize_external_polygonal_step_params(params)
    source_scenario = params.get("source_scenario") or params.get("base_scenario")
    source_params = params.get("source_params")
    source_preview = None
    if source_scenario is not None:
        source_scenario = _normalize_scenario(str(source_scenario))
        if source_scenario not in (
            "stepped_shaft",
            "external_conical_step",
            "external_polygonal_step",
        ):
            raise ValueError(
                "internal_polygonal_step source_scenario must be stepped_shaft, external_conical_step or external_polygonal_step"
            )
        if not isinstance(source_params, dict):
            raise ValueError("internal_polygonal_step source_params must be an object when source_scenario is provided")
        source_preview = preview_part_scenario(source_scenario, source_params)
    elif source_params is not None:
        raise ValueError("internal_polygonal_step source_params requires source_scenario")

    normalized["name"] = str(params.get("name") or "Internal polygonal step")
    normalized["source_scenario"] = source_scenario
    normalized["source_params"] = dict(source_params) if isinstance(source_params, dict) else None
    normalized["source_preview"] = source_preview
    return normalized


def normalize_external_flat_step_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    diameter = _optional_positive_float(params, "diameter", "diameter", "d", "d1")
    length = _optional_positive_float(params, "length", "length", "l", "h")
    flat_depth = _optional_positive_float(
        params,
        "flat_depth",
        "flat_depth",
        "flat_height",
        "lyska_height",
        "f",
        "f1",
    )
    flats_count_raw = (
        params.get("flats_count")
        or params.get("flat_count")
        or params.get("count")
        or params.get("lyski_count")
        or 1
    )
    if diameter is None:
        raise ValueError("external_flat_step requires diameter")
    if length is None:
        raise ValueError("external_flat_step requires length")
    if flat_depth is None:
        raise ValueError("external_flat_step requires flat_depth")
    try:
        flats_count = int(flats_count_raw)
    except Exception as exc:
        raise ValueError("external_flat_step flats_count must be an integer") from exc
    if flats_count not in (1, 2):
        raise ValueError("external_flat_step flats_count must be 1 or 2")

    diameter_value = float(diameter)
    radius = diameter_value / 2.0
    flat_depth_value = float(flat_depth)
    if flat_depth_value <= 0.0 or flat_depth_value >= radius:
        raise ValueError("external_flat_step flat_depth must be greater than 0 and less than diameter / 2")
    flat_offset = radius - flat_depth_value
    chord_half = math.sqrt(max(radius * radius - flat_offset * flat_offset, 0.0))

    axial_direction = _normalize_internal_conical_step_axial_direction(
        params.get("axial_direction") or params.get("direction") or params.get("axial") or "forward"
    )
    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    sketch = normalize_sketch_options(params.get("sketch"))
    placement = normalize_placement_options(params.get("placement"))
    if placement["base"]["mode"] in ("csys", "csys_ref") and not placement["rotation_supported"]:
        raise ValueError("placement.axis_direction rotation is not supported yet; use a translated csys with the default axis direction")
    parameter_prefix = normalize_parameter_prefix(
        params.get("parameter_prefix") or params.get("parameter_namespace")
    )
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))

    return {
        "name": str(params.get("name") or "External flat step"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "plane": str(params.get("plane") or "YOZ"),
        "axis": str(params.get("axis") or "OX"),
        "sketch": sketch,
        "placement": placement,
        "parameter_prefix": parameter_prefix,
        "diameter": diameter_value,
        "radius": radius,
        "length": float(length),
        "flat_depth": flat_depth_value,
        "flat_offset": flat_offset,
        "chord_half": chord_half,
        "flats_count": flats_count,
        "axial_direction": axial_direction,
        "operation_variable_bindings": _build_extrusion_length_variable_bindings(
            {"parameter_prefix": parameter_prefix}
        ),
        "output_path": output_path,
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def normalize_internal_flat_step_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    normalized = normalize_external_flat_step_params(params)
    source_scenario = params.get("source_scenario") or params.get("base_scenario")
    source_params = params.get("source_params")
    source_preview = None
    if source_scenario is not None:
        source_scenario = _normalize_scenario(str(source_scenario))
        if source_scenario not in (
            "stepped_shaft",
            "external_conical_step",
            "external_polygonal_step",
            "external_flat_step",
        ):
            raise ValueError(
                "internal_flat_step source_scenario must be stepped_shaft, external_conical_step, external_polygonal_step or external_flat_step"
            )
        if not isinstance(source_params, dict):
            raise ValueError("internal_flat_step source_params must be an object when source_scenario is provided")
        source_preview = preview_part_scenario(source_scenario, source_params)
    elif source_params is not None:
        raise ValueError("internal_flat_step source_params requires source_scenario")

    normalized["name"] = str(params.get("name") or "Internal flat step")
    normalized["source_scenario"] = source_scenario
    normalized["source_params"] = dict(source_params) if isinstance(source_params, dict) else None
    normalized["source_preview"] = source_preview
    return normalized


def normalize_external_threaded_step_params(params: dict[str, Any]) -> dict[str, Any]:
    return _normalize_threaded_step_params(
        params,
        scenario="external_threaded_step",
        internal=False,
    )


def normalize_internal_threaded_step_params(params: dict[str, Any]) -> dict[str, Any]:
    return _normalize_threaded_step_params(
        params,
        scenario="internal_threaded_step",
        internal=True,
    )


def normalize_external_helical_thread_params(params: dict[str, Any]) -> dict[str, Any]:
    return _normalize_helical_thread_params(
        params,
        scenario="external_helical_thread",
        internal=False,
    )


def normalize_internal_helical_thread_params(params: dict[str, Any]) -> dict[str, Any]:
    return _normalize_helical_thread_params(
        params,
        scenario="internal_helical_thread",
        internal=True,
    )


def normalize_bolt_circle_holes_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    hole_diameter = _optional_positive_float(
        params,
        "hole_diameter",
        "hole_diameter",
        "diameter",
        "d",
        "d1",
    )
    depth = _optional_positive_float(params, "depth", "depth", "length", "l", "h")
    bolt_circle_diameter = _optional_positive_float(
        params,
        "bolt_circle_diameter",
        "bolt_circle_diameter",
        "pcd",
        "distribution_diameter",
        "circle_diameter",
    )
    count_raw = params.get("count") or params.get("hole_count") or params.get("instances")
    if hole_diameter is None:
        raise ValueError("bolt_circle_holes requires hole_diameter")
    if depth is None:
        raise ValueError("bolt_circle_holes requires depth")
    if bolt_circle_diameter is None:
        raise ValueError("bolt_circle_holes requires bolt_circle_diameter")
    if count_raw in (None, ""):
        raise ValueError("bolt_circle_holes requires count")
    try:
        count = int(count_raw)
    except Exception as exc:
        raise ValueError("bolt_circle_holes count must be an integer") from exc
    if count < 2:
        raise ValueError("bolt_circle_holes count must be at least 2")

    hole_diameter = float(hole_diameter)
    depth = float(depth)
    bolt_circle_diameter = float(bolt_circle_diameter)
    if bolt_circle_diameter <= hole_diameter:
        raise ValueError("bolt_circle_holes requires bolt_circle_diameter greater than hole_diameter")

    start_angle_degrees = float(
        params.get("start_angle_degrees")
        or params.get("start_angle")
        or params.get("angle")
        or 0.0
    )
    clockwise = bool(params.get("clockwise") or params.get("reverse_direction"))
    axial_direction = _normalize_internal_conical_step_axial_direction(
        params.get("axial_direction") or params.get("direction") or params.get("axial") or "backward"
    )

    source_scenario = params.get("source_scenario") or params.get("base_scenario")
    source_params = params.get("source_params")
    source_preview = None
    if source_scenario is not None:
        source_scenario = _normalize_scenario(str(source_scenario))
        if source_scenario not in (
            "stepped_shaft",
            "external_conical_step",
            "internal_conical_step",
            "internal_cylindrical_step",
            "face_ring_groove",
        ):
            raise ValueError(
                "bolt_circle_holes source_scenario must be stepped_shaft, external_conical_step, internal_conical_step, internal_cylindrical_step or face_ring_groove"
            )
        if not isinstance(source_params, dict):
            raise ValueError("bolt_circle_holes source_params must be an object when source_scenario is provided")
        source_preview = preview_part_scenario(source_scenario, source_params)
    elif source_params is not None:
        raise ValueError("bolt_circle_holes source_params requires source_scenario")

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    sketch = normalize_sketch_options(params.get("sketch"))
    placement = normalize_placement_options(params.get("placement"))
    if placement["base"]["mode"] in ("csys", "csys_ref") and not placement["rotation_supported"]:
        raise ValueError("placement.axis_direction rotation is not supported yet; use a translated csys with the default axis direction")
    parameter_prefix = normalize_parameter_prefix(
        params.get("parameter_prefix") or params.get("parameter_namespace")
    )
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))
    operation_label = build_operation_label(params.get("name") or "Bolt circle holes", parameter_prefix=parameter_prefix)
    pcd_variable = build_parameter_name("PCD", 1, prefix=parameter_prefix)
    count_variable = build_parameter_name("N", 1, prefix=parameter_prefix)
    angle_variable = build_parameter_name("A", 1, prefix=parameter_prefix)
    pattern_angle_step = 360.0 / float(count)
    pattern_variable_plan = [
        {
            "name": pcd_variable,
            "value": bolt_circle_diameter,
            "note": build_parameter_note(operation_label, "pattern", pcd_variable, "Bolt circle diameter"),
            "kind": "driving_pcd",
            "step_name": "pattern",
            "operation_label": operation_label,
            "external": True,
        },
        {
            "name": count_variable,
            "value": float(count),
            "note": build_parameter_note(operation_label, "pattern", count_variable, "Instance count"),
            "kind": "driving_pattern_count",
            "step_name": "pattern",
            "operation_label": operation_label,
            "external": True,
        },
        {
            "name": angle_variable,
            "value": pattern_angle_step,
            "note": build_parameter_note(operation_label, "pattern", angle_variable, "Angular step"),
            "kind": "driving_pattern_angle_step",
            "step_name": "pattern",
            "operation_label": operation_label,
            "external": True,
        },
    ]
    pattern_radius_y_factor = math.cos(math.radians(start_angle_degrees))
    pattern_radius_z_factor = math.sin(math.radians(start_angle_degrees))

    return {
        "name": str(params.get("name") or "Bolt circle holes"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "plane": str(params.get("plane") or "XOY"),
        "axis": str(params.get("axis") or "OX"),
        "sketch": sketch,
        "placement": placement,
        "parameter_prefix": parameter_prefix,
        "hole_diameter": hole_diameter,
        "depth": depth,
        "bolt_circle_diameter": bolt_circle_diameter,
        "count": count,
        "start_angle_degrees": start_angle_degrees,
        "pattern_variable_plan": pattern_variable_plan,
        "pattern_count_expression": count_variable,
        "pattern_step_expression": angle_variable,
        "first_hole_offset_expressions": [
            None,
            f"({pcd_variable} / 2) * {pattern_radius_y_factor:.12g}",
            f"({pcd_variable} / 2) * {pattern_radius_z_factor:.12g}",
        ],
        "pattern_operation_variable_bindings": _build_circular_pattern_variable_bindings(
            count_variable,
            angle_variable,
        ),
        "clockwise": clockwise,
        "axial_direction": axial_direction,
        "auxiliary_geometry_hidden": bool(params.get("auxiliary_geometry_hidden", True)),
        "source_scenario": source_scenario,
        "source_params": dict(source_params) if isinstance(source_params, dict) else None,
        "source_preview": source_preview,
        "output_path": output_path,
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def normalize_compression_spring_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    wire_diameter = _optional_positive_float(
        params,
        "wire_diameter",
        "wire_diameter",
        "wire",
        "bar_diameter",
        "wire_d",
    )
    if wire_diameter is None:
        raise ValueError("compression_spring requires wire_diameter")
    wire_diameter = float(wire_diameter)

    mean_diameter, diameter_mode = _resolve_compression_spring_mean_diameter(
        params,
        wire_diameter=wire_diameter,
    )
    free_length = _optional_positive_float(
        params,
        "free_length",
        "free_length",
        "length",
        "height",
        "h",
        "l",
        "L0",
    )
    standard_length = _optional_positive_float(
        params,
        "standard_length",
        "standard_length",
        "full_length",
        "overall_length",
        "L",
    )
    working_turns = _optional_positive_float(
        params,
        "working_turns",
        "working_turns",
        "active_turns",
        "working_coils",
        "working_turn_count",
        "turns",
        "turn_count",
        "n",
    )
    total_turns = _optional_non_negative_float(
        params,
        "total_turns",
        "total_turns",
        "coil_count",
        "total_coils",
        "Nt",
    )
    end_contract = _parse_compression_spring_end_contract(params)
    end_projection_mode = str(end_contract["end_projection_mode"])
    start_end_turns = float(end_contract["start_end_turns"])
    finish_end_turns = float(end_contract["finish_end_turns"])
    start_ground_turns = float(end_contract["start_ground_turns"])
    finish_ground_turns = float(end_contract["finish_ground_turns"])
    transition_fillet_radius_explicit = "transition_fillet_radius" in params
    transition_fillet_radius = _optional_non_negative_float(
        params,
        "transition_fillet_radius",
        "transition_fillet_radius",
    )
    if transition_fillet_radius is not None and transition_fillet_radius <= 1e-9:
        transition_fillet_radius = None
    transition_trim_length = _optional_non_negative_float(
        params,
        "transition_trim_length",
        "transition_trim_length",
    )
    if transition_trim_length is not None and transition_trim_length <= 1e-9:
        transition_trim_length = None
    transition_connect_tension = _optional_non_negative_float(
        params,
        "transition_connect_tension",
        "transition_connect_tension",
        "transition_tension",
    )
    end_turns_per_side = (
        float(end_contract["end_turns_per_side"])
        if end_contract["end_turns_per_side"] is not None
        else None
    )
    ground_turns_per_side = (
        float(end_contract["ground_turns_per_side"])
        if end_contract["ground_turns_per_side"] is not None
        else None
    )
    total_end_turns = start_end_turns + finish_end_turns

    if working_turns is None and total_turns is None:
        working_turns = 6.0
    if total_turns is not None and working_turns is None:
        derived_working_turns = float(total_turns) - total_end_turns
        if derived_working_turns <= 0.0:
            if end_projection_mode == "projected_to_v1_symmetric":
                raise ValueError("compression_spring total_turns must exceed twice the end_turns_per_side")
            raise ValueError("compression_spring total_turns must exceed start_end_turns + finish_end_turns")
        working_turns = derived_working_turns
    if working_turns is None:
        raise ValueError("compression_spring requires working_turns or total_turns")
    working_turns = _normalize_spring_fractional_turn(
        float(working_turns),
        field_name="working_turns",
    )
    if working_turns <= 0.0:
        raise ValueError("compression_spring working_turns must be a positive number")

    total_turns_resolved = working_turns + total_end_turns
    if total_turns is not None and abs(float(total_turns) - total_turns_resolved) > 1e-6:
        if end_projection_mode == "projected_to_v1_symmetric":
            raise ValueError("compression_spring total_turns must equal working_turns + 2 * end_turns_per_side")
        raise ValueError("compression_spring total_turns must equal working_turns + start_end_turns + finish_end_turns")

    if mean_diameter <= wire_diameter:
        raise ValueError("compression_spring requires mean_diameter greater than wire_diameter")
    length_model = _build_compression_spring_length_model(
        standard_length=float(standard_length) if standard_length is not None else None,
        centerline_length=float(free_length) if free_length is not None else None,
        wire_diameter=wire_diameter,
        start_end_turns=start_end_turns,
        finish_end_turns=finish_end_turns,
        start_ground_turns=start_ground_turns,
        finish_ground_turns=finish_ground_turns,
    )
    free_length = float(length_model["centerline_length"])
    minimum_length = total_end_turns * wire_diameter
    if free_length <= minimum_length:
        raise ValueError("compression_spring free_length is too small for the requested end turns")
    active_height = free_length - minimum_length
    pitch = active_height / working_turns
    if pitch < float(wire_diameter):
        raise ValueError("compression_spring requires pitch greater than or equal to wire_diameter")

    direction_value = str(
        params.get("turn_direction") or params.get("direction") or params.get("hand") or ""
    ).strip().lower().replace("-", "_").replace(" ", "_")
    left_hand_raw = params.get("left_hand")
    if left_hand_raw is None:
        left_hand = direction_value in {
            "left",
            "left_hand",
            "left_handed",
            "ccw",
            "counterclockwise",
        }
    else:
        left_hand = bool(left_hand_raw)
    direction = "left" if left_hand else "right"

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    sketch = normalize_sketch_options(params.get("sketch"))
    placement = normalize_placement_options(params.get("placement"))
    if placement["base"]["mode"] in ("csys", "csys_ref") and not placement["rotation_supported"]:
        raise ValueError(
            "placement.axis_direction rotation is not supported yet; "
            "use a translated csys with the default axis direction"
        )

    parameter_prefix = normalize_parameter_prefix(
        params.get("parameter_prefix") or params.get("parameter_namespace")
    )
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))
    operation_label = build_operation_label(
        params.get("name") or "Compression spring",
        parameter_prefix=parameter_prefix,
    )
    spring_diameter_variable = build_parameter_name("D", 1, prefix=parameter_prefix)
    wire_diameter_variable = build_parameter_name("WD", 1, prefix=parameter_prefix)
    pitch_variable = build_parameter_name("P", 1, prefix=parameter_prefix)
    standard_length_variable = build_parameter_name("L", 1, prefix=parameter_prefix)
    height_variable = build_parameter_name("H", 1, prefix=parameter_prefix)
    turns_variable = build_parameter_name("N", 1, prefix=parameter_prefix)
    transition_trim_length_variable = build_parameter_name("TL", 1, prefix=parameter_prefix)
    transition_connect_tension_variable = build_parameter_name("TN", 1, prefix=parameter_prefix)
    outer_diameter = float(mean_diameter) + float(wire_diameter)
    mean_diameter_expression = f"({spring_diameter_variable}) - ({wire_diameter_variable})"
    variable_plan = [
        {
            "name": spring_diameter_variable,
            "value": outer_diameter,
            "note": build_parameter_note(operation_label, "spring", spring_diameter_variable, "Outer coil diameter"),
            "kind": "driving_mean_diameter",
            "step_name": "spring",
            "operation_label": operation_label,
            "external": True,
        },
        {
            "name": wire_diameter_variable,
            "value": float(wire_diameter),
            "note": build_parameter_note(operation_label, "spring", wire_diameter_variable, "Wire diameter"),
            "kind": "driving_wire_diameter",
            "step_name": "spring",
            "operation_label": operation_label,
            "external": True,
        },
        {
            "name": pitch_variable,
            "value": float(pitch),
            "note": build_parameter_note(operation_label, "spring", pitch_variable, "Pitch of working turns"),
            "kind": "driving_pitch",
            "step_name": "spring",
            "operation_label": operation_label,
            "external": True,
        },
        *(
            [
                {
                    "name": standard_length_variable,
                    "value": float(length_model["standard_length"]),
                    "note": build_parameter_note(
                        operation_label,
                        "spring",
                        standard_length_variable,
                        "Standard full spring length",
                    ),
                    "kind": "driving_standard_length",
                    "step_name": "spring",
                    "operation_label": operation_label,
                    "external": True,
                }
            ]
            if length_model["source"] == "standard_length"
            else []
        ),
        {
            "name": height_variable,
            "value": float(free_length),
            "note": build_parameter_note(operation_label, "spring", height_variable, "Centerline construction height"),
            "kind": "derived_centerline_height"
            if length_model["source"] == "standard_length"
            else "driving_height",
            "step_name": "spring",
            "operation_label": operation_label,
            "external": length_model["source"] != "standard_length",
        },
        {
            "name": turns_variable,
            "value": float(working_turns),
            "note": build_parameter_note(operation_label, "spring", turns_variable, "Working turn count"),
            "kind": "driving_turn_count",
            "step_name": "spring",
            "operation_label": operation_label,
            "external": True,
        },
    ]
    end_turns_variable: str | None = None
    ground_turns_variable: str | None = None
    start_end_turns_variable: str | None = None
    finish_end_turns_variable: str | None = None
    start_ground_turns_variable: str | None = None
    finish_ground_turns_variable: str | None = None
    if end_contract["end_contract_mode"] == "v1_symmetric":
        end_turns_variable = build_parameter_name("N2", 1, prefix=parameter_prefix)
        ground_turns_variable = build_parameter_name("N3", 1, prefix=parameter_prefix)
        start_end_turns_variable = end_turns_variable
        finish_end_turns_variable = end_turns_variable
        start_ground_turns_variable = ground_turns_variable
        finish_ground_turns_variable = ground_turns_variable
        variable_plan.extend(
            [
                {
                    "name": end_turns_variable,
                    "value": float(end_turns_per_side or 0.0),
                    "note": build_parameter_note(
                        operation_label,
                        "spring",
                        end_turns_variable,
                        "Closed turns per side",
                    ),
                    "kind": "driving_end_turn_count_per_side",
                    "step_name": "spring",
                    "operation_label": operation_label,
                    "external": True,
                },
                {
                    "name": ground_turns_variable,
                    "value": float(ground_turns_per_side or 0.0),
                    "note": build_parameter_note(
                        operation_label,
                        "spring",
                        ground_turns_variable,
                        "Ground turns per side",
                    ),
                    "kind": "driving_ground_turn_count_per_side",
                    "step_name": "spring",
                    "operation_label": operation_label,
                    "external": True,
                },
            ]
        )
    else:
        start_end_turns_variable = build_parameter_name("N2", 1, prefix=parameter_prefix)
        finish_end_turns_variable = build_parameter_name("N2", 2, prefix=parameter_prefix)
        start_ground_turns_variable = build_parameter_name("N3", 1, prefix=parameter_prefix)
        finish_ground_turns_variable = build_parameter_name("N3", 2, prefix=parameter_prefix)
        variable_plan.extend(
            [
                {
                    "name": start_end_turns_variable,
                    "value": float(start_end_turns),
                    "note": build_parameter_note(
                        operation_label,
                        "spring",
                        start_end_turns_variable,
                        "Closed start-end turns",
                    ),
                    "kind": "driving_start_end_turn_count",
                    "step_name": "spring",
                    "operation_label": operation_label,
                    "external": True,
                },
                {
                    "name": finish_end_turns_variable,
                    "value": float(finish_end_turns),
                    "note": build_parameter_note(
                        operation_label,
                        "spring",
                        finish_end_turns_variable,
                        "Closed finish-end turns",
                    ),
                    "kind": "driving_finish_end_turn_count",
                    "step_name": "spring",
                    "operation_label": operation_label,
                    "external": True,
                },
                {
                    "name": start_ground_turns_variable,
                    "value": float(start_ground_turns),
                    "note": build_parameter_note(
                        operation_label,
                        "spring",
                        start_ground_turns_variable,
                        "Grounded start-end turns",
                    ),
                    "kind": "driving_start_ground_turn_count",
                    "step_name": "spring",
                    "operation_label": operation_label,
                    "external": True,
                },
                {
                    "name": finish_ground_turns_variable,
                    "value": float(finish_ground_turns),
                    "note": build_parameter_note(
                        operation_label,
                        "spring",
                        finish_ground_turns_variable,
                        "Grounded finish-end turns",
                    ),
                    "kind": "driving_finish_ground_turn_count",
                    "step_name": "spring",
                    "operation_label": operation_label,
                    "external": True,
                },
            ]
        )

    sketch.setdefault("parameterization_order", "staged")

    mean_diameter = float(mean_diameter)
    pitch = float(pitch)
    turns = float(working_turns)
    start_end_turn_span = start_end_turns * wire_diameter
    finish_end_turn_span = finish_end_turns * wire_diameter
    active_height = pitch * turns
    if (
        end_projection_mode == "projected_to_v1_symmetric"
        and start_end_turns_variable is not None
        and finish_end_turns_variable is not None
    ):
        start_end_height_expression = f"{start_end_turns_variable} * {wire_diameter_variable}"
        finish_end_height_expression = f"{finish_end_turns_variable} * {wire_diameter_variable}"
        if end_contract["end_contract_mode"] == "v1_symmetric":
            active_height_expression = f"{height_variable} - 2 * ({start_end_height_expression})"
        else:
            active_height_expression = (
                f"{height_variable} - (({start_end_height_expression}) + ({finish_end_height_expression}))"
            )
        working_start_offset_expression = (
            start_end_height_expression if start_end_turn_span > 1e-9 else None
        )
        finish_start_offset_expression = (
            f"({start_end_height_expression}) + ({active_height_expression})"
            if finish_end_turn_span > 1e-9
            else None
        )
        working_rotation_turns_expression = (
            f"{start_end_turns_variable}" if start_end_turn_span > 1e-9 else None
        )
        finish_rotation_turns_expression = (
            f"({start_end_turns_variable}) + (({active_height_expression}) / ({pitch_variable}))"
            if finish_end_turn_span > 1e-9
            else None
        )
    else:
        start_end_height_expression = (
            _format_compression_spring_expression_literal(start_end_turn_span)
            if start_end_turn_span > 1e-9
            else None
        )
        finish_end_height_expression = (
            _format_compression_spring_expression_literal(finish_end_turn_span)
            if finish_end_turn_span > 1e-9
            else None
        )
        active_height_expression = _format_compression_spring_expression_literal(active_height)
        working_start_offset_expression = (
            _format_compression_spring_expression_literal(start_end_turn_span)
            if start_end_turn_span > 1e-9
            else None
        )
        finish_start_offset_expression = (
            _format_compression_spring_expression_literal(start_end_turn_span + active_height)
            if finish_end_turn_span > 1e-9
            else None
        )
        working_rotation_turns_expression = (
            _format_compression_spring_expression_literal(start_end_turns)
            if start_end_turn_span > 1e-9
            else None
        )
        finish_rotation_turns_expression = (
            _format_compression_spring_expression_literal(start_end_turns + turns)
            if finish_end_turn_span > 1e-9
            else None
        )
    phase_multiplier = 360.0 if left_hand else -360.0
    start_phase_raw = _optional_float(
        params,
        "start_phase_degrees",
        "start_phase_degrees",
        "initial_phase_degrees",
        "start_angle_degrees",
        "start_angle",
    )
    if start_phase_raw is None:
        start_phase_raw = 90.0
    start_phase_degrees = _normalize_spring_phase_degrees(start_phase_raw)
    start_turning_angle_degrees = _normalize_spring_turning_angle_degrees(start_phase_raw)
    first_segment_initial_rotation_degrees = _resolve_spring_segment_initial_angle_degrees(
        start_phase_raw,
        turns_before=0.0,
        left_hand=left_hand,
    )
    first_segment_rotation_expression = (
        _format_compression_spring_expression_literal(first_segment_initial_rotation_degrees)
        if abs(first_segment_initial_rotation_degrees) > 1e-9
        else None
    )
    transfer_first_segment_half_turn = (
        not left_hand
        and abs(_normalize_spring_turning_angle_degrees(first_segment_initial_rotation_degrees) - 180.0) <= 1e-9
    )
    if transfer_first_segment_half_turn:
        first_segment_rotation_expression = None
    working_rotation_expression = _build_spring_rotation_expression_from_turns(
        working_rotation_turns_expression,
        start_phase_degrees=start_phase_raw,
        left_hand=left_hand,
        extra_angle_offset_degrees=180.0 if transfer_first_segment_half_turn else 0.0,
    )
    finish_rotation_expression = _build_spring_rotation_expression_from_turns(
        finish_rotation_turns_expression,
        start_phase_degrees=start_phase_raw,
        left_hand=left_hand,
        extra_angle_offset_degrees=180.0 if transfer_first_segment_half_turn else 0.0,
    )
    segment_plan: list[dict[str, Any]] = []
    segment_phase_raw = float(start_phase_raw)
    if start_end_turn_span > 1e-9:
        segment_end_phase_raw = segment_phase_raw + phase_multiplier * (start_end_turn_span / wire_diameter)
        segment_plan.append(
            {
                "role": "start_end",
                "label": "start closed-end",
                "description": "Create the closed start turns",
                "path_name": "spring_start_end_path",
                "profile_name": "spring_start_end_profile",
                "sweep_name": "spring_start_end_body",
                "height": start_end_turn_span,
                "height_expression": start_end_height_expression,
                "pitch": wire_diameter,
                "pitch_expression": wire_diameter_variable,
                "turns": float(start_end_turns),
                "start_offset": 0.0,
                "start_offset_expression": None,
                "phase_degrees": _normalize_spring_phase_degrees(segment_phase_raw),
                "turning_angle_degrees": 0.0,
                "orientation_angle_degrees": 0.0,
                "anchor_rotation_expression": first_segment_rotation_expression,
                "angle_application_mode": "orientation",
                "end_phase_degrees": _normalize_spring_phase_degrees(segment_end_phase_raw),
                "start_angle_degrees_raw": float(segment_phase_raw),
                "end_angle_degrees_raw": float(segment_end_phase_raw),
                "turn_delta_degrees": float(segment_end_phase_raw - segment_phase_raw),
                "operation_variable_bindings": _build_spring_spiral_variable_bindings(
                    mean_diameter_expression,
                    wire_diameter_variable,
                    start_end_height_expression or _format_compression_spring_expression_literal(start_end_turn_span),
                ),
            }
        )
        segment_phase_raw = segment_end_phase_raw
    segment_end_phase_raw = segment_phase_raw + phase_multiplier * (active_height / pitch)
    segment_plan.append(
        {
            "role": "working",
            "label": "working",
            "description": "Create the working turns with the specified pitch",
            "path_name": "spring_working_path",
            "profile_name": "spring_working_profile",
            "sweep_name": "spring_working_body",
            "height": active_height,
            "height_expression": active_height_expression,
            "pitch": pitch,
            "pitch_expression": pitch_variable,
            "turns": turns,
            "start_offset": start_end_turn_span,
            "start_offset_expression": working_start_offset_expression,
            "phase_degrees": _normalize_spring_phase_degrees(segment_phase_raw),
            "turning_angle_degrees": 0.0,
            "orientation_angle_degrees": 0.0,
            "anchor_rotation_expression": (
                first_segment_rotation_expression if not segment_plan else working_rotation_expression
            ),
            "angle_application_mode": "orientation",
            "end_phase_degrees": _normalize_spring_phase_degrees(segment_end_phase_raw),
            "start_angle_degrees_raw": float(segment_phase_raw),
            "end_angle_degrees_raw": float(segment_end_phase_raw),
            "turn_delta_degrees": float(segment_end_phase_raw - segment_phase_raw),
            "operation_variable_bindings": _build_spring_spiral_variable_bindings(
                mean_diameter_expression,
                pitch_variable,
                active_height_expression,
            ),
        }
    )
    segment_phase_raw = segment_end_phase_raw
    if finish_end_turn_span > 1e-9:
        segment_end_phase_raw = segment_phase_raw + phase_multiplier * (finish_end_turn_span / wire_diameter)
        segment_plan.append(
            {
                "role": "finish_end",
                "label": "finish closed-end",
                "description": "Create the closed finish turns",
                "path_name": "spring_finish_end_path",
                "profile_name": "spring_finish_end_profile",
                "sweep_name": "spring_finish_end_body",
                "height": finish_end_turn_span,
                "height_expression": finish_end_height_expression,
                "pitch": wire_diameter,
                "pitch_expression": wire_diameter_variable,
                "turns": float(finish_end_turns),
                "start_offset": start_end_turn_span + active_height,
                "start_offset_expression": finish_start_offset_expression,
                "phase_degrees": _normalize_spring_phase_degrees(segment_phase_raw),
                "turning_angle_degrees": 0.0,
                "orientation_angle_degrees": 0.0,
                "anchor_rotation_expression": (
                    first_segment_rotation_expression
                    if not segment_plan
                    else finish_rotation_expression
                ),
                "angle_application_mode": "orientation",
                "end_phase_degrees": _normalize_spring_phase_degrees(segment_end_phase_raw),
                "start_angle_degrees_raw": float(segment_phase_raw),
                "end_angle_degrees_raw": float(segment_end_phase_raw),
                "turn_delta_degrees": float(segment_end_phase_raw - segment_phase_raw),
                "operation_variable_bindings": _build_spring_spiral_variable_bindings(
                    mean_diameter_expression,
                    wire_diameter_variable,
                    finish_end_height_expression
                    or _format_compression_spring_expression_literal(finish_end_turn_span),
                ),
            }
        )
    path_verification = _build_compression_spring_path_verification(
        segment_plan,
        mean_radius=mean_diameter / 2.0,
    )
    if (
        transition_fillet_radius is None
        and not transition_fillet_radius_explicit
        and len(segment_plan) >= 2
    ):
        transition_fillet_radius = _resolve_compression_spring_transition_fillet_radius(
            wire_diameter=wire_diameter,
        )
    connector_plan: list[dict[str, Any]] = []
    resolved_transition_trim_length = transition_trim_length
    resolved_transition_connect_tension: float | None = transition_connect_tension
    transition_trim_length_expression: str | None = None
    transition_connect_tension_expression: str | None = None
    if transition_fillet_radius is not None and len(segment_plan) >= 2:
        resolved_transition_trim_length = (
            float(transition_trim_length)
            if transition_trim_length is not None
            else _resolve_compression_spring_transition_trim_length(
                mean_diameter=mean_diameter,
                wire_diameter=wire_diameter,
                pitch=pitch,
            )
        )
        if transition_trim_length is not None:
            transition_trim_length_expression = _format_compression_spring_expression_literal(
                resolved_transition_trim_length
            )
        else:
            base_trim_length_expression = _compression_spring_expression_max(
                f"0.85 * ({wire_diameter_variable})",
                f"0.46 * sqrt(({mean_diameter_expression}) * ({wire_diameter_variable}))",
            )
            transition_trim_length_expression = _compression_spring_expression_min(
                f"0.85 * ({pitch_variable})",
                base_trim_length_expression,
            )
        resolved_transition_connect_tension = (
            float(transition_connect_tension)
            if transition_connect_tension is not None
            else _resolve_compression_spring_transition_connect_tension(
                mean_diameter=mean_diameter,
                wire_diameter=wire_diameter,
                pitch=pitch,
            )
        )
        if transition_connect_tension is not None:
            transition_connect_tension_expression = _format_compression_spring_expression_literal(
                resolved_transition_connect_tension
            )
        else:
            base_tension_expression = (
                f"2.03 * sqrt("
                f"{_compression_spring_expression_non_negative(f'({mean_diameter_expression}) - 15')}"
                f")"
            )
            pitch_adjustment_expression = _compression_spring_expression_min(
                "0",
                f"0.8 * ((({pitch_variable}) / ({wire_diameter_variable})) - 2)",
            )
            transition_connect_tension_expression = _compression_spring_expression_min(
                "15",
                _compression_spring_expression_non_negative(
                    f"({base_tension_expression}) + ({pitch_adjustment_expression})"
                ),
            )
        variable_plan.extend(
            [
                {
                    "name": transition_trim_length_variable,
                    "value": float(resolved_transition_trim_length),
                    "expression": transition_trim_length_expression,
                    "note": build_parameter_note(
                        operation_label,
                        "spring",
                        transition_trim_length_variable,
                        "Transition trim length",
                    ),
                    "kind": "derived_transition_trim_length",
                    "step_name": "spring",
                    "operation_label": operation_label,
                    "external": True,
                },
                {
                    "name": transition_connect_tension_variable,
                    "value": float(resolved_transition_connect_tension),
                    "expression": transition_connect_tension_expression,
                    "note": build_parameter_note(
                        operation_label,
                        "spring",
                        transition_connect_tension_variable,
                        "Transition connect-curve tension",
                    ),
                    "kind": "derived_transition_connect_tension",
                    "step_name": "spring",
                    "operation_label": operation_label,
                    "external": True,
                },
            ]
        )

        def _build_trimmed_transition_connector(
            previous_segment: dict[str, Any],
            current_segment: dict[str, Any],
            *,
            curve1_source_path_name: str | None = None,
        ) -> dict[str, Any]:
            connector_role = f"{str(previous_segment['role'])}_to_{str(current_segment['role'])}"
            curve1_trim = normalize_trimmed_curve_params(
                {
                    "name": "spring_%s_curve1_local_path" % connector_role,
                    "point_name": "spring_%s_curve1_local_point" % connector_role,
                    "offset": resolved_transition_trim_length,
                    "direction": False,
                    "sense": True,
                    "offset_type": 2,
                }
            )
            curve1_trim["point_operation_variable_bindings"] = _build_transition_point_variable_bindings(
                transition_trim_length_variable,
                f"{connector_role}_curve1_trim_offset",
            )
            curve2_trim = normalize_trimmed_curve_params(
                {
                    "name": "spring_%s_curve2_local_path" % connector_role,
                    "point_name": "spring_%s_curve2_local_point" % connector_role,
                    "offset": resolved_transition_trim_length,
                    "direction": True,
                    "sense": False,
                    "offset_type": 2,
                }
            )
            curve2_trim["point_operation_variable_bindings"] = _build_transition_point_variable_bindings(
                transition_trim_length_variable,
                f"{connector_role}_curve2_trim_offset",
            )
            connect_curve = normalize_connect_curve_params(
                {
                    "name": "spring_%s_connect_path" % connector_role,
                    "curve1_connect_vertex": False,
                    "curve2_connect_vertex": True,
                    "curve1_connect_type": "smooth",
                    "curve2_connect_type": "smooth",
                    "tension": resolved_transition_connect_tension,
                }
            )
            connect_curve["operation_variable_bindings"] = (
                _build_transition_connect_curve_variable_bindings(
                    transition_connect_tension_variable,
                    f"{connector_role}_connect_curve_tension",
                )
            )
            return {
                "builder": "trimmed_connect_curve",
                "role": connector_role,
                "label": connector_role.replace("_", " "),
                "description": (
                    "Trim the joint between %s and %s and connect the local spiral ends with a smooth bridge curve"
                    % (previous_segment["label"], current_segment["label"])
                ),
                "path_name": connect_curve["name"],
                "curve1_path_name": curve1_source_path_name or str(previous_segment["path_name"]),
                "curve2_path_name": str(current_segment["path_name"]),
                "curve1_trim": curve1_trim,
                "curve2_trim": curve2_trim,
                "connect_curve": connect_curve,
                "sequence_curve1_path_name": curve1_trim["name"],
                "sequence_curve2_path_name": curve2_trim["name"],
                "radius": float(transition_fillet_radius),
                "trim_length": resolved_transition_trim_length,
                "trim_length_expression": transition_trim_length_variable,
                "tension": resolved_transition_connect_tension,
                "tension_expression": transition_connect_tension_variable,
            }

        prior_connector_curve2_path_name: str | None = None
        for segment_index in range(len(segment_plan) - 1):
            previous_segment = segment_plan[segment_index]
            current_segment = segment_plan[segment_index + 1]
            connector = _build_trimmed_transition_connector(
                previous_segment,
                current_segment,
                curve1_source_path_name=prior_connector_curve2_path_name,
            )
            connector_plan.append(connector)
            prior_connector_curve2_path_name = str(connector["sequence_curve2_path_name"])
    full_path_sequence: list[str] = []
    if connector_plan:
        if all(
            str(connector.get("builder") or "") == "trimmed_connect_curve"
            for connector in connector_plan
        ):
            full_path_sequence.append(str(connector_plan[0]["sequence_curve1_path_name"]))
            for index, connector in enumerate(connector_plan):
                full_path_sequence.append(str(connector["path_name"]))
                if index + 1 < len(connector_plan):
                    full_path_sequence.append(
                        str(connector_plan[index + 1]["sequence_curve1_path_name"])
                    )
                else:
                    full_path_sequence.append(str(connector["sequence_curve2_path_name"]))
        else:
            full_path_sequence.append(str(segment_plan[0]["path_name"]))
            for index, connector in enumerate(connector_plan):
                full_path_sequence.append(str(connector["path_name"]))
                full_path_sequence.append(str(segment_plan[index + 1]["path_name"]))
    else:
        full_path_sequence = [str(segment["path_name"]) for segment in segment_plan]
    length_model["standard_length_expression"] = (
        standard_length_variable if length_model["source"] == "standard_length" else None
    )
    length_model["centerline_height_variable"] = height_variable
    if length_model["source"] == "standard_length":
        if start_ground_turns > 1e-9 or finish_ground_turns > 1e-9:
            length_model["centerline_height_expression"] = (
                f"{standard_length_variable} - {wire_diameter_variable} + "
                f"(({start_ground_turns_variable} + {finish_ground_turns_variable}) * {wire_diameter_variable})"
            )
        else:
            length_model["centerline_height_expression"] = f"{standard_length_variable} - {wire_diameter_variable}"
    ground_trim_plan = _build_compression_spring_ground_trim_plan(
        enabled=start_ground_turns > 1e-9 or finish_ground_turns > 1e-9,
        height_expression=height_variable,
        wire_diameter_expression=wire_diameter_variable,
        start_end_turns_expression=start_end_turns_variable,
        finish_end_turns_expression=finish_end_turns_variable,
        start_ground_turns_expression=(
            start_ground_turns_variable
            if end_contract["end_contract_mode"] == "v2_per_end"
            else ground_turns_variable
        ),
        finish_ground_turns_expression=(
            finish_ground_turns_variable
            if end_contract["end_contract_mode"] == "v2_per_end"
            else ground_turns_variable
        ),
        start_ground_turns=start_ground_turns,
        finish_ground_turns=finish_ground_turns,
        axis=direction,
    )
    profile_sketch_constraints = _build_compression_spring_profile_sketch_constraints()
    profile_sketch_dimensions = _build_compression_spring_profile_sketch_dimensions(
        spring_diameter_variable,
        wire_diameter_variable,
    )

    return {
        "name": str(params.get("name") or "Compression spring"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "plane": str(params.get("plane") or "XOY"),
        "axis": str(params.get("axis") or "OX"),
        "sketch": sketch,
        "placement": placement,
        "parameter_prefix": parameter_prefix,
        "diameter_mode": diameter_mode,
        "mean_diameter": mean_diameter,
        "outer_diameter": outer_diameter,
        "inner_diameter": mean_diameter - wire_diameter,
        "wire_diameter": wire_diameter,
        "pitch": pitch,
        "standard_length": length_model["standard_length"],
        "length_model": length_model,
        "height": free_length,
        "free_length": free_length,
        "turns": turns,
        "working_turns": turns,
        "total_turns": total_turns_resolved,
        "end_turns_per_side": float(end_turns_per_side) if end_turns_per_side is not None else None,
        "ground_turns_per_side": (
            float(ground_turns_per_side) if ground_turns_per_side is not None else None
        ),
        "transition_fillet_radius": transition_fillet_radius,
        "transition_trim_length": resolved_transition_trim_length,
        "transition_trim_length_expression": transition_trim_length_expression,
        "transition_trim_length_variable": (
            transition_trim_length_variable if transition_trim_length_expression else None
        ),
        "transition_connect_tension": resolved_transition_connect_tension,
        "transition_connect_tension_expression": transition_connect_tension_expression,
        "transition_connect_tension_variable": (
            transition_connect_tension_variable if transition_connect_tension_expression else None
        ),
        "end_contract_mode": str(end_contract["end_contract_mode"]),
        "end_projection_mode": end_projection_mode,
        "start_end_turns": start_end_turns,
        "finish_end_turns": finish_end_turns,
        "start_ground_turns": start_ground_turns,
        "finish_ground_turns": finish_ground_turns,
        "start_end_kind": str(end_contract["start_end_kind"]),
        "finish_end_kind": str(end_contract["finish_end_kind"]),
        "active_height": active_height,
        "end_turn_height": max(start_end_turn_span, finish_end_turn_span),
        "start_end_turn_height": start_end_turn_span,
        "finish_end_turn_height": finish_end_turn_span,
        "segment_plan": segment_plan,
        "connector_plan": connector_plan,
        "ground_trim_plan": ground_trim_plan,
        "full_path_sequence": full_path_sequence,
        "start_phase_degrees": start_phase_degrees,
        "start_turning_angle_degrees": start_turning_angle_degrees,
        "spiral_diameter": mean_diameter,
        "path_verification": path_verification,
        "turn_direction": direction,
        "left_hand": left_hand,
        "variable_plan": variable_plan,
        "mean_diameter_expression": mean_diameter_expression,
        "outer_diameter_expression": spring_diameter_variable,
        "wire_diameter_expression": wire_diameter_variable,
        "pitch_expression": pitch_variable,
        "height_expression": height_variable,
        "turns_expression": turns_variable,
        "end_turns_expression": end_turns_variable,
        "ground_turns_expression": ground_turns_variable,
        "start_end_turns_expression": (
            start_end_turns_variable if end_contract["end_contract_mode"] == "v2_per_end" else None
        ),
        "finish_end_turns_expression": (
            finish_end_turns_variable if end_contract["end_contract_mode"] == "v2_per_end" else None
        ),
        "start_ground_turns_expression": (
            start_ground_turns_variable
            if end_contract["end_contract_mode"] == "v2_per_end"
            else None
        ),
        "finish_ground_turns_expression": (
            finish_ground_turns_variable
            if end_contract["end_contract_mode"] == "v2_per_end"
            else None
        ),
        "profile_name": "spring_wire_profile",
        "profile_sketch_constraints": profile_sketch_constraints,
        "profile_sketch_dimensions": profile_sketch_dimensions,
        "profile_sketch_target_state": "fully_defined",
        "sweep_name": "spring_body",
        "sweep_alignment_mode": "orthogonal_to_path",
        "auxiliary_geometry_hidden": bool(params.get("auxiliary_geometry_hidden", True)),
        "live_supported": True,
        "output_path": output_path,
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def _build_compression_spring_ground_trim_plan(
    *,
    enabled: bool,
    height_expression: str,
    wire_diameter_expression: str,
    start_end_turns_expression: str | None,
    finish_end_turns_expression: str | None,
    start_ground_turns_expression: str | None,
    finish_ground_turns_expression: str | None,
    start_ground_turns: float,
    finish_ground_turns: float,
    axis: str,
) -> dict[str, Any]:
    """Describe future end-grinding section cuts without executing unsupported bridge geometry."""
    if not enabled:
        return {
            "enabled": False,
            "status": "not_requested",
            "height_reference": "centerline_start_to_centerline_finish",
            "operations": [],
        }

    start_ground_expression = start_ground_turns_expression or _format_compression_spring_expression_literal(
        start_ground_turns
    )
    finish_ground_expression = finish_ground_turns_expression or _format_compression_spring_expression_literal(
        finish_ground_turns
    )
    start_end_expression = start_end_turns_expression or "start_end_turns"
    finish_end_expression = finish_end_turns_expression or "finish_end_turns"
    start_depth_expression = (
        f"-(({start_end_expression} - {start_ground_expression} + 0.5) * {wire_diameter_expression})"
    )
    finish_depth_expression = (
        f"(({finish_end_expression} - {finish_ground_expression} + 0.5) * {wire_diameter_expression})"
    )
    operations: list[dict[str, Any]] = []
    if start_ground_turns > 1e-9:
        operations.append(
            {
                "operation": "section_by_surface",
                "role": "start_ground_trim",
                "surface_reference": "start_end_to_working_joint_plane",
                "offset_expression": start_depth_expression,
                "normal_direction": "axis_negative",
            }
        )
    if finish_ground_turns > 1e-9:
        operations.append(
            {
                "operation": "section_by_surface",
                "role": "finish_ground_trim",
                "surface_reference": "working_to_finish_end_joint_plane",
                "offset_expression": finish_depth_expression,
                "normal_direction": "axis_positive",
            }
        )
    return {
        "enabled": True,
        "status": "planned_bridge_action_required",
        "bridge_action_required": "section_by_surface",
        "height_reference": "centerline_start_to_centerline_finish",
        "full_height_status": "unverified_against_standard",
        "axis": axis,
        "offset_formula_model": "joint_based_end_turns_minus_ground_turns_times_wire_diameter",
        "standards_link_variables": {
            "start_end_turns": start_end_expression,
            "finish_end_turns": finish_end_expression,
            "start_ground_turns": start_ground_expression,
            "finish_ground_turns": finish_ground_expression,
            "wire_diameter": wire_diameter_expression,
            "height": height_expression,
        },
        "operations": operations,
    }


def _build_compression_spring_length_model(
    *,
    standard_length: float | None,
    centerline_length: float | None,
    wire_diameter: float,
    start_end_turns: float,
    finish_end_turns: float,
    start_ground_turns: float,
    finish_ground_turns: float,
) -> dict[str, Any]:
    if standard_length is None:
        if centerline_length is None:
            raise ValueError("compression_spring requires free_length or standard_length")
        return {
            "source": "centerline_length",
            "standard_length": None,
            "centerline_length": float(centerline_length),
            "height_reference": "centerline_start_to_centerline_finish",
            "centerline_height_expression": "H1",
        }

    if centerline_length is not None:
        raise ValueError("Use either free_length/height or standard_length/L, not both")

    if start_ground_turns > 1e-9 or finish_ground_turns > 1e-9:
        centerline_offset = (-1.0 + float(start_ground_turns) + float(finish_ground_turns)) * float(wire_diameter)
        expression = "L1 - WD1 + ((N31 + N32) * WD1)"
        reference = "ground_cut_to_ground_cut"
    else:
        centerline_offset = -float(wire_diameter)
        expression = "L1 - WD1"
        reference = "outer_extreme_to_outer_extreme"

    centerline_length_value = float(standard_length) + centerline_offset
    if centerline_length_value <= 0.0:
        raise ValueError("standard_length produces a non-positive centerline construction height")
    return {
        "source": "standard_length",
        "standard_length": float(standard_length),
        "centerline_length": centerline_length_value,
        "height_reference": reference,
        "centerline_height_expression": expression,
        "centerline_offset": centerline_offset,
        "full_height_status": "standard_length_drives_centerline_height",
    }


def normalize_point_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    mode = _normalize_point_mode(params.get("mode") or params.get("type") or "global")
    reference_payload = params.get("reference") or params.get("base") or params.get("ref")
    if reference_payload is not None and not isinstance(reference_payload, dict):
        raise ValueError("reference must be an object")
    reference = dict(reference_payload) if isinstance(reference_payload, dict) else None

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    material_payload = resolve_material_payload(params.get("material"), params.get("density"))
    reference_origin = None
    reference_name = ""
    offset = [0.0, 0.0, 0.0]
    reference_selector = ""
    source_scenario = ""
    live_supported = mode in ("global", "center_of_object", "offset_from_point")
    parameter_prefix = normalize_parameter_prefix(params.get("parameter_prefix") or params.get("parameter_namespace"))
    if mode == "global":
        origin = _normalize_xyz_triplet(params.get("origin") or params.get("point") or params)
    elif mode == "offset_from_point":
        if reference is None:
            raise ValueError("offset_from_point mode requires reference")
        reference_output_ref = str(reference.get("output_ref") or reference.get("token") or reference.get("ref") or "").strip()
        reference_origin = _normalize_xyz_triplet(
            reference.get("origin") or reference.get("point") or reference.get("position"),
            field_name="reference.origin",
        )
        reference_name = str(reference.get("name") or reference.get("point_name") or "PT_BASE")
        offset = _normalize_offset_triplet(params.get("offset") or params)
        origin = [
            float(reference_origin[0] + offset[0]),
            float(reference_origin[1] + offset[1]),
            float(reference_origin[2] + offset[2]),
        ]
    elif mode == "center_of_object":
        if reference is None:
            raise ValueError("center_of_object mode requires reference")
        reference_output_ref = str(reference.get("output_ref") or reference.get("token") or reference.get("ref") or "").strip()
        source_operation = str(reference.get("source_operation") or reference.get("operation") or "").strip()
        source_scenario = _normalize_scenario(reference.get("source_scenario") or reference.get("scenario") or "stepped_shaft")
        if source_scenario not in _REVOLVED_FACE_REFERENCE_SCENARIOS:
            raise ValueError(
                "center_of_object currently supports only source_scenario=%s"
                % ",".join(_REVOLVED_FACE_REFERENCE_SCENARIOS)
            )
        source_preview = _normalize_feature_reference_preview(
            reference,
            field_name="center_of_object",
            source_scenario=source_scenario,
        )
        reference_selector = _normalize_feature_reference_selector(
            reference.get("selector") or _default_feature_face_selector(source_scenario),
            source_scenario=source_scenario,
            source_preview=source_preview,
            field_name="center_of_object.reference.selector",
        )
        reference = {
            "selector": reference_selector,
            "source_scenario": source_scenario,
            "source_preview": source_preview,
        }
        if reference_output_ref:
            reference["output_ref"] = reference_output_ref
        if source_operation:
            reference["source_operation"] = source_operation
        reference_name = reference_selector
        reference_origin = _resolve_feature_selector_origin(source_scenario, reference_selector, source_preview)
        origin = list(reference_origin)
    else:
        raise ValueError(f"Unsupported point mode for now: {mode}")

    if mode == "offset_from_point" and reference is not None:
        normalized_reference = {
            "name": reference_name,
            "origin": list(reference_origin) if isinstance(reference_origin, list) else None,
        }
        if reference_output_ref:
            normalized_reference["output_ref"] = reference_output_ref
        reference = normalized_reference

    return {
        "name": str(params.get("name") or "Reference point"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "mode": mode,
        "point_name": str(params.get("point_name") or params.get("anchor_name") or params.get("name") or "PT1"),
        "origin": origin,
        "reference": reference,
        "reference_origin": reference_origin,
        "reference_name": reference_name,
        "offset": offset,
        "reference_selector": reference_selector,
        "source_scenario": source_scenario,
        "live_supported": live_supported,
        "parameter_prefix": parameter_prefix,
        "output_path": output_path,
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def normalize_lcs_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    mode = _normalize_lcs_mode(params.get("mode") or params.get("type") or "global")
    reference_payload = params.get("reference") or params.get("base") or params.get("ref")
    if reference_payload is not None and not isinstance(reference_payload, dict):
        raise ValueError("reference must be an object")
    reference = dict(reference_payload) if isinstance(reference_payload, dict) else None

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    rotation = _normalize_rotation_triplet(params.get("rotation") or params)
    only_outer_contour = bool(params.get("only_outer_contour") or (reference or {}).get("only_outer_contour"))

    origin = [0.0, 0.0, 0.0]
    reference_origin = None
    reference_name = ""
    live_supported = mode in ("global", "point")
    if mode == "global":
        origin = _normalize_xyz_triplet(params.get("origin") or params.get("position") or params)
    elif mode == "point":
        if reference is None:
            raise ValueError("point mode requires reference")
        reference_output_ref = str(reference.get("output_ref") or reference.get("token") or reference.get("ref") or "").strip()
        reference_origin = _normalize_xyz_triplet(
            reference.get("origin") or reference.get("point") or reference.get("position"),
            field_name="reference.origin",
        )
        origin = list(reference_origin)
        reference_name = str(reference.get("name") or reference.get("point_name") or "PT1")
        normalized_reference = {
            "name": reference_name,
            "origin": list(reference_origin),
        }
        if reference_output_ref:
            normalized_reference["output_ref"] = reference_output_ref
        reference = normalized_reference
    elif mode == "object":
        if reference is None:
            raise ValueError("object mode requires reference")
        if any(abs(float(value)) > 1e-9 for value in rotation.values()):
            raise ValueError("object mode does not support rotation")
        if reference.get("origin") is not None:
            origin = _normalize_xyz_triplet(reference.get("origin"), field_name="reference.origin")
        system_object = _normalize_lcs_system_object(reference.get("system_object") or reference.get("default_object"))
        if system_object is not None:
            reference["system_object"] = system_object
            reference_name = system_object
            reference_origin = [0.0, 0.0, 0.0]
            live_supported = True
        else:
            source_preview_payload = reference.get("source_preview")
            source_params_payload = reference.get("source_params") or reference.get("params")
            if source_preview_payload is not None or source_params_payload is not None:
                reference_output_ref = str(reference.get("output_ref") or reference.get("token") or reference.get("ref") or "").strip()
                source_operation = str(reference.get("source_operation") or reference.get("operation") or "").strip()
                source_scenario = _normalize_scenario(reference.get("source_scenario") or reference.get("scenario") or "stepped_shaft")
                if source_scenario not in _REVOLVED_FACE_REFERENCE_SCENARIOS:
                    raise ValueError(
                        "lcs object mode currently supports only source_scenario=%s"
                        % ",".join(_REVOLVED_FACE_REFERENCE_SCENARIOS)
                    )
                source_preview = _normalize_feature_reference_preview(
                    reference,
                    field_name="lcs object",
                    source_scenario=source_scenario,
                )
                reference_selector = _normalize_feature_reference_selector(
                    reference.get("selector") or _default_feature_face_selector(source_scenario),
                    source_scenario=source_scenario,
                    source_preview=source_preview,
                    field_name="lcs.object.reference.selector",
                )
                reference = {
                    "selector": reference_selector,
                    "source_scenario": source_scenario,
                    "source_preview": source_preview,
                }
                if reference_output_ref:
                    reference["output_ref"] = reference_output_ref
                if source_operation:
                    reference["source_operation"] = source_operation
                reference_name = reference_selector
                reference_origin = _resolve_feature_selector_origin(source_scenario, reference_selector, source_preview)
                origin = list(reference_origin)
                live_supported = _feature_selector_supports_object_lcs(source_scenario, reference_selector)
            else:
                live_supported = False

    material_payload = resolve_material_payload(params.get("material"), params.get("density"))

    return {
        "name": str(params.get("name") or "Local coordinate system"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "mode": mode,
        "lcs_name": str(params.get("lcs_name") or params.get("csys_name") or params.get("name") or "LCS1"),
        "origin": origin,
        "rotation": rotation,
        "reference": reference,
        "reference_origin": reference_origin,
        "reference_name": reference_name,
        "only_outer_contour": only_outer_contour,
        "live_supported": live_supported,
        "parameter_prefix": normalize_parameter_prefix(params.get("parameter_prefix") or params.get("parameter_namespace")),
        "output_path": output_path,
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def normalize_workflow_params(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    operations_payload = params.get("operations")
    if not isinstance(operations_payload, list) or not operations_payload:
        raise ValueError("operations must be a non-empty list")

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    context: dict[str, dict[str, Any]] = {}
    normalized_operations: list[dict[str, Any]] = []
    for index, operation_payload in enumerate(operations_payload, start=1):
        normalized_operation = _normalize_workflow_operation(operation_payload, index, context)
        context[normalized_operation["id"]] = normalized_operation
        normalized_operations.append(normalized_operation)
    normalized_exports = _normalize_workflow_exports(params.get("exports"), context)
    live_supported = all(
        operation["preview"].get("params", {}).get("live_supported") is not False
        for operation in normalized_operations
    )

    material_payload = resolve_material_payload(params.get("material"), params.get("density"))
    try:
        runtime_object_probe_max_items = int(params.get("runtime_object_probe_max_items", 20) or 20)
    except (TypeError, ValueError):
        runtime_object_probe_max_items = 20
    return {
        "name": str(params.get("name") or "Workflow chain"),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "operations": normalized_operations,
        "exports": normalized_exports,
        "live_supported": live_supported,
        "output_path": output_path,
        "close_after_save": bool(params.get("close_after_save", True)),
        "include_runtime_object_probe": bool(params.get("include_runtime_object_probe", False)),
        "runtime_object_probe_max_items": runtime_object_probe_max_items,
    }


def preview_part_scenario(scenario: str, params: dict[str, Any]) -> dict[str, Any]:
    normalized_scenario = _normalize_scenario(scenario)
    if normalized_scenario == "stepped_shaft":
        return preview_stepped_shaft(params)
    if normalized_scenario == "external_conical_step":
        return preview_external_conical_step(params)
    if normalized_scenario == "internal_conical_step":
        return preview_internal_conical_step(params)
    if normalized_scenario == "internal_cylindrical_step":
        return preview_internal_cylindrical_step(params)
    if normalized_scenario == "external_polygonal_step":
        return preview_external_polygonal_step(params)
    if normalized_scenario == "internal_polygonal_step":
        return preview_internal_polygonal_step(params)
    if normalized_scenario == "external_flat_step":
        return preview_external_flat_step(params)
    if normalized_scenario == "internal_flat_step":
        return preview_internal_flat_step(params)
    if normalized_scenario == "external_helical_thread":
        return preview_external_helical_thread(params)
    if normalized_scenario == "internal_helical_thread":
        return preview_internal_helical_thread(params)
    if normalized_scenario == "external_threaded_step":
        return preview_external_threaded_step(params)
    if normalized_scenario == "internal_threaded_step":
        return preview_internal_threaded_step(params)
    if normalized_scenario == "face_ring_groove":
        return preview_face_ring_groove(params)
    if normalized_scenario == "bolt_circle_holes":
        return preview_bolt_circle_holes(params)
    if normalized_scenario == "compression_spring":
        return _preview_part_scenario_legacy("compression_spring", params, scenario)
    if normalized_scenario == "extension_spring":
        return preview_extension_spring(params)
    if normalized_scenario == "point":
        return preview_point(params)
    if normalized_scenario == "lcs":
        return preview_lcs(params)
    if normalized_scenario == "workflow":
        return preview_workflow(params)
    return _preview_part_scenario_legacy(normalized_scenario, params, scenario)


def preview_extension_spring(params: dict[str, Any]) -> dict[str, Any]:
    extension_params = copy.deepcopy(params)
    hook_selection = _resolve_extension_hook_selection(extension_params)
    hook_type = hook_selection["base_hook_type"]
    use_self_wrapping_hooks = hook_selection["left_hook_type"] == "self_wrapping_hooks" and hook_selection["right_hook_type"] == "self_wrapping_hooks"
    extension_params["hook_type"] = hook_type
    result = _preview_part_scenario_legacy("extension_spring", extension_params, "extension_spring")
    result_params = result.get("params")
    if isinstance(result_params, dict):
        result_params["hook_selection"] = copy.deepcopy(hook_selection)
        result_params["left_hook_type"] = hook_selection["left_hook_type"]
        result_params["right_hook_type"] = hook_selection["right_hook_type"]
        result_params["mixed_hook_types"] = hook_selection["left_hook_type"] != hook_selection["right_hook_type"]
        result_params["requires_side_specific_hook_builders"] = bool(result_params["mixed_hook_types"])
        if use_self_wrapping_hooks:
            result_params["hook_type"] = "self_wrapping_hooks"
            result_params["base_hook_type"] = "v_hooks"
            result_params["self_wrapping_hooks"] = True
            result_params.setdefault("self_wrapping_hook_stage", "prepared_sketches_and_native_curve_fillets")
        for key in ("bent_coil_tangent_axis_flip", "bent_coil_angle_direction", "bent_coil_angle_axis_binding", "bent_coil_angle_axis_source", "bent_coil_building_direction"):
            if key in params:
                result_params[key] = params[key]
        if params.get("variable_plan"):
            existing_variables = result_params.setdefault("variable_plan", [])
            by_name = {variable.get("name"): variable for variable in existing_variables if isinstance(variable, dict)}
            for variable in params.get("variable_plan") or []:
                if isinstance(variable, dict) and variable.get("name"):
                    by_name[variable["name"]] = copy.deepcopy(variable)
            result_params["variable_plan"] = list(by_name.values())
    if use_self_wrapping_hooks:
        result = _normalize_self_wrapping_hooks_v1(result)
    return _normalize_bent_coil_left_spike_v2(result)


def _resolve_extension_hook_selection(params: dict[str, Any]) -> dict[str, Any]:
    legacy_hook_type = _normalize_extension_hook_type(params.get("hook_type") or params.get("end_type") or "v_hooks")
    left_hook_type = _normalize_extension_hook_type(
        params.get("left_hook_type") or params.get("start_hook_type") or params.get("left_end_type") or legacy_hook_type
    )
    right_hook_type = _normalize_extension_hook_type(
        params.get("right_hook_type") or params.get("finish_hook_type") or params.get("right_end_type") or legacy_hook_type
    )
    base_hook_type = "v_hooks" if "self_wrapping_hooks" in {legacy_hook_type, left_hook_type, right_hook_type} else legacy_hook_type
    return {
        "legacy_hook_type": legacy_hook_type,
        "base_hook_type": base_hook_type,
        "left_hook_type": left_hook_type,
        "right_hook_type": right_hook_type,
        "mixed_hook_types": left_hook_type != right_hook_type,
        "requires_side_specific_hook_builders": left_hook_type != right_hook_type,
        "left_source": _extension_hook_selection_source(params, ("left_hook_type", "start_hook_type", "left_end_type"), "hook_type"),
        "right_source": _extension_hook_selection_source(params, ("right_hook_type", "finish_hook_type", "right_end_type"), "hook_type"),
    }


def _extension_hook_selection_source(params: dict[str, Any], side_keys: tuple[str, ...], fallback_key: str) -> str:
    for key in side_keys:
        if params.get(key) is not None:
            return key
    if params.get(fallback_key) is not None:
        return fallback_key
    if params.get("end_type") is not None:
        return "end_type"
    return "default"


def _normalize_extension_hook_type(value: Any) -> str:
    raw = str(value or "v_hooks").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "self_wrapping": "self_wrapping_hooks",
        "wrap_around_hooks": "self_wrapping_hooks",
        "around_self_hooks": "self_wrapping_hooks",
        "machine_hook": "machine_hooks",
        "machine": "machine_hooks",
        "v_hook": "v_hooks",
        "v": "v_hooks",
        "u_hook": "u_hooks",
        "u": "u_hooks",
        "open_loop": "open_loop_hooks",
        "center_loop": "center_loop_hooks",
        "extended_center_loop": "extended_center_loop_hooks",
        "bent_coil": "bent_coil_left_spike",
    }
    return aliases.get(raw, raw)


def _normalize_self_wrapping_hooks_v1(result: dict[str, Any]) -> dict[str, Any]:
    params = result.get("params")
    if not isinstance(params, dict) or not params.get("self_wrapping_hooks"):
        return result
    variable_plan = params.setdefault("variable_plan", [])
    by_name = {variable.get("name"): variable for variable in variable_plan if isinstance(variable, dict)}
    by_name.setdefault("SH1", {"name": "SH1", "value": 40.0, "kind": "driving_self_wrapping_hook_height", "external": True})
    by_name.setdefault("SW1", {"name": "SW1", "value": 40.0, "kind": "driving_self_wrapping_hook_width", "external": True})
    by_name.setdefault("SHW1", {"name": "SHW1", "expression": "SW1 * 0.5", "kind": "derived_self_wrapping_hook_half_width", "external": False})
    by_name.setdefault("SFR1", {"name": "SFR1", "value": 3.0, "kind": "driving_self_wrapping_fillet_radius", "external": True})
    wire_diameter = float(params.get("wire_diameter") or params.get("wire_diameter_mm") or 3.0)
    by_name.setdefault("SWR1", {"name": "SWR1", "value": wire_diameter + 0.01, "expression": "WD1 + 0.01", "kind": "derived_self_wrapping_self_clearance_radius", "external": False})
    by_name.setdefault("HT1", {"name": "HT1", "value": 6.0, "kind": "driving_self_wrapping_tail_length", "external": True})
    params["variable_plan"] = list(by_name.values())
    params["self_wrapping_hook_plan"] = {
        "version": 1,
        "base_hook_type": params.get("base_hook_type") or "v_hooks",
        "left_first_sketch_name": "SELF_WRAPPING_LEFT_FIRST_SKETCH",
        "left_projected_sketch_name": "SELF_WRAPPING_LEFT_FIRST_SKETCH_PROJECTED",
        "left_axis_plane_name": "SELF_WRAPPING_LEFT_AXIS_PERP_PLANE",
        "left_second_sketch_name": "SELF_WRAPPING_LEFT_SECOND_SKETCH_PATH",
        "fillet_radius_expression": "SFR1",
        "second_sketch_radius_expression": "SWR1",
        "tail_length_expression": "HT1",
    }
    params["connector_plan"] = []
    params["profile_anchor_plane"] = {
        "path_name": "self_wrapping_left_second_edge2",
        "vertex": "end",
        "use_perpendicular_plane": True,
    }
    params["full_path_sequence"] = [
        "self_wrapping_left_second_edge2",
        "self_wrapping_left_second_edge1",
        "self_wrapping_left_fillet2_edge2",
        "self_wrapping_left_fillet2_edge0",
        "self_wrapping_left_fillet2_edge1",
        "self_wrapping_left_first_edge1",
        "self_wrapping_left_fillet1_edge2",
        "self_wrapping_left_fillet1_edge0",
        "self_wrapping_right_fillet1_edge1",
        "self_wrapping_right_fillet1_edge0",
        "self_wrapping_right_fillet1_edge2",
        "self_wrapping_right_first_edge1",
        "self_wrapping_right_fillet2_edge1",
        "self_wrapping_right_fillet2_edge0",
        "self_wrapping_right_fillet2_edge2",
        "self_wrapping_right_second_edge1",
        "self_wrapping_right_second_edge0",
    ]
    _sync_add_variables_operation(result, params["variable_plan"])
    return result


def _preview_part_scenario_legacy(normalized_scenario: str, params: dict[str, Any], original_scenario: str) -> dict[str, Any]:
    legacy = _load_extension_spring_legacy_module()
    return legacy.preview_part_scenario(normalized_scenario, params)


def _load_extension_spring_legacy_module():
    legacy_path = Path(__file__).with_name("parametric_extension_legacy.py")
    if not legacy_path.exists():
        raise ValueError("extension_spring preview is unavailable: missing parametric_extension_legacy.py")
    loader = importlib.machinery.SourceFileLoader("kompas_mcp._parametric_extension_legacy", str(legacy_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None or spec.loader is None:
        raise ValueError("extension_spring preview is unavailable: cannot load legacy implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize_bent_coil_left_spike_v2(result: dict[str, Any]) -> dict[str, Any]:
    params = result.get("params") if isinstance(result, dict) else None
    if not isinstance(params, dict) or params.get("hook_type") != "bent_coil_left_spike":
        return result

    spring_name = str(params.get("name") or "EXTENSION_SPRING")
    pitch = float(params.get("pitch", 0.0) or 0.0)
    outer_diameter = float(params.get("outer_diameter", params.get("diameter", 0.0)) or 0.0)
    bent_turns = float(params.get("bent_coil_turns", 1.0) or 1.0)
    bent_angle = float(params.get("bent_coil_angle_degrees", 0.0) or 0.0)
    body_path_name = f"{spring_name}_BODY_PATH"
    bent_path_name = f"{spring_name}_BENT_COIL_LEFT_SPIKE_PATH"
    right_bent_path_name = f"{spring_name}_RIGHT_BENT_COIL_PATH"

    body_segment = next(
        (copy.deepcopy(segment) for segment in params.get("segment_plan", []) if segment.get("role") == "body"),
        {
            "role": "body",
            "path_role": "body",
            "path_type": "cylindric_spiral",
            "path_name": body_path_name,
        },
    )
    body_segment["path_name"] = body_path_name
    body_segment.setdefault("path_type", "cylindric_spiral")
    body_segment.setdefault("construction_only", False)

    bent_segment = {
        "role": "bent_coil_left",
        "side": "left",
        "base_vertex": "start",
        "path_role": "bent_coil_left",
        "path_type": "cylindric_spiral",
        "path_name": bent_path_name,
        "path_label": "Bent coil left spike spiral",
        "turns": bent_turns,
        "turns_variable": "BT1",
        "turns_expression": "BT1",
        "height": pitch * bent_turns,
        "height_variable": "BH1",
        "height_expression": "BH1",
        "pitch": pitch,
        "pitch_variable": "P1",
        "pitch_expression": "P1",
        "diameter": outer_diameter,
        "diameter_variable": "D1",
        "diameter_expression": "D1 - WD1",
        "radius_expression": "(D1 - WD1) / 2",
        "angle_degrees": bent_angle,
        "angle_variable": "BA1",
        "angle_expression": "BA1",
        "initial_angle_degrees": 90.0,
        "orientation": "left",
        "construction_only": True,
        "operation_variable_bindings": [
            {
                "target": "bent_coil_spiral_path",
                "parameter_note": "Diameter",
                "parameter_note_aliases": ["Diameter", "Diameter 1", "Диаметр", "Диаметр 1", "D", "D1"],
                "expression": "D1 - WD1",
                "role": "bent_coil_diameter",
            },
            {
                "target": "bent_coil_spiral_path",
                "parameter_note": "Pitch",
                "parameter_note_aliases": ["Pitch", "Step", "Шаг", "P", "P1"],
                "expression": "P1",
                "role": "bent_coil_pitch",
            },
            {
                "target": "bent_coil_spiral_path",
                "parameter_note": "Height",
                "parameter_note_aliases": ["Height", "Высота", "H", "BH1"],
                "expression": "BH1",
                "role": "bent_coil_height",
            },
        ],
    }

    right_bent_segment = copy.deepcopy(bent_segment)
    right_bent_segment.update(
        {
            "role": "bent_coil_right",
            "side": "right",
            "base_vertex": "end",
            "path_role": "bent_coil_right",
            "path_name": right_bent_path_name,
            "path_label": "Bent coil right spike spiral",
            "orientation": "right",
            "angle_direction_param": "bent_coil_right_angle_direction",
            "building_direction_param": "bent_coil_right_building_direction",
            "initial_angle_degrees": float(params.get("bent_coil_right_initial_angle_degrees", 90.0) or 90.0),
        }
    )

    params["segment_plan"] = [body_segment, bent_segment, right_bent_segment]
    params["connector_plan"] = []
    params["full_path_sequence"] = [body_path_name, bent_path_name, right_bent_path_name]
    params["profile_anchor_plane"] = {
        "path_name": right_bent_path_name,
        "vertex": "end",
        "use_perpendicular_plane": True,
    }
    params["construction_only"] = False
    params["bent_coil_auxiliary_construction"] = True
    params.setdefault("bent_coil_building_direction", False)
    params.setdefault("bent_coil_right_building_direction", True)
    _ensure_bent_coil_v2_variables(params, pitch, bent_turns, bent_angle)
    _sync_add_variables_operation(result, params["variable_plan"])
    return result


def _ensure_bent_coil_v2_variables(params: dict[str, Any], pitch: float, turns: float, angle: float) -> None:
    variable_plan = params.setdefault("variable_plan", [])
    by_name = {variable.get("name"): variable for variable in variable_plan if isinstance(variable, dict)}
    by_name.setdefault("BT1", {"name": "BT1", "value": turns, "kind": "driving_bent_coil_turn_count", "external": True})
    by_name.setdefault("BH1", {"name": "BH1", "expression": "P1 * BT1", "kind": "derived_bent_coil_height", "external": False})
    by_name.setdefault(
        "BA1",
        {
            "name": "BA1",
            "value": angle,
            "kind": "driving_bent_coil_angle_degrees",
            "external": True,
            "comment": "BA1: bent-coil angle plane angle in degrees",
        },
    )
    by_name["BT1"].setdefault("value", turns)
    by_name["BH1"]["expression"] = "P1 * BT1"
    by_name["BA1"].setdefault("value", angle)
    by_name["BA1"]["kind"] = "driving_bent_coil_angle_degrees"
    by_name["BA1"]["comment"] = "BA1: bent-coil angle plane angle in degrees"
    params["variable_plan"] = list(by_name.values())


def _sync_add_variables_operation(result: dict[str, Any], variable_plan: list[dict[str, Any]]) -> None:
    operations = result.get("operations")
    if not isinstance(operations, list):
        return
    variables = [copy.deepcopy(variable) for variable in variable_plan if isinstance(variable, dict)]
    for operation in operations:
        if isinstance(operation, dict) and operation.get("operation") == "add_variables":
            operation["variables"] = variables
            return
    if variables:
        operations.insert(0, {"operation": "add_variables", "variables": variables})


def _normalize_scenario(scenario: str) -> str:
    value = str(scenario or "").strip().lower().replace("-", "_")
    aliases = {
        "shaft": "stepped_shaft",
        "step_shaft": "stepped_shaft",
        "stepped_shaft": "stepped_shaft",
    }
    aliases.update(EXTERNAL_CONICAL_STEP_SCENARIO_ALIASES)
    aliases.update(INTERNAL_CONICAL_STEP_SCENARIO_ALIASES)
    aliases.update(INTERNAL_CYLINDRICAL_STEP_SCENARIO_ALIASES)
    aliases.update(EXTERNAL_POLYGONAL_STEP_SCENARIO_ALIASES)
    aliases.update(INTERNAL_POLYGONAL_STEP_SCENARIO_ALIASES)
    aliases.update(EXTERNAL_FLAT_STEP_SCENARIO_ALIASES)
    aliases.update(INTERNAL_FLAT_STEP_SCENARIO_ALIASES)
    aliases.update(EXTERNAL_HELICAL_THREAD_SCENARIO_ALIASES)
    aliases.update(INTERNAL_HELICAL_THREAD_SCENARIO_ALIASES)
    aliases.update(EXTERNAL_THREADED_STEP_SCENARIO_ALIASES)
    aliases.update(INTERNAL_THREADED_STEP_SCENARIO_ALIASES)
    aliases.update(FACE_RING_GROOVE_SCENARIO_ALIASES)
    aliases.update(BOLT_CIRCLE_HOLES_SCENARIO_ALIASES)
    aliases.update(COMPRESSION_SPRING_SCENARIO_ALIASES)
    aliases.update({"extension_spring": "extension_spring", "tension_spring": "extension_spring"})
    aliases.update(POINT_SCENARIO_ALIASES)
    aliases.update(LCS_SCENARIO_ALIASES)
    aliases.update(WORKFLOW_SCENARIO_ALIASES)
    return aliases.get(value, value)


def _normalize_workflow_operation(
    operation_payload: dict[str, Any],
    index: int,
    context: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(operation_payload, dict):
        raise ValueError(f"operations[{index - 1}] must be an object")
    operation_id = str(operation_payload.get("id") or f"op_{index}").strip()
    if not operation_id:
        raise ValueError(f"operations[{index - 1}].id must not be empty")
    if operation_id in context:
        raise ValueError(f"Duplicate workflow operation id: {operation_id}")

    scenario = _normalize_scenario(operation_payload.get("scenario") or operation_payload.get("type") or "")
    if scenario not in SUPPORTED_PART_SCENARIOS or scenario == "workflow":
        raise ValueError(f"Unsupported workflow operation scenario: {scenario}")

    raw_params = operation_payload.get("params")
    if raw_params is None:
        raw_params = {
            key: value
            for key, value in operation_payload.items()
            if key not in {"id", "scenario", "type"}
        }
    if not isinstance(raw_params, dict):
        raise ValueError(f"operations[{index - 1}].params must be an object")

    params = dict(raw_params)
    bindings: dict[str, str] = {}
    depends_on: list[str] = []

    if scenario == "point":
        mode = _normalize_point_mode(params.get("mode") or params.get("type") or "global")
        reference_payload = params.get("reference") or params.get("base") or params.get("ref")
        reference = dict(reference_payload) if isinstance(reference_payload, dict) else reference_payload
        if mode == "offset_from_point":
            resolved_reference = _resolve_workflow_output_reference(
                context,
                reference,
                expected_output_type="point",
                allowed_scenarios=("point",),
                default_output="point",
            )
            if resolved_reference is not None:
                target = resolved_reference["target"]
                point_ref = resolved_reference["output"]
                params["reference"] = {
                    "name": point_ref["name"],
                    "origin": point_ref["origin"],
                    "output_ref": _build_workflow_output_token(
                        resolved_reference["operation_id"],
                        resolved_reference["output_key"],
                    ),
                }
                bindings["reference_operation"] = resolved_reference["operation_id"]
                bindings["reference_output"] = resolved_reference["output_key"]
                depends_on.append(resolved_reference["operation_id"])
            elif _looks_like_workflow_output_reference(reference):
                _raise_invalid_workflow_output_reference(
                    reference,
                    path="operations[%s].params.reference" % (index - 1),
                )
        elif mode == "center_of_object":
            default_face_output = "end_face"
            if isinstance(reference, dict):
                default_face_output = str(reference.get("output") or reference.get("selector") or default_face_output)
            resolved_reference = _resolve_workflow_output_reference(
                context,
                reference,
                expected_output_type="face",
                allowed_scenarios=_REVOLVED_FACE_REFERENCE_SCENARIOS,
                default_output=default_face_output,
            )
            if resolved_reference is not None:
                target = resolved_reference["target"]
                params["reference"] = {
                    "selector": resolved_reference["output_key"],
                    "source_scenario": str(target["scenario"]),
                    "source_preview": dict(target["preview"]),
                    "source_operation": resolved_reference["operation_id"],
                    "output_ref": _build_workflow_output_token(
                        resolved_reference["operation_id"],
                        resolved_reference["output_key"],
                    ),
                }
                bindings["reference_operation"] = resolved_reference["operation_id"]
                bindings["reference_output"] = resolved_reference["output_key"]
                depends_on.append(resolved_reference["operation_id"])
            elif _looks_like_workflow_output_reference(reference):
                _raise_invalid_workflow_output_reference(
                    reference,
                    path="operations[%s].params.reference" % (index - 1),
                )
        preview = preview_point(params)
    elif scenario == "lcs":
        mode = _normalize_lcs_mode(params.get("mode") or params.get("type") or "global")
        reference_payload = params.get("reference") or params.get("base") or params.get("ref")
        reference = dict(reference_payload) if isinstance(reference_payload, dict) else reference_payload
        if mode == "point":
            resolved_reference = _resolve_workflow_output_reference(
                context,
                reference,
                expected_output_type="point",
                allowed_scenarios=("point",),
                default_output="point",
            )
            if resolved_reference is not None:
                target = resolved_reference["target"]
                point_ref = resolved_reference["output"]
                params["reference"] = {
                    "name": point_ref["name"],
                    "origin": point_ref["origin"],
                    "output_ref": _build_workflow_output_token(
                        resolved_reference["operation_id"],
                        resolved_reference["output_key"],
                    ),
                }
                bindings["reference_operation"] = resolved_reference["operation_id"]
                bindings["reference_output"] = resolved_reference["output_key"]
                depends_on.append(resolved_reference["operation_id"])
            elif _looks_like_workflow_output_reference(reference):
                _raise_invalid_workflow_output_reference(
                    reference,
                    path="operations[%s].params.reference" % (index - 1),
                )
        elif mode == "object":
            default_face_output = "end_face"
            if isinstance(reference, dict):
                default_face_output = str(reference.get("output") or reference.get("selector") or default_face_output)
            resolved_reference = _resolve_workflow_output_reference(
                context,
                reference,
                expected_output_type="face",
                allowed_scenarios=_REVOLVED_FACE_REFERENCE_SCENARIOS,
                default_output=default_face_output,
            )
            if resolved_reference is not None:
                target = resolved_reference["target"]
                params["reference"] = {
                    "selector": resolved_reference["output_key"],
                    "source_scenario": str(target["scenario"]),
                    "source_preview": dict(target["preview"]),
                    "source_operation": resolved_reference["operation_id"],
                    "output_ref": _build_workflow_output_token(
                        resolved_reference["operation_id"],
                        resolved_reference["output_key"],
                    ),
                }
                bindings["reference_operation"] = resolved_reference["operation_id"]
                bindings["reference_output"] = resolved_reference["output_key"]
                depends_on.append(resolved_reference["operation_id"])
            elif _looks_like_workflow_output_reference(reference):
                _raise_invalid_workflow_output_reference(
                    reference,
                    path="operations[%s].params.reference" % (index - 1),
                )
        preview = preview_lcs(params)
    elif scenario in (
        "stepped_shaft",
        "external_conical_step",
        "internal_conical_step",
        "internal_cylindrical_step",
        "external_polygonal_step",
        "internal_polygonal_step",
        "external_flat_step",
            "internal_flat_step",
            "face_ring_groove",
            "bolt_circle_holes",
            "compression_spring",
        ):
        placement = params.get("placement")
        if isinstance(placement, dict):
            base_payload = placement.get("base") or placement
            reference_payload = base_payload.get("reference") or base_payload.get("ref") or placement.get("reference") or placement.get("ref")
            reference = dict(reference_payload) if isinstance(reference_payload, dict) else reference_payload
            resolved_reference = _resolve_workflow_output_reference(
                context,
                reference,
                expected_output_type="lcs",
                allowed_scenarios=("lcs",),
                default_output="lcs",
            )
            if resolved_reference is not None:
                placement_payload = dict(placement)
                normalized_base = dict(base_payload)
                normalized_base["reference"] = {
                    "output_ref": _build_workflow_output_token(
                        resolved_reference["operation_id"],
                        resolved_reference["output_key"],
                    )
                }
                output_origin = resolved_reference["output"].get("origin")
                if isinstance(output_origin, (list, tuple)) and len(output_origin) >= 2:
                    normalized_base["origin"] = [float(output_origin[0]), float(output_origin[1])]
                normalized_base["mode"] = "csys_ref"
                placement_payload["base"] = normalized_base
                params["placement"] = placement_payload
                bindings["placement_operation"] = resolved_reference["operation_id"]
                bindings["placement_output"] = resolved_reference["output_key"]
                depends_on.append(resolved_reference["operation_id"])
            elif _looks_like_workflow_output_reference(reference):
                _raise_invalid_workflow_output_reference(
                    reference,
                    path="operations[%s].params.placement.base.reference" % (index - 1),
                )
        if scenario == "stepped_shaft":
            preview = preview_stepped_shaft(params)
        elif scenario == "external_conical_step":
            preview = preview_external_conical_step(params)
        elif scenario == "internal_conical_step":
            preview = preview_internal_conical_step(params)
        elif scenario == "internal_cylindrical_step":
            preview = preview_internal_cylindrical_step(params)
        elif scenario == "external_polygonal_step":
            preview = preview_external_polygonal_step(params)
        elif scenario == "internal_polygonal_step":
            preview = preview_internal_polygonal_step(params)
        elif scenario == "external_flat_step":
            preview = preview_external_flat_step(params)
        elif scenario == "internal_flat_step":
            preview = preview_internal_flat_step(params)
        elif scenario == "face_ring_groove":
            preview = preview_face_ring_groove(params)
        elif scenario == "bolt_circle_holes":
            preview = preview_bolt_circle_holes(params)
        else:
            preview = preview_compression_spring(params)
    else:
        raise ValueError(f"Unsupported workflow operation scenario: {scenario}")

    return {
        "id": operation_id,
        "scenario": scenario,
        "params": dict(preview["params"]),
        "preview": preview,
        "outputs": dict((preview.get("interface") or {}).get("outputs") or {}),
        "bindings": bindings,
        "depends_on": depends_on,
    }


def _build_workflow_output_token(operation_id: str, output_key: str) -> str:
    return "%s.%s" % (str(operation_id).strip(), str(output_key).strip())


def _looks_like_workflow_output_reference(reference: Any) -> bool:
    if isinstance(reference, str):
        return bool(str(reference).strip())
    if not isinstance(reference, dict):
        return False
    for key in (
        "token",
        "output_ref",
        "ref",
        "operation",
        "operation_id",
        "workflow_operation",
        "output",
        "output_name",
    ):
        if reference.get(key) not in (None, ""):
            return True
    return False


def _raise_invalid_workflow_output_reference(reference: Any, *, path: str) -> None:
    raise ValueError(
        "%s must be a workflow output reference like op.output or {ref: 'op.output'}; got %r"
        % (path, reference)
    )


def _list_workflow_operation_outputs(target: dict[str, Any]) -> list[str]:
    outputs = dict((target.get("preview") or {}).get("interface", {}).get("outputs") or {})
    return sorted(str(name).strip() for name in outputs.keys() if str(name).strip())


def _format_workflow_output_choices(output_names: list[str]) -> str:
    if not output_names:
        return "<none>"
    return ", ".join(output_names)


def _list_stepped_shaft_selector_choices(source_preview: dict[str, Any] | None = None) -> list[str]:
    selector_points: dict[str, Any] = {}
    preview_payload = source_preview or {}
    preview_selectors = preview_payload.get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    anchors = ((preview_payload.get("interface") or {}).get("anchors") or {})
    anchor_selectors = anchors.get("selector_points") or {}
    if isinstance(anchor_selectors, dict):
        selector_points.update(anchor_selectors)
    if selector_points:
        return sorted(str(name).strip() for name in selector_points.keys() if str(name).strip())
    return [
        "far_end_face",
        "start_face",
        "step_1_start_face",
        "step_1_end_face",
        "step_1_outer_face",
        "shoulder_1_face",
    ]


def _format_stepped_shaft_selector_choices(selector_names: list[str]) -> str:
    if not selector_names:
        return "<none>"
    return ", ".join(selector_names)


def _raise_unknown_workflow_operation_reference(
    context: dict[str, dict[str, Any]],
    operation_id: str,
    *,
    output_key: str | None = None,
) -> None:
    token = _build_workflow_output_token(operation_id, output_key) if output_key else operation_id
    available_operations = ", ".join(sorted(context.keys())) or "<none>"
    raise ValueError(
        "Workflow reference %s points to unknown operation %s; available operations: %s"
        % (token, operation_id, available_operations)
    )


def _normalize_workflow_reference_output_key(
    target: dict[str, Any],
    output_key: str | None,
    *,
    fallback_output: str,
) -> str:
    try:
        return _normalize_operation_output_key(target["scenario"], output_key or fallback_output)
    except ValueError as exc:
        raise ValueError(
            "Workflow operation %s (scenario=%s) does not export output %s; available outputs: %s"
            % (
                target["id"],
                target["scenario"],
                str(output_key or fallback_output).strip(),
                _format_workflow_output_choices(_list_workflow_operation_outputs(target)),
            )
        ) from exc


def _extract_workflow_output_reference(reference: Any) -> tuple[str, str | None] | None:
    if isinstance(reference, str):
        token = str(reference).strip()
        if not token:
            return None
        if "." not in token:
            return token, None
        operation_id, output_key = token.split(".", 1)
        return operation_id.strip(), output_key.strip() or None
    if not isinstance(reference, dict):
        return None
    token = reference.get("token") or reference.get("output_ref") or reference.get("ref")
    if token not in (None, ""):
        return _extract_workflow_output_reference(token)
    operation_id = reference.get("operation") or reference.get("operation_id") or reference.get("workflow_operation")
    if operation_id in (None, ""):
        return None
    output_key = reference.get("output") or reference.get("output_name")
    output_value = str(output_key).strip() if output_key not in (None, "") else None
    return str(operation_id).strip(), output_value


def _default_operation_output_key(scenario: str) -> str:
    normalized_scenario = _normalize_scenario(scenario)
    if normalized_scenario in {
        "stepped_shaft",
        "external_conical_step",
        "internal_conical_step",
        "internal_cylindrical_step",
        "external_polygonal_step",
        "internal_polygonal_step",
        "face_ring_groove",
        "bolt_circle_holes",
        "compression_spring",
    }:
        return "body"
    if normalized_scenario == "point":
        return "point"
    if normalized_scenario == "lcs":
        return "lcs"
    return "result"


def _resolve_workflow_output_reference_any(
    context: dict[str, dict[str, Any]],
    reference: Any,
    *,
    default_output: str | None = None,
) -> dict[str, Any] | None:
    extracted = _extract_workflow_output_reference(reference)
    if extracted is None:
        return None
    operation_id, output_key = extracted
    target = context.get(operation_id)
    if target is None:
        _raise_unknown_workflow_operation_reference(context, operation_id, output_key=output_key)
    normalized_output = _normalize_workflow_reference_output_key(
        target,
        output_key,
        fallback_output=default_output or _default_operation_output_key(target["scenario"]),
    )
    outputs = dict((target["preview"].get("interface") or {}).get("outputs") or {})
    output = outputs.get(normalized_output)
    if output is None:
        raise ValueError(
            "Workflow operation %s (scenario=%s) does not export output %s; available outputs: %s"
            % (
                operation_id,
                target["scenario"],
                normalized_output,
                _format_workflow_output_choices(_list_workflow_operation_outputs(target)),
            )
        )
    return {
        "operation_id": operation_id,
        "output_key": normalized_output,
        "target": target,
        "output": output,
    }


def _resolve_workflow_output_reference(
    context: dict[str, dict[str, Any]],
    reference: Any,
    *,
    expected_output_type: str,
    allowed_scenarios: tuple[str, ...],
    default_output: str,
) -> dict[str, Any] | None:
    extracted = _extract_workflow_output_reference(reference)
    if extracted is None:
        return None
    operation_id, output_key = extracted
    target = context.get(operation_id)
    if target is None:
        _raise_unknown_workflow_operation_reference(context, operation_id, output_key=output_key)
    if target["scenario"] not in allowed_scenarios:
        raise ValueError(
            "Workflow reference %s must target scenarios=%s, got %s on operation %s; available outputs: %s"
            % (
                _build_workflow_output_token(
                    operation_id,
                    output_key or default_output or _default_operation_output_key(target["scenario"]),
                ),
                ",".join(allowed_scenarios),
                target["scenario"],
                operation_id,
                _format_workflow_output_choices(_list_workflow_operation_outputs(target)),
            )
        )
    normalized_output = _normalize_workflow_reference_output_key(
        target,
        output_key,
        fallback_output=default_output,
    )
    outputs = dict((target["preview"].get("interface") or {}).get("outputs") or {})
    output = outputs.get(normalized_output)
    if output is None:
        raise ValueError(
            "Workflow operation %s (scenario=%s) does not export output %s; available outputs: %s"
            % (
                operation_id,
                target["scenario"],
                normalized_output,
                _format_workflow_output_choices(_list_workflow_operation_outputs(target)),
            )
        )
    if str(output.get("type") or "") != expected_output_type:
        raise ValueError(
            "Workflow output %s.%s must be type=%s, got %s; available outputs: %s"
            % (
                operation_id,
                normalized_output,
                expected_output_type,
                output.get("type"),
                _format_workflow_output_choices(_list_workflow_operation_outputs(target)),
            )
        )
    return {
        "operation_id": operation_id,
        "output_key": normalized_output,
        "target": target,
        "output": output,
    }


def _normalize_workflow_exports(
    exports_payload: Any,
    context: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if exports_payload in (None, "", [], {}):
        return []

    normalized_items: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    if isinstance(exports_payload, dict):
        iterable = [
            {"name": str(name), "ref": reference}
            for name, reference in exports_payload.items()
        ]
    elif isinstance(exports_payload, list):
        iterable = list(exports_payload)
    else:
        raise ValueError("exports must be an object or a list")

    for index, item in enumerate(iterable, start=1):
        if isinstance(item, str):
            reference = item
            extracted = _extract_workflow_output_reference(reference)
            if extracted is None:
                _raise_invalid_workflow_output_reference(reference, path="exports[%s]" % (index - 1))
            operation_id, output_key = extracted
            export_name = str(output_key or operation_id).strip()
        elif isinstance(item, dict):
            export_name = str(item.get("name") or item.get("id") or "").strip()
            if not export_name:
                raise ValueError("exports[%s].name must not be empty" % (index - 1))
            reference = item.get("ref")
            if reference in (None, ""):
                reference = {
                    "operation": item.get("operation") or item.get("operation_id"),
                    "output": item.get("output") or item.get("output_name"),
                }
        else:
            raise ValueError("exports[%s] must be a string or an object" % (index - 1))

        if export_name in seen_names:
            raise ValueError("Duplicate workflow export name: %s" % export_name)
        if _extract_workflow_output_reference(reference) is None:
            _raise_invalid_workflow_output_reference(reference, path="exports[%s].ref" % (index - 1))
        resolved_reference = _resolve_workflow_output_reference_any(context, reference)
        if resolved_reference is None:
            raise ValueError(
                "exports[%s].ref does not resolve to a workflow output; got %r"
                % (index - 1, reference)
            )
        seen_names.add(export_name)
        normalized_items.append(
            {
                "name": export_name,
                "operation_id": resolved_reference["operation_id"],
                "output_key": resolved_reference["output_key"],
                "output": dict(resolved_reference["output"]),
                "token": "%s.%s" % (resolved_reference["operation_id"], resolved_reference["output_key"]),
            }
        )

    return normalized_items


def _require_workflow_operation(
    context: dict[str, dict[str, Any]],
    operation_id: str,
    expected_scenario: str,
) -> dict[str, Any]:
    target = context.get(operation_id)
    if target is None:
        raise ValueError(f"Unknown workflow operation reference: {operation_id}")
    if target["scenario"] != expected_scenario:
        raise ValueError(
            f"Workflow operation {operation_id} must be scenario={expected_scenario}, got {target['scenario']}"
        )
    return target


def _normalize_point_mode(value: Any) -> str:
    mode = str(value or "global").strip().lower().replace("-", "_")
    aliases = {
        "global": "global",
        "coordinates": "global",
        "by_coordinates": "global",
        "center": "center_of_object",
        "center_of_object": "center_of_object",
        "object_center": "center_of_object",
        "by_object_center": "center_of_object",
        "offset_from_point": "offset_from_point",
        "point_offset": "offset_from_point",
    }
    normalized = aliases.get(mode, mode)
    if normalized not in ("global", "center_of_object", "offset_from_point"):
        raise ValueError(f"Unsupported point mode: {normalized}")
    return normalized


def _normalize_lcs_mode(value: Any) -> str:
    mode = str(value or "global").strip().lower().replace("-", "_")
    aliases = {
        "global": "global",
        "coordinates": "global",
        "by_coordinates": "global",
        "point": "point",
        "by_point": "point",
        "object": "object",
        "by_object": "object",
    }
    normalized = aliases.get(mode, mode)
    if normalized not in ("global", "point", "object"):
        raise ValueError(f"Unsupported lcs mode: {normalized}")
    return normalized


def _positive_float(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except Exception as exc:
        raise ValueError(f"{field_name} must be a positive number") from exc
    if number <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return number


def _coalesce_defined(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return payload.get(key)
    return None


def _build_extrusion_length_variable_bindings(
    normalized: dict[str, Any],
    *,
    target: str = "extrusion",
) -> list[dict[str, Any]]:
    parameter_prefix = normalized["parameter_prefix"]
    length_variable = build_parameter_name("L", 1, prefix=parameter_prefix)
    return [
        {
            "target": target,
            "parameter_note": "Distance",
            "parameter_note_aliases": [
                "Distance",
                "Length",
                "Depth",
                "Extrusion depth",
                "Расстояние",
                "Длина",
                "Глубина",
            ],
            "expression": length_variable,
            "role": "extrusion_length",
        }
    ]


def _build_circular_pattern_variable_bindings(
    count_expression: str,
    angle_step_expression: str,
) -> list[dict[str, Any]]:
    return [
        {
            "target": "circular_pattern",
            "parameter_note": "Count",
            "parameter_note_aliases": [
                "Count",
                "Instance count",
                "Instances",
                "Количество",
                "Число",
            ],
            "expression": count_expression,
            "role": "pattern_count",
        },
        {
            "target": "circular_pattern",
            "parameter_note": "Angle",
            "parameter_note_aliases": [
                "Angle",
                "Step",
                "Angular step",
                "Angle step",
                "Угол",
                "Шаг",
                "Угловой шаг",
            ],
            "expression": angle_step_expression,
            "role": "pattern_angle_step",
        },
    ]


def _build_transition_point_variable_bindings(expression: str, role: str) -> list[dict[str, Any]]:
    text = str(expression or "").strip()
    if not text:
        return []
    return [
        {
            "target": "transition_trim_point",
            "parameter_note": "Расстояние",
            "parameter_note_aliases": [
                "Расстояние",
                "Смещение (длина сегмента)",
                "Distance",
                "Offset",
                "Segment length offset",
            ],
            "expression": text,
            "role": str(role or "transition_trim_offset"),
        }
    ]


def _build_transition_connect_curve_variable_bindings(
    expression: str,
    role: str,
) -> list[dict[str, Any]]:
    text = str(expression or "").strip()
    if not text:
        return []
    return [
        {
            "target": "connect_curve",
            "parameter_note": "Натяжение 1, %",
            "parameter_note_aliases": [
                "Натяжение 1, %",
                "Натяжение 1",
                "Tension 1, %",
                "Tension 1",
                "Tension",
            ],
            "expression": text,
            "role": str(role or "transition_connect_tension"),
        }
    ]


def _build_spring_spiral_variable_bindings(
    mean_diameter_expression: str,
    pitch_expression: str,
    height_expression: str,
) -> list[dict[str, Any]]:
    bindings = [
        {
            "target": "spiral_path",
            "parameter_note": "Diameter",
            "parameter_note_aliases": [
                "Diameter",
                "Diameter 1",
                "Diameter 2",
                "Mean diameter",
                "Coil diameter",
                "\u0414\u0438\u0430\u043c\u0435\u0442\u0440 1",
                "\u0414\u0438\u0430\u043c\u0435\u0442\u0440 2",
                "Диаметр",
                "Средний диаметр",
            ],
            "expression": mean_diameter_expression,
            "role": "spring_mean_diameter",
        },
        {
            "target": "spiral_path",
            "parameter_note": "Step",
            "parameter_note_aliases": [
                "Step",
                "Pitch",
                "Шаг",
            ],
            "expression": pitch_expression,
            "role": "spring_pitch",
        },
        {
            "target": "spiral_path",
            "parameter_note": "Height",
            "parameter_note_aliases": [
                "Height",
                "Length",
                "Высота",
                "Длина",
            ],
            "expression": height_expression,
            "role": "spring_height",
        },
    ]
    return bindings


def _optional_positive_float(payload: dict[str, Any], field_name: str, *keys: str) -> float | None:
    value = _coalesce_defined(payload, *keys)
    if value in (None, ""):
        return None
    return _positive_float(value, field_name)


def _optional_non_negative_float(payload: dict[str, Any], field_name: str, *keys: str) -> float | None:
    value = _coalesce_defined(payload, *keys)
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except Exception as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if result < 0.0:
        raise ValueError(f"{field_name} must be greater than or equal to zero")
    return result


def _optional_float(payload: dict[str, Any], field_name: str, *keys: str) -> float | None:
    value = _coalesce_defined(payload, *keys)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception as exc:
        raise ValueError(f"{field_name} must be a number") from exc


def _normalize_spring_fractional_turn(value: float, *, field_name: str) -> float:
    scaled = float(value) * 4.0
    rounded = round(scaled)
    if abs(scaled - rounded) > 1e-6:
        raise ValueError(f"{field_name} must use 0.25-turn increments")
    return rounded / 4.0


def _resolve_compression_spring_end_kind(end_turns: float, ground_turns: float) -> str:
    if ground_turns > 1e-6:
        return "closed_ground"
    if end_turns > 1e-6:
        return "closed"
    return "open"


def _format_compression_spring_expression_literal(value: float) -> str:
    normalized = 0.0 if abs(float(value)) <= 1e-9 else float(value)
    return f"{normalized:g}"


def _compression_spring_expression_max(left: str, right: str) -> str:
    return f"((({left}) + ({right}) + abs(({left}) - ({right}))) / 2)"


def _compression_spring_expression_min(left: str, right: str) -> str:
    return f"((({left}) + ({right}) - abs(({left}) - ({right}))) / 2)"


def _compression_spring_expression_non_negative(expression: str) -> str:
    return f"((({expression}) + abs({expression})) / 2)"


def _parse_compression_spring_end_contract(params: dict[str, Any]) -> dict[str, Any]:
    v1_end_turns = _coalesce_defined(
        params,
        "end_turns_per_side",
        "compressed_turns_per_side",
        "end_coils_per_side",
        "support_turns_per_side",
        "n2",
    )
    v1_ground_turns = _coalesce_defined(
        params,
        "ground_turns_per_side",
        "processed_turns_per_side",
        "ground_coils_per_side",
        "n3",
    )
    v2_start_end_turns = _coalesce_defined(params, "start_end_turns")
    v2_finish_end_turns = _coalesce_defined(params, "finish_end_turns")
    v2_start_ground_turns = _coalesce_defined(params, "start_ground_turns")
    v2_finish_ground_turns = _coalesce_defined(params, "finish_ground_turns")

    has_v1_fields = v1_end_turns is not None or v1_ground_turns is not None
    has_v2_fields = any(
        value is not None
        for value in (
            v2_start_end_turns,
            v2_finish_end_turns,
            v2_start_ground_turns,
            v2_finish_ground_turns,
        )
    )
    if has_v1_fields and has_v2_fields:
        raise ValueError(
            "compression_spring cannot mix V1 per-side end fields with V2 per-end end fields"
        )

    if not has_v2_fields:
        end_turns_per_side = _optional_non_negative_float(
            params,
            "end_turns_per_side",
            "end_turns_per_side",
            "compressed_turns_per_side",
            "end_coils_per_side",
            "support_turns_per_side",
            "n2",
        )
        ground_turns_per_side = _optional_non_negative_float(
            params,
            "ground_turns_per_side",
            "ground_turns_per_side",
            "processed_turns_per_side",
            "ground_coils_per_side",
            "n3",
        )
        end_turns_per_side = _normalize_spring_fractional_turn(
            float(end_turns_per_side or 0.0),
            field_name="end_turns_per_side",
        )
        ground_turns_per_side = _normalize_spring_fractional_turn(
            float(ground_turns_per_side or 0.0),
            field_name="ground_turns_per_side",
        )
        if ground_turns_per_side > end_turns_per_side + 1e-6:
            raise ValueError(
                "compression_spring ground_turns_per_side cannot exceed end_turns_per_side"
            )
        start_end_kind = _resolve_compression_spring_end_kind(
            end_turns_per_side,
            ground_turns_per_side,
        )
        return {
            "end_contract_mode": "v1_symmetric",
            "end_projection_mode": "projected_to_v1_symmetric",
            "end_turns_per_side": end_turns_per_side,
            "ground_turns_per_side": ground_turns_per_side,
            "start_end_turns": end_turns_per_side,
            "finish_end_turns": end_turns_per_side,
            "start_ground_turns": ground_turns_per_side,
            "finish_ground_turns": ground_turns_per_side,
            "start_end_kind": start_end_kind,
            "finish_end_kind": start_end_kind,
        }

    start_end_turns = _normalize_spring_fractional_turn(
        float(
            _optional_non_negative_float(
                params,
                "start_end_turns",
                "start_end_turns",
            )
            or 0.0
        ),
        field_name="start_end_turns",
    )
    finish_end_turns = _normalize_spring_fractional_turn(
        float(
            _optional_non_negative_float(
                params,
                "finish_end_turns",
                "finish_end_turns",
            )
            or 0.0
        ),
        field_name="finish_end_turns",
    )
    start_ground_turns = _normalize_spring_fractional_turn(
        float(
            _optional_non_negative_float(
                params,
                "start_ground_turns",
                "start_ground_turns",
            )
            or 0.0
        ),
        field_name="start_ground_turns",
    )
    finish_ground_turns = _normalize_spring_fractional_turn(
        float(
            _optional_non_negative_float(
                params,
                "finish_ground_turns",
                "finish_ground_turns",
            )
            or 0.0
        ),
        field_name="finish_ground_turns",
    )
    if start_ground_turns > start_end_turns + 1e-6:
        raise ValueError("compression_spring start_ground_turns cannot exceed start_end_turns")
    if finish_ground_turns > finish_end_turns + 1e-6:
        raise ValueError("compression_spring finish_ground_turns cannot exceed finish_end_turns")

    symmetric_end_turns = abs(start_end_turns - finish_end_turns) <= 1e-6
    symmetric_ground_turns = abs(start_ground_turns - finish_ground_turns) <= 1e-6
    projected_to_v1 = symmetric_end_turns and symmetric_ground_turns
    return {
        "end_contract_mode": "v2_per_end",
        "end_projection_mode": (
            "projected_to_v1_symmetric" if projected_to_v1 else "native_v2"
        ),
        "end_turns_per_side": start_end_turns if projected_to_v1 else None,
        "ground_turns_per_side": start_ground_turns if projected_to_v1 else None,
        "start_end_turns": start_end_turns,
        "finish_end_turns": finish_end_turns,
        "start_ground_turns": start_ground_turns,
        "finish_ground_turns": finish_ground_turns,
        "start_end_kind": _resolve_compression_spring_end_kind(
            start_end_turns,
            start_ground_turns,
        ),
        "finish_end_kind": _resolve_compression_spring_end_kind(
            finish_end_turns,
            finish_ground_turns,
        ),
    }


def _build_compression_spring_end_summary(
    normalized: dict[str, Any],
    *,
    side_name: str,
) -> dict[str, Any]:
    role = f"{side_name}_end"
    segment_names = [
        str(segment["path_name"])
        for segment in normalized["segment_plan"]
        if str(segment.get("role") or "") == role
    ]
    end_kind = str(normalized[f"{side_name}_end_kind"])
    label = end_kind.replace("_", "-")
    support_selector_names = [f"{side_name}_support_point"] if float(normalized[f"{side_name}_end_turns"]) > 1e-6 else []
    return {
        "end_turns": float(normalized[f"{side_name}_end_turns"]),
        "ground_turns": float(normalized[f"{side_name}_ground_turns"]),
        "label": label,
        "has_end_segment": bool(segment_names),
        "segment_names": segment_names,
        "support_selector_names": support_selector_names,
        "grounded_geometry_signal": False,
    }


def _build_compression_spring_selector_points(
    normalized: dict[str, Any],
    start_center: list[float],
    end_center: list[float],
) -> dict[str, list[float]]:
    segment_plan = normalized["segment_plan"]
    if not segment_plan:
        return {
            "start_tip_point": list(start_center),
            "finish_tip_point": list(end_center),
            "start_body_entry_point": list(start_center),
            "finish_body_exit_point": list(end_center),
        }
    working_segment = next(
        segment
        for segment in segment_plan
        if str(segment.get("role") or "") == "working"
    )
    selector_points: dict[str, list[float]] = {
        "start_tip_point": list(segment_plan[0]["start_point"]),
        "finish_tip_point": list(segment_plan[-1]["end_point"]),
        "start_body_entry_point": list(working_segment["start_point"]),
        "finish_body_exit_point": list(working_segment["end_point"]),
    }
    start_end_segment = next(
        (
            segment
            for segment in segment_plan
            if str(segment.get("role") or "") == "start_end"
        ),
        None,
    )
    if start_end_segment is not None:
        selector_points["start_support_point"] = list(start_end_segment["end_point"])
    finish_end_segment = next(
        (
            segment
            for segment in segment_plan
            if str(segment.get("role") or "") == "finish_end"
        ),
        None,
    )
    if finish_end_segment is not None:
        selector_points["finish_support_point"] = list(finish_end_segment["start_point"])
    return selector_points


def _build_compression_spring_point_output(
    selector_name: str,
    origin: list[float],
    *,
    live_supported: bool,
) -> dict[str, Any]:
    return {
        "type": "point",
        "name": selector_name,
        "selector": selector_name,
        "origin": list(origin),
        "live_supported": live_supported,
    }


def _normalize_spring_phase_degrees(value: float) -> float:
    return math.fmod(float(value), 360.0)


def _normalize_spring_turning_angle_degrees(value: float) -> float:
    normalized = math.fmod(float(value), 360.0)
    if abs(normalized) <= 1e-9:
        return 0.0
    if normalized < 0.0:
        normalized += 360.0
    return normalized


def _build_spring_rotation_expression_from_turns(
    turns_expression: str | None,
    *,
    start_phase_degrees: float,
    left_hand: bool,
    extra_angle_offset_degrees: float = 0.0,
) -> str | None:
    if turns_expression in (None, ""):
        return None
    if left_hand:
        angle_offset = 90.0 + float(start_phase_degrees) + float(extra_angle_offset_degrees)
        if abs(angle_offset) <= 1e-9:
            angle_offset = 0.0
        return _build_spring_normalized_degrees_expression(
            f"({angle_offset}) - (360 * ({turns_expression}))"
        )
    angle_offset = 90.0 - float(start_phase_degrees) + float(extra_angle_offset_degrees)
    if abs(angle_offset) <= 1e-9:
        angle_offset = 0.0
    return _build_spring_normalized_degrees_expression(f"({angle_offset}) + (360 * ({turns_expression}))")


def _build_spring_normalized_degrees_expression(expression: str) -> str:
    wrapped = f"({expression})"
    return f"({wrapped} - (floor(({wrapped}) / 360) * 360))"

def _resolve_spring_segment_initial_angle_degrees(
    start_phase_degrees: float,
    *,
    turns_before: float,
    left_hand: bool,
) -> float:
    if left_hand:
        return _normalize_spring_turning_angle_degrees(-(360.0 * float(turns_before)))
    turn_delta = -360.0 * float(turns_before)
    signed_phase = float(start_phase_degrees) + turn_delta
    return _normalize_spring_turning_angle_degrees(90.0 - signed_phase)


def _resolve_spring_segment_orientation_angle_degrees(
    phase_degrees: float,
    *,
    is_first_segment: bool,
    has_rotation_expression: bool = False,
) -> float | None:
    if has_rotation_expression:
        return 0.0
    normalized_phase = _normalize_spring_phase_degrees(phase_degrees)
    if abs(normalized_phase) <= 1e-9:
        normalized_phase = 0.0
    if is_first_segment and abs(normalized_phase - 90.0) <= 1e-9:
        return None
    return float(normalized_phase)


def _build_compression_spring_profile_sketch_constraints() -> list[dict[str, Any]]:
    return [
        {"kind": "fixed_point", "target": "radius_ref", "index": 0},
        {"kind": "vertical", "target": "radius_ref"},
        {"kind": "merge_points", "target": "radius_ref", "index": 1, "partner": "profile_radius_ref", "partner_index": 0},
        {"kind": "merge_points", "target": "radius_ref", "index": 1, "partner": "profile_circle", "partner_index": 0},
        {"kind": "horizontal", "target": "profile_radius_ref"},
        {"kind": "point_on_curve", "target": "profile_radius_ref", "index": 1, "partner": "profile_circle"},
    ]


def _build_compression_spring_profile_sketch_dimensions(
    outer_diameter_expression: str,
    wire_diameter_expression: str,
) -> list[dict[str, Any]]:
    return [
        {
            "kind": "line_length",
            "target": "radius_ref",
            "expression": f"(({outer_diameter_expression}) - ({wire_diameter_expression})) / 2",
            "driving": True,
        },
        {
            "kind": "line_length",
            "target": "profile_radius_ref",
            "expression": f"({wire_diameter_expression}) / 2",
            "driving": True,
            "placement_index": 1,
        },
    ]


def _build_compression_spring_path_verification(
    segment_plan: list[dict[str, Any]],
    *,
    mean_radius: float,
) -> dict[str, Any]:
    joints: list[dict[str, Any]] = []
    max_joint_gap = 0.0
    max_joint_angle_gap = 0.0
    contour_ready = True
    for index, segment in enumerate(segment_plan):
        start_angle_radians = math.radians(float(segment["start_angle_degrees_raw"]))
        end_angle_radians = math.radians(float(segment["end_angle_degrees_raw"]))
        start_offset = float(segment["start_offset"])
        end_offset = start_offset + float(segment["height"])
        segment["start_point"] = [
            start_offset,
            float(mean_radius) * math.cos(start_angle_radians),
            float(mean_radius) * math.sin(start_angle_radians),
        ]
        segment["end_point"] = [
            end_offset,
            float(mean_radius) * math.cos(end_angle_radians),
            float(mean_radius) * math.sin(end_angle_radians),
        ]
        if index == 0:
            continue
        previous_segment = segment_plan[index - 1]
        gap_vector = [
            float(segment["start_point"][axis]) - float(previous_segment["end_point"][axis])
            for axis in range(3)
        ]
        gap_length = math.sqrt(sum(component * component for component in gap_vector))
        angle_gap = _normalize_spring_phase_degrees(
            float(segment["start_angle_degrees_raw"]) - float(previous_segment["end_angle_degrees_raw"])
        )
        max_joint_gap = max(max_joint_gap, gap_length)
        max_joint_angle_gap = max(max_joint_angle_gap, abs(angle_gap))
        joint_ok = gap_length <= 1e-6 and abs(angle_gap) <= 1e-6
        contour_ready = contour_ready and joint_ok
        joints.append(
            {
                "from_role": str(previous_segment["role"]),
                "to_role": str(segment["role"]),
                "gap_length": gap_length,
                "gap_vector": gap_vector,
                "angle_gap_degrees": angle_gap,
                "ok": joint_ok,
            }
        )
    return {
        "contour_ready": contour_ready,
        "joint_count": len(joints),
        "max_joint_gap": max_joint_gap,
        "max_joint_angle_gap": max_joint_angle_gap,
        "joints": joints,
    }


def _resolve_compression_spring_transition_trim_length(
    *,
    mean_diameter: float,
    wire_diameter: float,
    pitch: float,
) -> float:
    base_trim_length = max(
        0.85 * float(wire_diameter),
        0.46 * math.sqrt(float(mean_diameter) * float(wire_diameter)),
    )
    return min(0.85 * float(pitch), base_trim_length)


def _resolve_compression_spring_transition_fillet_radius(
    *,
    wire_diameter: float,
) -> float:
    return max(0.01, 0.375 * float(wire_diameter))


def _resolve_compression_spring_transition_connect_tension(
    *,
    mean_diameter: float,
    wire_diameter: float,
    pitch: float,
) -> float:
    base_tension = 2.03 * math.sqrt(max(float(mean_diameter) - 15.0, 0.0))
    pitch_ratio = float(pitch) / float(wire_diameter)
    pitch_adjustment = min(0.0, 0.8 * (pitch_ratio - 2.0))
    return max(0.0, min(15.0, base_tension + pitch_adjustment))


def _resolve_compression_spring_mean_diameter(
    params: dict[str, Any],
    *,
    wire_diameter: float,
) -> tuple[float, str]:
    outer_diameter = _optional_positive_float(
        params,
        "outer_diameter",
        "outer_diameter",
        "outside_diameter",
        "outer",
        "D1",
        "d1",
    )
    mean_diameter = _optional_positive_float(
        params,
        "mean_diameter",
        "mean_diameter",
        "coil_diameter",
        "diameter",
        "D",
    )
    inner_diameter = _optional_positive_float(
        params,
        "inner_diameter",
        "inner_diameter",
        "inside_diameter",
        "inner",
        "D2",
        "d2",
    )

    resolved_mean = mean_diameter
    resolved_mode = "mean"
    if outer_diameter is not None:
        candidate = float(outer_diameter) - float(wire_diameter)
        if candidate <= 0.0:
            raise ValueError("compression_spring outer_diameter must exceed wire_diameter")
        if resolved_mean is None:
            resolved_mean = candidate
            resolved_mode = "outer"
        elif abs(float(resolved_mean) - candidate) > 1e-6:
            raise ValueError("compression_spring diameter inputs are inconsistent")
    if inner_diameter is not None:
        candidate = float(inner_diameter) + float(wire_diameter)
        if resolved_mean is None:
            resolved_mean = candidate
            resolved_mode = "inner"
        elif abs(float(resolved_mean) - candidate) > 1e-6:
            raise ValueError("compression_spring diameter inputs are inconsistent")
    if resolved_mean is None:
        raise ValueError("compression_spring requires mean_diameter, outer_diameter, or inner_diameter")
    return float(resolved_mean), resolved_mode


def _normalize_external_conical_step_definition_mode(value: Any) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    resolved = EXTERNAL_CONICAL_STEP_DEFINITION_MODE_ALIASES.get(normalized, normalized)
    if resolved not in {
        "diameters_length",
        "diameters_angle",
        "diameters_conicity",
        "one_diameter_length_angle",
        "one_diameter_length_conicity",
    }:
        raise ValueError(f"Unsupported external_conical_step definition_mode: {value}")
    return resolved


def _normalize_internal_conical_step_axial_direction(value: Any) -> str:
    normalized = str(value or "forward").strip().lower().replace("-", "_")
    aliases = {
        "forward": "forward",
        "positive": "forward",
        "plus_x": "forward",
        "outward": "forward",
        "backward": "backward",
        "negative": "backward",
        "minus_x": "backward",
        "reverse": "backward",
        "inward": "backward",
    }
    resolved = aliases.get(normalized)
    if resolved is None:
        raise ValueError(f"Unsupported internal_conical_step axial_direction: {value}")
    return resolved


def _normalize_thread_direction(payload: dict[str, Any]) -> str:
    value = _coalesce_defined(
        payload,
        "direction",
        "thread_direction",
        "handedness",
        "thread_handedness",
        "left_thread",
    )
    if value is None:
        return "right"
    if isinstance(value, bool):
        return "left" if value else "right"
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "right": "right",
        "right_hand": "right",
        "right_handed": "right",
        "rh": "right",
        "правая": "right",
        "прав": "right",
        "left": "left",
        "left_hand": "left",
        "left_handed": "left",
        "lh": "left",
        "левая": "left",
        "лев": "left",
        "true": "left",
        "false": "right",
        "1": "left",
        "0": "right",
    }
    resolved = aliases.get(normalized)
    if resolved is None:
        raise ValueError(f"Unsupported thread direction: {value}")
    return resolved


def _normalize_cone_slope_direction(value: Any) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "outward": "outward",
        "expand": "outward",
        "expanding": "outward",
        "increase": "outward",
        "larger_at_end": "outward",
        "angle_out": "outward",
        "наружу": "outward",
        "inward": "inward",
        "contract": "inward",
        "contracting": "inward",
        "decrease": "inward",
        "smaller_at_end": "inward",
        "angle_in": "inward",
        "внутрь": "inward",
    }
    resolved = aliases.get(normalized, normalized)
    if resolved not in {"outward", "inward"}:
        raise ValueError(f"Unsupported cone slope_direction: {value}")
    return resolved


def _normalize_cone_angle_degrees(value: Any) -> float | None:
    if value in (None, ""):
        return None
    angle = _positive_float(value, "cone_angle_degrees")
    if angle >= 90.0:
        raise ValueError("cone_angle_degrees must be in range (0, 90)")
    return angle


def _normalize_conicity_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if ":" in text:
            left, right = text.split(":", 1)
            numerator = _positive_float(left, "conicity")
            denominator = _positive_float(right, "conicity")
            return numerator / denominator
        if "/" in text:
            left, right = text.split("/", 1)
            numerator = _positive_float(left, "conicity")
            denominator = _positive_float(right, "conicity")
            return numerator / denominator
    return _positive_float(value, "conicity")


def _normalize_face_ring_groove_wall_angle(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    angle = float(value)
    if angle < 0.0 or angle >= 89.0:
        raise ValueError("face_ring_groove wall angle must be in range [0, 89)")
    return angle


def _infer_external_conical_step_definition_mode(
    *,
    length: float | None,
    start_diameter: float | None,
    end_diameter: float | None,
    cone_angle_degrees: float | None,
    conicity: float | None,
) -> str:
    has_length = length is not None
    has_start = start_diameter is not None
    has_end = end_diameter is not None
    has_angle = cone_angle_degrees is not None
    has_conicity = conicity is not None
    if has_length and has_start and has_end and not has_angle and not has_conicity:
        return "diameters_length"
    if has_start and has_end and has_angle and not has_length and not has_conicity:
        return "diameters_angle"
    if has_start and has_end and has_conicity and not has_length and not has_angle:
        return "diameters_conicity"
    if has_length and has_angle and (has_start ^ has_end) and not has_conicity:
        return "one_diameter_length_angle"
    if has_length and has_conicity and (has_start ^ has_end) and not has_angle:
        return "one_diameter_length_conicity"
    raise ValueError(
        "external_conical_step requires one of: "
        "(length + start_diameter + end_diameter), "
        "(start_diameter + end_diameter + cone_angle_degrees), "
        "(start_diameter + end_diameter + conicity), "
        "(length + one end diameter + cone_angle_degrees), "
        "or (length + one end diameter + conicity)"
    )


def _resolve_external_conical_step_geometry(
    *,
    mode: str,
    length: float | None,
    start_diameter: float | None,
    end_diameter: float | None,
    cone_angle_degrees: float | None,
    conicity: float | None,
    slope_direction: str | None,
) -> dict[str, Any]:
    resolved_length = length
    resolved_start = start_diameter
    resolved_end = end_diameter

    if mode == "diameters_length":
        if resolved_length is None or resolved_start is None or resolved_end is None:
            raise ValueError("diameters_length mode requires length, start_diameter and end_diameter")
    elif mode == "diameters_angle":
        if resolved_start is None or resolved_end is None or cone_angle_degrees is None:
            raise ValueError("diameters_angle mode requires start_diameter, end_diameter and cone_angle_degrees")
        taper = math.tan(math.radians(cone_angle_degrees))
        if taper <= 0:
            raise ValueError("cone_angle_degrees must produce a positive taper")
        resolved_length = abs(resolved_start - resolved_end) / (2.0 * taper)
    elif mode == "diameters_conicity":
        if resolved_start is None or resolved_end is None or conicity is None:
            raise ValueError("diameters_conicity mode requires start_diameter, end_diameter and conicity")
        resolved_length = abs(resolved_start - resolved_end) / conicity
    elif mode == "one_diameter_length_angle":
        if resolved_length is None or cone_angle_degrees is None:
            raise ValueError("one_diameter_length_angle mode requires length and cone_angle_degrees")
        if (resolved_start is None) == (resolved_end is None):
            raise ValueError("one_diameter_length_angle mode requires exactly one end diameter")
        resolved_direction = slope_direction or "inward"
        delta_diameter = 2.0 * resolved_length * math.tan(math.radians(cone_angle_degrees))
        if resolved_start is not None:
            resolved_end = resolved_start + delta_diameter if resolved_direction == "outward" else resolved_start - delta_diameter
        else:
            resolved_start = resolved_end - delta_diameter if resolved_direction == "outward" else resolved_end + delta_diameter
        slope_direction = resolved_direction
    elif mode == "one_diameter_length_conicity":
        if resolved_length is None or conicity is None:
            raise ValueError("one_diameter_length_conicity mode requires length and conicity")
        if (resolved_start is None) == (resolved_end is None):
            raise ValueError("one_diameter_length_conicity mode requires exactly one end diameter")
        resolved_direction = slope_direction or "inward"
        delta_diameter = conicity * resolved_length
        if resolved_start is not None:
            resolved_end = resolved_start + delta_diameter if resolved_direction == "outward" else resolved_start - delta_diameter
        else:
            resolved_start = resolved_end - delta_diameter if resolved_direction == "outward" else resolved_end + delta_diameter
        slope_direction = resolved_direction
    else:
        raise ValueError(f"Unsupported external_conical_step definition_mode: {mode}")

    if resolved_length is None or resolved_start is None or resolved_end is None:
        raise ValueError("failed to resolve external_conical_step geometry")
    if resolved_start <= 0 or resolved_end <= 0:
        raise ValueError("external_conical_step requires positive end diameters after resolving the selected definition_mode")
    if abs(resolved_start - resolved_end) <= 1e-9:
        raise ValueError("external_conical_step requires different start_diameter and end_diameter")

    resolved_slope = "outward" if resolved_end > resolved_start else "inward"
    if slope_direction and slope_direction != resolved_slope and mode in {"diameters_length", "diameters_angle", "diameters_conicity"}:
        raise ValueError(
            "slope_direction does not match the provided start_diameter and end_diameter"
        )

    resolved_conicity = abs(resolved_end - resolved_start) / resolved_length
    resolved_cone_angle = math.degrees(math.atan(abs(resolved_end - resolved_start) / (2.0 * resolved_length)))
    return {
        "length": float(resolved_length),
        "start_diameter": float(resolved_start),
        "end_diameter": float(resolved_end),
        "cone_angle_degrees": float(resolved_cone_angle),
        "conicity": float(resolved_conicity),
        "slope_direction": resolved_slope,
    }


def _resolve_internal_conical_step_geometry(
    *,
    mode: str,
    length: float | None,
    start_diameter: float | None,
    end_diameter: float | None,
    cone_angle_degrees: float | None,
    conicity: float | None,
    slope_direction: str | None,
) -> dict[str, Any]:
    try:
        return _resolve_external_conical_step_geometry(
            mode=mode,
            length=length,
            start_diameter=start_diameter,
            end_diameter=end_diameter,
            cone_angle_degrees=cone_angle_degrees,
            conicity=conicity,
            slope_direction=slope_direction,
        )
    except ValueError as exc:
        raise ValueError(str(exc).replace("external_conical_step", "internal_conical_step")) from exc


def _normalize_xyz_triplet(value: Any, *, field_name: str = "origin") -> list[float]:
    payload = value
    if isinstance(payload, dict):
        payload = [payload.get("x", 0.0), payload.get("y", 0.0), payload.get("z", 0.0)]
    if not isinstance(payload, (list, tuple)) or len(payload) != 3:
        raise ValueError(f"{field_name} must be [x, y, z]")
    try:
        return [float(payload[0]), float(payload[1]), float(payload[2])]
    except Exception as exc:
        raise ValueError(f"{field_name} must contain numeric values") from exc


def _normalize_offset_triplet(value: Any) -> list[float]:
    payload = value or {}
    if isinstance(payload, dict) and "offset" in payload:
        payload = payload.get("offset")
    if isinstance(payload, dict):
        payload = [payload.get("dx", payload.get("x", 0.0)), payload.get("dy", payload.get("y", 0.0)), payload.get("dz", payload.get("z", 0.0))]
    if not isinstance(payload, (list, tuple)) or len(payload) != 3:
        raise ValueError("offset must be [dx, dy, dz]")
    try:
        return [float(payload[0]), float(payload[1]), float(payload[2])]
    except Exception as exc:
        raise ValueError("offset must contain numeric values") from exc


def _normalize_lcs_system_object(value: Any) -> str | None:
    if value in (None, ""):
        return None
    system_object = str(value).strip().lower().replace("-", "_")
    aliases = {
        "xoy_plane": "xoy_plane",
        "xy_plane": "xoy_plane",
        "plane_xoy": "xoy_plane",
        "xoz_plane": "xoz_plane",
        "zx_plane": "xoz_plane",
        "plane_xoz": "xoz_plane",
        "yoz_plane": "yoz_plane",
        "zy_plane": "yoz_plane",
        "plane_yoz": "yoz_plane",
        "origin": "origin",
        "origin_point": "origin",
        "global_origin": "origin",
    }
    normalized = aliases.get(system_object)
    if normalized is None:
        raise ValueError(f"Unsupported lcs object reference: {value}")
    return normalized


def _normalize_operation_output_key(scenario: str, output_key: str) -> str:
    normalized_scenario = _normalize_scenario(scenario)
    key = str(output_key or "").strip().lower().replace("-", "_")
    if normalized_scenario == "stepped_shaft":
        if key in {"axis", "body", "sketch"}:
            return key
        return _normalize_stepped_shaft_face_selector(key)
    if normalized_scenario == "external_conical_step":
        aliases = {
            "body": "body",
            "sketch": "sketch",
            "axis": "axis",
            "start_face": "start_face",
            "end_face": "end_face",
            "far_end_face": "end_face",
            "outer_face": "outer_face",
            "outer_conical_face": "outer_face",
            "conical_face": "outer_face",
            "lateral_face": "outer_face",
        }
        normalized = aliases.get(key, key)
        if normalized not in {"body", "sketch", "axis", "start_face", "end_face", "outer_face"}:
            raise ValueError(f"Unsupported external_conical_step output: {output_key}")
        return normalized
    if normalized_scenario == "internal_conical_step":
        aliases = {
            "body": "body",
            "sketch": "sketch",
            "axis": "axis",
            "start_face": "start_face",
            "end_face": "end_face",
            "inner_face": "inner_face",
            "inner_conical_face": "inner_face",
            "conical_face": "inner_face",
            "lateral_face": "inner_face",
        }
        normalized = aliases.get(key, key)
        if normalized not in {"body", "sketch", "axis", "start_face", "end_face", "inner_face"}:
            raise ValueError(f"Unsupported internal_conical_step output: {output_key}")
        return normalized
    if normalized_scenario == "internal_cylindrical_step":
        if key in {"body", "sketch", "axis"}:
            return key
        return _normalize_internal_cylindrical_step_face_selector(key)
    if normalized_scenario == "external_polygonal_step":
        aliases = {
            "body": "body",
            "sketch": "sketch",
            "start_face": "start_face",
            "end_face": "end_face",
            "far_end_face": "end_face",
            "side_face_1": "side_face_1",
            "outer_face_1": "side_face_1",
            "first_side_face": "side_face_1",
        }
        normalized = aliases.get(key, key)
        if normalized not in {"body", "sketch", "start_face", "end_face", "side_face_1"}:
            raise ValueError(f"Unsupported external_polygonal_step output: {output_key}")
        return normalized
    if normalized_scenario == "internal_polygonal_step":
        aliases = {
            "body": "body",
            "sketch": "sketch",
            "start_face": "start_face",
            "end_face": "end_face",
            "far_end_face": "end_face",
            "side_face_1": "side_face_1",
            "inner_face_1": "side_face_1",
            "first_side_face": "side_face_1",
        }
        normalized = aliases.get(key, key)
        if normalized not in {"body", "sketch", "start_face", "end_face", "side_face_1"}:
            raise ValueError(f"Unsupported internal_polygonal_step output: {output_key}")
        return normalized
    if normalized_scenario == "external_flat_step":
        aliases = {
            "body": "body",
            "sketch": "sketch",
            "start_face": "start_face",
            "end_face": "end_face",
            "far_end_face": "end_face",
            "flat_1_face": "flat_1_face",
            "first_flat_face": "flat_1_face",
            "flat_2_face": "flat_2_face",
            "second_flat_face": "flat_2_face",
        }
        normalized = aliases.get(key, key)
        if normalized not in {"body", "sketch", "start_face", "end_face", "flat_1_face", "flat_2_face"}:
            raise ValueError(f"Unsupported external_flat_step output: {output_key}")
        return normalized
    if normalized_scenario == "internal_flat_step":
        aliases = {
            "body": "body",
            "sketch": "sketch",
            "start_face": "start_face",
            "end_face": "end_face",
            "far_end_face": "end_face",
            "flat_1_face": "flat_1_face",
            "first_flat_face": "flat_1_face",
            "flat_2_face": "flat_2_face",
            "second_flat_face": "flat_2_face",
        }
        normalized = aliases.get(key, key)
        if normalized not in {"body", "sketch", "start_face", "end_face", "flat_1_face", "flat_2_face"}:
            raise ValueError(f"Unsupported internal_flat_step output: {output_key}")
        return normalized
    if normalized_scenario in {"external_helical_thread", "internal_helical_thread"}:
        aliases = {
            "body": "body",
            "thread": "thread",
            "thread_feature": "thread",
            "spiral": "spiral",
            "path": "spiral",
            "profile_sketch": "profile_sketch",
            "thread_profile": "profile_sketch",
            "base_face": "base_face",
            "source_face": "base_face",
            "start_face": "start_face",
            "entry_face": "start_face",
            "end_face": "end_face",
            "exit_face": "end_face",
        }
        normalized = aliases.get(key, key)
        if normalized not in {"body", "thread", "spiral", "profile_sketch", "base_face", "start_face", "end_face"}:
            raise ValueError(f"Unsupported {normalized_scenario} output: {output_key}")
        return normalized
    if normalized_scenario in {"external_threaded_step", "internal_threaded_step"}:
        aliases = {
            "body": "body",
            "thread": "thread",
            "base_face": "base_face",
            "thread_face": "base_face",
            "source_face": "base_face",
            "start_border": "start_border",
            "start_face": "start_border",
            "end_border": "end_border",
            "end_face": "end_border",
        }
        normalized = aliases.get(key, key)
        if normalized not in {"body", "thread", "base_face", "start_border", "end_border"}:
            raise ValueError(f"Unsupported {normalized_scenario} output: {output_key}")
        return normalized
    if normalized_scenario == "face_ring_groove":
        aliases = {
            "body": "body",
            "sketch": "sketch",
            "axis": "axis",
            "bottom_face": "bottom_face",
            "inner_wall_face": "inner_wall_face",
            "inner_face": "inner_wall_face",
            "outer_wall_face": "outer_wall_face",
            "outer_face": "outer_wall_face",
        }
        normalized = aliases.get(key, key)
        if normalized not in {"body", "sketch", "axis", "bottom_face", "inner_wall_face", "outer_wall_face"}:
            raise ValueError(f"Unsupported face_ring_groove output: {output_key}")
        return normalized
    if normalized_scenario == "bolt_circle_holes":
        aliases = {
            "body": "body",
            "axis": "axis",
            "pattern_axis": "axis",
            "first_hole_center": "first_hole_center",
            "first_center": "first_hole_center",
            "first_hole_lcs": "first_hole_lcs",
            "hole_lcs": "first_hole_lcs",
        }
        normalized = aliases.get(key, key)
        if normalized not in {"body", "axis", "first_hole_center", "first_hole_lcs"}:
            raise ValueError(f"Unsupported bolt_circle_holes output: {output_key}")
        return normalized
    if normalized_scenario == "point":
        aliases = {
            "point": "point",
            "origin": "point",
            "reference_point": "point",
        }
        normalized = aliases.get(key, key)
        if normalized != "point":
            raise ValueError(f"Unsupported point output: {output_key}")
        return normalized
    if normalized_scenario == "lcs":
        aliases = {
            "lcs": "lcs",
            "csys": "lcs",
            "coordinate_system": "lcs",
            "placement_ref": "lcs",
        }
        normalized = aliases.get(key, key)
        if normalized != "lcs":
            raise ValueError(f"Unsupported lcs output: {output_key}")
        return normalized
    return key


def _normalize_stepped_shaft_face_selector(value: Any) -> str:
    selector = str(value or "far_end_face").strip().lower().replace("-", "_")
    aliases = {
        "far_end_face": "far_end_face",
        "end_face": "far_end_face",
        "tail_face": "far_end_face",
        "tail_end_face": "far_end_face",
        "near_end_face": "start_face",
        "start_face": "start_face",
        "head_face": "start_face",
        "front_face": "start_face",
    }
    normalized = aliases.get(selector, selector)
    if _parse_stepped_shaft_face_selector(normalized) is None:
        raise ValueError(f"Unsupported stepped_shaft face selector: {value}")
    return normalized


_STEP_INNER_FACE_PATTERN = re.compile(r"^step_(\d+)_(inner|inner_cylindrical|cyl|cylindrical)_face$")
_STEP_INNER_FACE_PATTERN_COMPACT = re.compile(r"^step(\d+)_(inner|inner_cylindrical|cyl|cylindrical)_face$")


def _parse_internal_cylindrical_step_face_selector(selector: str) -> dict[str, Any] | None:
    normalized = str(selector or "").strip().lower().replace("-", "_")
    if normalized == "start_face":
        return {"selector": "start_face", "kind": "boundary", "boundary_index": 0}
    if normalized == "end_face":
        return {"selector": "end_face", "kind": "boundary", "boundary_index": -1}
    if normalized == "inner_face":
        return {"selector": "inner_face", "kind": "step_inner_face", "step_index": 1, "boundary_index": None}
    for pattern in (_STEP_FACE_PATTERN, _STEP_FACE_PATTERN_COMPACT):
        match = pattern.fullmatch(normalized)
        if match:
            step_index = int(match.group(1))
            position = str(match.group(2))
            boundary_index = step_index - 1 if position == "start" else step_index
            return {
                "selector": f"step_{step_index}_{position}_face",
                "kind": "step_face",
                "step_index": step_index,
                "position": position,
                "boundary_index": boundary_index,
            }
    for pattern in (_SHOULDER_FACE_PATTERN, _SHOULDER_FACE_PATTERN_COMPACT):
        match = pattern.fullmatch(normalized)
        if match:
            shoulder_index = int(match.group(1))
            return {
                "selector": f"shoulder_{shoulder_index}_face",
                "kind": "shoulder_face",
                "shoulder_index": shoulder_index,
                "boundary_index": shoulder_index,
            }
    for pattern in (_STEP_INNER_FACE_PATTERN, _STEP_INNER_FACE_PATTERN_COMPACT):
        match = pattern.fullmatch(normalized)
        if match:
            step_index = int(match.group(1))
            return {
                "selector": f"step_{step_index}_inner_face",
                "kind": "step_inner_face",
                "step_index": step_index,
                "boundary_index": None,
            }
    return None


def _normalize_internal_cylindrical_step_face_selector(value: Any) -> str:
    selector = str(value or "inner_face").strip().lower().replace("-", "_")
    aliases = {
        "start_face": "start_face",
        "entry_face": "start_face",
        "end_face": "end_face",
        "far_end_face": "end_face",
        "tail_face": "end_face",
        "inner_face": "inner_face",
        "inner_cylindrical_face": "inner_face",
        "cylindrical_face": "inner_face",
        "lateral_face": "inner_face",
    }
    normalized = aliases.get(selector, selector)
    if _parse_internal_cylindrical_step_face_selector(normalized) is None:
        raise ValueError(f"Unsupported internal_cylindrical_step face selector: {value}")
    return normalized


def _normalize_face_ring_groove_face_selector(value: Any) -> str:
    selector = str(value or "bottom_face").strip().lower().replace("-", "_")
    aliases = {
        "bottom_face": "bottom_face",
        "groove_bottom_face": "bottom_face",
        "inner_wall_face": "inner_wall_face",
        "inner_face": "inner_wall_face",
        "outer_wall_face": "outer_wall_face",
        "outer_face": "outer_wall_face",
    }
    normalized = aliases.get(selector, selector)
    if normalized not in {"bottom_face", "inner_wall_face", "outer_wall_face"}:
        raise ValueError(f"Unsupported face_ring_groove face selector: {value}")
    return normalized


def _normalize_stepped_shaft_reference_selector(
    value: Any,
    *,
    source_preview: dict[str, Any] | None = None,
    field_name: str = "reference.selector",
) -> str:
    try:
        return _normalize_stepped_shaft_face_selector(value)
    except ValueError as exc:
        raise ValueError(
            "%s uses unsupported stepped_shaft selector %s; available selectors: %s"
            % (
                field_name,
                str(value or "").strip() or "<empty>",
                _format_stepped_shaft_selector_choices(_list_stepped_shaft_selector_choices(source_preview)),
            )
        ) from exc


def _resolve_stepped_shaft_selector_origin(selector: str, source_preview: dict[str, Any]) -> list[float]:
    anchors = ((source_preview or {}).get("interface") or {}).get("anchors") or {}
    selector_info = _parse_stepped_shaft_face_selector(selector)
    if selector_info is None:
        raise ValueError(
            "Stepped_shaft selector %s is unsupported; available selectors: %s"
            % (
                selector,
                _format_stepped_shaft_selector_choices(_list_stepped_shaft_selector_choices(source_preview)),
            )
        )
    selector_points = dict(anchors.get("selector_points") or {})
    preview_selectors = (source_preview or {}).get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    selector_key = str(selector_info["selector"])
    if selector_key in selector_points:
        return _normalize_xyz_triplet(selector_points[selector_key], field_name=f"reference.selector[{selector}]")
    params = (source_preview or {}).get("params") or {}
    boundary_points = _build_stepped_shaft_boundary_points(params, anchors)
    boundary_index = int(selector_info["boundary_index"])
    if boundary_index == -1:
        boundary_index = len(boundary_points) - 1
    if boundary_index < 0 or boundary_index >= len(boundary_points):
        raise ValueError(
            "Stepped_shaft selector %s is out of range for the source body; available selectors: %s"
            % (
                selector,
                _format_stepped_shaft_selector_choices(_list_stepped_shaft_selector_choices(source_preview)),
            )
        )
    point = boundary_points[boundary_index]
    if isinstance(point, (list, tuple)) and len(point) == 2:
        point = [point[0], point[1], 0.0]
    return _normalize_xyz_triplet(point, field_name=f"reference.selector[{selector}]")


_STEP_FACE_PATTERN = re.compile(r"^step_(\d+)_(start|end)_face$")
_STEP_FACE_PATTERN_COMPACT = re.compile(r"^step(\d+)_(start|end)_face$")
_SHOULDER_FACE_PATTERN = re.compile(r"^shoulder_(\d+)_face$")
_SHOULDER_FACE_PATTERN_COMPACT = re.compile(r"^shoulder(\d+)_face$")
_STEP_OUTER_FACE_PATTERN = re.compile(r"^step_(\d+)_(outer|side|cyl|cylindrical)_face$")
_STEP_OUTER_FACE_PATTERN_COMPACT = re.compile(r"^step(\d+)_(outer|side|cyl|cylindrical)_face$")
_STEP_INNER_FACE_PATTERN = re.compile(r"^step_(\d+)_(inner|bore|cyl|cylindrical)_face$")
_STEP_INNER_FACE_PATTERN_COMPACT = re.compile(r"^step(\d+)_(inner|bore|cyl|cylindrical)_face$")


def _parse_stepped_shaft_face_selector(selector: str) -> dict[str, Any] | None:
    normalized = str(selector or "").strip().lower().replace("-", "_")
    if normalized == "start_face":
        return {"selector": "start_face", "kind": "boundary", "boundary_index": 0}
    if normalized == "far_end_face":
        return {"selector": "far_end_face", "kind": "boundary", "boundary_index": -1}
    for pattern in (_STEP_FACE_PATTERN, _STEP_FACE_PATTERN_COMPACT):
        match = pattern.fullmatch(normalized)
        if match:
            step_index = int(match.group(1))
            position = str(match.group(2))
            boundary_index = step_index - 1 if position == "start" else step_index
            return {
                "selector": f"step_{step_index}_{position}_face",
                "kind": "step_face",
                "step_index": step_index,
                "position": position,
                "boundary_index": boundary_index,
            }
    for pattern in (_SHOULDER_FACE_PATTERN, _SHOULDER_FACE_PATTERN_COMPACT):
        match = pattern.fullmatch(normalized)
        if match:
            shoulder_index = int(match.group(1))
            return {
                "selector": f"shoulder_{shoulder_index}_face",
                "kind": "shoulder_face",
                "shoulder_index": shoulder_index,
                "boundary_index": shoulder_index,
            }
    for pattern in (_STEP_OUTER_FACE_PATTERN, _STEP_OUTER_FACE_PATTERN_COMPACT):
        match = pattern.fullmatch(normalized)
        if match:
            step_index = int(match.group(1))
            return {
                "selector": f"step_{step_index}_outer_face",
                "kind": "step_outer_face",
                "step_index": step_index,
                "boundary_index": None,
            }
    return None


def _parse_internal_cylindrical_step_face_selector(selector: str) -> dict[str, Any] | None:
    normalized = str(selector or "").strip().lower().replace("-", "_")
    if normalized in ("start_face", "entry_face"):
        return {"selector": "start_face", "kind": "boundary", "boundary_index": 0}
    if normalized in ("end_face", "tail_face", "far_end_face"):
        return {"selector": "end_face", "kind": "boundary", "boundary_index": -1}
    if normalized in ("inner_face", "inner_cylindrical_face", "cylindrical_face", "lateral_face"):
        return {"selector": "inner_face", "kind": "segment_face", "step_index": 1}
    for pattern in (_STEP_FACE_PATTERN, _STEP_FACE_PATTERN_COMPACT):
        match = pattern.fullmatch(normalized)
        if match:
            step_index = int(match.group(1))
            position = str(match.group(2))
            boundary_index = step_index - 1 if position == "start" else step_index
            return {
                "selector": f"step_{step_index}_{position}_face",
                "kind": "step_face",
                "step_index": step_index,
                "position": position,
                "boundary_index": boundary_index,
            }
    for pattern in (_SHOULDER_FACE_PATTERN, _SHOULDER_FACE_PATTERN_COMPACT):
        match = pattern.fullmatch(normalized)
        if match:
            shoulder_index = int(match.group(1))
            return {
                "selector": f"shoulder_{shoulder_index}_face",
                "kind": "shoulder_face",
                "step_index": shoulder_index,
                "boundary_index": shoulder_index,
            }
    for pattern in (_STEP_INNER_FACE_PATTERN, _STEP_INNER_FACE_PATTERN_COMPACT):
        match = pattern.fullmatch(normalized)
        if match:
            step_index = int(match.group(1))
            return {
                "selector": f"step_{step_index}_inner_face",
                "kind": "segment_face",
                "step_index": step_index,
            }
    return None


def _normalize_external_conical_thread_base_selector(value: Any) -> str:
    normalized = str(value or "outer_face").strip().lower().replace("-", "_")
    aliases = {
        "outer_face": "outer_face",
        "outer_conical_face": "outer_face",
        "conical_face": "outer_face",
        "lateral_face": "outer_face",
    }
    resolved = aliases.get(normalized, normalized)
    if resolved != "outer_face":
        raise ValueError(f"Unsupported external_conical_step base face selector: {value}")
    return resolved


def _normalize_internal_conical_thread_base_selector(value: Any) -> str:
    normalized = str(value or "inner_face").strip().lower().replace("-", "_")
    aliases = {
        "inner_face": "inner_face",
        "inner_conical_face": "inner_face",
        "conical_face": "inner_face",
        "lateral_face": "inner_face",
    }
    resolved = aliases.get(normalized, normalized)
    if resolved != "inner_face":
        raise ValueError(f"Unsupported internal_conical_step base face selector: {value}")
    return resolved


def _normalize_conical_thread_boundary_selector(value: Any) -> str:
    normalized = str(value or "end_face").strip().lower().replace("-", "_")
    aliases = {
        "start_face": "start_face",
        "near_end_face": "start_face",
        "front_face": "start_face",
        "large_end_face": "start_face",
        "seat_face": "start_face",
        "shoulder_face": "start_face",
        "gauge_face": "start_face",
        "end_face": "end_face",
        "far_end_face": "end_face",
        "tail_face": "end_face",
        "small_end_face": "end_face",
        "free_end_face": "end_face",
        "nose_face": "end_face",
        "tip_face": "end_face",
    }
    resolved = aliases.get(normalized, normalized)
    if resolved not in {"start_face", "end_face"}:
        raise ValueError(f"Unsupported conical thread boundary selector: {value}")
    return resolved


def _normalize_thread_source_selector(
    source_scenario: str,
    selector: Any,
    *,
    internal: bool,
    scenario_label: str | None = None,
) -> str:
    label = scenario_label or ("internal_threaded_step" if internal else "external_threaded_step")
    if source_scenario == "stepped_shaft":
        normalized = _normalize_stepped_shaft_face_selector(selector or "step_1_outer_face")
        selector_info = _parse_stepped_shaft_face_selector(normalized)
        if selector_info is None or selector_info.get("kind") != "step_outer_face":
            raise ValueError(f"{label} requires a stepped_shaft outer cylindrical face selector")
        return normalized
    if source_scenario == "internal_cylindrical_step":
        normalized = _normalize_internal_cylindrical_step_face_selector(selector or "inner_face")
        selector_info = _parse_internal_cylindrical_step_face_selector(normalized)
        if selector_info is None or selector_info.get("kind") not in {"segment_face", "step_inner_face"}:
            raise ValueError(f"{label} requires an internal_cylindrical_step inner cylindrical face selector")
        return normalized
    if source_scenario == "external_conical_step":
        if internal:
            raise ValueError(f"{label} cannot use external_conical_step as source_scenario")
        return _normalize_external_conical_thread_base_selector(selector)
    if source_scenario == "internal_conical_step":
        if not internal:
            raise ValueError(f"{label} cannot use internal_conical_step as source_scenario")
        return _normalize_internal_conical_thread_base_selector(selector)
    raise ValueError(f"Unsupported {label} source_scenario: {source_scenario}")


def _default_thread_boundary_selectors(
    source_scenario: str,
    source_selector: str,
    *,
    internal: bool,
) -> tuple[str, str]:
    if source_scenario == "stepped_shaft":
        selector_info = _parse_stepped_shaft_face_selector(source_selector)
        if selector_info is not None and selector_info.get("kind") == "step_outer_face":
            step_index = int(selector_info["step_index"])
            return f"step_{step_index}_start_face", f"step_{step_index}_end_face"
    if source_scenario == "internal_cylindrical_step":
        selector_info = _parse_internal_cylindrical_step_face_selector(source_selector)
        if selector_info is not None and selector_info.get("kind") in {"segment_face", "step_inner_face"}:
            step_index = int(selector_info["step_index"])
            return f"step_{step_index}_start_face", f"step_{step_index}_end_face"
    if source_scenario == "external_conical_step" and not internal:
        return "end_face", "start_face"
    return "start_face", "end_face"


def _resolve_thread_source_carrier_diameter(
    source_scenario: str,
    source_preview: dict[str, Any],
    source_selector: str,
) -> float | None:
    params = dict(source_preview.get("params") or {})
    if source_scenario == "stepped_shaft":
        selector_info = _parse_stepped_shaft_face_selector(source_selector)
        if selector_info is None or selector_info.get("kind") != "step_outer_face":
            return None
        step_index = int(selector_info["step_index"]) - 1
        steps = list(params.get("steps") or [])
        if step_index < 0 or step_index >= len(steps):
            return None
        value = steps[step_index].get("diameter")
        return float(value) if isinstance(value, int | float) else None
    if source_scenario == "internal_cylindrical_step":
        selector_info = _parse_internal_cylindrical_step_face_selector(source_selector)
        if selector_info is None or selector_info.get("kind") not in {"segment_face", "step_inner_face"}:
            return None
        step_index = int(selector_info["step_index"]) - 1
        steps = list(params.get("steps") or [])
        if step_index < 0 or step_index >= len(steps):
            return None
        value = steps[step_index].get("diameter")
        return float(value) if isinstance(value, int | float) else None
    if source_scenario in {"external_conical_step", "internal_conical_step"}:
        value = params.get("start_diameter")
        return float(value) if isinstance(value, int | float) else None
    return None


def _validate_external_conical_thread_orientation(
    *,
    scenario: str,
    source_preview: dict[str, Any],
    start_selector: str,
    end_selector: str,
    start_origin: list[float] | None,
    end_origin: list[float] | None,
) -> None:
    source_params_payload = dict(source_preview.get("params") or {})
    source_slope_direction = str(source_params_payload.get("slope_direction") or "").strip().lower()
    if source_slope_direction and source_slope_direction != "inward":
        raise ValueError(f"{scenario} external conical thread source must taper inward from start_face to end_face")
    if start_selector != "end_face" or end_selector != "start_face":
        raise ValueError(
            f"{scenario} external conical thread must run from end_face "
            f"(small/free entry end) to start_face (large/seat end)"
        )
    if start_origin is not None and end_origin is not None and float(end_origin[0]) >= float(start_origin[0]):
        raise ValueError(
            f"{scenario} external conical thread requires start_face to stay before end_face along the cone axis"
        )


def _resolve_conical_thread_span_diameters(
    source_preview: dict[str, Any],
    *,
    start_selector: str,
    end_selector: str,
    thread_length: float,
    source_span_length: float | None,
) -> dict[str, float] | None:
    params = dict(source_preview.get("params") or {})
    start_diameter_raw = params.get("start_diameter")
    end_diameter_raw = params.get("end_diameter")
    if not isinstance(start_diameter_raw, int | float) or not isinstance(end_diameter_raw, int | float):
        return None
    full_span_length = source_span_length
    if full_span_length is None:
        length_raw = params.get("length")
        if isinstance(length_raw, int | float):
            full_span_length = float(length_raw)
    if full_span_length is None or float(full_span_length) <= 0.0:
        return None

    selector_positions = {
        "start_face": 0.0,
        "end_face": float(full_span_length),
    }
    if start_selector not in selector_positions or end_selector not in selector_positions:
        return None

    axis_start = float(selector_positions[start_selector])
    axis_target = float(selector_positions[end_selector])
    axis_direction = 1.0 if axis_target >= axis_start else -1.0
    axis_end = axis_start + axis_direction * float(thread_length)
    slope = (float(end_diameter_raw) - float(start_diameter_raw)) / float(full_span_length)

    def _diameter_at(axis_position: float) -> float:
        return float(start_diameter_raw) + slope * float(axis_position)

    return {
        "source_start_diameter": float(start_diameter_raw),
        "source_end_diameter": float(end_diameter_raw),
        "thread_start_axis": axis_start,
        "thread_end_axis": axis_end,
        "thread_start_diameter": _diameter_at(axis_start),
        "thread_end_diameter": _diameter_at(axis_end),
        "diameter_slope": slope,
    }


def _normalize_thread_boundary_selector(source_scenario: str, selector: Any, *, default_selector: str) -> str:
    if source_scenario == "stepped_shaft":
        normalized = _normalize_stepped_shaft_face_selector(selector or default_selector)
        selector_info = _parse_stepped_shaft_face_selector(normalized)
        if selector_info is None or selector_info.get("kind") not in {"boundary", "step_face"}:
            raise ValueError(f"Unsupported stepped_shaft thread boundary selector: {selector}")
        return normalized
    if source_scenario == "internal_cylindrical_step":
        normalized = _normalize_internal_cylindrical_step_face_selector(selector or default_selector)
        selector_info = _parse_internal_cylindrical_step_face_selector(normalized)
        if selector_info is None or selector_info.get("kind") not in {"boundary", "step_face"}:
            raise ValueError(f"Unsupported internal_cylindrical_step thread boundary selector: {selector}")
        return normalized
    return _normalize_conical_thread_boundary_selector(selector or default_selector)


def _resolve_thread_preview_output(source_preview: dict[str, Any], selector: str, *, field_name: str) -> dict[str, Any]:
    outputs = (((source_preview or {}).get("interface") or {}).get("outputs") or {})
    if selector in outputs:
        return dict(outputs[selector] or {})
    for payload in outputs.values():
        if isinstance(payload, dict) and str(payload.get("selector") or "").strip() == selector:
            return dict(payload)
    raise ValueError(f"Threaded step {field_name} selector is unavailable in source preview: {selector}")


def _resolve_thread_output_origin(output_payload: dict[str, Any]) -> list[float] | None:
    origin = output_payload.get("origin")
    if not isinstance(origin, list) or len(origin) != 3:
        return None
    try:
        return [float(origin[0]), float(origin[1]), float(origin[2])]
    except Exception:
        return None


def _build_thread_output_payload(selector: str, origin: list[float] | None) -> dict[str, Any]:
    payload = {
        "type": "face",
        "selector": selector,
        "live_supported": True,
    }
    if origin is not None:
        payload["origin"] = origin
    return payload


def _build_threaded_step_interface(normalized: dict[str, Any], *, scenario: str) -> dict[str, Any]:
    outputs = {
        "body": {"type": "body", "name": "body", "live_supported": True},
        "thread": {"type": "thread", "name": "thread", "live_supported": True},
        "base_face": _build_thread_output_payload(normalized["source_selector"], normalized["source_origin"]),
        "start_border": _build_thread_output_payload(normalized["start_selector"], normalized["start_origin"]),
        "end_border": _build_thread_output_payload(normalized["end_selector"], normalized["end_origin"]),
    }
    selector_points = {}
    if normalized["source_origin"] is not None:
        selector_points["base_face"] = list(normalized["source_origin"])
    if normalized["start_origin"] is not None:
        selector_points["start_border"] = list(normalized["start_origin"])
    if normalized["end_origin"] is not None:
        selector_points["end_border"] = list(normalized["end_origin"])
    return {
        "feature_type": f"cosmetic_thread.{scenario}",
        "source_scenario": normalized["source_scenario"],
        "outputs": outputs,
        "anchors": {
            "selector_points": selector_points,
        },
    }


def _preview_threaded_step(normalized: dict[str, Any], *, scenario: str) -> dict[str, Any]:
    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        },
        {
            "operation": "create_source_body",
            "source_scenario": normalized["source_scenario"],
            "summary": (normalized["source_preview"] or {}).get("summary") or {},
            "description": "Create the source body used for cosmetic thread placement",
            "live_status": "planned",
        },
        {
            "operation": "add_thread",
            "source_selector": normalized["source_selector"],
            "start_selector": normalized["start_selector"],
            "end_selector": normalized["end_selector"],
            "diameter": normalized["diameter"],
            "pitch": normalized["pitch"],
            "standard_table_name": normalized["thread_standard_table_name"],
            "standard_display_name": normalized["thread_standard_display_name"],
            "designation": normalized["thread_designation"],
            "depth": normalized["thread_depth"],
            "direction": normalized["direction"],
            "left_thread": normalized["left_thread"],
            "auto_diameter": normalized["auto_diameter"],
            "auto_length": normalized["auto_length"],
            "live_status": "planned",
        },
    ]
    return {
        "scenario": scenario,
        "ok": True,
        "params": normalized,
        "summary": {
            "source_scenario": normalized["source_scenario"],
            "source_selector": normalized["source_selector"],
            "start_selector": normalized["start_selector"],
            "end_selector": normalized["end_selector"],
            "diameter": normalized["diameter"],
            "pitch": normalized["pitch"],
            "depth": normalized["thread_depth"],
            "thread_length": normalized["thread_length"],
            "direction": normalized["direction"],
            "thread_designation": normalized["thread_designation"],
            "thread_standard_table_name": normalized["thread_standard_table_name"],
            "thread_standard_display_name": normalized["thread_standard_display_name"],
            "auto_length": normalized["auto_length"],
            "auto_diameter": normalized["auto_diameter"],
            "left_thread": normalized["left_thread"],
            "internal": normalized["internal"],
            "creation_status": "available",
        },
        "interface": _build_threaded_step_interface(normalized, scenario=scenario),
        "operations": operations,
    }


def _build_helical_thread_interface(normalized: dict[str, Any], *, scenario: str) -> dict[str, Any]:
    profile_variables = list(normalized.get("profile_variables") or [])
    outputs = {
        "body": {"type": "body", "name": "body", "live_supported": True},
        "thread": {"type": "feature", "name": "thread", "live_supported": True},
        "spiral": {"type": "curve", "name": "spiral", "live_supported": True},
        "profile_sketch": {"type": "sketch", "name": "profile_sketch", "live_supported": True},
        "base_face": _build_thread_output_payload(normalized["source_selector"], normalized["source_origin"]),
        "start_face": _build_thread_output_payload(normalized["start_selector"], normalized["start_origin"]),
        "end_face": _build_thread_output_payload(normalized["end_selector"], normalized["end_origin"]),
    }
    selector_points = {}
    if normalized["source_origin"] is not None:
        selector_points["base_face"] = list(normalized["source_origin"])
    if normalized["start_origin"] is not None:
        selector_points["start_face"] = list(normalized["start_origin"])
    if normalized["end_origin"] is not None:
        selector_points["end_face"] = list(normalized["end_origin"])
    return {
        "feature_type": f"helical_thread.{scenario}",
        "parameter_namespace": normalized["parameter_prefix"],
        "operation_label": normalized["operation_label"],
        "source_scenario": normalized["source_scenario"],
        "parameters": {
            "profile_variables": [str(item.get("name") or "") for item in profile_variables if str(item.get("name") or "").strip()],
            "public_profile_variables": [str(item) for item in (normalized.get("public_profile_variables") or []) if str(item or "").strip()],
            "profile_dimension_variables": [str(item.get("variable") or "") for item in (normalized.get("profile_dimensions") or []) if str(item.get("variable") or "").strip()],
            "operation_variable_bindings": list(normalized.get("operation_variable_bindings") or []),
            "source_variable_bindings": list(normalized.get("source_variable_bindings") or []),
        },
        "outputs": outputs,
        "anchors": {
            "selector_points": selector_points,
        },
    }


def _preview_helical_thread(normalized: dict[str, Any], *, scenario: str) -> dict[str, Any]:
    crest_round_pass = dict(normalized.get("crest_round_pass") or {})
    profile_operation = {
        "operation": "create_thread_profile",
        "depth": normalized["thread_depth"],
        "clearance": normalized["clearance"],
        "fundamental_triangle_height": normalized["fundamental_triangle_height"],
        "profile_entry_offset": normalized["profile_entry_offset"],
        "profile_taper_compensation_radius": normalized.get("profile_taper_compensation_radius", 0.0),
        "profile_surface_offset": normalized["profile_surface_offset"],
        "profile_surface_offset_effective": normalized["profile_surface_offset_effective"],
        "profile_surface_offset_applied": normalized["profile_surface_offset_applied"],
        "profile_surface_offset_status": normalized["profile_surface_offset_status"],
        "profile_surface_offset_note": normalized["profile_surface_offset_note"],
        "profile_sketch_origin_shift": normalized["profile_sketch_origin_shift"],
        "profile_angle_degrees": normalized["profile_angle_degrees"],
        "profile_root_shape": normalized["profile_root_shape"],
        "carrier_shape": normalized.get("carrier_shape", "cylindrical"),
        "carrier_taper": dict(normalized.get("carrier_taper") or {}),
        "parameter_prefix": normalized["parameter_prefix"],
        "variable_count": len(normalized["profile_variables"]),
        "constraint_count": len(normalized["profile_constraints"]),
        "dimension_count": len(normalized["profile_dimensions"]),
        "profile_points": normalized["profile_points"],
        "profile_lines": normalized["profile_lines"],
        "profile_arcs": normalized["profile_arcs"],
        "construction_lines": normalized["profile_construction_lines"],
        "named_points": dict(normalized.get("profile_named_points") or {}),
        "verification": dict(normalized.get("profile_verification") or {}),
        "live_status": "planned",
    }
    profile_summary = {
        "fundamental_triangle_height": normalized["fundamental_triangle_height"],
        "thread_geometry": dict(normalized.get("thread_geometry") or {}),
        "metric_thread_geometry": dict(normalized.get("metric_thread_geometry") or {}),
        "thread_profile_family": normalized["thread_profile_family"],
        "thread_series": normalized["thread_series"],
        "thread_source_units": normalized["thread_source_units"],
        "thread_profile_resolved_from": normalized["thread_profile_resolved_from"],
        "profile_root_shape": normalized["profile_root_shape"],
        "carrier_shape": normalized.get("carrier_shape", "cylindrical"),
        "carrier_taper": dict(normalized.get("carrier_taper") or {}),
        "profile_verification": dict(normalized.get("profile_verification") or {}),
        "thread_reference_diameter": normalized["thread_reference_diameter"],
        "thread_reference_radius": normalized["thread_reference_radius"],
        "end_thread_reference_diameter": normalized.get("end_thread_reference_diameter"),
        "recommended_source_diameter": normalized["recommended_source_diameter"],
        "source_diameter_validation": dict(normalized.get("source_diameter_validation") or {}),
        "profile_entry_offset": normalized["profile_entry_offset"],
        "profile_taper_compensation_radius": normalized.get("profile_taper_compensation_radius", 0.0),
        "spiral_length": normalized["spiral_length"],
        "profile_surface_offset": normalized["profile_surface_offset"],
        "profile_surface_offset_effective": normalized["profile_surface_offset_effective"],
        "profile_surface_offset_applied": normalized["profile_surface_offset_applied"],
        "profile_surface_offset_status": normalized["profile_surface_offset_status"],
        "profile_surface_offset_note": normalized["profile_surface_offset_note"],
        "profile_sketch_origin_shift": normalized["profile_sketch_origin_shift"],
        "direction": normalized["direction"],
        "profile_angle_degrees": normalized["profile_angle_degrees"],
        "internal": normalized["internal"],
        "creation_status": "available",
        "parameter_prefix": normalized["parameter_prefix"],
        "operation_label": normalized["operation_label"],
        "planned_variable_count": len(normalized["profile_variables"]),
        "planned_constraint_count": len(normalized["profile_constraints"]),
        "planned_dimension_count": len(normalized["profile_dimensions"]),
    }
    if crest_round_pass:
        profile_summary.update(
            {
                "crest_rounding_enabled": True,
                "crest_round_phase_shift": crest_round_pass["phase_shift"],
                "crest_round_phase_shift_expression": crest_round_pass["phase_shift_expression"],
                "crest_round_radius": crest_round_pass["crest_round_radius"],
                "crest_round_profile_origin_offset": crest_round_pass["profile_origin_offset"],
                "crest_round_profile_radial_epsilon": crest_round_pass["radial_epsilon"],
                "secondary_cut_count": 1,
            }
        )
    else:
        profile_summary.update(
            {
                "crest_rounding_enabled": False,
                "secondary_cut_count": 0,
            }
        )
    if normalized["internal"]:
        profile_operation.update(
            {
                "crest_drop": normalized["profile_crest_drop"],
                "root_width": normalized["root_width"],
                "root_radius": normalized["root_radius"],
                "root_width": normalized.get("root_width"),
                "profile_outer_half_width": normalized["profile_outer_half_width"],
            }
        )
        profile_summary.update(
            {
                "crest_drop": normalized["profile_crest_drop"],
                "root_width": normalized["root_width"],
                "root_radius": normalized["root_radius"],
                "root_width": normalized.get("root_width"),
                "profile_outer_half_width": normalized["profile_outer_half_width"],
            }
        )
    else:
        profile_operation.update(
            {
                "major_radius": normalized["major_radius"],
                "root_radius_level": normalized["root_radius_level"],
                "root_diameter": normalized["root_diameter"],
                "profile_base_drop": normalized["profile_base_drop"],
                "profile_apex_height": normalized["profile_apex_height"],
                "root_radius": normalized["root_radius"],
                "root_width": normalized.get("root_width"),
                "profile_outer_half_width": normalized["profile_outer_half_width"],
            }
        )
        profile_summary.update(
            {
                "major_radius": normalized["major_radius"],
                "root_radius_level": normalized["root_radius_level"],
                "root_diameter": normalized["root_diameter"],
                "profile_base_drop": normalized["profile_base_drop"],
                "profile_apex_height": normalized["profile_apex_height"],
                "root_radius": normalized["root_radius"],
                "root_width": normalized.get("root_width"),
                "profile_outer_half_width": normalized["profile_outer_half_width"],
            }
        )

    operations = [
        {
            "operation": "create_part_document",
            "description": "Create a new 3D part document",
        },
        {
            "operation": "add_variables",
            "enabled": True,
            "variable_count": len(normalized["profile_variables"]),
            "variables": normalized["profile_variables"],
            "live_status": "planned",
        },
        {
            "operation": "create_source_body",
            "source_scenario": normalized["source_scenario"],
            "summary": (normalized["source_preview"] or {}).get("summary") or {},
            "source_diameter_validation": dict(normalized.get("source_diameter_validation") or {}),
            "description": "Create the source body used for the helical thread cut",
            "live_status": "planned",
        },
        {
            "operation": "create_spiral_path",
            "source_selector": normalized["source_selector"],
            "start_selector": normalized["start_selector"],
            "carrier_diameter": normalized.get("carrier_diameter"),
            "carrier_shape": normalized.get("carrier_shape", "cylindrical"),
            "carrier_taper": dict(normalized.get("carrier_taper") or {}),
            "diameter": normalized["diameter"],
            "end_diameter": normalized.get("end_diameter"),
            "pitch": normalized["pitch"],
            "length": normalized["length"],
            "spiral_length": normalized["spiral_length"],
            "direction": normalized["direction"],
            "live_status": "planned",
        },
        {
            "operation": "bind_operation_variables",
            "target": "spiral_path",
            "bindings": list(normalized.get("operation_variable_bindings") or []),
            "description": "Bind helical path operation parameters to public thread variables",
            "live_status": "planned",
        },
        profile_operation,
        {
            "operation": "cut_evolution",
            "source_selector": normalized["source_selector"],
            "start_selector": normalized["start_selector"],
            "end_selector": normalized["end_selector"],
            "carrier_diameter": normalized.get("carrier_diameter"),
            "carrier_shape": normalized.get("carrier_shape", "cylindrical"),
            "carrier_taper": dict(normalized.get("carrier_taper") or {}),
            "recommended_source_diameter": normalized["recommended_source_diameter"],
            "source_diameter_validation": dict(normalized.get("source_diameter_validation") or {}),
            "diameter": normalized["diameter"],
            "pitch": normalized["pitch"],
            "length": normalized["length"],
            "spiral_length": normalized["spiral_length"],
            "depth": normalized["thread_depth"],
            "direction": normalized["direction"],
            "internal": normalized["internal"],
            "live_status": "planned",
        },
    ]
    if crest_round_pass:
        operations.extend(
            [
                {
                    "operation": "create_crest_round_spiral_path",
                    "role": crest_round_pass["role"],
                    "phase_shift": crest_round_pass["phase_shift"],
                    "phase_shift_expression": crest_round_pass["phase_shift_expression"],
                    "phase_shift_direction": crest_round_pass["phase_shift_direction"],
                    "carrier_diameter": normalized.get("carrier_diameter"),
                    "carrier_shape": normalized.get("carrier_shape", "cylindrical"),
                    "pitch": normalized["pitch"],
                    "length": normalized["length"],
                    "spiral_length": normalized["spiral_length"],
                    "direction": normalized["direction"],
                    "live_status": "planned",
                },
                {
                    "operation": "bind_operation_variables",
                    "target": "crest_round_spiral_path",
                    "role": crest_round_pass["role"],
                    "bindings": list(crest_round_pass.get("operation_variable_bindings") or []),
                    "description": "Bind crest-round spiral parameters to public thread variables",
                    "live_status": "planned",
                },
                {
                    "operation": "create_crest_round_profile",
                    "role": crest_round_pass["role"],
                    "phase_shift": crest_round_pass["phase_shift"],
                    "crest_round_radius": crest_round_pass["crest_round_radius"],
                    "profile_origin_offset": crest_round_pass["profile_origin_offset"],
                    "radial_epsilon": crest_round_pass["radial_epsilon"],
                    "crest_apex_height": crest_round_pass["crest_apex_height"],
                    "crest_tangent_depth": crest_round_pass["crest_tangent_depth"],
                    "crest_tangent_half_width": crest_round_pass["crest_tangent_half_width"],
                    "parameter_prefix": normalized["parameter_prefix"],
                    "variable_count": 0,
                    "constraint_count": len(crest_round_pass["constraints"]),
                    "dimension_count": len(crest_round_pass["dimensions"]),
                    "profile_points": crest_round_pass["profile_points"],
                    "profile_lines": crest_round_pass["profile_lines"],
                    "profile_arcs": crest_round_pass["profile_arcs"],
                    "construction_lines": crest_round_pass["construction_lines"],
                    "named_points": dict(crest_round_pass.get("named_points") or {}),
                    "verification": dict(crest_round_pass.get("verification") or {}),
                    "dimension_expressions": dict(crest_round_pass.get("dimension_expressions") or {}),
                    "live_status": "planned",
                },
                {
                    "operation": "cut_crest_round_evolution",
                    "role": crest_round_pass["role"],
                    "phase_shift": crest_round_pass["phase_shift"],
                    "crest_round_radius": crest_round_pass["crest_round_radius"],
                    "pitch": normalized["pitch"],
                    "length": normalized["length"],
                    "spiral_length": normalized["spiral_length"],
                    "internal": normalized["internal"],
                    "live_status": "planned",
                },
            ]
        )
    if normalized["auxiliary_geometry_hidden"]:
        objects = [
            "start_center_point",
            "profile_origin_point",
            "profile_lcs",
            "profile_sketch",
            "spiral_axis",
            "spiral_path",
        ]
        if crest_round_pass:
            objects.extend(
                [
                    "crest_round_start_center_point",
                    "crest_round_profile_origin_point",
                    "crest_round_profile_lcs",
                    "crest_round_profile_sketch",
                    "crest_round_spiral_path",
                ]
            )
        operations.append(
            {
                "operation": "hide_auxiliary_geometry",
                "objects": objects,
                "description": "Hide service geometry created for the helical thread path and profile",
                "live_status": "planned",
            }
        )
    return {
        "scenario": scenario,
        "ok": True,
        "params": normalized,
        "summary": {
            "source_scenario": normalized["source_scenario"],
            "source_selector": normalized["source_selector"],
            "start_selector": normalized["start_selector"],
            "end_selector": normalized["end_selector"],
            "carrier_diameter": normalized.get("carrier_diameter"),
            "carrier_shape": normalized.get("carrier_shape", "cylindrical"),
            "carrier_taper": dict(normalized.get("carrier_taper") or {}),
            "diameter": normalized["diameter"],
            "end_diameter": normalized.get("end_diameter"),
            "pitch": normalized["pitch"],
            "length": normalized["length"],
            "depth": normalized["thread_depth"],
            "clearance": normalized["clearance"],
            "auxiliary_geometry_hidden": normalized["auxiliary_geometry_hidden"],
            **profile_summary,
        },
        "interface": _build_helical_thread_interface(normalized, scenario=scenario),
        "operations": operations,
    }


def _resolve_helical_thread_parameter_prefix(value: Any, name: str, scenario: str) -> str:
    explicit = normalize_parameter_prefix(value)
    if explicit:
        return explicit
    for candidate in (name, scenario):
        try:
            resolved = normalize_parameter_prefix(candidate)
        except ValueError:
            resolved = None
        if resolved:
            return resolved
    return "INTERNAL_HELICAL_THREAD" if scenario == "internal_helical_thread" else "EXTERNAL_HELICAL_THREAD"


def _format_thread_designation_token(designation: str, diameter: float, pitch: float) -> str:
    text = re.sub(r"\s+", "", str(designation or "").strip())
    if text:
        return text.replace("X", "x")
    diameter_token = f"{float(diameter):.6f}".rstrip("0").rstrip(".")
    pitch_token = f"{float(pitch):.6f}".rstrip("0").rstrip(".")
    return f"M{diameter_token}x{pitch_token}"


def _sanitize_thread_display_token(value: str) -> str:
    text = re.sub(r"[^\w]+", "_", str(value or "").strip(), flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "thread"


def _resolve_thread_display_index(params: dict[str, Any]) -> int:
    for key in ("thread_instance_index", "instance_index", "feature_index", "index"):
        raw_value = params.get(key)
        if raw_value in (None, ""):
            continue
        try:
            value = int(raw_value)
        except Exception:
            continue
        if value > 0:
            return value
    return 1


def _build_thread_module_display_name(
    *,
    designation: str,
    diameter: float,
    pitch: float,
    internal: bool,
    direction: str,
) -> str:
    side = "internal" if internal else "external"
    handed = "left" if direction == "left" else "right"
    designation_token = _format_thread_designation_token(designation, diameter, pitch)
    return f"Thread {side} {handed} {designation_token}"


def _build_thread_module_variable_token(
    *,
    designation: str,
    diameter: float,
    pitch: float,
    internal: bool,
    direction: str,
) -> str:
    side = "internal" if internal else "external"
    handed = "left" if direction == "left" else "right"
    designation_token = _sanitize_thread_display_token(_format_thread_designation_token(designation, diameter, pitch))
    return f"thread_{side}_{handed}_{designation_token}"


def _build_thread_public_variable_name(variable_name: str, module_display_name: str, display_index: int) -> str:
    return _sanitize_thread_display_token(f"{variable_name} {module_display_name} {display_index}")


def _build_thread_object_display_name(object_name: str, module_display_name: str, display_index: int) -> str:
    object_label = str(object_name or "").strip()
    module_label = str(module_display_name or "").strip()
    if module_label.lower().startswith(object_label.lower() + " "):
        return f"{module_label} {display_index}"
    return f"{object_label} {module_label} {display_index}"


def _build_thread_variable_note(variable_name: str, module_display_name: str, display_index: int, role: str) -> str:
    return f"{variable_name} | {module_display_name} | {display_index} | {role}"


def _format_thread_expression_number(value: float) -> str:
    text = f"{float(value):.12f}".rstrip("0").rstrip(".")
    if text in ("", "-0"):
        return "0"
    return text


def _build_thread_linear_expression(variable_name: str, coefficient: float = 0.0, constant: float = 0.0) -> str:
    coeff = float(coefficient)
    offset = float(constant)
    parts: list[str] = []
    if abs(coeff) > 1e-12:
        if abs(coeff - 1.0) <= 1e-12:
            parts.append(variable_name)
        elif abs(coeff + 1.0) <= 1e-12:
            parts.append(f"-{variable_name}")
        else:
            parts.append(f"{_format_thread_expression_number(coeff)} * {variable_name}")
    if abs(offset) > 1e-12 or not parts:
        offset_text = _format_thread_expression_number(offset)
        if parts:
            if offset > 0.0:
                parts.append(f"+ {offset_text}")
            else:
                parts.append(f"- {_format_thread_expression_number(abs(offset))}")
        else:
            parts.append(offset_text)
    return " ".join(parts)


def _build_helical_thread_dimension_expression_plan(normalized: dict[str, Any]) -> dict[str, str]:
    pitch_name = str(normalized["public_pitch_variable_name"])
    diameter_name = str(normalized["public_diameter_variable_name"])
    pitch = float(normalized["pitch"])
    thread_geometry = normalized.get("thread_geometry") or normalized.get("metric_thread_geometry") or {}
    half_angle_radians = math.radians(float(normalized["profile_angle_degrees"]) / 2.0)
    cos_half_angle = math.cos(half_angle_radians)
    tan_half_angle = math.tan(half_angle_radians)

    expressions: dict[str, str] = {
        "sketch_reference_radius": f"{diameter_name} / 2",
        "sketch_pitch_half": _build_thread_linear_expression(pitch_name, 0.5),
    }
    if str(normalized.get("carrier_shape") or "cylindrical") == "conical":
        compensation = float(normalized.get("profile_taper_compensation_radius") or 0.0)
        if abs(compensation) > 1e-12:
            operator = "+" if compensation > 0.0 else "-"
            if str(normalized.get("profile_entry_offset_mode") or "").strip().lower() == "auto":
                radius_ratio = abs(float(normalized.get("profile_taper_slope") or 0.0))
                expressions["sketch_reference_radius"] = (
                    f"{diameter_name} / 2 {operator} "
                    f"{_build_thread_linear_expression(pitch_name, 1.05 * radius_ratio)}"
                )
            else:
                expressions["sketch_reference_radius"] = (
                    f"{diameter_name} / 2 {operator} {_format_thread_expression_number(abs(compensation))}"
                )
        if str(normalized.get("profile_root_shape") or "round") == "flat":
            taper_radius_ratio = abs(float(normalized.get("profile_taper_slope") or 0.0))
            expressions["sketch_outer_taper_offset"] = _build_thread_linear_expression(
                pitch_name,
                taper_radius_ratio * float(normalized["profile_outer_half_width"]) / pitch,
            )
            expressions["sketch_root_taper_offset"] = _build_thread_linear_expression(
                pitch_name,
                taper_radius_ratio * float(normalized["profile_root_half_width"]) / pitch,
            )
    if not normalized["internal"]:
        if str(normalized.get("profile_root_shape") or "round") == "flat":
            expressions.update(
                {
                    "sketch_base_drop": _build_thread_linear_expression(
                        pitch_name,
                        float(normalized["profile_base_drop"]) / pitch,
                    ),
                    "sketch_apex_height": _build_thread_linear_expression(
                        pitch_name,
                        float(normalized["profile_apex_height"]) / pitch,
                    ),
                    "sketch_outer_half": _build_thread_linear_expression(
                        pitch_name,
                        float(normalized["profile_outer_half_width"]) / pitch,
                    ),
                    "sketch_root_half": _build_thread_linear_expression(
                        pitch_name,
                        float(normalized["profile_root_half_width"]) / pitch,
                    ),
                }
            )
            if str(normalized.get("root_radius_level_mode") or "auto") == "explicit":
                expressions["sketch_depth"] = (
                    f"{diameter_name} / 2 - "
                    f"{_format_thread_expression_number(float(normalized['root_radius_level']))}"
                )
            elif str(normalized.get("thread_depth_mode") or "auto") == "auto":
                expressions["sketch_depth"] = _build_thread_linear_expression(
                    pitch_name,
                    float(thread_geometry["external_thread_depth"]) / pitch,
                    float(normalized["clearance"]),
                )
            else:
                expressions["sketch_depth"] = _format_thread_expression_number(float(normalized["radial_cut_depth"]))
            return expressions
        expressions.update(
            {
                "sketch_base_drop": _build_thread_linear_expression(
                    pitch_name,
                    float(normalized["profile_base_drop"]) / pitch,
                ),
                "sketch_apex_height": _build_thread_linear_expression(
                    pitch_name,
                    float(normalized["profile_apex_height"]) / pitch,
                ),
                "sketch_outer_half": _build_thread_linear_expression(
                    pitch_name,
                    float(normalized["profile_outer_half_width"]) / pitch,
                ),
                "sketch_radius": _format_thread_expression_number(float(normalized["root_radius"])),
            }
        )
        if str(normalized.get("root_radius_level_mode") or "auto") == "explicit":
            expressions["sketch_depth"] = (
                f"{diameter_name} / 2 - "
                f"{_format_thread_expression_number(float(normalized['root_radius_level']))}"
            )
        elif str(normalized.get("thread_depth_mode") or "auto") == "auto":
            expressions["sketch_depth"] = _build_thread_linear_expression(
                pitch_name,
                float(thread_geometry["external_thread_depth"]) / pitch,
                float(normalized["clearance"]),
            )
        else:
            expressions["sketch_depth"] = _format_thread_expression_number(float(normalized["radial_cut_depth"]))
        return expressions

    cut_depth_expr = (
        _build_thread_linear_expression(
            pitch_name,
            float(thread_geometry["internal_thread_depth"]) / pitch,
            float(normalized["clearance"]),
        )
        if str(normalized.get("thread_depth_mode") or "auto") == "auto"
        else _format_thread_expression_number(float(normalized["radial_cut_depth"]))
    )
    crest_drop_coeff = (
        float(normalized["fundamental_triangle_height"]) - float(thread_geometry["internal_thread_depth"])
    ) / pitch
    root_half_expr = (
        _build_thread_linear_expression(pitch_name, 1.0 / 16.0)
        if str(normalized.get("root_width_mode") or "auto") == "auto"
        else _format_thread_expression_number(float(normalized["root_width"]) / 2.0)
    )
    root_radius_expr = (
        _format_thread_expression_number(0.0)
        if str(normalized.get("profile_root_shape") or "round") == "flat"
        else (
        _build_thread_linear_expression(pitch_name, 1.0 / (16.0 * cos_half_angle))
        if str(normalized.get("root_width_mode") or "auto") == "auto"
        else _format_thread_expression_number(float(normalized["root_radius"]))
        )
    )
    outer_half_expr = (
        _build_thread_linear_expression(
            pitch_name,
            float(normalized["profile_outer_half_width"]) / pitch,
        )
        if str(normalized.get("profile_root_shape") or "round") == "flat"
        else (
            _build_thread_linear_expression(
                pitch_name,
                (
                    float(thread_geometry["internal_thread_depth"]) / pitch * tan_half_angle
                    if str(normalized.get("thread_depth_mode") or "auto") == "auto"
                    else 0.0
                ),
                float(normalized["clearance"]) * tan_half_angle
                if str(normalized.get("thread_depth_mode") or "auto") == "auto"
                else float(normalized["profile_outer_half_width"]),
            )
            if str(normalized.get("thread_depth_mode") or "auto") == "auto"
            else _format_thread_expression_number(float(normalized["profile_outer_half_width"]))
        )
    )
    expressions.update(
        {
            "sketch_crest_drop": _build_thread_linear_expression(
                pitch_name,
                crest_drop_coeff,
                -float(normalized["clearance"]),
            ),
            "sketch_depth": cut_depth_expr,
            "sketch_outer_half": outer_half_expr,
            "sketch_root_half": root_half_expr,
            "sketch_radius": root_radius_expr,
        }
    )
    return expressions


def _build_helical_thread_variable_plan(normalized: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    prefix = normalized["parameter_prefix"]
    module_display_name = normalized["module_display_name"]
    display_index = int(normalized["display_index"])
    public_diameter_name = normalized["public_diameter_variable_name"]
    public_pitch_name = normalized["public_pitch_variable_name"]
    public_length_name = normalized["public_length_variable_name"]
    variables = [
        {
            "name": public_diameter_name,
            "value": normalized["thread_reference_diameter"],
            "note": _build_thread_variable_note(public_diameter_name, module_display_name, display_index, "Public thread diameter"),
            "external": True,
        },
        {
            "name": public_pitch_name,
            "value": normalized["pitch"],
            "note": _build_thread_variable_note(public_pitch_name, module_display_name, display_index, "Public thread pitch"),
            "external": True,
        },
        {
            "name": public_length_name,
            "value": normalized["length"],
            "note": _build_thread_variable_note(public_length_name, module_display_name, display_index, "Public thread length"),
            "external": True,
        },
    ]
    if not normalized["internal"]:
        sketch_reference_radius_name = build_parameter_name("SKO", 1, prefix=prefix)
        sketch_pitch_half_name = build_parameter_name("SKP", 1, prefix=prefix)
        sketch_base_drop_name = build_parameter_name("SKB", 1, prefix=prefix)
        sketch_apex_height_name = build_parameter_name("SKA", 1, prefix=prefix)
        sketch_depth_name = build_parameter_name("SKD", 1, prefix=prefix)
        sketch_outer_half_name = build_parameter_name("SKW", 1, prefix=prefix)
        if str(normalized.get("profile_root_shape") or "round") == "flat":
            sketch_root_half_name = build_parameter_name("SKT", 1, prefix=prefix)
            names = {
                "pitch": public_pitch_name,
                "diameter": public_diameter_name,
                "length": public_length_name,
                "sketch_reference_radius": sketch_reference_radius_name,
                "sketch_pitch_half": sketch_pitch_half_name,
                "sketch_base_drop": sketch_base_drop_name,
                "sketch_apex_height": sketch_apex_height_name,
                "sketch_depth": sketch_depth_name,
                "sketch_outer_half": sketch_outer_half_name,
                "sketch_root_half": sketch_root_half_name,
            }
            if str(normalized.get("carrier_shape") or "cylindrical") == "conical":
                names["sketch_outer_taper_offset"] = build_parameter_name("SKC", 1, prefix=prefix)
                names["sketch_root_taper_offset"] = build_parameter_name("SKC", 2, prefix=prefix)
            return variables, names
        sketch_radius_name = build_parameter_name("SKR", 1, prefix=prefix)
        return variables, {
            "pitch": public_pitch_name,
            "diameter": public_diameter_name,
            "length": public_length_name,
            "sketch_reference_radius": sketch_reference_radius_name,
            "sketch_pitch_half": sketch_pitch_half_name,
            "sketch_base_drop": sketch_base_drop_name,
            "sketch_apex_height": sketch_apex_height_name,
            "sketch_depth": sketch_depth_name,
            "sketch_outer_half": sketch_outer_half_name,
            "sketch_radius": sketch_radius_name,
        }

    sketch_reference_radius_name = build_parameter_name("SKO", 1, prefix=prefix)
    sketch_pitch_half_name = build_parameter_name("SKP", 1, prefix=prefix)
    sketch_crest_drop_name = build_parameter_name("SKB", 1, prefix=prefix)
    sketch_depth_name = build_parameter_name("SKD", 1, prefix=prefix)
    sketch_outer_half_name = build_parameter_name("SKW", 1, prefix=prefix)
    sketch_root_half_name = build_parameter_name("SKT", 1, prefix=prefix)
    sketch_radius_name = build_parameter_name("SKR", 1, prefix=prefix)
    names = {
        "pitch": public_pitch_name,
        "diameter": public_diameter_name,
        "length": public_length_name,
        "sketch_reference_radius": sketch_reference_radius_name,
        "sketch_pitch_half": sketch_pitch_half_name,
        "sketch_crest_drop": sketch_crest_drop_name,
        "sketch_depth": sketch_depth_name,
        "sketch_outer_half": sketch_outer_half_name,
        "sketch_root_half": sketch_root_half_name,
        "sketch_radius": sketch_radius_name,
    }
    if str(normalized.get("carrier_shape") or "cylindrical") == "conical" and str(normalized.get("profile_root_shape") or "round") == "flat":
        names["sketch_outer_taper_offset"] = build_parameter_name("SKC", 1, prefix=prefix)
        names["sketch_root_taper_offset"] = build_parameter_name("SKC", 2, prefix=prefix)
    return variables, names


def _build_helical_thread_spiral_variable_bindings(
    normalized: dict[str, Any],
    *,
    target: str = "spiral_path",
) -> list[dict[str, Any]]:
    variable_names = normalized.get("profile_variable_names") or {}
    pitch_variable = str(variable_names.get("pitch") or "").strip()
    length_variable = str(variable_names.get("length") or "").strip()
    if not pitch_variable or not length_variable:
        return []
    if str(normalized.get("profile_entry_offset_mode") or "").strip().lower() == "auto":
        height_expression = f"{length_variable} + 1.05 * {pitch_variable}"
    else:
        height_expression = f"{length_variable} + {_format_thread_expression_number(float(normalized['profile_entry_offset']))}"
    return [
        {
            "target": target,
            "parameter_note": "Шаг",
            "parameter_note_aliases": ["Шаг", "Step", "Pitch"],
            "expression": pitch_variable,
            "role": "spiral_pitch",
        },
        {
            "target": target,
            "parameter_note": "Высота",
            "parameter_note_aliases": ["Высота", "Height", "Length"],
            "expression": height_expression,
            "role": "spiral_height",
        },
    ]


def _build_crest_round_expression(
    pitch_variable: str,
    pitch: float,
    value: float,
    *,
    mode: str,
) -> str:
    if str(mode or "explicit").strip().lower() == "auto":
        return _build_thread_linear_expression(
            pitch_variable,
            float(value) / float(pitch),
        )
    return _format_thread_expression_number(float(value))


def _build_external_crest_round_constraint_plan() -> list[dict[str, Any]]:
    return [
        {"kind": "fixed_point", "target": "origin", "index": 0},
        {"kind": "fixed_point", "target": "axis", "index": 1},
        {"kind": "vertical", "target": "axis"},
        {"kind": "vertical", "target": "radius_ref"},
        {"kind": "vertical", "target": "apex_ref"},
        {"kind": "vertical", "target": "tangent_depth_ref"},
        {"kind": "vertical", "target": "center_ref"},
        {"kind": "horizontal", "target": "left_tangent_ref"},
        {"kind": "horizontal", "target": "right_tangent_ref"},
        {"kind": "merge_points", "target": "radius_ref", "index": 0, "partner": "axis", "partner_index": 0},
        {"kind": "merge_points", "target": "radius_ref", "index": 1, "partner": "apex_ref", "partner_index": 0},
        {"kind": "merge_points", "target": "radius_ref", "index": 1, "partner": "tangent_depth_ref", "partner_index": 0},
        {"kind": "merge_points", "target": "radius_ref", "index": 1, "partner": "center_ref", "partner_index": 0},
        {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "profile_line_1", "partner_index": 0},
        {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "profile_line_2", "partner_index": 1},
        {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "left_theory", "partner_index": 0},
        {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "right_theory", "partner_index": 0},
        {"kind": "merge_points", "target": "tangent_depth_ref", "index": 1, "partner": "left_tangent_ref", "partner_index": 0},
        {"kind": "merge_points", "target": "tangent_depth_ref", "index": 1, "partner": "right_tangent_ref", "partner_index": 0},
        {"kind": "merge_points", "target": "left_tangent_ref", "index": 1, "partner": "profile_line_1", "partner_index": 1},
        {"kind": "merge_points", "target": "left_tangent_ref", "index": 1, "partner": "left_theory", "partner_index": 1},
        {"kind": "merge_points", "target": "left_tangent_ref", "index": 1, "partner": "crest_arc", "partner_index": 2},
        {"kind": "merge_points", "target": "right_tangent_ref", "index": 1, "partner": "profile_line_2", "partner_index": 0},
        {"kind": "merge_points", "target": "right_tangent_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
        {"kind": "merge_points", "target": "right_tangent_ref", "index": 1, "partner": "crest_arc", "partner_index": 1},
        {"kind": "merge_points", "target": "center_ref", "index": 1, "partner": "crest_arc", "partner_index": 0},
        {"kind": "equal_length", "target": "left_tangent_ref", "partner": "right_tangent_ref"},
        {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
        {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
        {"kind": "tangent", "target": "crest_arc", "partner": "profile_line_1"},
        {"kind": "tangent", "target": "crest_arc", "partner": "profile_line_2"},
    ]


def _build_external_crest_round_dimension_plan(
    variable_names: dict[str, str],
    expressions: dict[str, str],
) -> list[dict[str, Any]]:
    return [
        {
            "kind": "line_length",
            "target": "radius_ref",
            "name": variable_names["sketch_reference_radius"],
            "variable": variable_names["sketch_reference_radius"],
            "expression": expressions["sketch_reference_radius"],
            "placement_index": 0,
        },
        {
            "kind": "line_length",
            "target": "apex_ref",
            "name": variable_names["sketch_apex_height"],
            "variable": variable_names["sketch_apex_height"],
            "expression": expressions["sketch_apex_height"],
            "placement_index": 1,
        },
        {
            "kind": "line_length",
            "target": "tangent_depth_ref",
            "name": variable_names["sketch_tangent_depth"],
            "variable": variable_names["sketch_tangent_depth"],
            "expression": expressions["sketch_tangent_depth"],
            "placement_index": 2,
        },
        {
            "kind": "line_length",
            "target": "right_tangent_ref",
            "name": variable_names["sketch_tangent_half"],
            "variable": variable_names["sketch_tangent_half"],
            "expression": expressions["sketch_tangent_half"],
            "placement_index": 3,
        },
        {
            "kind": "line_length",
            "target": "center_ref",
            "name": variable_names["sketch_radius"],
            "variable": variable_names["sketch_radius"],
            "expression": expressions["sketch_radius"],
            "placement_index": 4,
        },
    ]


def _build_external_crest_round_pass(
    normalized: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    scenario = "internal_helical_thread" if bool(normalized.get("internal")) else "external_helical_thread"
    internal = bool(normalized.get("internal"))
    crest_round_radius = _optional_positive_float(
        params,
        "crest_round_radius",
        "crest_round_radius",
        "crest_radius",
        "top_round_radius",
        "crest_rounding_radius",
    )
    thread_geometry = normalized.get("thread_geometry") or {}
    if crest_round_radius is None:
        geometry_radius = thread_geometry.get("crest_round_radius")
        if geometry_radius not in (None, ""):
            crest_round_radius = float(geometry_radius)
    enabled_raw = params.get("crest_rounding_enabled")
    enabled = bool(crest_round_radius and float(crest_round_radius) > 0.0) if enabled_raw is None else bool(enabled_raw)
    if not enabled:
        return None
    if crest_round_radius is None or float(crest_round_radius) <= 0.0:
        raise ValueError(f"{scenario} crest_rounding_enabled requires crest_round_radius")
    if str(normalized.get("carrier_shape") or "cylindrical").strip().lower() != "cylindrical":
        raise ValueError(f"{scenario} crest rounding pass currently supports only cylindrical carriers")

    pitch = float(normalized["pitch"])
    half_angle_radians = math.radians(float(normalized["profile_angle_degrees"]) / 2.0)
    sin_half_angle = math.sin(half_angle_radians)
    cos_half_angle = math.cos(half_angle_radians)
    if sin_half_angle <= 1e-9 or cos_half_angle <= 1e-9:
        raise ValueError(f"{scenario} crest rounding pass requires a valid profile_angle_degrees")

    crest_round_radius_mode = "explicit"
    geometry_radius = thread_geometry.get("crest_round_radius")
    if geometry_radius not in (None, "") and abs(float(crest_round_radius) - float(geometry_radius)) <= 1e-9:
        crest_round_radius_mode = "auto"

    phase_shift = _optional_positive_float(
        params,
        "crest_round_phase_shift",
        "crest_round_phase_shift",
        "crest_phase_shift",
        "secondary_phase_shift",
    )
    phase_shift_mode = "explicit"
    if phase_shift is None:
        phase_shift = pitch / 2.0
        phase_shift_mode = "auto"

    radial_epsilon_raw = _coalesce_defined(
        params,
        "crest_round_profile_radial_epsilon",
        "crest_round_profile_radial_epsilon",
        "crest_profile_radial_epsilon",
        "crest_radial_epsilon",
        "profile_radial_epsilon",
        "degenerate_edge_epsilon",
    )
    radial_epsilon_mode = "explicit"
    if radial_epsilon_raw in (None, ""):
        radial_epsilon = 0.0001
        radial_epsilon_mode = "auto"
    else:
        radial_epsilon = float(radial_epsilon_raw)
        if not math.isfinite(radial_epsilon) or radial_epsilon < 0.0:
            raise ValueError(f"{scenario} crest_round_profile_radial_epsilon must be a finite non-negative number")

    crest_round_radius = float(crest_round_radius)
    phase_shift = float(phase_shift)
    radial_epsilon = float(radial_epsilon)
    tangent_half_width = crest_round_radius * cos_half_angle
    tangent_depth = crest_round_radius * (1.0 - sin_half_angle)
    apex_height = crest_round_radius * ((1.0 / sin_half_angle) - 1.0)
    if tangent_half_width <= 0.0 or tangent_depth <= 0.0 or apex_height <= 0.0:
        raise ValueError(f"{scenario} crest rounding geometry is invalid")
    if tangent_half_width >= float(normalized["profile_outer_half_width"]) - 1e-6:
        raise ValueError(f"{scenario} crest_round_radius is too large for the available crest width")
    if phase_shift <= 0.0 or phase_shift >= pitch - 1e-6:
        raise ValueError(f"{scenario} crest_round_phase_shift must stay within one pitch")

    if internal:
        crest_y = -float(normalized["thread_reference_radius"]) - radial_epsilon
        tangent_y = crest_y + tangent_depth
        apex_y = crest_y - apex_height
        arc_center_y = crest_y + crest_round_radius
        arc_direction = True
    else:
        crest_y = float(normalized["thread_reference_radius"]) + radial_epsilon
        tangent_y = crest_y - tangent_depth
        apex_y = crest_y + apex_height
        arc_center_y = crest_y - crest_round_radius
        arc_direction = False
    axis_margin = max(abs(apex_y), abs(tangent_y), abs(arc_center_y), abs(crest_y), tangent_half_width, crest_round_radius, 1.0) * 0.3
    profile_origin_offset = float(normalized["profile_entry_offset"]) + phase_shift

    profile_points = [
        [0.0, apex_y],
        [-tangent_half_width, tangent_y],
        [tangent_half_width, tangent_y],
        [0.0, apex_y],
    ]
    profile_lines = [
        {"target": "profile_line_1", "start": [0.0, apex_y], "end": [-tangent_half_width, tangent_y]},
        {"target": "profile_line_2", "start": [tangent_half_width, tangent_y], "end": [0.0, apex_y]},
    ]
    profile_arcs = [
        {
            "target": "crest_arc",
            "xc": 0.0,
            "yc": arc_center_y,
            "radius": crest_round_radius,
            "x1": tangent_half_width,
            "y1": tangent_y,
            "x2": -tangent_half_width,
            "y2": tangent_y,
            "direction": arc_direction,
        }
    ]
    construction_lines = [
        {"target": "radius_ref", "start": [0.0, 0.0], "end": [0.0, crest_y], "line_style": 6},
        {"target": "apex_ref", "start": [0.0, crest_y], "end": [0.0, apex_y], "line_style": 6},
        {"target": "tangent_depth_ref", "start": [0.0, crest_y], "end": [0.0, tangent_y], "line_style": 6},
        {"target": "center_ref", "start": [0.0, crest_y], "end": [0.0, arc_center_y], "line_style": 6},
        {"target": "left_tangent_ref", "start": [0.0, tangent_y], "end": [-tangent_half_width, tangent_y], "line_style": 6},
        {"target": "right_tangent_ref", "start": [0.0, tangent_y], "end": [tangent_half_width, tangent_y], "line_style": 6},
        {"target": "left_theory", "start": [0.0, apex_y], "end": [-tangent_half_width, tangent_y], "line_style": 6},
        {"target": "right_theory", "start": [0.0, apex_y], "end": [tangent_half_width, tangent_y], "line_style": 6},
    ]

    prefix = str(normalized["parameter_prefix"])
    variable_names = {
        "pitch": str(normalized["public_pitch_variable_name"]),
        "diameter": str(normalized["public_diameter_variable_name"]),
        "length": str(normalized["public_length_variable_name"]),
        "sketch_reference_radius": build_parameter_name("CKO", 1, prefix=prefix),
        "sketch_apex_height": build_parameter_name("CKA", 1, prefix=prefix),
        "sketch_tangent_depth": build_parameter_name("CKD", 1, prefix=prefix),
        "sketch_tangent_half": build_parameter_name("CKW", 1, prefix=prefix),
        "sketch_radius": build_parameter_name("CKR", 1, prefix=prefix),
    }
    pitch_variable = variable_names["pitch"]
    if str(normalized.get("profile_entry_offset_mode") or "").strip().lower() == "auto":
        profile_entry_offset_expression = _build_thread_linear_expression(
            pitch_variable,
            1.05,
        )
    else:
        profile_entry_offset_expression = _format_thread_expression_number(
            float(normalized["profile_entry_offset"])
        )
    expressions = {
        "sketch_reference_radius": _build_thread_linear_expression(
            variable_names["diameter"],
            0.5,
            radial_epsilon,
        ),
        "sketch_apex_height": _build_crest_round_expression(
            pitch_variable,
            pitch,
            apex_height,
            mode=crest_round_radius_mode,
        ),
        "sketch_tangent_depth": _build_crest_round_expression(
            pitch_variable,
            pitch,
            tangent_depth,
            mode=crest_round_radius_mode,
        ),
        "sketch_tangent_half": _build_crest_round_expression(
            pitch_variable,
            pitch,
            tangent_half_width,
            mode=crest_round_radius_mode,
        ),
        "sketch_radius": _build_crest_round_expression(
            pitch_variable,
            pitch,
            crest_round_radius,
            mode=crest_round_radius_mode,
        ),
        "phase_shift": _build_crest_round_expression(
            pitch_variable,
            pitch,
            phase_shift,
            mode=phase_shift_mode,
        ),
    }
    expressions["profile_origin_offset"] = (
        f"{profile_entry_offset_expression} + {expressions['phase_shift']}"
    )
    constraints = _build_external_crest_round_constraint_plan()
    dimensions = _build_external_crest_round_dimension_plan(variable_names, expressions)
    verification = {
        "ok": True,
        "checks": [
            {"name": "crest_round_radius_positive", "ok": crest_round_radius > 0.0, "value": crest_round_radius},
            {"name": "tangent_half_within_outer_half", "ok": tangent_half_width < float(normalized["profile_outer_half_width"]), "value": tangent_half_width},
            {"name": "phase_shift_within_pitch", "ok": 0.0 < phase_shift < pitch, "value": phase_shift},
        ],
    }
    verification["ok"] = all(bool(item.get("ok")) for item in verification["checks"])

    feature_display_name = f"{normalized['feature_display_name']} crest round"
    path_display_name = f"{normalized['path_display_name']} crest round"
    profile_display_name = f"{normalized['profile_display_name']} crest round"
    operation_label = build_operation_label(
        feature_display_name,
        parameter_prefix=f"{prefix}_CREST",
    )
    return {
        "enabled": True,
        "internal": internal,
        "role": "crest_round_pass",
        "operation_label": operation_label,
        "feature_display_name": feature_display_name,
        "path_display_name": path_display_name,
        "profile_display_name": profile_display_name,
        "profile_origin_name": f"{normalized['profile_origin_name']}_CREST",
        "start_center_name": f"{normalized['start_center_name']}_CREST",
        "phase_shift": phase_shift,
        "phase_shift_mode": phase_shift_mode,
        "phase_shift_expression": expressions["phase_shift"],
        "phase_shift_direction": "along_build_direction",
        "profile_origin_offset": profile_origin_offset,
        "profile_origin_offset_expression": expressions["profile_origin_offset"],
        "profile_origin_phase_compensation": phase_shift,
        "crest_round_radius": crest_round_radius,
        "crest_round_radius_mode": crest_round_radius_mode,
        "radial_epsilon": radial_epsilon,
        "radial_epsilon_mode": radial_epsilon_mode,
        "crest_apex_height": apex_height,
        "crest_tangent_depth": tangent_depth,
        "crest_tangent_half_width": tangent_half_width,
        "profile_points": profile_points,
        "profile_lines": profile_lines,
        "profile_arcs": profile_arcs,
        "construction_lines": construction_lines,
        "constraints": constraints,
        "dimensions": dimensions,
        "variable_names": variable_names,
        "dimension_expressions": expressions,
        "axis_start": [0.0, 0.0],
        "axis_end": [0.0, min(0.0, apex_y) - axis_margin] if internal else [0.0, max(apex_y, crest_y) + axis_margin],
        "operation_variable_bindings": _build_helical_thread_spiral_variable_bindings(
            normalized,
            target="crest_round_spiral_path",
        ),
        "verification": verification,
        "named_points": {
            "apex": [0.0, apex_y],
            "left_tangent": [-tangent_half_width, tangent_y],
            "right_tangent": [tangent_half_width, tangent_y],
            "arc_center": [0.0, arc_center_y],
        },
    }


def _build_helical_thread_source_diameter_expression(normalized: dict[str, Any]) -> str:
    variable_names = normalized.get("profile_variable_names") or {}
    diameter_variable = str(variable_names.get("diameter") or "").strip()
    return diameter_variable


def _source_selector_step_index(selector: str | None) -> int | None:
    match = re.search(r"step_(\d+)_", str(selector or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _apply_helical_thread_source_variable_bindings(normalized: dict[str, Any]) -> None:
    source_preview = copy.deepcopy(normalized.get("source_preview") or {})
    bindings: list[dict[str, Any]] = []
    diameter_expression = _build_helical_thread_source_diameter_expression(normalized)
    target_index = _source_selector_step_index(normalized.get("source_selector")) or 1
    matched = False
    if diameter_expression:
        for operation in source_preview.get("operations") or []:
            if operation.get("operation") != "add_variables":
                continue
            for variable in operation.get("variables") or []:
                if str(variable.get("kind") or "").strip().lower() != "driving_diameter":
                    continue
                step_name = str(variable.get("step_name") or "")
                if target_index != 1 and step_name and step_name not in {
                    "step_%s" % target_index,
                    "step-%s" % target_index,
                    str(target_index),
                }:
                    continue
                variable["expression"] = diameter_expression
                bindings.append(
                    {
                        "source_scenario": normalized["source_scenario"],
                        "source_selector": normalized["source_selector"],
                        "variable": str(variable.get("name") or ""),
                        "kind": "driving_diameter",
                        "expression": diameter_expression,
                        "target_step_index": target_index,
                    }
                )
                matched = True
                break
            if matched:
                break

    if matched:
        params_payload = source_preview.get("params")
        if isinstance(params_payload, dict):
            steps = params_payload.get("steps")
            if isinstance(steps, list) and 0 <= target_index - 1 < len(steps) and isinstance(steps[target_index - 1], dict):
                steps[target_index - 1]["diameter_expression"] = diameter_expression
    normalized["source_preview"] = source_preview
    normalized["source_variable_bindings"] = bindings


def _prepare_helical_thread_source_params(source_params: dict[str, Any], *, parameter_prefix: str) -> dict[str, Any]:
    prepared = copy.deepcopy(source_params)
    if "parameter_prefix" not in prepared:
        prepared["parameter_prefix"] = f"{parameter_prefix}_SOURCE"
    nested_params = prepared.get("source_params")
    if isinstance(nested_params, dict) and "parameter_prefix" not in nested_params:
        nested_params["parameter_prefix"] = f"{parameter_prefix}_CARRIER"
    return prepared


def _build_helical_thread_profile_geometry(normalized: dict[str, Any]) -> dict[str, Any]:
    if str(normalized.get("profile_root_shape") or "round") == "flat":
        return build_v60_flat_thread_profile_sketch(normalized)

    if not normalized["internal"]:
        half_pitch = float(normalized["pitch"]) / 2.0
        reference_radius = float(normalized["thread_reference_radius"])
        outer_half_width = float(normalized["profile_outer_half_width"])
        root_shape = str(normalized.get("profile_root_shape") or "round")
        if root_shape == "flat":
            taper_slope = float(normalized.get("profile_taper_slope") or 0.0)
            conical = str(normalized.get("carrier_shape") or "cylindrical") == "conical"
            def y_at(x: float, y0: float) -> float:
                return float(y0) + float(taper_slope) * float(x)

            root_half_width = float(normalized["profile_root_half_width"])
            base_drop = float(normalized["profile_base_drop"])
            apex_height = -float(normalized["profile_apex_height"])
            root_depth = -float(normalized["radial_cut_depth"])
            crest_y = reference_radius
            theory_y = crest_y + base_drop
            apex_y = crest_y + apex_height
            root_y = crest_y + root_depth
            axis_margin = max(abs(crest_y), abs(apex_y), abs(root_y), abs(base_drop), abs(half_pitch), outer_half_width, root_half_width, 1.0) * 0.25
            left_outer = [-outer_half_width, y_at(-outer_half_width, crest_y)]
            right_outer = [outer_half_width, y_at(outer_half_width, crest_y)]
            left_root = [-root_half_width, y_at(-root_half_width, root_y)]
            right_root = [root_half_width, y_at(root_half_width, root_y)]
            profile_points = [
                left_outer,
                left_root,
                right_root,
                right_outer,
                left_outer,
            ]
            construction_lines = [
                {"target": "radius_ref", "start": [0.0, 0.0], "end": [0.0, crest_y], "line_style": 6},
                {"target": "theory_drop_ref", "start": [0.0, crest_y], "end": [0.0, theory_y], "line_style": 6},
                {"target": "apex_ref", "start": [0.0, crest_y], "end": [0.0, apex_y], "line_style": 6},
                {"target": "left_pitch_ref", "start": [0.0, theory_y], "end": [-half_pitch, y_at(-half_pitch, theory_y)], "line_style": 6},
                {"target": "right_pitch_ref", "start": [0.0, theory_y], "end": [half_pitch, y_at(half_pitch, theory_y)], "line_style": 6},
                {"target": "left_theory", "start": [0.0, apex_y], "end": [-half_pitch, y_at(-half_pitch, theory_y)], "line_style": 6},
                {"target": "right_theory", "start": [0.0, apex_y], "end": [half_pitch, y_at(half_pitch, theory_y)], "line_style": 6},
                {"target": "root_depth_ref", "start": [0.0, crest_y], "end": [0.0, root_y], "line_style": 6},
                {"target": "left_root_ref", "start": [0.0, root_y], "end": left_root, "line_style": 6},
                {"target": "right_root_ref", "start": [0.0, root_y], "end": right_root, "line_style": 6},
                {"target": "left_outer_ref", "start": [0.0, crest_y], "end": left_outer, "line_style": 6},
                {"target": "right_outer_ref", "start": [0.0, crest_y], "end": right_outer, "line_style": 6},
            ]
            if conical:
                construction_lines.extend(
                    [
                        {"target": "surface_taper_ref", "start": left_outer, "end": right_outer, "line_style": 6},
                        {"target": "root_taper_ref", "start": left_root, "end": right_root, "line_style": 6},
                    ]
                )
            profile_lines = [
                {"target": "profile_line_1", "start": left_outer, "end": left_root},
                {"target": "profile_line_2", "start": right_outer, "end": right_root},
                {"target": "profile_line_3", "start": right_outer, "end": left_outer},
                {"target": "profile_line_4", "start": left_root, "end": right_root},
            ]
            return {
                "profile_points": profile_points,
                "profile_lines": profile_lines,
                "profile_arcs": [],
                "construction_lines": construction_lines,
                "axis_start": [0.0, 0.0],
                "axis_end": [0.0, min(0.0, apex_y) - axis_margin],
            }
        root_radius = float(normalized["root_radius"])
        tangent_half_width = float(normalized["profile_tangent_half_width"])
        tangent_depth = -float(normalized["profile_tangent_depth"])
        arc_center_depth = -float(normalized["profile_arc_center_depth"])
        base_drop = float(normalized["profile_base_drop"])
        apex_height = -float(normalized["profile_apex_height"])
        root_depth = -float(normalized["radial_cut_depth"])
        crest_y = reference_radius
        theory_y = crest_y + base_drop
        apex_y = crest_y + apex_height
        root_y = crest_y + root_depth
        arc_center_y = crest_y + arc_center_depth
        tangent_y = crest_y + tangent_depth
        axis_margin = max(abs(crest_y), abs(apex_y), abs(root_y), abs(base_drop), abs(half_pitch), outer_half_width, root_radius, 1.0) * 0.25
        profile_points = [
            [-outer_half_width, crest_y],
            [-tangent_half_width, tangent_y],
            [tangent_half_width, tangent_y],
            [outer_half_width, crest_y],
            [-outer_half_width, crest_y],
        ]
        construction_lines = [
            {"target": "radius_ref", "start": [0.0, 0.0], "end": [0.0, crest_y], "line_style": 6},
            {"target": "theory_drop_ref", "start": [0.0, crest_y], "end": [0.0, theory_y], "line_style": 6},
            {"target": "apex_ref", "start": [0.0, crest_y], "end": [0.0, apex_y], "line_style": 6},
            {"target": "left_pitch_ref", "start": [0.0, theory_y], "end": [-half_pitch, theory_y], "line_style": 6},
            {"target": "right_pitch_ref", "start": [0.0, theory_y], "end": [half_pitch, theory_y], "line_style": 6},
            {"target": "left_theory", "start": [0.0, apex_y], "end": [-half_pitch, theory_y], "line_style": 6},
            {"target": "right_theory", "start": [0.0, apex_y], "end": [half_pitch, theory_y], "line_style": 6},
            {"target": "root_depth_ref", "start": [0.0, crest_y], "end": [0.0, root_y], "line_style": 6},
            {"target": "center_ref", "start": [0.0, root_y], "end": [0.0, arc_center_y], "line_style": 6},
            {"target": "left_outer_ref", "start": [0.0, crest_y], "end": [-outer_half_width, crest_y], "line_style": 6},
            {"target": "right_outer_ref", "start": [0.0, crest_y], "end": [outer_half_width, crest_y], "line_style": 6},
        ]
        profile_lines = [
            {"target": "profile_line_1", "start": [-outer_half_width, crest_y], "end": [-tangent_half_width, tangent_y]},
            {"target": "profile_line_2", "start": [outer_half_width, crest_y], "end": [tangent_half_width, tangent_y]},
            {"target": "profile_line_3", "start": [outer_half_width, crest_y], "end": [-outer_half_width, crest_y]},
        ]
        profile_arcs = [
            {
                "target": "root_arc",
                "xc": 0.0,
                "yc": arc_center_y,
                "radius": root_radius,
                "x1": tangent_half_width,
                "y1": tangent_y,
                "x2": -tangent_half_width,
                "y2": tangent_y,
                "direction": True,
            }
        ]
        return {
            "profile_points": profile_points,
            "profile_lines": profile_lines,
            "profile_arcs": profile_arcs,
            "construction_lines": construction_lines,
            "axis_start": [0.0, 0.0],
            "axis_end": [0.0, min(0.0, apex_y) - axis_margin],
        }

    half_pitch = float(normalized["pitch"]) / 2.0
    reference_radius = float(normalized["thread_reference_radius"])
    outer_half_width = float(normalized["profile_outer_half_width"])
    root_half_width = float(normalized["profile_root_half_width"])
    root_shape = str(normalized.get("profile_root_shape") or "round")
    root_radius = float(normalized["root_radius"])
    tangent_half_width = root_half_width
    tangent_depth = float(normalized["profile_tangent_depth"])
    arc_center_depth = float(normalized["profile_arc_center_depth"])
    crest_drop = -float(normalized["profile_crest_drop"])
    radial_root = float(normalized["radial_cut_depth"])
    crest_y = -reference_radius
    pitch_y = crest_y - crest_drop
    root_y = crest_y - tangent_depth
    apex_y = crest_y - radial_root
    arc_center_y = crest_y - arc_center_depth
    axis_margin = max(abs(crest_y), abs(root_y), abs(apex_y), abs(outer_half_width), abs(half_pitch), root_radius, 1.0) * 0.35
    taper_slope = float(normalized.get("profile_taper_slope") or 0.0)
    conical = str(normalized.get("carrier_shape") or "cylindrical") == "conical"
    def y_at(x: float, y0: float) -> float:
        return float(y0) + float(taper_slope) * float(x)

    left_outer = [-outer_half_width, y_at(-outer_half_width, crest_y)]
    right_outer = [outer_half_width, y_at(outer_half_width, crest_y)]
    left_root = [-tangent_half_width, y_at(-tangent_half_width, root_y)]
    right_root = [tangent_half_width, y_at(tangent_half_width, root_y)]
    profile_points = [
        left_outer,
        left_root,
        right_root,
        right_outer,
        left_outer,
    ]
    construction_lines = [
        {"target": "radius_ref", "start": [0.0, 0.0], "end": [0.0, crest_y], "line_style": 6},
        {"target": "theory_drop_ref", "start": [0.0, crest_y], "end": [0.0, pitch_y], "line_style": 6},
        {"target": "apex_ref", "start": [0.0, crest_y], "end": [0.0, apex_y], "line_style": 6},
        {"target": "left_pitch_ref", "start": [0.0, pitch_y], "end": [-half_pitch, y_at(-half_pitch, pitch_y)], "line_style": 6},
        {"target": "right_pitch_ref", "start": [0.0, pitch_y], "end": [half_pitch, y_at(half_pitch, pitch_y)], "line_style": 6},
        {"target": "left_theory", "start": [0.0, apex_y], "end": [-half_pitch, y_at(-half_pitch, pitch_y)], "line_style": 6},
        {"target": "right_theory", "start": [0.0, apex_y], "end": [half_pitch, y_at(half_pitch, pitch_y)], "line_style": 6},
        {"target": "left_root_ref", "start": [0.0, root_y], "end": left_root, "line_style": 6},
        {"target": "right_root_ref", "start": [0.0, root_y], "end": right_root, "line_style": 6},
        {"target": "left_outer_ref", "start": [0.0, crest_y], "end": left_outer, "line_style": 6},
        {"target": "right_outer_ref", "start": [0.0, crest_y], "end": right_outer, "line_style": 6},
    ]
    if conical:
        construction_lines.extend(
            [
                {"target": "surface_taper_ref", "start": left_outer, "end": right_outer, "line_style": 6},
                {"target": "root_taper_ref", "start": left_root, "end": right_root, "line_style": 6},
            ]
        )
    profile_lines = [
        {"target": "profile_line_1", "start": left_outer, "end": left_root},
        {"target": "profile_line_2", "start": right_outer, "end": right_root},
        {"target": "profile_line_3", "start": right_outer, "end": left_outer},
    ]
    if root_shape == "flat":
        profile_lines.append(
            {"target": "profile_line_4", "start": left_root, "end": right_root}
        )
        return {
            "profile_points": profile_points,
            "profile_lines": profile_lines,
            "profile_arcs": [],
            "construction_lines": construction_lines,
            "axis_start": [0.0, 0.0],
            "axis_end": [0.0, min(0.0, apex_y) - axis_margin],
        }
    profile_arcs = [
        {
            "target": "root_arc",
            "xc": 0.0,
            "yc": arc_center_y,
            "radius": root_radius,
            "x1": tangent_half_width,
            "y1": root_y,
            "x2": -tangent_half_width,
            "y2": root_y,
            "direction": True,
        }
    ]
    return {
        "profile_points": profile_points,
        "profile_lines": profile_lines,
        "profile_arcs": profile_arcs,
        "construction_lines": construction_lines,
        "axis_start": [0.0, 0.0],
        "axis_end": [0.0, min(0.0, apex_y) - axis_margin],
    }


def _translate_helical_thread_profile_geometry(geometry: dict[str, Any], delta_y: float) -> dict[str, Any]:
    shift = float(delta_y)

    def shift_point(point: list[float] | tuple[float, float]) -> list[float]:
        return [float(point[0]), float(point[1]) + shift]

    def shift_line(line: dict[str, Any]) -> dict[str, Any]:
        updated = dict(line)
        if "start" in updated and isinstance(updated["start"], list) and len(updated["start"]) == 2:
            updated["start"] = shift_point(updated["start"])
        if "end" in updated and isinstance(updated["end"], list) and len(updated["end"]) == 2:
            updated["end"] = shift_point(updated["end"])
        return updated

    def shift_arc(arc: dict[str, Any]) -> dict[str, Any]:
        updated = dict(arc)
        updated["yc"] = float(updated.get("yc") or 0.0) + shift
        updated["y1"] = float(updated.get("y1") or 0.0) + shift
        updated["y2"] = float(updated.get("y2") or 0.0) + shift
        return updated

    return {
        "profile_points": [shift_point(point) for point in list(geometry.get("profile_points") or [])],
        "profile_lines": [shift_line(line) for line in list(geometry.get("profile_lines") or [])],
        "profile_arcs": [shift_arc(arc) for arc in list(geometry.get("profile_arcs") or [])],
        "construction_lines": [shift_line(line) for line in list(geometry.get("construction_lines") or [])],
        "axis_start": shift_point(list(geometry.get("axis_start") or [0.0, 0.0])),
        "axis_end": shift_point(list(geometry.get("axis_end") or [0.0, 1.0])),
    }


def _mirror_helical_thread_profile_geometry_y(geometry: dict[str, Any]) -> dict[str, Any]:
    def mirror_point(point: list[float] | tuple[float, float]) -> list[float]:
        return [float(point[0]), -float(point[1])]

    def mirror_line(line: dict[str, Any]) -> dict[str, Any]:
        updated = dict(line)
        if "start" in updated and isinstance(updated["start"], list) and len(updated["start"]) == 2:
            updated["start"] = mirror_point(updated["start"])
        if "end" in updated and isinstance(updated["end"], list) and len(updated["end"]) == 2:
            updated["end"] = mirror_point(updated["end"])
        return updated

    def mirror_arc(arc: dict[str, Any]) -> dict[str, Any]:
        updated = dict(arc)
        updated["yc"] = -float(updated.get("yc") or 0.0)
        updated["y1"] = -float(updated.get("y1") or 0.0)
        updated["y2"] = -float(updated.get("y2") or 0.0)
        updated["direction"] = not bool(updated.get("direction", True))
        return updated

    return {
        "profile_points": [mirror_point(point) for point in list(geometry.get("profile_points") or [])],
        "profile_lines": [mirror_line(line) for line in list(geometry.get("profile_lines") or [])],
        "profile_arcs": [mirror_arc(arc) for arc in list(geometry.get("profile_arcs") or [])],
        "construction_lines": [mirror_line(line) for line in list(geometry.get("construction_lines") or [])],
        "axis_start": mirror_point(list(geometry.get("axis_start") or [0.0, 0.0])),
        "axis_end": mirror_point(list(geometry.get("axis_end") or [0.0, 1.0])),
    }


def _build_helical_thread_constraint_plan(
    internal: bool,
    *,
    root_shape: str = "round",
    carrier_shape: str = "cylindrical",
) -> list[dict[str, Any]]:
    root_shape = str(root_shape or "round")
    carrier_shape = str(carrier_shape or "cylindrical")
    if root_shape == "flat":
        return build_v60_flat_thread_profile_constraints(
            internal=bool(internal),
            carrier_shape=carrier_shape,
        )
    if not internal:
        if root_shape == "flat":
            if carrier_shape == "conical":
                return [
                    {"kind": "fixed_point", "target": "origin", "index": 0},
                    {"kind": "vertical", "target": "axis"},
                    {"kind": "vertical", "target": "radius_ref"},
                    {"kind": "vertical", "target": "theory_drop_ref"},
                    {"kind": "vertical", "target": "apex_ref"},
                    {"kind": "vertical", "target": "root_depth_ref"},
                    {"kind": "merge_points", "target": "radius_ref", "index": 0, "partner": "axis", "partner_index": 0},
                    {"kind": "merge_points", "target": "theory_drop_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                    {"kind": "merge_points", "target": "apex_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                    {"kind": "merge_points", "target": "axis", "index": 1, "partner": "apex_ref", "partner_index": 1},
                    {"kind": "merge_points", "target": "root_depth_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                    {"kind": "merge_points", "target": "left_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                    {"kind": "merge_points", "target": "right_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                    {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "left_pitch_ref", "partner_index": 0},
                    {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "right_pitch_ref", "partner_index": 0},
                    {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "left_theory", "partner_index": 0},
                    {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "right_theory", "partner_index": 0},
                    {"kind": "merge_points", "target": "left_pitch_ref", "index": 1, "partner": "left_theory", "partner_index": 1},
                    {"kind": "merge_points", "target": "right_pitch_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
                    {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_1", "partner_index": 0},
                    {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 1},
                    {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_2", "partner_index": 0},
                    {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 0},
                    {"kind": "merge_points", "target": "root_depth_ref", "index": 1, "partner": "left_root_ref", "partner_index": 0},
                    {"kind": "merge_points", "target": "root_depth_ref", "index": 1, "partner": "right_root_ref", "partner_index": 0},
                    {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_1", "partner_index": 1},
                    {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 0},
                    {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "profile_line_2", "partner_index": 1},
                    {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 1},
                    {"kind": "equal_length", "target": "left_pitch_ref", "partner": "right_pitch_ref"},
                    {"kind": "equal_length", "target": "left_outer_ref", "partner": "right_outer_ref"},
                    {"kind": "equal_length", "target": "left_root_ref", "partner": "right_root_ref"},
                    {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
                    {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
                    {"kind": "collinear", "target": "profile_line_3", "partner": "surface_taper_ref"},
                    {"kind": "collinear", "target": "profile_line_4", "partner": "root_taper_ref"},
                ]
            return [
                {"kind": "fixed_point", "target": "origin", "index": 0},
                {"kind": "vertical", "target": "axis"},
                {"kind": "vertical", "target": "radius_ref"},
                {"kind": "vertical", "target": "theory_drop_ref"},
                {"kind": "vertical", "target": "apex_ref"},
                {"kind": "vertical", "target": "root_depth_ref"},
                {"kind": "horizontal", "target": "left_pitch_ref"},
                {"kind": "horizontal", "target": "right_pitch_ref"},
                {"kind": "horizontal", "target": "left_root_ref"},
                {"kind": "horizontal", "target": "right_root_ref"},
                {"kind": "horizontal", "target": "left_outer_ref"},
                {"kind": "horizontal", "target": "right_outer_ref"},
                {"kind": "horizontal", "target": "profile_line_3"},
                {"kind": "horizontal", "target": "profile_line_4"},
                {"kind": "merge_points", "target": "radius_ref", "index": 0, "partner": "axis", "partner_index": 0},
                {"kind": "merge_points", "target": "theory_drop_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "apex_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "axis", "index": 1, "partner": "apex_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "root_depth_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "left_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "right_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "left_pitch_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "right_pitch_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "left_theory", "partner_index": 0},
                {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "right_theory", "partner_index": 0},
                {"kind": "merge_points", "target": "left_pitch_ref", "index": 1, "partner": "left_theory", "partner_index": 1},
                {"kind": "merge_points", "target": "right_pitch_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
                {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_1", "partner_index": 0},
                {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 1},
                {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_2", "partner_index": 0},
                {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 0},
                {"kind": "merge_points", "target": "root_depth_ref", "index": 1, "partner": "left_root_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "root_depth_ref", "index": 1, "partner": "right_root_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_1", "partner_index": 1},
                {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 0},
                {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "profile_line_2", "partner_index": 1},
                {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 1},
                {"kind": "equal_length", "target": "left_pitch_ref", "partner": "right_pitch_ref"},
                {"kind": "equal_length", "target": "left_outer_ref", "partner": "right_outer_ref"},
                {"kind": "equal_length", "target": "left_root_ref", "partner": "right_root_ref"},
                {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
                {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
            ]
        return [
            {"kind": "fixed_point", "target": "origin", "index": 0},
            {"kind": "vertical", "target": "axis"},
            {"kind": "vertical", "target": "radius_ref"},
            {"kind": "vertical", "target": "theory_drop_ref"},
            {"kind": "vertical", "target": "apex_ref"},
            {"kind": "vertical", "target": "root_depth_ref"},
            {"kind": "vertical", "target": "center_ref"},
            {"kind": "horizontal", "target": "left_pitch_ref"},
            {"kind": "horizontal", "target": "right_pitch_ref"},
            {"kind": "horizontal", "target": "left_outer_ref"},
            {"kind": "horizontal", "target": "right_outer_ref"},
            {"kind": "horizontal", "target": "profile_line_3"},
            {"kind": "merge_points", "target": "radius_ref", "index": 0, "partner": "axis", "partner_index": 0},
            {"kind": "merge_points", "target": "theory_drop_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "apex_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "axis", "index": 1, "partner": "apex_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "root_depth_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "left_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "right_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "left_pitch_ref", "partner_index": 0},
            {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "right_pitch_ref", "partner_index": 0},
            {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "left_theory", "partner_index": 0},
            {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "right_theory", "partner_index": 0},
            {"kind": "merge_points", "target": "left_pitch_ref", "index": 1, "partner": "left_theory", "partner_index": 1},
            {"kind": "merge_points", "target": "right_pitch_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
            {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_1", "partner_index": 0},
            {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 1},
            {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_2", "partner_index": 0},
            {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 0},
            {"kind": "merge_points", "target": "root_depth_ref", "index": 1, "partner": "center_ref", "partner_index": 0},
            {"kind": "equal_length", "target": "left_pitch_ref", "partner": "right_pitch_ref"},
            {"kind": "equal_length", "target": "left_outer_ref", "partner": "right_outer_ref"},
            {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
            {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
            {"kind": "tangent", "target": "root_arc", "partner": "profile_line_1"},
            {"kind": "tangent", "target": "root_arc", "partner": "profile_line_2"},
            {"kind": "merge_points", "target": "center_ref", "index": 1, "partner": "root_arc", "partner_index": 0},
            {"kind": "merge_points", "target": "profile_line_1", "index": 1, "partner": "root_arc", "partner_index": 2},
            {"kind": "merge_points", "target": "profile_line_2", "index": 1, "partner": "root_arc", "partner_index": 1},
        ]

    if root_shape == "flat":
        if carrier_shape == "conical":
            return [
                {"kind": "fixed_point", "target": "origin", "index": 0},
                {"kind": "vertical", "target": "axis"},
                {"kind": "vertical", "target": "radius_ref"},
                {"kind": "vertical", "target": "theory_drop_ref"},
                {"kind": "vertical", "target": "apex_ref"},
                {"kind": "merge_points", "target": "radius_ref", "index": 0, "partner": "axis", "partner_index": 0},
                {"kind": "merge_points", "target": "theory_drop_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "apex_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "axis", "index": 1, "partner": "apex_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "left_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "right_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "left_pitch_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "right_pitch_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "left_theory", "partner_index": 0},
                {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "right_theory", "partner_index": 0},
                {"kind": "merge_points", "target": "left_pitch_ref", "index": 1, "partner": "left_theory", "partner_index": 1},
                {"kind": "merge_points", "target": "right_pitch_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
                {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_1", "partner_index": 0},
                {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 1},
                {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_2", "partner_index": 0},
                {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 0},
                {"kind": "point_on_curve", "target": "left_root_ref", "index": 0, "partner": "axis"},
                {"kind": "point_on_curve", "target": "right_root_ref", "index": 0, "partner": "axis"},
                {"kind": "equal_length", "target": "left_pitch_ref", "partner": "right_pitch_ref"},
                {"kind": "equal_length", "target": "left_outer_ref", "partner": "right_outer_ref"},
                {"kind": "equal_length", "target": "left_root_ref", "partner": "right_root_ref"},
                {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
                {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
                {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_1", "partner_index": 1},
                {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 0},
                {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "profile_line_2", "partner_index": 1},
                {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 1},
                {"kind": "collinear", "target": "profile_line_3", "partner": "surface_taper_ref"},
                {"kind": "collinear", "target": "profile_line_4", "partner": "root_taper_ref"},
            ]
        return [
            {"kind": "fixed_point", "target": "origin", "index": 0},
            {"kind": "vertical", "target": "axis"},
            {"kind": "vertical", "target": "radius_ref"},
            {"kind": "vertical", "target": "theory_drop_ref"},
            {"kind": "vertical", "target": "apex_ref"},
            {"kind": "horizontal", "target": "left_pitch_ref"},
            {"kind": "horizontal", "target": "right_pitch_ref"},
            {"kind": "horizontal", "target": "left_root_ref"},
            {"kind": "horizontal", "target": "right_root_ref"},
            {"kind": "horizontal", "target": "left_outer_ref"},
            {"kind": "horizontal", "target": "right_outer_ref"},
            {"kind": "horizontal", "target": "profile_line_3"},
            {"kind": "horizontal", "target": "profile_line_4"},
            {"kind": "merge_points", "target": "radius_ref", "index": 0, "partner": "axis", "partner_index": 0},
            {"kind": "merge_points", "target": "theory_drop_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "apex_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "axis", "index": 1, "partner": "apex_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "left_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "right_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
            {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "left_pitch_ref", "partner_index": 0},
            {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "right_pitch_ref", "partner_index": 0},
            {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "left_theory", "partner_index": 0},
            {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "right_theory", "partner_index": 0},
            {"kind": "merge_points", "target": "left_pitch_ref", "index": 1, "partner": "left_theory", "partner_index": 1},
            {"kind": "merge_points", "target": "right_pitch_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
            {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_1", "partner_index": 0},
            {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 1},
            {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_2", "partner_index": 0},
            {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 0},
            {"kind": "point_on_curve", "target": "left_root_ref", "index": 0, "partner": "axis"},
            {"kind": "point_on_curve", "target": "right_root_ref", "index": 0, "partner": "axis"},
            {"kind": "equal_length", "target": "left_pitch_ref", "partner": "right_pitch_ref"},
            {"kind": "equal_length", "target": "left_outer_ref", "partner": "right_outer_ref"},
            {"kind": "equal_length", "target": "left_root_ref", "partner": "right_root_ref"},
            {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
            {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
            {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_1", "partner_index": 1},
            {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 0},
            {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "profile_line_2", "partner_index": 1},
            {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 1},
        ]

    return [
        {"kind": "fixed_point", "target": "origin", "index": 0},
        {"kind": "vertical", "target": "axis"},
        {"kind": "vertical", "target": "radius_ref"},
        {"kind": "vertical", "target": "theory_drop_ref"},
        {"kind": "vertical", "target": "apex_ref"},
        {"kind": "horizontal", "target": "left_pitch_ref"},
        {"kind": "horizontal", "target": "right_pitch_ref"},
        {"kind": "horizontal", "target": "left_root_ref"},
        {"kind": "horizontal", "target": "right_root_ref"},
        {"kind": "horizontal", "target": "left_outer_ref"},
        {"kind": "horizontal", "target": "right_outer_ref"},
        {"kind": "horizontal", "target": "profile_line_3"},
        {"kind": "merge_points", "target": "radius_ref", "index": 0, "partner": "axis", "partner_index": 0},
        {"kind": "merge_points", "target": "theory_drop_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
        {"kind": "merge_points", "target": "apex_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
        {"kind": "merge_points", "target": "axis", "index": 1, "partner": "apex_ref", "partner_index": 1},
        {"kind": "merge_points", "target": "left_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
        {"kind": "merge_points", "target": "right_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
        {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "left_pitch_ref", "partner_index": 0},
        {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "right_pitch_ref", "partner_index": 0},
        {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "left_theory", "partner_index": 0},
        {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "right_theory", "partner_index": 0},
        {"kind": "merge_points", "target": "left_pitch_ref", "index": 1, "partner": "left_theory", "partner_index": 1},
        {"kind": "merge_points", "target": "right_pitch_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
        {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_1", "partner_index": 0},
        {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 1},
        {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_2", "partner_index": 0},
        {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 0},
        {"kind": "point_on_curve", "target": "left_root_ref", "index": 0, "partner": "axis"},
        {"kind": "point_on_curve", "target": "right_root_ref", "index": 0, "partner": "axis"},
        {"kind": "equal_length", "target": "left_pitch_ref", "partner": "right_pitch_ref"},
        {"kind": "equal_length", "target": "left_outer_ref", "partner": "right_outer_ref"},
        {"kind": "equal_length", "target": "left_root_ref", "partner": "right_root_ref"},
        {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
        {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
        {"kind": "tangent", "target": "root_arc", "partner": "profile_line_1"},
        {"kind": "tangent", "target": "root_arc", "partner": "profile_line_2"},
        {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "root_arc", "partner_index": 2},
        {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "root_arc", "partner_index": 1},
        {"kind": "merge_points", "target": "profile_line_1", "index": 1, "partner": "root_arc", "partner_index": 2},
        {"kind": "merge_points", "target": "profile_line_2", "index": 1, "partner": "root_arc", "partner_index": 1},
    ]


def _build_helical_thread_dimension_plan(
    variable_names: dict[str, str],
    expressions: dict[str, str],
    *,
    internal: bool,
) -> list[dict[str, Any]]:
    if not internal:
        if "sketch_root_half" in variable_names:
            dimensions = [
                {
                    "kind": "line_length",
                    "target": "radius_ref",
                    "name": variable_names["sketch_reference_radius"],
                    "variable": variable_names["sketch_reference_radius"],
                    "expression": expressions["sketch_reference_radius"],
                    "placement_index": 0,
                },
                {
                    "kind": "line_length",
                    "target": "right_pitch_ref",
                    "name": variable_names["sketch_pitch_half"],
                    "variable": variable_names["sketch_pitch_half"],
                    "expression": expressions["sketch_pitch_half"],
                    "placement_index": 1,
                },
                {
                    "kind": "line_length",
                    "target": "theory_drop_ref",
                    "name": variable_names["sketch_base_drop"],
                    "variable": variable_names["sketch_base_drop"],
                    "expression": expressions["sketch_base_drop"],
                    "placement_index": 2,
                },
                {
                    "kind": "line_length",
                    "target": "apex_ref",
                    "name": variable_names["sketch_apex_height"],
                    "variable": variable_names["sketch_apex_height"],
                    "expression": expressions["sketch_apex_height"],
                    "placement_index": 3,
                },
                {
                    "kind": "line_length",
                    "target": "right_outer_ref",
                    "name": variable_names["sketch_outer_half"],
                    "variable": variable_names["sketch_outer_half"],
                    "expression": expressions["sketch_outer_half"],
                    "placement_index": 4,
                },
                {
                    "kind": "line_length",
                    "target": "root_depth_ref",
                    "name": variable_names["sketch_depth"],
                    "variable": variable_names["sketch_depth"],
                    "expression": expressions["sketch_depth"],
                    "placement_index": 5,
                },
                {
                    "kind": "line_length",
                    "target": "right_root_ref",
                    "name": variable_names["sketch_root_half"],
                    "variable": variable_names["sketch_root_half"],
                    "expression": expressions["sketch_root_half"],
                    "placement_index": 6,
                },
            ]
            if "sketch_outer_taper_offset" in variable_names:
                dimensions.extend(
                    [
                        {
                            "kind": "line_length",
                            "target": "right_outer_projection_ref",
                            "name": variable_names["sketch_outer_taper_offset"],
                            "variable": variable_names["sketch_outer_taper_offset"],
                            "expression": expressions["sketch_outer_taper_offset"],
                            "placement_index": 7,
                        },
                        {
                            "kind": "line_length",
                            "target": "right_root_projection_ref",
                            "name": variable_names["sketch_root_taper_offset"],
                            "variable": variable_names["sketch_root_taper_offset"],
                            "expression": expressions["sketch_root_taper_offset"],
                            "placement_index": 8,
                        },
                    ]
                )
            return dimensions
        return [
            {
                "kind": "line_length",
                "target": "radius_ref",
                "name": variable_names["sketch_reference_radius"],
                "variable": variable_names["sketch_reference_radius"],
                "expression": expressions["sketch_reference_radius"],
                "placement_index": 0,
            },
            {
                "kind": "line_length",
                "target": "right_pitch_ref",
                "name": variable_names["sketch_pitch_half"],
                "variable": variable_names["sketch_pitch_half"],
                "expression": expressions["sketch_pitch_half"],
                "placement_index": 1,
            },
            {
                "kind": "line_length",
                "target": "theory_drop_ref",
                "name": variable_names["sketch_base_drop"],
                "variable": variable_names["sketch_base_drop"],
                "expression": expressions["sketch_base_drop"],
                "placement_index": 2,
            },
            {
                "kind": "line_length",
                "target": "apex_ref",
                "name": variable_names["sketch_apex_height"],
                "variable": variable_names["sketch_apex_height"],
                "expression": expressions["sketch_apex_height"],
                "placement_index": 3,
            },
            {
                "kind": "line_length",
                "target": "right_outer_ref",
                "name": variable_names["sketch_outer_half"],
                "variable": variable_names["sketch_outer_half"],
                "expression": expressions["sketch_outer_half"],
                "placement_index": 4,
            },
            {
                "kind": "line_length",
                "target": "root_depth_ref",
                "name": variable_names["sketch_depth"],
                "variable": variable_names["sketch_depth"],
                "expression": expressions["sketch_depth"],
                "placement_index": 5,
            },
            {
                "kind": "line_length",
                "target": "center_ref",
                "name": variable_names["sketch_radius"],
                "variable": variable_names["sketch_radius"],
                "expression": expressions["sketch_radius"],
                "placement_index": 6,
            },
        ]

    dimensions = [
        {
            "kind": "line_length",
            "target": "radius_ref",
            "name": variable_names["sketch_reference_radius"],
            "variable": variable_names["sketch_reference_radius"],
            "expression": expressions["sketch_reference_radius"],
            "placement_index": 0,
        },
        {
            "kind": "line_length",
            "target": "right_pitch_ref",
            "name": variable_names["sketch_pitch_half"],
            "variable": variable_names["sketch_pitch_half"],
            "expression": expressions["sketch_pitch_half"],
            "placement_index": 1,
        },
        {
            "kind": "line_length",
            "target": "theory_drop_ref",
            "name": variable_names["sketch_crest_drop"],
            "variable": variable_names["sketch_crest_drop"],
            "expression": expressions["sketch_crest_drop"],
            "placement_index": 2,
        },
        {
            "kind": "line_length",
            "target": "apex_ref",
            "name": variable_names["sketch_depth"],
            "variable": variable_names["sketch_depth"],
            "expression": expressions["sketch_depth"],
            "placement_index": 3,
        },
        {
            "kind": "line_length",
            "target": "right_outer_ref",
            "name": variable_names["sketch_outer_half"],
            "variable": variable_names["sketch_outer_half"],
            "expression": expressions["sketch_outer_half"],
            "placement_index": 4,
        },
        {
            "kind": "line_length",
            "target": "right_root_ref",
            "name": variable_names["sketch_root_half"],
            "variable": variable_names["sketch_root_half"],
            "expression": expressions["sketch_root_half"],
            "placement_index": 5,
        },
    ]
    if "sketch_outer_taper_offset" in variable_names:
        dimensions.extend(
            [
                {
                    "kind": "line_length",
                    "target": "right_outer_projection_ref",
                    "name": variable_names["sketch_outer_taper_offset"],
                    "variable": variable_names["sketch_outer_taper_offset"],
                    "expression": expressions["sketch_outer_taper_offset"],
                    "placement_index": 6,
                },
                {
                    "kind": "line_length",
                    "target": "right_root_projection_ref",
                    "name": variable_names["sketch_root_taper_offset"],
                    "variable": variable_names["sketch_root_taper_offset"],
                    "expression": expressions["sketch_root_taper_offset"],
                    "placement_index": 7,
                },
            ]
        )
    return dimensions


def _layout_external_helical_thread_dimensions(
    dimensions: list[dict[str, Any]],
    normalized: dict[str, Any],
) -> list[dict[str, Any]]:
    half_pitch = float(normalized["pitch"]) / 2.0
    base_drop = float(normalized["profile_base_drop"])
    apex_height = -float(normalized["profile_apex_height"])
    outer_half_width = float(normalized["profile_outer_half_width"])
    tangent_half_width = float(normalized["profile_tangent_half_width"])
    root_depth = -float(normalized["radial_cut_depth"])
    arc_center_depth = -float(normalized["profile_arc_center_depth"])
    layout_margin = max(abs(root_depth), abs(apex_height), outer_half_width, half_pitch, 1.0) * 0.7

    layout_by_target = {
        "right_pitch_ref": {
            "point_x": half_pitch * 0.55,
            "point_y": base_drop + layout_margin * 0.9,
        },
        "theory_drop_ref": {
            "point_x": -half_pitch - layout_margin * 0.55,
            "point_y": base_drop * 0.5,
        },
        "apex_ref": {
            "point_x": -outer_half_width - layout_margin,
            "point_y": apex_height * 0.5,
        },
        "right_outer_ref": {
            "point_x": outer_half_width * 0.6,
            "point_y": layout_margin * 0.75,
        },
        "root_depth_ref": {
            "point_x": outer_half_width + layout_margin * 0.9,
            "point_y": root_depth * 0.45,
        },
        "center_ref": {
            "point_x": tangent_half_width + layout_margin * 0.45,
            "point_y": (root_depth + arc_center_depth) / 2.0,
        },
    }
    laid_out: list[dict[str, Any]] = []
    for dimension in dimensions:
        payload = dict(dimension)
        payload.update(layout_by_target.get(str(payload.get("target") or ""), {}))
        laid_out.append(payload)
    return laid_out


def _layout_internal_helical_thread_dimensions(
    dimensions: list[dict[str, Any]],
    normalized: dict[str, Any],
) -> list[dict[str, Any]]:
    half_pitch = float(normalized["pitch"]) / 2.0
    outer_half_width = float(normalized["profile_outer_half_width"])
    root_half_width = float(normalized["profile_root_half_width"])
    crest_drop = -float(normalized["profile_crest_drop"])
    root_depth = float(normalized["radial_cut_depth"])
    arc_center_depth = float(normalized["profile_arc_center_depth"])
    layout_margin = max(
        abs(root_depth),
        abs(crest_drop),
        abs(outer_half_width),
        abs(half_pitch),
        abs(root_half_width),
        1.0,
    ) * 0.75

    layout_by_target = {
        "right_pitch_ref": {
            "point_x": half_pitch * 0.55,
            "point_y": crest_drop + layout_margin * 0.9,
        },
        "theory_drop_ref": {
            "point_x": -half_pitch - layout_margin * 0.55,
            "point_y": crest_drop * 0.5,
        },
        "apex_ref": {
            "point_x": -outer_half_width - layout_margin,
            "point_y": root_depth * 0.5,
        },
        "right_outer_ref": {
            "point_x": outer_half_width * 0.6,
            "point_y": -layout_margin * 0.75,
        },
        "right_root_ref": {
            "point_x": root_half_width * 0.8,
            "point_y": root_depth - layout_margin * 0.45,
        },
    }
    laid_out: list[dict[str, Any]] = []
    for dimension in dimensions:
        payload = dict(dimension)
        payload.update(layout_by_target.get(str(payload.get("target") or ""), {}))
        laid_out.append(payload)
    return laid_out


def _normalize_source_diameter_validation_mode(value: Any, *, scenario: str) -> str:
    normalized = str(value or "warn").strip().lower()
    if normalized in {"", "warn"}:
        return "warn"
    if normalized in {"ignore", "off", "disabled"}:
        return "ignore"
    if normalized in {"error", "strict"}:
        return "error"
    raise ValueError(f"{scenario} source_diameter_validation_mode must be one of: ignore, warn, error")


def _resolve_source_diameter_validation_tolerance(params: dict[str, Any], *, scenario: str) -> float:
    raw_value = params.get("source_diameter_tolerance", params.get("source_geometry_tolerance", 0.01))
    try:
        tolerance = float(raw_value if raw_value not in (None, "") else 0.01)
    except Exception as exc:
        raise ValueError(f"{scenario} source_diameter_tolerance must be a number") from exc
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError(f"{scenario} source_diameter_tolerance must be a finite non-negative number")
    return tolerance


def _build_source_diameter_validation(
    *,
    source_diameter: float | None,
    recommended_diameter: float,
    tolerance: float,
    mode: str,
    scenario: str,
    internal: bool,
) -> dict[str, Any]:
    target_label = "source hole diameter" if internal else "source cylinder diameter"
    if source_diameter is None:
        return {
            "status": "unavailable",
            "mode": mode,
            "tolerance": tolerance,
            "source_diameter": None,
            "recommended_diameter": float(recommended_diameter),
            "delta": None,
            "matches": None,
            "message": f"{scenario} could not resolve {target_label} for validation",
        }

    delta = float(source_diameter) - float(recommended_diameter)
    matches = abs(delta) <= float(tolerance)
    status = "match" if matches else "mismatch"
    direction = "larger" if delta > 0.0 else "smaller"
    message = (
        f"{scenario} {target_label} {float(source_diameter):.6f} matches recommended {float(recommended_diameter):.6f}"
        if matches
        else (
            f"{scenario} {target_label} {float(source_diameter):.6f} is {abs(delta):.6f} mm {direction} "
            f"than recommended {float(recommended_diameter):.6f}"
        )
    )
    if status == "mismatch" and mode == "error":
        raise ValueError(message)
    return {
        "status": status,
        "mode": mode,
        "tolerance": float(tolerance),
        "source_diameter": float(source_diameter),
        "recommended_diameter": float(recommended_diameter),
        "delta": float(delta),
        "matches": matches,
        "message": message,
    }


def _build_profile_surface_offset_metadata(
    requested_offset: float,
    *,
    mode: str,
) -> dict[str, Any]:
    note = (
        "Accepted for backward compatibility; in helical_thread V1 this parameter "
        "does not affect profile geometry."
    )
    return {
        "requested": float(requested_offset),
        "effective": 0.0,
        "mode": mode,
        "status": "ignored_in_v1",
        "applied": False,
        "note": note,
    }


def _normalize_helical_thread_params(
    params: dict[str, Any],
    *,
    scenario: str,
    internal: bool,
) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    name = str(params.get("name") or ("Internal helical thread" if internal else "External helical thread"))
    parameter_prefix = _resolve_helical_thread_parameter_prefix(params.get("parameter_prefix"), name, scenario)

    source_scenario_raw = params.get("source_scenario") or params.get("base_scenario")
    if source_scenario_raw is None:
        raise ValueError(f"{scenario} requires source_scenario")
    source_scenario = _normalize_scenario(str(source_scenario_raw))
    allowed_source_scenarios = (
        ("internal_cylindrical_step", "internal_conical_step")
        if internal
        else ("stepped_shaft", "external_conical_step")
    )
    if source_scenario not in allowed_source_scenarios:
        raise ValueError(f"{scenario} source_scenario must be one of: {', '.join(allowed_source_scenarios)}")

    source_params = params.get("source_params")
    if not isinstance(source_params, dict):
        raise ValueError(f"{scenario} source_params must be an object")
    source_params = _prepare_helical_thread_source_params(source_params, parameter_prefix=parameter_prefix)
    source_preview = preview_part_scenario(source_scenario, source_params)

    source_selector = _normalize_thread_source_selector(
        source_scenario,
        params.get("source_selector") or params.get("face_selector") or params.get("base_face_selector"),
        internal=internal,
        scenario_label=scenario,
    )
    default_start_selector, default_end_selector = _default_thread_boundary_selectors(
        source_scenario,
        source_selector,
        internal=internal,
    )
    start_selector = _normalize_thread_boundary_selector(
        source_scenario,
        params.get("start_selector") or params.get("start_face_selector"),
        default_selector=default_start_selector,
    )
    end_selector = _normalize_thread_boundary_selector(
        source_scenario,
        params.get("end_selector") or params.get("end_face_selector"),
        default_selector=default_end_selector,
    )

    source_output = _resolve_thread_preview_output(source_preview, source_selector, field_name="source")
    start_output = _resolve_thread_preview_output(source_preview, start_selector, field_name="start")
    end_output = _resolve_thread_preview_output(source_preview, end_selector, field_name="end")
    source_origin = _resolve_thread_output_origin(source_output)
    start_origin = _resolve_thread_output_origin(start_output)
    end_origin = _resolve_thread_output_origin(end_output)
    carrier_diameter = _resolve_thread_source_carrier_diameter(source_scenario, source_preview, source_selector)

    derived_length = None
    if start_origin is not None and end_origin is not None:
        derived_length = abs(float(end_origin[0]) - float(start_origin[0]))

    diameter = _optional_positive_float(params, "diameter", "diameter", "nominal_diameter", "d")
    pitch = _optional_positive_float(params, "pitch", "pitch", "p")
    try:
        thread_profile_resolution = resolve_thread_profile_geometry(
            params,
            diameter=float(diameter) if diameter is not None else None,
            pitch=float(pitch) if pitch is not None else None,
        )
    except ValueError as exc:
        raise ValueError(f"{scenario} requires diameter/pitch or a resolvable inch thread designation") from exc
    thread_geometry = dict(thread_profile_resolution["geometry"])
    diameter = float(thread_geometry["major_diameter"])
    pitch = float(thread_geometry["pitch"])
    thread_profile_family = str(thread_profile_resolution.get("profile_family") or thread_geometry.get("profile_family") or "metric_v60")
    thread_series = str(thread_profile_resolution.get("thread_series") or thread_geometry.get("thread_series") or "")
    thread_source_units = str(thread_profile_resolution.get("source_units") or thread_geometry.get("source_units") or "mm")
    thread_profile_resolved_from = str(thread_profile_resolution.get("resolved_from") or "")
    profile_root_shape = str(thread_geometry.get("profile_root_shape") or "round")
    geometry_root_round_radius = None
    geometry_root_round_radius_raw = thread_geometry.get("root_round_radius")
    if geometry_root_round_radius_raw not in (None, ""):
        try:
            parsed_geometry_root_round_radius = float(geometry_root_round_radius_raw)
        except Exception:
            parsed_geometry_root_round_radius = None
        if parsed_geometry_root_round_radius is not None and math.isfinite(parsed_geometry_root_round_radius) and parsed_geometry_root_round_radius > 0.0:
            geometry_root_round_radius = parsed_geometry_root_round_radius
    carrier_shape = str(thread_geometry.get("carrier_shape") or "cylindrical").strip().lower()
    if carrier_shape not in {"cylindrical", "conical"}:
        raise ValueError(f"{scenario} resolved unsupported carrier shape: {carrier_shape}")
    if carrier_shape == "conical":
        expected_source = "internal_conical_step" if internal else "external_conical_step"
        if source_scenario != expected_source:
            raise ValueError(f"{scenario} {thread_profile_family} requires {expected_source} source_scenario")
    elif source_scenario in {"external_conical_step", "internal_conical_step"}:
        raise ValueError(f"{scenario} cylindrical thread profiles require a cylindrical source_scenario")
    length = _optional_positive_float(params, "length", "length", "thread_length", "l")
    if length is None:
        length = derived_length
    if length is None:
        raise ValueError(f"{scenario} requires length or resolvable start/end selectors")
    if derived_length is not None and float(length) > float(derived_length) + 1e-6:
        raise ValueError(f"{scenario} length exceeds the selected source span")
    conical_thread_span = None
    if source_scenario in {"external_conical_step", "internal_conical_step"}:
        conical_thread_span = _resolve_conical_thread_span_diameters(
            source_preview,
            start_selector=start_selector,
            end_selector=end_selector,
            thread_length=float(length),
            source_span_length=derived_length,
        )

    taper_diameter_ratio = float(thread_geometry.get("taper_diameter_ratio") or 0.0)
    taper_radius_ratio = float(thread_geometry.get("taper_radius_ratio") or 0.0)
    taper_half_angle_degrees = float(thread_geometry.get("taper_half_angle_degrees") or 0.0)
    taper_direction = str(thread_geometry.get("taper_direction") or "").strip().lower()
    if carrier_shape == "conical":
        if taper_diameter_ratio <= 0.0 or taper_radius_ratio <= 0.0:
            raise ValueError(f"{scenario} conical thread requires positive taper metadata")
        if not internal:
            _validate_external_conical_thread_orientation(
                scenario=scenario,
                source_preview=source_preview,
                start_selector=start_selector,
                end_selector=end_selector,
                start_origin=start_origin,
                end_origin=end_origin,
            )

    thread_database_path = params.get("thread_database_path") or params.get("catalog_path")
    if thread_database_path:
        thread_database_path = str(Path(str(thread_database_path)))
        if not Path(thread_database_path).exists():
            raise ValueError(f"{scenario} thread_database_path does not exist: {thread_database_path}")

    thread_standard_value = (
        params.get("thread_standard")
        or params.get("standard")
        or params.get("thread_standard_file_name")
        or params.get("standard_table_name")
    )
    standard_entry = None
    if (thread_standard_value is not None or thread_database_path) and (
        thread_database_path or thread_profile_family == "metric_v60"
    ):
        standard_entry = resolve_thread_standard_entry(
            thread_standard_value,
            float(diameter),
            float(pitch),
            database_path=thread_database_path,
        )
    if standard_entry is not None:
        assessment = assess_thread_standard_for_helical_thread_v1(standard_entry)
        if not bool(assessment.get("compatible")):
            standard_label = str(
                standard_entry.get("display_name")
                or standard_entry.get("table_name")
                or thread_standard_value
                or "thread standard"
            )
            reason = str(assessment.get("reason") or "standard is incompatible with helical-thread V1")
            raise ValueError(f"{scenario} standard {standard_label} is incompatible: {reason}")

    designation = str(params.get("designation") or "")
    if not designation and standard_entry is not None:
        designation = str(standard_entry.get("designation") or "")
    if not designation:
        designation = str(thread_profile_resolution.get("designation") or thread_geometry.get("designation") or "")

    thread_reference_diameter = (
        float(thread_geometry["internal_minor_diameter"])
        if internal
        else float(thread_geometry["major_diameter"])
    )
    if conical_thread_span is not None:
        thread_reference_diameter = float(conical_thread_span["thread_start_diameter"])
    thread_reference_radius = float(thread_reference_diameter) / 2.0
    if carrier_shape == "conical":
        taper_delta_diameter = float(length) * taper_diameter_ratio
        default_end_diameter = float(diameter) - taper_delta_diameter
        default_end_thread_reference_diameter = float(thread_reference_diameter) - taper_delta_diameter
        end_diameter = (
            float(conical_thread_span["thread_end_diameter"])
            if conical_thread_span is not None
            else default_end_diameter
        )
        end_thread_reference_diameter = (
            float(conical_thread_span["thread_end_diameter"])
            if conical_thread_span is not None
            else default_end_thread_reference_diameter
        )
        if end_diameter <= 0.0 or end_thread_reference_diameter <= 0.0:
            raise ValueError(f"{scenario} NPT taper makes the end diameter non-positive")
        profile_taper_slope = taper_radius_ratio if internal else -taper_radius_ratio
        carrier_diameter = (
            float(conical_thread_span["thread_start_diameter"])
            if conical_thread_span is not None
            else carrier_diameter
        )
        carrier_taper = {
            "diameter_ratio": taper_diameter_ratio,
            "radius_ratio": taper_radius_ratio,
            "half_angle_degrees": taper_half_angle_degrees,
            "direction": taper_direction or "inward",
            "start_diameter": float(carrier_diameter) if carrier_diameter is not None else float(thread_reference_diameter),
            "end_diameter": float(end_diameter),
            "start_thread_reference_diameter": float(thread_reference_diameter),
            "end_thread_reference_diameter": float(end_thread_reference_diameter),
            "source_start_diameter": (
                float(conical_thread_span["source_start_diameter"])
                if conical_thread_span is not None
                else float(diameter)
            ),
            "source_end_diameter": (
                float(conical_thread_span["source_end_diameter"])
                if conical_thread_span is not None
                else float(default_end_diameter)
            ),
            "thread_start_axis": (
                float(conical_thread_span["thread_start_axis"])
                if conical_thread_span is not None
                else 0.0
            ),
            "thread_end_axis": (
                float(conical_thread_span["thread_end_axis"])
                if conical_thread_span is not None
                else float(length)
            ),
            "profile_taper_slope": float(profile_taper_slope),
        }
    else:
        end_diameter = float(diameter)
        end_thread_reference_diameter = float(thread_reference_diameter)
        profile_taper_slope = 0.0
        carrier_taper = {
            "diameter_ratio": 0.0,
            "radius_ratio": 0.0,
            "half_angle_degrees": 0.0,
            "direction": "",
            "start_diameter": float(diameter),
            "end_diameter": float(end_diameter),
            "start_thread_reference_diameter": float(thread_reference_diameter),
            "end_thread_reference_diameter": float(end_thread_reference_diameter),
            "profile_taper_slope": 0.0,
        }
    source_diameter_validation_mode = _normalize_source_diameter_validation_mode(
        params.get("source_diameter_validation_mode"),
        scenario=scenario,
    )
    source_diameter_tolerance = _resolve_source_diameter_validation_tolerance(params, scenario=scenario)
    source_diameter_validation = _build_source_diameter_validation(
        source_diameter=float(carrier_diameter) if carrier_diameter is not None else None,
        recommended_diameter=thread_reference_diameter,
        tolerance=source_diameter_tolerance,
        mode=source_diameter_validation_mode,
        scenario=scenario,
        internal=internal,
    )

    thread_depth = _optional_positive_float(params, "thread_depth", "thread_depth", "depth", "profile_depth")
    thread_depth_mode = "explicit" if thread_depth is not None else "auto"
    if thread_depth is None:
        thread_depth = (
            float(thread_geometry["internal_thread_depth"])
            if internal
            else float(thread_geometry["external_thread_depth"])
        )

    profile_angle_degrees = _optional_positive_float(
        params,
        "profile_angle_degrees",
        "profile_angle_degrees",
        "thread_angle_degrees",
        "angle_degrees",
        "profile_angle",
    )
    if profile_angle_degrees is None:
        profile_angle_degrees = float(thread_geometry.get("profile_angle_degrees") or 60.0)
    if float(profile_angle_degrees) >= 179.0:
        raise ValueError(f"{scenario} profile_angle_degrees must be less than 179")

    clearance_raw = params.get("clearance", params.get("radial_clearance", 0.0))
    try:
        clearance = float(clearance_raw if clearance_raw not in (None, "") else 0.0)
    except Exception as exc:
        raise ValueError(f"{scenario} clearance must be a number") from exc
    if not math.isfinite(clearance):
        raise ValueError(f"{scenario} clearance must be finite")

    explicit_profile_entry_offset = _optional_positive_float(
        params,
        "profile_entry_offset",
        "profile_entry_offset",
        "entry_offset",
        "sketch_offset",
        "section_offset",
    )
    profile_entry_offset = explicit_profile_entry_offset
    if profile_entry_offset is None:
        profile_entry_offset = float(pitch) * 1.05
    profile_entry_offset_mode = "explicit" if explicit_profile_entry_offset is not None else "auto"
    spiral_length = float(length) + float(profile_entry_offset)
    explicit_profile_surface_offset = _optional_positive_float(
        params,
        "profile_surface_offset",
        "profile_surface_offset",
        "profile_radial_offset",
        "radial_entry_offset",
        "sketch_radial_offset",
    )

    direction = _normalize_thread_direction(params)
    display_index = _resolve_thread_display_index(params)
    module_display_name = _build_thread_module_display_name(
        designation=designation,
        diameter=float(diameter),
        pitch=float(pitch),
        internal=internal,
        direction=direction,
    )
    module_variable_token = _build_thread_module_variable_token(
        designation=designation,
        diameter=float(diameter),
        pitch=float(pitch),
        internal=internal,
        direction=direction,
    )
    feature_display_name = _build_thread_object_display_name("Thread", module_display_name, display_index)
    operation_label = feature_display_name
    profile_display_name = _build_thread_object_display_name("Sketch", module_display_name, display_index)
    path_display_name = _build_thread_object_display_name("Spiral", module_display_name, display_index)
    axis_display_name = _build_thread_object_display_name("Axis", module_display_name, display_index)
    start_center_name = _build_thread_object_display_name("Start center", module_display_name, display_index)
    profile_origin_name = _build_thread_object_display_name("Profile origin", module_display_name, display_index)
    public_diameter_variable_name = _build_thread_public_variable_name("Diameter", module_variable_token, display_index)
    public_pitch_variable_name = _build_thread_public_variable_name("Pitch", module_variable_token, display_index)
    public_length_variable_name = _build_thread_public_variable_name("Length", module_variable_token, display_index)
    if profile_entry_offset_mode == "auto":
        profile_entry_offset_expression = _build_thread_linear_expression(
            public_pitch_variable_name,
            1.05,
        )
    else:
        profile_entry_offset_expression = _format_thread_expression_number(float(profile_entry_offset))
    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    material_payload = resolve_material_payload(params.get("material"), params.get("density"))
    sketch = normalize_sketch_options(params.get("sketch"))
    if carrier_shape == "conical" and str(profile_root_shape or "round") == "flat":
        sketch["parameterization_order"] = "anchored_dimensions_then_constraints"
        sketch["readback_geometry"] = True
    major_radius = float(thread_reference_radius) if not internal else float(thread_geometry["major_radius"])
    radial_cut_depth = float(thread_depth) + float(clearance)
    half_angle_radians = math.radians(float(profile_angle_degrees) / 2.0)
    sin_half_angle = math.sin(half_angle_radians)
    cos_half_angle = math.cos(half_angle_radians)
    tan_half_angle = math.tan(half_angle_radians)
    if abs(tan_half_angle) < 1e-9:
        raise ValueError(f"{scenario} profile_angle_degrees produces invalid flank geometry")
    fundamental_triangle_height = float(pitch) / (2.0 * tan_half_angle)
    if not math.isfinite(fundamental_triangle_height) or float(fundamental_triangle_height) <= 0.0:
        raise ValueError(f"{scenario} profile_angle_degrees produces invalid fundamental triangle height")
    carrier_radius = float(carrier_diameter) / 2.0 if carrier_diameter is not None else float(thread_reference_radius)
    profile_surface_offset = explicit_profile_surface_offset
    if profile_surface_offset is None:
        profile_surface_offset = max(float(clearance), float(pitch) * 0.05)
    profile_surface_offset_mode = "explicit" if explicit_profile_surface_offset is not None else "auto"
    profile_surface_offset_metadata = _build_profile_surface_offset_metadata(
        float(profile_surface_offset),
        mode=profile_surface_offset_mode,
    )
    profile_taper_compensation_magnitude = (
        abs(float(profile_taper_slope)) * float(profile_entry_offset)
        if carrier_shape == "conical"
        else 0.0
    )
    profile_taper_compensation_radius = (
        -profile_taper_compensation_magnitude
        if internal
        else profile_taper_compensation_magnitude
    )
    profile_sketch_origin_shift = (
        float(thread_reference_radius)
        if not internal
        else -float(thread_reference_radius)
    )
    if not internal:
        explicit_root_radius_level = _optional_positive_float(
            params,
            "root_radius_level",
            "root_radius_level",
            "root_level_radius",
            "root_minor_radius",
            "minor_radius",
            "r3",
        )
        root_radius_level_mode = "explicit" if explicit_root_radius_level is not None else "auto"
        root_radius_level = explicit_root_radius_level
        if root_radius_level is None:
            root_radius_level = float(major_radius) - float(radial_cut_depth)
        radial_cut_depth = float(major_radius) - float(root_radius_level)
        if float(radial_cut_depth) <= 0.0:
            raise ValueError(f"{scenario} root_radius_level must be smaller than the carrier radius")
        thread_depth = float(radial_cut_depth) - float(clearance)
        if float(thread_depth) <= 0.0:
            raise ValueError(f"{scenario} root_radius_level and clearance produce non-positive thread depth")
        base_drop = float(fundamental_triangle_height) / 8.0
        apex_height = float(fundamental_triangle_height) - float(base_drop)
        outer_half_width = float(pitch) / 2.0 - float(base_drop) * tan_half_angle
        if float(outer_half_width) <= 0.0 or float(outer_half_width) >= float(pitch) * 0.5:
            raise ValueError(f"{scenario} derived outer half width is invalid")
        if profile_root_shape == "flat":
            explicit_root_width = _optional_positive_float(
                params,
                "root_width",
                "root_width",
                "root_chord_width",
                "bottom_width",
                "root_flat_width",
                "s",
            )
            root_width_mode = "explicit" if explicit_root_width is not None else "auto"
            root_width = explicit_root_width
            if root_width is None:
                root_width = float(thread_geometry.get("root_flat_width") or (float(pitch) / 16.0))
            root_half_width = float(root_width) / 2.0
            if float(root_half_width) <= 0.0:
                raise ValueError(f"{scenario} root_width must be positive")
            if root_width_mode == "auto":
                outer_half_width = float(pitch) / 2.0 - float(root_half_width)
                base_drop = (float(pitch) / 2.0 - float(outer_half_width)) / tan_half_angle
                apex_height = float(fundamental_triangle_height) - float(base_drop)
            else:
                outer_half_width = float(root_half_width) + float(radial_cut_depth) * tan_half_angle
                base_drop = (float(pitch) / 2.0 - float(outer_half_width)) / tan_half_angle
                apex_height = float(fundamental_triangle_height) - float(base_drop)
            if float(outer_half_width) <= 0.0 or float(outer_half_width) >= float(pitch) * 0.5:
                raise ValueError(f"{scenario} derived flat-root outer half width is invalid")
            if float(root_half_width) >= float(outer_half_width):
                raise ValueError(f"{scenario} root_width must be smaller than the profile opening")
            root_radius = 0.0
            tangent_depth = float(radial_cut_depth)
            arc_center_depth = 0.0
            normalized = {
                "name": name,
                "designation": designation,
                "material": material_payload["material"],
                "density": material_payload["density"],
                "material_catalog_matched": material_payload["catalog_matched"],
                "comment": str(params.get("comment") or ""),
                "parameter_prefix": parameter_prefix,
                "operation_label": operation_label,
                "module_display_name": module_display_name,
                "display_index": int(display_index),
                "feature_display_name": feature_display_name,
                "profile_display_name": profile_display_name,
                "path_display_name": path_display_name,
                "axis_display_name": axis_display_name,
                "start_center_name": start_center_name,
                "profile_origin_name": profile_origin_name,
                "public_diameter_variable_name": public_diameter_variable_name,
                "public_pitch_variable_name": public_pitch_variable_name,
                "public_length_variable_name": public_length_variable_name,
                "sketch": sketch,
                "diameter": float(diameter),
                "pitch": float(pitch),
                "length": float(length),
                "spiral_length": float(spiral_length),
                "thread_geometry": dict(thread_geometry),
                "metric_thread_geometry": dict(thread_geometry),
                "thread_profile_family": thread_profile_family,
                "thread_series": thread_series,
                "thread_source_units": thread_source_units,
                "thread_profile_resolved_from": thread_profile_resolved_from,
                "profile_root_shape": profile_root_shape,
                "carrier_shape": carrier_shape,
                "carrier_taper": dict(carrier_taper),
                "end_diameter": float(end_diameter),
                "end_thread_reference_diameter": float(end_thread_reference_diameter),
                "profile_taper_slope": float(profile_taper_slope),
                "thread_reference_diameter": float(thread_reference_diameter),
                "thread_reference_radius": float(thread_reference_radius),
                "recommended_source_diameter": float(thread_reference_diameter),
                "source_diameter_validation": dict(source_diameter_validation),
                "source_diameter_validation_mode": source_diameter_validation_mode,
                "source_diameter_tolerance": float(source_diameter_tolerance),
                "thread_depth": float(thread_depth),
                "thread_depth_mode": thread_depth_mode,
                "clearance": float(clearance),
                "major_radius": float(major_radius),
                "carrier_radius": float(carrier_radius),
                "root_radius_level": float(root_radius_level),
                "root_radius_level_mode": root_radius_level_mode,
                "root_diameter": float(root_radius_level) * 2.0,
                "radial_cut_depth": float(radial_cut_depth),
                "fundamental_triangle_height": float(fundamental_triangle_height),
                "profile_base_drop": float(base_drop),
                "profile_apex_height": float(apex_height),
                "root_width": float(root_width),
                "root_width_mode": root_width_mode,
                "profile_root_half_width": float(root_half_width),
                "root_radius": float(root_radius),
                "profile_entry_offset": float(profile_entry_offset),
                "profile_entry_offset_expression": profile_entry_offset_expression,
                "profile_entry_offset_mode": profile_entry_offset_mode,
                "profile_taper_compensation_radius": float(profile_taper_compensation_radius),
                "profile_surface_offset": float(profile_surface_offset),
                "profile_surface_offset_mode": profile_surface_offset_mode,
                "profile_surface_offset_effective": float(profile_surface_offset_metadata["effective"]),
                "profile_surface_offset_applied": bool(profile_surface_offset_metadata["applied"]),
                "profile_surface_offset_status": str(profile_surface_offset_metadata["status"]),
                "profile_surface_offset_note": str(profile_surface_offset_metadata["note"]),
                "profile_sketch_origin_shift": float(profile_sketch_origin_shift),
                "profile_outer_half_width": float(outer_half_width),
                "profile_tangent_half_width": float(root_half_width),
                "profile_tangent_depth": float(tangent_depth),
                "profile_arc_center_depth": float(arc_center_depth),
                "profile_angle_degrees": float(profile_angle_degrees),
                "direction": direction,
                "thread_direction": direction,
                "left_thread": direction == "left",
                "internal": internal,
                "source_scenario": source_scenario,
                "source_params": dict(source_params),
                "source_preview": source_preview,
                "source_selector": source_selector,
                "start_selector": start_selector,
                "end_selector": end_selector,
                "source_origin": source_origin,
                "start_origin": start_origin,
                "end_origin": end_origin,
                "carrier_diameter": float(carrier_diameter) if carrier_diameter is not None else None,
                "thread_database_path": (standard_entry or {}).get("database_path") if standard_entry else None,
                "thread_standard_table_name": str((standard_entry or {}).get("table_name") or "") if standard_entry else "",
                "thread_standard_display_name": str((standard_entry or {}).get("display_name") or "") if standard_entry else "",
                "thread_designation": str((standard_entry or {}).get("designation") or designation),
                "thread_standard_entry": dict((standard_entry or {}).get("entry") or {}) if standard_entry else {},
                "internal_diameter_coefficient": float((standard_entry or {}).get("internal_diameter_coefficient") or 0.0)
                if standard_entry
                else 0.0,
                "conical_thread_angle": float((standard_entry or {}).get("conical_thread_angle") or 0.0) if standard_entry else 0.0,
                "output_path": output_path,
                "visible": bool(params.get("visible", False)),
                "auxiliary_geometry_hidden": bool(params.get("auxiliary_geometry_hidden", True)),
                "close_after_save": bool(params.get("close_after_save", True)),
            }
            profile_variables, profile_variable_names = _build_helical_thread_variable_plan(normalized)
            profile_geometry = _build_helical_thread_profile_geometry(normalized)
            profile_dimension_expressions = _build_helical_thread_dimension_expression_plan(normalized)
            profile_constraints = _build_helical_thread_constraint_plan(
                False,
                root_shape=profile_root_shape,
                carrier_shape=carrier_shape,
            )
            profile_dimensions = _layout_external_helical_thread_dimensions(
                _build_helical_thread_dimension_plan(
                    profile_variable_names,
                    profile_dimension_expressions,
                    internal=False,
                ),
                normalized,
            )
            profile_verification = dict(profile_geometry.get("verification") or {})
            profile_contract_verification = verify_v60_flat_thread_profile_contract(
                constraints=profile_constraints,
                dimensions=profile_dimensions,
                dimension_expressions=profile_dimension_expressions,
                normalized=normalized,
            )
            profile_verification["constraint_contract"] = profile_contract_verification
            profile_verification["ok"] = bool(profile_verification.get("ok")) and bool(profile_contract_verification.get("ok"))
            normalized.update(
                {
                    "profile_variables": profile_variables,
                    "profile_variable_names": profile_variable_names,
                    "profile_dimension_expressions": profile_dimension_expressions,
                    "public_profile_variables": [
                        public_diameter_variable_name,
                        public_pitch_variable_name,
                        public_length_variable_name,
                    ],
                    "profile_constraints": profile_constraints,
                    "profile_dimensions": profile_dimensions,
                    "profile_points": profile_geometry["profile_points"],
                    "profile_lines": profile_geometry["profile_lines"],
                    "profile_arcs": profile_geometry["profile_arcs"],
                    "profile_construction_lines": profile_geometry["construction_lines"],
                    "profile_axis_start": profile_geometry["axis_start"],
                    "profile_axis_end": profile_geometry["axis_end"],
                    "profile_named_points": dict(profile_geometry.get("named_points") or {}),
                    "profile_verification": profile_verification,
                }
            )
            _apply_helical_thread_source_variable_bindings(normalized)
            normalized["operation_variable_bindings"] = _build_helical_thread_spiral_variable_bindings(normalized)
            normalized["crest_round_pass"] = _build_external_crest_round_pass(normalized, params)
            return normalized
        explicit_root_round_radius = _optional_positive_float(
            params,
            "root_round_radius",
            "root_round_radius",
            "root_arc_radius",
            "root_fillet_radius",
        )
        root_round_radius_mode = "explicit" if explicit_root_round_radius is not None else "auto"
        desired_root_radius = explicit_root_round_radius
        if desired_root_radius is None and geometry_root_round_radius is not None:
            desired_root_radius = geometry_root_round_radius
            root_round_radius_mode = "from_geometry"
        if desired_root_radius is None:
            root_radius = (float(outer_half_width) * cos_half_angle - float(radial_cut_depth) * sin_half_angle) / (1.0 - sin_half_angle)
            if not math.isfinite(root_radius) or float(root_radius) <= 0.0 or float(root_radius) >= float(radial_cut_depth):
                raise ValueError(f"{scenario} derived root radius is invalid; adjust r3 or profile_angle_degrees")
            tangent_depth = float(radial_cut_depth) - float(root_radius) * (1.0 - sin_half_angle)
            if float(tangent_depth) <= 0.0 or float(tangent_depth) >= float(radial_cut_depth):
                raise ValueError(f"{scenario} derived tangent depth is invalid; adjust r3 or profile_angle_degrees")
            tangent_half_width = float(outer_half_width) - float(tangent_depth) * tan_half_angle
            if float(tangent_half_width) <= 0.0 or float(tangent_half_width) >= float(outer_half_width):
                raise ValueError(f"{scenario} derived tangent half width is invalid; adjust r3 or profile_angle_degrees")
        else:
            root_radius = float(desired_root_radius)
            if not math.isfinite(root_radius) or float(root_radius) <= 0.0 or float(root_radius) >= float(radial_cut_depth):
                raise ValueError(f"{scenario} root_round_radius must stay between 0 and radial_cut_depth")
            tangent_depth = float(radial_cut_depth) - float(root_radius) * (1.0 - sin_half_angle)
            if float(tangent_depth) <= 0.0 or float(tangent_depth) >= float(radial_cut_depth):
                raise ValueError(f"{scenario} root_round_radius produces invalid tangent depth")
            tangent_half_width = float(root_radius) * cos_half_angle
            if float(tangent_half_width) <= 0.0:
                raise ValueError(f"{scenario} root_round_radius produces invalid tangent half width")
            outer_half_width = float(tangent_half_width) + float(tangent_depth) * tan_half_angle
            if float(outer_half_width) <= 0.0 or float(outer_half_width) >= float(pitch) * 0.5:
                raise ValueError(f"{scenario} root_round_radius produces crest width collision with adjacent turns")
            base_drop = (float(pitch) / 2.0 - float(outer_half_width)) / tan_half_angle
            if float(base_drop) <= 0.0 or float(base_drop) >= float(fundamental_triangle_height):
                raise ValueError(f"{scenario} root_round_radius produces invalid crest truncation")
            apex_height = float(fundamental_triangle_height) - float(base_drop)
        arc_center_depth = float(radial_cut_depth) - float(root_radius)
        normalized = {
            "name": name,
            "designation": designation,
            "material": material_payload["material"],
            "density": material_payload["density"],
            "material_catalog_matched": material_payload["catalog_matched"],
            "comment": str(params.get("comment") or ""),
            "parameter_prefix": parameter_prefix,
            "operation_label": operation_label,
            "module_display_name": module_display_name,
            "display_index": int(display_index),
            "feature_display_name": feature_display_name,
            "profile_display_name": profile_display_name,
            "path_display_name": path_display_name,
            "axis_display_name": axis_display_name,
            "start_center_name": start_center_name,
            "profile_origin_name": profile_origin_name,
            "public_diameter_variable_name": public_diameter_variable_name,
            "public_pitch_variable_name": public_pitch_variable_name,
            "public_length_variable_name": public_length_variable_name,
            "sketch": sketch,
            "diameter": float(diameter),
            "pitch": float(pitch),
            "length": float(length),
            "spiral_length": float(spiral_length),
            "thread_geometry": dict(thread_geometry),
            "metric_thread_geometry": dict(thread_geometry),
            "thread_profile_family": thread_profile_family,
            "thread_series": thread_series,
            "thread_source_units": thread_source_units,
            "thread_profile_resolved_from": thread_profile_resolved_from,
            "profile_root_shape": profile_root_shape,
            "carrier_shape": carrier_shape,
            "carrier_taper": dict(carrier_taper),
            "end_diameter": float(end_diameter),
            "end_thread_reference_diameter": float(end_thread_reference_diameter),
            "profile_taper_slope": float(profile_taper_slope),
            "thread_reference_diameter": float(thread_reference_diameter),
            "thread_reference_radius": float(thread_reference_radius),
            "recommended_source_diameter": float(thread_reference_diameter),
            "source_diameter_validation": dict(source_diameter_validation),
            "source_diameter_validation_mode": source_diameter_validation_mode,
            "source_diameter_tolerance": float(source_diameter_tolerance),
            "thread_depth": float(thread_depth),
            "thread_depth_mode": thread_depth_mode,
            "clearance": float(clearance),
            "major_radius": float(major_radius),
            "carrier_radius": float(carrier_radius),
            "root_radius_level": float(root_radius_level),
            "root_radius_level_mode": root_radius_level_mode,
            "root_diameter": float(root_radius_level) * 2.0,
            "radial_cut_depth": float(radial_cut_depth),
            "fundamental_triangle_height": float(fundamental_triangle_height),
            "profile_base_drop": float(base_drop),
            "profile_apex_height": float(apex_height),
            "root_radius": float(root_radius),
            "root_round_radius_mode": root_round_radius_mode,
            "profile_entry_offset": float(profile_entry_offset),
            "profile_entry_offset_expression": profile_entry_offset_expression,
            "profile_entry_offset_mode": profile_entry_offset_mode,
            "profile_taper_compensation_radius": float(profile_taper_compensation_radius),
            "profile_surface_offset": float(profile_surface_offset),
            "profile_surface_offset_mode": profile_surface_offset_mode,
            "profile_surface_offset_effective": float(profile_surface_offset_metadata["effective"]),
            "profile_surface_offset_applied": bool(profile_surface_offset_metadata["applied"]),
            "profile_surface_offset_status": str(profile_surface_offset_metadata["status"]),
            "profile_surface_offset_note": str(profile_surface_offset_metadata["note"]),
            "profile_sketch_origin_shift": float(profile_sketch_origin_shift),
            "profile_outer_half_width": float(outer_half_width),
            "profile_tangent_half_width": float(tangent_half_width),
            "profile_tangent_depth": float(tangent_depth),
            "profile_arc_center_depth": float(arc_center_depth),
            "profile_angle_degrees": float(profile_angle_degrees),
            "direction": direction,
            "thread_direction": direction,
            "left_thread": direction == "left",
            "internal": internal,
            "source_scenario": source_scenario,
            "source_params": dict(source_params),
            "source_preview": source_preview,
            "source_selector": source_selector,
            "start_selector": start_selector,
            "end_selector": end_selector,
            "source_origin": source_origin,
            "start_origin": start_origin,
            "end_origin": end_origin,
            "carrier_diameter": float(carrier_diameter) if carrier_diameter is not None else None,
            "thread_database_path": (standard_entry or {}).get("database_path") if standard_entry else None,
            "thread_standard_table_name": str((standard_entry or {}).get("table_name") or "") if standard_entry else "",
            "thread_standard_display_name": str((standard_entry or {}).get("display_name") or "") if standard_entry else "",
            "thread_designation": str((standard_entry or {}).get("designation") or designation),
            "thread_standard_entry": dict((standard_entry or {}).get("entry") or {}) if standard_entry else {},
            "internal_diameter_coefficient": float((standard_entry or {}).get("internal_diameter_coefficient") or 0.0)
            if standard_entry
            else 0.0,
            "conical_thread_angle": float((standard_entry or {}).get("conical_thread_angle") or 0.0) if standard_entry else 0.0,
            "output_path": output_path,
            "visible": bool(params.get("visible", False)),
            "auxiliary_geometry_hidden": bool(params.get("auxiliary_geometry_hidden", True)),
            "close_after_save": bool(params.get("close_after_save", True)),
        }
        profile_variables, profile_variable_names = _build_helical_thread_variable_plan(normalized)
        profile_geometry = _build_helical_thread_profile_geometry(normalized)
        profile_dimension_expressions = _build_helical_thread_dimension_expression_plan(normalized)
        normalized.update(
            {
                "profile_variables": profile_variables,
                "profile_variable_names": profile_variable_names,
                "profile_dimension_expressions": profile_dimension_expressions,
                "public_profile_variables": [
                    public_diameter_variable_name,
                    public_pitch_variable_name,
                    public_length_variable_name,
                ],
                "profile_constraints": _build_helical_thread_constraint_plan(
                    False,
                    carrier_shape=carrier_shape,
                ),
                "profile_dimensions": _layout_external_helical_thread_dimensions(
                    _build_helical_thread_dimension_plan(
                        profile_variable_names,
                        profile_dimension_expressions,
                        internal=False,
                    ),
                    normalized,
                ),
                "profile_points": profile_geometry["profile_points"],
                "profile_lines": profile_geometry["profile_lines"],
                "profile_arcs": profile_geometry["profile_arcs"],
                "profile_construction_lines": profile_geometry["construction_lines"],
                "profile_axis_start": profile_geometry["axis_start"],
                "profile_axis_end": profile_geometry["axis_end"],
                "profile_named_points": dict(profile_geometry.get("named_points") or {}),
                "profile_verification": dict(profile_geometry.get("verification") or {}),
            }
        )
        _apply_helical_thread_source_variable_bindings(normalized)
        normalized["operation_variable_bindings"] = _build_helical_thread_spiral_variable_bindings(normalized)
        normalized["crest_round_pass"] = _build_external_crest_round_pass(normalized, params)
        return normalized

    explicit_root_round_radius = _optional_positive_float(
        params,
        "root_round_radius",
        "root_round_radius",
        "root_arc_radius",
        "root_fillet_radius",
    )
    root_round_radius_mode = "explicit" if explicit_root_round_radius is not None else "auto"
    desired_root_radius = explicit_root_round_radius
    if desired_root_radius is None and geometry_root_round_radius is not None:
        desired_root_radius = geometry_root_round_radius
        root_round_radius_mode = "from_geometry"
    geometry_root_half_width = None
    if desired_root_radius is not None:
        geometry_root_half_width = float(desired_root_radius) * cos_half_angle
    elif geometry_root_round_radius is not None:
        geometry_root_half_width = float(geometry_root_round_radius) * cos_half_angle

    explicit_root_width = _optional_positive_float(
        params,
        "root_width",
        "root_width",
        "root_chord_width",
        "bottom_width",
        "root_flat_width",
        "s",
    )
    root_width = explicit_root_width
    if root_width is None:
        if profile_root_shape == "flat":
            root_width = float(thread_geometry.get("root_flat_width") or 0.0)
        elif geometry_root_half_width is not None and geometry_root_half_width > 0.0:
            root_width = 2.0 * float(geometry_root_half_width)
    if root_width is None or float(root_width) <= 0.0:
        root_width = float(pitch) / 8.0
    if explicit_root_width is not None:
        root_width_mode = "explicit"
    elif profile_root_shape != "flat" and geometry_root_half_width is not None and geometry_root_half_width > 0.0:
        root_width_mode = "from_geometry"
    else:
        root_width_mode = "auto"
    root_half_width = float(root_width) / 2.0
    if float(radial_cut_depth) <= 0.0 or float(radial_cut_depth) >= float(fundamental_triangle_height):
        raise ValueError(f"{scenario} cut depth must stay between 0 and the fundamental triangle height")
    crest_drop = float(fundamental_triangle_height) - float(radial_cut_depth)
    if float(crest_drop) <= 0.0:
        raise ValueError(f"{scenario} derived crest drop is invalid; reduce depth/clearance or increase pitch")
    outer_half_width = (
        float(root_half_width) + float(radial_cut_depth) * tan_half_angle
        if profile_root_shape == "flat"
        else float(radial_cut_depth) * tan_half_angle
    )
    if profile_root_shape == "flat":
        if float(outer_half_width) <= 0.0 or float(outer_half_width) >= float(pitch) * 0.5:
            raise ValueError(f"{scenario} derived crest width collides with adjacent turns; reduce depth/clearance or increase pitch")
        if float(root_half_width) <= 0.0 or float(root_half_width) >= float(outer_half_width):
            raise ValueError(f"{scenario} root_width must be smaller than the internal crest span")
        tangent_depth = float(radial_cut_depth)
        root_radius = 0.0
        arc_center_depth = 0.0
    elif desired_root_radius is not None:
        root_radius = float(desired_root_radius)
        if not math.isfinite(root_radius) or float(root_radius) <= 0.0 or float(root_radius) >= float(radial_cut_depth):
            raise ValueError(f"{scenario} root_round_radius must stay between 0 and radial_cut_depth")
        tangent_depth = float(radial_cut_depth) - float(root_radius) * (1.0 - sin_half_angle)
        if float(tangent_depth) <= 0.0 or float(tangent_depth) >= float(radial_cut_depth):
            raise ValueError(f"{scenario} root_round_radius produces invalid tangent depth")
        root_half_width = float(root_radius) * cos_half_angle
        if float(root_half_width) <= 0.0:
            raise ValueError(f"{scenario} root_round_radius produces invalid tangent half width")
        root_width = 2.0 * float(root_half_width)
        if root_round_radius_mode != "explicit":
            root_width_mode = "from_geometry"
        outer_half_width = float(root_half_width) + float(tangent_depth) * tan_half_angle
        if float(outer_half_width) <= 0.0 or float(outer_half_width) >= float(pitch) * 0.5:
            raise ValueError(f"{scenario} root_round_radius produces crest width collision with adjacent turns")
        arc_center_depth = float(radial_cut_depth) - float(root_radius)
    else:
        if float(outer_half_width) <= 0.0 or float(outer_half_width) >= float(pitch) * 0.5:
            raise ValueError(f"{scenario} derived crest width collides with adjacent turns; reduce depth/clearance or increase pitch")
        if float(root_half_width) <= 0.0 or float(root_half_width) >= float(outer_half_width):
            raise ValueError(f"{scenario} root_width must be smaller than the internal crest span")
        tangent_depth = float(radial_cut_depth) - float(root_half_width) / tan_half_angle
        if float(tangent_depth) <= 0.0 or float(tangent_depth) >= float(radial_cut_depth):
            raise ValueError(f"{scenario} derived tangent depth is invalid; adjust root_width or profile_angle_degrees")
        root_radius = float(root_half_width) / cos_half_angle
        if not math.isfinite(root_radius) or float(root_radius) <= 0.0 or float(root_radius) >= float(radial_cut_depth):
            raise ValueError(f"{scenario} derived root radius is invalid; adjust root_width or profile_angle_degrees")
        arc_center_depth = float(radial_cut_depth) - float(root_half_width) * tan_half_angle
    normalized = {
        "name": name,
        "designation": designation,
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "parameter_prefix": parameter_prefix,
        "operation_label": operation_label,
        "module_display_name": module_display_name,
        "display_index": int(display_index),
        "feature_display_name": feature_display_name,
        "profile_display_name": profile_display_name,
        "path_display_name": path_display_name,
        "axis_display_name": axis_display_name,
        "start_center_name": start_center_name,
        "profile_origin_name": profile_origin_name,
        "public_diameter_variable_name": public_diameter_variable_name,
        "public_pitch_variable_name": public_pitch_variable_name,
        "public_length_variable_name": public_length_variable_name,
        "sketch": sketch,
        "diameter": float(diameter),
        "pitch": float(pitch),
        "length": float(length),
        "spiral_length": float(spiral_length),
        "thread_geometry": dict(thread_geometry),
        "metric_thread_geometry": dict(thread_geometry),
        "thread_profile_family": thread_profile_family,
        "thread_series": thread_series,
        "thread_source_units": thread_source_units,
        "thread_profile_resolved_from": thread_profile_resolved_from,
        "profile_root_shape": profile_root_shape,
        "carrier_shape": carrier_shape,
        "carrier_taper": dict(carrier_taper),
        "end_diameter": float(end_diameter),
        "end_thread_reference_diameter": float(end_thread_reference_diameter),
        "profile_taper_slope": float(profile_taper_slope),
        "thread_reference_diameter": float(thread_reference_diameter),
        "thread_reference_radius": float(thread_reference_radius),
        "recommended_source_diameter": float(thread_reference_diameter),
        "source_diameter_validation": dict(source_diameter_validation),
        "source_diameter_validation_mode": source_diameter_validation_mode,
        "source_diameter_tolerance": float(source_diameter_tolerance),
        "thread_depth": float(thread_depth),
        "thread_depth_mode": thread_depth_mode,
        "clearance": float(clearance),
        "carrier_radius": float(carrier_radius),
        "radial_cut_depth": float(radial_cut_depth),
        "fundamental_triangle_height": float(fundamental_triangle_height),
        "profile_crest_drop": float(crest_drop),
        "root_width": float(root_width),
        "root_width_mode": root_width_mode,
        "profile_root_half_width": float(root_half_width),
        "root_radius": float(root_radius),
        "root_round_radius_mode": root_round_radius_mode,
        "profile_entry_offset": float(profile_entry_offset),
        "profile_entry_offset_expression": profile_entry_offset_expression,
        "profile_entry_offset_mode": profile_entry_offset_mode,
        "profile_taper_compensation_radius": float(profile_taper_compensation_radius),
        "profile_surface_offset": float(profile_surface_offset),
        "profile_surface_offset_mode": profile_surface_offset_mode,
        "profile_surface_offset_effective": float(profile_surface_offset_metadata["effective"]),
        "profile_surface_offset_applied": bool(profile_surface_offset_metadata["applied"]),
        "profile_surface_offset_status": str(profile_surface_offset_metadata["status"]),
        "profile_surface_offset_note": str(profile_surface_offset_metadata["note"]),
        "profile_sketch_origin_shift": float(profile_sketch_origin_shift),
        "profile_outer_half_width": float(outer_half_width),
        "profile_tangent_half_width": float(root_half_width),
        "profile_tangent_depth": float(tangent_depth),
        "profile_arc_center_depth": float(arc_center_depth),
        "profile_angle_degrees": float(profile_angle_degrees),
        "direction": direction,
        "thread_direction": direction,
        "left_thread": direction == "left",
        "internal": internal,
        "source_scenario": source_scenario,
        "source_params": dict(source_params),
        "source_preview": source_preview,
        "source_selector": source_selector,
        "start_selector": start_selector,
        "end_selector": end_selector,
        "source_origin": source_origin,
        "start_origin": start_origin,
        "end_origin": end_origin,
        "carrier_diameter": float(carrier_diameter) if carrier_diameter is not None else None,
        "thread_database_path": (standard_entry or {}).get("database_path") if standard_entry else None,
        "thread_standard_table_name": str((standard_entry or {}).get("table_name") or "") if standard_entry else "",
        "thread_standard_display_name": str((standard_entry or {}).get("display_name") or "") if standard_entry else "",
        "thread_designation": str((standard_entry or {}).get("designation") or designation),
        "thread_standard_entry": dict((standard_entry or {}).get("entry") or {}) if standard_entry else {},
        "internal_diameter_coefficient": float((standard_entry or {}).get("internal_diameter_coefficient") or 0.0)
        if standard_entry
        else 0.0,
        "conical_thread_angle": float((standard_entry or {}).get("conical_thread_angle") or 0.0) if standard_entry else 0.0,
        "output_path": output_path,
        "visible": bool(params.get("visible", False)),
        "auxiliary_geometry_hidden": bool(params.get("auxiliary_geometry_hidden", True)),
        "close_after_save": bool(params.get("close_after_save", True)),
    }
    profile_variables, profile_variable_names = _build_helical_thread_variable_plan(normalized)
    profile_geometry = _build_helical_thread_profile_geometry(normalized)
    profile_dimension_expressions = _build_helical_thread_dimension_expression_plan(normalized)
    profile_constraints = _build_helical_thread_constraint_plan(
        True,
        root_shape=profile_root_shape,
        carrier_shape=carrier_shape,
    )
    profile_dimensions = _layout_internal_helical_thread_dimensions(
        _build_helical_thread_dimension_plan(
            profile_variable_names,
            profile_dimension_expressions,
            internal=True,
        ),
        normalized,
    )
    profile_verification = dict(profile_geometry.get("verification") or {})
    if profile_root_shape == "flat":
        profile_contract_verification = verify_v60_flat_thread_profile_contract(
            constraints=profile_constraints,
            dimensions=profile_dimensions,
            dimension_expressions=profile_dimension_expressions,
            normalized=normalized,
        )
        profile_verification["constraint_contract"] = profile_contract_verification
        profile_verification["ok"] = bool(profile_verification.get("ok")) and bool(profile_contract_verification.get("ok"))
    normalized.update(
        {
            "profile_variables": profile_variables,
            "profile_variable_names": profile_variable_names,
            "profile_dimension_expressions": profile_dimension_expressions,
            "public_profile_variables": [
                public_diameter_variable_name,
                public_pitch_variable_name,
                public_length_variable_name,
            ],
            "profile_constraints": profile_constraints,
            "profile_dimensions": profile_dimensions,
            "profile_points": profile_geometry["profile_points"],
            "profile_lines": profile_geometry["profile_lines"],
            "profile_arcs": profile_geometry["profile_arcs"],
            "profile_construction_lines": profile_geometry["construction_lines"],
            "profile_axis_start": profile_geometry["axis_start"],
            "profile_axis_end": profile_geometry["axis_end"],
            "profile_named_points": dict(profile_geometry.get("named_points") or {}),
            "profile_verification": profile_verification,
        }
    )
    _apply_helical_thread_source_variable_bindings(normalized)
    normalized["operation_variable_bindings"] = _build_helical_thread_spiral_variable_bindings(normalized)
    normalized["crest_round_pass"] = _build_external_crest_round_pass(normalized, params)
    return normalized


def _normalize_threaded_step_params(
    params: dict[str, Any],
    *,
    scenario: str,
    internal: bool,
) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    source_scenario_raw = params.get("source_scenario") or params.get("base_scenario")
    if source_scenario_raw is None:
        raise ValueError(f"{scenario} requires source_scenario")
    source_scenario = _normalize_scenario(str(source_scenario_raw))
    allowed_source_scenarios = (
        ("internal_cylindrical_step", "internal_conical_step")
        if internal
        else ("stepped_shaft", "external_conical_step")
    )
    if source_scenario not in allowed_source_scenarios:
        raise ValueError(
            f"{scenario} source_scenario must be one of: {', '.join(allowed_source_scenarios)}"
        )

    source_params = params.get("source_params")
    if not isinstance(source_params, dict):
        raise ValueError(f"{scenario} source_params must be an object")
    source_preview = preview_part_scenario(source_scenario, source_params)

    source_selector = _normalize_thread_source_selector(
        source_scenario,
        params.get("source_selector") or params.get("face_selector") or params.get("base_face_selector"),
        internal=internal,
    )
    default_start_selector, default_end_selector = _default_thread_boundary_selectors(
        source_scenario,
        source_selector,
        internal=internal,
    )
    start_selector = _normalize_thread_boundary_selector(
        source_scenario,
        params.get("start_selector") or params.get("start_face_selector"),
        default_selector=default_start_selector,
    )
    end_selector = _normalize_thread_boundary_selector(
        source_scenario,
        params.get("end_selector") or params.get("end_face_selector"),
        default_selector=default_end_selector,
    )

    source_output = _resolve_thread_preview_output(source_preview, source_selector, field_name="source")
    start_output = _resolve_thread_preview_output(source_preview, start_selector, field_name="start")
    end_output = _resolve_thread_preview_output(source_preview, end_selector, field_name="end")
    source_origin = _resolve_thread_output_origin(source_output)
    start_origin = _resolve_thread_output_origin(start_output)
    end_origin = _resolve_thread_output_origin(end_output)
    if not internal and source_scenario == "external_conical_step":
        _validate_external_conical_thread_orientation(
            scenario=scenario,
            source_preview=source_preview,
            start_selector=start_selector,
            end_selector=end_selector,
            start_origin=start_origin,
            end_origin=end_origin,
        )
    derived_thread_length = None
    if start_origin is not None and end_origin is not None:
        derived_thread_length = abs(float(end_origin[0]) - float(start_origin[0]))

    diameter = _optional_positive_float(params, "diameter", "diameter", "d", "d1")
    if diameter is None:
        raise ValueError(f"{scenario} requires diameter")
    pitch = _optional_positive_float(params, "pitch", "pitch", "p")
    if pitch is None:
        raise ValueError(f"{scenario} requires pitch")

    thread_database_path = params.get("thread_database_path") or params.get("catalog_path")
    if thread_database_path:
        thread_database_path = str(Path(str(thread_database_path)))
        if not Path(thread_database_path).exists():
            raise ValueError(f"{scenario} thread_database_path does not exist: {thread_database_path}")

    standard_entry = resolve_thread_standard_entry(
        params.get("thread_standard")
        or params.get("standard")
        or params.get("thread_standard_file_name")
        or params.get("standard_table_name"),
        float(diameter),
        float(pitch),
        database_path=thread_database_path,
    )
    explicit_thread_length = _optional_positive_float(
        params,
        "thread depth",
        "thread_length",
        "thread_depth",
        "depth",
        "length",
        "l",
    )
    auto_length = bool(params.get("auto_length", explicit_thread_length is None))
    thread_length = float(explicit_thread_length) if explicit_thread_length is not None else derived_thread_length
    if not auto_length and thread_length is None:
        raise ValueError(f"{scenario} requires thread_length when auto_length is disabled")
    direction = _normalize_thread_direction(params)

    output_path = params.get("output_path")
    if output_path:
        output_path = str(Path(str(output_path)))

    material_payload = resolve_material_payload(params.get("material"), params.get("density"))
    return {
        "name": str(params.get("name") or ("Internal threaded step" if internal else "External threaded step")),
        "designation": str(params.get("designation") or ""),
        "material": material_payload["material"],
        "density": material_payload["density"],
        "material_catalog_matched": material_payload["catalog_matched"],
        "comment": str(params.get("comment") or ""),
        "diameter": float(diameter),
        "pitch": float(pitch),
        "thread_depth": thread_length,
        "thread_length": thread_length,
        "auto_length": auto_length,
        "auto_diameter": bool(params.get("auto_diameter", False)),
        "fit_base_object": bool(params.get("fit_base_object", False)),
        "fit_base_object_offset1": bool(params.get("fit_base_object_offset1", False)),
        "fit_base_object_offset2": bool(params.get("fit_base_object_offset2", False)),
        "direction": direction,
        "thread_direction": direction,
        "left_thread": direction == "left",
        "internal": internal,
        "source_scenario": source_scenario,
        "source_params": dict(source_params),
        "source_preview": source_preview,
        "source_selector": source_selector,
        "start_selector": start_selector,
        "end_selector": end_selector,
        "source_origin": source_origin,
        "start_origin": start_origin,
        "end_origin": end_origin,
        "thread_database_path": standard_entry["database_path"],
        "thread_standard_table_name": str(standard_entry["table_name"]),
        "thread_standard_display_name": str(standard_entry["display_name"]),
        "thread_designation": str(standard_entry.get("designation") or ""),
        "thread_standard_entry": dict(standard_entry.get("entry") or {}),
        "internal_diameter_coefficient": float(standard_entry.get("internal_diameter_coefficient") or 0.0),
        "conical_thread_angle": float(standard_entry.get("conical_thread_angle") or 0.0),
        "output_path": output_path,
        "visible": bool(params.get("visible", False)),
        "close_after_save": bool(params.get("close_after_save", True)),
    }


def _build_stepped_shaft_boundary_points(params: dict[str, Any], anchors: dict[str, Any]) -> list[list[float]]:
    steps = params.get("steps") or []
    axis_start = anchors.get("axis_start") or [0.0, 0.0]
    if isinstance(axis_start, (list, tuple)) and len(axis_start) == 3:
        axis_start = [axis_start[0], axis_start[1]]
    x = float(axis_start[0]) if isinstance(axis_start, (list, tuple)) and len(axis_start) >= 2 else 0.0
    y = float(axis_start[1]) if isinstance(axis_start, (list, tuple)) and len(axis_start) >= 2 else 0.0
    points: list[list[float]] = [[x, y, 0.0]]
    for step in steps:
        x += float(step.get("length") or 0.0)
        points.append([x, y, 0.0])
    return points


def _normalize_stepped_shaft_reference_preview(reference: dict[str, Any], *, field_name: str) -> dict[str, Any]:
    source_preview_payload = reference.get("source_preview")
    if isinstance(source_preview_payload, dict):
        source_preview = dict(source_preview_payload)
        if source_preview.get("scenario") != "stepped_shaft":
            raise ValueError(f"{field_name} reference.source_preview must be stepped_shaft preview")
        return source_preview
    source_params_payload = reference.get("source_params") or reference.get("params")
    if not isinstance(source_params_payload, dict):
        raise ValueError(f"{field_name} reference.source_params must be an object")
    return preview_stepped_shaft(source_params_payload)


_REVOLVED_FACE_REFERENCE_SCENARIOS = (
    "stepped_shaft",
    "external_conical_step",
    "internal_conical_step",
    "internal_cylindrical_step",
    "external_polygonal_step",
    "internal_polygonal_step",
    "external_flat_step",
    "internal_flat_step",
    "face_ring_groove",
)


def _feature_reference_label(source_scenario: str) -> str:
    labels = {
        "stepped_shaft": "stepped_shaft",
        "external_conical_step": "external_conical_step",
        "internal_conical_step": "internal_conical_step",
        "internal_cylindrical_step": "internal_cylindrical_step",
        "external_polygonal_step": "external_polygonal_step",
        "internal_polygonal_step": "internal_polygonal_step",
        "external_flat_step": "external_flat_step",
        "internal_flat_step": "internal_flat_step",
        "face_ring_groove": "face_ring_groove",
    }
    return labels.get(source_scenario, source_scenario)


def _feature_reference_title(source_scenario: str) -> str:
    return _feature_reference_label(source_scenario)[:1].upper() + _feature_reference_label(source_scenario)[1:]


def _default_feature_face_selector(source_scenario: str) -> str:
    if source_scenario == "stepped_shaft":
        return "far_end_face"
    if source_scenario == "face_ring_groove":
        return "bottom_face"
    if source_scenario in ("external_polygonal_step", "internal_polygonal_step"):
        return "end_face"
    if source_scenario in ("external_flat_step", "internal_flat_step"):
        return "end_face"
    return "end_face"


def _list_feature_face_selector_choices(
    source_scenario: str,
    source_preview: dict[str, Any] | None = None,
) -> list[str]:
    if source_scenario == "stepped_shaft":
        return _list_stepped_shaft_selector_choices(source_preview)
    outputs = dict(((source_preview or {}).get("interface") or {}).get("outputs") or {})
    selector_names = [
        str(name).strip()
        for name, output in outputs.items()
        if str((output or {}).get("type") or "") == "face" and str(name).strip()
    ]
    if selector_names:
        return sorted(set(selector_names))
    if source_scenario == "external_conical_step":
        return ["end_face", "outer_face", "start_face"]
    if source_scenario == "internal_conical_step":
        return ["end_face", "inner_face", "start_face"]
    if source_scenario == "internal_cylindrical_step":
        return ["end_face", "inner_face", "start_face", "step_1_inner_face", "step_1_end_face"]
    if source_scenario == "external_polygonal_step":
        return ["end_face", "start_face", "side_face_1"]
    if source_scenario == "internal_polygonal_step":
        return ["end_face", "start_face", "side_face_1"]
    if source_scenario == "external_flat_step":
        return ["end_face", "start_face", "flat_1_face", "flat_2_face"]
    if source_scenario == "internal_flat_step":
        return ["end_face", "start_face", "flat_1_face", "flat_2_face"]
    if source_scenario == "face_ring_groove":
        return ["bottom_face", "inner_wall_face", "outer_wall_face"]
    return []


def _format_feature_face_selector_choices(selector_names: list[str]) -> str:
    if not selector_names:
        return "<none>"
    return ", ".join(selector_names)


def _normalize_feature_reference_preview(
    reference: dict[str, Any],
    *,
    field_name: str,
    source_scenario: str,
) -> dict[str, Any]:
    source_preview_payload = reference.get("source_preview")
    if isinstance(source_preview_payload, dict):
        source_preview = dict(source_preview_payload)
        if source_preview.get("scenario") != source_scenario:
            raise ValueError(
                f"{field_name} reference.source_preview must be {source_scenario} preview"
            )
        return source_preview
    source_params_payload = reference.get("source_params") or reference.get("params")
    if not isinstance(source_params_payload, dict):
        raise ValueError(f"{field_name} reference.source_params must be an object")
    return preview_part_scenario(source_scenario, source_params_payload)


def _normalize_feature_reference_selector(
    value: Any,
    *,
    source_scenario: str,
    source_preview: dict[str, Any] | None = None,
    field_name: str = "reference.selector",
) -> str:
    if source_scenario == "stepped_shaft":
        return _normalize_stepped_shaft_reference_selector(
            value,
            source_preview=source_preview,
            field_name=field_name,
        )
    try:
        return _normalize_operation_output_key(source_scenario, str(value or _default_feature_face_selector(source_scenario)))
    except ValueError as exc:
        raise ValueError(
            "%s uses unsupported %s selector %s; available selectors: %s"
            % (
                field_name,
                _feature_reference_label(source_scenario),
                str(value or "").strip() or "<empty>",
                _format_feature_face_selector_choices(
                    _list_feature_face_selector_choices(source_scenario, source_preview)
                ),
            )
        ) from exc


def _resolve_feature_selector_origin(
    source_scenario: str,
    selector: str,
    source_preview: dict[str, Any],
) -> list[float]:
    if source_scenario == "stepped_shaft":
        return _resolve_stepped_shaft_selector_origin(selector, source_preview)
    normalized_selector = _normalize_operation_output_key(source_scenario, selector)
    outputs = dict(((source_preview or {}).get("interface") or {}).get("outputs") or {})
    output = outputs.get(normalized_selector)
    if not isinstance(output, dict):
        raise ValueError(
            "%s selector %s is out of range for the source body; available selectors: %s"
            % (
                _feature_reference_title(source_scenario),
                selector,
                _format_feature_face_selector_choices(
                    _list_feature_face_selector_choices(source_scenario, source_preview)
                ),
            )
        )
    origin = output.get("origin")
    if origin is None:
        raise ValueError(
            "%s selector %s does not expose origin in preview; available selectors: %s"
            % (
                _feature_reference_title(source_scenario),
                selector,
                _format_feature_face_selector_choices(
                    _list_feature_face_selector_choices(source_scenario, source_preview)
                ),
            )
        )
    return _normalize_xyz_triplet(origin, field_name=f"reference.selector[{selector}]")


def _feature_selector_supports_object_lcs(source_scenario: str, selector: str) -> bool:
    if source_scenario == "stepped_shaft":
        selector_info = _parse_stepped_shaft_face_selector(selector) or {}
        return selector_info.get("kind") != "step_outer_face"
    if source_scenario == "external_conical_step":
        return selector != "outer_face"
    if source_scenario == "internal_conical_step":
        return selector != "inner_face"
    if source_scenario == "internal_cylindrical_step":
        selector_info = _parse_internal_cylindrical_step_face_selector(selector) or {}
        return selector_info.get("kind") != "segment_face"
    if source_scenario == "face_ring_groove":
        return selector == "bottom_face"
    return False


def _normalize_reference_origin(reference: dict[str, Any] | None) -> list[float] | None:
    if not isinstance(reference, dict):
        return None
    if reference.get("origin") is not None:
        return _normalize_xyz_triplet(reference.get("origin"), field_name="reference.origin")
    if reference.get("point") is not None:
        return _normalize_xyz_triplet(reference.get("point"), field_name="reference.point")
    if reference.get("position") is not None:
        return _normalize_xyz_triplet(reference.get("position"), field_name="reference.position")
    if reference.get("system_object") is not None or reference.get("default_object") is not None:
        _normalize_lcs_system_object(reference.get("system_object") or reference.get("default_object"))
        return [0.0, 0.0, 0.0]
    return None


def _normalize_rotation_triplet(value: Any) -> dict[str, float]:
    payload = value or {}
    if not isinstance(payload, dict):
        raise ValueError("rotation must be an object")
    rotation_payload = payload.get("rotation") if "rotation" in payload else payload
    if rotation_payload is None:
        rotation_payload = {}
    if not isinstance(rotation_payload, dict):
        raise ValueError("rotation must be an object")
    return {
        "rx": float(rotation_payload.get("rx", 0.0) or 0.0),
        "ry": float(rotation_payload.get("ry", 0.0) or 0.0),
        "rz": float(rotation_payload.get("rz", 0.0) or 0.0),
    }


def _validate_adjacent_step_diameters(steps: list[dict[str, Any]]) -> None:
    for left, right in zip(steps, steps[1:]):
        if abs(float(left["diameter"]) - float(right["diameter"])) <= 1e-9:
            left_name = build_parameter_name("D", int(left["index"]) + 1)
            right_name = build_parameter_name("D", int(right["index"]) + 1)
            raise ValueError(
                f"Adjacent steps must not have equal diameters: {left_name} and {right_name} both equal {float(left['diameter'])}"
            )


def _build_shaft_profile_points(steps: list[dict[str, Any]]) -> list[list[float]]:
    points: list[list[float]] = [[0.0, 0.0], [0.0, steps[0]["radius"]]]
    x = 0.0
    for index, step in enumerate(steps):
        x += step["length"]
        radius = step["radius"]
        points.append([x, radius])
        next_step = steps[index + 1] if index + 1 < len(steps) else None
        if next_step and next_step["radius"] != radius:
            points.append([x, next_step["radius"]])
    points.append([x, 0.0])
    points.append([0.0, 0.0])
    return points


def _build_external_conical_step_profile_points(normalized: dict[str, Any]) -> list[list[float]]:
    length = float(normalized["length"])
    start_radius = float(normalized["start_radius"])
    end_radius = float(normalized["end_radius"])
    return [
        [0.0, 0.0],
        [0.0, start_radius],
        [length, end_radius],
        [length, 0.0],
        [0.0, 0.0],
    ]


def _build_internal_conical_step_profile_points(normalized: dict[str, Any]) -> list[list[float]]:
    length = float(normalized["length"])
    start_radius = float(normalized["start_radius"])
    end_radius = float(normalized["end_radius"])
    if normalized["axial_direction"] == "backward":
        return [
            [0.0, 0.0],
            [0.0, start_radius],
            [-length, end_radius],
            [-length, 0.0],
            [0.0, 0.0],
        ]
    return _build_external_conical_step_profile_points(normalized)


def _build_internal_cylindrical_step_profile_points(normalized: dict[str, Any]) -> list[list[float]]:
    steps = normalized["steps"]
    points: list[list[float]] = [[0.0, 0.0], [0.0, float(steps[0]["radius"])]]
    x = 0.0
    direction = -1.0 if normalized["axial_direction"] == "backward" else 1.0
    for index, step in enumerate(steps):
        x += direction * float(step["length"])
        radius = float(step["radius"])
        points.append([x, radius])
        next_step = steps[index + 1] if index + 1 < len(steps) else None
        if next_step and float(next_step["radius"]) != radius:
            points.append([x, float(next_step["radius"])])
    points.append([x, 0.0])
    points.append([0.0, 0.0])
    return points


def _build_face_ring_groove_profile_points(normalized: dict[str, Any]) -> list[list[float]]:
    direction = -1.0 if normalized["axial_direction"] == "backward" else 1.0
    depth = direction * float(normalized["depth"])
    return [
        [0.0, float(normalized["outer_radius"])],
        [0.0, float(normalized["inner_radius"])],
        [depth, float(normalized["bottom_inner_radius"])],
        [depth, float(normalized["bottom_outer_radius"])],
        [0.0, float(normalized["outer_radius"])],
    ]


def _build_stepped_shaft_interface(normalized: dict[str, Any], profile_points: list[list[float]]) -> dict[str, Any]:
    steps = normalized["steps"]
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    diameters = [build_parameter_name("D", index, prefix=parameter_prefix) for index, _ in enumerate(steps, start=1)]
    radii = [build_parameter_name("R", index, prefix=parameter_prefix) for index, _ in enumerate(steps, start=1)]
    lengths = [build_parameter_name("L", index, prefix=parameter_prefix) for index, _ in enumerate(steps, start=1)]
    axis_start = [float(profile_points[0][0]), float(profile_points[0][1])]
    axis_end = [axis_start[0] + float(normalized["total_length"]), axis_start[1]]
    selector_points = _build_stepped_shaft_selector_points(normalized, axis_start)
    return {
        "feature_type": "revolved_body.stepped_shaft",
        "parameter_namespace": parameter_prefix,
        "operation_label": operation_label,
        "placement": normalized["placement"],
        "parameters": {
            "driving_diameters": diameters,
            "driving_lengths": lengths,
            "internal_radii": radii,
        },
        "anchors": {
            "axis_start": axis_start,
            "axis_end": axis_end,
            "profile_start": list(profile_points[1]),
            "profile_end": list(profile_points[-2]),
            "selector_points": selector_points,
        },
        "selectors": selector_points,
        "outputs": _build_stepped_shaft_outputs(axis_start, axis_end, selector_points),
        "placement_contract": {
            "base_mode": normalized["placement"]["base"]["mode"],
            "base_origin": normalized["placement"]["base_origin"],
            "local_offset": normalized["placement"]["local_offset"],
            "effective_origin": normalized["placement"]["effective_origin"],
            "reference": normalized["placement"]["reference"],
        },
    }


def _build_stepped_shaft_outputs(
    axis_start: list[float],
    axis_end: list[float],
    selector_points: dict[str, list[float]],
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {
        "body": {
            "type": "body",
            "name": "body",
            "live_supported": True,
        },
        "sketch": {
            "type": "sketch",
            "name": "sketch",
            "live_supported": True,
        },
        "axis": {
            "type": "axis",
            "name": "axis",
            "start": list(axis_start),
            "end": list(axis_end),
            "live_supported": True,
        },
    }
    for selector_name, origin in selector_points.items():
        canonical = "end_face" if selector_name == "far_end_face" else selector_name
        outputs[canonical] = {
            "type": "face",
            "selector": selector_name,
            "origin": list(origin),
            "live_supported": True,
        }
        if selector_name == "far_end_face":
            outputs["far_end_face"] = dict(outputs[canonical])
    return outputs


def _build_stepped_shaft_selector_points(normalized: dict[str, Any], axis_start: list[float]) -> dict[str, list[float]]:
    x = float(axis_start[0])
    y = float(axis_start[1])
    selectors: dict[str, list[float]] = {
        "start_face": [x, y, 0.0],
    }
    for step in normalized["steps"]:
        index = int(step["index"]) + 1
        start_x = x
        selectors[f"step_{index}_start_face"] = [x, y, 0.0]
        x += float(step["length"])
        selectors[f"step_{index}_end_face"] = [x, y, 0.0]
        selectors[f"step_{index}_outer_face"] = [float((start_x + x) / 2.0), y, 0.0]
        if index < len(normalized["steps"]):
            selectors[f"shoulder_{index}_face"] = [x, y, 0.0]
    selectors["far_end_face"] = [x, y, 0.0]
    return selectors


def _build_external_conical_step_interface(normalized: dict[str, Any], profile_points: list[list[float]]) -> dict[str, Any]:
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    axis_start = [float(profile_points[0][0]), float(profile_points[0][1])]
    axis_end = [axis_start[0] + float(normalized["length"]), axis_start[1]]
    selector_points = {
        "start_face": [float(axis_start[0]), float(axis_start[1]), 0.0],
        "end_face": [float(axis_end[0]), float(axis_end[1]), 0.0],
        "outer_face": [float((axis_start[0] + axis_end[0]) / 2.0), float(axis_start[1]), 0.0],
    }
    return {
        "feature_type": "revolved_body.external_conical_step",
        "parameter_namespace": parameter_prefix,
        "operation_label": operation_label,
        "definition": {
            "mode": normalized["definition_mode"],
            "cone_angle_degrees": normalized["cone_angle_degrees"],
            "conicity": normalized["conicity"],
            "slope_direction": normalized["slope_direction"],
        },
        "placement": normalized["placement"],
        "parameters": {
            "driving_diameters": [
                build_parameter_name("D", 1, prefix=parameter_prefix),
                build_parameter_name("D", 2, prefix=parameter_prefix),
            ],
            "driving_lengths": [build_parameter_name("L", 1, prefix=parameter_prefix)],
            "internal_radii": [
                build_parameter_name("R", 1, prefix=parameter_prefix),
                build_parameter_name("R", 2, prefix=parameter_prefix),
            ],
        },
        "anchors": {
            "axis_start": axis_start,
            "axis_end": axis_end,
            "profile_start": list(profile_points[1]),
            "profile_end": list(profile_points[-2]),
            "selector_points": selector_points,
        },
        "selectors": selector_points,
        "outputs": _build_external_conical_step_outputs(axis_start, axis_end, selector_points),
        "placement_contract": {
            "base_mode": normalized["placement"]["base"]["mode"],
            "base_origin": normalized["placement"]["base_origin"],
            "local_offset": normalized["placement"]["local_offset"],
            "effective_origin": normalized["placement"]["effective_origin"],
            "reference": normalized["placement"]["reference"],
        },
    }


def _build_external_conical_step_outputs(
    axis_start: list[float],
    axis_end: list[float],
    selector_points: dict[str, list[float]],
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {
        "body": {
            "type": "body",
            "name": "body",
            "live_supported": True,
        },
        "sketch": {
            "type": "sketch",
            "name": "sketch",
            "live_supported": True,
        },
        "axis": {
            "type": "axis",
            "name": "axis",
            "start": list(axis_start),
            "end": list(axis_end),
            "live_supported": True,
        },
    }
    for selector_name, origin in selector_points.items():
        outputs[selector_name] = {
            "type": "face",
            "selector": selector_name,
            "origin": list(origin),
            "live_supported": True,
        }
    for alias_name, canonical_name in (
        ("large_end_face", "start_face"),
        ("seat_face", "start_face"),
        ("small_end_face", "end_face"),
        ("free_end_face", "end_face"),
    ):
        outputs[alias_name] = dict(outputs[canonical_name])
    return outputs


def _build_internal_conical_step_interface(normalized: dict[str, Any], profile_points: list[list[float]]) -> dict[str, Any]:
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    axis_start = [float(profile_points[0][0]), float(profile_points[0][1])]
    axis_end = [float(profile_points[-2][0]), float(profile_points[-2][1])]
    selector_points = {
        "start_face": [float(axis_start[0]), float(axis_start[1]), 0.0],
        "end_face": [float(axis_end[0]), float(axis_end[1]), 0.0],
        "inner_face": [float((axis_start[0] + axis_end[0]) / 2.0), float(axis_start[1]), 0.0],
    }
    return {
        "feature_type": "revolved_cut.internal_conical_step",
        "parameter_namespace": parameter_prefix,
        "operation_label": operation_label,
        "definition": {
            "mode": normalized["definition_mode"],
            "cone_angle_degrees": normalized["cone_angle_degrees"],
            "conicity": normalized["conicity"],
            "slope_direction": normalized["slope_direction"],
            "axial_direction": normalized["axial_direction"],
        },
        "placement": normalized["placement"],
        "parameters": {
            "driving_diameters": [
                build_parameter_name("D", 1, prefix=parameter_prefix),
                build_parameter_name("D", 2, prefix=parameter_prefix),
            ],
            "driving_lengths": [build_parameter_name("L", 1, prefix=parameter_prefix)],
            "internal_radii": [
                build_parameter_name("R", 1, prefix=parameter_prefix),
                build_parameter_name("R", 2, prefix=parameter_prefix),
            ],
        },
        "anchors": {
            "axis_start": axis_start,
            "axis_end": axis_end,
            "profile_start": list(profile_points[1]),
            "profile_end": list(profile_points[-2]),
            "selector_points": selector_points,
        },
        "selectors": selector_points,
        "outputs": _build_internal_conical_step_outputs(axis_start, axis_end, selector_points),
        "placement_contract": {
            "base_mode": normalized["placement"]["base"]["mode"],
            "base_origin": normalized["placement"]["base_origin"],
            "local_offset": normalized["placement"]["local_offset"],
            "effective_origin": normalized["placement"]["effective_origin"],
            "reference": normalized["placement"]["reference"],
        },
    }


def _build_internal_conical_step_outputs(
    axis_start: list[float],
    axis_end: list[float],
    selector_points: dict[str, list[float]],
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {
        "body": {
            "type": "body",
            "name": "body",
            "live_supported": True,
        },
        "sketch": {
            "type": "sketch",
            "name": "sketch",
            "live_supported": True,
        },
        "axis": {
            "type": "axis",
            "name": "axis",
            "start": list(axis_start),
            "end": list(axis_end),
            "live_supported": True,
        },
    }
    for selector_name, origin in selector_points.items():
        outputs[selector_name] = {
            "type": "face",
            "selector": selector_name,
            "origin": list(origin),
            "live_supported": True,
        }
    return outputs


def _build_internal_cylindrical_step_interface(normalized: dict[str, Any], profile_points: list[list[float]]) -> dict[str, Any]:
    steps = normalized["steps"]
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    axis_start = [float(profile_points[0][0]), float(profile_points[0][1])]
    axis_end = [float(profile_points[-2][0]), float(profile_points[-2][1])]
    selector_points = _build_internal_cylindrical_step_selector_points(normalized, axis_start)
    return {
        "feature_type": "revolved_cut.internal_cylindrical_step",
        "parameter_namespace": parameter_prefix,
        "operation_label": operation_label,
        "definition": {
            "mode": "diameter_length" if len(steps) == 1 else "stepped_diameter_length",
            "axial_direction": normalized["axial_direction"],
        },
        "placement": normalized["placement"],
        "parameters": {
            "driving_diameters": [
                build_parameter_name("D", index, prefix=parameter_prefix) for index, _ in enumerate(steps, start=1)
            ],
            "driving_lengths": [
                build_parameter_name("L", index, prefix=parameter_prefix) for index, _ in enumerate(steps, start=1)
            ],
            "internal_radii": [
                build_parameter_name("R", index, prefix=parameter_prefix) for index, _ in enumerate(steps, start=1)
            ],
        },
        "anchors": {
            "axis_start": axis_start,
            "axis_end": axis_end,
            "profile_start": list(profile_points[1]),
            "profile_end": list(profile_points[-2]),
            "selector_points": selector_points,
        },
        "selectors": selector_points,
        "outputs": _build_internal_cylindrical_step_outputs(axis_start, axis_end, selector_points),
        "placement_contract": {
            "base_mode": normalized["placement"]["base"]["mode"],
            "base_origin": normalized["placement"]["base_origin"],
            "local_offset": normalized["placement"]["local_offset"],
            "effective_origin": normalized["placement"]["effective_origin"],
            "reference": normalized["placement"]["reference"],
        },
    }


def _build_internal_cylindrical_step_outputs(
    axis_start: list[float],
    axis_end: list[float],
    selector_points: dict[str, list[float]],
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {
        "body": {
            "type": "body",
            "name": "body",
            "live_supported": True,
        },
        "sketch": {
            "type": "sketch",
            "name": "sketch",
            "live_supported": True,
        },
        "axis": {
            "type": "axis",
            "name": "axis",
            "start": list(axis_start),
            "end": list(axis_end),
            "live_supported": True,
        },
    }
    for selector_name, origin in selector_points.items():
        canonical = "far_end_face" if selector_name == "end_face" else selector_name
        outputs[canonical] = {
            "type": "face",
            "selector": selector_name,
            "origin": list(origin),
            "live_supported": True,
        }
        if selector_name == "end_face":
            outputs["end_face"] = dict(outputs[canonical])
    outputs["inner_cylindrical_face"] = dict(outputs["inner_face"])
    return outputs


def _build_internal_cylindrical_step_selector_points(
    normalized: dict[str, Any],
    axis_start: list[float],
) -> dict[str, list[float]]:
    x = float(axis_start[0])
    y = float(axis_start[1])
    direction = -1.0 if normalized["axial_direction"] == "backward" else 1.0
    selectors: dict[str, list[float]] = {
        "start_face": [x, y, 0.0],
    }
    for step in normalized["steps"]:
        index = int(step["index"]) + 1
        start_x = x
        selectors[f"step_{index}_start_face"] = [x, y, 0.0]
        x += direction * float(step["length"])
        selectors[f"step_{index}_end_face"] = [x, y, 0.0]
        selectors[f"step_{index}_inner_face"] = [float((start_x + x) / 2.0), y, 0.0]
        if index < len(normalized["steps"]):
            selectors[f"shoulder_{index}_face"] = [x, y, 0.0]
    selectors["end_face"] = [x, y, 0.0]
    selectors["inner_face"] = list(selectors["step_1_inner_face"])
    return selectors


def _normalize_polygonal_step_diameter_mode(value: Any) -> str:
    key = str(value or "inscribed_circle").strip().lower().replace("-", "_")
    aliases = {
        "inscribed_circle": "inscribed_circle",
        "inscribed": "inscribed_circle",
        "inner_circle": "inscribed_circle",
        "incircle": "inscribed_circle",
        "circumscribed_circle": "circumscribed_circle",
        "circumscribed": "circumscribed_circle",
        "outer_circle": "circumscribed_circle",
        "circumcircle": "circumscribed_circle",
    }
    normalized = aliases.get(key, key)
    if normalized not in {"inscribed_circle", "circumscribed_circle"}:
        raise ValueError("polygonal_step diameter_mode must be inscribed_circle or circumscribed_circle")
    return normalized


def _resolve_polygonal_step_radius(diameter: float, side_count: int, diameter_mode: str) -> float:
    base_radius = float(diameter) / 2.0
    if diameter_mode == "circumscribed_circle":
        return base_radius
    angle = math.pi / float(side_count)
    cos_value = math.cos(angle)
    if abs(cos_value) < 1e-9:
        raise ValueError("polygonal_step side_count produces invalid inscribed circle radius")
    return base_radius / cos_value


def _build_polygonal_step_vertices(normalized: dict[str, Any]) -> list[list[float]]:
    side_count = int(normalized["side_count"])
    polygon_radius = float(normalized["polygon_radius"])
    base_angle = math.radians(float(normalized["rotation_angle_degrees"])) + (math.pi / 2.0) - (math.pi / float(side_count))
    vertices: list[list[float]] = []
    for index in range(side_count):
        angle = base_angle + (2.0 * math.pi * index / float(side_count))
        vertices.append(
            [
                float(polygon_radius * math.cos(angle)),
                float(polygon_radius * math.sin(angle)),
            ]
        )
    return vertices


def _build_polygonal_step_selector_points(
    normalized: dict[str, Any],
    axis_start: list[float],
    axis_end: list[float],
    vertices: list[list[float]],
) -> dict[str, list[float]]:
    direction_mid_x = float(axis_start[0] + axis_end[0]) / 2.0
    center_y = float(axis_start[1])
    selectors = {
        "start_face": [float(axis_start[0]), center_y, 0.0],
        "end_face": [float(axis_end[0]), center_y, 0.0],
    }
    if len(vertices) >= 2:
        edge_mid = [
            float((vertices[0][0] + vertices[1][0]) / 2.0),
            float((vertices[0][1] + vertices[1][1]) / 2.0),
        ]
        selectors["side_face_1"] = [direction_mid_x, center_y + edge_mid[0], edge_mid[1]]
    else:
        selectors["side_face_1"] = [direction_mid_x, center_y, 0.0]
    return selectors


def _build_flat_step_profile_geometry(normalized: dict[str, Any]) -> dict[str, Any]:
    radius = float(normalized["radius"])
    flat_offset = float(normalized["flat_offset"])
    chord_half = float(normalized["chord_half"])
    chord_draw_half = max(chord_half - min(0.05, chord_half * 0.1, radius * 0.01), 0.0)
    helper_circle = {
        "xc": 0.0,
        "yc": 0.0,
        "radius": radius,
    }
    if int(normalized["flats_count"]) == 1:
        return {
            "helper_circle": helper_circle,
            "profile_lines": [
                {
                    "target": "top_flat_line",
                    "x1": -chord_draw_half,
                    "y1": flat_offset,
                    "x2": chord_draw_half,
                    "y2": flat_offset,
                }
            ],
            "profile_arcs": [
                {
                    "target": "outer_arc",
                    "xc": 0.0,
                    "yc": 0.0,
                    "radius": radius,
                    "x1": chord_half,
                    "y1": flat_offset,
                    "x2": -chord_half,
                    "y2": flat_offset,
                    "direction": False,
                }
            ],
        }

    return {
        "helper_circle": helper_circle,
        "profile_lines": [
            {
                "target": "top_flat_line",
                "x1": -chord_draw_half,
                "y1": flat_offset,
                "x2": chord_draw_half,
                "y2": flat_offset,
            },
            {
                "target": "bottom_flat_line",
                "x1": chord_draw_half,
                "y1": -flat_offset,
                "x2": -chord_draw_half,
                "y2": -flat_offset,
            },
        ],
        "profile_arcs": [
            {
                "target": "right_arc",
                "xc": 0.0,
                "yc": 0.0,
                "radius": radius,
                "x1": chord_half,
                "y1": flat_offset,
                "x2": chord_half,
                "y2": -flat_offset,
                "direction": False,
            },
            {
                "target": "left_arc",
                "xc": 0.0,
                "yc": 0.0,
                "radius": radius,
                "x1": -chord_half,
                "y1": -flat_offset,
                "x2": -chord_half,
                "y2": flat_offset,
                "direction": False,
            },
        ],
    }


def _build_flat_step_selector_points(
    normalized: dict[str, Any],
    axis_start: list[float],
    axis_end: list[float],
) -> dict[str, list[float]]:
    direction_mid_x = float(axis_start[0] + axis_end[0]) / 2.0
    center_y = float(axis_start[1])
    flat_offset = float(normalized["flat_offset"])
    selectors = {
        "start_face": [float(axis_start[0]), center_y, 0.0],
        "end_face": [float(axis_end[0]), center_y, 0.0],
        "flat_1_face": [direction_mid_x, center_y, flat_offset],
    }
    if int(normalized["flats_count"]) == 2:
        selectors["flat_2_face"] = [direction_mid_x, center_y, -flat_offset]
    return selectors


def _build_external_polygonal_step_interface(
    normalized: dict[str, Any],
    axis_start: list[float],
    axis_end: list[float],
    vertices: list[list[float]],
) -> dict[str, Any]:
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    selectors = _build_polygonal_step_selector_points(normalized, axis_start, axis_end, vertices)
    return {
        "feature_type": "extruded_body.external_polygonal_step",
        "parameter_namespace": parameter_prefix,
        "operation_label": operation_label,
        "definition": {
            "mode": normalized["diameter_mode"],
            "side_count": normalized["side_count"],
            "rotation_angle_degrees": normalized["rotation_angle_degrees"],
            "axial_direction": normalized["axial_direction"],
        },
        "placement": normalized["placement"],
        "parameters": {
            "driving_diameters": [build_parameter_name("D", 1, prefix=parameter_prefix)],
            "driving_lengths": [build_parameter_name("L", 1, prefix=parameter_prefix)],
            "internal_sizes": [build_parameter_name("R", 1, prefix=parameter_prefix)],
            "shape_parameters": {
                "diameter": normalized["diameter"],
                "length": normalized["length"],
                "side_count": normalized["side_count"],
            },
        },
        "anchors": {
            "axis_start": list(axis_start),
            "axis_end": list(axis_end),
            "profile_center": list(normalized["placement"]["effective_origin"]),
            "profile_vertices": [list(vertex) for vertex in vertices],
            "selector_points": selectors,
        },
        "selectors": selectors,
        "outputs": _build_polygonal_step_outputs(axis_start, axis_end, selectors),
        "placement_contract": {
            "base_mode": normalized["placement"]["base"]["mode"],
            "base_origin": normalized["placement"]["base_origin"],
            "local_offset": normalized["placement"]["local_offset"],
            "effective_origin": normalized["placement"]["effective_origin"],
            "reference": normalized["placement"]["reference"],
        },
    }


def _build_internal_polygonal_step_interface(
    normalized: dict[str, Any],
    axis_start: list[float],
    axis_end: list[float],
    vertices: list[list[float]],
) -> dict[str, Any]:
    payload = _build_external_polygonal_step_interface(normalized, axis_start, axis_end, vertices)
    payload["feature_type"] = "extruded_cut.internal_polygonal_step"
    payload["definition"] = dict(payload["definition"])
    payload["definition"]["source_scenario"] = normalized["source_scenario"]
    return payload


def _build_external_flat_step_interface(
    normalized: dict[str, Any],
    axis_start: list[float],
    axis_end: list[float],
) -> dict[str, Any]:
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    selectors = _build_flat_step_selector_points(normalized, axis_start, axis_end)
    return {
        "feature_type": "extruded_body.external_flat_step",
        "parameter_namespace": parameter_prefix,
        "operation_label": operation_label,
        "definition": {
            "mode": "diameter_flat_depth",
            "flats_count": normalized["flats_count"],
            "axial_direction": normalized["axial_direction"],
        },
        "placement": normalized["placement"],
        "parameters": {
            "driving_diameters": [build_parameter_name("D", 1, prefix=parameter_prefix)],
            "driving_lengths": [build_parameter_name("L", 1, prefix=parameter_prefix)],
            "driving_flat_depths": [build_parameter_name("F", 1, prefix=parameter_prefix)],
            "internal_sizes": [build_parameter_name("R", 1, prefix=parameter_prefix)],
            "shape_parameters": {
                "diameter": normalized["diameter"],
                "length": normalized["length"],
                "flat_depth": normalized["flat_depth"],
                "flats_count": normalized["flats_count"],
            },
        },
        "anchors": {
            "axis_start": list(axis_start),
            "axis_end": list(axis_end),
            "profile_center": list(normalized["placement"]["effective_origin"]),
            "selector_points": selectors,
        },
        "selectors": selectors,
        "outputs": _build_flat_step_outputs(selectors),
        "placement_contract": {
            "base_mode": normalized["placement"]["base"]["mode"],
            "base_origin": normalized["placement"]["base_origin"],
            "local_offset": normalized["placement"]["local_offset"],
            "effective_origin": normalized["placement"]["effective_origin"],
            "reference": normalized["placement"]["reference"],
        },
    }


def _build_internal_flat_step_interface(
    normalized: dict[str, Any],
    axis_start: list[float],
    axis_end: list[float],
) -> dict[str, Any]:
    payload = _build_external_flat_step_interface(normalized, axis_start, axis_end)
    payload["feature_type"] = "extruded_cut.internal_flat_step"
    payload["definition"] = dict(payload["definition"])
    payload["definition"]["source_scenario"] = normalized["source_scenario"]
    return payload


def _build_flat_step_outputs(selector_points: dict[str, list[float]]) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {
        "body": {
            "type": "body",
            "name": "body",
            "live_supported": True,
        },
        "sketch": {
            "type": "sketch",
            "name": "sketch",
            "live_supported": True,
        },
    }
    for selector_name, origin in selector_points.items():
        canonical = "far_end_face" if selector_name == "end_face" else selector_name
        outputs[canonical] = {
            "type": "face",
            "selector": selector_name,
            "origin": list(origin),
            "live_supported": selector_name in {"start_face", "end_face", "flat_1_face", "flat_2_face"},
        }
        if selector_name == "end_face":
            outputs["end_face"] = dict(outputs[canonical])
    return outputs


def _build_polygonal_step_outputs(
    axis_start: list[float],
    axis_end: list[float],
    selector_points: dict[str, list[float]],
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {
        "body": {
            "type": "body",
            "name": "body",
            "live_supported": True,
        },
        "sketch": {
            "type": "sketch",
            "name": "sketch",
            "live_supported": True,
        },
    }
    for selector_name, origin in selector_points.items():
        canonical = "far_end_face" if selector_name == "end_face" else selector_name
        outputs[canonical] = {
            "type": "face",
            "selector": selector_name,
            "origin": list(origin),
            "live_supported": selector_name in {"start_face", "end_face"},
        }
        if selector_name == "end_face":
            outputs["end_face"] = dict(outputs[canonical])
    return outputs


def _build_face_ring_groove_interface(normalized: dict[str, Any], profile_points: list[list[float]]) -> dict[str, Any]:
    parameter_prefix = normalized["parameter_prefix"]
    operation_label = build_operation_label(normalized["name"], parameter_prefix=parameter_prefix)
    axis_start = [float(normalized["placement"]["effective_origin"][0]), float(normalized["placement"]["effective_origin"][1])]
    axis_end = [
        float(axis_start[0]) + (-float(normalized["depth"]) if normalized["axial_direction"] == "backward" else float(normalized["depth"])),
        float(axis_start[1]),
    ]
    selectors = _build_face_ring_groove_selector_points(normalized, axis_start)
    return {
        "feature_type": "revolved_cut.face_ring_groove",
        "parameter_namespace": parameter_prefix,
        "operation_label": operation_label,
        "definition": {
            "mode": "diameters_depth_angles",
            "axial_direction": normalized["axial_direction"],
            "inner_wall_angle_degrees": normalized["inner_wall_angle_degrees"],
            "outer_wall_angle_degrees": normalized["outer_wall_angle_degrees"],
        },
        "placement": normalized["placement"],
        "parameters": {
            "driving_diameters": [
                build_parameter_name("ID", 1, prefix=parameter_prefix),
                build_parameter_name("OD", 1, prefix=parameter_prefix),
                build_parameter_name("BID", 1, prefix=parameter_prefix),
                build_parameter_name("BOD", 1, prefix=parameter_prefix),
            ],
            "driving_lengths": [build_parameter_name("DEP", 1, prefix=parameter_prefix)],
            "internal_radii": [
                build_parameter_name("IR", 1, prefix=parameter_prefix),
                build_parameter_name("OR", 1, prefix=parameter_prefix),
                build_parameter_name("BIR", 1, prefix=parameter_prefix),
                build_parameter_name("BOR", 1, prefix=parameter_prefix),
            ],
        },
        "anchors": {
            "axis_start": axis_start,
            "axis_end": axis_end,
            "profile_start": list(profile_points[0]),
            "profile_end": list(profile_points[-2]),
            "selector_points": selectors,
        },
        "selectors": selectors,
        "outputs": _build_face_ring_groove_outputs(axis_start, axis_end, selectors),
        "placement_contract": {
            "base_mode": normalized["placement"]["base"]["mode"],
            "base_origin": normalized["placement"]["base_origin"],
            "local_offset": normalized["placement"]["local_offset"],
            "effective_origin": normalized["placement"]["effective_origin"],
            "reference": normalized["placement"]["reference"],
        },
    }


def _build_face_ring_groove_outputs(
    axis_start: list[float],
    axis_end: list[float],
    selector_points: dict[str, list[float]],
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {
        "body": {
            "type": "body",
            "name": "body",
            "live_supported": True,
        },
        "sketch": {
            "type": "sketch",
            "name": "sketch",
            "live_supported": True,
        },
        "axis": {
            "type": "axis",
            "name": "axis",
            "start": list(axis_start),
            "end": list(axis_end),
            "live_supported": True,
        },
    }
    for selector_name, origin in selector_points.items():
        outputs[selector_name] = {
            "type": "face",
            "selector": selector_name,
            "origin": list(origin),
            "live_supported": True,
        }
    outputs["inner_face"] = dict(outputs["inner_wall_face"])
    outputs["outer_face"] = dict(outputs["outer_wall_face"])
    return outputs


def _build_face_ring_groove_selector_points(
    normalized: dict[str, Any],
    axis_start: list[float],
) -> dict[str, list[float]]:
    x = float(axis_start[0])
    y = float(axis_start[1])
    direction = -1.0 if normalized["axial_direction"] == "backward" else 1.0
    bottom_x = x + direction * float(normalized["depth"])
    return {
        "inner_wall_face": [
            float((x + bottom_x) / 2.0),
            y + float((normalized["inner_radius"] + normalized["bottom_inner_radius"]) / 2.0),
            0.0,
        ],
        "outer_wall_face": [
            float((x + bottom_x) / 2.0),
            y + float((normalized["outer_radius"] + normalized["bottom_outer_radius"]) / 2.0),
            0.0,
        ],
        "bottom_face": [
            bottom_x,
            y + float((normalized["bottom_inner_radius"] + normalized["bottom_outer_radius"]) / 2.0),
            0.0,
        ],
    }


def _build_bolt_circle_holes_interface(
    normalized: dict[str, Any],
    hole_centers: list[list[float]],
    first_hole_center: list[float],
    variable_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    placement_origin = normalized["placement"]["effective_origin"]
    driving_diameters = [item["name"] for item in variable_plan if str(item.get("kind") or "").startswith("driving_") and "diameter" in str(item.get("kind") or "")]
    driving_lengths = [item["name"] for item in variable_plan if str(item.get("kind") or "").startswith("driving_") and "length" in str(item.get("kind") or "")]
    pattern_variables = {
        str(item.get("kind") or ""): item["name"]
        for item in variable_plan
        if str(item.get("kind") or "").startswith("driving_pattern") or str(item.get("kind") or "") == "driving_pcd"
    }
    return {
        "feature_type": "pattern.bolt_circle_holes",
        "parameter_namespace": normalized["parameter_prefix"],
        "operation_label": build_operation_label(normalized["name"], parameter_prefix=normalized["parameter_prefix"]),
        "definition": {
            "mode": "circular_pattern",
            "axial_direction": normalized["axial_direction"],
            "count": normalized["count"],
            "start_angle_degrees": normalized["start_angle_degrees"],
            "clockwise": normalized["clockwise"],
            "auxiliary_geometry_hidden": normalized["auxiliary_geometry_hidden"],
        },
        "placement": normalized["placement"],
        "parameters": {
            "hole_diameter": normalized["hole_diameter"],
            "depth": normalized["depth"],
            "bolt_circle_diameter": normalized["bolt_circle_diameter"],
            "count": normalized["count"],
            "driving_diameters": driving_diameters,
            "driving_lengths": driving_lengths,
            "driving_pcd": pattern_variables.get("driving_pcd", ""),
            "driving_pattern_count": pattern_variables.get("driving_pattern_count", ""),
            "driving_pattern_angle_step": pattern_variables.get("driving_pattern_angle_step", ""),
            "pattern_count_expression": normalized["pattern_count_expression"],
            "pattern_step_expression": normalized["pattern_step_expression"],
        },
        "anchors": {
            "placement_center": [float(placement_origin[0]), float(placement_origin[1]), 0.0],
            "first_hole_center": list(first_hole_center),
            "hole_centers": [list(center) for center in hole_centers],
        },
        "outputs": {
            "body": {"type": "body", "live_supported": True},
            "axis": {
                "type": "axis",
                "name": "pattern_axis",
                "origin": [float(placement_origin[0]), float(placement_origin[1]), 0.0],
                "live_supported": True,
            },
            "first_hole_center": {
                "type": "point",
                "name": "first_hole_center",
                "origin": list(first_hole_center),
                "live_supported": True,
            },
            "first_hole_lcs": {
                "type": "lcs",
                "name": "first_hole_lcs",
                "origin": list(first_hole_center),
                "live_supported": True,
            },
        },
        "placement_contract": {
            "base_mode": normalized["placement"]["base"]["mode"],
            "base_origin": normalized["placement"]["base_origin"],
            "local_offset": normalized["placement"]["local_offset"],
            "effective_origin": normalized["placement"]["effective_origin"],
            "reference": normalized["placement"]["reference"],
        },
    }


def _build_compression_spring_interface(
    normalized: dict[str, Any],
    start_center: list[float],
    end_center: list[float],
    selector_points: dict[str, list[float]],
) -> dict[str, Any]:
    driving_variables = {
        str(item.get("kind") or ""): item["name"]
        for item in (normalized.get("variable_plan") or [])
        if str(item.get("kind") or "").startswith("driving_")
    }
    outputs: dict[str, dict[str, Any]] = {
        "body": {"type": "body", "live_supported": normalized["live_supported"]},
        "axis": {
            "type": "axis",
            "name": "spring_axis",
            "origin": list(start_center),
            "end": list(end_center),
            "live_supported": normalized["live_supported"],
        },
        "spiral_path": {
            "type": "curve3d",
            "name": "spiral_path",
            "live_supported": normalized["live_supported"],
        },
    }
    for selector_name, origin in selector_points.items():
        outputs[selector_name] = _build_compression_spring_point_output(
            selector_name,
            origin,
            live_supported=normalized["live_supported"],
        )
    return {
        "feature_type": "spring.compression",
        "parameter_namespace": normalized["parameter_prefix"],
        "operation_label": build_operation_label(normalized["name"], parameter_prefix=normalized["parameter_prefix"]),
        "definition": {
            "mode": "cylindrical_spiral_sweep",
            "axis": normalized["axis"],
            "turn_direction": normalized["turn_direction"],
            "left_hand": normalized["left_hand"],
            "auxiliary_geometry_hidden": normalized["auxiliary_geometry_hidden"],
            "live_supported": normalized["live_supported"],
        },
        "placement": normalized["placement"],
        "parameters": {
            "mean_diameter": normalized["mean_diameter"],
            "outer_diameter": normalized["outer_diameter"],
            "inner_diameter": normalized["inner_diameter"],
            "wire_diameter": normalized["wire_diameter"],
            "pitch": normalized["pitch"],
            "height": normalized["height"],
            "turns": normalized["turns"],
            "working_turns": normalized["working_turns"],
            "total_turns": normalized["total_turns"],
            "end_turns_per_side": normalized["end_turns_per_side"],
            "ground_turns_per_side": normalized["ground_turns_per_side"],
            "driving_mean_diameter": driving_variables.get("driving_mean_diameter", ""),
            "driving_wire_diameter": driving_variables.get("driving_wire_diameter", ""),
            "driving_pitch": driving_variables.get("driving_pitch", ""),
            "driving_height": driving_variables.get("driving_height", ""),
            "driving_turn_count": driving_variables.get("driving_turn_count", ""),
            "driving_end_turn_count_per_side": driving_variables.get("driving_end_turn_count_per_side", ""),
            "driving_ground_turn_count_per_side": driving_variables.get("driving_ground_turn_count_per_side", ""),
            "driving_start_end_turn_count": driving_variables.get("driving_start_end_turn_count", ""),
            "driving_finish_end_turn_count": driving_variables.get("driving_finish_end_turn_count", ""),
            "driving_start_ground_turn_count": driving_variables.get("driving_start_ground_turn_count", ""),
            "driving_finish_ground_turn_count": driving_variables.get("driving_finish_ground_turn_count", ""),
            "mean_diameter_expression": normalized["mean_diameter_expression"],
            "wire_diameter_expression": normalized["wire_diameter_expression"],
            "pitch_expression": normalized["pitch_expression"],
            "height_expression": normalized["height_expression"],
            "turns_expression": normalized["turns_expression"],
        },
        "anchors": {
            "start_center": list(start_center),
            "end_center": list(end_center),
            "selector_points": {name: list(origin) for name, origin in selector_points.items()},
        },
        "selectors": {name: list(origin) for name, origin in selector_points.items()},
        "outputs": outputs,
        "placement_contract": {
            "base_mode": normalized["placement"]["base"]["mode"],
            "base_origin": normalized["placement"]["base_origin"],
            "local_offset": normalized["placement"]["local_offset"],
            "effective_origin": normalized["placement"]["effective_origin"],
            "reference": normalized["placement"]["reference"],
        },
    }
