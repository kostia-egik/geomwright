"""Nominal internal cylindrical gear (ring gear) geometry and preview.

The internal gear is built on the same basic-rack systems as the external
cylindrical gear, but the material side is inverted:

* the tip circle is *inside* the reference circle and the root circle is
  *outside* it (GOST 19274-73, table 2, item 13):
  ``d_a2 = d2 - 2 (h_a* - x2 - 0.2) m`` and
  ``d_f2 = d2 + 2 (h_a* + c* + x2) m``;
* the tooth thickness at the reference circle is
  ``s2 = (pi/2 - 2 x2 tan(a)) m``; the mating space width carries the opposite
  sign and is the quantity measured by span and over-pin controls;
* the cut space is bounded by two involute flanks that narrow toward the root
  circle, closed by the root arc; toward the bore the space opens into the
  central hole, which is cut at the tip diameter.

The profile is ``nominal``: the flank is an exact involute down to the base
circle. When the tip circle lies inside the base circle (small tooth counts),
the nominal flank is extended radially to the tip and reported as such. A
generated-exact pinion-cutter envelope (dolbyak) is a separate future block.

The ring blank is an explicit input: the gear is cut from a ring whose outside
diameter the operator supplies, so the module does not silently invent a hub or
a rim.

Coordinates follow the transmission platform convention ``x = r sin(theta)``,
``y = r cos(theta)``, so the end view maps directly onto a KOMPAS sketch on the
YOZ plane. Linear values are millimetres, angles are radians unless the field
name says otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from .basic_racks import BasicRack, resolve_rack
from .internal_spec import InternalGearRequest
from .involute import error_item, involute, warning_item
from .measure import base_pitch, chordal_tooth, span_measurement
from .modules import describe_module
from .pins import select_standard_pin

# GOST 19274-73, table 2, item 13: the wheel tip is additionally offset by
# 0.2 m so the mating pinion tip keeps radial clearance.
INTERNAL_TIP_OFFSET_COEFFICIENT = 0.2

_EPS = 1e-12


def _polar(radius: float, angle: float) -> list[float]:
    return [radius * math.sin(angle), radius * math.cos(angle)]


def _radius(point: list[float]) -> float:
    return math.hypot(float(point[0]), float(point[1]))


def _angle(point: list[float]) -> float:
    return math.atan2(float(point[0]), float(point[1]))


def involute_polar(radius: float, base_radius: float) -> float:
    ratio = min(1.0, max(-1.0, base_radius / radius))
    return involute(math.acos(ratio))


def _arc_points(radius: float, start_angle: float, end_angle: float, count: int) -> list[list[float]]:
    if count <= 0:
        return [_polar(radius, start_angle), _polar(radius, end_angle)]
    return [
        _polar(radius, start_angle + (end_angle - start_angle) * index / count)
        for index in range(count + 1)
    ]


def _dedupe(points: list[list[float]], tolerance: float = 1e-9) -> list[list[float]]:
    result: list[list[float]] = []
    for point in points:
        if not result or math.dist(result[-1], point) > tolerance:
            result.append([float(point[0]), float(point[1])])
    return result


def _decimate(points: list[list[float]], target: int) -> list[list[float]]:
    if len(points) <= target:
        return points
    step = len(points) / target
    result = [points[int(index * step)] for index in range(target - 1)]
    result.append(points[-1])
    return _dedupe(result)


def _signed_area(polygon: list[list[float]]) -> float:
    area = 0.0
    for index in range(len(polygon) - 1):
        x1, y1 = polygon[index]
        x2, y2 = polygon[index + 1]
        area += x1 * y2 - x2 * y1
    return area / 2.0


@dataclass
class InternalGearGeometry:
    request: dict
    rack: BasicRack
    module_mm: float
    tooth_count: int
    pressure_angle_rad: float
    profile_shift: float
    face_width_mm: float
    ring_outside_radius: float
    rim_thickness_mm: float
    pitch_radius: float
    base_radius: float
    outside_radius: float
    root_radius: float
    addendum_mm: float
    dedendum_mm: float
    tooth_thickness_mm: float
    space_width_mm: float
    space_half_angle_rad: float
    root_space_half_angle_rad: float
    tip_space_half_angle_rad: float
    tip_arc_thickness_mm: float
    tip_thickness_normal_mm: float
    flank_start_radius_mm: float
    tip_below_base: bool
    root_fillet_radius_mm: float | None
    root_transition_mode: str = "sharp_root"
    root_transition_size_mm: float = 0.0
    right_transition_controls: list[list[float]] = field(default_factory=list)
    left_transition_controls: list[list[float]] = field(default_factory=list)
    root_middle_arc: list[list[float]] = field(default_factory=list)
    right_fillet_arc: list[list[float]] = field(default_factory=list)
    left_fillet_arc: list[list[float]] = field(default_factory=list)
    right_fillet_start: list[float] = field(default_factory=list)
    right_fillet_end: list[float] = field(default_factory=list)
    left_fillet_start: list[float] = field(default_factory=list)
    left_fillet_end: list[float] = field(default_factory=list)
    tip_chamfer_mm: float = 0.0
    tip_chamfer_angle_deg: float = 45.0
    tip_chamfer_depth_mm: float = 0.0
    helix_angle_rad: float = 0.0
    hand: str = "right"
    transverse_module_mm: float = 0.0
    base_helix_angle_rad: float = 0.0
    axial_pitch_mm: float = 0.0
    lead_mm: float = 0.0
    axial_overlap: float = 0.0
    closure_radius_mm: float = 0.0
    module_info: dict = field(default_factory=dict)
    right_flank_path: list[list[float]] = field(default_factory=list)
    right_involute_path: list[list[float]] = field(default_factory=list)
    left_involute_path: list[list[float]] = field(default_factory=list)
    tip_extension_path: list[list[float]] = field(default_factory=list)
    left_tip_extension_path: list[list[float]] = field(default_factory=list)
    tip_point_right: list[float] = field(default_factory=list)
    tip_point_left: list[float] = field(default_factory=list)
    root_point_right: list[float] = field(default_factory=list)
    root_point_left: list[float] = field(default_factory=list)
    hole_point_right: list[float] = field(default_factory=list)
    hole_point_left: list[float] = field(default_factory=list)
    space_outline: list[list[float]] = field(default_factory=list)
    space_cut_outline: list[list[float]] = field(default_factory=list)
    inner_profile_path: list[list[float]] = field(default_factory=list)
    period_outline: list[list[float]] = field(default_factory=list)
    full_ring_outline: list[list[float]] = field(default_factory=list)
    space_area_mm2: float = 0.0
    section_area_mm2: float = 0.0
    warnings: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


def _flank_angle(radius: float, *, space_half_angle: float, inv_alpha: float, base_radius: float) -> float:
    return space_half_angle + inv_alpha - involute_polar(radius, base_radius)


def _sample_flank(
    *,
    radius_start: float,
    radius_end: float,
    space_half_angle: float,
    inv_alpha: float,
    base_radius: float,
    count: int,
) -> list[list[float]]:
    if radius_end <= radius_start + 1e-9 or count <= 0:
        return []
    points: list[list[float]] = []
    for index in range(count + 1):
        radius = radius_start + (radius_end - radius_start) * index / count
        angle = _flank_angle(
            radius,
            space_half_angle=space_half_angle,
            inv_alpha=inv_alpha,
            base_radius=base_radius,
        )
        points.append(_polar(radius, angle))
    return points


def _flank_point_at(
    radius: float,
    *,
    space_half_angle: float,
    inv_alpha: float,
    base_radius: float,
) -> list[float]:
    angle = _flank_angle(
        radius,
        space_half_angle=space_half_angle,
        inv_alpha=inv_alpha,
        base_radius=base_radius,
    )
    return _polar(radius, angle)


def _cubic_bezier_points(controls: list[list[float]], count: int) -> list[list[float]]:
    points: list[list[float]] = []
    for index in range(max(2, count) + 1):
        t = index / max(2, count)
        u = 1.0 - t
        points.append(
            [
                u**3 * controls[0][axis]
                + 3.0 * u * u * t * controls[1][axis]
                + 3.0 * u * t * t * controls[2][axis]
                + t**3 * controls[3][axis]
                for axis in range(2)
            ]
        )
    return points


def _build_root_transition(
    *,
    root_radius: float,
    transition_size: float,
    flank_start_radius: float,
    space_half_angle: float,
    inv_alpha: float,
    base_radius: float,
) -> dict | None:
    """Build a tangent cubic transition from the involute to the root circle."""
    radial_room = root_radius - flank_start_radius
    if transition_size <= 1e-9 or radial_room <= 1e-9:
        return None
    flank_radius = max(flank_start_radius, root_radius - min(0.55 * transition_size, 0.45 * radial_room))
    flank_point = _flank_point_at(
        flank_radius,
        space_half_angle=space_half_angle,
        inv_alpha=inv_alpha,
        base_radius=base_radius,
    )
    flank_angle = _angle(flank_point)
    angular_span = min(0.90 * transition_size / root_radius, 0.85 * flank_angle)
    root_angle = max(0.0, flank_angle - angular_span)
    root_point = _polar(root_radius, root_angle)

    step = max(1e-5, 1e-4 * root_radius)
    lower = _flank_point_at(
        max(flank_start_radius, flank_radius - step),
        space_half_angle=space_half_angle,
        inv_alpha=inv_alpha,
        base_radius=base_radius,
    )
    upper = _flank_point_at(
        min(root_radius, flank_radius + step),
        space_half_angle=space_half_angle,
        inv_alpha=inv_alpha,
        base_radius=base_radius,
    )
    tangent_flank = [upper[0] - lower[0], upper[1] - lower[1]]
    tangent_length = math.hypot(*tangent_flank)
    if tangent_length <= 1e-12:
        return None
    tangent_flank = [value / tangent_length for value in tangent_flank]
    tangent_root = [-math.cos(root_angle), math.sin(root_angle)]
    chord = math.dist(flank_point, root_point)
    controls = [
        flank_point,
        [
            flank_point[0] + 0.42 * chord * tangent_flank[0],
            flank_point[1] + 0.42 * chord * tangent_flank[1],
        ],
        [
            root_point[0] - 0.36 * chord * tangent_root[0],
            root_point[1] - 0.36 * chord * tangent_root[1],
        ],
        root_point,
    ]
    return {
        "flank_point": flank_point,
        "root_point": root_point,
        "flank_radius": flank_radius,
        "controls": controls,
        "path": _cubic_bezier_points(controls, 20),
    }


def build_internal_gear_geometry(
    request: dict,
    *,
    flank_samples: int = 96,
    wheel_points_per_tooth: int = 56,
) -> InternalGearGeometry:
    """Build the complete nominal geometry for one internal cylindrical gear."""
    request = InternalGearRequest.model_validate(request).model_dump(exclude_none=True)
    rack = resolve_rack(
        str(request.get("standard") or "gost_13755_2015"),
        str(request.get("modification") or "a"),
        pressure_angle_deg=request.get("pressure_angle_deg"),
        addendum_coefficient=request.get("addendum_coefficient"),
        clearance_coefficient=request.get("clearance_coefficient"),
        root_fillet_coefficient=request.get("root_fillet_coefficient"),
    )
    module = float(request["module_mm"])
    tooth_count = int(request["tooth_count"])
    alpha_n = math.radians(float(rack.pressure_angle_deg))
    shift = float(request.get("profile_shift", 0.0))
    face_width = float(request.get("face_width_mm", 20.0))
    ring_outside_diameter = float(request.get("ring_outside_diameter_mm") or 0.0)
    helix_angle = math.radians(float(request.get("helix_angle_deg") or 0.0))
    hand = str(request.get("hand") or "right").strip().lower()
    if hand not in ("right", "left"):
        raise ValueError("hand must be 'right' or 'left'")

    ha = rack.addendum_coefficient
    clearance = rack.clearance_coefficient

    cos_beta = math.cos(helix_angle)
    module_t = module / cos_beta
    pressure_angle = math.atan(math.tan(alpha_n) / cos_beta)
    base_helix_angle = math.atan(math.tan(helix_angle) * math.cos(pressure_angle))
    pitch_radius = module_t * tooth_count / 2.0
    base_radius = pitch_radius * math.cos(pressure_angle)
    addendum = module * (ha - shift - INTERNAL_TIP_OFFSET_COEFFICIENT)
    dedendum = module * (ha + clearance + shift)
    outside_radius = pitch_radius - addendum
    root_radius = pitch_radius + dedendum
    ring_outside_radius = ring_outside_diameter / 2.0
    rim_thickness = ring_outside_radius - root_radius
    inv_alpha = involute(pressure_angle)

    warnings: list[dict] = []
    errors: list[dict] = []

    module_info = describe_module(module, rack.module_system)
    if not module_info["standard_value"]:
        warnings.append(
            warning_item(
                "gear_module_off_row",
                f"Module {module:g} mm is outside the {module_info['standard_edition']} rows.",
                module_mm=module,
                standard_edition=module_info["standard_edition"],
            )
        )
    below_range = rack.module_min is not None and module < rack.module_min - 1e-9
    above_range = rack.module_max is not None and (
        module >= rack.module_max - 1e-9
        if rack.module_max_exclusive
        else module > rack.module_max + 1e-9
    )
    if below_range or above_range:
        warnings.append(
            warning_item(
                "gear_standard_module_range",
                (
                    f"Module {module:g} mm is outside the applicable range of "
                    f"{rack.standard_edition}."
                ),
                module_mm=module,
                standard=rack.standard_edition,
                module_min=rack.module_min,
                module_max=rack.module_max,
                module_max_exclusive=rack.module_max_exclusive,
            )
        )
    if not rack.conformity_claim:
        warnings.append(
            warning_item(
                "gear_contour_modified",
                "Explicit coefficients make this a user-defined rack without a standard-conformity claim.",
            )
        )

    if outside_radius <= 0.0:
        errors.append(
            error_item(
                "gear_internal_tip_not_positive",
                "The internal tip diameter is not positive; reduce the tip offset or the profile shift.",
                tip_diameter_mm=2.0 * outside_radius,
            )
        )
    if root_radius <= outside_radius + 1e-9:
        errors.append(
            error_item(
                "gear_internal_invalid_radii",
                "The internal root diameter must exceed the tip diameter.",
                tip_diameter_mm=2.0 * outside_radius,
                root_diameter_mm=2.0 * root_radius,
            )
        )
    if ring_outside_diameter <= 0.0:
        errors.append(
            error_item(
                "gear_internal_ring_outside_missing",
                "The ring blank outside diameter must be positive.",
                ring_outside_diameter_mm=ring_outside_diameter,
            )
        )
    elif rim_thickness <= 0.0:
        errors.append(
            error_item(
                "gear_internal_ring_outside_below_root",
                "The ring blank outside diameter must exceed the internal root diameter.",
                ring_outside_diameter_mm=ring_outside_diameter,
                root_diameter_mm=2.0 * root_radius,
            )
        )
    elif rim_thickness < max(1.5, module) - 1e-9:
        warnings.append(
            warning_item(
                "gear_internal_ring_wall_thin",
                (
                    "The radial ring wall above the tooth roots is thin for this module; "
                    "verify the blank and the clamping."
                ),
                rim_thickness_mm=rim_thickness,
                recommended_min_mm=max(1.5, module),
            )
        )

    eta_tooth = math.pi / (2.0 * tooth_count) - 2.0 * shift * math.tan(alpha_n) / tooth_count
    space_half_angle = math.pi / tooth_count - eta_tooth
    tooth_thickness = 2.0 * pitch_radius * eta_tooth
    space_width = 2.0 * pitch_radius * space_half_angle
    if tooth_thickness <= 0.0:
        errors.append(
            error_item(
                "gear_internal_tooth_thickness_negative",
                "The internal tooth thickness at the reference circle is not positive.",
                tooth_thickness_mm=tooth_thickness,
                profile_shift=shift,
            )
        )
    if space_width <= 0.0:
        errors.append(
            error_item(
                "gear_internal_space_width_negative",
                "The internal tooth space at the reference circle is not positive.",
                space_width_mm=space_width,
                profile_shift=shift,
            )
        )

    flank_start_radius = max(outside_radius, base_radius)
    tip_below_base = outside_radius < base_radius - 1e-9
    if tip_below_base:
        warnings.append(
            warning_item(
                "gear_internal_tip_below_base",
                (
                    "The tip circle lies inside the base circle; the nominal flank is "
                    "extended radially to the tip. A pinion-cutter (dolbyak) envelope is "
                    "a separate generated-exact block."
                ),
                tip_diameter_mm=2.0 * outside_radius,
                base_diameter_mm=2.0 * base_radius,
            )
        )

    root_space_half_angle = 0.0
    tip_space_half_angle = 0.0
    tip_arc_thickness = 0.0
    tip_thickness_normal = 0.0
    if outside_radius > 0.0 and root_radius > base_radius:
        root_space_half_angle = _flank_angle(
            root_radius,
            space_half_angle=space_half_angle,
            inv_alpha=inv_alpha,
            base_radius=base_radius,
        )
        tip_space_half_angle = _flank_angle(
            flank_start_radius,
            space_half_angle=space_half_angle,
            inv_alpha=inv_alpha,
            base_radius=base_radius,
        )
        tooth_tip_half_angle = math.pi / tooth_count - tip_space_half_angle
        tip_arc_thickness = 2.0 * outside_radius * tooth_tip_half_angle
        tip_thickness_normal = tip_arc_thickness * math.cos(base_helix_angle)
        if tooth_tip_half_angle <= 0.0:
            errors.append(
                error_item(
                    "gear_internal_tip_vanishes",
                    "The internal tooth flanks cross before the tip circle; the tooth tip is not constructible.",
                    tip_thickness_mm=tip_arc_thickness,
                    profile_shift=shift,
                )
            )
        elif tip_thickness_normal < 0.25 * module:
            warnings.append(
                warning_item(
                    "gear_tip_thickness_low",
                    "Tooth tip thickness is below 0.25 m; the tip may be pointed and sensitive to tolerances.",
                    tip_thickness_mm=tip_arc_thickness,
                    tip_thickness_normal_mm=tip_thickness_normal,
                )
            )
        elif tip_thickness_normal < 0.3 * module:
            warnings.append(
                warning_item(
                    "gear_tip_thickness_below_recommendation",
                    "Tooth tip thickness is below the 0.30 m recommendation.",
                    tip_thickness_mm=tip_arc_thickness,
                    tip_thickness_normal_mm=tip_thickness_normal,
                )
            )
        if root_space_half_angle <= 0.0:
            errors.append(
                error_item(
                    "gear_internal_root_space_collapsed",
                    "The internal space closes before the root circle; the root arc is not constructible.",
                    root_space_half_angle_rad=root_space_half_angle,
                    profile_shift=shift,
                )
            )
        elif root_space_half_angle >= math.pi / tooth_count - 1e-9:
            errors.append(
                error_item(
                    "gear_internal_space_reaches_tooth_center",
                    "The internal space reaches the neighbouring tooth centre; the profile shift is too large.",
                    root_space_half_angle_rad=root_space_half_angle,
                    limit_rad=math.pi / tooth_count,
                )
            )
    else:
        if root_radius <= base_radius + 1e-9:
            errors.append(
                error_item(
                    "gear_internal_root_below_base",
                    "The internal root circle does not reach the base circle; no usable flank exists.",
                    root_diameter_mm=2.0 * root_radius,
                    base_diameter_mm=2.0 * base_radius,
                )
            )

    helical = helix_angle > 1e-9
    axial_pitch = math.pi * module / math.sin(helix_angle) if helical else 0.0
    lead = axial_pitch * tooth_count
    axial_overlap = face_width / axial_pitch if axial_pitch > 0.0 else 0.0
    if helical and axial_overlap < 1.0 - 1e-9:
        warnings.append(
            warning_item(
                "gear_axial_overlap",
                "Axial overlap is below 1.0; tooth engagement is not continuous across the face width.",
                axial_overlap=axial_overlap,
                axial_pitch_mm=axial_pitch,
                face_width_mm=face_width,
            )
        )

    tip_chamfer = float(request.get("tip_chamfer_mm") or 0.0)
    tip_chamfer_angle = float(request.get("tip_chamfer_angle_deg") or 45.0)
    tip_chamfer_depth = (
        tip_chamfer * math.tan(math.radians(tip_chamfer_angle)) if tip_chamfer > 0.0 else 0.0
    )
    if tip_chamfer > 0.0:
        if 2.0 * tip_chamfer >= face_width - 1e-9:
            errors.append(
                error_item(
                    "gear_internal_tip_chamfer_exceeds_face_width",
                    "The tooth-tip chamfers from both faces meet; reduce the chamfer width.",
                    tip_chamfer_mm=tip_chamfer,
                    face_width_mm=face_width,
                )
            )
        if tip_chamfer_depth >= (root_radius - outside_radius) - 1e-9:
            errors.append(
                error_item(
                    "gear_internal_tip_chamfer_reaches_root",
                    "The tooth-tip chamfer reaches the root circle; reduce the width or angle.",
                    tip_chamfer_mm=tip_chamfer,
                    tip_chamfer_angle_deg=tip_chamfer_angle,
                    tip_chamfer_depth_mm=tip_chamfer_depth,
                    tooth_height_mm=root_radius - outside_radius,
                )
            )

    geometry = InternalGearGeometry(
        request=dict(request),
        rack=rack,
        module_mm=module,
        tooth_count=tooth_count,
        pressure_angle_rad=pressure_angle,
        profile_shift=shift,
        face_width_mm=face_width,
        ring_outside_radius=ring_outside_radius,
        rim_thickness_mm=rim_thickness,
        pitch_radius=pitch_radius,
        base_radius=base_radius,
        outside_radius=outside_radius,
        root_radius=root_radius,
        addendum_mm=addendum,
        dedendum_mm=dedendum,
        tooth_thickness_mm=tooth_thickness,
        space_width_mm=space_width,
        space_half_angle_rad=space_half_angle,
        root_space_half_angle_rad=root_space_half_angle,
        tip_space_half_angle_rad=tip_space_half_angle,
        tip_arc_thickness_mm=tip_arc_thickness,
        tip_thickness_normal_mm=tip_thickness_normal,
        flank_start_radius_mm=flank_start_radius,
        tip_below_base=tip_below_base,
        root_fillet_radius_mm=(
            None if rack.fillet_coefficient is None else rack.fillet_coefficient * module
        ),
        tip_chamfer_mm=tip_chamfer,
        tip_chamfer_angle_deg=tip_chamfer_angle,
        tip_chamfer_depth_mm=tip_chamfer_depth,
        helix_angle_rad=helix_angle,
        hand=hand,
        transverse_module_mm=module_t,
        base_helix_angle_rad=base_helix_angle,
        axial_pitch_mm=axial_pitch,
        lead_mm=lead,
        axial_overlap=axial_overlap,
        module_info=module_info,
        warnings=warnings,
        errors=errors,
    )
    if errors:
        return geometry

    # The native internal-gear profile uses a generated transition represented
    # by a cubic Bezier, not a constant-radius arc. The selected rack radius is
    # only a scale bound for this nominal transition.
    transition_target = min(float(geometry.root_fillet_radius_mm or 0.0), 0.30 * module)
    transition_solution = None
    transition_scales = (1.0, 0.75, 0.5, 0.35, 0.25, 0.15)
    if transition_target > 1e-9:
        for scale in transition_scales:
            candidate = _build_root_transition(
                root_radius=root_radius,
                transition_size=transition_target * scale,
                flank_start_radius=flank_start_radius,
                space_half_angle=space_half_angle,
                inv_alpha=inv_alpha,
                base_radius=base_radius,
            )
            if candidate is not None and _angle(candidate["root_point"]) >= -1e-9:
                transition_solution = candidate
                geometry.root_transition_size_mm = transition_target * scale
                break
        if transition_solution is None:
            warnings.append(
                warning_item(
                    "gear_internal_root_transition_unresolved",
                    (
                        "The Bezier root transition does not fit the tooth space; the "
                        "nominal root is drawn with the root arc and sharp corners."
                    ),
                    requested_scale_mm=transition_target,
                )
            )

    flank_root_radius = root_radius
    if transition_solution is not None:
        flank_root_radius = float(transition_solution["flank_radius"])
    sample_count = max(24, min(240, int(
        flank_samples * max(1.0, (root_radius - flank_start_radius) / module)
    )))
    right_involute = _sample_flank(
        radius_start=flank_start_radius,
        radius_end=flank_root_radius,
        space_half_angle=space_half_angle,
        inv_alpha=inv_alpha,
        base_radius=base_radius,
        count=sample_count,
    )
    right_involute = list(reversed(right_involute))  # root transition tangent -> flank start
    tip_point_right = _polar(outside_radius, tip_space_half_angle)
    root_point_right = _polar(root_radius, root_space_half_angle)
    tip_point_left = _polar(outside_radius, -tip_space_half_angle)
    root_point_left = _polar(root_radius, -root_space_half_angle)
    right_flank = list(right_involute)
    tip_extension: list[list[float]] = []
    if tip_below_base:
        tip_extension = [list(right_flank[-1]), list(tip_point_right)]
        right_flank.append(list(tip_point_right))
    if not right_flank or (
        transition_solution is None
        and math.dist(right_flank[0], root_point_right) > 1e-6
    ):
        right_flank.insert(0, list(root_point_right))
    if math.dist(right_flank[-1], tip_point_right) > 1e-6:
        right_flank.append(list(tip_point_right))

    left_involute = [[-point[0], point[1]] for point in reversed(right_involute)]
    left_tip_extension = [[-point[0], point[1]] for point in reversed(tip_extension)]
    left_flank = [[-point[0], point[1]] for point in reversed(right_flank)]

    right_fillet_arc: list[list[float]] = []
    left_fillet_arc: list[list[float]] = []
    root_mid_arc: list[list[float]] = []
    if transition_solution is not None:
        right_fillet_arc = [list(point) for point in transition_solution["path"]]
        left_fillet_arc = [[-point[0], point[1]] for point in right_fillet_arc]
        root_theta = _angle(transition_solution["root_point"])
        if root_theta > 1e-7:
            root_mid_arc = _arc_points(root_radius, -root_theta, root_theta, 10)
        else:
            root_mid_arc = [list(transition_solution["root_point"])]
        geometry.root_transition_mode = "cubic_bezier_root_transition"
        geometry.right_fillet_arc = _dedupe(right_fillet_arc)
        geometry.left_fillet_arc = _dedupe(left_fillet_arc)
        geometry.root_middle_arc = _dedupe(root_mid_arc)
        geometry.right_transition_controls = [list(point) for point in transition_solution["controls"]]
        geometry.left_transition_controls = [
            [-point[0], point[1]] for point in transition_solution["controls"]
        ]
        geometry.right_fillet_start = list(transition_solution["flank_point"])
        geometry.right_fillet_end = list(transition_solution["root_point"])
        geometry.left_fillet_start = [-transition_solution["flank_point"][0], transition_solution["flank_point"][1]]
        geometry.left_fillet_end = [-transition_solution["root_point"][0], transition_solution["root_point"][1]]

    tip_arc_steps = max(4, int(16 * max(2.0 * tip_space_half_angle, 1e-3) / 0.1))
    root_arc_steps = max(4, int(16 * max(2.0 * root_space_half_angle, 1e-3) / 0.1))
    tip_arc = _arc_points(outside_radius, tip_space_half_angle, -tip_space_half_angle, tip_arc_steps)
    root_arc = _arc_points(root_radius, -root_space_half_angle, root_space_half_angle, root_arc_steps)
    contour_tolerance = max(1e-9, module * 1e-6)
    right_fillet_reverse = list(reversed(right_fillet_arc)) if transition_solution is not None else []

    if transition_solution is not None:
        space_surface = _dedupe(
            [
                *right_flank,
                *tip_arc[1:],
                *left_flank[1:],
                *left_fillet_arc[1:],
                *root_mid_arc[1:],
                *right_fillet_reverse[1:],
                [float(right_flank[0][0]), float(right_flank[0][1])],
            ],
            tolerance=contour_tolerance,
        )
    else:
        space_surface = _dedupe(
            [
                *right_flank,
                *tip_arc[1:],
                *left_flank[1:],
                *root_arc[1:],
                [float(right_flank[0][0]), float(right_flank[0][1])],
            ],
            tolerance=contour_tolerance,
        )

    # Closure inside the central bore: the space opens into the hole, so the cut
    # contour must pass through the void with a bounded overshoot.
    closure_radius = max(
        0.3 * outside_radius,
        outside_radius - max(0.5 * module, 0.06 * max(outside_radius, 1.0)),
    )
    closure_radius = min(closure_radius, outside_radius - 0.02 * module)
    if closure_radius <= 1e-6:
        errors.append(
            error_item(
                "gear_internal_closure_invalid",
                "The central bore is too small for a bounded cut closure.",
                outside_radius_mm=outside_radius,
            )
        )
        geometry.errors = errors
        return geometry
    hole_point_right = _polar(closure_radius, tip_space_half_angle)
    hole_point_left = _polar(closure_radius, -tip_space_half_angle)
    hole_arc_steps = max(4, int(16 * max(2.0 * tip_space_half_angle, 1e-3) / 0.1))
    hole_arc = _arc_points(closure_radius, tip_space_half_angle, -tip_space_half_angle, hole_arc_steps)
    if transition_solution is not None:
        space_cut = _dedupe(
            [
                *right_flank,
                *hole_arc[1:],
                *left_flank[1:],
                *left_fillet_arc[1:],
                *root_mid_arc[1:],
                *right_fillet_reverse[1:],
                [float(right_flank[0][0]), float(right_flank[0][1])],
            ],
            tolerance=contour_tolerance,
        )
    else:
        space_cut = _dedupe(
            [
                *right_flank,
                *hole_arc[1:],
                *left_flank[1:],
                *root_arc[1:],
                [float(right_flank[0][0]), float(right_flank[0][1])],
            ],
            tolerance=contour_tolerance,
        )
    space_area = abs(_signed_area(space_surface))

    # One pitch of the internal tooth boundary, ordered with increasing theta.
    step_angle = 2.0 * math.pi / tooth_count
    tip_arc_mid = _arc_points(
        outside_radius,
        tip_space_half_angle,
        step_angle - tip_space_half_angle,
        tip_arc_steps,
    )
    if transition_solution is not None:
        root_theta = _angle(transition_solution["root_point"])
        root_mid_half = (
            _arc_points(root_radius, 0.0, root_theta, max(3, root_arc_steps // 2))
            if root_theta > 1e-7
            else [list(transition_solution["root_point"])]
        )
        right_fillet_segment = list(right_fillet_reverse)
        next_flank = [
            _polar(_radius(point), step_angle - _angle(point))
            for point in reversed(right_flank)
        ]
        next_fillet = [
            _polar(_radius(point), step_angle - _angle(point))
            for point in right_fillet_arc
        ]
        next_root_half = _arc_points(
            root_radius,
            step_angle - root_theta,
            step_angle,
            max(3, root_arc_steps // 2),
        )
        period = _dedupe(
            [
                *root_mid_half,
                *right_fillet_segment[1:],
                *right_flank[1:],
                *tip_arc_mid[1:],
                *next_flank[1:],
                *next_fillet[1:],
                *next_root_half[1:],
            ],
            tolerance=contour_tolerance,
        )
    else:
        root_arc_half = _arc_points(root_radius, 0.0, root_space_half_angle, max(3, root_arc_steps // 2))
        next_flank = [
            _polar(_radius(point), step_angle - _angle(point))
            for point in reversed(right_flank)
        ]
        next_root_half = _arc_points(
            root_radius,
            step_angle - root_space_half_angle,
            step_angle,
            max(4, root_arc_steps // 2),
        )
        period = _dedupe(
            [
                *root_arc_half,
                *right_flank[1:],
                *tip_arc_mid[1:],
                *next_flank[1:],
                *next_root_half[1:],
            ],
            tolerance=contour_tolerance,
        )
    # Preview sampling keeps every segment's own shape. A single global
    # decimation across the whole period used to cut the small root arcs into
    # chords and broke the junctions between neighbouring teeth.
    budget = max(12, min(int(wheel_points_per_tooth), max(12, 4096 // max(1, tooth_count))))
    flank_budget = max(8, budget // 2)
    fillet_budget = max(6, budget // 4)
    tip_budget = max(4, budget // 6)
    if transition_solution is not None:
        wheel_period = _dedupe(
            [
                *_decimate(root_mid_half, 3),
                *_decimate(right_fillet_segment, fillet_budget)[1:],
                *_decimate(right_flank, flank_budget)[1:],
                *_decimate(tip_arc_mid, tip_budget)[1:],
                *_decimate(next_flank, flank_budget)[1:],
                *_decimate(next_fillet, fillet_budget)[1:],
                *_decimate(next_root_half, 3)[1:],
            ],
            tolerance=contour_tolerance,
        )
    else:
        wheel_period = _dedupe(
            [
                *_decimate(root_arc_half, 3),
                *_decimate(right_flank, flank_budget)[1:],
                *_decimate(tip_arc_mid, tip_budget)[1:],
                *_decimate(next_flank, flank_budget)[1:],
                *_decimate(next_root_half, 3)[1:],
            ],
            tolerance=contour_tolerance,
        )
    inner_points: list[list[float]] = []
    for index in range(tooth_count):
        rotated = [
            _polar(_radius(point), _angle(point) + index * step_angle)
            for point in wheel_period
        ]
        if inner_points:
            rotated = rotated[1:]
        inner_points.extend(rotated)
    inner_points = _dedupe(inner_points)
    if math.dist(inner_points[0], inner_points[-1]) > 1e-9:
        inner_points.append(inner_points[0])

    outer_steps = max(120, min(720, tooth_count * 8))
    outer_arc = _arc_points(ring_outside_radius, step_angle * tooth_count, 0.0, outer_steps)
    ring_outline = _dedupe(
        [*inner_points, *outer_arc, [float(inner_points[0][0]), float(inner_points[0][1])]],
        tolerance=max(1e-9, module * 1e-6),
    )
    if _signed_area(ring_outline) < 0.0:
        ring_outline = list(reversed(ring_outline))
        inner_points = list(reversed(inner_points))
        period = list(reversed(period))

    section_area = (
        math.pi * ring_outside_radius ** 2
        - math.pi * outside_radius ** 2
        - tooth_count * space_area
    )
    if section_area <= 0.0 or not math.isfinite(section_area):
        errors.append(
            error_item(
                "gear_internal_section_area_invalid",
                "The ring cross-section area is not positive; check the ring diameter and profile shift.",
                section_area_mm2=section_area,
            )
        )
        geometry.errors = errors
        return geometry

    geometry.right_flank_path = _dedupe(right_flank)
    geometry.right_involute_path = _dedupe(right_involute)
    geometry.left_involute_path = _dedupe(left_involute)
    geometry.tip_extension_path = _dedupe(tip_extension)
    geometry.left_tip_extension_path = _dedupe(left_tip_extension)
    geometry.tip_point_right = list(tip_point_right)
    geometry.tip_point_left = list(tip_point_left)
    geometry.root_point_right = list(root_point_right)
    geometry.root_point_left = list(root_point_left)
    geometry.hole_point_right = list(hole_point_right)
    geometry.hole_point_left = list(hole_point_left)
    geometry.closure_radius_mm = closure_radius
    geometry.space_outline = space_surface
    geometry.space_cut_outline = space_cut
    geometry.inner_profile_path = inner_points
    geometry.period_outline = period
    geometry.full_ring_outline = ring_outline
    geometry.space_area_mm2 = space_area
    geometry.section_area_mm2 = section_area
    return geometry


def _invert_involute(value: float, *, low: float = 1e-9, high: float = math.radians(70.0)) -> float:
    if value <= involute(low):
        return low
    if value >= involute(high):
        return high
    for _ in range(80):
        middle = (low + high) / 2.0
        if involute(middle) < value:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def internal_over_pin_measurement(
    *,
    module_mm: float,
    tooth_count: int,
    profile_shift: float,
    pressure_angle_rad: float,
    pitch_radius: float,
    tip_radius: float,
    root_radius: float,
    pin_diameter_mm: float,
    normal_pressure_angle_rad: float | None = None,
    transverse_pressure_angle_rad: float | None = None,
) -> dict:
    """Over-pin control per GOST 19274-73, table 4, items 12-17 (wheel)."""
    alpha_n = pressure_angle_rad if normal_pressure_angle_rad is None else normal_pressure_angle_rad
    alpha_t = pressure_angle_rad if transverse_pressure_angle_rad is None else transverse_pressure_angle_rad
    angle_ratio = (
        involute(alpha_t)
        + pin_diameter_mm / (module_mm * tooth_count * math.cos(alpha_n))
        - math.pi / (2.0 * tooth_count)
        - 2.0 * profile_shift * math.tan(alpha_n) / tooth_count
    )
    alpha_d = _invert_involute(angle_ratio)
    center_diameter = 2.0 * pitch_radius * math.cos(alpha_t) / math.cos(alpha_d)
    if tooth_count % 2 == 0:
        measurement = center_diameter - pin_diameter_mm
    else:
        measurement = center_diameter * math.cos(math.pi / (2.0 * tooth_count)) - pin_diameter_mm
    pin_inner = center_diameter - pin_diameter_mm
    pin_outer = center_diameter + pin_diameter_mm
    fits = (
        center_diameter > 0.0
        and pin_inner < 2.0 * tip_radius - 1e-9
        and pin_outer < 2.0 * root_radius - 1e-9
    )
    return {
        "pin_diameter_mm": pin_diameter_mm,
        "pin_pressure_angle_deg": math.degrees(alpha_d),
        "pin_center_diameter_mm": center_diameter,
        "over_pin_mm": measurement,
        "fits_below_tips": bool(fits),
    }


def internal_constant_chord(
    *,
    module_mm: float,
    profile_shift: float,
    pressure_angle_rad: float,
    pitch_radius: float,
    tip_radius: float,
) -> dict:
    """Constant chord and its height for the internal wheel (GOST 19274-73)."""
    chord = module_mm * (
        math.pi / 2.0 * math.cos(pressure_angle_rad) ** 2
        - profile_shift * math.sin(2.0 * pressure_angle_rad)
    )
    height = 0.5 * (2.0 * pitch_radius - 2.0 * tip_radius - chord * math.tan(pressure_angle_rad))
    return {
        "constant_chord_mm": chord,
        "constant_chord_height_mm": height,
    }


def internal_tooth_fraction(geometry: InternalGearGeometry, radius: float) -> float:
    """Circumferential material fraction of the internal wheel at ``radius``."""
    probe = max(float(radius), geometry.flank_start_radius_mm)
    theta_space = _flank_angle(
        probe,
        space_half_angle=geometry.space_half_angle_rad,
        inv_alpha=involute(geometry.pressure_angle_rad),
        base_radius=geometry.base_radius,
    )
    return max(0.0, min(1.0, (math.pi - geometry.tooth_count * theta_space) / math.pi))


def internal_tip_chamfer_volume(
    geometry: InternalGearGeometry,
    *,
    width_mm: float,
    angle_deg: float,
) -> float:
    """Material removed by two bore-edge chamfers on the internal tooth tips."""
    if width_mm <= 0.0:
        return 0.0
    depth = width_mm * math.tan(math.radians(angle_deg))
    tip = geometry.outside_radius
    root = geometry.root_radius
    if depth <= 0.0 or depth >= root - tip:
        return 0.0
    steps = 64
    volume = 0.0
    for index in range(steps):
        rho = tip + depth * (index + 0.5) / steps
        axial = width_mm * (1.0 - (rho - tip) / depth)
        fraction = internal_tooth_fraction(geometry, rho)
        volume += fraction * 2.0 * math.pi * rho * axial * (depth / steps)
    return 2.0 * volume


def _check(
    code: str,
    status: str,
    message: str,
    *,
    value=None,
    limit=None,
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


def evaluate_internal_gear_checks(geometry: InternalGearGeometry, measurements: dict) -> dict:
    """Combine scalar diagnostics and control measurements into one report."""
    checks: list[dict] = []
    checks.append(
        _check(
            "gear_internal_radii",
            "ok",
            "Internal tip, base, pitch and root diameters are ordered and positive.",
            value={
                "tip_diameter_mm": 2.0 * geometry.outside_radius,
                "base_diameter_mm": 2.0 * geometry.base_radius,
                "pitch_diameter_mm": 2.0 * geometry.pitch_radius,
                "root_diameter_mm": 2.0 * geometry.root_radius,
                "ring_outside_diameter_mm": 2.0 * geometry.ring_outside_radius,
            },
        )
    )
    checks.append(
        _check(
            "gear_internal_ring_wall",
            "warning" if geometry.rim_thickness_mm < max(1.5, geometry.module_mm) - 1e-9 else "ok",
            "Radial ring wall from the tooth root to the blank outside diameter.",
            value=geometry.rim_thickness_mm,
            limit=max(1.5, geometry.module_mm),
            unit="mm",
        )
    )
    checks.append(
        _check(
            "gear_internal_tip_below_base",
            "warning" if geometry.tip_below_base else "ok",
            (
                "The tip circle is inside the base circle; the nominal flank is extended radially."
                if geometry.tip_below_base
                else "The involute flank reaches the tip circle."
            ),
            value=2.0 * geometry.outside_radius,
            limit=2.0 * geometry.base_radius,
            unit="mm",
        )
    )
    tip_value = (
        geometry.tip_thickness_normal_mm
        if geometry.helix_angle_rad > 1e-9
        else geometry.tip_arc_thickness_mm
    )
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
            "gear_internal_tip_thickness",
            tip_status,
            "Internal tooth thickness on the tip circle against the 0.30 m recommendation.",
            value=tip_value,
            limit=tip_limit,
            unit="mm",
        )
    )
    checks.append(
        _check(
            "gear_internal_root_space",
            "ok" if geometry.root_space_half_angle_rad > 0.0 else "error",
            "Angular half-width of the tooth space at the internal root circle.",
            value=geometry.root_space_half_angle_rad,
            limit=math.pi / max(1, geometry.tooth_count),
            unit="rad",
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
            "ok" if rack.conformity_claim else "warning",
            (
                f"Basic rack {rack.name_ru} ({rack.standard} · {rack.modification}): "
                f"{rack.standard_edition}."
                if rack.conformity_claim
                else "Explicit coefficients define a user-defined rack without a standard-conformity claim."
            ),
            value={"standard": rack.standard, "modification": rack.modification},
        )
    )
    checks.append(
        _check(
            "gear_internal_root_envelope",
            "ok",
            (
                "Nominal envelope: involute flank with a cubic Bezier root transition and the root arc; "
                "the exact pinion-cutter tip is a separate generated-exact block."
            ),
            value=geometry.root_transition_mode,
        )
    )
    checks.append(
        _check(
            "gear_internal_root_transition",
            "ok",
            (
                "Cubic Bezier transition tangent to the involute flank and root circle."
                if geometry.root_transition_mode == "cubic_bezier_root_transition"
                else "The tooth space is drawn with a sharp nominal root."
            ),
            value=geometry.root_transition_size_mm,
            limit=geometry.root_fillet_radius_mm,
            unit="mm",
        )
    )
    span = measurements.get("span") or {}
    checks.append(
        _check(
            "gear_span_measurement",
            "ok" if span.get("usable") else "warning",
            (
                f"Span length over {span.get('span_tooth_count')} spaces; the contact radius "
                "must stay between the internal tip and root circles."
            ),
            value=span.get("span_length_mm"),
            limit=span.get("span_tooth_count"),
            unit="mm",
        )
    )
    over_pin = measurements.get("over_pin") or {}
    if over_pin.get("available") is False:
        checks.append(
            _check(
                "gear_over_pin",
                "ok",
                "Over-pin control is not performed for helical internal gears (GOST 19274-73, table 4).",
                value=None,
                limit=None,
                unit="mm",
            )
        )
    else:
        checks.append(
            _check(
                "gear_over_pin",
                "ok" if over_pin.get("fits_below_tips") else "warning",
                "Over-pin control with pins in the internal tooth spaces.",
                value=over_pin.get("over_pin_mm"),
                limit=over_pin.get("pin_diameter_mm"),
                unit="mm",
            )
        )
    if geometry.helix_angle_rad > 1e-9:
        checks.append(
            _check(
                "gear_axial_overlap",
                "ok" if geometry.axial_overlap >= 1.0 - 1e-9 else "warning",
                "Axial overlap ratio b / p_x for the helical internal gear.",
                value=geometry.axial_overlap,
                limit=1.0,
                unit="x",
            )
        )
    if geometry.tip_chamfer_mm > 0.0:
        checks.append(
            _check(
                "gear_internal_tip_chamfer",
                "ok",
                "End chamfer on the internal tooth tips at both bore edges.",
                value=geometry.tip_chamfer_mm,
                limit=geometry.tip_chamfer_angle_deg,
                unit="mm/deg",
            )
        )
    errors = list(geometry.errors)
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


def build_internal_gear_preview(
    request: dict,
    *,
    wheel_points_per_tooth: int = 56,
) -> dict:
    """Validate the request and return the complete nominal internal-gear analysis."""
    module = float(request["module_mm"])
    tooth_count = int(request["tooth_count"])
    geometry = build_internal_gear_geometry(
        request,
        wheel_points_per_tooth=wheel_points_per_tooth,
    )
    warning_items = list(geometry.warnings)
    warnings = [str(item["message"]) for item in warning_items]
    if geometry.errors:
        return {
            "success": False,
            "family": "gear_internal",
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
    alpha_n = math.radians(geometry.rack.pressure_angle_deg)
    alpha_t = geometry.pressure_angle_rad
    helical = geometry.helix_angle_rad > 1e-9
    measurements: dict = {
        "span": span_measurement(
            module_mm=module,
            tooth_count=tooth_count,
            profile_shift=geometry.profile_shift,
            pressure_angle_rad=alpha_t,
            base_radius=geometry.base_radius,
            outside_radius=geometry.root_radius,
            root_radius=geometry.outside_radius,
            normal_pressure_angle_rad=alpha_n,
            transverse_pressure_angle_rad=alpha_t,
        ),
        "constant_chord": internal_constant_chord(
            module_mm=module,
            profile_shift=geometry.profile_shift,
            pressure_angle_rad=alpha_n,
            pitch_radius=geometry.pitch_radius,
            tip_radius=geometry.outside_radius,
        ),
        "base_pitch_mm": base_pitch(module, alpha_n),
        "normal_tooth_thickness_mm": module
        * (math.pi / 2.0 - 2.0 * geometry.profile_shift * math.tan(alpha_n)),
        **chordal_tooth(
            pitch_radius=geometry.pitch_radius,
            tooth_thickness_mm=geometry.tooth_thickness_mm,
        ),
    }
    if helical:
        measurements["over_pin"] = {
            "available": False,
            "reason": "helical_internal_over_pin_not_performed",
            "over_pin_mm": None,
            "pin_diameter_mm": None,
            "pin_source": "not_performed_helical",
            "fits_below_tips": False,
        }
    else:
        pin_diameter = request.get("pin_diameter_mm")
        pin_kwargs = {
            "module_mm": module,
            "tooth_count": tooth_count,
            "profile_shift": geometry.profile_shift,
            "pressure_angle_rad": alpha_t,
            "pitch_radius": geometry.pitch_radius,
            "tip_radius": geometry.outside_radius,
            "root_radius": geometry.root_radius,
            "normal_pressure_angle_rad": alpha_n,
            "transverse_pressure_angle_rad": alpha_t,
        }

        def pin_probe(diameter: float) -> dict:
            return internal_over_pin_measurement(pin_diameter_mm=diameter, **pin_kwargs)

        if pin_diameter is None:
            preferred = 1.5 * module
            standard = select_standard_pin(
                preferred, lambda diameter: pin_probe(diameter).get("fits_below_tips")
            )
            if standard is not None:
                pin_diameter = standard["diameter_mm"]
                pin_source = standard["source"]
            else:
                chosen = None
                for candidate, source in (
                    (preferred, "nominal_1.5_m"),
                    (1.3 * module, "fallback_1.3_m"),
                    (1.1 * module, "fallback_1.1_m"),
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
        measurements["over_pin"] = {
            **pin_probe(pin_diameter),
            "available": True,
            "pin_source": pin_source,
        }
    report = evaluate_internal_gear_checks(geometry, measurements)
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
        "ring_outside_diameter_mm": 2.0 * geometry.ring_outside_radius,
        "rim_thickness_mm": geometry.rim_thickness_mm,
        "pitch_diameter_mm": 2.0 * geometry.pitch_radius,
        "base_diameter_mm": 2.0 * geometry.base_radius,
        "tip_diameter_mm": 2.0 * geometry.outside_radius,
        "root_diameter_mm": 2.0 * geometry.root_radius,
        "tooth_thickness_mm": geometry.tooth_thickness_mm,
        "space_width_mm": geometry.space_width_mm,
        "tip_thickness_mm": geometry.tip_arc_thickness_mm,
        "root_fillet_radius_mm": geometry.root_fillet_radius_mm,
        "root_transition_size_mm": geometry.root_transition_size_mm,
        "root_transition_mode": geometry.root_transition_mode,
        "tip_chamfer_mm": geometry.tip_chamfer_mm,
        "tip_chamfer_angle_deg": geometry.tip_chamfer_angle_deg,
        "tip_chamfer_depth_mm": geometry.tip_chamfer_depth_mm,
        "root_envelope": geometry.root_transition_mode,
        "span_length_mm": measurements["span"]["span_length_mm"],
        "span_tooth_count": measurements["span"]["span_tooth_count"],
        "constant_chord_mm": measurements["constant_chord"]["constant_chord_mm"],
        "constant_chord_height_mm": measurements["constant_chord"]["constant_chord_height_mm"],
        "over_pin_mm": measurements["over_pin"].get("over_pin_mm"),
        "over_pin_diameter_mm": measurements["over_pin"].get("pin_diameter_mm"),
        "over_pin_source": measurements["over_pin"].get("pin_source"),
        "base_pitch_mm": measurements["base_pitch_mm"],
        "section_area_mm2": geometry.section_area_mm2,
        "tip_below_base": geometry.tip_below_base,
        "representation_mode": report["representation_mode"],
        "verification_status": report["status"],
    }
    if helical:
        summary.update(
            {
                "helix_angle_deg": math.degrees(geometry.helix_angle_rad),
                "hand": geometry.hand,
                "transverse_module_mm": geometry.transverse_module_mm,
                "transverse_pressure_angle_deg": math.degrees(geometry.pressure_angle_rad),
                "base_helix_angle_deg": math.degrees(geometry.base_helix_angle_rad),
                "axial_pitch_mm": geometry.axial_pitch_mm,
                "lead_mm": geometry.lead_mm,
                "axial_overlap": geometry.axial_overlap,
                "tip_thickness_normal_mm": geometry.tip_thickness_normal_mm,
            }
        )
    derived = {
        **summary,
        "module_row": geometry.module_info.get("row"),
        "module_status": geometry.module_info.get("status"),
        "checks": report["checks"],
    }
    return {
        "success": True,
        "family": "gear_internal",
        "request": dict(request),
        "representation_mode": report["representation_mode"],
        "geometry": {
            "coordinate_system": "end_view_polar_yz",
            "full_ring_outline": geometry.full_ring_outline,
            "inner_profile_path": geometry.inner_profile_path,
            "period_outline": geometry.period_outline,
            "space_outline": geometry.space_outline,
            "space_cut_outline": geometry.space_cut_outline,
            "pitch_radius_mm": geometry.pitch_radius,
            "base_radius_mm": geometry.base_radius,
            "outside_radius_mm": geometry.outside_radius,
            "root_radius_mm": geometry.root_radius,
            "ring_outside_radius_mm": geometry.ring_outside_radius,
            "space_half_angle_rad": geometry.space_half_angle_rad,
            "root_space_half_angle_rad": geometry.root_space_half_angle_rad,
            "tip_space_half_angle_rad": geometry.tip_space_half_angle_rad,
            "root_transition_mode": geometry.root_transition_mode,
            "root_transition_size_mm": geometry.root_transition_size_mm,
            "right_transition_controls": geometry.right_transition_controls,
            "left_transition_controls": geometry.left_transition_controls,
            "tip_chamfer_mm": geometry.tip_chamfer_mm,
            "tip_chamfer_depth_mm": geometry.tip_chamfer_depth_mm,
        },
        "derived": derived,
        "measurements": measurements,
        "summary": summary,
        "report": report,
        "warnings": warnings,
        "warning_items": warning_items,
    }
