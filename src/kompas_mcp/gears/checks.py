"""Structured verification report for the external spur-gear module."""
from __future__ import annotations

from typing import Any


def _check(
    code: str,
    status: str,
    message: str,
    *,
    value: Any = None,
    limit: Any = None,
    unit: str | None = None,
) -> dict:
    return {
        "code": code,
        "status": status,
        "message": message,
        "value": value,
        "limit": limit,
        "unit": unit,
    }


def evaluate_gear_checks(geometry, measurements: dict) -> dict:
    """Combine scalar diagnostics and control measurements into one report."""
    checks: list[dict] = []
    checks.append(
        _check(
            "gear_radii",
            "ok",
            "Pitch, base, outside and root diameters are ordered and positive.",
            value={
                "pitch_diameter_mm": 2.0 * geometry.pitch_radius,
                "base_diameter_mm": 2.0 * geometry.base_radius,
                "outside_diameter_mm": 2.0 * geometry.outside_radius,
                "root_diameter_mm": 2.0 * geometry.root_radius,
            },
        )
    )
    checks.append(
        _check(
            "gear_undercut",
            "warning" if geometry.undercut else "ok",
            (
                "The generating rack cuts into the involute near the base circle; "
                "the form point is trimmed to the trochoid."
                if geometry.undercut
                else "No rack undercut: the profile shift is at or above the minimum."
            ),
            value=geometry.profile_shift,
            limit=geometry.minimum_shift,
            unit="x",
        )
    )
    helical = geometry.helix_angle_rad > 1e-9
    tip_value = geometry.tip_thickness_normal_mm if helical else geometry.tip_arc_thickness_mm
    tip_limit = 0.3 * geometry.module_mm
    if tip_value <= 0.0:
        tip_status = "error"
    elif tip_value < 0.25 * geometry.module_mm:
        tip_status = "warning"
    elif tip_value < tip_limit:
        tip_status = "warning"
    else:
        tip_status = "ok"
    checks.append(
        _check(
            "gear_tip_thickness",
            tip_status,
            (
                "Normal tooth thickness on the outside circle against the 0.30 m recommendation."
                if helical
                else "Arc tooth thickness on the outside circle against the 0.30 m recommendation."
            ),
            value=tip_value,
            limit=tip_limit,
            unit="mm",
        )
    )
    if helical:
        axial_pitch = geometry.axial_pitch_mm
        overlap = geometry.face_width_mm / axial_pitch if axial_pitch > 0.0 else 0.0
        checks.append(
            _check(
                "gear_axial_overlap",
                "ok" if overlap >= 1.0 - 1e-9 else "warning",
                (
                    "Axial overlap ratio b / p_x; below 1.0 the tooth engagement is not continuous "
                    "across the face width."
                ),
                value=overlap,
                limit=1.0,
                unit="x",
            )
        )
    module_status = "ok" if geometry.module_info.get("standard_value") else "warning"
    checks.append(
        _check(
            "gear_module_row",
            module_status,
            (
                f"Module value against {geometry.module_info.get('standard_edition')} "
                "rows and their recorded exceptions."
            ),
            value=geometry.module_mm,
            limit=None,
            unit="mm",
        )
    )
    rack = geometry.rack
    below_range = rack.module_min is not None and geometry.module_mm < rack.module_min - 1e-9
    above_range = rack.module_max is not None and (
        geometry.module_mm >= rack.module_max - 1e-9
        if rack.module_max_exclusive
        else geometry.module_mm > rack.module_max + 1e-9
    )
    if below_range or above_range:
        range_text = (
            f"{rack.module_min:g}..{rack.module_max:g}"
            + (" (upper bound excluded)" if rack.module_max_exclusive else "")
        )
        checks.append(
            _check(
                "gear_standard_module_range",
                "warning",
                f"{rack.standard_edition} applies to modules {range_text} mm.",
                value=geometry.module_mm,
                limit=[rack.module_min, rack.module_max],
                unit="mm",
            )
        )
    checks.append(
        _check(
            "gear_contour",
            "ok" if geometry.rack.conformity_claim else "warning",
            (
                f"Basic rack {geometry.rack.name_ru} ({geometry.rack.standard} · {geometry.rack.modification}): "
                f"{geometry.rack.standard_edition}."
                if geometry.rack.conformity_claim
                else "Explicit coefficients define a user-defined rack without a standard-conformity claim."
            ),
            value={
                "standard": geometry.rack.standard,
                "modification": geometry.rack.modification,
            },
        )
    )
    fillet_note = (
        "The contour fillet radius is not tabulated for this modification."
        if geometry.root_fillet_radius_mm is None
        else (
            f"The contour fillet radius {geometry.root_fillet_radius_mm:.4f} mm is reported, "
            "not applied as a rounded cutter tip."
        )
    )
    checks.append(
        _check(
            "gear_root_envelope",
            "ok",
            f"Nominal envelope: theoretical sharp generating rack. {fillet_note}",
            value=geometry.root_envelope,
        )
    )
    span = measurements.get("span") or {}
    checks.append(
        _check(
            "gear_span_measurement",
            "ok" if span.get("usable") else "warning",
            (
                f"Span length over {span.get('span_tooth_count')} teeth; "
                "the contact radius must stay between the root and outside circles."
            ),
            value=span.get("span_length_mm"),
            limit=span.get("span_tooth_count"),
            unit="mm",
        )
    )
    over_pin = measurements.get("over_pin") or {}
    checks.append(
        _check(
            "gear_over_pin",
            "ok" if over_pin.get("fits_below_tips") else "warning",
            "Over-pin measurement with the selected pin diameter; the pin must stay below the tooth tips.",
            value=over_pin.get("over_pin_mm"),
            limit=over_pin.get("pin_diameter_mm"),
            unit="mm",
        )
    )
    if geometry.tip_chamfer_mm > 0.0:
        checks.append(
            _check(
                "gear_tip_chamfer",
                "ok",
                "End chamfer on both tooth-tip faces; the two conical cuts remove the calculated ring volume.",
                value=geometry.tip_chamfer_mm,
                limit=geometry.tip_chamfer_angle_deg,
                unit="mm/deg",
            )
        )
    errors = [item for item in geometry.errors]
    if errors:
        status = "error"
    elif any(item["status"] == "warning" for item in checks):
        status = "warning"
    else:
        status = "ok"
    return {
        "status": status,
        "checks": checks,
        "errors": errors,
        "representation_mode": "nominal",
        "conformity_claim": bool(geometry.rack.conformity_claim and status != "error"),
    }
