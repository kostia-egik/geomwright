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


OUTPUT_DIR = ROOT / "sample" / "generated" / "external_npt_partial_helical_thread_example_2026_05_19"
CONFIG_DIR = OUTPUT_DIR / "configs"


def _set_output_dir(path: Path) -> None:
    global OUTPUT_DIR, CONFIG_DIR
    OUTPUT_DIR = path
    CONFIG_DIR = OUTPUT_DIR / "configs"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create one external partial-length NPT helical-thread example."
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
    designation = "1/4-18 NPT"
    geometry = _geometry(designation)

    source_cone_length_mm = 24.0
    thread_length_mm = 12.0
    taper_ratio = float(geometry["taper_diameter_ratio"])
    entry_major_diameter_mm = float(geometry["major_diameter"]) - source_cone_length_mm * taper_ratio
    seat_major_diameter_mm = float(geometry["major_diameter"])
    shoulder_length_mm = 10.0
    shoulder_diameter_mm = round(max(seat_major_diameter_mm + 12.0, seat_major_diameter_mm * 1.45), 3)

    return {
        "name": "ext_partial_1_4_18_npt_entry_from_small_end",
        "scenario": "external_helical_thread",
        "output_name": "external_npt_partial_entry_from_small_end_1_4_18.m3d",
        "params": {
            "name": "NPT external partial from small end",
            "designation": designation,
            "length": thread_length_mm,
            "direction": "right",
            "auxiliary_geometry_hidden": True,
            "source_scenario": "external_conical_step",
            "source_params": {
                "name": "Carrier external partial 1/4-18 NPT",
                "length": source_cone_length_mm,
                "start_diameter": round(seat_major_diameter_mm, 3),
                "end_diameter": round(entry_major_diameter_mm, 3),
                "slope_direction": "inward",
                "source_scenario": "stepped_shaft",
                "source_params": {
                    "steps": [
                        {
                            "length": round(source_cone_length_mm + shoulder_length_mm, 3),
                            "diameter": shoulder_diameter_mm,
                        }
                    ]
                },
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
    taper_report = dict(summary.get("carrier_taper") or {})

    if params.get("start_selector") != "end_face" or params.get("end_selector") != "start_face":
        raise RuntimeError(
            "External conical NPT example must anchor the thread from small end to large end."
        )

    return {
        "name": payload["name"],
        "ok": bool(result.get("ok")),
        "saved": bool(result.get("saved")),
        "output_path": str(output_path),
        "config_path": str(_write_config(payload)),
        "designation": summary.get("thread_designation") or params.get("designation"),
        "direction": summary.get("direction"),
        "source_length_mm": float((params.get("source_params") or {}).get("length") or 0.0),
        "thread_length_mm": float(summary.get("length") or params.get("length") or 0.0),
        "thread_reference_start_mm": float(summary.get("thread_reference_diameter") or 0.0),
        "thread_reference_end_mm": float(summary.get("end_thread_reference_diameter") or 0.0),
        "carrier_large_end_mm": float((params.get("source_params") or {}).get("start_diameter") or 0.0),
        "carrier_small_end_mm": float((params.get("source_params") or {}).get("end_diameter") or 0.0),
        "start_selector": params.get("start_selector"),
        "end_selector": params.get("end_selector"),
        "thread_entry_axis_mm": float(taper_report.get("thread_start_axis") or 0.0),
        "thread_exit_axis_mm": float(taper_report.get("thread_end_axis") or 0.0),
        "smooth_large_end_tail_mm": float(
            ((params.get("source_params") or {}).get("length") or 0.0) - (summary.get("length") or 0.0)
        ),
    }


def _write_readme(item: dict[str, Any]) -> None:
    lines = [
        "External partial-length NPT helical-thread example.",
        "This case is intentionally longer than the threaded span.",
        "The mating part enters from the small/free end, so the smooth remainder must stay at the large/seat end.",
        "",
        "Generated file: {0}".format(Path(item["output_path"]).name),
        "Designation: {0}".format(item["designation"]),
        "Direction: {0}".format(item["direction"]),
        "Carrier: large_end={0:.3f} mm -> small_end={1:.3f} mm over {2:.3f} mm".format(
            item["carrier_large_end_mm"],
            item["carrier_small_end_mm"],
            item["source_length_mm"],
        ),
        "Thread span: {0:.3f} mm, selectors {1} -> {2}".format(
            item["thread_length_mm"],
            item["start_selector"],
            item["end_selector"],
        ),
        "Thread reference diameters: start={0:.3f} mm, end={1:.3f} mm".format(
            item["thread_reference_start_mm"],
            item["thread_reference_end_mm"],
        ),
        "Thread axis span on cone: start={0:.3f} mm, end={1:.3f} mm".format(
            item["thread_entry_axis_mm"],
            item["thread_exit_axis_mm"],
        ),
        "Smooth remainder at large end: {0:.3f} mm".format(item["smooth_large_end_tail_mm"]),
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
        "{0} :: saved={1} :: selectors={2}->{3} :: thread_axis={4:.3f}->{5:.3f} :: "
        "smooth_large_end_tail={6:.3f} mm".format(
            Path(item["output_path"]).name,
            item["saved"],
            item["start_selector"],
            item["end_selector"],
            item["thread_entry_axis_mm"],
            item["thread_exit_axis_mm"],
            item["smooth_large_end_tail_mm"],
        )
    )
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
