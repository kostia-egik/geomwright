"""GB/T 10855 radial construction for the ASME-compatible Studio family.

Evidence: GB/T 10855-2016 text, Figures 6/7, equations 2--13, 16--19,
and Table 7 footnote a. This is not certification to ASME B29.2M.
Coordinates are mm, spaces are centred on +Y, positive rotation is clockwise.
No CAD calls, dossier root radii, or dependencies on the other chain families.

The large circles in Figures 6/7 are DIAMETER .75p/.827p construction
circles, not root fillets. dB is a centre locus, not the material floor.
Clause 4.1.5 permits tool-dependent geometry below the working faces. The
default filleted floor is therefore a generator policy, separately returned
from supported source geometry. Set profile['root_policy'] = 'partial' to
omit that policy. Neither policy asserts a standard nominal root contour.
"""

from __future__ import annotations

import math
from typing import Any


# Table 7 rectangle-tip maximum diameter / pitch, indexed by z - 17.
# Only the necessary numeric column is retained from official TXT lines
# 915--1118. Footnote a: upper deviation zero, lower deviation negative.
# Two inconsistent PRINTED values are retained here and substituted explicitly below;
# neither interpolation nor the coordinate construction supplies table values.
_TABLE_7_SQUARE_MAX_FACTORS = (
    5.298, 5.623, 5.947, 6.271, 6.595, 6.919, 7.243, 7.568,
    7.890, 8.213, 8.536, 8.859, 9.181, 9.504, 9.828, 10.150,
    10.471, 10.793, 11.115, 11.437, 11.757, 12.077, 12.397, 12.717,
    13.037, 13.357, 13.677, 13.997, 14.317, 14.637, 14.957, 15.277,
    15.597, 15.917, 16.236, 16.556, 16.876, 17.196, 17.515, 17.834,
    18.154, 18.473, 18.793, 19.112, 19.431, 19.750, 20.070, 20.388,
    20.708, 21.027, 21.346, 21.665, 21.984, 22.303, 22.622, 22.941,
    23.259, 23.578, 23.897, 24.216, 24.535, 24.853, 25.172, 25.491,
    25.809, 26.128, 26.447, 26.766, 27.084, 27.403, 27.722, 28.040,
    28.359, 28.678, 58.997, 29.315, 29.634, 29.953, 30.271, 30.900,
    30.909, 31.228, 31.546, 31.865, 32.183, 32.502, 32.820, 33.139,
    33.457, 33.776, 34.094, 34.413, 34.731, 35.050, 35.368, 35.687,
    36.005, 36.324,
)
_TABLE_7_SOURCE = 'GB/T 10855-2016 Table 7, rectangle tip, footnote a'
# Official TXT lines 1039/1044 exceed the round-tip maxima (29.035/30.627).
# Ramsey-PT-English.txt lines 970/975 independently give 736.524/776.986 mm
# diameter factors per inch pitch: dividing by 25.4 gives 28.997/30.590.
# Official page images confirm BOTH values as printed, not OCR errors. These
# manufacturer substitutes are not corrections certified by the publisher.
_TABLE_7_TEXT_CORRECTIONS = {91: 28.997, 96: 30.590}


def _rotate(point: list[float], angle: float) -> list[float]:
    x, y = point
    return [x * math.cos(angle) + y * math.sin(angle),
            y * math.cos(angle) - x * math.sin(angle)]


def _mirror(path: list[list[float]]) -> list[list[float]]:
    return [[-x, y] for x, y in path]


def _arc(center: list[float], radius: float, start: float,
         end: float) -> list[list[float]]:
    # Absolute chord sagitta <= .002 mm. Endpoints are included.
    step = 2 * math.acos(max(-1.0, 1 - min(.002 / radius, 1.0)))
    count = max(2, math.ceil(abs(end - start) / step))
    return [[center[0] + radius * math.cos(start + (end - start) * i / count),
             center[1] + radius * math.sin(start + (end - start) * i / count)]
            for i in range(count + 1)]


def build_asme_space(profile: dict[str, Any], z: int,
                     tipshape: str) -> dict[str, Any]:
    """Return ``geometry``, profile ``updates`` and derivation ``diagnostics``.

    profile_path traverses one space left-top to right-top; tooth_tip_path
    traverses the adjacent tooth from this space's right-top to the next
    space's left-top. supported_paths excludes the optional tool-policy root.
    Existing computed diameters in profile are deliberately recomputed.

    Optional root_policy: 'filleted_floor' (default) or 'partial'. Optional
    tool_root_radius_mm and tool_floor_depth_mm are generator choices. The
    small-pitch radius cannot exceed .16p (Figure 7: 最大半径, maximum radius).
    Depth is measured below the construction chord in the tooth frame.
    The generated floor can be deeper to preserve the dimensioned face.
    """
    if isinstance(z, bool) or not isinstance(z, int) or not 17 <= z <= 114:
        raise ValueError('ASME radial preview supports integer tooth counts 17..114')
    p = float(profile['pitch_mm'])
    if not math.isfinite(p) or not (p >= 9.525 or math.isclose(p, 4.7625, abs_tol=1e-9, rel_tol=0)):
        raise ValueError('ASME radial construction requires p >= 9.525 or p = 4.7625 mm')
    if tipshape not in ('round', 'square'):
        raise ValueError("tipshape must be 'round' or 'square'")
    small = p < 9.525
    if small and tipshape != 'round':
        raise ValueError('Figure 7 supports only the small-pitch round tip')
    policy = profile.get('root_policy', 'filleted_floor')
    if policy not in ('partial', 'filleted_floor'):
        raise ValueError("root_policy must be 'partial' or 'filleted_floor'")

    h = math.pi / z
    theta = math.radians(35 if small else 30)
    beta, gamma = theta - h, theta - 2 * h
    sb, cb = math.sin(beta), math.cos(beta)
    sg, cg = math.sin(gamma), math.cos(gamma)
    H = p / (2 * math.tan(h))
    pitch_radius = p / (2 * math.sin(h))
    construction_radius = (.4135 if small else .375) * p
    pin_radius = (.667 if small else .625) * p / 2
    pin_shift = (.080 if small else .0625) * p
    pin_center = pitch_radius - pin_shift / sb
    # Right space face: x cos(beta) - y sin(beta) = offset.
    # Both the construction circle (at the pitch radius) and the smaller
    # measuring pin must independently give this same signed offset.
    offset = construction_radius - pitch_radius * sb
    measured_offset = pin_radius - pin_center * sb
    tip_radius = (.107 if small else .15) * p
    center_y = H - (.123 if small else .11) * p
    # In the tooth frame, left face: x cos(gamma)-y sin(gamma)=offset.
    # Apex L and circle-centre displacement Y give equations (11)--(13).
    Y = p * (.5 - construction_radius / p / cg) / math.tan(gamma) + H - center_y
    L = center_y + Y
    distance = -offset - center_y * sg
    radicand = tip_radius**2 - distance**2
    if radicand <= 0:
        raise ValueError('Primary tip circle has no transverse face intersection')
    along = math.sqrt(radicand)
    # Equations (11)--(13) select X = Y cos(gamma) - sqrt(...):
    # the UPPER intersection, on the apex side of the circle. The other
    # branch would wrap the round cap beyond a semicircle and is not Fig. 6.
    left = [-distance * cg + along * sg,
            center_y + distance * sg + along * cg]
    right = [-left[0], left[1]]
    start = math.atan2(left[1] - center_y, left[0])
    if start < math.pi / 2:
        start += 2 * math.pi
    tip_circle_path = _arc([0.0, center_y], tip_radius, start, math.pi - start)
    round_d = 2 * (center_y + tip_radius)
    X = Y * cg - along
    square_d = 2 * math.hypot(*left)
    printed_square_d = 2 * math.sqrt(X * X + L * L + 2 * X * L * cg)
    reference_left, reference_right = left, right
    table_text_factor = None if small else _TABLE_7_SQUARE_MAX_FACTORS[z - 17]
    table_factor = None if small else _TABLE_7_TEXT_CORRECTIONS.get(z, table_text_factor)
    table_max_radius = None if small else table_factor * p / 2
    user_tip = tipshape == 'square' and profile.get('square_tip_resolution') in {'accept_ramsey', 'custom_diameter'}
    if tipshape == 'round':
        tooth_cap = tip_circle_path
        outside_d = round_d
    else:
        # Table 7 is a ceiling, not a rounded approximation permitting an
        # oversized coordinate-derived tip. Turn at that maximum and intersect
        # the unchanged straight face with the concentric turning circle.
        # Valid table values may exceed square_d; do not clamp them to it.
        outside_d = (float(profile['square_tip_diameter_mm']) if user_tip and profile.get('square_tip_resolution') == 'custom_diameter'
                     else table_factor * p)
        if not math.isfinite(outside_d) or outside_d <= 0:
            raise ValueError('User square-tip diameter must be finite and positive')
        if z not in _TABLE_7_TEXT_CORRECTIONS and outside_d > table_factor * p + 1e-9:
            raise ValueError('User square-tip diameter exceeds the Table 7 maximum')
        if user_tip:
            table_max_radius = outside_d / 2
        if outside_d > round_d:
            raise ValueError('Table 7 square maximum exceeds the round-tip diameter')
        turning_radicand = table_max_radius**2 - offset**2
        if turning_radicand <= 0:
            raise ValueError('Table 7 turning circle has no transverse face intersection')
        face_along = math.sqrt(turning_radicand)
        left = [offset * cg + face_along * sg,
                -offset * sg + face_along * cg]
        right = [-left[0], left[1]]
        angle = math.atan2(-left[0], left[1])
        if not 0 < angle < h:
            raise ValueError('Table 7 turned tip lies outside the tooth period')
        tooth_cap = _arc([0.0, 0.0], table_max_radius,
                          math.pi / 2 + angle, math.pi / 2 - angle)
    # Eliminate sampling-roundoff at analytically shared endpoints.
    tooth_cap[0], tooth_cap[-1] = left, right
    cap = [_rotate(point, h) for point in tooth_cap]
    top = cap[0]

    working_depth = (.5298 if small else .55) * p
    tooth_bottom_y = H - working_depth
    tooth_bottom_x = (offset + tooth_bottom_y * sg) / cg
    bottom = _rotate([tooth_bottom_x, tooth_bottom_y], h)
    if not 0 < bottom[0] < top[0] or bottom[1] >= top[1]:
        raise ValueError('Primary working face has invalid endpoints')
    flanks = [_mirror([top, bottom]), [bottom, top]]
    if user_tip:
        pin_contact = [pin_radius*cb, pin_center-pin_radius*sb]
        dx, dy = top[0]-bottom[0], top[1]-bottom[1]
        contact_parameter = ((pin_contact[0]-bottom[0])*dx+(pin_contact[1]-bottom[1])*dy)/(dx*dx+dy*dy)
        if not -1e-9 <= contact_parameter <= 1+1e-9:
            raise ValueError('User square tip removes the measuring-pin contact from the working face')
    closure = [flanks[0][-1], bottom]
    root_path: list[list[float]] = []
    policy_paths: list[list[list[float]]] = []
    root_entities: list[dict[str, Any]] = []
    root_d: float | None = None
    floor_y: float | None = None
    root_radius: float | None = None
    actual_depth: float | None = None
    if policy == 'filleted_floor':
        root_radius = float(profile.get('tool_root_radius_mm', (.08 if small else .04) * p))
        depth = float(profile.get('tool_floor_depth_mm', (.597 if small else .55) * p))
        if not math.isfinite(root_radius) or root_radius <= 0:
            raise ValueError('Tool-policy root radius must be finite and positive')
        if small and root_radius > .16 * p + 1e-12 * p:
            raise ValueError('Figure 7 root rounding radius must not exceed .16p')
        if not math.isfinite(depth) or depth < (.597 if small else .55) * p:
            raise ValueError('Tool-policy floor depth is below the selected dimensional bound')
        # Horizontal space-frame floor, tangent circular corners. Preserve
        # the complete dimensioned working face: its tangent may be deeper,
        # never above the lower endpoint. No dB-as-floor substitution.
        working_floor_limit = ((H - working_depth - root_radius * (1 - sb) * math.cos(h)
                        - (offset + root_radius * sb * (1 - sb)) / cb * math.sin(h))
                       / (math.cos(h) + sb / cb * math.sin(h)))
        requested_floor_y = (H - depth) / math.cos(h)
        if profile.get('exact_tool_floor') and requested_floor_y > working_floor_limit + 1e-9:
            raise ValueError('User tool floor depth is too shallow to retain the complete working faces')
        floor_y = requested_floor_y if profile.get('exact_tool_floor') else min(requested_floor_y, working_floor_limit)
        cx = (offset + (floor_y + root_radius) * sb - root_radius) / cb
        cy = floor_y + root_radius
        tangent = [cx + root_radius * cb, cy - root_radius * sb]
        if floor_y <= 0 or cx <= 0 or tangent[1] >= top[1] or tangent[0] >= top[0]:
            raise ValueError('Tool-policy root cannot fit below these working faces')
        right_arc = _arc([cx, cy], root_radius, -math.pi / 2, -beta)
        right_arc[0], right_arc[-1] = [cx, floor_y], tangent
        left_arc = _mirror(right_arc[::-1])
        root_path = left_arc + right_arc
        policy_paths = [_mirror([bottom, tangent]), root_path, [tangent, bottom]]
        root_entities = [
            {'kind': 'arc', 'center': [-cx, cy], 'radius_mm': root_radius,
             'start': left_arc[0], 'end': left_arc[-1]},
            {'kind': 'line', 'start': left_arc[-1], 'end': right_arc[0]},
            {'kind': 'arc', 'center': [cx, cy], 'radius_mm': root_radius,
             'start': right_arc[0], 'end': tangent},
        ]
        gap = _mirror([top, tangent]) + root_path[1:-1] + [tangent, top]
        closure = []
        root_d = 2 * floor_y
        actual_depth = H - floor_y * math.cos(h)
    else:
        gap = flanks[0] + flanks[1]

    center_locus_d = None if small else p * math.sqrt(1.515213 + (1 / math.tan(h) - 1.1)**2)
    pins = 2 * pin_center * (1 if z % 2 == 0 else math.cos(h / 2)) + 2 * pin_radius
    # Mathematical residuals are dimensional checks, not conformance claims.
    residuals = {
        'pin_vs_construction_face_mm': measured_offset - offset,
        'figure_circle_face_tangency_mm': (-.5 * p * cg - H * sg - offset) + construction_radius,
        'tip_face_mm': left[0] * cg - left[1] * sg - offset,
        'tip_circle_mm': math.hypot(reference_left[0], reference_left[1] - center_y) - tip_radius,
        'reference_tip_face_mm': reference_left[0] * cg - reference_left[1] * sg - offset,
        'actual_tip_radius_mm': (math.hypot(left[0], left[1] - center_y) - tip_radius
                                 if tipshape == 'round' else math.hypot(*left) - table_max_radius),
        'apex_circle_displacement_mm': distance - Y * sg,
        'square_coordinate_formula_mm': square_d - 2 * math.sqrt(X * X + L * L - 2 * X * L * cg),
        'adjacent_tip_endpoint_mm': math.dist(cap[-1], _rotate([-top[0], top[1]], 2 * h)),
        'round_tip_diameter_formula_mm': round_d - p * (1 / math.tan(h) + (-.032 if small else .08)),
    }
    if max(abs(value) for value in residuals.values()) > 1e-9 * p:
        raise ValueError('ASME primary construction failed a dimensional residual check')
    updates = {
        'pitch_diameter_mm': 2 * pitch_radius,
        'outside_diameter_mm': outside_d,
        'root_diameter_mm': root_d,
        'root_diameter_status': 'generator_policy_floor' if root_d is not None else 'not_specified',
        'root_arc_center_diameter_mm': center_locus_d,
        'root_round_radius_mm': root_radius,
        'root_reference_radius_mm': construction_radius,
        'root_reference_status': 'construction_circle_not_root_fillet',
        'construction_circle_diameter_mm': 2 * construction_radius,
        'tip_round_radius_mm': tip_radius,
        'tip_arc_center_diameter_mm': 2 * center_y,
        'pressure_angle_deg': 35.0 if small else 30.0,
        'half_gap_pitch_rad': beta,
        'working_flank_angle_rad': beta,
        'working_flank_offset_mm': offset,
        'measuring_pin_diameter_mm': 2 * pin_radius,
        'measuring_pin_center_radius_mm': pin_center,
        'over_pins_mm': pins,
        'flank_model': 'asme_straight_flanks',
        'engagement_diameter_mm': outside_d,
        'diameter_order_conflict': outside_d < 2 * pitch_radius,
        'tip_shape': tipshape,
        'preview_profile_height_mm': working_depth,
        'preview_end_round_radius_mm': tip_radius,
        'max_guide_groove_diameter_mm': p * (1 / math.tan(h) - (1.20 if small else 1.16)),
        'profile_status': ('source_faces_with_vendor_provisional_tip' if tipshape == 'square' and z in _TABLE_7_TEXT_CORRECTIONS else
                           'source_faces_and_tip_with_tool_policy_root' if root_path else 'source_faces_and_tip_partial_root'),
        'tip_status': ('user_defined_square_tip' if user_tip else 'primary_circle_face_intersection' if tipshape == 'round' else
                       'vendor_provisional_square_tip' if z in _TABLE_7_TEXT_CORRECTIONS else 'tabulated_square_tip_maximum'),
        'tip_flank_join_status': 'intersection_not_assumed_tangent',
        'radial_source': 'GB/T 10855-2016 Figures 6/7, equations 2-13, 16-19; Table 7 footnote a; ASME equivalence not certified',
    }
    geometry = {
        'profile_path': gap,
        'supported_paths': flanks + ([] if updates['tip_status'] in {'vendor_provisional_square_tip', 'user_defined_square_tip'} else [cap]),
        'user_radial_paths': [cap] if user_tip else [],
        'provisional_tip_paths': [cap] if updates['tip_status'] == 'vendor_provisional_square_tip' else [],
        'working_flank_paths': flanks,
        'supported_flank_paths': flanks,
        'construction_closure_path': closure,
        'tooth_tip_path': cap,
        'tool_policy_paths': policy_paths,
        'tool_policy_entities': root_entities,
        'root_status': 'tool_policy_tangent_fillets_and_flat_floor' if root_path else 'tool_dependent_unresolved',
        'profile_status': updates['profile_status'],
        'tip_status': updates['tip_status'],
    }
    diagnostics = {
        'source': updates['radial_source'],
        'source_dimensions': {
            'construction_circle_diameter_over_p': .827 if small else .75,
            'tip_radius_over_p': .107 if small else .15,
            'tip_center_drop_over_p': .123 if small else .11,
            'tip_top_rise_over_p': -.016 if small else .04,
            'working_depth_over_p': .5298 if small else .55,
            'small_root_depth_min_over_p': .597 if small else None,
            'small_root_rounding_radius_max_over_p': .16 if small else None,
        },
        'residuals_mm': residuals,
        'tip_join_tangent': False,
        'tip_face_normal_distance_mm': distance,
        'tip_face_tangency_deficit_mm': tip_radius - distance,
        'tip_intersection_branch': 'upper_apex_side_X_equals_Y_cos_minus_sqrt',
        'construction_circle_center_in_space_mm': [0.0, pitch_radius],
        'tip_circle_center_in_tooth_mm': [0.0, center_y],
        'root_arc_center_locus': {
            'diameter_mm': center_locus_d,
            'equation': 'p * sqrt(1.515213 + (cot(pi/z) - 1.1)^2)',
            'status': 'Figure 6 centre locus only; not a root floor or construction-circle diameter',
            'applicable': not small,
        },
        'square_construction': {
            'applicable': not small, 'Y_mm': Y, 'X_mm': X, 'L_mm': L,
            'coordinate_diameter_mm': square_d,
            'reference_circle_face_endpoints_in_tooth_mm': [reference_left, reference_right],
            'actual_tip_endpoints_in_tooth_mm': [left, right],
            'actual_vs_reference_endpoint_distance_mm': math.dist(left, reference_left),
            'actual_endpoint_reference_circle_residual_mm': math.hypot(left[0], left[1] - center_y) - tip_radius,
            'printed_equation_9_plus_diameter_mm': printed_square_d,
            'status': 'printed_plus_conflicts_with_coordinates_and_table_7',
            'tip_status': updates['tip_status'],
            'source': 'Ramsey RPV outside-diameter factors; conflicting printed GB Table 7 row' if z in _TABLE_7_TEXT_CORRECTIONS and tipshape == 'square' else _TABLE_7_SOURCE,
            'table_maximum_factor': table_factor,
            'table_text_factor': table_text_factor,
            'table_maximum_radius_mm': table_max_radius,
            'chosen_radius_mm': outside_d / 2 if tipshape == 'square' else None,
            'coordinate_vs_table_maximum_mm': square_d - 2 * table_max_radius if not small else None,
            'table_text_status': ('printed_source_conflict_with_vendor_substitute'
                                  if not small and z in _TABLE_7_TEXT_CORRECTIONS else 'as_transcribed'),
            'table_text_correction_basis': ('Ramsey-PT-English.txt, RPV outside-diameter factors, '
                                            'z91: 736.524/25.4=28.997; z96: 776.986/25.4=30.590'
                                            if not small and z in _TABLE_7_TEXT_CORRECTIONS else None),
            'maximum_diameter_tolerance': ('unverified for manufacturer substitute' if z in _TABLE_7_TEXT_CORRECTIONS and tipshape == 'square' else 'upper deviation 0; lower deviation negative (Table 7 footnote a)'),
            'table_7_z17_square_over_p': 5.298,
            'table_7_z17_coordinate_difference_over_p': square_d / p - 5.298 if z == 17 and not small else None,
        },
        'root_policy': {
            'name': policy, 'standard_nominal_root_claim': False,
            'floor_y_mm': floor_y, 'floor_depth_in_tooth_frame_mm': actual_depth,
            'corner_radius_mm': root_radius,
            'basis': 'Below dimensioned faces; GB/T 4.1.5 tool-dependent bottom; Figure 7 small-pitch dimensional bounds',
            'standard_pitch_radius_limit': 'not specified; selected .04p is a generator choice',
            'working_face_depth_bound_status': 'Figure 7 minimum' if small else 'Figure 6 .55p reference used as conservative policy boundary',
        },
        'proof_limits': [
            'GB/T primary construction, not independently certified ASME equivalence.',
            'dB is a root-arc centre locus; no actual root radius or nominal floor is deduced from it.',
            'Circle/face intersections are verified; tangent tip joins are not prescribed or imposed.',
            ('Square tip uses a provisional Ramsey diameter; the printed GB value is inconsistent, publisher clarification pending.' if updates['tip_status'] == 'vendor_provisional_square_tip' else
             'Square tip uses the Table 7 maximum turning circle; reference circle/face coordinates and printed equation (9) remain separate diagnostics.'),
            'Official page images confirm Table 7 z91/z96 values 58.997/30.900. Ramsey factors remain provisional substitutes, not official corrections.',
            'Root policy is preview geometry, not a recovered cutter envelope or CAD validation.',
        ],
    }
    return {'geometry': geometry, 'updates': updates, 'diagnostics': diagnostics}
