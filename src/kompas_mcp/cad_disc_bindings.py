"""Shared adapter for the existing normal-thickness disc spring profile."""
from __future__ import annotations
from .cad_session_policy import lifecycle_verification

import math
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .parametric import preview_part_scenario
from .cad_extension_bindings import inspect_extension_module


class DiscSpringParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    outer_diameter: float = Field(gt=0)
    inner_diameter: float = Field(gt=0)
    thickness: float = Field(gt=0, description="Thickness normal to the conical profile, mm.")
    cone_height: float | None = Field(default=None, gt=0)
    free_height: float | None = Field(default=None, gt=0, description="Legacy alias: cone_height = free_height - thickness; not the exact finished axial span.")
    cone_direction: Literal["up", "down"] = "up"


def disc_plan(parameters: dict, *, name: str) -> dict:
    if len({"cone_height", "free_height"} & parameters.keys()) != 1:
        raise ValueError("Specify exactly one of cone_height and legacy free_height")
    preview = preview_part_scenario("disc_spring", {**parameters, "name": name})
    p = preview["params"]
    p["sketch_name"] = "Disc spring profile"
    recipe = {"schema": "geomwright.disc.recipe", "version": 1, "parameters": parameters,
              "name": name, "profile_name": p["sketch_name"], "sweep_name": "Disc spring body"}
    points = p["profile_points"]
    moment = sum((a[1]+b[1]) * (a[0]*b[1]-b[0]*a[1]) for a,b in zip(points, points[1:])) / 6
    volume = 2*math.pi*abs(moment)/1000
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("Disc profile must have finite positive volume")
    return {"module_id": "disc_spring", "preview": preview, "recipe": recipe,
            "expected_volume_cm3": volume,
            "verification": {"single_solid": True, "positive_volume": True, "analytic_volume": True,
                             "diameters": True, "axial_bounds": True, "save_reopen_required": True}}


def disc_plan_data(plan: dict) -> dict:
    p = plan["preview"]["params"]
    x = [point[0] for point in p["profile_points"]]
    return {"name": plan["recipe"]["name"], "summary": {key: p[key] for key in
            ("outer_diameter", "inner_diameter", "thickness", "cone_height", "cone_direction", "cone_angle_degrees")},
            "geometry": {"axis": "global_x", "axial_interval_mm": [min(x),max(x)],
                         "volume_cm3": plan["expected_volume_cm3"]},
            "creation_policy": "saved_unique_export_then_open",
            "warnings": ["Engineering normal-thickness conical ring; no spring load/strength or standard conformity certification.",
                         "Legacy radius/height driving associations are not reliable for in-place edits. Recreate from input parameters; creation recipes are not CAD-driving certification."]}


def disc_preview(parameters: dict) -> dict:
    return {"success": True, "summary": disc_plan_data(disc_plan(parameters, name="Geomwright disc spring"))}


def inspect_disc_module(adapter, document_id: str) -> dict:
    return inspect_extension_module(adapter, document_id, family="disc", parameter_model=DiscSpringParameters,
        planner=disc_plan, required={"outer_diameter", "inner_diameter", "thickness", "cone_direction"})


def create_disc_module(adapter, plan: dict, visible: bool) -> dict:
    path = adapter._export_dir()/f"disc-module-{uuid4().hex}.m3d"
    document = None
    p = dict(plan["preview"]["params"])
    p.update(output_path=adapter._normalize_target_path_for_kompas(str(path)), close_after_save=True)
    try:
        created = adapter.runner.call("create_part_from_scenario", {"scenario":"disc_spring", "params":p,
            "preview":plan["preview"], "visible":visible, "disc_module_recipe":plan["recipe"]})
        if not created.get("ok") or not created.get("saved"):
            raise RuntimeError("Disc generator did not confirm saved creation")
        document = adapter.open_document(str(path), visible=visible, read_only=False)["document"]
        docid = document.get("runtime_id") or document["id"]
        block = inspect_disc_module(adapter, docid)
        if not block.get("recreatable") or block["profile"] != plan["recipe"]["parameters"]:
            raise RuntimeError("Disc recipe/owned roots did not survive reopen")
        bodies = adapter.list_model_bodies(docid, limit=2)
        if bodies["pagination"]["total"] != 1 or not bodies["items"][0]["solid"]:
            raise RuntimeError("Disc must contain one solid body")
        body_item = bodies["items"][0]
        bounds = body_item["bounds_mm"]
        x = [point[0] for point in p["profile_points"]]
        r = p["outer_diameter"]/2
        expected_bounds = [min(x),-r,-r,max(x),r,r]
        if max(abs(a-b) for a,b in zip(bounds,expected_bounds)) > 1e-5:
            raise RuntimeError("Disc bounds differ from the planned normal-thickness profile")
        edges = adapter.list_body_edges(body=body_item["selector"], document_id=docid, limit=50)
        radii = [edge["radius_mm"] for edge in edges["items"]
                 if edge.get("curve_type") in ("circle","arc") and edge.get("radius_mm") is not None]
        if not radii or abs(min(radii)-p["inner_diameter"]/2) > 1e-5 or abs(max(radii)-r) > 1e-5:
            raise RuntimeError("Disc native circular-edge diameters differ")
        body = adapter.runner.call("inspect_disc_module", {"document_id":docid,"creation_body_readback":True})["body"]
        volume = body["volume"]
        expected = plan["expected_volume_cm3"]
        before_volume = created["compression_module_body"]["volume"]
        if not math.isfinite(volume) or volume <= 0 or abs(volume-expected) > max(1e-7,expected*1e-5):
            raise RuntimeError("Disc native volume differs from the analytical profile volume")
        if abs(volume-before_volume) > max(1e-7,before_volume*1e-5):
            raise RuntimeError("Disc volume changed during save/reopen")
        body["bounds_mm"] = bounds
        return {"ok":True,"executed":True,"saved":True,"closed":False,"document":document,"body":body,"block":block,
                "verification":{"ok":True,"native_rebuild":True,"single_solid":True,"positive_volume":True,
                    "analytic_volume_verified":True,"native_diameters_verified":True,"axial_bounds_verified":True,
                    **lifecycle_verification(adapter)}}
    except Exception as exc:
        message = str(exc)
        marker = "RuntimeError: create_part_from_scenario failed at "
        if marker in message:
            message = "Disc creation failed at " + message.rsplit(marker,1)[1].split(" | steps=",1)[0]
        error = RuntimeError(message[:2000])
        error.partial_result = {"document":document,"output_path":str(path),"verified":False,
                                "stage":"disc_creation_or_reopen","rollback_performed":False}
        raise error from exc
