"""Host-side preview analysis for the external spur-gear module (no COM)."""
from __future__ import annotations

import math

from .checks import evaluate_gear_checks
from .involute import build_spur_gear_geometry
from .measure import base_pitch, chordal_tooth, constant_chord, over_pin_measurement, span_measurement
from .pins import select_standard_pin


def build_spur_gear_preview(
    request: dict,
    *,
    wheel_points_per_tooth: int = 48,
) -> dict:
    """Validate the request and return the complete nominal analysis."""
    module = float(request["module_mm"])
    tooth_count = int(request["tooth_count"])
    geometry = build_spur_gear_geometry(
        request,
        wheel_points_per_tooth=wheel_points_per_tooth,
    )
    warning_items = list(geometry.warnings)
    warnings = [str(item["message"]) for item in warning_items]
    if geometry.errors:
        return {
            "success": False,
            "family": "gear_spur",
            "request": dict(request),
            "warnings": warnings,
            "warning_items": warning_items,
            "errors": list(geometry.errors),
            "report": {
                "status": "error",
                "checks": [],
                "errors": list(geometry.errors),
                "representation_mode": "nominal",
                "conformity_claim": False,
            },
            "geometry": {},
            "derived": {},
            "measurements": {},
        }

    pin_diameter = request.get("pin_diameter_mm")
    alpha_n = math.radians(geometry.rack.pressure_angle_deg)
    pin_kwargs = {
        "normal_pressure_angle_rad": alpha_n,
        "transverse_pressure_angle_rad": geometry.pressure_angle_rad,
    }

    def pin_probe(diameter: float) -> dict:
        return over_pin_measurement(
            module_mm=module,
            tooth_count=tooth_count,
            profile_shift=geometry.profile_shift,
            pressure_angle_rad=geometry.pressure_angle_rad,
            pitch_radius=geometry.pitch_radius,
            outside_radius=geometry.outside_radius,
            pin_diameter_mm=diameter,
            **pin_kwargs,
        )

    if pin_diameter is None:
        preferred = (1.44 if tooth_count % 2 == 0 else 1.68) * module
        standard = select_standard_pin(
            preferred, lambda diameter: pin_probe(diameter).get("fits_below_tips")
        )
        if standard is not None:
            pin_diameter = standard["diameter_mm"]
            pin_source = standard["source"]
        else:
            alternate = (1.68 if tooth_count % 2 == 0 else 1.44) * module
            chosen = None
            for candidate, source in (
                (preferred, "nominal_even_1.44_m" if tooth_count % 2 == 0 else "nominal_odd_1.68_m"),
                (alternate, "fallback_even_1.68_m" if tooth_count % 2 == 0 else "fallback_odd_1.44_m"),
            ):
                if pin_probe(candidate).get("fits_below_tips"):
                    chosen = (candidate, source)
                    break
            if chosen is None:
                chosen = (preferred, "nominal_unplaced")
            pin_diameter, pin_source = chosen
    else:
        pin_diameter = float(pin_diameter)
        pin_source = "explicit"
    measurements = {
        "span": span_measurement(
            module_mm=module,
            tooth_count=tooth_count,
            profile_shift=geometry.profile_shift,
            pressure_angle_rad=geometry.pressure_angle_rad,
            base_radius=geometry.base_radius,
            outside_radius=geometry.outside_radius,
            root_radius=geometry.root_radius,
            **pin_kwargs,
        ),
        "constant_chord": constant_chord(
            module_mm=module,
            profile_shift=geometry.profile_shift,
            pressure_angle_rad=alpha_n,
            pitch_radius=geometry.pitch_radius,
            outside_radius=geometry.outside_radius,
        ),
        "over_pin": {
            **over_pin_measurement(
                module_mm=module,
                tooth_count=tooth_count,
                profile_shift=geometry.profile_shift,
                pressure_angle_rad=geometry.pressure_angle_rad,
                pitch_radius=geometry.pitch_radius,
                outside_radius=geometry.outside_radius,
                pin_diameter_mm=pin_diameter,
                **pin_kwargs,
            ),
            "pin_source": pin_source,
        },
        "base_pitch_mm": base_pitch(module, alpha_n),
        **chordal_tooth(
            pitch_radius=geometry.pitch_radius,
            tooth_thickness_mm=geometry.tooth_thickness_mm,
        ),
    }
    report = evaluate_gear_checks(geometry, measurements)
    span = measurements["span"]
    over_pin = measurements["over_pin"]
    axial_overlap = (
        geometry.face_width_mm / geometry.axial_pitch_mm if geometry.axial_pitch_mm > 0.0 else 0.0
    )
    summary = {
        "module_mm": module,
        "tooth_count": tooth_count,
        "standard": geometry.rack.standard,
        "modification": geometry.rack.modification,
        "contour_name": geometry.rack.name_ru,
        "standard_edition": geometry.rack.standard_edition,
        "pressure_angle_deg": math.degrees(alpha_n),
        "profile_shift": geometry.profile_shift,
        "face_width_mm": geometry.face_width_mm,
        "pitch_diameter_mm": 2.0 * geometry.pitch_radius,
        "base_diameter_mm": 2.0 * geometry.base_radius,
        "outside_diameter_mm": 2.0 * geometry.outside_radius,
        "root_diameter_mm": 2.0 * geometry.root_radius,
        "form_diameter_mm": 2.0 * geometry.form_radius_mm,
        "minimum_shift": geometry.minimum_shift,
        "tooth_thickness_mm": geometry.tooth_thickness_mm,
        "space_width_mm": geometry.space_width_mm,
        "tip_thickness_mm": geometry.tip_arc_thickness_mm,
        "root_fillet_radius_mm": geometry.root_fillet_radius_mm,
        "root_envelope": geometry.root_envelope,
        "span_length_mm": span["span_length_mm"],
        "span_tooth_count": span["span_tooth_count"],
        "constant_chord_mm": measurements["constant_chord"]["constant_chord_mm"],
        "constant_chord_height_mm": measurements["constant_chord"]["constant_chord_height_mm"],
        "over_pin_mm": over_pin["over_pin_mm"],
        "over_pin_diameter_mm": over_pin["pin_diameter_mm"],
        "over_pin_source": over_pin["pin_source"],
        "base_pitch_mm": measurements["base_pitch_mm"],
        "section_area_mm2": geometry.section_area_mm2,
        "representation_mode": report["representation_mode"],
        "verification_status": report["status"],
    }
    if geometry.helix_angle_rad > 1e-9:
        summary.update(
            {
                "helix_angle_deg": math.degrees(geometry.helix_angle_rad),
                "hand": geometry.hand,
                "transverse_module_mm": geometry.transverse_module_mm,
                "transverse_pressure_angle_deg": math.degrees(geometry.pressure_angle_rad),
                "base_helix_angle_deg": math.degrees(geometry.base_helix_angle_rad),
                "axial_pitch_mm": geometry.axial_pitch_mm,
                "lead_mm": geometry.lead_mm,
                "axial_overlap": axial_overlap,
                "tip_thickness_normal_mm": geometry.tip_thickness_normal_mm,
            }
        )
    if geometry.tip_chamfer_mm > 0.0:
        summary.update(
            {
                "tip_chamfer_mm": geometry.tip_chamfer_mm,
                "tip_chamfer_angle_deg": geometry.tip_chamfer_angle_deg,
                "tip_chamfer_depth_mm": geometry.tip_chamfer_depth_mm,
            }
        )
    derived = {
        **summary,
        "module_row": geometry.module_info.get("row"),
        "module_status": geometry.module_info.get("status"),
        "undercut": geometry.undercut,
        "checks": report["checks"],
    }
    return {
        "success": True,
        "family": "gear_spur",
        "request": dict(request),
        "representation_mode": report["representation_mode"],
        "geometry": {
            "coordinate_system": "end_view_polar_yz",
            "full_wheel_outline": geometry.full_wheel_outline,
            "gap_surface_path": geometry.gap_surface_path,
            "involute_path": geometry.involute_path,
            "root_arc_path": geometry.root_arc_path,
            "period_outline": geometry.period_outline,
            "gap_outline": geometry.gap_outline,
            "pitch_radius_mm": geometry.pitch_radius,
            "base_radius_mm": geometry.base_radius,
            "outside_radius_mm": geometry.outside_radius,
            "root_radius_mm": geometry.root_radius,
        },
        "derived": derived,
        "measurements": measurements,
        "summary": summary,
        "report": report,
        "warnings": warnings,
        "warning_items": warning_items,
    }
