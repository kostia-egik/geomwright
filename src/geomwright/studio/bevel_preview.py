"""Presentation-only projections of the calculated bevel rim (no COM)."""
from __future__ import annotations

import math
from collections.abc import Callable


def _arc(radius: float, start: float, end: float, count: int = 96) -> list[list[float]]:
    return [[radius * math.sin(a), radius * math.cos(a)]
            for a in (start + (end - start) * i / count for i in range(count + 1))]


def _bounds(paths: list[list[list[float]]]) -> dict[str, float]:
    points = [p for path in paths for p in path]
    return dict(x_min=min(p[0] for p in points), x_max=max(p[0] for p in points),
                y_min=min(p[1] for p in points), y_max=max(p[1] for p in points))


def build_bevel_views(sector: list[list[float]], geometry: dict, summary: dict,
                      *, break_contour: Callable[..., list[list[float]]]) -> dict:
    """The back-cone contour is shared, but each view has an explicit frame.

    Straight flanks are homothetic along apex rays. A future circular family
    must supply its own longitudinal curves, not bend these straight lines.
    """
    if not sector:
        raise ValueError("A bevel preview needs a nonempty outer contour")
    delta = math.radians(summary["pitch_cone_angle_deg"])
    sine, cosine = math.sin(delta), math.cos(delta)
    re = summary["outer_cone_distance_mm"]
    ratio = summary["inner_cone_distance_mm"] / re
    tip = summary["outer_tip_diameter_mm"] / 2
    pitch = summary["outer_pitch_diameter_mm"] / 2
    root = summary["outer_root_diameter_mm"] / 2
    step = 2 * math.pi / summary["tooth_count"]
    start, end = (math.atan2(p[0], p[1]) for p in (sector[0], sector[-1]))
    inner = [[p[0] * ratio, p[1] * ratio] for p in sector]
    rim = [*sector, *reversed(inner), sector[0]]
    # The solid blank continues to the axis beneath the small-end teeth.
    # The inner tooth contour is an edge on that body, not a hole boundary.
    material = [*sector, [0., 0.], sector[0]]
    inner_root = min(math.hypot(*p) for p in inner)
    base_band = min(summary["module_mm"] * .4, inner_root * .12)
    cut_radius = inner_root - base_band
    wave = min(summary["module_mm"] * .08, base_band * .25)
    front_break = break_contour(outside_radius=root, break_radius=cut_radius,
                                left_angle=start, right_angle=end, wave_depth=wave,
                                wavy_sides=True)
    front_break[0], front_break[-1] = sector[-1], sector[0]
    # The upper clipping boundary is outside the part: clipping exactly on
    # the tooth profile would erase half of its normal contour stroke.
    crop_top = _arc(tip + summary["module_mm"] * .2, start, end)
    crop_outline = [*crop_top, *front_break, crop_top[0]]
    tone_paths = [
        {"points": material, "tone": "exhaust", "stroke": False,
         "fill": "rgba(227,170,79,.04)"},
        {"points": rim, "tone": "exhaust", "width": 1.8},
    ]
    # Separate tooth-tip surfaces, preserving the sampled circular edge.
    caps: list[list[list[float]]] = []
    cap: list[list[float]] = []
    for p in sector:
        if abs(math.hypot(*p) - tip) < 1e-7:
            cap.append(p)
        elif cap:
            caps.append(cap)
            cap = []
    if cap:
        caps.append(cap)
    for cap in caps:
        if len(cap) < 2:
            continue
        tone_paths.append({
            "points": [*cap, *[[p[0] * ratio, p[1] * ratio] for p in reversed(cap)], cap[0]],
            "tone": "exhaust", "width": 2.1,
            "fill": "rgba(227,170,79,.10)",
        })
    references = [{"key": "pitch_circle", "points": _arc(pitch, start, end)},
                  {"key": "inner_pitch_circle", "points": _arc(pitch * ratio, start, end)}]
    groove_lines = []
    for index in range(-2, 2):
        angle = (index + .5) * step
        c, s = math.cos(angle), math.sin(angle)
        for edge in geometry.get("gap_root_edges", []):
            p = [edge[0] * c + edge[1] * s, edge[1] * c - edge[0] * s]
            if start - 1e-9 <= math.atan2(*p) <= end + 1e-9:
                groove_lines.append([p, [p[0] * ratio, p[1] * ratio]])
    radius_start = root * ratio * 0.88
    dimensions = [dict(key=key, symbol=symbol, orientation="radial",
                       start=[radius_start * math.sin(angle), radius_start * math.cos(angle)],
                       end=[radius * math.sin(angle), radius * math.cos(angle)],
                       value=2 * radius, unit="mm", label_normal=normal, label_tangent=tangent)
                  for key, symbol, radius, angle, normal, tangent in (
                      ("tip_diameter", "dₐₑ", tip, step, 35, 30),
                      ("pitch_diameter", "dₑ", pitch, -step, -34, -18),
                      ("root_diameter", "d_fₑ", root, step / 2, 24, 0))]

    def end_project(p: list[float]) -> list[float]:
        # Recover X on the revolved back cone, then view normal to the
        # pitch generator of the central tooth. This is not the virtual rack.
        x = (sine * math.hypot(*p) - re) / cosine
        return [p[0], sine * x + cosine * p[1]]

    # Crop the local view to the central tooth and its adjacent gaps.
    detail_sector = [p for p in sector if abs(math.atan2(p[0], p[1])) <= step + 1e-8]
    dstart, dend = (math.atan2(p[0], p[1]) for p in (detail_sector[0], detail_sector[-1]))
    base_radius = max(geometry["back_face_radius_mm"], root - .55 * (tip - root))
    detail_wave = summary["module_mm"] * .06
    detail_break = break_contour(
        outside_radius=math.hypot(*detail_sector[-1]),
        break_radius=base_radius + detail_wave * cosine * 1.3,
        left_angle=dstart, right_angle=dend,
        wave_depth=detail_wave * cosine, side_wave_depth=detail_wave * 2,
        wavy_sides=True,
    )
    detail_break[0], detail_break[-1] = detail_sector[-1], detail_sector[0]
    detail_outline = [*detail_sector, *detail_break[1:]]
    detail_refs = [{"key": key, "points": [end_project(p) for p in _arc(r, dstart, dend)]}
                   for key, r in (("pitch", pitch), ("root", root))]
    # Actual projected pitch chord: intersections of the calculated end
    # contour, not the nominal virtual-wheel control measurement.
    intersections = []
    for a, b in zip(detail_sector, detail_sector[1:]):
        ra, rb = math.hypot(*a), math.hypot(*b)
        if (ra - pitch) * (rb - pitch) < 0:
            lo, hi = 0., 1.
            for _ in range(35):
                f = (lo + hi) / 2
                p = [a[k] + f * (b[k] - a[k]) for k in (0, 1)]
                if (math.hypot(*p) - pitch) * (ra - pitch) > 0:
                    lo = f
                else:
                    hi = f
            if abs(math.atan2(p[0], p[1])) < step / 2:
                intersections.append(end_project(p))
    tooth_dimensions = []
    if len(intersections) == 2:
        a, b = sorted(intersections)
        tooth_dimensions.append(dict(symbol="sₑ,proj", start=a, end=b,
                                     value=b[0] - a[0], offset=-32))
    tooth_dimensions.extend([
        dict(symbol="hₐₑ", start=[0, 0], end=[0, summary["outer_addendum_mm"]],
             value=summary["outer_addendum_mm"], offset=54),
        dict(symbol="h_fₑ", start=[0, -summary["outer_dedendum_mm"]], end=[0, 0],
             value=summary["outer_dedendum_mm"], offset=-54),
    ])
    tooth_view = dict(
        outline=[end_project(p) for p in detail_outline], references=detail_refs,
        profile=[end_project(p) for p in detail_sector],
        break_path=[end_project(p) for p in detail_break],
        dimensions=tooth_dimensions, projection="orthographic_back_cone",
        view_direction=[cosine, 0., -sine], selected_tooth_angle_rad=0.,
    )
    tooth_view["bounds"] = _bounds([tooth_view["outline"], *[p["points"] for p in detail_refs]])
    return dict(
        closed_points=[material], rim_outline=rim, tone_paths=tone_paths, reference_paths=references,
        crop_outline=crop_outline, break_paths=[front_break],
        guide_paths=groove_lines,
        dimensions=dimensions, bounds=_bounds([sector, front_break]),
        labels=[{"x": 0, "y": tip * (1 + ratio) / 2,
                 "text_key": "gear.bevel_front_selected", "tone": "exhaust"},
                {"placement": "caption", "text_key": "gear.bevel_front_title"}],
        preview_window=dict(tooth_gap_count=3, visible_tooth_count=3,
                            section_style="projected_rim_sector", cut_style="wavy"),
        tooth_end_view=tooth_view,
    )
