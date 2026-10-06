"""DIN 8191 rolling rack envelope, evaluated entirely on the host (Layer 2).

``build_din_space(profile, z)`` does not mutate profile. The JSON-compatible
result has ``geometry`` (also exposed by the top-level path keys), ``updates``
to merge into the profile, and ``diagnostics``. Paths use millimetres, +Y as the
space centreline and clockwise positive angles. ``profile_path`` runs from the
left outside-circle endpoint through the generated root to the right endpoint.
The caller owns the outside-circle tooth cap and circular repetition.

Source: local complete Chinese reproduction of DIN 8191:1998, printed pp.
168/169, Figure 3 and Table 4. W and outside diameter are supplied by the caller
(including DIN 8191:2022 f24=14.95, f32=19.93 corrections). This translated source
is not a conformity certificate. Series 06 has an unresolved 0.030 mm rack
height inconsistency: its full candidate is returned, but only involute strokes
are in supported_paths. No construction closure or guessed circular root is used.

For a 30-degree, half-pitch rack, the sharp triangle half-height is
A=p/(4*tan(alpha)). Tip/root rounding gives depths A-r1 and A-r2, so hF is
2*A-r1-r2, NOT a dedendum. W fixes shift h=x*m and hence the cutter reference
line R+h. A cutter point (u,v), translated by -R*t and rotated clockwise by t,
has envelope contact t=(u+(h+v)*dv/du)/R. The straight flank is the supplied
shifted involute. Rounded-tip contacts give the root; rounded rack roots may
also trim the involute near the outside circle. A genuine undercut trims the
returning branch at an intersection; unlike the ordinary rack/flank junction,
that intersection is generally NOT tangent.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from kompas_mcp.sketch_runtime.cubic import fit_cubic_path

_ALPHA = math.pi / 6.0
_LIMIT = math.pi / 3.0
# series: pitch, hF, r1 (cutter tip), r2 (cutter root), Table-4 y
_RACK = {
    "06": (9.525, 5.519, 0.7, 2.0, 0.6),
    "08": (12.7, 7.5, 1.0, 2.5, 0.6),
    "12": (19.05, 11.698, 3.0, 1.8, 0.5),
    "16": (25.4, 15.197, 4.4, 2.4, 0.5),
    "24": (38.1, 22.996, 6.5, 3.5, 0.5),
    "32": (50.8, 29.994, 9.0, 5.0, 0.5),
}


def _bisect(function: Callable[[float], float], lo: float, hi: float) -> float:
    """Bounded bracketed solve; no unconstrained Newton branch selection."""
    left, right = function(lo), function(hi)
    if abs(left) < 1e-14:
        return lo
    if abs(right) < 1e-14:
        return hi
    if left * right > 0:
        raise ValueError("DIN envelope root is not bracketed")
    for _ in range(64):
        mid = (lo + hi) / 2.0
        value = function(mid)
        if left * value <= 0:
            hi = mid
        else:
            lo, left = mid, value
    return (lo + hi) / 2.0


def _sample(function: Callable[[float], list[float]], lo: float,
            hi: float, count: int = 96) -> list[list[float]]:
    if abs(hi - lo) < 1e-14:
        return [function(lo)]
    return [function(lo + (hi - lo) * i / count) for i in range(count + 1)]


def _radius(point: list[float]) -> float:
    return math.hypot(*point)


def _has_crossing(path: list[list[float]]) -> bool:
    """Bounded pair check on one sampled half (at most 289 points)."""
    def cross(a: list[float], b: list[float], c: list[float]) -> float:
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    segments = [(a, b, min(a[0], b[0]), max(a[0], b[0]),
                 min(a[1], b[1]), max(a[1], b[1]))
                for a, b in zip(path, path[1:])]
    for i, (a, b, xmin, xmax, ymin, ymax) in enumerate(segments):
        for c, d, cxmin, cxmax, cymin, cymax in segments[i+2:]:
            if xmax < cxmin or cxmax < xmin or ymax < cymin or cymax < ymin:
                continue
            if cross(a, b, c)*cross(a, b, d) <= 0 and cross(c, d, a)*cross(c, d, b) <= 0:
                return True
    return False


def _tangent_angle(first: Callable[[float], list[float]], at: float,
                   second: Callable[[float], list[float]], other: float,
                   scale: float) -> float:
    # Tangent lines, not traversal orientation: undercut trimming can reverse
    # the parametric branch. Two-sided finite differences avoid chord bias.
    def tangent(fn: Callable[[float], list[float]], t: float, step: float) -> list[float]:
        a, b = fn(t - step), fn(t + step)
        return [b[0] - a[0], b[1] - a[1]]
    a = tangent(first, at, 1e-6)
    b = tangent(second, other, scale * 1e-6)
    return math.degrees(math.atan2(abs(a[0]*b[1]-a[1]*b[0]),
                                   abs(a[0]*b[0]+a[1]*b[1])))


def build_din_space(profile: dict[str, Any], z: int) -> dict[str, Any]:
    """Build a source-labelled tool envelope, or reject unsupported topology.

    Required profile fields: module_mm, profile_shift_coefficient,
    reference_tooth_thickness_mm, base_diameter_mm, outside_diameter_mm.
    Optional pitch_diameter_mm and span_measurement_mm/span_tooth_count are
    independently checked. Table-4 tool dimensions are resolved by pitch so the
    old series-16 r2=2.1 input cannot contaminate the envelope. Errors raise
    ValueError; unresolved source evidence returns explicit partial statuses.
    """
    if isinstance(z, bool) or not isinstance(z, int) or z < 15:
        raise ValueError("DIN 8191 tooth count must be an integer >= 15")
    required = ("module_mm", "profile_shift_coefficient",
                "reference_tooth_thickness_mm", "base_diameter_mm",
                "outside_diameter_mm")
    values = {key: float(profile[key]) for key in required}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError("DIN profile fields must be finite")
    m = values["module_mm"]
    p = math.pi * m
    row = next(((series, data) for series, data in _RACK.items()
                if math.isclose(p, data[0], rel_tol=0, abs_tol=1e-7)), None)
    if row is None:
        raise ValueError("DIN cutter envelope requires a Table-4 pitch")
    series, (_, height, r1, r2, table_y) = row
    R, h = z*m/2.0, values["profile_shift_coefficient"]*m
    base, outside = values["base_diameter_mm"]/2, values["outside_diameter_mm"]/2
    thickness = p/2 + 2*h*math.tan(_ALPHA)
    tolerance = p*1e-9
    if not math.isclose(base, R*math.cos(_ALPHA), abs_tol=tolerance, rel_tol=0):
        raise ValueError("DIN base circle disagrees with 30-degree rack")
    if not math.isclose(values["reference_tooth_thickness_mm"], thickness,
                        abs_tol=tolerance, rel_tol=0):
        raise ValueError("DIN W-derived shift and reference thickness disagree")
    if "pitch_diameter_mm" in profile and not math.isclose(
            float(profile["pitch_diameter_mm"]), 2*R, abs_tol=tolerance, rel_tol=0):
        raise ValueError("DIN reference diameter disagrees with module/tooth count")
    if not 0 < thickness < p or not outside > base:
        raise ValueError("DIN shifted involute has invalid thickness/outside circle")
    A = p/(4*math.tan(_ALPHA))
    height_residual = height - (2*A-r1-r2)
    # Table 4 prints 08 hF to ONE decimal, all other hF values to three.
    height_rounding = 0.05 if series == "08" else 0.0005
    ambiguous = abs(height_residual) > height_rounding+1e-8
    resolution = profile.get("din_rack_resolution", "unresolved")
    user_rack = ambiguous and resolution in {"keep_radii", "keep_height"}
    if user_rack:
        if resolution == "keep_height":
            r1 = 2*A-r2-height
        else:
            height = 2*A-r1-r2
        if r1 <= 0:
            raise ValueError("User DIN rack resolution produced an invalid tip radius")
        ambiguous = False
    half = (p/4-h*math.tan(_ALPHA))/R
    inv_alpha = math.tan(_ALPHA)-_ALPHA

    def involute(radius: float) -> list[float]:
        parameter = math.sqrt(max(0.0, (radius/base)**2-1))
        angle = half-inv_alpha+parameter-math.atan(parameter)
        return [radius*math.sin(angle), radius*math.cos(angle)]

    def envelope(u: float, v: float, slope: float) -> list[float]:
        t = (u+(h+v)*slope)/R
        q, y = u-R*t, R+h+v
        return [q*math.cos(t)+y*math.sin(t), y*math.cos(t)-q*math.sin(t)]

    def tip(beta: float) -> list[float]:
        return envelope(r1*math.sin(beta), -A+2*r1-r1*math.cos(beta),
                        math.tan(beta))

    def crest(beta: float) -> list[float]:
        return envelope(p/2-r2*math.sin(beta), A-2*r2+r2*math.cos(beta),
                        math.tan(beta))

    tip_end = _radius(tip(_LIMIT))
    straight_lower_v, straight_upper_v = -A+1.5*r1, A-1.5*r2
    undercut = h+straight_lower_v < -R*math.sin(_ALPHA)**2-tolerance
    root_join_beta = _LIMIT
    if undercut:
        # The tip reaches the base circle shortly before its tangent point.
        # Include that precise boundary: a uniform grid can miss this tiny
        # interval for low tooth counts. Trim against the positive involute,
        # discarding the negative-parameter returning flank and its loop.
        if tip_end <= base:
            raise ValueError("DIN undercut does not reach the retained involute")
        at_base = _bisect(lambda b: _radius(tip(b))-base, 0, _LIMIT)
        def difference(beta: float) -> float:
            point = tip(beta)
            nominal = involute(_radius(point))
            return math.atan2(point[0], point[1])-math.atan2(nominal[0], nominal[1])
        root_join_beta = _bisect(difference, at_base, _LIMIT)
    root_join_radius = _radius(tip(root_join_beta))
    upper_join_beta = _LIMIT
    # A concave rack-root arc can have a returning envelope near its flank
    # tangent (particularly 06/08 at low z). Trim that loop too; simply attaching
    # the entire arc introduces a self-intersection at the retained involute.
    def upper_difference(beta: float) -> float:
        point = crest(beta)
        nominal = involute(_radius(point))
        return math.atan2(point[0], point[1])-math.atan2(nominal[0], nominal[1])
    crest_center_offset = h+A-2*r2
    def crest_speed_numerator(beta: float) -> float:
        cosine = math.cos(beta)
        return R*r2*cosine**3-crest_center_offset**2-crest_center_offset*r2*cosine
    if crest_center_offset >= 0 or crest_speed_numerator(0) <= 0:
        raise ValueError("DIN cutter crest placement is outside the supported envelope branch")
    if crest_speed_numerator(_LIMIT) < 0:
        # Here the numerator is strictly increasing in cos(beta): one cusp,
        # hence one returning loop. Bracket at the exact cusp instead of hoping
        # a sampling grid catches an arbitrarily short negative interval.
        cusp = _bisect(crest_speed_numerator, 0, _LIMIT)
        upper_join_beta = _bisect(upper_difference, 0, cusp)
    upper_join_radius = _radius(crest(upper_join_beta))
    if straight_lower_v >= straight_upper_v or root_join_radius >= outside:
        raise ValueError("DIN cutter leaves no usable working flank")
    if upper_join_radius <= root_join_radius:
        raise ValueError("DIN cutter upper transition precedes the root join")
    tip_path = _sample(tip, 0, root_join_beta)
    involute_end = min(outside, upper_join_radius)
    flank = _sample(involute, root_join_radius, involute_end)
    position_error = math.dist(tip_path[-1], flank[0])
    if position_error > tolerance:
        raise ValueError("DIN cutter root/involute join failed positional verification")
    flank[0] = tip_path[-1]
    upper_path: list[list[float]] = []
    if outside > upper_join_radius+tolerance:
        if _radius(crest(0)) < outside:
            raise ValueError("DIN outside circle exceeds the full cutter crest envelope")
        upper_beta = _bisect(lambda b: _radius(crest(b))-outside, 0, upper_join_beta)
        upper_path = _sample(crest, upper_join_beta, upper_beta)
        if math.dist(upper_path[0], flank[-1]) > tolerance:
            raise ValueError("DIN cutter upper/involute join failed verification")
        upper_path[0] = flank[-1]
    right = tip_path + flank[1:] + upper_path[1:]
    # Independently check sampled-half intersections. Convex, disjoint half
    # sectors then separate mirror/repeated halves; all vertices except the
    # outside endpoint are inside the outside circle, separating the cap too.
    radii = [_radius(point) for point in right]
    angles = [math.atan2(point[0], point[1]) for point in right]
    finite = all(math.isfinite(v) for point in right for v in point)
    monotone = all(b > a for a, b in zip(radii, radii[1:]))
    sector = all(0 < a < math.pi/z for a in angles[1:])
    if not finite or not monotone or not sector or radii[0] <= 0:
        raise ValueError("DIN envelope fails finite/simple/disjoint-sector verification")
    if _has_crossing(right):
        raise ValueError("DIN sampled cutter envelope intersects itself")
    left = [[-x, y] for x, y in reversed(right)]
    gap = left + right[1:]
    flanks = [[[-x, y] for x, y in reversed(flank)], flank]
    # Keep analytic pieces separate: genuine undercut/crest trim intersections
    # are corners, not interpolation nodes of a smoothed compound contour.
    cad_curves: list[dict[str, Any]] = []

    def mirror(function: Callable[[float], list[float]]) -> Callable[[float], list[float]]:
        def mirrored(parameter: float) -> list[float]:
            x, y = function(parameter)
            return [-x, y]
        return mirrored

    def add_curve(identifier: str, function: Callable[[float], list[float]],
                  lo: float, hi: float, start: list[float], end: list[float]) -> None:
        curve = fit_cubic_path(function, lo, hi, tolerance=0.0005)
        endpoint_error = max(math.dist(curve["points"][0], start),
                             math.dist(curve["points"][-1], end))
        if endpoint_error > tolerance:
            raise ValueError("DIN cubic endpoints disagree with the existing gap")
        # Analytic intersection solvers differ only at floating-point roundoff.
        # Reuse the raw path's canonical joins to make CAD closure exact.
        curve["points"][0], curve["points"][-1] = start[:], end[:]
        curve["id"] = identifier
        curve["fit"]["endpoint_adjustment_mm"] = endpoint_error
        curve["fit"]["max_error_mm"] += endpoint_error
        if curve["fit"]["max_error_mm"] > curve["fit"]["tolerance_mm"]:
            raise ValueError("DIN cubic endpoint adjustment exceeds fit tolerance")
        cad_curves.append(curve)

    if upper_path:
        add_curve("din_left_upper", mirror(crest), upper_beta, upper_join_beta,
                  gap[0], flanks[0][0])
    add_curve("din_left_involute", mirror(involute), involute_end, root_join_radius,
              flanks[0][0], flanks[0][-1])
    add_curve("din_root_envelope", tip, -root_join_beta, root_join_beta,
              flanks[0][-1], flank[0])
    add_curve("din_right_involute", involute, root_join_radius, involute_end,
              flank[0], flank[-1])
    if upper_path:
        add_curve("din_right_upper", crest, upper_join_beta, upper_beta,
                  flank[-1], gap[-1])
    join_angle = _tangent_angle(tip, root_join_beta, involute, root_join_radius, p)
    if not undercut and join_angle > 1e-4:
        raise ValueError("DIN ordinary root/involute join is not tangent")
    upper_angle = (_tangent_angle(crest, upper_join_beta, involute, upper_join_radius, p)
                   if upper_path else None)
    if upper_angle is not None and upper_join_beta == _LIMIT and upper_angle > 1e-4:
        raise ValueError("DIN ordinary upper/involute join is not tangent")
    span_error = None
    if "span_measurement_mm" in profile and "span_tooth_count" in profile:
        span = m*math.cos(_ALPHA)*((float(profile["span_tooth_count"])-0.5)*math.pi
                                  + z*inv_alpha) + 2*h*math.sin(_ALPHA)
        span_error = span-float(profile["span_measurement_mm"])
        if not math.isfinite(span_error) or abs(span_error) > tolerance:
            raise ValueError("DIN envelope changed the supplied W measurement")
    status = "user_resolved_rack_envelope" if user_rack else "partial_rack_height_inconsistent" if ambiguous else "rolling_rack_envelope_reconstructed"
    root_status = "candidate_rack_height_inconsistent" if ambiguous else "generated_cutter_tip_envelope"
    updates = {
        "root_diameter_mm": 2*radii[0], "root_diameter_status": root_status,
        "root_status": root_status, "profile_status": status,
        "root_round_radius_mm": None,
        "tool_tooth_height_mm": height, "tool_tip_radius_mm": r1,
        "tool_root_radius_mm": r2, "involute_display_min_radius_mm": root_join_radius,
        "involute_display_limit_status": "trimmed_undercut_intersection" if undercut else "tangent_tool_envelope_join",
        "tip_status": "cutter_root_envelope_at_outside_circle" if upper_path else "outside_circle_on_involute",
        "supported_flank_paths": flanks,
    }
    geometry = {
        "cad_curve_entities": cad_curves,
        "profile_path": gap, "supported_paths": flanks if ambiguous or user_rack else [gap],
        "user_radial_paths": [gap] if user_rack else [],
        "working_flank_paths": flanks, "root_path": [[-x, y] for x, y in reversed(tip_path)] + tip_path[1:],
        "upper_transition_paths": ([[[-x, y] for x, y in reversed(upper_path)], upper_path]
                                   if upper_path else []),
        "profile_status": status, "root_status": root_status,
        "construction_closure_path": [], "period_angle_rad": 2*math.pi/z,
        "outside_radius_mm": outside,
        "tooth_tip_arc": {"radius_mm": outside,
                          "start_angle_rad": angles[-1],
                          "end_angle_rad": 2*math.pi/z-angles[-1]},
    }
    diagnostics = {
        "cad_curve_fit": {
            "entity_count": len(cad_curves),
            "pole_count": sum(len(curve["points"]) for curve in cad_curves),
            "max_error_mm": max(curve["fit"]["max_error_mm"] for curve in cad_curves),
            "validation_sample_count": sum(curve["fit"]["validation_sample_count"] for curve in cad_curves),
            "tolerance_mm": 0.0005,
        },
        "source": "DIN 8191:1998 Chinese reproduction pp.168-169 Figure 3/Table 4",
        "conformity_claim": False, "series": series, "table_y": table_y,
        "rack_half_sharp_height_mm": A, "rack_reference_radial_offset_mm": h,
        "rack_tip_depth_from_reference_mm": A-r1,
        "rack_crest_height_from_reference_mm": A-r2,
        "rack_height_formula_residual_mm": height_residual,
        "rack_height_status": "user_resolved_not_standard_correction" if user_rack else "unresolved_06_0.030mm_discrepancy" if ambiguous else "agrees_with_printed_table_precision",
        "user_rack_resolution": resolution if user_rack else None,
        "rack_height_rounding_half_unit_mm": height_rounding,
        "undercut": undercut, "root_join_parameter_rad": root_join_beta,
        "root_join_radius_mm": root_join_radius,
        "root_join_type": "trimmed_intersection" if undercut else "tangent",
        "root_join_tangent_angle_deg": join_angle,
        "root_join_position_error_mm": position_error,
        "upper_transition_used": bool(upper_path), "span_residual_mm": span_error,
        "upper_join_type": "trimmed_intersection" if upper_join_beta < _LIMIT else "tangent",
        "upper_join_tangent_angle_deg": upper_angle,
        "finite": finite, "half_radius_strictly_increasing": monotone,
        "disjoint_half_sectors": sector, "repeated_contour_simple": True,
        "topology_proof": "intersection-checked sampled halves in disjoint convex half sectors, strictly inside outside-circle caps except at endpoints",
        "topology_scope": "sampled_polyline_with_analytic_outside_caps",
        "sample_count": len(gap),
        "source_corrections": {"r2_16_mm": 2.4, "y_08": 0.6,
                               "DIN_2022_f24_mm": 14.95, "DIN_2022_f32_mm": 19.93},
    }
    return {**geometry, "geometry": geometry, "updates": updates, "diagnostics": diagnostics}
