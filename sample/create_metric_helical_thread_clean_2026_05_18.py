from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.metric_thread_geometry import build_metric_thread_geometry


OUTPUT_DIR = ROOT / "sample" / "generated" / "metric_helical_thread_clean_2026_05_18"
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
            "name": f"Clean external {designation} {direction}",
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
            "name": f"Clean internal {designation} {direction}",
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
    _external_payload("ext_m12x1_right", diameter=12.0, pitch=1.0, length=10.0, direction="right"),
    _internal_payload("int_m16x2_right", diameter=16.0, pitch=2.0, length=10.0, direction="right"),
    _internal_payload("int_m16x1_left", diameter=16.0, pitch=1.0, length=10.0, direction="left"),
]


def _ensure_new_output_directory() -> None:
    if OUTPUT_DIR.exists():
        raise RuntimeError(f"Output directory already exists: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    CONFIG_DIR.mkdir(parents=True, exist_ok=False)


def _write_config(payload: dict) -> Path:
    config_path = CONFIG_DIR / payload["output_name"].replace(".m3d", ".json")
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
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
    summary = preview.get("summary") or {}
    hide_step = next(
        (step for step in result.get("steps", []) if step.get("step") == "hide_helical_thread_auxiliary_geometry"),
        {},
    )
    hidden_objects = list(hide_step.get("objects") or [])
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
        "direction": summary.get("direction"),
        "left_thread": bool((preview.get("params") or {}).get("left_thread")),
        "thread_reference_diameter": summary.get("thread_reference_diameter"),
        "carrier_diameter": summary.get("carrier_diameter"),
        "profile_sketch_origin_shift": summary.get("profile_sketch_origin_shift"),
        "auxiliary_geometry_hidden_requested": bool((preview.get("params") or {}).get("auxiliary_geometry_hidden")),
        "auxiliary_visibility_ok": bool(hide_step.get("ok")),
        "auxiliary_hidden_count": sum(1 for item in hidden_objects if item.get("ok")),
        "auxiliary_hidden_roles": [str(item.get("role") or "") for item in hidden_objects if item.get("ok")],
        "auxiliary_visibility_report": hide_step,
    }


def _write_readme(items: list[dict]) -> None:
    lines = [
        "Clean metric helical-thread examples generated after auxiliary-geometry hiding update.",
        "Expected hidden service objects: start_center_point, profile_origin_point, profile_lcs, profile_sketch, spiral_axis, spiral_path.",
        "",
    ]
    for item in items:
        handed = "left" if item["left_thread"] else "right"
        kind = "external" if item["scenario"] == "external_helical_thread" else "internal"
        lines.append(
            f"- {Path(item['output_path']).name}: {kind} {handed}, "
            f"M{item['diameter']:g}x{item['pitch']:g}, length={item['length']}, "
            f"aux_hidden={item['auxiliary_hidden_count']}/6, aux_ok={item['auxiliary_visibility_ok']}"
        )
    readme_path = OUTPUT_DIR / "README.txt"
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _ensure_new_output_directory()
    adapter = KompasAdapter()
    items = []
    for payload in EXAMPLES:
        item = _create_example(adapter, payload)
        items.append(item)
        print(
            "{0} :: saved={1} :: aux_hidden={2}/6 :: aux_ok={3}".format(
                Path(item["output_path"]).name,
                item["saved"],
                item["auxiliary_hidden_count"],
                item["auxiliary_visibility_ok"],
            )
        )
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_readme(items)
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
