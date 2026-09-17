from __future__ import annotations

import math
from typing import Any, Literal

ChainType = Literal["roller", "bush"]
ToothProfileVariant = Literal["offset", "non_offset"]
# Public compatibility alias retained for existing MCP clients.
GostToothProfileVariant = ToothProfileVariant
ChainDesignation = str

_SOURCE = {
    "evidence_level": "reference_catalog",
    "standards": ["ISO 606:2015", "ISO 606:1994 (ГОСТ 13568-97, приложение А)", "ГОСТ 13568-2017", "ГОСТ 21834-87", "ГОСТ 591-69"],
    "catalog_sources": [
        "KOMPAS application catalog: Таблица ГВС 005-2015 (special B-1 rows 081-085)",
    ],
    "profile_scope": "catalog-backed roller and bush sprocket families only",
    "status": "preview_reference",
    "tooth_profile_source": "GOST 591-69, 1986 reprint with amendments 1-3, scope and Table 1",
    "tooth_profile_engagement_ratio_range": {"min": 1.4, "max": 2.0},
    "references": [
        "https://www.iso.org/standard/61232.html",
        "https://files.stroyinf.ru/Index2/1/4294823/4294823321.htm",
        "https://files.stroyinf.ru/Index2/1/4294831/4294831887.htm",
        "https://files.stroyinf.ru/Data2/1/4293733/4293733500.pdf",
        "https://files.stroyinf.ru/Data2/1/4294831/4294831887.pdf",
        "https://mechcodex.com/reference/roller-chain-dimensions-bs-iso",
        "https://mechcodex.com/reference/roller-chain-dimensions-ansi",
    ],
}
_PROFILES: dict[str, dict[str, Any]] = {
    "ISO_05B": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 8.0, "outside_diameter": 5.0, "inner_width": 3.0, "plate_thickness": 0.8},
    "ISO_06B": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 9.525, "outside_diameter": 6.35, "inner_width": 5.72, "plate_thickness": 1.25},
    "ISO_08B": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 12.7, "outside_diameter": 8.51, "inner_width": 7.75, "plate_thickness": 1.6, "row_spacing": 13.92, "plate_height": 11.81, "row_spacing_source": "GOST 13568-97, Annex A, Table A.1 (ISO 606:1994)"},
    "ISO_081": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 12.7, "outside_diameter": 7.75, "inner_width": 3.3, "label": "081", "native_tooth_width": True, "native_simplex_only": True, "kompas_catalog_source": "Таблица ГВС 005-2015", "breaking_load_n": 8000},
    "ISO_082": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 12.7, "outside_diameter": 7.75, "inner_width": 2.38, "label": "082", "native_tooth_width": True, "native_simplex_only": True, "kompas_catalog_source": "Таблица ГВС 005-2015", "breaking_load_n": 10000},
    "ISO_083": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 12.7, "outside_diameter": 7.75, "inner_width": 4.88, "label": "083", "native_tooth_width": True, "native_simplex_only": True, "kompas_catalog_source": "Таблица ГВС 005-2015", "breaking_load_n": 12000},
    "ISO_084": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 12.7, "outside_diameter": 7.75, "inner_width": 4.88, "label": "084", "native_tooth_width": True, "native_simplex_only": True, "kompas_catalog_source": "Таблица ГВС 005-2015", "breaking_load_n": 16000},
    "ISO_085": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 12.7, "outside_diameter": 7.77, "inner_width": 6.38, "label": "085", "native_tooth_width": True, "native_simplex_only": True, "kompas_catalog_source": "Таблица ГВС 005-2015", "breaking_load_n": 8000},
    "ISO_10B": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 15.875, "outside_diameter": 10.16, "inner_width": 9.65, "plate_thickness": 1.6},
    "ISO_12B": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 19.05, "outside_diameter": 12.07, "inner_width": 11.68, "plate_thickness": 1.8},
    "ISO_16B": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 25.4, "outside_diameter": 15.88, "inner_width": 17.02, "plate_thickness": 2.4},
    "ISO_20B": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 31.75, "outside_diameter": 19.05, "inner_width": 19.56, "plate_thickness": 3.2},
    "ISO_24B": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 38.1, "outside_diameter": 25.4, "inner_width": 25.4},
    "ISO_28B": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 44.45, "outside_diameter": 27.94, "inner_width": 30.99},
    "ISO_32B": {"standard": "iso_606", "profile_family": "iso_b", "pitch": 50.8, "outside_diameter": 29.21, "inner_width": 30.99},
    "ISO_25A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 6.35, "outside_diameter": 3.30, "inner_width": 3.18, "chain_type": "bush", "engagement_diameter_kind": "bush"},
    "ISO_35A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 9.525, "outside_diameter": 5.08, "inner_width": 4.78, "chain_type": "bush", "engagement_diameter_kind": "bush"},
    "ISO_08A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 12.7, "outside_diameter": 7.95, "inner_width": 7.85, "row_spacing": 14.38, "plate_height": 12.07, "dimensions_standard": "ISO 606:1994", "dimensions_source": "GOST 13568-97, mandatory Annex A, Table A.1", "diameter_limit": "maximum", "inner_width_limit": "minimum"},
    "ISO_40A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 12.7, "outside_diameter": 7.92, "inner_width": 7.92},
    "ISO_50A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 15.875, "outside_diameter": 10.16, "inner_width": 9.53},
    "ISO_60A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 19.05, "outside_diameter": 11.91, "inner_width": 12.7},
    "ISO_80A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 25.4, "outside_diameter": 15.88, "inner_width": 15.88},
    "ISO_100A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 31.75, "outside_diameter": 19.05, "inner_width": 19.05},
    "ISO_120A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 38.1, "outside_diameter": 22.23, "inner_width": 25.4},
    "ISO_140A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 44.45, "outside_diameter": 25.4, "inner_width": 25.4},
    "ISO_160A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 50.8, "outside_diameter": 28.58, "inner_width": 31.75},
    "ISO_180A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 57.15, "outside_diameter": 35.71, "inner_width": 35.71},
    "ISO_200A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 63.5, "outside_diameter": 39.67, "inner_width": 38.1},
    "ISO_240A": {"standard": "iso_606", "profile_family": "iso_a", "pitch": 76.2, "outside_diameter": 47.63, "inner_width": 47.63},
    "GOST_PR_12_7_18_2": {"standard": "gost_13568_2017", "profile_family": "pr", "tooth_profile_standard": "gost_591", "pitch": 12.7, "outside_diameter": 8.51, "inner_width": 7.75, "plate_thickness": 1.6, "chain_type": "roller", "label": "ПР-12,7-18,2"},
    "GOST_2PV_9_525_20": {"standard": "gost_13568_2017", "profile_family": "pv", "tooth_profile_standard": "gost_591", "pitch": 9.525, "outside_diameter": 6.0, "inner_width": 5.2, "plate_thickness": 1.25, "chain_type": "bush", "nominal_row_count": 2, "label": "2ПВ-9,525-20"},
}

# ISO 606:1994, reproduced in mandatory Annex A, Table A.1 of GOST 13568-97.
# Columns: pitch, maximum roller diameter, minimum inner width, transverse pitch,
# maximum plate height (maximum of inner/outer plate columns). Transverse pitch
# is on the continuation of the SAME Table A.1, not the attachment Table A.2.
# Full dimensional keys prevent confusing old ISO 40A (pitch 63.5) with the
# existing ANSI-derived ISO_40A reference entry (pitch 12.7).
_ISO_1994_DIMENSIONS = {
    "05B": (8.0, 5.0, 3.0, 5.64, 7.11),
    "06B": (9.525, 6.35, 5.72, 10.24, 8.26),
    "08A": (12.7, 7.95, 7.85, 14.38, 12.07),
    "08B": (12.7, 8.51, 7.75, 13.92, 11.81),
    "10A": (15.875, 10.16, 9.40, 18.11, 15.09),
    "10B": (15.875, 10.16, 9.65, 16.59, 14.73),
    "12A": (19.05, 11.91, 12.57, 22.78, 18.08),
    "12B": (19.05, 12.07, 11.68, 19.46, 16.13),
    "16A": (25.4, 15.88, 15.75, 29.29, 24.13),
    "16B": (25.4, 15.88, 17.02, 31.88, 21.08),
    "20A": (31.75, 19.05, 18.90, 35.76, 30.18),
    "20B": (31.75, 19.05, 19.56, 36.45, 26.42),
    "24A": (38.1, 22.23, 25.22, 45.44, 36.20),
    "24B": (38.1, 25.4, 25.4, 48.36, 33.40),
    "28A": (44.45, 25.4, 25.22, 48.87, 42.24),
    "28B": (44.45, 27.94, 30.99, 59.56, 37.08),
    "32A": (50.8, 25.4, 31.55, 58.55, 48.26),
    "32B": (50.8, 29.21, 30.99, 58.55, 42.29),
}
for _series, (_pitch, _roller, _inner, _spacing, _height) in _ISO_1994_DIMENSIONS.items():
    _designation = f"ISO_{_series}"
    if _designation not in _PROFILES:
        _PROFILES[_designation] = {
            "standard": "iso_606", "profile_family": "iso_a" if _series.endswith("A") else "iso_b",
            "pitch": _pitch, "outside_diameter": _roller, "inner_width": _inner,
            "dimensions_standard": "ISO 606:1994", "dimensions_source": "GOST 13568-97, Annex A, Table A.1",
            "diameter_limit": "maximum", "inner_width_limit": "minimum",
        }
    _catalog_profile = _PROFILES[_designation]
    if any(abs(float(_catalog_profile[_field]) - _value) > 1e-9 for _field, _value in (
        ("pitch", _pitch), ("outside_diameter", _roller), ("inner_width", _inner),
    )):
        raise ValueError(f"ISO 606:1994 axial data does not match chain dimensions: {_designation}")
    _catalog_profile.update({
        "row_spacing": _spacing, "plate_height": _height,
        "row_spacing_source": "GOST 13568-97, Annex A, Table A.1 (ISO 606:1994)",
        "plate_height_source": "GOST 13568-97, Annex A, Table A.1, maximum of inner/outer plate heights",
    })

for _designation, _profile in list(_PROFILES.items()):
    if _profile["standard"] == "iso_606":
        _series = _designation.removeprefix("ISO_")
        _base_family = _profile["profile_family"]
        _profile["selection_family"] = f"{_base_family}_1"
        _profile["label"] = str(_profile.get("label") or f"{_series}-1")
        if _profile.get("native_simplex_only"):
            continue
        for _row_count in (2, 3):
            _variant = dict(_profile)
            _variant["selection_family"] = f"{_base_family}_{_row_count}"
            _variant["nominal_row_count"] = _row_count
            _variant["label"] = f"{_series}-{_row_count}"
            _PROFILES[f"{_designation}_{_row_count}"] = _variant

def _add_gost_profiles(family: str, chain_type: ChainType, rows: list[tuple[str, float, float, float, int]]) -> None:
    """Add normative designations with the radial dimensions needed for a sprocket."""
    for label, pitch, roller_diameter, inner_width, row_count in rows:
        designation = {
            "ПР-12,7-18,2": "GOST_PR_12_7_18_2",
            "2ПВ-9,525-20": "GOST_2PV_9_525_20",
        }.get(label, "GOST_" + "_".join(char if char.isascii() and char.isalnum() else str(ord(char)) for char in label))
        label_en = (label.replace("ПРИ", "PRI").replace("ПР", "PR").replace("ПВ", "PV")
                    .replace("НП", "NP").replace("ТП", "TP").replace(",", "."))
        standard = "gost_21834_87" if family in ("np", "tp") else "gost_13568_2017"
        _PROFILES[designation] = {
            "standard": standard, "profile_family": family,
            "selection_family": f"{family}_{row_count}",
            "tooth_profile_standard": "gost_591", "pitch": pitch,
            "outside_diameter": roller_diameter, "inner_width": inner_width,
            "chain_type": chain_type, "nominal_row_count": row_count,
            "label": label, "label_ru": label, "label_en": label_en,
        }


_add_gost_profiles("pr", "roller", [
    ("ПР-8-4,6", 8.0, 5.0, 3.0, 1), ("ПР-9,525-9,1", 9.525, 6.35, 5.72, 1),
    ("ПР-12,7-10-1", 12.7, 7.75, 2.4, 1), ("ПР-12,7-9", 12.7, 7.75, 3.3, 1),
    ("ПР-12,7-18,2-1", 12.7, 8.51, 5.4, 1), ("ПР-12,7-18,2", 12.7, 8.51, 7.75, 1),
    ("ПР-15,875-23-1", 15.875, 10.16, 6.48, 1), ("ПР-15,875-23", 15.875, 10.16, 9.65, 1),
    ("ПР-19,05-31,8", 19.05, 11.91, 12.70, 1), ("ПР-25,4-60", 25.4, 15.88, 15.88, 1),
    ("ПР-31,75-89", 31.75, 19.05, 19.05, 1), ("ПР-38,1-127", 38.1, 22.23, 25.40, 1),
    ("ПР-44,45-172,4", 44.45, 25.40, 25.40, 1), ("ПР-50,8-227", 50.8, 28.58, 31.75, 1),
    ("ПР-63,5-354", 63.5, 39.68, 38.10, 1),
    ("2ПР-12,7-31,8", 12.7, 8.51, 7.75, 2), ("2ПР-15,875-45,4", 15.875, 10.16, 9.65, 2),
    ("2ПР-19,05-64", 19.05, 11.91, 12.70, 2), ("2ПР-25,4-114", 25.4, 15.88, 15.88, 2),
    ("2ПР-31,75-177", 31.75, 19.05, 19.05, 2), ("2ПР-38,1-254", 38.1, 22.23, 25.40, 2),
    ("2ПР-44,45-344,8", 44.45, 25.40, 25.40, 2), ("2ПР-50,8-453,6", 50.8, 28.58, 31.75, 2),
    ("3ПР-12,7-45,4", 12.7, 8.51, 7.75, 3), ("3ПР-15,875-68,1", 15.875, 10.16, 9.65, 3),
    ("3ПР-19,05-96", 19.05, 11.91, 12.70, 3), ("3ПР-25,4-171", 25.4, 15.88, 15.88, 3),
    ("3ПР-31,75-265,5", 31.75, 19.05, 19.05, 3), ("3ПР-38,1-381", 38.1, 22.23, 25.40, 3),
    ("3ПР-44,45-517,2", 44.45, 25.40, 25.40, 3), ("3ПР-50,8-680,4", 50.8, 28.58, 31.75, 3),
    ("4ПР-19,05-128", 19.05, 11.91, 12.70, 4), ("4ПР-25,4-228", 25.4, 15.88, 15.88, 4),
    ("4ПР-31,75-355", 31.75, 19.05, 19.05, 4), ("4ПР-38,1-508", 38.1, 22.23, 25.40, 4),
    ("4ПР-50,8-900", 50.8, 28.58, 31.75, 4),
])
_add_gost_profiles("pv", "bush", [("ПВ-9,525-11,5", 9.525, 5.0, 7.60, 1), ("ПВ-9,525-13,0", 9.525, 6.0, 9.52, 1), ("2ПВ-9,525-20", 9.525, 6.0, 5.20, 2)])
_add_gost_profiles("pri", "roller", [("ПРИ-78,1-360", 78.1, 33.3, 38.1, 1), ("ПРИ-78,1-400", 78.1, 40.0, 38.1, 1), ("ПРИ-103,2-650", 103.2, 46.0, 49.0, 1), ("ПРИ-140-1200", 140.0, 65.0, 80.0, 1)])
_add_gost_profiles("np", "roller", [
    *( (f"{rows}НП-{pitch:g}".replace(".", ","), pitch, roller, inner, rows)
       for pitch, roller, inner, max_rows in (
           (25.4, 15.88, 15.88, 8), (31.75, 19.05, 19.05, 8),
           (38.1, 22.23, 25.40, 8), (44.45, 25.40, 25.40, 8),
           (50.8, 28.58, 31.75, 6), (57.15, 35.70, 35.72, 4),
           (63.5, 39.68, 39.67, 4),
       ) for rows in (1, 2, 3, 4, 6, 8) if rows <= max_rows),
])
_add_gost_profiles("tp", "roller", [
    *( (f"{rows}ТП-{pitch:g}".replace(".", ","), pitch, roller, inner, rows)
       for pitch, roller, inner, max_rows in (
           (25.4, 15.88, 15.88, 8), (31.75, 19.05, 19.05, 8),
           (38.1, 22.23, 25.40, 8), (44.45, 25.40, 25.40, 8),
           (50.8, 28.58, 31.75, 6), (57.15, 35.70, 35.72, 4),
           (63.5, 39.68, 39.67, 4),
       ) for rows in (1, 2, 3, 4, 6, 8) if rows <= max_rows),
])

# GOST 13568-97 Table 2: (pitch, roller/bush diameter, inner width) -> (A, h).
# Apply only to its PR/PV multi-row families, never infer NP/TP dimensions.
_GOST_13568_AXIAL_DATA = {
    (12.7, 8.51, 7.75): (13.92, 11.80),
    (15.875, 10.16, 9.65): (16.59, 14.80),
    (19.05, 11.91, 12.70): (22.78, 18.08),
    (25.4, 15.88, 15.88): (29.29, 24.20),
    (31.75, 19.05, 19.05): (35.76, 30.20),
    (38.1, 22.23, 25.40): (45.44, 36.20),
    (44.45, 25.40, 25.40): (48.87, 42.24),
    (50.8, 28.58, 31.75): (58.55, 48.30),
    (9.525, 6.0, 5.20): (10.75, 9.85),
}
for _profile in _PROFILES.values():
    if _profile.get("profile_family") not in ("pr", "pv") or int(_profile.get("nominal_row_count", 1)) == 1:
        continue
    _key = tuple(float(_profile[field]) for field in ("pitch", "outside_diameter", "inner_width"))
    if _key in _GOST_13568_AXIAL_DATA:
        _profile["row_spacing"], _profile["plate_height"] = _GOST_13568_AXIAL_DATA[_key]
        _profile["row_spacing_source"] = "GOST 13568-97 Table 2"
        _profile["plate_height_source"] = "GOST 13568-97 Table 2"

_FAMILY_STRATEGIES = {
    "iso_a": {
        "preview_strategy": "kompas_native_gost_591_profile",
        "cad_strategy": "kompas_gost_591_11_entity_tooth_gap",
        "equivalence_group": "iso_606",
    },
    "iso_b": {
        "preview_strategy": "kompas_native_gost_591_profile",
        "cad_strategy": "kompas_gost_591_11_entity_tooth_gap",
        "equivalence_group": "iso_606",
    },
    "pr": {
        "preview_strategy": "kompas_native_gost_591_profile",
        "cad_strategy": "kompas_gost_591_11_entity_tooth_gap",
        "equivalence_group": "gost_13568_2017",
    },
    "pri": {
        "preview_strategy": "kompas_native_gost_591_profile",
        "cad_strategy": "kompas_gost_591_11_entity_tooth_gap",
        "equivalence_group": "gost_13568_2017",
    },
    "pv": {
        "preview_strategy": "kompas_native_gost_591_profile",
        "cad_strategy": "kompas_gost_591_11_entity_tooth_gap",
        "equivalence_group": "gost_13568_2017",
    },
    "np": {
        "preview_strategy": "kompas_native_gost_591_profile",
        "cad_strategy": "kompas_gost_591_11_entity_tooth_gap",
        "equivalence_group": "gost_21834_87",
    },
    "tp": {
        "preview_strategy": "kompas_native_gost_591_profile",
        "cad_strategy": "kompas_gost_591_11_entity_tooth_gap",
        "equivalence_group": "gost_21834_87",
    },
}

_STANDARD_FAMILIES = {
    "iso_606": ("iso_a_1", "iso_a_2", "iso_a_3", "iso_b_1", "iso_b_2", "iso_b_3"),
    "gost_13568": ("pr_1", "pr_2", "pr_3", "pr_4", "pri_1", "pv_1", "pv_2"),
    "gost_21834": ("np_1", "np_2", "np_3", "np_4", "np_6", "np_8", "tp_1", "tp_2", "tp_3", "tp_4", "tp_6", "tp_8"),
}

_FAMILY_LABELS = {
    "iso_a_1": ("A-1", "A-1"), "iso_a_2": ("A-2", "A-2"), "iso_a_3": ("A-3", "A-3"),
    "iso_b_1": ("B-1", "B-1"), "iso_b_2": ("B-2", "B-2"), "iso_b_3": ("B-3", "B-3"),
    "pr_1": ("ПР", "PR"), "pr_2": ("2ПР", "2PR"), "pr_3": ("3ПР", "3PR"), "pr_4": ("4ПР", "4PR"),
    "pri_1": ("ПРИ", "PRI"), "pv_1": ("ПВ", "PV"), "pv_2": ("2ПВ", "2PV"),
    **{f"{family}_{rows}": (f"{rows}{label}", f"{rows}{latin}") for family, label, latin in (("np", "НП", "NP"), ("tp", "ТП", "TP")) for rows in (1, 2, 3, 4, 6, 8)},
}

_STANDARD_LABELS = {
    "iso_606": ("ISO 606", "ISO 606"),
    "gost_13568": ("ГОСТ 13568-2017", "GOST 13568-2017"),
    "gost_21834": ("ГОСТ 21834-87", "GOST 21834-87"),
}


def _family_summaries() -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for family, strategy in _FAMILY_STRATEGIES.items():
        members = [profile for profile in _PROFILES.values() if profile["profile_family"] == family]
        ratios = [float(profile["outside_diameter"]) / float(profile["pitch"]) for profile in members]
        summaries.append({
            "profile_family": family,
            "designation_count": len(members),
            "engagement_diameter_to_pitch": ({"min": min(ratios), "max": max(ratios)} if ratios else None),
            **strategy,
        })
    return summaries


def list_chain_profiles() -> dict[str, Any]:
    return {
        "ok": True,
        "standard": "combined",
        "source": dict(_SOURCE),
        "profiles": [
            {"designation": designation, "chain_type": profile.get("chain_type", "roller"), **profile}
            for designation, profile in _PROFILES.items()
        ],
        "profile_count": len(_PROFILES),
        "profile_families": _family_summaries(),
    }


def chain_profile_selection() -> dict[str, Any]:
    """Return the hierarchical Studio selector for the available catalog."""
    standards: dict[str, dict[str, Any]] = {
        standard: {
            "value": standard,
            "families": {
                family: {
                    "value": family,
                    "label_ru": _FAMILY_LABELS[family][0],
                    "label_en": _FAMILY_LABELS[family][1],
                    "profiles": [],
                    "available": False,
                }
                for family in families
            },
        }
        for standard, families in _STANDARD_FAMILIES.items()
    }
    for designation, profile in _PROFILES.items():
        standard = next(
            value for value, families in _STANDARD_FAMILIES.items()
            if profile["selection_family"] in families
        )
        family = profile["selection_family"]
        standards[standard]["families"][family]["profiles"].append({
            "value": designation,
            "label_ru": profile.get("label_ru", profile.get("label", designation)),
            "label_en": profile.get("label_en", profile.get("label", designation)),
            "pitch": profile["pitch"],
            "chain_type": profile.get("chain_type", "roller"),
            "nominal_row_count": profile.get("nominal_row_count", 1),
        })
        standards[standard]["families"][family]["available"] = True
    return {
        "standards": [
            {
                "value": item["value"],
                "label_ru": _STANDARD_LABELS[item["value"]][0],
                "label_en": _STANDARD_LABELS[item["value"]][1],
                "families": list(item["families"].values()),
                "available": any(family["available"] for family in item["families"].values()),
            }
            for item in standards.values()
        ],
    }


def _profile(designation: str) -> dict[str, Any]:
    try:
        return dict(_PROFILES[designation])
    except KeyError as exc:
        raise ValueError(f"Unknown chain designation: {designation}") from exc


def _polar(radius: float, angle: float) -> list[float]:
    return [radius * math.sin(angle), radius * math.cos(angle)]


def _point_on_circle(center: tuple[float, float], radius: float, angle: float) -> list[float]:
    return [center[0] + radius * math.sin(angle), center[1] + radius * math.cos(angle)]


def _sample_arc(center: tuple[float, float], radius: float, start: float, end: float, count: int = 16) -> list[list[float]]:
    return [_point_on_circle(center, radius, start + (end - start) * index / count) for index in range(count + 1)]


def _circle_angle(center: tuple[float, float], point: list[float] | tuple[float, float]) -> float:
    return math.atan2(float(point[0]) - center[0], float(point[1]) - center[1])


def _profile_arc_entity(
    entity_id: str,
    center: list[float] | tuple[float, float],
    radius: float,
    start: list[float] | tuple[float, float],
    end: list[float] | tuple[float, float],
    *,
    role: str,
) -> dict[str, Any]:
    """Describe the shortest true arc using KOMPAS direction semantics."""
    center_point = (float(center[0]), float(center[1]))
    start_point = (float(start[0]), float(start[1]))
    end_point = (float(end[0]), float(end[1]))
    start_angle = math.atan2(start_point[1] - center_point[1], start_point[0] - center_point[0])
    end_angle = math.atan2(end_point[1] - center_point[1], end_point[0] - center_point[0])
    sweep = (end_angle - start_angle + math.pi) % (2.0 * math.pi) - math.pi
    return {
        "id": entity_id,
        "kind": "arc",
        "role": role,
        "center": list(center_point),
        "radius": float(radius),
        "start": list(start_point),
        "end": list(end_point),
        # KOMPAS ICircleArc.Direction: false=CCW, true=CW.
        "direction": bool(sweep < 0.0),
        "line_style": 1,
    }


def _sample_short_arc(
    center: tuple[float, float],
    radius: float,
    start_point: list[float] | tuple[float, float],
    end_point: list[float] | tuple[float, float],
    *,
    count: int = 16,
) -> list[list[float]]:
    start = _circle_angle(center, start_point)
    end = _circle_angle(center, end_point)
    delta = (end - start + math.pi) % (2.0 * math.pi) - math.pi
    return _sample_arc(center, radius, start, start + delta, count=count)


def _circle_intersections(
    first_center: tuple[float, float],
    first_radius: float,
    second_center: tuple[float, float],
    second_radius: float,
) -> list[list[float]]:
    vx = second_center[0] - first_center[0]
    vy = second_center[1] - first_center[1]
    distance = math.hypot(vx, vy)
    if distance == 0.0 or distance > first_radius + second_radius or distance < abs(first_radius - second_radius):
        return []
    along = (first_radius**2 - second_radius**2 + distance**2) / (2.0 * distance)
    height_squared = max(0.0, first_radius**2 - along**2)
    height = math.sqrt(height_squared)
    base_x = first_center[0] + along * vx / distance
    base_y = first_center[1] + along * vy / distance
    perpendicular_x = -vy / distance
    perpendicular_y = vx / distance
    return [
        [base_x + height * perpendicular_x, base_y + height * perpendicular_y],
        [base_x - height * perpendicular_x, base_y - height * perpendicular_y],
    ]


def _kompas_native_tooth_geometry(
    *,
    pitch: float,
    roller_diameter: float,
    tooth_count: int,
    profile_variant: ToothProfileVariant,
    dimensions_standard: str,
) -> dict[str, Any]:
    """Build the detailed GOST 591 working profile and its technical CAD closure."""
    half_pitch_angle = math.pi / tooth_count
    pitch_diameter = pitch / math.sin(half_pitch_angle)
    pitch_radius = pitch_diameter / 2.0
    engagement_ratio = pitch / roller_diameter
    # GOST 591-69 scope limits lambda to <= 2; Table 1 starts at 1.40.
    # Never extrapolate K (including PRI rows outside this range).
    if not 1.4 <= engagement_ratio <= 2.0:
        raise ValueError(
            f"GOST 591-69 tooth construction requires 1.4 <= lambda = pitch / "
            f"engagement diameter <= 2.0; got {engagement_ratio:.6g} "
            f"({pitch:g} / {roller_diameter:g} mm). "
            "A separate validated tooth-profile method is required; K is not extrapolated."
        )
    # Shared endpoints use the interval starting at that endpoint; 2.0 is included.
    if engagement_ratio >= 1.8:
        outside_coefficient = 0.565
    elif 1.7 <= engagement_ratio < 1.8:
        outside_coefficient = 0.575
    elif 1.6 <= engagement_ratio < 1.7:
        outside_coefficient = 0.555
    elif 1.5 <= engagement_ratio < 1.6:
        outside_coefficient = 0.532
    else:
        outside_coefficient = 0.480
    outside_diameter = pitch * (outside_coefficient + 1.0 / math.tan(half_pitch_angle))
    outside_radius = outside_diameter / 2.0
    closure_radius = outside_radius + 0.01

    alpha = math.radians(55.0 - 60.0 / tooth_count)
    beta = math.radians(18.0 - 56.0 / tooth_count)
    phi = math.radians(17.0 - 64.0 / tooth_count)
    seating_radius = 0.5025 * roller_diameter + 0.05
    root_diameter = pitch_diameter - 2.0 * seating_radius
    root_radius = root_diameter / 2.0
    flank_radius = 0.8 * roller_diameter + seating_radius
    secondary_radius = roller_diameter * (
        1.24 * math.cos(phi) + 0.8 * math.cos(beta) - 1.3025
    ) - 0.05
    fg_distance = roller_diameter * (1.24 * math.sin(phi) - 0.8 * math.sin(beta))

    center_offset = 0.03 * pitch if profile_variant == "offset" else 0.0
    half_offset = center_offset / 2.0
    if half_offset >= seating_radius:
        raise ValueError("tooth-gap center offset must be smaller than the seating radius")
    # Offset the centres transversely without lowering the working branches.
    # Their common lower tangent owns the bottom; preserving the old circle
    # intersection height would introduce an unwanted radial shift of the tooth.
    seating_center_y = pitch_radius
    right_seating_center = (half_offset, seating_center_y)
    left_seating_center = (-half_offset, seating_center_y)
    # Trim the offset seats to their common lower tangent, not their intersection.
    right_bottom = [half_offset, seating_center_y - seating_radius]
    left_bottom = [-half_offset, seating_center_y - seating_radius]
    root = [0.0, seating_center_y - seating_radius]
    seating_contact_normal = (math.sin(alpha), -math.cos(alpha))
    right_contact = [
        right_seating_center[0] + seating_radius * seating_contact_normal[0],
        right_seating_center[1] + seating_radius * seating_contact_normal[1],
    ]
    right_flank_center = (
        right_seating_center[0] - (flank_radius - seating_radius) * seating_contact_normal[0],
        right_seating_center[1] - (flank_radius - seating_radius) * seating_contact_normal[1],
    )
    right_secondary_center = (
        right_seating_center[0] + 1.24 * roller_diameter * math.cos(half_pitch_angle),
        right_seating_center[1] - 1.24 * roller_diameter * math.sin(half_pitch_angle),
    )

    delta_x = right_secondary_center[0] - right_flank_center[0]
    delta_y = right_secondary_center[1] - right_flank_center[1]
    center_distance = math.hypot(delta_x, delta_y)
    radius_sum = flank_radius + secondary_radius
    if center_distance < radius_sum:
        raise ValueError("native KOMPAS flank circles do not admit a common internal tangent")
    unit_x = delta_x / center_distance
    unit_y = delta_y / center_distance
    normal_projection = radius_sum / center_distance
    normal_offset = math.sqrt(max(0.0, 1.0 - normal_projection * normal_projection))
    tangent_candidates: list[tuple[list[float], list[float]]] = []
    for sign in (-1.0, 1.0):
        normal_x = normal_projection * unit_x + sign * normal_offset * -unit_y
        normal_y = normal_projection * unit_y + sign * normal_offset * unit_x
        flank_tangent = [
            right_flank_center[0] + flank_radius * normal_x,
            right_flank_center[1] + flank_radius * normal_y,
        ]
        secondary_tangent = [
            right_secondary_center[0] - secondary_radius * normal_x,
            right_secondary_center[1] - secondary_radius * normal_y,
        ]
        tangent_candidates.append((flank_tangent, secondary_tangent))
    right_flank_tangent, right_secondary_tangent = next(
        pair for pair in tangent_candidates if pair[1][0] > pair[0][0]
    )

    outside_candidates = _circle_intersections(
        right_secondary_center, secondary_radius, (0.0, 0.0), closure_radius
    )
    right_outside_candidates = [point for point in outside_candidates if point[0] >= 0.0]
    if not right_outside_candidates:
        raise ValueError(
            "KOMPAS GOST 591 tooth-head arc does not intersect the outside closure circle"
        )
    right_outside = max(
        right_outside_candidates,
        key=lambda point: point[1],
    )
    closure_line_clearance = 0.5
    closure_line_y = outside_radius + closure_line_clearance
    right_closure = [right_outside[0], closure_line_y]

    right_seating_arc = _sample_short_arc(
        right_seating_center, seating_radius, right_bottom, right_contact, count=18
    )
    right_flank_arc = _sample_short_arc(
        right_flank_center, flank_radius, right_contact, right_flank_tangent, count=18
    )
    right_secondary_arc = _sample_short_arc(
        right_secondary_center, secondary_radius, right_secondary_tangent, right_outside, count=18
    )
    right_branch = [
        *right_seating_arc,
        *right_flank_arc[1:],
        right_secondary_tangent,
        *right_secondary_arc[1:],
    ]
    left_branch = [[-point[0], point[1]] for point in reversed(right_branch)]
    profile_path = [*left_branch, *(right_branch if center_offset > 0.0 else right_branch[1:])]
    left_outside = list(profile_path[0])
    left_closure = [-right_closure[0], right_closure[1]]
    break_path = [
        right_outside,
        right_closure,
        left_closure,
        left_outside,
    ]
    outline = [*profile_path, *break_path[1:]]

    def segment(entity_id: str, start: list[float], end: list[float], role: str) -> dict[str, Any]:
        return {
            "id": entity_id, "kind": "segment", "role": role,
            "start": list(start), "end": list(end), "line_style": 1,
        }

    left_contact = [-right_contact[0], right_contact[1]]
    left_flank_tangent = [-right_flank_tangent[0], right_flank_tangent[1]]
    left_secondary_tangent = [-right_secondary_tangent[0], right_secondary_tangent[1]]
    left_secondary_center = (-right_secondary_center[0], right_secondary_center[1])
    left_flank_center = (-right_flank_center[0], right_flank_center[1])
    cad_entities = [
        _profile_arc_entity("tooth_head_left", left_secondary_center, secondary_radius, left_outside, left_secondary_tangent, role="tooth_head"),
        segment("tooth_tangent_left", left_secondary_tangent, left_flank_tangent, "common_tangent"),
        _profile_arc_entity("tooth_flank_left", left_flank_center, flank_radius, left_flank_tangent, left_contact, role="tooth_flank"),
        _profile_arc_entity("roller_seat_left", left_seating_center, seating_radius, left_contact, left_bottom, role="roller_seat"),
        *([segment("roller_seat_bottom", left_bottom, right_bottom, "roller_seat_bottom")] if center_offset > 0.0 else []),
        _profile_arc_entity("roller_seat_right", right_seating_center, seating_radius, right_bottom, right_contact, role="roller_seat"),
        _profile_arc_entity("tooth_flank_right", right_flank_center, flank_radius, right_contact, right_flank_tangent, role="tooth_flank"),
        segment("tooth_tangent_right", right_flank_tangent, right_secondary_tangent, "common_tangent"),
        _profile_arc_entity("tooth_head_right", right_secondary_center, secondary_radius, right_secondary_tangent, right_outside, role="tooth_head"),
        segment("outside_overshoot_right", right_outside, right_closure, "outside_overshoot"),
        segment("outside_closure", right_closure, left_closure, "outside_closure"),
        segment("outside_overshoot_left", left_closure, left_outside, "outside_overshoot"),
    ]
    return {
        "pitch_diameter": pitch_diameter,
        "outside_diameter": outside_diameter,
        "root_diameter": root_diameter,
        "pitch_radius": pitch_radius,
        "outside_radius": outside_radius,
        "root_radius": root_radius,
        "seating_radius": seating_radius,
        "flank_radius": flank_radius,
        "secondary_radius": secondary_radius,
        "center_offset": center_offset,
        "standard_parameters": {
            "standard": f"{dimensions_standard} dimensions / GOST 591-69 tooth construction",
            "construction": f"kompas_native_gost_591_{profile_variant}",
            "engagement_ratio": engagement_ratio,
            "outside_coefficient": outside_coefficient,
            "outside_coefficient_range_clamped": False,
            "seating_radius": seating_radius,
            "flank_radius": flank_radius,
            "secondary_radius": secondary_radius,
            "seating_half_angle_degrees": math.degrees(alpha),
            "beta_degrees": math.degrees(beta),
            "phi_degrees": math.degrees(phi),
            "fg_distance": fg_distance,
            "center_offset": center_offset,
            "closure_offset": closure_line_y - right_outside[1],
            "closure_radial_overshoot": 0.01,
            "closure_line_clearance": closure_line_clearance,
        },
        "profile_path": profile_path,
        "break_path": break_path,
        "outline": outline,
        "cad_entities": cad_entities,
        "fillets": [
            {"kind": "roller_seat", "side": "left", "center": list(left_seating_center), "radius": seating_radius},
            {"kind": "roller_seat", "side": "right", "center": list(right_seating_center), "radius": seating_radius},
            {"kind": "tooth_flank", "side": "left", "center": list(left_flank_center), "radius": flank_radius},
            {"kind": "tooth_flank", "side": "right", "center": list(right_flank_center), "radius": flank_radius},
            {"kind": "secondary_flank", "side": "left", "center": list(left_secondary_center), "radius": secondary_radius},
            {"kind": "secondary_flank", "side": "right", "center": list(right_secondary_center), "radius": secondary_radius},
        ],
        "tangent_points": {
            "root": root,
            "right_seating_to_flank": right_contact,
            "right_flank_to_tip": right_flank_tangent,
            "right_flank_to_secondary": right_secondary_tangent,
            "right_outside": right_outside,
        },
    }


def _chain_tooth_profile_geometry(
    *,
    pitch: float,
    roller_diameter: float,
    tooth_count: int,
    dimensions_standard: str,
    gost_profile_variant: GostToothProfileVariant,
) -> dict[str, Any]:
    """Calculate one KOMPAS-compatible detailed tooth gap."""
    return _kompas_native_tooth_geometry(
        pitch=pitch,
        roller_diameter=roller_diameter,
        tooth_count=tooth_count,
        profile_variant=gost_profile_variant,
        dimensions_standard=dimensions_standard,
    )


def preview_chain_sprocket(
    *,
    designation: ChainDesignation,
    chain_type: ChainType,
    tooth_count: int,
    row_count: int = 1,
    gost_profile_variant: GostToothProfileVariant = "offset",
) -> dict[str, Any]:
    if tooth_count < 6 or tooth_count > 200:
        raise ValueError("tooth_count must be between 6 and 200")
    if chain_type not in ("roller", "bush"):
        raise ValueError("chain_type must be 'roller' or 'bush'")
    if row_count < 1 or row_count > 8:
        raise ValueError("row_count must be between 1 and 8")
    if gost_profile_variant not in ("offset", "non_offset"):
        raise ValueError("gost_profile_variant must be 'offset' or 'non_offset'")
    profile = _profile(designation)
    pitch = profile["pitch"]
    dimensions_standard = {
        "iso_606": "ISO 606",
        "gost_13568_2017": "GOST 13568-2017",
        "gost_21834_87": "GOST 21834-87",
    }[str(profile["standard"])]
    dimensions_standard = str(profile.get("dimensions_standard", dimensions_standard))
    tooth_gap_center_offset = 0.03 * pitch if gost_profile_variant == "offset" else 0.0
    profile_strategy = dict(_FAMILY_STRATEGIES[profile["profile_family"]])
    profile_strategy.update({
        "tooth_profile_variant": gost_profile_variant,
        "gost_profile_variant": gost_profile_variant,
        "tooth_gap_center_offset_mm": tooth_gap_center_offset,
    })
    roller_diameter = float(profile["outside_diameter"])
    tooth_geometry = _chain_tooth_profile_geometry(
        pitch=pitch,
        roller_diameter=roller_diameter,
        tooth_count=tooth_count,
        dimensions_standard=dimensions_standard,
        gost_profile_variant=gost_profile_variant,
    )
    pitch_diameter = tooth_geometry["pitch_diameter"]
    pitch_radius = tooth_geometry["pitch_radius"]
    outside_radius = tooth_geometry["outside_radius"]
    root_radius = tooth_geometry["root_radius"]
    break_path = tooth_geometry["break_path"]
    profile_path = tooth_geometry["profile_path"]
    outline = tooth_geometry["outline"]
    profile_strategy["preview_strategy"] = tooth_geometry["standard_parameters"]["construction"]
    pitch_circle = [
        _polar(pitch_radius, -math.pi / tooth_count + 2.0 * math.pi / tooth_count * index / 64.0)
        for index in range(65)
    ]
    return {
        "success": True,
        "standard": profile["standard"],
        "profile_family": profile["profile_family"],
        "profile_strategy": profile_strategy,
        "tooth_profile_variant": gost_profile_variant,
        "gost_profile_variant": gost_profile_variant,
        "chain_type": chain_type,
        "designation": designation,
        "profile": {"designation": designation, **profile},
        "derived": {
            "pitch_diameter": pitch_diameter,
            "outside_diameter": tooth_geometry["outside_diameter"],
            "root_diameter": tooth_geometry["root_diameter"],
            "tooth_count": tooth_count,
            "row_count": row_count,
            "nominal_row_count": profile.get("nominal_row_count", 1),
            "pitch_angle_degrees": 360.0 / tooth_count,
            "axial_layout": _chain_axial_layout(profile, tooth_count, row_count),
            "roller_seating_radius": tooth_geometry["seating_radius"],
            "tooth_flank_radius": tooth_geometry["flank_radius"],
            "secondary_profile_radius": tooth_geometry["secondary_radius"],
            "tooth_gap_center_offset_mm": tooth_gap_center_offset,
            "standard_parameters": tooth_geometry["standard_parameters"],
        },
        "geometry": {
            "outline": outline,
            "profile_path": profile_path,
            "break_path": break_path,
            "fillets": tooth_geometry["fillets"],
            "tangent_points": tooth_geometry["tangent_points"],
            "outside_circle": break_path,
            "break_radius": outside_radius,
            "pitch_circle": pitch_circle,
            "cad_entities": tooth_geometry.get("cad_entities"),
        },
        "warnings": [
            "Catalog dimensions come from the selected ISO or GOST chain family; the tooth gap uses the KOMPAS-compatible GOST 591 construction, and selecting its variant does not make the dimensional catalogs interchangeable.",
            "Hub, bore, keyway, shaft interface, and downstream manufacturing operations are outside this module.",
            "End-view preview shows the radial tooth profile only; multi-row axial rim geometry is not shown yet.",
        ],
    }


def _chain_tooth_space_entities(tooth_geometry: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert one sampled preview gap into its exact tangent-circle contour."""
    if tooth_geometry.get("cad_entities") is not None:
        return [dict(entity) for entity in tooth_geometry["cad_entities"]]
    fillets = {
        (str(item["kind"]), str(item["side"])): item
        for item in tooth_geometry["fillets"]
    }
    tangent_points = tooth_geometry["tangent_points"]
    root = list(tangent_points["root"])
    right_contact = list(tangent_points["right_seating_to_flank"])
    left_contact = [-right_contact[0], right_contact[1]]
    right_tip = list(tooth_geometry["profile_path"][-1])
    left_tip = list(tooth_geometry["profile_path"][0])

    left_seat = fillets[("roller_seat", "left")]
    right_seat = fillets[("roller_seat", "right")]
    left_flank = fillets[("tooth_flank", "left")]
    right_flank = fillets[("tooth_flank", "right")]
    right_secondary_contact = tangent_points.get("right_flank_to_secondary")
    entities: list[dict[str, Any]] = []

    if right_secondary_contact is not None:
        right_secondary_contact = list(right_secondary_contact)
        left_secondary_contact = [-right_secondary_contact[0], right_secondary_contact[1]]
        left_secondary = fillets[("secondary_flank", "left")]
        entities.append(_profile_arc_entity(
            "tooth_space_secondary_left",
            left_secondary["center"],
            float(left_secondary["radius"]),
            left_tip,
            left_secondary_contact,
            role="secondary_flank",
        ))
        left_flank_start = left_secondary_contact
    else:
        left_flank_start = left_tip

    entities.extend([
        _profile_arc_entity(
            "tooth_space_flank_left",
            left_flank["center"],
            float(left_flank["radius"]),
            left_flank_start,
            left_contact,
            role="tooth_flank",
        ),
        _profile_arc_entity(
            "tooth_space_seat_left",
            left_seat["center"],
            float(left_seat["radius"]),
            left_contact,
            root,
            role="roller_seat",
        ),
        _profile_arc_entity(
            "tooth_space_seat_right",
            right_seat["center"],
            float(right_seat["radius"]),
            root,
            right_contact,
            role="roller_seat",
        ),
    ])

    if right_secondary_contact is not None:
        right_secondary = fillets[("secondary_flank", "right")]
        entities.extend([
            _profile_arc_entity(
                "tooth_space_flank_right",
                right_flank["center"],
                float(right_flank["radius"]),
                right_contact,
                right_secondary_contact,
                role="tooth_flank",
            ),
            _profile_arc_entity(
                "tooth_space_secondary_right",
                right_secondary["center"],
                float(right_secondary["radius"]),
                right_secondary_contact,
                right_tip,
                role="secondary_flank",
            ),
        ])
    else:
        entities.append(_profile_arc_entity(
            "tooth_space_flank_right",
            right_flank["center"],
            float(right_flank["radius"]),
            right_contact,
            right_tip,
            role="tooth_flank",
        ))

    entities.append(_profile_arc_entity(
        "tooth_space_outside_closure",
        (0.0, 0.0),
        float(tooth_geometry["outside_radius"]),
        right_tip,
        left_tip,
        role="outside_closure",
    ))
    return entities


def _chain_variable(
    name: str,
    value: float | int,
    *,
    expression: str | None = None,
    note: str,
    unit: str = "mm",
) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "expression": expression,
        "note": note,
        "unit": unit,
    }


def _build_chain_tooth_parameterization(
    *,
    entities: list[dict[str, Any]],
    pitch: float,
    roller_diameter: float,
    tooth_count: int,
    face_width: float,
    outside_diameter: float,
    root_diameter: float,
    center_offset: float,
) -> dict[str, Any]:
    """Build the visible GOST tooth construction around the accepted contour."""
    by_id = {str(entity["id"]): entity for entity in entities}
    required_ids = {
        "tooth_head_left", "tooth_tangent_left", "tooth_flank_left",
        "roller_seat_left", "roller_seat_right", "tooth_flank_right",
        "tooth_tangent_right", "tooth_head_right", "outside_overshoot_right",
        "outside_closure", "outside_overshoot_left",
    }
    if center_offset > 0.0:
        required_ids.add("roller_seat_bottom")
    if set(by_id) != required_ids:
        raise ValueError("chain tooth parameterization requires the variant-specific closed contour")

    head_left = by_id["tooth_head_left"]
    head_right = by_id["tooth_head_right"]
    flank_left = by_id["tooth_flank_left"]
    flank_right = by_id["tooth_flank_right"]
    seat_left = by_id["roller_seat_left"]
    seat_right = by_id["roller_seat_right"]
    pitch_radius = pitch / (2.0 * math.sin(math.pi / tooth_count))
    outside_radius = outside_diameter / 2.0
    root_radius = root_diameter / 2.0
    seating_radius = float(seat_left["radius"])
    flank_radius = float(flank_left["radius"])
    head_radius = float(head_left["radius"])
    closure_width = abs(
        float(by_id["outside_closure"]["start"][0])
        - float(by_id["outside_closure"]["end"][0])
    )
    closure_shift = float(by_id["outside_overshoot_right"]["end"][1]) - float(
        by_id["outside_overshoot_right"]["start"][1]
    )

    center_specs = [
        ("head", head_left, head_right, "CH_HSPAN", "CH_HY"),
        ("flank", flank_left, flank_right, "CH_FSPAN", "CH_FY"),
    ]
    auxiliary_entities: list[dict[str, Any]] = [
        {
            "id": "chain_pitch_datum",
            "kind": "circle",
            "role": "parameterization_datum",
            "center": [0.0, 0.0],
            "radius": pitch_radius,
            "line_style": 2,
        },
        {
            "id": "chain_outside_datum",
            "kind": "circle",
            "role": "parameterization_datum",
            "center": [0.0, 0.0],
            "radius": outside_radius,
            "line_style": 2,
        },
    ]
    axis_length = max(float(point[1]) for entity in entities for point in (entity.get("start"), entity.get("end")) if point) + 10.0
    auxiliary_entities.append({
        "id": "chain_tooth_axis",
        "kind": "segment",
        "role": "parameterization_datum",
        "start": [0.0, 0.0],
        "end": [0.0, axis_length],
        "line_style": 2,
    })

    for prefix, left_arc, right_arc, _span_variable, _height_variable in center_specs:
        left_center = list(left_arc["center"])
        right_center = list(right_arc["center"])
        auxiliary_entities.append({
            "id": f"chain_{prefix}_center_span",
            "kind": "segment",
            "role": "parameterization_datum",
            "start": left_center,
            "end": right_center,
            "line_style": 2,
        })

    seat_center_y = float(seat_right["center"][1])
    if center_offset > 0.0:
        auxiliary_entities.append({
            "id": "chain_seat_center_span",
            "kind": "segment",
            "role": "parameterization_datum",
            "start": list(seat_right["center"]),
            "end": list(seat_left["center"]),
            "line_style": 2,
        })

    head_span = abs(float(head_right["center"][0]) - float(head_left["center"][0]))
    flank_span = abs(float(flank_right["center"][0]) - float(flank_left["center"][0]))
    variables = [
        _chain_variable("CH_Z", tooth_count, note="Chain sprocket tooth count", unit="unitless"),
        _chain_variable("CH_P", pitch, note="Chain pitch"),
        _chain_variable("CH_DR", roller_diameter, note="Roller or bush engagement diameter"),
        _chain_variable("CH_DA", outside_diameter, note="Sprocket outside diameter"),
        _chain_variable("CH_DF", root_diameter, note="Sprocket root diameter"),
        _chain_variable("CH_B", face_width, note="Functional tooth width"),
        _chain_variable("CH_RP", pitch_radius, expression=f"{pitch_radius / pitch:.15g} * CH_P", note="Pitch radius"),
        _chain_variable("CH_RA", outside_radius, expression="CH_DA / 2", note="Outside radius"),
        _chain_variable("CH_RF", root_radius, expression="CH_DF / 2", note="Root radius"),
        _chain_variable("CH_R", seating_radius, expression="0.5025 * CH_DR + 0.05", note="Roller-seat radius r"),
        _chain_variable("CH_R1", flank_radius, expression="0.8 * CH_DR + CH_R", note="Flank radius r1"),
        _chain_variable("CH_R2", head_radius, expression=f"{(head_radius + 0.05) / roller_diameter:.15g} * CH_DR - 0.05", note="Tooth-head radius r2"),
        _chain_variable("CH_E", center_offset, expression=("0.03 * CH_P" if center_offset > 0.0 else None), note="Roller-seat centre offset e"),
        _chain_variable("CH_SCY", seat_center_y, expression=f"{seat_center_y / pitch:.15g} * CH_P", note="Roller-seat centre height"),
        _chain_variable("CH_FSPAN", flank_span, expression=f"{flank_span / pitch:.15g} * CH_P", note="Flank-centre span"),
        _chain_variable("CH_FX", flank_span / 2.0, expression="CH_FSPAN / 2", note="Flank-centre horizontal offset"),
        _chain_variable("CH_FY", float(flank_right["center"][1]), expression=f"{float(flank_right['center'][1]) / pitch:.15g} * CH_P", note="Flank-centre height"),
        _chain_variable("CH_HSPAN", head_span, expression=f"{head_span / pitch:.15g} * CH_P", note="Tooth-head centre span"),
        _chain_variable("CH_HX", head_span / 2.0, expression="CH_HSPAN / 2", note="Tooth-head centre horizontal offset"),
        _chain_variable("CH_HY", float(head_right["center"][1]), expression=f"{float(head_right['center'][1]) / pitch:.15g} * CH_P", note="Tooth-head centre height"),
        _chain_variable("CH_CO", abs(closure_shift), note="Outside closure axial offset"),
        _chain_variable("CH_CW", closure_width, note="Width between outside closure side lines"),
        _chain_variable("CH_AXIS", axis_length, note="Tooth construction axis length"),
        _chain_variable("CH_SPAN", 360.0, note="Circular pattern span", unit="deg"),
        _chain_variable("CH_STEP", 360.0 / tooth_count, expression="CH_SPAN / CH_Z", note="Circular pattern angular step", unit="deg"),
    ]

    def point_index(entity: dict[str, Any], *, end: bool) -> int:
        if entity["kind"] == "arc":
            return 2 if end else 1
        return 1 if end else 0

    constraints: list[dict[str, Any]] = []
    for left, right in zip(entities, entities[1:] + entities[:1]):
        constraints.append({
            "kind": "merge_points",
            "target": left["id"],
            "index": point_index(left, end=True),
            "partner": right["id"],
            "partner_index": point_index(right, end=False),
        })
    constraints.extend([
        {"kind": "fixed_point", "target": "chain_pitch_datum", "index": 0},
        {"kind": "merge_points", "target": "chain_outside_datum", "index": 0, "partner": "chain_pitch_datum", "partner_index": 0},
        {"kind": "merge_points", "target": "chain_tooth_axis", "index": 0, "partner": "chain_pitch_datum", "partner_index": 0},
        {"kind": "vertical", "target": "chain_tooth_axis"},
        {"kind": "vertical", "target": "outside_overshoot_right"},
        {"kind": "vertical", "target": "outside_overshoot_left"},
        {"kind": "equal_length", "target": "outside_overshoot_left", "partner": "outside_overshoot_right"},
        {"kind": "tangent", "target": "tooth_head_left", "partner": "tooth_tangent_left"},
        {"kind": "tangent", "target": "tooth_tangent_left", "partner": "tooth_flank_left"},
        {"kind": "tangent", "target": "tooth_flank_left", "partner": "roller_seat_left"},
        {"kind": "tangent", "target": "roller_seat_right", "partner": "tooth_flank_right"},
        {"kind": "tangent", "target": "tooth_flank_right", "partner": "tooth_tangent_right"},
        {"kind": "tangent", "target": "tooth_tangent_right", "partner": "tooth_head_right"},
        {"kind": "equal_radius", "target": "roller_seat_left", "partner": "roller_seat_right"},
        {"kind": "equal_radius", "target": "tooth_flank_left", "partner": "tooth_flank_right"},
        {"kind": "equal_radius", "target": "tooth_head_left", "partner": "tooth_head_right"},
        {"kind": "horizontal", "target": "outside_closure"},
    ])
    for prefix, left_arc, right_arc, _span_variable, _height_variable in center_specs:
        span_id = f"chain_{prefix}_center_span"
        constraints.extend([
            {"kind": "horizontal", "target": span_id},
            {"kind": "merge_points", "target": span_id, "index": 0, "partner": left_arc["id"], "partner_index": 0},
            {"kind": "merge_points", "target": span_id, "index": 1, "partner": right_arc["id"], "partner_index": 0},
        ])
    if center_offset > 0.0:
        constraints.extend([
            {"kind": "horizontal", "target": "roller_seat_bottom"},
            {"kind": "tangent", "target": "roller_seat_left", "partner": "roller_seat_bottom"},
            {"kind": "tangent", "target": "roller_seat_bottom", "partner": "roller_seat_right"},
            {"kind": "horizontal", "target": "chain_seat_center_span"},
            {"kind": "merge_points", "target": "chain_seat_center_span", "index": 0, "partner": "roller_seat_right", "partner_index": 0},
            {"kind": "merge_points", "target": "chain_seat_center_span", "index": 1, "partner": "roller_seat_left", "partner_index": 0},
        ])
    else:
        constraints.extend([
            {"kind": "merge_points", "target": "roller_seat_right", "index": 0, "partner": "roller_seat_left", "partner_index": 0},
        ])

    dimensions = [
        {"kind": "circle_radius", "target": "chain_pitch_datum", "name": "CH_RP_DIM", "variable_name": "CH_RP", "value": pitch_radius, "driving": True},
        {"kind": "circle_radius", "target": "chain_outside_datum", "name": "CH_RA_DIM", "variable_name": "CH_RA", "value": outside_radius, "driving": True},
        {"kind": "line_length", "target": "chain_tooth_axis", "name": "CH_AXIS_DIM", "variable_name": "CH_AXIS", "value": axis_length, "driving": True},
        {"kind": "line_length", "target": "chain_head_center_span", "name": "CH_HSPAN_DIM", "variable_name": "CH_HSPAN", "value": head_span, "driving": True},
        {"kind": "point_coordinate", "target": "tooth_head_right", "point_index": 0, "orientation": "horizontal", "name": "CH_HX_DIM", "variable_name": "CH_HX", "value": head_span / 2.0, "driving": True},
        {"kind": "point_coordinate", "target": "tooth_head_right", "point_index": 0, "orientation": "vertical", "name": "CH_HY_DIM", "variable_name": "CH_HY", "value": float(head_right["center"][1]), "driving": True},
        {"kind": "line_length", "target": "chain_flank_center_span", "name": "CH_FSPAN_DIM", "variable_name": "CH_FSPAN", "value": flank_span, "driving": True},
        {"kind": "point_coordinate", "target": "tooth_flank_right", "point_index": 0, "orientation": "horizontal", "name": "CH_FX_DIM", "variable_name": "CH_FX", "value": flank_span / 2.0, "driving": True},
        {"kind": "point_coordinate", "target": "tooth_flank_right", "point_index": 0, "orientation": "vertical", "name": "CH_FY_DIM", "variable_name": "CH_FY", "value": float(flank_right["center"][1]), "driving": True},
        {"kind": "arc_radius", "target": "roller_seat_right", "name": "CH_R_DIM", "variable_name": "CH_R", "value": seating_radius, "driving": True},
        {"kind": "arc_radius", "target": "tooth_flank_right", "name": "CH_R1_DIM", "variable_name": "CH_R1", "value": flank_radius, "driving": True},
        {"kind": "arc_radius", "target": "tooth_head_right", "name": "CH_R2_DIM", "variable_name": "CH_R2", "value": head_radius, "driving": True},
        {"kind": "line_length", "target": "outside_overshoot_right", "name": "CH_CO_DIM", "variable_name": "CH_CO", "value": abs(closure_shift), "driving": True},
        {"kind": "line_length", "target": "outside_closure", "name": "CH_CW_DIM", "value": closure_width, "driving": False},
    ]
    if center_offset > 0.0:
        variables.append(_chain_variable("CH_E2", center_offset / 2.0, expression="CH_E / 2", note="Half roller-seat centre offset"))
        dimensions.extend([
            {"kind": "line_length", "target": "chain_seat_center_span", "name": "CH_E_DIM", "variable_name": "CH_E", "value": center_offset, "driving": True},
            {"kind": "point_coordinate", "target": "roller_seat_right", "point_index": 0, "orientation": "horizontal", "name": "CH_E2_DIM", "variable_name": "CH_E2", "value": center_offset / 2.0, "driving": True},
            {"kind": "point_coordinate", "target": "roller_seat_right", "point_index": 0, "orientation": "vertical", "name": "CH_SCY_DIM", "variable_name": "CH_SCY", "value": seat_center_y, "driving": True},
        ])
    return {
        "variables": variables,
        "auxiliary_entities": auxiliary_entities,
        "constraints": constraints,
        "dimensions": dimensions,
        "sketch_options": {
            "constraints": {"enabled": True},
            "dimensions": {"enabled": True, "driving": True},
            "parameterization_order": "staged",
            "require_exact_counts": True,
            "expected_constraint_count": len(constraints),
            "expected_dimension_count": len(dimensions),
        },
    }


def _single_row_tooth_width(profile: dict[str, Any]) -> tuple[float, str]:
    inner_width = float(profile["inner_width"])
    pitch = float(profile["pitch"])
    if profile.get("native_tooth_width"):
        return 0.93 * inner_width - 0.15, "KOMPAS native module / GOST 591-69 tooth-width formula"
    if profile["standard"] == "iso_606":
        coefficient = 0.93 if pitch <= 12.7 else 0.95
        return coefficient * inner_width, "DIN 8187 / ISO 606 single-sprocket tooth-width table"
    return 0.93 * inner_width - 0.15, "GOST 591-69 single-row sprocket tooth-width formula"


def _chain_axial_layout(
    profile: dict[str, Any], tooth_count: int, row_count: int, face_width: float | None = None,
) -> dict[str, Any]:
    """Shared preview/CAD axial dimensions; absent catalog data stays unknown."""
    if row_count == 1:
        nominal_width, source = _single_row_tooth_width(profile)
    else:
        coefficient, deduction = (0.90, 0.15) if row_count <= 3 else (0.86, 0.30)
        nominal_width = coefficient * float(profile["inner_width"]) - deduction
        source = "GOST 591-69 Table 2 multi-row tooth-width formula"
    width = nominal_width if face_width is None else float(face_width)
    if not math.isfinite(width) or width <= 0.0:
        raise ValueError("face_width must be finite and greater than 0")
    spacing = profile.get("row_spacing") if row_count > 1 else None
    if spacing is not None and (not math.isfinite(float(spacing)) or float(spacing) <= width):
        raise ValueError("row_spacing must exceed the width of one tooth row")
    height = profile.get("plate_height")
    connector_diameter = None
    if row_count > 1 and height is not None:
        # Table 2 maximum rim diameter; clause 1.5 rounds Dc down to whole mm.
        connector_diameter = float(math.floor(float(profile["pitch"]) / math.tan(math.pi / tooth_count) - 1.3 * float(height)))
    total = width if row_count == 1 else ((row_count - 1) * float(spacing) + width if spacing else None)
    return {
        "row_count": row_count, "tooth_width": width, "standard_tooth_width": nominal_width,
        "width_source": source, "row_spacing": spacing, "total_width": total,
        "connector_diameter": connector_diameter, "plate_height": height,
        "junction_fillet_radius": (1.6 if float(profile["pitch"]) <= 35.0 else 2.5) if row_count > 1 else None,
        "connector_source": "GOST 591-69 Table 2 / clause 1.5" if connector_diameter is not None else None,
        "row_offsets": [-index * float(spacing) for index in range(row_count)] if spacing else [0.0],
        "catalog_complete": row_count == 1 or (spacing is not None and height is not None),
    }


def _build_chain_row_layout_plan(layout: dict[str, Any], *, root_radius: float, rounding: dict[str, Any], name: str) -> dict[str, Any]:
    if layout["row_count"] == 1:
        return {"enabled": False, **layout}
    if not layout["catalog_complete"]:
        raise ValueError("multi-row CAD requires catalogued row_spacing and plate_height for this chain designation")
    radius = float(layout["connector_diameter"]) / 2.0
    if not 0.0 < radius < min(root_radius, float(rounding["center_y"])):
        raise ValueError("connecting rim must remain below the tooth roots and axial roundings")
    r4 = float(layout["junction_fillet_radius"])
    if (2.0 * r4 >= layout["row_spacing"] - layout["tooth_width"]
            or radius + r4 >= min(root_radius, float(rounding["center_y"]))):
        raise ValueError("GOST r4 junction fillets do not fit between rows and below the tooth roots")
    edge_specs = []
    for index in range(layout["row_count"] - 1):
        for side, x in (("near", -index * layout["row_spacing"] - layout["tooth_width"]),
                        ("far", -(index + 1) * layout["row_spacing"])):
            edge_specs.append({"role": f"row_gap_{index + 1}_{side}", "point": [x, radius / math.sqrt(2.0), radius / math.sqrt(2.0)]})
    # Concave quarter-circle fillet: area and radial first moment of added stock.
    added_area = r4**2 * (1.0 - math.pi / 4.0)
    radial_moment = r4**3 * (5.0 / 6.0 - math.pi / 4.0)
    added_volume = len(edge_specs) * 2.0 * math.pi * (radius * added_area + radial_moment) / 1000.0
    total = float(layout["total_width"])
    variables = [
        _chain_variable("CH_N", layout["row_count"], note="Number of tooth rows"),
        _chain_variable("CH_A", layout["row_spacing"], note="Catalog transverse chain pitch"),
        _chain_variable("CH_BT", total, expression="(CH_N - 1) * CH_A + CH_B", note="Total sprocket face width"),
        _chain_variable("CH_DC", layout["connector_diameter"], note="GOST 591-69 maximum rim diameter rounded down to mm"),
        _chain_variable("CH_RC", radius, expression="CH_DC / 2", note="Connecting rim radius"),
    ]
    points = [[0.0, 0.0], [-total, 0.0], [-total, radius], [0.0, radius]]
    names = ["rim_base", "rim_far", "rim_outer", "rim_near"]
    entities = [{"kind": "line", "target": target, "start": points[i], "end": points[(i + 1) % 4]} for i, target in enumerate(names)]
    constraints = [
        {"kind": "fixed_point", "target": "axis", "index": 0},
        {"kind": "fixed_point", "target": "axis", "index": 1},
        {"kind": "fixed_point", "target": "rim_base", "index": 0},
        *[{"kind": "merge_points", "target": target, "index": 1, "partner": names[(i + 1) % 4], "partner_index": 0} for i, target in enumerate(names)],
        *[{"kind": "horizontal" if i % 2 == 0 else "vertical", "target": target} for i, target in enumerate(names)],
    ]
    dimensions = [
        {"kind": "line_length", "target": "rim_base", "name": "CH_RIM_BT_DIM", "variable_name": "CH_BT", "value": total, "driving": True},
        {"kind": "line_length", "target": "rim_near", "name": "CH_RIM_RC_DIM", "variable_name": "CH_RC", "value": radius, "driving": True},
    ]
    return {
        "enabled": True, **layout, "variables": variables,
        "pattern_name": f"{name} row body pattern",
        "junction_fillet": {
            "name": f"{name} row junction fillets", "radius": r4,
            "source": "GOST 591-69 Table 2, r4", "edge_probe_points": edge_specs,
            "expected_edge_count": len(edge_specs), "probe_tolerance": 1e-5,
            "expected_added_volume_cm3": added_volume,
        },
        "pattern_bindings": [
            {"parameter_note_aliases": ["N 1", "Count 1", "Количество 1"], "expression": "CH_N"},
            {"parameter_note_aliases": ["Шаг 1", "Step 1"], "expression": "CH_A"},
        ],
        "expected_gap_volume_cm3": math.pi * radius**2 * (layout["row_count"] - 1) * (layout["row_spacing"] - layout["tooth_width"]) / 1000.0,
        "connector": {
            "params": {
                "name": f"{name} connecting rim", "sketch_name": f"{name} connecting rim sketch",
                "plane": "XOY", "total_length": total, "angle_degrees": 360.0,
                "rotation_axis_default_object_type": 71, "require_explicit_rotation_axis": True,
                "require_parameterization": True, "require_fully_defined": True,
                "require_all_constraints_applied": True, "verify_profile_after_parameterization": True,
                "expected_profile_component_count": 1,
                "sketch": {"constraints": {"enabled": True}, "dimensions": {"enabled": True, "driving": True},
                           "parameterization_order": "constraints_first", "require_exact_counts": True,
                           "expected_constraint_count": len(constraints), "expected_dimension_count": len(dimensions)},
            },
            "bridge_preview": {"geometry": {"profile_entities": entities}, "operations": [
                {"operation": "draw_axis", "start": [5.0, 0.0], "end": [-total - 5.0, 0.0]},
                {"operation": "draw_profile", "profile_entities": entities},
                {"operation": "apply_constraints", "constraints": constraints},
                {"operation": "add_dimensions", "dimensions": dimensions},
            ]},
        },
    }


def _build_chain_axial_rounding_plan(
    *, engagement_diameter: float, outside_radius: float, face_width: float, name: str,
) -> dict[str, Any]:
    """GOST 591-69 Fig. 3/Table 2 retained-tooth end profile, not an edge fillet."""
    if not all(math.isfinite(value) and value > 0.0 for value in (engagement_diameter, outside_radius, face_width)):
        raise ValueError("axial rounding dimensions must be finite and positive")
    minimum_radius = 1.7 * engagement_diameter
    h3 = 0.8 * engagement_diameter
    center_y = outside_radius - h3
    # Table 2 prescribes a MINIMUM radius, not a fixed radius. Our explicit
    # selection policy reserves >=20% of the width as a flat tooth-tip land.
    # For an arc of radial rise h and axial sag s: r = (h*h + s*s)/(2*s).
    # At the normative minimum, s = 0.2*D; keep it when s <= 0.4*b.
    widened_radius = face_width < 0.5 * engagement_diameter
    fitted_radius = h3 * h3 / (0.8 * face_width) + 0.2 * face_width
    r3 = fitted_radius if widened_radius else minimum_radius
    sag = h3 * h3 / (r3 + math.sqrt(r3 * r3 - h3 * h3))
    if not all(math.isfinite(value) for value in (r3, h3, center_y, face_width)):
        raise ValueError("axial rounding dimensions must be finite")
    if center_y <= 0.0:
        raise ValueError("axial rounding requires positive outside_radius - h3")
    if 2.0 * sag >= face_width:
        raise ValueError("axial rounding could not preserve a positive tooth-tip land")
    # Close above the blank and exactly along its end plane; no epsilon inset
    # may leave an uncut slice at either end.
    margin = max(1.0, 0.1 * engagement_diameter)
    variables = [
        _chain_variable("CH_H3", h3, expression="0.8 * CH_DR", note="GOST 591-69 Fig. 3/Table 2 radial centre drop h3"),
        _chain_variable("CH_R3_MIN", minimum_radius, expression="1.7 * CH_DR", note="GOST 591-69 Table 2 minimum radius"),
        _chain_variable("CH_R3_FIT", fitted_radius, expression="CH_H3 * CH_H3 / (0.8 * CH_B) + 0.2 * CH_B", note="Generator policy: radius for 20 percent tooth-tip land"),
        _chain_variable("CH_R3", r3, expression="(CH_B < 0.5 * CH_DR) * CH_R3_FIT + (CH_B >= 0.5 * CH_DR) * CH_R3_MIN", note="Selected radius: GOST minimum with generator tooth-tip land policy"),
        _chain_variable("CH_R3_CY", center_y, expression="CH_RA - CH_H3", note="Axial rounding circle centre height"),
        _chain_variable("CH_R3_CO", margin, note="Technical closure overshoot outside blank"),
        _chain_variable("CH_R3_TOP", outside_radius + margin, expression="CH_RA + CH_R3_CO", note="Technical closure top height"),
    ]
    ends = []
    for side in ("left", "right"):
        right = side == "right"
        def mirror(x: float) -> float:
            # The owned YOZ blank extrudes along -X: its end planes are 0 and -CH_B.
            # Both cutting arcs must enter that interval, not project outside it.
            return x - face_width if right else -x

        points = [[mirror(0.0), center_y], [mirror(sag), outside_radius],
                  [mirror(sag), outside_radius + margin],
                  [mirror(0.0), outside_radius + margin]]
        entities = [{"kind": "arc", "target": "rounding_arc", "center": [mirror(r3), center_y],
                     "radius": r3, "start": points[0], "end": points[1], "direction": right}]
        for index, target in enumerate(("top_riser", "top_closure", "end_closure"), start=1):
            entities.append({"kind": "line", "target": target, "start": points[index], "end": points[(index + 1) % 4]})
        constraints = [
            {"kind": "merge_points", "target": entity["target"], "index": 2 if entity["kind"] == "arc" else 1,
             "partner": following["target"], "partner_index": 1 if following["kind"] == "arc" else 0}
            for entity, following in zip(entities, entities[1:] + entities[:1])
        ]
        constraints.extend([
            {"kind": "fixed_point", "target": "axis", "index": 0},
            {"kind": "horizontal", "target": "axis"},
            *[{"kind": kind, "target": target} for kind, target in (
                ("vertical", "top_riser"), ("horizontal", "top_closure"),
                ("vertical", "end_closure"))],
            {"kind": "tangent", "target": "rounding_arc", "partner": "end_closure"},
        ])
        dimensions = [
            {"kind": "line_length", "target": "axis", "variable_name": "CH_B", "value": face_width},
            {"kind": "arc_radius", "target": "rounding_arc", "variable_name": "CH_R3", "value": r3},
            {"kind": "point_distance", "target": "rounding_arc", "support_point_index": 0,
             "partner": "axis", "partner_point_index": 1 if right else 0, "orientation": "horizontal",
             "variable_name": "CH_R3", "value": r3},
            *[{"kind": "point_coordinate", "target": "rounding_arc", "point_index": index,
               "orientation": "vertical", "variable_name": variable, "value": value}
              for index, variable, value in ((0, "CH_R3_CY", center_y), (2, "CH_RA", outside_radius))],
            {"kind": "point_coordinate", "target": "top_closure", "point_index": 0, "orientation": "vertical",
             "variable_name": "CH_R3_TOP", "value": outside_radius + margin},
        ]
        for index, dimension in enumerate(dimensions):
            dimension.update(name=f"CH_R3_{side.upper()}_{index + 1}_DIM", driving=True)
        sketch_options = {
            "constraints": {"enabled": True}, "dimensions": {"enabled": True, "driving": True},
            "parameterization_order": "constraints_first", "deferred_dimension_kinds": [],
            "require_exact_counts": True, "expected_constraint_count": len(constraints),
            "expected_dimension_count": len(dimensions),
        }
        ends.append({
            "id": f"axial_rounding_{side}", "side": side,
            "params": {
                "name": f"{name} axial rounding {side} cut", "sketch_name": f"{name} axial rounding {side} sketch",
                "plane": "XOY", "total_length": face_width, "angle_degrees": 360.0,
                "rotation_axis_default_object_type": 71, "require_explicit_rotation_axis": True,
                "require_parameterization": True, "require_all_constraints_applied": True,
                "require_fully_defined": True, "verify_profile_after_parameterization": True,
                "expected_profile_component_count": 1, "sketch": sketch_options,
                "_progress": {"sketch_percent": 80 if not right else 86,
                              "sketch_operation": f"axial_rounding_{side}_sketch",
                              "profile_percent": 81 if not right else 87,
                              "profile_operation": f"axial_rounding_{side}_profile",
                              "feature_percent": 83 if not right else 89,
                              "feature_operation": f"axial_rounding_{side}_cut"},
            },
            "bridge_preview": {
                "geometry": {"profile_entities": entities, "profile_points": points + [points[0]]},
                "variables": variables, "constraints": constraints, "dimensions": dimensions,
                "operations": [
                    {"operation": "draw_axis", "start": [0.0, 0.0], "end": [-face_width, 0.0]},
                    {"operation": "draw_profile", "profile_entities": entities, "profile_points": points + [points[0]]},
                    {"operation": "add_variables", "variables": variables},
                    {"operation": "apply_constraints", "constraints": constraints},
                    {"operation": "add_dimensions", "dimensions": dimensions},
                    {"operation": "cut_rotation"},
                ],
            },
        })
    return {
        "enabled": True, "method": "end_face_circular_profile_cut_revolutions", "axis": "global_x",
        "source": "GOST 591-69 Fig. 3 / Table 2",
        "radius_selection": "width_fitted_20_percent_land" if widened_radius else "minimum_1.7_engagement_diameter",
        "minimum_radius": minimum_radius,
        "minimum_tip_land_fraction": 0.2,
        "tip_land_policy_source": "generator design policy, not a GOST-prescribed dimension",
        "tip_land_width": face_width - 2.0 * sag,
        "engagement_diameter": engagement_diameter, "r3": r3, "h3": h3,
        "center_y": center_y, "sag": sag, "face_width": face_width, "outside_radius": outside_radius,
        "axial_interval": [-face_width, 0.0],
        "closure_overshoot": margin, "variables": variables, "ends": ends,
    }


def build_chain_sprocket_plan(
    *,
    designation: ChainDesignation,
    chain_type: ChainType,
    tooth_count: int,
    row_count: int = 1,
    gost_profile_variant: GostToothProfileVariant = "offset",
    face_width: float | None = None,
    name: str = "Geomwright chain sprocket",
) -> dict[str, Any]:
    """Build a host-side functional sprocket plan without touching KOMPAS."""
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")
    if chain_type not in ("roller", "bush"):
        raise ValueError("chain_type must be 'roller' or 'bush'")
    if row_count < 1 or row_count > 8:
        raise ValueError("row_count must be between 1 and 8")

    preview = preview_chain_sprocket(
        designation=designation,
        chain_type=chain_type,
        tooth_count=tooth_count,
        row_count=row_count,
        gost_profile_variant=gost_profile_variant,
    )
    derived = dict(preview["derived"])
    geometry = dict(preview["geometry"])
    profile = dict(preview["profile"])
    outline = [tuple(point) for point in geometry["outline"]]
    if len(outline) < 4 or outline[0] != outline[-1]:
        raise ValueError("chain preview must provide a closed tooth-space contour")

    if row_count > 1 and profile.get("native_simplex_only"):
        raise ValueError("this chain designation is simplex-only")
    nominal_rows = int(profile.get("nominal_row_count") or 1)
    if nominal_rows > 1 and row_count != nominal_rows:
        raise ValueError("row_count must match the selected multi-row designation")
    axial_layout = _chain_axial_layout(profile, tooth_count, row_count, face_width)
    standard_face_width = axial_layout["standard_tooth_width"]
    face_width_source = axial_layout["width_source"]
    resolved_face_width = axial_layout["tooth_width"]
    axial_rounding = _build_chain_axial_rounding_plan(
        engagement_diameter=float(profile["outside_diameter"]),
        outside_radius=float(derived["outside_diameter"]) / 2.0,
        face_width=resolved_face_width, name=requested_name,
    )
    row_layout = _build_chain_row_layout_plan(
        axial_layout, root_radius=float(derived["root_diameter"]) / 2.0,
        rounding=axial_rounding, name=requested_name,
    )
    row_spacing = axial_layout["row_spacing"]
    total_face_width = axial_layout["total_width"]
    entities = _chain_tooth_space_entities({
        **geometry,
        "outside_radius": float(derived["outside_diameter"]) / 2.0,
    })
    parameterization = _build_chain_tooth_parameterization(
        entities=entities,
        pitch=float(profile["pitch"]),
        roller_diameter=float(profile["outside_diameter"]),
        tooth_count=int(tooth_count),
        face_width=resolved_face_width,
        outside_diameter=float(derived["outside_diameter"]),
        root_diameter=float(derived["root_diameter"]),
        center_offset=float(derived["standard_parameters"]["center_offset"]),
    )
    sketch_entities = entities + list(parameterization["auxiliary_entities"])
    operations = [
        {
            "id": "blank",
            "scenario": "cylindrical_blank",
            "params": {
                "name": f"{requested_name} blank",
                "sketch_name": f"{requested_name} blank sketch",
                "outside_diameter": float(derived["outside_diameter"]),
                "width": resolved_face_width,
                "row_count": 1,
                "plane": "YOZ",
                "axis": "x_axis",
                "parameterize": True,
                "variable_plan": list(parameterization["variables"]),
                "constraints": [{"kind": "fixed_point", "target": "blank_circle", "index": 0}],
                "dimensions": [{"kind": "circle_radius", "target": "blank_circle", "name": "CH_BLANK_RA_DIM", "variable_name": "CH_RA", "value": float(derived["outside_diameter"]) / 2.0, "driving": True}],
                "operation_variable_bindings": [{"target": "extrusion", "parameter_note": "Distance 1", "parameter_note_aliases": ["Distance 1", "Length 1", "Depth 1", "Расстояние 1", "Длина 1", "Глубина 1"], "expression": "CH_B", "role": "blank_width"}],
                "sketch_options": {"constraints": {"enabled": True}, "dimensions": {"enabled": True, "driving": True}, "parameterization_order": "constraints_first"},
            },
        },
        {
            "id": "tooth_space_sketch",
            "scenario": "numeric_profile_sketch",
            "params": {
                "name": f"{requested_name} one tooth space",
                "plane": "YOZ",
                "entities": sketch_entities,
                "parameterize": True,
                "constraints": list(parameterization["constraints"]),
                "dimensions": list(parameterization["dimensions"]),
                "post_build_constraints": [
                    {
                        "kind": "point_on_curve",
                        "target": "outside_overshoot_right",
                        "index": 0,
                        "partner": "chain_outside_datum",
                    },
                ],
                "sketch_options": dict(parameterization["sketch_options"]),
                "require_fully_defined": True,
                "profile_status": "parameterized_true_arcs",
            },
        },
        {
            "id": "tooth_space_cut",
            "scenario": "cut_extrusion",
            "params": {
                "name": f"{requested_name} one tooth space cut",
                "sketch": "tooth_space_sketch.sketch",
                "direction": "both",
                "end_condition": "through_all",
                "require_fully_defined": True,
            },
        },
        {
            "id": "tooth_space_pattern",
            "scenario": "circular_pattern",
            "params": {
                "name": f"{requested_name} tooth space pattern",
                "source": "tooth_space_cut.feature",
                "axis": "blank.axis",
                "count": int(tooth_count),
                "span_angle": 360.0,
                "parameterize": True,
                "parameter_prefix": "CH",
                "count_variable": "CH_Z",
                "span_angle_variable": "CH_SPAN",
                "angle_step_variable": "CH_STEP",
            },
        },
    ]
    return {
        "ok": True,
        "stage": "managed_chain_sprocket_plan",
        "plan_version": 1,
        "family": "chain_sprocket",
        "name": requested_name,
        "profile_preview": preview,
        "axial_rounding": axial_rounding,
        "row_layout": row_layout,
        "workflow": {
            "scenario": "workflow",
            "params": {
                "name": requested_name,
                "operations": operations,
                "exports": [
                    {"name": "blank_body", "ref": "blank.body"},
                    {"name": "tooth_space_cut", "ref": "tooth_space_cut.feature"},
                    {"name": "tooth_space_pattern", "ref": "tooth_space_pattern.feature"},
                ],
            },
        },
        "geometry": {
            "tooth_space_vertices": [list(point) for point in outline],
            "tooth_space_entities": entities,
            "auxiliary_entities": list(parameterization["auxiliary_entities"]),
            "outside_radius": float(derived["outside_diameter"]) / 2.0,
            "root_radius": float(derived["root_diameter"]) / 2.0,
            "face_width": resolved_face_width,
            "total_face_width": total_face_width,
            "row_spacing": row_spacing,
            "row_count": int(row_count),
            "connector_diameter": axial_layout["connector_diameter"],
            "standard_face_width": standard_face_width,
            "face_width_source": face_width_source,
        },
        "ownership": {
            "schema": "geomwright.managed_chain_sprocket",
            "version": 1,
            "family": "chain_sprocket",
            "required_variables": [
                "GW_MANAGED_VERSION", "GW_FAMILY_CODE",
                *[str(variable["name"]) for variable in parameterization["variables"]],
                *[str(variable["name"]) for variable in axial_rounding["variables"]],
                *[str(variable["name"]) for variable in row_layout.get("variables", [])],
            ],
            "blank_feature_name": f"{requested_name} blank",
            "blank_sketch_name": f"{requested_name} blank sketch",
            "tooth_space_feature_name": f"{requested_name} one tooth space cut",
            "tooth_space_sketch_name": f"{requested_name} one tooth space",
            "pattern_feature_name": f"{requested_name} tooth space pattern",
            "axial_rounding_feature_names": [end["params"]["name"] for end in axial_rounding["ends"]],
            "axial_rounding_sketch_names": [end["params"]["sketch_name"] for end in axial_rounding["ends"]],
            "row_pattern_name": row_layout.get("pattern_name"),
            "connecting_rim_name": (row_layout.get("connector") or {}).get("params", {}).get("name"),
            "source_profile": {
                "designation": designation,
                "chain_type": chain_type,
                "tooth_count": int(tooth_count),
                "row_count": int(row_count),
                "tooth_profile_variant": gost_profile_variant,
                "gost_profile_variant": gost_profile_variant,
            },
        },
        "boundary": {
            "functional_geometry_only": True,
            "row_count": int(row_count),
            "axial_row_layout": "single_row" if row_count == 1 else "body_pattern_with_connecting_rim",
            "excluded": ["hub", "bore", "keyway", "shaft_interface", "downstream_manufacturing"],
        },
        "verification": {
            "require_single_body": True,
            "require_closed_primary_contour": True,
            "require_volume_decrease_after_cut": True,
            "require_pattern_count": int(tooth_count),
            "require_axial_rounding_cut_count": 2,
            "require_pattern_span_degrees": 360.0,
            "require_row_count": int(row_count),
            "axial_row_layout_status": "single_row" if row_count == 1 else "body_pattern_with_connecting_rim",
            "expected_total_face_width": total_face_width,
            "expected_pitch_diameter": float(derived["pitch_diameter"]),
            "expected_outside_diameter": float(derived["outside_diameter"]),
            "expected_root_diameter": float(derived["root_diameter"]),
            "profile_status": "numeric_true_arcs",
        },
        "parameterization": {
            "part_variables": True,
            "sketch_constraints": True,
            "sketch_dimensions": True,
            "operation_variables": True,
            "variables": list(parameterization["variables"]),
            "constraints": list(parameterization["constraints"]),
            "dimensions": list(parameterization["dimensions"]),
        },
    }
