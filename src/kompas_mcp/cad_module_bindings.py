"""Translate existing family APIs into the shared module contract.

No CAD algorithms live here. In particular, sprocket execution retains the
managed-pulley adapter's post-build sketch-constraint verification.
"""
from __future__ import annotations

from typing import Any

from .transmissions import build_chain_sprocket_plan, preview_chain_sprocket
from .cams.cad import build_cam_plan, execute_cam_plan, CamBuildError
from .cams.module_contract import CamModuleParameters, CamMotionRequest
from .transmissions.silent_chain import build_silent_chain_plan
from .transmissions.silent_geometry import SilentChainSelectionRequest, build_silent_chain_preview


class ModuleInputRequired(ValueError):
    """A valid selection that still needs explicit engineering inputs before planning."""

    def __init__(self, completion: dict, *, source_summary: dict | None = None):
        super().__init__("Supply completion.missing_fields explicitly; suggestions are not engineering inputs.")
        self.completion = completion
        self.source_summary = source_summary


def create_plan(adapter: Any, plan: dict, visible: bool, *, method: str) -> dict:
    return getattr(adapter, method)(plan, execute=True, confirm_write=True, visible=visible)


def inspect_plan(adapter: Any, document_id: str, *, method: str) -> dict:
    return getattr(adapter, method)(document_id=document_id)


def gear_plan_data(plan: dict) -> dict:
    return {"name": plan["name"], "geometry": plan["geometry"],
            "accuracy": plan["accuracy"], "warnings": plan["profile_preview"].get("warnings", [])}


def chain_preview(parameters: dict) -> dict:
    preview = preview_chain_sprocket(**parameters)
    return {"success": preview["success"], "warnings": preview.get("warnings", []),
            "summary": {**preview["derived"], "profile": preview["profile"],
                        "profile_strategy": preview["profile_strategy"], "chain_type": preview["chain_type"]}}


def chain_plan(parameters: dict, *, name: str) -> dict:
    return build_chain_sprocket_plan(**parameters, name=name)


def chain_plan_data(plan: dict) -> dict:
    geometry = {key: value for key, value in plan["geometry"].items()
                if key not in {"tooth_space_vertices", "tooth_space_entities", "auxiliary_entities"}}
    preview = plan["profile_preview"]
    return {"name": plan["name"], "geometry": geometry,
            "profile": preview["profile"], "profile_strategy": preview["profile_strategy"],
            "accuracy": {"profile": plan["verification"]["profile_status"],
                         "parameterization": {key: plan["parameterization"][key] for key in (
                             "part_variables", "sketch_constraints", "sketch_dimensions", "operation_variables")},
                         "edit_mode": "create_only", "conformity_claim": False},
            "warnings": preview.get("warnings", [])}


def inspect_chain(adapter: Any, document_id: str) -> dict:
    result = adapter.inspect_managed_pulley(document_id=document_id)
    if not result.get("recognized") or result.get("family") != "chain_sprocket":
        return {"module": None}
    return {"module": "chain_sprocket", "id": result.get("block_id"),
            "name": result.get("display_name"), "schema": result.get("schema"),
            "version": result.get("version"), "profile": result.get("profile_request"),
            "status": "recognized", "editable": False, "verified": None,
            "recreatable": bool(result.get("recreatable")),
            "recipe_error": result.get("recipe_error"),
            "owned_references": result.get("identity_references") or []}


def create_chain(adapter: Any, plan: dict, visible: bool) -> dict:
    source = plan["ownership"]["source_profile"]
    parameters = {key: source[key] for key in (
        "designation", "chain_type", "tooth_count", "row_count", "gost_profile_variant")}
    created = adapter.create_managed_pulley(
        family="chain_sprocket", profile_request=parameters, name=plan["name"],
        execute=True, confirm_write=True, visible=visible, prepared_plan=plan,
    )
    if created.get("ok") and (created.get("verification") or {}).get("ok"):
        document = created.get("document") or {}
        try:
            transition = created.get("transition_constraint") or {}
            if transition.get("ok") is not True:
                raise RuntimeError("Chain-sprocket transition constraint has no successful readback")
            document_id = document.get("runtime_id") or document.get("id")
            block = inspect_chain(adapter, document_id)
            if not block.get("recreatable") or block.get("profile") != parameters:
                raise RuntimeError("Chain-sprocket ownership/recipe readback does not match the request")
            created = {**created, "block": block,
                       "verification": {**created["verification"], "transition_constraint": transition}}
        except (ValueError, RuntimeError, OSError) as exc:
            exc.partial_result = {"document": document, "verified": False,
                                  "stage": "ownership_and_recipe_recognition", "rollback_performed": False}
            raise
    return created


def cam_plan(parameters: dict, *, name: str) -> dict:
    return build_cam_plan(**parameters, name=name)


def cam_plan_data(plan: dict) -> dict:
    return {"name": plan["name"], "geometry": {"width": plan["width"],
            "rotation_deg": plan["rotation_deg"], "axial_interval_mm": plan["axial_interval"]},
            "calculation": plan["calculation"], "accuracy": {**plan["fit"],
            "tolerance_mm": plan["tolerance_mm"], "parameterization": plan["parameterization"]},
            "warnings": plan["warnings"]}


def cam_preview(parameters: dict) -> dict:
    plan = cam_plan(parameters, name="Geomwright cam")
    return {"success": True, "summary": {**plan["calculation"]["summary"],
            "law": plan["calculation"]["law"], "selection": plan["calculation"].get("selection"),
            "accuracy": plan["fit"], "verification": plan["verification"]},
            "warnings": plan["warnings"]}


def inspect_cam_module(adapter: Any, document_id: str) -> dict:
    result = adapter.inspect_cam(document_id)
    block = result.get("block") or {}
    if not result.get("recognized") or block.get("module") != "camshaft_lobe":
        return {"module": None}
    recipe = block.get("recipe")
    parameters = None
    recipe_error = block.get("recipe_error")
    if recipe:
        try:
            parameters = _cam_recipe_parameters(recipe)
        except (ValueError, KeyError, TypeError) as exc:
            recipe_error = f"Saved cam recipe cannot restore shared parameters: {str(exc)[:500]}"
    return {**block, "module": "cam", "profile": parameters,
            "recreatable": parameters is not None, "recipe_error": recipe_error}


def _cam_recipe_parameters(recipe: dict) -> dict:
    if recipe.get("schema") != "geomwright.cam.recipe" or recipe.get("version") != 1:
        raise ValueError("Unsupported cam recipe")
    request = recipe["request"]
    # Persisted normalized specs are complete. Never repair a damaged recipe by
    # allowing the user-input schema to substitute its default geometry.
    required = set(CamMotionRequest.model_fields) - {"timing"}
    if not isinstance(request, dict) or not required.issubset(request):
        raise ValueError("Incomplete saved cam request")
    return CamModuleParameters.model_validate({"request": {
        key: value for key, value in request.items() if key != "law_continuity_order"},
        **{key: recipe[key] for key in ("width", "rotation_deg", "tolerance")}}).model_dump(exclude_none=True)


def create_cam_module(adapter: Any, plan: dict, visible: bool) -> dict:
    created = execute_cam_plan(adapter, plan, confirm_write=True, visible=visible)
    try:
        block = inspect_cam_module(adapter, created["document"]["runtime_id"])
        wanted = _cam_recipe_parameters(plan["recipe"])
        exports = created.get("exports") or {}
        references = [exports.get("sketch_ref"), exports.get("feature_ref")]
        if (not all(references) or block.get("owned_references") != references
                or not block.get("verified") or block.get("profile") != wanted):
            raise RuntimeError("Cam ownership/recipe/verification marker readback differs")
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        raise CamBuildError(str(exc), {"document": created.get("document"), "verified": False,
            "stage": "ownership_and_recipe_recognition", "rollback_performed": False}) from exc
    body = dict(created["body"])
    body["bounds_mm"] = body.pop("bounds")
    return {**created, "body": body, "block": block}


def _silent_summary(preview: dict) -> dict:
    return {"profile": preview["profile"], "derived": preview["derived"],
            "axial": {key: value for key, value in preview["axial"].items() if key != "drawing"},
            "completion": preview["completion"], "diagnostics": preview.get("diagnostics", {}),
            "warnings": preview.get("warnings", []), "conformity_claim": False}


def silent_preview(parameters: dict) -> dict:
    preview = build_silent_chain_preview(parameters)
    return {"success": True, "summary": _silent_summary(preview), "warnings": preview.get("warnings", [])}


def silent_plan(parameters: dict, *, name: str) -> dict:
    preview = build_silent_chain_preview(parameters)
    if not preview["completion"]["ready_for_cad_planning"]:
        raise ModuleInputRequired(preview["completion"], source_summary=_silent_summary(preview))
    plan = build_silent_chain_plan(preview["construction_spec"], parameters, name=name)
    plan["module_summary"] = _silent_summary(preview)
    return plan


def silent_plan_data(plan: dict) -> dict:
    return {**plan["module_summary"], "name": plan["name"], "geometry": plan["target"],
            "accuracy": plan["accuracy"]}


def _silent_block(block: dict) -> dict:
    if block.get("module") != "silent_chain_sprocket":
        return {"module": None}
    parameters = None
    recipe_error = None
    summary = None
    if block.get("profile"):
        try:
            required = {name for name, field in SilentChainSelectionRequest.model_fields.items()
                        if field.is_required() or field.default is not None}
            if not isinstance(block["profile"], dict) or not required.issubset(block["profile"]):
                raise ValueError("Incomplete saved silent-chain request; do not substitute selection defaults")
            parameters = SilentChainSelectionRequest.model_validate(block["profile"]).model_dump(exclude_none=True)
            preview = build_silent_chain_preview(parameters)
            summary = _silent_summary(preview)
            if not preview["completion"]["ready_for_cad_planning"]:
                raise ValueError("Saved silent-chain recipe is missing required engineering inputs")
        except (ValueError, TypeError) as exc:
            parameters = None
            recipe_error = str(exc)[:500]
    return {**block, "profile": parameters, "verified": None,
            "status": "recognized", "recreatable": parameters is not None,
            "recipe_error": recipe_error, "owned_references": block.get("identity_references") or [],
            "source_summary": summary}


def inspect_silent_module(adapter: Any, document_id: str) -> dict:
    result = adapter.inspect_silent_chain_sprocket(document_id)
    return _silent_block(result.get("block") or {}) if result.get("recognized") else {"module": None}


def create_silent_module(adapter: Any, plan: dict, visible: bool) -> dict:
    created = adapter.create_silent_chain_sprocket(plan, execute=True, confirm_write=True, visible=visible)
    try:
        block = _silent_block(created.get("block") or {})
        if not block.get("recreatable") or block.get("profile") != plan["profile_request"]:
            raise RuntimeError("Silent-chain ownership/recipe readback differs from the request")
    except (ValueError, RuntimeError, TypeError) as exc:
        exc.partial_result = {"document": created.get("document"), "verified": False,
                              "stage": "ownership_and_recipe_recognition", "rollback_performed": False}
        raise
    return {**created, "block": block}
