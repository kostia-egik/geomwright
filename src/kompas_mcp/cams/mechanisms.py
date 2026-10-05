from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import CamContactError
from .lift import MotionCurve, curve_from_points

RAMP_PROFILES = ("smooth", "smooth_c2", "constant_velocity", "constant_acceleration")


def _ramp_up_points(
    theta0: float, gamma: float, clearance: float, count: int, profile: str
) -> list[tuple[float, float, float, float, float]]:
    points: list[tuple[float, float, float, float, float]] = []
    for index in range(count):
        t = index / (count - 1)
        theta = theta0 + gamma * t
        if profile == "constant_velocity":
            points.append((theta, clearance * t, clearance / gamma, 0.0, 0.0))
        elif profile == "constant_acceleration":
            points.append(
                (
                    theta,
                    clearance * t**2,
                    2.0 * clearance * t / gamma,
                    2.0 * clearance / gamma**2,
                    0.0,
                )
            )
        elif profile == "smooth_c2":
            points.append((theta,
                clearance * (10*t**3 - 15*t**4 + 6*t**5),
                clearance * (30*t**2 - 60*t**3 + 30*t**4) / gamma,
                clearance * (60*t - 180*t**2 + 120*t**3) / gamma**2,
                clearance * (60 - 360*t + 360*t**2) / gamma**3))
        else:
            points.append(
                (
                    theta,
                    clearance * (3.0 * t**2 - 2.0 * t**3),
                    clearance * (6.0 * t - 6.0 * t**2) / gamma,
                    clearance * (6.0 - 12.0 * t) / gamma**2,
                    -12.0 * clearance / gamma**3,
                )
            )
    return points


def _ramp_down_points(
    theta0: float, gamma: float, clearance: float, count: int, profile: str
) -> list[tuple[float, float, float, float, float]]:
    if profile == "smooth_c2":
        return [(theta, clearance - s, -v, -a, -j)
                for theta, s, v, a, j in _ramp_up_points(theta0, gamma, clearance, count, profile)]
    points: list[tuple[float, float, float, float, float]] = []
    for index in range(count):
        t = index / (count - 1)
        theta = theta0 + gamma * t
        if profile == "constant_velocity":
            points.append((theta, clearance * (1.0 - t), -clearance / gamma, 0.0, 0.0))
        elif profile == "constant_acceleration":
            points.append(
                (
                    theta,
                    clearance * (1.0 - t) ** 2,
                    -2.0 * clearance * (1.0 - t) / gamma,
                    2.0 * clearance / gamma**2,
                    0.0,
                )
            )
        else:
            points.append(
                (
                    theta,
                    clearance * (1.0 - (3.0 * t**2 - 2.0 * t**3)),
                    -clearance * (6.0 * t - 6.0 * t**2) / gamma,
                    -clearance * (6.0 - 12.0 * t) / gamma**2,
                    12.0 * clearance / gamma**3,
                )
            )
    return points


def apply_clearance(
    valve: MotionCurve,
    *,
    lash: float,
    ramp_open_deg: float,
    ramp_close_deg: float,
    ramp_profile: str,
    samples_per_degree: float,
) -> MotionCurve:
    clearance = lash
    event = list(
        zip(
            valve.theta_rad,
            valve.lift,
            valve.velocity,
            valve.acceleration,
            valve.jerk,
        )
    )
    meta = {
        "lash": clearance,
        "ramp_open_deg": ramp_open_deg,
        "ramp_close_deg": ramp_close_deg,
        "ramp_profile": ramp_profile,
        "valve_meta": dict(valve.meta),
        "junctions": [valve.theta_rad[0], valve.theta_rad[-1]],
    }
    if clearance <= 0.0:
        meta["junction_velocity_jump"] = 0.0
        meta["junction_acceleration_jump"] = 0.0
        return curve_from_points("follower", list(event), meta)

    if ramp_open_deg <= 0.0 or ramp_close_deg <= 0.0:
        raise ValueError("positive ramp angles are required when lash is positive")
    if ramp_profile not in RAMP_PROFILES:
        raise ValueError(f"ramp_profile must be one of {RAMP_PROFILES}")

    start = valve.theta_rad[0]
    end = valve.theta_rad[-1]
    gamma_open = math.radians(ramp_open_deg)
    gamma_close = math.radians(ramp_close_deg)
    if ramp_profile == "constant_velocity":
        v_up, a_up = clearance / gamma_open, 0.0
        v_down, a_down = -clearance / gamma_close, 0.0
    elif ramp_profile == "constant_acceleration":
        v_up, a_up = 2.0 * clearance / gamma_open, 2.0 * clearance / gamma_open**2
        v_down, a_down = -2.0 * clearance / gamma_close, 2.0 * clearance / gamma_close**2
    elif ramp_profile == "smooth_c2":
        v_up, a_up, v_down, a_down = 0.0, 0.0, 0.0, 0.0
    else:
        v_up, a_up = 0.0, -6.0 * clearance / gamma_open**2
        v_down, a_down = 0.0, -6.0 * clearance / gamma_close**2
    meta["junction_velocity_jump"] = max(abs(v_up), abs(v_down))
    meta["junction_acceleration_jump"] = max(abs(a_up), abs(a_down))
    count_open = max(2, int(round(ramp_open_deg * samples_per_degree)) + 1)
    count_close = max(2, int(round(ramp_close_deg * samples_per_degree)) + 1)
    ramp_open = _ramp_up_points(start - gamma_open, gamma_open, clearance, count_open, ramp_profile)
    ramp_close = _ramp_down_points(end, gamma_close, clearance, count_close, ramp_profile)
    flank = [(theta, s + clearance, v, a, j) for theta, s, v, a, j in event]
    return curve_from_points("follower", ramp_open + flank[1:] + ramp_close[1:], meta)


class Mechanism:
    kind: str = ""


class DirectMechanism(Mechanism):
    kind = "direct"

    def __init__(
        self,
        *,
        lash: float = 0.0,
        ramp_open_deg: float = 0.0,
        ramp_close_deg: float = 0.0,
        ramp_profile: str = "smooth",
    ) -> None:
        self.lash = lash
        self.ramp_open_deg = ramp_open_deg
        self.ramp_close_deg = ramp_close_deg
        self.ramp_profile = ramp_profile

    @property
    def ratio(self) -> float:
        return 1.0

    def follower_from_valve(self, valve: MotionCurve, *, samples_per_degree: float = 2.0) -> MotionCurve:
        return apply_clearance(
            valve,
            lash=self.lash,
            ramp_open_deg=self.ramp_open_deg,
            ramp_close_deg=self.ramp_close_deg,
            ramp_profile=self.ramp_profile,
            samples_per_degree=samples_per_degree,
        )

    def valve_from_follower(self, follower: MotionCurve) -> MotionCurve:
        clearance = self.lash
        points: list[tuple[float, float, float, float, float]] = []
        for theta, s, v, a, j in zip(
            follower.theta_rad,
            follower.lift,
            follower.velocity,
            follower.acceleration,
            follower.jerk,
        ):
            if s > clearance:
                points.append((theta, s - clearance, v, a, j))
            else:
                points.append((theta, 0.0, 0.0, 0.0, 0.0))
        return curve_from_points("valve", points, {"mechanism": self.kind, "lash": clearance})


@dataclass(frozen=True)
class PitchCurve:
    role: str
    theta_rad: tuple[float, ...]
    theta_deg: tuple[float, ...]
    lift: tuple[float, ...]
    velocity: tuple[float, ...]
    center_x: tuple[float, ...]
    center_y: tuple[float, ...]
    normal_x: tuple[float, ...]
    normal_y: tuple[float, ...]
    flow_x: tuple[float, ...]
    flow_y: tuple[float, ...]
    arm_angle_deg: tuple[float, ...]
    valve_contact_x: tuple[float, ...]
    valve_ratio: tuple[float, ...]
    valve_lift: tuple[float, ...]
    pad_contact_angle_deg: tuple[float, ...]
    pivot_x: float
    pivot_y: float
    meta: dict


class RockerMechanism(Mechanism):
    kind = "rocker"

    def __init__(
        self,
        *,
        roller_arm: float,
        roller_angle_deg: float,
        valve_arm: float,
        valve_angle_deg: float,
        valve_axis_deg: float = 90.0,
        valve_pad_radius: float = 0.0,
        lash: float = 0.0,
        ramp_open_deg: float = 0.0,
        ramp_close_deg: float = 0.0,
        ramp_profile: str = "smooth",
    ) -> None:
        self.roller_arm = roller_arm
        self.roller_angle_deg = roller_angle_deg
        self.valve_arm = valve_arm
        self.valve_angle_deg = valve_angle_deg
        self.valve_axis_deg = valve_axis_deg
        self.valve_pad_radius = valve_pad_radius
        self.lash = lash
        self.ramp_open_deg = ramp_open_deg
        self.ramp_close_deg = ramp_close_deg
        self.ramp_profile = ramp_profile

    def pitch_curve(
        self,
        valve: MotionCurve,
        *,
        base_radius: float,
        roller_radius: float,
        samples_per_degree: float = 2.0,
    ) -> PitchCurve:
        pad = apply_clearance(
            valve,
            lash=self.lash,
            ramp_open_deg=self.ramp_open_deg,
            ramp_close_deg=self.ramp_close_deg,
            ramp_profile=self.ramp_profile,
            samples_per_degree=samples_per_degree,
        )
        return self.pitch_curve_from_pad(
            pad, base_radius=base_radius, roller_radius=roller_radius
        )

    def pitch_curve_from_pad(
        self,
        pad: MotionCurve,
        *,
        base_radius: float,
        roller_radius: float,
    ) -> PitchCurve:
        if self.roller_arm <= 0.0 or self.valve_arm <= 0.0:
            raise ValueError("rocker arm lengths must be positive")
        psi0 = math.radians(self.roller_angle_deg)
        phi0 = math.radians(self.valve_angle_deg)
        axis = math.radians(self.valve_axis_deg)
        delta0 = (phi0 - axis + math.pi) % (2.0 * math.pi) - math.pi
        rest_projection = math.cos(delta0)
        rest_radius = base_radius + roller_radius
        pivot_x = rest_radius - self.roller_arm * math.cos(psi0)
        pivot_y = -self.roller_arm * math.sin(psi0)

        theta: list[float] = []
        lift: list[float] = []
        velocity: list[float] = []
        center_x: list[float] = []
        center_y: list[float] = []
        normal_x: list[float] = []
        normal_y: list[float] = []
        flow_x: list[float] = []
        flow_y: list[float] = []
        arm_angle_deg: list[float] = []
        valve_contact_x: list[float] = []
        valve_ratio: list[float] = []
        valve_lift: list[float] = []
        pad_contact_angle_deg: list[float] = []
        for theta_value, p, dp in zip(pad.theta_rad, pad.lift, pad.velocity):
            # Fixed-radius tip sliding across a flat valve end. The projection
            # along the valve axis, not the length of the arm, changes with lift.
            cosine = rest_projection + p / self.valve_arm
            if abs(cosine) > 1.0 + 1e-12:
                raise CamContactError("cam_rocker_reach", "rocker valve lift exceeds the fixed arm reach",
                                      reach=self.valve_arm * (1.0 - rest_projection))
            delta = math.copysign(math.acos(max(-1.0, min(1.0, cosine))), delta0)
            alpha = delta - delta0
            cross = -self.valve_arm * math.sin(delta)
            if abs(cross) < 1e-9:
                if abs(dp) < 1e-12:
                    alpha_p = 0.0
                else:
                    raise CamContactError("cam_rocker_singular", "rocker geometry is singular (valve axis is tangent to the arm)",
                                          reach=self.valve_arm * (1.0 - rest_projection))
            else:
                alpha_p = dp / cross
            arm_x = math.cos(psi0 + alpha)
            arm_y = math.sin(psi0 + alpha)
            c_x = pivot_x + self.roller_arm * arm_x
            c_y = pivot_y + self.roller_arm * arm_y
            c_xp = self.roller_arm * alpha_p * (-arm_y)
            c_yp = self.roller_arm * alpha_p * arm_x
            cos_t = math.cos(theta_value)
            sin_t = math.sin(theta_value)
            p_x = cos_t * c_x - sin_t * c_y
            p_y = sin_t * c_x + cos_t * c_y
            p_xp = (-sin_t * c_x - cos_t * c_y) + (cos_t * c_xp - sin_t * c_yp)
            p_yp = (cos_t * c_x - sin_t * c_y) + (sin_t * c_xp + cos_t * c_yp)
            denom = math.hypot(p_xp, p_yp)
            if denom < 1e-12:
                raise CamContactError("cam_pitch_degenerate", "degenerate pitch curve")
            theta.append(theta_value)
            lift.append(p)
            velocity.append(dp)
            center_x.append(p_x)
            center_y.append(p_y)
            normal_x.append(p_yp / denom)
            normal_y.append(-p_xp / denom)
            flow_x.append(cos_t * c_xp - sin_t * c_yp)
            flow_y.append(sin_t * c_xp + cos_t * c_yp)
            arm_angle_deg.append(math.degrees(alpha))
            valve_contact_x.append(pivot_x + self.valve_arm * math.cos(phi0 + alpha))
            valve_ratio.append(cross)
            valve_lift.append(p)
            pad_contact_angle_deg.append(-90.0 - math.degrees(phi0 + alpha))
        meta = {
            "mechanism": self.kind,
            "roller_arm": self.roller_arm,
            "roller_angle_deg": self.roller_angle_deg,
            "valve_arm": self.valve_arm,
            "valve_angle_deg": self.valve_angle_deg,
            "valve_axis_deg": self.valve_axis_deg,
            "valve_pad_radius": self.valve_pad_radius,
            "lash": self.lash,
            "ramp_profile": self.ramp_profile,
            "pivot": (pivot_x, pivot_y),
            "junctions": pad.meta.get("junctions", []),
            "junction_velocity_jump": pad.meta.get("junction_velocity_jump", 0.0),
            "junction_acceleration_jump": pad.meta.get("junction_acceleration_jump", 0.0),
        }
        return PitchCurve(
            role="follower",
            theta_rad=tuple(theta),
            theta_deg=tuple(math.degrees(value) for value in theta),
            lift=tuple(lift),
            velocity=tuple(velocity),
            center_x=tuple(center_x),
            center_y=tuple(center_y),
            normal_x=tuple(normal_x),
            normal_y=tuple(normal_y),
            flow_x=tuple(flow_x),
            flow_y=tuple(flow_y),
            arm_angle_deg=tuple(arm_angle_deg),
            valve_contact_x=tuple(valve_contact_x),
            valve_ratio=tuple(valve_ratio),
            valve_lift=tuple(valve_lift),
            pad_contact_angle_deg=tuple(pad_contact_angle_deg),
            pivot_x=pivot_x,
            pivot_y=pivot_y,
            meta=meta,
        )


def build_mechanism(mechanism: str, **kwargs: object) -> Mechanism:
    if mechanism == "direct":
        return DirectMechanism(
            lash=float(kwargs.get("lash", 0.0)),
            ramp_open_deg=float(kwargs.get("ramp_open_deg", 0.0)),
            ramp_close_deg=float(kwargs.get("ramp_close_deg", 0.0)),
            ramp_profile=str(kwargs.get("ramp_profile", "smooth")),
        )
    if mechanism == "rocker":
        return RockerMechanism(
            roller_arm=float(kwargs.get("roller_arm", 0.0)),
            roller_angle_deg=float(kwargs.get("roller_angle_deg", 0.0)),
            valve_arm=float(kwargs.get("valve_arm", 0.0)),
            valve_angle_deg=float(kwargs.get("valve_angle_deg", 0.0)),
            valve_axis_deg=float(kwargs.get("valve_axis_deg", 90.0)),
            valve_pad_radius=float(kwargs.get("valve_pad_radius", 0.0)),
            lash=float(kwargs.get("lash", 0.0)),
            ramp_open_deg=float(kwargs.get("ramp_open_deg", 0.0)),
            ramp_close_deg=float(kwargs.get("ramp_close_deg", 0.0)),
            ramp_profile=str(kwargs.get("ramp_profile", "smooth")),
        )
    raise ValueError(f"unknown mechanism: {mechanism!r}")
