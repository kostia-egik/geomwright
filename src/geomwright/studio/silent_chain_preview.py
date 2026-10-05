"""Host-only silent-chain radial previews with explicit evidence boundaries.

Coordinates are millimetres about the sprocket centre, a space symmetric about
+Y. Positive angular rotation is clockwise. profile_path is always ONE space;
period_path includes its following tooth cap and repeats at period_angle_rad.
For partial profiles the paths contain a straight, separately exposed display
closure: consumers must use supported_paths and statuses for normative strokes.
"""

from __future__ import annotations

import math
from typing import Any

from .silent_chain import _ASME_PITCHES_MM, _DIN_ROWS, _GOST_DESIGNATIONS
from .silent_chain_axial import build_axial_view
from .silent_chain_asme import build_asme_space
from .silent_chain_din import build_din_space


def _find_profile(request: dict[str, Any]) -> dict[str, Any]:
    standard = request["standard"]
    designation = request["designation"]
    if standard == "gost_13552_81_13576_81":
        if designation not in _GOST_DESIGNATIONS:
            raise ValueError("Unknown GOST 13552-81 designation")
        _, type_no, pitch_text, load_text, width_text = designation.split("-")
        pitch = float(pitch_text)
        return {
            "chain_type": int(type_no), "pitch_mm": pitch,
            "working_width_mm": float(width_text), "min_breaking_load_kn": int(load_text),
            "plate_thickness_mm": {12.7: 1.5, 15.875: 2.0, 19.05: 3.0, 25.4: 3.0, 31.75: 3.0}[pitch],
            "axis_to_tooth_tip_h1_mm": {12.7: 7.0, 15.875: 8.7, 19.05: 10.5, 25.4: 13.35, 31.75: 16.7}[pitch],
            "joint_to_working_face_u_mm": {12.7: 4.76, 15.875: 5.95, 19.05: 7.14, 25.4: 9.52, 31.75: 11.91}[pitch],
        }
    if standard == "din_8190_8191_open":
        row = next((row for row in _DIN_ROWS if row[0] == designation and row[1] == request["family"]), None)
        if row is None:
            raise ValueError("Unknown DIN open-reconstruction catalog row")
        name, guide, pitch, working_width, overall_width, load = row
        return {
            "designation": name, "chain_type": guide, "pitch_mm": pitch,
            "working_width_mm": working_width, "overall_width_mm": overall_width,
            "breaking_load_n": load, "chain_series": name.split("-")[0],
            "confidence": "medium", "source": "MDESIGN/INGGO secondary reproduction of DIN 8190",
        }
    pitch = float(designation.split("-", 2)[1])
    if pitch not in _ASME_PITCHES_MM:
        raise ValueError("Unknown ASME open-reconstruction pitch")
    return {
        "chain_type": designation.rsplit("-", 1)[-1], "pitch_mm": pitch,
        "working_width_mm": float(request["face_width_mm"]),
        "overall_width_mm": float(request["face_width_mm"]),
        "confidence": "open_reconstruction",
        "source": "GB/T 10855-2016 with Ramsey catalog corroboration",
        "source_ru": "GB/T 10855-2016; независимая проверка по каталогу Ramsey",
    }


def _involute(angle: float) -> float:
    return math.tan(angle) - angle


def _gost_profile(request: dict[str, Any], chain: dict[str, Any]) -> dict[str, Any]:
    z = int(request["physical_tooth_count"])
    z_calc = 2 * z if chain["chain_type"] == 2 else z
    t = chain["pitch_mm"]
    h2 = chain["axis_to_tooth_tip_h1_mm"] + 0.1 * t
    k = (0.99 if z_calc <= 40 else 0.995) if chain["chain_type"] == 2 else 1.0
    dd = k * t / math.sin(math.pi / z_calc)
    de = k * t / math.tan(math.pi / z_calc)
    di = dd - 2.0 * h2 / math.cos(math.pi / z_calc)
    if min(dd, de, di) <= 0 or not di < de:
        raise ValueError("GOST profile produced invalid root/outside diameters")
    beta = math.radians((60.0 - 360.0 / z_calc) / 2.0)
    gamma = math.radians(30.0 - 360.0 / z_calc)
    u = chain["joint_to_working_face_u_mm"]
    measuring_y = u * math.sin(gamma) + 0.1 * t * math.cos(gamma)
    thickness = t - 2.0 * (u * math.cos(gamma) - 0.1 * t * math.sin(gamma))
    # Anchor a TOOTH flank by ty(y), then rotate into the neighbouring SPACE.
    # Type II omits every second theoretical tooth: its space spans two pitches.
    half_step = math.pi / z
    gap_beta = gamma + half_step
    px, py = _rotate([-thickness / 2.0, de / 2.0 - measuring_y], half_step)
    flank_offset = px * math.cos(gap_beta) - py * math.sin(gap_beta)
    return {
        "pitch_diameter_mm": dd, "outside_diameter_mm": de, "root_diameter_mm": di,
        "root_round_radius_mm": {12.7: 1.5, 15.875: 2.0, 19.05: 2.0, 25.4: 2.5, 31.75: 3.5}[t],
        "pressure_angle_deg": 30.0, "half_gap_pitch_rad": gap_beta,
        "theoretical_half_gap_pitch_rad": beta,
        "flank_model": "gost_formula_flanks", "calculation_tooth_count": z_calc,
        "engagement_diameter_mm": de,
        "diameter_order_conflict": de < dd,
        "preview_profile_height_mm": h2,
        "preview_end_round_radius_mm": 50.0 if chain["chain_type"] == 2 else t,
        "working_flank_angle_rad": gap_beta,
        "working_flank_offset_mm": flank_offset,
        "tooth_measuring_height_mm": measuring_y,
        "tooth_thickness_at_measuring_height_mm": thickness,
        "working_face_spacing_T_mm": t + (2.0 * u - h2) / 0.866,
        "tabulated_working_face_spacing_T_mm": {12.7: 14.11, 15.875: 17.73, 19.05: 21.22, 25.4: 28.33, 31.75: 35.35}[t],
        "tabulated_working_face_intersection_C_mm": {12.7: 20.52, 15.875: 25.65, 19.05: 30.76, 25.4: 41.03, 31.75: 51.34}[t],
        "profile_status": "dimensioned_flanks_root_circle_and_tangent_fillets",
        "tip_status": "outside_circle",
        "radial_source": "GOST 13576-81 Figures 1/2 and Table 1: ty(y), Di, De, r1",
    }


_DIN_PROFILE = {
    "06": {"two_c1_mm": 3.0, "f_mm": 3.76, "u_mm": 9.0, "y": 0.6, "h2_mm": 4.0, "h_mm": 5.3, "r_mm": 2.0, "c_mm": 0.5, "g_mm": 4.0},
    "08": {"two_c1_mm": 4.2, "f_mm": 5.085, "u_mm": 12.6, "y": 0.6, "h2_mm": 5.0, "h_mm": 6.9, "r_mm": 2.0, "c_mm": 0.5, "g_mm": 4.0},
    "12": {"two_c1_mm": 1.3, "f_mm": 7.44, "u_mm": 15.0, "y": 0.5, "h2_mm": 8.0, "h_mm": 11.2, "r_mm": 3.0, "c_mm": 0.5, "g_mm": 5.0},
    "16": {"two_c1_mm": 1.8, "f_mm": 10.04, "u_mm": 20.0, "y": 0.5, "h2_mm": 10.0, "h_mm": 14.6, "r_mm": 3.0, "c_mm": 1.0, "g_mm": 8.0},
    "24": {"two_c1_mm": 2.8, "f_mm": 14.95, "u_mm": 30.0, "y": 0.5, "h2_mm": 16.0, "h_mm": 21.0, "r_mm": 4.0, "c_mm": 1.5, "g_mm": 9.0},
    "32": {"two_c1_mm": 3.6, "f_mm": 19.93, "u_mm": 40.0, "y": 0.5, "h2_mm": 20.0, "h_mm": 28.0, "r_mm": 4.0, "c_mm": 1.5, "g_mm": 11.0},
}

def _din_profile(request: dict[str, Any], chain: dict[str, Any]) -> dict[str, Any]:
    z = int(request["physical_tooth_count"])
    p = chain["pitch_mm"]
    row = _DIN_PROFILE[chain["chain_series"]]
    delta_p = row["u_mm"] * (1.0 - math.cos(math.radians(6.0)) / math.cos(math.radians(6.0 - 180.0 / z)))
    pitch_d = z * p / math.pi
    outside_d = (p + delta_p) / math.tan(math.pi / z) - row["two_c1_mm"]
    module = p / math.pi
    alpha = math.pi / 6.0
    span_count = max(1, math.floor(z / 6.0 - row["y"] + 0.5))
    span_correction = ((p + delta_p) / (2.0 * math.tan(math.pi / z))
                       + p / (4.0 * math.tan(alpha)) - 2.0 * row["f_mm"] - pitch_d / 2.0)
    shift = span_correction / (2.0 * module * math.sin(alpha))
    span = module * math.cos(alpha) * ((span_count - 0.5) * math.pi + z * _involute(alpha)) + span_correction
    if min(pitch_d, outside_d) <= 0:
        raise ValueError("DIN open-reconstruction equations produced invalid root/tip diameters")
    return {
        "pitch_diameter_mm": pitch_d, "outside_diameter_mm": outside_d,
        "root_round_radius_mm": None, "pressure_angle_deg": 30.0,
        "half_gap_pitch_rad": math.pi / z - (p / 2.0 + 2.0 * shift * module * math.tan(alpha)) / pitch_d,
        "flank_model": "din_shifted_involute", "chain_profile_row": row,
        "engagement_diameter_mm": outside_d,
        "profile_form": "A" if chain["chain_type"] == "outer" else "B",
        "diameter_order_conflict": outside_d < pitch_d,
        "preview_profile_height_mm": row["h_mm"],
        "preview_end_round_radius_mm": row["r_mm"],
        "module_mm": module, "profile_shift_coefficient": shift,
        "reference_tooth_thickness_mm": p / 2.0 + 2.0 * shift * module * math.tan(alpha),
        "base_diameter_mm": pitch_d * math.cos(alpha),
        "span_measurement_mm": span, "span_tooth_count": span_count,
        "tip_status": "outside_circle",
        "radial_source": "DIN 8191:1998 Figure 3 and Table 4; equations (3)/(5) verified against DIN 8191 Berichtigung 1:2006-11; f corrected per DIN 8191:2022 change notice",
    }


def _rotate(point: list[float], angle: float) -> list[float]:
    """Positive angle is clockwise, measured from +Y toward +X."""
    x, y = point
    return [x * math.cos(angle) + y * math.sin(angle), y * math.cos(angle) - x * math.sin(angle)]


def _mirror(points: list[list[float]]) -> list[list[float]]:
    return [[-x, y] for x, y in points]


def _segment(start: list[float], end: list[float]) -> list[list[float]]:
    return [[start[0] + (end[0] - start[0]) * i / 16.0,
             start[1] + (end[1] - start[1]) * i / 16.0] for i in range(17)]


def _arc(center: list[float], radius: float, start: float, end: float) -> list[list[float]]:
    # Bound each circular chord's sagitta to 0.002 mm, independent of pitch.
    step = 2.0 * math.acos(max(-1.0, 1.0 - min(0.002 / radius, 1.0)))
    count = max(2, math.ceil(abs(end - start) / step))
    return [[center[0] + radius * math.cos(start + (end - start) * i / count),
             center[1] + radius * math.sin(start + (end - start) * i / count)] for i in range(count + 1)]


def _line_circle_tip(offset: float, beta: float, radius: float) -> list[float]:
    """Outward intersection of x*cos(beta)-y*sin(beta)=offset with r."""
    if abs(offset) >= radius:
        raise ValueError("Working face does not intersect the reference circle")
    along = math.sqrt(radius * radius - offset * offset)
    return [offset * math.cos(beta) + along * math.sin(beta),
            -offset * math.sin(beta) + along * math.cos(beta)]


def _make_gost_type_1_gap(profile: dict[str, Any], root_radius: float, outside_radius: float) -> list[list[float]]:
    """Figures 1/2: two r1 fillets tangent to positioned faces and Di.

    The historical name is retained for callers; type II also uses this
    construction, with the full physical gap angle (every other pitch).
    """
    beta = float(profile["working_flank_angle_rad"])
    offset = float(profile["working_flank_offset_mm"])
    fillet = float(profile["root_round_radius_mm"])
    center_radius = root_radius + fillet
    normal_offset = offset - fillet
    radicand = center_radius * center_radius - normal_offset * normal_offset
    if radicand <= 0:
        raise ValueError("GOST root circle cannot accommodate the specified tangent fillet")
    along = math.sqrt(radicand)
    center = [normal_offset * math.cos(beta) + along * math.sin(beta),
              -normal_offset * math.sin(beta) + along * math.cos(beta)]
    if center[0] < 0:
        raise ValueError("GOST root fillets overlap; no supported two-fillet construction")
    root_contact = [coord * root_radius / center_radius for coord in center]
    flank_contact = [center[0] + fillet * math.cos(beta), center[1] - fillet * math.sin(beta)]
    top = _line_circle_tip(offset, beta, outside_radius)
    if top[1] <= flank_contact[1]:
        raise ValueError("GOST root fillet consumes the working flank")
    root_angle = math.atan2(root_contact[1] - center[1], root_contact[0] - center[0])
    right = _arc(center, fillet, root_angle, -beta)
    right.extend(_segment(flank_contact, top)[1:])
    theta = math.atan2(root_contact[0], root_contact[1])
    root = _arc([0.0, 0.0], root_radius, math.pi / 2.0 + theta, math.pi / 2.0 - theta)
    profile["root_fillet_centers_mm"] = [[-center[0], center[1]], center]
    profile["supported_flank_paths"] = [_mirror(_segment(flank_contact, top)[::-1]), _segment(flank_contact, top)]
    return _mirror(right[::-1]) + root[1:] + right[1:]


def build_silent_chain_preview(request: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic radial and axial preview data without CAD/COM."""
    from .silent_chain_completion import has_user_geometry
    user_defined = has_user_geometry(request)
    chain = _find_profile(request)
    standard = request["standard"]
    z = int(request["physical_tooth_count"])
    t = chain["pitch_mm"]
    radial = None
    diagnostics = {}
    if standard == "gost_13552_81_13576_81":
        profile = _gost_profile(request, chain)
    elif standard == "din_8190_8191_open":
        profile = _din_profile(request, chain)
        if user_defined:
            profile["din_rack_resolution"] = request.get("din_rack_resolution", "unresolved")
        construction = build_din_space(profile, z)
        profile.update(construction["updates"])
        radial, diagnostics = construction["geometry"], construction["diagnostics"]
    else:
        # Figure 7 defines a single small-pitch tip; the legacy hidden request
        # value is retained for clients but cannot choose a different family.
        shape = "round" if t == 4.7625 else request["tooth_tip_shape"]
        tool = {"pitch_mm": t}
        if user_defined:
            for key in ("tool_root_radius_mm", "tool_floor_depth_mm", "square_tip_resolution", "square_tip_diameter_mm"):
                if request.get(key) is not None:
                    tool[key] = request[key]
            tool["exact_tool_floor"] = request.get("tool_floor_depth_mm") is not None
            if tool.get("square_tip_resolution") == "custom_diameter" and tool.get("square_tip_diameter_mm") is None:
                tool["square_tip_resolution"] = "unresolved"
        construction = build_asme_space(tool, z, shape)
        profile = construction["updates"]
        radial, diagnostics = construction["geometry"], construction["diagnostics"]
    if standard == "gost_13552_81_13576_81":
        if chain["chain_type"] == 1:
            tooth_width = chain["working_width_mm"] + 2.0 * chain["plate_thickness_mm"]
            total_width = tooth_width
            rib_count, row_spacing = 1, None
            guide_width = 2.0 * chain["plate_thickness_mm"]
            guide_grooves = [{"center_mm": total_width / 2.0, "width_mm": guide_width, "depth_mm": 0.75 * t}]
        else:
            tooth_width = 2.55 * chain["plate_thickness_mm"]
            total_width = chain["working_width_mm"] + 1.58 * chain["plate_thickness_mm"]
            count = (chain["working_width_mm"] / chain["plate_thickness_mm"] - 1.0) / 6.0 + 1.0
            if not math.isclose(count, round(count), abs_tol=1e-9) or not math.isclose(chain["plate_thickness_mm"], 3.0, abs_tol=1e-9):
                raise ValueError("GOST type II requires the catalogued 3 mm plates and an integral rib count")
            rib_count = round(count)
            row_spacing = 18.0  # Figure 2; also 6s for these catalogued plates.
            guide_width = None
            guide_grooves = []
        width_source = "GOST 13576-81 formulas"
        axial_status = "dimensioned"
    elif standard == "din_8190_8191_open":
        width = chain["working_width_mm"]
        if chain["chain_type"] == "outer":
            tooth_width = width - (0.5 if width <= 20 else 1.0 if width <= 39 else 1.5 if width <= 59 else 2.0 if width <= 100 else 2.5)
        else:
            tooth_width = width + (5.0 if t <= 19.05 else 10.0)
        tooth_width = max(0.5, tooth_width)
        total_width, rib_count, row_spacing, guide_width = tooth_width, 1, None, None
        guide_grooves = (
            [{"center_mm": total_width / 2.0, "width_mm": profile["chain_profile_row"]["g_mm"], "depth_mm": None}]
            if chain["chain_type"] == "inner" else []
        )
        width_source = "DIN 8191 table-3 form A/B meshing-width reconstruction"
        axial_status = "width_only" if guide_grooves else "dimensioned"
    else:
        tooth_width = float(request["face_width_mm"])
        gb_axial = request.get("axial_source", "ramsey_rp_sc") == "gb_10855_2016"
        total_width, rib_count, row_spacing, guide_width = tooth_width, 1, None, None
        guide_widths = {4.7625: 1.3, 9.525: 3.2, 12.7: 3.2, 15.875: 4.0, 19.05: 4.0, 25.4: 6.4, 38.1: 6.4, 50.8: 6.4}
        guide_width = guide_widths.get(t) if chain["chain_type"] in {"center_guide", "two_center_guide"} else None
        guide_grooves = []
        axial_status = "user_width_only" if chain["chain_type"] == "side_guide" else "guide_data_unavailable"
        if not gb_axial and guide_width is not None and chain["chain_type"] in {"center_guide", "two_center_guide"}:
            centers = [total_width / 2.0]
            if chain["chain_type"] == "two_center_guide":
                guide_spacing = {9.525: 25.4, 12.7: 25.4, 15.875: 50.8, 19.05: 101.6, 25.4: 101.6, 38.1: 101.6, 50.8: 101.6}.get(t)
                centers = [total_width / 2.0 - guide_spacing / 2.0, total_width / 2.0 + guide_spacing / 2.0] if guide_spacing is not None else []
            groove_depth = max(0.0, (profile["outside_diameter_mm"] - profile["max_guide_groove_diameter_mm"]) / 2.0)
            if any(center - guide_width / 2.0 < 0 or center + guide_width / 2.0 > total_width for center in centers):
                raise ValueError("ASME face width is too small to contain the selected guide groove layout")
            guide_grooves = [{"center_mm": center, "width_mm": guide_width, "depth_mm": None,
                             "minimum_depth_mm": groove_depth, "depth_relation": ">=",
                             "depth_source": "GB/T 10855-2016 maximum guide diameter; not a Ramsey groove floor"} for center in centers]
            axial_status = "partial" if centers else "guide_data_unavailable"
        elif chain["chain_type"] in {"center_guide", "two_center_guide"}:
            axial_status = "guide_data_unavailable"
        width_source = "user-supplied functional face width; not a catalog dimension"

    if standard == "gost_13552_81_13576_81" and chain["chain_type"] == 2:
        if (rib_count - 1) * row_spacing + tooth_width > total_width + 1e-7:
            raise ValueError("GOST type II ribs exceed Table 1 b4")
    if radial is None:
        gap = _make_gost_type_1_gap(profile, profile["root_diameter_mm"] / 2.0,
                                   profile["outside_diameter_mm"] / 2.0)
        flank_paths = profile.pop("supported_flank_paths")
        radial = {"profile_path": gap, "working_flank_paths": flank_paths,
                  "supported_paths": [gap], "construction_closure_path": [],
                  "root_status": "dimensioned_tangent_fillets_and_root_circle"}
    gap = radial["profile_path"]
    profile.pop("supported_flank_paths", None)
    flank_paths = radial["working_flank_paths"]
    closure = radial.get("construction_closure_path", [])
    tip_path = radial.get("tooth_tip_path")
    if tip_path is None:
        radius = math.hypot(*gap[-1])
        start = math.atan2(gap[-1][0], gap[-1][1])
        end = 2.0 * math.pi / z - start
        tip_path = _arc([0.0, 0.0], radius, math.pi / 2.0 - start, math.pi / 2.0 - end)
    # One complete open period, from this space's LEFT endpoint to the next
    # space's LEFT endpoint. Rotate by 2*pi/z; do not insert outside arcs.
    period = gap + tip_path[1:]
    supported = list(radial["supported_paths"])
    if tip_path not in supported and not radial.get("provisional_tip_paths") and tip_path not in radial.get("user_radial_paths", []):
        supported.append(tip_path)
    partial = bool(closure) or profile["profile_status"].startswith("partial_")
    tool_policy = bool(radial.get("tool_policy_paths"))
    warnings = []
    if standard == "gost_13552_81_13576_81":
        warnings.append("GOST nominal faces are positioned by ty(y), with two r1 fillets tangent to Di. Formula precision is retained; published rounded T/C and Appendix values may differ. Preview is not a manufacturing conformity certificate.")
    elif standard == "din_8190_8191_open":
        warnings.append("Unofficial DIN open reconstruction: the involute flank and catalog row are reconstructed from public secondary/translated sources; not a conformity claim.")
        if partial:
            warnings.append("DIN series 06: the printed rack height differs from the Figure-3 rounded-rack construction by about 0.03 mm. The candidate root is shown separately; it is not a verified nominal root.")
    else:
        warnings.append("Unofficial ASME-compatible open reconstruction based on GB/T 10855-2016 and Ramsey corroboration; not a conformity claim. Face width is user supplied.")
        warnings.append("Below the working faces, the root is a selected tool variant: tangent corner arcs and a flat floor. It is not a unique standard root contour; its dimensions are reported separately.")
        if t != 4.7625 and request["tooth_tip_shape"] == "square":
            warnings.append("The square-tip diameter uses a provisional Ramsey substitute; the printed GB Table 7 value is inconsistent, publisher clarification pending." if radial.get("provisional_tip_paths") else
                            "The square-tip turning diameter uses Table 7 maximum values (footnote a); the working faces are trimmed at that circle. The printed equation and figure coordinates do not fully agree with the table.")
    result = {
        "success": True,
        "profile": {**chain, **profile, "designation": request["designation"]},
        "derived": profile,
        "geometry": {
            **radial,
            "profile_path": gap, "profile_status": profile["profile_status"],
            "period_path": period, "period_angle_rad": 2.0 * math.pi / z,
            "period_status": "source_faces_with_provisional_tip" if radial.get("provisional_tip_paths") else "partial_reconstruction" if partial else "source_profile_with_tool_choice" if tool_policy else "reconstructed_from_source",
            "partial": partial, "tool_policy": tool_policy,
            "supported_paths": supported, "working_flank_paths": flank_paths,
            "construction_closure_path": closure, "tooth_tip_path": tip_path,
            "tip_status": profile["tip_status"], "circular_chord_error_mm": 0.002,
        },
        "diagnostics": diagnostics,
        "axial": {
            "view_mode": "side_section", "row_count": rib_count,
            "tooth_width_mm": tooth_width, "row_spacing_mm": row_spacing,
            "total_width_mm": total_width, "overall_width_mm": total_width,
            "engagement_diameter_mm": profile["engagement_diameter_mm"],
            "profile_height_mm": profile["preview_profile_height_mm"],
            "end_round_radius_mm": profile["preview_end_round_radius_mm"],
            "guide_groove_width_mm": guide_width,
            "guide_grooves_mm": guide_grooves,
            "width_source": width_source,
            "row_spacing_source": "GOST 13576-81 Figure 2: 18 mm; GOST 13552-81 Figure 2 plate packets repeat at 6s" if row_spacing else None,
            "axial_layout_status": axial_status,
        },
        "warnings": warnings,
    }
    if standard == "gost_13552_81_13576_81" and chain["chain_type"] == 2:
        margin = (total_width - (rib_count - 1) * row_spacing - tooth_width) / 2.0
        result["axial"].update({
            "rib_centers_mm": [margin + tooth_width / 2.0 + i * row_spacing for i in range(rib_count)],
            "relative_rib_phases_deg": [0.0] * rib_count,
            "rib_phase_source": "GOST 13552-81 Figure 2: the same plate packet and longitudinal pin phase repeat at 6s; z_calculation=2*z_physical",
            "rib_phase_period_deg": 360.0 / z,
        })
    result["axial"].update(build_axial_view(request, chain, profile, result["axial"]))
    from .silent_chain_completion import complete_silent_chain_geometry
    result.update(complete_silent_chain_geometry(request, result))
    return result
