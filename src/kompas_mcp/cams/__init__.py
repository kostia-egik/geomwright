"""Deterministic cam-profile kernel: valve lift, mechanisms, contacts, checks."""

from .analyze import minimum_curvature_radius
from .analyze import pressure_angles_from_directions
from .analyze import self_intersection
from .analyze import summarize
from .contacts import CamProfile
from .contacts import flat_follower_profile
from .contacts import roller_follower_geometry
from .contacts import roller_follower_profile
from .contacts import roller_from_pitch_curve
from .lift import LAW_NAMES
from .lift import MotionCurve
from .lift import build_lift_curve
from .lift import curve_from_points
from .lift import get_law
from .mechanisms import DirectMechanism
from .mechanisms import Mechanism
from .mechanisms import PitchCurve
from .mechanisms import RAMP_PROFILES
from .mechanisms import RockerMechanism
from .mechanisms import apply_clearance
from .mechanisms import build_mechanism
from .motion import PivotingMotion
from .motion import TranslatingMotion
from .preview import preview_cam_profile
from .spec import normalize_cam_request
from .timing import ValveEvent
from .timing import ValveCycle
from .timing import crank_angle
from .timing import event_from_crank
from .timing import valve_cycle

__all__ = [
    "CamProfile",
    "DirectMechanism",
    "LAW_NAMES",
    "Mechanism",
    "MotionCurve",
    "PitchCurve",
    "PivotingMotion",
    "RAMP_PROFILES",
    "RockerMechanism",
    "TranslatingMotion",
    "ValveEvent",
    "ValveCycle",
    "apply_clearance",
    "build_lift_curve",
    "build_mechanism",
    "crank_angle",
    "curve_from_points",
    "event_from_crank",
    "flat_follower_profile",
    "get_law",
    "minimum_curvature_radius",
    "normalize_cam_request",
    "preview_cam_profile",
    "pressure_angles_from_directions",
    "roller_follower_geometry",
    "roller_follower_profile",
    "roller_from_pitch_curve",
    "self_intersection",
    "summarize",
    "valve_cycle",
]
