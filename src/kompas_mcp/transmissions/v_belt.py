from __future__ import annotations

from copy import deepcopy
import math
from typing import Any


_SOURCE = {
    "document": "Optibelt Technical Manual: V-Belt Drives",
    "table": "Groove dimensions according to DIN 2211",
    "contextual_standard_references": ["DIN 2217", "ISO 4183"],
    "printed_page": 49,
    "pdf_page": 51,
    "url": "https://a.storyblok.com/f/192292/x/6c78e81d5a/optibelt-tm-v-belt-drives.pdf",
    "retrieved": "2026-07-26",
    "evidence_level": "manufacturer_reference",
    "certified_use": "Verify against the licensed edition of the applicable standard.",
}


def _angle_rules(first_angle: float, threshold: float) -> list[dict[str, float | None]]:
    return [
        {"angle_degrees": first_angle, "max_datum_diameter": threshold},
        {"angle_degrees": 38.0, "max_datum_diameter": None},
    ]


_COMMON_GEOMETRY: dict[str, dict[str, Any]] = {
    "Z": {
        "datum_width": 8.5,
        "approximate_top_width": 9.7,
        "datum_offset": 2.0,
        "groove_pitch": 12.0,
        "edge_distance": 8.0,
        "minimum_groove_depth": 11.0,
        "angle_rules": _angle_rules(34.0, 80.0),
        "angle_tolerance_degrees": 1.0,
    },
    "A": {
        "datum_width": 11.0,
        "approximate_top_width": 12.7,
        "datum_offset": 2.8,
        "groove_pitch": 15.0,
        "edge_distance": 10.0,
        "minimum_groove_depth": 14.0,
        "angle_rules": _angle_rules(34.0, 118.0),
        "angle_tolerance_degrees": 1.0,
    },
    "B": {
        "datum_width": 14.0,
        "approximate_top_width": 16.3,
        "datum_offset": 3.5,
        "groove_pitch": 19.0,
        "edge_distance": 12.5,
        "minimum_groove_depth": 18.0,
        "angle_rules": _angle_rules(34.0, 190.0),
        "angle_tolerance_degrees": 1.0,
    },
    "C": {
        "datum_width": 19.0,
        "approximate_top_width": 22.0,
        "datum_offset": 4.8,
        "groove_pitch": 25.5,
        "edge_distance": 17.0,
        "minimum_groove_depth": 24.0,
        "angle_rules": _angle_rules(34.0, 315.0),
        "angle_tolerance_degrees": 0.5,
    },
    "D": {
        "datum_width": 27.0,
        "approximate_top_width": 32.0,
        "datum_offset": 8.1,
        "groove_pitch": 37.0,
        "edge_distance": 24.0,
        "minimum_groove_depth": 28.0,
        "angle_rules": _angle_rules(36.0, 500.0),
        "angle_tolerance_degrees": 0.5,
    },
    "E": {
        "datum_width": 32.0,
        "approximate_top_width": 40.0,
        "datum_offset": 12.0,
        "groove_pitch": 44.5,
        "edge_distance": 29.0,
        "minimum_groove_depth": 33.0,
        "angle_rules": _angle_rules(36.0, 630.0),
        "angle_tolerance_degrees": 0.5,
    },
}


_PROFILE_ROWS = (
    ("Z", "classical", "Z", 50.0, "SPZ"),
    ("A", "classical", "A", 71.0, "SPA"),
    ("B", "classical", "B", 112.0, "SPB"),
    ("C", "classical", "C", 180.0, "SPC"),
    ("D", "classical", "D", 355.0, None),
    ("E", "classical", "E", 500.0, None),
    ("SPZ", "narrow_wedge", "Z", 63.0, "Z"),
    ("SPA", "narrow_wedge", "A", 90.0, "A"),
    ("SPB", "narrow_wedge", "B", 140.0, "B"),
    ("SPC", "narrow_wedge", "C", 224.0, "C"),
)


_PROFILES: dict[str, dict[str, Any]] = {}
for designation, family, geometry_key, minimum_diameter, dual_profile in _PROFILE_ROWS:
    _PROFILES[designation] = {
        "designation": designation,
        "family": family,
        "geometry_key": geometry_key,
        "dual_duty_profile": dual_profile,
        "minimum_datum_diameter": minimum_diameter,
        **deepcopy(_COMMON_GEOMETRY[geometry_key]),
        "source": deepcopy(_SOURCE),
    }


_CUSTOM_REQUIRED_FIELDS = (
    "datum_width",
    "datum_offset",
    "groove_pitch",
    "edge_distance",
    "groove_depth",
    "groove_angle_degrees",
)


_OVERRIDE_FIELDS = {
    "datum_width",
    "approximate_top_width",
    "datum_offset",
    "groove_pitch",
    "edge_distance",
    "groove_depth",
    "groove_angle_degrees",
}


def list_v_belt_profiles(family: str | None = None) -> dict[str, Any]:
    normalized_family = None
    if family is not None:
        normalized_family = str(family).strip().lower()
        if normalized_family not in {"classical", "narrow_wedge"}:
            raise ValueError("family must be 'classical' or 'narrow_wedge'")

    profiles = [
        deepcopy(profile)
        for profile in _PROFILES.values()
        if normalized_family is None or profile["family"] == normalized_family
    ]
    profiles.sort(key=lambda item: (item["family"], item["minimum_datum_diameter"]))
    return {
        "ok": True,
        "stage": "v_belt_profile_catalog",
        "family": normalized_family,
        "profile_count": len(profiles),
        "profiles": profiles,
        "source": deepcopy(_SOURCE),
    }


def resolve_v_belt_profile(
    designation: str,
    datum_diameter: float | None = None,
) -> dict[str, Any]:
    key = str(designation or "").strip().upper()
    if key not in _PROFILES:
        supported = ", ".join(_PROFILES)
        raise ValueError(f"Unknown V-belt profile '{designation}'. Supported profiles: {supported}")

    profile = deepcopy(_PROFILES[key])
    profile["profile_mode"] = "catalog"
    profile["groove_depth"] = float(profile["minimum_groove_depth"])
    if datum_diameter is None:
        profile["groove_angle_degrees"] = None
        profile["datum_diameter"] = None
        return profile

    diameter = _positive_float("datum_diameter", datum_diameter)
    minimum = float(profile["minimum_datum_diameter"])
    if diameter + 1e-9 < minimum:
        raise ValueError(
            f"datum_diameter={diameter:g} mm is below the {key} catalog minimum {minimum:g} mm"
        )
    profile["datum_diameter"] = diameter
    profile["groove_angle_degrees"] = _resolve_angle(profile["angle_rules"], diameter)
    return profile


def preview_v_belt_groove(
    designation: str,
    datum_diameter: float,
    groove_count: int = 1,
    profile_overrides: dict[str, Any] | None = None,
    custom_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diameter = _positive_float("datum_diameter", datum_diameter)
    count = _positive_int("groove_count", groove_count, maximum=64)
    key = str(designation or "").strip().upper()

    if key == "CUSTOM":
        profile = _normalize_custom_profile(custom_profile, diameter)
    else:
        if custom_profile is not None:
            raise ValueError("custom_profile is only allowed when designation='CUSTOM'")
        profile = resolve_v_belt_profile(key, diameter)

    overrides = dict(profile_overrides or {})
    unknown_overrides = sorted(set(overrides) - _OVERRIDE_FIELDS)
    if unknown_overrides:
        raise ValueError(f"Unsupported profile_overrides: {', '.join(unknown_overrides)}")
    if overrides:
        _apply_overrides(profile, overrides)
        profile["profile_mode"] = "catalog_with_overrides" if key != "CUSTOM" else "custom"

    angle = _positive_float("groove_angle_degrees", profile["groove_angle_degrees"])
    if angle >= 90.0:
        raise ValueError("groove_angle_degrees must be less than 90")
    datum_width = _positive_float("datum_width", profile["datum_width"])
    datum_offset = _positive_float("datum_offset", profile["datum_offset"], allow_zero=True)
    groove_depth = _positive_float("groove_depth", profile["groove_depth"])
    if groove_depth <= datum_offset:
        raise ValueError("groove_depth must be greater than datum_offset")
    groove_pitch = _positive_float("groove_pitch", profile["groove_pitch"])
    edge_distance = _positive_float("edge_distance", profile["edge_distance"])

    tangent = math.tan(math.radians(angle / 2.0))
    top_width = datum_width + 2.0 * datum_offset * tangent
    approximate_top_width = _positive_float(
        "approximate_top_width",
        profile.get("approximate_top_width", top_width),
        allow_zero=True,
    )
    root_half_width = datum_width / 2.0 - (groove_depth - datum_offset) * tangent
    if root_half_width <= 0.0:
        raise ValueError(
            "The selected groove angle/depth closes the groove before the catalog root depth; "
            "reduce groove_depth or angle, or increase datum_width"
        )

    datum_radius = diameter / 2.0
    outer_radius = datum_radius + datum_offset
    root_radius = outer_radius - groove_depth
    if root_radius <= 0.0:
        raise ValueError("groove_depth produces a non-positive root radius")

    face_width = (count - 1) * groove_pitch + 2.0 * edge_distance
    first_center = -((count - 1) * groove_pitch) / 2.0
    centers = [first_center + index * groove_pitch for index in range(count)]
    grooves = [
        _build_groove_geometry(
            index=index,
            center_x=center,
            outer_radius=outer_radius,
            datum_radius=datum_radius,
            root_radius=root_radius,
            top_width=top_width,
            datum_width=datum_width,
            root_half_width=root_half_width,
        )
        for index, center in enumerate(centers)
    ]

    left_edge = -face_width / 2.0
    right_edge = face_width / 2.0
    top_segments: list[dict[str, list[float]]] = []
    cursor = left_edge
    for groove in grooves:
        groove_left = groove["cut_polygon"][0][0]
        if groove_left > cursor + 1e-9:
            top_segments.append({"start": [cursor, outer_radius], "end": [groove_left, outer_radius]})
        cursor = groove["cut_polygon"][3][0]
    if right_edge > cursor + 1e-9:
        top_segments.append({"start": [cursor, outer_radius], "end": [right_edge, outer_radius]})

    assumptions = [
        {
            "field": "groove_dimensions",
            "status": profile["profile_mode"],
            "source": "custom_profile" if key == "CUSTOM" else _SOURCE["document"],
        },
        {
            "field": "groove_angle_degrees",
            "value": angle,
            "status": "catalog_rule" if "groove_angle_degrees" not in overrides else "user_override",
        },
    ]

    warnings = [
        "Stage A models the nominal straight-sided groove with a flat root; root and outer-edge rounding are not included.",
        "Manufacturer reference data must be checked against the licensed standard edition for certified drawings.",
    ]
    if overrides:
        warnings.append("Profile overrides make this a non-catalog geometry preview.")

    return {
        "ok": True,
        "success": True,
        "stage": "preview",
        "operation": "v_belt_groove",
        "inputs": {
            "designation": key,
            "datum_diameter": diameter,
            "groove_count": count,
            "profile_overrides": deepcopy(overrides),
        },
        "profile": profile,
        "derived": {
            "groove_angle_degrees": angle,
            "datum_diameter": diameter,
            "outer_diameter": outer_radius * 2.0,
            "root_diameter": root_radius * 2.0,
            "face_width": face_width,
            "actual_top_width": top_width,
            "catalog_approximate_top_width": approximate_top_width,
            "top_width_delta_from_catalog_approximation": top_width - approximate_top_width,
            "root_flat_width": root_half_width * 2.0,
            "groove_centers": centers,
        },
        "geometry": {
            "coordinate_system": {"x": "axial", "y": "radius"},
            "grooves": grooves,
            "outer_surface_segments": top_segments,
            "envelope": {
                "x_min": left_edge,
                "x_max": right_edge,
                "radius_min": root_radius,
                "radius_max": outer_radius,
            },
        },
        "composition": {
            "contract_status": "planned_for_cad_builder",
            "preferred_mode": "cut_from_body",
            "target_requirements": {
                "axis_ref": "required",
                "outer_cylinder_diameter": outer_radius * 2.0,
                "minimum_axial_width": face_width,
                "preserve_material_below_radius": root_radius,
            },
            "planned_semantic_outputs": [
                "member.body",
                "member.axis",
                "member.left_face",
                "member.right_face",
                "member.outer_rim",
                "member.pitch_surface",
                "member.functional_feature",
            ],
            "excluded_features": ["hub", "bore", "keyway", "thread", "generic_chamfers"],
        },
        "assumptions": assumptions,
        "warnings": warnings,
        "source": deepcopy(profile.get("source") or {"evidence_level": "user_supplied"}),
    }


def _normalize_custom_profile(profile: dict[str, Any] | None, datum_diameter: float) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise ValueError("custom_profile is required when designation='CUSTOM'")
    missing = [field for field in _CUSTOM_REQUIRED_FIELDS if field not in profile]
    if missing:
        raise ValueError(f"custom_profile is missing required fields: {', '.join(missing)}")
    normalized = {
        "designation": str(profile.get("designation") or "CUSTOM").strip() or "CUSTOM",
        "family": str(profile.get("family") or "custom").strip() or "custom",
        "profile_mode": "custom",
        "datum_width": _positive_float("datum_width", profile["datum_width"]),
        "approximate_top_width": _positive_float(
            "approximate_top_width", profile.get("approximate_top_width", 0.0), allow_zero=True
        ),
        "datum_offset": _positive_float("datum_offset", profile["datum_offset"], allow_zero=True),
        "groove_pitch": _positive_float("groove_pitch", profile["groove_pitch"]),
        "edge_distance": _positive_float("edge_distance", profile["edge_distance"]),
        "groove_depth": _positive_float("groove_depth", profile["groove_depth"]),
        "groove_angle_degrees": _positive_float(
            "groove_angle_degrees", profile["groove_angle_degrees"]
        ),
        "minimum_datum_diameter": _positive_float(
            "minimum_datum_diameter", profile.get("minimum_datum_diameter", 0.0), allow_zero=True
        ),
        "datum_diameter": datum_diameter,
        "source": deepcopy(profile.get("source") or {"evidence_level": "user_supplied"}),
    }
    if datum_diameter + 1e-9 < normalized["minimum_datum_diameter"]:
        raise ValueError(
            f"datum_diameter={datum_diameter:g} mm is below the custom minimum "
            f"{normalized['minimum_datum_diameter']:g} mm"
        )
    return normalized


def _apply_overrides(profile: dict[str, Any], overrides: dict[str, Any]) -> None:
    for field, raw_value in overrides.items():
        allow_zero = field in {"datum_offset", "approximate_top_width"}
        value = _positive_float(field, raw_value, allow_zero=allow_zero)
        if field == "groove_depth":
            profile["groove_depth"] = value
        else:
            profile[field] = value


def _resolve_angle(rules: list[dict[str, float | None]], diameter: float) -> float:
    for rule in rules:
        maximum = rule["max_datum_diameter"]
        if maximum is None or diameter <= float(maximum) + 1e-9:
            return float(rule["angle_degrees"])
    raise RuntimeError("V-belt profile has no terminal groove-angle rule")


def _build_groove_geometry(
    *,
    index: int,
    center_x: float,
    outer_radius: float,
    datum_radius: float,
    root_radius: float,
    top_width: float,
    datum_width: float,
    root_half_width: float,
) -> dict[str, Any]:
    top_half = top_width / 2.0
    datum_half = datum_width / 2.0
    polygon = [
        [center_x - top_half, outer_radius],
        [center_x - root_half_width, root_radius],
        [center_x + root_half_width, root_radius],
        [center_x + top_half, outer_radius],
    ]
    return {
        "index": index,
        "center_x": center_x,
        "cut_polygon": polygon,
        "closed_cut_polygon": [*polygon, polygon[0]],
        "datum_points": [
            [center_x - datum_half, datum_radius],
            [center_x + datum_half, datum_radius],
        ],
    }


def _positive_float(name: str, value: Any, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    if allow_zero:
        if number < 0.0:
            raise ValueError(f"{name} must be >= 0")
    elif number <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return number


def _positive_int(name: str, value: Any, *, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if number != value or number <= 0 or number > maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return number
