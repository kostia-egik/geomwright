"""Host-only silent-chain axial drawing, in mm, x right and y down from tooth top.

``build_axial_view`` returns {"drawing": ...} for merging into secondary_view.
Paths are arrays of [x, y]; polygons repeat their first point. Stroke only
visible_paths: outline is a fill silhouette, including a schematic lower closure.
reference_paths and break_paths must be dashed. Only section_polygons are hatched.
Bounds include geometry and dimension anchors, not renderer-dependent label sizes.
No display break coordinate is a nominal body dimension. An unavailable contour
has an empty outline/section_polygons, never a solid ungrooved substitute.
"""

from __future__ import annotations

import math
from typing import Any


# DIN 8191 Table 3 axial f (called f1 here to distinguish radial equation f).
_DIN = {
    "06": (4.0, 3.0, 5.3, 6.0, 4.0, 2.0, 0.5),
    "08": (4.0, 3.0, 6.9, 7.0, 5.0, 2.0, 0.5),
    "12": (5.0, 4.0, 11.2, 12.0, 8.0, 3.0, 0.5),
    "16": (8.0, 6.0, 14.6, 15.0, 10.0, 3.0, 1.0),
    "24": (9.0, 6.0, 21.0, 22.0, 16.0, 4.0, 1.5),
    "32": (11.0, 8.0, 28.0, 30.0, 20.0, 4.0, 1.5),
}
_RAMSEY_GW = {4.7625: 1.3, 9.525: 3.2, 12.7: 3.2, 15.875: 4.0,
              19.05: 4.0, 25.4: 6.4, 38.1: 6.4, 50.8: 6.4}
_RAMSEY_S = {9.525: 25.4, 12.7: 25.4, 15.875: 50.8, 19.05: 101.6,
             25.4: 101.6, 38.1: 101.6, 50.8: 101.6}
_RAMSEY_R = {4.7625: 0.8, 9.525: 4.8, 12.7: 6.4, 15.875: 7.9,
             19.05: 9.5, 25.4: 12.7, 38.1: 19.1}


def _number(value: Any, name: str, *, positive: bool = True) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be finite{' and positive' if positive else ''}")
    return result


def _closed(path: list[list[float]]) -> list[list[float]]:
    return path + [path[0][:]] if path and path[-1] != path[0] else path


def _round_side(x: float, sign: int, radius: float, center_y: float,
                end_y: float) -> list[list[float]]:
    """Circle tangent to x at center_y; sign points into the tooth material.

    GOST specifies center_y=C1. DIN reconstructs it from top setback and r;
    the latter placement is identified as an interpretation in the result.
    Samples have at most 0.002 mm circular chord error.
    """
    if not 0 < center_y <= radius or end_y < center_y-1e-9:
        raise ValueError("Axial round cannot fit the supplied depth/radius")
    end_y = max(end_y, center_y)  # coalesce numerical equality, not an engineering correction
    sweep = math.asin(center_y / radius)
    # Equivalent sagitta bound, stable even for a user-selected very large R.
    step = 4.0 * math.asin(min(1.0, math.sqrt(0.002 / radius / 2.0)))
    count = max(2, math.ceil(sweep / step))
    if count > 4096:
        raise ValueError("Axial round exceeds the bounded preview sampling budget")
    path = []
    for i in range(count + 1):
        angle = sweep * (1.0 - i / count)
        path.append([x + sign * radius * (1.0 - math.cos(angle)),
                     center_y - radius * math.sin(angle)])
    path[0][1] = 0.0
    path[-1] = [x, center_y]
    if end_y > center_y:
        path.append([x, end_y])
    return path


def _dimension(drawing: dict[str, Any], symbol: str, value: float,
               start: list[float], end: list[float], level: int = 0) -> None:
    drawing["dimensions"].append({
        "symbol": symbol, "value": value,
        "orientation": "horizontal" if start[1] == end[1] else "vertical",
        "start": start, "end": end, "level": level,
    })


def _section(drawing: dict[str, Any], width: float, top: list[list[float]],
             h2: float, grooves: list[tuple[float, float, float]], bottom: float) -> None:
    """Close the display below the cut plane, excluding groove voids from hatch."""
    drawing["outline"] = _closed(top + [[width, bottom], [0.0, bottom]])
    drawing["visible_paths"].extend([top, [[0.0, top[0][1]], [0.0, bottom]],
                                     [[width, top[-1][1]], [width, bottom]]])
    cut = [[0.0, h2]]
    for left, right, depth in grooves:
        if depth > h2:
            cut.extend([[left, h2], [left, depth], [right, depth], [right, h2]])
    cut.append([width, h2])
    drawing["section_polygons"] = [_closed(cut + [[width, bottom], [0.0, bottom]])]
    # The horizontal cut line is visible only where material exists.
    cursor = 0.0
    for left, right, _ in grooves:
        if left > cursor:
            drawing["visible_paths"].append([[cursor, h2], [left, h2]])
        cursor = right
    if cursor < width:
        drawing["visible_paths"].append([[cursor, h2], [width, h2]])
    amplitude = (bottom - max([h2] + [g[2] for g in grooves])) * 0.08
    drawing["break_paths"] = [[[width * i / 16.0,
                                bottom + amplitude * math.sin(i * math.pi / 2.0)]
                               for i in range(17)]]
    drawing["schematic_bottom_y_mm"] = bottom
    drawing["limitations"].append("Lower closure is a display break; body depth, hub and bore are unspecified.")


def _gost(d: dict[str, Any], chain: dict[str, Any], axial: dict[str, Any],
          width: float, pitch: float) -> None:
    kind = chain["chain_type"]
    if kind not in (1, 2):
        raise ValueError("Unknown GOST chain type")
    s = _number(chain["plate_thickness_mm"], "plate thickness")
    b = _number(chain["working_width_mm"], "working width")
    h2 = _number(chain["axis_to_tooth_tip_h1_mm"], "chain h1") + 0.1 * pitch
    h3, c1, radius = 0.75 * pitch, 0.4 * pitch, pitch if kind == 1 else 50.0
    expected_width = b + (2.0 if kind == 1 else 1.58) * s
    if not math.isclose(width, expected_width, abs_tol=1e-7):
        raise ValueError("GOST axial width disagrees with Table 1 b4")
    grooves = []
    if kind == 1:
        left, right = width / 2.0 - s, width / 2.0 + s
        outer_left = _round_side(0.0, 1, radius, c1, h2)
        outer_right = _round_side(width, -1, radius, c1, h2)
        guide_left = _round_side(left, -1, radius, c1, h3)
        guide_right = _round_side(right, 1, radius, c1, h3)
        if outer_left[0][0] >= guide_left[0][0]:
            raise ValueError("GOST face too narrow for rounded guide opening")
        top = list(reversed(outer_left)) + guide_left + list(reversed(guide_right)) + outer_right
        grooves = [(left, right, h3)]
        _dimension(d, "s₁", 2.0 * s, [left, h3], [right, h3], 1)
        _dimension(d, "b₃", width, [0.0, 0.0], [width, 0.0], 0)
    else:
        count = axial.get("row_count")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 256:
            raise ValueError("GOST rib count must be an integer from 1 to 256")
        expected_count = (b / s - 1.0) / 6.0 + 1.0
        if not math.isclose(s, 3.0, abs_tol=1e-9) or not math.isclose(count, expected_count, abs_tol=1e-9):
            raise ValueError("GOST type II rib count disagrees with chain plate packets")
        spacing, rib = 18.0, 2.55 * s
        phases = axial.get("relative_rib_phases_deg")
        if phases is None or len(phases) != count or any(not math.isfinite(v) or abs(v) > 1e-9 for v in phases):
            raise ValueError("GOST type II ribs must share the same angular phase")
        margin = (width - (count - 1) * spacing - rib) / 2.0
        if margin < -1e-7:
            raise ValueError("GOST ribs do not fit b4")
        top = [[0.0, h3]]
        cursor = 0.0
        for i in range(count):
            left, right = margin + i * spacing, margin + i * spacing + rib
            if left > cursor:
                grooves.append((cursor, left, h3))
            top += list(reversed(_round_side(left, 1, radius, c1, h3)))
            top += _round_side(right, -1, radius, c1, h3)
            cursor = right
        if cursor < width:
            grooves.append((cursor, width, h3))
        top.append([width, h3])
        _dimension(d, "b₃", rib, [margin, 0.0], [margin + rib, 0.0])
        if count > 1:
            _dimension(d, "pₐ", spacing,
                       [margin + rib / 2.0, 0.0], [margin + rib / 2.0 + spacing, 0.0], 1)
        d["limitations"].append("Figure 2 hub and its 1.5 mm shoulder are outside the functional-rim scope. Symmetric rib placement within b4 is a layout choice.")
    _section(d, width, top, h2, grooves, max(h2, h3) + 0.3 * pitch)
    if kind == 2:
        bottom = d["schematic_bottom_y_mm"]
        d["outline"] = []
        d["visible_paths"] = [p for p in d["visible_paths"] if p not in (
            [[0.0, top[0][1]], [0.0, bottom]], [[width, top[-1][1]], [width, bottom]])]
        # Hatch only the dimensioned rib section. Unknown lower-body occupancy
        # must not survive the common schematic closure helper.
        d["section_polygons"] = [_closed([[margin + i * spacing, h2],
            [margin + i * spacing + rib, h2], [margin + i * spacing + rib, h3],
            [margin + i * spacing, h3]]) for i in range(count)]
    _dimension(d, "b₄", width, [0.0, 0.0], [width, 0.0], 2)
    _dimension(d, "h₂", h2, [width, 0.0], [width, h2])
    _dimension(d, "h₃", h3, [width, 0.0], [width, h3], 1)
    _dimension(d, "C₁ ≈", c1, [0.0, 0.0], [0.0, c1], 1)
    d["reference_paths"].append([[0.0, c1], [width, c1]])
    d["annotations"].append({"symbol": "r ≈" if kind == 1 else "r", "value_mm": radius,
                              "center_depth_mm": c1, "status": "table_1"})
    d["source"] = "GOST 13576-81 Figures 1/2 and Table 1 (both types: h3=0.75t, C1≈0.4t)"
    d["status"] = "dimensioned_faces_with_schematic_body" if kind == 1 else "dimensioned_ribs_with_schematic_body"


def _din(d: dict[str, Any], chain: dict[str, Any], width: float, pitch: float) -> None:
    series = chain.get("chain_series")
    if series not in _DIN:
        raise ValueError("DIN axial Table 3 row unavailable")
    g, f1, h, h1, h2, radius, c = _DIN[series]
    # Figure A locates c horizontally; Figure B locates g at the top and f
    # at the parallel throat. Neither drawing gives circle centers or a
    # tangency constraint. These circles are a dashed illustration only:
    # h2 is a separately dimensioned level, NOT the inferred circle center.
    grooves = []
    if chain["chain_type"] == "inner":
        # Figure B has square external edges. Its r applies to the guide
        # entrance, not to outer shoulders; c belongs to Figure A only.
        left, right = [[0.0, 0.0], [0.0, h]], [[width, 0.0], [width, h]]
        delta = (g - f1) / 2.0
        guide_cy = math.sqrt(2.0 * radius * delta - delta * delta)
        a, b = width / 2.0 - f1 / 2.0, width / 2.0 + f1 / 2.0
        gl = _round_side(a, -1, radius, guide_cy, h1)
        gr = _round_side(b, 1, radius, guide_cy, h1)
        if gl[0][0] <= left[0][0] or gr[0][0] >= right[0][0]:
            raise ValueError("DIN face too narrow for Table 3 guide opening")
        top = list(reversed(left)) + gl + list(reversed(gr)) + right
        grooves = [(a, b, h1)]
        _dimension(d, "g", g, [width / 2.0 - g / 2.0, 0.0], [width / 2.0 + g / 2.0, 0.0], 1)
        _dimension(d, "f₁", f1, [a, h1], [b, h1], 2)
    elif chain["chain_type"] == "outer":
        cy = math.sqrt(2.0 * radius * c - c * c)
        left = _round_side(0.0, 1, radius, cy, h)
        right = _round_side(width, -1, radius, cy, h)
        if left[0][0] >= right[0][0]:
            raise ValueError("DIN face too narrow for Table 3 edge rounds")
        top = list(reversed(left)) + right
    else:
        raise ValueError("Unknown DIN guide type")
    _section(d, width, top, h, grooves, h1 + 0.3 * pitch)
    # The hatch starts at the confirmed h level, below the uncertain entrance.
    # Do not fill a silhouette bounded by the illustrative circular joins.
    d["outline"] = []
    # The dimensions support straight faces; placement of the short circular
    # joins is an interpretation and must not use a confirmed-geometry stroke.
    d["visible_paths"].remove(top)
    d["reference_paths"].append(top)
    outer_start = 0.0 if grooves else h2
    d["visible_paths"].extend([[[0.0, outer_start], [0.0, h]],
                              [[width, outer_start], [width, h]]])
    if grooves:
        d["visible_paths"].extend([[[left[0][0], 0.0], [gl[0][0], 0.0]],
                                   [[gr[0][0], 0.0], [right[0][0], 0.0]],
                                   [[a, h2], [a, h1]], [[b, h2], [b, h1]],
                                   [[a, h1], [b, h1]]])
    else:
        d["visible_paths"].append([left[0], right[0]])
    d["reference_paths"].append([[0.0, h2], [width, h2]])
    _dimension(d, "bB" if grooves else "bA", width, [0.0, 0.0], [width, 0.0])
    if not grooves:
        _dimension(d, "c", c, [0.0, 0.0], [c, 0.0], 1)
    for level, (symbol, depth) in enumerate((("h", h), ("h₁", h1), ("h₂", h2))):
        _dimension(d, symbol, depth, [width, 0.0], [width, depth], level)
    d["annotations"].append({"symbol": "r", "value_mm": radius, "status": "axial_fillet_table_3"})
    d["schematic_parameters"] = {
        "status": "illustrative_wall_tangent_circles_not_figure_center_coordinates",
    }
    if grooves:
        d["schematic_parameters"]["guide_round_center_depth_mm"] = guide_cy
    else:
        d["schematic_parameters"]["outer_round_center_depth_mm"] = cy
    d["external_references"].append({
        "source": "DIN 8191:1998-01 Figures 1(A)/2(B), Table 3; 2022 Table 3 corrections",
        "symbol": "axial depth levels", "status": "dimensioned_levels_not_circle_centers",
        "tooth_cut_depth_h_mm": h, "shoulder_or_guide_floor_h1_mm": h1,
        "entrance_reference_depth_h2_mm": h2,
    })
    d["source"] = "DIN 8191 Figures 1(A)/2(B), Tables 1–3; axial f1 distinct from radial equation f"
    d["status"] = "partial_fillet_placement_interpreted"
    d["limitations"].append("Figures A/B establish h, h1 and h2 as separate depth levels, but do not dimension circle centers or state tangency. Dashed circles illustrate an unverified placement; they do not bound a filled silhouette.")


def _gb_table_reference(d: dict[str, Any], kind: str, pitch: float,
                        profile: dict[str, Any]) -> None:
    """Expose primary GB facts independently; never use them to place Ramsey.

    Tables 2/3 and recovered Figures 4/5 define a separate source system.
    These references do not position Ramsey geometry or select chain widths.
    """
    # A, C, D (two-center only), R. All listed internal-guide rows at each
    # pitch share these values; side-guide rows exist only at 9.525/12.70.
    internal = {
        9.525: (3.38, 2.54, 25.40, 5.08),
        12.70: (3.38, 2.54, 25.40, 5.08),
        15.875: (4.50, 3.18, 50.80, 6.35),
        19.05: (6.96, 4.57, 101.60, 9.14),
        25.40: (6.96, 4.57, 101.60, 9.14),
        31.75: (6.96, 4.57, 101.60, 9.14),
        38.10: (6.96, 4.57, 101.60, 9.14),
        50.80: (6.96, 5.54, 101.60, 9.14),
    }
    values: dict[str, float] = {}
    ramsey_values: dict[str, float | None] = {}
    if pitch == 4.7625 and kind in {"side_guide", "center_guide"}:
        values = {"A": 1.5, "R": 2.3, **({"H": 0.64} if kind == "side_guide" else {"C": 1.27})}
    elif kind == "side_guide" and pitch in (9.525, 12.70):
        values = {"A": 3.38, "H": 1.30, "R": 5.08}
        ramsey_values = {"R": _RAMSEY_R.get(pitch)}
    elif kind in {"center_guide", "two_center_guide"} and pitch in internal:
        a, c, spacing, radius = internal[pitch]
        values = {"A": a, "C": c, "R": radius}
        ramsey_values = {"GW": _RAMSEY_GW.get(pitch)}
        if kind == "two_center_guide":
            values["D"] = spacing
            ramsey_values["S"] = _RAMSEY_S.get(pitch)
    if values:
        d["external_references"].append({
            "symbol": "GB axial table dimensions", "source": "GB/T 10855-2016 Table 3 / Figure 5" if pitch == 4.7625 else "GB/T 10855-2016 Table 2 / Figure 4",
            "axial_source_system": "gb_10855_2016", "pitch_mm": pitch,
            "guide_type": kind, "values_mm": values,
            "tolerances_mm": {s: [-t, t] for s, t in (("C", 0.13), ("D", 0.25),
                                                       ("H", 0.08), ("R", 0.08)) if s in values and pitch != 4.7625},
            "status": "primary_table_text_not_used_to_position_ramsey_contour",
            "figure_status": "primary_page_images_verified",
            "source_pitch_mm": 4.762 if pitch == 4.7625 else pitch,
            "ramsey_values_mm": ramsey_values,
        })
        d["limitations"].append("GB axial dimensions are a separate source system. C is not Ramsey GW; explicit source selection is required. Figure 5 prints nominal pitch 4.762 mm, distinct from the exact 3/16-inch selection 4.7625 mm.")
    if kind not in {"center_guide", "two_center_guide"}:
        return
    diameter = profile.get("max_guide_groove_diameter_mm")
    if diameter is None:
        return
    diameter = _number(diameter, "GB groove diameter")
    reference = {"symbol": "guide groove maximum diameter", "value_mm": diameter,
                 "source": "GB/T 10855-2016 derived radial profile",
                 "status": "not_used_to_position_ramsey_contour"}
    outside = profile.get("outside_diameter_mm")
    if outside is not None:
        gb_depth_bound = (_number(outside, "GB outside diameter") - diameter) / 2.0
        if gb_depth_bound < 0:
            raise ValueError("GB guide diameter bound exceeds its outside diameter")
        reference.update(minimum_depth_from_gb_tooth_top_mm=gb_depth_bound,
                         depth_relation=">=", depth_status="gb_only_bound_not_exact_floor_not_ramsey_depth")
    d["external_references"].append(reference)


def _gb(d: dict[str, Any], chain: dict[str, Any], profile: dict[str, Any],
        width: float, pitch: float) -> dict[str, Any]:
    """Source-defined circular entrances; guide cutter bottom remains variable.

    Figures 4/5 locate the horizontal circle-center level at A and the vertical
    throat at C. Use their rounded outer-edge alternative, not the chamfer H.
    A maximum dg supplies a minimum depth, never the actual cutter-tip shape.
    """
    kind = chain["chain_type"]
    _gb_table_reference(d, kind, pitch, profile)
    d.update(axial_source_system="gb_10855_2016", source="GB/T 10855-2016 Figures 4/5 and Tables 2/3",
             status="source_entrance_with_unspecified_guide_bottom")
    row = next((r for r in d["external_references"] if r.get("axial_source_system") == "gb_10855_2016"), None)
    updates = {"guide_grooves_mm": [], "guide_groove_width_mm": None,
               "axial_layout_status": "partial", "axial_source": "gb_10855_2016"}
    _dimension(d, "B*" if kind == "side_guide" else "F*", width, [0.0, 0.0], [width, 0.0])
    if row is None:
        d["status"] = "guide_data_unavailable"
        updates["axial_layout_status"] = "guide_data_unavailable"
        d["limitations"].append("No selected GB guide layout row exists; no Ramsey substitute is used.")
        return updates
    values = row["values_mm"]
    a, radius = values["A"], values["R"]
    bottom = a + .4 * pitch
    if kind == "side_guide":
        left, right = _round_side(0.0, 1, radius, a, a), _round_side(width, -1, radius, a, a)
        if left[0][0] >= right[0][0]:
            raise ValueError("GB face too narrow for the Figure 4/5 rounded edges")
        top = list(reversed(left)) + right
        d["visible_paths"].append(top)
        d["reference_paths"].extend([[[0.0, a], [0.0, bottom]], [[width, a], [width, bottom]]])
        d["status"] = "source_rounded_edges_with_schematic_body"
        d["limitations"].append("Rounded-edge alternative selected; the H-dimensioned chamfer is a different permitted alternative, not combined with these arcs.")
    else:
        c = values["C"]
        spacing = values.get("D", 0.0)
        centers = [width / 2.0] if kind == "center_guide" else [width / 2.0 - spacing / 2.0, width / 2.0 + spacing / 2.0]
        depth_min = (profile["outside_diameter_mm"] - profile["max_guide_groove_diameter_mm"]) / 2.0
        bottom = max(a, depth_min) + .3 * pitch
        cursor = 0.0
        for center in centers:
            left, right = center - c / 2.0, center + c / 2.0
            gl, gr = _round_side(left, -1, radius, a, a), _round_side(right, 1, radius, a, a)
            if gl[0][0] <= cursor or gr[0][0] >= width:
                raise ValueError("GB face too narrow to contain the rounded guide entrances")
            d["visible_paths"].extend([[[cursor, 0.0], gl[0]], gl, list(reversed(gr))])
            # The maximum diameter constrains the deepest cutter point, not
            # where a round cutter tip leaves the parallel walls. Stroke no
            # nominal straight wall below the source-defined entrance level.
            d["reference_paths"].append([[left, a], [left, bottom], [right, bottom], [right, a]])
            updates["guide_grooves_mm"].append({"center_mm": center, "width_mm": c, "depth_mm": None,
                "minimum_depth_mm": depth_min, "depth_relation": ">=", "depth_source": "GB/T maximum dg; cutter bottom may be round or square"})
            cursor = gr[0][0]
            _dimension(d, "C max", c, [left, a], [right, a], 2)
        d["visible_paths"].append([[cursor, 0.0], [width, 0.0]])
        d["reference_paths"].extend([[[0.0, 0.0], [0.0, bottom]], [[width, 0.0], [width, bottom]]])
        updates["guide_groove_width_mm"] = c
        if spacing:
            _dimension(d, "D", spacing, [centers[0], 0.0], [centers[1], 0.0], 1)
        d["limitations"].append("Guide bottom is cutter-dependent, round or square. Dashed depth/closure is a display choice; dg constrains maximum diameter only. C uses the table maximum.")
    _dimension(d, "A", a, [width, 0.0], [width, a])
    d["annotations"].append({"symbol": "R", "value_mm": radius, "center_depth_mm": a, "status": "primary_figure_and_table"})
    d["reference_paths"].append([[0.0, a], [width, a]])
    d["break_paths"] = [[[width * i / 16.0, bottom + .02 * pitch * math.sin(i * math.pi / 2)] for i in range(17)]]
    d["limitations"].append("F*/B* is user width, not a selected chain catalog size. Lower body depth, hub and bore unspecified; no invented section material is hatched.")
    return updates


def _ramsey(d: dict[str, Any], chain: dict[str, Any], profile: dict[str, Any],
            axial: dict[str, Any], width: float, pitch: float) -> None:
    kind = chain["chain_type"]
    depth = 0.75 * pitch  # Display extent only, NOT a Ramsey groove depth.
    _dimension(d, "W" if kind == "side_guide" else "F", width, [0.0, 0.0], [width, 0.0])
    d["dimensions"][-1].update(source="request face_width_mm", status="user_supplied_not_catalog_width")
    d["source"] = "Ramsey Products Power Transmission catalog p.13; RP/SC axial face data (not RPV, not an ASME conformity claim)"
    d["source_document"] = "Ramsey-PT-page-13.png"
    d["axial_source_system"] = "ramsey_rp_sc"
    d["radial_compatibility_status"] = "ramsey_axial_with_gb_radial_equivalence_unverified"
    d["status"] = "partial_axial_contour_unavailable"
    _gb_table_reference(d, kind, pitch, profile)
    d["schematic_parameters"] = {"display_depth_mm": depth,
                                  "status": "display_only_not_nominal_dimensions"}
    d["limitations"].append("Depth placement and stroke endpoints are display crops, not manufacturing dimensions; no hatch/fill until the cut boundary is established.")
    # A break, rather than a straight bottom, cannot be mistaken for a specified
    # groove floor. There is deliberately no closed material silhouette here.
    d["break_paths"].append([[width * i / 16.0,
                              depth + 0.025 * pitch * math.sin(i * math.pi / 2.0)]
                             for i in range(17)])
    if kind == "side_guide":
        radius = _RAMSEY_R.get(pitch)
        if radius is not None:
            # R is supported; neither its center nor chamfer height is given.
            # Show the radius with a DASHED arc at an explicitly schematic
            # placement, never borrowing GB Table 2 A/H to locate Ramsey R.
            inset = min(width / 6.0, radius * 0.25)
            center_y = math.sqrt(2.0 * radius * inset - inset * inset)
            display_end = max(depth, center_y)
            left = _round_side(0.0, 1, radius, center_y, display_end)
            right = _round_side(width, -1, radius, center_y, display_end)
            d["reference_paths"].extend([left, right,
                                          [[inset, 0.0], [width - inset, 0.0]]])
            # Crop the known flat tooth-top plane; its joins to the unknown
            # rounds remain dashed. No unsupported solid rounded outline.
            d["visible_paths"].append([[width / 3.0, 0.0], [2.0 * width / 3.0, 0.0]])
            d["annotations"].append({"symbol": "R", "value_mm": radius,
                                      "position": left[len(left) // 2][:],
                                      "label": "Tabulated R; dashed curve placement schematic",
                                      "status": "ramsey_rp_sc_radius_placement_unavailable"})
            d["schematic_parameters"]["side_round_center_depth_mm"] = center_y
            d["status"] = "partial_tabulated_radius_schematic_placement"
        else:
            d["reference_paths"].append(_closed([[0.0, 0.0], [width, 0.0],
                                                  [width, depth], [0.0, depth]]))
            d["status"] = "guide_data_unavailable"
            d["limitations"].append("Ramsey RP/SC table has no side radius for this pitch.")
        d["limitations"].append("Side chamfer center/height and chain WBG are unavailable; user W is not a verified Wmax.")
        return
    if kind not in {"center_guide", "two_center_guide"}:
        raise ValueError("Unknown Ramsey guide type")
    gw = _RAMSEY_GW.get(pitch)
    spacing = _RAMSEY_S.get(pitch) if kind == "two_center_guide" else 0.0
    if gw is None or spacing is None or axial.get("axial_layout_status") == "guide_data_unavailable":
        d["reference_paths"].append(_closed([[0.0, 0.0], [width, 0.0],
                                              [width, depth], [0.0, depth]]))
        d["status"] = "guide_data_unavailable"
        d["limitations"].append("Selected guide dimensions unavailable; dashed envelope is not an ungrooved part.")
        return
    centers = [width / 2.0] if kind == "center_guide" else [width / 2.0 - spacing / 2.0, width / 2.0 + spacing / 2.0]
    # Short entrance: its HEIGHT is unprovided, so it is dashed and carries
    # an explicit display-only label. Its 15-degree angle is from vertical.
    # Limit the illustrative opening to fit adjacent faces without pretending
    # that face width determines a manufacturing chamfer height.
    clearance = min(centers[0] - gw / 2.0, width - centers[-1] - gw / 2.0)
    if len(centers) == 2:
        clearance = min(clearance, (spacing - gw) / 2.0)
    if clearance <= 0:
        raise ValueError("Ramsey guide throats leave no face for an entrance")
    slope = math.tan(math.radians(15.0))
    chamfer_height = min(0.12 * pitch, clearance * 0.5 / slope)
    spread = chamfer_height * slope
    d["schematic_parameters"]["entrance_height_mm"] = chamfer_height
    d["status"] = "partial_dimensioned_throat_schematic_entrance"
    # Cropped solid throat strokes assert only their known width/direction.
    # Dashed continuations do not assert an exact upper join or lower depth.
    wall_start, wall_end = 0.4 * depth, 0.8 * depth
    d["reference_paths"].extend([[[0.0, 0.0], [0.0, depth]],
                                  [[width, 0.0], [width, depth]]])
    top_cursor = 0.0
    for center in centers:
        a, b = center - gw / 2.0, center + gw / 2.0
        if a < 0 or b > width:
            raise ValueError("Ramsey guide throats do not fit face width")
        mouth_left, mouth_right = a - spread, b + spread
        # Top-face strokes are cropped inside a schematic entrance envelope.
        # The complete top segment is dashed, so its unknown join stays clear.
        d["reference_paths"].append([[top_cursor, 0.0], [mouth_left, 0.0]])
        span = mouth_left - top_cursor
        if span > 0:
            d["visible_paths"].append([[top_cursor + span * 0.2, 0.0],
                                        [top_cursor + span * 0.8, 0.0]])
        d["reference_paths"].extend([[[mouth_left, 0.0], [a, chamfer_height]],
                                      [[mouth_right, 0.0], [b, chamfer_height]]])
        for x in (a, b):
            d["reference_paths"].extend([[[x, chamfer_height], [x, wall_start]],
                                          [[x, wall_end], [x, depth]]])
            d["visible_paths"].append([[x, wall_start], [x, wall_end]])
        d["annotations"].append({"symbol": "entrance", "value_deg": 15.0,
                                  "position": [mouth_left, 0.0],
                                  "label": "15° entrance; dashed height schematic",
                                  "status": "short_top_chamfer_height_unavailable"})
        top_cursor = mouth_right
        _dimension(d, "GW", gw, [a, depth], [b, depth], 1)
        d["dimensions"][-1].update(source="Ramsey p.13 center guide groove width table", status="tabulated_throat_width")
    span = width - top_cursor
    d["reference_paths"].append([[top_cursor, 0.0], [width, 0.0]])
    if span > 0:
        d["visible_paths"].append([[top_cursor + span * 0.2, 0.0],
                                    [top_cursor + span * 0.8, 0.0]])
    if spacing:
        _dimension(d, "S", spacing, [centers[0], 0.0], [centers[1], 0.0], 2)
        d["dimensions"][-1].update(source="Ramsey p.13 two-center guide spacing table", status="tabulated_center_spacing")
    d["limitations"].append("GW is the parallel throat; 15° is a short entrance, whose height/opening and lower depth Ramsey does not dimension here.")


def build_axial_view(request: dict[str, Any], chain: dict[str, Any],
                     profile: dict[str, Any], axial: dict[str, Any]) -> dict[str, Any]:
    """Return a drawing wrapper to merge into the existing axial/secondary view.

    Inputs are the request, resolved chain, derived radial profile and axial
    dictionaries of silent_chain_preview. They are never mutated. This module
    deliberately owns no registry, UI, radial calculation or CAD operation.
    """
    width = _number(axial["total_width_mm"], "total axial width")
    pitch = _number(chain["pitch_mm"], "chain pitch")
    drawing: dict[str, Any] = {
        "outline": [], "section_polygons": [], "visible_paths": [],
        "reference_paths": [], "break_paths": [], "dimensions": [],
        "bounds": [], "section_label": "A–A", "source": "", "status": "",
        "units": "mm", "coordinate_system": "x_axial_y_depth_from_tooth_top",
        "annotations": [], "limitations": [], "external_references": [],
    }
    standard = request["standard"]
    axial_updates = {}
    if standard == "gost_13552_81_13576_81":
        _gost(drawing, chain, axial, width, pitch)
    elif standard == "din_8190_8191_open":
        _din(drawing, chain, width, pitch)
    elif standard == "asme_b29_2m_open":
        if request.get("axial_source", "ramsey_rp_sc") == "gb_10855_2016":
            axial_updates = _gb(drawing, chain, profile, width, pitch)
        else:
            _ramsey(drawing, chain, profile, axial, width, pitch)
    else:
        raise ValueError(f"Unsupported silent-chain axial standard: {standard}")
    points = list(drawing["outline"])
    for key in ("section_polygons", "visible_paths", "reference_paths", "break_paths"):
        for path in drawing[key]:
            points.extend(path)
    for dimension in drawing["dimensions"]:
        _number(dimension["value"], "dimension value")
        points.extend((dimension["start"], dimension["end"]))
    min_x, max_x = drawing.get("display_x_envelope_mm", [0.0, width])
    for point in points:
        if len(point) != 2 or any(not math.isfinite(v) for v in point):
            raise ValueError("Axial drawing contains a nonfinite coordinate")
        if point[0] < min_x - 1e-7 or point[0] > max_x + 1e-7 or point[1] < -1e-7:
            raise ValueError("Axial drawing exceeds the axial/depth coordinate envelope")
    drawing["bounds"] = [min(p[0] for p in points), min(p[1] for p in points),
                         max(p[0] for p in points), max(p[1] for p in points)]
    return {"drawing": drawing, **axial_updates}
