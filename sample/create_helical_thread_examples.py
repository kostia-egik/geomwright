from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter


DEFAULT_CONFIGS = [
    "external_helical_thread_demo_external_collinear_fresh_2026_05_10.json",
    "internal_helical_thread_demo_internal_arc_direction_fix_2026_05_10.json",
    "generated/metric_thread_catalog_examples/configs/cil0_24705_2004_coarse_m12_external.json",
    "generated/metric_thread_catalog_examples/configs/cil0_24705_2004_coarse_m12_internal.json",
]


def load_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_example(config_name: str) -> dict:
    sample_path = ROOT / "sample" / config_name
    payload = load_payload(sample_path)

    output_dir = ROOT / "sample" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / payload["output_name"]

    adapter = KompasAdapter()
    result = adapter.create_part_from_scenario(
        payload["scenario"],
        payload["params"],
        output_path=str(output_path),
        visible=False,
        close_after_save=True,
    )
    summary = result.get("preview", {}).get("summary", {})
    visibility_step = next(
        (step for step in result.get("steps", []) if step.get("step") == "hide_helical_thread_auxiliary_geometry"),
        {},
    )
    hidden_objects = visibility_step.get("objects") or []
    print(
        "{0} :: saved={1} :: diameter={2} :: pitch={3} :: length={4} :: depth={5} :: direction={6} :: aux_hidden={7}/{8}".format(
            output_path.name,
            result.get("saved"),
            summary.get("diameter"),
            summary.get("pitch"),
            summary.get("length"),
            summary.get("depth"),
            summary.get("direction"),
            sum(1 for item in hidden_objects if item.get("ok")),
            len(hidden_objects),
        )
    )
    return {
        "config": config_name,
        "output_path": str(output_path),
        "saved": bool(result.get("saved")),
        "scenario": payload.get("scenario"),
        "summary": {
            "diameter": summary.get("diameter"),
            "pitch": summary.get("pitch"),
            "length": summary.get("length"),
            "depth": summary.get("depth"),
            "direction": summary.get("direction"),
        },
        "auxiliary_geometry": visibility_step,
    }


def main() -> None:
    config_names = sys.argv[1:] or DEFAULT_CONFIGS
    reports = []
    for config_name in config_names:
        reports.append(build_example(config_name))
    report_path = ROOT / "sample" / "generated" / "helical_thread_examples.report.json"
    report_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print("report :: {0}".format(report_path))


if __name__ == "__main__":
    main()
