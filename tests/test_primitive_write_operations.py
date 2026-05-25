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

    def test_update_sketch_entity_geometry_validates_payload_before_bridge_call(self) -> None:
        runner = _FakeRunner()
        adapter = KompasAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.update_sketch_entity_geometry(entity={"kind": "segment", "index": 0}, geometry={"start": [0, 0], "end": [1, 0]})
        with self.assertRaises(ValueError):
            adapter.update_sketch_entity_geometry(sketch_ref=100, entity={"kind": "arc", "index": 0}, geometry={})
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
