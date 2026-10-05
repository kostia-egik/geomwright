from __future__ import annotations

import math
from dataclasses import dataclass

MAX_SAMPLES_PER_DEGREE = 10.0

class LiftLaw:
    name: str = ""

    def derivative(self, t: float, order: int) -> float:
        raise NotImplementedError


class PolynomialLaw(LiftLaw):
    def __init__(self, name: str, terms: tuple[tuple[float, int], ...]) -> None:
        self.name = name
        self._terms = terms

    def derivative(self, t: float, order: int) -> float:
        if order < 0:
            raise ValueError("derivative order must be non-negative")
        total = 0.0
        for coefficient, exponent in self._terms:
            if exponent < order:
                continue
            factor = 1.0
            for step in range(order):
                factor *= exponent - step
            total += coefficient * factor * (t ** (exponent - order))
        return total


class CycloidalLaw(LiftLaw):
    name = "cycloidal"

    def derivative(self, t: float, order: int) -> float:
        two_pi = 2.0 * math.pi
        if order == 0:
            return t - math.sin(two_pi * t) / two_pi
        if order == 1:
            return 1.0 - math.cos(two_pi * t)
        if order == 2:
            return two_pi * math.sin(two_pi * t)
        if order == 3:
            return two_pi * two_pi * math.cos(two_pi * t)
        raise ValueError("cycloidal law supports derivative orders 0..3")


LAW_FACTORIES: dict[str, tuple[LiftLaw, int]] = {
    "polydyne_345": (PolynomialLaw("polydyne_345", ((10.0, 3), (-15.0, 4), (6.0, 5))), 2),
    "polydyne_4567": (
        PolynomialLaw("polydyne_4567", ((35.0, 4), (-84.0, 5), (70.0, 6), (-20.0, 7))),
        3,
    ),
    "polydyne_56789": (
        PolynomialLaw(
            "polydyne_56789",
            ((126.0, 5), (-420.0, 6), (540.0, 7), (-315.0, 8), (70.0, 9)),
        ),
        3,
    ),
    "cycloidal": (CycloidalLaw(), 2),
}
LAW_NAMES = (*LAW_FACTORIES, "curvature_spline", "motion_spline", "bounded_auto")


def get_law(name: str) -> tuple[LiftLaw, int]:
    if name in ("motion_spline", "bounded_auto"):
        raise ValueError(f"{name} requires contextual synthesis, not a normalized lift factory")
    if name == "curvature_spline":
        raise ValueError("curvature_spline is contact-aware; use build_lift_curve with base_radius")
    try:
        return LAW_FACTORIES[name]
    except KeyError as exc:
        raise ValueError(f"unknown lift law: {name!r}") from exc


@dataclass(frozen=True)
class MotionCurve:
    role: str
    theta_rad: tuple[float, ...]
    theta_deg: tuple[float, ...]
    lift: tuple[float, ...]
    velocity: tuple[float, ...]
    acceleration: tuple[float, ...]
    jerk: tuple[float, ...]
    meta: dict

    @property
    def max_lift(self) -> float:
        return max(self.lift) if self.lift else 0.0


def curve_from_points(role: str, points: list[tuple[float, float, float, float, float]], meta: dict) -> MotionCurve:
    theta = tuple(point[0] for point in points)
    return MotionCurve(
        role=role,
        theta_rad=theta,
        theta_deg=tuple(math.degrees(value) for value in theta),
        lift=tuple(point[1] for point in points),
        velocity=tuple(point[2] for point in points),
        acceleration=tuple(point[3] for point in points),
        jerk=tuple(point[4] for point in points),
        meta=meta,
    )


def _linspace(count: int, start: float, end: float) -> list[float]:
    if count <= 1:
        return [start]
    step = (end - start) / (count - 1)
    return [start + step * index for index in range(count)]


def build_lift_curve(
    *,
    law: str,
    max_lift: float,
    open_angle_deg: float,
    dwell_angle_deg: float,
    close_angle_deg: float,
    phase_deg: float = 0.0,
    samples_per_degree: float = 2.0,
    base_radius: float | None = None,
    lash: float = 0.0,
    min_curvature_radius: float = 1.0,
    nose_radius: float | None = None,
    max_acceleration: float | None = None,
    max_jerk: float | None = None,
) -> MotionCurve:
    if not all(math.isfinite(value) for value in (max_lift, open_angle_deg,
               dwell_angle_deg, close_angle_deg, phase_deg, samples_per_degree)):
        raise ValueError("motion parameters must be finite")
    if max_lift <= 0.0:
        raise ValueError("max_lift must be positive")
    if open_angle_deg <= 0.0 or close_angle_deg <= 0.0:
        raise ValueError("open_angle_deg and close_angle_deg must be positive")
    if dwell_angle_deg < 0.0:
        raise ValueError("dwell_angle_deg must be non-negative")
    if not 0.0 < samples_per_degree <= MAX_SAMPLES_PER_DEGREE:
        raise ValueError("samples_per_degree must be positive and at most 10")
    if open_angle_deg + dwell_angle_deg + close_angle_deg > 360.0:
        raise ValueError("motion event must not exceed 360 cam degrees")
    if law == "motion_spline":
        from .motion_spline import motion_spline_candidates
        from .errors import CamSynthesisError

        if dwell_angle_deg != 0.0:
            raise CamSynthesisError("cam_motion_requires_event", "motion spline does not support nose dwell")
        return motion_spline_candidates(max_lift=max_lift, open_angle_deg=open_angle_deg,
            close_angle_deg=close_angle_deg, phase_deg=phase_deg,
            samples_per_degree=samples_per_degree, max_acceleration=max_acceleration,
            max_jerk=max_jerk)[0]
    if law == "curvature_spline":
        from .curvature import build_curvature_lift_curve

        if base_radius is None:
            raise ValueError("curvature_spline requires base_radius")
        if dwell_angle_deg != 0.0:
            raise ValueError("curvature_spline does not support a nose dwell")
        return build_curvature_lift_curve(base_radius=base_radius, max_lift=max_lift,
            open_angle_deg=open_angle_deg, close_angle_deg=close_angle_deg, lash=lash,
            phase_deg=phase_deg, min_curvature_radius=min_curvature_radius,
            nose_radius=nose_radius, max_acceleration=max_acceleration,
            max_jerk=max_jerk, samples_per_degree=samples_per_degree)
    generator, _ = get_law(law)

    # Exact extrema of the standard laws, independent of preview sampling.
    if law == "cycloidal":
        unit_acceleration, unit_jerk = 2.0 * math.pi, 4.0 * math.pi**2
    else:
        n = {"polydyne_345": 3, "polydyne_4567": 4, "polydyne_56789": 5}[law]
        t_peak = (1.0 - 1.0 / math.sqrt(2 * n - 3)) / 2.0
        unit_acceleration = abs(generator.derivative(t_peak, 2))
        unit_jerk = {3: 60.0, 4: 52.5, 5: 78.75}[n]

    phase = math.radians(phase_deg)
    points: list[tuple[float, float, float, float, float]] = []

    def push(theta_value: float, s: float, v: float, a: float, j: float) -> None:
        points.append((phase + theta_value, s, v, a, j))

    beta_open = math.radians(open_angle_deg)
    count_open = max(2, int(round(open_angle_deg * samples_per_degree)) + 1)
    for theta_value in _linspace(count_open, 0.0, beta_open):
        t = theta_value / beta_open
        push(
            theta_value,
            max_lift * generator.derivative(t, 0),
            max_lift / beta_open * generator.derivative(t, 1),
            max_lift / beta_open**2 * generator.derivative(t, 2),
            max_lift / beta_open**3 * generator.derivative(t, 3),
        )

    if dwell_angle_deg > 0.0:
        beta_dwell = math.radians(dwell_angle_deg)
        count_dwell = max(2, int(round(dwell_angle_deg * samples_per_degree)) + 1)
        dwell_start = beta_open
        for theta_value in _linspace(count_dwell, dwell_start, dwell_start + beta_dwell)[1:]:
            push(theta_value, max_lift, 0.0, 0.0, 0.0)

    beta_close = math.radians(close_angle_deg)
    close_start = beta_open + math.radians(dwell_angle_deg)
    count_close = max(2, int(round(close_angle_deg * samples_per_degree)) + 1)
    for theta_value in _linspace(count_close, 0.0, beta_close)[1:]:
        t = theta_value / beta_close
        push(
            close_start + theta_value,
            max_lift * (1.0 - generator.derivative(t, 0)),
            -max_lift / beta_close * generator.derivative(t, 1),
            -max_lift / beta_close**2 * generator.derivative(t, 2),
            -max_lift / beta_close**3 * generator.derivative(t, 3),
        )

    meta = {
        "law": law,
        "peak_event_acceleration_mm_per_rad2": max_lift * unit_acceleration / min(beta_open, beta_close)**2,
        "peak_event_jerk_mm_per_rad3": max_lift * unit_jerk / min(beta_open, beta_close)**3,
        "opening_peak_contact_offset_mm": max_lift * generator.derivative(0.5, 1) / beta_open,
        "closing_peak_contact_offset_mm": max_lift * generator.derivative(0.5, 1) / beta_close,
        "max_lift": max_lift,
        "open_angle": open_angle_deg,
        "dwell_angle": dwell_angle_deg,
        "close_angle": close_angle_deg,
        "phase_deg": phase_deg,
        "event_angle": open_angle_deg + dwell_angle_deg + close_angle_deg,
        "junctions": [points[0][0], points[-1][0]],
    }
    return curve_from_points("valve", points, meta)
