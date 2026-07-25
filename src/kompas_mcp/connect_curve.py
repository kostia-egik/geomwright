from __future__ import annotations

import math
from typing import Any


CONNECT_TYPE_VALUES = {
    "position": 0,
    "tangent": 1,
    "normal": 2,
    "smooth": 3,
}


def normalize_connect_curve_type(value: Any) -> int:
    if isinstance(value, str):
        key = value.strip().lower()
        if key not in CONNECT_TYPE_VALUES:
            raise ValueError(f"unsupported connect curve type: {value}")
        return CONNECT_TYPE_VALUES[key]
    connect_type = int(value)
    if connect_type not in CONNECT_TYPE_VALUES.values():
        raise ValueError(f"unsupported connect curve type: {value}")
    return connect_type


def normalize_connect_curve_params(params: dict[str, Any]) -> dict[str, Any]:
    name = str(params.get("name") or "connect_curve").strip() or "connect_curve"
    curve1_connect_type = normalize_connect_curve_type(params.get("curve1_connect_type", "smooth"))
    curve2_connect_type = normalize_connect_curve_type(params.get("curve2_connect_type", curve1_connect_type))
    tension = float(params.get("tension", 100.0))
    if not math.isfinite(tension) or tension < 0.0 or tension > 100.0:
        raise ValueError("connect curve tension must be within 0..100")
    return {
        "name": name,
        "curve1_connect_vertex": bool(params.get("curve1_connect_vertex", True)),
        "curve2_connect_vertex": bool(params.get("curve2_connect_vertex", True)),
        "curve1_connect_type": curve1_connect_type,
        "curve2_connect_type": curve2_connect_type,
        "tension": tension,
    }
