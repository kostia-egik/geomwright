import ast
import inspect
import unittest
from pathlib import Path

from kompas_mcp.tool_catalog import get_mcp_tool_catalog


class ToolCatalogTests(unittest.TestCase):
    def test_catalog_covers_server_tools_without_duplicates(self) -> None:
        catalog = get_mcp_tool_catalog()
        catalog_tools = [
            tool
            for category in catalog["categories"]
            for tool in category["tools"]
        ]
        server_tools = _server_tool_names()

        self.assertEqual(len(catalog_tools), len(set(catalog_tools)))
        self.assertEqual(set(catalog_tools), set(server_tools))
        self.assertEqual(catalog["tool_count"], len(server_tools))

    def test_can_filter_by_category(self) -> None:
        catalog = get_mcp_tool_catalog(category="low_level_runtime")

        self.assertTrue(catalog["ok"])
        self.assertEqual(catalog["category_count"], 1)
        self.assertIn("probe_document_readback", catalog["categories"][0]["tools"])

    def test_unknown_category_returns_empty_catalog(self) -> None:
        catalog = get_mcp_tool_catalog(category="missing")

        self.assertFalse(catalog["ok"])
        self.assertEqual(catalog["tool_count"], 0)

    def test_probe_document_readback_surface_closes_model_path_by_default(self) -> None:
        from kompas_mcp import server
        from kompas_mcp.adapter import KompasAdapter

        server_default = inspect.signature(server.probe_document_readback).parameters["close_after_probe"].default
        adapter_default = inspect.signature(KompasAdapter.probe_document_readback).parameters["close_after_probe"].default

        self.assertIs(server_default, True)
        self.assertIs(adapter_default, True)


def _server_tool_names() -> list[str]:
    root = Path(__file__).resolve().parents[1]
    module = ast.parse((root / "src" / "kompas_mcp" / "server.py").read_text(encoding="utf-8"))
    names: list[str] = []
    for node in module.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        decorators = [ast.unparse(decorator) for decorator in node.decorator_list]
        if any("mcp.tool" in decorator for decorator in decorators):
            names.append(node.name)
    return names


if __name__ == "__main__":
    unittest.main()
