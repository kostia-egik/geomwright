from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .diagnostics import Diagnostic
from .readback import SketchReadbackReport
from .verify import SketchPreflightReport


@dataclass(frozen=True)
class SketchStateCard:
    stage: str
    ok: bool
    point_count: int
    primitive_count: int
    closed_loops: tuple[str, ...] = ()
    sections: dict[str, bool] = field(default_factory=dict)
    diagnostic_codes: tuple[str, ...] = ()
    diagnostic_entities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "point_count": self.point_count,
            "primitive_count": self.primitive_count,
            "closed_loops": list(self.closed_loops),
            "sections": dict(self.sections),
            "diagnostic_codes": list(self.diagnostic_codes),
            "diagnostic_entities": list(self.diagnostic_entities),
        }


def build_preflight_state_card(report: SketchPreflightReport, *, diagnostic_limit: int = 8) -> SketchStateCard:
    sections: dict[str, bool] = {"topology": report.topology.ok}
    for name in (
        "frame",
        "direction_aliases",
        "constraints",
        "relations",
        "tangencies",
        "measurements",
        "orientations",
        "dimensions",
    ):
        section = getattr(report, name)
        if section is not None:
            sections[name] = bool(section.ok)

    return SketchStateCard(
        stage=report.stage,
        ok=report.ok,
        point_count=report.topology.point_count,
        primitive_count=report.topology.primitive_count,
        closed_loops=tuple(loop.loop_id for loop in report.topology.loops if loop.closed),
        sections=sections,
        diagnostic_codes=_diagnostic_codes(report.diagnostics, diagnostic_limit),
        diagnostic_entities=_diagnostic_entities(report.diagnostics, diagnostic_limit),
    )


def build_readback_state_card(report: SketchReadbackReport, *, diagnostic_limit: int = 8) -> SketchStateCard:
    sections = {"readback": report.ok}
    closed_loops: tuple[str, ...] = ()
    if report.topology is not None:
        sections["topology"] = report.topology.ok
        closed_loops = tuple(loop.loop_id for loop in report.topology.loops if loop.closed)

    return SketchStateCard(
        stage=report.stage,
        ok=report.ok,
        point_count=report.actual_point_count,
        primitive_count=report.actual_primitive_count,
        closed_loops=closed_loops,
        sections=sections,
        diagnostic_codes=_diagnostic_codes(report.diagnostics, diagnostic_limit),
        diagnostic_entities=_diagnostic_entities(report.diagnostics, diagnostic_limit),
    )


def _diagnostic_codes(diagnostics: tuple[Diagnostic, ...], limit: int) -> tuple[str, ...]:
    return tuple(diagnostic.code for diagnostic in diagnostics[: max(0, limit)])


def _diagnostic_entities(diagnostics: tuple[Diagnostic, ...], limit: int) -> tuple[str, ...]:
    entity_ids: list[str] = []
    seen: set[str] = set()
    for diagnostic in diagnostics:
        for entity_id in diagnostic.entity_ids:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            entity_ids.append(entity_id)
            if len(entity_ids) >= limit:
                return tuple(entity_ids)
    return tuple(entity_ids)
