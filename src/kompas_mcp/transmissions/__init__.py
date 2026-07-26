"""Deterministic mechanical-transmission catalogs and geometry previews."""

from .v_belt import list_v_belt_profiles
from .v_belt import preview_v_belt_groove
from .v_belt import resolve_v_belt_profile

__all__ = [
    "list_v_belt_profiles",
    "preview_v_belt_groove",
    "resolve_v_belt_profile",
]
