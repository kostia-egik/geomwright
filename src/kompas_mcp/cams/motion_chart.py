"""Bounded sampled S/V/A/J display contract; no numerical differentiation."""
from __future__ import annotations

import math
from typing import Any

from .lift import MotionCurve


def motion_chart_payload(spec: dict[str, Any], valve: MotionCurve,
                         command: MotionCurve, summary: dict[str, Any],
                         warnings: list[dict[str, Any]]) -> dict[str, Any]:
    origin = command.theta_deg[0]
    main_start = valve.theta_deg[0] - origin
    main_end = valve.theta_deg[-1] - origin
    nose_start = main_start + spec["open_angle"]
    nose_end = nose_start + spec["dwell_angle"]
    end = command.theta_deg[-1] - origin
    windows = []
    for key, left, right in (("ramp_open", 0.0, main_start),
                              ("rise", main_start, nose_start),
                              ("dwell", nose_start, nose_end),
                              ("fall", nose_end, main_end),
                              ("ramp_close", main_end, end)):
        if right - left > 1e-9:
            windows.append({"key": key, "from_deg": left, "to_deg": right})
    joins = {0.0, main_start, main_end, end}
    jerk_breaks = set(joins) if spec["lash"] > 0.0 else set()
    if spec["law_continuity_order"] < 3:
        jerk_breaks.update((main_start, nose_start, nose_end, main_end))
    # Cubic motion and support-function splines have finite jerk jumps at
    # internal knots. Both flanks' knot angles must be exposed, including the
    # time-reversed closing flank. Charts do not interpolate across these.
    knots = valve.meta.get("knot_fractions", [])
    for side, angle in (("opening", spec["open_angle"]), ("closing", spec["close_angle"])):
        controls = valve.meta.get(f"{side}_acceleration_controls",
                                  valve.meta.get(f"{side}_curvature_controls_mm", []))
        if len(controls) != len(knots) or len(knots) < 3:
            continue
        beta = math.radians(angle)
        slopes = [(b - a) / (beta * (right - left))
                  for a, b, left, right in zip(controls, controls[1:], knots, knots[1:])]
        for i in range(1, len(slopes)):
            if not math.isclose(slopes[i - 1], slopes[i], rel_tol=1e-9, abs_tol=1e-9):
                jerk_breaks.add(main_start + knots[i] * angle if side == "opening"
                                else main_end - knots[i] * angle)
    order = summary["continuity_order"]
    return {
        "coordinate": summary.get("derivative_coordinate", "follower_translation"),
        "theta_deg": [t - origin for t in command.theta_deg],
        "lift": list(command.lift),
        "valve_lift": [max(0.0, value - spec["lash"]) for value in command.lift],
        "velocity": list(command.velocity),
        "acceleration": list(command.acceleration),
        "jerk": list(command.jerk),
        "windows": windows,
        "breaks_deg": {"lift": [], "velocity": sorted(joins) if order < 1 else [],
                       "acceleration": sorted(joins) if order < 2 else [],
                       "jerk": sorted(jerk_breaks)},
        "limits": {"acceleration": spec["max_acceleration"], "jerk": spec["max_jerk"]},
        "limit_exceeded": {"acceleration": any(w["code"] == "cam_acceleration_limit" for w in warnings),
                           "jerk": any(w["code"] == "cam_jerk_limit" for w in warnings)},
        "peaks": {"acceleration": summary["peak_acceleration_mm_per_rad2"],
                  "jerk": summary["peak_jerk_mm_per_rad3"]},
        "continuity_order": order,
        "derivative_jumps": order < 2,
        "derivative_units": "cam_radians",
    }
