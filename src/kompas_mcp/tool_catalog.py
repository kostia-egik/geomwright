from __future__ import annotations

from copy import deepcopy
from typing import Any


TOOL_CATEGORIES: list[dict[str, Any]] = [
    {
        "name": "server_guidance",
        "purpose": "Discover the MCP tool surface and choose the right workflow.",
        "tools": ["get_mcp_tool_catalog"],
    },
    {
        "name": "native_modules",
        "purpose": "Inspect installed native KOMPAS application modules and safely launch registered commands when explicitly allowed.",
        "tools": [
            "list_native_modules",
            "inspect_native_module",
            "inspect_native_module_interfaces",
            "inspect_native_spring_workflow",
            "launch_native_module_command",
            "start_native_module_result_probe",
            "capture_native_module_result",
            "diff_native_module_results",
        ],
    },
    {
        "name": "thread_catalog",
        "purpose": "Inspect KOMPAS thread.db standards and resolve thread sizes.",
        "tools": [
            "list_thread_catalog_standards",
            "list_thread_catalog_entries",
            "list_helical_thread_v1_candidates",
            "resolve_thread_catalog_designation",
        ],
    },
    {
        "name": "session_lifecycle",
        "purpose": "Check, open, close, save, and smoke-test KOMPAS documents.",
        "tools": [
            "get_session_state",
            "list_documents",
            "check_file_access",
            "open_document",
            "close_document",
            "shutdown_session",
            "smoke_check_session",
            "save_document",
            "save_document_as",
            "save_export_copy",
        ],
    },
    {
        "name": "low_level_runtime",
        "purpose": "Probe COM readback, classify runtime errors, and verify snapshot deltas.",
        "tools": [
            "preflight_document_context",
            "get_active_document_state",
            "capture_document_snapshot",
            "diff_document_snapshots",
            "verify_document_snapshot_delta",
            "verify_document_readback_stability",
            "classify_runtime_error",
            "normalize_operation_result",
            "create_point3d",
            "create_sketch_line_segment",
            "create_sketch_circle",
            "create_sketch_rectangle",
            "create_sketch_point",
            "create_sketch_polyline",
            "create_sketch_arc",
            "create_sketch_ellipse",
            "create_sketch_entities",
            "parameterize_sketch",
            "list_sketches",
            "rename_sketch",
            "set_sketch_entity_style",
            "delete_sketch_entity",
            "update_sketch_entity_geometry",
            "list_sketch_dimensions",
            "inspect_sketch_dimension",
            "list_sketch_constraints",
            "inspect_sketch_constraint",
            "clear_sketch_entity_constraints",
            "repair_sketch",
            "list_features",
            "inspect_feature",
            "repair_feature",
            "list_sketch_entities",
            "inspect_sketch_entity",
            "probe_document_readback",
            "probe_model_object_collections",
        ],
    },
    {
        "name": "batch_quality",
        "purpose": "Scan model files and run batch lifecycle or quality checks.",
        "tools": [
            "scan_model_files",
            "batch_smoke_check_session",
            "batch_analyze_model_quality",
        ],
    },
    {
        "name": "part_generation",
        "purpose": "Preview or create supported parametric part scenarios.",
        "tools": ["preview_part_scenario", "create_part_from_scenario"],
    },
    {
        "name": "composition_specification",
        "purpose": "Read assembly composition and preview/create/update specifications.",
        "tools": [
            "get_file_composition",
            "get_document_composition",
            "get_specification_descriptions",
            "get_specification",
            "preview_specification_generation",
            "preview_spw_generation",
            "create_spw_from_model",
            "create_specification",
            "preview_specification_changes",
            "apply_specification_changes",
            "preview_specification_autofill",
            "apply_specification_autofill",
            "refresh_specification_from_model",
        ],
    },
    {
        "name": "cleanup_export",
        "purpose": "Apply cleanup rules and export a safe working copy.",
        "tools": ["cleanup_to_export"],
    },
    {
        "name": "relink",
        "purpose": "Preview, plan, and apply assembly component path relinks.",
        "tools": [
            "preview_relink_paths",
            "preview_file_relink_paths",
            "preview_file_relink_map_paths",
            "build_file_relink_plan",
            "build_file_relink_map_plan",
            "preview_relink_map_paths",
            "build_relink_plan",
            "build_relink_map_plan",
            "apply_relink_paths",
            "apply_file_relink_paths",
            "relink_project_root",
            "relink_from_map",
            "relink_to_export",
            "relink_from_map_to_export",
            "relink_file_to_output",
            "relink_file_from_map_to_output",
        ],
    },
    {
        "name": "document_tree_items",
        "purpose": "Read and edit model tree items and item properties.",
        "tools": [
            "get_document_tree",
            "get_items",
            "get_item_properties",
            "preview_property_changes",
            "set_item_properties",
            "find_items",
        ],
    },
    {
        "name": "quality_changesets",
        "purpose": "Analyze naming/spec issues and preview or apply prepared changesets.",
        "tools": [
            "analyze_naming_issues",
            "analyze_spec_issues",
            "preview_changeset",
            "apply_changeset",
        ],
    },
]


def get_mcp_tool_catalog(*, category: str | None = None) -> dict[str, Any]:
    categories = deepcopy(TOOL_CATEGORIES)
    if category is not None:
        categories = [item for item in categories if item["name"] == category]
    tool_count = sum(len(item["tools"]) for item in categories)
    return {
        "ok": bool(categories),
        "category": category,
        "category_count": len(categories),
        "tool_count": tool_count,
        "categories": categories,
    }
