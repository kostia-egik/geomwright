"""Shared Layer 1 PNG handler, loaded by checkout and packaged bridges.

SDK v23: IKompasDocument3D1.ViewProjectionManager; Matrix3D is a flat
16-element VT_ARRAY|VT_R8; SetMatrix3D(matrix, scale) returns BOOL.
API5 GetViewProjectonType (SDK spelling) uses ksViewProjectionType, NOT
collection indices. RasterFormatParam uses extResolution, not resolution.
No geometry, rebuild, visibility changes, arbitrary rotation, or UI commands.
"""

import math
import os
from pathlib import Path
import struct
import zlib


PROJECTION_TYPES = {"front": 1, "rear": 2, "top": 3, "bottom": 4,
                    "left": 5, "right": 6, "isometric": 7}


def _validate(payload):
    document_id = payload.get("document_id")
    if not isinstance(document_id, str) or not document_id.strip() or document_id.startswith("@document:"):
        raise ValueError("document_id must be an exact open document ID")
    view = payload.get("view", "current")
    if not isinstance(view, str) or view not in ("current", *PROJECTION_TYPES):
        raise ValueError("view must be current/front/rear/top/bottom/left/right/isometric")
    dpi = payload.get("resolution_dpi", 150)
    if isinstance(dpi, bool) or not isinstance(dpi, int) or not 72 <= dpi <= 600:
        raise ValueError("resolution_dpi must be an integer in [72, 600]")
    fit = payload.get("fit", True)
    if not isinstance(fit, bool):
        raise ValueError("fit must be a boolean")
    output = payload.get("output_path")
    if not isinstance(output, str) or not output or "\0" in output:
        raise ValueError("output_path must be an absolute new .png path")
    path = Path(output)
    if not path.is_absolute() or path.suffix.lower() != ".png" or not path.parent.is_dir():
        raise ValueError("output_path must be an absolute .png path with an existing parent")
    if os.path.lexists(path):
        raise ValueError("output_path already exists; choose a new .png path")
    return document_id, path, view, dpi, fit


def _png_metadata(path):
    """Bounded header verification, not an image decoder or visual audit."""
    with path.open("rb") as stream:
        header = stream.read(33)
        size = os.fstat(stream.fileno()).st_size
    if len(header) != 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[8:16] != b"\0\0\0\rIHDR":
        raise RuntimeError("Raster export did not produce a PNG IHDR header")
    if size <= 33 or zlib.crc32(header[12:29]) != struct.unpack(">I", header[29:33])[0]:
        raise RuntimeError("Raster export produced an empty/truncated or invalid PNG header")
    width, height = struct.unpack(">II", header[16:24])
    if not 0 < width <= 2**31 - 1 or not 0 < height <= 2**31 - 1:
        raise RuntimeError("Raster export produced invalid PNG dimensions")
    return {"width": width, "height": height, "bytes": size, "mime_type": "image/png",
            "verification": "png_ihdr_only"}


def _snapshot(manager):
    matrix = tuple(float(x) for x in manager.Matrix3D)
    scale = float(manager.Scale)
    if len(matrix) != 16 or not all(math.isfinite(x) for x in matrix) or not math.isfinite(scale) or scale <= 0:
        raise RuntimeError("Cannot safely snapshot ViewProjectionManager Matrix3D/Scale")
    return matrix, scale


def _projections(legacy):
    collection = legacy.GetViewProjectionCollection()
    count = int(collection.GetCount())
    if not 0 <= count <= 32:
        raise RuntimeError("View projection collection exceeds the supported bound of 32")
    return [collection.GetByIndex(index) for index in range(count)]


def _current_type(projections):
    current = [int(item.GetViewProjectonType()) for item in projections if item.IsCurrent()]
    if len(current) > 1:
        raise RuntimeError("Multiple view projections report IsCurrent")
    return current[0] if current else None


def _require_success(value, operation):
    if not value:
        raise RuntimeError(operation + " returned failure")


def handle(action, payload, b):
    """Dispatch interface: handle('export_model_png', payload, bridge_module).

    Failures after attachment return ok=False with bounded partial/restoration
    evidence, so BridgeRunner quarantines uncertain CAD outcomes. Validation
    occurs before attachment. Exact screen pan is intentionally not certified.
    """
    if action != "export_model_png":
        raise ValueError("Unknown model image action: " + str(action))
    document_id, path, view, dpi, fit = _validate(payload)
    import win32com.client as com
    import pythoncom

    app = b.make_app()  # Uses the selected CAD session; never Dispatch another app.
    document = b.resolve_document_strict(app, document_id)
    if document is None:
        raise RuntimeError("Exact 3D document not found; refresh open document IDs")
    previous = app.ActiveDocument
    if previous is None:
        raise RuntimeError("No prior active document; activation cannot be safely restored")

    def identity(doc):
        value = b.describe_document(doc, app).get("runtime_id")
        if not value:
            raise RuntimeError("Cannot verify exact active document identity")
        return value

    previous_id = identity(previous)
    target_id = identity(document)
    if target_id != document_id:
        raise RuntimeError("Resolved document identity does not match document_id")
    changed_before = bool(document.Changed)
    result = {"ok": False, "document_id": target_id, "output_path": str(path),
              "view": view, "resolution_dpi": dpi, "fit": fit,
              "projection_type": None, "view_restored": False,
              "activation_restored": False, "no_geometry_operations": True,
              "changed_before": changed_before, "changed_after": None,
              "restore_fields": [], "screen_pan_verified": False}
    manager = saved = None
    view_touched = False
    errors = []
    try:
        if previous_id != target_id:
            com.CastTo(document, "IKompasDocument").Active = True
        if identity(app.ActiveDocument) != target_id:
            raise RuntimeError("Target document activation failed; raster export refused")
        manager = com.CastTo(document, "IKompasDocument3D1").ViewProjectionManager
        raw = b._APP5
        if raw is None:
            raise RuntimeError("Selected session has no API5 application; raster export unavailable")
        legacy = getattr(raw, "ActiveDocument3D", None)
        if callable(legacy) and not callable(getattr(legacy, "GetPart", None)):
            legacy = legacy()
        if legacy is None or not callable(getattr(legacy, "GetPart", None)):
            raise RuntimeError("Selected session API5 active 3D document is unavailable")
        saved = _snapshot(manager)
        projections = _projections(legacy)
        if view != "current":
            matches = [item for item in projections if int(item.GetViewProjectonType()) == PROJECTION_TYPES[view]]
            if len(matches) != 1:
                raise RuntimeError("Requested standard view is missing or ambiguous: " + view)
            view_touched = True  # A failed COM call can still have changed state.
            _require_success(matches[0].SetCurrent(), "ViewProjection.SetCurrent")
        if fit:
            view_touched = True
            _require_success(legacy.ZoomPrevNextOrAll(2), "ZoomPrevNextOrAll(2)")
        raw.ksRefreshActiveWindow()
        result["projection_type"] = _current_type(projections)
        if view != "current" and result["projection_type"] != PROJECTION_TYPES[view]:
            raise RuntimeError("Requested projection did not become current")
        params = legacy.RasterFormatParam()
        _require_success(params.Init(), "RasterFormatParam.Init")
        params.format, params.colorBPP = 3, 24
        params.extResolution, params.extScale = dpi, 1.0
        # Native export can retain the staging directory handle on Windows.
        # Write straight to the validated new destination; the default UUID
        # path avoids collision without an extra publication/cleanup lifecycle.
        if os.path.lexists(path):
            raise ValueError("output_path was created by another writer; choose a new path")
        _require_success(legacy.SaveAsToRasterFormat(str(path), params), "SaveAsToRasterFormat")
        result["artifact"] = {"path": str(path), **_png_metadata(path)}
    except Exception as exc:
        errors.append({"phase": "export", "message": str(exc)[:1000]})
    finally:
        try:
            if saved is not None:
                matrix = com.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, saved[0])
                _require_success(manager.SetMatrix3D(matrix, saved[1]), "ViewProjectionManager.SetMatrix3D")
                raw.ksRefreshActiveWindow()
                actual_matrix, actual_scale = _snapshot(manager)
                matrix_ok = all(math.isclose(a, c, rel_tol=1e-9, abs_tol=1e-9)
                                for a, c in zip(saved[0], actual_matrix))
                scale_ok = math.isclose(saved[1], actual_scale, rel_tol=1e-9, abs_tol=1e-9)
                result["restore_fields"] = [name for name, ok in (("Matrix3D", matrix_ok), ("Scale", scale_ok)) if ok]
                result["view_restored"] = matrix_ok and scale_ok
                if not result["view_restored"]:
                    raise RuntimeError("View matrix/scale restoration readback mismatch")
            else:
                result["view_restored"] = not view_touched
        except Exception as exc:
            errors.append({"phase": "restore_view", "message": str(exc)[:1000]})
        try:
            if previous_id != target_id:
                com.CastTo(previous, "IKompasDocument").Active = True
            result["activation_restored"] = identity(app.ActiveDocument) == previous_id
            if not result["activation_restored"]:
                raise RuntimeError("Prior active document restoration readback mismatch")
        except Exception as exc:
            errors.append({"phase": "restore_activation", "message": str(exc)[:1000]})
        try:
            result["changed_after"] = bool(document.Changed)  # Never clear user dirty state.
        except Exception as exc:
            errors.append({"phase": "readback", "message": str(exc)[:1000]})
    result["ok"] = not errors and result["view_restored"] and result["activation_restored"]
    if errors:
        result["errors"] = errors
        result["error"] = "; ".join(item["phase"] + ": " + item["message"] for item in errors)
    return result
