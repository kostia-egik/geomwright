from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from kompas_mcp.native_modules import inspect_native_module
from kompas_mcp.native_modules import list_native_modules
from kompas_mcp.native_modules import preview_native_module_launch
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


if __name__ == "__main__":
    unittest.main()
