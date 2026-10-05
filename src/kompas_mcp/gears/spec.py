"""Public request contract for the external spur-gear module (G1/G2 slice)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .basic_racks import STANDARDS, resolve_rack, standard_options
from .modules import ROW_1, ROW_2, STANDARD_EDITION as MODULE_EDITION


class SpurGearRequest(BaseModel):
    """External spur gear with a rack-generated nominal profile.

    `standard` selects the basic-rack system; `modification` selects one of its
    named variants. The standard supplies the profile angle and the head,
    clearance, and fillet coefficients. Only `modification="custom"` exposes
    those coefficients as explicit inputs.
    """

    model_config = ConfigDict(extra="forbid")

    standard: Literal["gost_13755_2015"] = Field(
        default="gost_13755_2015",
        title="Basic rack standard",
        description="Basic-rack system. ГОСТ 13755-2015 is the first supported system.",
    )
    modification: Literal["a", "b", "c", "d", "custom"] = Field(
        default="a",
        title="Contour modification",
        description="Named modification of the selected standard, or a user-defined contour.",
    )
    module_mm: float = Field(
        default=2.0, gt=0.0, le=100.0,
        title="Normal module, mm",
        description="Normal module m selected from the standard module rows.",
    )
    tooth_count: int = Field(
        default=20, ge=6, le=400,
        title="Tooth count",
        description="Number of teeth z.",
    )
    profile_shift: float = Field(
        default=0.0, ge=-1.5, le=1.5,
        title="Profile shift coefficient",
        description="Rack shift coefficient x applied to the nominal profile.",
    )
    face_width_mm: float = Field(
        default=20.0, gt=0.0, le=1000.0,
        title="Face width, mm",
        description="Functional tooth width b of the gear rim; hub and bore are separate.",
    )
    pressure_angle_deg: float | None = Field(
        default=None, gt=10.0, lt=35.0,
        title="Pressure angle, deg",
        description="User-defined modification only; named modifications derive it from the standard.",
    )
    addendum_coefficient: float | None = Field(
        default=None, ge=0.5, le=1.5,
        title="Addendum coefficient",
        description="User-defined modification only; named modifications derive h_a* from the standard.",
    )
    clearance_coefficient: float | None = Field(
        default=None, ge=0.0, le=1.0,
        title="Clearance coefficient",
        description="User-defined modification only; named modifications derive c* from the standard.",
    )
    root_fillet_coefficient: float | None = Field(
        default=None, ge=0.0, le=0.5,
        title="Root fillet coefficient",
        description="User-defined modification only; named modifications derive rho_f* from the standard.",
    )
    pin_diameter_mm: float | None = Field(
        default=None, gt=0.0, le=200.0,
        title="Over-pin diameter, mm",
        description="Measurement pin/ball diameter. Empty uses a nominal pin that fits below the tips.",
    )

    @model_validator(mode="after")
    def _validate_modification_coefficients(self) -> "SpurGearRequest":
        if self.mode != "custom":
            if any(
                value is not None
                for value in (
                    self.pressure_angle_deg,
                    self.addendum_coefficient,
                    self.clearance_coefficient,
                    self.root_fillet_coefficient,
                )
            ):
                raise ValueError(
                    "coefficient overrides are only available for modification='custom'"
                )
        return self

    @property
    def mode(self) -> str:
        return str(self.modification or "").strip().lower()

    def resolved_rack(self):
        return resolve_rack(
            self.standard,
            self.modification,
            pressure_angle_deg=self.pressure_angle_deg,
            addendum_coefficient=self.addendum_coefficient,
            clearance_coefficient=self.clearance_coefficient,
            root_fillet_coefficient=self.root_fillet_coefficient,
        )


def gear_selection() -> dict:
    """Studio selection metadata: standards, modifications, and module rows."""
    return {
        "standards": standard_options(),
        "module_rows": {
            "edition": MODULE_EDITION,
            "row_1": list(ROW_1),
            "row_2": list(ROW_2),
        },
    }


def standard_for(value: str):
    key = str(value or "").strip().lower()
    system = STANDARDS.get(key)
    if system is None:
        raise ValueError(f"Unknown basic rack standard: {value}")
    return system
