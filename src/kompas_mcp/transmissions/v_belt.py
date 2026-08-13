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

_GOST_SOURCE = {
    "document": "GOST 20889-88",
    "title": "Pulleys for classical-section drive V-belts. General specifications",
    "clauses": ["2.1", "2.4", "Table 1", "Table 2", "Drawing 10"],
    "url": "https://allgosts.ru/21/220/gost_20889-88",
    "evidence_level": "primary_standard_reproduction",
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
        "standard_system": "din_iso",
        "standard_top_edge_radius": None,
        "family": family,
        "geometry_key": geometry_key,
        "dual_duty_profile": dual_profile,
        "minimum_datum_diameter": minimum_diameter,
        **deepcopy(_COMMON_GEOMETRY[geometry_key]),
        "source": deepcopy(_SOURCE),
    }


_STANDARD_ALIASES = {
    "DIN": "din_iso",
    "DIN_ISO": "din_iso",
    "DIN/ISO": "din_iso",
    "ISO": "din_iso",
    "ISO_4183": "din_iso",
    "GOST": "gost_20889_88",
    "ГОСТ": "gost_20889_88",
    "GOST_20889_88": "gost_20889_88",
    "ГОСТ_20889_88": "gost_20889_88",
}

_GOST_GEOMETRY = {
    "Z": (8.5, 2.5, 12.0, 8.0, 9.5, 0.5),
    "A": (11.0, 3.3, 15.0, 10.0, 12.0, 1.0),
    "B": (14.0, 4.2, 19.0, 12.5, 15.0, 1.0),
    "C": (19.0, 5.7, 25.5, 17.0, 20.0, 1.5),
    "D": (27.0, 8.1, 37.0, 24.0, 28.0, 2.0),
    "E": (32.0, 9.6, 44.5, 29.0, 33.0, 2.0),
}

_GOST_PROFILE_ROWS = (
    ("Z", ((50.0, 71.0, 34.0), (80.0, 100.0, 36.0), (112.0, 160.0, 38.0), (180.0, None, 40.0))),
    ("A", ((75.0, 112.0, 34.0), (125.0, 160.0, 36.0), (180.0, 400.0, 38.0), (450.0, None, 40.0))),
    ("B", ((125.0, 160.0, 34.0), (180.0, 224.0, 36.0), (250.0, 500.0, 38.0), (560.0, None, 40.0))),
    ("C", ((200.0, 315.0, 36.0), (355.0, 630.0, 38.0), (710.0, None, 40.0))),
    ("D", ((315.0, 450.0, 36.0), (500.0, 900.0, 38.0), (1000.0, None, 40.0))),
    ("E", ((500.0, 560.0, 36.0), (630.0, 1120.0, 38.0), (1250.0, None, 40.0))),
)

_GOST_PROFILES: dict[str, dict[str, Any]] = {}
for designation, angle_rules in _GOST_PROFILE_ROWS:
    datum_width, datum_offset, groove_pitch, edge_distance, groove_depth, top_radius = _GOST_GEOMETRY[
        designation
    ]
    _GOST_PROFILES[designation] = {
        "designation": designation,
        "standard_system": "gost_20889_88",
        "standard_top_edge_radius": top_radius,
        "family": "classical",
        "geometry_key": designation,
        "dual_duty_profile": None,
        "minimum_datum_diameter": angle_rules[0][0],
        "datum_width": datum_width,
        "approximate_top_width": None,
        "datum_offset": datum_offset,
        "groove_pitch": groove_pitch,
        "edge_distance": edge_distance,
        "minimum_groove_depth": groove_depth,
        "angle_rules": [
            {
                "min_datum_diameter": minimum,
                "max_datum_diameter": maximum,
                "angle_degrees": angle,
            }
            for minimum, maximum, angle in angle_rules
        ],
        "angle_tolerance_degrees": 0.5 if designation in {"C", "D", "E"} else 1.0,
        "source": deepcopy(_GOST_SOURCE),
    }

_PROFILE_CATALOGS = {
    "din_iso": _PROFILES,
    "gost_20889_88": _GOST_PROFILES,
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
    "standard_top_edge_radius",
}


def _normalize_standard_system(value: str | None) -> str:
    raw = str(value or "din_iso").strip()
    key = raw.upper().replace("-", "_").replace(" ", "_")
    normalized = _STANDARD_ALIASES.get(key, raw.lower())
    if normalized not in _PROFILE_CATALOGS:
        supported = ", ".join(sorted(_PROFILE_CATALOGS))
        raise ValueError(f"Unknown V-belt standard_system '{value}'. Supported standards: {supported}")
    return normalized


def list_v_belt_profiles(
    family: str | None = None,
    standard_system: str = "din_iso",
) -> dict[str, Any]:
    normalized_standard = _normalize_standard_system(standard_system)
    normalized_family = None
    if family is not None:
        normalized_family = str(family).strip().lower()
        if normalized_family not in {"classical", "narrow_wedge"}:
            raise ValueError("family must be 'classical' or 'narrow_wedge'")

    profiles = [
        deepcopy(profile)
        for profile in _PROFILE_CATALOGS[normalized_standard].values()
        if normalized_family is None or profile["family"] == normalized_family
    ]
    profiles.sort(key=lambda item: (item["family"], item["minimum_datum_diameter"]))
    return {
        "ok": True,
        "stage": "v_belt_profile_catalog",
        "standard_system": normalized_standard,
        "available_standard_systems": sorted(_PROFILE_CATALOGS),
        "family": normalized_family,
        "profile_count": len(profiles),
        "profiles": profiles,
        "source": deepcopy(_GOST_SOURCE if normalized_standard == "gost_20889_88" else _SOURCE),
    }


def resolve_v_belt_profile(
    designation: str,
    datum_diameter: float | None = None,
    standard_system: str = "din_iso",
) -> dict[str, Any]:
    normalized_standard = _normalize_standard_system(standard_system)
    catalog = _PROFILE_CATALOGS[normalized_standard]
    key = str(designation or "").strip().upper()
    if key not in catalog:
        supported = ", ".join(catalog)
        raise ValueError(
            f"Unknown V-belt profile '{designation}' for standard_system={normalized_standard}. "
            f"Supported profiles: {supported}"
        )

    profile = deepcopy(catalog[key])
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
    standard_system: str = "din_iso",
) -> dict[str, Any]:
    diameter = _positive_float("datum_diameter", datum_diameter)
    count = _positive_int("groove_count", groove_count, maximum=64)
    key = str(designation or "").strip().upper()
    normalized_standard = _normalize_standard_system(standard_system)

    if key == "CUSTOM":
        profile = _normalize_custom_profile(custom_profile, diameter)
        profile["standard_system"] = "custom"
    else:
        if custom_profile is not None:
            raise ValueError("custom_profile is only allowed when designation='CUSTOM'")
        profile = resolve_v_belt_profile(key, diameter, standard_system=normalized_standard)

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
    approximate_raw = profile.get("approximate_top_width")
    approximate_top_width = (
        top_width
        if approximate_raw is None
        else _positive_float("approximate_top_width", approximate_raw, allow_zero=True)
    )
    root_half_width = datum_width / 2.0 - (groove_depth - datum_offset) * tangent
    if root_half_width <= 0.0:
        raise ValueError(
            "The selected groove angle/depth closes the groove before the catalog root depth; "
            "reduce groove_depth or angle, or increase datum_width"
        )
    if edge_distance < top_width / 2.0 - 1e-9:
        raise ValueError("edge_distance must contain half of the actual groove top width")
    if count > 1 and groove_pitch <= top_width + 1e-9:
        raise ValueError("groove_pitch must exceed the actual groove top width")

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
            "source": "custom_profile" if key == "CUSTOM" else profile["source"]["document"],
        },
        {
            "field": "groove_angle_degrees",
            "value": angle,
            "status": "catalog_rule" if "groove_angle_degrees" not in overrides else "user_override",
        },
    ]

    standard_top_edge_radius = profile.get("standard_top_edge_radius")
    warnings = [
        (
            "The functional cut profile remains straight-sided with a flat root; "
            "the upper-edge radius R=%g mm is applied as a separate Layer 3 post-cut fillet."
            % float(standard_top_edge_radius)
        )
        if isinstance(standard_top_edge_radius, (int, float))
        else "The functional cut profile is straight-sided with a flat root; this profile has no configured upper-edge fillet."
    ]
    evidence_level = str(profile.get("source", {}).get("evidence_level") or "")
    if evidence_level == "manufacturer_reference":
        warnings.append(
            "Manufacturer reference data must be checked against the licensed standard edition for certified drawings."
        )
    elif key == "CUSTOM":
        warnings.append("Custom profile geometry is user-supplied and is not certified against a standard catalog.")
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
            "standard_system": profile.get("standard_system", normalized_standard),
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
            "contract_status": "implemented_layer_3",
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


def _build_v_belt_parameterization_plan_legacy(
    preview: dict[str, Any],
    shifted_polygons: list[list[list[float]]],
    *,
    axial_center: float,
    axis: dict[str, Any],
) -> dict[str, Any]:
    derived = dict(preview.get("derived") or {})
    resolved = dict(preview.get("profile") or {})
    datum_diameter = float(derived["datum_diameter"])
    outer_radius = float(derived["outer_diameter"]) / 2.0
    root_radius = float(derived["root_diameter"]) / 2.0
    groove_angle = float(derived["groove_angle_degrees"])
    root_width = float(derived["root_flat_width"])
    variables: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = [
        {"kind": "fixed_point", "target": "axis", "index": 0},
        {"kind": "fixed_point", "target": "axis", "index": 1},
    ]
    dimensions: list[dict[str, Any]] = []
    construction_lines: list[dict[str, Any]] = []

    def add_variable(
        variable_name: str,
        value: float,
        *,
        expression: str | None = None,
        unit: str = "mm",
        note: str,
    ) -> None:
        variables.append(
            {
                "name": variable_name,
                "value": float(value),
                "expression": expression,
                "unit": unit,
                "note": note,
            }
        )

    def add_driving_dimension(
        dimension_name: str,
        value: float,
        expression: str,
        payload: dict[str, Any],
        *,
        unit: str = "mm",
        note: str,
    ) -> None:
        dimensions.append(
            {
                **payload,
                "name": dimension_name,
                "value": abs(float(value)),
                "expression": expression,
                "driving": True,
            }
        )

    def point_connection(
        target: str,
        target_index: int,
        partner: str,
        partner_index: int,
    ) -> list[dict[str, Any]]:
        return [
            {"kind": "point_on_curve", "target": target, "index": target_index, "partner": partner},
            {"kind": "point_on_curve", "target": partner, "index": partner_index, "partner": target},
        ]

    add_variable("VB_DD", datum_diameter, note="Datum diameter")
    add_variable("VB_OD", derived["outer_diameter"], note="Outer diameter")
    add_variable("VB_DEPTH", resolved["groove_depth"], note="Groove radial depth")
    add_variable("VB_TOP_W", derived["actual_top_width"], note="Actual groove top width")
    add_variable(
        "VB_ROOT_W",
        root_width,
        expression="VB_TOP_W - 2 * VB_DEPTH * tanD(VB_ANGLE / 2)",
        note="Groove root width",
    )
    add_variable("VB_DATUM_W", resolved["datum_width"], note="Catalog datum width")
    add_variable("VB_PITCH", resolved["groove_pitch"], note="Groove center pitch")
    add_variable("VB_EDGE", resolved["edge_distance"], note="Face edge distance")
    add_variable("VB_FACE_W", derived["face_width"], note="Pulley face width")
    add_variable("VB_CENTER", axial_center, note="Groove-set axial center")
    add_variable("VB_ANGLE", groove_angle, unit="deg", note="Included groove angle")
    add_variable("VB_COUNT", preview["inputs"]["groove_count"], unit="", note="Groove count")
    add_variable("VB_AXIS_X0", axis["start"][0], note="Rotation-axis construction start")
    add_variable(
        "VB_OR",
        outer_radius,
        expression="VB_OD / 2",
        note="Outer radius",
    )
    add_variable(
        "VB_RR",
        root_radius,
        expression="VB_OR - VB_DEPTH",
        note="Groove root radius",
    )

    groove_count = len(shifted_polygons)
    for groove_index, polygon in enumerate(shifted_polygons, start=1):
        top_left, root_left, root_right, top_right = polygon
        center_x = (float(top_left[0]) + float(top_right[0])) / 2.0
        prefix = "VB_G%s" % groove_index
        center_var = prefix + "_CX"
        center_factor = groove_index - 1 - (groove_count - 1) / 2.0
        center_expression = (
            "VB_CENTER"
            if groove_count == 1
            else "VB_CENTER + (%s) * VB_PITCH" % ("%.12g" % center_factor)
        )
        add_variable(
            center_var,
            center_x,
            expression=center_expression,
            note="Groove %s axial center" % groove_index,
        )

        centerline_id = "groove_%s_centerline" % groove_index
        axis_locator_id = "groove_%s_axis_locator" % groove_index
        top_locator_id = "groove_%s_top_locator" % groove_index
        construction_specs = [
            {
                    "id": centerline_id,
                    "target": centerline_id,
                    "start": [center_x, 0.0],
                    "end": [center_x, float(top_left[1])],
                    "style": 2,
                    "role": "groove_centerline",
                },
            {
                    "id": axis_locator_id,
                    "target": axis_locator_id,
                    "start": [float(axis["start"][0]), 0.0],
                    "end": [center_x, 0.0],
                    "style": 2,
                    "role": "groove_axis_locator",
                },
            {
                    "id": top_locator_id,
                    "target": top_locator_id,
                    "start": [float(top_left[0]), float(top_left[1])],
                    "end": [center_x, float(top_left[1])],
                    "style": 2,
                    "role": "groove_top_locator",
                },
        ]
        for construction_spec in construction_specs:
            initial_shift = 0.5 * (len(construction_lines) + 1)
            construction_spec["start"][0] += initial_shift
            construction_spec["end"][0] += initial_shift
            if construction_spec["role"] == "groove_axis_locator":
                construction_spec["start"][0] = float(axis["start"][0])
            construction_spec["initial_merge_offset"] = initial_shift
            construction_lines.append(construction_spec)
        edge_ids = ["groove_%s_side_%s" % (groove_index, side_index) for side_index in range(1, 5)]
        groove_constraints: list[dict[str, Any]] = [
                {"kind": "parallel", "target": edge_ids[1], "partner": "axis"},
                {"kind": "horizontal", "target": edge_ids[3]},
                {"kind": "vertical", "target": centerline_id},
                {"kind": "perpendicular", "target": edge_ids[1], "partner": centerline_id},
                {"kind": "horizontal", "target": axis_locator_id},
                {"kind": "horizontal", "target": top_locator_id},
                {"kind": "fixed_point", "target": axis_locator_id, "index": 0},
        ]
        groove_constraints.extend(point_connection(edge_ids[0], 1, edge_ids[1], 0))
        groove_constraints.append(
            {"kind": "point_on_curve", "target": edge_ids[1], "index": 1, "partner": edge_ids[2]}
        )
        groove_constraints.append(
            {"kind": "point_on_curve", "target": edge_ids[2], "index": 0, "partner": edge_ids[1]}
        )
        constraints.extend(groove_constraints)

        add_driving_dimension(
            prefix + "_HALF_TOP",
            float(derived["actual_top_width"]) / 2.0,
            "VB_TOP_W / 2",
            {"kind": "line_length", "target": top_locator_id},
            note="Groove %s half top width locator" % groove_index,
        )
        add_driving_dimension(
            prefix + "_X0",
            float(top_left[0]) - float(axis["start"][0]),
            center_var + " - VB_AXIS_X0 - VB_TOP_W / 2",
            {
                "kind": "point_distance",
                "orientation": "horizontal",
                "target": "axis",
                "partner": edge_ids[3],
                "support_point_index": 0,
                "partner_point_index": 1,
            },
            note="Groove %s top-left distance from rotation-axis start" % groove_index,
        )
        add_driving_dimension(
            prefix + "_LEFT_X",
            float(top_left[0]) - float(axis["start"][0]),
            center_var + " - VB_AXIS_X0 - VB_TOP_W / 2",
            {
                "kind": "point_distance",
                "orientation": "horizontal",
                "target": "axis",
                "partner": edge_ids[0],
                "support_point_index": 0,
                "partner_point_index": 0,
            },
            note="Groove %s left-side top X coordinate" % groove_index,
        )
        add_driving_dimension(
            prefix + "_LEFT_Y",
            outer_radius,
            "VB_OR",
            {
                "kind": "point_distance",
                "orientation": "vertical",
                "target": "axis",
                "partner": edge_ids[0],
                "support_point_index": 0,
                "partner_point_index": 0,
            },
            note="Groove %s left-side top radius" % groove_index,
        )
        add_driving_dimension(
            prefix + "_RIGHT_X",
            float(top_right[0]) - float(axis["start"][0]),
            center_var + " - VB_AXIS_X0 + VB_TOP_W / 2",
            {
                "kind": "point_distance",
                "orientation": "horizontal",
                "target": "axis",
                "partner": edge_ids[2],
                "support_point_index": 0,
                "partner_point_index": 1,
            },
            note="Groove %s right-side top X coordinate" % groove_index,
        )
        add_driving_dimension(
            prefix + "_RIGHT_Y",
            outer_radius,
            "VB_OR",
            {
                "kind": "point_distance",
                "orientation": "vertical",
                "target": "axis",
                "partner": edge_ids[2],
                "support_point_index": 0,
                "partner_point_index": 1,
            },
            note="Groove %s right-side top radius" % groove_index,
        )
        add_driving_dimension(
            prefix + "_TOP",
            derived["actual_top_width"],
            "VB_TOP_W",
            {"kind": "line_length", "target": edge_ids[3]},
            note="Groove %s top width" % groove_index,
        )
        add_driving_dimension(
            prefix + "_YTOP",
            outer_radius,
            "VB_OR",
            {
                "kind": "point_distance",
                "orientation": "vertical",
                "target": "axis",
                "partner": edge_ids[3],
                "support_point_index": 0,
                "partner_point_index": 0,
            },
            note="Groove %s outer radius" % groove_index,
        )
        add_driving_dimension(
            prefix + "_YROOT",
            root_radius,
            "VB_RR",
            {
                "kind": "point_distance",
                "orientation": "vertical",
                "target": "axis",
                "partner": edge_ids[1],
                "support_point_index": 0,
                "partner_point_index": 0,
            },
            note="Groove %s root radius" % groove_index,
        )
        add_driving_dimension(
            prefix + "_RIGHT_ROOT_Y",
            root_radius,
            "VB_RR",
            {
                "kind": "point_distance",
                "orientation": "vertical",
                "target": "axis",
                "partner": edge_ids[2],
                "support_point_index": 0,
                "partner_point_index": 0,
            },
            note="Groove %s right-side root radius" % groove_index,
        )
        add_driving_dimension(
            prefix + "_LEFT_ROOT_Y",
            root_radius,
            "VB_RR",
            {
                "kind": "point_distance",
                "orientation": "vertical",
                "target": "axis",
                "partner": edge_ids[0],
                "support_point_index": 0,
                "partner_point_index": 1,
            },
            note="Groove %s left-side root radius" % groove_index,
        )
        add_driving_dimension(
            prefix + "_ANGLE_L",
            90.0 - groove_angle / 2.0,
            "90 - VB_ANGLE / 2",
            {
                "kind": "angle_between_lines",
                "target": edge_ids[0],
                "partner": "axis",
                "point_x": (float(top_left[0]) + float(root_left[0])) / 2.0,
                "point_y": (float(top_left[1]) + float(root_left[1])) / 2.0,
            },
            unit="deg",
            note="Groove %s left oriented half-angle" % groove_index,
        )
        add_driving_dimension(
            prefix + "_CENTER",
            center_x - float(axis["start"][0]),
            center_var + " - VB_AXIS_X0",
            {"kind": "line_length", "target": axis_locator_id},
            note="Groove %s axis locator length" % groove_index,
        )
        add_driving_dimension(
            prefix + "_CENTER_H",
            outer_radius,
            "VB_OR",
            {"kind": "line_length", "target": centerline_id},
            note="Groove %s centerline height" % groove_index,
        )
        add_driving_dimension(
            prefix + "_CENTER_X",
            center_x - float(axis["start"][0]),
            center_var + " - VB_AXIS_X0",
            {
                "kind": "point_distance",
                "orientation": "horizontal",
                "target": "axis",
                "partner": centerline_id,
                "support_point_index": 0,
                "partner_point_index": 0,
            },
            note="Groove %s centerline distance from rotation-axis start" % groove_index,
        )
        add_driving_dimension(
            prefix + "_CENTER_Y",
            0.0,
            "0",
            {
                "kind": "axis_distance",
                "orientation": "vertical",
                "target": centerline_id,
                "support_point_index": 0,
            },
            note="Groove %s centerline start on rotation axis" % groove_index,
        )
        add_driving_dimension(
            prefix + "_TOP_CENTER_X",
            center_x - float(axis["start"][0]),
            center_var + " - VB_AXIS_X0",
            {
                "kind": "point_distance",
                "orientation": "horizontal",
                "target": "axis",
                "partner": top_locator_id,
                "support_point_index": 0,
                "partner_point_index": 1,
            },
            note="Groove %s top-locator center distance" % groove_index,
        )
        add_driving_dimension(
            prefix + "_TOP_Y",
            outer_radius,
            "VB_OR",
            {
                "kind": "axis_distance",
                "orientation": "vertical",
                "target": top_locator_id,
                "support_point_index": 1,
            },
            note="Groove %s top-locator radius" % groove_index,
        )
        add_driving_dimension(
            prefix + "_ROOT",
            root_width,
            "VB_ROOT_W",
            {"kind": "line_length", "target": edge_ids[1]},
            note="Groove %s root width" % groove_index,
        )

    face_width = float(derived["face_width"])
    face_left = axial_center - face_width / 2.0
    face_right = axial_center + face_width / 2.0
    cylinder_edge_id = "cylinder_outer_edge"
    edge_chain_id = "groove_edge_chain"
    pitch_chain_id = "groove_pitch_chain"
    centerline_ids = ["groove_%s_centerline" % index for index in range(1, len(shifted_polygons) + 1)]
    construction_lines = [
        {
            "id": cylinder_edge_id,
            "target": cylinder_edge_id,
            "start": [face_left, outer_radius],
            "end": [face_right, outer_radius],
            "style": 2,
            "role": "cylinder_outer_edge",
        }
    ]
    for groove_index, polygon in enumerate(shifted_polygons, start=1):
        center_x = (float(polygon[0][0]) + float(polygon[3][0])) / 2.0
        construction_lines.append(
            {
                "id": centerline_ids[groove_index - 1],
                "target": centerline_ids[groove_index - 1],
                "start": [center_x + 0.4 * groove_index, outer_radius + 0.3 * groove_index],
                "end": [center_x + 0.4 * groove_index, root_radius + 0.3 * groove_index],
                "style": 2,
                "role": "groove_symmetry_axis",
            }
        )
    first_center = (float(shifted_polygons[0][0][0]) + float(shifted_polygons[0][3][0])) / 2.0
    second_center = (float(shifted_polygons[1][0][0]) + float(shifted_polygons[1][3][0])) / 2.0
    chain_y = outer_radius + 7.0
    construction_lines.extend(
        [
            {
                "id": edge_chain_id,
                "target": edge_chain_id,
                "start": [face_left, chain_y],
                "end": [first_center + 0.6, chain_y + 0.2],
                "style": 2,
                "role": "groove_edge_dimension_chain",
            },
            {
                "id": pitch_chain_id,
                "target": pitch_chain_id,
                "start": [first_center + 0.8, chain_y + 0.4],
                "end": [second_center + 1.0, chain_y + 0.6],
                "style": 2,
                "role": "groove_pitch_dimension_chain",
            },
        ]
    )

    pre_constraints: list[dict[str, Any]] = []
    for groove_index in range(1, len(shifted_polygons) + 1):
        edge_ids = ["groove_%s_side_%s" % (groove_index, side_index) for side_index in range(1, 5)]
        pre_constraints.extend(
            [
                {"kind": "merge_points", "target": edge_ids[0], "index": 1, "partner": edge_ids[1], "partner_index": 0},
                {"kind": "merge_points", "target": edge_ids[1], "index": 1, "partner": edge_ids[2], "partner_index": 0},
                {"kind": "merge_points", "target": edge_ids[2], "index": 1, "partner": edge_ids[3], "partner_index": 0},
                {"kind": "merge_points", "target": edge_ids[3], "index": 1, "partner": edge_ids[0], "partner_index": 0},
            ]
        )
    pre_constraints.append(
        {"kind": "merge_points", "target": edge_chain_id, "index": 1, "partner": pitch_chain_id, "partner_index": 0}
    )

    constraints: list[dict[str, Any]] = [
        {"kind": "fixed_point", "target": "axis", "index": 0},
        {"kind": "fixed_point", "target": "axis", "index": 1},
        {"kind": "fixed_point", "target": cylinder_edge_id, "index": 0},
        {"kind": "fixed_point", "target": cylinder_edge_id, "index": 1},
        {"kind": "fixed_point", "target": edge_chain_id, "index": 0},
        {"kind": "horizontal", "target": edge_chain_id},
        {"kind": "horizontal", "target": pitch_chain_id},
        {"kind": "v_align_points", "target": edge_chain_id, "index": 1, "partner": centerline_ids[0], "partner_index": 0},
        {"kind": "v_align_points", "target": pitch_chain_id, "index": 1, "partner": centerline_ids[1], "partner_index": 0},
    ]
    for groove_index in range(1, len(shifted_polygons) + 1):
        edge_ids = ["groove_%s_side_%s" % (groove_index, side_index) for side_index in range(1, 5)]
        centerline_id = centerline_ids[groove_index - 1]
        constraints.extend(
            [
                {"kind": "vertical", "target": centerline_id},
                {"kind": "horizontal", "target": edge_ids[3]},
                {"kind": "horizontal", "target": edge_ids[1]},
                {"kind": "point_on_curve_middle", "target": centerline_id, "index": 0, "partner": edge_ids[3]},
                {"kind": "point_on_curve_middle", "target": centerline_id, "index": 1, "partner": edge_ids[1]},
                {"kind": "point_on_curve", "target": centerline_id, "index": 0, "partner": cylinder_edge_id},
            ]
        )
    constraints.extend(
        [
            {"kind": "collinear", "target": "groove_2_side_2", "partner": "groove_1_side_2"},
            {"kind": "equal_length", "target": "groove_2_side_4", "partner": "groove_1_side_4"},
            {"kind": "equal_length", "target": "groove_2_side_2", "partner": "groove_1_side_2"},
        ]
    )

    dimensions = []
    add_driving_dimension(
        "VB_EDGE_DIM",
        float(resolved["edge_distance"]),
        "VB_EDGE",
        {"kind": "line_length", "target": edge_chain_id},
        note="Distance from cylinder edge to first groove axis",
    )
    add_driving_dimension(
        "VB_PITCH_DIM",
        float(resolved["groove_pitch"]),
        "VB_PITCH",
        {"kind": "line_length", "target": pitch_chain_id},
        note="Groove-axis pitch",
    )
    add_driving_dimension(
        "VB_TOP_DIM",
        float(derived["actual_top_width"]),
        "VB_TOP_W",
        {"kind": "line_length", "target": "groove_1_side_4"},
        note="Base groove top width",
    )
    add_driving_dimension(
        "VB_ROOT_DIM",
        root_width,
        "VB_ROOT_W",
        {"kind": "line_length", "target": "groove_1_side_2"},
        note="Base groove root width",
    )
    add_driving_dimension(
        "VB_ROOT_R_DIM",
        root_radius,
        "VB_RR",
        {
            "kind": "axis_distance",
            "orientation": "vertical",
            "target": "groove_1_side_2",
            "support_point_index": 0,
        },
        note="Base groove root radius",
    )
    dimensions.append(
        {
            "kind": "axis_distance",
            "orientation": "vertical",
            "display_mode": "diameter",
            "target": "groove_1_side_2",
            "support_point_index": 0,
            "name": "VB_ROOT_D_REF",
            "value": float(derived["root_diameter"]),
            "driving": False,
            "reference": True,
        }
    )
    dimensions.append(
        {
            "kind": "axis_distance",
            "orientation": "vertical",
            "display_mode": "diameter",
            "target": cylinder_edge_id,
            "support_point_index": 0,
            "name": "VB_OD_REF",
            "value": float(derived["outer_diameter"]),
            "driving": False,
            "reference": True,
        }
    )

    return {
        "variables": variables,
        "pre_constraints": pre_constraints,
        "constraints": constraints,
        "dimensions": dimensions,
        "construction_lines": construction_lines,
        "summary": {
            "variable_count": len(variables) + sum(1 for item in dimensions if item.get("driving")),
            "semantic_variable_count": len(variables),
            "dimension_variable_count": sum(1 for item in dimensions if item.get("driving")),
            "constraint_count": len(constraints),
            "pre_constraint_count": len(pre_constraints),
            "dimension_count": len(dimensions),
            "axis_line_count": 1,
            "auxiliary_line_count": len(construction_lines),
            "target_state": "fully_defined",
        },
    }


def _build_origin_v_belt_parameterization_plan(
    preview: dict[str, Any],
    shifted_polygons: list[list[list[float]]],
    *,
    axial_center: float,
    axis: dict[str, Any],
    parameter_base: dict[str, Any],
) -> dict[str, Any]:
    """Build the origin-backed contract linked to the blank's variables."""

    derived = dict(preview.get("derived") or {})
    resolved = dict(preview.get("profile") or {})
    groove_count = len(shifted_polygons)
    if groove_count < 1:
        raise ValueError("origin parameterization requires at least one groove")

    outer_diameter = float(derived["outer_diameter"])
    outer_radius = outer_diameter / 2.0
    root_radius = float(derived["root_diameter"]) / 2.0
    groove_angle = float(derived["groove_angle_degrees"])
    root_width = float(derived["root_flat_width"])
    face_left = axial_center - float(derived["face_width"]) / 2.0
    if abs(face_left) > 1e-9:
        raise ValueError("origin parameterization requires the blank left face at global origin")

    outer_radius_variable = str(parameter_base["outer_radius_variable"])
    face_width_variable = str(parameter_base["face_width_variable"])
    projections: list[dict[str, Any]] = []

    variables: list[dict[str, Any]] = [
        {"name": "VB_OR", "value": outer_radius, "expression": outer_radius_variable, "unit": "mm", "note": "Blank outer radius link"},
        {"name": "VB_FACE_W", "value": float(derived["face_width"]), "expression": face_width_variable, "unit": "mm", "note": "Blank face width link"},
        {"name": "VB_EDGE", "value": float(resolved["edge_distance"]), "expression": None, "unit": "mm", "note": "Left face to first groove axis"},
    ]
    if groove_count > 1:
        variables.append(
            {
                "name": "VB_PITCH",
                "value": float(resolved["groove_pitch"]),
                "expression": None,
                "unit": "mm",
                "note": "Groove center pitch",
            }
        )
    variables.extend(
        [
            {"name": "VB_TOP_W", "value": float(derived["actual_top_width"]), "expression": None, "unit": "mm", "note": "Base groove top width"},
            {"name": "VB_DEPTH", "value": float(resolved["groove_depth"]), "expression": None, "unit": "mm", "note": "Groove radial depth"},
            {"name": "VB_ANGLE", "value": groove_angle, "expression": None, "unit": "deg", "note": "Included groove angle"},
            {"name": "VB_RR", "value": root_radius, "expression": "VB_OR - VB_DEPTH", "unit": "mm", "note": "Groove root radius"},
            {"name": "VB_ROOT_W", "value": root_width, "expression": "VB_TOP_W - 2 * VB_DEPTH * tanD(VB_ANGLE / 2)", "unit": "mm", "note": "Derived groove root width"},
        ]
    )

    construction_lines: list[dict[str, Any]] = [
        {
            "id": "blank_axial_datum",
            "target": "blank_axial_datum",
            "kind": "line",
            "role": "auxiliary",
            "style": 2,
            "start": [face_left + 0.25, 0.25],
            "end": [face_left + 0.25, outer_radius + 0.25],
        },
        {
            "id": "blank_outer_datum",
            "target": "blank_outer_datum",
            "kind": "line",
            "role": "auxiliary",
            "style": 2,
            "start": [face_left + 0.25, outer_radius + 0.5],
            "end": [face_left + float(derived["face_width"]) + 0.25, outer_radius + 0.5],
        },
    ]
    centerline_ids: list[str] = []
    for groove_index, polygon in enumerate(shifted_polygons, start=1):
        top_left, root_left, root_right, top_right = polygon
        center_x = (float(top_left[0]) + float(top_right[0])) / 2.0
        centerline_id = f"groove_axis_{groove_index}"
        centerline_ids.append(centerline_id)
        construction_lines.append(
            {
                "id": centerline_id,
                "target": centerline_id,
                "kind": "line",
                "role": "auxiliary",
                "style": 2,
                "start": [center_x, (float(root_left[1]) + float(root_right[1])) / 2.0],
                "end": [center_x, (float(top_left[1]) + float(top_right[1])) / 2.0],
            }
        )

    pre_constraints: list[dict[str, Any]] = [
        {"kind": "fixed_point", "target": "axis", "index": 0},
        {"kind": "fixed_point", "target": "axis", "index": 1},
        {"kind": "merge_points", "target": "axis", "index": 0, "partner": "blank_axial_datum", "partner_index": 0},
        {"kind": "merge_points", "target": "blank_axial_datum", "index": 1, "partner": "blank_outer_datum", "partner_index": 0},
    ]
    for groove_index in range(1, groove_count + 1):
        side = [f"groove_{groove_index}_side_{index}" for index in range(1, 5)]
        pre_constraints.extend(
            [
                {"kind": "merge_points", "target": side[0], "index": 1, "partner": side[1], "partner_index": 0},
                {"kind": "merge_points", "target": side[1], "index": 1, "partner": side[2], "partner_index": 0},
                {"kind": "merge_points", "target": side[2], "index": 1, "partner": side[3], "partner_index": 0},
                {"kind": "merge_points", "target": side[3], "index": 1, "partner": side[0], "partner_index": 0},
            ]
        )

    constraints: list[dict[str, Any]] = [
        {"kind": "vertical", "target": "blank_axial_datum"},
        {"kind": "horizontal", "target": "blank_outer_datum"},
    ]
    for groove_index, centerline_id in enumerate(centerline_ids, start=1):
        left = f"groove_{groove_index}_side_1"
        root = f"groove_{groove_index}_side_2"
        right = f"groove_{groove_index}_side_3"
        top = f"groove_{groove_index}_side_4"
        constraints.extend(
            [
                {"kind": "vertical", "target": centerline_id},
                {"kind": "point_on_curve_middle", "target": centerline_id, "index": 0, "partner": root},
                {"kind": "point_on_curve_middle", "target": centerline_id, "index": 1, "partner": top},
                {"kind": "collinear", "target": top, "partner": "blank_outer_datum"},
            ]
        )
        if groove_index == 1:
            constraints.append({"kind": "horizontal", "target": root})
        else:
            constraints.extend(
                [
                    {"kind": "collinear", "target": root, "partner": "groove_1_side_2"},
                    {"kind": "equal_length", "target": left, "partner": "groove_1_side_1"},
                    {"kind": "equal_length", "target": root, "partner": "groove_1_side_2"},
                    {"kind": "equal_length", "target": right, "partner": "groove_1_side_3"},
                ]
            )
    dimensions: list[dict[str, Any]] = [
        {
            "kind": "point_distance",
            "orientation": "horizontal",
            "target": "blank_outer_datum",
            "index": 0,
            "partner": centerline_ids[0],
            "partner_index": 1,
            "name": "VB_EDGE_DIM",
            "variable_name": "VB_EDGE",
            "value": float(resolved["edge_distance"]),
            "driving": True,
        },
    ]
    for groove_index in range(1, groove_count):
        dimensions.append(
            {
                "kind": "point_distance",
                "orientation": "horizontal",
                "target": centerline_ids[groove_index - 1],
                "index": 1,
                "partner": centerline_ids[groove_index],
                "partner_index": 1,
                "name": f"VB_PITCH_{groove_index}_{groove_index + 1}_DIM",
                "variable_name": "VB_PITCH",
                "value": float(resolved["groove_pitch"]),
                "driving": True,
            }
        )
    for groove_index in range(2, groove_count + 1):
        variable_name = f"VB_G{groove_index}_TOP_W"
        variables.append(
            {
                "name": variable_name,
                "value": float(derived["actual_top_width"]),
                "expression": "VB_TOP_W",
                "unit": "mm",
                "note": f"Groove {groove_index} inherited top width",
            }
        )
        dimensions.append(
            {
                "kind": "line_length",
                "target": f"groove_{groove_index}_side_4",
                "name": f"{variable_name}_DIM",
                "variable_name": variable_name,
                "value": float(derived["actual_top_width"]),
                "driving": True,
            }
        )
    dimensions.extend(
        [
            {"kind": "line_length", "target": "groove_1_side_4", "name": "VB_TOP_DIM", "variable_name": "VB_TOP_W", "value": float(derived["actual_top_width"]), "driving": True},
            {"kind": "line_length", "target": "groove_1_side_2", "name": "VB_ROOT_W_DIM", "variable_name": "VB_ROOT_W", "value": root_width, "driving": True},
            {"kind": "axis_distance", "orientation": "vertical", "target": "groove_1_side_2", "support_point_index": 0, "name": "VB_RR_DIM", "variable_name": "VB_RR", "value": root_radius, "driving": True},
            {"kind": "line_length", "target": "blank_axial_datum", "name": "VB_OR_DIM", "variable_name": "VB_OR", "value": outer_radius, "driving": True},
            {"kind": "line_length", "target": "blank_outer_datum", "name": "VB_FACE_W_DIM", "variable_name": "VB_FACE_W", "value": float(derived["face_width"]), "driving": True},
        ]
    )

    return {
        "base_mode": "origin_parameter_link",
        "projections": projections,
        "variables": variables,
        "pre_constraints": pre_constraints,
        "constraints": constraints,
        "dimensions": dimensions,
        "construction_lines": construction_lines,
        "summary": {
            "variable_count": len(variables),
            "semantic_variable_count": len(variables),
            "dimension_variable_count": sum(1 for item in dimensions if item.get("driving")),
            "constraint_count": len(constraints),
            "pre_constraint_count": len(pre_constraints),
            "dimension_count": len(dimensions),
            "projection_count": len(projections),
            "axis_line_count": 1,
            "auxiliary_line_count": len(construction_lines),
            "target_state": "fully_defined",
        },
    }


def _build_v_belt_parameterization_plan(
    preview: dict[str, Any],
    shifted_polygons: list[list[list[float]]],
    *,
    axial_center: float,
    axis: dict[str, Any],
    parameter_base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if parameter_base is None:
        raise ValueError("parameter_base is required for an executable V-belt cut plan")
    return _build_origin_v_belt_parameterization_plan(
        preview,
        shifted_polygons,
        axial_center=axial_center,
        axis=axis,
        parameter_base=parameter_base,
    )


def _build_v_belt_entity_names(
    preview: dict[str, Any],
    requested_name: str,
    *,
    top_edge_fillet_radius: float | None,
) -> dict[str, str | None]:
    inputs = dict(preview.get("inputs") or {})
    designation = str(inputs.get("designation") or "CUSTOM").strip().upper()
    groove_count = int(inputs.get("groove_count") or 1)
    groove_label = f"{designation} x{groove_count}"

    custom_label = str(requested_name or "").strip()
    suffix = ""
    if custom_label and custom_label.casefold() != "v-belt grooves":
        suffix = f" - {custom_label}"

    fillet_name = None
    if top_edge_fillet_radius is not None:
        fillet_name = f"V-belt grooves {groove_label} top edge fillets R{top_edge_fillet_radius:g}{suffix}"

    return {
        "sketch": f"V-belt grooves {groove_label} profile{suffix}",
        "cut": f"V-belt grooves {groove_label} cut rotation{suffix}",
        "top_edge_fillet": fillet_name,
    }


def build_v_belt_cut_plan(
    preview: dict[str, Any],
    *,
    axial_center: float = 0.0,
    name: str = "V-belt grooves",
    parameter_base: dict[str, Any] | None = None,
    top_edge_fillet_radius: float | None = None,
    include_standard_top_edge_fillet: bool = True,
) -> dict[str, Any]:
    if not isinstance(preview, dict) or preview.get("operation") != "v_belt_groove":
        raise ValueError("preview must be a successful v_belt_groove preview")
    if not preview.get("success"):
        raise ValueError("preview must be successful")
    center_offset = _finite_float("axial_center", axial_center)
    requested_name = str(name or "").strip()
    if not requested_name:
        raise ValueError("name must not be empty")

    source_grooves = list((preview.get("geometry") or {}).get("grooves") or [])
    if not source_grooves:
        raise ValueError("preview does not contain groove geometry")

    profile_entities: list[dict[str, Any]] = []
    shifted_polygons: list[list[list[float]]] = []
    expected_removed_volume_mm3 = 0.0
    for groove_index, groove in enumerate(source_grooves):
        source_polygon = list(groove.get("cut_polygon") or [])
        if len(source_polygon) != 4:
            raise ValueError("each groove cut polygon must contain four points")
        polygon = [
            [_finite_float("profile x", point[0]) + center_offset, _finite_float("profile y", point[1])]
            for point in source_polygon
        ]
        shifted_polygons.append(polygon)
        expected_removed_volume_mm3 += _revolved_polygon_volume_mm3(polygon)
        for side_index in range(len(polygon)):
            profile_entities.append(
                {
                    "id": f"groove_{groove_index + 1}_side_{side_index + 1}",
                    "target": f"groove_{groove_index + 1}_side_{side_index + 1}",
                    "kind": "line",
                    "role": "primary",
                    "style": 1,
                    "start": polygon[side_index],
                    "end": polygon[(side_index + 1) % len(polygon)],
                }
            )
    bridge_profile_entities: list[dict[str, Any]] = []
    for entity_index, entity in enumerate(profile_entities, start=1):
        initial_shift = 0.5 * entity_index
        initial_y_shift = 0.5 * entity_index
        bridge_entity = {
            **entity,
            "start": [
                float(entity["start"][0]) + initial_shift,
                float(entity["start"][1]) + initial_y_shift,
            ],
            "end": [
                float(entity["end"][0]) + initial_shift,
                float(entity["end"][1]) + initial_y_shift,
            ],
            "initial_merge_offset": initial_shift,
            "initial_y_offset": initial_y_shift,
        }
        bridge_profile_entities.append(bridge_entity)

    envelope = dict((preview.get("geometry") or {}).get("envelope") or {})
    x_min = _finite_float("envelope x_min", envelope.get("x_min")) + center_offset
    x_max = _finite_float("envelope x_max", envelope.get("x_max")) + center_offset
    axis_margin = max(5.0, (x_max - x_min) * 0.1)
    axis_start = 0.0 if x_min >= 0.0 else x_min - axis_margin
    axis_end = 0.0 if x_max <= 0.0 else x_max + axis_margin
    axis = {
        "id": "rotation_axis",
        "kind": "line",
        "role": "construction",
        "style": 3,
        "start": [axis_start, 0.0],
        "end": [axis_end, 0.0],
    }
    parameterization = _build_v_belt_parameterization_plan(
        preview,
        shifted_polygons,
        axial_center=center_offset,
        axis=axis,
        parameter_base=parameter_base,
    )
    standard_fillet_radius = preview.get("profile", {}).get("standard_top_edge_radius")
    effective_fillet_radius = top_edge_fillet_radius
    fillet_radius_source = "override" if top_edge_fillet_radius is not None else None
    if effective_fillet_radius is None and bool(include_standard_top_edge_fillet) and standard_fillet_radius is not None:
        effective_fillet_radius = standard_fillet_radius
        fillet_radius_source = "standard"
    top_edge_fillet = None
    fillet_radius: float | None = None
    if effective_fillet_radius is not None:
        fillet_radius = _positive_float("top_edge_fillet_radius", effective_fillet_radius)
    entity_names = _build_v_belt_entity_names(
        preview,
        requested_name,
        top_edge_fillet_radius=fillet_radius,
    )
    feature_name = str(entity_names["cut"])
    if effective_fillet_radius is not None:
        outer_radius = float(preview["derived"]["outer_diameter"]) / 2.0
        edge_probe_points = []
        for groove_index, polygon in enumerate(shifted_polygons, start=1):
            edge_probe_points.extend(
                [
                    {
                        "role": f"groove_{groove_index}_top_left",
                        "point": [float(polygon[0][0]), outer_radius, 0.0],
                    },
                    {
                        "role": f"groove_{groove_index}_top_right",
                        "point": [float(polygon[3][0]), outer_radius, 0.0],
                    },
                ]
            )
        top_edge_fillet = {
            "enabled": True,
            "name": entity_names["top_edge_fillet"],
            "radius": fillet_radius,
            "radius_source": fillet_radius_source,
            "standard_system": preview.get("profile", {}).get("standard_system"),
            "expected_edge_count": 2 * len(shifted_polygons),
            "edge_probe_points": edge_probe_points,
            "probe_tolerance": 1e-5,
        }

    bridge_preview = {
        "geometry": {
            "profile_points": shifted_polygons[0],
            "profile_entities": bridge_profile_entities,
            "axis": axis,
            "construction_entities": parameterization["construction_lines"],
        },
        "variables": parameterization["variables"],
        "projections": parameterization.get("projections", []),
        "pre_constraints": parameterization["pre_constraints"],
        "constraints": parameterization["constraints"],
        "dimensions": parameterization["dimensions"],
        "operations": [
            {
                "operation": "draw_axis",
                "start": axis["start"],
                "end": axis["end"],
            },
            {
                "operation": "draw_profile",
                "profile_points": shifted_polygons[0],
                "profile_entities": bridge_profile_entities,
                "construction_lines": parameterization["construction_lines"],
            },
            {"operation": "add_variables", "variables": parameterization["variables"]},
            {"operation": "apply_constraints", "constraints": parameterization["constraints"]},
            {"operation": "add_dimensions", "dimensions": parameterization["dimensions"]},
            {"operation": "cut_rotation"},
        ]
        + ([{"operation": "fillet_edges", **top_edge_fillet}] if top_edge_fillet is not None else []),
    }
    params = {
        "name": feature_name,
        "total_length": x_max - x_min,
        "angle_degrees": 360.0,
        "profile_line_style": 1,
        "axis_line_style": 3,
        "expected_profile_component_count": len(shifted_polygons),
        "max_removed_volume_error_ratio": 0.25,
        "rotation_axis_default_object_type": 71,
        "require_explicit_rotation_axis": True,
        "verify_profile_after_parameterization": True,
        "require_parameterization": True,
        "initial_merge_offset_step": 0.5,
        "require_fully_defined": True,
        "profile_sketch_target_state": "fully_defined",
        "sketch": {
            "constraints": {"enabled": True},
            "dimensions": {"enabled": True, "driving": True},
            "parameterization_order": "constraints_then_dimensions",
            "deferred_dimension_kinds": [],
            "preflight_after_update": True,
            "require_exact_counts": True,
            "expected_constraint_count": len(parameterization["constraints"]),
            "expected_dimension_count": len(parameterization["dimensions"]),
        },
        "variables": parameterization["variables"],
        "projections": parameterization.get("projections", []),
        "base_mode": parameterization.get("base_mode", "legacy_coordinates"),
        "pre_constraints": parameterization["pre_constraints"],
        "constraints": parameterization["constraints"],
        "dimensions": parameterization["dimensions"],
        "top_edge_fillet": top_edge_fillet,
    }

    planned_outputs = list(preview["composition"]["planned_semantic_outputs"])
    if top_edge_fillet is not None:
        planned_outputs.append("member.edge_fillet_feature")
    return {
        "ok": True,
        "stage": "v_belt_groove_cad_plan",
        "plan_version": 3,
        "operation": "cut_rotation",
        "axis": "global_x",
        "axial_center": center_offset,
        "name": feature_name,
        "requested_name": requested_name,
        "entity_names": entity_names,
        "groove_count": len(shifted_polygons),
        "profile_entity_count": len(profile_entities),
        "shifted_cut_polygons": shifted_polygons,
        "expected_removed_volume_mm3": expected_removed_volume_mm3,
        "expected_removed_volume_cm3": expected_removed_volume_mm3 / 1000.0,
        "top_edge_fillet": top_edge_fillet,
        "params": params,
        "bridge_preview": bridge_preview,
        "parameterization": {
            **parameterization["summary"],
            "base_mode": parameterization.get("base_mode", "legacy_coordinates"),
        },
        "preflight": {
            "required_body_count": 1,
            "required_axis": "global_x",
            "required_outer_diameter": preview["derived"]["outer_diameter"],
            "required_axial_interval": [x_min, x_max],
            "minimum_material_radius": preview["geometry"]["envelope"]["radius_min"],
        },
        "planned_outputs": planned_outputs,
    }


def validate_v_belt_cut_target(
    plan: dict[str, Any],
    target: dict[str, Any],
    *,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("stage") != "v_belt_groove_cad_plan":
        raise ValueError("plan must be a v_belt_groove_cad_plan")
    if not isinstance(target, dict):
        raise ValueError("target must be an object")
    if target.get("axis") != "global_x":
        raise ValueError("target axis must be 'global_x'")
    body_count = _positive_int("target.body_count", target.get("body_count"), maximum=1)
    if body_count != 1:
        raise ValueError("target.body_count must be 1")
    parameter_base = target.get("parameter_base")
    if not isinstance(parameter_base, dict):
        raise ValueError("target.parameter_base must be an object")
    outer_radius_variable = str(parameter_base.get("outer_radius_variable") or "").strip()
    face_width_variable = str(parameter_base.get("face_width_variable") or "").strip()
    if not outer_radius_variable or not face_width_variable:
        raise ValueError("target.parameter_base variable names must not be empty")
    planned_projections = list((plan.get("params") or {}).get("projections") or [])
    if planned_projections:
        raise ValueError("origin-mode plan must not contain projection anchors")
    variable_links = {
        str(item.get("name")): item.get("expression")
        for item in (plan.get("params") or {}).get("variables") or []
    }
    if variable_links.get("VB_OR") != outer_radius_variable:
        raise ValueError("plan VB_OR link does not match target.parameter_base")
    if variable_links.get("VB_FACE_W") != face_width_variable:
        raise ValueError("plan VB_FACE_W link does not match target.parameter_base")

    outer_diameter = _positive_float("target.outer_diameter", target.get("outer_diameter"))
    axial_min = _finite_float("target.axial_min", target.get("axial_min"))
    axial_max = _finite_float("target.axial_max", target.get("axial_max"))
    if axial_max <= axial_min:
        raise ValueError("target.axial_max must be greater than target.axial_min")

    required = plan["preflight"]
    required_diameter = float(required["required_outer_diameter"])
    required_interval = [float(value) for value in required["required_axial_interval"]]
    diameter_delta = outer_diameter - required_diameter
    if abs(diameter_delta) > tolerance:
        raise ValueError(
            f"target outer_diameter={outer_diameter:g} mm does not match required "
            f"{required_diameter:g} mm"
        )
    if abs(axial_min - required_interval[0]) > tolerance or abs(axial_max - required_interval[1]) > tolerance:
        raise ValueError(
            "origin-mode target axial interval must match the planned face interval "
            f"[{required_interval[0]:g}, {required_interval[1]:g}]"
        )

    return {
        "ok": True,
        "axis_matches": True,
        "body_count_matches": True,
        "outer_diameter_matches": True,
        "parameter_base_matches": True,
        "diameter_delta": diameter_delta,
        "target_axial_interval": [axial_min, axial_max],
        "required_axial_interval": required_interval,
        "axial_interval_matches_plan": True,
        "unverified_by_host": [
            "actual KOMPAS body count",
            "actual body axis",
            "actual outer-cylinder diameter",
            "actual material intersection",
        ],
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
        "standard_system": "custom",
        "standard_top_edge_radius": (
            None
            if profile.get("standard_top_edge_radius") is None
            else _positive_float("standard_top_edge_radius", profile.get("standard_top_edge_radius"))
        ),
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
        minimum = rule.get("min_datum_diameter")
        maximum = rule["max_datum_diameter"]
        minimum_matches = minimum is None or diameter >= float(minimum) - 1e-9
        maximum_matches = maximum is None or diameter <= float(maximum) + 1e-9
        if minimum_matches and maximum_matches:
            return float(rule["angle_degrees"])
    raise ValueError(
        f"datum_diameter={diameter:g} is not covered by the selected standard's groove-angle bands"
    )


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


def _finite_float(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _revolved_polygon_volume_mm3(polygon: list[list[float]]) -> float:
    signed_twice_area = 0.0
    centroid_y_numerator = 0.0
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        cross = point[0] * next_point[1] - next_point[0] * point[1]
        signed_twice_area += cross
        centroid_y_numerator += (point[1] + next_point[1]) * cross
    if abs(signed_twice_area) <= 1e-12:
        raise ValueError("groove cut polygon has zero area")
    signed_area = signed_twice_area / 2.0
    centroid_y = centroid_y_numerator / (3.0 * signed_twice_area)
    if centroid_y <= 0.0:
        raise ValueError("groove cut polygon centroid must have positive radius")
    return abs(signed_area) * 2.0 * math.pi * centroid_y


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
