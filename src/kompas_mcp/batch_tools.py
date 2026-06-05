from __future__ import annotations

from typing import Any, Callable


def register_batch_tools(mcp: Any, adapter: Any, rules_loader: Callable[[str | None], dict]) -> None:
    """Register batch inventory and quality tools."""

    @mcp.tool()
    def scan_model_files(
        root: str,
        recursive: bool = True,
        extensions: list[str] | None = None,
        include_locks: bool = False,
        max_files: int | None = None,
    ) -> dict:
        """Scan a folder or a single file for KOMPAS model files without opening KOMPAS."""
        return adapter.scan_model_files(
            root=root,
            recursive=recursive,
            extensions=extensions,
            include_locks=include_locks,
            max_files=max_files,
        )

    @mcp.tool()
    def batch_smoke_check_session(
        root: str | None = None,
        paths: list[str] | None = None,
        recursive: bool = True,
        extensions: list[str] | None = None,
        include_locks: bool = False,
        limit: int | None = 20,
        output_dir: str | None = None,
        visible: bool = False,
        dry_run: bool = False,
        continue_on_error: bool = True,
        report_dir: str | None = None,
        report_name: str | None = None,
        report_formats: list[str] | None = None,
    ) -> dict:
        """Run lifecycle smoke-checks over a folder or explicit file list, continuing after per-file errors."""
        return adapter.batch_smoke_check_session(
            root=root,
            paths=paths,
            recursive=recursive,
            extensions=extensions,
            include_locks=include_locks,
            limit=limit,
            output_dir=output_dir,
            visible=visible,
            dry_run=dry_run,
            continue_on_error=continue_on_error,
            report_dir=report_dir,
            report_name=report_name,
            report_formats=report_formats,
        )

    @mcp.tool()
    def batch_analyze_model_quality(
        root: str | None = None,
        paths: list[str] | None = None,
        recursive: bool = True,
        extensions: list[str] | None = None,
        include_locks: bool = False,
        limit: int | None = 20,
        visible: bool = False,
        analyses: list[str] | None = None,
        rules_path: str | None = None,
        continue_on_error: bool = True,
        report_dir: str | None = None,
        report_name: str | None = None,
        report_formats: list[str] | None = None,
    ) -> dict:
        """Open models read-only, run naming/spec quality checks, close each document and continue after errors."""
        return adapter.batch_analyze_model_quality(
            root=root,
            paths=paths,
            recursive=recursive,
            extensions=extensions,
            include_locks=include_locks,
            limit=limit,
            visible=visible,
            analyses=analyses,
            rules=rules_loader(rules_path),
            continue_on_error=continue_on_error,
            report_dir=report_dir,
            report_name=report_name,
            report_formats=report_formats,
        )
