from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter


CONFIG_NAME = "bolt_circle_holes_workflow_demo.json"


def load_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    sample_path = ROOT / "sample" / CONFIG_NAME
    payload = load_payload(sample_path)

    output_dir = ROOT / "sample" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / payload["output_name"]

    adapter = KompasAdapter()
    result = adapter.create_part_from_scenario(
        "workflow",
        payload,
        output_path=str(output_path),
        visible=False,
        close_after_save=True,
    )
    print(
        "{0} :: saved={1} :: operation_count={2}".format(
            output_path.name,
            result.get("saved"),
            result.get("preview", {}).get("summary", {}).get("operation_count"),
        )
    )


if __name__ == "__main__":
    main()
