import json
import os
import sys
import ctypes
import re
import math
import shutil
import uuid
from collections import defaultdict, deque
from win32com.client import Dispatch


def read_request(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_response(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def safe_get(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def _set_model_object_hidden(model_object, hidden=True, *, role=None):
    report = {
        "ok": False,
        "role": str(role or ""),
        "requested_hidden": bool(hidden),
        "reference": safe_get(model_object, "Reference"),
        "name": safe_get(model_object, "Name", ""),
    }
    if model_object is None:
        report["reason"] = "missing_object"
        return report

    def commit_visibility_update():
        update = safe_get(model_object, "Update")
        if not callable(update):
            report["update_available"] = False
            return True
        report["update_available"] = True
        try:
            result = update()
        except Exception as exc:
            report["update_ok"] = False
            report["update_error"] = str(exc)
            return False
        report["update_ok"] = bool(result)
        return bool(result)

    current_hidden = safe_get(model_object, "Hidden")
    if current_hidden is not None:
        report["hidden_before"] = bool(current_hidden)
        try:
            model_object.Hidden = bool(hidden)
        except Exception as exc:
            report["reason"] = "hidden_property_update_failed"
            report["error"] = str(exc)
            return report
        update_ok = commit_visibility_update()
        applied_hidden = safe_get(model_object, "Hidden")
        report["hidden_after"] = bool(applied_hidden) if applied_hidden is not None else None
        report["ok"] = applied_hidden is not None and bool(applied_hidden) == bool(hidden) and update_ok
        if not report["ok"]:
            if not update_ok:
                report["reason"] = "visibility_update_failed"
            else:
                report["reason"] = "hidden_property_state_mismatch"
        return report

    current_visible = safe_get(model_object, "Visible")
    if current_visible is None:
        report["reason"] = "hidden_property_unavailable"
        return report
    report["visible_before"] = bool(current_visible)
    try:
        model_object.Visible = not bool(hidden)
    except Exception as exc:
        report["reason"] = "visible_property_update_failed"
        report["error"] = str(exc)
        return report
    update_ok = commit_visibility_update()
    applied_visible = safe_get(model_object, "Visible")
    report["visible_after"] = bool(applied_visible) if applied_visible is not None else None
    report["ok"] = applied_visible is not None and bool(applied_visible) == (not bool(hidden)) and update_ok
    if not report["ok"]:
        if not update_ok:
            report["reason"] = "visibility_update_failed"
        else:
            report["reason"] = "visible_property_state_mismatch"
    return report


def _hide_auxiliary_model_objects(objects_by_role, hidden=True):
    reports = []
    for role, model_object in objects_by_role:
        reports.append(_set_model_object_hidden(model_object, hidden, role=role))
    return {
        "hidden": bool(hidden),
        "ok": all(item.get("ok") for item in reports),
        "objects": reports,
    }


def _iter_operation_variables(model_object):
    owner = safe_get(model_object, "Owner") or model_object
    variables_accessor = safe_get(owner, "Variables")
    variables = None
    if callable(variables_accessor):
        for args in ((False, False), (True, True), tuple()):
            try:
                variables = variables_accessor(*args)
                if variables is not None:
                    break
            except Exception:
                continue
    if variables is None:
        variables = safe_get(owner, "Variables")
    if variables is None:
        return []

    result = []
    count = safe_get(variables, "Count")
    if count is not None:
        try:
            count_int = int(count)
        except Exception:
            count_int = 0
        item_accessor = safe_get(variables, "Item")
        if callable(item_accessor):
            for index_base in (0, 1):
                batch = []
                failed = False
                for index in range(index_base, count_int + index_base):
                    try:
                        item = item_accessor(index)
                    except Exception:
                        failed = True
                        break
                    if item is not None:
                        batch.append(item)
                if batch and not failed:
                    return batch
                result.extend(batch)
        if result:
            return result

    try:
        return [item for item in variables]
    except Exception:
        return []


def _bind_operation_variables(model_object, planned_bindings):
    report = {
        "step": "bind_operation_variables",
        "ok": True,
        "planned_count": len(planned_bindings or []),
        "applied_count": 0,
        "failed_count": 0,
        "applied": [],
        "failed": [],
    }
    if not planned_bindings:
        report["live_status"] = "disabled"
        return report
    variables = _iter_operation_variables(model_object)
    if not variables:
        report["ok"] = False
        report["failed_count"] = len(planned_bindings)
        report["failed"] = [{"binding": binding, "error": "operation_variables_unavailable"} for binding in planned_bindings]
        report["live_status"] = "failed"
        return report

    for binding in planned_bindings:
        try:
            expression = str(binding.get("expression") or "").strip()
            if not expression:
                raise RuntimeError("expression_required")
            aliases = []
            if binding.get("parameter_note") not in (None, ""):
                aliases.append(str(binding.get("parameter_note")))
            aliases.extend([str(item) for item in (binding.get("parameter_note_aliases") or []) if str(item or "").strip()])
            target_name = str(binding.get("name") or "").strip()
            matched = None
            for variable in variables:
                note = str(safe_get(variable, "ParameterNote", "") or "")
                name = str(safe_get(variable, "Name", "") or "")
                if target_name and name == target_name:
                    matched = variable
                    break
                if aliases and note in aliases:
                    matched = variable
                    break
            if matched is None:
                raise RuntimeError("operation_variable_not_found")
            before_expression = safe_get(matched, "Expression")
            matched.Expression = expression
            update = safe_get(matched, "Update")
            variable_update_ok = True
            if callable(update):
                variable_update_ok = bool(update())
            object_update = safe_get(model_object, "Update")
            object_update_ok = True
            if callable(object_update):
                object_update_ok = bool(object_update())
            if not variable_update_ok or not object_update_ok:
                raise RuntimeError("operation_variable_update_failed")
            report["applied_count"] += 1
            report["applied"].append(
                {
                    "binding": binding,
                    "name": safe_get(matched, "Name", ""),
                    "parameter_note": safe_get(matched, "ParameterNote", ""),
                    "expression_before": before_expression,
                    "expression_after": safe_get(matched, "Expression"),
                    "variable_update_ok": variable_update_ok,
                    "object_update_ok": object_update_ok,
                }
            )
        except Exception as exc:
            report["failed"].append({"binding": binding, "error": str(exc)})

    report["failed_count"] = len(report["failed"])
    report["ok"] = report["failed_count"] == 0
    report["live_status"] = "applied" if report["ok"] else "partial"
    if report["applied_count"] == 0 and report["failed_count"] > 0:
        report["live_status"] = "failed"
    return report


MATERIAL_CATALOG = (
    {
        "name": "Сталь 10 ГОСТ 1050-2013",
        "density": 7.856,
        "aliases": ("сталь 10", "steel 10", "сталь10", "steel10"),
    },
    {
        "name": "Сталь 45 ГОСТ 1050-2013",
        "density": 7.85,
        "aliases": ("сталь 45", "steel 45", "сталь45", "steel45"),
    },
)
NEW_PART_DOCUMENT_SETTINGS_IID = "{7F3EEBF4-9277-4603-AD0A-C8DE1624F444}"
SKETCH_CONSTRAINT_TYPES = {
    "fixed_point": 1,
    "point_on_curve": 2,
    "horizontal": 3,
    "vertical": 4,
    "parallel": 5,
    "perpendicular": 6,
    "equal_length": 7,
    "h_align_points": 9,
    "v_align_points": 10,
    "merge_points": 11,
    "tangent": 15,
    "collinear": 17,
    "fixed_length": 19,
    "concentricity": 22,
}
LINE_DIMENSION_ORIENTATIONS = {
    "parallel": 0,
    "horizontal": 1,
    "vertical": 2,
}


def normalize_material_key(value):
    text = str(value or "").strip().lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


MATERIAL_ALIAS_INDEX = {
    normalize_material_key(alias): {"name": entry["name"], "density": entry["density"]}
    for entry in MATERIAL_CATALOG
    for alias in entry["aliases"]
}


def resolve_material_payload(material, density=None):
    text = str(material or "").strip()
    density_value = None
    if density not in (None, ""):
        density_value = float(density)
    if not text:
        return {"material": "", "density": density_value, "catalog_matched": False}
    matched = MATERIAL_ALIAS_INDEX.get(normalize_material_key(text))
    if matched is None:
        return {"material": text, "density": density_value, "catalog_matched": False}
    return {
        "material": matched["name"],
        "density": density_value if density_value is not None else matched["density"],
        "catalog_matched": True,
    }


def normalize_display_path(path):
    if not path:
        return path
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.kernel32.GetLongPathNameW(path, buffer, len(buffer))
        if result:
            return buffer.value
    except Exception:
        pass
    return path


def get_short_path(path):
    if not path:
        return path
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.kernel32.GetShortPathNameW(path, buffer, len(buffer))
        if result:
            return buffer.value
    except Exception:
        pass
    return path


def normalize_fs_path(path):
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def build_path_aliases(path):
    aliases = set()
    if not path:
        return aliases
    for candidate in (path, normalize_display_path(path), get_short_path(path)):
        normalized = normalize_fs_path(candidate)
        if normalized:
            aliases.add(normalized)
    return aliases


def replace_file_path(source_path, target_path):
    if hasattr(os, "replace"):
        return os.replace(source_path, target_path)

    MOVEFILE_REPLACE_EXISTING = 0x1
    MOVEFILE_WRITE_THROUGH = 0x8
    move_file_ex = getattr(ctypes.windll.kernel32, "MoveFileExW", None)
    if move_file_ex is None:
        raise RuntimeError("os.replace is unavailable and MoveFileExW is not exposed")
    ok = move_file_ex(
        ctypes.c_wchar_p(source_path),
        ctypes.c_wchar_p(target_path),
        MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
    )
    if not ok:
        error_code = ctypes.windll.kernel32.GetLastError()
        raise OSError("MoveFileExW failed with error %s" % error_code)


def document_open_diagnostics(path, payload, attempts):
    candidates = []
    if os.path.isdir(path):
        try:
            candidates = [
                os.path.join(path, name)
                for name in os.listdir(path)
                if os.path.splitext(name)[1].lower() in (".a3d", ".m3d", ".cdw", ".spw")
            ][:20]
        except Exception:
            candidates = []

    return {
        "path": path,
        "original_path": payload.get("original_path"),
        "exists": os.path.exists(path),
        "is_directory": os.path.isdir(path),
        "is_file": os.path.isfile(path),
        "size": os.path.getsize(path) if os.path.isfile(path) else None,
        "cwd": os.getcwd(),
        "attempts": attempts,
        "directory_candidates": candidates,
    }


def file_access_diagnostics(path):
    result = {
        "path": path,
        "exists": bool(path and os.path.exists(path)),
        "is_file": bool(path and os.path.isfile(path)),
        "size": os.path.getsize(path) if path and os.path.isfile(path) else None,
        "exclusive_open_ok": False,
        "error": None,
    }
    if not result["is_file"]:
        result["error"] = "not_a_file"
        return result

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    handle = ctypes.windll.kernel32.CreateFileW(
        path,
        GENERIC_READ | GENERIC_WRITE,
        0,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        error_code = ctypes.windll.kernel32.GetLastError()
        result["error"] = "CreateFileW failed with error %s" % error_code
        result["win32_error"] = error_code
        return result

    ctypes.windll.kernel32.CloseHandle(handle)
    result["exclusive_open_ok"] = True
    return result


def parse_close_mode(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return default


def ensure_backup_copy(target_path, backup_root):
    if not target_path or not os.path.exists(target_path):
        return None

    if not os.path.exists(backup_root):
        os.makedirs(backup_root)

    source_name = os.path.basename(target_path)
    source_stem, source_ext = os.path.splitext(source_name)
    candidate = os.path.join(backup_root, source_name)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(backup_root, "%s-%s%s" % (source_stem, counter, source_ext))
        counter += 1

    import shutil

    shutil.copy2(target_path, candidate)
    return str(candidate)


def collection_count(collection):
    try:
        count = safe_get(collection, "Count", 0)
        if callable(count):
            count = count()
        return int(count or 0)
    except Exception:
        return 0


def get_collection_item(collection, index):
    for accessor_name in ("Part", "Item", "Point3D", "Sketch"):
        accessor = safe_get(collection, accessor_name)
        if accessor is None:
            continue
        for candidate in (index, index + 1):
            try:
                return accessor(candidate)
            except Exception:
                continue
    return None


def iter_collection(collection):
    count = collection_count(collection)
    items = []
    for index in range(count):
        item = get_collection_item(collection, index)
        if item is not None:
            items.append(item)
    return items


_APP5 = None


def make_app():
    import win32com.client
    global _APP5
    _APP5 = win32com.client.Dispatch("KOMPAS.Application.5")
    controller_api = getattr(_APP5, "ActivateControllerAPI", None)
    if callable(controller_api):
        controller_api()
    else:
        controller_api
    app7 = getattr(_APP5, "ksGetApplication7", None)
    if callable(app7):
        try:
            return app7()
        except Exception:
            return app7
    return app7


def detect_kind(part):
    if safe_get(part, "Detail", False):
        return "part"
    if collection_count(safe_get(part, "Parts")):
        return "assembly"
    return "component"


def serialize_part(part, node_id, parent_id):
    item = {
        "id": node_id,
        "parent_id": parent_id,
        "name": safe_get(part, "Name", ""),
        "designation": safe_get(part, "Marking", ""),
        "title": None,
        "material": safe_get(part, "Material", ""),
        "comment": safe_get(part, "Comment", ""),
        "mass": safe_get(part, "Mass"),
        "volume": safe_get(part, "Volume"),
        "density": safe_get(part, "Density"),
        "quantity": None,
        "kind": detect_kind(part),
        "source_path": normalize_display_path(safe_get(part, "FileName", "")),
        "reference": safe_get(part, "Reference"),
        "unique_number": safe_get(part, "UniqueNumber"),
        "unique_meta_object_key": safe_get(part, "UniqueMetaObjectKey"),
        "is_local": safe_get(part, "IsLocal"),
        "children": [],
    }

    children = []
    parts = safe_get(part, "Parts")
    if parts is not None:
        for index, child in enumerate(iter_collection(parts)):
            child_id = "%s/%s" % (node_id, index)
            children.append(serialize_part(child, child_id, node_id))
    children.extend(_serialize_part_model_object_children(part, node_id))

    item["children"] = children
    return item


def _serialize_part_model_object_children(part, node_id):
    model_container = cast_model_container(part)
    children = []
    for collection_name, accessors in (
        ("points3d", ("Points3D", "GetPoints3D")),
        ("sketches", ("Sketchs", "GetSketchs")),
    ):
        collection, _, _ = _resolve_model_object_collection(model_container, accessors)
        count = collection_count(collection)
        for index in range(count):
            obj = get_collection_item(collection, index)
            if obj is None:
                continue
            reference = safe_get(obj, "Reference")
            child_id = "%s/%s/%s" % (node_id, collection_name, reference if reference not in (None, "") else index)
            child_children = _serialize_sketch_entity_children(obj, child_id) if collection_name == "sketches" else []
            children.append(
                {
                    "id": child_id,
                    "parent_id": node_id,
                    "name": safe_get(obj, "Name", ""),
                    "designation": "",
                    "title": None,
                    "material": "",
                    "comment": "",
                    "mass": None,
                    "volume": None,
                    "density": None,
                    "quantity": None,
                    "kind": "model_object",
                    "model_object_collection": collection_name,
                    "model_object_type": safe_get(obj, "ModelObjectType"),
                    "source_path": "",
                    "reference": reference,
                    "unique_number": safe_get(obj, "UniqueNumber"),
                    "unique_meta_object_key": safe_get(obj, "UniqueMetaObjectKey"),
                    "is_local": None,
                    "origin": [safe_get(obj, "X"), safe_get(obj, "Y"), safe_get(obj, "Z")],
                    "sketch_entity_count": len(child_children),
                    "children": child_children,
                }
            )
    return children


def _serialize_sketch_entity_children(sketch, sketch_id):
    if not callable(safe_get(sketch, "BeginEdit")):
        sketch = _cast_to_com_interface(sketch, "ISketch")
    begin_edit = safe_get(sketch, "BeginEdit")
    end_edit = safe_get(sketch, "EndEdit")
    if not callable(begin_edit):
        return []
    sketch_doc = None
    try:
        sketch_doc = begin_edit()
        if sketch_doc is None:
            return []
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        children = []
        children.extend(_serialize_sketch_entity_collection(drawing_container, sketch_id, "segments", ("LineSegments", "GetLineSegments"), "segment"))
        children.extend(_serialize_sketch_entity_collection(drawing_container, sketch_id, "circles", ("Circles", "GetCircles"), "circle"))
        children.extend(_serialize_sketch_entity_collection(drawing_container, sketch_id, "points", ("Points", "GetPoints"), "point"))
        children.extend(_serialize_sketch_entity_collection(drawing_container, sketch_id, "arcs", ("Arcs", "GetArcs"), "arc"))
        children.extend(_serialize_sketch_entity_collection(drawing_container, sketch_id, "ellipses", ("Ellipses", "GetEllipses"), "ellipse"))
        return children
    except Exception:
        return []
    finally:
        if callable(end_edit) and sketch_doc is not None:
            try:
                end_edit()
            except Exception:
                pass


def _serialize_sketch_entity_collection(drawing_container, sketch_id, collection_name, accessors, entity_kind):
    collection, _, _ = _resolve_model_object_collection(drawing_container, accessors)
    count = collection_count(collection)
    children = []
    for index in range(count):
        entity = get_collection_item(collection, index)
        if entity is None:
            continue
        reference = safe_get(entity, "Reference")
        geometry = _sketch_entity_geometry(entity_kind, entity)
        fingerprint = _sketch_entity_fingerprint(entity_kind, geometry, reference)
        children.append(
            {
                "id": "%s/%s/%s" % (sketch_id, collection_name, reference if reference not in (None, "") else index),
                "parent_id": sketch_id,
                "name": safe_get(entity, "Name", ""),
                "designation": "",
                "title": None,
                "material": "",
                "comment": "",
                "mass": None,
                "volume": None,
                "density": None,
                "quantity": None,
                "kind": "sketch_entity",
                "sketch_entity_kind": entity_kind,
                "model_object_collection": collection_name,
                "source_path": "",
                "reference": reference,
                "fingerprint": fingerprint,
                "geometry": geometry,
                "line_style": safe_get(entity, "Style"),
                "children": [],
            }
        )
    return children


def _sketch_entity_geometry(entity_kind, entity):
    if entity_kind == "segment":
        return {
            "start": [_json_safe_scalar(safe_get(entity, "X1")), _json_safe_scalar(safe_get(entity, "Y1"))],
            "end": [_json_safe_scalar(safe_get(entity, "X2")), _json_safe_scalar(safe_get(entity, "Y2"))],
        }
    if entity_kind == "circle":
        return {
            "center": [_json_safe_scalar(safe_get(entity, "Xc")), _json_safe_scalar(safe_get(entity, "Yc"))],
            "radius": _json_safe_scalar(safe_get(entity, "Radius")),
        }
    if entity_kind == "point":
        return {"point": [_json_safe_scalar(safe_get(entity, "X")), _json_safe_scalar(safe_get(entity, "Y"))]}
    if entity_kind == "arc":
        return {
            "center": [_json_safe_scalar(safe_get(entity, "Xc")), _json_safe_scalar(safe_get(entity, "Yc"))],
            "radius": _json_safe_scalar(safe_get(entity, "Radius")),
            "start": [_json_safe_scalar(safe_get(entity, "X1")), _json_safe_scalar(safe_get(entity, "Y1"))],
            "end": [_json_safe_scalar(safe_get(entity, "X2")), _json_safe_scalar(safe_get(entity, "Y2"))],
            "direction": _json_safe_scalar(safe_get(entity, "Direction")),
        }
    if entity_kind == "ellipse":
        return {
            "center": [_json_safe_scalar(safe_get(entity, "Xc")), _json_safe_scalar(safe_get(entity, "Yc"))],
            "radius_x": _json_safe_scalar(safe_get(entity, "SemiAxisA", safe_get(entity, "Rx", safe_get(entity, "RadiusX")))),
            "radius_y": _json_safe_scalar(safe_get(entity, "SemiAxisB", safe_get(entity, "Ry", safe_get(entity, "RadiusY")))),
            "angle": _json_safe_scalar(safe_get(entity, "Angle")),
        }
    return {}


def _sketch_entity_fingerprint(entity_kind, geometry, reference):
    parts = [str(entity_kind), str(reference if reference not in (None, "") else "")]
    if entity_kind == "segment":
        parts.extend(str(value) for value in geometry.get("start", []))
        parts.extend(str(value) for value in geometry.get("end", []))
    elif entity_kind == "circle":
        parts.extend(str(value) for value in geometry.get("center", []))
        parts.append(str(geometry.get("radius")))
    elif entity_kind == "point":
        parts.extend(str(value) for value in geometry.get("point", []))
    elif entity_kind == "arc":
        parts.extend(str(value) for value in geometry.get("center", []))
        parts.append(str(geometry.get("radius")))
        parts.extend(str(value) for value in geometry.get("start", []))
        parts.extend(str(value) for value in geometry.get("end", []))
        parts.append(str(geometry.get("direction")))
    elif entity_kind == "ellipse":
        parts.extend(str(value) for value in geometry.get("center", []))
        parts.append(str(geometry.get("radius_x")))
        parts.append(str(geometry.get("radius_y")))
        parts.append(str(geometry.get("angle")))
    return "|".join(parts)


def _flatten_tree_entries(root):
    entries = []

    def walk(node):
        entries.append(node)
        for child in node.get("children") or []:
            walk(child)

    walk(root)
    return entries


def _snapshot_from_tree(document, app, tree):
    entries = _flatten_tree_entries(tree)
    counts = {
        "items": len(entries),
        "tree_nodes": len(entries),
        "indexed_items": len(entries),
    }
    return {
        "ok": True,
        "snapshot": {
            "document": describe_document(document, app),
            "summary": dict(counts),
            "counts": dict(counts),
            "manifest": {
                "counts": dict(counts),
                "item_index": {"entries": entries},
            },
        },
    }


MODEL_OBJECT_COLLECTION_SPECS = [
    ("sketches", ("Sketchs", "GetSketchs")),
    ("rotateds", ("Rotateds", "GetRotateds")),
    ("extrusions", ("Extrusions", "GetExtrusions")),
    ("evolutions", ("Evolutions", "GetEvolutions")),
    ("feature_patterns", ("FeaturePatterns", "GetFeaturePatterns")),
]


MODEL_OBJECT_SURFACE_COLLECTION_SPECS = [
    (
        "part",
        "top_part",
        (
            ("parts", ("Parts", "GetParts")),
            ("model_objects", ("ModelObjects", "GetModelObjects")),
            ("result_bodies", ("ResultBodies", "GetResultBodies")),
            ("bodies", ("Bodies", "GetBodies")),
        ),
    ),
    (
        "model_container",
        "model_container",
        (
            ("sketches", ("Sketchs", "GetSketchs")),
            ("rotateds", ("Rotateds", "GetRotateds")),
            ("extrusions", ("Extrusions", "GetExtrusions")),
            ("evolutions", ("Evolutions", "GetEvolutions")),
            ("feature_patterns", ("FeaturePatterns", "GetFeaturePatterns")),
            ("points3d", ("Points3D", "GetPoints3D")),
            ("curves3d", ("Curves3D", "GetCurves3D")),
            ("surfaces3d", ("Surfaces3D", "GetSurfaces3D")),
        ),
    ),
    (
        "auxiliary_geometry",
        "auxiliary_geometry_container",
        (
            ("axes3d", ("Axes3D", "GetAxes3D")),
            ("planes3d", ("Planes3D", "GetPlanes3D")),
            ("local_coordinate_systems", ("LocalCoordinateSystems", "GetLocalCoordinateSystems")),
            ("points3d", ("Points3D", "GetPoints3D")),
        ),
    ),
]


def _json_safe_scalar(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    try:
        return str(value)
    except Exception:
        return None


def _describe_model_probe_object(obj, index):
    preview = {
        "index": index,
        "com_type": obj.__class__.__name__ if obj is not None else None,
    }
    for attr in (
        "Name",
        "Reference",
        "UniqueNumber",
        "UniqueMetaObjectKey",
        "Hidden",
        "Visible",
        "Changed",
        "Type",
    ):
        value = safe_get(obj, attr)
        if value is not None:
            preview[attr[:1].lower() + attr[1:]] = _json_safe_scalar(value)
    return preview


def _resolve_model_object_collection(container, accessor_names):
    errors = []
    for accessor_name in accessor_names:
        value = safe_get(container, accessor_name)
        if value is None:
            continue
        is_collection_like = any(safe_get(value, attr) is not None for attr in ("Count", "Item", "Add"))
        if callable(value) and (accessor_name.startswith("Get") or not is_collection_like):
            try:
                value = value()
            except Exception as exc:
                errors.append({"accessor": accessor_name, "error": str(exc), "type": exc.__class__.__name__})
                continue
        return value, accessor_name, errors
    return None, None, errors


def _probe_collection_entry(name, accessors, container, max_items):
    collection, accessor, errors = _resolve_model_object_collection(container, accessors)
    available = collection is not None
    count = collection_count(collection) if available else 0
    truncated = count > max_items
    preview = []
    if available and max_items:
        for index in range(min(count, max_items)):
            item = get_collection_item(collection, index)
            if item is not None:
                preview.append(_describe_model_probe_object(item, index))
    return {
        "name": name,
        "accessors": list(accessors),
        "accessor": accessor,
        "available": available,
        "count": count,
        "preview_count": len(preview),
        "preview": preview,
        "truncated": truncated,
        "errors": errors,
    }


def _probe_model_object_surface(surface_name, container_role, container, collection_specs, max_items, include_empty):
    container_available = container is not None
    collections = []
    total_items = 0
    available_count = 0
    nonempty_count = 0
    truncated_count = 0

    for collection_name, accessors in collection_specs:
        entry = _probe_collection_entry(collection_name, accessors, container, max_items)
        total_items += entry["count"]
        if entry["available"]:
            available_count += 1
        if entry["count"]:
            nonempty_count += 1
        if entry["truncated"]:
            truncated_count += 1
        if not include_empty and not entry["count"]:
            continue
        collections.append(entry)

    return {
        "name": surface_name,
        "container_role": container_role,
        "container_available": container_available,
        "container_type": container.__class__.__name__ if container is not None else None,
        "summary": {
            "collection_count": len(collections),
            "available_count": available_count,
            "nonempty_count": nonempty_count,
            "total_items": total_items,
            "truncated_count": truncated_count,
        },
        "collections": collections,
    }


def probe_model_object_surfaces(part, model_container, max_items=5, include_empty=True):
    auxiliary_container = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    containers = {
        "top_part": part,
        "model_container": model_container,
        "auxiliary_geometry_container": auxiliary_container,
    }
    surfaces = []
    total_items = 0
    available_surfaces = 0
    nonempty_surfaces = 0
    for surface_name, container_role, collection_specs in MODEL_OBJECT_SURFACE_COLLECTION_SPECS:
        surface = _probe_model_object_surface(
            surface_name,
            container_role,
            containers.get(container_role),
            collection_specs,
            max_items,
            include_empty,
        )
        total_items += surface["summary"]["total_items"]
        if surface["container_available"]:
            available_surfaces += 1
        if surface["summary"]["total_items"]:
            nonempty_surfaces += 1
        surfaces.append(surface)
    return {
        "summary": {
            "surface_count": len(surfaces),
            "available_surface_count": available_surfaces,
            "nonempty_surface_count": nonempty_surfaces,
            "total_items": total_items,
            "max_items": max_items,
        },
        "surfaces": surfaces,
    }


def probe_model_object_collections(part, max_items=5, include_empty=True):
    try:
        max_items = int(max_items)
    except Exception:
        max_items = 5
    max_items = max(0, min(max_items, 50))
    include_empty = bool(include_empty)

    model_container = cast_model_container(part)
    collections = []
    total_items = 0
    available_count = 0
    nonempty_count = 0
    truncated_count = 0

    for name, accessors in MODEL_OBJECT_COLLECTION_SPECS:
        entry = _probe_collection_entry(name, accessors, model_container, max_items)
        count = entry["count"]
        total_items += count
        if entry["available"]:
            available_count += 1
        if count:
            nonempty_count += 1
        if entry["truncated"]:
            truncated_count += 1
        if not include_empty and not count:
            continue
        collections.append(entry)

    surface_probe = probe_model_object_surfaces(
        part,
        model_container,
        max_items=max_items,
        include_empty=include_empty,
    )

    return {
        "summary": {
            "collection_count": len(collections),
            "available_count": available_count,
            "nonempty_count": nonempty_count,
            "total_items": total_items,
            "truncated_count": truncated_count,
            "surface_count": surface_probe["summary"]["surface_count"],
            "surface_total_items": surface_probe["summary"]["total_items"],
            "max_items": max_items,
        },
        "collections": collections,
        "surfaces": surface_probe["surfaces"],
        "limitations": [
            "Probe reports known model-container, part, and auxiliary collection accessors only.",
            "Preview is bounded and does not serialize geometry bodies or sketch entities.",
        ],
    }


def probe_runtime_objects(runtime_objects, max_items=5):
    try:
        max_items = int(max_items)
    except Exception:
        max_items = 5
    max_items = max(0, min(max_items, 50))

    operations = []
    output_type_counts = {}
    object_type_counts = {}
    total_outputs = 0
    preview_count = 0
    for operation_id in sorted((runtime_objects or {}).keys()):
        runtime_payload = runtime_objects.get(operation_id) or {}
        if not isinstance(runtime_payload, dict):
            operations.append(
                {
                    "id": str(operation_id),
                    "ok": False,
                    "error": "runtime payload is not an object",
                    "payload_type": runtime_payload.__class__.__name__,
                }
            )
            continue
        outputs = []
        declared_outputs = sorted(
            str(name).strip()
            for name in (((runtime_payload.get("preview") or {}).get("interface") or {}).get("outputs") or {}).keys()
            if str(name).strip()
        )
        if not declared_outputs:
            declared_outputs = sorted(
                str(name)
                for name in runtime_payload.keys()
                if name not in ("scenario", "preview", "params")
            )
        output_errors = []
        resolved_output_count = 0
        for output_key in declared_outputs:
            try:
                output_payload = _resolve_runtime_workflow_output(runtime_objects, operation_id, output_key)
            except Exception as exc:
                output_errors.append(
                    {
                        "key": str(output_key),
                        "error": str(exc),
                        "type": exc.__class__.__name__,
                    }
                )
                continue
            total_outputs += 1
            resolved_output_count += 1
            output_type = str(output_payload.get("type") or "unknown")
            output_type_counts[output_type] = output_type_counts.get(output_type, 0) + 1
            obj = output_payload.get("object")
            if obj is not None:
                object_type = obj.__class__.__name__
                object_type_counts[object_type] = object_type_counts.get(object_type, 0) + 1
            if preview_count >= max_items:
                continue
            entry = {
                "key": str(output_key),
                "type": output_type,
                "has_object": obj is not None,
            }
            for key in ("name", "role", "origin", "direction", "selector"):
                if key in output_payload:
                    entry[key] = output_payload.get(key)
            if obj is not None:
                entry["object"] = _describe_model_probe_object(obj, preview_count)
            outputs.append(entry)
            preview_count += 1
        operations.append(
            {
                "id": str(operation_id),
                "scenario": str(runtime_payload.get("scenario") or ""),
                "declared_output_count": len(declared_outputs),
                "resolved_output_count": resolved_output_count,
                "output_preview_count": len(outputs),
                "outputs": outputs,
                "errors": output_errors,
            }
        )
    return {
        "summary": {
            "operation_count": len(runtime_objects or {}),
            "total_outputs": total_outputs,
            "preview_count": preview_count,
            "truncated": total_outputs > preview_count,
            "max_items": max_items,
            "output_type_counts": output_type_counts,
            "object_type_counts": object_type_counts,
        },
        "operations": operations,
        "limitations": [
            "Runtime object probe inspects transient workflow handles before save/close.",
            "Preview is bounded and does not serialize geometry bodies or sketch entities.",
        ],
    }


def build_part_index(part, node_id, index):
    index[node_id] = part
    parts = safe_get(part, "Parts")
    if parts is None:
        return

    for child_index, child in enumerate(iter_collection(parts)):
        child_id = "%s/%s" % (node_id, child_index)
        build_part_index(child, child_id, index)


def iter_parts_with_ids(part, node_id):
    items = []
    parts = safe_get(part, "Parts")
    if parts is None:
        return items

    for child_index, child in enumerate(iter_collection(parts)):
        child_id = "%s/%s" % (node_id, child_index)
        items.append((child_id, child))
        items.extend(iter_parts_with_ids(child, child_id))
    return items


def describe_document(document, app):
    path_name = normalize_display_path(safe_get(document, "PathName", ""))
    name = safe_get(document, "Name", "") or os.path.basename(path_name) or "Untitled"
    return {
        "id": path_name or name,
        "name": name,
        "path": path_name,
        "type": safe_get(document, "Type"),
        "active": document == safe_get(app, "ActiveDocument"),
        "changed": safe_get(document, "Changed"),
    }


def text_to_string(text):
    if text is None:
        return ""
    value = safe_get(text, "Str")
    if value is not None:
        return value
    try:
        return str(text)
    except Exception:
        return ""


def make_spec_column_key(column_name, block_number, column_type_number, number):
    base = column_name or "type_%s_%s" % (column_type_number, number)
    return "%s#%s" % (base, block_number)


def serialize_spec_column(column, index):
    items = []
    column_items = safe_get(column, "ColumnItems")
    if column_items is not None:
        for item_index, item in enumerate(iter_collection(column_items)):
            items.append(
                {
                    "index": item_index,
                    "value": safe_get(item, "Value"),
                    "value_type": safe_get(item, "ValueType"),
                    "visible": safe_get(item, "Visible"),
                    "key": safe_get(item, "Key"),
                }
            )

    text_value = text_to_string(safe_get(column, "Text"))
    if not text_value and items:
        text_value = " ".join(str(item.get("value", "")) for item in items if item.get("visible", True)).strip()

    column_name = safe_get(column, "ColumnName", "")
    column_type_number = safe_get(column, "ColumnTypeNumber")
    number = safe_get(column, "Number")
    block_number = safe_get(column, "BlockNumber")

    return {
        "index": index,
        "column_name": column_name,
        "column_type": safe_get(column, "ColumnType"),
        "column_type_number": column_type_number,
        "number": number,
        "block_number": block_number,
        "column_key": make_spec_column_key(column_name, block_number, column_type_number, number),
        "value_type": safe_get(column, "ValueType"),
        "attribute_number": safe_get(column, "AttributeNumber"),
        "text": text_value,
        "items": items,
    }


def serialize_spec_object(obj, object_id):
    columns = []
    column_texts = {}
    column_texts_by_key = {}
    column_keys = {}
    spec_columns = safe_get(obj, "Columns")
    if spec_columns is not None:
        for column_index, column in enumerate(iter_collection(spec_columns)):
            serialized_column = serialize_spec_column(column, column_index)
            columns.append(serialized_column)
            column_key = serialized_column.get("column_key")
            column_name = serialized_column.get("column_name") or "type_%s_%s" % (
                serialized_column.get("column_type_number"),
                serialized_column.get("number"),
            )
            column_texts_by_key[column_key] = serialized_column.get("text", "")

            current_key = column_keys.get(column_name)
            current_block = None
            if current_key:
                current_block = int(current_key.rsplit("#", 1)[-1])
            block_number = int(serialized_column.get("block_number") or 0)
            if current_key is None or (block_number == 0 and current_block != 0):
                column_texts[column_name] = serialized_column.get("text", "")
                column_keys[column_name] = column_key

    return {
        "object_id": object_id,
        "section": safe_get(obj, "Section"),
        "subsection": safe_get(obj, "Subsection"),
        "nested_section": safe_get(obj, "NestedSection"),
        "nested_block": safe_get(obj, "NestedBlock"),
        "object_type": safe_get(obj, "ObjectType"),
        "state": safe_get(obj, "State"),
        "first_on_sheet": safe_get(obj, "FirstOnSheet"),
        "increment_position": safe_get(obj, "IncrementPosition"),
        "group_object": safe_get(obj, "GroupObject"),
        "is_group_object": safe_get(obj, "IsGroupObject"),
        "is_first_object": safe_get(obj, "IsFirstObject"),
        "attribute_number": safe_get(obj, "AttributeNumber"),
        "reference": safe_get(obj, "Reference"),
        "unique_number": safe_get(obj, "UniqueNumber"),
        "unique_meta_object_key": safe_get(obj, "UniqueMetaObjectKey"),
        "fill_name_by_material": safe_get(obj, "FillNameByMaterial"),
        "columns": columns,
        "column_texts": column_texts,
        "column_texts_by_key": column_texts_by_key,
        "column_keys": column_keys,
    }


def serialize_spec_description(description, index, active_description=None, include_objects=False, max_objects=200):
    base_objects = safe_get(description, "BaseObjects")
    comment_objects = safe_get(description, "CommentObjects")
    payload = {
        "index": index,
        "active": bool(active_description is not None and description == active_description),
        "layout_name": safe_get(description, "LayoutName", ""),
        "specification_document_name": safe_get(description, "SpecificationDocumentName", ""),
        "style_id": safe_get(description, "StyleID"),
        "show_all_objects": safe_get(description, "ShowAllObjects"),
        "show_excluded_objects": safe_get(description, "ShowExcludedObjects"),
        "show_on_sheet": safe_get(description, "ShowOnSheet"),
        "delegate_mode": safe_get(description, "DelegateMode"),
        "need_rebuild": safe_get(description, "NeedRebuild"),
        "performance_count": safe_get(description, "PerformanceCount"),
        "base_objects_count": collection_count(base_objects),
        "comment_objects_count": collection_count(comment_objects),
    }

    if include_objects:
        limit = max(0, int(max_objects or 0))
        base_items = []
        for object_index, base_object in enumerate(iter_collection(base_objects)):
            if limit and object_index >= limit:
                break
            base_items.append(serialize_spec_object(base_object, "base/%s" % object_index))
        comment_items = []
        for object_index, comment_object in enumerate(iter_collection(comment_objects)):
            if limit and object_index >= limit:
                break
            comment_items.append(serialize_spec_object(comment_object, "comment/%s" % object_index))
        payload["base_objects"] = base_items
        payload["comment_objects"] = comment_items
        payload["truncated"] = bool(limit and payload["base_objects_count"] > len(base_items))

    return payload


def _delete_all_specification_descriptions(document):
    descriptions = safe_get(document, "SpecificationDescriptions")
    if descriptions is None:
        return 0

    deleted = 0
    while collection_count(descriptions):
        description = get_collection_item(descriptions, 0)
        if description is None:
            break
        description.Delete()
        deleted += 1
    return deleted


def _build_created_specification_summary(description, deleted_descriptions):
    specification_payload = serialize_spec_description(
        description,
        0,
        active_description=description,
        include_objects=True,
        max_objects=max(collection_count(safe_get(description, "BaseObjects")), 1),
    )
    return {
        "deleted_descriptions": deleted_descriptions,
        "created_rows": specification_payload.get("base_objects_count", 0),
        "base_objects_count": specification_payload.get("base_objects_count", 0),
        "comment_objects_count": specification_payload.get("comment_objects_count", 0),
        "layout_name": specification_payload.get("layout_name", ""),
        "style_id": specification_payload.get("style_id"),
    }, specification_payload


def get_specification_descriptions(document):
    descriptions = safe_get(document, "SpecificationDescriptions")
    if descriptions is None:
        return None, [], None

    active_description = safe_get(descriptions, "Active")
    items = []
    for index, description in enumerate(iter_collection(descriptions)):
        items.append(serialize_spec_description(description, index, active_description=active_description, include_objects=False))
    return descriptions, items, active_description


def select_specification_description(document, payload):
    descriptions, items, active_description = get_specification_descriptions(document)
    if descriptions is None:
        return None, None, items, active_description

    description_index = payload.get("description_index")
    layout_name = payload.get("layout_name")
    if description_index is not None:
        try:
            description_index = int(description_index)
        except Exception:
            raise RuntimeError("description_index must be an integer")
        if description_index < 0 or description_index >= len(items):
            raise RuntimeError("description_index out of range")
        return get_collection_item(descriptions, description_index), description_index, items, active_description

    if layout_name:
        for index, description in enumerate(iter_collection(descriptions)):
            if safe_get(description, "LayoutName", "") == layout_name:
                return description, index, items, active_description
        raise RuntimeError("Specification description not found: %s" % layout_name)

    if active_description is not None:
        for index, description in enumerate(iter_collection(descriptions)):
            if description == active_description:
                return description, index, items, active_description
        return active_description, None, items, active_description
    if items:
        return get_collection_item(descriptions, 0), 0, items, active_description
    return None, None, items, active_description


def resolve_specification_object(description, object_id):
    if not object_id or "/" not in object_id:
        return None
    scope, index_text = object_id.split("/", 1)
    try:
        index = int(index_text)
    except Exception:
        return None

    if scope == "base":
        return get_collection_item(safe_get(description, "BaseObjects"), index)
    if scope == "comment":
        return get_collection_item(safe_get(description, "CommentObjects"), index)
    return None


def resolve_specification_column(spec_object, change):
    target_key = change.get("column_key")
    target_name = change.get("column_name")
    target_block = change.get("block_number")
    try:
        target_block = int(target_block)
    except Exception:
        target_block = None

    columns = safe_get(spec_object, "Columns")
    if columns is None:
        return None

    fallback = None
    for column in iter_collection(columns):
        column_name = safe_get(column, "ColumnName", "")
        column_key = make_spec_column_key(
            column_name,
            safe_get(column, "BlockNumber"),
            safe_get(column, "ColumnTypeNumber"),
            safe_get(column, "Number"),
        )
        if target_key and column_key == target_key:
            return column
        if target_name and column_name == target_name:
            if target_block is None or int(safe_get(column, "BlockNumber") or 0) == target_block:
                return column
            if fallback is None:
                fallback = column
    return fallback


SPW_COLUMN_TYPES = {
    "format": 1,
    "zone": 2,
    "position": 3,
    "designation": 4,
    "title": 5,
    "quantity": 6,
    "comment": 7,
}

SPW_DEFAULT_COLUMNS = [
    {"field": "position", "column_type": 3, "block_number": 1, "column_number": 0},
    {"field": "designation", "column_type": 4, "block_number": 1, "column_number": 0},
    {"field": "title", "column_type": 5, "block_number": 1, "column_number": 0},
    {"field": "quantity", "column_type": 6, "block_number": 1, "column_number": 0, "skip_unit_value": True},
    {"field": "comment", "column_type": 7, "block_number": 1, "column_number": 0},
]


def normalize_spw_column_payload(columns):
    aliases = {"name": "title", "qty": "quantity"}

    def as_bool(value, default=False):
        if value in (None, ""):
            return default
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    normalized = []
    for raw_column in columns or SPW_DEFAULT_COLUMNS:
        if isinstance(raw_column, str):
            column = {"field": raw_column}
        else:
            column = dict(raw_column)
        field = str(column.get("field") or "").strip().lower()
        field = aliases.get(field, field)
        if not field:
            continue
        normalized.append(
            {
                "field": field,
                "column_type": int(column.get("column_type") or column.get("type") or SPW_COLUMN_TYPES.get(field, 7)),
                "block_number": int(column.get("block_number") if column.get("block_number") not in (None, "") else column.get("block", 1)),
                "column_number": int(column.get("column_number") if column.get("column_number") not in (None, "") else column.get("number", 0)),
                "skip_unit_value": as_bool(column.get("skip_unit_value"), field == "quantity"),
                "label": column.get("label") or field,
            }
        )
    return normalized


def convert_spec_column_value(column, after):
    items = safe_get(column, "ColumnItems")
    item = get_collection_item(items, 0) if items is not None else None
    value_type = safe_get(item, "ValueType")
    if value_type is None:
        value_type = safe_get(column, "ValueType")

    if after is None:
        return ""
    if value_type == 1:
        return int(str(after).strip() or 0)
    if value_type == 2:
        return float(str(after).replace(",", "."))
    return str(after)


def list_documents(app):
    documents = safe_get(app, "Documents")
    if documents is None:
        return []
    return [describe_document(doc, app) for doc in iter_collection(documents)]


def resolve_document(app, document_id):
    active_document = safe_get(app, "ActiveDocument")
    if not document_id:
        return cast_document_3d(active_document)

    if active_document is not None:
        active_description = describe_document(active_document, app)
        if document_id in (active_description["id"], active_description["path"], active_description["name"]):
            return cast_document_3d(active_document)

    for document in iter_collection(safe_get(app, "Documents")):
        description = describe_document(document, app)
        if document_id in (description["id"], description["path"], description["name"]):
            return cast_document_3d(document)
    return None


def _open_document_in_app(app, path, visible=True, read_only=False):
    normalized_path = os.path.abspath(os.path.normpath(path))
    attempt_paths = [normalized_path]
    short_path = get_short_path(normalized_path)
    if short_path and normalize_fs_path(short_path) != normalize_fs_path(normalized_path):
        attempt_paths.append(short_path)

    document = None
    attempts = []
    for attempt_path in attempt_paths:
        try:
            document = app.Documents.Open(
                attempt_path,
                bool(visible),
                bool(read_only),
            )
            attempts.append({"path": attempt_path, "returned_document": document is not None})
        except Exception as exc:
            attempts.append({"path": attempt_path, "error": str(exc)})
            document = None
        if document is not None:
            break

    return cast_document_3d(document), attempts


def _build_save_staging_path(target_path):
    target_dir = os.path.dirname(target_path) or os.getcwd()
    target_name = os.path.basename(target_path)
    target_stem, target_ext = os.path.splitext(target_name)
    target_ext = target_ext or ".tmp"
    while True:
        candidate = os.path.join(
            target_dir,
            "%s.__kompas_mcp_stage__%s%s" % (target_stem or "document", uuid.uuid4().hex[:12], target_ext),
        )
        if normalize_fs_path(candidate) != normalize_fs_path(target_path) and not os.path.exists(candidate):
            return candidate


def _collect_open_documents_by_path(app, target_path, exclude_document=None):
    target_aliases = build_path_aliases(target_path)
    matches = []
    for document in iter_collection(safe_get(app, "Documents")):
        casted_document = cast_document_3d(document)
        if exclude_document is not None:
            try:
                if casted_document == exclude_document or document == exclude_document:
                    continue
            except Exception:
                pass
        description = describe_document(casted_document, app)
        if build_path_aliases(description.get("path")).intersection(target_aliases):
            matches.append({"document": casted_document, "description": description})
    return matches


def _replace_staging_file(app, staging_path, target_path, reopen_target=False, visible=True):
    target_path = os.path.abspath(os.path.normpath(target_path))
    matches = _collect_open_documents_by_path(app, target_path)
    report = {
        "mode": "staging_replace",
        "target_path": target_path,
        "staging_path": staging_path,
        "replaced_existing": bool(os.path.exists(target_path)),
        "open_target_documents": [match["description"] for match in matches],
        "closed_target_documents": [],
        "reopened_document": None,
        "reopen_attempts": [],
    }
    dirty_matches = [match["description"] for match in matches if match["description"].get("changed")]
    if dirty_matches:
        raise RuntimeError(
            "Target file is already open in KOMPAS with unsaved changes: %s"
            % json.dumps(dirty_matches, ensure_ascii=False)
        )

    for match in matches:
        try:
            match["document"].Close(0)
            report["closed_target_documents"].append(match["description"])
        except Exception as exc:
            raise RuntimeError(
                "Failed to close open target document before replace: %s | document=%s"
                % (exc, json.dumps(match["description"], ensure_ascii=False))
            )

    for _ in range(3):
        remaining_matches = _collect_open_documents_by_path(app, target_path)
        if not remaining_matches:
            break
        for match in remaining_matches:
            try:
                match["document"].Close(0)
                report["closed_target_documents"].append(match["description"])
            except Exception as exc:
                raise RuntimeError(
                    "Failed to close remaining target alias before replace: %s | document=%s"
                    % (exc, json.dumps(match["description"], ensure_ascii=False))
                )

    try:
        replace_file_path(staging_path, target_path)
    except Exception as exc:
        diagnostics = {
            "target_access": file_access_diagnostics(target_path),
            "staging_access": file_access_diagnostics(staging_path),
        }
        raise RuntimeError(
            "Failed to replace target file: %s | diagnostics=%s"
            % (exc, json.dumps(diagnostics, ensure_ascii=False))
        )

    if reopen_target or report["closed_target_documents"]:
        reopened_document, attempts = _open_document_in_app(app, target_path, visible=visible, read_only=False)
        report["reopen_attempts"] = attempts
        if reopened_document is None:
            raise RuntimeError(
                "Failed to reopen target document after replace | attempts=%s"
                % json.dumps(attempts, ensure_ascii=False)
            )
        report["reopened_document"] = describe_document(reopened_document, app)
        return reopened_document, report

    return None, report


def _save_document_via_staging(document, app, target_path, keep_open=False, visible=True):
    target_path = os.path.abspath(os.path.normpath(target_path))
    target_dir = os.path.dirname(target_path)
    if target_dir and not os.path.exists(target_dir):
        os.makedirs(target_dir)

    preexisting_matches = _collect_open_documents_by_path(app, target_path, exclude_document=document)
    dirty_matches = [match["description"] for match in preexisting_matches if match["description"].get("changed")]
    if dirty_matches:
        raise RuntimeError(
            "Target file is already open in KOMPAS with unsaved changes: %s"
            % json.dumps(dirty_matches, ensure_ascii=False)
        )

    staging_path = _build_save_staging_path(target_path)
    try:
        save_result = document.SaveAs(staging_path)
    except Exception as exc:
        raise RuntimeError("Failed to save staging document: %s" % exc)
    if not (bool(save_result) or os.path.exists(staging_path)):
        raise RuntimeError("Staging save did not create file: %s" % staging_path)

    document_description = describe_document(document, app)
    try:
        _close_generated_document(document, app)
    except Exception as exc:
        raise RuntimeError("Failed to close staging document before replace: %s" % exc)

    reopened_document, replace_report = _replace_staging_file(
        app,
        staging_path,
        target_path,
        reopen_target=bool(keep_open),
        visible=visible,
    )
    replace_report["source_document"] = document_description
    replace_report["kept_open"] = bool(keep_open)
    return reopened_document, replace_report


def cast_document_3d(document):
    if document is None:
        return None
    if safe_get(document, "TopPart") is not None:
        return document
    try:
        return Dispatch(document, "Document3D", "{7B60E769-06C3-4FDC-9677-7B5EF5180308}")
    except Exception:
        return document


def cast_model_container(part):
    if part is None:
        return None
    if safe_get(part, "Sketchs") is not None or safe_get(part, "Rotateds") is not None:
        return part
    try:
        import win32com.client

        return win32com.client.CastTo(part, "IModelContainer")
    except Exception:
        return part


def cast_drawing_container(view):
    if view is None:
        return None
    if safe_get(view, "LineSegments") is not None:
        return view
    try:
        import win32com.client

        return win32com.client.CastTo(view, "IDrawingContainer")
    except Exception:
        return view


def get_new_part_document_settings(app):
    system_settings = safe_get(app, "SystemSettings")
    if system_settings is None:
        return None
    new_document_settings = safe_get(system_settings, "NewDocumentSettings")
    if not callable(new_document_settings):
        return None
    raw_settings = new_document_settings(1)
    if raw_settings is None:
        return None
    return Dispatch(raw_settings, "INewPartDocumentSettings", NEW_PART_DOCUMENT_SETTINGS_IID)


def snapshot_new_part_document_settings(settings):
    return {
        "material": safe_get(settings, "Material", ""),
        "density": safe_get(settings, "Density"),
        "material_location": safe_get(settings, "MaterialLocation", ""),
    }


def restore_new_part_document_settings(settings, snapshot):
    settings.Material = snapshot.get("material", "")
    density = snapshot.get("density")
    if density not in (None, ""):
        settings.Density = float(density)
    settings.MaterialLocation = snapshot.get("material_location", "")


def apply_new_part_document_material_defaults(settings, params):
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))
    if not material_payload.get("material"):
        return material_payload
    settings.Material = material_payload["material"]
    if material_payload.get("density") not in (None, ""):
        settings.Density = float(material_payload["density"])
    params["material"] = material_payload["material"]
    if material_payload.get("density") not in (None, ""):
        params["density"] = material_payload["density"]
    return material_payload


def apply_part_properties(part, params):
    property_report = []
    material_payload = resolve_material_payload(params.get("material"), params.get("density"))
    material_name = material_payload.get("material")
    material_density = material_payload.get("density")
    for attr, value in (
        ("Name", params.get("name")),
        ("Marking", params.get("designation")),
        ("Comment", params.get("comment")),
    ):
        if not value:
            continue
        try:
            setattr(part, attr, value)
            actual = safe_get(part, attr)
            property_report.append({"property": attr, "ok": actual == value, "actual": actual})
        except Exception as exc:
            property_report.append({"property": attr, "ok": False, "error": str(exc)})
    if material_name:
        if params.get("_material_initialized_from_defaults"):
            actual = safe_get(part, "Material")
            actual_density = safe_get(part, "Density")
            property_report.append(
                {
                    "property": "Material",
                    "ok": actual == material_name and (material_density is None or actual_density is None or abs(float(actual_density) - float(material_density)) < 1e-6),
                    "actual": actual,
                    "density": actual_density,
                    "mode": "new_part_defaults",
                }
            )
        else:
            set_material = safe_get(part, "SetMaterial")
            try:
                density = float(material_density or safe_get(part, "Density", 7.85) or 7.85)
                if callable(set_material):
                    set_result = set_material(material_name, density)
                    actual = safe_get(part, "Material")
                    property_report.append(
                        {
                            "property": "Material",
                            "ok": set_result is not False and actual == material_name,
                            "actual": actual,
                            "density": density,
                        }
                    )
                else:
                    actual = safe_get(part, "Material")
                    property_report.append(
                        {"property": "Material", "ok": actual == material_name, "actual": actual, "density": density}
                    )
            except Exception as exc:
                property_report.append({"property": "Material", "ok": False, "error": str(exc)})
    updater = safe_get(part, "Update")
    if callable(updater):
        try:
            updater()
        except Exception:
            pass
    return property_report


def get_session_state():
    app = make_app()
    documents = list_documents(app)
    active_document = safe_get(app, "ActiveDocument")
    active_info = describe_document(active_document, app) if active_document is not None else None
    return {
        "kompas_connected": True,
        "visible": bool(safe_get(app, "Visible", False)),
        "documents_count": len(documents),
        "active_document": active_info,
    }


def handle_list_documents():
    app = make_app()
    return {"documents": list_documents(app)}


def handle_get_document_tree(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")

    return {
        "document": describe_document(document, app),
        "tree": serialize_part(top_part, "root", None),
    }


def handle_create_point3d(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    origin = payload.get("origin")
    if not isinstance(origin, list) or len(origin) != 3:
        raise RuntimeError("origin must contain exactly 3 coordinates")

    before_tree = serialize_part(top_part, "root", None)
    point = _create_point3d(model_container, payload.get("name") or "PT1", origin)
    updater = safe_get(top_part, "Update")
    update_ok = True
    if callable(updater):
        update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)

    return {
        "ok": True,
        "document": describe_document(document, app),
        "item": {
            "name": safe_get(point, "Name", payload.get("name")),
            "type": "Point3D",
            "origin": [safe_get(point, "X", 0.0), safe_get(point, "Y", 0.0), safe_get(point, "Z", 0.0)],
            "reference": safe_get(point, "Reference"),
        },
        "summary": {
            "name": safe_get(point, "Name", payload.get("name")),
            "update_ok": update_ok,
        },
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def _normalize_point2d_payload(value, name, default):
    values = list(default if value is None else value)
    if len(values) != 2:
        raise RuntimeError("%s must contain exactly 2 coordinates" % name)
    return [float(values[0]), float(values[1])]


def _normalize_sketch_plane(value):
    normalized = str(value or "XOY").strip().lower().replace("-", "_")
    aliases = {
        "xoy": "xoy_plane",
        "xy": "xoy_plane",
        "xoy_plane": "xoy_plane",
        "xoz": "xoz_plane",
        "xz": "xoz_plane",
        "xoz_plane": "xoz_plane",
        "yoz": "yoz_plane",
        "yz": "yoz_plane",
        "yoz_plane": "yoz_plane",
    }
    resolved = aliases.get(normalized)
    if resolved is None:
        raise RuntimeError("Unsupported sketch plane: %s" % value)
    return resolved


def _create_sketch_on_plane(model_container, part, name, plane):
    plane_key = _normalize_sketch_plane(plane)
    plane_object = _resolve_default_part_object(part, plane_key)
    sketchs = _get_sketch_collection(model_container)
    if sketchs is None or not callable(safe_get(sketchs, "Add")):
        raise RuntimeError("Part does not expose Sketchs.Add")
    sketch = sketchs.Add()
    if sketch is None:
        raise RuntimeError("Sketchs.Add returned None")
    sketch.Plane = plane_object
    if name:
        try:
            sketch.Name = str(name)
        except Exception:
            pass
    if not sketch.Update():
        raise RuntimeError("Sketch Update returned False")
    return sketch, plane_key


def _get_sketch_collection(model_container):
    sketchs = safe_get(model_container, "Sketchs")
    if sketchs is None:
        get_sketchs = safe_get(model_container, "GetSketchs")
        if callable(get_sketchs):
            sketchs = get_sketchs()
    return sketchs


def _resolve_existing_sketch(model_container, sketch_ref):
    sketchs = _get_sketch_collection(model_container)
    if sketchs is None:
        raise RuntimeError("unsupported COM shape: part does not expose Sketchs/GetSketchs")
    wanted = str(sketch_ref)
    for index in range(collection_count(sketchs)):
        sketch = get_collection_item(sketchs, index)
        if sketch is None:
            continue
        reference = safe_get(sketch, "Reference")
        if str(reference) == wanted:
            editable_sketch = sketch if callable(safe_get(sketch, "BeginEdit")) else _cast_to_com_interface(sketch, "ISketch")
            if not callable(safe_get(editable_sketch, "BeginEdit")):
                raise RuntimeError("unsupported COM shape: sketch_ref target does not expose ISketch.BeginEdit")
            return editable_sketch
    raise RuntimeError("ambiguous target: sketch_ref not found: %s" % wanted)


def _sketch_list_item(sketch, index):
    reference = safe_get(sketch, "Reference")
    return {
        "index": index,
        "collection_index": index,
        "type": "Sketch",
        "name": safe_get(sketch, "Name", ""),
        "reference": reference,
        "sketch_ref": reference,
    }


def _sketch_entity_counts(sketch):
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    try:
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        counts = {}
        for kind in ("segment", "circle", "point", "arc", "ellipse"):
            collection, collection_name = _collection_for_sketch_entity_kind(drawing_container, kind)
            counts[collection_name] = collection_count(collection)
        return counts
    finally:
        sketch.EndEdit()


def _list_existing_sketches(model_container, payload):
    sketchs = _get_sketch_collection(model_container)
    if sketchs is None:
        raise RuntimeError("unsupported COM shape: part does not expose Sketchs/GetSketchs")
    max_items = int(payload.get("max_items", 100))
    if max_items < 1:
        raise RuntimeError("invalid input: max_items must be greater than zero")
    name_contains = str(payload.get("name_contains") or "").strip().lower()
    include_entity_counts = bool(payload.get("include_entity_counts", False))

    items = []
    total = collection_count(sketchs)
    truncated = False
    for index in range(total):
        sketch = get_collection_item(sketchs, index)
        if sketch is None:
            continue
        item = _sketch_list_item(sketch, index)
        if name_contains and name_contains not in str(item.get("name") or "").lower():
            continue
        if len(items) >= max_items:
            truncated = True
            break
        if include_entity_counts:
            try:
                item["entity_counts"] = _sketch_entity_counts(sketch)
            except Exception as exc:
                item["entity_counts_error"] = str(exc)
        items.append(item)
    return items, {
        "sketch_count": len(items),
        "total_sketches": total,
        "truncated": truncated,
        "max_items": max_items,
        "include_entity_counts": include_entity_counts,
    }


def _rename_existing_sketch(model_container, payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    if sketch_ref in (None, ""):
        raise RuntimeError("invalid input: sketch_ref is required")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise RuntimeError("invalid input: name is required")
    sketch = _resolve_existing_sketch(model_container, sketch_ref)
    old_name = safe_get(sketch, "Name", "")
    sketch.Name = name
    update_ok = True
    updater = safe_get(sketch, "Update")
    if callable(updater):
        update_ok = bool(updater())
    return sketch, {
        "mode": "existing_sketch",
        "name": safe_get(sketch, "Name", name),
        "old_name": old_name,
        "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
    }, update_ok


def _get_sketch_system_view(sketch_doc):
    views_manager = safe_get(sketch_doc, "ViewsAndLayersManager")
    if views_manager is None:
        get_views_manager = safe_get(sketch_doc, "GetViewsAndLayersManager")
        if callable(get_views_manager):
            views_manager = get_views_manager()
    views = safe_get(views_manager, "Views") if views_manager is not None else None
    if views is None:
        raise RuntimeError("Sketch document does not expose ViewsAndLayersManager.Views")
    for accessor_name, accessor_arg in (("View", 0), ("Item", 0), ("View", 1), ("Item", 1)):
        accessor = safe_get(views, accessor_name)
        if not callable(accessor):
            continue
        try:
            view = accessor(accessor_arg)
            if view is not None:
                return view
        except Exception:
            continue
    raise RuntimeError("Failed to get sketch system view")


def _resolve_sketch_write_target(model_container, part, payload, default_name):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    mode = str(target.get("mode") or "").strip().lower()
    create_new = bool(payload.get("create_new_sketch", mode in ("", "create_new_sketch")))
    if sketch_ref not in (None, "") and (create_new or mode == "create_new_sketch"):
        raise RuntimeError("ambiguous target: provide sketch_ref or create_new_sketch, not both")
    if sketch_ref not in (None, "") or mode == "existing_sketch":
        if sketch_ref in (None, ""):
            raise RuntimeError("ambiguous target: existing_sketch requires sketch_ref")
        sketch = _resolve_existing_sketch(model_container, sketch_ref)
        return sketch, {
            "mode": "existing_sketch",
            "name": safe_get(sketch, "Name", ""),
            "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
        }
    if not create_new and mode != "create_new_sketch":
        raise RuntimeError("ambiguous target: create_new_sketch=false requires sketch_ref")
    name = target.get("name") or payload.get("name") or default_name
    plane = target.get("plane") or payload.get("plane") or "XOY"
    sketch, plane_key = _create_sketch_on_plane(model_container, part, name, plane)
    return sketch, {
        "mode": "create_new_sketch",
        "name": safe_get(sketch, "Name", name),
        "plane": plane_key,
        "sketch_ref": safe_get(sketch, "Reference"),
    }


def _get_sketch_drawing_container(sketch_doc):
    view = _get_sketch_system_view(sketch_doc)
    return cast_drawing_container(view)


def _get_add_collection(container, property_name, getter_name, label):
    collection = safe_get(container, property_name)
    if collection is None:
        getter = safe_get(container, getter_name)
        if callable(getter):
            collection = getter()
    if collection is None or not callable(safe_get(collection, "Add")):
        raise RuntimeError("Sketch view does not expose %s.Add" % label)
    return collection


def _apply_line_style(entity, line_style):
    try:
        entity.Style = int(line_style)
    except Exception:
        set_style = safe_get(entity, "SetStyle")
        if callable(set_style):
            set_style(int(line_style))
        else:
            raise


def _add_sketch_line_segment(drawing_container, start, end, line_style):
    line_segments = _get_add_collection(drawing_container, "LineSegments", "GetLineSegments", "LineSegments")
    line = line_segments.Add()
    if line is None:
        raise RuntimeError("LineSegments.Add returned None")
    line.X1 = float(start[0])
    line.Y1 = float(start[1])
    line.X2 = float(end[0])
    line.Y2 = float(end[1])
    _apply_line_style(line, line_style)
    if not line.Update():
        raise RuntimeError("LineSegment Update returned False")
    return line


def _add_sketch_circle(drawing_container, center, radius, line_style):
    circles = _get_add_collection(drawing_container, "Circles", "GetCircles", "Circles")
    circle = circles.Add()
    if circle is None:
        raise RuntimeError("Circles.Add returned None")
    circle.Xc = float(center[0])
    circle.Yc = float(center[1])
    circle.Radius = float(radius)
    _apply_line_style(circle, line_style)
    if not circle.Update():
        raise RuntimeError("Circle Update returned False")
    return circle


def _set_first_available_attr(entity, names, value):
    last_error = None
    for name in names:
        try:
            setattr(entity, name, value)
            return
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error


def _add_sketch_point(drawing_container, point, line_style):
    points = _get_add_collection(drawing_container, "Points", "GetPoints", "Points")
    created = points.Add()
    if created is None:
        raise RuntimeError("Points.Add returned None")
    created.X = float(point[0])
    created.Y = float(point[1])
    try:
        _apply_line_style(created, line_style)
    except Exception:
        pass
    if not created.Update():
        raise RuntimeError("Point Update returned False")
    return created


def _add_sketch_arc(drawing_container, center, radius, start, end, direction, line_style):
    arcs = _get_add_collection(drawing_container, "Arcs", "GetArcs", "Arcs")
    arc = arcs.Add()
    if arc is None:
        raise RuntimeError("Arcs.Add returned None")
    arc.Xc = float(center[0])
    arc.Yc = float(center[1])
    arc.Radius = float(radius)
    arc.X1 = float(start[0])
    arc.Y1 = float(start[1])
    arc.X2 = float(end[0])
    arc.Y2 = float(end[1])
    try:
        arc.Direction = bool(direction)
    except Exception:
        set_direction = safe_get(arc, "SetDirection")
        if callable(set_direction):
            set_direction(bool(direction))
    _apply_line_style(arc, line_style)
    if not arc.Update():
        raise RuntimeError("Arc Update returned False")
    return arc


def _add_sketch_ellipse(drawing_container, center, radius_x, radius_y, angle, line_style):
    ellipses = _get_add_collection(drawing_container, "Ellipses", "GetEllipses", "Ellipses")
    ellipse = ellipses.Add()
    if ellipse is None:
        raise RuntimeError("Ellipses.Add returned None")
    cx, cy = float(center[0]), float(center[1])
    rx, ry = float(radius_x), float(radius_y)
    ellipse.Xc = cx
    ellipse.Yc = cy
    _set_first_available_attr(ellipse, ("SemiAxisA", "Rx", "RadiusX"), rx)
    _set_first_available_attr(ellipse, ("SemiAxisB", "Ry", "RadiusY"), ry)
    _set_first_available_attr(ellipse, ("X1",), cx - rx)
    _set_first_available_attr(ellipse, ("Y1",), cy)
    _set_first_available_attr(ellipse, ("X2",), cx + rx)
    _set_first_available_attr(ellipse, ("Y2",), cy)
    try:
        ellipse.Angle = float(angle)
    except Exception:
        pass
    _apply_line_style(ellipse, line_style)
    if not ellipse.Update():
        raise RuntimeError("Ellipse Update returned False")
    return ellipse


def _add_sketch_polyline(drawing_container, points, closed, line_style):
    created = []
    pairs = list(zip(points, points[1:]))
    if closed and len(points) > 2:
        pairs.append((points[-1], points[0]))
    for start, end in pairs:
        created.append(_add_sketch_line_segment(drawing_container, start, end, line_style))
    return created


def _add_sketch_rectangle(drawing_container, corner1, corner2, line_style):
    lines = []
    x1, y1 = float(corner1[0]), float(corner1[1])
    x2, y2 = float(corner2[0]), float(corner2[1])
    for start, end in (([x1, y1], [x2, y1]), ([x2, y1], [x2, y2]), ([x2, y2], [x1, y2]), ([x1, y2], [x1, y1])):
        lines.append(_add_sketch_line_segment(drawing_container, start, end, line_style))
    return lines


def _create_sketch_entities(model_container, part, payload):
    sketch, target = _resolve_sketch_write_target(model_container, part, payload, "SKETCH_BATCH_1")
    entities = payload.get("entities")
    if not isinstance(entities, list) or not entities:
        raise RuntimeError("invalid input: entities must be a non-empty list")
    planned_constraints = payload.get("constraints") or []
    planned_dimensions = payload.get("dimensions") or []
    if not isinstance(planned_constraints, list):
        raise RuntimeError("invalid input: constraints must be a list")
    if not isinstance(planned_dimensions, list):
        raise RuntimeError("invalid input: dimensions must be a list")
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    results = []
    sketch_entities = {}
    parameterization_report = None
    try:
        view = _get_sketch_system_view(sketch_doc)
        drawing_container = cast_drawing_container(view)
        for index, entity in enumerate(entities):
            if not isinstance(entity, dict):
                raise RuntimeError("invalid input: entities[%s] must be an object" % index)
            kind = str(entity.get("kind") or "").strip().lower()
            entity_id = str(entity.get("entity_id") or entity.get("id") or "entity_%s" % (index + 1))
            role = str(entity.get("role") or kind)
            if kind == "segment":
                collection_index = _sketch_entity_collection_count(drawing_container, "segment")
                created = _add_sketch_line_segment(drawing_container, entity.get("start"), entity.get("end"), int(entity.get("line_style", 1)))
                start, end = entity.get("start"), entity.get("end")
                sketch_entities[entity_id] = _sketch_line_entry(created, start[0], start[1], end[0], end[1], role=role, target=entity_id)
                results.append({"index": index, "id": entity_id, "kind": kind, "ok": True, "reference": safe_get(created, "Reference"), "collection_index": collection_index})
            elif kind == "circle":
                collection_index = _sketch_entity_collection_count(drawing_container, "circle")
                created = _add_sketch_circle(drawing_container, entity.get("center"), float(entity.get("radius")), int(entity.get("line_style", 1)))
                center = entity.get("center")
                sketch_entities[entity_id] = _sketch_circle_entry(created, center[0], center[1], entity.get("radius"), role=role, target=entity_id)
                results.append({"index": index, "id": entity_id, "kind": kind, "ok": True, "reference": safe_get(created, "Reference"), "collection_index": collection_index})
            elif kind == "point":
                collection_index = _sketch_entity_collection_count(drawing_container, "point")
                created = _add_sketch_point(drawing_container, entity.get("point"), int(entity.get("line_style", 1)))
                point = entity.get("point")
                sketch_entities[entity_id] = _sketch_point_entry(created, point[0], point[1], role="point", target=entity_id)
                results.append({"index": index, "id": entity_id, "kind": kind, "ok": True, "reference": safe_get(created, "Reference"), "collection_index": collection_index})
            elif kind == "polyline":
                points = list(entity.get("points") or [])
                closed = bool(entity.get("closed", False))
                collection_index = _sketch_entity_collection_count(drawing_container, "segment")
                lines = _add_sketch_polyline(drawing_container, points, closed, int(entity.get("line_style", 1)))
                line_ids = []
                collection_indices = []
                pairs = list(zip(points, points[1:]))
                if closed and len(points) > 2:
                    pairs.append((points[-1], points[0]))
                for line_index, (line, pair) in enumerate(zip(lines, pairs), start=1):
                    line_id = "%s_%s" % (entity_id, line_index)
                    start, end = pair
                    sketch_entities[line_id] = _sketch_line_entry(line, start[0], start[1], end[0], end[1], role=role, target=line_id)
                    line_ids.append(line_id)
                    collection_indices.append(collection_index + line_index - 1 if collection_index is not None else None)
                if line_ids:
                    sketch_entities[entity_id] = sketch_entities[line_ids[0]]
                results.append({"index": index, "id": entity_id, "entity_ids": line_ids, "kind": kind, "ok": True, "line_count": len(lines), "reference": safe_get(lines[0], "Reference") if lines else None, "collection_index": collection_index, "collection_indices": collection_indices})
            elif kind == "arc":
                collection_index = _sketch_entity_collection_count(drawing_container, "arc")
                created = _add_sketch_arc(drawing_container, entity.get("center"), float(entity.get("radius")), entity.get("start"), entity.get("end"), bool(entity.get("direction", True)), int(entity.get("line_style", 1)))
                center, start, end = entity.get("center"), entity.get("start"), entity.get("end")
                sketch_entities[entity_id] = _sketch_arc_entry(
                    created, center[0], center[1], entity.get("radius"), start[0], start[1], end[0], end[1],
                    direction=bool(entity.get("direction", True)), role=role, target=entity_id,
                )
                results.append({"index": index, "id": entity_id, "kind": kind, "ok": True, "reference": safe_get(created, "Reference"), "collection_index": collection_index})
            elif kind == "ellipse":
                collection_index = _sketch_entity_collection_count(drawing_container, "ellipse")
                created = _add_sketch_ellipse(drawing_container, entity.get("center"), float(entity.get("radius_x")), float(entity.get("radius_y")), float(entity.get("angle", 0.0)), int(entity.get("line_style", 1)))
                center = entity.get("center")
                sketch_entities[entity_id] = {
                    "object": created,
                    "role": role,
                    "target": entity_id,
                    "xc": float(center[0]),
                    "yc": float(center[1]),
                    "radius_x": float(entity.get("radius_x")),
                    "radius_y": float(entity.get("radius_y")),
                    "angle": float(entity.get("angle", 0.0)),
                }
                results.append({"index": index, "id": entity_id, "kind": kind, "ok": True, "reference": safe_get(created, "Reference"), "collection_index": collection_index})
            elif kind == "rectangle":
                corner1, corner2 = entity.get("corner1"), entity.get("corner2")
                collection_index = _sketch_entity_collection_count(drawing_container, "segment")
                lines = _add_sketch_rectangle(drawing_container, corner1, corner2, int(entity.get("line_style", 1)))
                x1, y1 = float(corner1[0]), float(corner1[1])
                x2, y2 = float(corner2[0]), float(corner2[1])
                pairs = (([x1, y1], [x2, y1]), ([x2, y1], [x2, y2]), ([x2, y2], [x1, y2]), ([x1, y2], [x1, y1]))
                line_ids = []
                collection_indices = []
                for line_index, (line, pair) in enumerate(zip(lines, pairs), start=1):
                    line_id = "%s_%s" % (entity_id, line_index)
                    start, end = pair
                    sketch_entities[line_id] = _sketch_line_entry(line, start[0], start[1], end[0], end[1], role=role, target=line_id)
                    line_ids.append(line_id)
                    collection_indices.append(collection_index + line_index - 1 if collection_index is not None else None)
                if line_ids:
                    sketch_entities[entity_id] = sketch_entities[line_ids[0]]
                results.append({"index": index, "id": entity_id, "entity_ids": line_ids, "kind": kind, "ok": True, "line_count": len(lines), "reference": safe_get(lines[0], "Reference") if lines else None, "collection_index": collection_index, "collection_indices": collection_indices})
            else:
                raise RuntimeError("invalid input: unsupported sketch entity kind: %s" % (kind or "<missing>"))
        if planned_constraints or planned_dimensions:
            sketch_options = dict(payload.get("sketch_options") or payload.get("sketch") or {})
            constraint_options = dict(sketch_options.get("constraints") or {})
            dimension_options = dict(sketch_options.get("dimensions") or {})
            if planned_constraints:
                constraint_options.setdefault("enabled", True)
            if planned_dimensions:
                dimension_options.setdefault("enabled", True)
                dimension_options.setdefault("driving", True)
            sketch_options["constraints"] = constraint_options
            sketch_options["dimensions"] = dimension_options
            parameterization_report = _apply_sketch_parameterization(
                view,
                sketch_entities,
                planned_constraints,
                planned_dimensions,
                sketch_options,
                [],
                0.0,
            )
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    return sketch, target, results, parameterization_report


def _collection_for_sketch_entity_kind(drawing_container, kind):
    if kind == "segment":
        return _resolve_model_object_collection(drawing_container, ("LineSegments", "GetLineSegments"))[0], "segments"
    if kind == "circle":
        return _resolve_model_object_collection(drawing_container, ("Circles", "GetCircles"))[0], "circles"
    if kind == "point":
        return _resolve_model_object_collection(drawing_container, ("Points", "GetPoints"))[0], "points"
    if kind == "arc":
        return _resolve_model_object_collection(drawing_container, ("Arcs", "GetArcs"))[0], "arcs"
    if kind == "ellipse":
        return _resolve_model_object_collection(drawing_container, ("Ellipses", "GetEllipses"))[0], "ellipses"
    raise RuntimeError("unsupported_sketch_entity_kind")


def _normalize_sketch_entity_kind(kind):
    value = str(kind or "").strip().lower()
    if value in ("line", "line_segment"):
        return "segment"
    return value


def _sketch_entity_collection_count(drawing_container, kind):
    try:
        collection, _ = _collection_for_sketch_entity_kind(drawing_container, kind)
        return collection_count(collection)
    except Exception:
        return None


def _sketch_entity_list_item(entity, kind, collection_name, index, sketch_ref):
    reference = safe_get(entity, "Reference")
    geometry = _sketch_entity_geometry(kind, entity)
    fingerprint = _sketch_entity_fingerprint(kind, geometry, reference)
    return {
        "index": index,
        "collection_index": index,
        "kind": kind,
        "collection": collection_name,
        "sketch_ref": sketch_ref,
        "reference": reference,
        "fingerprint": fingerprint,
        "geometry": geometry,
        "line_style": safe_get(entity, "Style"),
        "name": safe_get(entity, "Name", ""),
    }


def _list_existing_sketch_entities(model_container, payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    if sketch_ref in (None, ""):
        raise RuntimeError("invalid input: sketch_ref is required")
    sketch = _resolve_existing_sketch(model_container, sketch_ref)
    raw_kinds = payload.get("kinds") or payload.get("entity_kinds")
    if raw_kinds in (None, ""):
        kinds = ["segment", "circle", "point", "arc", "ellipse"]
    elif isinstance(raw_kinds, (list, tuple)):
        kinds = [_normalize_sketch_entity_kind(item) for item in raw_kinds]
    else:
        kinds = [_normalize_sketch_entity_kind(raw_kinds)]
    allowed = {"segment", "circle", "point", "arc", "ellipse"}
    for kind in kinds:
        if kind not in allowed:
            raise RuntimeError("invalid input: unsupported sketch entity kind: %s" % (kind or "<missing>"))
    max_items = int(payload.get("max_items", 100))
    if max_items < 1:
        raise RuntimeError("invalid input: max_items must be greater than zero")

    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    items = []
    counts = {}
    truncated = False
    try:
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        for kind in kinds:
            collection, collection_name = _collection_for_sketch_entity_kind(drawing_container, kind)
            count = collection_count(collection)
            counts[collection_name] = count
            for index in range(count):
                if len(items) >= max_items:
                    truncated = True
                    break
                entity = get_collection_item(collection, index)
                if entity is not None:
                    items.append(_sketch_entity_list_item(entity, kind, collection_name, index, safe_get(sketch, "Reference", sketch_ref)))
            if truncated:
                break
    finally:
        sketch.EndEdit()
    return sketch, {
        "mode": "existing_sketch",
        "name": safe_get(sketch, "Name", ""),
        "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
    }, items, {
        "entity_count": len(items),
        "counts": counts,
        "truncated": truncated,
        "max_items": max_items,
    }


def _inspect_existing_sketch_entity(model_container, payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    if sketch_ref in (None, ""):
        raise RuntimeError("invalid input: sketch_ref is required")
    spec = payload.get("entity") or payload.get("selector")
    if not isinstance(spec, dict):
        raise RuntimeError("invalid input: entity selector must be an object")
    sketch = _resolve_existing_sketch(model_container, sketch_ref)
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    try:
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        entity, kind, collection_name = _select_existing_sketch_entity(drawing_container, spec)
        item = _sketch_entity_list_item(
            entity,
            kind,
            collection_name,
            int(spec.get("index")) if spec.get("index") not in (None, "") else -1,
            safe_get(sketch, "Reference", sketch_ref),
        )
        if item["collection_index"] < 0:
            collection, _collection_name = _collection_for_sketch_entity_kind(drawing_container, kind)
            count = collection_count(collection)
            for index in range(count):
                candidate = get_collection_item(collection, index)
                if candidate is None:
                    continue
                candidate_item = _sketch_entity_list_item(
                    candidate,
                    kind,
                    collection_name,
                    index,
                    safe_get(sketch, "Reference", sketch_ref),
                )
                if (
                    candidate is entity
                    or (
                        item.get("reference") not in (None, "")
                        and str(candidate_item.get("reference")) == str(item.get("reference"))
                    )
                    or (
                        item.get("fingerprint") not in (None, "")
                        and candidate_item.get("fingerprint") == item.get("fingerprint")
                    )
                ):
                    item["index"] = index
                    item["collection_index"] = index
                    break
    finally:
        sketch.EndEdit()
    return sketch, {
        "mode": "existing_sketch",
        "name": safe_get(sketch, "Name", ""),
        "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
    }, item


def _select_existing_sketch_entity(drawing_container, spec):
    kind = _normalize_sketch_entity_kind(spec.get("kind") or spec.get("type"))
    collection, collection_name = _collection_for_sketch_entity_kind(drawing_container, kind)
    expected_reference = spec.get("reference")
    expected_reference = str(expected_reference) if expected_reference not in (None, "") else None
    expected_fingerprint = str(spec.get("fingerprint") or "") or None
    if spec.get("index") not in (None, ""):
        entity = get_collection_item(collection, int(spec.get("index")))
        if entity is None:
            raise RuntimeError("sketch_entity_index_not_found")
        return entity, kind, collection_name
    count = collection_count(collection)
    for index in range(count):
        entity = get_collection_item(collection, index)
        if entity is None:
            continue
        reference = safe_get(entity, "Reference")
        geometry = _sketch_entity_geometry(kind, entity)
        fingerprint = _sketch_entity_fingerprint(kind, geometry, reference)
        if expected_reference is not None and str(reference) == expected_reference:
            return entity, kind, collection_name
        if expected_fingerprint is not None and fingerprint == expected_fingerprint:
            return entity, kind, collection_name
    raise RuntimeError("sketch_entity_not_found")


def _existing_sketch_entity_index(drawing_container, entity, kind, collection_name, sketch_ref):
    collection, _ = _collection_for_sketch_entity_kind(drawing_container, kind)
    count = collection_count(collection)
    expected_reference = safe_get(entity, "Reference")
    expected_geometry = _sketch_entity_geometry(kind, entity)
    expected_fingerprint = _sketch_entity_fingerprint(kind, expected_geometry, expected_reference)
    for index in range(count):
        candidate = get_collection_item(collection, index)
        if candidate is None:
            continue
        candidate_item = _sketch_entity_list_item(candidate, kind, collection_name, index, sketch_ref)
        if (
            candidate is entity
            or (
                expected_reference not in (None, "")
                and str(candidate_item.get("reference")) == str(expected_reference)
            )
            or candidate_item.get("fingerprint") == expected_fingerprint
        ):
            return index
    return -1


def _cast_sketch_entity_for_kind(entity, kind):
    interface_name = {
        "segment": "ILineSegment",
        "circle": "ICircle",
        "point": "IPoint",
        "arc": "IArc",
        "ellipse": "IEllipse",
    }.get(kind)
    if not interface_name:
        return entity
    return _cast_to_com_interface(entity, interface_name)


def _set_existing_sketch_entity_style(model_container, payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    if sketch_ref in (None, ""):
        raise RuntimeError("invalid input: sketch_ref is required")
    spec = payload.get("entity") or payload.get("selector")
    if not isinstance(spec, dict):
        raise RuntimeError("invalid input: entity selector must be an object")
    line_style = int(payload.get("line_style", 1))
    if line_style < 1:
        raise RuntimeError("invalid input: line_style must be greater than zero")
    sketch = _resolve_existing_sketch(model_container, sketch_ref)
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    try:
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        entity, kind, collection_name = _select_existing_sketch_entity(drawing_container, spec)
        resolved_sketch_ref = safe_get(sketch, "Reference", sketch_ref)
        index = _existing_sketch_entity_index(drawing_container, entity, kind, collection_name, resolved_sketch_ref)
        styled_entity = _cast_sketch_entity_for_kind(entity, kind)
        before = _sketch_entity_list_item(styled_entity, kind, collection_name, index, resolved_sketch_ref)
        _apply_line_style(styled_entity, line_style)
        updater = safe_get(styled_entity, "Update")
        if callable(updater) and not updater():
            raise RuntimeError("Sketch entity Update returned False")
        after = _sketch_entity_list_item(styled_entity, kind, collection_name, index, resolved_sketch_ref)
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    return sketch, {
        "mode": "existing_sketch",
        "name": safe_get(sketch, "Name", ""),
        "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
    }, before, after


def _existing_sketch_entity_entry(entity, kind, role, target, spec):
    if kind == "segment":
        start = spec.get("start") if isinstance(spec.get("start"), list) else None
        end = spec.get("end") if isinstance(spec.get("end"), list) else None
        return _sketch_line_entry(
            entity,
            start[0] if start else safe_get(entity, "X1"),
            start[1] if start else safe_get(entity, "Y1"),
            end[0] if end else safe_get(entity, "X2"),
            end[1] if end else safe_get(entity, "Y2"),
            role=role or "segment",
            target=target,
        )
    if kind == "circle":
        center = spec.get("center") if isinstance(spec.get("center"), list) else None
        return _sketch_circle_entry(
            entity,
            center[0] if center else safe_get(entity, "Xc"),
            center[1] if center else safe_get(entity, "Yc"),
            spec.get("radius", safe_get(entity, "Radius")),
            role=role or "circle",
            target=target,
        )
    if kind == "point":
        point = spec.get("point") if isinstance(spec.get("point"), list) else None
        return _sketch_point_entry(
            entity,
            point[0] if point else safe_get(entity, "X"),
            point[1] if point else safe_get(entity, "Y"),
            role=role or "point",
            target=target,
        )
    if kind == "arc":
        center = spec.get("center") if isinstance(spec.get("center"), list) else None
        start = spec.get("start") if isinstance(spec.get("start"), list) else None
        end = spec.get("end") if isinstance(spec.get("end"), list) else None
        return _sketch_arc_entry(
            entity,
            center[0] if center else safe_get(entity, "Xc"),
            center[1] if center else safe_get(entity, "Yc"),
            spec.get("radius", safe_get(entity, "Radius")),
            start[0] if start else safe_get(entity, "X1"),
            start[1] if start else safe_get(entity, "Y1"),
            end[0] if end else safe_get(entity, "X2"),
            end[1] if end else safe_get(entity, "Y2"),
            direction=bool(spec.get("direction", safe_get(entity, "Direction", True))),
            role=role or "arc",
            target=target,
        )
    if kind == "ellipse":
        geometry = _sketch_entity_geometry(kind, entity)
        center = spec.get("center") if isinstance(spec.get("center"), list) else geometry.get("center") or [0.0, 0.0]
        return {
            "object": entity,
            "role": role or "ellipse",
            "target": target,
            "xc": float(center[0]),
            "yc": float(center[1]),
            "radius_x": float(spec.get("radius_x", geometry.get("radius_x") or 0.0)),
            "radius_y": float(spec.get("radius_y", geometry.get("radius_y") or 0.0)),
            "angle": float(spec.get("angle", geometry.get("angle") or 0.0)),
        }
    raise RuntimeError("unsupported_sketch_entity_kind")


def _parameterize_existing_sketch(model_container, part, payload):
    sketch, target = _resolve_sketch_write_target(model_container, part, payload, "SKETCH_BATCH_1")
    entity_specs = payload.get("entities")
    if not isinstance(entity_specs, list) or not entity_specs:
        raise RuntimeError("invalid input: entities must be a non-empty list")
    planned_constraints = payload.get("constraints") or []
    planned_dimensions = payload.get("dimensions") or []
    if not isinstance(planned_constraints, list):
        raise RuntimeError("invalid input: constraints must be a list")
    if not isinstance(planned_dimensions, list):
        raise RuntimeError("invalid input: dimensions must be a list")
    if not planned_constraints and not planned_dimensions:
        raise RuntimeError("invalid input: constraints or dimensions must be provided")
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    selected = []
    parameterization_report = None
    try:
        view = _get_sketch_system_view(sketch_doc)
        drawing_container = cast_drawing_container(view)
        sketch_entities = {}
        for index, spec in enumerate(entity_specs):
            if not isinstance(spec, dict):
                raise RuntimeError("invalid input: entities[%s] must be an object" % index)
            entity_id = str(spec.get("entity_id") or spec.get("id") or "")
            if not entity_id:
                raise RuntimeError("invalid input: entities[%s] must include id or entity_id" % index)
            entity, kind, collection_name = _select_existing_sketch_entity(drawing_container, spec)
            role = str(spec.get("role") or kind)
            geometry = _sketch_entity_geometry(kind, entity)
            fingerprint = _sketch_entity_fingerprint(kind, geometry, safe_get(entity, "Reference"))
            sketch_entities[entity_id] = _existing_sketch_entity_entry(entity, kind, role, entity_id, spec)
            selected.append({
                "index": index,
                "id": entity_id,
                "kind": kind,
                "collection": collection_name,
                "reference": safe_get(entity, "Reference"),
                "fingerprint": fingerprint,
                "ok": True,
            })
        sketch_options = dict(payload.get("sketch_options") or payload.get("sketch") or {})
        constraint_options = dict(sketch_options.get("constraints") or {})
        dimension_options = dict(sketch_options.get("dimensions") or {})
        if planned_constraints:
            constraint_options.setdefault("enabled", True)
        if planned_dimensions:
            dimension_options.setdefault("enabled", True)
            dimension_options.setdefault("driving", True)
        sketch_options["constraints"] = constraint_options
        sketch_options["dimensions"] = dimension_options
        parameterization_report = _apply_sketch_parameterization(
            view,
            sketch_entities,
            planned_constraints,
            planned_dimensions,
            sketch_options,
            [],
            0.0,
        )
    finally:
        sketch.EndEdit()
    sketch_update_ok = bool(sketch.Update())
    if not sketch_update_ok:
        raise RuntimeError("Sketch Update after edit returned False")
    return sketch, target, selected, parameterization_report


def _create_sketch_line_segment(model_container, part, name, plane, start, end, line_style):
    sketch, plane_key = _create_sketch_on_plane(model_container, part, name, plane)
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    try:
        view = _get_sketch_system_view(sketch_doc)
        drawing_container = cast_drawing_container(view)
        line_segments = safe_get(drawing_container, "LineSegments")
        if line_segments is None:
            get_line_segments = safe_get(drawing_container, "GetLineSegments")
            if callable(get_line_segments):
                line_segments = get_line_segments()
        if line_segments is None or not callable(safe_get(line_segments, "Add")):
            raise RuntimeError("Sketch view does not expose LineSegments.Add")
        line = line_segments.Add()
        if line is None:
            raise RuntimeError("LineSegments.Add returned None")
        line.X1 = float(start[0])
        line.Y1 = float(start[1])
        line.X2 = float(end[0])
        line.Y2 = float(end[1])
        try:
            line.Style = int(line_style)
        except Exception:
            set_style = safe_get(line, "SetStyle")
            if callable(set_style):
                set_style(int(line_style))
            else:
                raise
        if not line.Update():
            raise RuntimeError("LineSegment Update returned False")
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    return sketch, line, plane_key


def _create_sketch_circle(model_container, part, name, plane, center, radius, line_style):
    sketch, plane_key = _create_sketch_on_plane(model_container, part, name, plane)
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    try:
        view = _get_sketch_system_view(sketch_doc)
        drawing_container = cast_drawing_container(view)
        circles = safe_get(drawing_container, "Circles")
        if circles is None:
            get_circles = safe_get(drawing_container, "GetCircles")
            if callable(get_circles):
                circles = get_circles()
        if circles is None or not callable(safe_get(circles, "Add")):
            raise RuntimeError("Sketch view does not expose Circles.Add")
        circle = circles.Add()
        if circle is None:
            raise RuntimeError("Circles.Add returned None")
        circle.Xc = float(center[0])
        circle.Yc = float(center[1])
        circle.Radius = float(radius)
        try:
            circle.Style = int(line_style)
        except Exception:
            set_style = safe_get(circle, "SetStyle")
            if callable(set_style):
                set_style(int(line_style))
            else:
                raise
        if not circle.Update():
            raise RuntimeError("Circle Update returned False")
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    return sketch, circle, plane_key


def _create_sketch_rectangle(model_container, part, name, plane, corner1, corner2, line_style):
    sketch, plane_key = _create_sketch_on_plane(model_container, part, name, plane)
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    lines = []
    x1, y1 = float(corner1[0]), float(corner1[1])
    x2, y2 = float(corner2[0]), float(corner2[1])
    segments = (
        ([x1, y1], [x2, y1]),
        ([x2, y1], [x2, y2]),
        ([x2, y2], [x1, y2]),
        ([x1, y2], [x1, y1]),
    )
    try:
        view = _get_sketch_system_view(sketch_doc)
        drawing_container = cast_drawing_container(view)
        line_segments = safe_get(drawing_container, "LineSegments")
        if line_segments is None:
            get_line_segments = safe_get(drawing_container, "GetLineSegments")
            if callable(get_line_segments):
                line_segments = get_line_segments()
        if line_segments is None or not callable(safe_get(line_segments, "Add")):
            raise RuntimeError("Sketch view does not expose LineSegments.Add")
        for start, end in segments:
            line = line_segments.Add()
            if line is None:
                raise RuntimeError("LineSegments.Add returned None")
            line.X1 = float(start[0])
            line.Y1 = float(start[1])
            line.X2 = float(end[0])
            line.Y2 = float(end[1])
            try:
                line.Style = int(line_style)
            except Exception:
                set_style = safe_get(line, "SetStyle")
                if callable(set_style):
                    set_style(int(line_style))
                else:
                    raise
            if not line.Update():
                raise RuntimeError("LineSegment Update returned False")
            lines.append(line)
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    return sketch, lines, plane_key


def handle_create_sketch_line_segment(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    start = _normalize_point2d_payload(payload.get("start"), "start", [0.0, 0.0])
    end = _normalize_point2d_payload(payload.get("end"), "end", [100.0, 0.0])

    before_tree = serialize_part(top_part, "root", None)
    sketch, line, plane = _create_sketch_line_segment(
        model_container,
        top_part,
        payload.get("name") or "SKETCH_LINE_1",
        payload.get("plane") or "XOY",
        start,
        end,
        int(payload.get("line_style", 1)),
    )
    updater = safe_get(top_part, "Update")
    update_ok = True
    if callable(updater):
        update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)

    return {
        "ok": True,
        "document": describe_document(document, app),
        "item": {
            "name": safe_get(sketch, "Name", payload.get("name")),
            "type": "SketchLineSegment",
            "plane": plane,
            "start": start,
            "end": end,
            "reference": safe_get(line, "Reference"),
        },
        "summary": {
            "name": safe_get(sketch, "Name", payload.get("name")),
            "plane": plane,
            "update_ok": update_ok,
        },
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_create_sketch_circle(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    center = _normalize_point2d_payload(payload.get("center"), "center", [0.0, 0.0])
    radius = float(payload.get("radius", 10.0))
    if radius <= 0:
        raise RuntimeError("radius must be greater than zero")

    before_tree = serialize_part(top_part, "root", None)
    sketch, circle, plane = _create_sketch_circle(
        model_container,
        top_part,
        payload.get("name") or "SKETCH_CIRCLE_1",
        payload.get("plane") or "XOY",
        center,
        radius,
        int(payload.get("line_style", 1)),
    )
    updater = safe_get(top_part, "Update")
    update_ok = True
    if callable(updater):
        update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)

    return {
        "ok": True,
        "document": describe_document(document, app),
        "item": {
            "name": safe_get(sketch, "Name", payload.get("name")),
            "type": "SketchCircle",
            "plane": plane,
            "center": center,
            "radius": radius,
            "reference": safe_get(circle, "Reference"),
        },
        "summary": {
            "name": safe_get(sketch, "Name", payload.get("name")),
            "plane": plane,
            "update_ok": update_ok,
        },
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_create_sketch_rectangle(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    corner1 = _normalize_point2d_payload(payload.get("corner1"), "corner1", [0.0, 0.0])
    corner2 = _normalize_point2d_payload(payload.get("corner2"), "corner2", [100.0, 50.0])

    before_tree = serialize_part(top_part, "root", None)
    sketch, lines, plane = _create_sketch_rectangle(
        model_container,
        top_part,
        payload.get("name") or "SKETCH_RECTANGLE_1",
        payload.get("plane") or "XOY",
        corner1,
        corner2,
        int(payload.get("line_style", 1)),
    )
    updater = safe_get(top_part, "Update")
    update_ok = True
    if callable(updater):
        update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)

    return {
        "ok": True,
        "document": describe_document(document, app),
        "item": {
            "name": safe_get(sketch, "Name", payload.get("name")),
            "type": "SketchRectangle",
            "plane": plane,
            "corner1": corner1,
            "corner2": corner2,
            "line_count": len(lines),
            "reference": safe_get(lines[0], "Reference") if lines else None,
        },
        "summary": {
            "name": safe_get(sketch, "Name", payload.get("name")),
            "plane": plane,
            "line_count": len(lines),
            "update_ok": update_ok,
        },
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_create_sketch_entities(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    before_tree = serialize_part(top_part, "root", None)
    sketch, target, entity_results, parameterization_report = _create_sketch_entities(model_container, top_part, payload)
    updater = safe_get(top_part, "Update")
    part_update_ok = True
    if callable(updater):
        part_update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)

    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "items": entity_results,
        "item": {
            "name": safe_get(sketch, "Name", target.get("name")),
            "type": "SketchEntitiesBatch",
            "plane": target.get("plane"),
            "entity_count": len(entity_results),
            "reference": safe_get(sketch, "Reference"),
        },
        "summary": {
            "name": safe_get(sketch, "Name", target.get("name")),
            "plane": target.get("plane"),
            "entity_count": len(entity_results),
            "failed_count": sum(1 for item in entity_results if not item.get("ok")),
            "update_ok": True,
            "sketch_update_ok": True,
            "part_update_ok": part_update_ok,
        },
        "parameterization": parameterization_report,
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_parameterize_sketch(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    before_tree = serialize_part(top_part, "root", None)
    sketch, target, selected_entities, parameterization_report = _parameterize_existing_sketch(model_container, top_part, payload)
    updater = safe_get(top_part, "Update")
    part_update_ok = True
    if callable(updater):
        part_update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)

    ok = True if parameterization_report is None else bool(parameterization_report.get("ok", True))
    return {
        "ok": ok,
        "document": describe_document(document, app),
        "target": target,
        "items": selected_entities,
        "item": {
            "name": safe_get(sketch, "Name", target.get("name")),
            "type": "SketchParameterization",
            "reference": safe_get(sketch, "Reference"),
        },
        "summary": {
            "name": safe_get(sketch, "Name", target.get("name")),
            "selected_entity_count": len(selected_entities),
            "update_ok": True,
            "sketch_update_ok": True,
            "part_update_ok": part_update_ok,
        },
        "parameterization": parameterization_report,
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_list_sketches(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    items, summary = _list_existing_sketches(model_container, payload)
    return {
        "ok": True,
        "document": describe_document(document, app),
        "items": items,
        "summary": summary,
    }


def handle_rename_sketch(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    before_tree = serialize_part(top_part, "root", None)
    sketch, target, sketch_update_ok = _rename_existing_sketch(model_container, payload)
    updater = safe_get(top_part, "Update")
    part_update_ok = True
    if callable(updater):
        part_update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)

    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "item": {
            "name": safe_get(sketch, "Name", target.get("name")),
            "old_name": target.get("old_name"),
            "type": "Sketch",
            "reference": safe_get(sketch, "Reference"),
        },
        "summary": {
            "old_name": target.get("old_name"),
            "name": safe_get(sketch, "Name", target.get("name")),
            "sketch_update_ok": sketch_update_ok,
            "part_update_ok": part_update_ok,
        },
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_set_sketch_entity_style(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    before_tree = serialize_part(top_part, "root", None)
    sketch, target, before_item, after_item = _set_existing_sketch_entity_style(model_container, payload)
    updater = safe_get(top_part, "Update")
    part_update_ok = True
    if callable(updater):
        part_update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)

    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "item": after_item,
        "before_item": before_item,
        "summary": {
            "kind": after_item.get("kind"),
            "collection": after_item.get("collection"),
            "collection_index": after_item.get("collection_index"),
            "old_line_style": before_item.get("line_style"),
            "line_style": after_item.get("line_style"),
            "part_update_ok": part_update_ok,
        },
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_list_sketch_entities(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    sketch, target, items, summary = _list_existing_sketch_entities(model_container, payload)
    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "items": items,
        "item": {
            "name": safe_get(sketch, "Name", target.get("name")),
            "type": "SketchEntityList",
            "reference": safe_get(sketch, "Reference"),
        },
        "summary": summary,
    }


def handle_inspect_sketch_entity(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(top_part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    sketch, target, item = _inspect_existing_sketch_entity(model_container, payload)
    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "item": item,
        "summary": {
            "found": True,
            "kind": item.get("kind"),
            "collection": item.get("collection"),
            "collection_index": item.get("collection_index"),
        },
    }


def handle_probe_model_object_collections(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")

    probe = probe_model_object_collections(
        top_part,
        max_items=payload.get("max_items", 5),
        include_empty=payload.get("include_empty", True),
    )
    return {
        "document": describe_document(document, app),
        "probe": probe,
    }


def handle_get_specification_descriptions(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    _, items, active_description = get_specification_descriptions(document)
    return {
        "document": describe_document(document, app),
        "summary": {
            "descriptions_count": len(items),
            "has_active": active_description is not None,
        },
        "descriptions": items,
    }


def handle_get_specification(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    description, description_index, items, active_description = select_specification_description(document, payload)
    include_objects = bool(payload.get("include_objects", True))
    max_objects = payload.get("max_objects", 200)

    if description is None:
        return {
            "document": describe_document(document, app),
            "summary": {
                "descriptions_count": len(items),
                "has_active": active_description is not None,
                "selected": False,
                "base_objects_count": 0,
                "comment_objects_count": 0,
            },
            "available_descriptions": items,
            "specification": None,
        }

    specification_payload = serialize_spec_description(
        description,
        description_index if description_index is not None else 0,
        active_description=active_description,
        include_objects=include_objects,
        max_objects=max_objects,
    )
    return {
        "document": describe_document(document, app),
        "summary": {
            "descriptions_count": len(items),
            "has_active": active_description is not None,
            "selected": True,
            "base_objects_count": specification_payload.get("base_objects_count", 0),
            "comment_objects_count": specification_payload.get("comment_objects_count", 0),
        },
        "available_descriptions": items,
        "specification": specification_payload,
    }


def handle_create_specification(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    descriptions = safe_get(document, "SpecificationDescriptions")
    if descriptions is None:
        raise RuntimeError("Document does not expose SpecificationDescriptions")

    existing_count = collection_count(descriptions)
    replace_existing = bool(payload.get("replace_existing"))
    if existing_count and not replace_existing:
        raise RuntimeError("Specification descriptions already exist; pass replace_existing=true")

    deleted_descriptions = 0
    if existing_count and replace_existing:
        deleted_descriptions = _delete_all_specification_descriptions(document)

    layout_name = payload.get("layout_name") or ""
    style_id = payload.get("style_id")
    try:
        style_id = int(style_id or 0)
    except Exception:
        style_id = 0
    specification_name = payload.get("specification_name") or ""

    description = descriptions.Add(layout_name, style_id, specification_name)
    if description is None:
        raise RuntimeError("Failed to create specification description")

    description.Active = True
    description.Update()
    saved = bool(payload.get("save"))
    if saved:
        document.Save()

    summary, specification_payload = _build_created_specification_summary(
        description,
        deleted_descriptions,
    )
    document_description = describe_document(document, app)
    closed = False
    if saved and payload.get("close_after_save"):
        document.Close(0)
        closed = True

    return {
        "document": document_description,
        "summary": summary,
        "specification": specification_payload,
        "saved": saved,
        "closed": closed,
    }


def handle_apply_specification_changes(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    description, description_index, items, active_description = select_specification_description(document, payload)
    if description is None:
        raise RuntimeError("Specification description not found")

    applied = []
    failed = []
    for change in payload.get("changes") or []:
        object_id = change.get("object_id")
        if not object_id:
            failed.append({"change": change, "error": "object_id is required"})
            continue

        spec_object = resolve_specification_object(description, object_id)
        if spec_object is None:
            failed.append({"change": change, "error": "Specification object not found"})
            continue

        column = resolve_specification_column(spec_object, change)
        if column is None:
            failed.append({"change": change, "error": "Specification column not found"})
            continue

        items_collection = safe_get(column, "ColumnItems")
        item = get_collection_item(items_collection, 0) if items_collection is not None else None
        if item is None:
            failed.append({"change": change, "error": "Specification column item not found"})
            continue

        try:
            item.Value = convert_spec_column_value(column, change.get("after"))
            updater = safe_get(spec_object, "Update")
            if callable(updater):
                updater()
            applied.append(change)
        except Exception as exc:
            failed.append({"change": change, "error": str(exc)})

    description.Update()
    saved = bool(payload.get("save"))
    if saved:
        document.Save()

    specification_payload = serialize_spec_description(
        description,
        description_index if description_index is not None else 0,
        active_description=active_description if active_description is not None else description,
        include_objects=True,
        max_objects=max(collection_count(safe_get(description, "BaseObjects")), 1),
    )
    document_description = describe_document(document, app)
    closed = False
    if saved and payload.get("close_after_save"):
        document.Close(0)
        closed = True

    return {
        "document": document_description,
        "selected_description": {
            "index": description_index if description_index is not None else 0,
            "layout_name": safe_get(description, "LayoutName", ""),
            "style_id": safe_get(description, "StyleID"),
        },
        "applied_count": len(applied),
        "failed_count": len(failed),
        "applied": applied,
        "failed": failed,
        "saved": saved,
        "closed": closed,
        "specification": specification_payload,
    }


def handle_open_document(payload):
    path = payload.get("path")
    if not path:
        raise RuntimeError("Path is required")

    path = os.path.abspath(os.path.normpath(path))
    if os.path.isdir(path):
        diagnostics = document_open_diagnostics(path, payload, [])
        raise RuntimeError("Document path points to a directory: %s | diagnostics=%s" % (path, json.dumps(diagnostics, ensure_ascii=False)))
    if not os.path.exists(path):
        diagnostics = document_open_diagnostics(path, payload, [])
        raise RuntimeError("Document path does not exist: %s | diagnostics=%s" % (path, json.dumps(diagnostics, ensure_ascii=False)))

    app = make_app()
    document, attempts = _open_document_in_app(
        app,
        path,
        visible=bool(payload.get("visible", True)),
        read_only=bool(payload.get("read_only", False)),
    )
    if document is None:
        diagnostics = document_open_diagnostics(path, payload, attempts)
        raise RuntimeError("Failed to open document | diagnostics=%s" % json.dumps(diagnostics, ensure_ascii=False))

    return {
        "document": describe_document(document, app),
        "open_attempts": attempts,
    }


def handle_close_document(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    save = bool(payload.get("save"))
    description = describe_document(document, app)
    document_path = description.get("path")
    if save:
        document.Save()

    close_mode = parse_close_mode(payload.get("close_mode"))
    document.Close(close_mode)
    remaining_documents = list_documents(app)

    return {
        "document": description,
        "saved": save,
        "closed": True,
        "close_mode": close_mode,
        "remaining_documents_count": len(remaining_documents),
        "remaining_documents": remaining_documents,
        "file_access": file_access_diagnostics(document_path) if document_path else None,
    }


def handle_shutdown_session(payload):
    app = make_app()
    save = bool(payload.get("save"))
    close_mode = parse_close_mode(payload.get("close_mode"))

    documents = list(iter_collection(safe_get(app, "Documents")))
    closed = []
    failed = []
    for document in documents:
        description = describe_document(document, app)
        try:
            if save:
                document.Save()
            document.Close(close_mode)
            closed_description = dict(description)
            closed_description["file_access"] = (
                file_access_diagnostics(description.get("path")) if description.get("path") else None
            )
            closed.append(closed_description)
        except Exception as exc:
            failed.append({"document": description, "error": str(exc)})

    remaining_documents = list_documents(app)

    quit_called = False
    for candidate in (app, _APP5):
        quitter = safe_get(candidate, "Quit")
        if callable(quitter):
            try:
                quitter()
                quit_called = True
            except Exception:
                pass

    return {
        "closed_count": len(closed),
        "failed_count": len(failed),
        "closed": closed,
        "failed": failed,
        "remaining_documents_count": len(remaining_documents),
        "remaining_documents": remaining_documents,
        "quit_called": quit_called,
        "saved": save,
        "close_mode": close_mode,
    }


def handle_apply_changeset(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")

    part_index = {}
    build_part_index(top_part, "root", part_index)

    applied = []
    failed = []
    for change in payload.get("changes") or []:
        item_id = change.get("item_id")
        field = change.get("field")
        after = change.get("after")

        target = part_index.get(item_id)
        if target is None:
            failed.append({"change": change, "error": "Item not found"})
            continue

        try:
            if field == "name":
                target.Name = after
            elif field == "designation":
                target.Marking = after
            elif field == "material":
                material_payload = resolve_material_payload(after, safe_get(target, "Density", 0.0) or 0.0)
                density = float(material_payload.get("density") or 0.0)
                ok = target.SetMaterial(material_payload["material"], density)
                if ok is False:
                    raise RuntimeError("SetMaterial returned False")
                change = dict(change)
                change["after"] = material_payload["material"]
                change["density"] = density
                change["catalog_matched"] = material_payload.get("catalog_matched", False)
            else:
                raise RuntimeError("Unsupported field: %s" % field)
            updater = safe_get(target, "Update")
            if callable(updater):
                updater()
            applied.append(change)
        except Exception as exc:
            failed.append({"change": change, "error": str(exc)})

    saved = bool(payload.get("save"))
    if saved:
        document.Save()

    document_description = describe_document(document, app)
    closed = False
    if saved and payload.get("close_after_save"):
        document.Close(0)
        closed = True

    return {
        "document": document_description,
        "applied_count": len(applied),
        "failed_count": len(failed),
        "applied": applied,
        "failed": failed,
        "saved": saved,
        "closed": closed,
    }


def handle_save_document(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    description = describe_document(document, app)
    current_path = os.path.abspath(os.path.normpath(description.get("path") or "")) if description.get("path") else ""
    target_path = payload.get("path")
    target_path = os.path.abspath(os.path.normpath(target_path)) if target_path else current_path
    if not target_path:
        raise RuntimeError("Document does not have a file path; pass payload.path")

    close_after_save = bool(payload.get("close_after_save"))
    keep_open = not close_after_save
    save_report = None
    reopened_document = None

    if normalize_fs_path(target_path) == normalize_fs_path(current_path):
        save_result = document.Save()
        saved = bool(save_result) or bool(os.path.exists(target_path))
        if not saved:
            raise RuntimeError("Failed to save document to %s" % target_path)
        if close_after_save:
            document.Close(0)
        result_document = description if close_after_save else describe_document(document, app)
    else:
        reopened_document, save_report = _save_document_via_staging(
            document,
            app,
            target_path,
            keep_open=keep_open,
            visible=bool(description.get("active", True)),
        )
        result_document = (
            describe_document(reopened_document, app)
            if reopened_document is not None
            else {
                "id": target_path,
                "name": os.path.basename(target_path),
                "path": target_path,
                "active": False,
                "changed": False,
            }
        )

    remaining_documents = list_documents(app)
    return {
        "document": result_document,
        "saved_as": target_path if normalize_fs_path(target_path) != normalize_fs_path(current_path) else None,
        "closed": close_after_save,
        "save_report": save_report,
        "remaining_documents_count": len(remaining_documents),
        "remaining_documents": remaining_documents,
        "file_access": file_access_diagnostics(target_path) if target_path else None,
    }


def handle_apply_relink_paths(payload):
    app = make_app()
    document = resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")

    part_index = {}
    build_part_index(top_part, "root", part_index)
    path_index = defaultdict(deque)
    for item_id, part in iter_parts_with_ids(top_part, "root"):
        current_path = normalize_display_path(safe_get(part, "FileName", ""))
        normalized_current = normalize_fs_path(current_path)
        if normalized_current:
            path_index[normalized_current].append((item_id, part))

    applied = []
    failed = []
    backed_up_targets = {}
    backup_root = payload.get("backup_root") or os.path.join(os.environ.get("KOMPAS_EXPORT_DIR", r"C:\Temp\kompas-mcp"), "relink-backups")
    for change in payload.get("changes") or []:
        item_id = change.get("item_id")
        old_path = change.get("old_path")
        new_path = change.get("new_path")
        target = part_index.get(item_id)
        resolved_item_id = item_id

        if target is None and old_path:
            queue = path_index.get(normalize_fs_path(old_path))
            if queue:
                resolved_item_id, target = queue.popleft()

        if target is None:
            failed.append({"change": change, "error": "Item not found"})
            continue
        if not new_path:
            failed.append({"change": change, "error": "new_path is required"})
            continue

        try:
            current_path = normalize_display_path(safe_get(target, "FileName", ""))
            if normalize_fs_path(current_path) == normalize_fs_path(new_path):
                applied.append(dict(change, old_path=current_path, method="already_linked"))
                continue

            backup_path = None
            normalized_new = normalize_fs_path(new_path)
            if os.path.exists(new_path):
                backup_path = backed_up_targets.get(normalized_new)
                if backup_path is None:
                    backup_path = ensure_backup_copy(new_path, backup_root)
                    backed_up_targets[normalized_new] = backup_path

            ok = target.SaveAs(new_path)
            if not ok:
                raise RuntimeError("SaveAs returned False")

            updated_path = normalize_display_path(safe_get(target, "FileName", ""))
            if normalize_fs_path(updated_path) != normalize_fs_path(new_path):
                raise RuntimeError("Component still points to %s" % updated_path)

            applied_change = dict(change)
            applied_change["item_id"] = resolved_item_id
            applied_change["old_path"] = current_path
            applied_change["new_path"] = updated_path
            applied_change["backup_path"] = backup_path
            applied_change["method"] = "save_as"
            applied.append(applied_change)
        except Exception as exc:
            failed.append({"change": change, "error": str(exc)})

    saved = bool(payload.get("save"))
    if saved:
        document.Save()

    document_description = describe_document(document, app)
    closed = False
    if saved and payload.get("close_after_save"):
        document.Close(0)
        closed = True

    return {
        "document": document_description,
        "applied_count": len(applied),
        "failed_count": len(failed),
        "applied": applied,
        "failed": failed,
        "saved": saved,
        "closed": closed,
    }


def handle_relink_document_file(payload):
    assembly_path = payload.get("assembly_path")
    if not assembly_path:
        raise RuntimeError("assembly_path is required")

    output_path = payload.get("output_path") or assembly_path
    if normalize_fs_path(assembly_path) != normalize_fs_path(output_path):
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        shutil.copy2(assembly_path, output_path)

    app = make_app()
    document = app.Documents.Open(output_path, True, False)
    if document is None:
        raise RuntimeError("Failed to open document for relink")

    top_part = safe_get(document, "TopPart")
    if top_part is None:
        raise RuntimeError("Document does not expose TopPart")

    change_by_old_path = defaultdict(deque)
    for change in payload.get("changes") or []:
        old_path = change.get("old_path")
        new_path = change.get("new_path")
        if old_path and new_path:
            change_by_old_path[normalize_fs_path(old_path)].append(change)

    applied = []
    failed = []
    backed_up_targets = {}
    backup_root = payload.get("backup_root") or os.path.join(os.environ.get("KOMPAS_EXPORT_DIR", r"C:\Temp\kompas-mcp"), "relink-backups")

    for item_id, part in iter_parts_with_ids(top_part, "root"):
        current_path = normalize_display_path(safe_get(part, "FileName", ""))
        if not current_path:
            continue

        queue = change_by_old_path.get(normalize_fs_path(current_path))
        if not queue:
            continue
        change = queue.popleft()

        new_path = change.get("new_path")
        try:
            if normalize_fs_path(current_path) == normalize_fs_path(new_path):
                applied.append({"item_id": item_id, "old_path": current_path, "new_path": current_path, "backup_path": None, "method": "already_linked"})
                continue

            backup_path = None
            normalized_new = normalize_fs_path(new_path)
            if os.path.exists(new_path):
                backup_path = backed_up_targets.get(normalized_new)
                if backup_path is None:
                    backup_path = ensure_backup_copy(new_path, backup_root)
                    backed_up_targets[normalized_new] = backup_path

            ok = part.SaveAs(new_path)
            if not ok:
                raise RuntimeError("SaveAs returned False")

            updated_path = normalize_display_path(safe_get(part, "FileName", ""))
            if normalize_fs_path(updated_path) != normalize_fs_path(new_path):
                raise RuntimeError("Component still points to %s" % updated_path)

            applied.append({"item_id": item_id, "old_path": current_path, "new_path": updated_path, "backup_path": backup_path, "method": "save_as"})
        except Exception as exc:
            failed.append({"item_id": item_id, "old_path": current_path, "new_path": new_path, "error": str(exc)})

    document.Save()
    result_document = describe_document(document, app)
    document.Close(0)

    return {
        "document": result_document,
        "output_path": output_path,
        "applied_count": len(applied),
        "failed_count": len(failed),
        "applied": applied,
        "failed": failed,
        "saved": True,
    }


def handle_create_spw_from_rows(payload):
    output_path = payload.get("output_path")
    if not output_path:
        raise RuntimeError("output_path is required")

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    app = make_app()
    app5 = _APP5
    if app5 is None:
        raise RuntimeError("Failed to initialize KOMPAS.Application.5")

    temp_doc = app.Documents.Add(3, False)
    if temp_doc is None:
        raise RuntimeError("Failed to create temporary SPW document")
    temp_doc.SaveAs(output_path)
    temp_doc.Close(0)

    spc_document = getattr(app5, "SpcDocument", None)
    if spc_document is None:
        raise RuntimeError("KOMPAS old specification API is unavailable")

    if not spc_document.ksOpenDocument(output_path, 0):
        raise RuntimeError("Failed to open SPW document through ksSpcDocument")

    specification = spc_document.GetSpecification()
    if specification is None:
        raise RuntimeError("Failed to get old specification interface")

    layout_name = (payload.get("layout_name") or "graphic.lyt").lower()
    style_id = int(payload.get("style_id") or 1)

    created_rows = []
    failed_rows = []
    spw_columns = normalize_spw_column_payload(payload.get("columns"))

    for index, row in enumerate(payload.get("rows") or []):
        section = int(row.get("section") or 20)
        subsection = int(row.get("subsection") or 0)
        attribute_number = int(row.get("attribute_number") or 0)
        object_type = int(row.get("object_type") or 0)

        try:
            created = specification.ksSpcObjectCreate(
                layout_name,
                style_id,
                section,
                subsection,
                attribute_number,
                object_type,
            )
            if created != 1:
                raise RuntimeError("ksSpcObjectCreate returned %s" % created)

            written_columns = []
            for column in spw_columns:
                field = column["field"]
                value = row.get(field)
                if value in (None, ""):
                    continue
                normalized_value = str(value)
                if column.get("skip_unit_value") and normalized_value.strip() in ("1", "1.0"):
                    continue
                result = specification.ksSetSpcObjectColumnText(
                    int(column["column_type"]),
                    int(column["block_number"]),
                    int(column["column_number"]),
                    normalized_value,
                )
                if result != 1:
                    raise RuntimeError("ksSetSpcObjectColumnText failed for %s" % field)
                written_columns.append(field)

            spc_object = specification.ksSpcObjectEnd()
            if not spc_object:
                raise RuntimeError("ksSpcObjectEnd returned empty reference")

            created_rows.append(
                {
                    "index": index,
                    "row_id": row.get("row_id") or ("row/%s" % index),
                    "title": row.get("title") or "",
                    "designation": row.get("designation") or "",
                    "quantity": row.get("quantity") or "",
                    "spc_object": spc_object,
                    "written_columns": written_columns,
                }
            )
        except Exception as exc:
            try:
                specification.ksSpcObjectEnd()
            except Exception:
                pass
            failed_rows.append(
                {
                    "index": index,
                    "row_id": row.get("row_id") or ("row/%s" % index),
                    "error": str(exc),
                }
            )

    saved = bool(spc_document.ksSaveDocument(output_path))
    spc_document.ksCloseDocument()

    inspect_document = app.Documents.Open(output_path, False, True)
    try:
        description = getattr(inspect_document.SpecificationDescriptions, "Active", None)
        if description is None:
            descriptions = inspect_document.SpecificationDescriptions
            description = get_collection_item(descriptions, 0) if descriptions is not None else None
        specification_payload = None
        summary = {
            "base_objects_count": 0,
            "comment_objects_count": 0,
            "selected": False,
        }
        if description is not None:
            specification_payload = serialize_spec_description(
                description,
                0,
                active_description=description,
                include_objects=True,
                max_objects=max(collection_count(safe_get(description, "BaseObjects")), 1),
            )
            summary = {
                "base_objects_count": specification_payload.get("base_objects_count", 0),
                "comment_objects_count": specification_payload.get("comment_objects_count", 0),
                "selected": True,
            }
        document_description = describe_document(inspect_document, app)
    finally:
        inspect_document.Close(0)

    return {
        "document": document_description,
        "output_path": output_path,
        "created_count": len(created_rows),
        "failed_count": len(failed_rows),
        "created": created_rows,
        "failed": failed_rows,
        "saved": saved,
        "summary": summary,
        "specification": specification_payload,
        "spw_columns": spw_columns,
    }


def _cast_to_com_interface(obj, interface_name):
    if obj is None:
        return None
    try:
        import win32com.client

        return win32com.client.CastTo(obj, interface_name)
    except Exception:
        return obj


def _sketch_line_entry(line, x1, y1, x2, y2, *, role, target, skipped=False):
    return {
        "object": line,
        "role": role,
        "target": target,
        "skipped": skipped,
        "x1": float(x1),
        "y1": float(y1),
        "x2": float(x2),
        "y2": float(y2),
    }


def _sketch_point_entry(point, x, y, *, role, target):
    return {
        "object": point,
        "role": role,
        "target": target,
        "x": float(x),
        "y": float(y),
    }


def _sketch_circle_entry(circle, xc, yc, radius, *, role, target):
    return {
        "object": circle,
        "role": role,
        "target": target,
        "xc": float(xc),
        "yc": float(yc),
        "radius": float(radius),
    }


def _sketch_arc_entry(arc, xc, yc, radius, x1, y1, x2, y2, *, direction, role, target):
    return {
        "object": arc,
        "role": role,
        "target": target,
        "xc": float(xc),
        "yc": float(yc),
        "radius": float(radius),
        "x1": float(x1),
        "y1": float(y1),
        "x2": float(x2),
        "y2": float(y2),
        "direction": bool(direction),
    }


def _line_geometry(entity):
    if entity is None:
        raise RuntimeError("sketch_entity_not_found")
    if entity.get("role") == "point":
        x = float(safe_get(entity.get("object"), "X", entity["x"]))
        y = float(safe_get(entity.get("object"), "Y", entity["y"]))
        return (x, y, x, y)
    if entity.get("role") == "circle":
        raise RuntimeError("circle_entity_has_no_endpoints")
    drawing_object = entity.get("object")
    if drawing_object is None:
        return (
            float(entity["x1"]),
            float(entity["y1"]),
            float(entity["x2"]),
            float(entity["y2"]),
        )
    return (
        float(safe_get(drawing_object, "X1", entity["x1"])),
        float(safe_get(drawing_object, "Y1", entity["y1"])),
        float(safe_get(drawing_object, "X2", entity["x2"])),
        float(safe_get(drawing_object, "Y2", entity["y2"])),
    )


def _constraint_point_coordinates(entity, index):
    if entity.get("role") == "point":
        return float(safe_get(entity.get("object"), "X", entity["x"])), float(safe_get(entity.get("object"), "Y", entity["y"]))
    if "radius" in entity and "x1" in entity and "x2" in entity:
        point_index = _normalize_constraint_point_index(index)
        if point_index == 0:
            return float(entity["xc"]), float(entity["yc"])
        if point_index == 1:
            return float(entity["x1"]), float(entity["y1"])
        if point_index == 2:
            return float(entity["x2"]), float(entity["y2"])
        raise RuntimeError("unsupported_arc_constraint_point_index")
    x1, y1, x2, y2 = _line_geometry(entity)
    point_index = _normalize_constraint_point_index(index)
    if point_index == 0:
        return x1, y1
    if point_index == 1:
        return x2, y2
    raise RuntimeError("unsupported_constraint_point_index")


def _normalize_constraint_point_index(index):
    return index


def _constraint_points_are_coincident(entity, index, partner_entity, partner_index, *, tolerance=1e-9):
    x1, y1 = _constraint_point_coordinates(entity, index)
    x2, y2 = _constraint_point_coordinates(partner_entity, partner_index)
    return abs(x1 - x2) < tolerance and abs(y1 - y2) < tolerance


def _line_length_from_geometry(entity):
    x1, y1, x2, y2 = _line_geometry(entity)
    return math.hypot(float(x2) - float(x1), float(y2) - float(y1))


def _point_line_distance(point, line_entity):
    px, py = float(point[0]), float(point[1])
    x1, y1, x2, y2 = _line_geometry(line_entity)
    dx = float(x2) - float(x1)
    dy = float(y2) - float(y1)
    denominator = math.hypot(dx, dy)
    if denominator <= 1e-12:
        return float("inf")
    return abs(dy * px - dx * py + float(x2) * float(y1) - float(y2) * float(x1)) / denominator


def _lines_are_collinear(target_entity, partner_entity, *, tolerance=1e-6):
    x1, y1, x2, y2 = _line_geometry(target_entity)
    return (
        _point_line_distance((x1, y1), partner_entity) <= tolerance
        and _point_line_distance((x2, y2), partner_entity) <= tolerance
    )


def _snapshot_sketch_line_entities(sketch_entities):
    lines = {}
    for name, entity in sketch_entities.items():
        if entity.get("role") == "point" or entity.get("object") is None:
            continue
        try:
            x1, y1, x2, y2 = _line_geometry(entity)
        except Exception:
            continue
        lines[str(name)] = {
            "role": entity.get("role"),
            "x1": float(x1),
            "y1": float(y1),
            "x2": float(x2),
            "y2": float(y2),
        }
    return lines


def _verify_sketch_constraint_geometry(sketch_entities, planned_constraints, *, tolerance=1e-6):
    checks = []

    def add_check(plan, ok, **details):
        item = {"constraint": plan, "ok": bool(ok)}
        item.update(details)
        checks.append(item)

    for plan in planned_constraints or []:
        kind = str(plan.get("kind") or "")
        target = sketch_entities.get(str(plan.get("target") or ""))
        partner = sketch_entities.get(str(plan.get("partner") or ""))
        if target is None:
            add_check(plan, False, error="target_not_found")
            continue
        try:
            if kind == "horizontal":
                x1, y1, x2, y2 = _line_geometry(target)
                add_check(plan, abs(float(y1) - float(y2)) <= tolerance, delta=abs(float(y1) - float(y2)))
            elif kind == "vertical":
                x1, y1, x2, y2 = _line_geometry(target)
                add_check(plan, abs(float(x1) - float(x2)) <= tolerance, delta=abs(float(x1) - float(x2)))
            elif kind == "merge_points":
                if partner is None:
                    add_check(plan, False, error="partner_not_found")
                    continue
                x1, y1 = _constraint_point_coordinates(target, plan.get("index"))
                x2, y2 = _constraint_point_coordinates(partner, plan.get("partner_index"))
                distance = math.hypot(float(x2) - float(x1), float(y2) - float(y1))
                add_check(plan, distance <= tolerance, distance=distance)
            elif kind == "point_on_curve":
                if partner is None:
                    add_check(plan, False, error="partner_not_found")
                    continue
                point = _constraint_point_coordinates(target, plan.get("index"))
                distance = _point_line_distance(point, partner)
                add_check(plan, distance <= tolerance, distance=distance)
            elif kind == "collinear":
                if partner is None:
                    add_check(plan, False, error="partner_not_found")
                    continue
                add_check(plan, _lines_are_collinear(target, partner, tolerance=tolerance))
            elif kind == "equal_length":
                if partner is None:
                    add_check(plan, False, error="partner_not_found")
                    continue
                target_length = _line_length_from_geometry(target)
                partner_length = _line_length_from_geometry(partner)
                add_check(plan, abs(target_length - partner_length) <= tolerance, delta=abs(target_length - partner_length))
        except Exception as exc:
            add_check(plan, False, error=str(exc))

    failed = [check for check in checks if not bool(check.get("ok"))]
    return {
        "tolerance": float(tolerance),
        "checked_count": len(checks),
        "failed_count": len(failed),
        "ok": len(failed) == 0,
        "failed": failed,
    }


def _apply_constraint_to_line(line, constraint_type, *, index=None, partner=None, partner_index=None, value=None, variable=None):
    drawing_object = _cast_to_com_interface(line, "IDrawingObject1")
    new_constraint = safe_get(drawing_object, "NewConstraint")
    if not callable(new_constraint):
        raise RuntimeError("object does not expose IDrawingObject1.NewConstraint")
    constraint = new_constraint()
    if constraint is None:
        raise RuntimeError("NewConstraint returned None")
    constraint.ConstraintType = int(constraint_type)
    if index is not None:
        constraint.Index = int(_normalize_constraint_point_index(index))
    if partner is not None:
        constraint.Partner = partner
    if partner_index is not None:
        constraint.PartnerIndex = int(_normalize_constraint_point_index(partner_index))
    if value is not None:
        constraint.Value = float(value)
    if variable:
        constraint.Variable = str(variable)
    created = bool(constraint.Create())
    return {
        "created": created,
        "valid": bool(safe_get(constraint, "Valid", False)),
        "type": int(constraint_type),
        "reference": safe_get(constraint, "Reference"),
    }


def _find_profile_axis_endpoint(sketch_entities, *, start):
    candidates = []
    axis_entity = sketch_entities.get("axis") or {}
    axis_y = float(axis_entity.get("y1", 0.0))
    for target, entity in sketch_entities.items():
        if not target.startswith("profile_line_") or entity.get("object") is None:
            continue
        endpoints = (
            (0, entity["x1"], entity["y1"]),
            (1, entity["x2"], entity["y2"]),
        )
        for point_index, x, y in endpoints:
            if abs(float(y) - axis_y) < 1e-9:
                candidates.append((float(x), point_index, entity))
    if not candidates:
        return None, None
    selected = min(candidates, key=lambda item: item[0]) if start else max(candidates, key=lambda item: item[0])
    return selected[2], selected[1]


def _resolve_constraint_target(plan, sketch_entities):
    kind = plan.get("kind")
    target = plan.get("target")
    if kind == "fixed_point" and target == "origin":
        return sketch_entities.get("axis"), 0, None, None
    if kind == "point_on_curve" and target == "profile_start_on_axis":
        entity, point_index = _find_profile_axis_endpoint(sketch_entities, start=True)
        return entity, point_index, sketch_entities.get("axis"), None
    if kind == "point_on_curve" and target == "profile_end_on_axis":
        entity, point_index = _find_profile_axis_endpoint(sketch_entities, start=False)
        return entity, point_index, sketch_entities.get("axis"), None
    return (
        sketch_entities.get(str(target)),
        plan.get("index"),
        sketch_entities.get(str(plan.get("partner"))),
        plan.get("partner_index"),
    )


def _apply_sketch_constraints(sketch_entities, planned_constraints, options):
    enabled = bool((options or {}).get("enabled", False))
    report = {
        "enabled": enabled,
        "planned_count": len(planned_constraints),
        "applied_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "live_status": "disabled" if not enabled else "not_started",
        "applied": [],
        "failed": [],
        "skipped": [],
    }
    if not enabled:
        return report

    pending = list(planned_constraints)
    max_passes = 3
    pass_index = 0
    while pending and pass_index < max_passes:
        pass_index += 1
        next_pending = []
        progress_made = False
        for plan in pending:
            kind = plan.get("kind")
            constraint_type = SKETCH_CONSTRAINT_TYPES.get(kind)
            if constraint_type is None:
                report["failed"].append({"constraint": plan, "error": "unsupported_constraint_kind"})
                continue
            entity, index, partner_entity, partner_index = _resolve_constraint_target(plan, sketch_entities)
            line = entity.get("object") if entity else None
            if line is None:
                report["failed"].append({"constraint": plan, "error": "target_line_not_found"})
                continue
            partner = partner_entity.get("object") if partner_entity else None
            try:
                result = _apply_constraint_to_line(
                    line,
                    constraint_type,
                    index=index,
                    partner=partner,
                    partner_index=partner_index,
                    value=plan.get("value"),
                    variable=plan.get("variable"),
                )
                item = {"constraint": plan, "pass": pass_index}
                item.update(result)
                if result["created"] and result["valid"]:
                    report["applied_count"] += 1
                    report["applied"].append(item)
                    progress_made = True
                    continue
                if (
                    kind == "merge_points"
                    and partner_entity is not None
                    and index is not None
                    and partner_index is not None
                ):
                    try:
                        if _constraint_points_are_coincident(entity, index, partner_entity, partner_index):
                            if pass_index < max_passes:
                                progress_made = True
                                next_pending.append((plan, dict(item, note="retry_coincident_points_on_next_pass")))
                                continue
                            skipped_item = dict(item)
                            skipped_item["reason"] = "redundant_coincident_points"
                            report["skipped_count"] += 1
                            report["skipped"].append(skipped_item)
                            progress_made = True
                            continue
                    except Exception:
                        pass
                if kind == "point_on_curve" and partner_entity is not None and index is not None:
                    try:
                        point = _constraint_point_coordinates(entity, index)
                        if _point_line_distance(point, partner_entity) <= 1e-6:
                            if pass_index < max_passes:
                                progress_made = True
                                next_pending.append((plan, dict(item, note="retry_redundant_point_on_curve_on_next_pass")))
                                continue
                            skipped_item = dict(item)
                            skipped_item["reason"] = "redundant_point_on_curve"
                            report["skipped_count"] += 1
                            report["skipped"].append(skipped_item)
                            progress_made = True
                            continue
                    except Exception:
                        pass
                next_pending.append((plan, dict(item, error="constraint_create_returned_false")))
            except Exception as exc:
                next_pending.append((plan, {"constraint": plan, "pass": pass_index, "error": str(exc)}))

        if not next_pending:
            pending = []
            break
        if not progress_made:
            report["failed"].extend(item for _, item in next_pending)
            pending = []
            break
        pending = [plan for plan, _ in next_pending]

    if pending:
        already_failed = {id(item.get("constraint")) for item in report["failed"]}
        for plan in pending:
            if id(plan) in already_failed:
                continue
            report["failed"].append({"constraint": plan, "error": "constraint_retry_limit_exceeded", "pass": pass_index})

    report["failed_count"] = len(report["failed"])
    report["live_status"] = "applied" if report["failed_count"] == 0 else "partial"
    if report["applied_count"] == 0 and report["failed_count"] > 0:
        report["live_status"] = "failed"
    return report


def _merge_constraint_reports(primary_report, secondary_report):
    if primary_report is None:
        return secondary_report
    if secondary_report is None:
        return primary_report
    merged = {
        "enabled": bool(primary_report.get("enabled") or secondary_report.get("enabled")),
        "planned_count": int(primary_report.get("planned_count", 0)) + int(secondary_report.get("planned_count", 0)),
        "applied_count": int(primary_report.get("applied_count", 0)) + int(secondary_report.get("applied_count", 0)),
        "failed_count": int(primary_report.get("failed_count", 0)) + int(secondary_report.get("failed_count", 0)),
        "skipped_count": int(primary_report.get("skipped_count", 0)) + int(secondary_report.get("skipped_count", 0)),
        "applied": list(primary_report.get("applied") or []) + list(secondary_report.get("applied") or []),
        "failed": list(primary_report.get("failed") or []) + list(secondary_report.get("failed") or []),
        "skipped": list(primary_report.get("skipped") or []) + list(secondary_report.get("skipped") or []),
    }
    if not merged["enabled"]:
        merged["live_status"] = "disabled"
    elif merged["failed_count"] == 0:
        merged["live_status"] = "applied"
    elif merged["applied_count"] == 0:
        merged["live_status"] = "failed"
    else:
        merged["live_status"] = "partial"
    return merged


def _constraint_is_anchor_stage(plan):
    explicit_stage = str(plan.get("stage") or "").strip().lower()
    if explicit_stage in {"anchor", "pre", "before_dimensions"}:
        return True
    if explicit_stage in {"final", "post", "after_dimensions"}:
        return False
    kind = str(plan.get("kind") or "")
    if kind in {"fixed_point", "horizontal", "vertical", "equal_length"}:
        return True
    if kind != "merge_points":
        return False
    target = str(plan.get("target") or "")
    partner = str(plan.get("partner") or "")
    late_tokens = (
        "profile_line",
        "projection_ref",
        "surface_taper_ref",
        "root_taper_ref",
        "left_theory",
        "right_theory",
    )
    return not any(token in target or token in partner for token in late_tokens)


def _split_staged_constraints(planned_constraints):
    anchor = []
    final = []
    for plan in planned_constraints or []:
        if _constraint_is_anchor_stage(plan):
            anchor.append(plan)
        else:
            final.append(plan)
    return anchor, final


def _format_dimension_expression(value):
    if isinstance(value, str):
        return value
    return ("%s" % float(value)).rstrip("0").rstrip(".")


def _apply_dimension_display(dimension_object, dimension):
    display_mode = str(dimension.get("display_mode") or "radius").strip().lower()
    if display_mode != "diameter":
        return {"display_overridden": False}
    if bool(dimension.get("native_break")):
        return {
            "display_overridden": False,
            "display_mode": "diameter",
            "display_native": True,
            "display_value": dimension.get("display_value", dimension.get("value")),
        }

    text = _cast_to_com_interface(dimension_object, "IDimensionText")
    text.AutoNominalValue = False
    text.Prefix.Str = str(dimension.get("display_prefix") or "Ø")
    display_value = dimension.get("display_value")
    if display_value in (None, ""):
        display_value = dimension.get("value")
    text.NominalText.Str = _format_dimension_expression(display_value)
    return {
        "display_overridden": True,
        "display_mode": "diameter",
        "display_value": display_value,
        "display_prefix": text.Prefix.Str,
        "display_text": text.NominalText.Str,
    }


def _create_dimension_constraint(dimension_object, constraint_type, *, variable=None, expression=None, value=None):
    drawing_object = _cast_to_com_interface(dimension_object, "IDrawingObject1")
    constraint = safe_get(drawing_object, "NewConstraint")
    if not callable(constraint):
        raise RuntimeError("dimension does not expose IDrawingObject1.NewConstraint")
    new_constraint = constraint()
    if new_constraint is None:
        raise RuntimeError("dimension NewConstraint returned None")
    new_constraint.ConstraintType = int(constraint_type)
    if variable:
        new_constraint.Variable = str(variable)
    if expression not in (None, ""):
        new_constraint.Expression = str(expression)
    elif value not in (None, ""):
        new_constraint.Value = float(value)
    created = bool(new_constraint.Create())
    return {
        "created": created,
        "reference": safe_get(new_constraint, "Reference"),
        "valid": bool(safe_get(new_constraint, "Valid", False)),
        "type": int(constraint_type),
        "variable": safe_get(new_constraint, "Variable"),
        "expression": safe_get(new_constraint, "Expression"),
    }


def _finalize_driving_dimension(dimension_object, dimension):
    drawing_object = _cast_to_com_interface(dimension_object, "IDrawingObject1")
    associate = safe_get(drawing_object, "Associate")
    associated = bool(associate()) if callable(associate) else False
    fixed_result = _create_dimension_constraint(dimension_object, 14)
    variable_name = dimension.get("variable") or dimension.get("name")
    expression = dimension.get("expression")
    if expression in (None, "") and dimension.get("value") not in (None, ""):
        expression = _format_dimension_expression(dimension.get("value"))
    variable_result = _create_dimension_constraint(
        dimension_object,
        13,
        variable=variable_name,
        expression=expression,
        value=dimension.get("value"),
    )
    allow_variable_only = str(dimension.get("kind") or "") in {"angle_between_lines"}
    result = {
        "associated": associated,
        "fixed_constraint": fixed_result,
        "variable_constraint": variable_result,
        "driving_created": bool(variable_result["created"] and (fixed_result["created"] or allow_variable_only)),
    }
    result.update(_apply_dimension_display(dimension_object, dimension))
    return result


def _add_line_dimension(line_dimensions, dimension, sketch_entities):
    target = sketch_entities.get(str(dimension.get("target")))
    if target is None:
        raise RuntimeError("target_line_not_found")
    orientation = LINE_DIMENSION_ORIENTATIONS.get(str(dimension.get("orientation") or "parallel"), 0)
    dim = line_dimensions.Add()
    if dim is None:
        raise RuntimeError("LineDimensions.Add returned None")
    x1, y1, x2, y2 = _line_geometry(target)
    placement_index = int(dimension.get("placement_index") or 0)
    dim.X1 = x1
    dim.Y1 = y1
    dim.X2 = x2
    dim.Y2 = y2
    dim.X3 = float(dimension.get("point_x", (x1 + x2) / 2.0))
    dim.Y3 = float(dimension.get("point_y", -8.0 - placement_index * 8.0))
    dim.Orientation = int(orientation)
    updated = bool(dim.Update())
    result = {
        "updated": updated,
        "reference": safe_get(dim, "Reference"),
        "orientation": orientation,
        "driving_created": False,
    }
    if updated and bool(dimension.get("driving", True)):
        result.update(_finalize_driving_dimension(dim, dimension))
    return result


def _add_axis_distance_dimension(line_dimensions, axis_line, dimension, sketch_entities):
    target = sketch_entities.get(str(dimension.get("target")))
    if target is None:
        raise RuntimeError("target_line_not_found")
    origin = sketch_entities.get("origin")
    if origin is None:
        raise RuntimeError("origin_point_not_found")
    x1, y1, x2, y2 = _line_geometry(target)
    placement_index = int(dimension.get("placement_index") or 0)
    point_x = float(dimension.get("point_x", float(x1 + x2) / 2.0))
    point_y = float(dimension.get("point_y", float(y1 + y2) / 2.0))
    # Ordinary linear dimension between the sketch origin and the left endpoint
    # of the horizontal step keeps the graphic readable and anchors every radius
    # the same way as the first one.
    support_point_index = dimension.get("support_point_index")
    if support_point_index in (0, "0", "start"):
        support_x = float(x1)
        support_y = float(y1)
    elif support_point_index in (1, "1", "end"):
        support_x = float(x2)
        support_y = float(y2)
    elif float(x1) <= float(x2):
        support_x = float(x1)
        support_y = float(y1)
    else:
        support_x = float(x2)
        support_y = float(y2)

    dim = line_dimensions.Add()
    if dim is None:
        raise RuntimeError("LineDimensions.Add returned None")
    dim.X1 = float(origin.get("x", 0.0))
    dim.Y1 = float(origin.get("y", 0.0))
    dim.X2 = support_x
    dim.Y2 = support_y
    visible_x3 = max(x1, x2) + 8.0 + placement_index * 6.0
    visible_y3 = point_y
    dim.X3 = visible_x3
    dim.Y3 = visible_y3
    dim.Orientation = int(LINE_DIMENSION_ORIENTATIONS["vertical"])
    updated = bool(dim.Update())
    result = {
        "updated": updated,
        "reference": safe_get(dim, "Reference"),
        "orientation": LINE_DIMENSION_ORIENTATIONS["vertical"],
        "driving_created": False,
    }
    if updated and bool(dimension.get("driving", True)):
        result.update(_finalize_driving_dimension(dim, dimension))
    return result


def _add_break_line_dimension(break_line_dimensions, axis_line, dimension, sketch_entities):
    target = sketch_entities.get(str(dimension.get("target")))
    if target is None:
        raise RuntimeError("target_line_not_found")
    dim = break_line_dimensions.Add()
    if dim is None:
        raise RuntimeError("BreakLineDimensions.Add returned None")
    x1, y1, x2, y2 = _line_geometry(target)
    placement_index = int(dimension.get("placement_index") or 0)
    dim.BaseObject = axis_line
    dim.X1 = x1
    dim.Y1 = y1
    dim.X2 = x2
    dim.Y2 = y2
    dim.X3 = max(x1, x2) + 10.0 + placement_index * 8.0
    dim.Y3 = float(y1)
    updated = bool(dim.Update())
    result = {
        "updated": updated,
        "reference": safe_get(dim, "Reference"),
        "orientation": "break_line",
        "driving_created": False,
    }
    if updated and bool(dimension.get("driving", True)):
        result.update(_finalize_driving_dimension(dim, dimension))
    return result


def _shared_line_vertex(target_entity, partner_entity):
    target_start = (float(target_entity["x1"]), float(target_entity["y1"]))
    target_end = (float(target_entity["x2"]), float(target_entity["y2"]))
    partner_start = (float(partner_entity["x1"]), float(partner_entity["y1"]))
    partner_end = (float(partner_entity["x2"]), float(partner_entity["y2"]))
    candidates = (
        (target_start, target_end, partner_start, partner_end),
        (target_start, target_end, partner_end, partner_start),
        (target_end, target_start, partner_start, partner_end),
        (target_end, target_start, partner_end, partner_start),
    )
    for vertex, target_far, partner_vertex, partner_far in candidates:
        if abs(vertex[0] - partner_vertex[0]) <= 1e-6 and abs(vertex[1] - partner_vertex[1]) <= 1e-6:
            return vertex, target_far, partner_far
    return None


def _normalize_vector(x, y):
    length = math.hypot(float(x), float(y))
    if length <= 1e-9:
        return None
    return (float(x) / length, float(y) / length)


def _add_angle_dimension(angle_dimensions, dimension, sketch_entities):
    target = sketch_entities.get(str(dimension.get("target")))
    partner = sketch_entities.get(str(dimension.get("partner")))
    if target is None or partner is None:
        raise RuntimeError("target_or_partner_line_not_found")
    target_object = target.get("object")
    partner_object = partner.get("object")
    if target_object is None or partner_object is None:
        raise RuntimeError("target_or_partner_object_not_found")

    dim = angle_dimensions.Add(10)
    if dim is None:
        raise RuntimeError("AngleDimensions.Add returned None")

    dim.BaseObject1 = target_object
    dim.BaseObject2 = partner_object

    target_x1, target_y1, target_x2, target_y2 = _line_geometry(target)
    partner_x1, partner_y1, partner_x2, partner_y2 = _line_geometry(partner)
    shared = _shared_line_vertex(
        {"x1": target_x1, "y1": target_y1, "x2": target_x2, "y2": target_y2},
        {"x1": partner_x1, "y1": partner_y1, "x2": partner_x2, "y2": partner_y2},
    )
    if shared is not None:
        vertex, target_far, partner_far = shared
        placement_index = int(dimension.get("placement_index") or 0)
        placement_distance = max(
            math.hypot(target_x2 - target_x1, target_y2 - target_y1),
            math.hypot(partner_x2 - partner_x1, partner_y2 - partner_y1),
            1.0,
        ) * (1.6 + placement_index * 0.2)
        target_vector = _normalize_vector(target_far[0] - vertex[0], target_far[1] - vertex[1])
        partner_vector = _normalize_vector(partner_far[0] - vertex[0], partner_far[1] - vertex[1])
        bisector = None
        if target_vector is not None and partner_vector is not None:
            bisector = _normalize_vector(
                target_vector[0] + partner_vector[0],
                target_vector[1] + partner_vector[1],
            )
        if bisector is None:
            opening_y = ((target_far[1] + partner_far[1]) / 2.0) - vertex[1]
            opening_sign = 1.0 if opening_y >= 0.0 else -1.0
            default_point_x = vertex[0]
            default_point_y = vertex[1] + opening_sign * placement_distance
        else:
            side = str(dimension.get("placement_side") or "").strip().lower()
            direction = -1.0 if side == "opposite_bisector" else 1.0
            default_point_x = vertex[0] + bisector[0] * placement_distance * direction
            default_point_y = vertex[1] + bisector[1] * placement_distance * direction
        dim.X3 = float(dimension.get("point_x", default_point_x))
        dim.Y3 = float(dimension.get("point_y", default_point_y))

    updated = bool(dim.Update())
    result = {
        "updated": updated,
        "reference": safe_get(dim, "Reference"),
        "orientation": "angle",
        "driving_created": False,
    }
    if updated and bool(dimension.get("driving", True)):
        result.update(_finalize_driving_dimension(dim, dimension))
    return result


def _add_circle_diameter_dimension(diametral_dimensions, dimension, sketch_entities):
    target = sketch_entities.get(str(dimension.get("target")))
    if target is None:
        raise RuntimeError("target_circle_not_found")
    circle_object = target.get("object")
    if circle_object is None:
        raise RuntimeError("target_circle_object_not_found")

    dim = diametral_dimensions.Add()
    if dim is None:
        raise RuntimeError("DiametralDimensions.Add returned None")

    try:
        dim.BaseObject = circle_object
    except Exception:
        set_base_object = safe_get(dim, "SetBaseObject")
        if callable(set_base_object):
            set_base_object(circle_object)
        else:
            raise

    dimension_type = bool(dimension.get("dimension_type", False))
    try:
        dim.DimensionType = dimension_type
    except Exception:
        set_dimension_type = safe_get(dim, "SetDimensionType")
        if callable(set_dimension_type):
            set_dimension_type(dimension_type)
        else:
            raise

    angle = float(dimension.get("angle", 0.0))
    try:
        dim.Angle = angle
    except Exception:
        set_angle = safe_get(dim, "SetAngle")
        if callable(set_angle):
            set_angle(angle)
        else:
            raise

    updated = bool(dim.Update())
    result = {
        "updated": updated,
        "reference": safe_get(dim, "Reference"),
        "orientation": "diameter",
        "driving_created": False,
    }
    if updated and bool(dimension.get("driving", True)):
        result.update(_finalize_driving_dimension(dim, dimension))
    return result


def _apply_sketch_dimensions(view, sketch_entities, planned_dimensions, options):
    enabled = bool((options or {}).get("enabled", False))
    driving = bool((options or {}).get("driving", True))
    report = {
        "enabled": enabled,
        "driving": driving,
        "planned_count": len(planned_dimensions),
        "applied_count": 0,
        "failed_count": 0,
        "live_status": "disabled" if not enabled else "not_started",
        "applied": [],
        "failed": [],
    }
    if not enabled:
        return report
    try:
        symbols_container = _cast_to_com_interface(view, "ISymbols2DContainer")
        line_dimensions = safe_get(symbols_container, "LineDimensions")
        break_line_dimensions = safe_get(symbols_container, "BreakLineDimensions")
        diametral_dimensions = safe_get(symbols_container, "DiametralDimensions")
        angle_dimensions = safe_get(symbols_container, "AngleDimensions")
        if line_dimensions is None:
            get_line_dimensions = safe_get(symbols_container, "GetLineDimensions")
            if callable(get_line_dimensions):
                line_dimensions = get_line_dimensions()
        if break_line_dimensions is None:
            get_break_line_dimensions = safe_get(symbols_container, "GetBreakLineDimensions")
            if callable(get_break_line_dimensions):
                break_line_dimensions = get_break_line_dimensions()
        if diametral_dimensions is None:
            get_diametral_dimensions = safe_get(symbols_container, "GetDiametralDimensions")
            if callable(get_diametral_dimensions):
                diametral_dimensions = get_diametral_dimensions()
        if angle_dimensions is None:
            get_angle_dimensions = safe_get(symbols_container, "GetAngleDimensions")
            if callable(get_angle_dimensions):
                angle_dimensions = get_angle_dimensions()
        if line_dimensions is None or not callable(safe_get(line_dimensions, "Add")):
            raise RuntimeError("view does not expose ISymbols2DContainer.LineDimensions.Add")
    except Exception as exc:
        report["failed_count"] = len(planned_dimensions)
        report["failed"] = [{"dimension": dimension, "error": str(exc)} for dimension in planned_dimensions]
        report["live_status"] = "failed"
        return report

    axis_entity = sketch_entities.get("axis")
    axis_line = axis_entity.get("object") if axis_entity else None
    for dimension in planned_dimensions:
        try:
            dimension_payload = dict(dimension)
            dimension_payload["driving"] = driving and bool(dimension.get("driving", True))
            kind = str(dimension_payload.get("kind") or "")
            if kind == "line_length":
                result = _add_line_dimension(line_dimensions, dimension_payload, sketch_entities)
            elif kind == "circle_diameter":
                if diametral_dimensions is None or not callable(safe_get(diametral_dimensions, "Add")):
                    raise RuntimeError("view does not expose ISymbols2DContainer.DiametralDimensions.Add")
                result = _add_circle_diameter_dimension(diametral_dimensions, dimension_payload, sketch_entities)
            elif kind == "axis_distance":
                if str(dimension_payload.get("display_mode") or "").strip().lower() == "diameter":
                    if axis_line is None:
                        raise RuntimeError("axis_line_not_found")
                    if break_line_dimensions is None or not callable(safe_get(break_line_dimensions, "Add")):
                        raise RuntimeError("view does not expose ISymbols2DContainer.BreakLineDimensions.Add")
                    result = _add_break_line_dimension(break_line_dimensions, axis_line, dimension_payload, sketch_entities)
                else:
                    result = _add_axis_distance_dimension(line_dimensions, axis_line, dimension_payload, sketch_entities)
            elif kind == "angle_between_lines":
                if angle_dimensions is None or not callable(safe_get(angle_dimensions, "Add")):
                    raise RuntimeError("view does not expose ISymbols2DContainer.AngleDimensions.Add")
                result = _add_angle_dimension(angle_dimensions, dimension_payload, sketch_entities)
            else:
                raise RuntimeError("unsupported_dimension_kind")
            item = {"dimension": dimension}
            item.update(result)
            if result["updated"] and (not dimension_payload.get("driving") or result.get("driving_created", False)):
                report["applied_count"] += 1
                report["applied"].append(item)
            else:
                failed_item = dict(item)
                failed_item["error"] = "dimension_constraint_not_applied" if result["updated"] else "dimension_update_returned_false"
                report["failed"].append(failed_item)
        except Exception as exc:
            report["failed"].append({"dimension": dimension, "error": str(exc)})

    report["failed_count"] = len(report["failed"])
    report["live_status"] = "applied" if report["failed_count"] == 0 else "partial"
    if report["applied_count"] == 0 and report["failed_count"] > 0:
        report["live_status"] = "failed"
    return report


def _merge_dimension_reports(primary_report, secondary_report):
    if primary_report is None:
        return secondary_report
    if secondary_report is None:
        return primary_report
    merged = {
        "enabled": bool(primary_report.get("enabled") or secondary_report.get("enabled")),
        "driving": bool(primary_report.get("driving") or secondary_report.get("driving")),
        "planned_count": int(primary_report.get("planned_count", 0)) + int(secondary_report.get("planned_count", 0)),
        "applied_count": int(primary_report.get("applied_count", 0)) + int(secondary_report.get("applied_count", 0)),
        "failed_count": int(primary_report.get("failed_count", 0)) + int(secondary_report.get("failed_count", 0)),
        "applied": list(primary_report.get("applied") or []) + list(secondary_report.get("applied") or []),
        "failed": list(primary_report.get("failed") or []) + list(secondary_report.get("failed") or []),
    }
    if not merged["enabled"]:
        merged["live_status"] = "disabled"
    elif merged["failed_count"] == 0:
        merged["live_status"] = "applied"
    elif merged["applied_count"] == 0:
        merged["live_status"] = "failed"
    else:
        merged["live_status"] = "partial"
    return merged


def _apply_sketch_parameterization(view, sketch_entities, planned_constraints, planned_dimensions, sketch_options, steps, total_length):
    constraints = sketch_options.get("constraints") or {}
    dimensions = sketch_options.get("dimensions") or {}
    parameterization_order = str(sketch_options.get("parameterization_order") or "dimensions_first").strip().lower()
    deferred_dimension_kinds = {"angle_between_lines"}
    primary_dimensions = [dimension for dimension in planned_dimensions if str(dimension.get("kind") or "") not in deferred_dimension_kinds]
    deferred_dimensions = [dimension for dimension in planned_dimensions if str(dimension.get("kind") or "") in deferred_dimension_kinds]
    if parameterization_order in {"anchored_dimensions_then_constraints", "staged"}:
        anchor_constraints, final_constraints = _split_staged_constraints(planned_constraints)
        anchor_constraints_report = _apply_sketch_constraints(sketch_entities, anchor_constraints, constraints)
        primary_dimensions_report = _apply_sketch_dimensions(view, sketch_entities, primary_dimensions, dimensions)
        final_constraints_report = _apply_sketch_constraints(sketch_entities, final_constraints, constraints)
        constraints_report = _merge_constraint_reports(anchor_constraints_report, final_constraints_report)
        constraints_report["anchor_stage"] = {
            "planned_count": len(anchor_constraints),
            "applied_count": anchor_constraints_report.get("applied_count"),
            "failed_count": anchor_constraints_report.get("failed_count"),
        }
        constraints_report["final_stage"] = {
            "planned_count": len(final_constraints),
            "applied_count": final_constraints_report.get("applied_count"),
            "failed_count": final_constraints_report.get("failed_count"),
        }
        deferred_dimensions_report = _apply_sketch_dimensions(view, sketch_entities, deferred_dimensions, dimensions)
    elif parameterization_order == "constraints_first":
        constraints_report = _apply_sketch_constraints(sketch_entities, planned_constraints, constraints)
        primary_dimensions_report = _apply_sketch_dimensions(view, sketch_entities, primary_dimensions, dimensions)
        deferred_dimensions_report = _apply_sketch_dimensions(view, sketch_entities, deferred_dimensions, dimensions)
    else:
        primary_dimensions_report = _apply_sketch_dimensions(view, sketch_entities, primary_dimensions, dimensions)
        constraints_report = _apply_sketch_constraints(sketch_entities, planned_constraints, constraints)
        deferred_dimensions_report = _apply_sketch_dimensions(view, sketch_entities, deferred_dimensions, dimensions)
    dimensions_report = _merge_dimension_reports(primary_dimensions_report, deferred_dimensions_report)
    geometry_checks = _verify_sketch_constraint_geometry(
        sketch_entities,
        planned_constraints,
        tolerance=float(sketch_options.get("readback_tolerance") or 1e-6),
    ) if bool(sketch_options.get("readback_geometry", False)) else {"ok": True, "checked_count": 0, "failed_count": 0}
    ok = (
        constraints_report["live_status"] in ("disabled", "applied", "partial")
        and dimensions_report["live_status"] in ("disabled", "applied", "partial")
        and bool(geometry_checks.get("ok", True))
    )
    return {
        "step": "sketch_parameterization",
        "ok": ok,
        "parameterization_order": parameterization_order,
        "constraints": constraints_report,
        "dimensions": dimensions_report,
        "geometry_checks": geometry_checks,
        "line_readback": _snapshot_sketch_line_entities(sketch_entities) if bool(sketch_options.get("readback_geometry", False)) else {},
    }


def _apply_part_variables(part, planned_variables):
    report = {
        "step": "part_variables",
        "ok": True,
        "planned_count": len(planned_variables),
        "applied_count": 0,
        "failed_count": 0,
        "live_status": "disabled" if not planned_variables else "not_started",
        "applied": [],
        "failed": [],
    }
    if not planned_variables:
        return report

    add_variable = safe_get(part, "AddVariable")
    if not callable(add_variable):
        report["ok"] = False
        report["failed_count"] = len(planned_variables)
        report["failed"] = [{"variable": variable, "error": "part does not expose AddVariable"} for variable in planned_variables]
        report["live_status"] = "failed"
        return report

    for variable in planned_variables:
        try:
            name = str(variable.get("name") or "").strip()
            if not name:
                raise RuntimeError("variable_name_required")
            value = variable.get("value")
            initial_value = float(value) if value not in (None, "") else 0.0
            created = add_variable(name, initial_value, str(variable.get("note") or ""))
            if created is None:
                raise RuntimeError("AddVariable returned None")
            if variable.get("external") is not None:
                created.External = bool(variable.get("external"))
            expression = variable.get("expression")
            if expression in (None, "") and value not in (None, ""):
                expression = _format_dimension_expression(value)
            if expression not in (None, ""):
                created.Expression = str(expression)
            update = safe_get(created, "Update")
            update_ok = True
            if callable(update):
                update_ok = bool(update())
            item = {
                "variable": variable,
                "name": safe_get(created, "Name", name),
                "expression": safe_get(created, "Expression"),
                "value": safe_get(created, "Value", initial_value),
                "update_ok": update_ok,
                "reference": safe_get(created, "Reference"),
            }
            report["applied_count"] += 1
            report["applied"].append(item)
        except Exception as exc:
            report["failed"].append({"variable": variable, "error": str(exc)})

    report["failed_count"] = len(report["failed"])
    report["ok"] = report["failed_count"] == 0
    report["live_status"] = "applied" if report["failed_count"] == 0 else "partial"
    if report["applied_count"] == 0 and report["failed_count"] > 0:
        report["live_status"] = "failed"
    return report


def _create_part_document(app, visible):
    doc3 = app.Documents.Add(4, bool(visible))
    if doc3 is None:
        raise RuntimeError("Documents.Add(ksDocumentPart) returned None")
    part = safe_get(doc3, "TopPart")
    if part is None:
        doc3_model = cast_document_3d(doc3)
        part = safe_get(doc3_model, "TopPart")
    if part is None:
        raise RuntimeError("Failed to get part from created document")
    return doc3, part, cast_model_container(part)


def _save_generated_part_document(doc3, app, output_path, close_after_save, steps_report, visible=False):
    output_path = os.path.abspath(os.path.normpath(output_path))
    reopened_document, save_report = _save_document_via_staging(
        doc3,
        app,
        output_path,
        keep_open=not close_after_save,
        visible=visible,
    )
    saved = bool(os.path.exists(output_path))
    steps_report.append(
        {
            "step": "save",
            "ok": saved,
            "output_path": output_path,
            "save_report": save_report,
            "error": None if saved else "target_file_missing_after_replace",
        }
    )
    if not saved:
        raise RuntimeError("Failed to save generated part: target file missing after replace")

    created_document = (
        describe_document(reopened_document, app)
        if reopened_document is not None
        else {
            "id": output_path,
            "name": os.path.basename(output_path),
            "path": output_path,
            "active": False,
            "changed": False,
        }
    )
    return saved, created_document


def _create_point3d(model_container, name, origin):
    points = safe_get(model_container, "Points3D")
    if points is None:
        get_points = safe_get(model_container, "GetPoints3D")
        if callable(get_points):
            points = get_points()
    if points is None:
        raise RuntimeError("Part does not expose Points3D")
    add_point = safe_get(points, "Add")
    point = None
    if callable(add_point):
        point = add_point()
    if point is None and safe_get(points, "_oleobj_") is not None:
        before_count = collection_count(points)
        raw = points._oleobj_.InvokeTypes(2, 0, 1, (9, 0), ())
        if raw not in (None, ""):
            point = _cast_to_com_interface(raw, "IPoint3D")
        if point is None:
            index = collection_count(points) - 1
            if index < 0:
                index = before_count
            getter = safe_get(points, "Point3D")
            point = getter(index) if callable(getter) else None
    if point is None:
        raise RuntimeError("Failed to create Point3D")
    point.Name = str(name or "")
    point.X = float(origin[0])
    point.Y = float(origin[1])
    point.Z = float(origin[2])
    if not point.Update():
        raise RuntimeError("Point3D Update returned False")
    return point


def _resolve_default_part_object(part, system_object):
    normalized = str(system_object or "").strip().lower().replace("-", "_")
    default_object_ids = {
        "xoy_plane": 1,
        "xoz_plane": 2,
        "yoz_plane": 3,
        "origin": 4,
    }
    object_id = default_object_ids.get(normalized)
    if object_id is None:
        raise RuntimeError("Unsupported default part object: %s" % system_object)
    default_object = safe_get(part, "DefaultObject")
    if not callable(default_object):
        default_object = safe_get(part, "GetDefaultObject")
    if not callable(default_object):
        raise RuntimeError("Part does not expose DefaultObject/GetDefaultObject")
    resolved = default_object(object_id)
    if resolved is None:
        raise RuntimeError("Failed to resolve default object %s" % normalized)
    return resolved


def _resolve_part_reference_object(part, reference):
    reference_payload = reference or {}
    system_object = reference_payload.get("system_object") or reference_payload.get("default_object")
    if system_object:
        return _resolve_default_part_object(part, system_object)
    raise RuntimeError("Unsupported reference object: only reference.system_object is supported in live mode for now")


_STEP_FACE_PATTERN = re.compile(r"^step_(\d+)_(start|end)_face$")
_STEP_FACE_PATTERN_COMPACT = re.compile(r"^step(\d+)_(start|end)_face$")
_SHOULDER_FACE_PATTERN = re.compile(r"^shoulder_(\d+)_face$")
_SHOULDER_FACE_PATTERN_COMPACT = re.compile(r"^shoulder(\d+)_face$")
_STEP_OUTER_FACE_PATTERN = re.compile(r"^step_(\d+)_(outer|side|cyl|cylindrical)_face$")
_STEP_OUTER_FACE_PATTERN_COMPACT = re.compile(r"^step(\d+)_(outer|side|cyl|cylindrical)_face$")
_STEP_INNER_FACE_PATTERN = re.compile(r"^step_(\d+)_(inner|bore|cyl|cylindrical)_face$")
_STEP_INNER_FACE_PATTERN_COMPACT = re.compile(r"^step(\d+)_(inner|bore|cyl|cylindrical)_face$")


def _create_point3d_on_object(model_container, name, association_object):
    point = _create_point3d(model_container, name, [0.0, 0.0, 0.0])
    if not bool(point.SetAssociationObject(association_object)):
        raise RuntimeError("Point3D SetAssociationObject returned False")
    if not point.Update():
        raise RuntimeError("Point3D Update returned False after SetAssociationObject")
    return point


def _create_point3d_displace(
    model_container,
    name,
    position_object,
    offset,
    offset_expressions=None,
    guiding_object=None,
    distance=None,
    distance_expression=None,
):
    point = _create_point3d(model_container, name, [0.0, 0.0, 0.0])
    point.ParameterType = 2
    parameters = _cast_to_com_interface(safe_get(point, "Parameters"), "IPoint3DParamDisplace")
    if parameters is None:
        raise RuntimeError("Point3D does not expose IPoint3DParamDisplace")
    if guiding_object is not None or distance is not None:
        set_association_vertex = safe_get(parameters, "SetAssociationVertex")
        set_guiding_object = safe_get(parameters, "SetGuidingObject")
        if position_object is not None:
            if not callable(set_association_vertex):
                raise RuntimeError("Point3D displacement parameters do not expose SetAssociationVertex")
            if not bool(set_association_vertex(position_object)):
                raise RuntimeError("Point3D displacement parameters SetAssociationVertex returned False")
        try:
            parameters.PositionObject = None
        except Exception:
            pass
        if guiding_object is not None:
            if not callable(set_guiding_object):
                raise RuntimeError("Point3D displacement parameters do not expose SetGuidingObject")
            if not bool(set_guiding_object(guiding_object)):
                raise RuntimeError("Point3D displacement parameters SetGuidingObject returned False")
        if distance_expression not in (None, ""):
            parameters.Distance = str(distance_expression)
        else:
            parameters.Distance = float(distance if distance is not None else 0.0)
    else:
        parameters.PositionObject = position_object
        expressions = list(offset_expressions or [])
        components = list(offset or [0.0, 0.0, 0.0])
        while len(expressions) < 3:
            expressions.append(None)
        while len(components) < 3:
            components.append(0.0)
        parameters.DX = str(expressions[0]) if expressions[0] not in (None, "") else float(components[0])
        parameters.DY = str(expressions[1]) if expressions[1] not in (None, "") else float(components[1])
        parameters.DZ = str(expressions[2]) if expressions[2] not in (None, "") else float(components[2])
    if not point.Update():
        raise RuntimeError("Point3D Update returned False for displacement point")
    return point


def _create_point3d_on_curve(model_container, name, curve_object, offset=0.0, *, direction=True, offset_type=0):
    point = _create_point3d(model_container, name, [0.0, 0.0, 0.0])
    point.ParameterType = 5
    parameters = _cast_to_com_interface(safe_get(point, "Parameters"), "IPoint3DParamCurve")
    if parameters is None:
        raise RuntimeError("Point3D does not expose IPoint3DParamCurve")
    set_curve_object = safe_get(parameters, "SetCurveObject")
    if not callable(set_curve_object):
        raise RuntimeError("Point3D curve parameters do not expose SetCurveObject")
    if not bool(set_curve_object(curve_object)):
        raise RuntimeError("Point3D curve parameters SetCurveObject returned False")
    parameters.OffsetType = int(offset_type)
    parameters.Offset = float(offset)
    set_direction = safe_get(parameters, "SetDirection")
    if callable(set_direction):
        set_direction(bool(direction))
    else:
        parameters.Direction = bool(direction)
    if not point.Update():
        raise RuntimeError("Point3D Update returned False for curve point")
    return point


def _signed_distance_expression(expression, sign):
    text = str(expression or "").strip()
    if not text:
        return None
    return "-(%s)" % text if float(sign) < 0.0 else text


def _build_distance_point_bindings(expression, role):
    text = str(expression or "").strip()
    if not text:
        return []
    return [
        {
            "role": str(role or "point_distance"),
            "parameter_note": "Расстояние",
            "parameter_note_aliases": ["Расстояние", "Distance"],
            "expression": text,
        }
    ]


def _estimate_model_object_center(model_object):
    edge = _cast_to_com_interface(model_object, "IEdge")
    if edge is not None:
        edge_points = _sample_edge_points(edge)
        if edge_points:
            return [
                sum(point[0] for point in edge_points) / float(len(edge_points)),
                sum(point[1] for point in edge_points) / float(len(edge_points)),
                sum(point[2] for point in edge_points) / float(len(edge_points)),
            ]

    face = _cast_to_com_interface(model_object, "IFace")
    if face is not None:
        points = []
        for edge_object in _ensure_dispatch_sequence(safe_get(face, "LimitingEdges")):
            points.extend(_sample_edge_points(edge_object))
        if points:
            return [
                sum(point[0] for point in points) / float(len(points)),
                sum(point[1] for point in points) / float(len(points)),
                sum(point[2] for point in points) / float(len(points)),
            ]

    return [0.0, 0.0, 0.0]


def _create_point3d_center_on_object(model_container, name, association_object):
    point = _create_point3d(model_container, name, [0.0, 0.0, 0.0])
    point.ParameterType = 4
    parameters = _cast_to_com_interface(safe_get(point, "Parameters"), "IPoint3DParamCenter")
    if parameters is None:
        raise RuntimeError("Point3D does not expose IPoint3DParamCenter")
    if not bool(parameters.SetObject(association_object)):
        raise RuntimeError("Point3D center parameters SetObject returned False")
    estimated_center = _estimate_model_object_center(association_object)
    point.X = float(estimated_center[0])
    point.Y = float(estimated_center[1])
    point.Z = float(estimated_center[2])
    if not point.Update():
        raise RuntimeError("Point3D Update returned False for center_of_object point")
    parameters = _cast_to_com_interface(safe_get(point, "Parameters"), "IPoint3DParamCenter")
    if parameters is None:
        raise RuntimeError("Point3D center parameters do not expose SetObject")
    return point


def _create_axis3d_by_2_points(part, name, point1, point2):
    auxiliary = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    if auxiliary is None:
        raise RuntimeError("Part does not expose IAuxiliaryGeomContainer")
    axes = safe_get(auxiliary, "Axes3D")
    if axes is None:
        get_axes = safe_get(auxiliary, "GetAxes3D")
        if callable(get_axes):
            axes = get_axes()
    if axes is None or not callable(safe_get(axes, "Add")):
        raise RuntimeError("Part does not expose Axes3D.Add")

    import win32com.client

    axis = win32com.client.CastTo(axes.Add(10), "IAxis3DBy2Points")
    axis.Name = str(name or "")
    axis.Point1 = point1
    axis.Point2 = point2
    if not axis.Update():
        raise RuntimeError("Axis3DBy2Points Update returned False")
    return axis


def _create_axis3d_by_cone_face(part, name, face):
    auxiliary = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    if auxiliary is None:
        raise RuntimeError("Part does not expose IAuxiliaryGeomContainer")
    axes = safe_get(auxiliary, "Axes3D")
    if axes is None:
        get_axes = safe_get(auxiliary, "GetAxes3D")
        if callable(get_axes):
            axes = get_axes()
    if axes is None or not callable(safe_get(axes, "Add")):
        raise RuntimeError("Part does not expose Axes3D.Add")

    import win32com.client

    axis = win32com.client.CastTo(axes.Add(11), "IAxis3DByConeface")
    axis.Name = str(name or "")
    try:
        axis.Face = face
    except Exception:
        if not bool(axis.SetFace(face)):
            raise RuntimeError("Axis3DByConeface SetFace returned False")
    if not axis.Update():
        raise RuntimeError("Axis3DByConeface Update returned False")
    return axis


def _create_circular_feature_pattern(
    model_container,
    name,
    source_feature,
    axis_object,
    count,
    angle_step_degrees,
    clockwise=False,
    count_expression=None,
    angle_step_expression=None,
):
    import win32com.client

    feature_patterns = safe_get(model_container, "FeaturePatterns")
    if feature_patterns is None:
        get_feature_patterns = safe_get(model_container, "GetFeaturePatterns")
        if callable(get_feature_patterns):
            feature_patterns = get_feature_patterns()
    if feature_patterns is None or not callable(safe_get(feature_patterns, "Add")):
        raise RuntimeError("Part does not expose FeaturePatterns.Add")

    pattern = win32com.client.CastTo(feature_patterns.Add(36), "ICircularPattern")
    pattern.Name = str(name or "")
    pattern.Axis = axis_object
    pattern.Count1 = 1
    pattern.Count2 = str(count_expression) if count_expression not in (None, "") else int(count)
    pattern.Step1 = 0.0
    pattern.Step2 = str(angle_step_expression) if angle_step_expression not in (None, "") else float(angle_step_degrees)
    pattern.StepByAxis = 0.0
    pattern.ReverseDirection = bool(clockwise)
    pattern.SaveInitialOrientation = True
    pattern.BuildingType = 0
    pattern.BoundaryInstancesStepFactor1 = False
    pattern.BoundaryInstancesStepFactor2 = False
    if not bool(pattern.AddInitialObjects(source_feature)):
        raise RuntimeError("CircularPattern AddInitialObjects returned False")
    if not pattern.Update():
        raise RuntimeError("CircularPattern Update returned False")
    return pattern


def _ensure_dispatch_sequence(value):
    if value is None:
        return []
    if isinstance(value, tuple):
        return [item for item in value if item is not None]
    return [value]


def _extract_stepped_shaft_preview_data(preview, params):
    planned_constraints = []
    planned_dimensions = []
    planned_variables = []
    profile_points = []
    construction_lines = []
    axis_start = None
    axis_end = None
    for operation in (preview or {}).get("operations") or []:
        if operation.get("operation") == "add_variables":
            planned_variables = operation.get("variables") or []
        elif operation.get("operation") == "apply_constraints":
            planned_constraints = operation.get("constraints") or []
        elif operation.get("operation") == "add_dimensions":
            planned_dimensions = operation.get("dimensions") or []
        elif operation.get("operation") == "draw_profile":
            profile_points = operation.get("profile_points") or []
            construction_lines = operation.get("construction_lines") or []
        elif operation.get("operation") == "draw_axis":
            axis_start = operation.get("start")
            axis_end = operation.get("end")
    if len(profile_points) < 4:
        raise RuntimeError("Invalid stepped_shaft profile")
    if not isinstance(axis_start, list) or len(axis_start) != 2:
        axis_start = [float(profile_points[0][0]), float(profile_points[0][1])]
    if not isinstance(axis_end, list) or len(axis_end) != 2:
        axis_end = [float(axis_start[0]) + float(params.get("total_length") or profile_points[-2][0]), float(axis_start[1])]
    return {
        "steps": params.get("steps") or [],
        "profile_points": profile_points,
        "construction_lines": construction_lines,
        "planned_constraints": planned_constraints,
        "planned_dimensions": planned_dimensions,
        "planned_variables": planned_variables,
        "axis_start": axis_start,
        "axis_end": axis_end,
    }


def _build_stepped_shaft_feature(part, model_container, params, preview, steps_report, coordinate_system=None, operation_kind="boss"):
    extracted = _extract_stepped_shaft_preview_data(preview, params)
    steps = extracted["steps"]
    profile_points = extracted["profile_points"]
    construction_lines = extracted["construction_lines"]
    planned_constraints = extracted["planned_constraints"]
    planned_dimensions = extracted["planned_dimensions"]
    planned_variables = extracted["planned_variables"]
    axis_start = extracted["axis_start"]
    axis_end = extracted["axis_end"]

    plane_map = {"XOY": 1, "XOZ": 2, "YOZ": 3}
    plane_id = plane_map.get(str(params.get("plane") or "XOY").upper(), 1)
    default_object = safe_get(part, "DefaultObject")
    if not callable(default_object):
        default_object = safe_get(part, "GetDefaultObject")
    if not callable(default_object):
        raise RuntimeError("Part does not expose DefaultObject/GetDefaultObject")
    plane = default_object(plane_id)
    if plane is None:
        raise RuntimeError("Failed to get default sketch plane")

    sketchs = safe_get(model_container, "Sketchs")
    if sketchs is None:
        get_sketchs = safe_get(model_container, "GetSketchs")
        if callable(get_sketchs):
            sketchs = get_sketchs()
    if sketchs is None or not callable(safe_get(sketchs, "Add")):
        raise RuntimeError("Part does not expose Sketchs.Add")
    sketch = sketchs.Add()
    if sketch is None:
        raise RuntimeError("Sketchs.Add returned None")
    sketch.Plane = plane
    if coordinate_system is not None:
        sketch.CoordinateSystem = coordinate_system
    if params.get("name"):
        try:
            sketch.Name = "%s profile" % params.get("name")
        except Exception:
            pass
    if not sketch.Update():
        raise RuntimeError("Sketch Update returned False")
    steps_report.append({"step": "create_sketch", "ok": True, "api": "api7_sketchs_add", "plane": params.get("plane") or "XOY"})

    steps_report.append(_apply_part_variables(part, planned_variables))

    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    line_count = 0
    line_style_report = []
    sketch_entities = {}
    parameterization_report = None
    try:
        views_manager = safe_get(sketch_doc, "ViewsAndLayersManager")
        if views_manager is None:
            get_views_manager = safe_get(sketch_doc, "GetViewsAndLayersManager")
            if callable(get_views_manager):
                views_manager = get_views_manager()
        views = safe_get(views_manager, "Views") if views_manager is not None else None
        if views is None:
            raise RuntimeError("Sketch document does not expose ViewsAndLayersManager.Views")
        view = None
        for accessor_name, accessor_arg in (("View", 0), ("Item", 0), ("View", 1), ("Item", 1)):
            accessor = safe_get(views, accessor_name)
            if not callable(accessor):
                continue
            try:
                view = accessor(accessor_arg)
                if view is not None:
                    break
            except Exception:
                continue
        if view is None:
            raise RuntimeError("Failed to get sketch system view")

        drawing_container = cast_drawing_container(view)
        line_segments = safe_get(drawing_container, "LineSegments")
        if line_segments is None:
            get_line_segments = safe_get(drawing_container, "GetLineSegments")
            if callable(get_line_segments):
                line_segments = get_line_segments()
        if line_segments is None or not callable(safe_get(line_segments, "Add")):
            raise RuntimeError("Sketch view does not expose LineSegments.Add")
        circles = safe_get(drawing_container, "Circles")
        if circles is None:
            get_circles = safe_get(drawing_container, "GetCircles")
            if callable(get_circles):
                circles = get_circles()
        if circles is None or not callable(safe_get(circles, "Add")):
            raise RuntimeError("Sketch view does not expose Circles.Add")

        sketch_options = params.get("sketch") or {}
        axis_line_style = int(sketch_options.get("axis_line_style", 3))
        profile_line_style = int(sketch_options.get("profile_line_style", 1))

        def add_line(x1, y1, x2, y2, style, role):
            line = line_segments.Add()
            if line is None:
                raise RuntimeError("LineSegments.Add returned None")
            line.X1 = float(x1)
            line.Y1 = float(y1)
            line.X2 = float(x2)
            line.Y2 = float(y2)
            requested_style = int(style)
            style_setter = "Style"
            try:
                line.Style = requested_style
            except Exception:
                set_style = safe_get(line, "SetStyle")
                if callable(set_style):
                    set_style(requested_style)
                    style_setter = "SetStyle"
                else:
                    raise
            if not line.Update():
                raise RuntimeError("LineSegment Update returned False")
            actual_style = safe_get(line, "Style")
            if actual_style is None:
                get_style = safe_get(line, "GetStyle")
                if callable(get_style):
                    try:
                        actual_style = get_style()
                    except Exception:
                        actual_style = None
            line_style_report.append(
                {
                    "role": role,
                    "requested_style": requested_style,
                    "actual_style": actual_style,
                    "setter": style_setter,
                    "ok": actual_style is None or int(actual_style) == requested_style,
                }
            )
            return line

        axis_start_x = float(axis_start[0])
        axis_start_y = float(axis_start[1])
        axis_end_x = float(axis_end[0])
        axis_end_y = float(axis_end[1])
        sketch_entities["origin"] = _sketch_point_entry(None, axis_start_x, axis_start_y, role="point", target="origin")
        axis_line = add_line(axis_start_x, axis_start_y, axis_end_x, axis_end_y, axis_line_style, "axis")
        sketch_entities["axis"] = _sketch_line_entry(
            axis_line,
            axis_start_x,
            axis_start_y,
            axis_end_x,
            axis_end_y,
            role="axis",
            target="axis",
        )
        line_count += 1
        for construction in construction_lines:
            target = str(construction.get("target") or "").strip()
            start = construction.get("start") or []
            end = construction.get("end") or []
            if not target or not isinstance(start, list) or not isinstance(end, list) or len(start) != 2 or len(end) != 2:
                continue
            line = add_line(
                float(start[0]),
                float(start[1]),
                float(end[0]),
                float(end[1]),
                int(construction.get("line_style", axis_line_style)),
                "construction",
            )
            sketch_entities[target] = _sketch_line_entry(
                line,
                float(start[0]),
                float(start[1]),
                float(end[0]),
                float(end[1]),
                role="construction",
                target=target,
            )
            line_count += 1
        for index in range(len(profile_points) - 1):
            x1, y1 = profile_points[index]
            x2, y2 = profile_points[index + 1]
            target = "profile_line_%s" % (index + 1)
            if x1 == x2 and y1 == y2:
                continue
            if abs(float(y1) - axis_start_y) < 1e-9 and abs(float(y2) - axis_start_y) < 1e-9:
                sketch_entities[target] = _sketch_line_entry(
                    None,
                    float(x1),
                    float(y1),
                    float(x2),
                    float(y2),
                    role="profile",
                    target=target,
                    skipped=True,
                )
                line_style_report.append(
                    {
                        "role": "profile",
                        "requested_style": profile_line_style,
                        "actual_style": None,
                        "setter": "skip_axis_overlap",
                        "ok": True,
                    }
                )
                continue
            line = add_line(float(x1), float(y1), float(x2), float(y2), profile_line_style, "profile")
            sketch_entities[target] = _sketch_line_entry(
                line,
                float(x1),
                float(y1),
                float(x2),
                float(y2),
                role="profile",
                target=target,
            )
            line_count += 1

        parameterization_report = _apply_sketch_parameterization(
            view,
            sketch_entities,
            planned_constraints,
            planned_dimensions,
            params.get("sketch") or {},
            steps,
            params.get("total_length") or (axis_end_x - axis_start_x),
        )
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    if parameterization_report is not None:
        parameterization_report["sketch_state"] = _describe_constraints_state(safe_get(sketch, "ConstraintsState"))
    steps_report.append(
        {
            "step": "draw_profile",
            "ok": True,
            "api": "api7_line_segments",
            "profile_point_count": len(profile_points),
            "line_count": line_count,
            "step_count": len(steps),
            "line_styles": line_style_report,
            "coordinate_system": safe_get(coordinate_system, "Name") if coordinate_system is not None else None,
        }
    )
    steps_report.append(parameterization_report or {"step": "sketch_parameterization", "ok": False, "error": "not_run"})

    rotateds = safe_get(model_container, "Rotateds")
    if rotateds is None:
        get_rotateds = safe_get(model_container, "GetRotateds")
        if callable(get_rotateds):
            rotateds = get_rotateds()
    if rotateds is None or not callable(safe_get(rotateds, "Add")):
        raise RuntimeError("Part does not expose Rotateds.Add")
    rotated_type = 28 if str(operation_kind or "boss").strip().lower() != "cut" else 29
    rotated = rotateds.Add(rotated_type)
    if rotated is None:
        if rotated_type == 29:
            raise RuntimeError("Rotateds.Add(o3d_cutRotated) returned None")
        raise RuntimeError("Rotateds.Add(o3d_bossRotated) returned None")
    rotated.Profile = sketch
    set_profile = safe_get(rotated, "SetProfile")
    if callable(set_profile):
        set_profile(sketch)
    try:
        rotated.Direction = 0
    except Exception:
        pass
    try:
        rotated.ToroidShapeType = False
    except Exception:
        pass
    set_angle = safe_get(rotated, "SetAngle")
    if callable(set_angle):
        set_angle(True, float(params.get("angle_degrees") or 360))
    else:
        rotated.Angle(True, float(params.get("angle_degrees") or 360))
    set_rotated_type = safe_get(rotated, "SetRotatedType")
    if callable(set_rotated_type):
        set_rotated_type(True, 0)
    if not rotated.Update():
        if rotated_type == 29:
            raise RuntimeError("Cut Rotated Update returned False")
        raise RuntimeError("Rotated Update returned False")
    steps_report.append(
        {
            "step": "cut_rotation" if rotated_type == 29 else "base_rotation",
            "ok": True,
            "api": "api7_rotateds_add",
            "rotated_type": rotated_type,
            "angle_degrees": params.get("angle_degrees") or 360,
        }
    )
    return {
        "sketch": sketch,
        "rotated": rotated,
        "axis": axis_line,
        "axis_end": axis_end,
    }


def _build_external_conical_step_feature(part, model_container, params, preview, steps_report, coordinate_system=None):
    return _build_stepped_shaft_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        coordinate_system=coordinate_system,
    )


def _build_internal_conical_step_source_feature(part, model_container, params, preview, steps_report):
    source_scenario = str(params.get("source_scenario") or "").strip().lower()
    source_preview = params.get("source_preview") or {}
    source_params = dict((source_preview.get("params") or params.get("source_params") or {}))
    if source_scenario == "stepped_shaft":
        return _build_stepped_shaft_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "external_conical_step":
        return _build_external_conical_step_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "internal_conical_step":
        return _build_internal_conical_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    raise RuntimeError("Unsupported internal_conical_step source_scenario: %s" % (params.get("source_scenario"),))


def _build_internal_conical_step_feature(part, model_container, params, preview, steps_report, coordinate_system=None, require_source=False):
    if params.get("source_scenario"):
        _build_internal_conical_step_source_feature(part, model_container, params, preview, steps_report)
    elif require_source:
        raise RuntimeError("internal_conical_step requires source_scenario/source_params when created as a standalone part scenario")
    return _build_stepped_shaft_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        coordinate_system=coordinate_system,
        operation_kind="cut",
    )


def _build_internal_cylindrical_step_source_feature(part, model_container, params, preview, steps_report):
    source_scenario = str(params.get("source_scenario") or "").strip().lower()
    source_preview = params.get("source_preview") or {}
    source_params = dict((source_preview.get("params") or params.get("source_params") or {}))
    if source_scenario == "stepped_shaft":
        return _build_stepped_shaft_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "external_conical_step":
        return _build_external_conical_step_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "internal_conical_step":
        return _build_internal_conical_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    if source_scenario == "internal_cylindrical_step":
        return _build_internal_cylindrical_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    raise RuntimeError("Unsupported internal_cylindrical_step source_scenario: %s" % (params.get("source_scenario"),))


def _build_internal_cylindrical_step_feature(part, model_container, params, preview, steps_report, coordinate_system=None, require_source=False):
    if params.get("source_scenario"):
        _build_internal_cylindrical_step_source_feature(part, model_container, params, preview, steps_report)
    elif require_source:
        raise RuntimeError("internal_cylindrical_step requires source_scenario/source_params when created as a standalone part scenario")
    return _build_stepped_shaft_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        coordinate_system=coordinate_system,
        operation_kind="cut",
    )


def _build_face_ring_groove_source_feature(part, model_container, params, preview, steps_report):
    source_scenario = str(params.get("source_scenario") or "").strip().lower()
    source_preview = params.get("source_preview") or {}
    source_params = dict((source_preview.get("params") or params.get("source_params") or {}))
    if source_scenario == "stepped_shaft":
        return _build_stepped_shaft_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "external_conical_step":
        return _build_external_conical_step_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "internal_conical_step":
        return _build_internal_conical_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    if source_scenario == "internal_cylindrical_step":
        return _build_internal_cylindrical_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    if source_scenario == "face_ring_groove":
        return _build_face_ring_groove_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    raise RuntimeError("Unsupported face_ring_groove source_scenario: %s" % (params.get("source_scenario"),))


def _build_face_ring_groove_feature(part, model_container, params, preview, steps_report, coordinate_system=None, require_source=False):
    if params.get("source_scenario"):
        _build_face_ring_groove_source_feature(part, model_container, params, preview, steps_report)
    elif require_source:
        raise RuntimeError("face_ring_groove requires source_scenario/source_params when created as a standalone part scenario")
    return _build_stepped_shaft_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        coordinate_system=coordinate_system,
        operation_kind="cut",
    )


def _build_bolt_circle_holes_source_feature(part, model_container, params, preview, steps_report):
    source_scenario = str(params.get("source_scenario") or "").strip().lower()
    source_preview = params.get("source_preview") or {}
    source_params = dict((source_preview.get("params") or params.get("source_params") or {}))
    if source_scenario == "stepped_shaft":
        return _build_stepped_shaft_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "external_conical_step":
        return _build_external_conical_step_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "internal_conical_step":
        return _build_internal_conical_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    if source_scenario == "internal_cylindrical_step":
        return _build_internal_cylindrical_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    if source_scenario == "face_ring_groove":
        return _build_face_ring_groove_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    raise RuntimeError("Unsupported bolt_circle_holes source_scenario: %s" % (params.get("source_scenario"),))


def _build_bolt_circle_holes_feature(part, model_container, params, preview, steps_report, coordinate_system=None, require_source=False):
    if params.get("source_scenario"):
        _build_bolt_circle_holes_source_feature(part, model_container, params, preview, steps_report)
    elif require_source:
        raise RuntimeError("bolt_circle_holes requires source_scenario/source_params when created as a standalone part scenario")

    planned_variables = []
    for operation in (preview or {}).get("operations") or []:
        if operation.get("operation") == "add_variables":
            planned_variables = list(operation.get("variables") or [])
            break
    if planned_variables:
        steps_report.append(_apply_part_variables(part, planned_variables))

    placement = params.get("placement") or {}
    placement_origin = placement.get("effective_origin") or placement.get("origin") or [0.0, 0.0]
    center_origin = [
        float(safe_get(coordinate_system, "X", placement_origin[0]) if coordinate_system is not None else placement_origin[0]),
        float(safe_get(coordinate_system, "Y", placement_origin[1]) if coordinate_system is not None else placement_origin[1]),
        float(safe_get(coordinate_system, "Z", 0.0) if coordinate_system is not None else 0.0),
    ]
    pattern_radius = float(params.get("bolt_circle_diameter") or 0.0) / 2.0
    start_angle = math.radians(float(params.get("start_angle_degrees") or 0.0))
    first_hole_offset_expressions = list(params.get("first_hole_offset_expressions") or [None, None, None])
    first_hole_center = [
        center_origin[0],
        center_origin[1] + pattern_radius * math.cos(start_angle),
        center_origin[2] + pattern_radius * math.sin(start_angle),
    ]

    center_point = safe_get(coordinate_system, "AssociationObject") if coordinate_system is not None else None
    created_center_point = False
    if center_point is None:
        center_point = _create_point3d(
            model_container,
            "%s_CENTER" % (params.get("name") or "BOLT_CIRCLE"),
            center_origin,
        )
        created_center_point = True
    axis_tip_point = _create_point3d_displace(
        model_container,
        "%s_AXIS_P2" % (params.get("name") or "BOLT_CIRCLE"),
        center_point,
        [1.0, 0.0, 0.0],
    )
    first_hole_point = _create_point3d_displace(
        model_container,
        "%s_HOLE_CENTER" % (params.get("name") or "BOLT_CIRCLE"),
        center_point,
        [0.0, pattern_radius * math.cos(start_angle), pattern_radius * math.sin(start_angle)],
        offset_expressions=first_hole_offset_expressions,
    )
    hole_lcs = _create_local_coordinate_system_on_point(
        part,
        "%s_HOLE_LCS" % (params.get("name") or "BOLT_CIRCLE"),
        first_hole_point,
    )
    pattern_axis = _create_axis3d_by_2_points(
        part,
        "%s_AXIS" % (params.get("name") or "BOLT_CIRCLE"),
        center_point,
        axis_tip_point,
    )

    hole_preview = (preview or {}).get("base_hole_preview") or {}
    hole_params = dict(hole_preview.get("params") or {})
    if not hole_preview or not hole_params:
        raise RuntimeError("bolt_circle_holes preview must contain base_hole_preview")
    base_hole = _build_internal_cylindrical_step_feature(
        part,
        model_container,
        hole_params,
        hole_preview,
        steps_report,
        coordinate_system=hole_lcs,
        require_source=False,
    )
    pattern = _create_circular_feature_pattern(
        model_container,
        "%s_PATTERN" % (params.get("name") or "BOLT_CIRCLE"),
        base_hole["rotated"],
        pattern_axis,
        int(params.get("count") or 0),
        360.0 / float(params.get("count") or 1),
        clockwise=bool(params.get("clockwise")),
        count_expression=params.get("pattern_count_expression"),
        angle_step_expression=params.get("pattern_step_expression"),
    )
    steps_report.append(
        {
            "step": "circular_pattern",
            "ok": True,
            "api": "api7_feature_patterns_add",
            "count": int(params.get("count") or 0),
            "angle_step_degrees": 360.0 / float(params.get("count") or 1),
            "clockwise": bool(params.get("clockwise")),
            "center_origin": center_origin,
            "first_hole_center": first_hole_center,
        }
    )
    if bool(params.get("auxiliary_geometry_hidden", True)):
        auxiliary_objects = []
        if created_center_point:
            auxiliary_objects.append(("pattern_center_point", center_point))
        auxiliary_objects.extend(
            [
                ("pattern_axis_tip_point", axis_tip_point),
                ("first_hole_center_point", first_hole_point),
                ("first_hole_lcs", hole_lcs),
                ("pattern_axis", pattern_axis),
            ]
        )
        visibility_report = _hide_auxiliary_model_objects(auxiliary_objects, True)
        step_report = {
            "step": "hide_bolt_circle_auxiliary_geometry",
            "scenario": "bolt_circle_holes",
        }
        step_report.update(visibility_report)
        steps_report.append(step_report)
    return {
        "base_hole": base_hole,
        "pattern": pattern,
        "pattern_axis": pattern_axis,
        "first_hole_center": first_hole_point,
        "first_hole_lcs": hole_lcs,
    }


def _extract_flat_step_preview_data(preview, params):
    helper_circle = None
    profile_lines = []
    profile_arcs = []
    planned_variables = []
    planned_constraints = []
    planned_dimensions = []
    for operation in (preview or {}).get("operations") or []:
        if operation.get("operation") == "draw_flat_profile":
            helper_circle = dict(operation.get("helper_circle") or {})
            profile_lines = list(operation.get("profile_lines") or [])
            profile_arcs = list(operation.get("profile_arcs") or [])
        elif operation.get("operation") == "add_variables":
            planned_variables = list(operation.get("variables") or [])
        elif operation.get("operation") == "apply_constraints":
            planned_constraints = list(operation.get("constraints") or [])
        elif operation.get("operation") == "add_dimensions":
            planned_dimensions = list(operation.get("dimensions") or [])
    if not helper_circle or not profile_lines or not profile_arcs:
        raise RuntimeError("Invalid flat_step profile")
    axis_start = [
        float(((preview or {}).get("interface") or {}).get("anchors", {}).get("axis_start", [0.0, 0.0])[0]),
        float(((preview or {}).get("interface") or {}).get("anchors", {}).get("axis_start", [0.0, 0.0])[1]),
    ]
    axis_end = [
        float(((preview or {}).get("interface") or {}).get("anchors", {}).get("axis_end", [float(axis_start[0]) + float(params.get("length") or 0.0), float(axis_start[1])])[0]),
        float(((preview or {}).get("interface") or {}).get("anchors", {}).get("axis_end", [float(axis_start[0]) + float(params.get("length") or 0.0), float(axis_start[1])])[1]),
    ]
    return {
        "helper_circle": helper_circle,
        "profile_lines": profile_lines,
        "profile_arcs": profile_arcs,
        "axis_start": axis_start,
        "axis_end": axis_end,
        "planned_variables": planned_variables,
        "planned_constraints": planned_constraints,
        "planned_dimensions": planned_dimensions,
    }


def _build_flat_step_feature(part, model_container, params, preview, steps_report, coordinate_system=None, operation_kind="boss"):
    extracted = _extract_flat_step_preview_data(preview, params)
    helper_circle = extracted["helper_circle"]
    profile_lines = extracted["profile_lines"]
    profile_arcs = extracted["profile_arcs"]
    planned_variables = extracted["planned_variables"]
    planned_constraints = extracted["planned_constraints"]
    planned_dimensions = extracted["planned_dimensions"]

    if planned_variables:
        steps_report.append(_apply_part_variables(part, planned_variables))

    plane_map = {"XOY": 1, "XOZ": 2, "YOZ": 3}
    plane_id = plane_map.get(str(params.get("plane") or "YOZ").upper(), 3)
    default_object = safe_get(part, "DefaultObject")
    if not callable(default_object):
        default_object = safe_get(part, "GetDefaultObject")
    if not callable(default_object):
        raise RuntimeError("Part does not expose DefaultObject/GetDefaultObject")
    plane = default_object(plane_id)
    if plane is None:
        raise RuntimeError("Failed to get default sketch plane")

    sketchs = safe_get(model_container, "Sketchs")
    if sketchs is None:
        get_sketchs = safe_get(model_container, "GetSketchs")
        if callable(get_sketchs):
            sketchs = get_sketchs()
    if sketchs is None or not callable(safe_get(sketchs, "Add")):
        raise RuntimeError("Part does not expose Sketchs.Add")
    sketch = sketchs.Add()
    if sketch is None:
        raise RuntimeError("Sketchs.Add returned None")
    sketch.Plane = plane
    if coordinate_system is not None:
        sketch.CoordinateSystem = coordinate_system
    if params.get("name"):
        try:
            sketch.Name = "%s profile" % params.get("name")
        except Exception:
            pass
    if not sketch.Update():
        raise RuntimeError("Sketch Update returned False")
    steps_report.append({"step": "create_sketch", "ok": True, "api": "api7_sketchs_add", "plane": params.get("plane") or "YOZ"})

    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    line_count = 0
    line_style_report = []
    sketch_entities = {}
    parameterization_report = None
    try:
        views_manager = safe_get(sketch_doc, "ViewsAndLayersManager")
        if views_manager is None:
            get_views_manager = safe_get(sketch_doc, "GetViewsAndLayersManager")
            if callable(get_views_manager):
                views_manager = get_views_manager()
        views = safe_get(views_manager, "Views") if views_manager is not None else None
        if views is None:
            raise RuntimeError("Sketch document does not expose ViewsAndLayersManager.Views")
        view = None
        for accessor_name, accessor_arg in (("View", 0), ("Item", 0), ("View", 1), ("Item", 1)):
            accessor = safe_get(views, accessor_name)
            if not callable(accessor):
                continue
            try:
                view = accessor(accessor_arg)
                if view is not None:
                    break
            except Exception:
                continue
        if view is None:
            raise RuntimeError("Failed to get sketch system view")

        drawing_container = cast_drawing_container(view)
        line_segments = safe_get(drawing_container, "LineSegments")
        if line_segments is None:
            get_line_segments = safe_get(drawing_container, "GetLineSegments")
            if callable(get_line_segments):
                line_segments = get_line_segments()
        circles = safe_get(drawing_container, "Circles")
        if circles is None:
            get_circles = safe_get(drawing_container, "GetCircles")
            if callable(get_circles):
                circles = get_circles()
        arcs = safe_get(drawing_container, "Arcs")
        if arcs is None:
            get_arcs = safe_get(drawing_container, "GetArcs")
            if callable(get_arcs):
                arcs = get_arcs()
        if line_segments is None or not callable(safe_get(line_segments, "Add")):
            raise RuntimeError("Sketch view does not expose LineSegments.Add")
        if circles is None or not callable(safe_get(circles, "Add")):
            raise RuntimeError("Sketch view does not expose Circles.Add")
        if arcs is None or not callable(safe_get(arcs, "Add")):
            raise RuntimeError("Sketch view does not expose Arcs.Add")

        def add_line(x1, y1, x2, y2, *, role, target, line_style=None):
            line = line_segments.Add()
            if line is None:
                raise RuntimeError("LineSegments.Add returned None")
            line.X1 = float(x1)
            line.Y1 = float(y1)
            line.X2 = float(x2)
            line.Y2 = float(y2)
            if line_style not in (None, ""):
                try:
                    line.Style = int(line_style)
                except Exception:
                    pass
            if not line.Update():
                raise RuntimeError("LineSegment.Update returned False for %s" % target)
            line_style_report.append(
                {
                    "target": target,
                    "role": role,
                    "style": safe_get(line, "Style"),
                }
            )
            sketch_entities[target] = _sketch_line_entry(line, x1, y1, x2, y2, role=role, target=target)
            return line

        def add_circle(xc, yc, radius, *, role, target, line_style=None):
            circle = circles.Add()
            if circle is None:
                raise RuntimeError("Circles.Add returned None")
            circle.Xc = float(xc)
            circle.Yc = float(yc)
            circle.Radius = float(radius)
            if line_style not in (None, ""):
                try:
                    circle.Style = int(line_style)
                except Exception:
                    pass
            if not circle.Update():
                raise RuntimeError("Circle.Update returned False for %s" % target)
            line_style_report.append(
                {
                    "target": target,
                    "role": role,
                    "style": safe_get(circle, "Style"),
                }
            )
            sketch_entities[target] = _sketch_circle_entry(circle, xc, yc, radius, role=role, target=target)
            return circle

        def add_arc(xc, yc, radius, x1, y1, x2, y2, *, direction, role, target, line_style=None):
            arc = arcs.Add()
            if arc is None:
                raise RuntimeError("Arcs.Add returned None")
            arc.Xc = float(xc)
            arc.Yc = float(yc)
            arc.Radius = float(radius)
            arc.X1 = float(x1)
            arc.Y1 = float(y1)
            arc.X2 = float(x2)
            arc.Y2 = float(y2)
            try:
                arc.Direction = bool(direction)
            except Exception:
                set_direction = safe_get(arc, "SetDirection")
                if callable(set_direction):
                    set_direction(bool(direction))
            if line_style not in (None, ""):
                try:
                    arc.Style = int(line_style)
                except Exception:
                    pass
            if not arc.Update():
                raise RuntimeError("Arc.Update returned False for %s" % target)
            line_style_report.append(
                {
                    "target": target,
                    "role": role,
                    "style": safe_get(arc, "Style"),
                }
            )
            sketch_entities[target] = _sketch_arc_entry(
                arc,
                xc,
                yc,
                radius,
                x1,
                y1,
                x2,
                y2,
                direction=direction,
                role=role,
                target=target,
            )
            return arc

        add_circle(
            helper_circle["xc"],
            helper_circle["yc"],
            helper_circle["radius"],
            role="circle",
            target="helper_circle",
            line_style=int((preview.get("operations") or [])[3].get("construction_line_style", 6)) if len((preview.get("operations") or [])) > 3 else 6,
        )
        line_count += 1
        for entry in profile_lines:
            add_line(
                entry["x1"],
                entry["y1"],
                entry["x2"],
                entry["y2"],
                role="profile",
                target=str(entry["target"]),
                line_style=int((preview.get("operations") or [])[3].get("line_style", 1)) if len((preview.get("operations") or [])) > 3 else 1,
            )
            line_count += 1
        for entry in profile_arcs:
            add_arc(
                entry["xc"],
                entry["yc"],
                entry["radius"],
                entry["x1"],
                entry["y1"],
                entry["x2"],
                entry["y2"],
                direction=bool(entry.get("direction", True)),
                role="profile",
                target=str(entry["target"]),
                line_style=int((preview.get("operations") or [])[3].get("line_style", 1)) if len((preview.get("operations") or [])) > 3 else 1,
            )
            line_count += 1

        sketch_entities["origin"] = {
            "object": None,
            "role": "point",
            "target": "origin",
            "x": float(helper_circle["xc"]),
            "y": float(helper_circle["yc"]),
        }
        parameterization_report = _apply_sketch_parameterization(
            view,
            sketch_entities,
            planned_constraints,
            planned_dimensions,
            params.get("sketch") or {},
            steps_report,
            float(params.get("length") or 0.0),
        )
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    steps_report.append(
        {
            "step": "draw_flat_profile",
            "ok": True,
            "api": "api7_flat_profile",
            "line_count": line_count,
            "coordinate_system": safe_get(coordinate_system, "Name") if coordinate_system is not None else None,
            "line_styles": line_style_report,
        }
    )
    if parameterization_report is not None:
        parameterization_report["sketch_state"] = _describe_constraints_state(safe_get(sketch, "ConstraintsState"))
    steps_report.append(parameterization_report or {"step": "sketch_parameterization", "ok": False, "error": "not_run"})

    extrusions = safe_get(model_container, "Extrusions")
    if extrusions is None:
        get_extrusions = safe_get(model_container, "GetExtrusions")
        if callable(get_extrusions):
            extrusions = get_extrusions()
    if extrusions is None or not callable(safe_get(extrusions, "Add")):
        raise RuntimeError("Part does not expose Extrusions.Add")

    extrusion_type = 25 if str(operation_kind or "boss").strip().lower() != "cut" else 26
    extrusion = extrusions.Add(extrusion_type)
    if extrusion is None:
        if extrusion_type == 26:
            raise RuntimeError("Extrusions.Add(o3d_cutExtrusion) returned None")
        raise RuntimeError("Extrusions.Add(o3d_bossExtrusion) returned None")

    assigned_profile = False
    for setter_name in ("SetSketch", "SetProfile"):
        setter = safe_get(extrusion, setter_name)
        if callable(setter):
            setter(sketch)
            assigned_profile = True
            break
    if not assigned_profile:
        for attr_name in ("Sketch", "Profile"):
            try:
                setattr(extrusion, attr_name, sketch)
                assigned_profile = True
                break
            except Exception:
                continue
    if not assigned_profile:
        raise RuntimeError("Extrusion does not expose Sketch/Profile binding")

    direction_normal = str(params.get("axial_direction") or "forward").strip().lower() != "backward"
    length_variable_name = None
    for variable in planned_variables:
        if str(variable.get("kind") or "").strip().lower() == "driving_length":
            length_variable_name = str(variable.get("name") or "").strip() or None
            if length_variable_name:
                break
    set_direction = safe_get(extrusion, "SetDirection")
    if callable(set_direction):
        set_direction(0 if direction_normal else 1)
    else:
        try:
            extrusion.Direction = 0 if direction_normal else 1
        except Exception:
            pass
    set_extrusion_type = safe_get(extrusion, "SetExtrusionType")
    if callable(set_extrusion_type):
        set_extrusion_type(direction_normal, 0)
    set_depth = safe_get(extrusion, "SetDepth")
    if not callable(set_depth):
        raise RuntimeError("Extrusion does not expose SetDepth")
    depth_binding = "value"
    depth_value = float(params.get("length") or 0.0)
    if length_variable_name:
        try:
            set_depth(direction_normal, str(length_variable_name))
            depth_binding = "expression"
            depth_value = str(length_variable_name)
        except Exception:
            set_depth(direction_normal, float(params.get("length") or 0.0))
    else:
        set_depth(direction_normal, float(params.get("length") or 0.0))
    if not extrusion.Update():
        if length_variable_name and depth_binding == "expression":
            set_depth(direction_normal, float(params.get("length") or 0.0))
            depth_binding = "value_fallback"
            depth_value = float(params.get("length") or 0.0)
        if not extrusion.Update():
            if extrusion_type == 26:
                raise RuntimeError("Cut Extrusion Update returned False")
            raise RuntimeError("Boss Extrusion Update returned False")
    steps_report.append(
        {
            "step": "cut_extrusion" if extrusion_type == 26 else "boss_extrusion",
            "ok": True,
            "api": "api7_extrusions_add",
            "extrusion_type": extrusion_type,
            "length": float(params.get("length") or 0.0),
            "length_binding": depth_binding,
            "length_binding_value": depth_value,
            "length_variable": length_variable_name,
            "axial_direction": params.get("axial_direction") or "forward",
        }
    )
    return {
        "sketch": sketch,
        "extrusion": extrusion,
        "sketch_parameterization": parameterization_report,
    }


def _build_external_flat_step_feature(part, model_container, params, preview, steps_report, coordinate_system=None):
    return _build_flat_step_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        coordinate_system=coordinate_system,
        operation_kind="boss",
    )


def _build_internal_flat_step_source_feature(part, model_container, params, preview, steps_report):
    source_scenario = str(params.get("source_scenario") or "").strip().lower()
    source_preview = params.get("source_preview") or {}
    source_params = dict((source_preview.get("params") or params.get("source_params") or {}))
    if source_scenario == "stepped_shaft":
        return _build_stepped_shaft_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "external_conical_step":
        return _build_external_conical_step_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "external_polygonal_step":
        return _build_external_polygonal_step_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "external_flat_step":
        return _build_external_flat_step_feature(part, model_container, source_params, source_preview, steps_report)
    raise RuntimeError("Unsupported internal_flat_step source_scenario: %s" % (params.get("source_scenario"),))


def _build_internal_flat_step_feature(part, model_container, params, preview, steps_report, coordinate_system=None, require_source=False):
    if params.get("source_scenario"):
        _build_internal_flat_step_source_feature(part, model_container, params, preview, steps_report)
    elif require_source:
        raise RuntimeError("internal_flat_step requires source_scenario/source_params when created as a standalone part scenario")
    return _build_flat_step_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        coordinate_system=coordinate_system,
        operation_kind="cut",
    )


def _extract_polygonal_step_preview_data(preview, params):
    anchors = ((preview or {}).get("interface") or {}).get("anchors") or {}
    vertices = anchors.get("profile_vertices") or []
    if len(vertices) < 3:
        for operation in (preview or {}).get("operations") or []:
            if operation.get("operation") == "draw_regular_polygon":
                vertices = operation.get("vertices") or []
                if len(vertices) >= 3:
                    break
    if len(vertices) < 3:
        raise RuntimeError("Invalid polygonal_step profile")
    axis_start = anchors.get("axis_start") or [0.0, 0.0]
    axis_end = anchors.get("axis_end") or [float(axis_start[0]) + float(params.get("length") or 0.0), float(axis_start[1])]
    planned_variables = []
    planned_constraints = []
    planned_dimensions = []
    for operation in (preview or {}).get("operations") or []:
        if operation.get("operation") == "add_variables":
            planned_variables = list(operation.get("variables") or [])
        elif operation.get("operation") == "apply_constraints":
            planned_constraints = list(operation.get("constraints") or [])
        elif operation.get("operation") == "add_dimensions":
            planned_dimensions = list(operation.get("dimensions") or [])
    return {
        "vertices": [[float(point[0]), float(point[1])] for point in vertices],
        "axis_start": [float(axis_start[0]), float(axis_start[1])],
        "axis_end": [float(axis_end[0]), float(axis_end[1])],
        "planned_variables": planned_variables,
        "planned_constraints": planned_constraints,
        "planned_dimensions": planned_dimensions,
    }


def _build_polygonal_step_feature(part, model_container, params, preview, steps_report, coordinate_system=None, operation_kind="boss"):
    extracted = _extract_polygonal_step_preview_data(preview, params)
    vertices = extracted["vertices"]
    planned_variables = extracted["planned_variables"]
    planned_constraints = extracted["planned_constraints"]
    planned_dimensions = extracted["planned_dimensions"]

    if planned_variables:
        steps_report.append(_apply_part_variables(part, planned_variables))

    plane_map = {"XOY": 1, "XOZ": 2, "YOZ": 3}
    plane_id = plane_map.get(str(params.get("plane") or "YOZ").upper(), 3)
    default_object = safe_get(part, "DefaultObject")
    if not callable(default_object):
        default_object = safe_get(part, "GetDefaultObject")
    if not callable(default_object):
        raise RuntimeError("Part does not expose DefaultObject/GetDefaultObject")
    plane = default_object(plane_id)
    if plane is None:
        raise RuntimeError("Failed to get default sketch plane")

    sketchs = safe_get(model_container, "Sketchs")
    if sketchs is None:
        get_sketchs = safe_get(model_container, "GetSketchs")
        if callable(get_sketchs):
            sketchs = get_sketchs()
    if sketchs is None or not callable(safe_get(sketchs, "Add")):
        raise RuntimeError("Part does not expose Sketchs.Add")
    sketch = sketchs.Add()
    if sketch is None:
        raise RuntimeError("Sketchs.Add returned None")
    sketch.Plane = plane
    if coordinate_system is not None:
        sketch.CoordinateSystem = coordinate_system
    if params.get("name"):
        try:
            sketch.Name = "%s profile" % params.get("name")
        except Exception:
            pass
    if not sketch.Update():
        raise RuntimeError("Sketch Update returned False")
    steps_report.append({"step": "create_sketch", "ok": True, "api": "api7_sketchs_add", "plane": params.get("plane") or "YOZ"})

    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    line_count = 0
    line_style_report = []
    sketch_entities = {}
    parameterization_report = None
    try:
        views_manager = safe_get(sketch_doc, "ViewsAndLayersManager")
        if views_manager is None:
            get_views_manager = safe_get(sketch_doc, "GetViewsAndLayersManager")
            if callable(get_views_manager):
                views_manager = get_views_manager()
        views = safe_get(views_manager, "Views") if views_manager is not None else None
        if views is None:
            raise RuntimeError("Sketch document does not expose ViewsAndLayersManager.Views")
        view = None
        for accessor_name, accessor_arg in (("View", 0), ("Item", 0), ("View", 1), ("Item", 1)):
            accessor = safe_get(views, accessor_name)
            if not callable(accessor):
                continue
            try:
                view = accessor(accessor_arg)
                if view is not None:
                    break
            except Exception:
                continue
        if view is None:
            raise RuntimeError("Failed to get sketch system view")

        drawing_container = cast_drawing_container(view)
        line_segments = safe_get(drawing_container, "LineSegments")
        if line_segments is None:
            get_line_segments = safe_get(drawing_container, "GetLineSegments")
            if callable(get_line_segments):
                line_segments = get_line_segments()
        if line_segments is None or not callable(safe_get(line_segments, "Add")):
            raise RuntimeError("Sketch view does not expose LineSegments.Add")
        circles = safe_get(drawing_container, "Circles")
        if circles is None:
            get_circles = safe_get(drawing_container, "GetCircles")
            if callable(get_circles):
                circles = get_circles()
        if circles is None or not callable(safe_get(circles, "Add")):
            raise RuntimeError("Sketch view does not expose Circles.Add")

        profile_line_style = int(((params.get("sketch") or {}).get("profile_line_style", 1)))
        construction_line_style = 6

        def add_line(x1, y1, x2, y2, *, role, target, line_style):
            line = line_segments.Add()
            if line is None:
                raise RuntimeError("LineSegments.Add returned None")
            line.X1 = float(x1)
            line.Y1 = float(y1)
            line.X2 = float(x2)
            line.Y2 = float(y2)
            requested_style = line_style
            style_setter = "Style"
            try:
                line.Style = requested_style
            except Exception:
                set_style = safe_get(line, "SetStyle")
                if callable(set_style):
                    set_style(requested_style)
                    style_setter = "SetStyle"
                else:
                    raise
            if not line.Update():
                raise RuntimeError("LineSegment Update returned False")
            actual_style = safe_get(line, "Style")
            if actual_style is None:
                get_style = safe_get(line, "GetStyle")
                if callable(get_style):
                    try:
                        actual_style = get_style()
                    except Exception:
                        actual_style = None
            line_style_report.append(
                {
                    "role": role,
                    "target": target,
                    "requested_style": requested_style,
                    "actual_style": actual_style,
                    "setter": style_setter,
                    "ok": actual_style is None or int(actual_style) == requested_style,
                }
            )
            sketch_entities[target] = _sketch_line_entry(line, x1, y1, x2, y2, role=role, target=target)
            return line

        def add_circle(xc, yc, radius, *, role, target, line_style):
            circle = circles.Add()
            if circle is None:
                raise RuntimeError("Circles.Add returned None")
            circle.Xc = float(xc)
            circle.Yc = float(yc)
            circle.Radius = float(radius)
            requested_style = line_style
            style_setter = "Style"
            try:
                circle.Style = requested_style
            except Exception:
                set_style = safe_get(circle, "SetStyle")
                if callable(set_style):
                    set_style(requested_style)
                    style_setter = "SetStyle"
                else:
                    raise
            if not circle.Update():
                raise RuntimeError("Circle Update returned False")
            actual_style = safe_get(circle, "Style")
            if actual_style is None:
                get_style = safe_get(circle, "GetStyle")
                if callable(get_style):
                    try:
                        actual_style = get_style()
                    except Exception:
                        actual_style = None
            line_style_report.append(
                {
                    "role": role,
                    "target": target,
                    "requested_style": requested_style,
                    "actual_style": actual_style,
                    "setter": style_setter,
                    "ok": actual_style is None or int(actual_style) == requested_style,
                }
            )
            sketch_entities[target] = _sketch_circle_entry(circle, xc, yc, radius, role=role, target=target)
            return circle

        center_x = float(extracted["axis_start"][0])
        center_y = float(extracted["axis_start"][1])
        polygon_radius = float(params.get("polygon_radius") or 0.0)
        helper_circle_radius = float(params.get("diameter") or 0.0) / 2.0
        diameter_mode = str(params.get("diameter_mode") or "inscribed_circle").strip().lower()

        add_circle(
            center_x,
            center_y,
            helper_circle_radius,
            role="construction",
            target="helper_circle",
            line_style=construction_line_style,
        )
        if diameter_mode == "inscribed_circle":
            add_circle(
                center_x,
                center_y,
                polygon_radius,
                role="construction",
                target="vertex_circle",
                line_style=construction_line_style,
            )
        add_line(
            center_x,
            center_y,
            center_x,
            center_y + helper_circle_radius,
            role="construction",
            target="circle_radius_line",
            line_style=construction_line_style,
        )
        line_count += 3 if diameter_mode == "inscribed_circle" else 2

        for index in range(len(vertices)):
            x1, y1 = vertices[index]
            x2, y2 = vertices[(index + 1) % len(vertices)]
            add_line(
                x1,
                y1,
                x2,
                y2,
                role="profile",
                target="profile_line_%s" % (index + 1),
                line_style=profile_line_style,
            )
            line_count += 1
        origin_entity = sketch_entities.get("circle_radius_line")
        if origin_entity is not None:
            sketch_entities["origin"] = {
                "object": origin_entity["object"],
                "role": "point",
                "target": "origin",
                "x": center_x,
                "y": center_y,
            }
        else:
            sketch_entities["origin"] = {
                "object": None,
                "role": "point",
                "target": "origin",
                "x": center_x,
                "y": center_y,
            }
        parameterization_report = _apply_sketch_parameterization(
            view,
            sketch_entities,
            planned_constraints,
            planned_dimensions,
            params.get("sketch") or {},
            steps_report,
            float(params.get("length") or 0.0),
        )
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    steps_report.append(
        {
            "step": "draw_profile",
            "ok": True,
            "api": "api7_line_segments",
            "profile_point_count": len(vertices),
            "line_count": line_count,
            "coordinate_system": safe_get(coordinate_system, "Name") if coordinate_system is not None else None,
            "line_styles": line_style_report,
        }
    )
    if parameterization_report is not None:
        parameterization_report["sketch_state"] = _describe_constraints_state(safe_get(sketch, "ConstraintsState"))
    steps_report.append(parameterization_report or {"step": "sketch_parameterization", "ok": False, "error": "not_run"})

    extrusions = safe_get(model_container, "Extrusions")
    if extrusions is None:
        get_extrusions = safe_get(model_container, "GetExtrusions")
        if callable(get_extrusions):
            extrusions = get_extrusions()
    if extrusions is None or not callable(safe_get(extrusions, "Add")):
        raise RuntimeError("Part does not expose Extrusions.Add")

    extrusion_type = 25 if str(operation_kind or "boss").strip().lower() != "cut" else 26
    extrusion = extrusions.Add(extrusion_type)
    if extrusion is None:
        if extrusion_type == 26:
            raise RuntimeError("Extrusions.Add(o3d_cutExtrusion) returned None")
        raise RuntimeError("Extrusions.Add(o3d_bossExtrusion) returned None")

    assigned_profile = False
    for setter_name in ("SetSketch", "SetProfile"):
        setter = safe_get(extrusion, setter_name)
        if callable(setter):
            setter(sketch)
            assigned_profile = True
            break
    if not assigned_profile:
        for attr_name in ("Sketch", "Profile"):
            try:
                setattr(extrusion, attr_name, sketch)
                assigned_profile = True
                break
            except Exception:
                continue
    if not assigned_profile:
        raise RuntimeError("Extrusion does not expose Sketch/Profile binding")

    direction_normal = str(params.get("axial_direction") or "forward").strip().lower() != "backward"
    length_variable_name = None
    for variable in planned_variables:
        if str(variable.get("kind") or "").strip().lower() == "driving_length":
            length_variable_name = str(variable.get("name") or "").strip() or None
            if length_variable_name:
                break
    set_direction = safe_get(extrusion, "SetDirection")
    if callable(set_direction):
        set_direction(0 if direction_normal else 1)
    else:
        try:
            extrusion.Direction = 0 if direction_normal else 1
        except Exception:
            pass
    set_extrusion_type = safe_get(extrusion, "SetExtrusionType")
    if callable(set_extrusion_type):
        set_extrusion_type(direction_normal, 0)
    set_depth = safe_get(extrusion, "SetDepth")
    if callable(set_depth):
        depth_binding = "value"
        depth_value = float(params.get("length") or 0.0)
        if length_variable_name:
            try:
                set_depth(direction_normal, str(length_variable_name))
                depth_binding = "expression"
                depth_value = str(length_variable_name)
            except Exception:
                set_depth(direction_normal, float(params.get("length") or 0.0))
        else:
            set_depth(direction_normal, float(params.get("length") or 0.0))
    else:
        raise RuntimeError("Extrusion does not expose SetDepth")
    if not extrusion.Update():
        if length_variable_name and depth_binding == "expression":
            set_depth(direction_normal, float(params.get("length") or 0.0))
            depth_binding = "value_fallback"
            depth_value = float(params.get("length") or 0.0)
        if extrusion.Update():
            pass
        else:
            if extrusion_type == 26:
                raise RuntimeError("Cut Extrusion Update returned False")
            raise RuntimeError("Boss Extrusion Update returned False")
    steps_report.append(
        {
            "step": "cut_extrusion" if extrusion_type == 26 else "boss_extrusion",
            "ok": True,
            "api": "api7_extrusions_add",
            "extrusion_type": extrusion_type,
            "length": float(params.get("length") or 0.0),
            "length_binding": depth_binding,
            "length_binding_value": depth_value,
            "length_variable": length_variable_name,
            "axial_direction": params.get("axial_direction") or "forward",
        }
    )
    return {
        "sketch": sketch,
        "extrusion": extrusion,
        "sketch_parameterization": parameterization_report,
    }


def _build_external_polygonal_step_feature(part, model_container, params, preview, steps_report, coordinate_system=None):
    return _build_polygonal_step_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        coordinate_system=coordinate_system,
        operation_kind="boss",
    )


def _build_internal_polygonal_step_source_feature(part, model_container, params, preview, steps_report):
    source_scenario = str(params.get("source_scenario") or "").strip().lower()
    source_preview = params.get("source_preview") or {}
    source_params = dict((source_preview.get("params") or params.get("source_params") or {}))
    if source_scenario == "stepped_shaft":
        return _build_stepped_shaft_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "external_conical_step":
        return _build_external_conical_step_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "external_polygonal_step":
        return _build_external_polygonal_step_feature(part, model_container, source_params, source_preview, steps_report)
    raise RuntimeError("Unsupported internal_polygonal_step source_scenario: %s" % (params.get("source_scenario"),))


def _build_internal_polygonal_step_feature(part, model_container, params, preview, steps_report, coordinate_system=None, require_source=False):
    if params.get("source_scenario"):
        _build_internal_polygonal_step_source_feature(part, model_container, params, preview, steps_report)
    elif require_source:
        raise RuntimeError("internal_polygonal_step requires source_scenario/source_params when created as a standalone part scenario")
    return _build_polygonal_step_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        coordinate_system=coordinate_system,
        operation_kind="cut",
    )


def _get_source_feature_reference_object(source_scenario, feature):
    if source_scenario in ("external_polygonal_step", "internal_polygonal_step"):
        return (feature or {}).get("extrusion")
    if source_scenario in ("external_flat_step", "internal_flat_step"):
        return (feature or {}).get("extrusion")
    return (feature or {}).get("rotated")


def _build_revolved_source_feature(part, model_container, source_scenario, source_params, source_preview, steps_report):
    if source_scenario == "stepped_shaft":
        return _build_stepped_shaft_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "external_conical_step":
        return _build_external_conical_step_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "internal_conical_step":
        return _build_internal_conical_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    if source_scenario == "internal_cylindrical_step":
        return _build_internal_cylindrical_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    if source_scenario == "external_polygonal_step":
        return _build_external_polygonal_step_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "internal_polygonal_step":
        return _build_internal_polygonal_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    if source_scenario == "external_flat_step":
        return _build_external_flat_step_feature(part, model_container, source_params, source_preview, steps_report)
    if source_scenario == "internal_flat_step":
        return _build_internal_flat_step_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    if source_scenario == "face_ring_groove":
        return _build_face_ring_groove_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    if source_scenario == "bolt_circle_holes":
        return _build_bolt_circle_holes_feature(
            part,
            model_container,
            source_params,
            source_preview,
            steps_report,
            require_source=False,
        )
    raise RuntimeError("Unsupported source_scenario: %s" % source_scenario)


def _build_threaded_step_feature(part, model_container, params, preview, steps_report, *, scenario):
    source_scenario = str(params.get("source_scenario") or "").strip().lower()
    source_preview = params.get("source_preview") or {}
    source_params = dict((source_preview.get("params") or params.get("source_params") or {}))
    if not source_scenario:
        raise RuntimeError("%s requires source_scenario" % scenario)
    if not source_preview or not source_params:
        raise RuntimeError("%s requires source_preview/source_params" % scenario)

    steps_report.append(_apply_part_variables(part, params.get("profile_variables") or []))
    source_feature = _build_revolved_source_feature(
        part,
        model_container,
        source_scenario,
        source_params,
        source_preview,
        steps_report,
    )
    source_feature_object = _get_source_feature_reference_object(source_scenario, source_feature)
    base_face, base_face_report = _select_revolved_feature_face(
        source_scenario,
        source_feature_object,
        params.get("source_selector"),
        source_preview,
    )
    start_border, start_border_report = _select_revolved_feature_face(
        source_scenario,
        source_feature_object,
        params.get("start_selector"),
        source_preview,
    )
    end_border, end_border_report = _select_revolved_feature_face(
        source_scenario,
        source_feature_object,
        params.get("end_selector"),
        source_preview,
    )
    steps_report.append(
        {
            "step": "resolve_thread_reference_faces",
            "ok": True,
            "scenario": scenario,
            "source_scenario": source_scenario,
            "base_face": base_face_report,
            "start_border": start_border_report,
            "end_border": end_border_report,
        }
    )

    import win32com.client

    symbols_container = win32com.client.CastTo(part, "ISymbols3DContainer")
    thread = symbols_container.Threads.Add()
    thread_params = win32com.client.CastTo(thread, "IThreadsParameters")
    standard_file_name = str(
        params.get("thread_standard_table_name")
        or params.get("thread_standard_file_name")
        or params.get("thread_standard_display_name")
        or ""
    ).strip()
    if not standard_file_name:
        raise RuntimeError("%s requires resolved thread standard information" % scenario)
    if not bool(thread_params.Init(standard_file_name, float(params.get("diameter") or 0.0), float(params.get("pitch") or 0.0))):
        raise RuntimeError("Failed to initialize thread parameters for %s" % scenario)
    thread.BaseObject = base_face
    thread.InitialBorder = start_border
    thread.FinalBorder = end_border
    thread.AutoLenght = bool(params.get("auto_length", True))
    thread.AutoDiameter = bool(params.get("auto_diameter", False))
    thread.BaseObjectAdjustment = bool(params.get("fit_base_object", False))
    thread.BaseObjectAdjustmentOffset1 = bool(params.get("fit_base_object_offset1", False))
    thread.BaseObjectAdjustmentOffset2 = bool(params.get("fit_base_object_offset2", False))
    direction = str(params.get("direction") or params.get("thread_direction") or "").strip().lower()
    left_thread = bool(params.get("left_thread", False))
    if direction in ("left", "left_hand", "left_handed", "левая", "лев"):
        left_thread = True
    elif direction in ("right", "right_hand", "right_handed", "правая", "прав"):
        left_thread = False
    thread.LeftThread = left_thread
    if not bool(params.get("auto_length", True)):
        thread.Lenght = float(params.get("thread_length") or 0.0)
    feature_display_name = str(params.get("feature_display_name") or params.get("name") or "").strip()
    if feature_display_name:
        thread.Name = feature_display_name
    if not bool(thread.Update()):
        raise RuntimeError("Failed to create %s" % scenario)
    steps_report.append(
        {
            "step": "create_thread",
            "ok": True,
            "scenario": scenario,
            "reference": safe_get(thread, "Reference"),
            "standard": standard_file_name,
            "diameter": float(params.get("diameter") or 0.0),
            "pitch": float(params.get("pitch") or 0.0),
            "thread_length": params.get("thread_length"),
            "direction": "left" if left_thread else "right",
            "auto_length": bool(params.get("auto_length", True)),
            "auto_diameter": bool(params.get("auto_diameter", False)),
        }
    )
    return {
        "thread": thread,
        "source_feature": source_feature,
        "source_scenario": source_scenario,
        "base_face": base_face,
        "start_border": start_border,
        "end_border": end_border,
        "base_face_report": base_face_report,
        "start_border_report": start_border_report,
        "end_border_report": end_border_report,
    }


def _build_external_threaded_step_feature(part, model_container, params, preview, steps_report):
    return _build_threaded_step_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        scenario="external_threaded_step",
    )


def _build_internal_threaded_step_feature(part, model_container, params, preview, steps_report):
    return _build_threaded_step_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        scenario="internal_threaded_step",
    )


def _build_thread_profile_section_sketch(
    part,
    model_container,
    section_origin,
    profile_points,
    steps_report,
    name=None,
    section_point=None,
    axis_start=None,
    axis_end=None,
    profile_lines=None,
    profile_arcs=None,
    construction_lines=None,
    planned_constraints=None,
    planned_dimensions=None,
    sketch_options=None,
    auxiliary_objects=None,
):
    plane = _resolve_default_part_object(part, "xoy_plane")
    profile_origin_point = section_point
    if profile_origin_point is None:
        profile_origin_point = _create_point3d(
            model_container,
            "%s_ORIGIN" % (name or "THREAD_PROFILE"),
            list(section_origin or [0.0, 0.0, 0.0]),
        )
    profile_lcs = _create_local_coordinate_system_on_point(
        part,
        "%s_LCS" % (name or "THREAD_PROFILE"),
        profile_origin_point,
    )
    if auxiliary_objects is not None:
        auxiliary_objects.append(("profile_lcs", profile_lcs))
    sketchs = safe_get(model_container, "Sketchs")
    if sketchs is None:
        get_sketchs = safe_get(model_container, "GetSketchs")
        if callable(get_sketchs):
            sketchs = get_sketchs()
    if sketchs is None or not callable(safe_get(sketchs, "Add")):
        raise RuntimeError("Part does not expose Sketchs.Add")
    sketch = sketchs.Add()
    if sketch is None:
        raise RuntimeError("Sketchs.Add returned None")
    sketch.Plane = plane
    sketch.CoordinateSystem = profile_lcs
    if name:
        try:
            sketch.Name = str(name)
        except Exception:
            pass
    if auxiliary_objects is not None:
        auxiliary_objects.append(("profile_sketch", sketch))
    if not sketch.Update():
        raise RuntimeError("Sketch Update returned False")

    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None for thread profile sketch")
    line_count = 0
    line_style_report = []
    sketch_entities = {}
    parameterization_report = None
    try:
        views_manager = safe_get(sketch_doc, "ViewsAndLayersManager")
        if views_manager is None:
            get_views_manager = safe_get(sketch_doc, "GetViewsAndLayersManager")
            if callable(get_views_manager):
                views_manager = get_views_manager()
        views = safe_get(views_manager, "Views") if views_manager is not None else None
        if views is None:
            raise RuntimeError("Thread profile sketch does not expose Views")

        view = None
        for accessor_name, accessor_arg in (("View", 0), ("Item", 0), ("View", 1), ("Item", 1)):
            accessor = safe_get(views, accessor_name)
            if not callable(accessor):
                continue
            try:
                view = accessor(accessor_arg)
                if view is not None:
                    break
            except Exception:
                continue
        if view is None:
            raise RuntimeError("Failed to get thread profile sketch system view")

        drawing_container = cast_drawing_container(view)
        line_segments = safe_get(drawing_container, "LineSegments")
        if line_segments is None:
            get_line_segments = safe_get(drawing_container, "GetLineSegments")
            if callable(get_line_segments):
                line_segments = get_line_segments()
        arcs = safe_get(drawing_container, "Arcs")
        if arcs is None:
            get_arcs = safe_get(drawing_container, "GetArcs")
            if callable(get_arcs):
                arcs = get_arcs()
        if line_segments is None or not callable(safe_get(line_segments, "Add")):
            raise RuntimeError("Thread profile sketch does not expose LineSegments.Add")
        if profile_arcs and (arcs is None or not callable(safe_get(arcs, "Add"))):
            raise RuntimeError("Thread profile sketch does not expose Arcs.Add")

        sketch_options = dict(sketch_options or {})
        construction_lines = list(construction_lines or [])
        profile_lines = list(profile_lines or [])
        profile_arcs = list(profile_arcs or [])
        planned_constraints = list(planned_constraints or [])
        planned_dimensions = list(planned_dimensions or [])
        axis_start = list(axis_start or [0.0, 0.0])
        axis_end = list(axis_end or [0.0, 1.0])
        axis_line_style = int(sketch_options.get("axis_line_style", 3))
        profile_line_style = int(sketch_options.get("profile_line_style", 1))

        def add_line(x1, y1, x2, y2, style, role):
            line = line_segments.Add()
            if line is None:
                raise RuntimeError("LineSegments.Add returned None")
            line.X1 = float(x1)
            line.Y1 = float(y1)
            line.X2 = float(x2)
            line.Y2 = float(y2)
            requested_style = int(style)
            style_setter = "Style"
            try:
                line.Style = requested_style
            except Exception:
                set_style = safe_get(line, "SetStyle")
                if callable(set_style):
                    set_style(requested_style)
                    style_setter = "SetStyle"
                else:
                    raise
            if not line.Update():
                raise RuntimeError("LineSegment Update returned False")
            actual_style = safe_get(line, "Style")
            if actual_style is None:
                get_style = safe_get(line, "GetStyle")
                if callable(get_style):
                    try:
                        actual_style = get_style()
                    except Exception:
                        actual_style = None
            line_style_report.append(
                {
                    "role": role,
                    "requested_style": requested_style,
                    "actual_style": actual_style,
                    "setter": style_setter,
                    "ok": actual_style is None or int(actual_style) == requested_style,
                }
            )
            return line

        def add_arc(xc, yc, radius, x1, y1, x2, y2, direction, role, target, style):
            arc = arcs.Add()
            if arc is None:
                raise RuntimeError("Arcs.Add returned None")
            arc.Xc = float(xc)
            arc.Yc = float(yc)
            arc.Radius = float(radius)
            arc.X1 = float(x1)
            arc.Y1 = float(y1)
            arc.X2 = float(x2)
            arc.Y2 = float(y2)
            try:
                arc.Direction = bool(direction)
            except Exception:
                set_direction = safe_get(arc, "SetDirection")
                if callable(set_direction):
                    set_direction(bool(direction))
            requested_style = int(style)
            try:
                arc.Style = requested_style
            except Exception:
                set_style = safe_get(arc, "SetStyle")
                if callable(set_style):
                    set_style(requested_style)
            if not arc.Update():
                raise RuntimeError("Arc Update returned False")
            actual_style = safe_get(arc, "Style")
            line_style_report.append(
                {
                    "role": role,
                    "requested_style": requested_style,
                    "actual_style": actual_style,
                    "setter": "Style",
                    "ok": actual_style is None or int(actual_style) == requested_style,
                }
            )
            return arc

        axis_line = add_line(float(axis_start[0]), float(axis_start[1]), float(axis_end[0]), float(axis_end[1]), axis_line_style, "axis")
        sketch_entities["origin"] = _sketch_point_entry(None, float(axis_start[0]), float(axis_start[1]), role="point", target="origin")
        sketch_entities["axis"] = _sketch_line_entry(
            axis_line,
            float(axis_start[0]),
            float(axis_start[1]),
            float(axis_end[0]),
            float(axis_end[1]),
            role="axis",
            target="axis",
        )
        line_count += 1

        for construction in construction_lines:
            target = str(construction.get("target") or "").strip()
            start = construction.get("start") or []
            end = construction.get("end") or []
            if not target or not isinstance(start, list) or not isinstance(end, list) or len(start) != 2 or len(end) != 2:
                continue
            line = add_line(
                float(start[0]),
                float(start[1]),
                float(end[0]),
                float(end[1]),
                int(construction.get("line_style", 6)),
                "construction",
            )
            sketch_entities[target] = _sketch_line_entry(
                line,
                float(start[0]),
                float(start[1]),
                float(end[0]),
                float(end[1]),
                role="construction",
                target=target,
            )
            line_count += 1

        if profile_lines:
            for entry in profile_lines:
                target = str(entry.get("target") or "").strip()
                start = list(entry.get("start") or [])
                end = list(entry.get("end") or [])
                if not target or len(start) != 2 or len(end) != 2:
                    continue
                line = add_line(float(start[0]), float(start[1]), float(end[0]), float(end[1]), profile_line_style, "profile")
                sketch_entities[target] = _sketch_line_entry(
                    line,
                    float(start[0]),
                    float(start[1]),
                    float(end[0]),
                    float(end[1]),
                    role="profile",
                    target=target,
                )
                line_count += 1
        else:
            for profile_index, ((x1, y1), (x2, y2)) in enumerate(zip(profile_points, profile_points[1:]), start=1):
                target = "profile_line_%s" % profile_index
                line = add_line(float(x1), float(y1), float(x2), float(y2), profile_line_style, "profile")
                sketch_entities[target] = _sketch_line_entry(
                    line,
                    float(x1),
                    float(y1),
                    float(x2),
                    float(y2),
                    role="profile",
                    target=target,
                )
                line_count += 1

        for entry in profile_arcs:
            target = str(entry.get("target") or "").strip()
            if not target:
                continue
            arc = add_arc(
                float(entry.get("xc") or 0.0),
                float(entry.get("yc") or 0.0),
                float(entry.get("radius") or 0.0),
                float(entry.get("x1") or 0.0),
                float(entry.get("y1") or 0.0),
                float(entry.get("x2") or 0.0),
                float(entry.get("y2") or 0.0),
                bool(entry.get("direction", True)),
                "profile",
                target,
                profile_line_style,
            )
            sketch_entities[target] = _sketch_arc_entry(
                arc,
                float(entry.get("xc") or 0.0),
                float(entry.get("yc") or 0.0),
                float(entry.get("radius") or 0.0),
                float(entry.get("x1") or 0.0),
                float(entry.get("y1") or 0.0),
                float(entry.get("x2") or 0.0),
                float(entry.get("y2") or 0.0),
                direction=bool(entry.get("direction", True)),
                role="profile",
                target=target,
            )
            line_count += 1

        parameterization_report = _apply_sketch_parameterization(
            view,
            sketch_entities,
            planned_constraints,
            planned_dimensions,
            sketch_options,
            [1.0],
            0.0,
        )
    finally:
        try:
            sketch.EndEdit()
        except Exception:
            pass
    if not sketch.Update():
        raise RuntimeError("Thread profile sketch final Update returned False")
    if parameterization_report is not None:
        parameterization_report["sketch_state"] = _describe_constraints_state(safe_get(sketch, "ConstraintsState"))
        steps_report.append(parameterization_report)
    steps_report.append(
        {
            "step": "create_thread_profile_section_sketch",
            "ok": True,
            "plane": "XOY",
            "origin": [
                float(safe_get(profile_origin_point, "X", 0.0) or 0.0),
                float(safe_get(profile_origin_point, "Y", 0.0) or 0.0),
                float(safe_get(profile_origin_point, "Z", 0.0) or 0.0),
            ],
            "point_reference": safe_get(profile_origin_point, "Reference"),
            "point_count": len(profile_points),
            "profile_points": [[float(x), float(y)] for x, y in profile_points],
            "profile_line_count": len(profile_lines) if profile_lines else max(len(profile_points) - 1, 0),
            "profile_arc_count": len(profile_arcs),
            "construction_line_count": len(construction_lines),
            "planned_constraint_count": len(planned_constraints),
            "planned_dimension_count": len(planned_dimensions),
            "line_count": line_count,
            "line_styles": line_style_report,
        }
    )
    return sketch


def _sample_edge_points(edge):
    edge_points = []
    for at in (True, False):
        try:
            point = edge.GetPoint(at)
        except Exception:
            continue
        if not isinstance(point, tuple) or len(point) < 4 or not point[0]:
            continue
        edge_points.append([float(point[1]), float(point[2]), float(point[3])])
    return edge_points


def _select_face_boundary_edge(face, target_x, *, target_radius=None):
    edges = _ensure_dispatch_sequence(safe_get(face, "LimitingEdges"))
    if not edges:
        raise RuntimeError("Face does not expose LimitingEdges")

    candidates = []
    for edge in edges:
        edge_points = _sample_edge_points(edge)
        if not edge_points:
            continue
        x_values = [point[0] for point in edge_points]
        radii = [(point[1] ** 2 + point[2] ** 2) ** 0.5 for point in edge_points]
        candidates.append(
            {
                "edge": edge,
                "reference": safe_get(edge, "Reference"),
                "anchor_point": list(edge_points[0]),
                "x_min": min(x_values),
                "x_max": max(x_values),
                "x_mid": (min(x_values) + max(x_values)) / 2.0,
                "radius_min": min(radii) if radii else 0.0,
                "radius_max": max(radii) if radii else 0.0,
                "radius_mid": ((min(radii) + max(radii)) / 2.0) if radii else 0.0,
            }
        )
    if not candidates:
        raise RuntimeError("Failed to resolve face boundary edges")

    selected = min(
        candidates,
        key=lambda item: (
            abs(float(item["x_mid"]) - float(target_x)),
            abs(float(item["radius_mid"]) - float(target_radius or 0.0)),
        ),
    )
    return selected["edge"], {
        "target_x": float(target_x),
        "target_radius": float(target_radius or 0.0),
        "selected_reference": selected["reference"],
        "selected_anchor_point": selected["anchor_point"],
        "selected_x_range": [selected["x_min"], selected["x_max"]],
        "selected_radius_range": [selected["radius_min"], selected["radius_max"]],
        "candidate_count": len(candidates),
        "candidates": [
            {
                "reference": item["reference"],
                "anchor_point": item["anchor_point"],
                "x_min": item["x_min"],
                "x_max": item["x_max"],
                "radius_min": item["radius_min"],
                "radius_max": item["radius_max"],
            }
            for item in candidates
        ],
    }


def _select_edge_orientation_face(edge, base_face):
    base_reference = safe_get(base_face, "Reference")
    adjacent_face = None
    adjacent_report = []
    for index in (0, 1):
        try:
            candidate = edge.AdjacentFace(index)
        except Exception:
            continue
        if candidate is None:
            continue
        candidate_reference = safe_get(candidate, "Reference")
        adjacent_report.append(
            {
                "index": index,
                "reference": candidate_reference,
                "surface_type": safe_get(candidate, "Surface3DType"),
                "matches_base_face": candidate_reference == base_reference,
            }
        )
        if candidate_reference != base_reference and adjacent_face is None:
            adjacent_face = candidate
    if adjacent_face is None:
        raise RuntimeError("Failed to resolve edge-adjacent orientation face")
    return adjacent_face, {
        "base_face_reference": base_reference,
        "selected_reference": safe_get(adjacent_face, "Reference"),
        "selected_surface_type": safe_get(adjacent_face, "Surface3DType"),
        "adjacent_faces": adjacent_report,
    }


def _create_plane_parallel_by_point(part, name, reference_plane, point):
    import win32com.client

    auxiliary = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    if auxiliary is None:
        raise RuntimeError("Part does not expose IAuxiliaryGeomContainer")
    planes = safe_get(auxiliary, "Planes3D")
    if planes is None:
        get_planes = safe_get(auxiliary, "GetPlanes3D")
        if callable(get_planes):
            planes = get_planes()
    if planes is None:
        raise RuntimeError("Part does not expose Planes3D")
    plane = win32com.client.CastTo(planes.Add(20), "IPlane3DParallelByPoint")
    if plane is None:
        raise RuntimeError("Planes3D.Add(o3d_plane3DParallelByPoint) returned None")
    plane.Name = str(name or "")
    plane.Plane = reference_plane
    plane.Point = point
    if not plane.Update():
        raise RuntimeError("Parallel-by-point plane Update returned False")
    return plane


def _build_helical_thread_feature(part, model_container, params, preview, steps_report, *, scenario):
    source_scenario = str(params.get("source_scenario") or "").strip().lower()
    source_preview = params.get("source_preview") or {}
    source_params = dict((source_preview.get("params") or params.get("source_params") or {}))
    if not source_scenario:
        raise RuntimeError("%s requires source_scenario" % scenario)
    if not source_preview or not source_params:
        raise RuntimeError("%s requires source_preview/source_params" % scenario)

    steps_report.append(_apply_part_variables(part, params.get("profile_variables") or []))
    source_feature = _build_revolved_source_feature(
        part,
        model_container,
        source_scenario,
        source_params,
        source_preview,
        steps_report,
    )
    source_feature_object = _get_source_feature_reference_object(source_scenario, source_feature)
    base_face, base_face_report = _select_revolved_feature_face(
        source_scenario,
        source_feature_object,
        params.get("source_selector"),
        source_preview,
    )
    start_face, start_face_report = _select_revolved_feature_face(
        source_scenario,
        source_feature_object,
        params.get("start_selector"),
        source_preview,
    )
    end_face, end_face_report = _select_revolved_feature_face(
        source_scenario,
        source_feature_object,
        params.get("end_selector"),
        source_preview,
    )
    steps_report.append(
        {
            "step": "resolve_helical_thread_reference_faces",
            "ok": True,
            "scenario": scenario,
            "source_scenario": source_scenario,
            "base_face": base_face_report,
            "start_face": start_face_report,
            "end_face": end_face_report,
        }
    )

    import win32com.client

    selector_points = ((((preview or {}).get("interface") or {}).get("anchors") or {}).get("selector_points") or {})
    start_origin = params.get("start_origin") or selector_points.get("start_face") or [0.0, 0.0, 0.0]
    end_origin = params.get("end_origin") or selector_points.get("end_face") or start_origin or [0.0, 0.0, 0.0]
    nominal_diameter = float(params.get("diameter") or 0.0)
    carrier_diameter = float(params.get("carrier_diameter") or nominal_diameter or 0.0)
    carrier_shape = str(params.get("carrier_shape") or "cylindrical").strip().lower()
    end_carrier_diameter = float(
        params.get("end_thread_reference_diameter")
        or params.get("end_carrier_diameter")
        or params.get("end_diameter")
        or carrier_diameter
    )
    source_radius = carrier_diameter / 2.0
    start_edge, start_edge_report = _select_face_boundary_edge(
        base_face,
        float(start_origin[0]),
        target_radius=source_radius,
    )
    start_center_point = _create_point3d_center_on_object(
        model_container,
        str(params.get("start_center_name") or ("%s_START_CENTER" % (params.get("name") or "THREAD"))),
        start_edge,
    )
    spiral_axis = _create_axis3d_by_cone_face(
        part,
        str(params.get("axis_display_name") or ("%s_AXIS" % (params.get("name") or "THREAD"))),
        base_face,
    )
    start_center_origin = [
        float(safe_get(start_center_point, "X", start_origin[0]) or 0.0),
        float(safe_get(start_center_point, "Y", 0.0) or 0.0),
        float(safe_get(start_center_point, "Z", 0.0) or 0.0),
    ]
    steps_report.append(
        {
            "step": "resolve_helical_thread_start_reference",
            "ok": True,
            "scenario": scenario,
            "start_origin": [float(value) for value in start_origin],
            "end_origin": [float(value) for value in end_origin],
            "start_center_origin": start_center_origin,
            "start_edge": start_edge_report,
            "position_point_reference": safe_get(start_center_point, "Reference"),
            "spiral_axis_reference": safe_get(spiral_axis, "Reference"),
            "spiral_axis_name": safe_get(spiral_axis, "Name"),
        }
    )

    auxiliary_container = win32com.client.CastTo(part, "IAuxiliaryGeomContainer")
    if carrier_shape == "conical":
        spiral = win32com.client.CastTo(auxiliary_container.Spirals3D.Add(54), "IConicSpiral3D")
        spiral_label = "Conic"
    else:
        spiral = win32com.client.CastTo(auxiliary_container.Spirals3D.Add(56), "ICylindricSpiral3D")
        spiral_label = "Cylindric"
    if spiral is None:
        raise RuntimeError("Spirals3D.Add(%s spiral) returned None" % spiral_label)
    spiral_position = safe_get(spiral, "Position")
    if spiral_position is None:
        raise RuntimeError("%s spiral does not expose Position" % spiral_label)
    spiral_position.ParameterType = 1
    spiral_position.OrientationType = 0
    if not bool(spiral_position.SetAssociationObject(start_center_point)):
        raise RuntimeError("Spiral position SetAssociationObject(point) returned False")
    position_parameters = win32com.client.CastTo(
        spiral_position.LocalCSParameters,
        "ILocalCSAxesDirectionParam",
    )
    if position_parameters is None:
        raise RuntimeError("Spiral position does not expose ILocalCSAxesDirectionParam")
    position_parameters.LeadAxis = 73
    if not bool(position_parameters.SetDirectingObject(73, spiral_axis)):
        raise RuntimeError("Spiral position SetDirectingObject(OZ, axis) returned False")
    if not bool(spiral_position.Update()):
        raise RuntimeError("Spiral position Update() returned False")
    spiral.CoordinateSystem = _resolve_default_part_object(part, "origin")
    if carrier_shape == "conical":
        spiral.DiameterType1 = 1
        spiral.Diameter1 = carrier_diameter
        spiral.DiameterBaseObject1 = start_edge
        spiral.DiameterType2 = 1
        spiral.Diameter2 = end_carrier_diameter
        try:
            spiral.GeneratrixTiltAngle = float(((params.get("carrier_taper") or {}).get("half_angle_degrees")) or 0.0)
        except Exception:
            pass
    else:
        spiral.DiameterType = 1
        spiral.Diameter = carrier_diameter
        spiral.DiameterBaseObject = start_edge
    spiral.BuildingType = 1
    spiral.Step = float(params.get("pitch") or 0.0)
    spiral.Height = abs(float(params.get("spiral_length") or params.get("length") or 0.0))
    building_direction = float(end_origin[0]) >= float(start_origin[0])
    spiral.BuildingDirection = building_direction
    spiral.TurnDirection = not bool(params.get("left_thread", False))
    path_display_name = str(params.get("path_display_name") or "").strip()
    if path_display_name:
        try:
            spiral.Name = path_display_name
        except Exception:
            pass
    if not bool(spiral.Update()):
        raise RuntimeError("Failed to create helical path for %s" % scenario)
    spiral_binding_report = _bind_operation_variables(spiral, params.get("operation_variable_bindings") or [])
    spiral_binding_report["scenario"] = scenario
    spiral_binding_report["target"] = "spiral_path"
    steps_report.append(spiral_binding_report)
    if (params.get("operation_variable_bindings") or []) and not spiral_binding_report.get("ok"):
        raise RuntimeError("Failed to bind helical path operation variables for %s" % scenario)
    steps_report.append(
        {
            "step": "create_spiral_path",
            "ok": True,
            "scenario": scenario,
            "reference": safe_get(spiral, "Reference"),
            "diameter": nominal_diameter,
            "carrier_diameter": carrier_diameter,
            "carrier_shape": carrier_shape,
            "end_carrier_diameter": end_carrier_diameter,
            "pitch": float(params.get("pitch") or 0.0),
            "length": float(params.get("length") or 0.0),
            "spiral_length": float(params.get("spiral_length") or params.get("length") or 0.0),
            "height": float(safe_get(spiral, "Height", 0.0) or 0.0),
            "building_direction": bool(safe_get(spiral, "BuildingDirection", False)),
            "building_direction_reason": "end_x_ge_start_x",
            "direction": str(params.get("direction") or "right"),
            "turn_direction": bool(safe_get(spiral, "TurnDirection", False)),
            "start_origin_x": float(start_origin[0]),
            "end_origin_x": float(end_origin[0]),
            "position_association_reference": safe_get(safe_get(spiral_position, "AssociationObject"), "Reference"),
            "position_parameter_type": safe_get(spiral_position, "ParameterType"),
            "position_orientation_type": safe_get(spiral_position, "OrientationType"),
            "position_lead_axis": safe_get(position_parameters, "LeadAxis"),
            "position_orientation_reference": safe_get(spiral_axis, "Reference"),
            "diameter_base_object_reference": safe_get(safe_get(spiral, "DiameterBaseObject"), "Reference"),
            "diameter_base_object_1_reference": safe_get(safe_get(spiral, "DiameterBaseObject1"), "Reference"),
            "diameter_base_object_2_reference": safe_get(safe_get(spiral, "DiameterBaseObject2"), "Reference"),
            "diameter1": float(safe_get(spiral, "Diameter1", 0.0) or 0.0),
            "diameter2": float(safe_get(spiral, "Diameter2", 0.0) or 0.0),
            "generatrix_tilt_angle": float(safe_get(spiral, "GeneratrixTiltAngle", 0.0) or 0.0),
            "base_point": [0.0, 0.0],
        }
    )

    thread_depth = float(params.get("thread_depth") or 0.0)
    clearance = float(params.get("clearance") or 0.0)
    radial_cut_depth = thread_depth + clearance
    root_radius = float(params.get("root_radius") or 0.0)
    profile_entry_offset = float(params.get("profile_entry_offset") or 0.0)
    profile_entry_offset_expression = str(params.get("profile_entry_offset_expression") or "").strip()
    section_offset_sign = -1.0 if building_direction else 1.0
    section_offset_distance = section_offset_sign * profile_entry_offset
    section_offset_distance_expression = _signed_distance_expression(
        profile_entry_offset_expression,
        section_offset_sign,
    )
    section_origin_point = _create_point3d_displace(
        model_container,
        str(params.get("profile_origin_name") or ("%s_PROFILE_ORIGIN" % (params.get("name") or "THREAD"))),
        start_center_point,
        [0.0, 0.0, 0.0],
        guiding_object=spiral_axis,
        distance=section_offset_distance,
    )
    section_origin_binding_report = _bind_operation_variables(
        section_origin_point,
        _build_distance_point_bindings(section_offset_distance_expression, "thread_profile_origin_distance"),
    )
    section_origin_binding_report["scenario"] = scenario
    section_origin_binding_report["target"] = "thread_profile_origin_point"
    steps_report.append(section_origin_binding_report)
    if section_offset_distance_expression and not section_origin_binding_report.get("ok"):
        raise RuntimeError("Failed to bind thread profile origin point distance for %s" % scenario)
    section_origin = [
        float(safe_get(section_origin_point, "X", start_center_origin[0]) or 0.0),
        float(safe_get(section_origin_point, "Y", start_center_origin[1]) or 0.0),
        float(safe_get(section_origin_point, "Z", start_center_origin[2]) or 0.0),
    ]
    steps_report.append(
        {
            "step": "create_thread_profile_origin",
            "ok": True,
            "scenario": scenario,
            "reference": safe_get(section_origin_point, "Reference"),
            "origin": section_origin,
            "origin_anchor_reference": safe_get(start_center_point, "Reference"),
            "origin_anchor": start_center_origin,
            "entry_offset": profile_entry_offset,
            "entry_offset_expression": profile_entry_offset_expression,
            "signed_distance": section_offset_distance,
            "signed_distance_expression": section_offset_distance_expression,
            "direction": "opposite_build_direction",
            "guiding_axis_reference": safe_get(spiral_axis, "Reference"),
            "base_point_reference": safe_get(start_center_point, "Reference"),
            "radial_edge_reference": safe_get(start_edge, "Reference"),
        }
    )
    profile_points = [tuple(point) for point in (params.get("profile_points") or [])]
    profile_lines = list(params.get("profile_lines") or [])
    profile_arcs = list(params.get("profile_arcs") or [])
    if not profile_points:
        raise RuntimeError("Helical thread profile_points were not generated")
    profile_auxiliary_objects = []
    profile_sketch = _build_thread_profile_section_sketch(
        part,
        model_container,
        section_origin,
        profile_points,
        steps_report,
        name=str(params.get("profile_display_name") or ("%s profile" % params.get("name"))) if (params.get("profile_display_name") or params.get("name")) else None,
        section_point=section_origin_point,
        axis_start=params.get("profile_axis_start"),
        axis_end=params.get("profile_axis_end"),
        profile_lines=profile_lines,
        profile_arcs=profile_arcs,
        construction_lines=params.get("profile_construction_lines"),
        planned_constraints=params.get("profile_constraints"),
        planned_dimensions=params.get("profile_dimensions"),
        sketch_options=params.get("sketch"),
        auxiliary_objects=profile_auxiliary_objects,
    )

    evolutions = safe_get(model_container, "Evolutions")
    if evolutions is None:
        get_evolutions = safe_get(model_container, "GetEvolutions")
        if callable(get_evolutions):
            evolutions = get_evolutions()
    if evolutions is None or not callable(safe_get(evolutions, "Add")):
        raise RuntimeError("Part does not expose Evolutions.Add")
    evolution = evolutions.Add(47)
    if evolution is None:
        raise RuntimeError("Evolutions.Add(o3d_cutEvolution) returned None")
    evolution.Sketch = profile_sketch
    evolution.Edges = [spiral]
    try:
        evolution.OperationResult = 2
    except Exception:
        pass
    feature_display_name = str(params.get("feature_display_name") or params.get("name") or "").strip()
    if feature_display_name:
        try:
            evolution.Name = feature_display_name
        except Exception:
            pass
    if not bool(evolution.Update()):
        raise RuntimeError("Failed to create %s" % scenario)
    steps_report.append(
        {
            "step": "cut_evolution",
            "ok": True,
            "scenario": scenario,
            "reference": safe_get(evolution, "Reference"),
            "diameter": nominal_diameter,
            "carrier_diameter": carrier_diameter,
            "pitch": float(params.get("pitch") or 0.0),
            "length": float(params.get("length") or 0.0),
            "thread_depth": thread_depth,
            "clearance": clearance,
            "major_radius": float(params.get("major_radius") or 0.0),
            "root_radius_level": float(params.get("root_radius_level") or 0.0),
            "radial_cut_depth": radial_cut_depth,
            "root_radius": root_radius,
            "direction": str(params.get("direction") or "right"),
            "internal": bool(params.get("internal")),
            "model_object_type": safe_get(evolution, "ModelObjectType"),
            "operation_result": safe_get(evolution, "OperationResult"),
        }
    )
    crest_round_pass = dict(params.get("crest_round_pass") or {})
    crest_round_feature = None
    crest_round_spiral = None
    crest_round_profile_sketch = None
    crest_round_auxiliary_objects = []
    crest_round_start_center_point = None
    crest_round_section_origin_point = None
    if crest_round_pass:
        phase_shift = float(crest_round_pass.get("phase_shift") or 0.0)
        phase_shift_expression = str(crest_round_pass.get("phase_shift_expression") or "").strip()
        phase_shift_distance = phase_shift if building_direction else -phase_shift
        phase_shift_distance_expression = _signed_distance_expression(
            phase_shift_expression,
            1.0 if building_direction else -1.0,
        )
        crest_round_profile_origin_offset = float(
            crest_round_pass.get("profile_origin_offset") or profile_entry_offset
        )
        crest_round_profile_origin_offset_expression = str(
            crest_round_pass.get("profile_origin_offset_expression") or ""
        ).strip()
        crest_round_section_offset_distance = section_offset_sign * crest_round_profile_origin_offset
        crest_round_section_offset_distance_expression = _signed_distance_expression(
            crest_round_profile_origin_offset_expression,
            section_offset_sign,
        )
        crest_round_start_center_point = _create_point3d_displace(
            model_container,
            str(crest_round_pass.get("start_center_name") or ("%s_CREST_START_CENTER" % (params.get("name") or "THREAD"))),
            start_center_point,
            [0.0, 0.0, 0.0],
            guiding_object=spiral_axis,
            distance=phase_shift_distance,
        )
        crest_round_start_binding_report = _bind_operation_variables(
            crest_round_start_center_point,
            _build_distance_point_bindings(phase_shift_distance_expression, "crest_round_start_distance"),
        )
        crest_round_start_binding_report["scenario"] = scenario
        crest_round_start_binding_report["target"] = "crest_round_start_center_point"
        crest_round_start_binding_report["role"] = str(crest_round_pass.get("role") or "crest_round_pass")
        steps_report.append(crest_round_start_binding_report)
        if phase_shift_distance_expression and not crest_round_start_binding_report.get("ok"):
            raise RuntimeError("Failed to bind crest-round start point distance for %s" % scenario)
        crest_round_start_center_origin = [
            float(safe_get(crest_round_start_center_point, "X", start_center_origin[0]) or 0.0),
            float(safe_get(crest_round_start_center_point, "Y", start_center_origin[1]) or 0.0),
            float(safe_get(crest_round_start_center_point, "Z", start_center_origin[2]) or 0.0),
        ]
        steps_report.append(
            {
                "step": "create_crest_round_start_reference",
                "ok": True,
                "scenario": scenario,
                "role": str(crest_round_pass.get("role") or "crest_round_pass"),
                "reference": safe_get(crest_round_start_center_point, "Reference"),
                "origin": crest_round_start_center_origin,
                "base_reference": safe_get(start_center_point, "Reference"),
                "base_origin": start_center_origin,
                "phase_shift": phase_shift,
                "phase_shift_expression": phase_shift_expression,
                "signed_distance": phase_shift_distance,
                "signed_distance_expression": phase_shift_distance_expression,
                "direction": "along_build_direction",
                "guiding_axis_reference": safe_get(spiral_axis, "Reference"),
            }
        )

        crest_round_spiral = win32com.client.CastTo(auxiliary_container.Spirals3D.Add(56), "ICylindricSpiral3D")
        if crest_round_spiral is None:
            raise RuntimeError("Spirals3D.Add(Cylindric spiral) returned None for crest_round_pass")
        crest_round_position = safe_get(crest_round_spiral, "Position")
        if crest_round_position is None:
            raise RuntimeError("Crest-round spiral does not expose Position")
        crest_round_position.ParameterType = 1
        crest_round_position.OrientationType = 0
        if not bool(crest_round_position.SetAssociationObject(crest_round_start_center_point)):
            raise RuntimeError("Crest-round spiral position SetAssociationObject(point) returned False")
        crest_round_position_parameters = win32com.client.CastTo(
            crest_round_position.LocalCSParameters,
            "ILocalCSAxesDirectionParam",
        )
        if crest_round_position_parameters is None:
            raise RuntimeError("Crest-round spiral position does not expose ILocalCSAxesDirectionParam")
        crest_round_position_parameters.LeadAxis = 73
        if not bool(crest_round_position_parameters.SetDirectingObject(73, spiral_axis)):
            raise RuntimeError("Crest-round spiral position SetDirectingObject(OZ, axis) returned False")
        if not bool(crest_round_position.Update()):
            raise RuntimeError("Crest-round spiral position Update() returned False")
        crest_round_spiral.CoordinateSystem = _resolve_default_part_object(part, "origin")
        crest_round_spiral.DiameterType = 1
        crest_round_spiral.Diameter = carrier_diameter
        crest_round_spiral.DiameterBaseObject = start_edge
        crest_round_spiral.BuildingType = 1
        crest_round_spiral.Step = float(params.get("pitch") or 0.0)
        crest_round_spiral.Height = abs(float(params.get("spiral_length") or params.get("length") or 0.0))
        crest_round_spiral.BuildingDirection = building_direction
        crest_round_spiral.TurnDirection = not bool(params.get("left_thread", False))
        crest_round_path_display_name = str(crest_round_pass.get("path_display_name") or "").strip()
        if crest_round_path_display_name:
            try:
                crest_round_spiral.Name = crest_round_path_display_name
            except Exception:
                pass
        if not bool(crest_round_spiral.Update()):
            raise RuntimeError("Failed to create crest-round helical path for %s" % scenario)
        crest_round_binding_report = _bind_operation_variables(
            crest_round_spiral,
            crest_round_pass.get("operation_variable_bindings") or [],
        )
        crest_round_binding_report["scenario"] = scenario
        crest_round_binding_report["target"] = "crest_round_spiral_path"
        crest_round_binding_report["role"] = str(crest_round_pass.get("role") or "crest_round_pass")
        steps_report.append(crest_round_binding_report)
        if (crest_round_pass.get("operation_variable_bindings") or []) and not crest_round_binding_report.get("ok"):
            raise RuntimeError("Failed to bind crest-round helical path operation variables for %s" % scenario)
        steps_report.append(
            {
                "step": "create_crest_round_spiral_path",
                "ok": True,
                "scenario": scenario,
                "role": str(crest_round_pass.get("role") or "crest_round_pass"),
                "reference": safe_get(crest_round_spiral, "Reference"),
                "phase_shift": phase_shift,
                "signed_distance": phase_shift_distance,
                "diameter": nominal_diameter,
                "carrier_diameter": carrier_diameter,
                "pitch": float(params.get("pitch") or 0.0),
                "length": float(params.get("length") or 0.0),
                "spiral_length": float(params.get("spiral_length") or params.get("length") or 0.0),
                "height": float(safe_get(crest_round_spiral, "Height", 0.0) or 0.0),
                "building_direction": bool(safe_get(crest_round_spiral, "BuildingDirection", False)),
                "direction": str(params.get("direction") or "right"),
                "turn_direction": bool(safe_get(crest_round_spiral, "TurnDirection", False)),
            }
        )

        crest_round_section_origin_point = _create_point3d_displace(
            model_container,
            str(crest_round_pass.get("profile_origin_name") or ("%s_CREST_PROFILE_ORIGIN" % (params.get("name") or "THREAD"))),
            start_center_point,
            [0.0, 0.0, 0.0],
            guiding_object=spiral_axis,
            distance=crest_round_section_offset_distance,
        )
        crest_round_origin_binding_report = _bind_operation_variables(
            crest_round_section_origin_point,
            _build_distance_point_bindings(
                crest_round_section_offset_distance_expression,
                "crest_round_profile_origin_distance",
            ),
        )
        crest_round_origin_binding_report["scenario"] = scenario
        crest_round_origin_binding_report["target"] = "crest_round_profile_origin_point"
        crest_round_origin_binding_report["role"] = str(crest_round_pass.get("role") or "crest_round_pass")
        steps_report.append(crest_round_origin_binding_report)
        if crest_round_section_offset_distance_expression and not crest_round_origin_binding_report.get("ok"):
            raise RuntimeError("Failed to bind crest-round profile origin point distance for %s" % scenario)
        crest_round_section_origin = [
            float(safe_get(crest_round_section_origin_point, "X", crest_round_start_center_origin[0]) or 0.0),
            float(safe_get(crest_round_section_origin_point, "Y", crest_round_start_center_origin[1]) or 0.0),
            float(safe_get(crest_round_section_origin_point, "Z", crest_round_start_center_origin[2]) or 0.0),
        ]
        steps_report.append(
            {
                "step": "create_crest_round_profile_origin",
                "ok": True,
                "scenario": scenario,
                "role": str(crest_round_pass.get("role") or "crest_round_pass"),
                "reference": safe_get(crest_round_section_origin_point, "Reference"),
                "origin": crest_round_section_origin,
                "origin_anchor_reference": safe_get(start_center_point, "Reference"),
                "origin_anchor": start_center_origin,
                "entry_offset": crest_round_profile_origin_offset,
                "entry_offset_expression": crest_round_profile_origin_offset_expression,
                "entry_offset_base": profile_entry_offset,
                "entry_offset_base_expression": profile_entry_offset_expression,
                "phase_shift_compensation": phase_shift,
                "phase_shift_compensation_expression": phase_shift_expression,
                "signed_distance": crest_round_section_offset_distance,
                "signed_distance_expression": crest_round_section_offset_distance_expression,
                "direction": "opposite_build_direction",
                "guiding_axis_reference": safe_get(spiral_axis, "Reference"),
                "base_point_reference": safe_get(start_center_point, "Reference"),
            }
        )
        crest_round_profile_points = [tuple(point) for point in (crest_round_pass.get("profile_points") or [])]
        if not crest_round_profile_points:
            raise RuntimeError("Crest-round pass profile_points were not generated")
        crest_round_profile_sketch = _build_thread_profile_section_sketch(
            part,
            model_container,
            crest_round_section_origin,
            crest_round_profile_points,
            steps_report,
            name=str(crest_round_pass.get("profile_display_name") or ("%s crest profile" % params.get("name"))) if (crest_round_pass.get("profile_display_name") or params.get("name")) else None,
            section_point=crest_round_section_origin_point,
            axis_start=crest_round_pass.get("axis_start"),
            axis_end=crest_round_pass.get("axis_end"),
            profile_lines=crest_round_pass.get("profile_lines"),
            profile_arcs=crest_round_pass.get("profile_arcs"),
            construction_lines=crest_round_pass.get("construction_lines"),
            planned_constraints=crest_round_pass.get("constraints"),
            planned_dimensions=crest_round_pass.get("dimensions"),
            sketch_options=params.get("sketch"),
            auxiliary_objects=crest_round_auxiliary_objects,
        )
        crest_round_feature = evolutions.Add(47)
        if crest_round_feature is None:
            raise RuntimeError("Evolutions.Add(o3d_cutEvolution) returned None for crest_round_pass")
        crest_round_feature.Sketch = crest_round_profile_sketch
        crest_round_feature.Edges = [crest_round_spiral]
        try:
            crest_round_feature.OperationResult = 2
        except Exception:
            pass
        crest_round_feature_display_name = str(crest_round_pass.get("feature_display_name") or "").strip()
        if crest_round_feature_display_name:
            try:
                crest_round_feature.Name = crest_round_feature_display_name
            except Exception:
                pass
        if not bool(crest_round_feature.Update()):
            raise RuntimeError("Failed to create crest-round pass for %s" % scenario)
        steps_report.append(
            {
                "step": "cut_crest_round_evolution",
                "ok": True,
                "scenario": scenario,
                "role": str(crest_round_pass.get("role") or "crest_round_pass"),
                "reference": safe_get(crest_round_feature, "Reference"),
                "phase_shift": phase_shift,
                "crest_round_radius": float(crest_round_pass.get("crest_round_radius") or 0.0),
                "crest_apex_height": float(crest_round_pass.get("crest_apex_height") or 0.0),
                "crest_tangent_depth": float(crest_round_pass.get("crest_tangent_depth") or 0.0),
                "crest_tangent_half_width": float(crest_round_pass.get("crest_tangent_half_width") or 0.0),
                "model_object_type": safe_get(crest_round_feature, "ModelObjectType"),
                "operation_result": safe_get(crest_round_feature, "OperationResult"),
            }
        )
    auxiliary_visibility_hidden = bool(params.get("auxiliary_geometry_hidden", True))
    if auxiliary_visibility_hidden:
        auxiliary_object_roles = [
            ("start_center_point", start_center_point),
            ("profile_origin_point", section_origin_point),
            ("spiral_axis", spiral_axis),
            ("spiral_path", spiral),
        ]
        auxiliary_object_roles.extend(profile_auxiliary_objects)
        if crest_round_spiral is not None:
            remapped_crest_auxiliary_objects = []
            for role_name, role_object in crest_round_auxiliary_objects:
                mapped_role_name = {
                    "profile_lcs": "crest_round_profile_lcs",
                    "profile_sketch": "crest_round_profile_sketch",
                }.get(str(role_name), str(role_name))
                remapped_crest_auxiliary_objects.append((mapped_role_name, role_object))
            auxiliary_object_roles.extend(
                [
                    ("crest_round_start_center_point", crest_round_start_center_point),
                    ("crest_round_profile_origin_point", crest_round_section_origin_point),
                    ("crest_round_spiral_path", crest_round_spiral),
                ]
            )
            auxiliary_object_roles.extend(remapped_crest_auxiliary_objects)
        auxiliary_objects = _hide_auxiliary_model_objects(
            auxiliary_object_roles,
            True,
        )
        step_report = {
            "step": "hide_helical_thread_auxiliary_geometry",
            "scenario": scenario,
        }
        step_report.update(auxiliary_objects)
        steps_report.append(step_report)
    return {
        "thread": evolution,
        "spiral": spiral,
        "profile_sketch": profile_sketch,
        "crest_round_thread": crest_round_feature,
        "crest_round_spiral": crest_round_spiral,
        "crest_round_profile_sketch": crest_round_profile_sketch,
        "source_feature": source_feature,
        "source_scenario": source_scenario,
        "base_face": base_face,
        "start_face": start_face,
        "end_face": end_face,
        "base_face_report": base_face_report,
        "start_face_report": start_face_report,
        "end_face_report": end_face_report,
    }


def _build_external_helical_thread_feature(part, model_container, params, preview, steps_report):
    return _build_helical_thread_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        scenario="external_helical_thread",
    )


def _build_internal_helical_thread_feature(part, model_container, params, preview, steps_report):
    return _build_helical_thread_feature(
        part,
        model_container,
        params,
        preview,
        steps_report,
        scenario="internal_helical_thread",
    )


def _normalize_stepped_shaft_face_selector(selector):
    normalized = str(selector or "far_end_face").strip().lower().replace("-", "_")
    aliases = {
        "far_end_face": "far_end_face",
        "end_face": "far_end_face",
        "tail_face": "far_end_face",
        "tail_end_face": "far_end_face",
        "near_end_face": "start_face",
        "start_face": "start_face",
        "head_face": "start_face",
        "front_face": "start_face",
    }
    resolved = aliases.get(normalized, normalized)
    if _parse_stepped_shaft_face_selector(resolved) is None:
        raise RuntimeError("Unsupported stepped_shaft face selector: %s" % selector)
    return resolved


def _list_stepped_shaft_selector_choices(feature_preview=None):
    selector_points = {}
    preview_payload = feature_preview or {}
    preview_selectors = preview_payload.get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    anchors = ((preview_payload.get("interface") or {}).get("anchors") or {})
    anchor_selectors = anchors.get("selector_points") or {}
    if isinstance(anchor_selectors, dict):
        selector_points.update(anchor_selectors)
    if selector_points:
        return sorted(str(name).strip() for name in selector_points.keys() if str(name).strip())
    return [
        "far_end_face",
        "start_face",
        "step_1_start_face",
        "step_1_end_face",
        "step_1_outer_face",
        "shoulder_1_face",
    ]


def _format_stepped_shaft_selector_choices(selector_names):
    if not selector_names:
        return "<none>"
    return ", ".join(selector_names)


def _normalize_external_conical_step_face_selector(selector):
    normalized = str(selector or "end_face").strip().lower().replace("-", "_")
    aliases = {
        "start_face": "start_face",
        "near_end_face": "start_face",
        "head_face": "start_face",
        "large_end_face": "start_face",
        "seat_face": "start_face",
        "shoulder_face": "start_face",
        "end_face": "end_face",
        "far_end_face": "end_face",
        "tail_face": "end_face",
        "small_end_face": "end_face",
        "free_end_face": "end_face",
        "nose_face": "end_face",
        "tip_face": "end_face",
        "outer_face": "outer_face",
        "outer_conical_face": "outer_face",
        "conical_face": "outer_face",
        "lateral_face": "outer_face",
    }
    resolved = aliases.get(normalized, normalized)
    if resolved not in ("start_face", "end_face", "outer_face"):
        raise RuntimeError("Unsupported external_conical_step face selector: %s" % selector)
    return resolved


def _list_external_conical_step_selector_choices():
    return ["end_face", "outer_face", "start_face"]


def _format_external_conical_step_selector_choices(selector_names):
    if not selector_names:
        return "<none>"
    return ", ".join(selector_names)


def _normalize_internal_conical_step_face_selector(selector):
    normalized = str(selector or "inner_face").strip().lower().replace("-", "_")
    aliases = {
        "start_face": "start_face",
        "entry_face": "start_face",
        "end_face": "end_face",
        "tail_face": "end_face",
        "inner_face": "inner_face",
        "inner_conical_face": "inner_face",
        "conical_face": "inner_face",
        "lateral_face": "inner_face",
    }
    resolved = aliases.get(normalized, normalized)
    if resolved not in ("start_face", "end_face", "inner_face"):
        raise RuntimeError("Unsupported internal_conical_step face selector: %s" % selector)
    return resolved


def _list_internal_conical_step_selector_choices():
    return ["end_face", "inner_face", "start_face"]


def _format_internal_conical_step_selector_choices(selector_names):
    if not selector_names:
        return "<none>"
    return ", ".join(selector_names)


def _normalize_internal_cylindrical_step_face_selector(selector):
    normalized = str(selector or "inner_face").strip().lower().replace("-", "_")
    aliases = {
        "start_face": "start_face",
        "entry_face": "start_face",
        "end_face": "end_face",
        "far_end_face": "end_face",
        "tail_face": "end_face",
        "inner_face": "inner_face",
        "inner_cylindrical_face": "inner_face",
        "bore_face": "inner_face",
        "cylindrical_face": "inner_face",
        "lateral_face": "inner_face",
    }
    resolved = aliases.get(normalized, normalized)
    if _parse_internal_cylindrical_step_face_selector(resolved) is None:
        raise RuntimeError("Unsupported internal_cylindrical_step face selector: %s" % selector)
    return resolved


def _normalize_face_ring_groove_face_selector(selector):
    normalized = str(selector or "bottom_face").strip().lower().replace("-", "_")
    aliases = {
        "bottom_face": "bottom_face",
        "groove_bottom_face": "bottom_face",
        "inner_wall_face": "inner_wall_face",
        "inner_face": "inner_wall_face",
        "outer_wall_face": "outer_wall_face",
        "outer_face": "outer_wall_face",
    }
    resolved = aliases.get(normalized, normalized)
    if resolved not in ("bottom_face", "inner_wall_face", "outer_wall_face"):
        raise RuntimeError("Unsupported face_ring_groove face selector: %s" % selector)
    return resolved


def _default_revolved_feature_face_selector(source_scenario):
    if source_scenario == "stepped_shaft":
        return "far_end_face"
    if source_scenario == "face_ring_groove":
        return "bottom_face"
    return "end_face"


def _list_internal_cylindrical_step_selector_choices(feature_preview=None):
    selector_points = {}
    preview_payload = feature_preview or {}
    preview_selectors = preview_payload.get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    anchors = ((preview_payload.get("interface") or {}).get("anchors") or {})
    anchor_selectors = anchors.get("selector_points") or {}
    if isinstance(anchor_selectors, dict):
        selector_points.update(anchor_selectors)
    if selector_points:
        return sorted(str(name).strip() for name in selector_points.keys() if str(name).strip())
    return [
        "end_face",
        "inner_face",
        "start_face",
        "step_1_start_face",
        "step_1_end_face",
        "step_1_inner_face",
        "shoulder_1_face",
    ]


def _format_internal_cylindrical_step_selector_choices(selector_names):
    if not selector_names:
        return "<none>"
    return ", ".join(selector_names)


def _normalize_polygonal_step_face_selector(selector):
    normalized = str(selector or "end_face").strip().lower().replace("-", "_")
    aliases = {
        "start_face": "start_face",
        "near_end_face": "start_face",
        "head_face": "start_face",
        "end_face": "end_face",
        "far_end_face": "end_face",
        "tail_face": "end_face",
        "side_face_1": "side_face_1",
        "outer_face_1": "side_face_1",
        "inner_face_1": "side_face_1",
        "first_side_face": "side_face_1",
    }
    resolved = aliases.get(normalized, normalized)
    if resolved not in ("start_face", "end_face", "side_face_1"):
        raise RuntimeError("Unsupported polygonal_step face selector: %s" % selector)
    return resolved


def _list_polygonal_step_selector_choices(feature_preview=None):
    selector_points = {}
    preview_payload = feature_preview or {}
    preview_selectors = preview_payload.get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    anchors = ((preview_payload.get("interface") or {}).get("anchors") or {})
    anchor_selectors = anchors.get("selector_points") or {}
    if isinstance(anchor_selectors, dict):
        selector_points.update(anchor_selectors)
    if selector_points:
        return sorted(str(name).strip() for name in selector_points.keys() if str(name).strip())
    return ["end_face", "side_face_1", "start_face"]


def _format_polygonal_step_selector_choices(selector_names):
    if not selector_names:
        return "<none>"
    return ", ".join(selector_names)


def _normalize_flat_step_face_selector(selector):
    normalized = str(selector or "end_face").strip().lower().replace("-", "_")
    aliases = {
        "start_face": "start_face",
        "near_end_face": "start_face",
        "head_face": "start_face",
        "end_face": "end_face",
        "far_end_face": "end_face",
        "tail_face": "end_face",
        "flat_1_face": "flat_1_face",
        "first_flat_face": "flat_1_face",
        "flat_face_1": "flat_1_face",
        "flat_2_face": "flat_2_face",
        "second_flat_face": "flat_2_face",
        "flat_face_2": "flat_2_face",
    }
    resolved = aliases.get(normalized, normalized)
    if resolved not in ("start_face", "end_face", "flat_1_face", "flat_2_face"):
        raise RuntimeError("Unsupported flat_step face selector: %s" % selector)
    return resolved


def _list_flat_step_selector_choices(feature_preview=None):
    selector_points = {}
    preview_payload = feature_preview or {}
    preview_selectors = preview_payload.get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    anchors = ((preview_payload.get("interface") or {}).get("anchors") or {})
    anchor_selectors = anchors.get("selector_points") or {}
    if isinstance(anchor_selectors, dict):
        selector_points.update(anchor_selectors)
    if selector_points:
        return sorted(str(name).strip() for name in selector_points.keys() if str(name).strip())
    return ["end_face", "flat_1_face", "start_face"]


def _format_flat_step_selector_choices(selector_names):
    if not selector_names:
        return "<none>"
    return ", ".join(selector_names)


def _list_face_ring_groove_selector_choices():
    return ["bottom_face", "inner_wall_face", "outer_wall_face"]


def _format_face_ring_groove_selector_choices(selector_names):
    if not selector_names:
        return "<none>"
    return ", ".join(selector_names)


def _parse_stepped_shaft_face_selector(selector):
    normalized = str(selector or "").strip().lower().replace("-", "_")
    if normalized == "start_face":
        return {"selector": "start_face", "kind": "boundary", "boundary_index": 0}
    if normalized == "far_end_face":
        return {"selector": "far_end_face", "kind": "boundary", "boundary_index": -1}
    for pattern in (_STEP_FACE_PATTERN, _STEP_FACE_PATTERN_COMPACT):
        match = pattern.match(normalized)
        if match:
            step_index = int(match.group(1))
            position = str(match.group(2))
            boundary_index = step_index - 1 if position == "start" else step_index
            return {
                "selector": "step_%s_%s_face" % (step_index, position),
                "kind": "step_face",
                "step_index": step_index,
                "position": position,
                "boundary_index": boundary_index,
            }
    for pattern in (_SHOULDER_FACE_PATTERN, _SHOULDER_FACE_PATTERN_COMPACT):
        match = pattern.match(normalized)
        if match:
            shoulder_index = int(match.group(1))
            return {
                "selector": "shoulder_%s_face" % shoulder_index,
                "kind": "shoulder_face",
                "shoulder_index": shoulder_index,
                "boundary_index": shoulder_index,
            }
    for pattern in (_STEP_OUTER_FACE_PATTERN, _STEP_OUTER_FACE_PATTERN_COMPACT):
        match = pattern.match(normalized)
        if match:
            step_index = int(match.group(1))
            return {
                "selector": "step_%s_outer_face" % step_index,
                "kind": "step_outer_face",
                "step_index": step_index,
                "boundary_index": None,
            }
    return None


def _parse_internal_cylindrical_step_face_selector(selector):
    normalized = str(selector or "").strip().lower().replace("-", "_")
    if normalized in ("start_face", "entry_face"):
        return {"selector": "start_face", "kind": "boundary", "boundary_index": 0}
    if normalized in ("end_face", "tail_face", "far_end_face"):
        return {"selector": "end_face", "kind": "boundary", "boundary_index": -1}
    if normalized in ("inner_face", "inner_cylindrical_face", "bore_face", "cylindrical_face", "lateral_face"):
        return {"selector": "inner_face", "kind": "step_inner_face", "step_index": 1, "boundary_index": None}
    for pattern in (_STEP_FACE_PATTERN, _STEP_FACE_PATTERN_COMPACT):
        match = pattern.match(normalized)
        if match:
            step_index = int(match.group(1))
            position = str(match.group(2))
            boundary_index = step_index - 1 if position == "start" else step_index
            return {
                "selector": "step_%s_%s_face" % (step_index, position),
                "kind": "step_face",
                "step_index": step_index,
                "position": position,
                "boundary_index": boundary_index,
            }
    for pattern in (_SHOULDER_FACE_PATTERN, _SHOULDER_FACE_PATTERN_COMPACT):
        match = pattern.match(normalized)
        if match:
            shoulder_index = int(match.group(1))
            return {
                "selector": "shoulder_%s_face" % shoulder_index,
                "kind": "shoulder_face",
                "shoulder_index": shoulder_index,
                "boundary_index": shoulder_index,
            }
    for pattern in (_STEP_INNER_FACE_PATTERN, _STEP_INNER_FACE_PATTERN_COMPACT):
        match = pattern.match(normalized)
        if match:
            step_index = int(match.group(1))
            return {
                "selector": "step_%s_inner_face" % step_index,
                "kind": "step_inner_face",
                "step_index": step_index,
                "boundary_index": None,
            }
    return None


def _build_stepped_shaft_boundary_points(params, axis_start):
    steps = (params or {}).get("steps") or []
    x = float(axis_start[0]) if isinstance(axis_start, (list, tuple)) and len(axis_start) >= 1 else 0.0
    y = float(axis_start[1]) if isinstance(axis_start, (list, tuple)) and len(axis_start) >= 2 else 0.0
    points = [[x, y, 0.0]]
    for step in steps:
        x += float((step or {}).get("length") or 0.0)
        points.append([x, y, 0.0])
    return points


def _resolve_stepped_shaft_selector_target(feature_preview, selector):
    selector_info = _parse_stepped_shaft_face_selector(selector)
    if selector_info is None:
        raise RuntimeError(
            "Unsupported stepped_shaft face selector: %s; available selectors: %s"
            % (selector, _format_stepped_shaft_selector_choices(_list_stepped_shaft_selector_choices(feature_preview)))
        )
    preview_payload = feature_preview or {}
    params = preview_payload.get("params") or {}
    anchors = ((preview_payload.get("interface") or {}).get("anchors") or {})
    axis_start = anchors.get("axis_start") or [0.0, 0.0]
    boundary_points = _build_stepped_shaft_boundary_points(params, axis_start)
    if selector_info.get("kind") == "step_outer_face":
        step_index = int(selector_info["step_index"])
        steps = params.get("steps") or []
        if step_index < 1 or step_index > len(steps):
            raise RuntimeError(
                "Stepped_shaft selector %s is out of range for the source body; available selectors: %s"
                % (selector, _format_stepped_shaft_selector_choices(_list_stepped_shaft_selector_choices(feature_preview)))
            )
        start_point = boundary_points[step_index - 1]
        end_point = boundary_points[step_index]
        step_payload = steps[step_index - 1] or {}
        radius = step_payload.get("radius")
        if radius is None:
            diameter = float(step_payload.get("diameter") or 0.0)
            radius = diameter / 2.0
        return {
            "selector_info": selector_info,
            "target_x": float((float(start_point[0]) + float(end_point[0])) / 2.0),
            "target_x_range": [float(start_point[0]), float(end_point[0])],
            "target_radius": float(radius),
        }
    boundary_index = int(selector_info["boundary_index"])
    if boundary_index == -1:
        boundary_index = len(boundary_points) - 1
    if boundary_index < 0 or boundary_index >= len(boundary_points):
        raise RuntimeError(
            "Stepped_shaft selector %s is out of range for the source body; available selectors: %s"
            % (selector, _format_stepped_shaft_selector_choices(_list_stepped_shaft_selector_choices(feature_preview)))
        )
    return {
        "selector_info": selector_info,
        "target_x": float(boundary_points[boundary_index][0]),
        "target_x_range": None,
        "target_radius": None,
    }


def _resolve_internal_cylindrical_step_selector_target(feature_preview, selector):
    selector_info = _parse_internal_cylindrical_step_face_selector(selector)
    if selector_info is None:
        raise RuntimeError(
            "Unsupported internal_cylindrical_step face selector: %s; available selectors: %s"
            % (
                selector,
                _format_internal_cylindrical_step_selector_choices(
                    _list_internal_cylindrical_step_selector_choices(feature_preview)
                ),
            )
        )

    preview_payload = feature_preview or {}
    selector_points = {}
    preview_selectors = preview_payload.get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    anchors = ((preview_payload.get("interface") or {}).get("anchors") or {})
    anchor_selectors = anchors.get("selector_points") or {}
    if isinstance(anchor_selectors, dict):
        selector_points.update(anchor_selectors)
    params = preview_payload.get("params") or {}
    steps = params.get("steps") or []

    canonical_selector = str(selector_info["selector"])
    target_origin = selector_points.get(canonical_selector)
    target_x = float(target_origin[0]) if isinstance(target_origin, (list, tuple)) and len(target_origin) >= 1 else None

    if selector_info.get("kind") == "step_inner_face":
        step_index = int(selector_info["step_index"])
        if step_index < 1 or step_index > len(steps):
            raise RuntimeError(
                "Internal_cylindrical_step selector %s is out of range for the source body; available selectors: %s"
                % (
                    selector,
                    _format_internal_cylindrical_step_selector_choices(
                        _list_internal_cylindrical_step_selector_choices(feature_preview)
                    ),
                )
            )
        start_selector = "step_%s_start_face" % step_index
        end_selector = "step_%s_end_face" % step_index
        start_origin = selector_points.get(start_selector)
        end_origin = selector_points.get(end_selector)
        if not (
            isinstance(start_origin, (list, tuple))
            and len(start_origin) >= 1
            and isinstance(end_origin, (list, tuple))
            and len(end_origin) >= 1
        ):
            raise RuntimeError(
                "Internal_cylindrical_step selector %s is unavailable in preview anchors; available selectors: %s"
                % (
                    selector,
                    _format_internal_cylindrical_step_selector_choices(
                        _list_internal_cylindrical_step_selector_choices(feature_preview)
                    ),
                )
            )
        step_payload = steps[step_index - 1] or {}
        radius = float(step_payload.get("radius") or (float(step_payload.get("diameter") or 0.0) / 2.0))
        return {
            "selector_info": selector_info,
            "target_x": target_x,
            "target_x_range": [
                min(float(start_origin[0]), float(end_origin[0])),
                max(float(start_origin[0]), float(end_origin[0])),
            ],
            "target_radius": radius,
        }

    boundary_index = int(selector_info["boundary_index"])
    ordered_boundaries = []
    for name, origin in selector_points.items():
        if not isinstance(origin, (list, tuple)) or len(origin) < 1:
            continue
        parsed = _parse_internal_cylindrical_step_face_selector(name)
        if parsed is None or parsed.get("kind") not in ("boundary", "step_face", "shoulder_face"):
            continue
        candidate_boundary_index = int(parsed["boundary_index"])
        if candidate_boundary_index == -1:
            candidate_boundary_index = len(steps)
        ordered_boundaries.append((candidate_boundary_index, float(origin[0])))
    ordered_boundaries = sorted({item[0]: item[1] for item in ordered_boundaries}.items(), key=lambda item: item[0])
    if boundary_index == -1:
        boundary_index = len(steps)
    if boundary_index < 0 or boundary_index > len(steps):
        raise RuntimeError(
            "Internal_cylindrical_step selector %s is out of range for the source body; available selectors: %s"
            % (
                selector,
                _format_internal_cylindrical_step_selector_choices(
                    _list_internal_cylindrical_step_selector_choices(feature_preview)
                ),
            )
        )
    if target_x is None:
        boundary_map = dict(ordered_boundaries)
        target_x = float(boundary_map.get(boundary_index))
    return {
        "selector_info": selector_info,
        "target_x": target_x,
        "target_x_range": None,
        "target_radius": None,
    }


def _get_feature_face_model_objects(feature_object):
    import win32com.client

    feature = win32com.client.CastTo(feature_object, "IFeature7")

    result_bodies = safe_get(feature, "ResultBodies")
    for result_body in _ensure_dispatch_sequence(result_bodies):
        body_feature = _cast_to_com_interface(result_body, "IFeature7")
        model_objects = safe_get(body_feature, "ModelObjects")
        if callable(model_objects):
            try:
                model_objects = model_objects(0)
            except Exception:
                model_objects = None
        if model_objects is not None and _ensure_dispatch_sequence(model_objects):
            return model_objects, "ResultBodies"

    model_objects = safe_get(feature, "ModelObjects")
    if callable(model_objects):
        try:
            model_objects = model_objects(0)
        except Exception:
            model_objects = None
    if model_objects is not None and _ensure_dispatch_sequence(model_objects):
        return model_objects, "Feature.ModelObjects"

    raise RuntimeError("Feature does not expose result ModelObjects")


def _select_stepped_shaft_planar_face(feature_object, selector, feature_preview=None):
    import win32com.client

    try:
        selector_name = _normalize_stepped_shaft_face_selector(selector)
    except RuntimeError as exc:
        raise RuntimeError(
            "Unsupported stepped_shaft face selector: %s; available selectors: %s"
            % (
                selector,
                _format_stepped_shaft_selector_choices(_list_stepped_shaft_selector_choices(feature_preview)),
            )
        ) from exc
    target_x = None
    target_x_range = None
    target_radius = None
    selector_info = None
    if feature_preview is not None:
        target_info = _resolve_stepped_shaft_selector_target(feature_preview, selector_name)
        target_x = target_info.get("target_x")
        target_x_range = target_info.get("target_x_range")
        target_radius = target_info.get("target_radius")
        selector_info = target_info.get("selector_info")
    objects, body_source = _get_feature_face_model_objects(feature_object)
    faces = []
    for item in _ensure_dispatch_sequence(objects):
        face = _cast_to_com_interface(item, "IFace")
        if face is None:
            continue
        is_planar = bool(safe_get(face, "IsPlanar", False))
        is_cylinder = bool(safe_get(face, "IsCylinder", False))
        if not is_planar and not is_cylinder:
            continue
        edges = _ensure_dispatch_sequence(safe_get(face, "LimitingEdges"))
        if not edges:
            continue
        edge_points = []
        for edge in edges:
            for at in (True, False):
                try:
                    point = edge.GetPoint(at)
                except Exception:
                    continue
                if not isinstance(point, tuple) or len(point) < 4 or not point[0]:
                    continue
                edge_points.append([float(point[1]), float(point[2]), float(point[3])])
        if not edge_points:
            continue
        x_values = [point[0] for point in edge_points]
        faces.append(
            {
                "face": face,
                "reference": safe_get(face, "Reference"),
                "surface_type": safe_get(face, "Surface3DType"),
                "is_planar": is_planar,
                "is_cylinder": is_cylinder,
                "radius": float(safe_get(face, "Radius", 0.0) or 0.0),
                "anchor_point": list(edge_points[0]),
                "x_min": min(x_values),
                "x_max": max(x_values),
                "x_mid": (min(x_values) + max(x_values)) / 2.0,
            }
        )
    if not faces:
        raise RuntimeError("Failed to resolve reference faces on the source body")
    selector_kind = (selector_info or {}).get("kind")
    if selector_kind == "step_outer_face":
        candidates = [item for item in faces if item["is_cylinder"]]
        if not candidates:
            raise RuntimeError("Failed to resolve cylindrical faces on the source body")
        start_x = float(target_x_range[0]) if isinstance(target_x_range, (list, tuple)) else float(target_x or 0.0)
        end_x = float(target_x_range[1]) if isinstance(target_x_range, (list, tuple)) else float(target_x or 0.0)
        selected = min(
            candidates,
            key=lambda item: (
                abs(float(item["x_min"]) - start_x) + abs(float(item["x_max"]) - end_x),
                abs(float(item["radius"]) - float(target_radius or 0.0)),
                abs(float(item["x_mid"]) - float(target_x or 0.0)),
            ),
        )
    else:
        candidates = [item for item in faces if item["is_planar"]]
        if not candidates:
            raise RuntimeError("Failed to resolve planar faces on the source body")
        if target_x is None:
            if selector_name == "start_face":
                selected = min(candidates, key=lambda item: item["anchor_point"][0])
            else:
                selected = max(candidates, key=lambda item: item["anchor_point"][0])
        else:
            selected = min(candidates, key=lambda item: abs(float(item["anchor_point"][0]) - float(target_x)))
    return selected["face"], {
        "selector": selector_name,
        "selector_info": selector_info,
        "target_x": target_x,
        "target_x_range": target_x_range,
        "target_radius": target_radius,
        "candidate_count": len(faces),
        "selected_reference": selected["reference"],
        "selected_anchor_point": selected["anchor_point"],
        "selected_x_range": [selected["x_min"], selected["x_max"]],
        "selected_radius": selected["radius"],
        "selected_is_planar": selected["is_planar"],
        "selected_is_cylinder": selected["is_cylinder"],
        "body_source": body_source,
        "candidates": [
            {
                "reference": item["reference"],
                "anchor_point": item["anchor_point"],
                "surface_type": item["surface_type"],
                "is_planar": item["is_planar"],
                "is_cylinder": item["is_cylinder"],
                "radius": item["radius"],
                "x_min": item["x_min"],
                "x_max": item["x_max"],
            }
            for item in faces
        ],
    }


def _select_external_conical_step_face(feature_object, selector, feature_preview=None):
    import win32com.client

    try:
        selector_name = _normalize_external_conical_step_face_selector(selector)
    except RuntimeError as exc:
        raise RuntimeError(
            "Unsupported external_conical_step face selector: %s; available selectors: %s"
            % (
                selector,
                _format_external_conical_step_selector_choices(_list_external_conical_step_selector_choices()),
            )
        ) from exc

    objects, body_source = _get_feature_face_model_objects(feature_object)
    faces = []
    for item in _ensure_dispatch_sequence(objects):
        face = _cast_to_com_interface(item, "IFace")
        if face is None:
            continue
        is_planar = bool(safe_get(face, "IsPlanar", False))
        is_cylinder = bool(safe_get(face, "IsCylinder", False))
        edges = _ensure_dispatch_sequence(safe_get(face, "LimitingEdges"))
        if not edges:
            continue
        edge_points = []
        for edge in edges:
            for at in (True, False):
                try:
                    point = edge.GetPoint(at)
                except Exception:
                    continue
                if not isinstance(point, tuple) or len(point) < 4 or not point[0]:
                    continue
                edge_points.append([float(point[1]), float(point[2]), float(point[3])])
        if not edge_points:
            continue
        x_values = [point[0] for point in edge_points]
        faces.append(
            {
                "face": face,
                "reference": safe_get(face, "Reference"),
                "surface_type": safe_get(face, "Surface3DType"),
                "is_planar": is_planar,
                "is_cylinder": is_cylinder,
                "anchor_point": list(edge_points[0]),
                "x_min": min(x_values),
                "x_max": max(x_values),
                "x_mid": (min(x_values) + max(x_values)) / 2.0,
            }
        )
    if not faces:
        raise RuntimeError("Failed to resolve reference faces on the source body")

    if selector_name == "outer_face":
        candidates = [item for item in faces if not item["is_planar"]]
        if not candidates:
            raise RuntimeError("Failed to resolve outer conical face on the source body")
        selected = max(candidates, key=lambda item: abs(float(item["x_max"]) - float(item["x_min"])))
    else:
        candidates = [item for item in faces if item["is_planar"]]
        if not candidates:
            raise RuntimeError("Failed to resolve planar faces on the source body")
        if selector_name == "start_face":
            selected = min(candidates, key=lambda item: item["anchor_point"][0])
        else:
            selected = max(candidates, key=lambda item: item["anchor_point"][0])

    return selected["face"], {
        "selector": selector_name,
        "candidate_count": len(faces),
        "selected_reference": selected["reference"],
        "selected_anchor_point": selected["anchor_point"],
        "selected_x_range": [selected["x_min"], selected["x_max"]],
        "selected_is_planar": selected["is_planar"],
        "selected_is_cylinder": selected["is_cylinder"],
        "body_source": body_source,
        "candidates": [
            {
                "reference": item["reference"],
                "anchor_point": item["anchor_point"],
                "surface_type": item["surface_type"],
                "is_planar": item["is_planar"],
                "is_cylinder": item["is_cylinder"],
                "x_min": item["x_min"],
                "x_max": item["x_max"],
            }
            for item in faces
        ],
    }


def _select_internal_conical_step_face(feature_object, selector, feature_preview=None):
    import win32com.client

    try:
        selector_name = _normalize_internal_conical_step_face_selector(selector)
    except RuntimeError as exc:
        raise RuntimeError(
            "Unsupported internal_conical_step face selector: %s; available selectors: %s"
            % (
                selector,
                _format_internal_conical_step_selector_choices(_list_internal_conical_step_selector_choices()),
            )
        ) from exc

    objects, body_source = _get_feature_face_model_objects(feature_object)
    faces = []
    for item in _ensure_dispatch_sequence(objects):
        face = _cast_to_com_interface(item, "IFace")
        if face is None:
            continue
        is_planar = bool(safe_get(face, "IsPlanar", False))
        edges = _ensure_dispatch_sequence(safe_get(face, "LimitingEdges"))
        if not edges:
            continue
        edge_points = []
        for edge in edges:
            for at in (True, False):
                try:
                    point = edge.GetPoint(at)
                except Exception:
                    continue
                if not isinstance(point, tuple) or len(point) < 4 or not point[0]:
                    continue
                edge_points.append([float(point[1]), float(point[2]), float(point[3])])
        if not edge_points:
            continue
        x_values = [point[0] for point in edge_points]
        radii = [(point[1] ** 2 + point[2] ** 2) ** 0.5 for point in edge_points]
        faces.append(
            {
                "face": face,
                "reference": safe_get(face, "Reference"),
                "surface_type": safe_get(face, "Surface3DType"),
                "is_planar": is_planar,
                "anchor_point": list(edge_points[0]),
                "x_min": min(x_values),
                "x_max": max(x_values),
                "x_mid": (min(x_values) + max(x_values)) / 2.0,
                "radius_min": min(radii) if radii else 0.0,
                "radius_max": max(radii) if radii else 0.0,
            }
        )
    if not faces:
        raise RuntimeError("Failed to resolve reference faces on the source body")

    selector_points = {}
    preview_selectors = (feature_preview or {}).get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    anchors = (((feature_preview or {}).get("interface") or {}).get("anchors") or {})
    anchor_selectors = anchors.get("selector_points") or {}
    if isinstance(anchor_selectors, dict):
        selector_points.update(anchor_selectors)
    target_origin = selector_points.get(selector_name)
    target_x = float(target_origin[0]) if isinstance(target_origin, (list, tuple)) and len(target_origin) >= 1 else None
    inner_origin = selector_points.get("inner_face")
    cut_span = None
    if isinstance(inner_origin, (list, tuple)) and target_x is not None and len(inner_origin) >= 1:
        cut_span = 2.0 * abs(float(inner_origin[0]) - float(target_x))

    if selector_name == "inner_face":
        candidates = [item for item in faces if not item["is_planar"]]
        if not candidates:
            raise RuntimeError("Failed to resolve inner conical face on the source body")
        if cut_span is not None and isinstance(inner_origin, (list, tuple)) and len(inner_origin) >= 1:
            selected = min(
                candidates,
                key=lambda item: (
                    abs(abs(float(item["x_max"]) - float(item["x_min"])) - cut_span),
                    abs(float(item["x_mid"]) - float(inner_origin[0])),
                    float(item["radius_max"]),
                ),
            )
        else:
            selected = min(candidates, key=lambda item: float(item["radius_max"]))
    else:
        candidates = [item for item in faces if item["is_planar"]]
        if not candidates:
            raise RuntimeError("Failed to resolve planar faces on the source body")
        if target_x is None:
            if selector_name == "start_face":
                selected = min(candidates, key=lambda item: item["anchor_point"][0])
            else:
                selected = max(candidates, key=lambda item: item["anchor_point"][0])
        else:
            selected = min(candidates, key=lambda item: abs(float(item["x_mid"]) - target_x))

    return selected["face"], {
        "selector": selector_name,
        "candidate_count": len(faces),
        "selected_reference": selected["reference"],
        "selected_anchor_point": selected["anchor_point"],
        "selected_x_range": [selected["x_min"], selected["x_max"]],
        "selected_radius_range": [selected["radius_min"], selected["radius_max"]],
        "selected_is_planar": selected["is_planar"],
        "selected_surface_type": selected["surface_type"],
        "body_source": body_source,
    }


def _select_internal_cylindrical_step_face(feature_object, selector, feature_preview=None):
    try:
        selector_name = _normalize_internal_cylindrical_step_face_selector(selector)
    except RuntimeError as exc:
        raise RuntimeError(
            "Unsupported internal_cylindrical_step face selector: %s; available selectors: %s"
            % (
                selector,
                _format_internal_cylindrical_step_selector_choices(
                    _list_internal_cylindrical_step_selector_choices(feature_preview)
                ),
            )
        ) from exc

    import win32com.client

    target_info = _resolve_internal_cylindrical_step_selector_target(feature_preview, selector_name)
    target_x = target_info.get("target_x")
    target_x_range = target_info.get("target_x_range")
    target_radius = target_info.get("target_radius")
    selector_info = target_info.get("selector_info") or {}

    objects, body_source = _get_feature_face_model_objects(feature_object)
    faces = []
    for item in _ensure_dispatch_sequence(objects):
        face = _cast_to_com_interface(item, "IFace")
        if face is None:
            continue
        is_planar = bool(safe_get(face, "IsPlanar", False))
        is_cylinder = bool(safe_get(face, "IsCylinder", False))
        edges = _ensure_dispatch_sequence(safe_get(face, "LimitingEdges"))
        if not edges:
            continue
        edge_points = []
        for edge in edges:
            for at in (True, False):
                try:
                    point = edge.GetPoint(at)
                except Exception:
                    continue
                if not isinstance(point, tuple) or len(point) < 4 or not point[0]:
                    continue
                edge_points.append([float(point[1]), float(point[2]), float(point[3])])
        if not edge_points:
            continue
        x_values = [point[0] for point in edge_points]
        radii = [(point[1] ** 2 + point[2] ** 2) ** 0.5 for point in edge_points]
        faces.append(
            {
                "face": face,
                "reference": safe_get(face, "Reference"),
                "surface_type": safe_get(face, "Surface3DType"),
                "is_planar": is_planar,
                "is_cylinder": is_cylinder,
                "anchor_point": list(edge_points[0]),
                "x_min": min(x_values),
                "x_max": max(x_values),
                "x_mid": (min(x_values) + max(x_values)) / 2.0,
                "radius_min": min(radii) if radii else 0.0,
                "radius_max": max(radii) if radii else 0.0,
            }
        )
    if not faces:
        raise RuntimeError("Failed to resolve reference faces on the source body")

    if selector_info.get("kind") == "step_inner_face":
        candidates = [item for item in faces if item["is_cylinder"]]
        if not candidates:
            raise RuntimeError("Failed to resolve cylindrical inner faces on the source body")
        start_x = float(target_x_range[0]) if isinstance(target_x_range, (list, tuple)) else float(target_x or 0.0)
        end_x = float(target_x_range[1]) if isinstance(target_x_range, (list, tuple)) else float(target_x or 0.0)
        selected = min(
            candidates,
            key=lambda item: (
                abs(float(item["x_min"]) - start_x) + abs(float(item["x_max"]) - end_x),
                abs(float(item["radius_max"]) - float(target_radius or 0.0)),
                abs(float(item["x_mid"]) - float(target_x or 0.0)),
            ),
        )
    else:
        candidates = [item for item in faces if item["is_planar"]]
        if not candidates:
            raise RuntimeError("Failed to resolve planar faces on the source body")
        if target_x is None:
            if selector_name == "start_face":
                selected = min(candidates, key=lambda item: item["anchor_point"][0])
            else:
                selected = max(candidates, key=lambda item: item["anchor_point"][0])
        else:
            selected = min(candidates, key=lambda item: abs(float(item["x_mid"]) - float(target_x)))

    return selected["face"], {
        "selector": selector_name,
        "selector_info": selector_info,
        "target_x": target_x,
        "target_x_range": target_x_range,
        "target_radius": target_radius,
        "candidate_count": len(faces),
        "selected_reference": selected["reference"],
        "selected_anchor_point": selected["anchor_point"],
        "selected_x_range": [selected["x_min"], selected["x_max"]],
        "selected_radius_range": [selected["radius_min"], selected["radius_max"]],
        "selected_is_planar": selected["is_planar"],
        "selected_is_cylinder": selected["is_cylinder"],
        "selected_surface_type": selected["surface_type"],
        "body_source": body_source,
    }


def _select_polygonal_step_face(feature_object, selector, feature_preview=None):
    try:
        selector_name = _normalize_polygonal_step_face_selector(selector)
    except RuntimeError as exc:
        raise RuntimeError(
            "Unsupported polygonal_step face selector: %s; available selectors: %s"
            % (
                selector,
                _format_polygonal_step_selector_choices(_list_polygonal_step_selector_choices(feature_preview)),
            )
        ) from exc

    selector_points = {}
    preview_payload = feature_preview or {}
    preview_selectors = preview_payload.get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    anchors = ((preview_payload.get("interface") or {}).get("anchors") or {})
    anchor_selectors = anchors.get("selector_points") or {}
    if isinstance(anchor_selectors, dict):
        selector_points.update(anchor_selectors)
    target_origin = selector_points.get(selector_name)
    target_x = float(target_origin[0]) if isinstance(target_origin, (list, tuple)) and len(target_origin) >= 1 else None
    target_y = float(target_origin[1]) if isinstance(target_origin, (list, tuple)) and len(target_origin) >= 2 else None
    target_z = float(target_origin[2]) if isinstance(target_origin, (list, tuple)) and len(target_origin) >= 3 else 0.0

    objects, body_source = _get_feature_face_model_objects(feature_object)
    faces = []
    for item in _ensure_dispatch_sequence(objects):
        face = _cast_to_com_interface(item, "IFace")
        if face is None:
            continue
        is_planar = bool(safe_get(face, "IsPlanar", False))
        edges = _ensure_dispatch_sequence(safe_get(face, "LimitingEdges"))
        if not edges:
            continue
        edge_points = []
        for edge in edges:
            for at in (True, False):
                try:
                    point = edge.GetPoint(at)
                except Exception:
                    continue
                if not isinstance(point, tuple) or len(point) < 4 or not point[0]:
                    continue
                edge_points.append([float(point[1]), float(point[2]), float(point[3])])
        if not edge_points:
            continue
        x_values = [point[0] for point in edge_points]
        y_values = [point[1] for point in edge_points]
        z_values = [point[2] for point in edge_points]
        faces.append(
            {
                "face": face,
                "reference": safe_get(face, "Reference"),
                "surface_type": safe_get(face, "Surface3DType"),
                "is_planar": is_planar,
                "anchor_point": list(edge_points[0]),
                "x_min": min(x_values),
                "x_max": max(x_values),
                "x_mid": sum(x_values) / float(len(x_values)),
                "y_mid": sum(y_values) / float(len(y_values)),
                "z_mid": sum(z_values) / float(len(z_values)),
            }
        )
    if not faces:
        raise RuntimeError("Failed to resolve reference faces on the source body")

    if selector_name == "side_face_1":
        candidates = [item for item in faces if item["is_planar"] and abs(float(item["x_max"]) - float(item["x_min"])) > 1e-6]
        if not candidates:
            raise RuntimeError("Failed to resolve polygon side faces on the source body")
        if target_origin is None:
            selected = candidates[0]
        else:
            selected = min(
                candidates,
                key=lambda item: (
                    abs(float(item["x_mid"]) - float(target_x or 0.0))
                    + abs(float(item["y_mid"]) - float(target_y or 0.0))
                    + abs(float(item["z_mid"]) - float(target_z or 0.0))
                ),
            )
    else:
        candidates = [item for item in faces if item["is_planar"] and abs(float(item["x_max"]) - float(item["x_min"])) <= 1e-6]
        if not candidates:
            raise RuntimeError("Failed to resolve polygon end faces on the source body")
        if target_x is None:
            if selector_name == "start_face":
                selected = min(candidates, key=lambda item: item["x_mid"])
            else:
                selected = max(candidates, key=lambda item: item["x_mid"])
        else:
            selected = min(candidates, key=lambda item: abs(float(item["x_mid"]) - target_x))

    return selected["face"], {
        "selector": selector_name,
        "target_origin": target_origin,
        "candidate_count": len(faces),
        "selected_reference": selected["reference"],
        "selected_anchor_point": selected["anchor_point"],
        "selected_x_range": [selected["x_min"], selected["x_max"]],
        "selected_mid_point": [selected["x_mid"], selected["y_mid"], selected["z_mid"]],
        "selected_surface_type": selected["surface_type"],
        "body_source": body_source,
    }


def _select_flat_step_face(feature_object, selector, feature_preview=None):
    try:
        selector_name = _normalize_flat_step_face_selector(selector)
    except RuntimeError as exc:
        raise RuntimeError(
            "Unsupported flat_step face selector: %s; available selectors: %s"
            % (
                selector,
                _format_flat_step_selector_choices(_list_flat_step_selector_choices(feature_preview)),
            )
        ) from exc

    selector_points = {}
    preview_payload = feature_preview or {}
    preview_selectors = preview_payload.get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    anchors = ((preview_payload.get("interface") or {}).get("anchors") or {})
    anchor_selectors = anchors.get("selector_points") or {}
    if isinstance(anchor_selectors, dict):
        selector_points.update(anchor_selectors)
    target_origin = selector_points.get(selector_name)
    target_x = float(target_origin[0]) if isinstance(target_origin, (list, tuple)) and len(target_origin) >= 1 else None
    target_y = float(target_origin[1]) if isinstance(target_origin, (list, tuple)) and len(target_origin) >= 2 else None
    target_z = float(target_origin[2]) if isinstance(target_origin, (list, tuple)) and len(target_origin) >= 3 else 0.0

    objects, body_source = _get_feature_face_model_objects(feature_object)
    faces = []
    for item in _ensure_dispatch_sequence(objects):
        face = _cast_to_com_interface(item, "IFace")
        if face is None:
            continue
        is_planar = bool(safe_get(face, "IsPlanar", False))
        edges = _ensure_dispatch_sequence(safe_get(face, "LimitingEdges"))
        if not edges:
            continue
        edge_points = []
        for edge in edges:
            for at in (True, False):
                try:
                    point = edge.GetPoint(at)
                except Exception:
                    continue
                if not isinstance(point, tuple) or len(point) < 4 or not point[0]:
                    continue
                edge_points.append([float(point[1]), float(point[2]), float(point[3])])
        if not edge_points:
            continue
        x_values = [point[0] for point in edge_points]
        y_values = [point[1] for point in edge_points]
        z_values = [point[2] for point in edge_points]
        faces.append(
            {
                "face": face,
                "reference": safe_get(face, "Reference"),
                "surface_type": safe_get(face, "Surface3DType"),
                "is_planar": is_planar,
                "anchor_point": list(edge_points[0]),
                "x_min": min(x_values),
                "x_max": max(x_values),
                "x_mid": sum(x_values) / float(len(x_values)),
                "y_mid": sum(y_values) / float(len(y_values)),
                "z_mid": sum(z_values) / float(len(z_values)),
            }
        )
    if not faces:
        raise RuntimeError("Failed to resolve reference faces on the source body")

    if selector_name in ("flat_1_face", "flat_2_face"):
        candidates = [item for item in faces if item["is_planar"] and abs(float(item["x_max"]) - float(item["x_min"])) > 1e-6]
        if not candidates:
            raise RuntimeError("Failed to resolve flat faces on the source body")
        if target_origin is None:
            selected = candidates[0]
        else:
            selected = min(
                candidates,
                key=lambda item: (
                    abs(float(item["x_mid"]) - float(target_x or 0.0))
                    + abs(float(item["y_mid"]) - float(target_y or 0.0))
                    + abs(float(item["z_mid"]) - float(target_z or 0.0))
                ),
            )
    else:
        candidates = [item for item in faces if item["is_planar"] and abs(float(item["x_max"]) - float(item["x_min"])) <= 1e-6]
        if not candidates:
            raise RuntimeError("Failed to resolve flat-step end faces on the source body")
        if target_x is None:
            if selector_name == "start_face":
                selected = min(candidates, key=lambda item: item["x_mid"])
            else:
                selected = max(candidates, key=lambda item: item["x_mid"])
        else:
            selected = min(candidates, key=lambda item: abs(float(item["x_mid"]) - target_x))

    return selected["face"], {
        "selector": selector_name,
        "target_origin": target_origin,
        "candidate_count": len(faces),
        "selected_reference": selected["reference"],
        "selected_anchor_point": selected["anchor_point"],
        "selected_x_range": [selected["x_min"], selected["x_max"]],
        "selected_mid_point": [selected["x_mid"], selected["y_mid"], selected["z_mid"]],
        "selected_surface_type": selected["surface_type"],
        "body_source": body_source,
    }


def _select_face_ring_groove_face(feature_object, selector, feature_preview=None):
    try:
        selector_name = _normalize_face_ring_groove_face_selector(selector)
    except RuntimeError as exc:
        raise RuntimeError(
            "Unsupported face_ring_groove face selector: %s; available selectors: %s"
            % (
                selector,
                _format_face_ring_groove_selector_choices(_list_face_ring_groove_selector_choices()),
            )
        ) from exc

    selector_points = {}
    preview_selectors = (feature_preview or {}).get("selectors") or {}
    if isinstance(preview_selectors, dict):
        selector_points.update(preview_selectors)
    anchors = (((feature_preview or {}).get("interface") or {}).get("anchors") or {})
    anchor_selectors = anchors.get("selector_points") or {}
    if isinstance(anchor_selectors, dict):
        selector_points.update(anchor_selectors)
    target_origin = selector_points.get(selector_name)
    target_x = float(target_origin[0]) if isinstance(target_origin, (list, tuple)) and len(target_origin) >= 1 else None
    target_radius = float(target_origin[1]) if isinstance(target_origin, (list, tuple)) and len(target_origin) >= 2 else None

    objects, body_source = _get_feature_face_model_objects(feature_object)
    faces = []
    for item in _ensure_dispatch_sequence(objects):
        face = _cast_to_com_interface(item, "IFace")
        if face is None:
            continue
        is_planar = bool(safe_get(face, "IsPlanar", False))
        edges = _ensure_dispatch_sequence(safe_get(face, "LimitingEdges"))
        if not edges:
            continue
        edge_points = []
        for edge in edges:
            for at in (True, False):
                try:
                    point = edge.GetPoint(at)
                except Exception:
                    continue
                if not isinstance(point, tuple) or len(point) < 4 or not point[0]:
                    continue
                edge_points.append([float(point[1]), float(point[2]), float(point[3])])
        if not edge_points:
            continue
        x_values = [point[0] for point in edge_points]
        radii = [(point[1] ** 2 + point[2] ** 2) ** 0.5 for point in edge_points]
        faces.append(
            {
                "face": face,
                "reference": safe_get(face, "Reference"),
                "surface_type": safe_get(face, "Surface3DType"),
                "is_planar": is_planar,
                "anchor_point": list(edge_points[0]),
                "x_min": min(x_values),
                "x_max": max(x_values),
                "x_mid": (min(x_values) + max(x_values)) / 2.0,
                "radius_min": min(radii) if radii else 0.0,
                "radius_max": max(radii) if radii else 0.0,
                "radius_mid": ((min(radii) + max(radii)) / 2.0) if radii else 0.0,
            }
        )
    if not faces:
        raise RuntimeError("Failed to resolve reference faces on the source body")

    if selector_name == "bottom_face":
        candidates = [item for item in faces if item["is_planar"]]
        if not candidates:
            raise RuntimeError("Failed to resolve groove bottom face on the source body")
        selected = min(
            candidates,
            key=lambda item: (
                abs(float(item["x_mid"]) - float(target_x or 0.0)),
                abs(float(item["radius_mid"]) - float(target_radius or 0.0)),
            ),
        )
    else:
        candidates = [item for item in faces if not item["is_planar"]]
        if not candidates:
            raise RuntimeError("Failed to resolve groove wall faces on the source body")
        selected = min(
            candidates,
            key=lambda item: (
                abs(float(item["radius_mid"]) - float(target_radius or 0.0)),
                abs(float(item["x_mid"]) - float(target_x or 0.0)),
            ),
        )

    return selected["face"], {
        "selector": selector_name,
        "candidate_count": len(faces),
        "selected_reference": selected["reference"],
        "selected_anchor_point": selected["anchor_point"],
        "selected_x_range": [selected["x_min"], selected["x_max"]],
        "selected_radius_range": [selected["radius_min"], selected["radius_max"]],
        "selected_surface_type": selected["surface_type"],
        "selected_is_planar": selected["is_planar"],
        "body_source": body_source,
    }


def _normalize_revolved_feature_face_selector(source_scenario, selector):
    if source_scenario == "stepped_shaft":
        return _normalize_stepped_shaft_face_selector(selector)
    if source_scenario == "external_conical_step":
        return _normalize_external_conical_step_face_selector(selector)
    if source_scenario == "internal_conical_step":
        return _normalize_internal_conical_step_face_selector(selector)
    if source_scenario == "internal_cylindrical_step":
        return _normalize_internal_cylindrical_step_face_selector(selector)
    if source_scenario in ("external_polygonal_step", "internal_polygonal_step"):
        return _normalize_polygonal_step_face_selector(selector)
    if source_scenario in ("external_flat_step", "internal_flat_step"):
        return _normalize_flat_step_face_selector(selector)
    if source_scenario == "face_ring_groove":
        return _normalize_face_ring_groove_face_selector(selector)
    raise RuntimeError("Unsupported source_scenario for face selector: %s" % source_scenario)


def _select_revolved_feature_face(source_scenario, feature_object, selector, feature_preview=None):
    if source_scenario == "stepped_shaft":
        return _select_stepped_shaft_planar_face(feature_object, selector, feature_preview)
    if source_scenario == "external_conical_step":
        return _select_external_conical_step_face(feature_object, selector, feature_preview)
    if source_scenario == "internal_conical_step":
        return _select_internal_conical_step_face(feature_object, selector, feature_preview)
    if source_scenario == "internal_cylindrical_step":
        return _select_internal_cylindrical_step_face(feature_object, selector, feature_preview)
    if source_scenario in ("external_polygonal_step", "internal_polygonal_step"):
        return _select_polygonal_step_face(feature_object, selector, feature_preview)
    if source_scenario in ("external_flat_step", "internal_flat_step"):
        return _select_flat_step_face(feature_object, selector, feature_preview)
    if source_scenario == "face_ring_groove":
        return _select_face_ring_groove_face(feature_object, selector, feature_preview)
    raise RuntimeError("Unsupported source_scenario for face resolution: %s" % source_scenario)


def _revolved_feature_face_supports_lcs_object(source_scenario, selector):
    if source_scenario == "stepped_shaft":
        selector_info = _parse_stepped_shaft_face_selector(selector) or {}
        return selector_info.get("kind") != "step_outer_face"
    if source_scenario == "external_conical_step":
        return selector != "outer_face"
    if source_scenario == "internal_conical_step":
        return selector != "inner_face"
    if source_scenario == "internal_cylindrical_step":
        selector_info = _parse_internal_cylindrical_step_face_selector(selector) or {}
        return selector_info.get("kind") != "segment_face"
    if source_scenario in ("external_polygonal_step", "internal_polygonal_step"):
        return True
    if source_scenario in ("external_flat_step", "internal_flat_step"):
        return True
    if source_scenario == "face_ring_groove":
        return selector == "bottom_face"
    return False


def _create_local_coordinate_system(part, params):
    auxiliary = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    if auxiliary is None:
        raise RuntimeError("Part does not expose IAuxiliaryGeomContainer")
    systems = safe_get(auxiliary, "LocalCoordinateSystems")
    if systems is None:
        get_systems = safe_get(auxiliary, "GetLocalCoordinateSystems")
        if callable(get_systems):
            systems = get_systems()
    if systems is None:
        raise RuntimeError("Part does not expose LocalCoordinateSystems")
    raw = systems._oleobj_.InvokeTypes(2, 0, 1, (9, 0), ())
    if raw is None:
        raise RuntimeError("LocalCoordinateSystems.Add returned None")
    try:
        import win32com.client

        lcs = win32com.client.dynamic.Dispatch(raw)
    except Exception:
        lcs = raw
    lcs.Name = str(params.get("lcs_name") or "")

    mode = str(params.get("mode") or "global")
    reference_point = None
    association_object = None
    if mode == "point":
        reference_origin = params.get("reference_origin")
        if not isinstance(reference_origin, list) or len(reference_origin) != 3:
            raise RuntimeError("lcs point mode requires reference_origin")
        reference_point = _create_point3d(
            _cast_to_com_interface(part, "IModelContainer"),
            params.get("reference_name") or "PT1",
            reference_origin,
        )
        association_object = reference_point
        if not bool(lcs.SetAssociationObject(reference_point)):
            raise RuntimeError("SetAssociationObject(point) returned False")
    elif mode == "object":
        reference = params.get("reference") or {}
        association_object = _resolve_default_part_object(part, reference.get("system_object"))
        if not bool(lcs.SetAssociationObject(association_object)):
            raise RuntimeError("SetAssociationObject(object) returned False")

    origin = params.get("origin") or [0.0, 0.0, 0.0]
    if mode != "object":
        lcs.X = float(origin[0])
        lcs.Y = float(origin[1])
        lcs.Z = float(origin[2])

    rotation = params.get("rotation") or {}
    if any(abs(float(rotation.get(axis, 0.0))) > 1e-9 for axis in ("rx", "ry", "rz")):
        lcs.OrientationType = 1
        euler = lcs.LocalCSParameters
        euler.NutationAngle = float(rotation.get("rx", 0.0))
        euler.PrecessionAngle = float(rotation.get("ry", 0.0))
        euler.RotationAngle = float(rotation.get("rz", 0.0))

    if not lcs.Update():
        raise RuntimeError("LocalCoordinateSystem Update returned False")
    return lcs, reference_point, association_object


def _create_local_coordinate_system_on_point(part, name, reference_point, rotation=None):
    auxiliary = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    if auxiliary is None:
        raise RuntimeError("Part does not expose IAuxiliaryGeomContainer")
    systems = safe_get(auxiliary, "LocalCoordinateSystems")
    if systems is None:
        get_systems = safe_get(auxiliary, "GetLocalCoordinateSystems")
        if callable(get_systems):
            systems = get_systems()
    if systems is None:
        raise RuntimeError("Part does not expose LocalCoordinateSystems")
    raw = systems._oleobj_.InvokeTypes(2, 0, 1, (9, 0), ())
    if raw is None:
        raise RuntimeError("LocalCoordinateSystems.Add returned None")
    try:
        import win32com.client

        lcs = win32com.client.dynamic.Dispatch(raw)
    except Exception:
        lcs = raw
    lcs.Name = str(name or "")
    if not bool(lcs.SetAssociationObject(reference_point)):
        raise RuntimeError("SetAssociationObject(point) returned False")
    rotation_payload = rotation or {}
    if any(abs(float(rotation_payload.get(axis, 0.0))) > 1e-9 for axis in ("rx", "ry", "rz")):
        lcs.OrientationType = 1
        euler = lcs.LocalCSParameters
        euler.NutationAngle = float(rotation_payload.get("rx", 0.0))
        euler.PrecessionAngle = float(rotation_payload.get("ry", 0.0))
        euler.RotationAngle = float(rotation_payload.get("rz", 0.0))
    if not lcs.Update():
        raise RuntimeError("LocalCoordinateSystem Update returned False")
    return lcs


def _create_local_coordinate_system_on_point_oriented_by_object(
    part,
    name,
    reference_point,
    orientation_object,
    only_outer_contour=False
):
    auxiliary = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    if auxiliary is None:
        raise RuntimeError("Part does not expose IAuxiliaryGeomContainer")
    systems = safe_get(auxiliary, "LocalCoordinateSystems")
    if systems is None:
        get_systems = safe_get(auxiliary, "GetLocalCoordinateSystems")
        if callable(get_systems):
            systems = get_systems()
    if systems is None:
        raise RuntimeError("Part does not expose LocalCoordinateSystems")
    raw = systems._oleobj_.InvokeTypes(2, 0, 1, (9, 0), ())
    if raw is None:
        raise RuntimeError("LocalCoordinateSystems.Add returned None")
    try:
        import win32com.client

        lcs = win32com.client.dynamic.Dispatch(raw)
    except Exception:
        lcs = raw
    lcs.Name = str(name or "")
    if not bool(lcs.SetAssociationObject(reference_point)):
        raise RuntimeError("SetAssociationObject(point) returned False for object-oriented LCS")
    lcs.OrientationType = 2
    parameters = safe_get(lcs, "LocalCSParameters")
    set_orientation_object = safe_get(parameters, "SetOrientationObject")
    if not callable(set_orientation_object):
        raise RuntimeError("LocalCS object parameters do not expose SetOrientationObject")
    if not bool(set_orientation_object(orientation_object)):
        raise RuntimeError("SetOrientationObject(object) returned False for point-oriented LCS")
    if only_outer_contour:
        try:
            if parameters is not None and hasattr(parameters, "OnlyOuterContour"):
                parameters.OnlyOuterContour = True
        except Exception:
            pass
    if not lcs.Update():
        raise RuntimeError("LocalCoordinateSystem Update returned False")
    return lcs


def _create_local_coordinate_system_on_object(part, model_container, name, association_object, *, only_outer_contour=False):
    auxiliary = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    if auxiliary is None:
        raise RuntimeError("Part does not expose IAuxiliaryGeomContainer")
    systems = safe_get(auxiliary, "LocalCoordinateSystems")
    if systems is None:
        get_systems = safe_get(auxiliary, "GetLocalCoordinateSystems")
        if callable(get_systems):
            systems = get_systems()
    if systems is None:
        raise RuntimeError("Part does not expose LocalCoordinateSystems")
    raw = systems._oleobj_.InvokeTypes(2, 0, 1, (9, 0), ())
    if raw is None:
        raise RuntimeError("LocalCoordinateSystems.Add returned None")
    try:
        import win32com.client

        lcs = win32com.client.dynamic.Dispatch(raw)
    except Exception:
        lcs = raw
    lcs.Name = str(name or "")
    reference_point = _create_point3d_center_on_object(model_container, "%s_CENTER" % (name or "LCS1"), association_object)
    if not bool(lcs.SetAssociationObject(reference_point)):
        raise RuntimeError("SetAssociationObject(point) returned False for object-based LCS")
    lcs.OrientationType = 2
    parameters = safe_get(lcs, "LocalCSParameters")
    set_orientation_object = safe_get(parameters, "SetOrientationObject")
    if not callable(set_orientation_object):
        raise RuntimeError("LocalCS object parameters do not expose SetOrientationObject")
    if not bool(set_orientation_object(association_object)):
        raise RuntimeError("SetOrientationObject(object) returned False")
    if only_outer_contour:
        try:
            if parameters is not None and hasattr(parameters, "OnlyOuterContour"):
                parameters.OnlyOuterContour = True
        except Exception:
            pass
    if not lcs.Update():
        raise RuntimeError("LocalCoordinateSystem Update returned False")
    return lcs, reference_point


def _resolve_default_lcs_object(lcs, system_object):
    normalized = str(system_object or "").strip().lower().replace("-", "_")
    default_object_ids = {
        "xoy_plane": 1,
        "xoz_plane": 2,
        "yoz_plane": 3,
        "origin": 4,
    }
    object_id = default_object_ids.get(normalized)
    if object_id is None:
        raise RuntimeError("Unsupported default LCS object: %s" % system_object)
    getter = safe_get(lcs, "DefaultObject")
    if not callable(getter):
        getter = safe_get(lcs, "GetDefaultObject")
    if not callable(getter):
        raise RuntimeError("LCS does not expose DefaultObject/GetDefaultObject")
    resolved = getter(object_id)
    if resolved is None:
        raise RuntimeError("Failed to resolve default LCS object %s" % normalized)
    return resolved


def _normalize_runtime_output_key(scenario, output_key):
    scenario_name = str(scenario or "").strip().lower()
    key = str(output_key or "").strip().lower().replace("-", "_")
    if scenario_name == "stepped_shaft":
        if key in ("body", "sketch", "axis"):
            return key
        return _normalize_stepped_shaft_face_selector(key)
    if scenario_name == "external_conical_step":
        if key in ("body", "sketch", "axis"):
            return key
        return _normalize_external_conical_step_face_selector(key)
    if scenario_name == "internal_conical_step":
        if key in ("body", "sketch", "axis"):
            return key
        return _normalize_internal_conical_step_face_selector(key)
    if scenario_name == "internal_cylindrical_step":
        if key in ("body", "sketch", "axis"):
            return key
        return _normalize_internal_cylindrical_step_face_selector(key)
    if scenario_name in ("external_polygonal_step", "internal_polygonal_step"):
        if key in ("body", "sketch"):
            return key
        return _normalize_polygonal_step_face_selector(key)
    if scenario_name in ("external_flat_step", "internal_flat_step"):
        if key in ("body", "sketch"):
            return key
        return _normalize_flat_step_face_selector(key)
    if scenario_name in ("external_helical_thread", "internal_helical_thread"):
        aliases = {
            "body": "body",
            "thread": "thread",
            "thread_feature": "thread",
            "spiral": "spiral",
            "path": "spiral",
            "profile_sketch": "profile_sketch",
            "thread_profile": "profile_sketch",
            "base_face": "base_face",
            "source_face": "base_face",
            "start_face": "start_face",
            "entry_face": "start_face",
            "end_face": "end_face",
            "exit_face": "end_face",
        }
        normalized = aliases.get(key, key)
        if normalized not in ("body", "thread", "spiral", "profile_sketch", "base_face", "start_face", "end_face"):
            raise RuntimeError("Unsupported helical_thread output: %s" % output_key)
        return normalized
    if scenario_name in ("external_threaded_step", "internal_threaded_step"):
        aliases = {
            "body": "body",
            "thread": "thread",
            "base_face": "base_face",
            "thread_face": "base_face",
            "source_face": "base_face",
            "start_border": "start_border",
            "start_face": "start_border",
            "end_border": "end_border",
            "end_face": "end_border",
        }
        normalized = aliases.get(key, key)
        if normalized not in ("body", "thread", "base_face", "start_border", "end_border"):
            raise RuntimeError("Unsupported threaded_step output: %s" % output_key)
        return normalized
    if scenario_name == "point":
        aliases = {
            "point": "point",
            "origin": "point",
            "reference_point": "point",
        }
        normalized = aliases.get(key, key)
        if normalized != "point":
            raise RuntimeError("Unsupported point output: %s" % output_key)
        return normalized
    if scenario_name == "lcs":
        aliases = {
            "lcs": "lcs",
            "csys": "lcs",
            "coordinate_system": "lcs",
            "placement_ref": "lcs",
        }
        normalized = aliases.get(key, key)
        if normalized != "lcs":
            raise RuntimeError("Unsupported lcs output: %s" % output_key)
        return normalized
    return key


def _resolve_runtime_workflow_output(runtime_objects, operation_id, output_key):
    target = runtime_objects.get(operation_id)
    if target is None:
        available_operations = ", ".join(sorted(runtime_objects.keys())) or "<none>"
        raise RuntimeError(
            "Workflow output reference %s.%s does not resolve to an operation; available operations: %s"
            % (operation_id, output_key, available_operations)
        )

    scenario = str(target.get("scenario") or "")
    available_outputs = sorted(
        str(name).strip()
        for name in (((target.get("preview") or {}).get("interface") or {}).get("outputs") or {}).keys()
        if str(name).strip()
    )
    available_outputs_text = ", ".join(available_outputs) if available_outputs else "<none>"
    try:
        normalized_output = _normalize_runtime_output_key(scenario, output_key)
    except Exception as exc:
        raise RuntimeError(
            "Workflow operation %s (scenario=%s) does not export output %s; available outputs: %s"
            % (operation_id, scenario, output_key, available_outputs_text)
        ) from exc

    if scenario in ("external_helical_thread", "internal_helical_thread"):
        feature = target.get("feature") or {}
        if normalized_output == "thread":
            thread = feature.get("thread")
            if thread is None:
                raise RuntimeError(
                    "Workflow output %s.thread is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "feature", "object": thread}
        if normalized_output == "spiral":
            spiral = feature.get("spiral")
            if spiral is None:
                raise RuntimeError(
                    "Workflow output %s.spiral is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "curve", "object": spiral}
        if normalized_output == "profile_sketch":
            sketch = feature.get("profile_sketch")
            if sketch is None:
                raise RuntimeError(
                    "Workflow output %s.profile_sketch is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "sketch", "object": sketch}
        if normalized_output == "body":
            source_feature = feature.get("source_feature")
            source_scenario = feature.get("source_scenario")
            if source_feature is None or not source_scenario:
                raise RuntimeError(
                    "Workflow output %s.body is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {
                "type": "body",
                "object": _get_source_feature_reference_object(source_scenario, source_feature),
            }
        if normalized_output == "base_face":
            face = feature.get("base_face")
            if face is None:
                raise RuntimeError(
                    "Workflow output %s.base_face is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {
                "type": "face",
                "object": face,
                "selector": str((target.get("params") or {}).get("source_selector") or "base_face"),
                "resolution_report": feature.get("base_face_report") or {},
            }
        if normalized_output == "start_face":
            face = feature.get("start_face")
            if face is None:
                raise RuntimeError(
                    "Workflow output %s.start_face is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {
                "type": "face",
                "object": face,
                "selector": str((target.get("params") or {}).get("start_selector") or "start_face"),
                "resolution_report": feature.get("start_face_report") or {},
            }
        face = feature.get("end_face")
        if face is None:
            raise RuntimeError(
                "Workflow output %s.end_face is unavailable; operation scenario=%s; available outputs: %s"
                % (operation_id, scenario, available_outputs_text)
            )
        return {
            "type": "face",
            "object": face,
            "selector": str((target.get("params") or {}).get("end_selector") or "end_face"),
            "resolution_report": feature.get("end_face_report") or {},
        }

    if scenario in ("external_threaded_step", "internal_threaded_step"):
        feature = target.get("feature") or {}
        if normalized_output == "thread":
            thread = feature.get("thread")
            if thread is None:
                raise RuntimeError(
                    "Workflow output %s.thread is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "thread", "object": thread}
        if normalized_output == "body":
            source_feature = feature.get("source_feature")
            source_scenario = feature.get("source_scenario")
            if source_feature is None or not source_scenario:
                raise RuntimeError(
                    "Workflow output %s.body is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {
                "type": "body",
                "object": _get_source_feature_reference_object(source_scenario, source_feature),
            }
        if normalized_output == "base_face":
            face = feature.get("base_face")
            if face is None:
                raise RuntimeError(
                    "Workflow output %s.base_face is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {
                "type": "face",
                "object": face,
                "selector": str((target.get("params") or {}).get("source_selector") or "base_face"),
                "resolution_report": feature.get("base_face_report") or {},
            }
        if normalized_output == "start_border":
            face = feature.get("start_border")
            if face is None:
                raise RuntimeError(
                    "Workflow output %s.start_border is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {
                "type": "face",
                "object": face,
                "selector": str((target.get("params") or {}).get("start_selector") or "start_border"),
                "resolution_report": feature.get("start_border_report") or {},
            }
        face = feature.get("end_border")
        if face is None:
            raise RuntimeError(
                "Workflow output %s.end_border is unavailable; operation scenario=%s; available outputs: %s"
                % (operation_id, scenario, available_outputs_text)
            )
        return {
            "type": "face",
            "object": face,
            "selector": str((target.get("params") or {}).get("end_selector") or "end_border"),
            "resolution_report": feature.get("end_border_report") or {},
        }

    if scenario == "point":
        if normalized_output != "point" or target.get("point") is None:
            raise RuntimeError(
                "Workflow output %s.%s does not resolve to a point; operation scenario=%s; available outputs: %s"
                % (operation_id, normalized_output, scenario, available_outputs_text)
            )
        point = target["point"]
        return {
            "type": "point",
            "object": point,
            "name": safe_get(point, "Name"),
            "origin": [safe_get(point, "X", 0.0), safe_get(point, "Y", 0.0), safe_get(point, "Z", 0.0)],
        }

    if scenario == "lcs":
        if normalized_output != "lcs" or target.get("lcs") is None:
            raise RuntimeError(
                "Workflow output %s.%s does not resolve to an LCS; operation scenario=%s; available outputs: %s"
                % (operation_id, normalized_output, scenario, available_outputs_text)
            )
        lcs = target["lcs"]
        return {
            "type": "lcs",
            "object": lcs,
            "name": safe_get(lcs, "Name"),
            "origin": [safe_get(lcs, "X", 0.0), safe_get(lcs, "Y", 0.0), safe_get(lcs, "Z", 0.0)],
        }

    if scenario == "stepped_shaft":
        feature = target.get("feature") or {}
        if normalized_output == "body":
            rotated = feature.get("rotated")
            if rotated is None:
                raise RuntimeError(
                    "Workflow output %s.body is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "body", "object": rotated}
        if normalized_output == "sketch":
            sketch = feature.get("sketch")
            if sketch is None:
                raise RuntimeError(
                    "Workflow output %s.sketch is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "sketch", "object": sketch}
        if normalized_output == "axis":
            axis = feature.get("axis")
            if axis is None:
                raise RuntimeError(
                    "Workflow output %s.axis is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "axis", "object": axis}
        try:
            face, resolution_report = _select_stepped_shaft_planar_face(feature.get("rotated"), normalized_output, target.get("preview"))
        except RuntimeError as exc:
            raise RuntimeError(
                "Workflow operation %s (scenario=%s) failed to resolve selector %s; available selectors: %s"
                % (
                    operation_id,
                    scenario,
                    normalized_output,
                    _format_stepped_shaft_selector_choices(_list_stepped_shaft_selector_choices(target.get("preview"))),
                )
            ) from exc
        return {
            "type": "face",
            "object": face,
            "selector": normalized_output,
            "resolution_report": resolution_report,
        }

    if scenario == "external_conical_step":
        feature = target.get("feature") or {}
        if normalized_output == "body":
            rotated = feature.get("rotated")
            if rotated is None:
                raise RuntimeError(
                    "Workflow output %s.body is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "body", "object": rotated}
        if normalized_output == "sketch":
            sketch = feature.get("sketch")
            if sketch is None:
                raise RuntimeError(
                    "Workflow output %s.sketch is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "sketch", "object": sketch}
        if normalized_output == "axis":
            axis = feature.get("axis")
            if axis is None:
                raise RuntimeError(
                    "Workflow output %s.axis is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "axis", "object": axis}
        try:
            face, resolution_report = _select_external_conical_step_face(feature.get("rotated"), normalized_output, target.get("preview"))
        except RuntimeError as exc:
            raise RuntimeError(
                "Workflow operation %s (scenario=%s) failed to resolve selector %s; available selectors: %s"
                % (
                    operation_id,
                    scenario,
                    normalized_output,
                    _format_external_conical_step_selector_choices(_list_external_conical_step_selector_choices()),
                )
            ) from exc
        return {
            "type": "face",
            "object": face,
            "selector": normalized_output,
            "resolution_report": resolution_report,
        }

    if scenario == "internal_conical_step":
        feature = target.get("feature") or {}
        if normalized_output == "body":
            rotated = feature.get("rotated")
            if rotated is None:
                raise RuntimeError(
                    "Workflow output %s.body is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "body", "object": rotated}
        if normalized_output == "sketch":
            sketch = feature.get("sketch")
            if sketch is None:
                raise RuntimeError(
                    "Workflow output %s.sketch is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "sketch", "object": sketch}
        if normalized_output == "axis":
            axis = feature.get("axis")
            if axis is None:
                raise RuntimeError(
                    "Workflow output %s.axis is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "axis", "object": axis}
        try:
            face, resolution_report = _select_internal_conical_step_face(feature.get("rotated"), normalized_output, target.get("preview"))
        except RuntimeError as exc:
            raise RuntimeError(
                "Workflow operation %s (scenario=%s) failed to resolve selector %s; available selectors: %s"
                % (
                    operation_id,
                    scenario,
                    normalized_output,
                    _format_internal_conical_step_selector_choices(_list_internal_conical_step_selector_choices()),
                )
            ) from exc
        return {
            "type": "face",
            "object": face,
            "selector": normalized_output,
            "resolution_report": resolution_report,
        }

    if scenario == "internal_cylindrical_step":
        feature = target.get("feature") or {}
        if normalized_output == "body":
            rotated = feature.get("rotated")
            if rotated is None:
                raise RuntimeError(
                    "Workflow output %s.body is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "body", "object": rotated}
        if normalized_output == "sketch":
            sketch = feature.get("sketch")
            if sketch is None:
                raise RuntimeError(
                    "Workflow output %s.sketch is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "sketch", "object": sketch}
        if normalized_output == "axis":
            axis = feature.get("axis")
            if axis is None:
                raise RuntimeError(
                    "Workflow output %s.axis is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "axis", "object": axis}
        try:
            face, resolution_report = _select_internal_cylindrical_step_face(feature.get("rotated"), normalized_output, target.get("preview"))
        except RuntimeError as exc:
            raise RuntimeError(
                "Workflow operation %s (scenario=%s) failed to resolve selector %s; available selectors: %s"
                % (
                    operation_id,
                    scenario,
                    normalized_output,
                    _format_internal_cylindrical_step_selector_choices(_list_internal_cylindrical_step_selector_choices()),
                )
            ) from exc
        return {
            "type": "face",
            "object": face,
            "selector": normalized_output,
            "resolution_report": resolution_report,
        }

    if scenario in ("external_polygonal_step", "internal_polygonal_step"):
        feature = target.get("feature") or {}
        if normalized_output == "body":
            extrusion = feature.get("extrusion")
            if extrusion is None:
                raise RuntimeError(
                    "Workflow output %s.body is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "body", "object": extrusion}
        if normalized_output == "sketch":
            sketch = feature.get("sketch")
            if sketch is None:
                raise RuntimeError(
                    "Workflow output %s.sketch is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "sketch", "object": sketch}
        try:
            face, resolution_report = _select_polygonal_step_face(feature.get("extrusion"), normalized_output, target.get("preview"))
        except RuntimeError as exc:
            raise RuntimeError(
                "Workflow operation %s (scenario=%s) failed to resolve selector %s; available selectors: %s"
                % (
                    operation_id,
                    scenario,
                    normalized_output,
                    _format_polygonal_step_selector_choices(_list_polygonal_step_selector_choices(target.get("preview"))),
                )
            ) from exc
        return {
            "type": "face",
            "object": face,
            "selector": normalized_output,
            "resolution_report": resolution_report,
        }

    if scenario in ("external_flat_step", "internal_flat_step"):
        feature = target.get("feature") or {}
        if normalized_output == "body":
            extrusion = feature.get("extrusion")
            if extrusion is None:
                raise RuntimeError(
                    "Workflow output %s.body is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "body", "object": extrusion}
        if normalized_output == "sketch":
            sketch = feature.get("sketch")
            if sketch is None:
                raise RuntimeError(
                    "Workflow output %s.sketch is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "sketch", "object": sketch}
        try:
            face, resolution_report = _select_flat_step_face(feature.get("extrusion"), normalized_output, target.get("preview"))
        except RuntimeError as exc:
            raise RuntimeError(
                "Workflow operation %s (scenario=%s) failed to resolve selector %s; available selectors: %s"
                % (
                    operation_id,
                    scenario,
                    normalized_output,
                    _format_flat_step_selector_choices(_list_flat_step_selector_choices(target.get("preview"))),
                )
            ) from exc
        return {
            "type": "face",
            "object": face,
            "selector": normalized_output,
            "resolution_report": resolution_report,
        }

    if scenario == "face_ring_groove":
        feature = target.get("feature") or {}
        if normalized_output == "body":
            rotated = feature.get("rotated")
            if rotated is None:
                raise RuntimeError(
                    "Workflow output %s.body is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "body", "object": rotated}
        if normalized_output == "sketch":
            sketch = feature.get("sketch")
            if sketch is None:
                raise RuntimeError(
                    "Workflow output %s.sketch is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "sketch", "object": sketch}
        if normalized_output == "axis":
            axis = feature.get("axis")
            if axis is None:
                raise RuntimeError(
                    "Workflow output %s.axis is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "axis", "object": axis}
        try:
            face, resolution_report = _select_face_ring_groove_face(feature.get("rotated"), normalized_output, target.get("preview"))
        except RuntimeError as exc:
            raise RuntimeError(
                "Workflow operation %s (scenario=%s) failed to resolve selector %s; available selectors: %s"
                % (
                    operation_id,
                    scenario,
                    normalized_output,
                    _format_face_ring_groove_selector_choices(_list_face_ring_groove_selector_choices()),
                )
            ) from exc
        return {
            "type": "face",
            "object": face,
            "selector": normalized_output,
            "resolution_report": resolution_report,
        }

    if scenario == "bolt_circle_holes":
        feature = target.get("feature") or {}
        if normalized_output == "body":
            pattern = feature.get("pattern")
            if pattern is None:
                raise RuntimeError(
                    "Workflow output %s.body is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "body", "object": pattern}
        if normalized_output == "axis":
            axis = feature.get("pattern_axis")
            if axis is None:
                raise RuntimeError(
                    "Workflow output %s.axis is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {"type": "axis", "object": axis}
        if normalized_output == "first_hole_center":
            point = feature.get("first_hole_center")
            if point is None:
                raise RuntimeError(
                    "Workflow output %s.first_hole_center is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {
                "type": "point",
                "object": point,
                "origin": [safe_get(point, "X", 0.0), safe_get(point, "Y", 0.0), safe_get(point, "Z", 0.0)],
            }
        if normalized_output == "first_hole_lcs":
            lcs = feature.get("first_hole_lcs")
            if lcs is None:
                raise RuntimeError(
                    "Workflow output %s.first_hole_lcs is unavailable; operation scenario=%s; available outputs: %s"
                    % (operation_id, scenario, available_outputs_text)
                )
            return {
                "type": "lcs",
                "object": lcs,
                "origin": [safe_get(lcs, "X", 0.0), safe_get(lcs, "Y", 0.0), safe_get(lcs, "Z", 0.0)],
            }

    raise RuntimeError(
        "Workflow output resolution is unsupported for scenario=%s on operation %s; available outputs: %s"
        % (scenario, operation_id, available_outputs_text)
    )


def _extract_runtime_output_reference(reference):
    if isinstance(reference, str):
        token = str(reference).strip()
        if not token:
            return None
        if "." not in token:
            return token, None
        operation_id, output_key = token.split(".", 1)
        return operation_id.strip(), (output_key.strip() or None)
    if not isinstance(reference, dict):
        return None
    token = reference.get("output_ref") or reference.get("token") or reference.get("ref")
    if token not in (None, ""):
        return _extract_runtime_output_reference(token)
    operation_id = reference.get("operation") or reference.get("operation_id") or reference.get("workflow_operation")
    if operation_id in (None, ""):
        return None
    output_key = reference.get("output") or reference.get("output_name")
    return str(operation_id).strip(), (str(output_key).strip() if output_key not in (None, "") else None)


def _looks_like_runtime_output_reference(reference):
    if isinstance(reference, str):
        return bool(str(reference).strip())
    if not isinstance(reference, dict):
        return False
    for key in (
        "output_ref",
        "token",
        "ref",
        "operation",
        "operation_id",
        "workflow_operation",
        "output",
        "output_name",
    ):
        if reference.get(key) not in (None, ""):
            return True
    return False


def _resolve_runtime_output_reference(runtime_objects, reference, default_output=None, context_label=None):
    extracted = _extract_runtime_output_reference(reference)
    if extracted is None:
        if _looks_like_runtime_output_reference(reference):
            raise RuntimeError(
                "%s must be a workflow output reference like op.output or {ref: 'op.output'}; got %r"
                % (context_label or "Workflow reference", reference)
            )
        return None
    operation_id, output_key = extracted
    normalized_output = output_key or default_output or "result"
    resolved = _resolve_runtime_workflow_output(runtime_objects, operation_id, normalized_output)
    payload = dict(resolved)
    payload["operation_id"] = operation_id
    payload["output_key"] = normalized_output
    return payload


def _serialize_runtime_workflow_output(resolved_output):
    if not isinstance(resolved_output, dict):
        return {}
    payload = {
        "type": resolved_output.get("type"),
        "name": resolved_output.get("name"),
        "origin": resolved_output.get("origin"),
        "selector": resolved_output.get("selector"),
    }
    return dict((key, value) for key, value in payload.items() if value not in (None, ""))


def _resolve_runtime_workflow_exports(exports_payload, runtime_objects):
    exports = {}
    for index, export in enumerate(exports_payload or []):
        export_name = str((export or {}).get("name") or "").strip()
        operation_id = str((export or {}).get("operation_id") or "").strip()
        output_key = str((export or {}).get("output_key") or "").strip()
        if not export_name or not operation_id or not output_key:
            continue
        try:
            resolved_output = _resolve_runtime_workflow_output(runtime_objects, operation_id, output_key)
        except RuntimeError as exc:
            raise RuntimeError(
                "Workflow export %s (exports[%s] -> %s.%s) failed: %s"
                % (export_name, index, operation_id, output_key, exc)
            ) from exc
        item = _serialize_runtime_workflow_output(resolved_output)
        item["token"] = "%s.%s" % (operation_id, output_key)
        exports[export_name] = item
    return exports


def _execute_workflow_operation(part, model_container, operation, runtime_objects, steps_report):
    operation_id = str(operation.get("id") or "")
    scenario = str(operation.get("scenario") or "")
    params = dict(operation.get("params") or {})
    preview = operation.get("preview") or {}
    bindings = operation.get("bindings") or {}

    if scenario in ("stepped_shaft", "external_conical_step", "internal_conical_step", "internal_cylindrical_step", "external_polygonal_step", "internal_polygonal_step", "external_flat_step", "internal_flat_step", "external_helical_thread", "internal_helical_thread", "external_threaded_step", "internal_threaded_step", "face_ring_groove", "bolt_circle_holes"):
        coordinate_system = None
        placement = params.get("placement") or {}
        base_reference = ((placement.get("base") or placement).get("reference") or (placement.get("base") or placement).get("ref") or placement.get("reference") or placement.get("ref"))
        resolved_output = _resolve_runtime_output_reference(
            runtime_objects,
            base_reference,
            default_output="lcs",
            context_label="Workflow placement reference on operation %s" % operation_id,
        )
        if resolved_output is None:
            placement_operation = bindings.get("placement_operation")
            if placement_operation:
                placement_output = bindings.get("placement_output") or "lcs"
                resolved_output = _resolve_runtime_workflow_output(runtime_objects, placement_operation, placement_output)
        if resolved_output is not None:
            if resolved_output.get("type") != "lcs":
                raise RuntimeError(
                    "Workflow placement reference %s.%s does not resolve to an LCS"
                    % (resolved_output.get("operation_id"), resolved_output.get("output_key"))
                )
            coordinate_system = resolved_output["object"]
        if scenario == "stepped_shaft":
            feature = _build_stepped_shaft_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
            )
        elif scenario == "external_conical_step":
            feature = _build_external_conical_step_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
            )
        elif scenario == "internal_conical_step":
            feature = _build_internal_conical_step_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
                require_source=False,
            )
        elif scenario == "internal_cylindrical_step":
            feature = _build_internal_cylindrical_step_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
                require_source=False,
            )
        elif scenario == "external_polygonal_step":
            feature = _build_external_polygonal_step_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
            )
        elif scenario == "internal_polygonal_step":
            feature = _build_internal_polygonal_step_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
                require_source=False,
            )
        elif scenario == "external_flat_step":
            feature = _build_external_flat_step_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
            )
        elif scenario == "internal_flat_step":
            feature = _build_internal_flat_step_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
                require_source=False,
            )
        elif scenario == "external_helical_thread":
            feature = _build_external_helical_thread_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
            )
        elif scenario == "internal_helical_thread":
            feature = _build_internal_helical_thread_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
            )
        elif scenario == "external_threaded_step":
            feature = _build_external_threaded_step_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
            )
        elif scenario == "internal_threaded_step":
            feature = _build_internal_threaded_step_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
            )
        elif scenario == "face_ring_groove":
            feature = _build_face_ring_groove_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
                require_source=False,
            )
        else:
            feature = _build_bolt_circle_holes_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
                require_source=False,
            )
        runtime_objects[operation_id] = {
            "scenario": scenario,
            "feature": feature,
            "preview": preview,
            "params": params,
        }
        steps_report.append(
            {
                "step": "workflow_operation",
                "ok": True,
                "operation_id": operation_id,
                "scenario": scenario,
                "coordinate_system": safe_get(coordinate_system, "Name") if coordinate_system is not None else None,
            }
        )
        return

    if scenario == "point":
        variable_plan = list(params.get("variable_plan") or [])
        if variable_plan:
            steps_report.append(_apply_part_variables(part, variable_plan))
        mode = str(params.get("mode") or "global")
        reference_point = None
        association_object = None
        if mode == "center_of_object":
            reference = params.get("reference") or {}
            source_scenario = str(reference.get("source_scenario") or reference.get("scenario") or "stepped_shaft")
            selector = _normalize_revolved_feature_face_selector(
                source_scenario,
                reference.get("selector") or _default_revolved_feature_face_selector(source_scenario),
            )
            resolved_output = _resolve_runtime_output_reference(
                runtime_objects,
                reference,
                default_output=selector,
                context_label="Workflow point reference on operation %s" % operation_id,
            )
            if resolved_output is None:
                reference_operation = bindings.get("reference_operation")
                if reference_operation:
                    reference_output = bindings.get("reference_output") or selector
                    resolved_output = _resolve_runtime_workflow_output(runtime_objects, reference_operation, reference_output)
                    resolved_output = dict(resolved_output, operation_id=reference_operation, output_key=reference_output)
            if resolved_output is not None:
                if resolved_output.get("type") != "face":
                    raise RuntimeError(
                        "Workflow point reference %s.%s does not resolve to a face"
                        % (resolved_output.get("operation_id"), resolved_output.get("output_key"))
                    )
                association_object = resolved_output["object"]
                resolution_report = resolved_output.get("resolution_report") or {}
                steps_report.append(
                    {
                        "step": "resolve_reference_object",
                        "ok": True,
                        "operation_id": operation_id,
                        "reference_operation": resolved_output.get("operation_id"),
                        "reference_output": resolved_output.get("output_key"),
                        "selector_report": resolution_report,
                    }
                )
            else:
                source_preview = reference.get("source_preview") or {}
                source_params = dict(reference.get("source_params") or (source_preview.get("params") or {}))
                source_feature = _build_revolved_source_feature(
                    part,
                    model_container,
                    source_scenario,
                    source_params,
                    source_preview,
                    steps_report,
                )
                association_object, resolution_report = _select_revolved_feature_face(
                    source_scenario,
                    _get_source_feature_reference_object(source_scenario, source_feature),
                    selector,
                    source_preview,
                )
                steps_report.append(
                    {
                        "step": "resolve_reference_object",
                        "ok": True,
                        "operation_id": operation_id,
                        "selector_report": resolution_report,
                    }
                )
            point = _create_point3d_center_on_object(model_container, params.get("point_name") or "PT1", association_object)
        elif mode == "offset_from_point":
            resolved_output = _resolve_runtime_output_reference(
                runtime_objects,
                params.get("reference"),
                default_output="point",
                context_label="Workflow point reference on operation %s" % operation_id,
            )
            if resolved_output is None:
                reference_operation = bindings.get("reference_operation")
                if reference_operation:
                    reference_output = bindings.get("reference_output") or "point"
                    resolved_output = _resolve_runtime_workflow_output(runtime_objects, reference_operation, reference_output)
                    resolved_output = dict(resolved_output, operation_id=reference_operation, output_key=reference_output)
            if resolved_output is not None:
                if resolved_output.get("type") != "point":
                    raise RuntimeError(
                        "Workflow point reference %s.%s does not resolve to a point"
                        % (resolved_output.get("operation_id"), resolved_output.get("output_key"))
                    )
                reference_point = resolved_output["object"]
            else:
                reference_origin = params.get("reference_origin")
                if not isinstance(reference_origin, list) or len(reference_origin) != 3:
                    raise RuntimeError("offset_from_point mode requires reference_origin")
                reference_point = _create_point3d(model_container, params.get("reference_name") or "PT_BASE", reference_origin)
            point = _create_point3d_displace(
                model_container,
                params.get("point_name") or "PT1",
                reference_point,
                params.get("offset") or [0.0, 0.0, 0.0],
                offset_expressions=params.get("offset_expressions"),
            )
        else:
            point = _create_point3d(model_container, params.get("point_name") or "PT1", params.get("origin") or [0.0, 0.0, 0.0])

        runtime_objects[operation_id] = {
            "scenario": scenario,
            "point": point,
            "preview": preview,
            "params": params,
        }
        steps_report.append(
            {
                "step": "workflow_operation",
                "ok": True,
                "operation_id": operation_id,
                "scenario": scenario,
                "mode": mode,
                "name": safe_get(point, "Name", params.get("point_name")),
                "origin": [safe_get(point, "X", 0.0), safe_get(point, "Y", 0.0), safe_get(point, "Z", 0.0)],
                "reference": safe_get(point, "Reference"),
            }
        )
        return

    if scenario == "lcs":
        mode = str(params.get("mode") or "global")
        resolved_output = None
        if mode == "point":
            resolved_output = _resolve_runtime_output_reference(
                runtime_objects,
                params.get("reference"),
                default_output="point",
                context_label="Workflow LCS reference on operation %s" % operation_id,
            )
            if resolved_output is None and bindings.get("reference_operation"):
                reference_operation = bindings["reference_operation"]
                reference_output = bindings.get("reference_output") or "point"
                resolved_output = _resolve_runtime_workflow_output(runtime_objects, reference_operation, reference_output)
                resolved_output = dict(resolved_output, operation_id=reference_operation, output_key=reference_output)
        if mode == "point" and resolved_output is not None:
            if resolved_output.get("type") != "point":
                raise RuntimeError(
                    "Workflow LCS reference %s.%s does not resolve to a point"
                    % (resolved_output.get("operation_id"), resolved_output.get("output_key"))
                )
            lcs = _create_local_coordinate_system_on_point(
                part,
                params.get("lcs_name") or "LCS1",
                resolved_output["object"],
                rotation=params.get("rotation") or {},
            )
            reference_point = resolved_output["object"]
            association_object = resolved_output["object"]
        elif mode == "object":
            reference = params.get("reference") or {}
            source_scenario = str(reference.get("source_scenario") or reference.get("scenario") or "stepped_shaft")
            selector = _normalize_revolved_feature_face_selector(
                source_scenario,
                reference.get("selector") or _default_revolved_feature_face_selector(source_scenario),
            )
            if not _revolved_feature_face_supports_lcs_object(source_scenario, selector):
                raise RuntimeError(
                    "LCS object mode does not support %s selector %s; use point.center_of_object -> lcs.point"
                    % (source_scenario, selector)
                )
            resolved_output = _resolve_runtime_output_reference(
                runtime_objects,
                reference,
                default_output=selector,
                context_label="Workflow LCS reference on operation %s" % operation_id,
            )
            if resolved_output is None and bindings.get("reference_operation"):
                reference_operation = bindings["reference_operation"]
                reference_output = bindings.get("reference_output") or selector
                resolved_output = _resolve_runtime_workflow_output(runtime_objects, reference_operation, reference_output)
                resolved_output = dict(resolved_output, operation_id=reference_operation, output_key=reference_output)
            if resolved_output is None:
                source_preview = reference.get("source_preview") or {}
                source_params = dict(reference.get("source_params") or (source_preview.get("params") or {}))
                if source_preview or source_params:
                    source_feature = _build_revolved_source_feature(
                        part,
                        model_container,
                        source_scenario,
                        source_params,
                        source_preview,
                        steps_report,
                    )
                    association_object, resolution_report = _select_revolved_feature_face(
                        source_scenario,
                        _get_source_feature_reference_object(source_scenario, source_feature),
                        selector,
                        source_preview,
                    )
                    steps_report.append(
                        {
                            "step": "resolve_reference_object",
                            "ok": True,
                            "operation_id": operation_id,
                            "selector_report": resolution_report,
                        }
                    )
                    lcs, reference_point = _create_local_coordinate_system_on_object(
                        part,
                        model_container,
                        params.get("lcs_name") or "LCS1",
                        association_object,
                        only_outer_contour=bool(params.get("only_outer_contour")),
                    )
                    runtime_objects[operation_id] = {
                        "scenario": scenario,
                        "lcs": lcs,
                        "preview": preview,
                        "params": params,
                    }
                    steps_report.append(
                        {
                            "step": "workflow_operation",
                            "ok": True,
                            "operation_id": operation_id,
                            "scenario": scenario,
                            "mode": mode,
                            "name": safe_get(lcs, "Name", params.get("lcs_name")),
                            "origin": [safe_get(lcs, "X", 0.0), safe_get(lcs, "Y", 0.0), safe_get(lcs, "Z", 0.0)],
                            "reference": safe_get(lcs, "Reference"),
                            "current": safe_get(lcs, "Current"),
                            "reference_point_name": safe_get(reference_point, "Name") if reference_point is not None else None,
                            "association_object_name": safe_get(association_object, "Name") if association_object is not None else None,
                        }
                    )
                    return
                lcs, reference_point, association_object = _create_local_coordinate_system(part, params)
                runtime_objects[operation_id] = {
                    "scenario": scenario,
                    "lcs": lcs,
                    "preview": preview,
                    "params": params,
                }
                steps_report.append(
                    {
                        "step": "workflow_operation",
                        "ok": True,
                        "operation_id": operation_id,
                        "scenario": scenario,
                        "mode": mode,
                        "name": safe_get(lcs, "Name", params.get("lcs_name")),
                        "origin": [safe_get(lcs, "X", 0.0), safe_get(lcs, "Y", 0.0), safe_get(lcs, "Z", 0.0)],
                        "reference": safe_get(lcs, "Reference"),
                        "current": safe_get(lcs, "Current"),
                        "reference_point_name": safe_get(reference_point, "Name") if reference_point is not None else None,
                        "association_object_name": safe_get(association_object, "Name") if association_object is not None else None,
                    }
                )
                return
            if resolved_output.get("type") != "face":
                raise RuntimeError(
                    "Workflow LCS reference %s.%s does not resolve to a face"
                    % (resolved_output.get("operation_id"), resolved_output.get("output_key"))
                )
            association_object = resolved_output["object"]
            resolution_report = resolved_output.get("resolution_report") or {}
            steps_report.append(
                {
                    "step": "resolve_reference_object",
                    "ok": True,
                    "operation_id": operation_id,
                    "reference_operation": resolved_output.get("operation_id"),
                    "reference_output": resolved_output.get("output_key"),
                    "selector_report": resolution_report,
                }
            )
            lcs, reference_point = _create_local_coordinate_system_on_object(
                part,
                model_container,
                params.get("lcs_name") or "LCS1",
                association_object,
                only_outer_contour=bool(params.get("only_outer_contour")),
            )
        else:
            lcs, reference_point, association_object = _create_local_coordinate_system(part, params)
        runtime_objects[operation_id] = {
            "scenario": scenario,
            "lcs": lcs,
            "preview": preview,
            "params": params,
        }
        steps_report.append(
            {
                "step": "workflow_operation",
                "ok": True,
                "operation_id": operation_id,
                "scenario": scenario,
                "mode": mode,
                "name": safe_get(lcs, "Name", params.get("lcs_name")),
                "origin": [safe_get(lcs, "X", 0.0), safe_get(lcs, "Y", 0.0), safe_get(lcs, "Z", 0.0)],
                "reference": safe_get(lcs, "Reference"),
                "current": safe_get(lcs, "Current"),
                "reference_point_name": safe_get(reference_point, "Name") if reference_point is not None else None,
                "association_object_name": safe_get(association_object, "Name") if association_object is not None else None,
            }
        )
        return

    raise RuntimeError("Unsupported workflow scenario: %s" % scenario)


def _handle_create_point_scenario(payload, scenario):
    params = payload.get("params") or {}
    output_path = params.get("output_path")
    if not output_path:
        raise RuntimeError("params.output_path is required")

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    app = make_app()
    doc3 = None
    close_after_save = bool(params.get("close_after_save", True))
    steps_report = []
    current_stage = "init"

    try:
        current_stage = "create_part_document"
        doc3, part, model_container = _create_part_document(app, payload.get("visible", False))
        steps_report.append({"step": "create_part_document", "ok": True, "api": "api7_documents_add"})

        property_report = apply_part_properties(part, params)
        if property_report:
            steps_report.append(
                {
                    "step": "set_part_properties_initial",
                    "ok": all(item["ok"] for item in property_report),
                    "properties": property_report,
                }
            )

        variable_plan = list(params.get("variable_plan") or [])
        if variable_plan:
            steps_report.append(_apply_part_variables(part, variable_plan))

        current_stage = "create_point"
        mode = str(params.get("mode") or "global")
        reference_point = None
        association_object = None
        source_feature = None
        if mode == "center_of_object":
            reference = params.get("reference") or {}
            source_preview = reference.get("source_preview") or {}
            source_params = dict(reference.get("source_params") or (source_preview.get("params") or {}))
            source_scenario = str(reference.get("source_scenario") or reference.get("scenario") or "stepped_shaft")
            source_feature = _build_revolved_source_feature(
                part,
                model_container,
                source_scenario,
                source_params,
                source_preview,
                steps_report,
            )
            selector = _normalize_revolved_feature_face_selector(
                source_scenario,
                reference.get("selector") or _default_revolved_feature_face_selector(source_scenario),
            )
            association_object, resolution_report = _select_revolved_feature_face(
                source_scenario,
                _get_source_feature_reference_object(source_scenario, source_feature),
                selector,
                source_preview,
            )
            steps_report.append(
                {
                    "step": "resolve_reference_object",
                    "ok": True,
                    "mode": mode,
                    "reference": reference,
                    "selector_report": resolution_report,
                    "association_object": {
                        "name": safe_get(association_object, "Name"),
                        "reference": safe_get(association_object, "Reference"),
                        "model_object_type": safe_get(association_object, "ModelObjectType"),
                        "surface_type": safe_get(association_object, "Surface3DType"),
                    },
                }
            )
        elif mode == "offset_from_point":
            reference_origin = params.get("reference_origin")
            if not isinstance(reference_origin, list) or len(reference_origin) != 3:
                raise RuntimeError("offset_from_point mode requires reference_origin")
            reference_point = _create_point3d(model_container, params.get("reference_name") or "PT_BASE", reference_origin)
            steps_report.append(
                {
                    "step": "create_point",
                    "role": "reference_point",
                    "ok": True,
                    "name": safe_get(reference_point, "Name", params.get("reference_name")),
                    "origin": [safe_get(reference_point, "X", 0.0), safe_get(reference_point, "Y", 0.0), safe_get(reference_point, "Z", 0.0)],
                    "reference": safe_get(reference_point, "Reference"),
                }
            )

        if mode == "center_of_object":
            point = _create_point3d_center_on_object(model_container, params.get("point_name") or "PT1", association_object)
        elif mode == "offset_from_point":
            point = _create_point3d_displace(
                model_container,
                params.get("point_name") or "PT1",
                reference_point,
                params.get("offset") or [0.0, 0.0, 0.0],
                offset_expressions=params.get("offset_expressions"),
            )
        else:
            point = _create_point3d(model_container, params.get("point_name") or "PT1", params.get("origin") or [0.0, 0.0, 0.0])
        item = {
            "step": "create_point",
            "ok": True,
            "name": safe_get(point, "Name", params.get("point_name")),
            "origin": [safe_get(point, "X", 0.0), safe_get(point, "Y", 0.0), safe_get(point, "Z", 0.0)],
            "reference": safe_get(point, "Reference"),
        }
        if reference_point is not None:
            item["mode"] = mode
            item["reference_point"] = {
                "name": safe_get(reference_point, "Name", params.get("reference_name")),
                "origin": [safe_get(reference_point, "X", 0.0), safe_get(reference_point, "Y", 0.0), safe_get(reference_point, "Z", 0.0)],
                "reference": safe_get(reference_point, "Reference"),
            }
            item["offset"] = params.get("offset") or [0.0, 0.0, 0.0]
        if association_object is not None:
            item["association_object"] = {
                "name": safe_get(association_object, "Name"),
                "reference": safe_get(association_object, "Reference"),
                "model_object_type": safe_get(association_object, "ModelObjectType"),
            }
        steps_report.append(item)

        current_stage = "save"
        saved, created_document = _save_generated_part_document(
            doc3,
            app,
            output_path,
            close_after_save,
            steps_report,
            visible=bool(payload.get("visible", False)),
        )
        return {
            "scenario": scenario,
            "ok": True,
            "document": created_document,
            "output_path": output_path,
            "saved": saved,
            "closed": close_after_save,
            "steps": steps_report,
            "summary": {
                "mode": params.get("mode"),
                "point_name": params.get("point_name"),
            },
            "remaining_documents": list_documents(app),
            "file_access": file_access_diagnostics(output_path),
        }
    except Exception as exc:
        if close_after_save:
            try:
                _close_generated_document(doc3, app)
            except Exception:
                pass
        raise RuntimeError(
            "create_part_from_scenario failed at %s: %s | steps=%s"
            % (current_stage, exc, json.dumps(steps_report, ensure_ascii=False))
        )


def _handle_create_lcs_scenario(payload, scenario):
    params = payload.get("params") or {}
    output_path = params.get("output_path")
    if not output_path:
        raise RuntimeError("params.output_path is required")

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    app = make_app()
    doc3 = None
    close_after_save = bool(params.get("close_after_save", True))
    steps_report = []
    current_stage = "init"

    try:
        current_stage = "create_part_document"
        doc3, part, _ = _create_part_document(app, payload.get("visible", False))
        steps_report.append({"step": "create_part_document", "ok": True, "api": "api7_documents_add"})

        property_report = apply_part_properties(part, params)
        if property_report:
            steps_report.append(
                {
                    "step": "set_part_properties_initial",
                    "ok": all(item["ok"] for item in property_report),
                    "properties": property_report,
                }
            )

        current_stage = "create_lcs"
        if str(params.get("mode") or "") == "object" and isinstance(params.get("reference"), dict) and (
            (params.get("reference") or {}).get("source_params") or (params.get("reference") or {}).get("source_preview")
        ):
            reference = params.get("reference") or {}
            source_preview = reference.get("source_preview") or {}
            source_params = dict(reference.get("source_params") or (source_preview.get("params") or {}))
            model_container = _cast_to_com_interface(part, "IModelContainer")
            source_scenario = str(reference.get("source_scenario") or reference.get("scenario") or "stepped_shaft")
            source_feature = _build_revolved_source_feature(
                part,
                model_container,
                source_scenario,
                source_params,
                source_preview,
                steps_report,
            )
            selector = _normalize_revolved_feature_face_selector(
                source_scenario,
                reference.get("selector") or _default_revolved_feature_face_selector(source_scenario),
            )
            if not _revolved_feature_face_supports_lcs_object(source_scenario, selector):
                raise RuntimeError(
                    "LCS object mode does not support %s selector %s; use point.center_of_object -> lcs.point"
                    % (source_scenario, selector)
                )
            association_object, resolution_report = _select_revolved_feature_face(
                source_scenario,
                _get_source_feature_reference_object(source_scenario, source_feature),
                selector,
                source_preview,
            )
            steps_report.append(
                {
                    "step": "resolve_reference_object",
                    "ok": True,
                    "mode": "object",
                    "reference": reference,
                    "selector_report": resolution_report,
                }
            )
            lcs, reference_point = _create_local_coordinate_system_on_object(
                part,
                model_container,
                params.get("lcs_name") or "LCS1",
                association_object,
                only_outer_contour=bool(params.get("only_outer_contour")),
            )
        else:
            lcs, reference_point, association_object = _create_local_coordinate_system(part, params)
        item = {
            "step": "create_lcs",
            "ok": True,
            "name": safe_get(lcs, "Name", params.get("lcs_name")),
            "mode": params.get("mode"),
            "origin": [safe_get(lcs, "X", 0.0), safe_get(lcs, "Y", 0.0), safe_get(lcs, "Z", 0.0)],
            "reference": safe_get(lcs, "Reference"),
            "current": safe_get(lcs, "Current"),
        }
        if reference_point is not None:
            item["reference_point"] = {
                "name": safe_get(reference_point, "Name", params.get("reference_name")),
                "origin": [safe_get(reference_point, "X", 0.0), safe_get(reference_point, "Y", 0.0), safe_get(reference_point, "Z", 0.0)],
                "reference": safe_get(reference_point, "Reference"),
            }
        if association_object is not None and str(params.get("mode") or "") == "object":
            item["association_object"] = {
                "name": safe_get(association_object, "Name"),
                "reference": safe_get(association_object, "Reference"),
                "model_object_type": safe_get(association_object, "ModelObjectType"),
            }
        steps_report.append(item)

        current_stage = "save"
        saved, created_document = _save_generated_part_document(
            doc3,
            app,
            output_path,
            close_after_save,
            steps_report,
            visible=bool(payload.get("visible", False)),
        )
        return {
            "scenario": scenario,
            "ok": True,
            "document": created_document,
            "output_path": output_path,
            "saved": saved,
            "closed": close_after_save,
            "steps": steps_report,
            "summary": {
                "mode": params.get("mode"),
                "lcs_name": params.get("lcs_name"),
            },
            "remaining_documents": list_documents(app),
            "file_access": file_access_diagnostics(output_path),
        }
    except Exception as exc:
        if close_after_save:
            try:
                _close_generated_document(doc3, app)
            except Exception:
                pass
        raise RuntimeError(
            "create_part_from_scenario failed at %s: %s | steps=%s"
            % (current_stage, exc, json.dumps(steps_report, ensure_ascii=False))
        )


def _handle_create_workflow_scenario(payload, scenario):
    params = payload.get("params") or {}
    output_path = params.get("output_path")
    if not output_path:
        raise RuntimeError("params.output_path is required")

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    app = make_app()
    doc3 = None
    close_after_save = bool(params.get("close_after_save", True))
    steps_report = []
    current_stage = "init"
    runtime_objects = {}

    try:
        current_stage = "create_part_document"
        doc3, part, model_container = _create_part_document(app, payload.get("visible", False))
        steps_report.append({"step": "create_part_document", "ok": True, "api": "api7_documents_add"})

        property_report = apply_part_properties(part, params)
        if property_report:
            steps_report.append(
                {
                    "step": "set_part_properties_initial",
                    "ok": all(item["ok"] for item in property_report),
                    "properties": property_report,
                }
            )

        current_stage = "workflow"
        operations = params.get("operations") or []
        for operation in operations:
            _execute_workflow_operation(part, model_container, operation, runtime_objects, steps_report)

        exports = _resolve_runtime_workflow_exports(params.get("exports"), runtime_objects)
        steps_report.append(
            {
                "step": "workflow_exports",
                "ok": True,
                "export_count": len(exports),
                "export_names": sorted(exports.keys()),
                "exports": exports,
            }
        )

        property_report = apply_part_properties(part, params)
        if property_report:
            steps_report.append(
                {
                    "step": "set_part_properties_final",
                    "ok": all(item["ok"] for item in property_report),
                    "properties": property_report,
                }
            )

        runtime_object_probe = None
        if params.get("include_runtime_object_probe"):
            runtime_object_probe = probe_runtime_objects(
                runtime_objects,
                max_items=params.get("runtime_object_probe_max_items", 20),
            )
            steps_report.append(
                {
                    "step": "runtime_object_probe",
                    "ok": True,
                    "summary": runtime_object_probe["summary"],
                }
            )

        current_stage = "save"
        saved, created_document = _save_generated_part_document(
            doc3,
            app,
            output_path,
            close_after_save,
            steps_report,
            visible=bool(payload.get("visible", False)),
        )
        return {
            "scenario": scenario,
            "ok": True,
            "document": created_document,
            "output_path": output_path,
            "saved": saved,
            "closed": close_after_save,
            "steps": steps_report,
            "exports": exports,
            "runtime_object_probe": runtime_object_probe,
            "summary": {
                "operation_count": len(operations),
                "operation_ids": [str(operation.get("id") or "") for operation in operations],
                "export_count": len(exports),
                "export_names": sorted(exports.keys()),
                "runtime_object_probe": runtime_object_probe["summary"] if runtime_object_probe else None,
            },
            "remaining_documents": list_documents(app),
            "file_access": file_access_diagnostics(output_path),
        }
    except Exception as exc:
        if close_after_save:
            try:
                _close_generated_document(doc3, app)
            except Exception:
                pass
        raise RuntimeError(
            "create_part_from_scenario failed at %s: %s | steps=%s"
            % (current_stage, exc, json.dumps(steps_report, ensure_ascii=False))
        )


def _describe_constraints_state(state):
    try:
        code = int(state)
    except Exception:
        return {"code": None, "name": "unknown", "label": "unknown"}
    mapping = {
        0: ("unknown", "unknown"),
        1: ("well_constrained", "fully_defined"),
        2: ("under_constrained", "has_degrees_of_freedom"),
        3: ("unresolved_redundancy", "has_conflicting_constraints"),
    }
    name, label = mapping.get(code, ("unknown", "unknown"))
    return {"code": code, "name": name, "label": label}


def handle_create_part_from_scenario(payload):
    scenario = (payload.get("scenario") or "").strip().lower()
    if scenario == "point":
        return _handle_create_point_scenario(payload, scenario)
    if scenario == "lcs":
        return _handle_create_lcs_scenario(payload, scenario)
    if scenario == "workflow":
        return _handle_create_workflow_scenario(payload, scenario)
    if scenario not in ("stepped_shaft", "external_conical_step", "internal_conical_step", "internal_cylindrical_step", "external_polygonal_step", "internal_polygonal_step", "external_flat_step", "internal_flat_step", "external_helical_thread", "internal_helical_thread", "external_threaded_step", "internal_threaded_step", "face_ring_groove", "bolt_circle_holes"):
        raise RuntimeError("Unsupported part scenario: %s" % scenario)

    params = payload.get("params") or {}
    output_path = params.get("output_path")
    if not output_path:
        raise RuntimeError("params.output_path is required")

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    app = make_app()
    app5 = _APP5
    if app5 is None:
        raise RuntimeError("Failed to initialize KOMPAS.Application.5")

    doc3 = None
    created_document = None
    close_after_save = bool(params.get("close_after_save", True))
    steps_report = []
    current_stage = "init"
    material_settings = None
    material_settings_snapshot = None

    try:
        current_stage = "create_part_document"
        if params.get("material"):
            material_settings = get_new_part_document_settings(app)
            if material_settings is not None:
                material_settings_snapshot = snapshot_new_part_document_settings(material_settings)
                material_payload = apply_new_part_document_material_defaults(material_settings, params)
                params["_material_initialized_from_defaults"] = True
                steps_report.append(
                    {
                        "step": "configure_new_part_material_defaults",
                        "ok": True,
                        "material": material_payload.get("material"),
                        "density": material_payload.get("density"),
                        "catalog_matched": material_payload.get("catalog_matched", False),
                    }
                )
        doc3 = app.Documents.Add(4, bool(payload.get("visible", False)))
        if doc3 is None:
            raise RuntimeError("Documents.Add(ksDocumentPart) returned None")
        if material_settings is not None and material_settings_snapshot is not None:
            restore_new_part_document_settings(material_settings, material_settings_snapshot)
            material_settings = None
            material_settings_snapshot = None
        steps_report.append({"step": "create_part_document", "ok": True, "api": "api7_documents_add"})

        for attr, value in (
            ("comment", params.get("comment") or params.get("name") or "Stepped shaft"),
            ("drawMode", 3),
            ("perspective", True),
        ):
            try:
                setattr(doc3, attr, value)
            except Exception:
                pass
        try:
            doc3.UpdateDocumentParam()
        except Exception:
            pass

        current_stage = "get_part"
        part = safe_get(doc3, "TopPart")
        if part is None:
            doc3_model = cast_document_3d(doc3)
            part = safe_get(doc3_model, "TopPart")
        if part is None:
            raise RuntimeError("Failed to get part from created document")
        model_container = cast_model_container(part)
        steps_report.append({"step": "get_part", "ok": True, "api": "api7_top_part"})

        property_report = apply_part_properties(part, params)
        if property_report:
            steps_report.append(
                {
                    "step": "set_part_properties_initial",
                    "ok": all(item["ok"] for item in property_report),
                    "properties": property_report,
                }
            )

        current_stage = "base_rotation"
        if scenario == "stepped_shaft":
            _build_stepped_shaft_feature(part, model_container, params, payload.get("preview") or {}, steps_report)
        elif scenario == "external_conical_step":
            _build_external_conical_step_feature(part, model_container, params, payload.get("preview") or {}, steps_report)
        elif scenario == "internal_conical_step":
            _build_internal_conical_step_feature(
                part,
                model_container,
                params,
                payload.get("preview") or {},
                steps_report,
                require_source=True,
            )
        elif scenario == "internal_cylindrical_step":
            _build_internal_cylindrical_step_feature(
                part,
                model_container,
                params,
                payload.get("preview") or {},
                steps_report,
                require_source=True,
            )
        elif scenario == "external_polygonal_step":
            _build_external_polygonal_step_feature(part, model_container, params, payload.get("preview") or {}, steps_report)
        elif scenario == "internal_polygonal_step":
            _build_internal_polygonal_step_feature(
                part,
                model_container,
                params,
                payload.get("preview") or {},
                steps_report,
                require_source=True,
            )
        elif scenario == "external_flat_step":
            _build_external_flat_step_feature(part, model_container, params, payload.get("preview") or {}, steps_report)
        elif scenario == "internal_flat_step":
            _build_internal_flat_step_feature(
                part,
                model_container,
                params,
                payload.get("preview") or {},
                steps_report,
                require_source=True,
            )
        elif scenario == "external_helical_thread":
            _build_external_helical_thread_feature(part, model_container, params, payload.get("preview") or {}, steps_report)
        elif scenario == "internal_helical_thread":
            _build_internal_helical_thread_feature(part, model_container, params, payload.get("preview") or {}, steps_report)
        elif scenario == "external_threaded_step":
            _build_external_threaded_step_feature(part, model_container, params, payload.get("preview") or {}, steps_report)
        elif scenario == "internal_threaded_step":
            _build_internal_threaded_step_feature(part, model_container, params, payload.get("preview") or {}, steps_report)
        elif scenario == "face_ring_groove":
            _build_face_ring_groove_feature(
                part,
                model_container,
                params,
                payload.get("preview") or {},
                steps_report,
                require_source=True,
            )
        else:
            _build_bolt_circle_holes_feature(
                part,
                model_container,
                params,
                payload.get("preview") or {},
                steps_report,
                require_source=True,
            )

        property_report = apply_part_properties(part, params)
        if property_report:
            steps_report.append(
                {
                    "step": "set_part_properties_final",
                    "ok": all(item["ok"] for item in property_report),
                    "properties": property_report,
                }
            )

        current_stage = "save"
        saved, created_document = _save_generated_part_document(
            doc3,
            app,
            output_path,
            close_after_save,
            steps_report,
            visible=bool(payload.get("visible", False)),
        )

        return {
            "scenario": scenario,
            "ok": True,
            "document": created_document,
            "output_path": output_path,
            "saved": saved,
            "closed": close_after_save,
            "steps": steps_report,
            "summary": {
                "step_count": len(params.get("steps") or []),
                "total_length": params.get("total_length"),
                "operation_count": 1,
            },
            "remaining_documents": list_documents(app),
            "file_access": file_access_diagnostics(output_path),
        }
    except Exception as exc:
        if material_settings is not None and material_settings_snapshot is not None:
            try:
                restore_new_part_document_settings(material_settings, material_settings_snapshot)
            except Exception:
                pass
        if close_after_save:
            try:
                _close_generated_document(doc3, app)
            except Exception:
                pass
        raise RuntimeError(
            "create_part_from_scenario failed at %s: %s | steps=%s"
            % (current_stage, exc, json.dumps(steps_report, ensure_ascii=False))
        )


def _close_generated_document(doc3, app):
    active_document = safe_get(app, "ActiveDocument")
    if active_document is not None:
        try:
            active_document.Close(0)
            return
        except Exception:
            pass
    if doc3 is not None:
        for method_name in ("close", "Close"):
            method = safe_get(doc3, method_name)
            if callable(method):
                try:
                    method()
                    return
                except Exception:
                    pass


def dispatch(request):
    action = request.get("action")
    payload = request.get("payload") or {}

    if action == "get_session_state":
        return get_session_state()
    if action == "list_documents":
        return handle_list_documents()
    if action == "get_document_tree":
        return handle_get_document_tree(payload)
    if action == "create_point3d":
        return handle_create_point3d(payload)
    if action == "create_sketch_line_segment":
        return handle_create_sketch_line_segment(payload)
    if action == "create_sketch_circle":
        return handle_create_sketch_circle(payload)
    if action == "create_sketch_rectangle":
        return handle_create_sketch_rectangle(payload)
    if action == "create_sketch_entities":
        return handle_create_sketch_entities(payload)
    if action == "parameterize_sketch":
        return handle_parameterize_sketch(payload)
    if action == "list_sketches":
        return handle_list_sketches(payload)
    if action == "rename_sketch":
        return handle_rename_sketch(payload)
    if action == "set_sketch_entity_style":
        return handle_set_sketch_entity_style(payload)
    if action == "list_sketch_entities":
        return handle_list_sketch_entities(payload)
    if action == "inspect_sketch_entity":
        return handle_inspect_sketch_entity(payload)
    if action == "probe_model_object_collections":
        return handle_probe_model_object_collections(payload)
    if action == "get_specification_descriptions":
        return handle_get_specification_descriptions(payload)
    if action == "get_specification":
        return handle_get_specification(payload)
    if action == "create_specification":
        return handle_create_specification(payload)
    if action == "apply_specification_changes":
        return handle_apply_specification_changes(payload)
    if action == "open_document":
        return handle_open_document(payload)
    if action == "close_document":
        return handle_close_document(payload)
    if action == "shutdown_session":
        return handle_shutdown_session(payload)
    if action == "apply_changeset":
        return handle_apply_changeset(payload)
    if action == "save_document":
        return handle_save_document(payload)
    if action == "apply_relink_paths":
        return handle_apply_relink_paths(payload)
    if action == "relink_document_file":
        return handle_relink_document_file(payload)
    if action == "create_spw_from_rows":
        return handle_create_spw_from_rows(payload)
    if action == "create_part_from_scenario":
        return handle_create_part_from_scenario(payload)
    raise RuntimeError("Unsupported action: %s" % action)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: kompas_bridge.py <request.json> <response.json>")

    request_path = sys.argv[1]
    response_path = sys.argv[2]

    try:
        request = read_request(request_path)
        payload = dispatch(request)
        write_response(response_path, {"ok": True, "data": payload})
    except Exception as exc:
        write_response(
            response_path,
            {"ok": False, "error": {"message": str(exc), "type": exc.__class__.__name__}},
        )
        raise


if __name__ == "__main__":
    main()
