from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter


SAMPLE_NAMES = (
    "stepped_shaft_radius.json",
    "stepped_shaft_two_step_compact.json",
    "stepped_shaft_long_neck.json",
    "stepped_shaft_five_step_mixed.json",
    "external_conical_step_demo.json",
    "external_conical_step_angle_demo.json",
    "internal_conical_step_demo.json",
    "internal_cylindrical_step_demo.json",
    "stepped_shaft_internal_stepped_bore_demo.json",
    "stepped_shaft_offset_csys.json",
    "stepped_shaft_csys_local_offset.json",
)


def load_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    adapter = KompasAdapter()
    output_dir = ROOT / "sample" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    for name in SAMPLE_NAMES:
        sample_path = ROOT / "sample" / name
        payload = load_payload(sample_path)
        output_path = output_dir / payload["output_name"]
        result = adapter.create_part_from_scenario(
            payload["scenario"],
            payload["params"],
            output_path=str(output_path),
            close_after_save=True,
        )
        summary = result["preview"]["summary"]
        if "step_count" in summary:
            descriptor = "steps={0}".format(summary["step_count"])
        else:
            descriptor = "length={0}".format(summary.get("length"))
            if "definition_mode" in summary:
                descriptor += ", mode={0}".format(summary.get("definition_mode"))
        print(
            "{0} :: {1} :: saved={2}".format(
                output_path.name,
                descriptor,
                result["saved"],
            )
        )


if __name__ == "__main__":
    main()
