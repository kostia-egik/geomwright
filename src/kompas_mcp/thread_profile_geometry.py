from __future__ import annotations

import math
import re
from fractions import Fraction
from typing import Any


INCH_TO_MM = 25.4
V60_THREAD_PROFILE_ANGLE_DEGREES = 60.0
V60_FUNDAMENTAL_HEIGHT_FACTOR = math.sqrt(3.0) / 2.0
V60_PITCH_DIAMETER_FACTOR = 3.0 * V60_FUNDAMENTAL_HEIGHT_FACTOR / 4.0
V60_INTERNAL_MINOR_FACTOR = 5.0 * V60_FUNDAMENTAL_HEIGHT_FACTOR / 4.0
V60_EXTERNAL_MINOR_FACTOR = 17.0 * V60_FUNDAMENTAL_HEIGHT_FACTOR / 12.0
WHITWORTH_THREAD_PROFILE_ANGLE_DEGREES = 55.0
WHITWORTH_HALF_ANGLE_RADIANS = math.radians(WHITWORTH_THREAD_PROFILE_ANGLE_DEGREES / 2.0)
WHITWORTH_FUNDAMENTAL_HEIGHT_FACTOR = 1.0 / (2.0 * math.tan(WHITWORTH_HALF_ANGLE_RADIANS))
WHITWORTH_THREAD_DEPTH_FACTOR = (2.0 / 3.0) * WHITWORTH_FUNDAMENTAL_HEIGHT_FACTOR
WHITWORTH_ROUND_RADIUS_FACTOR = (
    WHITWORTH_FUNDAMENTAL_HEIGHT_FACTOR * math.sin(WHITWORTH_HALF_ANGLE_RADIANS)
) / (6.0 * (1.0 - math.sin(WHITWORTH_HALF_ANGLE_RADIANS)))

METRIC_THREAD_PROFILE_ANGLE_DEGREES = V60_THREAD_PROFILE_ANGLE_DEGREES

UNIFIED_INCH_PROFILE_FAMILY_ALIASES = {
    "un": "unified_un_v60",
    "unc": "unified_un_v60",
    "unf": "unified_un_v60",
    "unef": "unified_un_v60",
    "uns": "unified_un_v60",
    "unified": "unified_un_v60",
    "unified_inch": "unified_un_v60",
    "unified_inch_v60": "unified_un_v60",
    "unified_un": "unified_un_v60",
    "unified_un_v60": "unified_un_v60",
    "unr": "unified_unr_v60",
    "unrc": "unified_unr_v60",
    "unrf": "unified_unr_v60",
    "unref": "unified_unr_v60",
    "unified_unr": "unified_unr_v60",
    "unified_unr_v60": "unified_unr_v60",
    "unj": "unified_unj_v60",
    "unjc": "unified_unj_v60",
    "unjf": "unified_unj_v60",
    "unjef": "unified_unj_v60",
    "unified_unj": "unified_unj_v60",
    "unified_unj_v60": "unified_unj_v60",
    "pipe": "pipe_nps_v60",
    "pipe_straight": "pipe_nps_v60",
    "nps": "pipe_nps_v60",
    "npsm": "pipe_nps_v60",
    "npsl": "pipe_nps_v60",
    "npsc": "pipe_nps_v60",
    "pipe_nps": "pipe_nps_v60",
    "pipe_nps_v60": "pipe_nps_v60",
    "pipe_taper": "pipe_npt_v60",
    "pipe_tapered": "pipe_npt_v60",
    "npt": "pipe_npt_v60",
    "pipe_npt": "pipe_npt_v60",
    "pipe_npt_v60": "pipe_npt_v60",
    "bsp": "pipe_bsp_g_v55",
    "bspp": "pipe_bsp_g_v55",
    "g": "pipe_bsp_g_v55",
    "pipe_bsp": "pipe_bsp_g_v55",
    "pipe_bsp_g": "pipe_bsp_g_v55",
    "pipe_bsp_g_v55": "pipe_bsp_g_v55",
    "bsp_parallel": "pipe_bsp_g_v55",
    "bsp_pipe_parallel": "pipe_bsp_g_v55",
    "pipe_cylindrical": "pipe_bsp_g_v55",
    "iso_228": "pipe_bsp_g_v55",
    "iso_228_1": "pipe_bsp_g_v55",
    "cil2_6357_81": "pipe_bsp_g_v55",
    "gost_6357_81": "pipe_bsp_g_v55",
}

_UNIFIED_NUMBER_SIZE_MAJOR_INCH = {
    "0": 0.060,
    "1": 0.073,
    "2": 0.086,
    "3": 0.099,
    "4": 0.112,
    "5": 0.125,
    "6": 0.138,
    "8": 0.164,
    "10": 0.190,
    "12": 0.216,
}

_UNIFIED_SERIES_TPI = {
    "UNC": {
        "#0": 80,
        "#1": 64,
        "#2": 56,
        "#3": 48,
        "#4": 40,
        "#5": 40,
        "#6": 32,
        "#8": 32,
        "#10": 24,
        "#12": 24,
        "1/4": 20,
        "5/16": 18,
        "3/8": 16,
        "7/16": 14,
        "1/2": 13,
        "9/16": 12,
        "5/8": 11,
        "3/4": 10,
        "7/8": 9,
        "1": 8,
        "1-1/8": 7,
        "1-1/4": 7,
        "1-3/8": 6,
        "1-1/2": 6,
    },
    "UNF": {
        "#0": 80,
        "#1": 72,
        "#2": 64,
        "#3": 56,
        "#4": 48,
        "#5": 44,
        "#6": 40,
        "#8": 36,
        "#10": 32,
        "#12": 28,
        "1/4": 28,
        "5/16": 24,
        "3/8": 24,
        "7/16": 20,
        "1/2": 20,
        "9/16": 18,
        "5/8": 18,
        "3/4": 16,
        "7/8": 14,
        "1": 12,
        "1-1/8": 12,
        "1-1/4": 12,
        "1-3/8": 12,
        "1-1/2": 12,
    },
    "UNEF": {
        "#12": 32,
        "1/4": 32,
        "5/16": 32,
        "3/8": 32,
        "7/16": 28,
        "1/2": 28,
        "9/16": 24,
        "5/8": 24,
        "3/4": 20,
        "7/8": 20,
        "1": 20,
        "1-1/8": 18,
        "1-1/4": 18,
        "1-3/8": 18,
        "1-1/2": 18,
    },
}

PIPE_V60_THREAD_HEIGHT_FACTOR = 0.8
PIPE_NPT_DIAMETER_TAPER_RATIO = 1.0 / 16.0
PIPE_NPT_RADIUS_TAPER_RATIO = PIPE_NPT_DIAMETER_TAPER_RATIO / 2.0
PIPE_NPT_TAPER_HALF_ANGLE_DEGREES = math.degrees(math.atan(PIPE_NPT_RADIUS_TAPER_RATIO))

_PIPE_NPS_SIZE_TABLE = {
    "1/16": {"major_diameter_inch": 0.3125, "tpi": 27.0},
    "1/8": {"major_diameter_inch": 0.405, "tpi": 27.0},
    "1/4": {"major_diameter_inch": 0.540, "tpi": 18.0},
    "3/8": {"major_diameter_inch": 0.675, "tpi": 18.0},
    "1/2": {"major_diameter_inch": 0.840, "tpi": 14.0},
    "3/4": {"major_diameter_inch": 1.050, "tpi": 14.0},
    "1": {"major_diameter_inch": 1.315, "tpi": 11.5},
    "1-1/4": {"major_diameter_inch": 1.660, "tpi": 11.5},
    "1-1/2": {"major_diameter_inch": 1.900, "tpi": 11.5},
    "2": {"major_diameter_inch": 2.375, "tpi": 11.5},
    "2-1/2": {"major_diameter_inch": 2.875, "tpi": 8.0},
    "3": {"major_diameter_inch": 3.500, "tpi": 8.0},
    "3-1/2": {"major_diameter_inch": 4.000, "tpi": 8.0},
    "4": {"major_diameter_inch": 4.500, "tpi": 8.0},
    "5": {"major_diameter_inch": 5.563, "tpi": 8.0},
    "6": {"major_diameter_inch": 6.625, "tpi": 8.0},
    "8": {"major_diameter_inch": 8.625, "tpi": 8.0},
    "10": {"major_diameter_inch": 10.750, "tpi": 8.0},
    "12": {"major_diameter_inch": 12.750, "tpi": 8.0},
}

_PIPE_BSP_G_SIZE_TABLE = {
    "1/16": {"major_diameter_inch": 7.723 / INCH_TO_MM, "tpi": 28.0},
    "1/8": {"major_diameter_inch": 9.728 / INCH_TO_MM, "tpi": 28.0},
    "1/4": {"major_diameter_inch": 13.157 / INCH_TO_MM, "tpi": 19.0},
    "3/8": {"major_diameter_inch": 16.662 / INCH_TO_MM, "tpi": 19.0},
    "1/2": {"major_diameter_inch": 20.955 / INCH_TO_MM, "tpi": 14.0},
    "5/8": {"major_diameter_inch": 22.911 / INCH_TO_MM, "tpi": 14.0},
    "3/4": {"major_diameter_inch": 26.441 / INCH_TO_MM, "tpi": 14.0},
    "7/8": {"major_diameter_inch": 30.201 / INCH_TO_MM, "tpi": 14.0},
    "1": {"major_diameter_inch": 33.249 / INCH_TO_MM, "tpi": 11.0},
    "1-1/8": {"major_diameter_inch": 37.897 / INCH_TO_MM, "tpi": 11.0},
    "1-1/4": {"major_diameter_inch": 41.910 / INCH_TO_MM, "tpi": 11.0},
    "1-3/8": {"major_diameter_inch": 44.323 / INCH_TO_MM, "tpi": 11.0},
    "1-1/2": {"major_diameter_inch": 47.803 / INCH_TO_MM, "tpi": 11.0},
    "1-3/4": {"major_diameter_inch": 53.746 / INCH_TO_MM, "tpi": 11.0},
    "2": {"major_diameter_inch": 59.614 / INCH_TO_MM, "tpi": 11.0},
    "2-1/4": {"major_diameter_inch": 65.710 / INCH_TO_MM, "tpi": 11.0},
    "2-1/2": {"major_diameter_inch": 75.184 / INCH_TO_MM, "tpi": 11.0},
    "2-3/4": {"major_diameter_inch": 81.534 / INCH_TO_MM, "tpi": 11.0},
    "3": {"major_diameter_inch": 87.884 / INCH_TO_MM, "tpi": 11.0},
    "3-1/4": {"major_diameter_inch": 93.980 / INCH_TO_MM, "tpi": 11.0},
    "3-1/2": {"major_diameter_inch": 100.330 / INCH_TO_MM, "tpi": 11.0},
    "3-3/4": {"major_diameter_inch": 106.680 / INCH_TO_MM, "tpi": 11.0},
    "4": {"major_diameter_inch": 113.030 / INCH_TO_MM, "tpi": 11.0},
}


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _optional_positive_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except Exception:
        return None
    if not math.isfinite(parsed) or parsed <= 0.0:
        return None
    return parsed


def _canonical_unified_size_token(value: str) -> str:
    token = str(value or "").strip().upper().replace(" ", "")
    if not token:
        return ""
    if token.startswith("NO."):
        token = "#" + token[3:]
    if token.startswith("N0."):
        token = "#" + token[3:]
    if token.startswith("N"):
        rest = token[1:]
        if rest.isdigit():
            token = "#" + rest
    if token.startswith("#"):
        return "#" + token[1:].lstrip("0") if token[1:].lstrip("0") else "#0"
    if "-" in token and "/" in token:
        whole, fraction = token.split("-", 1)
        return f"{int(whole)}-{Fraction(fraction)}"
    if "/" in token:
        return str(Fraction(token))
    if re.fullmatch(r"\d+(?:\.0+)?", token):
        return str(int(float(token)))
    return token


def _canonical_fractional_inch_token(value: Any) -> str:
    token = str(value or "").strip().upper().replace('"', "").replace(" ", "")
    if not token:
        return ""
    if "-" in token and "/" in token:
        whole, fraction = token.split("-", 1)
        return f"{int(whole)}-{Fraction(fraction)}"
    if "/" in token:
        return str(Fraction(token))
    if re.fullmatch(r"\d+(?:\.0+)?", token):
        return str(int(float(token)))
    return token


def _parse_unified_size_inch(value: Any) -> float:
    token = str(value or "").strip().upper().replace(" ", "")
    if not token:
        raise ValueError("unified inch thread size is required")
    if token.startswith("#"):
        key = token[1:].lstrip("0") or "0"
        if key not in _UNIFIED_NUMBER_SIZE_MAJOR_INCH:
            raise ValueError(f"unsupported unified number size #{key}")
        return _UNIFIED_NUMBER_SIZE_MAJOR_INCH[key]
    if token.startswith("NO."):
        return _parse_unified_size_inch("#" + token[3:])
    if token.startswith("N") and token[1:].isdigit():
        return _parse_unified_size_inch("#" + token[1:])
    if "-" in token and "/" in token:
        whole, fraction = token.split("-", 1)
        return float(int(whole) + Fraction(fraction))
    if "/" in token:
        return float(Fraction(token))
    try:
        parsed = float(token)
    except Exception as exc:
        raise ValueError(f"unsupported unified inch thread size: {value}") from exc
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"unsupported unified inch thread size: {value}")
    return parsed


def _normalize_unified_series(value: Any) -> str:
    series = str(value or "").strip().upper().replace(" ", "")
    if series in {"UNRC", "UNJC"}:
        return "UNC"
    if series in {"UNRF", "UNJF"}:
        return "UNF"
    if series in {"UNREF", "UNJEF"}:
        return "UNEF"
    if series in {"UN", "UNC", "UNF", "UNEF", "UNS"}:
        return series
    return ""


def _normalize_pipe_series(value: Any) -> str:
    series = str(value or "").strip().upper().replace(" ", "")
    if series in {"NPS", "NPSM", "NPSL", "NPSC", "NPT", "G", "BSPP"}:
        return series
    return ""


def _profile_family_from_unified_series(series: str, fallback: str = "unified_un_v60") -> str:
    text = str(series or "").strip().upper()
    if text.startswith("UNJ"):
        return "unified_unj_v60"
    if text.startswith("UNR"):
        return "unified_unr_v60"
    return fallback


def normalize_thread_profile_family(value: Any) -> str:
    key = _normalize_key(value)
    if not key or key in {"metric", "metric_v60", "iso_metric", "iso_metric_v60"}:
        return "metric_v60"
    return UNIFIED_INCH_PROFILE_FAMILY_ALIASES.get(key, key)


def is_unified_inch_profile_family(value: Any) -> bool:
    return normalize_thread_profile_family(value) in {
        "unified_un_v60",
        "unified_unr_v60",
        "unified_unj_v60",
    }


def is_pipe_nps_profile_family(value: Any) -> bool:
    return normalize_thread_profile_family(value) == "pipe_nps_v60"


def is_pipe_npt_profile_family(value: Any) -> bool:
    return normalize_thread_profile_family(value) == "pipe_npt_v60"


def is_pipe_bsp_g_profile_family(value: Any) -> bool:
    return normalize_thread_profile_family(value) == "pipe_bsp_g_v55"


def is_pipe_thread_profile_family(value: Any) -> bool:
    return normalize_thread_profile_family(value) in {"pipe_nps_v60", "pipe_npt_v60", "pipe_bsp_g_v55"}


def parse_pipe_bsp_parallel_thread_designation(value: Any) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = (
        text.upper()
        .replace("″", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
        .replace("  ", " ")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip().replace('"', "")
    size_pattern = r"\d+(?:[ -]\d+/\d+)?|\d+/\d+|\d+(?:\.\d+)?"
    series_pattern = r"BSPP|G"

    match = re.fullmatch(
        rf"(?P<series>{series_pattern})\s*(?P<size>{size_pattern})(?:\s*-\s*(?P<tpi>\d+(?:\.\d+)?))?",
        normalized,
    )
    if match is None:
        match = re.fullmatch(
            rf"(?P<size>{size_pattern})\s*(?:-\s*(?P<tpi>\d+(?:\.\d+)?))?\s*(?P<series>{series_pattern})",
            normalized,
        )
    if match is None:
        return None

    size_token = _canonical_fractional_inch_token(match.group("size").replace(" ", "-"))
    entry = _PIPE_BSP_G_SIZE_TABLE.get(size_token)
    if entry is None:
        raise ValueError(f"unsupported BSP G nominal pipe size: {match.group('size')}")
    tpi = float(match.group("tpi") or entry["tpi"])
    if tpi <= 0.0:
        raise ValueError(f"invalid BSP G TPI in designation: {value}")
    return {
        "designation": normalized,
        "nominal_pipe_size": size_token,
        "nominal_pipe_size_inch": float(_parse_unified_size_inch(size_token)),
        "major_diameter_inch": float(entry["major_diameter_inch"]),
        "tpi": tpi,
        "thread_series": "G",
        "profile_family": "pipe_bsp_g_v55",
        "root_radius_policy": "whitworth_equal_rounding",
    }


def parse_pipe_straight_thread_designation(value: Any) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = (
        text.upper()
        .replace("вЂі", '"')
        .replace("вЂќ", '"')
        .replace("вЂ“", "-")
        .replace("вЂ”", "-")
        .replace("  ", " ")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip().replace('"', "")
    size_pattern = r"\d+(?:[ -]\d+/\d+)?|\d+/\d+|\d+(?:\.\d+)?"
    series_pattern = r"NPSC|NPSM|NPSL|NPS"

    match = re.fullmatch(
        rf"(?P<size>{size_pattern})\s*(?:-\s*(?P<tpi>\d+(?:\.\d+)?))?\s*(?P<series>{series_pattern})",
        normalized,
    )
    if match is None:
        match = re.fullmatch(
            rf"(?P<series>{series_pattern})\s*(?P<size>{size_pattern})(?:\s*-\s*(?P<tpi>\d+(?:\.\d+)?))?",
            normalized,
        )
    if match is None:
        return None

    size_token = _canonical_fractional_inch_token(match.group("size").replace(" ", "-"))
    entry = _PIPE_NPS_SIZE_TABLE.get(size_token)
    if entry is None:
        raise ValueError(f"unsupported NPS nominal pipe size: {match.group('size')}")
    tpi = float(match.group("tpi") or entry["tpi"])
    if tpi <= 0.0:
        raise ValueError(f"invalid NPS TPI in designation: {value}")
    series = _normalize_pipe_series(match.group("series")) or "NPS"
    return {
        "designation": normalized,
        "nominal_pipe_size": size_token,
        "nominal_pipe_size_inch": float(_parse_unified_size_inch(size_token)),
        "major_diameter_inch": float(entry["major_diameter_inch"]),
        "tpi": tpi,
        "thread_series": series,
        "profile_family": "pipe_nps_v60",
        "root_radius_policy": "pipe_flat_truncation",
    }


def parse_pipe_tapered_thread_designation(value: Any) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = (
        text.upper()
        .replace("РІР‚С–", '"')
        .replace("РІР‚Сњ", '"')
        .replace("РІР‚вЂњ", "-")
        .replace("РІР‚вЂќ", "-")
        .replace("  ", " ")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip().replace('"', "")
    size_pattern = r"\d+(?:[ -]\d+/\d+)?|\d+/\d+|\d+(?:\.\d+)?"

    match = re.fullmatch(
        rf"(?P<size>{size_pattern})\s*(?:-\s*(?P<tpi>\d+(?:\.\d+)?))?\s*NPT",
        normalized,
    )
    if match is None:
        match = re.fullmatch(
            rf"NPT\s*(?P<size>{size_pattern})(?:\s*-\s*(?P<tpi>\d+(?:\.\d+)?))?",
            normalized,
        )
    if match is None:
        return None

    size_token = _canonical_fractional_inch_token(match.group("size").replace(" ", "-"))
    entry = _PIPE_NPS_SIZE_TABLE.get(size_token)
    if entry is None:
        raise ValueError(f"unsupported NPT nominal pipe size: {match.group('size')}")
    tpi = float(match.group("tpi") or entry["tpi"])
    if tpi <= 0.0:
        raise ValueError(f"invalid NPT TPI in designation: {value}")
    return {
        "designation": normalized,
        "nominal_pipe_size": size_token,
        "nominal_pipe_size_inch": float(_parse_unified_size_inch(size_token)),
        "major_diameter_inch": float(entry["major_diameter_inch"]),
        "tpi": tpi,
        "thread_series": "NPT",
        "profile_family": "pipe_npt_v60",
        "root_radius_policy": "pipe_flat_truncation",
    }


def parse_unified_inch_thread_designation(value: Any) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = (
        text.upper()
        .replace("″", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
        .replace("  ", " ")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = normalized.replace('"', "")

    with_tpi = re.fullmatch(
        r"(?P<size>#?\d+|N(?:O\.)?\d+|\d+(?:[ -]\d+/\d+)?|\d+/\d+|\d+(?:\.\d+)?)"
        r"\s*-\s*(?P<tpi>\d+(?:\.\d+)?)\s*(?P<series>UNRC|UNRF|UNREF|UNJC|UNJF|UNJEF|UNC|UNF|UNEF|UNR|UNJ|UNS|UN)?",
        normalized,
    )
    if with_tpi:
        size_token = with_tpi.group("size").replace(" ", "-")
        raw_series = with_tpi.group("series") or "UN"
        major_diameter_inch = _parse_unified_size_inch(size_token)
        tpi = float(with_tpi.group("tpi"))
        if tpi <= 0.0:
            raise ValueError(f"invalid unified inch TPI in designation: {value}")
        thread_series = _normalize_unified_series(raw_series) or "UN"
        profile_family = _profile_family_from_unified_series(raw_series)
        return {
            "designation": normalized,
            "major_diameter_inch": major_diameter_inch,
            "tpi": tpi,
            "thread_series": thread_series,
            "profile_family": profile_family,
            "root_radius_policy": _root_radius_policy_for_family(profile_family),
        }

    by_series = re.fullmatch(
        r"(?P<size>#?\d+|N(?:O\.)?\d+|\d+(?:[ -]\d+/\d+)?|\d+/\d+|\d+(?:\.\d+)?)"
        r"\s+(?P<series>UNRC|UNRF|UNREF|UNJC|UNJF|UNJEF|UNC|UNF|UNEF)",
        normalized,
    )
    if by_series:
        size_token = by_series.group("size").replace(" ", "-")
        raw_series = by_series.group("series")
        thread_series = _normalize_unified_series(raw_series)
        canonical_size = _canonical_unified_size_token(size_token)
        tpi = (_UNIFIED_SERIES_TPI.get(thread_series) or {}).get(canonical_size)
        if tpi is None:
            raise ValueError(f"no built-in TPI for unified designation: {value}")
        profile_family = _profile_family_from_unified_series(raw_series)
        return {
            "designation": f"{normalized}",
            "major_diameter_inch": _parse_unified_size_inch(size_token),
            "tpi": float(tpi),
            "thread_series": thread_series,
            "profile_family": profile_family,
            "root_radius_policy": _root_radius_policy_for_family(profile_family),
        }

    return None


def _root_radius_policy_for_family(profile_family: str) -> str:
    family = normalize_thread_profile_family(profile_family)
    if family == "unified_unr_v60":
        return "unr_external_controlled"
    if family == "unified_unj_v60":
        return "unj_controlled"
    if family == "unified_un_v60":
        return "un"
    return "metric"


def build_v60_thread_geometry(
    diameter: float,
    pitch: float,
    *,
    profile_family: str = "metric_v60",
    source_units: str = "mm",
    major_diameter_inch: float | None = None,
    tpi: float | None = None,
    thread_series: str | None = None,
    designation: str | None = None,
) -> dict[str, float | str | None]:
    major_diameter = float(diameter)
    thread_pitch = float(pitch)
    if not math.isfinite(major_diameter) or major_diameter <= 0.0:
        raise ValueError("thread diameter must be positive")
    if not math.isfinite(thread_pitch) or thread_pitch <= 0.0:
        raise ValueError("thread pitch must be positive")

    family = normalize_thread_profile_family(profile_family)
    fundamental_height = V60_FUNDAMENTAL_HEIGHT_FACTOR * thread_pitch
    pitch_diameter = major_diameter - V60_PITCH_DIAMETER_FACTOR * thread_pitch
    internal_minor_diameter = major_diameter - V60_INTERNAL_MINOR_FACTOR * thread_pitch
    external_minor_diameter = major_diameter - V60_EXTERNAL_MINOR_FACTOR * thread_pitch
    return {
        "profile_family": family,
        "thread_series": _normalize_unified_series(thread_series) or None,
        "designation": str(designation or "") or None,
        "source_units": str(source_units or "mm"),
        "major_diameter": major_diameter,
        "pitch": thread_pitch,
        "major_diameter_inch": float(major_diameter_inch) if major_diameter_inch is not None else None,
        "tpi": float(tpi) if tpi is not None else None,
        "pitch_diameter": pitch_diameter,
        "internal_minor_diameter": internal_minor_diameter,
        "external_minor_diameter": external_minor_diameter,
        "major_radius": major_diameter / 2.0,
        "pitch_radius": pitch_diameter / 2.0,
        "internal_minor_radius": internal_minor_diameter / 2.0,
        "external_minor_radius": external_minor_diameter / 2.0,
        "fundamental_triangle_height": fundamental_height,
        "internal_thread_depth": (major_diameter - internal_minor_diameter) / 2.0,
        "external_thread_depth": (major_diameter - external_minor_diameter) / 2.0,
        "profile_angle_degrees": V60_THREAD_PROFILE_ANGLE_DEGREES,
        "root_radius_policy": _root_radius_policy_for_family(family),
        "profile_root_shape": "round",
    }


def build_metric_thread_geometry(diameter: float, pitch: float) -> dict[str, float]:
    geometry = build_v60_thread_geometry(diameter, pitch, profile_family="metric_v60")
    return {key: value for key, value in geometry.items() if isinstance(value, int | float)}


def build_unified_inch_thread_geometry(
    *,
    major_diameter_inch: float,
    tpi: float,
    thread_series: str | None = None,
    profile_family: str = "unified_un_v60",
    designation: str | None = None,
) -> dict[str, Any]:
    major_inch = float(major_diameter_inch)
    threads_per_inch = float(tpi)
    if not math.isfinite(major_inch) or major_inch <= 0.0:
        raise ValueError("major_diameter_inch must be positive")
    if not math.isfinite(threads_per_inch) or threads_per_inch <= 0.0:
        raise ValueError("tpi must be positive")
    return build_v60_thread_geometry(
        major_inch * INCH_TO_MM,
        INCH_TO_MM / threads_per_inch,
        profile_family=profile_family,
        source_units="inch",
        major_diameter_inch=major_inch,
        tpi=threads_per_inch,
        thread_series=thread_series,
        designation=designation,
    )


def build_pipe_straight_thread_geometry(
    *,
    nominal_pipe_size: str | None = None,
    major_diameter_inch: float | None = None,
    tpi: float | None = None,
    thread_series: str | None = "NPS",
    designation: str | None = None,
) -> dict[str, Any]:
    nominal_key = _canonical_fractional_inch_token(nominal_pipe_size)
    table_entry = _PIPE_NPS_SIZE_TABLE.get(nominal_key) if nominal_key else None
    major_inch = float(major_diameter_inch if major_diameter_inch is not None else (table_entry or {}).get("major_diameter_inch", 0.0))
    threads_per_inch = float(tpi if tpi is not None else (table_entry or {}).get("tpi", 0.0))
    if not math.isfinite(major_inch) or major_inch <= 0.0:
        raise ValueError("major_diameter_inch or supported nominal_pipe_size is required")
    if not math.isfinite(threads_per_inch) or threads_per_inch <= 0.0:
        raise ValueError("tpi must be positive")

    pitch = INCH_TO_MM / threads_per_inch
    major_diameter = major_inch * INCH_TO_MM
    fundamental_height = V60_FUNDAMENTAL_HEIGHT_FACTOR * pitch
    thread_height = PIPE_V60_THREAD_HEIGHT_FACTOR * pitch
    truncation_depth = max((fundamental_height - thread_height) / 2.0, 0.0)
    root_flat_width = 2.0 * truncation_depth * math.tan(math.radians(V60_THREAD_PROFILE_ANGLE_DEGREES / 2.0))
    minor_diameter = major_diameter - 2.0 * thread_height
    pitch_diameter = major_diameter - thread_height
    series = _normalize_pipe_series(thread_series) or "NPS"
    return {
        "profile_family": "pipe_nps_v60",
        "thread_series": series,
        "designation": str(designation or "") or None,
        "source_units": "inch",
        "nominal_pipe_size": nominal_key or None,
        "nominal_pipe_size_inch": float(_parse_unified_size_inch(nominal_key)) if nominal_key else None,
        "major_diameter": major_diameter,
        "pitch": pitch,
        "major_diameter_inch": major_inch,
        "tpi": threads_per_inch,
        "pitch_diameter": pitch_diameter,
        "internal_minor_diameter": minor_diameter,
        "external_minor_diameter": minor_diameter,
        "major_radius": major_diameter / 2.0,
        "pitch_radius": pitch_diameter / 2.0,
        "internal_minor_radius": minor_diameter / 2.0,
        "external_minor_radius": minor_diameter / 2.0,
        "fundamental_triangle_height": fundamental_height,
        "thread_height": thread_height,
        "internal_thread_depth": thread_height,
        "external_thread_depth": thread_height,
        "truncation_depth": truncation_depth,
        "root_flat_width": root_flat_width,
        "crest_flat_width": root_flat_width,
        "profile_angle_degrees": V60_THREAD_PROFILE_ANGLE_DEGREES,
        "root_radius_policy": "pipe_flat_truncation",
        "profile_root_shape": "flat",
    }


def build_pipe_tapered_thread_geometry(
    *,
    nominal_pipe_size: str | None = None,
    major_diameter_inch: float | None = None,
    tpi: float | None = None,
    designation: str | None = None,
) -> dict[str, Any]:
    geometry = build_pipe_straight_thread_geometry(
        nominal_pipe_size=nominal_pipe_size,
        major_diameter_inch=major_diameter_inch,
        tpi=tpi,
        thread_series="NPT",
        designation=designation,
    )
    geometry.update(
        {
            "profile_family": "pipe_npt_v60",
            "thread_series": "NPT",
            "carrier_shape": "conical",
            "taper_direction": "inward",
            "taper_diameter_ratio": PIPE_NPT_DIAMETER_TAPER_RATIO,
            "taper_radius_ratio": PIPE_NPT_RADIUS_TAPER_RATIO,
            "taper_half_angle_degrees": PIPE_NPT_TAPER_HALF_ANGLE_DEGREES,
        }
    )
    return geometry


def build_pipe_bsp_parallel_thread_geometry(
    *,
    nominal_pipe_size: str | None = None,
    major_diameter_inch: float | None = None,
    tpi: float | None = None,
    thread_series: str | None = "G",
    designation: str | None = None,
) -> dict[str, Any]:
    nominal_key = _canonical_fractional_inch_token(nominal_pipe_size)
    table_entry = _PIPE_BSP_G_SIZE_TABLE.get(nominal_key) if nominal_key else None
    major_inch = float(major_diameter_inch if major_diameter_inch is not None else (table_entry or {}).get("major_diameter_inch", 0.0))
    threads_per_inch = float(tpi if tpi is not None else (table_entry or {}).get("tpi", 0.0))
    if not math.isfinite(major_inch) or major_inch <= 0.0:
        raise ValueError("major_diameter_inch or supported nominal_pipe_size is required")
    if not math.isfinite(threads_per_inch) or threads_per_inch <= 0.0:
        raise ValueError("tpi must be positive")

    pitch = INCH_TO_MM / threads_per_inch
    major_diameter = major_inch * INCH_TO_MM
    fundamental_height = WHITWORTH_FUNDAMENTAL_HEIGHT_FACTOR * pitch
    thread_height = WHITWORTH_THREAD_DEPTH_FACTOR * pitch
    round_radius = WHITWORTH_ROUND_RADIUS_FACTOR * pitch
    minor_diameter = major_diameter - 2.0 * thread_height
    pitch_diameter = major_diameter - thread_height
    series = _normalize_pipe_series(thread_series) or "G"
    return {
        "profile_family": "pipe_bsp_g_v55",
        "thread_series": "G" if series == "BSPP" else series,
        "designation": str(designation or "") or None,
        "source_units": "inch",
        "nominal_pipe_size": nominal_key or None,
        "nominal_pipe_size_inch": float(_parse_unified_size_inch(nominal_key)) if nominal_key else None,
        "major_diameter": major_diameter,
        "pitch": pitch,
        "major_diameter_inch": major_inch,
        "tpi": threads_per_inch,
        "pitch_diameter": pitch_diameter,
        "internal_minor_diameter": minor_diameter,
        "external_minor_diameter": minor_diameter,
        "major_radius": major_diameter / 2.0,
        "pitch_radius": pitch_diameter / 2.0,
        "internal_minor_radius": minor_diameter / 2.0,
        "external_minor_radius": minor_diameter / 2.0,
        "fundamental_triangle_height": fundamental_height,
        "thread_height": thread_height,
        "internal_thread_depth": thread_height,
        "external_thread_depth": thread_height,
        "profile_angle_degrees": WHITWORTH_THREAD_PROFILE_ANGLE_DEGREES,
        "root_round_radius": round_radius,
        "crest_round_radius": round_radius,
        "root_radius_policy": "whitworth_equal_rounding",
        "profile_root_shape": "round",
    }


def describe_thread_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    description = {
        "profile_family": str(geometry.get("profile_family") or "metric_v60"),
        "thread_series": geometry.get("thread_series"),
        "designation": geometry.get("designation"),
        "source_units": str(geometry.get("source_units") or "mm"),
        "nominal_pipe_size": geometry.get("nominal_pipe_size"),
        "nominal_pipe_size_inch": geometry.get("nominal_pipe_size_inch"),
        "major_diameter": geometry["major_diameter"],
        "pitch": geometry["pitch"],
        "major_diameter_inch": geometry.get("major_diameter_inch"),
        "tpi": geometry.get("tpi"),
        "pitch_diameter": geometry["pitch_diameter"],
        "internal_minor_diameter": geometry["internal_minor_diameter"],
        "external_minor_diameter": geometry["external_minor_diameter"],
        "fundamental_triangle_height": geometry["fundamental_triangle_height"],
        "profile_angle_degrees": geometry["profile_angle_degrees"],
        "root_radius_policy": geometry.get("root_radius_policy"),
        "profile_root_shape": geometry.get("profile_root_shape"),
    }
    for key in (
        "thread_height",
        "truncation_depth",
        "root_flat_width",
        "crest_flat_width",
        "root_round_radius",
        "crest_round_radius",
        "carrier_shape",
        "taper_direction",
        "taper_diameter_ratio",
        "taper_radius_ratio",
        "taper_half_angle_degrees",
    ):
        if key in geometry:
            description[key] = geometry.get(key)
    return description


def describe_metric_thread_geometry(diameter: float, pitch: float) -> dict[str, Any]:
    geometry = build_v60_thread_geometry(diameter, pitch, profile_family="metric_v60")
    return describe_thread_geometry(geometry)


def resolve_thread_profile_geometry(
    params: dict[str, Any],
    *,
    diameter: float | None = None,
    pitch: float | None = None,
) -> dict[str, Any]:
    designation_value = params.get("designation") or params.get("thread_designation")
    parsed_unified = parse_unified_inch_thread_designation(designation_value)
    parsed_npt = parse_pipe_tapered_thread_designation(designation_value)
    parsed_bsp = parse_pipe_bsp_parallel_thread_designation(designation_value)
    parsed_pipe = parse_pipe_straight_thread_designation(designation_value)
    standard_family = normalize_thread_profile_family(params.get("thread_standard") or params.get("standard"))
    if standard_family not in {
        "metric_v60",
        "unified_un_v60",
        "unified_unr_v60",
        "unified_unj_v60",
        "pipe_nps_v60",
        "pipe_npt_v60",
        "pipe_bsp_g_v55",
    }:
        standard_family = ""
    profile_family = normalize_thread_profile_family(
        params.get("thread_profile_family")
        or params.get("profile_family")
        or params.get("thread_family")
        or standard_family
        or (parsed_unified or {}).get("profile_family")
        or (parsed_npt or {}).get("profile_family")
        or (parsed_bsp or {}).get("profile_family")
        or (parsed_pipe or {}).get("profile_family")
        or "metric_v60"
    )

    explicit_tpi = _optional_positive_float(params.get("tpi") or params.get("threads_per_inch"))
    explicit_major_inch = _optional_positive_float(
        params.get("major_diameter_inch")
        or params.get("diameter_inch")
        or params.get("nominal_diameter_inch")
        or params.get("d_inch")
    )
    explicit_size = params.get("unified_size") or params.get("inch_size")
    if explicit_size in (None, "") and not is_pipe_thread_profile_family(profile_family):
        explicit_size = params.get("nominal_size")
    if explicit_major_inch is None and explicit_size not in (None, "") and not is_pipe_thread_profile_family(profile_family):
        explicit_major_inch = _parse_unified_size_inch(explicit_size)
    if profile_family == "metric_v60" and explicit_major_inch is not None and explicit_tpi is not None:
        profile_family = "unified_un_v60"

    if parsed_npt is not None:
        geometry = build_pipe_tapered_thread_geometry(
            nominal_pipe_size=str(parsed_npt["nominal_pipe_size"]),
            tpi=float(parsed_npt["tpi"]),
            designation=str(parsed_npt.get("designation") or designation_value or ""),
        )
        return {
            "geometry": geometry,
            "profile_family": "pipe_npt_v60",
            "designation": str(parsed_npt.get("designation") or designation_value or ""),
            "thread_series": "NPT",
            "source_units": "inch",
            "resolved_from": "pipe_tapered_designation",
        }

    if parsed_pipe is not None:
        geometry = build_pipe_straight_thread_geometry(
            nominal_pipe_size=str(parsed_pipe["nominal_pipe_size"]),
            tpi=float(parsed_pipe["tpi"]),
            thread_series=str(parsed_pipe.get("thread_series") or "NPS"),
            designation=str(parsed_pipe.get("designation") or designation_value or ""),
        )
        return {
            "geometry": geometry,
            "profile_family": "pipe_nps_v60",
            "designation": str(parsed_pipe.get("designation") or designation_value or ""),
            "thread_series": str(parsed_pipe.get("thread_series") or "NPS"),
            "source_units": "inch",
            "resolved_from": "pipe_designation",
        }

    if parsed_bsp is not None:
        geometry = build_pipe_bsp_parallel_thread_geometry(
            nominal_pipe_size=str(parsed_bsp["nominal_pipe_size"]),
            tpi=float(parsed_bsp["tpi"]),
            thread_series=str(parsed_bsp.get("thread_series") or "G"),
            designation=str(parsed_bsp.get("designation") or designation_value or ""),
        )
        return {
            "geometry": geometry,
            "profile_family": "pipe_bsp_g_v55",
            "designation": str(parsed_bsp.get("designation") or designation_value or ""),
            "thread_series": str(parsed_bsp.get("thread_series") or "G"),
            "source_units": "inch",
            "resolved_from": "pipe_bsp_designation",
        }

    if parsed_unified is not None:
        profile_family = normalize_thread_profile_family(parsed_unified["profile_family"])
        geometry = build_unified_inch_thread_geometry(
            major_diameter_inch=float(parsed_unified["major_diameter_inch"]),
            tpi=float(parsed_unified["tpi"]),
            thread_series=str(parsed_unified.get("thread_series") or "UN"),
            profile_family=profile_family,
            designation=str(parsed_unified.get("designation") or designation_value or ""),
        )
        return {
            "geometry": geometry,
            "profile_family": profile_family,
            "designation": str(parsed_unified.get("designation") or designation_value or ""),
            "thread_series": str(parsed_unified.get("thread_series") or "UN"),
            "source_units": "inch",
            "resolved_from": "designation",
        }

    if is_unified_inch_profile_family(profile_family) and explicit_major_inch is not None and explicit_tpi is not None:
        thread_series = _normalize_unified_series(params.get("thread_series") or params.get("series")) or "UN"
        geometry = build_unified_inch_thread_geometry(
            major_diameter_inch=explicit_major_inch,
            tpi=explicit_tpi,
            thread_series=thread_series,
            profile_family=profile_family,
            designation=str(designation_value or ""),
        )
        return {
            "geometry": geometry,
            "profile_family": profile_family,
            "designation": str(designation_value or ""),
            "thread_series": thread_series,
            "source_units": "inch",
            "resolved_from": "inch_inputs",
        }

    explicit_pipe_size = (
        params.get("nominal_pipe_size")
        or params.get("nps_size")
        or params.get("pipe_size")
        or params.get("pipe_nominal_size")
        or params.get("nominal_size")
    )
    if is_pipe_thread_profile_family(profile_family) and (explicit_pipe_size not in (None, "") or explicit_major_inch is not None):
        thread_series = _normalize_pipe_series(params.get("thread_series") or params.get("series"))
        if is_pipe_npt_profile_family(profile_family):
            geometry = build_pipe_tapered_thread_geometry(
                nominal_pipe_size=str(explicit_pipe_size or ""),
                major_diameter_inch=explicit_major_inch,
                tpi=explicit_tpi,
                designation=str(designation_value or ""),
            )
            thread_series = "NPT"
            resolved_family = "pipe_npt_v60"
            resolved_from = "pipe_tapered_inputs"
        elif is_pipe_bsp_g_profile_family(profile_family):
            geometry = build_pipe_bsp_parallel_thread_geometry(
                nominal_pipe_size=str(explicit_pipe_size or ""),
                major_diameter_inch=explicit_major_inch,
                tpi=explicit_tpi,
                thread_series=thread_series or "G",
                designation=str(designation_value or ""),
            )
            thread_series = "G"
            resolved_family = "pipe_bsp_g_v55"
            resolved_from = "pipe_bsp_inputs"
        else:
            thread_series = thread_series or "NPS"
            geometry = build_pipe_straight_thread_geometry(
                nominal_pipe_size=str(explicit_pipe_size or ""),
                major_diameter_inch=explicit_major_inch,
                tpi=explicit_tpi,
                thread_series=thread_series,
                designation=str(designation_value or ""),
            )
            resolved_family = "pipe_nps_v60"
            resolved_from = "pipe_inputs"
        return {
            "geometry": geometry,
            "profile_family": resolved_family,
            "designation": str(designation_value or ""),
            "thread_series": thread_series,
            "source_units": "inch",
            "resolved_from": resolved_from,
        }

    if diameter is None or pitch is None:
        raise ValueError("thread profile requires diameter/pitch or an inch designation/TPI input")
    geometry = build_v60_thread_geometry(
        float(diameter),
        float(pitch),
        profile_family=profile_family,
        designation=str(designation_value or ""),
        thread_series=_normalize_unified_series(params.get("thread_series") or params.get("series")) or None,
    )
    return {
        "geometry": geometry,
        "profile_family": profile_family,
        "designation": str(designation_value or ""),
        "thread_series": geometry.get("thread_series"),
        "source_units": "mm",
        "resolved_from": "metric_inputs" if profile_family == "metric_v60" else "mm_inputs",
    }
