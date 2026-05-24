import tempfile
import unittest
from pathlib import Path

from kompas_mcp.operation_result import normalize_operation_result


class OperationResultEnvelopeTests(unittest.TestCase):
    def test_normalizes_successful_primitive_result(self) -> None:
        result = normalize_operation_result(
            "create_line",
            result={"ok": True, "document_id": "doc-1", "id": "line-1", "extra": "ignored"},
            preflight={"ok": True, "checks": [{"name": "active_document_selected", "ok": True}]},
            readback_contract={"ok": True, "checks": [{"name": "readback_item:line", "ok": True}]},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["operation"], "create_line")
        self.assertEqual(result["result_preview"]["id"], "line-1")
        self.assertEqual(result["failures"], [])

    def test_collects_prefixed_failed_checks(self) -> None:
        result = normalize_operation_result(
            "create_line",
            result={"ok": False, "steps": [{"step": "select_sketch", "ok": False}]},
            preflight={"ok": False, "checks": [{"name": "document_type", "ok": False, "expected": "part", "actual": "drawing"}]},
            readback_contract={
                "ok": False,
                "checks": [{"name": "readback_item:line", "ok": False, "expected": {">=": 1}, "actual": 0}],
            },
        )

        failure_names = [item["name"] for item in result["failures"]]
        self.assertFalse(result["ok"])
        self.assertIn("operation_result_ok", failure_names)
        self.assertIn("preflight:document_type", failure_names)
        self.assertIn("readback:readback_item:line", failure_names)
        self.assertEqual(result["result_preview"]["failed_steps"], ["select_sketch"])

    def test_classifies_runtime_error(self) -> None:
        result = normalize_operation_result(
            "get_active_document",
            error="No active document",
            exception_type="RuntimeError",
            require_result=False,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "NO_ACTIVE_DOCUMENT")
        self.assertEqual(result["failures"][0]["name"], "runtime_error_absent")

    def test_records_artifact_existence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "readback.json"
            artifact.write_text("{}", encoding="utf-8")

            result = normalize_operation_result(
                "probe",
                result={"ok": True},
                artifacts={"readback_manifest": str(artifact)},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["artifacts"][0]["role"], "readback_manifest")
        self.assertTrue(result["artifacts"][0]["exists"])
        self.assertGreaterEqual(result["artifacts"][0]["size_bytes"], 2)

    def test_rejects_non_object_public_payloads(self) -> None:
        result = normalize_operation_result(
            "bad_payload",
            result=[],  # type: ignore[arg-type]
            preflight=[],  # type: ignore[arg-type]
            readback_contract=[],  # type: ignore[arg-type]
            artifacts=[],  # type: ignore[arg-type]
        )

        failure_names = [item["name"] for item in result["failures"]]
        self.assertFalse(result["ok"])
        self.assertIn("result_payload_object", failure_names)
        self.assertIn("preflight_payload_object", failure_names)
        self.assertIn("readback_contract_payload_object", failure_names)
        self.assertIn("artifacts_payload_object", failure_names)


if __name__ == "__main__":
    unittest.main()
