"""Control measurements for external spur gears.

Formulas follow the local ГОСТ 16532-70 research cache:

* span length `W_k = m cos(a) [pi (k - 0.5) + z inv(a)] + 2 x m sin(a)`
* constant chord `s_c = m (pi/2 cos^2(a) + x sin(2a))`,
  height `h_c = 0.5 (d_a - d - s_c tan(a))`
* over-pin `inv(a_D) = inv(a) + D / (m z cos(a)) - pi / (2 z) + 2 x tan(a) / z`
  with `d_D = d cos(a) / cos(a_D)`, `M = d_D + D` for even z and
  `M = d_D cos(pi / (2 z)) + D` for odd z.
"""
from __future__ import annotations

import math


def _involute(value: float) -> float:
    return math.tan(value) - value


def span_measurement(
    *,
    module_mm: float,
    tooth_count: int,
    profile_shift: float,
    pressure_angle_rad: float,
    base_radius: float,
    outside_radius: float,
    root_radius: float,
    normal_pressure_angle_rad: float | None = None,
    transverse_pressure_angle_rad: float | None = None,
) -> dict:
    """Span measurement W_k over the closest usable number of teeth.

    `module_mm` is the normal module. For a helical gear the span is measured
    in the normal plane: `inv` and the tooth wrap use the transverse pressure
    angle, while the sine/cosine weights use the normal one.
    """
    alpha_n = pressure_angle_rad if normal_pressure_angle_rad is None else normal_pressure_angle_rad
    alpha_t = pressure_angle_rad if transverse_pressure_angle_rad is None else transverse_pressure_angle_rad
    inv_alpha = _involute(alpha_t)
    baseline = tooth_count * alpha_t / math.pi + 0.5
    candidates = sorted({max(2, int(math.floor(baseline))), max(2, int(math.ceil(baseline)))})
    results = []
    for count in candidates:
        length = (
            module_mm * math.cos(alpha_n)
            * (math.pi * (count - 0.5) + tooth_count * inv_alpha)
            + 2.0 * profile_shift * module_mm * math.sin(alpha_n)
        )
        half = length / 2.0
        contact_radius = math.sqrt(base_radius ** 2 + half ** 2)
        usable = (
            count < tooth_count
            and contact_radius > root_radius + 1e-9
            and contact_radius < outside_radius - 1e-9
        )
        results.append(
            {
                "span_tooth_count": count,
                "span_length_mm": length,
                "contact_radius_mm": contact_radius,
                "usable": usable,
            }
        )
    usable = [item for item in results if item["usable"]]
    if usable:
        best = min(usable, key=lambda item: abs(item["span_tooth_count"] - baseline))
    else:
        mid_flank = (root_radius + outside_radius) / 2.0
        best = min(results, key=lambda item: abs(item["contact_radius_mm"] - mid_flank))
    return {**best, "candidates": results}


def constant_chord(
    *,
    module_mm: float,
    profile_shift: float,
    pressure_angle_rad: float,
    pitch_radius: float,
    outside_radius: float,
) -> dict:
    chord = module_mm * (
        math.pi / 2.0 * math.cos(pressure_angle_rad) ** 2
        + profile_shift * math.sin(2.0 * pressure_angle_rad)
    )
    height = 0.5 * (2.0 * outside_radius - 2.0 * pitch_radius - chord * math.tan(pressure_angle_rad))
    return {
        "constant_chord_mm": chord,
        "constant_chord_height_mm": height,
    }


def over_pin_measurement(
    *,
    module_mm: float,
    tooth_count: int,
    profile_shift: float,
    pressure_angle_rad: float,
    pitch_radius: float,
    outside_radius: float,
    pin_diameter_mm: float,
    normal_pressure_angle_rad: float | None = None,
    transverse_pressure_angle_rad: float | None = None,
) -> dict:
    """Over-pin size; `module_mm` is the normal module.

    `inv(a_D) = inv(a_t) + D / (m_n z cos(a_n)) - pi / (2 z) + 2 x tan(a_n) / z`
    with `d_D = d cos(a_t) / cos(a_D)`.
    """
    alpha_n = pressure_angle_rad if normal_pressure_angle_rad is None else normal_pressure_angle_rad
    alpha_t = pressure_angle_rad if transverse_pressure_angle_rad is None else transverse_pressure_angle_rad
    inv_alpha = _involute(alpha_t)
    angle_ratio = (
        inv_alpha
        + pin_diameter_mm / (module_mm * tooth_count * math.cos(alpha_n))
        - math.pi / (2.0 * tooth_count)
        + 2.0 * profile_shift * math.tan(alpha_n) / tooth_count
    )
    # Invert inv(a_D) by bisection on [1e-6, 70 degrees].
    low, high = 1e-9, math.radians(70.0)
    if angle_ratio <= _involute(low):
        alpha_d = low
    elif angle_ratio >= _involute(high):
        alpha_d = high
    else:
        for _ in range(80):
            middle = (low + high) / 2.0
            if _involute(middle) < angle_ratio:
                low = middle
            else:
                high = middle
        alpha_d = (low + high) / 2.0
    center_diameter = 2.0 * pitch_radius * math.cos(alpha_t) / math.cos(alpha_d)
    if tooth_count % 2 == 0:
        measurement = center_diameter + pin_diameter_mm
    else:
        measurement = center_diameter * math.cos(math.pi / (2.0 * tooth_count)) + pin_diameter_mm
    fits_below_tips = center_diameter + pin_diameter_mm < 2.0 * outside_radius - 1e-9
    center_above_root = center_diameter / 2.0 > 0.0
    return {
        "pin_diameter_mm": pin_diameter_mm,
        "pin_pressure_angle_deg": math.degrees(alpha_d),
        "pin_center_diameter_mm": center_diameter,
        "over_pin_mm": measurement,
        "fits_below_tips": bool(fits_below_tips and center_above_root),
    }


def base_pitch(module_mm: float, pressure_angle_rad: float) -> float:
    return math.pi * module_mm * math.cos(pressure_angle_rad)


def chordal_tooth(
    *, pitch_radius: float, tooth_thickness_mm: float
) -> dict:
    half_angle = tooth_thickness_mm / (2.0 * pitch_radius)
    return {
        "chordal_tooth_thickness_mm": 2.0 * pitch_radius * math.sin(half_angle),
        "chordal_height_mm": pitch_radius * (1.0 - math.cos(half_angle)),
    }
