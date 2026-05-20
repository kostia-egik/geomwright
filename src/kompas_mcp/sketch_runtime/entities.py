from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


PointId = str
PrimitiveId = str
PrimitiveKind = Literal["segment", "arc"]


@dataclass(frozen=True)
class Point:
    id: PointId
    x: float
    y: float
    role: str = ""

    def as_xy(self) -> tuple[float, float]:
        return (float(self.x), float(self.y))


@dataclass(frozen=True)
class Segment:
    id: PrimitiveId
    start: PointId
    end: PointId
    role: str = ""
    loop_id: str = "main"

    @property
    def kind(self) -> PrimitiveKind:
        return "segment"

    def endpoint_ids(self) -> tuple[PointId, PointId]:
        return (self.start, self.end)


@dataclass(frozen=True)
class Arc:
    id: PrimitiveId
    start: PointId
    end: PointId
    center: PointId
    direction: Literal["cw", "ccw"] = "ccw"
    role: str = ""
    loop_id: str = "main"

    @property
    def kind(self) -> PrimitiveKind:
        return "arc"

    def endpoint_ids(self) -> tuple[PointId, PointId]:
        return (self.start, self.end)


SketchPrimitive = Segment | Arc


@dataclass(frozen=True)
class SketchModel:
    points: tuple[Point, ...] = ()
    primitives: tuple[SketchPrimitive, ...] = ()
    expected_loops: tuple[str, ...] = ("main",)
    name: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def point_map(self) -> dict[PointId, Point]:
        return {point.id: point for point in self.points}

    def primitive_map(self) -> dict[PrimitiveId, SketchPrimitive]:
        return {primitive.id: primitive for primitive in self.primitives}
