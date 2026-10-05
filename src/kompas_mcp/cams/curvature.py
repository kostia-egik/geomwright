"""Contact-aware C2 lift synthesis for a translating flat tappet.

The support function h = base + lash + lift satisfies h'' + h = rho.
Positive piecewise-linear rho gives an exactly convex active envelope. This
bounded family search is not an OEM fit or a valve-train dynamics optimizer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .lift import MotionCurve, curve_from_points
from .errors import CurvatureSynthesisError

_FRACTIONS = (0.0, 0.025, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.55, 0.7, 0.85, 1.0)


@dataclass(frozen=True)
class _Span:
    start: float
    length: float
    radius: float
    slope: float
    h: float
    v: float

    def state(self, t: float) -> tuple[float, float, float, float]:
        c, d = self.h - self.radius, self.v - self.slope
        cosine, sine = math.cos(t), math.sin(t)
        h = self.radius + self.slope * t + c * cosine + d * sine
        v = self.slope - c * sine + d * cosine
        a = -c * cosine - d * sine
        j = c * sine - d * cosine
        return h, v, a, j

    def velocity_extrema(self) -> tuple[float, float]:
        c, d = self.h - self.radius, self.v - self.slope
        root = math.atan2(-c, d) % math.pi
        times = [0.0, self.length]
        if 0.0 < root < self.length:
            times.append(root)
        values = [self.state(t)[1] for t in times]
        return min(values), max(values)

    def derivative_peaks(self) -> tuple[float, float]:
        c, d = self.h - self.radius, self.v - self.slope
        a_root = math.atan2(d, c) % math.pi
        j_root = math.atan2(-c, d) % math.pi
        a_times = [0.0, self.length] + ([a_root] if 0.0 < a_root < self.length else [])
        j_times = [0.0, self.length] + ([j_root] if 0.0 < j_root < self.length else [])
        return (max(abs(self.state(t)[2]) for t in a_times),
                max(abs(self.state(t)[3]) for t in j_times))


def _spans(beta: float, controls: list[float], h: float) -> tuple[_Span, ...]:
    result = []
    v = 0.0
    for i in range(len(_FRACTIONS) - 1):
        start = beta * _FRACTIONS[i]
        length = beta * (_FRACTIONS[i + 1] - _FRACTIONS[i])
        span = _Span(start, length, controls[i],
                     (controls[i + 1] - controls[i]) / length, h, v)
        result.append(span)
        h, v, _, _ = span.state(length)
    return tuple(result)


def _solve_flank(beta: float, h0: float, peak: float, floor: float,
                 nose: float, max_acceleration: float | None,
                 max_jerk: float | None) -> tuple[tuple[_Span, ...], tuple[float, ...], float, float, float] | None:
    baseline = [h0, *([floor] * (len(_FRACTIONS) - 2)), nose]
    spans = _spans(beta, baseline, h0)
    h_end, v_end, _, _ = spans[-1].state(spans[-1].length)
    dh, dv = peak - h_end, -v_end
    weights = []
    bases = []
    for i in range(1, len(_FRACTIONS) - 1):
        basis = [0.0] * len(_FRACTIONS)
        basis[i] = 1.0
        bases.append(basis)
    # Broad early pulses avoid obtaining every high-lift solution through a
    # narrow initial acceleration spike. All basis values remain nonnegative.
    for peak_index, end_index in ((2, 5), (3, 6), (4, 7), (5, 8), (6, 9), (4, 9)):
        p, end = _FRACTIONS[peak_index], _FRACTIONS[end_index]
        bases.append([t / p if t <= p else max(0.0, (end - t) / (end - p))
                      for t in _FRACTIONS])
    for i, basis in enumerate(bases):
        response = _spans(beta, basis, 0.0)
        h, v, _, _ = response[-1].state(response[-1].length)
        weights.append((i, basis, h, v))

    best = None
    for n, (i, bi, hi, vi) in enumerate(weights):
        for j, bj, hj, vj in weights[n + 1:]:
            determinant = hi * vj - hj * vi
            if abs(determinant) < 1e-14:
                continue
            ai = (dh * vj - hj * dv) / determinant
            aj = (hi * dv - dh * vi) / determinant
            if not math.isfinite(ai) or not math.isfinite(aj) or ai < -1e-9 or aj < -1e-9:
                continue
            controls = [r + max(0.0, ai) * a + max(0.0, aj) * b
                        for r, a, b in zip(baseline, bi, bj)]
            if controls[1] <= h0:
                continue  # no hidden stationary interval inside the seat event
            candidate = _spans(beta, controls, h0)
            end_h, end_v, _, _ = candidate[-1].state(candidate[-1].length)
            if abs(end_h - peak) > 1e-8 * peak or abs(end_v) > 1e-8 * peak:
                continue
            extrema = [span.velocity_extrema() for span in candidate]
            if min(low for low, _ in extrema) < -1e-8:
                continue
            speed = max(high for _, high in extrema)
            derivatives = [span.derivative_peaks() for span in candidate]
            acceleration = max(a for a, _ in derivatives)
            jerk = max(j for _, j in derivatives)
            if max_acceleration is not None and acceleration > max_acceleration * (1.0 + 1e-9):
                continue
            if max_jerk is not None and jerk > max_jerk * (1.0 + 1e-9):
                continue
            score = (speed, max(controls), i, j)
            if best is None or score < best[0]:
                best = (score, candidate, tuple(controls), speed, acceleration, jerk)
    return None if best is None else best[1:]


def _sample(spans: tuple[_Span, ...], h0: float,
            samples_per_degree: float) -> list[tuple[float, float, float, float, float]]:
    beta = spans[-1].start + spans[-1].length
    count = max(2, math.ceil(math.degrees(beta) * samples_per_degree))
    times = sorted({beta * i / count for i in range(count + 1)}
                   | {span.start for span in spans} | {beta})
    points = []
    index = 0
    for theta in times:
        if points and theta - points[-1][0] < 1e-12:
            continue
        while index + 1 < len(spans) and theta >= spans[index + 1].start:
            index += 1
        h, v, a, j = spans[index].state(theta - spans[index].start)
        points.append((theta, h - h0, v, a, j))
    return points


def build_curvature_lift_curve(*, base_radius: float, max_lift: float,
                             open_angle_deg: float, close_angle_deg: float,
                             lash: float = 0.0, phase_deg: float = 0.0,
                             min_curvature_radius: float = 1.0,
                             nose_radius: float | None = None,
                             max_acceleration: float | None = None,
                             max_jerk: float | None = None,
                             samples_per_degree: float = 2.0) -> MotionCurve:
    values = (base_radius, max_lift, open_angle_deg, close_angle_deg, lash,
              phase_deg, min_curvature_radius, samples_per_degree)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("curvature profile parameters must be finite")
    if min(base_radius, max_lift, open_angle_deg, close_angle_deg, min_curvature_radius) <= 0.0:
        raise ValueError("curvature profile dimensions and angles must be positive")
    if lash < 0.0 or not 0.0 < samples_per_degree <= 10.0:
        raise ValueError("invalid lash or curvature sampling budget")
    for value in (max_acceleration, max_jerk):
        if value is not None and (not math.isfinite(value) or value <= 0.0):
            raise ValueError("acceleration and jerk limits must be positive finite numbers")
    if open_angle_deg + close_angle_deg > 360.0:
        raise ValueError("curvature event must not exceed 360 cam degrees")
    h0 = base_radius + lash
    peak = h0 + max_lift
    if not math.isfinite(h0) or not math.isfinite(peak):
        raise ValueError("curvature support radii overflow")
    floor = min_curvature_radius
    if floor >= h0:
        raise CurvatureSynthesisError("cam_curvature_floor", "minimum curvature radius must be below the seat support radius", radius=h0)
    betas = (math.radians(open_angle_deg), math.radians(close_angle_deg))
    for beta in betas:
        if (peak - floor) * math.cos(beta) >= h0 - floor:
            minimum_angle = math.degrees(math.acos((h0 - floor) / (peak - floor)))
            raise CurvatureSynthesisError("cam_flat_support_bound",
                f"flat contact support bound: each flank must exceed {minimum_angle:.3f} cam degrees",
                angle=round(minimum_angle, 3))
    if nose_radius is not None:
        if not math.isfinite(nose_radius) or not floor <= nose_radius < peak:
            raise CurvatureSynthesisError("cam_nose_range", "nose_radius must lie between minimum curvature radius and peak support radius", minimum=floor, maximum=peak)
        noses = [nose_radius]
    else:
        # Fixed bounded search, independent of output discretization.
        noses = sorted({floor, *[floor + (peak - floor) * i / 16.0 for i in range(1, 16)]})
    best = None
    for nose in noses:
        opening = _solve_flank(betas[0], h0, peak, floor, nose, max_acceleration, max_jerk)
        closing = opening if betas[0] == betas[1] else _solve_flank(betas[1], h0, peak, floor, nose, max_acceleration, max_jerk)
        if opening is None or closing is None:
            continue
        score = (max(opening[2], closing[2]), max(max(opening[1]), max(closing[1])), nose)
        if best is None or score < best[0]:
            best = (score, nose, opening, closing)
    if best is None:
        raise CurvatureSynthesisError("cam_curvature_no_solution",
            "no monotone solution in the bounded curvature-spline family; widen the event or adjust curvature/acceleration/jerk limits")
    _, nose, opening, closing = best
    rise = _sample(opening[0], h0, samples_per_degree)
    fall = _sample(closing[0], h0, samples_per_degree)
    phase = math.radians(phase_deg)
    points = [(phase + t, s, v, a, j) for t, s, v, a, j in rise]
    points += [(phase + betas[0] + betas[1] - t, s, -v, a, -j)
               for t, s, v, a, j in reversed(fall[:-1])]
    meta = {
        "law": "curvature_spline", "max_lift": max_lift,
        "knot_fractions": list(_FRACTIONS),
        "open_angle": open_angle_deg, "close_angle": close_angle_deg, "dwell_angle": 0.0,
        "event_angle": open_angle_deg + close_angle_deg,
        "phase_deg": phase_deg, "nose_radius_mm": nose,
        "minimum_active_curvature_mm": min(*opening[1], *closing[1]),
        "peak_contact_offset_mm": max(opening[2], closing[2]),
        "opening_peak_contact_offset_mm": opening[2],
        "closing_peak_contact_offset_mm": closing[2],
        "peak_event_acceleration_mm_per_rad2": max(opening[3], closing[3]),
        "peak_event_jerk_mm_per_rad3": max(opening[4], closing[4]),
        "opening_curvature_controls_mm": list(opening[1]),
        "closing_curvature_controls_mm": list(closing[1]),
        "junctions": [points[0][0], points[-1][0]],
        "synthesis_status": "bounded_family_solution",
    }
    return curve_from_points("valve", points, meta)
