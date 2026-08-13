from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kompas_mcp.bridge_runner import BridgeError, BridgeRunner


class BridgeRunnerResponseTests(unittest.TestCase):
    def test_rejects_invalid_response_json_as_bridge_error(self) -> None:
        with self._runner_context("{") as runner:
            with self.assertRaisesRegex(BridgeError, "Invalid bridge response JSON"):
                runner.call("list_documents")

    def test_rejects_non_object_response_envelope(self) -> None:
        with self._runner_context("[]") as runner:
            with self.assertRaisesRegex(BridgeError, "Bridge response must be an object"):
                runner.call("list_documents")

    def test_rejects_missing_success_data(self) -> None:
        with self._runner_context({"ok": True}) as runner:
            with self.assertRaisesRegex(BridgeError, "missing data"):
                runner.call("list_documents")

    def test_rejects_non_object_success_data(self) -> None:
        with self._runner_context({"ok": True, "data": []}) as runner:
            with self.assertRaisesRegex(BridgeError, "data must be an object"):
                runner.call("list_documents")

    def test_handles_non_object_error_payload(self) -> None:
        with self._runner_context({"ok": False, "error": "plain failure"}) as runner:
            with self.assertRaisesRegex(BridgeError, "plain failure"):
                runner.call("list_documents")

    def _runner_context(self, response_payload):
        return _BridgeRunnerContext(response_payload)


class _BridgeRunnerContext:
    def __init__(self, response_payload) -> None:
        self.response_payload = response_payload
        self.temp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.env_patch = None
        self.run_patch = None
        self.runner: BridgeRunner | None = None

    def __enter__(self) -> BridgeRunner:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        python_path = root / "python.exe"
        bridge_path = root / "kompas_bridge.py"
        python_path.write_text("", encoding="utf-8")
        bridge_path.write_text("", encoding="utf-8")

        class FakeProcess:
            def poll(self):
                return 0

            def communicate(self):
                return "", ""

        def fake_popen(args, **_kwargs):
            response_path = Path(args[3])
            if isinstance(self.response_payload, str):
                response_path.write_text(self.response_payload, encoding="utf-8")
            else:
                response_path.write_text(json.dumps(self.response_payload), encoding="utf-8")
            return FakeProcess()

        self.env_patch = patch.dict("os.environ", {"KOMPAS_MCP_TEMP_DIR": str(root)})
        self.run_patch = patch("kompas_mcp.bridge_runner.subprocess.Popen", side_effect=fake_popen)
        self.env_patch.start()
        self.run_patch.start()
        self.runner = BridgeRunner(kompas_python=str(python_path), bridge_script=str(bridge_path))
        return self.runner

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.run_patch is not None:
            self.run_patch.stop()
        if self.env_patch is not None:
            self.env_patch.stop()
        if self.temp_dir is not None:
            self.temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
