"""Top-level MCP server facade for the default KOMPAS adapter."""

from .kompas.server import adapter, get_mcp_tool_catalog, main, mcp

__all__ = ["adapter", "get_mcp_tool_catalog", "main", "mcp"]
