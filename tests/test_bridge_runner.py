from __future__ import annotations

import json
import tempfile
import threading
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

    def test_cancellation_terminates_a_running_bridge_process(self) -> None:
        cancel_event = threading.Event()
        cancel_event.set()
        process = _WaitingFakeProcess()
        with self._runner_context({"ok": True, "data": {}}) as runner:
            runner.cancel_event = cancel_event
            with patch("kompas_mcp.bridge_runner.subprocess.Popen", return_value=process):
                with self.assertRaisesRegex(BridgeError, "cancelled"):
                    runner.call("create_managed_pulley")
        self.assertTrue(process.terminated)

    def test_call_timeout_override_bounds_one_bridge_operation(self) -> None:
        process = _WaitingFakeProcess()
        with self._runner_context({"ok": True, "data": {}}) as runner:
            runner.timeout_seconds = 99.0
            with (
                patch("kompas_mcp.bridge_runner.subprocess.Popen", return_value=process),
                patch("kompas_mcp.bridge_runner.time.monotonic", side_effect=[0.0, 2.0]),
            ):
                with self.assertRaisesRegex(BridgeError, "timed out after 1 seconds"):
                    runner.call("apply_existing_sketch_constraint", timeout_seconds=1.0)
        self.assertTrue(process.terminated)

    def test_normalizes_progress_to_bounded_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress.jsonl"
            progress_path.write_text(
                json.dumps({"percent": 120, "operation": "rebuild", "name": "Pulley"}) + "\n",
                encoding="utf-8",
            )
            events = []
            with patch("kompas_mcp.bridge_runner.time.monotonic", return_value=1.25):
                consumed, last = BridgeRunner._report_progress(progress_path, 0, events.append, 1.0, None)

        self.assertEqual(consumed, 1)
        self.assertEqual(last, events[0])
        self.assertEqual(
            {key: events[0][key] for key in ("stage", "operation", "percent", "document_id", "target", "elapsed_ms")},
            {
                "stage": "rebuild",
                "operation": "rebuild",
                "percent": 100,
                "document_id": None,
                "target": "Pulley",
                "elapsed_ms": 250,
            },
        )

    def test_diagnostic_mode_keeps_full_call_artifacts(self) -> None:
        with self._runner_context({"ok": True, "data": {"documents": []}}) as runner:
            runner.mode = "diagnostic"
            runner.diagnostic_artifact_dir = runner.kompas_python.parent / "diagnostics"
            self.assertEqual(runner.call("list_documents"), {"documents": []})
            artifacts = runner.last_diagnostic_artifacts
            self.assertIsNotNone(artifacts)
            assert artifacts is not None
            self.assertTrue(Path(artifacts["request"]).exists())
            self.assertTrue(Path(artifacts["response"]).exists())
            self.assertTrue(Path(artifacts["stdout"]).exists())
            self.assertTrue(Path(artifacts["stderr"]).exists())

    def test_rejects_unknown_runner_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "normal.*diagnostic"):
            BridgeRunner(mode="verbose")  # type: ignore[arg-type]

    def test_timeout_reports_last_progress_checkpoint(self) -> None:
        process = _WaitingFakeProcess()

        def fake_popen(_args, **kwargs):
            progress_path = Path(kwargs["env"]["KOMPAS_MCP_PROGRESS_FILE"])
            progress_path.write_text(
                json.dumps({"percent": 78, "operation": "row_pattern_rebuild", "name": "Rows"}) + "\n",
                encoding="utf-8",
            )
            return process

        with self._runner_context({"ok": True, "data": {}}) as runner:
            with (
                patch("kompas_mcp.bridge_runner.subprocess.Popen", side_effect=fake_popen),
                patch("kompas_mcp.bridge_runner.time.monotonic", side_effect=[0.0, 0.25, 2.0]),
            ):
                with self.assertRaisesRegex(BridgeError, '"stage":"row_pattern_rebuild"'):
                    runner.call("create_chain_sprocket", progress_callback=lambda _event: None, timeout_seconds=1.0)
        self.assertTrue(process.terminated)


class _WaitingFakeProcess:
    def __init__(self) -> None:
        self.terminated = False

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.terminated = True
        return 0


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
