from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .diagnostics import Diagnostic
from .entities import Point, Segment, SketchModel


LoopOrientation = Literal["cw", "ccw"]


@dataclass(frozen=True)
class LoopOrientationExpectation:
    loop_id: str = "main"
    orientation: LoopOrientation = "ccw"
    min_abs_area: float = 1e-9


@dataclass(frozen=True)
class LoopOrientationResult:
    loop_id: str
    ok: bool
    expected: LoopOrientation
    actual: LoopOrientation | None
    signed_area: float | None
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "ok": self.ok,
            "expected": self.expected,
            "actual": self.actual,
            "signed_area": self.signed_area,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


@dataclass(frozen=True)
class LoopOrientationReport:
    stage: str
    ok: bool
    results: tuple[LoopOrientationResult, ...]
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "results": [result.to_dict() for result in self.results],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def verify_loop_orientations(
    model: SketchModel,
    expectations: tuple[LoopOrientationExpectation, ...],
    *,
    stage: str = "loop_orientation",
) -> LoopOrientationReport:
    results: list[LoopOrientationResult] = []
    diagnostics: list[Diagnostic] = []

    for expectation in expectations:
        result = _verify_loop_orientation(model, expectation)
        results.append(result)
        diagnostics.extend(result.diagnostics)

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return LoopOrientationReport(stage=stage, ok=ok, results=tuple(results), diagnostics=tuple(diagnostics))


def _verify_loop_orientation(
    model: SketchModel,
    expectation: LoopOrientationExpectation,
) -> LoopOrientationResult:
    diagnostics: list[Diagnostic] = []
    loop_primitives = [primitive for primitive in model.primitives if primitive.loop_id == expectation.loop_id]
    segment_primitives = [primitive for primitive in loop_primitives if isinstance(primitive, Segment)]

    if not loop_primitives:
        diagnostics.append(
            Diagnostic(
                "orientation_missing_loop",
                "Expected loop has no primitives for orientation verification",
                details={"loop_id": expectation.loop_id},
            )
        )
        return _orientation_result(expectation, None, None, diagnostics)

    if len(segment_primitives) != len(loop_primitives):
        diagnostics.append(
            Diagnostic(
                "orientation_unsupported_primitive",
                "Loop orientation verification currently supports segment-only loops",
                details={"loop_id": expectation.loop_id},
            )
        )
        return _orientation_result(expectation, None, None, diagnostics)

    points = model.point_map()
    ordered_points, order_diagnostics = _ordered_segment_loop_points(segment_primitives, points, expectation.loop_id)
    diagnostics.extend(order_diagnostics)
    if diagnostics:
        return _orientation_result(expectation, None, None, diagnostics)

    signed_area = _signed_area(ordered_points)
    if abs(signed_area) < expectation.min_abs_area:
        diagnostics.append(
            Diagnostic(
                "orientation_degenerate_loop",
                "Loop area is too small to determine a stable orientation",
                details={
                    "loop_id": expectation.loop_id,
                    "signed_area": signed_area,
                    "min_abs_area": expectation.min_abs_area,
                },
            )
        )
        return _orientation_result(expectation, None, signed_area, diagnostics)

    actual: LoopOrientation = "ccw" if signed_area > 0.0 else "cw"
    if actual != expectation.orientation:
        diagnostics.append(
            Diagnostic(
                "loop_orientation_mismatch",
                "Loop orientation differs from the expected orientation",
                details={
                    "loop_id": expectation.loop_id,
                    "expected": expectation.orientation,
                    "actual": actual,
                    "signed_area": signed_area,
                },
            )
        )

    return _orientation_result(expectation, actual, signed_area, diagnostics)


def _orientation_result(
    expectation: LoopOrientationExpectation,
    actual: LoopOrientation | None,
    signed_area: float | None,
    diagnostics: list[Diagnostic],
) -> LoopOrientationResult:
    return LoopOrientationResult(
        loop_id=expectation.loop_id,
        ok=not any(diagnostic.severity == "error" for diagnostic in diagnostics),
        expected=expectation.orientation,
        actual=actual,
        signed_area=signed_area,
        diagnostics=tuple(diagnostics),
    )


def _ordered_segment_loop_points(
    segments: list[Segment],
    points: dict[str, Point],
    loop_id: str,
) -> tuple[list[Point], list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    edges: dict[str, list[str]] = {}
    for segment in segments:
        if segment.start not in points or segment.end not in points:
            diagnostics.append(
                Diagnostic(
                    "orientation_missing_endpoint",
                    "Segment loop orientation cannot be verified because an endpoint is missing",
                    entity_ids=(segment.id,),
                    details={"loop_id": loop_id},
                )
            )
            continue
        edges.setdefault(segment.start, []).append(segment.end)
        edges.setdefault(segment.end, []).append(segment.start)

    bad_degree = sorted(point_id for point_id, neighbours in edges.items() if len(neighbours) != 2)
    if bad_degree:
        diagnostics.append(
            Diagnostic(
                "orientation_open_loop",
                "Segment loop orientation requires every point to have degree 2",
                details={"loop_id": loop_id, "point_ids": bad_degree},
            )
        )
        return [], diagnostics

    if diagnostics:
        return [], diagnostics

    start = sorted(edges)[0]
    previous: str | None = None
    current = start
    ordered_ids: list[str] = []
    for _ in range(len(edges) + 1):
        ordered_ids.append(current)
        neighbours = sorted(edges[current])
        next_point = neighbours[0] if neighbours[0] != previous else neighbours[1]
        previous, current = current, next_point
        if current == start:
            break

    if current != start or len(set(ordered_ids)) != len(edges):
        diagnostics.append(
            Diagnostic(
                "orientation_disconnected_loop",
                "Segment loop orientation requires one connected closed component",
                details={"loop_id": loop_id},
            )
        )
        return [], diagnostics

    return [points[point_id] for point_id in ordered_ids], diagnostics


def _signed_area(points: list[Point]) -> float:
    area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += float(point.x) * float(next_point.y) - float(next_point.x) * float(point.y)
    return area / 2.0
