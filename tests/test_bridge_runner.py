from __future__ import annotations

import json
import tempfile
import threading
import unittest
import os
import subprocess
import sys
import time
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch

from kompas_mcp.bridge_runner import BridgeError, BridgeRunner
from kompas_mcp.session_guard import SessionGuard, SessionGuardError


class BridgeRunnerResponseTests(unittest.TestCase):
    def test_terminal_receipts_distinguish_rejection_settled_failure_and_lost_outcome(self) -> None:
        from kompas_mcp import bridge_runner as runtime

        for outcome, matching, exit_code, expected in (
            ("no_cad", True, 1, "unblocked"),
            ("settled", True, 1, "settled_failure"),
            ("settled", False, 1, "unknown_outcome"),
            ("settled", True, 7, "unknown_outcome"),
        ):
            with self.subTest(outcome=outcome, matching=matching, exit_code=exit_code):
                def response(request):
                    return {"ok": False, "error": {"message": "fixture failure", "type": "RuntimeError"},
                            "completion": {"version": 1, "action": request["action"],
                                           "token": request["completion_token"] if matching else "stale",
                                           "outcome": outcome}}, exit_code

                with self._runner_context(response) as runner:
                    with patch.object(runtime, "CHECKOUT_BRIDGE_SCRIPT", runner.bridge_script), patch.object(runner, "_validate_runtime"):
                        with self.assertRaisesRegex(BridgeError, "fixture failure"):
                            runner.call("fixture")
                    self.assertEqual(runner.get_session_guard()["state"], expected)
                    self.assertEqual(runner.get_session_guard().get("automatic_recovery_available", False),
                                     expected == "settled_failure")

        # A custom script cannot acquire production completion semantics.
        with self._runner_context(response) as runner:
            with self.assertRaises(BridgeError):
                runner.call("fixture")
            self.assertEqual(runner.get_session_guard()["state"], "unknown_outcome")

    def test_finished_failure_audit_is_exclusive_retains_blockers_and_recovers_without_user(self) -> None:
        from kompas_mcp import bridge_runner as runtime
        audit_clear = False
        observed_states = []

        def response(request):
            if request["action"] == "audit_session_recovery":
                observed_states.append(runner.get_session_guard()["state"])
                with self.assertRaises(BridgeError):
                    runner.call("create_part")
                with self.assertRaises(SessionGuardError):
                    runner.session_guard.recover(request["completion_token"], confirm_idle=True, reason="concurrent recovery")
                data = {"session_observed_clear": audit_clear, "blockers": [] if audit_clear else ["visible_dialog"]}
            else:
                data = {"ok": False, "partial": True}
            return {"ok": True, "data": data, "completion": {
                "version": 1, "token": request["completion_token"], "action": request["action"], "outcome": "settled"}}, 0

        with self._runner_context(response) as runner:
            with patch.object(runtime, "CHECKOUT_BRIDGE_SCRIPT", runner.bridge_script), patch.object(runner, "_validate_runtime"):
                self.assertEqual(runner.call("create_part"), {"ok": False, "partial": True})
                status = runner.get_session_guard()
                self.assertEqual(status["state"], "settled_failure")
                with self.assertRaisesRegex(SessionGuardError, "current settled-failure token"):
                    runner.recover_session("stale", confirm_idle=False, reason="inspect partial")
                result = runner.recover_session(status["token"], confirm_idle=False, reason="inspect partial")
                self.assertFalse(result["ok"])
                self.assertEqual(runner.get_session_guard()["token"], status["token"])
                self.assertEqual(runner.get_session_guard()["state"], "settled_failure")
                audit_clear = True
                result = runner.recover_session(status["token"], confirm_idle=False, reason="retain partial; inspect before next write")
                self.assertTrue(result["ok"])
                self.assertEqual(result["basis"], "completed_handler_and_session_audit")
                self.assertFalse(result["cad_readiness_verified"])
                self.assertFalse(runner.get_session_guard()["blocked"])
                self.assertEqual(observed_states, ["recovering", "recovering"])
                runner.call("create_part")
                token = runner.get_session_guard()["token"]
                context = runner.cad_session_policy.read()
                context["binding"] = {"window_handle": 123, "process_id": 11,
                                      "process_started_at": 12345, "owned": False}
                runner.cad_session_policy._write(context)
                with patch.object(runtime, "process_alive", return_value=False), patch.object(runner, "_call") as com:
                    recovered = runner.recover_session(token, confirm_idle=False, reason="old bound server exited")
                    self.assertEqual(recovered["basis"], "bound_session_exited")
                    com.assert_not_called()
                self.assertEqual(runner.get_cad_work_mode()["binding"], context["binding"])

    def test_failed_recovery_audit_loses_no_unknown_outcome_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            guard = SessionGuard(directory)
            with guard.operation("failed_write", {}):
                guard.checkpoint({"stage": "failed_write", "document_id": "partial.m3d"})
                guard.finished("settled")
                guard.failed("retained partial")
            token = guard.status()["token"]
            with guard.recovery_audit(token):
                guard.checkpoint({"stage": "audit_completed", "document_id": None})
                guard.finished("settled")
            self.assertEqual(guard.status()["checkpoint"]["stage"], "failed_write")
            self.assertEqual(guard.status()["checkpoint"]["document_id"], "partial.m3d")
            with self.assertRaisesRegex(RuntimeError, "audit transport lost"):
                with guard.recovery_audit(token):
                    guard.started(_WaitingFakeProcess())
                    raise RuntimeError("audit transport lost")
            self.assertEqual(guard.status()["state"], "unknown_outcome")
            self.assertIn("audit transport lost", guard.status()["error"])

    def test_untrusted_success_or_audit_cannot_release_production_guard(self) -> None:
        from kompas_mcp import bridge_runner as runtime

        def response(request):
            if request["action"] == "audit_session_recovery":
                return {"ok": True, "data": {"session_observed_clear": False, "blockers": ["visible_dialog"]}}, 0
            return {"ok": True, "data": {"ok": False}, "completion": {
                "version": 1, "token": request["completion_token"], "action": request["action"], "outcome": "settled"}}, 0

        with self._runner_context(response) as runner:
            with patch.object(runtime, "CHECKOUT_BRIDGE_SCRIPT", runner.bridge_script), patch.object(runner, "_validate_runtime"):
                runner.call("fixture")
                token = runner.get_session_guard()["token"]
                with self.assertRaisesRegex(BridgeError, "terminal completion receipt"):
                    runner.recover_session(token, confirm_idle=False, reason="inspect before writing")
                self.assertEqual(runner.get_session_guard()["state"], "unknown_outcome")

        for payload in ({"ok": "yes", "data": {}}, {"ok": True, "data": {}},
                        {"ok": False, "error": "invalid error", "completion": {"version": 1, "outcome": "no_cad"}}):
            with self.subTest(payload=payload):
                def malformed(request):
                    receipt = {**payload.get("completion", {}), "token": request["completion_token"], "action": request["action"]}
                    return {**payload, "completion": receipt}, 1 if payload["ok"] is False else 0
                with self._runner_context(malformed) as runner:
                    with patch.object(runtime, "CHECKOUT_BRIDGE_SCRIPT", runner.bridge_script), patch.object(runner, "_validate_runtime"):
                        with self.assertRaises(BridgeError):
                            runner.call("fixture")
                    self.assertEqual(runner.get_session_guard()["state"], "unknown_outcome")

    def test_runtime_selection_respects_explicit_environment_and_owned_checkout(self) -> None:
        from kompas_mcp import bridge_runner as runtime
        with self._runner_context({"ok":True,"data":{}}) as fixture:
            with patch.multiple(runtime,CHECKOUT_BRIDGE_SCRIPT=fixture.bridge_script,CHECKOUT_KOMPAS_PYTHON=fixture.kompas_python):
                with patch.dict(os.environ,{"KOMPAS_PYTHON":""}):
                    self.assertEqual(BridgeRunner().kompas_python,fixture.kompas_python)
                    with patch.object(runtime,"CHECKOUT_KOMPAS_PYTHON",fixture.kompas_python.parent / "missing.exe"):
                        self.assertEqual(BridgeRunner().kompas_python,runtime.DEFAULT_KOMPAS_PYTHON)
                with patch.dict(os.environ,{"KOMPAS_PYTHON":"environment.exe"}):
                    self.assertEqual(BridgeRunner().kompas_python,Path("environment.exe"))
                    self.assertEqual(BridgeRunner(kompas_python="explicit.exe").kompas_python,Path("explicit.exe"))

    def test_production_preflight_failure_never_launches_cad_or_quarantines(self) -> None:
        from kompas_mcp import bridge_runner as runtime
        with self._runner_context({"ok":True,"data":{}}) as runner:
            with patch.object(runtime,"CHECKOUT_BRIDGE_SCRIPT",runner.bridge_script):
                failed = subprocess.CompletedProcess([],1,stdout=b"",stderr=b"SyntaxError: incompatible runtime")
                with patch.object(runtime.subprocess,"run",return_value=failed) as validate, patch.object(runtime.subprocess,"Popen") as launch:
                    with self.assertRaisesRegex(BridgeError,"CAD_RUNTIME_INVALID.*KOMPAS_PYTHON"):
                        runner.call("fixture")
                    launch.assert_not_called()
                    self.assertEqual(validate.call_args.kwargs["timeout"],5)
                    self.assertEqual(validate.call_args.kwargs["stdin"],subprocess.DEVNULL)
                    self.assertFalse(runner.get_session_guard()["blocked"])
                with patch.object(runtime.subprocess,"run",side_effect=subprocess.TimeoutExpired("preflight",5)), patch.object(runtime.subprocess,"Popen") as launch:
                    with self.assertRaisesRegex(BridgeError,"CAD_RUNTIME_INVALID.*TimeoutExpired"):
                        runner.call("fixture")
                    launch.assert_not_called()
                    self.assertFalse(runner.get_session_guard()["blocked"])

    def test_successful_preflight_is_cached_only_while_runtime_sources_match(self) -> None:
        from kompas_mcp import bridge_runner as runtime
        with self._runner_context({"ok":True,"data":{}}) as runner:
            with patch.object(runtime,"CHECKOUT_BRIDGE_SCRIPT",runner.bridge_script), patch.object(runtime.subprocess,"run",
                return_value=subprocess.CompletedProcess([],0,stdout=b"",stderr=b"")) as validate:
                self.assertEqual(runner.call("fixture"),{})
                self.assertEqual(runner.call("fixture"),{})
                self.assertEqual(validate.call_count,1)
                runner.bridge_script.write_text("# changed production source\n",encoding="utf-8")
                self.assertEqual(runner.call("fixture"),{})
                self.assertEqual(validate.call_count,2)

    def test_modes_are_explicit_shared_and_cannot_bypass_quarantine(self) -> None:
        with self._runner_context({"ok": True, "data": {}}) as runner:
            self.assertEqual(runner.get_cad_work_mode()["mode"], "interactive")
            with self.assertRaises(ValueError):
                runner.set_cad_work_mode("hidden", confirm_switch=False)
            runner.call("fixture")
            successor = BridgeRunner(session_guard_dir=runner.session_guard.directory)
            successor.set_cad_work_mode("hidden", confirm_switch=True)
            with patch("kompas_mcp.bridge_runner.subprocess.Popen") as launch:
                with self.assertRaisesRegex(BridgeError, "CAD_SESSION_CHANGED"):
                    runner.call("fixture")
                launch.assert_not_called()
            self.assertFalse(runner.get_session_guard()["blocked"])
            self.assertTrue(runner.get_cad_work_mode()["host_selection_stale"])
            runner.set_cad_work_mode("interactive", confirm_switch=True, target_window_handle=123)
            with patch("kompas_mcp.bridge_runner.subprocess.Popen") as launch:
                with self.assertRaisesRegex(BridgeError, "CAD_MODE_UNSUPPORTED_ACTION"):
                    runner.call("smoke_check_session")
                launch.assert_not_called()
            with runner.session_guard.operation("fixture", {}):
                runner.session_guard.quarantine("fixture only; no CAD")
            with self.assertRaisesRegex(SessionGuardError, "CAD_SESSION_BLOCKED"):
                runner.set_cad_work_mode("hidden", confirm_switch=True)
            self.assertEqual(runner.get_cad_work_mode()["mode"], "interactive")

    def test_quarantine_survives_runner_recreation_and_requires_explicit_recovery(self) -> None:
        with self._real_runner_context() as runner:
            with self.assertRaisesRegex(BridgeError, "CAD_SESSION_BLOCKED.*timed out"):
                runner.call("waiting", timeout_seconds=0.2)
            status = runner.get_session_guard()
            self.assertEqual(status["state"], "unknown_outcome")
            self.assertEqual(status["checkpoint"]["stage"], "waiting")
            successor = BridgeRunner(kompas_python=str(runner.kompas_python),
                                     bridge_script=str(runner.bridge_script))
            with patch("kompas_mcp.bridge_runner.subprocess.Popen") as launch:
                with self.assertRaisesRegex(BridgeError, "CAD_SESSION_BLOCKED"):
                    successor.call("list_documents")
                with self.assertRaises(ValueError):
                    successor.recover_session(status["token"], confirm_idle=False, reason="not confirmed")
                with self.assertRaises(ValueError):
                    successor.recover_session("stale", confirm_idle=True, reason="fixture idle")
                with patch("kompas_mcp.session_guard.process_alive", return_value=True):
                    with self.assertRaisesRegex(SessionGuardError, "still running"):
                        successor.recover_session(status["token"], confirm_idle=True, reason="bridge still alive")
                recovered = successor.recover_session(status["token"], confirm_idle=True, reason="fixture stopped; no CAD")
                self.assertFalse(recovered["cad_readiness_verified"])
                launch.assert_not_called()
            self.assertEqual(successor.call("noisy"), {"finished": True})
            self.assertFalse(successor.get_session_guard()["blocked"])

    def test_guard_refuses_concurrent_calls_and_recovery_during_host_readback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            guard = SessionGuard(directory)
            with guard.operation("fixture", {}):
                token = guard.record["token"]
                with self.assertRaises(SessionGuardError):
                    with guard.operation("concurrent", {}):
                        self.fail("Concurrent operation admitted")
                self.assertEqual(guard.record["token"], token)
                guard.started(_WaitingFakeProcess())
                with self.assertRaisesRegex(SessionGuardError, "still running"):
                    guard.recover(token, confirm_idle=True, reason="not actually idle")
            self.assertFalse(guard.status()["blocked"])

        with self._runner_context({"ok": True, "data": {}}) as runner:
            quarantined, successor_started, finish = (threading.Event() for _ in range(3))
            errors = []
            original = SessionGuard.quarantine

            def quarantine(guard, error):
                original(guard, error)
                quarantined.set()
                if not successor_started.wait(3):
                    raise RuntimeError("Successor did not start")

            def fake_call(action, payload, *, _guard, **kwargs):
                _guard.started(_WaitingFakeProcess())
                if action == "failed_fixture":
                    return {"ok": False}
                successor_started.set()
                if not finish.wait(3):
                    raise RuntimeError("Successor not released")
                return {"ok": True}

            def invoke(action):
                try:
                    runner.call(action)
                except BaseException as exc:
                    errors.append(str(exc))

            with patch.object(runner, "_call", side_effect=fake_call), patch.object(SessionGuard, "quarantine", quarantine):
                old = threading.Thread(target=invoke, args=("failed_fixture",))
                new = threading.Thread(target=invoke, args=("successor_fixture",))
                old.start()
                try:
                    self.assertTrue(quarantined.wait(2))
                    token = runner.get_session_guard()["token"]
                    runner.recover_session(token, confirm_idle=True, reason="fake fixture only; no CAD")
                    new.start()
                    self.assertTrue(successor_started.wait(2))
                    old.join(timeout=2)
                    self.assertFalse(old.is_alive())
                    status = runner.get_session_guard()
                    self.assertTrue(status["blocked"], "Old request removed successor's marker")
                    self.assertNotEqual(status["token"], token)
                finally:
                    successor_started.set()
                    finish.set()
                    old.join(timeout=3)
                    if new.ident is not None:
                        new.join(timeout=3)
            self.assertEqual(errors, [])
            self.assertFalse(runner.get_session_guard()["blocked"])

    def test_outer_watchdog_kill_leaves_durable_quarantine(self) -> None:
        watchdog = Path(__file__).resolve().parents[1] / "scripts/run_bounded.py"
        with self._real_runner_context() as runner:
            directory = runner.bridge_script.parent
            worker = directory / "worker.py"
            worker.write_text(
                "import sys\nfrom kompas_mcp.bridge_runner import BridgeRunner\n"
                "BridgeRunner(kompas_python=sys.executable, bridge_script=sys.argv[1], timeout_seconds=30).call('waiting')\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            result = subprocess.run([sys.executable, str(watchdog), "--timeout", "3", "--",
                                     sys.executable, str(worker), str(runner.bridge_script)],
                                    env=env, capture_output=True, text=True, timeout=12)
            self.assertEqual(result.returncode, 124, result.stderr)
            status = runner.get_session_guard()
            self.assertTrue(status["blocked"])
            self.assertEqual(status["state"], "in_flight")
            with patch("kompas_mcp.bridge_runner.subprocess.Popen") as launch:
                with self.assertRaisesRegex(BridgeError, "CAD_SESSION_BLOCKED"):
                    runner.call("get_session_state")
                runner.recover_session(status["token"], confirm_idle=True, reason="fake host and bridge stopped")
                launch.assert_not_called()

    def test_prelaunch_failure_releases_guard_and_partial_checkpoint_survives_failure(self) -> None:
        with self._runner_context({"ok": True, "data": {}}) as runner:
            with patch("kompas_mcp.bridge_runner.subprocess.Popen", side_effect=OSError("fixture launch failed")):
                with self.assertRaises(OSError):
                    runner.call("fixture")
            self.assertFalse(runner.get_session_guard()["blocked"])
            with self.assertRaises(RuntimeError):
                with runner.session_guard.operation("fixture", {}):
                    runner.session_guard.started(_WaitingFakeProcess())
                    runner.session_guard.checkpoint({"stage": "partial_document_retained",
                                                     "cleanup": {"attempted": False, "verified_closed": False}})
                    runner.session_guard.checkpoint({"stage": "action_failed"})
                    raise RuntimeError("fixture build failed")
            self.assertFalse(runner.get_session_guard()["checkpoint"]["cleanup"]["verified_closed"])

    def test_noisy_bridge_completes_without_pipe_deadlock(self) -> None:
        with self._real_runner_context() as runner:
            self.assertEqual(runner.call("noisy"), {"finished": True})

    def test_callback_failure_stops_bridge_and_keeps_diagnostic_logs(self) -> None:
        processes = []
        popen = subprocess.Popen

        def track_process(*args, **kwargs):
            process = popen(*args, **kwargs)
            processes.append(process)
            return process

        def fail_callback(_event):
            raise ValueError("callback failed")

        with self._real_runner_context() as runner:
            with patch("kompas_mcp.bridge_runner.subprocess.Popen", side_effect=track_process):
                try:
                    with self.assertRaisesRegex(ValueError, "callback failed"):
                        runner.call("waiting", mode="diagnostic", progress_callback=fail_callback)
                    self.assertIsNotNone(processes[0].poll(), "Bridge survived callback failure")
                    artifacts = runner.last_diagnostic_artifacts
                    self.assertIsNotNone(artifacts)
                    self.assertIn("started", Path(artifacts["stdout"]).read_text(encoding="utf-8"))
                finally:
                    # Keep this regression safe even against the broken implementation.
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=5)

    def test_nonzero_exit_cannot_publish_success(self) -> None:
        with self._real_runner_context() as runner:
            with self.assertRaisesRegex(BridgeError, "exited with code 7"):
                runner.call("bad_exit")

    def test_timeout_preserves_diagnostic_artifacts(self) -> None:
        with self._real_runner_context() as runner:
            with self.assertRaisesRegex(BridgeError, "timed out"):
                runner.call("waiting", mode="diagnostic", timeout_seconds=0.5)
            artifacts = runner.last_diagnostic_artifacts
            self.assertIsNotNone(artifacts)
            for key in ("request", "progress", "stdout", "stderr"):
                self.assertTrue(Path(artifacts[key]).exists(), key)
            self.assertIn("started", Path(artifacts["stdout"]).read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "nt", "Windows helper-job containment")
    def test_owned_helper_stops_on_timeout_cancel_and_exit_but_its_server_survives(self) -> None:
        import ast
        import signal
        from kompas_mcp.session_guard import process_alive

        # Use the actual spring fallback's pre-COM bootstrap; no CAD module is
        # imported or called. The unregistered descendant stands in for a COM
        # server and must NOT inherit the Python helper's termination domain.
        bridge_path = Path(__file__).resolve().parents[1] / "bridge/kompas_bridge.py"
        tree = ast.parse(bridge_path.read_bytes())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_apply_saved_compression_spring_anchor_rotation_bindings")
        child_script = next(node.value.value for node in ast.walk(function)
                            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "child_script" for t in node.targets))
        bootstrap = child_script.split("import json, sys", 1)[0]
        self.assertIn("join_helper_job", bootstrap)
        for ending in ("timeout", "cancel", "normal"):
            with self.subTest(ending=ending), self._real_runner_context() as runner:
                root = runner.bridge_script.parent
                record = root / "helper.json"
                helper = root / "helper.py"
                helper.write_text(bootstrap + "\nimport subprocess,sys,time,json\nfrom pathlib import Path\n"
                    "server=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
                    "Path(sys.argv[1]).write_text(json.dumps({'helper':os.getpid(),'server':server.pid}))\n"
                    "time.sleep(30)\n", encoding="utf-8")
                runner.bridge_script.write_text(
                    "import subprocess,sys,time,json,os\nfrom pathlib import Path\n"
                    f"record=Path({str(record)!r})\n"
                    # Production routes helper output to its own PIPEs, not the
                    # bridge transport logs. A venv redirector outlives its worker
                    # briefly and must not inherit these temporary log handles.
                    f"child=subprocess.Popen([sys.executable,{str(helper)!r},str(record)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
                    "deadline=time.monotonic()+5\n"
                    "while not record.exists():\n"
                    "    if child.poll() is not None: raise RuntimeError('helper exited before ready')\n"
                    "    if time.monotonic()>deadline: raise RuntimeError('helper startup failed')\n"
                    "    time.sleep(.01)\n"
                    "Path(os.environ['KOMPAS_MCP_PROGRESS_FILE']).write_text('{\"stage\":\"helper_ready\"}\\n')\n"
                    + ("time.sleep(30)\n" if ending != "normal" else "")
                    + "Path(sys.argv[2]).write_text(json.dumps({'ok':True,'data':{}}))\n", encoding="utf-8")
                cancel = threading.Event()
                runner.cancel_event = cancel
                def progress(event):
                    if ending == "cancel" and event["stage"] == "helper_ready":
                        cancel.set()
                try:
                    if ending == "normal":
                        self.assertEqual(runner.call("fixture", progress_callback=progress), {})
                    else:
                        with self.assertRaisesRegex(BridgeError, "timed out" if ending == "timeout" else "cancelled"):
                            runner.call("fixture", timeout_seconds=2, progress_callback=progress)
                        status = runner.get_session_guard()
                        self.assertEqual(status["state"], "unknown_outcome")
                        # Even explicit recovery cannot release a live helper.
                        with patch("kompas_mcp.session_guard.helper_job_active", return_value=True):
                            with self.assertRaisesRegex(SessionGuardError, "helper is still running"):
                                runner.session_guard.recover(status["token"], confirm_idle=True, reason="fixture idle")
                    pids = json.loads(record.read_text())
                    self.assertFalse(process_alive(pids["helper"]), "Python helper survived call cleanup")
                    self.assertTrue(process_alive(pids["server"]), "Unenrolled server was terminated")
                finally:
                    if record.exists():
                        for pid in json.loads(record.read_text()).values():
                            if process_alive(pid):
                                os.kill(pid, signal.SIGTERM)
                # A delayed helper must fail closed after the owner closed its job.
                if ending != "normal":
                    late = subprocess.run([sys.executable, "-c",
                        "import sys; from kompas_mcp.session_guard import join_helper_job; join_helper_job(sys.argv[1],sys.argv[2])",
                        status["helper_job_name"], str(runner.session_guard.path)],
                        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(late.returncode, 0)
                    self.assertIn("host job is unavailable", late.stderr)

    @contextmanager
    def _real_runner_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "fixture_bridge.py"
            script.write_text(
                "import json,os,sys,time\nfrom pathlib import Path\n"
                "action=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))['action']\n"
                "if action=='noisy':\n"
                "    sys.stdout.write('x'*200000); sys.stdout.flush()\n"
                "    sys.stderr.write('y'*200000); sys.stderr.flush()\n"
                "if action=='waiting':\n"
                "    print('started',flush=True)\n"
                "    Path(os.environ['KOMPAS_MCP_PROGRESS_FILE']).write_text('{\"stage\":\"waiting\"}\\n',encoding='utf-8')\n"
                "    time.sleep(30)\n"
                "Path(sys.argv[2]).write_text(json.dumps({'ok':True,'data':{'finished':True}}),encoding='utf-8')\n"
                "if action=='bad_exit': sys.exit(7)\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"KOMPAS_MCP_TEMP_DIR": str(root),
                                         "KOMPAS_MCP_SESSION_GUARD_DIR": str(root / "guard")}):
                yield BridgeRunner(kompas_python=sys.executable, bridge_script=str(script),
                                   timeout_seconds=3, diagnostic_artifact_dir=str(root / "diagnostics"))

    def test_terminal_watchdog_bounds_descendants_and_preserves_exit_status(self) -> None:
        watchdog = Path(__file__).resolve().parents[1]/"scripts/run_bounded.py"
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)/"descendants.py"
            record = Path(directory)/"child.pid"
            fixture.write_text(
                "import subprocess,sys,time\nfrom pathlib import Path\n"
                "options={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}\n"
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],**options)\n"
                "Path(sys.argv[1]).write_text(str(child.pid))\ntime.sleep(60)\n",encoding="utf-8")
            start = time.monotonic()
            result = subprocess.run([sys.executable,str(watchdog),"--timeout","3","--",
                                     sys.executable,str(fixture),str(record)],
                                    stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=12)
            self.assertEqual(result.returncode,124,result.stderr)
            self.assertLess(time.monotonic()-start,10)
            self.assertIn("deadline exceeded",result.stderr)
            self.assertTrue(record.exists(),result.stdout+result.stderr)
            pid = int(record.read_text())
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes as w
                kernel = ctypes.WinDLL("kernel32",use_last_error=True)
                kernel.OpenProcess.argtypes = [w.DWORD,w.BOOL,w.DWORD]
                kernel.OpenProcess.restype = w.HANDLE
                kernel.GetExitCodeProcess.argtypes = [w.HANDLE,ctypes.POINTER(w.DWORD)]
                kernel.CloseHandle.argtypes = [w.HANDLE]
                handle = kernel.OpenProcess(0x1000,False,pid)
                if handle:
                    try:
                        code = w.DWORD()
                        self.assertTrue(kernel.GetExitCodeProcess(handle,ctypes.byref(code)))
                        self.assertNotEqual(code.value,259,"Grandchild survived the deadline")
                    finally:
                        kernel.CloseHandle(handle)
            # Normal leader exit must not retain a sleeping grandchild either.
            fixture.write_text(fixture.read_text().replace("\ntime.sleep(60)\n","\n"),encoding="utf-8")
            normal = subprocess.run([sys.executable,str(watchdog),"--timeout","5","--",
                                     sys.executable,str(fixture),str(record)],
                                    stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=12)
            self.assertEqual(normal.returncode,0,normal.stdout+normal.stderr)
            if os.name == "nt":
                handle = kernel.OpenProcess(0x1000,False,int(record.read_text()))
                if handle:
                    try:
                        code = w.DWORD()
                        self.assertTrue(kernel.GetExitCodeProcess(handle,ctypes.byref(code)))
                        self.assertNotEqual(code.value,259,"Grandchild survived normal leader exit")
                    finally:
                        kernel.CloseHandle(handle)
            finished = subprocess.run([sys.executable,str(watchdog),"--timeout","5","--",
                                       sys.executable,"-c","print('bounded-ok'); raise SystemExit(7)"],
                                      stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=12)
            self.assertEqual(finished.returncode,7,finished.stderr)
            self.assertIn("bounded-ok",finished.stdout)

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
        process = _WaitingFakeProcess()
        def start_process(*_args, **_kwargs):
            cancel_event.set()
            return process

        with self._runner_context({"ok": True, "data": {}}) as runner:
            runner.cancel_event = cancel_event
            with patch("kompas_mcp.bridge_runner.subprocess.Popen", side_effect=start_process):
                with self.assertRaisesRegex(BridgeError, "cancelled"):
                    runner.call("create_managed_pulley")
            self.assertEqual(runner.get_session_guard()["state"], "unknown_outcome")
        self.assertTrue(process.terminated)

    def test_cancelled_call_does_not_launch_bridge(self) -> None:
        with self._runner_context({"ok": True, "data": {}}) as runner:
            runner.cancel_event = threading.Event()
            runner.cancel_event.set()
            with patch("kompas_mcp.bridge_runner.subprocess.Popen") as popen:
                with self.assertRaisesRegex(BridgeError, "cancelled"):
                    runner.call("create_part")
                popen.assert_not_called()

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

            self.assertEqual(consumed, progress_path.stat().st_size)

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

    def test_progress_waits_for_complete_utf8_record_and_does_not_repeat_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.jsonl"
            first = b'{"stage":"start"}\n'
            second = (json.dumps({"stage": "готово"}, ensure_ascii=False) + "\n").encode("utf-8")
            split = second.index("г".encode("utf-8")) + 1
            path.write_bytes(first + second[:split])
            events = []
            offset, last = BridgeRunner._report_progress(path, 0, events.append, time.monotonic(), None)
            self.assertEqual(offset, len(first))
            self.assertEqual([event["stage"] for event in events], ["start"])
            with path.open("ab") as stream:
                stream.write(second[split:])
            offset, last = BridgeRunner._report_progress(path, offset, events.append, time.monotonic(), last)
            self.assertEqual(offset, path.stat().st_size)
            self.assertEqual([event["stage"] for event in events], ["start", "готово"])
            BridgeRunner._report_progress(path, offset, events.append, time.monotonic(), last)
            self.assertEqual(len(events), 2)

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
            returncode = 0

            def poll(self):
                return self.returncode

            def communicate(self):
                return "", ""

        def fake_popen(args, **_kwargs):
            from kompas_mcp import bridge_runner as runtime
            response_path = Path(args[3])
            response = self.response_payload
            process = FakeProcess()
            if callable(response):
                response, process.returncode = response(json.loads(Path(args[2]).read_text(encoding="utf-8")))
            elif (isinstance(response, dict) and response.get("ok") is True
                    and "completion" not in response and Path(args[1]) == runtime.CHECKOUT_BRIDGE_SCRIPT):
                request = json.loads(Path(args[2]).read_text(encoding="utf-8"))
                response = {**response, "completion": {"version": 1, "token": request["completion_token"],
                            "action": request["action"], "outcome": "settled"}}
            if isinstance(response, str):
                response_path.write_text(response, encoding="utf-8")
            else:
                response_path.write_text(json.dumps(response), encoding="utf-8")
            return process

        self.env_patch = patch.dict("os.environ", {"KOMPAS_MCP_TEMP_DIR": str(root),
                                                  "KOMPAS_MCP_SESSION_GUARD_DIR": str(root / "guard")})
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
