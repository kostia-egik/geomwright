import json
import os
import sys
import ctypes
import re
import math
import itertools
import shutil
import subprocess
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


def _assign_sketch_origin_point(sketch, point):
    report = {
        "ok": False,
        "point_reference": safe_get(point, "Reference"),
        "attempts": [],
    }
    if sketch is None or point is None:
        report["reason"] = "missing_sketch_or_point"
        return report
    for attr in ("OriginPoint", "BasePoint", "Point"):
        attempt = {"attr": attr, "ok": False}
        try:
            setattr(sketch, attr, point)
            attempt["ok"] = True
            report["ok"] = True
            report["applied_attr"] = attr
            report["attempts"].append(attempt)
            return report
        except Exception as exc:
            attempt["error"] = str(exc)
            report["attempts"].append(attempt)
    report["reason"] = "origin_assignment_failed"
    return report


def _touch_com_dependency_chain(*items):
    report = []
    for label, obj in items:
        entry = {"label": label, "attempts": []}
        if obj is None:
            entry["reason"] = "missing_object"
            report.append(entry)
            continue
        for method_name in ("Update", "Rebuild", "Recalculate", "Refresh"):
            method = safe_get(obj, method_name)
            attempt = {"method": method_name, "ok": False}
            if not callable(method):
                attempt["reason"] = "not_callable"
                entry["attempts"].append(attempt)
                continue
            try:
                value = method()
                attempt["ok"] = value is not False
                attempt["result"] = value
                entry["attempts"].append(attempt)
                if attempt["ok"]:
                    entry["applied_method"] = method_name
                    break
            except Exception as exc:
                attempt["error"] = str(exc)
                entry["attempts"].append(attempt)
        report.append(entry)
    return report


def _touch_named_variable_same_value(owner, variable_name):
    report = {"variable_name": variable_name, "ok": False, "attempts": []}
    variables = _iter_operation_variables(owner)
    if not variables:
        report["reason"] = "variables_unavailable"
        return report
    matched = None
    for variable in variables:
        if str(safe_get(variable, "Name", "") or "") == variable_name:
            matched = variable
            break
    if matched is None:
        report["reason"] = "variable_not_found"
        report["available"] = [safe_get(variable, "Name", "") for variable in variables]
        return report
    expression = safe_get(matched, "Expression", None)
    value = safe_get(matched, "Value", None)
    try:
        if expression not in (None, ""):
            matched.Expression = expression
            report["touched"] = "Expression"
            report["expression"] = expression
        else:
            matched.Value = value
            report["touched"] = "Value"
            report["value"] = value
        update = safe_get(matched, "Update")
        report["variable_update_ok"] = bool(update()) if callable(update) else True
        owner_update = safe_get(owner, "Update")
        report["owner_update_ok"] = bool(owner_update()) if callable(owner_update) else True
        report["ok"] = bool(report["variable_update_ok"] and report["owner_update_ok"])
    except Exception as exc:
        report["error"] = str(exc)
    return report


def _touch_angle_plane_same_value(plane, angle_degrees, *, angle_expression=None):
    report = {"ok": False, "angle_degrees": angle_degrees, "angle_expression": angle_expression, "attempts": []}
    if plane is None:
        report["reason"] = "missing_plane"
        return report
    for attr in ("Angle", "Value"):
        attempt = {"attr": attr, "ok": False}
        try:
            if not hasattr(plane, attr):
                attempt["reason"] = "missing_attr"
                report["attempts"].append(attempt)
                continue
            property_report = _set_com_property_expression_or_value(plane, attr, angle_expression, float(angle_degrees))
            attempt["property_report"] = property_report
            update = safe_get(plane, "Update")
            attempt["update_ok"] = bool(update()) if callable(update) else True
            attempt["ok"] = bool(property_report.get("ok") and attempt["update_ok"])
            report["attempts"].append(attempt)
            if attempt["ok"]:
                report["ok"] = True
                report["applied_attr"] = attr
                return report
        except Exception as exc:
            attempt["error"] = str(exc)
            report["attempts"].append(attempt)
    report["reason"] = "angle_plane_touch_failed"
    return report


def _apply_spiral_initial_angle(spiral, angle_expression):
    report = {"requested": angle_expression, "ok": False, "attempts": []}
    for attr in ("InitialAngle", "StartAngle"):
        attempt = {"target": attr, "ok": False}
        try:
            setattr(spiral, attr, angle_expression)
            attempt["ok"] = True
            report["ok"] = True
            report["applied_target"] = attr
            report["attempts"].append(attempt)
            return report
        except Exception as exc:
            attempt["error"] = str(exc)
            report["attempts"].append(attempt)
    parameter = safe_get(spiral, "Parameter")
    if parameter is not None:
        for attr in ("Angle", "InitialAngle", "StartAngle"):
            attempt = {"target": "Parameter.%s" % attr, "ok": False}
            try:
                setattr(parameter, attr, angle_expression)
                attempt["ok"] = True
                report["ok"] = True
                report["applied_target"] = "Parameter.%s" % attr
                report["attempts"].append(attempt)
                return report
            except Exception as exc:
                attempt["error"] = str(exc)
                report["attempts"].append(attempt)
    report["reason"] = "initial_angle_api_unavailable"
    return report


def _set_com_property_expression_or_value(obj, attr, expression, value):
    report = {"property": attr, "expression": expression, "value": value, "mode": None, "ok": False, "attempts": []}
    for mode, candidate in (("expression", expression), ("value", value)):
        if candidate in (None, ""):
            continue
        attempt = {"mode": mode, "ok": False}
        try:
            setattr(obj, attr, candidate)
            attempt["ok"] = True
            report["ok"] = True
            report["mode"] = mode
            report["attempts"].append(attempt)
            return report
        except Exception as exc:
            attempt["error"] = str(exc)
            report["attempts"].append(attempt)
    report["reason"] = "assignment_failed"
    return report


def _probe_projection_api(*items):
    candidates = (
        "Projections", "ProjectionObjects", "ProjectedObjects", "ProjectedCurves",
        "ProjectObjects", "ProjectObject", "Project", "CreateProjection",
        "AddProjection", "AddProjectedObject", "GetProjections", "GetProjectionObjects",
    )
    report = []
    for label, obj in items:
        entry = {"label": label, "available": []}
        if obj is None:
            entry["reason"] = "missing_object"
            report.append(entry)
            continue
        for name in candidates:
            try:
                member = getattr(obj, name)
                entry["available"].append({"name": name, "callable": callable(member), "type": str(type(member))})
            except Exception:
                pass
        try:
            dir_matches = [name for name in dir(obj) if "proj" in name.lower()]
            if dir_matches:
                entry["dir_matches"] = dir_matches[:40]
        except Exception:
            pass
        report.append(entry)
    return report


def _project_point_to_sketch_xy(sketch, point):
    report = {"ok": False, "attempts": []}
    if sketch is None or point is None:
        report["reason"] = "missing_sketch_or_point"
        return report
    add_projection = safe_get(sketch, "AddProjectionOf")
    if callable(add_projection):
        try:
            projection = add_projection(point)
            report["projection_reference"] = safe_get(projection, "Reference")
            report["projection_created"] = projection is not None
        except Exception as exc:
            report["projection_error"] = str(exc)
    get_projection = safe_get(sketch, "GetPointProjectionToXY")
    if callable(get_projection):
        coordinates = [safe_get(point, "X", 0.0), safe_get(point, "Y", 0.0), safe_get(point, "Z", 0.0)]
        call_variants = (
            ("point_object", (point,)),
            ("xyz", tuple(coordinates)),
            ("xyz_list", (coordinates,)),
        )
        for label, args in call_variants:
            attempt = {"call": label, "ok": False}
            try:
                value = get_projection(*args)
                xy = _coerce_xy(value)
                attempt["raw"] = str(value)
                attempt["xy"] = xy
                attempt["ok"] = xy is not None
                report["attempts"].append(attempt)
                if xy is not None:
                    report["ok"] = True
                    report["xy"] = xy
                    report["call"] = label
                    return report
            except Exception as exc:
                attempt["error"] = str(exc)
                report["attempts"].append(attempt)
    if report.get("projection_created"):
        report["reason"] = "projection_created_without_xy"
    else:
        report["reason"] = "projection_failed"
    return report


def _coerce_projection_object(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for item in reversed(value):
            if item is not None and not isinstance(item, (bool, int, float, str)):
                return item
        return None
    if isinstance(value, (bool, int, float, str)):
        return None
    return value


def _project_point_to_sketch_xy_with_object(sketch, point):
    report = {"ok": False, "attempts": []}
    projection = None
    if sketch is None or point is None:
        report["reason"] = "missing_sketch_or_point"
        return report, projection
    add_projection = safe_get(sketch, "AddProjectionOf")
    if callable(add_projection):
        try:
            raw_projection = add_projection(point)
            projection = _coerce_projection_object(raw_projection)
            report["projection_raw"] = str(raw_projection)
            report["projection_reference"] = safe_get(projection, "Reference")
            report["projection_created"] = projection is not None
        except Exception as exc:
            report["projection_error"] = str(exc)
        if projection is None:
            try:
                sketch.BeginEdit()
                raw_projection = add_projection(point)
                sketch.EndEdit()
                projection = _coerce_projection_object(raw_projection)
                report["projection_begin_edit_raw"] = str(raw_projection)
                report["projection_reference"] = safe_get(projection, "Reference")
                report["projection_created"] = projection is not None
            except Exception as exc:
                try:
                    sketch.EndEdit()
                except Exception:
                    pass
                report["projection_begin_edit_error"] = str(exc)
    xy_report = _project_point_to_sketch_xy(sketch, point)
    initial_projection_created = bool(report.get("projection_created"))
    initial_projection_reference = report.get("projection_reference")
    initial_projection_raw = report.get("projection_raw")
    report.update(xy_report)
    if initial_projection_created:
        report["projection_created"] = True
        report["projection_reference"] = initial_projection_reference
        report["projection_raw"] = initial_projection_raw
    if projection is not None:
        report["projection_created"] = True
        report["projection_reference"] = safe_get(projection, "Reference")
    return report, projection


def _apply_center_axis_projection_constraints(center_axis_line, projected_point, *, length_expression=None, length_value=None):
    report = {"enabled": projected_point is not None, "applied": [], "failed": []}
    if center_axis_line is None:
        report["failed"].append({"kind": "input", "error": "missing_center_axis_line"})
        return report
    try:
        vertical = _apply_constraint_to_line(center_axis_line, SKETCH_CONSTRAINT_TYPES["vertical"])
        vertical_entry = dict(vertical)
        vertical_entry["kind"] = "vertical"
        report["applied" if vertical.get("created") else "failed"].append(vertical_entry)
    except Exception as exc:
        report["failed"].append({"kind": "vertical", "error": str(exc)})
    if projected_point is None:
        report["failed"].append({"kind": "merge_points", "error": "missing_projected_point"})
    else:
        for partner_index in (0, None, 1):
            try:
                coincident = _apply_constraint_to_line(
                    center_axis_line,
                    SKETCH_CONSTRAINT_TYPES["merge_points"],
                    index=0,
                    partner=projected_point,
                    partner_index=partner_index,
                )
                entry = dict(coincident)
                entry["kind"] = "merge_points"
                entry["partner_index"] = partner_index
                report["applied" if coincident.get("created") else "failed"].append(entry)
                if coincident.get("created"):
                    break
            except Exception as exc:
                report["failed"].append({"kind": "merge_points", "partner_index": partner_index, "error": str(exc)})
    has_anchor = any(item.get("kind") == "merge_points" and item.get("created") for item in report["applied"])
    if not has_anchor:
        try:
            fixed_point = _apply_constraint_to_line(
                center_axis_line,
                SKETCH_CONSTRAINT_TYPES["fixed_point"],
                index=0,
            )
            fixed_point_entry = dict(fixed_point)
            fixed_point_entry["kind"] = "fixed_point"
            fixed_point_entry["index"] = 0
            fixed_point_entry["fallback_after_merge"] = True
            report["applied" if fixed_point.get("created") else "failed"].append(fixed_point_entry)
        except Exception as exc:
            report["failed"].append({"kind": "fixed_point", "index": 0, "fallback_after_merge": True, "error": str(exc)})
    try:
        fixed_length = _apply_constraint_to_line(
            center_axis_line,
            SKETCH_CONSTRAINT_TYPES["fixed_length"],
            expression=length_expression,
            value=length_value,
        )
        fixed_length_entry = dict(fixed_length)
        fixed_length_entry["kind"] = "fixed_length"
        fixed_length_entry["expression"] = length_expression
        fixed_length_entry["value"] = length_value
        report["applied" if fixed_length.get("created") else "failed"].append(fixed_length_entry)
    except Exception as exc:
        report["failed"].append({"kind": "fixed_length", "expression": length_expression, "value": length_value, "error": str(exc)})
    report["created_count"] = len([item for item in report["applied"] if item.get("created")])
    return report


def _coerce_xy(value):
    if value is None:
        return None
    if isinstance(value, tuple) or isinstance(value, list):
        if len(value) >= 3 and isinstance(value[0], bool):
            if not value[0]:
                return None
            try:
                return [float(value[1]), float(value[2])]
            except Exception:
                return None
        if len(value) >= 2:
            try:
                return [float(value[0]), float(value[1])]
            except Exception:
                return None
    x = safe_get(value, "X", None)
    y = safe_get(value, "Y", None)
    if x is not None and y is not None:
        try:
            return [float(x), float(y)]
        except Exception:
            return None
    return None


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
            current_visible = safe_get(model_object, "Visible")
            if update_ok and current_visible is not None:
                report["visible_fallback_before"] = bool(current_visible)
                try:
                    model_object.Visible = not bool(hidden)
                    visible_update_ok = commit_visibility_update()
                    applied_visible = safe_get(model_object, "Visible")
                    report["visible_fallback_after"] = bool(applied_visible) if applied_visible is not None else None
                    report["ok"] = applied_visible is not None and bool(applied_visible) == (not bool(hidden)) and visible_update_ok
                    if report["ok"]:
                        report["reason"] = "hidden_property_ignored_visible_fallback_applied"
                        return report
                except Exception as exc:
                    report["visible_fallback_error"] = str(exc)
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
    seen = set()

    def add_items(items):
        added = 0
        for item in items:
            if item is None:
                continue
            key = (
                safe_get(item, "Name"),
                safe_get(item, "ParameterNote"),
                safe_get(item, "Reference"),
                id(item),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
            added += 1
        return added

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
                    batch.append(item)
                add_items(batch)
                if result and not failed:
                    break

    try:
        add_items([item for item in variables])
    except Exception:
        pass
    return result


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


def _set_operation_variable_value(model_object, *, parameter_note=None, parameter_note_aliases=None, value=None, role=None):
    report = {"ok": False, "role": role, "parameter_note": parameter_note, "value": value, "attempts": []}
    variables = _iter_operation_variables(model_object)
    if not variables:
        report["error"] = "operation_variables_unavailable"
        return report
    aliases = []
    if parameter_note not in (None, ""):
        aliases.append(str(parameter_note))
    aliases.extend([str(item) for item in (parameter_note_aliases or []) if str(item or "").strip()])
    for variable in variables:
        note = str(safe_get(variable, "ParameterNote", "") or "")
        name = str(safe_get(variable, "Name", "") or "")
        if aliases and note not in aliases:
            continue
        attempt = {"name": name, "parameter_note": note, "expression_before": safe_get(variable, "Expression"), "value_before": safe_get(variable, "Value")}
        try:
            variable.Expression = ""
            variable.Value = float(value)
            update = safe_get(variable, "Update")
            attempt["variable_update_ok"] = bool(update()) if callable(update) else True
            object_update = safe_get(model_object, "Update")
            attempt["object_update_ok"] = bool(object_update()) if callable(object_update) else True
            attempt["expression_after"] = safe_get(variable, "Expression")
            attempt["value_after"] = safe_get(variable, "Value")
            attempt["ok"] = bool(attempt["variable_update_ok"] and attempt["object_update_ok"])
            report["attempts"].append(attempt)
            if attempt["ok"]:
                report["ok"] = True
                report["applied"] = attempt
                return report
        except Exception as exc:
            attempt["ok"] = False
            attempt["error"] = str(exc)
            report["attempts"].append(attempt)
    report["error"] = "operation_variable_not_found_or_update_failed"
    return report


def _bind_extrusion_operation_variables(extrusion, params, scenario, target="extrusion"):
    planned_bindings = list(params.get("operation_variable_bindings") or [])
    if not planned_bindings:
        return None
    report = _bind_operation_variables(extrusion, planned_bindings)
    report["scenario"] = scenario
    report["target"] = target
    return report


def _bind_circular_pattern_operation_variables(pattern, params, scenario, target="circular_pattern"):
    planned_bindings = list(params.get("pattern_operation_variable_bindings") or [])
    if not planned_bindings:
        return None
    report = _bind_operation_variables(pattern, planned_bindings)
    report["scenario"] = scenario
    report["target"] = target
    return report


SPRING_ANCHOR_ROTATION_PARAMETER_NOTES = (
    "Angle",
    "Угол",
    "Rotation",
    "Rotation angle",
    "Angle of rotation",
    "Угол вращения",
    "Вращение",
)


def _build_spring_anchor_rotation_binding(expression):
    return {
        "target": "spiral_path",
        "parameter_note": "Angle",
        "parameter_note_aliases": list(SPRING_ANCHOR_ROTATION_PARAMETER_NOTES),
        "expression": str(expression),
        "role": "spring_anchor_rotation",
    }


def _build_post_save_compression_spring_anchor_rotation_bindings(segment_plan):
    planned = []
    for segment in segment_plan or []:
        expression_raw = segment.get("anchor_rotation_expression")
        if expression_raw in (None, ""):
            continue
        expression = str(expression_raw).strip()
        if not expression:
            continue
        path_name = str(segment.get("path_name") or "").strip()
        if not path_name:
            continue
        planned.append(
            {
                "role": str(segment.get("role") or "segment"),
                "path_name": path_name,
                "expression": expression,
            }
        )
    return planned


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
SKETCH_CONSTRAINT_TYPE_NAMES = {value: key for key, value in SKETCH_CONSTRAINT_TYPES.items()}
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


def _sketch_full_scalar(value):
    if value is None or callable(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        return float(value)
    except Exception:
        return str(value)


def _sketch_full_json_safe(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _sketch_full_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sketch_full_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_sketch_full_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_sketch_full_json_safe(item) for item in value]
    scalar = _sketch_full_scalar(value)
    if scalar is not None:
        return scalar
    try:
        return str(value)
    except Exception:
        return None


def _describe_sketch_reference_object(obj):
    if obj is None:
        return None
    data = {"type": type(obj).__name__}
    for attr in ("Name", "Reference", "Type", "UniqueNumber", "UniqueMetaObjectKey"):
        value = safe_get(obj, attr)
        if value is not None:
            data[attr[:1].lower() + attr[1:]] = _sketch_full_json_safe(value)
    parameters = safe_get(obj, "LocalCSParameters")
    if parameters is not None:
        param_data = {"type": type(parameters).__name__}
        for attr in (
            "X", "Y", "Z", "Angle", "RotateAngle", "AngleX", "AngleY", "AngleZ",
            "EulerAngleX", "EulerAngleY", "EulerAngleZ", "Ox", "Oy", "Oz",
            "Direction", "DirectionX", "DirectionY", "DirectionZ", "ReverseZ", "AxisZDirection",
        ):
            value = safe_get(parameters, attr)
            if value is not None:
                param_data[attr] = _sketch_full_json_safe(value)
        data["localCSParameters"] = param_data
    return data


def _read_sketch_placement_diagnostics(sketch):
    result = {}
    for attr in (
        "Name", "Reference", "Status", "State", "X", "Y", "Z", "Angle", "RotateAngle",
        "OffsetX", "OffsetY", "OffsetZ", "Direction", "DirectionX", "DirectionY", "DirectionZ",
        "ReverseZ", "AxisZDirection", "ConstructionMethod", "BuildMethod", "PlacementMode",
    ):
        value = safe_get(sketch, attr)
        if value is not None:
            result[attr] = _sketch_full_json_safe(value)
    result["plane"] = _describe_sketch_reference_object(safe_get(sketch, "Plane"))
    result["coordinateSystem"] = _describe_sketch_reference_object(safe_get(sketch, "CoordinateSystem"))
    prop_map = getattr(sketch, "_prop_map_get_", None)
    if isinstance(prop_map, dict):
        result["availableProperties"] = sorted(str(name) for name in prop_map.keys())[:200]
    return result


def _read_sketch_full_properties(entity, names):
    data = {}
    for name in names:
        try:
            value = safe_get(entity, name)
            if value is None or callable(value):
                continue
            data[name] = _sketch_full_json_safe(value)
        except Exception as exc:
            data[name] = {"error": str(exc)}
    return data


def _read_sketch_full_methods(entity, names):
    data = {}
    for name in names:
        method = safe_get(entity, name)
        if not callable(method):
            continue
        try:
            value = method()
            if value is not None:
                data[name] = _sketch_full_json_safe(value)
        except Exception as exc:
            data[name] = {"error": str(exc)}
    return data


def _describe_sketch_full_related_object(obj):
    if obj is None or callable(obj):
        return None
    data = {
        "com_type": obj.__class__.__name__,
        "reference": _sketch_full_json_safe(safe_get(obj, "Reference")),
        "type": _sketch_full_json_safe(safe_get(obj, "Type", safe_get(obj, "ObjType"))),
        "name": _sketch_full_json_safe(safe_get(obj, "Name")),
    }
    return {key: value for key, value in data.items() if value not in (None, "")}


def _read_sketch_full_object_details(obj, property_names=None, method_names=None, related_names=None):
    if obj is None:
        return None
    data = {"com_type": obj.__class__.__name__}
    available_properties = sorted(
        set(getattr(obj, "_prop_map_get_", {}) or {}).union(set(getattr(obj, "_prop_map_put_", {}) or {}))
    )
    if available_properties:
        data["available_properties"] = available_properties
    available_methods = [str(item) for item in (getattr(obj, "_methods_", []) or [])]
    if available_methods:
        data["available_methods"] = available_methods
    properties = _read_sketch_full_properties(obj, property_names or ())
    if properties:
        data["properties"] = properties
    methods = _read_sketch_full_methods(obj, method_names or ())
    if methods:
        data["methods"] = methods
    related = {}
    for name in related_names or ():
        value = safe_get(obj, name)
        if value is None or callable(value):
            continue
        related_value = _describe_sketch_full_related_object(value)
        if related_value is not None:
            related[name] = related_value
    if related:
        data["related"] = related
    return data


_SKETCH_COMMON_PROPERTY_NAMES = (
    "Name",
    "Reference",
    "Type",
    "ObjType",
    "Layer",
    "Style",
    "Color",
    "Visible",
    "Hidden",
    "Fixed",
    "Construction",
    "Auxiliary",
    "Deletable",
    "Changed",
    "X",
    "Y",
    "X1",
    "Y1",
    "X2",
    "Y2",
    "Xc",
    "Yc",
    "Radius",
    "Angle",
    "Direction",
)


_SKETCH_DIMENSION_PROPERTY_NAMES = (
    "Name",
    "Reference",
    "Type",
    "DimensionType",
    "ObjType",
    "Value",
    "NominalValue",
    "Text",
    "Expression",
    "ExpressionText",
    "Formula",
    "Variable",
    "VariableName",
    "VariableExpression",
    "ValueExpression",
    "Prefix",
    "Suffix",
    "Tolerance",
    "IsReference",
    "Driving",
    "Driven",
    "Hidden",
    "Visible",
)


_SKETCH_NESTED_PARAMETER_NAMES = (
    "Name",
    "Text",
    "Value",
    "Expression",
    "ExpressionText",
    "Formula",
    "Variable",
    "VariableName",
    "VariableExpression",
    "Prefix",
    "Suffix",
)


_SKETCH_CONSTRAINT_PROPERTY_NAMES = (
    "Name",
    "Reference",
    "Type",
    "Kind",
    "ConstraintType",
    "Value",
    "Expression",
    "Formula",
    "Variable",
    "VariableName",
    "Fixed",
    "Solved",
    "Enabled",
    "Suppressed",
    "Driving",
    "Driven",
)


_SKETCH_RELATED_OBJECT_NAMES = (
    "Object",
    "FirstObject",
    "SecondObject",
    "Object1",
    "Object2",
    "Entity",
    "FirstEntity",
    "SecondEntity",
    "Curve",
    "Point",
    "Point1",
    "Point2",
)


_API5_LIBID = "{0422828C-F174-495E-AC5D-D31014DBBE87}"
_API5_KO_CONSTRAINT_PARAM = 89
_API5_KO_ARC_BY_ANGLE_PARAM = 12
_API5_KO_ARC_BY_POINT_PARAM = 13
_API5_CONSTRAINT_TYPE_NAMES = {
    0: "unknown",
    1: "fixed_point",
    2: "point_on_curve",
    3: "horizontal",
    4: "vertical",
    5: "parallel",
    6: "perpendicular",
    7: "equal_length",
    8: "equal_radius",
    9: "horizontal_align_points",
    10: "vertical_align_points",
    11: "merge_points",
    12: "association",
    13: "dimension_with_variable",
    14: "fixed_dimension",
    15: "tangent_two_curves",
    16: "symmetry_two_points",
    17: "collinear",
    18: "fixed_angle",
    19: "fixed_length",
    20: "point_on_curve_middle",
    21: "bisector",
    22: "concentricity",
}


def _get_api5_kompas_object():
    try:
        import win32com.client
        import win32com.client.gencache

        api5_module = win32com.client.gencache.EnsureModule(_API5_LIBID, 0, 1, 0)
        raw_app = win32com.client.Dispatch("KOMPAS.Application.5")
        app5 = api5_module.KompasObject(raw_app._oleobj_)
        return app5, api5_module, {"ok": True, "class": app5.__class__.__name__}
    except Exception as exc:
        return None, None, {"ok": False, "error": str(exc)}


def _get_api5_document2d():
    app5, api5_module, status = _get_api5_kompas_object()
    if app5 is None:
        return None, status
    try:
        raw_doc2d = app5.ActiveDocument2D()
        if raw_doc2d is None:
            return None, {"ok": False, "error": "ActiveDocument2D returned None"}
        doc2d = api5_module.ksDocument2D(raw_doc2d._oleobj_)
        return doc2d, {"ok": True, "class": doc2d.__class__.__name__}
    except Exception as exc:
        return None, {"ok": False, "error": str(exc)}


def _read_api5_dynamic_array(array, max_items=20, item_struct_type=None):
    if array is None:
        return None
    data = {"class": array.__class__.__name__}
    count_method = safe_get(array, "ksGetArrayCount")
    if callable(count_method):
        try:
            count = count_method()
            data["count"] = _sketch_full_json_safe(count)
        except Exception as exc:
            data["count_error"] = str(exc)
            count = 0
    else:
        count = collection_count(array)
        if count:
            data["count"] = count
    get_item = safe_get(array, "ksGetArrayItem")
    array_type = None
    get_array_type = safe_get(array, "ksGetArrayType")
    if callable(get_array_type):
        try:
            array_type = get_array_type()
            data["array_type"] = _sketch_full_json_safe(array_type)
        except Exception as exc:
            data["array_type_error"] = str(exc)
    if callable(get_item) and isinstance(count, int) and count > 0:
        app5, _api5_module, app5_status = _get_api5_kompas_object()
        data["param_factory"] = app5_status
        data["items"] = []
        for index in range(min(count, max_items)):
            try:
                struct_type = item_struct_type if item_struct_type not in (None, "") else array_type
                param = app5.GetParamStruct(struct_type) if app5 is not None and struct_type not in (None, "") else None
                init = safe_get(param, "Init")
                if callable(init):
                    try:
                        init()
                    except Exception:
                        pass
                value = get_item(index, param)
                properties = _read_sketch_full_properties(param, ("constrType", "index", "partner", "partnerIndex")) if param is not None else {}
                if "constrType" in properties:
                    properties["constraint_kind"] = _API5_CONSTRAINT_TYPE_NAMES.get(properties.get("constrType"), "unknown")
                data["items"].append({
                    "index": index,
                    "return_code": _sketch_full_json_safe(value),
                    "class": None if param is None else param.__class__.__name__,
                    "struct_type": _sketch_full_json_safe(struct_type),
                    "properties": properties,
                    "details": _read_sketch_full_object_details(param) if param is not None else None,
                })
            except Exception as exc:
                data["items"].append({"index": index, "error": str(exc)})
        data["truncated"] = count > max_items
    return data


def _read_api5_dimension_diagnostics(api5_doc2d, dimension_ref):
    if api5_doc2d is None or dimension_ref in (None, ""):
        return None
    data = {"dimension_ref": _sketch_full_json_safe(dimension_ref)}
    get_name = safe_get(api5_doc2d, "ksGetDimensionVariableName")
    if callable(get_name):
        try:
            data["dimension_variable_name"] = _sketch_full_json_safe(get_name(dimension_ref))
        except Exception as exc:
            data["dimension_variable_name_error"] = str(exc)
    get_constraints = safe_get(api5_doc2d, "ksGetObjConstraints")
    if callable(get_constraints):
        try:
            data["constraints"] = _read_api5_dynamic_array(get_constraints(dimension_ref), item_struct_type=_API5_KO_CONSTRAINT_PARAM)
        except Exception as exc:
            data["constraints_error"] = str(exc)
    return data


def _read_api5_object_diagnostics(api5_doc2d, object_ref):
    if api5_doc2d is None or object_ref in (None, ""):
        return None
    data = {"object_ref": _sketch_full_json_safe(object_ref)}
    get_constraints = safe_get(api5_doc2d, "ksGetObjConstraints")
    if callable(get_constraints):
        try:
            data["constraints"] = _read_api5_dynamic_array(get_constraints(object_ref), item_struct_type=_API5_KO_CONSTRAINT_PARAM)
        except Exception as exc:
            data["constraints_error"] = str(exc)
    return data


def _api5_arc_geometry_from_param(param):
    if param is None:
        return None
    props = _read_sketch_full_properties(param, ("xc", "yc", "rad", "x1", "y1", "x2", "y2", "ang1", "ang2", "dir", "style"))
    if not props:
        return None
    geometry = {"center": [props.get("xc"), props.get("yc")], "radius": props.get("rad"), "direction": props.get("dir")}
    if props.get("x1") is not None or props.get("y1") is not None:
        geometry["start"] = [props.get("x1"), props.get("y1")]
    if props.get("x2") is not None or props.get("y2") is not None:
        geometry["end"] = [props.get("x2"), props.get("y2")]
    if props.get("ang1") is not None or props.get("ang2") is not None:
        geometry["angles"] = [props.get("ang1"), props.get("ang2")]
    return {key: value for key, value in geometry.items() if value is not None}


def _read_api5_arc_diagnostics(api5_doc2d, arc_ref):
    if api5_doc2d is None or arc_ref in (None, ""):
        return None
    app5, _api5_module, app5_status = _get_api5_kompas_object()
    data = {"object_ref": _sketch_full_json_safe(arc_ref), "param_factory": app5_status, "attempts": []}
    if app5 is None:
        return data
    for label, struct_type in (("arc_by_point", _API5_KO_ARC_BY_POINT_PARAM), ("arc_by_angle", _API5_KO_ARC_BY_ANGLE_PARAM)):
        attempt = {"label": label, "struct_type": struct_type}
        try:
            param = app5.GetParamStruct(struct_type)
            init = safe_get(param, "Init")
            if callable(init):
                init()
            ok = api5_doc2d.ksGetObjParam(arc_ref, param, struct_type)
            attempt["ok"] = _sketch_full_json_safe(ok)
            attempt["properties"] = _read_sketch_full_properties(param, ("xc", "yc", "rad", "x1", "y1", "x2", "y2", "ang1", "ang2", "dir", "style"))
            attempt["geometry"] = _api5_arc_geometry_from_param(param)
            attempt["details"] = _read_sketch_full_object_details(param)
            if ok and attempt.get("geometry"):
                data["geometry"] = attempt["geometry"]
                data["param_kind"] = label
        except Exception as exc:
            attempt["error"] = str(exc)
        data["attempts"].append(attempt)
    return data


def _collect_variable_definitions_from_surface_report(surface_report):
    definitions = {}

    def add_item(item):
        if not isinstance(item, dict):
            return
        props = item.get("properties") or {}
        name = props.get("Name")
        if name not in (None, ""):
            definitions[str(name)] = item

    def walk(value):
        if isinstance(value, dict):
            for item in value.get("items") or ():
                add_item(item)
            for item in value.get("iter_operation_variables") or ():
                add_item(item)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(surface_report)
    return definitions


def _link_dimension_variables_from_diagnostics(result):
    diagnostics = result.get("diagnostics") or {}
    definitions = _collect_variable_definitions_from_surface_report(diagnostics.get("variable_surfaces") or {})
    if not definitions:
        return
    linked = 0
    for item in ((result.get("dimensions") or {}).get("items") or ()):
        api5 = item.get("api5") if isinstance(item, dict) else None
        if not isinstance(api5, dict):
            continue
        name = api5.get("dimension_variable_name")
        if name not in (None, "") and str(name) in definitions:
            api5["dimension_variable"] = definitions[str(name)]
            linked += 1
    if linked:
        result.setdefault("summary", {})["dimension_variables_linked"] = linked


def _build_sketch_entity_reference_index(entities):
    index = {}
    for entity in entities or ():
        if not isinstance(entity, dict):
            continue
        reference = entity.get("reference")
        if reference not in (None, ""):
            index[str(reference)] = entity
    return index


def _build_sketch_dimension_reference_index(dimensions):
    index = {}
    for dimension in dimensions or ():
        if not isinstance(dimension, dict):
            continue
        api5 = dimension.get("api5") if isinstance(dimension.get("api5"), dict) else {}
        for reference in (dimension.get("dimension_ref"), api5.get("dimension_ref")):
            if reference not in (None, ""):
                index[str(reference)] = dimension
    return index


def _sketch_object_link(item, object_kind=None):
    if not isinstance(item, dict):
        return None
    if object_kind == "dimension" or item.get("dimension_type") is not None or item.get("dimension_ref") is not None:
        api5 = item.get("api5") if isinstance(item.get("api5"), dict) else {}
        return {
            "kind": "dimension",
            "index": item.get("index"),
            "dimension_type": item.get("dimension_type"),
            "dimension_ref": item.get("dimension_ref") or api5.get("dimension_ref"),
            "variable_name": api5.get("dimension_variable_name"),
            "variable_value": api5.get("dimension_variable_value"),
            "value": item.get("value"),
        }
    return {
        "kind": item.get("kind"),
        "collection_name": item.get("collection_name"),
        "index": item.get("index"),
        "reference": item.get("reference"),
        "fingerprint": item.get("fingerprint"),
        "name": item.get("name"),
        "geometry": item.get("geometry"),
    }


def _sketch_entity_link(entity):
    return _sketch_object_link(entity)


def _resolve_sketch_object_link(entity_index, dimension_index, reference):
    if reference in (None, ""):
        return None
    key = str(reference)
    if key in entity_index:
        return _sketch_object_link(entity_index.get(key))
    if key in dimension_index:
        return _sketch_object_link(dimension_index.get(key), object_kind="dimension")
    return None


def _resolve_sketch_entity_link(entity_index, reference):
    return _resolve_sketch_object_link(entity_index, {}, reference)


def _enrich_dimension_api5_constraint_partners(dimensions, entities):
    entity_index = _build_sketch_entity_reference_index(entities)
    dimension_index = _build_sketch_dimension_reference_index(dimensions)
    for dimension in dimensions or ():
        constraints = (((dimension.get("api5") or {}).get("constraints") or {}).get("items") or ()) if isinstance(dimension, dict) else ()
        for constraint in constraints:
            properties = constraint.get("properties") if isinstance(constraint, dict) else None
            if not isinstance(properties, dict):
                continue
            partner = properties.get("partner")
            partner_object = _resolve_sketch_object_link(entity_index, dimension_index, partner)
            if partner_object:
                constraint["partner_object"] = partner_object


def _collect_api5_constraints_from_entities(entities, dimensions=None):
    items = []
    seen = set()
    entity_index = _build_sketch_entity_reference_index(entities)
    dimension_index = _build_sketch_dimension_reference_index(dimensions)
    for entity in entities or ():
        if not isinstance(entity, dict):
            continue
        constraints = (((entity.get("api5") or {}).get("constraints") or {}).get("items") or ())
        owner = {
            "kind": entity.get("kind"),
            "collection_name": entity.get("collection_name"),
            "index": entity.get("index"),
            "reference": entity.get("reference"),
            "fingerprint": entity.get("fingerprint"),
        }
        for constraint in constraints:
            properties = constraint.get("properties") if isinstance(constraint, dict) else None
            if not isinstance(properties, dict):
                continue
            key = (
                owner.get("reference"),
                properties.get("constrType"),
                properties.get("index"),
                properties.get("partner"),
                properties.get("partnerIndex"),
            )
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "source": "api5.ksGetObjConstraints",
                "owner": owner,
                "index": constraint.get("index"),
                "return_code": constraint.get("return_code"),
                "struct_type": constraint.get("struct_type"),
                "constraint_type": properties.get("constrType"),
                "kind": properties.get("constraint_kind"),
                "point_index": properties.get("index"),
                "partner_reference": properties.get("partner"),
                "partner_index": properties.get("partnerIndex"),
                "properties": properties,
            })
            current = items[-1]
            owner_object = _sketch_entity_link(entity)
            partner_object = _resolve_sketch_object_link(entity_index, dimension_index, properties.get("partner"))
            if owner_object:
                constraint["owner_object"] = owner_object
                current["owner_object"] = owner_object
            if partner_object:
                constraint["partner_object"] = partner_object
                current["partner_object"] = partner_object
    return items


def _projection_classification(entity):
    projection = entity.get("projection") if isinstance(entity, dict) else None
    classification = projection.get("classification") if isinstance(projection, dict) else None
    return classification if isinstance(classification, dict) else {}


def _classify_projection_links(result):
    entities = result.get("entities") or []
    entity_index = _build_sketch_entity_reference_index(entities)
    projected_objects = []
    projection_items = []

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        classification = _projection_classification(entity)
        if not classification.get("is_projected_candidate"):
            continue
        style = classification.get("style")
        parent_type = classification.get("parent_type")
        if parent_type == 10031 and style == 6:
            classification["projection_role"] = "projection_reference_geometry_candidate"
        elif parent_type == 10031:
            classification["projection_role"] = "projected_object_candidate"
            link = {
                "source": "heuristic.parent_type_10031_style_not_6",
                "ui_name": "проекционная связь",
                "kind": "projection_link_candidate",
                "owner_object": _sketch_entity_link(entity),
                "parent_reference": classification.get("parent_reference"),
            }
            entity.setdefault("projection", {}).setdefault("ui_constraints", []).append(link)
            projected_objects.append(entity)
            projection_items.append(link)

    for constraint in (((result.get("constraints") or {}).get("all_items")) or []):
        if not isinstance(constraint, dict):
            continue
        owner_ref = (constraint.get("owner") or {}).get("reference")
        owner = entity_index.get(str(owner_ref)) if owner_ref not in (None, "") else None
        partner_ref = constraint.get("partner_reference")
        partner = entity_index.get(str(partner_ref)) if partner_ref not in (None, "") else None
        owner_classification = _projection_classification(owner or {})
        partner_classification = _projection_classification(partner or {})
        if (
            owner_classification.get("projection_role") == "projected_object_candidate"
            and constraint.get("kind") == "point_on_curve"
            and partner_classification.get("projection_role") == "projection_reference_geometry_candidate"
        ):
            constraint["projection_constraint_role"] = "endpoint_projection_candidate"
            constraint["ui_name"] = "проекция конечной точки"
            projection_items.append(constraint)

    if projection_items:
        result.setdefault("constraints", {})["projection_items"] = projection_items
        result.setdefault("constraints", {}).setdefault("summary", {})["projection_constraint_count"] = len(projection_items)
        result.setdefault("summary", {})["projection_constraint_count"] = len(projection_items)
    if projected_objects:
        result.setdefault("summary", {})["projected_object_count"] = len(projected_objects)


_SKETCH_VARIABLE_PROPERTY_NAMES = (
    "Name",
    "ParameterNote",
    "Note",
    "Expression",
    "Value",
    "External",
    "ReadOnly",
    "Type",
    "Reference",
)


def _read_sketch_variable_item(variable):
    if variable is None:
        return None
    return {
        "class": variable.__class__.__name__,
        "properties": _read_sketch_full_properties(variable, _SKETCH_VARIABLE_PROPERTY_NAMES),
        "details": _read_sketch_full_object_details(variable, _SKETCH_VARIABLE_PROPERTY_NAMES),
    }


def _append_sketch_variable_items(target, variables, max_items):
    if isinstance(variables, (list, tuple)):
        target["count"] = len(variables)
        for index, variable in enumerate(variables[:max_items]):
            item = _read_sketch_variable_item(variable)
            if item is not None:
                item["index"] = index
                target["items"].append(item)
        target["truncated"] = len(variables) > max_items
        return True
    count = collection_count(variables)
    if count:
        target["count"] = count
        for index in range(min(count, max_items)):
            item = _read_sketch_variable_item(get_collection_item(variables, index))
            if item is not None:
                item["index"] = index
                target["items"].append(item)
        target["truncated"] = count > max_items
        return True
    item = _read_sketch_variable_item(variables)
    if item is not None:
        target["items"].append(item)
        target["count"] = 1
        return True
    return False


def _resolve_variables_surface(obj):
    variables = safe_get(obj, "Variables")
    attempts = []
    if callable(variables):
        for args in ((False, False), (True, True), (False,), (True,), tuple()):
            try:
                value = variables(*args)
                attempts.append({"args": list(args), "ok": True, "class": None if value is None else value.__class__.__name__})
                if value is not None:
                    return value, attempts
            except Exception as exc:
                attempts.append({"args": list(args), "ok": False, "error": str(exc)})
        return None, attempts
    return variables, attempts


def _read_sketch_variable_surfaces(obj, max_items=50):
    if obj is None or callable(obj):
        return None
    surfaces = []
    seen = set()
    candidates = [
        ("self", obj),
        ("owner", safe_get(obj, "Owner")),
        ("owner_owner", safe_get(safe_get(obj, "Owner"), "Owner")),
    ]
    for label, candidate in candidates:
        if candidate is None or callable(candidate):
            continue
        identity = id(candidate)
        if identity in seen:
            continue
        seen.add(identity)
        variables, attempts = _resolve_variables_surface(candidate)
        surface = {
            "label": label,
            "object_class": candidate.__class__.__name__,
            "variables_class": None if variables is None else variables.__class__.__name__,
            "variables_call_attempts": attempts,
            "variables_properties": _read_sketch_full_properties(variables, ("Count", "Length", "Name", "ParameterNote", "Expression", "Value", "Type", "Reference")) if variables is not None else {},
            "items": [],
        }
        _append_sketch_variable_items(surface, variables, max_items)
        surfaces.append(surface)
    iter_items = []
    try:
        for index, variable in enumerate(_iter_operation_variables(obj)):
            if index >= max_items:
                iter_items.append({"truncated": True, "max_items": max_items})
                break
            item = _read_sketch_variable_item(variable)
            if item is not None:
                item["index"] = index
                iter_items.append(item)
    except Exception as exc:
        iter_items.append({"error": str(exc)})
    return {"object_class": obj.__class__.__name__, "surfaces": surfaces, "iter_operation_variables": iter_items}


def _read_sketch_api5_surface_diagnostics(app7, edit_doc):
    diagnostics = {"available": False, "attempts": []}
    app5 = _APP5
    if app5 is None:
        return diagnostics
    diagnostics["available"] = True
    for name in ("ActiveDocument", "ActiveDocument2D", "ActiveDocument3D", "Document2D", "Document3D"):
        value = safe_get(app5, name)
        entry = {"target": "app5", "name": name, "callable": callable(value)}
        if callable(value):
            for args in (tuple(), (0,), (1,), (-1,)):
                try:
                    result = value(*args)
                    entry.setdefault("calls", []).append({"args": list(args), "ok": True, "class": None if result is None else result.__class__.__name__, "value": _sketch_full_json_safe(result)})
                    if result is not None:
                        break
                except Exception as exc:
                    entry.setdefault("calls", []).append({"args": list(args), "ok": False, "error": str(exc)})
        else:
            entry["value"] = _sketch_full_json_safe(value)
            entry["class"] = None if value is None else value.__class__.__name__
        diagnostics["attempts"].append(entry)
    if edit_doc is not None:
        diagnostics["edit_doc"] = _read_sketch_full_object_details(edit_doc, ("DocumentType", "Active", "Name", "Path"), ("ksGetDocument2D", "GetDocument2D", "Document2D"))
    active = safe_get(app7, "ActiveDocument") if app7 is not None else None
    diagnostics["api7_active_document"] = describe_document(active, app7) if active is not None else None
    return diagnostics


def _read_sketch_full_point(entity, names):
    for name in names:
        point = safe_get(entity, name)
        if point is None or callable(point):
            continue
        x = safe_get(point, "X")
        y = safe_get(point, "Y")
        if x is not None or y is not None:
            return {"source": name, "x": _sketch_full_scalar(x), "y": _sketch_full_scalar(y)}
    return None


def _extract_sketch_ref(payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    return target.get("sketch_ref", payload.get("sketch_ref"))


def _inspect_sketch_full_entity(entity, *, entity_kind, collection_name, index):
    interface_name = {
        "segment": "ILineSegment",
        "arc": "IArc",
        "circle": "ICircle",
        "point": "IPoint",
        "ellipse": "IEllipse",
    }.get(entity_kind)
    if interface_name:
        try:
            entity = _cast_to_com_interface(entity, interface_name)
        except Exception:
            pass
    raw_properties = _read_sketch_full_properties(entity, _SKETCH_COMMON_PROPERTY_NAMES)
    geometry = _sketch_entity_geometry(entity_kind, entity)
    item = {
        "kind": entity_kind,
        "collection_name": collection_name,
        "index": index,
        "reference": _sketch_full_scalar(safe_get(entity, "Reference")),
        "name": _sketch_full_scalar(safe_get(entity, "Name", "")),
        "constraints_state": _describe_constraints_state(safe_get(entity, "ConstraintsState")),
        "geometry": geometry,
        "raw_properties": raw_properties,
        "points": {},
    }
    projection = _read_sketch_entity_projection_link(entity)
    if projection:
        item["projection"] = projection
    item["fingerprint"] = _sketch_entity_fingerprint(entity_kind, geometry or {}, item.get("reference"))
    for label, names in {
        "start": ("StartPoint", "Point1", "P1", "BeginPoint"),
        "end": ("EndPoint", "Point2", "P2", "FinishPoint"),
        "center": ("Center", "CenterPoint", "ArcCenter"),
    }.items():
        point = _read_sketch_full_point(entity, names)
        if point is not None:
            item["points"][label] = point
    return item


def _attach_sketch_constraints_to_entities(entities, constraints):
    by_fingerprint = {}
    by_reference = {}
    for entity in entities:
        fingerprint = entity.get("fingerprint")
        reference = entity.get("reference")
        if fingerprint not in (None, ""):
            by_fingerprint[str(fingerprint)] = entity
        if reference not in (None, ""):
            by_reference[str(reference)] = entity
    for constraint in constraints:
        owner = constraint.get("owner") if isinstance(constraint, dict) else {}
        entity = None
        owner_fingerprint = owner.get("fingerprint") if isinstance(owner, dict) else None
        owner_reference = owner.get("reference") if isinstance(owner, dict) else None
        if owner_fingerprint not in (None, ""):
            entity = by_fingerprint.get(str(owner_fingerprint))
        if entity is None and owner_reference not in (None, ""):
            entity = by_reference.get(str(owner_reference))
        if entity is not None:
            entity.setdefault("constraints", []).append(constraint)
    for entity in entities:
        entity["constraint_count"] = len(entity.get("constraints") or [])


def _inspect_sketch_full_collection(drawing_container, collection_name, accessors, entity_kind, *, max_items):
    collection, accessor_used, accessor_attempts = _resolve_model_object_collection(drawing_container, accessors)
    count = collection_count(collection)
    result = {
        "collection_name": collection_name,
        "kind": entity_kind,
        "accessor_used": accessor_used,
        "accessor_attempts": accessor_attempts,
        "count": count,
        "items": [],
        "errors": [],
    }
    for index in range(min(count, max_items)):
        try:
            entity = get_collection_item(collection, index)
            if entity is None:
                result["errors"].append({"index": index, "error": "item_not_found"})
                continue
            result["items"].append(_inspect_sketch_full_entity(entity, entity_kind=entity_kind, collection_name=collection_name, index=index))
        except Exception as exc:
            result["errors"].append({"index": index, "error": str(exc)})
    return result


def _sketch_projection_object_payload(obj):
    if obj is None:
        return None
    payload = {
        "class": obj.__class__.__name__,
        "properties": _read_sketch_full_properties(
            obj,
            (
                "Name", "Reference", "Type", "ObjType", "FeatureType", "ModelObjectType",
                "IsSketchEdge", "IsLineSeg", "IsArc", "IsCircle", "IsStraight", "IsPlanar",
                "Hidden", "Valid",
            ),
        ),
    }
    related = {}
    for name in ("Owner", "Parent", "Part", "Body", "AssociationObject"):
        value = safe_get(obj, name)
        if value is not None:
            related[name] = {
                "class": value.__class__.__name__,
                "properties": _read_sketch_full_properties(value, ("Name", "Reference", "Type", "ObjType", "FeatureType", "ModelObjectType")),
            }
    if related:
        payload["related"] = related
    methods = {}
    for name in ("GetAssociation", "GetSource", "GetSourceObject", "GetProjection", "GetProjectionSource", "GetReferenceObject", "GetObject"):
        method = safe_get(obj, name)
        if not callable(method):
            continue
        attempts = []
        for args in (tuple(), (0,), (1,), (False,), (True,)):
            try:
                value = method(*args)
                attempts.append({
                    "args": list(args),
                    "ok": True,
                    "class": None if value is None else value.__class__.__name__,
                    "properties": _read_sketch_full_properties(value, ("Name", "Reference", "Type", "ObjType", "FeatureType", "ModelObjectType")) if value is not None else {},
                })
                if value is not None:
                    break
            except Exception as exc:
                attempts.append({"args": list(args), "ok": False, "error": str(exc)})
        methods[name] = attempts
    if methods:
        payload["methods"] = methods
    payload["details"] = _read_sketch_full_object_details(
        obj,
        ("Name", "Reference", "Type", "ObjType", "FeatureType", "ModelObjectType", "Hidden", "Valid"),
        related_names=("Owner", "Parent", "Part", "Body", "AssociationObject"),
    )
    return payload


def _sketch_projection_value_payload(value, max_items=50):
    if isinstance(value, (list, tuple)):
        return {
            "kind": "sequence",
            "count": len(value),
            "items": [_sketch_projection_object_payload(item) for item in value[:max_items]],
            "truncated": len(value) > max_items,
        }
    count = collection_count(value)
    if count:
        return {
            "kind": "collection",
            "class": value.__class__.__name__,
            "count": count,
            "items": [_sketch_projection_object_payload(get_collection_item(value, index)) for index in range(min(count, max_items))],
            "truncated": count > max_items,
        }
    object_payload = _sketch_projection_object_payload(value)
    if object_payload is not None:
        return object_payload
    return {"value": _sketch_full_json_safe(value), "class": None if value is None else value.__class__.__name__}


def _read_sketch_projection_diagnostics(sketch, max_items=50):
    diagnostics = {
        "sketch": _sketch_projection_object_payload(sketch),
        "association_object": _sketch_projection_value_payload(safe_get(sketch, "AssociationObject"), max_items),
        "edges": [],
        "directing_objects": [],
    }
    edges = safe_get(sketch, "Edges")
    if callable(edges):
        for edge_type in range(-1, 10):
            try:
                value = edges(edge_type)
                payload = _sketch_projection_value_payload(value, max_items)
                if payload.get("value") is not None or payload.get("count") or payload.get("items"):
                    diagnostics["edges"].append({"edge_type": edge_type, "result": payload})
            except Exception as exc:
                diagnostics["edges"].append({"edge_type": edge_type, "error": str(exc)})
    directing = safe_get(sketch, "DirectingObject")
    if callable(directing):
        for index in range(0, 10):
            try:
                value = directing(index)
                payload = _sketch_projection_value_payload(value, max_items)
                if payload.get("value") is not None or payload.get("count") or payload.get("items"):
                    diagnostics["directing_objects"].append({"index": index, "result": payload})
            except Exception as exc:
                diagnostics["directing_objects"].append({"index": index, "error": str(exc)})
    for name in ("GetLocation", "GetLoftPoint"):
        method = safe_get(sketch, name)
        if callable(method):
            try:
                diagnostics[name] = _sketch_full_json_safe(method())
            except Exception as exc:
                diagnostics[name] = {"error": str(exc)}
    return diagnostics


def _read_sketch_entity_projection_link(entity, max_items=10):
    data = {"properties": {}, "methods": {}}
    drawing1 = _cast_to_com_interface(entity, "IDrawingObject1")
    if drawing1 is not None:
        data["drawing_object1"] = {
            "class": drawing1.__class__.__name__,
            "properties": _read_sketch_full_properties(
                drawing1,
                (
                    "Id", "IsInAssociationView", "IsVisibleInAssociationView", "IsGeometryObject",
                    "IsAnnotativeObject", "IsCurve", "ConstraintsState",
                ),
            ),
        }
        associate = safe_get(drawing1, "Associate")
        if callable(associate):
            try:
                data["drawing_object1"]["associate_result"] = _sketch_full_json_safe(associate())
            except Exception as exc:
                data["drawing_object1"]["associate_error"] = str(exc)
    for name in (
        "Association", "Associative", "Associated", "Source", "SourceObject",
        "Projection", "ProjectionSource", "ReferenceObject", "External", "Owner", "Parent",
    ):
        value = safe_get(entity, name)
        if value is not None and not callable(value):
            data["properties"][name] = _sketch_projection_value_payload(value, max_items)
    for name in (
        "GetAssociation", "GetSource", "GetSourceObject", "GetProjection",
        "GetProjectionSource", "GetReferenceObject", "GetObject", "GetParent", "GetOwner",
    ):
        method = safe_get(entity, name)
        if not callable(method):
            continue
        attempts = []
        for args in (tuple(), (0,), (1,), (False,), (True,)):
            try:
                value = method(*args)
                attempts.append({"args": list(args), "ok": True, "result": _sketch_projection_value_payload(value, max_items)})
                if value is not None:
                    break
            except Exception as exc:
                attempts.append({"args": list(args), "ok": False, "error": str(exc)})
        data["methods"][name] = attempts
    parent = safe_get(entity, "Parent")
    parent_parent = safe_get(parent, "Parent") if parent is not None else None
    style = _sketch_full_json_safe(safe_get(entity, "Style"))
    parent_type = _sketch_full_json_safe(safe_get(parent, "Type")) if parent is not None else None
    parent_reference = _sketch_full_json_safe(safe_get(parent, "Reference")) if parent is not None else None
    parent_parent_type = _sketch_full_json_safe(safe_get(parent_parent, "Type")) if parent_parent is not None else None
    reasons = []
    if style == 6:
        reasons.append("style_6")
    if parent_type == 10031:
        reasons.append("parent_type_10031")
    if parent_parent_type == 10022:
        reasons.append("parent_parent_type_10022")
    if reasons:
        data["classification"] = {
            "is_projected_candidate": True,
            "reasons": reasons,
            "style": style,
            "parent_type": parent_type,
            "parent_reference": parent_reference,
            "parent_parent_type": parent_parent_type,
        }
    if not data["properties"] and not data["methods"] and "classification" not in data and "drawing_object1" not in data:
        return None
    return data


def _inspect_sketch_full(model_container, payload):
    sketch_ref = _extract_sketch_ref(payload)
    if sketch_ref in (None, ""):
        raise RuntimeError("sketch_ref is required")
    max_items = int(payload.get("max_items") or 200)
    sketch = _resolve_existing_sketch(model_container, sketch_ref)
    if sketch is None:
        raise RuntimeError("Sketch not found: %s" % sketch_ref)
    begin_edit = safe_get(sketch, "BeginEdit")
    end_edit = safe_get(sketch, "EndEdit")
    if not callable(begin_edit):
        result = {
            "sketch_ref": str(sketch_ref),
            "sketch_name": _sketch_full_scalar(safe_get(sketch, "Name", "")),
            "reference": _sketch_full_scalar(safe_get(sketch, "Reference")),
            "placement": _read_sketch_placement_diagnostics(sketch),
            "entities": [],
            "collections": [],
            "summary": {"begin_edit_available": False, "begin_edit_error": "Sketch does not expose BeginEdit"},
            "projection_diagnostics": _read_sketch_projection_diagnostics(sketch, max_items=min(max_items, 50)),
        }
        return _sketch_full_json_safe(result)
    sketch_doc = None
    result = {
        "sketch_ref": str(sketch_ref),
        "sketch_name": _sketch_full_scalar(safe_get(sketch, "Name", "")),
        "reference": _sketch_full_scalar(safe_get(sketch, "Reference")),
        "status": _sketch_full_scalar(safe_get(sketch, "Status", safe_get(sketch, "State"))),
        "placement": _read_sketch_placement_diagnostics(sketch),
        "constraints_state": _describe_constraints_state(safe_get(sketch, "ConstraintsState")),
        "entities": [],
        "collections": [],
        "summary": {},
    }
    try:
        sketch_doc = begin_edit()
        if sketch_doc is None:
            result["summary"] = {"begin_edit_available": False, "begin_edit_error": "BeginEdit returned None"}
            result["projection_diagnostics"] = _read_sketch_projection_diagnostics(sketch, max_items=min(max_items, 50))
            return _sketch_full_json_safe(result)
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        symbols_container = None
        api5_doc2d, api5_doc2d_status = _get_api5_document2d()
        for collection_name, accessors, entity_kind in (
            ("segments", ("LineSegments", "GetLineSegments"), "segment"),
            ("arcs", ("Arcs", "GetArcs"), "arc"),
            ("circles", ("Circles", "GetCircles"), "circle"),
            ("points", ("Points", "GetPoints"), "point"),
            ("ellipses", ("Ellipses", "GetEllipses"), "ellipse"),
        ):
            collection_result = _inspect_sketch_full_collection(drawing_container, collection_name, accessors, entity_kind, max_items=max_items)
            result["collections"].append(collection_result)
            result["entities"].extend(collection_result.get("items", []))
        for entity_item in result["entities"]:
            api5_entity = _read_api5_object_diagnostics(api5_doc2d, entity_item.get("reference"))
            if api5_entity:
                entity_item["api5"] = api5_entity
            if entity_item.get("kind") == "arc":
                api5_arc = _read_api5_arc_diagnostics(api5_doc2d, entity_item.get("reference"))
                if api5_arc:
                    entity_item.setdefault("api5", {})["arc"] = api5_arc
                    if api5_arc.get("geometry"):
                        geometry = entity_item.get("geometry") or {}
                        if not geometry or all(value is None or value == [None, None] for value in geometry.values()):
                            entity_item["geometry"] = api5_arc["geometry"]
        target = {
            "mode": "existing_sketch",
            "name": _sketch_full_scalar(safe_get(sketch, "Name", "")),
            "sketch_ref": _sketch_full_scalar(safe_get(sketch, "Reference", sketch_ref)),
        }
        if bool(payload.get("include_dimensions", True)):
            try:
                symbols_container = _get_sketch_symbols_container(drawing_container)
                kinds = payload.get("dimension_kinds") or payload.get("kinds") or ["line", "break_line", "diametral", "angle"]
                dimension_items, dimension_summary = _collect_existing_sketch_dimensions(
                    symbols_container,
                    kinds,
                    max_items,
                    safe_get(sketch, "Reference", sketch_ref),
                    api5_doc2d,
                )
                dimension_summary["api5_document2d"] = api5_doc2d_status
                _enrich_dimension_api5_constraint_partners(dimension_items, result["entities"])
                result["dimensions"] = {"target": target, "items": dimension_items, "summary": dimension_summary}
            except Exception as exc:
                result["dimensions"] = {"ok": False, "error": str(exc)}
        if bool(payload.get("include_constraints", True)):
            try:
                raw_kinds = payload.get("constraint_kinds")
                if raw_kinds in (None, ""):
                    constraint_kinds = set()
                elif isinstance(raw_kinds, (list, tuple)):
                    constraint_kinds = {str(item or "").strip().lower() for item in raw_kinds}
                else:
                    constraint_kinds = {str(raw_kinds or "").strip().lower()}
                constraint_items, constraint_summary = _scan_existing_sketch_constraints(
                    drawing_container,
                    safe_get(sketch, "Reference", sketch_ref),
                    constraint_kinds,
                    max_items,
                )
                _attach_sketch_constraints_to_entities(result["entities"], constraint_items)
                result["constraints"] = {"target": target, "items": constraint_items, "summary": constraint_summary}
            except Exception as exc:
                result["constraints"] = {"ok": False, "error": str(exc)}
            api5_constraints = _collect_api5_constraints_from_entities(result["entities"], result.get("dimensions", {}).get("items"))
            if isinstance(result.get("constraints"), dict):
                result["constraints"]["api5_items"] = api5_constraints
                result["constraints"].setdefault("summary", {})["api5_constraint_count"] = len(api5_constraints)
                result["constraints"]["all_items"] = (result["constraints"].get("items") or []) + api5_constraints
                result["constraints"]["summary"]["all_constraint_count"] = len(result["constraints"]["all_items"])
                _classify_projection_links(result)
        if bool(payload.get("include_diagnostics", True)):
            if symbols_container is None:
                try:
                    symbols_container = _get_sketch_symbols_container(drawing_container)
                except Exception:
                    symbols_container = None
            diagnostics = {"variable_surfaces": {}}
            for label, obj in (
                ("model_container", model_container),
                ("sketch", sketch),
                ("edit_doc", sketch_doc),
                ("drawing_container", drawing_container),
                ("symbols_container", symbols_container),
            ):
                if obj is not None:
                    diagnostics["variable_surfaces"][label] = _read_sketch_variable_surfaces(obj, max_items=min(max_items, 50))
            app7_for_diag = None
            app7_for_diag = safe_get(sketch_doc, "Application")
            diagnostics["api5_surface"] = _read_sketch_api5_surface_diagnostics(app7_for_diag, sketch_doc)
            result["diagnostics"] = diagnostics
    finally:
        if callable(end_edit) and sketch_doc is not None:
            try:
                end_edit()
            except Exception:
                pass
    result["summary"] = {item["collection_name"]: item["count"] for item in result["collections"]}
    result["summary"]["entity_count"] = len(result["entities"])
    if "dimensions" in result and isinstance(result["dimensions"], dict):
        result["summary"]["dimension_count"] = result["dimensions"].get("summary", {}).get("dimension_count")
    if "constraints" in result and isinstance(result["constraints"], dict):
        result["summary"]["constraint_count"] = result["constraints"].get("summary", {}).get("constraint_count")
        result["summary"]["api5_constraint_count"] = result["constraints"].get("summary", {}).get("api5_constraint_count")
        result["summary"]["all_constraint_count"] = result["constraints"].get("summary", {}).get("all_constraint_count")
        result["summary"]["projection_constraint_count"] = result["constraints"].get("summary", {}).get("projection_constraint_count")
    projected_object_count = sum(1 for entity in result.get("entities", []) if _projection_classification(entity).get("projection_role") == "projected_object_candidate")
    if projected_object_count:
        result["summary"]["projected_object_count"] = projected_object_count
    _link_dimension_variables_from_diagnostics(result)
    return _sketch_full_json_safe(result)


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
            ("spirals3d", ("Spirals3D", "GetSpirals3D")),
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


FEATURE_COLLECTION_SPECS = [
    ("rotated", "rotateds", ("Rotateds", "GetRotateds")),
    ("extrusion", "extrusions", ("Extrusions", "GetExtrusions")),
    ("evolution", "evolutions", ("Evolutions", "GetEvolutions")),
    ("feature_pattern", "feature_patterns", ("FeaturePatterns", "GetFeaturePatterns")),
]


def _normalize_feature_kind(kind):
    value = str(kind or "").strip().lower()
    aliases = {
        "rotate": "rotated",
        "revolve": "rotated",
        "rotateds": "rotated",
        "extrude": "extrusion",
        "extrusions": "extrusion",
        "sweep": "evolution",
        "evolutions": "evolution",
        "pattern": "feature_pattern",
        "circular_pattern": "feature_pattern",
        "feature_patterns": "feature_pattern",
    }
    return aliases.get(value, value)


def _feature_collection_specs_for(kinds):
    if kinds in (None, ""):
        wanted = None
    elif isinstance(kinds, (list, tuple)):
        wanted = {_normalize_feature_kind(item) for item in kinds}
    else:
        wanted = {_normalize_feature_kind(kinds)}
    allowed = {kind for kind, _collection_name, _accessors in FEATURE_COLLECTION_SPECS}
    if wanted:
        unsupported = sorted(kind for kind in wanted if kind not in allowed)
        if unsupported:
            raise RuntimeError("invalid input: unsupported feature kind: %s" % ", ".join(unsupported))
    return [
        (kind, collection_name, accessors)
        for kind, collection_name, accessors in FEATURE_COLLECTION_SPECS
        if wanted is None or kind in wanted
    ]


def _feature_state_payload(feature):
    state = {}
    for attr in ("Hidden", "Visible", "Suppressed", "Enabled", "Changed", "Valid", "Type"):
        value = safe_get(feature, attr)
        if value is not None:
            state[attr[:1].lower() + attr[1:]] = _json_safe_scalar(value)
    return state


def _feature_variables_payload(feature, max_items=25):
    variables = []
    for index, variable in enumerate(_iter_operation_variables(feature)[:max_items]):
        row = {"index": index}
        for attr in ("Name", "Expression", "Value", "ParameterNote", "Note"):
            value = safe_get(variable, attr)
            if value is not None:
                row[attr[:1].lower() + attr[1:]] = _json_safe_scalar(value)
        variables.append(row)
    return variables


def _feature_fingerprint(kind, reference, name, com_type, state):
    return "|".join(
        [
            str(kind),
            str(reference if reference not in (None, "") else ""),
            str(name or ""),
            str(com_type or ""),
            str(state.get("type", "")),
        ]
    )


def _feature_list_item(feature, kind, collection_name, index, include_details=False):
    reference = safe_get(feature, "Reference")
    name = safe_get(feature, "Name", "")
    com_type = feature.__class__.__name__ if feature is not None else None
    state = _feature_state_payload(feature)
    item = {
        "index": index,
        "collection_index": index,
        "kind": kind,
        "collection": collection_name,
        "reference": reference,
        "name": name,
        "com_type": com_type,
        "fingerprint": _feature_fingerprint(kind, reference, name, com_type, state),
        "state": state,
    }
    if include_details:
        variables = _feature_variables_payload(feature)
        item["variables"] = variables
        item["variable_count"] = len(variables)
    return item


def _list_existing_features(model_container, payload):
    max_items = int(payload.get("max_items", 100))
    if max_items < 1:
        raise RuntimeError("invalid input: max_items must be greater than zero")
    items = []
    counts = {}
    available = {}
    truncated = False
    for kind, collection_name, accessors in _feature_collection_specs_for(payload.get("kinds")):
        collection, accessor, errors = _resolve_model_object_collection(model_container, accessors)
        available[collection_name] = collection is not None
        count = collection_count(collection)
        counts[collection_name] = count
        for index in range(count):
            if len(items) >= max_items:
                truncated = True
                break
            feature = get_collection_item(collection, index)
            if feature is not None:
                item = _feature_list_item(feature, kind, collection_name, index)
                if errors:
                    item["collection_errors"] = errors
                item["accessor"] = accessor
                items.append(item)
        if truncated:
            break
    return items, {
        "feature_count": len(items),
        "counts": counts,
        "available": available,
        "truncated": truncated,
        "max_items": max_items,
    }


def _collection_for_feature_kind(model_container, kind):
    normalized = _normalize_feature_kind(kind)
    for feature_kind, collection_name, accessors in FEATURE_COLLECTION_SPECS:
        if feature_kind == normalized:
            collection, _accessor, _errors = _resolve_model_object_collection(model_container, accessors)
            if collection is None:
                raise RuntimeError("feature_collection_unavailable")
            return collection, feature_kind, collection_name
    raise RuntimeError("unsupported_feature_kind")


def _select_existing_feature(model_container, spec):
    if not isinstance(spec, dict):
        raise RuntimeError("invalid input: feature selector must be an object")
    collection, kind, collection_name = _collection_for_feature_kind(
        model_container,
        spec.get("kind") or spec.get("type") or spec.get("collection"),
    )
    if spec.get("index") not in (None, ""):
        index = int(spec.get("index"))
        feature = get_collection_item(collection, index)
        if feature is None:
            raise RuntimeError("feature_index_not_found")
        return feature, kind, collection_name, index

    expected_reference = str(spec.get("reference")) if spec.get("reference") not in (None, "") else None
    expected_fingerprint = str(spec.get("fingerprint") or "") or None
    expected_name = str(spec.get("name") or "") or None
    count = collection_count(collection)
    for index in range(count):
        feature = get_collection_item(collection, index)
        if feature is None:
            continue
        item = _feature_list_item(feature, kind, collection_name, index)
        if expected_reference is not None and str(item.get("reference")) == expected_reference:
            return feature, kind, collection_name, index
        if expected_fingerprint is not None and item.get("fingerprint") == expected_fingerprint:
            return feature, kind, collection_name, index
        if expected_name is not None and str(item.get("name") or "") == expected_name:
            return feature, kind, collection_name, index
    raise RuntimeError("feature_not_found")


def _inspect_existing_feature(model_container, payload):
    spec = payload.get("feature") or payload.get("selector")
    feature, kind, collection_name, index = _select_existing_feature(model_container, spec)
    return _feature_list_item(feature, kind, collection_name, index, include_details=True)


def _normalize_feature_repair_operation(operation):
    operation = str(operation or "").strip().lower()
    aliases = {
        "rename": "rename",
        "rename_feature": "rename",
        "set_name": "rename",
        "suppress": "set_suppressed",
        "unsuppress": "set_suppressed",
        "set_suppressed": "set_suppressed",
        "set_suppression": "set_suppressed",
        "delete": "delete_feature",
        "delete_feature": "delete_feature",
        "remove": "delete_feature",
    }
    normalized = aliases.get(operation)
    if normalized is None:
        raise RuntimeError("invalid input: unsupported feature repair operation: %s" % (operation or "<missing>"))
    return normalized


def _update_feature_object(feature):
    updater = safe_get(feature, "Update")
    if not callable(updater):
        return None
    result = updater()
    return True if result is None else bool(result)


def _set_feature_suppressed(feature, suppressed):
    report = {
        "requested_suppressed": bool(suppressed),
        "reference": safe_get(feature, "Reference"),
        "name": safe_get(feature, "Name", ""),
    }
    current_suppressed = safe_get(feature, "Suppressed")
    if current_suppressed is not None:
        report["surface"] = "Suppressed"
        report["before"] = bool(current_suppressed)
        feature.Suppressed = bool(suppressed)
        report["update_ok"] = _update_feature_object(feature)
        applied = safe_get(feature, "Suppressed")
        report["after"] = bool(applied) if applied is not None else None
        report["ok"] = applied is not None and bool(applied) == bool(suppressed) and report["update_ok"] is not False
        return report

    current_enabled = safe_get(feature, "Enabled")
    if current_enabled is not None:
        report["surface"] = "Enabled"
        report["before"] = not bool(current_enabled)
        feature.Enabled = not bool(suppressed)
        report["update_ok"] = _update_feature_object(feature)
        applied = safe_get(feature, "Enabled")
        report["after"] = (not bool(applied)) if applied is not None else None
        report["ok"] = applied is not None and bool(applied) == (not bool(suppressed)) and report["update_ok"] is not False
        return report

    report["ok"] = False
    report["reason"] = "feature_suppression_property_unavailable"
    return report


def _delete_feature_from_collection(collection, feature, index):
    deleter = safe_get(feature, "Delete")
    if callable(deleter):
        result = deleter()
        if result is None or bool(result):
            return True
    collection_deleter = safe_get(collection, "Delete")
    if callable(collection_deleter):
        result = collection_deleter(index)
        return True if result is None else bool(result)
    items = safe_get(collection, "_items")
    if isinstance(items, list) and 0 <= index < len(items):
        try:
            items.pop(index)
            collection.Count = len(items)
        except Exception:
            pass
        return True
    raise RuntimeError("feature_delete_not_supported")


def _repair_existing_features(model_container, payload):
    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise RuntimeError("invalid input: operations must be a non-empty list")
    if len(operations) > 20:
        raise RuntimeError("invalid input: operations must contain at most 20 items")
    apply_changes = bool(payload.get("apply"))

    items = []
    for index, raw_operation in enumerate(operations):
        if not isinstance(raw_operation, dict):
            raise RuntimeError("invalid input: operations[%d] must be an object" % index)
        operation = _normalize_feature_repair_operation(raw_operation.get("operation") or raw_operation.get("type"))
        spec = raw_operation.get("feature") or raw_operation.get("selector")
        feature, kind, collection_name, collection_index = _select_existing_feature(model_container, spec)
        collection, _kind, _collection_name = _collection_for_feature_kind(model_container, kind)
        before = _feature_list_item(feature, kind, collection_name, collection_index, include_details=True)
        result = {
            "ok": True,
            "index": index,
            "operation": operation,
            "applied": apply_changes,
            "kind": kind,
            "collection": collection_name,
            "collection_index": collection_index,
            "reference": before.get("reference"),
            "fingerprint": before.get("fingerprint"),
            "before_item": before,
        }
        if raw_operation.get("id") not in (None, ""):
            result["id"] = str(raw_operation.get("id"))
        if raw_operation.get("reason") not in (None, ""):
            result["reason"] = str(raw_operation.get("reason"))

        if operation == "rename":
            new_name = str(raw_operation.get("name") or raw_operation.get("new_name") or "").strip()
            if not new_name:
                raise RuntimeError("invalid input: operations[%d].name is required" % index)
            if apply_changes:
                feature.Name = new_name
                update_ok = _update_feature_object(feature)
                if update_ok is False:
                    raise RuntimeError("Feature Update after rename returned False")
                after = _feature_list_item(feature, kind, collection_name, collection_index, include_details=True)
            else:
                update_ok = None
                after = dict(before)
                after["name"] = new_name
            result.update(
                {
                    "item": after,
                    "summary": {
                        "planned": not apply_changes,
                        "old_name": before.get("name"),
                        "name": new_name,
                        "feature_update_ok": update_ok,
                    },
                }
            )
        elif operation == "set_suppressed":
            if "suppressed" in raw_operation:
                suppressed = bool(raw_operation.get("suppressed"))
            elif "value" in raw_operation:
                suppressed = bool(raw_operation.get("value"))
            else:
                suppressed = str(raw_operation.get("operation") or raw_operation.get("type") or "").strip().lower() == "suppress"
            if apply_changes:
                suppression_report = _set_feature_suppressed(feature, suppressed)
                if not suppression_report.get("ok"):
                    raise RuntimeError(suppression_report.get("reason") or "feature_suppression_failed")
                after = _feature_list_item(feature, kind, collection_name, collection_index, include_details=True)
            else:
                suppression_report = {
                    "requested_suppressed": suppressed,
                    "before": before.get("state", {}).get("suppressed"),
                    "planned": True,
                }
                after = before
            result.update(
                {
                    "item": after,
                    "summary": dict(suppression_report, planned=not apply_changes),
                }
            )
        elif operation == "delete_feature":
            before_count = collection_count(collection)
            if collection_index < 0:
                raise RuntimeError("feature_index_not_found")
            if apply_changes:
                deleted = _delete_feature_from_collection(collection, feature, collection_index)
                after_count = collection_count(collection)
                if after_count >= before_count:
                    raise RuntimeError("feature_delete_not_confirmed")
            else:
                deleted = False
                after_count = before_count
            result.update(
                {
                    "item": {
                        "kind": before.get("kind"),
                        "collection": before.get("collection"),
                        "collection_index": before.get("collection_index"),
                        "reference": before.get("reference"),
                        "fingerprint": before.get("fingerprint"),
                        "deleted": deleted,
                        "before_count": before_count,
                        "after_count": after_count,
                        "deleted_count": before_count - after_count if apply_changes else 0,
                    },
                    "summary": {
                        "planned": not apply_changes,
                        "deleted": deleted,
                        "before_count": before_count,
                        "after_count": after_count,
                        "deleted_count": before_count - after_count if apply_changes else 0,
                    },
                }
            )
        items.append(result)

    return items, {
        "operation_count": len(items),
        "applied": apply_changes,
        "planned": not apply_changes,
        "failed_count": sum(1 for item in items if not item.get("ok")),
        "operations": [
            {
                "index": item.get("index"),
                "operation": item.get("operation"),
                "applied": item.get("applied"),
                "kind": item.get("kind"),
                "reference": item.get("reference"),
                "fingerprint": item.get("fingerprint"),
            }
            for item in items
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


def _safe_call(obj, method_name, *args):
    method = safe_get(obj, method_name)
    if not callable(method):
        return None
    try:
        return method(*args)
    except Exception:
        return None


def _read_com_value(obj, names):
    for name in names:
        value = safe_get(obj, name)
        if value not in (None, "") and not callable(value):
            return value
        if callable(value):
            try:
                value = value()
            except Exception:
                value = None
            if value not in (None, ""):
                return value
    return None


def _get_library_manager(app):
    manager = safe_get(app, "LibraryManager")
    if manager is not None:
        return manager
    return _safe_call(app, "GetLibraryManager")


def _get_procedure_libraries(manager):
    if manager is None:
        return None
    libraries = safe_get(manager, "ProceduresLibraries")
    if libraries is not None:
        return libraries
    return _safe_call(manager, "GetProceduresLibraries")


def _describe_procedure_library(library, index=None):
    return {
        "index": index,
        "name": _read_com_value(library, ("Name", "GetName", "LibraryName", "GetLibraryName")),
        "title": _read_com_value(library, ("Title", "Caption", "DisplayName", "DisplayLibraryName", "GetDisplayName")),
        "comment": _read_com_value(library, ("Comment", "GetComment")),
        "file_name": _read_com_value(library, ("FileName", "FullName", "Path", "GetFileName")),
        "reference": safe_get(library, "Reference"),
    }


def _procedure_library_matches(summary, query):
    needle = str(query or "").strip().lower()
    if not needle:
        return False
    for key in ("name", "title", "comment", "file_name"):
        value = summary.get(key)
        if value is None:
            continue
        text = str(value).strip().lower()
        if text == needle or needle in text:
            return True
    return False


def _candidate_libraries_from_collection(collection):
    libraries = []
    for index, library in enumerate(iter_collection(collection)):
        libraries.append((library, _describe_procedure_library(library, index=index)))
    return libraries


def _find_procedure_library(app, module, aliases=None):
    queries = [module]
    for alias in aliases or []:
        if alias not in (None, "") and alias not in queries:
            queries.append(alias)
    manager = _get_library_manager(app)
    libraries_collection = _get_procedure_libraries(manager)
    report = {
        "ok": False,
        "module": module,
        "queries": queries,
        "library_manager_available": manager is not None,
        "procedures_libraries_available": libraries_collection is not None,
        "available_libraries": [],
    }
    if libraries_collection is None:
        report["error"] = "KOMPAS procedures libraries collection is unavailable"
        return None, manager, report

    libraries = _candidate_libraries_from_collection(libraries_collection)
    report["available_libraries"] = [summary for _, summary in libraries[:25]]
    report["available_library_count"] = len(libraries)
    report["available_libraries_truncated"] = len(libraries) > 25
    for library, summary in libraries:
        if any(_procedure_library_matches(summary, query) for query in queries):
            report.update({"ok": True, "matched_library": summary})
            return library, manager, report

    item_accessor = safe_get(libraries_collection, "Item")
    if callable(item_accessor):
        for query in queries:
            for candidate in (query, str(query).upper(), str(query).lower()):
                try:
                    library = item_accessor(candidate)
                except Exception:
                    continue
                if library is None:
                    continue
                summary = _describe_procedure_library(library)
                report.update({"ok": True, "matched_library": summary, "matched_by": "Item"})
                return library, manager, report

    report["error"] = "Native KOMPAS procedure library was not found among registered libraries"
    return None, manager, report


def _set_current_library(manager, library):
    report = {"attempted": False, "ok": None}
    if manager is None or library is None:
        return report
    method = safe_get(manager, "SetCurrentLibrary")
    if not callable(method):
        report["available"] = False
        return report
    report["available"] = True
    report["attempted"] = True
    try:
        report["result"] = method(library)
        report["ok"] = bool(report["result"]) if report["result"] is not None else True
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
    return report


def _execute_procedure_library_command(library, command_id, post):
    execute = safe_get(library, "Execute")
    report = {
        "ok": False,
        "command_id": command_id,
        "post": bool(post),
        "attempts": [],
    }
    if not callable(execute):
        report["error"] = "Matched library does not expose Execute"
        return report

    command = int(command_id)
    attempt_specs = [
        ("automation_execute", (command, None, bool(post))),
        ("ksapi_execute", (command, bool(post), None)),
        ("two_arg_execute", (command, bool(post))),
        ("one_arg_execute", (command,)),
    ]
    for name, args in attempt_specs:
        attempt = {"name": name, "arg_count": len(args)}
        try:
            result = execute(*args)
        except Exception as exc:
            attempt["ok"] = False
            attempt["error"] = str(exc)
            report["attempts"].append(attempt)
            continue
        attempt["ok"] = bool(result) if result is not None else True
        attempt["result"] = result
        report["attempts"].append(attempt)
        if attempt["ok"]:
            report["ok"] = True
            report["successful_attempt"] = name
            return report

    report["error"] = "All Execute call signatures failed or returned false"
    return report


def list_documents(app):
    documents = safe_get(app, "Documents")
    if documents is None:
        return []
    return [describe_document(doc, app) for doc in iter_collection(documents)]


def resolve_document(app, document_id):
    active_document = safe_get(app, "ActiveDocument")
    if not document_id:
        if active_document is not None:
            return cast_document_3d(active_document)
        documents = list(iter_collection(safe_get(app, "Documents")))
        for document in reversed(documents):
            casted = cast_document_3d(document)
            if casted is not None:
                return casted
        return None

    if active_document is not None:
        active_description = describe_document(active_document, app)
        if document_id in (active_description["id"], active_description["path"], active_description["name"]):
            return cast_document_3d(active_document)

    for document in iter_collection(safe_get(app, "Documents")):
        description = describe_document(document, app)
        if document_id in (description["id"], description["path"], description["name"]):
            return cast_document_3d(document)
    if active_document is not None:
        casted = cast_document_3d(active_document)
        if casted is not None:
            return casted
    documents = list(iter_collection(safe_get(app, "Documents")))
    for document in reversed(documents):
        casted = cast_document_3d(document)
        if casted is not None:
            return casted
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


def _cleanup_staging_file(staging_path):
    cleanup_report = {"path": staging_path, "removed": False, "error": None}
    if not staging_path or not os.path.exists(staging_path):
        return cleanup_report
    try:
        os.remove(staging_path)
        cleanup_report["removed"] = True
    except Exception as exc:
        cleanup_report["error"] = str(exc)
    return cleanup_report


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
        "remaining_open_target_documents": [],
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
    remaining_matches = _collect_open_documents_by_path(app, target_path)
    if remaining_matches:
        report["remaining_open_target_documents"] = [match["description"] for match in remaining_matches]
        raise RuntimeError(
            "Target file is still open in KOMPAS after close attempts: %s"
            % json.dumps(report["remaining_open_target_documents"], ensure_ascii=False)
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

    try:
        reopened_document, replace_report = _replace_staging_file(
            app,
            staging_path,
            target_path,
            reopen_target=bool(keep_open),
            visible=visible,
        )
    except Exception as exc:
        cleanup_report = _cleanup_staging_file(staging_path)
        raise RuntimeError(
            "Failed to complete staged save into target: %s | staging_cleanup=%s"
            % (exc, json.dumps(cleanup_report, ensure_ascii=False))
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


def handle_launch_native_module_command(payload):
    app = make_app()
    requested_visible = bool(payload.get("visible", True))
    visibility_report = {
        "requested_visible": requested_visible,
        "visible_before": bool(safe_get(app, "Visible", False)),
    }
    try:
        app.Visible = requested_visible
        visibility_report["ok"] = bool(safe_get(app, "Visible", False)) == requested_visible
    except Exception as exc:
        visibility_report["ok"] = False
        visibility_report["error"] = str(exc)
    visibility_report["visible_after"] = bool(safe_get(app, "Visible", False))

    before_documents = list_documents(app)
    before_active = safe_get(app, "ActiveDocument")
    before_active_info = describe_document(before_active, app) if before_active is not None else None

    library, manager, library_report = _find_procedure_library(
        app,
        payload.get("module") or "Spring",
        aliases=[payload.get("module_title"), payload.get("app_id")],
    )
    set_current_report = _set_current_library(manager, library) if library is not None else {"attempted": False, "ok": None}
    execute_report = None
    if library is not None:
        execute_report = _execute_procedure_library_command(
            library,
            payload.get("command_id") or 101,
            bool(payload.get("post", True)),
        )

    after_documents = list_documents(app)
    after_active = safe_get(app, "ActiveDocument")
    after_active_info = describe_document(after_active, app) if after_active is not None else None
    before_ids = {item.get("id") for item in before_documents}
    after_ids = {item.get("id") for item in after_documents}

    ok = bool(library_report.get("ok")) and bool(execute_report and execute_report.get("ok"))
    return {
        "ok": ok,
        "module": payload.get("module") or "Spring",
        "command": {
            "id": payload.get("command_id") or 101,
            "title": payload.get("command_title"),
        },
        "interactive": True,
        "post": bool(payload.get("post", True)),
        "visibility": visibility_report,
        "library": library_report,
        "set_current_library": set_current_report,
        "execute": execute_report,
        "documents": {
            "before_count": len(before_documents),
            "after_count": len(after_documents),
            "added_ids": sorted(item for item in after_ids - before_ids if item),
            "removed_ids": sorted(item for item in before_ids - after_ids if item),
            "before_active": before_active_info,
            "after_active": after_active_info,
            "before": before_documents[:25],
            "after": after_documents[:25],
            "truncated": len(before_documents) > 25 or len(after_documents) > 25,
        },
    }


def _run_loader_probe_in_process(dll_path, export_name):
    report = {
        "ok": False,
        "dll_path": dll_path,
        "export_name": export_name,
    }
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LoadLibraryW.argtypes = [ctypes.c_wchar_p]
    kernel32.LoadLibraryW.restype = ctypes.c_void_p
    kernel32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    kernel32.GetProcAddress.restype = ctypes.c_void_p
    kernel32.FreeLibrary.argtypes = [ctypes.c_void_p]
    kernel32.FreeLibrary.restype = ctypes.c_int

    handle = kernel32.LoadLibraryW(dll_path)
    if not handle:
        report["load_library"] = {
            "ok": False,
            "last_error": ctypes.get_last_error(),
        }
        return report

    report["load_library"] = {
        "ok": True,
        "handle": "0x%x" % int(handle),
    }
    try:
        address = kernel32.GetProcAddress(handle, export_name.encode("ascii"))
        if address:
            report["get_proc_address"] = {
                "ok": True,
                "address": "0x%x" % int(address),
            }
        else:
            report["get_proc_address"] = {
                "ok": False,
                "last_error": ctypes.get_last_error(),
            }
        report["ok"] = bool(report["get_proc_address"].get("ok"))
    finally:
        report["free_library"] = {
            "ok": bool(kernel32.FreeLibrary(handle)),
        }
    return report


def handle_probe_native_entrypoint_loader_hosted(payload):
    app = make_app()
    search_dirs = [item for item in (payload.get("search_dirs") or []) if isinstance(item, str) and item]
    path_before = os.environ.get("PATH", "")
    dll_dir_handles = []
    if search_dirs:
        os.environ["PATH"] = os.pathsep.join(search_dirs) + os.pathsep + path_before
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if callable(add_dll_directory):
            for search_dir in search_dirs:
                try:
                    dll_dir_handles.append(add_dll_directory(search_dir))
                except Exception:
                    pass
    try:
        report = _run_loader_probe_in_process(
            payload.get("dll_path"),
            payload.get("export_name") or "",
        )
        app_name = safe_get(app, "ApplicationName")
        if callable(app_name):
            try:
                app_name = app_name()
            except Exception:
                app_name = None
        report["host"] = {
            "app_visible": bool(safe_get(app, "Visible", False)),
            "app_name": app_name,
        }
        report["search_dirs"] = search_dirs
        return report
    finally:
        os.environ["PATH"] = path_before
        for handle in dll_dir_handles:
            try:
                handle.close()
            except Exception:
                pass


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


def _create_sketch_on_plane(model_container, part, name, plane, assign_coordinate_system=True, coordinate_system_before_plane=True):
    if isinstance(plane, str):
        try:
            plane_key = _normalize_sketch_plane(plane)
            plane_object = _resolve_default_part_object(part, plane_key)
        except Exception:
            planes = _get_planes3d_container(part)
            plane_object = None
            for index in range(collection_count(planes)):
                candidate = get_collection_item(planes, index)
                if str(safe_get(candidate, "Name") or "") == str(plane):
                    plane_object = candidate
                    break
            if plane_object is None:
                raise RuntimeError("Unsupported sketch plane or plane name: %s" % plane)
            plane_key = str(safe_get(plane_object, "Name", "custom"))
    else:
        plane_key = str(safe_get(plane, "Name", "custom"))
        plane_object = plane
    sketchs = _get_sketch_collection(model_container)
    if sketchs is None or not callable(safe_get(sketchs, "Add")):
        raise RuntimeError("Part does not expose Sketchs.Add")
    sketch = sketchs.Add()
    if sketch is None:
        raise RuntimeError("Sketchs.Add returned None")
    if assign_coordinate_system and coordinate_system_before_plane and not isinstance(plane, str):
        try:
            sketch.CoordinateSystem = plane_object
        except Exception:
            pass
    sketch.Plane = plane_object
    if assign_coordinate_system and not coordinate_system_before_plane and not isinstance(plane, str):
        try:
            sketch.CoordinateSystem = plane_object
        except Exception:
            pass
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


def _get_sketch_edge(sketch, edge_index):
    edges = sketch.Edges(edge_index)
    if isinstance(edges, tuple) and edges:
        return edges[0]
    return edges


def _get_sketch_edge_tuple(sketch, edge_index):
    edges = sketch.Edges(edge_index)
    if isinstance(edges, tuple):
        return list(edges)
    if edges is None:
        return []
    return [edges]


def _get_first_sketch_edge_tuple(sketch, edge_indexes):
    attempts = []
    for edge_index in edge_indexes:
        try:
            edges = _get_sketch_edge_tuple(sketch, edge_index)
        except Exception as exc:
            attempts.append({"edge_index": edge_index, "ok": False, "error": str(exc)})
            continue
        attempts.append({"edge_index": edge_index, "ok": bool(edges), "count": len(edges)})
        if edges:
            return edges, edge_index, attempts
    return [], None, attempts


def _normalize_point(value):
    if isinstance(value, (list, tuple)):
        return [float(value[0]), float(value[1])]
    if hasattr(value, "__getitem__"):
        return [float(value[0]), float(value[1])]
    return [0.0, 0.0]


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


def _normalize_sketch_dimension_kind(kind):
    value = str(kind or "").strip().lower()
    if value in ("line", "linear", "line_length"):
        return "line"
    if value in ("break", "break_line", "axis_distance"):
        return "break_line"
    if value in ("diameter", "diametral", "circle_diameter"):
        return "diametral"
    if value in ("angle", "angle_between_lines"):
        return "angle"
    return value


def _get_sketch_symbols_container(view):
    try:
        return _cast_to_com_interface(view, "ISymbols2DContainer")
    except Exception:
        return view


def _get_dimension_collection(symbols_container, property_name, getter_name):
    collection = safe_get(symbols_container, property_name)
    if collection is None:
        getter = safe_get(symbols_container, getter_name)
        if callable(getter):
            collection = getter()
    return collection


def _collection_for_sketch_dimension_kind(symbols_container, kind):
    normalized = _normalize_sketch_dimension_kind(kind)
    if normalized == "line":
        return _get_dimension_collection(symbols_container, "LineDimensions", "GetLineDimensions"), "line_dimensions"
    if normalized == "break_line":
        return _get_dimension_collection(symbols_container, "BreakLineDimensions", "GetBreakLineDimensions"), "break_line_dimensions"
    if normalized == "diametral":
        return _get_dimension_collection(symbols_container, "DiametralDimensions", "GetDiametralDimensions"), "diametral_dimensions"
    if normalized == "angle":
        return _get_dimension_collection(symbols_container, "AngleDimensions", "GetAngleDimensions"), "angle_dimensions"
    raise RuntimeError("unsupported_sketch_dimension_kind")


def _sketch_dimension_geometry(dimension):
    geometry = {}
    for key in ("X1", "Y1", "X2", "Y2", "X3", "Y3"):
        value = safe_get(dimension, key)
        if value is not None:
            geometry[key.lower()] = _json_safe_scalar(value)
    angle = safe_get(dimension, "Angle")
    if angle is not None:
        geometry["angle"] = _json_safe_scalar(angle)
    orientation = safe_get(dimension, "Orientation")
    if orientation is not None:
        geometry["orientation"] = _json_safe_scalar(orientation)
    dimension_type = safe_get(dimension, "DimensionType")
    if dimension_type is not None:
        geometry["dimension_type"] = _json_safe_scalar(dimension_type)
    return geometry


def _sketch_dimension_fingerprint(kind, geometry, reference):
    parts = [str(kind), str(reference if reference not in (None, "") else "")]
    for key in ("x1", "y1", "x2", "y2", "x3", "y3", "angle", "orientation", "dimension_type"):
        if key in geometry:
            parts.append(str(geometry.get(key)))
    return "|".join(parts)


def _dimension_text_payload(dimension):
    payload = {}
    text = safe_get(dimension, "Text")
    if text is None:
        try:
            text = _cast_to_com_interface(dimension, "IDimensionText")
        except Exception:
            text = None
    if text is not None:
        for key in ("Prefix", "NominalText", "Suffix"):
            value = safe_get(text, key)
            if value is not None:
                payload[key.lower()] = safe_get(value, "Str", value)
        auto_nominal = safe_get(text, "AutoNominalValue")
        if auto_nominal is not None:
            payload["auto_nominal_value"] = _json_safe_scalar(auto_nominal)
    return payload


def _cast_sketch_dimension_object(dimension, kind):
    import win32com.client

    interfaces = {
        "line": ("ILineDimension", "IDimension", "IDrawingObject"),
        "break_line": ("IBreakLineDimension", "ILineDimension", "IDimension", "IDrawingObject"),
        "diametral": ("IDiametralDimension", "IDimension", "IDrawingObject"),
        "angle": ("IAngleDimension", "IDimension", "IDrawingObject"),
    }.get(str(kind or "").strip().lower(), ("IDimension", "IDrawingObject"))
    for interface_name in interfaces:
        try:
            casted = win32com.client.CastTo(dimension, interface_name)
            if casted is not None:
                return casted
        except Exception:
            continue
    return dimension


def _sketch_dimension_list_item(dimension, kind, collection_name, index, sketch_ref, api5_doc2d=None):
    dimension = _cast_sketch_dimension_object(dimension, kind)
    reference = safe_get(dimension, "Reference")
    geometry = _sketch_dimension_geometry(dimension)
    fingerprint = _sketch_dimension_fingerprint(kind, geometry, reference)
    item = {
        "index": index,
        "collection_index": index,
        "kind": kind,
        "collection": collection_name,
        "sketch_ref": sketch_ref,
        "reference": reference,
        "fingerprint": fingerprint,
        "geometry": geometry,
        "name": safe_get(dimension, "Name", ""),
        "value": _json_safe_scalar(safe_get(dimension, "Value")),
        "variable": _sketch_full_json_safe(safe_get(dimension, "Variable")),
        "expression": _sketch_full_json_safe(safe_get(dimension, "Expression")),
        "valid": _json_safe_scalar(safe_get(dimension, "Valid")),
    }
    text = _dimension_text_payload(dimension)
    if text:
        item["text"] = text
    details = _read_sketch_full_object_details(
        dimension,
        _SKETCH_DIMENSION_PROPERTY_NAMES,
        ("GetText", "GetExpression", "GetVariable", "GetValue"),
    )
    nested = {}
    for name in ("Text", "DimensionText", "Variable", "Expression", "Parameter", "Param", "Params"):
        value = safe_get(dimension, name)
        value_details = _read_sketch_full_object_details(value, _SKETCH_NESTED_PARAMETER_NAMES)
        if value_details:
            nested[name] = value_details
    if nested:
        details = details or {"com_type": dimension.__class__.__name__}
        details["nested"] = nested
    if details:
        item["details"] = details
    variable_surfaces = _read_sketch_variable_surfaces(dimension, 25)
    if variable_surfaces:
        item["variable_surfaces"] = variable_surfaces
    api5 = _read_api5_dimension_diagnostics(api5_doc2d, reference)
    if api5:
        item["api5"] = api5
    return item


def _collect_existing_sketch_dimensions(symbols_container, kinds, max_items, sketch_ref, api5_doc2d=None):
    items = []
    counts = {}
    truncated = False
    for kind in kinds:
        collection, collection_name = _collection_for_sketch_dimension_kind(symbols_container, kind)
        count = collection_count(collection)
        counts[collection_name] = count
        for index in range(count):
            if len(items) >= max_items:
                truncated = True
                break
            dimension = get_collection_item(collection, index)
            if dimension is not None:
                items.append(_sketch_dimension_list_item(dimension, kind, collection_name, index, sketch_ref, api5_doc2d))
        if truncated:
            break
    return items, {
        "dimension_count": len(items),
        "counts": counts,
        "truncated": truncated,
        "max_items": max_items,
    }


def _list_existing_sketch_dimensions(model_container, payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    if sketch_ref in (None, ""):
        raise RuntimeError("invalid input: sketch_ref is required")
    sketch = _resolve_existing_sketch(model_container, sketch_ref)
    raw_kinds = payload.get("kinds") or payload.get("dimension_kinds")
    if raw_kinds in (None, ""):
        kinds = ["line", "break_line", "diametral", "angle"]
    elif isinstance(raw_kinds, (list, tuple)):
        kinds = [_normalize_sketch_dimension_kind(item) for item in raw_kinds]
    else:
        kinds = [_normalize_sketch_dimension_kind(raw_kinds)]
    allowed = {"line", "break_line", "diametral", "angle"}
    for kind in kinds:
        if kind not in allowed:
            raise RuntimeError("invalid input: unsupported sketch dimension kind: %s" % (kind or "<missing>"))
    max_items = int(payload.get("max_items", 100))
    if max_items < 1:
        raise RuntimeError("invalid input: max_items must be greater than zero")

    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    try:
        view = _get_sketch_drawing_container(sketch_doc)
        api5_doc2d, api5_doc2d_status = _get_api5_document2d()
        symbols_container = _get_sketch_symbols_container(view)
        items, summary = _collect_existing_sketch_dimensions(
            symbols_container,
            kinds,
            max_items,
            safe_get(sketch, "Reference", sketch_ref),
            api5_doc2d,
        )
        summary["api5_document2d"] = api5_doc2d_status
    finally:
        sketch.EndEdit()
    return sketch, {
        "mode": "existing_sketch",
        "name": safe_get(sketch, "Name", ""),
        "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
    }, items, summary


def _select_existing_sketch_dimension(symbols_container, spec):
    kind = _normalize_sketch_dimension_kind(spec.get("kind") or spec.get("type"))
    collection, collection_name = _collection_for_sketch_dimension_kind(symbols_container, kind)
    expected_reference = spec.get("reference")
    expected_reference = str(expected_reference) if expected_reference not in (None, "") else None
    expected_fingerprint = str(spec.get("fingerprint") or "") or None
    if spec.get("index") not in (None, ""):
        dimension = get_collection_item(collection, int(spec.get("index")))
        if dimension is None:
            raise RuntimeError("sketch_dimension_index_not_found")
        return dimension, kind, collection_name
    count = collection_count(collection)
    for index in range(count):
        dimension = get_collection_item(collection, index)
        if dimension is None:
            continue
        reference = safe_get(dimension, "Reference")
        geometry = _sketch_dimension_geometry(dimension)
        fingerprint = _sketch_dimension_fingerprint(kind, geometry, reference)
        if expected_reference is not None and str(reference) == expected_reference:
            return dimension, kind, collection_name
        if expected_fingerprint is not None and fingerprint == expected_fingerprint:
            return dimension, kind, collection_name
    raise RuntimeError("sketch_dimension_not_found")


def _inspect_existing_sketch_dimension(model_container, payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    if sketch_ref in (None, ""):
        raise RuntimeError("invalid input: sketch_ref is required")
    spec = payload.get("dimension") or payload.get("selector")
    if not isinstance(spec, dict):
        raise RuntimeError("invalid input: dimension selector must be an object")
    sketch = _resolve_existing_sketch(model_container, sketch_ref)
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    try:
        view = _get_sketch_drawing_container(sketch_doc)
        symbols_container = _get_sketch_symbols_container(view)
        dimension, kind, collection_name = _select_existing_sketch_dimension(symbols_container, spec)
        item = _sketch_dimension_list_item(
            dimension,
            kind,
            collection_name,
            int(spec.get("index")) if spec.get("index") not in (None, "") else -1,
            safe_get(sketch, "Reference", sketch_ref),
        )
        if item["collection_index"] < 0:
            collection, _collection_name = _collection_for_sketch_dimension_kind(symbols_container, kind)
            count = collection_count(collection)
            for index in range(count):
                candidate = get_collection_item(collection, index)
                if candidate is None:
                    continue
                candidate_item = _sketch_dimension_list_item(
                    candidate,
                    kind,
                    collection_name,
                    index,
                    safe_get(sketch, "Reference", sketch_ref),
                )
                if (
                    candidate is dimension
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


def _get_constraint_collection(drawing_object):
    obj = _cast_to_com_interface(drawing_object, "IDrawingObject1")
    for property_name, getter_name in (("Constraints", "GetConstraints"), ("ConstraintCollection", "GetConstraintCollection")):
        collection = safe_get(obj, property_name)
        if callable(collection):
            try:
                collection = collection()
            except TypeError:
                pass
        if collection is None:
            getter = safe_get(obj, getter_name)
            if callable(getter):
                collection = getter()
        if collection is not None:
            return collection, property_name
    return None, None


def _constraint_kind_from_type(constraint_type):
    try:
        return SKETCH_CONSTRAINT_TYPE_NAMES.get(int(constraint_type), "type_%s" % int(constraint_type))
    except Exception:
        return None


def _sketch_constraint_fingerprint(kind, reference, owner, constraint_index, payload):
    parts = [
        str(kind or ""),
        str(reference if reference not in (None, "") else ""),
        str(owner.get("reference") if isinstance(owner, dict) else ""),
        str(owner.get("fingerprint") if isinstance(owner, dict) else ""),
        str(constraint_index),
    ]
    for key in ("constraint_type", "index", "partner_index", "value", "variable", "expression", "valid"):
        if key in payload and payload.get(key) not in (None, ""):
            parts.append(str(payload.get(key)))
    return "|".join(parts)


def _sketch_constraint_list_item(constraint, owner_item, constraint_index, scan_index):
    constraint = _cast_parametric_constraint_object(constraint)
    constraint_type = safe_get(constraint, "ConstraintType", safe_get(constraint, "Type"))
    kind = _constraint_kind_from_type(constraint_type)
    reference = safe_get(constraint, "Reference")
    payload = {
        "index": scan_index,
        "collection_index": scan_index,
        "constraint_index": constraint_index,
        "kind": kind,
        "constraint_type": _json_safe_scalar(constraint_type),
        "reference": reference,
        "valid": _json_safe_scalar(safe_get(constraint, "Valid")),
        "value": _json_safe_scalar(safe_get(constraint, "Value")),
        "variable": _sketch_full_json_safe(safe_get(constraint, "Variable")),
        "expression": _sketch_full_json_safe(safe_get(constraint, "Expression")),
        "point_index": _json_safe_scalar(safe_get(constraint, "Index")),
        "partner_index": _json_safe_scalar(safe_get(constraint, "PartnerIndex")),
        "owner": {
            "kind": owner_item.get("kind"),
            "reference": owner_item.get("reference"),
            "collection": owner_item.get("collection"),
            "collection_index": owner_item.get("collection_index"),
            "fingerprint": owner_item.get("fingerprint"),
        },
    }
    partner = safe_get(constraint, "Partner")
    partner_reference = safe_get(partner, "Reference") if partner is not None else None
    if partner_reference not in (None, ""):
        payload["partner_reference"] = partner_reference
    details = _read_sketch_full_object_details(
        constraint,
        _SKETCH_CONSTRAINT_PROPERTY_NAMES,
        ("GetObject", "GetFirstObject", "GetSecondObject", "GetPartner"),
        _SKETCH_RELATED_OBJECT_NAMES,
    )
    nested = {}
    for name in ("Variable", "Expression", "Parameter", "Param", "Params"):
        value = safe_get(constraint, name)
        value_details = _read_sketch_full_object_details(value, _SKETCH_NESTED_PARAMETER_NAMES)
        if value_details:
            nested[name] = value_details
    if nested:
        details = details or {"com_type": constraint.__class__.__name__}
        details["nested"] = nested
    if details:
        payload["details"] = details
    payload["fingerprint"] = _sketch_constraint_fingerprint(kind, reference, payload["owner"], constraint_index, payload)
    return payload


def _cast_parametric_constraint_object(constraint):
    if constraint is None:
        return None
    try:
        import win32com.client

        casted = win32com.client.CastTo(constraint, "IParametriticConstraint")
        if casted is not None:
            return casted
    except Exception:
        pass
    return constraint


def _scan_existing_sketch_constraints(drawing_container, sketch_ref, kinds, max_items):
    entity_kinds = ["segment", "circle", "point", "arc", "ellipse"]
    items = []
    counts = {}
    owners_scanned = 0
    surfaces = []
    truncated = False
    seen = set()
    for entity_kind in entity_kinds:
        collection, collection_name = _collection_for_sketch_entity_kind(drawing_container, entity_kind)
        entity_count = collection_count(collection)
        for entity_index in range(entity_count):
            entity = get_collection_item(collection, entity_index)
            if entity is None:
                continue
            owners_scanned += 1
            owner_item = _sketch_entity_list_item(entity, entity_kind, collection_name, entity_index, sketch_ref)
            constraint_collection, surface = _get_constraint_collection(entity)
            constraint_count = collection_count(constraint_collection)
            surfaces.append({
                "entity_kind": entity_kind,
                "entity_index": entity_index,
                "entity_reference": owner_item.get("reference"),
                "surface": surface,
                "constraint_count": constraint_count,
            })
            counts[entity_kind] = counts.get(entity_kind, 0) + constraint_count
            for constraint_index in range(constraint_count):
                if len(items) >= max_items:
                    truncated = True
                    break
                constraint = get_collection_item(constraint_collection, constraint_index)
                if constraint is None:
                    continue
                item = _sketch_constraint_list_item(constraint, owner_item, constraint_index, len(items))
                if kinds and item.get("kind") not in kinds:
                    continue
                dedupe_key = item.get("reference") or item.get("fingerprint")
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                items.append(item)
            if truncated:
                break
        if truncated:
            break
    return items, {
        "constraint_count": len(items),
        "counts": counts,
        "owners_scanned": owners_scanned,
        "surfaces": surfaces[: min(len(surfaces), 25)],
        "truncated": truncated,
        "max_items": max_items,
    }


def _list_existing_sketch_constraints(model_container, payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    if sketch_ref in (None, ""):
        raise RuntimeError("invalid input: sketch_ref is required")
    raw_kinds = payload.get("kinds") or payload.get("constraint_kinds")
    if raw_kinds in (None, ""):
        kinds = []
    elif isinstance(raw_kinds, (list, tuple)):
        kinds = [str(item or "").strip().lower() for item in raw_kinds]
    else:
        kinds = [str(raw_kinds or "").strip().lower()]
    allowed = set(SKETCH_CONSTRAINT_TYPES.keys())
    for kind in kinds:
        if kind not in allowed:
            raise RuntimeError("invalid input: unsupported sketch constraint kind: %s" % (kind or "<missing>"))
    max_items = int(payload.get("max_items", 100))
    if max_items < 1:
        raise RuntimeError("invalid input: max_items must be greater than zero")
    sketch = _resolve_existing_sketch(model_container, sketch_ref)
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    try:
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        items, summary = _scan_existing_sketch_constraints(
            drawing_container,
            safe_get(sketch, "Reference", sketch_ref),
            set(kinds),
            max_items,
        )
    finally:
        sketch.EndEdit()
    return sketch, {
        "mode": "existing_sketch",
        "name": safe_get(sketch, "Name", ""),
        "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
    }, items, summary


def _inspect_existing_sketch_constraint(model_container, payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    if sketch_ref in (None, ""):
        raise RuntimeError("invalid input: sketch_ref is required")
    spec = payload.get("constraint") or payload.get("selector")
    if not isinstance(spec, dict):
        raise RuntimeError("invalid input: constraint selector must be an object")
    sketch, target_payload, items, summary = _list_existing_sketch_constraints(
        model_container,
        {
            "target": {"mode": "existing_sketch", "sketch_ref": sketch_ref},
            "kinds": [spec.get("kind")] if spec.get("kind") not in (None, "") else None,
            "max_items": max(int(spec.get("index", 0)) + 1 if spec.get("index") not in (None, "") else 100, 100),
        },
    )
    expected_reference = str(spec.get("reference")) if spec.get("reference") not in (None, "") else None
    expected_fingerprint = str(spec.get("fingerprint") or "") or None
    expected_index = int(spec.get("index")) if spec.get("index") not in (None, "") else None
    for item in items:
        if expected_index is not None and int(item.get("index", -1)) == expected_index:
            return sketch, target_payload, item
        if expected_reference is not None and str(item.get("reference")) == expected_reference:
            return sketch, target_payload, item
        if expected_fingerprint is not None and item.get("fingerprint") == expected_fingerprint:
            return sketch, target_payload, item
    raise RuntimeError("sketch_constraint_not_found; scanned=%s" % summary.get("constraint_count"))


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


def _clear_constraints_from_entity(entity):
    drawing_object = _cast_to_com_interface(entity, "IDrawingObject1")
    deleter = safe_get(drawing_object, "DeleteConstraints")
    if not callable(deleter):
        raise RuntimeError("object does not expose IDrawingObject1.DeleteConstraints")
    result = deleter()
    return True if result is None else bool(result)


def _clear_existing_sketch_entity_constraints(model_container, payload):
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
        resolved_sketch_ref = safe_get(sketch, "Reference", sketch_ref)
        index = _existing_sketch_entity_index(drawing_container, entity, kind, collection_name, resolved_sketch_ref)
        before = _sketch_entity_list_item(entity, kind, collection_name, index, resolved_sketch_ref)
        before_collection, before_surface = _get_constraint_collection(entity)
        before_count = collection_count(before_collection)
        cleared = _clear_constraints_from_entity(entity)
        after_collection, after_surface = _get_constraint_collection(entity)
        after_count = collection_count(after_collection)
        updater = safe_get(entity, "Update")
        entity_update_ok = True
        if callable(updater):
            entity_update_ok = bool(updater())
        after = _sketch_entity_list_item(entity, kind, collection_name, index, resolved_sketch_ref)
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    return sketch, {
        "mode": "existing_sketch",
        "name": safe_get(sketch, "Name", ""),
        "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
    }, before, after, {
        "kind": kind,
        "collection": collection_name,
        "collection_index": index,
        "reference": before.get("reference"),
        "fingerprint": before.get("fingerprint"),
        "cleared": cleared,
        "before_count": before_count,
        "after_count": after_count,
        "cleared_count": max(0, int(before_count) - int(after_count)),
        "before_surface": before_surface,
        "after_surface": after_surface,
        "entity_update_ok": entity_update_ok,
    }


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


def _delete_entity_from_collection(collection, entity, index):
    deleter = safe_get(entity, "Delete")
    if callable(deleter):
        result = deleter()
        return True if result is None else bool(result)
    collection_deleter = safe_get(collection, "Delete")
    if callable(collection_deleter):
        result = collection_deleter(index)
        return True if result is None else bool(result)
    items = safe_get(collection, "_items")
    if isinstance(items, list) and 0 <= int(index) < len(items) and items[int(index)] is entity:
        items.pop(int(index))
        try:
            collection.Count = len(items)
        except Exception:
            pass
        return True
    raise RuntimeError("sketch_entity_delete_not_supported")


def _delete_existing_sketch_entity(model_container, payload):
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
        collection, _collection_name = _collection_for_sketch_entity_kind(drawing_container, kind)
        resolved_sketch_ref = safe_get(sketch, "Reference", sketch_ref)
        before_count = collection_count(collection)
        index = _existing_sketch_entity_index(drawing_container, entity, kind, collection_name, resolved_sketch_ref)
        before = _sketch_entity_list_item(entity, kind, collection_name, index, resolved_sketch_ref)
        if index < 0:
            raise RuntimeError("sketch_entity_index_not_found")
        deleted = _delete_entity_from_collection(collection, entity, index)
        after_count = collection_count(collection)
        if after_count >= before_count:
            raise RuntimeError("sketch_entity_delete_not_confirmed")
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    return sketch, {
        "mode": "existing_sketch",
        "name": safe_get(sketch, "Name", ""),
        "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
    }, before, {
        "kind": before.get("kind"),
        "collection": before.get("collection"),
        "collection_index": before.get("collection_index"),
        "reference": before.get("reference"),
        "fingerprint": before.get("fingerprint"),
        "deleted": deleted,
        "before_count": before_count,
        "after_count": after_count,
        "deleted_count": before_count - after_count,
    }


def _apply_existing_sketch_entity_geometry(entity, kind, geometry):
    if kind == "segment":
        start = _normalize_point2d_payload(geometry.get("start"), "geometry.start", None)
        end = _normalize_point2d_payload(geometry.get("end"), "geometry.end", None)
        entity.X1 = float(start[0])
        entity.Y1 = float(start[1])
        entity.X2 = float(end[0])
        entity.Y2 = float(end[1])
        return
    if kind == "circle":
        center = _normalize_point2d_payload(geometry.get("center"), "geometry.center", None)
        radius = float(geometry.get("radius"))
        if radius <= 0:
            raise RuntimeError("invalid input: geometry.radius must be greater than zero")
        entity.Xc = float(center[0])
        entity.Yc = float(center[1])
        entity.Radius = radius
        return
    if kind == "point":
        point = _normalize_point2d_payload(geometry.get("point", geometry.get("position")), "geometry.point", None)
        entity.X = float(point[0])
        entity.Y = float(point[1])
        return
    if kind == "arc":
        center = _normalize_point2d_payload(geometry.get("center"), "geometry.center", None)
        start = _normalize_point2d_payload(geometry.get("start"), "geometry.start", None)
        end = _normalize_point2d_payload(geometry.get("end"), "geometry.end", None)
        radius = float(geometry.get("radius"))
        if radius <= 0:
            raise RuntimeError("invalid input: geometry.radius must be greater than zero")
        entity.Xc = float(center[0])
        entity.Yc = float(center[1])
        entity.Radius = radius
        entity.X1 = float(start[0])
        entity.Y1 = float(start[1])
        entity.X2 = float(end[0])
        entity.Y2 = float(end[1])
        if geometry.get("direction") not in (None, ""):
            try:
                entity.Direction = bool(geometry.get("direction"))
            except Exception:
                set_direction = safe_get(entity, "SetDirection")
                if callable(set_direction):
                    set_direction(bool(geometry.get("direction")))
        return
    raise RuntimeError("invalid input: unsupported geometry update kind: %s" % (kind or "<missing>"))


def _update_existing_sketch_entity_geometry(model_container, payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    if sketch_ref in (None, ""):
        raise RuntimeError("invalid input: sketch_ref is required")
    spec = payload.get("entity") or payload.get("selector")
    if not isinstance(spec, dict):
        raise RuntimeError("invalid input: entity selector must be an object")
    geometry = payload.get("geometry")
    if not isinstance(geometry, dict):
        raise RuntimeError("invalid input: geometry must be an object")
    sketch = _resolve_existing_sketch(model_container, sketch_ref)
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    try:
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        entity, kind, collection_name = _select_existing_sketch_entity(drawing_container, spec)
        if kind not in ("point", "segment", "circle", "arc"):
            raise RuntimeError("invalid input: unsupported geometry update kind: %s" % (kind or "<missing>"))
        resolved_sketch_ref = safe_get(sketch, "Reference", sketch_ref)
        index = _existing_sketch_entity_index(drawing_container, entity, kind, collection_name, resolved_sketch_ref)
        edited_entity = _cast_sketch_entity_for_kind(entity, kind)
        before = _sketch_entity_list_item(edited_entity, kind, collection_name, index, resolved_sketch_ref)
        _apply_existing_sketch_entity_geometry(edited_entity, kind, geometry)
        updater = safe_get(edited_entity, "Update")
        if callable(updater) and not updater():
            raise RuntimeError("Sketch entity Update returned False")
        after = _sketch_entity_list_item(edited_entity, kind, collection_name, index, resolved_sketch_ref)
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after edit returned False")
    return sketch, {
        "mode": "existing_sketch",
        "name": safe_get(sketch, "Name", ""),
        "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
    }, before, after


def _normalize_sketch_repair_operation(value):
    operation = str(value or "").strip().lower()
    aliases = {
        "clear_constraints": "clear_constraints",
        "clear_entity_constraints": "clear_constraints",
        "delete_constraints": "clear_constraints",
        "update_geometry": "update_geometry",
        "update_entity_geometry": "update_geometry",
        "delete_entity": "delete_entity",
        "delete": "delete_entity",
    }
    normalized = aliases.get(operation)
    if normalized is None:
        raise RuntimeError("invalid input: unsupported repair operation")
    return normalized


def _repair_existing_sketch(model_container, payload):
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    sketch_ref = target.get("sketch_ref", payload.get("sketch_ref"))
    if sketch_ref in (None, ""):
        raise RuntimeError("invalid input: sketch_ref is required")
    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise RuntimeError("invalid input: operations must be a non-empty list")
    if len(operations) > 20:
        raise RuntimeError("invalid input: operations must contain at most 20 items")
    apply_changes = bool(payload.get("apply"))

    sketch = _resolve_existing_sketch(model_container, sketch_ref)
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    items = []
    try:
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        resolved_sketch_ref = safe_get(sketch, "Reference", sketch_ref)
        for index, raw_operation in enumerate(operations):
            if not isinstance(raw_operation, dict):
                raise RuntimeError("invalid input: operations[%d] must be an object" % index)
            operation = _normalize_sketch_repair_operation(raw_operation.get("operation") or raw_operation.get("type"))
            spec = raw_operation.get("entity") or raw_operation.get("selector")
            if not isinstance(spec, dict):
                raise RuntimeError("invalid input: operations[%d].entity must be an object" % index)

            entity, kind, collection_name = _select_existing_sketch_entity(drawing_container, spec)
            entity_index = _existing_sketch_entity_index(drawing_container, entity, kind, collection_name, resolved_sketch_ref)
            before = _sketch_entity_list_item(entity, kind, collection_name, entity_index, resolved_sketch_ref)
            result = {
                "ok": True,
                "index": index,
                "operation": operation,
                "applied": apply_changes,
                "kind": kind,
                "collection": collection_name,
                "collection_index": entity_index,
                "reference": before.get("reference"),
                "fingerprint": before.get("fingerprint"),
                "before_item": before,
            }
            if raw_operation.get("id") not in (None, ""):
                result["id"] = str(raw_operation.get("id"))
            if raw_operation.get("reason") not in (None, ""):
                result["reason"] = str(raw_operation.get("reason"))

            if operation == "clear_constraints":
                before_collection, before_surface = _get_constraint_collection(entity)
                before_count = collection_count(before_collection)
                if apply_changes:
                    cleared = _clear_constraints_from_entity(entity)
                    after_collection, after_surface = _get_constraint_collection(entity)
                    after_count = collection_count(after_collection)
                    updater = safe_get(entity, "Update")
                    entity_update_ok = True
                    if callable(updater):
                        entity_update_ok = bool(updater())
                    after = _sketch_entity_list_item(entity, kind, collection_name, entity_index, resolved_sketch_ref)
                else:
                    cleared = False
                    after_surface = before_surface
                    after_count = before_count
                    entity_update_ok = None
                    after = before
                result.update(
                    {
                        "item": after,
                        "summary": {
                            "planned": not apply_changes,
                            "cleared": cleared,
                            "before_count": before_count,
                            "after_count": after_count,
                            "cleared_count": max(0, int(before_count) - int(after_count)) if apply_changes else 0,
                            "before_surface": before_surface,
                            "after_surface": after_surface,
                            "entity_update_ok": entity_update_ok,
                        },
                    }
                )
            elif operation == "update_geometry":
                if kind not in ("point", "segment", "circle", "arc"):
                    raise RuntimeError("invalid input: unsupported geometry update kind: %s" % (kind or "<missing>"))
                geometry = raw_operation.get("geometry")
                if not isinstance(geometry, dict):
                    raise RuntimeError("invalid input: operations[%d].geometry must be an object" % index)
                edited_entity = _cast_sketch_entity_for_kind(entity, kind)
                before = _sketch_entity_list_item(edited_entity, kind, collection_name, entity_index, resolved_sketch_ref)
                if apply_changes:
                    _apply_existing_sketch_entity_geometry(edited_entity, kind, geometry)
                    updater = safe_get(edited_entity, "Update")
                    if callable(updater) and not updater():
                        raise RuntimeError("Sketch entity Update returned False")
                    after = _sketch_entity_list_item(edited_entity, kind, collection_name, entity_index, resolved_sketch_ref)
                else:
                    after = before
                result.update(
                    {
                        "before_item": before,
                        "item": after,
                        "summary": {
                            "planned": not apply_changes,
                            "old_geometry": before.get("geometry"),
                            "geometry": after.get("geometry") if apply_changes else geometry,
                        },
                    }
                )
            elif operation == "delete_entity":
                collection, _collection_name = _collection_for_sketch_entity_kind(drawing_container, kind)
                before_count = collection_count(collection)
                if entity_index < 0:
                    raise RuntimeError("sketch_entity_index_not_found")
                if apply_changes:
                    deleted = _delete_entity_from_collection(collection, entity, entity_index)
                    after_count = collection_count(collection)
                    if after_count >= before_count:
                        raise RuntimeError("sketch_entity_delete_not_confirmed")
                else:
                    deleted = False
                    after_count = before_count
                result.update(
                    {
                        "item": {
                            "kind": before.get("kind"),
                            "collection": before.get("collection"),
                            "collection_index": before.get("collection_index"),
                            "reference": before.get("reference"),
                            "fingerprint": before.get("fingerprint"),
                            "deleted": deleted,
                            "before_count": before_count,
                            "after_count": after_count,
                            "deleted_count": before_count - after_count if apply_changes else 0,
                        },
                        "summary": {
                            "planned": not apply_changes,
                            "deleted": deleted,
                            "before_count": before_count,
                            "after_count": after_count,
                            "deleted_count": before_count - after_count if apply_changes else 0,
                        },
                    }
                )
            items.append(result)
    finally:
        sketch.EndEdit()
    sketch_update_ok = None
    if apply_changes:
        sketch_update_ok = bool(sketch.Update())
        if not sketch_update_ok:
            raise RuntimeError("Sketch Update after repair returned False")
    return sketch, {
        "mode": "existing_sketch",
        "name": safe_get(sketch, "Name", ""),
        "sketch_ref": safe_get(sketch, "Reference", sketch_ref),
    }, items, {
        "operation_count": len(items),
        "applied": apply_changes,
        "planned": not apply_changes,
        "failed_count": sum(1 for item in items if not item.get("ok")),
        "sketch_update_ok": sketch_update_ok,
        "operations": [
            {
                "index": item.get("index"),
                "operation": item.get("operation"),
                "applied": item.get("applied"),
                "kind": item.get("kind"),
                "reference": item.get("reference"),
                "fingerprint": item.get("fingerprint"),
            }
            for item in items
        ],
    }


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


def _create_sketch_circle_with_coordinate_system(
    model_container,
    part,
    name,
    plane,
    center,
    radius,
    line_style,
    coordinate_system=None,
):
    sketch, plane_key = _create_sketch_on_plane(model_container, part, name, plane)
    if coordinate_system is not None:
        sketch.CoordinateSystem = coordinate_system
    if not sketch.Update():
        raise RuntimeError("Sketch Update returned False")
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


def _parameterize_compression_spring_profile_sketch(
    sketch,
    profile_circle,
    profile_center,
    wire_radius,
    params,
    steps_report,
):
    planned_constraints = list(params.get("profile_sketch_constraints") or [])
    planned_dimensions = list(params.get("profile_sketch_dimensions") or [])
    if not planned_constraints and not planned_dimensions:
        return None

    sketch_options = dict(params.get("sketch") or {})
    sketch_options.setdefault("parameterization_order", "constraints_first")
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None")
    parameterization_report = None
    try:
        view = _get_sketch_system_view(sketch_doc)
        drawing_container = cast_drawing_container(view)

        def references_target(value, target):
            if isinstance(value, dict):
                for key in ("target", "partner", "entity"):
                    if value.get(key) == target:
                        return True
                return any(references_target(item, target) for item in value.values())
            if isinstance(value, (list, tuple)):
                return any(references_target(item, target) for item in value)
            return False

        needs_radius_ref = references_target(planned_constraints, "radius_ref") or references_target(planned_dimensions, "radius_ref")
        needs_profile_radius_ref = references_target(planned_constraints, "profile_radius_ref") or references_target(planned_dimensions, "profile_radius_ref")
        line_segments = None
        construction_style = int(sketch_options.get("construction_line_style") or 6)
        helper_offset = max(float(wire_radius) * 0.25, 0.5)
        if needs_radius_ref or needs_profile_radius_ref:
            line_segments = safe_get(drawing_container, "LineSegments")
            if line_segments is None:
                get_line_segments = safe_get(drawing_container, "GetLineSegments")
                if callable(get_line_segments):
                    line_segments = get_line_segments()
            if line_segments is None or not callable(safe_get(line_segments, "Add")):
                raise RuntimeError("Sketch view does not expose LineSegments.Add")
        live_profile_circle = _resolve_current_sketch_circle(
            drawing_container,
            profile_circle,
            profile_center,
            wire_radius,
        )
        if live_profile_circle is None:
            raise RuntimeError("Current sketch profile circle was not found")
        circle_xc = float(safe_get(live_profile_circle, "Xc", profile_center[0]))
        circle_yc = float(safe_get(live_profile_circle, "Yc", profile_center[1]))
        sketch_entities = {
            "profile_circle": _sketch_circle_entry(
                live_profile_circle,
                circle_xc,
                circle_yc,
                float(wire_radius),
                role="circle",
                target="profile_circle",
            ),
            "origin": _sketch_point_entry(
                None,
                0.0,
                0.0,
                role="point",
                target="origin",
            ),
        }
        if needs_radius_ref:
            radius_ref = line_segments.Add()
            if radius_ref is None:
                raise RuntimeError("LineSegments.Add returned None")
            radius_ref.X1 = 0.0
            radius_ref.Y1 = 0.0
            if abs(float(profile_center[0])) <= 1e-9 and abs(float(profile_center[1])) <= 1e-9:
                radius_ref.X2 = helper_offset
                radius_ref.Y2 = 0.0
            else:
                radius_ref.X2 = float(profile_center[0])
                radius_ref.Y2 = float(profile_center[1])
            try:
                radius_ref.Style = construction_style
            except Exception:
                pass
            if not radius_ref.Update():
                raise RuntimeError("Radius reference Update returned False")
            sketch_entities["radius_ref"] = _sketch_line_entry(
                radius_ref,
                0.0,
                0.0,
                float(safe_get(radius_ref, "X2", profile_center[0]) or 0.0),
                float(safe_get(radius_ref, "Y2", profile_center[1]) or 0.0),
                role="construction",
                target="radius_ref",
            )
        if needs_profile_radius_ref:
            profile_radius_ref = line_segments.Add()
            if profile_radius_ref is None:
                raise RuntimeError("LineSegments.Add returned None")
            profile_radius_ref.X1 = float(profile_center[0])
            profile_radius_ref.Y1 = float(profile_center[1])
            profile_radius_ref.X2 = float(profile_center[0]) + helper_offset + float(wire_radius) * 1.5
            profile_radius_ref.Y2 = float(profile_center[1])
            try:
                profile_radius_ref.Style = construction_style
            except Exception:
                pass
            if not profile_radius_ref.Update():
                raise RuntimeError("Profile radius reference Update returned False")
            sketch_entities["profile_radius_ref"] = _sketch_line_entry(
                profile_radius_ref,
                float(profile_center[0]),
                float(profile_center[1]),
                float(profile_center[0]) + helper_offset + float(wire_radius) * 1.5,
                float(profile_center[1]),
                role="construction",
                target="profile_radius_ref",
            )
        transformed_constraints = list(planned_constraints)
        parameterization_report = _apply_sketch_parameterization(
            view,
            sketch_entities,
            transformed_constraints,
            planned_dimensions,
            sketch_options,
            steps_report,
            0.0,
        )
    finally:
        sketch.EndEdit()
    if not sketch.Update():
        raise RuntimeError("Sketch Update after spring profile parameterization returned False")
    if parameterization_report is None:
        return None
    parameterization_report["sketch_state"] = _describe_constraints_state(safe_get(sketch, "ConstraintsState"))
    parameterization_report["target_state"] = str(params.get("profile_sketch_target_state") or "fully_defined")
    state_ok = parameterization_report["sketch_state"].get("name") == "well_constrained"
    parameterization_report["state_ok"] = state_ok
    parameterization_report["ok"] = bool(parameterization_report.get("ok", True) and state_ok)
    steps_report.append(parameterization_report)
    return parameterization_report


def _resolve_compression_spring_profile_sketch_frame(params):
    plane = str((params or {}).get("plane") or "XOY").strip() or "XOY"
    normalized = plane.upper()
    rotation = None
    if normalized in {"XOY", "XY", "XOY_PLANE", "XY_PLANE", "PLANE_XOY"}:
        rotation = {"rz": 180.0}
    return plane, rotation


def _apply_spiral_turning_angle(spiral, position_parameters, angle_degrees, angle_application_mode="orientation"):
    requested_mode = str(angle_application_mode or "orientation").strip().lower()
    if requested_mode in ("default", "none"):
        return {
            "mode": "default",
            "requested_degrees": 0.0,
            "readback_degrees": 0.0,
        }
    if requested_mode == "turning_angle":
        try:
            spiral.TurningAngle = float(angle_degrees)
            return {
                "mode": "turning_angle",
                "requested_degrees": float(angle_degrees),
                "readback_degrees": float(safe_get(spiral, "TurningAngle", angle_degrees) or 0.0),
            }
        except Exception as exc:
            raise RuntimeError(
                "Failed to apply compression spring spiral TurningAngle: %s" % repr(exc)
            ) from exc
    if requested_mode == "orientation":
        try:
            position_parameters.AngleByOwnAxis(73, float(angle_degrees))
            return {
                "mode": "position_angle_by_own_axis",
                "requested_degrees": float(angle_degrees),
                "readback_degrees": float(angle_degrees),
            }
        except Exception as primary_exc:
            spiral_position = safe_get(spiral, "Position")
            if abs(float(angle_degrees)) > 1e-9 and spiral_position is not None:
                try:
                    spiral_position.OrientationType = 1
                    euler_parameters = safe_get(spiral_position, "LocalCSParameters")
                    if euler_parameters is None or safe_get(euler_parameters, "RotationAngle") is None:
                        raise AttributeError("Spiral position does not expose Euler rotation parameters")
                    if safe_get(euler_parameters, "NutationAngle") is not None:
                        euler_parameters.NutationAngle = 0.0
                    if safe_get(euler_parameters, "PrecessionAngle") is not None:
                        euler_parameters.PrecessionAngle = 0.0
                    euler_parameters.RotationAngle = float(angle_degrees)
                    return {
                        "mode": "position_local_cs_euler",
                        "requested_degrees": float(angle_degrees),
                        "readback_degrees": float(
                            safe_get(euler_parameters, "RotationAngle", angle_degrees) or 0.0
                        ),
                    }
                except Exception as fallback_exc:
                    raise RuntimeError(
                        "Failed to apply compression spring spiral orientation angle: own_axis=%s | euler=%s"
                        % (repr(primary_exc), repr(fallback_exc))
                    ) from fallback_exc
            raise RuntimeError(
                "Failed to apply compression spring spiral orientation angle: %s" % repr(primary_exc)
            ) from primary_exc
    raise RuntimeError("Unsupported compression spring angle application mode: %s" % angle_application_mode)


def _normalize_signed_angle_degrees(value):
    normalized = math.fmod(float(value), 360.0)
    if normalized <= -180.0:
        normalized += 360.0
    elif normalized > 180.0:
        normalized -= 360.0
    return normalized


def _distance3d(point1, point2):
    return math.sqrt(
        sum(
            (float(point1[index]) - float(point2[index])) ** 2
            for index in range(3)
        )
    )


def _sample_curve_endpoints(curve):
    points = []
    for at in (True, False):
        try:
            point = curve.GetPoint(at)
        except Exception:
            continue
        if not isinstance(point, tuple) or len(point) < 4 or not point[0]:
            continue
        points.append([float(point[1]), float(point[2]), float(point[3])])
    if len(points) < 2:
        return None
    return points[:2]


def _fillet_cut_points_near_shared_endpoint(curve1, curve2, curve1_ratio=0.05, curve2_ratio=0.03):
    curve1_points = _sample_curve_endpoints(curve1)
    curve2_points = _sample_curve_endpoints(curve2)
    if not curve1_points or not curve2_points:
        return None, None
    best = None
    for index1, point1 in enumerate(curve1_points):
        for index2, point2 in enumerate(curve2_points):
            distance = _distance3d(point1, point2)
            if best is None or distance < best[0]:
                best = (distance, index1, index2)
    if best is None:
        return None, None
    _, index1, index2 = best
    shared1 = curve1_points[index1]
    shared2 = curve2_points[index2]
    other1 = curve1_points[1 - index1]
    other2 = curve2_points[1 - index2]

    def inward(shared, other, ratio):
        return [float(shared[i]) + (float(other[i]) - float(shared[i])) * float(ratio) for i in range(3)]

    return inward(shared1, other1, curve1_ratio), inward(shared2, other2, curve2_ratio)


def _curve_cut_point_near_point(curve, point, ratio=0.03):
    curve_points = _sample_curve_endpoints(curve)
    if not curve_points or not point:
        return None
    shared_index = 0 if _distance3d(curve_points[0], point) <= _distance3d(curve_points[1], point) else 1
    shared = curve_points[shared_index]
    other = curve_points[1 - shared_index]
    return [float(shared[i]) + (float(other[i]) - float(shared[i])) * float(ratio) for i in range(3)]


def _score_curve_endpoints(actual_points, expected_start, expected_end):
    pairings = (
        (actual_points[0], actual_points[1], False),
        (actual_points[1], actual_points[0], True),
    )
    best = None
    for actual_start, actual_end, reversed_order in pairings:
        start_gap = _distance3d(actual_start, expected_start)
        end_gap = _distance3d(actual_end, expected_end)
        score = start_gap + end_gap
        candidate = {
            "score": score,
            "start_gap": start_gap,
            "end_gap": end_gap,
            "actual_start": list(actual_start),
            "actual_end": list(actual_end),
            "reversed": reversed_order,
        }
        if best is None or candidate["score"] < best["score"]:
            best = candidate
    return best


def _build_spiral_turning_angle_candidates(angle_degrees, angle_application_mode="orientation"):
    requested_mode = str(angle_application_mode or "orientation").strip().lower()
    if requested_mode != "orientation":
        return [0.0]
    candidates = []

    def add(value):
        candidate = float(value)
        for existing in candidates:
            if abs(existing - candidate) <= 1e-9:
                return
        candidates.append(candidate)

    raw_angle = float(angle_degrees)
    base_values = (
        raw_angle,
        -raw_angle,
        raw_angle - 180.0,
        raw_angle + 180.0,
        -raw_angle - 180.0,
        -raw_angle + 180.0,
        _normalize_signed_angle_degrees(raw_angle),
        _normalize_signed_angle_degrees(-raw_angle),
        _normalize_signed_angle_degrees(raw_angle - 180.0),
        _normalize_signed_angle_degrees(raw_angle + 180.0),
    )
    for value in base_values:
        add(value)
    for base in tuple(candidates):
        add(base - 360.0)
        add(base + 360.0)
    if abs(_normalize_signed_angle_degrees(raw_angle)) <= 1e-9:
        add(-360.0)
        add(360.0)
    return candidates


def _resolve_best_spiral_turning_angle(
    spiral,
    position_parameters,
    angle_degrees,
    angle_application_mode="orientation",
    expected_start=None,
    expected_end=None,
):
    candidates = _build_spiral_turning_angle_candidates(angle_degrees, angle_application_mode)
    best = None
    applied_candidate = None
    fallback_report = None
    for candidate in candidates:
        angle_report = _apply_spiral_turning_angle(
            spiral,
            position_parameters,
            candidate,
            angle_application_mode,
        )
        if not bool(spiral.Update()):
            continue
        endpoint_score = None
        geometry_checked = False
        if expected_start is not None and expected_end is not None:
            actual_points = _sample_curve_endpoints(spiral)
            if actual_points is not None:
                geometry_checked = True
                endpoint_score = _score_curve_endpoints(actual_points, expected_start, expected_end)
        if endpoint_score is None:
            endpoint_score = {
                "score": 0.0,
                "start_gap": 0.0,
                "end_gap": 0.0,
                "actual_start": None,
                "actual_end": None,
                "reversed": False,
            }
        geometry_ok = None
        if geometry_checked:
            geometry_ok = endpoint_score["start_gap"] <= 1e-6 and endpoint_score["end_gap"] <= 1e-6
        candidate_report = dict(angle_report)
        candidate_report.update(
            {
                "candidate_degrees": float(candidate),
                "geometry_checked": geometry_checked,
                "geometry_ok": geometry_ok,
                "start_gap": float(endpoint_score["start_gap"]),
                "end_gap": float(endpoint_score["end_gap"]),
                "actual_start": endpoint_score["actual_start"],
                "actual_end": endpoint_score["actual_end"],
                "reversed": bool(endpoint_score["reversed"]),
                "expected_start": list(expected_start) if expected_start is not None else None,
                "expected_end": list(expected_end) if expected_end is not None else None,
                "score": float(endpoint_score["score"]),
            }
        )
        fallback_report = candidate_report
        if best is None or candidate_report["score"] < best["score"]:
            best = candidate_report
            applied_candidate = float(candidate)
        if geometry_checked and geometry_ok:
            best = candidate_report
            applied_candidate = float(candidate)
            break
        if not geometry_checked:
            best = candidate_report
            applied_candidate = float(candidate)
            break
    if best is None:
        raise RuntimeError("Failed to evaluate compression spring spiral turning angle candidates")
    if applied_candidate is None or abs(applied_candidate - best["candidate_degrees"]) > 1e-9:
        best = fallback_report or best
    if (
        expected_start is not None
        and expected_end is not None
        and best.get("geometry_checked")
        and not best["geometry_ok"]
    ):
        raise RuntimeError(
            "Compression spring spiral turning angle verification failed: requested=%s best=%s start_gap=%s end_gap=%s"
            % (
                angle_degrees,
                best["candidate_degrees"],
                best["start_gap"],
                best["end_gap"],
            )
        )
    return best


def _compute_curve_endpoint_report(curve_object, expected_start=None, expected_end=None):
    actual_points = _sample_curve_endpoints(curve_object)
    geometry_checked = False
    endpoint_score = None
    if actual_points is not None and expected_start is not None and expected_end is not None:
        geometry_checked = True
        endpoint_score = _score_curve_endpoints(actual_points, expected_start, expected_end)
    if endpoint_score is None:
        endpoint_score = {
            "score": 0.0,
            "start_gap": 0.0,
            "end_gap": 0.0,
            "actual_start": None,
            "actual_end": None,
            "reversed": False,
        }
    geometry_ok = None
    if geometry_checked:
        geometry_ok = endpoint_score["start_gap"] <= 1e-6 and endpoint_score["end_gap"] <= 1e-6
    return {
        "geometry_checked": geometry_checked,
        "geometry_ok": geometry_ok,
        "start_gap": float(endpoint_score["start_gap"]),
        "end_gap": float(endpoint_score["end_gap"]),
        "actual_start": endpoint_score["actual_start"],
        "actual_end": endpoint_score["actual_end"],
        "reversed": bool(endpoint_score["reversed"]),
        "expected_start": list(expected_start) if expected_start is not None else None,
        "expected_end": list(expected_end) if expected_end is not None else None,
        "score": float(endpoint_score["score"]),
    }


def _curve_contour_edges_count(contour):
    edges_count = safe_get(contour, "EdgesCount")
    if edges_count is not None:
        try:
            return int(edges_count)
        except Exception:
            pass
    edges = safe_get(contour, "Edges")
    if isinstance(edges, (list, tuple)):
        return len(edges)
    count = collection_count(edges)
    if count:
        return int(count)
    return None


def _curve_reference_report(curve_object):
    if curve_object is None:
        return None
    reference = safe_get(curve_object, "Reference")
    name = safe_get(curve_object, "Name")
    model_type = safe_get(curve_object, "ModelObjectType")
    return {
        "reference": str(reference) if reference is not None else None,
        "name": str(name) if name is not None else None,
        "model_object_type": str(model_type) if model_type is not None else None,
    }


def _curve_collection_reference_report(curves):
    if curves is None:
        return []
    if isinstance(curves, (list, tuple)):
        return [_curve_reference_report(curve) for curve in curves]
    count = collection_count(curves)
    if not count:
        return []
    return [_curve_reference_report(get_collection_item(curves, index)) for index in range(count)]


def _build_curve_contour(
    auxiliary_container,
    name,
    curves,
    allow_incomplete=False,
    contour=None,
    expected_edges_count=None,
):
    if contour is None:
        contour = auxiliary_container.Contours3D.Add()
        if contour is None:
            raise RuntimeError("Contours3D.Add() returned None")
    contour.Edges = list(curves)
    try:
        contour.Name = name
    except Exception:
        pass
    if not bool(contour.Update()):
        raise RuntimeError("Failed to build spring path contour")
    edges_count = _curve_contour_edges_count(contour)
    source_count = len(curves)
    expected_count = int(expected_edges_count) if expected_edges_count is not None else int(source_count)
    if edges_count is None:
        raise RuntimeError("Failed to confirm spring path contour completeness")
    report = {
        "source_path_count": int(source_count),
        "edges_count": int(edges_count),
        "expected_edges_count": int(expected_count),
        "source_path_references": _curve_collection_reference_report(curves),
        "contour_edge_references": _curve_collection_reference_report(safe_get(contour, "Edges")),
    }
    if not allow_incomplete and int(edges_count) != int(expected_count):
        raise RuntimeError(
            "Spring path contour completeness check failed: expected %s edges, got %s"
            % (expected_count, edges_count)
        )
    return contour, report


def _delete_curve_contour(auxiliary_container, contour):
    if contour is None:
        return False
    contour_collection = safe_get(auxiliary_container, "Contours3D")
    contour_reference = safe_get(contour, "Reference")
    collection_count_value = collection_count(contour_collection)
    for index in range(collection_count_value):
        item = get_collection_item(contour_collection, index)
        if item is contour:
            try:
                return _delete_feature_from_collection(contour_collection, contour, index)
            except RuntimeError as exc:
                if "feature_delete_not_supported" not in str(exc):
                    raise
                break
        if contour_reference is not None and safe_get(item, "Reference") == contour_reference:
            try:
                return _delete_feature_from_collection(contour_collection, contour, index)
            except RuntimeError as exc:
                if "feature_delete_not_supported" not in str(exc):
                    raise
                break
    deleter = safe_get(contour, "Delete")
    if callable(deleter):
        result = deleter()
        return True if result is None else bool(result)
    return False


def _normalize_curve_cut_point(point):
    if not isinstance(point, (list, tuple)) or len(point) != 3:
        return None
    try:
        return [float(point[0]), float(point[1]), float(point[2])]
    except Exception:
        return None


def _create_curve_fillet_path(
    auxiliary_container,
    name,
    curve1,
    curve2,
    radius,
    trim_curve1=True,
    trim_curve2=True,
    curve1_cut_point=None,
    curve2_cut_point=None,
):
    fillet_curves = safe_get(auxiliary_container, "FilletCurves")
    if fillet_curves is None or not callable(safe_get(fillet_curves, "Add")):
        raise RuntimeError("Auxiliary geometry container does not expose FilletCurves.Add")
    fillet = fillet_curves.Add()
    if fillet is None:
        raise RuntimeError("FilletCurves.Add() returned None")
    try:
        fillet.Name = name
    except Exception:
        pass
    fillet.Curve1 = curve1
    fillet.Curve2 = curve2
    fillet.Radius = float(radius)
    fillet.TrimCurve1 = bool(trim_curve1)
    fillet.TrimCurve2 = bool(trim_curve2)
    normalized_curve1_cut_point = _normalize_curve_cut_point(curve1_cut_point)
    normalized_curve2_cut_point = _normalize_curve_cut_point(curve2_cut_point)
    if normalized_curve1_cut_point is not None:
        fillet.SetCurve1CutPoint(*normalized_curve1_cut_point)
    if normalized_curve2_cut_point is not None:
        fillet.SetCurve2CutPoint(*normalized_curve2_cut_point)
    if not bool(fillet.Update()):
        raise RuntimeError("Failed to create curve fillet path %s" % name)
    return fillet


def _create_staged_curve_fillet_path(
    auxiliary_container,
    name,
    curve1,
    curve2,
    radius,
    trim_curve1=True,
    trim_curve2=True,
    curve1_cut_point=None,
    curve2_cut_point=None,
):
    fillet_curves = safe_get(auxiliary_container, "FilletCurves")
    if fillet_curves is None or not callable(safe_get(fillet_curves, "Add")):
        raise RuntimeError("Auxiliary geometry container does not expose FilletCurves.Add")
    fillet = fillet_curves.Add()
    if fillet is None:
        raise RuntimeError("FilletCurves.Add() returned None")
    try:
        fillet.Name = name
    except Exception:
        pass
    fillet.Curve1 = curve1
    fillet.Curve2 = curve2
    fillet.TrimCurve1 = bool(trim_curve1)
    fillet.TrimCurve2 = bool(trim_curve2)
    normalized_curve1_cut_point = _normalize_curve_cut_point(curve1_cut_point)
    normalized_curve2_cut_point = _normalize_curve_cut_point(curve2_cut_point)
    if normalized_curve1_cut_point is not None:
        fillet.SetCurve1CutPoint(*normalized_curve1_cut_point)
    if normalized_curve2_cut_point is not None:
        fillet.SetCurve2CutPoint(*normalized_curve2_cut_point)
    first_update = bool(fillet.Update())
    fillet.Radius = float(radius)
    second_update = bool(fillet.Update())
    if not second_update:
        raise RuntimeError("Failed to create staged curve fillet path %s" % name)
    return fillet, [first_update, second_update]


def _create_connect_curve_path(
    auxiliary_container,
    name,
    curve1,
    curve2,
    curve1_connect_vertex=True,
    curve2_connect_vertex=True,
    curve1_connect_type=3,
    curve2_connect_type=None,
    tension=100.0,
    operation_variable_bindings=None,
):
    connect_curves = safe_get(auxiliary_container, "ConnectCurves")
    if connect_curves is None or not callable(safe_get(connect_curves, "Add")):
        raise RuntimeError("Auxiliary geometry container does not expose ConnectCurves.Add")
    connect_curve = connect_curves.Add()
    if connect_curve is None:
        raise RuntimeError("ConnectCurves.Add() returned None")
    try:
        connect_curve.Name = name
    except Exception:
        pass
    connect_curve.Curve1 = curve1
    connect_curve.Curve2 = curve2
    connect_curve.Curve1ConnectVertex = bool(curve1_connect_vertex)
    connect_curve.Curve2ConnectVertex = bool(curve2_connect_vertex)
    connect_curve.Curve1ConnectType = int(curve1_connect_type)
    connect_curve.Curve2ConnectType = int(curve1_connect_type if curve2_connect_type is None else curve2_connect_type)
    connect_curve.Tension = float(tension)
    if not bool(connect_curve.Update()):
        raise RuntimeError("Failed to create connect curve path %s" % name)
    binding_report = None
    if operation_variable_bindings:
        binding_report = _bind_operation_variables(connect_curve, operation_variable_bindings)
        if not binding_report.get("ok", False):
            raise RuntimeError("Failed to bind connect curve operation variables for %s" % name)
        if not bool(connect_curve.Update()):
            raise RuntimeError("Failed to update connect curve path %s after variable binding" % name)
    return connect_curve, binding_report


def _build_compression_spring_transition_curve_paths(
    part,
    model_container,
    auxiliary_container,
    spring_name,
    segment_objects,
    connector_plan,
    steps_report,
):
    if not connector_plan:
        return []
    curve_by_path_name = {
        str(item.get("path_name") or ""): item
        for item in segment_objects
        if item.get("path") is not None
    }
    created_curve_objects = []
    for connector in connector_plan:
        builder = str(connector.get("builder") or "curve_fillet").strip().lower()
        curve1_path_name = str(connector.get("curve1_path_name") or "").strip()
        curve2_path_name = str(connector.get("curve2_path_name") or "").strip()
        curve1_object = curve_by_path_name.get(curve1_path_name)
        curve2_object = curve_by_path_name.get(curve2_path_name)
        if curve1_object is None or curve2_object is None:
            raise RuntimeError(
                "Compression spring transition fillet curves require existing segment paths: %s -> %s"
                % (curve1_path_name, curve2_path_name)
            )
        if builder == "trimmed_connect_curve":
            curve1_trim = dict(connector.get("curve1_trim") or {})
            curve2_trim = dict(connector.get("curve2_trim") or {})
            connect_curve_plan = dict(connector.get("connect_curve") or {})

            curve1_point, trimmed_curve1, curve1_point_binding_report = _create_trimmed_curve_path(
                part,
                model_container,
                str(curve1_trim.get("name") or ("%s_curve1_local" % spring_name)),
                curve1_object["path"],
                point_name=str(curve1_trim.get("point_name") or ""),
                offset=float(curve1_trim.get("offset") or 0.0),
                direction=bool(curve1_trim.get("direction", True)),
                offset_type=int(curve1_trim.get("offset_type", 0)),
                sense=bool(curve1_trim.get("sense", True)),
                point_variable_bindings=list(curve1_trim.get("point_operation_variable_bindings") or []),
            )
            created_curve1 = {
                "role": "%s_curve1_trim" % str(connector.get("role") or ""),
                "path_name": str(curve1_trim.get("name") or ""),
                "path": trimmed_curve1,
                "kind": "trimmed_curve",
                "source_path_name": curve1_path_name,
                "point": curve1_point,
            }
            created_curve_objects.append(created_curve1)
            curve_by_path_name[created_curve1["path_name"]] = created_curve1
            steps_report.append(
                {
                    "step": "create_trimmed_curve_path",
                    "ok": True,
                    "scenario": "compression_spring",
                    "role": created_curve1["role"],
                    "reference": safe_get(trimmed_curve1, "Reference"),
                    "model_object_type": safe_get(trimmed_curve1, "ModelObjectType"),
                    "source_path_name": curve1_path_name,
                    "point_name": str(curve1_trim.get("point_name") or ""),
                    "offset": float(curve1_trim.get("offset") or 0.0),
                    "offset_type": int(curve1_trim.get("offset_type", 0)),
                    "direction": bool(curve1_trim.get("direction", True)),
                    "sense": bool(curve1_trim.get("sense", True)),
                    "offset_expression": str(
                        ((curve1_trim.get("point_operation_variable_bindings") or [{}])[0]).get("expression")
                        or ""
                    ),
                }
            )
            if curve1_point_binding_report is not None:
                curve1_point_binding_report["scenario"] = "compression_spring"
                curve1_point_binding_report["target"] = "transition_trim_point"
                curve1_point_binding_report["role"] = "%s_curve1_trim_point" % str(connector.get("role") or "")
                curve1_point_binding_report["path_name"] = str(curve1_trim.get("name") or "")
                curve1_point_binding_report["point_name"] = str(curve1_trim.get("point_name") or "")
                steps_report.append(curve1_point_binding_report)

            curve2_point, trimmed_curve2, curve2_point_binding_report = _create_trimmed_curve_path(
                part,
                model_container,
                str(curve2_trim.get("name") or ("%s_curve2_local" % spring_name)),
                curve2_object["path"],
                point_name=str(curve2_trim.get("point_name") or ""),
                offset=float(curve2_trim.get("offset") or 0.0),
                direction=bool(curve2_trim.get("direction", True)),
                offset_type=int(curve2_trim.get("offset_type", 0)),
                sense=bool(curve2_trim.get("sense", True)),
                point_variable_bindings=list(curve2_trim.get("point_operation_variable_bindings") or []),
            )
            created_curve2 = {
                "role": "%s_curve2_trim" % str(connector.get("role") or ""),
                "path_name": str(curve2_trim.get("name") or ""),
                "path": trimmed_curve2,
                "kind": "trimmed_curve",
                "source_path_name": curve2_path_name,
                "point": curve2_point,
            }
            created_curve_objects.append(created_curve2)
            curve_by_path_name[created_curve2["path_name"]] = created_curve2
            steps_report.append(
                {
                    "step": "create_trimmed_curve_path",
                    "ok": True,
                    "scenario": "compression_spring",
                    "role": created_curve2["role"],
                    "reference": safe_get(trimmed_curve2, "Reference"),
                    "model_object_type": safe_get(trimmed_curve2, "ModelObjectType"),
                    "source_path_name": curve2_path_name,
                    "point_name": str(curve2_trim.get("point_name") or ""),
                    "offset": float(curve2_trim.get("offset") or 0.0),
                    "offset_type": int(curve2_trim.get("offset_type", 0)),
                    "direction": bool(curve2_trim.get("direction", True)),
                    "sense": bool(curve2_trim.get("sense", True)),
                    "offset_expression": str(
                        ((curve2_trim.get("point_operation_variable_bindings") or [{}])[0]).get("expression")
                        or ""
                    ),
                }
            )
            if curve2_point_binding_report is not None:
                curve2_point_binding_report["scenario"] = "compression_spring"
                curve2_point_binding_report["target"] = "transition_trim_point"
                curve2_point_binding_report["role"] = "%s_curve2_trim_point" % str(connector.get("role") or "")
                curve2_point_binding_report["path_name"] = str(curve2_trim.get("name") or "")
                curve2_point_binding_report["point_name"] = str(curve2_trim.get("point_name") or "")
                steps_report.append(curve2_point_binding_report)

            connect_curve_name = str(connect_curve_plan.get("name") or ("%s_TRANSITION_CONNECT" % spring_name))
            connect_curve_binding_report = None
            connect_curve_fallback = None
            try:
                connect_curve, connect_curve_binding_report = _create_connect_curve_path(
                    auxiliary_container,
                    connect_curve_name,
                    trimmed_curve1,
                    trimmed_curve2,
                    curve1_connect_vertex=bool(connect_curve_plan.get("curve1_connect_vertex", True)),
                    curve2_connect_vertex=bool(connect_curve_plan.get("curve2_connect_vertex", True)),
                    curve1_connect_type=int(connect_curve_plan.get("curve1_connect_type", 3)),
                    curve2_connect_type=int(connect_curve_plan.get("curve2_connect_type", 3)),
                    tension=float(connect_curve_plan.get("tension") or 100.0),
                    operation_variable_bindings=list(connect_curve_plan.get("operation_variable_bindings") or []),
                )
            except RuntimeError as exc:
                connect_curve = trimmed_curve1
                connect_curve_fallback = str(exc)
            created_connect_curve = {
                "role": str(connector.get("role") or ""),
                "path_name": connect_curve_name,
                "path": connect_curve,
                "kind": "connect_curve" if connect_curve_fallback is None else "connect_curve_fallback",
                "curve1_path_name": created_curve1["path_name"],
                "curve2_path_name": created_curve2["path_name"],
            }
            created_curve_objects.append(created_connect_curve)
            curve_by_path_name[created_connect_curve["path_name"]] = created_connect_curve
            steps_report.append(
                {
                    "step": "create_connect_curve_path",
                    "ok": True,
                    "scenario": "compression_spring",
                    "role": created_connect_curve["role"],
                    "reference": safe_get(connect_curve, "Reference"),
                    "model_object_type": safe_get(connect_curve, "ModelObjectType"),
                    "curve1_path_name": created_curve1["path_name"],
                    "curve2_path_name": created_curve2["path_name"],
                    "curve1_connect_vertex": bool(connect_curve_plan.get("curve1_connect_vertex", True)),
                    "curve2_connect_vertex": bool(connect_curve_plan.get("curve2_connect_vertex", True)),
                    "curve1_connect_type": int(connect_curve_plan.get("curve1_connect_type", 3)),
                    "curve2_connect_type": int(connect_curve_plan.get("curve2_connect_type", 3)),
                    "tension": float(connect_curve_plan.get("tension") or 100.0),
                    "tension_expression": str(
                        ((connect_curve_plan.get("operation_variable_bindings") or [{}])[0]).get("expression")
                        or ""
                    ),
                    "fallback": connect_curve_fallback,
                }
            )
            if connect_curve_binding_report is not None:
                connect_curve_binding_report["scenario"] = "compression_spring"
                connect_curve_binding_report["target"] = "connect_curve"
                connect_curve_binding_report["role"] = created_connect_curve["role"]
                connect_curve_binding_report["path_name"] = created_connect_curve["path_name"]
                steps_report.append(connect_curve_binding_report)
            continue
        fillet_name = str(connector.get("path_name") or ("%s_TRANSITION_FILLET" % spring_name)).strip()
        joint_point = connector.get("joint_point")
        fillet, staged_updates = _create_staged_curve_fillet_path(
            auxiliary_container,
            fillet_name,
            curve1_object["path"],
            curve2_object["path"],
            radius=float(connector.get("radius") or 0.0),
            trim_curve1=bool(connector.get("trim_curve1", True)),
            trim_curve2=bool(connector.get("trim_curve2", True)),
            curve1_cut_point=connector.get("curve1_cut_point", joint_point),
            curve2_cut_point=connector.get("curve2_cut_point", joint_point),
        )
        fillet_binding_report = None
        if connector.get("operation_variable_bindings"):
            fillet_binding_report = _bind_operation_variables(fillet, connector.get("operation_variable_bindings") or [])
            if not fillet_binding_report.get("ok", False):
                raise RuntimeError("Failed to bind curve fillet operation variables for %s" % fillet_name)
            if not bool(fillet.Update()):
                raise RuntimeError("Failed to update curve fillet path %s after variable binding" % fillet_name)
        connector_object = {
            "role": str(connector.get("role") or ""),
            "path_name": fillet_name,
            "path": fillet,
            "kind": "curve_fillet",
            "joint_point": list(joint_point or []),
            "curve1_path_name": curve1_path_name,
            "curve2_path_name": curve2_path_name,
        }
        created_curve_objects.append(connector_object)
        curve_by_path_name[connector_object["path_name"]] = connector_object
        result_edges = _fillet_result_edges(fillet, expected_count=None)
        edge_names = list(connector.get("result_edge_path_names") or [connector.get("sequence_curve1_path_name"), connector.get("sequence_fillet_path_name"), connector.get("sequence_curve2_path_name")])
        edge_order = list(connector.get("result_edge_order") or [1, 0, 2])
        edge_entries = []
        if len(result_edges) >= len(edge_order) and len(edge_names) >= len(edge_order) and all(edge_names):
            for logical_index, edge_index in enumerate(edge_order):
                edge = result_edges[int(edge_index)]
                edge_object = {
                    "role": connector_object["role"],
                    "path_name": str(edge_names[logical_index]),
                    "path": edge,
                    "kind": "curve_fillet_result_edge",
                    "edge_index": int(edge_index),
                    "feature_path_name": fillet_name,
                }
                created_curve_objects.append(edge_object)
                curve_by_path_name[edge_object["path_name"]] = edge_object
                edge_entries.append({"path_name": edge_object["path_name"], "edge_index": int(edge_index), "reference": safe_get(edge, "Reference")})
        steps_report.append(
            {
                "step": "create_curve_fillet_path",
                "ok": True,
                "scenario": "compression_spring",
                "role": connector_object["role"],
                "reference": safe_get(fillet, "Reference"),
                "model_object_type": safe_get(fillet, "ModelObjectType"),
                "curve1_path_name": curve1_path_name,
                "curve2_path_name": curve2_path_name,
                "joint_point": list(joint_point or []),
                "radius": float(connector.get("radius") or 0.0),
                "radius_readback": safe_get(fillet, "Radius"),
                "staged_updates": staged_updates,
                "trim_curve1": bool(connector.get("trim_curve1", True)),
                "trim_curve2": bool(connector.get("trim_curve2", True)),
                "result_edge_count": len(result_edges),
                "sequence_edges": edge_entries,
            }
        )
        if fillet_binding_report is not None:
            fillet_binding_report["scenario"] = "compression_spring"
            fillet_binding_report["target"] = "curve_fillet"
            fillet_binding_report["role"] = connector_object["role"]
            fillet_binding_report["path_name"] = connector_object["path_name"]
            steps_report.append(fillet_binding_report)
    return created_curve_objects


def _find_sketch_by_name(model_container, name: str):
    sketches = _get_sketch_collection(model_container)
    for index in range(collection_count(sketches)):
        sketch = _cast_to_com_interface(get_collection_item(sketches, index), "ISketch")
        if safe_get(sketch, "Name") == name:
            return sketch
    raise RuntimeError("Sketch not found: %s" % name)


def _find_fillet_curve_by_name(auxiliary_container, name: str):
    fillets = safe_get(auxiliary_container, "FilletCurves")
    for index in range(collection_count(fillets)):
        fillet = get_collection_item(fillets, index)
        if safe_get(fillet, "Name") == name:
            return fillet
    raise RuntimeError("FilletCurve not found: %s" % name)


def _sketch_edges_list(sketch, edge_type: int) -> list:
    raw_edges = sketch.Edges(edge_type)
    return list(raw_edges) if isinstance(raw_edges, (list, tuple)) else list(iter_collection(raw_edges))


def _fillet_result_edges(fillet, expected_count=3) -> list:
    owner = safe_get(fillet, "Owner")
    if owner is None:
        raise RuntimeError("FilletCurve has no Owner feature")
    model_objects = safe_get(owner, "ModelObjects")
    if not callable(model_objects):
        raise RuntimeError("FilletCurve owner does not expose ModelObjects")
    result = model_objects(7)
    edges = list(result) if isinstance(result, (list, tuple)) else list(iter_collection(result))
    if expected_count is not None and len(edges) != int(expected_count):
        raise RuntimeError("Expected %s result edges from FilletCurve owner ModelObjects(7), got %s" % (int(expected_count), len(edges)))
    return edges


def _find_named_auxiliary_object(container, collection_name: str, name: str):
    collection = safe_get(container, collection_name)
    if collection is None:
        getter = safe_get(container, "Get%s" % collection_name)
        if callable(getter):
            collection = getter()
    if collection is None:
        return None
    for index in range(collection_count(collection)):
        item = get_collection_item(collection, index)
        if safe_get(item, "Name") == name:
            return item
    return None


def _transform_self_wrapping_payload_from_endpoint(payload: dict, endpoint_xy: list, spring_radius: float, *, mirror_x: bool, remove_fixed_origin: bool = False) -> dict:
    copied = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    anchor_x = float(endpoint_xy[0])
    anchor_y = float(endpoint_xy[1])

    def transform(point):
        local_x = float(point[0])
        local_y = float(point[1]) - float(spring_radius)
        point[0] = anchor_x - local_x if mirror_x else anchor_x + local_x
        point[1] = anchor_y + local_y

    for entity in copied.get("entities") or []:
        for key in ("start", "end", "center"):
            point = entity.get(key)
            if isinstance(point, list) and len(point) >= 2:
                transform(point)
        if mirror_x and entity.get("kind") == "arc" and "direction" in entity:
            entity["direction"] = not bool(entity.get("direction"))
    if remove_fixed_origin:
        copied["constraints"] = [
            constraint
            for constraint in copied.get("constraints") or []
            if not (constraint.get("kind") == "fixed_point" and constraint.get("target") == "spring_radius_axis" and int(constraint.get("index", 0)) == 0)
        ]
    return copied


def _add_self_wrapping_work_axis_entity(payload: dict, endpoint_xy: list, spring_radius: float) -> dict:
    copied = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    entities = list(copied.get("entities") or [])
    by_id = {entity.get("id"): entity for entity in entities}
    diagonal = by_id.get("work_diagonal")
    shelf = by_id.get("work_shelf")
    if not diagonal or not shelf:
        return copied
    diagonal_points = [list(diagonal.get("start") or []), list(diagonal.get("end") or [])]
    shelf_points = [list(shelf.get("start") or []), list(shelf.get("end") or [])]
    if len(diagonal_points[0]) < 2 or len(diagonal_points[1]) < 2 or len(shelf_points[0]) < 2 or len(shelf_points[1]) < 2:
        return copied

    endpoint_xy = [float(endpoint_xy[0]), float(endpoint_xy[1])]

    def dist2(point):
        return (float(point[0]) - endpoint_xy[0]) ** 2 + (float(point[1]) - endpoint_xy[1]) ** 2

    spring_index = 0 if dist2(diagonal_points[0]) <= dist2(diagonal_points[1]) else 1
    spring_point = [float(diagonal_points[spring_index][0]), float(diagonal_points[spring_index][1])]
    diag_far = [float(diagonal_points[1 - spring_index][0]), float(diagonal_points[1 - spring_index][1])]
    shelf_free = max(shelf_points, key=lambda point: float(point[1]))
    shelf_free = [float(shelf_free[0]), float(shelf_free[1])]
    mirror_start = [0.0, -abs(float(spring_radius))]
    mirror_end = [float(diag_far[0]), -float(diag_far[1])]

    def line_intersection(a1, a2, b1, b2):
        x1, y1 = a1
        x2, y2 = a2
        x3, y3 = b1
        x4, y4 = b2
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-9:
            return None
        px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
        py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
        return [float(px), float(py)]

    axis_start = line_intersection(spring_point, diag_far, mirror_start, mirror_end) or list(spring_point)
    entities.append(
        {
            "kind": "segment",
            "id": "work_axis",
            "start": axis_start,
            "end": shelf_free,
            "role": "construction_self_wrapping_work_axis",
            "line_style": 3,
        }
    )
    copied["entities"] = entities
    return copied


def _mirror_payload_x(payload: dict) -> dict:
    copied = json.loads(json.dumps(payload, ensure_ascii=False, default=str))

    def mirror_point(point):
        if isinstance(point, list) and len(point) >= 2:
            point[0] = -float(point[0])

    for entity in copied.get("entities") or []:
        for key in ("start", "end", "center", "point", "position"):
            mirror_point(entity.get(key))
    return copied


def _right_endpoint_self_wrapping_payload(params: dict) -> dict:
    payload = _first_sketch_self_wrapping_payload(params)
    spring_radius = float(_variable_value(params, "SRAD1", (float(params.get("outer_diameter", 30.0)) - float(params.get("wire_diameter", 3.0))) / 2.0))
    half_width = float(_variable_value(params, "SHW1", float(_variable_value(params, "SW1", 40.0)) / 2.0))
    top = [0.0, spring_radius]
    bottom_right = [0.0, -half_width]
    removed_ids = {"spring_radius_axis", "half_width_axis"}
    payload["entities"] = [entity for entity in payload.get("entities") or [] if entity.get("id") not in removed_ids]
    payload["entities"].insert(
        0,
        {"kind": "segment", "id": "endpoint_to_bottom_axis", "start": top, "end": bottom_right, "role": "construction_endpoint_to_bottom_axis", "line_style": 6},
    )
    payload["constraints"] = [
        constraint for constraint in payload.get("constraints") or []
        if constraint.get("target") not in removed_ids and constraint.get("partner") not in removed_ids
    ]
    payload["constraints"].extend(
        [
            {"kind": "merge_points", "target": "endpoint_to_bottom_axis", "index": 0, "partner": "diagonal_axis", "partner_index": 0},
            {"kind": "merge_points", "target": "endpoint_to_bottom_axis", "index": 0, "partner": "work_diagonal", "partner_index": 0},
            {"kind": "merge_points", "target": "endpoint_to_bottom_axis", "index": 1, "partner": "height_axis", "partner_index": 0},
            {"kind": "vertical", "target": "endpoint_to_bottom_axis"},
        ]
    )
    payload["dimensions"] = [dimension for dimension in payload.get("dimensions") or [] if dimension.get("target") not in removed_ids]
    payload["dimensions"].insert(
        0,
        {"kind": "line_length", "target": "endpoint_to_bottom_axis", "value": spring_radius + half_width, "expression": "(D1 - WD1) / 2 + SHW1"},
    )
    return payload


def _bind_first_sketch_start_to_projected_point(sketch, sketch_items: list, point3d, *, targets=("spring_radius_axis", "work_diagonal"), target_indices=None, projected_xy=None, projected_object=None, projection_report=None) -> dict:
    report = {"ok": True, "targets": [], "projection": projection_report or {}}
    if sketch is None or point3d is None:
        return {"ok": False, "error": "missing sketch or point"}
    if projected_xy is None or projected_object is None:
        projection_report, projected_object = _project_point_to_sketch_xy_with_object(sketch, point3d)
        report["projection"] = projection_report
        projected_xy = projection_report.get("xy")
    if projected_object is None:
        return {"ok": False, "error": "projection object was not created", "projection": report.get("projection"), "projected_xy": projected_xy}
    by_id = {item.get("id"): item for item in sketch_items or [] if isinstance(item, dict) and item.get("id")}
    sketch_doc = sketch.BeginEdit()
    try:
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        local_projection = None
        add_projection = safe_get(sketch, "AddProjectionOf")
        if callable(add_projection):
            try:
                raw_projection = add_projection(point3d)
                local_projection = _coerce_projection_object(raw_projection)
                report["binding_projection_raw"] = str(raw_projection)
                report["binding_projection_reference"] = safe_get(local_projection, "Reference")
            except Exception as exc:
                report["binding_projection_error"] = str(exc)
        if local_projection is not None:
            projected_object = local_projection
            report["projection_created_in_binding"] = True
        line_segments, _ = _collection_for_sketch_entity_kind(drawing_container, "segment")
        target_indices = target_indices or {}
        for target in targets:
            item = by_id.get(target)
            entry = {"target": target, "created": False}
            if not item:
                entry["error"] = "created entity item not found"
                report["ok"] = False
                report["targets"].append(entry)
                continue
            index = int(item.get("collection_index", item.get("index", -1)))
            if index < 0:
                entry["error"] = "invalid collection index"
                report["ok"] = False
                report["targets"].append(entry)
                continue
            line = get_collection_item(line_segments, index)
            constraint_report = _apply_constraint_to_line(
                line,
                SKETCH_CONSTRAINT_TYPES["merge_points"],
                index=int(target_indices.get(target, 0)),
                partner=projected_object,
                partner_index=0,
            )
            entry.update(constraint_report)
            if not constraint_report.get("created"):
                report["ok"] = False
            report["targets"].append(entry)
    finally:
        sketch.EndEdit()
    try:
        update = safe_get(sketch, "Update")
        if callable(update):
            report["sketch_update_ok"] = bool(update())
    except Exception as exc:
        report["sketch_update_error"] = str(exc)
        report["ok"] = False
    return report


def _bind_first_sketch_start_to_anchor_point(sketch, sketch_items: list, *, anchor_id: str, targets=("spring_radius_axis", "work_diagonal"), target_indices=None) -> dict:
    report = {"ok": True, "targets": [], "anchor_id": anchor_id}
    by_id = {item.get("id"): item for item in sketch_items if isinstance(item, dict)}
    anchor_item = by_id.get(anchor_id)
    if not anchor_item:
        return {"ok": False, "error": "anchor point item not found", "anchor_id": anchor_id}
    sketch_doc = sketch.BeginEdit()
    if sketch_doc is None:
        raise RuntimeError("BeginEdit returned None for anchor point binding")
    try:
        drawing_container = _get_sketch_drawing_container(sketch_doc)
        line_segments, _ = _collection_for_sketch_entity_kind(drawing_container, "segment")
        points, _ = _collection_for_sketch_entity_kind(drawing_container, "point")
        anchor_index = int(anchor_item.get("collection_index", anchor_item.get("index", -1)))
        if anchor_index < 0:
            return {"ok": False, "error": "invalid anchor point collection index", "anchor_id": anchor_id}
        anchor_point = get_collection_item(points, anchor_index)
        target_indices = target_indices or {}
        for target in targets:
            item = by_id.get(target)
            entry = {"target": target, "created": False}
            if not item:
                entry["error"] = "created entity item not found"
                report["ok"] = False
                report["targets"].append(entry)
                continue
            index = int(item.get("collection_index", item.get("index", -1)))
            if index < 0:
                entry["error"] = "invalid collection index"
                report["ok"] = False
                report["targets"].append(entry)
                continue
            line = get_collection_item(line_segments, index)
            constraint_report = _apply_constraint_to_line(
                line,
                SKETCH_CONSTRAINT_TYPES["merge_points"],
                index=int(target_indices.get(target, 0)),
                partner=anchor_point,
                partner_index=0,
            )
            entry.update(constraint_report)
            if not constraint_report.get("created"):
                report["ok"] = False
            report["targets"].append(entry)
    finally:
        sketch.EndEdit()
    try:
        update = safe_get(sketch, "Update")
        if callable(update):
            report["sketch_update_ok"] = bool(update())
    except Exception as exc:
        report["sketch_update_error"] = str(exc)
        report["ok"] = False
    return report


def _variable_value(params: dict, name: str, default: float) -> float:
    for variable in params.get("variable_plan") or []:
        if not isinstance(variable, dict) or variable.get("name") != name:
            continue
        if variable.get("value") is not None:
            try:
                return float(variable.get("value"))
            except Exception:
                return float(default)
    return float(default)


def _first_sketch_self_wrapping_payload(params: dict) -> dict:
    plan = params.get("self_wrapping_hook_plan") or {}
    hook_radius = float(_variable_value(params, "SFR1", 3.0))
    spring_radius = float(_variable_value(params, "SRAD1", (float(params.get("outer_diameter", 30.0)) - float(params.get("wire_diameter", 3.0))) / 2.0))
    hook_height = float(_variable_value(params, "SH1", 40.0))
    hook_width = float(_variable_value(params, "SW1", 40.0))
    half_width = hook_width / 2.0
    top = [0.0, spring_radius]
    origin = [0.0, 0.0]
    bottom_right = [0.0, -half_width]
    bottom_left = [-hook_height, -half_width]
    top_left = [-hook_height, half_width]
    arc_center = [-hook_height + hook_radius, -13.574361074530819]
    arc_start = [-hook_height, -13.574361074530819]
    arc_end = [-35.07379698404049, -15.874304974131086]
    return {
        "target": {"mode": "create_new_sketch", "name": plan.get("left_first_sketch_name") or "SELF_WRAPPING_LEFT_FIRST_SKETCH", "plane": "XOY"},
        "entities": [
            {"kind": "segment", "id": "spring_radius_axis", "start": origin, "end": top, "role": "construction_spring_endpoint_axis", "line_style": 6},
            {"kind": "segment", "id": "half_width_axis", "start": origin, "end": bottom_right, "role": "construction_half_width_axis", "line_style": 6},
            {"kind": "segment", "id": "height_axis", "start": bottom_right, "end": bottom_left, "role": "construction_hook_height_axis", "line_style": 6},
            {"kind": "segment", "id": "shelf_axis", "start": bottom_left, "end": top_left, "role": "construction_hook_width_shelf", "line_style": 6},
            {"kind": "segment", "id": "diagonal_axis", "start": top, "end": bottom_left, "role": "construction_diagonal_axis", "line_style": 6},
            {"kind": "segment", "id": "work_diagonal", "start": top, "end": arc_end, "role": "working_diagonal", "line_style": 1},
            {"kind": "arc", "id": "work_fillet", "center": arc_center, "radius": hook_radius, "start": arc_end, "end": arc_start, "direction": True, "role": "working_fillet", "line_style": 1},
            {"kind": "segment", "id": "work_shelf", "start": arc_start, "end": top_left, "role": "working_shelf", "line_style": 1},
        ],
        "constraints": [
            {"kind": "fixed_point", "target": "spring_radius_axis", "index": 0},
            {"kind": "merge_points", "target": "spring_radius_axis", "index": 0, "partner": "half_width_axis", "partner_index": 0},
            {"kind": "merge_points", "target": "half_width_axis", "index": 1, "partner": "height_axis", "partner_index": 0},
            {"kind": "merge_points", "target": "height_axis", "index": 1, "partner": "shelf_axis", "partner_index": 0},
            {"kind": "merge_points", "target": "shelf_axis", "index": 0, "partner": "diagonal_axis", "partner_index": 1},
            {"kind": "merge_points", "target": "spring_radius_axis", "index": 1, "partner": "diagonal_axis", "partner_index": 0},
            {"kind": "merge_points", "target": "spring_radius_axis", "index": 1, "partner": "work_diagonal", "partner_index": 0},
            {"kind": "merge_points", "target": "work_diagonal", "index": 1, "partner": "work_fillet", "partner_index": 1},
            {"kind": "merge_points", "target": "work_fillet", "index": 2, "partner": "work_shelf", "partner_index": 0},
            {"kind": "merge_points", "target": "work_shelf", "index": 1, "partner": "shelf_axis", "partner_index": 1},
            {"kind": "vertical", "target": "spring_radius_axis"},
            {"kind": "vertical", "target": "half_width_axis"},
            {"kind": "horizontal", "target": "height_axis"},
            {"kind": "vertical", "target": "shelf_axis"},
            {"kind": "vertical", "target": "work_shelf"},
            {"kind": "point_on_curve", "target": "work_diagonal", "index": 1, "partner": "diagonal_axis"},
            {"kind": "point_on_curve", "target": "work_shelf", "index": 0, "partner": "shelf_axis"},
            {"kind": "point_on_curve", "target": "work_shelf", "index": 1, "partner": "shelf_axis"},
            {"kind": "tangent", "target": "work_diagonal", "partner": "work_fillet"},
            {"kind": "tangent", "target": "work_shelf", "partner": "work_fillet"},
        ],
        "dimensions": [
            {"kind": "line_length", "target": "spring_radius_axis", "value": spring_radius, "expression": "(D1 - WD1) / 2"},
            {"kind": "line_length", "target": "half_width_axis", "value": half_width, "expression": "SHW1"},
            {"kind": "line_length", "target": "height_axis", "value": hook_height, "expression": "SH1"},
            {"kind": "line_length", "target": "shelf_axis", "value": hook_width, "expression": "SW1"},
            {"kind": "arc_radius", "target": "work_fillet", "value": hook_radius, "expression": "SFR1"},
        ],
    }


def _build_self_wrapping_left_hook_replacement(part, model_container, auxiliary_container, params: dict, steps_report: list, document_id=None, document=None) -> list:
    plan = params.get("self_wrapping_hook_plan") or {}
    first_sketch_name = plan.get("left_first_sketch_name") or "SELF_WRAPPING_LEFT_FIRST_SKETCH"
    projected_sketch_name = plan.get("left_projected_sketch_name") or "SELF_WRAPPING_LEFT_FIRST_SKETCH_PROJECTED"
    axis_plane_name = plan.get("left_axis_plane_name") or "SELF_WRAPPING_LEFT_AXIS_PERP_PLANE"
    second_sketch_name = plan.get("left_second_sketch_name") or "SELF_WRAPPING_LEFT_SECOND_SKETCH_PATH"
    sketch1, _, sketch1_items, sketch1_param = _create_sketch_entities(model_container, part, _first_sketch_self_wrapping_payload(params))
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_left_first_sketch", "ok": True, "sketch": safe_get(sketch1, "Name"), "item_count": len(sketch1_items), "parameterization": sketch1_param})
    project_result = handle_project_sketch_edges({"document_id": document_id, "_document": document, "source_sketch_name": first_sketch_name, "target": {"mode": "create_new_sketch", "name": projected_sketch_name, "plane": "XOY"}, "edge_types": [1, 2], "only_straight": True, "projected_line_style": 6, "add_self_wrapping_anchor": True, "post_anchor_constraints": True, "add_self_wrapping_constraints": False, "spring_radius": float(_variable_value(params, "SRAD1", (float(params.get("outer_diameter", 30.0)) - float(params.get("wire_diameter", 3.0))) / 2.0)), "include_snapshot": True, "max_items": 200})
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_left_projected_sketch", "ok": True, "result": _sketch_full_json_safe(project_result)})
    axis_plane_result = handle_create_plane_by_edge_and_plane({"document_id": document_id, "_document": document, "sketch_name": projected_sketch_name, "edge_style": 3, "base_plane": "XOY", "parallel": False, "name": axis_plane_name, "max_items": 300})
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_left_axis_plane", "ok": True, "result": _sketch_full_json_safe(axis_plane_result)})
    sketch2_result = handle_create_self_wrapping_sketch2({"document_id": document_id, "_document": document, "source_sketch_name": projected_sketch_name, "target_sketch_name": second_sketch_name, "target_plane": axis_plane_name, "radius": float(_variable_value(params, "SWR1", 3.01)), "radius_expression": plan.get("second_sketch_radius_expression") or "SWR1", "tail_length": float(_variable_value(params, "HT1", 6.0)), "tail_expression": plan.get("tail_length_expression") or "HT1", "side": "right", "use_anchor_points": False, "max_items": 300})
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_left_second_sketch", "ok": True, "result": _sketch_full_json_safe(sketch2_result)})
    if document_id:
        try:
            document = cast_document_3d(document) if document is not None else resolve_document(make_app(), document_id)
            steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_left_rebuild_before_fillet_creation", "ok": bool(document.RebuildDocument())})
            refreshed_part = safe_get(document, "TopPart")
            model_container = cast_model_container(refreshed_part)
            auxiliary_container = _cast_to_com_interface(refreshed_part, "IAuxiliaryGeomContainer")
        except Exception as exc:
            steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_left_rebuild_before_fillet_creation", "ok": False, "error": str(exc)})
    spirals = safe_get(auxiliary_container, "Spirals3D")
    spiral = get_collection_item(spirals, 0)
    first_sketch = _find_sketch_by_name(model_container, first_sketch_name)
    second_sketch = _find_sketch_by_name(model_container, second_sketch_name)
    first_edges = _get_sketch_edge_tuple(first_sketch, 1)
    second_edges = _get_sketch_edge_tuple(second_sketch, 1)
    if len(first_edges) < 3 or len(second_edges) < 3:
        raise RuntimeError("Self-wrapping sketch edge readback did not produce the expected path edges")
    first_work_start = first_edges[0]
    first_work_middle = first_edges[1]
    first_work_end = first_edges[2]
    second_work_start = second_edges[2]
    second_work_middle = second_edges[1]
    second_work_tail = second_edges[0]
    fillet_radius = float(_variable_value(params, "SFR1", 3.0))
    fillet1 = _create_curve_fillet_path(auxiliary_container, "SELF_WRAPPING_LEFT_FILLET_SPIRAL_TO_FIRST_CONTOUR", spiral, first_work_start, fillet_radius, trim_curve1=True, trim_curve2=True)
    binding1 = _bind_operation_variables(fillet1, [{"parameter_note": "Радиус", "parameter_note_aliases": ["Radius"], "expression": plan.get("fillet_radius_expression") or "SFR1"}])
    if not binding1.get("ok", False) or not bool(fillet1.Update()):
        raise RuntimeError("Failed to bind/update first self-wrapping native curve fillet")
    fillet1_edges = _fillet_result_edges(fillet1)
    fillet2 = _create_curve_fillet_path(auxiliary_container, "SELF_WRAPPING_LEFT_FILLET_FIRST_TO_SECOND_CONTOUR", first_work_end, second_work_start, fillet_radius, trim_curve1=True, trim_curve2=True)
    binding2 = _bind_operation_variables(fillet2, [{"parameter_note": "Радиус", "parameter_note_aliases": ["Radius"], "expression": plan.get("fillet_radius_expression") or "SFR1"}])
    if not binding2.get("ok", False) or not bool(fillet2.Update()):
        raise RuntimeError("Failed to bind/update second self-wrapping native curve fillet")
    fillet2_edges = _fillet_result_edges(fillet2)
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_left_native_fillets", "ok": True, "bindings": [binding1, binding2]})
    projected_sketch = _find_sketch_by_name(model_container, projected_sketch_name)
    axis_plane = _find_named_auxiliary_object(auxiliary_container, "Planes3D", axis_plane_name)
    auxiliary_visibility_objects = [("self_wrapping_first_sketch", first_sketch), ("self_wrapping_projected_sketch", projected_sketch), ("self_wrapping_second_sketch", second_sketch), ("self_wrapping_first_native_fillet", fillet1), ("self_wrapping_second_native_fillet", fillet2)]
    if axis_plane is not None:
        auxiliary_visibility_objects.append(("self_wrapping_axis_plane", axis_plane))
    path_chain = [("self_wrapping_left_fillet1_edge1", "left_self_wrapping_fillet_result", fillet1_edges[1], 1), ("self_wrapping_left_fillet1_edge0", "left_self_wrapping_fillet_result", fillet1_edges[0], 0), ("self_wrapping_left_fillet1_edge2", "left_self_wrapping_fillet_result", fillet1_edges[2], 2), ("self_wrapping_left_first_edge1", "left_self_wrapping_first_sketch", first_work_middle, 1), ("self_wrapping_left_fillet2_edge1", "left_self_wrapping_fillet_result", fillet2_edges[1], 1), ("self_wrapping_left_fillet2_edge0", "left_self_wrapping_fillet_result", fillet2_edges[0], 0), ("self_wrapping_left_fillet2_edge2", "left_self_wrapping_fillet_result", fillet2_edges[2], 2), ("self_wrapping_left_second_edge1", "left_self_wrapping_second_sketch", second_work_middle, 1), ("self_wrapping_left_second_edge2", "left_self_wrapping_second_sketch", second_work_tail, 2)]
    return [{"path_name": path_name, "role": role, "path": path, "path_reference": safe_get(path, "Reference"), "edge_index": edge_index, "side": "left", "self_wrapping": True} for path_name, role, path, edge_index in path_chain], auxiliary_container, auxiliary_visibility_objects


def _build_self_wrapping_right_hook_replacement(part, model_container, auxiliary_container, params: dict, steps_report: list, document_id=None, document=None, body_curve_source=None) -> tuple:
    right_base_plane = _find_named_auxiliary_object(auxiliary_container, "Planes3D", "%s_RIGHT_HOOK_PLANE" % str(params.get("name") or "EXTENSION_SPRING"))
    if right_base_plane is None:
        planes = safe_get(auxiliary_container, "Planes3D")
        for index in range(collection_count(planes)):
            plane = get_collection_item(planes, index)
            if str(safe_get(plane, "Name") or "").endswith("_RIGHT_HOOK_PLANE"):
                right_base_plane = plane
                break
    if right_base_plane is None:
        raise RuntimeError("self_wrapping_hooks right side requires preserved RIGHT_HOOK_PLANE")
    right_base_plane_name = str(safe_get(right_base_plane, "Name"))
    # Point3D objects are owned by the model container; using the auxiliary
    # container here misses the preserved spring endpoint and creates a visible
    # duplicate fallback point.
    right_anchor_point = _find_named_auxiliary_object(model_container, "Points3D", "%s_RIGHT_ANCHOR_POINT" % str(params.get("name") or "EXTENSION_SPRING"))
    if right_anchor_point is None:
        points = safe_get(model_container, "Points3D")
        for index in range(collection_count(points)):
            point = get_collection_item(points, index)
            if str(safe_get(point, "Name") or "").endswith("_RIGHT_ANCHOR_POINT"):
                right_anchor_point = point
                break
    if right_anchor_point is None:
        spirals = safe_get(auxiliary_container, "Spirals3D")
        body_spiral = get_collection_item(spirals, 0) if spirals is not None and collection_count(spirals) > 0 else None
        if body_spiral is not None:
            right_anchor_point = _create_point3d_on_curve(
                model_container,
                "%s_RIGHT_ANCHOR_POINT" % str(params.get("name") or "EXTENSION_SPRING"),
                body_spiral,
                offset=0.0,
                direction=False,
                offset_type=2,
            )
            steps_report.append({"step": "self_wrapping_right_anchor_point_fallback", "ok": True, "source": safe_get(body_spiral, "Name"), "anchor": safe_get(right_anchor_point, "Name")})
        if right_anchor_point is None:
            raise RuntimeError("self_wrapping_hooks right side requires preserved or rebuildable RIGHT_ANCHOR_POINT")
    _set_model_object_hidden(right_anchor_point, True)
    first_sketch_name = "SELF_WRAPPING_RIGHT_FIRST_SKETCH"
    projected_sketch_name = "SELF_WRAPPING_RIGHT_FIRST_SKETCH_PROJECTED"
    axis_plane_name = "SELF_WRAPPING_RIGHT_AXIS_PERP_PLANE"
    second_sketch_name = "SELF_WRAPPING_RIGHT_SECOND_SKETCH_PATH"
    first_sketch_seed, _ = _create_sketch_on_plane(model_container, part, first_sketch_name, right_base_plane, assign_coordinate_system=True, coordinate_system_before_plane=True)
    # Project the preserved spiral endpoint into the right hook plane. This
    # projected 2D anchor drives the local chord/normal math below.
    projection_report, projected_object = _project_point_to_sketch_xy_with_object(first_sketch_seed, right_anchor_point)
    projected_xy = projection_report.get("xy") if projection_report else None
    if projected_object is None:
        raise RuntimeError("Failed to project right spiral endpoint into right self-wrapping Sketch1")
    if not projected_xy:
        raise RuntimeError("Failed to compute right spiral endpoint projection XY in right self-wrapping Sketch1")
    # The right hook payload is mirrored relative to the sketch projection, so
    # the raw projected X is inverted before parameterizing Sketch1.
    right_plane_xy = [-float(projected_xy[0]), float(projected_xy[1])]
    # Reuse the stable left-hook payload as a geometric template; the transform
    # below relocates it onto the projected right endpoint and mirrors X.
    payload_params = dict(params)
    payload_params["self_wrapping_hook_plan"] = {"left_first_sketch_name": first_sketch_name}
    payload = _right_endpoint_self_wrapping_payload(payload_params)
    payload = _transform_self_wrapping_payload_from_endpoint(
        payload,
        right_plane_xy,
        float(_variable_value(params, "SRAD1", (float(params.get("outer_diameter", 30.0)) - float(params.get("wire_diameter", 3.0))) / 2.0)),
        mirror_x=True,
        remove_fixed_origin=True,
    )
    payload["target"] = {"mode": "existing_sketch", "sketch_ref": safe_get(first_sketch_seed, "Reference")}
    sketch1, _, sketch1_items, sketch1_param = _create_sketch_entities(model_container, part, payload)
    endpoint_binding = _bind_first_sketch_start_to_projected_point(
        sketch1,
        sketch1_items,
        right_anchor_point,
        targets=("endpoint_to_bottom_axis", "work_diagonal"),
        target_indices={"endpoint_to_bottom_axis": 0, "work_diagonal": 0},
        projected_xy=right_plane_xy,
        projected_object=projected_object,
        projection_report=projection_report,
    )
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_first_sketch", "ok": True, "sketch": safe_get(sketch1, "Name"), "item_count": len(sketch1_items), "parameterization": sketch1_param, "endpoint_projection": projection_report, "endpoint_projected_xy_raw": projected_xy, "endpoint_projected_xy": right_plane_xy})
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_endpoint_projection_binding", "ok": endpoint_binding.get("ok", False), "result": endpoint_binding})
    if bool(params.get("self_wrapping_right_stop_after_first_sketch")):
        steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_step_stop", "ok": True, "after": "first_sketch"})
        return [], auxiliary_container, []
    # This service sketch keeps a projected work axis in the same plane as
    # Sketch1; that axis is the stable input for the perpendicular Sketch2 plane.
    project_result = handle_project_sketch_edges({"document_id": document_id, "_document": document, "source_sketch_name": first_sketch_name, "target": {"mode": "create_new_sketch", "name": projected_sketch_name, "plane": right_base_plane_name, "coordinate_system": "plane"}, "target_coordinate_system": "plane", "edge_types": [1, 2], "only_straight": True, "projected_line_style": 6, "add_self_wrapping_anchor": True, "post_anchor_constraints": True, "add_self_wrapping_constraints": False, "spring_radius": float(_variable_value(params, "SRAD1", (float(params.get("outer_diameter", 30.0)) - float(params.get("wire_diameter", 3.0))) / 2.0)), "include_snapshot": True, "max_items": 300})
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_projected_sketch", "ok": True, "result": _sketch_full_json_safe(project_result)})
    try:
        projected_sketch_for_axis = _find_sketch_by_name(model_container, projected_sketch_name)
        _, projected_axis_report = _select_sketch_axis_edge_by_style(model_container, projected_sketch_for_axis, 3)
        steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_projected_axis_candidates", "ok": True, "result": _sketch_full_json_safe(projected_axis_report)})
    except Exception as exc:
        steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_projected_axis_candidates", "ok": False, "error": str(exc)})
    if bool(params.get("self_wrapping_right_stop_after_projected_sketch")):
        steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_step_stop", "ok": True, "after": "projected_sketch"})
        return [], auxiliary_container, []
    # Prefer the exact work-axis entity returned by projection; fall back to
    # geometry/style matching when COM returns only serialized entity metadata.
    projected_work_axis_geometry = None
    projected_work_axis_entity = (project_result.get("post_constraint_report") or {}).get("work_axis_entity")
    projected_work_axis_reference = None
    for item in ((project_result.get("anchor_report") or {}).get("added") or []):
        if item.get("id") == "work_axis":
            projected_work_axis_geometry = {"start": item.get("start"), "end": item.get("end")}
            projected_work_axis_reference = item.get("reference")
            break
    if projected_work_axis_entity is None:
        def _xy_same(a, b, tol=1.0e-6):
            return a is not None and b is not None and len(a) >= 2 and len(b) >= 2 and abs(float(a[0]) - float(b[0])) <= tol and abs(float(a[1]) - float(b[1])) <= tol
        def _geom_same(entity_geometry, expected_geometry):
            if not entity_geometry or not expected_geometry:
                return False
            a0 = entity_geometry.get("start")
            a1 = entity_geometry.get("end")
            b0 = expected_geometry.get("start")
            b1 = expected_geometry.get("end")
            return (_xy_same(a0, b0) and _xy_same(a1, b1)) or (_xy_same(a0, b1) and _xy_same(a1, b0))
        style3_entities = [entity for entity in (project_result.get("entities") or []) if entity.get("kind") == "segment" and int((entity.get("raw_properties") or {}).get("Style", -1)) == 3]
        projected_work_axis_entity = next((entity for entity in style3_entities if _geom_same(entity.get("geometry"), projected_work_axis_geometry)), None) or (style3_entities[0] if style3_entities else None)
        if projected_work_axis_entity is None:
            all_segments = [entity for entity in (project_result.get("entities") or []) if entity.get("kind") == "segment"]
            projected_work_axis_entity = next((entity for entity in all_segments if _geom_same(entity.get("geometry"), projected_work_axis_geometry)), None)
    # Sketch2 must be drawn on a plane perpendicular to the projected work axis,
    # otherwise its local coordinates drift when the spiral turn count changes.
    axis_plane_result = handle_create_plane_by_edge_and_plane({"document_id": document_id, "_document": document, "sketch_name": projected_sketch_name, "edge_style": None, "edge_reference": projected_work_axis_reference, "edge_geometry": projected_work_axis_geometry, "edge_collection_name": (projected_work_axis_entity or {}).get("collection_name"), "edge_index": (projected_work_axis_entity or {}).get("index"), "allow_axis_extra_edge_fallback": True, "allow_target_entity_object": True, "base_plane": right_base_plane_name, "parallel": False, "name": axis_plane_name, "max_items": 300})
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_axis_plane", "ok": True, "source": projected_sketch_name, "result": _sketch_full_json_safe(axis_plane_result)})
    sketch2_result = handle_create_self_wrapping_sketch2({"document_id": document_id, "_document": document, "source_sketch_name": projected_sketch_name, "target_sketch_name": second_sketch_name, "target_plane": axis_plane_name, "target_coordinate_system": "plane", "center_endpoint": "start", "radius": float(_variable_value(params, "SWR1", 3.01)), "radius_expression": "SWR1", "tail_length": float(_variable_value(params, "HT1", 6.0)), "tail_expression": "HT1", "side": "right", "use_anchor_points": False, "max_items": 300})
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_second_sketch", "ok": True, "result": _sketch_full_json_safe(sketch2_result)})
    if bool(params.get("self_wrapping_right_stop_after_second_sketch")):
        steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_step_stop", "ok": True, "after": "second_sketch"})
        return [], auxiliary_container, []
    if document_id:
        document = cast_document_3d(document) if document is not None else resolve_document(make_app(), document_id)
        steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_rebuild_before_fillet_creation", "ok": bool(document.RebuildDocument())})
        refreshed_part = safe_get(document, "TopPart")
        model_container = cast_model_container(refreshed_part)
        auxiliary_container = _cast_to_com_interface(refreshed_part, "IAuxiliaryGeomContainer")
    spirals = safe_get(auxiliary_container, "Spirals3D")
    spiral = get_collection_item(spirals, 0)
    first_sketch = _find_sketch_by_name(model_container, first_sketch_name)
    second_sketch = _find_sketch_by_name(model_container, second_sketch_name)
    first_edges = _get_sketch_edge_tuple(first_sketch, 1)
    second_edges = _get_sketch_edge_tuple(second_sketch, 1)
    if len(first_edges) < 3 or len(second_edges) < 3:
        raise RuntimeError("Right self-wrapping sketch edge readback did not produce expected edges")
    fillet_radius = float(_variable_value(params, "SFR1", 3.0))
    body_curve_for_fillet = body_curve_source or spiral
    try:
        fresh_left_fillet = _find_fillet_curve_by_name(auxiliary_container, "SELF_WRAPPING_LEFT_FILLET_SPIRAL_TO_FIRST_CONTOUR")
        fresh_left_edges = _fillet_result_edges(fresh_left_fillet)
        if len(fresh_left_edges) > 1:
            body_curve_for_fillet = fresh_left_edges[1]
    except Exception:
        pass
    right_transition_curve = first_edges[0]
    logical_body_end = None
    for segment in list(params.get("segment_plan") or []):
        if str(segment.get("role") or "") == "body":
            logical_body_end = list(segment.get("end_point") or segment.get("logical_end_point") or []) or None
            break
    body_curve_endpoints = _sample_curve_endpoints(body_curve_for_fillet)
    curve1_cut_point, curve2_cut_point = _fillet_cut_points_near_shared_endpoint(body_curve_for_fillet, right_transition_curve, curve1_ratio=0.0, curve2_ratio=0.03)
    if logical_body_end:
        if curve1_cut_point is None:
            curve1_cut_point = logical_body_end
        if curve2_cut_point is None:
            curve2_cut_point = _curve_cut_point_near_point(right_transition_curve, logical_body_end, ratio=0.03)
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_transition_fillet_inputs", "ok": True, "body_curve_endpoints": body_curve_endpoints, "logical_body_end": logical_body_end, "transition_curve_endpoints": _sample_curve_endpoints(right_transition_curve), "curve1_cut_point": curve1_cut_point, "curve2_cut_point": curve2_cut_point})
    fillet1, fillet1_staged_updates = _create_staged_curve_fillet_path(auxiliary_container, "SELF_WRAPPING_RIGHT_FILLET_SPIRAL_TO_FIRST_CONTOUR", body_curve_for_fillet, right_transition_curve, fillet_radius, trim_curve1=True, trim_curve2=True, curve1_cut_point=curve1_cut_point, curve2_cut_point=curve2_cut_point)
    binding1 = _bind_operation_variables(fillet1, [{"parameter_note": "Радиус", "parameter_note_aliases": ["Radius"], "expression": "SFR1"}])
    if not binding1.get("ok", False) or not bool(fillet1.Update()):
        raise RuntimeError("Failed to bind/update first right self-wrapping native curve fillet")
    f1_edges = _fillet_result_edges(fillet1)
    if len(f1_edges) < 3:
        raise RuntimeError("First right self-wrapping fillet did not expose expected result edges")
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_first_to_second_fillet_inputs", "ok": True, "first_edges": [{"index": index, "endpoints": _sample_curve_endpoints(edge)} for index, edge in enumerate(first_edges)], "second_edges": [{"index": index, "endpoints": _sample_curve_endpoints(edge)} for index, edge in enumerate(second_edges)], "f1_edges": [{"index": index, "endpoints": _sample_curve_endpoints(edge)} for index, edge in enumerate(f1_edges)]})
    fillet2_curve1_cut_point, fillet2_curve2_cut_point = _fillet_cut_points_near_shared_endpoint(first_edges[2], second_edges[2], curve1_ratio=0.10, curve2_ratio=0.03)
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_first_to_second_fillet_cut_points", "ok": True, "curve1_cut_point": fillet2_curve1_cut_point, "curve2_cut_point": fillet2_curve2_cut_point})
    fillet2, fillet2_staged_updates = _create_staged_curve_fillet_path(auxiliary_container, "SELF_WRAPPING_RIGHT_FILLET_FIRST_TO_SECOND_CONTOUR", first_edges[2], second_edges[2], fillet_radius, trim_curve1=True, trim_curve2=True, curve1_cut_point=fillet2_curve1_cut_point, curve2_cut_point=fillet2_curve2_cut_point)
    binding2 = _bind_operation_variables(fillet2, [{"parameter_note": "Радиус", "parameter_note_aliases": ["Radius"], "expression": "SFR1"}])
    if not binding2.get("ok", False) or not bool(fillet2.Update()):
        raise RuntimeError("Failed to bind/update second right self-wrapping native curve fillet")
    f2_edges = _fillet_result_edges(fillet2)
    if len(f2_edges) < 3:
        raise RuntimeError("Second right self-wrapping fillet did not expose expected result edges")
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_second_native_fillet", "ok": True, "edge1": _sample_curve_endpoints(f2_edges[1]), "edge0": _sample_curve_endpoints(f2_edges[0]), "edge2": _sample_curve_endpoints(f2_edges[2])})
    pre_rebuild_first_edges = first_edges
    pre_rebuild_second_edges = second_edges
    pre_rebuild_fillet1 = fillet1
    pre_rebuild_fillet2 = fillet2
    pre_rebuild_f1_edges = f1_edges
    pre_rebuild_f2_edges = f2_edges
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_native_fillets", "ok": True, "bindings": [binding1, binding2], "staged_updates": {"fillet1": fillet1_staged_updates, "fillet2": fillet2_staged_updates}})
    if document_id:
        steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_rebuild_before_path_capture", "ok": True, "skipped": True})
    steps_report.append({"scenario": "extension_spring", "target": "self_wrapping_right_path_capture_refetch", "ok": True, "skipped": True, "reason": "native_fillet_edges_are_current"})
    # Native fillet edges are already current here; keep the pre-rebuild COM
    # wrappers instead of refetching and risking a different edge ordering.
    first_edges = pre_rebuild_first_edges
    second_edges = pre_rebuild_second_edges
    fillet1 = pre_rebuild_fillet1
    fillet2 = pre_rebuild_fillet2
    f1_edges = pre_rebuild_f1_edges
    f2_edges = pre_rebuild_f2_edges
    try:
        projected_sketch = _find_sketch_by_name(model_container, projected_sketch_name)
    except Exception:
        projected_sketch = None
    axis_plane = _find_named_auxiliary_object(auxiliary_container, "Planes3D", axis_plane_name)
    auxiliary_visibility_objects = [("self_wrapping_right_anchor_point", right_anchor_point), ("self_wrapping_right_first_sketch", first_sketch), ("self_wrapping_right_projected_sketch", projected_sketch), ("self_wrapping_right_second_sketch", second_sketch), ("self_wrapping_right_first_native_fillet", fillet1), ("self_wrapping_right_second_native_fillet", fillet2)]
    if axis_plane is not None:
        auxiliary_visibility_objects.append(("self_wrapping_right_axis_plane", axis_plane))
    # The path order is the contour contract consumed by the evolution feature;
    # edge names are intentionally explicit so report diffs expose regressions.
    path_chain = [("self_wrapping_right_fillet1_edge1", "right_self_wrapping_fillet_result", f1_edges[1], 1), ("self_wrapping_right_fillet1_edge0", "right_self_wrapping_fillet_result", f1_edges[0], 0), ("self_wrapping_right_fillet1_edge2", "right_self_wrapping_fillet_result", f1_edges[2], 2), ("self_wrapping_right_first_edge1", "right_self_wrapping_first_sketch", first_edges[1], 1), ("self_wrapping_right_fillet2_edge1", "right_self_wrapping_fillet_result", f2_edges[1], 1), ("self_wrapping_right_fillet2_edge0", "right_self_wrapping_fillet_result", f2_edges[0], 0), ("self_wrapping_right_fillet2_edge2", "right_self_wrapping_fillet_result", f2_edges[2], 2), ("self_wrapping_right_second_edge1", "right_self_wrapping_second_sketch", second_edges[1], 1), ("self_wrapping_right_second_edge0", "right_self_wrapping_second_sketch", second_edges[0], 0)]
    return [{"path_name": path_name, "role": role, "path": path, "path_reference": safe_get(path, "Reference"), "edge_index": edge_index, "side": "right", "self_wrapping": True} for path_name, role, path, edge_index in path_chain], auxiliary_container, auxiliary_visibility_objects


def _resolve_named_curve_sequence(path_names, segment_objects, connector_objects):
    curve_by_name = {}
    for item in segment_objects:
        path_name = str(item.get("path_name") or "").strip()
        if path_name:
            curve_by_name[path_name] = item["path"]
    for item in connector_objects:
        path_name = str(item.get("path_name") or "").strip()
        if path_name:
            curve_by_name[path_name] = item["path"]
    ordered_curves = []
    for path_name in path_names or []:
        curve = curve_by_name.get(str(path_name or "").strip())
        if curve is None:
            raise RuntimeError("Compression spring contour path is missing curve object %s" % path_name)
        ordered_curves.append(curve)
    return ordered_curves


def _collect_compression_spring_connector_auxiliary_objects(connector_objects):
    auxiliary_objects = []
    for item in connector_objects or []:
        role = "spring_%s" % str(item.get("kind") or "transition_curve_path")
        path = item.get("path")
        if path is not None:
            auxiliary_objects.append((role, path))
        point = item.get("point")
        if point is not None:
            auxiliary_objects.append(("%s_point" % role, point))
    return auxiliary_objects


def _build_compression_spring_path_contour_with_connectors(
    part,
    model_container,
    auxiliary_container,
    spring_name,
    params,
    segment_objects,
    auxiliary_objects,
    steps_report,
):
    connector_plan = list(params.get("connector_plan") or [])
    connector_objects = []
    sweep_paths_for_report = [item["path"] for item in segment_objects]
    full_path_sequence = list(params.get("full_path_sequence") or [])
    if connector_plan or full_path_sequence:
        connector_objects = _build_compression_spring_transition_curve_paths(
            part,
            model_container,
            auxiliary_container,
            spring_name,
            segment_objects,
            connector_plan,
            steps_report,
        ) if connector_plan else []
        auxiliary_objects.extend(
            _collect_compression_spring_connector_auxiliary_objects(connector_objects)
        )
        contour_paths = _resolve_named_curve_sequence(
            full_path_sequence,
            segment_objects,
            connector_objects,
        )
        sweep_paths_for_report = list(contour_paths)
        path_contour, contour_report = _build_curve_contour(
            auxiliary_container,
            "%s_PATH_CONTOUR" % spring_name,
            contour_paths,
            allow_incomplete=True,
            expected_edges_count=len(contour_paths),
        )
    else:
        path_contour, contour_report = _resolve_spring_path_contour(
            auxiliary_container,
            spring_name,
            segment_objects,
        )
    auxiliary_objects.append(("spring_path_contour", path_contour))
    steps_report.append(
        {
            "step": "build_spring_path_contour",
            "ok": True,
            "scenario": "compression_spring",
            "reference": safe_get(path_contour, "Reference"),
            "model_object_type": safe_get(path_contour, "ModelObjectType"),
            "source_path_count": contour_report["source_path_count"],
            "edges_count": contour_report["edges_count"],
            "expected_edges_count": contour_report.get("expected_edges_count"),
            "source_path_references": contour_report.get("source_path_references"),
            "contour_edge_references": contour_report.get("contour_edge_references"),
            "connector_count": len(connector_plan),
            "candidate_orientation_angles": contour_report.get("candidate_orientation_angles"),
            "combo_index": contour_report.get("combo_index"),
            "selected_orientation_angles": [
                {
                    "role": item["role"],
                    "orientation_angle_degrees": float(item.get("applied_orientation_angle") or 0.0),
                }
                for item in segment_objects
            ],
        }
    )
    return connector_plan, connector_objects, path_contour, contour_report, sweep_paths_for_report


def _resolve_spring_path_contour(auxiliary_container, spring_name, segment_objects):
    if not segment_objects:
        raise RuntimeError("Compression spring path requires at least one spiral segment")
    contour_name = "%s_PATH_CONTOUR" % spring_name
    contour, direct_report = _build_curve_contour(
        auxiliary_container,
        contour_name,
        [item["path"] for item in segment_objects],
        allow_incomplete=True,
    )
    if int(direct_report["edges_count"]) == len(segment_objects):
        direct_report["candidate_orientation_angles"] = [
            float(item.get("applied_orientation_angle") or 0.0)
            for item in segment_objects
        ]
        direct_report["combo_index"] = -1
        return contour, direct_report
    candidate_lists = []
    for index, segment_object in enumerate(segment_objects):
        candidates = []
        applied_orientation_angle = float(segment_object.get("applied_orientation_angle") or 0.0)
        for candidate in [applied_orientation_angle] + list(segment_object.get("orientation_angle_candidates") or []):
            candidate_value = float(candidate)
            if any(abs(existing - candidate_value) <= 1e-9 for existing in candidates):
                continue
            candidates.append(candidate_value)
        if index == 0 and candidates:
            candidates = [applied_orientation_angle]
        candidate_lists.append(candidates or [applied_orientation_angle])

    best_report = dict(direct_report)
    best_report["candidate_orientation_angles"] = [
        float(item.get("applied_orientation_angle") or 0.0)
        for item in segment_objects
    ]
    best_report["combo_index"] = -1
    for combo_index, candidate_combo in enumerate(itertools.product(*candidate_lists)):
        for segment_object, candidate in zip(segment_objects, candidate_combo):
            current_angle = float(segment_object.get("applied_orientation_angle") or 0.0)
            if abs(current_angle - float(candidate)) <= 1e-9:
                continue
            _apply_spiral_turning_angle(
                segment_object["path"],
                segment_object["position_parameters"],
                candidate,
                segment_object.get("angle_application_mode"),
            )
            if not bool(segment_object["path"].Update()):
                raise RuntimeError(
                    "Failed to update compression spring spiral path for %s"
                    % segment_object.get("role", "segment")
                )
            segment_object["applied_orientation_angle"] = float(candidate)
        contour, contour_report = _build_curve_contour(
            auxiliary_container,
            contour_name,
            [item["path"] for item in segment_objects],
            allow_incomplete=True,
            contour=contour,
        )
        contour_report["candidate_orientation_angles"] = [float(value) for value in candidate_combo]
        contour_report["combo_index"] = int(combo_index)
        if best_report is None or int(contour_report["edges_count"]) > int(best_report["edges_count"]):
            best_report = contour_report
        if int(contour_report["edges_count"]) == len(segment_objects):
            return contour, contour_report
    _delete_curve_contour(auxiliary_container, contour)
    raise RuntimeError(
        "Spring path contour completeness check failed: expected %s edges, got %s"
        % (len(segment_objects), best_report["edges_count"] if best_report is not None else 0)
    )


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


def handle_delete_sketch_entity(payload):
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
    sketch, target, before_item, deletion = _delete_existing_sketch_entity(model_container, payload)
    updater = safe_get(top_part, "Update")
    part_update_ok = True
    if callable(updater):
        part_update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)

    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "item": deletion,
        "before_item": before_item,
        "summary": {
            "kind": deletion.get("kind"),
            "collection": deletion.get("collection"),
            "collection_index": deletion.get("collection_index"),
            "deleted": deletion.get("deleted"),
            "deleted_count": deletion.get("deleted_count"),
            "before_count": deletion.get("before_count"),
            "after_count": deletion.get("after_count"),
            "part_update_ok": part_update_ok,
        },
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_update_sketch_entity_geometry(payload):
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
    sketch, target, before_item, after_item = _update_existing_sketch_entity_geometry(model_container, payload)
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
            "old_geometry": before_item.get("geometry"),
            "geometry": after_item.get("geometry"),
            "part_update_ok": part_update_ok,
        },
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_list_sketch_dimensions(payload):
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

    sketch, target, items, summary = _list_existing_sketch_dimensions(model_container, payload)
    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "items": items,
        "item": {
            "name": safe_get(sketch, "Name", target.get("name")),
            "type": "SketchDimensionList",
            "reference": safe_get(sketch, "Reference"),
        },
        "summary": summary,
    }


def handle_inspect_sketch_dimension(payload):
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

    sketch, target, item = _inspect_existing_sketch_dimension(model_container, payload)
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


def handle_list_sketch_constraints(payload):
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

    sketch, target, items, summary = _list_existing_sketch_constraints(model_container, payload)
    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "items": items,
        "item": {
            "name": safe_get(sketch, "Name", target.get("name")),
            "type": "SketchConstraintList",
            "reference": safe_get(sketch, "Reference"),
        },
        "summary": summary,
    }


def handle_inspect_sketch_constraint(payload):
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

    sketch, target, item = _inspect_existing_sketch_constraint(model_container, payload)
    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "item": item,
        "summary": {
            "found": True,
            "kind": item.get("kind"),
            "reference": item.get("reference"),
            "collection_index": item.get("collection_index"),
        },
    }


def handle_clear_sketch_entity_constraints(payload):
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
    sketch, target, before_item, after_item, summary = _clear_existing_sketch_entity_constraints(model_container, payload)
    updater = safe_get(top_part, "Update")
    part_update_ok = True
    if callable(updater):
        part_update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)
    summary = dict(summary)
    summary["part_update_ok"] = part_update_ok

    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "item": after_item,
        "before_item": before_item,
        "summary": summary,
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_repair_sketch(payload):
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
    sketch, target, items, summary = _repair_existing_sketch(model_container, payload)
    part_update_ok = None
    if bool(payload.get("apply")):
        updater = safe_get(top_part, "Update")
        part_update_ok = True
        if callable(updater):
            part_update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)
    summary = dict(summary)
    summary["part_update_ok"] = part_update_ok

    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": target,
        "items": items,
        "item": {
            "name": safe_get(sketch, "Name", target.get("name")),
            "type": "SketchRepair",
            "reference": safe_get(sketch, "Reference"),
            "operation_count": len(items),
            "applied": bool(payload.get("apply")),
        },
        "summary": summary,
        "readback": {
            "before": _snapshot_from_tree(document, app, before_tree),
            "after": _snapshot_from_tree(document, app, after_tree),
        },
    }


def handle_list_features(payload):
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

    items, summary = _list_existing_features(model_container, payload)
    return {
        "ok": True,
        "document": describe_document(document, app),
        "items": items,
        "item": {
            "type": "FeatureList",
            "feature_count": len(items),
        },
        "summary": summary,
    }


def handle_inspect_feature(payload):
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

    item = _inspect_existing_feature(model_container, payload)
    return {
        "ok": True,
        "document": describe_document(document, app),
        "item": item,
        "summary": {
            "found": True,
            "kind": item.get("kind"),
            "collection": item.get("collection"),
            "collection_index": item.get("collection_index"),
            "variable_count": item.get("variable_count", 0),
        },
    }


def handle_repair_feature(payload):
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
    items, summary = _repair_existing_features(model_container, payload)
    part_update_ok = None
    if bool(payload.get("apply")):
        updater = safe_get(top_part, "Update")
        part_update_ok = True
        if callable(updater):
            part_update_ok = bool(updater())
    after_tree = serialize_part(top_part, "root", None)
    summary = dict(summary)
    summary["part_update_ok"] = part_update_ok

    return {
        "ok": True,
        "document": describe_document(document, app),
        "items": items,
        "item": {
            "type": "FeatureRepair",
            "operation_count": len(items),
            "applied": bool(payload.get("apply")),
        },
        "summary": summary,
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


def handle_inspect_sketch_full(payload):
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

    result = _inspect_sketch_full(model_container, payload)
    result["ok"] = True
    result["document"] = describe_document(document, app)
    return result


def handle_project_sketch_edges(payload):
    app = make_app()
    document_id = payload.get("document_id")
    doc = cast_document_3d(payload.get("_document")) if payload.get("_document") is not None else resolve_document(app, document_id)
    if doc is None:
        raise RuntimeError("No active document")
    part = safe_get(doc, "TopPart")
    model_container = cast_model_container(part)
    if model_container is None:
        raise RuntimeError("Active document does not expose TopPart model container")

    source_ref = payload.get("source_sketch_ref") or payload.get("source_sketch")
    source_name = payload.get("source_sketch_name")
    if source_ref is not None:
        source_sketch = _resolve_existing_sketch(model_container, source_ref)
    elif source_name:
        source_sketch = None
        sketches = _get_sketch_collection(model_container)
        for index in range(collection_count(sketches)):
            candidate = _cast_to_com_interface(get_collection_item(sketches, index), "ISketch")
            if safe_get(candidate, "Name") == source_name:
                source_sketch = candidate
                break
        if source_sketch is None:
            raise RuntimeError("source sketch not found: %s" % source_name)
    else:
        raise RuntimeError("source_sketch_ref or source_sketch_name is required")

    target = payload.get("target") or {}
    target_mode = str(target.get("mode") or "create_new_sketch")
    if target_mode == "existing_sketch":
        target_sketch = _resolve_existing_sketch(model_container, target.get("sketch_ref"))
    else:
        target_plane_value = target.get("plane") or payload.get("plane") or "XOY"
        target_coordinate_system_mode = str(target.get("coordinate_system") or payload.get("target_coordinate_system") or "").lower()
        target_plane_object = None
        if target_coordinate_system_mode == "plane":
            try:
                target_plane_key = _normalize_sketch_plane(target_plane_value)
                target_plane_object = _resolve_default_part_object(part, target_plane_key)
            except Exception:
                auxiliary = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
                target_plane_object = _find_named_auxiliary_object(auxiliary, "Planes3D", str(target_plane_value))
        target_sketch, _ = _create_sketch_on_plane(
            model_container,
            part,
            target.get("name") or payload.get("target_sketch_name") or "PROJECTED_SKETCH",
            target_plane_object if target_plane_object is not None else target_plane_value,
            assign_coordinate_system=target_coordinate_system_mode == "plane",
            coordinate_system_before_plane=target_coordinate_system_mode == "plane",
        )

    edge_types = payload.get("edge_types") if "edge_types" in payload else [1, 2]
    only_straight = bool(payload.get("only_straight", False))
    projected = []
    projected_live_segments = []
    seen_edges = set()
    target_edit_doc = target_sketch.BeginEdit()
    for edge_type in edge_types:
        try:
            edge_value = source_sketch.Edges(edge_type)
        except Exception as exc:
            projected.append({"edge_type": edge_type, "error": str(exc)})
            continue
        if isinstance(edge_value, (list, tuple)):
            edges = list(edge_value)
        else:
            count = collection_count(edge_value)
            if count:
                edges = [get_collection_item(edge_value, index) for index in range(count)]
            elif edge_value is not None:
                edges = [edge_value]
            else:
                edges = []
        for index, edge in enumerate(edges):
            edge_reference = safe_get(edge, "Reference")
            edge_key = edge_reference or (edge_type, index)
            if edge_key in seen_edges:
                projected.append({"edge_type": edge_type, "index": index, "skipped": "duplicate_edge", "reference": edge_reference})
                continue
            seen_edges.add(edge_key)
            if only_straight and safe_get(edge, "IsStraight") is False:
                projected.append({"edge_type": edge_type, "index": index, "skipped": "non_straight_edge", "reference": edge_reference})
                continue
            item = {"edge_type": edge_type, "index": index}
            try:
                item["source"] = _read_sketch_full_object_details(
                    edge,
                    ("Name", "Reference", "Type", "Curve3DType", "IsStraight"),
                    related_names=("Owner", "Parent"),
                )
                projection_result = target_sketch.AddProjectionOf(edge)
                item["result"] = _sketch_full_json_safe(projection_result)
                if isinstance(projection_result, (list, tuple)):
                    result_items = list(projection_result)
                elif collection_count(projection_result):
                    result_items = iter_collection(projection_result)
                else:
                    result_items = [projection_result]
                item["result_items_count"] = len(result_items)
                item["result_item_types"] = [type(result_item).__name__ for result_item in result_items]
                item["result_item_errors"] = []
                for result_item in result_items:
                    try:
                        segment_info = {
                            "index": len(projected_live_segments),
                            "kind": "segment",
                            "collection": "projected_live_segments",
                            "reference": safe_get(result_item, "Reference"),
                            "style": safe_get(result_item, "Style"),
                            "geometry": _sketch_entity_geometry("segment", result_item),
                        }
                        segment_info["object"] = result_item
                        segment_info["source_edge_reference"] = edge_reference
                        projected_live_segments.append(segment_info)
                    except Exception as exc:
                        item["result_item_errors"].append(str(exc))
            except Exception as exc:
                item["error"] = str(exc)
            projected.append(item)

    anchor_report = None
    projected_line_style = payload.get("projected_line_style")
    add_anchor = bool(payload.get("add_self_wrapping_anchor", False))
    add_constraints = bool(payload.get("add_self_wrapping_constraints", add_anchor))
    if (projected_line_style is not None or add_anchor) and target_edit_doc is not None and not (add_anchor and projected_live_segments):
        try:
            target_sketch.EndEdit()
            target_sketch.Update()
        except Exception as exc:
            projected.append({"stage": "projection_end_edit_before_anchor", "error": str(exc)})
        target_edit_doc = target_sketch.BeginEdit()
    if projected_line_style is not None or add_anchor:
        anchor_report = {"projected_style": projected_line_style, "added": [], "constraints": None, "errors": [], "existing_segments": []}
        try:
            drawing = _get_sketch_drawing_container(target_edit_doc)
            existing_segments = []
            if projected_live_segments:
                for info in projected_live_segments:
                    existing_segments.append(info)
                    anchor_report["existing_segments"].append(_sketch_full_json_safe({k: v for k, v in info.items() if k != "object"}))
                    if projected_line_style is not None:
                        try:
                            info["object"].Style = int(projected_line_style)
                        except Exception as exc:
                            anchor_report["errors"].append({"stage": "set_projected_style", "index": info.get("index"), "error": str(exc)})
            else:
                line_segments = _resolve_model_object_collection(drawing, ("LineSegments", "GetLineSegments"))
                for index in range(collection_count(line_segments)):
                    segment = get_collection_item(line_segments, index)
                    info = {
                        "index": index,
                        "kind": "segment",
                        "collection": "segments",
                        "reference": safe_get(segment, "Reference"),
                        "style": safe_get(segment, "Style"),
                        "geometry": _sketch_entity_geometry("segment", segment),
                        "object": segment,
                    }
                    existing_segments.append(info)
                    anchor_report["existing_segments"].append(_sketch_full_json_safe({k: v for k, v in info.items() if k != "object"}))
                    if projected_line_style is not None:
                        try:
                            segment.Style = int(projected_line_style)
                        except Exception as exc:
                            anchor_report["errors"].append({"stage": "set_projected_style", "index": index, "error": str(exc)})

            if add_anchor:
                def point_tuple(point):
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        return float(point[0]), float(point[1])
                    return float(point["x"]), float(point["y"])

                def segment_points(segment_info):
                    geometry = segment_info.get("geometry") or {}
                    return point_tuple(geometry["start"]), point_tuple(geometry["end"])

                def line_intersection(a1, a2, b1, b2):
                    x1, y1 = a1
                    x2, y2 = a2
                    x3, y3 = b1
                    x4, y4 = b2
                    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
                    if abs(denominator) <= 1e-12:
                        return None
                    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denominator
                    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denominator
                    return [float(px), float(py)]

                spring_radius = float(payload.get("spring_radius", 13.5))
                non_vertical = []
                vertical = []
                for segment_info in existing_segments:
                    p1, p2 = segment_points(segment_info)
                    if abs(p1[0] - p2[0]) <= 1e-6:
                        vertical.append(segment_info)
                    else:
                        non_vertical.append(segment_info)
                projected_diagonal = max(non_vertical, key=lambda item: abs(segment_points(item)[0][0] - segment_points(item)[1][0])) if non_vertical else None
                projected_shelf = max(vertical, key=lambda item: abs(segment_points(item)[0][1] - segment_points(item)[1][1])) if vertical else None
                if projected_diagonal is None or projected_shelf is None:
                    anchor_report["errors"].append({"stage": "add_anchor", "error": "projected_diagonal_or_shelf_not_found"})
                else:
                    diag_a, diag_b = segment_points(projected_diagonal)
                    spring_point = diag_a if abs(diag_a[0]) <= abs(diag_b[0]) else diag_b
                    diag_far = diag_b if spring_point == diag_a else diag_a
                    shelf_a, shelf_b = segment_points(projected_shelf)
                    shelf_free = shelf_a if shelf_a[1] >= shelf_b[1] else shelf_b
                    mirror_start = [0.0, -spring_radius]
                    mirror_end = [float(shelf_free[0]), float(shelf_free[1])]
                    vertical_base = _add_sketch_line_segment(drawing, [0.0, spring_radius], [0.0, -spring_radius], 6)
                    mirror_diagonal = _add_sketch_line_segment(drawing, mirror_start, mirror_end, 6)
                    axis_start = line_intersection(spring_point, diag_far, mirror_start, mirror_end)
                    if axis_start is None:
                        axis_start = [float((spring_point[0] + diag_far[0]) * 0.5), 0.0]
                    work_axis = _add_sketch_line_segment(drawing, axis_start, [float(shelf_free[0]), float(shelf_free[1])], 3)
                    shelf_point = _add_sketch_point(drawing, [float(shelf_free[0]), float(shelf_free[1])], 127)

                    sketch_entities = {
                        "projected_diagonal": dict(projected_diagonal, role="line"),
                        "projected_shelf": dict(projected_shelf, role="line"),
                        "vertical_base": {"object": vertical_base, "role": "line", "x1": 0.0, "y1": spring_radius, "x2": 0.0, "y2": -spring_radius},
                        "mirror_diagonal": {"object": mirror_diagonal, "role": "line", "x1": mirror_start[0], "y1": mirror_start[1], "x2": mirror_end[0], "y2": mirror_end[1]},
                        "work_axis": {"object": work_axis, "role": "line", "x1": axis_start[0], "y1": axis_start[1], "x2": float(shelf_free[0]), "y2": float(shelf_free[1])},
                        "shelf_point": {"object": shelf_point, "role": "point", "x": float(shelf_free[0]), "y": float(shelf_free[1])},
                    }
                    constraints = [
                        {"kind": "merge_points", "target": "vertical_base", "index": 0, "partner": "projected_diagonal", "partner_index": 0 if spring_point == diag_a else 1},
                        {"kind": "merge_points", "target": "vertical_base", "index": 1, "partner": "mirror_diagonal", "partner_index": 0},
                        {"kind": "point_on_curve", "target": "work_axis", "index": 0, "partner": "projected_diagonal"},
                        {"kind": "point_on_curve", "target": "work_axis", "index": 0, "partner": "mirror_diagonal"},
                        {"kind": "merge_points", "target": "mirror_diagonal", "index": 1, "partner": "projected_shelf", "partner_index": 0 if shelf_free == shelf_a else 1},
                        {"kind": "merge_points", "target": "work_axis", "index": 1, "partner": "projected_shelf", "partner_index": 0 if shelf_free == shelf_a else 1},
                        {"kind": "merge_points", "target": "shelf_point", "index": 0, "partner": "work_axis", "partner_index": 1},
                        {"kind": "merge_points", "target": "shelf_point", "index": 0, "partner": "projected_shelf", "partner_index": 0 if shelf_free == shelf_a else 1},
                        {"kind": "vertical", "target": "vertical_base"},
                    ]
                    anchor_report["added"] = [
                        {"id": "vertical_base", "start": [0.0, spring_radius], "end": [0.0, -spring_radius], "style": 6, "reference": safe_get(vertical_base, "Reference")},
                        {"id": "mirror_diagonal", "start": mirror_start, "end": mirror_end, "style": 6, "reference": safe_get(mirror_diagonal, "Reference")},
                        {"id": "work_axis", "start": axis_start, "end": [float(shelf_free[0]), float(shelf_free[1])], "style": 3, "reference": safe_get(work_axis, "Reference")},
                        {"id": "shelf_point", "point": [float(shelf_free[0]), float(shelf_free[1])], "style": 127, "reference": safe_get(shelf_point, "Reference")},
                    ]
                    anchor_report["constraints"] = _apply_sketch_constraints(sketch_entities, constraints, {"enabled": True})
                    anchor_report["dimensions"] = _apply_sketch_dimensions(
                        drawing,
                        sketch_entities,
                        [
                            {
                                "kind": "line_length",
                                "target": "vertical_base",
                                "value": spring_radius * 2.0,
                                "expression": "D1 - WD1",
                                "orientation": "vertical",
                            }
                        ],
                        {"enabled": True, "driving": True},
                    )
                    for added in anchor_report.get("added") or []:
                        entity = sketch_entities.get(added.get("id"))
                        if not entity:
                            continue
                        obj = entity.get("object")
                        added["reference"] = safe_get(obj, "Reference")
                        if entity.get("role") == "line":
                            try:
                                geometry = _sketch_entity_geometry("segment", obj)
                                added["start"] = geometry.get("start")
                                added["end"] = geometry.get("end")
                            except Exception as exc:
                                added["geometry_error"] = str(exc)
                        elif entity.get("role") == "point":
                            try:
                                geometry = _sketch_entity_geometry("point", obj)
                                added["point"] = geometry.get("point")
                            except Exception as exc:
                                added["geometry_error"] = str(exc)
        except Exception as exc:
            anchor_report["errors"].append({"stage": "anchor_outer", "error": str(exc)})
    if target_edit_doc is not None:
        try:
            target_sketch.EndEdit()
        except Exception as exc:
            projected.append({"stage": "target_end_edit", "error": str(exc)})

    target_update_ok = bool(target_sketch.Update())
    try:
        part_update_ok = bool(part.Update())
    except Exception as exc:
        part_update_ok = False
        projected.append({"stage": "part_update", "error": str(exc)})

    snapshot = None
    if payload.get("include_snapshot", True):
        snapshot = _inspect_sketch_full(
            model_container,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": safe_get(target_sketch, "Reference")},
                "include_dimensions": True,
                "include_constraints": True,
                "include_diagnostics": True,
                "max_items": payload.get("max_items") or 200,
            },
        )

    spring_radius = float(payload.get("spring_radius", 13.5))
    projected_segments = [item for item in (snapshot or {}).get("entities", []) if item.get("kind") == "segment"]
    post_anchor_report = None
    if snapshot and (projected_line_style is not None or (add_anchor and (not anchor_report or not anchor_report.get("added")))):
        post_anchor_report = {"style_refs": [], "added": [], "errors": []}
        projected_segments = [item for item in snapshot.get("entities", []) if item.get("kind") == "segment"]
        if projected_line_style is not None:
            try:
                target_sketch.BeginEdit()
                api5_doc2d, _api5_doc2d_status = _get_api5_document2d()
                api5_app, _api5_module, _api5_status = _get_api5_kompas_object()
                for item in projected_segments:
                    reference = item.get("reference")
                    if reference in (None, ""):
                        continue
                    param = api5_app.GetParamStruct(11)
                    ok = api5_doc2d.ksGetObjParam(reference, param, 11)
                    if ok:
                        param.style = int(projected_line_style)
                        post_anchor_report["style_refs"].append({"reference": reference, "set": api5_doc2d.ksSetObjParam(reference, param, 11)})
                    else:
                        post_anchor_report["style_refs"].append({"reference": reference, "set": False, "error": "ksGetObjParam_failed"})
                target_sketch.EndEdit()
                target_sketch.Update()
            except Exception as exc:
                post_anchor_report["errors"].append({"stage": "api5_style", "error": str(exc)})
                try:
                    target_sketch.EndEdit()
                except Exception:
                    pass
        if projected_line_style is not None and not any(item.get("set") for item in post_anchor_report.get("style_refs", [])):
            try:
                target_sketch.BeginEdit()
                api5_doc2d, _api5_doc2d_status = _get_api5_document2d()
                find_results = []
                for item in projected_segments:
                    geometry = item.get("geometry") or {}
                    start = geometry.get("start")
                    end = geometry.get("end")
                    if not (isinstance(start, (list, tuple)) and isinstance(end, (list, tuple)) and len(start) >= 2 and len(end) >= 2):
                        continue
                    mx = (float(start[0]) + float(end[0])) * 0.5
                    my = (float(start[1]) + float(end[1])) * 0.5
                    found_ref = 0
                    for limit in (0.001, 0.01, 0.1, 1.0, 5.0, 20.0):
                        found_ref = api5_doc2d.ksFindObj(mx, my, limit)
                        if found_ref:
                            break
                    result = {"source_reference": item.get("reference"), "midpoint": [mx, my], "found_ref": found_ref}
                    if found_ref:
                        result["style_before"] = api5_doc2d.ksGetObjectStyle(found_ref)
                        result["set"] = api5_doc2d.ksSetObjectStyle(found_ref, int(projected_line_style))
                        result["style_after"] = api5_doc2d.ksGetObjectStyle(found_ref)
                        try:
                            result["light_off"] = api5_doc2d.ksLightObj(found_ref, 0)
                        except Exception as exc:
                            result["light_off_error"] = str(exc)
                    find_results.append(result)
                try:
                    post_anchor_report["ksfind_end_obj"] = api5_doc2d.ksEndObj()
                except Exception as exc:
                    post_anchor_report["ksfind_end_obj_error"] = str(exc)
                post_anchor_report["ksfind_style_refs"] = find_results
                target_sketch.EndEdit()
                target_sketch.Update()
            except Exception as exc:
                post_anchor_report["errors"].append({"stage": "ksfind_style", "error": str(exc)})
                try:
                    target_sketch.EndEdit()
                except Exception:
                    pass
        if add_anchor and (not anchor_report or not anchor_report.get("added")):
            try:
                def point_tuple(point):
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        return float(point[0]), float(point[1])
                    return float(point["x"]), float(point["y"])

                def geometry_points(item):
                    geometry = item.get("geometry") or {}
                    return point_tuple(geometry["start"]), point_tuple(geometry["end"])

                def line_intersection(a1, a2, b1, b2):
                    x1, y1 = a1
                    x2, y2 = a2
                    x3, y3 = b1
                    x4, y4 = b2
                    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
                    if abs(denominator) <= 1e-12:
                        return None
                    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denominator
                    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denominator
                    return [float(px), float(py)]

                vertical = []
                non_vertical = []
                for item in projected_segments:
                    p1, p2 = geometry_points(item)
                    if abs(p1[0] - p2[0]) <= 1e-6:
                        vertical.append(item)
                    else:
                        non_vertical.append(item)
                if vertical and non_vertical:
                    projected_diagonal = max(non_vertical, key=lambda item: abs(geometry_points(item)[0][0] - geometry_points(item)[1][0]))
                    projected_shelf = max(vertical, key=lambda item: abs(geometry_points(item)[0][1] - geometry_points(item)[1][1]))
                    diag_a, diag_b = geometry_points(projected_diagonal)
                    spring_point = diag_a if abs(diag_a[0]) <= abs(diag_b[0]) else diag_b
                    diag_far = diag_b if spring_point == diag_a else diag_a
                    shelf_a, shelf_b = geometry_points(projected_shelf)
                    shelf_free = shelf_a if shelf_a[1] >= shelf_b[1] else shelf_b
                    mirror_start = [0.0, -spring_radius]
                    mirror_end = [float(diag_far[0]), float(-diag_far[1])]
                    axis_start = line_intersection(spring_point, diag_far, mirror_start, mirror_end)
                    if axis_start is None:
                        axis_start = [float((spring_point[0] + diag_far[0]) * 0.5), 0.0]
                    target_edit_doc = target_sketch.BeginEdit()
                    drawing = _get_sketch_drawing_container(target_edit_doc)
                    vertical_base_obj = _add_sketch_line_segment(drawing, [0.0, spring_radius], [0.0, -spring_radius], 6)
                    mirror_diagonal_obj = _add_sketch_line_segment(drawing, mirror_start, mirror_end, 6)
                    work_axis_obj = _add_sketch_line_segment(drawing, axis_start, [float(shelf_free[0]), float(shelf_free[1])], 3)
                    shelf_point_obj = _add_sketch_point(drawing, [float(shelf_free[0]), float(shelf_free[1])], 127)
                    if payload.get("post_anchor_constraints"):
                        def attempt_constraint(kind, target, partner_name, func):
                            item = {"kind": kind, "target": target}
                            if partner_name:
                                item["partner"] = partner_name
                            try:
                                item["result"] = func()
                            except Exception as exc:
                                item["error"] = str(exc)
                            return item

                        projected_diagonal_obj = None
                        projected_shelf_obj = None
                        projected_shelf_free_index = None
                        projected_anchor_report = []
                        for projected_info in projected_live_segments:
                            try:
                                projected_p1, projected_p2 = segment_points(projected_info)
                                projected_anchor_report.append(
                                    _sketch_full_json_safe({k: v for k, v in projected_info.items() if k != "object"})
                                )
                                if abs(projected_p1[0] - projected_p2[0]) <= 1e-4:
                                    projected_shelf_obj = projected_info.get("object")
                                    projected_shelf_free_index = 0 if projected_p1[1] >= projected_p2[1] else 1
                                else:
                                    projected_diagonal_obj = projected_info.get("object")
                            except Exception as exc:
                                post_anchor_report["errors"].append({"stage": "classify_projected_live_segment", "error": str(exc)})
                        post_anchor_report["projected_live_segments"] = projected_anchor_report

                        constraint_attempts = [
                            attempt_constraint(
                                "vertical",
                                "vertical_base",
                                None,
                                lambda: _apply_constraint_to_line(vertical_base_obj, SKETCH_CONSTRAINT_TYPES["vertical"]),
                            ),
                            attempt_constraint(
                                "merge_points",
                                "vertical_base.bottom",
                                "mirror_diagonal.start",
                                lambda: _apply_constraint_to_line(
                                    vertical_base_obj,
                                    SKETCH_CONSTRAINT_TYPES["merge_points"],
                                    index=1,
                                    partner=mirror_diagonal_obj,
                                    partner_index=0,
                                ),
                            ),
                            attempt_constraint(
                                "point_on_curve",
                                "work_axis.start",
                                "mirror_diagonal",
                                lambda: _apply_constraint_to_line(
                                    work_axis_obj,
                                    SKETCH_CONSTRAINT_TYPES["point_on_curve"],
                                    index=0,
                                    partner=mirror_diagonal_obj,
                                ),
                            ),
                            attempt_constraint(
                                "merge_points",
                                "work_axis.end",
                                "shelf_point",
                                lambda: _apply_constraint_to_line(
                                    work_axis_obj,
                                    SKETCH_CONSTRAINT_TYPES["merge_points"],
                                    index=1,
                                    partner=shelf_point_obj,
                                    partner_index=0,
                                ),
                            ),
                        ]
                        if projected_diagonal_obj is not None:
                            constraint_attempts.extend(
                                [
                                    attempt_constraint(
                                        "merge_points",
                                        "vertical_base.top",
                                        "projected_diagonal.top",
                                        lambda: _apply_constraint_to_line(
                                            vertical_base_obj,
                                            SKETCH_CONSTRAINT_TYPES["merge_points"],
                                            index=0,
                                            partner=projected_diagonal_obj,
                                            partner_index=0,
                                        ),
                                    ),
                                    attempt_constraint(
                                        "point_on_curve",
                                        "work_axis.start",
                                        "projected_diagonal",
                                        lambda: _apply_constraint_to_line(
                                            work_axis_obj,
                                            SKETCH_CONSTRAINT_TYPES["point_on_curve"],
                                            index=0,
                                            partner=projected_diagonal_obj,
                                        ),
                                    ),
                                ]
                            )
                        if projected_shelf_obj is not None:
                            constraint_attempts.append(
                                attempt_constraint(
                                    "merge_points",
                                    "work_axis.end",
                                    "projected_shelf.free_end",
                                    lambda: _apply_constraint_to_line(
                                        work_axis_obj,
                                        SKETCH_CONSTRAINT_TYPES["merge_points"],
                                        index=1,
                                        partner=projected_shelf_obj,
                                        partner_index=projected_shelf_free_index,
                                    ),
                                )
                            )
                        post_anchor_report["constraint_attempts"] = constraint_attempts
                        post_anchor_report["dimension_attempts"] = _apply_sketch_dimensions(
                            drawing,
                            {
                                "vertical_base": _sketch_line_entry(
                                    vertical_base_obj,
                                    0.0,
                                    spring_radius,
                                    0.0,
                                    -spring_radius,
                                    role="line",
                                    target="vertical_base",
                                )
                            },
                            [
                                {
                                    "kind": "line_length",
                                    "target": "vertical_base",
                                    "value": spring_radius * 2.0,
                                    "expression": "D1 - WD1",
                                    "orientation": "vertical",
                                }
                            ],
                            {"enabled": True, "driving": True},
                        )
                    target_sketch.EndEdit()
                    target_sketch.Update()
                    post_anchor_report["added"] = [
                        {"id": "vertical_base", "start": [0.0, spring_radius], "end": [0.0, -spring_radius], "style": 6, "reference": safe_get(vertical_base, "Reference")},
                        {"id": "mirror_diagonal", "start": mirror_start, "end": mirror_end, "style": 6, "reference": safe_get(mirror_diagonal, "Reference")},
                        {"id": "work_axis", "start": axis_start, "end": [float(shelf_free[0]), float(shelf_free[1])], "style": 3, "reference": safe_get(work_axis, "Reference")},
                        {"id": "shelf_point", "point": [float(shelf_free[0]), float(shelf_free[1])], "style": 127, "reference": safe_get(shelf_point, "Reference")},
                    ]
                else:
                    post_anchor_report["errors"].append({"stage": "post_add_anchor", "error": "projected_diagonal_or_shelf_not_found"})
            except Exception as exc:
                post_anchor_report["errors"].append({"stage": "post_add_anchor", "error": str(exc)})
                try:
                    target_sketch.EndEdit()
                except Exception:
                    pass
        snapshot = _inspect_sketch_full(
            model_container,
            {
                "target": {"mode": "existing_sketch", "sketch_ref": safe_get(target_sketch, "Reference")},
                "include_dimensions": True,
                "include_constraints": True,
                "include_diagnostics": True,
                "max_items": payload.get("max_items") or 200,
            },
        )
        projected_segments = [item for item in (snapshot or {}).get("entities", []) if item.get("kind") == "segment"]

    post_constraint_report = None
    if add_constraints and snapshot:
        post_constraint_report = {"errors": [], "constraints": None, "dimensions": None, "entities": {}}
        try:
            target_edit_doc = target_sketch.BeginEdit()
            drawing = _get_sketch_drawing_container(target_edit_doc)
            line_segments = _resolve_model_object_collection(drawing, ("LineSegments", "GetLineSegments"))
            points_collection = _resolve_model_object_collection(drawing, ("Points", "GetPoints"))

            def pt_tuple(point):
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    return float(point[0]), float(point[1])
                return float(point["x"]), float(point["y"])

            def dist2(a, b):
                return (float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2

            def close(a, b, tolerance=1e-5):
                return dist2(a, b) <= tolerance * tolerance

            def seg_points(info):
                geometry = info.get("geometry") or {}
                return pt_tuple(geometry["start"]), pt_tuple(geometry["end"])

            def endpoint_index(info, point):
                p1, p2 = seg_points(info)
                return 0 if dist2(p1, point) <= dist2(p2, point) else 1

            lines = []
            for index in range(collection_count(line_segments)):
                obj = get_collection_item(line_segments, index)
                segment = _cast_to_com_interface(obj, "ILineSegment") or obj
                info = _serialize_line_segment(segment, index, "segments")
                info["object"] = segment
                info["style"] = (info.get("raw_properties") or {}).get("Style")
                lines.append(info)

            vertical_lines = []
            nonvertical_lines = []
            for info in lines:
                p1, p2 = seg_points(info)
                if abs(p1[0] - p2[0]) <= 1e-6:
                    vertical_lines.append(info)
                else:
                    nonvertical_lines.append(info)

            spring_radius = float(payload.get("spring_radius", 13.5))
            vertical_base = min(vertical_lines, key=lambda item: min(abs(seg_points(item)[0][0]), abs(seg_points(item)[1][0]))) if vertical_lines else None
            projected_shelf = max(vertical_lines, key=lambda item: max(abs(seg_points(item)[0][0]), abs(seg_points(item)[1][0]))) if vertical_lines else None
            work_axis = next((item for item in lines if item.get("style") == 3), None)
            if work_axis is not None:
                post_constraint_report["work_axis_entity"] = {k: v for k, v in work_axis.items() if k != "object"}
            aux_nonvertical = [item for item in nonvertical_lines if item.get("style") == 6]
            projected_diagonal = None
            mirror_diagonal = None
            for info in aux_nonvertical:
                p1, p2 = seg_points(info)
                if close(p1, (0.0, spring_radius)) or close(p2, (0.0, spring_radius)):
                    projected_diagonal = info
                if close(p1, (0.0, -spring_radius)) or close(p2, (0.0, -spring_radius)):
                    mirror_diagonal = info

            shelf_point = None
            if projected_shelf is not None:
                shelf_a, shelf_b = seg_points(projected_shelf)
                shelf_free = shelf_a if shelf_a[1] >= shelf_b[1] else shelf_b
                for index in range(collection_count(points_collection)):
                    point_obj = get_collection_item(points_collection, index)
                    point_info = _serialize_point(point_obj, index, "points")
                    point_geometry = point_info.get("geometry") or {}
                    if close((point_geometry.get("x"), point_geometry.get("y")), shelf_free):
                        shelf_point = {"object": point_obj, "role": "point", "x": float(point_geometry.get("x")), "y": float(point_geometry.get("y"))}
                        break

            required = {
                "projected_diagonal": projected_diagonal,
                "projected_shelf": projected_shelf,
                "vertical_base": vertical_base,
                "mirror_diagonal": mirror_diagonal,
                "work_axis": work_axis,
                "shelf_point": shelf_point,
            }
            post_constraint_report["entities"] = {
                name: _sketch_full_json_safe({k: v for k, v in value.items() if k != "object"}) if isinstance(value, dict) else None
                for name, value in required.items()
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                post_constraint_report["errors"].append({"stage": "find_entities", "missing": missing})
            else:
                sketch_entities = {}
                for name, info in (
                    ("projected_diagonal", projected_diagonal),
                    ("projected_shelf", projected_shelf),
                    ("vertical_base", vertical_base),
                    ("mirror_diagonal", mirror_diagonal),
                    ("work_axis", work_axis),
                ):
                    p1, p2 = seg_points(info)
                    sketch_entities[name] = _sketch_line_entry(info["object"], p1[0], p1[1], p2[0], p2[1], role="line", target=name)
                sketch_entities["shelf_point"] = shelf_point

                vb_top = (0.0, spring_radius)
                vb_bottom = (0.0, -spring_radius)
                pd_spring_index = endpoint_index(projected_diagonal, vb_top)
                vb_top_index = endpoint_index(vertical_base, vb_top)
                md_start_index = endpoint_index(mirror_diagonal, vb_bottom)
                vb_bottom_index = endpoint_index(vertical_base, vb_bottom)
                shelf_a, shelf_b = seg_points(projected_shelf)
                shelf_free = shelf_a if shelf_a[1] >= shelf_b[1] else shelf_b
                shelf_free_index = endpoint_index(projected_shelf, shelf_free)
                work_end_index = endpoint_index(work_axis, shelf_free)
                work_start_index = 1 - work_end_index

                constraints = [
                    {"kind": "merge_points", "target": "vertical_base", "index": vb_top_index, "partner": "projected_diagonal", "partner_index": pd_spring_index},
                    {"kind": "merge_points", "target": "vertical_base", "index": vb_bottom_index, "partner": "mirror_diagonal", "partner_index": md_start_index},
                    {"kind": "point_on_curve", "target": "work_axis", "index": work_start_index, "partner": "projected_diagonal"},
                    {"kind": "point_on_curve", "target": "work_axis", "index": work_start_index, "partner": "mirror_diagonal"},
                    {"kind": "merge_points", "target": "work_axis", "index": work_end_index, "partner": "projected_shelf", "partner_index": shelf_free_index},
                    {"kind": "merge_points", "target": "shelf_point", "index": 0, "partner": "work_axis", "partner_index": work_end_index},
                    {"kind": "merge_points", "target": "shelf_point", "index": 0, "partner": "projected_shelf", "partner_index": shelf_free_index},
                    {"kind": "vertical", "target": "vertical_base"},
                ]
                dimensions = [
                    {"kind": "line_length", "target": "vertical_base", "value": spring_radius * 2.0, "expression": "D1 - WD1"},
                ]
                post_constraint_report["constraints"] = _apply_sketch_constraints(sketch_entities, constraints, {"enabled": True})
                post_constraint_report["dimensions"] = _apply_sketch_dimensions(drawing, sketch_entities, dimensions, {"enabled": True, "driving": True})
            target_sketch.EndEdit()
            target_sketch.Update()
            snapshot = _inspect_sketch_full(
                model_container,
                {
                    "target": {"mode": "existing_sketch", "sketch_ref": safe_get(target_sketch, "Reference")},
                    "include_dimensions": True,
                    "include_constraints": True,
                    "include_diagnostics": True,
                    "max_items": payload.get("max_items") or 200,
                },
            )
        except Exception as exc:
            post_constraint_report["errors"].append({"stage": "post_constraints", "error": str(exc)})
            try:
                target_sketch.EndEdit()
            except Exception:
                pass

    return {
        "source": {"name": safe_get(source_sketch, "Name"), "reference": safe_get(source_sketch, "Reference")},
        "target": {"name": safe_get(target_sketch, "Name"), "reference": safe_get(target_sketch, "Reference")},
        "projected": projected,
        "target_update_ok": target_update_ok,
        "part_update_ok": part_update_ok,
        "anchor_report": anchor_report,
        "post_anchor_report": post_anchor_report,
        "post_constraint_report": post_constraint_report,
        "snapshot_summary": snapshot.get("summary") if snapshot else None,
        "constraint_summary": (snapshot.get("constraints") or {}).get("summary") if snapshot else None,
        "snapshot": snapshot,
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


def handle_create_plane_by_edge_and_plane(payload):
    app = make_app()
    document = cast_document_3d(payload.get("_document")) if payload.get("_document") is not None else resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")
    part = safe_get(document, "TopPart")
    if part is None:
        raise RuntimeError("Document does not expose TopPart")
    model_container = cast_model_container(part)
    if model_container is None:
        raise RuntimeError("Document TopPart cannot be used as a model container")

    sketch_name = payload.get("sketch_name") or payload.get("source_sketch_name")
    if not sketch_name:
        raise RuntimeError("sketch_name is required")

    sketches = _get_sketch_collection(model_container)
    target_sketch = None
    sketch_report = []
    for index in range(collection_count(sketches)):
        sketch = _cast_to_com_interface(get_collection_item(sketches, index), "ISketch")
        item = {"index": index, "name": safe_get(sketch, "Name"), "reference": safe_get(sketch, "Reference")}
        sketch_report.append(item)
        if item["name"] == sketch_name:
            target_sketch = sketch
    if target_sketch is None:
        raise RuntimeError("Sketch not found: %s" % sketch_name)

    snapshot = _inspect_sketch_full(
        model_container,
        {
            "target": {"mode": "existing_sketch", "sketch_ref": safe_get(target_sketch, "Reference")},
            "include_dimensions": True,
            "include_constraints": True,
            "include_diagnostics": True,
            "max_items": payload.get("max_items") or 300,
        },
    )
    edge_style = payload.get("edge_style", payload.get("axis_style", 3))
    target_geometry = payload.get("edge_geometry")
    target_entity = None
    explicit_collection_name = payload.get("edge_collection_name")
    explicit_edge_index = payload.get("edge_index")
    if explicit_edge_index is not None:
        for entity in snapshot.get("entities") or []:
            if entity.get("kind") != "segment":
                continue
            if explicit_collection_name and entity.get("collection_name") != explicit_collection_name:
                continue
            if int(entity.get("index", -1)) == int(explicit_edge_index):
                target_entity = entity
                break
    for entity in snapshot.get("entities") or []:
        if target_entity is not None:
            break
        if entity.get("kind") != "segment":
            continue
        style = ((entity.get("classification") or {}).get("style")) or (entity.get("raw_properties") or {}).get("Style")
        if target_geometry is None and edge_style is not None and int(style or -1) == int(edge_style):
            target_entity = entity
            break
    if target_entity is None and target_geometry is not None:
        target_entity = {"geometry": target_geometry}
    if target_entity is None:
        raise RuntimeError("Could not find target sketch segment by style %s" % edge_style)

    def point_tuple(point):
        if isinstance(point, dict):
            point = point.get("point") or point.get("start") or point.get("end") or [point.get("x"), point.get("y")]
        return (float(point[0]), float(point[1]))

    def geometry_points(geometry):
        return point_tuple(geometry.get("start")), point_tuple(geometry.get("end"))

    def same_points(a, b, tol=1e-4):
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol

    target_start, target_end = geometry_points(target_entity.get("geometry") or {})
    if target_geometry is not None:
        for entity in snapshot.get("entities") or []:
            if entity.get("kind") != "segment" or not entity.get("geometry"):
                continue
            try:
                entity_start, entity_end = geometry_points(entity.get("geometry") or {})
                if (same_points(entity_start, target_start) and same_points(entity_end, target_end)) or (same_points(entity_start, target_end) and same_points(entity_end, target_start)):
                    target_entity = entity
                    break
            except Exception:
                pass
    target_reference = payload.get("edge_reference") or target_entity.get("reference")
    edge_types = payload.get("edge_types") or [1, 2, 3]
    edge_candidates = []
    edge_objects = []
    selected_edge = None
    selected_edge_report = None
    for edge_type in edge_types:
        try:
            raw_edges = target_sketch.Edges(int(edge_type))
        except Exception as exc:
            edge_candidates.append({"edge_type": edge_type, "error": str(exc)})
            continue
        if raw_edges is None:
            edge_candidates.append({"edge_type": edge_type, "count": 0})
            continue
        if isinstance(raw_edges, (list, tuple)):
            edges = list(raw_edges)
        elif collection_count(raw_edges):
            edges = iter_collection(raw_edges)
        else:
            edges = [raw_edges]
        for edge_index, edge in enumerate(edges):
            item = {"edge_type": edge_type, "index": edge_index, "reference": safe_get(edge, "Reference"), "type": type(edge).__name__}
            edge_objects.append((edge, item))
            if selected_edge is None and target_reference not in (None, "") and str(item.get("reference")) == str(target_reference):
                selected_edge = edge
                selected_edge_report = dict(item)
                selected_edge_report["matches_target"] = "reference"
            try:
                geometry = _sketch_entity_geometry("segment", edge)
                item["geometry"] = geometry
                edge_start, edge_end = geometry_points(geometry)
                direct = same_points(edge_start, target_start) and same_points(edge_end, target_end)
                reverse = same_points(edge_start, target_end) and same_points(edge_end, target_start)
                item["matches_target"] = bool(direct or reverse)
                if selected_edge is None and item["matches_target"]:
                    selected_edge = edge
                    selected_edge_report = dict(item)
            except Exception as exc:
                item["geometry_error"] = str(exc)
            edge_candidates.append(item)
    if selected_edge is None and len(edge_objects) == 1 and payload.get("allow_single_edge_fallback", True):
        selected_edge, selected_edge_report = edge_objects[0]
        selected_edge_report = dict(selected_edge_report)
        selected_edge_report["matches_target"] = "single_edge_fallback"
    if selected_edge is None and (int(edge_style or -1) == 3 or target_geometry is not None) and payload.get("allow_axis_extra_edge_fallback", True):
        refs_by_type = {}
        for edge, item in edge_objects:
            refs_by_type.setdefault(item.get("edge_type"), set()).add(item.get("reference"))
        type1_refs = refs_by_type.get(1, set())
        type2_extra_refs = [ref for ref in refs_by_type.get(2, set()) if ref not in type1_refs]
        if len(type2_extra_refs) == 1:
            extra_ref = type2_extra_refs[0]
            for edge, item in edge_objects:
                if item.get("edge_type") == 2 and item.get("reference") == extra_ref:
                    selected_edge = edge
                    selected_edge_report = dict(item)
                    selected_edge_report["matches_target"] = "axis_extra_edge_type2_fallback"
                    break
    if selected_edge is None and payload.get("allow_target_entity_object", False) and target_reference is not None:
        sketch_doc = target_sketch.BeginEdit()
        if sketch_doc is not None:
            try:
                drawing_container = _get_sketch_drawing_container(sketch_doc)
                collection, _ = _collection_for_sketch_entity_kind(drawing_container, "segment")
                for index, item in enumerate(iter_collection(collection)):
                    if str(safe_get(item, "Reference")) == str(target_reference):
                        selected_edge = item
                        selected_edge_report = {"matches_target": "target_entity_reference_object", "collection_name": "segments", "index": index, "reference": safe_get(item, "Reference")}
                        break
            finally:
                target_sketch.EndEdit()
    if selected_edge is None and payload.get("allow_target_entity_object", False) and target_start is not None and target_end is not None:
        sketch_doc = target_sketch.BeginEdit()
        if sketch_doc is not None:
            try:
                drawing_container = _get_sketch_drawing_container(sketch_doc)
                collection, _ = _collection_for_sketch_entity_kind(drawing_container, "segment")
                for index, item in enumerate(iter_collection(collection)):
                    try:
                        geometry = _sketch_entity_geometry("segment", item)
                        item_start, item_end = geometry_points(geometry)
                        direct = same_points(item_start, target_start) and same_points(item_end, target_end)
                        reverse = same_points(item_start, target_end) and same_points(item_end, target_start)
                    except Exception:
                        direct = reverse = False
                    if direct or reverse:
                        selected_edge = item
                        selected_edge_report = {"matches_target": "target_entity_geometry_object", "collection_name": "segments", "index": index, "reference": safe_get(item, "Reference")}
                        break
            finally:
                target_sketch.EndEdit()
    if selected_edge is None and payload.get("allow_target_entity_object", False) and explicit_edge_index is not None:
        sketch_doc = target_sketch.BeginEdit()
        if sketch_doc is not None:
            try:
                drawing_container = _get_sketch_drawing_container(sketch_doc)
                collection, _ = _collection_for_sketch_entity_kind(drawing_container, "segment")
                selected_edge = get_collection_item(collection, int(explicit_edge_index))
                selected_edge_report = {"matches_target": "explicit_target_entity_object", "collection_name": explicit_collection_name or "segments", "index": explicit_edge_index, "reference": safe_get(selected_edge, "Reference")}
            finally:
                target_sketch.EndEdit()
    if selected_edge is None and payload.get("allow_target_entity_object", False) and target_entity is not None and target_entity.get("collection_name") and target_entity.get("index") is not None:
        sketch_doc = target_sketch.BeginEdit()
        if sketch_doc is not None:
            try:
                drawing_container = _get_sketch_drawing_container(sketch_doc)
                collection, _ = _collection_for_sketch_entity_kind(drawing_container, target_entity.get("kind") or "segment")
                selected_edge = get_collection_item(collection, int(target_entity.get("index")))
                selected_edge_report = {"matches_target": "target_entity_object", "collection_name": target_entity.get("collection_name"), "index": target_entity.get("index"), "reference": safe_get(selected_edge, "Reference")}
            finally:
                target_sketch.EndEdit()
    if selected_edge is None:
        raise RuntimeError("Could not map sketch segment to IEdge; candidates=%s" % json.dumps(edge_candidates, ensure_ascii=False))

    base_plane_value = payload.get("base_plane") or payload.get("plane") or "XOY"
    try:
        base_plane_key = _normalize_sketch_plane(base_plane_value)
        reference_plane = _resolve_default_part_object(part, base_plane_key)
    except Exception:
        reference_plane = _find_named_auxiliary_object(part, "Planes3D", str(base_plane_value))
        if reference_plane is None:
            reference_plane = _find_named_auxiliary_object(_cast_to_com_interface(part, "IAuxiliaryGeomContainer"), "Planes3D", str(base_plane_value))
        if reference_plane is None:
            raise RuntimeError("Unsupported base plane or plane name: %s" % base_plane_value)
        base_plane_key = str(safe_get(reference_plane, "Name") or base_plane_value)
    plane = _create_plane_by_edge_and_plane(
        part,
        payload.get("name") or payload.get("plane_name") or "PLANE_BY_EDGE_AND_PLANE",
        selected_edge,
        reference_plane,
        parallel=bool(payload.get("parallel", False)),
    )
    try:
        model_container.Update()
    except Exception:
        pass
    return {
        "ok": True,
        "document": describe_document(document, app),
        "sketches": sketch_report,
        "source_sketch": {"name": sketch_name, "reference": safe_get(target_sketch, "Reference")},
        "target_entity": _sketch_full_json_safe(target_entity),
        "edge_candidates": _sketch_full_json_safe(edge_candidates),
        "selected_edge": _sketch_full_json_safe(selected_edge_report),
        "plane": {
            "name": safe_get(plane, "Name"),
            "reference": safe_get(plane, "Reference"),
            "type": type(plane).__name__,
            "parallel": bool(payload.get("parallel", False)),
            "base_plane": base_plane_key,
        },
    }


def _select_sketch_axis_edge_by_style(model_container, sketch, edge_style=3):
    snapshot = _inspect_sketch_full(
        model_container,
        {
            "target": {"mode": "existing_sketch", "sketch_ref": safe_get(sketch, "Reference")},
            "include_dimensions": True,
            "include_constraints": True,
            "include_diagnostics": True,
            "max_items": 300,
        },
    )
    target_entity = None
    for entity in snapshot.get("entities") or []:
        if entity.get("kind") != "segment":
            continue
        style = ((entity.get("classification") or {}).get("style")) or (entity.get("raw_properties") or {}).get("Style")
        if int(style or -1) == int(edge_style):
            target_entity = entity
            break

    edge_objects = []
    edge_candidates = []
    for edge_type in (1, 2, 3):
        try:
            raw_edges = sketch.Edges(int(edge_type))
        except Exception as exc:
            edge_candidates.append({"edge_type": edge_type, "error": str(exc)})
            continue
        if raw_edges is None:
            continue
        if isinstance(raw_edges, (list, tuple)):
            edges = list(raw_edges)
        elif collection_count(raw_edges):
            edges = iter_collection(raw_edges)
        else:
            edges = [raw_edges]
        for edge_index, edge in enumerate(edges):
            item = {"edge_type": edge_type, "index": edge_index, "reference": safe_get(edge, "Reference"), "type": type(edge).__name__}
            try:
                item["endpoints"] = _sample_curve_endpoints(edge)
            except Exception as exc:
                item["endpoints_error"] = str(exc)
            edge_objects.append((edge, item))
            edge_candidates.append(dict(item))
    selected_edge = None
    selected_report = None
    if selected_edge is None and len(edge_objects) == 1:
        selected_edge, selected_report = edge_objects[0]
        selected_report = dict(selected_report)
        selected_report["matches_target"] = "single_edge_fallback"
    elif selected_edge is None:
        refs_by_type = {}
        for _edge, item in edge_objects:
            refs_by_type.setdefault(item.get("edge_type"), set()).add(item.get("reference"))
        type1_refs = refs_by_type.get(1, set())
        type2_extra_refs = [ref for ref in refs_by_type.get(2, set()) if ref not in type1_refs]
        if len(type2_extra_refs) == 1:
            extra_ref = type2_extra_refs[0]
            for edge, item in edge_objects:
                if item.get("edge_type") == 2 and item.get("reference") == extra_ref:
                    selected_edge = edge
                    selected_report = dict(item)
                    selected_report["matches_target"] = "axis_extra_edge_type2_fallback"
                    break
    if selected_edge is None:
        raise RuntimeError("Could not select sketch axis edge; candidates=%s" % json.dumps(edge_candidates, ensure_ascii=False))
    return selected_edge, {"snapshot_target_entity": _sketch_full_json_safe(target_entity), "edge_candidates": edge_candidates, "selected_edge": selected_report}


def handle_create_self_wrapping_sketch2(payload):
    app = make_app()
    document = cast_document_3d(payload.get("_document")) if payload.get("_document") is not None else resolve_document(app, payload.get("document_id"))
    if document is None:
        raise RuntimeError("Document not found or no active document")
    part = safe_get(document, "TopPart")
    model_container = cast_model_container(part)
    source_sketch_name = payload.get("source_sketch_name") or "SELF_WRAPPING_PHASE2_LEFT_SKETCH1_PROJECTED"
    target_name = payload.get("target_sketch_name") or "SELF_WRAPPING_PHASE2_SKETCH2_PATH"
    target_plane = payload.get("plane") or payload.get("target_plane") or "SELF_WRAPPING_PHASE2_AXIS_PERP_PLANE"
    radius = float(payload.get("radius", payload.get("p1", 3.01)))
    radius_expression = str(payload.get("radius_expression") or "P1")
    tail_length = float(payload.get("tail_length", 6.0))
    tail_expression = str(payload.get("tail_expression") or "HT1")

    sketches = _get_sketch_collection(model_container)
    source_sketch = None
    for index in range(collection_count(sketches)):
        sketch = _cast_to_com_interface(get_collection_item(sketches, index), "ISketch")
        if safe_get(sketch, "Name") == source_sketch_name:
            source_sketch = sketch
            break
    if source_sketch is None:
        raise RuntimeError("Source sketch not found: %s" % source_sketch_name)
    axis_edge, axis_report = _select_sketch_axis_edge_by_style(model_container, source_sketch, int(payload.get("axis_style", 3)))

    target_coordinate_system_mode = str(payload.get("target_coordinate_system") or "").lower()
    target_plane_object = None
    if target_coordinate_system_mode == "plane":
        try:
            target_plane_object = _resolve_default_part_object(part, _normalize_sketch_plane(target_plane))
        except Exception:
            target_plane_object = _find_named_auxiliary_object(_cast_to_com_interface(part, "IAuxiliaryGeomContainer"), "Planes3D", str(target_plane))
    target_sketch, target_plane_key = _create_sketch_on_plane(
        model_container,
        part,
        target_name,
        target_plane_object if target_plane_object is not None else target_plane,
        assign_coordinate_system=target_coordinate_system_mode == "plane",
        coordinate_system_before_plane=target_coordinate_system_mode == "plane",
    )
    edit_doc = target_sketch.BeginEdit()
    if edit_doc is None:
        raise RuntimeError("BeginEdit returned None for Sketch2")
    drawing = _get_sketch_drawing_container(edit_doc)
    report = {"axis_edge": axis_report, "created": {}, "constraints": None, "dimensions": None}
    projected_axis_midpoint = None
    try:
        projected_axis_result = target_sketch.AddProjectionOf(axis_edge)
        if isinstance(projected_axis_result, (list, tuple)):
            projected_axis = projected_axis_result[0]
        elif collection_count(projected_axis_result):
            projected_axis = iter_collection(projected_axis_result)[0]
        else:
            projected_axis = projected_axis_result
        try:
            projected_axis.Style = 6
        except Exception:
            pass
        projected_axis_geometry = _sketch_entity_geometry("segment", projected_axis)
        axis_a = projected_axis_geometry.get("start")
        axis_b = projected_axis_geometry.get("end")
        if not axis_a or not axis_b:
            raise RuntimeError("Projected axis geometry is unavailable")
        projected_axis_midpoint = [(float(axis_a[0]) + float(axis_b[0])) / 2.0, (float(axis_a[1]) + float(axis_b[1])) / 2.0]
        center_endpoint = str(payload.get("center_endpoint") or "closest_to_origin").lower()
        if center_endpoint in {"start", "a", "axis_a"}:
            center = [float(axis_a[0]), float(axis_a[1])]
            start = [float(axis_b[0]), float(axis_b[1])]
        elif center_endpoint in {"end", "b", "axis_b"}:
            center = [float(axis_b[0]), float(axis_b[1])]
            start = [float(axis_a[0]), float(axis_a[1])]
        else:
            dist_a = math.hypot(float(axis_a[0]), float(axis_a[1]))
            dist_b = math.hypot(float(axis_b[0]), float(axis_b[1]))
            center = [float(axis_a[0]), float(axis_a[1])] if dist_a <= dist_b else [float(axis_b[0]), float(axis_b[1])]
            start = [float(axis_b[0]), float(axis_b[1])] if dist_a <= dist_b else [float(axis_a[0]), float(axis_a[1])]
        ux = start[0] - center[0]
        uy = start[1] - center[1]
        distance = math.hypot(ux, uy)
        if distance <= radius:
            raise RuntimeError("Projected axis length must be greater than arc radius")
        ux /= distance
        uy /= distance
        side = -1.0 if str(payload.get("side") or "left").lower() in {"right", "negative", "cw"} else 1.0
        nx = -uy * side
        ny = ux * side
        cos_alpha = radius / distance
        sin_alpha = math.sqrt(max(0.0, 1.0 - cos_alpha * cos_alpha))
        arc_start = [center[0] + radius * (cos_alpha * ux + sin_alpha * nx), center[1] + radius * (cos_alpha * uy + sin_alpha * ny)]
        arc_end = [center[0] - radius * nx, center[1] - radius * ny]
        tail_end = [arc_end[0] + tail_length * ux, arc_end[1] + tail_length * uy]

        long_line = _add_sketch_line_segment(drawing, start, arc_start, 1)
        arc = _add_sketch_arc(drawing, center, radius, arc_start, arc_end, True, 1)
        tail_line = _add_sketch_line_segment(drawing, arc_end, tail_end, 1)
        use_anchor_points = bool(payload.get("use_anchor_points", True))
        center_point = _add_sketch_point(drawing, center, 127) if use_anchor_points else None
        end_point = _add_sketch_point(drawing, start, 127) if use_anchor_points else None

        sketch_entities = {
            "projected_axis": _sketch_line_entry(projected_axis, axis_a[0], axis_a[1], axis_b[0], axis_b[1], role="line", target="projected_axis"),
            "long_line": _sketch_line_entry(long_line, start[0], start[1], arc_start[0], arc_start[1], role="line", target="long_line"),
            "turn_arc": _sketch_arc_entry(arc, center[0], center[1], radius, arc_start[0], arc_start[1], arc_end[0], arc_end[1], direction=True, role="arc", target="turn_arc"),
            "tail_line": _sketch_line_entry(tail_line, arc_end[0], arc_end[1], tail_end[0], tail_end[1], role="line", target="tail_line"),
        }
        if use_anchor_points:
            sketch_entities["center_point"] = _sketch_point_entry(center_point, center[0], center[1], role="point", target="center_point")
            sketch_entities["end_point"] = _sketch_point_entry(end_point, start[0], start[1], role="point", target="end_point")
        projected_center_index = 0 if math.hypot(axis_a[0] - center[0], axis_a[1] - center[1]) <= 1e-4 else 1
        projected_start_index = 1 - projected_center_index
        if use_anchor_points:
            constraints = [
                {"kind": "merge_points", "target": "end_point", "index": 0, "partner": "projected_axis", "partner_index": projected_start_index},
                {"kind": "merge_points", "target": "end_point", "index": 0, "partner": "long_line", "partner_index": 0},
                {"kind": "merge_points", "target": "long_line", "index": 1, "partner": "turn_arc", "partner_index": 1},
                {"kind": "tangent", "target": "long_line", "partner": "turn_arc"},
                {"kind": "merge_points", "target": "turn_arc", "index": 2, "partner": "tail_line", "partner_index": 0},
                {"kind": "tangent", "target": "tail_line", "partner": "turn_arc"},
                {"kind": "horizontal", "target": "tail_line"},
                {"kind": "merge_points", "target": "center_point", "index": 0, "partner": "turn_arc", "partner_index": 0},
                {"kind": "merge_points", "target": "center_point", "index": 0, "partner": "projected_axis", "partner_index": projected_center_index},
            ]
        else:
            constraints = [
                {"kind": "merge_points", "target": "long_line", "index": 0, "partner": "projected_axis", "partner_index": projected_start_index},
                {"kind": "merge_points", "target": "turn_arc", "index": 0, "partner": "projected_axis", "partner_index": projected_center_index},
                {"kind": "merge_points", "target": "long_line", "index": 1, "partner": "turn_arc", "partner_index": 1},
                {"kind": "tangent", "target": "long_line", "partner": "turn_arc"},
                {"kind": "merge_points", "target": "turn_arc", "index": 2, "partner": "tail_line", "partner_index": 0},
                {"kind": "tangent", "target": "tail_line", "partner": "turn_arc"},
                {"kind": "horizontal", "target": "tail_line"},
            ]
        report["constraints"] = _apply_sketch_constraints(sketch_entities, constraints, {"enabled": True})
        report["dimensions"] = _apply_sketch_dimensions(
            drawing,
            sketch_entities,
            [
                {"kind": "line_length", "target": "tail_line", "value": tail_length, "expression": tail_expression, "orientation": "parallel"},
                {"kind": "arc_radius", "target": "turn_arc", "value": radius, "expression": radius_expression, "angle": 0.0},
            ],
            {"enabled": True, "driving": True},
        )
        report["created"] = _sketch_full_json_safe({k: {kk: vv for kk, vv in v.items() if kk != "object"} for k, v in sketch_entities.items()})
    finally:
        try:
            target_sketch.EndEdit()
        except Exception:
            pass
    target_sketch.Update()
    if projected_axis_midpoint is not None:
        style_report = {"target": "projected_axis", "midpoint": projected_axis_midpoint}
        try:
            target_sketch.BeginEdit()
            app5, _api5_module, app5_status = _get_api5_kompas_object()
            api5_doc2d, doc2d_status = _get_api5_document2d()
            style_report["api5"] = {"app": app5_status, "doc2d": doc2d_status}
            if api5_doc2d is not None:
                found_ref = api5_doc2d.ksFindObj(float(projected_axis_midpoint[0]), float(projected_axis_midpoint[1]), 2.0)
                style_report["found_ref"] = int(found_ref) if found_ref else found_ref
                if found_ref:
                    style_report["set_style_result"] = api5_doc2d.ksSetObjectStyle(found_ref, 6)
                    try:
                        api5_doc2d.ksLightObj(found_ref, 0)
                    except Exception:
                        pass
                    try:
                        api5_doc2d.ksEndObj()
                    except Exception:
                        pass
            target_sketch.EndEdit()
            target_sketch.Update()
        except Exception as exc:
            style_report["error"] = str(exc)
            try:
                target_sketch.EndEdit()
            except Exception:
                pass
        report["projected_axis_style"] = style_report
    try:
        model_container.Update()
    except Exception:
        pass
    snapshot = _inspect_sketch_full(
        model_container,
        {"target": {"mode": "existing_sketch", "sketch_ref": safe_get(target_sketch, "Reference")}, "include_dimensions": True, "include_constraints": True, "include_diagnostics": True, "max_items": payload.get("max_items") or 300},
    )
    return {
        "ok": True,
        "document": describe_document(document, app),
        "target": {"name": safe_get(target_sketch, "Name"), "reference": safe_get(target_sketch, "Reference"), "plane": target_plane_key},
        "report": report,
        "snapshot": snapshot,
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
        "x1": float(xc),
        "y1": float(yc),
        "x2": float(xc),
        "y2": float(yc),
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


def _resolve_current_sketch_circle(drawing_container, source_circle, fallback_center, fallback_radius, *, tolerance=1e-6):
    if source_circle is None:
        return None
    circles, _, _ = _resolve_model_object_collection(drawing_container, ("Circles", "GetCircles"))
    if circles is None:
        return source_circle

    fallback_x = float((fallback_center or [0.0, 0.0])[0])
    fallback_y = float((fallback_center or [0.0, 0.0])[1])
    expected_reference = safe_get(source_circle, "Reference")
    expected_xc = float(safe_get(source_circle, "Xc", fallback_x))
    expected_yc = float(safe_get(source_circle, "Yc", fallback_y))
    expected_radius_value = float(safe_get(source_circle, "Radius", fallback_radius))
    best_match = None
    best_delta = None

    for circle in iter_collection(circles):
        if circle is None:
            continue
        if expected_reference not in (None, "") and str(safe_get(circle, "Reference")) == str(expected_reference):
            return circle
        candidate_xc = float(safe_get(circle, "Xc", expected_xc))
        candidate_yc = float(safe_get(circle, "Yc", expected_yc))
        candidate_radius = float(safe_get(circle, "Radius", expected_radius_value))
        delta = (
            abs(candidate_xc - expected_xc)
            + abs(candidate_yc - expected_yc)
            + abs(candidate_radius - expected_radius_value)
        )
        if best_delta is None or delta < best_delta:
            best_match = circle
            best_delta = delta
        if delta <= tolerance:
            return circle
    return best_match or source_circle


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
        drawing_object = entity.get("object")
        point_index = _normalize_constraint_point_index(index)
        if point_index == 0:
            return (
                float(safe_get(drawing_object, "Xc", entity["xc"])),
                float(safe_get(drawing_object, "Yc", entity["yc"])),
            )
        if point_index == 1:
            return (
                float(safe_get(drawing_object, "X1", entity["x1"])),
                float(safe_get(drawing_object, "Y1", entity["y1"])),
            )
        if point_index == 2:
            return (
                float(safe_get(drawing_object, "X2", entity["x2"])),
                float(safe_get(drawing_object, "Y2", entity["y2"])),
            )
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
    if "radius" in line_entity and "xc" in line_entity and "yc" in line_entity:
        drawing_object = line_entity.get("object")
        xc = float(safe_get(drawing_object, "Xc", line_entity["xc"]))
        yc = float(safe_get(drawing_object, "Yc", line_entity["yc"]))
        radius = float(safe_get(drawing_object, "Radius", line_entity["radius"]))
        return abs(math.hypot(px - xc, py - yc) - radius)
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


def _apply_constraint_to_line(line, constraint_type, *, index=None, partner=None, partner_index=None, value=None, variable=None, expression=None):
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
    if expression not in (None, ""):
        constraint.Expression = str(expression)
    elif value is not None:
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
                    expression=plan.get("expression"),
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


def _add_circle_radius_dimension(radial_dimensions, dimension, sketch_entities):
    target = sketch_entities.get(str(dimension.get("target")))
    if target is None:
        raise RuntimeError("target_circle_not_found")
    circle_object = target.get("object")
    if circle_object is None:
        raise RuntimeError("target_circle_object_not_found")

    dim = radial_dimensions.Add()
    if dim is None:
        raise RuntimeError("RadialDimensions.Add returned None")

    try:
        dim.BaseObject = circle_object
    except Exception:
        set_base_object = safe_get(dim, "SetBaseObject")
        if callable(set_base_object):
            set_base_object(circle_object)
        else:
            raise

    dimension_type = bool(dimension.get("dimension_type", True))
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
        "orientation": "radius",
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
        radial_dimensions = safe_get(symbols_container, "RadialDimensions")
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
        if radial_dimensions is None:
            get_radial_dimensions = safe_get(symbols_container, "GetRadialDimensions")
            if callable(get_radial_dimensions):
                radial_dimensions = get_radial_dimensions()
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
                creation_mode = str(dimension_payload.get("creation_mode") or "").strip().lower()
                if creation_mode == "radial":
                    if radial_dimensions is None or not callable(safe_get(radial_dimensions, "Add")):
                        raise RuntimeError("view does not expose ISymbols2DContainer.RadialDimensions.Add")
                    result = _add_circle_radius_dimension(radial_dimensions, dimension_payload, sketch_entities)
                else:
                    if diametral_dimensions is None or not callable(safe_get(diametral_dimensions, "Add")):
                        raise RuntimeError("view does not expose ISymbols2DContainer.DiametralDimensions.Add")
                    result = _add_circle_diameter_dimension(diametral_dimensions, dimension_payload, sketch_entities)
            elif kind in {"circle_radius", "arc_radius"}:
                if radial_dimensions is None or not callable(safe_get(radial_dimensions, "Add")):
                    raise RuntimeError("view does not expose ISymbols2DContainer.RadialDimensions.Add")
                result = _add_circle_radius_dimension(radial_dimensions, dimension_payload, sketch_entities)
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

    created_variables = []
    for variable in planned_variables:
        try:
            name = str(variable.get("name") or "").strip()
            if not name:
                raise RuntimeError("variable_name_required")
            value = variable.get("value")
            initial_value = float(value) if value not in (None, "") else 0.0
            note = str(variable.get("note") or variable.get("comment") or variable.get("parameter_note") or "")
            created = add_variable(name, initial_value, note)
            if created is None:
                raise RuntimeError("AddVariable returned None")
            if variable.get("external") is not None:
                created.External = bool(variable.get("external"))
            created_variables.append((variable, created, name, initial_value, value, note))
        except Exception as exc:
            report["failed"].append({"variable": variable, "error": str(exc)})

    for variable, created, name, initial_value, value, note in created_variables:
        try:
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
                "note": safe_get(created, "ParameterNote", note),
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
    fallback_error = None
    if doc3 is None:
        try:
            import win32com.client

            app = win32com.client.DispatchEx("KOMPAS.Application.7")
            app.Visible = bool(visible)
            doc3 = app.Documents.Add(4, bool(visible))
        except Exception as exc:
            fallback_error = str(exc)
            doc3 = None
    if doc3 is None:
        raise RuntimeError("Documents.Add(ksDocumentPart) returned None; DispatchEx fallback error=%s" % fallback_error)
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


def _attempt_partial_generated_part_save(doc3, app, output_path, close_after_save, steps_report, visible=False):
    if doc3 is None or not output_path:
        return {
            "attempted": False,
            "saved": False,
            "output_path": output_path,
            "document": None,
            "error": "partial_save_unavailable",
        }
    try:
        saved, created_document = _save_generated_part_document(
            doc3,
            app,
            output_path,
            close_after_save,
            steps_report,
            visible=visible,
        )
        return {
            "attempted": True,
            "saved": bool(saved),
            "output_path": output_path,
            "document": created_document,
            "error": None,
        }
    except Exception as exc:
        return {
            "attempted": True,
            "saved": False,
            "output_path": output_path,
            "document": None,
            "error": str(exc),
        }


def _apply_saved_compression_spring_anchor_rotation_bindings(app, output_path, planned_bindings, steps_report):
    planned = [item for item in (planned_bindings or []) if item and item.get("expression") not in (None, "")]
    if not planned:
        return {"ok": True, "applied_count": 0, "bindings": []}

    document, attempts = _open_document_in_app(app, output_path, visible=False, read_only=False)
    if document is None:
        raise RuntimeError(
            "Failed to reopen saved compression spring for anchor rotation binding | attempts=%s"
            % json.dumps(attempts, ensure_ascii=False)
        )

    try:
        part = safe_get(document, "TopPart")
        if part is None:
            doc3_model = cast_document_3d(document)
            part = safe_get(doc3_model, "TopPart")
        if part is None:
            raise RuntimeError("Saved compression spring document does not expose TopPart")
        auxiliary_container = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
        if auxiliary_container is None:
            raise RuntimeError("Saved compression spring part does not expose IAuxiliaryGeomContainer")
        spirals = safe_get(auxiliary_container, "Spirals3D")
        if spirals is None:
            raise RuntimeError("Saved compression spring part does not expose Spirals3D")
        spiral_by_name = {}
        for spiral in iter_collection(spirals):
            spiral_name = str(safe_get(spiral, "Name", "") or "").strip()
            if spiral_name:
                spiral_by_name[spiral_name] = spiral

        report = {
            "step": "post_save_bind_spring_anchor_rotation",
            "scenario": "compression_spring",
            "ok": True,
            "applied_count": 0,
            "failed_count": 0,
            "bindings": [],
            "open_attempts": attempts,
        }
        for item in planned:
            path_name = str(item.get("path_name") or "").strip()
            spiral = spiral_by_name.get(path_name)
            if spiral is None:
                report["bindings"].append(
                    {
                        "role": item.get("role"),
                        "path_name": path_name,
                        "ok": False,
                        "error": "spiral_not_found_in_saved_document",
                    }
                )
                report["failed_count"] += 1
                continue
            binding_report = _bind_operation_variables(
                spiral,
                [_build_spring_anchor_rotation_binding(item.get("expression"))],
            )
            binding_report["role"] = item.get("role")
            binding_report["path_name"] = path_name
            binding_report["target"] = "spiral_path"
            report["bindings"].append(binding_report)
            if binding_report.get("ok", False):
                report["applied_count"] += 1
            else:
                report["failed_count"] += 1
        report["ok"] = report["failed_count"] == 0
        if not report["ok"]:
            bridge_path = get_short_path(os.path.abspath(__file__))
            child_payload = {
                "bridge_path": bridge_path,
                "output_path": get_short_path(output_path),
                "planned_bindings": planned,
            }
            child_script = r"""
import json, sys
payload = json.loads(sys.argv[1])
try:
    import importlib.util as importlib_util
except Exception:
    importlib_util = None
if importlib_util is not None and hasattr(importlib_util, "spec_from_file_location"):
    spec = importlib_util.spec_from_file_location("kompas_bridge_fresh_bind", payload["bridge_path"])
    bridge = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
else:
    import imp
    bridge = imp.load_source("kompas_bridge_fresh_bind", payload["bridge_path"])
app = bridge.make_app()
document, attempts = bridge._open_document_in_app(app, payload["output_path"], visible=False, read_only=False)
if document is None:
    raise RuntimeError("fresh_process_open_failed: %s" % json.dumps(attempts, ensure_ascii=False))
try:
    part = bridge.safe_get(document, "TopPart")
    if part is None:
        doc3_model = bridge.cast_document_3d(document)
        part = bridge.safe_get(doc3_model, "TopPart")
    auxiliary_container = bridge._cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    spirals = bridge.safe_get(auxiliary_container, "Spirals3D")
    spiral_by_name = {}
    for spiral in bridge.iter_collection(spirals):
        spiral_name = str(bridge.safe_get(spiral, "Name", "") or "").strip()
        if spiral_name:
            spiral_by_name[spiral_name] = spiral
    fresh_report = {"step": "post_save_bind_spring_anchor_rotation_fresh_process", "scenario": "compression_spring", "ok": True, "applied_count": 0, "failed_count": 0, "bindings": []}
    for item in payload["planned_bindings"]:
        path_name = str(item.get("path_name") or "").strip()
        spiral = spiral_by_name.get(path_name)
        if spiral is None:
            fresh_report["bindings"].append({"role": item.get("role"), "path_name": path_name, "ok": False, "error": "spiral_not_found_in_saved_document"})
            fresh_report["failed_count"] += 1
            continue
        binding_report = bridge._bind_operation_variables(spiral, [{"target": "spiral_path", "parameter_note": "Angle", "parameter_note_aliases": ["Angle", "Угол", "Rotation", "Rotation angle", "Angle of rotation", "Угол вращения", "Вращение"], "expression": str(item.get("expression")), "role": "spring_anchor_rotation"}])
        binding_report["role"] = item.get("role")
        binding_report["path_name"] = path_name
        binding_report["target"] = "spiral_path"
        fresh_report["bindings"].append(binding_report)
        if binding_report.get("ok", False):
            fresh_report["applied_count"] += 1
        else:
            fresh_report["failed_count"] += 1
    fresh_report["ok"] = fresh_report["failed_count"] == 0
    if not fresh_report["ok"]:
        raise RuntimeError(json.dumps(fresh_report, ensure_ascii=False))
    if not bool(document.Save()):
        raise RuntimeError("fresh_process_save_failed")
    print(json.dumps(fresh_report, ensure_ascii=False))
finally:
    try:
        document.Close(bridge.parse_close_mode(None))
    except Exception:
        pass
"""
            subprocess_module = __import__("subprocess")
            process = subprocess_module.Popen(
                [sys.executable, "-c", child_script, json.dumps(child_payload, ensure_ascii=False)],
                stdout=subprocess_module.PIPE,
                stderr=subprocess_module.PIPE,
                universal_newlines=True,
            )
            try:
                stdout_text, stderr_text = process.communicate(timeout=180)
            except TypeError:
                stdout_text, stderr_text = process.communicate()
            except subprocess_module.TimeoutExpired:
                process.kill()
                stdout_text, stderr_text = process.communicate()
                raise RuntimeError(
                    "Timed out while binding saved compression spring anchor rotation expressions"
                )
            if process.returncode != 0:
                raise RuntimeError(
                    "Failed to bind saved compression spring anchor rotation expressions: %s | fresh_process_stdout=%s | fresh_process_stderr=%s"
                    % (
                        json.dumps(report["bindings"], ensure_ascii=False),
                        (stdout_text or "").strip(),
                        (stderr_text or "").strip(),
                    )
                )
            fresh_report = json.loads((stdout_text or "").strip() or "{}")
            steps_report.append(fresh_report)
            return fresh_report
        save_ok = bool(document.Save())
        report["save_returned_false"] = not save_ok
        if not save_ok:
            verification = _verify_saved_compression_spring_anchor_rotation_bindings(
                app,
                output_path,
                planned,
            )
            report["save_verification"] = verification
            if not verification.get("ok", False):
                raise RuntimeError(
                    "Saved compression spring document Save() after anchor rotation binding returned False"
                )
        steps_report.append(report)
        return report
    finally:
        try:
            document.Close(parse_close_mode(None))
        except Exception:
            pass


def _verify_saved_compression_spring_anchor_rotation_bindings(app, output_path, planned_bindings):
    planned = [item for item in (planned_bindings or []) if item and item.get("expression") not in (None, "")]
    if not planned:
        return {"ok": True, "verified_count": 0, "failed_count": 0, "bindings": []}

    document, attempts = _open_document_in_app(app, output_path, visible=False, read_only=False)
    if document is None:
        return {
            "ok": False,
            "verified_count": 0,
            "failed_count": len(planned),
            "bindings": [],
            "open_attempts": attempts,
            "error": "verify_open_failed",
        }

    try:
        part = safe_get(document, "TopPart")
        if part is None:
            doc3_model = cast_document_3d(document)
            part = safe_get(doc3_model, "TopPart")
        auxiliary_container = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
        spirals = safe_get(auxiliary_container, "Spirals3D") if auxiliary_container is not None else None
        spiral_by_name = {}
        for spiral in iter_collection(spirals or []):
            spiral_name = str(safe_get(spiral, "Name", "") or "").strip()
            if spiral_name:
                spiral_by_name[spiral_name] = spiral
        aliases = set(SPRING_ANCHOR_ROTATION_PARAMETER_NOTES)
        report = {
            "ok": True,
            "verified_count": 0,
            "failed_count": 0,
            "bindings": [],
            "open_attempts": attempts,
        }
        for item in planned:
            path_name = str(item.get("path_name") or "").strip()
            spiral = spiral_by_name.get(path_name)
            if spiral is None:
                report["bindings"].append(
                    {
                        "role": item.get("role"),
                        "path_name": path_name,
                        "ok": False,
                        "error": "spiral_not_found_in_saved_document",
                    }
                )
                report["failed_count"] += 1
                continue
            expected_expression = str(item.get("expression") or "").strip()
            matched = None
            seen = []
            for variable in _iter_operation_variables(spiral):
                note = str(safe_get(variable, "ParameterNote", "") or "")
                if note not in aliases:
                    continue
                expression = str(safe_get(variable, "Expression", "") or "").strip()
                seen.append({"parameter_note": note, "expression": expression})
                if expression == expected_expression:
                    matched = {
                        "parameter_note": note,
                        "expression": expression,
                        "value": safe_get(variable, "Value"),
                    }
                    break
            if matched is None:
                report["bindings"].append(
                    {
                        "role": item.get("role"),
                        "path_name": path_name,
                        "ok": False,
                        "expected_expression": expected_expression,
                        "seen": seen,
                        "error": "expression_not_persisted",
                    }
                )
                report["failed_count"] += 1
                continue
            report["bindings"].append(
                {
                    "role": item.get("role"),
                    "path_name": path_name,
                    "ok": True,
                    "parameter_note": matched["parameter_note"],
                    "expression": matched["expression"],
                    "value": _json_safe_scalar(matched["value"]),
                }
            )
            report["verified_count"] += 1
        report["ok"] = report["failed_count"] == 0
        return report
    finally:
        try:
            document.Close(parse_close_mode(None))
        except Exception:
            pass


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
    return_report=False,
):
    report = {"distance_expression": distance_expression, "binding_report": None}
    point = _create_point3d(model_container, name, [0.0, 0.0, 0.0])
    point.ParameterType = 2
    parameters = _cast_to_com_interface(safe_get(point, "Parameters"), "IPoint3DParamDisplace")
    if parameters is None:
        raise RuntimeError("Point3D does not expose IPoint3DParamDisplace")
    if guiding_object is not None or distance is not None or (position_object is not None and distance_expression is not None):
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
    if distance_expression not in (None, ""):
        binding_report = _bind_operation_variables(
            point,
            [
                {
                    "parameter_note": "Distance",
                    "parameter_note_aliases": ["Distance", "Offset", "Length", "Расстояние", "Смещение", "Длина"],
                    "expression": str(distance_expression),
                    "role": "point3d_displace_distance",
                }
            ],
        )
        report["binding_report"] = binding_report
        if binding_report.get("ok"):
            update = safe_get(point, "Update")
            report["post_binding_update"] = bool(update()) if callable(update) else True
    return (point, report) if return_report else point


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


def _create_trimmed_curve_path(
    part,
    model_container,
    name,
    base_curve,
    point_name=None,
    offset=0.0,
    direction=True,
    offset_type=0,
    sense=True,
    point_variable_bindings=None,
):
    auxiliary_container = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    if auxiliary_container is None:
        raise RuntimeError("Part does not expose IAuxiliaryGeomContainer")
    try:
        point = _create_point3d_on_curve(
            model_container,
            point_name or ("%s_point" % name),
            base_curve,
            offset=offset,
            direction=direction,
            offset_type=offset_type,
        )
    except RuntimeError:
        if not point_variable_bindings:
            raise
        point = _create_point3d_on_curve(
            model_container,
            point_name or ("%s_point" % name),
            base_curve,
            offset=0.0,
            direction=direction,
            offset_type=offset_type,
        )
    point_binding_report = None
    if point_variable_bindings:
        point_binding_report = _bind_operation_variables(point, point_variable_bindings)
        if not point_binding_report.get("ok", False):
            raise RuntimeError("Failed to bind trimmed curve point variables for %s" % name)
        if not bool(point.Update()):
            raise RuntimeError("Failed to update trimmed curve point %s after variable binding" % name)
    trimmed_curves = safe_get(auxiliary_container, "TrimmedCurves")
    if trimmed_curves is None or not callable(safe_get(trimmed_curves, "Add")):
        raise RuntimeError("Auxiliary geometry container does not expose TrimmedCurves.Add")
    trimmed = trimmed_curves.Add()
    if trimmed is None:
        raise RuntimeError("TrimmedCurves.Add() returned None")
    try:
        trimmed.Name = name
    except Exception:
        pass
    trimmed.Curve = base_curve
    trimmed.CutObject1 = point
    try:
        trimmed.UseTwoCutObjecs = False
    except Exception:
        pass
    trimmed.Sense = bool(sense)
    if not bool(trimmed.Update()):
        if point_variable_bindings:
            return point, base_curve, {
                "ok": True,
                "fallback": "base_curve_after_trimmed_curve_update_false",
                "bindings": point_binding_report,
            }
        raise RuntimeError("Failed to create trimmed curve %s" % name)
    return point, trimmed, point_binding_report


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
    if not planned_variables:
        planned_variables = list(params.get("variable_plan") or [])
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
    pattern_binding_report = _bind_circular_pattern_operation_variables(pattern, params, "bolt_circle_holes")
    if pattern_binding_report is not None:
        steps_report.append(pattern_binding_report)
        if not pattern_binding_report.get("ok"):
            raise RuntimeError(
                "Failed to bind bolt_circle_holes circular pattern variables: %s"
                % (pattern_binding_report.get("failed"),)
            )
    steps_report.append(
        {
            "step": "circular_pattern",
            "ok": True,
            "api": "api7_feature_patterns_add",
            "count": int(params.get("count") or 0),
            "angle_step_degrees": 360.0 / float(params.get("count") or 1),
            "pattern_count_expression": params.get("pattern_count_expression"),
            "pattern_step_expression": params.get("pattern_step_expression"),
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


def _build_compression_spring_feature(part, model_container, params, preview, steps_report, coordinate_system=None, document=None):
    import win32com.client

    planned_variables = []
    for operation in (preview or {}).get("operations") or []:
        if operation.get("operation") == "add_variables":
            planned_variables = list(operation.get("variables") or [])
            break
    if planned_variables:
        steps_report.append(_apply_part_variables(part, planned_variables))

    placement = params.get("placement") or {}
    effective_origin = list(placement.get("effective_origin") or [0.0, 0.0])
    while len(effective_origin) < 2:
        effective_origin.append(0.0)
    spring_start_origin = [float(effective_origin[0]), float(effective_origin[1]), 0.0]
    spring_end_origin = [
        float(effective_origin[0]) + float(params.get("height") or 0.0),
        float(effective_origin[1]),
        0.0,
    ]
    spring_name = str(params.get("name") or "COMPRESSION_SPRING").strip() or "COMPRESSION_SPRING"
    start_point = _create_point3d(model_container, "%s_START" % spring_name, spring_start_origin)
    end_point = _create_point3d(model_container, "%s_END" % spring_name, spring_end_origin)
    axis = _create_axis3d_by_2_points(part, "%s_AXIS" % spring_name, start_point, end_point)
    steps_report.append(
        {
            "step": "create_spring_axis",
            "ok": True,
            "scenario": "compression_spring",
            "reference": safe_get(axis, "Reference"),
            "name": safe_get(axis, "Name"),
            "start_origin": spring_start_origin,
            "end_origin": spring_end_origin,
        }
    )

    mean_diameter = float(params.get("mean_diameter") or 0.0)
    spiral_diameter = float(params.get("spiral_diameter") or mean_diameter)
    wire_radius = float(params.get("wire_diameter") or 0.0) / 2.0
    profile_name = str(params.get("profile_name") or "spring_wire_profile").strip() or "spring_wire_profile"
    sweep_name = str(params.get("sweep_name") or "spring_body").strip() or "spring_body"
    sketch_plane, profile_lcs_rotation = _resolve_compression_spring_profile_sketch_frame(params)

    segment_plan = list(params.get("segment_plan") or [])
    if params.get("requires_side_specific_hook_builders"):
        hook_selection = dict(params.get("hook_selection") or {})
        raise RuntimeError(
            params.get("unsupported_mixed_hook_reason")
            or "Extension spring mixed hook types require side-specific hook builders: left=%s right=%s"
            % (hook_selection.get("left_hook_type") or params.get("left_hook_type"), hook_selection.get("right_hook_type") or params.get("right_hook_type"))
        )
    steps_report.append(
        {
            "step": "prepare_spring_segments",
            "ok": True,
            "scenario": "compression_spring",
            "segment_count": len(segment_plan),
            "segment_roles": [str((segment or {}).get("role") or "") for segment in segment_plan],
        }
    )
    path_verification = dict(params.get("path_verification") or {})
    if path_verification:
        steps_report.append(
            {
                "step": "verify_segment_phase_plan",
                "ok": bool(path_verification.get("contour_ready", False)),
                "scenario": "compression_spring",
                "joint_count": int(path_verification.get("joint_count") or 0),
                "max_joint_gap": float(path_verification.get("max_joint_gap") or 0.0),
                "max_joint_angle_gap": float(path_verification.get("max_joint_angle_gap") or 0.0),
            }
        )
        if not bool(path_verification.get("contour_ready", False)):
            raise RuntimeError("Compression spring segment phase plan is not contour-ready")

    base_profile_phase = float(segment_plan[0].get("phase_degrees") or 0.0) if segment_plan else 90.0
    phase_radians = math.radians(base_profile_phase)
    profile_path_offset = [
        0.0,
        (spiral_diameter / 2.0) * math.cos(phase_radians),
        (spiral_diameter / 2.0) * math.sin(phase_radians),
    ]
    explicit_profile_path_offset = params.get("profile_path_offset")
    if explicit_profile_path_offset not in (None, ""):
        profile_path_offset = list(explicit_profile_path_offset)
        while len(profile_path_offset) < 3:
            profile_path_offset.append(0.0)
        profile_path_offset = [float(value) for value in profile_path_offset[:3]]
    auxiliary_objects = [
        ("spring_axis_start_point", start_point),
        ("spring_axis_end_point", end_point),
        ("spring_axis", axis),
    ]
    segment_objects = []
    deferred_bent_coil_segments = []
    post_save_anchor_rotation_bindings = _build_post_save_compression_spring_anchor_rotation_bindings(
        segment_plan
    )
    auxiliary_container = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
    if auxiliary_container is None:
        raise RuntimeError("Part does not expose IAuxiliaryGeomContainer")
    evolutions = safe_get(model_container, "Evolutions")
    if evolutions is None:
        get_evolutions = safe_get(model_container, "GetEvolutions")
        if callable(get_evolutions):
            evolutions = get_evolutions()
    if evolutions is None or not callable(safe_get(evolutions, "Add")):
        raise RuntimeError("Part does not expose Evolutions.Add")
    steps_report.append(
        {
            "step": "resolve_spring_runtime_containers",
            "ok": True,
            "scenario": "compression_spring",
            "auxiliary_container_type": str(type(auxiliary_container)),
            "spirals_exposed": safe_get(auxiliary_container, "Spirals3D") is not None,
            "evolutions_type": str(type(evolutions)),
            "evolutions_add_available": callable(safe_get(evolutions, "Add")),
        }
    )

    for segment in segment_plan:
        segment_role = str(segment.get("role") or "segment")
        if segment_role in {"bent_coil_left", "bent_coil_right"}:
            deferred_bent_coil_segments.append(segment)
            steps_report.append(
                {
                    "step": "defer_bent_coil_spiral_segment",
                    "ok": True,
                    "scenario": "compression_spring",
                    "role": segment_role,
                    "reason": "requires_bent_coil_center_point_from_auxiliary_construction",
                }
            )
            continue
        segment_name = str(segment.get("label") or segment_role)
        extra_sketch_edges = []
        extra_sketch_edge_indices = []
        extra_sketch_path_names = []
        sketch_edge_points = []
        start_offset = float(segment.get("start_offset") or 0.0)
        center_start_point = segment.get("center_start_point")
        start_distance_expression_raw = segment.get("start_offset_expression")
        start_distance_expression = (
            str(start_distance_expression_raw).strip()
            if start_distance_expression_raw not in (None, "")
            else None
        )
        if center_start_point is not None:
            center_start_coordinates = [float(center_start_point[0]), float(center_start_point[1]), float(center_start_point[2] if len(center_start_point) > 2 else 0.0)]
            segment_start_point = _create_point3d(
                model_container,
                "%s_%s_START" % (spring_name, segment_role.upper()),
                center_start_coordinates,
            )
            auxiliary_objects.append(("segment_start_point", segment_start_point))
        elif start_distance_expression is None and abs(start_offset) <= 1e-9:
            segment_start_point = start_point
        else:
            segment_start_point = _create_point3d_displace(
                model_container,
                "%s_%s_START" % (spring_name, segment_role.upper()),
                start_point,
                [0.0, 0.0, 0.0],
                guiding_object=axis,
                distance=start_offset,
            )
            auxiliary_objects.append(("segment_start_point", segment_start_point))
            if start_distance_expression is not None:
                start_point_binding_report = _bind_operation_variables(
                    segment_start_point,
                    [
                        {
                            "target": "segment_start_point",
                            "parameter_note": "Distance",
                            "parameter_note_aliases": [
                                "Distance",
                                "Offset",
                                "Расстояние",
                            ],
                            "expression": start_distance_expression,
                            "role": "spring_segment_start_offset",
                        }
                    ],
                )
                start_point_binding_report["scenario"] = "compression_spring"
                start_point_binding_report["target"] = "segment_start_point"
                start_point_binding_report["role"] = segment_role
                steps_report.append(start_point_binding_report)
                if not start_point_binding_report.get("ok", False):
                    raise RuntimeError(
                        "Failed to bind compression spring segment start offset expression for %s"
                        % segment_role
                    )
        segment_start_origin = [
            float(safe_get(segment_start_point, "X", spring_start_origin[0]) or 0.0),
            float(safe_get(segment_start_point, "Y", spring_start_origin[1]) or 0.0),
            float(safe_get(segment_start_point, "Z", spring_start_origin[2]) or 0.0),
        ]
        segment_end_point = [float(value) for value in list(segment.get("end_point") or [])[:3]]
        steps_report.append(
            {
                "step": "create_segment_start_reference",
                "ok": True,
                "scenario": "compression_spring",
                "role": segment_role,
                "segment": segment_name,
                "reference": safe_get(segment_start_point, "Reference"),
                "origin": segment_start_origin,
                "start_offset": start_offset,
                "center_start_point": center_start_point,
                "start_offset_expression": start_distance_expression,
                "guiding_axis_reference": safe_get(axis, "Reference"),
            }
        )

        phase_degrees = float(segment.get("phase_degrees") or 0.0)
        turning_angle_value = segment.get("turning_angle_degrees")
        if turning_angle_value is None:
            turning_angle_degrees = math.fmod(phase_degrees, 360.0)
            if abs(turning_angle_degrees) <= 1e-9:
                turning_angle_degrees = 0.0
            if turning_angle_degrees < 0.0:
                turning_angle_degrees += 360.0
        else:
            turning_angle_degrees = float(turning_angle_value)
        orientation_angle_value = segment.get("orientation_angle_degrees")
        orientation_angle_degrees = float(orientation_angle_value) if orientation_angle_value is not None else 0.0
        anchor_rotation_expression_raw = segment.get("anchor_rotation_expression")
        anchor_rotation_expression = (
            str(anchor_rotation_expression_raw).strip()
            if anchor_rotation_expression_raw not in (None, "")
            else None
        )
        angle_application_mode = str(segment.get("angle_application_mode") or "orientation")
        segment_coordinate_system_rotation_degrees = 0.0
        segment_coordinate_system_rotation = dict(segment.get("coordinate_system_rotation") or {})
        if segment_coordinate_system_rotation:
            segment_coordinate_system_rotation = {
                "rx": float(segment_coordinate_system_rotation.get("rx", 90.0) or 0.0),
                "ry": float(segment_coordinate_system_rotation.get("ry", 90.0) or 0.0),
                "rz": float(segment_coordinate_system_rotation.get("rz", segment_coordinate_system_rotation_degrees) or 0.0),
            }
        else:
            segment_coordinate_system_rotation = {
                "rx": 90.0,
                "ry": 90.0,
                "rz": segment_coordinate_system_rotation_degrees,
            }
        segment_coordinate_system = _create_local_coordinate_system_on_point(
            part,
            "%s_%s_CS" % (spring_name, segment_role.upper()),
            segment_start_point,
            rotation=segment_coordinate_system_rotation,
        )
        auxiliary_objects.append(("segment_coordinate_system", segment_coordinate_system))
        steps_report.append(
            {
                "step": "create_segment_coordinate_system",
                "ok": True,
                "scenario": "compression_spring",
                "role": segment_role,
                "segment": segment_name,
                "reference": safe_get(segment_coordinate_system, "Reference"),
                "point_reference": safe_get(segment_start_point, "Reference"),
                "rotation_degrees": segment_coordinate_system_rotation_degrees,
                "rotation_expression": None,
                "requested_spiral_orientation_degrees": orientation_angle_degrees,
                "rotation_expression_target": "spiral_path_post_save" if anchor_rotation_expression is not None else None,
                "base_rotation": {"rx": segment_coordinate_system_rotation["rx"], "ry": segment_coordinate_system_rotation["ry"]},
                "coordinate_system_rotation": segment_coordinate_system_rotation,
            }
        )
        segment_path_type = str(segment.get("path_type") or "cylindric_spiral").strip().lower()
        position_parameters = None
        if segment_path_type == "line_segment":
            line_segments = safe_get(auxiliary_container, "LineSegments3D")
            if line_segments is None:
                raise RuntimeError("Auxiliary geometry container does not expose LineSegments3D")
            spiral = win32com.client.CastTo(line_segments.Add(), "ILineSegment3D")
            spiral_label = "LineSegment"
            if spiral is None:
                raise RuntimeError("LineSegments3D.Add() returned None")
            try:
                spiral.Name = str(segment.get("path_name") or ("%s_%s_PATH" % (spring_name, segment_role.upper())))
            except Exception:
                pass
            line_start = list(segment.get("start_point") or [0.0, 0.0, 0.0])
            line_end = list(segment.get("end_point") or [0.0, 0.0, 0.0])
            if not bool(spiral.SetPoint(True, float(line_start[0]), float(line_start[1]), float(line_start[2]))):
                raise RuntimeError("Line segment SetPoint(start) returned False")
            if not bool(spiral.SetPoint(False, float(line_end[0]), float(line_end[1]), float(line_end[2]))):
                raise RuntimeError("Line segment SetPoint(end) returned False")
        elif segment_path_type == "sketch_path":
            sketch_plan = dict(segment.get("sketch_path") or {})
            dynamic_plane = sketch_plan.get("dynamic_plane") or {}
            if dynamic_plane:
                axis_role = str(dynamic_plane.get("axis_segment_role") or "")
                point_role = str(dynamic_plane.get("point_segment_role") or "")
                axis_obj = None
                point_obj = None
                for obj in segment_objects:
                    if str(obj.get("role") or "") == axis_role:
                        axis_obj = obj.get("axis")
                    if str(obj.get("role") or "") == point_role:
                        start_pt = obj.get("start_point")
                        if dynamic_plane.get("anchor_point_vertex", "end") == "end":
                            point_path = obj.get("path")
                            if point_path is None:
                                raise RuntimeError("dynamic_plane end anchor requires a path object for role %s" % point_role)
                            point_obj = _create_point3d_on_curve(
                                model_container,
                                "%s_RIGHT_ANCHOR_POINT" % spring_name,
                                point_path,
                                offset=0.0,
                                direction=False,
                                offset_type=2,
                            )
                            auxiliary_objects.append(("right_anchor_point", point_obj))
                        else:
                            point_obj = start_pt
                if axis_obj is None or point_obj is None:
                    raise RuntimeError("dynamic_plane could not resolve axis/point for roles %s/%s" % (axis_role, point_role))
                sketch_plane = _create_plane_by_edge_and_point(
                    part,
                    str(dynamic_plane.get("plane_name") or ("%s_RIGHT_HOOK_PLANE" % spring_name)),
                    point_obj,
                    axis_obj,
                )
                auxiliary_objects.append(("right_hook_plane", sketch_plane))
            else:
                sketch_plane = str(sketch_plan.get("plane") or "XOY")
            self_wrapping_skip_sides = set(params.get("self_wrapping_sides") or (["left", "right"] if params.get("self_wrapping_hooks") else []))
            if params.get("self_wrapping_hooks") and (
                (segment_role == "left_hook" and "left" in self_wrapping_skip_sides)
                or (segment_role == "right_hook" and "right" in self_wrapping_skip_sides)
            ):
                steps_report.append(
                    {
                        "step": "skip_legacy_hook_sketch_for_self_wrapping",
                        "ok": True,
                        "role": segment_role,
                        "path_name": segment.get("path_name"),
                    }
                )
                continue
            sketch_name = str(segment.get("path_name") or ("%s_%s_SKETCH" % (spring_name, segment_role.upper())))
            sketch, _ = _create_sketch_on_plane(model_container, part, sketch_name, sketch_plane)
            if dynamic_plane and point_obj is not None and bool(dynamic_plane.get("assign_local_coordinate_system", True)):
                sketch_cs = _create_local_coordinate_system_on_point(part, "%s_SKETCH_LCS" % sketch_name, point_obj)
                auxiliary_objects.append(("sketch_cs", sketch_cs))
                _assign_model_object_coordinate_system(sketch, sketch_cs)
                sketch.Update()
            sketch_doc = sketch.BeginEdit()
            drawing_container = _get_sketch_drawing_container(sketch_doc)
            view = _get_sketch_system_view(sketch_doc)
            sketch_entities = {}
            entity_index = 0
            for entity_plan in list(sketch_plan.get("entities") or []):
                entity_plan = dict(entity_plan)
                entity_name = str(entity_plan.get("name") or ("entity_%d" % entity_index))
                entity_kind = str(entity_plan.get("kind") or "")
                entity_role = str(entity_plan.get("role") or entity_kind)
                entity_index += 1
                if entity_kind == "arc":
                    center = _normalize_point(entity_plan.get("center", [0, 0]))
                    radius = float(entity_plan.get("radius") or 1.0)
                    start = _normalize_point(entity_plan.get("start", [0, 0]))
                    end = _normalize_point(entity_plan.get("end", [0, 0]))
                    arc_entity = _add_sketch_arc(
                        drawing_container,
                        center,
                        radius,
                        start,
                        end,
                        entity_plan.get("direction", True),
                        int(entity_plan.get("style") or 1),
                    )
                    sketch_entities[entity_name] = _sketch_arc_entry(
                        arc_entity,
                        center[0], center[1], radius,
                        start[0], start[1],
                        end[0], end[1],
                        direction=entity_plan.get("direction", True),
                        role=entity_role,
                        target=entity_name,
                    )
                elif entity_kind in ("line", "segment"):
                    start = _normalize_point(entity_plan.get("start", [0, 0]))
                    end = _normalize_point(entity_plan.get("end", [0, 0]))
                    line_entity = _add_sketch_line_segment(
                        drawing_container,
                        start,
                        end,
                        int(entity_plan.get("style") or 1),
                    )
                    sketch_entities[entity_name] = _sketch_line_entry(
                        line_entity,
                        start[0], start[1],
                        end[0], end[1],
                        role=entity_role,
                        target=entity_name,
                    )
                else:
                    raise RuntimeError("Unknown sketch entity kind: %s" % entity_kind)
            sketch_param_plan = sketch_plan.get("parameterization") or {}
            if sketch_param_plan:
                sketch_param_report = _apply_sketch_parameterization(
                    view,
                    sketch_entities,
                    sketch_param_plan.get("constraints") or [],
                    sketch_param_plan.get("dimensions") or [],
                    sketch_param_plan.get("options") or {},
                    [],
                    0.0,
                )
                steps_report.append(sketch_param_report)
            sketch.EndEdit()
            if not bool(sketch.Update()):
                raise RuntimeError("Sketch %s Update() returned False" % sketch_name)
            edge_indices = [int(sketch_plan.get("edge_index", 1) or 1)]
            if sketch_plan.get("edge_indices"):
                edge_indices = [int(edge_index) for edge_index in list(sketch_plan.get("edge_indices") or [])]
            if sketch_plan.get("edge_tuple_indices"):
                tuple_edges = _get_sketch_edge_tuple(sketch, edge_indices[0])
                tuple_indices = [int(edge_index) for edge_index in list(sketch_plan.get("edge_tuple_indices") or [])]
                sketch_edges = [tuple_edges[tuple_index] if 0 <= tuple_index < len(tuple_edges) else None for tuple_index in tuple_indices]
                edge_indices = [edge_indices[0]] + [edge_indices[0]] * (len(sketch_edges) - 1)
            else:
                sketch_edges = [_get_sketch_edge(sketch, edge_index) for edge_index in edge_indices]
            spiral = sketch_edges[0]
            spiral_label = "SketchEdge"
            for edge_index, sketch_edge in zip(edge_indices, sketch_edges):
                if sketch_edge is None:
                    raise RuntimeError("Sketch %s Edges(%d) returned None" % (sketch_name, edge_index))
            extra_sketch_edges = sketch_edges[1:]
            extra_sketch_edge_indices = edge_indices[1:]
            extra_sketch_path_names = list(sketch_plan.get("path_names") or [])
            sketch_edge_points = list(sketch_plan.get("edge_points") or [])
            auxiliary_objects.append(("sketch_base", sketch))
        elif segment_path_type == "arc3d":
            arcs = safe_get(auxiliary_container, "Arcs3D")
            if arcs is None:
                raise RuntimeError("Auxiliary geometry container does not expose Arcs3D")
            spiral = win32com.client.CastTo(arcs.Add(), "IArc3D")
            spiral_label = "Arc3D"
            if spiral is None:
                raise RuntimeError("Arcs3D.Add() returned None")
            try:
                spiral.Name = str(segment.get("path_name") or ("%s_%s_PATH" % (spring_name, segment_role.upper())))
            except Exception:
                pass
            try:
                spiral.BuildingType = int(segment.get("building_type", 0) or 0)
            except Exception:
                pass
            arc_points = list(segment.get("points") or [])
            if len(arc_points) < 3:
                raise RuntimeError("arc3d segment requires three points")
            for point_index, point in enumerate(arc_points[:3], start=1):
                if not bool(spiral.SetPoint(point_index, float(point[0]), float(point[1]), float(point[2]))):
                    raise RuntimeError("Arc3D SetPoint(%d) returned False" % point_index)
            if "direction" in segment:
                spiral.Direction = bool(segment.get("direction"))
        elif segment_path_type == "law_curve":
            curve_plan = dict(segment.get("law_curve") or {})
            curve_laws = safe_get(auxiliary_container, "CurveByLaws")
            if curve_laws is None:
                raise RuntimeError("Auxiliary geometry container does not expose CurveByLaws")
            spiral = win32com.client.CastTo(curve_laws.Add(), "ICurveByLaw")
            spiral_label = "CurveByLaw"
            if spiral is None:
                raise RuntimeError("CurveByLaws.Add() returned None")
            try:
                spiral.Name = str(segment.get("path_name") or ("%s_%s_PATH" % (spring_name, segment_role.upper())))
            except Exception:
                pass
            law_expressions = [
                str(curve_plan.get("expression_x") or "0"),
                str(curve_plan.get("expression_y") or "0"),
                str(curve_plan.get("expression_z") or "0"),
            ]
            for expression_index, expression in enumerate(law_expressions):
                spiral.SetLawType(expression_index, 3)
                spiral.SetExpression(expression_index, expression)
            interval_expression = str(curve_plan.get("interval_expression") or "[0; 0]")
            for expression_index in range(3):
                spiral.SetIntervalExpression(expression_index, interval_expression)
        elif segment_path_type in ("conic_spiral", "conical_spiral"):
            spiral = win32com.client.CastTo(auxiliary_container.Spirals3D.Add(54), "IConicSpiral3D")
            spiral_label = "Conic"
        else:
            spiral = win32com.client.CastTo(auxiliary_container.Spirals3D.Add(56), "ICylindricSpiral3D")
            spiral_label = "Cylindric"
        if spiral is None:
            raise RuntimeError("Spirals3D.Add(%s spiral) returned None" % spiral_label)
        if segment_path_type not in ("law_curve", "line_segment", "arc3d", "sketch_path"):
            spiral_position = safe_get(spiral, "Position")
            if spiral_position is None:
                raise RuntimeError("Compression spring %s spiral does not expose Position" % spiral_label)
            spiral_position.ParameterType = 1
            spiral_position.OrientationType = 0
            if not bool(spiral_position.SetAssociationObject(segment_start_point)):
                raise RuntimeError("Compression spring spiral SetAssociationObject(point) returned False")
            position_parameters = win32com.client.CastTo(
                spiral_position.LocalCSParameters,
                "ILocalCSAxesDirectionParam",
            )
            if position_parameters is None:
                raise RuntimeError("Compression spring spiral does not expose ILocalCSAxesDirectionParam")
            position_parameters.LeadAxis = 73
            try:
                position_parameters.RotateAxis = 73
            except Exception:
                pass
            if not bool(position_parameters.SetDirectingObject(73, axis)):
                raise RuntimeError("Compression spring spiral SetDirectingObject(OZ, axis) returned False")
            if not bool(spiral_position.Update()):
                raise RuntimeError("Compression spring spiral position Update() returned False")
            spiral.CoordinateSystem = segment_coordinate_system
        if segment_path_type in ("conic_spiral", "conical_spiral"):
            start_diameter = float(segment.get("start_diameter") or spiral_diameter)
            end_diameter = float(segment.get("end_diameter") or spiral_diameter)
            spiral.DiameterType1 = 0
            spiral.Diameter1 = start_diameter
            spiral.DiameterType2 = 0
            spiral.Diameter2 = end_diameter
            try:
                segment_height = float(segment.get("height") or 0.0)
                if abs(segment_height) > 1e-9:
                    spiral.GeneratrixTiltAngle = math.degrees(math.atan(((end_diameter - start_diameter) / 2.0) / segment_height))
            except Exception:
                pass
        elif segment_path_type not in ("law_curve", "line_segment", "arc3d", "sketch_path"):
            spiral.DiameterType = 0
            spiral.Diameter = spiral_diameter
        if segment_path_type not in ("law_curve", "line_segment", "arc3d", "sketch_path"):
            spiral.BuildingType = 1
            spiral.Step = float(segment.get("pitch") or 0.0)
            spiral.Height = float(segment.get("height") or 0.0)
            spiral.BuildingDirection = True
            spiral.TurnDirection = not bool(params.get("left_hand", False))
        try:
            spiral.Name = str(segment.get("path_name") or ("%s_%s_PATH" % (spring_name, segment_role.upper())))
        except Exception:
            pass
        if segment_path_type in ("law_curve", "line_segment", "arc3d", "sketch_path"):
            turning_angle_report = {"mode": segment_path_type, "requested_degrees": None, "candidate_degrees": None}
            orientation_report = {"mode": segment_path_type, "requested_degrees": None, "candidate_degrees": None}
        else:
            turning_angle_report = _apply_spiral_turning_angle(
                spiral,
                position_parameters,
                0.0,
                "default",
            )
            orientation_report = _apply_spiral_turning_angle(
                spiral,
                position_parameters,
                0.0,
                "default",
            )
        if not bool(spiral.Update()):
            raise RuntimeError("Compression spring spiral Update() after angle setup returned False")
        spiral_variable_bindings = list(segment.get("operation_variable_bindings") or [])
        if anchor_rotation_expression is not None and segment_path_type not in ("law_curve", "line_segment", "arc3d"):
            spiral_variable_bindings.append(
                _build_spring_anchor_rotation_binding(anchor_rotation_expression)
            )
        spiral_binding_report = _bind_operation_variables(
            spiral,
            spiral_variable_bindings,
        )
        spiral_binding_report["scenario"] = "compression_spring"
        spiral_binding_report["target"] = "spiral_path"
        spiral_binding_report["role"] = segment_role
        try:
            spiral_binding_report["post_binding_update"] = bool(spiral.Update())
        except Exception as exc:
            spiral_binding_report["post_binding_update"] = False
            spiral_binding_report["post_binding_update_error"] = str(exc)
        steps_report.append(spiral_binding_report)
        geometry_report = _compute_curve_endpoint_report(
            spiral,
            expected_start=segment.get("start_point"),
            expected_end=segment.get("end_point"),
        )
        sampled_endpoints = _sample_curve_endpoints(spiral)
        steps_report.append(
            {
                "step": "create_spiral_path",
                "ok": True,
                "scenario": "compression_spring",
                "role": segment_role,
                "segment": segment_name,
                "reference": safe_get(spiral, "Reference"),
                "height": float(safe_get(spiral, "Height", 0.0) or 0.0),
                "pitch": float(safe_get(spiral, "Step", 0.0) or 0.0),
                "diameter": float(safe_get(spiral, "Diameter", 0.0) or 0.0),
                "direction": None if segment_path_type != "arc3d" else bool(safe_get(spiral, "Direction", False)),
                "angle1": None if segment_path_type != "arc3d" else float(safe_get(spiral, "Angle1", 0.0) or 0.0),
                "angle2": None if segment_path_type != "arc3d" else float(safe_get(spiral, "Angle2", 0.0) or 0.0),
                "turn_direction": bool(safe_get(spiral, "TurnDirection", False)),
                "phase_degrees": phase_degrees,
                "turning_angle_degrees": turning_angle_degrees,
                "orientation_angle_degrees": None if angle_application_mode == "default" else 0.0,
                "anchor_rotation_expression": anchor_rotation_expression,
                "coordinate_system_reference": safe_get(segment_coordinate_system, "Reference"),
                "coordinate_system_rotation_degrees": segment_coordinate_system_rotation_degrees,
                "coordinate_system_rotation": segment_coordinate_system_rotation,
                "turning_angle_applied_degrees": turning_angle_report.get(
                    "candidate_degrees",
                    turning_angle_report.get("requested_degrees"),
                ),
                "orientation_angle_applied_degrees": orientation_report.get(
                    "candidate_degrees",
                    orientation_report.get("requested_degrees"),
                ),
                "angle_application_mode": orientation_report.get("mode"),
                "geometry_checked": geometry_report.get("geometry_checked"),
                "geometry_ok": geometry_report.get("geometry_ok"),
                "start_gap": geometry_report.get("start_gap"),
                "end_gap": geometry_report.get("end_gap"),
                "start_offset": start_offset,
                "sampled_endpoints": sampled_endpoints,
                "expected_start": list(segment.get("start_point") or []),
                "expected_end": list(segment.get("end_point") or []),
            }
        )
        auxiliary_objects.append(("segment_spiral_path", spiral))
        primary_edge_points = sketch_edge_points[0] if segment_path_type == "sketch_path" and sketch_edge_points else None
        primary_logical_start_point = list((primary_edge_points or {}).get("start") or segment.get("start_point") or [])
        primary_logical_end_point = list((primary_edge_points or {}).get("end") or segment.get("end_point") or [])
        segment_objects.append(
            {
                "role": segment_role,
                "start_point": segment_start_point,
                "end_point": segment_end_point,
                "logical_start_point": primary_logical_start_point,
                "logical_end_point": primary_logical_end_point,
                "path": spiral,
                "axis": axis,
                "position_parameters": position_parameters,
                "angle_application_mode": angle_application_mode,
                "applied_orientation_angle": 0.0,
                "orientation_angle_candidates": [0.0],
                "segment": segment_name,
                "path_name": str(segment.get("path_name") or ""),
                "anchor_rotation_expression": anchor_rotation_expression,
                "coordinate_system": segment_coordinate_system,
            }
        )
        for extra_edge_position, extra_spiral in enumerate(extra_sketch_edges, start=1):
            extra_edge_index = extra_sketch_edge_indices[extra_edge_position - 1]
            extra_edge_points = sketch_edge_points[extra_edge_position] if extra_edge_position < len(sketch_edge_points) else {}
            if extra_edge_position < len(extra_sketch_path_names):
                extra_path_name = str(extra_sketch_path_names[extra_edge_position] or "")
            else:
                base_path_name = str(segment.get("path_name") or segment_name or segment_role or "sketch_path")
                extra_path_name = "%s_edge_%d" % (base_path_name, extra_edge_index)
            segment_objects.append(
                {
                    "role": segment_role,
                    "start_point": segment_start_point,
                    "end_point": segment_end_point,
                    "logical_start_point": list(extra_edge_points.get("start") or segment.get("start_point") or []),
                    "logical_end_point": list(extra_edge_points.get("end") or segment.get("end_point") or []),
                    "path": extra_spiral,
                    "axis": axis,
                    "position_parameters": dict(position_parameters or {}, sketch_edge_index=extra_edge_index),
                    "angle_application_mode": angle_application_mode,
                    "applied_orientation_angle": 0.0,
                    "orientation_angle_candidates": [0.0],
                    "segment": segment_name,
                    "path_name": extra_path_name,
                    "anchor_rotation_expression": anchor_rotation_expression,
                    "coordinate_system": segment_coordinate_system,
                }
            )

    prebuilt_connector_plan = []
    prebuilt_connector_objects = []
    self_wrapping_sides = set(params.get("self_wrapping_sides") or (["left", "right"] if params.get("self_wrapping_hooks") else []))
    early_self_wrapping_segment_objects = []
    early_self_wrapping_auxiliary_objects = []
    early_self_wrapping_left_for_right_bent = bool(params.get("self_wrapping_hooks")) and self_wrapping_sides == {"left"} and any(
        str(item.get("role") or "") == "bent_coil_right" for item in deferred_bent_coil_segments
    )
    if early_self_wrapping_left_for_right_bent and params.get("self_wrapping_hook_plan"):
        document_id = None
        if document is not None:
            try:
                document_id = describe_document(document, make_app()).get("id")
            except Exception:
                document_id = None
        early_self_wrapping_segment_objects, refreshed_auxiliary_container, early_self_wrapping_auxiliary_objects = _build_self_wrapping_left_hook_replacement(
            part,
            model_container,
            auxiliary_container,
            params,
            steps_report,
            document_id=document_id,
            document=document,
        )
        if refreshed_auxiliary_container is not None:
            auxiliary_container = refreshed_auxiliary_container
        auxiliary_objects.extend(early_self_wrapping_auxiliary_objects)
        segment_objects = [item for item in segment_objects if not str(item.get("role") or "") == "left_hook"]
        segment_objects.extend(early_self_wrapping_segment_objects)
    right_self_wrapping_needs_left_connector_source = bool(params.get("self_wrapping_hooks")) and "right" in self_wrapping_sides and "left" not in self_wrapping_sides
    right_bent_needs_left_connector_source = any(
        str(item.get("role") or "") == "bent_coil_right" for item in deferred_bent_coil_segments
    ) and any(str(item.get("role") or "") == "left_hook_to_body" for item in list(params.get("connector_plan") or []))
    if right_bent_needs_left_connector_source or right_self_wrapping_needs_left_connector_source:
        prebuilt_connector_plan = [
            connector
            for connector in list(params.get("connector_plan") or [])
            if str(connector.get("role") or "") == "left_hook_to_body"
            and any(str(item.get("path_name") or "") == str(connector.get("curve1_path_name") or "") for item in segment_objects)
        ]
        if prebuilt_connector_plan:
            prebuilt_connector_objects = _build_compression_spring_transition_curve_paths(
                part,
                model_container,
                auxiliary_container,
                spring_name,
                segment_objects,
                prebuilt_connector_plan,
                steps_report,
            )
            segment_objects.extend(prebuilt_connector_objects)
            auxiliary_objects.extend(_collect_compression_spring_connector_auxiliary_objects(prebuilt_connector_objects))
            params["connector_plan"] = [
                connector
                for connector in list(params.get("connector_plan") or [])
                if str(connector.get("role") or "") != "left_hook_to_body"
            ]

    if bool(params.get("bent_coil_auxiliary_construction")):
        try:
            body_segment = next((item for item in segment_objects if item.get("role") == "body"), None)
            if body_segment is None:
                raise RuntimeError("Body segment is required for bent-coil auxiliary construction")
            if prebuilt_connector_objects:
                connector_body_path_name = str((prebuilt_connector_plan[0] or {}).get("sequence_curve2_path_name") or "")
                body_segment = next(
                    (item for item in prebuilt_connector_objects if str(item.get("path_name") or "") == connector_body_path_name),
                    body_segment,
                )
            if early_self_wrapping_segment_objects:
                body_segment = next(
                    (item for item in early_self_wrapping_segment_objects if str(item.get("path_name") or "") == "self_wrapping_left_fillet1_edge1"),
                    body_segment,
                )
            bent_coil_plan = next(
                (item for item in deferred_bent_coil_segments if isinstance(item, dict)),
                {},
            )
            has_left_bent_coil_segment = any(
                str(item.get("role") or "") == "bent_coil_left" for item in deferred_bent_coil_segments
            )
            if not has_left_bent_coil_segment:
                raise StopIteration("skip_bent_coil_left_auxiliary_construction")
            body_start_point = _create_point3d_on_curve(
                model_container,
                "%s_BENT_COIL_BODY_START_POINT" % spring_name,
                body_segment["path"],
                direction=True,
                offset=0.0,
                offset_type=2,
            )
            auxiliary_objects.append(("bent_coil_body_start_point", body_start_point))
            auxiliary_objects.append(("bent_coil_left_base_point", body_start_point))
            body_start_plane = _create_plane_perpendicular_by_edge(
                auxiliary_container,
                "%s_BENT_COIL_BODY_START_PLANE" % spring_name,
                body_start_point,
                axis,
            )
            auxiliary_objects.append(("bent_coil_body_start_plane", body_start_plane))
            auxiliary_objects.append(("bent_coil_left_base_plane", body_start_plane))
            radius_value = float(params.get("mean_diameter", 0.0) or 0.0) / 2.0
            if radius_value <= 0.0:
                outer_value = float(params.get("outer_diameter", params.get("diameter", 0.0)) or 0.0)
                wire_value = float(params.get("wire_diameter", 0.0) or 0.0)
                radius_value = (outer_value - wire_value) / 2.0 if outer_value > 0.0 else 0.0
            bent_coil_radius_expression = str(bent_coil_plan.get("radius_expression") or "(D1 - WD1) / 2")
            sketchs = safe_get(model_container, "Sketchs")
            if sketchs is None:
                get_sketchs = safe_get(model_container, "GetSketchs")
                if callable(get_sketchs):
                    sketchs = get_sketchs()
            if sketchs is None or not callable(safe_get(sketchs, "Add")):
                raise RuntimeError("Part does not expose Sketchs.Add for bent-coil tangent sketch")
            tangent_sketch = sketchs.Add()
            tangent_sketch.Plane = body_start_plane
            tangent_sketch.CoordinateSystem = body_start_plane
            tangent_sketch.Name = "%s_BENT_COIL_TANGENT_SKETCH" % spring_name
            if not tangent_sketch.Update():
                raise RuntimeError("Bent-coil tangent sketch Update returned False")
            sketch_doc = tangent_sketch.BeginEdit()
            if sketch_doc is None:
                raise RuntimeError("Bent-coil tangent sketch BeginEdit returned None")
            tangent_line_entity = None
            try:
                views_manager = safe_get(sketch_doc, "ViewsAndLayersManager")
                if views_manager is None:
                    get_views_manager = safe_get(sketch_doc, "GetViewsAndLayersManager")
                    if callable(get_views_manager):
                        views_manager = get_views_manager()
                views = safe_get(views_manager, "Views") if views_manager is not None else None
                view = None
                if views is not None:
                    for accessor_name, accessor_arg in (("View", 0), ("Item", 0), ("View", 1), ("Item", 1)):
                        accessor = safe_get(views, accessor_name)
                        if callable(accessor):
                            try:
                                view = accessor(accessor_arg)
                                if view is not None:
                                    break
                            except Exception:
                                pass
                if view is None:
                    raise RuntimeError("Bent-coil tangent sketch view not found")
                drawing_container = cast_drawing_container(view)
                line_segments = safe_get(drawing_container, "LineSegments")
                if line_segments is None:
                    get_line_segments = safe_get(drawing_container, "GetLineSegments")
                    if callable(get_line_segments):
                        line_segments = get_line_segments()
                if line_segments is None or not callable(safe_get(line_segments, "Add")):
                    raise RuntimeError("Bent-coil tangent sketch LineSegments.Add unavailable")
                tangent_axis_flip = bool(params.get("bent_coil_tangent_axis_flip", False))
                tangent_line = line_segments.Add()
                tangent_line.X1 = 0.0
                tangent_line.Y1 = 0.0
                tangent_line.X2 = 0.0
                tangent_line.Y2 = -radius_value if tangent_axis_flip else radius_value
                tangent_line.Style = 3
                tangent_line.Update()
                tangent_line_entity = tangent_line
                tangent_axis_projection_constraints_report = _apply_center_axis_projection_constraints(
                    tangent_line_entity,
                    None,
                    length_expression=bent_coil_radius_expression,
                    length_value=radius_value,
                )
                try:
                    fixed_origin = _apply_constraint_to_line(tangent_line_entity, SKETCH_CONSTRAINT_TYPES["fixed_point"], index=0)
                    fixed_origin = dict(fixed_origin)
                    fixed_origin["kind"] = "fixed_point"
                    fixed_origin["index"] = 0
                    tangent_axis_projection_constraints_report["applied" if fixed_origin.get("created") else "failed"].append(fixed_origin)
                    tangent_axis_projection_constraints_report["created_count"] = len([item for item in tangent_axis_projection_constraints_report["applied"] if item.get("created")])
                except Exception as exc:
                    tangent_axis_projection_constraints_report["failed"].append({"kind": "fixed_point", "index": 0, "error": str(exc)})
                tangent_axis_projection_constraints_report["created_during_initial_edit"] = True
            finally:
                tangent_sketch.EndEdit()
            if not tangent_sketch.Update():
                raise RuntimeError("Bent-coil tangent sketch final Update returned False")
            tangent_point_projection_report, tangent_projected_point = _project_point_to_sketch_xy_with_object(tangent_sketch, body_start_point)
            if tangent_projected_point is not None:
                tangent_axis_projection_constraints_report["merge_after_projection"] = _apply_center_axis_projection_constraints(
                    tangent_line_entity,
                    tangent_projected_point,
                )
            if not tangent_axis_projection_constraints_report.get("created_count"):
                try:
                    tangent_sketch.BeginEdit()
                    tangent_axis_projection_constraints_report = _apply_center_axis_projection_constraints(
                        tangent_line_entity,
                        tangent_projected_point,
                        length_expression=bent_coil_radius_expression,
                        length_value=radius_value,
                    )
                    tangent_axis_projection_constraints_report["edit_retry"] = True
                finally:
                    tangent_sketch.EndEdit()
                    tangent_sketch.Update()
            auxiliary_objects.append(("bent_coil_tangent_sketch", tangent_sketch))
            if tangent_line_entity is None:
                raise RuntimeError("Bent-coil tangent sketch did not expose tangent line entity")
            tangent_axis_edges, tangent_axis_edge_index, tangent_axis_edge_attempts = _get_first_sketch_edge_tuple(tangent_sketch, (1, 2, 0))
            if not tangent_axis_edges:
                raise RuntimeError("Bent-coil tangent sketch did not expose axis edge; attempts=%s" % tangent_axis_edge_attempts)
            tangent_axis_edge = tangent_axis_edges[0]
            angle_axis_object = tangent_axis_edge
            angle_axis_report = {"source": "sketch_edge", "ok": True}
            if str(params.get("bent_coil_angle_axis_source", "sketch_edge") or "sketch_edge") == "axis_2points":
                try:
                    axis_2p_point = _create_point3d_displace(
                        model_container,
                        "%s_BENT_COIL_AXIS_2P_POINT" % spring_name,
                        body_start_point,
                        [0.0, 0.0, 0.0],
                        guiding_object=tangent_axis_edge,
                        distance=radius_value,
                    )
                    angle_axis_object = _create_axis3d_by_2_points(
                        part,
                        "%s_BENT_COIL_AXIS_2P" % spring_name,
                        body_start_point,
                        axis_2p_point,
                    )
                    auxiliary_objects.append(("bent_coil_axis_2p_point", axis_2p_point))
                    auxiliary_objects.append(("bent_coil_axis_2p", angle_axis_object))
                    angle_axis_report = {
                        "source": "axis_2points",
                        "ok": True,
                        "point_reference": safe_get(axis_2p_point, "Reference"),
                        "axis_reference": safe_get(angle_axis_object, "Reference"),
                    }
                except Exception as exc:
                    angle_axis_report = {"source": "axis_2points", "ok": False, "error": str(exc)}
            tangent_axis_touch_report = _touch_com_dependency_chain(
                ("tangent_sketch", tangent_sketch),
                ("tangent_axis_edge", tangent_axis_edge),
                ("angle_axis_object", angle_axis_object),
                ("body_start_plane", body_start_plane),
                ("part", part),
            )
            bent_coil_angle_variable_touch_report = _touch_named_variable_same_value(part, "BA1")
            bent_coil_angle_plane = None
            bent_coil_angle_plane_report = None
            bent_coil_angle_degrees_value = float(params.get("bent_coil_angle_degrees", 90.0) or 90.0)
            bent_coil_angle_expression = str(bent_coil_plan.get("angle_expression") or "BA1")
            try:
                bent_coil_angle_plane, bent_coil_angle_plane_report = _create_plane_by_angle(
                    part,
                    "%s_BENT_COIL_ANGLE_PLANE" % spring_name,
                    body_start_plane,
                    angle_axis_object,
                    bent_coil_angle_degrees_value,
                    direction=bool(params.get("bent_coil_angle_direction", False)),
                    axis_binding=str(params.get("bent_coil_angle_axis_binding", "all") or "all"),
                    angle_expression=bent_coil_angle_expression,
                )
                bent_coil_angle_plane_touch_report = _touch_angle_plane_same_value(
                    bent_coil_angle_plane,
                    bent_coil_angle_degrees_value,
                    angle_expression=bent_coil_angle_expression,
                )
                bent_coil_angle_plane_binding_report = _bind_operation_variables(
                    bent_coil_angle_plane,
                    [
                        {
                            "parameter_note": "Angle",
                            "parameter_note_aliases": ["Angle", "Угол", "BA1"],
                            "expression": bent_coil_angle_expression,
                            "role": "bent_coil_angle_plane_angle",
                        }
                    ],
                )
                auxiliary_objects.append(("bent_coil_angle_plane", bent_coil_angle_plane))
                auxiliary_objects.append(("bent_coil_left_angle_plane", bent_coil_angle_plane))
            except Exception as exc:
                bent_coil_angle_plane_report = {"ok": False, "error": str(exc)}
                bent_coil_angle_plane_touch_report = None
                bent_coil_angle_plane_binding_report = None
            bent_coil_center_sketch = None
            bent_coil_center_axis_edge = None
            bent_coil_center_point3d = None
            projection_api_probe = None
            center_point_projection_report = None
            center_axis_projection_constraints_report = None
            if bent_coil_angle_plane is not None:
                center_sketch = sketchs.Add()
                center_sketch.CoordinateSystem = bent_coil_angle_plane
                center_sketch.Plane = bent_coil_angle_plane
                # Backup: without this explicit origin, KOMPAS may place the sketch at the angle plane origin.
                # Hypothesis 1 anchors the center sketch at the spring body start point.
                center_sketch_origin_report = _assign_sketch_origin_point(center_sketch, body_start_point)
                center_sketch.Name = "%s_BENT_COIL_CENTER_SKETCH" % spring_name
                if not center_sketch.Update():
                    raise RuntimeError("Bent-coil center sketch Update returned False")
                center_doc = center_sketch.BeginEdit()
                if center_doc is None:
                    raise RuntimeError("Bent-coil center sketch BeginEdit returned None")
                try:
                    center_views_manager = safe_get(center_doc, "ViewsAndLayersManager")
                    if center_views_manager is None:
                        get_center_views_manager = safe_get(center_doc, "GetViewsAndLayersManager")
                        if callable(get_center_views_manager):
                            center_views_manager = get_center_views_manager()
                    center_views = safe_get(center_views_manager, "Views") if center_views_manager is not None else None
                    center_view = None
                    if center_views is not None:
                        for accessor_name, accessor_arg in (("View", 0), ("Item", 0), ("View", 1), ("Item", 1)):
                            accessor = safe_get(center_views, accessor_name)
                            if callable(accessor):
                                try:
                                    center_view = accessor(accessor_arg)
                                    if center_view is not None:
                                        break
                                except Exception:
                                    pass
                    if center_view is None:
                        raise RuntimeError("Bent-coil center sketch view not found")
                    center_drawing_container = cast_drawing_container(center_view)
                    projection_api_probe = _probe_projection_api(
                        ("center_sketch", center_sketch),
                        ("center_doc", center_doc),
                        ("center_view", center_view),
                        ("center_drawing_container", center_drawing_container),
                    )
                    center_point_projection_report, center_projected_point = _project_point_to_sketch_xy_with_object(center_sketch, body_start_point)
                    projected_xy = center_point_projection_report.get("xy") if center_point_projection_report else None
                    center_axis_x = float(projected_xy[0]) if projected_xy else 0.0
                    center_axis_y = float(projected_xy[1]) if projected_xy else 0.0
                    center_line_segments = safe_get(center_drawing_container, "LineSegments")
                    if center_line_segments is None:
                        get_center_line_segments = safe_get(center_drawing_container, "GetLineSegments")
                        if callable(get_center_line_segments):
                            center_line_segments = get_center_line_segments()
                    if center_line_segments is None or not callable(safe_get(center_line_segments, "Add")):
                        raise RuntimeError("Bent-coil center sketch LineSegments.Add unavailable")
                    center_axis_line = center_line_segments.Add()
                    center_axis_line.X1 = center_axis_x
                    center_axis_line.Y1 = center_axis_y
                    center_axis_line.X2 = center_axis_x
                    center_axis_line.Y2 = center_axis_y + radius_value
                    center_axis_line.Style = 3
                    center_axis_line.Update()
                    center_axis_projection_constraints_report = _apply_center_axis_projection_constraints(
                        center_axis_line,
                        center_projected_point,
                        length_expression=bent_coil_radius_expression,
                        length_value=radius_value,
                    )
                finally:
                    center_sketch.EndEdit()
                if not center_sketch.Update():
                    raise RuntimeError("Bent-coil center sketch final Update returned False")
                bent_coil_center_sketch = center_sketch
                auxiliary_objects.append(("bent_coil_center_sketch", bent_coil_center_sketch))
                center_axis_edges = _get_sketch_edge_tuple(center_sketch, 2)
                if not center_axis_edges:
                    raise RuntimeError("Bent-coil center sketch did not expose center axis edge at Edges(2)")
                bent_coil_center_axis_edge = center_axis_edges[0]
                bent_coil_center_point3d, bent_coil_center_point3d_report = _create_point3d_displace(
                    model_container,
                    "%s_BENT_COIL_CENTER_POINT" % spring_name,
                    body_start_point,
                    [0.0, 0.0, 0.0],
                    guiding_object=bent_coil_center_axis_edge,
                    distance=radius_value,
                    distance_expression=bent_coil_radius_expression,
                    return_report=True,
                )
                auxiliary_objects.append(("bent_coil_center_point3d", bent_coil_center_point3d))
                auxiliary_objects.append(("bent_coil_left_center_point3d", bent_coil_center_point3d))
            steps_report.append(
                {
                    "step": "create_bent_coil_auxiliary_construction",
                    "ok": True,
                    "body_start_point_reference": safe_get(body_start_point, "Reference"),
                    "body_start_plane_reference": safe_get(body_start_plane, "Reference"),
                    "tangent_sketch_reference": safe_get(tangent_sketch, "Reference"),
                    "tangent_sketch_coordinate_system": {
                        "assigned": True,
                        "reference": safe_get(body_start_plane, "Reference"),
                    },
                    "tangent_axis_line_2d": {
                        "x1": 0.0,
                        "y1": 0.0,
                        "x2": 0.0,
                        "y2": -radius_value if tangent_axis_flip else radius_value,
                        "edge_index": tangent_axis_edge_index,
                        "edge_attempts": tangent_axis_edge_attempts,
                        "construction_radial_line": False,
                        "local_axis": "Y",
                        "axis_flip": tangent_axis_flip,
                    },
                    "tangent_point_projection": tangent_point_projection_report,
                    "tangent_axis_projection_constraints": tangent_axis_projection_constraints_report,
                    "tangent_axis_touch_report": tangent_axis_touch_report,
                    "bent_coil_angle_variable_touch_report": bent_coil_angle_variable_touch_report,
                    "angle_axis_report": angle_axis_report,
                    "tangent_axis_edge_reference": safe_get(tangent_axis_edge, "Reference"),
                    "angle_plane_reference": safe_get(bent_coil_angle_plane, "Reference") if bent_coil_angle_plane is not None else None,
                    "angle_plane": bent_coil_angle_plane_report,
                    "angle_plane_touch_report": bent_coil_angle_plane_touch_report,
                    "angle_plane_binding_report": bent_coil_angle_plane_binding_report,
                    "center_sketch_reference": safe_get(bent_coil_center_sketch, "Reference") if bent_coil_center_sketch is not None else None,
                    "center_axis_edge_reference": safe_get(bent_coil_center_axis_edge, "Reference") if bent_coil_center_axis_edge is not None else None,
                    "center_point3d_reference": safe_get(bent_coil_center_point3d, "Reference") if bent_coil_center_point3d is not None else None,
                    "center_point3d_coordinates": [safe_get(bent_coil_center_point3d, "X"), safe_get(bent_coil_center_point3d, "Y"), safe_get(bent_coil_center_point3d, "Z")] if bent_coil_center_point3d is not None else None,
                    "center_point3d_report": bent_coil_center_point3d_report if bent_coil_center_point3d is not None else None,
                    "center_sketch_origin": center_sketch_origin_report if bent_coil_angle_plane is not None else None,
                    "projection_api_probe": projection_api_probe,
                    "center_point_projection": center_point_projection_report,
                    "center_axis_projection_constraints": center_axis_projection_constraints_report,
                    "center_axis_line_2d": {
                        "x1": center_axis_x if center_point_projection_report else None,
                        "y1": center_axis_y if center_point_projection_report else None,
                        "x2": center_axis_x if center_point_projection_report else None,
                        "y2": center_axis_y + radius_value if center_point_projection_report else None,
                        "anchored_to_projected_body_start": bool(center_point_projection_report and center_point_projection_report.get("ok")),
                        "length_expression": bent_coil_radius_expression,
                    },
                }
            )
        except Exception as exc:
            if isinstance(exc, StopIteration) and str(exc) == "skip_bent_coil_left_auxiliary_construction":
                steps_report.append(
                    {
                        "step": "skip_bent_coil_left_auxiliary_construction",
                        "ok": True,
                        "reason": "no_bent_coil_left_segment",
                    }
                )
            else:
                steps_report.append(
                    {
                        "step": "create_bent_coil_right_auxiliary_construction",
                        "ok": False,
                        "error": str(exc),
                    }
                )

        if any(str(item.get("role") or "") == "bent_coil_right" for item in deferred_bent_coil_segments):
            try:
                right_body_segment = body_segment
                if right_body_segment is None:
                    raise RuntimeError("Body segment is required for right bent-coil auxiliary construction")
                right_plan = next(
                    (item for item in list(params.get("segment_plan") or []) if isinstance(item, dict) and str(item.get("role") or "") == "bent_coil_right"),
                    {},
                )
                right_radius_expression = str(right_plan.get("radius_expression") or "(D1 - WD1) / 2")
                right_angle_expression = str(right_plan.get("angle_expression") or "BA1")
                right_radius_value = float(params.get("mean_diameter", 0.0) or 0.0) / 2.0
                if right_radius_value <= 0.0:
                    outer_value = float(params.get("outer_diameter", params.get("diameter", 0.0)) or 0.0)
                    wire_value = float(params.get("wire_diameter", 0.0) or 0.0)
                    right_radius_value = (outer_value - wire_value) / 2.0 if outer_value > 0.0 else 0.0
                right_base_point = _create_point3d_on_curve(
                    model_container,
                    "%s_BENT_COIL_RIGHT_BODY_END_POINT" % spring_name,
                    right_body_segment["path"],
                    direction=False,
                    offset=0.0,
                    offset_type=2,
                )
                auxiliary_objects.append(("bent_coil_right_base_point", right_base_point))
                right_base_plane = _create_plane_perpendicular_by_edge(
                    auxiliary_container,
                    "%s_BENT_COIL_RIGHT_BODY_END_PLANE" % spring_name,
                    right_base_point,
                    axis,
                )
                auxiliary_objects.append(("bent_coil_right_base_plane", right_base_plane))
                sketchs = safe_get(model_container, "Sketchs")
                if sketchs is None:
                    get_sketchs = safe_get(model_container, "GetSketchs")
                    if callable(get_sketchs):
                        sketchs = get_sketchs()
                if sketchs is None or not callable(safe_get(sketchs, "Add")):
                    raise RuntimeError("Part does not expose Sketchs.Add for right bent-coil tangent sketch")
                right_tangent_sketch = sketchs.Add()
                right_tangent_sketch.Plane = right_base_plane
                right_tangent_sketch.CoordinateSystem = right_base_plane
                right_tangent_sketch.Name = "%s_BENT_COIL_RIGHT_TANGENT_SKETCH" % spring_name
                if not right_tangent_sketch.Update():
                    raise RuntimeError("Right bent-coil tangent sketch Update returned False")
                right_sketch_doc = right_tangent_sketch.BeginEdit()
                if right_sketch_doc is None:
                    raise RuntimeError("Right bent-coil tangent sketch BeginEdit returned None")
                right_tangent_line_entity = None
                try:
                    views_manager = safe_get(right_sketch_doc, "ViewsAndLayersManager")
                    if views_manager is None:
                        get_views_manager = safe_get(right_sketch_doc, "GetViewsAndLayersManager")
                        if callable(get_views_manager):
                            views_manager = get_views_manager()
                    views = safe_get(views_manager, "Views") if views_manager is not None else None
                    view = None
                    if views is not None:
                        for accessor_name, accessor_arg in (("View", 0), ("Item", 0), ("View", 1), ("Item", 1)):
                            accessor = safe_get(views, accessor_name)
                            if callable(accessor):
                                try:
                                    view = accessor(accessor_arg)
                                    if view is not None:
                                        break
                                except Exception:
                                    pass
                    if view is None:
                        raise RuntimeError("Right bent-coil tangent sketch view not found")
                    drawing_container = cast_drawing_container(view)
                    line_segments = safe_get(drawing_container, "LineSegments")
                    if line_segments is None:
                        get_line_segments = safe_get(drawing_container, "GetLineSegments")
                        if callable(get_line_segments):
                            line_segments = get_line_segments()
                    if line_segments is None or not callable(safe_get(line_segments, "Add")):
                        raise RuntimeError("Right bent-coil tangent sketch LineSegments.Add unavailable")
                    right_tangent_axis_flip = bool(params.get("bent_coil_right_tangent_axis_flip", params.get("bent_coil_tangent_axis_flip", False)))
                    right_tangent_line = line_segments.Add()
                    right_tangent_line.X1 = 0.0
                    right_tangent_line.Y1 = 0.0
                    right_tangent_line.X2 = 0.0
                    right_tangent_line.Y2 = -right_radius_value if right_tangent_axis_flip else right_radius_value
                    right_tangent_line.Style = 3
                    right_tangent_line.Update()
                    right_tangent_line_entity = right_tangent_line
                    right_tangent_constraints_report = _apply_center_axis_projection_constraints(
                        right_tangent_line_entity,
                        None,
                        length_expression=right_radius_expression,
                        length_value=right_radius_value,
                    )
                    try:
                        fixed_origin = _apply_constraint_to_line(right_tangent_line_entity, SKETCH_CONSTRAINT_TYPES["fixed_point"], index=0)
                        fixed_origin = dict(fixed_origin)
                        fixed_origin["kind"] = "fixed_point"
                        fixed_origin["index"] = 0
                        right_tangent_constraints_report["applied" if fixed_origin.get("created") else "failed"].append(fixed_origin)
                        right_tangent_constraints_report["created_count"] = len([item for item in right_tangent_constraints_report["applied"] if item.get("created")])
                    except Exception as exc:
                        right_tangent_constraints_report["failed"].append({"kind": "fixed_point", "index": 0, "error": str(exc)})
                    right_tangent_constraints_report["created_during_initial_edit"] = True
                finally:
                    right_tangent_sketch.EndEdit()
                if not right_tangent_sketch.Update():
                    raise RuntimeError("Right bent-coil tangent sketch final Update returned False")
                auxiliary_objects.append(("bent_coil_right_tangent_sketch", right_tangent_sketch))
                right_tangent_edges = _get_sketch_edge_tuple(right_tangent_sketch, 2)
                if not right_tangent_edges:
                    raise RuntimeError("Right bent-coil tangent sketch did not expose tangent edge at Edges(2)")
                right_tangent_axis_edge = right_tangent_edges[0]
                right_angle_direction_param = str(right_plan.get("angle_direction_param") or "bent_coil_right_angle_direction")
                right_angle_plane, right_angle_plane_report = _create_plane_by_angle(
                    model_container,
                    "%s_BENT_COIL_RIGHT_ANGLE_PLANE" % spring_name,
                    right_tangent_sketch,
                    right_tangent_axis_edge,
                    float(params.get("bent_coil_angle_degrees", 90.0) or 90.0),
                    direction=bool(params.get(right_angle_direction_param, True)),
                    axis_binding=str(params.get("bent_coil_angle_axis_binding", "all") or "all"),
                    angle_expression=right_angle_expression,
                )
                right_angle_plane_touch_report = _touch_angle_plane_same_value(
                    right_angle_plane,
                    float(params.get("bent_coil_angle_degrees", 90.0) or 90.0),
                    angle_expression=right_angle_expression,
                )
                right_angle_plane_binding_report = _bind_operation_variables(
                    right_angle_plane,
                    [{"parameter_note": "Angle", "parameter_note_aliases": ["Angle", "Угол", "BA1"], "expression": right_angle_expression, "role": "bent_coil_right_angle_plane_angle"}],
                )
                auxiliary_objects.append(("bent_coil_right_angle_plane", right_angle_plane))
                right_center_sketch = sketchs.Add()
                right_center_sketch.CoordinateSystem = right_angle_plane
                right_center_sketch.Plane = right_angle_plane
                right_center_sketch.Name = "%s_BENT_COIL_RIGHT_CENTER_SKETCH" % spring_name
                if not right_center_sketch.Update():
                    raise RuntimeError("Right bent-coil center sketch Update returned False")
                right_center_projection_report, right_center_projected_point = _project_point_to_sketch_xy_with_object(right_center_sketch, right_base_point)
                right_center_projection_retry_report = None
                right_center_xy = (right_center_projection_report.get("point_xy") or right_center_projection_report.get("xy")) if isinstance(right_center_projection_report, dict) else None
                if right_center_xy is None:
                    right_center_xy = [0.0, 0.0]
                right_center_x = float(right_center_xy[0])
                right_center_y = float(right_center_xy[1])
                right_center_doc = right_center_sketch.BeginEdit()
                if right_center_doc is None:
                    raise RuntimeError("Right bent-coil center sketch BeginEdit returned None")
                try:
                    if right_center_projected_point is None:
                        right_center_projection_retry_report, right_center_projected_point = _project_point_to_sketch_xy_with_object(right_center_sketch, right_base_point)
                        retry_xy = (right_center_projection_retry_report.get("point_xy") or right_center_projection_retry_report.get("xy")) if isinstance(right_center_projection_retry_report, dict) else None
                        if retry_xy is not None:
                            right_center_x = float(retry_xy[0])
                            right_center_y = float(retry_xy[1])
                    views_manager = safe_get(right_center_doc, "ViewsAndLayersManager")
                    if views_manager is None:
                        get_views_manager = safe_get(right_center_doc, "GetViewsAndLayersManager")
                        if callable(get_views_manager):
                            views_manager = get_views_manager()
                    views = safe_get(views_manager, "Views") if views_manager is not None else None
                    view = None
                    if views is not None:
                        for accessor_name, accessor_arg in (("View", 0), ("Item", 0), ("View", 1), ("Item", 1)):
                            accessor = safe_get(views, accessor_name)
                            if callable(accessor):
                                try:
                                    view = accessor(accessor_arg)
                                    if view is not None:
                                        break
                                except Exception:
                                    pass
                    if view is None:
                        raise RuntimeError("Right bent-coil center sketch view not found")
                    drawing_container = cast_drawing_container(view)
                    line_segments = safe_get(drawing_container, "LineSegments")
                    if line_segments is None:
                        get_line_segments = safe_get(drawing_container, "GetLineSegments")
                        if callable(get_line_segments):
                            line_segments = get_line_segments()
                    if line_segments is None or not callable(safe_get(line_segments, "Add")):
                        raise RuntimeError("Right bent-coil center sketch LineSegments.Add unavailable")
                    right_center_axis_line = line_segments.Add()
                    right_center_axis_line.X1 = right_center_x
                    right_center_axis_line.Y1 = right_center_y
                    right_center_axis_line.X2 = right_center_x
                    right_center_axis_line.Y2 = right_center_y + right_radius_value
                    right_center_axis_line.Style = 3
                    right_center_axis_line.Update()
                    right_center_axis_constraints_report = _apply_center_axis_projection_constraints(
                        right_center_axis_line,
                        right_center_projected_point,
                        length_expression=right_radius_expression,
                        length_value=right_radius_value,
                    )
                finally:
                    right_center_sketch.EndEdit()
                if not right_center_sketch.Update():
                    raise RuntimeError("Right bent-coil center sketch final Update returned False")
                auxiliary_objects.append(("bent_coil_right_center_sketch", right_center_sketch))
                right_center_edges = _get_sketch_edge_tuple(right_center_sketch, 2)
                if not right_center_edges:
                    raise RuntimeError("Right bent-coil center sketch did not expose center edge at Edges(2)")
                right_center_axis_edge = right_center_edges[0]
                auxiliary_objects.append(("bent_coil_right_center_axis_edge", right_center_axis_edge))
                right_center_point3d, right_center_point3d_report = _create_point3d_displace(
                    model_container,
                    "%s_BENT_COIL_RIGHT_CENTER_POINT" % spring_name,
                    right_base_point,
                    [0.0, 0.0, 0.0],
                    guiding_object=right_center_axis_edge,
                    distance=right_radius_value,
                    distance_expression=right_radius_expression,
                    return_report=True,
                )
                auxiliary_objects.append(("bent_coil_right_center_point3d", right_center_point3d))
                steps_report.append(
                    {
                        "step": "create_bent_coil_right_auxiliary_construction",
                        "role": "bent_coil_right",
                        "ok": True,
                        "base_point_reference": safe_get(right_base_point, "Reference"),
                        "base_plane_reference": safe_get(right_base_plane, "Reference"),
                        "tangent_constraints": right_tangent_constraints_report,
                        "angle_plane": right_angle_plane_report,
                        "angle_plane_touch_report": right_angle_plane_touch_report,
                        "angle_plane_binding_report": right_angle_plane_binding_report,
                        "center_point_projection": right_center_projection_report,
                        "center_point_projection_retry": right_center_projection_retry_report,
                        "center_axis_projection_constraints": right_center_axis_constraints_report,
                        "center_point3d_reference": safe_get(right_center_point3d, "Reference"),
                        "center_point3d_report": right_center_point3d_report,
                    }
                )
            except Exception as exc:
                steps_report.append({"step": "create_bent_coil_right_auxiliary_construction", "role": "bent_coil_right", "ok": False, "error": str(exc)})

    for segment in deferred_bent_coil_segments:
        segment_role = str(segment.get("role") or "bent_coil_left")
        segment_side = "right" if segment_role == "bent_coil_right" else "left"
        segment_center_point3d = next(
            (obj for role, obj in auxiliary_objects if role == "bent_coil_%s_center_point3d" % segment_side),
            bent_coil_center_point3d if segment_side == "left" else None,
        )
        segment_center_axis_edge = next(
            (obj for role, obj in auxiliary_objects if role == "bent_coil_%s_center_axis_edge" % segment_side),
            bent_coil_center_axis_edge if segment_side == "left" else None,
        )
        segment_angle_plane = next(
            (obj for role, obj in auxiliary_objects if role == "bent_coil_%s_angle_plane" % segment_side),
            bent_coil_angle_plane if segment_side == "left" else None,
        )
        try:
            if segment_center_point3d is None or segment_angle_plane is None:
                raise RuntimeError("Bent-coil auxiliary center point/angle plane is not available")
            spiral = win32com.client.CastTo(auxiliary_container.Spirals3D.Add(56), "ICylindricSpiral3D")
            if spiral is None:
                raise RuntimeError("Bent-coil Spirals3D.Add(56) returned None")
            spiral.Name = str(segment.get("path_name") or "%s_BENT_COIL_LEFT_PATH" % spring_name)
            spiral_position = safe_get(spiral, "Position")
            if spiral_position is None:
                raise RuntimeError("Bent-coil spiral does not expose Position")
            spiral_position.ParameterType = 1
            spiral_position.OrientationType = 0
            if not bool(spiral_position.SetAssociationObject(segment_center_point3d)):
                raise RuntimeError("Bent-coil spiral SetAssociationObject(center point) returned False")
            raw_local_cs_parameters = safe_get(spiral_position, "LocalCSParameters")
            position_parameters = win32com.client.CastTo(raw_local_cs_parameters, "ILocalCSAxesDirectionParam")
            if position_parameters is None:
                raise RuntimeError("Bent-coil spiral does not expose ILocalCSAxesDirectionParam")
            position_parameters.LeadAxis = 73
            if not bool(position_parameters.SetDirectingObject(73, segment_angle_plane)):
                raise RuntimeError("Bent-coil spiral SetDirectingObject(OZ, angle plane) returned False")
            try:
                position_parameters.AngleByOwnAxis(73, 0.0)
                own_axis_angle_report = {"axis": 73, "angle": 0.0, "ok": True}
            except Exception as exc:
                own_axis_angle_report = {"axis": 73, "angle": 0.0, "ok": False, "error": str(exc)}
            if not bool(spiral_position.Update()):
                raise RuntimeError("Bent-coil spiral position Update() returned False")
            spiral.DiameterType = 0
            diameter_report = _set_com_property_expression_or_value(
                spiral,
                "Diameter",
                str(segment.get("diameter_expression") or "D1 - WD1"),
                float(segment.get("diameter") or outer_diameter),
            )
            spiral.BuildingType = 1
            step_report = _set_com_property_expression_or_value(
                spiral,
                "Step",
                str(segment.get("pitch_expression") or "P1"),
                float(segment.get("pitch") or pitch),
            )
            height_report = _set_com_property_expression_or_value(
                spiral,
                "Height",
                str(segment.get("height_expression") or "BH1"),
                float(segment.get("height") or 0.0),
            )
            turns_report = None
            for turns_attr in ("TurnCount", "Turns", "NumberOfTurns"):
                turns_report = _set_com_property_expression_or_value(
                    spiral,
                    turns_attr,
                    str(segment.get("turns_expression") or "BT1"),
                    float(segment.get("turns") or 0.0),
                )
                if turns_report.get("ok"):
                    break
            building_direction_param = str(segment.get("building_direction_param") or "bent_coil_building_direction")
            spiral.BuildingDirection = bool(params.get(building_direction_param, params.get("bent_coil_building_direction", False)))
            spiral.TurnDirection = not bool(params.get("left_hand", False))
            if not bool(spiral.Update()):
                raise RuntimeError("Bent-coil spiral Update() returned False")
            binding_report = _bind_operation_variables(spiral, list(segment.get("operation_variable_bindings") or []))
            binding_report["scenario"] = "compression_spring"
            binding_report["target"] = "bent_coil_spiral_path"
            binding_report["role"] = segment_role
            steps_report.append(binding_report)
            initial_angle_report = _set_operation_variable_value(
                spiral,
                parameter_note="Angle",
                parameter_note_aliases=["Angle", "Initial angle", "Start angle", "Угол", "BA1"],
                value=float(segment.get("initial_angle_degrees", 90.0)),
                role="bent_coil_initial_angle_fixed_value",
            )
            post_binding_update_report = _touch_com_dependency_chain(
                ("bent_coil_spiral", spiral),
                ("part", part),
            )
            steps_report.append(
                {
                    "step": "create_bent_coil_spiral_segment",
                    "ok": True,
                    "scenario": "compression_spring",
                    "role": segment_role,
                    "reference": safe_get(spiral, "Reference"),
                    "center_point_reference": safe_get(segment_center_point3d, "Reference"),
                    "center_axis_edge_reference": safe_get(segment_center_axis_edge, "Reference"),
                    "direction_object": "bent_coil_%s_angle_plane" % segment_side,
                    "height": float(safe_get(spiral, "Height", 0.0) or 0.0),
                    "pitch": float(safe_get(spiral, "Step", 0.0) or 0.0),
                    "diameter": float(safe_get(spiral, "Diameter", 0.0) or 0.0),
                    "building_direction": bool(safe_get(spiral, "BuildingDirection", False)),
                    "turn_direction": bool(safe_get(spiral, "TurnDirection", False)),
                    "positioning": {
                        "orientation_type": "axis_direction",
                        "orientation_type_value": safe_get(spiral_position, "OrientationType"),
                        "parameter_type_value": safe_get(spiral_position, "ParameterType"),
                        "lead_axis": str(safe_get(position_parameters, "LeadAxis")),
                        "direction_object": "angle_plane",
                        "own_axis_angle": own_axis_angle_report,
                    },
                    "parameterization": {
                        "diameter": diameter_report,
                        "step": step_report,
                        "height": height_report,
                        "turns": turns_report,
                        "initial_angle": {
                            "mode": "fixed_value",
                            "value": float(segment.get("initial_angle_degrees", 90.0)),
                            "property_report": initial_angle_report,
                        },
                    },
                    "post_binding_update_report": post_binding_update_report,
                    "operation_variable_snapshot": [
                        {
                            "name": safe_get(variable, "Name"),
                            "parameter_note": safe_get(variable, "ParameterNote", ""),
                            "expression": safe_get(variable, "Expression", ""),
                            "value": safe_get(variable, "Value", None),
                        }
                        for variable in _iter_operation_variables(spiral)
                    ],
                    "coordinate_system_reference": safe_get(segment_angle_plane, "Reference") if segment_angle_plane is not None else None,
                    "built_after_auxiliary": True,
                }
            )
            auxiliary_objects.append(("bent_coil_spiral_path", spiral))
            segment_objects.append(
                {
                    "role": segment_role,
                    "start_point": segment_center_point3d,
                    "end_point": segment_center_point3d,
                    "logical_start_point": list(segment.get("start_point") or []),
                    "logical_end_point": list(segment.get("end_point") or []),
                    "path": spiral,
                    "axis": segment_center_axis_edge,
                    "direction_object": segment_angle_plane,
                    "position_parameters": position_parameters,
                    "angle_application_mode": "initial_angle",
                    "applied_orientation_angle": 0.0,
                    "orientation_angle_candidates": [0.0],
                    "segment": str(segment.get("label") or segment_role),
                    "path_name": str(segment.get("path_name") or ""),
                    "coordinate_system": segment_angle_plane,
                }
            )
        except Exception as exc:
            steps_report.append(
                {
                    "step": "create_bent_coil_spiral_segment",
                    "ok": False,
                    "scenario": "compression_spring",
                    "role": segment_role,
                    "error": str(exc),
                }
            )

    deferred_left_connector_plan = [
        connector
        for connector in list(params.get("connector_plan") or [])
        if str(connector.get("role") or "") == "left_hook_to_body"
        and any(str(item.get("path_name") or "") == str(connector.get("curve1_path_name") or "") for item in segment_objects)
    ]
    if deferred_left_connector_plan and bool(params.get("self_wrapping_hooks")) and "right" in self_wrapping_sides:
        deferred_left_connector_objects = _build_compression_spring_transition_curve_paths(
            part,
            model_container,
            auxiliary_container,
            spring_name,
            segment_objects,
            deferred_left_connector_plan,
            steps_report,
        )
        segment_objects.extend(deferred_left_connector_objects)
        auxiliary_objects.extend(_collect_compression_spring_connector_auxiliary_objects(deferred_left_connector_objects))
        prebuilt_connector_plan.extend(deferred_left_connector_plan)
        prebuilt_connector_objects.extend(deferred_left_connector_objects)
        params["connector_plan"] = [
            connector
            for connector in list(params.get("connector_plan") or [])
            if str(connector.get("role") or "") != "left_hook_to_body"
        ]

    self_wrapping_segment_objects = list(early_self_wrapping_segment_objects)
    if params.get("self_wrapping_hooks") and params.get("self_wrapping_hook_plan"):
        self_wrapping_sides = set(params.get("self_wrapping_sides") or ["left", "right"])
        document_id = None
        if document is not None:
            try:
                document.Active = True
            except Exception:
                pass
            try:
                document_id = describe_document(document, make_app()).get("id")
            except Exception:
                document_id = None
        self_wrapping_auxiliary_objects = []
        if "left" in self_wrapping_sides and not early_self_wrapping_segment_objects:
            self_wrapping_segment_objects, refreshed_auxiliary_container, self_wrapping_auxiliary_objects = _build_self_wrapping_left_hook_replacement(part, model_container, auxiliary_container, params, steps_report, document_id=document_id, document=document)
            if refreshed_auxiliary_container is not None:
                auxiliary_container = refreshed_auxiliary_container
            auxiliary_objects.extend(self_wrapping_auxiliary_objects)
        right_body_curve_source = None
        for item in self_wrapping_segment_objects:
            if str(item.get("path_name") or "") == "self_wrapping_left_fillet1_edge1":
                right_body_curve_source = item.get("path")
                break
        explicit_right_body_source_path_name = str(params.get("self_wrapping_right_body_source_path_name") or "")
        if right_body_curve_source is None and explicit_right_body_source_path_name:
            for item in segment_objects:
                if str(item.get("path_name") or "") == explicit_right_body_source_path_name:
                    explicit_source_path = item.get("path")
                    explicit_source_edge = None
                    try:
                        explicit_source_edge = explicit_source_path.GetEdge() if explicit_source_path is not None else None
                    except Exception:
                        explicit_source_edge = None
                    right_body_curve_source = explicit_source_edge if _sample_curve_endpoints(explicit_source_edge) else explicit_source_path
                    break
        if right_body_curve_source is None and prebuilt_connector_objects:
            connector_body_path_name = str((prebuilt_connector_plan[0] or {}).get("sequence_curve2_path_name") or "")
            for item in prebuilt_connector_objects:
                if str(item.get("path_name") or "") == connector_body_path_name:
                    right_body_curve_source = item.get("path")
                    break
        if right_body_curve_source is None:
            left_bent_source_segment = next((item for item in segment_objects if item.get("role") == "bent_coil_left"), None)
            body_source_segment = next((item for item in segment_objects if item.get("role") == "body"), None)
            if left_bent_source_segment is not None and body_source_segment is not None:
                try:
                    handoff_contour, handoff_report = _build_curve_contour(
                        auxiliary_container,
                        "%s_BENT_TO_RIGHT_SELF_WRAPPING_HANDOFF_CONTOUR" % spring_name,
                        [left_bent_source_segment.get("path"), body_source_segment.get("path")],
                        allow_incomplete=True,
                        expected_edges_count=2,
                    )
                    handoff_edges = safe_get(handoff_contour, "Edges")
                    handoff_edge_count = collection_count(handoff_edges)
                    if handoff_edge_count:
                        right_body_curve_source = get_collection_item(handoff_edges, handoff_edge_count - 1)
                    else:
                        right_body_curve_source = handoff_contour
                    steps_report.append(
                        {
                            "step": "create_bent_to_right_self_wrapping_handoff_source",
                            "ok": right_body_curve_source is not None,
                            "contour": handoff_report,
                        }
                    )
                except Exception as exc:
                    steps_report.append(
                        {
                            "step": "create_bent_to_right_self_wrapping_handoff_source",
                            "ok": False,
                            "error": str(exc),
                        }
                    )
        if right_body_curve_source is None:
            body_source_segment = next((item for item in segment_objects if item.get("role") == "body"), None)
            if body_source_segment is not None:
                try:
                    body_edge_contour, body_edge_report = _build_curve_contour(
                        auxiliary_container,
                        "%s_RIGHT_SELF_WRAPPING_BODY_EDGE_SOURCE_CONTOUR" % spring_name,
                        [body_source_segment.get("path")],
                        allow_incomplete=False,
                        expected_edges_count=1,
                    )
                    body_edge_collection = safe_get(body_edge_contour, "Edges")
                    right_body_curve_source = get_collection_item(body_edge_collection, 0)
                    steps_report.append(
                        {
                            "step": "create_right_self_wrapping_body_edge_source",
                            "ok": right_body_curve_source is not None,
                            "contour": body_edge_report,
                        }
                    )
                except Exception as exc:
                    right_body_curve_source = body_source_segment.get("path")
                    steps_report.append(
                        {
                            "step": "create_right_self_wrapping_body_edge_source",
                            "ok": False,
                            "error": str(exc),
                        }
                    )
        right_self_wrapping_segment_objects = []
        right_self_wrapping_auxiliary_objects = []
        if "right" in self_wrapping_sides:
            right_self_wrapping_segment_objects, refreshed_auxiliary_container, right_self_wrapping_auxiliary_objects = _build_self_wrapping_right_hook_replacement(
                part,
                model_container,
                auxiliary_container,
                params,
                steps_report,
                document_id=document_id,
                document=document,
                body_curve_source=right_body_curve_source,
            )
            if refreshed_auxiliary_container is not None:
                auxiliary_container = refreshed_auxiliary_container
            auxiliary_objects.extend(right_self_wrapping_auxiliary_objects)
        remove_prefixes = []
        if "left" in self_wrapping_sides:
            remove_prefixes.append("left_hook")
        if "right" in self_wrapping_sides:
            remove_prefixes.append("right_hook")
        if remove_prefixes:
            segment_objects = [item for item in segment_objects if not str(item.get("role") or "").startswith(tuple(remove_prefixes))]
        segment_objects.extend(self_wrapping_segment_objects)
        segment_objects.extend(right_self_wrapping_segment_objects)
        steps_report.append(
            {
                "step": "self_wrapping_left_hook_replacement",
                "ok": True,
                "scenario": "extension_spring",
                "path_names": [item.get("path_name") for item in self_wrapping_segment_objects],
            }
        )
        steps_report.append(
            {
                "step": "self_wrapping_right_hook_replacement",
                "ok": True,
                "scenario": "extension_spring",
                "path_names": [item.get("path_name") for item in right_self_wrapping_segment_objects],
            }
        )
    if bool(params.get("construction_only")):
        steps_report.append(
            {
                "step": "construction_only_stop",
                "ok": True,
                "scenario": "compression_spring",
                "segment_count": len(segment_objects),
                "paths": [safe_get(item.get("path"), "Reference") for item in segment_objects],
            }
        )
        return {
            "body": None,
            "axis": axis,
            "spiral_path": segment_objects[0]["path"] if segment_objects else None,
            "path_contour": None,
            "segments": segment_objects,
            "connectors": [],
            "profile": None,
        }

    profile_anchor_plane = params.get("profile_anchor_plane") or {}
    early_path_contour_bundle = None
    profile_anchor_path_name_for_early_contour = str(profile_anchor_plane.get("path_name") or "")
    profile_anchor_needs_connector_path = bool(profile_anchor_path_name_for_early_contour) and not any(
        str(item.get("path_name") or "") == profile_anchor_path_name_for_early_contour
        for item in segment_objects
    )
    self_wrapping_requires_symmetric_early_bundle = bool(params.get("self_wrapping_hooks")) and set(
        params.get("self_wrapping_sides") or ["left", "right"]
    ) == {"left", "right"}
    if self_wrapping_requires_symmetric_early_bundle or profile_anchor_needs_connector_path:
        early_path_contour_bundle = _build_compression_spring_path_contour_with_connectors(
            part,
            model_container,
            auxiliary_container,
            spring_name,
            params,
            segment_objects,
            auxiliary_objects,
            steps_report,
        )

    profile_lcs = None
    profile_plane_object = sketch_plane
    profile_anchor_report = None
    if profile_anchor_plane:
        anchor_path_name = str(profile_anchor_plane.get("path_name") or "")
        anchor_segment = None
        profile_anchor_connector_objects = early_path_contour_bundle[1] if early_path_contour_bundle is not None else []
        for segment_object in list(segment_objects) + list(profile_anchor_connector_objects):
            if str(segment_object.get("path_name") or "") == anchor_path_name:
                anchor_segment = segment_object
                break
        if anchor_segment is None:
            raise RuntimeError("profile_anchor_plane path not found: %s" % anchor_path_name)
        anchor_vertex = str(profile_anchor_plane.get("vertex") or "start").lower()
        if anchor_vertex not in ("start", "end"):
            raise RuntimeError("profile_anchor_plane vertex must be start or end")
        profile_anchor_direction = anchor_vertex == "start"
        profile_anchor = _create_point3d_on_curve(
            model_container,
            "%s_PROFILE_ANCHOR_POINT" % spring_name,
            anchor_segment["path"],
            offset=0.0,
            direction=profile_anchor_direction,
            offset_type=2,
        )
        auxiliary_objects.append(("profile_anchor_point", profile_anchor))
        use_perpendicular_profile_plane = bool(profile_anchor_plane.get("use_perpendicular_plane", True))
        if use_perpendicular_profile_plane:
            profile_plane_object = _create_plane_perpendicular_by_edge(
                auxiliary_container,
                "%s_PROFILE_ANCHOR_PLANE" % spring_name,
                profile_anchor,
                anchor_segment["path"],
            )
            auxiliary_objects.append(("profile_anchor_plane", profile_plane_object))
        else:
            profile_lcs = _create_local_coordinate_system_on_point(
                part,
                "%s_PROFILE_LCS" % spring_name,
                profile_anchor,
                rotation=profile_lcs_rotation,
            )
            auxiliary_objects.append(("profile_lcs", profile_lcs))
        profile_anchor_report = {
            "path_name": anchor_path_name,
            "vertex": anchor_vertex,
            "point": [safe_get(profile_anchor, "X"), safe_get(profile_anchor, "Y"), safe_get(profile_anchor, "Z")],
            "plane_reference": safe_get(profile_plane_object, "Reference"),
            "use_perpendicular_plane": use_perpendicular_profile_plane,
        }
    else:
        profile_anchor = segment_objects[0]["start_point"] if segment_objects else start_point
        profile_lcs = _create_local_coordinate_system_on_point(
            part,
            "%s_PROFILE_LCS" % spring_name,
            profile_anchor,
            rotation=profile_lcs_rotation,
        )
        auxiliary_objects.append(("profile_lcs", profile_lcs))
    profile_sketch_center = params.get("profile_sketch_center")
    if profile_sketch_center is None:
        profile_center = [profile_path_offset[0], profile_path_offset[2]]
    else:
        profile_center = [float(profile_sketch_center[0]), float(profile_sketch_center[1])]
    if profile_anchor_plane:
        profile_seed_center = [float(profile_center[0]), float(profile_center[1])]
    else:
        profile_seed_offset = max(float(wire_radius) * 0.5, 1.0)
        profile_seed_center = [
            float(profile_center[0]) + profile_seed_offset,
            float(profile_center[1]) + profile_seed_offset,
        ]
    profile_sketch, profile_circle, _ = _create_sketch_circle_with_coordinate_system(
        model_container,
        part,
        profile_name,
        profile_plane_object,
        profile_seed_center,
        wire_radius,
        int(((params.get("sketch") or {}).get("profile_line_style")) or 1),
        coordinate_system=profile_lcs,
    )
    profile_circle_bindings = list(params.get("profile_circle_variable_bindings") or [])
    if profile_circle_bindings:
        profile_circle_binding_report = _bind_operation_variables(profile_circle, profile_circle_bindings)
        profile_circle_binding_report["step"] = "bind_operation_variables"
        profile_circle_binding_report["scenario"] = "compression_spring"
        profile_circle_binding_report["target"] = "profile_circle"
        try:
            profile_circle_binding_report["post_binding_update"] = bool(profile_circle.Update())
            profile_circle_binding_report["sketch_update_ok"] = bool(profile_sketch.Update())
        except Exception as exc:
            profile_circle_binding_report["post_binding_update"] = False
            profile_circle_binding_report["post_binding_update_error"] = str(exc)
        steps_report.append(profile_circle_binding_report)
    auxiliary_objects.append(("wire_profile_sketch", profile_sketch))
    steps_report.append(
        {
            "step": "create_wire_profile",
            "ok": True,
            "scenario": "compression_spring",
            "role": "full_path",
            "reference": safe_get(profile_sketch, "Reference"),
            "plane": sketch_plane if not profile_anchor_plane else safe_get(profile_plane_object, "Name", "profile_anchor_plane"),
            "profile_anchor_plane": profile_anchor_report,
            "radius": wire_radius,
            "coordinate_system_reference": safe_get(profile_lcs, "Reference") if profile_lcs is not None else None,
            "coordinate_system_rotation": dict(profile_lcs_rotation or {}),
            "center": profile_center,
            "center_offset_3d": profile_path_offset,
            "profile_sketch_target_state": str(params.get("profile_sketch_target_state") or "fully_defined"),
        }
    )
    _parameterize_compression_spring_profile_sketch(
        profile_sketch,
        profile_circle,
        profile_center,
        wire_radius,
        params,
        steps_report,
    )
    profile_lcs_bindings = list(params.get("profile_lcs_variable_bindings") or [])
    if profile_lcs_bindings:
        if profile_lcs is None:
            raise RuntimeError("profile_lcs_variable_bindings require a profile local coordinate system")
        profile_lcs_binding_report = _bind_operation_variables(profile_lcs, profile_lcs_bindings)
        profile_lcs_binding_report["step"] = "bind_operation_variables"
        profile_lcs_binding_report["scenario"] = "compression_spring"
        profile_lcs_binding_report["target"] = "profile_lcs"
        try:
            profile_lcs_binding_report["post_binding_update"] = bool(profile_lcs.Update())
            profile_lcs_binding_report["sketch_update_ok"] = bool(profile_sketch.Update())
        except Exception as exc:
            profile_lcs_binding_report["post_binding_update"] = False
            profile_lcs_binding_report["post_binding_update_error"] = str(exc)
        steps_report.append(profile_lcs_binding_report)

    if early_path_contour_bundle is not None:
        connector_plan, connector_objects, path_contour, contour_report, sweep_paths_for_report = early_path_contour_bundle
    else:
        connector_plan, connector_objects, path_contour, contour_report, sweep_paths_for_report = (
            _build_compression_spring_path_contour_with_connectors(
                part,
                model_container,
                auxiliary_container,
                spring_name,
                params,
                segment_objects,
                auxiliary_objects,
                steps_report,
            )
        )

    evolution = win32com.client.CastTo(evolutions.Add(46), "IEvolution")
    if evolution is None:
        raise RuntimeError("Evolutions.Add(o3d_bossEvolution) returned None")
    evolution.Sketch = profile_sketch
    evolution.Edges = path_contour
    sketch_shift_type_applied = False
    sketch_shift_type = params.get("evolution_sketch_shift_type", 2)
    if sketch_shift_type is not None:
        try:
            evolution.SketchShiftType = int(sketch_shift_type)
            sketch_shift_type_applied = True
        except Exception:
            pass
    by_surface_normal_applied = False
    by_surface_normal = params.get("evolution_by_surface_normal", True)
    if by_surface_normal is not None:
        try:
            evolution.BySurfaceNormal = bool(by_surface_normal)
            by_surface_normal_applied = True
        except Exception:
            pass
    try:
        evolution.Name = sweep_name
    except Exception:
        pass
    if not bool(evolution.Update()):
        raise RuntimeError("Failed to create compression_spring body")
    steps_report.append(
        {
            "step": "boss_evolution",
            "ok": True,
            "scenario": "compression_spring",
            "role": "full_path",
            "reference": safe_get(evolution, "Reference"),
            "model_object_type": safe_get(evolution, "ModelObjectType"),
            "operation_result": safe_get(evolution, "OperationResult"),
            "edge_count": len(sweep_paths_for_report),
            "path_contour_reference": safe_get(path_contour, "Reference"),
            "paths": [safe_get(path, "Reference") for path in sweep_paths_for_report],
            "profile": safe_get(profile_sketch, "Reference"),
            "sketch_shift_type": safe_get(evolution, "SketchShiftType"),
            "sketch_shift_type_applied": sketch_shift_type_applied,
            "by_surface_normal": safe_get(evolution, "BySurfaceNormal"),
            "by_surface_normal_applied": by_surface_normal_applied,
        }
    )
    params["_post_save_anchor_rotation_bindings"] = post_save_anchor_rotation_bindings

    if params.get("self_wrapping_hooks"):
        coordinate_system_rows = []
        coordinate_system_ok = True
        try:
            current_model = model_container
            current_auxiliary = auxiliary_container
            right_plane_name = "%s_RIGHT_HOOK_PLANE" % str(params.get("name") or spring_name or "EXTENSION_SPRING")
            right_sketch_coordinate_systems = [
                ("SELF_WRAPPING_RIGHT_FIRST_SKETCH", right_plane_name),
                ("SELF_WRAPPING_RIGHT_FIRST_SKETCH_PROJECTED", right_plane_name),
                ("SELF_WRAPPING_RIGHT_SECOND_SKETCH_PATH", "SELF_WRAPPING_RIGHT_AXIS_PERP_PLANE"),
            ]
            for sketch_name, plane_name in right_sketch_coordinate_systems:
                row = {"sketch": sketch_name, "plane": plane_name}
                try:
                    sketch = _find_sketch_by_name(current_model, sketch_name)
                    plane = _find_named_auxiliary_object(current_auxiliary, "Planes3D", plane_name)
                    if plane is None and str(plane_name).endswith("_RIGHT_HOOK_PLANE"):
                        planes = safe_get(current_auxiliary, "Planes3D")
                        for index in range(collection_count(planes)):
                            candidate = get_collection_item(planes, index)
                            if str(safe_get(candidate, "Name") or "").endswith("_RIGHT_HOOK_PLANE"):
                                plane = candidate
                                row["resolved_plane"] = safe_get(candidate, "Name")
                                break
                    sketch.CoordinateSystem = plane
                    row["ok"] = True
                    row["sketch_update_ok"] = bool(sketch.Update())
                    row["plane_reference"] = safe_get(plane, "Reference")
                    row["sketch_reference"] = safe_get(sketch, "Reference")
                except Exception as exc:
                    row["ok"] = False
                    row["error"] = str(exc)
                    coordinate_system_ok = False
                coordinate_system_rows.append(row)
            try:
                rebuild_after_cs = bool(part.Update())
            except Exception as exc:
                rebuild_after_cs = False
                coordinate_system_rows.append({"ok": False, "target": "part_update_after_coordinate_systems", "error": str(exc)})
        except Exception as exc:
            coordinate_system_ok = False
            rebuild_after_cs = False
            coordinate_system_rows.append({"ok": False, "error": str(exc)})
        steps_report.append(
            {
                "step": "self_wrapping_right_sketch_coordinate_systems",
                "ok": coordinate_system_ok,
                "scenario": "extension_spring",
                "timing": "post_body",
                "rebuild_after_coordinate_systems": rebuild_after_cs,
                "items": coordinate_system_rows,
            }
        )

    trim_report = _apply_compression_spring_ground_surface_sections(
        part,
        model_container,
        params,
        segment_objects,
        auxiliary_objects,
    )
    if trim_report is not None:
        steps_report.append(trim_report)

    if bool(params.get("auxiliary_geometry_hidden", True)):
        visibility_objects = auxiliary_objects
        if params.get("self_wrapping_hooks"):
            visibility_objects = [item for item in auxiliary_objects if item[0] != "segment_spiral_path"]
        visibility_report = _hide_auxiliary_model_objects(visibility_objects, True)
        step_report = {
            "step": "hide_spring_auxiliary_geometry",
            "scenario": "compression_spring",
        }
        step_report.update(visibility_report)
        steps_report.append(step_report)

    working_segment = None
    for item in segment_objects:
        role = str(item.get("role") or "")
        if role == "working" or role.startswith("working_"):
            working_segment = item
            break
    if working_segment is None and segment_objects:
        working_segment = segment_objects[0]
    return {
        "body": evolution,
        "axis": axis,
        "spiral_path": working_segment["path"] if working_segment is not None else None,
        "path_contour": path_contour,
        "segments": segment_objects,
        "connectors": [],
        "profile": profile_sketch,
    }


def _apply_compression_spring_ground_surface_sections(part, model_container, params, segment_objects, auxiliary_objects):
    trim_plan = (params or {}).get("ground_trim_plan") or {}
    if not trim_plan.get("enabled"):
        return None
    if str((params or {}).get("direction") or "Z").strip().upper() != "Z":
        return {
            "step": "compression_spring_ground_surface_section",
            "ok": False,
            "status": "unsupported_axis",
            "axis": (params or {}).get("direction") or "Z",
        }

    by_role = {str(entry.get("role") or ""): entry for entry in segment_objects or []}
    working_segments = [
        entry
        for entry in segment_objects or []
        if str(entry.get("role") or "") == "working"
        or str(entry.get("role") or "").startswith("working_")
    ]
    axis_object = (segment_objects or [{}])[0].get("axis") if segment_objects else None
    results = []
    for operation in list(trim_plan.get("operations") or []):
        role = str(operation.get("role") or "").strip()
        if role == "start_ground_trim":
            joint_source = working_segments[0] if working_segments else by_role.get("start_end")
            joint_point = (joint_source or {}).get("start_point")
            direction = True
        elif role == "finish_ground_trim":
            joint_source = by_role.get("finish_end")
            joint_point = (joint_source or {}).get("start_point")
            direction = False
        else:
            results.append({"role": role, "ok": False, "error": "unsupported_trim_role"})
            continue
        if joint_point is None:
            results.append({"role": role, "ok": False, "error": "missing_joint_point"})
            continue

        offset_expression = str(operation.get("offset_expression") or "0")
        trim_point = _create_point3d_displace(
            model_container,
            "%s_SECTION_POINT" % role.upper(),
            joint_point,
            [0.0, 0.0, 1.0],
            distance=0.0,
            guiding_object=axis_object,
        )
        trim_point_binding_report = _bind_operation_variables(
            trim_point,
            _build_distance_point_bindings(offset_expression, "%s_section_point_distance" % role),
        )
        if not trim_point_binding_report.get("ok", False):
            raise RuntimeError("Failed to bind trim point distance for %s" % role)
        auxiliary_objects.append(("%s_section_point" % role, trim_point))
        section_plane = _create_plane_perpendicular_by_edge(
            part,
            "%s_SECTION_PLANE" % role.upper(),
            trim_point,
            axis_object,
        )
        auxiliary_objects.append(("%s_section_plane" % role, section_plane))
        cut = _create_cut_by_surface(model_container, section_plane, direction=direction)
        results.append(
            {
                "role": role,
                "ok": True,
                "operation": "section_by_surface",
                "offset_expression": offset_expression,
                "direction": direction,
                "trim_point_reference": safe_get(trim_point, "Reference"),
                "trim_point_binding": trim_point_binding_report,
                "section_plane_reference": safe_get(section_plane, "Reference"),
                "cut_reference": safe_get(cut, "Reference"),
            }
        )

    return {
        "step": "compression_spring_ground_surface_section",
        "ok": all(item.get("ok") for item in results),
        "status": "executed" if all(item.get("ok") for item in results) else "partial_failure",
        "height_reference": trim_plan.get("height_reference"),
        "results": results,
    }


def _create_cut_by_surface(model_container, surface_object, *, direction):
    cuts = safe_get(model_container, "Cuts")
    if cuts is None:
        get_cuts = safe_get(model_container, "GetCuts")
        if callable(get_cuts):
            cuts = get_cuts()
    if cuts is None or not callable(safe_get(cuts, "Add")):
        raise RuntimeError("Part does not expose Cuts.Add")
    cut = cuts.Add()
    if cut is None:
        raise RuntimeError("Cuts.Add returned None")
    try:
        cut.BuildingType = 50
    except Exception:
        pass
    cut.CutObject = surface_object
    try:
        cut.Direction = bool(direction)
    except Exception:
        set_direction = safe_get(cut, "SetDirection")
        if callable(set_direction):
            set_direction(bool(direction))
    if not cut.Update():
        raise RuntimeError("Cut-by-surface Update returned False")
    return cut


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
    operation_binding_report = _bind_extrusion_operation_variables(
        extrusion,
        params,
        "internal_flat_step" if extrusion_type == 26 else "external_flat_step",
    )
    if operation_binding_report is not None:
        steps_report.append(operation_binding_report)
        if not operation_binding_report.get("ok"):
            raise RuntimeError("Failed to bind flat-step extrusion operation variables")
        depth_binding = "operation_variable"
        depth_value = operation_binding_report.get("applied", [{}])[0].get("expression_after", depth_value)
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
    operation_binding_report = _bind_extrusion_operation_variables(
        extrusion,
        params,
        "internal_polygonal_step" if extrusion_type == 26 else "external_polygonal_step",
    )
    if operation_binding_report is not None:
        steps_report.append(operation_binding_report)
        if not operation_binding_report.get("ok"):
            raise RuntimeError("Failed to bind polygonal-step extrusion operation variables")
        depth_binding = "operation_variable"
        depth_value = operation_binding_report.get("applied", [{}])[0].get("expression_after", depth_value)
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


def _create_plane_perpendicular_by_edge(part, name, point, edge):
    import win32com.client

    planes = safe_get(part, "Planes3D") or getattr(part, "Planes3D", None) or safe_get(part, "Planes") or getattr(part, "Planes", None)
    if planes is None:
        aux = _cast_to_com_interface(part, "IAuxiliaryGeomContainer")
        if aux is not None:
            planes = safe_get(aux, "Planes3D") or getattr(aux, "Planes3D", None) or safe_get(aux, "Planes") or getattr(aux, "Planes", None)
            if planes is None:
                get_planes = safe_get(aux, "GetPlanes3D")
                if callable(get_planes):
                    planes = get_planes()
    if planes is None:
        get_planes = safe_get(part, "GetPlanes3D")
        if callable(get_planes):
            planes = get_planes()
    if planes is None:
        try:
            aux_direct = win32com.client.CastTo(part, "IAuxiliaryGeomContainer")
            planes = safe_get(aux_direct, "Planes3D") or getattr(aux_direct, "Planes3D", None)
        except Exception:
            planes = None
    if planes is None:
        raise RuntimeError("Part does not expose Planes3D helper")
    plane = planes.Add(21)
    if plane is None:
        raise RuntimeError("Planes3D.Add(21) returned None")
    plane = win32com.client.CastTo(plane, "IPlane3DPerpendicularByEdge")
    if name:
        plane.Name = str(name)
    plane.Point = point
    plane.Edge = edge
    if not plane.Update():
        raise RuntimeError("IPlane3DPerpendicularByEdge Update returned False")
    return plane


def _get_planes3d_container(container):
    import win32com.client

    planes = safe_get(container, "Planes3D") or getattr(container, "Planes3D", None)
    if planes is None or not callable(getattr(planes, "Add", None)):
        aux = _cast_to_com_interface(container, "IAuxiliaryGeomContainer")
        if aux is not None:
            planes = safe_get(aux, "Planes3D") or getattr(aux, "Planes3D", None)
            if planes is None:
                get_planes = safe_get(aux, "GetPlanes3D")
                if callable(get_planes):
                    planes = get_planes()
    if planes is None or not callable(getattr(planes, "Add", None)):
        try:
            aux_direct = win32com.client.CastTo(container, "IAuxiliaryGeomContainer")
            planes = safe_get(aux_direct, "Planes3D") or getattr(aux_direct, "Planes3D", None)
        except Exception:
            planes = None
    if planes is None or not callable(getattr(planes, "Add", None)):
        raise RuntimeError("container does not expose Planes3D")
    return planes


def _create_plane_by_edge_and_plane(container, name, edge, reference_plane, *, parallel=False):
    import win32com.client

    if edge is None:
        raise RuntimeError("Plane by edge and plane requires edge")
    if reference_plane is None:
        raise RuntimeError("Plane by edge and plane requires reference plane")
    planes = _get_planes3d_container(container)
    plane = planes.Add(23)
    if plane is None:
        raise RuntimeError("Planes3D.Add(23) returned None")
    plane = win32com.client.CastTo(plane, "IPlane3DByEdgeAndPlane")
    if name:
        plane.Name = str(name)
    plane.Edge = edge
    plane.Plane = reference_plane
    plane.Parallel = bool(parallel)
    if not plane.Update():
        raise RuntimeError("IPlane3DByEdgeAndPlane Update returned False")
    return plane


def _create_plane_by_edge_and_point(container, name, point, edge):
    import win32com.client

    if point is None:
        raise RuntimeError("Plane by edge and point requires point")
    if edge is None:
        raise RuntimeError("Plane by edge and point requires edge")
    planes = safe_get(container, "Planes3D") or getattr(container, "Planes3D", None)
    if planes is None or not callable(getattr(planes, "Add", None)):
        aux = _cast_to_com_interface(container, "IAuxiliaryGeomContainer")
        if aux is not None:
            planes = safe_get(aux, "Planes3D") or getattr(aux, "Planes3D", None)
    if planes is None:
        raise RuntimeError("container does not expose Planes3D or Planes")
    plane = planes.Add(19)
    if plane is None:
        raise RuntimeError("Planes3D.Add(19) returned None")
    plane = win32com.client.CastTo(plane, "IPlane3DByEdgeAndPoint")
    if name:
        plane.Name = str(name)
    plane.Point = point
    plane.Edge = edge
    if not plane.Update():
        raise RuntimeError("IPlane3DByEdgeAndPoint Update returned False")
    return plane


def _create_plane_by_angle(part, name, base_plane, axis_edge, angle_degrees, direction=False, axis_binding="all", angle_expression=None):
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
        raise RuntimeError("Part does not expose Planes3D for angle plane")
    errors = []
    for code in (15, 17, 22, 23, 24, 18, 16):
        try:
            raw_plane = planes.Add(code)
        except Exception as exc:
            errors.append("Add(%s): %s" % (code, exc))
            continue
        for interface_name in (
            "IPlane3DByAngle",
            "IPlane3DAngle",
            "IPlane3DByAngleToPlane",
            "IPlane3DByAngleAndAxis",
            "IPlane3DByRotation",
        ):
            try:
                plane = win32com.client.CastTo(raw_plane, interface_name)
            except Exception as exc:
                errors.append("Add(%s) CastTo(%s): %s" % (code, interface_name, exc))
                continue
            try:
                if hasattr(plane, "Name"):
                    plane.Name = str(name or "")
                if callable(safe_get(plane, "SetPlane")):
                    plane.SetPlane(base_plane)
                elif hasattr(plane, "Plane"):
                    plane.Plane = base_plane
                elif hasattr(plane, "BasePlane"):
                    plane.BasePlane = base_plane
                elif callable(safe_get(plane, "SetBasePlane")):
                    plane.SetBasePlane(base_plane)
                axis_report = {"binding": axis_binding, "assigned": []}
                if axis_binding in ("all", "baseline_only") and hasattr(plane, "BaseLine"):
                    plane.BaseLine = axis_edge
                    axis_report["assigned"].append("BaseLine")
                if axis_binding in ("all", "no_baseline", "axis_only", "setaxis_only") and callable(safe_get(plane, "SetAxis")):
                    plane.SetAxis(axis_edge)
                    axis_report["assigned"].append("SetAxis")
                elif axis_binding in ("all", "no_baseline", "axis_only") and hasattr(plane, "Axis"):
                    plane.Axis = axis_edge
                    axis_report["assigned"].append("Axis")
                elif axis_binding in ("all", "no_baseline", "edge_only", "setedge_only") and callable(safe_get(plane, "SetEdge")):
                    plane.SetEdge(axis_edge)
                    axis_report["assigned"].append("SetEdge")
                elif axis_binding in ("all", "no_baseline", "edge_only") and hasattr(plane, "Edge"):
                    plane.Edge = axis_edge
                    axis_report["assigned"].append("Edge")
                if hasattr(plane, "Direction"):
                    plane.Direction = bool(direction)
                angle_report = {"ok": False, "attribute": None}
                if hasattr(plane, "Angle"):
                    angle_report = _set_com_property_expression_or_value(plane, "Angle", None, float(angle_degrees))
                elif hasattr(plane, "Value"):
                    angle_report = _set_com_property_expression_or_value(plane, "Value", None, float(angle_degrees))
                if plane.Update():
                    return plane, {
                        "code": code,
                        "interface": interface_name,
                        "angle_degrees": float(angle_degrees),
                        "angle_expression": angle_expression,
                        "angle_report": angle_report,
                        "direction": bool(direction),
                        "axis": axis_report,
                    }
                errors.append("Add(%s) CastTo(%s): Update returned False" % (code, interface_name))
            except Exception as exc:
                errors.append("Add(%s) CastTo(%s): %s" % (code, interface_name, exc))
    raise RuntimeError("Could not create angle plane: " + "; ".join(errors[-10:]))


def _create_axis_by_two_planes(part, name, plane1, plane2):
    import win32com.client

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
    axis = win32com.client.CastTo(axes.Add(9), "IAxis3DBy2Planes")
    axis.Plane1 = plane1
    axis.Plane2 = plane2
    axis.Name = name
    if not axis.Update():
        raise RuntimeError("IAxis3DBy2Planes Update returned False")
    return axis


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


def _assign_model_object_coordinate_system(model_object, coordinate_system):
    lcs_object = _cast_to_com_interface(model_object, "ILocalCSObject")
    if lcs_object is None:
        raise RuntimeError("Model object does not expose ILocalCSObject")
    lcs_object.CoordinateSystem = coordinate_system
    return safe_get(lcs_object, "LocalCoordinateSystem") or coordinate_system


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
    if scenario_name == "compression_spring":
        aliases = {
            "body": "body",
            "axis": "axis",
            "spiral": "spiral_path",
            "path": "spiral_path",
            "spiral_path": "spiral_path",
        }
        normalized = aliases.get(key, key)
        if normalized not in ("body", "axis", "spiral_path"):
            raise RuntimeError("Unsupported compression_spring output: %s" % output_key)
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

    if scenario in ("stepped_shaft", "external_conical_step", "internal_conical_step", "internal_cylindrical_step", "external_polygonal_step", "internal_polygonal_step", "external_flat_step", "internal_flat_step", "external_helical_thread", "internal_helical_thread", "external_threaded_step", "internal_threaded_step", "face_ring_groove", "bolt_circle_holes", "compression_spring", "conical_compression_spring", "torsion_spring", "extension_spring"):
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
        elif scenario in ("compression_spring", "compression_spring_variable_pitch", "conical_compression_spring", "torsion_spring", "extension_spring"):
            feature = _build_compression_spring_feature(
                part,
                model_container,
                params,
                preview,
                steps_report,
                coordinate_system=coordinate_system,
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
        if scenario == "compression_spring":
            current_stage = "post_save_anchor_rotation_bindings"
            _apply_saved_compression_spring_anchor_rotation_bindings(
                app,
                output_path,
                params.get("_post_save_anchor_rotation_bindings") or [],
                steps_report,
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
    if scenario not in ("stepped_shaft", "external_conical_step", "internal_conical_step", "internal_cylindrical_step", "external_polygonal_step", "internal_polygonal_step", "external_flat_step", "internal_flat_step", "external_helical_thread", "internal_helical_thread", "external_threaded_step", "internal_threaded_step", "face_ring_groove", "bolt_circle_holes", "compression_spring", "compression_spring_variable_pitch", "conical_compression_spring", "torsion_spring", "extension_spring"):
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
        doc3, _part_from_helper, _model_container_from_helper = _create_part_document(app, payload.get("visible", False))
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
        elif scenario in ("compression_spring", "compression_spring_variable_pitch", "conical_compression_spring", "torsion_spring", "extension_spring"):
            _build_compression_spring_feature(
                part,
                model_container,
                params,
                payload.get("preview") or {},
                steps_report,
                document=doc3,
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
        if scenario == "compression_spring":
            current_stage = "post_save_anchor_rotation_bindings"
            _apply_saved_compression_spring_anchor_rotation_bindings(
                app,
                output_path,
                params.get("_post_save_anchor_rotation_bindings") or [],
                steps_report,
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
        partial_save_report = None
        if material_settings is not None and material_settings_snapshot is not None:
            try:
                restore_new_part_document_settings(material_settings, material_settings_snapshot)
            except Exception:
                pass
        if params.get("save_partial_on_error"):
            partial_save_report = _attempt_partial_generated_part_save(
                doc3,
                app,
                output_path,
                close_after_save,
                steps_report,
                visible=bool(payload.get("visible", False)),
            )
            if params.get("return_partial_result_on_error") and partial_save_report.get("saved"):
                return {
                    "scenario": scenario,
                    "ok": False,
                    "partial": True,
                    "document": partial_save_report.get("document"),
                    "output_path": output_path,
                    "saved": True,
                    "closed": close_after_save,
                    "error": {
                        "stage": current_stage,
                        "message": str(exc),
                        "traceback": __import__("traceback").format_exc(),
                        "partial_save": partial_save_report,
                    },
                    "steps": steps_report,
                    "summary": {
                        "step_count": len(params.get("steps") or []),
                        "total_length": params.get("total_length"),
                        "operation_count": 1,
                    },
                    "remaining_documents": list_documents(app),
                    "file_access": file_access_diagnostics(output_path),
                }
        if close_after_save and not (partial_save_report and partial_save_report.get("saved")):
            try:
                _close_generated_document(doc3, app)
            except Exception:
                pass
        raise RuntimeError(
            "create_part_from_scenario failed at %s: %s | steps=%s | partial_save=%s"
            % (
                current_stage,
                exc,
                json.dumps(steps_report, ensure_ascii=False),
                json.dumps(partial_save_report, ensure_ascii=False),
            )
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
    if action == "launch_native_module_command":
        return handle_launch_native_module_command(payload)
    if action == "probe_native_entrypoint_loader_hosted":
        return handle_probe_native_entrypoint_loader_hosted(payload)
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
    if action == "project_sketch_edges":
        return handle_project_sketch_edges(payload)
    if action == "create_plane_by_edge_and_plane":
        return handle_create_plane_by_edge_and_plane(payload)
    if action == "create_self_wrapping_sketch2":
        return handle_create_self_wrapping_sketch2(payload)
    if action == "parameterize_sketch":
        return handle_parameterize_sketch(payload)
    if action == "list_sketches":
        return handle_list_sketches(payload)
    if action == "rename_sketch":
        return handle_rename_sketch(payload)
    if action == "set_sketch_entity_style":
        return handle_set_sketch_entity_style(payload)
    if action == "delete_sketch_entity":
        return handle_delete_sketch_entity(payload)
    if action == "update_sketch_entity_geometry":
        return handle_update_sketch_entity_geometry(payload)
    if action == "list_sketch_dimensions":
        return handle_list_sketch_dimensions(payload)
    if action == "inspect_sketch_dimension":
        return handle_inspect_sketch_dimension(payload)
    if action == "list_sketch_constraints":
        return handle_list_sketch_constraints(payload)
    if action == "inspect_sketch_constraint":
        return handle_inspect_sketch_constraint(payload)
    if action == "clear_sketch_entity_constraints":
        return handle_clear_sketch_entity_constraints(payload)
    if action == "repair_sketch":
        return handle_repair_sketch(payload)
    if action == "list_features":
        return handle_list_features(payload)
    if action == "inspect_feature":
        return handle_inspect_feature(payload)
    if action == "repair_feature":
        return handle_repair_feature(payload)
    if action == "list_sketch_entities":
        return handle_list_sketch_entities(payload)
    if action == "inspect_sketch_full":
        return handle_inspect_sketch_full(payload)
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
