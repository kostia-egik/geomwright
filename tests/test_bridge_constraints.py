from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_bridge_module():
    module_name = "kompas_bridge_constraints_test_module"
    if module_name in sys.modules:
        return sys.modules[module_name]

    fake_win32com = types.ModuleType("win32com")
    fake_client = types.ModuleType("win32com.client")

    def _dispatch(obj, *args, **kwargs):
        return obj

    fake_client.Dispatch = _dispatch
    fake_win32com.client = fake_client
    sys.modules.setdefault("win32com", fake_win32com)
    sys.modules.setdefault("win32com.client", fake_client)

    bridge_path = Path(__file__).resolve().parents[1] / "bridge" / "kompas_bridge.py"
    spec = importlib.util.spec_from_file_location(module_name, bridge_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module


BRIDGE = _load_bridge_module()


class BridgeConstraintTests(unittest.TestCase):
    def test_apply_sketch_constraints_skips_redundant_arc_merge_points(self) -> None:
        original = BRIDGE._apply_constraint_to_line

        def _always_fail(*args, **kwargs):
            return {
                "created": False,
                "valid": False,
                "type": BRIDGE.SKETCH_CONSTRAINT_TYPES["merge_points"],
                "reference": 0,
            }

        BRIDGE._apply_constraint_to_line = _always_fail
        self.addCleanup(setattr, BRIDGE, "_apply_constraint_to_line", original)

        sketch_entities = {
            "right_root_ref": {
                "object": object(),
                "role": "construction",
                "target": "right_root_ref",
                "x1": 0.0,
                "y1": -1.0,
                "x2": 0.25,
                "y2": -1.0,
            },
            "root_arc": {
                "object": object(),
                "role": "profile",
                "target": "root_arc",
                "xc": 0.0,
                "yc": -0.75,
                "radius": 0.5,
                "x1": 0.25,
                "y1": -1.0,
                "x2": -0.25,
                "y2": -1.0,
                "direction": True,
            },
        }
        planned_constraints = [
            {
                "kind": "merge_points",
                "target": "right_root_ref",
                "index": 1,
                "partner": "root_arc",
                "partner_index": 1,
            }
        ]

        report = BRIDGE._apply_sketch_constraints(sketch_entities, planned_constraints, {"enabled": True})

        self.assertEqual(report["failed_count"], 0)
        self.assertEqual(report["skipped_count"], 1)
        self.assertEqual(report["live_status"], "applied")
        self.assertEqual(report["skipped"][0]["reason"], "redundant_coincident_points")


if __name__ == "__main__":
    unittest.main()
