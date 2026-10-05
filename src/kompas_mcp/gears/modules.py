"""Module rows of ГОСТ 9563-60 (СТ СЭВ 310-76).

The rows are informational: a gear with an off-row modulus is still calculated,
but the result records that the value is outside the standard row instead of
silently claiming standard conformity. Row data was verified against the local
research cache of the standard in `experiments/standards/`.
"""
from __future__ import annotations

STANDARD_EDITION = "ГОСТ 9563-60"
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


def _matches(value: float, rows: tuple[float, ...], tolerance: float = 5e-7) -> bool:
    return any(abs(value - row) <= tolerance * max(1.0, abs(row)) for row in rows)


def module_row(value: float) -> int | None:
    """Return 1 or 2 for a standard-row module, otherwise None."""
    if _matches(value, ROW_1):
        return 1
    if _matches(value, ROW_2):
        return 2
    return None


def is_standard_module(value: float) -> bool:
    return module_row(value) is not None or _matches(value, ALLOWED_EXCEPTIONS)


def describe_module(value: float) -> dict[str, float | int | bool | str | None]:
    row = module_row(value)
    allowed_exception = row is None and _matches(value, ALLOWED_EXCEPTIONS)
    if row is not None:
        status = f"row_{row}"
    elif allowed_exception:
        status = "allowed_exception"
    else:
        status = "outside_standard_rows"
    return {
        "standard_edition": STANDARD_EDITION,
        "row": row,
        "allowed_exception": allowed_exception,
        "standard_value": row is not None or allowed_exception,
        "status": status,
    }
