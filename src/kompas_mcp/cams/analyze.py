from __future__ import annotations

import math

from .contacts import CamProfile


def minimum_curvature_radius(x: tuple[float, ...], y: tuple[float, ...]) -> float:
    if len(x) > 1 and math.dist((x[0], y[0]), (x[-1], y[-1])) < 1e-12:
        x, y = x[:-1], y[:-1]
    count = len(x)
    if count < 3:
        return math.inf
    best = math.inf
    for index in range(count):
        if index == 0:
            a = (x[-1], y[-1])
            b = (x[0], y[0])
            c = (x[1], y[1])
        elif index == count - 1:
            a = (x[-2], y[-2])
            b = (x[-1], y[-1])
            c = (x[0], y[0])
        else:
            a = (x[index - 1], y[index - 1])
            b = (x[index], y[index])
            c = (x[index + 1], y[index + 1])
        ab = math.dist(a, b)
        bc = math.dist(b, c)
        ac = math.dist(a, c)
        if ab < 1e-12 or bc < 1e-12 or ac < 1e-12:
            continue
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        area = 0.5 * abs(cross)
        if area < 1e-12:
            continue
        radius = (ab * bc * ac) / (4.0 * area)
        best = min(best, radius)
    return best


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def minimum_convex_curvature_radius(x: list[float] | tuple[float, ...],
                                    y: list[float] | tuple[float, ...]) -> float:
    """Minimum positive (CCW convex) pitch radius, excluding closure chords."""
    best = math.inf
    points = list(zip(x, y))
    for a, b, c in zip(points, points[1:], points[2:]):
        cross = _orientation(a, b, c)
        if cross > 1e-12:
            radius = math.dist(a, b) * math.dist(b, c) * math.dist(a, c) / (2.0 * cross)
            best = min(best, radius)
    return best


def _segments_intersect(
    p1: tuple[float, float],
    q1: tuple[float, float],
    p2: tuple[float, float],
    q2: tuple[float, float],
) -> bool:
    d1 = _orientation(p1, q1, p2)
    d2 = _orientation(p1, q1, q2)
    d3 = _orientation(p2, q2, p1)
    d4 = _orientation(p2, q2, q1)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True
    for distance, point, start, end in ((d1, p2, p1, q1), (d2, q2, p1, q1),
                                       (d3, p1, p2, q2), (d4, q1, p2, q2)):
        if abs(distance) <= 1e-12 and (
            min(start[0], end[0]) <= point[0] <= max(start[0], end[0])
            and min(start[1], end[1]) <= point[1] <= max(start[1], end[1])
        ):
            return True
    return False


def self_intersection(x: tuple[float, ...], y: tuple[float, ...]) -> bool:
    count = len(x)
    if count < 4:
        return False
    points = []
    for point in zip(x, y):
        if not points or math.dist(point, points[-1]) >= 1e-12:
            points.append(point)
    if math.dist(points[0], points[-1]) < 1e-12:
        points.pop()
    count = len(points)
    segments = []
    for i, p in enumerate(points):
        q = points[(i + 1) % count]
        if math.dist(p, q) >= 1e-12:
            segments.append((min(p[0], q[0]), max(p[0], q[0]),
                             min(p[1], q[1]), max(p[1], q[1]), i, p, q))
    # Broad-phase sweep: most sampled cam edges have disjoint bounding boxes.
    # Pathological geometry can still be quadratic; sampling is bounded upstream.
    active = []
    for segment in sorted(segments):
        low_x, high_x, low_y, high_y, i, p, q = segment
        active = [other for other in active if other[1] >= low_x]
        for other in active:
            _, _, other_low_y, other_high_y, j, p2, q2 = other
            if abs(i - j) in (1, count - 1):
                continue
            if high_y < other_low_y or other_high_y < low_y:
                continue
            if _segments_intersect(p, q, p2, q2):
                return True
        active.append(segment)
    return False


def pressure_angles_roller(
    normals: list[tuple[float, float]], theta_rad: tuple[float, ...] | None = None
) -> tuple[float, ...]:
    angles: list[float] = []
    for index, (normal_x, normal_y) in enumerate(normals):
        theta = theta_rad[index] if theta_rad is not None else 0.0
        # Both normal and translating axis must be in the same (cam) frame.
        projection = normal_x * math.cos(theta) + normal_y * math.sin(theta)
        value = max(-1.0, min(1.0, abs(projection)))
        angles.append(math.degrees(math.acos(value)))
    return tuple(angles)


def pressure_angles_from_directions(
    normal_x: tuple[float, ...],
    normal_y: tuple[float, ...],
    flow_x: tuple[float, ...],
    flow_y: tuple[float, ...],
) -> tuple[float, ...]:
    angles: list[float] = []
    for nx, ny, fx, fy in zip(normal_x, normal_y, flow_x, flow_y):
        flow_norm = math.hypot(fx, fy)
        if flow_norm < 1e-12:
            continue
        value = abs((nx * fx + ny * fy) / flow_norm)
        angles.append(math.degrees(math.acos(max(-1.0, min(1.0, value)))))
    return tuple(angles)


def summarize(profile: CamProfile, roller_normals: list[tuple[float, float]] | None = None,
              theta_rad: tuple[float, ...] | None = None) -> dict[str, float | bool | int]:
    min_radius = minimum_curvature_radius(profile.x, profile.y)
    summary: dict[str, float | bool | int] = {
        "point_count": len(profile.x),
        "active_count": profile.active_count,
        "min_curvature_radius": round(min_radius, 6) if math.isfinite(min_radius) else None,
        "self_intersection": self_intersection(profile.x, profile.y),
    }
    if roller_normals:
        angles = pressure_angles_roller(roller_normals, theta_rad)
        summary["max_pressure_angle_deg"] = round(max(angles), 4)
    return summary
