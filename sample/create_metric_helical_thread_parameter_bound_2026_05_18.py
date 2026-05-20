from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.metric_thread_geometry import build_metric_thread_geometry


OUTPUT_DIR = ROOT / "sample" / "generated" / "metric_helical_thread_parameter_bound_2026_05_18"
CONFIG_DIR = OUTPUT_DIR / "configs"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    return slug or "thread"


def _external_payload(name: str, *, diameter: float, pitch: float, length: float, direction: str) -> dict:
    designation = f"M{diameter:g}x{pitch:g}"
    slug = _slugify(name)
    return {
        "name": name,
        "scenario": "external_helical_thread",
        "output_name": f"{slug}.m3d",
        "params": {
            "name": f"Parameter-bound external {designation} {direction}",
            "designation": designation,
            "diameter": diameter,
            "pitch": pitch,
            "length": length,
            "direction": direction,
            "auxiliary_geometry_hidden": True,
            "source_scenario": "stepped_shaft",
            "source_params": {
                "name": f"Carrier external {designation}",
                "steps": [
                    {"length": round(length + pitch * 2.0, 3), "diameter": diameter},
                    {"length": round(max(8.0, diameter * 0.45), 3), "diameter": round(diameter + 8.0, 3)},
                ],
            },
        },
    }


def _internal_payload(name: str, *, diameter: float, pitch: float, length: float, direction: str) -> dict:
    designation = f"M{diameter:g}x{pitch:g}"
    geometry = build_metric_thread_geometry(diameter, pitch)
    minor_diameter = float(geometry["internal_minor_diameter"])
    outer_diameter = round(max(diameter + 16.0, diameter * 2.2), 3)
    slug = _slugify(name)
    return {
        "name": name,
        "scenario": "internal_helical_thread",
        "output_name": f"{slug}.m3d",
        "params": {
            "name": f"Parameter-bound internal {designation} {direction}",
            "designation": designation,
            "diameter": diameter,
            "pitch": pitch,
            "length": length,
            "direction": direction,
            "auxiliary_geometry_hidden": True,
            "source_scenario": "internal_cylindrical_step",
            "source_params": {
                "name": f"Carrier internal {designation}",
                "steps": [{"length": round(length + pitch * 2.0, 3), "diameter": minor_diameter}],
                "source_scenario": "stepped_shaft",
                "source_params": {
                    "steps": [{"length": round(length + pitch * 4.0, 3), "diameter": outer_diameter}],
                },
            },
        },
    }


EXAMPLES = [
    _external_payload("ext_m20x2_left", diameter=20.0, pitch=2.0, length=12.0, direction="left"),
    _internal_payload("int_m16x2_right", diameter=16.0, pitch=2.0, length=10.0, direction="right"),
]


def _ensure_new_output_directory() -> None:
    if OUTPUT_DIR.exists():
        raise RuntimeError(f"Output directory already exists: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    CONFIG_DIR.mkdir(parents=True, exist_ok=False)


def _write_config(payload: dict) -> Path:
    config_path = CONFIG_DIR / payload["output_name"].replace(".m3d", ".json")
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return config_path


def _create_example(adapter: KompasAdapter, payload: dict) -> dict:
    output_path = OUTPUT_DIR / payload["output_name"]
    result = adapter.create_part_from_scenario(
        payload["scenario"],
        payload["params"],
        output_path=str(output_path),
        visible=False,
        close_after_save=True,
    )
    preview = result.get("preview") or {}
    params = preview.get("params") or {}
    summary = preview.get("summary") or {}
    binding_step = next(
        (step for step in result.get("steps", []) if step.get("step") == "bind_operation_variables" and step.get("target") == "spiral_path"),
        {},
    )
    source_bindings = list(params.get("source_variable_bindings") or [])
    operation_bindings = list(params.get("operation_variable_bindings") or [])
    applied_bindings = list(binding_step.get("applied") or [])
    return {
        "name": payload["name"],
        "scenario": payload["scenario"],
        "ok": bool(result.get("ok")),
        "saved": bool(result.get("saved")),
        "output_path": str(output_path),
        "config_path": str(_write_config(payload)),
        "diameter": summary.get("diameter"),
        "pitch": summary.get("pitch"),
        "length": summary.get("length"),
        "source_variable_bindings": source_bindings,
        "operation_variable_bindings": operation_bindings,
        "operation_binding_ok": bool(binding_step.get("ok")),
        "operation_binding_applied_count": int(binding_step.get("applied_count") or 0),
        "operation_binding_failed_count": int(binding_step.get("failed_count") or 0),
        "operation_binding_report": binding_step,
        "operation_binding_expressions_after": [item.get("expression_after") for item in applied_bindings],
    }


def main() -> None:
    _ensure_new_output_directory()
    adapter = KompasAdapter()
    items = []
    for payload in EXAMPLES:
        item = _create_example(adapter, payload)
        items.append(item)
        print(
            "{0} :: saved={1} :: op_bind={2}/2 :: source_bind={3}".format(
                Path(item["output_path"]).name,
                item["saved"],
                item["operation_binding_applied_count"],
                len(item["source_variable_bindings"]),
            )
        )
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
