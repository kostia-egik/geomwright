"""Basic rack contours for cylindrical involute gears.

Coefficients follow the local research cache of ГОСТ 13755-2015 (table A.1,
contour types A-D). The standard applies to modules m >= 1 mm per ГОСТ 9563-60;
small-module contours of ГОСТ 9587-81 are not implemented yet and are reported
as a warning instead of being mixed in silently.
"""
from __future__ import annotations

from dataclasses import dataclass

STANDARD_SYSTEM_GOST = "gost_13755_2015"
STANDARD_SYSTEM_CUSTOM = "custom"

STANDARD_EDITION = "ГОСТ 13755-2015 (ISO 53:1998, MOD)"


@dataclass(frozen=True)
class BasicRack:
    contour: str
    name_ru: str
    name_en: str
    pressure_angle_deg: float
    addendum_coefficient: float
    clearance_coefficient: float
    fillet_coefficient: float
    standard_system: str = STANDARD_SYSTEM_GOST
    standard_edition: str = STANDARD_EDITION
    conformity_claim: bool = True

    @property
    def dedendum_coefficient(self) -> float:
        return self.addendum_coefficient + self.clearance_coefficient

    def to_dict(self) -> dict[str, float | str | bool]:
        return {
            "contour": self.contour,
            "name_ru": self.name_ru,
            "name_en": self.name_en,
            "pressure_angle_deg": self.pressure_angle_deg,
            "addendum_coefficient": self.addendum_coefficient,
            "clearance_coefficient": self.clearance_coefficient,
            "fillet_coefficient": self.fillet_coefficient,
            "dedendum_coefficient": self.dedendum_coefficient,
            "standard_system": self.standard_system,
            "standard_edition": self.standard_edition,
            "conformity_claim": self.conformity_claim,
        }


GOST_CONTOURS: dict[str, BasicRack] = {
    "gost_a": BasicRack("gost_a", "Тип A", "Type A", 20.0, 1.0, 0.25, 0.38),
    "gost_b": BasicRack("gost_b", "Тип B", "Type B", 20.0, 1.0, 0.25, 0.30),
    "gost_c": BasicRack("gost_c", "Тип C", "Type C", 20.0, 1.0, 0.25, 0.25),
    "gost_d": BasicRack("gost_d", "Тип D", "Type D", 20.0, 1.0, 0.40, 0.39),
}


def resolve_rack(
    contour: str,
    *,
    pressure_angle_deg: float | None = None,
    addendum_coefficient: float | None = None,
    clearance_coefficient: float | None = None,
    fillet_coefficient: float | None = None,
) -> BasicRack:
    """Resolve one named contour, applying explicit coefficient overrides."""
    key = str(contour or "").strip().lower()
    base = GOST_CONTOURS.get(key)
    if base is None:
        if key != "custom":
            raise ValueError(f"Unknown basic rack contour: {contour}")
        base = BasicRack(
            "custom",
            "Пользовательский контур",
            "Custom contour",
            20.0,
            1.0,
            0.25,
            0.38,
            standard_system=STANDARD_SYSTEM_CUSTOM,
            standard_edition="explicit user coefficients",
            conformity_claim=False,
        )
    values = {
        "pressure_angle_deg": pressure_angle_deg,
        "addendum_coefficient": addendum_coefficient,
        "clearance_coefficient": clearance_coefficient,
        "fillet_coefficient": fillet_coefficient,
    }
    applied = {
        field: float(value)
        for field, value in values.items()
        if value is not None
    }
    if not applied:
        return base
    unchanged = all(
        abs(applied.get(field, getattr(base, field)) - getattr(base, field)) <= 1e-9
        for field in applied
    )
    if unchanged:
        return base
    overridden = BasicRack(
        contour=base.contour if base.contour == "custom" else f"{base.contour}_modified",
        name_ru=base.name_ru,
        name_en=base.name_en,
        pressure_angle_deg=float(applied.get("pressure_angle_deg", base.pressure_angle_deg)),
        addendum_coefficient=float(applied.get("addendum_coefficient", base.addendum_coefficient)),
        clearance_coefficient=float(applied.get("clearance_coefficient", base.clearance_coefficient)),
        fillet_coefficient=float(applied.get("fillet_coefficient", base.fillet_coefficient)),
        standard_system=base.standard_system,
        standard_edition=base.standard_edition,
        conformity_claim=False,
    )
    return overridden
