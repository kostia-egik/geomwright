"""Geomwright MCP bootstrap for the KOMPAS-3D adapter."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from kompas_mcp.batch_tools import register_batch_tools
from kompas_mcp.cam_tools import register_cam_tools
from kompas_mcp.document_tools import register_document_tools
from kompas_mcp.native_tools import register_native_tools
from kompas_mcp.part_tools import register_part_tools
from kompas_mcp.quality_tools import register_quality_tools
from kompas_mcp.rules import load_rules
from kompas_mcp.runtime_tools import register_runtime_tools
from kompas_mcp.section_tools import register_section_tools
from kompas_mcp.session_tools import register_session_tools
from kompas_mcp.sketch_tools import register_sketch_tools
from kompas_mcp.specification_tools import register_specification_tools
from kompas_mcp.spring_tools import register_spring_tools
from kompas_mcp.thread_tools import register_thread_tools
from kompas_mcp.transmission_tools import register_transmission_tools
from kompas_mcp.workflow_tools import register_workflow_tools

from .adapter import KompasAdapter
from .tool_catalog import get_mcp_tool_catalog as build_mcp_tool_catalog


mcp = FastMCP("geomwright", json_response=True)
adapter = KompasAdapter()


def _research_tools_enabled() -> bool:
    return os.environ.get("GEOMWRIGHT_ENABLE_RESEARCH_TOOLS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _rules(rules_path: str | None = None) -> dict:
    return load_rules(rules_path or os.environ.get("KOMPAS_RULES_PATH"))


@mcp.tool()
def get_mcp_tool_catalog(
    category: str | None = None,
    stability: str | None = None,
    include_research: bool = False,
) -> dict:
    """Return the public tool catalog; research tools require explicit opt-in."""
    research_enabled = _research_tools_enabled()
    return build_mcp_tool_catalog(
        category=category,
        stability=stability,
        include_research=include_research and research_enabled,
    )


if _research_tools_enabled():
    register_native_tools(mcp, adapter)
register_thread_tools(mcp)
register_transmission_tools(mcp, adapter)
register_cam_tools(mcp, adapter)
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


__all__ = ["adapter", "get_mcp_tool_catalog", "main", "mcp"]
