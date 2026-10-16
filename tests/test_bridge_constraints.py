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
    def test_metric_thread_edge_audit_verifies_native_lead_hand_and_constant_radius(self) -> None:
        import math
        from copy import deepcopy

        pitch, turns, count = 2.5, 8, 129
        points = [[pitch*turns*i/(count-1), 10*math.cos(2*math.pi*turns*i/(count-1)),
                   10*math.sin(2*math.pi*turns*i/(count-1))] for i in range(count)]
        result = BRIDGE._metric_helix_edge_evidence(points, pitch)
        self.assertAlmostEqual(result["signed_lead_mm"], pitch)
        self.assertAlmostEqual(result["axial_max_mm"], 20)
        self.assertAlmostEqual(result["turns"], 8)
        # Reversing the native edge parameter must not reverse thread handedness.
        reversed_result = BRIDGE._metric_helix_edge_evidence(list(reversed(points)), pitch)
        self.assertAlmostEqual(reversed_result["signed_lead_mm"], pitch)
        left = [[x,y,-z] for x,y,z in points]
        self.assertAlmostEqual(BRIDGE._metric_helix_edge_evidence(left,pitch,True)["signed_lead_mm"], -pitch)
        with self.assertRaisesRegex(RuntimeError, "lead/hand"):
            BRIDGE._metric_helix_edge_evidence(left,pitch)
        warped = deepcopy(points); warped[31][0] += .01
        with self.assertRaisesRegex(RuntimeError, "constant-lead"):
            BRIDGE._metric_helix_edge_evidence(warped,pitch)
        warped = deepcopy(points); warped[31][1] *= 1.01
        with self.assertRaises(RuntimeError):
            BRIDGE._metric_helix_edge_evidence(warped,pitch)
        self.assertIsNone(BRIDGE._metric_helix_edge_evidence([[0,10,0],[20,10,0]],pitch))

    def test_readonly_fragment_preserves_source_and_cleans_up_after_read_failure(self) -> None:
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        active = SimpleNamespace(Active=True)
        document = SimpleNamespace(Changed=False)
        app = SimpleNamespace(ActiveDocument=active)
        fragment = SimpleNamespace(Close=Mock())
        paths = []
        def write(path):
            paths.append(path)
            Path(path).write_bytes(b"fragment")
            return True
        sketch = SimpleNamespace(Application=app, ConstraintsState=1,
            Part=SimpleNamespace(Parent=document), WriteToFragment=write,
            BeginEditEx=Mock(side_effect=AssertionError("Source definition must not open")),
            EndEdit=Mock(side_effect=AssertionError("Source definition must not commit")))
        with patch.object(BRIDGE, "_open_document_in_app", return_value=(fragment, [])), \
                patch.object(BRIDGE, "_cast_to_com_interface", side_effect=lambda obj, name: obj):
            with self.assertRaisesRegex(RuntimeError, "probe failed"):
                with BRIDGE._readonly_sketch_fragment(sketch) as read:
                    self.assertIs(read, fragment)
                    raise RuntimeError("probe failed")
        fragment.Close.assert_called_once_with(0)
        self.assertEqual(sketch.ConstraintsState, 1)
        self.assertFalse(document.Changed)
        self.assertFalse(Path(paths[0]).exists())
        self.assertTrue(active.Active)

    def test_physical_thread_wrapper_delegates_resolved_faces_without_changing_source_contract(self) -> None:
        from unittest.mock import patch

        carrier = {"rotated": object()}
        faces = [object(), object(), object()]
        reports = []
        params = {"source_scenario": "stepped_shaft", "source_preview": {
            "params": {"steps": [{"length": 20, "diameter": 20}]}},
            "source_selector": "base", "start_selector": "start", "end_selector": "end"}
        result = {"thread": object()}
        with patch.object(BRIDGE, "_apply_part_variables", return_value={"ok": True}), \
                patch.object(BRIDGE, "_build_revolved_source_feature", return_value=carrier) as build, \
                patch.object(BRIDGE, "_get_source_feature_reference_object", return_value=carrier["rotated"]), \
                patch.object(BRIDGE, "_select_revolved_feature_face", side_effect=[(face, {"selector": key})
                    for face,key in zip(faces, ("base", "start", "end"))]), \
                patch.object(BRIDGE, "_apply_helical_thread_feature", return_value=result) as apply:
            actual = BRIDGE._build_external_helical_thread_feature("part", "model", params, {}, reports)
            build.assert_called_once()
            apply.assert_called_once_with("part", "model", params, {}, reports,
                scenario="external_helical_thread", base_face=faces[0], start_face=faces[1], end_face=faces[2],
                face_reports={"base_face": {"selector": "base"}, "start_face": {"selector": "start"}, "end_face": {"selector": "end"}})
            self.assertIs(actual["source_feature"], carrier)
            self.assertIs(actual["thread"], result["thread"])
        # An incomplete input must fail before entering any geometry operation.
        with patch.object(BRIDGE, "_build_revolved_source_feature", side_effect=AssertionError("No source recreation")):
            with self.assertRaisesRegex(ValueError, "carrier faces"):
                BRIDGE._apply_helical_thread_feature("part", "model", {}, {}, [],
                    scenario="external_helical_thread", base_face=faces[0], start_face=None,
                    end_face=faces[2], face_reports={})

    def test_spline_acceptance_requires_bounds_and_every_patterned_cut(self) -> None:
        from copy import deepcopy
        from kompas_mcp.connections.cad import build_straight_spline_plan

        hub = build_straight_spline_plan({"series":"light","designation":"8x36x40","body":"hub"})
        recipe_variables = BRIDGE._spline_recipe_variables(hub)
        recipe, error = BRIDGE._read_spline_recipe({row["name"]:types.SimpleNamespace(Value=row["value"],Note=row.get("note")) for row in recipe_variables})
        self.assertIsNone(error)
        self.assertEqual(recipe["profile_geometry_revision"],2)
        old = deepcopy(hub);old.pop("profile_geometry_revision")
        with self.assertRaisesRegex(ValueError,"revision 2"):
            BRIDGE.handle_create_spline({"plan":old,"execute":True,"confirm_write":True})
        from unittest.mock import patch
        obj = lambda name,ref:types.SimpleNamespace(Name=name,Reference=ref)
        model = types.SimpleNamespace(Sketchs=[obj("Hub blank sketch",1),obj("Hub one tooth space",2)],
            Extrusions=[obj("Hub blank",3),obj("Hub one tooth space cut",4)],
            FeaturePatterns=[obj("Hub tooth space pattern",5)])
        values = {name:1 for name in ("GW_SPLINE_VERSION","SPL_STANDARD","SPL_SERIES","SPL_BODY",
            "SPL_CENTERING","SPL_EXECUTION","SPL_Z","SPL_D","SPL_DD","SPL_B","SPL_ROOT_D","SPL_L","SPL_VERIFIED")}
        values["SPL_BODY"]=2
        variables = [types.SimpleNamespace(Name=name,Value=value) for name,value in values.items()]
        with patch.object(BRIDGE,"_iter_operation_variables",return_value=variables), \
                patch.object(BRIDGE,"cast_model_container",return_value=model), \
                patch.object(BRIDGE,"iter_collection",side_effect=lambda rows:rows), \
                patch.object(BRIDGE,"_read_spline_recipe",return_value=({"studio_profile":{"body":"hub"}},None)):
            legacy=BRIDGE._inspect_spline_block(types.SimpleNamespace(TopPart=types.SimpleNamespace(Name="Hub")))
        self.assertFalse(legacy["verified"])
        self.assertEqual(legacy["status"],"legacy_hub_profile")
        self.assertTrue(legacy["recreatable"])
        plan = build_straight_spline_plan({"series": "light", "designation": "8x36x40"})
        verify = plan["verification"]
        body = {"solid": True, "volume": verify["expected_volume_mm3"] / 1000,
                "bounds_mm": verify["expected_bounds_mm"]}
        reports = [{"id": "tooth_space_cut", "volume_removed": 0.2},
            {"id": "tooth_space_pattern", "valid": True, "count": 8,
             "angle_step": 45.0, "additional_volume_removed": 1.4}]
        accepted = BRIDGE._verify_straight_spline_metrics(plan, body, reports)
        self.assertTrue(accepted["pattern_material_verified"])
        # A readable counter and nominal total volume cannot conceal one missing
        # instance, and a body inside the old radial envelope is not correct bounds.
        wrong_reports = deepcopy(reports)
        wrong_reports[1]["additional_volume_removed"] = 1.2
        with self.assertRaisesRegex(RuntimeError, "material removal"):
            BRIDGE._verify_straight_spline_metrics(plan, body, wrong_reports)
        wrong_body = deepcopy(body)
        wrong_body["bounds_mm"][1] += 2.0
        with self.assertRaisesRegex(RuntimeError, "bounds"):
            BRIDGE._verify_straight_spline_metrics(plan, wrong_body, reports)
        wrong_reports[1]["additional_volume_removed"] = float("nan")
        with self.assertRaisesRegex(RuntimeError, "finite"):
            BRIDGE._verify_straight_spline_metrics(plan, body, wrong_reports)
        finite = {"direction":"normal","end_condition":"length","depth":20}
        self.assertEqual(BRIDGE._cut_extrusion_extent(finite,20),
                         {"direction":"normal","types":(0,0),"depth":20})
        self.assertEqual(BRIDGE._cut_extrusion_extent({"direction":"both"})["types"],(1,1))
        self.assertEqual(BRIDGE._cut_extrusion_extent({"direction":"reverse"})["types"],(0,1))
        with self.assertRaises(ValueError):BRIDGE._cut_extrusion_extent(finite)
        for update in ({"depth":float("nan")},{"depth":21},{"direction":"reverse"},{"end_condition":"through_all"}):
            with self.subTest(bounded_extent=update),self.assertRaises(ValueError):
                BRIDGE._cut_extrusion_extent({**finite,**update},20)

    def test_bevel_section_mapping_preserves_cubic_order_and_knots(self) -> None:
        from kompas_mcp.gears.cad import build_bevel_gear_plan

        plan = build_bevel_gear_plan({})
        section = next(operation for operation in plan["workflow"]["params"]["operations"]
                       if operation["scenario"] == "section_profile_sketch")
        source = section["params"]["entities"]
        frame = {"origin": [0, 0, 0], "u": [1, 0, 0], "v": [0, 1, 0],
                 "u_length": 1, "v_length": 1}
        converted = BRIDGE._section_entities_to_sketch_2d(source, frame)
        curves = [(before, after) for before, after in zip(source, converted)
                  if before["kind"] == "nurbs"]
        self.assertEqual(len(curves), 4)
        for before, after in curves:
            self.assertEqual(after["degree"], 3)
            self.assertEqual(after["order"], 4)
            self.assertEqual(after["knots"], before["knots"])
            self.assertEqual(len(after["knots"]), len(after["points"]) + after["order"])

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

        # A successful value/Update readback does not make an output a driver.
        # Reject before writing the expression (native screenshot regression).
        extrusion.updated = False
        extrusion.Owner.variable.Information = True
        refused = BRIDGE._bind_extrusion_operation_variables(extrusion,
            {"operation_variable_bindings": [{"parameter_note": "Расстояние", "expression": "OTHER_L1"}]},
            "external_flat_step")
        self.assertFalse(refused["ok"])
        self.assertEqual(extrusion.Owner.variable.Expression, "FLAT01_L1")
        self.assertFalse(extrusion.updated)
        self.assertIn("informational_output_variable", refused["failed"][0]["error"])

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
