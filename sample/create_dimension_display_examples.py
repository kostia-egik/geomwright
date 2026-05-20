from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter


def load_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    adapter = KompasAdapter()
    output_dir = ROOT / "sample" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    for name in ("stepped_shaft_radius.json", "stepped_shaft_diameter.json"):
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
        print("{0} :: {1} :: saved={2}".format(output_path, summary["dimension_display"], result["saved"]))


if __name__ == "__main__":
    main()
