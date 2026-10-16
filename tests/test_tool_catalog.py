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
    def test_model_png_host_contract_and_preflight_without_cad(self) -> None:
        import asyncio
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import Mock
        from mcp.server.fastmcp import FastMCP
        from kompas_mcp.model_image import export_model_png
        from kompas_mcp.session_tools import register_session_tools

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = Mock()
            runner.call.return_value = {"ok": True}
            adapter = SimpleNamespace(runner=runner, _export_dir=lambda: root)
            mcp = FastMCP("model-png-contract")
            register_session_tools(mcp, adapter)
            tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
            schema = tools["export_model_png"].inputSchema
            self.assertEqual(schema["required"], ["document_id"])
            self.assertEqual(schema["properties"]["view"]["enum"], [
                "current", "front", "rear", "top", "bottom", "left", "right", "isometric",
            ])
            self.assertEqual(schema["properties"]["view"]["default"], "current")
            self.assertEqual(schema["properties"]["resolution_dpi"]["default"], 150)
            self.assertIs(schema["properties"]["fit"]["default"], True)
            runner.call.assert_not_called()
            self.assertEqual(export_model_png(adapter, "@reference:123"), {"ok": True})
            action, first = runner.call.call_args.args
            self.assertEqual(action, "export_model_png")
            self.assertEqual({k: v for k, v in first.items() if k != "output_path"}, {
                "document_id": "@reference:123", "view": "current", "resolution_dpi": 150, "fit": True,
            })
            self.assertEqual(Path(first["output_path"]).parent, root.resolve())
            export_model_png(adapter, "@reference:123")
            self.assertNotEqual(first["output_path"], runner.call.call_args.args[1]["output_path"])
            explicit = str(root / "rear.PNG")
            export_model_png(adapter, "@reference:123", explicit, "rear", 600, False)
            self.assertEqual(runner.call.call_args.args[1], {
                "document_id": "@reference:123", "output_path": explicit,
                "view": "rear", "resolution_dpi": 600, "fit": False,
            })
            existing = root / "existing.png"
            existing.write_bytes(b"user artifact")
            runner.reset_mock()
            for values in ({"document_id": ""}, {"document_id": "@document:0"}, {"view": "rotate"}, {"view": []},
                           {"resolution_dpi": True}, {"resolution_dpi": 71},
                           {"resolution_dpi": 601}, {"resolution_dpi": 150.0}, {"fit": 1},
                           {"output_path": "relative.png"}, {"output_path": str(root / "x.jpg")},
                           {"output_path": str(root / "missing" / "x.png")},
                           {"output_path": str(existing)}):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    export_model_png(adapter, **{"document_id": "@reference:123", **values})
            runner.call.assert_not_called()
            self.assertEqual(existing.read_bytes(), b"user artifact")

    def test_model_png_native_export_restores_state_and_reports_failures(self) -> None:
        import struct
        import sys
        import tempfile
        import zlib
        from types import ModuleType, SimpleNamespace
        from unittest.mock import Mock, patch
        from kompas_mcp.assets.bridge import model_image_runtime as runtime

        # One SDK-shaped scenario; no generated COM classes or live attachment.
        app = SimpleNamespace(ActiveDocument=None)
        manager = SimpleNamespace(Matrix3D=tuple(float(i) for i in range(16)), Scale=2.5)
        original_matrix, original_scale = manager.Matrix3D, manager.Scale
        def restore(matrix, scale):
            manager.Matrix3D, manager.Scale = matrix, scale
            return True
        manager.SetMatrix3D = Mock(side_effect=restore)
        class Document(SimpleNamespace):
            # API7 typed document has Active, not an Activate method.
            @property
            def Active(self):
                return app.ActiveDocument is self

            @Active.setter
            def Active(self, value):
                if value:
                    app.ActiveDocument = self

        previous = Document(runtime_id="@reference:old")
        target = Document(runtime_id="@reference:target", Changed=False,
                                  ViewProjectionManager=manager)
        app.ActiveDocument = previous
        front = SimpleNamespace(GetViewProjectonType=lambda: 1, IsCurrent=lambda: False)
        # Rear intentionally occupies index zero, proving type != index.
        rear = SimpleNamespace(GetViewProjectonType=lambda: 2, IsCurrent=lambda: True)
        def select_rear():
            manager.Matrix3D = tuple(reversed(original_matrix))
            target.Changed = True
            return 1
        rear.SetCurrent = Mock(side_effect=select_rear)
        collection = SimpleNamespace(GetCount=lambda: 2, GetByIndex=lambda i: [rear, front][i])
        params = SimpleNamespace(Init=Mock(return_value=1))
        def fit(code):
            self.assertEqual(code, 2)
            manager.Scale = 7.0
            return 1
        legacy = SimpleNamespace(GetPart=Mock(), GetViewProjectionCollection=lambda: collection,
                                 ZoomPrevNextOrAll=Mock(side_effect=fit),
                                 RasterFormatParam=lambda: params)
        ihdr = struct.pack(">IIBBBBB", 800, 600, 8, 2, 0, 0, 0)
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        png_header = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")
        def save(path, raster_params):
            self.assertIs(raster_params, params)
            self.assertIs(app.ActiveDocument, target)
            self.assertEqual(path, expected_output_path)
            Path(path).write_bytes(png_header)
            return 1
        legacy.SaveAsToRasterFormat = Mock(side_effect=save)
        bridge = SimpleNamespace(make_app=Mock(return_value=app),
                                 resolve_document_strict=Mock(return_value=target),
                                 describe_document=lambda doc, app: {"runtime_id": doc.runtime_id},
                                 _APP5=SimpleNamespace(ActiveDocument3D=lambda: legacy,
                                                       ksRefreshActiveWindow=Mock()))
        com = ModuleType("win32com.client")
        com.CastTo = Mock(side_effect=lambda doc, interface: doc)
        com.VARIANT = Mock(side_effect=lambda kind, values: values)
        win32 = ModuleType("win32com")
        win32.client = com
        pythoncom = ModuleType("pythoncom")
        pythoncom.VT_ARRAY, pythoncom.VT_R8 = 8192, 5
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {
            "win32com": win32, "win32com.client": com, "pythoncom": pythoncom,
        }):
            path = Path(directory) / "model.png"
            expected_output_path = str(path)
            payload = {"document_id": target.runtime_id, "output_path": str(path),
                       "view": "rear", "resolution_dpi": 150, "fit": True}
            with patch("tempfile.TemporaryDirectory", side_effect=AssertionError("No native staging directory")), \
                    patch("os.link", side_effect=AssertionError("No hardlink publication")):
                result = runtime.handle("export_model_png", payload, bridge)
            self.assertTrue(result["ok"], result)
            legacy.SaveAsToRasterFormat.assert_called_once_with(str(path), params)
            self.assertEqual(set(Path(directory).iterdir()), {path})
            self.assertEqual(path.read_bytes(), png_header)
            self.assertEqual(bridge._APP5.ksRefreshActiveWindow.call_count, 2)
            self.assertEqual(result["projection_type"], 2)
            self.assertEqual(result["restore_fields"], ["Matrix3D", "Scale"])
            self.assertTrue(result["view_restored"] and result["activation_restored"])
            self.assertTrue(result["no_geometry_operations"])
            self.assertFalse(result["screen_pan_verified"])
            self.assertFalse(result["changed_before"])
            self.assertTrue(result["changed_after"])  # Dirty flag is not overwritten.
            self.assertEqual((manager.Matrix3D, manager.Scale), (original_matrix, original_scale))
            self.assertIs(app.ActiveDocument, previous)
            self.assertEqual((result["artifact"]["width"], result["artifact"]["height"]), (800, 600))
            self.assertEqual(result["artifact"]["bytes"], len(png_header))
            self.assertEqual((params.format, params.colorBPP, params.extResolution, params.extScale),
                             (3, 24, 150, 1.0))
            com.VARIANT.assert_called_with(8197, original_matrix)
            com.CastTo.assert_any_call(target, "IKompasDocument3D1")
            com.CastTo.assert_any_call(target, "IKompasDocument")
            com.CastTo.assert_called_with(previous, "IKompasDocument")
            bridge.make_app.reset_mock()
            legacy.SaveAsToRasterFormat.reset_mock()
            bridge._APP5.ksRefreshActiveWindow.reset_mock()
            with self.assertRaises(ValueError):
                runtime.handle("export_model_png", payload, bridge)
            bridge.make_app.assert_not_called()
            legacy.SaveAsToRasterFormat.assert_not_called()
            bridge._APP5.ksRefreshActiveWindow.assert_not_called()
            self.assertEqual(path.read_bytes(), png_header)

            failed_path = Path(directory) / "failed.png"
            expected_output_path = str(failed_path)
            legacy.SaveAsToRasterFormat.side_effect = RuntimeError("fixture export failure")
            result = runtime.handle("export_model_png", {**payload, "output_path": str(failed_path)}, bridge)
            self.assertFalse(result["ok"])
            self.assertIn("fixture export failure", result["error"])
            self.assertTrue(result["view_restored"] and result["activation_restored"])
            self.assertFalse(failed_path.exists())
            self.assertEqual((manager.Matrix3D, manager.Scale), (original_matrix, original_scale))
            self.assertIs(app.ActiveDocument, previous)
            self.assertEqual(bridge._APP5.ksRefreshActiveWindow.call_count, 2)

            def invalid_png(path, raster_params):
                Path(path).write_bytes(b"not a PNG")
                return 1
            legacy.SaveAsToRasterFormat.side_effect = invalid_png
            result = runtime.handle("export_model_png", {**payload, "output_path": str(failed_path)}, bridge)
            self.assertFalse(result["ok"])
            self.assertIn("PNG IHDR header", result["error"])
            self.assertTrue(result["view_restored"] and result["activation_restored"])
            self.assertEqual(failed_path.read_bytes(), b"not a PNG")  # Direct-export failure leaves evidence.
            failed_path.unlink()

            legacy.SaveAsToRasterFormat.side_effect = save
            manager.SetMatrix3D.side_effect = lambda matrix, scale: True  # Lying success; verify readback.
            result = runtime.handle("export_model_png", {**payload, "output_path": str(failed_path)}, bridge)
            self.assertFalse(result["ok"])
            self.assertFalse(result["view_restored"])
            self.assertTrue(result["activation_restored"])
            self.assertIn("restoration readback mismatch", result["error"])
            self.assertIn("artifact", result)  # Partial artifact remains discoverable.

    def test_construction_chain_fresh_fastmcp_schema_discovery_and_no_cad(self) -> None:
        import os
        import subprocess
        import sys
        # Import canonical registration in an isolated process: cached server
        # objects or direct decorated-function calls cannot prove MCP validation.
        code = '''
import asyncio
from unittest.mock import patch
from kompas_mcp.bridge_runner import BridgeRunner
with patch.object(BridgeRunner, "call", side_effect=AssertionError("CAD forbidden during import")):
    from geomwright.kompas import server
from kompas_mcp.tool_catalog import get_mcp_tool_catalog

async def check():
    from kompas_mcp.construction_chains import ConstructionChain, get_construction_chain_contract
    with patch.object(server.adapter.runner, "call", side_effect=AssertionError("CAD forbidden")) as cad:
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}
        catalog = {name for category in get_mcp_tool_catalog()["categories"] for name in category["tools"]}
        assert set(tools) == catalog
        names = {"get_construction_chain_contract", "run_construction_chain", "get_cad_module_contract", "run_cad_module"}
        assert names <= set(tools)
        schema = tools["run_construction_chain"].inputSchema
        assert schema["required"] == ["action"]
        assert schema["properties"]["action"]["enum"] == get_construction_chain_contract()["actions"]
        assert "ConstructionChain" in schema["$defs"]
        expected = ConstructionChain.model_json_schema(by_alias=True)
        assert schema["$defs"]["ConstructionChain"] == {k: v for k, v in expected.items() if k != "$defs"}
        for key, definition in expected["$defs"].items():
            assert schema["$defs"][key] == definition, key
        await server.mcp.call_tool("get_construction_chain_contract", {})
        await server.mcp.call_tool("get_cad_module_contract", {"module_id": "stepped_shaft"})
        recipe = {"steps": [{"id": "base", "module": "stepped_shaft", "basis": "own", "material": "create",
                            "parameters": {"steps": [{"length": 20, "diameter": 30}]}}]}
        result = await server.mcp.call_tool("run_construction_chain", {"action": "plan", "chain": recipe})
        import json
        # FastMCP returns structured content alongside text when the tool has
        # a dict return annotation; inspect that actual transport response.
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert "preview" not in data["steps"][0]
        assert data["recipe"]["steps"][0]["id"] == "base"
        section_chain = {"steps": [{"id": "flat", "module": "external_flat_step", "basis": "own",
            "material": "create", "parameters": {"diameter": 60, "length": 12, "flat_depth": 4}},
            {"id": "holes", "module": "bolt_circle_holes", "basis": "input", "material": "remove", "target": "flat",
             "parameters": {"hole_diameter": 5, "depth": 12, "bolt_circle_diameter": 40, "count": 4},
             "placement": {"reference": {"step": "flat", "anchor": "start"}}}]}
        result = await server.mcp.call_tool("run_construction_chain", {"action": "plan", "chain": section_chain})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert len(data["steps"][1]["section"]["hole_centers_yz_mm"]) == 4
        assert "preview" not in data["steps"][1]
        assert data["recipe"]["steps"][0]["id"] == "flat"
        assert len(json.dumps(data)) < 24000
        polygon = {"steps": [{"id": "poly", "module": "external_polygonal_step", "basis": "own",
            "material": "create", "parameters": {"diameter": 30, "length": 10, "side_count": 6}}]}
        result = await server.mcp.call_tool("run_construction_chain", {"action": "plan", "chain": polygon})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert data["steps"][0]["section"]["carrier_role"] == "inscribed_core"
        assert "preview" not in data["steps"][0]
        spline = {"steps": [{"id": "spline", "module": "straight_spline", "basis": "own",
            "material": "create", "parameters": {"designation": "8x36x40", "series": "light"}}]}
        result = await server.mcp.call_tool("run_construction_chain", {"action": "plan", "chain": spline})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert data["steps"][0]["section"]["axial_interval_mm"] == [-30, 0]
        assert "family_plan" not in data["steps"][0]
        assert len(json.dumps(data)) < 24000
        input_spline = {"steps":[{"id":"base","module":"stepped_shaft","basis":"own","material":"create",
            "parameters":{"steps":[{"length":50,"diameter":40}]}},
            {"id":"spline","module":"straight_spline","basis":"input","material":"remove","target":"base",
             "placement":{"reference":{"step":"base","anchor":"start"},"offset_mm":10},
             "parameters":{"designation":"8x36x40","series":"light","length_mm":20,"include_tip_chamfer":False}}]}
        result = await server.mcp.call_tool("run_construction_chain", {"action":"plan","chain":input_spline})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert data["steps"][-1]["section"]["axial_interval_mm"] == [10,30]
        assert "spline_application" not in data["steps"][-1] and "spline_prefix_plan" not in data
        assert len(json.dumps(data)) < 24000
        assert {"basis":"input","material":"remove"} in get_construction_chain_contract()["modules"]["straight_spline"]["supported_modes"]
        input_hub = {"steps":[{"id":"stock","module":"stepped_shaft","basis":"own","material":"create",
            "parameters":{"steps":[{"diameter":55,"length":20}]}},
            {"id":"bore","module":"internal_cylindrical_step","basis":"input","material":"remove","target":"stock",
             "placement":{"reference":{"step":"stock","anchor":"start"}},"parameters":{"steps":[{"diameter":36,"length":20}]}},
            {"id":"spline","module":"straight_spline","basis":"input","material":"remove","target":"bore",
             "placement":{"reference":{"step":"bore","anchor":"start"}},
             "parameters":{"body":"hub","series":"light","designation":"8x36x40","length_mm":20,"include_tip_chamfer":False}}]}
        result = await server.mcp.call_tool("run_construction_chain", {"action":"plan","chain":input_hub})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert data["steps"][-1]["spline_guard"]["scope"] == "through_internal_spline_cylinder_positive_x"
        assert data["recipe"]["steps"][-1]["parameters"]["hub_outside_diameter_mm"] == 55
        assert "spline_application" not in data["steps"][-1] and "spline_prefix_plan" not in data
        assert len(json.dumps(data)) < 24000
        assert get_construction_chain_contract()["modules"]["straight_spline"]["input_application"]["hub"]["exit_modes"] == ["through","blind"]
        import copy
        blind = copy.deepcopy(input_hub)
        blind["steps"][0]["parameters"]["steps"][0]["length"] = 30
        blind["steps"][1]["parameters"]["steps"][0]["length"] = 25
        blind["steps"][-1]["parameters"]["exit_mode"] = "blind"
        result = await server.mcp.call_tool("run_construction_chain", {"action":"plan","chain":blind})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert data["steps"][-1]["spline_guard"]["scope"] == "blind_internal_spline_cylinder_positive_x"
        assert data["steps"][-1]["spline_guard"]["smooth_tail_span_mm"] == [20,25]
        assert data["steps"][-1]["spline_guard"]["bottom_stock_mm"] == 5
        assert data["recipe"]["steps"][-1]["parameters"]["hub_outside_diameter_mm"] == 55
        assert "spline_application" not in data["steps"][-1] and "spline_prefix_plan" not in data
        assert len(json.dumps(data)) < 24000
        thread = {"steps": [{"id": "base", "module": "stepped_shaft", "basis": "own", "material": "create",
            "parameters": {"steps": [{"length": 20, "diameter": 20}]}},
            {"id": "thread", "module": "external_helical_thread", "basis": "input", "material": "remove",
             "target": "base", "placement": {"reference": {"step": "base", "anchor": "start"}},
             "parameters": {"diameter": 20, "pitch": 2.5, "length": 20, "direction": "left"}}]}
        result = await server.mcp.call_tool("run_construction_chain", {"action": "plan", "chain": thread})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert data["expected_total_volume_cm3"] is None
        assert data["steps"][-1]["expected_delta_cm3"] is None
        assert "preview" not in data["steps"][-1] and "thread_prefix_plan" not in data
        assert get_construction_chain_contract()["modules"]["external_helical_thread"]["terminal_only"]
        assert len(json.dumps(data)) < 24000
        blind = {"steps": [thread["steps"][0], {**thread["steps"][1], "parameters": {
            **thread["steps"][1]["parameters"], "length": 18, "entry_mode": "through", "exit_mode": "blind"}}]}
        result = await server.mcp.call_tool("run_construction_chain", {"action": "plan", "chain": blind})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert data["steps"][-1]["section"]["axial_interval_mm"] == [0, 18]
        assert data["steps"][-1]["thread_guard"]["end_plan"]["terminal_section_projection_mm"] == [15.8125, 18]
        assert data["recipe"]["steps"][-1]["parameters"]["exit_mode"] == "blind"
        assert data["expected_total_volume_cm3"] is None and "preview" not in data["steps"][-1]
        assert len(json.dumps(data)) < 24000
        through = {"steps": [thread["steps"][0], {**thread["steps"][1], "parameters": {
            **thread["steps"][1]["parameters"], "entry_mode": "through", "exit_mode": "through"}}]}
        result = await server.mcp.call_tool("run_construction_chain", {"action": "plan", "chain": through})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert data["steps"][-1]["thread_guard"]["end_plan"]["spiral_length_mm"] == 24.34375
        assert data["steps"][-1]["thread_guard"]["end_plan"]["terminal_section_projection_mm"] == [20, 22.1875]
        assert "preview" not in data["steps"][-1] and len(json.dumps(data)) < 24000
        internal = {"steps": [{**thread["steps"][0], "parameters": {"steps": [{"diameter": 36, "length": 20}]}},
            {"id": "bore", "module": "internal_cylindrical_step", "basis": "input", "material": "remove",
             "target": "base", "placement": {"reference": {"step": "base", "anchor": "start"}},
             "parameters": {"steps": [{"diameter": 17.29367061317363, "length": 20}]}},
            {**thread["steps"][1], "module": "internal_helical_thread", "target": "bore",
             "placement": {"reference": {"step": "bore", "anchor": "start"}}}]}
        result = await server.mcp.call_tool("run_construction_chain", {"action": "plan", "chain": internal})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert data["recipe"]["steps"][-1]["parameters"]["method_version"] == 1
        assert data["steps"][-1]["thread_guard"]["bore_radius_mm"] == 17.29367061317363/2
        assert data["expected_total_volume_cm3"] is None and "preview" not in data["steps"][-1]
        assert len(json.dumps(data)) < 24000
        internal["steps"][0]["parameters"]["steps"][0]["length"] = 24
        internal["steps"][-1]["parameters"] = {"diameter":20,"pitch":2.5,"length":18,"exit_mode":"blind"}
        result = await server.mcp.call_tool("run_construction_chain", {"action":"plan","chain":internal})
        data = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        assert data["steps"][-1]["thread_guard"]["end_plan"]["bottom_stock_thickness_mm"] == 4
        assert data["steps"][-1]["thread_guard"]["working_span_mm"] == [0,18]
        assert "preview" not in data["steps"][-1] and len(json.dumps(data)) < 24000
        for arguments in ({"action": "plan"}, {"action": "unknown"},
                          {"action": "plan", "chain": {"steps": [thread["steps"][0], {**thread["steps"][1], "parameters": {**thread["steps"][1]["parameters"], "length": 19}}]}},
                          {"action": "plan", "chain": {"steps": [{**spline["steps"][0], "parameters": {**spline["steps"][0]["parameters"], "body": "hub"}}]}},
                          {"action": "plan", "chain": {"steps": [{**polygon["steps"][0], "parameters": {**polygon["steps"][0]["parameters"], "axial_direction": "forward"}}]}},
                          {"action": "plan", "chain": {"steps": [{**recipe["steps"][0], "placement": {"reference": {"step": "missing", "anchor": "end"}}}]}}):
            try:
                await server.mcp.call_tool("run_construction_chain", arguments)
            except Exception:
                pass
            else:
                raise AssertionError("Invalid chain accepted")
        await server.mcp.call_tool("run_cad_module", {"request": {"module_id": "stepped_shaft", "action": "plan",
                    "parameters": {"steps": [{"length": 20, "diameter": 30}]}}})
        cad.assert_not_called()
asyncio.run(check())
'''
        environment = {**os.environ, "GEOMWRIGHT_ENABLE_RESEARCH_TOOLS": "0", "KOMPAS_MCP_ENABLE_RESEARCH_TOOLS": "0"}
        result = subprocess.run([sys.executable, "-c", code], cwd=SOURCE_ROOT.parent,
                                env=environment, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])

    def test_unknown_session_recovery_remains_host_only_and_requires_confirmation(self) -> None:
        import inspect
        import tempfile
        from unittest.mock import patch
        from geomwright.kompas import server
        from kompas_mcp.bridge_runner import BridgeRunner

        with tempfile.TemporaryDirectory() as directory:
            runner = BridgeRunner(session_guard_dir=directory)
            status_fn = server.mcp._tool_manager._tools["get_cad_session_guard"].fn
            recover_fn = server.mcp._tool_manager._tools["recover_cad_session"].fn
            self.assertIs(inspect.signature(recover_fn).parameters["confirm_idle"].default, False)
            self.assertIn("settled_failure", recover_fn.__doc__)
            with patch.object(server.adapter, "runner", runner), patch.object(runner, "call") as com:
                self.assertFalse(status_fn()["blocked"])
                with runner.session_guard.operation("fixture", {}):
                    runner.session_guard.quarantine("fixture only; no CAD")
                status = status_fn()
                with self.assertRaises(ValueError):
                    recover_fn(status["token"], False, "not confirmed")
                result = recover_fn(status["token"], True, "fake fixture idle")
                self.assertFalse(result["rollback_performed"])
                com.assert_not_called()

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

    def test_module_discovery_uses_family_schema_and_declares_create_only(self) -> None:
        from kompas_mcp.cad_modules import CadModuleRequest, get_cad_module_contract
        from kompas_mcp.gears import (
            BevelGearCreateRequest, BevelGearRequest,
            InternalGearCreateRequest, InternalGearRequest,
            SpurGearCreateRequest, SpurGearRequest,
        )
        from pydantic import ValidationError
        from kompas_mcp.transmission_tools import ChainSprocketCreateRequest, ChainSprocketPreviewRequest

        listed = get_cad_module_contract()
        self.assertEqual([item["module_id"] for item in listed["modules"]],
                          ["gear_spur", "gear_internal", "gear_bevel", "chain_sprocket", "cam", "silent_chain_sprocket", "compression_spring", "extension_spring", "torsion_spring", "disc_spring", "diaphragm_spring", "stepped_shaft", "external_conical_step", "external_polygonal_step", "external_flat_step",
                           "v_belt", "poly_v", "flat_belt", "timing_trapezoidal", "timing_curvilinear"])
        for module_id, request_type, create_type in (
            ("gear_spur", SpurGearRequest, SpurGearCreateRequest),
            ("gear_internal", InternalGearRequest, InternalGearCreateRequest),
            ("gear_bevel", BevelGearRequest, BevelGearCreateRequest),
            ("chain_sprocket", ChainSprocketPreviewRequest, ChainSprocketCreateRequest),
        ):
            with self.subTest(module_id=module_id):
                contract = get_cad_module_contract(module_id)
                self.assertEqual(contract["parameter_schema"], request_type.model_json_schema())
                self.assertEqual(contract["defaults"], request_type().model_dump(exclude_none=True))
                self.assertEqual(contract["default_name"], create_type.model_fields["name"].default)
                self.assertFalse(contract["capabilities"]["update_in_place"])
                self.assertFalse(contract["capabilities"]["apply_to_existing_body"])
                self.assertEqual(contract["units"]["body_volume"], "cm3")
                request_type.model_validate(contract["examples"]["create"]["parameters"])
                CadModuleRequest.model_validate(contract["examples"]["create"])
        self.assertEqual(get_cad_module_contract("gear_bevel")["frame"]["face_width_direction"],
                         "pitch_cone_generator")
        self.assertEqual(get_cad_module_contract("missing")["error"]["code"], "UNKNOWN_MODULE")
        stable_tools = [tool for category in get_mcp_tool_catalog(stability="stable")["categories"]
                        for tool in category["tools"]]
        self.assertNotIn("run_cad_module", stable_tools)
        with self.assertRaises(ValidationError):
            CadModuleRequest(module_id="gear_spur", action="inspect")
        with self.assertRaises(ValidationError):
            CadModuleRequest(module_id="gear_spur", action="create", document_id="@document:0")

    def test_cam_module_typed_inputs_compact_plan_and_saved_recipe(self) -> None:
        import json
        from unittest.mock import Mock, patch
        from kompas_mcp.cad_modules import CadModuleRequest, get_cad_module_contract, run_cad_module
        from kompas_mcp.cams.module_contract import CamModuleParameters
        from kompas_mcp.cad_module_bindings import cam_plan
        contract = get_cad_module_contract("cam")
        self.assertEqual(contract["parameter_schema"], CamModuleParameters.model_json_schema())
        self.assertEqual(contract["selection_tools"], [])
        from kompas_mcp.cams.lift import LAW_NAMES
        self.assertEqual(set(contract["parameter_schema"]["$defs"]["CamMotionRequest"]["properties"]["law"]["enum"]), set(LAW_NAMES))
        parameters = contract["examples"]["plan"]["parameters"]
        adapter = Mock()
        planned = run_cad_module(CadModuleRequest(module_id="cam", action="plan", parameters=parameters), adapter)
        self.assertTrue(planned["ok"])
        self.assertNotIn("curve", planned["data"])
        self.assertLess(len(json.dumps(planned)), 20000)
        preview = run_cad_module(CadModuleRequest(module_id="cam", action="preview", parameters=parameters), adapter)
        self.assertTrue(preview["ok"])
        self.assertNotIn("motion_chart", preview["data"])
        invalid = run_cad_module(CadModuleRequest(module_id="cam", action="create", confirm_write=True,
            parameters={"request": {"mechanism": "rocker", "contact": "flat"}}), adapter)
        self.assertEqual(invalid["error"]["code"], "INVALID_PARAMETERS")
        unknown = run_cad_module(CadModuleRequest(module_id="cam", action="plan",
            parameters={"request": {"bas_radius": 30}}), adapter)
        self.assertEqual(unknown["error"]["code"], "INVALID_PARAMETERS")
        self.assertEqual(adapter.mock_calls, [])
        strict_refusal = run_cad_module(CadModuleRequest(module_id="cam", action="create", confirm_write=True,
            parameters={"request": {"min_curvature_radius": 1000}}), adapter)
        self.assertEqual(strict_refusal["error"]["code"], "INVALID_PARAMETERS")
        self.assertFalse(strict_refusal["executed"])
        self.assertEqual(adapter.mock_calls, [])
        plan = cam_plan(planned["parameters"], name="Geomwright cam")
        block = {"module": "camshaft_lobe", "id": "cam:1", "version": 2,
            "recipe": plan["recipe"], "verified": True, "owned_references": [1, 2],
            "recreatable": False, "status": "verified"}  # No Studio form is required for MCP recreation.
        adapter.inspect_cam.return_value = {"recognized": True, "block": block}
        inspected = run_cad_module(CadModuleRequest(module_id="cam", action="inspect", document_id="@document:1"), adapter)
        self.assertTrue(inspected["ok"] and inspected["data"]["recreatable"])
        self.assertFalse(inspected["verified"])
        self.assertTrue(inspected["verification"]["stored_verified"])
        self.assertNotIn("law_continuity_order", inspected["parameters"]["request"])
        created_native = {"ok": True, "executed": True, "document": {"runtime_id": "@document:1"},
            "exports": {"sketch_ref": 1, "feature_ref": 2},
            "body": {"bounds": [-12, -30, -30, 0, 30, 36], "volume": 10},
            "verification": {"ok": True}}
        with patch("kompas_mcp.cad_module_bindings.execute_cam_plan", return_value=created_native) as execute:
            created = run_cad_module(CadModuleRequest(module_id="cam", action="create", parameters=parameters,
                confirm_write=True), adapter)
            self.assertTrue(created["verified"])
            self.assertEqual(created["data"]["owned_references"], [1, 2])
            self.assertIn("bounds_mm", created["data"]["body"])
            self.assertEqual(execute.call_args.args[1]["stage"], "cam_plan")
            adapter.inspect_cam.return_value = {"recognized": True, "block": {**block, "verified": False}}
            failed = run_cad_module(CadModuleRequest(module_id="cam", action="create", parameters=parameters,
                confirm_write=True), adapter)
            self.assertFalse(failed["ok"])
            self.assertEqual(failed["partial_result"]["document"]["runtime_id"], "@document:1")
        adapter.inspect_cam.return_value = {"recognized": True, "block": {**block, "version": 1, "recipe": None, "verified": False}}
        legacy = run_cad_module(CadModuleRequest(module_id="cam", action="inspect", document_id="@document:1"), adapter)
        self.assertFalse(legacy["data"]["recreatable"])
        self.assertIsNone(legacy["parameters"])
        adapter.inspect_cam.return_value = {"recognized": True, "block": {**block,
            "recipe": {**plan["recipe"], "request": {"law": "polydyne_345"}}}}
        damaged = run_cad_module(CadModuleRequest(module_id="cam", action="inspect", document_id="@document:1"), adapter)
        self.assertIsNone(damaged["parameters"])
        self.assertIn("Incomplete", damaged["data"]["recipe_error"])
        adapter.inspect_cam.return_value = {"recognized": True, "block": {**block,
            "recipe": {**plan["recipe"], "request": {**plan["recipe"]["request"], "tappet_diameter": None}}}}
        unspecified_face = run_cad_module(CadModuleRequest(module_id="cam", action="inspect", document_id="@document:1"), adapter)
        self.assertIsNone(CamModuleParameters.model_validate(unspecified_face["parameters"]).request.tappet_diameter)

    def test_silent_module_explicit_inputs_compact_sources_and_recipe_readback(self) -> None:
        import json
        from unittest.mock import Mock
        from kompas_mcp.bridge_runner import BridgeError
        from kompas_mcp.cad_modules import CadModuleRequest, get_cad_module_contract, run_cad_module
        from kompas_mcp.transmissions.silent_geometry import SilentChainSelectionRequest
        contract = get_cad_module_contract("silent_chain_sprocket")
        self.assertEqual(contract["parameter_schema"], SilentChainSelectionRequest.model_json_schema())
        self.assertNotIn("designation", contract["defaults"])
        self.assertNotIn("physical_tooth_count", contract["defaults"])
        self.assertEqual(contract["selection_tools"], ["list_silent_chain_profiles"])
        adapter = Mock()
        parameters = contract["examples"]["plan"]["parameters"]
        planned = run_cad_module(CadModuleRequest(module_id="silent_chain_sprocket", action="plan", parameters=parameters), adapter)
        self.assertTrue(planned["ok"])
        self.assertEqual(planned["data"]["accuracy"]["other_runs"], "analytic_piece_cubic_nurbs")
        self.assertNotIn("drawing", planned["data"]["axial"])
        self.assertNotIn("construction_spec", planned["data"])
        self.assertLess(len(json.dumps(planned)), 20000)
        incomplete = {"standard": "gost_13552_81_13576_81", "family": "type_2",
            "designation": "PZ-2-25.4-101-57", "physical_tooth_count": 23, "accuracy_class": 1}
        preview = run_cad_module(CadModuleRequest(module_id="silent_chain_sprocket", action="preview", parameters=incomplete), adapter)
        self.assertTrue(preview["ok"])
        self.assertTrue(preview["data"]["summary"]["completion"]["missing_fields"])
        for action in ("plan", "create"):
            failed = run_cad_module(CadModuleRequest(module_id="silent_chain_sprocket", action=action,
                parameters=incomplete, confirm_write=action == "create"), adapter)
            self.assertEqual(failed["error"]["code"], "INPUT_REQUIRED")
            self.assertFalse(failed["executed"])
            self.assertTrue(failed["data"]["completion"]["missing_fields"])
        self.assertEqual(adapter.mock_calls, [])
        block = {"module": "silent_chain_sprocket", "profile": planned["parameters"],
            "identity_references": [1, 2, 3, 4, 5], "owned_references": list(range(1000)),
            "version": 1, "id": "silent:1"}
        adapter.create_silent_chain_sprocket.return_value = {"ok": True, "success": True, "executed": True,
            "document": {"runtime_id": "@document:1"}, "block": block, "verification": {"ok": True,
            "all_pattern_instances_remove_expected_material": True, "pattern_volume_relative_error": 0}}
        created = run_cad_module(CadModuleRequest(module_id="silent_chain_sprocket", action="create",
            parameters=parameters, confirm_write=True), adapter)
        self.assertTrue(created["verified"])
        self.assertEqual(created["data"]["owned_references"], [1, 2, 3, 4, 5])
        self.assertTrue(created["verification"]["all_pattern_instances_remove_expected_material"])
        self.assertEqual(adapter.create_silent_chain_sprocket.call_args.args[0]["stage"], "silent_chain_cad_plan")
        adapter.inspect_silent_chain_sprocket.return_value = {"recognized": True, "block": block}
        inspected = run_cad_module(CadModuleRequest(module_id="silent_chain_sprocket", action="inspect", document_id="@document:1"), adapter)
        self.assertEqual(inspected["parameters"], planned["parameters"])
        self.assertFalse(inspected["verified"])
        self.assertIsNone(inspected["verification"]["stored_verified"])
        self.assertTrue(inspected["data"]["source_summary"]["warnings"])
        adapter.inspect_silent_chain_sprocket.return_value = {"recognized": True, "block": {**block, "profile": incomplete}}
        damaged = run_cad_module(CadModuleRequest(module_id="silent_chain_sprocket", action="inspect", document_id="@document:1"), adapter)
        self.assertIsNone(damaged["parameters"])
        error = BridgeError("Native verification failed")
        error.partial_result = {"document": {"runtime_id": "@document:2"}}
        adapter.create_silent_chain_sprocket.side_effect = error
        interrupted = run_cad_module(CadModuleRequest(module_id="silent_chain_sprocket", action="create",
            parameters=parameters, confirm_write=True), adapter)
        self.assertEqual(interrupted["partial_result"]["document"]["runtime_id"], "@document:2")
        self.assertIsNone(interrupted["executed"])
        self.assertFalse(interrupted["error"]["retryable"])

    def test_pulley_modules_share_existing_plans_and_preserve_complete_recipes(self) -> None:
        import json
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest, get_cad_module_contract, run_cad_module
        from kompas_mcp.cad_pulley_bindings import PULLEY_MODELS, PULLEY_EXAMPLES, pulley_plan
        for family, parameters in PULLEY_EXAMPLES.items():
            with self.subTest(family=family):
                contract = get_cad_module_contract(family)
                self.assertEqual(contract["parameter_schema"], PULLEY_MODELS[family].model_json_schema())
                adapter = Mock()
                request = CadModuleRequest(module_id=family, action="plan", parameters=parameters)
                planned = run_cad_module(request, adapter)
                self.assertTrue(planned["ok"])
                self.assertNotIn("workflow", planned["data"])
                self.assertLess(len(json.dumps(planned)), 20000)
                preview = run_cad_module(request.model_copy(update={"action": "preview"}), adapter)
                self.assertTrue(preview["ok"])
                self.assertEqual(adapter.mock_calls, [])
                source = pulley_plan(planned["parameters"], name="Geomwright pulley", family=family)
                profile = source["profile_request"]
                inspection = {"recognized": True, "family": family, "block_id": "pulley:1",
                    "identity_references": [1, 2, 3, 4], "profile_request": profile,
                    "module_recipe": source["shared_recipe"], "version": 1}
                adapter.inspect_managed_pulley.return_value = inspection
                width = profile["face_width"] if family.startswith("timing_") else source["profile_preview"]["derived"]["face_width"]
                adapter.list_model_bodies.return_value = {"pagination": {"total": 1},
                    "items": [{"bounds_mm": [-width if family.startswith("timing_") else 0, -50, -50,
                        0 if family.startswith("timing_") else width, 50, 50]}]}
                adapter.create_managed_pulley.return_value = {"ok": True, "executed": True,
                    "document": {"runtime_id": "@document:1"}, "body": {"body_count": 1, "solid": True, "volume": 10},
                    "verification": {"ok": True}, "steps": [{"scenario": "circular_pattern",
                        "count": profile.get("tooth_count", 1), "source_volume_removed": .01,
                        "additional_volume_removed": .01*(profile.get("tooth_count", 1)-1)}]}
                created = run_cad_module(request.model_copy(update={"action": "create", "confirm_write": True}), adapter)
                self.assertTrue(created["verified"])
                self.assertIn("bounds_mm", created["data"]["body"])
                prepared = adapter.create_managed_pulley.call_args.kwargs["prepared_plan"]
                self.assertEqual(prepared["shared_recipe"]["parameters"], planned["parameters"])
                inspected = run_cad_module(CadModuleRequest(module_id=family, action="inspect", document_id="@document:1"), adapter)
                self.assertEqual(inspected["parameters"], planned["parameters"])
                self.assertFalse(inspected["verified"])
                self.assertIsNone(inspected["verification"]["stored_verified"])
                adapter.inspect_managed_pulley.return_value = {**inspection, "module_recipe": None}
                legacy = run_cad_module(CadModuleRequest(module_id=family, action="inspect", document_id="@document:1"), adapter)
                self.assertIsNone(legacy["parameters"])
                self.assertFalse(legacy["data"]["recreatable"])
                live_changed = dict(profile)
                size_key = "face_width" if "face_width" in profile else "datum_diameter" if "datum_diameter" in profile else "effective_diameter"
                live_changed[size_key] += 1
                adapter.inspect_managed_pulley.return_value = {**inspection, "profile_request": live_changed}
                stale = run_cad_module(CadModuleRequest(module_id=family, action="inspect", document_id="@document:1"), adapter)
                self.assertIsNone(stale["parameters"])
                self.assertIn("changed", stale["data"]["recipe_error"])
                adapter.inspect_managed_pulley.return_value = inspection
                adapter.list_model_bodies.return_value = {}
                failed = run_cad_module(request.model_copy(update={"action": "create", "confirm_write": True}), adapter)
                self.assertFalse(failed["ok"])
                self.assertEqual(failed["partial_result"]["document"]["runtime_id"], "@document:1")

    def test_compression_family_contract_delegates_legacy_planning_and_never_defaults_geometry(self) -> None:
        import json
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest, get_cad_module_contract, run_cad_module
        from kompas_mcp.cad_spring_bindings import CompressionSpringParameters, spring_plan
        contract = get_cad_module_contract("compression_spring")
        self.assertEqual(contract["parameter_schema"], CompressionSpringParameters.model_json_schema())
        self.assertEqual(contract["creation_policy"], "saved_unique_export_then_open")
        self.assertNotIn("wire_diameter", contract["defaults"])
        self.assertEqual(contract["defaults"]["end_pitch_gap"], .01)
        cases = [contract["examples"]["plan"]["parameters"],
            {"variant": "two_zone", "wire_diameter": 4, "mean_diameter": 30,
             "working_turns_1": 3, "pitch_1": 6, "working_turns_2": 2.5, "pitch_2": 10},
            {"variant": "conical", "wire_diameter": 4, "large_mean_diameter": 40,
             "small_mean_diameter": 20, "height": 48, "turns": 6}]
        adapter = Mock()
        for parameters in cases:
            with self.subTest(variant=parameters.get("variant")):
                request = CadModuleRequest(module_id="compression_spring", action="plan", parameters=parameters)
                result = run_cad_module(request, adapter)
                self.assertTrue(result["ok"])
                self.assertLess(len(json.dumps(result)), 15000)
                self.assertNotIn("segment_plan", result["data"])
                recipe = spring_plan(result["parameters"], name="Test spring")["recipe"]
                adapter.runner.call.return_value = {"recognized": True, "block": {"recipe": recipe,
                    "owned_references": [1, 2], "schema": "geomwright.compression", "version": 1}}
                inspected = run_cad_module(CadModuleRequest(module_id="compression_spring", action="inspect", document_id="@document:1"), adapter)
                self.assertEqual(inspected["parameters"], result["parameters"])
                self.assertFalse(inspected["verified"])
                self.assertIsNone(inspected["verification"]["stored_verified"])
                old_recipe = {**recipe, "parameters": {k: v for k, v in recipe["parameters"].items() if k != "end_pitch_gap"}}
                adapter.runner.call.return_value = {"recognized": True, "block": {"recipe": old_recipe,
                    "owned_references": [1, 2], "schema": "geomwright.compression", "version": 1}}
                old = run_cad_module(CadModuleRequest(module_id="compression_spring", action="inspect", document_id="@document:1"), adapter)
                self.assertEqual(old["parameters"]["end_pitch_gap"], 0)
                adapter.reset_mock()
        for parameters in ({}, {"wire_diameter": 4, "mean_diamter": 30},
                           {"wire_diameter": 4, "variant": "two_zone"},
                           {"wire_diameter": 4, "variant": "cylindrical", "small_mean_diameter": 20},
                           {"wire_diameter": 4, "mean_diameter": 30, "end_pitch_gap": -.01},
                           {"wire_diameter": 4, "mean_diameter": 30, "height": 48, "standard_length": 48},
                           {"wire_diameter": 4, "mean_diameter": 30, "height": 48, "turns": 6, "pitch": 9}):
            bad = run_cad_module(CadModuleRequest(module_id="compression_spring", action="create", parameters=parameters, confirm_write=True), adapter)
            self.assertFalse(bad["ok"])
            self.assertFalse(bad["executed"])
        self.assertEqual(adapter.mock_calls, [])
        from kompas_mcp.bridge_runner import BridgeError
        adapter._export_dir.return_value = Path("C:/unused-test-export")
        adapter._normalize_target_path_for_kompas.side_effect = str
        adapter.runner.call.side_effect = BridgeError("RuntimeError: create_part_from_scenario failed at base_rotation: missing curve | steps=[]")
        failed = run_cad_module(CadModuleRequest(module_id="compression_spring", action="create",
            parameters=cases[0], confirm_write=True), adapter)
        self.assertFalse(failed["ok"])
        self.assertIn("missing curve", failed["error"]["message"])
        self.assertNotIn("steps=[]", failed["error"]["message"])
        self.assertIn("compression-module-", failed["partial_result"]["output_path"])
        self.assertFalse(failed["error"]["retryable"])
        self.assertIsNone(failed["executed"])

    def test_extension_family_preserves_inputs_and_refuses_silent_gap_or_hook_substitution(self) -> None:
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest, run_cad_module, get_cad_module_contract
        from kompas_mcp.cad_extension_bindings import ExtensionSpringParameters, Hook, extension_plan
        contract = get_cad_module_contract("extension_spring")
        self.assertEqual(contract["parameter_schema"], ExtensionSpringParameters.model_json_schema())
        self.assertEqual(contract["creation_policy"], "saved_unique_export_then_open")
        adapter = Mock()
        for hook in Hook.__args__:
            with self.subTest(hook=hook):
                profile = {"wire_diameter": 2, "outer_diameter": 22, "turns": 6, "hook_type": hook}
                result = run_cad_module(CadModuleRequest(module_id="extension_spring", action="plan", parameters=profile), adapter)
                self.assertTrue(result["ok"])
                self.assertAlmostEqual(result["data"]["summary"]["pitch"], 2.01)
                self.assertAlmostEqual(result["data"]["summary"]["height"], 12.06)
                self.assertEqual(adapter.mock_calls, [])
                recipe = extension_plan(result["parameters"], name="Saved extension")["recipe"]
                adapter.runner.call.return_value = {"recognized": True, "block": {"recipe": recipe, "owned_references": [1, 2]}}
                inspected = run_cad_module(CadModuleRequest(module_id="extension_spring", action="inspect", document_id="@document:1"), adapter)
                self.assertEqual(inspected["parameters"], result["parameters"])
                self.assertTrue(inspected["data"]["recreatable"])
                self.assertFalse(inspected["verified"])
                recipe["parameters"].pop("turns")
                incomplete = run_cad_module(CadModuleRequest(module_id="extension_spring", action="inspect", document_id="@document:1"), adapter)
                self.assertIsNone(incomplete["parameters"])
                self.assertFalse(incomplete["data"]["recreatable"])
                adapter.reset_mock()
        for overrides in ({"gap": 0}, {"gap": .005}, {"hook_type": "unknown_hook"},
                          {"left_hook_type": "unknown_hook"}, {"hook_type": "u_hooks", "v_hook_height": 12},
                          {"hook_type": "v_hooks", "hook_clearance": 1}, {"outer_diameter": 1}):
            refused = run_cad_module(CadModuleRequest(module_id="extension_spring", action="create", confirm_write=True,
                parameters={"wire_diameter": 2, "outer_diameter": 22, "turns": 6, **overrides}), adapter)
            self.assertFalse(refused["ok"])
            self.assertFalse(refused["executed"])
        self.assertEqual(adapter.mock_calls, [])
        for left, right in (("machine_hooks", "v_hooks"), ("self_wrapping_hooks", "bent_coil_left_spike"),
                            ("bent_coil_left_spike", "self_wrapping_hooks")):
            profile = ExtensionSpringParameters(outer_diameter=30, wire_diameter=3, turns=5.5,
                hook_type=left, left_hook_type=left, right_hook_type=right).model_dump(exclude_none=True)
            plan = extension_plan(profile, name="Mixed")
            p = plan["preview"]["params"]
            self.assertTrue(p["mixed_hook_types"])
            self.assertEqual(p["right_hook_type"], right)
            self.assertFalse(p["requires_side_specific_hook_builders"])
            if left == "bent_coil_left_spike":
                self.assertTrue(any(s["role"] == "right_hook" for s in p["segment_plan"]))
                self.assertFalse(any(s["role"] == "bent_coil_right" for s in p["segment_plan"]))
            self.assertEqual(plan["recipe"]["parameters"], profile)
        wrapping = ExtensionSpringParameters(outer_diameter=30, wire_diameter=3, turns=5.5,
            hook_type="self_wrapping_hooks", self_wrapping_height=42, self_wrapping_width=44,
            self_wrapping_fillet_radius=3.5, self_wrapping_tail_length=7).model_dump(exclude_none=True)
        p = extension_plan(wrapping, name="Custom wrapping")["preview"]["params"]
        variables = {v["name"]: v for v in p["variable_plan"]}
        for key, value in (("SH1", 42), ("SW1", 44), ("SFR1", 3.5), ("HT1", 7)):
            self.assertEqual(variables[key]["value"], value)

    def test_torsion_family_reuses_legacy_plans_and_requires_complete_dimensions(self) -> None:
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest, run_cad_module
        from kompas_mcp.cad_torsion_bindings import torsion_plan, verify_torsion_legs
        adapter = Mock()
        base = {"wire_diameter": 2, "mean_diameter": 20, "turns": 5, "leg_length": 25}
        for end in ("tangent_legs", "radial_legs", "axial_transition_legs"):
            result = run_cad_module(CadModuleRequest(module_id="torsion_spring", action="plan",
                parameters={**base, "end_type": end, "free_angle_degrees": 45,
                            "start_phase_degrees": 0 if end == "tangent_legs" else 30}), adapter)
            self.assertTrue(result["ok"])
            self.assertAlmostEqual(result["data"]["summary"]["turns"], 5.125)
            plan = torsion_plan(result["parameters"], name="Saved torsion")
            p = plan["preview"]["params"]
            legs = {s["role"]: [s["start_point"], s["end_point"]] for s in p["segment_plan"] if s["path_type"] == "line_segment"}
            verify_torsion_legs(p, {"legs": legs})
            adapter.runner.call.return_value = {"recognized": True, "block": {"recipe": plan["recipe"], "owned_references": [1, 2]}}
            restored = run_cad_module(CadModuleRequest(module_id="torsion_spring", action="inspect", document_id="@document:1"), adapter)
            self.assertEqual(restored["parameters"], result["parameters"])
            self.assertFalse(restored["verified"])
            plan["recipe"]["parameters"].pop("turns")
            incomplete = run_cad_module(CadModuleRequest(module_id="torsion_spring", action="inspect", document_id="@document:1"), adapter)
            self.assertIsNone(incomplete["parameters"])
            adapter.reset_mock()
        for bad in ({"leg_length": None}, {"outer_diameter": 22}, {"left_leg_length": 20},
                    {"gap": .005}, {"start_phase_degrees": 30}, {"transition_fillet_radius": 2}):
            refused = run_cad_module(CadModuleRequest(module_id="torsion_spring", action="create", confirm_write=True,
                parameters={**base, **bad}), adapter)
            self.assertFalse(refused["ok"])
            self.assertFalse(refused["executed"])
        self.assertEqual(adapter.mock_calls, [])

    def test_disc_family_preserves_normal_thickness_and_declares_recreation_limits(self) -> None:
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest, run_cad_module
        from kompas_mcp.cad_disc_bindings import disc_plan
        adapter = Mock()
        base = {"outer_diameter":50,"inner_diameter":25,"thickness":2,"cone_height":3}
        volumes = []
        for direction in ("up","down"):
            planned = run_cad_module(CadModuleRequest(module_id="disc_spring",action="plan",parameters={**base,"cone_direction":direction}),adapter)
            self.assertTrue(planned["ok"])
            self.assertIn("not reliable", " ".join(planned["data"]["warnings"]))
            plan = disc_plan(planned["parameters"],name="Disc")
            volumes.append(plan["expected_volume_cm3"])
            adapter.runner.call.return_value = {"recognized":True,"block":{"recipe":plan["recipe"],"owned_references":[1,2]}}
            inspected = run_cad_module(CadModuleRequest(module_id="disc_spring",action="inspect",document_id="@document:1"),adapter)
            self.assertEqual(inspected["parameters"],planned["parameters"])
            self.assertFalse(inspected["verified"])
            plan["recipe"]["parameters"].pop("cone_height")
            incomplete = run_cad_module(CadModuleRequest(module_id="disc_spring",action="inspect",document_id="@document:1"),adapter)
            self.assertIsNone(incomplete["parameters"])
            adapter.reset_mock()
        self.assertAlmostEqual(volumes[0],volumes[1])
        self.assertAlmostEqual(volumes[0],2.9179990384813)
        alias = run_cad_module(CadModuleRequest(module_id="disc_spring",action="plan",parameters={"outer_diameter":50,"inner_diameter":25,"thickness":2,"free_height":5}),adapter)
        self.assertTrue(alias["ok"])
        self.assertAlmostEqual(alias["data"]["geometry"]["volume_cm3"],volumes[0])
        for bad in ({"inner_diameter":50},{"free_height":5},{"cone_height":0},{"thickness":0}):
            refused = run_cad_module(CadModuleRequest(module_id="disc_spring",action="create",confirm_write=True,parameters={**base,**bad}),adapter)
            self.assertFalse(refused["ok"])
            self.assertFalse(refused["executed"])
        self.assertEqual(adapter.mock_calls,[])

    def test_diaphragm_family_retains_complete_legacy_workflow_and_variant_boundaries(self) -> None:
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CAD_MODULES, CadModuleRequest, run_cad_module
        from kompas_mcp.cad_diaphragm_bindings import diaphragm_plan
        p = dict(CAD_MODULES["diaphragm_spring"].example_parameters)
        adapter = Mock()
        planned = run_cad_module(CadModuleRequest(module_id="diaphragm_spring", action="plan", parameters=p), adapter)
        self.assertTrue(planned["ok"])
        self.assertTrue(any("not certified" in warning for warning in planned["data"]["warnings"]))
        plan = diaphragm_plan(planned["parameters"], name="Test diaphragm")
        ops = plan["preview"]["params"]["operations"]
        self.assertEqual(len(ops), 10)
        self.assertEqual(ops[2]["params"]["nominal_start_radius"], 39)
        self.assertEqual(ops[-1]["params"]["count"], 12)
        self.assertEqual(ops[-1]["params"]["sources"], ["slot_cut.feature", "relief_cut.feature"])
        for cut in ops[-3:-1]:
            self.assertEqual(cut["params"]["end_condition"], "through_all")
            self.assertEqual(cut["params"]["direction"], "both")
        adapter.runner.call.return_value = {"ok":True,"recognized":True,"block":{"recipe":plan["recipe"]}}
        restored = run_cad_module(CadModuleRequest(module_id="diaphragm_spring",action="inspect",document_id="exact-doc"),adapter)
        self.assertTrue(restored["data"]["recreatable"])
        self.assertFalse(restored["verified"])
        self.assertEqual(restored["parameters"],planned["parameters"])
        adapter.reset_mock()
        for changes in ({"slot_fillet_radius":2}, {"relief_radius":2}, {"slot_end_radius":120},
                        {"relief_variant":"oval"}, {"slot_count":1}, {"tip_length":10}, {"cone_height":0}):
            with self.subTest(changes=changes):
                result = run_cad_module(CadModuleRequest(module_id="diaphragm_spring",action="create",confirm_write=True,parameters={**p,**changes}),adapter)
                self.assertFalse(result["ok"])
                self.assertFalse(result["executed"])
        self.assertEqual(adapter.mock_calls, [])

        # High counts must not hide a whole omitted source group within 1%.
        from pathlib import Path
        from kompas_mcp.cad_diaphragm_bindings import create_diaphragm_module
        adapter._export_dir.return_value = Path.cwd()
        adapter._normalize_target_path_for_kompas.side_effect = lambda path: path
        adapter.runner.call.return_value = {"ok":True,"saved":True,"steps":[{"scenario":"circular_pattern",
            "count":500,"pattern_report":{"initial_object_count":2},
            "source_volume_removed":1.0,"additional_volume_removed":498.0}]}
        large_plan = diaphragm_plan({**planned["parameters"],"slot_count":500},name="High-count readback")
        with self.assertRaisesRegex(RuntimeError, "expected repeated material"):
            create_diaphragm_module(adapter,large_plan,False)
        adapter.open_document.assert_not_called()
        adapter.reset_mock()
        def failed_native_call(_action, _payload, **kwargs):
            kwargs["progress_callback"]({"stage":"action_failed","target":"create_part_from_scenario",
                "error":"create_part_from_scenario failed at workflow: native root cause | steps=very long report"})
            raise RuntimeError("tail of diagnostic report " * 1000)
        adapter.runner.call.side_effect = failed_native_call
        with self.assertRaisesRegex(RuntimeError, "native root cause") as caught:
            create_diaphragm_module(adapter,plan,False)
        self.assertLess(len(str(caught.exception)), 200)
        self.assertEqual(caught.exception.partial_result["checkpoint"]["stage"], "action_failed")
        adapter.runner.call.assert_called_once()
        adapter.open_document.assert_not_called()

    def test_shaft_contract_and_native_step_checks_preserve_geometry_boundaries(self) -> None:
        import math
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest,run_cad_module
        from kompas_mcp.cad_shaft_bindings import shaft_plan,verify_shaft_geometry
        p = {"steps":[{"length":10,"diameter":20},{"length":12,"diameter":30},{"length":8,"diameter":20}]}
        adapter = Mock()
        result = run_cad_module(CadModuleRequest(module_id="stepped_shaft",action="plan",parameters=p),adapter)
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["data"]["geometry"]["volume_cm3"],math.pi*(400*18+900*12)/4000)
        plan = shaft_plan(p,name="Shaft test")
        self.assertTrue(plan["preview"]["params"]["fix_sketch_placement"])
        self.assertTrue(plan["preview"]["params"]["require_fully_defined"])
        faces = [{"surface_type":"cylinder","radius_mm":r,"axial_min":a,"axial_max":b}
                 for r,a,b in ((10,0,10),(15,10,22),(10,22,30))]
        bounds = [0,-15,-15,30,15,15]
        verify_shaft_geometry(plan,bounds,faces,plan["expected_volume_cm3"])
        faces[-1]["axial_min"] = 21
        with self.assertRaisesRegex(RuntimeError,"native step"):
            verify_shaft_geometry(plan,bounds,faces,plan["expected_volume_cm3"])
        for invalid in ({"steps":[]},{"steps":[{"length":0,"diameter":20}]},
                        {"steps":[{"length":10,"diameter":20},{"length":5,"diameter":20}]},
                        {**p,"source_scenario":"stepped_shaft"},{**p,"angle_degrees":180},
                        {"steps":[{"length":10,"diameter":1e200}]}):
            with self.subTest(invalid=invalid):
                refused = run_cad_module(CadModuleRequest(module_id="stepped_shaft",action="create",parameters=invalid,confirm_write=True),adapter)
                self.assertFalse(refused["ok"])
                self.assertFalse(refused["executed"])
        self.assertEqual(adapter.mock_calls,[])
        adapter.runner.call.return_value = {"ok":True,"recognized":True,"block":{"recipe":plan["recipe"]}}
        restored = run_cad_module(CadModuleRequest(module_id="stepped_shaft",action="inspect",document_id="exact-shaft"),adapter)
        self.assertTrue(restored["data"]["recreatable"])
        self.assertEqual(restored["parameters"],p)
        self.assertFalse(restored["verified"])
        plan["recipe"]["parameters"] = {}
        self.assertIsNone(run_cad_module(CadModuleRequest(module_id="stepped_shaft",action="inspect",document_id="exact-shaft"),adapter)["parameters"])

    def test_external_cone_modes_keep_independent_inputs_and_native_end_orientation(self) -> None:
        import math
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest,run_cad_module
        from kompas_mcp.cad_cone_bindings import cone_plan,verify_cone_geometry
        base = {"definition_mode":"diameters_length","start_diameter":40,"end_diameter":20,"length":30}
        cases = [base,
            {"definition_mode":"diameters_angle","start_diameter":40,"end_diameter":20,"cone_angle_degrees":math.degrees(math.atan(1/3))},
            {"definition_mode":"diameters_conicity","start_diameter":40,"end_diameter":20,"conicity":2/3},
            {"definition_mode":"one_diameter_length_angle","start_diameter":40,"length":30,"cone_angle_degrees":math.degrees(math.atan(1/3)),"slope_direction":"inward"},
            {"definition_mode":"one_diameter_length_conicity","end_diameter":20,"length":30,"conicity":2/3,"slope_direction":"inward"}]
        adapter = Mock()
        for p in cases:
            with self.subTest(mode=p["definition_mode"]):
                result = run_cad_module(CadModuleRequest(module_id="external_conical_step",action="plan",parameters=p),adapter)
                self.assertTrue(result["ok"])
                self.assertAlmostEqual(result["data"]["geometry"]["volume_cm3"],math.pi*7)
                self.assertEqual(set(result["parameters"]),set(p))
                plan = cone_plan(result["parameters"],name="Cone test")
                dims = next(op["dimensions"] for op in plan["preview"]["operations"] if op["operation"]=="add_dimensions")
                self.assertEqual((dims[0]["kind"],dims[0]["target"],dims[0]["expression"]),("line_length","axis","CONE_L1"))
        plan = cone_plan(base,name="Cone test")
        faces = [{"surface_type":"cone","axial_min":0,"axial_max":30,"start_radius_mm":20,"end_radius_mm":10}]
        verify_cone_geometry(plan,[0,-20,-20,30,20,20],faces,plan["expected_volume_cm3"])
        faces[0].update(start_radius_mm=10,end_radius_mm=20)
        with self.assertRaisesRegex(RuntimeError,"trimmed end"):
            verify_cone_geometry(plan,[0,-20,-20,30,20,20],faces,plan["expected_volume_cm3"])
        faces[0]["start_radius_mm"] = float("nan")
        with self.assertRaisesRegex(RuntimeError,"non-finite"):
            verify_cone_geometry(plan,[0,-20,-20,30,20,20],faces,plan["expected_volume_cm3"])
        invalid = [{**base,"end_diameter":40},{**base,"cone_angle_degrees":20},
            {**base,"source_scenario":"stepped_shaft"},{"definition_mode":"one_diameter_length_angle","start_diameter":40,"length":30,"cone_angle_degrees":10},
            {**cases[-1],"start_diameter":40},{**cases[1],"cone_angle_degrees":90},
            {**cases[-1],"end_diameter":1,"slope_direction":"outward"},
            {**base,"start_diameter":1e200,"end_diameter":2e200}]
        for p in invalid:
            with self.subTest(invalid=p):
                refused = run_cad_module(CadModuleRequest(module_id="external_conical_step",action="create",parameters=p,confirm_write=True),adapter)
                self.assertFalse(refused["ok"])
                self.assertFalse(refused["executed"])
        self.assertEqual(adapter.mock_calls,[])
        adapter.runner.call.return_value = {"ok":True,"recognized":True,"block":{"recipe":plan["recipe"]}}
        restored = run_cad_module(CadModuleRequest(module_id="external_conical_step",action="inspect",document_id="exact-cone"),adapter)
        self.assertEqual(restored["parameters"],base)
        self.assertTrue(restored["data"]["recreatable"])
        self.assertFalse(restored["verified"])
        plan["recipe"]["parameters"].pop("length")
        self.assertIsNone(run_cad_module(CadModuleRequest(module_id="external_conical_step",action="inspect",document_id="exact-cone"),adapter)["parameters"])

    def test_polygon_contract_geometry_drivers_and_recipe_boundary(self) -> None:
        import math
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest, run_cad_module
        from kompas_mcp.cad_polygon_bindings import polygon_plan, verify_polygon_geometry

        adapter = Mock()
        base = {"diameter":32,"length":22,"side_count":5,"diameter_mode":"inscribed_circle",
            "rotation_angle_degrees":17,"axial_direction":"backward"}
        cases = [base, {**base,"diameter":24,"length":17,"side_count":3,
            "diameter_mode":"circumscribed_circle","rotation_angle_degrees":23,"axial_direction":"forward"}]
        for p in cases:
            with self.subTest(mode=p["diameter_mode"]):
                result = run_cad_module(CadModuleRequest(module_id="external_polygonal_step",action="plan",parameters=p), adapter)
                self.assertTrue(result["ok"])
                geometry = result["data"]["geometry"]
                radius = p["diameter"]/2
                if p["diameter_mode"] == "inscribed_circle":
                    radius /= math.cos(math.pi/p["side_count"])
                expected = p["side_count"]*radius*radius*math.sin(2*math.pi/p["side_count"])*p["length"]/2000
                self.assertAlmostEqual(geometry["volume_cm3"], expected)
                self.assertEqual([geometry["bounds_mm"][i] for i in (0,3)],
                    [0,22] if p["axial_direction"] == "backward" else [-17,0])
                plan = polygon_plan(result["parameters"], name="Polygon contract")
                self.assertEqual(plan["preview"]["params"]["sketch_name"], plan["recipe"]["profile_name"])
                self.assertTrue(plan["preview"]["params"]["fix_sketch_placement"])
                operations = plan["preview"]["operations"]
                constraints = next(op["constraints"] for op in operations if op["operation"] == "apply_constraints")
                self.assertFalse(any(row.get("name") == "first_edge_horizontal" for row in constraints))
                self.assertEqual(sum(row["kind"] == "tangent" for row in constraints),
                    1 if p["diameter_mode"] == "inscribed_circle" else 0)
                dims = next(op["dimensions"] for op in operations if op["operation"] == "add_dimensions")
                self.assertEqual(dims[-1]["expression"], "90 - POLY_A1")
                binding = plan["preview"]["params"]["operation_variable_bindings"][0]
                self.assertEqual(binding["parameter_note"], "Distance 2" if p["axial_direction"] == "backward" else "Distance 1")
                points = list(reversed(plan["expected_vertices_mm"]))
                faces = [{"surface_type":"prism_vertices","points_mm":points}]
                verify_polygon_geometry(plan,geometry["bounds_mm"],faces,expected)
                faces[0]["points_mm"] = [points[0]]*len(points)
                with self.assertRaisesRegex(RuntimeError,"vertex position"):
                    verify_polygon_geometry(plan,geometry["bounds_mm"],faces,expected)
        for invalid in ({**base,"side_count":2},{**base,"side_count":65},{**base,"diameter":float("nan")},
                        {**base,"diameter":1e200},{**base,"length":0},{**base,"apply_to_body":True}):
            refused = run_cad_module(CadModuleRequest(module_id="external_polygonal_step",action="create",
                parameters=invalid,confirm_write=True),adapter)
            self.assertFalse(refused["ok"])
            self.assertFalse(refused["executed"])
        self.assertEqual(adapter.mock_calls, [])
        adapter.runner.call.return_value = {"ok":True,"recognized":True,"block":{"recipe":plan["recipe"]}}
        restored = run_cad_module(CadModuleRequest(module_id="external_polygonal_step",action="inspect",document_id="polygon"),adapter)
        self.assertEqual(restored["parameters"],cases[-1])
        self.assertTrue(restored["data"]["recreatable"])
        self.assertFalse(restored["verified"])
        plan["recipe"]["parameters"].pop("rotation_angle_degrees")
        self.assertIsNone(run_cad_module(CadModuleRequest(module_id="external_polygonal_step",action="inspect",document_id="polygon"),adapter)["parameters"])

    def test_flat_contract_geometry_drivers_and_complete_recipe(self) -> None:
        import math
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest, run_cad_module
        from kompas_mcp.cad_flat_bindings import flat_plan, verify_flat_geometry

        adapter = Mock()
        base = {"diameter":30,"length":25,"flat_depth":4,"flats_count":1,"axial_direction":"forward"}
        for p in (base, {**base,"flats_count":2,"axial_direction":"backward"}):
            result = run_cad_module(CadModuleRequest(module_id="external_flat_step",action="plan",parameters=p),adapter)
            self.assertTrue(result["ok"])
            plan = flat_plan(result["parameters"],name="Flat contract")
            self.assertEqual(plan["preview"]["params"]["sketch_name"],plan["recipe"]["profile_name"])
            geometry = result["data"]["geometry"]
            cap = 225*math.acos(11/15)-11*math.sqrt(104)
            self.assertAlmostEqual(geometry["volume_cm3"],(math.pi*225-p["flats_count"]*cap)*25/1000)
            bounds = geometry["bounds_mm"]
            self.assertEqual([bounds[i] for i in (0,3)],[-25,0] if p["axial_direction"] == "forward" else [0,25])
            self.assertEqual([bounds[i] for i in (1,4)],[-11,15] if p["flats_count"] == 1 else [-11,11])
            ops = plan["preview"]["operations"]
            dims = next(op["dimensions"] for op in ops if op["operation"] == "add_dimensions")
            self.assertEqual(dims[0]["expression"],"FLAT_D1")
            self.assertTrue(all(row["expression"] == "FLAT_D1 / 2 - FLAT_F1" for row in dims[1:]))
            binding = plan["preview"]["params"]["operation_variable_bindings"]
            extrusion = next(op for op in ops if op["operation"] == "boss_extrusion")
            self.assertEqual(extrusion["operation_variable_bindings"],binding)
            self.assertEqual(binding[0]["parameter_note"],"Distance 1" if p["axial_direction"] == "forward" else "Distance 2")
            points = plan["expected_chord_vertices_mm"]
            faces = [{"surface_type":"plane","points_mm":[point for point in points if point[0] == end]}
                for end in (bounds[0],bounds[3])]
            faces += [{"surface_type":"plane","points_mm":[point for point in points if point[1] == level]}
                for level in plan["expected_flat_levels_y_mm"]]
            faces += [{"surface_type":"cylinder","radius_mm":15,"points_mm":points if p["flats_count"] == 1
                else [point for point in points if sign*point[2] > 0]} for sign in ((1,) if p["flats_count"] == 1 else (-1,1))]
            verify_flat_geometry(plan,bounds,faces,geometry["volume_cm3"])
            faces[-1]["radius_mm"] = 16
            with self.assertRaisesRegex(RuntimeError,"radius"):
                verify_flat_geometry(plan,bounds,faces,geometry["volume_cm3"])
        for invalid in ({**base,"flat_depth":15},{**base,"flat_depth":0},{**base,"flats_count":1.5},
                        {**base,"flats_count":3},{**base,"diameter":float("nan")},{**base,"flat_depth":1e-300},
                        {**base,"diameter":1e200},{**base,"apply_to_body":True}):
            refused = run_cad_module(CadModuleRequest(module_id="external_flat_step",action="create",
                parameters=invalid,confirm_write=True),adapter)
            self.assertFalse(refused["ok"])
            self.assertFalse(refused["executed"])
        self.assertEqual(adapter.mock_calls,[])
        adapter.runner.call.return_value = {"ok":True,"recognized":True,"block":{"recipe":plan["recipe"]}}
        restored = run_cad_module(CadModuleRequest(module_id="external_flat_step",action="inspect",document_id="flat"),adapter)
        self.assertEqual(restored["parameters"],p)
        self.assertTrue(restored["data"]["recreatable"])
        self.assertFalse(restored["verified"])
        plan["recipe"]["parameters"].pop("flats_count")
        self.assertIsNone(run_cad_module(CadModuleRequest(module_id="external_flat_step",action="inspect",document_id="flat"),adapter)["parameters"])

    def test_module_mcp_preflight_is_bounded_and_never_calls_cad(self) -> None:
        from unittest.mock import Mock
        from mcp.server.fastmcp import FastMCP
        from kompas_mcp.cad_modules import CadModuleRequest, CadModuleResult
        from kompas_mcp.module_tools import register_module_tools

        adapter = Mock()
        mcp = FastMCP("module-contract")
        register_module_tools(mcp, adapter)
        tool = mcp._tool_manager._tools["run_cad_module"].fn
        request = CadModuleRequest(module_id="gear_spur", action="plan")
        planned = tool(request)
        CadModuleResult.model_validate(planned)
        self.assertTrue(planned["ok"])
        self.assertFalse(planned["executed"])
        self.assertFalse(planned["verified"])
        self.assertEqual(planned["verification"]["scope"], "planned_expectations")
        self.assertNotIn("workflow", planned["data"])
        preview = tool(request.model_copy(update={"action": "preview"}))
        self.assertTrue(preview["ok"])
        self.assertNotIn("geometry", preview["data"])
        self.assertFalse(preview["data"]["conformity_claim"])
        self.assertNotIn("conformity_claim", preview["data"]["report"])
        invalid = tool(request.model_copy(update={"parameters": {"tooth_count": 0}}))
        self.assertEqual(invalid["error"]["code"], "INVALID_PARAMETERS")
        self.assertEqual(invalid["error"]["issues"][0]["loc"], ("tooth_count",))
        extra = tool(request.model_copy(update={"parameters": {"execute": True}}))
        self.assertEqual(extra["error"]["code"], "INVALID_PARAMETERS")
        many = tool(request.model_copy(update={"parameters": {"x" * 200 + str(i): 1 for i in range(100)}}))
        self.assertEqual(len(many["error"]["issues"]), 12)
        self.assertEqual(many["error"]["omitted_issues"], 88)
        self.assertLessEqual(len(many["error"]["issues"][0]["loc"][0]), 120)
        refused = tool(request.model_copy(update={"action": "create"}))
        self.assertEqual(refused["error"]["code"], "WRITE_CONFIRMATION_REQUIRED")
        self.assertEqual(adapter.mock_calls, [])

    def test_module_creation_and_recognition_have_different_verification_scopes(self) -> None:
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest, run_cad_module

        adapter = Mock()
        adapter.create_gear_spur.return_value = {
            "ok": True, "executed": True, "document": {"runtime_id": "@document:0"},
            "body": {"volume": 1.0}, "verification": {"ok": True, "pattern_count": 20},
            "block": {"owned_references": ["root:1", "root:2"]},
            "saved": False, "steps": [{"large_detail": [1, 2, 3]}],
        }
        request = CadModuleRequest(module_id="gear_spur", action="create", confirm_write=True)
        created = run_cad_module(request, adapter)
        self.assertTrue(created["verified"])
        self.assertEqual(created["data"]["document"]["runtime_id"], "@document:0")
        self.assertNotIn("steps", created["data"])
        self.assertEqual(created["data"]["owned_references"], ["root:1", "root:2"])
        adapter.create_gear_spur.assert_called_once()
        self.assertEqual(adapter.create_gear_spur.call_args.kwargs,
                         {"execute": True, "confirm_write": True, "visible": True})
        adapter.inspect_gear_spur.return_value = {
            "module": "gear_spur", "verified": True, "recreatable": True,
            "profile": created["parameters"], "owned_references": ["root:1"],
        }
        inspect_request = CadModuleRequest(module_id="gear_spur", action="inspect", document_id="@document:0")
        recognized = run_cad_module(inspect_request, adapter)
        self.assertTrue(recognized["ok"])
        self.assertFalse(recognized["verified"])
        self.assertTrue(recognized["verification"]["stored_verified"])
        self.assertFalse(recognized["verification"]["fresh_geometry_audit"])
        self.assertEqual(recognized["parameters"], created["parameters"])
        adapter.inspect_gear_spur.return_value["recreatable"] = False
        self.assertIsNone(run_cad_module(inspect_request, adapter)["parameters"])
        adapter.create_gear_spur.return_value.pop("verification")
        self.assertFalse(run_cad_module(request, adapter)["ok"])

    def test_module_runtime_failure_preserves_partial_document_without_retry(self) -> None:
        from unittest.mock import Mock
        from kompas_mcp.bridge_runner import BridgeError
        from kompas_mcp.cad_modules import CadModuleRequest, run_cad_module

        adapter = Mock()
        adapter.create_gear_spur.side_effect = BridgeError(
            'create_gear_spur failed at rebuild: native failure | partial_document={"runtime_id":"@document:0"}'
        )
        request = CadModuleRequest(module_id="gear_spur", action="create", confirm_write=True)
        failed = run_cad_module(request, adapter)
        self.assertFalse(failed["ok"])
        self.assertFalse(failed["verified"])
        self.assertIsNone(failed["executed"])
        self.assertEqual(failed["partial_result"]["document"]["runtime_id"], "@document:0")
        self.assertFalse(failed["partial_result"]["rollback_performed"])
        self.assertFalse(failed["error"]["retryable"])
        adapter.create_gear_spur.assert_called_once()
        adapter.create_gear_spur.side_effect = BridgeError("Bridge call timed out")
        self.assertIsNone(run_cad_module(request, adapter)["partial_result"])
        adapter.create_gear_spur.side_effect = PermissionError("Unable to read response after CAD write")
        failed = run_cad_module(request, adapter)
        self.assertEqual(failed["stage"], "failed")
        self.assertIsNone(failed["executed"])

        adapter.create_gear_spur.side_effect = BridgeError("CAD_RUNTIME_INVALID: runtime preflight failed")
        failed = run_cad_module(request,adapter)
        self.assertEqual(failed["error"]["code"],"CAD_RUNTIME_INVALID")
        self.assertIn("KOMPAS_PYTHON",failed["error"]["hint"])
        self.assertFalse(failed["error"]["retryable"])
        # A multi-call creator may already have written before a later preflight.
        self.assertIsNone(failed["executed"])

    def test_module_cli_stdin_and_exit_codes_follow_shared_contract(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO
        import json
        from unittest.mock import patch
        from geomwright.model import main

        output = StringIO()
        with redirect_stdout(output), patch("sys.stdin", StringIO(
            '{"module_id":"gear_spur","action":"preview","parameters":{"tooth_count":24}}'
        )):
            self.assertEqual(main(["run", "-"]), 0)
        self.assertEqual(json.loads(output.getvalue())["data"]["summary"]["tooth_count"], 24)
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["describe", "missing"]), 1)
        with redirect_stdout(StringIO()), patch("sys.stdin", StringIO('{"action":"inspect"}')):
            self.assertEqual(main(["run", "-"]), 2)

    def test_internal_and_bevel_modules_reuse_dispatch_with_family_specific_validation(self) -> None:
        import json
        from unittest.mock import Mock
        from kompas_mcp.cad_modules import CadModuleRequest, get_cad_module_contract, run_cad_module

        for module_id, create_method, inspect_method in (
            ("gear_internal", "create_gear_internal", "inspect_gear_internal"),
            ("gear_bevel", "create_gear_bevel", "inspect_gear_bevel"),
        ):
            with self.subTest(module_id=module_id):
                adapter = Mock()
                contract = get_cad_module_contract(module_id)
                request = CadModuleRequest.model_validate(contract["examples"]["plan"])
                planned = run_cad_module(request, adapter)
                self.assertTrue(planned["ok"])
                self.assertEqual(planned["data"]["name"], contract["default_name"])
                self.assertLess(len(json.dumps(planned)), 20000)
                preview = run_cad_module(request.model_copy(update={"action": "preview"}), adapter)
                self.assertTrue(preview["ok"])
                self.assertFalse(preview["data"]["conformity_claim"])
                self.assertNotIn("geometry", preview["data"])
                self.assertEqual(adapter.mock_calls, [])
                getattr(adapter, create_method).return_value = {
                    "ok": True, "executed": True, "verification": {"ok": True},
                    "block": {"owned_references": ["root:1"]},
                }
                created = run_cad_module(request.model_copy(update={
                    "action": "create", "confirm_write": True, "name": "Explicit gear name",
                }), adapter)
                self.assertTrue(created["verified"])
                self.assertEqual(created["data"]["name"], "Explicit gear name")
                getattr(adapter, create_method).assert_called_once()
                self.assertEqual(getattr(adapter, create_method).call_args.args[0]["family"], module_id)
                getattr(adapter, inspect_method).return_value = {"module": "gear_spur"}
                wrong = run_cad_module(CadModuleRequest(
                    module_id=module_id, action="inspect", document_id="@document:0",
                ), adapter)
                self.assertEqual(wrong["error"]["code"], "WRONG_MODULE")

        adapter = Mock()
        ring = run_cad_module(CadModuleRequest(module_id="gear_internal", action="create",
            confirm_write=True, parameters={"ring_outside_diameter_mm": 10}), adapter)
        self.assertFalse(ring["ok"])
        self.assertFalse(ring["executed"])
        circular = run_cad_module(CadModuleRequest(module_id="gear_bevel", action="create",
            confirm_write=True, parameters={"tooth_type": "circular"}), adapter)
        self.assertEqual(circular["error"]["code"], "INVALID_PARAMETERS")
        cylindrical_field = run_cad_module(CadModuleRequest(module_id="gear_bevel", action="plan",
            parameters={"helix_angle_deg": 20}), adapter)
        self.assertEqual(cylindrical_field["error"]["code"], "INVALID_PARAMETERS")
        self.assertEqual(adapter.mock_calls, [])

    def test_chain_module_keeps_managed_execution_and_compact_recipe_readback(self) -> None:
        import json
        from unittest.mock import Mock, patch
        from kompas_mcp.adapter import KompasAdapter
        from kompas_mcp.cad_modules import CadModuleRequest, get_cad_module_contract, run_cad_module

        adapter = Mock()
        contract = get_cad_module_contract("chain_sprocket")
        self.assertEqual(contract["selection_tools"], ["list_chain_profiles"])
        request = CadModuleRequest(module_id="chain_sprocket", action="plan",
                                   parameters={"designation": "ISO_08B_2", "tooth_count": 25, "row_count": 2})
        planned = run_cad_module(request, adapter)
        self.assertTrue(planned["ok"])
        self.assertEqual(planned["data"]["geometry"]["row_count"], 2)
        self.assertNotIn("tooth_space_entities", planned["data"]["geometry"])
        self.assertLess(len(json.dumps(planned)), 15000)
        preview = run_cad_module(request.model_copy(update={"action": "preview"}), adapter)
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["data"]["summary"]["row_count"], 2)
        invalid = run_cad_module(request.model_copy(update={"parameters": {"designation": "ISO_08B_2", "row_count": 1}}), adapter)
        self.assertFalse(invalid["ok"])
        self.assertFalse(invalid["executed"])
        self.assertEqual(adapter.mock_calls, [])

        adapter.create_managed_pulley.return_value = {
            "ok": True, "executed": True, "verification": {"ok": True},
            "transition_constraint": {"ok": True, "constraints_state_requires_ui_confirmation": False},
            "document": {"runtime_id": "@document:0"}, "body": {"body_count": 1},
        }
        adapter.inspect_managed_pulley.return_value = {
            "recognized": True, "family": "chain_sprocket", "recreatable": True,
            "profile_request": planned["parameters"], "identity_references": [1, 2, 3, 4, 5],
            "owned_references": list(range(100)),
        }
        created = run_cad_module(request.model_copy(update={"action": "create", "confirm_write": True}), adapter)
        self.assertTrue(created["verified"])
        self.assertEqual(created["data"]["owned_references"], [1, 2, 3, 4, 5])
        kwargs = adapter.create_managed_pulley.call_args.kwargs
        self.assertIs(kwargs["confirm_write"], True)
        self.assertEqual(kwargs["prepared_plan"]["family"], "chain_sprocket")
        inspected = run_cad_module(CadModuleRequest(module_id="chain_sprocket", action="inspect",
                                                   document_id="@document:0"), adapter)
        self.assertEqual(inspected["parameters"], planned["parameters"])
        self.assertIsNone(inspected["verification"]["stored_verified"])
        self.assertFalse(inspected["verified"])
        adapter.inspect_managed_pulley.return_value["recreatable"] = False
        failed = run_cad_module(request.model_copy(update={"action": "create", "confirm_write": True}), adapter)
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["partial_result"]["document"]["runtime_id"], "@document:0")

        # A prepared plan reuses the existing finalization path without recalculating it.
        runner = Mock()
        runner.call.return_value = {"success": False}
        real_adapter = KompasAdapter(runner=runner)
        with patch("kompas_mcp.adapter.build_chain_sprocket_plan", side_effect=AssertionError("unexpected rebuild")):
            real_adapter.create_managed_pulley(family="chain_sprocket", profile_request=kwargs["profile_request"],
                name=kwargs["name"], execute=True, confirm_write=True, prepared_plan=kwargs["prepared_plan"])
        self.assertEqual(runner.call.call_args.args[0], "create_chain_sprocket")
        runner.call.reset_mock()
        with self.assertRaisesRegex(ValueError, "prepared_plan"):
            real_adapter.create_managed_pulley(family="chain_sprocket", profile_request={"row_count": 1},
                name=kwargs["name"], execute=True, confirm_write=True, prepared_plan=kwargs["prepared_plan"])
        runner.call.assert_not_called()

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

    def test_bevel_request_and_geometry_reject_invalid_numeric_inputs(self) -> None:
        from kompas_mcp.gears import BevelGearRequest, build_bevel_gear_preview
        from kompas_mcp.gears.bevel import build_bevel_gear_geometry

        fields = ("module_mm", "pitch_cone_angle_deg", "profile_shift", "face_width_mm",
                  "rim_back_extension_mm", "rim_front_extension_mm", "pressure_angle_deg",
                  "addendum_coefficient", "clearance_coefficient", "root_fillet_coefficient")
        for field in fields:
            for value in (float("nan"), float("inf"), -float("inf")):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        BevelGearRequest(**{field: value})
                    with self.assertRaises(ValueError):
                        build_bevel_gear_geometry({field: value})
        for payload in ({"tooth_count": 1e100}, {"face_width_mm": 0},
                        {"tooth_type": "circular"}, {"profile_shift": 1e100}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                build_bevel_gear_preview(payload)
        for payload, code in (
            ({"profile_shift": -1.0}, "gear_bevel_invalid_tooth_heights"),
            ({"face_width_mm": 1000}, "gear_bevel_face_width_exceeds_cone"),
            ({"module_mm": 1e-300}, "gear_bevel_blank_face_radius_invalid"),
        ):
            preview = build_bevel_gear_preview(payload)
            self.assertFalse(preview["success"])
            self.assertIn(code, {item["code"] for item in preview["errors"]})

    def test_bevel_plan_preserves_homothety_and_verification_contract(self) -> None:
        import math
        from unittest.mock import patch
        from kompas_mcp.gears.bevel import build_bevel_gear_geometry
        from kompas_mcp.gears.cad import build_bevel_gear_plan
        from kompas_mcp.gears import BevelGearRequest

        normalized = BevelGearRequest(standard="GOST_13754_68", modification="STANDARD")
        self.assertEqual((normalized.standard, normalized.modification),
                         ("gost_13754_68", "standard"))
        with self.assertRaisesRegex(ValueError, "120"):
            build_bevel_gear_plan({}, name="x" * 121)

        with patch("kompas_mcp.gears.cad.build_bevel_gear_geometry",
                   wraps=build_bevel_gear_geometry) as calculate:
            plan = build_bevel_gear_plan({})
        self.assertEqual(calculate.call_count, 1)
        geometry = plan["geometry"]
        self.assertAlmostEqual(geometry["outer_pitch_diameter_mm"], 60.0)
        self.assertAlmostEqual(geometry["outer_cone_distance_mm"], 30 * math.sqrt(2))
        self.assertAlmostEqual(geometry["virtual_tooth_count"], 20 * math.sqrt(2))
        self.assertAlmostEqual(geometry["rim_back_extension_mm"], 10.26)
        self.assertAlmostEqual(geometry["rim_front_extension_mm"], 2.565)
        self.assertEqual(plan["ownership"]["standard_code"], 5)
        self.assertEqual(plan["ownership"]["modification_code"], 5)
        outer, inner = plan["workflow"]["params"]["operations"][1:3]
        self.assertIn("c2_cubic_bspline", plan["accuracy"]["profile_encoding"])
        for entity in outer["params"]["entities"]:
            if entity["kind"] == "nurbs":
                interior = entity["knots"][4:-4]
                self.assertEqual(len(interior), len(set(interior)))
                self.assertTrue(all(a < b for a, b in zip(interior, interior[1:])))
        ratio = geometry["inner_section_scale"] / geometry["outer_section_scale"]
        for first, second in zip(outer["params"]["entities"], inner["params"]["entities"]):
            keys = ("points3",) if first["kind"] == "nurbs" else ("start3", "end3")
            for key in keys:
                points1 = first[key] if key == "points3" else [first[key]]
                points2 = second[key] if key == "points3" else [second[key]]
                for point1, point2 in zip(points1, points2):
                    for coordinate1, coordinate2 in zip(point1, point2):
                        self.assertAlmostEqual(coordinate2, coordinate1 * ratio)
        self.assertEqual(plan["verification"]["expected_volume_mm3"],
                         plan["profile_preview"]["summary"]["expected_volume_mm3"])
        self.assertFalse(plan["accuracy"]["conformity_claim"])
        self.assertGreater(geometry["removed_volume_mm3"], 0.0)
        self.assertGreaterEqual(plan["verification"]["bounds_tolerance_mm"],
                                2.0 * geometry["spline_deviation_mm"])

        from kompas_mcp.gears.bevel import _project_to_end_view
        calculated = build_bevel_gear_geometry({})
        self.assertAlmostEqual(plan["profile_preview"]["summary"]["blank_width_mm"],
                               calculated.expected_bounds_mm[3] - calculated.expected_bounds_mm[0])
        cosine = math.cos(calculated.pitch_cone_angle_rad)
        sine = math.sin(calculated.pitch_cone_angle_rad)
        apex = calculated.cone_frame["apex"][0]
        for u, v in calculated.virtual_surface_path:
            projected = _project_to_end_view([u, v], cosine, sine, apex,
                                             calculated.outer_cone_distance_mm)
            scale = projected[1] / (v * cosine)
            axial = scale * (apex + v * sine)
            # Every tooth-end point lies on the revolved back cone, not just
            # on its tangent plane at the pitch generator.
            self.assertAlmostEqual(sine * math.hypot(*projected) - cosine * axial,
                                   calculated.outer_cone_distance_mm)
        # Repeating a closed cropped period used to draw gap-to-gap chords
        # across every tooth; the complete outline must remain continuous.
        self.assertLess(max(math.dist(a, b) for a, b in zip(
            calculated.end_view_wheel, calculated.end_view_wheel[1:])),
            calculated.module_mm / 2)
        # One period must stay between its two gap centres. A mirrored flank
        # used to generate a >pitch tip arc across neighboring tooth spaces.
        pitch_angle = 2 * math.pi / calculated.tooth_count
        angles = [math.atan2(y, z) for y, z in calculated.end_view_period]
        self.assertGreaterEqual(min(angles), -1e-10)
        self.assertLessEqual(max(angles), pitch_angle + 1e-10)
        high_cone = build_bevel_gear_geometry({"pitch_cone_angle_deg": 80})
        self.assertFalse(high_cone.errors)
        curves = high_cone.diagnostics["curves"]
        self.assertEqual(curves["junction"], "analytic_rack_tangent")
        self.assertGreaterEqual(len(curves["fillet_path"]), 24)
        self.assertLess(math.dist(curves["fillet_path"][-1], curves["involute_path"][0]), 1e-8)
        h = high_cone.outer_dedendum_mm
        rho = high_cone.rack.fillet_coefficient * high_cone.module_mm
        centre_depth = h - rho
        alpha = high_cone.pressure_angle_rad
        expected_form_radius = math.hypot(high_cone.virtual_pitch_radius_mm - centre_depth - rho * math.sin(alpha),
                                         centre_depth / math.tan(alpha) + rho * math.cos(alpha))
        self.assertAlmostEqual(curves["form_radius_mm"], expected_form_radius)
        self.assertEqual(curves["root_envelope"], "rounded_rack_trochoid")
        a, b, c = curves["fillet_path"][:3]
        twice_area = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        root_curvature_radius = math.dist(a, b) * math.dist(b, c) * math.dist(a, c) / (2 * twice_area)
        self.assertGreaterEqual(root_curvature_radius, rho * .95)

    def test_bevel_volume_clipping_and_quadrature_converge(self) -> None:
        import math
        from kompas_mcp.gears.bevel import build_bevel_gear_geometry, _removed_volume, _ray_polygon_intervals

        # In this parallel-plane limit the pyramid integral is known exactly:
        # area * outer_distance * (1 - inner_scale**3) / 3.
        rectangle = [[-1., 2.], [1., 2.], [1., 3.], [-1., 3.], [-1., 2.]]
        self.assertEqual(_ray_polygon_intervals(
            [0., 0.], [1., 1.], [[1., 1.], [2., 1.], [2., 2.], [1., 2.], [1., 1.]]),
            [1.0, 2.0])
        args = dict(cone_apex_x=-10., sin_delta=0., cos_delta=1., tan_face_cone=10.,
                    back_face_x=-20., front_face_x=0., outer_cone_distance=10.,
                    inner_cone_distance=5.)
        volume = _removed_volume(rectangle, **args)
        self.assertAlmostEqual(volume / (2 * 10 * (1 - .5**3) / 3), 1.0, places=4)
        # The front flat face can extend the plate into the nominal inner cone.
        args["section_inner_cone_distance"] = 2.
        args["front_face_x"] = -8.
        self.assertAlmostEqual(_removed_volume(rectangle, **args), volume)
        args["front_face_x"] = -2.
        self.assertGreater(_removed_volume(rectangle, **args), volume)

        for request in ({}, {"module_mm": 4., "tooth_count": 16,
                             "pitch_cone_angle_deg": 26.565, "profile_shift": .3},
                        {"pitch_cone_angle_deg": 80., "tooth_count": 40}):
            with self.subTest(request=request):
                geometry = build_bevel_gear_geometry(request)
                self.assertFalse(geometry.errors)
                kwargs = dict(
                    cone_apex_x=geometry.cone_frame["apex"][0],
                    sin_delta=math.sin(geometry.pitch_cone_angle_rad),
                    cos_delta=math.cos(geometry.pitch_cone_angle_rad),
                    tan_face_cone=math.tan(geometry.face_cone_angle_rad),
                    back_face_x=geometry.back_face_x_mm, front_face_x=geometry.front_face_x_mm,
                    outer_cone_distance=geometry.outer_cone_distance_mm,
                    inner_cone_distance=geometry.inner_cone_distance_mm,
                    section_outer_cone_distance=geometry.section_outer_cone_distance_mm,
                    section_inner_cone_distance=geometry.section_inner_cone_distance_mm,
                )
                refined = _removed_volume(geometry.virtual_gap_outline, stations=384, **kwargs)
                self.assertLess(abs(refined * geometry.tooth_count - geometry.removed_volume_mm3)
                                / geometry.expected_volume_mm3, .0001)

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
