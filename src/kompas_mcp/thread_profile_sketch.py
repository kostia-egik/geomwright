from __future__ import annotations

import math
from typing import Any


def _point(x: float, y: float) -> list[float]:
    return [float(x), float(y)]


def _line(target: str, start: list[float], end: list[float], *, line_style: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"target": target, "start": list(start), "end": list(end)}
    if line_style is not None:
        payload["line_style"] = int(line_style)
    return payload


def _y_on_taper(x: float, center_y: float, slope: float) -> float:
    return float(center_y) + float(slope) * float(x)


def _line_slope(line: dict[str, Any]) -> float | None:
    start = list(line.get("start") or [])
    end = list(line.get("end") or [])
    if len(start) != 2 or len(end) != 2:
        return None
    dx = float(end[0]) - float(start[0])
    if abs(dx) <= 1e-12:
        return None
    return (float(end[1]) - float(start[1])) / dx


def _line_intersection(
    a1: list[float],
    a2: list[float],
    b1: list[float],
    b2: list[float],
) -> list[float]:
    x1, y1 = float(a1[0]), float(a1[1])
    x2, y2 = float(a2[0]), float(a2[1])
    x3, y3 = float(b1[0]), float(b1[1])
    x4, y4 = float(b2[0]), float(b2[1])
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) <= 1e-12:
        raise ValueError("profile flank lines are parallel and cannot define a theory apex")
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denominator
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denominator
    return _point(px, py)


def _point_on_line_at_y(a: list[float], b: list[float], y: float) -> list[float]:
    x1, y1 = float(a[0]), float(a[1])
    x2, y2 = float(b[0]), float(b[1])
    dy = y2 - y1
    if abs(dy) <= 1e-12:
        raise ValueError("cannot project a horizontal line to a target Y")
    t = (float(y) - y1) / dy
    return _point(x1 + t * (x2 - x1), float(y))


def _point_on_line_at_x(a: list[float], b: list[float], x: float) -> list[float]:
    x1, y1 = float(a[0]), float(a[1])
    x2, y2 = float(b[0]), float(b[1])
    dx = x2 - x1
    if abs(dx) <= 1e-12:
        raise ValueError("cannot project a vertical line to a target X")
    t = (float(x) - x1) / dx
    return _point(float(x), y1 + t * (y2 - y1))


def _constraint_key(constraint: dict[str, Any]) -> tuple[Any, ...]:
    return (
        constraint.get("kind"),
        constraint.get("target"),
        constraint.get("index"),
        constraint.get("partner"),
        constraint.get("partner_index"),
    )


def _has_constraint(constraints: list[dict[str, Any]], expected: dict[str, Any]) -> bool:
    expected_items = tuple(sorted(expected.items()))
    for constraint in constraints:
        if all(constraint.get(key) == value for key, value in expected_items):
            return True
    return False


def _build_flat_v60_verification(
    *,
    profile_lines: list[dict[str, Any]],
    construction_lines: list[dict[str, Any]],
    named_points: dict[str, list[float]],
    taper_slope: float,
    root_shape: str,
    carrier_shape: str,
) -> dict[str, Any]:
    lines_by_name = {str(line.get("target")): line for line in profile_lines + construction_lines}
    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, **details: Any) -> None:
        item = {"name": name, "ok": bool(ok)}
        item.update(details)
        checks.append(item)

    def same_point(left: list[float], right: list[float], tolerance: float = 1e-9) -> bool:
        return abs(float(left[0]) - float(right[0])) <= tolerance and abs(float(left[1]) - float(right[1])) <= tolerance

    add_check("profile_closed", same_point(named_points["left_outer"], named_points["left_outer_close"]))
    add_check(
        "flat_root_has_no_arc",
        str(root_shape) == "flat",
        root_shape=str(root_shape),
    )
    add_check(
        "line_3_on_surface_taper",
        abs((_line_slope(lines_by_name["profile_line_3"]) or 0.0) - float(taper_slope)) <= 1e-9,
        expected_slope=float(taper_slope),
        actual_slope=_line_slope(lines_by_name["profile_line_3"]),
    )
    add_check(
        "line_4_on_root_taper",
        abs((_line_slope(lines_by_name["profile_line_4"]) or 0.0) - float(taper_slope)) <= 1e-9,
        expected_slope=float(taper_slope),
        actual_slope=_line_slope(lines_by_name["profile_line_4"]),
    )
    if str(carrier_shape) == "conical":
        for profile_name, theory_name in (("profile_line_1", "left_theory"), ("profile_line_2", "right_theory")):
            profile_slope = _line_slope(lines_by_name[profile_name])
            theory_slope = _line_slope(lines_by_name[theory_name])
            add_check(
                f"{profile_name}_geometrically_collinear_with_{theory_name}",
                profile_slope is not None and theory_slope is not None and abs(profile_slope - theory_slope) <= 1e-9,
                profile_slope=profile_slope,
                theory_slope=theory_slope,
            )
        for name in (
            "left_outer_ref",
            "right_outer_ref",
            "left_root_ref",
            "right_root_ref",
            "left_pitch_ref",
            "right_pitch_ref",
        ):
            add_check(
                f"{name}_is_horizontal_dimension_ref",
                abs((_line_slope(lines_by_name[name]) or 0.0)) <= 1e-12,
                actual_slope=_line_slope(lines_by_name[name]),
            )
        for name in (
            "left_outer_projection_ref",
            "right_outer_projection_ref",
            "left_root_projection_ref",
            "right_root_projection_ref",
        ):
            start = list(lines_by_name[name]["start"])
            end = list(lines_by_name[name]["end"])
            add_check(
                f"{name}_is_vertical_lock_ref",
                abs(float(start[0]) - float(end[0])) <= 1e-12,
                x=float(start[0]),
            )

    return {
        "ok": all(bool(check["ok"]) for check in checks),
        "carrier_shape": str(carrier_shape),
        "root_shape": str(root_shape),
        "checks": checks,
    }


def build_v60_flat_thread_profile_sketch(normalized: dict[str, Any]) -> dict[str, Any]:
    """Build a named, self-checked flat-root V60 thread profile sketch plan.

    The returned plan intentionally separates real tapered profile lines from
    horizontal/vertical reference lines used by driving dimensions. This avoids
    making KOMPAS solve horizontal values on sloped entities.
    """

    internal = bool(normalized["internal"])
    half_pitch = float(normalized["pitch"]) / 2.0
    base_reference_radius = float(normalized["thread_reference_radius"])
    taper_slope = float(normalized.get("profile_taper_slope") or 0.0)
    entry_offset = float(normalized.get("profile_entry_offset") or 0.0)
    fallback_compensation = abs(taper_slope) * entry_offset
    if internal:
        fallback_compensation = -fallback_compensation
    taper_compensation = float(normalized.get("profile_taper_compensation_radius") or fallback_compensation)
    carrier_shape = str(normalized.get("carrier_shape") or "cylindrical")
    conical = carrier_shape == "conical"
    root_shape = str(normalized.get("profile_root_shape") or "flat")
    root_half_width = float(normalized["profile_root_half_width"])
    outer_half_width = float(normalized["profile_outer_half_width"])
    axis_radius_sign = -1.0 if internal else 1.0
    base_crest_y = axis_radius_sign * base_reference_radius
    # The sketch origin is shifted before the first turn by entry_offset. On a
    # cone, the local surface radius at that section changes; keep that as an
    # explicit radius compensation so dimension checks can prove it was applied.
    crest_y = base_crest_y + axis_radius_sign * taper_compensation

    if internal:
        depth_center_y = crest_y - float(normalized["profile_tangent_depth"])
        theory_center_y = crest_y - float(normalized["profile_crest_drop"])
        apex_center_y = crest_y - float(normalized["radial_cut_depth"])
    else:
        depth_center_y = crest_y - float(normalized["radial_cut_depth"])
        theory_center_y = crest_y + float(normalized["profile_base_drop"])
        apex_center_y = crest_y - float(normalized["profile_apex_height"])

    left_outer = _point(-outer_half_width, _y_on_taper(-outer_half_width, crest_y, taper_slope))
    right_outer = _point(outer_half_width, _y_on_taper(outer_half_width, crest_y, taper_slope))
    left_root = _point(-root_half_width, _y_on_taper(-root_half_width, depth_center_y, taper_slope))
    right_root = _point(root_half_width, _y_on_taper(root_half_width, depth_center_y, taper_slope))
    profile_points = [left_outer, left_root, right_root, right_outer, left_outer]
    if conical:
        apex_center = _line_intersection(left_outer, left_root, right_outer, right_root)
        left_theory_width = _point_on_line_at_x(apex_center, left_outer, -half_pitch)
        right_theory_width = _point_on_line_at_x(apex_center, right_outer, half_pitch)
    else:
        left_theory_width = _point(-half_pitch, theory_center_y)
        right_theory_width = _point(half_pitch, theory_center_y)

    named_points = {
        "origin": _point(0.0, 0.0),
        "crest_center": _point(0.0, crest_y),
        "theory_center": _point(0.0, theory_center_y),
        "apex_center": apex_center if conical else _point(0.0, apex_center_y),
        "root_center": _point(0.0, depth_center_y),
        "left_pitch_width": _point(-half_pitch, theory_center_y),
        "right_pitch_width": _point(half_pitch, theory_center_y),
        "left_theory_width": left_theory_width,
        "right_theory_width": right_theory_width,
        "left_outer_width": _point(-outer_half_width, crest_y),
        "right_outer_width": _point(outer_half_width, crest_y),
        "left_root_width": _point(-root_half_width, depth_center_y),
        "right_root_width": _point(root_half_width, depth_center_y),
        "left_outer": left_outer,
        "right_outer": right_outer,
        "left_root": left_root,
        "right_root": right_root,
        "left_outer_close": left_outer,
        "taper_compensation_radius": _point(0.0, taper_compensation),
    }
    construction_lines = [
        _line("radius_ref", named_points["origin"], named_points["crest_center"], line_style=6),
        _line("theory_drop_ref", named_points["crest_center"], named_points["theory_center"], line_style=6),
        _line("apex_ref", named_points["crest_center"], named_points["apex_center"], line_style=6),
        _line("left_pitch_ref", named_points["theory_center"], named_points["left_pitch_width"], line_style=6),
        _line("right_pitch_ref", named_points["theory_center"], named_points["right_pitch_width"], line_style=6),
        _line("left_theory", named_points["apex_center"], named_points["left_theory_width"], line_style=6),
        _line("right_theory", named_points["apex_center"], named_points["right_theory_width"], line_style=6),
        _line("left_outer_ref", named_points["crest_center"], named_points["left_outer_width"], line_style=6),
        _line("right_outer_ref", named_points["crest_center"], named_points["right_outer_width"], line_style=6),
        _line("left_root_ref", named_points["root_center"], named_points["left_root_width"], line_style=6),
        _line("right_root_ref", named_points["root_center"], named_points["right_root_width"], line_style=6),
    ]
    if not internal:
        construction_lines.append(_line("root_depth_ref", named_points["crest_center"], named_points["root_center"], line_style=6))
    if conical:
        construction_lines.extend(
            [
                _line("surface_taper_ref", left_outer, right_outer, line_style=6),
                _line("root_taper_ref", left_root, right_root, line_style=6),
                _line("pitch_taper_ref", left_theory_width, right_theory_width, line_style=6),
                _line("left_outer_projection_ref", named_points["left_outer_width"], left_outer, line_style=6),
                _line("right_outer_projection_ref", named_points["right_outer_width"], right_outer, line_style=6),
                _line("left_root_projection_ref", named_points["left_root_width"], left_root, line_style=6),
                _line("right_root_projection_ref", named_points["right_root_width"], right_root, line_style=6),
            ]
        )

    profile_lines = [
        _line("profile_line_1", left_outer, left_root),
        _line("profile_line_2", right_outer, right_root),
        _line("profile_line_3", right_outer, left_outer),
        _line("profile_line_4", left_root, right_root),
    ]
    axis_margin = max(
        abs(crest_y),
        abs(theory_center_y),
        abs(apex_center_y),
        abs(depth_center_y),
        abs(half_pitch),
        outer_half_width,
        root_half_width,
        1.0,
    ) * 0.25
    verification = _build_flat_v60_verification(
        profile_lines=profile_lines,
        construction_lines=construction_lines,
        named_points=named_points,
        taper_slope=taper_slope,
        root_shape=root_shape,
        carrier_shape=carrier_shape,
    )
    if not verification["ok"]:
        failed = [check["name"] for check in verification["checks"] if not check["ok"]]
        raise ValueError(f"flat V60 thread profile sketch verification failed: {', '.join(failed)}")

    return {
        "profile_points": profile_points,
        "profile_lines": profile_lines,
        "profile_arcs": [],
        "construction_lines": construction_lines,
        "axis_start": [0.0, 0.0],
        "axis_end": [0.0, min(0.0, apex_center_y, depth_center_y) - axis_margin],
        "named_points": named_points,
        "verification": verification,
    }


def verify_v60_flat_thread_profile_contract(
    *,
    constraints: list[dict[str, Any]],
    dimensions: list[dict[str, Any]],
    dimension_expressions: dict[str, str],
    normalized: dict[str, Any],
) -> dict[str, Any]:
    """Verify that the generated flat V60 sketch is constrained as intended.

    This is not a replacement for KOMPAS' DOF solver. It is a contract check for
    the failure modes that are easy to miss visually: unconstrained flank links,
    missing projection locks, missing driving dimensions, and conical entry
    offset compensation omitted from the reference-radius expression.
    """

    carrier_shape = str(normalized.get("carrier_shape") or "cylindrical")
    conical = carrier_shape == "conical"
    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, **details: Any) -> None:
        item = {"name": name, "ok": bool(ok)}
        item.update(details)
        checks.append(item)

    def require_constraint(name: str, expected: dict[str, Any]) -> None:
        add_check(name, _has_constraint(constraints, expected), expected=dict(expected))

    dimension_targets = {str(dimension.get("target") or "") for dimension in dimensions}
    expression_by_target = {
        str(dimension.get("target") or ""): str(dimension.get("expression") or "")
        for dimension in dimensions
    }
    for target in ("radius_ref", "right_pitch_ref", "theory_drop_ref", "apex_ref", "right_outer_ref", "right_root_ref"):
        add_check(f"{target}_has_driving_dimension", target in dimension_targets, target=target)
    if not bool(normalized.get("internal")):
        add_check("root_depth_ref_has_driving_dimension", "root_depth_ref" in dimension_targets, target="root_depth_ref")

    require_constraint(
        "left_flank_collinear_with_theory",
        {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
    )
    require_constraint(
        "right_flank_collinear_with_theory",
        {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
    )
    require_constraint(
        "right_outer_ref_locked_to_profile",
        {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "right_outer_projection_ref" if conical else "profile_line_2", "partner_index": 0},
    )
    require_constraint(
        "right_root_ref_locked_to_profile",
        {
            "kind": "merge_points",
            "target": "right_root_ref",
            "index": 1,
            "partner": "right_root_projection_ref" if conical else "profile_line_4",
            "partner_index": 0 if conical else 1,
        },
    )

    if conical:
        for name in (
            "left_outer_projection_ref",
            "right_outer_projection_ref",
            "left_root_projection_ref",
            "right_root_projection_ref",
        ):
            require_constraint(f"{name}_is_vertical", {"kind": "vertical", "target": name})
        require_constraint(
            "surface_flat_collinear_with_taper_ref",
            {"kind": "collinear", "target": "profile_line_3", "partner": "surface_taper_ref"},
        )
        require_constraint(
            "root_flat_collinear_with_taper_ref",
            {"kind": "collinear", "target": "profile_line_4", "partner": "root_taper_ref"},
        )
        require_constraint(
            "left_theory_endpoint_locked_to_profile",
            {"kind": "merge_points", "target": "left_theory", "index": 1, "partner": "profile_line_1", "partner_index": 0},
        )
        require_constraint(
            "right_theory_endpoint_locked_to_profile",
            {"kind": "merge_points", "target": "right_theory", "index": 1, "partner": "profile_line_2", "partner_index": 0},
        )
        require_constraint(
            "pitch_taper_ref_left_locked_to_left_theory",
            {"kind": "merge_points", "target": "pitch_taper_ref", "index": 0, "partner": "left_theory", "partner_index": 1},
        )
        require_constraint(
            "pitch_taper_ref_right_locked_to_right_theory",
            {"kind": "merge_points", "target": "pitch_taper_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
        )
        for target in ("right_outer_projection_ref", "right_root_projection_ref"):
            add_check(f"{target}_has_driving_dimension", target in dimension_targets, target=target)
        require_constraint(
            "left_outer_projection_matches_right_outer_projection",
            {"kind": "equal_length", "target": "left_outer_projection_ref", "partner": "right_outer_projection_ref"},
        )
        require_constraint(
            "left_root_projection_matches_right_root_projection",
            {"kind": "equal_length", "target": "left_root_projection_ref", "partner": "right_root_projection_ref"},
        )
        compensation = float(normalized.get("profile_taper_compensation_radius") or 0.0)
        reference_expression = str(dimension_expressions.get("sketch_reference_radius") or expression_by_target.get("radius_ref") or "")
        expected_operator = "-" if compensation < 0.0 else "+"
        add_check(
            "reference_radius_expression_compensates_entry_offset",
            abs(compensation) > 1e-12 and "/ 2" in reference_expression and expected_operator in reference_expression,
            compensation=compensation,
            expected_operator=expected_operator,
            expression=reference_expression,
        )

    return {
        "ok": all(bool(check["ok"]) for check in checks),
        "carrier_shape": carrier_shape,
        "root_shape": str(normalized.get("profile_root_shape") or "flat"),
        "checks": checks,
        "constraint_count": len({_constraint_key(constraint) for constraint in constraints}),
        "dimension_count": len(dimensions),
    }


def build_v60_flat_thread_profile_constraints(*, internal: bool, carrier_shape: str) -> list[dict[str, Any]]:
    carrier_shape = str(carrier_shape or "cylindrical")
    base = [
        {"kind": "fixed_point", "target": "origin", "index": 0},
        {"kind": "vertical", "target": "axis"},
        {"kind": "vertical", "target": "radius_ref"},
        {"kind": "vertical", "target": "theory_drop_ref"},
        {"kind": "vertical", "target": "apex_ref"},
        {"kind": "horizontal", "target": "left_pitch_ref"},
        {"kind": "horizontal", "target": "right_pitch_ref"},
        {"kind": "horizontal", "target": "left_root_ref"},
        {"kind": "horizontal", "target": "right_root_ref"},
        {"kind": "horizontal", "target": "left_outer_ref"},
        {"kind": "horizontal", "target": "right_outer_ref"},
        {"kind": "merge_points", "target": "radius_ref", "index": 0, "partner": "axis", "partner_index": 0},
        {"kind": "merge_points", "target": "theory_drop_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
        {"kind": "merge_points", "target": "apex_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
        {"kind": "merge_points", "target": "axis", "index": 1, "partner": "apex_ref", "partner_index": 1},
        {"kind": "merge_points", "target": "left_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
        {"kind": "merge_points", "target": "right_outer_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
        {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "left_pitch_ref", "partner_index": 0},
        {"kind": "merge_points", "target": "theory_drop_ref", "index": 1, "partner": "right_pitch_ref", "partner_index": 0},
        {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "left_theory", "partner_index": 0},
        {"kind": "merge_points", "target": "apex_ref", "index": 1, "partner": "right_theory", "partner_index": 0},
        {"kind": "equal_length", "target": "left_pitch_ref", "partner": "right_pitch_ref"},
        {"kind": "equal_length", "target": "left_outer_ref", "partner": "right_outer_ref"},
        {"kind": "equal_length", "target": "left_root_ref", "partner": "right_root_ref"},
    ]
    if not internal:
        base.extend(
            [
                {"kind": "vertical", "target": "root_depth_ref"},
                {"kind": "merge_points", "target": "root_depth_ref", "index": 0, "partner": "radius_ref", "partner_index": 1},
                {"kind": "merge_points", "target": "root_depth_ref", "index": 1, "partner": "left_root_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "root_depth_ref", "index": 1, "partner": "right_root_ref", "partner_index": 0},
            ]
        )
    else:
        base.extend(
            [
                {"kind": "point_on_curve", "target": "left_root_ref", "index": 0, "partner": "axis"},
                {"kind": "point_on_curve", "target": "right_root_ref", "index": 0, "partner": "axis"},
            ]
        )
    if carrier_shape == "conical":
        base.extend(
            [
                {"kind": "vertical", "target": "left_outer_projection_ref"},
                {"kind": "vertical", "target": "right_outer_projection_ref"},
                {"kind": "vertical", "target": "left_root_projection_ref"},
                {"kind": "vertical", "target": "right_root_projection_ref"},
                {"kind": "equal_length", "target": "left_outer_projection_ref", "partner": "right_outer_projection_ref"},
                {"kind": "equal_length", "target": "left_root_projection_ref", "partner": "right_root_projection_ref"},
                {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "left_outer_projection_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "right_outer_projection_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "left_root_projection_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "right_root_projection_ref", "partner_index": 0},
                {"kind": "merge_points", "target": "left_outer_projection_ref", "index": 1, "partner": "profile_line_1", "partner_index": 0},
                {"kind": "merge_points", "target": "left_outer_projection_ref", "index": 1, "partner": "profile_line_3", "partner_index": 1},
                {"kind": "merge_points", "target": "right_outer_projection_ref", "index": 1, "partner": "profile_line_2", "partner_index": 0},
                {"kind": "merge_points", "target": "right_outer_projection_ref", "index": 1, "partner": "profile_line_3", "partner_index": 0},
                {"kind": "merge_points", "target": "left_root_projection_ref", "index": 1, "partner": "profile_line_1", "partner_index": 1},
                {"kind": "merge_points", "target": "left_root_projection_ref", "index": 1, "partner": "profile_line_4", "partner_index": 0},
                {"kind": "merge_points", "target": "right_root_projection_ref", "index": 1, "partner": "profile_line_2", "partner_index": 1},
                {"kind": "merge_points", "target": "right_root_projection_ref", "index": 1, "partner": "profile_line_4", "partner_index": 1},
                {"kind": "merge_points", "target": "left_theory", "index": 1, "partner": "profile_line_1", "partner_index": 0},
                {"kind": "merge_points", "target": "right_theory", "index": 1, "partner": "profile_line_2", "partner_index": 0},
                {"kind": "merge_points", "target": "surface_taper_ref", "index": 0, "partner": "profile_line_3", "partner_index": 1},
                {"kind": "merge_points", "target": "surface_taper_ref", "index": 1, "partner": "profile_line_3", "partner_index": 0},
                {"kind": "merge_points", "target": "root_taper_ref", "index": 0, "partner": "profile_line_4", "partner_index": 0},
                {"kind": "merge_points", "target": "root_taper_ref", "index": 1, "partner": "profile_line_4", "partner_index": 1},
                {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
                {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
                {"kind": "merge_points", "target": "pitch_taper_ref", "index": 0, "partner": "left_theory", "partner_index": 1},
                {"kind": "merge_points", "target": "pitch_taper_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
                {"kind": "collinear", "target": "profile_line_3", "partner": "surface_taper_ref"},
                {"kind": "collinear", "target": "profile_line_4", "partner": "root_taper_ref"},
            ]
        )
        return base
    base.extend(
        [
            {"kind": "horizontal", "target": "profile_line_3"},
            {"kind": "horizontal", "target": "profile_line_4"},
            {"kind": "merge_points", "target": "left_pitch_ref", "index": 1, "partner": "left_theory", "partner_index": 1},
            {"kind": "merge_points", "target": "right_pitch_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
            {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_1", "partner_index": 0},
            {"kind": "merge_points", "target": "left_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 1},
            {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_2", "partner_index": 0},
            {"kind": "merge_points", "target": "right_outer_ref", "index": 1, "partner": "profile_line_3", "partner_index": 0},
            {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_1", "partner_index": 1},
            {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 0},
            {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "profile_line_2", "partner_index": 1},
            {"kind": "merge_points", "target": "right_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 1},
            {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
            {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
        ]
    )
    return base
