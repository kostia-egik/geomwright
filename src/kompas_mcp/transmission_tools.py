from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .transmissions import list_v_belt_profiles as _list_v_belt_profiles
from .transmissions import preview_v_belt_groove as _preview_v_belt_groove
from .transmissions import resolve_v_belt_profile as _resolve_v_belt_profile


BuiltinVProfile = Literal["Z", "A", "B", "C", "D", "E", "SPZ", "SPA", "SPB", "SPC"]
VProfileDesignation = Literal["Z", "A", "B", "C", "D", "E", "SPZ", "SPA", "SPB", "SPC", "CUSTOM"]
VProfileFamily = Literal["classical", "narrow_wedge"]


class VGrooveOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datum_width: float | None = Field(default=None, gt=0)
    approximate_top_width: float | None = Field(default=None, ge=0)
    datum_offset: float | None = Field(default=None, ge=0)
    groove_pitch: float | None = Field(default=None, gt=0)
    edge_distance: float | None = Field(default=None, gt=0)
    groove_depth: float | None = Field(default=None, gt=0)
    groove_angle_degrees: float | None = Field(default=None, gt=0, lt=90)


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
    source: dict[str, Any] | None = None


class VProfileListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: VProfileFamily | None = None


class VProfileResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: BuiltinVProfile
    datum_diameter: float | None = Field(default=None, gt=0)


class VGroovePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: VProfileDesignation
    datum_diameter: float = Field(gt=0)
    groove_count: int = Field(default=1, ge=1, le=64)
    profile_overrides: VGrooveOverrides | None = None
    custom_profile: CustomVGrooveProfile | None = None


def register_transmission_tools(mcp: Any) -> None:
    @mcp.tool()
    def list_v_belt_profiles(request: VProfileListRequest) -> dict:
        """List built-in classical or narrow-wedge V-belt groove profiles."""
        return _list_v_belt_profiles(family=request.family)

    @mcp.tool()
    def resolve_v_belt_profile(
        request: VProfileResolveRequest,
    ) -> dict:
        """Resolve one V-belt groove profile and its diameter-dependent angle."""
        return _resolve_v_belt_profile(
            designation=request.designation,
            datum_diameter=request.datum_diameter,
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
