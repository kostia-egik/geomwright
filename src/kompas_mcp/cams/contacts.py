from __future__ import annotations

import math
from dataclasses import dataclass

from .lift import MotionCurve
from .mechanisms import PitchCurve
from .motion import TranslatingMotion


@dataclass(frozen=True)
class CamProfile:
    x: tuple[float, ...]
    y: tuple[float, ...]
    active_count: int
    base_radius: float
    contact: str
    offset: float
    roller_radius: float


def _translating_offset(motion: object) -> float:
    if not isinstance(motion, TranslatingMotion):
        raise ValueError("only translating follower motion is supported")
    return motion.offset


def _closed_with_base(
    xs: list[float],
    ys: list[float],
    base_radius: float,
    base_points: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if math.dist((xs[0], ys[0]), (xs[-1], ys[-1])) < 1e-9:
        # A full-turn event is already closed; another base turn creates a loop.
        return tuple(xs), tuple(ys)
    start_angle = math.atan2(ys[0], xs[0]) % (2.0 * math.pi)
    end_angle = math.atan2(ys[-1], xs[-1]) % (2.0 * math.pi)
    span = (start_angle - end_angle) % (2.0 * math.pi)
    if span <= 1e-12:
        span = 2.0 * math.pi
    steps = max(2, base_points)
    for index in range(1, steps + 1):
        angle = end_angle + span * index / steps
        xs.append(base_radius * math.cos(angle))
        ys.append(base_radius * math.sin(angle))
    return tuple(xs), tuple(ys)


def flat_follower_profile(
    curve: MotionCurve,
    *,
    base_radius: float,
    motion: object = TranslatingMotion(),
    base_points: int = 36,
) -> CamProfile:
    if base_radius <= 0.0:
        raise ValueError("base_radius must be positive")
    offset = _translating_offset(motion)
    # Lateral offset of a flat face does not change its infinite-plane envelope;
    # its finite face/edge reach is checked separately in preview.py.
    xs: list[float] = []
    ys: list[float] = []
    for theta, s, v in zip(curve.theta_rad, curve.lift, curve.velocity):
        radius = base_radius + s
        xs.append(radius * math.cos(theta) - v * math.sin(theta))
        ys.append(radius * math.sin(theta) + v * math.cos(theta))
    active = len(xs)
    x_closed, y_closed = _closed_with_base(xs, ys, base_radius, base_points)
    return CamProfile(
        x=x_closed,
        y=y_closed,
        active_count=active,
        base_radius=base_radius,
        contact="flat",
        offset=offset,
        roller_radius=0.0,
    )


def roller_follower_geometry(
    curve: MotionCurve,
    *,
    base_radius: float,
    roller_radius: float,
    offset: float = 0.0,
) -> tuple[list[float], list[float], list[float], list[float], list[tuple[float, float]]]:
    if base_radius <= 0.0:
        raise ValueError("base_radius must be positive")
    if roller_radius <= 0.0:
        raise ValueError("roller_radius must be positive")
    reach = base_radius + roller_radius
    if abs(offset) >= reach:
        raise ValueError("abs(offset) must be less than base_radius + roller_radius")
    center_radius = math.sqrt(reach * reach - offset * offset)
    xs: list[float] = []
    ys: list[float] = []
    centers_x: list[float] = []
    centers_y: list[float] = []
    normals: list[tuple[float, float]] = []
    for theta, s, v in zip(curve.theta_rad, curve.lift, curve.velocity):
        a = v - offset
        center_x = center_radius + s
        denom = math.hypot(center_x, a)
        pitch_x = center_x * math.cos(theta) - offset * math.sin(theta)
        pitch_y = center_x * math.sin(theta) + offset * math.cos(theta)
        tangent_x = a * math.cos(theta) - center_x * math.sin(theta)
        tangent_y = a * math.sin(theta) + center_x * math.cos(theta)
        normal_x = tangent_y / denom
        normal_y = -tangent_x / denom
        xs.append(pitch_x - roller_radius * normal_x)
        ys.append(pitch_y - roller_radius * normal_y)
        centers_x.append(pitch_x)
        centers_y.append(pitch_y)
        normals.append((normal_x, normal_y))
    return xs, ys, centers_x, centers_y, normals


def roller_from_pitch_curve(
    pitch: PitchCurve,
    *,
    base_radius: float,
    roller_radius: float,
    base_points: int = 36,
) -> CamProfile:
    if base_radius <= 0.0:
        raise ValueError("base_radius must be positive")
    if roller_radius <= 0.0:
        raise ValueError("roller_radius must be positive")
    xs = [
        center - roller_radius * normal
        for center, normal in zip(pitch.center_x, pitch.normal_x)
    ]
    ys = [
        center - roller_radius * normal
        for center, normal in zip(pitch.center_y, pitch.normal_y)
    ]
    active = len(xs)
    x_closed, y_closed = _closed_with_base(xs, ys, base_radius, base_points)
    return CamProfile(
        x=x_closed,
        y=y_closed,
        active_count=active,
        base_radius=base_radius,
        contact="roller",
        offset=0.0,
        roller_radius=roller_radius,
    )


def roller_follower_profile(
    curve: MotionCurve,
    *,
    base_radius: float,
    roller_radius: float,
    motion: object = TranslatingMotion(),
    base_points: int = 36,
) -> CamProfile:
    offset = _translating_offset(motion)
    xs, ys, _, _, _ = roller_follower_geometry(
        curve,
        base_radius=base_radius,
        roller_radius=roller_radius,
        offset=offset,
    )
    active = len(xs)
    x_closed, y_closed = _closed_with_base(xs, ys, base_radius, base_points)
    return CamProfile(
        x=x_closed,
        y=y_closed,
        active_count=active,
        base_radius=base_radius,
        contact="roller",
        offset=offset,
        roller_radius=roller_radius,
    )
