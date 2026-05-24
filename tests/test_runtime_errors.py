import unittest

from kompas_mcp.runtime_errors import classify_runtime_error


class RuntimeErrorClassificationTests(unittest.TestCase):
    def test_classifies_missing_active_document(self) -> None:
        result = classify_runtime_error(RuntimeError("No active document"), stage="preflight")

        self.assertEqual(result["code"], "NO_ACTIVE_DOCUMENT")
        self.assertEqual(result["category"], "document_state")
        self.assertEqual(result["exception_type"], "RuntimeError")
        self.assertEqual(result["stage"], "preflight")
        self.assertFalse(result["retryable"])
        self.assertIn("Open or activate", result["hint"])

    def test_classifies_com_failure_as_retryable(self) -> None:
        result = classify_runtime_error("pywintypes.com_error: server execution failed")

        self.assertEqual(result["code"], "COM_CALL_FAILED")
        self.assertEqual(result["category"], "com")
        self.assertTrue(result["retryable"])

    def test_classifies_empty_readback(self) -> None:
        result = classify_runtime_error("Document tree empty after operation")

        self.assertEqual(result["code"], "EMPTY_READBACK")
        self.assertEqual(result["category"], "readback")

    def test_classifies_empty_readback_payload(self) -> None:
        result = classify_runtime_error("Readback returned empty payload")

        self.assertEqual(result["code"], "EMPTY_READBACK")
        self.assertEqual(result["category"], "readback")

    def test_unknown_error_keeps_message_and_hint(self) -> None:
        result = classify_runtime_error("unexpected bridge payload")

        self.assertEqual(result["code"], "UNKNOWN_RUNTIME_ERROR")
        self.assertEqual(result["message"], "unexpected bridge payload")
        self.assertTrue(result["retryable"])
        self.assertIn("preflight", result["hint"])


if __name__ == "__main__":
    unittest.main()
