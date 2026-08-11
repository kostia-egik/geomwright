from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.tool_catalog import get_mcp_tool_catalog
from kompas_mcp.transmission_tools import PolyVGrooveApplyRequest, PolyVGroovePreviewRequest
from kompas_mcp.transmissions import build_poly_v_cut_plan
from kompas_mcp.transmissions import list_poly_v_profiles
from kompas_mcp.transmissions import preview_poly_v_groove
from kompas_mcp.transmissions import resolve_poly_v_profile
from kompas_mcp.transmissions import validate_poly_v_cut_target


EXPECTED_ISO_TABLE = {
    "PH": (1.60, 0.03, 0.25, 0.05, 0.30, 1.00, 0.11, 0.69, 1.30),
    "PJ": (2.34, 0.03, 0.30, 0.05, 0.40, 1.50, 0.23, 0.81, 1.80),
    "PK": (3.56, 0.05, 0.35, 0.10, 0.50, 2.50, 0.99, 1.68, 2.50),
    "PL": (4.70, 0.05, 0.55, 0.15, 0.40, 3.50, 2.36, 3.50, 3.30),
    "PM": (9.40, 0.08, 0.90, 0.15, 0.75, 7.00, 4.53, 5.92, 6.40),
}


def test_iso_9982_catalog_preserves_all_supported_profile_dimensions() -> None:
    catalog = list_poly_v_profiles()

    assert catalog["ok"] is True
    assert catalog["standard_system"] == "iso_9982_2021"
    assert catalog["profile_count"] == 5
    assert catalog["source"]["document"] == "ISO 9982:2021"
    assert catalog["source"]["evidence_level"] == "official_standard_preview"
    assert {item["designation"] for item in catalog["profiles"]} == set(EXPECTED_ISO_TABLE)
    for item in catalog["profiles"]:
        assert (
            item["groove_pitch"],
            item["groove_pitch_tolerance"],
            item["transition_radius"],
            item["transition_radius_tolerance"],
            item["maximum_root_radius"],
            item["checking_ball_or_rod_diameter"],
            item["two_x_nominal"],
            item["two_n_maximum"],
            item["minimum_edge_distance"],
        ) == EXPECTED_ISO_TABLE[item["designation"]]
        assert item["groove_angle_degrees"] == 40.0
        assert item["groove_angle_tolerance_degrees"] == 0.5
        assert item["cumulative_pitch_tolerance"] == 0.30


@pytest.mark.parametrize("designation", ["PH", "PJ", "PK", "PL", "PM"])
def test_preview_builds_one_exact_rounded_profile_with_iso_diameter_relation(
    designation: str,
) -> None:
    preview = preview_poly_v_groove(designation, effective_diameter=200.0, groove_count=4)
    profile = resolve_poly_v_profile(designation)
    derived = preview["derived"]
    geometry = preview["geometry"]

    assert preview["operation"] == "poly_v_groove"
    assert geometry["profile_component_count"] == 1
    assert geometry["closed"] is True
    assert len(geometry["profile_entities"]) == 23
    assert [item["target"] for item in geometry["profile_entities"][-3:]] == [
        "profile_right_overshoot",
        "profile_top_closure",
        "profile_left_overshoot",
    ]
    assert geometry["envelope"]["cut_profile_radius_max"] > geometry["envelope"]["radius_max"]
    assert derived["checking_diameter_over_balls_or_rods"] == pytest.approx(
        200.0 + profile["two_x_nominal"]
    )
    assert derived["outer_diameter"] == pytest.approx(
        derived["checking_diameter_over_balls_or_rods"] - derived["two_n_geometry"]
    )
    assert derived["two_n_geometry"] <= profile["two_n_maximum"]
    assert derived["face_width"] == pytest.approx(
        3.0 * profile["groove_pitch"] + 2.0 * profile["minimum_edge_distance"]
    )
    assert derived["outer_diameter"] < derived["effective_diameter"]
    assert 0.0 < derived["root_diameter"] < derived["outer_diameter"]
    assert derived["expected_removed_volume_mm3"] > 0.0
    assert json.loads(json.dumps(preview))["inputs"]["designation"] == designation

    groove = geometry["grooves"][0]
    entities = groove["profile_entities"]
    assert [item["kind"] for item in entities] == ["arc", "line", "arc", "line", "arc"]
    assert [item.get("direction") for item in entities if item["kind"] == "arc"] == [True, False, True]
    for left, right in zip(entities, entities[1:]):
        assert left["end"] == pytest.approx(right["start"])
    assert entities[0]["start"] == pytest.approx(groove["outer_points"][0])
    assert entities[-1]["end"] == pytest.approx(groove["outer_points"][1])

    half_angle = math.radians(20.0)
    left_flank = entities[1]
    dx = left_flank["end"][0] - left_flank["start"][0]
    dy = left_flank["end"][1] - left_flank["start"][1]
    assert dy / dx == pytest.approx(-1.0 / math.tan(half_angle))
    for arc, line, point in (
        (entities[0], entities[1], entities[0]["end"]),
        (entities[2], entities[1], entities[2]["start"]),
        (entities[2], entities[3], entities[2]["end"]),
        (entities[4], entities[3], entities[4]["start"]),
    ):
        radius_vector = [point[0] - arc["center"][0], point[1] - arc["center"][1]]
        line_vector = [line["end"][0] - line["start"][0], line["end"][1] - line["start"][1]]
        assert radius_vector[0] * line_vector[0] + radius_vector[1] * line_vector[1] == pytest.approx(
            0.0, abs=1e-9
        )


def test_preview_rejects_unknown_profile_invalid_count_and_too_small_diameter() -> None:
    with pytest.raises(ValueError, match="Unknown Poly-V profile"):
        preview_poly_v_groove("XX", effective_diameter=100.0)
    with pytest.raises(ValueError, match="between 1 and 64"):
        preview_poly_v_groove("PJ", effective_diameter=100.0, groove_count=0)
    with pytest.raises(ValueError, match="non-positive Poly-V groove root radius"):
        preview_poly_v_groove("PM", effective_diameter=1.0)


def test_cut_plan_has_canonical_names_parametric_arc_family_and_strict_preflight() -> None:
    preview = preview_poly_v_groove("PJ", effective_diameter=80.0, groove_count=6)
    parameter_base = {
        "outer_radius_variable": "D1 / 2",
        "face_width_variable": "L1",
    }
    plan = build_poly_v_cut_plan(
        preview,
        axial_center=20.0,
        parameter_base=parameter_base,
    )

    assert plan["stage"] == "poly_v_groove_cad_plan"
    assert plan["operation"] == "cut_rotation"
    assert plan["entity_names"] == {
        "sketch": "Poly-V grooves PJ x6 profile",
        "cut": "Poly-V grooves PJ x6 cut rotation",
    }
    assert plan["profile_component_count"] == 1
    assert plan["profile_entity_count"] == 33
    assert plan["profile_rounding"] == {
        "mode": "sketch_arcs",
        "transition_radius": 0.30,
        "root_radius": 0.40,
    }
    assert plan["params"]["require_fully_defined"] is True
    assert plan["params"]["require_all_constraints_applied"] is True
    assert plan["params"]["verify_profile_after_parameterization"] is True
    assert plan["parameterization"] == {
        "variable_count": 18,
        "semantic_variable_count": 18,
        "dimension_variable_count": 8,
        "constraint_count": 115,
        "pre_constraint_count": 43,
        "dimension_count": 8,
        "projection_count": 0,
        "axis_line_count": 1,
        "auxiliary_line_count": 15,
        "target_state": "fully_defined",
        "base_mode": "parametric_master_dependent",
        "master_groove": 1,
        "dependent_groove_count": 5,
    }
    assert plan["params"]["sketch"]["expected_constraint_count"] == 115
    assert plan["params"]["sketch"]["expected_dimension_count"] == 8
    assert {item["kind"] for item in plan["bridge_preview"]["geometry"]["profile_entities"]} == {
        "line",
        "arc",
    }
    variables = {item["name"]: item for item in plan["params"]["variables"]}
    assert [item["name"] for item in plan["params"]["variables"]] == [
        "PV_OR",
        "PV_FACE_W",
        "PV_E",
        "PV_RT",
        "PV_RB",
        "PV_DB",
        "PV_2X",
        "PV_ALPHA",
        "PV_COUNT",
        "PV_CENTER",
        "PV_AXIS_X0",
        "PV_CLOSURE",
        "PV_DO",
        "PV_2N",
        "PV_DE",
        "PV_DEPTH",
        "PV_ROOT_D",
        "PV_F",
    ]
    assert variables["PV_OR"]["expression"] == "D1 / 2"
    assert variables["PV_FACE_W"]["expression"] == "L1"
    assert variables["PV_RT"]["value"] == pytest.approx(0.30)
    assert variables["PV_RB"]["value"] == pytest.approx(0.40)
    assert variables["PV_2N"]["expression"].startswith("PV_DB / sinD(PV_ALPHA / 2)")
    assert variables["PV_DE"]["expression"] == "PV_DO - PV_2X + PV_2N"
    assert variables["PV_DEPTH"]["expression"].startswith("PV_E / (2 * tanD(PV_ALPHA / 2))")
    assert variables["PV_ROOT_D"]["expression"] == "2 * (PV_OR - PV_DEPTH)"
    assert variables["PV_F"]["expression"] == "(PV_FACE_W - (PV_COUNT - 1) * PV_E) / 2"

    pre_constraints = plan["params"]["pre_constraints"]
    constraints = plan["params"]["constraints"]
    dimensions = plan["params"]["dimensions"]
    assert [item for item in pre_constraints if item["kind"] == "fixed_point"] == [
        {"kind": "fixed_point", "target": "axis", "index": 0},
        {"kind": "fixed_point", "target": "axis", "index": 1},
    ]
    assert all(item["kind"] != "fixed_point" for item in constraints)
    assert {item["kind"] for item in constraints} >= {
        "equal_length",
        "equal_radius",
        "parallel",
        "tangent",
        "v_align_points",
    }
    assert {item["kind"] for item in dimensions} == {
        "line_length",
        "arc_radius",
        "angle_between_lines",
    }
    assert {item.get("variable_name") for item in dimensions if item.get("variable_name")} == {
        "PV_FACE_W",
        "PV_OR",
        "PV_E",
        "PV_RT",
        "PV_RB",
        "PV_CLOSURE",
    }
    assert [item["expression"] for item in dimensions if item["kind"] == "angle_between_lines"] == [
        "90 - PV_ALPHA / 2",
    ]
    assert len(plan["bridge_preview"]["geometry"]["construction_entities"]) == 15
    assert plan["preflight"]["required_axial_interval"] == pytest.approx(
        [20.0 - preview["derived"]["face_width"] / 2.0, 20.0 + preview["derived"]["face_width"] / 2.0]
    )

    target = {
        "axis": "global_x",
        "body_count": 1,
        "outer_diameter": preview["derived"]["outer_diameter"],
        "axial_min": plan["preflight"]["required_axial_interval"][0],
        "axial_max": plan["preflight"]["required_axial_interval"][1],
        "parameter_base": parameter_base,
    }
    assert validate_poly_v_cut_target(plan, target)["ok"] is True
    with pytest.raises(ValueError, match="outer_diameter"):
        validate_poly_v_cut_target(plan, {**target, "outer_diameter": target["outer_diameter"] + 0.01})
    with pytest.raises(ValueError, match="face interval"):
        validate_poly_v_cut_target(plan, {**target, "axial_min": target["axial_min"] + 0.01})


def test_apply_schema_requires_confirmation_and_adapter_dispatches_poly_v_action() -> None:
    profile = PolyVGroovePreviewRequest(designation="PJ", effective_diameter=80.0, groove_count=6)
    preview = preview_poly_v_groove(**profile.model_dump())
    target = {
        "axis": "global_x",
        "body_count": 1,
        "outer_diameter": preview["derived"]["outer_diameter"],
        "axial_min": -preview["derived"]["face_width"] / 2.0,
        "axial_max": preview["derived"]["face_width"] / 2.0,
        "parameter_base": {
            "outer_radius_variable": "D1 / 2",
            "face_width_variable": "L1",
        },
    }
    with pytest.raises(ValidationError, match="confirm_write"):
        PolyVGrooveApplyRequest(
            document_id="doc-1",
            profile=profile,
            target=target,
            execute=True,
        )

    runner = _RecordingRunner()
    adapter = KompasAdapter(runner=runner)
    result = adapter.apply_poly_v_grooves(
        document_id="doc-1",
        preview_request=profile.model_dump(),
        target=target,
        execute=False,
    )

    assert result["stage"] == "preflight"
    assert runner.calls[0][0] == "apply_poly_v_grooves"
    payload = runner.calls[0][1]
    assert payload["execute"] is False
    assert payload["preview"]["operation"] == "poly_v_groove"
    assert payload["plan"]["stage"] == "poly_v_groove_cad_plan"
    assert payload["host_preflight"]["stage"] == "poly_v_target_preflight"


def test_tool_catalog_and_bundled_bridge_expose_poly_v_contract_with_parity() -> None:
    tools = {
        tool
        for category in get_mcp_tool_catalog()["categories"]
        if category["name"] == "transmission_design"
        for tool in category["tools"]
    }
    assert {
        "list_poly_v_profiles",
        "resolve_poly_v_profile",
        "preview_poly_v_groove",
        "apply_poly_v_grooves",
    } <= tools

    root = Path(__file__).resolve().parents[1]
    bridge = (root / "bridge" / "kompas_bridge.py").read_bytes()
    bundled = (root / "src" / "kompas_mcp" / "assets" / "bridge" / "kompas_bridge.py").read_bytes()
    assert bridge == bundled
    source = bridge.decode("utf-8")
    assert "def handle_apply_poly_v_grooves(payload):" in source
    assert 'if action == "apply_poly_v_grooves":' in source
    assert "Poly-V groove plan must contain exactly one closed profile component" in source


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, action: str, payload: dict) -> dict:
        self.calls.append((action, payload))
        return {"ok": True, "success": True, "stage": "preflight", "executed": False}
