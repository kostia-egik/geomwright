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
    def test_bind_extrusion_operation_variables_matches_distance_alias(self) -> None:
        class FakeVariable:
            Name = "var_1"
            ParameterNote = "Расстояние"
            Expression = "12"

            def Update(self):
                return True

        class FakeOwner:
            def __init__(self):
                self.variable = FakeVariable()

            def Variables(self, *args):
                return [self.variable]

        class FakeExtrusion:
            def __init__(self):
                self.Owner = FakeOwner()
                self.updated = False

            def Update(self):
                self.updated = True
                return True

        extrusion = FakeExtrusion()
        report = BRIDGE._bind_extrusion_operation_variables(
            extrusion,
            {
                "operation_variable_bindings": [
                    {
                        "parameter_note_aliases": ["Distance", "Расстояние"],
                        "expression": "FLAT01_L1",
                    }
                ]
            },
            "external_flat_step",
        )

        self.assertIsNotNone(report)
        self.assertTrue(report["ok"])
        self.assertEqual(report["scenario"], "external_flat_step")
        self.assertEqual(report["applied_count"], 1)
        self.assertEqual(extrusion.Owner.variable.Expression, "FLAT01_L1")
        self.assertTrue(extrusion.updated)

    def test_bind_extrusion_operation_variables_reports_missing_distance_alias(self) -> None:
        class FakeVariable:
            Name = "var_1"
            ParameterNote = "Angle"
            Expression = "12"

            def Update(self):
                return True

        class FakeOwner:
            def __init__(self):
                self.variable = FakeVariable()

            def Variables(self, *args):
                return [self.variable]

        class FakeExtrusion:
            Owner = FakeOwner()

            def Update(self):
                return True

        report = BRIDGE._bind_extrusion_operation_variables(
            FakeExtrusion(),
            {
                "operation_variable_bindings": [
                    {
                        "parameter_note_aliases": ["Distance", "Расстояние"],
                        "expression": "FLAT01_L1",
                    }
                ]
            },
            "external_flat_step",
        )

        self.assertIsNotNone(report)
        self.assertFalse(report["ok"])
        self.assertEqual(report["scenario"], "external_flat_step")
        self.assertEqual(report["target"], "extrusion")
        self.assertEqual(report["failed_count"], 1)
        self.assertEqual(report["failed"][0]["error"], "operation_variable_not_found")

    def test_bind_circular_pattern_operation_variables_matches_count_and_angle_aliases(self) -> None:
        class FakeVariable:
            def __init__(self, name, note, expression):
                self.Name = name
                self.ParameterNote = note
                self.Expression = expression

            def Update(self):
                return True

        class FakeOwner:
            def __init__(self):
                self.count = FakeVariable("var_count", "Count", "4")
                self.angle = FakeVariable("var_angle", "Angle", "90")

            def Variables(self, *args):
                return [self.count, self.angle]

        class FakePattern:
            def __init__(self):
                self.Owner = FakeOwner()
                self.updated = 0

            def Update(self):
                self.updated += 1
                return True

        pattern = FakePattern()
        report = BRIDGE._bind_circular_pattern_operation_variables(
            pattern,
            {
                "pattern_operation_variable_bindings": [
                    {
                        "parameter_note_aliases": ["Count"],
                        "expression": "BCH01_N1",
                    },
                    {
                        "parameter_note_aliases": ["Angle"],
                        "expression": "BCH01_A1",
                    },
                ]
            },
            "bolt_circle_holes",
        )

        self.assertIsNotNone(report)
        self.assertTrue(report["ok"])
        self.assertEqual(report["scenario"], "bolt_circle_holes")
        self.assertEqual(report["target"], "circular_pattern")
        self.assertEqual(report["applied_count"], 2)
        self.assertEqual(pattern.Owner.count.Expression, "BCH01_N1")
        self.assertEqual(pattern.Owner.angle.Expression, "BCH01_A1")
        self.assertEqual(pattern.updated, 2)

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
