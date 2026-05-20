from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .diagnostics import Diagnostic
from .frames import Frame2D, Vector2


AxisDirection = Literal["+x", "-x", "+y", "-y"]


@dataclass(frozen=True)
class DirectionAlias:
    id: str
    vector: Vector2
    expected: AxisDirection
    min_alignment: float = 0.999999
    role: str = ""


@dataclass(frozen=True)
class DirectionAliasResult:
    id: str
    ok: bool
    expected: AxisDirection
    alignment: float | None
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ok": self.ok,
            "expected": self.expected,
            "alignment": self.alignment,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


@dataclass(frozen=True)
class DirectionAliasReport:
    stage: str
    ok: bool
    frame_id: str
    results: tuple[DirectionAliasResult, ...]
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "frame_id": self.frame_id,
            "results": [result.to_dict() for result in self.results],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def verify_direction_aliases(
    frame: Frame2D,
    aliases: tuple[DirectionAlias, ...],
    *,
    stage: str = "direction_aliases",
    tolerance: float = 1e-9,
) -> DirectionAliasReport:
    diagnostics: list[Diagnostic] = []
    results: list[DirectionAliasResult] = []

    alias_ids = [alias.id for alias in aliases]
    if len(set(alias_ids)) != len(alias_ids):
        diagnostics.append(Diagnostic("duplicate_direction_alias_id", "Direction alias plan contains duplicate ids"))

    frame_axes, frame_diagnostics = _normalized_frame_axes(frame, tolerance)
    diagnostics.extend(frame_diagnostics)

    for alias in aliases:
        result_diagnostics: list[Diagnostic] = []
        alignment: float | None = None
        if frame_axes is None:
            result_diagnostics.append(
                Diagnostic(
                    "invalid_direction_alias_frame",
                    "Direction alias cannot be checked because the frame axes are invalid",
                    entity_ids=(alias.id,),
                    details={"frame_id": frame.id, "role": alias.role},
                )
            )
        elif alias.vector.length() <= tolerance:
            result_diagnostics.append(
                Diagnostic(
                    "zero_direction_alias",
                    "Direction alias vector must not be zero",
                    entity_ids=(alias.id,),
                    details={"frame_id": frame.id, "role": alias.role},
                )
            )
        else:
            target = frame_axes[alias.expected]
            alignment = alias.vector.normalized().dot(target)
            if alignment < alias.min_alignment:
                result_diagnostics.append(
                    Diagnostic(
                        "direction_alias_mismatch",
                        "Direction alias does not match the expected frame direction",
                        entity_ids=(alias.id,),
                        details={
                            "frame_id": frame.id,
                            "expected": alias.expected,
                            "alignment": alignment,
                            "min_alignment": alias.min_alignment,
                            "vector": alias.vector.to_list(),
                            "role": alias.role,
                        },
                    )
                )

        result = DirectionAliasResult(
            id=alias.id,
            ok=not any(diagnostic.severity == "error" for diagnostic in result_diagnostics),
            expected=alias.expected,
            alignment=alignment,
            diagnostics=tuple(result_diagnostics),
        )
        results.append(result)
        diagnostics.extend(result_diagnostics)

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return DirectionAliasReport(
        stage=stage,
        ok=ok,
        frame_id=frame.id,
        results=tuple(results),
        diagnostics=tuple(diagnostics),
    )


def _normalized_frame_axes(
    frame: Frame2D,
    tolerance: float,
) -> tuple[dict[AxisDirection, Vector2] | None, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    if frame.x_axis.length() <= tolerance:
        diagnostics.append(
            Diagnostic(
                "zero_x_axis",
                "Frame X axis must not be a zero vector",
                details={"frame_id": frame.id, "x_role": frame.x_role},
            )
        )
    if frame.y_axis.length() <= tolerance:
        diagnostics.append(
            Diagnostic(
                "zero_y_axis",
                "Frame Y axis must not be a zero vector",
                details={"frame_id": frame.id, "y_role": frame.y_role},
            )
        )
    if diagnostics:
        return None, diagnostics

    x_axis = frame.x_axis.normalized()
    y_axis = frame.y_axis.normalized()
    return {
        "+x": x_axis,
        "-x": Vector2(-x_axis.x, -x_axis.y),
        "+y": y_axis,
        "-y": Vector2(-y_axis.x, -y_axis.y),
    }, diagnostics
