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
