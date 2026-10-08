from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
from typing import Any

from pydantic import BaseModel

from kompas_mcp.transmission_tools import ChainSprocketPreviewRequest, FlatBeltPulleyPreviewRequest, PolyVGroovePreviewRequest, TimingCurvilinearPulleyPreviewRequest, TimingTrapezoidalPulleyPreviewRequest, VGroovePreviewRequest
from kompas_mcp.transmissions import build_chain_sprocket_plan, chain_profile_selection, preview_chain_sprocket, preview_flat_belt_pulley, preview_poly_v_groove, preview_timing_belt_pulley, preview_v_belt_groove
from kompas_mcp.transmissions import build_managed_pulley_plan
from kompas_mcp.connections import StraightSplineRequest, spline_selection
from .spline_preview import adapt_spline_preview, build_spline_preview
from kompas_mcp.gears import (
    BevelGearRequest,
    InternalGearRequest,
    SpurGearRequest,
    bevel_gear_selection,
    build_bevel_gear_preview,
    build_internal_gear_preview,
    build_spur_gear_preview,
    gear_selection,
)
from .silent_chain import SilentChainSelectionRequest, silent_chain_selection
from .silent_chain_preview import build_silent_chain_preview
from kompas_mcp.transmissions.silent_chain import build_silent_chain_plan
from .camshaft import CamshaftPhasesRequest, adapt_camshaft_phases, build_camshaft_phases_preview, cam_profile_request


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
    builder: PreviewBuilder | None
    adapter: PreviewAdapter | None
    group: str = "mechanical_transmissions"
    subgroup: str = "belt_drives"
    family: str = "belt_pulleys"
    build: bool = True
    preview_available: bool = True
    icon: str | None = ""
    selection: dict[str, Any] | None = None

    def descriptor(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
            "standard": self.standard,
            "group": self.group,
            "subgroup": self.subgroup,
            "family": self.family,
            "icon": self.icon,
            "selection": self.selection,
            "capabilities": {"preview": self.preview_available, "build": self.build, "inspect": False},
            "spec_url": f"/modules/{self.kind}/spec",
            "preview_url": f"/modules/{self.kind}/preview" if self.preview_available else None,
            "cad_plan_url": f"/modules/{self.kind}/cad/plan" if self.build else None,
            "cad_create_url": f"/modules/{self.kind}/cad/create" if self.build else None,
            "cad_job_url": f"/modules/{self.kind}/cad/jobs" if self.build else None,
        }

    def spec(self) -> dict[str, Any]:
        return {
            "module": self.descriptor(),
            "schema": self.request_model.model_json_schema(),
            "defaults": dict(self.defaults),
        }

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.preview_available or self.builder is None or self.adapter is None:
            raise ValueError(f"{self.kind} has no preview yet")
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


def _build_chain_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return preview_chain_sprocket(**payload)


def _build_silent_chain_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return build_silent_chain_preview(payload)


def _silent_full_wheel_outline(tooth_gap: list[list[float]], tooth_count: int, outside_radius: float) -> list[list[float]]:
    """Repeat one analytic tooth space into one continuous closed wheel contour."""
    if len(tooth_gap) < 3 or tooth_count < 3 or outside_radius <= 0:
        return []
    step = 2.0 * math.pi / tooth_count
    start_angle = math.atan2(tooth_gap[0][0], tooth_gap[0][1])
    end_angle = math.atan2(tooth_gap[-1][0], tooth_gap[-1][1])
    while end_angle <= start_angle:
        end_angle += 2.0 * math.pi
    outline: list[list[float]] = []
    for index in range(tooth_count):
        gap = _rotate_path(tooth_gap, index * step)
        if not outline:
            outline.extend(gap)
        else:
            outline.extend(gap[1:])
        current_end = end_angle + index * step
        next_start = start_angle + (index + 1) * step
        while next_start <= current_end:
            next_start += 2.0 * math.pi
        arc_steps = max(3, math.ceil((next_start - current_end) / math.radians(3.0)))
        for arc_index in range(1, arc_steps + 1):
            if index == tooth_count - 1 and arc_index == arc_steps:
                outline.append(list(outline[0]))
            else:
                angle = current_end + (next_start - current_end) * arc_index / arc_steps
                outline.append(_polar(outside_radius, angle))
    return outline


def _adapt_silent_chain(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    geometry = dict(preview.get("geometry") or {})
    derived = dict(preview.get("derived") or {})
    profile = dict(preview.get("profile") or {})
    tooth_gap = _points(geometry.get("profile_path"))
    tooth_count = int(request.get("physical_tooth_count") or 1)
    outside_radius = float(derived["outside_diameter_mm"]) / 2.0
    pitch_radius = float(derived["pitch_diameter_mm"]) / 2.0
    root_radius = float(derived["root_diameter_mm"]) / 2.0
    section = _chain_section_preview(
        tooth_gap=tooth_gap,
        pitch_radius=pitch_radius,
        outside_radius=outside_radius,
        root_radius=root_radius,
        tooth_count=tooth_count,
        tooth_tip=_points(geometry.get("tooth_tip_path")),
    )
    profile_path = section["profile_path"]
    break_path = section["break_path"]
    closed = section["outline"]
    pitch_circle = section["pitch_circle"]
    outside_circle = section["outside_circle"]
    axial = dict(preview.get("axial") or {})
    partial = bool(geometry.get("partial"))
    tool_policy = bool(geometry.get("tool_policy"))
    user_radial = bool(geometry.get("user_radial_paths"))
    dimensions = []
    dimension_start_radius = float(section["break_radius"])
    for key, symbol, value, radius, angle in (
        ("outside_diameter", "Dₑ" if request["standard"].startswith("gost") else "Dₐ", derived["outside_diameter_mm"], outside_radius, float(section["left_angle"]) * 0.78),
        ("pitch_diameter", "dд" if request["standard"].startswith("gost") else "Dₚ", derived["pitch_diameter_mm"], pitch_radius, float(section["right_angle"]) * 0.78),
        ("root_diameter", "Dᵢ*" if tool_policy or user_radial else "Dᵢ", derived["root_diameter_mm"], root_radius, float(section["left_angle"]) * 0.35),
    ):
        if key == "root_diameter" and partial:
            continue
        dimensions.append({
            "key": key, "symbol": symbol, "orientation": "radial",
            "start": _polar(float(dimension_start_radius), angle),
            "end": _polar(float(radius), angle), "value": value, "unit": "mm",
            "label_normal": 24, "label_tangent": 8,
        })
    bounds = _bounds([closed], [pitch_circle, outside_circle])
    standard = str(request.get("standard"))
    warnings = list(preview.get("warnings") or [])
    warning_code = {
        "gost_13552_81_13576_81": "silent_gost_profile_verified",
        "din_8190_8191_open": "silent_din_open_reconstruction",
        "asme_b29_2m_open": "silent_asme_open_reconstruction",
    }.get(standard, "silent_chain_preview_assumption")
    strokes = []
    for index in (-1, 0, 1):
        for path in geometry.get("supported_paths", []):
            # The third space closes the window; its following cap is outside it.
            if index == 1 and path == geometry.get("tooth_tip_path"):
                continue
            strokes.append({"points": _rotate_path(_points(path), index * 2.0 * math.pi / tooth_count), "tone": "exhaust", "width": 2.4})
    tone_paths = [{"points": closed, "tone": "exhaust", "fill": "rgba(227,170,79,.05)", "width": 1.0 if partial else 2.4, "dashed": partial}]
    if partial or tool_policy or user_radial:
        if tool_policy or user_radial:
            tone_paths[0]["stroke"] = False
        tone_paths.extend(strokes)
        for index in (-1, 0, 1):
            for path in geometry.get("tool_policy_paths", []):
                tone_paths.append({"points": _rotate_path(_points(path), index * 2.0 * math.pi / tooth_count), "tone": "intake", "width": 2.4})
            for path in geometry.get("user_radial_paths", []):
                if index == 1 and path == geometry.get("tooth_tip_path"):
                    continue
                tone_paths.append({"points": _rotate_path(_points(path), index * 2.0 * math.pi / tooth_count), "tone": "intake", "width": 2.4})
    for index in (-1, 0):
        for path in geometry.get("provisional_tip_paths", []):
            tone_paths.append({"points": _rotate_path(_points(path), index * 2.0 * math.pi / tooth_count), "tone": "exhaust", "width": 2.4, "dashed": True})
    drawing_status = axial.get("drawing", {}).get("status", "")
    warning_items = [{"code": warning_code, "message": warnings[0]}] if warnings else []
    if partial:
        warning_items.append({"code": "silent_din_rack_height_conflict", "message": "Series 06: the tabulated tool height and Figure-3 rack construction differ by about 0.03 mm; the candidate root is dashed."})
    if tool_policy:
        warning_items.append({"code": "silent_asme_tool_root", "message": "Teal root and Dᵢ*: selected tool variant below the source-defined working faces, not a unique standard root."})
    if standard == "asme_b29_2m_open" and derived.get("tip_shape") == "square":
        if derived.get("tip_status") == "user_defined_square_tip":
            warning_items.append({"code": "silent_asme_user_tip", "message": "Square-tip diameter is an explicit user construction choice, not an official standard correction."})
        elif preview["diagnostics"]["square_construction"]["table_text_status"] == "printed_source_conflict_with_vendor_substitute":
            warning_items.append({"code": "silent_asme_table_transcription", "message": "The inconsistent Table 7 value is confirmed in the printed standard. The diameter uses a provisional Ramsey substitute, not an official correction."})
        else:
            warning_items.append({"code": "silent_asme_square_equation_conflict", "message": "The square-tip diameter uses Table 7 maximum values; the printed equation and figure coordinates do not fully agree with the table."})
    return {
        "ok": bool(preview.get("success")),
        "family": "silent_chain_sprocket",
        "view_mode": "end",
        "secondary_view": axial,
        "completion": preview.get("completion"),
        "construction_spec": preview.get("construction_spec"),
        "closed_points": [closed] if closed else [],
        "feature_paths": [profile_path] if profile_path else [],
        "tone_paths": tone_paths if closed else [],
        "guide_paths": [break_path] if break_path else [],
        "reference_paths": [
            {"key": "pitch_circle", "points": pitch_circle},
            {"key": "outside_circle", "points": outside_circle},
        ],
        "phantom_bodies": [],
        "bounds": bounds,
        "coordinate_system": "end_view",
        "summary": {
            "construction_status": (preview.get("completion") or {}).get("status", "source_only"),
            **({"remaining_web_mm": preview["construction_spec"]["validation"]["material_below_cuts_mm"]}
               if preview.get("construction_spec") else {}),
            "designation": "not_provided" if standard == "asme_b29_2m_open" else request.get("designation"),
            "standard": standard,
            "family": request.get("family"),
            "physical_tooth_count": tooth_count,
            "calculation_tooth_count": derived.get("calculation_tooth_count", tooth_count),
            "chain_pitch_mm": profile.get("pitch_mm"),
            "pitch_diameter_mm": derived.get("pitch_diameter_mm"),
            "outside_diameter_mm": derived.get("outside_diameter_mm"),
            **({"generator_root_diameter_mm" if tool_policy else "root_diameter_mm": derived.get("root_diameter_mm")} if not partial else {}),
            "profile_mechanics": derived.get("flank_model"),
            "tooth_width_mm": axial.get("tooth_width_mm"),
            "overall_width_mm": axial.get("overall_width_mm"),
            "profile_status": "user_defined_geometry" if user_radial else "source_faces_with_provisional_tip" if geometry.get("provisional_tip_paths") else "partial_reconstruction" if partial else "source_profile_with_tool_choice" if tool_policy else "reconstructed_from_source" if standard.startswith("din") else "dimensioned_nominal",
            "axial_status": "user_defined_geometry" if drawing_status == "user_defined_geometry" else "dimensioned" if drawing_status == "dimensioned_faces_with_schematic_body" else "interpreted" if standard.startswith("gost") or standard.startswith("din") else "incomplete",
            **({"accuracy_class": request.get("accuracy_class")} if standard.startswith("gost") else {}),
            **({"measuring_tooth_thickness_mm": derived["tooth_thickness_at_measuring_height_mm"], "measuring_height_mm": derived["tooth_measuring_height_mm"]} if "tooth_measuring_height_mm" in derived else {}),
            **({"span_measurement_mm": derived["span_measurement_mm"]} if "span_measurement_mm" in derived else {}),
            **({"over_pins_mm": derived["over_pins_mm"]} if "over_pins_mm" in derived else {}),
            **({"generator_root_radius_mm": derived["root_round_radius_mm"]} if tool_policy else {}),
            "data_source": profile.get("source"),
            "profile_form": derived.get("profile_form"),
            "face_width_mm": request.get("face_width_mm") if standard == "asme_b29_2m_open" else None,
            "tooth_tip_shape": derived.get("tip_shape") if standard == "asme_b29_2m_open" else None,
        },
        "profile_diagnostics": preview.get("diagnostics", {}),
        "dimensions": dimensions,
        "warnings": warnings,
        "warning_items": warning_items,
        "preview_window": {
            "tooth_gap_count": section["tooth_gap_count"],
            "visible_tooth_count": section["visible_tooth_count"],
            "section_style": "broken_out",
        },
    }


def _dedupe_points(points: list[list[float]], tolerance: float = 1e-9) -> list[list[float]]:
    result: list[list[float]] = []
    for point in points:
        if not result or math.dist(result[-1], point) > tolerance:
            result.append([float(point[0]), float(point[1])])
    return result


def _points(value: Any) -> list[list[float]]:
    result: list[list[float]] = []
    for point in list(value or []):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        result.append([float(point[0]), float(point[1])])
    return result


def _polar(radius: float, angle: float) -> list[float]:
    return [radius * math.sin(angle), radius * math.cos(angle)]


def _rotate_path(points: list[list[float]], angle: float) -> list[list[float]]:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        [point[0] * cosine + point[1] * sine, point[1] * cosine - point[0] * sine]
        for point in points
    ]


def _radial_arc(radius: float, start_angle: float, end_angle: float, count: int = 16) -> list[list[float]]:
    return [
        _polar(radius, start_angle + (end_angle - start_angle) * index / count)
        for index in range(count + 1)
    ]


def _section_break_contour(
    *,
    outside_radius: float,
    break_radius: float,
    left_angle: float,
    right_angle: float,
    wave_depth: float,
) -> list[list[float]]:
    """Close a cropped end-view sector with the timing-pulley break style."""
    points: list[list[float]] = []
    side_samples = 24
    for index in range(side_samples + 1):
        progress = index / side_samples
        smooth = progress * progress * (3.0 - 2.0 * progress)
        radius = outside_radius + (break_radius - outside_radius) * smooth
        radius += math.sin(progress * math.pi * 4.0) * wave_depth * 0.045
        angle = right_angle + math.sin(progress * math.pi) * wave_depth * 0.14 / outside_radius
        points.append(_polar(radius, angle))
    bottom_samples = 96
    for index in range(1, bottom_samples + 1):
        progress = index / bottom_samples
        angle = right_angle + (left_angle - right_angle) * progress
        radius = break_radius + math.sin(progress * math.pi * 8.0) * wave_depth
        points.append(_polar(radius, angle))
    for index in range(1, side_samples + 1):
        progress = index / side_samples
        smooth = progress * progress * (3.0 - 2.0 * progress)
        radius = break_radius + (outside_radius - break_radius) * smooth
        radius += math.sin(progress * math.pi * 4.0) * wave_depth * 0.045
        angle = left_angle - math.sin(progress * math.pi) * wave_depth * 0.14 / outside_radius
        points.append(_polar(radius, angle))
    return points


def _radial_break_contour(
    *,
    start_radius: float,
    end_radius: float,
    angle: float,
    wave_depth: float,
    count: int = 40,
) -> list[list[float]]:
    """Draw one wavy radial break edge for a cropped annular sector."""
    points: list[list[float]] = []
    for index in range(count + 1):
        progress = index / count
        radius = start_radius + (end_radius - start_radius) * progress
        envelope = math.sin(math.pi * progress) ** 0.35
        tangent_offset = math.sin(progress * math.pi * 6.0) * wave_depth * envelope
        local_angle = angle + tangent_offset / max(radius, 1e-9)
        points.append(_polar(radius, local_angle))
    return points


def _chain_section_preview(
    *,
    tooth_gap: list[list[float]],
    pitch_radius: float,
    outside_radius: float,
    root_radius: float,
    tooth_count: int,
    tooth_tip: list[list[float]] | None = None,
) -> dict[str, Any]:
    pitch_angle = 2.0 * math.pi / tooth_count
    sector: list[list[float]] = []
    for center_angle in (-pitch_angle, 0.0, pitch_angle):
        gap = _rotate_path(tooth_gap, center_angle)
        if sector:
            previous_angle = math.atan2(sector[-1][0], sector[-1][1])
            next_angle = math.atan2(gap[0][0], gap[0][1])
            if next_angle - previous_angle > 1e-9:
                sector.extend((_rotate_path(tooth_tip, center_angle - pitch_angle) if tooth_tip else _radial_arc(outside_radius, previous_angle, next_angle, count=10))[1:-1])
            if math.dist(sector[-1], gap[0]) <= 1e-9:
                gap = gap[1:]
        sector.extend(gap)
    left_angle = math.atan2(sector[0][0], sector[0][1])
    right_angle = math.atan2(sector[-1][0], sector[-1][1])
    groove_depth = outside_radius - root_radius
    break_radius = max(root_radius - groove_depth * 1.5, root_radius * 0.72)
    break_path = _section_break_contour(
        outside_radius=outside_radius,
        break_radius=break_radius,
        left_angle=left_angle,
        right_angle=right_angle,
        wave_depth=max(groove_depth * 0.08, outside_radius * 0.0015),
    )
    break_path[0] = list(sector[-1])
    break_path[-1] = list(sector[0])
    return {
        "profile_path": sector,
        "break_path": break_path,
        "outline": [*sector, *break_path[1:]],
        "pitch_circle": _radial_arc(pitch_radius, left_angle, right_angle, count=96),
        "outside_circle": _radial_arc(outside_radius, left_angle, right_angle, count=96),
        "break_radius": break_radius,
        "left_angle": left_angle,
        "right_angle": right_angle,
        "tooth_gap_count": 3,
        "visible_tooth_count": 2,
    }


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


def _adapt_chain(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    geometry = dict(preview.get("geometry") or {})
    derived = dict(preview.get("derived") or {})
    tooth_gap = _points(geometry.get("profile_path"))
    pitch_radius = float(derived.get("pitch_diameter") or 0.0) / 2.0
    outside_radius = float(derived.get("outside_diameter") or 0.0) / 2.0
    root_radius = float(derived.get("root_diameter") or 0.0) / 2.0
    standard_parameters = dict(derived.get("standard_parameters") or {})
    profile = dict(preview.get("profile") or {})
    row_count = int(request.get("row_count") or 1)
    axial_layout = derived["axial_layout"]
    tooth_width = axial_layout["tooth_width"]
    row_spacing = axial_layout["row_spacing"]
    connector_diameter = axial_layout.get("connector_diameter")
    secondary_view = {
        "view_mode": "side_section", "row_count": row_count,
        "tooth_width_mm": tooth_width,
        "row_spacing_mm": row_spacing,
        "total_width_mm": axial_layout["total_width"],
        "engagement_diameter_mm": profile["outside_diameter"],
        "connector_diameter_mm": connector_diameter,
        "width_source": axial_layout.get("width_source"),
        "row_spacing_source": profile.get("row_spacing_source", profile.get("dimensions_source")),
        "axial_layout_status": "dimensioned" if row_spacing else "schematic_missing_row_spacing",
        "connector_status": "dimensioned" if connector_diameter else "schematic_missing_plate_height",
    }
    tooth_count = int(request.get("tooth_count") or 1)
    groove_angle = 2.0 * math.pi / tooth_count
    section = _chain_section_preview(
        tooth_gap=tooth_gap,
        pitch_radius=pitch_radius,
        outside_radius=outside_radius,
        root_radius=root_radius,
        tooth_count=tooth_count,
    )
    profile_path = section["profile_path"]
    break_path = section["break_path"]
    closed = section["outline"]
    pitch_circle = section["pitch_circle"]
    dimension_start_radius = float(section["break_radius"])
    radial_dimensions = [
        {
            "key": "outside_diameter",
            "symbol": "Dₐ",
            "orientation": "radial",
            "start": _polar(dimension_start_radius, -groove_angle * 0.5),
            "end": _polar(outside_radius, -groove_angle * 0.5),
            "value": derived.get("outside_diameter"),
            "unit": "mm",
            "label_normal": 38,
            "label_tangent": 8,
        },
        {
            "key": "pitch_diameter",
            "symbol": "Dₚ",
            "orientation": "radial",
            "start": _polar(dimension_start_radius, groove_angle * 1.28),
            "end": _polar(pitch_radius, groove_angle * 1.28),
            "value": derived.get("pitch_diameter"),
            "unit": "mm",
            "label_normal": -36,
            "label_tangent": -8,
        },
        {
            "key": "root_diameter",
            "symbol": "Dᵣ",
            "orientation": "radial",
            "start": _polar(dimension_start_radius, -groove_angle),
            "end": _polar(root_radius, -groove_angle),
            "value": derived.get("root_diameter"),
            "unit": "mm",
            "label_normal": 34,
            "label_tangent": -8,
        },
    ]
    bounds = _bounds([closed], [pitch_circle, section["outside_circle"]])
    return {
        "ok": bool(preview.get("success")),
        "family": "chain_sprocket",
        "view_mode": "end",
        "secondary_view": secondary_view if row_count > 1 else None,
        "closed_points": [closed] if closed else [],
        "feature_paths": [profile_path] if profile_path else [],
        "guide_paths": [break_path] if break_path else [],
        "reference_paths": [
            {"key": "pitch_circle", "points": pitch_circle},
            {"key": "outside_circle", "points": section["outside_circle"]},
        ],
        "phantom_bodies": [],
        "bounds": bounds,
        "coordinate_system": "end_view",
        "summary": {
            "designation": request.get("designation"),
            "chain_type": request.get("chain_type"),
            "row_count": request.get("row_count", 1),
            "standard": preview.get("standard"),
            "profile_family": preview.get("profile_family"),
            "gost_profile_variant": preview.get("gost_profile_variant"),
            "tooth_gap_center_offset_mm": derived.get("tooth_gap_center_offset_mm"),
            "tooth_count": request.get("tooth_count"),
            "chain_pitch_mm": dict(preview.get("profile") or {}).get("pitch"),
            "pitch_diameter_mm": derived.get("pitch_diameter"),
            "outside_diameter_mm": derived.get("outside_diameter"),
            "root_diameter_mm": derived.get("root_diameter"),
            "roller_seating_radius_mm": derived.get("roller_seating_radius"),
            "tooth_flank_radius_mm": derived.get("tooth_flank_radius"),
            "profile_construction": standard_parameters.get("construction"),
        },
        "dimensions": radial_dimensions,
        "warnings": _warnings(preview),
        "preview_window": {
            "tooth_gap_count": section["tooth_gap_count"],
            "visible_tooth_count": section["visible_tooth_count"],
            "section_style": "broken_out",
        },
        "warning_items": _warning_items(
            preview,
            [
                "chain_profile_standard_scope",
                "chain_multirow_axial_preview_pending",
                "chain_pri_extended_profile",
            ],
        ),
    }


def _build_gear_spur_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return build_spur_gear_preview(payload)


def _build_gear_internal_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return build_internal_gear_preview(payload)


def _gear_sector_outline(period: list[list[float]], tooth_count: int, visible_pitches: int = 3) -> list[list[float]]:
    """Repeat one high-resolution tooth period into a symmetric cropped sector."""
    if len(period) < 8 or tooth_count < 4:
        return []
    core = period[:-1] if math.dist(period[0], period[-1]) <= 1e-9 else list(period)
    step = 2.0 * math.pi / tooth_count
    offset = -(visible_pitches - 1) / 2.0
    points: list[list[float]] = []
    for index in range(visible_pitches):
        rotated = _rotate_path(core, (offset + index) * step)
        if points:
            rotated = rotated[1:]
        points.extend(rotated)
    points.append(_rotate_path([core[0]], (offset + visible_pitches) * step)[0])
    # The middle tooth center must sit on the vertical axis. The period starts
    # at a gap center, so the assembled sector needs a half-pitch rotation.
    return _dedupe_points(_rotate_path(points, -0.5 * step))


def _adapt_gear_spur(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    if not preview.get("success"):
        return {
            "ok": False,
            "family": "gear_spur",
            "view_mode": "end",
            "closed_points": [],
            "feature_paths": [],
            "tone_paths": [],
            "guide_paths": [],
            "reference_paths": [],
            "phantom_bodies": [],
            "bounds": None,
            "summary": {},
            "derived": {},
            "measurements": {},
            "report": dict(preview.get("report") or {}),
            "dimensions": [],
            "warnings": list(preview.get("warnings") or []),
            "warning_items": list(preview.get("warning_items") or []),
            "errors": list(preview.get("errors") or []),
            "request": dict(request),
        }
    geometry = dict(preview.get("geometry") or {})
    summary = dict(preview.get("summary") or {})
    report = dict(preview.get("report") or {})
    period = _points(geometry.get("period_outline"))
    tooth_count = int(request.get("tooth_count") or summary.get("tooth_count") or 0)
    sector = _gear_sector_outline(period, tooth_count, 3)
    root_radius = float(geometry["root_radius_mm"])
    outside_radius = float(geometry["outside_radius_mm"])
    pitch_radius = float(geometry["pitch_radius_mm"])
    base_radius = float(geometry["base_radius_mm"])
    step = 2.0 * math.pi / max(1, tooth_count)
    if sector:
        left_angle = math.atan2(sector[0][0], sector[0][1])
        right_angle = math.atan2(sector[-1][0], sector[-1][1])
        tooth_depth = max(0.1, outside_radius - root_radius)
        break_radius = max(root_radius * 0.58, root_radius - tooth_depth * 1.6)
        break_path = _section_break_contour(
            outside_radius=root_radius,
            break_radius=break_radius,
            left_angle=left_angle,
            right_angle=right_angle,
            wave_depth=max(tooth_depth * 0.08, outside_radius * 0.0015),
        )
        break_path[0] = list(sector[-1])
        break_path[-1] = list(sector[0])
        outline = [*sector, *break_path[1:]]
    else:
        outline = []
        left_angle, right_angle, break_radius = -step, step, root_radius * 0.7
    closed = _dedupe_points(outline) if outline else []
    reference_paths = [
        {"key": "pitch_circle", "points": _radial_arc(pitch_radius, left_angle, right_angle, count=96)},
        {"key": "base_circle", "points": _radial_arc(base_radius, left_angle, right_angle, count=96)},
    ]
    bounds = _bounds([closed] if closed else [], [item["points"] for item in reference_paths])
    dimension_start = max(1.0, break_radius * 1.12)
    gap_angle = 0.5 * step
    dimensions = [
        {
            "key": "outside_diameter",
            "symbol": "dₐ",
            "orientation": "radial",
            "start": _polar(dimension_start, step),
            "end": _polar(outside_radius, step),
            "value": summary.get("outside_diameter_mm"),
            "unit": "mm",
            "label_normal": 26,
            "label_tangent": 0,
        },
        {
            "key": "pitch_diameter",
            "symbol": "d",
            "orientation": "radial",
            "start": _polar(dimension_start, -gap_angle),
            "end": _polar(pitch_radius, -gap_angle),
            "value": summary.get("pitch_diameter_mm"),
            "unit": "mm",
            "label_normal": -26,
            "label_tangent": 0,
        },
        {
            "key": "root_diameter",
            "symbol": "d_f",
            "orientation": "radial",
            "start": _polar(dimension_start, gap_angle),
            "end": _polar(root_radius, gap_angle),
            "value": summary.get("root_diameter_mm"),
            "unit": "mm",
            "label_normal": 24,
            "label_tangent": 0,
        },
    ]
    warning_items = list(preview.get("warning_items") or [])
    warnings = list(preview.get("warnings") or [])
    period_items = [
        {
            "radius": math.hypot(float(point[0]), float(point[1])),
            "angle": math.atan2(float(point[0]), float(point[1])),
        }
        for point in _points(geometry.get("period_outline"))
    ]
    radial_tolerance = max(1e-6, 1e-9 * outside_radius)
    step_angle = 2.0 * math.pi / max(1, tooth_count)

    def _radial_runs(predicate) -> list[tuple[int, int]]:
        runs: list[tuple[int, int]] = []
        index = 0
        while index < len(period_items):
            if not predicate(period_items[index]):
                index += 1
                continue
            start = index
            while index + 1 < len(period_items) and predicate(period_items[index + 1]):
                index += 1
            runs.append((start, index))
            index += 1
        return runs

    def _first_long_run(runs):
        return next(((start, end) for start, end in runs if end > start), None)

    def _last_long_run(runs):
        for start, end in reversed(runs):
            if end > start:
                return (start, end)
        return None

    local_pairs: list[tuple[str, dict[str, float], dict[str, float]]] = []
    tip_run = _first_long_run(
        _radial_runs(lambda item: item["radius"] >= outside_radius - radial_tolerance)
    )
    if tip_run is not None:
        local_pairs.append(
            ("tip", period_items[tip_run[0]], period_items[tip_run[1]])
        )
    root_runs = _radial_runs(lambda item: item["radius"] <= root_radius + radial_tolerance)
    root_start = _first_long_run(root_runs)
    root_end = _last_long_run(root_runs)
    if root_start is not None and root_end is not None:
        root_first = period_items[root_start[1]]
        root_second = dict(period_items[root_end[0]])
        root_second["angle"] -= step_angle
        local_pairs.append(("root", root_first, root_second))

    tip_edges: list[dict[str, float]] = []
    root_edges: list[dict[str, float]] = []
    for index in range(max(1, tooth_count)):
        offset = -index * step_angle
        for kind, first, second in local_pairs:
            target = tip_edges if kind == "tip" else root_edges
            target.append({"radius": first["radius"], "angle": first["angle"] + offset})
            target.append({"radius": second["radius"], "angle": second["angle"] + offset})
    for check in list(report.get("checks") or []):
        if check.get("status") != "warning":
            continue
        if check.get("code") == "gear_span_measurement":
            message = "Span measurement does not contact the flanks between the root and outside circles."
            code = "gear_span_unusable"
        elif check.get("code") == "gear_over_pin":
            message = "The selected or nominal pin does not fit below the tooth tips."
            code = "gear_over_pin_unusable"
        else:
            continue
        warning_items.append({"code": code, "severity": "warning", "message": message})
        warnings.append(message)
    return {
        "ok": bool(preview.get("success")),
        "family": "gear_spur",
        "view_mode": "end",
        "closed_points": [closed] if closed else [],
        "feature_paths": [],
        "tone_paths": (
            [{"points": closed, "tone": "exhaust", "width": 2.4, "fill": "rgba(227,170,79,.05)"}]
            if closed
            else []
        ),
        "guide_paths": [],
        "reference_paths": reference_paths,
        "phantom_bodies": [],
        "bounds": bounds,
        "coordinate_system": geometry.get("coordinate_system"),
        "summary": summary,
        "derived": preview.get("derived"),
        "measurements": preview.get("measurements"),
        "report": report,
        "dimensions": dimensions,
        "warnings": warnings,
        "warning_items": warning_items,
        "preview_window": {
            "tooth_gap_count": 3,
            "visible_tooth_count": 3,
            "section_style": "broken_out",
        },
        "secondary_view": {
            "family": "gear_spur",
            "tip_edges": tip_edges,
            "root_edges": root_edges,
            "face_width_mm": summary.get("face_width_mm"),
            "outside_diameter_mm": summary.get("outside_diameter_mm"),
            "pitch_diameter_mm": summary.get("pitch_diameter_mm"),
            "root_diameter_mm": summary.get("root_diameter_mm"),
            "tooth_count": tooth_count,
            "tip_thickness_mm": summary.get("tip_thickness_mm"),
            "tip_chamfer_mm": summary.get("tip_chamfer_mm", 0.0),
            "tip_chamfer_angle_deg": summary.get("tip_chamfer_angle_deg", 45.0),
            "tip_chamfer_depth_mm": summary.get("tip_chamfer_depth_mm", 0.0),
            "helix_angle_deg": summary.get("helix_angle_deg", 0.0),
            "hand": summary.get("hand", "right"),
            "lead_mm": summary.get("lead_mm", 0.0),
            "axial_pitch_mm": summary.get("axial_pitch_mm", 0.0),
            "axial_overlap": summary.get("axial_overlap", 0.0),
        },
        "request": dict(request),
    }


def _adapt_gear_internal(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    warning_items = list(preview.get("warning_items") or [])
    warnings = list(preview.get("warnings") or [])
    if not preview.get("success"):
        return {
            "ok": False,
            "family": "gear_internal",
            "view_mode": "end",
            "closed_points": [],
            "feature_paths": [],
            "tone_paths": [],
            "guide_paths": [],
            "reference_paths": [],
            "phantom_bodies": [],
            "bounds": None,
            "summary": {},
            "derived": {},
            "measurements": {},
            "report": dict(preview.get("report") or {}),
            "dimensions": [],
            "warnings": warnings,
            "warning_items": warning_items,
            "errors": list(preview.get("errors") or []),
            "request": dict(request),
        }
    geometry = dict(preview.get("geometry") or {})
    summary = dict(preview.get("summary") or {})
    report = dict(preview.get("report") or {})
    tooth_count = int(summary.get("tooth_count") or request.get("tooth_count") or 0)
    ring_radius = float(geometry.get("ring_outside_radius_mm") or 0.0)
    pitch_radius = float(geometry.get("pitch_radius_mm") or 0.0)
    base_radius = float(geometry.get("base_radius_mm") or 0.0)
    tip_radius = float(geometry.get("outside_radius_mm") or 0.0)
    root_radius = float(geometry.get("root_radius_mm") or 0.0)
    period = _points(geometry.get("period_outline"))
    inner_path = _gear_sector_outline(period, tooth_count, 3)
    step = 2.0 * math.pi / max(1, tooth_count)
    if inner_path:
        left_angle = math.atan2(inner_path[0][0], inner_path[0][1])
        right_angle = math.atan2(inner_path[-1][0], inner_path[-1][1])
        outer_path = _radial_arc(ring_radius, right_angle, left_angle, count=96)
        wave_depth = max(0.12 * (root_radius - tip_radius), 0.002 * ring_radius)
        right_break = _radial_break_contour(
            start_radius=math.hypot(*inner_path[-1]),
            end_radius=ring_radius,
            angle=right_angle,
            wave_depth=wave_depth,
        )
        left_break = _radial_break_contour(
            start_radius=ring_radius,
            end_radius=math.hypot(*inner_path[0]),
            angle=left_angle,
            wave_depth=wave_depth,
        )
        right_break[0] = list(inner_path[-1])
        right_break[-1] = _polar(ring_radius, right_angle)
        left_break[0] = _polar(ring_radius, left_angle)
        left_break[-1] = list(inner_path[0])
        outline = _dedupe_points([
            *inner_path,
            *right_break[1:],
            *outer_path[1:],
            *left_break[1:],
        ])
    else:
        left_angle, right_angle = -1.5 * step, 1.5 * step
        outer_path = []
        outline = []
    reference_paths = [
        {"key": "pitch_circle", "points": _radial_arc(pitch_radius, left_angle, right_angle, count=96)},
        {"key": "tip_circle", "points": _radial_arc(tip_radius, left_angle, right_angle, count=96)},
        {"key": "root_circle", "points": _radial_arc(root_radius, left_angle, right_angle, count=96)},
    ]
    tone_paths: list[dict[str, Any]] = []
    if outline:
        tone_paths.append(
            {
                "points": outline,
                "tone": "exhaust",
                "width": 2.2,
                "fill": "rgba(227,170,79,.09)",
                "stroke": "#e3aa4f",
            }
        )
    bounds = _bounds(
        [outline] if outline else [],
        [item["points"] for item in reference_paths],
    )
    dimension_start = max(1.0, 0.88 * tip_radius)
    sector_span = right_angle - left_angle
    dimension_angles = [
        left_angle + 0.18 * sector_span,
        left_angle + 0.50 * sector_span,
        left_angle + 0.82 * sector_span,
    ]
    dimensions = [
        {
            "key": "pitch_diameter",
            "symbol": "d",
            "orientation": "radial",
            "start": _polar(dimension_start, dimension_angles[0]),
            "end": _polar(pitch_radius, dimension_angles[0]),
            "value": summary.get("pitch_diameter_mm"),
            "unit": "mm",
            "label_normal": -24,
            "label_tangent": 0,
        },
        {
            "key": "root_diameter",
            "symbol": "d_f",
            "orientation": "radial",
            "start": _polar(dimension_start, dimension_angles[1]),
            "end": _polar(root_radius, dimension_angles[1]),
            "value": summary.get("root_diameter_mm"),
            "unit": "mm",
            "label_normal": 24,
            "label_tangent": 0,
        },
        {
            "key": "tip_diameter",
            "symbol": "d_a",
            "orientation": "radial",
            "start": _polar(dimension_start, dimension_angles[2]),
            "end": _polar(tip_radius, dimension_angles[2]),
            "value": summary.get("tip_diameter_mm"),
            "unit": "mm",
            "label_normal": -24,
            "label_tangent": 0,
        },
    ]
    tip_half = math.pi / max(1, tooth_count) - float(geometry.get("tip_space_half_angle_rad") or 0.0)
    root_half = float(geometry.get("root_space_half_angle_rad") or 0.0)
    tip_edges: list[dict[str, float]] = []
    root_edges: list[dict[str, float]] = []
    for index in range(max(1, tooth_count)):
        center = index * step
        tip_edges.append({"radius": tip_radius, "angle": center + tip_half})
        tip_edges.append({"radius": tip_radius, "angle": center - tip_half})
        root_edges.append({"radius": root_radius, "angle": center + root_half})
        root_edges.append({"radius": root_radius, "angle": center - root_half})
    span = dict((preview.get("measurements") or {}).get("span") or {})
    if not span.get("usable"):
        message = "Span measurement does not contact the internal flanks between the tip and root circles."
        warning_items.append({"code": "gear_span_unusable", "severity": "warning", "message": message})
        warnings.append(message)
    over_pin = dict((preview.get("measurements") or {}).get("over_pin") or {})
    if over_pin.get("available") is False:
        message = "Over-pin control is not performed for helical internal gears."
        warning_items.append(
            {"code": "gear_internal_over_pin_not_performed", "severity": "warning", "message": message}
        )
        warnings.append(message)
    elif not over_pin.get("fits_below_tips"):
        message = "The selected or nominal pin does not fit the internal tooth space."
        warning_items.append({"code": "gear_over_pin_unusable", "severity": "warning", "message": message})
        warnings.append(message)
    return {
        "ok": bool(preview.get("success")),
        "family": "gear_internal",
        "view_mode": "end",
        "closed_points": [outline] if outline else [],
        "feature_paths": [],
        "tone_paths": tone_paths,
        "guide_paths": [],
        "reference_paths": reference_paths,
        "phantom_bodies": [],
        "bounds": bounds,
        "coordinate_system": geometry.get("coordinate_system"),
        "summary": summary,
        "derived": preview.get("derived"),
        "measurements": preview.get("measurements"),
        "report": report,
        "dimensions": dimensions,
        "warnings": warnings,
        "warning_items": warning_items,
        "preview_window": {
            "tooth_gap_count": 3,
            "visible_tooth_count": 3,
            "section_style": "cropped_sector",
        },
        "secondary_view": {
            "family": "gear_internal",
            "internal": True,
            "tip_edges": tip_edges,
            "root_edges": root_edges,
            "face_width_mm": summary.get("face_width_mm"),
            "outside_diameter_mm": summary.get("ring_outside_diameter_mm"),
            "pitch_diameter_mm": summary.get("pitch_diameter_mm"),
            "root_diameter_mm": summary.get("root_diameter_mm"),
            "tip_diameter_mm": summary.get("tip_diameter_mm"),
            "tooth_count": tooth_count,
            "tip_thickness_mm": summary.get("tip_thickness_mm"),
            "root_transition_size_mm": summary.get("root_transition_size_mm"),
            "tip_chamfer_mm": summary.get("tip_chamfer_mm", 0.0),
            "tip_chamfer_angle_deg": summary.get("tip_chamfer_angle_deg", 45.0),
            "tip_chamfer_depth_mm": summary.get("tip_chamfer_depth_mm", 0.0),
            "helix_angle_deg": summary.get("helix_angle_deg", 0.0),
            "hand": summary.get("hand", "right"),
            "lead_mm": summary.get("lead_mm", 0.0),
            "axial_pitch_mm": summary.get("axial_pitch_mm", 0.0),
            "axial_overlap": summary.get("axial_overlap", 0.0),
        },
        "request": dict(request),
    }


def _build_gear_bevel_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return build_bevel_gear_preview(payload)


def _adapt_gear_bevel(preview: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    if not preview.get("success"):
        return {
            "ok": False,
            "family": "gear_bevel",
            "view_mode": "end",
            "closed_points": [],
            "feature_paths": [],
            "tone_paths": [],
            "guide_paths": [],
            "reference_paths": [],
            "phantom_bodies": [],
            "bounds": None,
            "summary": {},
            "derived": {},
            "measurements": {},
            "report": dict(preview.get("report") or {}),
            "dimensions": [],
            "warnings": list(preview.get("warnings") or []),
            "warning_items": list(preview.get("warning_items") or []),
            "errors": list(preview.get("errors") or []),
            "secondary_view": None,
            "request": dict(request),
        }
    geometry = dict(preview.get("geometry") or {})
    summary = dict(preview.get("summary") or {})
    report = dict(preview.get("report") or {})
    period = _points(geometry.get("end_view_period"))
    tooth_count = int(request.get("tooth_count") or summary.get("tooth_count") or 0)
    sector = _gear_sector_outline(period, tooth_count, 3)
    tip_radius = float(geometry.get("tip_radius_mm") or 0.0)
    pitch_radius = float(geometry.get("pitch_radius_mm") or 0.0)
    root_radius = float(geometry.get("root_radius_mm") or 0.0)
    gap_root_radius = root_radius
    root_line = (geometry.get("tooth_lines") or {}).get("root_line") or []
    if len(root_line) >= 1:
        gap_root_radius = max(1e-6, float(root_line[0][1]))
    step = 2.0 * math.pi / max(1, tooth_count)
    if sector:
        left_angle = math.atan2(sector[0][0], sector[0][1])
        right_angle = math.atan2(sector[-1][0], sector[-1][1])
        tooth_depth = max(0.1, tip_radius - gap_root_radius)
        break_radius = max(gap_root_radius * 0.58, gap_root_radius - tooth_depth * 1.6)
        break_path = _section_break_contour(
            outside_radius=gap_root_radius,
            break_radius=break_radius,
            left_angle=left_angle,
            right_angle=right_angle,
            wave_depth=max(tooth_depth * 0.08, tip_radius * 0.0015),
        )
        break_path[0] = list(sector[-1])
        break_path[-1] = list(sector[0])
        outline = [*sector, *break_path[1:]]
    else:
        outline = []
        left_angle, right_angle, break_radius = -step, step, gap_root_radius * 0.7
    closed = _dedupe_points(outline) if outline else []
    reference_paths = [
        {"key": "tip_circle", "points": _radial_arc(tip_radius, left_angle, right_angle, count=96)},
        {"key": "pitch_circle", "points": _radial_arc(pitch_radius, left_angle, right_angle, count=96)},
        {"key": "root_circle", "points": _radial_arc(root_radius, left_angle, right_angle, count=96)},
    ]
    bounds = _bounds(
        [closed] if closed else [],
        [item["points"] for item in reference_paths],
    )
    dimension_start = max(1.0, break_radius * 1.12)
    gap_angle = 0.5 * step
    dimensions = [
        {
            "key": "tip_diameter",
            "symbol": "dₐₑ",
            "orientation": "radial",
            "start": _polar(dimension_start, step),
            "end": _polar(tip_radius, step),
            "value": summary.get("outer_tip_diameter_mm"),
            "unit": "mm",
            "label_normal": 52,
            "label_tangent": 62,
        },
        {
            "key": "pitch_diameter",
            "symbol": "dₑ",
            "orientation": "radial",
            "start": _polar(dimension_start, -gap_angle),
            "end": _polar(pitch_radius, -gap_angle),
            "value": summary.get("outer_pitch_diameter_mm"),
            "unit": "mm",
            "label_normal": -30,
            "label_tangent": -6,
        },
        {
            "key": "root_diameter",
            "symbol": "d_fₑ",
            "orientation": "radial",
            "start": _polar(dimension_start, gap_angle),
            "end": _polar(root_radius, gap_angle),
            "value": summary.get("outer_root_diameter_mm"),
            "unit": "mm",
            "label_normal": 22,
            "label_tangent": 2,
        },
    ]
    axial = dict((geometry.get("axial_section") or {}))
    outline = [[float(point[0]), float(point[1])] for point in (geometry.get("blank_profile") or [])]
    tooth_lines = {
        key: [[float(point[0]), float(point[1])] for point in (value or [])]
        for key, value in (geometry.get("tooth_lines") or {}).items()
    }
    secondary_view = {
        "family": "gear_bevel",
        "tooth_type": "straight",
        "outline": outline,
        "pitch_line": tooth_lines.get("pitch_line") or [],
        "root_line": tooth_lines.get("root_line") or [],
        "tooth_lines": tooth_lines,
        "back_face_x_mm": float(geometry.get("back_face_x_mm") or 0.0),
        "front_face_x_mm": float(geometry.get("front_face_x_mm") or 0.0),
        "back_face_radius_mm": float(geometry.get("back_face_radius_mm") or 0.0),
        "front_face_radius_mm": float(geometry.get("front_face_radius_mm") or 0.0),
        "tip_corner_x_mm": float(geometry.get("tip_corner_x_mm") or 0.0),
        "tip_corner_radius_mm": float(geometry.get("tip_corner_radius_mm") or 0.0),
        "inner_tip_corner_x_mm": float(geometry.get("inner_tip_corner_x_mm") or 0.0),
        "inner_tip_corner_radius_mm": float(geometry.get("inner_tip_corner_radius_mm") or 0.0),
        "blank_width_mm": summary.get("blank_width_mm"),
        "back_face_diameter_mm": summary.get("back_face_diameter_mm"),
        "front_face_diameter_mm": summary.get("front_face_diameter_mm"),
        "face_width_mm": summary.get("face_width_mm"),
        "outer_tip_diameter_mm": summary.get("outer_tip_diameter_mm"),
        "outer_pitch_diameter_mm": summary.get("outer_pitch_diameter_mm"),
        "outer_root_diameter_mm": summary.get("outer_root_diameter_mm"),
        "outer_cone_distance_mm": summary.get("outer_cone_distance_mm"),
        "rim_back_extension_mm": summary.get("rim_back_extension_mm"),
        "rim_front_extension_mm": summary.get("rim_front_extension_mm"),
        "pitch_cone_angle_deg": summary.get("pitch_cone_angle_deg"),
        "face_cone_angle_deg": summary.get("face_cone_angle_deg"),
        "root_cone_angle_deg": summary.get("root_cone_angle_deg"),
        "tooth_count": tooth_count,
        "virtual_tooth_count": summary.get("virtual_tooth_count"),
    }
    return {
        "ok": bool(preview.get("success")),
        "family": "gear_bevel",
        "view_mode": "end",
        "closed_points": [closed] if closed else [],
        "feature_paths": [],
        "tone_paths": (
            [{"points": closed, "tone": "exhaust", "width": 2.4, "fill": "rgba(227,170,79,.05)"}]
            if closed
            else []
        ),
        "guide_paths": [],
        "reference_paths": reference_paths,
        "phantom_bodies": [],
        "bounds": bounds,
        "coordinate_system": geometry.get("coordinate_system"),
        "summary": summary,
        "derived": preview.get("derived"),
        "measurements": preview.get("measurements"),
        "report": report,
        "dimensions": dimensions,
        "warnings": list(preview.get("warnings") or []),
        "warning_items": list(preview.get("warning_items") or []),
        "preview_window": {
            "tooth_gap_count": 3,
            "visible_tooth_count": 3,
            "section_style": "cropped_sector",
        },
        "secondary_view": secondary_view,
        "request": dict(request),
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
    "chain_sprocket": PreviewModule(
        kind="chain_sprocket",
        name="Втулочно-роликовая звездочка",
        description="Общий модуль для стандартных цепей: ISO 606, ГОСТ 13568 и ГОСТ 21834.",
        standard="ISO 606:2015 / ГОСТ 13568-2017 / ГОСТ 21834-87",
        request_model=ChainSprocketPreviewRequest,
        defaults={
            "designation": "ISO_08B",
            "chain_type": "roller",
            "tooth_count": 19,
            "row_count": 1,
            "gost_profile_variant": "offset",
        },
        builder=_build_chain_preview,
        adapter=_adapt_chain,
        subgroup="chain_drives",
        family="chain_sprockets",
        build=True,
        icon="/static/icons/roller-sprocket.svg",
        selection=chain_profile_selection(),
    ),
    "silent_chain_sprocket": PreviewModule(
        kind="silent_chain_sprocket",
        name="Звёздочка пластинчатой зубчатой цепи",
        description="Торцевой профиль и осевой вид для ГОСТ, DIN- и ASME-compatible открытых реконструкций.",
        standard="ГОСТ 13552-81 / ГОСТ 13576-81; DIN/ASME open reconstructions",
        request_model=SilentChainSelectionRequest,
        defaults=SilentChainSelectionRequest(designation="PZ-1-19.05-74-45", physical_tooth_count=23, accuracy_class=1).model_dump(),
        builder=_build_silent_chain_preview,
        adapter=_adapt_silent_chain,
        subgroup="chain_drives",
        family="chain_sprockets",
        build=True,
        preview_available=True,
        icon="/static/icons/silent-sprocket.svg",
        selection=silent_chain_selection(),
    ),
    "gear_spur": PreviewModule(
        kind="gear_spur",
        name="Цилиндрическая шестерня (прямозубая / косозубая)",
        description="Внешнее цилиндрическое колесо: четыре системы исходного контура, эвольвента торцового сечения, трохоида впадины, косой зуб и контрольные размеры.",
        standard="ГОСТ 13755-2015 / ГОСТ 9587-81 / ГОСТ Р 50531-93 / ISO 53:1998 (nominal)",
        request_model=SpurGearRequest,
        defaults=SpurGearRequest().model_dump(exclude_none=True),
        builder=_build_gear_spur_preview,
        adapter=_adapt_gear_spur,
        subgroup="gear_drives",
        family="gear_drives",
        build=True,
        preview_available=True,
        icon="/static/icons/gear-spur.svg",
        selection=gear_selection(),
    ),
    "gear_internal": PreviewModule(
        kind="gear_internal",
        name="Цилиндрическое колесо внутреннего зацепления",
        description="Зубчатый венец: явный внешний диаметр кольцевой заготовки, впадины с внутренней поверхности, эвольвента торцового сечения и контрольные размеры.",
        standard="ГОСТ 19274-73 / ГОСТ 13755-2015 / ГОСТ 9587-81 / ГОСТ Р 50531-93 / ISO 53:1998 (nominal)",
        request_model=InternalGearRequest,
        defaults=InternalGearRequest().model_dump(exclude_none=True),
        builder=_build_gear_internal_preview,
        adapter=_adapt_gear_internal,
        subgroup="gear_drives",
        family="gear_drives",
        build=True,
        preview_available=True,
        icon="/static/icons/gear-internal.svg",
        selection=gear_selection(),
    ),
    "gear_bevel": PreviewModule(
        kind="gear_bevel",
        name="Коническая шестерня (прямозубая)",
        description="Коническое колесо с прямыми зубьями: макрогеометрия ГОСТ 19624-74, виртуальное колесо Тредголда, торцовое и осевое сечение с контрольными размерами.",
        standard="ГОСТ 19624-74 / ГОСТ 13754-68 (nominal)",
        request_model=BevelGearRequest,
        defaults=BevelGearRequest().model_dump(exclude_none=True),
        builder=_build_gear_bevel_preview,
        adapter=_adapt_gear_bevel,
        subgroup="gear_drives",
        family="gear_drives",
        build=True,
        preview_available=True,
        icon="/static/icons/gear-bevel.svg",
        selection=bevel_gear_selection(),
    ),
    "shaft_spline": PreviewModule(
        kind="shaft_spline",
        name="Вал со шлицами (прямобочные)",
        description="Прямобочные шлицы ГОСТ 1139-80 на валу: торцевой профиль, посадки, фаски c x 45.",
        standard="ГОСТ 1139-80",
        request_model=StraightSplineRequest,
        defaults={
            "standard": "gost_1139_80",
            "series": "light",
            "designation": "8x36x40",
            "body": "shaft",
            "centering": "inner_diameter",
            "execution": "auto",
            "length_mm": 30.0,
            "include_tip_chamfer": True,
        },
        builder=build_spline_preview,
        adapter=adapt_spline_preview,
        group="connections",
        subgroup="splines",
        family="spline_joints",
        build=True,
        preview_available=True,
        icon="/static/icons/shaft-spline.svg",
        selection=spline_selection(),
    ),
    "hub_spline": PreviewModule(
        kind="hub_spline",
        name="Втулка со шлицами (прямобочные)",
        description="Внутренние прямобочные шлицы ГОСТ 1139-80: кольцевая заготовка, пазы d/D, посадки.",
        standard="ГОСТ 1139-80",
        request_model=StraightSplineRequest,
        defaults={
            "standard": "gost_1139_80",
            "series": "light",
            "designation": "8x36x40",
            "body": "hub",
            "centering": "inner_diameter",
            "length_mm": 30.0,
            "hub_outside_diameter_mm": 55.0,
        },
        builder=build_spline_preview,
        adapter=adapt_spline_preview,
        group="connections",
        subgroup="splines",
        family="spline_joints",
        build=True,
        preview_available=True,
        icon="/static/icons/hub-spline.svg",
        selection=spline_selection(),
    ),
    "camshaft_lobe": PreviewModule(
        kind="camshaft_lobe",
        name="Кулачок ГРМ",
        description="Профиль кулачка распределительного вала по фазам клапана и кинематике привода.",
        standard="Инженерная методика; профиль кулачка не стандартизован",
        request_model=CamshaftPhasesRequest,
        defaults={
            "active_lobe": "intake",
            "intake_open_deg": -10.0,
            "intake_close_deg": 50.0,
            "exhaust_open_deg": -45.0,
            "exhaust_close_deg": 15.0,
        },
        builder=build_camshaft_phases_preview,
        adapter=adapt_camshaft_phases,
        group="valvetrain",
        subgroup="valvetrain",
        family="camshafts",
        build=True,
        icon="/static/icons/cam.svg",
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
        raise ValueError(f"{module.kind} has no CAD planning or build yet")
    request = module.request_model.model_validate(payload)
    normalized_request = request.model_dump(exclude_none=True)
    if module.kind == "camshaft_lobe":
        if request.step != "cam":
            raise ValueError("Open the Cam step to plan or build the calculated cam profile")
        from kompas_mcp.cams.cad import build_cam_plan
        plan = build_cam_plan(cam_profile_request(request), width=request.cam_width,
                              rotation_deg=request.cam_rotation_deg, tolerance=request.cad_tolerance)
        return {k:v for k,v in plan.items() if k not in {"curve", "base", "source_request"}}
    if module.kind == "chain_sprocket":
        return build_chain_sprocket_plan(**normalized_request)
    if module.kind == "gear_spur":
        from kompas_mcp.gears.cad import build_gear_spur_plan
        return build_gear_spur_plan(normalized_request)
    if module.kind == "gear_internal":
        from kompas_mcp.gears.cad import build_internal_gear_plan
        return build_internal_gear_plan(normalized_request)
    if module.kind == "gear_bevel":
        from kompas_mcp.gears.cad import build_bevel_gear_plan
        return build_bevel_gear_plan(normalized_request)
    if module.kind in ("shaft_spline", "hub_spline"):
        from kompas_mcp.connections.cad import build_straight_spline_plan
        return build_straight_spline_plan(normalized_request)
    if module.kind == "silent_chain_sprocket":
        preview = build_silent_chain_preview(normalized_request)
        missing = preview["completion"]["missing_fields"]
        if missing:
            raise ValueError("Complete construction dimensions: " + ", ".join(missing))
        return build_silent_chain_plan(preview["construction_spec"], normalized_request)
    return build_managed_pulley_plan(module.kind, normalized_request)
