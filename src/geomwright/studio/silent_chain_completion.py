"""Layer-2 completion of a functional rim; no CAD calls or conformity claim.

Source-only previews may contain schematic crops. Construction geometry uses
only applicable source dimensions plus explicit request values. Suggestions are
returned as data, never promoted to inputs. Readiness requires complete validated
values, not a confirmation checkbox. The physical lower closure defines an inner rim radius, not a
hub, shaft seat, keyway, or an inferred display break.
"""

from __future__ import annotations

import copy
import math
from typing import Any

from .silent_chain_axial import _closed, _round_side

_USER_FIELDS = {
    "body_depth_mm", "guide_depth_mm", "guide_bottom_radius_mm", "guide_width_mm", "guide_spacing_mm",
    "entrance_height_mm", "axial_round_radius_mm", "tool_root_radius_mm", "tool_floor_depth_mm", "din_rack_resolution",
    "square_tip_resolution", "square_tip_diameter_mm",
}


def has_user_geometry(request: dict[str, Any]) -> bool:
    """Infer construction intent from actual dimensions or resolved choices."""
    return any(request.get(name) not in (None, "unresolved") for name in _USER_FIELDS)


def _slot(left: float, right: float, depth: float, bottom_r: float,
          height: float, radius: float | None) -> list[list[float]]:
    if right-left <= 1e-9:
        raise ValueError("Guide throat collapses at the numeric geometry tolerance")
    if bottom_r < 0 or bottom_r > (right-left)/2+1e-9 or depth-bottom_r < height-1e-9:
        raise ValueError("Guide bottom radius/depth cannot fit below the entrance")
    if radius is None:  # Ramsey's 15-degree entrance; height is a user value.
        spread = height * math.tan(math.radians(15))
        gl = [[left-spread, 0.0], [left, height], [left, depth-bottom_r]]
        gr = [[right+spread, 0.0], [right, height], [right, depth-bottom_r]]
    else:
        gl = _round_side(left, -1, radius, height, depth-bottom_r)
        gr = _round_side(right, 1, radius, height, depth-bottom_r)
    bottom = []
    if bottom_r:
        step = 4*math.asin(min(1.0, math.sqrt(.002/bottom_r/2)))
        count = max(2, math.ceil((math.pi/2)/step))
        if count > 4096:
            raise ValueError("Guide bottom exceeds the bounded arc sampling budget")
        # Quarter-circle corners; r=width/2 is the semicircular alternative.
        for cx, lo, hi in ((left+bottom_r, math.pi, math.pi/2),
                           (right-bottom_r, math.pi/2, 0.0)):
            bottom.extend([[cx+bottom_r*math.cos(lo+(hi-lo)*i/count),
                            depth-bottom_r+bottom_r*math.sin(lo+(hi-lo)*i/count)]
                           for i in range(count+1)])
    else:
        bottom = [[left, depth], [right, depth]]
    return gl + bottom + list(reversed(gr))


def _clip_below(polygon: list[list[float]], height: float) -> list[list[float]]:
    """Clip the material polygon to the source-defined section-cut level."""
    output = []
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        inside_a, inside_b = a[1] >= height, b[1] >= height
        if inside_a:
            output.append(a)
        if inside_a != inside_b:
            t = (height-a[1])/(b[1]-a[1])
            output.append([a[0]+t*(b[0]-a[0]), height])
    return _closed(output)


def complete_silent_chain_geometry(request: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    """Return completion report and, when fully specified, a construction spec.

    The input preview is not mutated. Missing values return a bounded report;
    invalid supplied geometry raises before any complete/readiness result.
    """
    profile, axial = preview["profile"], preview["axial"]
    source_drawing = axial["drawing"]
    pitch, width = profile["pitch_mm"], axial["total_width_mm"]
    outside_r = preview["derived"]["outside_diameter_mm"]/2
    root_depth = outside_r-preview["derived"]["root_diameter_mm"]/2
    standard, kind = request["standard"], profile["chain_type"]
    defined = has_user_geometry(request)
    fields: dict[str, dict[str, Any]] = {}

    def require(name: str, suggested: float | str) -> None:
        if isinstance(suggested, float):
            suggested = round(suggested, 6)  # proposals only, never round entered values
        fields[name] = {"suggested": suggested, "value": request.get(name), "required": True}

    def number(name: str) -> float:
        value = request.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be an explicit finite number")
        return float(value)

    if standard.startswith("din") and profile["chain_series"] == "06":
        require("din_rack_resolution", "keep_radii")
    if standard.startswith("asme"):
        tool = preview["diagnostics"]["root_policy"]
        require("tool_root_radius_mm", (.08 if pitch < 9.525 else .04)*pitch)
        require("tool_floor_depth_mm", tool["floor_depth_in_tooth_frame_mm"]+.01*pitch)
        if request["physical_tooth_count"] in {91, 96} and preview["derived"]["tip_shape"] == "square":
            require("square_tip_resolution", "accept_ramsey")
            if request.get("square_tip_resolution") == "custom_diameter":
                require("square_tip_diameter_mm", preview["derived"]["outside_diameter_mm"])

    reference = next((r for r in source_drawing.get("external_references", [])
                      if r.get("axial_source_system") == "gb_10855_2016"), None)
    # No cross-source filling: only use GB facts when the GB source is selected.
    gb = standard.startswith("asme") and request.get("axial_source") == "gb_10855_2016"
    values = reference["values_mm"] if gb and reference else {}
    guides = standard.startswith("asme") and kind in {"center_guide", "two_center_guide"}
    radius = None
    entrance = 0.0
    guide_width = None
    spacing = 0.0
    depth = 0.0
    if standard.startswith("gost"):
        require("entrance_height_mm", .4*pitch)  # C1 is approximate, not an exact nominal.
        entrance = request.get("entrance_height_mm") or .4*pitch
        radius = 50.0 if kind == 2 else pitch
        if kind == 1:  # Figure/Table also mark r approximately equal to pitch.
            require("axial_round_radius_mm", pitch)
            radius = request.get("axial_round_radius_mm") or pitch
    elif standard.startswith("din"):
        centers = source_drawing.get("schematic_parameters", {})
        entrance = centers.get("guide_round_center_depth_mm", centers.get("outer_round_center_depth_mm", 0.0))
        radius = next(a["value_mm"] for a in source_drawing["annotations"] if a["symbol"] == "r")
    if standard.startswith("asme"):
        if kind == "side_guide":
            radius = values.get("R") if gb else next((a["value_mm"] for a in source_drawing["annotations"] if a["symbol"] == "R"), None)
            if radius is None:
                require("axial_round_radius_mm", .5*pitch)
                radius = request.get("axial_round_radius_mm") or .5*pitch
            entrance = values.get("A", 0.0)
            if not entrance:
                require("entrance_height_mm", min(.15*pitch, radius*.5))
                entrance = request.get("entrance_height_mm") or fields["entrance_height_mm"]["suggested"]
        elif guides:
            guide_width = values.get("C") if gb else axial.get("guide_groove_width_mm")
            if guide_width is None:
                require("guide_width_mm", .2*pitch)
                guide_width = request.get("guide_width_mm") or .2*pitch
            if kind == "two_center_guide":
                spacing = values.get("D") if gb else (abs(axial["guide_grooves_mm"][1]["center_mm"]-axial["guide_grooves_mm"][0]["center_mm"]) if len(axial["guide_grooves_mm"]) == 2 else None)
                if spacing is None:
                    require("guide_spacing_mm", width*.5)
                    spacing = request.get("guide_spacing_mm") or width*.5
            radius, entrance = (values.get("R"), values.get("A", 0.0)) if gb else (None, 0.0)
            if gb and radius is None:
                require("axial_round_radius_mm", .5*pitch)
                radius = request.get("axial_round_radius_mm") or .5*pitch
            if not entrance:
                require("entrance_height_mm", .12*pitch)
                entrance = request.get("entrance_height_mm") or .12*pitch
            require("guide_bottom_radius_mm", guide_width/2)
            bottom_r = request.get("guide_bottom_radius_mm")
            if bottom_r is None:
                bottom_r = guide_width/2
            min_depth = (preview["derived"]["outside_diameter_mm"]-preview["derived"]["max_guide_groove_diameter_mm"])/2
            # Explicit conservative clearance rule: retain full parallel width
            # down to the dg bound before beginning the bottom corner arcs.
            require("guide_depth_mm", max(min_depth, entrance)+bottom_r+.05*pitch)
            depth = request.get("guide_depth_mm") or fields["guide_depth_mm"]["suggested"]
    else:
        depth = max((d["value"] for d in source_drawing["dimensions"] if d["symbol"] in {"h₁", "h₃"}), default=0.0)
    required_depth = max(root_depth, depth, entrance)
    require("body_depth_mm", min(required_depth+.4*pitch, (required_depth+outside_r)/2))
    missing = [name for name in fields if request.get(name) is None or request.get(name) == "unresolved"]
    report = {"mode": "user_defined" if defined else "source_only", "fields": fields,
              "missing_fields": missing,
              "geometry_complete": False, "ready_for_cad_planning": False,
              "cad_build_available": False, "conformity_claim": False,
              "status": "source_only" if not defined else "missing_values" if missing else "defined"}
    if defined:
        inactive = [name for name in _USER_FIELDS-fields.keys() if request.get(name) not in (None, "unresolved")]
        if inactive:
            raise ValueError(f"Construction parameters not applicable to this selection: {', '.join(sorted(inactive))}")
    if not defined or missing:
        return {"completion": report, "construction_spec": None}
    if preview["geometry"]["partial"] or preview["geometry"].get("provisional_tip_paths"):
        raise ValueError("Radial source conflict must be explicitly resolved before construction")

    for name in fields:
        if name not in {"din_rack_resolution", "square_tip_resolution"}:
            number(name)
    body_depth = number("body_depth_mm")
    if not required_depth+1e-9 < body_depth <= outside_r:
        raise ValueError("Body depth must leave positive material below tooth/guide cuts and must not pass the rotational axis")
    d = copy.deepcopy(source_drawing)
    if standard.startswith("gost"):
        h2 = next(dim["value"] for dim in d["dimensions"] if dim["symbol"] == "h₂")
        if kind == 1:
            left, right = width/2-profile["plate_thickness_mm"], width/2+profile["plate_thickness_mm"]
            ol, ore = _round_side(0, 1, radius, entrance, h2), _round_side(width, -1, radius, entrance, h2)
            gl, gr = _round_side(left, -1, radius, entrance, depth), _round_side(right, 1, radius, entrance, depth)
            top = list(reversed(ol))+gl+list(reversed(gr))+ore
        else:
            rib = axial["tooth_width_mm"]
            margin = (width-(axial["row_count"]-1)*18.0-rib)/2
            top = [[0.0, depth]]
            for i in range(axial["row_count"]):
                left = margin+i*18.0
                top += list(reversed(_round_side(left, 1, radius, entrance, depth)))
                top += _round_side(left+rib, -1, radius, entrance, depth)
            top.append([width, depth])
        for dim in d["dimensions"]:
            if dim["symbol"] == "C₁ ≈":
                dim.update(symbol="C₁*", value=entrance, end=[dim["end"][0], entrance], status="user_defined")
        d["annotations"] = [{"symbol": "r*" if kind == 1 else "r", "value_mm": radius,
                             "center_depth_mm": entrance, "status": "user_defined" if kind == 1 else "source"}]
    elif standard.startswith("din"):
        # Explicit acceptance of tangent-to-wall circles selects the previous
        # candidate's unique placement from c or (g-f1)/2 and the listed radius.
        top = d["reference_paths"][0]
    elif kind == "side_guide":
        left = _round_side(0.0, 1, radius, entrance, entrance)
        right = _round_side(width, -1, radius, entrance, entrance)
        if left[0][0] >= right[0][0]:
            raise ValueError("User side rounds overlap at the selected width")
        top = list(reversed(left))+right
    else:
        min_depth = (preview["derived"]["outside_diameter_mm"]-preview["derived"]["max_guide_groove_diameter_mm"])/2
        if depth < min_depth-1e-9:
            raise ValueError("User guide depth violates the maximum guide-diameter bound")
        if depth-number("guide_bottom_radius_mm") < min_depth-1e-9:
            raise ValueError("Guide bottom starts above the selected full-width clearance bound")
        centers = [width/2] if kind == "center_guide" else [width/2-spacing/2, width/2+spacing/2]
        top, cursor = [[0.0, 0.0]], 0.0
        for center in centers:
            slot = _slot(center-guide_width/2, center+guide_width/2, depth,
                         number("guide_bottom_radius_mm"), entrance, radius)
            if slot[0][0] <= cursor or slot[-1][0] >= width:
                raise ValueError("User guide entrances overlap or exceed the face width")
            top.extend(slot)
            cursor = slot[-1][0]
        top.append([width, 0.0])
    if any(b[0] < a[0]-1e-9 for a, b in zip(top, top[1:])):
        raise ValueError("Completed axial entrances overlap; the top contour is not monotone")
    closure = [[width, body_depth], [0.0, body_depth]]
    vertices = []
    for point in top+closure:
        if not vertices or math.dist(point, vertices[-1]) > 1e-9:
            vertices.append(point)
    if len(vertices) > 2 and math.dist(vertices[0], vertices[-1]) <= 1e-9:
        vertices.pop()
    outline = _closed(vertices)
    if any(not math.isfinite(v) for p in outline for v in p):
        raise ValueError("Completed axial outline contains a nonfinite coordinate")
    area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(outline, outline[1:]))/2
    if not math.isfinite(area) or area <= 0:
        raise ValueError("Completed axial material outline has invalid orientation/area")
    d.update(outline=outline, user_paths=[outline], visible_paths=[],
             reference_paths=[], break_paths=[], status="user_defined_geometry",
             schematic_bottom_y_mm=None, limitations=["User-defined geometry is not a conformity certificate or a live-verified CAD body."])
    d.pop("schematic_parameters", None)
    for annotation in d["annotations"]:
        annotation.pop("position", None)
        annotation.update(center_depth_mm=entrance, status="dimension_with_explicit_construction_placement",
                          label="Dimension with explicit construction placement")
    section = next((dim["value"] for dim in d["dimensions"] if dim["symbol"] in {"h₂", "h"}), None)
    d["section_polygons"] = [_clip_below(outline[:-1], section)] if section is not None else []
    for name, value in (("δ", body_depth),):
        d["dimensions"].append({"symbol": name, "value": value, "orientation": "vertical",
                                "start": [width, 0.0], "end": [width, value], "level": 3,
                                "status": "user_defined"})
    # Old display crops are not dimensional anchors in a completed outline.
    for dim in d["dimensions"]:
        if dim["symbol"] in {"GW", "C max"}:
            dim["start"][1] = dim["end"][1] = depth-number("guide_bottom_radius_mm")
    if guides and "guide_width_mm" in fields:
        for center in centers:
            y = depth-number("guide_bottom_radius_mm")
            d["dimensions"].append({"symbol": "GW*", "value": guide_width, "orientation": "horizontal",
                                    "start": [center-guide_width/2, y], "end": [center+guide_width/2, y],
                                    "level": 2, "status": "user_defined"})
    if standard.startswith("asme") and "entrance_height_mm" in fields:
        d["dimensions"].append({"symbol": "E*", "value": entrance, "orientation": "vertical",
                                "start": [width, 0.0], "end": [width, entrance], "level": 1,
                                "status": "user_defined"})
    if standard.startswith("asme") and not d["annotations"]:
        d["annotations"].append({"symbol": "R*" if radius is not None else "entrance",
                                **({"value_mm": radius} if radius is not None else {"value_deg": 15.0}),
                                "center_depth_mm": entrance, "status": "explicit_construction"})
    points = outline+[p for dim in d["dimensions"] for p in (dim["start"], dim["end"])]
    d["bounds"] = [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]
    ax = copy.deepcopy(axial)
    ax.update(drawing=d, axial_layout_status="user_defined_geometry")
    extent = [min(p[0] for p in outline), max(p[0] for p in outline)]
    ax["overall_width_mm"] = extent[1]-extent[0]
    if guides:
        ax.update(guide_groove_width_mm=guide_width, guide_grooves_mm=[
            {"center_mm": c, "width_mm": guide_width, "depth_mm": depth,
             "bottom_radius_mm": number("guide_bottom_radius_mm"),
             "parallel_depth_mm": depth-number("guide_bottom_radius_mm"),
             "source": "explicit_user_construction"} for c in centers])
    elif ax["guide_grooves_mm"]:
        throat = next((dim["value"] for dim in d["dimensions"] if dim["symbol"] == "f₁"), ax["guide_grooves_mm"][0]["width_mm"])
        mouth = next((dim["value"] for dim in d["dimensions"] if dim["symbol"] == "g"), throat)
        ax["guide_groove_width_mm"] = throat
        ax["guide_grooves_mm"] = [{**g, "width_mm": throat, "mouth_width_mm": mouth,
                                    "depth_mm": depth, "bottom_radius_mm": 0.0,
                                    "source": "source_dimensions_with_selected_square_floor"} for g in ax["guide_grooves_mm"]]
    selected = {name: request[name] for name in fields}
    report.update(geometry_complete=True, ready_for_cad_planning=True, cad_build_available=True, status="defined")
    rules = ["exact_source_dimensions_retained_except_explicit_conflict_resolution", "explicit_lower_closure"]
    rules.append("Ramsey_15deg_entrance" if radius is None else "tangent_circular_axial_entrances")
    if standard.startswith("gost"):
        rules.append("approximate_axial_dimensions_explicitly_selected")
        if kind == 2:
            rules.append("symmetric_rib_layout_with_common_angular_phase")
    if guides:
        rules.extend(["corner_rounded_or_square_guide_floor", "full_width_guide_clearance_to_dg_bound"])
    elif ax["guide_grooves_mm"]:
        rules.append("source_illustrated_square_guide_floor")
    if standard.startswith("asme"):
        rules.append("exact_tooth_floor_with_tangent_corner_arcs")
    spec = {"version": 1, "scope": "functional_rim_only", "axis": "global_x", "units": "mm",
            "coordinate_system": "x_axial_y_depth_from_tooth_top",
            "radial_coordinate_system": "first_global_z_second_global_y_space_center_on_positive_y",
            "source_system": standard, "axial_source": source_drawing.get("axial_source_system", standard),
            "selection": {"designation": profile["designation"], "chain_type": kind,
                          "physical_tooth_count": request["physical_tooth_count"],
                          "accuracy_class": request.get("accuracy_class") if standard.startswith("gost") else None},
            "user_parameters": selected, "accepted_rules": rules,
            "resolved_dimensions": {"tool_tip_radius_mm": preview["derived"].get("tool_tip_radius_mm"),
                                    "tool_tooth_height_mm": preview["derived"].get("tool_tooth_height_mm"),
                                    "tool_root_radius_mm": preview["derived"].get("tool_root_radius_mm", preview["derived"].get("root_round_radius_mm")),
                                    "entrance_height_mm": entrance, "entrance_radius_mm": radius},
            "outside_diameter_mm": 2*outside_r, "inner_rim_diameter_mm": 2*(outside_r-body_depth),
            "functional_width_mm": width, "axial_extent_mm": extent,
            "radial_parameters": copy.deepcopy(preview["derived"]),
             "physical_tooth_count": request["physical_tooth_count"], "radial_period": preview["geometry"]["period_path"],
             "radial_space": preview["geometry"]["profile_path"],
             "radial_tip_circle": ({
                 "center": [preview["derived"]["tip_arc_center_diameter_mm"]/2*math.sin(math.pi/request["physical_tooth_count"]),
                            preview["derived"]["tip_arc_center_diameter_mm"]/2*math.cos(math.pi/request["physical_tooth_count"])],
                 "radius": preview["derived"]["tip_round_radius_mm"],
                 "start": preview["geometry"]["tooth_tip_path"][0],
                 "end": preview["geometry"]["tooth_tip_path"][-1], "direction": True,
             } if standard.startswith("asme") and preview["derived"].get("tip_shape") == "round" else None),
            "axial_material_outline": outline, "guide_grooves": ax["guide_grooves_mm"],
            "relative_rib_phases_deg": ax.get("relative_rib_phases_deg", [0.0]),
            "rib_centers_mm": ax.get("rib_centers_mm", [width/2]),
            "rib_width_mm": ax["tooth_width_mm"],
            "validation": {"finite": True, "axial_top_x_monotone": True, "material_area_mm2": area,
                           "material_below_cuts_mm": body_depth-max(root_depth, depth, entrance)},
            "manufacturing_conformity_verified": False, "cad_verified": False}
    return {"completion": report, "construction_spec": spec, "axial": ax}
