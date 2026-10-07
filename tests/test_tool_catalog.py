import ast
import inspect
from pathlib import Path
import unittest

from kompas_mcp.tool_catalog import get_mcp_tool_catalog


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
PACKAGE_ROOT = SOURCE_ROOT / "kompas_mcp"
SERVER_PATH = SOURCE_ROOT / "geomwright" / "kompas" / "server.py"
TOOL_MODULE_PATHS = sorted(PACKAGE_ROOT.glob("*_tools.py"))


class ToolCatalogTests(unittest.TestCase):
    def test_catalog_covers_server_tools_without_duplicates(self) -> None:
        catalog = get_mcp_tool_catalog()
        catalog_tools = [
            tool
            for category in catalog["categories"]
            for tool in category["tools"]
        ]
        server_tools = _registered_tool_names()

        self.assertEqual(len(catalog_tools), len(set(catalog_tools)))
        self.assertEqual(set(catalog_tools), set(server_tools))
        self.assertEqual(catalog["tool_count"], len(server_tools))

    def test_can_filter_by_category(self) -> None:
        catalog = get_mcp_tool_catalog(category="low_level_runtime")

        self.assertTrue(catalog["ok"])
        self.assertEqual(catalog["category_count"], 1)
        self.assertIn("probe_document_readback", catalog["categories"][0]["tools"])

    def test_can_filter_by_stability(self) -> None:
        catalog = get_mcp_tool_catalog(stability="research", include_research=True)

        self.assertTrue(catalog["ok"])
        self.assertEqual(catalog["stability"], "research")
        self.assertIn(
            "native_modules",
            [category["name"] for category in catalog["categories"]],
        )
        self.assertTrue(
            all(category["stability"] == "research" for category in catalog["categories"])
        )

    def test_can_filter_by_category_and_stability(self) -> None:
        catalog = get_mcp_tool_catalog(category="native_modules", stability="stable")

        self.assertFalse(catalog["ok"])
        self.assertEqual(catalog["tool_count"], 0)

    def test_unknown_category_returns_empty_catalog(self) -> None:
        catalog = get_mcp_tool_catalog(category="missing")

        self.assertFalse(catalog["ok"])
        self.assertEqual(catalog["tool_count"], 0)

    def test_every_category_declares_stability(self) -> None:
        catalog = get_mcp_tool_catalog()

        self.assertTrue(
            all(
                category.get("stability") in {"stable", "experimental", "research"}
                for category in catalog["categories"]
            )
        )

    def test_server_tool_exposes_stability_filter(self) -> None:
        from geomwright.kompas import server

        catalog = server.get_mcp_tool_catalog(stability="research", include_research=True)

        self.assertFalse(catalog["ok"])
        self.assertEqual(catalog["stability"], "research")

    def test_research_tools_are_not_registered_or_catalogued_by_default(self) -> None:
        from geomwright.kompas import server

        self.assertNotIn("list_native_modules", _registered_tool_names())
        self.assertFalse(server.get_mcp_tool_catalog(stability="research")["ok"])

    def test_geomwright_server_facade_preserves_the_mcp_contract(self) -> None:
        from geomwright import server as public_server
        from geomwright.kompas import KompasAdapter, get_mcp_tool_catalog
        from geomwright.kompas import server as kompas_server
        from kompas_mcp import server as legacy_server
        from kompas_mcp.adapter import KompasAdapter as LegacyKompasAdapter

        self.assertIs(public_server.mcp, kompas_server.mcp)
        self.assertIs(public_server.mcp, legacy_server.mcp)
        self.assertIs(public_server.adapter, kompas_server.adapter)
        self.assertIs(public_server.adapter, legacy_server.adapter)
        self.assertIs(KompasAdapter, LegacyKompasAdapter)
        self.assertEqual(public_server.mcp.name, "geomwright")
        self.assertEqual(get_mcp_tool_catalog(), public_server.get_mcp_tool_catalog())
        self.assertEqual(
            public_server.get_mcp_tool_catalog(),
            legacy_server.get_mcp_tool_catalog(),
        )

    def test_probe_document_readback_surface_closes_model_path_by_default(self) -> None:
        from geomwright.kompas import server
        from geomwright.kompas.adapter import KompasAdapter

        tool_fn = server.mcp._tool_manager._tools["probe_document_readback"].fn
        server_default = inspect.signature(tool_fn).parameters["close_after_probe"].default
        adapter_default = inspect.signature(KompasAdapter.probe_document_readback).parameters["close_after_probe"].default

        self.assertIs(server_default, True)
        self.assertIs(adapter_default, True)

    def test_registered_tools_live_in_server_or_registration_modules(self) -> None:
        source_tools = set(_source_tool_names([SERVER_PATH, *TOOL_MODULE_PATHS]))
        from geomwright.kompas import server

        if not server._research_tools_enabled():
            source_tools -= {
                "list_native_modules",
                "inspect_native_module",
                "inspect_native_module_interfaces",
                "inspect_native_spring_workflow",
                "probe_native_module_programmatic_access",
                "inspect_native_module_entrypoints",
                "plan_native_entrypoint_validation",
                "inspect_native_entrypoint_static_abi",
                "probe_native_entrypoint_loader",
                "probe_native_entrypoint_loader_hosted",
                "launch_native_module_command",
                "start_native_module_result_probe",
                "capture_native_module_result",
                "diff_native_module_results",
            }

        self.assertEqual(source_tools, set(_registered_tool_names()))

    def test_silent_chain_mcp_preflight_and_write_boundary(self) -> None:
        from unittest.mock import Mock
        from mcp.server.fastmcp import FastMCP
        from kompas_mcp.bridge_runner import BridgeError
        from kompas_mcp.silent_chain_tools import register_silent_chain_tools
        from kompas_mcp.transmissions.silent_geometry import SilentChainSelectionRequest

        adapter = Mock()
        mcp = FastMCP("silent-contract")
        register_silent_chain_tools(mcp, adapter)
        tools = {name: tool.fn for name, tool in mcp._tool_manager._tools.items()}
        page = tools["list_silent_chain_profiles"](standard="din_8190_8191_open", limit=2)
        self.assertEqual(len(page["profiles"]), 2)
        self.assertTrue(page["has_more"])
        self.assertEqual(tools["list_silent_chain_profiles"](query="no-such-size")["total"], 0)
        request = SilentChainSelectionRequest(standard="din_8190_8191_open", family="outer",
                                             designation="08-020A", physical_tooth_count=23)
        preview = tools["preview_silent_chain_sprocket"](request)
        self.assertTrue(preview["completion"]["ready_for_cad_planning"])
        self.assertNotIn("geometry", preview)
        planned = tools["create_silent_chain_sprocket"](request)
        self.assertFalse(planned["executed"])
        self.assertNotIn("plan", planned)
        adapter.create_silent_chain_sprocket.assert_not_called()
        with self.assertRaisesRegex(ValueError, "confirm_write"):
            tools["create_silent_chain_sprocket"](request, execute=True)
        adapter.create_silent_chain_sprocket.assert_not_called()
        incomplete = SilentChainSelectionRequest(designation="PZ-1-19.05-74-45",
                                                 physical_tooth_count=17, accuracy_class=1)
        refused = tools["create_silent_chain_sprocket"](incomplete, execute=True, confirm_write=True)
        self.assertEqual(refused["stage"], "needs_input")
        adapter.create_silent_chain_sprocket.assert_not_called()
        error = BridgeError("native failure")
        error.partial_result = {"document": {"runtime_id": "@document:0"}, "rollback_performed": False}
        adapter.create_silent_chain_sprocket.side_effect = error
        failed = tools["create_silent_chain_sprocket"](request, execute=True, confirm_write=True)
        self.assertEqual(failed["partial_result"], error.partial_result)
        self.assertFalse(failed["success"])
        self.assertTrue(failed["executed"])
        adapter.create_silent_chain_sprocket.side_effect = None
        adapter.create_silent_chain_sprocket.return_value = {
            "ok": True, "success": True, "executed": True,
            "body": {"volume": 1.0}, "document": {"runtime_id": "@document:0"},
            "readback": {"large_native_arrays": []}, "steps": []}
        created = tools["create_silent_chain_sprocket"](request, execute=True, confirm_write=True)
        self.assertTrue(created["success"])
        self.assertEqual(created["body_units"]["volume"], "cm3")
        self.assertNotIn("readback", created)
        self.assertNotIn("steps", created)

    def test_gear_mcp_preflight_and_write_boundary(self) -> None:
        from unittest.mock import Mock

        from mcp.server.fastmcp import FastMCP

        from kompas_mcp.gear_tools import register_gear_tools
        from kompas_mcp.gears import SpurGearCreateRequest, SpurGearRequest

        adapter = Mock()
        mcp = FastMCP("gear-contract")
        register_gear_tools(mcp, adapter)
        tools = {name: tool.fn for name, tool in mcp._tool_manager._tools.items()}

        standards = tools["list_gear_standards"]()
        self.assertEqual(
            [item["value"] for item in standards["standards"]],
            ["gost_13755_2015", "gost_9587_81", "gost_r_50531_93", "iso_53_1998"],
        )

        preview_request = SpurGearRequest(
            standard="iso_53_1998", modification="b",
            module_mm=2.0, tooth_count=20, face_width_mm=20.0,
        )
        preview = tools["preview_cylindrical_gear"](preview_request)
        self.assertTrue(preview["success"])
        self.assertEqual(preview["family"], "gear_spur")
        adapter.create_gear_spur.assert_not_called()

        create_request = SpurGearCreateRequest(
            standard="gost_9587_81", modification="h1_c25",
            module_mm=0.5, tooth_count=24, face_width_mm=6.0,
        )
        adapter.create_gear_spur.return_value = {
            "ok": True, "success": True, "executed": False, "stage": "planned",
        }
        planned = tools["create_cylindrical_gear"](create_request)
        self.assertFalse(planned["executed"])
        adapter.create_gear_spur.assert_called_once()
        self.assertFalse(adapter.create_gear_spur.call_args.kwargs["execute"])
        adapter.create_gear_spur.reset_mock()
        with self.assertRaisesRegex(ValueError, "confirm_write"):
            SpurGearCreateRequest(
                standard="gost_9587_81", modification="h1_c25",
                module_mm=0.5, tooth_count=24, face_width_mm=6.0,
                execute=True,
            )
        adapter.create_gear_spur.assert_not_called()

        adapter.inspect_gear_spur.return_value = {"module": "gear_spur", "recipe": {"version": 1}}
        inspected = tools["inspect_cylindrical_gear"]("doc-1")
        self.assertEqual(inspected["module"], "gear_spur")
        adapter.inspect_gear_spur.return_value = {"module": "v_belt"}
        with self.assertRaisesRegex(ValueError, "recognized gear block"):
            tools["inspect_cylindrical_gear"]("doc-2")

        from kompas_mcp.gears import InternalGearCreateRequest, InternalGearRequest

        internal_preview_request = InternalGearRequest(
            module_mm=2.0, tooth_count=40, face_width_mm=20.0,
            ring_outside_diameter_mm=100.0,
        )
        internal_preview = tools["preview_internal_gear"](internal_preview_request)
        self.assertTrue(internal_preview["success"])
        self.assertEqual(internal_preview["family"], "gear_internal")
        self.assertEqual(internal_preview["summary"]["ring_outside_diameter_mm"], 100.0)
        adapter.create_gear_internal.assert_not_called()

        internal_create_request = InternalGearCreateRequest(
            module_mm=2.0, tooth_count=40, face_width_mm=20.0,
            ring_outside_diameter_mm=100.0,
        )
        adapter.create_gear_internal.return_value = {
            "ok": True, "success": True, "executed": False, "stage": "planned",
        }
        internal_planned = tools["create_internal_gear"](internal_create_request)
        self.assertFalse(internal_planned["executed"])
        adapter.create_gear_internal.assert_called_once()
        self.assertFalse(adapter.create_gear_internal.call_args.kwargs["execute"])
        adapter.create_gear_internal.reset_mock()
        with self.assertRaisesRegex(ValueError, "confirm_write"):
            InternalGearCreateRequest(
                module_mm=2.0, tooth_count=40, face_width_mm=20.0,
                ring_outside_diameter_mm=100.0, execute=True,
            )
        adapter.create_gear_internal.assert_not_called()

        adapter.inspect_gear_internal.return_value = {"module": "gear_internal", "recipe": {"version": 1}}
        internal_inspected = tools["inspect_internal_gear"]("doc-1")
        self.assertEqual(internal_inspected["module"], "gear_internal")
        adapter.inspect_gear_internal.return_value = {"module": "gear_spur"}
        with self.assertRaisesRegex(ValueError, "recognized internal gear block"):
            tools["inspect_internal_gear"]("doc-2")

        from kompas_mcp.gears import BevelGearCreateRequest, BevelGearRequest

        bevel_preview = tools["preview_bevel_gear"](
            BevelGearRequest(module_mm=3.0, tooth_count=20, pitch_cone_angle_deg=45.0)
        )
        self.assertTrue(bevel_preview["success"])
        self.assertEqual(bevel_preview["family"], "gear_bevel")
        self.assertGreater(
            bevel_preview["summary"]["outer_tip_diameter_mm"],
            bevel_preview["summary"]["outer_pitch_diameter_mm"],
        )
        adapter.create_gear_bevel.assert_not_called()
        bevel_selection = tools["list_gear_standards"]()
        self.assertIn(
            "gost_13754_68",
            [item["value"] for item in bevel_selection["bevel_standards"]],
        )
        with self.assertRaisesRegex(ValueError, "straight"):
            BevelGearRequest(tooth_type="circular")

        adapter.create_gear_bevel.return_value = {
            "ok": True, "success": True, "executed": False, "stage": "planned",
        }
        bevel_planned = tools["create_bevel_gear"](
            BevelGearCreateRequest(module_mm=3.0, tooth_count=20, pitch_cone_angle_deg=45.0)
        )
        self.assertFalse(bevel_planned["executed"])
        adapter.create_gear_bevel.assert_called_once()
        self.assertFalse(adapter.create_gear_bevel.call_args.kwargs["execute"])
        adapter.create_gear_bevel.reset_mock()
        with self.assertRaisesRegex(ValueError, "confirm_write"):
            BevelGearCreateRequest(
                module_mm=3.0, tooth_count=20, pitch_cone_angle_deg=45.0, execute=True,
            )
        adapter.create_gear_bevel.assert_not_called()

        adapter.inspect_gear_bevel.return_value = {"module": "gear_bevel", "recipe": {"kind": "bevel"}}
        bevel_inspected = tools["inspect_bevel_gear"]("doc-bevel")
        self.assertEqual(bevel_inspected["module"], "gear_bevel")
        adapter.inspect_gear_bevel.return_value = {"module": "gear_spur"}
        with self.assertRaisesRegex(ValueError, "recognized bevel gear block"):
            tools["inspect_bevel_gear"]("doc-bevel-2")

    def test_server_stays_bootstrap_sized(self) -> None:
        server_tool_names = _source_tool_names([SERVER_PATH])
        self.assertLessEqual(len(SERVER_PATH.read_text(encoding="utf-8").splitlines()), 120)

    def test_registration_modules_do_not_import_server(self) -> None:
        for path in TOOL_MODULE_PATHS:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("from .server", source)
                self.assertNotIn("import server", source)


def _registered_tool_names() -> list[str]:
    from geomwright.kompas import server

    return list(server.mcp._tool_manager._tools)


def _source_tool_names(paths: list[Path]) -> list[str]:
    names: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(_is_mcp_tool_decorator(decorator) for decorator in node.decorator_list):
                names.append(node.name)
    return names


def _is_mcp_tool_decorator(decorator: ast.AST) -> bool:
    if isinstance(decorator, ast.Call):
        decorator = decorator.func
    return (
        isinstance(decorator, ast.Attribute)
        and decorator.attr == "tool"
        and isinstance(decorator.value, ast.Name)
        and decorator.value.id == "mcp"
    )


if __name__ == "__main__":
    unittest.main()
