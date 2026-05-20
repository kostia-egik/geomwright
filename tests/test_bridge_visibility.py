from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_bridge_module():
    module_name = "kompas_bridge_visibility_test_module"
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


class _FakeHiddenObject:
    def __init__(self, hidden: bool = False) -> None:
        self.Hidden = bool(hidden)
        self.Name = "aux"
        self.Reference = 42
        self.update_count = 0

    def Update(self) -> bool:
        self.update_count += 1
        return True


class _FakeVisibleObject:
    def __init__(self, visible: bool = True) -> None:
        self.Visible = bool(visible)
        self.Name = "visible-aux"
        self.Reference = 43
        self.update_count = 0

    def Update(self) -> bool:
        self.update_count += 1
        return True


class _FakeFailingUpdateObject(_FakeHiddenObject):
    def Update(self) -> bool:
        self.update_count += 1
        return False


class _FakeOperationVariable:
    def __init__(self, name: str, note: str, expression: str = "") -> None:
        self.Name = name
        self.ParameterNote = note
        self.Expression = expression
        self.update_count = 0

    def Update(self) -> bool:
        self.update_count += 1
        return True


class _FakeOperationVariableCollection:
    def __init__(self, variables: list[_FakeOperationVariable]) -> None:
        self._variables = list(variables)
        self.Count = len(self._variables)

    def Item(self, index: int) -> _FakeOperationVariable:
        return self._variables[index]


class _FakeOperationOwner:
    def __init__(self, variables: list[_FakeOperationVariable]) -> None:
        self._variables = _FakeOperationVariableCollection(variables)

    def Variables(self, *_args):
        return self._variables


class _FakeOperationObject:
    def __init__(self, variables: list[_FakeOperationVariable]) -> None:
        self.Owner = _FakeOperationOwner(variables)
        self.update_count = 0

    def Update(self) -> bool:
        self.update_count += 1
        return True


class _FakeFailingOperationObject(_FakeOperationObject):
    def Update(self) -> bool:
        self.update_count += 1
        return False


class BridgeVisibilityTests(unittest.TestCase):
    def test_set_model_object_hidden_updates_hidden_flag(self) -> None:
        obj = _FakeHiddenObject(hidden=False)

        report = BRIDGE._set_model_object_hidden(obj, True, role="spiral_path")

        self.assertTrue(report["ok"])
        self.assertEqual(report["role"], "spiral_path")
        self.assertFalse(report["hidden_before"])
        self.assertTrue(report["hidden_after"])
        self.assertTrue(report["update_available"])
        self.assertTrue(report["update_ok"])
        self.assertEqual(obj.update_count, 1)

    def test_set_model_object_hidden_reports_missing_hidden_property(self) -> None:
        report = BRIDGE._set_model_object_hidden(object(), True, role="start_center_point")

        self.assertFalse(report["ok"])
        self.assertEqual(report["role"], "start_center_point")
        self.assertEqual(report["reason"], "hidden_property_unavailable")

    def test_set_model_object_hidden_uses_visible_fallback(self) -> None:
        obj = _FakeVisibleObject(visible=True)

        report = BRIDGE._set_model_object_hidden(obj, True, role="profile_sketch")

        self.assertTrue(report["ok"])
        self.assertEqual(report["role"], "profile_sketch")
        self.assertTrue(report["visible_before"])
        self.assertFalse(report["visible_after"])
        self.assertTrue(report["update_ok"])
        self.assertFalse(obj.Visible)
        self.assertEqual(obj.update_count, 1)

    def test_set_model_object_hidden_requires_successful_update_when_available(self) -> None:
        report = BRIDGE._set_model_object_hidden(_FakeFailingUpdateObject(hidden=False), True, role="profile_lcs")

        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"], "visibility_update_failed")
        self.assertTrue(report["hidden_after"])
        self.assertFalse(report["update_ok"])

    def test_hide_auxiliary_model_objects_reports_each_role(self) -> None:
        point = _FakeHiddenObject(hidden=False)
        axis = _FakeHiddenObject(hidden=False)

        report = BRIDGE._hide_auxiliary_model_objects(
            [
                ("pattern_center_point", point),
                ("pattern_axis", axis),
            ],
            True,
        )

        self.assertTrue(report["ok"])
        self.assertTrue(report["hidden"])
        self.assertEqual([item["role"] for item in report["objects"]], ["pattern_center_point", "pattern_axis"])
        self.assertTrue(point.Hidden)
        self.assertTrue(axis.Hidden)

    def test_bind_operation_variables_sets_expression_by_parameter_note(self) -> None:
        pitch = _FakeOperationVariable("v1", "Шаг", "2")
        height = _FakeOperationVariable("v2", "Высота", "12")
        operation = _FakeOperationObject([pitch, height])

        report = BRIDGE._bind_operation_variables(
            operation,
            [
                {"parameter_note": "Шаг", "expression": "Pitch_thread_1", "role": "spiral_pitch"},
                {"parameter_note": "Высота", "expression": "Length_thread_1 + 1.05 * Pitch_thread_1", "role": "spiral_height"},
            ],
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["applied_count"], 2)
        self.assertEqual(pitch.Expression, "Pitch_thread_1")
        self.assertEqual(height.Expression, "Length_thread_1 + 1.05 * Pitch_thread_1")
        self.assertEqual(pitch.update_count, 1)
        self.assertEqual(height.update_count, 1)
        self.assertEqual(operation.update_count, 2)

    def test_bind_operation_variables_reports_failed_operation_update(self) -> None:
        pitch = _FakeOperationVariable("v1", "Шаг", "2")
        operation = _FakeFailingOperationObject([pitch])

        report = BRIDGE._bind_operation_variables(operation, [{"parameter_note": "Шаг", "expression": "Pitch_thread_1"}])

        self.assertFalse(report["ok"])
        self.assertEqual(report["live_status"], "failed")
        self.assertEqual(report["failed_count"], 1)
        self.assertEqual(report["failed"][0]["error"], "operation_variable_update_failed")


if __name__ == "__main__":
    unittest.main()
