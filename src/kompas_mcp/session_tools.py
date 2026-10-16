from __future__ import annotations

from typing import Any, Literal
from .model_image import export_model_png as export_png


def register_session_tools(mcp: Any, adapter: Any) -> None:
    """Register KOMPAS session lifecycle tools."""

    @mcp.tool()
    def export_model_png(
        document_id: str, output_path: str | None = None,
        view: Literal["current", "front", "rear", "top", "bottom", "left", "right", "isometric"] = "current",
        resolution_dpi: int = 150, fit: bool = True,
    ) -> dict:
        """Export an exact open model to a new PNG without a save dialog.

        Standard views change orientation only for export; the prior view matrix,
        scale and active document are restored and checked. Default output is a
        unique file in the export directory; existing paths are never overwritten.
        Returns the artifact path and dimensions for visual review, not image bytes.
        No model rebuild or geometry edits. Exact screen pan restoration is not certified.
        """
        return export_png(adapter, document_id, output_path, view, resolution_dpi, fit)

    @mcp.tool()
    def get_cad_work_mode() -> dict:
        """Read interactive/hidden mode and the bound window/process without COM. Does not verify CAD readiness."""
        return adapter.get_cad_work_mode()

    @mcp.tool()
    def set_cad_work_mode(mode: Literal["interactive", "hidden"], confirm_switch: bool,
                          target_window_handle: int | None = None) -> dict:
        """Explicitly select CAD mode without COM; never recovers quarantine or changes a window's visibility.

        interactive is the default: bind to a visible window and retain documents.
        hidden requires a separately created, proven-owned process; no reuse of the
        user's instance. Optional HWND selects the interactive window. Switching
        is refused while blocked or while an owned hidden session remains alive.
        """
        return adapter.set_cad_work_mode(mode, confirm_switch, target_window_handle)

    @mcp.tool()
    def get_cad_session_guard() -> dict:
        """Read durable CAD quarantine status without COM, even while KOMPAS is busy."""
        return adapter.get_cad_session_guard()

    @mcp.tool()
    def recover_cad_session(token: str, confirm_idle: bool = False, reason: str = "") -> dict:
        """Recover a finished failure through an automatic bounded session audit.

        Read get_cad_session_guard first. For settled_failure leave confirm_idle=false:
        no user confirmation is needed. The audit observes the bound window, edit
        blockers and open documents without changing them. Inspect the affected
        model before writing; recovery never retries, rolls back, closes or saves.
        For unknown_outcome or orphaned in_flight, confirm_idle=true requires the
        user's fresh explicit idle UI/partial-document confirmation. Never infer
        that from process exit. Running bridges/hosts cannot be recovered.
        """
        return adapter.recover_cad_session(token=token, confirm_idle=confirm_idle, reason=reason)

    @mcp.tool()
    def get_session_state() -> dict:
        """Return basic information about the current KOMPAS session."""
        return adapter.get_session_state()

    @mcp.tool()
    def list_documents() -> dict:
        """Return open KOMPAS documents."""
        return adapter.list_documents()

    @mcp.tool()
    def check_file_access(path: str) -> dict:
        """Check whether a file can be opened and whether it appears locked by another process."""
        return adapter.check_file_access(path)

    @mcp.tool()
    def open_document(path: str, visible: bool = True, read_only: bool = False) -> dict:
        """Open a KOMPAS document and return a stable document_id."""
        return adapter.open_document(path=path, visible=visible, read_only=read_only)

    @mcp.tool()
    def close_document(document_id: str | None = None, save: bool = False, close_mode: int = 0) -> dict:
        """Close the selected or active document."""
        return adapter.close_document(document_id=document_id, save=save, close_mode=close_mode, user_requested=True)

    @mcp.tool()
    def shutdown_session(save: bool = False, close_mode: int = 0) -> dict:
        """Close all tracked documents and release the KOMPAS session."""
        return adapter.shutdown_session(save=save, close_mode=close_mode, user_requested=True)

    @mcp.tool()
    def smoke_check_session(path: str, output_dir: str | None = None, visible: bool = False) -> dict:
        """Open, save-as-close, reopen-readonly and close a KOMPAS document to verify lifecycle handling."""
        return adapter.smoke_check_session(path=path, output_dir=output_dir, visible=visible)

    @mcp.tool()
    def save_document(document_id: str | None = None, close_after_save: bool = False) -> dict:
        """Save the selected or active document in place."""
        return adapter.save_document(document_id=document_id, close_after_save=close_after_save,
                                     user_requested_close=close_after_save)

    @mcp.tool()
    def save_document_as(path: str, document_id: str | None = None, close_after_save: bool = False) -> dict:
        """Save the selected or active document to an explicit path."""
        return adapter.save_document_as(path=path, document_id=document_id, close_after_save=close_after_save,
                                        user_requested_close=close_after_save)

    @mcp.tool()
    def save_export_copy(document_id: str | None = None, suffix: str = "codex", close_after_save: bool = False) -> dict:
        """Save the active document to the default export directory with an ASCII-safe file name."""
        return adapter.save_export_copy(
            document_id=document_id,
            suffix=suffix,
            close_after_save=close_after_save,
            user_requested_close=close_after_save,
        )
