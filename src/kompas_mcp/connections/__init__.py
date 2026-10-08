"""Соединения валов и ступиц: прямобочные шлицы ГОСТ 1139-80.

Layer 2 владеет каталогом, геометрией, посадками и проверками; Layer 3
(`cad.py`) собирает create-only планы для вала и втулки. COM-вызовы выполняет
только bridge.
"""
from __future__ import annotations

from .cad import (
    FAMILY_CODE,
    OWNERSHIP_SCHEMA,
    PLAN_STAGE,
    RECIPE_SCHEMA,
    build_straight_spline_plan,
)
from .splines import (
    StraightSplineCreateRequest,
    StraightSplineRequest,
    build_spline_geometry,
    build_straight_spline_preview,
    list_straight_spline_sizes,
    resolve_spline_size,
    spline_selection,
    straight_spline_selection,
)

__all__ = [
    "FAMILY_CODE",
    "OWNERSHIP_SCHEMA",
    "PLAN_STAGE",
    "RECIPE_SCHEMA",
    "StraightSplineCreateRequest",
    "StraightSplineRequest",
    "build_spline_geometry",
    "build_straight_spline_plan",
    "build_straight_spline_preview",
    "list_straight_spline_sizes",
    "resolve_spline_size",
    "spline_selection",
    "straight_spline_selection",
]
