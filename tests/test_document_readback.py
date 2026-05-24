import tempfile
import unittest
from pathlib import Path
from typing import Any

from kompas_mcp.document_readback import (
    build_document_item_index,
    build_document_readback_manifest,
    find_document_items,
    readback_saved_document,
    run_document_readback,
)


class DocumentReadbackTests(unittest.TestCase):
    def test_readback_saved_document_calls_adapter_and_closes_document(self) -> None:
        adapter = _FakeDocumentAdapter()
        payload = readback_saved_document(adapter, "part.m3d")

        self.assertEqual(payload["open_document"]["document"]["id"], "doc-1")
        self.assertEqual(payload["items"]["count"], 2)
        self.assertTrue(payload["close_document"]["closed"])
        self.assertEqual(adapter.calls, ["open", "tree", "items", "list", "close"])

    def test_readback_saved_document_reports_malformed_payloads_without_crashing(self) -> None:
        adapter = _MalformedOpenDocumentAdapter()

        payload = readback_saved_document(adapter, "part.m3d")

        self.assertEqual(payload["open_document"]["error_type"], "TypeError")
        self.assertEqual(payload["document_tree"]["tree"]["id"], "")
        self.assertEqual(adapter.calls, ["open", "tree", "items", "list"])

    def test_run_document_readback_normalizes_counts_and_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model = Path(temp_dir) / "part.m3d"
            model.write_bytes(b"model")

            report = run_document_readback(str(model), _fake_callback, stage="readback")

            self.assertTrue(report["ok"])
            self.assertEqual(report["counts"]["documents"], 1)
            self.assertEqual(report["counts"]["items"], 2)
            self.assertEqual(report["counts"]["tree_nodes"], 2)
            self.assertFalse(report["failures"])

    def test_run_document_readback_reports_callback_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model = Path(temp_dir) / "part.m3d"
            model.write_bytes(b"model")

            report = run_document_readback(str(model), _failing_callback, stage="readback")

            self.assertFalse(report["ok"])
            self.assertEqual(report["error"]["error_type"], "RuntimeError")
            self.assertEqual(report["counts"], {"documents": 0, "items": 0, "tree_nodes": 0})

    def test_build_document_readback_manifest_normalizes_items_and_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model = Path(temp_dir) / "part.m3d"
            model.write_bytes(b"model")
            report = run_document_readback(str(model), _fake_callback, stage="readback")

            manifest = build_document_readback_manifest(report, stage="manifest")

            self.assertTrue(manifest["ok"])
            self.assertEqual(manifest["counts"]["documents"], 1)
            self.assertEqual(manifest["counts"]["items"], 2)
            self.assertEqual(manifest["counts"]["tree_nodes"], 2)
            self.assertEqual(manifest["tree_root"]["id"], "root")
            self.assertEqual(manifest["item_types"]["unknown"], 2)
            self.assertEqual(manifest["counts"]["indexed_items"], 4)
            self.assertEqual(manifest["counts"]["duplicate_ids"], 2)
            self.assertEqual(manifest["counts"]["same_source_duplicate_ids"], 0)
            self.assertEqual(manifest["tree_nodes"][1]["parent_id"], "root")
            self.assertEqual(manifest["item_index"]["counts"]["parent_ids"], 1)

    def test_build_document_readback_manifest_keeps_failures(self) -> None:
        report = {
            "stage": "readback",
            "ok": False,
            "model_path": "part.m3d",
            "failures": [{"name": "open_document", "ok": False}],
            "readback": {},
        }

        manifest = build_document_readback_manifest(report, stage="manifest")

        self.assertFalse(manifest["ok"])
        self.assertEqual(manifest["counts"]["failures"], 1)

    def test_build_document_item_index_supports_low_level_lookup(self) -> None:
        item_index = build_document_item_index(
            tree_nodes=[
                {"id": "root", "name": "Part", "type": "part", "path": "Part"},
                {
                    "id": "root/0",
                    "name": "ThreadSketch",
                    "type": "sketch",
                    "role": "profile_sketch",
                    "parent_id": "root",
                    "parent_path": "Part",
                    "hidden": True,
                    "visible": False,
                    "depth": 1,
                    "children_count": 0,
                },
            ],
            items=[
                {
                    "id": "root/0",
                    "name": "ThreadSketch",
                    "type": "sketch",
                    "role": "profile_sketch",
                    "reference": 101,
                    "hidden": True,
                    "visible": False,
                },
                {
                    "id": "axis-1",
                    "name": "ThreadAxis",
                    "type": "axis",
                    "role": "spiral_axis",
                    "reference": 102,
                    "active": True,
                    "changed": False,
                    "metrics": {"length": 22.001, "origin": {"x": 10.0, "y": 5.0}},
                    "properties": {"layer": "Construction", "owner": "ThreadBuilder"},
                    "geometry": {"kind": "AxisLine", "tags": ["thread", "auxiliary"]},
                },
            ],
        )

        self.assertEqual(item_index["counts"]["entries"], 4)
        self.assertEqual(item_index["counts"]["duplicate_ids"], 1)
        self.assertEqual(item_index["counts"]["same_source_duplicate_ids"], 0)
        self.assertEqual(item_index["duplicate_ids"]["root/0"], [1, 2])

        sketch_items = find_document_items(item_index, item_type="SKETCH", role="profile_sketch")
        self.assertEqual([item["source"] for item in sketch_items], ["tree", "items"])

        tree_sketch_items = find_document_items(item_index, item_type="sketch", role="profile_sketch", source="tree")
        self.assertEqual(len(tree_sketch_items), 1)
        self.assertEqual(tree_sketch_items[0]["source"], "tree")

        child_sketch_items = find_document_items(
            item_index,
            item_type="sketch",
            parent_id="root",
            parent_path_contains="part",
            depth=1,
            children_count=0,
        )
        self.assertEqual(len(child_sketch_items), 1)
        self.assertEqual(child_sketch_items[0]["id"], "root/0")

        axis_items = find_document_items(item_index, reference=102)
        self.assertEqual(len(axis_items), 1)
        self.assertEqual(axis_items[0]["role"], "spiral_axis")

        hidden_sketch_items = find_document_items(item_index, role="profile_sketch", hidden=True, visible=False)
        self.assertEqual(len(hidden_sketch_items), 2)

        active_axis_items = find_document_items(item_index, role="spiral_axis", active=True, changed=False)
        self.assertEqual(len(active_axis_items), 1)
        self.assertEqual(active_axis_items[0]["id"], "axis-1")

        measured_axis_items = find_document_items(
            item_index,
            role="spiral_axis",
            numeric_fields={"metrics.length": 22.0, "metrics.origin.x": {"expected": 10.01, "tolerance": 0.02}},
            numeric_tolerance=0.01,
        )
        self.assertEqual(len(measured_axis_items), 1)
        self.assertEqual(measured_axis_items[0]["id"], "axis-1")

        out_of_tolerance_items = find_document_items(
            item_index,
            role="spiral_axis",
            numeric_fields={"metrics.origin.y": 5.1},
            numeric_tolerance=0.01,
        )
        self.assertEqual(out_of_tolerance_items, [])

        custom_field_items = find_document_items(
            item_index,
            role="spiral_axis",
            field_equals={"properties.layer": "construction", "geometry.tags.0": "thread"},
            field_contains={"properties.owner": "builder", "geometry.kind": "axis"},
            field_has={"geometry.tags": ["thread", "auxiliary"]},
            field_has_contains={"geometry.tags": "aux"},
            field_exists=["properties.layer", "geometry.tags.1"],
            field_missing=["properties.suppressed", "geometry.tags.5"],
        )
        self.assertEqual(len(custom_field_items), 1)
        self.assertEqual(custom_field_items[0]["id"], "axis-1")

        missing_required_field_items = find_document_items(
            item_index,
            role="spiral_axis",
            field_exists=["properties.layer", "properties.suppressed"],
        )
        self.assertEqual(missing_required_field_items, [])

        missing_tag_items = find_document_items(
            item_index,
            role="spiral_axis",
            field_has={"geometry.tags": "temporary"},
        )
        self.assertEqual(missing_tag_items, [])

        missing_custom_field_items = find_document_items(
            item_index,
            role="spiral_axis",
            field_equals={"properties.layer": "model"},
        )
        self.assertEqual(missing_custom_field_items, [])

    def test_find_document_items_supports_contains_filters(self) -> None:
        item_index = build_document_item_index(
            tree_nodes=[
                {"id": "root", "name": "Part", "type": "part"},
                {"id": "sketch-1", "name": "Thread_Profile_Sketch", "type": "ksSketchDefinition", "role": "profile_sketch"},
            ],
            items=[
                {
                    "id": "axis-1",
                    "name": "ThreadAxis",
                    "type": "axis",
                    "role": "spiral_axis",
                    "path": "Part/Construction/ThreadAxis",
                }
            ],
        )

        sketch_items = find_document_items(item_index, name_contains="profile", item_type_contains="sketch")
        self.assertEqual(len(sketch_items), 1)
        self.assertEqual(sketch_items[0]["id"], "sketch-1")

        axis_items = find_document_items(item_index, path_contains="construction/thread", source="items")
        self.assertEqual(len(axis_items), 1)
        self.assertEqual(axis_items[0]["role"], "spiral_axis")

    def test_find_document_items_supports_live_part_scalar_fields(self) -> None:
        item_index = build_document_item_index(
            tree_nodes=[],
            items=[
                {
                    "id": "root",
                    "name": "Real external M12x1 after sketch-runtime preflight",
                    "type": "part",
                    "reference": 1073745002,
                    "designation": "M12x1",
                    "density": 7.856,
                    "material": "Steel 10 GOST 1050-2013",
                    "source_path": r"C:\work\real_ext_m12x1_sketch_runtime_checked.m3d",
                    "mass": 34.49550468149512,
                }
            ],
        )

        part_items = find_document_items(
            item_index,
            item_type="part",
            field_equals={"designation": "M12x1"},
            field_contains={"material": "gost", "source_path": "sketch_runtime_checked"},
            numeric_fields={"density": 7.856, "mass": {"expected": 34.5, "tolerance": 0.01}},
        )

        self.assertEqual(len(part_items), 1)
        self.assertEqual(part_items[0]["id"], "root")

    def test_find_document_items_rejects_malformed_filter_payloads_without_exception(self) -> None:
        item_index = build_document_item_index(
            tree_nodes=[{"id": "root", "name": "Part", "type": "part"}],
            items=[{"id": "axis-1", "role": "spiral_axis", "metrics": {"length": 10}}],
        )

        self.assertEqual(find_document_items(["not", "an", "index"], role="spiral_axis"), [])
        self.assertEqual(find_document_items({"entries": [], "by_role": []}, role="spiral_axis"), [])
        self.assertEqual(find_document_items(item_index, field_equals=["properties.layer"]), [])
        self.assertEqual(find_document_items(item_index, field_contains=["axis"]), [])
        self.assertEqual(find_document_items(item_index, field_has=["thread"]), [])
        self.assertEqual(find_document_items(item_index, field_has_contains=["thread"]), [])
        self.assertEqual(find_document_items(item_index, numeric_fields=["metrics.length"]), [])
        self.assertEqual(find_document_items(item_index, numeric_fields={"metrics.length": 10}, numeric_tolerance="wide"), [])
        self.assertEqual(
            find_document_items(item_index, numeric_fields={"metrics.length": {"expected": 10, "tolerance": "wide"}}),
            [],
        )

    def test_build_document_item_index_reports_same_source_duplicate_ids(self) -> None:
        item_index = build_document_item_index(
            tree_nodes=[
                {"id": "root", "name": "Part", "type": "part"},
                {"id": "sketch-1", "name": "SketchA", "type": "sketch"},
                {"id": "sketch-1", "name": "SketchB", "type": "sketch"},
            ],
            items=[],
        )

        self.assertEqual(item_index["counts"]["duplicate_ids"], 1)
        self.assertEqual(item_index["counts"]["same_source_duplicate_ids"], 1)
        self.assertEqual(item_index["same_source_duplicate_ids"]["sketch-1"], [1, 2])


class _FakeDocumentAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.document = {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}

    def open_document(self, path: str, *, visible: bool, read_only: bool) -> dict[str, Any]:
        self.calls.append("open")
        return {"document": self.document, "visible": visible, "read_only": read_only}

    def get_document_tree(self, *, document_id: str) -> dict[str, Any]:
        self.calls.append("tree")
        return {"document": self.document, "tree": {"id": document_id, "children": [{"id": "solid"}]}}

    def get_items(self, *, document_id: str) -> dict[str, Any]:
        self.calls.append("items")
        return {"document": self.document, "items": [{"id": document_id}, {"id": "solid"}], "count": 2}

    def list_documents(self) -> dict[str, Any]:
        self.calls.append("list")
        return {"documents": [self.document]}

    def close_document(self, *, document_id: str, save: bool) -> dict[str, Any]:
        self.calls.append("close")
        return {"document": self.document, "closed": True, "save": save}


class _MalformedOpenDocumentAdapter(_FakeDocumentAdapter):
    def open_document(self, path: str, *, visible: bool, read_only: bool) -> Any:
        self.calls.append("open")
        return ["not", "a", "dict"]


def _fake_callback(model_path: str) -> dict[str, Any]:
    document = {"id": model_path, "name": Path(model_path).name, "path": model_path}
    tree = {"id": "root", "children": [{"id": "solid"}]}
    return {
        "open_document": {"document": document},
        "document_tree": {"document": document, "tree": tree},
        "items": {"document": document, "items": [{"id": "root"}, {"id": "solid"}], "count": 2},
        "list_documents": {"documents": [document]},
        "close_document": {"document": document, "closed": True},
    }


def _failing_callback(model_path: str) -> dict[str, Any]:
    raise RuntimeError(f"cannot read {model_path}")


if __name__ == "__main__":
    unittest.main()
