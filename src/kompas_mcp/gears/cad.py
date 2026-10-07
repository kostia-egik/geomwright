"""Layer 3 create-only CAD plans for cylindrical gears.

External plan: a cylindrical blank, one numeric tooth-space cut, and a circular
pattern. Internal plan: a ring blank with an explicit outside diameter, a
central bore at the internal tip diameter, one internal tooth-space cut, and a
circular pattern. The tooth-space flanks are single interpolating cubic
B-splines (KOMPAS spline entities) instead of dense segment chains, so the cut
contour is smooth; only the closures and the root arcs use exact arcs and
segments. The plans are create-only and numeric, matching the accepted KOMPAS
numeric-profile path. High-level code builds these plans; only
`bridge/kompas_bridge.py` executes COM calls.
"""
from __future__ import annotations

import math
from typing import Any

from .bevel import build_bevel_gear_geometry, build_bevel_gear_preview
from .bevel_spec import BevelGearRequest
from .internal import (
    build_internal_gear_geometry,
    build_internal_gear_preview,
    internal_tip_chamfer_volume,
)
from .internal_spec import InternalGearRequest
from .involute import build_spur_gear_geometry
from .nurbs import bezier_chain, spline_max_deviation
from .preview import build_spur_gear_preview
from .spec import SpurGearRequest

FAMILY_CODE = 8
OWNERSHIP_SCHEMA = "geomwright.managed_gear_spur"
PLAN_STAGE = "gear_spur_cad_plan"
INTERNAL_FAMILY_CODE = 9
INTERNAL_OWNERSHIP_SCHEMA = "geomwright.managed_gear_internal"
INTERNAL_PLAN_STAGE = "internal_gear_cad_plan"
BEVEL_FAMILY_CODE = 10
BEVEL_OWNERSHIP_SCHEMA = "geomwright.managed_gear_bevel"
BEVEL_PLAN_STAGE = "bevel_gear_cad_plan"
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


def _point_in_polygon(point: list[float], polygon: list[list[float]]) -> bool:
    x, y = float(point[0]), float(point[1])
    inside = False
    count = len(polygon)
    if count < 3:
        return False
    for index in range(count):
        x1, y1 = polygon[index - 1]
        x2, y2 = polygon[index]
        if (y1 > y) != (y2 > y):
            cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < cross:
                inside = not inside
    return inside


def _chamfer_removed_volume(geometry) -> float:
    """Material actually removed by the two end cone cuts.

    The full-ring formula overestimates the chamfer because the teeth occupy
    only part of the circumference near the tip. The material fraction is
    sampled from the analytic per-pitch outline at each cut radius.
    """
    width = geometry.tip_chamfer_mm
    depth = geometry.tip_chamfer_depth_mm
    if width <= 0.0 or depth <= 0.0 or not geometry.period_outline:
        return 0.0
    steps = 48
    samples = 180
    outside_radius = geometry.outside_radius
    tooth_count = max(1, int(geometry.tooth_count))
    radii = [outside_radius - depth + depth * index / steps for index in range(steps + 1)]
    fractions = []
    for radius in radii:
        inside = 0
        for sample in range(samples):
            angle = 2.0 * math.pi * sample / samples
            point = [radius * math.sin(angle), radius * math.cos(angle)]
            if _point_in_polygon(point, geometry.period_outline):
                inside += 1
        fractions.append(min(1.0, inside * tooth_count / float(samples)))
    ring_areas = [
        fractions[index] * math.pi * (radii[index + 1] ** 2 - radii[index] ** 2)
        for index in range(steps)
    ]
    removed_area = [0.0] * (steps + 1)
    for index in range(steps - 1, -1, -1):
        removed_area[index] = removed_area[index + 1] + ring_areas[index]
    axial_step = width / steps
    return 2.0 * sum(removed_area[index] * axial_step for index in range(steps))


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
    chamfer_volume = 0.0
    if geometry.tip_chamfer_mm > 0.0:
        chamfer_volume = _chamfer_removed_volume(geometry)
    expected_volume = expected_section * geometry.face_width_mm - chamfer_volume
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
    helical = geometry.helix_angle_rad > 1e-9
    if helical:
        cut_operation = {
            "id": "tooth_space_cut",
            "scenario": "helical_cut_evolution",
            "params": {
                "name": f"{requested_name} one tooth space cut",
                "sketch": "tooth_space_sketch.sketch",
                "axis": "blank.axis",
                "reference_diameter": 2.0 * geometry.pitch_radius,
                "anchor_radius_mm": 0.0,
                "lead": geometry.lead_mm,
                "height": geometry.face_width_mm,
                "hand": geometry.hand,
                "start_x": 0.0,
                "start_angle_deg": 0.0,
                "building_direction": False,
                "require_fully_defined": False,
            },
        }
    else:
        cut_operation = {
            "id": "tooth_space_cut",
            "scenario": "cut_extrusion",
            "params": {
                "name": f"{requested_name} one tooth space cut",
                "sketch": "tooth_space_sketch.sketch",
                "direction": "both",
                "end_condition": "through_all",
                "require_fully_defined": False,
            },
        }
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
        cut_operation,
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
    if geometry.tip_chamfer_mm > 0.0:
        chamfer_width = geometry.tip_chamfer_mm
        chamfer_depth = geometry.tip_chamfer_depth_mm
        chamfer_radius = geometry.outside_radius
        face_width = geometry.face_width_mm
        chamfer_operations = [
            {
                "id": "tip_chamfer_face_a",
                "scenario": "rotational_cut",
                "params": {
                    "name": f"{requested_name} tip chamfer A",
                    "plane": "XOY",
                    "axis": "blank.axis",
                    "profile_points": [
                        [-face_width, chamfer_radius - chamfer_depth],
                        [-face_width + chamfer_width, chamfer_radius],
                        [-face_width, chamfer_radius],
                    ],
                    "angle_degrees": 360.0,
                    "require_fully_defined": False,
                },
            },
            {
                "id": "tip_chamfer_face_b",
                "scenario": "rotational_cut",
                "params": {
                    "name": f"{requested_name} tip chamfer B",
                    "plane": "XOY",
                    "axis": "blank.axis",
                    "profile_points": [
                        [0.0, chamfer_radius - chamfer_depth],
                        [-chamfer_width, chamfer_radius],
                        [0.0, chamfer_radius],
                    ],
                    "angle_degrees": 360.0,
                    "require_fully_defined": False,
                },
            },
        ]
        # Chamfer the blank before the tooth-space cut: geometrically identical
        # to chamfering the finished teeth, but the expensive pattern rebuild
        # stays the last feature in the tree.
        operations = [operations[0], *chamfer_operations, *operations[1:]]
    exports = [
        {"name": "blank_body", "ref": "blank.body"},
        {"name": "tooth_space_cut", "ref": "tooth_space_cut.feature"},
        {"name": "tooth_space_pattern", "ref": "tooth_space_pattern.feature"},
    ]
    if geometry.tip_chamfer_mm > 0.0:
        exports.extend(
            [
                {"name": "tip_chamfer_a", "ref": "tip_chamfer_face_a.feature"},
                {"name": "tip_chamfer_b", "ref": "tip_chamfer_face_b.feature"},
            ]
        )
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
                "exports": exports,
            },
        },
        "geometry": {
            "outside_radius": geometry.outside_radius,
            "root_radius": geometry.root_radius,
            "pitch_radius": geometry.pitch_radius,
            "base_radius": geometry.base_radius,
            "face_width": geometry.face_width_mm,
            "tooth_count": pattern_count,
            "helix_angle_deg": math.degrees(geometry.helix_angle_rad),
            "hand": geometry.hand,
            "transverse_module_mm": geometry.transverse_module_mm,
            "base_helix_angle_deg": math.degrees(geometry.base_helix_angle_rad),
            "axial_pitch_mm": geometry.axial_pitch_mm,
            "lead_mm": geometry.lead_mm,
            "axial_overlap": (
                geometry.face_width_mm / geometry.axial_pitch_mm
                if geometry.axial_pitch_mm > 0.0
                else 0.0
            ),
            "cut_scenario": "helical_cut_evolution" if helical else "cut_extrusion",
            "tip_chamfer_mm": geometry.tip_chamfer_mm,
            "tip_chamfer_angle_deg": geometry.tip_chamfer_angle_deg,
            "tip_chamfer_depth_mm": geometry.tip_chamfer_depth_mm,
            "tip_chamfer_volume_mm3": chamfer_volume,
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
            "profile": (
                "analytic_transverse_involute_with_sharp_rack_trochoid"
                if helical
                else "analytic_involute_with_sharp_rack_trochoid"
            ),
            "profile_encoding": "root_and_involute_cubic_bezier_nurbs_per_flank_with_exact_cap_arc",
            "sweep": (
                "cut_evolution_along_cylindric_spiral_lead_%s_mm" % round(geometry.lead_mm, 6)
                if helical
                else "cut_extrusion_through_all"
            ),
            "tip_chamfer": (
                "two_cut_rotations_width_%s_angle_%s"
                % (round(geometry.tip_chamfer_mm, 6), round(geometry.tip_chamfer_angle_deg, 3))
                if geometry.tip_chamfer_mm > 0.0
                else "none"
            ),
            "flank_spline_deviation_mm": deviation,
            "parameterization": "numeric_create_only",
            "representation_mode": "nominal",
            "conformity_claim": False,
        },
    }


def build_internal_gear_plan(
    request: dict,
    *,
    name: str = "Geomwright internal gear",
) -> dict[str, Any]:
    """Build a create-only managed internal-gear (ring gear) plan."""
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")
    request = InternalGearRequest.model_validate(request).model_dump(exclude_none=True)
    preview = build_internal_gear_preview(request)
    if not preview.get("success"):
        errors = ", ".join(str(item.get("code")) for item in preview.get("errors") or [])
        raise ValueError("Internal gear preview rejected the request: " + (errors or "invalid geometry"))
    geometry = build_internal_gear_geometry(request, wheel_points_per_tooth=200)
    if len(geometry.right_involute_path) < 4:
        raise ValueError("Internal gear flank is missing")
    right_path = [list(point) for point in geometry.right_involute_path]
    left_path = [[-point[0], point[1]] for point in reversed(right_path)]
    _, right_spline, right_deviation = _fit_smooth_curve(right_path, geometry.module_mm)
    _, left_spline, left_deviation = _fit_smooth_curve(left_path, geometry.module_mm)
    deviation = max(right_deviation, left_deviation)

    entities: list[dict] = [_nurbs_entity(right_spline, "internal_space_involute_right")]
    tip_extension = list(geometry.tip_extension_path)
    if len(tip_extension) >= 2:
        entities.append(
            {
                "id": "internal_space_tip_extension_right",
                "kind": "segment",
                "start": list(tip_extension[0]),
                "end": list(tip_extension[1]),
                "style": 1,
            }
        )
    tip_right = list(geometry.tip_point_right)
    tip_left = list(geometry.tip_point_left)
    hole_right = list(geometry.hole_point_right)
    hole_left = list(geometry.hole_point_left)
    closure_radius = geometry.closure_radius_mm
    closure_mid = _polar(closure_radius, 0.0)
    entities.append(
        {
            "id": "internal_space_bore_right",
            "kind": "segment",
            "start": tip_right,
            "end": hole_right,
            "style": 1,
        }
    )
    entities.append(
        {
            "id": "internal_space_bore_arc",
            "kind": "arc",
            "center": [0.0, 0.0],
            "radius": closure_radius,
            "start": hole_right,
            "end": hole_left,
            "direction": _clockwise(hole_right, closure_mid, hole_left),
            "style": 1,
        }
    )
    entities.append(
        {
            "id": "internal_space_bore_left",
            "kind": "segment",
            "start": hole_left,
            "end": tip_left,
            "style": 1,
        }
    )
    left_extension = list(geometry.left_tip_extension_path)
    if len(left_extension) >= 2:
        entities.append(
            {
                "id": "internal_space_tip_extension_left",
                "kind": "segment",
                "start": list(left_extension[0]),
                "end": list(left_extension[1]),
                "style": 1,
            }
        )
    entities.append(_nurbs_entity(left_spline, "internal_space_involute_left"))
    if geometry.root_transition_mode == "cubic_bezier_root_transition":
        left_controls = list(geometry.left_transition_controls)
        if len(left_controls) == 4:
            entities.append(
                _nurbs_entity(
                    {
                        "points": left_controls,
                        "weights": [1.0] * 4,
                        "knots": [0.0] * 4 + [1.0] * 4,
                        "degree": 3,
                    },
                    "internal_space_root_transition_left",
                )
            )
        root_middle = list(geometry.root_middle_arc)
        if len(root_middle) >= 2 and math.dist(root_middle[0], root_middle[-1]) > 1e-6:
            root_mid = root_middle[len(root_middle) // 2]
            entities.append(
                {
                    "id": "internal_space_root_arc",
                    "kind": "arc",
                    "center": [0.0, 0.0],
                    "radius": geometry.root_radius,
                    "start": list(geometry.left_fillet_end),
                    "end": list(geometry.right_fillet_end),
                    "direction": _clockwise(
                        list(geometry.left_fillet_end), root_mid, list(geometry.right_fillet_end)
                    ),
                    "style": 1,
                }
            )
        right_controls = list(reversed(geometry.right_transition_controls))
        if len(right_controls) == 4:
            entities.append(
                _nurbs_entity(
                    {
                        "points": right_controls,
                        "weights": [1.0] * 4,
                        "knots": [0.0] * 4 + [1.0] * 4,
                        "degree": 3,
                    },
                    "internal_space_root_transition_right",
                )
            )
    else:
        root_point_right = list(geometry.root_point_right)
        root_point_left = list(geometry.root_point_left)
        root_mid = _polar(geometry.root_radius, 0.0)
        entities.append(
            {
                "id": "internal_space_root_arc",
                "kind": "arc",
                "center": [0.0, 0.0],
                "radius": geometry.root_radius,
                "start": root_point_left,
                "end": root_point_right,
                "direction": _clockwise(root_point_left, root_mid, root_point_right),
                "style": 1,
            }
        )
    _validate_entity_contour(entities, geometry.module_mm)

    pattern_count = int(geometry.tooth_count)
    tip_chamfer_volume = internal_tip_chamfer_volume(
        geometry,
        width_mm=geometry.tip_chamfer_mm,
        angle_deg=geometry.tip_chamfer_angle_deg,
    )
    expected_section = geometry.section_area_mm2
    expected_volume = expected_section * geometry.face_width_mm - tip_chamfer_volume
    if expected_volume <= 0.0 or not math.isfinite(expected_volume):
        raise ValueError("Internal gear expected volume is not positive")

    ring_radius = geometry.ring_outside_radius
    width = geometry.face_width_mm
    expected_bounds = [-width, -ring_radius, -ring_radius, 0.0, ring_radius, ring_radius]
    helical = geometry.helix_angle_rad > 1e-9
    if helical:
        tooth_space_cut = {
            "id": "tooth_space_cut",
            "scenario": "helical_cut_evolution",
            "params": {
                "name": f"{requested_name} one internal tooth space cut",
                "sketch": "tooth_space_sketch.sketch",
                "axis": "blank.axis",
                "reference_diameter": 2.0 * geometry.pitch_radius,
                "anchor_radius_mm": 0.0,
                "lead": geometry.lead_mm,
                "height": geometry.face_width_mm,
                "hand": geometry.hand,
                "start_x": 0.0,
                "start_angle_deg": 0.0,
                "building_direction": False,
                "require_fully_defined": False,
            },
        }
    else:
        tooth_space_cut = {
            "id": "tooth_space_cut",
            "scenario": "cut_extrusion",
            "params": {
                "name": f"{requested_name} one internal tooth space cut",
                "sketch": "tooth_space_sketch.sketch",
                "direction": "both",
                "end_condition": "through_all",
                "require_fully_defined": False,
            },
        }
    operations: list[dict] = [
        {
            "id": "blank",
            "scenario": "cylindrical_blank",
            "params": {
                "name": f"{requested_name} ring blank",
                "sketch_name": f"{requested_name} ring blank sketch",
                "outside_diameter": 2.0 * ring_radius,
                "width": width,
                "plane": "YOZ",
                "axis": "x_axis",
                "parameterize": False,
                "require_fully_defined": False,
            },
        },
    ]
    operations.append(
        {
            "id": "bore_cut",
            "scenario": "rotational_cut",
            "params": {
                "name": f"{requested_name} bore cut",
                "plane": "XOY",
                "axis": "blank.axis",
                "profile_points": [
                    [-width - 1.0, 0.0],
                    [1.0, 0.0],
                    [1.0, geometry.outside_radius],
                    [-width - 1.0, geometry.outside_radius],
                ],
                "angle_degrees": 360.0,
                "require_fully_defined": False,
            },
        }
    )
    if geometry.tip_chamfer_mm > 0.0:
        tip_depth = geometry.tip_chamfer_depth_mm
        tip_width = geometry.tip_chamfer_mm
        tip_radius = geometry.outside_radius
        operations.extend(
            [
                {
                    "id": "tip_chamfer_face_a",
                    "scenario": "rotational_cut",
                    "params": {
                        "name": f"{requested_name} tip chamfer A",
                        "plane": "XOY",
                        "axis": "blank.axis",
                        "profile_points": [
                            [-width, tip_radius],
                            [-width, tip_radius + tip_depth],
                            [-width + tip_width, tip_radius],
                        ],
                        "angle_degrees": 360.0,
                        "require_fully_defined": False,
                    },
                },
                {
                    "id": "tip_chamfer_face_b",
                    "scenario": "rotational_cut",
                    "params": {
                        "name": f"{requested_name} tip chamfer B",
                        "plane": "XOY",
                        "axis": "blank.axis",
                        "profile_points": [
                            [0.0, tip_radius],
                            [0.0, tip_radius + tip_depth],
                            [-tip_width, tip_radius],
                        ],
                        "angle_degrees": 360.0,
                        "require_fully_defined": False,
                    },
                },
            ]
        )
    operations.extend(
        [
            {
                "id": "tooth_space_sketch",
                "scenario": "numeric_profile_sketch",
                "params": {
                    "name": f"{requested_name} one internal tooth space",
                    "plane": "YOZ",
                    "entities": entities,
                    "parameterize": False,
                    "require_fully_defined": False,
                    "profile_status": "nominal_internal_space_numeric_profile",
                },
            },
            tooth_space_cut,
            {
                "id": "tooth_space_pattern",
                "scenario": "circular_pattern",
                "params": {
                    "name": f"{requested_name} internal tooth space pattern",
                    "source": "tooth_space_cut.feature",
                    "axis": "blank.axis",
                    "count": pattern_count,
                    "span_angle": 360.0,
                    "parameterize": False,
                },
            },
        ]
    )
    exports = [
        {"name": "ring_body", "ref": "blank.body"},
        {"name": "bore_cut", "ref": "bore_cut.feature"},
        {"name": "tooth_space_cut", "ref": "tooth_space_cut.feature"},
        {"name": "tooth_space_pattern", "ref": "tooth_space_pattern.feature"},
    ]
    if geometry.tip_chamfer_mm > 0.0:
        exports.extend(
            [
                {"name": "tip_chamfer_a", "ref": "tip_chamfer_face_a.feature"},
                {"name": "tip_chamfer_b", "ref": "tip_chamfer_face_b.feature"},
            ]
        )
    return {
        "ok": True,
        "stage": INTERNAL_PLAN_STAGE,
        "plan_version": 1,
        "family": "gear_internal",
        "name": requested_name,
        "profile_request": dict(request),
        "profile_preview": preview,
        "workflow": {
            "scenario": "workflow",
            "params": {
                "name": requested_name,
                "operations": operations,
                "exports": exports,
            },
        },
        "geometry": {
            "ring_outside_radius": ring_radius,
            "tip_radius": geometry.outside_radius,
            "root_radius": geometry.root_radius,
            "pitch_radius": geometry.pitch_radius,
            "base_radius": geometry.base_radius,
            "closure_radius": closure_radius,
            "face_width": width,
            "tooth_count": pattern_count,
            "helix_angle_deg": math.degrees(geometry.helix_angle_rad),
            "hand": geometry.hand,
            "transverse_module_mm": geometry.transverse_module_mm,
            "base_helix_angle_deg": math.degrees(geometry.base_helix_angle_rad),
            "axial_pitch_mm": geometry.axial_pitch_mm,
            "lead_mm": geometry.lead_mm,
            "axial_overlap": geometry.axial_overlap,
            "cut_scenario": "helical_cut_evolution" if helical else "cut_extrusion",
            "space_area_mm2": geometry.space_area_mm2,
            "section_area_mm2": geometry.section_area_mm2,
            "entity_count": len(entities),
            "spline_control_points": len(right_spline["points"]) + len(left_spline["points"]),
            "spline_deviation_mm": deviation,
            "tip_below_base": geometry.tip_below_base,
            "root_transition_mode": geometry.root_transition_mode,
            "root_transition_size_mm": geometry.root_transition_size_mm,
            "tip_chamfer_mm": geometry.tip_chamfer_mm,
            "tip_chamfer_angle_deg": geometry.tip_chamfer_angle_deg,
            "tip_chamfer_depth_mm": geometry.tip_chamfer_depth_mm,
            "tip_chamfer_volume_mm3": tip_chamfer_volume,
        },
        "ownership": {
            "schema": INTERNAL_OWNERSHIP_SCHEMA,
            "version": 1,
            "family_code": INTERNAL_FAMILY_CODE,
            "standard_code": STANDARD_CODES.get(str(request.get("standard")), 0),
            "modification_code": MODIFICATION_CODES.get(str(request.get("modification")), 0),
            "source_profile": dict(request),
        },
        "verification": {
            "expected_volume_mm3": expected_volume,
            "volume_relative_tolerance": 0.01,
            "expected_bounds_mm": expected_bounds,
            "expected_bounds_candidates_mm": [expected_bounds],
            "bounds_tolerance_mm": 0.05,
            "max_radius_mm": ring_radius,
            "face_width_mm": width,
            "pattern_count": pattern_count,
        },
        "accuracy": {
            "profile": (
                "analytic_transverse_involute_with_nominal_tip_extension_and_cubic_bezier_root_transition"
                if geometry.tip_below_base
                else "analytic_transverse_involute_with_cubic_bezier_root_transition"
            ),
            "profile_encoding": "involute_and_root_transition_cubic_bezier_nurbs_per_flank_with_bore_arcs",
            "root_fillet": (
                "cubic_bezier_transition_scale_%s_mm" % round(geometry.root_transition_size_mm, 6)
                if geometry.root_transition_mode == "cubic_bezier_root_transition"
                else "sharp_nominal_root"
            ),
            "tip_chamfer": (
                "two_cut_rotations_width_%s_angle_%s"
                % (round(geometry.tip_chamfer_mm, 6), round(geometry.tip_chamfer_angle_deg, 3))
                if geometry.tip_chamfer_mm > 0.0
                else "none"
            ),
            "sweep": (
                "cut_evolution_along_cylindric_spiral_lead_%s_mm" % round(geometry.lead_mm, 6)
                if helical
                else "cut_extrusion_through_all"
            ),
            "flank_spline_deviation_mm": deviation,
            "parameterization": "numeric_create_only",
            "representation_mode": "nominal",
            "conformity_claim": False,
        },
    }


def _mirror_spline(spline: dict) -> dict:
    """Mirror a fitted Bezier-chain spline across the Y=0 plane and reverse it."""
    knots = [float(value) for value in spline["knots"]]
    total = knots[-1]
    return {
        "degree": int(spline["degree"]),
        "points": [[-float(point[0]), float(point[1])] for point in reversed(spline["points"])],
        "weights": [float(value) for value in reversed(spline["weights"])],
        "knots": [total - float(value) for value in reversed(knots)],
    }


def _bevel_virtual_entities(geometry) -> tuple[list[dict], dict]:
    """Fit the virtual tooth-space curves once in the back-cone plane frame.

    All frontal cut sections are homothetic copies of the same virtual contour,
    so fitting the virtual root/involute paths once and scaling the control
    points keeps the two section sketches exactly corresponding.
    """
    surface = geometry.virtual_surface_path
    split = int(geometry.virtual_surface_split_index)
    root_path = surface[: split + 1]
    involute_path = surface[split:]
    root_points, root_spline, root_deviation = _fit_smooth_curve(root_path, geometry.module_mm)
    involute_points, involute_spline, involute_deviation = _fit_smooth_curve(
        involute_path, geometry.module_mm
    )
    cap_points = [list(point) for point in geometry.virtual_cap_points]
    cap_segments = []
    for index in range(len(cap_points) - 1):
        cap_segments.append(
            {
                "id": "bevel_space_cap_%d" % index,
                "kind": "segment",
                "start": cap_points[index],
                "end": cap_points[index + 1],
                "style": 1,
            }
        )
    left_involute_spline = _mirror_spline(involute_spline)
    left_root_spline = _mirror_spline(root_spline)
    entities = [
        _nurbs_entity(root_spline, "bevel_space_root_right"),
        _nurbs_entity(involute_spline, "bevel_space_involute_right"),
        *cap_segments,
        _nurbs_entity(left_involute_spline, "bevel_space_involute_left"),
        _nurbs_entity(left_root_spline, "bevel_space_root_left"),
    ]
    return entities, {
        "root_deviation_mm": root_deviation,
        "involute_deviation_mm": involute_deviation,
        "deviation_mm": max(root_deviation, involute_deviation),
        "root_control_points": len(root_spline["points"]),
        "involute_control_points": len(involute_spline["points"]),
        "cap_segment_count": len(cap_segments),
        "root_samples": len(root_points),
        "involute_samples": len(involute_points),
        "cap_samples": len(cap_points),
    }


def _bevel_entities_3d(entities_2d: list[dict], frame: dict, scale: float) -> list[dict]:
    """Lift virtual-plane (u, v) entities to the cone-normal section at `scale`."""

    apex = [float(value) for value in frame["apex"]]
    e1 = [float(value) for value in frame["e1"]]
    e2 = [float(value) for value in frame["e2"]]

    def point3(point) -> list[float]:
        u_value = float(point[0]) * scale
        v_value = float(point[1]) * scale
        return [
            apex[index] * scale + v_value * e1[index] + u_value * e2[index]
            for index in range(3)
        ]

    result = []
    for entity in entities_2d:
        item = dict(entity)
        if item["kind"] == "nurbs":
            item["points3"] = [point3(point) for point in item["points"]]
        elif item["kind"] == "segment":
            item["start3"] = point3(item["start"])
            item["end3"] = point3(item["end"])
        else:
            raise ValueError("Bevel section entities must be NURBS or segments")
        result.append(item)
    return result


def build_bevel_gear_plan(
    request: dict,
    *,
    name: str = "Geomwright bevel gear",
) -> dict[str, Any]:
    """Build a create-only managed straight-bevel-gear plan without touching KOMPAS."""
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")
    request = BevelGearRequest.model_validate(request).model_dump(exclude_none=True)
    preview = build_bevel_gear_preview(request)
    if not preview.get("success"):
        errors = ", ".join(str(item.get("code")) for item in preview.get("errors") or [])
        raise ValueError("Bevel gear preview rejected the request: " + (errors or "invalid geometry"))
    geometry = build_bevel_gear_geometry(request, curve_samples=260)
    if not geometry.blank_profile or not geometry.virtual_surface_path:
        raise ValueError("Bevel gear blank profile or virtual flank is missing")
    virtual_entities, outer_report = _bevel_virtual_entities(geometry)
    _validate_entity_contour(virtual_entities, geometry.module_mm)
    outer_scale = float(geometry.section_outer_cone_distance_mm) / float(
        geometry.outer_cone_distance_mm
    )
    inner_scale = float(geometry.section_inner_cone_distance_mm) / float(
        geometry.outer_cone_distance_mm
    )
    outer_entities = _bevel_entities_3d(virtual_entities, geometry.cone_frame, outer_scale)
    inner_entities = _bevel_entities_3d(virtual_entities, geometry.cone_frame, inner_scale)
    deviation = float(outer_report["deviation_mm"])
    cos_delta = math.cos(geometry.pitch_cone_angle_rad)
    sin_delta = math.sin(geometry.pitch_cone_angle_rad)
    outer_cone_distance = float(geometry.section_outer_cone_distance_mm)
    inner_cone_distance = float(geometry.section_inner_cone_distance_mm)
    axis_length = max(float(geometry.outer_cone_distance_mm), outer_cone_distance) * 1.05
    axis_outer = [-axis_length * cos_delta, 0.0, axis_length * sin_delta]
    axis_line = [[0.0, 0.0, 0.0], axis_outer]
    outer_anchor = [
        -outer_cone_distance * cos_delta,
        0.0,
        outer_cone_distance * sin_delta,
    ]
    inner_anchor = [
        -inner_cone_distance * cos_delta,
        0.0,
        inner_cone_distance * sin_delta,
    ]

    pattern_count = int(geometry.tooth_count)
    expected_volume = float(geometry.expected_volume_mm3)
    if expected_volume <= 0.0 or not math.isfinite(expected_volume):
        raise ValueError("Bevel gear expected volume is not positive")
    expected_bounds = [float(value) for value in geometry.expected_bounds_mm]
    max_radius = float(geometry.tip_corner_radius_mm)
    x_max = max(float(geometry.front_face_x_mm), float(geometry.inner_tip_corner_x_mm))
    disk_bounds = [
        float(geometry.back_face_x_mm), -max_radius, -max_radius,
        x_max, max_radius, max_radius,
    ]
    operations = [
        {
            "id": "blank",
            "scenario": "revolved_profile_blank",
            "params": {
                "name": "%s blank" % requested_name,
                "sketch_name": "%s blank sketch" % requested_name,
                "profile_points": [
                    [float(point[0]), float(point[1])] for point in geometry.blank_profile
                ],
                "parameterize": False,
                "require_fully_defined": False,
            },
        },
        {
            "id": "tooth_space_outer",
            "scenario": "section_profile_sketch",
            "params": {
                "name": "%s tooth space outer section" % requested_name,
                "sketch_name": "%s tooth space outer section" % requested_name,
                "plane_mode": "perpendicular_to_axis",
                "anchor": outer_anchor,
                "axis_line": axis_line,
                "entities": outer_entities,
                "require_closure": True,
                "profile_status": "nominal_tredgold_projection_outer_cone_section",
            },
        },
        {
            "id": "tooth_space_inner",
            "scenario": "section_profile_sketch",
            "params": {
                "name": "%s tooth space inner section" % requested_name,
                "sketch_name": "%s tooth space inner section" % requested_name,
                "plane_mode": "perpendicular_to_axis",
                "anchor": inner_anchor,
                "axis_line": axis_line,
                "entities": inner_entities,
                "require_closure": True,
                "profile_status": "nominal_tredgold_projection_inner_cone_section",
            },
        },
        {
            "id": "tooth_space_cut",
            "scenario": "loft_cut",
            "params": {
                "name": "%s one tooth space cut" % requested_name,
                "sections": ["tooth_space_outer.sketch", "tooth_space_inner.sketch"],
                "require_material_removal": True,
            },
        },
        {
            "id": "tooth_space_pattern",
            "scenario": "circular_pattern",
            "params": {
                "name": "%s tooth space pattern" % requested_name,
                "source": "tooth_space_cut.feature",
                "axis": "blank.axis",
                "count": pattern_count,
                "span_angle": 360.0,
                "parameterize": False,
            },
        },
    ]
    exports = [
        {"name": "blank_body", "operation_id": "blank", "output_key": "body"},
        {"name": "blank_sketch", "operation_id": "blank", "output_key": "sketch"},
        {"name": "blank_axis", "operation_id": "blank", "output_key": "axis"},
        {"name": "tooth_space_outer", "operation_id": "tooth_space_outer", "output_key": "sketch"},
        {"name": "tooth_space_inner", "operation_id": "tooth_space_inner", "output_key": "sketch"},
        {"name": "tooth_space_cut", "operation_id": "tooth_space_cut", "output_key": "feature"},
        {"name": "tooth_space_pattern", "operation_id": "tooth_space_pattern", "output_key": "feature"},
    ]
    return {
        "ok": True,
        "stage": BEVEL_PLAN_STAGE,
        "plan_version": 1,
        "family": "gear_bevel",
        "name": requested_name,
        "profile_request": dict(request),
        "profile_preview": preview,
        "workflow": {
            "scenario": "workflow",
            "params": {
                "name": requested_name,
                "operations": operations,
                "exports": exports,
            },
        },
        "geometry": {
            "tooth_type": "straight",
            "module_mm": geometry.module_mm,
            "tooth_count": pattern_count,
            "pitch_cone_angle_deg": math.degrees(geometry.pitch_cone_angle_rad),
            "face_cone_angle_deg": math.degrees(geometry.face_cone_angle_rad),
            "root_cone_angle_deg": math.degrees(geometry.root_cone_angle_rad),
            "outer_pitch_diameter_mm": geometry.outer_pitch_diameter_mm,
            "outer_tip_diameter_mm": geometry.outer_tip_diameter_mm,
            "outer_root_diameter_mm": geometry.outer_root_diameter_mm,
            "outer_cone_distance_mm": geometry.outer_cone_distance_mm,
            "face_width_mm": geometry.face_width_mm,
            "back_face_x_mm": geometry.back_face_x_mm,
            "front_face_x_mm": geometry.front_face_x_mm,
            "back_face_radius_mm": geometry.back_face_radius_mm,
            "front_face_radius_mm": geometry.front_face_radius_mm,
            "tip_corner_radius_mm": geometry.tip_corner_radius_mm,
            "rim_back_extension_mm": geometry.rim_back_extension_mm,
            "rim_front_extension_mm": geometry.rim_front_extension_mm,
            "virtual_tooth_count": geometry.virtual_tooth_count,
            "virtual_pitch_radius_mm": geometry.virtual_pitch_radius_mm,
            "cut_scenario": "loft_cut_between_cone_normal_tredgold_sections",
            "outer_section_cone_distance_mm": geometry.section_outer_cone_distance_mm,
            "inner_section_cone_distance_mm": geometry.section_inner_cone_distance_mm,
            "outer_section_scale": outer_scale,
            "inner_section_scale": inner_scale,
            "section_margin_mm": geometry.section_margin_mm,
            "entity_count_per_section": len(outer_entities),
            "spline_deviation_mm": deviation,
            "expected_volume_mm3": expected_volume,
            "blank_volume_mm3": geometry.blank_volume_mm3,
            "removed_volume_mm3": geometry.removed_volume_mm3,
            "gap_area_clipped_mm2": geometry.gap_area_clipped_mm2,
        },
        "ownership": {
            "schema": BEVEL_OWNERSHIP_SCHEMA,
            "version": 1,
            "family_code": BEVEL_FAMILY_CODE,
            "standard_code": STANDARD_CODES.get(str(request.get("standard")), 0),
            "modification_code": MODIFICATION_CODES.get(str(request.get("modification")), 0),
            "source_profile": dict(request),
        },
        "verification": {
            "expected_volume_mm3": expected_volume,
            "volume_relative_tolerance": 0.015,
            "expected_bounds_mm": expected_bounds,
            "expected_bounds_candidates_mm": [expected_bounds, disk_bounds],
            "bounds_tolerance_mm": 0.1,
            "max_radius_mm": max_radius,
            "face_width_mm": geometry.face_width_mm,
            "pattern_count": pattern_count,
        },
        "accuracy": {
            "profile": "tredgold_virtual_gear_projection_to_the_apex",
            "profile_encoding": "root_and_involute_cubic_bezier_nurbs_per_flank_plus_cap_curve_per_section",
            "sweep": "cut_loft_between_cone_normal_tredgold_sections",
            "blank": "dish_plate_with_back_and_front_cone_normal_rim_faces",
            "flank_spline_deviation_mm": deviation,
            "parameterization": "numeric_create_only",
            "representation_mode": "nominal",
            "conformity_claim": False,
        },
    }
