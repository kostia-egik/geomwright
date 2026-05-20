from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter


CONFIG_NAMES = [
    "point_center_start_face_demo.json",
    "point_center_shoulder_1_demo.json",
    "point_center_step_2_outer_face_demo.json",
    "lcs_object_far_end_face_demo.json",
    "lcs_object_step_2_end_face_demo.json",
]


def load_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    output_dir = ROOT / "sample" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    adapter = KompasAdapter()
    for config_name in CONFIG_NAMES:
        sample_path = ROOT / "sample" / config_name
        payload = load_payload(sample_path)
        scenario = str(payload.get("scenario") or "").strip()
        params = dict(payload.get("params") or {})
        output_name = sample_path.with_suffix(".m3d").name
        output_path = output_dir / output_name
        result = adapter.create_part_from_scenario(
            scenario,
            params,
            output_path=str(output_path),
            visible=False,
            close_after_save=True,
        )
        print(
            "{0} :: saved={1} :: scenario={2}".format(
                output_path.name,
                result.get("saved"),
                scenario,
            )
        )


if __name__ == "__main__":
    main()
