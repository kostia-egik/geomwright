"""Geomwright Studio presentation layer.

The web dependency is imported lazily so the core MCP package remains usable
without the optional ``ui`` dependency group.
"""

from __future__ import annotations

from typing import Any

from .registry import get_module, list_modules, preview_module


def create_app() -> Any:
    """Create the FastAPI application when optional UI dependencies exist."""

    from .app import create_app as _create_app

    return _create_app()


__all__ = ["create_app", "get_module", "list_modules", "preview_module"]
