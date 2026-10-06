"""Basic rack standards and modifications for cylindrical involute gears.

The catalog separates a standard from its modification. A named modification
supplies the profile angle, head/clearance coefficients, and the nominal fillet
radius; those values are derived, not free inputs. A user-defined modification
carries explicit coefficients instead.

Verified sources (local research cache in `experiments/standards/`):

* ГОСТ 13755-2015 types A-D (existing large-module system);
* ГОСТ 9587-81 small-module contour, annex 2 recommended root shapes;
* ГОСТ Р 50531-93 high-stress contours, table types 1-2;
* ISO 53:1998 standard basic rack profile (table 2) and profiles A-D
  (annex A, informative).

The standard also declares its module system and applicable module range so the
host can flag a gear built outside the contour's declared scope instead of
silently claiming conformity.
"""
from __future__ import annotations

from dataclasses import dataclass

STANDARD_GOST_13755_2015 = "gost_13755_2015"
STANDARD_GOST_9587_81 = "gost_9587_81"
STANDARD_GOST_R_50531_93 = "gost_r_50531_93"
STANDARD_ISO_53_1998 = "iso_53_1998"

MODULE_SYSTEM_GOST_9563_60 = "gost_9563_60"
MODULE_SYSTEM_ISO_54_1996 = "iso_54_1996"

STANDARD_EDITION = "ГОСТ 13755-2015 (ISO 53:1998, MOD)"


@dataclass(frozen=True)
class RackModification:
    value: str
    name_ru: str
    name_en: str
    pressure_angle_deg: float | None
    addendum_coefficient: float | None
    clearance_coefficient: float | None
    fillet_coefficient: float | None
    module_min: float | None = None
    module_max: float | None = None
    module_max_exclusive: bool = False

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "label_ru": self.name_ru,
            "label_en": self.name_en,
            "pressure_angle_deg": self.pressure_angle_deg,
            "addendum_coefficient": self.addendum_coefficient,
            "clearance_coefficient": self.clearance_coefficient,
            "root_fillet_coefficient": self.fillet_coefficient,
            "module_min": self.module_min,
            "module_max": self.module_max,
            "module_max_exclusive": self.module_max_exclusive,
        }


@dataclass(frozen=True)
class RackStandard:
    value: str
    name_ru: str
    name_en: str
    edition: str
    modifications: tuple[RackModification, ...]
    module_system: str
    module_min: float | None
    module_max: float | None
    scope_ru: str
    scope_en: str
    module_max_exclusive: bool = False

    def modification(self, value: str) -> RackModification | None:
        key = str(value or "").strip().lower()
        return next((item for item in self.modifications if item.value == key), None)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "label_ru": self.name_ru,
            "label_en": self.name_en,
            "edition": self.edition,
            "module_system": self.module_system,
            "module_min": self.module_min,
            "module_max": self.module_max,
            "module_max_exclusive": self.module_max_exclusive,
            "scope_ru": self.scope_ru,
            "scope_en": self.scope_en,
            "modifications": [item.to_dict() for item in self.modifications],
        }


GOST_13755_MODIFICATIONS: tuple[RackModification, ...] = (
    RackModification("a", "Тип A", "Type A", 20.0, 1.0, 0.25, 0.38),
    RackModification("b", "Тип B", "Type B", 20.0, 1.0, 0.25, 0.30),
    RackModification("c", "Тип C", "Type C", 20.0, 1.0, 0.25, 0.25),
    RackModification("d", "Тип D", "Type D", 20.0, 1.0, 0.40, 0.39),
    RackModification("custom", "Пользовательский", "Custom", None, None, None, None),
)

# ГОСТ 9587-81, annex 2 (informative): recommended root shapes for the
# small-module contour. The fillet radius is not tabulated for the h_a* = 1.1
# variants; those shapes are defined by the annex figures.
GOST_9587_MODIFICATIONS: tuple[RackModification, ...] = (
    RackModification(
        "h1_c25", "h*ₐ=1,0 · c*=0,25 · ρ_f=0,38m", "h*ₐ=1.0 · c*=0.25 · ρ_f=0.38m",
        20.0, 1.0, 0.25, 0.38,
        module_min=0.1, module_max=1.0, module_max_exclusive=True,
    ),
    RackModification(
        "h1_c30", "h*ₐ=1,0 · c*=0,30 · ρ_f=0,44m", "h*ₐ=1.0 · c*=0.30 · ρ_f=0.44m",
        20.0, 1.0, 0.30, 0.44,
        module_min=0.1, module_max=1.0, module_max_exclusive=True,
    ),
    RackModification(
        "h11_c40", "h*ₐ=1,1 · c*=0,40 (m < 0,5)", "h*ₐ=1.1 · c*=0.40 (m < 0.5)",
        20.0, 1.1, 0.40, None,
        module_min=0.1, module_max=0.5, module_max_exclusive=True,
    ),
    RackModification(
        "h11_c25", "h*ₐ=1,1 · c*=0,25 (0,5 ≤ m < 1)", "h*ₐ=1.1 · c*=0.25 (0.5 ≤ m < 1)",
        20.0, 1.1, 0.25, None,
        module_min=0.5, module_max=1.0, module_max_exclusive=True,
    ),
    RackModification("custom", "Пользовательский", "Custom", None, None, None, None),
)

# ГОСТ Р 50531-93, table on page 2. The two numeric columns are the fillet
# radius and the rounded-space clearance; the identity
# ρ_f = c / (1 - sin α) holds for both types, which fixes the column order.
# h_f* equals h_a* for both types, so the total generating depth is
# h_a* + c* (the host root formula).
GOST_R_50531_MODIFICATIONS: tuple[RackModification, ...] = (
    RackModification("type_1", "Тип 1 · α=25°", "Type 1 · α=25°", 25.0, 1.0, 0.20328, 0.35208),
    RackModification("type_2", "Тип 2 · α=28°", "Type 2 · α=28°", 28.0, 0.9, 0.18438, 0.34754),
    RackModification("custom", "Пользовательский", "Custom", None, None, None, None),
)

# ISO 53:1998 table 2 defines the standard profile (profile A in annex A).
ISO_53_MODIFICATIONS: tuple[RackModification, ...] = (
    RackModification("a", "Тип A · стандартный (табл. 2)", "Type A · standard (table 2)", 20.0, 1.0, 0.25, 0.38),
    RackModification("b", "Тип B", "Type B", 20.0, 1.0, 0.25, 0.30),
    RackModification("c", "Тип C", "Type C", 20.0, 1.0, 0.25, 0.25),
    RackModification("d", "Тип D · полный радиус галтели", "Type D · full-radius fillet", 20.0, 1.0, 0.40, 0.39),
    RackModification("custom", "Пользовательский", "Custom", None, None, None, None),
)

STANDARDS: dict[str, RackStandard] = {
    STANDARD_GOST_13755_2015: RackStandard(
        STANDARD_GOST_13755_2015,
        "ГОСТ 13755-2015",
        "ГОСТ 13755-2015",
        STANDARD_EDITION,
        GOST_13755_MODIFICATIONS,
        MODULE_SYSTEM_GOST_9563_60,
        1.0,
        100.0,
        "Крупномодульные цилиндрические передачи, модуль от 1 мм.",
        "Large-module cylindrical gears, module from 1 mm.",
    ),
    STANDARD_GOST_9587_81: RackStandard(
        STANDARD_GOST_9587_81,
        "ГОСТ 9587-81",
        "ГОСТ 9587-81",
        "ГОСТ 9587-81 (СТ СЭВ 309-85)",
        GOST_9587_MODIFICATIONS,
        MODULE_SYSTEM_GOST_9563_60,
        0.1,
        1.0,
        "Мелкомодульные передачи: модуль от 0,1 до 1 мм исключительно.",
        "Small-module gears: module from 0.1 up to but excluding 1 mm.",
        module_max_exclusive=True,
    ),
    STANDARD_GOST_R_50531_93: RackStandard(
        STANDARD_GOST_R_50531_93,
        "ГОСТ Р 50531-93",
        "ГОСТ Р 50531-93",
        "ГОСТ Р 50531-93",
        GOST_R_50531_MODIFICATIONS,
        MODULE_SYSTEM_GOST_9563_60,
        1.0,
        100.0,
        "Высоконапряжённые передачи, модуль от 1 мм; точность не грубее 7-й степени по ГОСТ 1643.",
        "High-stress gears, module from 1 mm; accuracy not coarser than GOST 1643 grade 7.",
    ),
    STANDARD_ISO_53_1998: RackStandard(
        STANDARD_ISO_53_1998,
        "ISO 53:1998",
        "ISO 53:1998",
        "ISO 53:1998",
        ISO_53_MODIFICATIONS,
        MODULE_SYSTEM_ISO_54_1996,
        1.0,
        50.0,
        "Цилиндрические передачи общего и тяжёлого машиностроения; модули по ISO 54:1996.",
        "Cylindrical gears for general and heavy engineering; ISO 54:1996 modules.",
    ),
}


@dataclass(frozen=True)
class BasicRack:
    standard: str
    modification: str
    name_ru: str
    name_en: str
    pressure_angle_deg: float
    addendum_coefficient: float
    clearance_coefficient: float
    fillet_coefficient: float | None
    standard_edition: str = STANDARD_EDITION
    conformity_claim: bool = True
    module_system: str = MODULE_SYSTEM_GOST_9563_60
    module_min: float | None = None
    module_max: float | None = None
    module_max_exclusive: bool = False
    scope_ru: str = ""
    scope_en: str = ""

    @property
    def dedendum_coefficient(self) -> float:
        return self.addendum_coefficient + self.clearance_coefficient


def resolve_rack(
    standard: str,
    modification: str,
    *,
    pressure_angle_deg: float | None = None,
    addendum_coefficient: float | None = None,
    clearance_coefficient: float | None = None,
    root_fillet_coefficient: float | None = None,
) -> BasicRack:
    """Resolve one standard modification or a user-defined contour."""
    key = str(standard or "").strip().lower()
    system = STANDARDS.get(key)
    if system is None:
        raise ValueError(f"Unknown basic rack standard: {standard}")
    variant = str(modification or "").strip().lower()
    selected = system.modification(variant)
    if selected is None:
        raise ValueError(f"Unknown {system.name_ru} modification: {modification}")
    overrides = {
        "pressure_angle_deg": pressure_angle_deg,
        "addendum_coefficient": addendum_coefficient,
        "clearance_coefficient": clearance_coefficient,
        "fillet_coefficient": root_fillet_coefficient,
    }
    provided = {name: value for name, value in overrides.items() if value is not None}
    if variant == "custom":
        if len(provided) != 4:
            raise ValueError(
                "A user-defined rack requires pressure angle, addendum, clearance, "
                "and root-fillet coefficients"
            )
        return BasicRack(
            standard=key,
            modification="custom",
            name_ru=selected.name_ru,
            name_en=selected.name_en,
            pressure_angle_deg=float(provided["pressure_angle_deg"]),
            addendum_coefficient=float(provided["addendum_coefficient"]),
            clearance_coefficient=float(provided["clearance_coefficient"]),
            fillet_coefficient=float(provided["fillet_coefficient"]),
            standard_edition="explicit user coefficients",
            conformity_claim=False,
            module_system=system.module_system,
            module_min=system.module_min,
            module_max=system.module_max,
            module_max_exclusive=system.module_max_exclusive,
            scope_ru=system.scope_ru,
            scope_en=system.scope_en,
        )
    if provided:
        raise ValueError(
            "Coefficient overrides are only available for a user-defined modification"
        )
    modification_range = selected.module_min is not None or selected.module_max is not None
    module_min = selected.module_min if selected.module_min is not None else system.module_min
    module_max = selected.module_max if selected.module_max is not None else system.module_max
    module_max_exclusive = (
        selected.module_max_exclusive if modification_range else system.module_max_exclusive
    )
    return BasicRack(
        standard=key,
        modification=variant,
        name_ru=selected.name_ru,
        name_en=selected.name_en,
        pressure_angle_deg=float(selected.pressure_angle_deg),
        addendum_coefficient=float(selected.addendum_coefficient),
        clearance_coefficient=float(selected.clearance_coefficient),
        fillet_coefficient=(
            None if selected.fillet_coefficient is None else float(selected.fillet_coefficient)
        ),
        standard_edition=system.edition,
        module_system=system.module_system,
        module_min=module_min,
        module_max=module_max,
        module_max_exclusive=module_max_exclusive,
        scope_ru=system.scope_ru,
        scope_en=system.scope_en,
    )


def standard_options() -> list[dict]:
    """Catalog metadata for the Studio cascading selector."""
    return [system.to_dict() for system in STANDARDS.values()]
