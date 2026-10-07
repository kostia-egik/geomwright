"""Public request contract for the bevel gear module."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .basic_racks import resolve_rack


class BevelGearRequest(BaseModel):
    """Straight bevel gear with a nominal Tredgold virtual-gear profile.

    The module builds one wheel from an explicit pitch cone angle. The tooth
    flank is the classic Tredgold construction: the tooth space of the
    equivalent (virtual) spur gear on the back cone is projected to the gear
    apex. `tooth_type="straight"` is the implemented modification;
    `tooth_type="circular"` is reserved for the circular-tooth stage and is
    rejected until that method has its own named geometry.
    """

    model_config = ConfigDict(extra="forbid")

    tooth_type: Literal["straight", "circular"] = Field(
        default="straight",
        title="Tooth type",
        description=(
            "straight - прямозубая (реализовано); "
            "circular - с круговым зубом (следующий этап, пока не строится)."
        ),
    )
    standard: str = Field(
        default="gost_13754_68",
        title="Basic rack standard",
        description=(
            "Basic-rack system: ГОСТ 13754-68 (default for bevel gears), "
            "ГОСТ 13755-2015, ГОСТ 9587-81, ГОСТ Р 50531-93, or ISO 53:1998."
        ),
    )
    modification: str = Field(
        default="standard",
        title="Contour modification",
        description="Named modification of the selected standard, or a user-defined contour.",
    )
    module_mm: float = Field(
        default=3.0, gt=0.0, le=100.0,
        title="Outer circumferential module, mm",
        description="External circumferential module m_e on the back cone.",
    )
    tooth_count: int = Field(
        default=20, ge=6, le=400,
        title="Tooth count",
        description="Number of teeth z.",
    )
    pitch_cone_angle_deg: float = Field(
        default=45.0, ge=5.0, le=85.0,
        title="Pitch cone angle, deg",
        description="Pitch cone half-angle delta; 45 degrees is a 1:1 orthogonal pair.",
    )
    profile_shift: float = Field(
        default=0.0, ge=-1.5, le=1.5,
        title="Profile shift coefficient",
        description="Rack shift coefficient x of the wheel.",
    )
    face_width_mm: float | None = Field(
        default=None, gt=0.0, le=1000.0,
        title="Face width, mm",
        description=(
            "Functional face width b along the pitch cone. Empty selects the "
            "ГОСТ 19624-74 recommendation b = 0.285 R_e."
        ),
    )
    rim_back_extension_mm: float | None = Field(
        default=None, ge=0.0, le=500.0,
        title="Back cone extension, mm",
        description=(
            "Axial extension of the back conical rim face behind the outer tip "
            "plane. Empty selects 0.3 b sin(delta) (at least 1.5 mm)."
        ),
    )
    rim_front_extension_mm: float | None = Field(
        default=None, ge=0.0, le=500.0,
        title="Front cone extension, mm",
        description=(
            "Axial extension of the front conical rim face behind the inner tip "
            "plane. Empty selects 0.3 b sin(delta) (at least 1.5 mm)."
        ),
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

    @model_validator(mode="after")
    def _validate_selection(self) -> "BevelGearRequest":
        if self.tooth_type != "straight":
            raise ValueError(
                "Круговая модификация конической передачи входит в следующий этап; "
                "сейчас доступна tooth_type='straight'."
            )
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


class BevelGearCreateRequest(BevelGearRequest):
    """Create-only MCP request: plan with execute=false, write with both flags."""

    name: str = Field(default="Geomwright bevel gear", min_length=1, max_length=120)
    execute: bool = False
    confirm_write: bool = False
    visible: bool = True

    @model_validator(mode="after")
    def _validate_write_confirmation(self) -> "BevelGearCreateRequest":
        if self.execute and self.confirm_write is not True:
            raise ValueError("confirm_write=true is required when execute=true")
        return self
