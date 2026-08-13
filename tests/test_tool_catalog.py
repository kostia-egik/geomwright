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
        catalog = get_mcp_tool_catalog(stability="research")

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

        catalog = server.get_mcp_tool_catalog(stability="research")

        self.assertTrue(catalog["ok"])
        self.assertEqual(catalog["stability"], "research")

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

        self.assertEqual(source_tools, set(_registered_tool_names()))

    def test_server_stays_bootstrap_sized(self) -> None:
        server_tool_names = _source_tool_names([SERVER_PATH])

        self.assertEqual(server_tool_names, ["get_mcp_tool_catalog"])
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
