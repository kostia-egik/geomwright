from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.metric_thread_geometry import build_metric_thread_geometry
from kompas_mcp.thread_catalog import find_thread_database_path
from kompas_mcp.thread_catalog import list_helical_thread_v1_candidates
from kompas_mcp.thread_catalog import list_thread_standard_entries


OUTPUT_DIR = ROOT / "sample" / "generated" / "metric_thread_catalog_examples"
CONFIG_DIR = OUTPUT_DIR / "configs"

EXAMPLE_REQUESTS = [
    {"standard": "cil0_24705-2004 coarse", "diameter": 12.0},
    {"standard": "cil0_24705-2004 fine", "diameter": 16.0, "pitch": 1.5},
    {"standard": "cil1_24705-2004", "diameter": 20.0, "pitch": 2.5},
    {"standard": "cil1_ex_ISO 724 coarse", "diameter": 10.0},
    {"standard": "cil1_ex_ISO 724 fine", "diameter": 12.0, "pitch": 1.25},
]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    return slug or "thread"


def _pick_entry(database_path: str, request: dict) -> dict:
    payload = list_thread_standard_entries(request["standard"], database_path=database_path, limit=None)
    entries = list(payload.get("entries") or [])
    if not entries:
        raise RuntimeError(f"No entries found for standard {request['standard']}")

    target_diameter = float(request["diameter"])
    target_pitch = request.get("pitch")
    best_entry = None
    best_score = None
    for entry in entries:
        score = abs(float(entry["d"]) - target_diameter)
        if target_pitch is not None:
            score += abs(float(entry["p"]) - float(target_pitch))
        if best_score is None or score < best_score:
            best_entry = entry
            best_score = score
    if best_entry is None:
        raise RuntimeError(f"Unable to pick entry for standard {request['standard']}")
    return best_entry


def _require_internal_minor_diameter(entry: dict) -> float:
    geometry = build_metric_thread_geometry(float(entry["d"]), float(entry["p"]))
    catalog_minor_diameter = entry.get("d1")
    if isinstance(catalog_minor_diameter, (int, float)) and abs(float(catalog_minor_diameter) - geometry["internal_minor_diameter"]) > 0.02:
        designation = str(entry.get("designation") or "").strip() or "<unknown>"
        raise RuntimeError(
            f"Catalog entry {designation} d1={float(catalog_minor_diameter):.6f} disagrees with metric geometry "
            f"{geometry['internal_minor_diameter']:.6f}"
        )
    return float(geometry["internal_minor_diameter"])


def _build_external_payload(database_path: str, standard: str, entry: dict, *, direction: str) -> dict:
    diameter = float(entry["d"])
    pitch = float(entry["p"])
    thread_length = max(12.0, min(24.0, diameter))
    shoulder_diameter = round(max(diameter + 8.0, diameter * 1.6), 3)
    shoulder_length = round(max(8.0, diameter * 0.75), 3)
    slug = _slugify(f"{standard}_{entry['designation']}")
    return {
        "scenario": "external_helical_thread",
        "output_name": f"{slug}_external.m3d",
        "params": {
            "name": f"MetricThreadCatalogExternal_{slug}",
            "designation": str(entry["designation"]),
            "diameter": diameter,
            "pitch": pitch,
            "length": thread_length,
            "direction": direction,
            "thread_standard": standard,
            "thread_database_path": database_path,
            "source_scenario": "stepped_shaft",
            "source_params": {
                "name": f"MetricThreadCarrierExternal_{slug}",
                "steps": [
                    {"length": round(thread_length + 8.0, 3), "diameter": diameter},
                    {"length": shoulder_length, "diameter": shoulder_diameter},
                ],
            },
        },
    }


def _build_internal_payload(database_path: str, standard: str, entry: dict, *, direction: str) -> dict:
    diameter = float(entry["d"])
    pitch = float(entry["p"])
    minor_diameter = _require_internal_minor_diameter(entry)
    thread_length = max(10.0, min(24.0, diameter))
    outer_diameter = round(max(diameter + 16.0, diameter * 2.2), 3)
    slug = _slugify(f"{standard}_{entry['designation']}")
    return {
        "scenario": "internal_helical_thread",
        "output_name": f"{slug}_internal.m3d",
        "params": {
            "name": f"MetricThreadCatalogInternal_{slug}",
            "designation": str(entry["designation"]),
            "diameter": diameter,
            "pitch": pitch,
            "length": thread_length,
            "direction": direction,
            "thread_standard": standard,
            "thread_database_path": database_path,
            "source_scenario": "internal_cylindrical_step",
            "source_params": {
                "name": f"MetricThreadCarrierInternal_{slug}",
                "steps": [{"length": round(thread_length + 8.0, 3), "diameter": minor_diameter}],
                "source_scenario": "stepped_shaft",
                "source_params": {
                    "steps": [{"length": round(thread_length + 14.0, 3), "diameter": outer_diameter}],
                },
            },
        },
    }


def _build_description_lines(manifest: list[dict]) -> list[str]:
    lines = [
        "Набор примеров физических метрических резьб без конусности.",
        "Все примеры в этом пакете правые.",
        "",
    ]
    for item in manifest:
        scenario = str(item["scenario"])
        kind = "наружная" if scenario == "external_helical_thread" else "внутренняя"
        line = (
            f"- {item['thread_designation']} | {item['thread_standard_table_name']} | "
            f"{kind} | P={item['pitch']} | d={item['diameter']}"
        )
        if scenario == "internal_helical_thread" and item.get("source_hole_diameter") is not None:
            line += f" | source_hole_d={item['source_hole_diameter']}"
        lines.append(line)
    return lines


def _write_config(payload: dict) -> Path:
    config_path = CONFIG_DIR / payload["output_name"].replace(".m3d", ".json")
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return config_path


def _create_example(adapter: KompasAdapter, payload: dict) -> dict:
    output_path = OUTPUT_DIR / payload["output_name"]
    params = payload["params"]
    source_hole_diameter = None
    if payload["scenario"] == "internal_helical_thread":
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
        "pitch": summary.get("pitch") or params.get("pitch"),
        "direction": summary.get("direction") or params.get("direction"),
        "source_hole_diameter": source_hole_diameter,
    }


def main() -> None:
    database_path = find_thread_database_path()
    if not database_path:
        raise RuntimeError("KOMPAS thread.db not found")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    candidates = list_helical_thread_v1_candidates(database_path=database_path, limit_per_standard=3)
    available_standards = {item["table_name"] for item in candidates.get("standards") or []}

    adapter = KompasAdapter()
    manifest = []
    for index, request in enumerate(EXAMPLE_REQUESTS):
        standard = str(request["standard"])
        if standard not in available_standards:
            raise RuntimeError(f"Standard {standard} is not available in V1-compatible metric catalog")
        entry = _pick_entry(database_path, request)
        external_payload = _build_external_payload(
            database_path,
            standard,
            entry,
            direction="right",
        )
        internal_payload = _build_internal_payload(
            database_path,
            standard,
            entry,
            direction="right",
        )
        for payload in (external_payload, internal_payload):
            config_path = _write_config(payload)
            result = _create_example(adapter, payload)
            result["config_path"] = str(config_path)
            manifest.append(result)
            print(
                "{0} :: saved={1} :: designation={2} :: standard={3} :: direction={4}".format(
                    Path(result["output_path"]).name,
                    result["saved"],
                    result["thread_designation"],
                    result["thread_standard_table_name"],
                    result["direction"],
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
