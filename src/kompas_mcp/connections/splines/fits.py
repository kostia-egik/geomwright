"""Поля допусков и посадки ГОСТ 1139-80 на базе системы ГОСТ 25346 (ISO 286).

Модуль хранит только те числовые зоны, которые перечисляет ГОСТ 1139-80 для
шлицевых соединений, в диапазоне диаметров 3-140 мм. Обозначения пар взяты из
таблиц 4, 5, 5а и приложения 1 ГОСТ 1139-80; числовые предельные отклонения -
из таблиц ГОСТ 25346/ISO 286-2 для этих зон.
"""
from __future__ import annotations

from typing import Any

STANDARD_REFERENCE = "ГОСТ 25346-89 (ISO 286-1/2)"

# Границы интервалов диаметров (свыше, до], мм.
_STEPS: tuple[tuple[float, float], ...] = (
    (3.0, 6.0),
    (6.0, 10.0),
    (10.0, 18.0),
    (18.0, 30.0),
    (30.0, 40.0),
    (40.0, 50.0),
    (50.0, 65.0),
    (65.0, 80.0),
    (80.0, 100.0),
    (100.0, 120.0),
    (120.0, 140.0),
)

_IT: dict[int, tuple[int, ...]] = {
    5: (5, 6, 8, 9, 11, 11, 13, 13, 15, 15, 18),
    6: (8, 9, 11, 13, 16, 16, 19, 19, 22, 22, 25),
    7: (12, 15, 18, 21, 25, 25, 30, 30, 35, 35, 40),
    8: (18, 22, 27, 33, 39, 39, 46, 46, 54, 54, 63),
    9: (30, 36, 43, 52, 62, 62, 74, 74, 87, 87, 100),
    10: (48, 58, 70, 84, 100, 100, 120, 120, 140, 140, 160),
    11: (75, 90, 110, 130, 160, 160, 190, 190, 220, 220, 250),
    12: (120, 150, 180, 210, 250, 250, 300, 300, 350, 350, 400),
}

# Основные отклонения валов: a, d, e, f, g (es) и k, n (ei), мкм.
_SHAFT_DEVIATION: dict[str, tuple[int, ...]] = {
    "a": (-270, -280, -290, -300, -310, -320, -340, -360, -380, -410, -460),
    "d": (-30, -40, -50, -65, -80, -80, -100, -100, -120, -120, -145),
    "e": (-20, -25, -32, -40, -50, -50, -60, -60, -72, -72, -85),
    "f": (-10, -13, -16, -20, -25, -25, -30, -30, -36, -36, -43),
    "g": (-4, -5, -6, -7, -9, -9, -10, -10, -12, -12, -14),
    "k": (1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3),
    "n": (8, 10, 12, 15, 17, 17, 20, 20, 23, 23, 27),
}

# Основные отклонения отверстий: D, F (EI), мкм.
_HOLE_DEVIATION: dict[str, tuple[int, ...]] = {
    "D": (30, 40, 50, 65, 80, 80, 100, 100, 120, 120, 145),
    "F": (10, 13, 16, 20, 25, 25, 30, 30, 36, 36, 43),
}

# Зоны, для которых модуль считает числовые предельные отклонения.
NUMERIC_SHAFT_ZONES: tuple[str, ...] = (
    "a11", "d8", "d9", "d10", "e8", "e9", "f7", "f8", "f9", "g6", "g7",
    "h6", "h7", "h8", "h9", "h10", "js6", "js7", "k7", "n6",
)
NUMERIC_HOLE_ZONES: tuple[str, ...] = (
    "H7", "H8", "H9", "H10", "H11", "H12", "D9", "D10", "F8", "F10",
)

CENTERING_FITS: dict[str, dict[str, Any]] = {
    "inner_diameter": {
        "centering_pairs": ["H8/e8", "H7/f7", "H7/g6", "H7/g7", "H7/h7", "H7/js6", "H7/js7", "H7/n6"],
        "preferred_centering_pairs": ["H7/f7", "H7/g6", "H7/g7", "H7/h7", "H7/js6"],
        "default_centering_pair": "H7/f7",
        "side_pairs": [
            "D9/d9", "D9/e8", "D9/e9", "D9/f7", "D9/f8", "D9/f9", "D9/h8", "D9/h9", "D9/js7", "D9/k7",
            "D10/d9", "D10/e9", "F8/f7", "F8/f8", "F8/h7", "F8/h9", "F8/js7", "F8/k7",
            "F10/d9", "F10/e8", "F10/e9", "F10/f7", "F10/f8", "F10/f9", "F10/h7", "F10/h8", "F10/h9",
            "F10/js7", "F10/k7", "H8/h7", "H8/h8", "H8/js7", "H9/d10", "H9/f9", "H9/h7", "H9/h8",
            "H9/h10", "H11/d10", "H11/f9", "H11/h7", "H11/h8", "H11/h10",
        ],
        "preferred_side_pairs": [
            "D9/e9", "D9/f9", "D9/js7", "D9/k7", "F10/e9", "F10/f9", "F10/js7", "F8/h7", "F8/js7",
            "F8/k7", "H9/d10", "H9/f9", "H9/h7", "H9/h8", "H9/h10", "H11/d10", "H11/f9", "H11/h7",
            "H11/h8", "H11/h10",
        ],
        "default_side_pair": "H9/f9",
        "non_centering": {
            "element": "D",
            "title": "Нецентрирующий наружный диаметр D втулки",
            "default_pair": "H12/a11",
            "options": ["H12/a11", "H12/d10", "H12/f9", "H10/a11", "H10/f9", "H11/a11", "H11/f9"],
            "preferred": ["H12/a11", "H10/a11"],
        },
    },
    "outer_diameter": {
        "centering_pairs": ["H8/d8", "H8/e8", "H8/h7", "H10/d8", "H10/e8", "H7/f7", "H7/g6", "H7/h7", "H7/js6", "H7/n6"],
        "preferred_centering_pairs": ["H7/f7", "H7/g6", "H7/h7", "H7/js6"],
        "default_centering_pair": "H7/h7",
        "side_pairs": [
            "D9/d9", "D9/e8", "D9/f7", "D9/h8", "D9/h9", "D9/js7",
            "F8/e8", "F8/f7", "F8/f8", "F8/h8", "F8/js7",
            "F10/d9", "F10/e8", "F10/f7", "F10/f8", "F10/h9",
        ],
        "preferred_side_pairs": ["D9/d9", "F8/f7", "F8/f8", "F8/js7", "F10/f7", "F10/f8", "F10/h9"],
        "default_side_pair": "F10/h9",
        "non_centering": {
            "element": "d",
            "title": "Нецентрирующий внутренний диаметр d втулки",
            "default_pair": "H11",
            "options": ["H11"],
            "preferred": ["H11"],
        },
    },
    "side_faces": {
        "centering_pairs": [
            "D9/d9", "D9/e8", "D9/f8", "D9/f9", "D9/h8", "D9/h9", "D9/js7", "D9/k7",
            "F8/e8", "F8/f8", "F8/js7",
            "F10/d9", "F10/e8", "F10/f8", "F10/f9", "F10/h8", "F10/h9", "F10/js7", "F10/k7",
        ],
        "preferred_centering_pairs": ["D9/e8", "D9/f8", "F8/js7", "F10/d9", "F10/f8"],
        "default_centering_pair": "D9/f8",
        "side_pairs": [],
        "preferred_side_pairs": [],
        "default_side_pair": None,
        "non_centering": {
            "element": "D",
            "title": "Нецентрирующие диаметры d и D",
            "default_pair": "H12/a11",
            "options": ["H12/a11", "H12/d10", "H12/f9", "H10/a11", "H10/f9", "H11"],
            "preferred": ["H12/a11", "H10/a11", "H11"],
        },
    },
}


def _step_index(nominal_mm: float) -> int | None:
    value = float(nominal_mm)
    for index, (low, high) in enumerate(_STEPS):
        if low < value <= high:
            return index
    return None


def _split_zone(zone: str) -> tuple[str, int, bool]:
    text = str(zone or "").strip()
    lowered = text.lower()
    if lowered.startswith("js"):
        letter, digits = "js", text[2:]
    else:
        letter, digits = text[:1], text[1:]
    if not letter or not digits:
        raise ValueError(f"Некорректная запись поля допуска: {zone!r}")
    try:
        grade = int(digits)
    except ValueError as exc:
        raise ValueError(f"Некорректная запись поля допуска: {zone!r}") from exc
    is_hole = letter.isupper()
    return letter, grade, is_hole


def deviation_limits(zone: str, nominal_mm: float) -> dict[str, Any]:
    """Предельные отклонения одной зоны в мкм для диаметра до 140 мм."""
    letter, grade, is_hole = _split_zone(zone)
    index = _step_index(nominal_mm)
    if index is None:
        raise ValueError("Числовые отклонения рассчитаны для размеров свыше 3 до 140 мм")
    if grade not in _IT:
        raise ValueError(f"Квалитет IT{grade} вне числовой таблицы этого модуля")
    tolerance = _IT[grade][index]
    if letter == "H" and is_hole:
        lower, upper = 0, tolerance
    elif letter == "D" or letter == "F":
        if not is_hole:
            raise ValueError("Строчная d/f - вал; для отверстия используйте D/F")
        lower = _HOLE_DEVIATION[letter][index]
        upper = lower + tolerance
    elif letter in ("a", "d", "e", "f", "g") and not is_hole:
        upper = _SHAFT_DEVIATION[letter][index]
        lower = upper - tolerance
    elif letter in ("k", "n") and not is_hole:
        lower = _SHAFT_DEVIATION[letter][index]
        upper = lower + tolerance
    elif letter == "h" and not is_hole:
        lower, upper = -tolerance, 0
    elif letter == "js" and not is_hole:
        lower, upper = -tolerance / 2.0, tolerance / 2.0
    else:
        raise ValueError(f"Зона {zone} вне числовой таблицы этого модуля")
    numeric_zone = f"{letter}{grade}"
    supported = numeric_zone in (NUMERIC_HOLE_ZONES if is_hole else NUMERIC_SHAFT_ZONES)
    if not supported:
        raise ValueError(f"Зона {numeric_zone} не входит в перечень ГОСТ 1139-80 этого среза")
    return {
        "zone": numeric_zone,
        "role": "hole" if is_hole else "shaft",
        "nominal_mm": float(nominal_mm),
        "step_mm": list(_STEPS[index]),
        "grade": grade,
        "tolerance_um": tolerance,
        "lower_um": float(lower),
        "upper_um": float(upper),
        "lower_mm": float(nominal_mm) + float(lower) / 1000.0,
        "upper_mm": float(nominal_mm) + float(upper) / 1000.0,
        "reference": STANDARD_REFERENCE,
    }


def _pair_limits(pair: str, nominal_mm: float) -> dict[str, Any]:
    parts = [part for part in str(pair or "").replace(" ", "").split("/") if part]
    if len(parts) == 2:
        hub_zone, shaft_zone = parts
    elif len(parts) == 1:
        hub_zone, shaft_zone = parts[0], None
    else:
        raise ValueError(f"Некорректная посадка: {pair!r}")
    report: dict[str, Any] = {"pair": str(pair), "nominal_mm": float(nominal_mm), "hub": None, "shaft": None}
    notes: list[str] = []
    report["hub"] = deviation_limits(hub_zone, nominal_mm)
    if shaft_zone:
        report["shaft"] = deviation_limits(shaft_zone, nominal_mm)
        hub_limits = report["hub"]
        shaft_limits = report["shaft"]
        report["clearance_min_um"] = float(hub_limits["lower_um"]) - float(shaft_limits["upper_um"])
        report["clearance_max_um"] = float(hub_limits["upper_um"]) - float(shaft_limits["lower_um"])
        if report["clearance_min_um"] >= 0:
            report["character"] = "зазор"
        elif report["clearance_max_um"] <= 0:
            report["character"] = "натяг"
        else:
            report["character"] = "переходная"
    return report


def _safe_pair(pair: str | None, nominal_mm: float) -> dict[str, Any] | None:
    if not pair:
        return None
    try:
        return _pair_limits(pair, nominal_mm)
    except ValueError as exc:
        return {"pair": str(pair), "nominal_mm": float(nominal_mm), "numeric": False, "note": str(exc)}


def build_fit_report(request: Any, size: Any, centering: str) -> dict[str, Any]:
    """Собрать посадки по умолчанию или явные пары пользователя."""
    selection = CENTERING_FITS.get(str(centering))
    if selection is None:
        raise ValueError(f"Неизвестный способ центрирования: {centering}")
    requested_centering = getattr(request, "fit_centering", None)
    requested_side = getattr(request, "fit_side", None)
    centering_pair = str(requested_centering or selection["default_centering_pair"])
    side_pair = None
    if selection["side_pairs"]:
        side_pair = str(requested_side or selection["default_side_pair"])
    warnings: list[str] = []
    if requested_centering and centering_pair not in selection["centering_pairs"]:
        warnings.append(
            f"Посадка {centering_pair} не входит в рекомендуемые ГОСТ 1139-80 для этого вида центрирования"
        )
    if requested_side and side_pair and side_pair not in selection["side_pairs"]:
        warnings.append(f"Посадка {side_pair} не входит в рекомендуемые ГОСТ 1139-80 по боковым сторонам")

    centering_nominal = {
        "inner_diameter": float(size.inner_diameter_mm),
        "outer_diameter": float(size.outer_diameter_mm),
        "side_faces": float(size.tooth_width_mm),
    }[centering]
    selected = {
        "centering_kind": centering,
        "centering": _safe_pair(centering_pair, centering_nominal),
        "centering_preferred": centering_pair in selection["preferred_centering_pairs"],
        "side": _safe_pair(side_pair, float(size.tooth_width_mm)) if side_pair else None,
        "side_preferred": bool(side_pair and side_pair in selection["preferred_side_pairs"]),
        "non_centering": _safe_pair(
            selection["non_centering"]["default_pair"],
            float(size.outer_diameter_mm) if selection["non_centering"]["element"] == "D" else float(size.inner_diameter_mm),
        ),
        "non_centering_element": selection["non_centering"]["element"],
        "non_centering_title": selection["non_centering"]["title"],
        "warnings": warnings,
    }
    return {
        "centering": centering,
        "selected": selected,
        "options": {
            "centering_pairs": list(selection["centering_pairs"]),
            "preferred_centering_pairs": list(selection["preferred_centering_pairs"]),
            "side_pairs": list(selection["side_pairs"]),
            "preferred_side_pairs": list(selection["preferred_side_pairs"]),
            "non_centering": dict(selection["non_centering"]),
        },
        "reference": STANDARD_REFERENCE,
        "warnings": warnings,
    }


def fits_selection() -> dict[str, Any]:
    """Данные посадок для Studio-селектора."""
    return {
        "reference": STANDARD_REFERENCE,
        "centering": {key: {k: v for k, v in value.items()} for key, value in CENTERING_FITS.items()},
        "numeric_shaft_zones": list(NUMERIC_SHAFT_ZONES),
        "numeric_hole_zones": list(NUMERIC_HOLE_ZONES),
        "diameter_range_mm": [3.0, 140.0],
    }
