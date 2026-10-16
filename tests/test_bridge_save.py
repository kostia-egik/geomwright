from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch


def _load_bridge_module():
    module_name = "kompas_bridge_test_module"
    if module_name in sys.modules:
        return sys.modules[module_name]

    fake_win32com = types.ModuleType("win32com")
    fake_client = types.ModuleType("win32com.client")

    def _dispatch(obj, *args, **kwargs):
        return obj

    fake_client.Dispatch = _dispatch
    fake_win32com.client = fake_client
    sys.modules.setdefault("win32com", fake_win32com)
    sys.modules.setdefault("win32com.client", fake_client)

    bridge_path = Path(__file__).resolve().parents[1] / "bridge" / "kompas_bridge.py"
    spec = importlib.util.spec_from_file_location(module_name, bridge_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module


BRIDGE = _load_bridge_module()


def test_export_copy_uses_native_part_extension_before_save(tmp_path):
    from kompas_mcp.adapter import KompasAdapter

    adapter = KompasAdapter(runner=Mock())
    with patch.object(adapter, "_select_document", return_value={
            "id": "part", "name": "Untitled", "path": "", "type": 10024}), \
            patch.object(adapter, "_export_dir", return_value=tmp_path), \
            patch.object(adapter, "save_document_as", return_value={"saved": True}) as save:
        result = adapter.save_export_copy(document_id="part")
        assert Path(result["export_path"]).suffix == ".m3d"
        save.assert_called_once_with(result["export_path"], document_id="part",
            close_after_save=False, user_requested_close=False)


class FakeDocumentsCollection:
    def __init__(self, app) -> None:
        self._app = app
        self._items = []

    @property
    def Count(self) -> int:
        return len(self._items)

    def Item(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        if 1 <= index <= len(self._items):
            return self._items[index - 1]
        raise IndexError(index)

    def Open(self, path, visible, read_only):
        document = FakeDocument(self._app, path=str(path), content=Path(path).read_text(encoding="utf-8"))
        self.add(document)
        return document

    def add(self, document) -> None:
        self._items.append(document)
        self._app.ActiveDocument = document

    def remove(self, document) -> None:
        self._items = [item for item in self._items if item is not document]
        self._app.ActiveDocument = self._items[-1] if self._items else None


class FakeDocument:
    def __init__(self, app, path: str = "", name: str | None = None, changed: bool = False, content: str = "payload") -> None:
        self._app = app
        self.PathName = path
        self.Name = name or (Path(path).name if path else "Untitled")
        self.Type = 4
        self.Reference = id(self)
        self.Changed = changed
        self._content = content
        self.close_calls: list[int] = []
        self.save_as_calls: list[str] = []
        self.save_calls = 0

    def SaveAs(self, path):
        Path(path).write_text(self._content, encoding="utf-8")
        self.PathName = str(path)
        self.Name = Path(path).name
        self.Changed = False
        self.save_as_calls.append(str(path))
        return True

    def Save(self):
        if not self.PathName:
            return False
        Path(self.PathName).write_text(self._content, encoding="utf-8")
        self.Changed = False
        self.save_calls += 1
        return True

    def Close(self, mode):
        self.close_calls.append(int(mode))
        self._app.Documents.remove(self)


class StickyFakeDocument(FakeDocument):
    def Close(self, mode):
        self.close_calls.append(int(mode))


class FakeApp:
    def __init__(self) -> None:
        self.ActiveDocument = None
        self.Documents = FakeDocumentsCollection(self)


class BridgeSaveTests(unittest.TestCase):
    def test_unsaved_document_identity_survives_collection_reordering(self) -> None:
        app = FakeApp()
        first, second, third = (FakeDocument(app, name="Untitled") for _ in range(3))
        for document in (first, second, third):
            app.Documents.add(document)
        identity = BRIDGE.describe_document(second, app, 1)["runtime_id"]
        self.assertTrue(identity.startswith("@reference:"))
        self.assertEqual(BRIDGE.describe_document(second, app)["id"], identity)
        self.assertIsNone(BRIDGE.resolve_document(app, "Untitled"))
        app.Documents.remove(first)
        self.assertIs(BRIDGE.resolve_document_strict(app, identity), second)
        self.assertIs(BRIDGE.resolve_document(app, identity), second)
        self.assertIsNone(BRIDGE.resolve_document_strict(app, "@document:1"))
        self.assertIsNone(BRIDGE.resolve_document(app, "@document:1"))
        app.Documents.remove(second)
        self.assertIsNone(BRIDGE.resolve_document_strict(app, identity))
        del third.Reference
        self.assertIsNone(BRIDGE.describe_document(third, app, 0)["runtime_id"])

    def test_explicit_missing_document_never_falls_back_to_active(self) -> None:
        app = FakeApp()
        first = FakeDocument(app, path="C:/models/first.m3d")
        active = FakeDocument(app, path="C:/models/active.m3d")
        app.Documents.add(first)
        app.Documents.add(active)
        self.assertIs(BRIDGE.resolve_document(app, None), active)
        self.assertIs(BRIDGE.resolve_document(app, first.PathName), first)
        self.assertIs(BRIDGE.resolve_document_strict(app, first.PathName), first)
        self.assertIsNone(BRIDGE.resolve_document(app, "C:/models/missing.m3d"))
        self.assertIsNone(BRIDGE.resolve_document_strict(app, "C:/models/missing.m3d"))
        with patch.object(BRIDGE, "make_app", return_value=app):
            for handler, payload in (
                (BRIDGE.handle_save_document, {"close_after_save": True}),
                (BRIDGE.handle_close_document, {"save": True}),
            ):
                with self.subTest(handler=handler.__name__):
                    with self.assertRaisesRegex(RuntimeError, "Document not found"):
                        handler(dict(payload, document_id="C:/models/missing.m3d"))
        self.assertEqual(active.save_calls, 0)
        self.assertEqual(active.close_calls, [])

    def test_failed_saves_preserve_open_document_and_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "part.m3d"
            target.write_text("old", encoding="utf-8")
            app = FakeApp()
            source = FakeDocument(app, path=str(target), changed=True, content="new")
            app.Documents.add(source)
            app.Quit = Mock()
            with patch.object(BRIDGE, "make_app", return_value=app), patch.object(
                source, "Save", return_value=False
            ):
                for handler, payload in (
                    (BRIDGE.handle_save_document, {"close_after_save": True}),
                    (BRIDGE.handle_close_document, {"save": True}),
                ):
                    with self.subTest(handler=handler.__name__):
                        with self.assertRaisesRegex(RuntimeError, "Save returned failure"):
                            handler(dict(payload, document_id=BRIDGE.describe_document(source, app)["runtime_id"], strict=True))
                report = BRIDGE.handle_shutdown_session({"save": True})
            self.assertEqual(report["failed_count"], 1)
            self.assertFalse(report["quit_called"])
            app.Quit.assert_not_called()
            self.assertEqual(source.close_calls, [])
            self.assertTrue(source.Changed)
            self.assertEqual(app.Documents.Count, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_void_save_requires_clean_readback_before_close(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "part.m3d"
            target.write_text("old", encoding="utf-8")
            app = FakeApp()
            source = FakeDocument(app, path=str(target), changed=True, content="new")
            app.Documents.add(source)
            with patch.object(BRIDGE, "make_app", return_value=app):
                with patch.object(source, "Save", return_value=None):
                    with self.assertRaisesRegex(RuntimeError, "unsaved changes remain"):
                        BRIDGE.handle_save_document({"close_after_save": True})
                    source.Changed = None
                    with self.assertRaisesRegex(RuntimeError, "clean state was not confirmed"):
                        BRIDGE.handle_close_document({"save": True})
                self.assertEqual(source.close_calls, [])
                real_save = source.Save

                def void_save():
                    real_save()
                    return None

                with patch.object(source, "Save", side_effect=void_save):
                    report = BRIDGE.handle_save_document({"close_after_save": False})
                    self.assertFalse(report["closed"])
                    report = BRIDGE.handle_close_document({"save": True})
            self.assertTrue(report["saved"])
            self.assertTrue(report["closed"])
            self.assertEqual(source.close_calls, [0])
            self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_staged_save_failure_never_closes_source_or_reopened_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = FakeApp()
            target = Path(temp_dir) / "part.m3d"
            target.write_text("old", encoding="utf-8")
            source = FakeDocument(app, changed=True, content="new")
            app.Documents.add(source)

            def failed_save_as(path):
                Path(path).write_text("incomplete", encoding="utf-8")
                return False

            with patch.object(source, "SaveAs", side_effect=failed_save_as):
                with self.assertRaisesRegex(RuntimeError, "Save returned failure"):
                    BRIDGE._save_document_via_staging(source, app, str(target))
            self.assertEqual(source.close_calls, [])
            self.assertTrue(source.Changed)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

            reopened = FakeDocument(app, path=str(target), changed=True)
            app.Documents.add(reopened)
            # Inject only the reopen boundary; the source's staging save is real.
            with patch.object(BRIDGE, "_replace_staging_file", return_value=(reopened, {})), patch.object(
                reopened, "Save", return_value=False
            ):
                reopened.Changed = False
                with self.assertRaisesRegex(RuntimeError, "document remains open"):
                    BRIDGE._save_document_via_staging(source, app, str(target), keep_open=False)
            self.assertEqual(reopened.close_calls, [])

    def test_build_post_save_compression_spring_anchor_rotation_bindings_collects_named_segments(self) -> None:
        planned = BRIDGE._build_post_save_compression_spring_anchor_rotation_bindings(
            [
                {
                    "role": "start_end",
                    "path_name": "spring_start_path",
                    "anchor_rotation_expression": "360 * SPG01_N31",
                },
                {
                    "role": "working",
                    "path_name": "spring_working_path",
                    "anchor_rotation_expression": "  360 * SPG01_N21  ",
                },
                {
                    "role": "finish_end",
                    "path_name": "spring_finish_path",
                    "anchor_rotation_expression": "",
                },
                {
                    "role": "orphan",
                    "anchor_rotation_expression": "90",
                },
            ]
        )

        self.assertEqual(
            planned,
            [
                {
                    "role": "start_end",
                    "path_name": "spring_start_path",
                    "expression": "360 * SPG01_N31",
                },
                {
                    "role": "working",
                    "path_name": "spring_working_path",
                    "expression": "360 * SPG01_N21",
                },
            ],
        )

    def test_build_save_staging_path_keeps_target_directory_and_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "part.m3d"
            candidate = BRIDGE._build_save_staging_path(str(target))

        self.assertEqual(Path(candidate).parent, target.parent)
        self.assertEqual(Path(candidate).suffix.lower(), ".m3d")
        self.assertNotEqual(Path(candidate).name, target.name)

    def test_save_document_via_staging_replaces_target_and_closes_reopened_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = FakeApp()
            target = Path(temp_dir) / "part.m3d"
            target.write_text("old", encoding="utf-8")

            open_target = FakeDocument(app, path=str(target), changed=False, content="old")
            app.Documents.add(open_target)
            source = FakeDocument(app, content="new-content")
            app.Documents.add(source)

            reopened_document, report = BRIDGE._save_document_via_staging(
                source,
                app,
                str(target),
                keep_open=False,
                visible=False,
            )

            self.assertEqual(target.read_text(encoding="utf-8"), "new-content")
            self.assertEqual(open_target.close_calls, [0])
            self.assertEqual(source.close_calls, [0])
            self.assertIsNone(reopened_document)
            self.assertEqual(len(report["closed_target_documents"]), 1)
            self.assertTrue(Path(report["reopened_document"]["path"]).samefile(target))

    def test_save_document_via_staging_rejects_dirty_open_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = FakeApp()
            target = Path(temp_dir) / "part.m3d"
            target.write_text("old", encoding="utf-8")

            dirty_target = FakeDocument(app, path=str(target), changed=True, content="old")
            app.Documents.add(dirty_target)
            source = FakeDocument(app, content="new-content")
            app.Documents.add(source)

            with self.assertRaisesRegex(RuntimeError, "unsaved changes"):
                BRIDGE._save_document_via_staging(
                    source,
                    app,
                    str(target),
                    keep_open=False,
                    visible=False,
                )

            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(dirty_target.close_calls, [])
            self.assertEqual(source.close_calls, [])

    def test_save_document_via_staging_rejects_target_that_remains_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = FakeApp()
            target = Path(temp_dir) / "part.m3d"
            target.write_text("old", encoding="utf-8")

            open_target = StickyFakeDocument(app, path=str(target), changed=False, content="old")
            app.Documents.add(open_target)
            source = FakeDocument(app, content="new-content")
            app.Documents.add(source)

            with self.assertRaisesRegex(RuntimeError, "still open"):
                BRIDGE._save_document_via_staging(
                    source,
                    app,
                    str(target),
                    keep_open=False,
                    visible=False,
                )

            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(open_target.close_calls, [0, 0, 0, 0])
            self.assertEqual(source.close_calls, [0])
            self.assertEqual(list(Path(temp_dir).glob("*.__kompas_mcp_stage__*.m3d")), [])

    def test_attempt_partial_generated_part_save_returns_saved_document_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = FakeApp()
            source = FakeDocument(app, content="partial-content")
            app.Documents.add(source)
            target = Path(temp_dir) / "partial.m3d"
            steps_report: list[dict[str, object]] = []

            report = BRIDGE._attempt_partial_generated_part_save(
                source,
                app,
                str(target),
                True,
                steps_report,
                visible=False,
            )

            self.assertTrue(report["attempted"])
            self.assertTrue(report["saved"])
            self.assertEqual(target.read_text(encoding="utf-8"), "partial-content")
            self.assertIsNone(report["error"])
            self.assertTrue(Path(report["document"]["path"]).samefile(target))

    def test_attempt_partial_generated_part_save_captures_save_failure(self) -> None:
        steps_report: list[dict[str, object]] = []

        original = BRIDGE._save_generated_part_document
        self.addCleanup(setattr, BRIDGE, "_save_generated_part_document", original)
        BRIDGE._save_generated_part_document = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("save_failed"))

        report = BRIDGE._attempt_partial_generated_part_save(
            object(),
            object(),
            "C:/tmp/partial.m3d",
            True,
            steps_report,
            visible=False,
        )

        self.assertTrue(report["attempted"])
        self.assertFalse(report["saved"])
        self.assertEqual(report["error"], "save_failed")
        self.assertIsNone(report["document"])

    def test_owned_cleanup_never_targets_foreign_document_and_failure_report_does_not_call_com(self) -> None:
        from unittest.mock import Mock, patch
        original = BRIDGE._cast_to_com_interface
        self.addCleanup(setattr, BRIDGE, "_cast_to_com_interface", original)
        owned, foreign = Mock(), Mock()
        BRIDGE._cast_to_com_interface = lambda obj, name: obj
        app = Mock(ActiveDocument=foreign)
        BRIDGE._close_generated_document(owned, app)
        owned.Close.assert_called_once_with(0)
        foreign.Close.assert_not_called()
        BRIDGE._close_generated_document(None, app)
        foreign.Close.assert_not_called()
        owned.reset_mock()
        with patch.object(BRIDGE, "report_progress") as progress:
            BRIDGE._report_retained_partial_document(owned, "C:/tmp/intended.m3d", "sketch_update")
            owned.assert_not_called()
            owned.Close.assert_not_called()
            report = progress.call_args.kwargs
            self.assertEqual(report["cleanup"], {
                "attempted": False, "verified_closed": False,
                "reason": "CAD outcome unknown; explicit user recovery required",
            })
            self.assertIsNone(report["partial_document"]["document_id"])

    def test_native_session_modes_pin_identity_and_never_hide_an_existing_instance(self) -> None:
        import importlib.util
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from kompas_mcp.cad_session_policy import CadSessionPolicy
        from kompas_mcp.session_guard import SessionGuard

        runtime_path = Path(__file__).resolve().parents[1] / "src/kompas_mcp/assets/bridge/cad_session_runtime.py"
        spec = importlib.util.spec_from_file_location("session_runtime_test", runtime_path)
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)

        owners, pids = {10: 20, 20: None}, {10: 1, 20: 1}

        def owning_pid(hwnd, output):
            output._obj.value = pids[hwnd]
            return True

        windows = SimpleNamespace(GetAncestor=lambda hwnd, flag: hwnd,
                                  GetWindow=lambda hwnd, flag: owners[hwnd],
                                  GetWindowThreadProcessId=owning_pid)
        self.assertEqual(runtime._presentation_window(10, 1, windows), 20)
        pids[20] = 2
        with self.assertRaisesRegex(RuntimeError, "another process"):
            runtime._presentation_window(10, 1, windows)
        pids[20] = 1
        owners[20] = 10
        with self.assertRaisesRegex(RuntimeError, "cyclic"):
            runtime._presentation_window(10, 1, windows)

        def app(hwnd, pid, visible):
            result = SimpleNamespace(MainWindowHandle=hwnd, pid=pid, started=pid*100, Visible=visible,
                                     Documents=Mock(), ActivateControllerAPI=Mock())
            result.ksGetApplication7 = lambda: result
            return result

        def identity(value):
            return {"window_handle": value.MainWindowHandle, "process_id": value.pid,
                    "process_started_at": value.started, "window_visible": value.Visible}

        with tempfile.TemporaryDirectory() as directory:
            policy = CadSessionPolicy(SessionGuard(directory))
            user, other, owned = app(10, 1, True), app(20, 2, False), app(30, 3, True)
            client = Mock()
            client.GetActiveObject.return_value = user
            with patch.object(runtime, "window_identity", side_effect=identity), patch.object(runtime, "visible_process_ids", return_value={1}):
                session = runtime.Session(policy.prepare())
                selected = session.attach(client)
                selected.Documents.Add(4, False)
                selected.Documents.Open("model.m3d", False, True)
                user.Documents.Add.assert_called_once_with(4, True)
                user.Documents.Open.assert_called_once_with("model.m3d", True, True)
                client.DispatchEx.assert_not_called()
                self.assertTrue(user.Visible)
                self.assertFalse(other.Visible)
                user.ActivateControllerAPI.reset_mock()
                user.ActiveDocument = None
                user.Documents.Count = 0
                user.ActiveDocument2D = Mock(return_value=None)
                user.ActiveDocument3D = Mock(return_value=SimpleNamespace(IsEditMode=lambda: 0))
                clear = {"observed_clear": True, "blockers": []}
                with patch.object(runtime, "recovery_window_state", return_value=clear):
                    audit = runtime.Session(policy.prepare()).audit_recovery(client, BRIDGE)
                    self.assertTrue(audit["session_observed_clear"])
                    self.assertFalse(audit["model_verified"])
                    user.ActivateControllerAPI.assert_not_called()
                    client.DispatchEx.assert_not_called()
                    user.ActiveDocument2D.return_value = SimpleNamespace(ksIsActiveProcessRunnig=lambda: 0)
                    audit = runtime.Session(policy.prepare()).audit_recovery(client, BRIDGE)
                    self.assertIn("possible_active_sketch_editor", audit["blockers"])
                    self.assertFalse(audit["session_observed_clear"])
                    user.ActiveDocument2D.return_value = None
                with patch.object(runtime, "recovery_window_state", return_value={
                        "observed_clear": False, "blockers": ["main_window_disabled"]}):
                    client.reset_mock()
                    audit = runtime.Session(policy.prepare()).audit_recovery(client, BRIDGE)
                    self.assertFalse(audit["session_observed_clear"])
                    client.GetActiveObject.assert_not_called()
                client.GetActiveObject.return_value = other
                with self.assertRaisesRegex(RuntimeError, "CAD_SESSION_CHANGED"):
                    runtime.Session(policy.prepare()).attach(client)
                client.DispatchEx.assert_not_called()

                policy.configure("hidden", confirm_switch=True)
                context = policy.prepare()
                client.DispatchEx.return_value = user
                with patch.object(runtime, "process_ids", return_value={1, 2}):
                    with self.assertRaisesRegex(RuntimeError, "CAD_HIDDEN_SESSION_NOT_ISOLATED"):
                        runtime.Session(context).attach(client)
                    self.assertTrue(user.Visible)
                    client.DispatchEx.return_value = owned
                    hidden = runtime.Session(context)
                    hidden_app = hidden.attach(client)
                self.assertFalse(owned.Visible)
                self.assertTrue(user.Visible)
                with patch("kompas_mcp.cad_session_policy.process_alive", return_value=True):
                    with self.assertRaisesRegex(RuntimeError, "CAD_HIDDEN_SESSION_ACTIVE"):
                        policy.configure("interactive", confirm_switch=True)
                hidden_app.Documents.Add(4, True)
                owned.Documents.Add.assert_called_once_with(4, False)
                client.GetActiveObject.return_value = owned
                previous_creations = client.DispatchEx.call_count
                runtime.Session(policy.prepare()).attach(client)
                self.assertEqual(client.DispatchEx.call_count, previous_creations)
                owned.Visible = True
                with self.assertRaisesRegex(RuntimeError, "CAD_MODE_MISMATCH"):
                    runtime.Session(policy.prepare()).attach(client)
                self.assertTrue(owned.Visible, "Must not silently hide a manually shown owned window")
                owned.Visible = False
                owned.started += 1
                with self.assertRaisesRegex(RuntimeError, "CAD_SESSION_CHANGED"):
                    runtime.Session(policy.prepare()).attach(client)
                owned.started -= 1
                owned.Documents.Count = 0
                owned.Quit = Mock(return_value=True)
                hidden.quit_owned()
                self.assertTrue(policy.read()["shutdown_requested"])
                self.assertIsNotNone(policy.read()["binding"], "Quit must not erase ownership before process exit")

    def test_interactive_save_retains_document_and_does_not_claim_reopen(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "visible.m3d")
            document, app = Mock(), Mock()
            mode = SimpleNamespace(mode="interactive", allow_explicit_close=False)
            with patch.object(BRIDGE, "_CAD_SESSION", mode), \
                 patch.object(BRIDGE, "_collect_open_documents_by_path", return_value=[]), \
                 patch.object(BRIDGE, "_require_document_save_success"), \
                 patch.object(BRIDGE, "describe_document", return_value={"path": path, "id": path}):
                retained, report = BRIDGE._save_document_via_staging(document, app, path, keep_open=False, visible=False)
                self.assertIs(retained, document)
                self.assertTrue(report["kept_open"])
                self.assertFalse(report["reopened"])
                document.Close.assert_not_called()
                app.Documents.Open.assert_not_called()
                self.assertFalse(BRIDGE._close_document_for_workflow(document))
                mode.allow_explicit_close = True
                self.assertTrue(BRIDGE._close_document_for_workflow(document))
                document.Close.assert_called_once_with(0)
                mode.allow_explicit_close = False
                document.reset_mock()
                with patch.object(BRIDGE, "_collect_open_documents_by_path", return_value=[{"description": {"changed": False}}]):
                    with self.assertRaisesRegex(RuntimeError, "already open in another"):
                        BRIDGE._save_document_via_staging(document, app, path)
                document.SaveAs.assert_not_called()

    def test_apply_saved_compression_spring_anchor_rotation_bindings_binds_to_spiral_path(self) -> None:
        class _FakeSpiral:
            def __init__(self, name: str) -> None:
                self.Name = name

        class _FakeAuxiliaryContainer:
            def __init__(self, spirals: list[Any]) -> None:
                self.Spirals3D = spirals

        class _FakePart:
            def __init__(self, spirals: list[Any]) -> None:
                self._auxiliary_container = _FakeAuxiliaryContainer(spirals)

        class _FakeSavedDocument:
            def __init__(self, spirals: list[Any]) -> None:
                self.TopPart = _FakePart(spirals)
                self.save_calls = 0
                self.close_calls: list[int] = []

            def Save(self) -> bool:
                self.save_calls += 1
                return True

            def Close(self, mode: int) -> None:
                self.close_calls.append(int(mode))

        spiral = _FakeSpiral("spring_working_path")
        document = _FakeSavedDocument([spiral])
        steps_report: list[dict[str, object]] = []
        binding_calls: list[tuple[Any, list[dict[str, Any]]]] = []

        original_open = BRIDGE._open_document_in_app
        original_cast = BRIDGE._cast_to_com_interface
        original_iter = BRIDGE.iter_collection
        original_bind = BRIDGE._bind_operation_variables
        self.addCleanup(setattr, BRIDGE, "_open_document_in_app", original_open)
        self.addCleanup(setattr, BRIDGE, "_cast_to_com_interface", original_cast)
        self.addCleanup(setattr, BRIDGE, "iter_collection", original_iter)
        self.addCleanup(setattr, BRIDGE, "_bind_operation_variables", original_bind)

        BRIDGE._open_document_in_app = lambda app, output_path, visible=False, read_only=False: (document, ["opened"])
        BRIDGE._cast_to_com_interface = (
            lambda obj, interface_name: obj._auxiliary_container if interface_name == "IAuxiliaryGeomContainer" else obj
        )
        BRIDGE.iter_collection = lambda collection: list(collection)

        def _fake_bind_operation_variables(model_object, planned_bindings):
            binding_calls.append((model_object, planned_bindings))
            return {
                "step": "bind_operation_variables",
                "ok": True,
                "applied_count": len(planned_bindings),
                "failed_count": 0,
                "planned_count": len(planned_bindings),
                "applied": [],
                "failed": [],
                "live_status": "applied",
            }

        BRIDGE._bind_operation_variables = _fake_bind_operation_variables

        report = BRIDGE._apply_saved_compression_spring_anchor_rotation_bindings(
            object(),
            "C:/tmp/spring.m3d",
            [
                {
                    "role": "working",
                    "path_name": "spring_working_path",
                    "expression": "360 * (N21)",
                }
            ],
            steps_report,
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["applied_count"], 1)
        self.assertEqual(document.save_calls, 1)
        self.assertEqual(document.close_calls, [0])
        self.assertEqual(len(binding_calls), 1)
        self.assertIs(binding_calls[0][0], spiral)
        self.assertEqual(binding_calls[0][1][0]["expression"], "360 * (N21)")
        self.assertEqual(binding_calls[0][1][0]["parameter_note"], "Angle")
        self.assertIn("Угол", binding_calls[0][1][0]["parameter_note_aliases"])
        self.assertIn("Угол вращения", binding_calls[0][1][0]["parameter_note_aliases"])
        self.assertEqual(steps_report[-1]["step"], "post_save_bind_spring_anchor_rotation")


class DiaphragmReopenOwnershipTests(unittest.TestCase):
    def test_pattern_sources_are_not_confused_with_same_named_copies(self):
        def item(name, ref):
            return types.SimpleNamespace(Name=name, Reference=ref, Valid=True, Hidden=True, ConstraintsState=1)
        sources = [item("Diaphragm slot cut", 10), item("Diaphragm relief cut", 11)]
        pattern = item("Diaphragm cuts", 2)
        pattern.InitialObjects = tuple(sources)
        pattern.Count2, pattern.Step2, pattern.SaveInitialOrientation = 12, 30, False
        sketches = [item(name, i + 3) for i, name in enumerate(("Diaphragm spring profile", "Cut radius references", "Cut profile sketch", "Terminal relief sketch"))]
        model = types.SimpleNamespace(Rotateds=[item("Diaphragm spring body", 1)], FeaturePatterns=[pattern],
            Sketchs=sketches, Extrusions=sources + [item(source.Name, i + 20) for i, source in enumerate(sources)])
        part = types.SimpleNamespace(Planes3D=[item("Diaphragm tangent plane", 40)],
            Points3D=[item("Cut start projection", 41), item("Cut end projection", 42)])
        model.Points3D = part.Points3D
        recipe = {"profile_name":"Diaphragm spring profile", "sweep_name":"Diaphragm spring body", "parameters":{"slot_count":12}}
        with patch.object(BRIDGE, "cast_model_container", return_value=model), \
             patch.object(BRIDGE, "_cast_to_com_interface", side_effect=lambda obj, _interface: obj), \
             patch.object(BRIDGE, "iter_collection", side_effect=lambda collection: list(collection)):
            result = BRIDGE._diaphragm_module_readback(part, recipe)
            self.assertEqual(result["initial_object_count"], 2)
            self.assertIn(10, result["owned_references"])
            self.assertNotIn(20, result["owned_references"])
            self.assertTrue(result["auxiliary_geometry_hidden"])
            pattern.InitialObjects = (sources[0], sources[0])
            with self.assertRaisesRegex(RuntimeError, "both slot and relief"):
                BRIDGE._diaphragm_module_readback(part, recipe)
            pattern.InitialObjects = tuple(sources)
            pattern.Count2 = 11
            with self.assertRaisesRegex(RuntimeError, "pattern parameters"):
                BRIDGE._diaphragm_module_readback(part, recipe)
            pattern.Count2 = 12
            part.Planes3D[0].Hidden = False
            with self.assertRaisesRegex(RuntimeError, "missing or visible"):
                BRIDGE._diaphragm_module_readback(part, recipe)


if __name__ == "__main__":
    unittest.main()
