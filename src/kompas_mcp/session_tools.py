from __future__ import annotations

from typing import Any


def register_session_tools(mcp: Any, adapter: Any) -> None:
    """Register KOMPAS session lifecycle tools."""

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
        return adapter.close_document(document_id=document_id, save=save, close_mode=close_mode)

    @mcp.tool()
    def shutdown_session(save: bool = False, close_mode: int = 0) -> dict:
        """Close all tracked documents and release the KOMPAS session."""
        return adapter.shutdown_session(save=save, close_mode=close_mode)

    @mcp.tool()
    def smoke_check_session(path: str, output_dir: str | None = None, visible: bool = False) -> dict:
        """Open, save-as-close, reopen-readonly and close a KOMPAS document to verify lifecycle handling."""
        return adapter.smoke_check_session(path=path, output_dir=output_dir, visible=visible)

    @mcp.tool()
    def save_document(document_id: str | None = None, close_after_save: bool = True) -> dict:
        """Save the selected or active document in place."""
        return adapter.save_document(document_id=document_id, close_after_save=close_after_save)

    @mcp.tool()
    def save_document_as(path: str, document_id: str | None = None, close_after_save: bool = True) -> dict:
        """Save the selected or active document to an explicit path."""
        return adapter.save_document_as(path=path, document_id=document_id, close_after_save=close_after_save)

    @mcp.tool()
    def save_export_copy(document_id: str | None = None, suffix: str = "codex", close_after_save: bool = True) -> dict:
        """Save the active document to the default export directory with an ASCII-safe file name."""
        return adapter.save_export_copy(
            document_id=document_id,
            suffix=suffix,
            close_after_save=close_after_save,
        )
