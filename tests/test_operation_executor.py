import unittest

from kompas_mcp.operation_executor import execute_primitive_operation
from kompas_mcp.operation_runtime import DocumentReadbackContractSpec


class PrimitiveOperationExecutorTests(unittest.TestCase):
    def test_runs_preflight_operation_and_readback_contract(self) -> None:
        calls: list[str] = []

        def run_operation() -> dict:
            calls.append("operation")
            return {"ok": True, "id": "line-1", "type": "line"}

        result = execute_primitive_operation(
            "create_line",
            run_operation,
            preflight={"ok": True, "checks": [{"name": "active_document", "ok": True}]},
            readback=_readback_report(),
            readback_contract_spec=DocumentReadbackContractSpec(
                require_path_match=False,
                require_close_document=False,
                expected_items=({"id": "line-1", "type": "line", "unique": True},),
            ),
        )

        self.assertEqual(calls, ["operation"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["execution"]["operation_ran"])
        self.assertTrue(result["execution"]["readback_contract_ran"])
        self.assertEqual(result["result_preview"]["id"], "line-1")

    def test_skips_operation_after_failed_preflight(self) -> None:
        calls: list[str] = []

        result = execute_primitive_operation(
            "create_line",
            lambda: calls.append("operation") or {"ok": True},
            preflight={"ok": False, "checks": [{"name": "document_type", "ok": False}]},
        )

        self.assertEqual(calls, [])
        self.assertFalse(result["ok"])
        self.assertFalse(result["execution"]["operation_ran"])
        failure_names = [item["name"] for item in result["failures"]]
        self.assertIn("preflight_ok", failure_names)
        self.assertIn("operation_skipped_after_preflight", failure_names)

    def test_classifies_operation_exception(self) -> None:
        def run_operation() -> dict:
            raise RuntimeError("No active document")

        result = execute_primitive_operation(
            "get_active_document",
            run_operation,
            preflight={"ok": True},
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["execution"]["preflight_ran"])
        self.assertFalse(result["execution"]["operation_ran"])
        self.assertEqual(result["error"]["code"], "NO_ACTIVE_DOCUMENT")

    def test_records_readback_exception_after_operation(self) -> None:
        def readback() -> dict:
            raise RuntimeError("Readback returned empty payload")

        result = execute_primitive_operation(
            "create_line",
            lambda: {"ok": True, "id": "line-1"},
            preflight={"ok": True},
            readback=readback,
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["execution"]["operation_ran"])
        self.assertFalse(result["execution"]["readback_ran"])
        self.assertEqual(result["error"]["code"], "EMPTY_READBACK")

    def test_reports_non_object_preflight_payload_as_failure(self) -> None:
        calls: list[str] = []

        result = execute_primitive_operation(
            "create_line",
            lambda: calls.append("operation") or {"ok": True},
            preflight=lambda: [],
        )

        self.assertEqual(calls, [])
        self.assertFalse(result["ok"])
        self.assertFalse(result["execution"]["preflight_ran"])
        self.assertFalse(result["execution"]["operation_ran"])
        self.assertEqual(result["error"]["exception_type"], "TypeError")
        self.assertIn("operation payload must be dict", result["error"]["message"])

    def test_reports_non_object_readback_payload_as_failure(self) -> None:
        result = execute_primitive_operation(
            "create_line",
            lambda: {"ok": True, "id": "line-1"},
            preflight={"ok": True},
            readback=lambda: [],
            readback_contract_spec=DocumentReadbackContractSpec(),
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["execution"]["operation_ran"])
        self.assertFalse(result["execution"]["readback_ran"])
        self.assertFalse(result["execution"]["readback_contract_ran"])
        self.assertEqual(result["error"]["exception_type"], "TypeError")


def _readback_report() -> dict:
    return {
        "ok": True,
        "model_path": "part.m3d",
        "document": {"id": "doc-1", "name": "part.m3d"},
        "counts": {"documents": 1, "items": 1, "tree_nodes": 1},
        "checks": [
            {"name": "open_document", "ok": True},
            {"name": "document_tree", "ok": True},
            {"name": "close_document", "ok": True},
        ],
        "readback": {
            "open_document": {"document": {"id": "doc-1", "name": "part.m3d"}},
            "document_tree": {"tree": {"id": "root", "name": "Part", "type": "part"}},
            "items": {"items": [{"id": "line-1", "name": "Line 1", "type": "line"}]},
            "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d"}]},
            "close_document": {"closed": True},
        },
    }


if __name__ == "__main__":
    unittest.main()
