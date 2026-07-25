from __future__ import annotations

import math
import re
from typing import Any


LINE_STYLES = {
    "hidden": -1,
    "invisible": 0,
    "normal": 1,
    "main": 1,
    "thin": 2,
    "axial": 3,
    "axis": 3,
    "dashed": 4,
    "construction": 6,
    "normal_dash_dot": 10,
}

PARAMETER_PREFIX_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def normalize_line_style(value: Any, *, default: str = "normal") -> int:
    if value is None or value == "":
        return LINE_STYLES[default]
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text in LINE_STYLES:
        return LINE_STYLES[text]
    try:
        return int(text)
    except Exception as exc:
        raise ValueError(f"Unknown sketch line style: {value}") from exc


def normalize_sketch_options(options: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = options or {}
    if not isinstance(payload, dict):
        raise ValueError("sketch must be an object")

    dimensions = payload.get("dimensions", True)
    constraints = payload.get("constraints", True)
    if isinstance(dimensions, dict):
        dimensions_enabled = bool(dimensions.get("enabled", True))
        driving_dimensions = bool(dimensions.get("driving", True))
    else:
        dimensions_enabled = bool(dimensions)
        driving_dimensions = True
    if isinstance(constraints, dict):
        constraints_enabled = bool(constraints.get("enabled", True))
        auto_constraints = bool(constraints.get("auto", True))
    else:
        constraints_enabled = bool(constraints)
        auto_constraints = True

    dimension_display = str(payload.get("dimension_display") or payload.get("display") or "radius").strip().lower()
    aliases = {
        "r": "radius",
        "radius": "radius",
        "radial": "radius",
        "d": "diameter",
        "diameter": "diameter",
        "diametral": "diameter",
    }
    dimension_display = aliases.get(dimension_display, dimension_display)
    if dimension_display not in ("radius", "diameter"):
        raise ValueError(f"Unsupported sketch dimension display mode: {dimension_display}")

    return {
        "axis_line_style": normalize_line_style(payload.get("axis_line_style"), default="axial"),
        "profile_line_style": normalize_line_style(payload.get("profile_line_style"), default="normal"),
        "parametric": bool(payload.get("parametric", True)),
        "dimension_display": dimension_display,
        "dimensions": {
            "enabled": dimensions_enabled,
            "driving": driving_dimensions,
        },
        "constraints": {
            "enabled": constraints_enabled,
            "auto": auto_constraints,
        },
    }


def _normalize_xy_pair(
    value: Any,
    field_name: str,
    *,
    default: tuple[float, float] = (0.0, 0.0),
) -> list[float]:
    payload = value
    if payload is None:
        payload = [default[0], default[1]]
    elif isinstance(payload, dict):
        payload = [payload.get("x", default[0]), payload.get("y", default[1])]
    if not isinstance(payload, (list, tuple)) or len(payload) != 2:
        raise ValueError(f"{field_name} must be [x, y]")
    try:
        return [float(payload[0]), float(payload[1])]
    except Exception as exc:
        raise ValueError(f"{field_name} must contain numeric values") from exc


def _normalize_placement_mode(value: Any, *, default: str = "global") -> str:
    mode = str(value or default).strip().lower().replace("-", "_")
    aliases = {
        "global": "global",
        "world": "global",
        "offset": "offset",
        "translated": "offset",
        "local": "offset",
        "csys": "csys",
        "lcs": "csys",
        "csys_ref": "csys_ref",
        "lcs_ref": "csys_ref",
        "reference_csys": "csys_ref",
    }
    normalized = aliases.get(mode, mode)
    if normalized not in ("global", "offset", "csys", "csys_ref"):
        raise ValueError(f"Unsupported placement mode: {normalized}")
    return normalized


def normalize_placement_options(options: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = options or {}
    if not isinstance(payload, dict):
        raise ValueError("placement must be an object")

    base_payload = payload.get("base")
    if base_payload is not None and not isinstance(base_payload, dict):
        raise ValueError("placement.base must be an object")

    legacy_mode = _normalize_placement_mode(payload.get("mode") or payload.get("type") or "global")
    base_mode = _normalize_placement_mode((base_payload or {}).get("mode") or legacy_mode)
    axis_direction = _normalize_xy_pair(
        (base_payload or {}).get("axis_direction") or (base_payload or {}).get("x_direction") or payload.get("axis_direction") or payload.get("x_direction"),
        "placement.axis_direction",
        default=(1.0, 0.0),
    )
    axis_dx, axis_dy = axis_direction
    if abs(axis_dx) < 1e-9 and abs(axis_dy) < 1e-9:
        raise ValueError("placement.axis_direction must not be a zero vector")

    base_name = str((base_payload or {}).get("name") or (base_payload or {}).get("csys_name") or payload.get("name") or payload.get("csys_name") or "")
    reference_payload = (base_payload or {}).get("reference") or (base_payload or {}).get("ref") or payload.get("reference") or payload.get("ref")
    if reference_payload is not None and not isinstance(reference_payload, dict):
        raise ValueError("placement.reference must be an object")
    reference = dict(reference_payload) if isinstance(reference_payload, dict) else None

    if base_payload is not None:
        base_origin = _normalize_xy_pair((base_payload or {}).get("origin") or (base_payload or {}).get("base_point"), "placement.base.origin")
        local_offset = _normalize_xy_pair(payload.get("local_offset") or payload.get("offset"), "placement.local_offset")
    elif legacy_mode == "offset":
        base_origin = [0.0, 0.0]
        local_offset = _normalize_xy_pair(payload.get("origin") or payload.get("base_point"), "placement.origin")
        base_mode = "global"
    else:
        base_origin = _normalize_xy_pair(payload.get("origin") or payload.get("base_point"), "placement.origin")
        local_offset = _normalize_xy_pair(payload.get("local_offset") or payload.get("offset"), "placement.local_offset")

    supports_rotation = abs(axis_dy) <= 1e-9 and axis_dx > 0.0
    if base_mode == "global":
        base_origin = [0.0, 0.0]
        axis_dx = 1.0
        axis_dy = 0.0
        supports_rotation = True

    effective_origin = [float(base_origin[0]) + float(local_offset[0]), float(base_origin[1]) + float(local_offset[1])]
    mode = base_mode
    if base_mode == "global" and (abs(float(local_offset[0])) > 1e-9 or abs(float(local_offset[1])) > 1e-9):
        mode = "offset"

    return {
        "mode": mode,
        "origin": effective_origin,
        "effective_origin": effective_origin,
        "base_origin": [float(base_origin[0]), float(base_origin[1])],
        "local_offset": [float(local_offset[0]), float(local_offset[1])],
        "axis_direction": [axis_dx, axis_dy],
        "name": base_name,
        "reference": reference,
        "rotation_supported": supports_rotation,
        "base": {
            "mode": base_mode,
            "origin": [float(base_origin[0]), float(base_origin[1])],
            "axis_direction": [axis_dx, axis_dy],
            "name": base_name,
            "reference": reference,
            "rotation_supported": supports_rotation,
        },
    }


def normalize_parameter_prefix(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("-", "_").replace(" ", "_")
    if not PARAMETER_PREFIX_PATTERN.fullmatch(text):
        raise ValueError("parameter_prefix must start with a letter and contain only letters, digits, or underscores")
    return text.upper()


def build_parameter_name(kind: str, index: int, *, prefix: str | None = None) -> str:
    base = f"{str(kind).upper()}{int(index)}"
    return f"{prefix}_{base}" if prefix else base


def build_operation_label(name: Any, *, parameter_prefix: str | None = None) -> str:
    operation_name = str(name or "Stepped shaft").strip() or "Stepped shaft"
    if parameter_prefix:
        return f"{operation_name} [{parameter_prefix}]"
    return operation_name


def build_parameter_note(
    operation_label: str,
    step_name: str,
    parameter_name: str,
    parameter_role: str,
) -> str:
    return f"{operation_label} | {step_name} | {parameter_role} {parameter_name}"


def apply_placement_to_points(
    profile_points: list[list[float]],
    placement: dict[str, Any] | None,
) -> list[list[float]]:
    normalized = placement or normalize_placement_options()
    origin_x, origin_y = float(normalized["effective_origin"][0]), float(normalized["effective_origin"][1])
    return [[float(point[0]) + origin_x, float(point[1]) + origin_y] for point in profile_points]


def _build_profile_segments(profile_points: list[list[float]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    axis_y = float(profile_points[0][1]) if profile_points else 0.0
    for index, (start, end) in enumerate(zip(profile_points, profile_points[1:]), start=1):
        x1, y1 = float(start[0]), float(start[1])
        x2, y2 = float(end[0]), float(end[1])
        skipped = x1 == x2 and y1 == y2 or (y1 == axis_y and y2 == axis_y)
        orientation = "other"
        if x1 == x2 and y1 != y2:
            orientation = "vertical"
        elif y1 == y2 and x1 != x2:
            orientation = "horizontal"
        segments.append(
            {
                "target": f"profile_line_{index}",
                "index": index,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "orientation": orientation,
                "skipped": skipped,
            }
        )
    return segments


def build_stepped_shaft_dimension_plan(
    steps: list[dict[str, Any]],
    profile_points: list[list[float]],
    *,
    parameter_prefix: str | None = None,
) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    axis_y = float(profile_points[0][1]) if profile_points else 0.0
    top_segments = [
        segment
        for segment in _build_profile_segments(profile_points)
        if segment["orientation"] == "horizontal" and float(segment["y1"]) != axis_y and not segment["skipped"]
    ]
    if len(top_segments) != len(steps):
        raise ValueError("failed to map stepped shaft dimensions to sketch segments")

    for index, (step, segment) in enumerate(zip(steps, top_segments, strict=True), start=1):
        length = float(step["length"])
        radius = float(step["radius"])
        length_name = build_parameter_name("L", index, prefix=parameter_prefix)
        sketch_length_name = build_parameter_name("SKL", index, prefix=parameter_prefix)
        radius_name = build_parameter_name("R", index, prefix=parameter_prefix)
        diameter_name = build_parameter_name("D", index, prefix=parameter_prefix)
        dimensions.append(
            {
                "kind": "line_length",
                "name": sketch_length_name,
                "variable": sketch_length_name,
                "expression": length_name,
                "source_variable": length_name,
                "orientation": "horizontal",
                "target": segment["target"],
                "value": length,
                "driving": True,
                "placement_index": index - 1,
            }
        )
        dimensions.append(
            {
                "kind": "axis_distance",
                "name": radius_name,
                "variable": radius_name,
                "expression": f"{diameter_name} / 2",
                "orientation": "vertical",
                "target": segment["target"],
                "point_x": float(segment["x1"]),
                "point_y": float(segment["y1"]),
                "value": radius,
                "driving": True,
                "placement_index": index - 1,
            }
        )
    return dimensions


def build_external_conical_step_dimension_plan(
    normalized: dict[str, Any],
    profile_points: list[list[float]],
    *,
    parameter_prefix: str | None = None,
) -> list[dict[str, Any]]:
    segments = [segment for segment in _build_profile_segments(profile_points) if not segment["skipped"]]
    if len(segments) != 3:
        raise ValueError("failed to map external conical step dimensions to sketch segments")

    start_segment, _, end_segment = segments
    length_name = build_parameter_name("L", 1, prefix=parameter_prefix)
    sketch_length_name = build_parameter_name("SKL", 1, prefix=parameter_prefix)
    start_radius_name = build_parameter_name("R", 1, prefix=parameter_prefix)
    end_radius_name = build_parameter_name("R", 2, prefix=parameter_prefix)
    start_diameter_name = build_parameter_name("D", 1, prefix=parameter_prefix)
    end_diameter_name = build_parameter_name("D", 2, prefix=parameter_prefix)

    return [
        {
            "kind": "circle_diameter",
            "name": sketch_length_name,
            "variable": sketch_length_name,
            "expression": length_name,
            "source_variable": length_name,
            "orientation": "horizontal",
            "target": "axis",
            "value": float(normalized["length"]),
            "driving": True,
            "placement_index": 0,
        },
        {
            "kind": "axis_distance",
            "name": start_radius_name,
            "variable": start_radius_name,
            "expression": f"{start_diameter_name} / 2",
            "orientation": "vertical",
            "target": start_segment["target"],
            "point_x": float(start_segment["x2"]),
            "point_y": float(start_segment["y2"]),
            "support_point_index": 1,
            "value": float(normalized["start_radius"]),
            "driving": True,
            "placement_index": 0,
        },
        {
            "kind": "axis_distance",
            "name": end_radius_name,
            "variable": end_radius_name,
            "expression": f"{end_diameter_name} / 2",
            "orientation": "vertical",
            "target": end_segment["target"],
            "point_x": float(end_segment["x1"]),
            "point_y": float(end_segment["y1"]),
            "support_point_index": 0,
            "value": float(normalized["end_radius"]),
            "driving": True,
            "placement_index": 1,
        },
    ]


def build_face_ring_groove_dimension_plan(
    normalized: dict[str, Any],
    profile_points: list[list[float]],
    *,
    parameter_prefix: str | None = None,
) -> list[dict[str, Any]]:
    segments = [segment for segment in _build_profile_segments(profile_points) if not segment["skipped"]]
    if len(segments) != 4:
        raise ValueError("failed to map face ring groove dimensions to sketch segments")

    top_segment, inner_wall_segment, bottom_segment, outer_wall_segment = segments
    depth_name = build_parameter_name("DEP", 1, prefix=parameter_prefix)
    sketch_depth_name = build_parameter_name("SKDEP", 1, prefix=parameter_prefix)
    inner_diameter_name = build_parameter_name("ID", 1, prefix=parameter_prefix)
    outer_diameter_name = build_parameter_name("OD", 1, prefix=parameter_prefix)
    bottom_inner_diameter_name = build_parameter_name("BID", 1, prefix=parameter_prefix)
    bottom_outer_diameter_name = build_parameter_name("BOD", 1, prefix=parameter_prefix)
    inner_radius_name = build_parameter_name("IR", 1, prefix=parameter_prefix)
    outer_radius_name = build_parameter_name("OR", 1, prefix=parameter_prefix)
    bottom_inner_radius_name = build_parameter_name("BIR", 1, prefix=parameter_prefix)
    bottom_outer_radius_name = build_parameter_name("BOR", 1, prefix=parameter_prefix)

    return [
        {
            "kind": "circle_diameter",
            "name": sketch_depth_name,
            "variable": sketch_depth_name,
            "expression": depth_name,
            "source_variable": depth_name,
            "orientation": "horizontal",
            "target": inner_wall_segment["target"],
            "value": float(normalized["depth"]),
            "driving": True,
            "placement_index": 0,
        },
        {
            "kind": "axis_distance",
            "name": outer_radius_name,
            "variable": outer_radius_name,
            "expression": f"{outer_diameter_name} / 2",
            "orientation": "vertical",
            "target": top_segment["target"],
            "point_x": float(top_segment["x1"]),
            "point_y": float(top_segment["y1"]),
            "support_point_index": 0,
            "value": float(normalized["outer_radius"]),
            "driving": True,
            "placement_index": 0,
        },
        {
            "kind": "axis_distance",
            "name": inner_radius_name,
            "variable": inner_radius_name,
            "expression": f"{inner_diameter_name} / 2",
            "orientation": "vertical",
            "target": top_segment["target"],
            "point_x": float(top_segment["x2"]),
            "point_y": float(top_segment["y2"]),
            "support_point_index": 1,
            "value": float(normalized["inner_radius"]),
            "driving": True,
            "placement_index": 1,
        },
        {
            "kind": "axis_distance",
            "name": bottom_inner_radius_name,
            "variable": bottom_inner_radius_name,
            "expression": f"{bottom_inner_diameter_name} / 2",
            "orientation": "vertical",
            "target": bottom_segment["target"],
            "point_x": float(bottom_segment["x1"]),
            "point_y": float(bottom_segment["y1"]),
            "support_point_index": 0,
            "value": float(normalized["bottom_inner_radius"]),
            "driving": True,
            "placement_index": 2,
        },
        {
            "kind": "axis_distance",
            "name": bottom_outer_radius_name,
            "variable": bottom_outer_radius_name,
            "expression": f"{bottom_outer_diameter_name} / 2",
            "orientation": "vertical",
            "target": bottom_segment["target"],
            "point_x": float(bottom_segment["x2"]),
            "point_y": float(bottom_segment["y2"]),
            "support_point_index": 1,
            "value": float(normalized["bottom_outer_radius"]),
            "driving": True,
            "placement_index": 3,
        },
    ]


def apply_dimension_display_mode(
    dimensions: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    *,
    mode: str = "radius",
) -> list[dict[str, Any]]:
    display_mode = str(mode or "radius").strip().lower()
    if display_mode == "radius":
        return dimensions

    remapped: list[dict[str, Any]] = []
    radial_index = 0
    for dimension in dimensions:
        item = dict(dimension)
        if item.get("kind") != "axis_distance":
            remapped.append(item)
            continue
        step = steps[radial_index]
        radial_index += 1
        item["display_mode"] = "diameter"
        item["native_break"] = True
        item["display_value"] = float(step["diameter"])
        remapped.append(item)
    return remapped


def build_stepped_shaft_variable_plan(
    steps: list[dict[str, Any]],
    *,
    parameter_prefix: str | None = None,
    operation_label: str = "Stepped shaft",
) -> list[dict[str, Any]]:
    variables: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        diameter_name = build_parameter_name("D", index, prefix=parameter_prefix)
        length_name = build_parameter_name("L", index, prefix=parameter_prefix)
        variables.append(
            {
                "name": diameter_name,
                "value": float(step["diameter"]),
                "note": build_parameter_note(operation_label, str(step["name"]), diameter_name, "Diameter"),
                "kind": "driving_diameter",
                "step_name": str(step["name"]),
                "operation_label": operation_label,
            }
        )
        variables.append(
            {
                "name": length_name,
                "value": float(step["length"]),
                "note": build_parameter_note(operation_label, str(step["name"]), length_name, "Length"),
                "kind": "driving_length",
                "step_name": str(step["name"]),
                "operation_label": operation_label,
            }
        )
    return variables


def build_external_conical_step_variable_plan(
    normalized: dict[str, Any],
    *,
    parameter_prefix: str | None = None,
    operation_label: str = "External conical step",
) -> list[dict[str, Any]]:
    start_diameter_name = build_parameter_name("D", 1, prefix=parameter_prefix)
    end_diameter_name = build_parameter_name("D", 2, prefix=parameter_prefix)
    length_name = build_parameter_name("L", 1, prefix=parameter_prefix)
    return [
        {
            "name": start_diameter_name,
            "value": float(normalized["start_diameter"]),
            "note": build_parameter_note(operation_label, "start", start_diameter_name, "Start diameter"),
            "kind": "driving_start_diameter",
            "step_name": "start",
            "operation_label": operation_label,
        },
        {
            "name": end_diameter_name,
            "value": float(normalized["end_diameter"]),
            "note": build_parameter_note(operation_label, "end", end_diameter_name, "End diameter"),
            "kind": "driving_end_diameter",
            "step_name": "end",
            "operation_label": operation_label,
        },
        {
            "name": length_name,
            "value": float(normalized["length"]),
            "note": build_parameter_note(operation_label, "body", length_name, "Length"),
            "kind": "driving_length",
            "step_name": "body",
            "operation_label": operation_label,
        },
    ]


def build_face_ring_groove_variable_plan(
    normalized: dict[str, Any],
    *,
    parameter_prefix: str | None = None,
    operation_label: str = "Face ring groove",
) -> list[dict[str, Any]]:
    inner_diameter_name = build_parameter_name("ID", 1, prefix=parameter_prefix)
    outer_diameter_name = build_parameter_name("OD", 1, prefix=parameter_prefix)
    bottom_inner_diameter_name = build_parameter_name("BID", 1, prefix=parameter_prefix)
    bottom_outer_diameter_name = build_parameter_name("BOD", 1, prefix=parameter_prefix)
    depth_name = build_parameter_name("DEP", 1, prefix=parameter_prefix)
    return [
        {
            "name": inner_diameter_name,
            "value": float(normalized["inner_diameter"]),
            "note": build_parameter_note(operation_label, "face", inner_diameter_name, "Inner diameter"),
            "kind": "driving_inner_diameter",
            "step_name": "face",
            "operation_label": operation_label,
        },
        {
            "name": outer_diameter_name,
            "value": float(normalized["outer_diameter"]),
            "note": build_parameter_note(operation_label, "face", outer_diameter_name, "Outer diameter"),
            "kind": "driving_outer_diameter",
            "step_name": "face",
            "operation_label": operation_label,
        },
        {
            "name": bottom_inner_diameter_name,
            "value": float(normalized["bottom_inner_diameter"]),
            "note": build_parameter_note(operation_label, "bottom", bottom_inner_diameter_name, "Bottom inner diameter"),
            "kind": "driving_bottom_inner_diameter",
            "step_name": "bottom",
            "operation_label": operation_label,
        },
        {
            "name": bottom_outer_diameter_name,
            "value": float(normalized["bottom_outer_diameter"]),
            "note": build_parameter_note(operation_label, "bottom", bottom_outer_diameter_name, "Bottom outer diameter"),
            "kind": "driving_bottom_outer_diameter",
            "step_name": "bottom",
            "operation_label": operation_label,
        },
        {
            "name": depth_name,
            "value": float(normalized["depth"]),
            "note": build_parameter_note(operation_label, "body", depth_name, "Depth"),
            "kind": "driving_depth",
            "step_name": "body",
            "operation_label": operation_label,
        },
    ]


def _format_expression_number(value: float) -> str:
    return ("%0.12f" % float(value)).rstrip("0").rstrip(".")


def build_disc_spring_variable_plan(
    *,
    outer_radius: float,
    inner_radius: float,
    thickness: float,
    free_height: float,
    cone_height: float,
    radial_width: float,
    center_radial_span: float,
    normal_radial_margin: float,
    cone_angle_degrees: float,
    outer_gauge_offset: float,
    parameter_prefix: str | None = "DS",
    operation_label: str = "Disc spring",
) -> list[dict[str, Any]]:
    outer_radius_name = build_parameter_name("OR", 1, prefix=parameter_prefix)
    inner_radius_name = build_parameter_name("IR", 1, prefix=parameter_prefix)
    outer_diameter_name = build_parameter_name("OD", 1, prefix=parameter_prefix)
    inner_diameter_name = build_parameter_name("ID", 1, prefix=parameter_prefix)
    thickness_name = build_parameter_name("T", 1, prefix=parameter_prefix)
    cone_height_name = build_parameter_name("CH", 1, prefix=parameter_prefix)
    free_height_name = build_parameter_name("FH", 1, prefix=parameter_prefix)
    radial_width_name = build_parameter_name("RW", 1, prefix=parameter_prefix)
    center_span_name = build_parameter_name("CRS", 1, prefix=parameter_prefix)
    normal_margin_name = build_parameter_name("NRM", 1, prefix=parameter_prefix)
    cone_angle_name = build_parameter_name("CA", 1, prefix=parameter_prefix)
    outer_gauge_offset_name = build_parameter_name("OGO", 1, prefix=parameter_prefix)

    return [
        {
            "name": outer_radius_name,
            "value": float(outer_radius),
            "expression": _format_expression_number(outer_radius),
            "external": True,
            "note": build_parameter_note(operation_label, "profile", outer_radius_name, "Outer radius"),
            "kind": "driving_outer_radius",
        },
        {
            "name": inner_radius_name,
            "value": float(inner_radius),
            "expression": _format_expression_number(inner_radius),
            "external": True,
            "note": build_parameter_note(operation_label, "profile", inner_radius_name, "Inner radius"),
            "kind": "driving_inner_radius",
        },
        {
            "name": outer_diameter_name,
            "value": float(outer_radius) * 2.0,
            "expression": f"2*{outer_radius_name}",
            "external": True,
            "note": build_parameter_note(operation_label, "profile", outer_diameter_name, "Outer diameter"),
            "kind": "derived_outer_diameter",
        },
        {
            "name": inner_diameter_name,
            "value": float(inner_radius) * 2.0,
            "expression": f"2*{inner_radius_name}",
            "external": True,
            "note": build_parameter_note(operation_label, "profile", inner_diameter_name, "Inner diameter"),
            "kind": "derived_inner_diameter",
        },
        {
            "name": thickness_name,
            "value": float(thickness),
            "expression": _format_expression_number(thickness),
            "external": True,
            "note": build_parameter_note(operation_label, "profile", thickness_name, "Normal thickness"),
            "kind": "driving_thickness",
        },
        {
            "name": cone_height_name,
            "value": float(cone_height),
            "expression": _format_expression_number(cone_height),
            "external": True,
            "note": build_parameter_note(operation_label, "profile", cone_height_name, "Cone rise"),
            "kind": "driving_cone_height",
        },
        {
            "name": free_height_name,
            "value": float(cone_height) + float(thickness),
            "expression": f"{cone_height_name}+{thickness_name}",
            "external": True,
            "note": build_parameter_note(operation_label, "profile", free_height_name, "Free height"),
            "kind": "derived_free_height",
        },
        {
            "name": radial_width_name,
            "value": float(radial_width),
            "expression": f"{outer_radius_name}-{inner_radius_name}",
            "external": False,
            "note": build_parameter_note(operation_label, "profile", radial_width_name, "Radial width"),
            "kind": "derived_radial_width",
        },
        {
            "name": center_span_name,
            "value": float(center_radial_span),
            "expression": _format_expression_number(center_radial_span),
            "external": False,
            "note": build_parameter_note(operation_label, "profile", center_span_name, "Center radial span"),
            "kind": "derived_center_radial_span",
        },
        {
            "name": normal_margin_name,
            "value": float(normal_radial_margin),
            "expression": _format_expression_number(normal_radial_margin),
            "external": False,
            "note": build_parameter_note(operation_label, "profile", normal_margin_name, "Normal radial margin"),
            "kind": "derived_normal_radial_margin",
        },
        {
            "name": cone_angle_name,
            "value": float(cone_angle_degrees),
            "expression": _format_expression_number(cone_angle_degrees),
            "external": True,
            "note": build_parameter_note(operation_label, "profile", cone_angle_name, "Cone angle"),
            "kind": "derived_cone_angle",
        },
        {
            "name": outer_gauge_offset_name,
            "value": abs(float(outer_gauge_offset)),
            "expression": _format_expression_number(abs(float(outer_gauge_offset))),
            "external": False,
            "note": build_parameter_note(operation_label, "profile", outer_gauge_offset_name, "Outer gauge offset"),
            "kind": "derived_outer_gauge_offset",
        },
    ]


def build_disc_spring_constraint_plan() -> list[dict[str, Any]]:
    return [
        {"kind": "horizontal", "target": "axis", "stage": "anchor"},
        {"kind": "fixed_point", "target": "origin", "stage": "anchor"},
        {"kind": "fixed_point", "target": "axis", "index": 1, "stage": "anchor"},
        {"kind": "vertical", "target": "inner_radius_anchor", "stage": "anchor"},
        {"kind": "fixed_point", "target": "inner_radius_anchor", "index": 0, "stage": "anchor"},
        {"kind": "vertical", "target": "outer_radius_anchor", "stage": "anchor"},
        {
            "kind": "merge_points",
            "target": "inner_radius_anchor",
            "index": 1,
            "partner": "profile_line_1",
            "partner_index": 0,
            "stage": "pre_dimension",
        },
        {
            "kind": "merge_points",
            "target": "outer_radius_anchor",
            "index": 1,
            "partner": "profile_line_2",
            "partner_index": 1,
            "stage": "pre_dimension",
        },
        {
            "kind": "merge_points",
            "target": "outer_radius_anchor",
            "index": 0,
            "partner": "outer_gauge_offset_anchor",
            "partner_index": 1,
            "stage": "pre_dimension",
        },
        {
            "kind": "merge_points",
            "target": "profile_line_1",
            "index": 1,
            "partner": "profile_line_2",
            "partner_index": 0,
            "stage": "pre_dimension",
        },
        {
            "kind": "merge_points",
            "target": "profile_line_2",
            "index": 1,
            "partner": "profile_line_3",
            "partner_index": 0,
            "stage": "pre_dimension",
        },
        {
            "kind": "merge_points",
            "target": "profile_line_3",
            "index": 1,
            "partner": "profile_line_4",
            "partner_index": 0,
            "stage": "pre_dimension",
        },
        {
            "kind": "merge_points",
            "target": "profile_line_4",
            "index": 1,
            "partner": "profile_line_1",
            "partner_index": 0,
            "stage": "pre_dimension",
        },
        {"kind": "parallel", "target": "profile_line_1", "partner": "profile_line_3", "stage": "pre_dimension"},
        {"kind": "perpendicular", "target": "profile_line_1", "partner": "profile_line_2", "stage": "pre_dimension"},
        {"kind": "perpendicular", "target": "profile_line_1", "partner": "profile_line_4", "stage": "pre_dimension"},
    ]


def build_disc_spring_dimension_plan(
    *,
    outer_radius_variable: str,
    inner_radius_variable: str,
    thickness_variable: str,
    outer_gauge_offset_variable: str,
) -> list[dict[str, Any]]:
    return [
        {
            "kind": "line_length",
            "target": "profile_line_2",
            "expression": thickness_variable,
            "driving": True,
            "allow_variable_only": True,
            "label": "outer normal thickness",
        },
        {
            "kind": "line_length",
            "target": "profile_line_4",
            "expression": thickness_variable,
            "driving": True,
            "label": "inner normal thickness",
        },
        {
            "kind": "line_length",
            "target": "outer_radius_anchor",
            "expression": outer_radius_variable,
            "driving": True,
            "label": "outer radius",
        },
        {
            "kind": "line_length",
            "target": "inner_radius_anchor",
            "expression": inner_radius_variable,
            "driving": True,
            "label": "inner radius",
        },
        {
            "kind": "line_length",
            "target": "outer_gauge_offset_anchor",
            "expression": outer_gauge_offset_variable,
            "driving": True,
            "label": "outer gauge offset",
        },
    ]


def build_diaphragm_spring_variable_plan(
    *,
    outer_radius: float,
    body_inner_radius: float,
    inner_radius: float,
    thickness: float,
    free_height: float,
    cone_height: float,
    tip_bend_inner_radius: float,
    tip_bend_outer_radius: float,
    tip_variant: str = "single_bend",
    first_tip_inner_radius: float | None = None,
    first_tip_height: float | None = None,
    second_tip_bend_inner_radius: float | None = None,
    second_tip_bend_outer_radius: float | None = None,
    parameter_prefix: str | None = "DIA",
    operation_label: str = "Diaphragm spring",
) -> list[dict[str, Any]]:
    def variable(
        kind: str,
        value: float,
        label: str,
        *,
        expression: str | None = None,
        external: bool = True,
        section: str = "main geometry",
    ) -> dict[str, Any]:
        name = build_parameter_name(kind, 1, prefix=parameter_prefix)
        note = f"{label}. {operation_label}; {section}; variable {name}."
        return {
            "name": name,
            "value": float(value),
            "expression": expression or _format_expression_number(value),
            "external": external,
            "note": note,
            "kind": "driving_%s" % str(kind).lower(),
        }

    outer_diameter_name = build_parameter_name("OD", 1, prefix=parameter_prefix)
    body_inner_diameter_name = build_parameter_name("BODY_ID", 1, prefix=parameter_prefix)
    inner_diameter_name = build_parameter_name("ID", 1, prefix=parameter_prefix)
    thickness_name = build_parameter_name("T", 1, prefix=parameter_prefix)
    bend_inner_name = build_parameter_name("BEND_RI", 1, prefix=parameter_prefix)
    first_tip_inner_diameter_name = build_parameter_name("FIRST_TIP_ID", 1, prefix=parameter_prefix)
    second_bend_inner_name = build_parameter_name("BEND2_RI", 1, prefix=parameter_prefix)

    if tip_variant == "no_bend":
        return [
            variable("OD", outer_radius * 2.0, "Outer diameter"),
            variable("ID", inner_radius * 2.0, "Inner diameter"),
            variable("T", thickness, "Normal thickness"),
            variable("CH", cone_height, "Cone height"),
            variable("OR", outer_radius, "Outer radius", expression="%s/2" % outer_diameter_name, external=False, section="derived geometry"),
            variable("IR", inner_radius, "Inner radius", expression="%s/2" % inner_diameter_name, external=False, section="derived geometry"),
        ]

    variables = [
        variable("OD", outer_radius * 2.0, "Outer diameter"),
        variable("BODY_ID", body_inner_radius * 2.0, "Body inner diameter"),
        variable("ID", inner_radius * 2.0, "Final inner diameter"),
        variable("T", thickness, "Normal thickness"),
        variable("FH", free_height, "Free height"),
        variable("CH", cone_height, "Bend/lip junction height"),
        variable("BEND_RI", tip_bend_inner_radius, "Tip bend inner radius", external=True),
        variable("BEND_RO", tip_bend_outer_radius, "Tip bend outer radius", expression="%s+%s" % (bend_inner_name, thickness_name), external=False),
        variable("OR", outer_radius, "Outer radius", expression="%s/2" % outer_diameter_name, external=False, section="derived geometry"),
        variable("BODY_IR", body_inner_radius, "Body inner radius", expression="%s/2" % body_inner_diameter_name, external=False, section="derived geometry"),
        variable("IR", inner_radius, "Final inner radius", expression="%s/2" % inner_diameter_name, external=False, section="derived geometry"),
    ]

    if tip_variant == "s_bend":
        if (
            first_tip_inner_radius is None
            or first_tip_height is None
            or second_tip_bend_inner_radius is None
            or second_tip_bend_outer_radius is None
        ):
            raise ValueError("s_bend diaphragm variable plan requires first tip and second bend values")
        variables[7:7] = [
            variable("FIRST_TIP_ID", first_tip_inner_radius * 2.0, "Inner diameter after first straight lip segment"),
            variable("FIRST_TIP_H", first_tip_height, "Height after first straight lip segment"),
            variable("BEND2_RI", second_tip_bend_inner_radius, "Second bend inner radius"),
        ]
        variables.extend([
            variable("FIRST_TIP_IR", first_tip_inner_radius, "Inner radius after first straight lip segment", expression="%s/2" % first_tip_inner_diameter_name, external=False, section="derived geometry"),
            variable("BEND2_RO", second_tip_bend_outer_radius, "Second bend outer radius", expression="%s+%s" % (second_bend_inner_name, thickness_name), external=False, section="derived geometry"),
        ])
    elif tip_variant != "single_bend":
        raise ValueError("Unsupported diaphragm spring tip_variant for variable plan: %s" % tip_variant)

    return variables


def build_diaphragm_spring_constraint_plan(*, tip_variant: str = "single_bend") -> list[dict[str, Any]]:
    if tip_variant == "no_bend":
        constraints: list[dict[str, Any]] = [
            {"kind": "fixed_point", "target": "axis", "index": 0, "stage": "anchor"},
            {"kind": "fixed_point", "target": "axis", "index": 1, "stage": "anchor"},
            {"kind": "horizontal", "target": "axis", "stage": "anchor"},
            {"kind": "vertical", "target": "base_height_zero_anchor", "stage": "anchor"},
            {"kind": "horizontal", "target": "inner_gauge_offset_anchor", "stage": "anchor"},
            {"kind": "horizontal", "target": "outer_gauge_offset_anchor", "stage": "anchor"},
            {"kind": "vertical", "target": "inner_radius_anchor", "stage": "anchor"},
            {"kind": "vertical", "target": "outer_radius_anchor", "stage": "anchor"},
            {"kind": "fixed_point", "target": "base_height_zero_anchor", "index": 0, "stage": "anchor"},
            {"kind": "fixed_point", "target": "inner_gauge_offset_anchor", "index": 0, "stage": "anchor"},
            {"kind": "fixed_point", "target": "outer_gauge_offset_anchor", "index": 0, "stage": "anchor"},
            {"kind": "merge_points", "target": "base_height_zero_anchor", "index": 1, "partner": "main_inner_face", "partner_index": 0, "stage": "pre_dimension"},
            {"kind": "merge_points", "target": "inner_radius_anchor", "index": 0, "partner": "inner_gauge_offset_anchor", "partner_index": 1, "stage": "pre_dimension"},
            {"kind": "merge_points", "target": "inner_radius_anchor", "index": 1, "partner": "main_inner_face", "partner_index": 1, "stage": "pre_dimension"},
            {"kind": "merge_points", "target": "outer_radius_anchor", "index": 0, "partner": "outer_gauge_offset_anchor", "partner_index": 1, "stage": "pre_dimension"},
            {"kind": "merge_points", "target": "outer_radius_anchor", "index": 1, "partner": "main_outer_face", "partner_index": 1, "stage": "pre_dimension"},
            {"kind": "parallel", "target": "main_inner_face", "partner": "main_outer_face", "stage": "pre_dimension"},
            {"kind": "perpendicular", "target": "main_inner_face", "partner": "inner_normal_face", "stage": "pre_dimension"},
            {"kind": "perpendicular", "target": "main_inner_face", "partner": "outer_normal_face", "stage": "pre_dimension"},
        ]
        sequence = [
            ("main_inner_face", 1, "inner_normal_face", 0),
            ("inner_normal_face", 1, "main_outer_face", 0),
            ("main_outer_face", 1, "outer_normal_face", 0),
            ("outer_normal_face", 1, "main_inner_face", 0),
        ]
        for target, index, partner, partner_index in sequence:
            constraints.append(
                {
                    "kind": "merge_points",
                    "target": target,
                    "index": index,
                    "partner": partner,
                    "partner_index": partner_index,
                    "stage": "pre_dimension",
                }
            )
        return constraints

    constraints: list[dict[str, Any]] = [
        {"kind": "fixed_point", "target": "axis", "index": 0, "stage": "anchor"},
        {"kind": "fixed_point", "target": "axis", "index": 1, "stage": "anchor"},
        {"kind": "horizontal", "target": "axis", "stage": "anchor"},
        {"kind": "vertical", "target": "base_height_zero_anchor", "stage": "anchor"},
        {"kind": "horizontal", "target": "inner_gauge_offset_anchor", "stage": "anchor"},
        {"kind": "horizontal", "target": "transition_gauge_offset_anchor", "stage": "anchor"},
        {"kind": "horizontal", "target": "outer_gauge_offset_anchor", "stage": "anchor"},
        {"kind": "horizontal", "target": "full_height_gauge_offset_anchor", "stage": "anchor"},
        {"kind": "vertical", "target": "inner_radius_anchor", "stage": "anchor"},
        {"kind": "vertical", "target": "transition_radius_anchor", "stage": "anchor"},
        {"kind": "vertical", "target": "outer_radius_anchor", "stage": "anchor"},
        {"kind": "vertical", "target": "full_height_radius_anchor", "stage": "anchor"},
        {"kind": "fixed_point", "target": "base_height_zero_anchor", "index": 0, "stage": "anchor"},
        {"kind": "fixed_point", "target": "inner_gauge_offset_anchor", "index": 0, "stage": "anchor"},
        {"kind": "fixed_point", "target": "transition_gauge_offset_anchor", "index": 0, "stage": "anchor"},
        {"kind": "fixed_point", "target": "outer_gauge_offset_anchor", "index": 0, "stage": "anchor"},
        {"kind": "fixed_point", "target": "full_height_gauge_offset_anchor", "index": 0, "stage": "anchor"},
        {"kind": "merge_points", "target": "base_height_zero_anchor", "index": 1, "partner": "main_inner_face", "partner_index": 1, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "inner_radius_anchor", "index": 0, "partner": "inner_gauge_offset_anchor", "partner_index": 1, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "inner_radius_anchor", "index": 1, "partner": "tip_inner_face", "partner_index": 0, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "transition_radius_anchor", "index": 0, "partner": "transition_gauge_offset_anchor", "partner_index": 1, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "transition_radius_anchor", "index": 1, "partner": "first_tip_inner_face" if tip_variant == "s_bend" else "tip_inner_face", "partner_index": 1, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "outer_radius_anchor", "index": 0, "partner": "outer_gauge_offset_anchor", "partner_index": 1, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "outer_radius_anchor", "index": 1, "partner": "main_outer_face", "partner_index": 0, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "full_height_radius_anchor", "index": 0, "partner": "full_height_gauge_offset_anchor", "partner_index": 1, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "full_height_radius_anchor", "index": 1, "partner": "tip_outer_face", "partner_index": 1, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "bend_inner_radius_line", "index": 0, "partner": "inner_bend_arc", "partner_index": 0, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "bend_inner_radius_line", "index": 0, "partner": "outer_bend_arc", "partner_index": 0, "stage": "pre_dimension"},
        {"kind": "merge_points", "target": "bend_inner_radius_line", "index": 1, "partner": "inner_bend_arc", "partner_index": 1, "stage": "pre_dimension"},
        {"kind": "parallel", "target": "main_inner_face", "partner": "main_outer_face", "stage": "pre_dimension"},
        {"kind": "parallel", "target": "tip_inner_face", "partner": "tip_outer_face", "stage": "pre_dimension"},
        {"kind": "perpendicular", "target": "main_inner_face", "partner": "outer_normal_face", "stage": "pre_dimension"},
        {"kind": "perpendicular", "target": "tip_inner_face", "partner": "tip_end_face", "stage": "pre_dimension"},
        {"kind": "tangent", "target": "first_tip_inner_face" if tip_variant == "s_bend" else "tip_inner_face", "partner": "outer_bend_arc", "stage": "pre_dimension"},
        {"kind": "tangent", "target": "main_inner_face", "partner": "outer_bend_arc", "stage": "pre_dimension"},
        {"kind": "tangent", "target": "main_outer_face", "partner": "inner_bend_arc", "stage": "pre_dimension"},
        {"kind": "tangent", "target": "first_tip_outer_face" if tip_variant == "s_bend" else "tip_outer_face", "partner": "inner_bend_arc", "stage": "pre_dimension"},
    ]
    if tip_variant == "s_bend":
        constraints.extend([
            {"kind": "horizontal", "target": "first_tip_height_gauge_offset_anchor", "stage": "anchor"},
            {"kind": "vertical", "target": "first_tip_height_radius_anchor", "stage": "anchor"},
            {"kind": "vertical", "target": "first_tip_inner_radius_anchor", "stage": "anchor"},
            {"kind": "fixed_point", "target": "first_tip_height_gauge_offset_anchor", "index": 0, "stage": "anchor"},
            {"kind": "merge_points", "target": "first_tip_height_radius_anchor", "index": 0, "partner": "first_tip_height_gauge_offset_anchor", "partner_index": 1, "stage": "pre_dimension"},
            {"kind": "merge_points", "target": "first_tip_height_radius_anchor", "index": 1, "partner": "first_tip_inner_face", "partner_index": 0, "stage": "pre_dimension"},
            {"kind": "merge_points", "target": "first_tip_inner_radius_anchor", "index": 0, "partner": "first_tip_inner_gauge_offset_anchor", "partner_index": 1, "stage": "pre_dimension"},
            {"kind": "merge_points", "target": "first_tip_inner_radius_anchor", "index": 1, "partner": "first_tip_inner_face", "partner_index": 0, "stage": "pre_dimension"},
            {"kind": "horizontal", "target": "first_tip_inner_gauge_offset_anchor", "stage": "anchor"},
            {"kind": "fixed_point", "target": "first_tip_inner_gauge_offset_anchor", "index": 0, "stage": "anchor"},
            {"kind": "merge_points", "target": "second_bend_inner_radius_line", "index": 0, "partner": "second_inner_bend_arc", "partner_index": 0, "stage": "pre_dimension"},
            {"kind": "merge_points", "target": "second_bend_inner_radius_line", "index": 0, "partner": "second_outer_bend_arc", "partner_index": 0, "stage": "pre_dimension"},
            {"kind": "merge_points", "target": "second_bend_inner_radius_line", "index": 1, "partner": "second_inner_bend_arc", "partner_index": 2, "stage": "pre_dimension"},
            {"kind": "parallel", "target": "first_tip_inner_face", "partner": "first_tip_outer_face", "stage": "pre_dimension"},
            {"kind": "tangent", "target": "first_tip_inner_face", "partner": "second_inner_bend_arc", "stage": "pre_dimension"},
            {"kind": "tangent", "target": "tip_inner_face", "partner": "second_inner_bend_arc", "stage": "pre_dimension"},
            {"kind": "tangent", "target": "first_tip_outer_face", "partner": "second_outer_bend_arc", "stage": "pre_dimension"},
            {"kind": "tangent", "target": "tip_outer_face", "partner": "second_outer_bend_arc", "stage": "pre_dimension"},
        ])
        sequence = [
            ("tip_inner_face", 1, "second_inner_bend_arc", 1),
            ("second_inner_bend_arc", 2, "first_tip_inner_face", 0),
            ("first_tip_inner_face", 1, "outer_bend_arc", 1),
            ("outer_bend_arc", 2, "main_inner_face", 0),
            ("main_inner_face", 1, "outer_normal_face", 0),
            ("outer_normal_face", 1, "main_outer_face", 0),
            ("main_outer_face", 1, "inner_bend_arc", 1),
            ("inner_bend_arc", 2, "first_tip_outer_face", 0),
            ("first_tip_outer_face", 1, "second_outer_bend_arc", 1),
            ("second_outer_bend_arc", 2, "tip_outer_face", 0),
            ("tip_outer_face", 1, "tip_end_face", 0),
            ("tip_end_face", 1, "tip_inner_face", 0),
        ]
    elif tip_variant == "single_bend":
        sequence = [
            ("tip_inner_face", 1, "outer_bend_arc", 1),
            ("outer_bend_arc", 2, "main_inner_face", 0),
            ("main_inner_face", 1, "outer_normal_face", 0),
            ("outer_normal_face", 1, "main_outer_face", 0),
            ("main_outer_face", 1, "inner_bend_arc", 1),
            ("inner_bend_arc", 2, "tip_outer_face", 0),
            ("tip_outer_face", 1, "tip_end_face", 0),
            ("tip_end_face", 1, "tip_inner_face", 0),
        ]
    else:
        raise ValueError("Unsupported diaphragm spring tip_variant for constraint plan: %s" % tip_variant)
    for target, index, partner, partner_index in sequence:
        constraints.append(
            {
                "kind": "merge_points",
                "target": target,
                "index": index,
                "partner": partner,
                "partner_index": partner_index,
                "stage": "pre_dimension",
            }
        )
    return constraints


def build_diaphragm_spring_dimension_plan(
    *,
    outer_radius_variable: str,
    inner_radius_variable: str,
    body_inner_radius_variable: str,
    cone_height_variable: str,
    free_height_variable: str,
    thickness_variable: str,
    bend_inner_radius_variable: str,
    tip_variant: str = "single_bend",
    first_tip_inner_radius_variable: str | None = None,
    first_tip_height_variable: str | None = None,
    second_bend_inner_radius_variable: str | None = None,
) -> list[dict[str, Any]]:
    """Return driving dimensions for the fully-defined diaphragm profile.

    Bend arcs are fixed through their common center, endpoints, and tangencies
    rather than direct radial dimensions: API-created radial dimensions for
    these arcs do not persist as solver-defining dimensions after save/reopen.
    """

    if tip_variant == "no_bend":
        return [
            {
                "kind": "line_length",
                "target": "inner_radius_anchor",
                "expression": inner_radius_variable,
                "driving": True,
                "label": "inner radius",
            },
            {
                "kind": "line_length",
                "target": "outer_radius_anchor",
                "expression": outer_radius_variable,
                "driving": True,
                "label": "outer radius",
            },
            {
                "kind": "line_length",
                "target": "outer_normal_face",
                "expression": thickness_variable,
                "driving": True,
                "label": "normal thickness",
            },
            {
                "kind": "line_length",
                "target": "inner_gauge_offset_anchor",
                "expression": cone_height_variable,
                "driving": True,
                "label": "cone height",
            },
        ]

    dimensions = [
        {
            "kind": "line_length",
            "target": "inner_radius_anchor",
            "expression": inner_radius_variable,
            "driving": True,
            "label": "final inner radius",
        },
        {
            "kind": "line_length",
            "target": "transition_gauge_offset_anchor",
            "expression": cone_height_variable,
            "driving": True,
            "label": "transition gauge offset",
        },
        {
            "kind": "line_length",
            "target": "transition_radius_anchor",
            "expression": body_inner_radius_variable,
            "driving": True,
            "label": "body inner radius",
        },
        {
            "kind": "line_length",
            "target": "outer_radius_anchor",
            "expression": outer_radius_variable,
            "driving": True,
            "label": "outer radius",
        },
        {
            "kind": "line_length",
            "target": "full_height_gauge_offset_anchor",
            "expression": free_height_variable,
            "driving": True,
            "label": "free height",
        },
        {
            "kind": "line_length",
            "target": "outer_normal_face",
            "expression": thickness_variable,
            "driving": True,
            "allow_variable_only": True,
            "label": "outer normal thickness",
        },
        {
            "kind": "line_length",
            "target": "bend_inner_radius_line",
            "expression": bend_inner_radius_variable,
            "driving": True,
            "allow_variable_only": True,
            "label": "bend inner radius",
        },
    ]

    if tip_variant == "s_bend":
        if first_tip_inner_radius_variable is None or first_tip_height_variable is None or second_bend_inner_radius_variable is None:
            raise ValueError("s_bend diaphragm dimension plan requires first tip and second bend variables")
        dimensions.extend([
            {
                "kind": "line_length",
                "target": "first_tip_inner_radius_anchor",
                "expression": first_tip_inner_radius_variable,
                "driving": True,
                "label": "first tip inner radius",
            },
            {
                "kind": "line_length",
                "target": "first_tip_height_gauge_offset_anchor",
                "expression": first_tip_height_variable,
                "driving": True,
                "label": "first tip height",
            },
            {
                "kind": "line_length",
                "target": "second_bend_inner_radius_line",
                "expression": second_bend_inner_radius_variable,
                "driving": True,
                "allow_variable_only": True,
                "label": "second bend inner radius",
            },
        ])
    elif tip_variant != "single_bend":
        raise ValueError("Unsupported diaphragm spring tip_variant for dimension plan: %s" % tip_variant)

    return dimensions


def build_polygonal_step_dimension_plan(
    normalized: dict[str, Any],
    vertices: list[list[float]],
    *,
    parameter_prefix: str | None = None,
) -> list[dict[str, Any]]:
    if len(vertices) < 3:
        raise ValueError("polygonal step requires at least three vertices")

    diameter_name = build_parameter_name("D", 1, prefix=parameter_prefix)
    radius_expression = diameter_name

    return [
        {
            "kind": "circle_diameter",
            "name": build_parameter_name("R", 1, prefix=parameter_prefix),
            "variable": build_parameter_name("R", 1, prefix=parameter_prefix),
            "expression": radius_expression,
            "target": "helper_circle",
            "value": float(normalized["diameter"]),
            "driving": True,
            "placement_index": 1,
            "dimension_type": False,
            "angle": 0.0,
            "display_prefix": "Ø",
        },
    ]


def build_polygonal_step_variable_plan(
    normalized: dict[str, Any],
    *,
    parameter_prefix: str | None = None,
    operation_label: str = "Polygonal step",
) -> list[dict[str, Any]]:
    diameter_name = build_parameter_name("D", 1, prefix=parameter_prefix)
    length_name = build_parameter_name("L", 1, prefix=parameter_prefix)
    return [
        {
            "name": diameter_name,
            "value": float(normalized["diameter"]),
            "note": build_parameter_note(operation_label, "profile", diameter_name, "Diameter"),
            "kind": "driving_diameter",
            "step_name": "profile",
            "operation_label": operation_label,
            "external": True,
        },
        {
            "name": length_name,
            "value": float(normalized["length"]),
            "note": build_parameter_note(operation_label, "profile", length_name, "Length"),
            "kind": "driving_length",
            "step_name": "profile",
            "operation_label": operation_label,
            "external": True,
        },
    ]


def build_polygonal_step_constraint_plan(
    normalized: dict[str, Any],
    vertices: list[list[float]],
    *,
    parameter_prefix: str | None = None,
) -> list[dict[str, Any]]:
    if len(vertices) < 3:
        raise ValueError("polygonal step requires at least three vertices")

    constraints: list[dict[str, Any]] = [
        {"kind": "fixed_point", "target": "circle_radius_line", "index": 0, "name": "polygon_center_fixed"},
        {
            "kind": "fixed_point",
            "target": "helper_circle",
            "index": 0,
            "name": "helper_circle_center_fixed",
        },
        {
            "kind": "point_on_curve",
            "target": "circle_radius_line",
            "index": 1,
            "partner": "helper_circle",
            "name": "radius_point_on_circle",
        },
        {"kind": "vertical", "target": "circle_radius_line", "name": "radius_line_vertical"},
        {"kind": "horizontal", "target": "profile_line_1", "name": "first_edge_horizontal"},
    ]
    if normalized["diameter_mode"] == "inscribed_circle":
        constraints.append(
            {
                "kind": "concentricity",
                "target": "vertex_circle",
                "partner": "helper_circle",
                "name": "vertex_circle_concentric",
            }
        )
    vertex_count = len(vertices)

    for index in range(1, vertex_count + 1):
        profile_target = f"profile_line_{index}"
        if index != 1:
            constraints.append(
                {
                    "kind": "equal_length",
                    "target": profile_target,
                    "partner": "profile_line_1",
                    "name": f"{profile_target}_equal_length",
                }
            )
        constraints.append(
            {
                "kind": "point_on_curve",
                "target": profile_target,
                "index": 0,
                "partner": "helper_circle" if normalized["diameter_mode"] == "circumscribed_circle" else "vertex_circle",
                "name": f"{profile_target}_on_circle",
            }
        )
        if normalized["diameter_mode"] == "inscribed_circle":
            constraints.append(
                {
                    "kind": "tangent",
                    "target": profile_target,
                    "partner": "helper_circle",
                    "name": f"{profile_target}_tangent_circle",
                }
            )
        constraints.append(
            {
                "kind": "merge_points",
                "target": profile_target,
                "index": 1,
                "partner": f"profile_line_{1 if index == vertex_count else index + 1}",
                "partner_index": 0,
                "name": f"{profile_target}_to_profile_line_{1 if index == vertex_count else index + 1}",
            }
        )
    return constraints


def build_flat_step_dimension_plan(
    normalized: dict[str, Any],
    *,
    parameter_prefix: str | None = None,
) -> list[dict[str, Any]]:
    diameter_name = build_parameter_name("D", 1, prefix=parameter_prefix)
    flat_depth_name = build_parameter_name("F", 1, prefix=parameter_prefix)
    dimensions: list[dict[str, Any]] = [
        {
            "kind": "circle_diameter",
            "name": build_parameter_name("R", 1, prefix=parameter_prefix),
            "variable": build_parameter_name("R", 1, prefix=parameter_prefix),
            "expression": diameter_name,
            "target": "helper_circle",
            "value": float(normalized["diameter"]),
            "driving": True,
            "dimension_type": False,
            "angle": 0.0,
            "display_prefix": "Ø",
        },
        {
            "kind": "axis_distance",
            "name": build_parameter_name("SFK", 1, prefix=parameter_prefix),
            "variable": build_parameter_name("SFK", 1, prefix=parameter_prefix),
            "expression": f"{diameter_name} / 2 - {flat_depth_name}",
            "target": "top_flat_line",
            "value": float(normalized["flat_offset"]),
            "driving": True,
            "placement_index": 0,
            "support_point_index": 0,
            "point_y": float(normalized["flat_offset"]),
        },
    ]
    if int(normalized["flats_count"]) == 2:
        dimensions.append(
            {
                "kind": "axis_distance",
                "name": build_parameter_name("SFK", 2, prefix=parameter_prefix),
                "variable": build_parameter_name("SFK", 2, prefix=parameter_prefix),
                "expression": f"{diameter_name} / 2 - {flat_depth_name}",
                "target": "bottom_flat_line",
                "value": float(normalized["flat_offset"]),
                "driving": True,
                "placement_index": 1,
                "support_point_index": 0,
                "point_y": -float(normalized["flat_offset"]),
            }
        )
    return dimensions


def build_flat_step_variable_plan(
    normalized: dict[str, Any],
    *,
    parameter_prefix: str | None = None,
    operation_label: str = "Flat step",
) -> list[dict[str, Any]]:
    diameter_name = build_parameter_name("D", 1, prefix=parameter_prefix)
    length_name = build_parameter_name("L", 1, prefix=parameter_prefix)
    flat_depth_name = build_parameter_name("F", 1, prefix=parameter_prefix)
    return [
        {
            "name": diameter_name,
            "value": float(normalized["diameter"]),
            "note": build_parameter_note(operation_label, "profile", diameter_name, "Diameter"),
            "kind": "driving_diameter",
            "step_name": "profile",
            "operation_label": operation_label,
            "external": True,
        },
        {
            "name": length_name,
            "value": float(normalized["length"]),
            "note": build_parameter_note(operation_label, "body", length_name, "Length"),
            "kind": "driving_length",
            "step_name": "body",
            "operation_label": operation_label,
            "external": True,
        },
        {
            "name": flat_depth_name,
            "value": float(normalized["flat_depth"]),
            "note": build_parameter_note(operation_label, "profile", flat_depth_name, "Flat depth"),
            "kind": "driving_flat_depth",
            "step_name": "profile",
            "operation_label": operation_label,
            "external": True,
        },
    ]


def build_flat_step_constraint_plan(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    flats_count = int(normalized["flats_count"])
    constraints: list[dict[str, Any]] = [
        {"kind": "fixed_point", "target": "helper_circle", "index": 0, "name": "profile_center_fixed"},
        {"kind": "horizontal", "target": "top_flat_line", "name": "top_flat_horizontal"},
        {
            "kind": "point_on_curve",
            "target": "top_flat_line",
            "index": 0,
            "partner": "helper_circle",
            "name": "top_flat_start_on_circle",
        },
        {
            "kind": "point_on_curve",
            "target": "top_flat_line",
            "index": 1,
            "partner": "helper_circle",
            "name": "top_flat_end_on_circle",
        },
    ]
    if flats_count == 1:
        constraints.extend(
            [
                {
                    "kind": "fixed_point",
                    "target": "outer_arc",
                    "index": 0,
                    "name": "outer_arc_center_fixed",
                },
                {
                    "kind": "merge_points",
                    "target": "outer_arc",
                    "index": 2,
                    "partner": "top_flat_line",
                    "partner_index": 1,
                    "name": "top_flat_to_outer_arc_start",
                },
                {
                    "kind": "merge_points",
                    "target": "outer_arc",
                    "index": 1,
                    "partner": "top_flat_line",
                    "partner_index": 0,
                    "name": "outer_arc_end_to_top_flat_start",
                },
            ]
        )
        return constraints

    constraints.extend(
        [
            {"kind": "horizontal", "target": "bottom_flat_line", "name": "bottom_flat_horizontal"},
            {
                "kind": "point_on_curve",
                "target": "bottom_flat_line",
                "index": 0,
                "partner": "helper_circle",
                "name": "bottom_flat_start_on_circle",
            },
            {
                "kind": "point_on_curve",
                "target": "bottom_flat_line",
                "index": 1,
                "partner": "helper_circle",
                "name": "bottom_flat_end_on_circle",
            },
            {
                "kind": "fixed_point",
                "target": "right_arc",
                "index": 0,
                "name": "right_arc_center_fixed",
            },
            {
                "kind": "fixed_point",
                "target": "left_arc",
                "index": 0,
                "name": "left_arc_center_fixed",
            },
            {
                "kind": "merge_points",
                "target": "right_arc",
                "index": 2,
                "partner": "top_flat_line",
                "partner_index": 1,
                "name": "top_flat_to_right_arc_start",
            },
            {
                "kind": "merge_points",
                "target": "right_arc",
                "index": 1,
                "partner": "bottom_flat_line",
                "partner_index": 0,
                "name": "right_arc_end_to_bottom_flat_start",
            },
            {
                "kind": "merge_points",
                "target": "left_arc",
                "index": 2,
                "partner": "bottom_flat_line",
                "partner_index": 1,
                "name": "bottom_flat_to_left_arc_start",
            },
            {
                "kind": "merge_points",
                "target": "left_arc",
                "index": 1,
                "partner": "top_flat_line",
                "partner_index": 0,
                "name": "left_arc_end_to_top_flat_start",
            },
        ]
    )
    return constraints


def build_stepped_shaft_constraint_plan(steps: list[dict[str, Any]], profile_points: list[list[float]]) -> list[dict[str, Any]]:
    axis_y = float(profile_points[0][1]) if profile_points else 0.0
    constraints: list[dict[str, Any]] = [
        {"kind": "horizontal", "target": "axis", "name": "axis_horizontal"},
        {"kind": "fixed_point", "target": "axis", "index": 0, "name": "axis_origin_fixed"},
    ]
    segments = _build_profile_segments(profile_points)
    actual_segments = [segment for segment in segments if not segment["skipped"]]

    if actual_segments:
        constraints.append(
            {
                "kind": "merge_points",
                "target": actual_segments[0]["target"],
                "index": 0,
                "partner": "axis",
                "partner_index": 0,
                "name": "profile_start_to_axis_origin",
            }
        )

    for current, following in zip(actual_segments, actual_segments[1:]):
        constraints.append(
            {
                "kind": "merge_points",
                "target": current["target"],
                "index": 1,
                "partner": following["target"],
                "partner_index": 0,
                "name": f"{current['target']}_to_{following['target']}",
            }
        )

    if actual_segments:
        constraints.append(
            {
                "kind": "merge_points",
                "target": actual_segments[-1]["target"],
                "index": 1,
                "partner": "axis",
                "partner_index": 1,
                "name": "profile_end_to_axis_end",
            }
        )

    for segment in actual_segments:
        target = segment["target"]
        if segment["orientation"] == "vertical":
            constraints.append({"kind": "perpendicular", "target": target, "partner": "axis"})
        elif segment["orientation"] == "horizontal" and float(segment["y1"]) != axis_y:
            constraints.append({"kind": "parallel", "target": target, "partner": "axis"})
    return constraints


def build_face_ring_groove_constraint_plan(profile_points: list[list[float]]) -> list[dict[str, Any]]:
    segments = [segment for segment in _build_profile_segments(profile_points) if not segment["skipped"]]
    if len(segments) != 4:
        raise ValueError("failed to map face ring groove constraints to sketch segments")

    top_segment, inner_wall_segment, bottom_segment, outer_wall_segment = segments
    return [
        {"kind": "horizontal", "target": "axis", "name": "axis_horizontal"},
        {"kind": "fixed_point", "target": "axis", "index": 0, "name": "axis_origin_fixed"},
        {"kind": "vertical", "target": top_segment["target"], "name": "face_plane_vertical"},
        {"kind": "point_on_curve", "target": "axis", "index": 0, "partner": top_segment["target"], "name": "axis_origin_on_face_plane"},
        {"kind": "vertical", "target": bottom_segment["target"], "name": "bottom_face_vertical"},
        {"kind": "point_on_curve", "target": "axis", "index": 1, "partner": bottom_segment["target"], "name": "axis_end_on_bottom_face"},
        {"kind": "merge_points", "target": top_segment["target"], "index": 1, "partner": inner_wall_segment["target"], "partner_index": 0, "name": "top_to_inner_wall"},
        {"kind": "merge_points", "target": inner_wall_segment["target"], "index": 1, "partner": bottom_segment["target"], "partner_index": 0, "name": "inner_wall_to_bottom"},
        {"kind": "merge_points", "target": bottom_segment["target"], "index": 1, "partner": outer_wall_segment["target"], "partner_index": 0, "name": "bottom_to_outer_wall"},
        {"kind": "merge_points", "target": outer_wall_segment["target"], "index": 1, "partner": top_segment["target"], "partner_index": 0, "name": "outer_wall_to_top"},
    ]


def build_external_conical_step_constraint_plan(profile_points: list[list[float]]) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = [
        {"kind": "horizontal", "target": "axis", "name": "axis_horizontal"},
        {"kind": "fixed_point", "target": "axis", "index": 0, "name": "axis_origin_fixed"},
    ]
    actual_segments = [segment for segment in _build_profile_segments(profile_points) if not segment["skipped"]]

    if len(actual_segments) != 3:
        raise ValueError("failed to map external conical step constraints to sketch segments")

    constraints.extend(
        [
            {
                "kind": "merge_points",
                "target": actual_segments[0]["target"],
                "index": 0,
                "partner": "axis",
                "partner_index": 0,
                "name": "profile_start_to_axis_origin",
            },
            {
                "kind": "merge_points",
                "target": actual_segments[0]["target"],
                "index": 1,
                "partner": actual_segments[1]["target"],
                "partner_index": 0,
                "name": f"{actual_segments[0]['target']}_to_{actual_segments[1]['target']}",
            },
            {
                "kind": "merge_points",
                "target": actual_segments[1]["target"],
                "index": 1,
                "partner": actual_segments[2]["target"],
                "partner_index": 0,
                "name": f"{actual_segments[1]['target']}_to_{actual_segments[2]['target']}",
            },
            {
                "kind": "merge_points",
                "target": actual_segments[2]["target"],
                "index": 1,
                "partner": "axis",
                "partner_index": 1,
                "name": "profile_end_to_axis_end",
            },
            {"kind": "perpendicular", "target": actual_segments[0]["target"], "partner": "axis"},
            {"kind": "perpendicular", "target": actual_segments[2]["target"], "partner": "axis"},
        ]
    )
    return constraints
