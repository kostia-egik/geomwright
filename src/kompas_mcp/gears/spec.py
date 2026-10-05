"""Public request contract for the external spur-gear module (G1/G2 slice)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .basic_racks import GOST_CONTOURS, resolve_rack

CONTOUR_VALUES = ("gost_a", "gost_b", "gost_c", "gost_d", "custom")


class SpurGearRequest(BaseModel):
    """External spur gear with a rack-generated nominal profile.

    `contour` selects the standard basic rack (ГОСТ 13755-2015, types A-D).
    Optional coefficient fields override that contour; any override marks the
    result as a modified contour instead of a standard-conformity claim.
    """

    model_config = ConfigDict(extra="forbid")

    contour: Literal["gost_a", "gost_b", "gost_c", "gost_d", "custom"] = Field(
        default="gost_a",
        title="Basic rack contour",
        description="ГОСТ 13755-2015 type A-D or explicit custom coefficients.",
    )
    module_mm: float = Field(
        default=2.0, gt=0.0, le=100.0,
        title="Normal module, mm",
        description="Normal module m. Off-row values are calculated but reported as non-standard.",
    )
    tooth_count: int = Field(
        default=20, ge=6, le=400,
        title="Tooth count",
        description="Number of teeth z.",
    )
    pressure_angle_deg: float = Field(
        default=20.0, gt=10.0, lt=35.0,
        title="Pressure angle, deg",
        description="Basic rack profile angle. The GOST A-D contours use 20 degrees.",
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
    addendum_coefficient: float | None = Field(
        default=None, ge=0.5, le=1.5,
        title="Addendum coefficient override",
        description="Optional override of h_a*; empty keeps the selected contour value.",
    )
    clearance_coefficient: float | None = Field(
        default=None, ge=0.0, le=1.0,
        title="Clearance coefficient override",
        description="Optional override of c*; empty keeps the selected contour value.",
    )
    pin_diameter_mm: float | None = Field(
        default=None, gt=0.0, le=200.0,
        title="Over-pin diameter, mm",
        description="Measurement pin/ball diameter. Empty uses the nominal 1.68 m.",
    )

    @model_validator(mode="after")
    def _reject_contour_overrides(self) -> "SpurGearRequest":
        if self.contour == "custom":
            if not any(
                value is not None
                for value in (
                    self.addendum_coefficient,
                    self.clearance_coefficient,
                )
            ):
                raise ValueError(
                    "contour=custom requires explicit addendum/clearance coefficients"
                )
        return self

    def resolved_rack(self):
        return resolve_rack(
            self.contour,
            pressure_angle_deg=self.pressure_angle_deg,
            addendum_coefficient=self.addendum_coefficient,
            clearance_coefficient=self.clearance_coefficient,
        )


def contour_options() -> list[dict[str, object]]:
    """Catalog of the named contours for UI selection metadata."""
    return [
        {
            "value": key,
            "label_ru": rack.name_ru,
            "label_en": rack.name_en,
            "pressure_angle_deg": rack.pressure_angle_deg,
            "addendum_coefficient": rack.addendum_coefficient,
            "clearance_coefficient": rack.clearance_coefficient,
            "fillet_coefficient": rack.fillet_coefficient,
            "standard_edition": rack.standard_edition,
        }
        for key, rack in GOST_CONTOURS.items()
    ] + [
        {
            "value": "custom",
            "label_ru": "Пользовательский контур",
            "label_en": "Custom contour",
            "pressure_angle_deg": None,
            "addendum_coefficient": None,
            "clearance_coefficient": None,
            "fillet_coefficient": None,
            "standard_edition": "explicit user coefficients",
        }
    ]
