"""Compression-family interface over the existing saved legacy construction path."""
from __future__ import annotations
from .cad_session_policy import lifecycle_verification

import json
import math
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .parametric import preview_part_scenario


class CompressionSpringParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    variant: Literal["cylindrical", "two_zone", "conical"] = "cylindrical"
    wire_diameter: float = Field(gt=0)
    end_pitch_gap: float = Field(default=0.01, ge=0, description="Axial end-pitch increment in mm: end pitch = wire diameter + this value. Not a certified minimum surface clearance.")
    mean_diameter: float | None = Field(default=None, gt=0)
    outer_diameter: float | None = Field(default=None, gt=0)
    inner_diameter: float | None = Field(default=None, gt=0)
    large_mean_diameter: float | None = Field(default=None, gt=0)
    small_mean_diameter: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0, description="Wire-centreline axial span in mm.")
    free_length: float | None = Field(default=None, gt=0, description="Legacy centreline-span alias, NOT the physical end-to-end length; prefer height.")
    standard_length: float | None = Field(default=None, gt=0, description="Physical end-to-end length in the legacy grinding/extreme-plane model; mutually exclusive with height/free_length.")
    turns: float | None = Field(default=None, gt=0)
    working_turns: float | None = Field(default=None, gt=0)
    pitch: float | None = Field(default=None, gt=0, description="Optional consistency check for the derived working pitch; length and turns drive it.")
    working_turns_1: float | None = Field(default=None, gt=0)
    pitch_1: float | None = Field(default=None, gt=0)
    working_turns_2: float | None = Field(default=None, gt=0)
    pitch_2: float | None = Field(default=None, gt=0)
    pitch_mode: Literal["constant_pitch", "constant_angle"] | None = None
    large_at_start: bool = True
    end_turns_per_side: float | None = Field(default=None, ge=0)
    ground_turns_per_side: float | None = Field(default=None, ge=0)
    start_end_turns: float | None = Field(default=None, ge=0)
    finish_end_turns: float | None = Field(default=None, ge=0)
    start_ground_turns: float | None = Field(default=None, ge=0)
    finish_ground_turns: float | None = Field(default=None, ge=0)
    turn_direction: Literal["right", "left"] = "right"
    start_phase_degrees: float = 0.0
    transition_fillet_radius: float | None = Field(default=None, gt=0)
    transition_fillet_radius_factor: float | None = Field(default=None, gt=0)
    transition_connector_builder: Literal["auto", "curve_fillet", "trimmed_connect_curve"] = "auto"


SCENARIOS = {"cylindrical": "compression_spring", "two_zone": "compression_spring_variable_pitch",
             "conical": "conical_compression_spring"}


def spring_plan(parameters: dict, *, name: str) -> dict:
    variant = parameters["variant"]
    profile = {key: value for key, value in parameters.items() if key != "variant"}
    conical_fields = {"large_mean_diameter", "small_mean_diameter", "pitch_mode", "transition_fillet_radius_factor"}
    zone_fields = {"working_turns_1", "pitch_1", "working_turns_2", "pitch_2"}
    if variant != "conical" and conical_fields & profile.keys():
        raise ValueError("Cone dimensions/pitch_mode/fillet factor apply only to variant=conical")
    if variant != "two_zone" and zone_fields & profile.keys():
        raise ValueError("Zone dimensions apply only to variant=two_zone")
    if variant == "conical" and {"mean_diameter", "outer_diameter", "inner_diameter"} & profile.keys():
        raise ValueError("Use small_mean_diameter and large_mean_diameter for a conical spring")
    if variant != "conical" and len({"mean_diameter", "outer_diameter", "inner_diameter"} & profile.keys()) != 1:
        raise ValueError("Specify exactly one of mean_diameter, outer_diameter or inner_diameter")
    if variant == "conical" and not {"small_mean_diameter", "large_mean_diameter"}.issubset(profile):
        raise ValueError("conical requires small_mean_diameter and large_mean_diameter")
    if len({"height", "free_length", "standard_length"} & profile.keys()) > 1:
        raise ValueError("Specify exactly one length input: height, legacy free_length or standard_length")
    if "turns" in profile and "working_turns" in profile:
        raise ValueError("Specify turns or working_turns, not both")
    if variant == "two_zone" and not zone_fields.issubset(profile):
        raise ValueError("two_zone requires working_turns_1, pitch_1, working_turns_2 and pitch_2")
    profile.update(name=name)
    preview = preview_part_scenario(SCENARIOS[variant], profile)
    params = preview["params"]
    if "pitch" in profile and not math.isclose(profile["pitch"], params["pitch"], rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("Requested pitch conflicts with the working pitch derived from length and turns")
    if not params.get("live_supported", True):
        raise ValueError("This spring layout is preview-only")
    recipe = {"schema": "geomwright.compression.recipe", "version": 1,
              "parameters": parameters, "name": name,
              "profile_name": params["profile_name"], "sweep_name": params["sweep_name"]}
    if len(json.dumps(recipe, ensure_ascii=True, allow_nan=False)) > 24000:
        raise ValueError("Spring recipe exceeds 24000 characters")
    return {"stage": "compression_module_plan", "preview": preview, "recipe": recipe,
            "verification": {"single_solid": True, "positive_volume": True, "saved_recipe": True,
                             "radial_bounds": "within input wire envelope", "save_reopen_required": True}}


def spring_plan_data(plan: dict) -> dict:
    preview = plan["preview"]
    summary = {key: value for key, value in preview["summary"].items()
               if not key.endswith(("_expression", "_variable"))}
    return {"name": plan["recipe"]["name"], "summary": summary,
            "geometry": {"axis": "global_x", "frame": "legacy_global_origin", "wire_diameter": preview["params"]["wire_diameter"]},
            "creation_policy": "saved_unique_export_then_open", "warnings": [
                "Geometric spring construction, not a strength, fatigue or load calculation.",
                "Inspect recognizes a creation recipe; it does not audit driving formulas or later edits."]}


def spring_preview(parameters: dict) -> dict:
    return {"success": True, "summary": spring_plan_data(spring_plan(parameters, name="Geomwright compression spring"))}


def inspect_spring_module(adapter: Any, document_id: str) -> dict:
    result = adapter.runner.call("inspect_compression_module", {"document_id": document_id})
    block = result.get("block") or {}
    if not result.get("recognized"):
        return {"module": None}
    recipe = block.get("recipe")
    parameters = None
    error = block.get("recipe_error")
    if recipe:
        try:
            raw = recipe["parameters"]
            if not {"variant", "wire_diameter", "large_at_start", "turn_direction", "start_phase_degrees",
                    "transition_connector_builder"}.issubset(raw):
                raise ValueError("Incomplete saved spring inputs; no default substitution")
            # Earlier version-1 recipes predate this field and used pitch=wire.
            raw = {"end_pitch_gap": 0.0, **raw}
            parameters = CompressionSpringParameters.model_validate(raw).model_dump(exclude_none=True)
            spring_plan(parameters, name=recipe["name"])
        except (ValueError, KeyError, TypeError) as exc:
            error = str(exc)[:500]
            parameters = None
    return {**block, "module": "compression_spring", "profile": parameters, "verified": None,
            "editable": False, "recreatable": parameters is not None, "recipe_error": error,
            "status": "creation_recipe_recognized" if parameters is not None else "partial_unverified"}


def create_spring_module(adapter: Any, plan: dict, visible: bool) -> dict:
    # The established post-save anchor-binding path must not be skipped.
    extension = plan.get("module_id") in ("extension_spring", "torsion_spring")
    family = plan["module_id"].removesuffix("_spring") if extension else "compression"
    inspect_module = inspect_spring_module
    if extension:
        from .cad_extension_bindings import inspect_extension_module, verify_extension_readback
        inspect_module = inspect_extension_module
        if family == "torsion":
            from .cad_torsion_bindings import inspect_torsion_module
            inspect_module = inspect_torsion_module
    path = adapter._export_dir() / f"{family}-module-{uuid4().hex}.m3d"
    params = dict(plan["preview"]["params"])
    params.update(output_path=adapter._normalize_target_path_for_kompas(str(path)), close_after_save=True)
    document = None
    try:
        created = adapter.runner.call("create_part_from_scenario", {
            "scenario": plan["preview"]["scenario"], "params": params, "preview": plan["preview"],
            "visible": visible, f"{family}_module_recipe": plan["recipe"]})
        if not created.get("ok") or not created.get("saved"):
            raise RuntimeError("Legacy spring generator did not confirm a saved result")
        document = adapter.open_document(str(path), visible=visible, read_only=False)["document"]
        docid = document.get("runtime_id") or document["id"]
        block = inspect_module(adapter, docid)
        if not block.get("recreatable") or block["profile"] != plan["recipe"]["parameters"]:
            raise RuntimeError("Spring saved recipe/owned roots did not survive reopen")
        bodies = adapter.list_model_bodies(docid, limit=2)
        if bodies["pagination"]["total"] != 1 or not bodies["items"][0]["solid"]:
            raise RuntimeError("Reopened spring must contain one solid body")
        bounds = bodies["items"][0]["bounds_mm"]
        readback = adapter.runner.call(f"inspect_{family}_module", {
            "document_id": docid, "creation_body_readback": True})
        if extension:
            verify_extension_readback(params, bounds, readback)
            if family == "torsion":
                from .cad_torsion_bindings import verify_torsion_legs
                verify_torsion_legs(params, readback)
        wire = params["wire_diameter"]
        radius = max(params.get("outer_diameter") or 0,
                     (params.get("large_mean_diameter") or 0)+wire) / 2
        if not extension and max(abs(v) for v in (bounds[1], bounds[2], bounds[4], bounds[5])) > radius + .01:
            raise RuntimeError("Spring radial bounds exceed the input wire envelope")
        height = params["height"]
        start_ground = params.get("start_ground_turns") or 0
        finish_ground = params.get("finish_ground_turns") or 0
        end_pitch = params.get("end_pitch", wire)
        if start_ground > 0:
            if abs(bounds[0] - (start_ground*end_pitch-wire/2)) > .01:
                raise RuntimeError("Spring start ground plane differs from the planned axial end")
        elif not extension and not -wire/2-.01 <= bounds[0] <= wire/2+.01:
            raise RuntimeError("Spring start lies outside the input axial envelope")
        if finish_ground > 0:
            if abs(bounds[3] - (height-finish_ground*end_pitch+wire/2)) > .01:
                raise RuntimeError("Spring finish ground plane differs from the planned axial end")
        elif not extension and not height-wire/2-.01 <= bounds[3] <= height+wire/2+.01:
            raise RuntimeError("Spring finish lies outside the input axial envelope")
        body = dict(readback["body"])
        volume = body.get("volume")
        before_volume = created["compression_module_body"]["volume"]
        if (body.get("body_count") != 1 or not body.get("solid") or not isinstance(volume, (int, float))
                or not math.isfinite(volume) or volume <= 0
                or abs(volume-before_volume) > max(1e-6, before_volume*1e-5)):
            raise RuntimeError("Spring body volume changed during save/anchor-binding/reopen")
        body["bounds_mm"] = bounds
        return {"ok": True, "executed": True, "saved": True, "closed": False, "document": document,
                "body": body, "block": block, "verification": {"ok": True, "single_solid": True,
                    "positive_volume": True, "native_rebuild": True,
                    "radial_bounds_verified": not extension, "volume_preserved_after_bindings": True,
                    "axial_end_bounds_verified": not extension, "native_coil_dimensions_verified": extension,
                    "native_leg_endpoints_verified": family == "torsion",
                    **lifecycle_verification(adapter)}}
    except Exception as exc:
        message = str(exc)
        marker = "RuntimeError: create_part_from_scenario failed at "
        if marker in message:
            message = "Legacy spring creation failed at " + message.rsplit(marker, 1)[1].split(" | steps=", 1)[0]
        error = RuntimeError(message[:2000])
        error.partial_result = {"document": document, "output_path": str(path), "verified": False,
                                "stage": "legacy_creation_or_reopen", "rollback_performed": False,
                                "cause_partial_result": getattr(exc, "partial_result", None)}
        raise error from exc
