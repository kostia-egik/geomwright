from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .diagnostics import Diagnostic
from .entities import SketchModel


PointRelationKind = Literal["left_of", "right_of", "below", "above", "same_x", "same_y"]


@dataclass(frozen=True)
class PointRelationExpectation:
    id: str
    kind: PointRelationKind
    first_point_id: str
    second_point_id: str
    tolerance: float = 1e-9
    min_delta: float = 0.0
    role: str = ""


@dataclass(frozen=True)
class PointRelationReport:
    stage: str
    ok: bool
    relation_count: int
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "relation_count": self.relation_count,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def verify_point_relations(
    model: SketchModel,
    expectations: tuple[PointRelationExpectation, ...],
    *,
    stage: str = "point_relations",
) -> PointRelationReport:
    diagnostics: list[Diagnostic] = []
    points = model.point_map()

    expectation_ids = [expectation.id for expectation in expectations]
    if len(set(expectation_ids)) != len(expectation_ids):
        diagnostics.append(Diagnostic("duplicate_point_relation_id", "Point relation plan contains duplicate ids"))

    for expectation in expectations:
        first = points.get(expectation.first_point_id)
        second = points.get(expectation.second_point_id)
        missing = [
            point_id
            for point_id, point in (
                (expectation.first_point_id, first),
                (expectation.second_point_id, second),
            )
            if point is None
        ]
        if missing:
            diagnostics.append(
                Diagnostic(
                    "missing_point_relation_target",
                    "Point relation references a point that does not exist",
                    entity_ids=(expectation.id,),
                    details={"point_ids": missing, "role": expectation.role},
                )
            )
            continue

        assert first is not None
        assert second is not None
        if not _relation_holds(expectation.kind, first.x, first.y, second.x, second.y, expectation):
            diagnostics.append(
                Diagnostic(
                    "point_relation_mismatch",
                    "Point relation does not match expected relative position",
                    entity_ids=(expectation.id, expectation.first_point_id, expectation.second_point_id),
                    details={
                        "kind": expectation.kind,
                        "first": [float(first.x), float(first.y)],
                        "second": [float(second.x), float(second.y)],
                        "tolerance": expectation.tolerance,
                        "min_delta": expectation.min_delta,
                        "role": expectation.role,
                    },
                )
            )

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return PointRelationReport(
        stage=stage,
        ok=ok,
        relation_count=len(expectations),
        diagnostics=tuple(diagnostics),
    )


def _relation_holds(
    kind: PointRelationKind,
    first_x: float,
    first_y: float,
    second_x: float,
    second_y: float,
    expectation: PointRelationExpectation,
) -> bool:
    tolerance = expectation.tolerance
    min_delta = expectation.min_delta
    if kind == "left_of":
        return float(first_x) <= float(second_x) - min_delta + tolerance
    if kind == "right_of":
        return float(first_x) >= float(second_x) + min_delta - tolerance
    if kind == "below":
        return float(first_y) <= float(second_y) - min_delta + tolerance
    if kind == "above":
        return float(first_y) >= float(second_y) + min_delta - tolerance
    if kind == "same_x":
        return abs(float(first_x) - float(second_x)) <= tolerance
    if kind == "same_y":
        return abs(float(first_y) - float(second_y)) <= tolerance
    return False
