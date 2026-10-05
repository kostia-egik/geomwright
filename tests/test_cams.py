from __future__ import annotations

import math

import pytest

from kompas_mcp.cams import DirectMechanism
from kompas_mcp.cams import build_lift_curve
from kompas_mcp.cams import crank_angle
from kompas_mcp.cams import event_from_crank
from kompas_mcp.cams import flat_follower_profile
from kompas_mcp.cams import get_law
from kompas_mcp.cams import minimum_curvature_radius
from kompas_mcp.cams import normalize_cam_request
from kompas_mcp.cams import preview_cam_profile
from kompas_mcp.cams import roller_follower_geometry
from kompas_mcp.cams import valve_cycle
from kompas_mcp.cams.analyze import pressure_angles_roller
from kompas_mcp.cams.cad import build_cam_plan, verify_cam_geometry, create_cam, CamBuildError

CONTINUITY = {
    "polydyne_345": 2,
    "polydyne_4567": 3,
    "polydyne_56789": 3,
    "cycloidal": 2,
}


def test_cam_cad_strict_limits_recipe_and_actual_curve_verification() -> None:
    from kompas_mcp.cams.cad import _minimum_radius, _radius
    a = 0.317
    # A quadratic expressed as a cubic: the worst curvature is between the
    # previous nine fixed samples, at t=a, and has exact radius 0.5 mm.
    parabola = [[0,a*a],[1/3,a*a-2*a/3],[2/3,a*a-4*a/3+1/3],[1,(1-a)**2]]
    assert _minimum_radius([parabola]) == pytest.approx(0.5,abs=1e-10)
    assert min(_radius(parabola,j/8) for j in range(9)) > 0.51
    payload = _valve_payload(samples_per_degree=10.0,tappet_diameter=40.0)
    plan = build_cam_plan(payload,width=7,rotation_deg=37,tolerance=0.01)
    assert plan["recipe"]["request"]["law"] == payload["law"]
    assert plan["recipe"]["width"] == 7
    report = plan["verification"]
    assert report["engineering_limits"] == "strict"
    assert report["curvature_check"] == "cubic_stationary_roots_and_base_arc"
    preview = preview_cam_profile(payload)
    preview["spec"]["min_curvature_radius"] = report["min_sampled_curvature_radius_mm"]+0.001
    with pytest.raises(ValueError,match="minimum curvature"):
        verify_cam_geometry(plan,plan["curve"],plan["base"],preview)
    preview["spec"]["min_curvature_radius"] = 1.0
    preview["spec"]["tappet_diameter"] = report["required_sampled_tappet_diameter_mm"]-0.001
    with pytest.raises(ValueError,match="tappet edge"):
        verify_cam_geometry(plan,plan["curve"],plan["base"],preview)
    roller = build_cam_plan(_valve_payload(contact="roller",roller_radius=5.0,offset=3.0))
    assert roller["verification"]["contact_recovery_error_mm"] < 0.001
    assert roller["verification"]["max_sampled_pressure_angle_deg"] is not None
    bad_curve = {**plan["curve"],"weights":[math.nan]+plan["curve"]["weights"][1:]}
    with pytest.raises(ValueError,match="finite geometry"):
        verify_cam_geometry(plan,bad_curve,plan["base"])


def test_cam_cad_partial_results_never_finalize_and_preflight_never_writes() -> None:
    from types import SimpleNamespace
    import threading
    class Runner:
        def __init__(self):
            self.calls = []
        def call(self,action,payload,progress_callback=None):
            self.calls.append(action)
            if action == "finalize_cam":
                assert payload["document_id"] == "@document:9"
                assert payload["confirm_write"] is True and len(payload["curve_digest"]) == 64
                return {"ok":True}
            if progress_callback:
                progress_callback({"stage":"cam_profile","document_id":"@document:9"})
            if self.mode == "cancelled":
                raise RuntimeError("Bridge call was cancelled")
            if self.mode in {"verified","cancel_after_native"}:
                plan = payload["plan"]
                bounds = plan["verification"]["bounds_2d"]
                if self.mode == "cancel_after_native":
                    self.cancel_event.set()
                return {"ok":True,"document":{"runtime_id":"@document:9"},
                        "curve_readback":{"curve":plan["curve"],"base":plan["base"]},
                        "exports":{"sketch_ref":12,"feature_ref":13},"verification":{},
                        "body":{"volume":plan["verification"]["expected_volume_cm3"],
                                "bounds":[-plan["width"],-bounds[3],-bounds[2],0,-bounds[1],-bounds[0]]}}
            return {"ok":False,"error":"native failure","partial_result":{
                "document":{"runtime_id":"@document:9"},"verified":False,"status":"partial"}}
    runner = Runner()
    adapter = SimpleNamespace(runner=runner)
    create_cam(adapter,_valve_payload())
    assert not runner.calls
    for mode in ("failed","cancelled"):
        runner.mode = mode
        with pytest.raises(CamBuildError) as caught:
            create_cam(adapter,_valve_payload(),execute=True,confirm_write=True)
        partial = caught.value.partial_result
        assert partial["verified"] is False
        assert (partial.get("document") or {}).get("runtime_id",partial.get("document_id")) == "@document:9"
    assert runner.calls == ["create_cam","create_cam"]
    runner.mode = "verified"
    result = create_cam(adapter,_valve_payload(),execute=True,confirm_write=True)
    assert result["verification"]["ok"] and result["recipe"]["version"] == 1
    assert runner.calls[-2:] == ["create_cam","finalize_cam"]
    runner.mode = "cancel_after_native"
    runner.cancel_event = threading.Event()
    with pytest.raises(CamBuildError,match="cancelled before finalization"):
        create_cam(adapter,_valve_payload(),execute=True,confirm_write=True)
    assert runner.calls[-1] == "create_cam"


def _valve_payload(**overrides: object) -> dict:
    payload = {
        "law": "polydyne_345",
        "base_radius": 30.0,
        "max_lift": 6.0,
        "open_angle": 70.0,
        "dwell_angle": 10.0,
        "close_angle": 70.0,
        "contact": "flat",
        "mechanism": "direct",
        "samples_per_degree": 1.0,
    }
    payload.update(overrides)
    return payload


def _rocker_payload(**overrides: object) -> dict:
    payload = {
        "law": "polydyne_345",
        "base_radius": 30.0,
        "max_lift": 8.0,
        "open_angle": 60.0,
        "dwell_angle": 10.0,
        "close_angle": 60.0,
        "contact": "roller",
        "roller_radius": 10.0,
        "mechanism": "rocker",
        "roller_arm": 30.0,
        "roller_angle_deg": 250.0,
        "valve_arm": 40.0,
        "valve_angle_deg": 200.0,
        "valve_axis_deg": 110.0,
        "samples_per_degree": 2.0,
    }
    payload.update(overrides)
    return payload


def test_bounded_selection_preserves_inputs_and_reports_no_fit() -> None:
    payload = _valve_payload(law="bounded_auto", tappet_diameter=40.0,
                            max_acceleration=40.0, max_jerk=220.0)
    result = preview_cam_profile(payload)
    assert result["selection"]["status"] == "passed_sampled_checks"
    assert result["summary"]["peak_acceleration_mm_per_rad2"] <= 40.0
    assert result["summary"]["peak_jerk_mm_per_rad3"] <= 220.0
    assert result["spec"]["base_radius"] == payload["base_radius"]
    assert result["spec"]["max_lift"] == payload["max_lift"]
    failed = preview_cam_profile({**payload, "max_jerk": 1.0})
    assert failed["selection"]["status"] == "no_passing_candidate"
    assert failed["spec"]["max_jerk"] == 1.0
    assert {w["code"] for w in failed["warning_items"]} >= {"cam_auto_no_solution", "cam_jerk_limit"}


def test_rocker_selection_checks_valve_derivatives_and_actual_contact() -> None:
    result = preview_cam_profile(_rocker_payload(law="bounded_auto", max_acceleration=100.0, max_jerk=1500.0))
    assert len(result["selection"]["candidates"]) == 4
    assert result["summary"]["derivative_coordinate"] == "valve_command_with_lash"
    assert result["summary"]["max_pressure_angle_deg"] >= 0.0
    assert result["summary"]["min_convex_pitch_radius_mm"] is not None
    failed = preview_cam_profile(_rocker_payload(law="bounded_auto", max_acceleration=1.0))
    assert failed["selection"]["status"] == "no_passing_candidate"
    assert any(w["code"] == "cam_acceleration_limit" for w in failed["warning_items"])


def test_standard_derivative_peaks_do_not_depend_on_preview_resolution() -> None:
    for law in CONTINUITY:
        coarse = preview_cam_profile(_valve_payload(law=law, samples_per_degree=0.1))
        fine = preview_cam_profile(_valve_payload(law=law, samples_per_degree=4.0))
        for key in ("peak_acceleration_mm_per_rad2", "peak_jerk_mm_per_rad3", "required_tappet_diameter_mm"):
            assert coarse["summary"][key] == pytest.approx(fine["summary"][key], abs=1e-6)


def test_motion_spline_asymmetric_c2_flanks_and_exact_derivative_caps() -> None:
    from kompas_mcp.cams.motion_spline import MAX_MOTION_CANDIDATES, motion_spline_candidates
    from kompas_mcp.cams.errors import CamSynthesisError

    params = dict(max_lift=8.0, open_angle_deg=55.0, close_angle_deg=75.0,
                  phase_deg=37.0, max_acceleration=100.0, max_jerk=1500.0)
    curves = motion_spline_candidates(**params, samples_per_degree=0.1)
    fine = motion_spline_candidates(**params, samples_per_degree=4.0)
    assert 0 < len(curves) <= MAX_MOTION_CANDIDATES == 48
    curve = curves[0]
    assert curve.meta["candidate_id"] == fine[0].meta["candidate_id"]
    assert curve.theta_deg[0] == pytest.approx(37.0)
    assert curve.theta_deg[-1] == pytest.approx(167.0)
    assert curve.max_lift == pytest.approx(8.0)
    assert curve.lift[0] == pytest.approx(0.0)
    assert curve.lift[-1] == pytest.approx(0.0, abs=1e-9)
    assert curve.velocity[0] == pytest.approx(0.0)
    assert curve.velocity[-1] == pytest.approx(0.0, abs=1e-9)
    assert curve.acceleration[0] == pytest.approx(0.0)
    assert curve.acceleration[-1] == pytest.approx(0.0, abs=1e-9)
    nose = curve.lift.index(max(curve.lift))
    assert curve.velocity[nose] == pytest.approx(0.0, abs=1e-9)
    assert min(curve.velocity[:nose + 1]) >= -1e-9
    assert max(curve.velocity[nose:]) <= 1e-9
    assert curve.meta["opening_acceleration_controls"][-1] == pytest.approx(curve.meta["closing_acceleration_controls"][-1])
    assert len(curve.meta["knot_fractions"]) == len(curve.meta["opening_acceleration_controls"]) == 9
    # All knot angles are sampled: trapezoidal integration of piecewise-linear
    # acceleration must reproduce each velocity increment exactly, including
    # both flanks and the nose. No finite-difference derivative approximation.
    for i in range(len(curve.theta_rad) - 1):
        dt = curve.theta_rad[i + 1] - curve.theta_rad[i]
        expected_dv = dt * (curve.acceleration[i] + curve.acceleration[i + 1]) / 2.0
        assert curve.velocity[i + 1] - curve.velocity[i] == pytest.approx(expected_dv, abs=1e-8)
    assert curve.meta["peak_event_acceleration_mm_per_rad2"] <= 100.0
    assert curve.meta["peak_event_jerk_mm_per_rad3"] <= 1500.0
    assert curve.meta["peak_event_jerk_mm_per_rad3"] == fine[0].meta["peak_event_jerk_mm_per_rad3"]
    with pytest.raises(CamSynthesisError) as error:
        motion_spline_candidates(**{**params, "max_jerk": 1.0})
    assert error.value.code == "cam_motion_no_kinematic_solution"
    with pytest.raises(CamSynthesisError) as tiny:
        motion_spline_candidates(**{**params, "open_angle_deg": 1e-200})
    assert tiny.value.code == "cam_motion_input"


def test_motion_spline_rejects_actual_rocker_contact_without_relaxing_inputs(monkeypatch) -> None:
    import importlib
    from kompas_mcp.cams.errors import CamContactError
    runtime = importlib.import_module("kompas_mcp.cams.preview")
    evaluate = runtime._evaluate_curve
    calls = 0
    def one_degenerate_candidate(spec, curve):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise CamContactError("cam_pitch_degenerate", "degenerate test candidate")
        return evaluate(spec, curve)
    monkeypatch.setattr(runtime, "_evaluate_curve", one_degenerate_candidate)
    params = _rocker_payload(law="motion_spline", dwell_angle=0.0,
                            max_acceleration=100.0, max_jerk=1500.0, min_curvature_radius=500.0)
    result = preview_cam_profile(params)
    assert result["synthesis"]["status"] == "no_passing_candidate"
    assert result["synthesis"]["contact_candidate_count"] == result["synthesis"]["kinematic_candidate_count"]
    assert result["synthesis"]["rejection_counts"]["cam_curvature_below_min"] > 0
    assert result["synthesis"]["rejection_counts"]["cam_pitch_degenerate"] == 1
    assert result["spec"]["min_curvature_radius"] == 500.0
    assert result["spec"]["base_radius"] == params["base_radius"]
    assert result["warning_items"][0]["code"] == "cam_motion_no_contact_solution"
    from kompas_mcp.cams.errors import CamSynthesisError
    reach = 40.0 * (1.0 - math.cos(math.radians(90.0)))
    with pytest.raises(CamSynthesisError) as singular:
        preview_cam_profile(_rocker_payload(law="motion_spline", dwell_angle=0.0, max_lift=reach))
    assert singular.value.code == "cam_rocker_singular"


def test_motion_spline_contact_is_rechecked_at_a_minimum_density() -> None:
    result = preview_cam_profile(_rocker_payload(law="motion_spline", dwell_angle=0.0,
        samples_per_degree=0.1, pressure_angle_limit_deg=45.0,
        max_acceleration=100.0, max_jerk=1500.0))
    assert result["synthesis"]["search_samples_per_degree"] == 2.0
    assert result["synthesis"]["samples_per_degree"] == 4.0
    assert result["synthesis"]["refined_candidate_count"] >= 1
    assert result["spec"]["samples_per_degree"] == 4.0
    assert result["synthesis"]["status"] == "passed_sampled_checks"
    rotated = preview_cam_profile({**result["spec"], "samples_per_degree": 0.1, "phase_deg": 37.0})
    assert rotated["synthesis"]["candidate_id"] == result["synthesis"]["candidate_id"]
    assert rotated["summary"]["max_pressure_angle_deg"] == pytest.approx(result["summary"]["max_pressure_angle_deg"], abs=1e-4)


@pytest.mark.parametrize("law_name", list(CONTINUITY))
def test_laws_satisfy_boundary_conditions(law_name: str) -> None:
    law, _ = get_law(law_name)
    order = CONTINUITY[law_name]

    assert law.derivative(0.0, 0) == pytest.approx(0.0, abs=1e-12)
    assert law.derivative(1.0, 0) == pytest.approx(1.0, abs=1e-9)
    for rank in range(1, order + 1):
        assert law.derivative(0.0, rank) == pytest.approx(0.0, abs=1e-9)
        assert law.derivative(1.0, rank) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("law_name", list(CONTINUITY))
def test_analytic_derivatives_match_finite_difference(law_name: str) -> None:
    law, _ = get_law(law_name)
    step = 1e-6
    for t in (0.13, 0.37, 0.62, 0.88):
        for rank in (1, 2, 3):
            analytic = law.derivative(t, rank)
            numeric = (
                law.derivative(t + step, rank - 1) - law.derivative(t - step, rank - 1)
            ) / (2.0 * step)
            assert analytic == pytest.approx(numeric, rel=1e-4, abs=1e-4)


def test_polydyne_56789_is_minimum_jerk_like() -> None:
    law, _ = get_law("polydyne_56789")
    assert law.derivative(1.0, 4) == pytest.approx(0.0, abs=1e-6)


def test_valve_curve_endpoints_and_peak() -> None:
    curve = build_lift_curve(
        law="polydyne_345",
        max_lift=8.0,
        open_angle_deg=60.0,
        dwell_angle_deg=10.0,
        close_angle_deg=60.0,
        samples_per_degree=1.0,
    )
    assert curve.role == "valve"
    assert curve.lift[0] == pytest.approx(0.0, abs=1e-9)
    assert curve.lift[-1] == pytest.approx(0.0, abs=1e-9)
    assert max(curve.lift) == pytest.approx(8.0, abs=1e-9)
    assert curve.velocity[0] == pytest.approx(0.0, abs=1e-9)
    assert curve.velocity[-1] == pytest.approx(0.0, abs=1e-9)


def test_direct_mechanism_without_lash_is_identity() -> None:
    valve = build_lift_curve(
        law="polydyne_4567",
        max_lift=8.0,
        open_angle_deg=60.0,
        dwell_angle_deg=10.0,
        close_angle_deg=60.0,
        samples_per_degree=1.0,
    )
    follower = DirectMechanism().follower_from_valve(valve)
    assert follower.role == "follower"
    assert follower.lift == pytest.approx(valve.lift)
    assert max(follower.lift) == pytest.approx(8.0, abs=1e-9)


def test_direct_mechanism_applies_thermal_clearance_ramp() -> None:
    valve = build_lift_curve(
        law="polydyne_345",
        max_lift=8.0,
        open_angle_deg=60.0,
        dwell_angle_deg=10.0,
        close_angle_deg=60.0,
        samples_per_degree=1.0,
    )
    mechanism = DirectMechanism(lash=0.3, ramp_open_deg=20.0, ramp_close_deg=20.0)
    follower = mechanism.follower_from_valve(valve, samples_per_degree=1.0)

    assert max(follower.lift) == pytest.approx(8.3, abs=1e-9)
    assert min(follower.lift) == pytest.approx(0.0, abs=1e-9)
    assert follower.theta_rad[0] < valve.theta_rad[0]
    assert follower.theta_rad[-1] > valve.theta_rad[-1]

    round_trip = mechanism.valve_from_follower(follower)
    assert max(round_trip.lift) == pytest.approx(8.0, abs=1e-9)
    assert min(round_trip.lift) == pytest.approx(0.0, abs=1e-9)


def test_flat_profile_closes_on_base_circle() -> None:
    spec = normalize_cam_request(_valve_payload())
    curve = build_lift_curve(
        law=spec["law"],
        max_lift=spec["max_lift"],
        open_angle_deg=spec["open_angle"],
        dwell_angle_deg=spec["dwell_angle"],
        close_angle_deg=spec["close_angle"],
        samples_per_degree=spec["samples_per_degree"],
    )
    follower = DirectMechanism().follower_from_valve(curve)
    profile = flat_follower_profile(follower, base_radius=spec["base_radius"])

    assert profile.x[0] == pytest.approx(profile.x[-1], abs=1e-9)
    assert profile.y[0] == pytest.approx(profile.y[-1], abs=1e-9)
    assert math.hypot(profile.x[0], profile.y[0]) == pytest.approx(30.0, abs=1e-9)
    assert profile.active_count < len(profile.x)


def test_roller_profile_stays_tangent_to_roller() -> None:
    valve = build_lift_curve(
        law="polydyne_4567",
        max_lift=8.0,
        open_angle_deg=60.0,
        dwell_angle_deg=10.0,
        close_angle_deg=60.0,
        samples_per_degree=1.0,
    )
    follower = DirectMechanism().follower_from_valve(valve)
    xs, ys, centers_x, centers_y, _ = roller_follower_geometry(
        follower,
        base_radius=20.0,
        roller_radius=10.0,
        offset=5.0,
    )
    for x, y, cx, cy in zip(xs, ys, centers_x, centers_y):
        assert math.dist((x, y), (cx, cy)) == pytest.approx(10.0, rel=1e-9, abs=1e-9)


def test_roller_offset_base_pressure_angle() -> None:
    valve = build_lift_curve(
        law="polydyne_345",
        max_lift=8.0,
        open_angle_deg=60.0,
        dwell_angle_deg=0.0,
        close_angle_deg=60.0,
        samples_per_degree=1.0,
    )
    follower = DirectMechanism().follower_from_valve(valve)
    _, _, _, _, normals = roller_follower_geometry(
        follower,
        base_radius=20.0,
        roller_radius=10.0,
        offset=5.0,
    )
    angles = pressure_angles_roller(normals)
    expected = math.degrees(math.asin(5.0 / 30.0))
    assert angles[0] == pytest.approx(expected, abs=1e-6)


def test_roller_pressure_is_phase_invariant_and_matches_velocity() -> None:
    curve = build_lift_curve(law="polydyne_345", max_lift=8.0,
                            open_angle_deg=60.0, dwell_angle_deg=0.0,
                            close_angle_deg=60.0, phase_deg=137.0)
    _, _, _, _, normals = roller_follower_geometry(
        curve, base_radius=20.0, roller_radius=10.0, offset=5.0)
    angles = pressure_angles_roller(normals, curve.theta_rad)
    rest = math.sqrt(30.0**2 - 5.0**2)
    expected = [math.degrees(math.atan2(abs(v - 5.0), rest + s))
                for s, v in zip(curve.lift, curve.velocity)]
    assert angles == pytest.approx(expected, abs=1e-6)
    assert preview_cam_profile(_valve_payload(contact="roller", roller_radius=10.0,
                                              phase_deg=0.0))["summary"]["max_pressure_angle_deg"] == pytest.approx(
        preview_cam_profile(_valve_payload(contact="roller", roller_radius=10.0,
                                           phase_deg=137.0))["summary"]["max_pressure_angle_deg"])


def test_rocker_fixed_arm_projection_and_normal_match_numeric_tangent() -> None:
    from kompas_mcp.cams.mechanisms import RockerMechanism

    curve = build_lift_curve(law="polydyne_345", max_lift=8.0,
                            open_angle_deg=60.0, dwell_angle_deg=0.0,
                            close_angle_deg=60.0, samples_per_degree=10.0)
    mechanism = RockerMechanism(roller_arm=30.0, roller_angle_deg=250.0,
                               valve_arm=40.0, valve_angle_deg=200.0,
                               valve_axis_deg=110.0)
    pitch = mechanism.pitch_curve(curve, base_radius=30.0, roller_radius=10.0)
    phi, axis = math.radians(200.0), math.radians(110.0)
    for i in (100, 300, 500, 700, 900):
        alpha = math.radians(pitch.arm_angle_deg[i])
        projected_lift = 40.0 * (math.cos(phi + alpha - axis) - math.cos(phi - axis))
        assert projected_lift == pytest.approx(curve.lift[i], abs=1e-9)
        dx = pitch.center_x[i + 1] - pitch.center_x[i - 1]
        dy = pitch.center_y[i + 1] - pitch.center_y[i - 1]
        assert (dx * pitch.normal_x[i] + dy * pitch.normal_y[i]) / math.hypot(dx, dy) == pytest.approx(0.0, abs=2e-5)


def test_cam_sampling_budget_is_bounded() -> None:
    with pytest.raises(ValueError, match="at most 10"):
        normalize_cam_request(_valve_payload(samples_per_degree=1e8))
    with pytest.raises(ValueError, match="at most 10"):
        build_lift_curve(law="polydyne_345", max_lift=6.0, open_angle_deg=70.0,
                         dwell_angle_deg=0.0, close_angle_deg=70.0, samples_per_degree=1e8)
    with pytest.raises(ValueError, match="finite"):
        event_from_crank(open_deg=0.0, close_deg=float("nan"))


def test_roller_undercut_uses_pitch_radius_not_finished_radius() -> None:
    result = preview_cam_profile(_valve_payload(contact="roller", roller_radius=10.0,
        base_radius=5.0, max_lift=0.2, open_angle=120.0, close_angle=120.0))
    assert result["summary"]["min_curvature_radius"] < 10.0
    assert result["summary"]["min_convex_pitch_radius_mm"] > 10.0
    assert not any("undercut" in item for item in result["warnings"])


def test_full_turn_event_does_not_append_a_second_base_turn() -> None:
    curve = build_lift_curve(law="polydyne_345", max_lift=0.2,
        open_angle_deg=180.0, dwell_angle_deg=0.0, close_angle_deg=180.0)
    profile = flat_follower_profile(curve, base_radius=30.0)
    assert len(profile.x) == profile.active_count
    assert profile.x[0] == pytest.approx(profile.x[-1])


def test_self_intersection_handles_closed_contours() -> None:
    from kompas_mcp.cams.analyze import self_intersection

    assert self_intersection((0, 2, 0, 2, 0), (0, 2, 2, 0, 0))
    assert not self_intersection((0, 2, 2, 0, 0), (0, 0, 2, 2, 0))
    assert not self_intersection((0, 2, 2, 2, 0, 0), (0, 0, 0, 2, 2, 0))
    assert self_intersection((0, 2, 1, 1, 0), (0, 0, 0, 1, 1))


def test_circle_curvature_matches_radius() -> None:
    radius = 7.0
    count = 120
    x = tuple(radius * math.cos(2.0 * math.pi * i / count) for i in range(count))
    y = tuple(radius * math.sin(2.0 * math.pi * i / count) for i in range(count))
    assert minimum_curvature_radius(x, y) == pytest.approx(radius, rel=1e-3)


def test_preview_flat_with_thermal_clearance() -> None:
    result = preview_cam_profile(_valve_payload(lash=0.3, ramp_open_deg=20.0, ramp_close_deg=20.0))

    assert result["summary"]["self_intersection"] is False
    assert result["summary"]["flat_curvature_margin"] > 0.0
    assert max(result["follower"]["lift"]) == pytest.approx(6.3, abs=1e-6)
    assert result["profile"]["x"][0] == pytest.approx(result["profile"]["x"][-1], abs=1e-6)
    assert any("thermal clearance" in warning for warning in result["warnings"])


def test_preview_flat_detects_undercut() -> None:
    result = preview_cam_profile(
        _valve_payload(base_radius=20.0, max_lift=8.0, open_angle=60.0, close_angle=60.0)
    )

    assert result["summary"]["flat_curvature_margin"] <= 0.0
    assert any("cusps/undercut" in warning for warning in result["warnings"])


def test_contact_aware_spline_supports_small_base_and_high_direct_lift() -> None:
    payload = _valve_payload(law="curvature_spline", base_radius=15.0, max_lift=18.0,
        open_angle=80.0, close_angle=80.0, dwell_angle=0.0, lash=0.3,
        ramp_open_deg=20.0, ramp_close_deg=20.0, tappet_diameter=42.0)
    result = preview_cam_profile(payload)
    summary = result["summary"]
    assert summary["valve_lift_mm"] == pytest.approx(18.0)
    assert summary["profile_radial_height_mm"] == pytest.approx(18.3)
    assert summary["flat_curvature_margin"] >= 1.0 - 1e-6
    assert summary["self_intersection"] is False
    assert summary["tappet_edge_clearance_mm"] > 1.0
    assert summary["continuity_order"] == 2
    assert summary["continuity"] == {"velocity_jump": 0.0, "acceleration_jump": 0.0}
    assert "flat_min_base_radius_mm" not in summary  # law depends on the base
    assert not {"cam_flat_undercut", "cam_self_intersection", "cam_tappet_edge"} & {
        item["code"] for item in result["warning_items"]}
    assert result["spec"]["ramp_profile"] == "smooth_c2"

    # Independent inverse-contact check: every sampled flat face supports the
    # whole contour, and its support distance reproduces the prescribed lift.
    points = list(zip(result["profile"]["x"], result["profile"]["y"]))
    follower = result["follower"]
    for i in range(0, len(follower["lift"]), 29):
        theta = math.radians(follower["theta_deg"][i])
        support = max(x * math.cos(theta) + y * math.sin(theta) for x, y in points)
        assert support == pytest.approx(15.0 + follower["lift"][i], abs=1e-7)

    legacy = preview_cam_profile({**payload, "law": "polydyne_345"})
    assert legacy["summary"]["flat_curvature_margin"] < 0.0
    shorter = preview_cam_profile({**payload, "open_angle": 70.0, "close_angle": 70.0,
                                   "tappet_diameter": 48.0})
    assert shorter["summary"]["flat_curvature_margin"] >= 1.0 - 1e-6
    assert shorter["summary"]["self_intersection"] is False
    assert shorter["summary"]["tappet_edge_clearance_mm"] > 0.0


def test_curvature_family_preserves_nose_and_sampling_independent_contact_limits() -> None:
    payload = _valve_payload(law="curvature_spline", base_radius=15.0, max_lift=18.0,
        open_angle=80.0, close_angle=85.0, dwell_angle=0.0, nose_radius=3.0,
        tappet_diameter=50.0)
    coarse = preview_cam_profile({**payload, "samples_per_degree": 1.0})
    fine = preview_cam_profile({**payload, "samples_per_degree": 5.0})
    assert coarse["summary"]["nose_radius_mm"] == 3.0
    assert fine["summary"]["required_tappet_diameter_mm"] == coarse["summary"]["required_tappet_diameter_mm"]
    assert coarse["valve"]["acceleration"][0] == pytest.approx(0.0, abs=1e-8)
    assert coarse["valve"]["acceleration"][-1] == pytest.approx(0.0, abs=1e-8)
    peak = max(range(len(coarse["valve"]["lift"])), key=lambda i: coarse["valve"]["lift"][i])
    assert coarse["valve"]["acceleration"][peak] == pytest.approx(3.0 - 15.0 - 18.0)
    assert coarse["summary"]["self_intersection"] is False


def test_flat_tappet_offset_and_width_affect_contact_not_infinite_envelope() -> None:
    payload = _valve_payload(law="curvature_spline", base_radius=15.0, max_lift=18.0,
        open_angle=80.0, close_angle=80.0, dwell_angle=0.0, tappet_diameter=42.0)
    centered = preview_cam_profile(payload)
    offset = preview_cam_profile({**payload, "offset": 3.0})
    assert centered["profile"] == offset["profile"]
    assert offset["summary"]["required_tappet_diameter_mm"] == pytest.approx(
        centered["summary"]["required_tappet_diameter_mm"] + 6.0)
    assert any(item["code"] == "cam_tappet_edge" for item in offset["warning_items"])
    assert offset["summary"]["self_intersection"] is False


def test_contact_spline_rejects_geometry_bound_and_unsupported_mechanisms() -> None:
    from kompas_mcp.cams.curvature import CurvatureSynthesisError

    with pytest.raises(CurvatureSynthesisError) as error:
        preview_cam_profile(_valve_payload(law="curvature_spline", base_radius=15,
            max_lift=18, open_angle=60, close_angle=60, dwell_angle=0))
    assert error.value.code == "cam_flat_support_bound"
    assert error.value.params["angle"] > 60
    with pytest.raises(CurvatureSynthesisError, match="direct flat tappet"):
        normalize_cam_request(_rocker_payload(law="curvature_spline", dwell_angle=0))


def test_contact_spline_enforces_angular_derivative_limits_without_hidden_lift_changes() -> None:
    from kompas_mcp.cams.curvature import CurvatureSynthesisError

    payload = _valve_payload(law="curvature_spline", base_radius=15.0, max_lift=18.0,
        open_angle=80.0, close_angle=80.0, dwell_angle=0.0, lash=0.3,
        ramp_open_deg=25.0, ramp_close_deg=25.0, tappet_diameter=48.0,
        min_curvature_radius=3.0, max_acceleration=100.0, max_jerk=1500.0)
    result = preview_cam_profile(payload)
    summary = result["summary"]
    assert summary["valve_lift_mm"] == 18.0
    assert summary["peak_acceleration_mm_per_rad2"] <= 100.0
    assert summary["peak_jerk_mm_per_rad3"] <= 1500.0
    assert max(abs(a) for a in result["follower"]["acceleration"]) <= 100.0
    assert max(abs(j) for j in result["follower"]["jerk"]) <= 1500.0
    assert summary["flat_curvature_margin"] >= 3.0 - 1e-6
    assert summary["tappet_edge_clearance_mm"] > 0.0
    assert summary["self_intersection"] is False
    assert not {"cam_curvature_below_min", "cam_tappet_edge", "cam_acceleration_limit",
                "cam_jerk_limit", "cam_curvature_unbounded"} & {
                    item["code"] for item in result["warning_items"]}
    with pytest.raises(CurvatureSynthesisError) as error:
        preview_cam_profile({**payload, "max_acceleration": 1.0, "max_jerk": 1.0})
    assert error.value.code == "cam_curvature_no_solution"
    # Main-event limits do not hide a too-short clearance ramp.
    short_ramp = preview_cam_profile({**payload, "ramp_open_deg": 5.0})
    assert any(item["code"] == "cam_jerk_limit" for item in short_ramp["warning_items"])


def test_preview_roller_offset() -> None:
    result = preview_cam_profile(
        _valve_payload(
            contact="roller",
            roller_radius=10.0,
            offset=5.0,
            law="polydyne_56789",
        )
    )

    assert result["summary"]["self_intersection"] is False
    assert "max_pressure_angle_deg" in result["summary"]
    assert result["summary"]["max_pressure_angle_deg"] >= 0.0


def test_rocker_pitch_rests_on_base_circle() -> None:
    result = preview_cam_profile(_rocker_payload())

    profile_x = result["profile"]["x"]
    profile_y = result["profile"]["y"]
    assert profile_x[0] == pytest.approx(profile_x[-1], abs=1e-6)
    assert math.hypot(profile_x[0], profile_y[0]) == pytest.approx(30.0, abs=1e-6)
    assert max(result["follower"]["lift"]) == pytest.approx(8.0, abs=1e-6)
    assert len(result["follower"]["pivot"]) == 2


def test_rocker_is_clean_and_reports_pressure_angle() -> None:
    result = preview_cam_profile(_rocker_payload())

    assert result["summary"]["self_intersection"] is False
    assert result["summary"]["min_curvature_radius"] > result["spec"]["roller_radius"]
    assert result["summary"]["max_pressure_angle_deg"] > 0.0


def test_rocker_with_thermal_clearance() -> None:
    result = preview_cam_profile(
        _rocker_payload(lash=0.3, ramp_open_deg=20.0, ramp_close_deg=20.0)
    )

    assert result["summary"]["self_intersection"] is False
    assert max(result["follower"]["lift"]) == pytest.approx(8.3, abs=1e-6)
    assert any("thermal clearance" in warning for warning in result["warnings"])


def test_event_from_crank_intake_example() -> None:
    event = event_from_crank(open_deg=-10.0, close_deg=230.0)

    assert event.duration_crank_deg == pytest.approx(240.0)
    assert event.duration_cam_deg == pytest.approx(120.0)
    assert event.open_angle == pytest.approx(60.0)
    assert event.close_angle == pytest.approx(60.0)
    assert event.dwell_angle == pytest.approx(0.0)
    assert event.phase_deg == pytest.approx(-5.0)


def test_event_from_crank_with_dwell() -> None:
    event = event_from_crank(open_deg=-10.0, close_deg=230.0, dwell_deg=20.0)

    assert event.dwell_angle == pytest.approx(10.0)
    assert event.open_angle == pytest.approx(55.0)
    assert event.open_angle + event.dwell_angle + event.close_angle == pytest.approx(
        event.duration_cam_deg
    )


def test_event_from_crank_asymmetric_nose_center() -> None:
    event = event_from_crank(open_deg=-10.0, close_deg=230.0, nose_center_deg=90.0)

    assert event.open_angle == pytest.approx(50.0)
    assert event.close_angle == pytest.approx(70.0)
    assert event.duration_cam_deg == pytest.approx(120.0)
    assert event.phase_deg == pytest.approx(-5.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"open_deg": 10.0, "close_deg": 5.0},
        {"open_deg": 0.0, "close_deg": 800.0},
        {"open_deg": 0.0, "close_deg": 240.0, "dwell_deg": 240.0},
        {"open_deg": 0.0, "close_deg": 240.0, "nose_center_deg": 250.0},
        {"open_deg": 0.0, "close_deg": 240.0, "nose_center_deg": -5.0},
    ],
)
def test_event_from_crank_validation(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        event_from_crank(**kwargs)


def test_preview_accepts_asymmetric_timing() -> None:
    result = preview_cam_profile(
        _valve_payload(timing={"open_deg": -10.0, "close_deg": 230.0, "nose_center_deg": 90.0})
    )

    spec = result["spec"]
    assert spec["open_angle"] == pytest.approx(50.0)
    assert spec["close_angle"] == pytest.approx(70.0)
    assert max(result["valve"]["lift"]) == pytest.approx(6.0, abs=1e-6)


def test_preview_accepts_crank_timing() -> None:
    result = preview_cam_profile(
        _valve_payload(timing={"open_deg": -10.0, "close_deg": 230.0})
    )

    spec = result["spec"]
    assert spec["open_angle"] == pytest.approx(60.0)
    assert spec["dwell_angle"] == pytest.approx(0.0)
    assert spec["close_angle"] == pytest.approx(60.0)
    assert spec["phase_deg"] == pytest.approx(-5.0)
    assert result["summary"]["self_intersection"] is False


def test_rocker_reports_valve_slide_and_ratio() -> None:
    result = preview_cam_profile(_rocker_payload())

    ratio = result["follower"]["valve_ratio"]
    contact_x = result["follower"]["valve_contact_x"]
    assert any(abs(value) > 0.0 for value in ratio)
    assert max(ratio) - min(ratio) > 0.0
    assert max(contact_x) - min(contact_x) > 0.0
    assert any(abs(value) > 0.0 for value in result["follower"]["arm_angle_deg"])


def test_cam_driven_direct_uses_law_as_cam() -> None:
    result = preview_cam_profile(_valve_payload(drive="cam"))

    assert result["follower"]["role"] == "follower"
    assert max(result["follower"]["lift"]) == pytest.approx(6.0, abs=1e-6)
    assert max(result["valve"]["lift"]) == pytest.approx(6.0, abs=1e-6)
    assert result["summary"]["self_intersection"] is False


def test_cam_driven_direct_applies_lash_forward() -> None:
    result = preview_cam_profile(_valve_payload(drive="cam", lash=0.3))

    assert max(result["follower"]["lift"]) == pytest.approx(6.0, abs=1e-6)
    assert max(result["valve"]["lift"]) == pytest.approx(5.7, abs=1e-6)


def test_cam_driven_rocker_forward_valve() -> None:
    result = preview_cam_profile(_rocker_payload(drive="cam"))

    assert result["follower"]["role"] == "follower"
    assert max(result["follower"]["lift"]) == pytest.approx(8.0, abs=1e-6)
    assert max(result["valve"]["lift"]) > 0.0
    assert result["summary"]["self_intersection"] is False


def test_smooth_ramp_is_continuous() -> None:
    result = preview_cam_profile(
        _valve_payload(lash=0.3, ramp_open_deg=20.0, ramp_close_deg=20.0)
    )

    continuity = result["summary"]["continuity"]
    assert continuity["velocity_jump"] == pytest.approx(0.0, abs=1e-9)
    assert continuity["acceleration_jump"] > 0.0
    assert result["motion_chart"]["derivative_jumps"] is True
    assert result["motion_chart"]["breaks_deg"]["acceleration"]
    assert result["motion_chart"]["velocity"] == result["follower"]["velocity"]


def test_constant_velocity_ramp_reports_velocity_step() -> None:
    result = preview_cam_profile(
        _valve_payload(
            lash=0.3,
            ramp_open_deg=20.0,
            ramp_close_deg=20.0,
            ramp_profile="constant_velocity",
        )
    )

    continuity = result["summary"]["continuity"]
    expected = 0.3 / math.radians(20.0)
    assert continuity["velocity_jump"] == pytest.approx(expected, rel=1e-9)
    assert result["motion_chart"]["breaks_deg"]["velocity"]
    assert continuity["acceleration_jump"] == pytest.approx(0.0, abs=1e-9)


def test_constant_acceleration_ramp_runs() -> None:
    result = preview_cam_profile(
        _valve_payload(
            lash=0.3,
            ramp_open_deg=20.0,
            ramp_close_deg=20.0,
            ramp_profile="constant_acceleration",
        )
    )

    assert max(result["follower"]["lift"]) == pytest.approx(6.3, abs=1e-6)
    continuity = result["summary"]["continuity"]
    assert continuity["velocity_jump"] == pytest.approx(
        2.0 * 0.3 / math.radians(20.0), rel=1e-9
    )
    assert continuity["acceleration_jump"] > 0.0


def test_law_continuity_order_exposed() -> None:
    assert normalize_cam_request(_valve_payload(law="polydyne_345"))["law_continuity_order"] == 2
    assert normalize_cam_request(_valve_payload(law="polydyne_4567"))["law_continuity_order"] == 3
    assert normalize_cam_request(_valve_payload(law="cycloidal"))["law_continuity_order"] == 2


def test_continuity_order_reduced_by_ramp() -> None:
    no_lash = preview_cam_profile(_valve_payload(law="polydyne_56789"))
    assert no_lash["summary"]["continuity_order"] == 3

    smooth = preview_cam_profile(
        _valve_payload(law="polydyne_56789", lash=0.3, ramp_open_deg=20.0, ramp_close_deg=20.0)
    )
    assert smooth["summary"]["continuity_order"] == 1

    constant_velocity = preview_cam_profile(
        _valve_payload(
            law="polydyne_56789",
            lash=0.3,
            ramp_open_deg=20.0,
            ramp_close_deg=20.0,
            ramp_profile="constant_velocity",
        )
    )
    assert constant_velocity["summary"]["continuity_order"] == 0


def test_flank_to_nose_continuity() -> None:
    curve = build_lift_curve(
        law="polydyne_56789",
        max_lift=8.0,
        open_angle_deg=60.0,
        dwell_angle_deg=10.0,
        close_angle_deg=60.0,
        samples_per_degree=2.0,
    )
    peak = max(curve.lift)
    dwell = [index for index, value in enumerate(curve.lift) if abs(value - peak) < 1e-9]
    assert dwell

    for index in dwell:
        assert abs(curve.velocity[index]) < 1e-9
        assert abs(curve.acceleration[index]) < 1e-9
        assert abs(curve.jerk[index]) < 1e-9

    first = dwell[0]
    assert abs(curve.velocity[first] - curve.velocity[first - 1]) < 1e-3
    assert abs(curve.acceleration[first] - curve.acceleration[first - 1]) < 5e-2

    last = dwell[-1]
    assert abs(curve.velocity[last + 1] - curve.velocity[last]) < 1e-3
    assert abs(curve.acceleration[last + 1] - curve.acceleration[last]) < 5e-2


def test_valve_pad_radius_does_not_change_lift() -> None:
    plain = preview_cam_profile(_rocker_payload())
    padded = preview_cam_profile(_rocker_payload(valve_pad_radius=200.0))

    assert padded["follower"]["lift"] == pytest.approx(plain["follower"]["lift"], abs=1e-9)
    assert padded["valve"]["lift"] == pytest.approx(plain["valve"]["lift"], abs=1e-9)
    assert padded["spec"]["valve_pad_radius"] == pytest.approx(200.0)

    angles = plain["follower"]["pad_contact_angle_deg"]
    assert max(angles) - min(angles) > 0.0


def test_crank_angle_flags() -> None:
    assert crank_angle(10.0, "BTDC", 360.0) == pytest.approx(350.0)
    assert crank_angle(50.0, "ABDC", 540.0) == pytest.approx(590.0)
    assert crank_angle(45.0, "BBDC", 180.0) == pytest.approx(135.0)
    assert crank_angle(15.0, "ATDC", 360.0) == pytest.approx(375.0)
    with pytest.raises(ValueError):
        crank_angle(1.0, "SIDEWAYS", 0.0)


def test_valve_cycle_overlap_and_validation() -> None:
    cycle = valve_cycle(
        intake_open=350.0,
        intake_close=590.0,
        exhaust_open=135.0,
        exhaust_close=375.0,
    )

    assert cycle.intake_close - cycle.intake_open == pytest.approx(240.0)
    assert cycle.exhaust_close - cycle.exhaust_open == pytest.approx(240.0)
    assert cycle.overlap == ((350.0, 375.0),)
    assert cycle.scale_deg == pytest.approx(720.0)

    with pytest.raises(ValueError):
        valve_cycle(intake_open=590.0, intake_close=350.0, exhaust_open=100.0, exhaust_close=200.0)


@pytest.mark.parametrize(
    "payload",
    [
        _valve_payload(law="unknown"),
        _valve_payload(base_radius=-1.0),
        _valve_payload(open_angle=200.0, close_angle=200.0),
        _valve_payload(contact="roller"),
        _valve_payload(tappet_diameter=0.5, tappet_edge_margin=0.5),
        _valve_payload(lash=0.3),
        _valve_payload(ramp_profile="bogus"),
        _valve_payload(timing={"open_deg": 10.0, "close_deg": 5.0}),
        _rocker_payload(contact="flat"),
        _rocker_payload(roller_radius=0.0),
        _rocker_payload(valve_arm=3.0),
        _rocker_payload(offset=2.0),
        _rocker_payload(valve_pad_radius=-1.0),
    ],
)
def test_invalid_requests_raise(payload: dict) -> None:
    with pytest.raises(ValueError):
        normalize_cam_request(payload)
