from __future__ import annotations

import math

import pytest

from kompas_mcp.transmission_tools import (
    CustomVGrooveProfile,
    VGrooveOverrides,
    VGroovePreviewRequest,
    VProfileListRequest,
    VProfileResolveRequest,
)
from kompas_mcp.transmissions import list_v_belt_profiles
from kompas_mcp.transmissions import preview_v_belt_groove
from kompas_mcp.transmissions import resolve_v_belt_profile


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
    assert payload["composition"]["contract_status"] == "planned_for_cad_builder"
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
    for request_model in (VProfileListRequest, VProfileResolveRequest, VGroovePreviewRequest):
        assert request_model.model_json_schema()["additionalProperties"] is False
