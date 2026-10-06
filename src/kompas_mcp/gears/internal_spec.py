"""Public request contract for the internal cylindrical gear module."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .basic_racks import resolve_rack


class InternalGearRequest(BaseModel):
    """Internal cylindrical gear (ring gear) with a nominal involute profile.

    The gear is cut from a ring blank whose outside diameter is an explicit
    input; the internal tooth spaces are cut from the bore. `standard` and
    `modification` select the basic-rack system exactly as for the external
    gear; only `modification="custom"` exposes the rack coefficients.
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
        default=40, ge=8, le=400,
        title="Tooth count",
        description="Number of internal teeth z.",
    )
    profile_shift: float = Field(
        default=0.0, ge=-1.5, le=1.5,
        title="Profile shift coefficient",
        description="Rack shift coefficient x2 of the internal gear; positive values thin the tooth.",
    )
    face_width_mm: float = Field(
        default=20.0, gt=0.0, le=1000.0,
        title="Face width, mm",
        description="Functional tooth width b of the ring.",
    )
    ring_outside_diameter_mm: float = Field(
        default=100.0, gt=0.0, le=5000.0,
        title="Ring blank outside diameter, mm",
        description="Outside diameter of the ring blank on whose inner surface the teeth are cut.",
    )
    helix_angle_deg: float = Field(
        default=0.0, ge=0.0, le=45.0,
        title="Helix angle, deg",
        description="Tooth helix angle beta on the reference cylinder; 0 keeps a spur internal gear.",
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
            "standard pin that fits the internal tooth space."
        ),
    )
    ring_chamfer_mm: float = Field(
        default=0.5, ge=0.0, le=50.0,
        title="Ring end chamfer width, mm",
        description="Axial width of the chamfer on both outside edges of the ring blank; 0 keeps sharp edges.",
    )
    ring_chamfer_angle_deg: float = Field(
        default=45.0, ge=15.0, le=75.0,
        title="Ring chamfer angle, deg",
        description="Angle between the ring chamfer surface and the end face; 45 degrees is the c x 45 form.",
    )
    tip_chamfer_mm: float = Field(
        default=0.0, ge=0.0, le=20.0,
        title="Tooth tip chamfer width, mm",
        description="Axial width of the chamfer on the internal tooth tips at both bore edges; 0 keeps sharp tips.",
    )
    tip_chamfer_angle_deg: float = Field(
        default=45.0, ge=15.0, le=75.0,
        title="Tooth tip chamfer angle, deg",
        description="Angle between the tooth-tip chamfer surface and the end face; 45 degrees is the c x 45 form.",
    )

    @model_validator(mode="after")
    def _validate_rack_selection(self) -> "InternalGearRequest":
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


class InternalGearCreateRequest(InternalGearRequest):
    """Create-only MCP request: plan with execute=false, write with both flags."""

    name: str = Field(default="Geomwright internal gear", min_length=1, max_length=120)
    execute: bool = False
    confirm_write: bool = False
    visible: bool = True

    @model_validator(mode="after")
    def _validate_write_confirmation(self) -> "InternalGearCreateRequest":
        if self.execute and self.confirm_write is not True:
            raise ValueError("confirm_write=true is required when execute=true")
        return self
