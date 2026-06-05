from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .adapter import KompasAdapter
from .batch_tools import register_batch_tools
from .document_tools import register_document_tools
from .part_tools import register_part_tools
from .quality_tools import register_quality_tools
from .runtime_tools import register_runtime_tools
from .section_tools import register_section_tools
from .rules import load_rules
from .session_tools import register_session_tools
from .sketch_tools import register_sketch_tools
from .specification_tools import register_specification_tools
from .spring_tools import register_spring_tools
from .native_tools import register_native_tools
from .thread_tools import register_thread_tools
from .tool_catalog import get_mcp_tool_catalog as build_mcp_tool_catalog
from .workflow_tools import register_workflow_tools


mcp = FastMCP("kompas-mcp", json_response=True)
adapter = KompasAdapter()


def _rules(rules_path: str | None = None) -> dict:
    return load_rules(rules_path or os.environ.get("KOMPAS_RULES_PATH"))


@mcp.tool()
def get_mcp_tool_catalog(category: str | None = None, stability: str | None = None) -> dict:
    """Return the grouped MCP tool catalog for discoverability."""
    return build_mcp_tool_catalog(category=category, stability=stability)


register_native_tools(mcp, adapter)
register_thread_tools(mcp)
register_session_tools(mcp, adapter)
register_runtime_tools(mcp, adapter)
register_section_tools(mcp)
register_sketch_tools(mcp, adapter)
register_batch_tools(mcp, adapter, _rules)
register_part_tools(mcp, adapter)
register_spring_tools(mcp, adapter)
register_specification_tools(mcp, adapter)


register_workflow_tools(mcp, adapter, _rules)
register_document_tools(mcp, adapter)


register_quality_tools(mcp, adapter, _rules)


def main() -> None:
    mcp.run()
