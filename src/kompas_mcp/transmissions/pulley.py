from __future__ import annotations

from typing import Any, Literal

from ..parametric import preview_part_scenario, preview_stepped_shaft
from .poly_v import build_poly_v_cut_plan, preview_poly_v_groove
from .v_belt import build_v_belt_cut_plan, preview_v_belt_groove
from .flat_belt import build_flat_belt_pulley_plan, preview_flat_belt_pulley
from .timing_belt import build_curvilinear_timing_pulley_plan, build_trapezoidal_timing_pulley_plan


PulleyFamily = Literal["v_belt", "poly_v", "flat_belt", "timing_trapezoidal", "timing_curvilinear"]
_PLAN_VERSION = 1
_PARAMETER_PREFIX = "PULLEY"
_TIMING_DESIGNATION_CODES = {
    "CUSTOM": 0, "T2.5": 1, "T5": 2, "T10": 3, "AT5": 4,
    "HTD_3M": 5, "HTD_5M": 6, "HTD_8M": 7,
}


def build_managed_pulley_plan(
    family: PulleyFamily,
    profile_request: dict[str, Any],
    *,
    name: str = "Geomwright pulley",
    top_edge_fillet_radius: float | None = None,
    include_standard_top_edge_fillet: bool = True,
) -> dict[str, Any]:
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")
    if family in ("timing_trapezoidal", "timing_curvilinear"):
        timing_builder = (
            build_trapezoidal_timing_pulley_plan
            if family == "timing_trapezoidal"
            else build_curvilinear_timing_pulley_plan
        )
        member_plan = timing_builder(
            designation=str(profile_request.get("designation") or "T5"),
            tooth_count=int(profile_request.get("tooth_count") or 24),
            face_width=float(profile_request.get("face_width") or 20.0),
            name=requested_name,
            custom_pitch=profile_request.get("custom_pitch"),
            custom_groove_depth=profile_request.get("custom_groove_depth"),
            custom_groove_width=profile_request.get("custom_groove_width"),
            custom_pitch_line_offset=profile_request.get("custom_pitch_line_offset"),
            custom_tip_radius=profile_request.get("custom_tip_radius"),
            custom_root_radius=profile_request.get("custom_root_radius"),
            parameterize=True,
        )
        member_plan["workflow"]["params"] = preview_part_scenario(
            "workflow", member_plan["workflow"]["params"]
        )["params"]
        profile_preview = member_plan["profile_preview"]
        derived = dict(profile_preview.get("derived") or {})
        inputs = dict(profile_preview.get("inputs") or {})
        designation = str(profile_request.get("designation") or "T5")
        ownership = {
            "schema": "geomwright.managed_pulley",
            "version": _PLAN_VERSION,
            "family": family,
            "family_code": 4 if family == "timing_trapezoidal" else 5,
            "parameter_prefix": "TB",
            "required_variables": [
                "GW_MANAGED_VERSION", "GW_FAMILY_CODE", "GW_TIMING_DESIGNATION_CODE",
                "TB_P", "TB_Z", "TB_B", "TB_OR", "TB_H", "TB_RR", "TB_W",
                "TB_RT", "TB_RF", "TB_CO", "TB_STEP",
            ],
            "blank_feature_name": f"{requested_name} blank",
            "blank_sketch_name": f"{requested_name} blank sketch",
            "groove_feature_name": f"{requested_name} one groove cut",
            "groove_sketch_name": f"{requested_name} one groove",
            "pattern_feature_name": f"{requested_name} groove pattern",
            "source_profile": {
                **dict(profile_request),
                "designation": designation,
                "designation_code": _TIMING_DESIGNATION_CODES[designation],
            },
        }
        return {
            "ok": True,
            "stage": "managed_pulley_plan",
            "plan_version": _PLAN_VERSION,
            "family": family,
            "name": requested_name,
            "profile_request": dict(profile_request),
            "profile_preview": profile_preview,
            "member": member_plan,
            "target": {
                "axis": "global_x",
                "body_count": 1,
                "outer_diameter": float(derived["outside_diameter"]),
                "axial_min": 0.0,
                "axial_max": float(inputs["face_width"]),
                "parameter_base": {
                    "outer_radius_variable": "TB_OR",
                    "face_width_variable": "TB_B",
                },
            },
            "ownership": ownership,
            "verification": {
                "require_single_body": True,
                "require_blank_variables": ownership["required_variables"],
                "require_fully_defined_groove_sketch": True,
                "require_volume_decrease": True,
                "require_pattern_count": int(profile_request.get("tooth_count") or 24),
                "require_downstream_rebuild": True,
            },
        }
    if family == "v_belt":
        profile_preview = preview_v_belt_groove(**dict(profile_request))
    elif family == "poly_v":
        profile_preview = preview_poly_v_groove(**dict(profile_request))
    elif family == "flat_belt":
        profile_preview = preview_flat_belt_pulley(**dict(profile_request))
        member_plan = build_flat_belt_pulley_plan(profile_preview, name=requested_name)
        ownership = {
            "schema": "geomwright.managed_pulley",
            "version": _PLAN_VERSION,
            "family": family,
            "parameter_prefix": _PARAMETER_PREFIX,
            "required_variables": ["PULLEY_D1", "PULLEY_L1", "FP_OR", "FP_CROWN", "FP_PROFILE"],
            "blank_feature_name": member_plan["entity_names"]["feature"],
            "blank_sketch_name": member_plan["entity_names"]["sketch"],
            "groove_feature_name": None,
            "groove_sketch_name": None,
            "source_profile": dict(profile_request),
        }
        return {
            "ok": True,
            "stage": "managed_pulley_plan",
            "plan_version": _PLAN_VERSION,
            "family": family,
            "name": requested_name,
            "profile_request": dict(profile_request),
            "profile_preview": profile_preview,
            "member": member_plan,
            "ownership": ownership,
            "verification": {
                "require_single_body": True,
                "require_blank_variables": ownership["required_variables"],
                "require_positive_volume": True,
                "require_downstream_rebuild": True,
            },
        }
    else:
        raise ValueError("family must be 'v_belt', 'poly_v', 'flat_belt', 'timing_trapezoidal', or 'timing_curvilinear'")

    derived = dict(profile_preview.get("derived") or {})
    outer_diameter = float(derived["outer_diameter"])
    face_width = float(derived["face_width"])
    blank_params = {
        "name": f"{requested_name} blank",
        "sketch_name": f"{requested_name} blank profile",
        "designation": str(profile_request.get("designation") or ""),
        "comment": "Geomwright managed pulley blank",
        "parameter_prefix": _PARAMETER_PREFIX,
        "steps": [
            {
                "name": "functional rim",
                "length": face_width,
                "diameter": outer_diameter,
            }
        ],
        "close_after_save": False,
    }
    blank_preview = preview_stepped_shaft(blank_params)
    parameter_base = {
        "outer_radius_variable": f"{_PARAMETER_PREFIX}_D1/2",
        "face_width_variable": f"{_PARAMETER_PREFIX}_L1",
    }
    axial_center = face_width / 2.0
    if family == "v_belt":
        groove_plan = build_v_belt_cut_plan(
            profile_preview,
            axial_center=axial_center,
            name=requested_name,
            parameter_base=parameter_base,
            top_edge_fillet_radius=top_edge_fillet_radius,
            include_standard_top_edge_fillet=include_standard_top_edge_fillet,
        )
    else:
        if top_edge_fillet_radius is not None:
            raise ValueError("top_edge_fillet_radius is only supported for v_belt")
        groove_plan = build_poly_v_cut_plan(
            profile_preview,
            axial_center=axial_center,
            name=requested_name,
            parameter_base=parameter_base,
        )

    target = {
        "axis": "global_x",
        "body_count": 1,
        "outer_diameter": outer_diameter,
        "axial_min": 0.0,
        "axial_max": face_width,
        "parameter_base": parameter_base,
    }
    ownership = {
        "schema": "geomwright.managed_pulley",
        "version": _PLAN_VERSION,
        "family": family,
        "parameter_prefix": _PARAMETER_PREFIX,
        "required_variables": [f"{_PARAMETER_PREFIX}_D1", f"{_PARAMETER_PREFIX}_L1"],
        "blank_feature_name": blank_params["name"],
        "blank_sketch_name": blank_params["sketch_name"],
        "groove_feature_name": groove_plan["entity_names"]["cut"],
        "groove_sketch_name": groove_plan["entity_names"]["sketch"],
        "source_profile": {
            "designation": str(profile_request.get("designation") or ""),
            "groove_count": int(profile_request.get("groove_count") or 1),
            "datum_diameter": profile_request.get("datum_diameter"),
            "effective_diameter": profile_request.get("effective_diameter"),
            "standard_code": 2 if profile_request.get("standard_system") == "gost_20889_88" else 1,
            "custom_profile": dict(profile_request.get("custom_profile") or {}),
            "profile_overrides": dict(profile_request.get("profile_overrides") or {}),
        },
    }
    return {
        "ok": True,
        "stage": "managed_pulley_plan",
        "plan_version": _PLAN_VERSION,
        "family": family,
        "name": requested_name,
        "profile_request": dict(profile_request),
        "profile_preview": profile_preview,
        "blank": {
            "scenario": "stepped_shaft",
            "params": blank_preview["params"],
            "preview": blank_preview,
        },
        "grooves": groove_plan,
        "target": target,
        "ownership": ownership,
        "verification": {
            "require_single_body": True,
            "require_blank_variables": ownership["required_variables"],
            "require_fully_defined_groove_sketch": True,
            "require_volume_decrease": True,
            "require_downstream_rebuild": True,
        },
    }
