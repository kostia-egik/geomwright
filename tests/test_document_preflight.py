import unittest
from typing import Any

from kompas_mcp.document_preflight import preflight_document_context


class DocumentPreflightTests(unittest.TestCase):
    def test_preflight_active_document_with_tree_and_items(self) -> None:
        adapter = _FakePreflightAdapter()

        result = preflight_document_context(
            adapter,
            expected_document_type=5,
            expected_extensions=["m3d"],
            require_tree=True,
            min_tree_nodes=2,
            require_items=True,
            min_items=2,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["document"]["id"], "doc-1")
        self.assertEqual(result["readback"], {"tree_nodes": 2, "items": 2})
        self.assertEqual(adapter.calls, ["session", "list", "tree:doc-1", "items:doc-1"])

    def test_preflight_reports_missing_active_document_without_readback_calls(self) -> None:
        adapter = _FakePreflightAdapter(active_document=None, documents=[])

        result = preflight_document_context(adapter, require_tree=True, require_items=True)

        self.assertFalse(result["ok"])
        checks = {check["name"]: check for check in result["checks"]}
        self.assertFalse(checks["document_selected"]["ok"])
        self.assertFalse(checks["active_document_selected"]["ok"])
        self.assertNotIn("document_tree_readback", checks)
        self.assertEqual(adapter.calls, ["session", "list"])

    def test_preflight_reports_tree_failure_as_check(self) -> None:
        adapter = _FakePreflightAdapter(fail_tree=True)

        result = preflight_document_context(adapter, require_tree=True)

        self.assertFalse(result["ok"])
        checks = {check["name"]: check for check in result["checks"]}
        self.assertFalse(checks["document_tree_readback"]["ok"])
        self.assertIn("TopPart missing", checks["document_tree_readback"]["actual"]["error"])
        self.assertEqual(
            checks["document_tree_readback"]["actual"]["classification"]["code"],
            "UNKNOWN_RUNTIME_ERROR",
        )
        self.assertFalse(checks["min_tree_nodes"]["ok"])

    def test_preflight_can_select_document_by_id_without_requiring_active(self) -> None:
        adapter = _FakePreflightAdapter(
            active_document={"id": "doc-1", "name": "first.m3d", "path": "first.m3d", "type": 5, "active": True},
            documents=[
                {"id": "doc-1", "name": "first.m3d", "path": "first.m3d", "type": 5, "active": True},
                {"id": "doc-2", "name": "second.a3d", "path": "second.a3d", "type": 7, "active": False},
            ],
        )

        result = preflight_document_context(
            adapter,
            document_id="doc-2",
            require_active_document=False,
            expected_document_type="7",
            expected_extensions=[".a3d"],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["document"]["id"], "doc-2")

    def test_preflight_reports_malformed_session_payload(self) -> None:
        adapter = _FakePreflightAdapter(malformed_session=True)

        result = preflight_document_context(adapter)

        self.assertFalse(result["ok"])
        checks = {check["name"]: check for check in result["checks"]}
        self.assertFalse(checks["session_state"]["ok"])
        self.assertEqual(checks["session_state"]["actual"]["type"], "list")

    def test_preflight_reports_malformed_list_documents_payload(self) -> None:
        adapter = _FakePreflightAdapter(malformed_list=True)

        result = preflight_document_context(adapter, require_active_document=False)

        self.assertFalse(result["ok"])
        checks = {check["name"]: check for check in result["checks"]}
        self.assertFalse(checks["list_documents"]["ok"])
        self.assertEqual(checks["list_documents"]["actual"]["type"], "str")

    def test_preflight_reports_malformed_tree_payload(self) -> None:
        adapter = _FakePreflightAdapter(malformed_tree=True)

        result = preflight_document_context(adapter, require_tree=True)

        self.assertFalse(result["ok"])
        checks = {check["name"]: check for check in result["checks"]}
        self.assertFalse(checks["document_tree_readback"]["ok"])
        self.assertEqual(checks["document_tree_readback"]["actual"]["type"], "list")
        self.assertFalse(checks["min_tree_nodes"]["ok"])

    def test_preflight_reports_malformed_items_payload(self) -> None:
        adapter = _FakePreflightAdapter(malformed_items=True)

        result = preflight_document_context(adapter, require_items=True)

        self.assertFalse(result["ok"])
        checks = {check["name"]: check for check in result["checks"]}
        self.assertFalse(checks["document_items_readback"]["ok"])
        self.assertEqual(checks["document_items_readback"]["actual"]["type"], "NoneType")
        self.assertFalse(checks["min_items"]["ok"])


_SENTINEL = object()


class _FakePreflightAdapter:
    def __init__(
        self,
        *,
        active_document: dict[str, Any] | None | object = _SENTINEL,
        documents: list[dict[str, Any]] | None = None,
        fail_tree: bool = False,
        malformed_session: bool = False,
        malformed_list: bool = False,
        malformed_tree: bool = False,
        malformed_items: bool = False,
    ) -> None:
        self.calls: list[str] = []
        default_document = {"id": "doc-1", "name": "part.m3d", "path": "part.m3d", "type": 5, "active": True}
        self.active_document = default_document if active_document is _SENTINEL else active_document
        self.documents = documents if documents is not None else ([self.active_document] if isinstance(self.active_document, dict) else [])
        self.fail_tree = fail_tree
        self.malformed_session = malformed_session
        self.malformed_list = malformed_list
        self.malformed_tree = malformed_tree
        self.malformed_items = malformed_items

    def get_session_state(self) -> dict[str, Any]:
        self.calls.append("session")
        if self.malformed_session:
            return []  # type: ignore[return-value]
        return {
            "kompas_connected": True,
            "documents_count": len(self.documents),
            "active_document": self.active_document,
        }

    def list_documents(self) -> dict[str, Any]:
        self.calls.append("list")
        if self.malformed_list:
            return "not-documents"  # type: ignore[return-value]
        return {"documents": self.documents}

    def get_document_tree(self, document_id: str | None = None) -> dict[str, Any]:
        self.calls.append(f"tree:{document_id}")
        if self.fail_tree:
            raise RuntimeError("TopPart missing")
        if self.malformed_tree:
            return []  # type: ignore[return-value]
        return {
            "document": self.active_document,
            "tree": {"id": "doc-1", "name": "Part", "children": [{"id": "solid", "name": "Solid"}]},
        }

    def get_items(self, document_id: str | None = None, item_ids: list[str] | None = None) -> dict[str, Any]:
        self.calls.append(f"items:{document_id}")
        if self.malformed_items:
            return None  # type: ignore[return-value]
        return {
            "document": self.active_document,
            "items": [{"id": "doc-1", "name": "Part"}, {"id": "solid", "name": "Solid"}],
        }


if __name__ == "__main__":
    unittest.main()
