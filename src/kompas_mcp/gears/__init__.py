"""External spur-gear module (cylindrical gears, first G1/G2 slice).

Host-side geometry, checks, and measurements live in this package. CAD planning
is added in `cad.py`; no COM access happens here.
"""
from __future__ import annotations

from .basic_racks import STANDARD_EDITION, STANDARDS, BasicRack, resolve_rack, standard_options
from .checks import evaluate_gear_checks
from .involute import SpurGearGeometry, build_spur_gear_geometry, involute
from .measure import base_pitch, constant_chord, over_pin_measurement, span_measurement
from .modules import describe_module, is_standard_module, module_row
from .preview import build_spur_gear_preview
from .spec import SpurGearRequest, gear_selection

__all__ = [
    "BasicRack",
    "STANDARDS",
    "STANDARD_EDITION",
    "SpurGearGeometry",
    "SpurGearRequest",
    "base_pitch",
    "build_spur_gear_geometry",
    "build_spur_gear_preview",
    "constant_chord",
    "describe_module",
    "evaluate_gear_checks",
    "gear_selection",
    "involute",
    "is_standard_module",
    "module_row",
    "over_pin_measurement",
    "resolve_rack",
    "span_measurement",
    "standard_options",
]
