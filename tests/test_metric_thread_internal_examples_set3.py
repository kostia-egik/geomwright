from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "sample" / "create_metric_thread_internal_examples_set3.py"
SPEC = importlib.util.spec_from_file_location("create_metric_thread_internal_examples_set3", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load example generator from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MetricThreadInternalExampleSet3Tests(unittest.TestCase):
    def test_description_marks_left_handed_internal_example_and_source_hole(self) -> None:
        lines = MODULE._build_description_lines(
            [
                {
                    "thread_designation": "M16x1.5",
                    "thread_standard_table_name": "custom_metric",
                    "pitch": 1.5,
                    "diameter": 16.0,
                    "carrier_diameter": 14.376,
                    "source_hole_diameter": 14.376,
                    "direction": "right",
                },
                {
                    "thread_designation": "MF 16x1",
                    "thread_standard_table_name": "custom_metric_fine",
                    "pitch": 1.0,
                    "diameter": 16.0,
                    "carrier_diameter": 14.92,
                    "source_hole_diameter": 14.92,
                    "direction": "left",
                },
            ]
        )

        self.assertIn("только для внутренних метрических резьб", lines[0])
        self.assertIn("правая", lines[3])
        self.assertIn("левая", lines[4])
        self.assertIn("carrier_d=14.92", lines[4])
        self.assertIn("source_hole_d=14.92", lines[4])

    def test_output_directory_is_new(self) -> None:
        self.assertIn("set3", MODULE.OUTPUT_DIR.name)


if __name__ == "__main__":
    unittest.main()
