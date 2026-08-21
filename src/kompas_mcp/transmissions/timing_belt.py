from __future__ import annotations

import math
from typing import Any, Literal


TimingProfileDesignation = Literal["T2.5", "T5", "T10", "AT5", "HTD_3M", "HTD_5M", "HTD_8M", "CUSTOM"]
TimingProfileShape = Literal["trapezoidal", "curvilinear"]


_SOURCE_URL = "https://github.com/JustCuzRobotics/Pulley_Generator/blob/main/Pulley_T-MXL-XL-HTD-GT2_N-tooth.scad"
_PROFILES: dict[str, dict[str, Any]] = {
    "T2.5": {"shape": "trapezoidal", "pitch": 2.5, "groove_depth": 0.70, "groove_width": 1.678, "pitch_line_offset": 0.30, "tip_radius": 0.12, "root_fillet_radius": 0.12},
    "T5": {"shape": "trapezoidal", "pitch": 5.0, "groove_depth": 1.19, "groove_width": 3.264, "pitch_line_offset": 0.60, "tip_radius": 0.41, "root_fillet_radius": 0.41},
    "T10": {"shape": "trapezoidal", "pitch": 10.0, "groove_depth": 2.50, "groove_width": 6.130, "pitch_line_offset": 0.93, "tip_radius": 0.60, "root_fillet_radius": 0.60},
    "AT5": {"shape": "trapezoidal", "pitch": 5.0, "groove_depth": 1.19, "groove_width": 4.268, "pitch_line_offset": 0.60, "tip_radius": 0.53, "root_fillet_radius": 0.40},
    "HTD_3M": {"shape": "curvilinear", "pitch": 3.0, "groove_depth": 1.289, "groove_width": 2.270, "pitch_line_offset": 0.381, "tip_radius": 0.25, "root_fillet_radius": 0.86},
    "HTD_5M": {"shape": "curvilinear", "pitch": 5.0, "groove_depth": 2.199, "groove_width": 3.781, "pitch_line_offset": 0.5715, "tip_radius": 0.43, "root_fillet_radius": 1.50},
    "HTD_8M": {"shape": "curvilinear", "pitch": 8.0, "groove_depth": 3.607, "groove_width": 6.603, "pitch_line_offset": 0.6858, "tip_radius": 0.76, "root_fillet_radius": 2.60},
}


def list_timing_belt_profiles() -> dict[str, Any]:
    return {
        "profiles": [dict({"designation": designation, "source": _SOURCE_URL, "status": "preview_reference"}, **profile) for designation, profile in _PROFILES.items()],
        "custom_supported": True,
        "automotive_profiles": "supplier_data_required",
    }


def _positive(name: str, value: Any) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _polar(radius: float, angle: float) -> list[float]:
    return [radius * math.sin(angle), radius * math.cos(angle)]


def _rounded_polyline(
    points: list[tuple[float, float]],
    radii: list[float],
    roles: list[dict[str, Any] | None],
) -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:
    fillets: list[dict[str, Any] | None] = [None] * len(points)
    for index in range(1, len(points) - 1):
        radius = radii[index]
        if radius <= 0.0:
            continue
        previous, vertex, following = points[index - 1], points[index], points[index + 1]
        previous_vector = (previous[0] - vertex[0], previous[1] - vertex[1])
        following_vector = (following[0] - vertex[0], following[1] - vertex[1])
        previous_length = math.hypot(*previous_vector)
        following_length = math.hypot(*following_vector)
        if previous_length <= 1e-9 or following_length <= 1e-9:
            raise ValueError("timing profile contains a zero-length segment")
        previous_unit = (previous_vector[0] / previous_length, previous_vector[1] / previous_length)
        following_unit = (following_vector[0] / following_length, following_vector[1] / following_length)
        cosine = max(-1.0, min(1.0, previous_unit[0] * following_unit[0] + previous_unit[1] * following_unit[1]))
        angle = math.acos(cosine)
        if angle <= 1e-6 or abs(math.pi - angle) <= 1e-6:
            raise ValueError("timing profile fillet requires a finite corner angle")
        tangent_distance = radius / math.tan(angle / 2.0)
        bisector = (previous_unit[0] + following_unit[0], previous_unit[1] + following_unit[1])
        bisector_length = math.hypot(*bisector)
        center_distance = radius / math.sin(angle / 2.0)
        center = (
            vertex[0] + bisector[0] / bisector_length * center_distance,
            vertex[1] + bisector[1] / bisector_length * center_distance,
        )
        fillets[index] = {
            "radius": radius,
            "distance": tangent_distance,
            "start": (vertex[0] + previous_unit[0] * tangent_distance, vertex[1] + previous_unit[1] * tangent_distance),
            "end": (vertex[0] + following_unit[0] * tangent_distance, vertex[1] + following_unit[1] * tangent_distance),
            "center": center,
            **dict(roles[index] or {}),
        }

    for index in range(len(points) - 1):
        segment_length = math.dist(points[index], points[index + 1])
        consumed = float((fillets[index] or {}).get("distance", 0.0)) + float((fillets[index + 1] or {}).get("distance", 0.0))
        if consumed >= segment_length - 1e-7:
            raise ValueError("timing profile radii overlap on a flank or tooth surface")

    result: list[tuple[float, float]] = [points[0]]
    annotations: list[dict[str, Any]] = []
    for index in range(1, len(points) - 1):
        fillet = fillets[index]
        if fillet is None:
            result.append(points[index])
            continue
        start = fillet["start"]
        end = fillet["end"]
        center = fillet["center"]
        start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
        end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
        sweep = (end_angle - start_angle + math.pi) % (2.0 * math.pi) - math.pi
        arc = [
            (
                center[0] + fillet["radius"] * math.cos(start_angle + sweep * sample / 12.0),
                center[1] + fillet["radius"] * math.sin(start_angle + sweep * sample / 12.0),
            )
            for sample in range(13)
        ]
        result.extend(arc if math.dist(result[-1], arc[0]) > 1e-9 else arc[1:])
        annotations.append(
            {
                **{key: value for key, value in fillet.items() if key not in {"distance", "start", "end", "center"}},
                "vertex_index": index,
                "start": start,
                "end": end,
                "sweep": sweep,
                "center": center,
                "anchor": arc[6],
                "anchor_start": arc[3],
                "anchor_end": arc[9],
            }
        )
    result.append(points[-1])
    return result, annotations


def _tip_transition(
    tip: tuple[float, float],
    root: tuple[float, float],
    *,
    outside_radius: float,
    radius: float,
) -> dict[str, Any]:
    dx, dy = root[0] - tip[0], root[1] - tip[1]
    flank_length = math.hypot(dx, dy)
    if flank_length <= 1e-9:
        raise ValueError("timing profile tip transition requires a finite flank")
    direction = (dx / flank_length, dy / flank_length)
    normal = (-direction[1], direction[0])
    center_radius = outside_radius - radius
    if center_radius <= 0.0:
        raise ValueError("timing profile tip radius must be smaller than outside radius")
    normal_angle = math.atan2(normal[1], normal[0])
    side = -1.0 if tip[0] < 0.0 else 1.0
    candidates: list[dict[str, Any]] = []
    for signed_distance in (-radius, radius):
        cosine = (normal[0] * tip[0] + normal[1] * tip[1] + signed_distance) / center_radius
        if abs(cosine) > 1.0:
            continue
        offset = math.acos(max(-1.0, min(1.0, cosine)))
        for angle in (normal_angle + offset, normal_angle - offset):
            center = (center_radius * math.cos(angle), center_radius * math.sin(angle))
            distance = normal[0] * (center[0] - tip[0]) + normal[1] * (center[1] - tip[1])
            tangent = (center[0] - normal[0] * distance, center[1] - normal[1] * distance)
            flank_fraction = (
                (tangent[0] - tip[0]) * direction[0] + (tangent[1] - tip[1]) * direction[1]
            ) / flank_length
            outer = (center[0] * outside_radius / center_radius, center[1] * outside_radius / center_radius)
            if -1e-9 <= flank_fraction <= 1.0 + 1e-9 and side * outer[0] > side * tip[0]:
                candidates.append(
                    {
                        "center": center,
                        "outer": outer,
                        "tangent": tangent,
                        "flank_fraction": flank_fraction,
                        "distance_from_sharp_tip": math.dist(outer, tip),
                    }
                )
    if not candidates:
        raise ValueError("timing profile tip radius does not fit between the outside circle and flank")
    selected = min(candidates, key=lambda item: float(item["distance_from_sharp_tip"]))
    start_angle = math.atan2(selected["outer"][1] - selected["center"][1], selected["outer"][0] - selected["center"][0])
    end_angle = math.atan2(selected["tangent"][1] - selected["center"][1], selected["tangent"][0] - selected["center"][0])
    selected["sweep"] = (end_angle - start_angle + math.pi) % (2.0 * math.pi) - math.pi
    return selected


def _profile_segment(entity_id: str, start: tuple[float, float], end: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": entity_id,
        "kind": "segment",
        "role": "primary_groove_contour",
        "start": list(start),
        "end": list(end),
        "line_style": 1,
    }


def _profile_arc(
    entity_id: str,
    center: tuple[float, float],
    radius: float,
    start: tuple[float, float],
    end: tuple[float, float],
    sweep: float,
    annotation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entity = {
        "id": entity_id,
        "kind": "arc",
        "role": "primary_groove_contour",
        "center": list(center),
        "radius": float(radius),
        "start": list(start),
        "end": list(end),
        # KOMPAS IArc.Direction uses the inverse sense of mathematical sweep.
        "direction": bool(float(sweep) < 0.0),
        "line_style": 1,
    }
    if annotation:
        entity["fillet"] = dict(annotation)
    return entity


def _timing_variable(
    name: str,
    value: float,
    *,
    note: str,
    expression: str | None = None,
    unit: str = "mm",
) -> dict[str, Any]:
    return {
        "name": name,
        "value": float(value),
        "expression": expression,
        "unit": unit,
        "note": note,
    }


def _build_trapezoidal_parameterization(
    *,
    groove_entities: list[dict[str, Any]],
    sharp_tip_left: tuple[float, float],
    sharp_tip_right: tuple[float, float],
    sharp_root_left: tuple[float, float],
    sharp_root_right: tuple[float, float],
    outside_radius: float,
    root_radius: float,
    tip_radius: float,
    root_fillet_radius: float,
    closure_overshoot: float,
    pitch: float,
    tooth_count: int,
    face_width: float,
    pitch_line_offset: float,
    groove_depth: float,
) -> dict[str, Any]:
    mouth_width = abs(sharp_tip_right[0] - sharp_tip_left[0])
    root_width = abs(sharp_root_right[0] - sharp_root_left[0])
    root_width_ratio = root_width / mouth_width
    outside_diameter = outside_radius * 2.0
    variables = [
        _timing_variable("TB_P", pitch, note="Timing-belt tooth pitch"),
        _timing_variable("TB_Z", tooth_count, note="Timing-pulley tooth count", unit="unitless"),
        _timing_variable("TB_B", face_width, note="Timing-pulley face width"),
        _timing_variable("TB_PL", pitch_line_offset, note="Pitch-line radial offset"),
        _timing_variable(
            "TB_DA",
            outside_diameter,
            expression="TB_P * TB_Z / 3.141592653589793 - 2 * TB_PL",
            note="Outside diameter",
        ),
        _timing_variable("TB_OR", outside_radius, expression="TB_DA / 2", note="Outside radius"),
        _timing_variable("TB_H", groove_depth, note="Groove radial depth"),
        _timing_variable("TB_RR", root_radius, expression="TB_OR - TB_H", note="Root radius"),
        _timing_variable("TB_W", mouth_width, note="Sharp groove-mouth chord width"),
        _timing_variable(
            "TB_RW",
            root_width,
            expression=f"{root_width_ratio:.15g} * TB_W",
            note="Sharp groove-root chord width",
        ),
        _timing_variable("TB_RT", tip_radius, note="Retained-tooth transition radius"),
        _timing_variable("TB_RF", root_fillet_radius, note="Groove-root fillet radius"),
        _timing_variable("TB_CO", closure_overshoot, note="Cut-contour radial closure overshoot"),
        _timing_variable("TB_SPAN", 360.0, note="Circular pattern span", unit="deg"),
        _timing_variable(
            "TB_STEP",
            360.0 / float(tooth_count),
            expression="TB_SPAN / TB_Z",
            note="Circular pattern angular step",
            unit="deg",
        ),
    ]

    auxiliary_entities = [
        {
            "id": "timing_outer_datum",
            "kind": "circle",
            "role": "parameterization_datum",
            "center": [0.0, 0.0],
            "radius": outside_radius,
            "line_style": 2,
        },
        {
            "id": "timing_root_datum",
            "kind": "circle",
            "role": "parameterization_datum",
            "center": [0.0, 0.0],
            "radius": root_radius,
            "line_style": 2,
        },
        _profile_segment("timing_tip_span", sharp_tip_left, sharp_tip_right),
        _profile_segment("timing_root_span", sharp_root_left, sharp_root_right),
        _profile_segment("timing_tip_center", (0.0, 0.0), (0.0, sharp_tip_left[1])),
        _profile_segment("timing_root_center", (0.0, 0.0), (0.0, sharp_root_left[1])),
        _profile_segment("timing_sharp_flank_left", sharp_tip_left, sharp_root_left),
        _profile_segment("timing_sharp_flank_right", sharp_tip_right, sharp_root_right),
    ]
    for entity in auxiliary_entities[2:]:
        entity["role"] = "parameterization_datum"
        entity["line_style"] = 2

    pre_constraints: list[dict[str, Any]] = []
    for left, right in zip(groove_entities, groove_entities[1:]):
        pre_constraints.append(
            {
                "kind": "merge_points",
                "target": left["id"],
                "index": 2 if left["kind"] == "arc" else 1,
                "partner": right["id"],
                "partner_index": 1 if right["kind"] == "arc" else 0,
            }
        )
    pre_constraints.append(
        {
            "kind": "merge_points",
            "target": groove_entities[-1]["id"],
            "index": 1,
            "partner": groove_entities[0]["id"],
            "partner_index": 0,
        }
    )
    pre_constraints.extend(
        [
            {"kind": "fixed_point", "target": "timing_outer_datum", "index": 0},
            {"kind": "merge_points", "target": "timing_root_datum", "index": 0, "partner": "timing_outer_datum", "partner_index": 0},
            {"kind": "merge_points", "target": "timing_tip_center", "index": 0, "partner": "timing_outer_datum", "partner_index": 0},
            {"kind": "merge_points", "target": "timing_root_center", "index": 0, "partner": "timing_outer_datum", "partner_index": 0},
            {"kind": "merge_points", "target": "timing_sharp_flank_left", "index": 0, "partner": "timing_tip_span", "partner_index": 0},
            {"kind": "merge_points", "target": "timing_sharp_flank_left", "index": 1, "partner": "timing_root_span", "partner_index": 0},
            {"kind": "merge_points", "target": "timing_sharp_flank_right", "index": 0, "partner": "timing_tip_span", "partner_index": 1},
            {"kind": "merge_points", "target": "timing_sharp_flank_right", "index": 1, "partner": "timing_root_span", "partner_index": 1},
        ]
    )
    constraints = pre_constraints + [
        {"kind": "horizontal", "target": "timing_tip_span"},
        {"kind": "horizontal", "target": "timing_root_span"},
        {"kind": "vertical", "target": "timing_tip_center"},
        {"kind": "vertical", "target": "timing_root_center"},
        {"kind": "point_on_curve_middle", "target": "timing_tip_center", "index": 1, "partner": "timing_tip_span"},
        {"kind": "point_on_curve_middle", "target": "timing_root_center", "index": 1, "partner": "timing_root_span"},
        {"kind": "point_on_curve", "target": "timing_tip_span", "index": 0, "partner": "timing_outer_datum"},
        {"kind": "point_on_curve", "target": "timing_tip_span", "index": 1, "partner": "timing_outer_datum"},
        {"kind": "point_on_curve", "target": "timing_root_span", "index": 0, "partner": "timing_root_datum"},
        {"kind": "point_on_curve", "target": "timing_root_span", "index": 1, "partner": "timing_root_datum"},
        {"kind": "point_on_curve", "target": "groove_arc_tip_left", "index": 1, "partner": "timing_outer_datum"},
        {"kind": "point_on_curve", "target": "groove_arc_tip_right", "index": 2, "partner": "timing_outer_datum"},
        {"kind": "collinear", "target": "groove_segment_2", "partner": "timing_sharp_flank_left"},
        {"kind": "collinear", "target": "groove_segment_4", "partner": "timing_sharp_flank_right"},
        {"kind": "collinear", "target": "groove_segment_3", "partner": "timing_root_span"},
        {"kind": "tangent", "target": "groove_arc_tip_left", "partner": "timing_outer_datum"},
        {"kind": "tangent", "target": "groove_arc_tip_left", "partner": "groove_segment_2"},
        {"kind": "tangent", "target": "groove_segment_2", "partner": "groove_arc_root_left"},
        {"kind": "tangent", "target": "groove_arc_root_left", "partner": "groove_segment_3"},
        {"kind": "tangent", "target": "groove_segment_3", "partner": "groove_arc_root_right"},
        {"kind": "tangent", "target": "groove_arc_root_right", "partner": "groove_segment_4"},
        {"kind": "tangent", "target": "groove_segment_4", "partner": "groove_arc_tip_right"},
        {"kind": "tangent", "target": "groove_arc_tip_right", "partner": "timing_outer_datum"},
        {"kind": "equal_radius", "target": "groove_arc_tip_right", "partner": "groove_arc_tip_left"},
        {"kind": "equal_radius", "target": "groove_arc_root_right", "partner": "groove_arc_root_left"},
        {"kind": "horizontal", "target": "groove_segment_6"},
        {"kind": "equal_length", "target": "groove_segment_5", "partner": "groove_segment_1"},
    ]
    dimensions = [
        {"kind": "circle_radius", "target": "timing_outer_datum", "name": "TB_OR_DIM", "variable_name": "TB_OR", "value": outside_radius, "driving": True},
        {"kind": "circle_radius", "target": "timing_root_datum", "name": "TB_RR_DIM", "variable_name": "TB_RR", "value": root_radius, "driving": True},
        {"kind": "line_length", "target": "timing_tip_span", "name": "TB_W_DIM", "variable_name": "TB_W", "value": mouth_width, "driving": True},
        {"kind": "line_length", "target": "timing_root_span", "name": "TB_RW_DIM", "variable_name": "TB_RW", "value": root_width, "driving": True},
        {"kind": "arc_radius", "target": "groove_arc_tip_left", "name": "TB_RT_DIM", "variable_name": "TB_RT", "value": tip_radius, "driving": True},
        {"kind": "arc_radius", "target": "groove_arc_root_left", "name": "TB_RF_DIM", "variable_name": "TB_RF", "value": root_fillet_radius, "driving": True},
        {"kind": "line_length", "target": "groove_segment_1", "name": "TB_CO_DIM", "variable_name": "TB_CO", "value": closure_overshoot, "driving": True},
        {"kind": "point_distance", "target": "timing_outer_datum", "support_point_index": 0, "partner": "groove_segment_1", "partner_point_index": 0, "orientation": "parallel", "name": "TB_CLOSURE_RADIUS_DIM", "expression": "TB_OR + TB_CO", "value": outside_radius + closure_overshoot, "driving": True},
    ]
    return {
        "variables": variables,
        "auxiliary_entities": auxiliary_entities,
        "constraints": constraints,
        "dimensions": dimensions,
        "sketch_options": {
            "constraints": {"enabled": True},
            "dimensions": {"enabled": True, "driving": True},
            "parameterization_order": "staged",
            "require_exact_counts": True,
            "expected_constraint_count": len(constraints),
            "expected_dimension_count": len(dimensions),
        },
    }


def _build_curvilinear_parameterization(
    *,
    groove_entities: list[dict[str, Any]],
    sharp_tip_left: tuple[float, float],
    sharp_tip_right: tuple[float, float],
    root_control: tuple[float, float],
    outside_radius: float,
    root_radius: float,
    tip_radius: float,
    root_fillet_radius: float,
    closure_overshoot: float,
    pitch: float,
    tooth_count: int,
    face_width: float,
    pitch_line_offset: float,
    groove_depth: float,
) -> dict[str, Any]:
    mouth_width = abs(sharp_tip_right[0] - sharp_tip_left[0])
    outside_diameter = outside_radius * 2.0
    variables = [
        _timing_variable("TB_P", pitch, note="Timing-belt tooth pitch"),
        _timing_variable("TB_Z", tooth_count, note="Timing-pulley tooth count", unit="unitless"),
        _timing_variable("TB_B", face_width, note="Timing-pulley face width"),
        _timing_variable("TB_PL", pitch_line_offset, note="Pitch-line radial offset"),
        _timing_variable(
            "TB_DA", outside_diameter,
            expression="TB_P * TB_Z / 3.141592653589793 - 2 * TB_PL",
            note="Outside diameter",
        ),
        _timing_variable("TB_OR", outside_radius, expression="TB_DA / 2", note="Outside radius"),
        _timing_variable("TB_H", groove_depth, note="Groove radial depth"),
        _timing_variable("TB_RR", root_radius, expression="TB_OR - TB_H", note="Root radius"),
        _timing_variable("TB_W", mouth_width, note="Sharp groove-mouth chord width"),
        _timing_variable("TB_RT", tip_radius, note="Retained-tooth transition radius"),
        _timing_variable("TB_RF", root_fillet_radius, note="Central groove-root radius"),
        _timing_variable("TB_CO", closure_overshoot, note="Cut-contour radial closure overshoot"),
        _timing_variable("TB_SPAN", 360.0, note="Circular pattern span", unit="deg"),
        _timing_variable(
            "TB_STEP", 360.0 / float(tooth_count), expression="TB_SPAN / TB_Z",
            note="Circular pattern angular step", unit="deg",
        ),
    ]
    auxiliary_entities = [
        {
            "id": "timing_outer_datum", "kind": "circle", "role": "parameterization_datum",
            "center": [0.0, 0.0], "radius": outside_radius, "line_style": 2,
        },
        {
            "id": "timing_root_datum", "kind": "circle", "role": "parameterization_datum",
            "center": [0.0, 0.0], "radius": root_radius, "line_style": 2,
        },
        _profile_segment("timing_tip_span", sharp_tip_left, sharp_tip_right),
        _profile_segment("timing_tip_center", (0.0, 0.0), (0.0, sharp_tip_left[1])),
        _profile_segment("timing_root_axis", (0.0, 0.0), root_control),
        _profile_segment("timing_sharp_flank_left", sharp_tip_left, root_control),
        _profile_segment("timing_sharp_flank_right", sharp_tip_right, root_control),
    ]
    for entity in auxiliary_entities[2:]:
        entity["role"] = "parameterization_datum"
        entity["line_style"] = 2

    constraints: list[dict[str, Any]] = []
    for left, right in zip(groove_entities, groove_entities[1:]):
        constraints.append(
            {
                "kind": "merge_points", "target": left["id"],
                "index": 2 if left["kind"] == "arc" else 1,
                "partner": right["id"], "partner_index": 1 if right["kind"] == "arc" else 0,
            }
        )
    constraints.append(
        {
            "kind": "merge_points", "target": groove_entities[-1]["id"], "index": 1,
            "partner": groove_entities[0]["id"], "partner_index": 0,
        }
    )
    constraints.extend(
        [
            {"kind": "fixed_point", "target": "timing_outer_datum", "index": 0},
            {"kind": "merge_points", "target": "timing_root_datum", "index": 0, "partner": "timing_outer_datum", "partner_index": 0},
            {"kind": "merge_points", "target": "timing_tip_center", "index": 0, "partner": "timing_outer_datum", "partner_index": 0},
            {"kind": "merge_points", "target": "timing_root_axis", "index": 0, "partner": "timing_outer_datum", "partner_index": 0},
            {"kind": "merge_points", "target": "timing_sharp_flank_left", "index": 0, "partner": "timing_tip_span", "partner_index": 0},
            {"kind": "merge_points", "target": "timing_sharp_flank_right", "index": 0, "partner": "timing_tip_span", "partner_index": 1},
            {"kind": "merge_points", "target": "timing_sharp_flank_left", "index": 1, "partner": "timing_root_axis", "partner_index": 1},
            {"kind": "merge_points", "target": "timing_sharp_flank_right", "index": 1, "partner": "timing_root_axis", "partner_index": 1},
            {"kind": "horizontal", "target": "timing_tip_span"},
            {"kind": "vertical", "target": "timing_tip_center"},
            {"kind": "vertical", "target": "timing_root_axis"},
            {"kind": "point_on_curve_middle", "target": "timing_tip_center", "index": 1, "partner": "timing_tip_span"},
            {"kind": "point_on_curve", "target": "timing_tip_span", "index": 0, "partner": "timing_outer_datum"},
            {"kind": "point_on_curve", "target": "timing_tip_span", "index": 1, "partner": "timing_outer_datum"},
            {"kind": "point_on_curve", "target": "groove_arc_tip_left", "index": 1, "partner": "timing_outer_datum"},
            {"kind": "point_on_curve", "target": "groove_arc_tip_right", "index": 2, "partner": "timing_outer_datum"},
            {"kind": "collinear", "target": "groove_segment_2", "partner": "timing_sharp_flank_left"},
            {"kind": "collinear", "target": "groove_segment_3", "partner": "timing_sharp_flank_right"},
            {"kind": "tangent", "target": "groove_arc_tip_left", "partner": "timing_outer_datum"},
            {"kind": "tangent", "target": "groove_arc_tip_left", "partner": "groove_segment_2"},
            {"kind": "tangent", "target": "groove_segment_2", "partner": "groove_arc_root"},
            {"kind": "tangent", "target": "groove_arc_root", "partner": "groove_segment_3"},
            {"kind": "tangent", "target": "groove_segment_3", "partner": "groove_arc_tip_right"},
            {"kind": "tangent", "target": "groove_arc_tip_right", "partner": "timing_outer_datum"},
            {"kind": "tangent", "target": "groove_arc_root", "partner": "timing_root_datum"},
            {"kind": "equal_radius", "target": "groove_arc_tip_right", "partner": "groove_arc_tip_left"},
            {"kind": "equal_length", "target": "timing_sharp_flank_right", "partner": "timing_sharp_flank_left"},
            {"kind": "horizontal", "target": "groove_segment_5"},
            {"kind": "equal_length", "target": "groove_segment_4", "partner": "groove_segment_1"},
        ]
    )
    dimensions = [
        {"kind": "circle_radius", "target": "timing_outer_datum", "name": "TB_OR_DIM", "variable_name": "TB_OR", "value": outside_radius, "driving": True},
        {"kind": "circle_radius", "target": "timing_root_datum", "name": "TB_RR_DIM", "variable_name": "TB_RR", "value": root_radius, "driving": True},
        {"kind": "line_length", "target": "timing_tip_span", "name": "TB_W_DIM", "variable_name": "TB_W", "value": mouth_width, "driving": True},
        {"kind": "arc_radius", "target": "groove_arc_tip_left", "name": "TB_RT_DIM", "variable_name": "TB_RT", "value": tip_radius, "driving": True},
        {"kind": "arc_radius", "target": "groove_arc_root", "name": "TB_RF_DIM", "variable_name": "TB_RF", "value": root_fillet_radius, "driving": True},
        {"kind": "line_length", "target": "groove_segment_1", "name": "TB_CO_DIM", "variable_name": "TB_CO", "value": closure_overshoot, "driving": True},
        {"kind": "point_distance", "target": "timing_outer_datum", "support_point_index": 0, "partner": "groove_segment_1", "partner_point_index": 0, "orientation": "parallel", "name": "TB_CLOSURE_RADIUS_DIM", "expression": "TB_OR + TB_CO", "value": outside_radius + closure_overshoot, "driving": True},
    ]
    return {
        "variables": variables,
        "auxiliary_entities": auxiliary_entities,
        "constraints": constraints,
        "dimensions": dimensions,
        "sketch_options": {
            "constraints": {"enabled": True},
            "dimensions": {"enabled": True, "driving": True},
            "parameterization_order": "staged",
            "require_exact_counts": True,
            "expected_constraint_count": len(constraints),
            "expected_dimension_count": len(dimensions),
        },
    }


def _curvilinear_control_depth(half_width: float, groove_depth: float, root_radius: float) -> float:
    control_depth = groove_depth + root_radius
    for _ in range(24):
        flank_length = math.hypot(half_width, control_depth)
        actual_depth = control_depth - root_radius * flank_length / half_width + root_radius
        derivative = 1.0 - root_radius * control_depth / (half_width * flank_length)
        if derivative <= 1e-8:
            raise ValueError("root radius is too large for the curvilinear groove width")
        control_depth += (groove_depth - actual_depth) / derivative
    return control_depth


def _sector_profile(
    *,
    pitch: float,
    outside_radius: float,
    groove_width: float,
    groove_depth: float,
    shape: str,
    tip_radius: float,
    root_fillet_radius: float,
) -> tuple[list[list[float]], list[dict[str, Any]]]:
    half_width = groove_width / 2.0
    control_depth = groove_depth if shape == "trapezoidal" else _curvilinear_control_depth(half_width, groove_depth, root_fillet_radius)
    points: list[tuple[float, float]] = [(-1.5 * pitch, 0.0)]
    radii = [0.0]
    roles: list[dict[str, Any] | None] = [None]
    for groove_index, center in enumerate((-pitch, 0.0, pitch)):
        points.append((center - half_width, 0.0))
        radii.append(tip_radius)
        roles.append({"kind": "tip", "groove_index": groove_index, "side": "left"})
        if shape == "trapezoidal":
            half_root = groove_width * 0.22
            points.extend(((center - half_root, groove_depth), (center + half_root, groove_depth)))
            radii.extend((root_fillet_radius, root_fillet_radius))
            roles.extend(
                (
                    {"kind": "root", "groove_index": groove_index, "side": "left"},
                    {"kind": "root", "groove_index": groove_index, "side": "right"},
                )
            )
        else:
            points.append((center, control_depth))
            radii.append(root_fillet_radius)
            roles.append({"kind": "root", "groove_index": groove_index, "side": "center"})
        points.append((center + half_width, 0.0))
        radii.append(tip_radius)
        roles.append({"kind": "tip", "groove_index": groove_index, "side": "right"})
    points.append((1.5 * pitch, 0.0))
    radii.append(0.0)
    roles.append(None)

    local_profile, local_fillets = _rounded_polyline(points, radii, roles)

    def wrapped(point: tuple[float, float]) -> list[float]:
        x, indentation = point
        return _polar(outside_radius - indentation, x / outside_radius)

    return [wrapped(point) for point in local_profile], [
        {
            **fillet,
            "center": wrapped(fillet["center"]),
            "start": wrapped(fillet["start"]),
            "end": wrapped(fillet["end"]),
            "anchor": wrapped(fillet["anchor"]),
            "anchor_start": wrapped(fillet["anchor_start"]),
            "anchor_end": wrapped(fillet["anchor_end"]),
        }
        for fillet in local_fillets
    ]


def _arc(radius: float, angle_start: float, angle_end: float, samples: int = 64) -> list[list[float]]:
    return [_polar(radius, angle_start + (angle_end - angle_start) * index / samples) for index in range(samples + 1)]


def _break_contour(outside_radius: float, radius: float, angle_start: float, angle_end: float, depth: float) -> list[list[float]]:
    points: list[list[float]] = []
    side_samples = 24
    for index in range(side_samples + 1):
        progress = index / side_samples
        smooth = progress * progress * (3.0 - 2.0 * progress)
        side_radius = outside_radius + (radius - outside_radius) * smooth
        side_radius += math.sin(progress * math.pi * 4.0) * depth * 0.045
        side_angle = angle_end + math.sin(progress * math.pi) * depth * 0.14 / outside_radius
        points.append(_polar(side_radius, side_angle))
    bottom_samples = 96
    for index in range(1, bottom_samples + 1):
        progress = index / bottom_samples
        angle = angle_end + (angle_start - angle_end) * progress
        wave = math.sin(progress * math.pi * 8.0) * depth
        points.append(_polar(radius + wave, angle))
    for index in range(1, side_samples + 1):
        progress = index / side_samples
        smooth = progress * progress * (3.0 - 2.0 * progress)
        side_radius = radius + (outside_radius - radius) * smooth
        side_radius += math.sin(progress * math.pi * 4.0) * depth * 0.045
        side_angle = angle_start - math.sin(progress * math.pi) * depth * 0.14 / outside_radius
        points.append(_polar(side_radius, side_angle))
    return points


def preview_timing_belt_pulley(
    *,
    designation: TimingProfileDesignation,
    tooth_count: int,
    face_width: float,
    custom_shape: TimingProfileShape | None = None,
    custom_pitch: float | None = None,
    custom_groove_depth: float | None = None,
    custom_groove_width: float | None = None,
    custom_pitch_line_offset: float | None = None,
    custom_tip_radius: float | None = None,
    custom_root_radius: float | None = None,
) -> dict[str, Any]:
    designation = str(designation or "").strip().upper()
    count_value = float(tooth_count)
    count = int(round(count_value))
    if count < 8 or count > 360 or abs(count_value - count) > 1e-9:
        raise ValueError("tooth_count must be an integer from 8 to 360")
    width = _positive("face_width", face_width)

    if designation == "CUSTOM":
        shape = str(custom_shape or "").strip().lower()
        if shape not in ("trapezoidal", "curvilinear"):
            raise ValueError("custom_shape must be 'trapezoidal' or 'curvilinear'")
        groove_depth = _positive("custom_groove_depth", custom_groove_depth)
        profile = {
            "shape": shape,
            "pitch": _positive("custom_pitch", custom_pitch),
            "groove_depth": groove_depth,
            "groove_width": _positive("custom_groove_width", custom_groove_width),
            "pitch_line_offset": _positive("custom_pitch_line_offset", custom_pitch_line_offset),
            "tip_radius": _positive("custom_tip_radius", custom_tip_radius) if custom_tip_radius is not None else groove_depth * 0.2,
            "root_fillet_radius": _positive("custom_root_radius", custom_root_radius) if custom_root_radius is not None else groove_depth * (0.35 if shape == "trapezoidal" else 0.68),
        }
    elif designation in _PROFILES:
        profile = dict(_PROFILES[designation])
    else:
        raise ValueError("Unsupported timing-belt profile designation")

    pitch = float(profile["pitch"])
    groove_depth = float(profile["groove_depth"])
    groove_width = float(profile["groove_width"])
    pitch_line_offset = float(profile["pitch_line_offset"])
    tip_radius = float(profile["tip_radius"])
    root_fillet_radius = float(profile["root_fillet_radius"])
    pitch_radius = pitch * count / (2.0 * math.pi)
    outside_radius = pitch_radius - pitch_line_offset
    root_radius = outside_radius - groove_depth
    if outside_radius <= 0.0 or root_radius <= 0.0:
        raise ValueError("profile and tooth_count must leave positive outside and root radii")
    half_groove_angle = groove_width / (2.0 * outside_radius)
    tooth_angle = 2.0 * math.pi / count
    if half_groove_angle >= tooth_angle / 2.0:
        raise ValueError("groove_width is too large for the selected pitch diameter")

    sector, fillets = _sector_profile(
        pitch=pitch,
        outside_radius=outside_radius,
        groove_width=groove_width,
        groove_depth=groove_depth,
        shape=str(profile["shape"]),
        tip_radius=tip_radius,
        root_fillet_radius=root_fillet_radius,
    )
    sector_half_angle = math.atan2(sector[-1][0], sector[-1][1])
    break_radius = max(root_radius - groove_depth * 1.5, root_radius * 0.72)
    break_arc = _break_contour(outside_radius, break_radius, -sector_half_angle, sector_half_angle, groove_depth * 0.08)
    outline = [*sector, *break_arc]
    outside_circle = _arc(outside_radius, -sector_half_angle, sector_half_angle)
    return {
        "success": True,
        "operation": "timing_belt_pulley_preview",
        "inputs": {
            "designation": designation,
            "tooth_count": count,
            "face_width": width,
            **({
                "custom_shape": profile["shape"],
                "custom_pitch": pitch,
                "custom_groove_depth": groove_depth,
                "custom_groove_width": groove_width,
                "custom_pitch_line_offset": pitch_line_offset,
                "custom_tip_radius": tip_radius,
                "custom_root_radius": root_fillet_radius,
            } if designation == "CUSTOM" else {}),
        },
        "profile": dict(profile),
        "provenance": {
            "source": _SOURCE_URL if designation != "CUSTOM" else "user_input",
            "status": "preview_reference" if designation != "CUSTOM" else "custom_unverified",
            "note": "Profile constants and circular-fit tip/root radii are suitable for Studio geometry exploration, not a licensed-standard manufacturing claim.",
        },
        "derived": {
            "pitch_diameter": pitch_radius * 2.0,
            "outside_diameter": outside_radius * 2.0,
            "root_diameter": root_radius * 2.0,
            "angular_pitch_degrees": 360.0 / count,
            "tip_radius": tip_radius,
            "root_fillet_radius": root_fillet_radius,
        },
        "geometry": {
            "view": "end",
            "outline": outline,
            "profile_path": sector,
            "break_path": break_arc,
            "highlighted_sector": sector,
            "fillets": fillets,
            "outside_circle": outside_circle,
            "sector_half_angle": sector_half_angle,
            "break_radius": break_radius,
            "coordinate_system": {"x": "radial_horizontal", "y": "radial_vertical"},
        },
        "warnings": (["Custom geometry is not asserted to match a published belt standard."] if designation == "CUSTOM" else []),
    }


def build_trapezoidal_timing_pulley_plan(
    *,
    designation: TimingProfileDesignation,
    tooth_count: int,
    face_width: float,
    name: str = "Geomwright trapezoidal timing pulley",
    custom_pitch: float | None = None,
    custom_groove_depth: float | None = None,
    custom_groove_width: float | None = None,
    custom_pitch_line_offset: float | None = None,
    custom_tip_radius: float | None = None,
    custom_root_radius: float | None = None,
    parameterize: bool = False,
) -> dict[str, Any]:
    """Build the accepted numeric T/AT mechanics with optional parameterization."""
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")
    preview = preview_timing_belt_pulley(
        designation=designation,
        tooth_count=tooth_count,
        face_width=face_width,
        custom_shape="trapezoidal" if str(designation).strip().upper() == "CUSTOM" else None,
        custom_pitch=custom_pitch,
        custom_groove_depth=custom_groove_depth,
        custom_groove_width=custom_groove_width,
        custom_pitch_line_offset=custom_pitch_line_offset,
        custom_tip_radius=custom_tip_radius,
        custom_root_radius=custom_root_radius,
    )
    profile = dict(preview["profile"])
    if profile["shape"] != "trapezoidal":
        raise ValueError("build_trapezoidal_timing_pulley_plan supports only T/AT trapezoidal profiles")

    derived = dict(preview["derived"])
    outside_radius = float(derived["outside_diameter"]) / 2.0
    root_radius = float(derived["root_diameter"]) / 2.0
    groove_width = float(profile["groove_width"])
    half_tip_angle = groove_width / (2.0 * outside_radius)
    half_root_width = groove_width * 0.22
    half_root_angle = half_root_width / root_radius
    sharp_tip_left = tuple(_polar(outside_radius, -half_tip_angle))
    sharp_root_left = tuple(_polar(root_radius, -half_root_angle))
    sharp_root_right = tuple(_polar(root_radius, half_root_angle))
    sharp_tip_right = tuple(_polar(outside_radius, half_tip_angle))
    tip_radius = float(profile["tip_radius"])
    root_fillet_radius = float(profile["root_fillet_radius"])

    left_tip = _tip_transition(
        sharp_tip_left,
        sharp_root_left,
        outside_radius=outside_radius,
        radius=tip_radius,
    )
    right_tip = _tip_transition(
        sharp_tip_right,
        sharp_root_right,
        outside_radius=outside_radius,
        radius=tip_radius,
    )
    _, root_fillets = _rounded_polyline(
        [sharp_tip_left, sharp_root_left, sharp_root_right, sharp_tip_right],
        [0.0, root_fillet_radius, root_fillet_radius, 0.0],
        [None, {"kind": "root", "side": "left"}, {"kind": "root", "side": "right"}, None],
    )
    root_fillet_by_vertex = {int(item["vertex_index"]): item for item in root_fillets}
    left_root = root_fillet_by_vertex[1]
    right_root = root_fillet_by_vertex[2]

    closure_clearance = max(float(profile["groove_depth"]) * 0.25, 0.25)
    transition_cosine = min(
        float(left_tip["outer"][1]) / outside_radius,
        float(right_tip["outer"][1]) / outside_radius,
    )
    closure_radius = (outside_radius + closure_clearance) / transition_cosine
    closure_left = tuple(value * closure_radius / outside_radius for value in left_tip["outer"])
    closure_right = tuple(value * closure_radius / outside_radius for value in right_tip["outer"])

    groove_entities = [
        _profile_segment("groove_segment_1", closure_left, left_tip["outer"]),
        _profile_arc(
            "groove_arc_tip_left",
            left_tip["center"],
            tip_radius,
            left_tip["outer"],
            left_tip["tangent"],
            float(left_tip["sweep"]),
            {"kind": "tip", "side": "left"},
        ),
        _profile_segment("groove_segment_2", left_tip["tangent"], left_root["start"]),
        _profile_arc(
            "groove_arc_root_left",
            left_root["center"],
            root_fillet_radius,
            left_root["start"],
            left_root["end"],
            float(left_root["sweep"]),
            {"kind": "root", "side": "left"},
        ),
        _profile_segment("groove_segment_3", left_root["end"], right_root["start"]),
        _profile_arc(
            "groove_arc_root_right",
            right_root["center"],
            root_fillet_radius,
            right_root["start"],
            right_root["end"],
            float(right_root["sweep"]),
            {"kind": "root", "side": "right"},
        ),
        _profile_segment("groove_segment_4", right_root["end"], right_tip["tangent"]),
        _profile_arc(
            "groove_arc_tip_right",
            right_tip["center"],
            tip_radius,
            right_tip["tangent"],
            right_tip["outer"],
            -float(right_tip["sweep"]),
            {"kind": "tip", "side": "right"},
        ),
        _profile_segment("groove_segment_5", right_tip["outer"], closure_right),
        _profile_segment("groove_segment_6", closure_right, closure_left),
    ]
    groove_vertices = [
        closure_left,
        sharp_tip_left,
        sharp_root_left,
        sharp_root_right,
        sharp_tip_right,
        closure_right,
    ]
    parameterization = (
        _build_trapezoidal_parameterization(
            groove_entities=groove_entities,
            sharp_tip_left=sharp_tip_left,
            sharp_tip_right=sharp_tip_right,
            sharp_root_left=sharp_root_left,
            sharp_root_right=sharp_root_right,
            outside_radius=outside_radius,
            root_radius=root_radius,
            tip_radius=tip_radius,
            root_fillet_radius=root_fillet_radius,
            closure_overshoot=closure_radius - outside_radius,
            pitch=float(profile["pitch"]),
            tooth_count=int(tooth_count),
            face_width=float(face_width),
            pitch_line_offset=float(profile["pitch_line_offset"]),
            groove_depth=float(profile["groove_depth"]),
        )
        if parameterize
        else {"variables": [], "auxiliary_entities": [], "constraints": [], "dimensions": [], "sketch_options": {}}
    )
    sketch_entities = groove_entities + list(parameterization["auxiliary_entities"])
    operations = [
        {
            "id": "blank",
            "scenario": "cylindrical_blank",
            "params": {
                "name": f"{requested_name} blank",
                "sketch_name": f"{requested_name} blank sketch",
                "outside_diameter": float(derived["outside_diameter"]),
                "width": float(face_width),
                "plane": "YOZ",
                "axis": "x_axis",
                "parameterize": bool(parameterize),
                "variable_plan": list(parameterization["variables"]),
                "constraints": ([{"kind": "fixed_point", "target": "blank_circle", "index": 0}] if parameterize else []),
                "dimensions": ([{"kind": "circle_radius", "target": "blank_circle", "name": "TB_BLANK_OR_DIM", "variable_name": "TB_OR", "value": outside_radius, "driving": True}] if parameterize else []),
                "operation_variable_bindings": ([{"target": "extrusion", "parameter_note": "Distance 1", "parameter_note_aliases": ["Distance 1", "Length 1", "Depth 1", "Расстояние 1", "Длина 1", "Глубина 1"], "expression": "TB_B", "role": "blank_width"}] if parameterize else []),
                "sketch_options": ({"constraints": {"enabled": True}, "dimensions": {"enabled": True, "driving": True}, "parameterization_order": "constraints_first"} if parameterize else {}),
            },
        },
        {
            "id": "groove_sketch",
            "scenario": "numeric_profile_sketch",
            "params": {
                "name": f"{requested_name} one groove",
                "plane": "YOZ",
                "entities": sketch_entities,
                "parameterize": bool(parameterize),
                "constraints": list(parameterization["constraints"]),
                "dimensions": list(parameterization["dimensions"]),
                "sketch_options": dict(parameterization["sketch_options"]),
                "require_fully_defined": bool(parameterize),
            },
        },
        {
            "id": "groove_cut",
            "scenario": "cut_extrusion",
            "params": {
                "name": f"{requested_name} one groove cut",
                "sketch": "groove_sketch.sketch",
                "direction": "both",
                "end_condition": "through_all",
                "require_fully_defined": bool(parameterize),
            },
        },
        {
            "id": "groove_pattern",
            "scenario": "circular_pattern",
            "params": {
                "name": f"{requested_name} groove pattern",
                "source": "groove_cut.feature",
                "axis": "blank.axis",
                "count": int(tooth_count),
                "span_angle": 360.0,
                "parameterize": bool(parameterize),
                "parameter_prefix": "TB",
                "count_variable": "TB_Z",
                "span_angle_variable": "TB_SPAN",
                "angle_step_variable": "TB_STEP",
            },
        },
    ]
    return {
        "ok": True,
        "stage": ("trapezoidal_timing_pulley_parameterized_mechanics" if parameterize else "trapezoidal_timing_pulley_numeric_mechanics"),
        "name": requested_name,
        "profile_preview": preview,
        "workflow": {
            "scenario": "workflow",
            "params": {
                "name": requested_name,
                "operations": operations,
                "exports": [
                    {"name": "blank_body", "ref": "blank.body"},
                    {"name": "groove_cut", "ref": "groove_cut.feature"},
                    {"name": "groove_pattern", "ref": "groove_pattern.feature"},
                ],
            },
        },
        "geometry": {
            "groove_vertices": [list(point) for point in groove_vertices],
            "groove_entities": groove_entities,
            "auxiliary_entities": list(parameterization["auxiliary_entities"]),
            "closure_radius": closure_radius,
            "outside_radius": outside_radius,
            "root_radius": root_radius,
            "tip_transitions": {
                "left": {key: value for key, value in left_tip.items() if key != "distance_from_sharp_tip"},
                "right": {key: value for key, value in right_tip.items() if key != "distance_from_sharp_tip"},
            },
        },
        "parameterization": {
            "part_variables": bool(parameterize),
            "sketch_constraints": bool(parameterize),
            "sketch_dimensions": bool(parameterize),
            "operation_variables": bool(parameterize),
            "variables": list(parameterization["variables"]),
            "constraints": list(parameterization["constraints"]),
            "dimensions": list(parameterization["dimensions"]),
        },
        "verification": {
            "require_single_body": True,
            "require_closed_primary_contour": True,
            "require_volume_decrease_after_cut": True,
            "require_pattern_count": int(tooth_count),
            "require_pattern_span_degrees": 360.0,
            "expected_outside_diameter": float(derived["outside_diameter"]),
            "expected_root_diameter": float(derived["root_diameter"]),
        },
    }


def _curvilinear_root_fillet(
    sharp_tip_left: tuple[float, float],
    sharp_tip_right: tuple[float, float],
    *,
    root_radius: float,
    fillet_radius: float,
) -> tuple[tuple[float, float], dict[str, Any]]:
    """Solve the sharp control vertex so the true root arc reaches root_radius."""

    def solve(control_radius: float) -> tuple[float, dict[str, Any]]:
        control = (0.0, control_radius)
        _, annotations = _rounded_polyline(
            [sharp_tip_left, control, sharp_tip_right],
            [0.0, fillet_radius, 0.0],
            [None, {"kind": "root", "side": "center"}, None],
        )
        fillet = annotations[0]
        actual_root_radius = math.hypot(*fillet["center"]) - fillet_radius
        return actual_root_radius, fillet

    control_radius = root_radius - fillet_radius
    fillet: dict[str, Any] | None = None
    for _ in range(24):
        actual, fillet = solve(control_radius)
        error = actual - root_radius
        if abs(error) <= 1e-10:
            break
        step = max(1e-6, abs(control_radius) * 1e-6)
        shifted, _ = solve(control_radius + step)
        derivative = (shifted - actual) / step
        if abs(derivative) <= 1e-9:
            raise ValueError("curvilinear timing root control depth could not be solved")
        control_radius -= error / derivative
    if fillet is None or control_radius <= 0.0:
        raise ValueError("curvilinear timing root geometry is not feasible")
    actual, fillet = solve(control_radius)
    if abs(actual - root_radius) > 1e-7:
        raise ValueError("curvilinear timing root radius did not converge")
    return (0.0, control_radius), fillet


def build_curvilinear_timing_pulley_plan(
    *,
    designation: TimingProfileDesignation,
    tooth_count: int,
    face_width: float,
    name: str = "Curvilinear timing-belt pulley",
    custom_pitch: float | None = None,
    custom_groove_depth: float | None = None,
    custom_groove_width: float | None = None,
    custom_pitch_line_offset: float | None = None,
    custom_tip_radius: float | None = None,
    custom_root_radius: float | None = None,
    parameterize: bool = False,
) -> dict[str, Any]:
    """Build numeric HTD mechanics from true tangent arcs and straight flanks."""
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")
    preview = preview_timing_belt_pulley(
        designation=designation,
        tooth_count=tooth_count,
        face_width=face_width,
        custom_shape="curvilinear" if str(designation).strip().upper() == "CUSTOM" else None,
        custom_pitch=custom_pitch,
        custom_groove_depth=custom_groove_depth,
        custom_groove_width=custom_groove_width,
        custom_pitch_line_offset=custom_pitch_line_offset,
        custom_tip_radius=custom_tip_radius,
        custom_root_radius=custom_root_radius,
    )
    profile = dict(preview["profile"])
    if profile["shape"] != "curvilinear":
        raise ValueError("build_curvilinear_timing_pulley_plan supports only HTD curvilinear profiles")

    derived = dict(preview["derived"])
    outside_radius = float(derived["outside_diameter"]) / 2.0
    root_radius = float(derived["root_diameter"]) / 2.0
    half_tip_angle = float(profile["groove_width"]) / (2.0 * outside_radius)
    sharp_tip_left = tuple(_polar(outside_radius, -half_tip_angle))
    sharp_tip_right = tuple(_polar(outside_radius, half_tip_angle))
    root_control, root_fillet = _curvilinear_root_fillet(
        sharp_tip_left,
        sharp_tip_right,
        root_radius=root_radius,
        fillet_radius=float(profile["root_fillet_radius"]),
    )
    left_tip = _tip_transition(
        sharp_tip_left,
        root_control,
        outside_radius=outside_radius,
        radius=float(profile["tip_radius"]),
    )
    right_tip = _tip_transition(
        sharp_tip_right,
        root_control,
        outside_radius=outside_radius,
        radius=float(profile["tip_radius"]),
    )
    closure_clearance = max(float(profile["groove_depth"]) * 0.25, 0.25)
    transition_cosine = min(
        float(left_tip["outer"][1]) / outside_radius,
        float(right_tip["outer"][1]) / outside_radius,
    )
    closure_radius = (outside_radius + closure_clearance) / transition_cosine
    closure_left = tuple(value * closure_radius / outside_radius for value in left_tip["outer"])
    closure_right = tuple(value * closure_radius / outside_radius for value in right_tip["outer"])
    groove_entities = [
        _profile_segment("groove_segment_1", closure_left, left_tip["outer"]),
        _profile_arc(
            "groove_arc_tip_left", left_tip["center"], float(profile["tip_radius"]),
            left_tip["outer"], left_tip["tangent"], float(left_tip["sweep"]),
            {"kind": "tip", "side": "left"},
        ),
        _profile_segment("groove_segment_2", left_tip["tangent"], root_fillet["start"]),
        _profile_arc(
            "groove_arc_root", root_fillet["center"], float(profile["root_fillet_radius"]),
            root_fillet["start"], root_fillet["end"], float(root_fillet["sweep"]),
            {"kind": "root", "side": "center"},
        ),
        _profile_segment("groove_segment_3", root_fillet["end"], right_tip["tangent"]),
        _profile_arc(
            "groove_arc_tip_right", right_tip["center"], float(profile["tip_radius"]),
            right_tip["tangent"], right_tip["outer"], -float(right_tip["sweep"]),
            {"kind": "tip", "side": "right"},
        ),
        _profile_segment("groove_segment_4", right_tip["outer"], closure_right),
        _profile_segment("groove_segment_5", closure_right, closure_left),
    ]
    parameterization = (
        _build_curvilinear_parameterization(
            groove_entities=groove_entities,
            sharp_tip_left=sharp_tip_left,
            sharp_tip_right=sharp_tip_right,
            root_control=root_control,
            outside_radius=outside_radius,
            root_radius=root_radius,
            tip_radius=float(profile["tip_radius"]),
            root_fillet_radius=float(profile["root_fillet_radius"]),
            closure_overshoot=closure_radius - outside_radius,
            pitch=float(profile["pitch"]),
            tooth_count=int(tooth_count),
            face_width=float(face_width),
            pitch_line_offset=float(profile["pitch_line_offset"]),
            groove_depth=float(profile["groove_depth"]),
        )
        if parameterize
        else {"variables": [], "auxiliary_entities": [], "constraints": [], "dimensions": [], "sketch_options": {}}
    )
    sketch_entities = groove_entities + list(parameterization["auxiliary_entities"])
    operations = [
        {
            "id": "blank", "scenario": "cylindrical_blank",
            "params": {
                "name": f"{requested_name} blank", "sketch_name": f"{requested_name} blank sketch",
                "outside_diameter": float(derived["outside_diameter"]), "width": float(face_width),
                "plane": "YOZ", "axis": "x_axis", "parameterize": bool(parameterize),
                "variable_plan": list(parameterization["variables"]),
                "constraints": ([{"kind": "fixed_point", "target": "blank_circle", "index": 0}] if parameterize else []),
                "dimensions": ([{"kind": "circle_radius", "target": "blank_circle", "name": "TB_BLANK_OR_DIM", "variable_name": "TB_OR", "value": outside_radius, "driving": True}] if parameterize else []),
                "operation_variable_bindings": ([{"target": "extrusion", "parameter_note": "Distance 1", "parameter_note_aliases": ["Distance 1", "Length 1", "Depth 1", "Расстояние 1", "Длина 1", "Глубина 1"], "expression": "TB_B", "role": "blank_width"}] if parameterize else []),
                "sketch_options": ({"constraints": {"enabled": True}, "dimensions": {"enabled": True, "driving": True}, "parameterization_order": "constraints_first"} if parameterize else {}),
            },
        },
        {
            "id": "groove_sketch", "scenario": "numeric_profile_sketch",
            "params": {
                "name": f"{requested_name} one groove", "plane": "YOZ",
                "entities": sketch_entities, "parameterize": bool(parameterize),
                "constraints": list(parameterization["constraints"]),
                "dimensions": list(parameterization["dimensions"]),
                "sketch_options": dict(parameterization["sketch_options"]),
                "require_fully_defined": bool(parameterize),
            },
        },
        {
            "id": "groove_cut", "scenario": "cut_extrusion",
            "params": {
                "name": f"{requested_name} one groove cut", "sketch": "groove_sketch.sketch",
                "direction": "both", "end_condition": "through_all", "require_fully_defined": bool(parameterize),
            },
        },
        {
            "id": "groove_pattern", "scenario": "circular_pattern",
            "params": {
                "name": f"{requested_name} groove pattern", "source": "groove_cut.feature",
                "axis": "blank.axis", "count": int(tooth_count), "span_angle": 360.0,
                "parameterize": bool(parameterize), "parameter_prefix": "TB",
                "count_variable": "TB_Z", "span_angle_variable": "TB_SPAN",
                "angle_step_variable": "TB_STEP",
            },
        },
    ]
    return {
        "ok": True,
        "stage": ("curvilinear_timing_pulley_parameterized_mechanics" if parameterize else "curvilinear_timing_pulley_numeric_mechanics"),
        "name": requested_name,
        "profile_preview": preview,
        "workflow": {
            "scenario": "workflow",
            "params": {
                "name": requested_name,
                "operations": operations,
                "exports": [
                    {"name": "blank_body", "ref": "blank.body"},
                    {"name": "groove_cut", "ref": "groove_cut.feature"},
                    {"name": "groove_pattern", "ref": "groove_pattern.feature"},
                ],
            },
        },
        "geometry": {
            "groove_vertices": [list(closure_left), list(sharp_tip_left), list(root_control), list(sharp_tip_right), list(closure_right)],
            "groove_entities": groove_entities,
            "closure_radius": closure_radius,
            "outside_radius": outside_radius,
            "root_radius": root_radius,
            "root_control": list(root_control),
            "root_fillet": root_fillet,
            "auxiliary_entities": list(parameterization["auxiliary_entities"]),
            "tip_transitions": {
                "left": {key: value for key, value in left_tip.items() if key != "distance_from_sharp_tip"},
                "right": {key: value for key, value in right_tip.items() if key != "distance_from_sharp_tip"},
            },
        },
        "parameterization": {
            "part_variables": bool(parameterize), "sketch_constraints": bool(parameterize),
            "sketch_dimensions": bool(parameterize), "operation_variables": bool(parameterize),
            "variables": list(parameterization["variables"]),
            "constraints": list(parameterization["constraints"]),
            "dimensions": list(parameterization["dimensions"]),
        },
        "verification": {
            "require_single_body": True,
            "require_closed_primary_contour": True,
            "require_volume_decrease_after_cut": True,
            "require_pattern_count": int(tooth_count),
            "require_pattern_span_degrees": 360.0,
            "expected_outside_diameter": float(derived["outside_diameter"]),
            "expected_root_diameter": float(derived["root_diameter"]),
        },
    }
