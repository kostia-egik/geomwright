"""Cached standard wire/roller diameters for over-pin gear measurement.

The rows are derived numeric data, not copies of the standards. Sources were
verified in the local research cache / public downloads in
`experiments/standards/`:

* ГОСТ 2475-88 table 3: nominal diameters for measuring involute spline joints
  (the closest gear-relevant row), and annex 2 table 6: the consolidated row of
  measuring wires and rollers for thread measurement;
* ГОСТ 25255-82 table 1: long cylindrical bearing rollers;
* ГОСТ 22696-77 table 1: short cylindrical bearing rollers.

The gear module treats these as *candidate* pin sizes. The automatic choice
picks the candidate nearest the nominal over-pin diameter that still fits below
the tooth tips; an explicit user diameter is never replaced.
"""
from __future__ import annotations

import math

GOST_2475_88_SPLINE_DIAMETERS: tuple[float, ...] = (
    1.0, 1.25, 1.4, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 4.0,
    4.25, 4.5, 5.0, 5.25, 5.5, 6.0, 6.5, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0,
    14.0, 15.0, 16.0, 18.0, 20.0, 22.0, 25.0, 28.0, 30.0,
)

GOST_2475_88_THREAD_DIAMETERS: tuple[float, ...] = (
    0.045, 0.048, 0.052, 0.058, 0.073, 0.088, 0.101, 0.115, 0.130, 0.144,
    0.173, 0.183, 0.202, 0.204, 0.229, 0.231, 0.260, 0.262, 0.289, 0.306,
    0.333, 0.346, 0.367, 0.404, 0.407, 0.433, 0.458, 0.462, 0.511, 0.524,
    0.543, 0.577, 0.596, 0.611, 0.716, 0.722, 0.733, 0.754, 0.776, 0.795,
    0.815, 0.866, 0.895, 0.917, 1.010, 1.023, 1.035, 1.048, 1.086, 1.128,
    1.155, 1.193, 1.222, 1.275, 1.302, 1.333, 1.432, 1.443, 1.467, 1.553,
    1.591, 1.629, 1.732, 1.790, 1.833, 2.021, 2.045, 2.071, 2.095, 2.173,
    2.309, 2.387, 2.444, 2.588, 2.598, 2.716, 2.864, 2.887, 2.933, 3.106,
    3.175, 3.182, 3.259, 3.464, 3.579, 3.623, 3.666, 4.091, 4.141, 4.345,
    4.406, 4.659, 4.773, 4.980, 5.176, 5.207, 5.431, 5.454, 5.727, 6.212,
    6.518, 7.247, 7.603, 8.282, 8.690, 9.317, 9.776, 10.353, 10.950, 11.388,
    11.948, 12.423, 13.133, 14.493, 15.207, 16.565, 17.362, 18.634, 20.152,
    20.706, 21.863, 22.774, 23.896, 24.845, 26.069,
)

GOST_25255_82_LONG_ROLLER_DIAMETERS: tuple[float, ...] = (
    3.0, 4.0, 5.0, 6.0, 6.5, 7.0, 7.5, 8.0, 9.0, 10.0, 12.0, 15.0,
)

GOST_22696_77_SHORT_ROLLER_DIAMETERS: tuple[float, ...] = (
    3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0,
)

_PIN_SOURCES: tuple[dict, ...] = (
    {
        "id": "gost_2475_88_spline",
        "label_ru": "ГОСТ 2475-88, табл. 3 · шлицевые соединения",
        "label_en": "ГОСТ 2475-88, table 3 · involute splines",
        "diameters": GOST_2475_88_SPLINE_DIAMETERS,
    },
    {
        "id": "gost_2475_88_thread",
        "label_ru": "ГОСТ 2475-88, прил. 2 · измерительные проволочки",
        "label_en": "ГОСТ 2475-88, annex 2 · measuring wires",
        "diameters": GOST_2475_88_THREAD_DIAMETERS,
    },
    {
        "id": "gost_25255_82",
        "label_ru": "ГОСТ 25255-82 · длинные ролики",
        "label_en": "ГОСТ 25255-82 · long rollers",
        "diameters": GOST_25255_82_LONG_ROLLER_DIAMETERS,
    },
    {
        "id": "gost_22696_77",
        "label_ru": "ГОСТ 22696-77 · короткие ролики",
        "label_en": "ГОСТ 22696-77 · short rollers",
        "diameters": GOST_22696_77_SHORT_ROLLER_DIAMETERS,
    },
)


def pin_source_catalog() -> list[dict]:
    """Serializable catalog of cached standard pin rows."""
    return [
        {
            "id": source["id"],
            "label_ru": source["label_ru"],
            "label_en": source["label_en"],
            "diameters": list(source["diameters"]),
        }
        for source in _PIN_SOURCES
    ]


def _priority(diameter: float) -> tuple[int, float]:
    for index, source in enumerate(_PIN_SOURCES):
        if any(math.isclose(diameter, value, abs_tol=1e-9) for value in source["diameters"]):
            return index, diameter
    return len(_PIN_SOURCES), diameter


def standard_pin_candidates(
    ideal_mm: float,
    *,
    min_ratio: float = 0.6,
    max_ratio: float = 1.4,
) -> list[dict]:
    """Cached diameters in a practical band around the ideal pin, nearest first."""
    if ideal_mm <= 0.0:
        return []
    low, high = ideal_mm * min_ratio, ideal_mm * max_ratio
    seen: set[float] = set()
    candidates: list[dict] = []
    for source in _PIN_SOURCES:
        for diameter in source["diameters"]:
            if not low <= diameter <= high:
                continue
            key = round(diameter, 6)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "diameter_mm": diameter,
                    "source": source["id"],
                    "label_ru": source["label_ru"],
                    "label_en": source["label_en"],
                    "distance_mm": abs(diameter - ideal_mm),
                }
            )
    candidates.sort(key=lambda item: (item["distance_mm"], _priority(item["diameter_mm"])))
    return candidates


def select_standard_pin(ideal_mm: float, fits) -> dict | None:
    """First cached candidate that fits below the tips, or None."""
    for candidate in standard_pin_candidates(ideal_mm):
        if fits(candidate["diameter_mm"]):
            return candidate
    return None
