from __future__ import annotations

import pytest
from pydantic import ValidationError

from geomwright.studio.camshaft import (
    CamshaftPhasesRequest,
    adapt_camshaft_phases,
    build_camshaft_phases_preview,
)


def test_phases_preview_defaults_are_signed_angles() -> None:
    preview = build_camshaft_phases_preview(CamshaftPhasesRequest().model_dump())
    summary = preview["summary"]

    assert summary["intake_open_deg"] == pytest.approx(350.0)
    assert summary["intake_close_deg"] == pytest.approx(590.0)
    assert summary["intake_duration_deg"] == pytest.approx(240.0)
    assert summary["exhaust_open_deg"] == pytest.approx(135.0)
    assert summary["exhaust_close_deg"] == pytest.approx(375.0)
    assert summary["overlap_deg"] == pytest.approx(25.0)
    assert preview["cycle"]["overlap"] == [[350.0, 375.0]]


def test_phases_preview_accepts_dict_payload() -> None:
    preview = build_camshaft_phases_preview(
        {"active_lobe": "exhaust", "intake_open_deg": 5.0}
    )

    assert preview["summary"]["active_lobe"] == "exhaust"
    assert preview["summary"]["intake_open_deg"] == pytest.approx(365.0)


def test_phases_adapter_emits_canvas_contract() -> None:
    import math

    preview = build_camshaft_phases_preview(CamshaftPhasesRequest().model_dump())
    adapted = adapt_camshaft_phases(preview, {})

    assert adapted["family"] == "camshaft_phases"
    assert adapted["active_lobe"] == "intake"
    assert len(adapted["feature_paths"]) == 2
    assert len(adapted["guide_paths"]) == 1
    assert {item["key"] for item in adapted["reference_paths"]} == {"tdc", "bdc"}
    for band in adapted["feature_paths"]:
        assert all(math.isfinite(point[0]) and math.isfinite(point[1]) for point in band)
    bounds = adapted["bounds"]
    assert bounds["x_min"] < bounds["x_max"]
    assert bounds["y_min"] < bounds["y_max"]


def test_phases_request_rejects_unknown_lobe() -> None:
    with pytest.raises(ValidationError):
        CamshaftPhasesRequest(active_lobe="cam")


def test_default_cam_selects_law_and_limits_also_apply_to_rocker() -> None:
    preview = build_camshaft_phases_preview({"step": "cam", "max_acceleration": 100.0, "max_jerk": 1500.0})
    assert preview["cam"]["selection"]["status"] == "passed_sampled_checks"
    adapted = adapt_camshaft_phases(preview, {})
    assert adapted["summary"]["selected_law"]
    assert not adapted["warning_items"]
    failed = build_camshaft_phases_preview({"step": "cam", "law": "polydyne_345", "max_acceleration": 1.0})
    assert any(w["code"] == "cam_acceleration_limit" for w in failed["cam"]["warning_items"])
    assert failed["cam"]["motion_chart"]["limit_exceeded"]["acceleration"] is True


def test_rocker_motion_spline_passes_a_jerk_cap_that_all_standard_laws_fail() -> None:
    params = {"step": "cam", "max_acceleration": 100.0, "max_jerk": 250.0,
              "ramp_open_deg": 25.0, "ramp_close_deg": 25.0}
    result = build_camshaft_phases_preview(params)["cam"]
    assert result["selection"]["selected_law"] == "motion_spline"
    assert result["selection"]["status"] == "passed_sampled_checks"
    standard = result["selection"]["candidates"][:4]
    assert all("cam_jerk_limit" in item["issues"] for item in standard)
    assert result["synthesis"]["status"] == "passed_sampled_checks"
    assert result["summary"]["continuity_order"] == 2
    assert result["summary"]["valve_lift_mm"] == pytest.approx(8.0)
    assert result["summary"]["peak_jerk_mm_per_rad3"] <= 250.0
    assert result["summary"]["peak_acceleration_mm_per_rad2"] <= 100.0
    assert not result["summary"]["self_intersection"]
    manual = build_camshaft_phases_preview({**params, "law": "motion_spline"})["cam"]
    assert manual["synthesis"]["candidate_id"] == result["synthesis"]["candidate_id"]
    assert result["spec"]["max_jerk"] == 250.0
    chart = result["motion_chart"]
    assert chart["coordinate"] == "valve_command_with_lash"
    assert chart["derivative_units"] == "cam_radians"
    assert chart["theta_deg"][0] == pytest.approx(0.0)
    assert chart["theta_deg"][-1] == pytest.approx(170.0)
    assert [w["key"] for w in chart["windows"]] == ["ramp_open", "rise", "fall", "ramp_close"]
    assert chart["windows"][0]["to_deg"] == pytest.approx(25.0)
    assert max(chart["lift"]) == pytest.approx(8.3)
    assert max(chart["valve_lift"]) == pytest.approx(8.0)
    assert len(chart["theta_deg"]) == len(chart["lift"]) == len(chart["jerk"])
    assert chart["peaks"]["jerk"] == result["summary"]["peak_jerk_mm_per_rad3"]
    assert chart["limits"]["jerk"] == 250.0
    assert chart["limit_exceeded"] == {"acceleration": False, "jerk": False}
    assert len(chart["breaks_deg"]["jerk"]) > 4
    first_internal = chart["windows"][0]["to_deg"] + result["synthesis"]["knot_fractions"][1] * result["spec"]["open_angle"]
    assert all(abs(first_internal - t) > 1e-8 for t in chart["breaks_deg"]["jerk"])
    assert chart["breaks_deg"]["acceleration"] == []
    assert chart["derivative_jumps"] is False
    adapted = adapt_camshaft_phases({"step": "cam", "cam": result}, {})
    assert adapted["motion_chart"]["jerk"] == chart["jerk"]
    assert adapted["motion_chart"]["has_warnings"] is False


def test_kinematics_step_emits_schematic() -> None:
    preview = build_camshaft_phases_preview({"step": "kinematics"})
    assert "kinematics" in preview

    adapted = adapt_camshaft_phases(preview, {})
    assert adapted["family"] == "camshaft_kinematics"
    assert adapted["tone_paths"]
    assert adapted["guide_paths"]
    assert adapted["bounds"]["x_min"] < adapted["bounds"]["x_max"]


def test_rocker_roller_tangent_to_base_circle() -> None:
    import math

    preview = build_camshaft_phases_preview({"step": "kinematics"})
    kinematics = preview["kinematics"]
    roller = kinematics["roller"]
    cam = kinematics["cam"]
    assert math.dist(roller, cam) == pytest.approx(40.3, rel=1e-9)
    assert 0.0 <= kinematics["contact_offset_deg"] <= 90.0


def test_direct_mechanism_always_uses_flat_tappet() -> None:
    assert CamshaftPhasesRequest(mechanism="direct", contact="roller").contact == "flat"
    assert CamshaftPhasesRequest(mechanism="rocker", contact="flat").contact == "roller"
    preview = build_camshaft_phases_preview({"step": "kinematics", "mechanism": "direct", "contact": "roller"})
    tappet = preview["kinematics"]["rest_items"][0]["points"]
    assert len(tappet) == 5


def test_direct_mechanism_applies_cam_offset() -> None:
    preview = build_camshaft_phases_preview({"step": "kinematics", "mechanism": "direct", "offset": 6.0})
    assert preview["kinematics"]["cam"][0] == 6.0
    cam = build_camshaft_phases_preview({"step": "cam", "mechanism": "direct", "offset": 6.0})["cam"]
    assert cam["spec"]["offset"] == -6.0


def test_valve_axis_check_warns_when_off() -> None:
    preview = build_camshaft_phases_preview({"step": "kinematics", "valve_tip_y": -40.0})
    kinematics = preview["kinematics"]
    assert kinematics["valve_axis_deviation_deg"] > 10.0
    assert any(item.get("code") == "camshaft_valve_axis" for item in kinematics["warnings"])


def test_rocker_invalid_geometry_raises() -> None:
    with pytest.raises(ValueError):
        build_camshaft_phases_preview(
            {
                "step": "kinematics",
                "roller_arm": 1.0,
                "base_diameter": 60.0,
                "roller_radius": 10.0,
                "cam_y": 50.0,
            }
        )


def test_cam_step_emits_profile() -> None:
    preview = build_camshaft_phases_preview({"step": "cam"})
    assert "cam" in preview

    adapted = adapt_camshaft_phases(preview, {})
    assert adapted["family"] == "camshaft_cam"
    assert len(adapted["feature_paths"]) == 1
    assert adapted["summary"]["point_count"] > 0


@pytest.mark.parametrize("phases,duration,center,overlap", [
    ((-42, 68, -78, 32), 290, 103, 74),  # Kent TR4-6 manufacturer card
    ((-10, 50, -50, 10), 240, 110, 20),  # Stock TR2, Elgin/Tilden
    ((-28, 62, -66, 24), 270, 107, 52),  # TilTech 270, Tilden
])
def test_phases_match_published_cam_cards(phases, duration, center, overlap) -> None:
    # Sources and distinction between seat/gross/net lift: docs/en/camshaft.md.
    payload = dict(zip(("intake_open_deg", "intake_close_deg", "exhaust_open_deg",
                        "exhaust_close_deg"), phases))
    preview = build_camshaft_phases_preview(payload)
    assert preview["summary"]["intake_duration_deg"] == duration
    assert preview["summary"]["exhaust_duration_deg"] == duration
    assert preview["summary"]["intake_lca_deg"] - 360.0 == center
    assert preview["summary"]["overlap_deg"] == overlap
    cam = build_camshaft_phases_preview({**payload, "step": "cam"})["cam"]
    assert cam["spec"]["open_angle"] + cam["spec"]["close_angle"] == duration / 2


def test_kinematics_explicitly_marks_illustrative_profile() -> None:
    adapted = adapt_camshaft_phases(build_camshaft_phases_preview({"step": "kinematics"}), {})
    assert any(item["code"] == "camshaft_schematic" for item in adapted["warning_items"])


def test_request_rejects_nonfinite_and_negative_dimensions() -> None:
    for payload in ({"cam_x": float("nan")}, {"base_diameter": -1},
                    {"lash": -0.1}, {"roller_arm": 0}):
        with pytest.raises(ValidationError):
            CamshaftPhasesRequest.model_validate(payload)
    with pytest.raises(ValueError, match="reach"):
        build_camshaft_phases_preview({"step": "kinematics", "max_lift": 100.0})


def test_studio_contact_spline_uses_valve_lift_and_tappet_width() -> None:
    preview = build_camshaft_phases_preview({"step": "cam", "mechanism": "direct",
        "law": "curvature_spline", "base_diameter": 30.0, "max_lift": 18.0,
        "intake_open_deg": -70.0, "intake_close_deg": 70.0, "tappet_diameter": 42.0})
    adapted = adapt_camshaft_phases(preview, {})
    assert adapted["summary"]["valve_lift_mm"] == 18.0
    assert adapted["summary"]["profile_radial_height_mm"] == 18.3
    assert adapted["summary"]["self_intersection"] is False
    assert adapted["summary"]["contact_width_verified"] is True
    assert adapted["summary"]["tappet_edge_clearance_mm"] > 1.0
