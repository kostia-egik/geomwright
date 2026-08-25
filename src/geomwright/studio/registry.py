from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
from typing import Any

from pydantic import BaseModel

from kompas_mcp.transmission_tools import FlatBeltPulleyPreviewRequest, PolyVGroovePreviewRequest, TimingCurvilinearPulleyPreviewRequest, TimingTrapezoidalPulleyPreviewRequest, VGroovePreviewRequest
from kompas_mcp.transmissions import preview_flat_belt_pulley, preview_poly_v_groove, preview_timing_belt_pulley, preview_v_belt_groove
from kompas_mcp.transmissions import build_managed_pulley_plan


PreviewBuilder = Callable[[dict[str, Any]], dict[str, Any]]
PreviewAdapter = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class PreviewModule:
    kind: str
    name: str
    description: str
    standard: str
    request_model: type[BaseModel]
    defaults: dict[str, Any]
    builder: PreviewBuilder
    adapter: PreviewAdapter
    group: str = "mechanical_transmissions"
    subgroup: str = "belt_drives"
    family: str = "belt_pulleys"
    build: bool = True
    icon: str = ""

    def descriptor(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
            "standard": self.standard,
            "group": self.group,
            "subgroup": self.subgroup,
            "family": self.family,
            "icon": self.icon or f"/static/icons/{self.kind}.svg",
            "capabilities": {"preview": True, "build": self.build, "inspect": False},
            "spec_url": f"/modules/{self.kind}/spec",
            "preview_url": f"/modules/{self.kind}/preview",
            "cad_plan_url": f"/modules/{self.kind}/cad/plan",
            "cad_create_url": f"/modules/{self.kind}/cad/create",
            "cad_job_url": f"/modules/{self.kind}/cad/jobs",
        }

    def spec(self) -> dict[str, Any]:
        return {
            "module": self.descriptor(),
            "schema": self.request_model.model_json_schema(),
            "defaults": dict(self.defaults),
        }

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = self.request_model.model_validate(payload)
        normalized_request = request.model_dump(exclude_none=True)
        raw_preview = self.builder(normalized_request)
        result = self.adapter(raw_preview, normalized_request)
        result["module"] = self.descriptor()
        result["request"] = normalized_request
        return result


def _build_v_belt_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return preview_v_belt_groove(**payload)


def _build_poly_v_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return preview_poly_v_groove(**payload)


def _build_flat_belt_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return preview_flat_belt_pulley(**payload)


def _build_timing_trapezoidal_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return preview_timing_belt_pulley(**payload, custom_shape="trapezoidal" if payload.get("designation") == "CUSTOM" else None)


def _build_timing_curvilinear_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return preview_timing_belt_pulley(**payload, custom_shape="curvilinear" if payload.get("designation") == "CUSTOM" else None)


def _points(value: Any) -> list[list[float]]:
    result: list[list[float]] = []
    for point in list(value or []):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        result.append([float(point[0]), float(point[1])])
    return result


def _polar(radius: float, angle: float) -> list[float]:
    return [radius * math.sin(angle), radius * math.cos(angle)]


def _bounds(closed_points: list[list[list[float]]], guide_paths: list[list[list[float]]]) -> dict[str, float]:
    points = [point for path in [*closed_points, *guide_paths] for point in path]
    if not points:
        return {"x_min": 0.0, "x_max": 1.0, "y_min": 0.0, "y_max": 1.0}
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "x_min": min(xs),
        "x_max": max(xs),
        "y_min": min(ys),
        "y_max": max(ys),
    }


def _phantom_body(
    *,
    x_min: float,
    x_max: float,
    root_radius: float,
    outer_radius: float,
    groove_depth: float,
    surface: list[list[float]] | None = None,
) -> dict[str, Any]:
    face_width = x_max - x_min
    radial_extension = max(groove_depth * 0.75, min(face_width * 0.3, root_radius * 0.18))
    inner_radius = max(0.0, root_radius - radial_extension)
    return {
        "outline": [
            [x_min, outer_radius],
            [x_min, inner_radius],
            [x_max, inner_radius],
            [x_max, outer_radius],
        ],
        "inner_radius": inner_radius,
        "outer_radius": outer_radius,
        "truncated": inner_radius > 0.0,
        "surface": list(surface or [[x_min, outer_radius], [x_max, outer_radius]]),
    }


def _joined_surface_paths(paths: list[list[list[float]]]) -> list[list[float]]:
    ordered = sorted((path for path in paths if path), key=lambda path: float(path[0][0]))
    result: list[list[float]] = []
    for path in ordered:
        for point in path:
            if not result or point != result[-1]:
                result.append(point)
    return result


def _reference_path(
    *,
    key: str,
    x_min: float,
    x_max: float,
    radius: Any,
) -> dict[str, Any] | None:
    if not isinstance(radius, (int, float)):
        return None
    return {
        "key": key,
        "points": [[x_min, float(radius)], [x_max, float(radius)]],
    }


def _editable_v_profile(profile: dict[str, Any]) -> dict[str, float]:
    fields = (
        "datum_width",
        "datum_offset",
        "groove_pitch",
        "edge_distance",
        "groove_depth",
        "groove_angle_degrees",
        "approximate_top_width",
        "minimum_datum_diameter",
        "standard_top_edge_radius",
    )
    return {
        field: float(profile[field])
        for field in fields
        if isinstance(profile.get(field), (int, float))
    }


def _line_intersection(
    first_start: list[float],
    first_end: list[float],
    second_start: list[float],
    second_end: list[float],
) -> list[float] | None:
    x1, y1 = first_start
    x2, y2 = first_end
    x3, y3 = second_start
    x4, y4 = second_end
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) <= 1e-12:
        return None
    determinant1 = x1 * y2 - y1 * x2
    determinant2 = x3 * y4 - y3 * x4
    return [
        (determinant1 * (x3 - x4) - (x1 - x2) * determinant2) / denominator,
        (determinant1 * (y3 - y4) - (y1 - y2) * determinant2) / denominator,
    ]


def _v_belt_angle_geometry(geometry: dict[str, Any]) -> dict[str, list[float]] | None:
    grooves = list(geometry.get("grooves") or [])
    polygon = _points(grooves[0].get("cut_polygon")) if grooves else []
    if len(polygon) < 4:
        return None
    left_top, left_root, right_root, right_top = polygon[:4]
    vertex = _line_intersection(left_root, left_top, right_root, right_top)
    if vertex is None:
        return None
    return {"vertex": vertex, "left_ray": left_root, "right_ray": right_root}


def _v_belt_top_edge_fillets(
    geometry: dict[str, Any],
    profile: dict[str, Any],
    inputs: dict[str, Any],
) -> list[dict[str, Any]]:
    radius = profile.get("standard_top_edge_radius")
    if not isinstance(radius, (int, float)) or float(radius) <= 0.0:
        return []
    radius = float(radius)
    source = "override" if "standard_top_edge_radius" in dict(inputs.get("profile_overrides") or {}) else "standard"
    result: list[dict[str, Any]] = []
    for groove_index, groove in enumerate(list(geometry.get("grooves") or []), start=1):
        polygon = _points(groove.get("cut_polygon"))
        if len(polygon) < 4:
            continue
        left_top, left_root, right_root, right_top = polygon[:4]
        for side, top, root, top_direction in (
            ("left", left_top, left_root, [-1.0, 0.0]),
            ("right", right_top, right_root, [1.0, 0.0]),
        ):
            flank = [root[0] - top[0], root[1] - top[1]]
            flank_length = math.hypot(*flank)
            if flank_length <= 1e-12:
                continue
            flank_direction = [flank[0] / flank_length, flank[1] / flank_length]
            cosine = max(-1.0, min(1.0, top_direction[0] * flank_direction[0] + top_direction[1] * flank_direction[1]))
            corner_angle = math.acos(cosine)
            tangent_distance = radius / math.tan(corner_angle / 2.0)
            top_tangent = [top[0] + top_direction[0] * tangent_distance, top[1]]
            flank_tangent = [
                top[0] + flank_direction[0] * tangent_distance,
                top[1] + flank_direction[1] * tangent_distance,
            ]
            center = [top_tangent[0], top_tangent[1] - radius]
            start_angle = math.atan2(top_tangent[1] - center[1], top_tangent[0] - center[0])
            end_angle = math.atan2(flank_tangent[1] - center[1], flank_tangent[0] - center[0])
            delta = (end_angle - start_angle + math.pi) % (2.0 * math.pi) - math.pi
            points = [
                [
                    center[0] + radius * math.cos(start_angle + delta * index / 12.0),
                    center[1] + radius * math.sin(start_angle + delta * index / 12.0),
                ]
                for index in range(13)
            ]
            result.append(
                {
                    "kind": "top_edge_fillet",
                    "groove_index": groove_index,
                    "side": side,
                    "radius": radius,
                    "radius_source": source,
                    "center": center,
                    "anchor": points[6],
                    "points": points,
                }
            )
    return result


def _rounded_v_belt_closed_points(
    geometry: dict[str, Any],
    surface_features: list[dict[str, Any]],
) -> list[list[list[float]]]:
    by_groove = {
        (int(feature["groove_index"]), str(feature["side"])): feature
        for feature in surface_features
    }
    result: list[list[list[float]]] = []
    for groove_index, groove in enumerate(list(geometry.get("grooves") or []), start=1):
        polygon = _points(groove.get("cut_polygon"))
        if len(polygon) < 4:
            continue
        left_top, left_root, right_root, right_top = polygon[:4]
        left = by_groove.get((groove_index, "left"))
        right = by_groove.get((groove_index, "right"))
        if not left or not right:
            closed = _points(groove.get("closed_cut_polygon"))
            if closed:
                result.append(closed)
            continue
        left_arc = _points(left.get("points"))
        right_arc = _points(right.get("points"))
        if not left_arc or not right_arc:
            continue
        rounded = [
            left_arc[0],
            *left_arc[1:],
            left_root,
            right_root,
            *list(reversed(right_arc[:-1])),
            left_arc[0],
        ]
        result.append(rounded)
    return result


def _poly_v_angle_geometry(geometry: dict[str, Any]) -> dict[str, list[float]] | None:
    grooves = list(geometry.get("grooves") or [])
    tangent_points = dict(grooves[0].get("tangent_points") or {}) if grooves else {}
    left_root = _points([tangent_points.get("left_root")])
    left_crest = _points([tangent_points.get("left_crest")])
    right_root = _points([tangent_points.get("right_root")])
    right_crest = _points([tangent_points.get("right_crest")])
    if not all((left_root, left_crest, right_root, right_crest)):
        return None
    vertex = _line_intersection(left_root[0], left_crest[0], right_root[0], right_crest[0])
    if vertex is None:
        return None
    return {"vertex": vertex, "left_ray": left_root[0], "right_ray": right_root[0]}


def _poly_v_radius_dimensions(
    geometry: dict[str, Any],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    grooves = list(geometry.get("grooves") or [])
    entities = list(grooves[0].get("profile_entities") or []) if grooves else []
    result: list[dict[str, Any]] = []
    specs = (
        ("transition_radius", "Rₜ", "tip_transition", "left", 42, profile.get("transition_radius")),
        ("maximum_root_radius", "Rᵣ", "groove_root", "right", 52, profile.get("maximum_root_radius")),
    )
    for key, symbol, role, placement, extension_length, value in specs:
        entity = next((item for item in entities if item.get("role") == role), None)
        if not entity or not isinstance(value, (int, float)):
            continue
        center = _points([entity.get("center")])
        anchor = _points([entity.get("end")])
        if not center or not anchor:
            continue
        result.append(
            {
                "key": key,
                "symbol": symbol,
                "orientation": "radius",
                "center": center[0],
                "anchor": anchor[0],
                "start": anchor[0],
                "end": center[0],
                "placement": placement,
                "extension_length": extension_length,
                "value": float(value),
                "unit": "mm",
            }
        )
    return result


def _warnings(preview: dict[str, Any]) -> list[str]:
    return [str(item) for item in list(preview.get("warnings") or [])]


def _warning_items(preview: dict[str, Any], codes: list[str]) -> list[dict[str, str]]:
    return [
        {"code": codes[index] if index < len(codes) else "unclassified", "message": message}
        for index, message in enumerate(_warnings(preview))
    ]


def _v_belt_warning_codes(preview: dict[str, Any]) -> list[str]:
    inputs = dict(preview.get("inputs") or {})
    profile = dict(preview.get("profile") or {})
    source = dict(preview.get("source") or {})
    codes = [
        "v_belt_post_cut_fillet"
        if isinstance(profile.get("standard_top_edge_radius"), (int, float))
        else "v_belt_flat_preview"
    ]
    if source.get("evidence_level") == "manufacturer_reference":
        codes.append("licensed_standard_check")
    elif inputs.get("designation") == "CUSTOM":
        codes.append("custom_profile_unverified")
    if inputs.get("profile_overrides"):
        codes.append("profile_overrides_non_catalog")
    return codes


def _dimensions(
    *,
    bounds: dict[str, float],
    centers: list[Any],
    face_width: Any,
    groove_pitch: Any,
    groove_depth: Any,
    groove_top_width: Any = None,
    outer_diameter: Any = None,
    reference_diameter: Any = None,
    reference_key: str = "datum_diameter",
    root_diameter: Any = None,
    groove_angle: Any = None,
    angle_geometry: dict[str, list[float]] | None = None,
    body_break_radius: Any = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    y_max = bounds["y_max"]
    if isinstance(face_width, (int, float)):
        result.append(
            {
                "key": "face_width",
                "symbol": "B",
                "orientation": "horizontal",
                "start": [bounds["x_min"], y_max],
                "end": [bounds["x_max"], y_max],
                "placement": "top",
                "level": 2,
                "value": float(face_width),
                "unit": "mm",
            }
        )
    numeric_centers = [float(value) for value in centers if isinstance(value, (int, float))]
    if len(numeric_centers) > 1 and isinstance(groove_pitch, (int, float)):
        result.append(
            {
                "key": "groove_pitch",
                "symbol": "e",
                "orientation": "horizontal",
                "start": [numeric_centers[0], y_max],
                "end": [numeric_centers[1], y_max],
                "placement": "top",
                "level": 0,
                "value": float(groove_pitch),
                "unit": "mm",
            }
        )
    if numeric_centers and isinstance(groove_depth, (int, float)):
        result.append(
            {
                "key": "groove_depth",
                "symbol": "h",
                "orientation": "vertical",
                "start": [numeric_centers[0], y_max],
                "end": [numeric_centers[0], y_max - float(groove_depth)],
                "placement": "left",
                "level": 0,
                "value": float(groove_depth),
                "unit": "mm",
            }
        )
    if numeric_centers and isinstance(groove_top_width, (int, float)):
        center = numeric_centers[0]
        half_width = float(groove_top_width) / 2.0
        result.append(
            {
                "key": "groove_top_width",
                "symbol": "b₀",
                "orientation": "horizontal",
                "start": [center - half_width, y_max],
                "end": [center + half_width, y_max],
                "placement": "top",
                "level": 1,
                "value": float(groove_top_width),
                "unit": "mm",
            }
        )
    if (
        numeric_centers
        and isinstance(groove_angle, (int, float))
        and angle_geometry
    ):
        vertex = angle_geometry["vertex"]
        result.append(
            {
                "key": "groove_angle",
                "symbol": "α",
                "orientation": "angular",
                "vertex": vertex,
                "left_ray": angle_geometry["left_ray"],
                "right_ray": angle_geometry["right_ray"],
                "start": vertex,
                "end": vertex,
                "value": float(groove_angle),
                "unit": "°",
            }
        )
    diameter_specs = (
        ("outer_diameter", "⌀Dₐ", outer_diameter, "right", 1, None),
        (reference_key, "⌀Dₑ" if reference_key == "effective_diameter" else "⌀D", reference_diameter, "left", 0, None),
        ("root_diameter", "⌀Dᵣ", root_diameter, "right", 0, numeric_centers[-1] if numeric_centers else None),
    )
    for key, symbol, value, placement, level, target_x in diameter_specs:
        if not isinstance(value, (int, float)):
            continue
        result.append(
            {
                "key": key,
                "symbol": symbol,
                "orientation": "diameter",
                "start": [bounds["x_max"], float(value) / 2.0],
                "end": [bounds["x_max"], float(value) / 2.0],
                "placement": placement,
                "level": level,
                "target_x": target_x,
                "break_radius": float(body_break_radius) if isinstance(body_break_radius, (int, float)) else 0.0,
                "value": float(value),
                "unit": "mm",
            }
        )
    return result


def _adapt_v_belt(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    geometry = dict(preview.get("geometry") or {})
    derived = dict(preview.get("derived") or {})
    profile = dict(preview.get("profile") or {})
    inputs = dict(preview.get("inputs") or request)
    surface_features = _v_belt_top_edge_fillets(geometry, profile, inputs)
    closed_points = [
        points
        for groove in list(geometry.get("grooves") or [])
        if (points := _points(groove.get("closed_cut_polygon")))
    ]
    if surface_features:
        closed_points = _rounded_v_belt_closed_points(geometry, surface_features)
    feature_paths = [points[:-1] for points in closed_points if len(points) > 1]
    guide_paths = [
        points
        for segment in list(geometry.get("outer_surface_segments") or [])
        if (points := _points([segment.get("start"), segment.get("end")]))
    ]
    envelope = dict(geometry.get("envelope") or {})
    surface_bounds = {
        "x_min": float(envelope.get("x_min", 0.0)),
        "x_max": float(envelope.get("x_max", 1.0)),
        "y_max": float(envelope.get("radius_max", 1.0)),
    }
    body_surface = _joined_surface_paths([*guide_paths, *feature_paths])
    phantom_body = _phantom_body(
        x_min=surface_bounds["x_min"],
        x_max=surface_bounds["x_max"],
        root_radius=float(envelope.get("radius_min", 0.0)),
        outer_radius=surface_bounds["y_max"],
        groove_depth=float(profile.get("groove_depth", 0.0)),
        surface=body_surface,
    )
    reference_paths = [
        path
        for path in (
            _reference_path(
                key="datum_diameter",
                x_min=surface_bounds["x_min"],
                x_max=surface_bounds["x_max"],
                radius=float(derived["datum_diameter"]) / 2.0,
            ),
        )
        if path is not None
    ]
    contextual_paths = [
        phantom_body["outline"],
        *[path["points"] for path in reference_paths],
    ]
    bounds = _bounds(closed_points, [*guide_paths, *contextual_paths])
    warnings = _warnings(preview)
    return {
        "ok": bool(preview.get("success")),
        "family": "v_belt",
        "closed_points": closed_points,
        "feature_paths": feature_paths,
        "guide_paths": guide_paths,
        "surface_features": surface_features,
        "reference_paths": reference_paths,
        "phantom_bodies": [phantom_body],
        "editable_profile": _editable_v_profile(profile),
        "bounds": bounds,
        "coordinate_system": geometry.get("coordinate_system"),
        "summary": {
            "designation": inputs.get("designation"),
            "standard_system": inputs.get("standard_system"),
            "groove_count": inputs.get("groove_count"),
            "datum_diameter_mm": derived.get("datum_diameter"),
            "outer_diameter_mm": derived.get("outer_diameter"),
            "root_diameter_mm": derived.get("root_diameter"),
            "face_width_mm": derived.get("face_width"),
            "groove_pitch_mm": profile.get("groove_pitch"),
            "groove_depth_mm": profile.get("groove_depth"),
            "groove_top_width_mm": derived.get("actual_top_width"),
            "groove_angle_degrees": derived.get("groove_angle_degrees"),
            "top_edge_fillet_radius_mm": profile.get("standard_top_edge_radius"),
        },
        "dimensions": _dimensions(
            bounds=surface_bounds,
            centers=list(derived.get("groove_centers") or []),
            face_width=derived.get("face_width"),
            groove_pitch=profile.get("groove_pitch"),
            groove_depth=profile.get("groove_depth"),
            groove_top_width=derived.get("actual_top_width"),
            outer_diameter=derived.get("outer_diameter"),
            reference_diameter=derived.get("datum_diameter"),
            reference_key="datum_diameter",
            root_diameter=derived.get("root_diameter"),
            groove_angle=derived.get("groove_angle_degrees"),
            angle_geometry=_v_belt_angle_geometry(geometry),
            body_break_radius=phantom_body.get("inner_radius"),
        )
        + (
            [
                {
                    "key": "top_edge_fillet_radius",
                    "symbol": "Rₖ",
                    "orientation": "radius",
                    "center": surface_features[0]["center"],
                    "anchor": surface_features[0]["anchor"],
                    "start": surface_features[0]["anchor"],
                    "end": surface_features[0]["center"],
                    "placement": "left",
                    "extension_length": 34,
                    "value": surface_features[0]["radius"],
                    "unit": "mm",
                }
            ]
            if surface_features
            else []
        ),
        "warnings": warnings,
        "warning_items": _warning_items(preview, _v_belt_warning_codes(preview)),
    }


def _adapt_poly_v(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    geometry = dict(preview.get("geometry") or {})
    derived = dict(preview.get("derived") or {})
    profile_data = dict(preview.get("profile") or {})
    inputs = dict(preview.get("inputs") or request)
    profile = _points(geometry.get("sampled_cut_polygon"))
    closed_points = [profile] if profile else []
    feature_paths = []
    for groove in list(geometry.get("grooves") or []):
        outer_points = _points(groove.get("outer_points"))
        if len(outer_points) != 2:
            continue
        x_min = min(outer_points[0][0], outer_points[1][0]) - 1e-9
        x_max = max(outer_points[0][0], outer_points[1][0]) + 1e-9
        groove_path = [point for point in profile[:-1] if x_min <= point[0] <= x_max]
        if groove_path:
            feature_paths.append(groove_path)
    envelope = dict(geometry.get("envelope") or {})
    guide_paths = [
        points
        for points in (
            _points(
                [
                    [envelope.get("x_min"), envelope.get("radius_max")],
                    [envelope.get("profile_x_min"), envelope.get("radius_max")],
                ]
            ),
            _points(
                [
                    [envelope.get("profile_x_max"), envelope.get("radius_max")],
                    [envelope.get("x_max"), envelope.get("radius_max")],
                ]
            ),
        )
        if points
    ]
    surface_bounds = {
        "x_min": float(envelope.get("x_min", 0.0)),
        "x_max": float(envelope.get("x_max", 1.0)),
        "y_max": float(envelope.get("radius_max", 1.0)),
    }
    body_surface = _joined_surface_paths([*guide_paths, *feature_paths])
    phantom_body = _phantom_body(
        x_min=surface_bounds["x_min"],
        x_max=surface_bounds["x_max"],
        root_radius=float(envelope.get("radius_min", 0.0)),
        outer_radius=surface_bounds["y_max"],
        groove_depth=float(derived.get("groove_depth", 0.0)),
        surface=body_surface,
    )
    reference_paths = [
        path
        for path in (
            _reference_path(
                key="effective_diameter",
                x_min=surface_bounds["x_min"],
                x_max=surface_bounds["x_max"],
                radius=float(derived["effective_diameter"]) / 2.0,
            ),
        )
        if path is not None
    ]
    contextual_paths = [
        phantom_body["outline"],
        *[path["points"] for path in reference_paths],
    ]
    bounds = _bounds(closed_points, [*guide_paths, *contextual_paths])
    warnings = _warnings(preview)
    return {
        "ok": bool(preview.get("success")),
        "family": "poly_v",
        "closed_points": closed_points,
        "feature_paths": feature_paths,
        "guide_paths": guide_paths,
        "reference_paths": reference_paths,
        "phantom_bodies": [phantom_body],
        "bounds": bounds,
        "coordinate_system": geometry.get("coordinate_system"),
        "summary": {
            "designation": inputs.get("designation"),
            "standard_system": "ISO 9982:2021",
            "groove_count": inputs.get("groove_count"),
            "effective_diameter_mm": derived.get("effective_diameter"),
            "outer_diameter_mm": derived.get("outer_diameter"),
            "root_diameter_mm": derived.get("root_diameter"),
            "face_width_mm": derived.get("face_width"),
            "groove_pitch_mm": profile_data.get("groove_pitch"),
            "groove_depth_mm": derived.get("groove_depth"),
            "transition_radius_mm": profile_data.get("transition_radius"),
            "maximum_root_radius_mm": profile_data.get("maximum_root_radius"),
            "groove_angle_degrees": derived.get("groove_angle_degrees"),
        },
        "dimensions": [
            *_dimensions(
                bounds=surface_bounds,
                centers=list(derived.get("groove_centers") or []),
                face_width=derived.get("face_width"),
                groove_pitch=profile_data.get("groove_pitch"),
                groove_depth=derived.get("groove_depth"),
                outer_diameter=derived.get("outer_diameter"),
                reference_diameter=derived.get("effective_diameter"),
                reference_key="effective_diameter",
                root_diameter=derived.get("root_diameter"),
                groove_angle=derived.get("groove_angle_degrees"),
                angle_geometry=_poly_v_angle_geometry(geometry),
                body_break_radius=phantom_body.get("inner_radius"),
            ),
            *_poly_v_radius_dimensions(geometry, profile_data),
        ],
        "warnings": warnings,
        "warning_items": _warning_items(
            preview,
            [
                "poly_v_nominal_radii",
                "poly_v_cut_overshoot",
                "licensed_standard_check",
            ],
        ),
    }


def _adapt_flat_belt(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    geometry = dict(preview.get("geometry") or {})
    derived = dict(preview.get("derived") or {})
    inputs = dict(preview.get("inputs") or request)
    closed = _points(geometry.get("closed_profile"))
    outer = _points(geometry.get("outer_surface"))
    body_break_radius = max(0.0, float(derived["edge_diameter"]) * 0.32)
    phantom = _phantom_body(
        x_min=0.0,
        x_max=float(inputs["face_width"]),
        root_radius=body_break_radius,
        outer_radius=float(derived["outer_radius"]),
        groove_depth=max(1.0, float(derived["outer_radius"]) - body_break_radius),
        surface=outer,
    )
    bounds = _bounds([closed], [outer, phantom["outline"]])
    dimensions = [
        {"key": "face_width", "symbol": "B", "orientation": "horizontal", "start": [0.0, derived["outer_radius"]], "end": [inputs["face_width"], derived["outer_radius"]], "value": inputs["face_width"], "unit": "mm", "level": 1},
        {"key": "outer_diameter", "symbol": "⌀D", "orientation": "diameter", "start": [inputs["face_width"], derived["outer_radius"]], "end": [inputs["face_width"], derived["outer_radius"]], "target_x": inputs["face_width"] / 2.0, "break_radius": phantom["inner_radius"], "value": inputs["outer_diameter"], "unit": "mm", "placement": "right", "level": 2},
    ]
    if inputs["profile"] == "crowned":
        dimensions.append(
            {"key": "crown_height", "symbol": "h", "orientation": "vertical", "start": [inputs["face_width"] / 2.0, derived["edge_diameter"] / 2.0], "end": [inputs["face_width"] / 2.0, derived["outer_radius"]], "value": inputs["crown_height"], "unit": "mm", "level": 2}
        )
    return {
        "ok": bool(preview.get("success")),
        "family": "flat_belt",
        "closed_points": [closed],
        "feature_paths": [outer],
        "guide_paths": [outer],
        "reference_paths": [],
        "phantom_bodies": [phantom],
        "bounds": bounds,
        "coordinate_system": geometry.get("coordinate_system"),
        "summary": {
            "profile": inputs["profile"],
            "outer_diameter_mm": inputs["outer_diameter"],
            "edge_diameter_mm": derived["edge_diameter"],
            "face_width_mm": inputs["face_width"],
            "crown_height_mm": inputs["crown_height"],
            "crown_radius_mm": derived.get("crown_radius"),
        },
        "dimensions": dimensions,
        "warnings": list(preview.get("warnings") or []),
        "warning_items": [
            {"code": "explicit_nonstandard_crown", "message": item}
            for item in list(preview.get("warnings") or [])
        ],
    }


def _adapt_timing_belt(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    geometry = dict(preview["geometry"])
    profile = dict(preview["profile"])
    derived = dict(preview["derived"])
    outside_radius = derived["outside_diameter"] / 2.0
    root_radius = derived["root_diameter"] / 2.0
    tooth_angle = 2.0 * math.pi / request["tooth_count"]
    half_groove_angle = profile["groove_width"] / (2.0 * outside_radius)
    dimension_start_radius = geometry["break_radius"] + profile["groove_depth"] * 0.48
    outside_angle = -1.34 * tooth_angle
    root_angle = tooth_angle
    fillets = list(geometry.get("fillets") or [])
    tip_fillet = next(
        item
        for item in fillets
        if item.get("kind") == "tip" and item.get("groove_index") == 0 and item.get("side") == "right"
    )
    root_fillet = next(
        item
        for item in fillets
        if item.get("kind") == "root" and item.get("groove_index") == 2 and item.get("side") in {"left", "center"}
    )
    dimensions = [
        {
            "key": "outside_diameter",
            "symbol": "Dₐ",
            "orientation": "radial",
            "start": _polar(dimension_start_radius, outside_angle),
            "end": _polar(outside_radius, outside_angle),
            "value": derived["outside_diameter"],
            "unit": "mm",
            "label_normal": -43,
            "label_tangent": 5,
        },
        {
            "key": "root_diameter",
            "symbol": "D_f",
            "orientation": "radial",
            "start": _polar(dimension_start_radius, root_angle),
            "end": _polar(root_radius, root_angle),
            "value": derived["root_diameter"],
            "unit": "mm",
            "label_normal": 47,
            "label_tangent": -4,
        },
        {
            "key": "groove_width",
            "symbol": "s",
            "orientation": "horizontal",
            "start": _polar(outside_radius, -half_groove_angle),
            "end": _polar(outside_radius, half_groove_angle),
            "value": profile["groove_width"],
            "unit": "mm",
            "placement": "top",
        },
        {
            "key": "groove_depth",
            "symbol": "h",
            "orientation": "vertical",
            "start": _polar(outside_radius, 0.0),
            "end": _polar(root_radius, 0.0),
            "value": profile["groove_depth"],
            "unit": "mm",
            "placement": "right",
            "label_horizontal": True,
            "label_dx": 42,
        },
        {
            "key": "tip_radius",
            "symbol": "rₐ",
            "orientation": "radius",
            "start": tip_fillet["anchor_end"],
            "end": tip_fillet["center"],
            "center": tip_fillet["center"],
            "anchor": tip_fillet["anchor_end"],
            "value": derived["tip_radius"],
            "unit": "mm",
            "extension_length": 24,
            "label_dx": -20,
            "label_dy": -10,
            "label_horizontal": True,
        },
        {
            "key": "root_fillet_radius",
            "symbol": "r_f",
            "orientation": "radius",
            "start": root_fillet["anchor_start"],
            "end": root_fillet["center"],
            "center": root_fillet["center"],
            "anchor": root_fillet["anchor_start"],
            "value": derived["root_fillet_radius"],
            "unit": "mm",
            "extension_length": 25,
            "label_dx": 18,
            "label_dy": 8,
            "label_horizontal": True,
        },
    ]
    angle = geometry["sector_half_angle"] * 1.22
    x_extent = outside_radius * math.sin(angle)
    y_min = geometry["break_radius"] - profile["groove_depth"] * 0.45
    return {
        "ok": True,
        "family": "timing_belt",
        "view_mode": "end",
        "closed_points": [geometry["outline"]],
        "feature_paths": [geometry["profile_path"]],
        "guide_paths": [geometry["break_path"]],
        "reference_paths": [
            {"key": "outside_circle", "points": geometry["outside_circle"]},
        ],
        "phantom_bodies": [],
        "bounds": {"x_min": -x_extent, "x_max": x_extent, "y_min": y_min, "y_max": outside_radius + profile["groove_depth"] * 1.8},
        "coordinate_system": geometry["coordinate_system"],
        "summary": {
            "designation": request["designation"],
            "profile_shape": profile["shape"],
            "tooth_count": request["tooth_count"],
            "pitch_mm": profile["pitch"],
            "pitch_diameter_mm": derived["pitch_diameter"],
            "outside_diameter_mm": derived["outside_diameter"],
            "root_diameter_mm": derived["root_diameter"],
            "face_width_mm": request["face_width"],
            "groove_width_mm": profile["groove_width"],
            "groove_depth_mm": profile["groove_depth"],
            "tip_radius_mm": derived["tip_radius"],
            "root_fillet_radius_mm": derived["root_fillet_radius"],
        },
        "dimensions": dimensions,
        "warnings": list(preview.get("warnings") or []),
        "warning_items": [
            {"code": "custom_timing_profile", "message": item}
            for item in list(preview.get("warnings") or [])
        ],
    }


_MODULES: dict[str, PreviewModule] = {
    "v_belt": PreviewModule(
        kind="v_belt",
        name="V-belt pulley grooves",
        description="Classical and narrow-wedge V-grooves from the existing transmission catalog.",
        standard="DIN/ISO or GOST 20889-88",
        request_model=VGroovePreviewRequest,
        defaults={
            "designation": "A",
            "datum_diameter": 100.0,
            "groove_count": 2,
            "standard_system": "din_iso",
        },
        builder=_build_v_belt_preview,
        adapter=_adapt_v_belt,
        family="wedge_pulleys",
        icon="/static/icons/v.svg",
    ),
    "poly_v": PreviewModule(
        kind="poly_v",
        name="Poly-V pulley grooves",
        description="Rounded PH, PJ, PK, PL, and PM profiles from ISO 9982:2021.",
        standard="ISO 9982:2021",
        request_model=PolyVGroovePreviewRequest,
        defaults={"designation": "PJ", "effective_diameter": 80.0, "groove_count": 6},
        builder=_build_poly_v_preview,
        adapter=_adapt_poly_v,
        family="wedge_pulleys",
        icon="/static/icons/poli-v.svg",
    ),
    "flat_belt": PreviewModule(
        kind="flat_belt",
        name="Flat-belt pulley",
        description="Cylindrical or explicitly crowned functional rim without a belt, hub, or bore.",
        standard="Parametric geometry; no implicit standard crown",
        request_model=FlatBeltPulleyPreviewRequest,
        defaults={
            "outer_diameter": 160.0,
            "face_width": 50.0,
            "crown_height": 0.0,
        },
        builder=_build_flat_belt_preview,
        adapter=_adapt_flat_belt,
        family="friction_pulleys",
        icon="/static/icons/flat.svg",
    ),
    "timing_trapezoidal": PreviewModule(
        kind="timing_trapezoidal",
        name="Trapezoidal timing-belt pulley",
        description="End-view straight-flank tooth geometry for T and AT synchronous-belt profiles.",
        standard="Catalog geometry preview; supplier data required for automotive profiles",
        request_model=TimingTrapezoidalPulleyPreviewRequest,
        defaults={
            "designation": "T5",
            "tooth_count": 24,
            "face_width": 20.0,
        },
        builder=_build_timing_trapezoidal_preview,
        adapter=_adapt_timing_belt,
        family="synchronous_pulleys",
        build=True,
        icon="/static/icons/trap.svg",
    ),
    "timing_curvilinear": PreviewModule(
        kind="timing_curvilinear",
        name="Curvilinear timing-belt pulley",
        description="End-view rounded tooth geometry for HTD synchronous-belt profiles.",
        standard="Catalog geometry preview; supplier data required for automotive profiles",
        request_model=TimingCurvilinearPulleyPreviewRequest,
        defaults={"designation": "HTD_5M", "tooth_count": 24, "face_width": 20.0},
        builder=_build_timing_curvilinear_preview,
        adapter=_adapt_timing_belt,
        family="synchronous_pulleys",
        build=True,
        icon="/static/icons/crc.svg",
    ),
}


def list_modules() -> list[dict[str, Any]]:
    return [module.descriptor() for module in _MODULES.values()]


def get_module(kind: str) -> PreviewModule:
    normalized = str(kind or "").strip().lower().replace("-", "_")
    try:
        return _MODULES[normalized]
    except KeyError as exc:
        raise KeyError(f"Unknown Geomwright Studio module: {kind}") from exc


def preview_module(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Preview payload must be a JSON object")
    return get_module(kind).preview(payload)


def managed_pulley_plan(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    module = get_module(kind)
    if not module.build:
        raise ValueError(f"{module.kind} is preview-only; CAD planning is not implemented")
    request = module.request_model.model_validate(payload)
    normalized_request = request.model_dump(exclude_none=True)
    return build_managed_pulley_plan(module.kind, normalized_request)
