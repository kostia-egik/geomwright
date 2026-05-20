from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .diagnostics import Diagnostic


ConstraintStageName = Literal["anchor", "orientation", "shape", "driving_dimensions", "deferred"]

DEFAULT_CONSTRAINT_STAGES: tuple[ConstraintStageName, ...] = (
    "anchor",
    "orientation",
    "shape",
    "driving_dimensions",
    "deferred",
)

_MIN_TARGETS_BY_KIND: dict[str, int] = {
    "coincident": 2,
    "collinear": 2,
    "equal_radius": 2,
    "fixed": 1,
    "horizontal": 1,
    "parallel": 2,
    "perpendicular": 2,
    "symmetric": 3,
    "tangent": 2,
    "vertical": 1,
}


@dataclass(frozen=True)
class ConstraintSpec:
    id: str
    kind: str
    target_ids: tuple[str, ...]
    stage: str = "shape"
    required: bool = True
    role: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ConstraintStageSpec:
    name: str
    required_ids: tuple[str, ...] = ()
    expected_count: int | None = None


@dataclass(frozen=True)
class ConstraintPlan:
    constraints: tuple[ConstraintSpec, ...] = ()
    stages: tuple[ConstraintStageSpec, ...] = tuple(
        ConstraintStageSpec(name=stage_name) for stage_name in DEFAULT_CONSTRAINT_STAGES
    )

    def ordered_constraints(self) -> tuple[ConstraintSpec, ...]:
        stage_index = {stage.name: index for index, stage in enumerate(self.stages)}
        return tuple(
            constraint
            for _, constraint in sorted(
                enumerate(self.constraints),
                key=lambda item: (stage_index.get(item[1].stage, len(stage_index)), item[0]),
            )
        )


@dataclass(frozen=True)
class ConstraintStageReport:
    name: str
    constraint_ids: tuple[str, ...]
    ok: bool
    expected_count: int | None = None
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "constraint_ids": list(self.constraint_ids),
            "ok": self.ok,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }
        if self.expected_count is not None:
            payload["expected_count"] = self.expected_count
        return payload


@dataclass(frozen=True)
class ConstraintReport:
    stage: str
    ok: bool
    constraint_count: int
    stages: tuple[ConstraintStageReport, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "constraint_count": self.constraint_count,
            "stages": [stage.to_dict() for stage in self.stages],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def verify_constraint_plan(
    plan: ConstraintPlan,
    *,
    entity_ids: set[str] | frozenset[str],
    stage: str = "constraints",
) -> ConstraintReport:
    diagnostics: list[Diagnostic] = []
    stage_reports: list[ConstraintStageReport] = []

    constraint_ids = [constraint.id for constraint in plan.constraints]
    constraint_by_id = {constraint.id: constraint for constraint in plan.constraints}
    if len(constraint_by_id) != len(constraint_ids):
        diagnostics.append(Diagnostic("duplicate_constraint_id", "Constraint plan contains duplicate constraint ids"))

    stage_names = [stage_spec.name for stage_spec in plan.stages]
    stage_name_set = set(stage_names)
    if len(stage_name_set) != len(stage_names):
        diagnostics.append(Diagnostic("duplicate_constraint_stage", "Constraint plan contains duplicate stage names"))

    constraints_by_stage: dict[str, list[ConstraintSpec]] = {stage_spec.name: [] for stage_spec in plan.stages}
    for constraint in plan.constraints:
        if constraint.stage not in stage_name_set:
            diagnostics.append(
                Diagnostic(
                    "unknown_constraint_stage",
                    "Constraint references a stage that is not in the plan",
                    entity_ids=(constraint.id,),
                    details={"stage": constraint.stage, "role": constraint.role},
                )
            )
            continue
        constraints_by_stage[constraint.stage].append(constraint)
        diagnostics.extend(_verify_constraint_targets(constraint, entity_ids))

    for stage_spec in plan.stages:
        stage_constraints = constraints_by_stage.get(stage_spec.name, [])
        stage_diagnostics: list[Diagnostic] = []
        stage_constraint_ids = tuple(constraint.id for constraint in stage_constraints)

        if stage_spec.expected_count is not None and len(stage_constraints) != stage_spec.expected_count:
            stage_diagnostics.append(
                Diagnostic(
                    "constraint_stage_count_mismatch",
                    "Constraint stage contains an unexpected number of constraints",
                    details={
                        "stage": stage_spec.name,
                        "expected": stage_spec.expected_count,
                        "actual": len(stage_constraints),
                    },
                )
            )
        for required_id in stage_spec.required_ids:
            if required_id not in constraint_by_id:
                stage_diagnostics.append(
                    Diagnostic(
                        "missing_required_constraint",
                        "Required constraint is missing from the plan",
                        details={"stage": stage_spec.name, "constraint_id": required_id},
                    )
                )
            elif constraint_by_id[required_id].stage != stage_spec.name:
                stage_diagnostics.append(
                    Diagnostic(
                        "required_constraint_wrong_stage",
                        "Required constraint is assigned to the wrong stage",
                        entity_ids=(required_id,),
                        details={
                            "expected_stage": stage_spec.name,
                            "actual_stage": constraint_by_id[required_id].stage,
                        },
                    )
                )

        diagnostics.extend(stage_diagnostics)
        stage_reports.append(
            ConstraintStageReport(
                name=stage_spec.name,
                constraint_ids=stage_constraint_ids,
                ok=not any(diagnostic.severity == "error" for diagnostic in stage_diagnostics),
                expected_count=stage_spec.expected_count,
                diagnostics=tuple(stage_diagnostics),
            )
        )

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return ConstraintReport(
        stage=stage,
        ok=ok,
        constraint_count=len(plan.constraints),
        stages=tuple(stage_reports),
        diagnostics=tuple(diagnostics),
    )


def _verify_constraint_targets(
    constraint: ConstraintSpec,
    entity_ids: set[str] | frozenset[str],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not constraint.kind:
        diagnostics.append(
            Diagnostic(
                "empty_constraint_kind",
                "Constraint kind must not be empty",
                entity_ids=(constraint.id,),
                details={"role": constraint.role},
            )
        )

    min_targets = _MIN_TARGETS_BY_KIND.get(constraint.kind, 1)
    if len(constraint.target_ids) < min_targets:
        diagnostics.append(
            Diagnostic(
                "constraint_target_count",
                "Constraint does not reference enough targets for its kind",
                entity_ids=(constraint.id,),
                details={
                    "kind": constraint.kind,
                    "expected_min": min_targets,
                    "actual": len(constraint.target_ids),
                    "role": constraint.role,
                },
            )
        )

    missing_targets = [target_id for target_id in constraint.target_ids if target_id not in entity_ids]
    if missing_targets:
        diagnostics.append(
            Diagnostic(
                "missing_constraint_target",
                "Constraint references an entity that does not exist",
                entity_ids=(constraint.id,),
                details={"target_ids": missing_targets, "role": constraint.role},
            )
        )

    if len(set(constraint.target_ids)) != len(constraint.target_ids):
        diagnostics.append(
            Diagnostic(
                "duplicate_constraint_target",
                "Constraint references the same target more than once",
                entity_ids=(constraint.id,),
                details={"target_ids": list(constraint.target_ids), "role": constraint.role},
            )
        )

    return diagnostics
