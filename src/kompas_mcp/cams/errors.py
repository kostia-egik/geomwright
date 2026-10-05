from __future__ import annotations


class CamSynthesisError(ValueError):
    """Stable host-side diagnostic shared by bounded synthesis families."""

    def __init__(self, code: str, message: str, **params: float) -> None:
        super().__init__(message)
        self.code = code
        self.params = params


class CurvatureSynthesisError(CamSynthesisError):
    """Compatibility name for direct-flat support-function synthesis errors."""


class CamContactError(CamSynthesisError):
    """An unusable contact candidate, not a solver or programming failure."""
