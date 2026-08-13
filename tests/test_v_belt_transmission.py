from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.transmission_tools import (
    CustomVGrooveProfile,
    VGrooveOverrides,
    VGroovePreviewRequest,
    VGrooveApplyRequest,
    VProfileListRequest,
    VProfileResolveRequest,
)
from kompas_mcp.transmissions import build_v_belt_cut_plan
from kompas_mcp.transmissions import list_v_belt_profiles
from kompas_mcp.transmissions import preview_v_belt_groove
from kompas_mcp.transmissions import resolve_v_belt_profile
from kompas_mcp.transmissions import validate_v_belt_cut_target


def test_catalog_lists_classical_and_narrow_profiles_with_provenance() -> None:
    payload = list_v_belt_profiles()

    assert payload["ok"] is True
    assert payload["profile_count"] == 10
    assert {item["designation"] for item in payload["profiles"]} == {
        "Z",
        "A",
        "B",
        "C",
        "D",
        "E",
        "SPZ",
        "SPA",
        "SPB",
        "SPC",
    }
    assert payload["source"]["evidence_level"] == "manufacturer_reference"
    assert payload["source"]["table"] == "Groove dimensions according to DIN 2211"
    expected = {
        "Z": (50.0, 8.5, 9.7, 2.0, 12.0, 8.0, 11.0),
        "A": (71.0, 11.0, 12.7, 2.8, 15.0, 10.0, 14.0),
        "B": (112.0, 14.0, 16.3, 3.5, 19.0, 12.5, 18.0),
        "C": (180.0, 19.0, 22.0, 4.8, 25.5, 17.0, 24.0),
        "D": (355.0, 27.0, 32.0, 8.1, 37.0, 24.0, 28.0),
        "E": (500.0, 32.0, 40.0, 12.0, 44.5, 29.0, 33.0),
        "SPZ": (63.0, 8.5, 9.7, 2.0, 12.0, 8.0, 11.0),
        "SPA": (90.0, 11.0, 12.7, 2.8, 15.0, 10.0, 14.0),
        "SPB": (140.0, 14.0, 16.3, 3.5, 19.0, 12.5, 18.0),
        "SPC": (224.0, 19.0, 22.0, 4.8, 25.5, 17.0, 24.0),
    }
    for item in payload["profiles"]:
        assert (
            item["minimum_datum_diameter"],
            item["datum_width"],
            item["approximate_top_width"],
            item["datum_offset"],
            item["groove_pitch"],
            item["edge_distance"],
            item["minimum_groove_depth"],
        ) == expected[item["designation"]]


def test_gost_catalog_has_independent_geometry_angle_schedule_and_radii() -> None:
    payload = list_v_belt_profiles(standard_system="gost_20889_88")

    assert payload["standard_system"] == "gost_20889_88"
    assert payload["profile_count"] == 6
    assert {item["designation"] for item in payload["profiles"]} == {"Z", "A", "B", "C", "D", "E"}
    assert payload["source"]["document"] == "GOST 20889-88"
    expected = {
        "Z": (50.0, 8.5, 2.5, 9.5, 12.0, 8.0, 0.5),
        "A": (75.0, 11.0, 3.3, 12.0, 15.0, 10.0, 1.0),
        "B": (125.0, 14.0, 4.2, 15.0, 19.0, 12.5, 1.0),
        "C": (200.0, 19.0, 5.7, 20.0, 25.5, 17.0, 1.5),
        "D": (315.0, 27.0, 8.1, 28.0, 37.0, 24.0, 2.0),
        "E": (500.0, 32.0, 9.6, 33.0, 44.5, 29.0, 2.0),
    }
    for item in payload["profiles"]:
        assert (
            item["minimum_datum_diameter"],
            item["datum_width"],
            item["datum_offset"],
            item["minimum_groove_depth"],
            item["groove_pitch"],
            item["edge_distance"],
            item["standard_top_edge_radius"],
        ) == expected[item["designation"]]

    angle_cases = [
        ("Z", 50.0, 34.0), ("Z", 80.0, 36.0), ("Z", 112.0, 38.0), ("Z", 180.0, 40.0),
        ("A", 75.0, 34.0), ("A", 125.0, 36.0), ("A", 180.0, 38.0), ("A", 450.0, 40.0),
        ("B", 125.0, 34.0), ("B", 180.0, 36.0), ("B", 250.0, 38.0), ("B", 560.0, 40.0),
        ("C", 200.0, 36.0), ("C", 355.0, 38.0), ("C", 710.0, 40.0),
        ("D", 315.0, 36.0), ("D", 500.0, 38.0), ("D", 1000.0, 40.0),
        ("E", 500.0, 36.0), ("E", 630.0, 38.0), ("E", 1250.0, 40.0),
    ]
    for designation, diameter, expected_angle in angle_cases:
        assert resolve_v_belt_profile(
            designation,
            diameter,
            standard_system="gost_20889_88",
        )["groove_angle_degrees"] == expected_angle
    for designation, diameter in [("Z", 75.0), ("A", 120.0), ("B", 240.0), ("C", 340.0), ("D", 475.0), ("E", 600.0)]:
        with pytest.raises(ValueError, match="not covered"):
            resolve_v_belt_profile(designation, diameter, standard_system="gost_20889_88")
    with pytest.raises(ValueError, match="standard_system=gost_20889_88"):
        resolve_v_belt_profile("SPZ", 100.0, standard_system="gost_20889_88")


def test_gost_preview_uses_gost_geometry_and_standard_fillet_policy() -> None:
    preview = preview_v_belt_groove(
        "A",
        datum_diameter=100.0,
        groove_count=2,
        standard_system="gost_20889_88",
    )
    parameter_base = {"outer_radius_variable": "R1", "face_width_variable": "L1"}
    plan = build_v_belt_cut_plan(
        preview,
        axial_center=17.5,
        parameter_base=parameter_base,
    )
    sharp_plan = build_v_belt_cut_plan(
        preview,
        axial_center=17.5,
        parameter_base=parameter_base,
        include_standard_top_edge_fillet=False,
    )

    assert preview["inputs"]["standard_system"] == "gost_20889_88"
    assert preview["derived"]["outer_diameter"] == pytest.approx(106.6)
    assert preview["derived"]["root_diameter"] == pytest.approx(82.6)
    assert preview["derived"]["face_width"] == pytest.approx(35.0)
    assert plan["top_edge_fillet"]["radius"] == pytest.approx(1.0)
    assert plan["top_edge_fillet"]["radius_source"] == "standard"
    assert sharp_plan["top_edge_fillet"] is None


def test_profile_resolution_enforces_minimum_diameter_and_angle_rule() -> None:
    at_threshold = resolve_v_belt_profile("SPZ", datum_diameter=80.0)
    above_threshold = resolve_v_belt_profile("SPZ", datum_diameter=80.01)

    assert at_threshold["groove_angle_degrees"] == 34.0
    assert above_threshold["groove_angle_degrees"] == 38.0
    with pytest.raises(ValueError, match="catalog minimum 63"):
        resolve_v_belt_profile("SPZ", datum_diameter=62.9)


@pytest.mark.parametrize(
    ("designation", "minimum", "threshold", "lower_angle"),
    [
        ("Z", 50.0, 80.0, 34.0),
        ("A", 71.0, 118.0, 34.0),
        ("B", 112.0, 190.0, 34.0),
        ("C", 180.0, 315.0, 34.0),
        ("D", 355.0, 500.0, 36.0),
        ("E", 500.0, 630.0, 36.0),
        ("SPZ", 63.0, 80.0, 34.0),
        ("SPA", 90.0, 118.0, 34.0),
        ("SPB", 140.0, 190.0, 34.0),
        ("SPC", 224.0, 315.0, 34.0),
    ],
)
def test_all_catalog_profiles_keep_their_minimum_and_angle_breakpoint(
    designation: str,
    minimum: float,
    threshold: float,
    lower_angle: float,
) -> None:
    assert resolve_v_belt_profile(designation, minimum)["groove_angle_degrees"] == lower_angle
    assert resolve_v_belt_profile(designation, threshold)["groove_angle_degrees"] == lower_angle
    assert resolve_v_belt_profile(designation, threshold + 0.01)["groove_angle_degrees"] == 38.0


def test_preview_builds_two_groove_cut_geometry_and_composition_contract() -> None:
    payload = preview_v_belt_groove("A", datum_diameter=100.0, groove_count=2)

    assert payload["success"] is True
    assert payload["derived"]["groove_angle_degrees"] == 34.0
    assert payload["derived"]["face_width"] == pytest.approx(35.0)
    assert payload["derived"]["outer_diameter"] == pytest.approx(105.6)
    assert payload["derived"]["root_diameter"] == pytest.approx(77.6)
    assert payload["derived"]["groove_centers"] == pytest.approx([-7.5, 7.5])
    assert len(payload["geometry"]["grooves"]) == 2
    assert all(len(item["closed_cut_polygon"]) == 5 for item in payload["geometry"]["grooves"])
    assert payload["composition"]["preferred_mode"] == "cut_from_body"
    assert payload["composition"]["contract_status"] == "implemented_layer_3"
    assert "hub" in payload["composition"]["excluded_features"]
    left_top, left_root = payload["geometry"]["grooves"][0]["cut_polygon"][:2]
    half_angle = math.degrees(
        math.atan((left_root[0] - left_top[0]) / (left_top[1] - left_root[1]))
    )
    assert 2.0 * half_angle == pytest.approx(34.0)
    assert payload["derived"]["actual_top_width"] == pytest.approx(12.7120918162)


def test_preview_supports_custom_profile_and_marks_non_catalog_source() -> None:
    payload = preview_v_belt_groove(
        "CUSTOM",
        datum_diameter=120.0,
        custom_profile={
            "designation": "CUSTOM-12",
            "datum_width": 12.0,
            "datum_offset": 3.0,
            "groove_pitch": 18.0,
            "edge_distance": 11.0,
            "groove_depth": 15.0,
            "groove_angle_degrees": 36.0,
        },
    )

    assert payload["profile"]["profile_mode"] == "custom"
    assert payload["source"]["evidence_level"] == "user_supplied"
    assert payload["derived"]["face_width"] == pytest.approx(22.0)


def test_preview_rejects_unknown_overrides_and_invalid_root_geometry() -> None:
    with pytest.raises(ValueError, match="Unsupported profile_overrides"):
        preview_v_belt_groove("A", 100.0, profile_overrides={"root_radius": 1.0})

    with pytest.raises(ValueError, match="closes the groove"):
        preview_v_belt_groove(
            "A",
            100.0,
            profile_overrides={"groove_depth": 50.0},
        )

    with pytest.raises(ValueError, match="groove_pitch"):
        preview_v_belt_groove(
            "A",
            100.0,
            groove_count=2,
            profile_overrides={"groove_pitch": 12.0},
        )

    with pytest.raises(ValueError, match="edge_distance"):
        preview_v_belt_groove(
            "A",
            100.0,
            profile_overrides={"edge_distance": 6.0},
        )


def test_mcp_input_models_expose_bounds_and_forbid_unknown_fields() -> None:
    overrides_schema = VGrooveOverrides.model_json_schema()
    custom_schema = CustomVGrooveProfile.model_json_schema()

    assert overrides_schema["additionalProperties"] is False
    assert custom_schema["additionalProperties"] is False
    assert overrides_schema["properties"]["groove_angle_degrees"]["anyOf"][0]["exclusiveMinimum"] == 0
    assert custom_schema["required"] == [
        "datum_width",
        "datum_offset",
        "groove_pitch",
        "edge_distance",
        "groove_depth",
        "groove_angle_degrees",
    ]
    for request_model in (
        VProfileListRequest,
        VProfileResolveRequest,
        VGroovePreviewRequest,
        VGrooveApplyRequest,
    ):
        assert request_model.model_json_schema()["additionalProperties"] is False


def test_cut_plan_offsets_multiple_loops_and_validates_declared_blank() -> None:
    preview = preview_v_belt_groove("A", datum_diameter=100.0, groove_count=2)
    parameter_base = {
        "outer_radius_variable": "R1",
        "face_width_variable": "L1",
    }
    shifted_plan = build_v_belt_cut_plan(
        preview,
        axial_center=17.5,
        name="A100 grooves",
        parameter_base=parameter_base,
    )
    filleted_plan = build_v_belt_cut_plan(
        preview,
        axial_center=17.5,
        name="A100 grooves",
        parameter_base=parameter_base,
        top_edge_fillet_radius=1.0,
    )

    assert shifted_plan["operation"] == "cut_rotation"
    assert shifted_plan["plan_version"] == 3
    assert shifted_plan["axis"] == "global_x"
    assert shifted_plan["requested_name"] == "A100 grooves"
    assert shifted_plan["entity_names"] == {
        "sketch": "V-belt grooves A x2 profile - A100 grooves",
        "cut": "V-belt grooves A x2 cut rotation - A100 grooves",
        "top_edge_fillet": None,
    }
    assert filleted_plan["entity_names"]["top_edge_fillet"] == (
        "V-belt grooves A x2 top edge fillets R1 - A100 grooves"
    )
    assert shifted_plan["groove_count"] == 2
    assert shifted_plan["profile_entity_count"] == 8
    draw_profile = shifted_plan["bridge_preview"]["operations"][1]
    assert len(draw_profile["profile_entities"]) == 8
    assert len(draw_profile["construction_lines"]) == 4
    assert len(shifted_plan["bridge_preview"]["operations"][2]["variables"]) == 10
    assert len(shifted_plan["bridge_preview"]["operations"][3]["constraints"]) == 15
    assert len(shifted_plan["params"]["pre_constraints"]) == 12
    assert len(shifted_plan["bridge_preview"]["operations"][4]["dimensions"]) == 8
    draw_axis = shifted_plan["bridge_preview"]["operations"][0]
    assert draw_axis["start"] == pytest.approx([0.0, 0.0])
    assert draw_axis["end"] == pytest.approx([40.0, 0.0])
    assert shifted_plan["params"]["expected_profile_component_count"] == 2
    assert shifted_plan["params"]["max_removed_volume_error_ratio"] == pytest.approx(0.25)
    assert shifted_plan["params"]["require_parameterization"] is True
    assert shifted_plan["params"]["initial_merge_offset_step"] == pytest.approx(0.5)
    assert shifted_plan["params"]["require_fully_defined"] is True
    assert shifted_plan["params"]["rotation_axis_default_object_type"] == 71
    assert shifted_plan["params"]["require_explicit_rotation_axis"] is True
    assert shifted_plan["params"]["sketch"]["constraints"]["enabled"] is True
    assert shifted_plan["params"]["sketch"]["dimensions"]["enabled"] is True
    assert shifted_plan["params"]["sketch"]["parameterization_order"] == "constraints_then_dimensions"
    assert shifted_plan["params"]["sketch"]["deferred_dimension_kinds"] == []
    assert shifted_plan["parameterization"] == {
        "variable_count": 10,
        "semantic_variable_count": 10,
        "dimension_variable_count": 8,
        "constraint_count": 15,
        "pre_constraint_count": 12,
        "dimension_count": 8,
        "projection_count": 0,
        "axis_line_count": 1,
        "auxiliary_line_count": 4,
        "target_state": "fully_defined",
        "base_mode": "origin_parameter_link",
    }
    sketch_contract = shifted_plan["params"]["sketch"]
    assert sketch_contract["require_exact_counts"] is True
    assert sketch_contract["expected_constraint_count"] == 15
    assert sketch_contract["expected_dimension_count"] == 8
    variable_items = shifted_plan["bridge_preview"]["variables"]
    assert [item["name"] for item in variable_items] == [
        "VB_OR",
        "VB_FACE_W",
        "VB_EDGE",
        "VB_PITCH",
        "VB_TOP_W",
        "VB_DEPTH",
        "VB_ANGLE",
        "VB_RR",
        "VB_ROOT_W",
        "VB_G2_TOP_W",
    ]
    variables = {item["name"]: item for item in variable_items}
    assert variables["VB_OR"]["expression"] == "R1"
    assert variables["VB_RR"]["expression"] == "VB_OR - VB_DEPTH"
    assert variables["VB_ROOT_W"]["expression"] == "VB_TOP_W - 2 * VB_DEPTH * tanD(VB_ANGLE / 2)"
    assert set(variables) == {
        "VB_DEPTH",
        "VB_TOP_W",
        "VB_ROOT_W",
        "VB_PITCH",
        "VB_EDGE",
        "VB_FACE_W",
        "VB_ANGLE",
        "VB_OR",
        "VB_RR",
        "VB_G2_TOP_W",
    }
    dimensions = shifted_plan["params"]["dimensions"]
    assert all(item["driving"] is True for item in dimensions)
    assert all(item.get("variable_name") for item in dimensions)
    centerlines = shifted_plan["bridge_preview"]["geometry"]["construction_entities"]
    assert len(centerlines) == 4
    assert {item["style"] for item in centerlines} == {2}
    assert shifted_plan["params"]["projections"] == []
    assert shifted_plan["params"]["top_edge_fillet"] is None
    fillet_plan = filleted_plan["params"]["top_edge_fillet"]
    assert fillet_plan["radius"] == pytest.approx(1.0)
    assert fillet_plan["expected_edge_count"] == 4
    assert len(fillet_plan["edge_probe_points"]) == 4
    assert {item["role"] for item in fillet_plan["edge_probe_points"]} == {
        "groove_1_top_left",
        "groove_1_top_right",
        "groove_2_top_left",
        "groove_2_top_right",
    }
    assert filleted_plan["bridge_preview"]["operations"][-1]["operation"] == "fillet_edges"
    assert "member.edge_fillet_feature" in filleted_plan["planned_outputs"]
    assert shifted_plan["params"]["axis_line_style"] == 3
    nominal_top_left = preview["geometry"]["grooves"][0]["cut_polygon"][0]
    assert shifted_plan["shifted_cut_polygons"][0][0] == pytest.approx(
        [nominal_top_left[0] + 17.5, nominal_top_left[1]]
    )
    assert shifted_plan["preflight"]["required_axial_interval"] == pytest.approx([0.0, 35.0])
    assert shifted_plan["expected_removed_volume_mm3"] > 0.0

    target = {
        "axis": "global_x",
        "body_count": 1,
        "outer_diameter": 105.6,
        "axial_min": 0.0,
        "axial_max": 35.0,
        "parameter_base": parameter_base,
    }
    assert validate_v_belt_cut_target(shifted_plan, target)["ok"] is True
    with pytest.raises(ValueError, match="outer_diameter"):
        validate_v_belt_cut_target(shifted_plan, {**target, "outer_diameter": 106.0})


def test_single_groove_origin_plan_omits_orphan_pitch_variable() -> None:
    preview = preview_v_belt_groove("A", datum_diameter=100.0, groove_count=1)
    parameter_base = {
        "outer_radius_variable": "R1",
        "face_width_variable": "L1",
    }
    plan = build_v_belt_cut_plan(
        preview,
        axial_center=float(preview["derived"]["face_width"]) / 2.0,
        parameter_base=parameter_base,
    )

    variables = {item["name"]: item for item in plan["params"]["variables"]}
    assert [item["name"] for item in plan["params"]["variables"]] == [
        "VB_OR",
        "VB_FACE_W",
        "VB_EDGE",
        "VB_TOP_W",
        "VB_DEPTH",
        "VB_ANGLE",
        "VB_RR",
        "VB_ROOT_W",
    ]
    dimensions = plan["params"]["dimensions"]
    assert "VB_PITCH" not in variables
    assert all("PITCH" not in str(item.get("variable_name")) for item in dimensions)

    dimension_variables = {str(item["variable_name"]) for item in dimensions}
    for variable_name in variables:
        if variable_name in dimension_variables:
            continue
        assert any(
            variable_name in str(other.get("expression") or "")
            for other_name, other in variables.items()
            if other_name != variable_name
        )


def test_apply_request_requires_confirmation_and_adapter_sends_preflight_plan() -> None:
    profile = VGroovePreviewRequest(designation="A", datum_diameter=100.0, groove_count=2)
    target = {
        "axis": "global_x",
        "body_count": 1,
        "outer_diameter": 105.6,
        "axial_min": 0.0,
        "axial_max": 35.0,
        "parameter_base": {
            "outer_radius_variable": "R1",
            "face_width_variable": "L1",
        },
    }
    with pytest.raises(ValidationError, match="confirm_write"):
        VGrooveApplyRequest(
            document_id="doc-1",
            profile=profile,
            target=target,
            execute=True,
        )

    runner = _RecordingRunner()
    adapter = KompasAdapter(runner=runner)
    result = adapter.apply_v_belt_grooves(
        document_id="doc-1",
        preview_request=profile.model_dump(exclude_none=True),
        target=target,
        axial_center=17.5,
        top_edge_fillet_radius=1.0,
        execute=False,
    )

    assert result["stage"] == "preflight"
    assert runner.calls[0][0] == "apply_v_belt_grooves"
    assert runner.calls[0][1]["execute"] is False
    assert runner.calls[0][1]["plan"]["profile_entity_count"] == 8
    assert runner.calls[0][1]["plan"]["params"]["top_edge_fillet"]["radius"] == pytest.approx(1.0)
    assert runner.calls[0][1]["plan"]["entity_names"] == {
        "sketch": "V-belt grooves A x2 profile",
        "cut": "V-belt grooves A x2 cut rotation",
        "top_edge_fillet": "V-belt grooves A x2 top edge fillets R1",
    }


def test_managed_pulley_adapter_owns_blank_and_routes_create_and_inspection() -> None:
    runner = _RecordingRunner()
    adapter = KompasAdapter(runner=runner)

    with pytest.raises(ValueError, match="confirm_write"):
        adapter.create_managed_pulley(
            family="v_belt",
            profile_request={"designation": "A", "datum_diameter": 100.0, "groove_count": 2},
            execute=True,
        )

    result = adapter.create_managed_pulley(
        family="v_belt",
        profile_request={"designation": "A", "datum_diameter": 100.0, "groove_count": 2},
        name="Owned pulley",
        execute=True,
        confirm_write=True,
    )
    action, payload = runner.calls[0]
    assert action == "create_managed_pulley"
    assert payload["confirm_write"] is True
    assert "document_id" not in payload
    assert payload["plan"]["ownership"]["schema"] == "geomwright.managed_pulley"
    assert payload["plan"]["blank"]["params"]["close_after_save"] is False
    assert result["plan"] == payload["plan"]

    adapter.inspect_managed_pulley(document_id="pulley.m3d")
    assert runner.calls[1] == ("inspect_managed_pulley", {"document_id": "pulley.m3d"})

    updated = adapter.update_managed_pulley(
        document_id="pulley.m3d",
        block_id="managed-pulley:1-2-3-4",
        family="v_belt",
        profile_request={"designation": "A", "datum_diameter": 110.0, "groove_count": 2},
        previous_profile_request={"designation": "A", "datum_diameter": 100.0, "groove_count": 2},
        name="Owned pulley",
        execute=True,
        confirm_write=True,
    )
    update_action, update_payload = runner.calls[2]
    assert update_action == "update_managed_pulley"
    assert update_payload["document_id"] == "pulley.m3d"
    assert update_payload["block_id"] == "managed-pulley:1-2-3-4"
    assert update_payload["plan"]["target"]["outer_diameter"] == pytest.approx(115.6)
    assert update_payload["rollback_plan"]["target"]["outer_diameter"] == pytest.approx(105.6)
    assert updated["plan"] == update_payload["plan"]

    custom_request = {
        "designation": "CUSTOM",
        "datum_diameter": 100.0,
        "groove_count": 3,
        "standard_system": "din_iso",
        "custom_profile": {
            "designation": "CUSTOM",
            "family": "custom",
            "datum_width": 11.0,
            "approximate_top_width": 13.0,
            "datum_offset": 3.5,
            "groove_pitch": 16.0,
            "edge_distance": 11.0,
            "groove_depth": 13.0,
            "groove_angle_degrees": 36.0,
            "minimum_datum_diameter": 70.0,
            "standard_top_edge_radius": 1.1,
        },
    }
    custom_plan = adapter.update_managed_pulley(
        document_id="pulley.m3d",
        block_id="managed-pulley:1-2-3-4",
        family="v_belt",
        profile_request=custom_request,
        previous_profile_request=custom_request,
        execute=False,
    )["plan"]
    assert custom_plan["ownership"]["source_profile"]["custom_profile"] == custom_request["custom_profile"]


def test_managed_pulley_adapter_forwards_bridge_progress_callback() -> None:
    class ProgressRunner:
        def call(self, action: str, payload: dict, *, progress_callback=None) -> dict:
            assert action == "create_managed_pulley"
            assert progress_callback is not None
            progress_callback({"percent": 12, "operation": "create_blank_sketch"})
            return {"ok": True, "success": True, "stage": "executed"}

    events: list[dict] = []
    KompasAdapter(runner=ProgressRunner()).create_managed_pulley(
        family="v_belt",
        profile_request={"designation": "A", "datum_diameter": 100.0, "groove_count": 2},
        execute=True,
        confirm_write=True,
        progress_callback=events.append,
    )

    assert events == [{"percent": 12, "operation": "create_blank_sketch"}]


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, action: str, payload: dict) -> dict:
        self.calls.append((action, payload))
        return {"ok": True, "success": True, "stage": "preflight", "executed": False}
