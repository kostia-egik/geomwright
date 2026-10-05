"""Analytic involute and rack-generated root geometry for external spur gears.

Coordinates follow the transmission platform convention used by the timing
pulleys, chain sprockets, and the Studio adapter:

    x = r * sin(theta),  y = r * cos(theta)

so theta is measured from the +Y axis and a gear rotation in the YZ plane maps
directly onto a KOMPAS sketch on the YOZ plane. Linear values are millimetres,
angles are radians unless the field name says otherwise.

The flank is an exact involute. The root is the trochoid of the theoretical
sharp generating rack at the full dedendum depth, joined to the involute at the
numerically detected intersection. This is the same nominal envelope used by
the open py_gearworks oracle (`enable_undercut=True`), which ignores the cutter
tip radius as well. The selected basic-rack fillet radius is reported as
metadata; a rounded-tip `generated_exact` envelope is a later refinement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from .basic_racks import BasicRack, resolve_rack
from .modules import describe_module

_EPS = 1e-12


def _polar(radius: float, angle: float) -> list[float]:
    return [radius * math.sin(angle), radius * math.cos(angle)]


def _radius(point: list[float]) -> float:
    return math.hypot(float(point[0]), float(point[1]))


def _angle(point: list[float]) -> float:
    return math.atan2(float(point[0]), float(point[1]))


def involute(value_rad: float) -> float:
    return math.tan(value_rad) - value_rad


def _involute_polar(radius: float, base_radius: float) -> float:
    ratio = min(1.0, max(-1.0, base_radius / radius))
    return involute(math.acos(ratio))


def sample_involute_flank(
    *,
    base_radius: float,
    radius_start: float,
    radius_end: float,
    base_half_angle: float,
    inv_pressure_angle: float,
    count: int,
) -> list[list[float]]:
    """Positive gap-side involute from `radius_start` to `radius_end`.

    `base_half_angle` is the gap half-angle at the pitch circle (pi/z - eta);
    the flank angle is `base_half_angle - inv(alpha) + inv(alpha_rho)`.
    """
    if radius_end <= radius_start + 1e-9 or count <= 0:
        return []
    points: list[list[float]] = []
    for index in range(count + 1):
        radius = radius_start + (radius_end - radius_start) * index / count
        theta = base_half_angle - inv_pressure_angle + _involute_polar(radius, base_radius)
        points.append(_polar(radius, theta))
    return points


def _trochoid_point(pitch_radius: float, depth: float, lateral: float, t: float) -> list[float]:
    """Theoretical sharp-rack corner point at rolling parameter `t`.

    x = (xi + r t) cos t - (r - h) sin t
    y = (xi + r t) sin t + (r - h) cos t
    """
    u = lateral + pitch_radius * t
    return [
        u * math.cos(t) - (pitch_radius - depth) * math.sin(t),
        u * math.sin(t) + (pitch_radius - depth) * math.cos(t),
    ]


def _segment_intersection(
    a: list[float], b: list[float], c: list[float], d: list[float]
) -> list[float] | None:
    denominator = (a[0] - b[0]) * (c[1] - d[1]) - (a[1] - b[1]) * (c[0] - d[0])
    if abs(denominator) <= 1e-14:
        return None
    det_ab = a[0] * b[1] - a[1] * b[0]
    det_cd = c[0] * d[1] - c[1] * d[0]
    x = (det_ab * (c[0] - d[0]) - (a[0] - b[0]) * det_cd) / denominator
    y = (det_ab * (c[1] - d[1]) - (a[1] - b[1]) * det_cd) / denominator
    if not (min(a[0], b[0]) - 1e-9 <= x <= max(a[0], b[0]) + 1e-9):
        return None
    if not (min(a[1], b[1]) - 1e-9 <= y <= max(a[1], b[1]) + 1e-9):
        return None
    if not (min(c[0], d[0]) - 1e-9 <= x <= max(c[0], d[0]) + 1e-9):
        return None
    if not (min(c[1], d[1]) - 1e-9 <= y <= max(c[1], d[1]) + 1e-9):
        return None
    return [x, y]


def _polyline_intersections(first: list[list[float]], second: list[list[float]]) -> list[list[float]]:
    hits: list[list[float]] = []
    for index in range(len(first) - 1):
        for other in range(len(second) - 1):
            point = _segment_intersection(first[index], first[index + 1], second[other], second[other + 1])
            if point is not None:
                hits.append(point)
    return hits


def _signed_area(polygon: list[list[float]]) -> float:
    area = 0.0
    for index in range(len(polygon) - 1):
        x1, y1 = polygon[index]
        x2, y2 = polygon[index + 1]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _dedupe(points: list[list[float]], tolerance: float = 1e-9) -> list[list[float]]:
    result: list[list[float]] = []
    for point in points:
        if not result or math.dist(result[-1], point) > tolerance:
            result.append([float(point[0]), float(point[1])])
    return result


def _decimate(points: list[list[float]], target: int) -> list[list[float]]:
    if len(points) <= target:
        return points
    step = len(points) / target
    result = [points[int(index * step)] for index in range(target - 1)]
    result.append(points[-1])
    return _dedupe(result)


def _arc_points(radius: float, start_angle: float, end_angle: float, count: int) -> list[list[float]]:
    return [
        _polar(radius, start_angle + (end_angle - start_angle) * index / count)
        for index in range(count + 1)
    ]


@dataclass
class SpurGearGeometry:
    request: dict
    rack: BasicRack
    module_mm: float
    tooth_count: int
    pressure_angle_rad: float
    profile_shift: float
    face_width_mm: float
    pitch_radius: float
    base_radius: float
    outside_radius: float
    root_radius: float
    dedendum_mm: float
    tooth_thickness_mm: float
    space_width_mm: float
    tip_arc_thickness_mm: float
    form_radius_mm: float
    root_fillet_radius_mm: float
    gap_half_angle_rad: float
    tip_half_angle_rad: float
    root_arc_half_angle_rad: float
    minimum_shift: float = 0.0
    undercut: bool = False
    root_envelope: str = "sharp_rack_trochoid"
    module_info: dict = field(default_factory=dict)
    full_wheel_outline: list[list[float]] = field(default_factory=list)
    period_outline: list[list[float]] = field(default_factory=list)
    gap_outline: list[list[float]] = field(default_factory=list)
    gap_surface_path: list[list[float]] = field(default_factory=list)
    involute_path: list[list[float]] = field(default_factory=list)
    fillet_path: list[list[float]] = field(default_factory=list)
    root_arc_path: list[list[float]] = field(default_factory=list)
    section_area_mm2: float = 0.0
    warnings: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


def warning_item(code: str, message: str, **values) -> dict:
    return {"code": code, "severity": "warning", "message": message, **values}


def error_item(code: str, message: str, **values) -> dict:
    return {"code": code, "severity": "error", "message": message, **values}


def _involute_sample_count(outside_radius: float, base_radius: float) -> int:
    roll = math.sqrt(max(outside_radius ** 2 - base_radius ** 2, 0.0))
    step = max(0.05, 0.008 * max(outside_radius, 1.0))
    return max(24, min(120, int(math.ceil(roll / step))))


def build_spur_gear_geometry(
    request: dict,
    *,
    curve_samples: int = 260,
    wheel_points_per_tooth: int = 48,
    max_involute_samples: int | None = None,
) -> SpurGearGeometry:
    """Build the complete nominal geometry for one external spur gear."""
    rack = resolve_rack(
        str(request.get("contour") or "gost_a"),
        pressure_angle_deg=request.get("pressure_angle_deg"),
        addendum_coefficient=request.get("addendum_coefficient"),
        clearance_coefficient=request.get("clearance_coefficient"),
    )
    module = float(request["module_mm"])
    tooth_count = int(request["tooth_count"])
    pressure_angle = math.radians(float(rack.pressure_angle_deg))
    shift = float(request.get("profile_shift", 0.0))
    face_width = float(request.get("face_width_mm", 20.0))

    ha = rack.addendum_coefficient
    clearance = rack.clearance_coefficient

    pitch_radius = module * tooth_count / 2.0
    base_radius = pitch_radius * math.cos(pressure_angle)
    outside_radius = pitch_radius + module * (ha + shift)
    root_radius = pitch_radius - module * (ha + clearance - shift)
    inv_alpha = involute(pressure_angle)
    dedendum = module * (ha + clearance - shift)

    warnings: list[dict] = []
    errors: list[dict] = []

    module_info = describe_module(module)
    if not module_info["standard_value"]:
        warnings.append(
            warning_item(
                "gear_module_off_row",
                f"Module {module:g} mm is outside ГОСТ 9563-60 rows 1-2 and their recorded exceptions.",
                module_mm=module,
            )
        )
    if module < 1.0:
        warnings.append(
            warning_item(
                "gear_small_module_contour",
                "ГОСТ 9587-81 small-module contours are not implemented; ГОСТ 13755-2015 coefficients are used.",
                module_mm=module,
            )
        )
    if not rack.conformity_claim:
        warnings.append(
            warning_item(
                "gear_contour_modified",
                "Explicit coefficients make this a modified, non-standard contour.",
            )
        )
    if outside_radius <= base_radius + 1e-9:
        errors.append(
            error_item(
                "gear_tip_below_base",
                "The outside circle does not reach the base circle; no involute flank can be generated.",
                outside_diameter_mm=2.0 * outside_radius,
                base_diameter_mm=2.0 * base_radius,
            )
        )
    if root_radius <= 1e-9:
        errors.append(error_item("gear_root_not_positive", "The root diameter is not positive."))
    if outside_radius <= root_radius:
        errors.append(error_item("gear_invalid_radii", "The outside diameter must exceed the root diameter."))

    eta = math.pi / (2.0 * tooth_count) + 2.0 * shift * math.tan(pressure_angle) / tooth_count
    base_half_angle = math.pi / tooth_count - eta
    tooth_tip_half_angle = eta + inv_alpha - _involute_polar(outside_radius, base_radius)
    tooth_thickness = 2.0 * pitch_radius * eta
    space_width = math.pi * module - tooth_thickness
    tip_arc_thickness = 2.0 * outside_radius * tooth_tip_half_angle
    if tip_arc_thickness <= 0.0:
        errors.append(
            error_item(
                "gear_tip_thickness_negative",
                "The involute flanks cross before the outside circle: the tooth tip is not constructible.",
                tip_thickness_mm=tip_arc_thickness,
            )
        )
    elif tip_arc_thickness < 0.25 * module:
        warnings.append(
            warning_item(
                "gear_tip_thickness_low",
                "Tooth tip thickness is below 0.25 m; the flank may be pointed and sensitive to tolerances.",
                tip_thickness_mm=tip_arc_thickness,
            )
        )
    elif tip_arc_thickness < 0.3 * module:
        warnings.append(
            warning_item(
                "gear_tip_thickness_below_recommendation",
                "Tooth tip thickness is below the 0.30 m recommendation of ГОСТ 16532-70.",
                tip_thickness_mm=tip_arc_thickness,
            )
        )

    min_shift = ha - tooth_count * math.sin(pressure_angle) ** 2 / 2.0
    undercut = shift < min_shift - 1e-9
    if undercut:
        warnings.append(
            warning_item(
                "gear_undercut",
                "The rack cuts into the involute near the base circle; the form point is trimmed accordingly.",
                profile_shift=shift,
                minimum_shift=min_shift,
            )
        )

    geometry = SpurGearGeometry(
        request=dict(request),
        rack=rack,
        module_mm=module,
        tooth_count=tooth_count,
        pressure_angle_rad=pressure_angle,
        profile_shift=shift,
        face_width_mm=face_width,
        pitch_radius=pitch_radius,
        base_radius=base_radius,
        outside_radius=outside_radius,
        root_radius=root_radius,
        dedendum_mm=dedendum,
        tooth_thickness_mm=tooth_thickness,
        space_width_mm=space_width,
        tip_arc_thickness_mm=tip_arc_thickness,
        form_radius_mm=base_radius,
        root_fillet_radius_mm=rack.fillet_coefficient * module,
        gap_half_angle_rad=math.pi / (2.0 * tooth_count) - 2.0 * shift * math.tan(pressure_angle) / tooth_count,
        tip_half_angle_rad=tooth_tip_half_angle,
        root_arc_half_angle_rad=0.0,
        minimum_shift=min_shift,
        undercut=undercut,
        module_info=module_info,
        warnings=warnings,
        errors=errors,
    )
    if errors:
        return geometry

    # Theoretical sharp generating rack: the corner sits at the full rack
    # dedendum below the rack pitch line. The profile shift is carried by the
    # tooth thickness and by the reduced corner depth, matching the open
    # py_gearworks reference construction (rolling on the reference radius).
    rack_depth = (ha + clearance) * module
    corner_depth = (ha + clearance - shift) * module
    lateral = math.pi * module / 4.0 - rack_depth * math.tan(pressure_angle)
    t_root = -lateral / pitch_radius
    trochoid_curve = [
        _trochoid_point(pitch_radius, corner_depth, lateral, t_root + 1.2 * index / curve_samples)
        for index in range(curve_samples + 1)
    ]
    involute_count = _involute_sample_count(outside_radius, base_radius)
    if max_involute_samples is not None:
        involute_count = max(6, min(involute_count, int(max_involute_samples)))
    full_involute = sample_involute_flank(
        base_radius=base_radius,
        radius_start=base_radius,
        radius_end=outside_radius,
        base_half_angle=base_half_angle,
        inv_pressure_angle=inv_alpha,
        count=involute_count,
    )
    hits = _polyline_intersections(trochoid_curve, full_involute)
    trochoid_used = bool(hits)
    if hits:
        form_point = min(hits, key=_radius)
        form_radius = _radius(form_point)
        if form_radius >= outside_radius - 1e-9:
            errors.append(
                error_item(
                    "gear_fillet_reaches_tip",
                    "The generated root trochoid reaches the outside circle; the tooth space is not valid.",
                    form_radius_mm=form_radius,
                    outside_radius_mm=outside_radius,
                )
            )
            geometry.errors = errors
            return geometry
        trochoid_trim: list[list[float]] = []
        for point in trochoid_curve:
            trochoid_trim.append(point)
            if _radius(point) >= form_radius - 1e-9:
                break
        involute_trim = [point for point in full_involute if _radius(point) >= form_radius - 1e-9]
        if not involute_trim or math.dist(involute_trim[0], form_point) > 1e-6:
            involute_trim.insert(0, [float(form_point[0]), float(form_point[1])])
        boundary = _dedupe([*trochoid_trim, *involute_trim], tolerance=max(1e-9, module * 1e-6))
        root_angle = _angle(trochoid_curve[0])
    else:
        # The trochoid stays below the involute (no undercut trim). The visible
        # flank starts where the involute leaves the root circle.
        start_radius = max(base_radius, root_radius)
        involute_trim = [point for point in full_involute if _radius(point) >= start_radius - 1e-9]
        if not involute_trim:
            errors.append(
                error_item(
                    "gear_flank_missing",
                    "No usable involute flank exists between the root and outside circles.",
                )
            )
            geometry.errors = errors
            return geometry
        boundary = _dedupe(involute_trim, tolerance=max(1e-9, module * 1e-6))
        form_radius = _radius(boundary[0])
        root_angle = _angle(boundary[0])

    root_arc_steps = max(3, int(8 * max(root_angle, 1e-3) / 0.1))
    root_arc = _arc_points(root_radius, 0.0, root_angle, root_arc_steps)
    surface = _dedupe([*root_arc, *boundary])

    # Closed tooth-space cut contour with an overshoot cap outside the blank.
    overshoot = outside_radius + max(1.0, 0.02 * outside_radius)
    tip_point = surface[-1]
    tip_angle = _angle(tip_point)
    cap_arc = _arc_points(overshoot, tip_angle, -tip_angle, max(8, int(12 * max(tip_angle, 1e-3) / 0.1)))
    mirrored_surface = [[-point[0], point[1]] for point in reversed(surface)]
    gap = _dedupe([
        *surface,
        _polar(overshoot, tip_angle),
        *cap_arc[1:-1],
        _polar(outside_radius, -tip_angle),
        *mirrored_surface[1:],
        [float(surface[0][0]), float(surface[0][1])],
    ])
    if _signed_area(gap) < 0.0:
        gap = list(reversed(gap))

    # One pitch of the material boundary from gap center to gap center.
    tooth_center = math.pi / tooth_count
    tip_arc_end_angle = 2.0 * tooth_center - tip_angle
    tip_arc_count = max(4, int(16 * max(tip_arc_end_angle - tip_angle, 1e-3) / 0.1))
    tip_arc = _arc_points(outside_radius, tip_angle, tip_arc_end_angle, tip_arc_count)
    mirrored_tooth = [
        _polar(_radius(point), 2.0 * tooth_center - _angle(point))
        for point in reversed(surface)
    ]
    period = _dedupe([*surface, *tip_arc[1:-1], *mirrored_tooth[1:]])
    if math.dist(period[0], period[-1]) > 1e-9:
        period.append(period[0])
    period = _decimate(period, max(20, int(wheel_points_per_tooth)))

    wheel_points: list[list[float]] = []
    for index in range(tooth_count):
        angle_step = 2.0 * math.pi / tooth_count
        rotated = [
            _polar(_radius(point), _angle(point) + index * angle_step)
            for point in period
        ]
        if wheel_points:
            rotated = rotated[1:]
        wheel_points.extend(rotated)
    wheel_points = _dedupe(wheel_points)
    if math.dist(wheel_points[0], wheel_points[-1]) > 1e-9:
        wheel_points.append(wheel_points[0])

    geometry.form_radius_mm = min(form_radius, outside_radius)
    geometry.root_arc_half_angle_rad = root_angle
    geometry.root_envelope = "sharp_rack_trochoid" if trochoid_used else "involute_root_circle"
    geometry.gap_outline = gap
    geometry.gap_surface_path = _dedupe([*surface, *mirrored_surface])
    geometry.involute_path = involute_trim
    geometry.fillet_path = trochoid_curve if trochoid_used else []
    geometry.root_arc_path = root_arc
    geometry.period_outline = period
    geometry.full_wheel_outline = wheel_points
    geometry.section_area_mm2 = abs(_signed_area(wheel_points))
    return geometry
