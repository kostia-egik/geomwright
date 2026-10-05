from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranslatingMotion:
    offset: float = 0.0
    kind: str = "translating"


@dataclass(frozen=True)
class PivotingMotion:
    pivot_x: float
    pivot_y: float
    arm_length: float
    zero_angle_deg: float = 0.0
    kind: str = "pivoting"


FollowerMotion = TranslatingMotion | PivotingMotion


def translating(offset: float = 0.0) -> TranslatingMotion:
    return TranslatingMotion(offset=offset)
