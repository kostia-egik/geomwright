import unittest
import importlib.util
from pathlib import Path

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.tool_catalog import get_mcp_tool_catalog


class ModelObjectProbeTests(unittest.TestCase):
    def test_adapter_calls_bridge_probe_action(self) -> None:
        runner = _RecordingRunner()
        adapter = KompasAdapter(runner=runner)

        result = adapter.probe_model_object_collections(
            document_id="doc-1",
            max_items=3,
            include_empty=False,
        )

        self.assertEqual(result["ok"], True)
        self.assertEqual(runner.calls, [
            (
                "probe_model_object_collections",
                {"document_id": "doc-1", "max_items": 3, "include_empty": False},
            )
        ])

    def test_probe_is_listed_in_low_level_catalog(self) -> None:
        catalog = get_mcp_tool_catalog(category="low_level_runtime")
        tools = catalog["categories"][0]["tools"]

        self.assertIn("probe_model_object_collections", tools)

    def test_bridge_probe_reports_auxiliary_and_surface_collections(self) -> None:
        bridge = _load_bridge_module()
        part = _FakePart()

        probe = bridge.probe_model_object_collections(part, max_items=1, include_empty=True)

        self.assertEqual(probe["summary"]["surface_count"], 3)
        self.assertEqual(probe["summary"]["surface_total_items"], 3)
        surfaces = {item["name"]: item for item in probe["surfaces"]}
        self.assertEqual(surfaces["model_container"]["summary"]["total_items"], 1)
        self.assertEqual(surfaces["auxiliary_geometry"]["summary"]["total_items"], 2)
        aux_collections = {item["name"]: item for item in surfaces["auxiliary_geometry"]["collections"]}
        self.assertEqual(aux_collections["axes3d"]["count"], 1)
        self.assertEqual(aux_collections["local_coordinate_systems"]["count"], 1)
        self.assertEqual(aux_collections["axes3d"]["preview"][0]["name"], "Axis A")

    def test_bridge_runtime_object_probe_reports_transient_handles(self) -> None:
        bridge = _load_bridge_module()
        runtime_objects = {
            "pt1": {
                "scenario": "point",
                "point": _FakeItem("PT1", "pt-1"),
            },
            "lcs1": {
                "scenario": "lcs",
                "lcs": _FakeItem("LCS1", "lcs-1"),
            },
        }

        probe = bridge.probe_runtime_objects(runtime_objects, max_items=1)

        self.assertEqual(probe["summary"]["operation_count"], 2)
        self.assertEqual(probe["summary"]["total_outputs"], 2)
        self.assertEqual(probe["summary"]["preview_count"], 1)
        self.assertEqual(probe["summary"]["output_type_counts"], {"lcs": 1, "point": 1})
        self.assertEqual(probe["summary"]["object_type_counts"], {"_FakeItem": 2})
        self.assertEqual(probe["operations"][0]["outputs"][0]["object"]["name"], "LCS1")


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls = []

    def call(self, action, payload=None):
        self.calls.append((action, payload or {}))
        return {"ok": True, "action": action, "payload": payload or {}}


class _FakeItem:
    def __init__(self, name, reference):
        self.Name = name
        self.Reference = reference
        self.Visible = True


class _FakeCollection:
    def __init__(self, items):
        self._items = list(items)
        self.Count = len(self._items)

    def Item(self, index):
        if index < 0:
            raise IndexError(index)
        if index < len(self._items):
            return self._items[index]
        one_based = index - 1
        if 0 <= one_based < len(self._items):
            return self._items[one_based]
        raise IndexError(index)


class _FakePart:
    def __init__(self):
        self.Sketchs = _FakeCollection([_FakeItem("Sketch A", "sketch-a")])
        self.Axes3D = _FakeCollection([_FakeItem("Axis A", "axis-a")])
        self.LocalCoordinateSystems = _FakeCollection([_FakeItem("LCS A", "lcs-a")])


def _load_bridge_module():
    path = Path(__file__).resolve().parents[1] / "bridge" / "kompas_bridge.py"
    spec = importlib.util.spec_from_file_location("test_kompas_bridge_probe", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
