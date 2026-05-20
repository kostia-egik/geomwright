from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Any, Literal

from .diagnostics import Diagnostic
from .entities import Arc, Circle, Point, Segment, SketchModel


MeasurementKind = Literal[
    "point_distance",
    "horizontal_distance",
    "vertical_distance",
    "segment_length",
    "arc_radius",
    "circle_radius",
]


@dataclass(frozen=True)
class MeasurementExpectation:
    id: str
    kind: MeasurementKind
    target_ids: tuple[str, ...]
    expected: float
    tolerance: float = 1e-6
    role: str = ""


@dataclass(frozen=True)
class MeasurementResult:
    id: str
    kind: MeasurementKind
    ok: bool
    expected: float
    actual: float | None
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "ok": self.ok,
            "expected": self.expected,
            "actual": self.actual,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


@dataclass(frozen=True)
class MeasurementReport:
    stage: str
    ok: bool
    results: tuple[MeasurementResult, ...]
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "results": [result.to_dict() for result in self.results],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def verify_measurements(
    model: SketchModel,
    expectations: tuple[MeasurementExpectation, ...],
    *,
    stage: str = "measurements",
) -> MeasurementReport:
    diagnostics: list[Diagnostic] = []
    results: list[MeasurementResult] = []

    expectation_ids = [expectation.id for expectation in expectations]
    if len(set(expectation_ids)) != len(expectation_ids):
        diagnostics.append(Diagnostic("duplicate_measurement_id", "Measurement plan contains duplicate ids"))

    points = model.point_map()
    primitives = model.primitive_map()
    for expectation in expectations:
        actual, result_diagnostics = _measure(expectation, points, primitives)
        if actual is not None and abs(actual - float(expectation.expected)) > expectation.tolerance:
            result_diagnostics.append(
                Diagnostic(
                    "measurement_mismatch",
                    "Measured sketch value differs from the expected value",
                    entity_ids=(expectation.id, *expectation.target_ids),
                    details={
                        "kind": expectation.kind,
                        "expected": float(expectation.expected),
                        "actual": actual,
                        "tolerance": expectation.tolerance,
                        "role": expectation.role,
                    },
                )
            )
        result = MeasurementResult(
            id=expectation.id,
            kind=expectation.kind,
            ok=not any(diagnostic.severity == "error" for diagnostic in result_diagnostics),
            expected=float(expectation.expected),
            actual=actual,
            diagnostics=tuple(result_diagnostics),
        )
        results.append(result)
        diagnostics.extend(result_diagnostics)

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return MeasurementReport(stage=stage, ok=ok, results=tuple(results), diagnostics=tuple(diagnostics))


def _measure(
    expectation: MeasurementExpectation,
    points: dict[str, Point],
    primitives: dict[str, object],
) -> tuple[float | None, list[Diagnostic]]:
    if expectation.kind in ("point_distance", "horizontal_distance", "vertical_distance"):
        return _measure_point_pair(expectation, points)
    if expectation.kind == "segment_length":
        return _measure_segment_length(expectation, points, primitives)
    if expectation.kind == "arc_radius":
        return _measure_arc_radius(expectation, points, primitives)
    if expectation.kind == "circle_radius":
        return _measure_circle_radius(expectation, primitives)
    return None, [
        Diagnostic(
            "unsupported_measurement_kind",
            "Measurement kind is not supported",
            entity_ids=(expectation.id,),
            details={"kind": expectation.kind, "role": expectation.role},
        )
    ]


def _measure_point_pair(
    expectation: MeasurementExpectation,
    points: dict[str, Point],
) -> tuple[float | None, list[Diagnostic]]:
    if len(expectation.target_ids) != 2:
        return None, [_wrong_target_count(expectation, expected_count=2)]
    first = points.get(expectation.target_ids[0])
    second = points.get(expectation.target_ids[1])
    missing = [point_id for point_id, point in zip(expectation.target_ids, (first, second)) if point is None]
    if missing:
        return None, [_missing_targets(expectation, missing)]

    assert first is not None
    assert second is not None
    dx = float(second.x) - float(first.x)
    dy = float(second.y) - float(first.y)
    if expectation.kind == "horizontal_distance":
        return abs(dx), []
    if expectation.kind == "vertical_distance":
        return abs(dy), []
    return hypot(dx, dy), []


def _measure_segment_length(
    expectation: MeasurementExpectation,
    points: dict[str, Point],
    primitives: dict[str, object],
) -> tuple[float | None, list[Diagnostic]]:
    primitive, diagnostics = _single_primitive(expectation, primitives, Segment)
    if primitive is None:
        return None, diagnostics
    start = points.get(primitive.start)
    end = points.get(primitive.end)
    missing = [point_id for point_id, point in ((primitive.start, start), (primitive.end, end)) if point is None]
    if missing:
        return None, [_missing_targets(expectation, missing)]

    assert start is not None
    assert end is not None
    return hypot(float(end.x) - float(start.x), float(end.y) - float(start.y)), []


def _measure_arc_radius(
    expectation: MeasurementExpectation,
    points: dict[str, Point],
    primitives: dict[str, object],
) -> tuple[float | None, list[Diagnostic]]:
    primitive, diagnostics = _single_primitive(expectation, primitives, Arc)
    if primitive is None:
        return None, diagnostics
    start = points.get(primitive.start)
    end = points.get(primitive.end)
    center = points.get(primitive.center)
    missing = [
        point_id
        for point_id, point in ((primitive.start, start), (primitive.end, end), (primitive.center, center))
        if point is None
    ]
    if missing:
        return None, [_missing_targets(expectation, missing)]

    assert start is not None
    assert end is not None
    assert center is not None
    start_radius = hypot(float(start.x) - float(center.x), float(start.y) - float(center.y))
    end_radius = hypot(float(end.x) - float(center.x), float(end.y) - float(center.y))
    if abs(start_radius - end_radius) > expectation.tolerance:
        return None, [
            Diagnostic(
                "arc_radius_inconsistent",
                "Arc endpoints are not on the same radius from the center",
                entity_ids=(expectation.id, primitive.id),
                details={
                    "start_radius": start_radius,
                    "end_radius": end_radius,
                    "tolerance": expectation.tolerance,
                    "role": expectation.role,
                },
            )
        ]
    return (start_radius + end_radius) / 2.0, []


def _measure_circle_radius(
    expectation: MeasurementExpectation,
    primitives: dict[str, object],
) -> tuple[float | None, list[Diagnostic]]:
    primitive, diagnostics = _single_primitive(expectation, primitives, Circle)
    if primitive is None:
        return None, diagnostics
    return float(primitive.radius), []


def _single_primitive(
    expectation: MeasurementExpectation,
    primitives: dict[str, object],
    primitive_type: type[Segment] | type[Arc] | type[Circle],
) -> tuple[Segment | Arc | Circle | None, list[Diagnostic]]:
    if len(expectation.target_ids) != 1:
        return None, [_wrong_target_count(expectation, expected_count=1)]
    primitive = primitives.get(expectation.target_ids[0])
    if primitive is None:
        return None, [_missing_targets(expectation, [expectation.target_ids[0]])]
    if not isinstance(primitive, primitive_type):
        return None, [
            Diagnostic(
                "measurement_target_kind_mismatch",
                "Measurement target primitive has an unexpected kind",
                entity_ids=(expectation.id, expectation.target_ids[0]),
                details={"kind": expectation.kind, "role": expectation.role},
            )
        ]
    return primitive, []


def _wrong_target_count(expectation: MeasurementExpectation, *, expected_count: int) -> Diagnostic:
    return Diagnostic(
        "measurement_target_count_mismatch",
        "Measurement has an unexpected number of targets",
        entity_ids=(expectation.id,),
        details={
            "kind": expectation.kind,
            "expected_count": expected_count,
            "actual_count": len(expectation.target_ids),
            "role": expectation.role,
        },
    )


def _missing_targets(expectation: MeasurementExpectation, target_ids: list[str]) -> Diagnostic:
    return Diagnostic(
        "missing_measurement_target",
        "Measurement references targets that do not exist",
        entity_ids=(expectation.id,),
        details={"target_ids": target_ids, "kind": expectation.kind, "role": expectation.role},
    )
