from __future__ import annotations

import math
from pathlib import Path
import sqlite3
import tempfile
import unittest

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.metric_thread_geometry import build_metric_thread_geometry
from kompas_mcp.parametric import normalize_compression_spring_params
from kompas_mcp.parametric import preview_part_scenario
from kompas_mcp.sketch import normalize_line_style
from kompas_mcp.thread_profile_geometry import build_pipe_bsp_parallel_thread_geometry
from kompas_mcp.thread_profile_geometry import build_pipe_straight_thread_geometry
from kompas_mcp.thread_profile_geometry import build_pipe_tapered_thread_geometry


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, action: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        self.calls.append((action, payload))
        if action == "create_part_from_scenario":
            return {
                "scenario": payload["scenario"],
                "ok": True,
                "output_path": payload["params"]["output_path"],
                "saved": True,
                "closed": payload["params"]["close_after_save"],
                "steps": [{"step": "create_part_document", "ok": True}],
            }
        raise AssertionError(f"Unexpected bridge action: {action}")


class ParametricPartTests(unittest.TestCase):
    def _create_thread_catalog_fixture(self) -> str:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        database_path = Path(temp_dir.name) / "thread.db"
        connection = sqlite3.connect(str(database_path))
        try:
            cursor = connection.cursor()
            cursor.execute(
                "create table [description] (n integer, displayname text, koeff real, cone real, tablename text primary key, note integer)"
            )
            cursor.execute(
                "insert into [description] values (?, ?, ?, ?, ?, ?)",
                (1, "Custom metric coarse", 1.08, 0.0, "custom_metric", 0),
            )
            cursor.execute(
                "insert into [description] values (?, ?, ?, ?, ?, ?)",
                (2, "Custom Whitworth", 1.28, 0.0, "custom_whitworth", 1),
            )
            cursor.execute(
                "create table [custom_metric] (d real, p real, d1 real, row integer, title text)"
            )
            cursor.execute(
                "create table [custom_whitworth] (d real, p real, d1 real, row integer, title text)"
            )
            cursor.execute(
                "insert into [custom_metric] values (?, ?, ?, ?, ?)",
                (20.0, 2.5, 17.3, 1, "M20"),
            )
            cursor.execute(
                "insert into [custom_metric] values (?, ?, ?, ?, ?)",
                (16.0, 2.0, 13.8, 1, "M16"),
            )
            cursor.execute(
                "insert into [custom_whitworth] values (?, ?, ?, ?, ?)",
                (20.0, 2.5, 17.0, 1, "G3/4"),
            )
            connection.commit()
        finally:
            connection.close()
        return str(database_path)

    def test_preview_stepped_shaft_builds_rotation_profile(self) -> None:
        preview = preview_part_scenario(
            "shaft",
            {
                "steps": [
                    {"length": 20, "diameter": 10},
                    {"length": 30, "diameter": 16},
                    {"length": 10, "diameter": 12},
                ],
            },
        )

        variables = preview["operations"][1]["variables"]
        profile = preview["operations"][4]["profile_points"]
        self.assertEqual(preview["scenario"], "stepped_shaft")
        self.assertEqual(preview["summary"]["step_count"], 3)
        self.assertEqual(preview["summary"]["total_length"], 60.0)
        self.assertEqual(preview["summary"]["creation_status"], "available")
        self.assertEqual(preview["summary"]["axis_line_style"], 3)
        self.assertEqual(preview["params"]["sketch"]["dimension_display"], "radius")
        self.assertEqual(preview["summary"]["dimension_display"], "radius")
        self.assertIsNone(preview["summary"]["parameter_prefix"])
        self.assertEqual(preview["summary"]["placement_mode"], "global")
        self.assertEqual(preview["summary"]["placement_origin"], [0.0, 0.0])
        self.assertEqual(preview["summary"]["placement_base_mode"], "global")
        self.assertEqual(preview["summary"]["placement_base_origin"], [0.0, 0.0])
        self.assertEqual(preview["summary"]["placement_local_offset"], [0.0, 0.0])
        self.assertGreater(preview["summary"]["planned_dimension_count"], 0)
        self.assertGreater(preview["summary"]["planned_constraint_count"], 0)
        self.assertGreater(preview["summary"]["planned_variable_count"], 0)
        constraints = preview["operations"][5]["constraints"]
        dimensions = preview["operations"][6]["dimensions"]
        self.assertIn("parallel", {constraint["kind"] for constraint in constraints})
        self.assertIn("perpendicular", {constraint["kind"] for constraint in constraints})
        self.assertNotIn("fixed_length", {constraint["kind"] for constraint in constraints})
        self.assertIn("merge_points", {constraint["kind"] for constraint in constraints})
        self.assertNotIn("point_on_curve", {constraint["kind"] for constraint in constraints})
        self.assertNotIn("vertical", {constraint["kind"] for constraint in constraints})
        self.assertEqual(constraints[0]["kind"], "horizontal")
        self.assertEqual(constraints[1]["kind"], "fixed_point")
        self.assertEqual(constraints[1]["target"], "axis")
        self.assertEqual(constraints[1]["index"], 0)
        self.assertEqual(constraints[2]["kind"], "merge_points")
        self.assertEqual(constraints[2]["target"], "profile_line_1")
        self.assertEqual(constraints[2]["partner"], "axis")
        self.assertEqual(constraints[2]["index"], 0)
        self.assertEqual(constraints[2]["partner_index"], 0)
        self.assertTrue(any(item["name"] == "profile_end_to_axis_end" for item in constraints))
        self.assertIn("line_length", {dimension["kind"] for dimension in dimensions})
        self.assertIn("axis_distance", {dimension["kind"] for dimension in dimensions})
        self.assertIn("target", dimensions[0])
        radial = next(dimension for dimension in dimensions if dimension["kind"] == "axis_distance")
        linear = next(dimension for dimension in dimensions if dimension["kind"] == "line_length")
        self.assertEqual(radial["name"], "R1")
        self.assertEqual(radial["variable"], "R1")
        self.assertEqual(radial["expression"], "D1 / 2")
        self.assertEqual(linear["name"], "SKL1")
        self.assertEqual(linear["variable"], "SKL1")
        self.assertEqual(linear["expression"], "L1")
        self.assertNotIn("display_mode", radial)
        self.assertNotIn("native_break", radial)
        self.assertEqual(variables[0]["name"], "D1")
        self.assertNotIn("expression", variables[0])
        self.assertEqual(variables[0]["value"], 10.0)
        self.assertEqual(variables[0]["note"], "Stepped shaft | step-1 | Diameter D1")
        self.assertEqual(variables[1]["name"], "L1")
        self.assertEqual(variables[1]["value"], 20.0)
        self.assertEqual(variables[1]["note"], "Stepped shaft | step-1 | Length L1")
        self.assertEqual(preview["interface"]["feature_type"], "revolved_body.stepped_shaft")
        self.assertEqual(preview["summary"]["operation_label"], "Stepped shaft")
        self.assertEqual(preview["interface"]["operation_label"], "Stepped shaft")
        self.assertEqual(preview["interface"]["anchors"]["axis_start"], [0.0, 0.0])
        self.assertEqual(preview["interface"]["anchors"]["axis_end"], [60.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["axis"]["type"], "axis")
        self.assertEqual(preview["interface"]["outputs"]["start_face"]["origin"], [0.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["end_face"]["selector"], "far_end_face")
        self.assertEqual(preview["interface"]["outputs"]["step_2_outer_face"]["origin"], [35.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["parameters"]["driving_diameters"], ["D1", "D2", "D3"])
        self.assertEqual(preview["interface"]["parameters"]["driving_lengths"], ["L1", "L2", "L3"])
        self.assertEqual(profile[0], [0.0, 0.0])
        self.assertEqual(profile[1], [0.0, 5.0])
        self.assertIn([20.0, 8.0], profile)
        self.assertEqual(profile[-1], [0.0, 0.0])

    def test_preview_supports_explicit_radius_dimension_display(self) -> None:
        preview = preview_part_scenario(
            "stepped_shaft",
            {
                "steps": [{"length": 10, "diameter": 8}],
                "sketch": {"dimension_display": "radius"},
            },
        )

        variables = preview["operations"][1]["variables"]
        dimensions = preview["operations"][6]["dimensions"]
        radial = next(dimension for dimension in dimensions if dimension["kind"] == "axis_distance")
        linear = next(dimension for dimension in dimensions if dimension["kind"] == "line_length")
        self.assertEqual(preview["params"]["sketch"]["dimension_display"], "radius")
        self.assertEqual(preview["summary"]["dimension_display"], "radius")
        self.assertEqual(radial["name"], "R1")
        self.assertEqual(radial["expression"], "D1 / 2")
        self.assertEqual(linear["name"], "SKL1")
        self.assertEqual(linear["expression"], "L1")
        self.assertNotIn("display_mode", radial)
        self.assertNotIn("native_break", radial)
        self.assertEqual(variables[0]["name"], "D1")
        self.assertNotIn("expression", variables[0])
        self.assertEqual(variables[1]["name"], "L1")

    def test_preview_rejects_invalid_steps(self) -> None:
        with self.assertRaises(ValueError):
            preview_part_scenario("stepped_shaft", {"steps": [{"length": 10, "diameter": 0}]})

    def test_preview_external_conical_step_builds_rotation_profile(self) -> None:
        preview = preview_part_scenario(
            "external_conical_step",
            {
                "length": 40,
                "start_diameter": 30,
                "end_diameter": 18,
                "parameter_prefix": "cone01",
            },
        )

        variables = preview["operations"][1]["variables"]
        constraints = preview["operations"][5]["constraints"]
        dimensions = preview["operations"][6]["dimensions"]
        profile = preview["operations"][4]["profile_points"]
        self.assertEqual(preview["scenario"], "external_conical_step")
        self.assertEqual(preview["summary"]["length"], 40.0)
        self.assertEqual(preview["summary"]["start_diameter"], 30.0)
        self.assertEqual(preview["summary"]["end_diameter"], 18.0)
        self.assertEqual(preview["summary"]["parameter_prefix"], "CONE01")
        self.assertEqual(preview["interface"]["feature_type"], "revolved_body.external_conical_step")
        self.assertEqual(preview["interface"]["outputs"]["start_face"]["origin"], [0.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["end_face"]["origin"], [40.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["outer_face"]["origin"], [20.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["large_end_face"]["origin"], [0.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["seat_face"]["origin"], [0.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["small_end_face"]["origin"], [40.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["free_end_face"]["origin"], [40.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["parameters"]["driving_diameters"], ["CONE01_D1", "CONE01_D2"])
        self.assertEqual(preview["interface"]["parameters"]["driving_lengths"], ["CONE01_L1"])
        self.assertIn("merge_points", {constraint["kind"] for constraint in constraints})
        self.assertIn("perpendicular", {constraint["kind"] for constraint in constraints})
        self.assertEqual(dimensions[0]["target"], "axis")
        self.assertEqual(dimensions[0]["expression"], "CONE01_L1")
        self.assertEqual(dimensions[1]["expression"], "CONE01_D1 / 2")
        self.assertEqual(dimensions[1]["support_point_index"], 1)
        self.assertEqual(dimensions[2]["expression"], "CONE01_D2 / 2")
        self.assertEqual(dimensions[2]["support_point_index"], 0)
        self.assertEqual(variables[0]["note"], "External conical step [CONE01] | start | Start diameter CONE01_D1")
        self.assertEqual(variables[1]["note"], "External conical step [CONE01] | end | End diameter CONE01_D2")
        self.assertEqual(variables[2]["note"], "External conical step [CONE01] | body | Length CONE01_L1")
        self.assertEqual(profile[0], [0.0, 0.0])
        self.assertEqual(profile[1], [0.0, 15.0])
        self.assertEqual(profile[2], [40.0, 9.0])
        self.assertEqual(profile[-1], [0.0, 0.0])

    def test_preview_external_conical_step_rejects_equal_diameters(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"external_conical_step requires different start_diameter and end_diameter",
        ):
            preview_part_scenario(
                "external_conical_step",
                {"length": 40, "start_diameter": 20, "end_diameter": 20},
            )

    def test_preview_external_conical_step_supports_diameters_and_angle_definition(self) -> None:
        preview = preview_part_scenario(
            "external_conical_step",
            {
                "start_diameter": 30,
                "end_diameter": 18,
                "cone_angle_degrees": 10,
            },
        )

        expected_length = abs(30.0 - 18.0) / (2.0 * math.tan(math.radians(10.0)))
        self.assertEqual(preview["summary"]["definition_mode"], "diameters_angle")
        self.assertAlmostEqual(preview["summary"]["length"], expected_length, places=6)
        self.assertAlmostEqual(preview["summary"]["cone_angle_degrees"], 10.0, places=6)
        self.assertAlmostEqual(preview["summary"]["conicity"], abs(30.0 - 18.0) / expected_length, places=6)
        self.assertEqual(preview["summary"]["slope_direction"], "inward")

    def test_preview_external_conical_step_supports_diameters_and_conicity_definition(self) -> None:
        preview = preview_part_scenario(
            "external_conical_step",
            {
                "start_diameter": 18,
                "end_diameter": 30,
                "conicity": "1:5",
            },
        )

        self.assertEqual(preview["summary"]["definition_mode"], "diameters_conicity")
        self.assertAlmostEqual(preview["summary"]["length"], 60.0, places=6)
        self.assertAlmostEqual(preview["summary"]["conicity"], 0.2, places=6)
        self.assertEqual(preview["summary"]["slope_direction"], "outward")

    def test_preview_external_conical_step_supports_single_diameter_length_angle_definition(self) -> None:
        preview = preview_part_scenario(
            "external_conical_step",
            {
                "length": 40,
                "start_diameter": 18,
                "cone_angle_degrees": 10,
                "slope_direction": "outward",
            },
        )

        expected_end = 18.0 + 2.0 * 40.0 * math.tan(math.radians(10.0))
        self.assertEqual(preview["summary"]["definition_mode"], "one_diameter_length_angle")
        self.assertAlmostEqual(preview["summary"]["start_diameter"], 18.0, places=6)
        self.assertAlmostEqual(preview["summary"]["end_diameter"], expected_end, places=6)
        self.assertEqual(preview["summary"]["slope_direction"], "outward")

    def test_preview_external_conical_step_supports_single_diameter_length_conicity_definition(self) -> None:
        preview = preview_part_scenario(
            "external_conical_step",
            {
                "length": 40,
                "end_diameter": 18,
                "conicity": 0.2,
                "slope_direction": "inward",
            },
        )

        self.assertEqual(preview["summary"]["definition_mode"], "one_diameter_length_conicity")
        self.assertAlmostEqual(preview["summary"]["start_diameter"], 26.0, places=6)
        self.assertAlmostEqual(preview["summary"]["end_diameter"], 18.0, places=6)
        self.assertEqual(preview["summary"]["slope_direction"], "inward")

    def test_preview_internal_conical_step_builds_cut_profile(self) -> None:
        preview = preview_part_scenario(
            "internal_conical_step",
            {
                "length": 24,
                "start_diameter": 12,
                "end_diameter": 6,
                "axial_direction": "backward",
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 40, "diameter": 32}]},
                "parameter_prefix": "icut01",
            },
        )

        self.assertEqual(preview["scenario"], "internal_conical_step")
        self.assertEqual(preview["summary"]["axial_direction"], "backward")
        self.assertEqual(preview["summary"]["source_scenario"], "stepped_shaft")
        self.assertFalse(preview["summary"]["requires_existing_body"])
        self.assertEqual(preview["operations"][1]["operation"], "create_source_body")
        self.assertEqual(preview["operations"][-1]["operation"], "cut_rotation")
        self.assertEqual(preview["interface"]["feature_type"], "revolved_cut.internal_conical_step")
        self.assertEqual(preview["interface"]["outputs"]["start_face"]["origin"], [0.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["end_face"]["origin"], [-24.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["inner_face"]["origin"], [-12.0, 0.0, 0.0])
        self.assertEqual(preview["operations"][2]["variables"][0]["note"], "Internal conical step [ICUT01] | start | Start diameter ICUT01_D1")
        profile = preview["operations"][5]["profile_points"]
        self.assertEqual(profile[1], [0.0, 6.0])
        self.assertEqual(profile[2], [-24.0, 3.0])

    def test_preview_internal_conical_step_requires_valid_source_when_provided(self) -> None:
        with self.assertRaisesRegex(ValueError, r"internal_conical_step source_scenario must be stepped_shaft or external_conical_step"):
            preview_part_scenario(
                "internal_conical_step",
                {
                    "length": 24,
                    "start_diameter": 12,
                    "end_diameter": 6,
                    "source_scenario": "point",
                    "source_params": {"origin": [0, 0, 0]},
                },
            )

    def test_preview_internal_conical_step_supports_workflow_placement_operation(self) -> None:
        preview = preview_part_scenario(
            "workflow",
            {
                "operations": [
                    {
                        "id": "lcs01",
                        "scenario": "lcs",
                        "params": {"mode": "global", "lcs_name": "LCS01", "origin": [40, 0, 0]},
                    },
                    {
                        "id": "icut01",
                        "scenario": "internal_conical_step",
                        "params": {
                            "length": 18,
                            "start_diameter": 10,
                            "end_diameter": 4,
                            "axial_direction": "backward",
                            "placement": {"base": {"reference": {"ref": "lcs01.lcs"}}},
                        },
                    },
                ],
                "exports": {"inner_face": "icut01.inner_face"},
            },
        )

        operations = preview["params"]["operations"]
        self.assertEqual(operations[1]["scenario"], "internal_conical_step")
        self.assertEqual(operations[1]["bindings"]["placement_operation"], "lcs01")
        self.assertEqual(operations[1]["params"]["placement"]["base"]["reference"]["output_ref"], "lcs01.lcs")
        self.assertEqual(operations[1]["preview"]["interface"]["outputs"]["inner_face"]["selector"], "inner_face")

    def test_preview_internal_cylindrical_step_builds_cut_profile(self) -> None:
        preview = preview_part_scenario(
            "internal_cylindrical_step",
            {
                "length": 24,
                "diameter": 12,
                "axial_direction": "backward",
                "parameter_prefix": "ibore01",
                "source_scenario": "stepped_shaft",
                "source_params": {
                    "steps": [{"length": 48, "diameter": 30}],
                },
            },
        )

        self.assertEqual(preview["scenario"], "internal_cylindrical_step")
        self.assertEqual(preview["summary"]["length"], 24.0)
        self.assertEqual(preview["summary"]["diameter"], 12.0)
        self.assertEqual(preview["summary"]["axial_direction"], "backward")
        self.assertEqual(preview["summary"]["source_scenario"], "stepped_shaft")
        self.assertFalse(preview["summary"]["requires_existing_body"])
        self.assertEqual(preview["operations"][1]["operation"], "create_source_body")
        self.assertEqual(preview["operations"][-1]["operation"], "cut_rotation")
        self.assertEqual(preview["interface"]["feature_type"], "revolved_cut.internal_cylindrical_step")
        self.assertEqual(preview["interface"]["outputs"]["start_face"]["origin"], [0.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["end_face"]["origin"], [-24.0, 0.0, 0.0])
        self.assertEqual(preview["interface"]["outputs"]["inner_face"]["origin"], [-12.0, 0.0, 0.0])
        dimensions = preview["operations"][7]["dimensions"]
        self.assertEqual(dimensions[0]["expression"], "IBORE01_L1")
        self.assertEqual(dimensions[1]["expression"], "IBORE01_D1 / 2")
        profile = preview["operations"][5]["profile_points"]
        self.assertEqual(profile[1], [0.0, 6.0])
        self.assertEqual(profile[2], [-24.0, 6.0])

    def test_preview_internal_cylindrical_step_supports_multiple_steps(self) -> None:
        preview = preview_part_scenario(
            "internal_cylindrical_step",
            {
                "parameter_prefix": "ibore02",
                "steps": [
                    {"length": 12, "diameter": 10},
                    {"length": 8, "diameter": 16},
                    {"length": 20, "diameter": 12},
                ],
            },
        )

        summary = preview["summary"]
        outputs = preview["interface"]["outputs"]
        dimensions = preview["operations"][6]["dimensions"]

        self.assertEqual(summary["step_count"], 3)
        self.assertEqual(summary["total_length"], 40.0)
        self.assertEqual(summary["step_lengths"], [12.0, 8.0, 20.0])
        self.assertEqual(summary["step_diameters"], [10.0, 16.0, 12.0])
        self.assertEqual(summary["min_diameter"], 10.0)
        self.assertEqual(summary["max_diameter"], 16.0)
        self.assertEqual(outputs["step_2_inner_face"]["selector"], "step_2_inner_face")
        self.assertEqual(outputs["shoulder_1_face"]["selector"], "shoulder_1_face")
        self.assertEqual(outputs["step_3_end_face"]["selector"], "step_3_end_face")
        self.assertEqual(dimensions[0]["expression"], "IBORE02_L1")
        self.assertEqual(dimensions[1]["expression"], "IBORE02_D1 / 2")
        self.assertEqual(dimensions[2]["expression"], "IBORE02_L2")
        self.assertEqual(dimensions[3]["expression"], "IBORE02_D2 / 2")
        self.assertEqual(dimensions[4]["expression"], "IBORE02_L3")
        self.assertEqual(dimensions[5]["expression"], "IBORE02_D3 / 2")

    def test_preview_internal_cylindrical_step_supports_workflow_placement_operation(self) -> None:
        preview = preview_part_scenario(
            "workflow",
            {
                "operations": [
                    {
                        "id": "lcs01",
                        "scenario": "lcs",
                        "params": {"mode": "global", "lcs_name": "LCS01", "origin": [40, 0, 0]},
                    },
                    {
                        "id": "ibore01",
                        "scenario": "internal_cylindrical_step",
                        "params": {
                            "length": 18,
                            "diameter": 8,
                            "placement": {"base": {"reference": {"ref": "lcs01.lcs"}}},
                        },
                    },
                ]
            },
        )

        operations = preview["params"]["operations"]
        self.assertEqual(operations[1]["scenario"], "internal_cylindrical_step")
        self.assertEqual(operations[1]["bindings"]["placement_operation"], "lcs01")
        self.assertEqual(operations[1]["params"]["placement"]["base"]["reference"]["output_ref"], "lcs01.lcs")
        self.assertEqual(operations[1]["preview"]["interface"]["outputs"]["inner_face"]["selector"], "inner_face")

    def test_preview_external_polygonal_step_builds_extrusion_profile(self) -> None:
        preview = preview_part_scenario(
            "external_polygonal_step",
            {
                "diameter": 24,
                "length": 18,
                "side_count": 6,
                "diameter_mode": "inscribed_circle",
                "parameter_prefix": "poly01",
            },
        )

        self.assertEqual(preview["scenario"], "external_polygonal_step")
        self.assertEqual(preview["summary"]["diameter"], 24.0)
        self.assertEqual(preview["summary"]["length"], 18.0)
        self.assertEqual(preview["summary"]["side_count"], 6)
        self.assertEqual(preview["summary"]["diameter_mode"], "inscribed_circle")
        self.assertEqual(preview["summary"]["planned_variable_count"], 2)
        self.assertEqual(preview["summary"]["planned_dimension_count"], 1)
        self.assertGreater(preview["summary"]["planned_constraint_count"], 0)
        self.assertEqual(preview["operations"][1]["operation"], "add_variables")
        self.assertEqual(preview["operations"][2]["operation"], "create_sketch")
        self.assertEqual(preview["operations"][3]["operation"], "draw_regular_polygon")
        self.assertEqual(preview["operations"][4]["operation"], "apply_constraints")
        self.assertEqual(preview["operations"][5]["operation"], "add_dimensions")
        self.assertEqual(preview["operations"][6]["operation"], "boss_extrusion")
        self.assertEqual(preview["operations"][6]["operation_variable_bindings"][0]["expression"], "POLY01_L1")
        self.assertEqual(preview["interface"]["feature_type"], "extruded_body.external_polygonal_step")
        self.assertEqual(preview["interface"]["outputs"]["start_face"]["selector"], "start_face")
        self.assertEqual(preview["interface"]["outputs"]["far_end_face"]["selector"], "end_face")
        self.assertEqual(preview["interface"]["outputs"]["side_face_1"]["selector"], "side_face_1")
        self.assertEqual(len(preview["interface"]["anchors"]["profile_vertices"]), 6)
        self.assertEqual(preview["interface"]["parameters"]["driving_diameters"], ["POLY01_D1"])
        self.assertEqual(preview["interface"]["parameters"]["driving_lengths"], ["POLY01_L1"])
        self.assertEqual(preview["interface"]["parameters"]["internal_sizes"], ["POLY01_R1"])
        variables = preview["operations"][1]["variables"]
        self.assertEqual(variables[0]["name"], "POLY01_D1")
        self.assertEqual(variables[0]["note"], "External polygonal step [POLY01] | profile | Diameter POLY01_D1")
        self.assertEqual(variables[1]["name"], "POLY01_L1")
        self.assertEqual(variables[1]["note"], "External polygonal step [POLY01] | profile | Length POLY01_L1")

    def test_preview_internal_polygonal_step_builds_cut_profile(self) -> None:
        preview = preview_part_scenario(
            "internal_polygonal_step",
            {
                "diameter": 14,
                "length": 16,
                "side_count": 8,
                "diameter_mode": "circumscribed_circle",
                "axial_direction": "backward",
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 32, "diameter": 28}]},
                "parameter_prefix": "ipoly01",
            },
        )

        self.assertEqual(preview["scenario"], "internal_polygonal_step")
        self.assertEqual(preview["summary"]["source_scenario"], "stepped_shaft")
        self.assertEqual(preview["summary"]["axial_direction"], "backward")
        self.assertEqual(preview["summary"]["planned_variable_count"], 2)
        self.assertEqual(preview["summary"]["planned_dimension_count"], 1)
        self.assertGreater(preview["summary"]["planned_constraint_count"], 0)
        self.assertEqual(preview["operations"][1]["operation"], "create_source_body")
        self.assertEqual(preview["operations"][2]["operation"], "add_variables")
        self.assertEqual(preview["operations"][-1]["operation"], "cut_extrusion")
        self.assertEqual(preview["operations"][-1]["operation_variable_bindings"][0]["expression"], "IPOLY01_L1")
        self.assertEqual(preview["interface"]["feature_type"], "extruded_cut.internal_polygonal_step")
        self.assertEqual(preview["interface"]["outputs"]["end_face"]["selector"], "end_face")
        self.assertEqual(preview["interface"]["outputs"]["side_face_1"]["selector"], "side_face_1")
        self.assertEqual(preview["interface"]["parameters"]["driving_lengths"], ["IPOLY01_L1"])

    def test_preview_external_flat_step_builds_extrusion_profile(self) -> None:
        preview = preview_part_scenario(
            "external_flat_step",
            {
                "diameter": 28,
                "length": 16,
                "flat_depth": 4,
                "flats_count": 1,
                "parameter_prefix": "flat01",
            },
        )
        self.assertEqual(preview["scenario"], "external_flat_step")
        self.assertEqual(preview["summary"]["diameter"], 28.0)
        self.assertEqual(preview["summary"]["length"], 16.0)
        self.assertEqual(preview["summary"]["flat_depth"], 4.0)
        self.assertEqual(preview["summary"]["flats_count"], 1)
        self.assertEqual(preview["summary"]["planned_variable_count"], 3)
        self.assertEqual(preview["summary"]["planned_dimension_count"], 2)
        self.assertGreater(preview["summary"]["planned_constraint_count"], 0)
        self.assertEqual(preview["operations"][1]["operation"], "add_variables")
        self.assertEqual(preview["operations"][-1]["operation_variable_bindings"][0]["expression"], "FLAT01_L1")
        self.assertEqual(preview["interface"]["feature_type"], "extruded_body.external_flat_step")
        self.assertEqual(preview["interface"]["outputs"]["start_face"]["selector"], "start_face")
        self.assertEqual(preview["interface"]["outputs"]["far_end_face"]["selector"], "end_face")
        self.assertEqual(preview["interface"]["outputs"]["flat_1_face"]["selector"], "flat_1_face")
        self.assertEqual(preview["interface"]["parameters"]["driving_diameters"], ["FLAT01_D1"])
        self.assertEqual(preview["interface"]["parameters"]["driving_lengths"], ["FLAT01_L1"])
        self.assertEqual(preview["interface"]["parameters"]["driving_flat_depths"], ["FLAT01_F1"])
        self.assertEqual(preview["interface"]["parameters"]["internal_sizes"], ["FLAT01_R1"])

    def test_preview_internal_flat_step_builds_cut_profile(self) -> None:
        preview = preview_part_scenario(
            "internal_flat_step",
            {
                "diameter": 20,
                "length": 18,
                "flat_depth": 3,
                "flats_count": 2,
                "axial_direction": "backward",
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 30, "diameter": 40}]},
                "parameter_prefix": "iflat01",
            },
        )
        self.assertEqual(preview["scenario"], "internal_flat_step")
        self.assertEqual(preview["summary"]["source_scenario"], "stepped_shaft")
        self.assertEqual(preview["summary"]["axial_direction"], "backward")
        self.assertEqual(preview["summary"]["planned_variable_count"], 3)
        self.assertEqual(preview["summary"]["planned_dimension_count"], 3)
        self.assertGreater(preview["summary"]["planned_constraint_count"], 0)
        self.assertEqual(preview["operations"][1]["operation"], "create_source_body")
        self.assertEqual(preview["operations"][2]["operation"], "add_variables")
        self.assertEqual(preview["operations"][-1]["operation"], "cut_extrusion")
        self.assertEqual(preview["operations"][-1]["operation_variable_bindings"][0]["expression"], "IFLAT01_L1")
        self.assertEqual(preview["interface"]["feature_type"], "extruded_cut.internal_flat_step")
        self.assertEqual(preview["interface"]["outputs"]["end_face"]["selector"], "end_face")
        self.assertEqual(preview["interface"]["outputs"]["flat_1_face"]["selector"], "flat_1_face")
        self.assertEqual(preview["interface"]["outputs"]["flat_2_face"]["selector"], "flat_2_face")
        self.assertEqual(preview["interface"]["parameters"]["driving_lengths"], ["IFLAT01_L1"])

    def test_preview_external_threaded_step_builds_thread_contract(self) -> None:
        database_path = self._create_thread_catalog_fixture()
        preview = preview_part_scenario(
            "external_threaded_step",
            {
                "diameter": 20,
                "pitch": 2.5,
                "depth": 12,
                "direction": "left",
                "thread_standard": "custom_metric",
                "thread_database_path": database_path,
                "source_scenario": "stepped_shaft",
                "source_params": {
                    "steps": [
                        {"length": 20, "diameter": 20},
                        {"length": 12, "diameter": 30},
                    ]
                },
                "source_selector": "step_1_outer_face",
            },
        )

        self.assertEqual(preview["scenario"], "external_threaded_step")
        self.assertEqual(preview["summary"]["source_scenario"], "stepped_shaft")
        self.assertEqual(preview["summary"]["source_selector"], "step_1_outer_face")
        self.assertEqual(preview["summary"]["thread_designation"], "M20")
        self.assertEqual(preview["summary"]["thread_standard_table_name"], "custom_metric")
        self.assertEqual(preview["summary"]["depth"], 12.0)
        self.assertEqual(preview["summary"]["thread_length"], 12.0)
        self.assertEqual(preview["summary"]["direction"], "left")
        self.assertTrue(preview["summary"]["left_thread"])
        self.assertFalse(preview["summary"]["auto_length"])
        self.assertEqual(preview["operations"][1]["operation"], "create_source_body")
        self.assertEqual(preview["operations"][2]["operation"], "add_thread")
        self.assertEqual(preview["operations"][2]["depth"], 12.0)
        self.assertEqual(preview["operations"][2]["direction"], "left")
        self.assertEqual(preview["interface"]["feature_type"], "cosmetic_thread.external_threaded_step")
        self.assertEqual(preview["interface"]["outputs"]["base_face"]["selector"], "step_1_outer_face")
        self.assertEqual(preview["interface"]["outputs"]["start_border"]["selector"], "step_1_start_face")
        self.assertEqual(preview["interface"]["outputs"]["end_border"]["selector"], "step_1_end_face")

    def test_preview_internal_threaded_step_builds_thread_contract(self) -> None:
        database_path = self._create_thread_catalog_fixture()
        preview = preview_part_scenario(
            "internal_threaded_step",
            {
                "diameter": 16,
                "pitch": 2.0,
                "depth": 10,
                "direction": "right",
                "thread_standard": "custom_metric",
                "thread_database_path": database_path,
                "source_scenario": "internal_cylindrical_step",
                "source_params": {
                    "steps": [
                        {"length": 18, "diameter": 16},
                    ],
                    "source_scenario": "stepped_shaft",
                    "source_params": {
                        "steps": [{"length": 30, "diameter": 36}],
                    },
                },
            },
        )

        self.assertEqual(preview["scenario"], "internal_threaded_step")
        self.assertEqual(preview["summary"]["source_scenario"], "internal_cylindrical_step")
        self.assertEqual(preview["summary"]["source_selector"], "inner_face")
        self.assertEqual(preview["summary"]["thread_designation"], "M16")
        self.assertEqual(preview["summary"]["depth"], 10.0)
        self.assertEqual(preview["summary"]["thread_length"], 10.0)
        self.assertEqual(preview["summary"]["direction"], "right")
        self.assertFalse(preview["summary"]["left_thread"])
        self.assertTrue(preview["summary"]["internal"])
        self.assertEqual(preview["interface"]["feature_type"], "cosmetic_thread.internal_threaded_step")
        self.assertEqual(preview["interface"]["outputs"]["base_face"]["selector"], "inner_face")
        self.assertEqual(preview["interface"]["outputs"]["start_border"]["selector"], "step_1_start_face")
        self.assertEqual(preview["interface"]["outputs"]["end_border"]["selector"], "step_1_end_face")

    def test_preview_external_threaded_step_defaults_conical_entry_at_small_end(self) -> None:
        database_path = self._create_thread_catalog_fixture()
        preview = preview_part_scenario(
            "external_threaded_step",
            {
                "diameter": 20,
                "pitch": 2.5,
                "depth": 12,
                "thread_standard": "custom_metric",
                "thread_database_path": database_path,
                "source_scenario": "external_conical_step",
                "source_params": {
                    "length": 12,
                    "start_diameter": 20,
                    "end_diameter": 19.25,
                },
            },
        )

        self.assertEqual(preview["summary"]["start_selector"], "end_face")
        self.assertEqual(preview["summary"]["end_selector"], "start_face")
        self.assertEqual(preview["interface"]["outputs"]["start_border"]["selector"], "end_face")
        self.assertEqual(preview["interface"]["outputs"]["end_border"]["selector"], "start_face")

    def test_preview_external_threaded_step_rejects_large_to_small_conical_span(self) -> None:
        database_path = self._create_thread_catalog_fixture()
        with self.assertRaisesRegex(
            ValueError,
            r"external_threaded_step external conical thread must run from end_face "
            r"\(small/free entry end\) to start_face \(large/seat end\)",
        ):
            preview_part_scenario(
                "external_threaded_step",
                {
                    "diameter": 20,
                    "pitch": 2.5,
                    "depth": 12,
                    "thread_standard": "custom_metric",
                    "thread_database_path": database_path,
                    "start_selector": "seat_face",
                    "end_selector": "free_end_face",
                    "source_scenario": "external_conical_step",
                    "source_params": {
                        "length": 12,
                        "start_diameter": 20,
                        "end_diameter": 19.25,
                    },
                },
            )

    def test_preview_external_helical_thread_builds_cut_contract(self) -> None:
        preview = preview_part_scenario(
            "external_helical_thread",
            {
                "diameter": 20,
                "pitch": 2.0,
                "length": 12,
                "depth": 1.1,
                "clearance": 0.2,
                "direction": "left",
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 20, "diameter": 20}]},
            },
        )

        self.assertEqual(preview["scenario"], "external_helical_thread")
        self.assertEqual(preview["summary"]["source_scenario"], "stepped_shaft")
        self.assertEqual(preview["summary"]["source_selector"], "step_1_outer_face")
        self.assertEqual(preview["summary"]["diameter"], 20.0)
        self.assertEqual(preview["summary"]["pitch"], 2.0)
        self.assertEqual(preview["summary"]["length"], 12.0)
        self.assertAlmostEqual(preview["summary"]["depth"], 1.1, places=6)
        self.assertEqual(preview["summary"]["clearance"], 0.2)
        self.assertAlmostEqual(preview["summary"]["fundamental_triangle_height"], 2.0 / (2.0 * math.tan(math.radians(30.0))), places=6)
        self.assertAlmostEqual(preview["summary"]["major_radius"], 10.0, places=6)
        self.assertAlmostEqual(preview["summary"]["root_radius_level"], 8.7, places=6)
        self.assertAlmostEqual(preview["summary"]["root_diameter"], 17.4, places=6)
        self.assertAlmostEqual(preview["summary"]["profile_base_drop"], preview["summary"]["fundamental_triangle_height"] / 8.0, places=6)
        self.assertAlmostEqual(preview["summary"]["profile_apex_height"], preview["summary"]["fundamental_triangle_height"] * 7.0 / 8.0, places=6)
        self.assertAlmostEqual(preview["summary"]["profile_outer_half_width"], 0.875, places=6)
        self.assertAlmostEqual(preview["summary"]["root_radius"], 0.21554445662276763, places=6)
        self.assertAlmostEqual(preview["summary"]["profile_entry_offset"], 2.1, places=6)
        self.assertAlmostEqual(preview["summary"]["profile_surface_offset"], 0.2, places=6)
        self.assertAlmostEqual(preview["summary"]["profile_surface_offset_effective"], 0.0, places=6)
        self.assertFalse(preview["summary"]["profile_surface_offset_applied"])
        self.assertEqual(preview["summary"]["profile_surface_offset_status"], "ignored_in_v1")
        self.assertAlmostEqual(preview["summary"]["profile_sketch_origin_shift"], 10.0, places=6)
        self.assertEqual(preview["summary"]["direction"], "left")
        self.assertEqual(preview["summary"]["parameter_prefix"], "EXTERNAL_HELICAL_THREAD")
        self.assertAlmostEqual(preview["summary"]["spiral_length"], 14.1, places=6)
        self.assertEqual(preview["summary"]["planned_variable_count"], 3)
        self.assertEqual(preview["summary"]["planned_dimension_count"], 7)
        self.assertEqual(preview["summary"]["planned_constraint_count"], 39)
        self.assertEqual(preview["operations"][1]["operation"], "add_variables")
        self.assertEqual(preview["operations"][1]["variable_count"], 3)
        self.assertEqual(preview["operations"][1]["variables"][0]["name"], "Diameter_thread_external_left_M20x2_1")
        self.assertEqual(preview["operations"][1]["variables"][1]["name"], "Pitch_thread_external_left_M20x2_1")
        self.assertEqual(preview["operations"][1]["variables"][2]["name"], "Length_thread_external_left_M20x2_1")
        self.assertTrue(preview["operations"][1]["variables"][0]["external"])
        self.assertTrue(preview["operations"][1]["variables"][1]["external"])
        self.assertTrue(preview["operations"][1]["variables"][2]["external"])
        self.assertEqual(preview["operations"][2]["operation"], "create_source_body")
        self.assertEqual(preview["operations"][3]["operation"], "create_spiral_path")
        self.assertAlmostEqual(preview["operations"][3]["spiral_length"], 14.1, places=6)
        self.assertEqual(preview["operations"][4]["operation"], "bind_operation_variables")
        self.assertEqual(preview["operations"][4]["bindings"][0]["expression"], "Pitch_thread_external_left_M20x2_1")
        self.assertEqual(
            preview["operations"][4]["bindings"][1]["expression"],
            "Length_thread_external_left_M20x2_1 + 1.05 * Pitch_thread_external_left_M20x2_1",
        )
        self.assertEqual(preview["operations"][5]["operation"], "create_thread_profile")
        self.assertEqual(preview["operations"][6]["operation"], "cut_evolution")
        self.assertEqual(preview["operations"][5]["parameter_prefix"], "EXTERNAL_HELICAL_THREAD")
        self.assertEqual(preview["operations"][5]["dimension_count"], 7)
        self.assertEqual(preview["operations"][5]["constraint_count"], 39)
        self.assertEqual(len(preview["operations"][5]["construction_lines"]), 11)
        self.assertEqual(len(preview["operations"][5]["profile_lines"]), 3)
        self.assertEqual(len(preview["operations"][5]["profile_arcs"]), 1)
        self.assertAlmostEqual(preview["operations"][5]["profile_entry_offset"], 2.1, places=6)
        self.assertAlmostEqual(preview["operations"][5]["profile_surface_offset"], 0.2, places=6)
        self.assertAlmostEqual(preview["operations"][5]["profile_surface_offset_effective"], 0.0, places=6)
        self.assertFalse(preview["operations"][5]["profile_surface_offset_applied"])
        self.assertEqual(preview["operations"][5]["profile_surface_offset_status"], "ignored_in_v1")
        self.assertAlmostEqual(preview["operations"][5]["profile_sketch_origin_shift"], 10.0, places=6)
        self.assertAlmostEqual(preview["operations"][5]["major_radius"], 10.0, places=6)
        self.assertAlmostEqual(preview["operations"][5]["root_radius_level"], 8.7, places=6)
        self.assertAlmostEqual(preview["operations"][5]["root_diameter"], 17.4, places=6)
        self.assertAlmostEqual(preview["operations"][5]["root_radius"], 0.21554445662276763, places=6)
        self.assertAlmostEqual(preview["operations"][5]["profile_points"][0][1], 10.0, places=6)
        self.assertTrue(preview["summary"]["auxiliary_geometry_hidden"])
        self.assertEqual(preview["operations"][-1]["operation"], "hide_auxiliary_geometry")
        self.assertEqual(
            preview["operations"][-1]["objects"],
            [
                "start_center_point",
                "profile_origin_point",
                "profile_lcs",
                "profile_sketch",
                "spiral_axis",
                "spiral_path",
            ],
        )
        self.assertIn(
            {
                "kind": "merge_points",
                "target": "center_ref",
                "index": 1,
                "partner": "root_arc",
                "partner_index": 0,
            },
            preview["params"]["profile_constraints"],
        )
        self.assertIn({"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"}, preview["params"]["profile_constraints"])
        self.assertIn({"kind": "tangent", "target": "root_arc", "partner": "profile_line_1"}, preview["params"]["profile_constraints"])
        self.assertEqual(preview["interface"]["feature_type"], "helical_thread.external_helical_thread")
        self.assertEqual(preview["interface"]["parameter_namespace"], "EXTERNAL_HELICAL_THREAD")
        self.assertEqual(
            preview["interface"]["parameters"]["profile_variables"],
            [
                "Diameter_thread_external_left_M20x2_1",
                "Pitch_thread_external_left_M20x2_1",
                "Length_thread_external_left_M20x2_1",
            ],
        )
        self.assertEqual(
            preview["interface"]["parameters"]["public_profile_variables"],
            [
                "Diameter_thread_external_left_M20x2_1",
                "Pitch_thread_external_left_M20x2_1",
                "Length_thread_external_left_M20x2_1",
            ],
        )
        self.assertEqual(preview["params"]["feature_display_name"], "Thread external left M20x2 1")
        self.assertEqual(preview["params"]["path_display_name"], "Spiral Thread external left M20x2 1")
        self.assertEqual(preview["params"]["profile_display_name"], "Sketch Thread external left M20x2 1")
        self.assertTrue(preview["params"]["auxiliary_geometry_hidden"])
        self.assertIn("EXTERNAL_HELICAL_THREAD_SKP1", preview["interface"]["parameters"]["profile_dimension_variables"])
        self.assertIn("EXTERNAL_HELICAL_THREAD_SKB1", preview["interface"]["parameters"]["profile_dimension_variables"])
        self.assertIn("EXTERNAL_HELICAL_THREAD_SKA1", preview["interface"]["parameters"]["profile_dimension_variables"])
        self.assertIn("EXTERNAL_HELICAL_THREAD_SKW1", preview["interface"]["parameters"]["profile_dimension_variables"])
        self.assertIn("EXTERNAL_HELICAL_THREAD_SKR1", preview["interface"]["parameters"]["profile_dimension_variables"])
        self.assertEqual(preview["params"]["profile_dimensions"][0]["expression"], "Diameter_thread_external_left_M20x2_1 / 2")
        self.assertEqual(preview["params"]["profile_dimensions"][1]["expression"], "0.5 * Pitch_thread_external_left_M20x2_1")
        self.assertEqual(preview["params"]["profile_dimensions"][2]["expression"], "0.108253175473 * Pitch_thread_external_left_M20x2_1")
        self.assertEqual(preview["interface"]["outputs"]["base_face"]["selector"], "step_1_outer_face")
        self.assertEqual(preview["interface"]["outputs"]["start_face"]["selector"], "step_1_start_face")
        self.assertEqual(preview["interface"]["outputs"]["end_face"]["selector"], "step_1_end_face")

    def test_preview_external_helical_thread_accepts_unified_inch_designation(self) -> None:
        preview = preview_part_scenario(
            "external_helical_thread",
            {
                "designation": "1/4-20 UNC",
                "length": 8,
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 10, "diameter": 6.35}]},
            },
        )

        geometry = preview["summary"]["thread_geometry"]
        self.assertEqual(preview["summary"]["thread_profile_family"], "unified_un_v60")
        self.assertEqual(preview["summary"]["thread_series"], "UNC")
        self.assertEqual(preview["summary"]["thread_source_units"], "inch")
        self.assertEqual(preview["summary"]["thread_profile_resolved_from"], "designation")
        self.assertAlmostEqual(preview["summary"]["diameter"], 6.35, places=6)
        self.assertAlmostEqual(preview["summary"]["pitch"], 1.27, places=6)
        self.assertAlmostEqual(geometry["major_diameter_inch"], 0.25, places=6)
        self.assertAlmostEqual(geometry["tpi"], 20.0, places=6)
        self.assertEqual(geometry["root_radius_policy"], "un")
        self.assertEqual(preview["summary"]["source_diameter_validation"]["status"], "match")
        self.assertEqual(preview["params"]["thread_designation"], "1/4-20 UNC")
        self.assertEqual(preview["params"]["designation"], "1/4-20 UNC")

    def test_preview_external_helical_thread_builds_secondary_crest_round_pass(self) -> None:
        crest_round_radius = 0.25
        preview = preview_part_scenario(
            "external_helical_thread",
            {
                "diameter": 20,
                "pitch": 2.0,
                "length": 12,
                "depth": 1.1,
                "clearance": 0.2,
                "crest_round_radius": crest_round_radius,
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 20, "diameter": 20}]},
            },
        )

        crest_round_pass = preview["params"]["crest_round_pass"]
        crest_profile = next(
            operation for operation in preview["operations"] if operation["operation"] == "create_crest_round_profile"
        )
        hide_operation = preview["operations"][-1]
        half_angle = math.radians(preview["summary"]["profile_angle_degrees"] / 2.0)
        expected_tangent_half_width = crest_round_radius * math.cos(half_angle)
        expected_tangent_depth = crest_round_radius * (1.0 - math.sin(half_angle))
        expected_apex_height = crest_round_radius * ((1.0 / math.sin(half_angle)) - 1.0)

        self.assertTrue(preview["summary"]["crest_rounding_enabled"])
        self.assertEqual(preview["summary"]["secondary_cut_count"], 1)
        self.assertAlmostEqual(preview["summary"]["crest_round_phase_shift"], 1.0, places=6)
        self.assertAlmostEqual(preview["summary"]["crest_round_radius"], crest_round_radius, places=6)
        self.assertAlmostEqual(preview["summary"]["crest_round_profile_radial_epsilon"], 0.0001, places=9)
        self.assertEqual(crest_round_pass["role"], "crest_round_pass")
        self.assertEqual(crest_round_pass["phase_shift_mode"], "auto")
        self.assertIn(preview["params"]["public_pitch_variable_name"], crest_round_pass["phase_shift_expression"])
        self.assertAlmostEqual(crest_round_pass["crest_round_radius"], crest_round_radius, places=6)
        self.assertAlmostEqual(crest_round_pass["radial_epsilon"], 0.0001, places=9)
        self.assertAlmostEqual(
            crest_round_pass["profile_origin_offset"],
            preview["params"]["profile_entry_offset"] + crest_round_pass["phase_shift"],
            places=6,
        )
        self.assertAlmostEqual(crest_round_pass["crest_tangent_half_width"], expected_tangent_half_width, places=6)
        self.assertAlmostEqual(crest_round_pass["crest_tangent_depth"], expected_tangent_depth, places=6)
        self.assertAlmostEqual(crest_round_pass["crest_apex_height"], expected_apex_height, places=6)
        self.assertEqual(len(crest_round_pass["dimensions"]), 5)
        self.assertEqual(len(crest_round_pass["constraints"]), 31)
        self.assertIn({"kind": "fixed_point", "target": "axis", "index": 1}, crest_round_pass["constraints"])
        expected_entry_offset_expression = f"1.05 * {preview['params']['public_pitch_variable_name']}"
        self.assertEqual(preview["params"]["profile_entry_offset_expression"], expected_entry_offset_expression)
        self.assertEqual(
            crest_round_pass["profile_origin_offset_expression"],
            f"{expected_entry_offset_expression} + {crest_round_pass['phase_shift_expression']}",
        )
        self.assertTrue(crest_round_pass["verification"]["ok"])
        self.assertEqual(crest_profile["role"], "crest_round_pass")
        self.assertAlmostEqual(crest_profile["profile_origin_offset"], crest_round_pass["profile_origin_offset"], places=6)
        self.assertAlmostEqual(crest_profile["radial_epsilon"], crest_round_pass["radial_epsilon"], places=9)
        self.assertEqual(crest_profile["dimension_count"], 5)
        self.assertEqual(crest_profile["constraint_count"], 31)
        self.assertEqual(len(crest_profile["profile_lines"]), 2)
        self.assertEqual(len(crest_profile["profile_arcs"]), 1)
        self.assertFalse(crest_profile["profile_arcs"][0]["direction"])
        self.assertAlmostEqual(crest_profile["phase_shift"], 1.0, places=6)
        self.assertIn("crest_round_profile_lcs", hide_operation["objects"])
        self.assertIn("crest_round_profile_sketch", hide_operation["objects"])
        self.assertIn("crest_round_spiral_path", hide_operation["objects"])

    def test_preview_external_helical_thread_rejects_conical_crest_round_pass_for_now(self) -> None:
        pipe_geometry = build_pipe_tapered_thread_geometry(nominal_pipe_size="1/4")
        with self.assertRaisesRegex(
            ValueError,
            r"external_helical_thread crest rounding pass currently supports only cylindrical carriers",
        ):
            preview_part_scenario(
                "external_helical_thread",
                {
                    "designation": "1/4 NPT",
                    "length": 12.0,
                    "crest_round_radius": 0.2,
                    "source_scenario": "external_conical_step",
                    "source_params": {
                        "length": 16.0,
                        "start_diameter": pipe_geometry["major_diameter"],
                        "end_diameter": pipe_geometry["major_diameter"] - 1.0,
                    },
                },
            )

    def test_preview_external_helical_thread_accepts_nps_flat_profile(self) -> None:
        pipe_geometry = build_pipe_straight_thread_geometry(nominal_pipe_size="1/4", thread_series="NPS")
        preview = preview_part_scenario(
            "external_helical_thread",
            {
                "designation": "1/4 NPS",
                "length": 12,
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 14, "diameter": pipe_geometry["major_diameter"]}]},
            },
        )

        geometry = preview["summary"]["thread_geometry"]
        self.assertEqual(preview["summary"]["thread_profile_family"], "pipe_nps_v60")
        self.assertEqual(preview["summary"]["thread_series"], "NPS")
        self.assertEqual(preview["summary"]["thread_profile_resolved_from"], "pipe_designation")
        self.assertEqual(preview["summary"]["profile_root_shape"], "flat")
        self.assertAlmostEqual(preview["summary"]["diameter"], 0.540 * 25.4, places=6)
        self.assertAlmostEqual(preview["summary"]["pitch"], 25.4 / 18.0, places=6)
        self.assertAlmostEqual(preview["summary"]["depth"], 0.8 * 25.4 / 18.0, places=6)
        self.assertAlmostEqual(geometry["root_flat_width"], preview["summary"]["root_width"], places=6)
        self.assertEqual(len(preview["operations"][5]["profile_arcs"]), 0)
        self.assertEqual(len(preview["operations"][5]["profile_lines"]), 4)
        self.assertTrue(preview["operations"][5]["verification"]["ok"])
        self.assertIn({"kind": "horizontal", "target": "profile_line_4"}, preview["params"]["profile_constraints"])
        self.assertIn(
            {"kind": "merge_points", "target": "left_root_ref", "index": 1, "partner": "profile_line_4", "partner_index": 0},
            preview["params"]["profile_constraints"],
        )
        self.assertNotIn(
            {"kind": "tangent", "target": "root_arc", "partner": "profile_line_1"},
            preview["params"]["profile_constraints"],
        )

    def test_preview_external_helical_thread_accepts_bsp_g_whitworth_profile(self) -> None:
        pipe_geometry = build_pipe_bsp_parallel_thread_geometry(nominal_pipe_size="1/4")
        preview = preview_part_scenario(
            "external_helical_thread",
            {
                "designation": "G 1/4",
                "length": 12,
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 16, "diameter": pipe_geometry["major_diameter"]}]},
            },
        )

        geometry = preview["summary"]["thread_geometry"]
        profile_operation = next(
            operation for operation in preview["operations"] if operation["operation"] == "create_thread_profile"
        )
        crest_profile = next(
            operation for operation in preview["operations"] if operation["operation"] == "create_crest_round_profile"
        )
        self.assertEqual(preview["summary"]["thread_profile_family"], "pipe_bsp_g_v55")
        self.assertEqual(preview["summary"]["thread_series"], "G")
        self.assertEqual(preview["summary"]["thread_source_units"], "inch")
        self.assertEqual(preview["summary"]["thread_profile_resolved_from"], "pipe_bsp_designation")
        self.assertEqual(preview["summary"]["profile_root_shape"], "round")
        self.assertAlmostEqual(preview["summary"]["profile_angle_degrees"], 55.0, places=6)
        self.assertAlmostEqual(preview["summary"]["diameter"], pipe_geometry["major_diameter"], places=6)
        self.assertAlmostEqual(preview["summary"]["pitch"], pipe_geometry["pitch"], places=6)
        self.assertAlmostEqual(preview["summary"]["depth"], pipe_geometry["external_thread_depth"], places=6)
        self.assertAlmostEqual(preview["summary"]["root_radius"], geometry["root_round_radius"], places=6)
        self.assertTrue(preview["summary"]["crest_rounding_enabled"])
        self.assertEqual(preview["summary"]["secondary_cut_count"], 1)
        self.assertAlmostEqual(preview["summary"]["crest_round_radius"], geometry["crest_round_radius"], places=6)
        self.assertAlmostEqual(preview["summary"]["crest_round_phase_shift"], pipe_geometry["pitch"] / 2.0, places=6)
        self.assertAlmostEqual(
            preview["summary"]["crest_round_profile_origin_offset"],
            preview["params"]["profile_entry_offset"] + (pipe_geometry["pitch"] / 2.0),
            places=6,
        )
        self.assertEqual(len(profile_operation["profile_arcs"]), 1)
        self.assertEqual(len(profile_operation["profile_lines"]), 3)
        self.assertEqual(len(crest_profile["profile_arcs"]), 1)
        self.assertEqual(len(crest_profile["profile_lines"]), 2)
        self.assertFalse(crest_profile["profile_arcs"][0]["direction"])
        self.assertTrue(crest_profile["verification"]["ok"])
        self.assertEqual(preview["params"]["thread_designation"], "G 1/4")

    def test_preview_internal_helical_thread_accepts_bsp_g_whitworth_profile(self) -> None:
        pipe_geometry = build_pipe_bsp_parallel_thread_geometry(nominal_pipe_size="1/4")
        preview = preview_part_scenario(
            "internal_helical_thread",
            {
                "designation": "G 1/4",
                "length": 12,
                "source_scenario": "internal_cylindrical_step",
                "source_params": {
                    "steps": [{"length": 16, "diameter": pipe_geometry["internal_minor_diameter"]}],
                    "source_scenario": "stepped_shaft",
                    "source_params": {"steps": [{"length": 20, "diameter": 24}]},
                },
            },
        )

        geometry = preview["summary"]["thread_geometry"]
        profile_operation = next(
            operation for operation in preview["operations"] if operation["operation"] == "create_thread_profile"
        )
        crest_profile = next(
            operation for operation in preview["operations"] if operation["operation"] == "create_crest_round_profile"
        )
        crest_cut = next(
            operation for operation in preview["operations"] if operation["operation"] == "cut_crest_round_evolution"
        )
        self.assertEqual(preview["summary"]["thread_profile_family"], "pipe_bsp_g_v55")
        self.assertEqual(preview["summary"]["thread_series"], "G")
        self.assertEqual(preview["summary"]["thread_source_units"], "inch")
        self.assertEqual(preview["summary"]["thread_profile_resolved_from"], "pipe_bsp_designation")
        self.assertEqual(preview["summary"]["profile_root_shape"], "round")
        self.assertAlmostEqual(preview["summary"]["profile_angle_degrees"], 55.0, places=6)
        self.assertAlmostEqual(preview["summary"]["thread_reference_diameter"], pipe_geometry["internal_minor_diameter"], places=6)
        self.assertAlmostEqual(preview["summary"]["depth"], pipe_geometry["internal_thread_depth"], places=6)
        self.assertAlmostEqual(preview["summary"]["root_radius"], geometry["root_round_radius"], places=6)
        self.assertTrue(preview["summary"]["crest_rounding_enabled"])
        self.assertEqual(preview["summary"]["secondary_cut_count"], 1)
        self.assertAlmostEqual(preview["summary"]["crest_round_radius"], geometry["crest_round_radius"], places=6)
        self.assertAlmostEqual(preview["summary"]["crest_round_phase_shift"], pipe_geometry["pitch"] / 2.0, places=6)
        half_angle = math.radians(preview["summary"]["profile_angle_degrees"] / 2.0)
        expected_tangent_depth = preview["params"]["radial_cut_depth"] - (
            preview["summary"]["root_radius"] * (1.0 - math.sin(half_angle))
        )
        self.assertAlmostEqual(preview["params"]["profile_tangent_depth"], expected_tangent_depth, places=6)
        self.assertEqual(preview["params"]["root_width_mode"], "from_geometry")
        self.assertEqual(len(profile_operation["profile_arcs"]), 1)
        self.assertEqual(len(profile_operation["profile_lines"]), 3)
        self.assertEqual(len(crest_profile["profile_arcs"]), 1)
        self.assertEqual(len(crest_profile["profile_lines"]), 2)
        self.assertEqual(profile_operation["profile_arcs"][0]["direction"], True)
        self.assertTrue(crest_profile["profile_arcs"][0]["direction"])
        self.assertTrue(crest_profile["verification"]["ok"])
        self.assertTrue(crest_cut["internal"])
        self.assertEqual(preview["params"]["thread_designation"], "G 1/4")

    def test_preview_internal_helical_thread_accepts_npsm_flat_profile(self) -> None:
        pipe_geometry = build_pipe_straight_thread_geometry(nominal_pipe_size="1/4", thread_series="NPSM")
        preview = preview_part_scenario(
            "internal_helical_thread",
            {
                "designation": "1/4-18 NPSM",
                "length": 12,
                "source_scenario": "internal_cylindrical_step",
                "source_params": {
                    "steps": [{"length": 14, "diameter": pipe_geometry["internal_minor_diameter"]}],
                    "source_scenario": "stepped_shaft",
                    "source_params": {"steps": [{"length": 18, "diameter": 24}]},
                },
            },
        )

        geometry = preview["summary"]["thread_geometry"]
        self.assertEqual(preview["summary"]["thread_profile_family"], "pipe_nps_v60")
        self.assertEqual(preview["summary"]["thread_series"], "NPSM")
        self.assertEqual(preview["summary"]["profile_root_shape"], "flat")
        self.assertAlmostEqual(preview["summary"]["thread_reference_diameter"], pipe_geometry["internal_minor_diameter"], places=6)
        self.assertAlmostEqual(geometry["root_flat_width"], preview["summary"]["root_width"], places=6)
        self.assertEqual(len(preview["operations"][5]["profile_arcs"]), 0)
        self.assertEqual(len(preview["operations"][5]["profile_lines"]), 4)
        self.assertTrue(preview["operations"][5]["verification"]["ok"])
        self.assertIn({"kind": "horizontal", "target": "profile_line_4"}, preview["params"]["profile_constraints"])

    def test_preview_external_helical_thread_accepts_npt_conical_flat_profile(self) -> None:
        pipe_geometry = build_pipe_tapered_thread_geometry(nominal_pipe_size="1/4")
        length = 16.0
        preview = preview_part_scenario(
            "external_helical_thread",
            {
                "designation": "1/4 NPT",
                "length": length,
                "source_scenario": "external_conical_step",
                "source_params": {
                    "length": length,
                    "start_diameter": pipe_geometry["major_diameter"],
                    "end_diameter": pipe_geometry["major_diameter"] - length / 16.0,
                },
            },
        )

        geometry = preview["summary"]["thread_geometry"]
        self.assertEqual(preview["summary"]["thread_profile_family"], "pipe_npt_v60")
        self.assertEqual(preview["summary"]["thread_series"], "NPT")
        self.assertEqual(preview["summary"]["thread_profile_resolved_from"], "pipe_tapered_designation")
        self.assertEqual(preview["summary"]["profile_root_shape"], "flat")
        self.assertEqual(preview["summary"]["carrier_shape"], "conical")
        self.assertEqual(preview["summary"]["source_scenario"], "external_conical_step")
        self.assertEqual(preview["params"]["start_selector"], "end_face")
        self.assertEqual(preview["params"]["end_selector"], "start_face")
        self.assertAlmostEqual(preview["summary"]["carrier_diameter"], pipe_geometry["major_diameter"] - length / 16.0)
        self.assertAlmostEqual(preview["summary"]["thread_reference_diameter"], pipe_geometry["major_diameter"] - length / 16.0)
        self.assertAlmostEqual(preview["summary"]["carrier_taper"]["diameter_ratio"], 1.0 / 16.0)
        self.assertAlmostEqual(preview["summary"]["carrier_taper"]["source_start_diameter"], pipe_geometry["major_diameter"])
        self.assertAlmostEqual(preview["summary"]["carrier_taper"]["source_end_diameter"], pipe_geometry["major_diameter"] - length / 16.0)
        self.assertAlmostEqual(preview["summary"]["end_diameter"], pipe_geometry["major_diameter"])
        self.assertAlmostEqual(preview["summary"]["end_thread_reference_diameter"], pipe_geometry["major_diameter"])
        self.assertEqual(len(preview["operations"][5]["profile_arcs"]), 0)
        self.assertEqual(len(preview["operations"][5]["profile_lines"]), 4)
        self.assertTrue(preview["operations"][5]["verification"]["ok"])
        contract = preview["operations"][5]["verification"]["constraint_contract"]
        self.assertTrue(contract["ok"])
        self.assertGreater(preview["summary"]["profile_taper_compensation_radius"], 0.0)
        self.assertIn(" + ", preview["params"]["profile_dimension_expressions"]["sketch_reference_radius"])
        for check in preview["operations"][5]["verification"]["checks"]:
            if check["name"].endswith("_geometrically_collinear_with_left_theory") or check["name"].endswith("_geometrically_collinear_with_right_theory"):
                self.assertTrue(check["ok"])
        self.assertIn(
            {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
            preview["params"]["profile_constraints"],
        )
        self.assertIn(
            {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
            preview["params"]["profile_constraints"],
        )
        self.assertIn(
            {"kind": "collinear", "target": "profile_line_3", "partner": "surface_taper_ref"},
            preview["params"]["profile_constraints"],
        )
        self.assertIn(
            {"kind": "collinear", "target": "profile_line_4", "partner": "root_taper_ref"},
            preview["params"]["profile_constraints"],
        )
        self.assertIn(
            {"kind": "merge_points", "target": "pitch_taper_ref", "index": 0, "partner": "left_theory", "partner_index": 1},
            preview["params"]["profile_constraints"],
        )
        self.assertEqual(preview["params"]["sketch"]["parameterization_order"], "anchored_dimensions_then_constraints")
        self.assertTrue(preview["params"]["sketch"]["readback_geometry"])
        self.assertNotIn({"kind": "horizontal", "target": "profile_line_4"}, preview["params"]["profile_constraints"])
        profile_line_3 = next(line for line in preview["operations"][5]["profile_lines"] if line["target"] == "profile_line_3")
        self.assertNotAlmostEqual(profile_line_3["start"][1], profile_line_3["end"][1], places=9)
        right_outer_ref = next(line for line in preview["operations"][5]["construction_lines"] if line["target"] == "right_outer_ref")
        right_outer_projection = next(line for line in preview["operations"][5]["construction_lines"] if line["target"] == "right_outer_projection_ref")
        self.assertAlmostEqual(right_outer_ref["start"][1], right_outer_ref["end"][1], places=9)
        self.assertAlmostEqual(right_outer_projection["start"][0], right_outer_projection["end"][0], places=9)
        self.assertIn({"kind": "horizontal", "target": "right_outer_ref"}, preview["params"]["profile_constraints"])
        self.assertIn({"kind": "vertical", "target": "right_outer_projection_ref"}, preview["params"]["profile_constraints"])
        self.assertEqual(geometry["carrier_shape"], "conical")

    def test_preview_external_helical_thread_anchors_partial_conical_span_at_small_end(self) -> None:
        pipe_geometry = build_pipe_tapered_thread_geometry(nominal_pipe_size="1/4")
        source_length = 24.0
        thread_length = 12.0
        source_small_diameter = pipe_geometry["major_diameter"] - source_length / 16.0
        preview = preview_part_scenario(
            "external_helical_thread",
            {
                "designation": "1/4 NPT",
                "length": thread_length,
                "source_scenario": "external_conical_step",
                "source_params": {
                    "length": source_length,
                    "start_diameter": pipe_geometry["major_diameter"],
                    "end_diameter": source_small_diameter,
                },
            },
        )

        self.assertEqual(preview["params"]["start_selector"], "end_face")
        self.assertEqual(preview["params"]["end_selector"], "start_face")
        self.assertAlmostEqual(preview["summary"]["carrier_diameter"], source_small_diameter, places=6)
        self.assertAlmostEqual(preview["summary"]["thread_reference_diameter"], source_small_diameter, places=6)
        self.assertAlmostEqual(preview["summary"]["end_diameter"], source_small_diameter + thread_length / 16.0, places=6)
        self.assertAlmostEqual(
            preview["summary"]["carrier_taper"]["thread_start_axis"],
            source_length,
            places=6,
        )
        self.assertAlmostEqual(
            preview["summary"]["carrier_taper"]["thread_end_axis"],
            source_length - thread_length,
            places=6,
        )

    def test_preview_external_helical_thread_rejects_reversed_conical_span(self) -> None:
        pipe_geometry = build_pipe_tapered_thread_geometry(nominal_pipe_size="1/4")
        length = 16.0
        with self.assertRaisesRegex(
            ValueError,
            r"external_helical_thread external conical thread must run from end_face "
            r"\(small/free entry end\) to start_face \(large/seat end\)",
        ):
            preview_part_scenario(
                "external_helical_thread",
                {
                    "designation": "1/4 NPT",
                    "length": length,
                    "start_selector": "seat_face",
                    "end_selector": "free_end_face",
                    "source_scenario": "external_conical_step",
                    "source_params": {
                        "length": length,
                        "start_diameter": pipe_geometry["major_diameter"],
                        "end_diameter": pipe_geometry["major_diameter"] - length / 16.0,
                    },
                },
            )

    def test_preview_internal_helical_thread_accepts_npt_conical_flat_profile(self) -> None:
        pipe_geometry = build_pipe_tapered_thread_geometry(nominal_pipe_size="1/2")
        length = 16.0
        start_diameter = pipe_geometry["internal_minor_diameter"]
        preview = preview_part_scenario(
            "internal_helical_thread",
            {
                "designation": "1/2 NPT",
                "length": length,
                "source_scenario": "internal_conical_step",
                "source_params": {
                    "length": length,
                    "start_diameter": start_diameter,
                    "end_diameter": start_diameter - length / 16.0,
                    "source_scenario": "stepped_shaft",
                    "source_params": {"steps": [{"length": 20, "diameter": pipe_geometry["major_diameter"] + 8.0}]},
                },
            },
        )

        self.assertEqual(preview["summary"]["thread_profile_family"], "pipe_npt_v60")
        self.assertEqual(preview["summary"]["source_scenario"], "internal_conical_step")
        self.assertEqual(preview["summary"]["carrier_shape"], "conical")
        self.assertAlmostEqual(preview["summary"]["thread_reference_diameter"], start_diameter, places=6)
        self.assertAlmostEqual(preview["summary"]["end_thread_reference_diameter"], start_diameter - length / 16.0, places=6)
        self.assertEqual(len(preview["operations"][5]["profile_arcs"]), 0)
        self.assertEqual(len(preview["operations"][5]["profile_lines"]), 4)
        self.assertTrue(preview["operations"][5]["verification"]["ok"])
        contract = preview["operations"][5]["verification"]["constraint_contract"]
        self.assertTrue(contract["ok"])
        self.assertLess(preview["summary"]["profile_taper_compensation_radius"], 0.0)
        self.assertIn(" - ", preview["params"]["profile_dimension_expressions"]["sketch_reference_radius"])
        for check in preview["operations"][5]["verification"]["checks"]:
            if check["name"].endswith("_geometrically_collinear_with_left_theory") or check["name"].endswith("_geometrically_collinear_with_right_theory"):
                self.assertTrue(check["ok"])
        self.assertIn(
            {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
            preview["params"]["profile_constraints"],
        )
        self.assertIn(
            {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
            preview["params"]["profile_constraints"],
        )
        self.assertIn(
            {"kind": "collinear", "target": "profile_line_4", "partner": "root_taper_ref"},
            preview["params"]["profile_constraints"],
        )
        self.assertIn(
            {"kind": "merge_points", "target": "pitch_taper_ref", "index": 1, "partner": "right_theory", "partner_index": 1},
            preview["params"]["profile_constraints"],
        )
        self.assertEqual(preview["params"]["sketch"]["parameterization_order"], "anchored_dimensions_then_constraints")
        self.assertTrue(preview["params"]["sketch"]["readback_geometry"])
        right_root_ref = next(line for line in preview["operations"][5]["construction_lines"] if line["target"] == "right_root_ref")
        right_root_projection = next(line for line in preview["operations"][5]["construction_lines"] if line["target"] == "right_root_projection_ref")
        self.assertAlmostEqual(right_root_ref["start"][1], right_root_ref["end"][1], places=9)
        self.assertAlmostEqual(right_root_projection["start"][0], right_root_projection["end"][0], places=9)

    def test_preview_internal_helical_thread_builds_cut_contract(self) -> None:
        geometry = build_metric_thread_geometry(16.0, 2.0)
        preview = preview_part_scenario(
            "internal_helical_thread",
            {
                "diameter": 16,
                "pitch": 2.0,
                "length": 10,
                "depth": 1.0,
                "clearance": 0.15,
                "direction": "right",
                "source_scenario": "internal_cylindrical_step",
                "source_params": {
                    "steps": [{"length": 18, "diameter": geometry["internal_minor_diameter"]}],
                    "source_scenario": "stepped_shaft",
                    "source_params": {"steps": [{"length": 28, "diameter": 32}]},
                },
            },
        )

        self.assertEqual(preview["scenario"], "internal_helical_thread")
        self.assertEqual(preview["summary"]["source_scenario"], "internal_cylindrical_step")
        self.assertEqual(preview["summary"]["source_selector"], "inner_face")
        self.assertAlmostEqual(preview["summary"]["carrier_diameter"], geometry["internal_minor_diameter"], places=6)
        self.assertEqual(preview["summary"]["diameter"], 16.0)
        self.assertEqual(preview["summary"]["pitch"], 2.0)
        self.assertEqual(preview["summary"]["length"], 10.0)
        self.assertEqual(preview["summary"]["depth"], 1.0)
        self.assertEqual(preview["summary"]["clearance"], 0.15)
        self.assertAlmostEqual(preview["summary"]["fundamental_triangle_height"], 2.0 / (2.0 * math.tan(math.radians(30.0))), places=6)
        self.assertAlmostEqual(preview["summary"]["crest_drop"], preview["summary"]["fundamental_triangle_height"] - 1.15, places=6)
        self.assertAlmostEqual(preview["summary"]["root_width"], 0.25, places=6)
        self.assertAlmostEqual(preview["summary"]["root_radius"], 0.14433756729740643, places=6)
        self.assertAlmostEqual(preview["summary"]["profile_outer_half_width"], 0.6639528095680696, places=6)
        self.assertAlmostEqual(preview["summary"]["profile_entry_offset"], 2.1, places=6)
        self.assertAlmostEqual(preview["summary"]["profile_surface_offset"], 0.15, places=6)
        self.assertAlmostEqual(preview["summary"]["profile_surface_offset_effective"], 0.0, places=6)
        self.assertFalse(preview["summary"]["profile_surface_offset_applied"])
        self.assertEqual(preview["summary"]["profile_surface_offset_status"], "ignored_in_v1")
        self.assertAlmostEqual(
            preview["summary"]["profile_sketch_origin_shift"],
            -geometry["internal_minor_radius"],
            places=6,
        )
        self.assertAlmostEqual(preview["summary"]["thread_reference_diameter"], geometry["internal_minor_diameter"], places=6)
        self.assertEqual(preview["summary"]["source_diameter_validation"]["status"], "match")
        self.assertEqual(preview["summary"]["direction"], "right")
        self.assertTrue(preview["summary"]["internal"])
        self.assertEqual(preview["summary"]["parameter_prefix"], "INTERNAL_HELICAL_THREAD")
        self.assertAlmostEqual(preview["summary"]["spiral_length"], 12.1, places=6)
        self.assertEqual(preview["summary"]["planned_variable_count"], 3)
        self.assertEqual(preview["summary"]["planned_dimension_count"], 6)
        self.assertEqual(preview["summary"]["planned_constraint_count"], 41)
        self.assertEqual(preview["operations"][1]["operation"], "add_variables")
        self.assertEqual(preview["operations"][1]["variable_count"], 3)
        self.assertEqual(preview["operations"][1]["variables"][0]["name"], "Diameter_thread_internal_right_M16x2_1")
        self.assertEqual(preview["operations"][1]["variables"][1]["name"], "Pitch_thread_internal_right_M16x2_1")
        self.assertEqual(preview["operations"][1]["variables"][2]["name"], "Length_thread_internal_right_M16x2_1")
        self.assertTrue(preview["operations"][1]["variables"][0]["external"])
        self.assertTrue(preview["operations"][1]["variables"][1]["external"])
        self.assertTrue(preview["operations"][1]["variables"][2]["external"])
        self.assertAlmostEqual(preview["operations"][3]["spiral_length"], 12.1, places=6)
        self.assertEqual(preview["operations"][4]["operation"], "bind_operation_variables")
        self.assertEqual(preview["operations"][4]["bindings"][0]["expression"], "Pitch_thread_internal_right_M16x2_1")
        self.assertEqual(
            preview["operations"][4]["bindings"][1]["expression"],
            "Length_thread_internal_right_M16x2_1 + 1.05 * Pitch_thread_internal_right_M16x2_1",
        )
        self.assertAlmostEqual(preview["operations"][5]["profile_entry_offset"], 2.1, places=6)
        self.assertAlmostEqual(preview["operations"][5]["profile_surface_offset"], 0.15, places=6)
        self.assertAlmostEqual(preview["operations"][5]["profile_surface_offset_effective"], 0.0, places=6)
        self.assertFalse(preview["operations"][5]["profile_surface_offset_applied"])
        self.assertEqual(preview["operations"][5]["profile_surface_offset_status"], "ignored_in_v1")
        self.assertAlmostEqual(
            preview["operations"][5]["profile_sketch_origin_shift"],
            -geometry["internal_minor_radius"],
            places=6,
        )
        self.assertEqual(preview["operations"][5]["dimension_count"], 6)
        self.assertEqual(preview["operations"][5]["constraint_count"], 41)
        self.assertTrue(preview["summary"]["auxiliary_geometry_hidden"])
        self.assertEqual(preview["operations"][-1]["operation"], "hide_auxiliary_geometry")
        self.assertEqual(
            preview["operations"][-1]["objects"],
            [
                "start_center_point",
                "profile_origin_point",
                "profile_lcs",
                "profile_sketch",
                "spiral_axis",
                "spiral_path",
            ],
        )
        self.assertAlmostEqual(
            preview["operations"][5]["profile_points"][0][1],
            -geometry["internal_minor_radius"],
            places=6,
        )
        self.assertLess(preview["operations"][5]["profile_points"][1][1], preview["operations"][5]["profile_points"][0][1])
        self.assertLess(preview["params"]["profile_axis_end"][1], preview["params"]["profile_axis_start"][1])
        self.assertIn(
            {"kind": "collinear", "target": "profile_line_1", "partner": "left_theory"},
            preview["params"]["profile_constraints"],
        )
        self.assertIn(
            {"kind": "collinear", "target": "profile_line_2", "partner": "right_theory"},
            preview["params"]["profile_constraints"],
        )
        self.assertEqual(preview["interface"]["feature_type"], "helical_thread.internal_helical_thread")
        self.assertEqual(preview["interface"]["parameter_namespace"], "INTERNAL_HELICAL_THREAD")
        self.assertEqual(
            preview["interface"]["parameters"]["profile_variables"],
            [
                "Diameter_thread_internal_right_M16x2_1",
                "Pitch_thread_internal_right_M16x2_1",
                "Length_thread_internal_right_M16x2_1",
            ],
        )
        self.assertEqual(
            preview["interface"]["parameters"]["public_profile_variables"],
            [
                "Diameter_thread_internal_right_M16x2_1",
                "Pitch_thread_internal_right_M16x2_1",
                "Length_thread_internal_right_M16x2_1",
            ],
        )
        self.assertEqual(preview["params"]["feature_display_name"], "Thread internal right M16x2 1")
        self.assertEqual(preview["params"]["path_display_name"], "Spiral Thread internal right M16x2 1")
        self.assertEqual(preview["params"]["profile_display_name"], "Sketch Thread internal right M16x2 1")
        self.assertTrue(preview["params"]["auxiliary_geometry_hidden"])
        self.assertIn("INTERNAL_HELICAL_THREAD_SKP1", preview["interface"]["parameters"]["profile_dimension_variables"])
        self.assertIn("INTERNAL_HELICAL_THREAD_SKB1", preview["interface"]["parameters"]["profile_dimension_variables"])
        self.assertIn("INTERNAL_HELICAL_THREAD_SKD1", preview["interface"]["parameters"]["profile_dimension_variables"])
        self.assertIn("INTERNAL_HELICAL_THREAD_SKT1", preview["interface"]["parameters"]["profile_dimension_variables"])
        self.assertEqual(preview["params"]["profile_dimensions"][0]["expression"], "Diameter_thread_internal_right_M16x2_1 / 2")
        self.assertEqual(preview["params"]["profile_dimensions"][1]["expression"], "0.5 * Pitch_thread_internal_right_M16x2_1")
        self.assertEqual(preview["params"]["profile_dimensions"][2]["expression"], "0.324759526419 * Pitch_thread_internal_right_M16x2_1 - 0.15")
        self.assertEqual(preview["interface"]["outputs"]["base_face"]["selector"], "inner_face")
        self.assertEqual(preview["interface"]["outputs"]["start_face"]["selector"], "step_1_start_face")
        self.assertEqual(preview["interface"]["outputs"]["end_face"]["selector"], "step_1_end_face")
        self.assertAlmostEqual(preview["params"]["carrier_diameter"], geometry["internal_minor_diameter"], places=6)

    def test_preview_internal_helical_thread_reports_source_diameter_mismatch(self) -> None:
        preview = preview_part_scenario(
            "internal_helical_thread",
            {
                "diameter": 16,
                "pitch": 1.0,
                "length": 8,
                "source_scenario": "internal_cylindrical_step",
                "source_params": {
                    "steps": [{"length": 12, "diameter": 15.02}],
                    "source_scenario": "stepped_shaft",
                    "source_params": {"steps": [{"length": 20, "diameter": 30}]},
                },
            },
        )

        validation = preview["summary"]["source_diameter_validation"]
        self.assertEqual(validation["status"], "mismatch")
        self.assertAlmostEqual(validation["recommended_diameter"], build_metric_thread_geometry(16.0, 1.0)["internal_minor_diameter"], places=6)
        self.assertGreater(validation["delta"], 0.0)

    def test_preview_face_ring_groove_builds_cut_profile(self) -> None:
        preview = preview_part_scenario(
            "face_ring_groove",
            {
                "inner_diameter": 18,
                "outer_diameter": 30,
                "depth": 8,
                "inner_wall_angle_degrees": 5,
                "outer_wall_angle_degrees": 12,
                "axial_direction": "backward",
                "parameter_prefix": "groove01",
                "source_scenario": "stepped_shaft",
                "source_params": {
                    "steps": [{"length": 48, "diameter": 36}],
                },
            },
        )

        self.assertEqual(preview["scenario"], "face_ring_groove")
        self.assertEqual(preview["summary"]["source_scenario"], "stepped_shaft")
        self.assertEqual(preview["summary"]["axial_direction"], "backward")
        self.assertEqual(preview["summary"]["inner_diameter"], 18.0)
        self.assertEqual(preview["summary"]["outer_diameter"], 30.0)
        self.assertEqual(preview["summary"]["depth"], 8.0)
        self.assertEqual(preview["operations"][1]["operation"], "create_source_body")
        self.assertEqual(preview["operations"][-1]["operation"], "cut_rotation")
        self.assertEqual(preview["interface"]["feature_type"], "revolved_cut.face_ring_groove")
        self.assertEqual(preview["interface"]["outputs"]["bottom_face"]["selector"], "bottom_face")
        self.assertEqual(preview["interface"]["outputs"]["inner_face"]["selector"], "inner_wall_face")
        self.assertEqual(preview["interface"]["outputs"]["outer_face"]["selector"], "outer_wall_face")
        self.assertEqual(preview["interface"]["parameters"]["driving_diameters"], ["GROOVE01_ID1", "GROOVE01_OD1", "GROOVE01_BID1", "GROOVE01_BOD1"])
        self.assertEqual(preview["interface"]["parameters"]["driving_lengths"], ["GROOVE01_DEP1"])
        self.assertEqual(preview["operations"][5]["construction_lines"], [])
        self.assertEqual(preview["operations"][6]["constraints"][2]["target"], "profile_line_1")
        self.assertEqual(preview["operations"][6]["constraints"][3]["target"], "axis")
        self.assertEqual(preview["operations"][6]["constraints"][4]["target"], "profile_line_3")
        self.assertEqual(preview["operations"][7]["dimensions"][0]["expression"], "GROOVE01_DEP1")
        self.assertEqual(preview["operations"][7]["dimensions"][1]["expression"], "GROOVE01_OD1 / 2")
        self.assertEqual(preview["operations"][7]["dimensions"][2]["expression"], "GROOVE01_ID1 / 2")
        self.assertEqual(preview["operations"][7]["dimensions"][3]["expression"], "GROOVE01_BID1 / 2")
        self.assertEqual(preview["operations"][7]["dimensions"][4]["expression"], "GROOVE01_BOD1 / 2")
        profile = preview["operations"][5]["profile_points"]
        self.assertEqual(profile[0], [0.0, 15.0])
        self.assertEqual(profile[1], [0.0, 9.0])
        self.assertEqual(profile[2][0], -8.0)
        self.assertEqual(profile[-1], [0.0, 15.0])

    def test_preview_face_ring_groove_rejects_invalid_bottom_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, r"bottom_outer_diameter must stay greater than bottom_inner_diameter"):
            preview_part_scenario(
                "face_ring_groove",
                {
                    "inner_diameter": 18,
                    "outer_diameter": 20,
                    "depth": 8,
                    "inner_wall_angle_degrees": 30,
                    "outer_wall_angle_degrees": 30,
                },
            )

    def test_preview_point_builds_reference_contract(self) -> None:
        preview = preview_part_scenario(
            "point",
            {
                "name": "Tail point",
                "point_name": "PT_TAIL",
                "origin": [10, 20, 30],
                "parameter_prefix": "pt_01",
            },
        )

        self.assertEqual(preview["scenario"], "point")
        self.assertEqual(preview["summary"]["mode"], "global")
        self.assertEqual(preview["summary"]["point_name"], "PT_TAIL")
        self.assertEqual(preview["summary"]["origin"], [10.0, 20.0, 30.0])
        self.assertEqual(preview["summary"]["parameter_prefix"], "PT_01")
        self.assertEqual(preview["interface"]["feature_type"], "reference.point3d")
        self.assertEqual(preview["interface"]["anchors"]["point"], [10.0, 20.0, 30.0])
        self.assertEqual(preview["interface"]["outputs"]["point"]["type"], "point")
        self.assertEqual(preview["interface"]["outputs"]["point"]["origin"], [10.0, 20.0, 30.0])
        self.assertEqual(preview["interface"]["reference"]["name"], "PT_TAIL")
        self.assertEqual(preview["operations"][1]["operation"], "create_point")

    def test_preview_point_supports_offset_from_point(self) -> None:
        preview = preview_part_scenario(
            "point",
            {
                "mode": "offset_from_point",
                "point_name": "PT_ECC",
                "reference": {"name": "PT_BASE", "origin": [40, 0, 0]},
                "offset": {"dx": 0, "dy": 8, "dz": 0},
            },
        )

        self.assertEqual(preview["summary"]["mode"], "offset_from_point")
        self.assertEqual(preview["summary"]["reference_name"], "PT_BASE")
        self.assertEqual(preview["summary"]["reference_origin"], [40.0, 0.0, 0.0])
        self.assertEqual(preview["summary"]["offset"], [0.0, 8.0, 0.0])
        self.assertEqual(preview["summary"]["origin"], [40.0, 8.0, 0.0])
        self.assertEqual(preview["operations"][1]["role"], "reference_point")
        self.assertEqual(preview["operations"][2]["mode"], "offset_from_point")

    def test_preview_point_supports_center_of_object_mode(self) -> None:
        preview = preview_part_scenario(
            "point",
            {
                "mode": "center_of_object",
                "point_name": "PT_TAIL_CENTER",
                "reference": {
                    "selector": "far_end_face",
                    "source_scenario": "stepped_shaft",
                    "source_params": {
                        "steps": [
                            {"length": 20, "diameter": 10},
                            {"length": 30, "diameter": 16},
                            {"length": 10, "diameter": 12},
                        ]
                    },
                },
            },
        )

        self.assertEqual(preview["summary"]["mode"], "center_of_object")
        self.assertEqual(preview["summary"]["creation_status"], "available")
        self.assertEqual(preview["summary"]["origin"], [60.0, 0.0, 0.0])
        self.assertEqual(preview["summary"]["reference_selector"], "far_end_face")
        self.assertEqual(preview["summary"]["source_scenario"], "stepped_shaft")
        self.assertEqual(preview["operations"][1]["operation"], "create_source_body")
        self.assertEqual(preview["operations"][2]["operation"], "resolve_reference_object")
        self.assertEqual(preview["operations"][3]["mode"], "center_of_object")
        self.assertTrue(preview["interface"]["reference"]["live_supported"])

    def test_preview_point_supports_start_face_selector(self) -> None:
        preview = preview_part_scenario(
            "point",
            {
                "mode": "center_of_object",
                "point_name": "PT_HEAD_CENTER",
                "reference": {
                    "selector": "start_face",
                    "source_scenario": "stepped_shaft",
                    "source_params": {
                        "steps": [
                            {"length": 20, "diameter": 10},
                            {"length": 30, "diameter": 16},
                        ]
                    },
                },
            },
        )

        self.assertEqual(preview["summary"]["origin"], [0.0, 0.0, 0.0])
        self.assertEqual(preview["summary"]["reference_selector"], "start_face")
        self.assertEqual(preview["params"]["reference"]["selector"], "start_face")

    def test_preview_point_supports_shoulder_face_selector(self) -> None:
        preview = preview_part_scenario(
            "point",
            {
                "mode": "center_of_object",
                "point_name": "PT_SHOULDER",
                "reference": {
                    "selector": "shoulder_1_face",
                    "source_scenario": "stepped_shaft",
                    "source_params": {
                        "steps": [
                            {"length": 20, "diameter": 10},
                            {"length": 30, "diameter": 16},
                            {"length": 10, "diameter": 12},
                        ]
                    },
                },
            },
        )

        self.assertEqual(preview["summary"]["origin"], [20.0, 0.0, 0.0])
        self.assertEqual(preview["summary"]["reference_selector"], "shoulder_1_face")
        self.assertEqual(preview["params"]["reference"]["selector"], "shoulder_1_face")

    def test_preview_point_supports_step_face_selector(self) -> None:
        preview = preview_part_scenario(
            "point",
            {
                "mode": "center_of_object",
                "point_name": "PT_STEP_END",
                "reference": {
                    "selector": "step_2_end_face",
                    "source_scenario": "stepped_shaft",
                    "source_params": {
                        "steps": [
                            {"length": 20, "diameter": 10},
                            {"length": 30, "diameter": 16},
                            {"length": 10, "diameter": 12},
                        ]
                    },
                },
            },
        )

        self.assertEqual(preview["summary"]["origin"], [50.0, 0.0, 0.0])
        self.assertEqual(preview["summary"]["reference_selector"], "step_2_end_face")
        self.assertEqual(preview["params"]["reference"]["selector"], "step_2_end_face")

    def test_preview_point_supports_step_outer_face_selector(self) -> None:
        preview = preview_part_scenario(
            "point",
            {
                "mode": "center_of_object",
                "point_name": "PT_STEP_OUTER",
                "reference": {
                    "selector": "step_2_outer_face",
                    "source_scenario": "stepped_shaft",
                    "source_params": {
                        "steps": [
                            {"length": 20, "diameter": 10},
                            {"length": 30, "diameter": 16},
                            {"length": 10, "diameter": 12},
                        ]
                    },
                },
            },
        )

        self.assertEqual(preview["summary"]["origin"], [35.0, 0.0, 0.0])
        self.assertEqual(preview["summary"]["reference_selector"], "step_2_outer_face")
        self.assertEqual(preview["params"]["reference"]["selector"], "step_2_outer_face")

    def test_preview_point_supports_external_conical_step_selector(self) -> None:
        preview = preview_part_scenario(
            "point",
            {
                "mode": "center_of_object",
                "point_name": "PT_CONE_OUTER",
                "reference": {
                    "selector": "outer_face",
                    "source_scenario": "external_conical_step",
                    "source_params": {
                        "length": 24,
                        "start_diameter": 12,
                        "end_diameter": 20,
                    },
                },
            },
        )

        self.assertEqual(preview["summary"]["source_scenario"], "external_conical_step")
        self.assertEqual(preview["summary"]["reference_selector"], "outer_face")
        self.assertEqual(preview["summary"]["origin"], [12.0, 0.0, 0.0])

    def test_preview_point_supports_internal_cylindrical_step_inner_selector(self) -> None:
        preview = preview_part_scenario(
            "point",
            {
                "mode": "center_of_object",
                "point_name": "PT_BORE_STEP2",
                "reference": {
                    "selector": "step_2_inner_face",
                    "source_scenario": "internal_cylindrical_step",
                    "source_params": {
                        "steps": [
                            {"length": 8, "diameter": 10},
                            {"length": 12, "diameter": 14},
                        ],
                        "source_scenario": "stepped_shaft",
                        "source_params": {
                            "steps": [{"length": 32, "diameter": 24}],
                        },
                    },
                },
            },
        )

        self.assertEqual(preview["summary"]["source_scenario"], "internal_cylindrical_step")
        self.assertEqual(preview["summary"]["reference_selector"], "step_2_inner_face")
        self.assertEqual(preview["summary"]["origin"], [14.0, 0.0, 0.0])

    def test_preview_point_rejects_unsupported_center_selector(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"center_of_object\.reference\.selector uses unsupported stepped_shaft selector middle_face; available selectors: .*far_end_face.*start_face",
        ):
            preview_part_scenario(
                "point",
                {
                    "mode": "center_of_object",
                    "reference": {
                        "selector": "middle_face",
                        "source_params": {"steps": [{"length": 10, "diameter": 8}]},
                    },
                },
            )

    def test_preview_point_rejects_out_of_range_center_selector(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"Stepped_shaft selector step_3_end_face is out of range for the source body; available selectors: .*step_2_end_face",
        ):
            preview_part_scenario(
                "point",
                {
                    "mode": "center_of_object",
                    "reference": {
                        "selector": "step_3_end_face",
                        "source_params": {
                            "steps": [
                                {"length": 20, "diameter": 30},
                                {"length": 10, "diameter": 20},
                            ]
                        },
                    },
                },
            )

    def test_preview_lcs_supports_object_selector_mode(self) -> None:
        preview = preview_part_scenario(
            "lcs",
            {
                "mode": "object",
                "lcs_name": "LCS_TAIL",
                "reference": {
                    "selector": "far_end_face",
                    "source_scenario": "stepped_shaft",
                    "source_params": {
                        "steps": [
                            {"length": 20, "diameter": 10},
                            {"length": 30, "diameter": 16},
                        ]
                    },
                },
            },
        )

        self.assertEqual(preview["summary"]["mode"], "object")
        self.assertEqual(preview["summary"]["reference"]["selector"], "far_end_face")
        self.assertEqual(preview["summary"]["origin"], [50.0, 0.0, 0.0])
        self.assertEqual(preview["operations"][1]["operation"], "create_source_body")
        self.assertEqual(preview["operations"][2]["operation"], "resolve_reference_object")
        self.assertEqual(preview["operations"][3]["operation"], "create_lcs")
        self.assertEqual(preview["operations"][3]["live_status"], "planned")

    def test_preview_lcs_supports_internal_conical_end_face_selector_mode(self) -> None:
        preview = preview_part_scenario(
            "lcs",
            {
                "mode": "object",
                "lcs_name": "LCS_IBORE_END",
                "reference": {
                    "selector": "end_face",
                    "source_scenario": "internal_conical_step",
                    "source_params": {
                        "length": 16,
                        "start_diameter": 8,
                        "end_diameter": 14,
                        "source_scenario": "stepped_shaft",
                        "source_params": {
                            "steps": [{"length": 40, "diameter": 26}],
                        },
                    },
                },
            },
        )

        self.assertEqual(preview["summary"]["mode"], "object")
        self.assertEqual(preview["summary"]["reference"]["selector"], "end_face")
        self.assertEqual(preview["summary"]["reference"]["source_scenario"], "internal_conical_step")
        self.assertEqual(preview["summary"]["origin"], [16.0, 0.0, 0.0])
        self.assertEqual(preview["operations"][3]["live_status"], "planned")

    def test_preview_lcs_supports_step_outer_face_selector_mode(self) -> None:
        preview = preview_part_scenario(
            "lcs",
            {
                "mode": "object",
                "lcs_name": "LCS_STEP2_OUTER",
                "reference": {
                    "selector": "step_2_outer_face",
                    "source_scenario": "stepped_shaft",
                    "source_params": {
                        "steps": [
                            {"length": 20, "diameter": 10},
                            {"length": 30, "diameter": 16},
                            {"length": 10, "diameter": 12},
                        ]
                    },
                },
            },
        )

        self.assertEqual(preview["summary"]["reference"]["selector"], "step_2_outer_face")
        self.assertEqual(preview["summary"]["origin"], [35.0, 0.0, 0.0])
        self.assertEqual(preview["summary"]["creation_status"], "preview_only")
        self.assertEqual(preview["operations"][3]["live_status"], "not_supported_yet")

    def test_preview_lcs_supports_global_mode(self) -> None:
        preview = preview_part_scenario(
            "lcs",
            {
                "lcs_name": "LCS_ECC_01",
                "origin": [40, 12, 0],
                "rotation": {"rx": 10, "ry": 20, "rz": 30},
            },
        )

        self.assertEqual(preview["scenario"], "lcs")
        self.assertEqual(preview["summary"]["mode"], "global")
        self.assertEqual(preview["summary"]["lcs_name"], "LCS_ECC_01")
        self.assertEqual(preview["summary"]["origin"], [40.0, 12.0, 0.0])
        self.assertEqual(preview["summary"]["rotation"], {"rx": 10.0, "ry": 20.0, "rz": 30.0})
        self.assertEqual(preview["interface"]["feature_type"], "reference.lcs")
        self.assertEqual(preview["interface"]["outputs"]["lcs"]["type"], "lcs")
        self.assertEqual(preview["interface"]["outputs"]["lcs"]["origin"], [40.0, 12.0, 0.0])
        self.assertEqual(preview["interface"]["placement_ref"], "LCS_ECC_01")
        self.assertEqual(preview["operations"][-1]["operation"], "create_lcs")
        self.assertEqual(preview["operations"][-1]["mode"], "global")

    def test_preview_lcs_supports_point_mode(self) -> None:
        preview = preview_part_scenario(
            "lcs",
            {
                "mode": "point",
                "lcs_name": "LCS_BY_POINT",
                "reference": {
                    "name": "PT_BASE",
                    "origin": [5, 6, 7],
                },
                "rotation": {"rz": 45},
            },
        )

        self.assertEqual(preview["summary"]["mode"], "point")
        self.assertEqual(preview["summary"]["reference_name"], "PT_BASE")
        self.assertEqual(preview["summary"]["reference_origin"], [5.0, 6.0, 7.0])
        self.assertEqual(preview["summary"]["origin"], [5.0, 6.0, 7.0])
        self.assertEqual(preview["operations"][1]["operation"], "create_point")
        self.assertEqual(preview["operations"][2]["operation"], "create_lcs")
        self.assertEqual(preview["operations"][2]["mode"], "point")

    def test_preview_lcs_object_mode_supports_system_objects(self) -> None:
        preview = preview_part_scenario(
            "lcs",
            {
                "mode": "object",
                "reference": {"system_object": "xoy_plane"},
            },
        )

        self.assertEqual(preview["summary"]["mode"], "object")
        self.assertEqual(preview["summary"]["creation_status"], "available")
        self.assertEqual(preview["operations"][-1]["live_status"], "planned")
        self.assertEqual(preview["params"]["reference"]["system_object"], "xoy_plane")

    def test_preview_lcs_object_mode_external_reference_is_preview_only(self) -> None:
        preview = preview_part_scenario(
            "lcs",
            {
                "mode": "object",
                "reference": {"feature": "REV01", "anchor": "end_face"},
                "only_outer_contour": True,
            },
        )

        self.assertEqual(preview["summary"]["mode"], "object")
        self.assertEqual(preview["summary"]["creation_status"], "preview_only")
        self.assertTrue(preview["summary"]["only_outer_contour"])
        self.assertEqual(preview["operations"][-1]["live_status"], "not_supported_yet")

    def test_preview_workflow_resolves_operation_bindings(self) -> None:
        preview = preview_part_scenario(
            "workflow",
            {
                "name": "Eccentric chain",
                "operations": [
                    {
                        "id": "rev01",
                        "scenario": "stepped_shaft",
                        "params": {
                            "name": "Primary shaft",
                            "parameter_prefix": "REV01",
                            "steps": [
                                {"length": 18, "diameter": 30},
                                {"length": 24, "diameter": 22},
                            ],
                        },
                    },
                    {
                        "id": "pt_center",
                        "scenario": "point",
                        "params": {
                            "mode": "center_of_object",
                            "point_name": "PT_CENTER",
                            "reference": {"operation": "rev01", "selector": "far_end_face"},
                        },
                    },
                    {
                        "id": "pt_ecc",
                        "scenario": "point",
                        "params": {
                            "mode": "offset_from_point",
                            "point_name": "PT_ECC",
                            "reference": {"operation": "pt_center"},
                            "offset": {"dy": 8},
                        },
                    },
                    {
                        "id": "lcs_ecc",
                        "scenario": "lcs",
                        "params": {
                            "mode": "point",
                            "lcs_name": "LCS_ECC",
                            "reference": {"operation": "pt_ecc"},
                        },
                    },
                    {
                        "id": "rev02",
                        "scenario": "stepped_shaft",
                        "params": {
                            "name": "Eccentric journal",
                            "parameter_prefix": "REV02",
                            "placement": {"base": {"mode": "csys_ref", "reference": {"operation": "lcs_ecc"}}},
                            "steps": [
                                {"length": 16, "diameter": 18},
                                {"length": 12, "diameter": 12},
                            ],
                        },
                    },
                ],
            },
        )

        operations = preview["params"]["operations"]
        self.assertEqual(preview["scenario"], "workflow")
        self.assertEqual(preview["summary"]["operation_count"], 5)
        self.assertEqual(preview["summary"]["operation_ids"], ["rev01", "pt_center", "pt_ecc", "lcs_ecc", "rev02"])
        self.assertEqual(operations[1]["bindings"]["reference_operation"], "rev01")
        self.assertEqual(operations[1]["depends_on"], ["rev01"])
        self.assertEqual(operations[1]["params"]["reference"]["output_ref"], "rev01.far_end_face")
        self.assertEqual(operations[2]["bindings"]["reference_operation"], "pt_center")
        self.assertEqual(operations[2]["params"]["reference"]["output_ref"], "pt_center.point")
        self.assertEqual(operations[3]["bindings"]["reference_operation"], "pt_ecc")
        self.assertEqual(operations[3]["params"]["reference"]["output_ref"], "pt_ecc.point")
        self.assertEqual(operations[4]["bindings"]["placement_operation"], "lcs_ecc")
        self.assertEqual(operations[4]["params"]["placement"]["base"]["reference"]["output_ref"], "lcs_ecc.lcs")
        self.assertEqual(operations[4]["scenario"], "stepped_shaft")
        self.assertEqual(operations[4]["preview"]["scenario"], "stepped_shaft")
        self.assertEqual(preview["operations"][4]["depends_on"], ["lcs_ecc"])

    def test_preview_workflow_preserves_runtime_object_probe_options(self) -> None:
        preview = preview_part_scenario(
            "workflow",
            {
                "include_runtime_object_probe": True,
                "runtime_object_probe_max_items": 7,
                "operations": [
                    {
                        "id": "pt1",
                        "scenario": "point",
                        "params": {"mode": "global", "origin": [0, 0, 0]},
                    },
                ],
            },
        )

        self.assertTrue(preview["params"]["include_runtime_object_probe"])
        self.assertEqual(preview["params"]["runtime_object_probe_max_items"], 7)

    def test_preview_workflow_supports_explicit_output_tokens(self) -> None:
        preview = preview_part_scenario(
            "workflow",
            {
                "operations": [
                    {
                        "id": "rev01",
                        "scenario": "stepped_shaft",
                        "params": {"steps": [{"length": 18, "diameter": 30}, {"length": 12, "diameter": 20}]},
                    },
                    {
                        "id": "pt_end",
                        "scenario": "point",
                        "params": {
                            "mode": "center_of_object",
                            "point_name": "PT_END",
                            "reference": {"operation": "rev01", "output": "end_face"},
                        },
                    },
                    {
                        "id": "pt_ecc",
                        "scenario": "point",
                        "params": {
                            "mode": "offset_from_point",
                            "point_name": "PT_ECC",
                            "reference": {"operation": "pt_end", "output": "point"},
                            "offset": {"dy": 6},
                        },
                    },
                    {
                        "id": "lcs_ecc",
                        "scenario": "lcs",
                        "params": {
                            "mode": "point",
                            "lcs_name": "LCS_ECC",
                            "reference": {"ref": "pt_ecc.point"},
                        },
                    },
                    {
                        "id": "rev02",
                        "scenario": "stepped_shaft",
                        "params": {
                            "placement": {"base": {"mode": "csys_ref", "reference": {"operation": "lcs_ecc", "output": "lcs"}}},
                            "steps": [{"length": 10, "diameter": 12}],
                        },
                    },
                ]
            },
        )

        operations = preview["params"]["operations"]
        self.assertEqual(operations[1]["bindings"]["reference_output"], "far_end_face")
        self.assertEqual(operations[2]["bindings"]["reference_output"], "point")
        self.assertEqual(operations[3]["bindings"]["reference_output"], "point")
        self.assertEqual(operations[4]["bindings"]["placement_output"], "lcs")
        self.assertEqual(operations[1]["params"]["reference"]["selector"], "far_end_face")
        self.assertEqual(operations[1]["params"]["reference"]["output_ref"], "rev01.far_end_face")
        self.assertEqual(operations[2]["params"]["reference"]["output_ref"], "pt_end.point")
        self.assertEqual(operations[3]["params"]["reference"]["output_ref"], "pt_ecc.point")
        self.assertEqual(operations[4]["params"]["placement"]["base"]["reference"]["output_ref"], "lcs_ecc.lcs")
        self.assertEqual(operations[4]["preview"]["interface"]["outputs"]["end_face"]["type"], "face")

    def test_preview_workflow_exports_selected_outputs(self) -> None:
        preview = preview_part_scenario(
            "workflow",
            {
                "operations": [
                    {
                        "id": "rev01",
                        "scenario": "stepped_shaft",
                        "params": {"steps": [{"length": 18, "diameter": 30}, {"length": 12, "diameter": 20}]},
                    },
                    {
                        "id": "pt_end",
                        "scenario": "point",
                        "params": {
                            "mode": "center_of_object",
                            "reference": {"ref": "rev01.end_face"},
                        },
                    },
                ],
                "exports": {
                    "shaft_body": "rev01.body",
                    "tail_face": {"operation": "rev01", "output": "end_face"},
                    "tail_center": {"ref": "pt_end.point"},
                },
            },
        )

        self.assertEqual(preview["summary"]["export_count"], 3)
        self.assertEqual(preview["summary"]["export_names"], ["shaft_body", "tail_face", "tail_center"])
        self.assertEqual(preview["params"]["exports"][0]["token"], "rev01.body")
        self.assertEqual(preview["params"]["exports"][1]["output_key"], "far_end_face")
        self.assertEqual(preview["interface"]["outputs"]["shaft_body"]["type"], "body")
        self.assertEqual(preview["interface"]["outputs"]["tail_face"]["type"], "face")
        self.assertEqual(preview["interface"]["outputs"]["tail_center"]["type"], "point")

    def test_preview_workflow_invalid_export_reference_mentions_path(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"exports\[0\]\.ref must be a workflow output reference like op\.output or \{ref: 'op\.output'\}; got \{'operation': None, 'output': 'body'\}",
        ):
            preview_part_scenario(
                "workflow",
                {
                    "operations": [
                        {
                            "id": "rev01",
                            "scenario": "stepped_shaft",
                            "params": {"steps": [{"length": 18, "diameter": 30}]},
                        }
                    ],
                    "exports": [
                        {
                            "name": "broken_export",
                            "operation": "",
                            "output": "body",
                        }
                    ],
                },
            )

    def test_preview_workflow_unknown_operation_error_lists_available_operations(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"Workflow reference rev_missing\.end_face points to unknown operation rev_missing; available operations: rev01",
        ):
            preview_part_scenario(
                "workflow",
                {
                    "operations": [
                        {
                            "id": "rev01",
                            "scenario": "stepped_shaft",
                            "params": {"steps": [{"length": 18, "diameter": 30}]},
                        },
                        {
                            "id": "pt_end",
                            "scenario": "point",
                            "params": {
                                "mode": "center_of_object",
                                "reference": {"ref": "rev_missing.end_face"},
                            },
                        },
                    ]
                },
            )

    def test_preview_workflow_invalid_placement_reference_mentions_path(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"operations\[1\]\.params\.placement\.base\.reference must be a workflow output reference like op\.output or \{ref: 'op\.output'\}; got \{'operation': '', 'output': 'lcs'\}",
        ):
            preview_part_scenario(
                "workflow",
                {
                    "operations": [
                        {
                            "id": "lcs_ecc",
                            "scenario": "lcs",
                            "params": {"mode": "global", "origin": [60, 8, 0]},
                        },
                        {
                            "id": "rev02",
                            "scenario": "stepped_shaft",
                            "params": {
                                "placement": {
                                    "base": {
                                        "mode": "csys_ref",
                                        "reference": {"operation": "", "output": "lcs"},
                                    }
                                },
                                "steps": [{"length": 10, "diameter": 12}],
                            },
                        },
                    ]
                },
            )

    def test_preview_workflow_unknown_output_error_lists_available_outputs(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"Workflow operation rev01 \(scenario=stepped_shaft\) does not export output missing_face; available outputs: .*far_end_face",
        ):
            preview_part_scenario(
                "workflow",
                {
                    "operations": [
                        {
                            "id": "rev01",
                            "scenario": "stepped_shaft",
                            "params": {"steps": [{"length": 18, "diameter": 30}]},
                        },
                        {
                            "id": "pt_end",
                            "scenario": "point",
                            "params": {
                                "mode": "center_of_object",
                                "reference": {"ref": "rev01.missing_face"},
                            },
                        },
                    ]
                },
            )

    def test_preview_workflow_wrong_reference_type_mentions_available_outputs(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"Workflow reference rev01\.body must target scenarios=point, got stepped_shaft on operation rev01; available outputs: .*body",
        ):
            preview_part_scenario(
                "workflow",
                {
                    "operations": [
                        {
                            "id": "rev01",
                            "scenario": "stepped_shaft",
                            "params": {"steps": [{"length": 18, "diameter": 30}]},
                        },
                        {
                            "id": "pt_ecc",
                            "scenario": "point",
                            "params": {
                                "mode": "offset_from_point",
                                "reference": {"ref": "rev01.body"},
                                "offset": {"dy": 8},
                            },
                        },
                    ]
                },
            )

    def test_preview_workflow_resolves_object_lcs_binding(self) -> None:
        preview = preview_part_scenario(
            "workflow",
            {
                "operations": [
                    {
                        "id": "rev01",
                        "scenario": "stepped_shaft",
                        "params": {"steps": [{"length": 18, "diameter": 30}, {"length": 12, "diameter": 20}]},
                    },
                    {
                        "id": "lcs_tail",
                        "scenario": "lcs",
                        "params": {
                            "mode": "object",
                            "lcs_name": "LCS_TAIL",
                            "reference": {"operation": "rev01", "selector": "far_end_face"},
                        },
                    },
                ]
            },
        )

        operations = preview["params"]["operations"]
        self.assertEqual(operations[1]["bindings"]["reference_operation"], "rev01")
        self.assertEqual(operations[1]["depends_on"], ["rev01"])
        self.assertEqual(operations[1]["preview"]["summary"]["reference"]["selector"], "far_end_face")

    def test_preview_workflow_object_references_use_source_preview_not_source_params(self) -> None:
        preview = preview_part_scenario(
            "workflow",
            {
                "operations": [
                    {
                        "id": "rev01",
                        "scenario": "stepped_shaft",
                        "params": {
                            "steps": [
                                {"length": 18, "diameter": 30},
                                {"length": 12, "diameter": 20},
                            ]
                        },
                    },
                    {
                        "id": "pt_shoulder",
                        "scenario": "point",
                        "params": {
                            "mode": "center_of_object",
                            "reference": {"operation": "rev01", "selector": "shoulder_1_face"},
                        },
                    },
                    {
                        "id": "lcs_end",
                        "scenario": "lcs",
                        "params": {
                            "mode": "object",
                            "lcs_name": "LCS_END",
                            "reference": {"operation": "rev01", "selector": "step_2_end_face"},
                        },
                    },
                ]
            },
        )

        point_reference = preview["params"]["operations"][1]["params"]["reference"]
        lcs_reference = preview["params"]["operations"][2]["params"]["reference"]
        self.assertEqual(point_reference["selector"], "shoulder_1_face")
        self.assertIn("source_preview", point_reference)
        self.assertNotIn("source_params", point_reference)
        self.assertEqual(lcs_reference["selector"], "step_2_end_face")
        self.assertIn("source_preview", lcs_reference)
        self.assertNotIn("source_params", lcs_reference)

    def test_preview_rejects_equal_adjacent_diameters(self) -> None:
        with self.assertRaisesRegex(ValueError, "Adjacent steps must not have equal diameters"):
            preview_part_scenario(
                "stepped_shaft",
                {
                    "steps": [
                        {"length": 10, "diameter": 12},
                        {"length": 15, "diameter": 12},
                    ]
                },
            )

    def test_create_part_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "stepped-shaft",
            {"steps": [{"length": 12, "diameter": 6}], "close_after_save": False},
            output_path=r"C:\Temp\kompas-mcp\unit-shaft.m3d",
            close_after_save=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["summary"]["total_length"], 12.0)
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "stepped_shaft")
        self.assertEqual(payload["params"]["steps"][0]["radius"], 3.0)

    def test_create_workflow_from_scenario_passes_normalized_operations(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "workflow",
            {
                "operations": [
                    {
                        "id": "rev01",
                        "scenario": "stepped_shaft",
                        "params": {"steps": [{"length": 12, "diameter": 6}]},
                    },
                    {
                        "id": "pt_center",
                        "scenario": "point",
                        "params": {
                            "mode": "center_of_object",
                            "reference": {"operation": "rev01", "selector": "far_end_face"},
                        },
                    },
                ],
                "exports": {
                    "shaft_body": "rev01.body",
                },
                "close_after_save": False,
            },
            output_path=r"C:\Temp\kompas-mcp\unit-workflow.m3d",
            close_after_save=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["summary"]["operation_count"], 2)
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "workflow")
        self.assertEqual(payload["params"]["operations"][0]["id"], "rev01")
        self.assertEqual(payload["params"]["operations"][1]["bindings"]["reference_operation"], "rev01")
        self.assertEqual(payload["params"]["operations"][1]["bindings"]["reference_output"], "far_end_face")
        self.assertEqual(payload["params"]["operations"][1]["params"]["reference"]["output_ref"], "rev01.far_end_face")
        self.assertEqual(payload["params"]["exports"][0]["name"], "shaft_body")
        self.assertEqual(payload["params"]["exports"][0]["token"], "rev01.body")
        self.assertTrue(payload["params"]["close_after_save"])
        self.assertIn("preview", payload)

    def test_create_external_conical_step_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "external_conical_step",
            {
                "length": 32,
                "start_diameter": 28,
                "end_diameter": 16,
                "parameter_prefix": "cone01",
                "close_after_save": False,
            },
            output_path=r"C:\Temp\kompas-mcp\unit-external-conical-step.m3d",
            close_after_save=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "external_conical_step")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "external_conical_step")
        self.assertEqual(payload["params"]["length"], 32.0)
        self.assertEqual(payload["params"]["start_radius"], 14.0)
        self.assertEqual(payload["params"]["end_radius"], 8.0)
        self.assertEqual(payload["params"]["parameter_prefix"], "CONE01")
        self.assertTrue(payload["params"]["close_after_save"])

    def test_create_internal_conical_step_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "internal_conical_step",
            {
                "length": 20,
                "start_diameter": 12,
                "end_diameter": 6,
                "axial_direction": "backward",
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 40, "diameter": 30}]},
                "parameter_prefix": "icut01",
                "close_after_save": False,
            },
            output_path=r"C:\Temp\kompas-mcp\unit-internal-conical-step.m3d",
            close_after_save=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "internal_conical_step")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "internal_conical_step")
        self.assertEqual(payload["params"]["length"], 20.0)
        self.assertEqual(payload["params"]["start_radius"], 6.0)
        self.assertEqual(payload["params"]["end_radius"], 3.0)
        self.assertEqual(payload["params"]["axial_direction"], "backward")
        self.assertEqual(payload["params"]["source_scenario"], "stepped_shaft")
        self.assertEqual(payload["params"]["parameter_prefix"], "ICUT01")

    def test_create_internal_cylindrical_step_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "internal_cylindrical_step",
            {
                "length": 20,
                "diameter": 10,
                "axial_direction": "backward",
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 48, "diameter": 30}]},
                "parameter_prefix": "ibore01",
            },
            output_path=r"C:\Temp\kompas-mcp\unit-internal-cylindrical-step.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "internal_cylindrical_step")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "internal_cylindrical_step")
        self.assertEqual(payload["params"]["length"], 20.0)
        self.assertEqual(payload["params"]["diameter"], 10.0)
        self.assertEqual(payload["params"]["radius"], 5.0)
        self.assertEqual(payload["params"]["axial_direction"], "backward")
        self.assertEqual(payload["params"]["source_scenario"], "stepped_shaft")
        self.assertEqual(payload["params"]["parameter_prefix"], "IBORE01")
        self.assertTrue(payload["params"]["close_after_save"])

    def test_create_external_polygonal_step_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "external_polygonal_step",
            {
                "diameter": 22,
                "length": 18,
                "side_count": 6,
                "diameter_mode": "circumscribed_circle",
                "parameter_prefix": "poly01",
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-external-polygonal-step.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "external_polygonal_step")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "external_polygonal_step")
        self.assertEqual(payload["params"]["diameter"], 22.0)
        self.assertEqual(payload["params"]["length"], 18.0)
        self.assertEqual(payload["params"]["side_count"], 6)
        self.assertEqual(payload["params"]["diameter_mode"], "circumscribed_circle")
        self.assertEqual(payload["params"]["parameter_prefix"], "POLY01")

    def test_create_internal_polygonal_step_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "internal_polygonal_step",
            {
                "diameter": 12,
                "length": 14,
                "side_count": 8,
                "diameter_mode": "inscribed_circle",
                "axial_direction": "backward",
                "source_scenario": "external_polygonal_step",
                "source_params": {
                    "diameter": 26,
                    "length": 30,
                    "side_count": 8,
                },
                "parameter_prefix": "ipoly01",
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-internal-polygonal-step.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "internal_polygonal_step")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "internal_polygonal_step")
        self.assertEqual(payload["params"]["diameter"], 12.0)
        self.assertEqual(payload["params"]["length"], 14.0)
        self.assertEqual(payload["params"]["side_count"], 8)
        self.assertEqual(payload["params"]["axial_direction"], "backward")
        self.assertEqual(payload["params"]["source_scenario"], "external_polygonal_step")
        self.assertEqual(payload["params"]["parameter_prefix"], "IPOLY01")

    def test_create_external_flat_step_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "external_flat_step",
            {
                "diameter": 28,
                "length": 16,
                "flat_depth": 4,
                "flats_count": 1,
                "parameter_prefix": "flat01",
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-external-flat-step.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "external_flat_step")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "external_flat_step")
        self.assertEqual(payload["params"]["diameter"], 28.0)
        self.assertEqual(payload["params"]["length"], 16.0)
        self.assertEqual(payload["params"]["flat_depth"], 4.0)
        self.assertEqual(payload["params"]["flats_count"], 1)
        self.assertEqual(payload["params"]["parameter_prefix"], "FLAT01")

    def test_create_internal_flat_step_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "internal_flat_step",
            {
                "diameter": 20,
                "length": 18,
                "flat_depth": 3,
                "flats_count": 2,
                "axial_direction": "backward",
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 30, "diameter": 40}]},
                "parameter_prefix": "iflat01",
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-internal-flat-step.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "internal_flat_step")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "internal_flat_step")
        self.assertEqual(payload["params"]["diameter"], 20.0)
        self.assertEqual(payload["params"]["length"], 18.0)
        self.assertEqual(payload["params"]["flat_depth"], 3.0)
        self.assertEqual(payload["params"]["flats_count"], 2)
        self.assertEqual(payload["params"]["axial_direction"], "backward")
        self.assertEqual(payload["params"]["source_scenario"], "stepped_shaft")
        self.assertEqual(payload["params"]["parameter_prefix"], "IFLAT01")

    def test_create_external_threaded_step_from_scenario_passes_normalized_params(self) -> None:
        database_path = self._create_thread_catalog_fixture()
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "external_threaded_step",
            {
                "diameter": 20,
                "pitch": 2.5,
                "depth": 12,
                "direction": "left",
                "thread_standard": "custom_metric",
                "thread_database_path": database_path,
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 20, "diameter": 20}]},
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-external-threaded-step.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "external_threaded_step")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "external_threaded_step")
        self.assertEqual(payload["params"]["diameter"], 20.0)
        self.assertEqual(payload["params"]["pitch"], 2.5)
        self.assertEqual(payload["params"]["source_scenario"], "stepped_shaft")
        self.assertEqual(payload["params"]["source_selector"], "step_1_outer_face")
        self.assertEqual(payload["params"]["thread_length"], 12.0)
        self.assertEqual(payload["params"]["thread_depth"], 12.0)
        self.assertEqual(payload["params"]["direction"], "left")
        self.assertTrue(payload["params"]["left_thread"])
        self.assertEqual(payload["params"]["thread_standard_table_name"], "custom_metric")
        self.assertEqual(payload["params"]["thread_designation"], "M20")

    def test_create_internal_threaded_step_from_scenario_passes_normalized_params(self) -> None:
        database_path = self._create_thread_catalog_fixture()
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "internal_threaded_step",
            {
                "diameter": 16,
                "pitch": 2.0,
                "depth": 10,
                "direction": "right",
                "thread_standard": "custom_metric",
                "thread_database_path": database_path,
                "source_scenario": "internal_cylindrical_step",
                "source_params": {
                    "steps": [{"length": 18, "diameter": 16}],
                    "source_scenario": "stepped_shaft",
                    "source_params": {"steps": [{"length": 28, "diameter": 32}]},
                },
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-internal-threaded-step.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "internal_threaded_step")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "internal_threaded_step")
        self.assertEqual(payload["params"]["diameter"], 16.0)
        self.assertEqual(payload["params"]["pitch"], 2.0)
        self.assertEqual(payload["params"]["source_scenario"], "internal_cylindrical_step")
        self.assertEqual(payload["params"]["source_selector"], "inner_face")
        self.assertEqual(payload["params"]["thread_length"], 10.0)
        self.assertEqual(payload["params"]["thread_depth"], 10.0)
        self.assertEqual(payload["params"]["direction"], "right")
        self.assertFalse(payload["params"]["left_thread"])
        self.assertEqual(payload["params"]["thread_standard_table_name"], "custom_metric")
        self.assertEqual(payload["params"]["thread_designation"], "M16")
        self.assertTrue(payload["params"]["internal"])

    def test_preview_external_helical_thread_rejects_incompatible_standard(self) -> None:
        database_path = self._create_thread_catalog_fixture()
        with self.assertRaisesRegex(ValueError, "incompatible"):
            preview_part_scenario(
                "external_helical_thread",
                {
                    "diameter": 20,
                    "pitch": 2.5,
                    "length": 12,
                    "thread_standard": "custom_whitworth",
                    "thread_database_path": database_path,
                    "source_scenario": "stepped_shaft",
                    "source_params": {"steps": [{"length": 20, "diameter": 20}]},
                },
            )

    def test_create_external_helical_thread_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "external_helical_thread",
            {
                "diameter": 20,
                "pitch": 2.0,
                "length": 12,
                "depth": 1.1,
                "clearance": 0.2,
                "direction": "left",
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 20, "diameter": 20}]},
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-external-helical-thread.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "external_helical_thread")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "external_helical_thread")
        self.assertEqual(payload["params"]["diameter"], 20.0)
        self.assertEqual(payload["params"]["pitch"], 2.0)
        self.assertEqual(payload["params"]["length"], 12.0)
        self.assertAlmostEqual(payload["params"]["thread_depth"], 1.1, places=6)
        self.assertEqual(payload["params"]["clearance"], 0.2)
        self.assertAlmostEqual(payload["params"]["profile_entry_offset"], 2.1, places=6)
        self.assertAlmostEqual(payload["params"]["major_radius"], 10.0, places=6)
        self.assertAlmostEqual(payload["params"]["root_radius_level"], 8.7, places=6)
        self.assertAlmostEqual(payload["params"]["root_diameter"], 17.4, places=6)
        self.assertAlmostEqual(payload["params"]["fundamental_triangle_height"], 2.0 / (2.0 * math.tan(math.radians(30.0))), places=6)
        self.assertAlmostEqual(payload["params"]["profile_base_drop"], payload["params"]["fundamental_triangle_height"] / 8.0, places=6)
        self.assertAlmostEqual(payload["params"]["profile_apex_height"], payload["params"]["fundamental_triangle_height"] * 7.0 / 8.0, places=6)
        self.assertAlmostEqual(payload["params"]["profile_outer_half_width"], 0.875, places=6)
        self.assertAlmostEqual(payload["params"]["root_radius"], 0.21554445662276763, places=6)
        self.assertEqual(payload["params"]["parameter_prefix"], "EXTERNAL_HELICAL_THREAD")
        self.assertAlmostEqual(payload["params"]["spiral_length"], 14.1, places=6)
        self.assertEqual(len(payload["params"]["profile_variables"]), 3)
        self.assertEqual(len(payload["params"]["profile_dimensions"]), 7)
        self.assertEqual(len(payload["params"]["profile_constraints"]), 39)
        self.assertEqual(payload["params"]["direction"], "left")
        self.assertTrue(payload["params"]["left_thread"])
        self.assertEqual(payload["params"]["profile_variables"][0]["name"], "Diameter_thread_external_left_M20x2_1")
        self.assertEqual(payload["params"]["profile_variables"][1]["name"], "Pitch_thread_external_left_M20x2_1")
        self.assertEqual(payload["params"]["profile_variables"][2]["name"], "Length_thread_external_left_M20x2_1")
        self.assertEqual(
            payload["params"]["source_variable_bindings"][0]["expression"],
            "Diameter_thread_external_left_M20x2_1",
        )
        self.assertEqual(payload["params"]["operation_variable_bindings"][0]["expression"], "Pitch_thread_external_left_M20x2_1")
        self.assertEqual(
            payload["params"]["operation_variable_bindings"][1]["expression"],
            "Length_thread_external_left_M20x2_1 + 1.05 * Pitch_thread_external_left_M20x2_1",
        )
        self.assertEqual(payload["params"]["profile_dimensions"][0]["expression"], "Diameter_thread_external_left_M20x2_1 / 2")
        self.assertEqual(payload["params"]["profile_dimensions"][1]["expression"], "0.5 * Pitch_thread_external_left_M20x2_1")
        self.assertEqual(
            payload["params"]["public_profile_variables"],
            [
                "Diameter_thread_external_left_M20x2_1",
                "Pitch_thread_external_left_M20x2_1",
                "Length_thread_external_left_M20x2_1",
            ],
        )
        self.assertEqual(payload["params"]["feature_display_name"], "Thread external left M20x2 1")
        self.assertEqual(payload["params"]["source_selector"], "step_1_outer_face")

    def test_create_internal_helical_thread_from_scenario_passes_normalized_params(self) -> None:
        geometry = build_metric_thread_geometry(16.0, 2.0)
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "internal_helical_thread",
            {
                "diameter": 16,
                "pitch": 2.0,
                "length": 10,
                "depth": 1.0,
                "clearance": 0.15,
                "direction": "right",
                "source_scenario": "internal_cylindrical_step",
                "source_params": {
                    "steps": [{"length": 18, "diameter": geometry["internal_minor_diameter"]}],
                    "source_scenario": "stepped_shaft",
                    "source_params": {"steps": [{"length": 28, "diameter": 32}]},
                },
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-internal-helical-thread.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "internal_helical_thread")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "internal_helical_thread")
        self.assertEqual(payload["params"]["diameter"], 16.0)
        self.assertEqual(payload["params"]["pitch"], 2.0)
        self.assertEqual(payload["params"]["length"], 10.0)
        self.assertEqual(payload["params"]["thread_depth"], 1.0)
        self.assertEqual(payload["params"]["clearance"], 0.15)
        self.assertAlmostEqual(payload["params"]["profile_entry_offset"], 2.1, places=6)
        self.assertAlmostEqual(payload["params"]["fundamental_triangle_height"], 2.0 / (2.0 * math.tan(math.radians(30.0))), places=6)
        self.assertAlmostEqual(payload["params"]["profile_crest_drop"], payload["params"]["fundamental_triangle_height"] - 1.15, places=6)
        self.assertAlmostEqual(payload["params"]["root_width"], 0.25, places=6)
        self.assertAlmostEqual(payload["params"]["root_radius"], 0.14433756729740643, places=6)
        self.assertAlmostEqual(payload["params"]["profile_outer_half_width"], 0.6639528095680696, places=6)
        self.assertAlmostEqual(payload["params"]["profile_surface_offset"], 0.15, places=6)
        self.assertAlmostEqual(payload["params"]["profile_surface_offset_effective"], 0.0, places=6)
        self.assertFalse(payload["params"]["profile_surface_offset_applied"])
        self.assertEqual(payload["params"]["profile_surface_offset_status"], "ignored_in_v1")
        self.assertAlmostEqual(
            payload["params"]["profile_sketch_origin_shift"],
            -geometry["internal_minor_radius"],
            places=6,
        )
        self.assertAlmostEqual(payload["params"]["recommended_source_diameter"], geometry["internal_minor_diameter"], places=6)
        self.assertEqual(payload["params"]["source_diameter_validation"]["status"], "match")
        self.assertEqual(payload["params"]["parameter_prefix"], "INTERNAL_HELICAL_THREAD")
        self.assertAlmostEqual(payload["params"]["spiral_length"], 12.1, places=6)
        self.assertEqual(len(payload["params"]["profile_variables"]), 3)
        self.assertEqual(len(payload["params"]["profile_dimensions"]), 6)
        self.assertEqual(len(payload["params"]["profile_constraints"]), 41)
        self.assertEqual(payload["params"]["direction"], "right")
        self.assertFalse(payload["params"]["left_thread"])
        self.assertEqual(payload["params"]["profile_variables"][0]["name"], "Diameter_thread_internal_right_M16x2_1")
        self.assertEqual(payload["params"]["profile_variables"][1]["name"], "Pitch_thread_internal_right_M16x2_1")
        self.assertEqual(payload["params"]["profile_variables"][2]["name"], "Length_thread_internal_right_M16x2_1")
        self.assertEqual(
            payload["params"]["source_variable_bindings"][0]["expression"],
            "Diameter_thread_internal_right_M16x2_1",
        )
        self.assertEqual(payload["params"]["operation_variable_bindings"][0]["expression"], "Pitch_thread_internal_right_M16x2_1")
        self.assertEqual(
            payload["params"]["operation_variable_bindings"][1]["expression"],
            "Length_thread_internal_right_M16x2_1 + 1.05 * Pitch_thread_internal_right_M16x2_1",
        )
        self.assertEqual(payload["params"]["profile_dimensions"][0]["expression"], "Diameter_thread_internal_right_M16x2_1 / 2")
        self.assertEqual(payload["params"]["profile_dimensions"][1]["expression"], "0.5 * Pitch_thread_internal_right_M16x2_1")
        self.assertEqual(
            payload["params"]["public_profile_variables"],
            [
                "Diameter_thread_internal_right_M16x2_1",
                "Pitch_thread_internal_right_M16x2_1",
                "Length_thread_internal_right_M16x2_1",
            ],
        )
        self.assertEqual(payload["params"]["feature_display_name"], "Thread internal right M16x2 1")
        self.assertEqual(payload["params"]["source_selector"], "inner_face")
        self.assertTrue(payload["params"]["internal"])

    def test_create_face_ring_groove_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "face_ring_groove",
            {
                "inner_diameter": 14,
                "outer_diameter": 28,
                "depth": 6,
                "inner_wall_angle_degrees": 4,
                "outer_wall_angle_degrees": 10,
                "axial_direction": "backward",
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 48, "diameter": 32}]},
                "parameter_prefix": "groove01",
            },
            output_path=r"C:\Temp\kompas-mcp\unit-face-ring-groove.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "face_ring_groove")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "face_ring_groove")
        self.assertEqual(payload["params"]["inner_diameter"], 14.0)
        self.assertEqual(payload["params"]["outer_diameter"], 28.0)
        self.assertEqual(payload["params"]["depth"], 6.0)
        self.assertEqual(payload["params"]["inner_radius"], 7.0)
        self.assertEqual(payload["params"]["outer_radius"], 14.0)
        self.assertEqual(payload["params"]["axial_direction"], "backward")
        self.assertEqual(payload["params"]["parameter_prefix"], "GROOVE01")

    def test_preview_bolt_circle_holes_builds_pattern_contract(self) -> None:
        preview = preview_part_scenario(
            "bolt_circle_holes",
            {
                "hole_diameter": 6,
                "depth": 10,
                "bolt_circle_diameter": 32,
                "count": 4,
                "start_angle_degrees": 30,
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 18, "diameter": 40}]},
                "parameter_prefix": "bch01",
            },
        )

        self.assertEqual(preview["scenario"], "bolt_circle_holes")
        self.assertEqual(preview["summary"]["hole_diameter"], 6.0)
        self.assertEqual(preview["summary"]["bolt_circle_diameter"], 32.0)
        self.assertEqual(preview["summary"]["count"], 4)
        self.assertEqual(preview["summary"]["axial_direction"], "backward")
        self.assertTrue(preview["summary"]["auxiliary_geometry_hidden"])
        self.assertEqual(preview["summary"]["planned_variable_count"], 5)
        self.assertEqual(preview["operations"][1]["operation"], "add_variables")
        self.assertEqual(preview["operations"][2]["operation"], "create_source_body")
        self.assertEqual(preview["operations"][-2]["operation"], "create_circular_pattern")
        self.assertEqual(preview["operations"][-2]["pattern_count_expression"], "BCH01_N1")
        self.assertEqual(preview["operations"][-2]["pattern_step_expression"], "BCH01_A1")
        self.assertEqual(preview["operations"][-2]["operation_variable_bindings"][0]["expression"], "BCH01_N1")
        self.assertEqual(preview["operations"][-2]["operation_variable_bindings"][1]["expression"], "BCH01_A1")
        self.assertEqual(preview["operations"][-1]["operation"], "hide_auxiliary_geometry")
        self.assertIn("pattern_axis", preview["operations"][-1]["objects"])
        self.assertEqual(preview["interface"]["feature_type"], "pattern.bolt_circle_holes")
        self.assertTrue(preview["interface"]["definition"]["auxiliary_geometry_hidden"])
        self.assertEqual(preview["interface"]["outputs"]["axis"]["type"], "axis")
        self.assertEqual(preview["interface"]["outputs"]["first_hole_center"]["type"], "point")
        self.assertEqual(preview["interface"]["outputs"]["first_hole_lcs"]["type"], "lcs")
        self.assertEqual(preview["interface"]["parameters"]["driving_diameters"], ["BCH01_D1"])
        self.assertEqual(preview["interface"]["parameters"]["driving_lengths"], ["BCH01_L1"])
        self.assertEqual(preview["interface"]["parameters"]["driving_pcd"], "BCH01_PCD1")
        self.assertEqual(preview["interface"]["parameters"]["driving_pattern_count"], "BCH01_N1")
        self.assertEqual(preview["interface"]["parameters"]["driving_pattern_angle_step"], "BCH01_A1")

    def test_create_bolt_circle_holes_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "bolt_circle_holes",
            {
                "hole_diameter": 6,
                "depth": 10,
                "bolt_circle_diameter": 32,
                "count": 6,
                "start_angle_degrees": 15,
                "source_scenario": "stepped_shaft",
                "source_params": {"steps": [{"length": 18, "diameter": 40}]},
                "parameter_prefix": "bch01",
            },
            output_path=r"C:\Temp\kompas-mcp\unit-bolt-circle-holes.m3d",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["scenario"], "bolt_circle_holes")
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "bolt_circle_holes")
        self.assertEqual(payload["params"]["hole_diameter"], 6.0)
        self.assertEqual(payload["params"]["depth"], 10.0)
        self.assertEqual(payload["params"]["bolt_circle_diameter"], 32.0)
        self.assertEqual(payload["params"]["count"], 6)
        self.assertEqual(payload["params"]["start_angle_degrees"], 15.0)
        self.assertEqual(payload["params"]["parameter_prefix"], "BCH01")
        self.assertTrue(payload["params"]["auxiliary_geometry_hidden"])
        self.assertEqual(payload["params"]["pattern_count_expression"], "BCH01_N1")
        self.assertEqual(payload["params"]["pattern_step_expression"], "BCH01_A1")
        self.assertIn("BCH01_PCD1", payload["params"]["first_hole_offset_expressions"][1])
        self.assertEqual(payload["params"]["pattern_operation_variable_bindings"][0]["expression"], "BCH01_N1")

    def test_preview_compression_spring_builds_spiral_contract(self) -> None:
        preview = preview_part_scenario(
            "spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "height": 48,
                "turns": 6,
                "parameter_prefix": "spg01",
            },
        )

        self.assertEqual(preview["scenario"], "compression_spring")
        self.assertEqual(preview["summary"]["mean_diameter"], 30.0)
        self.assertEqual(preview["summary"]["outer_diameter"], 34.0)
        self.assertEqual(preview["summary"]["inner_diameter"], 26.0)
        self.assertEqual(preview["summary"]["height"], 48.0)
        self.assertEqual(preview["summary"]["turns"], 6.0)
        self.assertEqual(preview["summary"]["working_turns"], 6.0)
        self.assertEqual(preview["summary"]["total_turns"], 6.0)
        self.assertEqual(preview["summary"]["end_turns_per_side"], 0.0)
        self.assertEqual(preview["summary"]["ground_turns_per_side"], 0.0)
        self.assertTrue(preview["summary"]["live_supported"])
        self.assertEqual(preview["summary"]["profile_plane"], "XOY")
        self.assertEqual(preview["summary"]["sweep_alignment"], "orthogonal_to_path")
        self.assertEqual(preview["summary"]["connector_count"], 0)
        self.assertEqual(preview["params"]["sketch"]["parameterization_order"], "staged")
        self.assertEqual(preview["operations"][1]["operation"], "add_variables")
        self.assertEqual(preview["operations"][3]["operation"], "create_spiral_path")
        self.assertEqual(preview["operations"][3]["phase_degrees"], 90.0)
        self.assertEqual(preview["operations"][3]["turning_angle_degrees"], 0.0)
        self.assertEqual(preview["operations"][3]["orientation_angle_degrees"], 0.0)
        self.assertIsNone(preview["operations"][3]["anchor_rotation_expression"])
        self.assertEqual(preview["operations"][3]["angle_application_mode"], "orientation")
        self.assertIsNone(preview["operations"][3]["start_offset_expression"])
        self.assertEqual(
            preview["operations"][3]["operation_variable_bindings"][0]["expression"],
            "(SPG01_D1) - (SPG01_WD1)",
        )
        self.assertEqual(preview["operations"][3]["operation_variable_bindings"][1]["expression"], "SPG01_P1")
        self.assertEqual(
            preview["operations"][3]["operation_variable_bindings"][2]["expression"],
            "SPG01_H1 - 2 * (SPG01_N21 * SPG01_WD1)",
        )
        self.assertEqual(preview["operations"][4]["operation"], "create_wire_profile")
        self.assertEqual(preview["operations"][4]["plane"], "XOY")
        self.assertEqual(preview["operations"][4]["name"], "spring_wire_profile")
        self.assertEqual(preview["operations"][4]["sketch_parameterization"]["target_state"], "fully_defined")
        self.assertEqual(preview["operations"][4]["sketch_parameterization"]["constraint_count"], 6)
        self.assertEqual(preview["operations"][4]["sketch_parameterization"]["dimension_count"], 2)
        circle_center_lock = next(
            constraint
            for constraint in preview["operations"][4]["sketch_parameterization"]["constraints"]
            if constraint["kind"] == "merge_points" and constraint["partner"] == "profile_circle"
        )
        self.assertEqual(circle_center_lock["target"], "radius_ref")
        self.assertEqual(circle_center_lock["index"], 1)
        self.assertEqual(circle_center_lock["partner_index"], 0)
        self.assertEqual(
            preview["operations"][4]["sketch_parameterization"]["dimensions"][0]["expression"],
            "((SPG01_D1) - (SPG01_WD1)) / 2",
        )
        self.assertEqual(
            preview["operations"][4]["sketch_parameterization"]["dimensions"][1],
            {
                "kind": "line_length",
                "target": "profile_radius_ref",
                "expression": "(SPG01_WD1) / 2",
                "driving": True,
                "placement_index": 1,
            },
        )
        self.assertEqual(preview["operations"][5]["operation"], "boss_evolution")
        self.assertEqual(preview["operations"][5]["path_count"], 1)
        self.assertEqual(preview["operations"][5]["sweep_alignment"], "orthogonal_to_path")
        self.assertEqual(preview["operations"][5]["live_status"], "planned")
        self.assertTrue(preview["summary"]["contour_ready"])
        self.assertAlmostEqual(preview["summary"]["max_joint_gap"], 0.0, places=9)
        self.assertEqual(preview["interface"]["feature_type"], "spring.compression")
        self.assertTrue(preview["interface"]["outputs"]["body"]["live_supported"])
        self.assertEqual(preview["interface"]["parameters"]["driving_mean_diameter"], "SPG01_D1")
        self.assertEqual(preview["interface"]["parameters"]["driving_wire_diameter"], "SPG01_WD1")
        self.assertEqual(preview["interface"]["parameters"]["driving_pitch"], "SPG01_P1")
        self.assertEqual(preview["interface"]["parameters"]["driving_height"], "SPG01_H1")
        self.assertEqual(preview["interface"]["parameters"]["driving_turn_count"], "SPG01_N1")
        self.assertEqual(preview["interface"]["parameters"]["driving_end_turn_count_per_side"], "SPG01_N21")
        self.assertEqual(preview["interface"]["parameters"]["driving_ground_turn_count_per_side"], "SPG01_N31")
        self.assertEqual(preview["interface"]["parameters"]["driving_start_end_turn_count"], "")
        self.assertEqual(preview["interface"]["parameters"]["driving_finish_end_turn_count"], "")
        self.assertEqual(preview["interface"]["parameters"]["driving_start_ground_turn_count"], "")
        self.assertEqual(preview["interface"]["parameters"]["driving_finish_ground_turn_count"], "")

    def test_preview_compression_spring_supports_segmented_end_turns(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "outer_diameter": 34,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "ground_turns_per_side": 0.5,
            },
        )
        segment_roles = [
            operation["role"]
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        segment_phases = [
            operation["phase_degrees"]
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        segment_turning_angles = [
            operation["turning_angle_degrees"]
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        segment_orientation_angles = [
            operation["orientation_angle_degrees"]
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        segment_angle_modes = [
            operation["angle_application_mode"]
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        segment_start_offset_expressions = [
            operation.get("start_offset_expression")
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        segment_anchor_rotation_expressions = [
            operation.get("anchor_rotation_expression")
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        segment_bindings = [
            operation["operation_variable_bindings"]
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        self.assertEqual(segment_roles, ["start_end", "working", "finish_end"])
        self.assertEqual(segment_phases[:2], [90.0, -180.0])
        self.assertEqual(segment_turning_angles, [0.0, 0.0, 0.0])
        self.assertEqual(segment_orientation_angles, [0.0, 0.0, 0.0])
        self.assertEqual(segment_angle_modes, ["orientation", "orientation", "orientation"])
        self.assertEqual(
            segment_start_offset_expressions,
            [
                None,
                "N21 * WD1",
                "(N21 * WD1) + (H1 - 2 * (N21 * WD1))",
            ],
        )
        self.assertIsNone(segment_anchor_rotation_expressions[0])
        self.assertIn("floor", str(segment_anchor_rotation_expressions[1]).lower())
        self.assertIn("N21", str(segment_anchor_rotation_expressions[1]))
        self.assertNotIn("AR", str(segment_anchor_rotation_expressions[1]))
        self.assertIn("floor", str(segment_anchor_rotation_expressions[2]).lower())
        self.assertIn("N21", str(segment_anchor_rotation_expressions[2]))
        self.assertIn("P1", str(segment_anchor_rotation_expressions[2]))
        self.assertNotIn("AR", str(segment_anchor_rotation_expressions[2]))
        self.assertEqual(len(segment_bindings[0]), 3)
        self.assertEqual(len(segment_bindings[1]), 3)
        self.assertEqual(len(segment_bindings[2]), 3)
        boss_operations = [
            operation
            for operation in preview["operations"]
            if operation.get("operation") == "boss_evolution"
        ]
        self.assertEqual(len(boss_operations), 1)
        self.assertEqual(boss_operations[0]["path_count"], 5)
        self.assertEqual(preview["summary"]["mean_diameter"], 30.0)
        self.assertEqual(preview["summary"]["total_turns"], 7.0)
        self.assertEqual(preview["summary"]["end_turns_per_side"], 0.75)
        self.assertEqual(preview["summary"]["ground_turns_per_side"], 0.5)
        self.assertEqual(preview["summary"]["connector_count"], 2)
        self.assertEqual(preview["summary"]["transition_fillet_radius"], 1.5)
        self.assertAlmostEqual(preview["summary"]["transition_trim_length"], 5.0390475290475285)
        self.assertAlmostEqual(preview["summary"]["transition_connect_tension"], 7.862156192801056)
        self.assertTrue(preview["summary"]["contour_ready"])
        self.assertAlmostEqual(preview["summary"]["max_joint_gap"], 0.0, places=9)

    def test_preview_compression_spring_accepts_negative_start_phase(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 48,
                "working_turns": 6,
                "start_phase_degrees": -90,
            },
        )
        spiral_operation = next(
            operation
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        )
        self.assertEqual(spiral_operation["phase_degrees"], -90.0)
        self.assertEqual(spiral_operation["turning_angle_degrees"], 0.0)
        self.assertEqual(spiral_operation["orientation_angle_degrees"], 0.0)
        self.assertIsNone(spiral_operation["anchor_rotation_expression"])
        self.assertEqual(spiral_operation["angle_application_mode"], "orientation")
        self.assertTrue(preview["summary"]["contour_ready"])

    def test_preview_compression_spring_allows_disabling_default_transition_connectors(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "transition_fillet_radius": 0,
            },
        )
        self.assertEqual(preview["summary"]["connector_count"], 0)
        self.assertIsNone(preview["summary"]["transition_fillet_radius"])
        self.assertIsNone(preview["summary"]["transition_trim_length"])
        self.assertIsNone(preview["summary"]["transition_connect_tension"])
        self.assertEqual(preview["params"]["connector_plan"], [])

    def test_preview_compression_spring_plans_first_transition_connect_curve(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "transition_fillet_radius": 1.5,
            },
        )
        summary = preview["summary"]
        self.assertEqual(summary["connector_count"], 2)
        self.assertEqual(summary["transition_fillet_radius"], 1.5)
        self.assertAlmostEqual(summary["transition_trim_length"], 5.0390475290475285)
        self.assertAlmostEqual(summary["transition_connect_tension"], 7.862156192801056)
        self.assertEqual(summary["transition_trim_length_variable"], "TL1")
        self.assertEqual(summary["transition_connect_tension_variable"], "TN1")
        self.assertIn("sqrt", str(summary["transition_trim_length_expression"]))
        self.assertIn("abs", str(summary["transition_trim_length_expression"]))
        self.assertIn("sqrt", str(summary["transition_connect_tension_expression"]))
        self.assertIn("abs", str(summary["transition_connect_tension_expression"]))
        self.assertEqual(
            preview["params"]["full_path_sequence"],
            [
                "spring_start_end_to_working_curve1_local_path",
                "spring_start_end_to_working_connect_path",
                "spring_working_to_finish_end_curve1_local_path",
                "spring_working_to_finish_end_connect_path",
                "spring_working_to_finish_end_curve2_local_path",
            ],
        )
        self.assertEqual(len(preview["params"]["connector_plan"]), 2)
        first_connector = preview["params"]["connector_plan"][0]
        self.assertEqual(first_connector["builder"], "trimmed_connect_curve")
        self.assertEqual(first_connector["path_name"], "spring_start_end_to_working_connect_path")
        second_connector = preview["params"]["connector_plan"][1]
        self.assertEqual(second_connector["builder"], "trimmed_connect_curve")
        self.assertEqual(second_connector["path_name"], "spring_working_to_finish_end_connect_path")
        self.assertEqual(
            second_connector["curve1_path_name"],
            "spring_start_end_to_working_curve2_local_path",
        )
        self.assertAlmostEqual(first_connector["trim_length"], summary["transition_trim_length"])
        self.assertAlmostEqual(first_connector["tension"], summary["transition_connect_tension"])
        self.assertEqual(first_connector["trim_length_expression"], "TL1")
        self.assertEqual(first_connector["tension_expression"], "TN1")
        self.assertAlmostEqual(second_connector["trim_length"], summary["transition_trim_length"])
        self.assertAlmostEqual(second_connector["tension"], summary["transition_connect_tension"])
        self.assertEqual(second_connector["trim_length_expression"], "TL1")
        self.assertEqual(second_connector["tension_expression"], "TN1")
        trimmed_operations = [
            operation
            for operation in preview["operations"]
            if operation.get("operation") == "create_trimmed_curve_path"
        ]
        self.assertEqual(len(trimmed_operations), 4)
        self.assertEqual(
            [operation["source_curve"] for operation in trimmed_operations],
            [
                "spring_start_end_path",
                "spring_working_path",
                "spring_start_end_to_working_curve2_local_path",
                "spring_finish_end_path",
            ],
        )
        self.assertEqual(
            [operation["offset_type"] for operation in trimmed_operations],
            [2, 2, 2, 2],
        )
        self.assertEqual(
            [operation["offset_expression"] for operation in trimmed_operations],
            ["TL1", "TL1", "TL1", "TL1"],
        )
        self.assertTrue(
            all(operation["point_operation_variable_bindings"] for operation in trimmed_operations)
        )
        self.assertTrue(
            all(
                "Смещение (длина сегмента)"
                in operation["point_operation_variable_bindings"][0]["parameter_note_aliases"]
                for operation in trimmed_operations
            )
        )
        connector_operations = [
            operation
            for operation in preview["operations"]
            if operation.get("operation") == "create_connect_curve_path"
        ]
        self.assertEqual(len(connector_operations), 2)
        self.assertEqual(
            connector_operations[0]["curve1"],
            "spring_start_end_to_working_curve1_local_path",
        )
        self.assertAlmostEqual(
            connector_operations[0]["tension"],
            summary["transition_connect_tension"],
        )
        self.assertEqual(connector_operations[0]["tension_expression"], "TN1")
        self.assertTrue(connector_operations[0]["operation_variable_bindings"])
        self.assertEqual(
            connector_operations[0]["curve2"],
            "spring_start_end_to_working_curve2_local_path",
        )
        self.assertEqual(
            connector_operations[1]["curve1"],
            "spring_working_to_finish_end_curve1_local_path",
        )
        self.assertEqual(
            connector_operations[1]["curve2"],
            "spring_working_to_finish_end_curve2_local_path",
        )
        self.assertAlmostEqual(
            connector_operations[1]["tension"],
            summary["transition_connect_tension"],
        )
        self.assertEqual(connector_operations[1]["tension_expression"], "TN1")
        self.assertTrue(connector_operations[1]["operation_variable_bindings"])
        boss_evolution = next(
            operation
            for operation in preview["operations"]
            if operation.get("operation") == "boss_evolution"
        )
        self.assertEqual(boss_evolution["path_count"], 5)

    def test_preview_compression_spring_transition_tuning_tracks_diameter_and_pitch(self) -> None:
        small_diameter = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 15,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "transition_fillet_radius": 1.5,
            },
        )
        baseline = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "transition_fillet_radius": 1.5,
            },
        )
        large_diameter = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 50,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "transition_fillet_radius": 1.5,
            },
        )
        reduced_pitch = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 40,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "transition_fillet_radius": 1.5,
            },
        )

        self.assertAlmostEqual(small_diameter["summary"]["transition_connect_tension"], 0.0)
        self.assertGreater(
            baseline["summary"]["transition_trim_length"],
            small_diameter["summary"]["transition_trim_length"],
        )
        self.assertGreater(
            large_diameter["summary"]["transition_trim_length"],
            baseline["summary"]["transition_trim_length"],
        )
        self.assertGreater(
            large_diameter["summary"]["transition_connect_tension"],
            baseline["summary"]["transition_connect_tension"],
        )
        self.assertLess(
            reduced_pitch["summary"]["transition_connect_tension"],
            baseline["summary"]["transition_connect_tension"],
        )

    def test_preview_compression_spring_segment_anchor_rotation_tracks_start_phase(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "start_phase_degrees": 0,
                "turn_direction": "right",
            },
        )
        spiral_operations = [
            operation
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        self.assertEqual(
            [operation["orientation_angle_degrees"] for operation in spiral_operations],
            [0.0, 0.0, 0.0],
        )
        self.assertEqual(spiral_operations[0]["anchor_rotation_expression"], "90")
        self.assertIn("(90.0)", str(spiral_operations[1]["anchor_rotation_expression"]))
        self.assertIn("(90.0)", str(spiral_operations[2]["anchor_rotation_expression"]))

    def test_preview_compression_spring_right_hand_transfers_half_turn_to_later_segments(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "start_phase_degrees": -90,
                "turn_direction": "right",
            },
        )
        spiral_operations = [
            operation
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        self.assertEqual(spiral_operations[0]["role"], "start_end")
        self.assertIsNone(spiral_operations[0]["anchor_rotation_expression"])
        self.assertIn("360.0", str(spiral_operations[1]["anchor_rotation_expression"]))
        self.assertIn("360.0", str(spiral_operations[2]["anchor_rotation_expression"]))
        self.assertNotIn("180.0", str(spiral_operations[1]["anchor_rotation_expression"]))
        self.assertNotIn("180.0", str(spiral_operations[2]["anchor_rotation_expression"]))
        self.assertIn("+ (360 * (N21))", str(spiral_operations[1]["anchor_rotation_expression"]))

    def test_preview_compression_spring_without_ground_has_empty_trim_plan(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 48,
                "working_turns": 6,
            },
        )

        trim_plan = preview["params"]["ground_trim_plan"]
        self.assertFalse(trim_plan["enabled"])
        self.assertEqual(trim_plan["status"], "not_requested")
        self.assertEqual(trim_plan["operations"], [])

    def test_preview_compression_spring_ground_trim_plan_uses_per_end_standard_variables(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.75,
                "start_ground_turns": 0.5,
                "finish_ground_turns": 0.25,
            },
        )

        trim_plan = preview["params"]["ground_trim_plan"]
        self.assertTrue(trim_plan["enabled"])
        self.assertEqual(trim_plan["bridge_action_required"], "section_by_surface")
        self.assertEqual(trim_plan["height_reference"], "centerline_start_to_centerline_finish")
        self.assertEqual(trim_plan["standards_link_variables"]["start_ground_turns"], "N31")
        self.assertEqual(trim_plan["standards_link_variables"]["finish_ground_turns"], "N32")
        self.assertEqual(trim_plan["standards_link_variables"]["wire_diameter"], "WD1")
        self.assertEqual(trim_plan["standards_link_variables"]["height"], "H1")
        self.assertEqual(trim_plan["standards_link_variables"]["start_end_turns"], "N21")
        self.assertEqual(trim_plan["standards_link_variables"]["finish_end_turns"], "N22")
        self.assertEqual(trim_plan["operations"][0]["surface_reference"], "start_end_to_working_joint_plane")
        self.assertEqual(trim_plan["operations"][0]["offset_expression"], "-((N21 - N31 + 0.5) * WD1)")
        self.assertEqual(trim_plan["operations"][1]["surface_reference"], "working_to_finish_end_joint_plane")
        self.assertEqual(trim_plan["operations"][1]["offset_expression"], "((N22 - N32 + 0.5) * WD1)")

    def test_preview_compression_spring_explicit_zero_ground_depth_disables_trim_plan(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 48,
                "working_turns": 5.5,
                "start_end_turns": 1.0,
                "finish_end_turns": 1.0,
                "start_ground_turns": 0.0,
                "finish_ground_turns": 0.0,
            },
        )

        trim_plan = preview["params"]["ground_trim_plan"]
        self.assertFalse(trim_plan["enabled"])
        self.assertEqual(trim_plan["operations"], [])

    def test_preview_compression_spring_zero_ground_depth_can_disable_one_trim_side(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 48,
                "working_turns": 5.5,
                "start_end_turns": 1.0,
                "finish_end_turns": 1.0,
                "start_ground_turns": 0.0,
                "finish_ground_turns": 0.5,
            },
        )

        trim_plan = preview["params"]["ground_trim_plan"]
        self.assertTrue(trim_plan["enabled"])
        self.assertEqual([operation["role"] for operation in trim_plan["operations"]], ["finish_ground_trim"])

    def test_preview_compression_spring_standard_length_derives_centerline_height(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "standard_length": 50,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.75,
                "start_ground_turns": 0.5,
                "finish_ground_turns": 0.25,
            },
        )

        self.assertEqual(preview["params"]["standard_length"], 50)
        self.assertEqual(preview["params"]["height"], 49)
        length_model = preview["params"]["length_model"]
        self.assertEqual(length_model["source"], "standard_length")
        self.assertEqual(length_model["height_reference"], "ground_cut_to_ground_cut")
        self.assertEqual(
            length_model["centerline_height_expression"],
            "L1 - WD1 + ((N31 + N32) * WD1)",
        )

    def test_preview_compression_spring_accepts_L_alias_for_standard_length(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "L": 52,
                "working_turns": 5.5,
            },
        )

        self.assertEqual(preview["params"]["standard_length"], 52)
        self.assertEqual(preview["params"]["height"], 48)
        self.assertEqual(preview["params"]["length_model"]["centerline_height_expression"], "L1 - WD1")

    def test_preview_compression_spring_left_hand_segment_anchor_rotation_flips_direction(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "start_phase_degrees": -90,
                "turn_direction": "left",
            },
        )
        spiral_operations = [
            operation
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        self.assertEqual(
            [operation["orientation_angle_degrees"] for operation in spiral_operations],
            [0.0, 0.0, 0.0],
        )
        self.assertIn("(0.0) - (360 * (N21))", str(spiral_operations[1]["anchor_rotation_expression"]))
        self.assertNotIn("+ (360 * (N21))", str(spiral_operations[1]["anchor_rotation_expression"]))
        self.assertIn("- (360 * (", str(spiral_operations[2]["anchor_rotation_expression"]))
        self.assertIn("N21", str(spiral_operations[2]["anchor_rotation_expression"]))
        self.assertIn("H1", str(spiral_operations[2]["anchor_rotation_expression"]))
        self.assertIn("WD1", str(spiral_operations[2]["anchor_rotation_expression"]))
        self.assertIn("P1", str(spiral_operations[2]["anchor_rotation_expression"]))
        self.assertNotIn("N1", str(spiral_operations[2]["anchor_rotation_expression"]))

    def test_preview_compression_spring_rejects_ground_turns_above_end_turns(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"compression_spring ground_turns_per_side cannot exceed end_turns_per_side",
        ):
            preview_part_scenario(
                "compression_spring",
                {
                    "mean_diameter": 30,
                    "wire_diameter": 4,
                    "free_length": 54,
                    "working_turns": 5.5,
                    "end_turns_per_side": 0.5,
                    "ground_turns_per_side": 0.75,
                },
            )

    def test_normalize_compression_spring_v1_backfills_per_end_contract(self) -> None:
        normalized = normalize_compression_spring_params(
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "end_turns_per_side": 0.75,
                "ground_turns_per_side": 0.5,
            }
        )
        self.assertEqual(normalized["end_contract_mode"], "v1_symmetric")
        self.assertEqual(normalized["end_projection_mode"], "projected_to_v1_symmetric")
        self.assertEqual(normalized["start_end_turns"], 0.75)
        self.assertEqual(normalized["finish_end_turns"], 0.75)
        self.assertEqual(normalized["start_ground_turns"], 0.5)
        self.assertEqual(normalized["finish_ground_turns"], 0.5)
        self.assertEqual(normalized["start_end_kind"], "closed_ground")
        self.assertEqual(normalized["finish_end_kind"], "closed_ground")

    def test_normalize_compression_spring_accepts_symmetric_v2_projection(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.75,
                "start_ground_turns": 0.5,
                "finish_ground_turns": 0.5,
            },
        )
        self.assertEqual(preview["params"]["end_contract_mode"], "v2_per_end")
        self.assertEqual(preview["params"]["end_projection_mode"], "projected_to_v1_symmetric")
        self.assertEqual(preview["params"]["start_end_turns"], 0.75)
        self.assertEqual(preview["params"]["finish_end_turns"], 0.75)
        self.assertEqual(preview["params"]["start_ground_turns"], 0.5)
        self.assertEqual(preview["params"]["finish_ground_turns"], 0.5)
        self.assertEqual(preview["params"]["start_end_kind"], "closed_ground")
        self.assertEqual(preview["params"]["finish_end_kind"], "closed_ground")
        self.assertEqual(preview["summary"]["end_turns_per_side"], 0.75)
        self.assertEqual(preview["summary"]["ground_turns_per_side"], 0.5)
        self.assertEqual(
            [
                operation["role"]
                for operation in preview["operations"]
                if operation.get("operation") == "create_spiral_path"
            ],
            ["start_end", "working", "finish_end"],
        )

    def test_preview_compression_spring_rejects_mixed_v1_and_v2_end_fields(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"compression_spring cannot mix V1 per-side end fields with V2 per-end end fields",
        ):
            preview_part_scenario(
                "compression_spring",
                {
                    "mean_diameter": 30,
                    "wire_diameter": 4,
                    "free_length": 54,
                    "working_turns": 5.5,
                    "end_turns_per_side": 0.75,
                    "start_end_turns": 0.75,
                },
            )

    def test_preview_compression_spring_rejects_start_ground_above_start_end(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"compression_spring start_ground_turns cannot exceed start_end_turns",
        ):
            preview_part_scenario(
                "compression_spring",
                {
                    "mean_diameter": 30,
                    "wire_diameter": 4,
                    "free_length": 54,
                    "working_turns": 5.5,
                    "start_end_turns": 0.5,
                    "finish_end_turns": 0.5,
                    "start_ground_turns": 0.75,
                    "finish_ground_turns": 0.5,
                },
            )

    def test_preview_compression_spring_rejects_finish_ground_above_finish_end(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"compression_spring finish_ground_turns cannot exceed finish_end_turns",
        ):
            preview_part_scenario(
                "compression_spring",
                {
                    "mean_diameter": 30,
                    "wire_diameter": 4,
                    "free_length": 54,
                    "working_turns": 5.5,
                    "start_end_turns": 0.5,
                    "finish_end_turns": 0.5,
                    "start_ground_turns": 0.5,
                    "finish_ground_turns": 0.75,
                },
            )

    def test_preview_compression_spring_v2_symmetric_summary_exposes_per_end_blocks(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.75,
                "start_ground_turns": 0.5,
                "finish_ground_turns": 0.5,
            },
        )

        summary = preview["summary"]
        self.assertEqual(summary["end_contract_mode"], "v2_per_end")
        self.assertEqual(summary["end_projection_mode"], "projected_to_v1_symmetric")
        self.assertEqual(summary["start_end_summary"]["end_turns"], 0.75)
        self.assertEqual(summary["finish_end_summary"]["end_turns"], 0.75)
        self.assertEqual(summary["start_end_summary"]["ground_turns"], 0.5)
        self.assertEqual(summary["finish_end_summary"]["ground_turns"], 0.5)
        self.assertEqual(summary["start_end_summary"]["label"], "closed-ground")
        self.assertEqual(summary["finish_end_summary"]["label"], "closed-ground")
        self.assertEqual(summary["start_end_summary"]["segment_names"], ["spring_start_end_path"])
        self.assertEqual(summary["finish_end_summary"]["segment_names"], ["spring_finish_end_path"])
        self.assertEqual(summary["start_end_summary"]["support_selector_names"], ["start_support_point"])
        self.assertEqual(summary["finish_end_summary"]["support_selector_names"], ["finish_support_point"])
        self.assertFalse(summary["start_end_summary"]["grounded_geometry_signal"])
        self.assertFalse(summary["finish_end_summary"]["grounded_geometry_signal"])

    def test_preview_compression_spring_v2_symmetric_interface_exposes_distinct_per_end_variable_names(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.75,
                "start_ground_turns": 0.5,
                "finish_ground_turns": 0.5,
                "parameter_prefix": "spg01",
            },
        )

        parameters = preview["interface"]["parameters"]
        self.assertEqual(parameters["driving_end_turn_count_per_side"], "")
        self.assertEqual(parameters["driving_ground_turn_count_per_side"], "")
        self.assertEqual(parameters["driving_start_end_turn_count"], "SPG01_N21")
        self.assertEqual(parameters["driving_finish_end_turn_count"], "SPG01_N22")
        self.assertEqual(parameters["driving_start_ground_turn_count"], "SPG01_N31")
        self.assertEqual(parameters["driving_finish_ground_turn_count"], "SPG01_N32")
        self.assertEqual(preview["params"]["start_end_turns_expression"], "SPG01_N21")
        self.assertEqual(preview["params"]["finish_end_turns_expression"], "SPG01_N22")
        self.assertEqual(preview["params"]["start_ground_turns_expression"], "SPG01_N31")
        self.assertEqual(preview["params"]["finish_ground_turns_expression"], "SPG01_N32")
        self.assertIsNone(preview["params"]["end_turns_expression"])
        self.assertIsNone(preview["params"]["ground_turns_expression"])

        spiral_operations = [
            operation
            for operation in preview["operations"]
            if operation.get("operation") == "create_spiral_path"
        ]
        self.assertEqual(
            spiral_operations[0]["operation_variable_bindings"][2]["expression"],
            "SPG01_N21 * SPG01_WD1",
        )
        self.assertEqual(
            spiral_operations[1]["start_offset_expression"],
            "SPG01_N21 * SPG01_WD1",
        )
        self.assertEqual(
            spiral_operations[1]["operation_variable_bindings"][2]["expression"],
            "SPG01_H1 - ((SPG01_N21 * SPG01_WD1) + (SPG01_N22 * SPG01_WD1))",
        )
        self.assertEqual(
            spiral_operations[2]["operation_variable_bindings"][2]["expression"],
            "SPG01_N22 * SPG01_WD1",
        )

    def test_preview_compression_spring_v2_asymmetric_summary_reports_native_v2(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.0,
                "start_ground_turns": 0.0,
                "finish_ground_turns": 0.0,
            },
        )

        summary = preview["summary"]
        self.assertEqual(summary["end_contract_mode"], "v2_per_end")
        self.assertEqual(summary["end_projection_mode"], "native_v2")
        self.assertEqual(summary["start_end_summary"]["label"], "closed")
        self.assertEqual(summary["finish_end_summary"]["label"], "open")
        self.assertTrue(summary["start_end_summary"]["has_end_segment"])
        self.assertFalse(summary["finish_end_summary"]["has_end_segment"])
        self.assertEqual(
            [
                operation["role"]
                for operation in preview["operations"]
                if operation.get("operation") == "create_spiral_path"
            ],
            ["start_end", "working"],
        )

    def test_preview_compression_spring_v2_adds_unconditional_selector_points(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.0,
                "finish_end_turns": 0.0,
                "start_ground_turns": 0.0,
                "finish_ground_turns": 0.0,
            },
        )

        selector_keys = {
            "start_tip_point",
            "finish_tip_point",
            "start_body_entry_point",
            "finish_body_exit_point",
        }
        self.assertEqual(set(preview["selectors"].keys()), selector_keys)
        self.assertEqual(
            set(preview["interface"]["anchors"]["selector_points"].keys()),
            selector_keys,
        )

    def test_preview_compression_spring_v2_support_points_are_conditional(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.0,
                "start_ground_turns": 0.0,
                "finish_ground_turns": 0.0,
            },
        )

        self.assertIn("start_support_point", preview["selectors"])
        self.assertNotIn("finish_support_point", preview["selectors"])
        self.assertIn("start_support_point", preview["interface"]["anchors"]["selector_points"])
        self.assertNotIn("finish_support_point", preview["interface"]["anchors"]["selector_points"])

    def test_preview_compression_spring_v2_point_outputs_match_selector_names(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.0,
                "start_ground_turns": 0.0,
                "finish_ground_turns": 0.0,
            },
        )

        for selector_name, origin in preview["selectors"].items():
            self.assertIn(selector_name, preview["interface"]["outputs"])
            output = preview["interface"]["outputs"][selector_name]
            self.assertEqual(output["type"], "point")
            self.assertEqual(output["name"], selector_name)
            self.assertEqual(output["selector"], selector_name)
            self.assertEqual(output["origin"], origin)

    def test_preview_compression_spring_v2_ground_contact_outputs_stay_absent(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.75,
                "start_ground_turns": 0.5,
                "finish_ground_turns": 0.5,
            },
        )

        self.assertNotIn("start_ground_contact_point", preview["selectors"])
        self.assertNotIn("finish_ground_contact_point", preview["selectors"])
        self.assertNotIn("start_ground_contact_point", preview["interface"]["outputs"])
        self.assertNotIn("finish_ground_contact_point", preview["interface"]["outputs"])
        self.assertFalse(preview["summary"]["start_end_summary"]["grounded_geometry_signal"])
        self.assertFalse(preview["summary"]["finish_end_summary"]["grounded_geometry_signal"])

    def test_preview_compression_spring_v2_interface_outputs_keep_v1_baseline(self) -> None:
        preview = preview_part_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.0,
                "start_ground_turns": 0.0,
                "finish_ground_turns": 0.0,
            },
        )

        self.assertIn("body", preview["interface"]["outputs"])
        self.assertIn("axis", preview["interface"]["outputs"])
        self.assertIn("spiral_path", preview["interface"]["outputs"])

    def test_preview_compression_spring_rejects_interfering_pitch(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"compression_spring requires pitch greater than or equal to wire_diameter",
        ):
            preview_part_scenario(
                "compression_spring",
                {
                    "mean_diameter": 30,
                    "wire_diameter": 4,
                    "free_length": 18,
                    "working_turns": 4,
                    "end_turns_per_side": 0.5,
                },
            )

    def test_create_compression_spring_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)
        result = adapter.create_part_from_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "height": 48,
                "turns": 6,
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-spring.m3d",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(runner.calls[0][0], "create_part_from_scenario")
        self.assertEqual(runner.calls[0][1]["scenario"], "compression_spring")
        self.assertEqual(runner.calls[0][1]["params"]["pitch"], 8.0)
        self.assertEqual(runner.calls[0][1]["params"]["total_turns"], 6.0)
        self.assertEqual(runner.calls[0][1]["params"]["profile_sketch_target_state"], "fully_defined")
        self.assertEqual(runner.calls[0][1]["params"]["mean_diameter_expression"], "(D1) - (WD1)")
        self.assertEqual(
            runner.calls[0][1]["params"]["profile_sketch_dimensions"][0]["expression"],
            "((D1) - (WD1)) / 2",
        )
        self.assertEqual(
            runner.calls[0][1]["params"]["profile_sketch_dimensions"][1],
            {
                "kind": "line_length",
                "target": "profile_radius_ref",
                "expression": "(WD1) / 2",
                "driving": True,
                "placement_index": 1,
            },
        )
        self.assertEqual(result["preview"]["scenario"], "compression_spring")

    def test_create_compression_spring_from_scenario_preserves_v2_per_end_variable_vocabulary(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)
        result = adapter.create_part_from_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "free_length": 54,
                "working_turns": 5.5,
                "start_end_turns": 0.75,
                "finish_end_turns": 0.75,
                "start_ground_turns": 0.5,
                "finish_ground_turns": 0.5,
                "parameter_prefix": "spg01",
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-spring-v2.m3d",
        )
        self.assertTrue(result["ok"])
        params = runner.calls[0][1]["params"]
        variable_names = {
            item["kind"]: item["name"]
            for item in params["variable_plan"]
        }
        self.assertEqual(params["end_contract_mode"], "v2_per_end")
        self.assertEqual(params["end_projection_mode"], "projected_to_v1_symmetric")
        self.assertEqual(variable_names["driving_start_end_turn_count"], "SPG01_N21")
        self.assertEqual(variable_names["driving_finish_end_turn_count"], "SPG01_N22")
        self.assertEqual(variable_names["driving_start_ground_turn_count"], "SPG01_N31")
        self.assertEqual(variable_names["driving_finish_ground_turn_count"], "SPG01_N32")
        self.assertNotIn("driving_end_turn_count_per_side", variable_names)
        self.assertNotIn("driving_ground_turn_count_per_side", variable_names)

    def test_create_part_from_scenario_passes_partial_save_flags(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        adapter.create_part_from_scenario(
            "compression_spring",
            {
                "mean_diameter": 30,
                "wire_diameter": 4,
                "height": 48,
                "turns": 6,
            },
            output_path=r"C:\\Temp\\kompas-mcp\\unit-spring-partial.m3d",
            save_partial_on_error=True,
            return_partial_result_on_error=True,
        )

        payload = runner.calls[0][1]
        self.assertTrue(payload["params"]["save_partial_on_error"])
        self.assertTrue(payload["params"]["return_partial_result_on_error"])

    def test_workflow_with_compression_spring_is_live_supported(self) -> None:
        params = {
            "operations": [
                {
                    "id": "spring01",
                    "scenario": "compression_spring",
                    "params": {
                        "mean_diameter": 30,
                        "wire_diameter": 4,
                        "height": 48,
                        "turns": 6,
                    },
                }
            ]
        }
        preview = preview_part_scenario("workflow", params)
        self.assertTrue(preview["params"]["live_supported"])
        self.assertEqual(preview["summary"]["creation_status"], "available")

        adapter = KompasAdapter(runner=FakeRunner())
        result = adapter.create_part_from_scenario(
            "workflow",
            params,
            output_path=r"C:\\Temp\\kompas-mcp\\unit-spring-workflow.m3d",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["preview"]["summary"]["creation_status"], "available")

    def test_preview_workflow_supports_external_conical_step_operation(self) -> None:
        preview = preview_part_scenario(
            "workflow",
            {
                "operations": [
                    {
                        "id": "lcs01",
                        "scenario": "lcs",
                        "params": {"mode": "global", "lcs_name": "LCS01", "origin": [60, 8, 0]},
                    },
                    {
                        "id": "cone01",
                        "scenario": "external_conical_step",
                        "params": {
                            "length": 24,
                            "start_diameter": 22,
                            "end_diameter": 14,
                            "placement": {"base": {"reference": {"ref": "lcs01.lcs"}}},
                        },
                    },
                ],
                "exports": {"cone_face": "cone01.end_face"},
            },
        )

        operations = preview["params"]["operations"]
        self.assertEqual(operations[1]["scenario"], "external_conical_step")
        self.assertEqual(operations[1]["bindings"]["placement_operation"], "lcs01")
        self.assertEqual(operations[1]["params"]["placement"]["base"]["reference"]["output_ref"], "lcs01.lcs")
        self.assertEqual(preview["interface"]["outputs"]["cone_face"]["selector"], "end_face")

    def test_create_lcs_object_from_scenario_passes_selector_reference(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "lcs",
            {
                "mode": "object",
                "lcs_name": "LCS_TAIL",
                "reference": {
                    "selector": "far_end_face",
                    "source_scenario": "stepped_shaft",
                    "source_params": {"steps": [{"length": 12, "diameter": 6}]},
                },
            },
            output_path=r"C:\Temp\kompas-mcp\unit-lcs-object.m3d",
            close_after_save=True,
        )

        self.assertTrue(result["ok"])
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "lcs")
        self.assertEqual(payload["params"]["reference"]["selector"], "far_end_face")

    def test_create_point_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "point",
            {"point_name": "PT1", "origin": [1, 2, 3], "close_after_save": False},
            output_path=r"C:\Temp\kompas-mcp\unit-point.m3d",
        )

        self.assertTrue(result["ok"])
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "point")
        self.assertEqual(payload["params"]["origin"], [1.0, 2.0, 3.0])
        self.assertEqual(payload["params"]["point_name"], "PT1")

    def test_create_offset_point_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "point",
            {
                "mode": "offset_from_point",
                "point_name": "PT_ECC",
                "reference": {"name": "PT_BASE", "origin": [40, 0, 0]},
                "offset": {"dx": 0, "dy": 8, "dz": 0},
            },
            output_path=r"C:\Temp\kompas-mcp\unit-offset-point.m3d",
        )

        self.assertTrue(result["ok"])
        payload = runner.calls[0][1]
        self.assertEqual(payload["params"]["mode"], "offset_from_point")
        self.assertEqual(payload["params"]["reference_origin"], [40.0, 0.0, 0.0])
        self.assertEqual(payload["params"]["offset"], [0.0, 8.0, 0.0])
        self.assertEqual(payload["params"]["origin"], [40.0, 8.0, 0.0])

    def test_create_center_point_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "point",
            {
                "mode": "center_of_object",
                "point_name": "PT_CENTER",
                "reference": {
                    "selector": "far_end_face",
                    "source_scenario": "stepped_shaft",
                    "source_params": {
                        "steps": [
                            {"length": 20, "diameter": 10},
                            {"length": 30, "diameter": 16},
                            {"length": 10, "diameter": 12},
                        ]
                    },
                },
            },
            output_path=r"C:\Temp\kompas-mcp\unit-center-point.m3d",
        )

        self.assertTrue(result["ok"])
        payload = runner.calls[0][1]
        self.assertEqual(payload["params"]["mode"], "center_of_object")
        self.assertEqual(payload["params"]["reference"]["selector"], "far_end_face")
        self.assertEqual(payload["params"]["reference"]["source_scenario"], "stepped_shaft")
        self.assertEqual(payload["params"]["offset"], [0.0, 0.0, 0.0])
        self.assertEqual(payload["params"]["origin"], [60.0, 0.0, 0.0])

    def test_create_lcs_from_scenario_passes_normalized_params(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "local-coordinate-system",
            {
                "mode": "point",
                "lcs_name": "LCS1",
                "reference": {"name": "PT1", "origin": [1, 2, 3]},
                "rotation": {"rz": 45},
            },
            output_path=r"C:\Temp\kompas-mcp\unit-lcs.m3d",
        )

        self.assertTrue(result["ok"])
        payload = runner.calls[0][1]
        self.assertEqual(payload["scenario"], "lcs")
        self.assertEqual(payload["params"]["mode"], "point")
        self.assertEqual(payload["params"]["reference_origin"], [1.0, 2.0, 3.0])
        self.assertEqual(payload["params"]["rotation"], {"rx": 0.0, "ry": 0.0, "rz": 45.0})

    def test_create_object_lcs_from_scenario_passes_system_reference(self) -> None:
        runner = FakeRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.create_part_from_scenario(
            "lcs",
            {
                "mode": "object",
                "lcs_name": "LCS_SYS",
                "reference": {"system_object": "origin"},
            },
            output_path=r"C:\Temp\kompas-mcp\unit-lcs-object.m3d",
        )

        self.assertTrue(result["ok"])
        payload = runner.calls[0][1]
        self.assertEqual(payload["params"]["mode"], "object")
        self.assertEqual(payload["params"]["reference"]["system_object"], "origin")

    def test_preview_accepts_sketch_line_style_options(self) -> None:
        preview = preview_part_scenario(
            "stepped_shaft",
            {
                "steps": [{"length": 10, "diameter": 8}],
                "sketch": {"axis_line_style": "axial", "profile_line_style": "thin"},
            },
        )

        self.assertEqual(preview["params"]["sketch"]["axis_line_style"], 3)
        self.assertEqual(preview["params"]["sketch"]["profile_line_style"], 2)
        self.assertEqual(preview["operations"][3]["line_style"], 3)
        self.assertEqual(preview["operations"][4]["line_style"], 2)

    def test_preview_supports_diameter_dimension_display(self) -> None:
        preview = preview_part_scenario(
            "stepped_shaft",
            {
                "steps": [{"length": 10, "diameter": 8}],
                "sketch": {"dimension_display": "diameter"},
            },
        )

        dimensions = preview["operations"][6]["dimensions"]
        radial = next(dimension for dimension in dimensions if dimension["kind"] == "axis_distance")
        self.assertEqual(preview["params"]["sketch"]["dimension_display"], "diameter")
        self.assertEqual(preview["summary"]["dimension_display"], "diameter")
        self.assertEqual(radial["name"], "R1")
        self.assertEqual(radial["expression"], "D1 / 2")
        self.assertEqual(radial["display_mode"], "diameter")
        self.assertTrue(radial["native_break"])
        self.assertEqual(radial["display_value"], 8.0)

    def test_preview_supports_parameter_prefix(self) -> None:
        preview = preview_part_scenario(
            "stepped_shaft",
            {
                "parameter_prefix": "rev_01",
                "steps": [{"length": 10, "diameter": 8}],
            },
        )

        variables = preview["operations"][1]["variables"]
        dimensions = preview["operations"][6]["dimensions"]
        radial = next(dimension for dimension in dimensions if dimension["kind"] == "axis_distance")
        linear = next(dimension for dimension in dimensions if dimension["kind"] == "line_length")
        self.assertEqual(preview["params"]["parameter_prefix"], "REV_01")
        self.assertEqual(preview["summary"]["parameter_prefix"], "REV_01")
        self.assertEqual(variables[0]["name"], "REV_01_D1")
        self.assertEqual(variables[0]["note"], "Stepped shaft [REV_01] | step-1 | Diameter REV_01_D1")
        self.assertEqual(variables[1]["name"], "REV_01_L1")
        self.assertEqual(variables[1]["note"], "Stepped shaft [REV_01] | step-1 | Length REV_01_L1")
        self.assertEqual(linear["name"], "REV_01_SKL1")
        self.assertEqual(linear["variable"], "REV_01_SKL1")
        self.assertEqual(linear["expression"], "REV_01_L1")
        self.assertEqual(radial["name"], "REV_01_R1")
        self.assertEqual(radial["variable"], "REV_01_R1")
        self.assertEqual(radial["expression"], "REV_01_D1 / 2")
        self.assertEqual(preview["interface"]["parameter_namespace"], "REV_01")
        self.assertEqual(preview["summary"]["operation_label"], "Stepped shaft [REV_01]")
        self.assertEqual(preview["interface"]["operation_label"], "Stepped shaft [REV_01]")
        self.assertEqual(preview["interface"]["parameters"]["driving_diameters"], ["REV_01_D1"])
        self.assertEqual(preview["interface"]["parameters"]["driving_lengths"], ["REV_01_L1"])

    def test_preview_supports_translated_placement(self) -> None:
        preview = preview_part_scenario(
            "stepped_shaft",
            {
                "placement": {"mode": "csys", "origin": [100, 25]},
                "steps": [{"length": 10, "diameter": 8}],
            },
        )

        profile = preview["operations"][4]["profile_points"]
        axis = preview["operations"][3]
        self.assertEqual(preview["params"]["placement"]["mode"], "csys")
        self.assertEqual(preview["summary"]["placement_origin"], [100.0, 25.0])
        self.assertEqual(preview["summary"]["placement_base_mode"], "csys")
        self.assertEqual(preview["summary"]["placement_base_origin"], [100.0, 25.0])
        self.assertEqual(preview["summary"]["placement_local_offset"], [0.0, 0.0])
        self.assertEqual(axis["start"], [100.0, 25.0])
        self.assertEqual(axis["end"], [110.0, 25.0])
        self.assertEqual(profile[0], [100.0, 25.0])
        self.assertEqual(profile[1], [100.0, 29.0])
        self.assertEqual(preview["interface"]["anchors"]["axis_start"], [100.0, 25.0])
        self.assertEqual(preview["interface"]["anchors"]["axis_end"], [110.0, 25.0])
        self.assertEqual(preview["interface"]["placement_contract"]["effective_origin"], [100.0, 25.0])

    def test_preview_supports_base_csys_with_local_offset(self) -> None:
        preview = preview_part_scenario(
            "stepped_shaft",
            {
                "placement": {
                    "base": {
                        "mode": "csys",
                        "name": "TAIL-CSYS-01",
                        "origin": [100, 25],
                    },
                    "local_offset": [0, 12],
                },
                "steps": [{"length": 10, "diameter": 8}],
            },
        )

        profile = preview["operations"][4]["profile_points"]
        axis = preview["operations"][3]
        self.assertEqual(preview["params"]["placement"]["mode"], "csys")
        self.assertEqual(preview["params"]["placement"]["base"]["mode"], "csys")
        self.assertEqual(preview["summary"]["placement_origin"], [100.0, 37.0])
        self.assertEqual(preview["summary"]["placement_base_origin"], [100.0, 25.0])
        self.assertEqual(preview["summary"]["placement_local_offset"], [0.0, 12.0])
        self.assertEqual(axis["start"], [100.0, 37.0])
        self.assertEqual(axis["end"], [110.0, 37.0])
        self.assertEqual(profile[0], [100.0, 37.0])
        self.assertEqual(profile[1], [100.0, 41.0])
        self.assertEqual(preview["interface"]["placement_contract"]["base_mode"], "csys")
        self.assertEqual(preview["interface"]["placement_contract"]["base_origin"], [100.0, 25.0])
        self.assertEqual(preview["interface"]["placement_contract"]["local_offset"], [0.0, 12.0])
        self.assertEqual(preview["interface"]["placement_contract"]["effective_origin"], [100.0, 37.0])

    def test_preview_supports_csys_ref_contract_with_resolved_origin(self) -> None:
        preview = preview_part_scenario(
            "stepped_shaft",
            {
                "placement": {
                    "base": {
                        "mode": "csys_ref",
                        "name": "PREV-END-CSYS",
                        "origin": [50, 10],
                        "reference": {
                            "feature": "REV01",
                            "anchor": "axis_end",
                        },
                    },
                    "local_offset": {"x": 0, "y": 6},
                },
                "steps": [{"length": 10, "diameter": 8}],
            },
        )

        self.assertEqual(preview["params"]["placement"]["mode"], "csys_ref")
        self.assertEqual(preview["summary"]["placement_base_mode"], "csys_ref")
        self.assertEqual(preview["summary"]["placement_base_origin"], [50.0, 10.0])
        self.assertEqual(preview["summary"]["placement_local_offset"], [0.0, 6.0])
        self.assertEqual(preview["summary"]["placement_origin"], [50.0, 16.0])
        self.assertEqual(
            preview["interface"]["placement_contract"]["reference"],
            {"feature": "REV01", "anchor": "axis_end"},
        )

    def test_preview_rejects_rotated_placement_axis_direction(self) -> None:
        with self.assertRaisesRegex(ValueError, "rotation is not supported yet"):
            preview_part_scenario(
                "stepped_shaft",
                {
                    "placement": {"mode": "csys", "origin": [10, 5], "axis_direction": [0, 1]},
                    "steps": [{"length": 10, "diameter": 8}],
                },
            )

    def test_preview_normalizes_known_material_alias(self) -> None:
        preview = preview_part_scenario(
            "stepped_shaft",
            {
                "material": "Steel 45",
                "steps": [{"length": 10, "diameter": 8}],
            },
        )

        self.assertEqual(preview["params"]["material"], "\u0421\u0442\u0430\u043b\u044c 45 \u0413\u041e\u0421\u0422 1050-2013")
        self.assertEqual(preview["params"]["density"], 7.85)
        self.assertTrue(preview["params"]["material_catalog_matched"])

    def test_line_style_aliases(self) -> None:
        self.assertEqual(normalize_line_style("axis"), 3)
        self.assertEqual(normalize_line_style("main"), 1)
        self.assertEqual(normalize_line_style(6), 6)


if __name__ == "__main__":
    unittest.main()
