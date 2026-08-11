from __future__ import annotations

from copy import deepcopy
import math
from typing import Any


_SOURCE = {
    "document": "ISO 9982:2021",
    "title": (
        "Belt drives — Pulleys and V-ribbed belts for industrial applications — "
        "PH, PJ, PK, PL and PM profiles: Dimensions"
    ),
    "clauses": ["5.1", "Figure 1", "Figure 2", "Table 2"],
    "url": "https://www.iso.org/standard/82249.html",
    "preview_url": "https://standards.iteh.ai/catalog/standards/iso/db756eb7-e16c-42dc-b5bd-da4a3602d879/iso-9982-2021",
    "retrieved": "2026-08-11",
    "evidence_level": "official_standard_preview",
    "certified_use": "Verify against a licensed copy of ISO 9982:2021 for certified drawings.",
}


# ISO 9982:2021 Table 2, dimensions in millimetres and degrees.  The pulley
# groove root below rb is optional in the standard.  This module deliberately
# chooses the maximum permitted rb and the nominal rt to produce one stable,
# reproducible manufacturing profile.
_PROFILE_ROWS = {
    "PH": {
        "groove_pitch": 1.60,
        "groove_pitch_tolerance": 0.03,
        "transition_radius": 0.25,
        "transition_radius_tolerance": 0.05,
        "maximum_root_radius": 0.30,
        "checking_ball_or_rod_diameter": 1.00,
        "two_x_nominal": 0.11,
        "two_n_maximum": 0.69,
        "minimum_edge_distance": 1.30,
    },
    "PJ": {
        "groove_pitch": 2.34,
        "groove_pitch_tolerance": 0.03,
        "transition_radius": 0.30,
        "transition_radius_tolerance": 0.05,
        "maximum_root_radius": 0.40,
        "checking_ball_or_rod_diameter": 1.50,
        "two_x_nominal": 0.23,
        "two_n_maximum": 0.81,
        "minimum_edge_distance": 1.80,
    },
    "PK": {
        "groove_pitch": 3.56,
        "groove_pitch_tolerance": 0.05,
        "transition_radius": 0.35,
        "transition_radius_tolerance": 0.10,
        "maximum_root_radius": 0.50,
        "checking_ball_or_rod_diameter": 2.50,
        "two_x_nominal": 0.99,
        "two_n_maximum": 1.68,
        "minimum_edge_distance": 2.50,
    },
    "PL": {
        "groove_pitch": 4.70,
        "groove_pitch_tolerance": 0.05,
        "transition_radius": 0.55,
        "transition_radius_tolerance": 0.15,
        "maximum_root_radius": 0.40,
        "checking_ball_or_rod_diameter": 3.50,
        "two_x_nominal": 2.36,
        "two_n_maximum": 3.50,
        "minimum_edge_distance": 3.30,
    },
    "PM": {
        "groove_pitch": 9.40,
        "groove_pitch_tolerance": 0.08,
        "transition_radius": 0.90,
        "transition_radius_tolerance": 0.15,
        "maximum_root_radius": 0.75,
        "checking_ball_or_rod_diameter": 7.00,
        "two_x_nominal": 4.53,
        "two_n_maximum": 5.92,
        "minimum_edge_distance": 6.40,
    },
}

_PROFILES: dict[str, dict[str, Any]] = {
    designation: {
        "designation": designation,
        "standard_system": "iso_9982_2021",
        "groove_angle_degrees": 40.0,
        "groove_angle_tolerance_degrees": 0.5,
        "cumulative_pitch_tolerance": 0.30,
        **deepcopy(dimensions),
        "source": deepcopy(_SOURCE),
    }
    for designation, dimensions in _PROFILE_ROWS.items()
}


def list_poly_v_profiles() -> dict[str, Any]:
    profiles = [deepcopy(_PROFILES[key]) for key in _PROFILES]
    return {
        "ok": True,
        "stage": "poly_v_profile_catalog",
        "standard_system": "iso_9982_2021",
        "profile_count": len(profiles),
        "profiles": profiles,
        "source": deepcopy(_SOURCE),
    }


def resolve_poly_v_profile(designation: str) -> dict[str, Any]:
    key = str(designation or "").strip().upper()
    if key not in _PROFILES:
        raise ValueError(
            f"Unknown Poly-V profile '{designation}'. Supported profiles: {', '.join(_PROFILES)}"
        )
    return deepcopy(_PROFILES[key])


def preview_poly_v_groove(
    designation: str,
    effective_diameter: float,
    groove_count: int = 1,
) -> dict[str, Any]:
    profile = resolve_poly_v_profile(designation)
    diameter = _positive_float("effective_diameter", effective_diameter)
    count = _positive_int("groove_count", groove_count, maximum=64)

    pitch = float(profile["groove_pitch"])
    angle = float(profile["groove_angle_degrees"])
    transition_radius = float(profile["transition_radius"])
    root_radius = float(profile["maximum_root_radius"])
    checking_diameter = float(profile["checking_ball_or_rod_diameter"])
    two_x = float(profile["two_x_nominal"])
    two_n_maximum = float(profile["two_n_maximum"])
    edge_distance = float(profile["minimum_edge_distance"])

    half_angle = math.radians(angle / 2.0)
    sin_half = math.sin(half_angle)
    cos_half = math.cos(half_angle)
    tan_half = math.tan(half_angle)
    fillet_apex_factor = 1.0 / sin_half - 1.0

    # K is the diameter over checking balls or rods.  ISO defines x and N as
    # half-differences from K.  For an external pulley K > de and K > do:
    # de = K - 2x; do = K - 2N.  N below is calculated from the selected
    # nominal rt profile and checked against the Table 2 maximum.
    two_n_geometry = (
        checking_diameter / sin_half
        + checking_diameter
        - pitch / tan_half
        + 2.0 * transition_radius * fillet_apex_factor
    )
    if two_n_geometry > two_n_maximum + 1e-9:
        raise ValueError("The selected nominal Poly-V tip geometry exceeds the ISO 9982 2N maximum")

    outer_diameter = diameter + two_x - two_n_geometry
    if outer_diameter <= 0.0:
        raise ValueError("effective_diameter is too small for the selected Poly-V profile")
    outer_radius = outer_diameter / 2.0

    sharp_root_apex_radius = (
        outer_radius
        + transition_radius * fillet_apex_factor
        - pitch / (2.0 * tan_half)
    )
    groove_root_radius = sharp_root_apex_radius + root_radius * fillet_apex_factor
    if groove_root_radius <= 0.0:
        raise ValueError("effective_diameter produces a non-positive Poly-V groove root radius")
    groove_depth = outer_radius - groove_root_radius
    if groove_depth <= 0.0:
        raise ValueError("The selected Poly-V profile does not produce a positive groove depth")

    face_width = (count - 1) * pitch + 2.0 * edge_distance
    first_center = -((count - 1) * pitch) / 2.0
    centers = [first_center + index * pitch for index in range(count)]
    grooves = [
        _build_rounded_groove(
            index=index + 1,
            center_x=center,
            pitch=pitch,
            outer_radius=outer_radius,
            sharp_root_apex_radius=sharp_root_apex_radius,
            transition_radius=transition_radius,
            root_radius=root_radius,
            half_angle=half_angle,
        )
        for index, center in enumerate(centers)
    ]
    wave_entities = [
        deepcopy(entity)
        for groove in grooves
        for entity in list(groove["profile_entities"])
    ]
    wave_start = list(grooves[0]["outer_points"][0])
    wave_end = list(grooves[-1]["outer_points"][1])
    closure_overshoot = max(0.10, pitch * 0.05)
    closure_radius = outer_radius + closure_overshoot
    cut_entities = [
        *wave_entities,
        _line_entity(
            "profile_right_overshoot",
            wave_end,
            [wave_end[0], closure_radius],
            role="operation_overshoot",
        ),
        _line_entity(
            "profile_top_closure",
            [wave_end[0], closure_radius],
            [wave_start[0], closure_radius],
            role="closure",
        ),
        _line_entity(
            "profile_left_overshoot",
            [wave_start[0], closure_radius],
            wave_start,
            role="operation_overshoot",
        ),
    ]
    sampled_polygon = _sample_cut_polygon(grooves, outer_radius)
    expected_removed_volume_mm3 = _revolved_polygon_volume_mm3(sampled_polygon)

    face_left = -face_width / 2.0
    face_right = face_width / 2.0
    warnings = [
        (
            "The deterministic profile uses nominal rt and the maximum permitted rb; "
            "ISO 9982 allows other compliant tip and root configurations."
        ),
        "The rotational-cut closure intentionally overshoots the blank radius and is clipped by the target body.",
        "Verify dimensions against a licensed ISO 9982:2021 copy for certified drawings.",
    ]

    return {
        "ok": True,
        "success": True,
        "stage": "preview",
        "operation": "poly_v_groove",
        "inputs": {
            "designation": profile["designation"],
            "effective_diameter": diameter,
            "groove_count": count,
            "standard_system": profile["standard_system"],
        },
        "profile": profile,
        "derived": {
            "groove_angle_degrees": angle,
            "effective_diameter": diameter,
            "datum_diameter": diameter,
            "checking_diameter_over_balls_or_rods": diameter + two_x,
            "outer_diameter": outer_diameter,
            "root_diameter": 2.0 * groove_root_radius,
            "groove_depth": groove_depth,
            "face_width": face_width,
            "groove_centers": centers,
            "two_n_geometry": two_n_geometry,
            "two_n_margin_to_maximum": two_n_maximum - two_n_geometry,
            "cad_closure_radial_overshoot": closure_overshoot,
            "expected_removed_volume_mm3": expected_removed_volume_mm3,
        },
        "geometry": {
            "coordinate_system": {"x": "axial", "y": "radius"},
            "grooves": grooves,
            "profile_entities": cut_entities,
            "profile_component_count": 1,
            "closed": True,
            "sampled_cut_polygon": sampled_polygon,
            "envelope": {
                "x_min": face_left,
                "x_max": face_right,
                "profile_x_min": wave_start[0],
                "profile_x_max": wave_end[0],
                "radius_min": groove_root_radius,
                "radius_max": outer_radius,
                "cut_profile_radius_max": closure_radius,
            },
        },
        "composition": {
            "contract_status": "implemented_layer_3",
            "preferred_mode": "cut_from_body",
            "target_requirements": {
                "axis_ref": "global_x",
                "outer_cylinder_diameter": outer_diameter,
                "minimum_axial_width": face_width,
                "preserve_material_below_radius": groove_root_radius,
            },
            "planned_semantic_outputs": [
                "member.body",
                "member.axis",
                "member.left_face",
                "member.right_face",
                "member.outer_rim",
                "member.pitch_surface",
                "member.functional_feature",
                "member.profile_sketch",
                "member.parameters",
            ],
            "excluded_features": ["hub", "bore", "keyway", "thread", "generic_chamfers"],
        },
        "assumptions": [
            {
                "field": "transition_radius",
                "value": transition_radius,
                "status": "iso_nominal",
            },
            {
                "field": "root_radius",
                "value": root_radius,
                "status": "iso_maximum_selected_as_deterministic_value",
            },
            {
                "field": "edge_distance",
                "value": edge_distance,
                "status": "iso_minimum_selected_as_nominal_face_layout",
            },
        ],
        "verification": {
            "profile_component_count": 1,
            "profile_closed": True,
            "two_n_within_iso_maximum": two_n_geometry <= two_n_maximum + 1e-9,
            "positive_removed_volume": expected_removed_volume_mm3 > 0.0,
        },
        "warnings": warnings,
        "source": deepcopy(_SOURCE),
    }


def build_poly_v_cut_plan(
    preview: dict[str, Any],
    *,
    axial_center: float = 0.0,
    name: str = "Poly-V grooves",
    parameter_base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(preview, dict) or preview.get("operation") != "poly_v_groove":
        raise ValueError("preview must be a successful poly_v_groove preview")
    if not preview.get("success"):
        raise ValueError("preview must be successful")
    center_offset = _finite_float("axial_center", axial_center)
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")
    if not isinstance(parameter_base, dict):
        raise ValueError("parameter_base is required for an executable Poly-V cut plan")
    outer_radius_variable = str(parameter_base.get("outer_radius_variable") or "").strip()
    face_width_variable = str(parameter_base.get("face_width_variable") or "").strip()
    if not outer_radius_variable or not face_width_variable:
        raise ValueError("parameter_base variable names must not be empty")

    source_entities = list((preview.get("geometry") or {}).get("profile_entities") or [])
    if not source_entities:
        raise ValueError("preview does not contain Poly-V profile entities")
    profile_entities = [_shift_entity(entity, center_offset) for entity in source_entities]

    envelope = dict((preview.get("geometry") or {}).get("envelope") or {})
    x_min = _finite_float("envelope x_min", envelope.get("x_min")) + center_offset
    x_max = _finite_float("envelope x_max", envelope.get("x_max")) + center_offset
    axis_margin = max(5.0, (x_max - x_min) * 0.1)
    axis_start = 0.0 if x_min >= 0.0 else x_min - axis_margin
    axis_end = 0.0 if x_max <= 0.0 else x_max + axis_margin
    axis = {
        "id": "rotation_axis",
        "kind": "line",
        "role": "construction",
        "style": 3,
        "start": [axis_start, 0.0],
        "end": [axis_end, 0.0],
    }

    derived = dict(preview.get("derived") or {})
    profile = dict(preview.get("profile") or {})
    outer_radius = float(derived["outer_diameter"]) / 2.0
    closure_overshoot = float(derived["cad_closure_radial_overshoot"])
    variables = [
        _variable("PV_OR", outer_radius, expression=outer_radius_variable, note="Composed blank outer radius"),
        _variable("PV_FACE_W", derived["face_width"], expression=face_width_variable, note="Composed blank face width"),
        _variable("PV_E", profile["groove_pitch"], note="Groove pitch"),
        _variable("PV_RT", profile["transition_radius"], note="Nominal groove transition radius"),
        _variable("PV_RB", profile["maximum_root_radius"], note="Selected groove root radius"),
        _variable("PV_DB", profile["checking_ball_or_rod_diameter"], note="Checking ball or rod diameter"),
        _variable("PV_2X", profile["two_x_nominal"], note="Nominal ISO 9982 two-x value"),
        _variable("PV_ALPHA", profile["groove_angle_degrees"], unit="deg", note="Included groove angle"),
        _variable("PV_COUNT", preview["inputs"]["groove_count"], unit="", note="Groove count"),
        _variable("PV_CENTER", center_offset, note="Groove-set axial center"),
        _variable("PV_AXIS_X0", axis_start, note="Fixed rotation-axis sketch datum"),
        _variable("PV_CLOSURE", closure_overshoot, note="Radial cut-profile closure overshoot"),
        _variable("PV_DO", derived["outer_diameter"], expression="2 * PV_OR", note="Pulley outer diameter"),
        _variable(
            "PV_2N",
            derived["two_n_geometry"],
            expression=(
                "PV_DB / sinD(PV_ALPHA / 2) + PV_DB - PV_E / tanD(PV_ALPHA / 2) "
                "+ 2 * PV_RT * (1 / sinD(PV_ALPHA / 2) - 1)"
            ),
            note="Actual two-N value of the parametric profile",
        ),
        _variable(
            "PV_DE",
            derived["effective_diameter"],
            expression="PV_DO - PV_2X + PV_2N",
            note="Poly-V effective diameter",
        ),
        _variable(
            "PV_DEPTH",
            derived["groove_depth"],
            expression=(
                "PV_E / (2 * tanD(PV_ALPHA / 2)) "
                "- (PV_RT + PV_RB) * (1 / sinD(PV_ALPHA / 2) - 1)"
            ),
            note="Rounded groove radial depth",
        ),
        _variable(
            "PV_ROOT_D",
            derived["root_diameter"],
            expression="2 * (PV_OR - PV_DEPTH)",
            note="Groove root diameter",
        ),
        _variable(
            "PV_F",
            profile["minimum_edge_distance"],
            expression="(PV_FACE_W - (PV_COUNT - 1) * PV_E) / 2",
            note="Actual rim edge distance derived from blank width and pitch",
        ),
    ]

    parameterization = _build_poly_v_parameterization_plan(
        preview,
        profile_entities,
        axial_center=center_offset,
        axis=axis,
        variables=variables,
    )
    constraints = parameterization["constraints"]
    pre_constraints = parameterization["pre_constraints"]
    dimensions = parameterization["dimensions"]
    construction_lines = parameterization["construction_lines"]

    designation = str(preview["inputs"]["designation"])
    groove_count = int(preview["inputs"]["groove_count"])
    custom_label = ""
    if requested_name.casefold() != "poly-v grooves":
        custom_label = f" - {requested_name}"
    entity_names = {
        "sketch": f"Poly-V grooves {designation} x{groove_count} profile{custom_label}",
        "cut": f"Poly-V grooves {designation} x{groove_count} cut rotation{custom_label}",
    }
    feature_name = entity_names["cut"]
    bridge_preview = {
        "geometry": {
            "profile_points": [],
            "profile_entities": profile_entities,
            "axis": axis,
            "construction_entities": construction_lines,
        },
        "variables": variables,
        "projections": [],
        "pre_constraints": pre_constraints,
        "constraints": constraints,
        "dimensions": dimensions,
        "operations": [
            {"operation": "draw_axis", "start": axis["start"], "end": axis["end"]},
            {
                "operation": "draw_profile",
                "profile_entities": profile_entities,
                "construction_lines": construction_lines,
            },
            {"operation": "add_variables", "variables": variables},
            {"operation": "apply_pre_constraints", "constraints": pre_constraints},
            {"operation": "apply_constraints", "constraints": constraints},
            {"operation": "add_dimensions", "dimensions": dimensions},
            {"operation": "cut_rotation"},
        ],
    }
    params = {
        "name": feature_name,
        "total_length": x_max - x_min,
        "angle_degrees": 360.0,
        "profile_line_style": 1,
        "axis_line_style": 3,
        "expected_profile_component_count": 1,
        "max_removed_volume_error_ratio": 0.05,
        "rotation_axis_default_object_type": 71,
        "require_explicit_rotation_axis": True,
        "verify_profile_after_parameterization": True,
        "require_parameterization": True,
        "require_fully_defined": True,
        "require_all_constraints_applied": True,
        "profile_sketch_target_state": "fully_defined",
        "sketch": {
            "constraints": {"enabled": True},
            "dimensions": {"enabled": True, "driving": True},
            "parameterization_order": "staged",
            "deferred_dimension_kinds": ["angle_between_lines"],
            "preflight_after_update": True,
            "require_exact_counts": True,
            "expected_constraint_count": len(constraints),
            "expected_dimension_count": len(dimensions),
        },
        "variables": variables,
        "projections": [],
        "base_mode": "origin_variables",
        "pre_constraints": pre_constraints,
        "constraints": constraints,
        "dimensions": dimensions,
    }

    return {
        "ok": True,
        "stage": "poly_v_groove_cad_plan",
        "plan_version": 1,
        "operation": "cut_rotation",
        "axis": "global_x",
        "axial_center": center_offset,
        "name": feature_name,
        "requested_name": requested_name,
        "entity_names": entity_names,
        "groove_count": groove_count,
        "profile_component_count": 1,
        "profile_entity_count": len(profile_entities),
        "expected_removed_volume_mm3": derived["expected_removed_volume_mm3"],
        "expected_removed_volume_cm3": float(derived["expected_removed_volume_mm3"]) / 1000.0,
        "profile_rounding": {
            "mode": "sketch_arcs",
            "transition_radius": profile["transition_radius"],
            "root_radius": profile["maximum_root_radius"],
        },
        "params": params,
        "bridge_preview": bridge_preview,
        "parameterization": parameterization["summary"],
        "preflight": {
            "required_body_count": 1,
            "required_axis": "global_x",
            "required_outer_diameter": derived["outer_diameter"],
            "required_axial_interval": [x_min, x_max],
            "minimum_material_radius": float(derived["root_diameter"]) / 2.0,
        },
        "planned_outputs": list(preview["composition"]["planned_semantic_outputs"]),
    }


def _build_poly_v_parameterization_plan(
    preview: dict[str, Any],
    profile_entities: list[dict[str, Any]],
    *,
    axial_center: float,
    axis: dict[str, Any],
    variables: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build one driving rounded groove and a constrained dependent family."""

    derived = dict(preview.get("derived") or {})
    groove_count = int((preview.get("inputs") or {}).get("groove_count") or 0)
    if groove_count < 1:
        raise ValueError("Poly-V parameterization requires at least one groove")

    entity_by_target = {str(entity["target"]): entity for entity in profile_entities}
    outer_radius = float(derived["outer_diameter"]) / 2.0
    face_width = float(derived["face_width"])
    pitch = float((preview.get("profile") or {})["groove_pitch"])
    transition_radius = float((preview.get("profile") or {})["transition_radius"])
    root_radius = float((preview.get("profile") or {})["maximum_root_radius"])
    closure_overshoot = float(derived["cad_closure_radial_overshoot"])
    axis_start_x = float(axis["start"][0])

    construction_lines: list[dict[str, Any]] = [
        {
            "id": "blank_face_datum",
            "target": "blank_face_datum",
            "kind": "line",
            "role": "blank_face_datum",
            "style": 2,
            "start": [axial_center - face_width / 2.0, outer_radius],
            "end": [axial_center + face_width / 2.0, outer_radius],
        },
        {
            "id": "groove_set_centerline",
            "target": "groove_set_centerline",
            "kind": "line",
            "role": "groove_set_centerline",
            "style": 2,
            "start": [axial_center, 0.0],
            "end": [axial_center, outer_radius],
        },
        {
            "id": "groove_set_center_locator",
            "target": "groove_set_center_locator",
            "kind": "line",
            "role": "groove_set_center_locator",
            "style": 2,
            "start": [axis_start_x, 0.0],
            "end": [axial_center, 0.0],
        },
    ]

    for groove_index in range(1, groove_count + 1):
        left_transition = entity_by_target[f"groove_{groove_index}_left_transition"]
        right_transition = entity_by_target[f"groove_{groove_index}_right_transition"]
        root = entity_by_target[f"groove_{groove_index}_root"]
        left_outer = list(left_transition["start"])
        right_outer = list(right_transition["end"])
        root_center = list(root["center"])
        groove_center_x = (float(left_outer[0]) + float(right_outer[0])) / 2.0
        pitch_seed_offset = 0.15 + 0.02 * groove_index
        construction_lines.extend(
            [
                {
                    "id": f"groove_{groove_index}_pitch_span",
                    "target": f"groove_{groove_index}_pitch_span",
                    "kind": "line",
                    "role": "groove_pitch_span",
                    "style": 2,
                    "start": [
                        float(left_outer[0]) - 0.2 * pitch_seed_offset,
                        float(left_outer[1]) + pitch_seed_offset,
                    ],
                    "end": [
                        float(right_outer[0]) + 0.3 * pitch_seed_offset,
                        float(right_outer[1]) - pitch_seed_offset,
                    ],
                },
                {
                    "id": f"groove_{groove_index}_centerline",
                    "target": f"groove_{groove_index}_centerline",
                    "kind": "line",
                    "role": "groove_centerline",
                    "style": 2,
                    "start": root_center,
                    "end": [groove_center_x, outer_radius],
                },
            ]
        )

    pre_constraints: list[dict[str, Any]] = [
        {"kind": "fixed_point", "target": "axis", "index": 0},
        {"kind": "fixed_point", "target": "axis", "index": 1},
        {
            "kind": "merge_points",
            "target": "groove_set_center_locator",
            "index": 0,
            "partner": "axis",
            "partner_index": 0,
        },
        {
            "kind": "merge_points",
            "target": "groove_set_center_locator",
            "index": 1,
            "partner": "groove_set_centerline",
            "partner_index": 0,
        },
    ]
    for left, right in zip(profile_entities, profile_entities[1:]):
        pre_constraints.append(
            {
                "kind": "merge_points",
                "target": str(left["target"]),
                "index": 2 if left["kind"] == "arc" else 1,
                "partner": str(right["target"]),
                "partner_index": 1 if right["kind"] == "arc" else 0,
            }
        )
    pre_constraints.append(
        {
            "kind": "merge_points",
            "target": str(profile_entities[-1]["target"]),
            "index": 1,
            "partner": str(profile_entities[0]["target"]),
            "partner_index": 1,
        }
    )
    for groove_index in range(1, groove_count + 1):
        pitch_span = f"groove_{groove_index}_pitch_span"
        centerline = f"groove_{groove_index}_centerline"
        root = f"groove_{groove_index}_root"
        pre_constraints.extend(
            [
                {
                    "kind": "merge_points",
                    "target": centerline,
                    "index": 0,
                    "partner": root,
                    "partner_index": 0,
                },
            ]
        )

    constraints: list[dict[str, Any]] = [
        {"kind": "horizontal", "target": "blank_face_datum"},
        {"kind": "vertical", "target": "groove_set_centerline"},
        {
            "kind": "point_on_curve",
            "target": "groove_set_centerline",
            "index": 0,
            "partner": "axis",
        },
        {
            "kind": "point_on_curve_middle",
            "target": "groove_set_centerline",
            "index": 1,
            "partner": "blank_face_datum",
        },
        {
            "kind": "equal_length",
            "target": "groove_1_right_flank",
            "partner": "groove_1_left_flank",
        },
    ]
    for groove_index in range(1, groove_count + 1):
        pitch_span = f"groove_{groove_index}_pitch_span"
        centerline = f"groove_{groove_index}_centerline"
        left_transition = f"groove_{groove_index}_left_transition"
        left_flank = f"groove_{groove_index}_left_flank"
        root = f"groove_{groove_index}_root"
        right_flank = f"groove_{groove_index}_right_flank"
        right_transition = f"groove_{groove_index}_right_transition"
        constraints.extend(
            [
                {"kind": "horizontal", "target": pitch_span},
                {"kind": "vertical", "target": centerline},
                {
                    "kind": "point_on_curve_middle",
                    "target": centerline,
                    "index": 1,
                    "partner": pitch_span,
                },
                {
                    "kind": "h_align_points",
                    "target": pitch_span,
                    "index": 0,
                    "partner": left_transition,
                    "partner_index": 1,
                },
                {
                    "kind": "v_align_points",
                    "target": pitch_span,
                    "index": 0,
                    "partner": left_transition,
                    "partner_index": 1,
                },
                {
                    "kind": "h_align_points",
                    "target": pitch_span,
                    "index": 1,
                    "partner": right_transition,
                    "partner_index": 2,
                },
                {
                    "kind": "v_align_points",
                    "target": pitch_span,
                    "index": 1,
                    "partner": right_transition,
                    "partner_index": 2,
                },
                {
                    "kind": "v_align_points",
                    "target": left_transition,
                    "index": 0,
                    "partner": pitch_span,
                    "partner_index": 0,
                },
                {
                    "kind": "v_align_points",
                    "target": right_transition,
                    "index": 0,
                    "partner": pitch_span,
                    "partner_index": 1,
                },
                {"kind": "tangent", "target": left_transition, "partner": left_flank},
                {"kind": "tangent", "target": left_flank, "partner": root},
                {"kind": "tangent", "target": root, "partner": right_flank},
                {"kind": "tangent", "target": right_flank, "partner": right_transition},
            ]
        )
        if groove_index > 1:
            constraints.extend(
                [
                    {
                        "kind": "equal_length",
                        "target": pitch_span,
                        "partner": "groove_1_pitch_span",
                    },
                    {
                        "kind": "parallel",
                        "target": left_flank,
                        "partner": "groove_1_left_flank",
                    },
                    {
                        "kind": "parallel",
                        "target": right_flank,
                        "partner": "groove_1_right_flank",
                    },
                    {"kind": "equal_radius", "target": root, "partner": "groove_1_root"},
                ]
            )
        transition = right_transition if groove_index == 1 else left_transition
        constraints.append(
            {
                "kind": "equal_radius",
                "target": transition,
                "partner": "groove_1_left_transition",
            }
        )

    if groove_count % 2:
        constraints.append(
            {
                "kind": "point_on_curve_middle",
                "target": "groove_set_centerline",
                "index": 1,
                "partner": f"groove_{(groove_count + 1) // 2}_pitch_span",
            }
        )
    else:
        constraints.extend(
            [
                {
                    "kind": "h_align_points",
                    "target": "groove_set_centerline",
                    "index": 1,
                    "partner": f"groove_{groove_count // 2}_pitch_span",
                    "partner_index": 1,
                },
                {
                    "kind": "v_align_points",
                    "target": "groove_set_centerline",
                    "index": 1,
                    "partner": f"groove_{groove_count // 2}_pitch_span",
                    "partner_index": 1,
                },
            ]
        )
    constraints.extend(
        [
            {"kind": "vertical", "target": "profile_right_overshoot"},
            {"kind": "horizontal", "target": "profile_top_closure"},
            {"kind": "vertical", "target": "profile_left_overshoot"},
            {
                "kind": "equal_length",
                "target": "profile_right_overshoot",
                "partner": "profile_left_overshoot",
            },
        ]
    )

    dimensions: list[dict[str, Any]] = [
        {
            "kind": "line_length",
            "target": "blank_face_datum",
            "name": "PV_FACE_W_DIM",
            "variable_name": "PV_FACE_W",
            "value": face_width,
            "driving": True,
        },
        {
            "kind": "line_length",
            "target": "groove_set_centerline",
            "name": "PV_OR_DIM",
            "variable_name": "PV_OR",
            "value": outer_radius,
            "driving": True,
        },
        {
            "kind": "line_length",
            "target": "groove_set_center_locator",
            "name": "PV_CENTER_DIM",
            "expression": "PV_CENTER - PV_AXIS_X0",
            "value": axial_center - axis_start_x,
            "driving": True,
        },
        {
            "kind": "line_length",
            "target": "groove_1_pitch_span",
            "name": "PV_E_DIM",
            "variable_name": "PV_E",
            "value": pitch,
            "driving": True,
        },
        {
            "kind": "arc_radius",
            "target": "groove_1_left_transition",
            "name": "PV_RT_DIM",
            "variable_name": "PV_RT",
            "value": transition_radius,
            "driving": True,
        },
        {
            "kind": "arc_radius",
            "target": "groove_1_root",
            "name": "PV_RB_DIM",
            "variable_name": "PV_RB",
            "value": root_radius,
            "driving": True,
        },
        {
            "kind": "line_length",
            "target": "profile_left_overshoot",
            "name": "PV_CLOSURE_DIM",
            "variable_name": "PV_CLOSURE",
            "value": closure_overshoot,
            "driving": True,
        },
        {
            "kind": "angle_between_lines",
            "target": "groove_1_left_flank",
            "partner": "axis",
            "name": "PV_ALPHA_LEFT_DIM",
            "expression": "90 - PV_ALPHA / 2",
            "value": 90.0 - float((preview.get("profile") or {})["groove_angle_degrees"]) / 2.0,
            "driving": True,
        },
    ]

    return {
        "variables": variables,
        "pre_constraints": pre_constraints,
        "constraints": constraints,
        "dimensions": dimensions,
        "construction_lines": construction_lines,
        "summary": {
            "variable_count": len(variables),
            "semantic_variable_count": len(variables),
            "dimension_variable_count": sum(1 for item in dimensions if item.get("driving")),
            "constraint_count": len(constraints),
            "pre_constraint_count": len(pre_constraints),
            "dimension_count": len(dimensions),
            "projection_count": 0,
            "axis_line_count": 1,
            "auxiliary_line_count": len(construction_lines),
            "target_state": "fully_defined",
            "base_mode": "parametric_master_dependent",
            "master_groove": 1,
            "dependent_groove_count": groove_count - 1,
        },
    }


def validate_poly_v_cut_target(
    plan: dict[str, Any],
    target: dict[str, Any],
    *,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("stage") != "poly_v_groove_cad_plan":
        raise ValueError("plan must be a poly_v_groove_cad_plan")
    if not isinstance(target, dict):
        raise ValueError("target must be an object")
    if target.get("axis") != "global_x":
        raise ValueError("target axis must be 'global_x'")
    if _positive_int("target.body_count", target.get("body_count"), maximum=1) != 1:
        raise ValueError("target.body_count must be 1")

    parameter_base = target.get("parameter_base")
    if not isinstance(parameter_base, dict):
        raise ValueError("target.parameter_base must be an object")
    outer_radius_variable = str(parameter_base.get("outer_radius_variable") or "").strip()
    face_width_variable = str(parameter_base.get("face_width_variable") or "").strip()
    if not outer_radius_variable or not face_width_variable:
        raise ValueError("target.parameter_base variable names must not be empty")
    variable_links = {
        str(item.get("name")): item.get("expression")
        for item in (plan.get("params") or {}).get("variables") or []
    }
    if variable_links.get("PV_OR") != outer_radius_variable:
        raise ValueError("plan PV_OR link does not match target.parameter_base")
    if variable_links.get("PV_FACE_W") != face_width_variable:
        raise ValueError("plan PV_FACE_W link does not match target.parameter_base")

    outer_diameter = _positive_float("target.outer_diameter", target.get("outer_diameter"))
    axial_min = _finite_float("target.axial_min", target.get("axial_min"))
    axial_max = _finite_float("target.axial_max", target.get("axial_max"))
    if axial_max <= axial_min:
        raise ValueError("target.axial_max must be greater than target.axial_min")
    preflight = dict(plan.get("preflight") or {})
    required_diameter = float(preflight.get("required_outer_diameter") or 0.0)
    if abs(outer_diameter - required_diameter) > tolerance:
        raise ValueError("target outer_diameter does not match the Poly-V groove plan")
    required_interval = list(preflight.get("required_axial_interval") or [])
    if len(required_interval) != 2:
        raise ValueError("plan required_axial_interval is invalid")
    if axial_min > float(required_interval[0]) + tolerance or axial_max < float(required_interval[1]) - tolerance:
        raise ValueError("target axial interval does not contain the planned Poly-V face interval")

    return {
        "ok": True,
        "stage": "poly_v_target_preflight",
        "body_count": 1,
        "axis": "global_x",
        "outer_diameter": outer_diameter,
        "required_outer_diameter": required_diameter,
        "axial_interval": [axial_min, axial_max],
        "required_axial_interval": required_interval,
        "parameter_base": {
            "outer_radius_variable": outer_radius_variable,
            "face_width_variable": face_width_variable,
        },
    }


def _build_rounded_groove(
    *,
    index: int,
    center_x: float,
    pitch: float,
    outer_radius: float,
    sharp_root_apex_radius: float,
    transition_radius: float,
    root_radius: float,
    half_angle: float,
) -> dict[str, Any]:
    sin_half = math.sin(half_angle)
    cos_half = math.cos(half_angle)
    left_crest_x = center_x - pitch / 2.0
    right_crest_x = center_x + pitch / 2.0
    crest_center_y = outer_radius - transition_radius
    crest_tangent_y = crest_center_y + transition_radius * sin_half
    root_center_y = sharp_root_apex_radius + root_radius / sin_half
    root_tangent_y = root_center_y - root_radius * sin_half

    left_outer = [left_crest_x, outer_radius]
    left_crest_tangent = [left_crest_x + transition_radius * cos_half, crest_tangent_y]
    left_root_tangent = [center_x - root_radius * cos_half, root_tangent_y]
    right_root_tangent = [center_x + root_radius * cos_half, root_tangent_y]
    right_crest_tangent = [right_crest_x - transition_radius * cos_half, crest_tangent_y]
    right_outer = [right_crest_x, outer_radius]
    prefix = f"groove_{index}"
    entities = [
        _arc_entity(
            f"{prefix}_left_transition",
            [left_crest_x, crest_center_y],
            transition_radius,
            left_outer,
            left_crest_tangent,
            direction=True,
            role="tip_transition",
        ),
        _line_entity(
            f"{prefix}_left_flank",
            left_crest_tangent,
            left_root_tangent,
            role="flank",
        ),
        _arc_entity(
            f"{prefix}_root",
            [center_x, root_center_y],
            root_radius,
            left_root_tangent,
            right_root_tangent,
            direction=False,
            role="groove_root",
        ),
        _line_entity(
            f"{prefix}_right_flank",
            right_root_tangent,
            right_crest_tangent,
            role="flank",
        ),
        _arc_entity(
            f"{prefix}_right_transition",
            [right_crest_x, crest_center_y],
            transition_radius,
            right_crest_tangent,
            right_outer,
            direction=True,
            role="tip_transition",
        ),
    ]
    return {
        "index": index,
        "center_x": center_x,
        "outer_points": [left_outer, right_outer],
        "tangent_points": {
            "left_crest": left_crest_tangent,
            "left_root": left_root_tangent,
            "right_root": right_root_tangent,
            "right_crest": right_crest_tangent,
        },
        "profile_entities": entities,
    }


def _sample_cut_polygon(
    grooves: list[dict[str, Any]],
    outer_radius: float,
    *,
    arc_segments: int = 24,
) -> list[list[float]]:
    points: list[list[float]] = []
    for groove in grooves:
        entities = list(groove["profile_entities"])
        for entity in entities:
            if entity["kind"] == "line":
                if not points:
                    points.append(list(entity["start"]))
                points.append(list(entity["end"]))
                continue
            center = entity["center"]
            start = entity["start"]
            end = entity["end"]
            start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
            end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
            clockwise = bool(entity["direction"])
            if clockwise:
                while end_angle >= start_angle:
                    end_angle -= 2.0 * math.pi
            else:
                while end_angle <= start_angle:
                    end_angle += 2.0 * math.pi
            if not points:
                points.append(list(start))
            for segment in range(1, arc_segments + 1):
                ratio = segment / arc_segments
                angle = start_angle + (end_angle - start_angle) * ratio
                points.append(
                    [
                        float(center[0]) + float(entity["radius"]) * math.cos(angle),
                        float(center[1]) + float(entity["radius"]) * math.sin(angle),
                    ]
                )
    if not points:
        raise ValueError("Poly-V profile sampling produced no points")
    points.append([points[0][0], outer_radius])
    return points


def _arc_entity(
    target: str,
    center: list[float],
    radius: float,
    start: list[float],
    end: list[float],
    *,
    direction: bool,
    role: str,
) -> dict[str, Any]:
    return {
        "id": target,
        "target": target,
        "kind": "arc",
        "role": role,
        "style": 1,
        "center": list(center),
        "radius": float(radius),
        "start": list(start),
        "end": list(end),
        "direction": bool(direction),
    }


def _line_entity(target: str, start: list[float], end: list[float], *, role: str) -> dict[str, Any]:
    return {
        "id": target,
        "target": target,
        "kind": "line",
        "role": role,
        "style": 1,
        "start": list(start),
        "end": list(end),
    }


def _shift_entity(entity: dict[str, Any], offset: float) -> dict[str, Any]:
    shifted = deepcopy(entity)
    for field in ("start", "end", "center"):
        point = shifted.get(field)
        if isinstance(point, list) and len(point) == 2:
            shifted[field] = [float(point[0]) + offset, float(point[1])]
    return shifted


def _variable(
    name: str,
    value: Any,
    *,
    expression: str | None = None,
    unit: str = "mm",
    note: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": float(value),
        "expression": expression,
        "unit": unit,
        "note": note,
    }


def _positive_float(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return number


def _finite_float(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _positive_int(name: str, value: Any, *, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if number != value or number <= 0 or number > maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return number


def _revolved_polygon_volume_mm3(polygon: list[list[float]]) -> float:
    signed_twice_area = 0.0
    centroid_y_numerator = 0.0
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        cross = point[0] * next_point[1] - next_point[0] * point[1]
        signed_twice_area += cross
        centroid_y_numerator += (point[1] + next_point[1]) * cross
    if abs(signed_twice_area) <= 1e-12:
        raise ValueError("Poly-V cut profile has zero area")
    signed_area = signed_twice_area / 2.0
    centroid_y = centroid_y_numerator / (3.0 * signed_twice_area)
    if centroid_y <= 0.0:
        raise ValueError("Poly-V cut profile centroid must have positive radius")
    return abs(signed_area) * 2.0 * math.pi * centroid_y
