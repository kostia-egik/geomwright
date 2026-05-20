from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "sample" / "create_metric_thread_catalog_examples_set2.py"
SPEC = importlib.util.spec_from_file_location("create_metric_thread_catalog_examples_set2", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load example generator from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MetricThreadCatalogExampleSet2Tests(unittest.TestCase):
    def test_description_explicitly_lists_left_handed_examples(self) -> None:
        lines = MODULE._build_description_lines(
            [
                {
                    "scenario": "external_helical_thread",
                    "thread_designation": "M12x1.25",
                    "thread_standard_table_name": "custom_metric",
                    "pitch": 1.25,
                    "diameter": 12.0,
                    "direction": "left",
                },
                {
                    "scenario": "internal_helical_thread",
                    "thread_designation": "M12x1.25",
                    "thread_standard_table_name": "custom_metric",
                    "pitch": 1.25,
                    "diameter": 12.0,
                    "direction": "left",
                    "source_hole_diameter": 10.647,
                },
            ]
        )

        self.assertIn("Файлы созданы в новой папке, старый набор не перезаписывается.", lines)
        self.assertIn("Левые резьбы: M12x1.25 (наружная), M12x1.25 (внутренняя)", lines)
        self.assertIn("левая", lines[-1])
        self.assertIn("source_hole_d=10.647", lines[-1])

    def test_output_directory_is_new_and_distinct_from_first_batch(self) -> None:
        self.assertNotEqual(MODULE.OUTPUT_DIR.name, "metric_thread_catalog_examples")
        self.assertIn("set2", MODULE.OUTPUT_DIR.name)


if __name__ == "__main__":
    unittest.main()
