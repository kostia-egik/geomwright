import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from kompas_mcp.document_probe import probe_document_readback


class DocumentProbeTests(unittest.TestCase):
    def test_probe_active_document_builds_manifest_without_opening_file(self) -> None:
        adapter = _FakeProbeAdapter()

        result = probe_document_readback(adapter, document_id="doc-1")

        self.assertTrue(result["ok"])
        self.assertEqual(result["probe"]["mode"], "active_document")
        self.assertEqual(result["summary"]["tree_nodes"], 2)
        self.assertEqual(result["summary"]["indexed_items"], 4)
        self.assertEqual(result["manifest"]["open"]["ok"], True)
        self.assertEqual(adapter.calls, ["tree:doc-1", "items:doc-1", "list"])

    def test_probe_opened_file_can_write_json_artifact_and_closes_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = _FakeProbeAdapter()
            model = Path(temp_dir) / "part.m3d"
            model.write_bytes(b"model")
            output_path = Path(temp_dir) / "probe.json"

            result = probe_document_readback(
                adapter,
                model_path=str(model),
                output_path=output_path,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["probe"]["mode"], "open_file")
            self.assertEqual(result["artifact"]["path"], str(output_path))
            self.assertTrue(output_path.exists())
            artifact = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["summary"]["items"], 2)
            self.assertEqual(adapter.calls, ["open", "tree:doc-1", "items:doc-1", "list", "close"])

    def test_probe_opened_file_can_leave_document_open_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = _FakeProbeAdapter()
            model = Path(temp_dir) / "part.m3d"
            model.write_bytes(b"model")

            result = probe_document_readback(adapter, model_path=str(model), close_after_probe=False)

            self.assertTrue(result["ok"])
            self.assertFalse(result["probe"]["close_after_probe"])
            self.assertEqual(adapter.calls, ["open", "tree:doc-1", "items:doc-1", "list"])

    def test_probe_rejects_model_path_with_document_id(self) -> None:
        with self.assertRaises(ValueError):
            probe_document_readback(_FakeProbeAdapter(), model_path="part.m3d", document_id="doc-1")

    def test_probe_reports_malformed_tree_payload_without_crashing(self) -> None:
        adapter = _MalformedTreeProbeAdapter()

        result = probe_document_readback(adapter, document_id="doc-1")

        self.assertFalse(result["ok"])
        self.assertEqual(result["manifest"]["counts"]["tree_nodes"], 0)
        failures = [item["name"] for item in result["manifest"]["failures"]]
        self.assertIn("document_tree", failures)

    def test_probe_reports_close_exception_without_crashing(self) -> None:
        adapter = _CloseFailingProbeAdapter()

        result = probe_document_readback(adapter, model_path="part.m3d")

        self.assertFalse(result["ok"])
        self.assertEqual(result["manifest"]["close"]["closed"], None)
        failures = [item["name"] for item in result["manifest"]["failures"]]
        self.assertIn("close_document", failures)

    def test_probe_reports_artifact_write_error_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = probe_document_readback(
                _FakeProbeAdapter(),
                document_id="doc-1",
                output_path=temp_dir,
            )

            self.assertFalse(result["ok"])
            self.assertFalse(result["artifact"]["written"])
            self.assertEqual(result["artifact"]["error_type"], "PermissionError")
            failures = [item["name"] for item in result["failures"]]
            self.assertIn("artifact_write", failures)


class _FakeProbeAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.document = {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}

    def open_document(self, path: str, *, visible: bool, read_only: bool) -> dict[str, Any]:
        self.calls.append("open")
        return {"document": self.document, "visible": visible, "read_only": read_only}

    def get_document_tree(self, *, document_id: str | None) -> dict[str, Any]:
        self.calls.append(f"tree:{document_id}")
        return {
            "document": self.document,
            "tree": {"id": "doc-1", "name": "Part", "children": [{"id": "solid", "name": "Solid"}]},
        }

    def get_items(self, *, document_id: str | None) -> dict[str, Any]:
        self.calls.append(f"items:{document_id}")
        return {
            "document": self.document,
            "items": [{"id": "doc-1", "name": "Part"}, {"id": "solid", "name": "Solid"}],
            "count": 2,
        }

    def list_documents(self) -> dict[str, Any]:
        self.calls.append("list")
        return {"documents": [self.document]}

    def close_document(self, *, document_id: str, save: bool) -> dict[str, Any]:
        self.calls.append("close")
        return {"document": self.document, "closed": True, "save": save}


class _MalformedTreeProbeAdapter(_FakeProbeAdapter):
    def get_document_tree(self, *, document_id: str | None) -> Any:
        self.calls.append(f"tree:{document_id}")
        return ["not", "a", "dict"]


class _CloseFailingProbeAdapter(_FakeProbeAdapter):
    def close_document(self, *, document_id: str, save: bool) -> dict[str, Any]:
        self.calls.append("close")
        raise RuntimeError("close failed")


if __name__ == "__main__":
    unittest.main()
