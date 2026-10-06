"""Create-only silent-chain CAD planning from a completed Layer-2 rim spec.

Circular sample runs are recovered as native arcs only at numerical roundoff.
Other runs remain source-resolution segments: this is not an involute or
manufacturing-conformity certificate. No COM or Studio dependency lives here.
"""
from __future__ import annotations

import math
import copy
from typing import Any

_SEGMENT_TOLERANCE_MM = .0005


def _simplify(points):
    """Bound distance from every held-out source point to retained segments."""
    if len(points) <= 2:
        return points
    a, b = points[0], points[-1]
    dx, dy = b[0]-a[0], b[1]-a[1]
    norm = dx*dx+dy*dy
    distances = []
    for p in points[1:-1]:
        t = max(0., min(1., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/norm)) if norm else 0.
        distances.append(math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy))
    maximum = max(distances)
    if maximum <= _SEGMENT_TOLERANCE_MM:
        return [a, b]
    index = distances.index(maximum)+1
    return _simplify(points[:index+1])[:-1]+_simplify(points[index:])


def _circle(a, b, c):
    bx, by = b[0]-a[0], b[1]-a[1]
    cx, cy = c[0]-a[0], c[1]-a[1]
    det = 2*(bx*cy-by*cx)
    if abs(det) < 1e-12:
        return None
    u, v = bx*bx+by*by, cx*cx+cy*cy
    center = [a[0]+(cy*u-by*v)/det, a[1]+(bx*v-cx*u)/det]
    return center, math.dist(a, center), det < 0


def _disk_edge_area(a, b, radius):
    """Signed polygon/disk intersection contribution, including undercuts."""
    dx, dy = b[0]-a[0], b[1]-a[1]
    norm = dx*dx+dy*dy
    times = [0., 1.]
    if norm:
        dot = a[0]*dx+a[1]*dy
        disc = dot*dot-norm*(a[0]*a[0]+a[1]*a[1]-radius*radius)
        if disc > 0:
            times.extend(t for t in ((-dot-math.sqrt(disc))/norm, (-dot+math.sqrt(disc))/norm) if 0 < t < 1)
    times.sort()
    area = 0.
    for lo, hi in zip(times, times[1:]):
        p, q = [a[0]+lo*dx, a[1]+lo*dy], [a[0]+hi*dx, a[1]+hi*dy]
        cross = p[0]*q[1]-p[1]*q[0]
        mx, my = a[0]+(lo+hi)/2*dx, a[1]+(lo+hi)/2*dy
        if mx*mx+my*my <= radius*radius:
            area += cross/2
        else:
            area += radius*radius*math.atan2(cross, p[0]*q[0]+p[1]*q[1])/2
    return area


def _insert_tip_maximum(period, outside_radius):
    """Recover a missing radial stationary point on an exact source circle."""
    for arc in path_entities(period, "source"):
        if arc["kind"] != "arc":
            continue
        center, radius = arc["center"], arc["radius"]
        norm = math.hypot(*center)
        if not norm or abs(norm+radius-outside_radius) > 1e-7:
            continue
        candidate = [c*(norm+radius)/norm for c in center]
        begin = math.atan2(arc["start"][1]-center[1], arc["start"][0]-center[0])
        sign = -1 if arc["direction"] else 1
        span = (sign*(math.atan2(arc["end"][1]-center[1], arc["end"][0]-center[0])-begin)) % (2*math.pi)
        position = (sign*(math.atan2(candidate[1]-center[1], candidate[0]-center[0])-begin)) % (2*math.pi)
        if position > span+1e-9:
            continue
        if any(math.dist(p, candidate) <= 1e-8 for p in period):
            return period
        start = next(i for i, p in enumerate(period) if math.dist(p, arc["start"]) <= 1e-8)
        end = next(i for i, p in enumerate(period) if i > start and math.dist(p, arc["end"]) <= 1e-8)
        for i in range(start, end):
            after = (sign*(math.atan2(period[i+1][1]-center[1], period[i+1][0]-center[0])-begin)) % (2*math.pi)
            if after >= position-1e-9:
                return period[:i+1]+[candidate]+period[i+1:]
    return period


def path_entities(path: list[list[float]], prefix: str) -> list[dict[str, Any]]:
    """Recover exact circular runs; bound simplification of noncircular runs."""
    points = []
    for point in path:
        if len(point) != 2 or not all(math.isfinite(v) for v in point):
            raise ValueError("Silent-chain path contains invalid coordinates")
        if not points or math.dist(points[-1], point) > 1e-9:
            points.append(list(point))
    entities, i = [], 0
    while i < len(points)-1:
        j = i+1
        a, b = points[i], points[j]
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        while j+1 < len(points):
            c = points[j+1]
            if abs(dx*(c[1]-a[1])-dy*(c[0]-a[0]))/length > 1e-9:
                break
            if (c[0]-b[0])*dx+(c[1]-b[1])*dy <= 0:
                break
            j += 1
            b = c
        entity = {"kind": "segment", "start": a, "end": points[j]}
        if j == i+1 and i+4 < len(points):
            circle = _circle(*points[i:i+3])
            if circle:
                center, radius, clockwise = circle
                initial_sag = max(radius-math.sqrt(max(0., radius*radius-math.dist(a, b)**2/4))
                                  for a, b in zip(points[i:i+2], points[i+1:i+3]))
                k = i+2
                # Five points and source-size chords exclude a square U-floor
                # whose four corners happen to be concyclic.
                while initial_sag <= .0021 and k+1 < len(points):
                    c = points[k+1]
                    turn = ((points[k][0]-center[0])*(c[1]-center[1])
                            -(points[k][1]-center[1])*(c[0]-center[0]))
                    chord = math.dist(points[k], c)
                    sag = radius-math.sqrt(max(0., radius*radius-chord*chord/4))
                    if abs(math.dist(c, center)-radius) > 1e-8 or (turn < 0) != clockwise or sag > .0021:
                        break
                    k += 1
                if k >= i+4:
                    j = k
                    entity = {"kind": "arc", "center": center, "radius": radius,
                              "start": a, "end": points[j], "direction": clockwise}
        entity.update(id=f"{prefix}_{len(entities)}", target=f"{prefix}_{len(entities)}", line_style=1)
        entities.append(entity)
        i = j
    compact, i = [], 0
    while i < len(entities):
        if entities[i]["kind"] == "arc":
            compact.append(entities[i])
            i += 1
            continue
        run = [entities[i]["start"]]
        while i < len(entities) and entities[i]["kind"] == "segment":
            run.append(entities[i]["end"])
            i += 1
        run = _simplify(run)
        compact.extend({"kind": "segment", "start": a, "end": b} for a, b in zip(run, run[1:]))
    for i, entity in enumerate(compact):
        entity.update(id=f"{prefix}_{i}", target=f"{prefix}_{i}", line_style=1)
    if not compact or len(compact) > 450:
        raise ValueError("Silent-chain contour exceeds the bounded CAD entity budget")
    return compact


def build_silent_chain_plan(spec: dict[str, Any], profile_request: dict[str, Any], *,
                            name: str = "Geomwright silent sprocket") -> dict[str, Any]:
    """Plan axial revolution plus a full-period radial cut and circular pattern."""
    if not spec or spec.get("version") != 1 or spec.get("scope") != "functional_rim_only":
        raise ValueError("Complete the explicit construction dimensions before CAD planning")
    if not str(name).strip():
        raise ValueError("name must not be empty")
    radius = spec["outside_diameter_mm"]/2
    inner = spec["inner_rim_diameter_mm"]/2
    if inner != 0 or spec.get("blank_policy") != "solid_to_axis":
        raise ValueError("Silent sprocket CAD requires a solid blank to the axis; bores belong to other modules")
    count = spec["physical_tooth_count"]
    period = [list(p) for p in spec["radial_period"]]
    circle = spec.get("radial_tip_circle")
    if circle:
        center, cr = circle["center"], circle["radius"]
        start = next(i for i, p in enumerate(period) if math.dist(p, circle["start"]) < 1e-8)
        end = next(i for i, p in enumerate(period) if i > start and math.dist(p, circle["end"]) < 1e-8)
        if any(abs(math.dist(p, center)-cr) > 1e-8 for p in period[start:end+1]):
            raise ValueError("Source tip samples disagree with their analytic circle")
        angle = math.atan2(circle["start"][1]-center[1], circle["start"][0]-center[0])
        sweep = -((angle-math.atan2(circle["end"][1]-center[1], circle["end"][0]-center[0])) % (2*math.pi))
        steps = max(32, math.ceil(abs(sweep)/(4*math.asin(min(1., math.sqrt(.002/cr/2))))))
        cap = [[center[0]+cr*math.cos(angle+sweep*i/steps), center[1]+cr*math.sin(angle+sweep*i/steps)]
               for i in range(steps+1)]
        cap[0], cap[-1] = circle["start"], circle["end"]
        period = period[:start]+cap+period[end+1:]
    if spec["source_system"].startswith("asme"):
        period = _insert_tip_maximum(period, radius)
    axial = spec["axial_material_outline"]
    if not 0 <= inner < radius or not spec["validation"]["material_below_cuts_mm"] > 0:
        raise ValueError("Silent-chain rim must retain material below every cut")
    angles = [math.atan2(p[0], p[1]) for p in period]
    if abs(angles[-1]-angles[0]-2*math.pi/count) > 1e-7:
        raise ValueError("Silent-chain period endpoints do not match the physical tooth pitch")
    radial_r = [math.hypot(*p) for p in period]
    if min(radial_r) <= inner or max(radial_r) > radius+1e-7:
        raise ValueError("Radial profile conflicts with the completed rim radii")
    rim_entities = path_entities([[p[0], radius-p[1]] for p in axial], "rim")
    # Circular tips already belong to the revolved rim. Cutting their zero-stock
    # arc makes adjacent full-period cutters coincide and can suppress a native
    # pattern instance. Use the actual space alone for these two systems.
    cut_path = spec["radial_space"] if spec["source_system"].startswith(("gost", "din")) else period
    if spec["source_system"].startswith("asme"):
        # A rounded tip joins its flank below the blank's outside circle.
        # Partition at the actual tip maximum, not at that internal junction:
        # neighbouring cutters then meet only outside material.
        peak = 0 if abs(radial_r[0]-radius) <= 1e-7 else radial_r.index(max(radial_r))
        if abs(radial_r[peak]-radius) > 1e-7:
            raise ValueError("ASME cutter partition needs a source-defined outside-radius point")
        if peak:
            angle = -2*math.pi/count
            cut_path = [[p[0]*math.cos(angle)+p[1]*math.sin(angle),
                         p[1]*math.cos(angle)-p[0]*math.sin(angle)] for p in period[peak:]] + period[1:peak+1]
    cut_angles = [math.atan2(p[0], p[1]) for p in (cut_path[0], cut_path[-1])]
    if spec["source_system"].startswith("din"):
        cut_entities = copy.deepcopy(spec.get("radial_curve_entities") or [])
        if len(cut_entities) not in (3, 5) or any(e.get("kind") != "nurbs" for e in cut_entities):
            raise ValueError("DIN CAD requires its analytic-piece cubic NURBS plan; no segment fallback")
        for entity in cut_entities:
            entity.update(start=list(entity["points"][0]), end=list(entity["points"][-1]),
                          degree=entity["order"], line_style=1)
    else:
        cut_entities = path_entities(cut_path, "period")
    overshoot = radius+max(1.0, .01*radius)
    left = [overshoot*math.sin(cut_angles[0]), overshoot*math.cos(cut_angles[0])]
    right = [overshoot*math.sin(cut_angles[-1]), overshoot*math.cos(cut_angles[-1])]
    cut_entities.extend([
        {"id": "cap_right", "kind": "segment", "start": cut_path[-1], "end": right},
        {"id": "cap", "kind": "arc", "center": [0., 0.], "radius": overshoot,
         "start": right, "end": left, "direction": False},
        {"id": "cap_left", "kind": "segment", "start": left, "end": cut_path[0]},
    ])
    # Native YOZ sketch maps (u,v) to global (X=0,Y=-v,Z=u).
    # The source spec uses (global Z, global Y), with its space at +Y.
    for entity in cut_entities:
        if entity["kind"] == "nurbs":
            entity["points"] = [[p[0], -p[1]] for p in entity["points"]]
        for key in ("start", "end", "center"):
            if key in entity:
                entity[key] = [entity[key][0], -entity[key][1]]
        if entity["kind"] == "arc":
            entity["direction"] = not entity["direction"]
    # Independent numerical volume of the intersection of axial and radial rims.
    # Midpoint quadrature is a body-orientation/profile check, not metrology.
    volume = 0.0
    area_cache = {}
    for a, b in zip(axial, axial[1:]):
        if b[0] <= a[0]:
            continue  # bottom closure and vertical walls
        stations = 1 if abs(b[1]-a[1]) < 1e-12 else 16
        for i in range(stations):
            depth = a[1]+(b[1]-a[1])*(i+.5)/stations
            limit = radius-depth
            if limit not in area_cache:
                area = count*abs(sum(_disk_edge_area(p, q, limit) for p, q in zip(period, period[1:])))
                area_cache[limit] = max(0., area-math.pi*inner*inner)
            volume += (b[0]-a[0])/stations*area_cache[limit]
    if volume <= 0 or not math.isfinite(volume):
        raise ValueError("Silent-chain expected material volume is not positive")
    width = spec["functional_width_mm"]
    rotations = [(p[0]*math.cos(k*2*math.pi/count)+p[1]*math.sin(k*2*math.pi/count),
                  p[1]*math.cos(k*2*math.pi/count)-p[0]*math.sin(k*2*math.pi/count))
                 for k in range(count) for p in period]
    names = {"rim_sketch": "Silent rim profile", "rim": "Silent functional rim",
             "period_sketch": "Silent radial period", "cut": "Silent radial cut",
             "pattern": "Silent tooth pattern"}
    operations = [
        {"id": "period_sketch", "scenario": "numeric_profile_sketch", "params": {
            "name": names["period_sketch"], "plane": "YOZ", "entities": cut_entities,
            "parameterize": False, "require_fully_defined": False}},
        {"id": "radial_cut", "scenario": "cut_extrusion", "params": {
            "name": names["cut"], "sketch": "period_sketch.sketch", "direction": "both",
            "end_condition": "through_all", "require_fully_defined": False}},
        {"id": "tooth_pattern", "scenario": "circular_pattern", "params": {
            "name": names["pattern"], "source": "radial_cut.feature", "axis": "rim.axis",
            "count": count, "span_angle": 360., "parameterize": False}},
    ]
    return {"ok": True, "stage": "silent_chain_cad_plan", "plan_version": 1,
            "family": "silent_chain_sprocket", "name": str(name).strip(),
            "profile_request": dict(profile_request), "construction_spec": spec,
            "entity_names": names, "rim_entities": rim_entities, "operations": operations,
            "target": {"axis": "global_x", "outer_diameter": 2*radius,
                       "axial_min": 0., "axial_max": width},
            "verification": {"expected_volume_mm3": volume, "volume_relative_tolerance": .005,
                "expected_bounds_mm": [0., min(p[1] for p in rotations), min(p[0] for p in rotations),
                                       width, max(p[1] for p in rotations), max(p[0] for p in rotations)],
                "bounds_tolerance_mm": .01, "pattern_count": count},
            "accuracy": {"circular_runs": "native_arcs", "other_runs": "analytic_piece_cubic_nurbs" if spec["source_system"].startswith("din") else "source_resolution_segments",
                         "source_circular_chord_error_mm": .002,
                         "max_segment_source_deviation_mm": _SEGMENT_TOLERANCE_MM,
                         "nurbs_fit": [{"id": e["id"], **e["fit"]} for e in cut_entities if e["kind"] == "nurbs"],
                         "parameterization": "numeric_create_only", "conformity_claim": False}}
