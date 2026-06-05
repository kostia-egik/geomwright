from __future__ import annotations

from typing import Any

from .thread_catalog import list_helical_thread_v1_candidates as build_helical_thread_v1_candidates
from .thread_catalog import list_thread_catalog_standards as build_thread_catalog_standards
from .thread_catalog import list_thread_standard_entries as build_thread_standard_entries
from .thread_catalog import resolve_thread_designation_entry as build_thread_designation_entry


def register_thread_tools(mcp: Any) -> None:
    """Register thread catalog discovery tools."""

    @mcp.tool()
    def list_thread_catalog_standards(database_path: str | None = None) -> dict:
        """List thread standards from KOMPAS thread.db with helical-thread V1 compatibility hints."""
        return build_thread_catalog_standards(database_path=database_path)

    @mcp.tool()
    def list_thread_catalog_entries(
        standard: str,
        database_path: str | None = None,
        limit: int | None = 200,
        offset: int | None = 0,
        title_query: str | None = None,
        diameter: float | None = None,
        pitch: float | None = None,
        diameter_min: float | None = None,
        diameter_max: float | None = None,
        pitch_min: float | None = None,
        pitch_max: float | None = None,
    ) -> dict:
        """List size rows of one thread standard table (d/p/title), with helical-thread-friendly shaping."""
        return build_thread_standard_entries(
            standard,
            database_path=database_path,
            limit=limit,
            offset=offset,
            title_query=title_query,
            diameter=diameter,
            pitch=pitch,
            diameter_min=diameter_min,
            diameter_max=diameter_max,
            pitch_min=pitch_min,
            pitch_max=pitch_max,
        )

    @mcp.tool()
    def list_helical_thread_v1_candidates(
        database_path: str | None = None,
        limit_per_standard: int | None = 20,
        offset: int | None = 0,
        title_query: str | None = None,
        diameter_min: float | None = None,
        diameter_max: float | None = None,
        pitch_min: float | None = None,
        pitch_max: float | None = None,
    ) -> dict:
        """List only helical-thread-V1-compatible metric standards with bundled size rows."""
        return build_helical_thread_v1_candidates(
            database_path=database_path,
            limit_per_standard=limit_per_standard,
            offset=offset,
            title_query=title_query,
            diameter_min=diameter_min,
            diameter_max=diameter_max,
            pitch_min=pitch_min,
            pitch_max=pitch_max,
        )

    @mcp.tool()
    def resolve_thread_catalog_designation(
        designation: str,
        standard: str | None = None,
        thread_type: str | None = None,
        database_path: str | None = None,
    ) -> dict:
        """Resolve a thread size by its designation/title within the default standard for a thread type (or an explicit standard)."""
        return build_thread_designation_entry(
            designation,
            standard=standard,
            thread_type=thread_type,
            database_path=database_path,
        )
