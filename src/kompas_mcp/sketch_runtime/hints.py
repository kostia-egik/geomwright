from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .diagnostics import Diagnostic


@dataclass(frozen=True)
class RepairHint:
    code: str
    likely_cause: str
    suggested_fix: str
    entity_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "likely_cause": self.likely_cause,
            "suggested_fix": self.suggested_fix,
        }
        if self.entity_ids:
            payload["entity_ids"] = list(self.entity_ids)
        return payload


_HINTS: dict[str, tuple[str, str]] = {
    "construction_in_expected_loop": (
        "A helper/construction primitive was added to a profile loop.",
        "Move the primitive to a construction loop or mark only real profile geometry as part of the expected loop.",
    ),
    "direction_alias_mismatch": (
        "A semantic direction points against the declared local frame axis.",
        "Check the LCS axis mapping and swap/invert the alias vector before applying sketch operations.",
    ),
    "loop_orientation_mismatch": (
        "The contour was assembled in the opposite traversal direction.",
        "Reverse the segment order or swap segment endpoints for the loop before applying dimensions/constraints.",
    ),
    "measurement_mismatch": (
        "The declared geometry value differs from the actual point/primitive layout.",
        "Recompute the driving points from variables before binding dimensions or adjust the expected measurement.",
    ),
    "missing_constraint_target": (
        "A constraint references an entity id that is not present in the sketch registry.",
        "Use semantic ids from the registered points/primitives, or register the target before creating the constraint.",
    ),
    "missing_dimension_variable": (
        "A required dimension refers to an undeclared variable.",
        "Declare the variable in the dimension binding plan before the dimension is compiled.",
    ),
    "missing_endpoint": (
        "A primitive references a point that is missing from the sketch registry.",
        "Create/register all endpoint points before adding the primitive.",
    ),
    "point_relation_mismatch": (
        "A semantic relative-position expectation does not match the coordinates.",
        "Check local-frame orientation and point construction formulas for swapped left/right or inward/outward values.",
    ),
    "self_intersection": (
        "The loop is topologically closed but its profile segments cross each other.",
        "Inspect point ordering and rebuild the loop in contour order.",
    ),
    "tangency_mismatch": (
        "Two primitives meet but their tangent vectors do not align.",
        "Check arc center/direction or the adjacent segment endpoint before applying tangent constraints.",
    ),
}


def build_repair_hints(diagnostics: tuple[Diagnostic, ...], *, limit: int = 8) -> tuple[RepairHint, ...]:
    hints: list[RepairHint] = []
    seen_codes: set[str] = set()
    for diagnostic in diagnostics:
        if diagnostic.code in seen_codes:
            continue
        hint = _HINTS.get(diagnostic.code)
        if hint is None:
            continue
        seen_codes.add(diagnostic.code)
        likely_cause, suggested_fix = hint
        hints.append(
            RepairHint(
                code=diagnostic.code,
                likely_cause=likely_cause,
                suggested_fix=suggested_fix,
                entity_ids=diagnostic.entity_ids,
            )
        )
        if len(hints) >= max(0, limit):
            break
    return tuple(hints)
