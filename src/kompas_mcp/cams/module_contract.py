"""Typed shared-interface inputs; engineering validation stays in cams.spec."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .spec import normalize_cam_request


class CamTimingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    open_deg: float
    close_deg: float
    dwell_deg: float = 0.0
    nose_center_deg: float | None = None
    cam_reference_deg: float = 0.0


class CamMotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    law: Literal["polydyne_345", "polydyne_4567", "polydyne_56789", "cycloidal",
                 "curvature_spline", "motion_spline", "bounded_auto"] = "polydyne_345"
    base_radius: float = 30.0
    max_lift: float = 6.0
    open_angle: float = Field(default=70.0, description="Cam degrees; timing overrides this value.")
    close_angle: float = Field(default=70.0, description="Cam degrees; timing overrides this value.")
    dwell_angle: float = 10.0
    phase_deg: float = 0.0
    timing: CamTimingRequest | None = None
    mechanism: Literal["direct", "rocker"] = "direct"
    contact: Literal["flat", "roller"] = "flat"
    drive: Literal["valve", "cam"] = "valve"
    lash: float = 0.0
    ramp_open_deg: float = 0.0
    ramp_close_deg: float = 0.0
    ramp_profile: Literal["smooth", "smooth_c2", "constant_velocity", "constant_acceleration"] | None = None
    roller_radius: float = 0.0
    offset: float = 0.0
    roller_arm: float = 0.0
    roller_angle_deg: float = 0.0
    valve_arm: float = 0.0
    valve_angle_deg: float = 0.0
    valve_axis_deg: float = 90.0
    valve_pad_radius: float = 0.0
    samples_per_degree: float = Field(default=10.0, description="CAD preflight always uses 10 samples/degree.")
    pressure_angle_limit_deg: float = 30.0
    min_curvature_radius: float = 1.0
    nose_radius: float | None = None
    tappet_diameter: float | None = None
    tappet_edge_margin: float = 0.5
    max_acceleration: float | None = None
    max_jerk: float | None = None

    @model_validator(mode="after")
    def _engineering_contract(self) -> "CamMotionRequest":
        normalize_cam_request(self.model_dump(exclude_none=True))
        return self


class CamModuleParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    request: CamMotionRequest = Field(default_factory=CamMotionRequest)
    width: float = Field(default=12.0, gt=0, le=10000, description="Solid width in mm, along negative global X.")
    rotation_deg: float = 0.0
    tolerance: float = Field(default=0.01, gt=0.0001, le=0.1,
                             description="Sampled CAD profile/contact accuracy in mm; not engineering-limit slack.")
