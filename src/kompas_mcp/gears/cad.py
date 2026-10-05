"""Layer 3 create-only CAD plan for one external spur gear.

The plan owns a new part: a cylindrical blank, one numeric tooth-space cut with
the involute/trochoid contour, and a circular pattern. It is create-only and
numeric: the sketch is not parameterized, matching the accepted silent-chain
numeric-profile path in the bridge. High-level code builds this plan; only
`bridge/kompas_bridge.py` executes COM calls.
"""
from __future__ import annotations

import math
from typing import Any

from .involute import build_spur_gear_geometry
from .preview import build_spur_gear_preview
from .spec import SpurGearRequest

FAMILY_CODE = 8
OWNERSHIP_SCHEMA = "geomwright.managed_gear_spur"
PLAN_STAGE = "gear_spur_cad_plan"
CONTOUR_CODES = {"gost_a": 1, "gost_b": 2, "gost_c": 3, "gost_d": 4, "custom": 0}


def _simplify_closed(path: list[list[float]], tolerance: float) -> list[list[float]]:
    """Ramer-Douglas-Peucker decimation that preserves the closed contour."""
    points = [list(map(float, point)) for point in path]
    if len(points) >= 2 and math.dist(points[0], points[-1]) <= 1e-9:
        points = points[:-1]
    if len(points) < 8:
        return [*points, points[0]]

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

    simplified = simplify([*points, points[0]])
    if len(simplified) < 4:
        simplified = [*points[:4], points[0]]
    return simplified


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


def _circle(a: list[float], b: list[float], c: list[float]):
    bx, by = b[0] - a[0], b[1] - a[1]
    cx, cy = c[0] - a[0], c[1] - a[1]
    det = 2.0 * (bx * cy - by * cx)
    if abs(det) < 1e-12:
        return None
    u, v = bx * bx + by * by, cx * cx + cy * cy
    center = [a[0] + (cy * u - by * v) / det, a[1] + (bx * v - cx * u) / det]
    return center, math.dist(a, center), det < 0


def contour_entities(path: list[list[float]], prefix: str) -> list[dict[str, Any]]:
    """Compact one closed numeric contour into segments and exact arcs."""
    points: list[list[float]] = []
    for point in path:
        if len(point) != 2 or not all(math.isfinite(float(value)) for value in point):
            raise ValueError("Gear contour contains invalid coordinates")
        candidate = [float(point[0]), float(point[1])]
        if not points or math.dist(points[-1], candidate) > 1e-9:
            points.append(candidate)
    if len(points) >= 2 and math.dist(points[0], points[-1]) <= 1e-9:
        points = points[:-1]
    if len(points) < 8:
        raise ValueError("Gear tooth-space contour is too short")
    entities: list[dict[str, Any]] = []
    count = len(points)
    index = 0
    while index < count - 1:
        current = points[index]
        third = min(index + 2, count - 1)
        circle = _circle(points[index], points[index + 1], points[third])
        if circle:
            center, radius, clockwise = circle
            end = index + 2
            while end + 1 < count:
                candidate = points[end + 1]
                previous = points[end]
                turn = ((previous[0] - center[0]) * (candidate[1] - center[1])
                        - (previous[1] - center[1]) * (candidate[0] - center[0]))
                if abs(math.dist(candidate, center) - radius) > 1e-7 or (turn < 0) != clockwise:
                    break
                end += 1
            if end - index >= 3:
                entities.append({
                    "id": f"{prefix}_{len(entities)}",
                    "kind": "arc",
                    "center": center,
                    "radius": radius,
                    "start": current,
                    "end": points[end],
                    "direction": clockwise,
                    "style": 1,
                })
                index = end
                continue
        dx = points[index + 1][0] - current[0]
        dy = points[index + 1][1] - current[1]
        segment_length = math.hypot(dx, dy)
        run = index + 1
        while run + 1 < count and segment_length > 1e-12:
            candidate = points[run + 1]
            cross = abs(dx * (candidate[1] - current[1]) - dy * (candidate[0] - current[0])) / segment_length
            if cross > 1e-7:
                break
            projection = (candidate[0] - current[0]) * dx + (candidate[1] - current[1]) * dy
            if projection <= 0:
                break
            run += 1
        entities.append({
            "id": f"{prefix}_{len(entities)}",
            "kind": "segment",
            "start": current,
            "end": points[run],
            "style": 1,
        })
        index = run
    # Close the contour back to its first point.
    if math.dist(entities[-1]["end"], points[0]) > 1e-9:
        entities.append({
            "id": f"{prefix}_{len(entities)}",
            "kind": "segment",
            "start": entities[-1]["end"],
            "end": points[0],
            "style": 1,
        })
    if len(entities) > 1024:
        raise ValueError("Gear tooth-space contour exceeds the bounded CAD entity budget")
    return entities


def _closed_polygon_area(points: list[list[float]]) -> float:
    area = 0.0
    for index in range(len(points) - 1):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _validate_closed_contour(points: list[list[float]], module_mm: float) -> None:
    if len(points) < 4:
        raise ValueError("Gear tooth-space contour must be a closed polyline")
    if math.dist(points[0], points[-1]) > 1e-7:
        raise ValueError("Gear tooth-space contour is not closed")
    if abs(_closed_polygon_area(points)) < 1e-6:
        raise ValueError("Gear tooth-space contour has no area")
    # Reject self-intersections before any COM call.
    def orientation(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    count = len(points) - 1
    tolerance = max(1e-12, module_mm * 1e-9)
    for first in range(count):
        a, b = points[first], points[first + 1]
        for second in range(first + 1, count):
            if second in (first, (first + 1) % count):
                continue
            if first == 0 and second == count - 1:
                continue
            c, d = points[second], points[second + 1]
            o1, o2 = orientation(a, b, c), orientation(a, b, d)
            o3, o4 = orientation(c, d, a), orientation(c, d, b)
            if o1 * o2 < -tolerance and o3 * o4 < -tolerance:
                raise ValueError("Gear tooth-space contour self-intersects")


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
    geometry = build_spur_gear_geometry(request, curve_samples=220, wheel_points_per_tooth=16)
    gap_outline = _simplify_closed(geometry.gap_outline, max(0.01, geometry.module_mm * 0.002))
    _validate_closed_contour(gap_outline, geometry.module_mm)
    entities = contour_entities(gap_outline, "gear_gap")
    pattern_count = int(geometry.tooth_count)
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
                "profile_status": "nominal_sharp_rack_numeric_profile",
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
    clipped_gap = _clip_to_circle(gap_outline, geometry.outside_radius)
    gap_area = _polygon_area(clipped_gap) if len(clipped_gap) >= 3 else 0.0
    expected_section = math.pi * geometry.outside_radius ** 2 - pattern_count * gap_area
    expected_volume = expected_section * geometry.face_width_mm
    if expected_volume <= 0.0 or not math.isfinite(expected_volume):
        raise ValueError("Gear expected volume is not positive")
    bounds_outline = build_spur_gear_geometry(
        request, curve_samples=220, wheel_points_per_tooth=160
    ).full_wheel_outline
    x_values = [point[0] for point in bounds_outline]
    y_values = [point[1] for point in bounds_outline]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    width = geometry.face_width_mm
    # The YOZ sketch may map its two axes to global Y/Z in either order.
    expected_bounds_candidates = [
        [-width, y_min, x_min, 0.0, y_max, x_max],
        [-width, x_min, y_min, 0.0, x_max, y_max],
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
            "contour_points": len(gap_outline),
        },
        "ownership": {
            "schema": OWNERSHIP_SCHEMA,
            "version": 1,
            "family_code": FAMILY_CODE,
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
            "profile_encoding": "numeric_segments_and_exact_arcs",
            "parameterization": "numeric_create_only",
            "representation_mode": "nominal",
            "conformity_claim": False,
        },
    }
