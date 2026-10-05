from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kompas_mcp.cams import event_from_crank, preview_cam_profile, valve_cycle

Lobe = Literal["intake", "exhaust"]
Step = Literal["phases", "kinematics", "cam"]

_INTAKE_TDC = 360.0
_INTAKE_BDC = 540.0
_EXHAUST_BDC = 180.0
_EXHAUST_TDC = 360.0
_STEPS = 96
_CONTACT_OFFSET_LIMIT_DEG = 15.0
_VALVE_AXIS_LIMIT_DEG = 10.0


class CamshaftGeometryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CamshaftPhasesRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    step: Step = "phases"
    active_lobe: Lobe = "intake"
    intake_open_deg: float = -10.0
    intake_close_deg: float = 50.0
    exhaust_open_deg: float = -45.0
    exhaust_close_deg: float = 15.0

    mechanism: Literal["direct", "rocker"] = "rocker"
    base_diameter: float = Field(default=60.0, gt=0.0)
    offset: float = 0.0
    contact: Literal["flat", "roller"] = "flat"
    roller_radius: float = Field(default=10.0, gt=0.0)
    cam_x: float = 0.0
    cam_y: float = 50.0
    roller_arm: float = Field(default=30.0, gt=0.0)
    valve_tip_x: float = Field(default=60.0, ge=0.0)
    valve_tip_y: float = 4.0
    valve_pad_radius: float = Field(default=0.0, ge=0.0)
    lash: float = Field(default=0.3, ge=0.0)

    law: Literal["polydyne_345", "polydyne_4567", "polydyne_56789", "cycloidal", "curvature_spline", "motion_spline", "bounded_auto"] = "bounded_auto"
    max_lift: float = Field(default=8.0, gt=0.0)
    tappet_diameter: float = Field(default=40.0, gt=0.0)
    tappet_edge_margin: float = Field(default=0.5, ge=0.0)
    min_curvature_radius: float = Field(default=1.0, gt=0.0)
    nose_radius: float | None = Field(default=None, gt=0.0)
    max_acceleration: float | None = Field(default=None, gt=0.0)
    max_jerk: float | None = Field(default=None, gt=0.0)
    ramp_open_deg: float = Field(default=20.0, ge=0.0)
    ramp_close_deg: float = Field(default=20.0, ge=0.0)
    cam_width: float = Field(default=12.0, gt=0.0, le=10000.0)
    cam_rotation_deg: float = 0.0
    cad_tolerance: float = Field(default=0.01, gt=0.0001, le=0.1)

    @model_validator(mode="after")
    def _derive_contact(self) -> "CamshaftPhasesRequest":
        self.contact = "roller" if self.mechanism == "rocker" else "flat"
        return self


def _arc(radius: float, start_deg: float, end_deg: float, steps: int) -> list[list[float]]:
    points: list[list[float]] = []
    for index in range(steps + 1):
        angle = math.radians(start_deg + (end_deg - start_deg) * index / steps)
        points.append([radius * math.sin(angle), radius * math.cos(angle)])
    return points


def _circle_points(radius: float, cx: float, cy: float, steps: int = _STEPS) -> list[list[float]]:
    points: list[list[float]] = []
    for index in range(steps + 1):
        angle = 2.0 * math.pi * index / steps
        points.append([cx + radius * math.sin(angle), cy + radius * math.cos(angle)])
    return points


def _band(inner: float, outer: float, start_deg: float, end_deg: float) -> list[list[float]]:
    outer_arc = _arc(outer, start_deg, end_deg, _STEPS)
    inner_arc = _arc(inner, start_deg, end_deg, _STEPS)
    return outer_arc + list(reversed(inner_arc)) + [outer_arc[0]]


def _tick(radius: float, angle_deg: float) -> list[list[float]]:
    return _arc(radius, float(angle_deg) - 2.0, float(angle_deg) + 2.0, 4)


def _polar(radius: float, angle_deg: float) -> dict[str, float]:
    angle = math.radians(angle_deg)
    return {"x": radius * math.sin(angle), "y": radius * math.cos(angle)}


def _rotate(point: list[float], angle_rad: float) -> list[float]:
    cosine, sine = math.cos(angle_rad), math.sin(angle_rad)
    return [point[0] * cosine - point[1] * sine, point[0] * sine + point[1] * cosine]


def _bounds(paths: list[list[list[float]]], label_points: list[list[float]] | None = None) -> dict[str, float]:
    xs = [point[0] for path in paths for point in path]
    ys = [point[1] for path in paths for point in path]
    for point in label_points or []:
        xs.append(point[0])
        ys.append(point[1])
    if not xs:
        return {"x_min": -1.0, "x_max": 1.0, "y_min": -1.0, "y_max": 1.0}
    pad = 8.0
    return {
        "x_min": min(xs) - pad,
        "x_max": max(xs) + pad,
        "y_min": min(ys) - pad,
        "y_max": max(ys) + pad,
    }


def _absolute_phases(request: CamshaftPhasesRequest) -> tuple[float, float, float, float]:
    return (
        _INTAKE_TDC + request.intake_open_deg,
        _INTAKE_BDC + request.intake_close_deg,
        _EXHAUST_BDC + request.exhaust_open_deg,
        _EXHAUST_TDC + request.exhaust_close_deg,
    )


def _phases_preview(request: CamshaftPhasesRequest) -> dict[str, Any]:
    intake_open, intake_close, exhaust_open, exhaust_close = _absolute_phases(request)
    if not (0.0 <= intake_open < intake_close <= 720.0 and
            0.0 <= exhaust_open < exhaust_close <= 720.0):
        raise CamshaftGeometryError("camshaft_phase_range", "each valve event must satisfy 0 <= opening < closing <= 720 crank degrees")
    cycle = valve_cycle(
        intake_open=intake_open,
        intake_close=intake_close,
        exhaust_open=exhaust_open,
        exhaust_close=exhaust_close,
    )
    overlap_deg = sum(high - low for low, high in cycle.overlap)
    summary = {
        "active_lobe": request.active_lobe,
        "intake_open_deg": intake_open,
        "intake_close_deg": intake_close,
        "intake_duration_deg": intake_close - intake_open,
        "intake_lca_deg": (intake_open + intake_close) / 2.0,
        "exhaust_open_deg": exhaust_open,
        "exhaust_close_deg": exhaust_close,
        "exhaust_duration_deg": exhaust_close - exhaust_open,
        "exhaust_lca_deg": (exhaust_open + exhaust_close) / 2.0,
        "overlap_deg": overlap_deg,
        "scale_deg": cycle.scale_deg,
    }
    return {
        "cycle": {
            "intake_open": intake_open,
            "intake_close": intake_close,
            "exhaust_open": exhaust_open,
            "exhaust_close": exhaust_close,
            "overlap": [list(item) for item in cycle.overlap],
            "tdc": list(cycle.tdc),
            "bdc": list(cycle.bdc),
            "scale_deg": cycle.scale_deg,
        },
        "summary": summary,
    }


def _opening_alpha(valve_arm: float, valve_angle_deg: float, lift: float) -> float:
    phi0 = math.radians(valve_angle_deg)
    sine = math.sin(phi0) - lift / valve_arm
    if abs(sine) > 1.0:
        raise CamshaftGeometryError("camshaft_reach", "valve lift exceeds the fixed rocker arm reach")
    return math.asin(sine) - phi0


def _circle_intersection(p1: list[float], r1: float, p2: list[float], r2: float) -> list[list[float]]:
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    distance = math.hypot(dx, dy)
    if distance <= 1e-9 or distance > r1 + r2 or distance < abs(r1 - r2):
        return []
    a = (r1 * r1 - r2 * r2 + distance * distance) / (2.0 * distance)
    h = math.sqrt(max(0.0, r1 * r1 - a * a))
    mx, my = p1[0] + a * dx / distance, p1[1] + a * dy / distance
    return [[mx - h * dy / distance, my + h * dx / distance], [mx + h * dy / distance, my - h * dx / distance]]


def _rocker_geometry(request: CamshaftPhasesRequest) -> dict[str, Any]:
    pivot = [0.0, 0.0]
    cam = [request.cam_x, request.cam_y]
    tip = [request.valve_tip_x, request.valve_tip_y]
    base_radius = request.base_diameter / 2.0
    lash = request.lash
    reach = base_radius + request.roller_radius + lash
    points = _circle_intersection(pivot, request.roller_arm, cam, reach)
    if not points:
        raise CamshaftGeometryError("camshaft_unreachable", "roller cannot reach the cam base circle for this geometry")
    valve_arm = math.hypot(tip[0], tip[1])
    if valve_arm <= 1e-9:
        raise CamshaftGeometryError("camshaft_degenerate", "valve tip must not coincide with the rocker pivot")
    travel = request.max_lift
    valve_angle = math.degrees(math.atan2(tip[1], tip[0]))
    alpha_open = _opening_alpha(valve_arm, valve_angle, travel)

    def distance_rate(roller: list[float]) -> float:
        return (roller[0] - cam[0]) * (-roller[1]) + (roller[1] - cam[1]) * roller[0]

    roller = points[0]
    for candidate in points:
        if distance_rate(candidate) * alpha_open > 0.0:
            roller = candidate
            break

    def direction(point: list[float]) -> float:
        return math.atan2(point[1] - cam[1], point[0] - cam[0])

    rest_dir = direction(roller)
    nose = direction(_rotate(roller, _opening_alpha(valve_arm, valve_angle, travel / 2.0)))
    max_dir = direction(_rotate(roller, alpha_open))

    def deviation(angle: float) -> float:
        return math.degrees(abs((angle - nose + math.pi) % (2.0 * math.pi) - math.pi))

    worst_pressure = 0.0
    for index in range(21):
        angle = alpha_open * index / 20.0
        center = _rotate(roller, angle)
        normal = [center[0] - cam[0], center[1] - cam[1]]
        velocity = [-center[1], center[0]]
        normal_length = math.hypot(normal[0], normal[1])
        velocity_length = math.hypot(velocity[0], velocity[1])
        if normal_length <= 1e-9 or velocity_length <= 1e-9:
            continue
        cosine = abs(
            (normal[0] * velocity[0] + normal[1] * velocity[1]) / (normal_length * velocity_length)
        )
        worst_pressure = max(worst_pressure, math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))

    roller_max = _rotate(roller, alpha_open)
    radial_rest = math.hypot(roller[0] - cam[0], roller[1] - cam[1])
    radial_max = math.hypot(roller_max[0] - cam[0], roller_max[1] - cam[1])
    lobe_height = lash + max(radial_max - radial_rest, 0.0)

    mid_tip = [tip[0], tip[1] - travel / 2.0]
    arm_mid = (math.degrees(math.atan2(mid_tip[1], mid_tip[0])) + 90.0) % 180.0 - 90.0

    return {
        "pivot": pivot,
        "cam": cam,
        "base_radius": base_radius,
        "roller": roller,
        "roller_angle_deg": math.degrees(math.atan2(roller[1], roller[0])),
        "valve_arm": valve_arm,
        "valve_angle_deg": valve_angle,
        "travel": travel,
        "lash": lash,
        "lobe_height": lobe_height,
        "alpha_open_deg": math.degrees(alpha_open),
        "cam_pressure_angle_deg": worst_pressure,
        "valve_axis_deviation_deg": abs(arm_mid),
        "contact_span_deg": math.degrees(abs((max_dir - rest_dir + math.pi) % (2.0 * math.pi) - math.pi)),
        "contact_offset_deg": max(deviation(rest_dir), deviation(max_dir)),
    }


def _placeholder_cam(base_radius: float, nose_angle_deg: float, height: float, width: float = 26.0) -> list[list[float]]:
    points: list[list[float]] = []
    for index in range(181):
        angle = 360.0 * index / 180.0
        delta = (angle - nose_angle_deg + 180.0) % 360.0 - 180.0
        radius = base_radius + height * math.exp(-((delta / width) ** 2))
        points.append([radius * math.sin(math.radians(angle)), radius * math.cos(math.radians(angle))])
    return points


def _direction_angle(point_from: list[float], point_to: list[float]) -> float:
    return math.degrees(math.atan2(point_to[0] - point_from[0], point_to[1] - point_from[1]))


def _convex_hull(points: list[list[float]]) -> list[list[float]]:
    unique = sorted({(round(point[0], 6), round(point[1], 6)) for point in points})
    if len(unique) <= 2:
        return [list(point) for point in unique]

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    hull = [list(point) for point in lower[:-1] + upper[:-1]]
    if hull:
        hull.append(hull[0])
    return hull


def _pad_arc_points(
    center: list[float],
    radius: float,
    start: list[float],
    end: list[float],
    steps: int = 24,
) -> list[list[float]]:
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    delta = a1 - a0
    while delta > math.pi:
        delta -= 2.0 * math.pi
    while delta < -math.pi:
        delta += 2.0 * math.pi
    reach = -0.5 * math.pi - a0
    while reach > math.pi:
        reach -= 2.0 * math.pi
    while reach < -math.pi:
        reach += 2.0 * math.pi
    covered = 0.0 <= reach <= delta if delta >= 0.0 else delta <= reach <= 0.0
    if not covered:
        delta = delta - 2.0 * math.pi if delta > 0.0 else delta + 2.0 * math.pi
    return [
        [
            center[0] + radius * math.cos(a0 + delta * index / steps),
            center[1] + radius * math.sin(a0 + delta * index / steps),
        ]
        for index in range(steps + 1)
    ]


def _round_corner(
    previous: list[float],
    corner: list[float],
    following: list[float],
    radius: float,
    steps: int = 8,
) -> list[list[float]]:
    first = [previous[0] - corner[0], previous[1] - corner[1]]
    second = [following[0] - corner[0], following[1] - corner[1]]
    first_length = math.hypot(first[0], first[1])
    second_length = math.hypot(second[0], second[1])
    if first_length <= 1e-9 or second_length <= 1e-9:
        return []
    first = [first[0] / first_length, first[1] / first_length]
    second = [second[0] / second_length, second[1] / second_length]
    cosine = max(-1.0, min(1.0, first[0] * second[0] + first[1] * second[1]))
    angle = math.acos(cosine)
    if angle <= 1e-6 or angle >= math.pi - 1e-6:
        return []
    radius = min(radius, min(first_length, second_length) * math.tan(angle * 0.5) * 0.9)
    if radius <= 1e-9:
        return []
    offset = radius / math.tan(angle * 0.5)
    start = [corner[0] + first[0] * offset, corner[1] + first[1] * offset]
    end = [corner[0] + second[0] * offset, corner[1] + second[1] * offset]
    bisector = [first[0] + second[0], first[1] + second[1]]
    length = math.hypot(bisector[0], bisector[1])
    if length <= 1e-9:
        return []
    bisector = [bisector[0] / length, bisector[1] / length]
    center = [
        corner[0] + bisector[0] * radius / math.sin(angle * 0.5),
        corner[1] + bisector[1] * radius / math.sin(angle * 0.5),
    ]
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
    delta = end_angle - start_angle
    while delta > math.pi:
        delta -= 2.0 * math.pi
    while delta < -math.pi:
        delta += 2.0 * math.pi
    arc = [
        [
            center[0] + radius * math.cos(start_angle + delta * index / steps),
            center[1] + radius * math.sin(start_angle + delta * index / steps),
        ]
        for index in range(1, steps)
    ]
    return [start, *arc, end]


def _splice_pad(
    outline: list[list[float]],
    tip: list[float],
    pad_radius: float,
    half_width: float,
    fillet: float,
) -> list[list[float]]:
    body = outline[:-1] if len(outline) > 1 and outline[0] == outline[-1] else list(outline)
    if not body or half_width <= 0.0 or pad_radius <= 0.0:
        return outline
    half_width = min(half_width, 0.9 * pad_radius)
    total = len(body)
    center = [tip[0], tip[1] + pad_radius]
    drop = math.sqrt(max(0.0, pad_radius * pad_radius - half_width * half_width))
    level = tip[1] + pad_radius - drop
    left = [tip[0] - half_width, level]
    right = [tip[0] + half_width, level]

    def crossing(x: float) -> tuple[int, list[float]] | None:
        best: tuple[int, list[float]] | None = None
        for index in range(total):
            a = body[index]
            b = body[(index + 1) % total]
            if (a[0] - x) * (b[0] - x) < 0.0:
                ratio = (x - a[0]) / (b[0] - a[0])
                point = [x, a[1] + ratio * (b[1] - a[1])]
                if best is None or point[1] < best[1][1]:
                    best = (index, point)
        return best

    left_side = crossing(tip[0] - half_width)
    right_side = crossing(tip[0] + half_width)
    while (left_side is None or right_side is None) and half_width > 1e-3:
        half_width *= 0.85
        drop = math.sqrt(max(0.0, pad_radius * pad_radius - half_width * half_width))
        level = tip[1] + pad_radius - drop
        left = [tip[0] - half_width, level]
        right = [tip[0] + half_width, level]
        left_side = crossing(left[0])
        right_side = crossing(right[0])
    if left_side is None or right_side is None:
        return outline
    left_edge, left_top = left_side
    right_edge, right_top = right_side
    span = (right_edge - left_edge) % total
    if span == 0:
        return outline
    removed = {(left_edge + offset) % total for offset in range(1, span + 1)}
    arc = _pad_arc_points(center, pad_radius, left, right)
    result: list[list[float]] = []
    for index in range(total):
        if index in removed:
            continue
        result.append(body[index])
        if index == left_edge:
            result.extend([left_top, *arc])
        if index == right_edge:
            result.append(right_top)
    targets = [left_top, left, right, right_top]
    corners: list[int] = []
    for target in targets:
        for index, point in enumerate(result):
            if abs(point[0] - target[0]) < 1e-9 and abs(point[1] - target[1]) < 1e-9:
                corners.append(index)
                break
    for index in sorted(set(corners), reverse=True):
        if index <= 0 or index >= len(result) - 1:
            continue
        rounded = _round_corner(result[index - 1], result[index], result[index + 1], fillet)
        if rounded:
            result = result[: index - 1] + rounded + result[index + 2 :]
    compact: list[list[float]] = []
    for point in result:
        if not compact or abs(point[0] - compact[-1][0]) > 1e-9 or abs(point[1] - compact[-1][1]) > 1e-9:
            compact.append(point)
    if len(compact) < 3:
        return outline
    compact.append(compact[0])
    return compact


def _valve_outline(tip: list[float], scale: float) -> list[list[float]]:
    tx, ty = tip
    head_radius = 0.85 * scale
    stem_half = 0.12 * head_radius
    stem_len = 2.4 * head_radius
    shoulder_radius = head_radius - stem_half
    head_thick = 0.25 * head_radius
    shoulder_y = ty - stem_len
    bottom_y = shoulder_y - shoulder_radius - head_thick
    right: list[list[float]] = [[tx + stem_half, ty], [tx + stem_half, shoulder_y]]
    steps = 12
    for index in range(1, steps + 1):
        angle = math.pi + (math.pi / 2.0) * index / steps
        right.append([
            tx + head_radius + shoulder_radius * math.cos(angle),
            shoulder_y + shoulder_radius * math.sin(angle),
        ])
    right.append([tx + head_radius, bottom_y])
    left_side = [[2.0 * tx - point[0], point[1]] for point in right]
    outline = right + list(reversed(left_side))
    outline.append(outline[0])
    return outline


def _kinematics_preview(request: CamshaftPhasesRequest) -> dict[str, Any]:
    labels: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if request.mechanism == "direct":
        travel = request.max_lift
        lash = request.lash
        r0 = request.base_diameter / 2.0
        cam = [request.offset, request.cam_y]
        base_bottom = cam[1] - r0 - lash
        half = 0.5 * request.tappet_diameter
        tappet_rest = [[-half, 0.0], [half, 0.0], [half, base_bottom], [-half, base_bottom], [-half, 0.0]]
        tappet_max = [
            [-half, -travel], [half, -travel], [half, base_bottom - travel], [-half, base_bottom - travel], [-half, -travel]
        ]
        rest_items = [{"points": tappet_rest, "fill": True}]
        max_items = [{"points": tappet_max, "fill": True}]
        tip_rest = [0.0, 0.0]
        tip_max = [0.0, -travel]
        rest_items.append({"points": _valve_outline(tip_rest, r0)})
        max_items.append({"points": _valve_outline(tip_max, r0)})
        axis_items = []
        roller = None
        valve_tip = tip_rest
        nose_angle = 180.0
        lobe_height = lash + travel
        labels.append({"x": 0.0, "y": base_bottom * 0.5, "text_key": "camshaft.part.follower", "fallback": "Tappet", "tone": "ref", "leader": True, "side": "left"})
        scheme = "direct"
        base_radius = r0
        contact_offset = 0.0
        contact_span = 0.0
        pressure = 0.0
        valve_dev = 0.0
        metrics = {
            "base_radius_mm": round(r0, 3),
            "lift_mm": round(travel, 3),
            "cam_lift_mm": round(max(lobe_height - lash, 0.0), 3),
            "cam_height_mm": round(lobe_height, 3),
            "lash_mm": round(lash, 3),
        }
        if abs(request.offset) > 1e-9:
            metrics["cam_offset_mm"] = round(request.offset, 3)
    else:
        geo = _rocker_geometry(request)
        cam = geo["cam"]
        base_radius = geo["base_radius"]
        roller = geo["roller"]
        travel = geo["travel"]
        valve_arm = geo["valve_arm"]
        valve_angle = geo["valve_angle_deg"]
        lobe_height = geo["lobe_height"]
        alpha_max = _opening_alpha(valve_arm, valve_angle, travel)
        roller_max = _rotate(roller, alpha_max)
        tip_rest = [request.valve_tip_x, request.valve_tip_y]
        tip_max = [tip_rest[0], tip_rest[1] - travel]
        axis_radius = max(0.4 * request.roller_radius, 0.8)
        pad_height = 0.6 * axis_radius
        requested_pad = request.valve_pad_radius if request.valve_pad_radius > 0.0 else 1.2 * axis_radius
        pad_curvature = max(requested_pad, pad_height)

        def node(center: list[float], radius: float) -> list[list[float]]:
            return _circle_points(radius, center[0], center[1], 48)

        def unit(vector: list[float]) -> list[float]:
            length = math.hypot(vector[0], vector[1]) or 1.0
            return [vector[0] / length, vector[1] / length]

        def rocker_body(tip: list[float], roller_center: list[float]) -> list[list[float]]:
            direction = unit(tip)
            normal = [-direction[1], direction[0]]
            if normal[1] < 0.0:
                normal = [direction[1], -direction[0]]
            vertex = [
                tip[0] + axis_radius * normal[0],
                tip[1] + pad_height + axis_radius * normal[1],
            ]
            outline = _convex_hull(
                node([0.0, 0.0], axis_radius) + node(roller_center, axis_radius) + node(vertex, axis_radius)
            )
            return _splice_pad(outline, tip, pad_curvature, axis_radius, 0.3 * pad_height)

        roller_rest = _circle_points(request.roller_radius, roller[0], roller[1], 48)
        roller_max_circle = _circle_points(request.roller_radius, roller_max[0], roller_max[1], 48)
        dot = 0.5 * axis_radius
        rest_items = [
            {"points": roller_rest},
            {"points": rocker_body(tip_rest, roller), "fill": True},
            {"points": _valve_outline(tip_rest, base_radius)},
        ]
        max_items = [
            {"points": roller_max_circle},
            {"points": rocker_body(tip_max, roller_max), "fill": True},
            {"points": _valve_outline(tip_max, base_radius)},
        ]
        axis_items = [
            {"tone": "ref", "points": _circle_points(dot, 0.0, 0.0, 24)},
            {"tone": "rest", "points": _circle_points(dot, roller[0], roller[1], 24)},
            {"tone": "max", "points": _circle_points(dot, roller_max[0], roller_max[1], 24)},
        ]
        valve_tip = tip_rest
        nose_angle = _direction_angle(cam, _rotate(roller, _opening_alpha(valve_arm, valve_angle, travel / 2.0)))
        scheme = "cam_above" if request.cam_y >= 0.0 else "cam_below"
        contact_offset = geo["contact_offset_deg"]
        contact_span = geo["contact_span_deg"]
        pressure = geo["cam_pressure_angle_deg"]
        valve_dev = geo["valve_axis_deviation_deg"]
        if pressure > _CONTACT_OFFSET_LIMIT_DEG:
            warnings.append(
                {
                    "code": "camshaft_pressure_angle",
                    "params": {"value": round(pressure, 1), "limit": round(_CONTACT_OFFSET_LIMIT_DEG)},
                    "message": (
                        f"cam-roller pressure angle {pressure:.1f} deg exceeds "
                        f"{_CONTACT_OFFSET_LIMIT_DEG:.0f} deg (side load)"
                    ),
                }
            )
        if valve_dev > _VALVE_AXIS_LIMIT_DEG:
            warnings.append(
                {
                    "code": "camshaft_valve_axis",
                    "params": {"value": round(valve_dev, 1), "limit": round(_VALVE_AXIS_LIMIT_DEG)},
                    "message": (
                        f"valve-side arm is {valve_dev:.1f} deg off perpendicular to the "
                        "valve axis at mid-lift (side load on the stem)"
                    ),
                }
            )
        labels.append({"x": 0.0, "y": 0.0, "text_key": "camshaft.part.pivot", "fallback": "Pivot", "tone": "ref", "leader": True, "side": "left"})
        labels.append({"x": roller[0], "y": roller[1], "text_key": "camshaft.part.roller", "fallback": "Roller", "tone": "ref", "leader": True, "side": "left"})
        labels.append({"x": roller[0] / 2.0, "y": roller[1] / 2.0, "text_key": "camshaft.part.rocker", "fallback": "Rocker", "tone": "ref", "leader": True, "side": "left"})
        metrics = {
            "base_radius_mm": round(base_radius, 3),
            "lift_mm": round(travel, 3),
            "cam_lift_mm": round(max(lobe_height - request.lash, 0.0), 3),
            "cam_height_mm": round(lobe_height, 3),
            "lash_mm": round(request.lash, 3),
            "rocker_ratio": round(valve_arm / request.roller_arm, 3),
            "rocker_rotation_deg": round(abs(geo["alpha_open_deg"]), 3),
            "roller_arm_mm": round(request.roller_arm, 3),
            "valve_arm_mm": round(valve_arm, 3),
            "arm_angle_deg": round(valve_angle, 3),
        }

    cam_outline = _placeholder_cam(base_radius, nose_angle, lobe_height)
    cam_outline = [[point[0] + cam[0], point[1] + cam[1]] for point in cam_outline]
    labels.append({"x": cam[0], "y": cam[1], "text_key": "camshaft.part.cam", "fallback": "Cam", "tone": "ref", "leader": True, "side": "left"})
    labels.append({"x": tip_rest[0], "y": tip_rest[1] - 1.5 * base_radius, "text_key": "camshaft.part.valve", "fallback": "Valve", "tone": "ref", "leader": True, "side": "right"})

    return {
        "cam": cam,
        "base_radius": base_radius,
        "travel": request.max_lift,
        "lobe_height": lobe_height,
        "scheme": scheme,
        "roller": roller,
        "valve_tip": valve_tip,
        "cam_outline": cam_outline,
        "rest_items": rest_items,
        "max_items": max_items,
        "axis_items": axis_items,
        "labels": labels,
        "warnings": warnings,
        "contact_offset_deg": contact_offset,
        "contact_span_deg": contact_span,
        "cam_pressure_angle_deg": pressure,
        "valve_axis_deviation_deg": valve_dev,
        "metrics": metrics,
    }


def cam_profile_request(request: CamshaftPhasesRequest) -> dict[str, Any]:
    _phases_preview(request)
    intake_open, intake_close, exhaust_open, exhaust_close = _absolute_phases(request)
    lobe_open = intake_open if request.active_lobe == "intake" else exhaust_open
    lobe_close = intake_close if request.active_lobe == "intake" else exhaust_close
    event = event_from_crank(open_deg=lobe_open, close_deg=lobe_close)
    payload: dict[str, Any] = {
        "law": request.law,
        "max_lift": request.max_lift,
        "open_angle": event.open_angle,
        "dwell_angle": event.dwell_angle,
        "close_angle": event.close_angle,
        "phase_deg": event.phase_deg,
        "contact": request.contact,
        "roller_radius": request.roller_radius,
        # Studio offsets the cam axis; Layer 2 offsets the face centre relative
        # to the cam, so the transverse coordinate has the opposite sign.
        "offset": -request.offset if request.mechanism == "direct" else 0.0,
        "lash": request.lash,
        "ramp_open_deg": request.ramp_open_deg,
        "ramp_close_deg": request.ramp_close_deg,
        "samples_per_degree": 10.0,
        "mechanism": request.mechanism,
        "tappet_diameter": request.tappet_diameter,
        "tappet_edge_margin": request.tappet_edge_margin,
        "min_curvature_radius": request.min_curvature_radius,
        "nose_radius": request.nose_radius,
        "max_acceleration": request.max_acceleration,
        "max_jerk": request.max_jerk,
    }
    if request.mechanism == "rocker":
        geo = _rocker_geometry(request)
        cam_center = geo["cam"]
        pivot = geo["pivot"]
        tip = [request.valve_tip_x, request.valve_tip_y]
        reach = geo["base_radius"] + request.roller_radius
        candidates = _circle_intersection(pivot, request.roller_arm, cam_center, reach)
        if not candidates:
            raise CamshaftGeometryError("camshaft_unreachable", "roller cannot reach the cam base circle for this geometry")
        rest = min(candidates, key=lambda point: math.dist(point, geo["roller"]))
        rotation = math.degrees(math.atan2(rest[1] - cam_center[1], rest[0] - cam_center[0]))
        roller_angle = math.degrees(math.atan2(rest[1] - pivot[1], rest[0] - pivot[0])) - rotation
        valve_angle = math.degrees(math.atan2(tip[1] - pivot[1], tip[0] - pivot[0])) - rotation
        payload.update(
            {
                "base_radius": geo["base_radius"],
                "roller_arm": request.roller_arm,
                "roller_angle_deg": roller_angle,
                "valve_arm": geo["valve_arm"],
                "valve_angle_deg": valve_angle,
                "valve_axis_deg": -90.0 - rotation,
            }
        )
    else:
        payload["base_radius"] = request.base_diameter / 2.0
    return payload


def _cam_preview(request: CamshaftPhasesRequest) -> dict[str, Any]:
    result = preview_cam_profile(cam_profile_request(request))
    if request.mechanism == "rocker" and request.valve_pad_radius > 0.0:
        result["warning_items"].append({"code": "camshaft_pad_illustrative", "params": {},
            "message": "Valve-pad radius affects the layout only; the calculated profile assumes a flat valve end."})
    return result


def build_camshaft_phases_preview(payload: dict[str, Any]) -> dict[str, Any]:
    request = CamshaftPhasesRequest.model_validate(payload)
    result: dict[str, Any] = {"step": request.step}
    result.update(_phases_preview(request))
    if request.step == "kinematics":
        result["kinematics"] = _kinematics_preview(request)
    elif request.step == "cam":
        result["cam"] = _cam_preview(request)
    return result


def adapt_camshaft_phases(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    step = str(preview.get("step") or "phases")
    if step == "kinematics":
        return _adapt_kinematics(preview)
    if step == "cam":
        return _adapt_cam(preview, request)
    return _adapt_phases(preview)


def _adapt_kinematics(preview: dict[str, Any]) -> dict[str, Any]:
    kinematics = dict(preview.get("kinematics") or {})
    base_radius = float(kinematics.get("base_radius", 30.0))
    cam = list(kinematics.get("cam_outline") or [])
    circle_center = list(kinematics.get("cam") or [0.0, 0.0])
    circle = _circle_points(base_radius, float(circle_center[0]), float(circle_center[1]), _STEPS)
    rest_items = list(kinematics.get("rest_items") or [])
    max_items = list(kinematics.get("max_items") or [])
    axis_items = list(kinematics.get("axis_items") or [])
    rest_paths = [item["points"] for item in rest_items]
    max_paths = [item["points"] for item in max_items]
    labels = list(kinematics.get("labels") or [])
    axis_paths = [
        {"tone": item.get("tone", "ref"), "width": 1.0, "points": item["points"], "fill": True}
        for item in axis_items
    ]
    tone_paths = [{"tone": "cam", "width": 2.0, "points": cam}] if cam else []
    tone_paths += [
        {"tone": "rest", "width": 1.8, "points": item["points"], "fill": bool(item.get("fill"))}
        for item in rest_items
    ]
    tone_paths += [item for item in axis_paths if item["tone"] == "rest"]
    tone_paths += [
        {"tone": "max", "width": 2.8, "points": item["points"], "fill": bool(item.get("fill"))}
        for item in max_items
    ]
    tone_paths += [item for item in axis_paths if item["tone"] == "max"]
    tone_paths += [item for item in axis_paths if item["tone"] not in ("rest", "max")]
    caption = {
        "x": float(circle_center[0]),
        "y": 0.0,
        "text_key": f"camshaft.scheme.{kinematics.get('scheme', 'direct')}",
        "fallback": str(kinematics.get("scheme")),
        "tone": "ref",
        "placement": "caption",
    }
    labels.append(caption)
    summary = dict(kinematics.get("metrics") or {})
    if kinematics.get("scheme") != "direct":
        summary.update(
            {
                "cam_pressure_angle_deg": round(float(kinematics.get("cam_pressure_angle_deg", 0.0)), 3),
                "valve_axis_deviation_deg": round(float(kinematics.get("valve_axis_deviation_deg", 0.0)), 3),
                "contact_offset_deg": round(float(kinematics.get("contact_offset_deg", 0.0)), 3),
                "contact_span_deg": round(float(kinematics.get("contact_span_deg", 0.0)), 3),
            }
        )
    return {
        "ok": True,
        "family": "camshaft_kinematics",
        "closed_points": max_paths,
        "feature_paths": max_paths,
        "tone_paths": tone_paths,
        "labels": labels,
        "guide_paths": [circle],
        "reference_paths": [],
        "phantom_bodies": [],
        "bounds": _bounds([cam, circle, *rest_paths, *max_paths]),
        "summary": summary,
        "warning_items": list(kinematics.get("warnings") or []) + [{"code": "camshaft_schematic", "params": {},
                           "message": "Kinematic layout only: the cam outline is illustrative, not the calculated profile."}],
        "warnings": [],
    }


def _adapt_cam(preview: dict[str, Any], request: dict[str, Any] | None = None) -> dict[str, Any]:
    cam = dict(preview.get("cam") or {})
    profile = dict(cam.get("profile") or {})
    x = list(profile.get("x") or [])
    y = list(profile.get("y") or [])
    points = [[float(px), float(py)] for px, py in zip(x, y)]
    rotation = math.radians(float((request or {}).get("cam_rotation_deg", 0.0)))
    if rotation:
        points = [_rotate(point, rotation) for point in points]
    if points and points[0] != points[-1]:
        points.append(points[0])
    base_radius = float((cam.get("spec") or {}).get("base_radius") or 1.0)
    circle = _arc(base_radius, 0.0, 360.0, _STEPS)
    summary = dict(cam.get("summary") or {})
    summary.pop("continuity", None)
    summary.pop("derivative_coordinate", None)
    notes = {"cam_clearance", "cam_curvature_family"}
    warning_items = [w for w in cam.get("warning_items", []) if w["code"] not in notes]
    motion_chart = cam.get("motion_chart")
    if motion_chart:
        motion_chart = {**motion_chart, "has_warnings": bool(warning_items)}
    return {
        "ok": True,
        "family": "camshaft_cam",
        "closed_points": [points] if points else [],
        "feature_paths": [points] if points else [],
        "tone_paths": [{"tone": "max", "width": 2.4, "points": points}] if points else [],
        "guide_paths": [circle],
        "reference_paths": [],
        "phantom_bodies": [],
        "bounds": _bounds([points, circle]) if points else _bounds([circle]),
        "summary": summary,
        "warnings": [w["message"] for w in warning_items],
        "warning_items": warning_items,
        "motion_chart": motion_chart,
    }


def _adapt_phases(preview: dict[str, Any]) -> dict[str, Any]:
    cycle = dict(preview.get("cycle") or {})
    summary = dict(preview.get("summary") or {})
    intake_open = float(cycle.get("intake_open", 0.0))
    intake_close = float(cycle.get("intake_close", 0.0))
    exhaust_open = float(cycle.get("exhaust_open", 0.0))
    exhaust_close = float(cycle.get("exhaust_close", 0.0))

    intake_band = _band(80.0, 100.0, intake_open, intake_close)
    exhaust_band = _band(48.0, 68.0, exhaust_open, exhaust_close)
    circle = _arc(74.0, 0.0, 720.0, _STEPS)
    frame = _arc(122.0, 0.0, 720.0, 12)
    intake_mid = (intake_open + intake_close) / 2.0
    exhaust_mid = (exhaust_open + exhaust_close) / 2.0
    active = str(summary.get("active_lobe") or "intake")
    intake_active = active == "intake"
    summary.pop("active_lobe", None)

    tone_paths = [
        {"tone": "intake", "active": intake_active, "points": intake_band},
        {"tone": "exhaust", "active": not intake_active, "points": exhaust_band},
    ]
    active_path = {
        "tone": "intake" if intake_active else "exhaust",
        "points": intake_band if intake_active else exhaust_band,
    }
    labels = [
        {"key": "tdc", "text_key": "camshaft.label.tdc", "fallback": "TDC", "tone": "ref", **_polar(112.0, 0.0)},
        {"key": "bdc", "text_key": "camshaft.label.bdc", "fallback": "BDC", "tone": "ref", **_polar(112.0, 180.0)},
        {"key": "intake", "text_key": "camshaft.label.intake", "fallback": "Intake", "tone": "intake", "size": 0.8, **_polar(90.0, intake_mid)},
        {"key": "exhaust", "text_key": "camshaft.label.exhaust", "fallback": "Exhaust", "tone": "exhaust", "size": 0.8, **_polar(58.0, exhaust_mid)},
    ]
    arrows = [
        {"tone": "intake", "points": _arc(90.0, intake_mid - 34.0, intake_mid - 8.0, 24)},
        {"tone": "exhaust", "points": _arc(58.0, exhaust_mid - 34.0, exhaust_mid - 8.0, 24)},
    ]
    reference_paths: list[dict[str, Any]] = []
    for key, angles in (("tdc", cycle.get("tdc") or []), ("bdc", cycle.get("bdc") or [])):
        points: list[list[float]] = []
        for angle in angles:
            points.extend(_tick(74.0, float(angle)))
        reference_paths.append({"key": key, "points": points})

    return {
        "ok": True,
        "family": "camshaft_phases",
        "active_lobe": active,
        "closed_points": [intake_band, exhaust_band],
        "feature_paths": [intake_band, exhaust_band],
        "tone_paths": tone_paths,
        "active_path": active_path,
        "labels": labels,
        "arrows": arrows,
        "guide_paths": [circle],
        "reference_paths": reference_paths,
        "phantom_bodies": [],
        "bounds": _bounds([intake_band, exhaust_band, circle, frame]),
        "summary": summary,
        "warnings": [],
    }
