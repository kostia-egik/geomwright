from __future__ import annotations

import re
from dataclasses import dataclass, field
from math import cos, sin, sqrt, tan
from typing import Any

from .diagnostics import Diagnostic


_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_REFERENCE_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*\b")
_NUMERIC_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
_SAFE_EXPRESSION_PATTERN = re.compile(r"^[A-Za-z0-9_+\-*/()., \t]+$")
_FUNCTION_NAMES = frozenset({"abs", "min", "max", "sqrt", "sin", "cos", "tan"})
_FUNCTIONS = {"abs": abs, "min": min, "max": max, "sqrt": sqrt, "sin": sin, "cos": cos, "tan": tan}


@dataclass(frozen=True)
class VariableSpec:
    name: str
    value: float | int | None = None
    unit: str = "mm"
    role: str = ""


@dataclass(frozen=True)
class DimensionBinding:
    id: str
    kind: str
    target_ids: tuple[str, ...]
    variable: str
    expression: str | None = None
    required: bool = True
    role: str = ""


@dataclass(frozen=True)
class DimensionReadback:
    id: str
    expression: str | None = None
    value: float | int | None = None
    role: str = ""


@dataclass(frozen=True)
class DimensionReport:
    stage: str
    ok: bool
    variable_count: int
    dimension_count: int
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "variable_count": self.variable_count,
            "dimension_count": self.dimension_count,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def verify_dimension_bindings(
    *,
    variables: tuple[VariableSpec, ...],
    dimensions: tuple[DimensionBinding, ...],
    entity_ids: set[str] | frozenset[str],
    stage: str = "dimensions",
) -> DimensionReport:
    diagnostics: list[Diagnostic] = []
    variable_names = [variable.name for variable in variables]
    variable_set = set(variable_names)
    dimension_ids = [dimension.id for dimension in dimensions]

    if len(variable_set) != len(variable_names):
        diagnostics.append(Diagnostic("duplicate_variable_name", "Dimension plan contains duplicate variable names"))
    if len(set(dimension_ids)) != len(dimension_ids):
        diagnostics.append(Diagnostic("duplicate_dimension_id", "Dimension plan contains duplicate dimension ids"))

    for variable in variables:
        if not _NAME_PATTERN.match(variable.name):
            diagnostics.append(
                Diagnostic(
                    "invalid_variable_name",
                    "Variable name must be a simple KOMPAS-safe identifier",
                    details={"name": variable.name, "role": variable.role},
                )
            )

    for dimension in dimensions:
        if not _NAME_PATTERN.match(dimension.variable):
            diagnostics.append(
                Diagnostic(
                    "invalid_dimension_variable",
                    "Dimension variable must be a simple KOMPAS-safe identifier",
                    entity_ids=(dimension.id,),
                    details={"variable": dimension.variable, "role": dimension.role},
                )
            )
        if dimension.required and dimension.variable not in variable_set:
            diagnostics.append(
                Diagnostic(
                    "missing_dimension_variable",
                    "Required dimension variable is not declared",
                    entity_ids=(dimension.id,),
                    details={"variable": dimension.variable, "role": dimension.role},
                )
            )

        missing_targets = [target_id for target_id in dimension.target_ids if target_id not in entity_ids]
        if missing_targets:
            diagnostics.append(
                Diagnostic(
                    "missing_dimension_target",
                    "Dimension references an entity that does not exist",
                    entity_ids=(dimension.id,),
                    details={"target_ids": missing_targets, "role": dimension.role},
                )
            )

        expression = (dimension.expression or dimension.variable).strip()
        if not expression:
            diagnostics.append(
                Diagnostic(
                    "empty_dimension_expression",
                    "Dimension expression must not be empty",
                    entity_ids=(dimension.id,),
                    details={"variable": dimension.variable},
                )
            )
            continue
        for reference in _expression_references(expression):
            if reference not in variable_set:
                diagnostics.append(
                    Diagnostic(
                        "unknown_expression_reference",
                        "Dimension expression references an undeclared variable",
                        entity_ids=(dimension.id,),
                        details={"reference": reference, "expression": expression},
                    )
                )

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return DimensionReport(
        stage=stage,
        ok=ok,
        variable_count=len(variables),
        dimension_count=len(dimensions),
        diagnostics=tuple(diagnostics),
    )


@dataclass(frozen=True)
class DimensionReadbackReport:
    stage: str
    ok: bool
    readback_count: int
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "readback_count": self.readback_count,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def verify_dimension_readback(
    *,
    variables: tuple[VariableSpec, ...],
    dimensions: tuple[DimensionBinding, ...],
    readbacks: tuple[DimensionReadback, ...],
    stage: str = "dimension_readback",
    tolerance: float = 1e-6,
) -> DimensionReadbackReport:
    diagnostics: list[Diagnostic] = []
    readback_by_id = {readback.id: readback for readback in readbacks}
    if len(readback_by_id) != len(readbacks):
        diagnostics.append(Diagnostic("duplicate_dimension_readback_id", "Dimension readback contains duplicate ids"))

    variable_values = {variable.name: float(variable.value) for variable in variables if variable.value is not None}
    for dimension in dimensions:
        readback = readback_by_id.get(dimension.id)
        if readback is None:
            if dimension.required:
                diagnostics.append(
                    Diagnostic(
                        "missing_dimension_readback",
                        "Required dimension has no readback data",
                        entity_ids=(dimension.id,),
                        details={"role": dimension.role},
                    )
                )
            continue

        expected_expression = (dimension.expression or dimension.variable).strip()
        actual_expression = (readback.expression or "").strip()
        if not actual_expression:
            diagnostics.append(
                Diagnostic(
                    "missing_dimension_expression_readback",
                    "Dimension readback has no expression",
                    entity_ids=(dimension.id,),
                    details={"expected": expected_expression, "role": dimension.role or readback.role},
                )
            )
        elif _normalize_expression(actual_expression) != _normalize_expression(expected_expression):
            code = "formula_numeric_fallback" if _is_numeric_fallback(actual_expression, expected_expression) else "formula_not_bound"
            diagnostics.append(
                Diagnostic(
                    code,
                    "Dimension expression readback does not match the expected formula",
                    entity_ids=(dimension.id,),
                    details={
                        "expected": expected_expression,
                        "actual": actual_expression,
                        "role": dimension.role or readback.role,
                    },
                )
            )

        expected_value = _try_eval_expression(expected_expression, variable_values)
        if expected_value is not None and readback.value is not None:
            actual_value = float(readback.value)
            if abs(actual_value - expected_value) > tolerance:
                diagnostics.append(
                    Diagnostic(
                        "dimension_value_mismatch",
                        "Dimension value readback does not match the expected expression value",
                        entity_ids=(dimension.id,),
                        details={
                            "expected": expected_value,
                            "actual": actual_value,
                            "tolerance": tolerance,
                            "role": dimension.role or readback.role,
                        },
                    )
                )

    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return DimensionReadbackReport(
        stage=stage,
        ok=ok,
        readback_count=len(readbacks),
        diagnostics=tuple(diagnostics),
    )


def _expression_references(expression: str) -> tuple[str, ...]:
    references: list[str] = []
    for token in _REFERENCE_PATTERN.findall(expression):
        if token in _FUNCTION_NAMES:
            continue
        references.append(token)
    return tuple(references)


def _normalize_expression(expression: str) -> str:
    return "".join(expression.split())


def _is_numeric_fallback(actual_expression: str, expected_expression: str) -> bool:
    return bool(_NUMERIC_PATTERN.match(actual_expression.strip())) and bool(_expression_references(expected_expression))


def _try_eval_expression(expression: str, variable_values: dict[str, float]) -> float | None:
    if not _SAFE_EXPRESSION_PATTERN.match(expression):
        return None
    references = _expression_references(expression)
    if any(reference not in variable_values for reference in references):
        return None
    namespace: dict[str, object] = dict(_FUNCTIONS)
    namespace.update(variable_values)
    try:
        return float(eval(expression, {"__builtins__": {}}, namespace))
    except Exception:
        return None
