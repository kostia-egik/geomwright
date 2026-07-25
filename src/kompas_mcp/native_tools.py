from __future__ import annotations

from typing import Any

from .native_modules import inspect_native_entrypoint_static_abi as build_native_entrypoint_static_abi_inspection
from .native_modules import inspect_native_module as build_native_module_inspection
from .native_modules import inspect_native_module_entrypoints as build_native_module_entrypoint_inspection
from .native_modules import inspect_native_module_interfaces as build_native_module_interface_inspection
from .native_modules import inspect_native_spring_workflow as build_native_spring_workflow_inspection
from .native_modules import list_native_modules as build_native_modules
from .native_modules import plan_native_entrypoint_validation as build_native_entrypoint_validation_plan
from .native_modules import probe_native_entrypoint_loader as build_native_entrypoint_loader_probe
from .native_modules import probe_native_entrypoint_loader_hosted as build_native_entrypoint_loader_hosted_probe
from .native_modules import probe_native_module_programmatic_access as build_native_module_programmatic_access_probe


def register_native_tools(mcp: Any, adapter: Any) -> None:
    """Register native KOMPAS module research tools."""

    @mcp.tool()
    def list_native_modules(
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        max_modules: int | None = 200,
    ) -> dict:
        """List installed native KOMPAS application modules from a Libs directory."""
        return build_native_modules(
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            max_modules=max_modules,
        )

    @mcp.tool()
    def inspect_native_module(
        module: str = "Spring",
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        include_database_inventory: bool = True,
        max_tables_per_database: int | None = 40,
    ) -> dict:
        """Inspect one native KOMPAS module manifest, files, commands, and read-only database inventory."""
        return build_native_module_inspection(
            module=module,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            include_database_inventory=include_database_inventory,
            max_tables_per_database=max_tables_per_database,
        )

    @mcp.tool()
    def inspect_native_module_interfaces(
        module: str = "Spring",
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        max_files: int | None = 40,
        max_string_hits: int | None = 80,
        max_bytes_per_file: int | None = 1_000_000,
    ) -> dict:
        """Inspect static evidence for native module parameter/session/job-file interfaces."""
        return build_native_module_interface_inspection(
            module=module,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            max_files=max_files,
            max_string_hits=max_string_hits,
            max_bytes_per_file=max_bytes_per_file,
        )

    @mcp.tool()
    def inspect_native_spring_workflow(
        spring_kind: str | None = None,
        command_id: int | None = None,
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        max_tables: int | None = 80,
        max_sample_rows: int | None = 3,
    ) -> dict:
        """Inspect native Spring commands, workflow modes, and bounded reference calculation tables."""
        return build_native_spring_workflow_inspection(
            spring_kind=spring_kind,
            command_id=command_id,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            max_tables=max_tables,
            max_sample_rows=max_sample_rows,
        )

    @mcp.tool()
    def probe_native_module_programmatic_access(
        module: str = "Spring",
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        include_registry: bool = True,
        include_exports: bool = True,
        max_registry_keys: int | None = 25_000,
        max_registry_matches: int | None = 40,
        max_exports_per_file: int | None = 120,
    ) -> dict:
        """Probe COM/TypeLib/exports/job evidence for autonomous native-module automation access."""
        return build_native_module_programmatic_access_probe(
            module=module,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            include_registry=include_registry,
            include_exports=include_exports,
            max_registry_keys=max_registry_keys,
            max_registry_matches=max_registry_matches,
            max_exports_per_file=max_exports_per_file,
        )

    @mcp.tool()
    def inspect_native_module_entrypoints(
        module: str = "Spring",
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        include_registry: bool = False,
        max_exports_per_file: int | None = 120,
    ) -> dict:
        """Map native DLL exports to cautious reverse-engineering candidates without calling them."""
        return build_native_module_entrypoint_inspection(
            module=module,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            include_registry=include_registry,
            max_exports_per_file=max_exports_per_file,
        )

    @mcp.tool()
    def plan_native_entrypoint_validation(
        module: str = "Spring",
        export_name: str | None = None,
        command_id: int | str | None = None,
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        max_exports_per_file: int | None = 120,
    ) -> dict:
        """Build a non-executing isolated validation plan for private native exports."""
        return build_native_entrypoint_validation_plan(
            module=module,
            export_name=export_name,
            command_id=command_id,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            max_exports_per_file=max_exports_per_file,
        )

    @mcp.tool()
    def inspect_native_entrypoint_static_abi(
        module: str = "Spring",
        export_name: str | None = None,
        command_id: int | str | None = None,
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        max_exports_per_file: int | None = 120,
        max_import_dlls: int | None = 80,
        max_imports_per_dll: int | None = 80,
    ) -> dict:
        """Parse static PE ABI evidence for selected private native exports without loading DLLs."""
        return build_native_entrypoint_static_abi_inspection(
            module=module,
            export_name=export_name,
            command_id=command_id,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            max_exports_per_file=max_exports_per_file,
            max_import_dlls=max_import_dlls,
            max_imports_per_dll=max_imports_per_dll,
        )

    @mcp.tool()
    def probe_native_entrypoint_loader(
        module: str = "Spring",
        export_name: str | None = None,
        command_id: int | str | None = None,
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        max_exports_per_file: int | None = 120,
        max_import_dlls: int | None = 80,
        max_imports_per_dll: int | None = 80,
        timeout_seconds: int | None = 10,
        confirm_load: bool = False,
    ) -> dict:
        """Load an approved KOMPAS DLL in a child process and resolve one export without calling it."""
        return build_native_entrypoint_loader_probe(
            module=module,
            export_name=export_name,
            command_id=command_id,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            max_exports_per_file=max_exports_per_file,
            max_import_dlls=max_import_dlls,
            max_imports_per_dll=max_imports_per_dll,
            timeout_seconds=timeout_seconds,
            confirm_load=confirm_load,
        )

    @mcp.tool()
    def probe_native_entrypoint_loader_hosted(
        module: str = "Spring",
        export_name: str | None = None,
        command_id: int | str | None = None,
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        max_exports_per_file: int | None = 120,
        max_import_dlls: int | None = 80,
        max_imports_per_dll: int | None = 80,
        timeout_seconds: int | None = 15,
        confirm_load: bool = False,
    ) -> dict:
        """Load an approved KOMPAS DLL in a fresh bridge process and resolve one export without calling it."""
        return build_native_entrypoint_loader_hosted_probe(
            module=module,
            export_name=export_name,
            command_id=command_id,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            max_exports_per_file=max_exports_per_file,
            max_import_dlls=max_import_dlls,
            max_imports_per_dll=max_imports_per_dll,
            timeout_seconds=timeout_seconds,
            confirm_load=confirm_load,
        )

    @mcp.tool()
    def launch_native_module_command(
        module: str = "Spring",
        command_id: int | str | None = 101,
        command_title: str | None = None,
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        post: bool = True,
        visible: bool = True,
        allow_interactive: bool = False,
    ) -> dict:
        """Preview or interactively launch a registered native KOMPAS module command."""
        return adapter.launch_native_module_command(
            module=module,
            command_id=command_id,
            command_title=command_title,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            post=post,
            visible=visible,
            allow_interactive=allow_interactive,
        )

    @mcp.tool()
    def capture_native_module_result(
        module: str = "Spring",
        command_id: int | str | None = 101,
        command_title: str | None = None,
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        document_id: str | None = None,
        require_active_document: bool = False,
        include_tree: bool = True,
        include_items: bool = True,
        max_items: int = 25,
    ) -> dict:
        """Read bounded document state after a native module command has completed interactively."""
        return adapter.capture_native_module_result(
            module=module,
            command_id=command_id,
            command_title=command_title,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            document_id=document_id,
            require_active_document=require_active_document,
            include_tree=include_tree,
            include_items=include_items,
            max_items=max_items,
        )

    @mcp.tool()
    def diff_native_module_results(
        before: dict,
        after: dict,
        max_documents: int = 10,
    ) -> dict:
        """Compare two native module readbacks captured before and after an interactive workflow."""
        return adapter.diff_native_module_results(
            before,
            after,
            max_documents=max_documents,
        )

    @mcp.tool()
    def start_native_module_result_probe(
        module: str = "Spring",
        command_id: int | str | None = 101,
        command_title: str | None = None,
        kompas_root: str | None = None,
        libs_dir: str | None = None,
        include_tree: bool = True,
        include_items: bool = True,
        max_items: int = 25,
        post: bool = True,
        visible: bool = True,
        allow_interactive: bool = False,
    ) -> dict:
        """Capture before-state and optionally launch a native command for manual result probing."""
        return adapter.start_native_module_result_probe(
            module=module,
            command_id=command_id,
            command_title=command_title,
            kompas_root=kompas_root,
            libs_dir=libs_dir,
            include_tree=include_tree,
            include_items=include_items,
            max_items=max_items,
            post=post,
            visible=visible,
            allow_interactive=allow_interactive,
        )
