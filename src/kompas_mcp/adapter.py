from __future__ import annotations

import ctypes
import os
import re
import uuid
from pathlib import Path
from typing import Any

from .batch import build_file_list
from .batch import scan_model_files as scan_model_files_payload
from .batch import summarize_batch_results
from .bridge_runner import BridgeRunner
from .analyzers import analyze_naming_issues
from .analyzers import analyze_spec_issues
from .composition import read_file_composition
from .document_preflight import preflight_document_context as build_document_preflight
from .document_probe import probe_document_readback as build_document_readback_probe
from .document_snapshot import capture_document_snapshot as build_document_snapshot
from .document_snapshot_diff import diff_document_snapshots as build_document_snapshot_diff
from .document_snapshot_verify import verify_document_snapshot_delta as build_document_snapshot_delta_verification
from .document_stability import verify_document_readback_stability as build_document_readback_stability
from .document_state import get_active_document_state as build_active_document_state
from .operation_result import normalize_operation_result as build_operation_result_envelope
from .properties import get_item_properties as build_item_properties
from .properties import preview_property_changes as build_property_preview
from .parametric import preview_part_scenario as build_part_scenario_preview
from .reports import write_batch_report
from .runtime_errors import classify_runtime_error as build_runtime_error_classification
from .specification import build_specification_autofill_preview
from .specification import build_specification_preview
from .specification import resolve_spw_columns
from .specification import preview_specification_changes as build_specification_changes_preview
from .specification import SPW_ENGINEERING_FIELDS
from .vbs_relink import run_vbs_file_relink


def flatten_tree(root: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def walk(node: dict[str, Any]) -> None:
        items.append(node)
        for child in node.get("children", []):
            walk(child)

    walk(root)
    return items


class KompasAdapter:
    def __init__(self, runner: BridgeRunner | None = None) -> None:
        self.runner = runner or BridgeRunner()

    def get_session_state(self) -> dict[str, Any]:
        return self.runner.call("get_session_state")

    def list_documents(self) -> dict[str, Any]:
        return self.runner.call("list_documents")

    def preflight_document_context(
        self,
        document_id: str | None = None,
        *,
        require_active_document: bool = True,
        expected_document_type: str | int | None = None,
        expected_extensions: list[str] | tuple[str, ...] | None = None,
        require_tree: bool = False,
        min_tree_nodes: int = 1,
        require_items: bool = False,
        min_items: int = 1,
    ) -> dict[str, Any]:
        return build_document_preflight(
            self,
            document_id=document_id,
            require_active_document=require_active_document,
            expected_document_type=expected_document_type,
            expected_extensions=expected_extensions,
            require_tree=require_tree,
            min_tree_nodes=min_tree_nodes,
            require_items=require_items,
            min_items=min_items,
        )

    def get_active_document_state(
        self,
        document_id: str | None = None,
        *,
        require_active_document: bool = True,
        include_tree: bool = False,
        include_items: bool = False,
        max_items: int = 25,
    ) -> dict[str, Any]:
        return build_active_document_state(
            self,
            document_id=document_id,
            require_active_document=require_active_document,
            include_tree=include_tree,
            include_items=include_items,
            max_items=max_items,
        )

    def capture_document_snapshot(
        self,
        model_path: str | None = None,
        *,
        document_id: str | None = None,
        output_path: str | None = None,
        require_active_document: bool = True,
        visible: bool = False,
        read_only: bool = True,
        close_after_probe: bool = True,
        include_manifest: bool = False,
    ) -> dict[str, Any]:
        return build_document_snapshot(
            self,
            model_path=model_path,
            document_id=document_id,
            output_path=output_path,
            require_active_document=require_active_document,
            visible=visible,
            read_only=read_only,
            close_after_probe=close_after_probe,
            include_manifest=include_manifest,
        )

    def diff_document_snapshots(
        self,
        before: dict[str, Any] | str,
        after: dict[str, Any] | str,
        *,
        max_items: int = 25,
        ignore_paths: list[str] | tuple[str, ...] | None = None,
        ignore_keys: list[str] | tuple[str, ...] | None = None,
        use_default_volatile_ignores: bool = False,
    ) -> dict[str, Any]:
        return build_document_snapshot_diff(
            before,
            after,
            max_items=max_items,
            ignore_paths=ignore_paths,
            ignore_keys=ignore_keys,
            use_default_volatile_ignores=use_default_volatile_ignores,
        )

    def verify_document_snapshot_delta(
        self,
        operation: str,
        *,
        before: dict[str, Any] | str | None = None,
        after: dict[str, Any] | str | None = None,
        diff: dict[str, Any] | None = None,
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
        ignore_paths: list[str] | tuple[str, ...] | None = None,
        ignore_keys: list[str] | tuple[str, ...] | None = None,
        use_default_volatile_ignores: bool = False,
    ) -> dict[str, Any]:
        return build_document_snapshot_delta_verification(
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

    def verify_document_readback_stability(
        self,
        document_id: str | None = None,
        *,
        before_output_path: str | None = None,
        after_output_path: str | None = None,
        require_active_document: bool = True,
        max_items: int = 25,
        include_manifests: bool = False,
        ignore_paths: list[str] | tuple[str, ...] | None = None,
        ignore_keys: list[str] | tuple[str, ...] | None = None,
        use_default_volatile_ignores: bool = False,
    ) -> dict[str, Any]:
        return build_document_readback_stability(
            self,
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

    def classify_runtime_error(
        self,
        message: str,
        *,
        exception_type: str | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        return build_runtime_error_classification(message, exception_type=exception_type, stage=stage)

    def normalize_operation_result(
        self,
        operation: str,
        *,
        result: dict[str, Any] | None = None,
        preflight: dict[str, Any] | None = None,
        readback_contract: dict[str, Any] | None = None,
        checks: list[dict[str, Any]] | None = None,
        error: str | None = None,
        exception_type: str | None = None,
        artifacts: dict[str, str] | None = None,
        stage: str = "operation_result",
        require_result: bool = True,
    ) -> dict[str, Any]:
        return build_operation_result_envelope(
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

    def check_file_access(self, path: str) -> dict[str, Any]:
        return self._check_file_access(path)

    def get_document_tree(self, document_id: str | None = None) -> dict[str, Any]:
        return self.runner.call("get_document_tree", {"document_id": document_id})

    def probe_model_object_collections(
        self,
        document_id: str | None = None,
        *,
        max_items: int = 5,
        include_empty: bool = True,
    ) -> dict[str, Any]:
        return self.runner.call(
            "probe_model_object_collections",
            {
                "document_id": document_id,
                "max_items": max_items,
                "include_empty": include_empty,
            },
        )

    def get_specification_descriptions(self, document_id: str | None = None) -> dict[str, Any]:
        return self.runner.call("get_specification_descriptions", {"document_id": document_id})

    def get_specification(
        self,
        document_id: str | None = None,
        *,
        description_index: int | None = None,
        layout_name: str | None = None,
        include_objects: bool = True,
        max_objects: int = 200,
    ) -> dict[str, Any]:
        return self.runner.call(
            "get_specification",
            {
                "document_id": document_id,
                "description_index": description_index,
                "layout_name": layout_name,
                "include_objects": include_objects,
                "max_objects": max_objects,
            },
        )

    def preview_specification_generation(
        self,
        document_id: str | None = None,
        *,
        include_root: bool = False,
    ) -> dict[str, Any]:
        tree_payload = self.get_document_tree(document_id=document_id)
        return build_specification_preview(
            tree_payload["document"],
            tree_payload["tree"],
            include_root=include_root,
        )

    def preview_spw_generation(
        self,
        document_id: str | None = None,
        *,
        include_root: bool = False,
        columns: list[str | dict[str, Any]] | None = None,
        include_engineering: bool = False,
        column_preset: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_specification_generation(
            document_id=document_id,
            include_root=include_root,
        )
        column_plan = resolve_spw_columns(
            columns,
            include_engineering=include_engineering,
            column_preset=column_preset,
        )
        spw_columns = column_plan["columns"]
        engineering = dict(preview["summary"].get("engineering") or {})
        engineering["written_to_spw_columns"] = [
            column for column in spw_columns if column.get("field") in SPW_ENGINEERING_FIELDS
        ]
        return {
            "document": preview["document"],
            "summary": {
                **preview["summary"],
                "document_type": "spw",
                "spw_columns": spw_columns,
                "spw_column_preset": column_plan["preset"],
                "spw_column_preset_description": column_plan["preset_description"],
                "spw_ignored_columns": column_plan["ignored_columns"],
                "spw_column_report": {
                    "requested_count": column_plan["requested_count"],
                    "normalized_count": column_plan["normalized_count"],
                    "engineering_column_count": len(column_plan["engineering_columns"]),
                    "available_presets": column_plan["available_presets"],
                },
                "include_engineering": include_engineering,
                "engineering": engineering,
            },
            "rows": preview["rows"],
        }

    def create_spw_from_model(
        self,
        document_id: str | None = None,
        *,
        output_path: str | None = None,
        include_root: bool = False,
        layout_name: str = "graphic.lyt",
        style_id: int = 1,
        columns: list[str | dict[str, Any]] | None = None,
        include_engineering: bool = False,
        column_preset: str | None = None,
    ) -> dict[str, Any]:
        selected = self._select_document(document_id=document_id)
        preview = self.preview_spw_generation(
            document_id=selected.get("id"),
            include_root=include_root,
            columns=columns,
            include_engineering=include_engineering,
            column_preset=column_preset,
        )
        target_path = output_path or self._build_export_path(
            selected.get("path") or selected.get("name") or "document.a3d",
            suffix="spw",
            extension=".spw",
        )
        result = self.runner.call(
            "create_spw_from_rows",
            {
                "document_id": selected.get("id"),
                "output_path": self._normalize_target_path_for_kompas(target_path),
                "rows": preview["rows"],
                "columns": preview["summary"]["spw_columns"],
                "layout_name": layout_name,
                "style_id": style_id,
            },
        )
        result["preview"] = preview["summary"]
        result["preview_rows"] = preview["rows"]
        result["output_path"] = target_path
        return result

    def create_specification(
        self,
        document_id: str | None = None,
        *,
        include_root: bool = False,
        replace_existing: bool = False,
        save: bool = False,
        close_after_save: bool = False,
        layout_name: str = "",
        style_id: int = 0,
        specification_name: str = "",
    ) -> dict[str, Any]:
        preview = self.preview_specification_generation(
            document_id=document_id,
            include_root=include_root,
        )
        result = self.runner.call(
            "create_specification",
            {
                "document_id": document_id,
                "replace_existing": replace_existing,
                "save": save,
                "close_after_save": close_after_save,
                "layout_name": layout_name,
                "style_id": style_id,
                "specification_name": specification_name,
            },
        )
        result["preview"] = preview["summary"]
        result["preview_rows"] = preview["rows"]
        return result

    def preview_specification_changes(
        self,
        updates: list[dict[str, Any]],
        *,
        document_id: str | None = None,
        description_index: int | None = None,
        layout_name: str | None = None,
        max_objects: int = 2000,
    ) -> dict[str, Any]:
        specification_payload = self.get_specification(
            document_id=document_id,
            description_index=description_index,
            layout_name=layout_name,
            include_objects=True,
            max_objects=max_objects,
        )
        return build_specification_changes_preview(specification_payload, updates)

    def apply_specification_changes(
        self,
        updates: list[dict[str, Any]],
        *,
        document_id: str | None = None,
        description_index: int | None = None,
        layout_name: str | None = None,
        save: bool = False,
        close_after_save: bool = False,
        max_objects: int = 2000,
    ) -> dict[str, Any]:
        preview = self.preview_specification_changes(
            updates,
            document_id=document_id,
            description_index=description_index,
            layout_name=layout_name,
            max_objects=max_objects,
        )
        apply_result = self.runner.call(
            "apply_specification_changes",
            {
                "document_id": document_id,
                "description_index": description_index,
                "layout_name": layout_name,
                "changes": preview["changes"],
                "save": save,
                "close_after_save": close_after_save,
            },
        )
        return {
            "document": apply_result["document"],
            "selected_description": preview.get("selected_description"),
            "preview": preview["summary"],
            "applied_count": apply_result["applied_count"],
            "failed_count": apply_result["failed_count"],
            "applied": apply_result["applied"],
            "failed": apply_result["failed"],
            "saved": apply_result["saved"],
            "missing_objects": preview["missing_objects"],
            "missing_columns": preview["missing_columns"],
            "unsupported_fields": preview["unsupported_fields"],
        }

    def preview_specification_autofill(
        self,
        *,
        document_id: str | None = None,
        description_index: int | None = None,
        layout_name: str | None = None,
        include_root: bool = False,
        fields: list[str] | None = None,
        fill_only: bool = False,
        max_objects: int = 2000,
    ) -> dict[str, Any]:
        model_preview = self.preview_specification_generation(
            document_id=document_id,
            include_root=include_root,
        )
        specification_payload = self.get_specification(
            document_id=document_id,
            description_index=description_index,
            layout_name=layout_name,
            include_objects=True,
            max_objects=max_objects,
        )
        return build_specification_autofill_preview(
            specification_payload,
            model_preview,
            fields=fields,
            fill_only=fill_only,
        )

    def apply_specification_autofill(
        self,
        *,
        document_id: str | None = None,
        description_index: int | None = None,
        layout_name: str | None = None,
        include_root: bool = False,
        fields: list[str] | None = None,
        fill_only: bool = False,
        save: bool = False,
        close_after_save: bool = False,
        max_objects: int = 2000,
    ) -> dict[str, Any]:
        autofill = self.preview_specification_autofill(
            document_id=document_id,
            description_index=description_index,
            layout_name=layout_name,
            include_root=include_root,
            fields=fields,
            fill_only=fill_only,
            max_objects=max_objects,
        )
        apply_result = self.apply_specification_changes(
            updates=autofill["updates"],
            document_id=document_id,
            description_index=description_index,
            layout_name=layout_name,
            save=save,
            close_after_save=close_after_save,
            max_objects=max_objects,
        )
        return {
            "document": apply_result["document"],
            "selected_description": apply_result.get("selected_description"),
            "model_preview_summary": autofill["model_preview_summary"],
            "matching_summary": autofill["matching_summary"],
            "preview": apply_result["preview"],
            "applied_count": apply_result["applied_count"],
            "failed_count": apply_result["failed_count"],
            "applied": apply_result["applied"],
            "failed": apply_result["failed"],
            "saved": apply_result["saved"],
            "matched_rows": autofill["matched_rows"],
            "unmatched_rows": autofill["unmatched_rows"],
            "unmatched_spec_objects": autofill["unmatched_spec_objects"],
        }

    def refresh_specification_from_model(
        self,
        *,
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
    ) -> dict[str, Any]:
        create_result = self.create_specification(
            document_id=document_id,
            include_root=include_root,
            replace_existing=replace_existing,
            save=False,
            close_after_save=False,
            layout_name=layout_name,
            style_id=style_id,
            specification_name=specification_name,
        )
        autofill_result = self.apply_specification_autofill(
            document_id=document_id,
            include_root=include_root,
            fields=fields,
            fill_only=fill_only,
            save=False,
            close_after_save=False,
            max_objects=max_objects,
        )
        final_specification = self.get_specification(
            document_id=document_id,
            include_objects=True,
            max_objects=max_objects,
        )
        save_result = None
        if save:
            save_result = self.save_document(
                document_id=document_id,
                close_after_save=close_after_save,
            )
        return {
            "document": (save_result or autofill_result)["document"],
            "created": {
                "summary": create_result.get("summary"),
                "specification": create_result.get("specification"),
                "saved": bool(save),
                "preview": create_result.get("preview"),
            },
            "autofill": {
                "matching_summary": autofill_result.get("matching_summary"),
                "preview": autofill_result.get("preview"),
                "applied_count": autofill_result.get("applied_count", 0),
                "failed_count": autofill_result.get("failed_count", 0),
                "saved": bool(save),
            },
            "specification_summary": final_specification.get("summary"),
            "specification": final_specification.get("specification"),
            "saved": bool(save),
            "closed": bool(save_result and save_result.get("closed")),
        }

    def get_file_composition(self, assembly_path: str) -> dict[str, Any]:
        return read_file_composition(assembly_path)

    def get_document_composition(self, document_id: str | None = None) -> dict[str, Any]:
        selected = self._select_document(document_id=document_id)
        assembly_path = selected.get("path")
        if not assembly_path:
            raise RuntimeError("Selected document does not have a saved file path")

        payload = read_file_composition(assembly_path)
        payload["document"] = selected
        return payload

    def open_document(
        self,
        path: str,
        *,
        visible: bool = True,
        read_only: bool = False,
    ) -> dict[str, Any]:
        normalized_path = self._normalize_path_for_kompas(path)
        source_path = Path(path)
        return self.runner.call(
            "open_document",
            {
                "path": normalized_path,
                "original_path": path,
                "path_exists": source_path.exists(),
                "path_is_dir": source_path.is_dir(),
                "visible": visible,
                "read_only": read_only,
            },
        )

    def close_document(
        self,
        document_id: str | None = None,
        *,
        save: bool = False,
        close_mode: int = 0,
    ) -> dict[str, Any]:
        return self.runner.call(
            "close_document",
            {"document_id": document_id, "save": save, "close_mode": close_mode},
        )

    def shutdown_session(
        self,
        *,
        save: bool = False,
        close_mode: int = 0,
    ) -> dict[str, Any]:
        return self.runner.call(
            "shutdown_session",
            {"save": save, "close_mode": close_mode},
        )

    def smoke_check_session(
        self,
        path: str,
        *,
        output_dir: str | None = None,
        visible: bool = False,
    ) -> dict[str, Any]:
        source = Path(path)
        if not source.exists():
            raise RuntimeError(f"Smoke-check source does not exist: {path}")
        if source.is_dir():
            raise RuntimeError(f"Smoke-check source points to a directory: {path}")

        before = self.list_documents()
        opened_document: dict[str, Any] | None = None
        reopened_document: dict[str, Any] | None = None
        cleanup: list[dict[str, Any]] = []
        steps: list[dict[str, Any]] = []
        smoke_path = self._build_smoke_export_path(str(source), output_dir=output_dir)

        try:
            opened = self.open_document(str(source), visible=visible, read_only=False)
            opened_document = opened["document"]
            steps.append({"step": "open_for_save_as", "ok": True, "document": opened_document})

            save_result = self.save_document_as(
                smoke_path,
                document_id=opened_document.get("id"),
                close_after_save=True,
            )
            steps.append({"step": "save_as_close", "ok": True, "result": save_result})
        finally:
            if opened_document is not None:
                cleanup.extend(self._close_matching_documents([opened_document.get("id"), smoke_path]))

        after_save_close = self.list_documents()
        saved_file_access = self.check_file_access(smoke_path)

        try:
            reopened = self.open_document(str(source), visible=visible, read_only=True)
            reopened_document = reopened["document"]
            steps.append({"step": "open_read_only", "ok": True, "document": reopened_document})

            close_result = self.close_document(reopened_document.get("id"), save=False)
            steps.append({"step": "close_read_only", "ok": True, "result": close_result})
            reopened_document = None
        finally:
            if reopened_document is not None:
                cleanup.extend(self._close_matching_documents([reopened_document.get("id")]))

        after = self.list_documents()
        target_ids = {
            value
            for value in (
                opened_document.get("id") if opened_document else None,
                opened_document.get("path") if opened_document else None,
                reopened_document.get("id") if reopened_document else None,
                reopened_document.get("path") if reopened_document else None,
                smoke_path,
            )
            if value
        }
        remaining_target_documents = [
            document
            for document in after.get("documents", [])
            if document.get("id") in target_ids or document.get("path") in target_ids
        ]

        return {
            "ok": not remaining_target_documents and bool(saved_file_access.get("exclusive_open_ok")),
            "source_path": str(source),
            "smoke_path": smoke_path,
            "before": before,
            "after_save_close": after_save_close,
            "after": after,
            "steps": steps,
            "cleanup": cleanup,
            "remaining_target_documents": remaining_target_documents,
            "saved_file_access": saved_file_access,
        }

    def scan_model_files(
        self,
        root: str,
        *,
        recursive: bool = True,
        extensions: list[str] | None = None,
        include_locks: bool = False,
        max_files: int | None = None,
    ) -> dict[str, Any]:
        return scan_model_files_payload(
            root,
            recursive=recursive,
            extensions=extensions,
            include_locks=include_locks,
            max_files=max_files,
        )

    def batch_smoke_check_session(
        self,
        *,
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
    ) -> dict[str, Any]:
        if root:
            inventory = self.scan_model_files(
                root,
                recursive=recursive,
                extensions=extensions,
                include_locks=include_locks,
            )
        elif paths:
            inventory = build_file_list(
                paths,
                extensions=extensions,
                include_locks=include_locks,
            )
        else:
            raise RuntimeError("Either root or paths must be provided")

        files = inventory["files"]
        selected_files = files
        if limit is not None and limit > 0:
            selected_files = files[:limit]

        results: list[dict[str, Any]] = []
        stopped_after_error = False
        for item in selected_files:
            path = item["path"]
            if dry_run:
                results.append({"path": path, "status": "dry_run", "file": item})
                continue

            try:
                smoke = self.smoke_check_session(path, output_dir=output_dir, visible=visible)
                results.append(
                    {
                        "path": path,
                        "status": "ok" if smoke.get("ok") else "error",
                        "file": item,
                        "smoke": smoke,
                    }
                )
                if not smoke.get("ok") and not continue_on_error:
                    stopped_after_error = True
                    break
            except Exception as exc:
                results.append({"path": path, "status": "error", "file": item, "error": str(exc)})
                if not continue_on_error:
                    stopped_after_error = True
                    break

        if stopped_after_error:
            remaining = selected_files[len(results) :]
            results.extend({"path": item["path"], "status": "stopped", "file": item} for item in remaining)

        successful_statuses = ("ok", "dry_run")
        payload = {
            "report_type": "batch_smoke_check",
            "ok": bool(results) and all(result.get("status") in successful_statuses for result in results),
            "dry_run": dry_run,
            "limit": limit,
            "truncated_by_limit": len(selected_files) < len(files),
            "inventory": inventory["summary"],
            "skipped": inventory["skipped"],
            "results": results,
            "summary": {
                **summarize_batch_results(results),
                "candidate_count": len(files),
                "selected_count": len(selected_files),
                "skipped_count": len(inventory["skipped"]),
                "stopped_after_error": stopped_after_error,
            },
        }
        if report_dir:
            payload["report"] = write_batch_report(
                payload,
                report_dir=report_dir,
                report_name=report_name,
                formats=report_formats,
            )
        return payload

    def batch_analyze_model_quality(
        self,
        *,
        root: str | None = None,
        paths: list[str] | None = None,
        recursive: bool = True,
        extensions: list[str] | None = None,
        include_locks: bool = False,
        limit: int | None = 20,
        visible: bool = False,
        analyses: list[str] | None = None,
        rules: dict[str, Any] | None = None,
        continue_on_error: bool = True,
        report_dir: str | None = None,
        report_name: str | None = None,
        report_formats: list[str] | None = None,
    ) -> dict[str, Any]:
        if root:
            inventory = self.scan_model_files(
                root,
                recursive=recursive,
                extensions=extensions,
                include_locks=include_locks,
            )
        elif paths:
            inventory = build_file_list(
                paths,
                extensions=extensions,
                include_locks=include_locks,
            )
        else:
            raise RuntimeError("Either root or paths must be provided")

        files = inventory["files"]
        selected_files = files[:limit] if limit is not None and limit > 0 else files
        selected_analyses = set(analyses or ["naming", "spec"])
        rule_payload = rules or {}
        results: list[dict[str, Any]] = []
        stopped_after_error = False

        for item in selected_files:
            opened_document: dict[str, Any] | None = None
            path = item["path"]
            try:
                opened = self.open_document(path, visible=visible, read_only=True)
                opened_document = opened["document"]
                tree_payload = self.get_document_tree(document_id=opened_document.get("id"))

                analysis_payload: dict[str, Any] = {}
                issue_count = 0
                if "naming" in selected_analyses:
                    naming = analyze_naming_issues(tree_payload["tree"], rule_payload).to_dict()
                    analysis_payload["naming"] = naming
                    issue_count += int(naming.get("summary", {}).get("issues_found", 0))
                if "spec" in selected_analyses:
                    spec = analyze_spec_issues(tree_payload["tree"], rule_payload).to_dict()
                    analysis_payload["spec"] = spec
                    issue_count += int(spec.get("summary", {}).get("issues_found", 0))

                results.append(
                    {
                        "path": path,
                        "status": "ok",
                        "file": item,
                        "document": tree_payload["document"],
                        "analyses": analysis_payload,
                        "issue_count": issue_count,
                    }
                )
            except Exception as exc:
                results.append({"path": path, "status": "error", "file": item, "error": str(exc)})
                if not continue_on_error:
                    stopped_after_error = True
                    break
            finally:
                if opened_document is not None:
                    try:
                        self.close_document(opened_document.get("id"), save=False)
                    except Exception:
                        pass

        if stopped_after_error:
            remaining = selected_files[len(results) :]
            results.extend({"path": item["path"], "status": "stopped", "file": item} for item in remaining)

        status_summary = summarize_batch_results(results)
        total_issues = sum(int(result.get("issue_count") or 0) for result in results)
        payload = {
            "report_type": "batch_model_quality",
            "ok": bool(results) and status_summary["error_count"] == 0 and status_summary["stopped_count"] == 0,
            "limit": limit,
            "truncated_by_limit": len(selected_files) < len(files),
            "analyses": sorted(selected_analyses),
            "inventory": inventory["summary"],
            "skipped": inventory["skipped"],
            "results": results,
            "summary": {
                **status_summary,
                "candidate_count": len(files),
                "selected_count": len(selected_files),
                "skipped_count": len(inventory["skipped"]),
                "total_issues": total_issues,
                "stopped_after_error": stopped_after_error,
            },
        }
        if report_dir:
            payload["report"] = write_batch_report(
                payload,
                report_dir=report_dir,
                report_name=report_name,
                formats=report_formats,
            )
        return payload

    def preview_part_scenario(self, scenario: str, params: dict[str, Any]) -> dict[str, Any]:
        return build_part_scenario_preview(scenario, params)

    def create_part_from_scenario(
        self,
        scenario: str,
        params: dict[str, Any],
        *,
        output_path: str | None = None,
        visible: bool = False,
        close_after_save: bool | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_part_scenario(scenario, params)
        normalized_params = dict(preview["params"])
        if output_path:
            normalized_params["output_path"] = self._normalize_target_path_for_kompas(output_path)
        elif normalized_params.get("output_path"):
            normalized_params["output_path"] = self._normalize_target_path_for_kompas(normalized_params["output_path"])
        if close_after_save is not None:
            normalized_params["close_after_save"] = bool(close_after_save)

        result = self.runner.call(
            "create_part_from_scenario",
            {
                "scenario": preview["scenario"],
                "params": normalized_params,
                "preview": preview,
                "visible": visible,
            },
        )
        return {
            **result,
            "preview": preview,
        }

    @staticmethod
    def _normalize_path_for_kompas(path: str) -> str:
        candidate = str(Path(path))
        if not Path(candidate).exists():
            return candidate

        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "kernel32"):
            buffer = ctypes.create_unicode_buffer(32768)
            result = ctypes.windll.kernel32.GetShortPathNameW(candidate, buffer, len(buffer))
            if result:
                return buffer.value

        return candidate

    @staticmethod
    def _normalize_long_path_for_kompas(path: str) -> str:
        candidate = str(Path(path))
        if not Path(candidate).exists():
            return candidate

        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "kernel32"):
            buffer = ctypes.create_unicode_buffer(32768)
            result = ctypes.windll.kernel32.GetLongPathNameW(candidate, buffer, len(buffer))
            if result:
                return buffer.value

        return candidate

    def _close_matching_documents(self, document_ids: list[str | None]) -> list[dict[str, Any]]:
        wanted = {document_id for document_id in document_ids if document_id}
        if not wanted:
            return []

        cleanup: list[dict[str, Any]] = []
        try:
            documents = self.list_documents().get("documents", [])
        except Exception as exc:
            return [{"ok": False, "error": str(exc), "stage": "list_documents"}]

        for document in documents:
            identifiers = {document.get("id"), document.get("path"), document.get("name")}
            if not wanted.intersection({identifier for identifier in identifiers if identifier}):
                continue
            try:
                cleanup.append(
                    {
                        "ok": True,
                        "document": document,
                        "result": self.close_document(document.get("id"), save=False),
                    }
                )
            except Exception as exc:
                cleanup.append({"ok": False, "document": document, "error": str(exc)})
        return cleanup

    def get_items(self, document_id: str | None = None, item_ids: list[str] | None = None) -> dict[str, Any]:
        tree_payload = self.get_document_tree(document_id=document_id)
        items = flatten_tree(tree_payload["tree"])
        wanted = set(item_ids or [])
        if wanted:
            items = [item for item in items if item["id"] in wanted]

        return {
            "document": tree_payload["document"],
            "items": items,
            "count": len(items),
        }

    def probe_document_readback(
        self,
        model_path: str | None = None,
        *,
        document_id: str | None = None,
        output_path: str | None = None,
        visible: bool = False,
        read_only: bool = True,
        close_after_probe: bool = True,
    ) -> dict[str, Any]:
        return build_document_readback_probe(
            self,
            model_path=model_path,
            document_id=document_id,
            output_path=output_path,
            visible=visible,
            read_only=read_only,
            close_after_probe=close_after_probe,
        )

    def get_item_properties(self, document_id: str | None = None, item_ids: list[str] | None = None) -> dict[str, Any]:
        tree_payload = self.get_document_tree(document_id=document_id)
        return build_item_properties(tree_payload["document"], tree_payload["tree"], item_ids=item_ids)

    def preview_property_changes(
        self,
        updates: list[dict[str, Any]],
        *,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        tree_payload = self.get_document_tree(document_id=document_id)
        return build_property_preview(tree_payload["document"], tree_payload["tree"], updates)

    def set_item_properties(
        self,
        updates: list[dict[str, Any]],
        *,
        document_id: str | None = None,
        save: bool = False,
        close_after_save: bool = False,
    ) -> dict[str, Any]:
        preview = self.preview_property_changes(updates, document_id=document_id)
        apply_result = self.apply_changeset(
            preview["changes"],
            document_id=document_id,
            save=save,
            close_after_save=close_after_save,
        )
        return {
            "document": apply_result["document"],
            "preview": preview["summary"],
            "applied_count": apply_result["applied_count"],
            "failed_count": apply_result["failed_count"],
            "applied": apply_result["applied"],
            "failed": apply_result["failed"],
            "saved": apply_result["saved"],
        }

    def find_items(
        self,
        document_id: str | None = None,
        query: str = "",
        kinds: list[str] | None = None,
    ) -> dict[str, Any]:
        tree_payload = self.get_document_tree(document_id=document_id)
        items = flatten_tree(tree_payload["tree"])
        normalized_query = query.strip().lower()
        allowed_kinds = set(kinds or [])

        matches = []
        for item in items:
            if allowed_kinds and item.get("kind") not in allowed_kinds:
                continue

            haystack = " ".join(
                str(item.get(field) or "")
                for field in ("name", "designation", "material", "comment", "source_path")
            ).lower()

            if normalized_query and normalized_query not in haystack:
                continue

            matches.append(item)

        return {
            "document": tree_payload["document"],
            "items": matches,
            "count": len(matches),
        }

    def apply_changeset(
        self,
        changes: list[dict[str, Any]],
        *,
        document_id: str | None = None,
        save: bool = False,
        close_after_save: bool = False,
    ) -> dict[str, Any]:
        return self.runner.call(
            "apply_changeset",
            {
                "document_id": document_id,
                "changes": changes,
                "save": save,
                "close_after_save": close_after_save,
            },
        )

    def save_document(self, document_id: str | None = None, *, close_after_save: bool = True) -> dict[str, Any]:
        return self.runner.call(
            "save_document",
            {"document_id": document_id, "close_after_save": close_after_save},
        )

    def save_document_as(
        self,
        path: str,
        document_id: str | None = None,
        *,
        close_after_save: bool = True,
    ) -> dict[str, Any]:
        return self.runner.call(
            "save_document",
            {
                "document_id": document_id,
                "path": self._normalize_target_path_for_kompas(path),
                "close_after_save": close_after_save,
            },
        )

    def save_export_copy(
        self,
        document_id: str | None = None,
        suffix: str = "codex",
        *,
        close_after_save: bool = True,
    ) -> dict[str, Any]:
        selected = self._select_document(document_id=document_id)
        export_path = self._build_export_path(selected.get("path") or selected.get("name") or "document.a3d", suffix=suffix)
        result = self.save_document_as(
            export_path,
            document_id=selected.get("id"),
            close_after_save=close_after_save,
        )
        result["export_path"] = export_path
        return result

    def apply_relink_paths(
        self,
        changes: list[dict[str, Any]],
        *,
        document_id: str | None = None,
        save: bool = False,
        close_after_save: bool = False,
    ) -> dict[str, Any]:
        normalized_changes = []
        for change in changes:
            normalized = dict(change)
            if normalized.get("new_path"):
                normalized["new_path"] = self._normalize_target_path_for_kompas(normalized["new_path"])
            normalized_changes.append(normalized)

        return self.runner.call(
            "apply_relink_paths",
            {
                "document_id": document_id,
                "changes": normalized_changes,
                "save": save,
                "close_after_save": close_after_save,
            },
        )

    def relink_document_file(
        self,
        assembly_path: str,
        changes: list[dict[str, Any]],
        *,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        normalized_changes = []
        for change in changes:
            normalized = dict(change)
            if normalized.get("new_path"):
                normalized["new_path"] = self._normalize_target_path_for_kompas(normalized["new_path"])
            normalized_changes.append(normalized)

        return run_vbs_file_relink(
            assembly_path=assembly_path,
            changes=normalized_changes,
            output_path=output_path,
        )

    @classmethod
    def _normalize_target_path_for_kompas(cls, path: str) -> str:
        candidate = Path(path)
        if candidate.exists():
            return cls._normalize_long_path_for_kompas(str(candidate))

        parent = candidate.parent
        if parent.exists():
            normalized_parent = Path(cls._normalize_long_path_for_kompas(str(parent)))
            return str(normalized_parent / candidate.name)

        return str(candidate)

    @staticmethod
    def _check_file_access(path: str) -> dict[str, Any]:
        candidate = Path(path)
        result: dict[str, Any] = {
            "path": str(candidate),
            "exists": candidate.exists(),
            "is_file": candidate.is_file(),
            "size": candidate.stat().st_size if candidate.is_file() else None,
            "exclusive_open_ok": False,
            "error": None,
        }
        if not candidate.is_file():
            result["error"] = "not_a_file"
            return result

        if not hasattr(ctypes, "windll") or not hasattr(ctypes.windll, "kernel32"):
            try:
                with candidate.open("r+b"):
                    pass
                result["exclusive_open_ok"] = True
            except OSError as exc:
                result["error"] = str(exc)
            return result

        kernel32 = ctypes.windll.kernel32
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        handle = kernel32.CreateFileW(
            str(candidate),
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            error_code = kernel32.GetLastError()
            result["error"] = f"CreateFileW failed with error {error_code}"
            result["win32_error"] = error_code
            return result

        kernel32.CloseHandle(handle)
        result["exclusive_open_ok"] = True
        return result

    @classmethod
    def _build_smoke_export_path(cls, source_path: str, *, output_dir: str | None = None) -> str:
        source = Path(source_path)
        export_dir = Path(output_dir) if output_dir else cls._export_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        ext = source.suffix or ".a3d"
        safe_stem = cls._safe_ascii_stem(source.stem)
        token = uuid.uuid4().hex[:8]
        return str(export_dir / f"{safe_stem}-lifecycle-smoke-{token}{ext}")

    @staticmethod
    def _export_dir() -> Path:
        export_dir = Path(os.environ.get("KOMPAS_EXPORT_DIR", r"C:\Temp\kompas-mcp"))
        export_dir.mkdir(parents=True, exist_ok=True)
        return export_dir

    @staticmethod
    def _safe_ascii_stem(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "")
        safe = safe.strip("._-")
        return safe or "document"

    @classmethod
    def _build_export_path(cls, source_path: str, suffix: str = "codex", extension: str | None = None) -> str:
        source = Path(source_path)
        ext = extension or source.suffix or ".a3d"
        safe_stem = cls._safe_ascii_stem(source.stem)
        safe_suffix = cls._safe_ascii_stem(suffix) or "codex"
        export_dir = cls._export_dir()

        candidate = export_dir / f"{safe_stem}-{safe_suffix}{ext}"
        counter = 2
        while candidate.exists():
            candidate = export_dir / f"{safe_stem}-{safe_suffix}-{counter}{ext}"
            counter += 1

        return str(candidate)

    def _select_document(self, document_id: str | None = None) -> dict[str, Any]:
        documents = self.list_documents().get("documents", [])
        selected = None
        if document_id:
            for document in documents:
                if document_id in (document.get("id"), document.get("path"), document.get("name")):
                    selected = document
                    break
        else:
            selected = next((document for document in documents if document.get("active")), None)

        if selected is None:
            raise RuntimeError("Document not found or no active document")

        return selected
