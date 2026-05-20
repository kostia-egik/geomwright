from __future__ import annotations

import re
from typing import Any


_CATALOG = (
    {
        "name": "Сталь 10 ГОСТ 1050-2013",
        "density": 7.856,
        "aliases": ("сталь 10", "steel 10", "сталь10", "steel10"),
    },
    {
        "name": "Сталь 45 ГОСТ 1050-2013",
        "density": 7.85,
        "aliases": ("сталь 45", "steel 45", "сталь45", "steel45"),
    },
)


def _normalize_material_key(value: Any) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_ALIAS_INDEX = {
    _normalize_material_key(alias): {"name": entry["name"], "density": entry["density"]}
    for entry in _CATALOG
    for alias in entry["aliases"]
}


def resolve_material_payload(material: Any, density: Any = None) -> dict[str, Any]:
    text = str(material or "").strip()
    density_value = None
    if density not in (None, ""):
        density_value = float(density)
    if not text:
        return {"material": "", "density": density_value, "catalog_matched": False}

    matched = _ALIAS_INDEX.get(_normalize_material_key(text))
    if matched is None:
        return {"material": text, "density": density_value, "catalog_matched": False}

    return {
        "material": matched["name"],
        "density": density_value if density_value is not None else matched["density"],
        "catalog_matched": True,
    }
