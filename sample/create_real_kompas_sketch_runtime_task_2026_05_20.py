from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.document_readback import readback_saved_document
from kompas_mcp.operation_runtime import (
    DocumentReadbackContractSpec,
    OperationContractSpec,
    OperationInvariantSpec,
    ThreadGeometryProbeSpec,
)
from kompas_mcp.sketch_runtime import (
    FlatV60ThreadProfileSpec,
    build_flat_v60_thread_profile_preflight,
    verify_sketch_preflight,
)
from kompas_mcp.thread_profile_geometry import build_metric_thread_geometry
from kompas_mcp.verified_runner import run_verified_kompas_task


BASE_OUTPUT_DIR = ROOT / "sample" / "generated" / "real_kompas_sketch_runtime_task_2026_05_20"
RUN_INDEX_NAME = "real_kompas_sketch_runtime_runs_index.json"
AUXILIARY_ROLES = (
    "start_center_point",
    "profile_origin_point",
    "spiral_axis",
    "spiral_path",
    "profile_lcs",
    "profile_sketch",
)


def _build_thread_payload() -> dict[str, Any]:
    diameter = 12.0
    pitch = 1.0
    length = 14.0
    designation = "M12x1"
    return {
        "name": "real_ext_m12x1_sketch_runtime_checked",
        "scenario": "external_helical_thread",
        "output_name": "real_ext_m12x1_sketch_runtime_checked.m3d",
        "params": {
            "name": "Real external M12x1 after sketch-runtime preflight",
            "designation": designation,
            "diameter": diameter,
            "pitch": pitch,
            "length": length,
            "direction": "right",
            "auxiliary_geometry_hidden": True,
            "source_scenario": "stepped_shaft",
            "source_params": {
                "name": "Carrier shaft M12x1",
                "steps": [
                    {"length": 18.0, "diameter": diameter},
                    {"length": 8.0, "diameter": 20.0},
                ],
            },
        },
    }


def _run_profile_preflight() -> dict[str, Any]:
    geometry = build_metric_thread_geometry(12.0, 1.0)
    depth = float(geometry["external_thread_depth"])
    profile = FlatV60ThreadProfileSpec(
        pitch=1.0,
        crest_y=0.0,
        root_y=-depth,
        outer_half_width=0.5,
        root_half_width=0.125,
    )
    plan = build_flat_v60_thread_profile_preflight(profile)
    report = verify_sketch_preflight(plan, stage="real_kompas_task_preflight")
    if not report.ok:
        raise RuntimeError("sketch_runtime preflight failed before KOMPAS call")
    return {
        "geometry": geometry,
        "profile": {
            "pitch": profile.pitch,
            "crest_y": profile.crest_y,
            "root_y": profile.root_y,
            "outer_half_width": profile.outer_half_width,
            "root_half_width": profile.root_half_width,
            "frame_id": profile.frame_id,
        },
        "report": report.to_dict(),
    }


def main() -> None:
    payload = _build_thread_payload()
    params = payload["params"]
    preflight = _run_profile_preflight()
    adapter = KompasAdapter()

    run = run_verified_kompas_task(
        payload=payload,
        preflight=preflight,
        output_base_dir=BASE_OUTPUT_DIR,
        create_part=adapter.create_part_from_scenario,
        invariant_spec=OperationInvariantSpec(
            scenario=payload["scenario"],
            required_steps=(
                "create_part_document",
                "cut_evolution",
                "hide_helical_thread_auxiliary_geometry",
            ),
            require_auxiliary_hidden=True,
            expected_auxiliary_roles=AUXILIARY_ROLES,
            expected_operation_values={
                "cut_evolution": {
                    "diameter": params["diameter"],
                    "pitch": params["pitch"],
                    "length": params["length"],
                    "direction": params["direction"],
                }
            },
        ),
        thread_geometry_spec=ThreadGeometryProbeSpec(
            diameter=params["diameter"],
            pitch=params["pitch"],
            length=params["length"],
            direction=params["direction"],
            depth=float(preflight["geometry"]["external_thread_depth"]),
            min_source_total_length=params["length"],
        ),
        contract_spec=OperationContractSpec(
            scenario=payload["scenario"],
            required_sections=(
                "sketch_runtime_preflight",
                "operation_invariants",
                "thread_geometry_probes",
            ),
            required_artifact_roles=("model",),
            min_counts={
                "steps": 20,
                "operations": 8,
                "variables": 7,
                "auxiliary_objects": 6,
                "hidden_auxiliary_objects": 6,
            },
            expected_operation_names=(
                "create_source_body",
                "create_spiral_path",
                "create_thread_profile",
                "cut_evolution",
            ),
            expected_variable_names=(
                "Diameter_thread_external_right_M12x1_1",
                "Pitch_thread_external_right_M12x1_1",
                "Length_thread_external_right_M12x1_1",
            ),
            expected_auxiliary_roles=AUXILIARY_ROLES,
        ),
        run_index_name=RUN_INDEX_NAME,
        document_readback=lambda model_path: readback_saved_document(adapter, model_path),
        document_readback_contract_spec=DocumentReadbackContractSpec(min_documents=1, min_items=1, min_tree_nodes=1),
        require_document_readback=True,
        created_elements=(
            "stepped shaft carrier",
            "external helical thread",
            "profile sketch",
            "helix path",
            "thread cut operation",
        ),
        stage_prefix="real_kompas_task",
        visible=False,
        close_after_save=True,
    )
    print(json.dumps(run["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
