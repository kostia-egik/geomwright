from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from .diagnostics import Diagnostic
from .entities import Point, PointId, Segment, SketchModel, SketchPrimitive


@dataclass(frozen=True)
class LoopReport:
    loop_id: str
    primitive_ids: tuple[str, ...]
    point_ids: tuple[PointId, ...]
    closed: bool
    connected: bool
    dangling_point_ids: tuple[PointId, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "primitive_ids": list(self.primitive_ids),
            "point_ids": list(self.point_ids),
            "closed": self.closed,
            "connected": self.connected,
            "dangling_point_ids": list(self.dangling_point_ids),
        }


@dataclass(frozen=True)
class TopologyReport:
    stage: str
    ok: bool
    point_count: int
    primitive_count: int
    loops: tuple[LoopReport, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "point_count": self.point_count,
            "primitive_count": self.primitive_count,
            "loops": [loop.to_dict() for loop in self.loops],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def verify_topology(model: SketchModel, *, stage: str = "topology") -> TopologyReport:
    diagnostics: list[Diagnostic] = []
    loops: list[LoopReport] = []

    point_by_id = model.point_map()
    primitive_by_id = model.primitive_map()
    if len(point_by_id) != len(model.points):
        diagnostics.append(Diagnostic("duplicate_point_id", "Sketch contains duplicate point ids"))
    if len(primitive_by_id) != len(model.primitives):
        diagnostics.append(Diagnostic("duplicate_primitive_id", "Sketch contains duplicate primitive ids"))

    expected_loops = set(model.expected_loops)
    primitives_by_loop: dict[str, list[SketchPrimitive]] = defaultdict(list)
    for primitive in model.primitives:
        primitives_by_loop[primitive.loop_id].append(primitive)
        missing = [point_id for point_id in primitive.endpoint_ids() if point_id not in point_by_id]
        if missing:
            diagnostics.append(
                Diagnostic(
                    "missing_endpoint",
                    "Primitive references a point that does not exist",
                    entity_ids=(primitive.id,),
                    details={"missing_point_ids": missing},
                )
            )
        if primitive.kind == "arc" and primitive.center not in point_by_id:
            diagnostics.append(
                Diagnostic(
                    "missing_arc_center",
                    "Arc references a center point that does not exist",
                    entity_ids=(primitive.id,),
                    details={"center_point_id": primitive.center},
                )
            )

    actual_loops = set(primitives_by_loop)
    for loop_id in sorted(expected_loops - actual_loops):
        diagnostics.append(
            Diagnostic(
                "missing_expected_loop",
                "Expected loop has no primitives",
                details={"loop_id": loop_id},
            )
        )

    for loop_id in sorted(actual_loops):
        loop_primitives = primitives_by_loop[loop_id]
        loop_report, loop_diagnostics = _verify_loop(loop_id, loop_primitives, point_by_id)
        loops.append(loop_report)
        diagnostics.extend(loop_diagnostics)

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return TopologyReport(
        stage=stage,
        ok=ok,
        point_count=len(model.points),
        primitive_count=len(model.primitives),
        loops=tuple(loops),
        diagnostics=tuple(diagnostics),
    )


def _verify_loop(
    loop_id: str,
    primitives: list[SketchPrimitive],
    point_by_id: dict[PointId, Point],
) -> tuple[LoopReport, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    primitive_ids = tuple(primitive.id for primitive in primitives)
    adjacency: dict[PointId, set[PointId]] = defaultdict(set)
    degree: dict[PointId, int] = defaultdict(int)

    for primitive in primitives:
        start, end = primitive.endpoint_ids()
        if start not in point_by_id or end not in point_by_id:
            continue
        if start == end:
            diagnostics.append(
                Diagnostic(
                    "zero_length_primitive",
                    "Primitive starts and ends at the same point",
                    entity_ids=(primitive.id,),
                )
            )
            degree[start] += 2
            continue
        adjacency[start].add(end)
        adjacency[end].add(start)
        degree[start] += 1
        degree[end] += 1

    point_ids = tuple(sorted(degree))
    dangling = tuple(sorted(point_id for point_id, value in degree.items() if value != 2))
    connected = _is_connected(point_ids, adjacency)
    closed = not dangling and connected and bool(primitives)

    if dangling:
        diagnostics.append(
            Diagnostic(
                "dangling_loop_points",
                "Loop points must have degree 2",
                details={"loop_id": loop_id, "point_ids": list(dangling)},
            )
        )
    if primitives and not connected:
        diagnostics.append(
            Diagnostic(
                "disconnected_loop",
                "Loop primitives do not form one connected component",
                details={"loop_id": loop_id},
            )
        )
    diagnostics.extend(_verify_unexpected_segment_intersections(loop_id, primitives, point_by_id))

    return (
        LoopReport(
            loop_id=loop_id,
            primitive_ids=primitive_ids,
            point_ids=point_ids,
            closed=closed,
            connected=connected,
            dangling_point_ids=dangling,
        ),
        diagnostics,
    )


def _verify_unexpected_segment_intersections(
    loop_id: str,
    primitives: list[SketchPrimitive],
    point_by_id: dict[PointId, Point],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    segments = [primitive for primitive in primitives if isinstance(primitive, Segment)]
    for index, first in enumerate(segments):
        first_points = set(first.endpoint_ids())
        first_start = point_by_id.get(first.start)
        first_end = point_by_id.get(first.end)
        if first_start is None or first_end is None:
            continue
        for second in segments[index + 1 :]:
            if first_points.intersection(second.endpoint_ids()):
                continue
            second_start = point_by_id.get(second.start)
            second_end = point_by_id.get(second.end)
            if second_start is None or second_end is None:
                continue
            if _segments_intersect(first_start, first_end, second_start, second_end):
                diagnostics.append(
                    Diagnostic(
                        "unexpected_segment_intersection",
                        "Loop segments intersect away from declared shared endpoints",
                        entity_ids=(first.id, second.id),
                        details={"loop_id": loop_id},
                    )
                )
    return diagnostics


def _segments_intersect(a: Point, b: Point, c: Point, d: Point, *, tolerance: float = 1e-9) -> bool:
    ab_c = _orientation(a, b, c)
    ab_d = _orientation(a, b, d)
    cd_a = _orientation(c, d, a)
    cd_b = _orientation(c, d, b)

    if abs(ab_c) <= tolerance and _on_segment(a, c, b, tolerance=tolerance):
        return True
    if abs(ab_d) <= tolerance and _on_segment(a, d, b, tolerance=tolerance):
        return True
    if abs(cd_a) <= tolerance and _on_segment(c, a, d, tolerance=tolerance):
        return True
    if abs(cd_b) <= tolerance and _on_segment(c, b, d, tolerance=tolerance):
        return True
    return (ab_c > tolerance) != (ab_d > tolerance) and (cd_a > tolerance) != (cd_b > tolerance)


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (float(b.x) - float(a.x)) * (float(c.y) - float(a.y)) - (float(b.y) - float(a.y)) * (float(c.x) - float(a.x))


def _on_segment(a: Point, b: Point, c: Point, *, tolerance: float) -> bool:
    return (
        min(float(a.x), float(c.x)) - tolerance <= float(b.x) <= max(float(a.x), float(c.x)) + tolerance
        and min(float(a.y), float(c.y)) - tolerance <= float(b.y) <= max(float(a.y), float(c.y)) + tolerance
    )


def _is_connected(point_ids: tuple[PointId, ...], adjacency: dict[PointId, set[PointId]]) -> bool:
    if not point_ids:
        return False
    seen: set[PointId] = set()
    queue: deque[PointId] = deque([point_ids[0]])
    while queue:
        point_id = queue.popleft()
        if point_id in seen:
            continue
        seen.add(point_id)
        queue.extend(sorted(adjacency.get(point_id, ())))
    return len(seen) == len(point_ids)
