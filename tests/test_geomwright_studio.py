from __future__ import annotations

import re
import time
import math

import pytest

from geomwright.studio.registry import get_module, list_modules, managed_pulley_plan, preview_module
from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.bridge_runner import BridgeError
from kompas_mcp.transmissions import build_chain_sprocket_plan, list_chain_profiles, preview_chain_sprocket


def test_registry_exposes_schema_driven_transmission_modules() -> None:
    modules = list_modules()

    assert [item["kind"] for item in modules] == ["v_belt", "poly_v", "flat_belt", "timing_trapezoidal", "timing_curvilinear", "chain_sprocket", "silent_chain_sprocket", "gear_spur", "gear_internal", "gear_bevel", "shaft_spline", "hub_spline", "camshaft_lobe"]
    transmissions = [item for item in modules if item["group"] == "mechanical_transmissions"]
    valvetrain = [item for item in modules if item["group"] == "valvetrain"]
    assert [item["kind"] for item in valvetrain] == ["camshaft_lobe"]
    assert valvetrain[0]["subgroup"] == "valvetrain"
    assert all(item["subgroup"] == "belt_drives" for item in transmissions[:-5])
    assert all(item["subgroup"] == "chain_drives" for item in transmissions[-5:-3])
    assert all(item["subgroup"] == "gear_drives" for item in transmissions[-3:])
    assert [item["icon"] for item in transmissions[-5:-3]] == [
        "/static/icons/roller-sprocket.svg", "/static/icons/silent-sprocket.svg",
    ]
    assert [item["icon"] for item in transmissions[-3:]] == [
        "/static/icons/gear-spur.svg", "/static/icons/gear-internal.svg", "/static/icons/gear-bevel.svg",
    ]
    assert valvetrain[0]["icon"] == "/static/icons/cam.svg"
    assert get_module("timing_trapezoidal").descriptor()["capabilities"]["build"] is True
    assert get_module("timing_curvilinear").descriptor()["capabilities"] == {"preview": True, "build": True, "inspect": False}
    assert get_module("gear_spur").descriptor()["capabilities"] == {"preview": True, "build": True, "inspect": False}
    assert get_module("gear_internal").descriptor()["capabilities"] == {"preview": True, "build": True, "inspect": False}
    assert get_module("gear_bevel").descriptor()["capabilities"] == {"preview": True, "build": True, "inspect": False}
    for kind in ("v_belt", "poly_v", "flat_belt", "timing_trapezoidal", "timing_curvilinear", "gear_spur", "gear_internal", "gear_bevel"):
        module = get_module(kind)
        spec = module.spec()
        validated = module.request_model.model_validate(spec["defaults"])

        assert spec["module"]["preview_url"] == f"/modules/{kind}/preview"
        assert spec["module"]["cad_plan_url"] == f"/modules/{kind}/cad/plan"
        assert spec["module"]["cad_job_url"] == f"/modules/{kind}/cad/jobs"
        assert spec["schema"]["additionalProperties"] is False
        assert validated.model_dump(exclude_none=True) == spec["defaults"]


def test_silent_chain_catalog_selection_is_distinct_from_roller_chain_and_requires_completion() -> None:
    module = get_module("silent_chain_sprocket")
    descriptor = module.descriptor()
    assert descriptor["capabilities"] == {"preview": True, "build": True, "inspect": False}
    assert descriptor["subgroup"] == "chain_drives"
    assert descriptor["preview_url"] == "/modules/silent_chain_sprocket/preview"
    assert descriptor["cad_plan_url"] == "/modules/silent_chain_sprocket/cad/plan"
    assert module.request_model.model_validate(module.defaults).model_dump() == module.defaults
    standards = module.spec()["module"]["selection"]["standards"]
    assert [item["value"] for item in standards] == [
        "gost_13552_81_13576_81", "din_8190_8191_open", "asme_b29_2m_open",
    ]
    families = standards[0]["families"]
    assert [item["value"] for item in families] == ["type_1", "type_2"]
    assert [len(item["profiles"]) for item in families] == [17, 8]
    assert families[0]["profiles"][0]["label_ru"] == "ПЗ-1-12,7-26-22,5"
    assert families[1]["profiles"][0]["pitch_mm"] == 25.4
    assert families[1]["profiles"][0]["working_width_mm"] == 57.0
    assert module.request_model.model_validate({"family": "type_2", "designation": "PZ-2-25.4-101-57", "physical_tooth_count": 11, "accuracy_class": 2})
    din = standards[1]
    assert [len(family["profiles"]) for family in din["families"]] == [30, 30]
    assert din["reconstruction"] is True
    assert "secondary table" in din["warning_en"]
    din_profile = din["families"][0]["profiles"][0]
    assert din_profile["source"] == "MDESIGN/INGGO secondary reproduction of DIN 8190"
    assert din_profile["confidence"] == "medium"
    assert module.request_model.model_validate({
        "standard": "din_8190_8191_open", "family": "outer", "designation": "06-015A",
        "physical_tooth_count": 15,
    })
    asme = standards[2]
    assert asme["reconstruction"] is True
    assert "not established" in asme["warning_en"]
    asme_profile = asme["families"][0]["profiles"][0]
    assert asme_profile["designation_available"] is False
    assert module.request_model.model_validate({
        "standard": "asme_b29_2m_open", "family": "pitch_and_guide",
        "designation": "asme-4.7625-side_guide", "physical_tooth_count": 17,
    })
    for invalid in (
        {"designation": "ISO_08B", "physical_tooth_count": 23},
        {"designation": "PZ-1-19.05-74-45", "physical_tooth_count": 11},
        {"family": "type_2", "designation": "PZ-2-25.4-101-57", "physical_tooth_count": 49, "accuracy_class": 1},
        {"standard": "din_8190_8191_open", "family": "outer", "designation": "06-015A", "physical_tooth_count": 14},
        {"standard": "asme_b29_2m_open", "family": "pitch_and_guide", "designation": "asme-6.35-side_guide", "physical_tooth_count": 20},
    ):
        with pytest.raises(ValueError):
            module.request_model.model_validate(invalid)
    with pytest.raises(ValueError, match="Complete construction dimensions"):
        managed_pulley_plan(module.kind, module.defaults)

    gost_preview = preview_module(module.kind, module.defaults)
    assert gost_preview["family"] == "silent_chain_sprocket"
    assert gost_preview["view_mode"] == "end"
    assert gost_preview["secondary_view"]["view_mode"] == "side_section"
    assert len(gost_preview["closed_points"][0]) > 20
    assert gost_preview["closed_points"][0][0] == pytest.approx(gost_preview["closed_points"][0][-1])
    assert gost_preview["preview_window"] == {
        "tooth_gap_count": 3,
        "visible_tooth_count": 2,
        "section_style": "broken_out",
    }
    assert gost_preview["summary"]["calculation_tooth_count"] == 23
    assert gost_preview["summary"]["tooth_width_mm"] == pytest.approx(51.0)
    gost_gap = gost_preview["feature_paths"][0]
    gost_radii = [math.hypot(point[0], point[1]) for point in gost_gap]
    assert min(gost_radii) == pytest.approx(gost_preview["summary"]["root_diameter_mm"] / 2)
    assert max(gost_radii) == pytest.approx(gost_preview["summary"]["outside_diameter_mm"] / 2)
    assert gost_gap[0][0] < 0 < gost_gap[-1][0]
    assert gost_preview["secondary_view"]["guide_grooves_mm"] == [{
        "center_mm": pytest.approx(25.5), "width_mm": 6.0, "depth_mm": pytest.approx(14.2875),
    }]
    assert {item["key"] for item in gost_preview["dimensions"]} == {
        "outside_diameter", "pitch_diameter", "root_diameter",
    }
    assert {item["code"] for item in gost_preview["warning_items"]} == {
        "silent_gost_profile_verified",
    }
    # Independent Table-1 measuring section: catches the former 8.57 mm tooth.
    from geomwright.studio.silent_chain_preview import build_silent_chain_preview
    raw = build_silent_chain_preview(module.defaults)
    angle = math.pi / 23
    flank = raw["geometry"]["working_flank_paths"][1]
    rotated = [[x * math.cos(angle) - y * math.sin(angle),
                x * math.sin(angle) + y * math.cos(angle)] for x, y in flank]
    gamma = math.radians(30 - 360 / 23)
    measuring_y = 7.14 * math.sin(gamma) + 1.905 * math.cos(gamma)
    expected_ty = 19.05 - 2 * (7.14 * math.cos(gamma) - 1.905 * math.sin(gamma))
    cut_y = gost_preview["summary"]["outside_diameter_mm"] / 2 - measuring_y
    a, b = rotated[0], rotated[-1]
    cut_x = a[0] + (b[0] - a[0]) * (cut_y - a[1]) / (b[1] - a[1])
    assert -2 * cut_x == pytest.approx(expected_ty, abs=1e-8)
    drawing = gost_preview["secondary_view"]["drawing"]
    assert drawing["section_polygons"] and drawing["visible_paths"]
    assert {d["symbol"] for d in drawing["dimensions"]} >= {"s₁", "b₃", "h₂", "h₃"}

    gost_type_2 = preview_module(module.kind, {
        "standard": "gost_13552_81_13576_81", "family": "type_2",
        "designation": "PZ-2-25.4-101-57", "physical_tooth_count": 23, "accuracy_class": 1,
    })
    assert gost_type_2["summary"]["calculation_tooth_count"] == 46
    assert gost_type_2["secondary_view"]["row_count"] == 4
    assert gost_type_2["secondary_view"]["row_spacing_mm"] == 18.0
    assert gost_type_2["secondary_view"]["total_width_mm"] == pytest.approx(61.74)
    assert gost_type_2["secondary_view"]["end_round_radius_mm"] == 50.0
    axial = gost_type_2["secondary_view"]
    assert axial["rib_centers_mm"] == pytest.approx([3.87, 21.87, 39.87, 57.87])
    assert axial["relative_rib_phases_deg"] == [0.0] * 4
    assert not any(d["symbol"] == "Δb" for d in axial["drawing"]["dimensions"])
    assert "lower_body_projection_mm" not in axial
    assert max(p[1] for poly in axial["drawing"]["section_polygons"] for p in poly) == pytest.approx(.75 * 25.4)
    from geomwright.studio.silent_chain_axial import build_axial_view
    type2_raw = build_silent_chain_preview({
        "standard": "gost_13552_81_13576_81", "family": "type_2",
        "designation": "PZ-2-25.4-101-57", "physical_tooth_count": 23,
    })
    with pytest.raises(ValueError, match="angular phase"):
        build_axial_view({"standard": "gost_13552_81_13576_81"}, type2_raw["profile"], type2_raw["derived"],
                         {**type2_raw["axial"], "relative_rib_phases_deg": [0, 1, 0, 0]})

    din_preview = preview_module(module.kind, {
        "standard": "din_8190_8191_open", "family": "outer", "designation": "06-015A",
        "physical_tooth_count": 21,
    })
    assert din_preview["summary"]["profile_mechanics"] == "din_shifted_involute"
    assert din_preview["secondary_view"]["total_width_mm"] == pytest.approx(12.0)
    assert din_preview["summary"]["tooth_width_mm"] == pytest.approx(12.0)
    assert "not a conformity claim" in din_preview["warnings"][0]
    assert len(din_preview["closed_points"][0]) > 200

    din_inner = preview_module(module.kind, {
        "standard": "din_8190_8191_open", "family": "inner", "designation": "06-025B",
        "physical_tooth_count": 21,
    })
    assert din_inner["secondary_view"]["axial_layout_status"] == "width_only"
    assert din_inner["secondary_view"]["guide_grooves_mm"] == [{
        "center_mm": pytest.approx(15.4), "width_mm": 4.0, "depth_mm": None,
    }]
    assert {d["symbol"]: d["value"] for d in din_inner["secondary_view"]["drawing"]["dimensions"]}["f₁"] == 3.0
    assert any(item["dashed"] for item in din_preview["tone_paths"])
    assert "root_diameter_mm" not in din_preview["summary"]

    asme_preview = preview_module(module.kind, {
        "standard": "asme_b29_2m_open", "family": "pitch_and_guide",
        "designation": "asme-9.525-side_guide", "physical_tooth_count": 23,
        "face_width_mm": 24.0, "tooth_tip_shape": "square",
    })
    assert asme_preview["summary"]["profile_mechanics"] == "asme_straight_flanks"
    assert asme_preview["secondary_view"]["total_width_mm"] == 24.0
    assert asme_preview["summary"]["outside_diameter_mm"] > 0
    assert len(asme_preview["closed_points"][0]) > 50
    assert "not a conformity claim" in asme_preview["warnings"][0]
    expected_root_center_d = 9.525 * math.sqrt(
        1.515213 + (1 / math.tan(math.pi / 23) - 1.1) ** 2
    )
    asme_raw = build_silent_chain_preview({
        "standard": "asme_b29_2m_open", "designation": "asme-9.525-side_guide",
        "physical_tooth_count": 23, "face_width_mm": 24.0, "tooth_tip_shape": "square",
    })
    assert asme_raw["derived"]["root_arc_center_diameter_mm"] == pytest.approx(expected_root_center_d)
    assert "root_diameter_mm" not in asme_preview["summary"]
    assert asme_raw["derived"]["tip_round_radius_mm"] == pytest.approx(0.15 * 9.525)
    assert asme_preview["summary"]["profile_status"] == "source_profile_with_tool_choice"
    assert asme_preview["summary"]["generator_root_diameter_mm"] > 0
    assert any(item["tone"] == "intake" for item in asme_preview["tone_paths"])
    # Check pin tangency against generated points, not only returned metadata.
    pin_center_y = 9.525 / (2 * math.sin(math.pi / 23)) - 0.0625 * 9.525 / math.sin(math.radians(30 - 180 / 23))
    a, b = asme_raw["geometry"]["working_flank_paths"][1][::len(asme_raw["geometry"]["working_flank_paths"][1]) - 1]
    pin_distance = abs((b[0] - a[0]) * (pin_center_y - a[1]) + (b[1] - a[1]) * a[0]) / math.dist(a, b)
    assert pin_distance == pytest.approx(0.625 * 9.525 / 2, abs=1e-8)
    period = asme_raw["geometry"]["period_path"]
    angle = 2 * math.pi / 23
    x, y = period[0]
    assert period[-1] == pytest.approx([x * math.cos(angle) + y * math.sin(angle), -x * math.sin(angle) + y * math.cos(angle)])

    asme_center = preview_module(module.kind, {
        "standard": "asme_b29_2m_open", "family": "pitch_and_guide",
        "designation": "asme-9.525-center_guide", "physical_tooth_count": 23,
        "face_width_mm": 24.0, "tooth_tip_shape": "round",
    })
    center_groove = asme_center["secondary_view"]["guide_grooves_mm"][0]
    assert center_groove["center_mm"] == pytest.approx(12.0)
    assert center_groove["width_mm"] == 3.2
    assert center_groove["depth_mm"] is None
    assert center_groove["depth_relation"] == ">="
    assert center_groove["minimum_depth_mm"] == pytest.approx(
        (asme_center["summary"]["outside_diameter_mm"] - 9.525 * (1 / math.tan(math.pi / 23) - 1.16)) / 2
    )
    with pytest.raises(ValueError, match="too small to contain"):
        preview_module(module.kind, {
            "standard": "asme_b29_2m_open", "family": "pitch_and_guide",
            "designation": "asme-9.525-center_guide", "physical_tooth_count": 23,
            "face_width_mm": 3.0, "tooth_tip_shape": "round",
        })

    asme_two_center = preview_module(module.kind, {
        "standard": "asme_b29_2m_open", "family": "pitch_and_guide",
        "designation": "asme-9.525-two_center_guide", "physical_tooth_count": 23,
        "face_width_mm": 40.0, "tooth_tip_shape": "round",
    })
    assert [groove["center_mm"] for groove in asme_two_center["secondary_view"]["guide_grooves_mm"]] == pytest.approx([7.3, 32.7])

    asme_round = preview_module("silent_chain_sprocket", {
        "standard": "asme_b29_2m_open", "family": "pitch_and_guide",
        "designation": "asme-9.525-side_guide", "physical_tooth_count": 23,
        "face_width_mm": 24.0, "tooth_tip_shape": "round",
    })
    assert asme_round["feature_paths"] != asme_preview["feature_paths"]
    assert "root_diameter_mm" not in asme_round["summary"]

    asme_3_16 = preview_module("silent_chain_sprocket", {
        "standard": "asme_b29_2m_open", "family": "pitch_and_guide",
        "designation": "asme-4.7625-side_guide", "physical_tooth_count": 23,
        "face_width_mm": 12.0, "tooth_tip_shape": "round",
    })
    assert "root_diameter_mm" not in asme_3_16["summary"]
    assert asme_3_16["summary"]["tooth_tip_shape"] == "round"
    assert "silent_asme_small_pitch_unverified" not in {item["code"] for item in asme_3_16["warning_items"]}
    missing_guides = preview_module("silent_chain_sprocket", {
        "standard": "asme_b29_2m_open", "family": "pitch_and_guide",
        "designation": "asme-4.7625-two_center_guide", "physical_tooth_count": 23,
        "face_width_mm": 20.0, "tooth_tip_shape": "square",
    })
    assert missing_guides["secondary_view"]["drawing"]["status"] == "guide_data_unavailable"
    assert not missing_guides["secondary_view"]["drawing"]["section_polygons"]


def test_silent_chain_source_envelope_and_tool_policy() -> None:
    from geomwright.studio.silent_chain_asme import build_asme_space
    from geomwright.studio.silent_chain_preview import build_silent_chain_preview

    # DIN Table 5, 08 z18: y=.6 gives two measuring teeth, not three.
    din = build_silent_chain_preview({
        "standard": "din_8190_8191_open", "family": "outer", "designation": "08-020A",
        "physical_tooth_count": 18,
    })
    d, geometry, check = din["derived"], din["geometry"], din["diagnostics"]
    assert d["span_tooth_count"] == 2
    assert d["span_measurement_mm"] == pytest.approx(14.95, abs=0.01)
    assert not geometry["partial"] and not geometry["construction_closure_path"]
    assert check["root_join_type"] == "tangent"
    assert check["root_join_position_error_mm"] < 1e-8
    assert check["root_join_tangent_angle_deg"] < 1e-4
    # Figure-3 cutter tip at the space centre: independent root-radius relation.
    assert d["root_diameter_mm"] / 2 == pytest.approx(
        d["pitch_diameter_mm"] / 2 + d["profile_shift_coefficient"] * d["module_mm"]
        - 12.7 / (4 * math.tan(math.pi / 6)) + 1.0,
    )
    assert max(p[1] for p in geometry["root_path"]) > min(p[1] for p in geometry["root_path"])

    # Figure 6 and Table 7: round-tip and over-pin factors at z23.
    asme = build_asme_space({"pitch_mm": 9.525}, 23, "round")
    a, g = asme["updates"], asme["geometry"]
    assert a["outside_diameter_mm"] / 9.525 == pytest.approx(7.356, abs=0.001)
    assert a["over_pins_mm"] / 9.525 == pytest.approx(7.621, abs=0.001)
    assert a["construction_circle_diameter_mm"] == pytest.approx(0.75 * 9.525)
    h = math.pi / 23
    circle = [a["tip_arc_center_diameter_mm"] / 2 * math.sin(h),
              a["tip_arc_center_diameter_mm"] / 2 * math.cos(h)]
    assert all(math.dist(p, circle) == pytest.approx(0.15 * 9.525) for p in g["tooth_tip_path"])
    assert g["tooth_tip_path"] in g["supported_paths"]
    assert g["tool_policy_paths"] and not asme["diagnostics"]["root_policy"]["standard_nominal_root_claim"]
    square = build_asme_space({"pitch_mm": 12.7}, 17, "square")
    assert square["updates"]["outside_diameter_mm"] == pytest.approx(2.649 * 25.4)
    assert all(math.hypot(*point) <= 5.298 * 12.7 / 2 + 1e-9 for point in square["geometry"]["tooth_tip_path"])
    corrected = preview_module("silent_chain_sprocket", {
        "standard": "asme_b29_2m_open", "family": "pitch_and_guide",
        "designation": "asme-12.7-side_guide", "physical_tooth_count": 96,
        "face_width_mm": 24.0, "tooth_tip_shape": "square",
    })
    assert corrected["summary"]["outside_diameter_mm"] == pytest.approx(30.590 * 12.7)
    assert corrected["summary"]["profile_status"] == "source_faces_with_provisional_tip"
    assert "silent_asme_table_transcription" in {w["code"] for w in corrected["warning_items"]}
    provisional = build_asme_space({"pitch_mm": 12.7}, 96, "square")
    assert provisional["updates"]["tip_status"] == "vendor_provisional_square_tip"
    assert provisional["geometry"]["tooth_tip_path"] not in provisional["geometry"]["supported_paths"]
    assert provisional["diagnostics"]["square_construction"]["table_text_factor"] == 30.900
    assert provisional["diagnostics"]["square_construction"]["table_text_status"] == "printed_source_conflict_with_vendor_substitute"
    assert any(p.get("dashed") for p in corrected["tone_paths"])

    # Figure 7: .107p radius and .123p centre drop; .16p is a MAXIMUM RADIUS.
    small = build_asme_space({"pitch_mm": 4.7625, "tool_root_radius_mm": .12 * 4.7625}, 17, "round")
    assert small["updates"]["tip_round_radius_mm"] == pytest.approx(.107 * 4.7625)
    assert small["updates"]["outside_diameter_mm"] == pytest.approx(4.7625 * (1 / math.tan(math.pi / 17) - .032))
    assert small["diagnostics"]["root_policy"]["floor_depth_in_tooth_frame_mm"] >= .597 * 4.7625 - 1e-10
    # Figure 7's .5298p MINIMUM must also hold for the actual policy points,
    # transformed into each neighbouring tooth's frame, not just its metadata.
    h = math.pi / 17
    chord = 4.7625 / (2 * math.tan(h))
    policy_depths = [chord - y * math.cos(h) - abs(x) * math.sin(h)
                     for path in small["geometry"]["tool_policy_paths"] for x, y in path]
    assert min(policy_depths) >= .5298 * 4.7625 - 1e-9
    with pytest.raises(ValueError, match="radius must not exceed"):
        build_asme_space({"pitch_mm": 4.7625, "tool_root_radius_mm": .17 * 4.7625}, 17, "round")

    # Recovered Figure 4 is an independent axial source, not a Ramsey patch.
    request = {"standard": "asme_b29_2m_open", "family": "pitch_and_guide",
               "designation": "asme-31.75-center_guide", "physical_tooth_count": 23,
               "face_width_mm": 24.0, "tooth_tip_shape": "round"}
    ramsey = build_silent_chain_preview(request)
    gb = build_silent_chain_preview({**request, "axial_source": "gb_10855_2016"})
    assert gb["geometry"] == ramsey["geometry"]
    assert ramsey["axial"]["drawing"]["status"] == "guide_data_unavailable"
    axial = gb["axial"]
    assert axial["guide_groove_width_mm"] == 4.57
    assert axial["guide_grooves_mm"][0]["depth_mm"] is None
    drawing = axial["drawing"]
    assert drawing["axial_source_system"] == "gb_10855_2016"
    assert not drawing["outline"] and not drawing["section_polygons"]
    assert {d["symbol"] for d in drawing["dimensions"]} >= {"A", "C max", "F*"}
    a, radius, left = 6.96, 9.14, 12.0 - 4.57 / 2
    entrance = drawing["visible_paths"][1]
    assert entrance[0][0] == pytest.approx(left - radius + math.sqrt(radius**2 - a**2))
    assert all(math.hypot(x - (left - radius), y - a) == pytest.approx(radius)
               for x, y in entrance if y <= a)
    assert max(p[1] for path in drawing["visible_paths"] for p in path) <= a
    with pytest.raises(ValueError, match="rounded guide entrances"):
        build_silent_chain_preview({**request, "face_width_mm": 6.0, "axial_source": "gb_10855_2016"})
    small_gb = build_silent_chain_preview({**request, "designation": "asme-4.7625-center_guide", "axial_source": "gb_10855_2016"})
    assert small_gb["axial"]["guide_groove_width_mm"] == 1.27
    assert next(r for r in small_gb["axial"]["drawing"]["external_references"]
                if "source_pitch_mm" in r)["source_pitch_mm"] == 4.762


def test_silent_chain_explicit_completion_gate_and_geometry() -> None:
    from geomwright.studio.silent_chain_preview import build_silent_chain_preview
    from geomwright.studio.registry import managed_pulley_plan

    def propose(request):
        base = preview_module("silent_chain_sprocket", request)
        assert not base["completion"]["ready_for_cad_planning"]
        assert base["construction_spec"] is None
        choices = {name: f["suggested"] for name, f in base["completion"]["fields"].items()}
        return {**request, **choices}

    gost = {"standard": "gost_13552_81_13576_81", "family": "type_2",
            "designation": "PZ-2-25.4-101-57", "physical_tooth_count": 23, "accuracy_class": 1}
    choices = propose(gost)
    ready = preview_module("silent_chain_sprocket", choices)
    assert ready["completion"]["geometry_complete"]
    assert ready["completion"]["ready_for_cad_planning"]
    assert ready["completion"]["cad_build_available"]
    spec = ready["construction_spec"]
    assert spec["axial_material_outline"][0] == spec["axial_material_outline"][-1]
    assert spec["relative_rib_phases_deg"] == [0.0]*4
    assert spec["inner_rim_diameter_mm"] == 0
    assert spec["blank_policy"] == "solid_to_axis"
    assert max(p[1] for p in spec["axial_material_outline"]) == pytest.approx(spec["outside_diameter_mm"]/2)
    plan = managed_pulley_plan("silent_chain_sprocket", choices)
    assert min(p[k][1] for p in plan["rim_entities"] for k in ("start", "end")) == pytest.approx(0)
    assert ready["summary"]["overall_width_mm"] == pytest.approx(spec["functional_width_mm"])
    assert spec["axial_extent_mm"] == pytest.approx([0.0, spec["functional_width_mm"]])
    assert not any("projection" in name for name in ready["completion"]["fields"])
    assert all(math.dist(a, b) > 1e-9 for a, b in zip(spec["axial_material_outline"], spec["axial_material_outline"][1:]))
    assert not ready["secondary_view"]["drawing"]["break_paths"]
    assert ready["feature_paths"] == preview_module("silent_chain_sprocket", gost)["feature_paths"]
    assert {"construction_mode", "construction_confirmed"}.isdisjoint(get_module("silent_chain_sprocket").request_model.model_json_schema()["properties"])
    missing = preview_module("silent_chain_sprocket", {**choices, "body_depth_mm": None})
    assert missing["completion"]["ready_for_cad_planning"]
    assert not missing["completion"]["fields"]["body_depth_mm"]["required"]
    assert missing["construction_spec"]["axial_material_outline"] == spec["axial_material_outline"]
    cropped = managed_pulley_plan("silent_chain_sprocket", {**choices, "body_depth_mm": .1})
    assert cropped["rim_entities"] == plan["rim_entities"]
    assert cropped["verification"] == plan["verification"]
    source_din = preview_module("silent_chain_sprocket", {
        "standard": "din_8190_8191_open", "family": "outer", "designation": "08-020A",
        "physical_tooth_count": 23})
    assert source_din["completion"]["ready_for_cad_planning"]
    assert source_din["completion"]["missing_fields"] == []

    din = {"standard": "din_8190_8191_open", "family": "inner", "designation": "06-025B", "physical_tooth_count": 21}
    choices = propose(din)
    unresolved = preview_module("silent_chain_sprocket", {**choices, "din_rack_resolution": "unresolved"})
    assert not unresolved["completion"]["ready_for_cad_planning"]
    assert "din_rack_resolution" in unresolved["completion"]["missing_fields"]
    choices.update(din_rack_resolution="keep_height")
    ready = preview_module("silent_chain_sprocket", choices)
    assert ready["completion"]["ready_for_cad_planning"]
    assert ready["construction_spec"]["resolved_dimensions"]["tool_tooth_height_mm"] == 5.519
    assert ready["construction_spec"]["resolved_dimensions"]["tool_tip_radius_mm"] == pytest.approx(9.525/(2*math.tan(math.pi/6))-2-5.519)
    assert any(p["tone"] == "intake" for p in ready["tone_paths"])
    assert ready["construction_spec"]["guide_grooves"][0]["depth_mm"] is not None
    assert ready["construction_spec"]["guide_grooves"][0]["width_mm"] == 3.0

    asme = {"standard": "asme_b29_2m_open", "family": "pitch_and_guide",
            "designation": "asme-31.75-center_guide", "physical_tooth_count": 23,
            "face_width_mm": 160, "tooth_tip_shape": "round", "axial_source": "gb_10855_2016"}
    choices = propose(asme)
    raw = build_silent_chain_preview(choices)
    assert raw["completion"]["ready_for_cad_planning"]
    assert raw["diagnostics"]["root_policy"]["floor_depth_in_tooth_frame_mm"] == pytest.approx(choices["tool_floor_depth_mm"])
    groove = raw["construction_spec"]["guide_grooves"][0]
    assert groove["depth_mm"] == choices["guide_depth_mm"]
    assert groove["bottom_radius_mm"] == pytest.approx(groove["width_mm"]/2)
    with pytest.raises(ValueError, match="maximum guide-diameter"):
        preview_module("silent_chain_sprocket", {**choices, "guide_depth_mm": .1})
    with pytest.raises(ValueError, match="too shallow"):
        preview_module("silent_chain_sprocket", {**choices, "tool_floor_depth_mm": .55*31.75})

    manual = propose({**asme, "axial_source": "ramsey_rp_sc"})
    assert "guide_width_mm" in manual and "entrance_height_mm" in manual
    assert preview_module("silent_chain_sprocket", manual)["completion"]["ready_for_cad_planning"]

    conflict = {**asme, "designation": "asme-12.7-side_guide", "physical_tooth_count": 96,
                "tooth_tip_shape": "square"}
    choices = propose(conflict)
    ready = preview_module("silent_chain_sprocket", choices)
    assert ready["completion"]["ready_for_cad_planning"]
    assert ready["construction_spec"]["user_parameters"]["square_tip_resolution"] == "accept_ramsey"
    custom = {**choices, "square_tip_resolution": "custom_diameter",
               "square_tip_diameter_mm": ready["summary"]["outside_diameter_mm"]-.01}
    assert preview_module("silent_chain_sprocket", custom)["completion"]["ready_for_cad_planning"]


def test_chain_sprocket_exposes_hierarchical_catalog_preview_and_icon() -> None:
    module = get_module("chain_sprocket")
    assert module.descriptor()["capabilities"] == {"preview": True, "build": True, "inspect": False}
    assert module.descriptor()["icon"] == "/static/icons/roller-sprocket.svg"
    assert module.request_model.model_validate(module.defaults).model_dump() == module.defaults
    assert "face_width" not in module.spec()["schema"]["properties"]
    assert module.spec()["schema"]["properties"]["gost_profile_variant"]["enum"] == ["offset", "non_offset"]
    selection = module.spec()["module"]["selection"]
    assert [item["value"] for item in selection["standards"]] == ["iso_606", "gost_13568", "gost_21834"]
    assert [item["value"] for item in selection["standards"][0]["families"]] == [
        "iso_a_1", "iso_a_2", "iso_a_3", "iso_b_1", "iso_b_2", "iso_b_3",
    ]
    assert [item["value"] for item in selection["standards"][1]["families"]] == [
        "pr_1", "pr_2", "pr_3", "pr_4", "pri_1", "pv_1", "pv_2",
    ]
    assert [item["value"] for item in selection["standards"][2]["families"]] == [
        "np_1", "np_2", "np_3", "np_4", "np_6", "np_8",
        "tp_1", "tp_2", "tp_3", "tp_4", "tp_6", "tp_8",
    ]
    assert selection["standards"][1]["label_ru"] == "ГОСТ 13568-2017"
    assert selection["standards"][1]["label_en"] == "GOST 13568-2017"
    assert selection["standards"][1]["families"][0]["label_ru"] == "ПР"
    assert selection["standards"][1]["families"][0]["label_en"] == "PR"
    assert selection["standards"][0]["families"][1]["label_ru"] == "A-2"
    assert selection["standards"][0]["families"][1]["label_en"] == "A-2"
    assert selection["standards"][2]["available"] is True
    pv = selection["standards"][1]["families"][6]
    assert pv["profiles"][0]["chain_type"] == "bush"
    assert pv["profiles"][0]["nominal_row_count"] == 2

    roller = preview_module("chain_sprocket", module.defaults)
    bush = preview_module("chain_sprocket", {**module.defaults, "chain_type": "bush"})

    assert roller["family"] == "chain_sprocket"
    assert roller["secondary_view"] is None
    multi = preview_module("chain_sprocket", {**module.defaults, "designation": "ISO_08B_3", "row_count": 3})["secondary_view"]
    assert multi["row_count"] == 3
    assert multi["tooth_width_mm"] == pytest.approx(0.90 * 7.75 - 0.15)
    assert multi["row_spacing_mm"] == 13.92
    assert multi["total_width_mm"] == pytest.approx(2 * 13.92 + multi["tooth_width_mm"])
    ansi_a = preview_module("chain_sprocket", {**module.defaults, "designation": "ISO_50A_2", "row_count": 2})["secondary_view"]
    assert ansi_a["row_spacing_mm"] == pytest.approx(0.713 * 25.4)
    assert ansi_a["total_width_mm"] > ansi_a["row_spacing_mm"]
    assert ansi_a["axial_layout_status"] == "dimensioned"
    assert roller["summary"]["profile_family"] == "iso_b"
    assert roller["summary"]["chain_type"] == "roller"
    assert bush["summary"]["chain_type"] == "bush"
    assert roller["summary"]["pitch_diameter_mm"] == pytest.approx(12.7 / math.sin(math.pi / 19))
    assert roller["summary"]["standard"] == "iso_606"
    assert len(roller["closed_points"][0]) > 20
    assert len(roller["feature_paths"]) == 1
    assert len(roller["feature_paths"][0]) > 20
    assert {item["key"] for item in roller["dimensions"]} == {
        "pitch_diameter", "outside_diameter", "root_diameter",
    }
    assert all(item["orientation"] == "radial" for item in roller["dimensions"])
    for item in roller["dimensions"]:
        assert item["start"][0] * item["end"][1] - item["start"][1] * item["end"][0] == pytest.approx(0.0)
    assert len(roller["closed_points"]) == 1
    assert roller["closed_points"][0][0] == roller["closed_points"][0][-1]
    assert roller["preview_window"] == {
        "tooth_gap_count": 3,
        "visible_tooth_count": 2,
        "section_style": "broken_out",
    }
    assert {item["key"] for item in roller["reference_paths"]} == {"pitch_circle", "outside_circle"}
    one_gap = preview_chain_sprocket(
        designation="ISO_08B",
        chain_type="roller",
        tooth_count=19,
    )["geometry"]["profile_path"]
    section_profile = roller["feature_paths"][0]
    assert len(section_profile) >= 3 * len(one_gap) - 2
    assert any(
        section_profile[index:index + len(one_gap)] == one_gap
        for index in range(len(section_profile) - len(one_gap) + 1)
    )
    assert min(point[1] for point in roller["guide_paths"][0]) < roller["summary"]["root_diameter_mm"] / 2.0
    assert {item["code"] for item in roller["warning_items"]} == {
        "chain_profile_standard_scope",
        "chain_multirow_axial_preview_pending",
    }

    gost = preview_module(
        "chain_sprocket",
        {"designation": "GOST_PR_12_7_18_2", "chain_type": "roller", "tooth_count": 19},
    )
    assert gost["summary"]["standard"] == "gost_13568_2017"
    assert gost["summary"]["designation"] == "GOST_PR_12_7_18_2"
    assert gost["summary"]["gost_profile_variant"] == "offset"
    assert gost["summary"]["tooth_gap_center_offset_mm"] == pytest.approx(0.03 * 12.7)

    gost_non_offset = preview_module(
        "chain_sprocket",
        {
            "designation": "GOST_PR_12_7_18_2",
            "chain_type": "roller",
            "tooth_count": 19,
            "gost_profile_variant": "non_offset",
        },
    )
    assert gost_non_offset["summary"]["gost_profile_variant"] == "non_offset"
    assert gost_non_offset["summary"]["tooth_gap_center_offset_mm"] == 0.0
    assert roller["summary"]["gost_profile_variant"] == "offset"
    assert roller["summary"]["tooth_gap_center_offset_mm"] == pytest.approx(0.03 * 12.7)
    assert roller["summary"]["profile_construction"] == "kompas_native_gost_591_offset"
    seating_radius = 0.5025 * 8.51 + 0.05
    assert roller["summary"]["roller_seating_radius_mm"] == pytest.approx(seating_radius)
    assert roller["summary"]["tooth_flank_radius_mm"] == pytest.approx(0.8 * 8.51 + seating_radius)

    duplex = preview_module(
        "chain_sprocket",
        {"designation": "ISO_08B", "chain_type": "roller", "tooth_count": 19, "row_count": 2},
    )
    assert duplex["summary"]["row_count"] == 2
    assert duplex["request"]["row_count"] == 2


def test_chain_tooth_profile_uses_native_detail_and_gost_half_offsets_for_iso_and_gost() -> None:
    pitch = 12.7
    roller_diameter = 8.51
    tooth_count = 19
    expected_pitch_diameter = pitch / math.sin(math.pi / tooth_count)
    expected_outside_diameter = pitch * (0.480 + 1.0 / math.tan(math.pi / tooth_count))
    expected_seating_radius = 0.5025 * roller_diameter + 0.05
    expected_flank_radius = 0.8 * roller_diameter + expected_seating_radius
    beta = math.radians(18.0 - 56.0 / tooth_count)
    phi = math.radians(17.0 - 64.0 / tooth_count)
    expected_secondary_radius = roller_diameter * (
        1.24 * math.cos(phi) + 0.8 * math.cos(beta) - 1.3025
    ) - 0.05

    for variant in ("offset", "non_offset"):
        preview = preview_chain_sprocket(
            designation="GOST_PR_12_7_18_2",
            chain_type="roller",
            tooth_count=tooth_count,
            gost_profile_variant=variant,
        )
        derived = preview["derived"]
        fillets = preview["geometry"]["fillets"]
        right_seat = next(item for item in fillets if item["kind"] == "roller_seat" and item["side"] == "right")
        left_seat = next(item for item in fillets if item["kind"] == "roller_seat" and item["side"] == "left")
        right_flank = next(item for item in fillets if item["kind"] == "tooth_flank" and item["side"] == "right")
        left_flank = next(item for item in fillets if item["kind"] == "tooth_flank" and item["side"] == "left")
        right_secondary = next(item for item in fillets if item["kind"] == "secondary_flank" and item["side"] == "right")
        left_secondary = next(item for item in fillets if item["kind"] == "secondary_flank" and item["side"] == "left")
        contact = preview["geometry"]["tangent_points"]["right_seating_to_flank"]
        flank_tangent = preview["geometry"]["tangent_points"]["right_flank_to_tip"]
        secondary_tangent = preview["geometry"]["tangent_points"]["right_flank_to_secondary"]
        entities = preview["geometry"]["cad_entities"]

        assert derived["pitch_diameter"] == pytest.approx(expected_pitch_diameter)
        assert derived["outside_diameter"] == pytest.approx(expected_outside_diameter)
        assert derived["root_diameter"] == pytest.approx(expected_pitch_diameter - 2 * expected_seating_radius)
        assert right_seat["radius"] == pytest.approx(expected_seating_radius)
        assert right_seat["center"][1] == pytest.approx(expected_pitch_diameter / 2.0)
        assert left_seat["center"][1] == pytest.approx(expected_pitch_diameter / 2.0)
        assert right_flank["radius"] == pytest.approx(expected_flank_radius)
        assert math.dist(right_seat["center"], contact) == pytest.approx(right_seat["radius"])
        assert math.dist(right_flank["center"], contact) == pytest.approx(right_flank["radius"])
        assert math.dist(right_flank["center"], flank_tangent) == pytest.approx(right_flank["radius"])
        assert math.dist(right_secondary["center"], secondary_tangent) == pytest.approx(right_secondary["radius"])
        assert right_secondary["radius"] == pytest.approx(expected_secondary_radius)
        assert right_secondary["center"][0] - right_seat["center"][0] == pytest.approx(
            1.24 * roller_diameter * math.cos(math.pi / tooth_count)
        )
        assert right_secondary["center"][1] - right_seat["center"][1] == pytest.approx(
            -1.24 * roller_diameter * math.sin(math.pi / tooth_count)
        )
        assert left_flank["center"][0] == pytest.approx(-right_flank["center"][0])
        assert left_secondary["center"][0] == pytest.approx(-right_secondary["center"][0])
        assert len(entities) == (12 if variant == "offset" else 11)
        assert [entity["kind"] for entity in entities].count("arc") == 6
        assert [entity["kind"] for entity in entities].count("segment") == (6 if variant == "offset" else 5)
        bottoms = [entity for entity in entities if entity["id"] == "roller_seat_bottom"]
        if variant == "offset":
            bottom = bottoms[0]
            assert math.dist(bottom["start"], bottom["end"]) == pytest.approx(0.03 * pitch)
            assert bottom["start"][1] == pytest.approx(bottom["end"][1])
            for side, point in ((left_seat, bottom["start"]), (right_seat, bottom["end"])):
                assert point[0] == pytest.approx(side["center"][0])
                assert point[1] == pytest.approx(side["center"][1] - side["radius"])
        else:
            assert not bottoms
        assert all(
            math.dist(left["end"], right["start"]) <= 1e-10
            for left, right in zip(entities, entities[1:] + entities[:1])
        )
        right_tip = preview["geometry"]["profile_path"][-1]
        assert math.hypot(*right_tip) > math.hypot(*secondary_tangent)
        assert math.atan2(right_tip[0], right_tip[1]) < math.pi / tooth_count
        profile_path = preview["geometry"]["profile_path"]
        right_branch_radii = [math.hypot(*point) for point in profile_path[len(profile_path) // 2 :]]
        assert all(
            next_radius > radius
            for radius, next_radius in zip(right_branch_radii, right_branch_radii[1:])
        )
        assert preview["geometry"]["outline"][0] == preview["geometry"]["outline"][-1]
        expected_offset = 0.03 * pitch if variant == "offset" else 0.0
        assert right_seat["center"][0] == pytest.approx(expected_offset / 2.0)
        assert left_seat["center"][0] == pytest.approx(-expected_offset / 2.0)
        assert right_seat["center"][0] - left_seat["center"][0] == pytest.approx(expected_offset)

    iso_offset = preview_chain_sprocket(
        designation="ISO_08B",
        chain_type="roller",
        tooth_count=tooth_count,
        gost_profile_variant="offset",
    )
    iso_non_offset = preview_chain_sprocket(
        designation="ISO_08B",
        chain_type="roller",
        tooth_count=tooth_count,
        gost_profile_variant="non_offset",
    )
    assert iso_offset["gost_profile_variant"] == "offset"
    assert iso_non_offset["gost_profile_variant"] == "non_offset"
    assert iso_offset["derived"]["tooth_gap_center_offset_mm"] == pytest.approx(0.03 * pitch)
    assert iso_non_offset["derived"]["tooth_gap_center_offset_mm"] == 0.0
    low_tooth_gost = preview_chain_sprocket(
        designation="GOST_PR_12_7_18_2",
        chain_type="roller",
        tooth_count=6,
        gost_profile_variant="non_offset",
    )
    assert any(item["kind"] == "secondary_flank" for item in low_tooth_gost["geometry"]["fillets"])

    assert iso_non_offset["derived"]["standard_parameters"]["standard"].startswith("ISO 606")
    assert iso_non_offset["derived"]["standard_parameters"]["construction"] == (
        "kompas_native_gost_591_non_offset"
    )


def test_chain_catalog_keeps_iso_dimensions_and_gost_tooth_strategy_separate() -> None:
    catalog = list_chain_profiles()
    families = {item["profile_family"]: item for item in catalog["profile_families"]}

    assert catalog["profile_count"] == 215
    assert {families[family]["designation_count"] for family in ("pr", "pri", "pv")} == {36, 4, 3}
    assert families["np"]["designation_count"] == families["tp"]["designation_count"] == 37
    assert families["iso_a"]["cad_strategy"] == "kompas_gost_591_11_entity_tooth_gap"
    assert families["iso_b"]["cad_strategy"] == "kompas_gost_591_11_entity_tooth_gap"
    assert families["iso_a"]["equivalence_group"] == families["iso_b"]["equivalence_group"]
    for family in ("pr", "pri", "pv", "np", "tp"):
        assert families[family]["cad_strategy"] == "kompas_gost_591_11_entity_tooth_gap"
        assert families[family]["equivalence_group"] != families["iso_b"]["equivalence_group"]
    assert families["iso_a"]["engagement_diameter_to_pitch"]["min"] < families["iso_a"]["engagement_diameter_to_pitch"]["max"]
    profiles = {item["designation"]: item for item in catalog["profiles"]}
    assert profiles["ISO_08A"]["outside_diameter"] == 7.95
    assert profiles["ISO_08A"]["inner_width"] == 7.85
    assert profiles["ISO_08A_2"]["dimensions_standard"] == "ISO 606:1994"
    assert profiles["ISO_40A"]["outside_diameter"] == 7.92
    assert profiles["ISO_40A_3"]["row_spacing"] == pytest.approx(0.566 * 25.4)
    assert profiles["ISO_40A_3"]["plate_height"] == pytest.approx(0.469 * 25.4)
    assert profiles["ISO_10A_3"]["pitch"] == 15.875
    assert profiles["ISO_10A_3"]["inner_width"] == 9.4
    assert profiles["ISO_10A_3"]["row_spacing"] == 18.11
    assert profiles["ISO_12B_2"]["plate_height"] == 16.13
    assert profiles["ISO_16A_2"]["plate_height"] == 24.13
    assert profiles["ISO_28B_2"]["plate_height"] == 37.08
    iso_selection = get_module("chain_sprocket").spec()["module"]["selection"]["standards"][0]
    a3 = next(f for f in iso_selection["families"] if f["value"] == "iso_a_3")
    assert any(p["value"] == "ISO_10A_3" and p["label_ru"] == "10A-3" for p in a3["profiles"])
    iso_a = preview_chain_sprocket(designation="ISO_08A", chain_type="roller", tooth_count=25)
    assert iso_a["derived"]["standard_parameters"]["outside_coefficient"] == 0.532
    assert iso_a["derived"]["outside_diameter"] == pytest.approx(12.7 * (0.532 + 1 / math.tan(math.pi / 25)))
    # One catalog representative per Table 1 interval; ISO_05B also covers lambda=1.60.
    for designation, coefficient in (("ISO_08B", 0.480), ("ISO_08A", 0.532),
                                     ("ISO_05B", 0.555), ("ISO_140A", 0.575), ("ISO_25A", 0.565)):
        preview = preview_chain_sprocket(
            designation=designation, chain_type=profiles[designation]["chain_type"], tooth_count=25,
        )
        assert preview["derived"]["standard_parameters"]["outside_coefficient"] == coefficient
    for label in ("ПРИ-78,1-360", "ПРИ-103,2-650", "ПРИ-140-1200"):
        designation = next(key for key, item in profiles.items() if item["label"] == label)
        pri_plan = managed_pulley_plan("chain_sprocket", {
            "designation": designation, "chain_type": "roller", "tooth_count": 90,
        })
        parameters = pri_plan["profile_preview"]["derived"]["standard_parameters"]
        assert parameters["extended_lambda_policy"] == "native_kompas_pri_k_0_532"
        assert parameters["outside_coefficient"] == pytest.approx(0.532)
        assert parameters["outside_coefficient_source"] == "native_kompas_pri_compatibility"
        assert parameters["construction"] == "kompas_native_pri_compatibility_offset"
        assert parameters["standard"].endswith("native KOMPAS PRI compatibility")
        assert parameters["tooth_tip_radial_clearance"] > 0.0
        geometry = pri_plan["profile_preview"]["geometry"]
        outside_radius = pri_plan["profile_preview"]["derived"]["outside_diameter"] / 2.0
        right_outside = geometry["tangent_points"]["right_outside"]
        right_head = next(item for item in geometry["cad_entities"] if item["id"] == "tooth_head_right")
        assert math.hypot(*right_outside) == pytest.approx(outside_radius)
        assert math.hypot(*right_head["end"]) == pytest.approx(outside_radius)
        assert math.dist(right_head["center"], right_head["end"]) == pytest.approx(right_head["radius"])
    pri_360 = next(key for key, item in profiles.items() if item["label"] == "ПРИ-78,1-360")
    for tooth_count, native_diameter in (
        (25, 659.77), (40, 1033.90), (60, 1531.79), (90, 2278.04), (120, 3024.07),
    ):
        pri_360_preview = preview_chain_sprocket(
            designation=pri_360, chain_type="roller", tooth_count=tooth_count,
        )
        assert pri_360_preview["derived"]["outside_diameter"] == pytest.approx(
            native_diameter, abs=0.005
        )
    pri_360_studio = preview_module(
        "chain_sprocket",
        {"designation": pri_360, "chain_type": "roller", "tooth_count": 90},
    )
    assert pri_360_studio["warning_items"][-1]["code"] == "chain_pri_extended_profile"
    pri_360_studio_radius = pri_360_studio["summary"]["outside_diameter_mm"] / 2.0
    assert max(
        math.hypot(*point) for point in pri_360_studio["feature_paths"][0]
    ) == pytest.approx(pri_360_studio_radius)
    supported_pri = next(key for key, item in profiles.items() if item["label"] == "ПРИ-78,1-400")
    supported_pri_preview = preview_chain_sprocket(
        designation=supported_pri, chain_type="roller", tooth_count=60,
    )
    assert supported_pri_preview["success"]
    assert supported_pri_preview["derived"]["outside_diameter"] == pytest.approx(1534.36, abs=0.005)
    assert supported_pri_preview["derived"]["standard_parameters"]["outside_coefficient"] == 0.565
    assert supported_pri_preview["derived"]["standard_parameters"]["tooth_tip_radial_clearance"] > 0.0
    for label, native_diameter in (
        ("ПРИ-103,2-650", 2024.08),
        ("ПРИ-140-1200", 2745.84),
    ):
        designation = next(key for key, item in profiles.items() if item["label"] == label)
        preview = preview_chain_sprocket(
            designation=designation, chain_type="roller", tooth_count=60,
        )
        assert preview["derived"]["outside_diameter"] == pytest.approx(
            native_diameter, abs=0.005
        )
    iso_a_plan = managed_pulley_plan("chain_sprocket", {
        "designation": "ISO_08A", "chain_type": "roller", "tooth_count": 25,
    })
    assert iso_a_plan["geometry"]["outside_radius"] == pytest.approx(iso_a["derived"]["outside_diameter"] / 2)
    special = {
        profile["label"]: profile
        for profile in catalog["profiles"]
        if profile.get("kompas_catalog_source") == "Таблица ГВС 005-2015"
    }
    assert set(special) == {"081", "082", "083", "084", "085"}
    assert special["082"]["inner_width"] == pytest.approx(2.38)
    assert special["085"]["outside_diameter"] == pytest.approx(7.77)
    assert all(profile["selection_family"] == "iso_b_1" for profile in special.values())
    assert {
        profile["standard"]
        for profile in catalog["profiles"]
        if profile["profile_family"] in ("np", "tp")
    } == {"gost_21834_87"}


def test_chain_sprocket_cad_plan_uses_true_arcs_and_rejects_unmodelled_multirow_layout() -> None:
    plan = managed_pulley_plan(
        "chain_sprocket",
        {
            "designation": "ISO_08B",
            "chain_type": "roller",
            "tooth_count": 19,
            "row_count": 1,
            "gost_profile_variant": "offset",
        },
    )

    assert plan["stage"] == "managed_chain_sprocket_plan"
    assert plan["ownership"]["schema"] == "geomwright.managed_chain_sprocket"
    assert plan["geometry"]["face_width"] == pytest.approx(0.93 * 7.75)
    rounding = plan["axial_rounding"]
    assert rounding["r3"] == pytest.approx(1.7 * 8.51)
    assert rounding["h3"] == pytest.approx(0.8 * 8.51)
    assert rounding["axial_interval"] == [-plan["geometry"]["face_width"], 0.0]
    left, right = rounding["ends"]
    left_arc = left["bridge_preview"]["geometry"]["profile_entities"][0]
    right_arc = right["bridge_preview"]["geometry"]["profile_entities"][0]
    assert left_arc["start"][0] == 0.0
    assert right_arc["start"][0] == pytest.approx(-rounding["face_width"])
    assert left_arc["end"][0] < left_arc["start"][0]
    assert right_arc["end"][0] > right_arc["start"][0]
    assert left_arc["end"][0] + right_arc["end"][0] == pytest.approx(-rounding["face_width"])
    assert left_arc["direction"] is False and right_arc["direction"] is True
    for end in rounding["ends"]:
        axial_entities = end["bridge_preview"]["geometry"]["profile_entities"]
        arc = axial_entities[0]
        assert math.dist(arc["center"], arc["start"]) == pytest.approx(rounding["r3"])
        assert math.dist(arc["center"], arc["end"]) == pytest.approx(rounding["r3"])
        assert arc["start"][1] == pytest.approx(rounding["outside_radius"] - rounding["h3"])
        assert arc["end"][1] == pytest.approx(rounding["outside_radius"])
        assert all(a["end"] == b["start"] for a, b in zip(axial_entities, axial_entities[1:] + axial_entities[:1]))
        assert end["params"]["require_fully_defined"] is True
        assert end["params"]["sketch"]["parameterization_order"] == "constraints_first"
    entities = plan["geometry"]["tooth_space_entities"]
    assert len(entities) == 12
    assert [entity["kind"] for entity in entities].count("arc") == 6
    assert [entity["kind"] for entity in entities].count("segment") == 6
    closure = next(entity for entity in entities if entity["id"] == "outside_closure")
    assert closure["start"][1] == pytest.approx(plan["geometry"]["outside_radius"] + 0.5)
    assert closure["end"][1] == pytest.approx(plan["geometry"]["outside_radius"] + 0.5)
    assert all(
        math.dist(left["end"], right["start"]) <= 1e-10
        for left, right in zip(entities, entities[1:])
    )
    assert math.dist(entities[-1]["end"], entities[0]["start"]) <= 1e-10
    operations = plan["workflow"]["params"]["operations"]
    assert [operation["scenario"] for operation in operations] == [
        "cylindrical_blank", "numeric_profile_sketch", "cut_extrusion", "circular_pattern",
    ]
    sketch_params = operations[1]["params"]
    assert sketch_params["parameterize"] is True
    assert sketch_params["require_fully_defined"] is True
    assert sketch_params["sketch_options"]["require_exact_counts"] is True
    assert sketch_params["sketch_options"]["expected_constraint_count"] == 41
    assert sketch_params["sketch_options"]["expected_dimension_count"] == 17
    assert sketch_params["post_build_constraints"] == [{
        "kind": "point_on_curve",
        "target": "outside_overshoot_right",
        "index": 0,
        "partner": "chain_outside_datum",
    }]
    assert operations[2]["params"]["require_fully_defined"] is True
    assert operations[-1]["params"]["parameterize"] is True
    assert operations[-1]["params"]["count_variable"] == "CH_Z"
    assert operations[-1]["params"]["angle_step_variable"] == "CH_STEP"
    dimensions = {item["name"]: item for item in plan["parameterization"]["dimensions"]}
    assert dimensions["CH_E_DIM"]["variable_name"] == "CH_E"
    assert {
        "CH_RP_DIM", "CH_RA_DIM", "CH_AXIS_DIM",
        "CH_HSPAN_DIM", "CH_HX_DIM", "CH_HY_DIM",
        "CH_FSPAN_DIM", "CH_FX_DIM", "CH_FY_DIM",
        "CH_R_DIM", "CH_R1_DIM", "CH_R2_DIM",
        "CH_E_DIM", "CH_E2_DIM", "CH_CO_DIM", "CH_CW_DIM", "CH_SCY_DIM",
    } == set(dimensions)
    assert dimensions["CH_R_DIM"]["target"] == "roller_seat_right"
    assert dimensions["CH_R1_DIM"]["target"] == "tooth_flank_right"
    assert dimensions["CH_R2_DIM"]["target"] == "tooth_head_right"
    assert dimensions["CH_CW_DIM"]["kind"] == "line_length"
    assert dimensions["CH_CW_DIM"]["target"] == "outside_closure"
    assert dimensions["CH_CW_DIM"]["driving"] is False
    assert "variable_name" not in dimensions["CH_CW_DIM"]
    assert dimensions["CH_CW_DIM"]["value"] == pytest.approx(
        abs(closure["end"][0] - closure["start"][0])
    )
    constraints = plan["parameterization"]["constraints"]
    assert sum(item["kind"] == "tangent" for item in constraints) == 8
    assert {"kind": "horizontal", "target": "roller_seat_bottom"} in constraints
    assert not any(item["target"] == "roller_seat_bottom" for item in dimensions.values())
    assert sum(item["kind"] == "equal_radius" for item in constraints) == 3
    assert sum(item["kind"] == "point_on_curve" for item in constraints) == 0
    assert {"kind": "horizontal", "target": "outside_closure"} in constraints
    assert "chain_closure_datum" not in {
        item["id"] for item in plan["geometry"]["auxiliary_entities"]
    }
    variables = {item["name"]: item for item in plan["parameterization"]["variables"]}
    assert variables["CH_R"]["expression"] == "0.5025 * CH_DR + 0.05"
    assert variables["CH_R1"]["expression"] == "0.8 * CH_DR + CH_R"
    assert variables["CH_R2"]["expression"].endswith("* CH_DR - 0.05")
    assert variables["CH_CW"]["value"] > 0.0
    assert {"CH_E", "CH_R", "CH_R1", "CH_R2", "CH_CW", "CH_STEP"}.issubset(
        plan["ownership"]["required_variables"]
    )

    gost_plan = build_chain_sprocket_plan(
        designation="GOST_PR_12_7_18_2",
        chain_type="roller",
        tooth_count=19,
        row_count=1,
    )
    assert gost_plan["geometry"]["face_width"] == pytest.approx(0.93 * 7.75 - 0.15)
    assert len(gost_plan["geometry"]["tooth_space_entities"]) == 12

    narrow_plan = build_chain_sprocket_plan(designation="ISO_081", chain_type="roller", tooth_count=19)
    narrow = narrow_plan["axial_rounding"]
    assert narrow_plan["geometry"]["face_width"] == pytest.approx(2.919)
    assert narrow["r3"] > 1.7 * 7.75
    assert narrow["h3"] == pytest.approx(0.8 * 7.75)
    assert narrow["tip_land_width"] == pytest.approx(0.2 * 2.919)
    assert narrow["radius_selection"] == "width_fitted_20_percent_land"
    assert narrow["r3"] == pytest.approx((6.2 ** 2 + (0.4 * 2.919) ** 2) / (0.8 * 2.919))
    assert rounding["radius_selection"] == "minimum_1.7_engagement_diameter"
    # Continuous transition from the fitted radius to the normative minimum.
    for width in (0.5 * 7.75 - 1e-5, 0.5 * 7.75, 0.5 * 7.75 + 1e-5):
        boundary = build_chain_sprocket_plan(
            designation="ISO_081", chain_type="roller", tooth_count=19, face_width=width,
        )["axial_rounding"]
        assert boundary["r3"] >= boundary["minimum_radius"] - 1e-10
        assert boundary["tip_land_width"] >= 0.2 * width - 1e-10
        assert boundary["r3"] == pytest.approx(1.7 * 7.75, abs=1e-4)
    with pytest.raises(ValueError, match="simplex-only"):
        preview_chain_sprocket(
            designation="ISO_081", chain_type="roller", tooth_count=19, row_count=2,
        )
    native_preview = preview_chain_sprocket(
        designation="ISO_081",
        chain_type="roller",
        tooth_count=19,
        row_count=1,
        gost_profile_variant="non_offset",
    )
    native_parameters = native_preview["derived"]["standard_parameters"]
    native_entities = native_preview["geometry"]["cad_entities"]
    assert native_preview["profile"]["label"] == "081"
    assert native_preview["profile"]["outside_diameter"] == pytest.approx(7.75)
    assert native_preview["profile"]["inner_width"] == pytest.approx(3.3)
    assert native_preview["derived"]["pitch_diameter"] == pytest.approx(77.1592795263731)
    assert native_preview["derived"]["outside_diameter"] == pytest.approx(83.15542752026585)
    assert native_parameters["construction"] == "kompas_native_gost_591_non_offset"
    assert native_parameters["seating_radius"] == pytest.approx(3.944375)
    assert native_parameters["flank_radius"] == pytest.approx(10.144375)
    assert native_parameters["secondary_radius"] == pytest.approx(5.182186887975166)
    assert native_parameters["fg_distance"] == pytest.approx(0.6546848419970204)
    assert len(native_entities) == 11
    assert [entity["kind"] for entity in native_entities].count("arc") == 6
    assert [entity["kind"] for entity in native_entities].count("segment") == 5
    assert all(
        math.dist(left["end"], right["start"]) <= 1e-10
        for left, right in zip(native_entities, native_entities[1:] + native_entities[:1])
    )
    assert native_entities[2]["start"] == pytest.approx([-4.455519529261, 38.429318275896])
    assert math.hypot(*native_entities[7]["end"]) == pytest.approx(
        native_preview["derived"]["outside_diameter"] / 2.0
    )
    native_iso_plan = build_chain_sprocket_plan(
        designation="ISO_08B", chain_type="roller", tooth_count=19, gost_profile_variant="non_offset",
    )
    native_sketch = native_iso_plan["workflow"]["params"]["operations"][1]["params"]
    assert native_sketch["sketch_options"]["expected_constraint_count"] == 35
    assert native_sketch["sketch_options"]["expected_dimension_count"] == 14
    assert "CH_E_DIM" not in {
        item["name"] for item in native_iso_plan["parameterization"]["dimensions"]
    }
    assert "chain_seat_center_span" not in {
        item["id"] for item in native_iso_plan["geometry"]["auxiliary_entities"]
    }

    multi = build_chain_sprocket_plan(designation="ISO_08B_2", chain_type="roller", tooth_count=25, row_count=2)
    layout = multi["row_layout"]
    assert layout["enabled"]
    assert layout["tooth_width"] == pytest.approx(6.825)
    assert layout["row_spacing"] == pytest.approx(13.92)
    assert layout["total_width"] == pytest.approx(20.745)
    assert layout["connector_diameter"] == 85.0
    junction = layout["junction_fillet"]
    assert junction["radius"] == 1.6
    assert junction["expected_edge_count"] == 2
    assert [edge["point"][0] for edge in junction["edge_probe_points"]] == pytest.approx([-6.825, -13.92])
    assert all(math.hypot(*edge["point"][1:]) == pytest.approx(42.5) for edge in junction["edge_probe_points"])
    assert junction["expected_added_volume_cm3"] > 0.0
    assert layout["row_offsets"] == [0.0, -13.92]
    assert multi["workflow"]["params"]["operations"][0]["params"]["width"] == layout["tooth_width"]
    assert layout["connector"]["params"]["require_fully_defined"]
    assert layout["expected_gap_volume_cm3"] == pytest.approx(math.pi * 42.5**2 * (13.92 - 6.825) / 1000)
    triple = build_chain_sprocket_plan(designation="ISO_08A_3", chain_type="roller", tooth_count=25, row_count=3)
    assert triple["row_layout"]["row_offsets"] == [0.0, -14.38, -28.76]
    assert triple["row_layout"]["junction_fillet"]["expected_edge_count"] == 4
    assert triple["geometry"]["total_face_width"] == pytest.approx(2 * 14.38 + 0.9 * 7.85 - 0.15)
    new_a = build_chain_sprocket_plan(designation="ISO_10A_3", chain_type="roller", tooth_count=25, row_count=3)
    assert new_a["geometry"]["total_face_width"] == pytest.approx(44.53)
    assert new_a["row_layout"]["row_spacing"] == 18.11
    profiles_by_label = {p["label"]: p for p in list_chain_profiles()["profiles"]}
    for label, count, spacing, height, r4 in (
        ("2ПВ-9,525-20", 2, 10.75, 9.85, 1.6),
        ("4ПР-38,1-508", 4, 45.44, 36.2, 2.5),
    ):
        profile = profiles_by_label[label]
        plan = build_chain_sprocket_plan(designation=profile["designation"], chain_type=profile["chain_type"], tooth_count=25, row_count=count)
        assert plan["row_layout"]["row_spacing"] == spacing
        assert plan["row_layout"]["plate_height"] == height
        assert plan["row_layout"]["junction_fillet"]["radius"] == r4
        assert plan["row_layout"]["junction_fillet"]["expected_edge_count"] == 2 * (count - 1)
    ansi_plan = build_chain_sprocket_plan(
        designation="ISO_50A_2",
        chain_type="roller",
        tooth_count=19,
        row_count=2,
    )
    assert ansi_plan["row_layout"]["row_spacing"] == pytest.approx(0.713 * 25.4)
    assert ansi_plan["row_layout"]["plate_height"] == pytest.approx(0.585 * 25.4)
    with pytest.raises(ValueError, match="row_count must match"):
        build_chain_sprocket_plan(designation="ISO_08B_3", chain_type="roller", tooth_count=25, row_count=2)
    with pytest.raises(ValueError, match="row_spacing must exceed"):
        build_chain_sprocket_plan(designation="ISO_08B_2", chain_type="roller", tooth_count=25, row_count=2, face_width=14.0)
    fitted = build_chain_sprocket_plan(
        designation="ISO_08B_2", chain_type="roller", tooth_count=25, row_count=2, face_width=12.0,
    )["row_layout"]["junction_fillet"]
    assert fitted["radius_selection"] == "width_fitted_10_percent_land"
    assert fitted["minimum_land"] > 0.0
    iso_05b = build_chain_sprocket_plan(
        designation="ISO_05B_3", chain_type="roller", tooth_count=19, row_count=3,
    )["row_layout"]["junction_fillet"]
    assert iso_05b["nominal_radius"] == 1.6
    assert iso_05b["radius"] == pytest.approx(0.45 * (5.64 - (0.90 * 3.0 - 0.15)))
    assert iso_05b["radius_selection"] == "width_fitted_10_percent_land"
    with pytest.raises(ValueError, match="outside circle must precede"):
        build_chain_sprocket_plan(
            designation="ISO_24B", chain_type="roller", tooth_count=200,
        )


def test_chain_sprocket_recipe_roundtrip_restores_studio_profile() -> None:
    import importlib.util
    from pathlib import Path

    plan = build_chain_sprocket_plan(
        designation="ISO_08B", chain_type="roller", tooth_count=19, row_count=1,
    )
    bridge_path = Path(__file__).resolve().parents[1] / "bridge" / "kompas_bridge.py"
    spec = importlib.util.spec_from_file_location("test_kompas_bridge_chain_recipe", bridge_path)
    assert spec is not None and spec.loader is not None
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)

    variables = bridge._chain_recipe_variables(plan)
    items = [
        {"name": item["name"], "value": item["value"], "note": item["note"]}
        for item in variables
    ]
    recipe, error = bridge._read_chain_recipe(items)
    assert error is None
    assert recipe["schema"] == "geomwright.chain.recipe"
    assert recipe["version"] == 1
    assert recipe["studio_profile"] == {
        "designation": "ISO_08B",
        "chain_type": "roller",
        "tooth_count": 19,
        "row_count": 1,
        "gost_profile_variant": "offset",
    }

    corrupted = [dict(item) for item in items]
    corrupted[1]["note"] = corrupted[1]["note"] + "x"
    recipe, error = bridge._read_chain_recipe(corrupted)
    assert recipe is None
    assert "checksum" in error


def test_chain_sprocket_multirow_representatives_cover_every_standard_in_mcp_and_studio() -> None:
    catalog = {item["designation"]: item for item in list_chain_profiles()["profiles"]}
    representatives = (
        ("iso_606", "ISO_08B_2", "roller", 2),
        ("gost_13568_2017", "GOST_2PV_9_525_20", "bush", 2),
        ("gost_21834_87", next(item["designation"] for item in catalog.values() if item["standard"] == "gost_21834_87" and item["nominal_row_count"] == 2), "roller", 2),
    )
    for standard, designation, chain_type, row_count in representatives:
        request = {
            "designation": designation,
            "chain_type": chain_type,
            "tooth_count": 25,
            "row_count": row_count,
        }
        plan = managed_pulley_plan("chain_sprocket", request)
        preview = preview_module("chain_sprocket", request)
        assert plan["profile_preview"]["standard"] == standard
        assert plan["geometry"]["row_count"] == row_count
        assert plan["geometry"]["row_spacing"] > plan["geometry"]["face_width"]
        assert preview["secondary_view"]["row_spacing_mm"] == pytest.approx(plan["geometry"]["row_spacing"])
        assert preview["secondary_view"]["total_width_mm"] == pytest.approx(plan["geometry"]["total_face_width"])
        assert preview["secondary_view"]["connector_status"] == "dimensioned"


def test_chain_sprocket_execute_routes_the_managed_plan_to_its_bridge_action() -> None:
    class RecordingRunner:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def call(self, action: str, payload: dict, **_: object) -> dict:
            self.calls.append((action, payload))
            if action == "create_chain_sprocket":
                return {
                    "ok": True,
                    "success": True,
                    "stage": "executed",
                    "document": {"runtime_id": "@document:1"},
                    "steps": [{
                        "id": "tooth_space_sketch",
                        "sketch": {"reference": 101},
                        "entities": [
                            {"id": "outside_overshoot_right", "reference": 201, "collection_index": 2},
                            {"id": "chain_outside_datum", "reference": 301, "collection_index": 1},
                        ],
                    }],
                }
            if action == "apply_existing_sketch_constraint":
                raise BridgeError("Bridge call timed out after 15 seconds")
            if action == "inspect_sketch_full":
                return {
                    "entities": [
                        {"kind": "segment", "index": 2, "reference": 201},
                        {"kind": "circle", "index": 1, "reference": 301},
                    ],
                    "constraints_state": {"code": 2, "label": "fully_defined"},
                    "summary": {
                        "closure_primary_closed": True,
                        "closure_primary_gap_count": 0,
                        "closure_primary_self_intersection_count": 0,
                    },
                    "constraints": {"all_items": [{
                        "properties": {"constraint_kind": "point_on_curve"},
                        "owner_object": {"reference": 201},
                        "partner_object": {"reference": 301},
                    }]},
                }
            raise AssertionError(action)

    runner = RecordingRunner()
    result = KompasAdapter(runner=runner).create_managed_pulley(
        family="chain_sprocket",
        profile_request={
            "designation": "ISO_08B",
            "chain_type": "roller",
            "tooth_count": 19,
            "row_count": 1,
            "gost_profile_variant": "offset",
        },
        execute=True,
        confirm_write=True,
    )

    assert result["success"] is True
    assert result["transition_constraint"]["ok"] is True
    assert result["transition_constraint"]["apply_call_timed_out"] is True
    assert result["transition_constraint"]["constraints_state_requires_ui_confirmation"] is False
    assert runner.calls[0][0] == "create_chain_sprocket"
    assert runner.calls[0][1]["plan"]["stage"] == "managed_chain_sprocket_plan"
    assert [action for action, _ in runner.calls] == [
        "create_chain_sprocket",
        "apply_existing_sketch_constraint",
        "inspect_sketch_full",
    ]


def test_registry_adapts_both_belt_previews_to_one_canvas_contract() -> None:
    v_belt = preview_module("v_belt", get_module("v_belt").defaults)
    poly_v = preview_module("poly_v", get_module("poly_v").defaults)

    assert v_belt["ok"] is True
    assert v_belt["family"] == "v_belt"
    assert len(v_belt["closed_points"]) == 2
    assert len(v_belt["feature_paths"]) == 2
    assert all(path[0] != path[-1] for path in v_belt["feature_paths"])
    assert len(v_belt["guide_paths"]) == 3
    assert v_belt["summary"]["datum_diameter_mm"] == pytest.approx(100.0)
    assert [item["key"] for item in v_belt["dimensions"]] == [
        "face_width",
        "groove_pitch",
        "groove_depth",
        "groove_top_width",
        "groove_angle",
        "outer_diameter",
        "datum_diameter",
        "root_diameter",
    ]
    assert v_belt["reference_paths"][0]["key"] == "datum_diameter"
    v_dimensions = {item["key"]: item for item in v_belt["dimensions"]}
    assert v_dimensions["groove_angle"]["orientation"] == "angular"
    assert v_dimensions["groove_angle"]["vertex"] != v_dimensions["groove_angle"]["left_ray"]
    assert v_dimensions["datum_diameter"]["placement"] == "left"
    assert v_dimensions["outer_diameter"]["placement"] == "right"
    assert v_dimensions["outer_diameter"]["level"] > v_dimensions["root_diameter"]["level"]
    assert v_dimensions["root_diameter"]["target_x"] is not None
    assert v_dimensions["face_width"]["level"] > v_dimensions["groove_top_width"]["level"]
    assert [item["code"] for item in v_belt["warning_items"]] == [
        "v_belt_flat_preview",
        "licensed_standard_check",
    ]
    assert v_belt["surface_features"] == []
    assert v_belt["summary"]["top_edge_fillet_radius_mm"] is None

    assert poly_v["ok"] is True
    assert poly_v["family"] == "poly_v"
    assert len(poly_v["closed_points"]) == 1
    assert len(poly_v["feature_paths"]) == 6
    assert all(path[0] != path[-1] for path in poly_v["feature_paths"])
    assert len(poly_v["guide_paths"]) == 2
    assert poly_v["summary"]["effective_diameter_mm"] == pytest.approx(80.0)
    assert [item["key"] for item in poly_v["dimensions"]] == [
        "face_width",
        "groove_pitch",
        "groove_depth",
        "groove_angle",
        "outer_diameter",
        "effective_diameter",
        "root_diameter",
        "transition_radius",
        "maximum_root_radius",
    ]
    assert poly_v["reference_paths"][0]["key"] == "effective_diameter"
    poly_dimensions = {item["key"]: item for item in poly_v["dimensions"]}
    assert poly_dimensions["groove_angle"]["orientation"] == "angular"
    assert poly_dimensions["effective_diameter"]["placement"] == "left"
    assert poly_dimensions["transition_radius"]["orientation"] == "radius"
    assert poly_dimensions["transition_radius"]["value"] == pytest.approx(0.3)
    assert poly_dimensions["maximum_root_radius"]["value"] == pytest.approx(0.4)
    assert poly_dimensions["maximum_root_radius"]["extension_length"] > 0
    assert poly_dimensions["root_diameter"]["target_x"] is not None
    assert poly_dimensions["outer_diameter"]["level"] > poly_dimensions["root_diameter"]["level"]
    assert "editable_profile" not in poly_v
    assert v_belt["editable_profile"]["groove_angle_degrees"] == pytest.approx(34.0)

    for result in (v_belt, poly_v):
        assert result["bounds"]["x_min"] < result["bounds"]["x_max"]
        assert result["bounds"]["y_min"] < result["bounds"]["y_max"]
        assert len(result["phantom_bodies"]) == 1
        assert result["phantom_bodies"][0]["truncated"] is True
        assert len(result["phantom_bodies"][0]["surface"]) > 2
        assert result["phantom_bodies"][0]["inner_radius"] < result["summary"]["root_diameter_mm"] / 2.0
        assert result["module"]["capabilities"]["build"] is True


def test_managed_pulley_plan_owns_a_new_blank_and_internal_target_contract() -> None:
    v_plan = managed_pulley_plan("v_belt", get_module("v_belt").defaults)
    poly_plan = managed_pulley_plan("poly_v", get_module("poly_v").defaults)

    for plan in (v_plan, poly_plan):
        assert plan["stage"] == "managed_pulley_plan"
        assert plan["blank"]["scenario"] == "stepped_shaft"
        assert plan["blank"]["params"]["close_after_save"] is False
        assert plan["target"]["axial_min"] == 0.0
        assert plan["target"]["axial_max"] == pytest.approx(plan["profile_preview"]["derived"]["face_width"])
        assert plan["target"]["parameter_base"] == {
            "outer_radius_variable": "PULLEY_D1/2",
            "face_width_variable": "PULLEY_L1",
        }
        assert plan["ownership"]["schema"] == "geomwright.managed_pulley"
        assert plan["ownership"]["required_variables"] == ["PULLEY_D1", "PULLEY_L1"]
        assert "document_id" not in plan

    assert v_plan["grooves"]["axial_center"] == pytest.approx(v_plan["target"]["axial_max"] / 2.0)
    assert poly_plan["grooves"]["axial_center"] == pytest.approx(poly_plan["target"]["axial_max"] / 2.0)


def test_timing_trapezoidal_managed_plan_owns_parameterized_workflow() -> None:
    request = dict(get_module("timing_trapezoidal").defaults)
    plan = managed_pulley_plan("timing_trapezoidal", request)

    assert plan["stage"] == "managed_pulley_plan"
    assert plan["family"] == "timing_trapezoidal"
    assert plan["member"]["stage"] == "trapezoidal_timing_pulley_parameterized_mechanics"
    assert plan["ownership"]["schema"] == "geomwright.managed_pulley"
    assert plan["ownership"]["pattern_feature_name"] == "Geomwright pulley groove pattern"
    assert plan["ownership"]["source_profile"]["designation_code"] == 2
    assert plan["target"] == {
        "axis": "global_x",
        "body_count": 1,
        "outer_diameter": pytest.approx(plan["profile_preview"]["derived"]["outside_diameter"]),
        "axial_min": 0.0,
        "axial_max": 20.0,
        "parameter_base": {
            "outer_radius_variable": "TB_OR",
            "face_width_variable": "TB_B",
        },
    }
    assert {"GW_MANAGED_VERSION", "GW_FAMILY_CODE", "GW_TIMING_DESIGNATION_CODE", "TB_Z", "TB_B"}.issubset(
        plan["ownership"]["required_variables"]
    )
    operations = plan["member"]["workflow"]["params"]["operations"]
    assert [item["scenario"] for item in operations] == [
        "cylindrical_blank",
        "numeric_profile_sketch",
        "cut_extrusion",
        "circular_pattern",
    ]
    assert operations[1]["params"]["require_fully_defined"] is True
    assert plan["verification"]["require_pattern_count"] == 24


def test_timing_curvilinear_managed_plan_is_available_through_studio_gate() -> None:
    from kompas_mcp.transmissions.pulley import build_managed_pulley_plan

    plan = build_managed_pulley_plan(
        "timing_curvilinear",
        {"designation": "HTD_5M", "tooth_count": 24, "face_width": 20.0},
    )

    assert plan["family"] == "timing_curvilinear"
    assert plan["member"]["stage"] == "curvilinear_timing_pulley_parameterized_mechanics"
    assert plan["ownership"]["family_code"] == 5
    assert plan["ownership"]["source_profile"]["designation_code"] == 6
    assert len(plan["member"]["workflow"]["params"]["operations"][1]["params"]["constraints"]) == 37
    assert get_module("timing_curvilinear").descriptor()["capabilities"]["build"] is True


def test_flat_belt_pulley_preview_and_managed_plan_cover_both_rim_profiles() -> None:
    cylindrical = preview_module("flat_belt", get_module("flat_belt").defaults)
    crowned_request = {
        "outer_diameter": 160.0,
        "face_width": 50.0,
        "crown_height": 1.5,
    }
    crowned = preview_module("flat_belt", crowned_request)

    assert cylindrical["family"] == "flat_belt"
    assert cylindrical["summary"]["edge_diameter_mm"] == pytest.approx(160.0)
    assert cylindrical["warnings"] == []
    assert crowned["summary"]["edge_diameter_mm"] == pytest.approx(157.0)
    assert crowned["summary"]["crown_radius_mm"] == pytest.approx(209.08333333333334)
    assert crowned["feature_paths"] == [crowned["guide_paths"][0]]
    assert crowned["feature_paths"][0][0][1] > 0.0
    assert crowned["feature_paths"][0][-1][1] > 0.0
    assert crowned["phantom_bodies"][0]["surface"] == crowned["feature_paths"][0]
    assert len(crowned["closed_points"][0]) > 20
    assert crowned["closed_points"][0][len(crowned["closed_points"][0]) // 2][1] > crowned["summary"]["edge_diameter_mm"] / 2.0
    assert [item["key"] for item in crowned["dimensions"]] == [
        "face_width",
        "outer_diameter",
        "crown_height",
    ]
    assert crowned["warning_items"][0]["code"] == "explicit_nonstandard_crown"
    diameter_dimensions = [item for item in crowned["dimensions"] if item["orientation"] == "diameter"]
    assert [item["symbol"] for item in diameter_dimensions] == ["⌀D"]
    assert all(item.get("start") and item.get("end") for item in diameter_dimensions)

    plan = managed_pulley_plan("flat_belt", crowned_request)
    assert plan["family"] == "flat_belt"
    assert plan["member"]["stage"] == "flat_belt_pulley_cad_plan"
    assert plan["member"]["operation"] == "boss_rotation"
    assert plan["ownership"]["required_variables"] == [
        "PULLEY_D1",
        "PULLEY_L1",
        "FP_OR",
        "FP_CROWN",
        "FP_PROFILE",
    ]
    entities = plan["member"]["bridge_preview"]["operations"][1]["profile_entities"]
    assert [item["kind"] for item in entities] == ["line", "line", "arc", "line"]
    assert entities[2]["direction"] is False
    params = plan["member"]["params"]
    assert params["require_parameterization"] is True
    assert params["require_fully_defined"] is True
    assert params["sketch"]["expected_dimension_count"] == 3
    assert {item["variable_name"] for item in params["dimensions"]} == {"PULLEY_L1", "FP_CENTER_Y", "FP_ARC_R"}
    variables = {item["name"]: item for item in plan["member"]["params"]["variables"]}
    assert variables["FP_OR"]["expression"] == "PULLEY_D1/2"
    assert variables["FP_ARC_R"]["expression"] == "(PULLEY_L1^2/4 + FP_CROWN^2)/(2*FP_CROWN)"
    assert variables["FP_CENTER_Y"]["expression"] == "FP_ARC_R - FP_OR"


def test_flat_belt_pulley_infers_profile_from_crown_height_and_rejects_impossible_crown() -> None:
    spec = get_module("flat_belt").spec()
    assert "profile" not in spec["schema"]["properties"]
    assert "profile" not in spec["defaults"]
    assert preview_module("flat_belt", {**spec["defaults"], "crown_height": 0.0})["summary"]["profile"] == "cylindrical"
    assert preview_module("flat_belt", {**spec["defaults"], "crown_height": 1.0})["summary"]["profile"] == "crowned"
    assert "rim_thickness" not in spec["schema"]["properties"]
    assert "rim_thickness" not in spec["defaults"]
    with pytest.raises(ValueError, match="positive edge radius"):
        preview_module(
            "flat_belt",
            {
                "outer_diameter": 40.0,
                "face_width": 20.0,
                "crown_height": 20.0,
            },
        )


def test_timing_belt_preview_uses_cropped_end_view_catalog_and_exposes_managed_cad() -> None:
    result = preview_module("timing_curvilinear", get_module("timing_curvilinear").defaults)

    assert result["family"] == "timing_belt"
    assert result["view_mode"] == "end"
    assert result["summary"]["designation"] == "HTD_5M"
    assert result["summary"]["profile_shape"] == "curvilinear"
    assert result["summary"]["pitch_diameter_mm"] == pytest.approx(24 * 5 / math.pi)
    assert len(result["feature_paths"][0]) == 119
    assert min(math.hypot(*point) for point in result["feature_paths"][0]) == pytest.approx(
        result["summary"]["root_diameter_mm"] / 2.0,
        abs=1e-8,
    )
    assert len(result["guide_paths"][0]) == 145
    assert result["guide_paths"][0][0] == pytest.approx(result["feature_paths"][0][-1])
    assert result["guide_paths"][0][-1] == pytest.approx(result["feature_paths"][0][0])
    assert result["bounds"]["y_min"] > 0
    assert [item["key"] for item in result["dimensions"]] == [
        "outside_diameter",
        "root_diameter",
        "groove_width",
        "groove_depth",
        "tip_radius",
        "root_fillet_radius",
    ]
    assert [item["key"] for item in result["reference_paths"]] == ["outside_circle"]
    assert all(item["orientation"] == "radial" for item in result["dimensions"][:2])
    assert result["dimensions"][2]["value"] == pytest.approx(result["summary"]["groove_width_mm"])
    assert result["dimensions"][3]["value"] == pytest.approx(result["summary"]["groove_depth_mm"])
    assert result["summary"]["tip_radius_mm"] == pytest.approx(0.43)
    assert result["summary"]["root_fillet_radius_mm"] == pytest.approx(1.5)
    assert result["module"]["family"] == "synchronous_pulleys"
    assert result["module"]["capabilities"]["build"] is True
    managed = managed_pulley_plan("timing_curvilinear", get_module("timing_curvilinear").defaults)
    assert managed["family"] == "timing_curvilinear"
    assert managed["target"]["outer_diameter"] == pytest.approx(result["summary"]["outside_diameter_mm"])


def test_timing_belt_custom_profile_requires_complete_geometry() -> None:
    request = {
        "designation": "CUSTOM",
        "tooth_count": 30,
        "face_width": 18.0,
        "custom_pitch": 4.0,
        "custom_groove_depth": 1.2,
        "custom_groove_width": 2.4,
        "custom_pitch_line_offset": 0.5,
        "custom_tip_radius": 0.18,
        "custom_root_radius": 0.32,
    }
    result = preview_module("timing_trapezoidal", request)

    assert result["summary"]["profile_shape"] == "trapezoidal"
    profile_path = result["feature_paths"][0]
    assert len(profile_path) == 158
    assert [item["key"] for item in result["dimensions"]][-2:] == ["tip_radius", "root_fillet_radius"]
    assert result["summary"]["tip_radius_mm"] == pytest.approx(0.18)
    assert result["summary"]["root_fillet_radius_mm"] == pytest.approx(0.32)
    assert result["warning_items"][0]["code"] == "custom_timing_profile"
    compatible = preview_module(
        "timing_trapezoidal",
        {key: value for key, value in request.items() if key not in {"custom_tip_radius", "custom_root_radius"}},
    )
    assert compatible["summary"]["tip_radius_mm"] == pytest.approx(0.24)
    assert compatible["summary"]["root_fillet_radius_mm"] == pytest.approx(0.42)
    with pytest.raises(Exception, match="CUSTOM requires"):
        preview_module("timing_trapezoidal", {"designation": "CUSTOM", "tooth_count": 30, "face_width": 18.0})


def test_flat_belt_studio_russian_copy_covers_fields_help_summary_warning_and_progress() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "geomwright" / "studio" / "static" / "i18n.js").read_text(encoding="utf-8")

    expected = [
        '"module.flat_belt.name": "Плоский"',
        '"field.outer_diameter": "Наружный диаметр"',
        '"field.face_width": "Ширина обода"',
        '"field.crown_height": "Высота выпуклости"',
        '"field.crown_height.help": "0 — цилиндрический обод;',
        '"summary.profile": "Форма обода"',
        '"summary.crown_height_mm": "Высота выпуклости, мм"',
        '"warning.explicit_nonstandard_crown": "Выпуклость задана явно',
        '"cad.operation.create_flat_pulley_sketch": "Создание эскиза плоскоременного шкива',
        '"cad.operation.create_flat_pulley_rotation": "Операция вращения обода',
    ]
    assert all(text in source for text in expected)


def test_canvas_renders_neutral_bodies_and_unfilled_feature_contours() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "geomwright" / "studio" / "static" / "canvas.js").read_text(encoding="utf-8")

    assert 'context.fillStyle = "rgba(132, 174, 204, 0.055)";' in source
    assert "(state.data.feature_paths || []).forEach" in source
    assert "drawPath(path, view, { stroke, lineWidth: 2.5 });" in source
    assert "drawPath(path, view, { fill, stroke });" not in source


def test_studio_cad_plan_status_reads_family_specific_dimensions_without_a_target() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "geomwright" / "studio" / "static" / "app.js").read_text(encoding="utf-8")

    assert "const planDimensions = cadPlanDisplayDimensions(plan);" in source
    assert "const derived = plan?.profile_preview?.derived || {};" in source
    assert "outerDiameter: derived.outer_diameter" in source
    assert "faceWidth: derived.face_width" in source
    assert "const geometry = plan?.geometry || {};" in source
    assert "outerDiameter: 2 * geometry.outside_radius" in source
    assert "faceWidth: geometry.face_width" in source
    assert "plan.target.outer_diameter" not in source
    assert 'timing_trapezoidal: "block.timing_trapezoidal"' in source
    assert 'timing_curvilinear: "block.timing_curvilinear"' in source
    assert 'form.addEventListener("wheel"' in source
    assert "event.preventDefault();" in source
    assert 'input.min === "" ? -Infinity : Number(input.min)' in source
    assert 'input.max === "" ? Infinity : Number(input.max)' in source
    assert 'moduleSelect.addEventListener("change"' in source
    assert 'const applies = currentModule?.kind === "chain_sprocket";' in source
    assert 'standard?.startsWith("gost_")' not in source
    assert 'moduleSelect.value' in source


def test_studio_exposes_a_cancel_control_for_running_cad_jobs() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    template = (root / "src" / "geomwright" / "studio" / "templates" / "fields.html").read_text(encoding="utf-8")
    source = (root / "src" / "geomwright" / "studio" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="cad-cancel-button"' in template
    assert 'requestJson(`/cad/jobs/${activeCadJobId}/cancel`, { method: "POST" })' in source


def test_bundled_bridge_contains_managed_pulley_create_and_ownership_paths() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "bridge" / "kompas_bridge.py").read_text(encoding="utf-8")
    packaged = (root / "src" / "kompas_mcp" / "assets" / "bridge" / "kompas_bridge.py").read_text(encoding="utf-8")

    assert source == packaged
    # BRIDGE-001: the bundled KOMPAS runtime is Python 3.2. f-strings and
    # starred display expressions are 3.5+ syntax; an ast feature_version check
    # does not catch the starred form reliably, so guard the source directly.
    assert not re.search(r"(^|[^A-Za-z0-9_])f[\"']", source)
    assert not re.search(r"^\s+\*\s*[A-Za-z_]", source, re.M)
    assert "def _build_managed_flat_pulley(" in source
    assert 'family not in ("v_belt", "poly_v", "flat_belt", "timing_trapezoidal", "timing_curvilinear")' in source
    assert '{"FP_OR", "FP_T"}.intersection(variable_names)' in source
    assert 'name.startswith(("V-belt grooves ", "Poly-V grooves ", "Flat-belt pulley "))' in source
    assert 'and object_valid is False' in source
    assert '"GW_TIMING_DESIGNATION_CODE"' in source
    assert '"all_feature_patterns": True' in source
    assert "def _refresh_timing_blank_sketch(model_container):" in source
    assert "def _rebuild_managed_timing_groove_branch(" in source
    assert '"groove_branch_replacement"' in source
    assert '"Managed timing-pulley rebuild after blank sketch refresh was not confirmed"' in source
    assert '"feature": _v_belt_object_reference(result.get("feature"), "member.functional_feature")' in source
    assert '"sketch": _v_belt_object_reference(result.get("sketch"), "member.profile_sketch")' in source
    assert 'family_code == 6' in source
    assert '"geomwright.managed_chain_sprocket" if family == "chain_sprocket"' in source
    assert '(feature_patterns, " tooth space pattern")' in source
    assert '"managed-chain-sprocket:"' in source
    assert "def handle_apply_existing_sketch_constraint(payload):" in source
    assert 'if action == "apply_existing_sketch_constraint":' in source
    assert "def _chain_recipe_variables(plan):" in source
    assert "CHAIN_RECIPE_SCHEMA" in source
    assert "CHAIN_RECIPE_HASH" in source
    assert '"recipe": chain_recipe' in source
    assert 'inspection.get("recreatable")' in source


def test_shared_pulley_body_verification_calls_api5_active_document_accessor() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "bridge" / "kompas_bridge.py").read_text(encoding="utf-8")

    assert 'document5 = safe_get(_APP5, "ActiveDocument3D")' in source
    assert 'if callable(document5) and not callable(safe_get(document5, "GetPart")):' in source


def test_managed_pulley_update_cannot_be_interrupted_mid_transaction() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "geomwright" / "studio" / "app.py").read_text(encoding="utf-8")

    assert "studio_adapter(cancel_event, interruptible=False).update_managed_pulley(" in source


def test_flat_belt_preview_is_registered_in_the_public_tool_catalog() -> None:
    from kompas_mcp.tool_catalog import get_mcp_tool_catalog

    catalog = get_mcp_tool_catalog()
    category = next(item for item in catalog["categories"] if item["name"] == "transmission_design")
    assert "preview_flat_belt_pulley" in category["tools"]
    assert "preview_timing_belt_pulley" in category["tools"]
    assert {
        "list_chain_profiles",
        "preview_chain_sprocket",
        "create_chain_sprocket",
        "inspect_chain_sprocket",
    } <= set(category["tools"])


def test_chain_sprocket_mcp_tools_are_registered_and_plan_without_com() -> None:
    from kompas_mcp.transmission_tools import ChainSprocketCreateRequest, ChainSprocketPreviewRequest
    from geomwright.kompas import server

    tools = server.mcp._tool_manager._tools
    assert {
        "list_chain_profiles",
        "preview_chain_sprocket",
        "create_chain_sprocket",
        "inspect_chain_sprocket",
    } <= set(tools)

    listing = tools["list_chain_profiles"].fn()
    assert listing["profile_count"] == 215

    preview = tools["preview_chain_sprocket"].fn(
        ChainSprocketPreviewRequest(designation="ISO_08B", chain_type="roller", tooth_count=19)
    )
    assert preview["success"] is True
    assert preview["profile_family"] == "iso_b"
    assert preview["derived"]["tooth_count"] == 19

    planned = tools["create_chain_sprocket"].fn(
        ChainSprocketCreateRequest(designation="ISO_08B", chain_type="roller", tooth_count=19)
    )
    assert planned["stage"] == "planned"
    assert planned["plan"]["stage"] == "managed_chain_sprocket_plan"
    assert planned["plan"]["ownership"]["schema"] == "geomwright.managed_chain_sprocket"


def test_v_belt_warning_codes_follow_conditions_instead_of_list_positions() -> None:
    custom = preview_module(
        "v_belt",
        {
            "designation": "CUSTOM",
            "datum_diameter": 100.0,
            "groove_count": 1,
            "custom_profile": {
                "datum_width": 10.0,
                "datum_offset": 2.0,
                "groove_pitch": 15.0,
                "edge_distance": 8.0,
                "groove_depth": 6.0,
                "groove_angle_degrees": 40.0,
            },
        },
    )
    overridden = preview_module(
        "v_belt",
        {
            **get_module("v_belt").defaults,
            "profile_overrides": {"groove_angle_degrees": 38.0},
        },
    )

    assert [item["code"] for item in custom["warning_items"]] == [
        "v_belt_flat_preview",
        "custom_profile_unverified",
    ]
    assert [item["code"] for item in overridden["warning_items"]] == [
        "v_belt_flat_preview",
        "licensed_standard_check",
        "profile_overrides_non_catalog",
    ]


def test_gost_v_belt_preview_shows_the_post_cut_top_edge_fillets() -> None:
    preview = preview_module(
        "v_belt",
        {
            "designation": "A",
            "datum_diameter": 100.0,
            "groove_count": 2,
            "standard_system": "gost_20889_88",
        },
    )

    fillets = preview["surface_features"]
    assert len(fillets) == 4
    assert {item["side"] for item in fillets} == {"left", "right"}
    assert {item["groove_index"] for item in fillets} == {1, 2}
    assert all(item["radius"] == pytest.approx(1.0) for item in fillets)
    assert all(item["radius_source"] == "standard" for item in fillets)
    assert all(len(item["points"]) == 13 for item in fillets)
    assert preview["summary"]["top_edge_fillet_radius_mm"] == pytest.approx(1.0)
    assert preview["dimensions"][-1]["key"] == "top_edge_fillet_radius"
    assert preview["dimensions"][-1]["symbol"] == "Rₖ"
    assert preview["warning_items"][0]["code"] == "v_belt_post_cut_fillet"

    cad_plan = managed_pulley_plan(
        "v_belt",
        {
            "designation": "A",
            "datum_diameter": 100.0,
            "groove_count": 2,
            "standard_system": "gost_20889_88",
        },
    )
    assert cad_plan["grooves"]["top_edge_fillet"]["radius"] == pytest.approx(1.0)
    assert cad_plan["grooves"]["top_edge_fillet"]["expected_edge_count"] == len(fillets)

    first_left = fillets[0]
    top_tangent = first_left["points"][0]
    flank_tangent = first_left["points"][-1]
    assert top_tangent[1] == pytest.approx(preview["bounds"]["y_max"])
    assert first_left["center"][1] == pytest.approx(top_tangent[1] - first_left["radius"])
    assert flank_tangent[0] > top_tangent[0]
    assert flank_tangent[1] < top_tangent[1]
    visible_contour = preview["closed_points"][0]
    assert len(visible_contour) > 20
    assert visible_contour[0] == pytest.approx(top_tangent)
    assert visible_contour[-1] == pytest.approx(top_tangent)
    assert [-6.508911248813579, 53.3] not in visible_contour


def test_v_belt_preview_marks_an_overridden_top_edge_fillet() -> None:
    preview = preview_module(
        "v_belt",
        {
            **get_module("v_belt").defaults,
            "profile_overrides": {"standard_top_edge_radius": 0.75},
        },
    )

    assert len(preview["surface_features"]) == 4
    assert all(item["radius"] == pytest.approx(0.75) for item in preview["surface_features"])
    assert all(item["radius_source"] == "override" for item in preview["surface_features"])


def test_http_api_serves_ui_catalog_preview_and_structured_errors() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    import time

    class HostOnlyAdapter:
        calls: list[dict] = []

        def create_managed_pulley(self, **kwargs):
            type(self).calls.append(kwargs)
            return {"ok": True, "host_test_double": True}

    client = TestClient(create_app(adapter_factory=HostOnlyAdapter))

    root = client.get("/")
    assert root.status_code == 200
    assert "Профиль ременного шкива" in root.text
    assert 'id="workspace-save-as-document"' in root.text
    assert 'id="editor-save-document"' in root.text
    assert 'id="editor-save-as-document"' in root.text
    assert 'id="cad-save-button"' not in root.text
    health = client.get("/health").json()
    assert health["product"] == "geomwright_studio"
    assert health["mode"] == "managed_cad"
    assert health["contract_version"] == 2
    assert len(health["static_version"]) == 12
    assert len(health["studio_version"]) == 12
    page = client.get("/").text
    assert f"styles.css?v={health['static_version']}" in page
    assert f"app.js?v={health['static_version']}" in page
    assert "managed_pulley_create_job" in health["capabilities"]
    assert client.get("/modules").json()["count"] == len(list_modules())
    gear_spec = client.get("/modules/gear_spur/spec").json()
    assert gear_spec["module"]["capabilities"] == {"preview": True, "build": True, "inspect": False}
    gear_preview = client.post("/modules/gear_spur/preview", json=gear_spec["defaults"])
    assert gear_preview.status_code == 200
    gear_body = gear_preview.json()
    assert gear_body["family"] == "gear_spur"
    assert len(gear_body["closed_points"][0]) > 200
    assert gear_body["summary"]["pitch_diameter_mm"] == 40.0
    assert gear_body["summary"]["verification_status"] == "ok"
    assert gear_body["secondary_view"]["helix_angle_deg"] == 0.0
    assert gear_body["secondary_view"]["hand"] == "right"
    gear_plan = client.post("/modules/gear_spur/cad/plan", json=gear_spec["defaults"])
    assert gear_plan.status_code == 200
    assert gear_plan.json()["stage"] == "gear_spur_cad_plan"
    assert gear_plan.json()["verification"]["pattern_count"] == 20
    assert gear_plan.json()["geometry"]["entity_count"] < 200
    invalid_gear = client.post("/modules/gear_spur/preview", json={"tooth_count": 3})
    assert invalid_gear.status_code == 422
    helical_request = {**gear_spec["defaults"], "helix_angle_deg": 20.0, "hand": "left"}
    helical_preview = client.post("/modules/gear_spur/preview", json=helical_request)
    assert helical_preview.status_code == 200
    helical_body = helical_preview.json()
    helical_summary = helical_body["summary"]
    assert helical_summary["verification_status"] == "ok"
    assert round(helical_summary["helix_angle_deg"], 6) == 20.0
    assert helical_summary["hand"] == "left"
    assert round(helical_summary["pitch_diameter_mm"], 4) == 42.5671
    assert round(helical_summary["transverse_module_mm"], 4) == 2.1284
    assert round(helical_summary["transverse_pressure_angle_deg"], 4) == 21.1728
    assert round(helical_summary["lead_mm"], 3) == 367.416
    assert round(helical_summary["axial_overlap"], 4) == 1.0887
    assert helical_summary["tip_thickness_normal_mm"] > 0.0
    assert helical_body["secondary_view"]["helix_angle_deg"] == 20.0
    assert helical_body["secondary_view"]["hand"] == "left"
    assert round(helical_body["secondary_view"]["lead_mm"], 3) == 367.416
    helical_plan = client.post("/modules/gear_spur/cad/plan", json=helical_request)
    assert helical_plan.status_code == 200
    helical_plan_body = helical_plan.json()
    helical_cut = helical_plan_body["workflow"]["params"]["operations"][2]
    assert helical_cut["scenario"] == "helical_cut_evolution"
    assert helical_cut["params"]["hand"] == "left"
    assert helical_cut["params"]["anchor_radius_mm"] == 0.0
    assert round(helical_cut["params"]["lead"], 3) == 367.416
    assert helical_plan_body["geometry"]["cut_scenario"] == "helical_cut_evolution"
    assert helical_plan_body["verification"]["expected_volume_mm3"] > 0.0
    chamfer_request = {**gear_spec["defaults"], "tip_chamfer_mm": 0.5, "tip_chamfer_angle_deg": 45.0}
    chamfer_preview = client.post("/modules/gear_spur/preview", json=chamfer_request)
    assert chamfer_preview.status_code == 200
    chamfer_body = chamfer_preview.json()
    assert chamfer_body["ok"] is True
    assert chamfer_body["summary"]["tip_chamfer_mm"] == 0.5
    assert round(chamfer_body["summary"]["tip_chamfer_depth_mm"], 6) == 0.5
    chamfer_plan = client.post("/modules/gear_spur/cad/plan", json=chamfer_request)
    assert chamfer_plan.status_code == 200
    chamfer_plan_body = chamfer_plan.json()
    assert [op["scenario"] for op in chamfer_plan_body["workflow"]["params"]["operations"]] == [
        "cylindrical_blank",
        "rotational_cut",
        "rotational_cut",
        "numeric_profile_sketch",
        "cut_extrusion",
        "circular_pattern",
    ]
    assert chamfer_plan_body["geometry"]["tip_chamfer_volume_mm3"] > 0.0
    assert (
        chamfer_plan_body["verification"]["expected_volume_mm3"]
        < gear_plan.json()["verification"]["expected_volume_mm3"]
    )
    oversized_chamfer = client.post(
        "/modules/gear_spur/preview", json={**chamfer_request, "tip_chamfer_mm": 12.0}
    )
    assert oversized_chamfer.status_code == 200
    assert oversized_chamfer.json()["ok"] is False
    assert any(
        item["code"] == "gear_chamfer_exceeds_face_width"
        for item in oversized_chamfer.json()["report"]["errors"]
    )

    internal_spec = client.get("/modules/gear_internal/spec").json()
    assert internal_spec["module"]["capabilities"] == {"preview": True, "build": True, "inspect": False}
    internal_preview = client.post("/modules/gear_internal/preview", json=internal_spec["defaults"])
    assert internal_preview.status_code == 200
    internal_body = internal_preview.json()
    assert internal_body["family"] == "gear_internal"
    assert internal_body["summary"]["ring_outside_diameter_mm"] == 100.0
    assert internal_body["summary"]["tip_diameter_mm"] == 76.8
    assert internal_body["summary"]["root_diameter_mm"] == 85.0
    assert internal_body["summary"]["verification_status"] == "ok"
    assert len(internal_body["closed_points"][0]) > 200
    assert internal_body["preview_window"] == {
        "tooth_gap_count": 3,
        "visible_tooth_count": 3,
        "section_style": "cropped_sector",
    }
    assert [item["key"] for item in internal_body["reference_paths"]] == [
        "pitch_circle",
        "tip_circle",
        "root_circle",
    ]
    assert len(internal_body["dimensions"]) == 3
    assert internal_body["summary"]["root_transition_mode"] == "cubic_bezier_root_transition"
    assert internal_body["summary"]["root_transition_size_mm"] == 0.6
    assert internal_body["secondary_view"]["internal"] is True
    assert internal_body["secondary_view"]["outside_diameter_mm"] == 100.0
    internal_plan = client.post("/modules/gear_internal/cad/plan", json=internal_spec["defaults"])
    assert internal_plan.status_code == 200
    internal_plan_body = internal_plan.json()
    assert internal_plan_body["stage"] == "internal_gear_cad_plan"
    assert [op["id"] for op in internal_plan_body["workflow"]["params"]["operations"]] == [
        "blank",
        "bore_cut",
        "tooth_space_sketch",
        "tooth_space_cut",
        "tooth_space_pattern",
    ]
    assert [op["scenario"] for op in internal_plan_body["workflow"]["params"]["operations"]] == [
        "cylindrical_blank",
        "rotational_cut",
        "numeric_profile_sketch",
        "cut_extrusion",
        "circular_pattern",
    ]
    assert internal_plan_body["verification"]["pattern_count"] == 40
    assert internal_plan_body["verification"]["expected_volume_mm3"] > 0.0
    tooth_entities = next(
        op for op in internal_plan_body["workflow"]["params"]["operations"]
        if op["id"] == "tooth_space_sketch"
    )["params"]["entities"]
    assert [
        entity["kind"] for entity in tooth_entities
        if "root_transition" in entity["id"]
    ] == ["nurbs", "nurbs"]
    internal_chamfer = client.post(
        "/modules/gear_internal/preview",
        json={**internal_spec["defaults"], "tip_chamfer_mm": 0.5},
    ).json()
    assert internal_chamfer["secondary_view"]["tip_chamfer_mm"] == 0.5
    assert internal_chamfer["secondary_view"]["tip_chamfer_depth_mm"] == pytest.approx(0.5)
    internal_chamfer_plan = client.post(
        "/modules/gear_internal/cad/plan",
        json={**internal_spec["defaults"], "tip_chamfer_mm": 0.5},
    ).json()
    chamfer_a = next(
        op for op in internal_chamfer_plan["workflow"]["params"]["operations"]
        if op["id"] == "tip_chamfer_face_a"
    )
    expected_chamfer_points = [
        [-20.0, 38.4],
        [-20.0, 38.9],
        [-19.5, 38.4],
    ]
    for actual, expected in zip(chamfer_a["params"]["profile_points"], expected_chamfer_points):
        assert actual == pytest.approx(expected)
    internal_helical = {**internal_spec["defaults"], "helix_angle_deg": 20.0, "hand": "left"}
    internal_helical_preview = client.post("/modules/gear_internal/preview", json=internal_helical)
    assert internal_helical_preview.status_code == 200
    assert internal_helical_preview.json()["summary"]["hand"] == "left"
    assert internal_helical_preview.json()["measurements"]["over_pin"]["available"] is False
    internal_helical_plan = client.post("/modules/gear_internal/cad/plan", json=internal_helical)
    assert internal_helical_plan.status_code == 200
    assert internal_helical_plan.json()["geometry"]["cut_scenario"] == "helical_cut_evolution"
    internal_bad_ring = client.post(
        "/modules/gear_internal/preview", json={**internal_spec["defaults"], "ring_outside_diameter_mm": 80.0}
    )
    assert internal_bad_ring.status_code == 200
    assert internal_bad_ring.json()["ok"] is False
    assert any(
        item["code"] == "gear_internal_ring_outside_below_root"
        for item in internal_bad_ring.json()["report"]["errors"]
    )

    cam_spec = client.get("/modules/camshaft_lobe/spec").json()
    assert cam_spec["module"]["capabilities"] == {"preview": True, "build": True, "inspect": False}
    cam_preview = client.post("/modules/camshaft_lobe/preview", json={"step": "cam"})
    assert cam_preview.status_code == 200
    assert not cam_preview.json()["warning_items"]
    assert cam_preview.json()["summary"]["selected_law"]
    assert cam_preview.json()["motion_chart"]["coordinate"] == "valve_command_with_lash"
    assert 'id="cam-chart-view"' in root.text
    assert "cam-motion.js?v=" in root.text
    motion_failure = client.post("/modules/camshaft_lobe/preview",
        json={"step": "cam", "law": "motion_spline", "max_jerk": 1.0})
    assert motion_failure.status_code == 422
    assert motion_failure.json()["detail"]["code"] == "cam_motion_no_kinematic_solution"
    invalid_cam = client.post("/modules/camshaft_lobe/preview", json={"base_diameter": -1})
    assert invalid_cam.status_code == 422
    assert invalid_cam.json()["detail"][0]["ctx"] == {"gt": 0.0}
    invalid_phases = client.post("/modules/camshaft_lobe/preview", json={"intake_open_deg": 300})
    assert invalid_phases.status_code == 422
    assert invalid_phases.json()["detail"]["code"] == "camshaft_phase_range"
    unreachable_cam = client.post("/modules/camshaft_lobe/preview", json={"step": "cam", "cam_y": 500})
    assert unreachable_cam.status_code == 422
    assert unreachable_cam.json()["detail"]["code"] == "camshaft_unreachable"
    contact_cam = {"step": "cam", "mechanism": "direct", "law": "curvature_spline",
        "base_diameter": 30, "max_lift": 18, "intake_open_deg": -70,
        "intake_close_deg": 70, "tappet_diameter": 42}
    contact_result = client.post("/modules/camshaft_lobe/preview", json=contact_cam)
    assert contact_result.status_code == 200
    assert contact_result.json()["summary"]["contact_width_verified"] is True
    contact_error = client.post("/modules/camshaft_lobe/preview",
        json={**contact_cam, "intake_open_deg": -10, "intake_close_deg": 50})
    assert contact_error.status_code == 422
    assert contact_error.json()["detail"]["code"] == "cam_flat_support_bound"
    assert contact_error.json()["detail"]["params"]["angle"] > 60

    silent_spec = client.get("/modules/silent_chain_sprocket/spec").json()
    assert silent_spec["module"]["capabilities"]["preview"] is True
    silent_preview = client.post("/modules/silent_chain_sprocket/preview", json=silent_spec["defaults"])
    assert silent_preview.status_code == 200
    assert silent_preview.json()["family"] == "silent_chain_sprocket"
    for suffix, payload, status in (
        ("cad/plan", silent_spec["defaults"], 422),
        ("cad/create", {"profile": silent_spec["defaults"], "confirm_write": True}, 422),
        ("cad/jobs", {"profile": silent_spec["defaults"], "confirm_write": True}, 422),
        ("cad/update-jobs", {"profile": silent_spec["defaults"], "confirm_write": True}, 409),
    ):
        assert client.post(f"/modules/silent_chain_sprocket/{suffix}", json=payload).status_code == status

    spec = client.get("/modules/poly_v/spec")
    assert spec.status_code == 200
    assert spec.json()["defaults"]["designation"] == "PJ"

    preview = client.post("/modules/poly_v/preview", json=spec.json()["defaults"])
    assert preview.status_code == 200
    assert preview.json()["family"] == "poly_v"
    assert len(preview.json()["closed_points"]) == 1

    cad_plan = client.post("/modules/poly_v/cad/plan", json=spec.json()["defaults"])
    assert cad_plan.status_code == 200
    assert cad_plan.json()["stage"] == "managed_pulley_plan"

    timing_spec = client.get("/modules/timing_trapezoidal/spec").json()
    timing_plan = client.post(
        "/modules/timing_trapezoidal/cad/plan",
        json=timing_spec["defaults"],
    )
    assert timing_plan.status_code == 200
    assert timing_plan.json()["target"]["outer_diameter"] > 0
    assert timing_plan.json()["target"]["axial_max"] == 20.0

    chain_spec = client.get("/modules/chain_sprocket/spec").json()
    chain_plan = client.post("/modules/chain_sprocket/cad/plan", json=chain_spec["defaults"])
    assert chain_plan.status_code == 200
    assert chain_plan.json()["stage"] == "managed_chain_sprocket_plan"
    multirow_chain = dict(chain_spec["defaults"], designation="ISO_08B_2", row_count=2)
    multirow_plan = client.post("/modules/chain_sprocket/cad/plan", json=multirow_chain)
    assert multirow_plan.status_code == 200
    assert multirow_plan.json()["stage"] == "managed_chain_sprocket_plan"
    multirow_job = client.post(
        "/modules/chain_sprocket/cad/jobs",
        json={"profile": multirow_chain, "confirm_write": True},
    )
    assert multirow_job.status_code == 202
    for _ in range(100):
        job = client.get(f"/cad/jobs/{multirow_job.json()['id']}").json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert job["status"] == "completed"
    assert job["result"]["host_test_double"] is True
    assert len(HostOnlyAdapter.calls) == 1
    assert HostOnlyAdapter.calls[0]["family"] == "chain_sprocket"

    unconfirmed = client.post(
        "/modules/poly_v/cad/create",
        json={"profile": spec.json()["defaults"]},
    )
    assert unconfirmed.status_code == 409

    invalid = client.post("/modules/v_belt/preview", json={"designation": "A"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["loc"] == ["datum_diameter"]
    assert client.get("/modules/missing/spec").status_code == 404
    assert client.post("/modules/poly_v/build", json={}).status_code == 404
    client.close()


def test_workspace_api_routes_snapshot_activation_and_file_opening() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    class WorkspaceAdapter:
        snapshots = 0
        calls: list[tuple] = []

        def studio_workspace_snapshot(self) -> dict:
            type(self).snapshots += 1
            return {
                "ok": True,
                "active_runtime_id": "@document:1",
                "documents": [
                    {
                        "document": {"runtime_id": "@document:1", "name": "Untitled", "active": True},
                        "blocks": [{"id": "block-1", "module": "poly_v", "editable": True}],
                        "operations": [],
                    }
                ],
            }

        def activate_document(self, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append(("activate", document_id, kwargs))
            return {"ok": True, "document": {"runtime_id": document_id}}

        def open_document(self, path: str, **kwargs: object) -> dict:
            return {"document": {"path": path}, "options": kwargs}

        def save_document(self, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append(("save", document_id, kwargs))
            return {"closed": True}

        def save_document_as(self, path: str, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append(("save_as", path, document_id, kwargs))
            return {"closed": True, "saved_as": path}

        def close_document(self, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append(("close", document_id, kwargs))
            return {"closed": True}

    client = TestClient(
        create_app(
            adapter_factory=WorkspaceAdapter,
            file_picker=lambda: r"C:\models\picked.m3d",
            save_file_picker=lambda suggested_name: rf"C:\models\{suggested_name}",
        )
    )
    workspace = client.get("/workspace")
    assert workspace.status_code == 200
    assert workspace.json()["documents"][0]["blocks"][0]["module"] == "poly_v"

    activated = client.post("/workspace/activate", json={"document_id": "@document:1"})
    assert activated.status_code == 200
    assert activated.json()["activated"]["document"]["runtime_id"] == "@document:1"
    assert WorkspaceAdapter.calls[-1] == ("activate", "@document:1", {"strict": True})

    opened = client.post("/workspace/open", json={"path": r"C:\models\pulley.m3d"})
    assert opened.status_code == 200
    assert opened.json()["opened"]["document"]["path"].endswith("pulley.m3d")
    selection = client.post("/workspace/pick-file")
    assert selection.status_code == 200
    assert selection.json() == {
        "ok": True,
        "cancelled": False,
        "path": r"C:\models\picked.m3d",
    }
    picked = client.post("/workspace/open-dialog")
    assert picked.status_code == 200
    assert picked.json()["opened"]["document"]["path"].endswith("picked.m3d")
    save_selection = client.post(
        "/workspace/pick-save-file",
        json={"suggested_name": "Untitled"},
    )
    assert save_selection.json()["path"].endswith("Untitled.m3d")

    closed = client.post(
        "/workspace/close",
        json={"document_id": "@document:1", "action": "discard"},
    )
    assert closed.status_code == 200
    assert WorkspaceAdapter.calls[-1] == (
        "close",
        "@document:1",
        {"save": False, "close_mode": 0, "strict": True},
    )
    saved_as = client.post(
        "/workspace/close",
        json={
            "document_id": "@document:1",
            "action": "save",
            "save_path": r"C:\models\Untitled.m3d",
        },
    )
    assert saved_as.status_code == 200
    assert WorkspaceAdapter.calls[-1][0] == "save_as"
    assert WorkspaceAdapter.calls[-1][-1] == {"close_after_save": True, "strict": True}
    saved_copy = client.post(
        "/workspace/save-as",
        json={"document_id": "@document:1", "save_path": r"C:\models\copy.m3d"},
    )
    assert saved_copy.status_code == 200
    assert WorkspaceAdapter.calls[-1] == (
        "save_as",
        r"C:\models\copy.m3d",
        "@document:1",
        {"close_after_save": False, "strict": True},
    )
    assert client.post("/workspace/save-as", json={"document_id": "@document:1"}).status_code == 422
    assert client.post(
        "/workspace/close",
        json={"document_id": "stale", "action": "discard"},
    ).status_code == 502
    assert client.post("/workspace/open", json={}).status_code == 422


def test_workspace_reports_disconnected_state_without_failing_initialization() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    class DisconnectedAdapter:
        def studio_workspace_snapshot(self) -> dict:
            raise RuntimeError("No running visible KOMPAS-3D instance. Start KOMPAS-3D.")

    response = TestClient(create_app(adapter_factory=DisconnectedAdapter)).get("/workspace")

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "connected": False,
        "documents": [],
        "active_runtime_id": None,
        "diagnostic": "No running visible KOMPAS-3D instance. Start KOMPAS-3D.",
    }


def test_studio_marks_bridge_runner_as_visible_session_only() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    class Runner:
        require_visible_kompas = False

    class VisibleAdapter:
        runner = Runner()

        def studio_workspace_snapshot(self) -> dict:
            return {"ok": True, "connected": True, "documents": [], "active_runtime_id": None}

    response = TestClient(create_app(adapter_factory=VisibleAdapter)).get("/workspace")

    assert response.status_code == 200
    assert VisibleAdapter.runner.require_visible_kompas is True


def test_workspace_save_keeps_document_open_and_refreshes_snapshot() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    class SaveAdapter:
        calls: list[tuple] = []

        def studio_workspace_snapshot(self) -> dict:
            return {
                "ok": True,
                "active_runtime_id": "@document:0",
                "documents": [{"document": {"runtime_id": "@document:0", "name": "Untitled", "path": ""}}],
            }

        def save_document_as(self, path: str, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append((path, document_id, kwargs))
            return {"document": {"runtime_id": path, "path": path}, "closed": False}

    client = TestClient(create_app(adapter_factory=SaveAdapter))
    response = client.post(
        "/workspace/save",
        json={"document_id": "@document:0", "save_path": r"C:\models\pulley.m3d"},
    )
    assert response.status_code == 200
    assert SaveAdapter.calls == [
        (r"C:\models\pulley.m3d", "@document:0", {"close_after_save": False, "strict": True})
    ]


def test_workspace_close_saved_document_uses_strict_save_and_close() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    class SavedWorkspaceAdapter:
        calls: list[tuple] = []

        def studio_workspace_snapshot(self) -> dict:
            return {
                "ok": True,
                "active_runtime_id": r"C:\models\pulley.m3d",
                "documents": [
                    {
                        "document": {
                            "runtime_id": r"C:\models\pulley.m3d",
                            "name": "pulley.m3d",
                            "path": r"C:\models\pulley.m3d",
                            "active": True,
                        },
                        "blocks": [],
                        "operations": [],
                    }
                ],
            }

        def save_document(self, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append((document_id, kwargs))
            return {"closed": True}

    client = TestClient(create_app(adapter_factory=SavedWorkspaceAdapter))
    response = client.post(
        "/workspace/close",
        json={"document_id": r"C:\models\pulley.m3d", "action": "save"},
    )

    assert response.status_code == 200
    assert SavedWorkspaceAdapter.calls == [
        (r"C:\models\pulley.m3d", {"close_after_save": True, "strict": True})
    ]


def test_curvilinear_timing_cad_create_job_reports_real_lifecycle_without_blocking_start_request() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    calls: list[dict] = []

    class FakeAdapter:
        def create_managed_pulley(self, **kwargs: object) -> dict:
            calls.append(dict(kwargs))
            progress_callback = kwargs.get("progress_callback")
            assert callable(progress_callback)
            progress_callback(
                {
                    "percent": 50,
                    "operation": "create_groove_sketch",
                    "name": "Poly-V grooves PJ x4 profile",
                }
            )
            time.sleep(0.03)
            return {"ok": True, "stage": "executed", "verification": {"ok": True}}

    client = TestClient(create_app(adapter_factory=FakeAdapter))
    profile = get_module("timing_curvilinear").defaults
    started = client.post(
        "/modules/timing_curvilinear/cad/jobs",
        json={"profile": profile, "confirm_write": True},
    )
    assert started.status_code == 202
    job = started.json()
    assert job["status"] in {"queued", "running"}

    deadline = time.monotonic() + 1.0
    while job["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
        time.sleep(0.01)
        job = client.get(f"/cad/jobs/{job['id']}").json()

    assert job["status"] == "completed"
    assert job["stage"] == "verified"
    assert job["result"]["verification"]["ok"] is True
    assert job["progress"]["percent"] == 100
    assert job["progress"]["operation"] == "completed"
    assert calls[0]["family"] == "timing_curvilinear"
    assert calls[0]["confirm_write"] is True
    assert client.get("/cad/jobs/missing").status_code == 404
    assert client.post("/modules/timing_curvilinear/cad/jobs", json={"profile": profile}).status_code == 409


def test_cam_job_preserves_recipe_partial_result_and_releases_lock() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from geomwright.studio.app import create_app
    from kompas_mcp.cams.cad import CamBuildError

    calls = []
    class FakeCamAdapter:
        def create_cam(self, request, **options):
            calls.append(options)
            assert options["studio_profile"]["step"] == "cam"
            if len(calls) == 1:
                raise CamBuildError("Native failed",{"status":"partial","verified":False,
                                    "document":{"runtime_id":"@document:7"}})
            return {"ok":True,"verification":{"ok":True}}

    client = TestClient(create_app(adapter_factory=FakeCamAdapter))
    for expected_status in ("failed","completed"):
        job = client.post("/modules/camshaft_lobe/cad/jobs",json={
            "profile":{"step":"cam"},"confirm_write":True}).json()
        deadline = time.monotonic()+2.0
        while job["status"] not in {"failed","completed"} and time.monotonic()<deadline:
            time.sleep(0.01)
            job = client.get(f"/cad/jobs/{job['id']}").json()
        assert job["status"] == expected_status
        if expected_status == "failed":
            assert job["partial_result"]["document"]["runtime_id"] == "@document:7"
            assert job["partial_result"]["verified"] is False
    assert len(calls) == 2


def test_curvilinear_timing_cad_update_job_targets_existing_managed_block() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    calls: list[dict] = []

    class UpdateAdapter:
        def update_managed_pulley(self, **kwargs: object) -> dict:
            calls.append(dict(kwargs))
            progress_callback = kwargs["progress_callback"]
            progress_callback({"percent": 70, "operation": "rebuild_updated_model", "name": "Pulley"})
            return {"ok": True, "success": True, "stage": "updated"}

    client = TestClient(create_app(adapter_factory=UpdateAdapter))
    profile = get_module("timing_curvilinear").defaults
    started = client.post(
        "/modules/timing_curvilinear/cad/update-jobs",
        json={
            "profile": profile,
            "previous_profile": profile,
            "document_id": "@document:0",
            "block_id": "managed-pulley:1-2-3-4",
            "confirm_write": True,
        },
    )
    assert started.status_code == 202
    job = started.json()
    deadline = time.monotonic() + 1.0
    while job["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
        time.sleep(0.01)
        job = client.get(f"/cad/jobs/{job['id']}").json()
    assert job["status"] == "completed"
    assert calls[0]["document_id"] == "@document:0"
    assert calls[0]["block_id"] == "managed-pulley:1-2-3-4"
    assert calls[0]["family"] == "timing_curvilinear"
    assert calls[0]["previous_profile_request"] == profile
    assert calls[0]["confirm_write"] is True


def test_studio_background_launcher_closes_streams_and_bounds_startup(tmp_path,monkeypatch) -> None:
    from geomwright.studio import background
    import subprocess
    import os
    calls = []
    stopped = []
    class Process:
        pid = 12345
        def poll(self):
            return None
    process = Process()
    def spawn(command,**kwargs):
        calls.append((command,kwargs))
        return process
    monkeypatch.setattr(background.subprocess,"Popen",spawn)
    monkeypatch.setattr(background,"_stop_owned_startup",stopped.append)
    result = background.launch_background(port=8765,expected_version="current",timeout=0.03,
        log_dir=tmp_path,health=lambda _: {"ok":True,"product":"geomwright_studio","studio_version":"current",
                                         "launch_id":calls[-1][1]["env"]["GEOMWRIGHT_STUDIO_LAUNCH_ID"]})
    assert result["pid"] == 12345
    assert calls[0][1]["stdin"] == subprocess.DEVNULL
    assert calls[0][1]["stdout"].closed and calls[0][1]["stderr"].closed
    assert calls[0][1]["close_fds"] is True
    if os.name == "nt":
        assert calls[0][1]["creationflags"] & subprocess.CREATE_NO_WINDOW
        assert not calls[0][1]["creationflags"] & subprocess.DETACHED_PROCESS
    with pytest.raises(RuntimeError,match="did not become ready"):
        background.launch_background(port=8765,expected_version="current",timeout=0.03,
                                     log_dir=tmp_path,health=lambda _: {
                                         "ok":True,"product":"geomwright_studio","studio_version":"current",
                                         "launch_id":"some-other-process"})
    assert stopped == [process]
    from geomwright.studio import __main__ as cli
    import threading
    release = threading.Event()
    def stalled_response(*args,**kwargs):
        release.wait()
        raise OSError("simulated stalled HTTP")
    monkeypatch.setattr(cli,"urlopen",stalled_response)
    started = time.monotonic()
    try:
        assert cli._ui_health("http://127.0.0.1:8765/") is None
        assert time.monotonic()-started<1.0
    finally:
        release.set()


def test_cli_starts_or_reopens_ui_and_reports_foreign_port_conflict(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from geomwright.studio import __main__ as ui_main
    from geomwright.studio.app import _studio_content_version

    opened: list[tuple[str, int]] = []
    monkeypatch.setattr(ui_main, "_ui_is_running", lambda _url: True)
    monkeypatch.setattr(ui_main, "_ui_health", lambda _url: {"studio_version": _studio_content_version()})
    monkeypatch.setattr(
        ui_main.webbrowser,
        "open",
        lambda url, new: opened.append((url, new)),
    )

    ui_main.main(["--port", "9876"])
    ui_main.main(["--port", "9876", "--no-browser"])

    assert opened == [("http://127.0.0.1:9876/", 2)]
    assert "already running" in capsys.readouterr().out

    monkeypatch.setattr(ui_main, "_ui_is_running", lambda _url: False)
    monkeypatch.setattr(ui_main, "_port_is_available", lambda _port: False)
    with pytest.raises(SystemExit, match="already in use"):
        ui_main.main(["--port", "9876"])

    scheduled: list[str] = []
    uvicorn_calls: list[dict[str, object]] = []
    monkeypatch.setattr(ui_main, "_port_is_available", lambda _port: True)
    monkeypatch.setattr(ui_main, "_schedule_browser_open", scheduled.append)

    import uvicorn

    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda _app, **kwargs: uvicorn_calls.append(kwargs),
    )
    ui_main.main(["--port", "9876"])

    assert scheduled == ["http://127.0.0.1:9876/"]
    assert uvicorn_calls == [{"host": "127.0.0.1", "port": 9876, "reload": False}]


def test_cli_reuses_current_studio_instead_of_stale_same_count_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from geomwright.studio import __main__ as ui_main
    from geomwright.studio.app import _studio_content_version

    current_version = _studio_content_version()
    monkeypatch.setattr(ui_main, "_port_is_available", lambda port: port not in (8765, 8766))
    monkeypatch.setattr(ui_main, "_ui_is_running", lambda url: url.endswith(("8765/", "8766/")))
    monkeypatch.setattr(
        ui_main,
        "_ui_health",
        lambda url: {"module_count": 8, "studio_version": "outdated" if url.endswith("8765/") else current_version},
    )
    opened: list[str] = []
    monkeypatch.setattr(ui_main.webbrowser, "open", lambda url, new: opened.append(url))

    ui_main.main([])

    assert opened == ["http://127.0.0.1:8766/"]


def test_cli_default_port_falls_back_for_legacy_studio_or_foreign_occupant(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from geomwright.studio import __main__ as ui_main

    monkeypatch.setattr(
        ui_main,
        "_ui_health",
        lambda _url: {
            "ok": True,
            "product": "geomwright_studio",
            "mode": "preview_only",
            "module_count": 2,
        },
    )
    assert ui_main._legacy_ui_is_running("http://127.0.0.1:8765/") is True
    assert ui_main._ui_is_running("http://127.0.0.1:8765/") is False

    monkeypatch.setattr(
        ui_main,
        "_ui_health",
        lambda _url: {
            "ok": True,
            "product": "geomwright_studio",
            "mode": "managed_cad",
            "contract_version": 2,
            "capabilities": ["managed_pulley_plan", "managed_pulley_create_job"],
            "module_count": 2,
        },
    )
    assert ui_main._ui_is_running("http://127.0.0.1:8765/") is True

    monkeypatch.setattr(ui_main, "_ui_is_running", lambda _url: False)
    monkeypatch.setattr(ui_main, "_port_is_available", lambda port: port == 8766)
    scheduled: list[str] = []
    uvicorn_calls: list[dict[str, object]] = []
    monkeypatch.setattr(ui_main, "_schedule_browser_open", scheduled.append)

    import uvicorn

    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda _app, **kwargs: uvicorn_calls.append(kwargs),
    )

    ui_main.main([])

    output = capsys.readouterr().out
    assert "older Geomwright Studio instance" in output
    assert "using 8766" in output
    assert scheduled == ["http://127.0.0.1:8766/"]
    assert uvicorn_calls == [{"host": "127.0.0.1", "port": 8766, "reload": False}]


def test_legacy_mechanics_ui_imports_remain_compatible() -> None:
    from kompas_mcp.studio.registry import list_modules as former_studio_list_modules
    from kompas_mcp.mechanics.ui.registry import list_modules as legacy_list_modules

    assert former_studio_list_modules() == list_modules()
    assert legacy_list_modules() == list_modules()


def test_gear_standard_catalog_and_pin_cache_cover_small_module_high_stress_and_iso() -> None:
    from kompas_mcp.gears import (
        SpurGearRequest,
        build_spur_gear_preview,
        gear_selection,
        resolve_rack,
    )

    selection = gear_selection()
    assert [item["value"] for item in selection["standards"]] == [
        "gost_13755_2015",
        "gost_9587_81",
        "gost_r_50531_93",
        "iso_53_1998",
    ]
    by_standard = {item["value"]: item for item in selection["standards"]}
    assert by_standard["gost_9587_81"]["module_system"] == "gost_9563_60"
    assert by_standard["gost_9587_81"]["module_max"] == 1.0
    assert by_standard["gost_9587_81"]["module_max_exclusive"] is True
    small_mods = {item["value"]: item for item in by_standard["gost_9587_81"]["modifications"]}
    assert small_mods["h11_c40"]["module_max"] == 0.5
    assert small_mods["h11_c40"]["module_max_exclusive"] is True
    assert small_mods["h11_c25"]["module_min"] == 0.5
    assert by_standard["iso_53_1998"]["module_system"] == "iso_54_1996"
    assert len(selection["module_rows"]["iso_54_1996"]["row_1"]) == 18
    assert selection["module_rows"]["gost_9563_60"]["exceptions"]
    assert any(source["id"] == "gost_2475_88_spline" for source in selection["pin_sources"])

    small = resolve_rack("gost_9587_81", "h1_c25")
    assert small.pressure_angle_deg == 20.0
    assert small.clearance_coefficient == 0.25
    assert small.fillet_coefficient == 0.38
    high_stress = resolve_rack("gost_r_50531_93", "type_1")
    assert high_stress.pressure_angle_deg == 25.0
    assert high_stress.clearance_coefficient == 0.20328
    assert abs(high_stress.fillet_coefficient - 0.35208) < 1e-9
    iso_d = resolve_rack("iso_53_1998", "d")
    assert iso_d.clearance_coefficient == 0.4
    assert iso_d.fillet_coefficient == 0.39

    preview = build_spur_gear_preview(
        {"standard": "gost_9587_81", "modification": "h1_c25",
         "module_mm": 0.5, "tooth_count": 24, "face_width_mm": 6.0}
    )
    assert preview["success"]
    assert preview["summary"]["standard"] == "gost_9587_81"
    assert abs(preview["summary"]["root_diameter_mm"] - 10.75) < 1e-9
    assert not any(item["code"] == "gear_small_module_contour" for item in preview["warning_items"])

    iso_preview = build_spur_gear_preview(
        {"standard": "iso_53_1998", "modification": "b",
         "module_mm": 5.5, "tooth_count": 30, "face_width_mm": 40.0}
    )
    assert iso_preview["success"]
    module_check = next(item for item in iso_preview["report"]["checks"] if item["code"] == "gear_module_row")
    assert module_check["status"] == "ok"
    assert iso_preview["summary"]["over_pin_source"].startswith("gost_")

    out_of_range = build_spur_gear_preview(
        {"standard": "gost_13755_2015", "modification": "a",
         "module_mm": 0.5, "tooth_count": 24, "face_width_mm": 6.0}
    )
    assert any(item["code"] == "gear_standard_module_range" for item in out_of_range["warning_items"])

    with pytest.raises(ValueError):
        SpurGearRequest(standard="iso_53_1998", modification="h1_c25")
