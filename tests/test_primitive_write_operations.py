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
            return sketch, {"mode": "create_new_sketch", "name": "SK_BATCH", "plane": "xoy_plane", "sketch_ref": 100}, entity_results

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
        self.assertEqual(result["readback"]["after"]["snapshot"]["counts"]["items"], 2)

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

        _, target, results = bridge._create_sketch_entities(
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
        self.assertEqual([item["kind"] for item in results], ["point", "polyline", "arc", "ellipse"])
        self.assertEqual(results[1]["line_count"], 2)
        self.assertTrue(all(entity.updated for bucket in created_entities.values() for entity in bucket))
        self.assertTrue(sketch.ended)
        self.assertTrue(sketch.updated)

    def test_bridge_create_sketch_entities_targets_existing_sketch_ref(self) -> None:
        bridge = _load_bridge_module()
        line = _FakeSketchEntity(401)
        view = types.SimpleNamespace(LineSegments=_FakeAddCollection([line]))
        sketch_doc = types.SimpleNamespace(ViewsAndLayersManager=_FakeViewsManager(view))
        existing = _FakeSketch("SK_EXISTING", 100, sketch_doc)
        other = _FakeSketch("SK_OTHER", 99, sketch_doc)
        part = types.SimpleNamespace(Sketchs=_FakeCollection([other, existing]))

        sketch, target, results = bridge._create_sketch_entities(
            part,
            part,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": "100"},
                "entities": [{"kind": "segment", "start": [0.0, 0.0], "end": [10.0, 0.0], "line_style": 1}],
            },
        )

        self.assertIs(sketch, existing)
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
