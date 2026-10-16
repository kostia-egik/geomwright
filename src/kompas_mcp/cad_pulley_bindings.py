"""Shared-interface adapters for the five existing managed pulley families."""
from __future__ import annotations

import json
import math
from typing import Any

from pydantic import Field

from .transmission_tools import (VGroovePreviewRequest, PolyVGroovePreviewRequest,
    FlatBeltPulleyPreviewRequest, TimingTrapezoidalPulleyPreviewRequest,
    TimingCurvilinearPulleyPreviewRequest)
from .transmissions.pulley import build_managed_pulley_plan
from .transmissions import (preview_v_belt_groove, preview_poly_v_groove,
    preview_flat_belt_pulley, preview_timing_belt_pulley)


class VPulleyParameters(VGroovePreviewRequest):
    top_edge_fillet_radius: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    include_standard_top_edge_fillet: bool = True


PULLEY_MODELS = {
    "v_belt": VPulleyParameters, "poly_v": PolyVGroovePreviewRequest,
    "flat_belt": FlatBeltPulleyPreviewRequest,
    "timing_trapezoidal": TimingTrapezoidalPulleyPreviewRequest,
    "timing_curvilinear": TimingCurvilinearPulleyPreviewRequest,
}
PULLEY_EXAMPLES = {
    "v_belt": {"designation": "A", "datum_diameter": 160, "groove_count": 2},
    "poly_v": {"designation": "PJ", "effective_diameter": 100, "groove_count": 6},
    "flat_belt": {"outer_diameter": 100, "face_width": 30, "crown_height": 1},
    "timing_trapezoidal": {"designation": "T5", "tooth_count": 24, "face_width": 20},
    "timing_curvilinear": {"designation": "HTD_5M", "tooth_count": 24, "face_width": 20},
}


def _profile(parameters: dict) -> dict:
    return {key: value for key, value in parameters.items()
            if key not in {"top_edge_fillet_radius", "include_standard_top_edge_fillet"}}


def pulley_preview(parameters: dict, *, family: str) -> dict:
    profile = _profile(parameters)
    if family.startswith("timing_"):
        if profile["designation"] == "CUSTOM":
            profile["custom_shape"] = "trapezoidal" if family == "timing_trapezoidal" else "curvilinear"
        result = preview_timing_belt_pulley(**profile)
    else:
        result = {"v_belt": preview_v_belt_groove, "poly_v": preview_poly_v_groove,
                  "flat_belt": preview_flat_belt_pulley}[family](**profile)
    # Plan preflight includes requested finishing, not just the unrounded preview.
    if family == "v_belt":
        build_managed_pulley_plan(family, _profile(parameters),
            top_edge_fillet_radius=parameters.get("top_edge_fillet_radius"),
            include_standard_top_edge_fillet=parameters["include_standard_top_edge_fillet"])
    return {"success": result["success"], "summary": {"inputs": result.get("inputs"),
            "derived": result["derived"], "profile": result.get("profile")},
            "warnings": result.get("warnings", [])}


def pulley_plan(parameters: dict, *, name: str, family: str) -> dict:
    plan = build_managed_pulley_plan(family, _profile(parameters), name=name,
        top_edge_fillet_radius=parameters.get("top_edge_fillet_radius"),
        include_standard_top_edge_fillet=parameters.get("include_standard_top_edge_fillet", True))
    attach_pulley_recipe(plan, parameters)
    return plan


def attach_pulley_recipe(plan: dict, parameters: dict) -> None:
    recipe = {"schema": "geomwright.pulley.recipe", "version": 1, "family": plan["family"],
              "parameters": parameters, "name": plan["name"]}
    if len(json.dumps(recipe, ensure_ascii=True, allow_nan=False)) > 24000:
        raise ValueError("Pulley recipe exceeds 24000 characters")
    plan["shared_recipe"] = recipe


def pulley_plan_data(plan: dict) -> dict:
    preview = plan["profile_preview"]
    geometry = dict(plan.get("target") or {})
    geometry.pop("parameter_base", None)
    if not geometry:
        geometry = {key: preview["derived"][key] for key in ("outer_diameter", "face_width")}
        geometry["axial_interval_mm"] = [0, geometry["face_width"]]
    return {"name": plan["name"], "geometry": geometry, "derived": preview["derived"],
            "profile": preview.get("profile"), "warnings": preview.get("warnings", []),
            "accuracy": {"construction": "existing_parameterized_managed_pulley",
                         "edit_mode": "shared_interface_create_only", "conformity_claim": False}}


def _agrees(saved: dict, live: dict, *, nested: bool = False) -> bool:
    for key in set(saved) & set(live):
        a, b = saved[key], live[key]
        if key in {"source", "family"} or (nested and key == "designation"):
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            if not _agrees(a, b, nested=True):
                return False
        elif isinstance(a, (float, int)) and isinstance(b, (float, int)):
            if not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-8):
                return False
        elif a != b:
            return False
    return True


def _pulley_block(inspection: dict, family: str) -> dict:
    if not inspection.get("recognized") or inspection.get("family") != family:
        return {"module": None}
    parameters = None
    error = inspection.get("module_recipe_error")
    recipe = inspection.get("module_recipe")
    if recipe:
        try:
            if (recipe.get("schema") != "geomwright.pulley.recipe" or recipe.get("version") != 1
                    or recipe.get("family") != family):
                raise ValueError("Unsupported pulley recipe")
            raw = recipe["parameters"]
            required = {key for key, field in PULLEY_MODELS[family].model_fields.items()
                        if field.is_required() or field.default is not None}
            if not required.issubset(raw):
                raise ValueError("Incomplete pulley recipe; do not substitute defaults")
            parameters = PULLEY_MODELS[family].model_validate(raw).model_dump(exclude_none=True)
            live_profile = inspection.get("profile_request")
            if not isinstance(live_profile, dict) or not live_profile or not _agrees(_profile(parameters), live_profile):
                raise ValueError("Pulley driving inputs changed since the stored creation recipe")
        except (ValueError, KeyError, TypeError) as exc:
            error = str(exc)[:500]
            parameters = None
    return {"module": family, "id": inspection.get("block_id"),
            "name": recipe.get("name") if isinstance(recipe, dict) else inspection.get("display_name"),
            "schema": inspection.get("schema"), "version": inspection.get("version"),
            "profile": parameters, "recreatable": parameters is not None, "recipe_error": error,
            "verified": None, "status": "creation_recipe_recognized", "editable": False,
            "owned_references": inspection.get("identity_references") or []}


def inspect_pulley_module(adapter: Any, document_id: str, *, family: str) -> dict:
    return _pulley_block(adapter.inspect_managed_pulley(document_id=document_id), family)


def create_pulley_module(adapter: Any, plan: dict, visible: bool, *, family: str) -> dict:
    parameters = plan["shared_recipe"]["parameters"]
    created = adapter.create_managed_pulley(family=family, profile_request=_profile(parameters),
        name=plan["name"], execute=True, confirm_write=True, visible=visible, prepared_plan=plan,
        top_edge_fillet_radius=parameters.get("top_edge_fillet_radius"),
        include_standard_top_edge_fillet=parameters.get("include_standard_top_edge_fillet", True))
    try:
        doc = created["document"]
        docid = doc.get("runtime_id") or doc["id"]
        block = inspect_pulley_module(adapter, docid, family=family)
        if not block.get("recreatable") or block.get("profile") != parameters:
            raise RuntimeError("Pulley recipe/ownership readback differs from the request")
        body = created.get("body")
        if not body:
            fallback = created.get("blank" if family == "flat_belt" else "grooves") or {}
            body = fallback.get("body_after")
        body = dict(body or {})
        bodies = adapter.list_model_bodies(docid, limit=2)
        if (bodies["pagination"]["total"] != 1 or body.get("body_count") != 1
                or not body.get("solid") or body.get("volume", 0) <= 0):
            raise RuntimeError("Pulley must have one positive-volume solid")
        bounds = bodies["items"][0]["bounds_mm"]
        width = plan["profile_preview"]["derived"]["face_width"] if not family.startswith("timing_") else parameters["face_width"]
        axial_min, axial_max = (-width, 0) if family.startswith("timing_") else (0, width)
        if abs(bounds[0]-axial_min) > 1e-7 or abs(bounds[3]-axial_max) > 1e-7:
            raise RuntimeError("Pulley has unexpected global-X width or direction")
        body["bounds_mm"] = bounds
        verification = dict(created["verification"])
        verification["bounds_verified"] = True
        if family.startswith("timing_"):
            step = next(s for s in created["steps"] if s.get("scenario") == "circular_pattern")
            removed = float(step["source_volume_removed"])
            actual = removed + float(step["additional_volume_removed"])
            expected = removed * parameters["tooth_count"]
            if (step["count"] != parameters["tooth_count"] or removed <= 0
                    or abs(actual-expected) > max(1e-6, expected*5e-4)):
                raise RuntimeError("Timing pulley pattern did not remove the expected material")
            verification.update(pattern_count=step["count"], all_pattern_instances_remove_expected_material=True,
                                pattern_volume_relative_error=abs(actual-expected)/expected)
        return {**created, "body": body, "block": block, "verification": verification}
    except (ValueError, RuntimeError, KeyError, TypeError, StopIteration) as exc:
        error = RuntimeError(str(exc) or "Pulley readback contract is incomplete")
        error.partial_result = {"document": created.get("document"), "verified": False,
                                "stage": "pulley_readback", "rollback_performed": False}
        raise error from exc
