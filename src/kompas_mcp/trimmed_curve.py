from __future__ import annotations

import math
from typing import Any


def normalize_trimmed_curve_offset(value: Any) -> float:
    offset = float(value)
    if not math.isfinite(offset) or offset <= 0.0:
        raise ValueError("trimmed curve offset must be a positive finite number")
    return offset


def normalize_trimmed_curve_params(params: dict[str, Any]) -> dict[str, Any]:
    name = str(params.get("name") or "trimmed_curve").strip() or "trimmed_curve"
    point_name = str(params.get("point_name") or f"{name}_point").strip() or f"{name}_point"
    offset_type = int(params.get("offset_type", 0))
    return {
        "name": name,
        "point_name": point_name,
        "offset": normalize_trimmed_curve_offset(params.get("offset", 0.0)),
        "direction": bool(params.get("direction", True)),
        "sense": bool(params.get("sense", True)),
        "offset_type": offset_type,
    }
