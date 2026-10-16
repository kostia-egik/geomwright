"""Presentation adapter: торцевой разрез вала/втулки прямобочных шлицов."""
from __future__ import annotations

import math
from typing import Any

from kompas_mcp.connections.splines.straight import build_straight_spline_preview


def build_spline_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return build_straight_spline_preview(payload)


def _points(value: Any) -> list[list[float]]:
    result: list[list[float]] = []
    for point in value or []:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            result.append([float(point[0]), float(point[1])])
    return result


def _polar(radius: float, angle: float) -> list[float]:
    return [radius * math.sin(angle), radius * math.cos(angle)]


def _rotate_path(points: list[list[float]], angle: float) -> list[list[float]]:
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return [
        [point[0] * cos_a + point[1] * sin_a, -point[0] * sin_a + point[1] * cos_a]
        for point in points
    ]


def _dedupe_points(points: list[list[float]], tolerance: float = 1e-9) -> list[list[float]]:
    unique: list[list[float]] = []
    for point in points:
        if not unique or math.dist(unique[-1], point) > tolerance:
            unique.append(list(point))
    return unique


def _radial_arc(radius: float, start_angle: float, end_angle: float, count: int = 96) -> list[list[float]]:
    return [
        _polar(radius, start_angle + (end_angle - start_angle) * index / count)
        for index in range(count + 1)
    ]


def _bounds(paths: list[list[list[float]]]) -> dict[str, float] | None:
    points = [point for path in paths for point in path]
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {"x_min": min(xs), "x_max": max(xs), "y_min": min(ys), "y_max": max(ys)}


def _section_break_contour(
    *,
    start: list[float],
    end: list[float],
    break_radius: float,
    wave_depth: float,
) -> list[list[float]]:
    """Uniform arc-length waves, joining the circular crop ends normally.

    Two tangent-continuous cubics retain the low centre of the section. Their
    endpoint handles point into the shaft along its radii, perpendicular to
    the root circle. Wave amplitude fades only within a quarter wavelength,
    preserving those endpoint directions without long smooth side sections.
    """
    middle = [(start[0] + end[0]) / 2, break_radius]
    handle = (end[0] - start[0]) * 0.18
    curves = [
        [start, [v * 0.75 for v in start], [middle[0] - handle, middle[1]], middle],
        [middle, [middle[0] + handle, middle[1]], [v * 0.75 for v in end], end],
    ]

    def baseline(parameter: float) -> tuple[list[float], list[float]]:
        segment = min(1, int(parameter))
        t = parameter - segment
        u = 1 - t
        a, b, c, d = curves[segment]
        point = [u**3*a[k] + 3*u*u*t*b[k] + 3*u*t*t*c[k] + t**3*d[k] for k in (0, 1)]
        tangent = [3*u*u*(b[k]-a[k]) + 6*u*t*(c[k]-b[k]) + 3*t*t*(d[k]-c[k]) for k in (0, 1)]
        return point, tangent

    # Resample by distance, so the wave is equally dense at the ends and centre.
    baseline_samples = 512
    lengths = [0.0]
    previous = start
    for index in range(1, baseline_samples + 1):
        point, _ = baseline(2 * index / baseline_samples)
        lengths.append(lengths[-1] + math.dist(previous, point))
        previous = point
    total_length = lengths[-1]
    waves = max(12, min(24, round(total_length / (8 * wave_depth))))
    samples = waves * 48
    points: list[list[float]] = []
    interval = 0
    for index in range(samples + 1):
        progress = index / samples
        distance = progress * total_length
        while interval < baseline_samples - 1 and lengths[interval + 1] < distance:
            interval += 1
        fraction = (distance - lengths[interval]) / (lengths[interval + 1] - lengths[interval])
        point, tangent = baseline(2 * (interval + fraction) / baseline_samples)
        edge = min(1.0, progress * waves * 4, (1 - progress) * waves * 4)
        envelope = edge * edge * (3 - 2 * edge)
        offset = math.sin(progress * math.tau * waves) * wave_depth * envelope
        tangent_length = math.hypot(*tangent)
        points.append([point[0] - tangent[1] / tangent_length * offset,
                       point[1] + tangent[0] / tangent_length * offset])
    points[0], points[-1] = list(start), list(end)
    return points


def _radial_break_contour(
    *,
    start_radius: float,
    end_radius: float,
    angle: float,
    wave_depth: float,
    count: int = 40,
) -> list[list[float]]:
    points: list[list[float]] = []
    for index in range(count + 1):
        progress = index / count
        radius = start_radius + (end_radius - start_radius) * progress
        envelope = math.sin(math.pi * progress) ** 0.35
        tangent_offset = math.sin(progress * math.pi * 6.0) * wave_depth * envelope
        local_angle = angle + tangent_offset / max(radius, 1e-9)
        points.append(_polar(radius, local_angle))
    return points


def _crop_sector(points: list[list[float]], half_span: float) -> list[list[float]]:
    """Оставить непрерывный кусок полилинии в угловом окне [-half_span, half_span]."""
    if len(points) < 3:
        return []
    angles = [math.atan2(point[0], point[1]) for point in points]

    def inside(index: int) -> bool:
        return -half_span - 1e-9 <= angles[index] <= half_span + 1e-9

    first = next((index for index in range(len(points)) if inside(index)), None)
    if first is None:
        return []
    last = next((index for index in range(len(points) - 1, -1, -1) if inside(index)), None)
    if last is None or last <= first:
        return []
    cropped = [list(points[index]) for index in range(first, last + 1)]
    # Если соседние точки лежат за границей окна, добавить точное пересечение.
    if first > 0:
        cropped.insert(0, _boundary_point(points[first - 1], points[first], half_span))
    if last < len(points) - 1:
        cropped.append(_boundary_point(points[last], points[last + 1], -half_span))
    return _dedupe_points(cropped)


def _boundary_point(a: list[float], b: list[float], target_angle: float) -> list[float]:
    # Intersect the segment with the boundary ray, retaining corners next to it.
    ray = _polar(1.0, target_angle)
    delta = [b[0] - a[0], b[1] - a[1]]
    cross = delta[0] * ray[1] - delta[1] * ray[0]
    if abs(cross) <= 1e-12:
        return list(a)
    progress = (a[1] * ray[0] - a[0] * ray[1]) / cross
    progress = max(0.0, min(1.0, progress))
    return [a[0] + (b[0] - a[0]) * progress, a[1] + (b[1] - a[1]) * progress]


def _sector_outline(
    period: list[list[float]],
    tooth_count: int,
    visible_pitches: int = 3,
) -> tuple[list[list[float]], float, float]:
    """Собрать непрерывный сектор из повторов одного периода.

    Период начинается на боковой стороне паза и покрывает одну сторону зуба,
    паз и следующий зуб в отрицательном направлении угла. Сектор из трёх
    периодов поворачивается на полшага так, чтобы средний зуб смотрел вверх,
    и обрезается по углам +/-1.5*step.
    """
    if len(period) < 8 or tooth_count < 4:
        return [], -math.pi / tooth_count, math.pi / tooth_count
    step = 2.0 * math.pi / tooth_count
    assembled: list[list[float]] = []
    periods = visible_pitches + 2
    for index in range(periods):
        offset = (visible_pitches - 1 - index) * step
        rotated = _rotate_path(period, offset)
        if assembled:
            rotated = rotated[1:]
        assembled.extend(rotated)
    assembled = _rotate_path(assembled, 0.5 * step)
    half_span = 1.5 * step
    cropped = _crop_sector(assembled, half_span)
    if not cropped:
        return [], half_span, -half_span
    return cropped, math.atan2(*cropped[0]), math.atan2(*cropped[-1])


def adapt_spline_preview(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    warning_items = list(preview.get("warning_items") or [])
    warnings = list(preview.get("warnings") or [])
    body = str(request.get("body") or "shaft")
    family = "shaft_spline" if body == "shaft" else "hub_spline"
    if not preview.get("success"):
        return {
            "ok": False,
            "family": family,
            "view_mode": "end",
            "closed_points": [],
            "feature_paths": [],
            "tone_paths": [],
            "guide_paths": [],
            "reference_paths": [],
            "phantom_bodies": [],
            "bounds": None,
            "summary": {},
            "derived": {},
            "measurements": {},
            "report": dict(preview.get("report") or {}),
            "dimensions": [],
            "warnings": warnings,
            "warning_items": warning_items,
            "errors": list(preview.get("errors") or []),
            "request": dict(request),
        }
    geometry = dict(preview.get("geometry") or {})
    summary = dict(preview.get("summary") or {})
    report = dict(preview.get("report") or {})
    tooth_count = int(summary.get("tooth_count") or 0)
    outer_radius = float(geometry.get("outer_radius_mm") or 0.0)
    root_radius = float(geometry.get("root_radius_mm") or 0.0)
    period = _points(geometry.get("period_outline"))
    sector, left_angle, right_angle = _sector_outline(period, tooth_count, 3)
    step = 2.0 * math.pi / max(1, tooth_count)

    reference_paths: list[dict[str, Any]] = []
    if body == "shaft":
        inside_radius = root_radius
        outside_radius = outer_radius
        if sector:
            tooth_depth = max(0.1, outer_radius - root_radius)
            # Show a substantial part of the shaft core, including for shallow
            # teeth; tooth-depth-based cropping leaves an overly thin strip.
            break_radius = root_radius * 0.52
            break_path = _section_break_contour(
                start=sector[-1],
                end=sector[0],
                break_radius=break_radius,
                wave_depth=max(tooth_depth * 0.12, outer_radius * 0.002),
            )
            outline = _dedupe_points([*sector, *break_path[1:]])
        else:
            outline = []
            break_radius = root_radius * 0.52
        reference_paths = [
            {"key": "outer_circle", "points": _radial_arc(outer_radius, left_angle, right_angle, count=96)},
            {"key": "root_circle", "points": _radial_arc(root_radius, left_angle, right_angle, count=96)},
        ]
        tone_paths = (
            [
                {"points": outline, "stroke": False, "fill": "rgba(227,170,79,.05)"},
                {"points": sector, "tone": "exhaust", "width": 2.2, "closed": False},
                {"points": break_path, "tone": "exhaust", "width": 1.15, "closed": False},
            ]
            if outline else []
        )
        dimension_start = max(1.0, root_radius * 0.8)
        dimensions = [
            {
                "key": "outer_diameter",
                "symbol": "D",
                "orientation": "radial",
                "start": _polar(dimension_start, step),
                "end": _polar(outer_radius, step),
                "value": summary.get("outer_diameter_mm"),
                "unit": "mm",
                "label_normal": 26,
                "label_tangent": 0,
            },
            {
                "key": "inner_diameter",
                "symbol": "d",
                "orientation": "radial",
                "start": _polar(dimension_start, -0.5 * step),
                "end": _polar(root_radius, -0.5 * step),
                "value": summary.get("root_diameter_mm"),
                "unit": "mm",
                "label_normal": -26,
                "label_tangent": 0,
            },
            {
                "key": "tooth_width",
                "symbol": "b",
                "orientation": "horizontal",
                "start": [-0.5 * float(summary.get("tooth_width_mm") or 0.0), outer_radius],
                "end": [0.5 * float(summary.get("tooth_width_mm") or 0.0), outer_radius],
                "value": summary.get("tooth_width_mm"),
                "unit": "mm",
                "label_normal": 0,
                "label_tangent": 0,
            },
        ]
    else:
        hub_radius = float(geometry.get("hub_outside_radius_mm") or outer_radius)
        # geometry.outer_radius_mm is the hub blank, while D is the groove
        # diameter. Its reference circle and dimension must use the spline size.
        outer_radius = 0.5 * float(summary["outer_diameter_mm"])
        inside_radius = float(geometry.get("bore_radius_mm") or root_radius)
        outside_radius = hub_radius
        if sector:
            outer_path = _radial_arc(hub_radius, right_angle, left_angle, count=96)
            wave_depth = max(0.002 * hub_radius, 0.08 * max(0.1, hub_radius - inside_radius))
            right_break = _radial_break_contour(
                start_radius=math.hypot(*sector[-1]),
                end_radius=hub_radius,
                angle=right_angle,
                wave_depth=wave_depth,
            )
            left_break = _radial_break_contour(
                start_radius=hub_radius,
                end_radius=math.hypot(*sector[0]),
                angle=left_angle,
                wave_depth=wave_depth,
            )
            right_break[0] = list(sector[-1])
            right_break[-1] = _polar(hub_radius, right_angle)
            left_break[0] = _polar(hub_radius, left_angle)
            left_break[-1] = list(sector[0])
            outline = _dedupe_points([*sector, *right_break[1:], *outer_path[1:], *left_break[1:]])
        else:
            outline = []
        reference_paths = [
            {"key": "tip_circle", "points": _radial_arc(inside_radius, left_angle, right_angle, count=96)},
            {"key": "root_circle", "points": _radial_arc(outer_radius, left_angle, right_angle, count=96)},
            {"key": "outer_circle", "points": _radial_arc(hub_radius, left_angle, right_angle, count=96)},
        ]
        tone_paths = (
            [
                {"points": outline, "stroke": False, "fill": "rgba(227,170,79,.09)"},
                {"points": sector, "tone": "exhaust", "width": 2.2, "closed": False},
                {"points": outer_path, "tone": "exhaust", "width": 2.2, "closed": False},
                {"points": right_break, "tone": "exhaust", "width": 1.15, "closed": False},
                {"points": left_break, "tone": "exhaust", "width": 1.15, "closed": False},
            ]
            if outline else []
        )
        dimension_start = max(1.0, 0.82 * inside_radius)
        dimensions = [
            {
                "key": "inner_diameter",
                "symbol": "d",
                "orientation": "radial",
                "start": _polar(dimension_start, -0.5 * step),
                "end": _polar(inside_radius, -0.5 * step),
                "value": summary.get("inner_diameter_mm"),
                "unit": "mm",
                "label_normal": -26,
                "label_tangent": 0,
            },
            {
                "key": "root_diameter",
                "symbol": "D",
                "orientation": "radial",
                "start": _polar(dimension_start, 0.5 * step),
                "end": _polar(outer_radius, 0.5 * step),
                "value": summary.get("outer_diameter_mm"),
                "unit": "mm",
                "label_normal": 26,
                "label_tangent": 0,
            },
            {
                "key": "hub_outside_diameter",
                "symbol": "Dо",
                "orientation": "radial",
                "start": _polar(0.9 * outer_radius, -0.28 * step),
                "end": _polar(hub_radius, -0.28 * step),
                "value": summary.get("hub_outside_diameter_mm"),
                "unit": "mm",
                "label_normal": -20,
                "label_tangent": 0,
            },
        ]

    closed = _dedupe_points(outline) if outline else []
    paths: list[list[list[float]]] = []
    if closed:
        paths.append(closed)
    paths.extend(item["points"] for item in reference_paths)
    bounds = _bounds(paths)
    return {
        "ok": bool(preview.get("success")),
        "family": family,
        "view_mode": "end",
        "closed_points": [closed] if closed else [],
        "feature_paths": [],
        "tone_paths": tone_paths,
        "guide_paths": [],
        "reference_paths": reference_paths,
        "phantom_bodies": [],
        "bounds": bounds,
        "coordinate_system": geometry.get("coordinate_system"),
        "summary": summary,
        "derived": preview.get("derived"),
        "measurements": preview.get("measurements"),
        "fits": preview.get("fits"),
        "report": report,
        "dimensions": dimensions,
        "warnings": warnings,
        "warning_items": warning_items,
        "preview_window": {
            "tooth_gap_count": 3,
            "visible_tooth_count": 3,
            "section_style": "cropped_sector",
        },
        "request": dict(request),
    }
