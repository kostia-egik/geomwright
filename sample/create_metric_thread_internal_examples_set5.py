from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.thread_catalog import find_thread_database_path
from kompas_mcp.thread_catalog import list_helical_thread_v1_candidates


COMMON_SCRIPT_PATH = ROOT / "sample" / "create_metric_thread_catalog_examples.py"
COMMON_SPEC = importlib.util.spec_from_file_location("create_metric_thread_catalog_examples", COMMON_SCRIPT_PATH)
if COMMON_SPEC is None or COMMON_SPEC.loader is None:
    raise RuntimeError(f"Unable to load common example generator from {COMMON_SCRIPT_PATH}")
COMMON = importlib.util.module_from_spec(COMMON_SPEC)
COMMON_SPEC.loader.exec_module(COMMON)


OUTPUT_DIR = ROOT / "sample" / "generated" / "metric_thread_internal_examples_set5_2026_05_14"
CONFIG_DIR = OUTPUT_DIR / "configs"

EXAMPLE_REQUESTS = [
    {"standard": "cil0_24705-2004 fine", "diameter": 16.0, "pitch": 1.5, "direction": "right"},
    {"standard": "cil1_ex_ISO 724 fine", "diameter": 16.0, "pitch": 1.0, "direction": "left"},
]


def _ensure_new_output_directory() -> None:
    if OUTPUT_DIR.exists():
        raise RuntimeError(f"Output directory already exists: {OUTPUT_DIR}")


def _write_config(payload: dict) -> Path:
    config_path = CONFIG_DIR / payload["output_name"].replace(".m3d", ".json")
    if config_path.exists():
        raise RuntimeError(f"Refusing to overwrite config file: {config_path}")
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return config_path


def _create_example(adapter: KompasAdapter, payload: dict) -> dict:
    output_path = OUTPUT_DIR / payload["output_name"]
    if output_path.exists():
        raise RuntimeError(f"Refusing to overwrite output file: {output_path}")
    params = payload["params"]
    source_hole_diameter = None
    steps = ((params.get("source_params") or {}).get("steps") or [])
    if steps:
        source_hole_diameter = steps[0].get("diameter")
    result = adapter.create_part_from_scenario(
        payload["scenario"],
        params,
        output_path=str(output_path),
        visible=False,
        close_after_save=True,
    )
    summary = result.get("preview", {}).get("summary", {})
    return {
        "scenario": payload["scenario"],
        "output_path": str(output_path),
        "saved": bool(result.get("saved")),
        "thread_standard_table_name": summary.get("thread_standard_table_name") or params.get("thread_standard"),
        "thread_designation": summary.get("thread_designation") or params.get("designation"),
        "diameter": summary.get("diameter") or params.get("diameter"),
        "carrier_diameter": summary.get("carrier_diameter") or params.get("carrier_diameter"),
        "pitch": summary.get("pitch") or params.get("pitch"),
        "direction": summary.get("direction") or params.get("direction"),
        "profile_surface_offset": summary.get("profile_surface_offset") or params.get("profile_surface_offset"),
        "profile_surface_offset_effective": summary.get("profile_surface_offset_effective"),
        "profile_surface_offset_status": summary.get("profile_surface_offset_status")
        or params.get("profile_surface_offset_status")
        or "ignored_in_v1",
        "profile_sketch_origin_shift": summary.get("profile_sketch_origin_shift")
        or params.get("profile_sketch_origin_shift"),
        "thread_reference_diameter": summary.get("thread_reference_diameter"),
        "recommended_source_diameter": summary.get("recommended_source_diameter"),
        "source_hole_diameter": source_hole_diameter,
    }


def _build_description_lines(manifest: list[dict]) -> list[str]:
    lines = [
        "Новая отдельная группа примеров только для внутренних метрических резьб.",
        "В этой версии рабочий профиль внутренней резьбы привязан к D1, а radial surface_offset в V1 только принимается для совместимости.",
        "",
    ]
    for item in manifest:
        handed = "левая" if str(item.get("direction")) == "left" else "правая"
        lines.append(
            f"- {item['thread_designation']} | {item['thread_standard_table_name']} | внутренняя | "
            f"{handed} | P={item['pitch']} | d={item['diameter']} | "
            f"carrier_d={item.get('carrier_diameter')} | source_hole_d={item.get('source_hole_diameter')} | "
            f"ref_d={item.get('thread_reference_diameter')} | "
            f"surface_offset_status={item.get('profile_surface_offset_status') or 'ignored_in_v1'} | "
            f"sketch_shift={item.get('profile_sketch_origin_shift')}"
        )
    return lines


def main() -> None:
    database_path = find_thread_database_path()
    if not database_path:
        raise RuntimeError("KOMPAS thread.db not found")

    _ensure_new_output_directory()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    CONFIG_DIR.mkdir(parents=True, exist_ok=False)

    candidates = list_helical_thread_v1_candidates(database_path=database_path, limit_per_standard=3)
    available_standards = {item["table_name"] for item in candidates.get("standards") or []}

    adapter = KompasAdapter()
    manifest = []
    for request in EXAMPLE_REQUESTS:
        standard = str(request["standard"])
        if standard not in available_standards:
            raise RuntimeError(f"Standard {standard} is not available in V1-compatible metric catalog")
        entry = COMMON._pick_entry(database_path, request)
        payload = COMMON._build_internal_payload(
            database_path,
            standard,
            entry,
            direction=str(request["direction"]),
        )
        config_path = _write_config(payload)
        result = _create_example(adapter, payload)
        result["config_path"] = str(config_path)
        manifest.append(result)
        print(
            "{0} :: saved={1} :: designation={2} :: standard={3} :: direction={4} :: carrier_d={5} :: sketch_shift={6}".format(
                Path(result["output_path"]).name,
                result["saved"],
                result["thread_designation"],
                result["thread_standard_table_name"],
                result["direction"],
                result["carrier_diameter"],
                result["profile_sketch_origin_shift"],
            )
        )

    manifest_path = OUTPUT_DIR / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump({"database_path": database_path, "items": manifest}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    description_path = OUTPUT_DIR / "README.txt"
    with description_path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(_build_description_lines(manifest)))
        handle.write("\n")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
