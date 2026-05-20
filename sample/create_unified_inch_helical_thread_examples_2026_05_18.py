from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.thread_profile_geometry import resolve_thread_profile_geometry


OUTPUT_DIR = ROOT / "sample" / "generated" / "unified_inch_helical_thread_examples_2026_05_18"
CONFIG_DIR = OUTPUT_DIR / "configs"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    return slug or "thread"


def _geometry(designation: str) -> dict[str, Any]:
    return dict(resolve_thread_profile_geometry({"designation": designation})["geometry"])


def _external_payload(
    name: str,
    *,
    designation: str,
    length: float,
    direction: str = "right",
) -> dict[str, Any]:
    geometry = _geometry(designation)
    diameter = float(geometry["major_diameter"])
    pitch = float(geometry["pitch"])
    shoulder_diameter = round(max(diameter + 8.0, diameter * 1.8), 3)
    shoulder_length = round(max(7.0, diameter * 0.65), 3)
    slug = _slugify(name)
    return {
        "name": name,
        "scenario": "external_helical_thread",
        "output_name": f"{slug}.m3d",
        "params": {
            "name": f"Unified inch external {designation} {direction}",
            "designation": designation,
            "length": length,
            "direction": direction,
            "auxiliary_geometry_hidden": True,
            "source_scenario": "stepped_shaft",
            "source_params": {
                "name": f"Carrier external {designation}",
                "steps": [
                    {"length": round(length + pitch * 2.0, 3), "diameter": round(diameter, 3)},
                    {"length": shoulder_length, "diameter": shoulder_diameter},
                ],
            },
        },
    }


def _internal_payload(
    name: str,
    *,
    designation: str,
    length: float,
    direction: str = "right",
) -> dict[str, Any]:
    geometry = _geometry(designation)
    pitch = float(geometry["pitch"])
    major_diameter = float(geometry["major_diameter"])
    minor_diameter = float(geometry["internal_minor_diameter"])
    outer_diameter = round(max(major_diameter + 14.0, major_diameter * 2.5), 3)
    slug = _slugify(name)
    return {
        "name": name,
        "scenario": "internal_helical_thread",
        "output_name": f"{slug}.m3d",
        "params": {
            "name": f"Unified inch internal {designation} {direction}",
            "designation": designation,
            "length": length,
            "direction": direction,
            "auxiliary_geometry_hidden": True,
            "source_scenario": "internal_cylindrical_step",
            "source_params": {
                "name": f"Carrier internal {designation}",
                "steps": [{"length": round(length + pitch * 2.0, 3), "diameter": round(minor_diameter, 3)}],
                "source_scenario": "stepped_shaft",
                "source_params": {
                    "steps": [{"length": round(length + pitch * 4.0, 3), "diameter": outer_diameter}],
                },
            },
        },
    }


EXAMPLES = [
    _external_payload("ext_1_4_20_unc_right", designation="1/4-20 UNC", length=12.0, direction="right"),
    _external_payload("ext_3_8_24_unf_left", designation="3/8-24 UNF", length=14.0, direction="left"),
    _external_payload("ext_1_2_28_unef_right", designation="1/2-28 UNEF", length=16.0, direction="right"),
    _internal_payload("int_no10_32_unf_right", designation="#10-32 UNF", length=9.0, direction="right"),
    _internal_payload("int_5_16_18_unc_right", designation="5/16-18 UNC", length=12.0, direction="right"),
    _internal_payload("int_1_4_32_unef_left", designation="1/4-32 UNEF", length=10.0, direction="left"),
]


def _ensure_new_output_directory() -> None:
    if OUTPUT_DIR.exists():
        raise RuntimeError(f"Output directory already exists: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    CONFIG_DIR.mkdir(parents=True, exist_ok=False)


def _write_config(payload: dict[str, Any]) -> Path:
    config_path = CONFIG_DIR / payload["output_name"].replace(".m3d", ".json")
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return config_path


def _create_example(adapter: KompasAdapter, payload: dict[str, Any]) -> dict[str, Any]:
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
    params = preview.get("params") or {}
    thread_geometry = dict((summary.get("profile") or {}).get("thread_geometry") or params.get("thread_geometry") or {})
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
        "thread_designation": summary.get("thread_designation") or params.get("designation"),
        "profile_family": params.get("thread_profile_family"),
        "thread_series": params.get("thread_series"),
        "source_units": params.get("thread_source_units"),
        "resolved_from": params.get("thread_profile_resolved_from"),
        "major_diameter_mm": summary.get("diameter"),
        "pitch_mm": summary.get("pitch"),
        "major_diameter_inch": thread_geometry.get("major_diameter_inch"),
        "tpi": thread_geometry.get("tpi"),
        "length": summary.get("length"),
        "direction": summary.get("direction"),
        "thread_reference_diameter": summary.get("thread_reference_diameter"),
        "carrier_diameter": summary.get("carrier_diameter"),
        "auxiliary_visibility_ok": bool(hide_step.get("ok")),
        "auxiliary_hidden_count": sum(1 for item in hidden_objects if item.get("ok")),
    }


def _write_readme(items: list[dict[str, Any]]) -> None:
    lines = [
        "Unified inch V60 helical-thread visual examples.",
        "All dimensions used by KOMPAS operations are normalized to millimeters.",
        "",
    ]
    for item in items:
        kind = "external" if item["scenario"] == "external_helical_thread" else "internal"
        lines.append(
            "- {name}: {kind} {direction}, {designation}, d={diameter:.3f} mm, "
            "P={pitch:.4f} mm, TPI={tpi:g}, saved={saved}, aux_hidden={hidden}/6".format(
                name=Path(item["output_path"]).name,
                kind=kind,
                direction=item["direction"],
                designation=item["thread_designation"],
                diameter=float(item["major_diameter_mm"]),
                pitch=float(item["pitch_mm"]),
                tpi=float(item["tpi"]),
                saved=item["saved"],
                hidden=int(item["auxiliary_hidden_count"]),
            )
        )
    (OUTPUT_DIR / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _ensure_new_output_directory()
    adapter = KompasAdapter()
    items = []
    for payload in EXAMPLES:
        item = _create_example(adapter, payload)
        items.append(item)
        print(
            "{0} :: saved={1} :: {2} :: d={3:.3f} mm :: P={4:.4f} mm :: aux_hidden={5}/6".format(
                Path(item["output_path"]).name,
                item["saved"],
                item["thread_designation"],
                float(item["major_diameter_mm"]),
                float(item["pitch_mm"]),
                int(item["auxiliary_hidden_count"]),
            )
        )
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_readme(items)
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
