"""Layer 3 create-only CAD plans for straight-sided splines (ГОСТ 1139-80).

Вал: цилиндрическая заготовка ØD, до двух торцевых фасок c x 45 (тем же
приёмом, что у шестерён), один числовой паз с точными отрезками и дугами и
круговой массив на z пазов. Втулка: кольцевая заготовка с явным наружным
диаметром, расточка до внутреннего диаметра d, один паз с дном D и массивы.
Планы numeric create-only: смена входов требует нового построения.
"""
from __future__ import annotations

import math
from typing import Any

from .splines.spec import StraightSplineRequest
from .splines.straight import (
    STANDARD_CODE,
    build_spline_geometry,
    build_straight_spline_preview,
    resolve_spline_size,
)

FAMILY_CODE = 11
OWNERSHIP_SCHEMA = "geomwright.managed_spline_straight"
PLAN_STAGE = "straight_spline_cad_plan"
RECIPE_SCHEMA = "geomwright.spline.recipe"


def _rotate(point: list[float], angle: float) -> list[float]:
    x, y = float(point[0]), float(point[1])
    return [x * math.cos(angle) + y * math.sin(angle), -x * math.sin(angle) + y * math.cos(angle)]


def _validate_contour(entities: list[dict[str, Any]]) -> None:
    if len(entities) < 4:
        raise ValueError("Контур паза шлица содержит меньше четырёх сущностей")
    tolerance = 1e-6
    for index, entity in enumerate(entities):
        following = entities[(index + 1) % len(entities)]
        if math.dist(entity["end"], following["start"]) > tolerance:
            raise ValueError("Сущности контура паза шлица не соединены по порядку")


def _full_outline(period: list[list[float]], tooth_count: int) -> list[list[float]]:
    step = 2.0 * math.pi / tooth_count
    points: list[list[float]] = []
    for index in range(tooth_count):
        rotated = [_rotate(point, index * step) for point in period]
        points.extend(rotated)
    return points


def build_straight_spline_plan(
    request: dict[str, Any],
    *,
    name: str = "Geomwright spline",
    length_mm: float | None = None,
) -> dict[str, Any]:
    """Собрать create-only план вала или втулки без обращения к KOMPAS."""
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")
    model = StraightSplineRequest.model_validate(request)
    if length_mm is not None and float(length_mm) > 0.0:
        model = model.model_copy(update={"length_mm": float(length_mm)})
    preview = build_straight_spline_preview(model)
    if not preview.get("success"):
        errors = ", ".join(str(item) for item in preview.get("errors") or [])
        raise ValueError("Spline preview rejected the request: " + (errors or "invalid geometry"))
    geometry = build_spline_geometry(model)
    _validate_contour(geometry.space_entities)
    size = geometry.size
    length = geometry.length_mm
    tooth_count = size.tooth_count
    outer_radius = 0.5 * size.outer_diameter_mm
    outline = _full_outline(geometry.period_outline, tooth_count) if geometry.period_outline else []
    if not outline:
        raise ValueError("Полный контур шлицевого венца не построен")

    operations: list[dict[str, Any]] = []
    if geometry.body == "shaft":
        operations.append(
            {
                "id": "blank",
                "scenario": "cylindrical_blank",
                "params": {
                    "name": f"{requested_name} blank",
                    "sketch_name": f"{requested_name} blank sketch",
                    "outside_diameter": 2.0 * outer_radius,
                    "width": length,
                    "plane": "YOZ",
                    "axis": "x_axis",
                    "parameterize": False,
                    "require_fully_defined": False,
                },
            }
        )
        if model.include_tip_chamfer and geometry.chamfer_mm > 0.0:
            chamfer = geometry.chamfer_mm
            operations.extend(
                [
                    {
                        "id": "tip_chamfer_face_a",
                        "scenario": "rotational_cut",
                        "params": {
                            "name": f"{requested_name} tip chamfer A",
                            "plane": "XOY",
                            "axis": "blank.axis",
                            "profile_points": [
                                [-length, outer_radius - chamfer],
                                [-length + chamfer, outer_radius],
                                [-length, outer_radius],
                            ],
                            "angle_degrees": 360.0,
                            "require_fully_defined": False,
                        },
                    },
                    {
                        "id": "tip_chamfer_face_b",
                        "scenario": "rotational_cut",
                        "params": {
                            "name": f"{requested_name} tip chamfer B",
                            "plane": "XOY",
                            "axis": "blank.axis",
                            "profile_points": [
                                [0.0, outer_radius - chamfer],
                                [-chamfer, outer_radius],
                                [0.0, outer_radius],
                            ],
                            "angle_degrees": 360.0,
                            "require_fully_defined": False,
                        },
                    },
                ]
            )
        blank_reference = "blank.body"
    else:
        hub_radius = float(geometry.hub_outside_radius_mm or 0.0)
        if hub_radius <= 0.0:
            raise ValueError("Наружный радиус втулки не определён")
        operations.append(
            {
                "id": "blank",
                "scenario": "cylindrical_blank",
                "params": {
                    "name": f"{requested_name} ring blank",
                    "sketch_name": f"{requested_name} ring blank sketch",
                    "outside_diameter": 2.0 * hub_radius,
                    "width": length,
                    "plane": "YOZ",
                    "axis": "x_axis",
                    "parameterize": False,
                    "require_fully_defined": False,
                },
            }
        )
        bore_radius = 0.5 * size.inner_diameter_mm
        operations.append(
            {
                "id": "bore_cut",
                "scenario": "rotational_cut",
                "params": {
                    "name": f"{requested_name} bore cut",
                    "plane": "XOY",
                    "axis": "blank.axis",
                    "profile_points": [
                        [-length - 1.0, 0.0],
                        [1.0, 0.0],
                        [1.0, bore_radius],
                        [-length - 1.0, bore_radius],
                    ],
                    "angle_degrees": 360.0,
                    "require_fully_defined": False,
                },
            }
        )
        blank_reference = "blank.body"

    operations.extend(
        [
            {
                "id": "tooth_space_sketch",
                "scenario": "numeric_profile_sketch",
                "params": {
                    "name": f"{requested_name} one tooth space",
                    "plane": "YOZ",
                    "entities": geometry.space_entities,
                    "parameterize": False,
                    "require_fully_defined": False,
                    "profile_status": "nominal_straight_sided_space_numeric_profile",
                },
            },
            {
                "id": "tooth_space_cut",
                "scenario": "cut_extrusion",
                "params": {
                    "name": f"{requested_name} one tooth space cut",
                    "sketch": "tooth_space_sketch.sketch",
                    "direction": "both",
                    "end_condition": "through_all",
                    "require_fully_defined": False,
                },
            },
            {
                "id": "tooth_space_pattern",
                "scenario": "circular_pattern",
                "params": {
                    "name": f"{requested_name} tooth space pattern",
                    "source": "tooth_space_cut.feature",
                    "axis": "blank.axis",
                    "count": tooth_count,
                    "span_angle": 360.0,
                    "parameterize": False,
                },
            },
        ]
    )
    exports = [
        {"name": "blank_body", "ref": blank_reference},
        {"name": "tooth_space_cut", "ref": "tooth_space_cut.feature"},
        {"name": "tooth_space_pattern", "ref": "tooth_space_pattern.feature"},
    ]
    if any(operation["id"] == "bore_cut" for operation in operations):
        exports.append({"name": "bore_cut", "ref": "bore_cut.feature"})
    if any(operation["id"] == "tip_chamfer_face_a" for operation in operations):
        exports.extend(
            [
                {"name": "tip_chamfer_a", "ref": "tip_chamfer_face_a.feature"},
                {"name": "tip_chamfer_b", "ref": "tip_chamfer_face_b.feature"},
            ]
        )

    if geometry.body == "shaft":
        xs = [point[0] for point in outline]
        ys = [point[1] for point in outline]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        bounds_candidates = [
            [-length, x_min, y_min, 0.0, x_max, y_max],
            [-length, y_min, x_min, 0.0, y_max, x_max],
        ]
        expected_bounds = bounds_candidates[0]
        max_radius = outer_radius
    else:
        hub_radius = float(geometry.hub_outside_radius_mm or 0.0)
        expected_bounds = [-length, -hub_radius, -hub_radius, 0.0, hub_radius, hub_radius]
        bounds_candidates = [expected_bounds]
        max_radius = hub_radius

    return {
        "ok": True,
        "stage": PLAN_STAGE,
        "plan_version": 1,
        "family": "straight_spline",
        "name": requested_name,
        "profile_request": model.model_dump(exclude_none=True),
        "profile_preview": preview,
        "workflow": {
            "scenario": "workflow",
            "params": {
                "name": requested_name,
                "operations": operations,
                "exports": exports,
            },
        },
        "geometry": {
            "body": geometry.body,
            "standard": STANDARD_CODE,
            "series": size.series,
            "designation": size.designation,
            "centering": geometry.centering,
            "execution": geometry.execution,
            "tooth_count": tooth_count,
            "inner_diameter_mm": size.inner_diameter_mm,
            "outer_diameter_mm": size.outer_diameter_mm,
            "tooth_width_mm": size.tooth_width_mm,
            "relief_diameter_mm": size.relief_diameter_mm,
            "relief_width_mm": size.relief_width_mm,
            "root_radius_mm": geometry.root_radius_mm,
            "outer_radius_mm": outer_radius,
            "hub_outside_radius_mm": geometry.hub_outside_radius_mm,
            "length_mm": length,
            "chamfer_mm": geometry.chamfer_mm if geometry.body == "shaft" else 0.0,
            "fillet_mm": geometry.fillet_mm,
            "space_area_mm2": geometry.space_area_mm2,
            "section_area_mm2": geometry.section_area_mm2,
            "expected_volume_mm3": geometry.expected_volume_mm3,
            "space_entity_count": len(geometry.space_entities),
            "bounds_candidates_mm": bounds_candidates,
        },
        "ownership": {
            "schema": OWNERSHIP_SCHEMA,
            "version": 1,
            "family_code": FAMILY_CODE,
            "source_profile": model.model_dump(exclude_none=True),
        },
        "verification": {
            "expected_volume_mm3": geometry.expected_volume_mm3,
            "volume_relative_tolerance": 0.005,
            "expected_bounds_mm": expected_bounds,
            "expected_bounds_candidates_mm": bounds_candidates,
            "bounds_tolerance_mm": 0.05,
            "max_radius_mm": max_radius,
            "length_mm": length,
            "pattern_count": tooth_count,
            "body": geometry.body,
        },
        "accuracy": {
            "profile": "nominal_straight_sided_flanks_with_root_fillets",
            "profile_encoding": "exact_segments_and_arcs_numeric_profile",
            "representation_mode": "nominal",
            "create_only": True,
            "conformity_claim": False,
            "runout": "not_in_this_slice",
            "execution_1_groove": "table_values_reported_not_built",
        },
    }
