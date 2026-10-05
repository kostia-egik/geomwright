"""Basic rack standards and modifications for cylindrical involute gears.

The catalog separates the standard from its modification: ГОСТ 13755-2015 is
one system with types A-D from its annex A. The standard supplies the profile
angle, head/clearance coefficients, and the nominal fillet radius; those values
are derived, not free inputs. A user-defined modification carries explicit
coefficients instead.

The standard applies to modules m >= 1 mm per ГОСТ 9563-60; small-module
contours of ГОСТ 9587-81 are not implemented yet and are reported as a warning
instead of being mixed in silently.
"""
from __future__ import annotations

from dataclasses import dataclass

STANDARD_GOST_13755_2015 = "gost_13755_2015"

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

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "label_ru": self.name_ru,
            "label_en": self.name_en,
            "pressure_angle_deg": self.pressure_angle_deg,
            "addendum_coefficient": self.addendum_coefficient,
            "clearance_coefficient": self.clearance_coefficient,
            "root_fillet_coefficient": self.fillet_coefficient,
        }


@dataclass(frozen=True)
class RackStandard:
    value: str
    name_ru: str
    name_en: str
    edition: str
    modifications: tuple[RackModification, ...]

    def modification(self, value: str) -> RackModification | None:
        key = str(value or "").strip().lower()
        return next((item for item in self.modifications if item.value == key), None)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "label_ru": self.name_ru,
            "label_en": self.name_en,
            "edition": self.edition,
            "modifications": [item.to_dict() for item in self.modifications],
        }


GOST_MODIFICATIONS: tuple[RackModification, ...] = (
    RackModification("a", "Тип A", "Type A", 20.0, 1.0, 0.25, 0.38),
    RackModification("b", "Тип B", "Type B", 20.0, 1.0, 0.25, 0.30),
    RackModification("c", "Тип C", "Type C", 20.0, 1.0, 0.25, 0.25),
    RackModification("d", "Тип D", "Type D", 20.0, 1.0, 0.40, 0.39),
    RackModification("custom", "Пользовательский", "Custom", None, None, None, None),
)

STANDARDS: dict[str, RackStandard] = {
    STANDARD_GOST_13755_2015: RackStandard(
        STANDARD_GOST_13755_2015,
        "ГОСТ 13755-2015",
        "ГОСТ 13755-2015",
        STANDARD_EDITION,
        GOST_MODIFICATIONS,
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
    fillet_coefficient: float
    standard_edition: str = STANDARD_EDITION
    conformity_claim: bool = True

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
        )
    if provided:
        raise ValueError(
            "Coefficient overrides are only available for a user-defined modification"
        )
    return BasicRack(
        standard=key,
        modification=variant,
        name_ru=selected.name_ru,
        name_en=selected.name_en,
        pressure_angle_deg=float(selected.pressure_angle_deg),
        addendum_coefficient=float(selected.addendum_coefficient),
        clearance_coefficient=float(selected.clearance_coefficient),
        fillet_coefficient=float(selected.fillet_coefficient),
    )


def standard_options() -> list[dict]:
    """Catalog metadata for the Studio cascading selector."""
    return [system.to_dict() for system in STANDARDS.values()]
