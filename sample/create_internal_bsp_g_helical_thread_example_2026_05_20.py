from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.thread_profile_geometry import resolve_thread_profile_geometry


OUTPUT_DIR = ROOT / "sample" / "generated" / "internal_bsp_g_helical_thread_example_2026_05_20"
CONFIG_DIR = OUTPUT_DIR / "configs"


def _set_output_dir(path: Path) -> None:
    global OUTPUT_DIR, CONFIG_DIR
    OUTPUT_DIR = path
    CONFIG_DIR = OUTPUT_DIR / "configs"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create one internal BSP G Whitworth helical-thread example."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory for generated .m3d files; it must not already exist.",
    )
    return parser.parse_args()


def _geometry(designation: str) -> dict[str, Any]:
    return dict(resolve_thread_profile_geometry({"designation": designation})["geometry"])


def _build_payload() -> dict[str, Any]:
    designation = "G 1/4"
    geometry = _geometry(designation)
    thread_length_mm = 12.0
    carrier_length_mm = 16.0
    source_body_length_mm = 22.0
    source_body_diameter_mm = 24.0

    return {
        "name": "int_bsp_g_1_4_whitworth",
        "scenario": "internal_helical_thread",
        "output_name": "internal_bsp_g_1_4_whitworth.m3d",
        "params": {
            "name": "BSP G 1/4 internal Whitworth",
            "designation": designation,
            "length": thread_length_mm,
            "direction": "right",
            "auxiliary_geometry_hidden": True,
            "source_scenario": "internal_cylindrical_step",
            "source_params": {
                "name": "Carrier BSP G 1/4 internal",
                "steps": [{"length": carrier_length_mm, "diameter": float(geometry["internal_minor_diameter"])}],
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": source_body_length_mm, "diameter": source_body_diameter_mm}]},
            },
        },
    }


def _ensure_new_output_directory() -> None:
    if OUTPUT_DIR.exists():
        raise RuntimeError(f"Output directory already exists: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    CONFIG_DIR.mkdir(parents=True, exist_ok=False)


def _write_config(payload: dict[str, Any]) -> Path:
    config_path = CONFIG_DIR / payload["output_name"].replace(".m3d", ".json")
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    geometry = dict(summary.get("thread_geometry") or {})

    if str(summary.get("thread_profile_family") or "") != "pipe_bsp_g_v55":
        raise RuntimeError("Internal BSP G example resolved an unexpected profile family.")
    if abs(float(summary.get("profile_angle_degrees") or 0.0) - 55.0) > 1e-6:
        raise RuntimeError("Internal BSP G example must use the 55 degree Whitworth profile.")
    if not bool(summary.get("crest_rounding_enabled")):
        raise RuntimeError("Internal BSP G example must create the mirrored crest-round pass.")
    if int(summary.get("secondary_cut_count") or 0) != 1:
        raise RuntimeError("Internal BSP G example must report one secondary crest-round cut.")
    if str(params.get("root_width_mode") or "") != "from_geometry":
        raise RuntimeError("Internal BSP G example must derive its round root from thread geometry.")

    return {
        "name": payload["name"],
        "ok": bool(result.get("ok")),
        "saved": bool(result.get("saved")),
        "output_path": str(output_path),
        "config_path": str(_write_config(payload)),
        "designation": summary.get("thread_designation") or params.get("designation"),
        "direction": summary.get("direction"),
        "thread_length_mm": float(summary.get("length") or params.get("length") or 0.0),
        "carrier_length_mm": float(((params.get("source_params") or {}).get("steps") or [{}])[0].get("length") or 0.0),
        "thread_reference_diameter_mm": float(summary.get("thread_reference_diameter") or 0.0),
        "pitch_mm": float(summary.get("pitch") or 0.0),
        "depth_mm": float(summary.get("depth") or 0.0),
        "root_round_radius_mm": float(summary.get("root_radius") or 0.0),
        "root_width_mm": float(summary.get("root_width") or 0.0),
        "secondary_cut_count": int(summary.get("secondary_cut_count") or 0),
        "crest_round_radius_mm": float(summary.get("crest_round_radius") or 0.0),
        "crest_round_phase_shift_mm": float(summary.get("crest_round_phase_shift") or 0.0),
        "thread_profile_family": str(summary.get("thread_profile_family") or ""),
        "geometry_profile_angle_degrees": float(geometry.get("profile_angle_degrees") or 0.0),
    }


def _write_readme(item: dict[str, Any]) -> None:
    lines = [
        "Internal BSP G Whitworth helical-thread example.",
        "This case validates the 55 degree BSP G profile on the internal helical-thread branch",
        "with a round root taken directly from thread_geometry and a mirrored secondary crest-round pass.",
        "",
        "Generated file: {0}".format(Path(item["output_path"]).name),
        "Designation: {0}".format(item["designation"]),
        "Direction: {0}".format(item["direction"]),
        "Profile family: {0}".format(item["thread_profile_family"]),
        "Carrier length: {0:.3f} mm".format(item["carrier_length_mm"]),
        "Thread length: {0:.3f} mm".format(item["thread_length_mm"]),
        "Thread reference diameter: {0:.6f} mm".format(item["thread_reference_diameter_mm"]),
        "Pitch: {0:.6f} mm".format(item["pitch_mm"]),
        "Depth: {0:.6f} mm".format(item["depth_mm"]),
        "Root round radius: {0:.6f} mm".format(item["root_round_radius_mm"]),
        "Root width: {0:.6f} mm".format(item["root_width_mm"]),
        "Crest round radius: {0:.6f} mm".format(item["crest_round_radius_mm"]),
        "Crest round phase shift: {0:.6f} mm".format(item["crest_round_phase_shift_mm"]),
        "Secondary cut count: {0}".format(item["secondary_cut_count"]),
        "Profile angle: {0:.1f} deg".format(item["geometry_profile_angle_degrees"]),
    ]
    (OUTPUT_DIR / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = _parse_args()
    _set_output_dir(args.output_dir.resolve())
    _ensure_new_output_directory()

    payload = _build_payload()
    adapter = KompasAdapter()
    item = _create_example(adapter, payload)
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps({"items": [item]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_readme(item)

    print(
        "{0} :: saved={1} :: depth={2:.6f} mm :: root_r={3:.6f} mm :: root_w={4:.6f} mm".format(
            Path(item["output_path"]).name,
            item["saved"],
            item["depth_mm"],
            item["root_round_radius_mm"],
            item["root_width_mm"],
        )
    )
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
