from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from .diagnostics import Diagnostic


Handedness = Literal["right", "left"]


@dataclass(frozen=True)
class Vector2:
    x: float
    y: float

    def length(self) -> float:
        return math.hypot(float(self.x), float(self.y))

    def normalized(self) -> "Vector2":
        length = self.length()
        if length <= 0.0:
            raise ValueError("cannot normalize a zero vector")
        return Vector2(float(self.x) / length, float(self.y) / length)

    def dot(self, other: "Vector2") -> float:
        return float(self.x) * float(other.x) + float(self.y) * float(other.y)

    def cross(self, other: "Vector2") -> float:
        return float(self.x) * float(other.y) - float(self.y) * float(other.x)

    def to_list(self) -> list[float]:
        return [float(self.x), float(self.y)]


@dataclass(frozen=True)
class Frame2D:
    id: str
    origin: tuple[float, float] = (0.0, 0.0)
    x_axis: Vector2 = Vector2(1.0, 0.0)
    y_axis: Vector2 = Vector2(0.0, 1.0)
    x_role: str = ""
    y_role: str = ""
    expected_handedness: Handedness = "right"


@dataclass(frozen=True)
class FrameReport:
    stage: str
    frame_id: str
    ok: bool
    handedness: Handedness | None
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "frame_id": self.frame_id,
            "ok": self.ok,
            "handedness": self.handedness,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def verify_frame(
    frame: Frame2D,
    *,
    stage: str = "frame",
    tolerance: float = 1e-9,
) -> FrameReport:
    diagnostics: list[Diagnostic] = []

    x_length = frame.x_axis.length()
    y_length = frame.y_axis.length()
    if x_length <= tolerance:
        diagnostics.append(
            Diagnostic(
                "zero_x_axis",
                "Frame X axis must not be a zero vector",
                details={"frame_id": frame.id, "x_role": frame.x_role},
            )
        )
    if y_length <= tolerance:
        diagnostics.append(
            Diagnostic(
                "zero_y_axis",
                "Frame Y axis must not be a zero vector",
                details={"frame_id": frame.id, "y_role": frame.y_role},
            )
        )

    handedness: Handedness | None = None
    if x_length > tolerance and y_length > tolerance:
        x_axis = frame.x_axis.normalized()
        y_axis = frame.y_axis.normalized()
        dot = x_axis.dot(y_axis)
        cross = x_axis.cross(y_axis)
        if abs(dot) > tolerance:
            diagnostics.append(
                Diagnostic(
                    "non_orthogonal_axes",
                    "Frame axes must be orthogonal",
                    details={"frame_id": frame.id, "dot": dot},
                )
            )
        if abs(cross) <= tolerance:
            diagnostics.append(
                Diagnostic(
                    "collinear_axes",
                    "Frame axes must not be collinear",
                    details={"frame_id": frame.id, "cross": cross},
                )
            )
        else:
            handedness = "right" if cross > 0.0 else "left"
            if handedness != frame.expected_handedness:
                diagnostics.append(
                    Diagnostic(
                        "wrong_handedness",
                        "Frame handedness does not match the contract",
                        details={
                            "frame_id": frame.id,
                            "expected": frame.expected_handedness,
                            "actual": handedness,
                            "x_role": frame.x_role,
                            "y_role": frame.y_role,
                        },
                    )
                )

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return FrameReport(
        stage=stage,
        frame_id=frame.id,
        ok=ok,
        handedness=handedness,
        diagnostics=tuple(diagnostics),
    )
