from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


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
    def test_build_save_staging_path_keeps_target_directory_and_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "part.m3d"
            candidate = BRIDGE._build_save_staging_path(str(target))

        self.assertEqual(Path(candidate).parent, target.parent)
        self.assertEqual(Path(candidate).suffix.lower(), ".m3d")
        self.assertNotEqual(Path(candidate).name, target.name)

    def test_save_document_via_staging_replaces_target_and_reopens_closed_target(self) -> None:
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
            self.assertIsNotNone(reopened_document)
            self.assertTrue(
                BRIDGE.build_path_aliases(reopened_document.PathName).intersection(BRIDGE.build_path_aliases(str(target)))
            )
            self.assertEqual(len(report["closed_target_documents"]), 1)
            self.assertTrue(
                BRIDGE.build_path_aliases(report["reopened_document"]["path"]).intersection(
                    BRIDGE.build_path_aliases(str(target))
                )
            )

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


if __name__ == "__main__":
    unittest.main()
