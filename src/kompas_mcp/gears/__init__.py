"""Cylindrical gear module: external and internal involute slices.

Host-side geometry, checks, and measurements live in this package. CAD planning
is added in `cad.py`; no COM access happens here.
"""
from __future__ import annotations

from .basic_racks import STANDARD_EDITION, STANDARDS, BasicRack, resolve_rack, standard_options
from .checks import evaluate_gear_checks
from .internal import (
    InternalGearGeometry,
    build_internal_gear_geometry,
    build_internal_gear_preview,
    evaluate_internal_gear_checks,
    internal_constant_chord,
    internal_over_pin_measurement,
)
from .internal_spec import InternalGearCreateRequest, InternalGearRequest
from .involute import SpurGearGeometry, build_spur_gear_geometry, involute
from .measure import base_pitch, constant_chord, over_pin_measurement, span_measurement
from .modules import describe_module, is_standard_module, module_row, module_rows_catalog
from .pins import pin_source_catalog, select_standard_pin, standard_pin_candidates
from .preview import build_spur_gear_preview
from .spec import SpurGearCreateRequest, SpurGearRequest, gear_selection

__all__ = [
    "BasicRack",
    "STANDARDS",
    "STANDARD_EDITION",
    "InternalGearCreateRequest",
    "InternalGearGeometry",
    "InternalGearRequest",
    "SpurGearCreateRequest",
    "SpurGearGeometry",
    "SpurGearRequest",
    "base_pitch",
    "build_internal_gear_geometry",
    "build_internal_gear_preview",
    "build_spur_gear_geometry",
    "build_spur_gear_preview",
    "constant_chord",
    "describe_module",
    "evaluate_gear_checks",
    "evaluate_internal_gear_checks",
    "gear_selection",
    "internal_constant_chord",
    "internal_over_pin_measurement",
    "involute",
    "is_standard_module",
    "module_row",
    "module_rows_catalog",
    "over_pin_measurement",
    "pin_source_catalog",
    "resolve_rack",
    "select_standard_pin",
    "span_measurement",
    "standard_options",
    "standard_pin_candidates",
]
