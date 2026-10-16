"""Create-only common adapter for the existing stepped-shaft generator."""
from __future__ import annotations
from .cad_session_policy import lifecycle_verification

import math
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .parametric import preview_part_scenario


class ShaftStep(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    length: float = Field(gt=0)
    diameter: float = Field(gt=0)


class SteppedShaftParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    steps: list[ShaftStep] = Field(min_length=1, max_length=100)


def shaft_plan(parameters: dict, *, name: str) -> dict:
    preview = preview_part_scenario("stepped_shaft", {**parameters, "name": name,
        "sketch_name": "Stepped shaft profile", "parameter_prefix": "SHAFT"})
    preview["params"].update(fix_sketch_placement=True, require_fully_defined=True)
    volume = math.fsum(math.pi * step["diameter"] * step["diameter"] / 4 * step["length"] for step in parameters["steps"]) / 1000
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("Shaft volume must be finite and positive")
    return {"module_id":"stepped_shaft", "preview":preview, "expected_volume_cm3":volume,
        "recipe":{"schema":"geomwright.stepped_shaft.recipe", "version":1, "name":name,
                  "parameters":parameters, "profile_name":"Stepped shaft profile", "body_name":"Stepped shaft body"},
        "verification":{"single_solid":True,"analytic_volume":True,"step_dimensions":True,"save_reopen_required":True}}


def shaft_plan_data(plan: dict) -> dict:
    p = plan["preview"]["params"]
    return {"name":plan["recipe"]["name"], "summary":{"steps":plan["recipe"]["parameters"]["steps"],
        "total_length":p["total_length"]}, "geometry":{"axis":"global_x","axial_interval_mm":[0,p["total_length"]],
        "volume_cm3":plan["expected_volume_cm3"]}, "creation_policy":"saved_unique_export_then_open",
        "warnings":["Full rotational body only; no bores, finishing, external-body application or new Studio block.",
                    "Inspect recognizes creation inputs, not current geometry or manual driving edits; recreate from inputs.",
                    "A native diameter/length driving probe changes geometry correctly, but manual edits can leave the sketch under-constrained; in-place editing is not certified."]}


def shaft_preview(parameters: dict) -> dict:
    return {"success":True,"summary":shaft_plan_data(shaft_plan(parameters,name="Geomwright stepped shaft"))}


def inspect_rotational_module(adapter, document_id: str, *, family, parameter_model, planner, required) -> dict:
    result = adapter.runner.call(f"inspect_{family}_module", {"document_id":document_id})
    block = result.get("block") or {}
    if not result.get("recognized"):
        return {"module":None}
    profile, error = None, block.get("recipe_error")
    recipe = block.get("recipe")
    if recipe:
        try:
            raw = recipe["parameters"]
            if not required.issubset(raw):
                raise ValueError("Missing saved rotational inputs; no default substitution")
            profile = parameter_model.model_validate(raw).model_dump(exclude_none=True)
            planner(profile,name=recipe["name"])
        except (ValueError,KeyError,TypeError) as exc:
            error, profile = str(exc)[:500], None
    return {**block,"module":family,"profile":profile,"verified":None,"editable":False,
        "recreatable":profile is not None,"recipe_error":error,
        "status":"creation_recipe_recognized" if profile else "partial_unverified"}


def inspect_shaft_module(adapter, document_id: str) -> dict:
    return inspect_rotational_module(adapter,document_id,family="stepped_shaft",parameter_model=SteppedShaftParameters,
                                     planner=shaft_plan,required={"steps"})


def verify_shaft_geometry(plan: dict, bounds: list, faces: list, volume: float) -> None:
    expected = plan["expected_volume_cm3"]
    steps = plan["recipe"]["parameters"]["steps"]
    length = math.fsum(step["length"] for step in steps)
    radius = max(step["diameter"] for step in steps)/2
    if len(bounds) != 6 or not all(math.isfinite(value) for value in bounds):
        raise RuntimeError("Shaft bounds are incomplete")
    if max(abs(a-b) for a,b in zip(bounds,[0,-radius,-radius,length,radius,radius])) > 1e-5:
        raise RuntimeError("Shaft bounds differ from input")
    if not math.isfinite(volume) or volume <= 0 or abs(volume-expected) > max(1e-7,expected*1e-5):
        raise RuntimeError("Shaft volume differs from analytic stepped cylinders")
    # Cylinder frames are not trimmed extents: read each face's boundary circles.
    cylinders = [face for face in faces if face["surface_type"] == "cylinder"]
    if not all(math.isfinite(face[key]) for face in cylinders for key in ("radius_mm","axial_min","axial_max")):
        raise RuntimeError("Shaft native dimensions are incomplete or non-finite")
    if len(cylinders) != len(steps):
        raise RuntimeError("Shaft cylinder-face count differs")
    remaining = list(cylinders)
    x = 0.0
    for step in steps:
        end = x + step["length"]
        match = next((face for face in remaining if abs(face["radius_mm"]-step["diameter"]/2)<1e-5
                      and abs(face["axial_min"]-x)<1e-5 and abs(face["axial_max"]-end)<1e-5),None)
        if match is None:
            raise RuntimeError("Shaft native step radius/axial interval differs")
        remaining.remove(match)
        x = end


def create_legacy_body_module(adapter, plan: dict, visible: bool, *, inspector, verifier) -> dict:
    family = plan["module_id"]
    path = adapter._export_dir()/f"{family}-module-{uuid4().hex}.m3d"
    document, checkpoint = None, {}
    params = dict(plan["preview"]["params"],output_path=adapter._normalize_target_path_for_kompas(str(path)),close_after_save=True)
    try:
        created = adapter.runner.call("create_part_from_scenario",{"scenario":family,"params":params,
            "preview":plan["preview"],"visible":visible,"legacy_body_module_recipe":plan["recipe"]},progress_callback=checkpoint.update)
        if not created.get("ok") or not created.get("saved"):
            raise RuntimeError("Rotational generator did not confirm saved creation")
        document = adapter.open_document(str(path),visible=visible,read_only=False)["document"]
        docid = document.get("runtime_id") or document["id"]
        block = inspector(adapter,docid)
        if not block.get("recreatable") or block["profile"] != plan["recipe"]["parameters"]:
            raise RuntimeError("Rotational creation recipe did not survive reopen")
        native = adapter.runner.call(f"inspect_{family}_module",{"document_id":docid,"creation_body_readback":True})
        body = native["body"]
        bodies = adapter.list_model_bodies(docid,limit=2)
        if bodies["pagination"]["total"] != 1 or not bodies["items"][0]["solid"]:
            raise RuntimeError("Rotational module must contain one solid body")
        body["bounds_mm"] = bodies["items"][0]["bounds_mm"]
        verifier(plan,body["bounds_mm"],native["faces"],body["volume"])
        if abs(body["volume"]-created["legacy_module_body"]["volume"]) > max(1e-7,body["volume"]*1e-5):
            raise RuntimeError("Rotational volume changed during save/reopen")
        if native["sketch_state"]["code"] != 1:  # ksStateWellConstrained, not drawing-object state
            raise RuntimeError("Rotational profile is not fully defined after reopen")
        return {"ok":True,"executed":True,"saved":True,"closed":False,"document":document,"body":body,"block":block,
            "diagnostics":{"sketch_state":native["sketch_state"],"functional_faces":native["faces"]},
            "verification":{"ok":True,"single_solid":True,"analytic_volume_verified":True,
                            "functional_dimensions_verified":True,
                             "profile_fully_defined":True,**lifecycle_verification(adapter)}}
    except Exception as exc:
        message = str(checkpoint.get("error") or exc).split(" | steps=",1)[0]
        error = RuntimeError(message[:2000])
        error.partial_result = {"document":document,"output_path":str(path),"verified":False,
            "stage":family + "_creation_or_reopen","rollback_performed":False}
        raise error from exc


def create_shaft_module(adapter, plan: dict, visible: bool) -> dict:
    result = create_legacy_body_module(adapter,plan,visible,inspector=inspect_shaft_module,verifier=verify_shaft_geometry)
    result["verification"]["step_dimensions_verified"] = True
    return result


def create_rotational_module(adapter, plan: dict, visible: bool, *, inspector, verifier) -> dict:
    result = create_legacy_body_module(adapter,plan,visible,inspector=inspector,verifier=verifier)
    result["verification"]["cone_end_dimensions_verified"] = True
    return result
