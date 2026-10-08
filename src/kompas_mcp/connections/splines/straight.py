"""Layer 2 owner for straight-sided splines (прямобочные шлицы).

Геометрия, каталог и проверки по ГОСТ 1139-80. Модуль не вызывает COM и не
владеет документом КОМПАС: он возвращает нормализованный preview с точными
сущностями контура (отрезки и дуги), диагностикой и данными для проверки
CAD-плана. Размеры таблиц 1-3 и поля допусков выгружены из официального
издания ГОСТ 1139-80 (июль 2003, Изм. No 1, 2).

Соглашение координат совпадает с шестернями: плоскость YOZ, в пределах
эскиза x - тангенциальное направление, y - радиальное; ``polar(r, a)`` =
``[r*sin(a), r*cos(a)]``. Пазы и зубья строятся с центром на оси +Y.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from .spec import StraightSplineRequest

STANDARD_CODE = "gost_1139_80"
STANDARD_TITLE = "ГОСТ 1139-80"
STANDARD_EDITION = "Июль 2003 г., Изм. № 1, 2"
STANDARD_SOURCE = (
    "ГОСТ 1139-80, таблицы 1-3; полный текст с изменениями № 1, 2 "
    "(официальное переиздание, ИПК Издательство стандартов)"
)

SERIES_ORDER = ("light", "medium", "heavy")
SERIES_META: dict[str, dict[str, Any]] = {
    "light": {"title": "Лёгкая серия", "table": 1, "source": "ГОСТ 1139-80, таблица 1"},
    "medium": {"title": "Средняя серия", "table": 2, "source": "ГОСТ 1139-80, таблица 2"},
    "heavy": {"title": "Тяжёлая серия", "table": 3, "source": "ГОСТ 1139-80, таблица 3"},
}

CENTERING_META: dict[str, dict[str, str]] = {
    "inner_diameter": {
        "title": "По внутреннему диаметру d",
        "short": "d",
        "description": "Центрирующая пара - впадины вала d и вершины зубьев втулки d.",
    },
    "outer_diameter": {
        "title": "По наружному диаметру D",
        "short": "D",
        "description": "Центрирующая пара - вершины зубьев вала D и впадины втулки D.",
    },
    "side_faces": {
        "title": "По боковым сторонам b",
        "short": "b",
        "description": "Центрирующая пара - боковые стороны зубьев вала и пазов втулки.",
    },
}

EXECUTION_META: dict[str, dict[str, str]] = {
    "plain": {
        "title": "Исполнение 3: корень d с галтелью",
        "standard": "ГОСТ 1139-80, исполнение 3",
        "description": "Вал центрируется по d; корень впадины - окружность d, галтель r.",
    },
    "recessed": {
        "title": "Исполнение 2: корень d1 с галтелью",
        "standard": "ГОСТ 1139-80, исполнение 2",
        "description": "Нецентрирующий корень впадины выполнен по d1; галтель r.",
    },
    "grooved": {
        "title": "Исполнение 1: корень d с канавкой d1/a (не строится)",
        "standard": "ГОСТ 1139-80, исполнение 1",
        "description": "Вал обкатки: табличные d1/a сохраняются в отчёте, CAD-форма вне среза.",
    },
}

# (z, d, D, b, d1, a, c, r); a отсутствует в таблице 3.
_CATALOG_ROWS: dict[str, tuple[tuple[float | None, ...], ...]] = {
    "light": (
        (6, 23, 26, 6, 22.1, 3.54, 0.3, 0.2),
        (6, 26, 30, 6, 24.6, 3.85, 0.3, 0.2),
        (6, 28, 32, 7, 26.7, 4.03, 0.3, 0.2),
        (8, 32, 36, 6, 30.4, 2.71, 0.4, 0.3),
        (8, 36, 40, 7, 34.5, 3.46, 0.4, 0.3),
        (8, 42, 46, 8, 40.4, 5.03, 0.4, 0.3),
        (8, 46, 50, 9, 44.6, 5.75, 0.4, 0.3),
        (8, 52, 58, 10, 49.7, 4.89, 0.5, 0.5),
        (8, 56, 62, 10, 53.6, 6.38, 0.5, 0.5),
        (8, 62, 68, 12, 59.8, 7.31, 0.5, 0.5),
        (10, 72, 78, 12, 69.6, 5.45, 0.5, 0.5),
        (10, 82, 88, 12, 79.3, 8.62, 0.5, 0.5),
        (10, 92, 98, 14, 89.4, 10.08, 0.5, 0.5),
        (10, 102, 108, 16, 99.9, 11.49, 0.5, 0.5),
        (10, 112, 120, 18, 108.8, 10.72, 0.5, 0.5),
    ),
    "medium": (
        (6, 11, 14, 3.0, 9.9, None, 0.3, 0.2),
        (6, 13, 16, 3.5, 12.0, None, 0.3, 0.2),
        (6, 16, 20, 4.0, 14.5, None, 0.3, 0.2),
        (6, 18, 22, 5.0, 16.7, None, 0.3, 0.2),
        (6, 21, 25, 5.0, 19.5, 1.95, 0.3, 0.2),
        (6, 23, 28, 6.0, 21.3, 1.34, 0.3, 0.2),
        (6, 26, 32, 6.0, 23.4, 1.65, 0.4, 0.3),
        (6, 28, 34, 7.0, 25.9, 1.70, 0.4, 0.3),
        (8, 32, 38, 6.0, 29.4, None, 0.4, 0.3),
        (8, 36, 42, 7.0, 33.5, 1.02, 0.4, 0.3),
        (8, 42, 48, 8.0, 39.5, 2.57, 0.4, 0.3),
        (8, 46, 54, 9.0, 42.7, None, 0.5, 0.5),
        (8, 52, 60, 10.0, 48.7, 2.44, 0.5, 0.5),
        (8, 56, 65, 10.0, 52.2, 2.50, 0.5, 0.5),
        (8, 62, 72, 12.0, 57.8, 2.40, 0.5, 0.5),
        (10, 72, 82, 12.0, 67.4, None, 0.5, 0.5),
        (10, 82, 92, 12.0, 77.1, 3.00, 0.5, 0.5),
        (10, 92, 102, 14.0, 87.3, 4.50, 0.5, 0.5),
        (10, 102, 112, 16.0, 97.7, 6.30, 0.5, 0.5),
        (10, 112, 125, 18.0, 106.3, 4.40, 0.5, 0.5),
    ),
    "heavy": (
        (10, 16, 20, 2.5, 14.1, None, 0.3, 0.2),
        (10, 18, 23, 3.0, 15.6, None, 0.3, 0.2),
        (10, 21, 26, 3.0, 18.5, None, 0.3, 0.2),
        (10, 23, 29, 4.0, 20.3, None, 0.3, 0.2),
        (10, 26, 32, 4.0, 23.0, None, 0.4, 0.3),
        (10, 28, 35, 4.0, 24.4, None, 0.4, 0.3),
        (10, 32, 40, 5.0, 28.0, None, 0.4, 0.3),
        (10, 36, 45, 5.0, 31.3, None, 0.4, 0.3),
        (10, 42, 52, 6.0, 36.9, None, 0.4, 0.3),
        (10, 46, 56, 7.0, 40.9, None, 0.5, 0.5),
        (16, 52, 60, 5.0, 47.0, None, 0.5, 0.5),
        (16, 56, 65, 5.0, 50.6, None, 0.5, 0.5),
        (16, 62, 72, 6.0, 56.1, None, 0.5, 0.5),
        (16, 72, 82, 7.0, 65.9, None, 0.5, 0.5),
        (20, 82, 92, 6.0, 75.6, None, 0.5, 0.5),
        (20, 92, 102, 7.0, 85.5, None, 0.5, 0.5),
        (20, 102, 115, 8.0, 94.0, None, 0.5, 0.5),
        (20, 112, 125, 9.0, 104.0, None, 0.5, 0.5),
    ),
}


def _designation(tooth_count: int, d: float, D: float) -> str:
    return f"{int(tooth_count)}x{_trim(d)}x{_trim(D)}"


def _trim(value: float) -> str:
    number = float(value)
    if abs(number - round(number)) <= 1e-9:
        return str(int(round(number)))
    return ("%g" % number).replace(".", ",")


def normalize_designation(value: str) -> str:
    """Нормализовать запись вида ``8×36×40``/``8x36x40`` к сравнимому ключу."""
    text = str(value or "").strip().lower().replace("х", "x").replace("×", "x").replace("*", "x")
    parts = [part for part in text.replace(" ", "").split("x") if part]
    if len(parts) != 3:
        return text
    try:
        return "x".join(_trim(float(part.replace(",", "."))) for part in parts)
    except ValueError:
        return text


@dataclass(frozen=True)
class SplineSize:
    """Одна строка таблиц 1-3 ГОСТ 1139-80 или явный нестандартный размер."""

    series: str
    designation: str
    tooth_count: int
    inner_diameter_mm: float
    outer_diameter_mm: float
    tooth_width_mm: float
    relief_diameter_mm: float | None
    relief_width_mm: float | None
    chamfer_mm: float
    fillet_mm: float
    catalog: bool
    source: str
    standard: str = STANDARD_CODE

    def as_dict(self) -> dict[str, Any]:
        return {
            "series": self.series,
            "series_title": SERIES_META[self.series]["title"],
            "designation": self.designation,
            "tooth_count": self.tooth_count,
            "inner_diameter_mm": self.inner_diameter_mm,
            "outer_diameter_mm": self.outer_diameter_mm,
            "tooth_width_mm": self.tooth_width_mm,
            "relief_diameter_mm": self.relief_diameter_mm,
            "relief_width_mm": self.relief_width_mm,
            "chamfer_mm": self.chamfer_mm,
            "fillet_mm": self.fillet_mm,
            "catalog": self.catalog,
            "source": self.source,
            "standard": self.standard,
        }


def iter_catalog_sizes(series: str | None = None) -> Iterable[SplineSize]:
    keys = (str(series).strip().lower(),) if series else SERIES_ORDER
    for key in keys:
        meta = SERIES_META.get(key)
        rows = _CATALOG_ROWS.get(key)
        if meta is None or rows is None:
            raise ValueError(f"Неизвестная серия ГОСТ 1139-80: {series}")
        for z, d, D, b, d1, a, c, r in rows:
            yield SplineSize(
                series=key,
                designation=_designation(int(z), float(d), float(D)),
                tooth_count=int(z),
                inner_diameter_mm=float(d),
                outer_diameter_mm=float(D),
                tooth_width_mm=float(b),
                relief_diameter_mm=None if d1 is None else float(d1),
                relief_width_mm=None if a is None else float(a),
                chamfer_mm=float(c),
                fillet_mm=float(r),
                catalog=True,
                source=meta["source"],
            )


def list_straight_spline_sizes(
    series: str | None = None,
    query: str | None = None,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    """Публичный список типоразмеров ГОСТ 1139-80 for MCP/Studio."""
    normalized_query = normalize_designation(query) if query else ""
    items: list[dict[str, Any]] = []
    for size in iter_catalog_sizes(series):
        if normalized_query and normalized_query not in normalize_designation(size.designation):
            continue
        items.append(size.as_dict())
        if len(items) >= max(1, int(limit)):
            break
    return {
        "ok": True,
        "standard": STANDARD_CODE,
        "standard_title": STANDARD_TITLE,
        "edition": STANDARD_EDITION,
        "series": [
            {
                "value": key,
                "title": SERIES_META[key]["title"],
                "table": SERIES_META[key]["table"],
                "count": len(_CATALOG_ROWS[key]),
            }
            for key in SERIES_ORDER
        ],
        "count": len(items),
        "items": items,
    }


def _match_row(series: str, d: float, D: float) -> tuple[float, ...] | None:
    for row in _CATALOG_ROWS.get(series, ()):
        if abs(float(row[1]) - d) <= 1e-6 and abs(float(row[2]) - D) <= 1e-6:
            return row
    return None


def resolve_spline_size(request: dict[str, Any] | StraightSplineRequest) -> SplineSize:
    """Разрешить обозначение или явные размеры в строку каталога/нестандарт."""
    model = request if isinstance(request, StraightSplineRequest) else StraightSplineRequest.model_validate(request)
    series = str(model.series)
    if model.designation:
        wanted = normalize_designation(model.designation)
        for size in iter_catalog_sizes(series):
            if normalize_designation(size.designation) == wanted:
                return size
        raise ValueError(f"Обозначение {model.designation} не найдено в {SERIES_META[series]['title']}")
    z = int(model.tooth_count or 0)
    d = float(model.inner_diameter_mm or 0.0)
    D = float(model.outer_diameter_mm or 0.0)
    b = float(model.tooth_width_mm or 0.0)
    if not (z > 0 and d > 0 and D > d and b > 0):
        raise ValueError("Явные размеры должны удовлетворять z > 0, D > d > 0, b > 0")
    row = _match_row(series, d, D)
    if row is not None:
        size = next(
            size for size in iter_catalog_sizes(series)
            if size.tooth_count == z and abs(size.tooth_width_mm - b) <= 1e-6
            and abs(size.inner_diameter_mm - d) <= 1e-6 and abs(size.outer_diameter_mm - D) <= 1e-6
        )
        return size
    fillet = model.root_fillet_mm
    chamfer = model.tip_chamfer_mm
    return SplineSize(
        series=series,
        designation=_designation(z, d, D),
        tooth_count=z,
        inner_diameter_mm=d,
        outer_diameter_mm=D,
        tooth_width_mm=b,
        relief_diameter_mm=None,
        relief_width_mm=None,
        chamfer_mm=0.3 if chamfer is None else float(chamfer),
        fillet_mm=0.2 if fillet is None else float(fillet),
        catalog=False,
        source="Нестандартный размер; d1/a не нормированы",
    )


# ---------------------------------------------------------------------------
# Геометрия
# ---------------------------------------------------------------------------


def _polar(radius: float, angle: float) -> list[float]:
    return [radius * math.sin(angle), radius * math.cos(angle)]


def _axis_unit(angle: float) -> list[float]:
    return [math.sin(angle), math.cos(angle)]


def _tangent_unit(angle: float) -> list[float]:
    return [math.cos(angle), -math.sin(angle)]


def _dot(a: list[float], b: list[float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _add(a: list[float], b: list[float]) -> list[float]:
    return [a[0] + b[0], a[1] + b[1]]


def _scale(a: list[float], factor: float) -> list[float]:
    return [a[0] * factor, a[1] * factor]


def _norm(a: list[float]) -> float:
    return math.hypot(a[0], a[1])


def _clockwise(start: list[float], middle: list[float], end: list[float]) -> bool:
    cross = (middle[0] - start[0]) * (end[1] - middle[1]) - (middle[1] - start[1]) * (end[0] - middle[0])
    return cross < 0.0


def _flank_side_point(tooth_angle: float, b_mm: float, radius: float) -> list[float]:
    """Точка на боковой стороне зуба (dot = -b/2) на заданном радиусе."""
    half = 0.5 * b_mm
    squared = radius * radius - half * half
    if squared <= 0.0:
        raise ValueError("Ширина зуба b не помещается на окружности радиуса r")
    along = math.sqrt(squared)
    return _add(_scale(_axis_unit(tooth_angle), along), _scale(_tangent_unit(tooth_angle), -half))


def _shaft_fillet(tooth_angle: float, root_radius: float, b_mm: float, r_mm: float) -> tuple[list[float], list[float], list[float]]:
    """Галтель вала: центр, точка на боковой стороне, точка на корне."""
    tangent = _tangent_unit(tooth_angle)
    normal_offset = -(0.5 * b_mm + r_mm)
    squared = (root_radius + r_mm) ** 2 - normal_offset ** 2
    if squared <= 0.0:
        raise ValueError("Галтель r не помещается между боковой стороной и корнем d")
    center = _add(
        _scale(_axis_unit(tooth_angle), math.sqrt(squared)),
        _scale(tangent, normal_offset),
    )
    root_point = _scale(center, root_radius / (root_radius + r_mm))
    flank_point = _add(center, _scale(tangent, r_mm))
    return center, flank_point, root_point


def _hub_fillet(tooth_angle: float, root_radius: float, b_mm: float, r_mm: float) -> tuple[list[float], list[float], list[float]]:
    """Галтель впадины втулки: центр внутри паза, касание дна D и бока."""
    tangent = _tangent_unit(tooth_angle)
    normal_offset = -(0.5 * b_mm + r_mm)
    squared = (root_radius - r_mm) ** 2 - normal_offset ** 2
    if squared <= 0.0:
        raise ValueError("Галтель r не помещается между боковой стороной и дном D втулки")
    center = _add(
        _scale(_axis_unit(tooth_angle), math.sqrt(squared)),
        _scale(tangent, normal_offset),
    )
    root_point = _scale(center, root_radius / (root_radius - r_mm))
    flank_point = _add(center, _scale(tangent, r_mm))
    return center, flank_point, root_point


def _arc_entity(identifier: str, center: list[float], radius: float, start: list[float], end: list[float], middle: list[float]) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "arc",
        "center": [float(center[0]), float(center[1])],
        "radius": float(radius),
        "start": [float(start[0]), float(start[1])],
        "end": [float(end[0]), float(end[1])],
        "direction": _clockwise(start, middle, end),
        "style": 1,
    }


def _segment_entity(identifier: str, start: list[float], end: list[float]) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "segment",
        "start": [float(start[0]), float(start[1])],
        "end": [float(end[0]), float(end[1])],
        "style": 1,
    }


def _arc_sweep(start: list[float], end: list[float], center: list[float], clockwise: bool) -> float:
    a1 = math.atan2(start[1] - center[1], start[0] - center[0])
    a2 = math.atan2(end[1] - center[1], end[0] - center[0])
    delta = (a2 - a1) % (2.0 * math.pi)
    if clockwise and delta > 1e-12:
        delta -= 2.0 * math.pi
    elif not clockwise and delta < -1e-12:
        delta += 2.0 * math.pi
    return delta


def contour_signed_area(entities: list[dict[str, Any]]) -> float:
    """Точная площадь замкнутого контура из отрезков и дуг (формула Грина)."""
    total = 0.0
    for entity in entities:
        if entity.get("kind") == "segment":
            x1, y1 = entity["start"]
            x2, y2 = entity["end"]
            total += 0.5 * (x1 * y2 - x2 * y1)
        elif entity.get("kind") == "arc":
            x1, y1 = entity["start"]
            x2, y2 = entity["end"]
            cx, cy = entity["center"]
            radius = float(entity["radius"])
            delta = _arc_sweep(entity["start"], entity["end"], entity["center"], bool(entity.get("direction")))
            total += 0.5 * (cx * (y2 - y1) - cy * (x2 - x1) + radius * radius * delta)
        else:
            raise ValueError(f"Контур содержит неизвестную сущность: {entity.get('kind')}")
    return total


def contour_points(entities: list[dict[str, Any]], samples: int = 24, *, close: bool = True) -> list[list[float]]:
    """Дискретизировать контур в полилинию (для превью и проверок)."""
    points: list[list[float]] = []
    for entity in entities:
        if entity.get("kind") == "segment":
            points.append([float(entity["start"][0]), float(entity["start"][1])])
        elif entity.get("kind") == "arc":
            start = entity["start"]
            end = entity["end"]
            center = entity["center"]
            radius = float(entity["radius"])
            clockwise = bool(entity.get("direction"))
            delta = _arc_sweep(start, end, center, clockwise)
            a1 = math.atan2(start[1] - center[1], start[0] - center[0])
            steps = max(2, int(samples))
            for index in range(steps):
                angle = a1 + delta * index / steps
                points.append([center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)])
        else:
            raise ValueError(f"Контур содержит неизвестную сущность: {entity.get('kind')}")
    if close and points:
        points.append(list(points[0]))
    return points


def _chain_is_closed(entities: list[dict[str, Any]], tolerance: float = 1e-7) -> bool:
    for index, entity in enumerate(entities):
        following = entities[(index + 1) % len(entities)]
        if math.dist(entity["end"], following["start"]) > tolerance:
            return False
    return True


def build_shaft_space_entities(tooth_count: int, root_radius: float, outer_radius: float, b_mm: float, r_mm: float) -> list[dict[str, Any]]:
    """Точный контур паза вала между двумя соседними зубьями."""
    step = 2.0 * math.pi / tooth_count
    tooth_angle = 0.5 * step
    center_plus, flank_plus, root_plus = _shaft_fillet(tooth_angle, root_radius, b_mm, r_mm)
    tip_plus = _flank_side_point(tooth_angle, b_mm, outer_radius)
    center_minus = [-center_plus[0], center_plus[1]]
    flank_minus = [-flank_plus[0], flank_plus[1]]
    root_minus = [-root_plus[0], root_plus[1]]
    tip_minus = [-tip_plus[0], tip_plus[1]]
    cap_radius = outer_radius + max(1.0, 0.02 * outer_radius)
    cap_plus = _flank_side_point(tooth_angle, b_mm, cap_radius)
    cap_minus = [-cap_plus[0], cap_plus[1]]
    cap_middle = [0.0, cap_radius]
    root_middle = [0.0, root_radius]
    fillet_plus_clockwise = abs(_arc_sweep(flank_plus, root_plus, center_plus, True)) <= abs(
        _arc_sweep(flank_plus, root_plus, center_plus, False)
    )
    fillet_minus_clockwise = abs(_arc_sweep(root_minus, flank_minus, center_minus, True)) <= abs(
        _arc_sweep(root_minus, flank_minus, center_minus, False)
    )
    entities = [
        _segment_entity("spline_space_flank_right", tip_plus, flank_plus),
        {
            "id": "spline_space_fillet_right",
            "kind": "arc",
            "center": center_plus,
            "radius": float(r_mm),
            "start": flank_plus,
            "end": root_plus,
            "direction": bool(fillet_plus_clockwise),
            "style": 1,
        },
        _arc_entity("spline_space_root", [0.0, 0.0], root_radius, root_plus, root_minus, root_middle),
        {
            "id": "spline_space_fillet_left",
            "kind": "arc",
            "center": center_minus,
            "radius": float(r_mm),
            "start": root_minus,
            "end": flank_minus,
            "direction": bool(fillet_minus_clockwise),
            "style": 1,
        },
        _segment_entity("spline_space_flank_left", flank_minus, tip_minus),
        _segment_entity("spline_space_cap_extension_minus", tip_minus, cap_minus),
        _arc_entity("spline_space_cap", [0.0, 0.0], cap_radius, cap_minus, cap_plus, cap_middle),
        _segment_entity("spline_space_cap_extension_plus", cap_plus, tip_plus),
    ]
    if not _chain_is_closed(entities):
        raise ValueError("Контур паза вала не замкнут")
    return entities


def space_interior_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Сущности от начала паза до конца второй боковой стороны включительно."""
    for index, entity in enumerate(entities):
        if entity.get("id") == "spline_space_flank_left":
            return entities[:index + 1]
    return list(entities)


def build_hub_space_entities(tooth_count: int, bore_radius: float, groove_radius: float, b_mm: float, r_mm: float) -> list[dict[str, Any]]:
    """Точный контур паза втулки, открытого внутрь отверстия d."""
    step = 2.0 * math.pi / tooth_count
    tooth_angle = 0.5 * step
    center_plus, flank_plus, bottom_plus = _hub_fillet(tooth_angle, groove_radius, b_mm, r_mm)
    bore_plus = _flank_side_point(tooth_angle, b_mm, bore_radius)
    center_minus = [-center_plus[0], center_plus[1]]
    flank_minus = [-flank_plus[0], flank_plus[1]]
    bottom_minus = [-bottom_plus[0], bottom_plus[1]]
    bore_minus = [-bore_plus[0], bore_plus[1]]
    bottom_middle = [0.0, groove_radius]
    bore_middle = [0.0, bore_radius]
    fillet_plus_clockwise = abs(_arc_sweep(flank_plus, bottom_plus, center_plus, True)) <= abs(
        _arc_sweep(flank_plus, bottom_plus, center_plus, False)
    )
    fillet_minus_clockwise = abs(_arc_sweep(bottom_minus, flank_minus, center_minus, True)) <= abs(
        _arc_sweep(bottom_minus, flank_minus, center_minus, False)
    )
    entities = [
        _segment_entity("spline_space_flank_right", bore_plus, flank_plus),
        {
            "id": "spline_space_fillet_right",
            "kind": "arc",
            "center": center_plus,
            "radius": float(r_mm),
            "start": flank_plus,
            "end": bottom_plus,
            "direction": bool(fillet_plus_clockwise),
            "style": 1,
        },
        _arc_entity("spline_space_root", [0.0, 0.0], groove_radius, bottom_plus, bottom_minus, bottom_middle),
        {
            "id": "spline_space_fillet_left",
            "kind": "arc",
            "center": center_minus,
            "radius": float(r_mm),
            "start": bottom_minus,
            "end": flank_minus,
            "direction": bool(fillet_minus_clockwise),
            "style": 1,
        },
        _segment_entity("spline_space_flank_left", flank_minus, bore_minus),
        _arc_entity("spline_space_bore", [0.0, 0.0], bore_radius, bore_minus, bore_plus, bore_middle),
    ]
    if not _chain_is_closed(entities):
        raise ValueError("Контур паза втулки не замкнут")
    return entities


def build_period_outline(
    space_entities: list[dict[str, Any]],
    tooth_count: int,
    tip_radius: float,
    b_mm: float,
) -> list[list[float]]:
    """Один период венца: от боковой точки паза до той же точки следующего паза.

    Период начинается на боковой стороне зуба (tip_plus), проходит паз до
    второй боковой стороны и заканчивается дугой вершины следующего зуба в
    точке tip_plus - step. Повторы периода в отрицательном направлении
    угла смыкаются без разрывов.
    """
    if len(space_entities) < 2 or tooth_count < 3:
        return []
    half = math.pi / tooth_count
    delta = math.asin(min(1.0, 0.5 * b_mm / tip_radius))
    angle_plus = half - delta
    interior = contour_points(space_entities[:-1], samples=24, close=False)
    if len(interior) < 2:
        return []
    tip_out = _polar_arc(tip_radius, -angle_plus, angle_plus - 2.0 * half, count=12)
    return [*interior, *tip_out[1:]]


def _polar_arc(radius: float, start_angle: float, end_angle: float, count: int = 24) -> list[list[float]]:
    return [
        _polar(radius, start_angle + (end_angle - start_angle) * index / max(1, count))
        for index in range(count + 1)
    ]


def _shaft_chamfer_volume(tooth_count: int, outer_radius: float, b_mm: float, c_mm: float) -> float:
    """Удалённый объём двух торцевых фасок c x 45 на зубьях вала."""
    if c_mm <= 0.0:
        return 0.0
    steps = 160
    total = 0.0
    half = 0.5 * b_mm
    for index in range(steps):
        radius = outer_radius - c_mm + c_mm * (index + 0.5) / steps
        if radius <= half:
            continue
        half_angle = math.asin(min(1.0, half / radius))
        height = outer_radius - radius
        total += 2.0 * radius * half_angle * height * (c_mm / steps)
    return 2.0 * tooth_count * total


@dataclass
class SplineGeometry:
    size: SplineSize
    body: str
    centering: str
    execution: str
    root_radius_mm: float
    outer_radius_mm: float
    bore_radius_mm: float | None
    hub_outside_radius_mm: float | None
    length_mm: float
    chamfer_mm: float
    fillet_mm: float
    space_entities: list[dict[str, Any]]
    space_area_mm2: float
    section_area_mm2: float
    chamfer_volume_mm3: float
    expected_volume_mm3: float
    period_outline: list[list[float]]
    checks: list[dict[str, Any]]
    measurements: dict[str, Any]
    warnings: list[str]
    warning_items: list[dict[str, Any]]
    errors: list[str]

    @property
    def success(self) -> bool:
        return not self.errors


def _issue(code: str, status: str, message: str, **values: Any) -> dict[str, Any]:
    item = {"code": code, "status": status, "message": message}
    item.update({key: value for key, value in values.items() if value is not None})
    return item


def build_spline_geometry(request: dict[str, Any] | StraightSplineRequest) -> SplineGeometry:
    """Рассчитать точную геометрию вала или втулки и собрать диагностику."""
    model = request if isinstance(request, StraightSplineRequest) else StraightSplineRequest.model_validate(request)
    size = resolve_spline_size(model)
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    warning_items: list[dict[str, Any]] = []
    errors: list[str] = []

    def warn(code: str, message: str, **values: Any) -> None:
        warning_items.append(_issue(code, "warning", message, **values))
        warnings.append(message)

    def fail(code: str, message: str, **values: Any) -> None:
        checks.append(_issue(code, "error", message, **values))
        errors.append(message)

    def ok(code: str, message: str, **values: Any) -> None:
        checks.append(_issue(code, "ok", message, **values))

    fillet = float(model.root_fillet_mm) if model.root_fillet_mm is not None else size.fillet_mm
    chamfer = float(model.tip_chamfer_mm) if model.tip_chamfer_mm is not None else size.chamfer_mm
    if not size.catalog:
        if model.root_fillet_mm is None:
            warn(
                "spline_custom_fillet_default",
                "Нестандартный размер: галтель r=0,2 мм принята как инженерное значение по умолчанию",
                value=0.2,
            )
        if model.tip_chamfer_mm is None and model.include_tip_chamfer:
            warn(
                "spline_custom_chamfer_default",
                "Нестандартный размер: фаска c=0,3 мм принята как инженерное значение по умолчанию",
                value=0.3,
            )
    elif model.root_fillet_mm is not None and fillet > size.fillet_mm + 1e-9:
        fail(
            "spline_fillet_above_table",
            f"Галтель r={fillet} мм превышает табличное ограничение r не более {size.fillet_mm} мм",
            value=fillet,
            limit=size.fillet_mm,
        )
    elif model.tip_chamfer_mm is not None and abs(chamfer - size.chamfer_mm) > 1e-9 and model.include_tip_chamfer:
        warn(
            "spline_chamfer_override",
            f"Фаска c={chamfer} мм отличается от табличной c={size.chamfer_mm} мм",
            value=chamfer,
            table=size.chamfer_mm,
        )

    tooth_count = int(size.tooth_count)
    d = float(size.inner_diameter_mm)
    D = float(size.outer_diameter_mm)
    b = float(size.tooth_width_mm)
    length = float(model.length_mm)
    body = str(model.body)
    centering = str(model.centering)
    step = 2.0 * math.pi / tooth_count

    if b >= d:
        fail(
            "spline_flank_root",
            "Ширина зуба b не помещается на внутреннем диаметре d",
            value=b,
            limit=d,
        )
    if math.asin(min(1.0, b / D)) >= math.pi / tooth_count:
        fail(
            "spline_tooth_overlap",
            "Зубья перекрываются: asin(b/D) не меньше половины углового шага",
            value=math.degrees(math.asin(min(1.0, b / D))),
            limit=math.degrees(math.pi / tooth_count),
        )
    if model.include_tip_chamfer and body == "shaft" and 2.0 * chamfer >= b:
        fail(
            "spline_tip_land",
            "Фаска c исчерпывает вершину зуба: b - 2c должно быть положительным",
            value=b - 2.0 * chamfer,
        )

    if body == "shaft":
        requested = str(model.execution)
        execution = "plain" if requested == "auto" and centering == "inner_diameter" else (
            "recessed" if requested == "auto" else requested
        )
        if execution == "recessed" and size.relief_diameter_mm is None:
            fail(
                "spline_relief_missing",
                "Исполнение 2 требует табличного d1; для нестандартного размера оно недоступно",
            )
        if execution == "recessed" and size.relief_diameter_mm is not None and b >= float(size.relief_diameter_mm):
            fail(
                "spline_flank_relief",
                "Ширина зуба b не помещается на диаметре впадины d1",
                value=b,
                limit=size.relief_diameter_mm,
            )
        root_diameter = (
            float(size.relief_diameter_mm)
            if execution == "recessed" and size.relief_diameter_mm is not None
            else d
        )
        root_radius = 0.5 * root_diameter
        outer_radius = 0.5 * D
        try:
            space_entities = build_shaft_space_entities(tooth_count, root_radius, outer_radius, b, fillet)
        except ValueError as exc:
            space_entities = []
            fail("spline_space_invalid", str(exc))
        interior_entities = space_interior_entities(space_entities) if space_entities else []
        if interior_entities:
            tip_arc = _arc_entity(
                "spline_space_top",
                [0.0, 0.0],
                outer_radius,
                interior_entities[-1]["end"],
                interior_entities[0]["start"],
                [0.0, outer_radius],
            )
            space_area = abs(contour_signed_area([*interior_entities, tip_arc]))
        else:
            space_area = 0.0
        if space_area <= 0.0 and space_entities:
            fail("spline_space_area", "Площадь паза вала не положительна")
        section_area = math.pi * outer_radius ** 2 - tooth_count * space_area
        chamfer_volume = (
            _shaft_chamfer_volume(tooth_count, outer_radius, b, chamfer)
            if model.include_tip_chamfer else 0.0
        )
        expected_volume = section_area * length - chamfer_volume
        hub_outside_radius = None
        bore_radius = None
        interior_source = space_interior_entities(space_entities)
    else:
        execution = str(model.execution)
        if execution not in ("auto", "plain"):
            warn(
                "spline_hub_execution",
                "Для втулки исполнение вала не применяется; номинальный профиль строится по d и D",
            )
        execution = "hub"
        bore_radius = 0.5 * d
        groove_radius = 0.5 * D
        hub_outside = model.hub_outside_diameter_mm
        wall_minimum = max(2.0, 0.12 * D)
        if hub_outside is None:
            hub_outside_radius = 0.5 * D + wall_minimum
            warn(
                "spline_hub_wall_default",
                f"Наружный диаметр втулки не задан: принята рекомендуемая стенка {wall_minimum:.2f} мм",
                value=2.0 * hub_outside_radius,
            )
        else:
            hub_outside_radius = 0.5 * float(hub_outside)
            wall = hub_outside_radius - groove_radius
            if wall < wall_minimum - 1e-9:
                fail(
                    "spline_hub_wall",
                    f"Стенка втулки {wall:.2f} мм меньше рекомендуемой {wall_minimum:.2f} мм",
                    value=wall,
                    limit=wall_minimum,
                )
        try:
            space_entities = build_hub_space_entities(tooth_count, bore_radius, groove_radius, b, fillet)
        except ValueError as exc:
            space_entities = []
            fail("spline_space_invalid", str(exc))
        if D - b <= 4.0 * fillet:
            fail(
                "spline_hub_fillet",
                "Галтель r не помещается между боковой стороной и дном D втулки",
                value=D - b,
                limit=4.0 * fillet,
            )
        space_area = abs(contour_signed_area(space_entities)) if space_entities else 0.0
        if space_area <= 0.0 and space_entities:
            fail("spline_space_area", "Площадь паза втулки не положительна")
        ring_area = math.pi * (hub_outside_radius ** 2 - bore_radius ** 2)
        section_area = ring_area - tooth_count * space_area
        chamfer_volume = 0.0
        expected_volume = section_area * length
        interior_source = space_interior_entities(space_entities)

    if expected_volume <= 0.0:
        fail("spline_volume", "Ожидаемый объём тела не положителен", value=expected_volume)

    period_outline = (
        build_period_outline(
            interior_source,
            tooth_count,
            outer_radius if body == "shaft" else float(bore_radius),
            b,
        )
        if interior_source else []
    )

    tip_land = b - 2.0 * chamfer if body == "shaft" and model.include_tip_chamfer else b
    space_half_angle = math.pi / tooth_count - math.asin(min(1.0, b / D))
    measurements = {
        "tip_land_mm": tip_land,
        "space_width_at_tip_mm": 2.0 * 0.5 * D * math.sin(space_half_angle),
        "root_space_half_angle_deg": math.degrees(space_half_angle),
        "angular_pitch_deg": math.degrees(step),
        "flank_depth_mm": 0.5 * (D - d),
        "section_area_mm2": section_area,
        "space_area_mm2": space_area,
        "expected_volume_mm3": expected_volume,
        "chamfer_volume_mm3": chamfer_volume,
    }

    ok(
        "spline_geometry",
        "Номинальная геометрия построена",
        entity_count=len(space_entities),
    )
    if body == "shaft" and execution == "plain" and centering != "inner_diameter":
        warn(
            "spline_execution_centering",
            "Корень d с галтелью (исполнение 3) при центрировании не по d - нестандартное сочетание",
        )
    if body == "shaft" and size.relief_diameter_mm is not None and size.relief_width_mm is not None:
        checks.append(
            _issue(
                "spline_execution_1_reference",
                "warning",
                "Табличные d1 и a исполнения 1 сохранены в отчёте; форма обкатки в этот срез не входит",
                relief_diameter_mm=size.relief_diameter_mm,
                relief_width_mm=size.relief_width_mm,
            )
        )

    return SplineGeometry(
        size=size,
        body=body,
        centering=centering,
        execution=execution,
        root_radius_mm=root_radius if body == "shaft" else bore_radius,
        outer_radius_mm=outer_radius if body == "shaft" else float(hub_outside_radius),
        bore_radius_mm=bore_radius,
        hub_outside_radius_mm=hub_outside_radius,
        length_mm=length,
        chamfer_mm=chamfer,
        fillet_mm=fillet,
        space_entities=space_entities,
        space_area_mm2=space_area,
        section_area_mm2=section_area,
        chamfer_volume_mm3=chamfer_volume,
        expected_volume_mm3=expected_volume,
        period_outline=period_outline,
        checks=checks,
        measurements=measurements,
        warnings=warnings,
        warning_items=warning_items,
        errors=errors,
    )


def build_straight_spline_preview(request: dict[str, Any] | StraightSplineRequest) -> dict[str, Any]:
    """Нормализованный preview вала/втулки для MCP и Studio."""
    model = request if isinstance(request, StraightSplineRequest) else StraightSplineRequest.model_validate(request)
    from .fits import build_fit_report

    try:
        geometry = build_spline_geometry(model)
    except ValueError as exc:
        return {
            "ok": False,
            "success": False,
            "family": "straight_spline",
            "summary": {},
            "geometry": {},
            "derived": {},
            "measurements": {},
            "report": {"checks": [], "representation": "nominal_analytic"},
            "warnings": [],
            "warning_items": [],
            "errors": [str(exc)],
        }
    summary = geometry.size.as_dict()
    summary.update(
        {
            "body": geometry.body,
            "centering": geometry.centering,
            "centering_title": CENTERING_META[geometry.centering]["title"],
            "execution": geometry.execution,
            "execution_title": EXECUTION_META.get(geometry.execution, {}).get("title", geometry.execution),
            "length_mm": geometry.length_mm,
            "root_diameter_mm": 2.0 * geometry.root_radius_mm if geometry.body == "shaft" else geometry.size.inner_diameter_mm,
            "tip_land_mm": geometry.measurements["tip_land_mm"],
            "hub_outside_diameter_mm": (
                None if geometry.hub_outside_radius_mm is None else 2.0 * geometry.hub_outside_radius_mm
            ),
            "hub_wall_mm": (
                None if geometry.hub_outside_radius_mm is None
                else geometry.hub_outside_radius_mm - 0.5 * geometry.size.outer_diameter_mm
            ),
            "space_area_mm2": geometry.space_area_mm2,
            "section_area_mm2": geometry.section_area_mm2,
            "expected_volume_mm3": geometry.expected_volume_mm3,
            "cad_ready": geometry.success,
        }
    )
    fit_report = build_fit_report(model, geometry.size, geometry.centering)
    summary["fits"] = fit_report["selected"]
    geometry_payload = {
        "coordinate_system": "YOZ sketch; x tangential, y radial; space centered on +Y",
        "space_entities": geometry.space_entities,
        "period_outline": geometry.period_outline,
        "root_radius_mm": geometry.root_radius_mm,
        "outer_radius_mm": geometry.outer_radius_mm,
        "bore_radius_mm": geometry.bore_radius_mm,
        "hub_outside_radius_mm": geometry.hub_outside_radius_mm,
        "relief_diameter_mm": geometry.size.relief_diameter_mm,
        "relief_width_mm": geometry.size.relief_width_mm,
        "chamfer_mm": geometry.chamfer_mm if geometry.body == "shaft" else 0.0,
        "fillet_mm": geometry.fillet_mm,
        "length_mm": geometry.length_mm,
        "tooth_count": geometry.size.tooth_count,
        "body": geometry.body,
    }
    return {
        "ok": geometry.success,
        "success": geometry.success,
        "family": "straight_spline",
        "standard": STANDARD_CODE,
        "standard_title": STANDARD_TITLE,
        "summary": summary,
        "geometry": geometry_payload,
        "derived": {
            "chamfer_volume_mm3": geometry.chamfer_volume_mm3,
            "ring_area_mm2": (
                None if geometry.hub_outside_radius_mm is None
                else math.pi * (geometry.hub_outside_radius_mm ** 2 - (geometry.size.inner_diameter_mm / 2.0) ** 2)
            ),
        },
        "measurements": dict(geometry.measurements),
        "report": {
            "checks": geometry.checks,
            "representation": "nominal_analytic",
            "standard": STANDARD_CODE,
            "edition": STANDARD_EDITION,
            "source": STANDARD_SOURCE,
            "provenance": (
                "Числовые данные таблиц 1-3 выгружены из официального издания ГОСТ 1139-80 "
                "и сверены с полным текстом стандарта; допуски d, D, b - по ГОСТ 25346."
            ),
            "conformity_claim": False,
        },
        "fits": fit_report,
        "warnings": geometry.warnings,
        "warning_items": geometry.warning_items,
        "errors": geometry.errors,
    }


def straight_spline_selection(include_fits: bool = False) -> dict[str, Any]:
    """Studio-селектор: серии, типоразмеры, способы центрирования."""
    from .fits import fits_selection

    selection: dict[str, Any] = {
        "standard": {"code": STANDARD_CODE, "title": STANDARD_TITLE, "edition": STANDARD_EDITION},
        "series": [
            {
                "value": key,
                "title": SERIES_META[key]["title"],
                "table": SERIES_META[key]["table"],
                "sizes": [size.as_dict() for size in iter_catalog_sizes(key)],
            }
            for key in SERIES_ORDER
        ],
        "centering": [
            {"value": key, "title": value["title"], "short": value["short"], "description": value["description"]}
            for key, value in CENTERING_META.items()
        ],
        "executions": [
            {"value": key, "title": value["title"], "standard": value["standard"], "description": value["description"]}
            for key, value in EXECUTION_META.items()
        ],
    }
    if include_fits:
        selection["fits"] = fits_selection()
    return selection
