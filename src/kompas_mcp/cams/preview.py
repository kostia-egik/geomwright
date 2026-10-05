from __future__ import annotations

import math
from typing import Any

from .analyze import minimum_convex_curvature_radius, pressure_angles_from_directions, summarize
from .contacts import (
    flat_follower_profile,
    roller_follower_geometry,
    roller_follower_profile,
    roller_from_pitch_curve,
)
from .lift import MotionCurve, build_lift_curve
from .mechanisms import PitchCurve, apply_clearance, build_mechanism
from .motion import TranslatingMotion
from .spec import normalize_cam_request
from .errors import CamContactError, CamSynthesisError
from .lift import LAW_FACTORIES
from .motion_spline import MAX_MOTION_CANDIDATES, motion_spline_candidates, resample_motion_spline
from .motion_chart import motion_chart_payload


def _selection_issues(result: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    radius = result["summary"].get("min_curvature_radius")
    if radius is not None and radius < spec["min_curvature_radius"] - 1e-6 and not any(w["code"] == "cam_curvature_below_min" for w in result["warning_items"]):
        result["warning_items"].append({"code": "cam_curvature_below_min", "params": {
            "value": radius, "limit": spec["min_curvature_radius"]},
            "message": "sampled profile curvature is below the requested minimum"})
    notes = {"cam_clearance", "cam_curvature_family", "cam_curvature_unbounded"}
    return [w["code"] for w in result["warning_items"] if w["code"] not in notes]


def _motion_selection(spec: dict[str, Any]) -> dict[str, Any]:
    # A coarse requested drawing must not become the contact search grid.
    spec = {**spec, "samples_per_degree": max(2.0, spec["samples_per_degree"])}
    curves = motion_spline_candidates(max_lift=spec["max_lift"], open_angle_deg=spec["open_angle"],
        close_angle_deg=spec["close_angle"], phase_deg=spec["phase_deg"],
        samples_per_degree=spec["samples_per_degree"], max_acceleration=spec["max_acceleration"],
        max_jerk=spec["max_jerk"])
    best = None
    rejections: dict[str, int] = {}
    tested = 0
    refined = 0
    verify_density = min(10.0, 2.0 * spec["samples_per_degree"])
    for curve in curves:
        tested += 1
        try:
            result = _evaluate_curve(spec, curve)
            issues = _selection_issues(result, spec)
            if not issues and verify_density > spec["samples_per_degree"]:
                verify_spec = {**spec, "samples_per_degree": verify_density}
                curve = resample_motion_spline(curve, verify_density)
                result = _evaluate_curve(verify_spec, curve)
                issues = _selection_issues(result, verify_spec)
                refined += 1
        except CamContactError as exc:
            rejections[exc.code] = rejections.get(exc.code, 0) + 1
            continue
        for code in set(issues):
            rejections[code] = rejections.get(code, 0) + 1
        # Exact jerk/acceleration sort lets us stop at the first passing
        # contact candidate; no better candidate remains in this fixed family.
        score = (len(issues), curve.meta["peak_event_jerk_mm_per_rad3"],
                 curve.meta["peak_event_acceleration_mm_per_rad2"], curve.meta["candidate_id"])
        if best is None or score < best[0]:
            best = (score, result, curve, issues)
        if not issues:
            break
    if best is None:
        raise CamSynthesisError("cam_motion_no_contact_solution", "all motion-spline candidates have unusable contact geometry")
    _, result, curve, issues = best
    result["synthesis"] = {"family": "piecewise_linear_acceleration", "candidate_id": curve.meta["candidate_id"],
        "status": "passed_sampled_checks" if not issues else "no_passing_candidate",
        "family_budget": MAX_MOTION_CANDIDATES, "kinematic_candidate_count": len(curves),
        "contact_candidate_count": tested, "rejection_counts": rejections,
        "refined_candidate_count": refined, "geometry_verification": "sampled",
        "search_samples_per_degree": spec["samples_per_degree"],
        "samples_per_degree": result["spec"]["samples_per_degree"],
        "nose_acceleration_mm_per_rad2": curve.meta["nose_acceleration_mm_per_rad2"],
        "knot_fractions": curve.meta["knot_fractions"],
        "opening_acceleration_controls": curve.meta["opening_acceleration_controls"],
        "closing_acceleration_controls": curve.meta["closing_acceleration_controls"]}
    if issues:
        result["warning_items"].insert(0, {"code": "cam_motion_no_contact_solution", "params": {},
            "message": "No bounded motion-spline candidate passes the contact checks; the displayed candidate is not accepted."})
    if spec["max_acceleration"] is None or spec["max_jerk"] is None:
        result["warning_items"].append({"code": "cam_curvature_unbounded", "params": {},
            "message": "Acceleration or jerk limit is unspecified; bounded motion synthesis does not impose an external engineering limit."})
    result["warnings"] = [w["message"] for w in result["warning_items"]]
    return result


def _bounded_selection(spec: dict[str, Any]) -> dict[str, Any]:
    """Select, without changing dimensions or caps; geometric checks are sampled."""
    laws = list(LAW_FACTORIES)
    if spec["dwell_angle"] == 0.0:
        laws.append("motion_spline")
    if spec["mechanism"] == "direct" and spec["contact"] == "flat" and spec["drive"] == "valve" and spec["dwell_angle"] == 0.0:
        laws.append("curvature_spline")
    candidates = []
    reports = []
    for law in laws:
        try:
            result = preview_cam_profile({**spec, "law": law})
        except CamSynthesisError as exc:
            reports.append({"law": law, "issues": [exc.code]})
            continue
        issues = _selection_issues(result, spec)
        reports.append({"law": law, "issues": issues})
        # Prefer a passing candidate, then lower angular jerk. A failed best
        # candidate remains explicitly failed; never silently relax inputs.
        score = (len(issues), result["summary"]["peak_jerk_mm_per_rad3"], laws.index(law))
        candidates.append((score, result))
    if not candidates:
        raise CamSynthesisError("cam_auto_no_solution", "all available laws fail to produce usable contact geometry")
    _, result = min(candidates, key=lambda item: item[0])
    selected = next(r for r in reports if r["law"] == result["law"])
    result["selection"] = {"requested_law": "bounded_auto", "selected_law": result["law"],
        "status": "passed_sampled_checks" if not selected["issues"] else "no_passing_candidate",
        "candidates": reports, "geometry_verification": "sampled"}
    result["summary"]["selected_law"] = result["law"]
    if selected["issues"]:
        result["warning_items"].insert(0, {"code": "cam_auto_no_solution", "params": {},
            "message": "No available law passes all checks; the displayed candidate is not accepted."})
    result["warnings"] = [w["message"] for w in result["warning_items"]]
    return result


def _curve_payload(curve: MotionCurve) -> dict[str, Any]:
    return {
        "role": curve.role,
        "theta_deg": list(curve.theta_deg),
        "lift": list(curve.lift),
        "velocity": list(curve.velocity),
        "acceleration": list(curve.acceleration),
        "jerk": list(curve.jerk),
    }


def _pitch_payload(pitch: PitchCurve) -> dict[str, Any]:
    return {
        "role": pitch.role,
        "theta_deg": list(pitch.theta_deg),
        "lift": list(pitch.lift),
        "velocity": list(pitch.velocity),
        "pivot": [pitch.pivot_x, pitch.pivot_y],
        "arm_angle_deg": list(pitch.arm_angle_deg),
        "valve_contact_x": list(pitch.valve_contact_x),
        "valve_ratio": list(pitch.valve_ratio),
        "pad_contact_angle_deg": list(pitch.pad_contact_angle_deg),
    }


def _jump_payload(meta: dict) -> dict[str, float]:
    return {
        "velocity_jump": round(float(meta.get("junction_velocity_jump", 0.0)), 9),
        "acceleration_jump": round(float(meta.get("junction_acceleration_jump", 0.0)), 9),
    }


def _mechanism_kwargs(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "lash": spec["lash"],
        "ramp_open_deg": spec["ramp_open_deg"],
        "ramp_close_deg": spec["ramp_close_deg"],
        "ramp_profile": spec["ramp_profile"],
        "roller_arm": spec["roller_arm"],
        "roller_angle_deg": spec["roller_angle_deg"],
        "valve_arm": spec["valve_arm"],
        "valve_angle_deg": spec["valve_angle_deg"],
        "valve_axis_deg": spec["valve_axis_deg"],
        "valve_pad_radius": spec["valve_pad_radius"],
    }


def _contact_and_summary(
    spec: dict[str, Any],
    follower: MotionCurve,
    warnings: list[dict[str, Any]],
) -> tuple[Any, dict[str, Any]]:
    motion = TranslatingMotion(offset=spec["offset"])
    if spec["contact"] == "flat":
        profile = flat_follower_profile(follower, base_radius=spec["base_radius"], motion=motion)
        summary = summarize(profile)
        margin = min(
            spec["base_radius"] + s + a for s, a in zip(follower.lift, follower.acceleration)
        )
        summary["flat_curvature_margin"] = round(margin, 6)
        if spec["law"] != "curvature_spline":
            summary["flat_min_base_radius_mm"] = round(spec["base_radius"] - margin, 6)
        contact_offset = max(abs(v - spec["offset"]) for v in follower.velocity)
        # Context-aware synthesis has exact span velocity extrema, independent
        # of output sampling. Include both flanks and the lateral face offset.
        meta = follower.meta.get("valve_meta", {})
        if "opening_peak_contact_offset_mm" in meta:
            contact_offset = max(contact_offset,
                abs(meta["opening_peak_contact_offset_mm"] - spec["offset"]),
                abs(-meta["closing_peak_contact_offset_mm"] - spec["offset"]))
        required_diameter = 2.0 * (contact_offset + spec["tappet_edge_margin"])
        summary["required_tappet_diameter_mm"] = round(required_diameter, 6)
        summary["peak_contact_offset_mm"] = round(contact_offset, 6)
        summary["contact_width_verified"] = spec["tappet_diameter"] is not None
        if spec["tappet_diameter"] is not None:
            edge_clearance = 0.5 * spec["tappet_diameter"] - contact_offset - spec["tappet_edge_margin"]
            summary["tappet_edge_clearance_mm"] = round(edge_clearance, 6)
            if edge_clearance < 0.0:
                warnings.append({"code": "cam_tappet_edge", "params": {"diameter": round(required_diameter, 3)},
                    "message": f"flat contact reaches the tappet edge: working diameter must be at least {required_diameter:.3f} mm"})
        elif spec["law"] == "curvature_spline":
            warnings.append({"code": "cam_tappet_unverified", "params": {},
                "message": "tappet working diameter is not specified; edge contact is unverified"})
        if margin <= 0.0:
            warnings.append({"code": "cam_flat_undercut",
                "params": {"radius": round(spec['base_radius'] - margin, 3)},
                "message": "flat follower cusps/undercut: base radius must exceed "
                           f"{round(spec['base_radius'] - margin, 3)} mm"})
        if spec["law"] == "curvature_spline" and margin < spec["min_curvature_radius"] - 1e-6:
            warnings.append({"code": "cam_curvature_below_min", "params": {
                "value": round(margin, 3), "limit": spec["min_curvature_radius"]},
                "message": "the complete profile falls below the selected minimum curvature; adjust clearance ramps"})
        return profile, summary

    profile = roller_follower_profile(
        follower,
        base_radius=spec["base_radius"],
        roller_radius=spec["roller_radius"],
        motion=motion,
    )
    _, _, centers_x, centers_y, normals = roller_follower_geometry(
        follower,
        base_radius=spec["base_radius"],
        roller_radius=spec["roller_radius"],
        offset=spec["offset"],
    )
    summary = summarize(profile, normals, follower.theta_rad)
    pitch_radius = minimum_convex_curvature_radius(centers_x, centers_y)
    summary["min_convex_pitch_radius_mm"] = round(pitch_radius, 6) if math.isfinite(pitch_radius) else None
    max_angle = summary.get("max_pressure_angle_deg")
    if isinstance(max_angle, float) and max_angle > spec["pressure_angle_limit_deg"]:
        warnings.append({"code": "cam_pressure", "params": {"value": max_angle, "limit": spec['pressure_angle_limit_deg']},
                         "message": f"maximum pressure angle {max_angle} exceeds limit {spec['pressure_angle_limit_deg']}"})
    return profile, summary


def preview_cam_profile(payload: dict[str, Any]) -> dict[str, Any]:
    spec = normalize_cam_request(payload)
    if spec["law"] == "bounded_auto":
        return _bounded_selection(spec)
    if spec["law"] == "motion_spline":
        return _motion_selection(spec)
    base_curve = build_lift_curve(
        law=spec["law"],
        max_lift=spec["max_lift"],
        open_angle_deg=spec["open_angle"],
        dwell_angle_deg=spec["dwell_angle"],
        close_angle_deg=spec["close_angle"],
        phase_deg=spec["phase_deg"],
        samples_per_degree=spec["samples_per_degree"],
        base_radius=spec["base_radius"], lash=spec["lash"],
        min_curvature_radius=spec["min_curvature_radius"], nose_radius=spec["nose_radius"],
        max_acceleration=spec["max_acceleration"], max_jerk=spec["max_jerk"],
    )
    return _evaluate_curve(spec, base_curve)


def _evaluate_curve(spec: dict[str, Any], base_curve: MotionCurve) -> dict[str, Any]:
    mechanism = build_mechanism(spec["mechanism"], **_mechanism_kwargs(spec))
    warnings: list[dict[str, Any]] = []

    if spec["mechanism"] == "rocker":
        if spec["drive"] == "valve":
            valve_payload = _curve_payload(base_curve)
            command = apply_clearance(base_curve, lash=spec["lash"],
                ramp_open_deg=spec["ramp_open_deg"], ramp_close_deg=spec["ramp_close_deg"],
                ramp_profile=spec["ramp_profile"], samples_per_degree=spec["samples_per_degree"])
            pitch = mechanism.pitch_curve_from_pad(
                command,
                base_radius=spec["base_radius"],
                roller_radius=spec["roller_radius"],
            )
        else:
            pitch = mechanism.pitch_curve_from_pad(
                base_curve,
                base_radius=spec["base_radius"],
                roller_radius=spec["roller_radius"],
            )
            valve_payload = {
                "role": "valve",
                "theta_deg": list(pitch.theta_deg),
                "lift": [max(0.0, value - spec["lash"]) for value in pitch.valve_lift],
            }
        profile = roller_from_pitch_curve(
            pitch, base_radius=spec["base_radius"], roller_radius=spec["roller_radius"]
        )
        summary = summarize(profile)
        pitch_radius = minimum_convex_curvature_radius(pitch.center_x, pitch.center_y)
        summary["min_convex_pitch_radius_mm"] = round(pitch_radius, 6) if math.isfinite(pitch_radius) else None
        angles = pressure_angles_from_directions(
            pitch.normal_x, pitch.normal_y, pitch.flow_x, pitch.flow_y
        )
        if angles:
            summary["min_pressure_angle_deg"] = round(min(angles), 4)
            summary["max_pressure_angle_deg"] = round(max(angles), 4)
            if max(angles) > spec["pressure_angle_limit_deg"]:
                warnings.append({"code": "cam_pressure", "params": {"value": round(max(angles), 4), "limit": spec['pressure_angle_limit_deg']},
                    "message": f"maximum pressure angle {round(max(angles), 4)} exceeds limit {spec['pressure_angle_limit_deg']}"})
        follower_payload = _pitch_payload(pitch)
        follower_payload["center_x"] = list(pitch.center_x)
        follower_payload["center_y"] = list(pitch.center_y)
        follower_payload["flow_x"] = list(pitch.flow_x)
        follower_payload["flow_y"] = list(pitch.flow_y)
        summary["continuity"] = _jump_payload(pitch.meta)
    elif spec["drive"] == "valve":
        valve_payload = _curve_payload(base_curve)
        follower = mechanism.follower_from_valve(
            base_curve, samples_per_degree=spec["samples_per_degree"]
        )
        command = follower
        profile, summary = _contact_and_summary(spec, follower, warnings)
        follower_payload = _curve_payload(follower)
        summary["continuity"] = _jump_payload(follower.meta)
    else:
        follower = base_curve
        command = follower
        follower_payload = {**_curve_payload(follower), "role": "follower"}
        valve_payload = _curve_payload(mechanism.valve_from_follower(follower))
        profile, summary = _contact_and_summary(spec, follower, warnings)
        summary["continuity"] = _jump_payload(follower.meta)

    if spec["mechanism"] == "direct" and spec["contact"] == "roller":
        _, _, centers_x, centers_y, _ = roller_follower_geometry(
            follower, base_radius=spec["base_radius"], roller_radius=spec["roller_radius"], offset=spec["offset"]
        )
        follower_payload["center_x"] = centers_x
        follower_payload["center_y"] = centers_y

    min_radius = summary.get("min_convex_pitch_radius_mm")
    law_order = spec["law_continuity_order"]
    if spec["drive"] == "valve" and spec["lash"] > 0.0:
        ramp_order = {"smooth": 1, "smooth_c2": 2}.get(spec["ramp_profile"], 0)
        summary["continuity_order"] = min(law_order, ramp_order)
    else:
        summary["continuity_order"] = law_order
    if spec["drive"] == "valve" or spec["mechanism"] == "direct":
        acceleration = max(abs(value) for value in command.acceleration)
        jerk = max(abs(value) for value in command.jerk)
        acceleration = max(acceleration, base_curve.meta["peak_event_acceleration_mm_per_rad2"])
        jerk = max(jerk, base_curve.meta["peak_event_jerk_mm_per_rad3"])
        if spec["lash"] > 0.0 and spec["drive"] == "valve" and spec["ramp_profile"] == "smooth_c2":
            gamma = math.radians(min(spec["ramp_open_deg"], spec["ramp_close_deg"]))
            acceleration = max(acceleration, 10.0 / math.sqrt(3.0) * spec["lash"] / gamma**2)
            jerk = max(jerk, 60.0 * spec["lash"] / gamma**3)
        summary["peak_acceleration_mm_per_rad2"] = round(acceleration, 6)
        summary["peak_jerk_mm_per_rad3"] = round(jerk, 6)
        summary["derivative_coordinate"] = "valve_command_with_lash" if spec["mechanism"] == "rocker" else "follower_translation"
        for value, limit, code in ((acceleration, spec["max_acceleration"], "cam_acceleration_limit"),
                                   (jerk, spec["max_jerk"], "cam_jerk_limit")):
            if limit is not None and value > limit * (1.0 + 1e-9):
                warnings.append({"code": code, "params": {"value": round(value, 3), "limit": limit},
                    "message": f"complete follower motion derivative {value:.3f} exceeds limit {limit}"})
        if summary["continuity_order"] < 2 and (spec["max_acceleration"] is not None or spec["max_jerk"] is not None):
            warnings.append({"code": "cam_kinematic_discontinuity", "params": {},
                "message": "derivative jumps remain at junctions; finite sampled derivative limits do not cover these discontinuities"})
    if spec["contact"] == "roller" and isinstance(min_radius, float):
        if min_radius < spec["roller_radius"]:
            warnings.append({"code": "cam_roller_undercut", "params": {},
                "message": "minimum convex pitch-curve radius is smaller than roller radius (undercut risk)"})
    if summary["self_intersection"]:
        warnings.append({"code": "cam_self_intersection", "params": {}, "message": "profile self-intersects"})
    if spec["lash"] > 0.0 and spec["drive"] == "valve":
        warnings.append({"code": "cam_clearance", "params": {"lash": spec['lash'],
            "open": spec['ramp_open_deg'], "close": spec['ramp_close_deg']},
            "message": f"thermal clearance {spec['lash']} taken up by {spec['ramp_profile']} ramps "
                       f"({spec['ramp_open_deg']}deg open / {spec['ramp_close_deg']}deg close)"})

    summary["valve_lift_mm"] = round(max(valve_payload["lift"]), 6)
    summary["profile_radial_height_mm"] = round(max(math.hypot(x, y) for x, y in zip(profile.x, profile.y)) - spec["base_radius"], 6)
    if spec["law"] == "curvature_spline":
        summary["nose_radius_mm"] = round(base_curve.meta["nose_radius_mm"], 6)
        summary["minimum_active_curvature_mm"] = round(base_curve.meta["minimum_active_curvature_mm"], 6)
        if spec["max_acceleration"] is None or spec["max_jerk"] is None:
            warnings.append({"code": "cam_curvature_unbounded", "params": {},
                "message": "acceleration or jerk is unbounded; geometrically valid contact can still have excessive acceleration"})
        warnings.append({"code": "cam_curvature_family", "params": {},
            "message": "contact-aware C2 curvature spline with finite jerk jumps; bounded family, not a global optimum"})

    return {
        "law": spec["law"],
        "spec": spec,
        "valve": valve_payload,
        "follower": follower_payload,
        "summary": summary,
        "warnings": [item["message"] for item in warnings],
        "warning_items": warnings,
        "motion_chart": motion_chart_payload(spec, base_curve, command, summary, warnings)
            if spec["drive"] == "valve" or spec["mechanism"] == "direct" else None,
        "profile": {"x": list(profile.x), "y": list(profile.y), "active_count": profile.active_count},
    }
