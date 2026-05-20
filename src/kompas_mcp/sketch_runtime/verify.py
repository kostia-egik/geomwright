from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constraints import ConstraintPlan, ConstraintReport, verify_constraint_plan
from .diagnostics import Diagnostic
from .dimensions import DimensionBinding, DimensionReport, VariableSpec, verify_dimension_bindings
from .entities import SketchModel
from .frames import Frame2D, FrameReport, verify_frame
from .measurements import MeasurementExpectation, MeasurementReport, verify_measurements
from .orientation import LoopOrientationExpectation, LoopOrientationReport, verify_loop_orientations
from .relations import PointRelationExpectation, PointRelationReport, verify_point_relations
from .tangency import TangencyExpectation, TangencyReport, verify_tangencies
from .topology import TopologyReport, verify_topology


@dataclass(frozen=True)
class SketchPreflightPlan:
    model: SketchModel
    frame: Frame2D | None = None
    constraints: ConstraintPlan | None = None
    relations: tuple[PointRelationExpectation, ...] = ()
    tangencies: tuple[TangencyExpectation, ...] = ()
    measurements: tuple[MeasurementExpectation, ...] = ()
    orientations: tuple[LoopOrientationExpectation, ...] = ()
    variables: tuple[VariableSpec, ...] = ()
    dimensions: tuple[DimensionBinding, ...] = ()


@dataclass(frozen=True)
class SketchPreflightReport:
    stage: str
    ok: bool
    topology: TopologyReport
    frame: FrameReport | None = None
    constraints: ConstraintReport | None = None
    relations: PointRelationReport | None = None
    tangencies: TangencyReport | None = None
    measurements: MeasurementReport | None = None
    orientations: LoopOrientationReport | None = None
    dimensions: DimensionReport | None = None
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stage": self.stage,
            "ok": self.ok,
            "topology": self.topology.to_dict(),
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }
        if self.frame is not None:
            payload["frame"] = self.frame.to_dict()
        if self.constraints is not None:
            payload["constraints"] = self.constraints.to_dict()
        if self.relations is not None:
            payload["relations"] = self.relations.to_dict()
        if self.tangencies is not None:
            payload["tangencies"] = self.tangencies.to_dict()
        if self.measurements is not None:
            payload["measurements"] = self.measurements.to_dict()
        if self.orientations is not None:
            payload["orientations"] = self.orientations.to_dict()
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions.to_dict()
        return payload


def verify_sketch_preflight(
    plan: SketchPreflightPlan,
    *,
    stage: str = "preflight",
) -> SketchPreflightReport:
    topology = verify_topology(plan.model, stage="preflight_topology")
    frame = verify_frame(plan.frame, stage="preflight_frame") if plan.frame is not None else None

    entity_ids = set(plan.model.point_map()) | set(plan.model.primitive_map())
    constraints = (
        verify_constraint_plan(
            plan.constraints,
            entity_ids=entity_ids,
            stage="preflight_constraints",
        )
        if plan.constraints is not None
        else None
    )
    relations = (
        verify_point_relations(
            plan.model,
            plan.relations,
            stage="preflight_relations",
        )
        if plan.relations
        else None
    )
    tangencies = (
        verify_tangencies(
            plan.model,
            plan.tangencies,
            stage="preflight_tangencies",
        )
        if plan.tangencies
        else None
    )
    measurements = (
        verify_measurements(
            plan.model,
            plan.measurements,
            stage="preflight_measurements",
        )
        if plan.measurements
        else None
    )
    orientations = (
        verify_loop_orientations(
            plan.model,
            plan.orientations,
            stage="preflight_orientations",
        )
        if plan.orientations
        else None
    )
    dimensions = (
        verify_dimension_bindings(
            variables=plan.variables,
            dimensions=plan.dimensions,
            entity_ids=entity_ids,
            stage="preflight_dimensions",
        )
        if plan.dimensions
        else None
    )

    diagnostics = _collect_diagnostics(
        topology,
        frame,
        constraints,
        relations,
        tangencies,
        measurements,
        orientations,
        dimensions,
    )
    ok = topology.ok
    if frame is not None:
        ok = ok and frame.ok
    if constraints is not None:
        ok = ok and constraints.ok
    if relations is not None:
        ok = ok and relations.ok
    if tangencies is not None:
        ok = ok and tangencies.ok
    if measurements is not None:
        ok = ok and measurements.ok
    if orientations is not None:
        ok = ok and orientations.ok
    if dimensions is not None:
        ok = ok and dimensions.ok

    return SketchPreflightReport(
        stage=stage,
        ok=ok,
        topology=topology,
        frame=frame,
        constraints=constraints,
        relations=relations,
        tangencies=tangencies,
        measurements=measurements,
        orientations=orientations,
        dimensions=dimensions,
        diagnostics=diagnostics,
    )


def _collect_diagnostics(
    topology: TopologyReport,
    frame: FrameReport | None,
    constraints: ConstraintReport | None,
    relations: PointRelationReport | None,
    tangencies: TangencyReport | None,
    measurements: MeasurementReport | None,
    orientations: LoopOrientationReport | None,
    dimensions: DimensionReport | None,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = list(topology.diagnostics)
    if frame is not None:
        diagnostics.extend(frame.diagnostics)
    if constraints is not None:
        diagnostics.extend(constraints.diagnostics)
    if relations is not None:
        diagnostics.extend(relations.diagnostics)
    if tangencies is not None:
        diagnostics.extend(tangencies.diagnostics)
    if measurements is not None:
        diagnostics.extend(measurements.diagnostics)
    if orientations is not None:
        diagnostics.extend(orientations.diagnostics)
    if dimensions is not None:
        diagnostics.extend(dimensions.diagnostics)
    return tuple(diagnostics)
