"""Bounded C2 valve-motion family, independent of follower/contact geometry.

Acceleration is linear on each span, hence lift is cubic and jerk is constant.
Two nonnegative pulse amplitudes satisfy the nose lift and zero nose velocity.
Both flanks share nose acceleration, including for unequal flank durations.
The caller must check the real contact envelope; this is not flat-face synthesis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import CamSynthesisError
from .lift import MotionCurve, curve_from_points

_KNOTS = (0.0, 0.0625, 0.125, 0.25, 0.375, 0.5, 0.625, 0.8125, 1.0)
_RISE_PULSES = ((2, 4), (3, 5), (4, 6), (3, 6))
_BRAKE_PULSES = ((3, 6), (4, 7), (5, 7))
_NOSE_FACTORS = (0.0, 1.0, 2.0, 4.0)
MAX_MOTION_CANDIDATES = len(_RISE_PULSES) * len(_BRAKE_PULSES) * len(_NOSE_FACTORS)


@dataclass(frozen=True)
class AccelerationSpan:
    start: float
    length: float
    lift: float
    velocity: float
    acceleration: float
    jerk: float

    def state(self, t: float) -> tuple[float, float, float, float]:
        a, j = self.acceleration, self.jerk
        return (self.lift + self.velocity * t + a * t*t / 2.0 + j * t**3 / 6.0,
                self.velocity + a * t + j * t*t / 2.0, a + j * t, j)

    def velocity_range(self) -> tuple[float, float]:
        times = [0.0, self.length]
        if self.jerk != 0.0:
            root = -self.acceleration / self.jerk
            if 0.0 < root < self.length:
                times.append(root)
        values = [self.state(t)[1] for t in times]
        return min(values), max(values)


def _integrate(beta: float, controls: list[float]) -> tuple[AccelerationSpan, ...]:
    spans = []
    lift = velocity = 0.0
    for left, right, a, b in zip(_KNOTS, _KNOTS[1:], controls, controls[1:]):
        length = beta * (right - left)
        span = AccelerationSpan(beta * left, length, lift, velocity, a, (b - a) / length)
        spans.append(span)
        lift, velocity, _, _ = span.state(length)
    return tuple(spans)


def _pulse(start: int, peak: int, end: int) -> list[float]:
    left, middle, right = _KNOTS[start], _KNOTS[peak], _KNOTS[end]
    return [max(0.0, min((t - left) / (middle - left), (right - t) / (right - middle)))
            for t in _KNOTS]


def _flank(beta: float, height: float, nose_a: float, rise: tuple[int, int],
           brake: tuple[int, int]) -> tuple[AccelerationSpan, ...] | None:
    baseline = [0.0] * (len(_KNOTS) - 1) + [nose_a]
    positive = _pulse(0, *rise)
    negative = [-v for v in _pulse(*brake, len(_KNOTS) - 1)]
    def end(controls):
        spans = _integrate(beta, controls)
        return spans[-1].state(spans[-1].length)[:2]
    h0, v0 = end(baseline)
    hp, vp = end(positive)
    hn, vn = end(negative)
    determinant = hp * vn - hn * vp
    if abs(determinant) < 1e-14:
        return None
    ap = ((height - h0) * vn + hn * v0) / determinant
    an = (-hp * v0 - (height - h0) * vp) / determinant
    if not all(math.isfinite(v) and v >= -1e-10 for v in (ap, an)):
        return None
    controls = [a + max(0.0, ap) * p + max(0.0, an) * n
                for a, p, n in zip(baseline, positive, negative)]
    spans = _integrate(beta, controls)
    h, v, _, _ = spans[-1].state(spans[-1].length)
    if abs(h - height) > height * 1e-9 or abs(v) > height * 1e-9:
        return None
    if controls[1] <= 0.0 or min(s.velocity_range()[0] for s in spans) < -1e-9:
        return None
    return spans


def _sample(spans: tuple[AccelerationSpan, ...], density: float) -> list[tuple[float, float, float, float, float]]:
    beta = spans[-1].start + spans[-1].length
    count = max(2, math.ceil(math.degrees(beta) * density))
    times = sorted({beta * i / count for i in range(count + 1)} | {s.start for s in spans} | {beta})
    points = []
    index = 0
    for t in times:
        if points and t - points[-1][0] < 1e-12:
            continue
        while index + 1 < len(spans) and t >= spans[index + 1].start:
            index += 1
        points.append((t, *spans[index].state(t - spans[index].start)))
    return points


def resample_motion_spline(curve: MotionCurve, density: float) -> MotionCurve:
    """Regenerate the same control solution, without rerunning shape selection."""
    meta = curve.meta
    if meta.get("law") != "motion_spline" or not math.isfinite(density) or not 0 < density <= 10:
        raise CamSynthesisError("cam_motion_input", "invalid motion spline resampling request")
    opening_beta, closing_beta = math.radians(meta["open_angle"]), math.radians(meta["close_angle"])
    opening = _integrate(opening_beta, meta["opening_acceleration_controls"])
    closing = _integrate(closing_beta, meta["closing_acceleration_controls"])
    phase = math.radians(meta["phase_deg"])
    points = [(phase + t, h, v, a, j) for t, h, v, a, j in _sample(opening, density)]
    points += [(phase + opening_beta + closing_beta - t, h, -v, a, -j)
               for t, h, v, a, j in reversed(_sample(closing, density)[:-1])]
    return curve_from_points("valve", points, dict(meta))


def motion_spline_candidates(*, max_lift: float, open_angle_deg: float, close_angle_deg: float,
                             phase_deg: float = 0.0, samples_per_degree: float = 2.0,
                             max_acceleration: float | None = None,
                             max_jerk: float | None = None) -> list[MotionCurve]:
    values = (max_lift, open_angle_deg, close_angle_deg, phase_deg, samples_per_degree)
    if not all(math.isfinite(v) for v in values) or min(max_lift, open_angle_deg, close_angle_deg) <= 0:
        raise CamSynthesisError("cam_motion_input", "motion spline requires finite positive lift and flank durations")
    if not 0.0 < samples_per_degree <= 10.0 or open_angle_deg + close_angle_deg > 360.0:
        raise CamSynthesisError("cam_motion_input", "invalid motion spline sampling or event duration")
    if any(v is not None and (not math.isfinite(v) or v <= 0) for v in (max_acceleration, max_jerk)):
        raise CamSynthesisError("cam_motion_input", "motion derivative limits must be finite and positive")
    opening_beta, closing_beta = math.radians(open_angle_deg), math.radians(close_angle_deg)
    scale = min(opening_beta, closing_beta)**3
    if scale == 0.0 or not math.isfinite(max_lift / scale):
        raise CamSynthesisError("cam_motion_input", "motion spline lift/duration scaling exceeds finite arithmetic")
    phase = math.radians(phase_deg)
    curves = []
    for nose_factor in _NOSE_FACTORS:
        nose_a = -nose_factor * max_lift / max(opening_beta, closing_beta)**2
        for rise in _RISE_PULSES:
            for brake in _BRAKE_PULSES:
                opening = _flank(opening_beta, max_lift, nose_a, rise, brake)
                closing = opening if opening_beta == closing_beta else _flank(closing_beta, max_lift, nose_a, rise, brake)
                if opening is None or closing is None:
                    continue
                spans = (*opening, *closing)
                acceleration = max(max(abs(s.acceleration), abs(s.state(s.length)[2])) for s in spans)
                jerk = max(abs(s.jerk) for s in spans)
                if not math.isfinite(acceleration) or not math.isfinite(jerk):
                    continue
                if ((max_acceleration is not None and acceleration > max_acceleration * (1 + 1e-9)) or
                        (max_jerk is not None and jerk > max_jerk * (1 + 1e-9))):
                    continue
                points = [(phase + t, h, v, a, j) for t, h, v, a, j in _sample(opening, samples_per_degree)]
                points += [(phase + opening_beta + closing_beta - t, h, -v, a, -j)
                           for t, h, v, a, j in reversed(_sample(closing, samples_per_degree)[:-1])]
                meta = {"law": "motion_spline", "max_lift": max_lift,
                    "knot_fractions": list(_KNOTS),
                    "open_angle": open_angle_deg, "close_angle": close_angle_deg, "dwell_angle": 0.0,
                    "event_angle": open_angle_deg + close_angle_deg, "phase_deg": phase_deg,
                    "candidate_id": f"n{nose_factor:g}-r{rise[0]}{rise[1]}-b{brake[0]}{brake[1]}",
                    "nose_acceleration_mm_per_rad2": nose_a,
                    "peak_event_acceleration_mm_per_rad2": acceleration,
                    "peak_event_jerk_mm_per_rad3": jerk,
                    "opening_peak_contact_offset_mm": max(s.velocity_range()[1] for s in opening),
                    "closing_peak_contact_offset_mm": max(s.velocity_range()[1] for s in closing),
                    "opening_acceleration_controls": [opening[0].acceleration, *[s.state(s.length)[2] for s in opening]],
                    "closing_acceleration_controls": [closing[0].acceleration, *[s.state(s.length)[2] for s in closing]],
                    "junctions": [points[0][0], points[-1][0]],
                    "synthesis_status": "bounded_motion_candidate"}
                curves.append(curve_from_points("valve", points, meta))
    if not curves:
        raise CamSynthesisError("cam_motion_no_kinematic_solution",
            "no monotone C2 motion spline in the bounded family meets the supplied derivative limits")
    return sorted(curves, key=lambda c: (c.meta["peak_event_jerk_mm_per_rad3"],
                                       c.meta["peak_event_acceleration_mm_per_rad2"], c.meta["candidate_id"]))
