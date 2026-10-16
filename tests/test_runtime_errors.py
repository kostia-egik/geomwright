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

    def test_classifies_v2_write_contract_errors(self) -> None:
        cases = [
            ("invalid input: entities must be a non-empty list", "INVALID_INPUT", "input"),
            ("ambiguous target: provide sketch_ref or create_new_sketch, not both", "AMBIGUOUS_TARGET", "target_resolution"),
            ("unsupported COM shape: existing sketch_ref target is not implemented", "UNSUPPORTED_COM_SHAPE", "com_shape"),
            ("CAD_SELF_INTERSECTION: compression spring sweep is invalid; KOMPAS ObjectError=31", "CAD_SELF_INTERSECTION", "geometry"),
            ("CAD_SESSION_BLOCKED: unknown outcome; pywintypes.com_error", "CAD_SESSION_BLOCKED", "session"),
            ("CAD_DIAGNOSTICS_REQUIRED: CAD_MODE_MISMATCH: finished failure", "CAD_DIAGNOSTICS_REQUIRED", "session"),
            ("CAD_MODE_MISMATCH: selected hidden session", "CAD_MODE_MISMATCH", "session"),
            ("CAD_RUNTIME_INVALID: SyntaxError before CAD launch", "CAD_RUNTIME_INVALID", "environment"),
            ("CAD_SESSION_BLOCKED: CAD_RUNTIME_INVALID: old failure", "CAD_SESSION_BLOCKED", "session"),
            ("CAD_SESSION_BLOCKED: CAD_MODE_MISMATCH: selected hidden session", "CAD_SESSION_BLOCKED", "session"),
        ]

        for message, code, category in cases:
            with self.subTest(code=code):
                result = classify_runtime_error(message)
                self.assertEqual(result["code"], code)
                self.assertEqual(result["category"], category)
                if code == "CAD_SELF_INTERSECTION":
                    self.assertFalse(result["retryable"])
                    self.assertIn("do not retry", result["hint"])
                if code == "CAD_RUNTIME_INVALID":
                    self.assertFalse(result["retryable"])
                    self.assertIn("KOMPAS_PYTHON",result["hint"])
                if code == "CAD_SESSION_BLOCKED":
                    self.assertFalse(result["retryable"])
                    self.assertIn("without COM", result["hint"])
                if code == "CAD_DIAGNOSTICS_REQUIRED":
                    self.assertFalse(result["retryable"])
                    self.assertIn("confirm_idle=false", result["hint"])

    def test_unknown_error_keeps_message_and_hint(self) -> None:
        result = classify_runtime_error("unexpected bridge payload")

        self.assertEqual(result["code"], "UNKNOWN_RUNTIME_ERROR")
        self.assertEqual(result["message"], "unexpected bridge payload")
        self.assertTrue(result["retryable"])
        self.assertIn("preflight", result["hint"])


if __name__ == "__main__":
    unittest.main()
