from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any


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


if __name__ == "__main__":
    unittest.main()
