import unittest
from typing import Any

from kompas_mcp.document_state import get_active_document_state


class DocumentStateTests(unittest.TestCase):
    def test_reads_active_document_state_with_bounded_tree_and_items(self) -> None:
        adapter = _FakeStateAdapter()

        result = get_active_document_state(adapter, include_tree=True, include_items=True, max_items=1)

        self.assertTrue(result["ok"])
        self.assertTrue(result["execution"]["operation_ran"])
        self.assertEqual(result["state"]["document"]["id"], "doc-1")
        self.assertEqual(result["state"]["counts"], {"tree_nodes": 3, "items": 2, "items_returned": 1})
        self.assertEqual(result["state"]["tree_preview"]["children_count"], 2)
        self.assertEqual(len(result["state"]["items_preview"]), 1)
        self.assertEqual(adapter.calls, ["session", "list", "tree:doc-1", "items:doc-1"])

    def test_skips_state_read_after_failed_preflight(self) -> None:
        adapter = _FakeStateAdapter(active_document=None, documents=[])

        result = get_active_document_state(adapter, include_tree=True, include_items=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["execution"]["operation_ran"])
        self.assertNotIn("state", result)
        self.assertEqual(adapter.calls, ["session", "list"])

    def test_classifies_tree_failure_from_operation_stage(self) -> None:
        adapter = _FakeStateAdapter(fail_tree=True)

        result = get_active_document_state(adapter, include_tree=True)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "UNKNOWN_RUNTIME_ERROR")
        self.assertFalse(result["execution"]["operation_ran"])
        self.assertNotIn("state", result)

    def test_reports_malformed_tree_payload_as_failed_state(self) -> None:
        adapter = _MalformedTreeStateAdapter()

        result = get_active_document_state(adapter, include_tree=True)

        self.assertFalse(result["ok"])
        self.assertTrue(result["execution"]["operation_ran"])
        self.assertEqual(result["state"]["tree_preview"], None)
        self.assertEqual(result["state"]["steps"][0]["step"], "read_tree")
        self.assertFalse(result["state"]["steps"][0]["ok"])
        self.assertIn("read_tree", result["result_preview"]["failed_steps"])

    def test_reports_malformed_items_payload_as_failed_state(self) -> None:
        adapter = _MalformedItemsStateAdapter()

        result = get_active_document_state(adapter, include_items=True)

        self.assertFalse(result["ok"])
        self.assertTrue(result["execution"]["operation_ran"])
        self.assertEqual(result["state"]["items_preview"], [])
        self.assertEqual(result["state"]["steps"][0]["step"], "read_items")
        self.assertFalse(result["state"]["steps"][0]["ok"])
        self.assertIn("read_items", result["result_preview"]["failed_steps"])


_SENTINEL = object()


class _FakeStateAdapter:
    def __init__(
        self,
        *,
        active_document: dict[str, Any] | None | object = _SENTINEL,
        documents: list[dict[str, Any]] | None = None,
        fail_tree: bool = False,
    ) -> None:
        self.calls: list[str] = []
        default_document = {"id": "doc-1", "name": "part.m3d", "path": "part.m3d", "type": 5, "active": True}
        self.active_document = default_document if active_document is _SENTINEL else active_document
        self.documents = documents if documents is not None else ([self.active_document] if isinstance(self.active_document, dict) else [])
        self.fail_tree = fail_tree

    def get_session_state(self) -> dict[str, Any]:
        self.calls.append("session")
        return {
            "kompas_connected": True,
            "documents_count": len(self.documents),
            "active_document": self.active_document,
        }

    def list_documents(self) -> dict[str, Any]:
        self.calls.append("list")
        return {"documents": self.documents}

    def get_document_tree(self, document_id: str | None = None) -> dict[str, Any]:
        self.calls.append(f"tree:{document_id}")
        if self.fail_tree:
            raise RuntimeError("Unable to read tree")
        return {
            "document": self.active_document,
            "tree": {
                "id": "root",
                "name": "Part",
                "type": "part",
                "children": [
                    {"id": "sketch-1", "name": "Sketch 1", "type": "sketch"},
                    {"id": "solid-1", "name": "Solid", "type": "feature"},
                ],
            },
        }

    def get_items(self, document_id: str | None = None, item_ids: list[str] | None = None) -> dict[str, Any]:
        self.calls.append(f"items:{document_id}")
        return {
            "document": self.active_document,
            "items": [
                {"id": "sketch-1", "name": "Sketch 1", "type": "sketch", "active": True},
                {"id": "solid-1", "name": "Solid", "type": "feature"},
            ],
        }


class _MalformedTreeStateAdapter(_FakeStateAdapter):
    def get_document_tree(self, document_id: str | None = None) -> Any:
        self.calls.append(f"tree:{document_id}")
        return ["not", "a", "dict"]


class _MalformedItemsStateAdapter(_FakeStateAdapter):
    def get_items(self, document_id: str | None = None, item_ids: list[str] | None = None) -> Any:
        self.calls.append(f"items:{document_id}")
        return {"items": {"not": "a-list"}}


if __name__ == "__main__":
    unittest.main()
