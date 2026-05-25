from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from kompas_mcp.native_modules import inspect_native_module
from kompas_mcp.native_modules import list_native_modules
from kompas_mcp.native_modules import preview_native_module_launch
from kompas_mcp.native_module_result import capture_native_module_result
from kompas_mcp.native_module_result import diff_native_module_results
from kompas_mcp.native_module_result import start_native_module_result_probe
from kompas_mcp.adapter import KompasAdapter


class NativeModuleDiscoveryTests(unittest.TestCase):
    def test_lists_manifest_commands_from_libs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            libs_dir = _create_spring_fixture(Path(temp_dir))

            payload = list_native_modules(libs_dir=str(libs_dir))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["module_count"], 1)
        self.assertEqual(payload["modules"][0]["name"], "Spring")
        self.assertEqual(payload["modules"][0]["title"], "Mechanics: Springs")
        self.assertEqual(payload["modules"][0]["commands"][0]["id"], 101)
        self.assertEqual(payload["modules"][0]["commands"][0]["title"], "Compression springs")

    def test_inspects_spring_files_and_sqlite_inventory_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            libs_dir = _create_spring_fixture(Path(temp_dir))

            payload = inspect_native_module("Spring", libs_dir=str(libs_dir))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["integration_status"]["mode"], "read_only_discovery")
        self.assertFalse(payload["integration_status"]["launch_supported"])
        self.assertEqual(payload["runtime_files"][0]["name"], "SPR_CCS.dll")
        self.assertEqual(payload["spring"]["module_kind"], "calculation_workflow")
        self.assertEqual(payload["spring"]["commands"][0]["workflow"][0], "design_calculation")
        self.assertEqual(payload["spring"]["commands"][0]["help_key"], "IDD_HELP_CCS")
        self.assertEqual(payload["database_inventory"][0]["tables"][0]["name"], "MATERIALS")
        self.assertEqual(payload["database_inventory"][0]["tables"][0]["row_count"], 2)

    def test_missing_module_returns_available_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            libs_dir = _create_spring_fixture(Path(temp_dir))

            payload = inspect_native_module("Gear", libs_dir=str(libs_dir))

        self.assertFalse(payload["ok"])
        self.assertIn("Spring", payload["available_modules"])
        self.assertIn("was not found", payload["error"])

    def test_previews_native_spring_launch_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            libs_dir = _create_spring_fixture(Path(temp_dir))

            payload = preview_native_module_launch("Spring", libs_dir=str(libs_dir), command_id=101)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["module"], "Spring")
        self.assertEqual(payload["command"]["id"], 101)
        self.assertEqual(payload["launch_contract"]["mode"], "interactive_native_module_command")
        self.assertFalse(payload["launch_contract"]["parameter_automation"])

    def test_adapter_requires_explicit_interactive_launch_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            libs_dir = _create_spring_fixture(Path(temp_dir))
            runner = _FakeNativeLaunchRunner()
            adapter = KompasAdapter(runner=runner)

            payload = adapter.launch_native_module_command(libs_dir=str(libs_dir))

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["launch_attempted"])
        self.assertEqual(runner.calls, [])

    def test_adapter_calls_bridge_for_allowed_interactive_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            libs_dir = _create_spring_fixture(Path(temp_dir))
            runner = _FakeNativeLaunchRunner()
            adapter = KompasAdapter(runner=runner)

            payload = adapter.launch_native_module_command(
                libs_dir=str(libs_dir),
                allow_interactive=True,
            )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["launch_attempted"])
        self.assertEqual(runner.calls[0][0], "launch_native_module_command")
        self.assertEqual(runner.calls[0][1]["module"], "Spring")
        self.assertEqual(runner.calls[0][1]["command_id"], 101)

    def test_captures_native_module_result_after_interactive_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            libs_dir = _create_spring_fixture(Path(temp_dir))
            adapter = _FakeNativeResultAdapter()

            payload = capture_native_module_result(adapter, libs_dir=str(libs_dir), max_items=1)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["module"], "Spring")
        self.assertEqual(payload["command"]["id"], 101)
        self.assertEqual(payload["status"], "document_readback_captured")
        self.assertIn("not proven", payload["result_assumption"])
        self.assertFalse(payload["launch_attempted"])
        self.assertTrue(payload["readback_only"])
        self.assertEqual(payload["documents"]["selected"]["id"], "doc-1")
        self.assertEqual(payload["active_document_state"]["state"]["counts"]["items_returned"], 1)
        self.assertEqual(adapter.calls, ["session", "list", "active:doc-1"])

    def test_native_module_result_reports_missing_document_without_launching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            libs_dir = _create_spring_fixture(Path(temp_dir))
            adapter = _FakeNativeResultAdapter(documents=[])

            payload = capture_native_module_result(adapter, libs_dir=str(libs_dir))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "no_document_readback_available")
        self.assertIsNone(payload["documents"]["selected"])
        self.assertIsNone(payload["active_document_state"])
        self.assertEqual(adapter.calls, ["session", "list"])

    def test_diffs_native_module_result_captures(self) -> None:
        before = _native_capture_payload(
            documents=[{"id": "doc-1", "name": "base.m3d", "active": True}],
            selected={"id": "doc-1", "name": "base.m3d", "active": True},
            counts={"items": 3, "tree_nodes": 5},
        )
        after = _native_capture_payload(
            documents=[
                {"id": "doc-1", "name": "base.m3d", "active": False},
                {"id": "doc-2", "name": "spring.m3d", "active": True},
            ],
            selected={"id": "doc-2", "name": "spring.m3d", "active": True},
            counts={"items": 8, "tree_nodes": 12},
        )

        payload = diff_native_module_results(before, after)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "native_result_delta_detected")
        self.assertEqual(payload["evidence_level"], "new_document_detected")
        self.assertEqual(payload["summary"]["added_documents"], 1)
        self.assertTrue(payload["summary"]["selected_document_changed"])
        self.assertEqual(payload["documents"]["added"][0]["id"], "doc-2")
        self.assertEqual(payload["active_document_counts"]["delta"]["items"], 5)

    def test_diffs_native_module_result_captures_without_delta(self) -> None:
        before = _native_capture_payload(
            documents=[{"id": "doc-1", "name": "base.m3d", "active": True}],
            selected={"id": "doc-1", "name": "base.m3d", "active": True},
            counts={"items": 3, "tree_nodes": 5},
        )
        after = _native_capture_payload(
            documents=[{"id": "doc-1", "name": "base.m3d", "active": True}],
            selected={"id": "doc-1", "name": "base.m3d", "active": True},
            counts={"items": 3, "tree_nodes": 5},
        )

        payload = diff_native_module_results(before, after)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "no_native_result_delta_detected")
        self.assertEqual(payload["evidence_level"], "no_detected_delta")
        self.assertEqual(payload["summary"]["added_documents"], 0)

    def test_starts_native_module_result_probe_preview_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            libs_dir = _create_spring_fixture(Path(temp_dir))
            adapter = _FakeNativeResultAdapter()

            payload = start_native_module_result_probe(adapter, libs_dir=str(libs_dir))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "preview_only")
        self.assertFalse(payload["workflow"]["launch_attempted"])
        self.assertEqual(payload["before_capture"]["status"], "document_readback_captured")
        self.assertEqual(adapter.launches[0]["allow_interactive"], False)
        self.assertIn("allow_interactive=true", payload["next_step"])

    def test_starts_native_module_result_probe_with_interactive_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            libs_dir = _create_spring_fixture(Path(temp_dir))
            adapter = _FakeNativeResultAdapter()

            payload = start_native_module_result_probe(
                adapter,
                libs_dir=str(libs_dir),
                allow_interactive=True,
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "waiting_for_manual_native_workflow_completion")
        self.assertTrue(payload["workflow"]["launch_attempted"])
        self.assertTrue(payload["workflow"]["requires_user_to_complete_native_ui"])
        self.assertEqual(payload["next_calls"]["after_capture"]["tool"], "capture_native_module_result")
        self.assertEqual(adapter.launches[0]["allow_interactive"], True)


def _create_spring_fixture(root: Path) -> Path:
    libs_dir = root / "Libs"
    spring_dir = libs_dir / "Spring"
    base_dir = spring_dir / "Base"
    base_dir.mkdir(parents=True)
    (spring_dir / "SPRING.xml").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<application id="SPRING-APP" title="Mechanics: Springs" helpDb="SPRING" showInMenu="true">
  <toolBarSet id="toolbar" title="Springs">
    <toolBar id="spring" title="Springs">
      <appCommand id="101" title="Compression springs" appIcon="E000"/>
      <appCommand id="102" title="Extension springs" appIcon="E001"/>
    </toolBar>
  </toolBarSet>
</application>
""",
        encoding="utf-16",
    )
    (spring_dir / "SPR_CCS.dll").write_bytes(b"fake")
    _create_sqlite_database(base_dir / "Spring.sdb")
    _create_help_database(spring_dir / "SPRING_ru-RU.db")
    return libs_dir


class _FakeNativeLaunchRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, action: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        self.calls.append((action, payload))
        return {
            "ok": True,
            "module": payload.get("module"),
            "execute": {"ok": True, "successful_attempt": "automation_execute"},
            "documents": {"before_count": 0, "after_count": 0},
        }


class _FakeNativeResultAdapter:
    def __init__(self, documents: list[dict] | None = None) -> None:
        self.document = {"id": "doc-1", "name": "spring.m3d", "path": r"C:\Temp\spring.m3d", "active": True}
        self.documents = [self.document] if documents is None else documents
        self.calls: list[str] = []
        self.launches: list[dict] = []

    def get_session_state(self) -> dict:
        self.calls.append("session")
        return {
            "kompas_connected": True,
            "documents_count": len(self.documents),
            "active_document": self.documents[0] if self.documents else None,
        }

    def list_documents(self) -> dict:
        self.calls.append("list")
        return {"documents": self.documents}

    def get_active_document_state(
        self,
        document_id: str | None = None,
        *,
        require_active_document: bool = True,
        include_tree: bool = False,
        include_items: bool = False,
        max_items: int = 25,
    ) -> dict:
        self.calls.append(f"active:{document_id}")
        return {
            "ok": True,
            "state": {
                "document": self.document,
                "counts": {"tree_nodes": 3, "items": 2, "items_returned": min(max_items, 2)},
                "tree_preview": {"id": "doc-1", "name": "spring.m3d", "children_count": 1},
                "items_preview": [{"id": "solid-1", "name": "Spring"}][:max_items],
            },
        }

    def launch_native_module_command(
        self,
        *,
        module: str = "Spring",
        command_id: int | str | None = 101,
        command_title: str | None = None,
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        post: bool = True,
        visible: bool = True,
        allow_interactive: bool = False,
    ) -> dict:
        self.launches.append(
            {
                "module": module,
                "command_id": command_id,
                "allow_interactive": allow_interactive,
                "post": post,
                "visible": visible,
            }
        )
        return {
            "ok": True,
            "module": module,
            "command": {"id": command_id, "title": command_title or "Compression springs"},
            "launch_attempted": bool(allow_interactive),
            "status": "launched" if allow_interactive else "preview_only",
        }


def _create_sqlite_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("create table MATERIALS (ID integer primary key, NAME text)")
        connection.executemany(
            "insert into MATERIALS (ID, NAME) values (?, ?)",
            [(1, "Steel A"), (2, "Steel B")],
        )
        connection.commit()
    finally:
        connection.close()


def _create_help_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("create table Ids (Id integer, Name text)")
        connection.execute("create table Help (Id text, D1 text, D2 text, D3 text)")
        connection.execute("insert into Ids (Id, Name) values (101, 'IDD_HELP_CCS')")
        connection.execute(
            "insert into Help (Id, D1, D2, D3) values (?, ?, ?, ?)",
            (
                "IDD_HELP_CCS",
                "Design and verification calculation for compression springs.",
                "Calculation method: fixture standard.",
                "Build model or drawing without calculation.",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _native_capture_payload(
    *,
    documents: list[dict],
    selected: dict,
    counts: dict,
) -> dict:
    return {
        "ok": True,
        "module": "Spring",
        "command": {"id": 101, "title": "Compression springs"},
        "documents": {
            "count": len(documents),
            "selected": selected,
            "payload": {"documents": documents},
        },
        "active_document_state": {"ok": True, "state": {"counts": counts}},
    }


if __name__ == "__main__":
    unittest.main()
