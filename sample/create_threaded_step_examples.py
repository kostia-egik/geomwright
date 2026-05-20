from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter


DEFAULT_CONFIGS = [
    "external_threaded_step_demo.json",
    "internal_threaded_step_demo.json",
]


def load_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_example(config_name: str) -> None:
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
    print(
        "{0} :: saved={1} :: designation={2} :: standard={3} :: depth={4} :: direction={5}".format(
            output_path.name,
            result.get("saved"),
            summary.get("thread_designation"),
            summary.get("thread_standard_table_name"),
            summary.get("depth"),
            summary.get("direction"),
        )
    )


def main() -> None:
    config_names = sys.argv[1:] or DEFAULT_CONFIGS
    for config_name in config_names:
        build_example(config_name)


if __name__ == "__main__":
    main()
