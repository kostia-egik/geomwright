from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .adapter import KompasAdapter
from .analyzers import analyze_naming_issues as run_naming_analysis
from .analyzers import analyze_spec_issues as run_spec_analysis
from .changesets import preview_changeset as build_preview_changeset
from .relink import preview_file_relink_paths as build_file_relink_preview
from .relink import preview_file_relink_map_paths as build_file_relink_map_preview
from .relink import build_file_relink_plan as build_file_relink_plan_payload
from .relink import build_file_relink_map_plan as build_file_relink_map_plan_payload
from .relink import relink_file_from_map_to_output as run_relink_file_from_map_to_output
from .relink import relink_from_map as run_relink_from_map
from .relink import relink_from_map_to_export as run_relink_from_map_to_export
from .relink import relink_project_root as run_relink_project_root
from .relink import relink_file_to_output as run_relink_file_to_output
from .relink import relink_to_export as run_relink_to_export
from .rules import load_rules
from .thread_catalog import list_thread_catalog_standards as build_thread_catalog_standards
from .thread_catalog import list_helical_thread_v1_candidates as build_helical_thread_v1_candidates
from .thread_catalog import list_thread_standard_entries as build_thread_standard_entries
from .thread_catalog import resolve_thread_designation_entry as build_thread_designation_entry
from .tool_catalog import get_mcp_tool_catalog as build_mcp_tool_catalog
from .workflow import cleanup_to_export as run_cleanup_to_export


mcp = FastMCP("kompas-mcp", json_response=True)
adapter = KompasAdapter()


def _rules(rules_path: str | None = None) -> dict:
    return load_rules(rules_path or os.environ.get("KOMPAS_RULES_PATH"))


@mcp.tool()
def get_mcp_tool_catalog(category: str | None = None) -> dict:
    """Return the grouped MCP tool catalog for discoverability."""
    return build_mcp_tool_catalog(category=category)


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


@mcp.tool()
def get_session_state() -> dict:
    """Return KOMPAS connection state and the active document."""
    return adapter.get_session_state()


@mcp.tool()
def list_documents() -> dict:
    """Return open KOMPAS documents."""
    return adapter.list_documents()


@mcp.tool()
def preflight_document_context(
    document_id: str | None = None,
    require_active_document: bool = True,
    expected_document_type: str | int | None = None,
    expected_extensions: list[str] | None = None,
    require_tree: bool = False,
    min_tree_nodes: int = 1,
    require_items: bool = False,
    min_items: int = 1,
) -> dict:
    """Check KOMPAS session/document readiness before running a low-level operation."""
    return adapter.preflight_document_context(
        document_id=document_id,
        require_active_document=require_active_document,
        expected_document_type=expected_document_type,
        expected_extensions=expected_extensions,
        require_tree=require_tree,
        min_tree_nodes=min_tree_nodes,
        require_items=require_items,
        min_items=min_items,
    )


@mcp.tool()
def get_active_document_state(
    document_id: str | None = None,
    require_active_document: bool = True,
    include_tree: bool = False,
    include_items: bool = False,
    max_items: int = 25,
) -> dict:
    """Read bounded active-document state through the primitive operation pipeline."""
    return adapter.get_active_document_state(
        document_id=document_id,
        require_active_document=require_active_document,
        include_tree=include_tree,
        include_items=include_items,
        max_items=max_items,
    )


@mcp.tool()
def capture_document_snapshot(
    model_path: str | None = None,
    document_id: str | None = None,
    output_path: str | None = None,
    require_active_document: bool = True,
    visible: bool = False,
    read_only: bool = True,
    close_after_probe: bool = True,
    include_manifest: bool = False,
) -> dict:
    """Capture a bounded readback snapshot for an active/opened document, optionally writing the full manifest JSON."""
    return adapter.capture_document_snapshot(
        model_path=model_path,
        document_id=document_id,
        output_path=output_path,
        require_active_document=require_active_document,
        visible=visible,
        read_only=read_only,
        close_after_probe=close_after_probe,
        include_manifest=include_manifest,
    )


@mcp.tool()
def diff_document_snapshots(
    before: dict | str,
    after: dict | str,
    max_items: int = 25,
    ignore_paths: list[str] | None = None,
    ignore_keys: list[str] | None = None,
    use_default_volatile_ignores: bool = False,
) -> dict:
    """Compare two readback snapshot/manifest payloads or JSON artifact paths with bounded item deltas."""
    return adapter.diff_document_snapshots(
        before,
        after,
        max_items=max_items,
        ignore_paths=ignore_paths,
        ignore_keys=ignore_keys,
        use_default_volatile_ignores=use_default_volatile_ignores,
    )


@mcp.tool()
def verify_document_snapshot_delta(
    operation: str,
    before: dict | str | None = None,
    after: dict | str | None = None,
    diff: dict | None = None,
    expected_added: int | None = None,
    expected_removed: int | None = None,
    expected_changed: int | None = None,
    min_added: int | None = None,
    min_removed: int | None = None,
    min_changed: int | None = None,
    max_added: int | None = None,
    max_removed: int | None = None,
    max_changed: int | None = None,
    require_no_removed: bool = False,
    require_no_changed: bool = False,
    expected_counts_delta: dict[str, int | float] | None = None,
    max_items: int = 25,
    ignore_paths: list[str] | None = None,
    ignore_keys: list[str] | None = None,
    use_default_volatile_ignores: bool = False,
) -> dict:
    """Verify expected before/after readback snapshot deltas for a primitive operation."""
    return adapter.verify_document_snapshot_delta(
        operation,
        before=before,
        after=after,
        diff=diff,
        expected_added=expected_added,
        expected_removed=expected_removed,
        expected_changed=expected_changed,
        min_added=min_added,
        min_removed=min_removed,
        min_changed=min_changed,
        max_added=max_added,
        max_removed=max_removed,
        max_changed=max_changed,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        expected_counts_delta=expected_counts_delta,
        max_items=max_items,
        ignore_paths=ignore_paths,
        ignore_keys=ignore_keys,
        use_default_volatile_ignores=use_default_volatile_ignores,
    )


@mcp.tool()
def verify_document_readback_stability(
    document_id: str | None = None,
    before_output_path: str | None = None,
    after_output_path: str | None = None,
    require_active_document: bool = True,
    max_items: int = 25,
    include_manifests: bool = False,
    ignore_paths: list[str] | None = None,
    ignore_keys: list[str] | None = None,
    use_default_volatile_ignores: bool = False,
) -> dict:
    """Capture two readback snapshots and verify that document readback is stable before write/read checks."""
    return adapter.verify_document_readback_stability(
        document_id=document_id,
        before_output_path=before_output_path,
        after_output_path=after_output_path,
        require_active_document=require_active_document,
        max_items=max_items,
        include_manifests=include_manifests,
        ignore_paths=ignore_paths,
        ignore_keys=ignore_keys,
        use_default_volatile_ignores=use_default_volatile_ignores,
    )


@mcp.tool()
def classify_runtime_error(
    message: str,
    exception_type: str | None = None,
    stage: str | None = None,
) -> dict:
    """Classify a KOMPAS/COM runtime error into a stable code, category, and recovery hint."""
    return adapter.classify_runtime_error(message, exception_type=exception_type, stage=stage)


@mcp.tool()
def normalize_operation_result(
    operation: str,
    result: dict | None = None,
    preflight: dict | None = None,
    readback_contract: dict | None = None,
    checks: list[dict] | None = None,
    error: str | None = None,
    exception_type: str | None = None,
    artifacts: dict[str, str] | None = None,
    stage: str = "operation_result",
    require_result: bool = True,
) -> dict:
    """Normalize a primitive operation result, preflight/readback checks, and optional error into one envelope."""
    return adapter.normalize_operation_result(
        operation,
        result=result,
        preflight=preflight,
        readback_contract=readback_contract,
        checks=checks,
        error=error,
        exception_type=exception_type,
        artifacts=artifacts,
        stage=stage,
        require_result=require_result,
    )


@mcp.tool()
def create_point3d(
    document_id: str | None = None,
    name: str = "PT1",
    origin: list[float] | None = None,
    min_added: int = 1,
    require_no_removed: bool = True,
    require_no_changed: bool = False,
    max_items: int = 25,
) -> dict:
    """Create a 3D point in the active part and verify the before/after snapshot delta."""
    return adapter.create_point3d(
        document_id=document_id,
        name=name,
        origin=origin,
        min_added=min_added,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        max_items=max_items,
    )


@mcp.tool()
def create_sketch_line_segment(
    document_id: str | None = None,
    name: str = "SKETCH_LINE_1",
    plane: str = "XOY",
    start: list[float] | None = None,
    end: list[float] | None = None,
    sketch_ref: str | None = None,
    create_new_sketch: bool = True,
    line_style: int = 1,
    min_added: int = 1,
    require_no_removed: bool = True,
    require_no_changed: bool = False,
    max_items: int = 25,
) -> dict:
    """Create a sketch with one 2D line segment and verify the before/after snapshot delta."""
    return adapter.create_sketch_line_segment(
        document_id=document_id,
        name=name,
        plane=plane,
        start=start,
        end=end,
        sketch_ref=sketch_ref,
        create_new_sketch=create_new_sketch,
        line_style=line_style,
        min_added=min_added,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        max_items=max_items,
    )


@mcp.tool()
def create_sketch_circle(
    document_id: str | None = None,
    name: str = "SKETCH_CIRCLE_1",
    plane: str = "XOY",
    center: list[float] | None = None,
    radius: float = 10.0,
    sketch_ref: str | None = None,
    create_new_sketch: bool = True,
    line_style: int = 1,
    min_added: int = 1,
    require_no_removed: bool = True,
    require_no_changed: bool = False,
    max_items: int = 25,
) -> dict:
    """Create a sketch with one 2D circle and verify the before/after snapshot delta."""
    return adapter.create_sketch_circle(
        document_id=document_id,
        name=name,
        plane=plane,
        center=center,
        radius=radius,
        sketch_ref=sketch_ref,
        create_new_sketch=create_new_sketch,
        line_style=line_style,
        min_added=min_added,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        max_items=max_items,
    )


@mcp.tool()
def create_sketch_rectangle(
    document_id: str | None = None,
    name: str = "SKETCH_RECTANGLE_1",
    plane: str = "XOY",
    corner1: list[float] | None = None,
    corner2: list[float] | None = None,
    sketch_ref: str | None = None,
    create_new_sketch: bool = True,
    line_style: int = 1,
    min_added: int = 1,
    require_no_removed: bool = True,
    require_no_changed: bool = False,
    max_items: int = 25,
) -> dict:
    """Create a sketch rectangle from two corners and verify the before/after snapshot delta."""
    return adapter.create_sketch_rectangle(
        document_id=document_id,
        name=name,
        plane=plane,
        corner1=corner1,
        corner2=corner2,
        sketch_ref=sketch_ref,
        create_new_sketch=create_new_sketch,
        line_style=line_style,
        min_added=min_added,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        max_items=max_items,
    )


@mcp.tool()
def create_sketch_point(
    document_id: str | None = None,
    name: str = "SKETCH_POINT_1",
    plane: str = "XOY",
    point: list[float] | None = None,
    sketch_ref: str | None = None,
    create_new_sketch: bool = True,
    line_style: int = 1,
    min_added: int = 1,
    require_no_removed: bool = False,
    require_no_changed: bool = False,
    max_items: int = 25,
) -> dict:
    """Create one 2D sketch point in a new or existing sketch and verify the snapshot delta."""
    return adapter.create_sketch_point(
        document_id=document_id,
        name=name,
        plane=plane,
        point=point,
        sketch_ref=sketch_ref,
        create_new_sketch=create_new_sketch,
        line_style=line_style,
        min_added=min_added,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        max_items=max_items,
    )


@mcp.tool()
def create_sketch_polyline(
    document_id: str | None = None,
    name: str = "SKETCH_POLYLINE_1",
    plane: str = "XOY",
    points: list[list[float]] | None = None,
    closed: bool = False,
    sketch_ref: str | None = None,
    create_new_sketch: bool = True,
    line_style: int = 1,
    min_added: int = 1,
    require_no_removed: bool = False,
    require_no_changed: bool = False,
    max_items: int = 25,
) -> dict:
    """Create one 2D sketch polyline in a new or existing sketch and verify the snapshot delta."""
    return adapter.create_sketch_polyline(
        document_id=document_id,
        name=name,
        plane=plane,
        points=points,
        closed=closed,
        sketch_ref=sketch_ref,
        create_new_sketch=create_new_sketch,
        line_style=line_style,
        min_added=min_added,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        max_items=max_items,
    )


@mcp.tool()
def create_sketch_arc(
    document_id: str | None = None,
    name: str = "SKETCH_ARC_1",
    plane: str = "XOY",
    center: list[float] | None = None,
    radius: float = 10.0,
    start: list[float] | None = None,
    end: list[float] | None = None,
    direction: bool = True,
    sketch_ref: str | None = None,
    create_new_sketch: bool = True,
    line_style: int = 1,
    min_added: int = 1,
    require_no_removed: bool = False,
    require_no_changed: bool = False,
    max_items: int = 25,
) -> dict:
    """Create one 2D sketch arc in a new or existing sketch and verify the snapshot delta."""
    return adapter.create_sketch_arc(
        document_id=document_id,
        name=name,
        plane=plane,
        center=center,
        radius=radius,
        start=start,
        end=end,
        direction=direction,
        sketch_ref=sketch_ref,
        create_new_sketch=create_new_sketch,
        line_style=line_style,
        min_added=min_added,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        max_items=max_items,
    )


@mcp.tool()
def create_sketch_ellipse(
    document_id: str | None = None,
    name: str = "SKETCH_ELLIPSE_1",
    plane: str = "XOY",
    center: list[float] | None = None,
    radius_x: float = 10.0,
    radius_y: float = 5.0,
    angle: float = 0.0,
    sketch_ref: str | None = None,
    create_new_sketch: bool = True,
    line_style: int = 1,
    min_added: int = 1,
    require_no_removed: bool = False,
    require_no_changed: bool = False,
    max_items: int = 25,
) -> dict:
    """Create one 2D sketch ellipse in a new or existing sketch and verify the snapshot delta."""
    return adapter.create_sketch_ellipse(
        document_id=document_id,
        name=name,
        plane=plane,
        center=center,
        radius_x=radius_x,
        radius_y=radius_y,
        angle=angle,
        sketch_ref=sketch_ref,
        create_new_sketch=create_new_sketch,
        line_style=line_style,
        min_added=min_added,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        max_items=max_items,
    )


@mcp.tool()
def create_sketch_entities(
    document_id: str | None = None,
    name: str = "SKETCH_BATCH_1",
    plane: str = "XOY",
    entities: list[dict] | None = None,
    sketch_ref: str | None = None,
    create_new_sketch: bool = True,
    constraints: list[dict] | None = None,
    dimensions: list[dict] | None = None,
    sketch_options: dict | None = None,
    min_added: int = 1,
    require_no_removed: bool = False,
    require_no_changed: bool = False,
    max_items: int = 25,
) -> dict:
    """Create several 2D sketch entities in one target sketch and verify the snapshot delta."""
    return adapter.create_sketch_entities(
        document_id=document_id,
        name=name,
        plane=plane,
        entities=entities,
        sketch_ref=sketch_ref,
        create_new_sketch=create_new_sketch,
        constraints=constraints,
        dimensions=dimensions,
        sketch_options=sketch_options,
        min_added=min_added,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        max_items=max_items,
    )


@mcp.tool()
def parameterize_sketch(
    document_id: str | None = None,
    sketch_ref: str | None = None,
    entities: list[dict] | None = None,
    constraints: list[dict] | None = None,
    dimensions: list[dict] | None = None,
    sketch_options: dict | None = None,
    require_no_removed: bool = False,
    require_no_changed: bool = False,
    max_items: int = 25,
) -> dict:
    """Apply constraints/dimensions to existing sketch entities selected by reference, index, or fingerprint."""
    return adapter.parameterize_sketch(
        document_id=document_id,
        sketch_ref=sketch_ref,
        entities=entities,
        constraints=constraints,
        dimensions=dimensions,
        sketch_options=sketch_options,
        require_no_removed=require_no_removed,
        require_no_changed=require_no_changed,
        max_items=max_items,
    )


@mcp.tool()
def list_sketch_entities(
    document_id: str | None = None,
    sketch_ref: str | None = None,
    kinds: list[str] | str | None = None,
    max_items: int = 100,
) -> dict:
    """List existing sketch entities with reference, index, fingerprint, and geometry selectors."""
    return adapter.list_sketch_entities(
        document_id=document_id,
        sketch_ref=sketch_ref,
        kinds=kinds,
        max_items=max_items,
    )


@mcp.tool()
def inspect_sketch_entity(
    document_id: str | None = None,
    sketch_ref: str | None = None,
    entity: dict | None = None,
) -> dict:
    """Inspect one existing sketch entity selected by reference, index, or fingerprint."""
    return adapter.inspect_sketch_entity(
        document_id=document_id,
        sketch_ref=sketch_ref,
        entity=entity,
    )


@mcp.tool()
def check_file_access(path: str) -> dict:
    """Check whether a file is visible and can be opened exclusively by this process."""
    return adapter.check_file_access(path)


@mcp.tool()
def open_document(path: str, visible: bool = True, read_only: bool = False) -> dict:
    """Open a document inside the automation-controlled KOMPAS instance."""
    return adapter.open_document(path=path, visible=visible, read_only=read_only)


@mcp.tool()
def close_document(document_id: str | None = None, save: bool = False, close_mode: int = 0) -> dict:
    """Close the selected or active document, optionally saving it first."""
    return adapter.close_document(document_id=document_id, save=save, close_mode=close_mode)


@mcp.tool()
def shutdown_session(save: bool = False, close_mode: int = 0) -> dict:
    """Close all open documents in the automation instance and try to quit KOMPAS."""
    return adapter.shutdown_session(save=save, close_mode=close_mode)


@mcp.tool()
def smoke_check_session(path: str, output_dir: str | None = None, visible: bool = False) -> dict:
    """Open, save-as-close, reopen-readonly and close a KOMPAS document to verify lifecycle handling."""
    return adapter.smoke_check_session(path=path, output_dir=output_dir, visible=visible)


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
        rules=_rules(rules_path),
        continue_on_error=continue_on_error,
        report_dir=report_dir,
        report_name=report_name,
        report_formats=report_formats,
    )


@mcp.tool()
def preview_part_scenario(scenario: str, params: dict) -> dict:
    """Preview a parametric part scenario without creating a KOMPAS document."""
    return adapter.preview_part_scenario(scenario=scenario, params=params)


@mcp.tool()
def create_part_from_scenario(
    scenario: str,
    params: dict,
    output_path: str | None = None,
    visible: bool = False,
    close_after_save: bool | None = None,
) -> dict:
    """Create a KOMPAS part from a supported parametric scenario such as stepped_shaft."""
    return adapter.create_part_from_scenario(
        scenario=scenario,
        params=params,
        output_path=output_path,
        visible=visible,
        close_after_save=close_after_save,
    )


@mcp.tool()
def get_file_composition(assembly_path: str) -> dict:
    """Read the stored composition of an assembly file directly from the file itself."""
    return adapter.get_file_composition(assembly_path)


@mcp.tool()
def get_document_composition(document_id: str | None = None) -> dict:
    """Read the stored composition of the selected or active saved document."""
    return adapter.get_document_composition(document_id=document_id)


@mcp.tool()
def get_specification_descriptions(document_id: str | None = None) -> dict:
    """List available specification descriptions for the selected or active document."""
    return adapter.get_specification_descriptions(document_id=document_id)


@mcp.tool()
def get_specification(
    document_id: str | None = None,
    description_index: int | None = None,
    layout_name: str | None = None,
    include_objects: bool = True,
    max_objects: int = 200,
) -> dict:
    """Read the active or selected specification description with its objects and columns."""
    return adapter.get_specification(
        document_id=document_id,
        description_index=description_index,
        layout_name=layout_name,
        include_objects=include_objects,
        max_objects=max_objects,
    )


@mcp.tool()
def preview_specification_generation(
    document_id: str | None = None,
    include_root: bool = False,
) -> dict:
    """Build a practical specification preview from the assembly tree."""
    return adapter.preview_specification_generation(
        document_id=document_id,
        include_root=include_root,
    )


@mcp.tool()
def preview_spw_generation(
    document_id: str | None = None,
    include_root: bool = False,
    columns: list[dict] | None = None,
    include_engineering: bool = False,
    column_preset: str | None = None,
) -> dict:
    """Build a preview for a separate .spw specification document from the assembly tree.

    columns maps row fields to .spw columns: field, column_type, block_number,
    column_number, skip_unit_value. column_preset can be default/base or
    engineering_comment_columns. Engineering fields require explicit opt-in.
    """
    return adapter.preview_spw_generation(
        document_id=document_id,
        include_root=include_root,
        columns=columns,
        include_engineering=include_engineering,
        column_preset=column_preset,
    )


@mcp.tool()
def create_spw_from_model(
    document_id: str | None = None,
    output_path: str | None = None,
    include_root: bool = False,
    layout_name: str = "graphic.lyt",
    style_id: int = 1,
    columns: list[dict] | None = None,
    include_engineering: bool = False,
    column_preset: str | None = None,
) -> dict:
    """Create a separate .spw specification document from the current model tree.

    By default writes only position, designation, title, quantity, comment.
    Engineering fields are written only when mapped by columns and opted in.
    """
    return adapter.create_spw_from_model(
        document_id=document_id,
        output_path=output_path,
        include_root=include_root,
        layout_name=layout_name,
        style_id=style_id,
        columns=columns,
        include_engineering=include_engineering,
        column_preset=column_preset,
    )


@mcp.tool()
def create_specification(
    document_id: str | None = None,
    include_root: bool = False,
    replace_existing: bool = False,
    save: bool = False,
    close_after_save: bool = False,
    layout_name: str = "",
    style_id: int = 0,
    specification_name: str = "",
) -> dict:
    """Create a specification description and fill rows from the current assembly tree."""
    return adapter.create_specification(
        document_id=document_id,
        include_root=include_root,
        replace_existing=replace_existing,
        save=save,
        close_after_save=close_after_save,
        layout_name=layout_name,
        style_id=style_id,
        specification_name=specification_name,
    )


@mcp.tool()
def preview_specification_changes(
    updates: list[dict],
    document_id: str | None = None,
    description_index: int | None = None,
    layout_name: str | None = None,
    max_objects: int = 2000,
) -> dict:
    """Preview edits for existing specification rows by object_id and standard fields."""
    return adapter.preview_specification_changes(
        updates=updates,
        document_id=document_id,
        description_index=description_index,
        layout_name=layout_name,
        max_objects=max_objects,
    )


@mcp.tool()
def apply_specification_changes(
    updates: list[dict],
    document_id: str | None = None,
    description_index: int | None = None,
    layout_name: str | None = None,
    save: bool = False,
    close_after_save: bool = False,
    max_objects: int = 2000,
) -> dict:
    """Apply edits to existing specification rows by object_id and standard fields."""
    return adapter.apply_specification_changes(
        updates=updates,
        document_id=document_id,
        description_index=description_index,
        layout_name=layout_name,
        save=save,
        close_after_save=close_after_save,
        max_objects=max_objects,
    )


@mcp.tool()
def preview_specification_autofill(
    document_id: str | None = None,
    description_index: int | None = None,
    layout_name: str | None = None,
    include_root: bool = False,
    fields: list[str] | None = None,
    fill_only: bool = False,
    max_objects: int = 2000,
) -> dict:
    """Build a safe preview of filling or syncing specification rows from the model tree."""
    return adapter.preview_specification_autofill(
        document_id=document_id,
        description_index=description_index,
        layout_name=layout_name,
        include_root=include_root,
        fields=fields,
        fill_only=fill_only,
        max_objects=max_objects,
    )


@mcp.tool()
def apply_specification_autofill(
    document_id: str | None = None,
    description_index: int | None = None,
    layout_name: str | None = None,
    include_root: bool = False,
    fields: list[str] | None = None,
    fill_only: bool = False,
    save: bool = False,
    close_after_save: bool = False,
    max_objects: int = 2000,
) -> dict:
    """Apply filling or syncing of specification rows from the model tree."""
    return adapter.apply_specification_autofill(
        document_id=document_id,
        description_index=description_index,
        layout_name=layout_name,
        include_root=include_root,
        fields=fields,
        fill_only=fill_only,
        save=save,
        close_after_save=close_after_save,
        max_objects=max_objects,
    )


@mcp.tool()
def refresh_specification_from_model(
    document_id: str | None = None,
    include_root: bool = False,
    replace_existing: bool = True,
    save: bool = False,
    close_after_save: bool = False,
    layout_name: str = "",
    style_id: int = 0,
    specification_name: str = "",
    fields: list[str] | None = None,
    fill_only: bool = False,
    max_objects: int = 2000,
) -> dict:
    """Recreate the active specification from the model and then apply safe autofill for supported fields."""
    return adapter.refresh_specification_from_model(
        document_id=document_id,
        include_root=include_root,
        replace_existing=replace_existing,
        save=save,
        close_after_save=close_after_save,
        layout_name=layout_name,
        style_id=style_id,
        specification_name=specification_name,
        fields=fields,
        fill_only=fill_only,
        max_objects=max_objects,
    )


@mcp.tool()
def save_document(document_id: str | None = None, close_after_save: bool = True) -> dict:
    """Save the selected or active document."""
    return adapter.save_document(document_id=document_id, close_after_save=close_after_save)


@mcp.tool()
def save_document_as(path: str, document_id: str | None = None, close_after_save: bool = True) -> dict:
    """Save the selected or active document to a new file path."""
    return adapter.save_document_as(path=path, document_id=document_id, close_after_save=close_after_save)


@mcp.tool()
def save_export_copy(document_id: str | None = None, suffix: str = "codex", close_after_save: bool = True) -> dict:
    """Save the active document to the default export directory with an ASCII-safe file name."""
    return adapter.save_export_copy(
        document_id=document_id,
        suffix=suffix,
        close_after_save=close_after_save,
    )


@mcp.tool()
def cleanup_to_export(document_id: str | None = None, suffix: str = "clean", rules_path: str | None = None) -> dict:
    """Apply the current cleanup rules, export a working copy, and write a report next to it."""
    return run_cleanup_to_export(adapter, _rules(rules_path), document_id=document_id, suffix=suffix)


@mcp.tool()
def preview_relink_paths(document_id: str | None = None, search_root: str = "", relink_all: bool = False) -> dict:
    """Find candidate component path updates by searching for matching filenames under a new root."""
    composition_payload = adapter.get_document_composition(document_id=document_id)
    return {
        "document": composition_payload["document"],
        "assembly_path": composition_payload["assembly_path"],
        **build_file_relink_preview(composition_payload["assembly_path"], search_root, relink_all=relink_all),
    }


@mcp.tool()
def preview_file_relink_paths(assembly_path: str, search_root: str, relink_all: bool = False) -> dict:
    """Preview persistent relinks by reading the Sources entry of an assembly file directly."""
    return build_file_relink_preview(assembly_path=assembly_path, search_root=search_root, relink_all=relink_all)


@mcp.tool()
def preview_file_relink_map_paths(assembly_path: str, mapping_path: str) -> dict:
    """Preview relinks for a file assembly from an explicit mapping file."""
    return build_file_relink_map_preview(assembly_path=assembly_path, mapping_path=mapping_path)


@mcp.tool()
def build_file_relink_plan(assembly_path: str, search_root: str, relink_all: bool = False) -> dict:
    """Build a grouped actionable relink plan for an assembly file."""
    return build_file_relink_plan_payload(
        assembly_path=assembly_path,
        search_root=search_root,
        relink_all=relink_all,
    )


@mcp.tool()
def build_file_relink_map_plan(assembly_path: str, mapping_path: str) -> dict:
    """Build a grouped actionable relink plan from an explicit mapping file."""
    return build_file_relink_map_plan_payload(
        assembly_path=assembly_path,
        mapping_path=mapping_path,
    )


@mcp.tool()
def preview_relink_map_paths(document_id: str | None = None, mapping_path: str = "") -> dict:
    """Preview relinks from an explicit old->new mapping file, useful when files were also renamed."""
    composition_payload = adapter.get_document_composition(document_id=document_id)
    return {
        "document": composition_payload["document"],
        "assembly_path": composition_payload["assembly_path"],
        **build_file_relink_map_preview(composition_payload["assembly_path"], mapping_path),
    }


@mcp.tool()
def build_relink_plan(document_id: str | None = None, search_root: str = "", relink_all: bool = False) -> dict:
    """Build a grouped actionable relink plan for the selected or active document."""
    composition_payload = adapter.get_document_composition(document_id=document_id)
    return {
        "document": composition_payload["document"],
        **build_file_relink_plan_payload(
            assembly_path=composition_payload["assembly_path"],
            search_root=search_root,
            relink_all=relink_all,
        ),
    }


@mcp.tool()
def build_relink_map_plan(document_id: str | None = None, mapping_path: str = "") -> dict:
    """Build a grouped actionable relink plan for the selected or active document from a mapping file."""
    composition_payload = adapter.get_document_composition(document_id=document_id)
    return {
        "document": composition_payload["document"],
        **build_file_relink_map_plan_payload(
            assembly_path=composition_payload["assembly_path"],
            mapping_path=mapping_path,
        ),
    }


@mcp.tool()
def apply_relink_paths(
    changes: list[dict],
    document_id: str | None = None,
    save: bool = False,
    close_after_save: bool = False,
) -> dict:
    """Apply component source-path relinks to the selected or active assembly."""
    return adapter.apply_relink_paths(
        changes=changes,
        document_id=document_id,
        save=save,
        close_after_save=close_after_save,
    )


@mcp.tool()
def apply_file_relink_paths(
    assembly_path: str,
    changes: list[dict],
    output_path: str | None = None,
) -> dict:
    """Apply relinks to an assembly file through KOMPAS itself and save the result to the target path."""
    return adapter.relink_document_file(assembly_path=assembly_path, changes=changes, output_path=output_path)


@mcp.tool()
def relink_project_root(
    search_root: str,
    document_id: str | None = None,
    relink_all: bool = False,
    save: bool = False,
) -> dict:
    """Preview and apply assembly relinks by matching component filenames under a new root."""
    return run_relink_project_root(
        adapter,
        search_root=search_root,
        document_id=document_id,
        relink_all=relink_all,
        save=save,
    )


@mcp.tool()
def relink_from_map(
    mapping_path: str,
    document_id: str | None = None,
    save: bool = False,
) -> dict:
    """Preview and apply assembly relinks from an explicit mapping file."""
    return run_relink_from_map(
        adapter,
        mapping_path=mapping_path,
        document_id=document_id,
        save=save,
    )


@mcp.tool()
def relink_to_export(
    search_root: str,
    document_id: str | None = None,
    relink_all: bool = False,
    suffix: str = "relinked",
) -> dict:
    """Preview and apply assembly relinks, then save a safe exported copy with a relink report."""
    return run_relink_to_export(
        adapter,
        search_root=search_root,
        document_id=document_id,
        relink_all=relink_all,
        suffix=suffix,
    )


@mcp.tool()
def relink_from_map_to_export(
    mapping_path: str,
    document_id: str | None = None,
    suffix: str = "relinked",
) -> dict:
    """Apply relinks from an explicit mapping file and save a safe exported copy with a report."""
    return run_relink_from_map_to_export(
        adapter,
        mapping_path=mapping_path,
        document_id=document_id,
        suffix=suffix,
    )


@mcp.tool()
def relink_file_to_output(
    assembly_path: str,
    search_root: str,
    output_path: str,
    relink_all: bool = False,
) -> dict:
    """Preview and apply assembly relinks to a copied file through KOMPAS itself."""
    return run_relink_file_to_output(
        adapter,
        assembly_path=assembly_path,
        search_root=search_root,
        output_path=output_path,
        relink_all=relink_all,
    )


@mcp.tool()
def relink_file_from_map_to_output(
    assembly_path: str,
    mapping_path: str,
    output_path: str,
) -> dict:
    """Apply relinks from an explicit mapping file to a copied assembly through KOMPAS itself."""
    return run_relink_file_from_map_to_output(
        adapter,
        assembly_path=assembly_path,
        mapping_path=mapping_path,
        output_path=output_path,
    )


@mcp.tool()
def get_document_tree(document_id: str | None = None) -> dict:
    """Return the assembly/model tree for the selected or active document."""
    return adapter.get_document_tree(document_id=document_id)


@mcp.tool()
def get_items(document_id: str | None = None, item_ids: list[str] | None = None) -> dict:
    """Return selected tree items with their current properties."""
    return adapter.get_items(document_id=document_id, item_ids=item_ids)


@mcp.tool()
def probe_model_object_collections(
    document_id: str | None = None,
    max_items: int = 5,
    include_empty: bool = True,
) -> dict:
    """Probe known sketch/feature collections exposed by the selected or active 3D document."""
    return adapter.probe_model_object_collections(
        document_id=document_id,
        max_items=max_items,
        include_empty=include_empty,
    )


@mcp.tool()
def probe_document_readback(
    model_path: str | None = None,
    document_id: str | None = None,
    output_path: str | None = None,
    visible: bool = False,
    read_only: bool = True,
    close_after_probe: bool = True,
) -> dict:
    """Collect a low-level COM readback manifest for an opened file or active document."""
    return adapter.probe_document_readback(
        model_path=model_path,
        document_id=document_id,
        output_path=output_path,
        visible=visible,
        read_only=read_only,
        close_after_probe=close_after_probe,
    )


@mcp.tool()
def get_item_properties(document_id: str | None = None, item_ids: list[str] | None = None) -> dict:
    """Return a practical properties snapshot for selected items."""
    return adapter.get_item_properties(document_id=document_id, item_ids=item_ids)


@mcp.tool()
def preview_property_changes(
    updates: list[dict],
    document_id: str | None = None,
) -> dict:
    """Preview direct property edits for writable item fields."""
    return adapter.preview_property_changes(updates=updates, document_id=document_id)


@mcp.tool()
def set_item_properties(
    updates: list[dict],
    document_id: str | None = None,
    save: bool = False,
    close_after_save: bool = False,
) -> dict:
    """Apply direct property edits for writable item fields."""
    return adapter.set_item_properties(
        updates=updates,
        document_id=document_id,
        save=save,
        close_after_save=close_after_save,
    )


@mcp.tool()
def find_items(
    document_id: str | None = None,
    query: str = "",
    kinds: list[str] | None = None,
) -> dict:
    """Search items by text and optional kinds."""
    return adapter.find_items(document_id=document_id, query=query, kinds=kinds)


@mcp.tool()
def analyze_naming_issues(document_id: str | None = None, rules_path: str | None = None) -> dict:
    """Analyze naming issues in the selected or active document."""
    tree_payload = adapter.get_document_tree(document_id=document_id)
    result = run_naming_analysis(tree_payload["tree"], _rules(rules_path))
    return {
        "document": tree_payload["document"],
        **result.to_dict(),
    }


@mcp.tool()
def analyze_spec_issues(document_id: str | None = None, rules_path: str | None = None) -> dict:
    """Analyze basic specification issues in the selected or active document."""
    tree_payload = adapter.get_document_tree(document_id=document_id)
    result = run_spec_analysis(tree_payload["tree"], _rules(rules_path))
    return {
        "document": tree_payload["document"],
        **result.to_dict(),
    }


@mcp.tool()
def preview_changeset(document_id: str | None = None, rules_path: str | None = None) -> dict:
    """Build a safe preview of name and designation changes."""
    tree_payload = adapter.get_document_tree(document_id=document_id)
    return build_preview_changeset(tree_payload["document"], tree_payload["tree"], _rules(rules_path))


@mcp.tool()
def apply_changeset(
    changes: list[dict],
    document_id: str | None = None,
    save: bool = False,
    close_after_save: bool = False,
) -> dict:
    """Apply a prepared changeset to writable fields only."""
    return adapter.apply_changeset(
        changes=changes,
        document_id=document_id,
        save=save,
        close_after_save=close_after_save,
    )


def main() -> None:
    mcp.run()
