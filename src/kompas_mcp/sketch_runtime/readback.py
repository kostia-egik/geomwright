from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .diagnostics import Diagnostic
from .entities import Arc, Point, Segment, SketchModel, SketchPrimitive
from .topology import TopologyReport, verify_topology


@dataclass(frozen=True)
class SketchReadbackExpectation:
    model: SketchModel
    point_tolerance: float = 1e-6
    required_point_ids: tuple[str, ...] = ()
    required_primitive_ids: tuple[str, ...] = ()
    verify_actual_topology: bool = True


@dataclass(frozen=True)
class SketchReadbackReport:
    stage: str
    ok: bool
    expected_point_count: int
    actual_point_count: int
    expected_primitive_count: int
    actual_primitive_count: int
    topology: TopologyReport | None = None
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stage": self.stage,
            "ok": self.ok,
            "expected_point_count": self.expected_point_count,
            "actual_point_count": self.actual_point_count,
            "expected_primitive_count": self.expected_primitive_count,
            "actual_primitive_count": self.actual_primitive_count,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }
        if self.topology is not None:
            payload["topology"] = self.topology.to_dict()
        return payload


def verify_sketch_readback(
    expectation: SketchReadbackExpectation,
    actual: SketchModel,
    *,
    stage: str = "readback",
) -> SketchReadbackReport:
    expected = expectation.model
    diagnostics: list[Diagnostic] = []

    diagnostics.extend(_duplicate_id_diagnostics(expected, "expected"))
    diagnostics.extend(_duplicate_id_diagnostics(actual, "actual"))

    expected_points = expected.point_map()
    actual_points = actual.point_map()
    expected_primitives = expected.primitive_map()
    actual_primitives = actual.primitive_map()

    required_point_ids = expectation.required_point_ids or tuple(expected_points)
    required_primitive_ids = expectation.required_primitive_ids or tuple(expected_primitives)

    for point_id in required_point_ids:
        expected_point = expected_points.get(point_id)
        actual_point = actual_points.get(point_id)
        if expected_point is None:
            diagnostics.append(
                Diagnostic(
                    "readback_unknown_expected_point",
                    "Readback expectation references a point that is not in the expected model",
                    entity_ids=(point_id,),
                )
            )
            continue
        if actual_point is None:
            diagnostics.append(
                Diagnostic(
                    "missing_readback_point",
                    "Actual sketch is missing an expected point",
                    entity_ids=(point_id,),
                    details={"role": expected_point.role},
                )
            )
            continue
        diagnostics.extend(_verify_point_readback(expected_point, actual_point, expectation.point_tolerance))

    for primitive_id in required_primitive_ids:
        expected_primitive = expected_primitives.get(primitive_id)
        actual_primitive = actual_primitives.get(primitive_id)
        if expected_primitive is None:
            diagnostics.append(
                Diagnostic(
                    "readback_unknown_expected_primitive",
                    "Readback expectation references a primitive that is not in the expected model",
                    entity_ids=(primitive_id,),
                )
            )
            continue
        if actual_primitive is None:
            diagnostics.append(
                Diagnostic(
                    "missing_readback_primitive",
                    "Actual sketch is missing an expected primitive",
                    entity_ids=(primitive_id,),
                    details={"role": expected_primitive.role},
                )
            )
            continue
        diagnostics.extend(_verify_primitive_readback(expected_primitive, actual_primitive))

    topology = verify_topology(actual, stage=f"{stage}_topology") if expectation.verify_actual_topology else None
    if topology is not None:
        diagnostics.extend(topology.diagnostics)

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return SketchReadbackReport(
        stage=stage,
        ok=ok,
        expected_point_count=len(expected.points),
        actual_point_count=len(actual.points),
        expected_primitive_count=len(expected.primitives),
        actual_primitive_count=len(actual.primitives),
        topology=topology,
        diagnostics=tuple(diagnostics),
    )


def _duplicate_id_diagnostics(model: SketchModel, side: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    point_ids = [point.id for point in model.points]
    primitive_ids = [primitive.id for primitive in model.primitives]
    duplicate_points = sorted({point_id for point_id in point_ids if point_ids.count(point_id) > 1})
    duplicate_primitives = sorted(
        {primitive_id for primitive_id in primitive_ids if primitive_ids.count(primitive_id) > 1}
    )
    if duplicate_points:
        diagnostics.append(
            Diagnostic(
                "duplicate_readback_point_id",
                "Sketch readback contains duplicate point ids",
                details={"side": side, "point_ids": duplicate_points},
            )
        )
    if duplicate_primitives:
        diagnostics.append(
            Diagnostic(
                "duplicate_readback_primitive_id",
                "Sketch readback contains duplicate primitive ids",
                details={"side": side, "primitive_ids": duplicate_primitives},
            )
        )
    return diagnostics


def _verify_point_readback(expected: Point, actual: Point, tolerance: float) -> list[Diagnostic]:
    dx = float(actual.x) - float(expected.x)
    dy = float(actual.y) - float(expected.y)
    if abs(dx) <= tolerance and abs(dy) <= tolerance:
        return []
    return [
        Diagnostic(
            "readback_point_coordinate_mismatch",
            "Actual point coordinates differ from the expected coordinates",
            entity_ids=(expected.id,),
            details={
                "expected": [float(expected.x), float(expected.y)],
                "actual": [float(actual.x), float(actual.y)],
                "delta": [dx, dy],
                "tolerance": tolerance,
                "role": expected.role,
            },
        )
    ]


def _verify_primitive_readback(expected: SketchPrimitive, actual: SketchPrimitive) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if expected.kind != actual.kind:
        diagnostics.append(
            Diagnostic(
                "readback_primitive_kind_mismatch",
                "Actual primitive kind differs from the expected primitive kind",
                entity_ids=(expected.id,),
                details={"expected": expected.kind, "actual": actual.kind, "role": expected.role},
            )
        )
        return diagnostics

    if expected.endpoint_ids() != actual.endpoint_ids():
        diagnostics.append(
            Diagnostic(
                "readback_primitive_endpoint_mismatch",
                "Actual primitive endpoints differ from the expected endpoints",
                entity_ids=(expected.id,),
                details={
                    "expected": list(expected.endpoint_ids()),
                    "actual": list(actual.endpoint_ids()),
                    "role": expected.role,
                },
            )
        )
    if expected.loop_id != actual.loop_id:
        diagnostics.append(
            Diagnostic(
                "readback_loop_mismatch",
                "Actual primitive loop differs from the expected loop",
                entity_ids=(expected.id,),
                details={"expected": expected.loop_id, "actual": actual.loop_id, "role": expected.role},
            )
        )
    if expected.construction != actual.construction:
        diagnostics.append(
            Diagnostic(
                "readback_construction_mismatch",
                "Actual primitive construction flag differs from the expected flag",
                entity_ids=(expected.id,),
                details={"expected": expected.construction, "actual": actual.construction, "role": expected.role},
            )
        )

    if isinstance(expected, Arc) and isinstance(actual, Arc):
        if expected.center != actual.center:
            diagnostics.append(
                Diagnostic(
                    "readback_arc_center_mismatch",
                    "Actual arc center differs from the expected center",
                    entity_ids=(expected.id,),
                    details={"expected": expected.center, "actual": actual.center, "role": expected.role},
                )
            )
        if expected.direction != actual.direction:
            diagnostics.append(
                Diagnostic(
                    "readback_arc_direction_mismatch",
                    "Actual arc direction differs from the expected direction",
                    entity_ids=(expected.id,),
                    details={"expected": expected.direction, "actual": actual.direction, "role": expected.role},
                )
            )
    elif isinstance(expected, Segment) and isinstance(actual, Segment):
        pass

    return diagnostics
