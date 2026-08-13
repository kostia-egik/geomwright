from __future__ import annotations

from typing import Any, Literal

from ..parametric import preview_stepped_shaft
from .poly_v import build_poly_v_cut_plan, preview_poly_v_groove
from .v_belt import build_v_belt_cut_plan, preview_v_belt_groove
from .flat_belt import build_flat_belt_pulley_plan, preview_flat_belt_pulley


PulleyFamily = Literal["v_belt", "poly_v", "flat_belt"]
_PLAN_VERSION = 1
_PARAMETER_PREFIX = "PULLEY"


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
        raise ValueError("family must be 'v_belt', 'poly_v', or 'flat_belt'")

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
