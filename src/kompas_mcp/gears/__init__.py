"""External spur-gear module (cylindrical gears, first G1/G2 slice).

Host-side geometry, checks, and measurements live in this package. CAD planning
is added in `cad.py`; no COM access happens here.
"""
from __future__ import annotations

from .basic_racks import GOST_CONTOURS, STANDARD_EDITION, BasicRack, resolve_rack
from .checks import evaluate_gear_checks
from .involute import SpurGearGeometry, build_spur_gear_geometry, involute
from .measure import base_pitch, constant_chord, over_pin_measurement, span_measurement
from .modules import describe_module, is_standard_module, module_row
from .preview import build_spur_gear_preview
from .spec import SpurGearRequest, contour_options

__all__ = [
    "BasicRack",
    "GOST_CONTOURS",
    "STANDARD_EDITION",
    "SpurGearGeometry",
    "SpurGearRequest",
    "base_pitch",
    "build_spur_gear_geometry",
    "build_spur_gear_preview",
    "constant_chord",
    "contour_options",
    "describe_module",
    "evaluate_gear_checks",
    "involute",
    "is_standard_module",
    "module_row",
    "over_pin_measurement",
    "resolve_rack",
    "span_measurement",
]
