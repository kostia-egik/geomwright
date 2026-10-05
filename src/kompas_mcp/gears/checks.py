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
    tip_value = geometry.tip_arc_thickness_mm
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
            "Arc tooth thickness on the outside circle against the 0.30 m recommendation.",
            value=tip_value,
            limit=tip_limit,
            unit="mm",
        )
    )
    module_status = "ok" if geometry.module_info.get("standard_value") else "warning"
    checks.append(
        _check(
            "gear_module_row",
            module_status,
            "Module value against ГОСТ 9563-60 rows 1-2 and their recorded exceptions.",
            value=geometry.module_mm,
            limit=None,
            unit="mm",
        )
    )
    if geometry.module_mm < 1.0:
        checks.append(
            _check(
                "gear_small_module_contour",
                "warning",
                "Small-module contour of ГОСТ 9587-81 is not implemented; ГОСТ 13755-2015 coefficients are used.",
                value=geometry.module_mm,
                limit=1.0,
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
    checks.append(
        _check(
            "gear_root_envelope",
            "ok",
            (
                "Nominal envelope: theoretical sharp generating rack. "
                f"The contour fillet radius {geometry.root_fillet_radius_mm:.4f} mm is reported, "
                "not applied as a rounded cutter tip."
            ),
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
