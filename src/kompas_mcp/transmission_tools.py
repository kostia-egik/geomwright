from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .transmissions import list_v_belt_profiles as _list_v_belt_profiles
from .transmissions import list_poly_v_profiles as _list_poly_v_profiles
from .transmissions import preview_flat_belt_pulley as _preview_flat_belt_pulley
from .transmissions import preview_timing_belt_pulley as _preview_timing_belt_pulley
from .transmissions import preview_poly_v_groove as _preview_poly_v_groove
from .transmissions import preview_v_belt_groove as _preview_v_belt_groove
from .transmissions import resolve_poly_v_profile as _resolve_poly_v_profile
from .transmissions import resolve_v_belt_profile as _resolve_v_belt_profile


BuiltinVProfile = Literal["Z", "A", "B", "C", "D", "E", "SPZ", "SPA", "SPB", "SPC"]
VProfileDesignation = Literal["Z", "A", "B", "C", "D", "E", "SPZ", "SPA", "SPB", "SPC", "CUSTOM"]
VProfileFamily = Literal["classical", "narrow_wedge"]
VStandardSystem = Literal["din_iso", "gost_20889_88"]
PolyVProfileDesignation = Literal["PH", "PJ", "PK", "PL", "PM"]
FlatPulleyProfile = Literal["cylindrical", "crowned"]
TimingPulleyDesignation = Literal["T2.5", "T5", "T10", "AT5", "HTD_3M", "HTD_5M", "HTD_8M", "CUSTOM"]
TimingPulleyShape = Literal["trapezoidal", "curvilinear"]


class VGrooveOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datum_width: float | None = Field(default=None, gt=0)
    approximate_top_width: float | None = Field(default=None, ge=0)
    datum_offset: float | None = Field(default=None, ge=0)
    groove_pitch: float | None = Field(default=None, gt=0)
    edge_distance: float | None = Field(default=None, gt=0)
    groove_depth: float | None = Field(default=None, gt=0)
    groove_angle_degrees: float | None = Field(default=None, gt=0, lt=90)
    standard_top_edge_radius: float | None = Field(default=None, gt=0)


class CustomVGrooveProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: str = "CUSTOM"
    family: str = "custom"
    datum_width: float = Field(gt=0)
    approximate_top_width: float = Field(default=0, ge=0)
    datum_offset: float = Field(ge=0)
    groove_pitch: float = Field(gt=0)
    edge_distance: float = Field(gt=0)
    groove_depth: float = Field(gt=0)
    groove_angle_degrees: float = Field(gt=0, lt=90)
    minimum_datum_diameter: float = Field(default=0, ge=0)
    standard_top_edge_radius: float | None = Field(default=None, gt=0)
    source: dict[str, Any] | None = None


class VProfileListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: VProfileFamily | None = None
    standard_system: VStandardSystem = "din_iso"


class VProfileResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: BuiltinVProfile
    datum_diameter: float | None = Field(default=None, gt=0)
    standard_system: VStandardSystem = "din_iso"


class VGroovePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: VProfileDesignation
    datum_diameter: float = Field(gt=0)
    groove_count: int = Field(default=1, ge=1, le=64)
    standard_system: VStandardSystem = "din_iso"
    profile_overrides: VGrooveOverrides | None = None
    custom_profile: CustomVGrooveProfile | None = None


class PolyVProfileResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: PolyVProfileDesignation


class PolyVGroovePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: PolyVProfileDesignation
    effective_diameter: float = Field(gt=0)
    groove_count: int = Field(default=1, ge=1, le=64)


class FlatBeltPulleyPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outer_diameter: float = Field(gt=0)
    face_width: float = Field(gt=0)
    crown_height: float = Field(
        default=0.0,
        ge=0,
        description="Zero creates a cylindrical rim; a positive value creates a crowned rim.",
    )


class TimingBeltPulleyPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: TimingPulleyDesignation = "HTD_5M"
    tooth_count: int = Field(default=24, ge=8, le=360)
    face_width: float = Field(default=20.0, gt=0)
    custom_shape: TimingPulleyShape | None = None
    custom_pitch: float | None = Field(default=None, gt=0)
    custom_groove_depth: float | None = Field(default=None, gt=0)
    custom_groove_width: float | None = Field(default=None, gt=0)
    custom_pitch_line_offset: float | None = Field(default=None, gt=0)
    custom_tip_radius: float | None = Field(default=None, gt=0)
    custom_root_radius: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_custom_profile(self) -> "TimingBeltPulleyPreviewRequest":
        required_custom_values = (
            self.custom_shape,
            self.custom_pitch,
            self.custom_groove_depth,
            self.custom_groove_width,
            self.custom_pitch_line_offset,
        )
        all_custom_values = (*required_custom_values, self.custom_tip_radius, self.custom_root_radius)
        if self.designation == "CUSTOM" and any(value is None for value in required_custom_values):
            raise ValueError("CUSTOM requires shape, pitch, groove depth/width, and pitch-line offset")
        if self.designation != "CUSTOM" and any(value is not None for value in all_custom_values):
            raise ValueError("custom timing dimensions are allowed only for designation=CUSTOM")
        return self


class TimingTrapezoidalPulleyPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: Literal["T2.5", "T5", "T10", "AT5", "CUSTOM"] = "T5"
    tooth_count: int = Field(default=24, ge=8, le=360)
    face_width: float = Field(default=20.0, gt=0)
    custom_pitch: float | None = Field(default=None, gt=0)
    custom_groove_depth: float | None = Field(default=None, gt=0)
    custom_groove_width: float | None = Field(default=None, gt=0)
    custom_pitch_line_offset: float | None = Field(default=None, gt=0)
    custom_tip_radius: float | None = Field(default=None, gt=0)
    custom_root_radius: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_custom_profile(self) -> "TimingTrapezoidalPulleyPreviewRequest":
        required_values = (self.custom_pitch, self.custom_groove_depth, self.custom_groove_width, self.custom_pitch_line_offset)
        all_values = (*required_values, self.custom_tip_radius, self.custom_root_radius)
        if self.designation == "CUSTOM" and any(value is None for value in required_values):
            raise ValueError("CUSTOM requires pitch, groove depth/width, and pitch-line offset")
        if self.designation != "CUSTOM" and any(value is not None for value in all_values):
            raise ValueError("custom timing dimensions are allowed only for designation=CUSTOM")
        return self


class TimingCurvilinearPulleyPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: Literal["HTD_3M", "HTD_5M", "HTD_8M", "CUSTOM"] = "HTD_5M"
    tooth_count: int = Field(default=24, ge=8, le=360)
    face_width: float = Field(default=20.0, gt=0)
    custom_pitch: float | None = Field(default=None, gt=0)
    custom_groove_depth: float | None = Field(default=None, gt=0)
    custom_groove_width: float | None = Field(default=None, gt=0)
    custom_pitch_line_offset: float | None = Field(default=None, gt=0)
    custom_tip_radius: float | None = Field(default=None, gt=0)
    custom_root_radius: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_custom_profile(self) -> "TimingCurvilinearPulleyPreviewRequest":
        required_values = (self.custom_pitch, self.custom_groove_depth, self.custom_groove_width, self.custom_pitch_line_offset)
        all_values = (*required_values, self.custom_tip_radius, self.custom_root_radius)
        if self.designation == "CUSTOM" and any(value is None for value in required_values):
            raise ValueError("CUSTOM requires pitch, groove depth/width, and pitch-line offset")
        if self.designation != "CUSTOM" and any(value is not None for value in all_values):
            raise ValueError("custom timing dimensions are allowed only for designation=CUSTOM")
        return self


class RotationalBlankParameterBaseContract(BaseModel):
    """Operation variables that define a composed rotational blank."""

    model_config = ConfigDict(extra="forbid")

    outer_radius_variable: str = Field(min_length=1, max_length=64)
    face_width_variable: str = Field(min_length=1, max_length=64)


class RotationalBlankContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    axis: Literal["global_x"] = "global_x"
    body_count: Literal[1] = 1
    outer_diameter: float = Field(gt=0)
    axial_min: float
    axial_max: float
    parameter_base: RotationalBlankParameterBaseContract

    @model_validator(mode="after")
    def validate_interval(self) -> "RotationalBlankContract":
        if self.axial_max <= self.axial_min:
            raise ValueError("axial_max must be greater than axial_min")
        return self


class VGrooveApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    profile: VGroovePreviewRequest
    target: RotationalBlankContract
    axial_center: float = 0.0
    name: str = Field(
        default="V-belt grooves",
        min_length=1,
        max_length=120,
        description=(
            "Optional semantic label appended to the canonical KOMPAS sketch, "
            "rotational-cut, and fillet names"
        ),
    )
    top_edge_fillet_radius: float | None = Field(default=None, gt=0.0)
    include_standard_top_edge_fillet: bool = True
    execute: bool = False
    confirm_write: bool = False

    @model_validator(mode="after")
    def validate_write_confirmation(self) -> "VGrooveApplyRequest":
        if self.execute and self.confirm_write is not True:
            raise ValueError("confirm_write=true is required when execute=true")
        return self


class PolyVGrooveApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    profile: PolyVGroovePreviewRequest
    target: RotationalBlankContract
    axial_center: float = 0.0
    name: str = Field(
        default="Poly-V grooves",
        min_length=1,
        max_length=120,
        description="Optional semantic label appended to canonical KOMPAS sketch and cut names",
    )
    execute: bool = False
    confirm_write: bool = False

    @model_validator(mode="after")
    def validate_write_confirmation(self) -> "PolyVGrooveApplyRequest":
        if self.execute and self.confirm_write is not True:
            raise ValueError("confirm_write=true is required when execute=true")
        return self


def register_transmission_tools(mcp: Any, adapter: Any) -> None:
    @mcp.tool()
    def preview_timing_belt_pulley(request: TimingBeltPulleyPreviewRequest) -> dict:
        """Preview an end-view synchronous-belt pulley tooth profile; no CAD write."""
        return _preview_timing_belt_pulley(**request.model_dump(exclude_none=True))

    @mcp.tool()
    def preview_flat_belt_pulley(request: FlatBeltPulleyPreviewRequest) -> dict:
        """Preview a cylindrical or explicitly crowned flat-belt pulley rim."""
        return _preview_flat_belt_pulley(**request.model_dump())

    @mcp.tool()
    def list_poly_v_profiles() -> dict:
        """List ISO 9982:2021 PH, PJ, PK, PL, and PM Poly-V pulley profiles."""
        return _list_poly_v_profiles()

    @mcp.tool()
    def resolve_poly_v_profile(request: PolyVProfileResolveRequest) -> dict:
        """Resolve one ISO 9982:2021 Poly-V pulley groove profile."""
        return _resolve_poly_v_profile(designation=request.designation)

    @mcp.tool()
    def preview_poly_v_groove(request: PolyVGroovePreviewRequest) -> dict:
        """Preview a rounded Poly-V pulley groove set without hubs, bores, or COM."""
        return _preview_poly_v_groove(
            designation=request.designation,
            effective_diameter=request.effective_diameter,
            groove_count=request.groove_count,
        )

    @mcp.tool()
    def list_v_belt_profiles(request: VProfileListRequest) -> dict:
        """List built-in classical or narrow-wedge V-belt groove profiles."""
        return _list_v_belt_profiles(family=request.family, standard_system=request.standard_system)

    @mcp.tool()
    def resolve_v_belt_profile(
        request: VProfileResolveRequest,
    ) -> dict:
        """Resolve one V-belt groove profile and its diameter-dependent angle."""
        return _resolve_v_belt_profile(
            designation=request.designation,
            datum_diameter=request.datum_diameter,
            standard_system=request.standard_system,
        )

    @mcp.tool()
    def preview_v_belt_groove(
        request: VGroovePreviewRequest,
    ) -> dict:
        """Preview functional V-groove cut geometry without hubs, bores, or COM."""
        return _preview_v_belt_groove(
            designation=request.designation,
            datum_diameter=request.datum_diameter,
            groove_count=request.groove_count,
            standard_system=request.standard_system,
            profile_overrides=(
                request.profile_overrides.model_dump(exclude_none=True)
                if request.profile_overrides
                else None
            ),
            custom_profile=(
                request.custom_profile.model_dump(exclude_none=True)
                if request.custom_profile
                else None
            ),
        )

    @mcp.tool()
    def apply_v_belt_grooves(request: VGrooveApplyRequest) -> dict:
        """Preflight or cut previewed V-grooves into one global-X rotational body."""
        return adapter.apply_v_belt_grooves(
            document_id=request.document_id,
            preview_request=request.profile.model_dump(exclude_none=True),
            target=request.target.model_dump(),
            axial_center=request.axial_center,
            name=request.name,
            top_edge_fillet_radius=request.top_edge_fillet_radius,
            include_standard_top_edge_fillet=request.include_standard_top_edge_fillet,
            execute=request.execute,
            confirm_write=request.confirm_write,
        )

    @mcp.tool()
    def apply_poly_v_grooves(request: PolyVGrooveApplyRequest) -> dict:
        """Preflight or cut exact rounded Poly-V grooves into one global-X rotational body."""
        return adapter.apply_poly_v_grooves(
            document_id=request.document_id,
            preview_request=request.profile.model_dump(),
            target=request.target.model_dump(),
            axial_center=request.axial_center,
            name=request.name,
            execute=request.execute,
            confirm_write=request.confirm_write,
        )
