from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any

from kompas_mcp.adapter import KompasAdapter


class PrimitiveWriteOperationTests(unittest.TestCase):
    def test_create_point3d_runs_between_snapshots_and_verifies_delta(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.create_point3d(document_id="doc-1", name="PT_A", origin=[1, 2, 3])

        self.assertEqual(runner.calls, [("create_point3d", {"document_id": "doc-1", "name": "PT_A", "origin": [1.0, 2.0, 3.0]})])
        self.assertTrue(result["ok"])
        self.assertTrue(result["execution"]["delta_verification_ran"])
        self.assertEqual(result["delta"]["summary"]["added_items"], 1)

    def test_create_point3d_rejects_malformed_origin_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.create_point3d(origin=[1, 2])

        self.assertEqual(runner.calls, [])

    def test_create_point3d_fails_when_readback_delta_does_not_show_added_item(self) -> None:
        runner = _NoDeltaRunner()
        adapter = KompasAdapter(runner)

        result = adapter.create_point3d(name="PT_A", origin=[1, 2, 3])

        self.assertFalse(result["ok"])
        self.assertEqual(result["delta"]["summary"]["added_items"], 0)
        self.assertIn("snapshot_delta_verification_ok", [failure["name"] for failure in result["failures"]])

    def test_create_sketch_line_segment_runs_between_snapshots_and_verifies_delta(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.create_sketch_line_segment(
            document_id="doc-1",
            name="SK_A",
            plane="XOY",
            start=[0, 0],
            end=[10, 5],
            line_style=1,
        )

        self.assertEqual(
            runner.calls,
            [
                (
                    "create_sketch_line_segment",
                    {
                        "document_id": "doc-1",
                        "name": "SK_A",
                        "plane": "XOY",
                        "start": [0.0, 0.0],
                        "end": [10.0, 5.0],
                        "line_style": 1,
                    },
                )
            ],
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["execution"]["delta_verification_ran"])
        self.assertEqual(result["delta"]["summary"]["added_items"], 1)

    def test_create_sketch_line_segment_rejects_malformed_points_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.create_sketch_line_segment(start=[1, 2, 3])

        self.assertEqual(runner.calls, [])

    def test_create_sketch_circle_runs_between_snapshots_and_verifies_delta(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.create_sketch_circle(
            document_id="doc-1",
            name="SK_C",
            plane="XOY",
            center=[5, 5],
            radius=12,
            line_style=1,
        )

        self.assertEqual(
            runner.calls,
            [
                (
                    "create_sketch_circle",
                    {
                        "document_id": "doc-1",
                        "name": "SK_C",
                        "plane": "XOY",
                        "center": [5.0, 5.0],
                        "radius": 12.0,
                        "line_style": 1,
                    },
                )
            ],
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["execution"]["delta_verification_ran"])
        self.assertEqual(result["delta"]["summary"]["added_items"], 1)

    def test_create_sketch_circle_rejects_invalid_radius_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.create_sketch_circle(radius=0)

        self.assertEqual(runner.calls, [])

    def test_create_sketch_rectangle_runs_between_snapshots_and_verifies_delta(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.create_sketch_rectangle(
            document_id="doc-1",
            name="SK_R",
            plane="XOY",
            corner1=[0, 0],
            corner2=[20, 10],
            line_style=1,
        )

        self.assertEqual(
            runner.calls,
            [
                (
                    "create_sketch_rectangle",
                    {
                        "document_id": "doc-1",
                        "name": "SK_R",
                        "plane": "XOY",
                        "corner1": [0.0, 0.0],
                        "corner2": [20.0, 10.0],
                        "line_style": 1,
                    },
                )
            ],
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["execution"]["delta_verification_ran"])
        self.assertEqual(result["delta"]["summary"]["added_items"], 1)

    def test_create_sketch_rectangle_rejects_malformed_corner_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.create_sketch_rectangle(corner1=[1, 2, 3])

        self.assertEqual(runner.calls, [])

    def test_create_sketch_entities_uses_explicit_create_new_target(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.create_sketch_entities(
            document_id="doc-1",
            name="SK_BATCH",
            plane="XOY",
            entities=[
                {"kind": "segment", "start": [0, 0], "end": [10, 0]},
                {"kind": "circle", "center": [5, 5], "radius": 2},
                {"kind": "point", "point": [1, 1]},
                {"kind": "polyline", "points": [[0, 0], [1, 0], [1, 1]], "closed": True},
                {"kind": "arc", "center": [5, 5], "radius": 3, "start": [8, 5], "end": [5, 8], "direction": True},
                {"kind": "ellipse", "center": [5, 5], "radius_x": 4, "radius_y": 2, "angle": 0},
            ],
        )

        self.assertEqual(
            runner.calls,
            [
                (
                    "create_sketch_entities",
                    {
                        "document_id": "doc-1",
                        "target": {"mode": "create_new_sketch", "name": "SK_BATCH", "plane": "XOY"},
                        "entities": [
                            {"kind": "segment", "start": [0.0, 0.0], "end": [10.0, 0.0], "line_style": 1},
                            {"kind": "circle", "center": [5.0, 5.0], "radius": 2.0, "line_style": 1},
                            {"kind": "point", "point": [1.0, 1.0], "line_style": 1},
                            {"kind": "polyline", "points": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]], "closed": True, "line_style": 1},
                            {
                                "kind": "arc",
                                "center": [5.0, 5.0],
                                "radius": 3.0,
                                "start": [8.0, 5.0],
                                "end": [5.0, 8.0],
                                "direction": True,
                                "line_style": 1,
                            },
                            {"kind": "ellipse", "center": [5.0, 5.0], "radius_x": 4.0, "radius_y": 2.0, "angle": 0.0, "line_style": 1},
                        ],
                    },
                )
            ],
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["execution"]["preflight_ran"])
        self.assertEqual(result["delta"]["summary"]["added_items"], 1)

    def test_create_sketch_entities_forwards_entity_ids_and_parameterization_payload(self) -> None:
        class _ParameterizationRunner(_FakeRunner):
            def call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
                result = super().call(action, payload)
                result["parameterization"] = {
                    "ok": True,
                    "constraints": {"live_status": "applied", "applied_count": 1},
                    "dimensions": {"live_status": "disabled"},
                }
                return result

        runner = _ParameterizationRunner()
        adapter = KompasAdapter(runner)

        result = adapter.create_sketch_entities(
            document_id="doc-1",
            entities=[{"kind": "segment", "id": "base", "role": "profile", "start": [0, 0], "end": [10, 0]}],
            constraints=[{"kind": "horizontal", "target": "base"}],
            sketch_options={"readback_geometry": True},
        )

        self.assertEqual(
            runner.calls[0][1],
            {
                "document_id": "doc-1",
                "target": {"mode": "create_new_sketch", "name": "SKETCH_BATCH_1", "plane": "XOY"},
                "entities": [{"kind": "segment", "start": [0.0, 0.0], "end": [10.0, 0.0], "line_style": 1, "entity_id": "base", "role": "profile"}],
                "constraints": [{"kind": "horizontal", "target": "base"}],
                "sketch_options": {"readback_geometry": True},
            },
        )
        self.assertEqual(result["parameterization"]["constraints"]["live_status"], "applied")

    def test_create_sketch_entities_rejects_ambiguous_target_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.create_sketch_entities(
                sketch_ref="100",
                create_new_sketch=True,
                entities=[{"kind": "segment", "start": [0, 0], "end": [10, 0]}],
            )

        self.assertEqual(runner.calls, [])

    def test_create_sketch_entities_uses_existing_sketch_target(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        adapter.create_sketch_entities(
            document_id="doc-1",
            sketch_ref=100,
            create_new_sketch=False,
            entities=[{"kind": "segment", "start": [0, 0], "end": [10, 0]}],
        )

        self.assertEqual(
            runner.calls,
            [
                (
                    "create_sketch_entities",
                    {
                        "document_id": "doc-1",
                        "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                        "entities": [{"kind": "segment", "start": [0.0, 0.0], "end": [10.0, 0.0], "line_style": 1}],
                    },
                )
            ],
        )

    def test_parameterize_sketch_forwards_existing_entity_refs(self) -> None:
        class _ParameterizationRunner(_FakeRunner):
            def call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
                result = super().call(action, payload)
                result["parameterization"] = {
                    "ok": True,
                    "constraints": {"live_status": "applied", "applied_count": 1},
                    "dimensions": {"live_status": "disabled"},
                }
                return result

        runner = _ParameterizationRunner()
        adapter = KompasAdapter(runner)

        result = adapter.parameterize_sketch(
            document_id="doc-1",
            sketch_ref=100,
            entities=[{"id": "base", "kind": "line", "reference": 201}],
            constraints=[{"kind": "horizontal", "target": "base"}],
            sketch_options={"readback_geometry": True},
        )

        self.assertEqual(
            runner.calls[0],
            (
                "parameterize_sketch",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "entities": [{"id": "base", "kind": "segment", "reference": "201"}],
                    "constraints": [{"kind": "horizontal", "target": "base"}],
                    "sketch_options": {"readback_geometry": True},
                },
            ),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["parameterization"]["constraints"]["live_status"], "applied")

    def test_parameterize_sketch_requires_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.parameterize_sketch(sketch_ref=100, entities=[{"id": "base", "kind": "segment", "reference": 201}])

        with self.assertRaises(ValueError):
            adapter.parameterize_sketch(
                sketch_ref=100,
                entities=[{"kind": "segment", "reference": 201}],
                constraints=[{"kind": "horizontal", "target": "base"}],
            )

        self.assertEqual(runner.calls, [])

    def test_list_sketch_entities_forwards_selector_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.list_sketch_entities(document_id="doc-1", sketch_ref=100, kinds=["line", "circle"], max_items=12)

        self.assertEqual(
            runner.calls[0],
            (
                "list_sketch_entities",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "max_items": 12,
                    "kinds": ["segment", "circle"],
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_inspect_sketch_full_forwards_selector_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.inspect_sketch_full(
            document_id="doc-1",
            sketch_ref=100,
            include_dimensions=False,
            include_constraints=True,
            max_items=12,
        )

        self.assertEqual(
            runner.calls[0],
            (
                "inspect_sketch_full",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "include_dimensions": False,
                    "include_constraints": True,
                    "include_diagnostics": True,
                    "max_items": 12,
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_list_sketch_entities_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.list_sketch_entities(sketch_ref=100, kinds=["spline"])
        with self.assertRaises(ValueError):
            adapter.list_sketch_entities(kinds=["segment"])
        with self.assertRaises(ValueError):
            adapter.list_sketch_entities(sketch_ref=100, max_items=0)

        self.assertEqual(runner.calls, [])

    def test_list_sketches_forwards_filter_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.list_sketches(document_id="doc-1", name_contains="base", max_items=12, include_entity_counts=True)

        self.assertEqual(
            runner.calls[0],
            (
                "list_sketches",
                {
                    "document_id": "doc-1",
                    "max_items": 12,
                    "name_contains": "base",
                    "include_entity_counts": True,
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_list_sketches_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.list_sketches(max_items=0)

        self.assertEqual(runner.calls, [])

    def test_rename_sketch_forwards_target_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.rename_sketch(document_id="doc-1", sketch_ref=100, name="RENAMED")

        self.assertEqual(
            runner.calls[0],
            (
                "rename_sketch",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "name": "RENAMED",
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_rename_sketch_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.rename_sketch(sketch_ref=100, name="")
        with self.assertRaises(ValueError):
            adapter.rename_sketch(name="RENAMED")

        self.assertEqual(runner.calls, [])

    def test_set_sketch_entity_style_forwards_selector_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.set_sketch_entity_style(
            document_id="doc-1",
            sketch_ref=100,
            entity={"kind": "line", "index": "2"},
            line_style=3,
        )

        self.assertEqual(
            runner.calls[0],
            (
                "set_sketch_entity_style",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "entity": {"kind": "segment", "index": 2},
                    "line_style": 3,
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_set_sketch_entity_style_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.set_sketch_entity_style(sketch_ref=100, entity={"kind": "segment", "index": 0}, line_style=0)
        with self.assertRaises(ValueError):
            adapter.set_sketch_entity_style(entity={"kind": "segment", "index": 0}, line_style=1)
        with self.assertRaises(ValueError):
            adapter.set_sketch_entity_style(sketch_ref=100, entity={"kind": "spline", "index": 0}, line_style=1)

        self.assertEqual(runner.calls, [])

    def test_delete_sketch_entity_forwards_selector_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.delete_sketch_entity(
            document_id="doc-1",
            sketch_ref=100,
            entity={"kind": "line", "index": "2"},
        )

        self.assertEqual(
            runner.calls[0],
            (
                "delete_sketch_entity",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "entity": {"kind": "segment", "index": 2},
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_delete_sketch_entity_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.delete_sketch_entity(entity={"kind": "segment", "index": 0})
        with self.assertRaises(ValueError):
            adapter.delete_sketch_entity(sketch_ref=100, entity={"kind": "spline", "index": 0})

        self.assertEqual(runner.calls, [])

    def test_update_sketch_entity_geometry_forwards_selector_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.update_sketch_entity_geometry(
            document_id="doc-1",
            sketch_ref=100,
            entity={"kind": "line", "index": "2"},
            geometry={"start": [1, 2], "end": [3, 4]},
        )

        self.assertEqual(
            runner.calls[0],
            (
                "update_sketch_entity_geometry",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "entity": {"kind": "segment", "index": 2},
                    "geometry": {"start": [1.0, 2.0], "end": [3.0, 4.0]},
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_update_sketch_entity_geometry_forwards_arc_geometry_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.update_sketch_entity_geometry(
            document_id="doc-1",
            sketch_ref=100,
            entity={"kind": "arc", "index": 1},
            geometry={"center": [5, 5], "radius": 7, "start": [12, 5], "end": [5, 12], "direction": True},
        )

        self.assertEqual(
            runner.calls[0],
            (
                "update_sketch_entity_geometry",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "entity": {"kind": "arc", "index": 1},
                    "geometry": {
                        "center": [5.0, 5.0],
                        "radius": 7.0,
                        "start": [12.0, 5.0],
                        "end": [5.0, 12.0],
                        "direction": True,
                    },
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_update_sketch_entity_geometry_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.update_sketch_entity_geometry(entity={"kind": "segment", "index": 0}, geometry={"start": [0, 0], "end": [1, 0]})
        with self.assertRaises(ValueError):
            adapter.update_sketch_entity_geometry(sketch_ref=100, entity={"kind": "ellipse", "index": 0}, geometry={})
        with self.assertRaises(ValueError):
            adapter.update_sketch_entity_geometry(sketch_ref=100, entity={"kind": "circle", "index": 0}, geometry={"center": [0, 0], "radius": 0})

        self.assertEqual(runner.calls, [])

    def test_list_sketch_dimensions_forwards_filter_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.list_sketch_dimensions(
            document_id="doc-1",
            sketch_ref=100,
            kinds=["line_length", "circle_diameter"],
            max_items=10,
        )

        self.assertEqual(
            runner.calls[0],
            (
                "list_sketch_dimensions",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "max_items": 10,
                    "kinds": ["line", "diametral"],
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_inspect_sketch_dimension_forwards_selector_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.inspect_sketch_dimension(
            document_id="doc-1",
            sketch_ref=100,
            dimension={"kind": "circle_diameter", "reference": 301},
        )

        self.assertEqual(
            runner.calls[0],
            (
                "inspect_sketch_dimension",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "dimension": {"kind": "diametral", "reference": "301"},
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_sketch_dimension_readback_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.list_sketch_dimensions(sketch_ref=100, kinds=["unsupported"])
        with self.assertRaises(ValueError):
            adapter.list_sketch_dimensions(kinds=["line"])
        with self.assertRaises(ValueError):
            adapter.inspect_sketch_dimension(sketch_ref=100, dimension={"kind": "line"})
        with self.assertRaises(ValueError):
            adapter.inspect_sketch_dimension(sketch_ref=100, dimension={"kind": "unsupported", "index": 0})

        self.assertEqual(runner.calls, [])

    def test_list_sketch_constraints_forwards_filter_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.list_sketch_constraints(
            document_id="doc-1",
            sketch_ref=100,
            kinds=["horizontal", "fixed_length"],
            max_items=10,
        )

        self.assertEqual(
            runner.calls[0],
            (
                "list_sketch_constraints",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "max_items": 10,
                    "kinds": ["horizontal", "fixed_length"],
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_inspect_sketch_constraint_forwards_selector_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.inspect_sketch_constraint(
            document_id="doc-1",
            sketch_ref=100,
            constraint={"kind": "horizontal", "reference": 401},
        )

        self.assertEqual(
            runner.calls[0],
            (
                "inspect_sketch_constraint",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "constraint": {"kind": "horizontal", "reference": "401"},
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_clear_sketch_entity_constraints_forwards_selector_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.clear_sketch_entity_constraints(
            document_id="doc-1",
            sketch_ref=100,
            entity={"kind": "line", "reference": 201},
        )

        self.assertEqual(
            runner.calls[0],
            (
                "clear_sketch_entity_constraints",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "entity": {"kind": "segment", "reference": "201"},
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_repair_sketch_forwards_bounded_operations_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.repair_sketch(
            document_id="doc-1",
            sketch_ref=100,
            apply=True,
            operations=[
                {
                    "id": "fix-line",
                    "operation": "update_geometry",
                    "entity": {"kind": "line", "reference": 201},
                    "geometry": {"start": [1, 2], "end": [3, 4]},
                    "reason": "move line",
                },
                {"operation": "delete_entity", "entity": {"kind": "point", "index": "0"}},
                {"operation": "clear_constraints", "entity": {"kind": "arc", "fingerprint": "arc|1"}},
            ],
        )

        self.assertEqual(
            runner.calls[0],
            (
                "repair_sketch",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "operations": [
                        {
                            "id": "fix-line",
                            "operation": "update_geometry",
                            "entity": {"kind": "segment", "reference": "201"},
                            "geometry": {"start": [1.0, 2.0], "end": [3.0, 4.0]},
                            "reason": "move line",
                        },
                        {"operation": "delete_entity", "entity": {"kind": "point", "index": 0}},
                        {"operation": "clear_constraints", "entity": {"kind": "arc", "fingerprint": "arc|1"}},
                    ],
                    "apply": True,
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_sketch_constraint_readback_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.list_sketch_constraints(sketch_ref=100, kinds=["unsupported"])
        with self.assertRaises(ValueError):
            adapter.list_sketch_constraints(kinds=["horizontal"])
        with self.assertRaises(ValueError):
            adapter.inspect_sketch_constraint(sketch_ref=100, constraint={"kind": "horizontal"})
        with self.assertRaises(ValueError):
            adapter.inspect_sketch_constraint(sketch_ref=100, constraint={"kind": "unsupported", "index": 0})
        with self.assertRaises(ValueError):
            adapter.clear_sketch_entity_constraints(entity={"kind": "segment", "index": 0})
        with self.assertRaises(ValueError):
            adapter.clear_sketch_entity_constraints(sketch_ref=100, entity={"kind": "unsupported", "index": 0})
        with self.assertRaises(ValueError):
            adapter.repair_sketch(sketch_ref=100, operations=[])
        with self.assertRaises(ValueError):
            adapter.repair_sketch(sketch_ref=100, operations=[{"operation": "missing", "entity": {"kind": "line", "index": 0}}])
        with self.assertRaises(ValueError):
            adapter.repair_sketch(
                sketch_ref=100,
                operations=[{"operation": "update_geometry", "entity": {"kind": "circle", "index": 0}, "geometry": {"radius": 0}}],
            )

        self.assertEqual(runner.calls, [])

    def test_list_features_forwards_filter_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.list_features(
            document_id="doc-1",
            kinds=["revolve", "extrude"],
            max_items=10,
        )

        self.assertEqual(
            runner.calls[0],
            (
                "list_features",
                {
                    "document_id": "doc-1",
                    "max_items": 10,
                    "kinds": ["rotated", "extrusion"],
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_inspect_feature_forwards_selector_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.inspect_feature(
            document_id="doc-1",
            feature={"kind": "revolve", "reference": 501},
        )

        self.assertEqual(
            runner.calls[0],
            (
                "inspect_feature",
                {
                    "document_id": "doc-1",
                    "feature": {"kind": "rotated", "reference": "501"},
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_repair_feature_forwards_bounded_operations(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.repair_feature(
            document_id="doc-1",
            operations=[
                {
                    "operation": "rename_feature",
                    "feature": {"kind": "revolve", "reference": 501},
                    "name": "RENAMED",
                },
                {
                    "operation": "suppress",
                    "feature": {"kind": "extrude", "index": "0"},
                },
            ],
            apply=True,
        )

        self.assertEqual(
            runner.calls[0],
            (
                "repair_feature",
                {
                    "document_id": "doc-1",
                    "operations": [
                        {
                            "operation": "rename",
                            "feature": {"kind": "rotated", "reference": "501"},
                            "name": "RENAMED",
                        },
                        {
                            "operation": "set_suppressed",
                            "feature": {"kind": "extrusion", "index": 0},
                            "suppressed": True,
                        },
                    ],
                    "apply": True,
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_feature_readback_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.list_features(kinds=["unsupported"])
        with self.assertRaises(ValueError):
            adapter.list_features(max_items=0)
        with self.assertRaises(ValueError):
            adapter.inspect_feature(feature={"kind": "unsupported", "index": 0})
        with self.assertRaises(ValueError):
            adapter.inspect_feature(feature={"kind": "rotated"})
        with self.assertRaises(ValueError):
            adapter.repair_feature(operations=[])
        with self.assertRaises(ValueError):
            adapter.repair_feature(operations=[{"operation": "rename", "feature": {"kind": "rotated", "index": 0}}])
        with self.assertRaises(ValueError):
            adapter.repair_feature(operations=[{"operation": "explode", "feature": {"kind": "rotated", "index": 0}}])

        self.assertEqual(runner.calls, [])

    def test_inspect_sketch_entity_forwards_selector_payload(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.inspect_sketch_entity(
            document_id="doc-1",
            sketch_ref=100,
            entity={"kind": "line", "index": "2"},
        )

        self.assertEqual(
            runner.calls[0],
            (
                "inspect_sketch_entity",
                {
                    "document_id": "doc-1",
                    "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                    "entity": {"kind": "segment", "index": 2},
                },
            ),
        )
        self.assertTrue(result["ok"])

    def test_inspect_sketch_entity_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.inspect_sketch_entity(sketch_ref=100, entity={"kind": "spline", "index": 0})
        with self.assertRaises(ValueError):
            adapter.inspect_sketch_entity(entity={"kind": "segment", "index": 0})
        with self.assertRaises(ValueError):
            adapter.inspect_sketch_entity(sketch_ref=100, entity={"kind": "segment"})

        self.assertEqual(runner.calls, [])

    def test_create_sketch_line_segment_can_append_to_existing_sketch_target(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.create_sketch_line_segment(
            document_id="doc-1",
            sketch_ref=100,
            create_new_sketch=False,
            start=[0, 0],
            end=[10, 0],
        )

        self.assertEqual(result["operation"], "create_sketch_line_segment")
        self.assertEqual(
            runner.calls,
            [
                (
                    "create_sketch_entities",
                    {
                        "document_id": "doc-1",
                        "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                        "entities": [{"kind": "segment", "start": [0.0, 0.0], "end": [10.0, 0.0], "line_style": 1}],
                    },
                )
            ],
        )

    def test_create_sketch_point_uses_single_entity_batch_contract(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        result = adapter.create_sketch_point(
            document_id="doc-1",
            sketch_ref=100,
            create_new_sketch=False,
            point=[1, 2],
        )

        self.assertEqual(result["operation"], "create_sketch_point")
        self.assertEqual(
            runner.calls,
            [
                (
                    "create_sketch_entities",
                    {
                        "document_id": "doc-1",
                        "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                        "entities": [{"kind": "point", "point": [1.0, 2.0], "line_style": 1}],
                    },
                )
            ],
        )

    def test_create_sketch_arc_and_ellipse_validate_single_entity_payloads(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        adapter.create_sketch_arc(center=[5, 5], radius=3, start=[8, 5], end=[5, 8], direction=False)
        adapter.create_sketch_ellipse(center=[5, 5], radius_x=4, radius_y=2, angle=15)

        self.assertEqual(runner.calls[0][0], "create_sketch_entities")
        self.assertEqual(runner.calls[0][1]["entities"][0]["kind"], "arc")
        self.assertEqual(runner.calls[0][1]["entities"][0]["direction"], False)
        self.assertEqual(runner.calls[1][1]["entities"][0]["kind"], "ellipse")
        self.assertEqual(runner.calls[1][1]["entities"][0]["angle"], 15.0)

    def test_create_sketch_polyline_rejects_too_few_points_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.create_sketch_polyline(points=[[0, 0]])

        self.assertEqual(runner.calls, [])

    def test_bridge_create_point3d_targets_active_part(self) -> None:
        bridge = _load_bridge_module()
        app = object()
        part = _FakePart()
        document = types.SimpleNamespace(TopPart=part)
        point = types.SimpleNamespace(Name="PT_A", X=1.0, Y=2.0, Z=3.0, Reference=42)
        created: dict[str, Any] = {}

        original_make_app = bridge.make_app
        original_resolve_document = bridge.resolve_document
        original_cast_model_container = bridge.cast_model_container
        original_create_point3d = bridge._create_point3d
        original_describe_document = bridge.describe_document
        self.addCleanup(setattr, bridge, "make_app", original_make_app)
        self.addCleanup(setattr, bridge, "resolve_document", original_resolve_document)
        self.addCleanup(setattr, bridge, "cast_model_container", original_cast_model_container)
        self.addCleanup(setattr, bridge, "_create_point3d", original_create_point3d)
        self.addCleanup(setattr, bridge, "describe_document", original_describe_document)

        bridge.make_app = lambda: app
        bridge.resolve_document = lambda live_app, document_id: document
        bridge.cast_model_container = lambda live_part: live_part
        bridge.describe_document = lambda live_document, live_app: {"id": "doc-1"}

        def create_point(model_container: Any, name: str, origin: list[float]) -> Any:
            created.update({"model_container": model_container, "name": name, "origin": origin})
            part.Points3D = _FakeCollection([point])
            return point

        bridge._create_point3d = create_point

        result = bridge.handle_create_point3d({"document_id": "doc-1", "name": "PT_A", "origin": [1.0, 2.0, 3.0]})

        self.assertTrue(result["ok"])
        self.assertEqual(created, {"model_container": part, "name": "PT_A", "origin": [1.0, 2.0, 3.0]})
        self.assertTrue(part.updated)
        self.assertEqual(result["item"]["reference"], 42)
        self.assertEqual(result["summary"]["update_ok"], True)
        self.assertEqual(result["readback"]["before"]["snapshot"]["counts"]["items"], 1)
        self.assertEqual(result["readback"]["after"]["snapshot"]["counts"]["items"], 2)
        self.assertEqual(
            result["readback"]["after"]["snapshot"]["manifest"]["item_index"]["entries"][-1]["source_path"],
            "",
        )
        self.assertEqual(
            result["readback"]["after"]["snapshot"]["manifest"]["item_index"]["entries"][-1]["model_object_collection"],
            "points3d",
        )

    def test_bridge_create_point3d_uses_points3d_add(self) -> None:
        bridge = _load_bridge_module()
        point = _FakePoint3D()
        points = _FakePoint3DCollection(point)
        part = types.SimpleNamespace(Points3D=points)

        result = bridge._create_point3d(part, "PT_ADD", [1.0, 2.0, 3.0])

        self.assertIs(result, point)
        self.assertEqual(points.Count, 1)
        self.assertEqual(point.Name, "PT_ADD")
        self.assertEqual([point.X, point.Y, point.Z], [1.0, 2.0, 3.0])
        self.assertTrue(point.updated)

    def test_bridge_create_point3d_displace_prefers_distance_expression(self) -> None:
        bridge = _load_bridge_module()
        parameters = types.SimpleNamespace(
            PositionObject=None,
            Distance=None,
            association_vertex=None,
            guiding_object=None,
        )
        parameters.SetAssociationVertex = lambda obj: setattr(parameters, "association_vertex", obj) or True
        parameters.SetGuidingObject = lambda obj: setattr(parameters, "guiding_object", obj) or True
        point = types.SimpleNamespace(ParameterType=None, Parameters=parameters, Update=lambda: True)
        position_object = object()
        guiding_object = object()

        original_create_point3d = bridge._create_point3d
        original_cast = bridge._cast_to_com_interface
        original_bind = bridge._bind_operation_variables
        self.addCleanup(setattr, bridge, "_create_point3d", original_create_point3d)
        self.addCleanup(setattr, bridge, "_cast_to_com_interface", original_cast)
        self.addCleanup(setattr, bridge, "_bind_operation_variables", original_bind)
        bridge._create_point3d = lambda model_container, name, origin: point
        bridge._cast_to_com_interface = lambda obj, interface_name: obj
        binding_calls = []
        bridge._bind_operation_variables = lambda obj, bindings: binding_calls.append((obj, bindings)) or {"ok": True}

        result = bridge._create_point3d_displace(
            object(),
            "PT_EXPR",
            position_object,
            [0.0, 0.0, 0.0],
            guiding_object=guiding_object,
            distance=3.0,
            distance_expression="SPG01_N21 * SPG01_WD1",
        )

        self.assertIs(result, point)
        self.assertEqual(point.ParameterType, 2)
        self.assertIs(parameters.association_vertex, position_object)
        self.assertIs(parameters.guiding_object, guiding_object)
        self.assertEqual(parameters.Distance, 3.0)
        self.assertEqual(binding_calls[0][0], point)
        self.assertEqual(binding_calls[0][1][0]["expression"], "SPG01_N21 * SPG01_WD1")

    def test_bridge_bind_operation_variables_uses_iter_fallback_for_hidden_variables(self) -> None:
        bridge = _load_bridge_module()

        class _FakeVariable:
            def __init__(self, name: str, note: str, expression: str = "") -> None:
                self.Name = name
                self.ParameterNote = note
                self.Expression = expression

            def Update(self) -> bool:
                return True

        class _FakeVariables:
            def __init__(self, indexed: list[Any], iterated: list[Any]) -> None:
                self._indexed = list(indexed)
                self._iterated = list(iterated)
                self.Count = len(self._indexed)

            def Item(self, index: int) -> Any:
                if index < 0 or index >= len(self._indexed):
                    raise IndexError(index)
                return self._indexed[index]

            def __iter__(self):
                return iter(self._iterated)

        indexed = [
            _FakeVariable("v82", "Диаметр 1"),
            _FakeVariable("v77", "Шаг"),
            _FakeVariable("v80", "Высота"),
        ]
        hidden_rotation = _FakeVariable("v1244", "Вращение")
        model = types.SimpleNamespace(
            Variables=_FakeVariables(indexed=indexed, iterated=indexed + [hidden_rotation]),
            Update=lambda: True,
        )

        report = bridge._bind_operation_variables(
            model,
            [
                {
                    "parameter_note": "Rotation",
                    "parameter_note_aliases": ["Rotation", "Вращение"],
                    "expression": "360 * (N21)",
                    "role": "spring_anchor_rotation",
                }
            ],
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["applied_count"], 1)
        self.assertEqual(report["applied"][0]["parameter_note"], "Вращение")
        self.assertEqual(hidden_rotation.Expression, "360 * (N21)")

    def test_bridge_apply_part_variables_uses_comment_as_parameter_note(self) -> None:
        bridge = _load_bridge_module()

        class _FakeCreatedVariable:
            def __init__(self, name: str, value: float, note: str) -> None:
                self.Name = name
                self.Value = value
                self.ParameterNote = note
                self.Expression = ""
                self.External = False
                self.Reference = 12

            def Update(self) -> bool:
                return True

        class _FakePart:
            def __init__(self) -> None:
                self.created: list[_FakeCreatedVariable] = []

            def AddVariable(self, name: str, value: float, note: str) -> _FakeCreatedVariable:
                variable = _FakeCreatedVariable(name, value, note)
                self.created.append(variable)
                return variable

        part = _FakePart()

        report = bridge._apply_part_variables(
            part,
            [
                {
                    "name": "G1",
                    "value": 0.01,
                    "external": True,
                    "comment": "G1: axial gap between adjacent body coils",
                }
            ],
        )

        self.assertTrue(report["ok"])
        self.assertEqual(part.created[0].ParameterNote, "G1: axial gap between adjacent body coils")
        self.assertEqual(report["applied"][0]["note"], "G1: axial gap between adjacent body coils")

    def test_bridge_collection_resolver_does_not_call_callable_collection_property(self) -> None:
        bridge = _load_bridge_module()
        point = _FakePoint3D()
        points = _FakePoint3DCollection(point)
        part = types.SimpleNamespace(Points3D=points)

        collection, accessor, errors = bridge._resolve_model_object_collection(part, ("Points3D", "GetPoints3D"))

        self.assertIs(collection, points)
        self.assertEqual(accessor, "Points3D")
        self.assertEqual(errors, [])
        self.assertFalse(points.called_as_function)

    def test_bridge_create_sketch_line_segment_targets_active_part(self) -> None:
        bridge = _load_bridge_module()
        app = object()
        part = _FakePart()
        document = types.SimpleNamespace(TopPart=part)
        sketch = types.SimpleNamespace(Name="SK_A", Reference=100)
        line = types.SimpleNamespace(Name="", Reference=101, Style=1)
        created: dict[str, Any] = {}

        original_make_app = bridge.make_app
        original_resolve_document = bridge.resolve_document
        original_cast_model_container = bridge.cast_model_container
        original_create_line = bridge._create_sketch_line_segment
        original_describe_document = bridge.describe_document
        self.addCleanup(setattr, bridge, "make_app", original_make_app)
        self.addCleanup(setattr, bridge, "resolve_document", original_resolve_document)
        self.addCleanup(setattr, bridge, "cast_model_container", original_cast_model_container)
        self.addCleanup(setattr, bridge, "_create_sketch_line_segment", original_create_line)
        self.addCleanup(setattr, bridge, "describe_document", original_describe_document)

        bridge.make_app = lambda: app
        bridge.resolve_document = lambda live_app, document_id: document
        bridge.cast_model_container = lambda live_part: live_part
        bridge.describe_document = lambda live_document, live_app: {"id": "doc-1"}

        def create_line(model_container: Any, part_arg: Any, name: str, plane: str, start: list[float], end: list[float], line_style: int) -> Any:
            created.update(
                {
                    "model_container": model_container,
                    "part": part_arg,
                    "name": name,
                    "plane": plane,
                    "start": start,
                    "end": end,
                    "line_style": line_style,
                }
            )
            part.Sketchs = _FakeCollection([sketch])
            return sketch, line, "xoy_plane"

        bridge._create_sketch_line_segment = create_line

        result = bridge.handle_create_sketch_line_segment(
            {"document_id": "doc-1", "name": "SK_A", "plane": "XOY", "start": [0.0, 0.0], "end": [10.0, 5.0], "line_style": 1}
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            created,
            {
                "model_container": part,
                "part": part,
                "name": "SK_A",
                "plane": "XOY",
                "start": [0.0, 0.0],
                "end": [10.0, 5.0],
                "line_style": 1,
            },
        )
        self.assertTrue(part.updated)
        self.assertEqual(result["item"]["reference"], 101)
        self.assertEqual(result["summary"]["plane"], "xoy_plane")
        self.assertEqual(result["readback"]["before"]["snapshot"]["counts"]["items"], 1)
        self.assertEqual(result["readback"]["after"]["snapshot"]["counts"]["items"], 2)
        self.assertEqual(
            result["readback"]["after"]["snapshot"]["manifest"]["item_index"]["entries"][-1]["model_object_collection"],
            "sketches",
        )

    def test_bridge_create_sketch_circle_targets_active_part(self) -> None:
        bridge = _load_bridge_module()
        app = object()
        part = _FakePart()
        document = types.SimpleNamespace(TopPart=part)
        sketch = types.SimpleNamespace(Name="SK_C", Reference=100)
        circle = types.SimpleNamespace(Name="", Reference=102, Style=1)
        created: dict[str, Any] = {}

        original_make_app = bridge.make_app
        original_resolve_document = bridge.resolve_document
        original_cast_model_container = bridge.cast_model_container
        original_create_circle = bridge._create_sketch_circle
        original_describe_document = bridge.describe_document
        self.addCleanup(setattr, bridge, "make_app", original_make_app)
        self.addCleanup(setattr, bridge, "resolve_document", original_resolve_document)
        self.addCleanup(setattr, bridge, "cast_model_container", original_cast_model_container)
        self.addCleanup(setattr, bridge, "_create_sketch_circle", original_create_circle)
        self.addCleanup(setattr, bridge, "describe_document", original_describe_document)

        bridge.make_app = lambda: app
        bridge.resolve_document = lambda live_app, document_id: document
        bridge.cast_model_container = lambda live_part: live_part
        bridge.describe_document = lambda live_document, live_app: {"id": "doc-1"}

        def create_circle(
            model_container: Any,
            part_arg: Any,
            name: str,
            plane: str,
            center: list[float],
            radius: float,
            line_style: int,
        ) -> Any:
            created.update(
                {
                    "model_container": model_container,
                    "part": part_arg,
                    "name": name,
                    "plane": plane,
                    "center": center,
                    "radius": radius,
                    "line_style": line_style,
                }
            )
            part.Sketchs = _FakeCollection([sketch])
            return sketch, circle, "xoy_plane"

        bridge._create_sketch_circle = create_circle

        result = bridge.handle_create_sketch_circle(
            {"document_id": "doc-1", "name": "SK_C", "plane": "XOY", "center": [5.0, 5.0], "radius": 12.0, "line_style": 1}
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            created,
            {
                "model_container": part,
                "part": part,
                "name": "SK_C",
                "plane": "XOY",
                "center": [5.0, 5.0],
                "radius": 12.0,
                "line_style": 1,
            },
        )
        self.assertTrue(part.updated)
        self.assertEqual(result["item"]["reference"], 102)
        self.assertEqual(result["summary"]["plane"], "xoy_plane")
        self.assertEqual(result["readback"]["before"]["snapshot"]["counts"]["items"], 1)
        self.assertEqual(result["readback"]["after"]["snapshot"]["counts"]["items"], 2)
        self.assertEqual(
            result["readback"]["after"]["snapshot"]["manifest"]["item_index"]["entries"][-1]["model_object_collection"],
            "sketches",
        )

    def test_bridge_create_sketch_rectangle_targets_active_part(self) -> None:
        bridge = _load_bridge_module()
        app = object()
        part = _FakePart()
        document = types.SimpleNamespace(TopPart=part)
        sketch = types.SimpleNamespace(Name="SK_R", Reference=100)
        lines = [types.SimpleNamespace(Name="", Reference=200 + index, Style=1) for index in range(4)]
        created: dict[str, Any] = {}

        original_make_app = bridge.make_app
        original_resolve_document = bridge.resolve_document
        original_cast_model_container = bridge.cast_model_container
        original_create_rectangle = bridge._create_sketch_rectangle
        original_describe_document = bridge.describe_document
        self.addCleanup(setattr, bridge, "make_app", original_make_app)
        self.addCleanup(setattr, bridge, "resolve_document", original_resolve_document)
        self.addCleanup(setattr, bridge, "cast_model_container", original_cast_model_container)
        self.addCleanup(setattr, bridge, "_create_sketch_rectangle", original_create_rectangle)
        self.addCleanup(setattr, bridge, "describe_document", original_describe_document)

        bridge.make_app = lambda: app
        bridge.resolve_document = lambda live_app, document_id: document
        bridge.cast_model_container = lambda live_part: live_part
        bridge.describe_document = lambda live_document, live_app: {"id": "doc-1"}

        def create_rectangle(
            model_container: Any,
            part_arg: Any,
            name: str,
            plane: str,
            corner1: list[float],
            corner2: list[float],
            line_style: int,
        ) -> Any:
            created.update(
                {
                    "model_container": model_container,
                    "part": part_arg,
                    "name": name,
                    "plane": plane,
                    "corner1": corner1,
                    "corner2": corner2,
                    "line_style": line_style,
                }
            )
            part.Sketchs = _FakeCollection([sketch])
            return sketch, lines, "xoy_plane"

        bridge._create_sketch_rectangle = create_rectangle

        result = bridge.handle_create_sketch_rectangle(
            {"document_id": "doc-1", "name": "SK_R", "plane": "XOY", "corner1": [0.0, 0.0], "corner2": [20.0, 10.0], "line_style": 1}
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            created,
            {
                "model_container": part,
                "part": part,
                "name": "SK_R",
                "plane": "XOY",
                "corner1": [0.0, 0.0],
                "corner2": [20.0, 10.0],
                "line_style": 1,
            },
        )
        self.assertTrue(part.updated)
        self.assertEqual(result["item"]["reference"], 200)
        self.assertEqual(result["summary"]["line_count"], 4)
        self.assertEqual(result["readback"]["before"]["snapshot"]["counts"]["items"], 1)
        self.assertEqual(result["readback"]["after"]["snapshot"]["counts"]["items"], 2)
        self.assertEqual(
            result["readback"]["after"]["snapshot"]["manifest"]["item_index"]["entries"][-1]["model_object_collection"],
            "sketches",
        )

    def test_bridge_create_sketch_entities_reports_target_and_per_entity_results(self) -> None:
        bridge = _load_bridge_module()
        app = object()
        part = _FakePart()
        document = types.SimpleNamespace(TopPart=part)
        sketch = types.SimpleNamespace(Name="SK_BATCH", Reference=100)
        entity_results = [{"index": 0, "kind": "segment", "ok": True, "reference": 201}]
        created: dict[str, Any] = {}

        original_make_app = bridge.make_app
        original_resolve_document = bridge.resolve_document
        original_cast_model_container = bridge.cast_model_container
        original_create_entities = bridge._create_sketch_entities
        original_describe_document = bridge.describe_document
        self.addCleanup(setattr, bridge, "make_app", original_make_app)
        self.addCleanup(setattr, bridge, "resolve_document", original_resolve_document)
        self.addCleanup(setattr, bridge, "cast_model_container", original_cast_model_container)
        self.addCleanup(setattr, bridge, "_create_sketch_entities", original_create_entities)
        self.addCleanup(setattr, bridge, "describe_document", original_describe_document)

        bridge.make_app = lambda: app
        bridge.resolve_document = lambda live_app, document_id: document
        bridge.cast_model_container = lambda live_part: live_part
        bridge.describe_document = lambda live_document, live_app: {"id": "doc-1"}

        def create_entities(model_container: Any, part_arg: Any, payload: dict[str, Any]) -> Any:
            created.update({"model_container": model_container, "part": part_arg, "payload": payload})
            part.Sketchs = _FakeCollection([sketch])
            return sketch, {"mode": "create_new_sketch", "name": "SK_BATCH", "plane": "xoy_plane", "sketch_ref": 100}, entity_results, None

        bridge._create_sketch_entities = create_entities

        result = bridge.handle_create_sketch_entities(
            {
                "document_id": "doc-1",
                "target": {"mode": "create_new_sketch", "name": "SK_BATCH", "plane": "XOY"},
                "entities": [{"kind": "segment", "start": [0.0, 0.0], "end": [10.0, 0.0], "line_style": 1}],
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual(created["model_container"], part)
        self.assertEqual(result["target"]["sketch_ref"], 100)
        self.assertEqual(result["items"], entity_results)
        self.assertEqual(result["summary"]["entity_count"], 1)
        self.assertTrue(result["summary"]["update_ok"])
        self.assertTrue(result["summary"]["sketch_update_ok"])
        self.assertTrue(result["summary"]["part_update_ok"])
        self.assertEqual(result["readback"]["after"]["snapshot"]["counts"]["items"], 2)

    def test_bridge_create_sketch_entities_reports_nonfatal_part_update_status(self) -> None:
        bridge = _load_bridge_module()
        app = object()
        part = _FakePart()
        document = types.SimpleNamespace(TopPart=part)
        sketch = types.SimpleNamespace(Name="SK_BATCH", Reference=100)
        entity_results = [{"index": 0, "kind": "segment", "ok": True, "reference": 201}]

        def update_false() -> bool:
            part.updated = True
            return False

        part.Update = update_false  # type: ignore[method-assign]

        original_make_app = bridge.make_app
        original_resolve_document = bridge.resolve_document
        original_cast_model_container = bridge.cast_model_container
        original_create_entities = bridge._create_sketch_entities
        original_describe_document = bridge.describe_document
        self.addCleanup(setattr, bridge, "make_app", original_make_app)
        self.addCleanup(setattr, bridge, "resolve_document", original_resolve_document)
        self.addCleanup(setattr, bridge, "cast_model_container", original_cast_model_container)
        self.addCleanup(setattr, bridge, "_create_sketch_entities", original_create_entities)
        self.addCleanup(setattr, bridge, "describe_document", original_describe_document)

        bridge.make_app = lambda: app
        bridge.resolve_document = lambda live_app, document_id: document
        bridge.cast_model_container = lambda live_part: live_part
        bridge.describe_document = lambda live_document, live_app: {"id": "doc-1"}
        bridge._create_sketch_entities = lambda model_container, part_arg, payload: (
            sketch,
            {"mode": "create_new_sketch", "name": "SK_BATCH", "plane": "xoy_plane", "sketch_ref": 100},
            entity_results,
            None,
        )

        result = bridge.handle_create_sketch_entities(
            {
                "document_id": "doc-1",
                "target": {"mode": "create_new_sketch", "name": "SK_BATCH", "plane": "XOY"},
                "entities": [{"kind": "segment", "start": [0.0, 0.0], "end": [10.0, 0.0]}],
            }
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["summary"]["update_ok"])
        self.assertTrue(result["summary"]["sketch_update_ok"])
        self.assertFalse(result["summary"]["part_update_ok"])
        self.assertTrue(part.updated)

    def test_bridge_create_sketch_entities_supports_v2_entity_batch(self) -> None:
        bridge = _load_bridge_module()
        created_entities = {
            "Points": [_FakeSketchEntity(301)],
            "LineSegments": [_FakeSketchEntity(302), _FakeSketchEntity(303)],
            "Arcs": [_FakeSketchEntity(305)],
            "Ellipses": [_FakeSketchEntity(306)],
        }
        view = types.SimpleNamespace(
            Points=_FakeAddCollection(created_entities["Points"]),
            LineSegments=_FakeAddCollection(created_entities["LineSegments"]),
            Arcs=_FakeAddCollection(created_entities["Arcs"]),
            Ellipses=_FakeAddCollection(created_entities["Ellipses"]),
        )
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_BATCH", 100, sketch_doc)

        original_resolve_target = bridge._resolve_sketch_write_target
        self.addCleanup(setattr, bridge, "_resolve_sketch_write_target", original_resolve_target)
        bridge._resolve_sketch_write_target = lambda model_container, part, payload, default_name: (
            sketch,
            {"mode": "create_new_sketch", "name": "SK_BATCH", "plane": "xoy_plane", "sketch_ref": 100},
        )

        _, target, results, parameterization = bridge._create_sketch_entities(
            object(),
            object(),
            {
                "entities": [
                    {"kind": "point", "point": [1.0, 2.0], "line_style": 1},
                    {"kind": "polyline", "points": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]], "closed": False, "line_style": 1},
                    {"kind": "arc", "center": [5.0, 5.0], "radius": 2.0, "start": [7.0, 5.0], "end": [5.0, 7.0], "direction": True, "line_style": 1},
                    {"kind": "ellipse", "center": [5.0, 5.0], "radius_x": 4.0, "radius_y": 2.0, "angle": 0.0, "line_style": 1},
                ]
            },
        )

        self.assertEqual(target["sketch_ref"], 100)
        self.assertIsNone(parameterization)
        self.assertEqual([item["kind"] for item in results], ["point", "polyline", "arc", "ellipse"])
        self.assertEqual(results[1]["line_count"], 2)
        self.assertTrue(all(entity.updated for bucket in created_entities.values() for entity in bucket))
        self.assertTrue(sketch.ended)
        self.assertTrue(sketch.updated)

    def test_bridge_create_sketch_entities_applies_parameterization_to_entity_ids(self) -> None:
        bridge = _load_bridge_module()
        line = _FakeSketchEntity(501)
        view = types.SimpleNamespace(LineSegments=_FakeAddCollection([line]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_BATCH", 100, sketch_doc)
        captured: dict[str, Any] = {}

        original_resolve_target = bridge._resolve_sketch_write_target
        original_apply_parameterization = bridge._apply_sketch_parameterization
        self.addCleanup(setattr, bridge, "_resolve_sketch_write_target", original_resolve_target)
        self.addCleanup(setattr, bridge, "_apply_sketch_parameterization", original_apply_parameterization)
        bridge._resolve_sketch_write_target = lambda model_container, part, payload, default_name: (
            sketch,
            {"mode": "create_new_sketch", "name": "SK_BATCH", "plane": "xoy_plane", "sketch_ref": 100},
        )

        def apply_parameterization(view_arg: Any, sketch_entities: dict[str, Any], constraints: list[dict[str, Any]], dimensions: list[dict[str, Any]], options: dict[str, Any], steps: list[Any], total_length: float) -> dict[str, Any]:
            captured.update({"view": view_arg, "entities": sketch_entities, "constraints": constraints, "dimensions": dimensions, "options": options})
            return {"ok": True, "constraints": {"live_status": "applied"}, "dimensions": {"live_status": "disabled"}}

        bridge._apply_sketch_parameterization = apply_parameterization

        _, _, results, parameterization = bridge._create_sketch_entities(
            object(),
            object(),
            {
                "entities": [{"kind": "segment", "entity_id": "base", "role": "profile", "start": [0.0, 0.0], "end": [10.0, 0.0], "line_style": 1}],
                "constraints": [{"kind": "horizontal", "target": "base"}],
                "sketch_options": {"readback_geometry": True},
            },
        )

        self.assertEqual(results[0]["id"], "base")
        self.assertIs(captured["entities"]["base"]["object"], line)
        self.assertEqual(captured["constraints"], [{"kind": "horizontal", "target": "base"}])
        self.assertTrue(captured["options"]["constraints"]["enabled"])
        self.assertEqual(parameterization["constraints"]["live_status"], "applied")

    def test_bridge_create_sketch_entities_targets_existing_sketch_ref(self) -> None:
        bridge = _load_bridge_module()
        line = _FakeSketchEntity(401)
        view = types.SimpleNamespace(LineSegments=_FakeAddCollection([line]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        existing = _FakeSketch("SK_EXISTING", 100, sketch_doc)
        other = _FakeSketch("SK_OTHER", 99, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([other, existing]))

        sketch, target, results, parameterization = bridge._create_sketch_entities(
            part,
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "entities": [{"kind": "segment", "start": [0.0, 0.0], "end": [10.0, 0.0], "line_style": 1}],
            },
        )

        self.assertIs(sketch, existing)
        self.assertIsNone(parameterization)
        self.assertEqual(target, {"mode": "existing_sketch", "name": "SK_EXISTING", "sketch_ref": 100})
        self.assertEqual(results[0]["reference"], 401)
        self.assertTrue(existing.ended)
        self.assertTrue(existing.updated)

    def test_bridge_existing_sketch_ref_not_found_is_target_error(self) -> None:
        bridge = _load_bridge_module()
        part = types.SimpleNamespace(Sketchs=_FakeCollection([]))

        with self.assertRaisesRegex(RuntimeError, "sketch_ref not found"):
            bridge._resolve_sketch_write_target(
                part,
                part,
                {"target": {"mode": "existing_sketch", "sketch_ref": "404"}},
                "SK_BATCH",
            )

    def test_bridge_serialize_part_includes_point3d_children(self) -> None:
        bridge = _load_bridge_module()
        point = types.SimpleNamespace(Name="PT_A", X=1.0, Y=2.0, Z=3.0, Reference=42, ModelObjectType=17)
        part = types.SimpleNamespace(
            Name="Part",
            Marking="",
            Material="",
            Comment="",
            Reference=1,
            Points3D=_FakeCollection([point]),
        )

        tree = bridge.serialize_part(part, "root", None)

        self.assertEqual(len(tree["children"]), 1)
        child = tree["children"][0]
        self.assertEqual(child["id"], "root/points3d/42")
        self.assertEqual(child["kind"], "model_object")
        self.assertEqual(child["model_object_collection"], "points3d")
        self.assertEqual(child["origin"], [1.0, 2.0, 3.0])

    def test_bridge_serialize_part_includes_sketch_entity_children(self) -> None:
        bridge = _load_bridge_module()
        line = types.SimpleNamespace(Name="", X1=0.0, Y1=0.0, X2=10.0, Y2=5.0, Style=1, Reference=201)
        circle = types.SimpleNamespace(Name="", Xc=4.0, Yc=3.0, Radius=2.0, Style=1, Reference=202)
        point = types.SimpleNamespace(Name="", X=1.0, Y=2.0, Style=1, Reference=203)
        arc = types.SimpleNamespace(Name="", Xc=4.0, Yc=3.0, Radius=2.0, X1=6.0, Y1=3.0, X2=4.0, Y2=5.0, Direction=True, Style=1, Reference=204)
        ellipse = types.SimpleNamespace(Name="", Xc=7.0, Yc=8.0, Rx=4.0, Ry=2.0, Angle=0.0, Style=1, Reference=205)
        view = types.SimpleNamespace(
            LineSegments=_FakeCollection([line]),
            Circles=_FakeCollection([circle]),
            Points=_FakeCollection([point]),
            Arcs=_FakeCollection([arc]),
            Ellipses=_FakeCollection([ellipse]),
        )
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(
            Name="Part",
            Marking="",
            Material="",
            Comment="",
            Reference=1,
            Sketchs=_FakeCollection([sketch]),
        )

        tree = bridge.serialize_part(part, "root", None)

        sketch_node = tree["children"][0]
        self.assertEqual(sketch_node["model_object_collection"], "sketches")
        self.assertEqual(sketch_node["sketch_entity_count"], 5)
        self.assertEqual([child["sketch_entity_kind"] for child in sketch_node["children"]], ["segment", "circle", "point", "arc", "ellipse"])
        self.assertEqual(sketch_node["children"][0]["geometry"]["end"], [10.0, 5.0])
        self.assertIn("segment|201", sketch_node["children"][0]["fingerprint"])
        self.assertEqual(sketch_node["children"][2]["geometry"]["point"], [1.0, 2.0])
        self.assertIn("arc|204", sketch_node["children"][3]["fingerprint"])
        self.assertEqual(sketch_node["children"][4]["geometry"]["radius_y"], 2.0)
        self.assertTrue(sketch.ended)

    def test_bridge_parameterize_sketch_selects_existing_entities_by_reference(self) -> None:
        bridge = _load_bridge_module()
        line = types.SimpleNamespace(Name="", X1=0.0, Y1=0.0, X2=10.0, Y2=0.0, Style=1, Reference=201)
        view = types.SimpleNamespace(LineSegments=_FakeCollection([line]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))
        captured: dict[str, Any] = {}

        original_apply = bridge._apply_sketch_parameterization
        self.addCleanup(setattr, bridge, "_apply_sketch_parameterization", original_apply)

        def apply_parameterization(view_arg: Any, sketch_entities: dict[str, Any], constraints: list[dict[str, Any]], dimensions: list[dict[str, Any]], options: dict[str, Any], steps: list[Any], total_length: float) -> dict[str, Any]:
            captured["entities"] = sketch_entities
            captured["constraints"] = constraints
            captured["options"] = options
            return {
                "ok": True,
                "constraints": {"live_status": "applied", "applied_count": len(constraints)},
                "dimensions": {"live_status": "disabled"},
                "geometry_checks": {"ok": True},
            }

        bridge._apply_sketch_parameterization = apply_parameterization

        sketch_result, target, selected, report = bridge._parameterize_existing_sketch(
            part,
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "entities": [{"id": "base", "kind": "segment", "reference": 201}],
                "constraints": [{"kind": "horizontal", "target": "base"}],
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(selected[0]["reference"], 201)
        self.assertIn("base", captured["entities"])
        self.assertEqual(captured["entities"]["base"]["x2"], 10.0)
        self.assertEqual(report["constraints"]["applied_count"], 1)
        self.assertTrue(sketch.ended)

    def test_bridge_parameterize_compression_spring_profile_sketch_requires_fully_defined_state(self) -> None:
        bridge = _load_bridge_module()
        profile_circle = _FakeSketchEntity(999)
        profile_circle.Xc = 0.0
        profile_circle.Yc = 15.0
        profile_circle.Radius = 2.0
        live_profile_circle = _FakeSketchEntity(201)
        live_profile_circle.Xc = 0.0
        live_profile_circle.Yc = 15.0
        live_profile_circle.Radius = 2.0
        radius_ref = _FakeSketchEntity(202)
        profile_radius_ref = _FakeSketchEntity(203)
        profile_center_ref = _FakeSketchEntity(204)
        profile_circle_point_ref = _FakeSketchEntity(205)
        view = types.SimpleNamespace(
            LineSegments=_FakeAddCollection([radius_ref, profile_radius_ref]),
            Circles=_FakeCollection([live_profile_circle]),
            Points=_FakeAddCollection([profile_center_ref, profile_circle_point_ref]),
        )
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SPRING_PROFILE", 100, sketch_doc)
        sketch.ConstraintsState = 1
        captured: dict[str, Any] = {}

        original_apply = bridge._apply_sketch_parameterization
        self.addCleanup(setattr, bridge, "_apply_sketch_parameterization", original_apply)

        def apply_parameterization(view_arg: Any, sketch_entities: dict[str, Any], constraints: list[dict[str, Any]], dimensions: list[dict[str, Any]], options: dict[str, Any], steps: list[Any], total_length: float) -> dict[str, Any]:
            captured["entities"] = sketch_entities
            captured["constraints"] = constraints
            captured["dimensions"] = dimensions
            captured["options"] = options
            return {
                "step": "sketch_parameterization",
                "ok": True,
                "constraints": {"live_status": "applied", "applied_count": len(constraints)},
                "dimensions": {"live_status": "applied", "applied_count": len(dimensions)},
                "geometry_checks": {"ok": True},
            }

        bridge._apply_sketch_parameterization = apply_parameterization

        report = bridge._parameterize_compression_spring_profile_sketch(
            sketch,
            profile_circle,
            [0.0, 15.0],
            2.0,
            {
                "sketch": {"construction_line_style": 6, "parameterization_order": "staged"},
                "profile_sketch_constraints": [
                    {"kind": "vertical", "target": "radius_ref"},
                    {"kind": "merge_points", "target": "profile_circle", "index": 0, "partner": "radius_ref", "partner_index": 1},
                    {"kind": "point_on_curve", "target": "profile_radius_ref", "index": 1, "partner": "profile_circle"},
                ],
                "profile_sketch_dimensions": [
                    {
                        "kind": "line_length",
                        "target": "profile_radius_ref",
                        "expression": "(SPRING_WD1) / 2",
                        "driving": True,
                        "placement_index": 1,
                    }
                ],
                "profile_sketch_target_state": "fully_defined",
            },
            [],
        )

        self.assertIs(captured["entities"]["profile_circle"]["object"], live_profile_circle)
        self.assertIs(captured["entities"]["radius_ref"]["object"], radius_ref)
        self.assertIs(captured["entities"]["profile_radius_ref"]["object"], profile_radius_ref)
        self.assertEqual(captured["entities"]["radius_ref"]["y2"], 15.0)
        self.assertEqual(captured["entities"]["profile_radius_ref"]["x1"], 0.0)
        self.assertEqual(captured["entities"]["profile_radius_ref"]["y1"], 15.0)
        self.assertIn(
            {"kind": "merge_points", "target": "profile_circle", "index": 0, "partner": "radius_ref", "partner_index": 1},
            captured["constraints"],
        )
        self.assertIn(
            {"kind": "point_on_curve", "target": "profile_radius_ref", "index": 1, "partner": "profile_circle"},
            captured["constraints"],
        )
        self.assertEqual(
            captured["dimensions"],
            [
                {
                    "kind": "line_length",
                    "target": "profile_radius_ref",
                    "expression": "(SPRING_WD1) / 2",
                    "driving": True,
                    "placement_index": 1,
                }
            ],
        )
        self.assertEqual(captured["options"]["parameterization_order"], "staged")
        self.assertEqual(report["sketch_state"]["label"], "fully_defined")
        self.assertEqual(report["target_state"], "fully_defined")
        self.assertTrue(sketch.ended)
        self.assertTrue(sketch.updated)

    def test_bridge_parameterize_compression_spring_profile_sketch_reports_underdefined_state(self) -> None:
        bridge = _load_bridge_module()
        profile_circle = _FakeSketchEntity(301)
        radius_ref = _FakeSketchEntity(302)
        profile_radius_ref = _FakeSketchEntity(303)
        profile_center_ref = _FakeSketchEntity(304)
        profile_circle_point_ref = _FakeSketchEntity(305)
        view = types.SimpleNamespace(
            LineSegments=_FakeAddCollection([radius_ref, profile_radius_ref]),
            Points=_FakeAddCollection([profile_center_ref, profile_circle_point_ref]),
        )
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SPRING_PROFILE", 101, sketch_doc)
        sketch.ConstraintsState = 2

        original_apply = bridge._apply_sketch_parameterization
        self.addCleanup(setattr, bridge, "_apply_sketch_parameterization", original_apply)
        bridge._apply_sketch_parameterization = lambda *args, **kwargs: {
            "step": "sketch_parameterization",
            "ok": True,
            "constraints": {"live_status": "applied", "applied_count": 1},
            "dimensions": {"live_status": "applied", "applied_count": 1},
            "geometry_checks": {"ok": True},
        }

        report = bridge._parameterize_compression_spring_profile_sketch(
            sketch,
            profile_circle,
            [0.0, 15.0],
            2.0,
            {
                "profile_sketch_constraints": [{"kind": "vertical", "target": "radius_ref"}],
                "profile_sketch_dimensions": [
                    {
                        "kind": "line_length",
                        "target": "profile_radius_ref",
                        "expression": "(SPRING_WD1) / 2",
                        "driving": True,
                        "placement_index": 1,
                    }
                ],
            },
            [],
        )

        self.assertFalse(report["ok"])
        self.assertFalse(report["state_ok"])
        self.assertEqual(report["sketch_state"]["name"], "under_constrained")

    def test_bridge_resolve_compression_spring_profile_sketch_frame_defaults_to_xoy_with_half_turn(self) -> None:
        bridge = _load_bridge_module()

        plane, rotation = bridge._resolve_compression_spring_profile_sketch_frame({})

        self.assertEqual(plane, "XOY")
        self.assertEqual(rotation, {"rz": 180.0})

    def test_bridge_resolve_compression_spring_profile_sketch_frame_keeps_explicit_non_xoy_plane(self) -> None:
        bridge = _load_bridge_module()

        plane, rotation = bridge._resolve_compression_spring_profile_sketch_frame({"plane": "XOZ"})

        self.assertEqual(plane, "XOZ")
        self.assertIsNone(rotation)

    def test_bridge_apply_sketch_parameterization_runs_constraints_before_dimensions_for_constraints_first(self) -> None:
        bridge = _load_bridge_module()
        call_order: list[tuple[str, list[dict[str, Any]]]] = []

        original_constraints = bridge._apply_sketch_constraints
        original_dimensions = bridge._apply_sketch_dimensions
        self.addCleanup(setattr, bridge, "_apply_sketch_constraints", original_constraints)
        self.addCleanup(setattr, bridge, "_apply_sketch_dimensions", original_dimensions)

        def apply_constraints(sketch_entities: dict[str, Any], planned: list[dict[str, Any]], options: dict[str, Any]) -> dict[str, Any]:
            call_order.append(("constraints", planned))
            return {"live_status": "applied", "planned_count": len(planned), "applied_count": len(planned), "failed_count": 0}

        def apply_dimensions(view: Any, sketch_entities: dict[str, Any], planned: list[dict[str, Any]], options: dict[str, Any]) -> dict[str, Any]:
            call_order.append(("dimensions", planned))
            return {"live_status": "applied", "planned_count": len(planned), "applied_count": len(planned), "failed_count": 0}

        bridge._apply_sketch_constraints = apply_constraints
        bridge._apply_sketch_dimensions = apply_dimensions

        report = bridge._apply_sketch_parameterization(
            None,
            {},
            [{"kind": "merge_points", "target": "profile_circle", "partner": "radius_ref"}],
            [{"kind": "circle_diameter", "target": "profile_circle", "expression": "WD1"}],
            {
                "constraints": {"enabled": True},
                "dimensions": {"enabled": True},
                "parameterization_order": "constraints_first",
            },
            [],
            0.0,
        )

        self.assertEqual([item[0] for item in call_order], ["constraints", "dimensions", "dimensions"])
        self.assertEqual(report["parameterization_order"], "constraints_first")

    def test_bridge_add_circle_diameter_dimension_uses_circle_as_base_object(self) -> None:
        bridge = _load_bridge_module()
        circle_object = types.SimpleNamespace(Reference=501)
        dimension_object = types.SimpleNamespace(
            BaseObject=None,
            DimensionType=None,
            Angle=None,
            Reference=601,
        )
        dimension_object.Update = lambda: True
        diametral_dimensions = _FakeAddCollection([dimension_object])

        result = bridge._add_circle_diameter_dimension(
            diametral_dimensions,
            {
                "target": "profile_circle",
                "dimension_type": False,
                "angle": 45.0,
                "driving": False,
            },
            {"profile_circle": {"object": circle_object}},
        )

        self.assertIs(dimension_object.BaseObject, circle_object)
        self.assertFalse(dimension_object.DimensionType)
        self.assertEqual(dimension_object.Angle, 45.0)
        self.assertTrue(result["updated"])

    def test_bridge_add_circle_radius_dimension_uses_circle_as_base_object(self) -> None:
        bridge = _load_bridge_module()
        circle_object = types.SimpleNamespace(Reference=701)
        dimension_object = types.SimpleNamespace(
            BaseObject=None,
            DimensionType=None,
            Angle=None,
            Reference=801,
        )
        dimension_object.Update = lambda: True
        radial_dimensions = _FakeAddCollection([dimension_object])

        result = bridge._add_circle_radius_dimension(
            radial_dimensions,
            {
                "target": "profile_circle",
                "dimension_type": True,
                "angle": 0.0,
                "driving": False,
            },
            {"profile_circle": {"object": circle_object}},
        )

        self.assertIs(dimension_object.BaseObject, circle_object)
        self.assertTrue(dimension_object.DimensionType)
        self.assertEqual(dimension_object.Angle, 0.0)
        self.assertTrue(result["updated"])

    def test_bridge_apply_sketch_dimensions_supports_circle_diameter_via_radial_dimension(self) -> None:
        bridge = _load_bridge_module()
        radial_dimension = types.SimpleNamespace(
            BaseObject=None,
            DimensionType=None,
            Angle=None,
            Reference=901,
        )
        radial_dimension.Update = lambda: True
        view = types.SimpleNamespace(
            LineDimensions=_FakeAddCollection([_FakeSketchEntity(1)]),
            RadialDimensions=_FakeAddCollection([radial_dimension]),
        )

        report = bridge._apply_sketch_dimensions(
            view,
            {"profile_circle": {"object": types.SimpleNamespace(Reference=902)}},
            [
                {
                    "kind": "circle_diameter",
                    "target": "profile_circle",
                    "creation_mode": "radial",
                    "dimension_type": True,
                    "angle": 0.0,
                    "driving": False,
                }
            ],
            {"enabled": True, "driving": False},
        )

        self.assertEqual(report["applied_count"], 1)
        self.assertEqual(report["failed_count"], 0)
        self.assertEqual(report["live_status"], "applied")
        self.assertTrue(radial_dimension.DimensionType)
        self.assertEqual(radial_dimension.Angle, 0.0)

    def test_bridge_list_sketch_entities_returns_selectors(self) -> None:
        bridge = _load_bridge_module()
        line = types.SimpleNamespace(Name="", X1=0.0, Y1=0.0, X2=10.0, Y2=0.0, Style=1, Reference=201)
        circle = types.SimpleNamespace(Name="", Xc=5.0, Yc=5.0, Radius=2.0, Style=1, Reference=202)
        view = types.SimpleNamespace(LineSegments=_FakeCollection([line]), Circles=_FakeCollection([circle]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, items, summary = bridge._list_existing_sketch_entities(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "kinds": ["line", "circle"],
                "max_items": 10,
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual([item["kind"] for item in items], ["segment", "circle"])
        self.assertEqual(items[0]["collection_index"], 0)
        self.assertEqual(items[0]["geometry"]["end"], [10.0, 0.0])
        self.assertIn("segment|201", items[0]["fingerprint"])
        self.assertEqual(summary["counts"], {"segments": 1, "circles": 1})
        self.assertFalse(summary["truncated"])
        self.assertTrue(sketch.ended)

    def test_bridge_list_sketch_dimensions_returns_selectors(self) -> None:
        bridge = _load_bridge_module()
        line_dim = types.SimpleNamespace(
            Name="D1",
            X1=0.0,
            Y1=0.0,
            X2=10.0,
            Y2=0.0,
            X3=5.0,
            Y3=-8.0,
            Orientation=0,
            Reference=301,
        )
        diam_dim = types.SimpleNamespace(Name="D2", Angle=0.0, DimensionType=False, Reference=302)
        view = types.SimpleNamespace(
            LineDimensions=_FakeCollection([line_dim]),
            DiametralDimensions=_FakeCollection([diam_dim]),
        )
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, items, summary = bridge._list_existing_sketch_dimensions(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "kinds": ["line_length", "circle_diameter"],
                "max_items": 10,
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual([item["kind"] for item in items], ["line", "diametral"])
        self.assertEqual(items[0]["collection_index"], 0)
        self.assertEqual(items[0]["geometry"]["x2"], 10.0)
        self.assertIn("line|301", items[0]["fingerprint"])
        self.assertEqual(summary["counts"], {"line_dimensions": 1, "diametral_dimensions": 1})
        self.assertFalse(summary["truncated"])
        self.assertTrue(sketch.ended)

    def test_bridge_inspect_sketch_dimension_returns_one_selector(self) -> None:
        bridge = _load_bridge_module()
        line_dim = types.SimpleNamespace(
            Name="D1",
            X1=0.0,
            Y1=0.0,
            X2=10.0,
            Y2=0.0,
            X3=5.0,
            Y3=-8.0,
            Orientation=0,
            Reference=301,
        )
        view = types.SimpleNamespace(LineDimensions=_FakeCollection([line_dim]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, item = bridge._inspect_existing_sketch_dimension(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "dimension": {"kind": "line_length", "reference": 301},
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(item["kind"], "line")
        self.assertEqual(item["collection_index"], 0)
        self.assertEqual(item["geometry"]["x3"], 5.0)
        self.assertTrue(sketch.ended)

    def test_bridge_list_sketch_constraints_returns_selectors(self) -> None:
        bridge = _load_bridge_module()
        constraint = types.SimpleNamespace(ConstraintType=3, Reference=401, Valid=True, Index=0)
        line = types.SimpleNamespace(
            Name="",
            X1=0.0,
            Y1=0.0,
            X2=10.0,
            Y2=0.0,
            Style=1,
            Reference=201,
            Constraints=_FakeCollection([constraint]),
        )
        view = types.SimpleNamespace(LineSegments=_FakeCollection([line]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, items, summary = bridge._list_existing_sketch_constraints(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "kinds": ["horizontal"],
                "max_items": 10,
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "horizontal")
        self.assertEqual(items[0]["owner"]["reference"], 201)
        self.assertIn("horizontal|401", items[0]["fingerprint"])
        self.assertEqual(summary["constraint_count"], 1)
        self.assertEqual(summary["owners_scanned"], 1)
        self.assertTrue(sketch.ended)

    def test_bridge_inspect_sketch_constraint_returns_one_selector(self) -> None:
        bridge = _load_bridge_module()
        constraint = types.SimpleNamespace(ConstraintType=3, Reference=401, Valid=True, Index=0)
        line = types.SimpleNamespace(
            Name="",
            X1=0.0,
            Y1=0.0,
            X2=10.0,
            Y2=0.0,
            Style=1,
            Reference=201,
            Constraints=_FakeCollection([constraint]),
        )
        view = types.SimpleNamespace(LineSegments=_FakeCollection([line]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, item = bridge._inspect_existing_sketch_constraint(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "constraint": {"kind": "horizontal", "reference": 401},
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(item["kind"], "horizontal")
        self.assertEqual(item["owner"]["collection_index"], 0)
        self.assertTrue(sketch.ended)

    def test_bridge_clear_sketch_entity_constraints_calls_delete_constraints(self) -> None:
        bridge = _load_bridge_module()
        constraint = types.SimpleNamespace(ConstraintType=3, Reference=401, Valid=True, Index=0)
        line = _FakeSketchEntity(201)
        line.Name = ""
        line.X1 = 0.0
        line.Y1 = 0.0
        line.X2 = 10.0
        line.Y2 = 0.0
        line.Style = 1
        line.Constraints = _FakeCollection([constraint])

        def delete_constraints() -> bool:
            line.Constraints._items.clear()
            line.Constraints.Count = 0
            line.constraints_deleted = True
            return True

        line.DeleteConstraints = delete_constraints
        view = types.SimpleNamespace(LineSegments=_FakeCollection([line]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, before, after, summary = bridge._clear_existing_sketch_entity_constraints(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "entity": {"kind": "line", "reference": 201},
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(before["reference"], 201)
        self.assertEqual(after["reference"], 201)
        self.assertTrue(summary["cleared"])
        self.assertEqual(summary["before_count"], 1)
        self.assertEqual(summary["after_count"], 0)
        self.assertTrue(line.constraints_deleted)
        self.assertTrue(line.updated)
        self.assertTrue(sketch.ended)
        self.assertTrue(sketch.updated)

    def test_bridge_repair_sketch_can_plan_without_mutation(self) -> None:
        bridge = _load_bridge_module()
        line = _FakeSketchEntity(201)
        line.Name = ""
        line.X1 = 0.0
        line.Y1 = 0.0
        line.X2 = 10.0
        line.Y2 = 0.0
        line.Style = 1
        collection = _FakeCollection([line])
        view = types.SimpleNamespace(LineSegments=collection)
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, items, summary = bridge._repair_existing_sketch(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "apply": False,
                "operations": [
                    {
                        "operation": "update_geometry",
                        "entity": {"kind": "line", "reference": 201},
                        "geometry": {"start": [5, 6], "end": [15, 16]},
                    },
                ],
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["applied"])
        self.assertEqual(items[0]["summary"]["geometry"]["start"], [5, 6])
        self.assertEqual(line.X1, 0.0)
        self.assertEqual(line.X2, 10.0)
        self.assertTrue(sketch.ended)
        self.assertFalse(sketch.updated)
        self.assertTrue(summary["planned"])

    def test_bridge_repair_sketch_applies_clear_update_and_delete(self) -> None:
        bridge = _load_bridge_module()
        constraint = types.SimpleNamespace(ConstraintType=3, Reference=401, Valid=True, Index=0)
        line = _FakeSketchEntity(201)
        line.Name = ""
        line.X1 = 0.0
        line.Y1 = 0.0
        line.X2 = 10.0
        line.Y2 = 0.0
        line.Style = 1
        line.Constraints = _FakeCollection([constraint])

        def delete_constraints() -> bool:
            line.Constraints._items.clear()
            line.Constraints.Count = 0
            return True

        line.DeleteConstraints = delete_constraints
        point = _FakeSketchEntity(301)
        point.Name = ""
        point.X = 3.0
        point.Y = 4.0
        line_collection = _FakeCollection([line])
        point_collection = _FakeCollection([point])
        view = types.SimpleNamespace(LineSegments=line_collection, Points=point_collection)
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, items, summary = bridge._repair_existing_sketch(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "apply": True,
                "operations": [
                    {"operation": "clear_constraints", "entity": {"kind": "line", "reference": 201}},
                    {
                        "operation": "update_geometry",
                        "entity": {"kind": "line", "reference": 201},
                        "geometry": {"start": [5, 6], "end": [15, 16]},
                    },
                    {"operation": "delete_entity", "entity": {"kind": "point", "reference": 301}},
                ],
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(len(items), 3)
        self.assertTrue(all(item["applied"] for item in items))
        self.assertEqual(items[0]["summary"]["cleared_count"], 1)
        self.assertEqual(items[1]["item"]["geometry"]["start"], [5.0, 6.0])
        self.assertEqual(items[2]["summary"]["deleted_count"], 1)
        self.assertEqual(line.X1, 5.0)
        self.assertEqual(line.Y2, 16.0)
        self.assertEqual(point_collection.Count, 0)
        self.assertTrue(line.updated)
        self.assertTrue(sketch.ended)
        self.assertTrue(sketch.updated)
        self.assertTrue(summary["applied"])
        self.assertEqual(summary["operation_count"], 3)

    def test_bridge_list_features_returns_selectors(self) -> None:
        bridge = _load_bridge_module()
        rotated = types.SimpleNamespace(Name="BaseRevolve", Reference=501, Hidden=False, Type=12)
        extrusion = types.SimpleNamespace(Name="CutPocket", Reference=502, Visible=True, Type=8)
        part = types.SimpleNamespace(
            Rotateds=_FakeCollection([rotated]),
            Extrusions=_FakeCollection([extrusion]),
        )

        items, summary = bridge._list_existing_features(
            part,
            {
                "kinds": ["revolve", "extrusion"],
                "max_items": 10,
            },
        )

        self.assertEqual([item["kind"] for item in items], ["rotated", "extrusion"])
        self.assertEqual(items[0]["collection"], "rotateds")
        self.assertEqual(items[0]["collection_index"], 0)
        self.assertEqual(items[0]["reference"], 501)
        self.assertIn("rotated|501|BaseRevolve", items[0]["fingerprint"])
        self.assertEqual(summary["counts"], {"rotateds": 1, "extrusions": 1})
        self.assertFalse(summary["truncated"])

    def test_bridge_inspect_feature_returns_state_and_variables(self) -> None:
        bridge = _load_bridge_module()
        variables = _FakeCollection(
            [
                types.SimpleNamespace(Name="Length", Expression="L1", Value=42.0, ParameterNote="length"),
            ]
        )
        feature = types.SimpleNamespace(Name="BaseRevolve", Reference=501, Hidden=False, Type=12, Variables=variables)
        part = types.SimpleNamespace(Rotateds=_FakeCollection([feature]))

        item = bridge._inspect_existing_feature(
            part,
            {
                "feature": {"kind": "revolve", "reference": 501},
            },
        )

        self.assertEqual(item["kind"], "rotated")
        self.assertEqual(item["collection_index"], 0)
        self.assertFalse(item["state"]["hidden"])
        self.assertEqual(item["variables"][0]["name"], "Length")
        self.assertEqual(item["variables"][0]["expression"], "L1")
        self.assertEqual(item["variable_count"], 1)

    def test_bridge_repair_feature_plans_and_applies_rename_suppress_delete(self) -> None:
        bridge = _load_bridge_module()
        rotated = _FakeFeature("BaseRevolve", 501, suppressed=False)
        extrusion = _FakeFeature("CutExtrude", 601, suppressed=False)
        pattern = _FakeFeature("Pattern", 701, suppressed=False)
        part = types.SimpleNamespace(
            Rotateds=_FakeCollection([rotated]),
            Extrusions=_FakeCollection([extrusion]),
            FeaturePatterns=_FakeCollection([pattern]),
        )

        planned_items, planned_summary = bridge._repair_existing_features(
            part,
            {
                "operations": [
                    {"operation": "rename", "feature": {"kind": "rotated", "index": 0}, "name": "RENAMED"},
                    {"operation": "suppress", "feature": {"kind": "extrusion", "index": 0}},
                    {"operation": "delete", "feature": {"kind": "feature_pattern", "index": 0}},
                ],
                "apply": False,
            },
        )

        self.assertFalse(planned_summary["applied"])
        self.assertEqual(planned_items[0]["item"]["name"], "RENAMED")
        self.assertEqual(rotated.Name, "BaseRevolve")
        self.assertFalse(extrusion.Suppressed)
        self.assertEqual(part.FeaturePatterns.Count, 1)

        applied_items, applied_summary = bridge._repair_existing_features(
            part,
            {
                "operations": [
                    {"operation": "rename", "feature": {"kind": "rotated", "index": 0}, "name": "RENAMED"},
                    {"operation": "suppress", "feature": {"kind": "extrusion", "index": 0}},
                    {"operation": "delete_feature", "feature": {"kind": "feature_pattern", "index": 0}},
                ],
                "apply": True,
            },
        )

        self.assertTrue(applied_summary["applied"])
        self.assertEqual(rotated.Name, "RENAMED")
        self.assertTrue(rotated.updated)
        self.assertTrue(extrusion.Suppressed)
        self.assertTrue(extrusion.updated)
        self.assertEqual(part.FeaturePatterns.Count, 0)
        self.assertEqual(applied_items[2]["summary"]["deleted_count"], 1)

    def test_bridge_list_sketches_returns_references_and_counts(self) -> None:
        bridge = _load_bridge_module()
        line = types.SimpleNamespace(Name="", X1=0.0, Y1=0.0, X2=10.0, Y2=0.0, Style=1, Reference=201)
        circle = types.SimpleNamespace(Name="", Xc=5.0, Yc=5.0, Radius=2.0, Style=1, Reference=202)
        view = types.SimpleNamespace(LineSegments=_FakeCollection([line]), Circles=_FakeCollection([circle]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("BASE_SKETCH", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        items, summary = bridge._list_existing_sketches(
            part,
            {"name_contains": "base", "max_items": 10, "include_entity_counts": True},
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "BASE_SKETCH")
        self.assertEqual(items[0]["sketch_ref"], 100)
        self.assertEqual(items[0]["collection_index"], 0)
        self.assertEqual(items[0]["entity_counts"]["segments"], 1)
        self.assertEqual(items[0]["entity_counts"]["circles"], 1)
        self.assertEqual(summary["sketch_count"], 1)
        self.assertFalse(summary["truncated"])
        self.assertTrue(sketch.ended)

    def test_bridge_rename_sketch_updates_name(self) -> None:
        bridge = _load_bridge_module()
        sketch = _FakeSketch("OLD_NAME", 100, types.SimpleNamespace())
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, update_ok = bridge._rename_existing_sketch(
            part,
            {"target": {"mode": "existing_sketch", "sketch_ref": "100"}, "name": "NEW_NAME"},
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(sketch.Name, "NEW_NAME")
        self.assertEqual(target["old_name"], "OLD_NAME")
        self.assertEqual(target["name"], "NEW_NAME")
        self.assertEqual(target["sketch_ref"], 100)
        self.assertTrue(update_ok)
        self.assertTrue(sketch.updated)

    def test_bridge_set_sketch_entity_style_updates_selected_entity(self) -> None:
        bridge = _load_bridge_module()
        line = _FakeSketchEntity(201)
        line.Name = ""
        line.X1 = 0.0
        line.Y1 = 0.0
        line.X2 = 10.0
        line.Y2 = 0.0
        line.Style = 1
        view = types.SimpleNamespace(LineSegments=_FakeCollection([line]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, before, after = bridge._set_existing_sketch_entity_style(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "entity": {"kind": "line", "reference": 201},
                "line_style": 3,
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(before["line_style"], 1)
        self.assertEqual(after["line_style"], 3)
        self.assertEqual(after["collection_index"], 0)
        self.assertEqual(line.Style, 3)
        self.assertTrue(line.updated)
        self.assertTrue(sketch.ended)
        self.assertTrue(sketch.updated)

    def test_bridge_delete_sketch_entity_removes_selected_entity(self) -> None:
        bridge = _load_bridge_module()
        line = _FakeSketchEntity(201)
        line.Name = ""
        line.X1 = 0.0
        line.Y1 = 0.0
        line.X2 = 10.0
        line.Y2 = 0.0
        other = _FakeSketchEntity(202)
        other.Name = ""
        other.X1 = 20.0
        other.Y1 = 0.0
        other.X2 = 30.0
        other.Y2 = 0.0
        collection = _FakeCollection([line, other])
        view = types.SimpleNamespace(LineSegments=collection)
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, before, deletion = bridge._delete_existing_sketch_entity(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "entity": {"kind": "line", "reference": 201},
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(before["reference"], 201)
        self.assertTrue(deletion["deleted"])
        self.assertEqual(deletion["deleted_count"], 1)
        self.assertEqual(collection.Count, 1)
        self.assertIs(collection.Item(0), other)
        self.assertTrue(sketch.ended)
        self.assertTrue(sketch.updated)

    def test_bridge_update_sketch_entity_geometry_updates_selected_entity(self) -> None:
        bridge = _load_bridge_module()
        line = _FakeSketchEntity(201)
        line.Name = ""
        line.X1 = 0.0
        line.Y1 = 0.0
        line.X2 = 10.0
        line.Y2 = 0.0
        collection = _FakeCollection([line])
        view = types.SimpleNamespace(LineSegments=collection)
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, before, after = bridge._update_existing_sketch_entity_geometry(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "entity": {"kind": "line", "reference": 201},
                "geometry": {"start": [5, 6], "end": [15, 16]},
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(before["geometry"]["start"], [0.0, 0.0])
        self.assertEqual(after["geometry"]["start"], [5.0, 6.0])
        self.assertEqual(after["geometry"]["end"], [15.0, 16.0])
        self.assertEqual(line.X1, 5.0)
        self.assertEqual(line.Y2, 16.0)
        self.assertTrue(line.updated)
        self.assertTrue(sketch.ended)
        self.assertTrue(sketch.updated)

    def test_bridge_update_sketch_entity_geometry_updates_arc(self) -> None:
        bridge = _load_bridge_module()
        arc = _FakeSketchEntity(301)
        arc.Name = ""
        arc.Xc = 0.0
        arc.Yc = 0.0
        arc.Radius = 5.0
        arc.X1 = 5.0
        arc.Y1 = 0.0
        arc.X2 = 0.0
        arc.Y2 = 5.0
        arc.Direction = False
        collection = _FakeCollection([arc])
        view = types.SimpleNamespace(Arcs=collection)
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, before, after = bridge._update_existing_sketch_entity_geometry(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "entity": {"kind": "arc", "reference": 301},
                "geometry": {"center": [2, 3], "radius": 8, "start": [10, 3], "end": [2, 11], "direction": True},
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(before["geometry"]["center"], [0.0, 0.0])
        self.assertEqual(after["geometry"]["center"], [2.0, 3.0])
        self.assertEqual(after["geometry"]["radius"], 8.0)
        self.assertEqual(after["geometry"]["end"], [2.0, 11.0])
        self.assertTrue(arc.Direction)
        self.assertTrue(arc.updated)
        self.assertTrue(sketch.ended)
        self.assertTrue(sketch.updated)

    def test_bridge_inspect_sketch_entity_returns_one_selector(self) -> None:
        bridge = _load_bridge_module()
        line = types.SimpleNamespace(Name="", X1=0.0, Y1=0.0, X2=10.0, Y2=0.0, Style=1, Reference=201)
        view = types.SimpleNamespace(LineSegments=_FakeCollection([line]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        sketch = _FakeSketch("SK_A", 100, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([sketch]))

        sketch_result, target, item = bridge._inspect_existing_sketch_entity(
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "entity": {"kind": "line", "reference": 201},
            },
        )

        self.assertIs(sketch_result, sketch)
        self.assertEqual(target["sketch_ref"], 100)
        self.assertEqual(item["kind"], "segment")
        self.assertEqual(item["collection_index"], 0)
        self.assertEqual(item["geometry"]["end"], [10.0, 0.0])
        self.assertIn("segment|201", item["fingerprint"])
        self.assertTrue(sketch.ended)

    def test_bridge_resolve_spring_path_contour_reuses_single_contour(self) -> None:
        bridge = _load_bridge_module()

        class _FakePositionParameters:
            def __init__(self, path: Any) -> None:
                self._path = path

            def AngleByOwnAxis(self, _axis: int, angle: float) -> None:
                self._path.orientation_angle = float(angle)

        class _FakeSpiralPath:
            def __init__(self, reference: int, angle: float = 0.0) -> None:
                self.Reference = reference
                self.orientation_angle = float(angle)
                self.updated = False

            def Update(self) -> bool:
                self.updated = True
                return True

        class _FakeContour:
            def __init__(self, collection: Any, expected_angles: list[float]) -> None:
                self._collection = collection
                self._expected_angles = list(expected_angles)
                self.Reference = len(collection._items) + 1000
                self.Name = ""
                self.Edges: list[Any] = []
                self.EdgesCount = 0
                self.update_calls = 0

            def Update(self) -> bool:
                self.update_calls += 1
                actual_angles = [float(getattr(edge, "orientation_angle", 0.0)) for edge in self.Edges]
                if actual_angles == self._expected_angles:
                    self.EdgesCount = len(self.Edges)
                else:
                    self.EdgesCount = max(0, len(self.Edges) - 1)
                return True

        class _FakeContours3D:
            def __init__(self, expected_angles: list[float]) -> None:
                self._expected_angles = list(expected_angles)
                self._items: list[Any] = []
                self.Count = 0

            def Add(self) -> Any:
                contour = _FakeContour(self, self._expected_angles)
                self._items.append(contour)
                self.Count = len(self._items)
                return contour

            def Item(self, index: int) -> Any:
                return self._items[index]

            def Delete(self, index: int) -> bool:
                self._items.pop(index)
                self.Count = len(self._items)
                return True

        auxiliary_container = types.SimpleNamespace(Contours3D=_FakeContours3D([0.0, 180.0]))
        start_path = _FakeSpiralPath(101, 0.0)
        work_path = _FakeSpiralPath(102, 0.0)

        contour, report = bridge._resolve_spring_path_contour(
            auxiliary_container,
            "SPRING_A",
            [
                {
                    "role": "start_end",
                    "path": start_path,
                    "position_parameters": _FakePositionParameters(start_path),
                    "applied_orientation_angle": 0.0,
                    "orientation_angle_candidates": [0.0],
                    "angle_application_mode": "default",
                },
                {
                    "role": "working",
                    "path": work_path,
                    "position_parameters": _FakePositionParameters(work_path),
                    "applied_orientation_angle": 0.0,
                    "orientation_angle_candidates": [180.0],
                    "angle_application_mode": "orientation",
                },
            ],
        )

        self.assertEqual(report["edges_count"], 2)
        self.assertEqual(report["combo_index"], 1)
        self.assertEqual(report["candidate_orientation_angles"], [0.0, 180.0])
        self.assertEqual(auxiliary_container.Contours3D.Count, 1)
        self.assertIs(auxiliary_container.Contours3D._items[0], contour)
        self.assertEqual(contour.Name, "SPRING_A_PATH_CONTOUR")
        self.assertEqual(contour.update_calls, 3)

    def test_apply_spiral_turning_angle_prefers_own_axis_for_orientation_mode(self) -> None:
        bridge = _load_bridge_module()

        class _FakeEulerParameters:
            def __init__(self) -> None:
                self.NutationAngle = 11.0
                self.PrecessionAngle = 22.0
                self.RotationAngle = 33.0

        class _FakePosition:
            def __init__(self) -> None:
                self.OrientationType = 0
                self.LocalCSParameters = _FakeEulerParameters()

        class _FakePositionParameters:
            def __init__(self) -> None:
                self.calls: list[tuple[int, float]] = []

            def AngleByOwnAxis(self, axis: int, angle: float) -> None:
                self.calls.append((int(axis), float(angle)))

        class _FakeSpiral:
            def __init__(self) -> None:
                self.Position = _FakePosition()

        spiral = _FakeSpiral()
        position_parameters = _FakePositionParameters()

        report = bridge._apply_spiral_turning_angle(
            spiral,
            position_parameters,
            2250.0,
            "orientation",
        )

        self.assertEqual(report["mode"], "position_angle_by_own_axis")
        self.assertEqual(position_parameters.calls, [(73, 2250.0)])
        self.assertEqual(spiral.Position.OrientationType, 0)
        self.assertEqual(spiral.Position.LocalCSParameters.RotationAngle, 33.0)

    def test_bridge_resolve_spring_path_contour_deletes_failed_contour(self) -> None:
        bridge = _load_bridge_module()

        class _FakePositionParameters:
            def __init__(self, path: Any) -> None:
                self._path = path

            def AngleByOwnAxis(self, _axis: int, angle: float) -> None:
                self._path.orientation_angle = float(angle)

        class _FakeSpiralPath:
            def __init__(self, reference: int, angle: float = 0.0) -> None:
                self.Reference = reference
                self.orientation_angle = float(angle)

            def Update(self) -> bool:
                return True

        class _FakeContour:
            def __init__(self, collection: Any) -> None:
                self._collection = collection
                self.Reference = len(collection._items) + 2000
                self.Name = ""
                self.Edges: list[Any] = []
                self.EdgesCount = 1

            def Update(self) -> bool:
                self.EdgesCount = 1
                return True

        class _FakeContours3D:
            def __init__(self) -> None:
                self._items: list[Any] = []
                self.Count = 0

            def Add(self) -> Any:
                contour = _FakeContour(self)
                self._items.append(contour)
                self.Count = len(self._items)
                return contour

            def Item(self, index: int) -> Any:
                return self._items[index]

            def Delete(self, index: int) -> bool:
                self._items.pop(index)
                self.Count = len(self._items)
                return True

        auxiliary_container = types.SimpleNamespace(Contours3D=_FakeContours3D())
        start_path = _FakeSpiralPath(201, 0.0)
        work_path = _FakeSpiralPath(202, 0.0)

        with self.assertRaises(RuntimeError):
            bridge._resolve_spring_path_contour(
                auxiliary_container,
                "SPRING_FAIL",
                [
                    {
                        "role": "start_end",
                        "path": start_path,
                        "position_parameters": _FakePositionParameters(start_path),
                        "applied_orientation_angle": 0.0,
                        "orientation_angle_candidates": [0.0],
                        "angle_application_mode": "default",
                    },
                    {
                        "role": "working",
                        "path": work_path,
                        "position_parameters": _FakePositionParameters(work_path),
                        "applied_orientation_angle": 0.0,
                        "orientation_angle_candidates": [180.0],
                        "angle_application_mode": "orientation",
                    },
                ],
            )

        self.assertEqual(auxiliary_container.Contours3D.Count, 0)

    def test_bridge_delete_curve_contour_falls_back_to_object_delete(self) -> None:
        bridge = _load_bridge_module()

        class _FakeContour:
            def __init__(self) -> None:
                self.Reference = 3001
                self.deleted = False

            def Delete(self) -> bool:
                self.deleted = True
                return True

        class _FakeContours3D:
            def __init__(self, contour: Any) -> None:
                self._items = [contour]
                self.Count = 1

            def Item(self, index: int) -> Any:
                return self._items[index]

        contour = _FakeContour()
        auxiliary_container = types.SimpleNamespace(Contours3D=_FakeContours3D(contour))

        original_delete = bridge._delete_feature_from_collection
        self.addCleanup(setattr, bridge, "_delete_feature_from_collection", original_delete)
        bridge._delete_feature_from_collection = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("feature_delete_not_supported"))

        deleted = bridge._delete_curve_contour(auxiliary_container, contour)

        self.assertTrue(deleted)
        self.assertTrue(contour.deleted)


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        self.calls.append((action, payload))
        return {
            "ok": True,
            "item": {"reference": 42},
            "readback": {
                "before": _snapshot([{"id": "root"}], items=1),
                "after": _snapshot([{"id": "root"}, {"id": "point-1", "type": "Point3D"}], items=2),
            },
        }


class _NoDeltaRunner(_FakeRunner):
    def call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        self.calls.append((action, payload))
        return {
            "ok": True,
            "item": {"reference": 42},
            "readback": {
                "before": _snapshot([{"id": "root"}], items=1),
                "after": _snapshot([{"id": "root"}], items=1),
            },
        }


class _FakePart:
    def __init__(self) -> None:
        self.updated = False

    def Update(self) -> bool:
        self.updated = True
        return True


class _FakePoint3D:
    def __init__(self) -> None:
        self.Name = ""
        self.X = 0.0
        self.Y = 0.0
        self.Z = 0.0
        self.updated = False

    def Update(self) -> bool:
        self.updated = True
        return True


class _FakePoint3DCollection:
    def __init__(self, point: _FakePoint3D) -> None:
        self._point = point
        self.Count = 0
        self.called_as_function = False

    def Add(self) -> _FakePoint3D:
        self.Count += 1
        return self._point

    def __call__(self) -> _FakePoint3D:
        self.called_as_function = True
        return self._point


class _FakeCollection:
    def __init__(self, items: list[Any]) -> None:
        self._items = items
        self.Count = len(items)

    def Item(self, index: int) -> Any:
        return self._items[index]

    def Delete(self, index: int) -> bool:
        self._items.pop(index)
        self.Count = len(self._items)
        return True


class _FakeViews:
    def __init__(self, view: Any) -> None:
        self._view = view

    def View(self, index: int) -> Any:
        return self._view


class _FakeViewsManager:
    def __init__(self, view: Any) -> None:
        self.Views = _FakeViews(view)


class _FakeSketch:
    def __init__(self, name: str, reference: int, sketch_doc: Any) -> None:
        self.Name = name
        self.Reference = reference
        self._sketch_doc = sketch_doc
        self.ended = False
        self.updated = False

    def BeginEdit(self) -> Any:
        return self._sketch_doc

    def EndEdit(self) -> None:
        self.ended = True

    def Update(self) -> bool:
        self.updated = True
        return True


class _FakeSketchEntity:
    def __init__(self, reference: int) -> None:
        self.Reference = reference
        self.updated = False

    def Update(self) -> bool:
        self.updated = True
        return True


class _FakeFeature:
    def __init__(self, name: str, reference: int, *, suppressed: bool = False) -> None:
        self.Name = name
        self.Reference = reference
        self.Suppressed = suppressed
        self.Hidden = False
        self.Type = 1
        self.updated = False

    def Update(self) -> bool:
        self.updated = True
        return True


class _FakeAddCollection:
    def __init__(self, items: list[_FakeSketchEntity]) -> None:
        self._items = items
        self._next = 0
        self.Count = len(items)

    def Add(self) -> _FakeSketchEntity:
        item = self._items[self._next]
        self._next += 1
        return item


def _snapshot(entries: list[dict[str, Any]], *, items: int) -> dict[str, Any]:
    return {
        "ok": True,
        "snapshot": {
            "summary": {"items": items},
            "counts": {"items": items, "indexed_items": len(entries)},
            "manifest": {
                "counts": {"items": items, "indexed_items": len(entries)},
                "item_index": {"entries": entries},
            },
        },
    }


def _load_bridge_module():
    module_name = "kompas_bridge_primitive_write_test_module"
    if module_name in sys.modules:
        return sys.modules[module_name]

    fake_win32com = types.ModuleType("win32com")
    fake_client = types.ModuleType("win32com.client")
    fake_client.Dispatch = lambda obj, *args, **kwargs: obj
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


if __name__ == "__main__":
    unittest.main()
