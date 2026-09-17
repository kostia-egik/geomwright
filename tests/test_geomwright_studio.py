from __future__ import annotations

import time
import math

import pytest

from geomwright.studio.registry import get_module, list_modules, managed_pulley_plan, preview_module
from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.bridge_runner import BridgeError
from kompas_mcp.transmissions import build_chain_sprocket_plan, list_chain_profiles, preview_chain_sprocket


def test_registry_exposes_schema_driven_transmission_modules() -> None:
    modules = list_modules()

    assert [item["kind"] for item in modules] == ["v_belt", "poly_v", "flat_belt", "timing_trapezoidal", "timing_curvilinear", "chain_sprocket"]
    assert all(item["group"] == "mechanical_transmissions" for item in modules)
    assert all(item["subgroup"] == "belt_drives" for item in modules[:-1])
    assert modules[-1]["subgroup"] == "chain_drives"
    assert modules[-1]["icon"] is None
    assert get_module("timing_trapezoidal").descriptor()["capabilities"]["build"] is True
    assert get_module("timing_curvilinear").descriptor()["capabilities"] == {"preview": True, "build": True, "inspect": False}
    for kind in ("v_belt", "poly_v", "flat_belt", "timing_trapezoidal", "timing_curvilinear"):
        module = get_module(kind)
        spec = module.spec()
        validated = module.request_model.model_validate(spec["defaults"])

        assert spec["module"]["preview_url"] == f"/modules/{kind}/preview"
        assert spec["module"]["cad_plan_url"] == f"/modules/{kind}/cad/plan"
        assert spec["module"]["cad_job_url"] == f"/modules/{kind}/cad/jobs"
        assert spec["schema"]["additionalProperties"] is False
        assert validated.model_dump(exclude_none=True) == spec["defaults"]


def test_chain_sprocket_exposes_hierarchical_catalog_and_preview_without_icon() -> None:
    module = get_module("chain_sprocket")
    assert module.descriptor()["capabilities"] == {"preview": True, "build": True, "inspect": False}
    assert module.descriptor()["icon"] is None
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
    unknown = preview_module("chain_sprocket", {**module.defaults, "designation": "ISO_50A_2", "row_count": 2})["secondary_view"]
    assert unknown["row_spacing_mm"] is None
    assert unknown["total_width_mm"] is None
    assert unknown["axial_layout_status"] == "schematic_missing_row_spacing"
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
        "chain_downstream_operations_external",
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
    assert "row_spacing" not in profiles["ISO_40A_3"]
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
        with pytest.raises(ValueError, match="GOST 591-69.*lambda"):
            managed_pulley_plan("chain_sprocket", {
                "designation": designation, "chain_type": "roller", "tooth_count": 90,
            })
    supported_pri = next(key for key, item in profiles.items() if item["label"] == "ПРИ-78,1-400")
    assert preview_chain_sprocket(designation=supported_pri, chain_type="roller", tooth_count=25)["success"]
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
    assert native_entities[7]["end"] == pytest.approx([6.318632539610, 41.104900177632])
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
    with pytest.raises(ValueError, match="multi-row CAD"):
        build_chain_sprocket_plan(
            designation="ISO_50A_2",
            chain_type="roller",
            tooth_count=19,
            row_count=2,
        )
    with pytest.raises(ValueError, match="row_count must match"):
        build_chain_sprocket_plan(designation="ISO_08B_3", chain_type="roller", tooth_count=25, row_count=2)
    with pytest.raises(ValueError, match="row_spacing must exceed"):
        build_chain_sprocket_plan(designation="ISO_08B_2", chain_type="roller", tooth_count=25, row_count=2, face_width=14.0)
    with pytest.raises(ValueError, match="r4 junction fillets do not fit"):
        build_chain_sprocket_plan(designation="ISO_08B_2", chain_type="roller", tooth_count=25, row_count=2, face_width=12.0)


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

    client = TestClient(create_app())

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
    page = client.get("/").text
    assert f"styles.css?v={health['static_version']}" in page
    assert f"app.js?v={health['static_version']}" in page
    assert "managed_pulley_create_job" in health["capabilities"]
    assert client.get("/modules").json()["count"] == 6

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
    assert multirow_job.json()["status"] in {"queued", "running", "completed", "failed"}

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


def test_cli_starts_or_reopens_ui_and_reports_foreign_port_conflict(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from geomwright.studio import __main__ as ui_main

    opened: list[tuple[str, int]] = []
    monkeypatch.setattr(ui_main, "_ui_is_running", lambda _url: True)
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
