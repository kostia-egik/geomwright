from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from kompas_mcp.metric_thread_geometry import build_metric_thread_geometry


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "sample" / "create_metric_thread_catalog_examples.py"
SPEC = importlib.util.spec_from_file_location("create_metric_thread_catalog_examples", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load example generator from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MetricThreadCatalogExampleTests(unittest.TestCase):
    def test_build_internal_payload_uses_metric_internal_minor_diameter_for_hole(self) -> None:
        geometry = build_metric_thread_geometry(16.0, 1.5)
        payload = MODULE._build_internal_payload(
            "C:\\temp\\thread.db",
            "custom_metric",
            {"designation": "M16x1.5", "d": 16.0, "p": 1.5, "d1": geometry["internal_minor_diameter"]},
            direction="right",
        )

        self.assertEqual(payload["params"]["direction"], "right")
        self.assertEqual(payload["params"]["source_scenario"], "internal_cylindrical_step")
        self.assertAlmostEqual(payload["params"]["source_params"]["steps"][0]["diameter"], geometry["internal_minor_diameter"], places=6)
        self.assertEqual(payload["params"]["diameter"], 16.0)

    def test_build_description_mentions_internal_minor_diameter(self) -> None:
        lines = MODULE._build_description_lines(
            [
                {
                    "scenario": "internal_helical_thread",
                    "thread_designation": "M16x1.5",
                    "thread_standard_table_name": "custom_metric",
                    "pitch": 1.5,
                    "diameter": 16.0,
                    "source_hole_diameter": 14.16,
                }
            ]
        )

        self.assertIn("Все примеры в этом пакете правые.", lines)
        self.assertIn("source_hole_d=14.16", lines[-1])


if __name__ == "__main__":
    unittest.main()
