import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from kompas_mcp.document_snapshot import capture_document_snapshot


class DocumentSnapshotTests(unittest.TestCase):
    def test_captures_active_document_snapshot_without_full_manifest_by_default(self) -> None:
        adapter = _FakeSnapshotAdapter()

        result = capture_document_snapshot(adapter, document_id="doc-1")

        self.assertTrue(result["ok"])
        self.assertTrue(result["execution"]["operation_ran"])
        self.assertEqual(result["snapshot"]["document"]["id"], "doc-1")
        self.assertEqual(result["snapshot"]["summary"]["indexed_items"], 4)
        self.assertEqual(result["snapshot"]["index_counts"]["entries"], 4)
        self.assertNotIn("manifest", result["snapshot"])
        self.assertEqual(adapter.calls, ["session", "list", "tree:doc-1", "items:doc-1", "list"])

    def test_can_write_full_snapshot_artifact_for_active_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "snapshot.json"
            adapter = _FakeSnapshotAdapter()

            result = capture_document_snapshot(adapter, document_id="doc-1", output_path=output_path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["snapshot"]["artifact"]["path"], str(output_path))
            self.assertTrue(result["artifacts"][0]["exists"])
            artifact = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn("manifest", artifact)
            self.assertEqual(artifact["summary"]["tree_nodes"], 2)

    def test_can_include_manifest_when_requested(self) -> None:
        result = capture_document_snapshot(_FakeSnapshotAdapter(), document_id="doc-1", include_manifest=True)

        self.assertTrue(result["ok"])
        self.assertIn("manifest", result["snapshot"])
        self.assertEqual(result["snapshot"]["manifest"]["counts"]["tree_nodes"], 2)

    def test_opened_file_snapshot_closes_by_default(self) -> None:
        adapter = _FakeSnapshotAdapter()

        result = capture_document_snapshot(adapter, model_path="part.m3d")

        self.assertTrue(result["ok"])
        self.assertEqual(adapter.calls, ["open", "tree:doc-1", "items:doc-1", "list", "close"])
        self.assertTrue(result["snapshot"]["probe"]["close_after_probe"])

    def test_skips_snapshot_after_failed_preflight(self) -> None:
        adapter = _FakeSnapshotAdapter(active_document=None, documents=[])

        result = capture_document_snapshot(adapter, document_id=None)

        self.assertFalse(result["ok"])
        self.assertFalse(result["execution"]["operation_ran"])
        self.assertNotIn("snapshot", result)
        self.assertEqual(adapter.calls, ["session", "list"])

    def test_failed_probe_details_are_visible_in_snapshot_preview(self) -> None:
        adapter = _MalformedTreeSnapshotAdapter()

        result = capture_document_snapshot(adapter, document_id="doc-1")

        self.assertFalse(result["ok"])
        self.assertTrue(result["execution"]["operation_ran"])
        self.assertIn("document_tree", result["result_preview"]["failed_steps"])
        self.assertIn("document_tree", [step["step"] for step in result["snapshot"]["steps"]])


_SENTINEL = object()


class _FakeSnapshotAdapter:
    def __init__(
        self,
        *,
        active_document: dict[str, Any] | None | object = _SENTINEL,
        documents: list[dict[str, Any]] | None = None,
    ) -> None:
        self.calls: list[str] = []
        default_document = {"id": "doc-1", "name": "part.m3d", "path": "part.m3d", "type": 5, "active": True}
        self.document = default_document if active_document is _SENTINEL else active_document
        self.documents = documents if documents is not None else ([self.document] if isinstance(self.document, dict) else [])

    def get_session_state(self) -> dict[str, Any]:
        self.calls.append("session")
        return {
            "kompas_connected": True,
            "documents_count": len(self.documents),
            "active_document": self.document,
        }

    def list_documents(self) -> dict[str, Any]:
        self.calls.append("list")
        return {"documents": self.documents}

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

    def close_document(self, *, document_id: str, save: bool) -> dict[str, Any]:
        self.calls.append("close")
        return {"document": self.document, "closed": True, "save": save}


class _MalformedTreeSnapshotAdapter(_FakeSnapshotAdapter):
    def get_document_tree(self, *, document_id: str | None) -> Any:
        self.calls.append(f"tree:{document_id}")
        return ["not", "a", "dict"]


if __name__ == "__main__":
    unittest.main()
