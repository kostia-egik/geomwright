from __future__ import annotations

import math
from typing import Any

from .lift import LAW_NAMES, MAX_SAMPLES_PER_DEGREE, get_law
from .mechanisms import RAMP_PROFILES
from .timing import event_from_crank
from .curvature import CurvatureSynthesisError

CONTACT_TYPES = ("flat", "roller")
MECHANISM_TYPES = ("direct", "rocker")


def _finite(name: str, value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def normalize_cam_request(payload: dict[str, Any]) -> dict[str, Any]:
    law = str(payload.get("law", "") or "").strip().lower()
    if law not in LAW_NAMES:
        raise ValueError(f"law must be one of {LAW_NAMES}")

    base_radius = _finite("base_radius", payload.get("base_radius"))
    if base_radius <= 0.0:
        raise ValueError("base_radius must be positive")
    max_lift = _finite("max_lift", payload.get("max_lift"))
    if max_lift <= 0.0:
        raise ValueError("max_lift must be positive")

    timing = payload.get("timing")
    if timing is not None:
        if not isinstance(timing, dict):
            raise ValueError("timing must be an object")
        nose_center = timing.get("nose_center_deg")
        event = event_from_crank(
            open_deg=_finite("timing.open_deg", timing.get("open_deg")),
            close_deg=_finite("timing.close_deg", timing.get("close_deg")),
            dwell_deg=_finite("timing.dwell_deg", timing.get("dwell_deg", 0.0)),
            nose_center_deg=(
                None if nose_center is None else _finite("timing.nose_center_deg", nose_center)
            ),
            cam_reference_deg=_finite(
                "timing.cam_reference_deg", timing.get("cam_reference_deg", 0.0)
            ),
        )
        open_angle = event.open_angle
        dwell_angle = event.dwell_angle
        close_angle = event.close_angle
        phase_deg = event.phase_deg
    else:
        open_angle = _finite("open_angle", payload.get("open_angle"))
        close_angle = _finite("close_angle", payload.get("close_angle"))
        dwell_angle = _finite("dwell_angle", payload.get("dwell_angle", 0.0))
        phase_deg = _finite("phase_deg", payload.get("phase_deg", 0.0))

    if open_angle <= 0.0 or close_angle <= 0.0:
        raise ValueError("open_angle and close_angle must be positive")
    if dwell_angle < 0.0:
        raise ValueError("dwell_angle must be non-negative")
    if open_angle + dwell_angle + close_angle > 360.0:
        raise ValueError("valve event angles must not exceed 360")

    mechanism = str(payload.get("mechanism", "direct") or "direct").strip().lower()
    if mechanism not in MECHANISM_TYPES:
        raise ValueError(f"mechanism must be one of {MECHANISM_TYPES}")

    drive = str(payload.get("drive", "valve") or "valve").strip().lower()
    if drive not in ("valve", "cam"):
        raise ValueError("drive must be 'valve' or 'cam'")

    lash = _finite("lash", payload.get("lash", 0.0))
    if lash < 0.0:
        raise ValueError("lash must be non-negative")
    default_ramp = "smooth_c2" if law in ("curvature_spline", "motion_spline", "bounded_auto") else "smooth"
    ramp_profile = str(payload.get("ramp_profile", default_ramp) or default_ramp).strip().lower()
    if ramp_profile not in RAMP_PROFILES:
        raise ValueError(f"ramp_profile must be one of {RAMP_PROFILES}")
    ramp_open_deg = _finite("ramp_open_deg", payload.get("ramp_open_deg", 0.0))
    ramp_close_deg = _finite("ramp_close_deg", payload.get("ramp_close_deg", 0.0))
    if ramp_open_deg < 0.0 or ramp_close_deg < 0.0:
        raise ValueError("ramp angles must be non-negative")
    if lash > 0.0 and drive == "valve":
        if ramp_open_deg <= 0.0 or ramp_close_deg <= 0.0:
            raise CurvatureSynthesisError("cam_ramps_required", "positive ramp angles are required when lash is positive")
    else:
        ramp_open_deg = 0.0
        ramp_close_deg = 0.0

    total_angle = open_angle + dwell_angle + close_angle + ramp_open_deg + ramp_close_deg
    if total_angle > 360.0:
        raise CurvatureSynthesisError("cam_event_budget", "valve event plus ramps must not exceed 360")

    samples_per_degree = _finite("samples_per_degree", payload.get("samples_per_degree", 2.0))
    if not 0.0 < samples_per_degree <= MAX_SAMPLES_PER_DEGREE:
        raise ValueError("samples_per_degree must be positive and at most 10")

    contact = str(payload.get("contact", "flat") or "flat").strip().lower()
    if contact not in CONTACT_TYPES:
        raise ValueError(f"contact must be one of {CONTACT_TYPES}")

    roller_radius = _finite("roller_radius", payload.get("roller_radius", 0.0))
    offset = _finite("offset", payload.get("offset", 0.0))

    roller_arm = _finite("roller_arm", payload.get("roller_arm", 0.0))
    roller_angle_deg = _finite("roller_angle_deg", payload.get("roller_angle_deg", 0.0))
    valve_arm = _finite("valve_arm", payload.get("valve_arm", 0.0))
    valve_angle_deg = _finite("valve_angle_deg", payload.get("valve_angle_deg", 0.0))
    valve_axis_deg = _finite("valve_axis_deg", payload.get("valve_axis_deg", 90.0))
    valve_pad_radius = _finite("valve_pad_radius", payload.get("valve_pad_radius", 0.0))
    if valve_pad_radius < 0.0:
        raise ValueError("valve_pad_radius must be non-negative")

    if mechanism == "rocker":
        if contact != "roller":
            raise ValueError("rocker mechanism requires contact='roller'")
        if abs(offset) > 1e-12:
            raise ValueError("rocker mechanism does not support follower offset")
        if roller_arm <= 0.0 or valve_arm <= 0.0:
            raise ValueError("rocker arm lengths must be positive")
        reach = valve_arm * (1.0 - math.cos(math.radians(valve_angle_deg - valve_axis_deg)))
        if max_lift + lash > reach + 1e-9:
            raise CurvatureSynthesisError("cam_rocker_reach", "valve_arm is too short for max_lift + lash at given valve_angle", reach=reach)
        if reach - (max_lift + lash) <= 1e-9:
            raise CurvatureSynthesisError("cam_rocker_singular", "rocker reaches the valve-axis projection singularity at peak lift", reach=reach)
        if roller_radius <= 0.0:
            raise ValueError("roller_radius must be positive for a roller contact")
    else:
        if contact == "roller":
            if roller_radius <= 0.0:
                raise ValueError("roller_radius must be positive for a roller contact")
            if abs(offset) >= base_radius + roller_radius:
                raise ValueError("abs(offset) must be less than base_radius + roller_radius")
        else:
            roller_radius = 0.0
        roller_arm = 0.0
        roller_angle_deg = 0.0
        valve_arm = 0.0
        valve_angle_deg = 0.0
        valve_axis_deg = 90.0

    pressure_angle_limit = _finite(
        "pressure_angle_limit_deg", payload.get("pressure_angle_limit_deg", 30.0)
    )
    if pressure_angle_limit <= 0.0:
        raise ValueError("pressure_angle_limit_deg must be positive")

    min_curvature_radius = _finite("min_curvature_radius", payload.get("min_curvature_radius", 1.0))
    nose_radius = payload.get("nose_radius")
    nose_radius = None if nose_radius is None else _finite("nose_radius", nose_radius)
    tappet_diameter = payload.get("tappet_diameter")
    tappet_diameter = None if tappet_diameter is None else _finite("tappet_diameter", tappet_diameter)
    edge_margin = _finite("tappet_edge_margin", payload.get("tappet_edge_margin", 0.5))
    max_acceleration = payload.get("max_acceleration")
    max_acceleration = None if max_acceleration is None else _finite("max_acceleration", max_acceleration)
    max_jerk = payload.get("max_jerk")
    max_jerk = None if max_jerk is None else _finite("max_jerk", max_jerk)
    if any(value is not None and value <= 0.0 for value in (max_acceleration, max_jerk)):
        raise ValueError("acceleration and jerk limits must be positive")
    if min_curvature_radius <= 0.0 or edge_margin < 0.0:
        raise ValueError("minimum curvature radius must be positive and tappet edge margin non-negative")
    if tappet_diameter is not None and tappet_diameter <= 2.0 * edge_margin:
        raise CurvatureSynthesisError("cam_tappet_size", "tappet_diameter must exceed twice tappet_edge_margin")
    if law == "curvature_spline":
        if mechanism != "direct" or contact != "flat" or drive != "valve" or dwell_angle != 0.0:
            raise CurvatureSynthesisError("cam_curvature_requires_flat",
                "curvature_spline requires a valve-driven direct flat tappet without nose dwell")
    if law == "bounded_auto" and drive != "valve":
        raise CurvatureSynthesisError("cam_auto_requires_valve", "automatic law selection requires valve-driven motion")
    if law == "motion_spline" and (drive != "valve" or dwell_angle != 0.0):
        raise CurvatureSynthesisError("cam_motion_requires_event", "motion spline requires valve-driven motion without nose dwell")

    return {
        "law": law,
        "law_continuity_order": 2 if law in ("curvature_spline", "motion_spline", "bounded_auto") else get_law(law)[1],
        "base_radius": base_radius,
        "max_lift": max_lift,
        "open_angle": open_angle,
        "dwell_angle": dwell_angle,
        "close_angle": close_angle,
        "phase_deg": phase_deg,
        "contact": contact,
        "roller_radius": roller_radius,
        "offset": offset,
        "mechanism": mechanism,
        "drive": drive,
        "lash": lash,
        "ramp_open_deg": ramp_open_deg,
        "ramp_close_deg": ramp_close_deg,
        "ramp_profile": ramp_profile,
        "roller_arm": roller_arm,
        "roller_angle_deg": roller_angle_deg,
        "valve_arm": valve_arm,
        "valve_angle_deg": valve_angle_deg,
        "valve_axis_deg": valve_axis_deg,
        "valve_pad_radius": valve_pad_radius,
        "samples_per_degree": samples_per_degree,
        "pressure_angle_limit_deg": pressure_angle_limit,
        "min_curvature_radius": min_curvature_radius,
        "nose_radius": nose_radius,
        "tappet_diameter": tappet_diameter,
        "tappet_edge_margin": edge_margin,
        "max_acceleration": max_acceleration,
        "max_jerk": max_jerk,
    }
