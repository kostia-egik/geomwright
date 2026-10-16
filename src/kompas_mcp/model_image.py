"""Host contract for a dialog-free, temporarily oriented model PNG export.

Layer 1 only: registration and adapter methods are owned by the integration
caller. This action writes a file and temporarily changes session view state;
it must not be advertised as a read-only MCP tool.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4


ModelView = Literal["current", "front", "rear", "top", "bottom", "left", "right", "isometric"]
MODEL_VIEWS = ("current", "front", "rear", "top", "bottom", "left", "right", "isometric")


def export_model_png(
    adapter: Any,
    document_id: str,
    output_path: str | None = None,
    view: ModelView = "current",
    resolution_dpi: int = 150,
    fit: bool = True,
) -> dict[str, Any]:
    """Export an exact open document; restore its matrix/scale and activation.

    Explicit destinations must be absolute, new .png paths with an existing
    parent. Omitted destinations get a UUID name in adapter._export_dir().
    Native readback reports restoration failures and Changed before/after;
    restoring the dirty flag or promising exact screen pan is not part of this
    contract. Presets follow the document's native orientation scheme.
    """
    if not isinstance(document_id, str) or not document_id.strip() or document_id.startswith("@document:"):
        raise ValueError("document_id must be an exact open document ID")
    if not isinstance(view, str) or view not in MODEL_VIEWS:
        raise ValueError(f"view must be one of {MODEL_VIEWS}")
    if isinstance(resolution_dpi, bool) or not isinstance(resolution_dpi, int) or not 72 <= resolution_dpi <= 600:
        raise ValueError("resolution_dpi must be an integer in [72, 600]")
    if not isinstance(fit, bool):
        raise ValueError("fit must be a boolean")
    if output_path is None:
        path = Path(adapter._export_dir()).resolve() / f"model-{uuid4().hex}.png"
    else:
        if not isinstance(output_path, str) or not output_path or "\0" in output_path:
            raise ValueError("output_path must be an absolute new .png path")
        path = Path(output_path)
    if not path.is_absolute() or path.suffix.lower() != ".png":
        raise ValueError("output_path must be an absolute new .png path")
    if not path.parent.is_dir():
        raise ValueError("output_path parent directory must already exist")
    if os.path.lexists(path):
        raise ValueError("output_path already exists; choose a new .png path")
    return adapter.runner.call("export_model_png", {
        "document_id": document_id, "output_path": str(path), "view": view,
        "resolution_dpi": resolution_dpi, "fit": fit,
    })
