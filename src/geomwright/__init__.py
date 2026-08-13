"""Public Geomwright application namespace.

The KOMPAS-specific implementation remains in ``kompas_mcp`` during the
compatibility migration. New application entry points live under this package.
"""

from kompas_mcp import __version__

__all__ = ["__version__"]
