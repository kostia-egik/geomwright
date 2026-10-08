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
    outside_radius: float,
    break_radius: float,
    left_angle: float,
    right_angle: float,
    wave_depth: float,
) -> list[list[float]]:
    points: list[list[float]] = []
    side_samples = 24
    for index in range(side_samples + 1):
        progress = index / side_samples
        smooth = progress * progress * (3.0 - 2.0 * progress)
        radius = outside_radius + (break_radius - outside_radius) * smooth
        radius += math.sin(progress * math.pi * 4.0) * wave_depth * 0.045
        angle = right_angle + math.sin(progress * math.pi) * wave_depth * 0.14 / outside_radius
        points.append(_polar(radius, angle))
    bottom_samples = 96
    for index in range(1, bottom_samples + 1):
        progress = index / bottom_samples
        angle = right_angle + (left_angle - right_angle) * progress
        radius = break_radius + math.sin(progress * math.pi * 8.0) * wave_depth
        points.append(_polar(radius, angle))
    for index in range(1, side_samples + 1):
        progress = index / side_samples
        smooth = progress * progress * (3.0 - 2.0 * progress)
        radius = break_radius + (outside_radius - break_radius) * smooth
        radius += math.sin(progress * math.pi * 4.0) * wave_depth * 0.045
        angle = left_angle - math.sin(progress * math.pi) * wave_depth * 0.14 / outside_radius
        points.append(_polar(radius, angle))
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
        cropped[0] = _boundary_point(points[first - 1], points[first], half_span, angles[first - 1], angles[first])
    if last < len(points) - 1:
        cropped[-1] = _boundary_point(points[last], points[last + 1], -half_span, angles[last], angles[last + 1])
    return _dedupe_points(cropped)


def _boundary_point(a: list[float], b: list[float], target_angle: float, angle_a: float, angle_b: float) -> list[float]:
    span = angle_b - angle_a
    if abs(span) <= 1e-12:
        return list(a)
    progress = (target_angle - angle_a) / span
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
    return cropped, -half_span, half_span


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
            break_radius = max(root_radius * 0.58, root_radius - tooth_depth * 1.6)
            break_path = _section_break_contour(
                outside_radius=root_radius,
                break_radius=break_radius,
                left_angle=left_angle,
                right_angle=right_angle,
                wave_depth=max(tooth_depth * 0.08, outer_radius * 0.0015),
            )
            break_path[0] = list(sector[-1])
            break_path[-1] = list(sector[0])
            outline = _dedupe_points([*sector, *break_path[1:]])
        else:
            outline = []
            break_radius = root_radius * 0.7
        reference_paths = [
            {"key": "outer_circle", "points": _radial_arc(outer_radius, left_angle, right_angle, count=96)},
            {"key": "root_circle", "points": _radial_arc(root_radius, left_angle, right_angle, count=96)},
        ]
        tone_paths = (
            [{"points": outline, "tone": "exhaust", "width": 2.4, "fill": "rgba(227,170,79,.05)"}]
            if outline else []
        )
        dimension_start = max(1.0, break_radius * 1.12)
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
                "start": [-0.5 * float(summary.get("tooth_width_mm") or 0.0), root_radius + 0.35 * (outer_radius - root_radius)],
                "end": [0.5 * float(summary.get("tooth_width_mm") or 0.0), root_radius + 0.35 * (outer_radius - root_radius)],
                "value": summary.get("tooth_width_mm"),
                "unit": "mm",
                "label_normal": 0,
                "label_tangent": 0,
            },
        ]
    else:
        hub_radius = float(geometry.get("hub_outside_radius_mm") or outer_radius)
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
            [{"points": outline, "tone": "exhaust", "width": 2.2, "fill": "rgba(227,170,79,.09)", "stroke": "#e3aa4f"}]
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
                "start": _polar(0.55 * hub_radius, 0.0),
                "end": _polar(hub_radius, 0.0),
                "value": summary.get("hub_outside_diameter_mm"),
                "unit": "mm",
                "label_normal": 20,
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
