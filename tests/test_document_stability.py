import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from kompas_mcp.document_stability import verify_document_readback_stability


class DocumentReadbackStabilityTests(unittest.TestCase):
    def test_verifies_stable_consecutive_snapshots(self) -> None:
        adapter = _FakeStabilityAdapter()

        result = verify_document_readback_stability(adapter, document_id="doc-1")

        self.assertTrue(result["ok"])
        self.assertEqual(result["delta"]["summary"]["added_items"], 0)
        self.assertEqual(result["snapshots"]["before"]["counts"]["items"], 2)
        self.assertNotIn("manifest", result["snapshots"]["before"])
        self.assertEqual(adapter.items_calls, 2)

    def test_reports_unstable_readback_delta(self) -> None:
        adapter = _FakeStabilityAdapter(after_items=[{"id": "doc-1"}, {"id": "solid"}, {"id": "late"}])

        result = verify_document_readback_stability(adapter, document_id="doc-1")

        failure_names = [item["name"] for item in result["failures"]]
        self.assertFalse(result["ok"])
        self.assertIn("readback_stability_ok", failure_names)
        self.assertIn("stability:snapshot_delta_added_items", failure_names)
        self.assertEqual(result["delta"]["summary"]["added_items"], 1)

    def test_can_ignore_noisy_readback_fields(self) -> None:
        adapter = _FakeStabilityAdapter(
            before_items=[{"id": "doc-1"}, {"id": "solid", "properties": {"timestamp": "10:00"}, "session_id": "a"}],
            after_items=[{"id": "doc-1"}, {"id": "solid", "properties": {"timestamp": "10:01"}, "session_id": "b"}],
        )

        result = verify_document_readback_stability(
            adapter,
            document_id="doc-1",
            ignore_paths=["properties.timestamp"],
            ignore_keys=["session_id"],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["delta"]["summary"]["changed_items"], 0)
        self.assertEqual(result["delta"]["ignored"]["keys"], ["session_id"])

    def test_can_use_default_volatile_ignores(self) -> None:
        adapter = _FakeStabilityAdapter(
            before_items=[{"id": "doc-1"}, {"id": "solid", "timestamp": "10:00", "session_id": "a"}],
            after_items=[{"id": "doc-1"}, {"id": "solid", "timestamp": "10:01", "session_id": "b"}],
        )

        result = verify_document_readback_stability(
            adapter,
            document_id="doc-1",
            use_default_volatile_ignores=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["delta"]["summary"]["changed_items"], 0)
        self.assertTrue(result["delta"]["ignored"]["default_volatile"])
        self.assertIn("timestamp", result["delta"]["ignored"]["keys"])

    def test_can_write_before_and_after_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            before_path = Path(temp_dir) / "before.json"
            after_path = Path(temp_dir) / "after.json"

            result = verify_document_readback_stability(
                _FakeStabilityAdapter(),
                document_id="doc-1",
                before_output_path=before_path,
                after_output_path=after_path,
            )

            self.assertTrue(result["ok"])
            self.assertEqual({row["role"] for row in result["artifacts"]}, {"before_snapshot", "after_snapshot"})
            self.assertIn("manifest", json.loads(before_path.read_text(encoding="utf-8")))
            self.assertIn("manifest", json.loads(after_path.read_text(encoding="utf-8")))

    def test_skips_after_snapshot_when_before_snapshot_fails(self) -> None:
        adapter = _FakeStabilityAdapter(active_document=None, documents=[])

        result = verify_document_readback_stability(adapter)

        self.assertFalse(result["ok"])
        self.assertEqual(adapter.items_calls, 0)
        self.assertIn("before_snapshot_ok", [item["name"] for item in result["failures"]])
        self.assertIn("after_snapshot_ran", [item["name"] for item in result["failures"]])
        self.assertIn("before_snapshot:preflight_ok", [item["name"] for item in result["failures"]])


_SENTINEL = object()


class _FakeStabilityAdapter:
    def __init__(
        self,
        *,
        active_document: dict[str, Any] | None | object = _SENTINEL,
        documents: list[dict[str, Any]] | None = None,
        before_items: list[dict[str, Any]] | None = None,
        after_items: list[dict[str, Any]] | None = None,
    ) -> None:
        default_document = {"id": "doc-1", "name": "part.m3d", "path": "part.m3d", "type": 5, "active": True}
        self.document = default_document if active_document is _SENTINEL else active_document
        self.documents = documents if documents is not None else ([self.document] if isinstance(self.document, dict) else [])
        self.before_items = before_items or [{"id": "doc-1", "name": "Part"}, {"id": "solid", "name": "Solid"}]
        self.after_items = after_items or list(self.before_items)
        self.items_calls = 0

    def get_session_state(self) -> dict[str, Any]:
        return {
            "kompas_connected": True,
            "documents_count": len(self.documents),
            "active_document": self.document,
        }

    def list_documents(self) -> dict[str, Any]:
        return {"documents": self.documents}

    def get_document_tree(self, *, document_id: str | None) -> dict[str, Any]:
        return {
            "document": self.document,
            "tree": {"id": "doc-1", "name": "Part", "children": [{"id": "solid", "name": "Solid"}]},
        }

    def get_items(self, *, document_id: str | None) -> dict[str, Any]:
        self.items_calls += 1
        items = self.before_items if self.items_calls == 1 else self.after_items
        return {"document": self.document, "items": items, "count": len(items)}


if __name__ == "__main__":
    unittest.main()
