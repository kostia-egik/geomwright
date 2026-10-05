"""Create-only silent-chain CAD planning from a completed Layer-2 rim spec.

Circular sample runs are recovered as native arcs only at numerical roundoff.
Other runs remain source-resolution segments: this is not an involute or
manufacturing-conformity certificate. No COM or Studio dependency lives here.
"""
from __future__ import annotations

import math
from typing import Any


def _circle(a, b, c):
    bx, by = b[0]-a[0], b[1]-a[1]
    cx, cy = c[0]-a[0], c[1]-a[1]
    det = 2*(bx*cy-by*cx)
    if abs(det) < 1e-12:
        return None
    u, v = bx*bx+by*by, cx*cx+cy*cy
    center = [a[0]+(cy*u-by*v)/det, a[1]+(bx*v-cx*u)/det]
    return center, math.dist(a, center), det < 0


def path_entities(path: list[list[float]], prefix: str) -> list[dict[str, Any]]:
    """Keep every source point; compact only straight/exact circular runs."""
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
        if j == i+1 and i+3 < len(points):
            circle = _circle(*points[i:i+3])
            if circle:
                center, radius, clockwise = circle
                k = i+2
                # Four points minimum avoids treating arbitrary curve triples as circles.
                while k+1 < len(points):
                    c = points[k+1]
                    turn = ((points[k][0]-center[0])*(c[1]-center[1])
                            -(points[k][1]-center[1])*(c[0]-center[0]))
                    if abs(math.dist(c, center)-radius) > 1e-8 or (turn < 0) != clockwise:
                        break
                    k += 1
                if k >= i+3:
                    j = k
                    entity = {"kind": "arc", "center": center, "radius": radius,
                              "start": a, "end": points[j], "direction": clockwise}
        entity.update(id=f"{prefix}_{len(entities)}", target=f"{prefix}_{len(entities)}", style=1)
        entities.append(entity)
        i = j
    if not entities or len(entities) > 1024:
        raise ValueError("Silent-chain contour exceeds the bounded CAD entity budget")
    return entities


def build_silent_chain_plan(spec: dict[str, Any], profile_request: dict[str, Any], *,
                            name: str = "Geomwright silent sprocket") -> dict[str, Any]:
    """Plan axial revolution plus a full-period radial cut and circular pattern."""
    if not spec or spec.get("version") != 1 or spec.get("scope") != "functional_rim_only":
        raise ValueError("Complete the explicit construction dimensions before CAD planning")
    if not str(name).strip():
        raise ValueError("name must not be empty")
    radius = spec["outside_diameter_mm"]/2
    inner = spec["inner_rim_diameter_mm"]/2
    count = spec["physical_tooth_count"]
    period = spec["radial_period"]
    axial = spec["axial_material_outline"]
    if not 0 <= inner < radius or not spec["validation"]["material_below_cuts_mm"] > 0:
        raise ValueError("Silent-chain rim must retain material below every cut")
    angles = [math.atan2(p[0], p[1]) for p in period]
    if any(b < a-1e-9 for a, b in zip(angles, angles[1:])):
        raise ValueError("Silent-chain period must be radially single-valued")
    if abs(angles[-1]-angles[0]-2*math.pi/count) > 1e-7:
        raise ValueError("Silent-chain period endpoints do not match the physical tooth pitch")
    radial_r = [math.hypot(*p) for p in period]
    if min(radial_r) <= inner or max(radial_r) > radius+1e-7:
        raise ValueError("Radial profile conflicts with the completed rim radii")
    rim_entities = path_entities([[p[0], radius-p[1]] for p in axial], "rim")
    cut_entities = path_entities(period, "period")
    overshoot = radius+max(1.0, .01*radius)
    left = [overshoot*math.sin(angles[0]), overshoot*math.cos(angles[0])]
    right = [overshoot*math.sin(angles[-1]), overshoot*math.cos(angles[-1])]
    cut_entities.extend([
        {"id": "cap_right", "kind": "segment", "start": period[-1], "end": right},
        {"id": "cap", "kind": "arc", "center": [0., 0.], "radius": overshoot,
         "start": right, "end": left, "direction": False},
        {"id": "cap_left", "kind": "segment", "start": left, "end": period[0]},
    ])
    # Independent numerical volume of the intersection of axial and radial rims.
    # Midpoint quadrature is a body-orientation/profile check, not metrology.
    volume = 0.0
    for a, b in zip(axial, axial[1:]):
        if b[0] <= a[0]:
            continue  # bottom closure and vertical walls
        for i in range(64):
            depth = a[1]+(b[1]-a[1])*(i+.5)/64
            limit = radius-depth
            sector = sum((v-u)*(max(0., min(r, limit)**2-inner**2)
                                +max(0., min(s, limit)**2-inner**2))/4
                         for u, v, r, s in zip(angles, angles[1:], radial_r, radial_r[1:]))
            volume += (b[0]-a[0])/64*count*sector
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
            "accuracy": {"circular_runs": "native_arcs", "other_runs": "source_resolution_segments",
                         "source_circular_chord_error_mm": .002,
                         "parameterization": "numeric_create_only", "conformity_claim": False}}
