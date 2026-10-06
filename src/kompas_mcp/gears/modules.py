"""Module rows for the supported gear module systems.

Two systems are cached:

* ГОСТ 9563-60 (СТ СЭВ 310-76) rows 1-2 with the recorded industry exceptions;
* ISO 54:1996 series I-II (table 1).

The rows are informational: a gear with an off-row module is still calculated,
but the result records that the value is outside the standard row instead of
silently claiming standard conformity. Row data was verified against the local
research cache for ГОСТ 9563-60 and the public ISO 54:1996 sample in
`experiments/standards/`.
"""
from __future__ import annotations

from .basic_racks import MODULE_SYSTEM_GOST_9563_60, MODULE_SYSTEM_ISO_54_1996

STANDARD_EDITION = "ГОСТ 9563-60"
ISO_54_EDITION = "ISO 54:1996"

ROW_1: tuple[float, ...] = (
    0.05, 0.06, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.8,
    1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0,
    20.0, 25.0, 32.0, 40.0, 50.0, 60.0, 80.0, 100.0,
)
ROW_2: tuple[float, ...] = (
    0.055, 0.07, 0.09, 0.11, 0.14, 0.18, 0.22, 0.28, 0.35, 0.45, 0.55, 0.7,
    0.9, 1.125, 1.375, 1.75, 2.25, 2.75, 3.5, 4.5, 5.5, 7.0, 9.0, 11.0,
    14.0, 18.0, 22.0, 28.0, 36.0, 45.0, 55.0, 70.0, 90.0,
)
# Industry exceptions recorded by the standard (notes 2a/2b and amendment 2).
ALLOWED_EXCEPTIONS: tuple[float, ...] = (3.75, 4.25, 6.5, 1.6, 3.15, 6.3, 12.5)

# ISO 54:1996 table 1. Series I is preferred; 6.5 in series II should be avoided.
ISO_54_ROW_1: tuple[float, ...] = (
    1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0,
    20.0, 25.0, 32.0, 40.0, 50.0,
)
ISO_54_ROW_2: tuple[float, ...] = (
    1.125, 1.375, 1.75, 2.25, 2.75, 3.5, 4.5, 5.5, 6.5, 7.0, 9.0, 11.0,
    14.0, 18.0, 22.0, 28.0, 36.0, 45.0,
)
ISO_54_AVOID: tuple[float, ...] = (6.5,)

MODULE_SYSTEMS: dict[str, dict] = {
    MODULE_SYSTEM_GOST_9563_60: {
        "edition": STANDARD_EDITION,
        "row_1": ROW_1,
        "row_2": ROW_2,
        "exceptions": ALLOWED_EXCEPTIONS,
        "avoid": (),
    },
    MODULE_SYSTEM_ISO_54_1996: {
        "edition": ISO_54_EDITION,
        "row_1": ISO_54_ROW_1,
        "row_2": ISO_54_ROW_2,
        "exceptions": (),
        "avoid": ISO_54_AVOID,
    },
}


def _matches(value: float, rows: tuple[float, ...], tolerance: float = 5e-7) -> bool:
    return any(abs(value - row) <= tolerance * max(1.0, abs(row)) for row in rows)


def module_row(value: float, system: str = MODULE_SYSTEM_GOST_9563_60) -> int | None:
    """Return 1 or 2 for a standard-row module, otherwise None."""
    rows = MODULE_SYSTEMS.get(system) or MODULE_SYSTEMS[MODULE_SYSTEM_GOST_9563_60]
    if _matches(value, rows["row_1"]):
        return 1
    if _matches(value, rows["row_2"]):
        return 2
    return None


def is_standard_module(value: float, system: str = MODULE_SYSTEM_GOST_9563_60) -> bool:
    return module_row(value, system) is not None


def describe_module(
    value: float, system: str = MODULE_SYSTEM_GOST_9563_60
) -> dict[str, float | int | bool | str | None]:
    rows = MODULE_SYSTEMS.get(system) or MODULE_SYSTEMS[MODULE_SYSTEM_GOST_9563_60]
    row = module_row(value, system)
    allowed_exception = row is None and _matches(value, rows["exceptions"])
    avoid = row is not None and _matches(value, rows["avoid"])
    if row is not None:
        status = "row_1_avoid" if avoid and row == 1 else f"row_{row}"
        if avoid and row == 2:
            status = "row_2_avoid"
    elif allowed_exception:
        status = "allowed_exception"
    else:
        status = "outside_standard_rows"
    return {
        "standard_edition": rows["edition"],
        "module_system": system,
        "row": row,
        "allowed_exception": allowed_exception,
        "avoid": avoid,
        "standard_value": row is not None or allowed_exception,
        "status": status,
    }


def module_rows_catalog() -> dict[str, dict]:
    """Serializable module-row catalog for the Studio selector."""
    return {
        key: {
            "edition": rows["edition"],
            "row_1": list(rows["row_1"]),
            "row_2": list(rows["row_2"]),
            "exceptions": list(rows["exceptions"]),
            "avoid": list(rows["avoid"]),
        }
        for key, rows in MODULE_SYSTEMS.items()
    }
