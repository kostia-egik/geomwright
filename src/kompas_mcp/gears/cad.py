"""Layer 3 create-only CAD plan for one external spur gear.

The plan owns a new part: a cylindrical blank, one numeric tooth-space cut, and
a circular pattern. The tooth-space flanks are single interpolating cubic
B-splines (KOMPAS spline entities) instead of dense segment chains, so the cut
contour is smooth; only the cap and the root-adjacent closure use exact arcs and
segments. The plan is create-only and numeric, matching the accepted KOMPAS
numeric-profile path. High-level code builds this plan; only
`bridge/kompas_bridge.py` executes COM calls.
"""
from __future__ import annotations

import math
from typing import Any

from .involute import build_spur_gear_geometry
from .nurbs import bezier_chain, spline_max_deviation
from .preview import build_spur_gear_preview
from .spec import SpurGearRequest

FAMILY_CODE = 8
OWNERSHIP_SCHEMA = "geomwright.managed_gear_spur"
PLAN_STAGE = "gear_spur_cad_plan"
STANDARD_CODES = {"gost_13755_2015": 1}
MODIFICATION_CODES = {"a": 1, "b": 2, "c": 3, "d": 4, "custom": 0}


def _simplify_open(points: list[list[float]], tolerance: float) -> list[list[float]]:
    """Ramer-Douglas-Peucker decimation that keeps the first and last point."""
    unique: list[list[float]] = []
    for point in points:
        candidate = [float(point[0]), float(point[1])]
        if not unique or math.dist(unique[-1], candidate) > 1e-9:
            unique.append(candidate)
    if len(unique) <= 2:
        return unique

    def simplify(sequence: list[list[float]]) -> list[list[float]]:
        if len(sequence) < 3:
            return sequence
        first, last = sequence[0], sequence[-1]
        dx, dy = last[0] - first[0], last[1] - first[1]
        length = math.hypot(dx, dy)
        worst = -1.0
        worst_index = 0
        for index in range(1, len(sequence) - 1):
            point = sequence[index]
            if length <= 1e-12:
                distance = math.dist(point, first)
            else:
                distance = abs(dx * (point[1] - first[1]) - dy * (point[0] - first[0])) / length
            if distance > worst:
                worst = distance
                worst_index = index
        if worst <= tolerance:
            return [first, last]
        left = simplify(sequence[: worst_index + 1])
        right = simplify(sequence[worst_index:])
        return [*left[:-1], *right]

    return simplify(unique)


def _polygon_area(points: list[list[float]]) -> float:
    area = 0.0
    for index in range(len(points) - 1):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _clip_to_circle(polygon: list[list[float]], radius: float, segments: int = 720) -> list[list[float]]:
    """Sutherland-Hodgman clip of a closed polygon to a circle polygon."""
    clip = [
        [radius * math.sin(2.0 * math.pi * index / segments),
         radius * math.cos(2.0 * math.pi * index / segments)]
        for index in range(segments)
    ]

    def inside(point: list[float], a: list[float], b: list[float]) -> bool:
        return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]) <= 1e-12

    def intersect(p: list[float], q: list[float], a: list[float], b: list[float]) -> list[float]:
        denominator = (p[0] - q[0]) * (a[1] - b[1]) - (p[1] - q[1]) * (a[0] - b[0])
        if abs(denominator) < 1e-15:
            return [q[0], q[1]]
        px = ((p[0] * q[1] - p[1] * q[0]) * (a[0] - b[0]) - (p[0] - q[0]) * (a[0] * b[1] - a[1] * b[0])) / denominator
        py = ((p[0] * q[1] - p[1] * q[0]) * (a[1] - b[1]) - (p[1] - q[1]) * (a[0] * b[1] - a[1] * b[0])) / denominator
        return [px, py]

    output = [list(point) for point in polygon]
    for index in range(len(clip)):
        a = clip[index]
        b = clip[(index + 1) % len(clip)]
        if not output:
            break
        source = output
        output = []
        start = source[-1]
        for end in source:
            if inside(end, a, b):
                if not inside(start, a, b):
                    output.append(intersect(start, end, a, b))
                output.append(end)
            elif inside(start, a, b):
                output.append(intersect(start, end, a, b))
            start = end
    return output


def _polar(radius: float, angle: float) -> list[float]:
    return [radius * math.sin(angle), radius * math.cos(angle)]


def _clockwise(start: list[float], middle: list[float], end: list[float]) -> bool:
    cross = (middle[0] - start[0]) * (end[1] - middle[1]) - (middle[1] - start[1]) * (end[0] - middle[0])
    return cross < 0.0


def _entity_endpoints(entity: dict) -> tuple[list[float], list[float]] | None:
    kind = str(entity.get("kind") or "")
    if kind in ("segment", "arc"):
        return list(entity["start"]), list(entity["end"])
    if kind == "nurbs":
        points = list(entity.get("points") or [])
        if len(points) >= 2:
            return list(points[0]), list(points[-1])
    return None


def _validate_entity_contour(entities: list[dict], module_mm: float) -> None:
    if len(entities) < 3:
        raise ValueError("Gear tooth-space contour needs at least three entities")
    tolerance = max(1e-6, module_mm * 1e-6)
    for index, entity in enumerate(entities):
        endpoints = _entity_endpoints(entity)
        if endpoints is None:
            raise ValueError("Gear contour entity has no usable endpoints")
        following = entities[(index + 1) % len(entities)]
        following_endpoints = _entity_endpoints(following)
        if following_endpoints is None:
            raise ValueError("Gear contour entity has no usable endpoints")
        if math.dist(endpoints[1], following_endpoints[0]) > tolerance:
            raise ValueError("Gear contour entities are not connected in order")
    for entity in entities:
        if entity.get("kind") == "nurbs" and len(entity.get("points") or []) < 4:
            raise ValueError("Gear flank spline needs at least four control points")


def _nurbs_entity(spline: dict, entity_id: str) -> dict:
    return {
        "id": entity_id,
        "kind": "nurbs",
        "points": spline["points"],
        "weights": spline["weights"],
        "knots": spline["knots"],
        "degree": spline["degree"],
        "closed": False,
        "style": 1,
    }


def _fit_smooth_curve(
    points: list[list[float]],
    module_mm: float,
) -> tuple[list[list[float]], dict, float]:
    """Fit one smooth Bezier chain within a bounded deviation."""
    deviation_cap = max(0.03, module_mm * 0.01)
    best = None
    for tolerance in (0.01, 0.005, 0.002, 0.001, 0.0005):
        candidate_points = _simplify_open(points, tolerance)
        if len(candidate_points) < 4:
            continue
        candidate_spline = bezier_chain(candidate_points)
        candidate_deviation = spline_max_deviation(candidate_spline, points)
        if best is None or candidate_deviation < best[2]:
            best = (candidate_points, candidate_spline, candidate_deviation)
        if candidate_deviation <= deviation_cap:
            break
    if best is None or best[2] > deviation_cap:
        raise ValueError("Gear flank spline deviation exceeds the CAD tolerance")
    return best


def build_gear_spur_plan(
    request: dict,
    *,
    name: str = "Geomwright spur gear",
) -> dict[str, Any]:
    """Build a create-only managed part plan without touching KOMPAS."""
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")
    request = SpurGearRequest.model_validate(request).model_dump(exclude_none=True)
    preview = build_spur_gear_preview(request)
    if not preview.get("success"):
        errors = ", ".join(str(item.get("code")) for item in preview.get("errors") or [])
        raise ValueError("Gear preview rejected the request: " + (errors or "invalid geometry"))
    geometry = build_spur_gear_geometry(request, curve_samples=260, wheel_points_per_tooth=160)
    path = geometry.gap_surface_path
    if len(path) < 8:
        raise ValueError("Gear tooth-space surface is missing")
    tip_index = max(range(len(path)), key=lambda index: math.hypot(path[index][0], path[index][1]))
    surface = path[:tip_index + 1]
    split_index = int(getattr(geometry, "surface_split_index", 0) or 0)
    if not 0 < split_index < len(surface) - 2:
        split_index = max(1, len(surface) // 2)
    root_surface = surface[:split_index + 1]
    involute_surface = surface[split_index:]
    root_points, root_spline, root_deviation = _fit_smooth_curve(root_surface, geometry.module_mm)
    involute_points, involute_spline, involute_deviation = _fit_smooth_curve(
        involute_surface, geometry.module_mm
    )
    deviation = max(root_deviation, involute_deviation)
    left_involute_points = [[-point[0], point[1]] for point in reversed(involute_points)]
    left_root_points = [[-point[0], point[1]] for point in reversed(root_points)]
    left_involute_spline = bezier_chain(left_involute_points)
    left_root_spline = bezier_chain(left_root_points)

    tip = surface[-1]
    tip_angle = math.atan2(tip[0], tip[1])
    overshoot = geometry.outside_radius + max(1.0, 0.02 * geometry.outside_radius)
    cap_out = _polar(overshoot, tip_angle)
    cap_in = _polar(geometry.outside_radius, -tip_angle)
    cap_arc_start = cap_out
    cap_arc_mid = _polar(overshoot, 0.0)
    cap_arc_end = _polar(overshoot, -tip_angle)
    entities = [
        _nurbs_entity(root_spline, "gear_space_root_right"),
        _nurbs_entity(involute_spline, "gear_space_involute_right"),
        {"id": "gear_space_cap_out", "kind": "segment", "start": tip, "end": cap_arc_start, "style": 1},
        {
            "id": "gear_space_cap_arc",
            "kind": "arc",
            "center": [0.0, 0.0],
            "radius": overshoot,
            "start": cap_arc_start,
            "end": cap_arc_end,
            "direction": _clockwise(cap_arc_start, cap_arc_mid, cap_arc_end),
            "style": 1,
        },
        {"id": "gear_space_cap_in", "kind": "segment", "start": cap_arc_end, "end": cap_in, "style": 1},
        _nurbs_entity(left_involute_spline, "gear_space_involute_left"),
        _nurbs_entity(left_root_spline, "gear_space_root_left"),
    ]
    _validate_entity_contour(entities, geometry.module_mm)

    clipped_gap = _clip_to_circle(geometry.gap_outline, geometry.outside_radius)
    gap_area = _polygon_area(clipped_gap) if len(clipped_gap) >= 3 else 0.0
    pattern_count = int(geometry.tooth_count)
    expected_section = math.pi * geometry.outside_radius ** 2 - pattern_count * gap_area
    expected_volume = expected_section * geometry.face_width_mm
    if expected_volume <= 0.0 or not math.isfinite(expected_volume):
        raise ValueError("Gear expected volume is not positive")

    x_values = [point[0] for point in geometry.full_wheel_outline]
    y_values = [point[1] for point in geometry.full_wheel_outline]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    width = geometry.face_width_mm
    expected_bounds_candidates = [
        [-width, y_min, x_min, 0.0, y_max, x_max],
        [-width, x_min, y_min, 0.0, x_max, y_max],
    ]
    operations = [
        {
            "id": "blank",
            "scenario": "cylindrical_blank",
            "params": {
                "name": f"{requested_name} blank",
                "sketch_name": f"{requested_name} blank sketch",
                "outside_diameter": 2.0 * geometry.outside_radius,
                "width": geometry.face_width_mm,
                "plane": "YOZ",
                "axis": "x_axis",
                "parameterize": False,
                "require_fully_defined": False,
            },
        },
        {
            "id": "tooth_space_sketch",
            "scenario": "numeric_profile_sketch",
            "params": {
                "name": f"{requested_name} one tooth space",
                "plane": "YOZ",
                "entities": entities,
                "parameterize": False,
                "require_fully_defined": False,
                "profile_status": "nominal_smooth_flank_numeric_profile",
            },
        },
        {
            "id": "tooth_space_cut",
            "scenario": "cut_extrusion",
            "params": {
                "name": f"{requested_name} one tooth space cut",
                "sketch": "tooth_space_sketch.sketch",
                "direction": "both",
                "end_condition": "through_all",
                "require_fully_defined": False,
            },
        },
        {
            "id": "tooth_space_pattern",
            "scenario": "circular_pattern",
            "params": {
                "name": f"{requested_name} tooth space pattern",
                "source": "tooth_space_cut.feature",
                "axis": "blank.axis",
                "count": pattern_count,
                "span_angle": 360.0,
                "parameterize": False,
            },
        },
    ]
    return {
        "ok": True,
        "stage": PLAN_STAGE,
        "plan_version": 1,
        "family": "gear_spur",
        "name": requested_name,
        "profile_request": dict(request),
        "profile_preview": preview,
        "workflow": {
            "scenario": "workflow",
            "params": {
                "name": requested_name,
                "operations": operations,
                "exports": [
                    {"name": "blank_body", "ref": "blank.body"},
                    {"name": "tooth_space_cut", "ref": "tooth_space_cut.feature"},
                    {"name": "tooth_space_pattern", "ref": "tooth_space_pattern.feature"},
                ],
            },
        },
        "geometry": {
            "outside_radius": geometry.outside_radius,
            "root_radius": geometry.root_radius,
            "pitch_radius": geometry.pitch_radius,
            "base_radius": geometry.base_radius,
            "face_width": geometry.face_width_mm,
            "tooth_count": pattern_count,
            "section_area_mm2": geometry.section_area_mm2,
            "expected_section_area_mm2": expected_section,
            "clipped_gap_area_mm2": gap_area,
            "entity_count": len(entities),
            "spline_control_points": len(root_spline["points"]) + len(involute_spline["points"]),
            "spline_deviation_mm": deviation,
        },
        "ownership": {
            "schema": OWNERSHIP_SCHEMA,
            "version": 1,
            "family_code": FAMILY_CODE,
            "standard_code": STANDARD_CODES.get(str(request.get("standard")), 0),
            "modification_code": MODIFICATION_CODES.get(str(request.get("modification")), 0),
            "source_profile": dict(request),
        },
        "verification": {
            "expected_volume_mm3": expected_volume,
            "volume_relative_tolerance": 0.01,
            "expected_bounds_mm": expected_bounds_candidates[0],
            "expected_bounds_candidates_mm": expected_bounds_candidates,
            "bounds_tolerance_mm": 0.05,
            "max_radius_mm": geometry.outside_radius,
            "face_width_mm": geometry.face_width_mm,
            "pattern_count": pattern_count,
        },
        "accuracy": {
            "profile": "analytic_involute_with_sharp_rack_trochoid",
            "profile_encoding": "root_and_involute_cubic_bezier_nurbs_per_flank_with_exact_cap_arc",
            "flank_spline_deviation_mm": deviation,
            "parameterization": "numeric_create_only",
            "representation_mode": "nominal",
            "conformity_claim": False,
        },
    }
