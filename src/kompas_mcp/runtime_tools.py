from __future__ import annotations

from typing import Any


def register_runtime_tools(mcp: Any, adapter: Any) -> None:
    """Register low-level document readback and operation-normalization tools."""

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
    def probe_model_formulas(
        model_path: str | None = None,
        document_id: str | None = None,
        output_path: str | None = None,
        visible: bool = False,
        read_only: bool = True,
        close_after_probe: bool = True,
        include_contents_fallback: bool = True,
    ) -> dict:
        """Probe formula-bearing sketch dimensions, constraints, and feature variables."""
        return adapter.probe_model_formulas(
            model_path=model_path,
            document_id=document_id,
            output_path=output_path,
            visible=visible,
            read_only=read_only,
            close_after_probe=close_after_probe,
            include_contents_fallback=include_contents_fallback,
        )
