from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Any

from .diagnostics import Diagnostic
from .entities import Arc, Circle, Point, Segment, SketchModel, SketchPrimitive


@dataclass(frozen=True)
class TangencyExpectation:
    id: str
    first_primitive_id: str
    second_primitive_id: str
    at_point_id: str | None = None
    tolerance: float = 1e-6
    role: str = ""


@dataclass(frozen=True)
class TangencyReport:
    stage: str
    ok: bool
    tangency_count: int
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "tangency_count": self.tangency_count,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def verify_tangencies(
    model: SketchModel,
    expectations: tuple[TangencyExpectation, ...],
    *,
    stage: str = "tangencies",
) -> TangencyReport:
    diagnostics: list[Diagnostic] = []
    primitives = model.primitive_map()
    points = model.point_map()

    expectation_ids = [expectation.id for expectation in expectations]
    if len(set(expectation_ids)) != len(expectation_ids):
        diagnostics.append(Diagnostic("duplicate_tangency_id", "Tangency plan contains duplicate ids"))

    for expectation in expectations:
        first = primitives.get(expectation.first_primitive_id)
        second = primitives.get(expectation.second_primitive_id)
        missing = [
            primitive_id
            for primitive_id, primitive in (
                (expectation.first_primitive_id, first),
                (expectation.second_primitive_id, second),
            )
            if primitive is None
        ]
        if missing:
            diagnostics.append(
                Diagnostic(
                    "missing_tangency_primitive",
                    "Tangency references a primitive that does not exist",
                    entity_ids=(expectation.id,),
                    details={"primitive_ids": missing, "role": expectation.role},
                )
            )
            continue

        assert first is not None
        assert second is not None
        point_id, point_diagnostics = _resolve_contact_point(expectation, first, second, points)
        diagnostics.extend(point_diagnostics)
        if point_id is None:
            continue

        first_tangent, first_diagnostics = _tangent_vector(first, point_id, points, expectation)
        second_tangent, second_diagnostics = _tangent_vector(second, point_id, points, expectation)
        diagnostics.extend(first_diagnostics)
        diagnostics.extend(second_diagnostics)
        if first_tangent is None or second_tangent is None:
            continue

        cross_abs = abs(_cross(_normalize(first_tangent), _normalize(second_tangent)))
        if cross_abs > expectation.tolerance:
            diagnostics.append(
                Diagnostic(
                    "tangency_mismatch",
                    "Primitive tangents are not parallel at the expected contact point",
                    entity_ids=(expectation.id, first.id, second.id, point_id),
                    details={
                        "cross_abs": cross_abs,
                        "tolerance": expectation.tolerance,
                        "role": expectation.role,
                    },
                )
            )

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return TangencyReport(
        stage=stage,
        ok=ok,
        tangency_count=len(expectations),
        diagnostics=tuple(diagnostics),
    )


def _resolve_contact_point(
    expectation: TangencyExpectation,
    first: SketchPrimitive,
    second: SketchPrimitive,
    points: dict[str, Point],
) -> tuple[str | None, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    if expectation.at_point_id is not None:
        if expectation.at_point_id not in points:
            diagnostics.append(
                Diagnostic(
                    "missing_tangency_point",
                    "Tangency contact point does not exist",
                    entity_ids=(expectation.id, expectation.at_point_id),
                    details={"role": expectation.role},
                )
            )
            return None, diagnostics
        return expectation.at_point_id, diagnostics

    shared_points = sorted(set(first.endpoint_ids()) & set(second.endpoint_ids()))
    if len(shared_points) != 1:
        diagnostics.append(
            Diagnostic(
                "ambiguous_tangency_point",
                "Tangency requires exactly one shared endpoint or an explicit contact point",
                entity_ids=(expectation.id, first.id, second.id),
                details={"shared_point_ids": shared_points, "role": expectation.role},
            )
        )
        return None, diagnostics

    return shared_points[0], diagnostics


def _tangent_vector(
    primitive: SketchPrimitive,
    point_id: str,
    points: dict[str, Point],
    expectation: TangencyExpectation,
) -> tuple[tuple[float, float] | None, list[Diagnostic]]:
    if isinstance(primitive, Segment):
        return _segment_tangent(primitive, point_id, points, expectation)
    if isinstance(primitive, Arc):
        return _arc_tangent(primitive, point_id, points, expectation)
    if isinstance(primitive, Circle):
        return _circle_tangent(primitive, point_id, points, expectation)
    return None, [
        Diagnostic(
            "unsupported_tangency_primitive",
            "Tangency verification does not support this primitive type",
            entity_ids=(expectation.id, primitive.id),
            details={"role": expectation.role},
        )
    ]


def _segment_tangent(
    segment: Segment,
    point_id: str,
    points: dict[str, Point],
    expectation: TangencyExpectation,
) -> tuple[tuple[float, float] | None, list[Diagnostic]]:
    if point_id == segment.start:
        start = points.get(segment.start)
        end = points.get(segment.end)
    elif point_id == segment.end:
        start = points.get(segment.end)
        end = points.get(segment.start)
    else:
        return None, [_not_incident_diagnostic(expectation, segment, point_id)]

    if start is None or end is None:
        return None, [_missing_endpoint_diagnostic(expectation, segment, point_id)]

    return _nonzero_vector((end.x - start.x, end.y - start.y), expectation, segment.id, point_id)


def _arc_tangent(
    arc: Arc,
    point_id: str,
    points: dict[str, Point],
    expectation: TangencyExpectation,
) -> tuple[tuple[float, float] | None, list[Diagnostic]]:
    if point_id not in (arc.start, arc.end):
        return None, [_not_incident_diagnostic(expectation, arc, point_id)]

    point = points.get(point_id)
    center = points.get(arc.center)
    if point is None or center is None:
        return None, [_missing_endpoint_diagnostic(expectation, arc, point_id)]

    radius = (point.x - center.x, point.y - center.y)
    tangent = (-radius[1], radius[0]) if arc.direction == "ccw" else (radius[1], -radius[0])
    return _nonzero_vector(tangent, expectation, arc.id, point_id)


def _circle_tangent(
    circle: Circle,
    point_id: str,
    points: dict[str, Point],
    expectation: TangencyExpectation,
) -> tuple[tuple[float, float] | None, list[Diagnostic]]:
    point = points.get(point_id)
    center = points.get(circle.center)
    if point is None or center is None:
        return None, [_missing_endpoint_diagnostic(expectation, circle, point_id)]

    radius = (point.x - center.x, point.y - center.y)
    radius_length = hypot(radius[0], radius[1])
    if abs(radius_length - float(circle.radius)) > expectation.tolerance:
        return None, [
            Diagnostic(
                "tangency_point_off_circle",
                "Tangency contact point is not on the circle",
                entity_ids=(expectation.id, circle.id, point_id),
                details={
                    "radius": float(circle.radius),
                    "actual_distance": radius_length,
                    "tolerance": expectation.tolerance,
                    "role": expectation.role,
                },
            )
        ]

    return _nonzero_vector((-radius[1], radius[0]), expectation, circle.id, point_id)


def _nonzero_vector(
    vector: tuple[float, float],
    expectation: TangencyExpectation,
    primitive_id: str,
    point_id: str,
) -> tuple[tuple[float, float] | None, list[Diagnostic]]:
    if hypot(vector[0], vector[1]) <= expectation.tolerance:
        return None, [
            Diagnostic(
                "degenerate_tangency_vector",
                "Tangency vector is too small to compare reliably",
                entity_ids=(expectation.id, primitive_id, point_id),
                details={"tolerance": expectation.tolerance, "role": expectation.role},
            )
        ]
    return vector, []


def _normalize(vector: tuple[float, float]) -> tuple[float, float]:
    length = hypot(vector[0], vector[1])
    return (vector[0] / length, vector[1] / length)


def _cross(first: tuple[float, float], second: tuple[float, float]) -> float:
    return first[0] * second[1] - first[1] * second[0]


def _not_incident_diagnostic(
    expectation: TangencyExpectation,
    primitive: SketchPrimitive,
    point_id: str,
) -> Diagnostic:
    return Diagnostic(
        "tangency_point_not_incident",
        "Tangency contact point is not incident to the primitive",
        entity_ids=(expectation.id, primitive.id, point_id),
        details={"role": expectation.role},
    )


def _missing_endpoint_diagnostic(
    expectation: TangencyExpectation,
    primitive: SketchPrimitive,
    point_id: str,
) -> Diagnostic:
    return Diagnostic(
        "missing_tangency_endpoint",
        "Tangency cannot be checked because a required point is missing",
        entity_ids=(expectation.id, primitive.id, point_id),
        details={"role": expectation.role},
    )
