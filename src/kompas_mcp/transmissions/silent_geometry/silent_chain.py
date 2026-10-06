"""Studio-only selection data for GOST silent-chain sprockets (no geometry)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# GOST 13552-81 (reprint 03.1987, amendment 1), chain designation table.
# Each key encodes type, pitch (mm), minimum breaking load (kN), and working
# chain width (mm). No tooth/face-width dimensions are inferred from these keys.
_GOST_DESIGNATIONS = """
PZ-1-12.7-26-22.5 PZ-1-12.7-31-28.5 PZ-1-12.7-36-34.5
PZ-1-12.7-42-40.5 PZ-1-12.7-49-46.5 PZ-1-12.7-56-52.5
PZ-1-15.875-41-30 PZ-1-15.875-50-38 PZ-1-15.875-58-46
PZ-1-15.875-69-54 PZ-1-15.875-80-62 PZ-1-15.875-91-70
PZ-1-19.05-74-45 PZ-1-19.05-89-57 PZ-1-19.05-105-69
PZ-1-19.05-124-81 PZ-1-19.05-143-93
PZ-2-25.4-101-57 PZ-2-25.4-132-75 PZ-2-25.4-164-93
PZ-2-25.4-196-111 PZ-2-31.75-166-75 PZ-2-31.75-206-93
PZ-2-31.75-246-111 PZ-2-31.75-286-129
""".split()

# Research-stage catalog `din-8190-catalog.csv`: 60 entries reproduced from
# MDESIGN/INGGO secondary tables. The source marks confidence=medium. This data
# is intentionally kept separate from the GOST and ASME-compatible families.
_DIN_ROWS = (
    ("06-015A", "outer", 9.525, 12.5, 19.8, 17400), ("06-020A", "outer", 9.525, 17.2, 24.5, 21200),
    ("06-025A", "outer", 9.525, 23.5, 30.8, 29000), ("06-030A", "outer", 9.525, 29.7, 37.0, 36700),
    ("06-040A", "outer", 9.525, 39.1, 46.5, 48300), ("08-020A", "outer", 12.7, 17.2, 25.9, 33000),
    ("08-025A", "outer", 12.7, 23.5, 32.2, 44700), ("08-030A", "outer", 12.7, 29.7, 38.5, 56000),
    ("08-040A", "outer", 12.7, 39.1, 47.9, 74500), ("08-050A", "outer", 12.7, 48.5, 57.2, 92400),
    ("12-035A", "outer", 19.05, 35.4, 46.5, 90000), ("12-050A", "outer", 19.05, 47.8, 59.0, 121000),
    ("12-065A", "outer", 19.05, 64.5, 75.6, 164000), ("12-090A", "outer", 19.05, 85.3, 96.4, 217000),
    ("12-110A", "outer", 19.05, 106.1, 117.2, 270000), ("16-050A", "outer", 25.4, 43.3, 57.5, 153000),
    ("16-060A", "outer", 25.4, 58.8, 73.0, 194000), ("16-080A", "outer", 25.4, 77.4, 91.6, 255000),
    ("16-100A", "outer", 25.4, 99.0, 113.2, 337000), ("16-125A", "outer", 25.4, 120.7, 135.0, 398000),
    ("24-060A", "outer", 38.1, 55.9, 74.1, 279000), ("24-080A", "outer", 38.1, 74.5, 92.7, 368000),
    ("24-100A", "outer", 38.1, 93.2, 111.4, 456000), ("24-125A", "outer", 38.1, 118.0, 136.2, 574000),
    ("24-150A", "outer", 38.1, 142.8, 161.0, 692000), ("32-080A", "outer", 50.8, 74.5, 95.6, 507000),
    ("32-100A", "outer", 50.8, 90.9, 112.1, 614000), ("32-125A", "outer", 50.8, 115.6, 136.2, 774000),
    ("32-160A", "outer", 50.8, 148.7, 169.9, 987000), ("32-200A", "outer", 50.8, 190.0, 211.2, 1254000),
    ("06-025B", "inner", 9.525, 25.8, 30.8, 33000), ("06-030B", "inner", 9.525, 31.8, 37.1, 40600),
    ("06-040B", "inner", 9.525, 37.9, 43.4, 48300), ("06-050B", "inner", 9.525, 50.0, 55.8, 63800),
    ("06-065B", "inner", 9.525, 62.1, 68.4, 79300), ("08-030B", "inner", 12.7, 31.8, 38.5, 62600),
    ("08-040B", "inner", 12.7, 37.9, 44.7, 74500), ("08-050B", "inner", 12.7, 50.0, 57.2, 98400),
    ("08-065B", "inner", 12.7, 62.1, 69.8, 122000), ("08-075B", "inner", 12.7, 74.2, 82.3, 146000),
    ("12-035B", "inner", 19.05, 34.3, 42.4, 90000), ("12-040B", "inner", 19.05, 42.4, 50.7, 111000),
    ("12-050B", "inner", 19.05, 50.5, 59.0, 132000), ("12-065B", "inner", 19.05, 66.7, 75.8, 174000),
    ("12-100B", "inner", 19.05, 99.0, 108.9, 259000), ("16-050B", "inner", 25.4, 51.4, 60.6, 173000),
    ("16-065B", "inner", 25.4, 63.5, 73.0, 214000), ("16-075B", "inner", 25.4, 75.6, 85.4, 255000),
    ("16-100B", "inner", 25.4, 99.8, 110.0, 337000), ("16-150B", "inner", 25.4, 148.2, 160.0, 500000),
    ("24-065B", "inner", 38.1, 63.7, 77.2, 309000), ("24-075B", "inner", 38.1, 75.9, 89.6, 368000),
    ("24-100B", "inner", 38.1, 100.2, 114.5, 485000), ("24-125B", "inner", 38.1, 124.4, 139.3, 603000),
    ("24-150B", "inner", 38.1, 148.7, 164.0, 721000), ("32-090B", "inner", 50.8, 84.7, 99.7, 560000),
    ("32-100B", "inner", 50.8, 100.9, 116.3, 667000), ("32-115B", "inner", 50.8, 117.0, 132.8, 774000),
    ("32-150B", "inner", 50.8, 149.3, 165.8, 987000), ("32-180B", "inner", 50.8, 181.6, 198.9, 1200000),
)

_ASME_PITCHES_MM = (4.7625, 9.525, 12.7, 15.875, 19.05, 25.4, 31.75, 38.1, 50.8)
_ASME_GUIDES = ("side_guide", "center_guide", "two_center_guide")


class SilentChainSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standard: Literal["gost_13552_81_13576_81", "din_8190_8191_open", "asme_b29_2m_open"] = "gost_13552_81_13576_81"
    family: str = "type_1"
    designation: str
    physical_tooth_count: int = Field(ge=11, le=114)
    accuracy_class: Literal[1, 2] | None = None
    face_width_mm: float = Field(default=20.0, gt=0, allow_inf_nan=False)
    tooth_tip_shape: Literal["square", "round"] = "square"
    axial_source: Literal["ramsey_rp_sc", "gb_10855_2016"] = "ramsey_rp_sc"
    body_depth_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    guide_depth_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    guide_bottom_radius_mm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    guide_width_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    guide_spacing_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    entrance_height_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    axial_round_radius_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    tool_root_radius_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    tool_floor_depth_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    din_rack_resolution: Literal["unresolved", "keep_radii", "keep_height"] = "unresolved"
    square_tip_resolution: Literal["unresolved", "accept_ramsey", "custom_diameter"] = "unresolved"
    square_tip_diameter_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_selection(self) -> SilentChainSelectionRequest:
        if self.standard == "gost_13552_81_13576_81":
            if self.designation not in _GOST_DESIGNATIONS:
                raise ValueError("Unknown GOST 13552-81 chain designation")
            chain_type = int(self.designation.split("-")[1])
            low, high = (17, 96) if chain_type == 1 else (11, 48)
            if self.family != f"type_{chain_type}":
                raise ValueError("GOST chain family does not match the selected designation")
            if self.accuracy_class not in (1, 2):
                raise ValueError("GOST 13576-81 accuracy class must be 1 or 2")
        elif self.standard == "din_8190_8191_open":
            matches = [row for row in _DIN_ROWS if row[0] == self.designation and row[1] == self.family]
            if not matches:
                raise ValueError("Unknown DIN open-reconstruction designation or guide family")
            low, high = 15, 114
            if self.accuracy_class is not None:
                raise ValueError("Accuracy class is only selectable for the GOST catalog")
        else:
            if not self.designation.startswith("asme-") or self.family != "pitch_and_guide":
                raise ValueError("Unknown ASME open-reconstruction pitch/guide selection")
            try:
                _, pitch_value, guide = self.designation.split("-", 2)
                pitch = float(pitch_value)
            except (IndexError, ValueError) as exc:
                raise ValueError("Unknown ASME open-reconstruction pitch") from exc
            if pitch not in _ASME_PITCHES_MM or guide not in _ASME_GUIDES:
                raise ValueError("Unknown ASME open-reconstruction pitch")
            low, high = 17, 114
            if self.accuracy_class is not None:
                raise ValueError("Accuracy class is only selectable for the GOST catalog")
            if self.face_width_mm <= 0:
                raise ValueError("ASME open-reconstruction preview requires a positive user-supplied face width")
        if not low <= self.physical_tooth_count <= high:
            raise ValueError(f"{self.standard} requires {low}…{high} physical teeth")
        return self


def silent_chain_selection() -> dict:
    gost_families = []
    for chain_type in (1, 2):
        profiles = []
        for designation in _GOST_DESIGNATIONS:
            _, type_number, pitch, load, width = designation.split("-")
            if int(type_number) != chain_type:
                continue
            profiles.append({
                "value": designation,
                "label_ru": designation.replace("PZ-", "ПЗ-").replace(".", ","),
                "label_en": designation,
                "chain_type": chain_type,
                "pitch_mm": float(pitch),
                "working_width_mm": float(width),
                "min_breaking_load_kn": int(load),
                "plate_thickness_mm": {12.7: 1.5, 15.875: 2.0, 19.05: 3.0, 25.4: 3.0, 31.75: 3.0}[float(pitch)],
                "axis_to_tooth_tip_h1_mm": {12.7: 7.0, 15.875: 8.7, 19.05: 10.5, 25.4: 13.35, 31.75: 16.7}[float(pitch)],
                "joint_to_working_face_u_mm": {12.7: 4.76, 15.875: 5.95, 19.05: 7.14, 25.4: 9.52, 31.75: 11.91}[float(pitch)],
            })
        gost_families.append({
            "value": f"type_{chain_type}",
            "label_ru": f"Тип {chain_type} · {'одностороннее' if chain_type == 1 else 'двухстороннее'} зацепление",
            "label_en": f"Type {chain_type} · {'single-sided' if chain_type == 1 else 'double-sided'} engagement",
            "profiles": profiles,
        })
    din_families = []
    for guide, label_ru, label_en in (("outer", "Наружное направление · форма A", "Outer guide · form A"), ("inner", "Внутреннее направление · форма B", "Inner guide · form B")):
        profiles = [{
            "value": designation,
            "label_ru": f"{designation} · {pitch:g} мм",
            "label_en": f"{designation} · {pitch:g} mm",
            "chain_type": guide,
            "pitch_mm": pitch,
            "working_width_mm": width,
            "overall_width_mm": overall,
            "breaking_load_n": load,
            "source": "MDESIGN/INGGO secondary reproduction of DIN 8190",
            "source_ru": "Вторичная таблица MDESIGN/INGGO по DIN 8190",
            "confidence": "medium",
            "reconstruction": True,
        } for designation, row_guide, pitch, width, overall, load in _DIN_ROWS if row_guide == guide]
        din_families.append({"value": guide, "label_ru": label_ru, "label_en": label_en, "profiles": profiles})

    asme_profiles = []
    guide_labels = {
        "side_guide": ("боковая направляющая", "side guide"),
        "center_guide": ("центральная направляющая", "center guide"),
        "two_center_guide": ("двойная центральная направляющая", "two-center guide"),
    }
    for pitch in _ASME_PITCHES_MM:
        for guide in _ASME_GUIDES:
            asme_profiles.append({
                "value": f"asme-{pitch:g}-{guide}",
                "label_ru": f"Шаг {pitch:g} мм · {guide_labels[guide][0]}",
                "label_en": f"{pitch:g} mm pitch · {guide_labels[guide][1]}",
                "chain_type": guide,
                "pitch_mm": pitch,
                "source": "GB/T 10855-2016 plus Ramsey catalog corroboration",
                "source_ru": "GB/T 10855-2016; независимая проверка по каталогу Ramsey",
                "confidence": "open_reconstruction",
                "reconstruction": True,
                "designation_available": False,
            })
    return {
        "standards": [{
            "value": "gost_13552_81_13576_81",
            "label_ru": "ГОСТ 13552-81 / ГОСТ 13576-81",
            "label_en": "GOST 13552-81 / GOST 13576-81",
            "reconstruction": False,
            "warning_ru": "Диаметры preview рассчитаны по формулам ГОСТ. Контур зуба показан аналитически и требует отдельной сверки с чертежом 1/2 стандарта; это не CAD-модель.",
            "warning_en": "Preview diameters use GOST equations. The tooth contour is an analytical visualization and still needs a separate check against standard drawing 1/2; this is not a CAD model.",
            "families": gost_families,
        }, {
            "value": "din_8190_8191_open",
            "label_ru": "DIN 8190/8191-compatible · открытая реконструкция",
            "label_en": "DIN 8190/8191-compatible · open reconstruction",
            "reconstruction": True,
            "warning_ru": "Неофициальная реконструкция: DIN-каталог получен из вторичной таблицы (MDESIGN/INGGO, средняя уверенность), профиль — по доступному переводу DIN 8191:1998. Требуется осторожность; соответствие DIN 8191:2022 не подтверждено.",
            "warning_en": "Unofficial reconstruction: DIN catalog comes from a secondary table (MDESIGN/INGGO, medium confidence); tooth profile uses an available translation of DIN 8191:1998. Use with caution; conformity to DIN 8191:2022 is unverified.",
            "families": din_families,
        }, {
            "value": "asme_b29_2m_open",
            "label_ru": "ASME B29.2M-compatible · открытая реконструкция",
            "label_en": "ASME B29.2M-compatible · open reconstruction",
            "reconstruction": True,
            "warning_ru": "Неофициальная реконструкция: номинальный профиль основан на открытом GB/T 10855-2016 и проверке по каталогу Ramsey. Точное соответствие ASME B29.2M не установлено; обозначения цепей и размерный каталог не предоставляются.",
            "warning_en": "Unofficial reconstruction: nominal profile is based on open GB/T 10855-2016 and corroborated against the Ramsey catalog. Exact ASME B29.2M equivalence is not established; chain designations and a dimensional chain catalog are not supplied.",
            "families": [{
                "value": "pitch_and_guide",
                "label_ru": "Шаг и направляющая · без каталожного обозначения",
                "label_en": "Pitch and guide · no catalog designation",
                "profiles": asme_profiles,
            }],
        }],
    }
