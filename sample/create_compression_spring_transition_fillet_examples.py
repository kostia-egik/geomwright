from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.parametric import preview_part_scenario


OUTPUT_ROOT = ROOT / "sample" / "generated"

EXAMPLES: list[dict[str, Any]] = [
    {
        "name": "spring_right_transition_fillet",
        "output_name": "spring_right_transition_fillet.m3d",
        "transition_step": "create_curve_fillet_path",
        "params": {
            "mean_diameter": 30,
            "wire_diameter": 4,
            "free_length": 54,
            "working_turns": 5.5,
            "end_turns_per_side": 0.75,
            "ground_turns_per_side": 0.5,
            "start_phase_degrees": -90,
            "turn_direction": "right",
            "transition_fillet_radius": 4.0,
        },
    },
    {
        "name": "spring_left_transition_fillet",
        "output_name": "spring_left_transition_fillet.m3d",
        "transition_step": "create_curve_fillet_path",
        "params": {
            "mean_diameter": 30,
            "wire_diameter": 4,
            "free_length": 54,
            "working_turns": 5.5,
            "end_turns_per_side": 0.75,
            "ground_turns_per_side": 0.5,
            "start_phase_degrees": -90,
            "turn_direction": "left",
            "transition_fillet_radius": 6.0,
        },
    },
]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _find_step(steps: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for step in steps:
        if step.get("step") == name:
            return step
    return None


def _verify_result(
    preview: dict[str, Any],
    result: dict[str, Any],
    *,
    transition_step_name: str,
) -> dict[str, Any]:
    steps = list(result.get("steps") or [])
    contour_step = _find_step(steps, "build_spring_path_contour") or {}
    sweep_step = _find_step(steps, "boss_evolution") or {}
    connector_steps = [step for step in steps if step.get("step") == transition_step_name]

    if not bool(result.get("ok")):
        raise RuntimeError(f"Live build failed: {result.get('error') or result}")
    if not bool(result.get("saved")):
        raise RuntimeError("Live build did not save the model")
    if int((preview.get("summary") or {}).get("connector_count") or 0) != 2:
        raise RuntimeError("Preview did not plan the expected two transitions")
    if int(contour_step.get("source_path_count") or 0) != 5:
        raise RuntimeError(f"Unexpected contour source_path_count: {contour_step}")
    if int(contour_step.get("connector_count") or 0) != 2:
        raise RuntimeError(f"Unexpected contour connector_count: {contour_step}")
    if len(connector_steps) != 2:
        raise RuntimeError(
            f"Expected two {transition_step_name} steps, got {len(connector_steps)}"
        )
    if not bool(sweep_step.get("ok")):
        raise RuntimeError(f"boss_evolution failed: {sweep_step}")

    return {
        "ok": bool(result.get("ok")),
        "saved": bool(result.get("saved")),
        "connector_count": int(contour_step.get("connector_count") or 0),
        "source_path_count": int(contour_step.get("source_path_count") or 0),
        "edges_count": contour_step.get("edges_count"),
        "expected_edges_count": contour_step.get("expected_edges_count"),
        "sweep_ok": bool(sweep_step.get("ok")),
    }


def main() -> None:
    run_dir = OUTPUT_ROOT / (
        "compression_spring_transition_fillet_live_" + datetime.now().strftime("%Y_%m_%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)

    adapter = KompasAdapter()
    manifest: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for example in EXAMPLES:
        bundle_dir = run_dir / example["name"]
        bundle_dir.mkdir(parents=True, exist_ok=False)
        request = {
            "scenario": "compression_spring",
            "params": dict(example["params"]),
            "output_name": example["output_name"],
        }
        output_path = bundle_dir / example["output_name"]
        _write_json(bundle_dir / "request.json", request)

        try:
            preview = preview_part_scenario("compression_spring", request["params"])
            _write_json(bundle_dir / "preview.json", preview)
            result = adapter.create_part_from_scenario(
                "compression_spring",
                request["params"],
                output_path=str(output_path),
                visible=False,
                close_after_save=True,
                save_partial_on_error=True,
                return_partial_result_on_error=True,
            )
            _write_json(bundle_dir / "result.json", result)
            verification = _verify_result(
                preview,
                result,
                transition_step_name=str(example["transition_step"]),
            )
            manifest.append(
                {
                    "name": example["name"],
                    "bundle_dir": str(bundle_dir),
                    "model_path": str(output_path),
                    "verification": verification,
                }
            )
            print(
                "{name} :: saved={saved} :: contour_paths={source_path_count} :: edges={edges_count} :: sweep_ok={sweep_ok}".format(
                    name=example["name"],
                    saved=verification["saved"],
                    source_path_count=verification["source_path_count"],
                    edges_count=verification["edges_count"],
                    sweep_ok=verification["sweep_ok"],
                )
            )
        except Exception as exc:
            failure = {
                "name": example["name"],
                "bundle_dir": str(bundle_dir),
                "model_path": str(output_path),
                "error": str(exc),
            }
            failures.append(failure)
            _write_json(bundle_dir / "failure.json", failure)
            print(f"{example['name']} :: FAILED :: {exc}")

    summary = {
        "run_dir": str(run_dir),
        "example_count": len(EXAMPLES),
        "success_count": len(manifest),
        "failure_count": len(failures),
        "examples": manifest,
        "failures": failures,
    }
    _write_json(run_dir / "summary.json", summary)

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
