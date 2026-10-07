"""Public request contract for the external cylindrical gear module."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .basic_racks import STANDARDS, resolve_rack, standard_options
from .modules import module_rows_catalog
from .pins import pin_source_catalog


class SpurGearRequest(BaseModel):
    """External cylindrical gear with a rack-generated nominal profile.

    `standard` selects the basic-rack system; `modification` selects one of its
    named variants. The standard supplies the pressure angle and the head,
    clearance, and fillet coefficients. Only `modification="custom"` exposes
    those coefficients as explicit inputs. `helix_angle_deg = 0` is a spur
    gear; a positive angle turns the same module into a helical gear whose
    end view is the transverse section.
    """

    model_config = ConfigDict(extra="forbid")

    standard: str = Field(
        default="gost_13755_2015",
        title="Basic rack standard",
        description=(
            "Basic-rack system: ГОСТ 13755-2015, ГОСТ 9587-81, ГОСТ Р 50531-93, "
            "or ISO 53:1998."
        ),
    )
    modification: str = Field(
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
    helix_angle_deg: float = Field(
        default=0.0, ge=0.0, le=45.0,
        title="Helix angle, deg",
        description="Tooth helix angle beta on the reference cylinder; 0 keeps a spur gear.",
    )
    hand: Literal["right", "left"] = Field(
        default="right",
        title="Helix hand",
        description="Right- or left-hand tooth direction; ignored when the helix angle is 0.",
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
        description=(
            "Measurement pin/ball diameter. Empty selects the nearest cached "
            "standard pin that fits below the tips."
        ),
    )
    tip_chamfer_mm: float = Field(
        default=0.0, ge=0.0, le=20.0,
        title="Tip chamfer width, mm",
        description="Axial width of the end chamfer on the tooth tips; 0 keeps sharp tooth ends.",
    )
    tip_chamfer_angle_deg: float = Field(
        default=45.0, ge=15.0, le=75.0,
        title="Tip chamfer angle, deg",
        description="Angle between the chamfer surface and the end face; 45 degrees is the c x 45 form.",
    )

    @model_validator(mode="after")
    def _validate_rack_selection(self) -> "SpurGearRequest":
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
        if self.hand not in ("right", "left"):
            raise ValueError("hand must be 'right' or 'left'")
        resolve_rack(
            self.standard,
            self.modification,
            pressure_angle_deg=self.pressure_angle_deg,
            addendum_coefficient=self.addendum_coefficient,
            clearance_coefficient=self.clearance_coefficient,
            root_fillet_coefficient=self.root_fillet_coefficient,
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


class SpurGearCreateRequest(SpurGearRequest):
    """Create-only MCP request: plan with execute=false, write with both flags."""

    name: str = Field(default="Geomwright cylindrical gear", min_length=1, max_length=120)
    execute: bool = False
    confirm_write: bool = False
    visible: bool = True

    @model_validator(mode="after")
    def _validate_write_confirmation(self) -> "SpurGearCreateRequest":
        if self.execute and self.confirm_write is not True:
            raise ValueError("confirm_write=true is required when execute=true")
        return self


def gear_selection() -> dict:
    """Studio selection metadata: standards, module rows, and pin rows."""
    return {
        "standards": standard_options(
            (
                "gost_13755_2015",
                "gost_9587_81",
                "gost_r_50531_93",
                "iso_53_1998",
            )
        ),
        "bevel_standards": standard_options(("gost_13754_68", "iso_53_1998")),
        "module_rows": module_rows_catalog(),
        "pin_sources": pin_source_catalog(),
    }


def bevel_gear_selection() -> dict:
    """Studio selection metadata for the straight bevel gear family."""
    selection = gear_selection()
    return {
        "standards": selection["bevel_standards"],
        "module_rows": selection["module_rows"],
        "pin_sources": selection["pin_sources"],
    }


def standard_for(value: str):
    key = str(value or "").strip().lower()
    system = STANDARDS.get(key)
    if system is None:
        raise ValueError(f"Unknown basic rack standard: {value}")
    return system
