"""Native, fail-fast executor for the bounded coaxial host plan.

Loaded with the bridge namespace; never owns a connection, mutex or retry loop.
Recipe recognition is deliberately separate from a fresh final-body audit.
"""
import json
import hashlib
import math
import os
import re
import sys
from copy import deepcopy


SCHEMA = "geomwright.construction_chain.recipe"
# Comparison floors, not manufacturing tolerances. Match rotational readback and
# PATTERN-001 mass-property bounds; a missing operation cannot pass delta checks.
LENGTH_TOL = 1e-5
VOLUME_REL = 5e-4
VOLUME_FLOOR = 1e-6  # cm3 = 0.001 mm3
TOTAL_VOLUME_REL = 1e-5
TOTAL_VOLUME_FLOOR = 1e-7  # Existing shaft/cone total-volume contract.
_GEOMETRY_RUNTIME = None
LABELS = {"stepped_shaft": "Stepped shaft", "external_conical_step": "External cone",
          "internal_cylindrical_step": "Internal cylindrical bore", "face_ring_groove": "Face ring groove",
           "gear_spur": "External cylindrical gear", "external_polygonal_step": "External polygon", "external_flat_step": "External flat",
            "bolt_circle_holes": "Bolt circle holes", "straight_spline": "Straight spline shaft"}
FOUNDATIONS = ("gear_spur", "straight_spline")


def _foundation(steps):
    return steps[0] if steps[0]["module"] in FOUNDATIONS else None


def _family_plan(step):
    return step["family_plan"] if step["module"] == "straight_spline" else step["gear_plan"]


def _prism_runtime():
    import importlib.util
    spec = importlib.util.spec_from_file_location("chain_prism", os.path.join(os.path.dirname(__file__), "chain_prism_runtime.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _holes_runtime():
    import importlib.util
    spec = importlib.util.spec_from_file_location("chain_holes", os.path.join(os.path.dirname(__file__), "chain_holes_runtime.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spline_runtime():
    import importlib.util
    spec = importlib.util.spec_from_file_location("chain_spline", os.path.join(os.path.dirname(__file__), "chain_spline_runtime.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _thread_runtime():
    import importlib.util
    spec = importlib.util.spec_from_file_location("chain_thread", os.path.join(os.path.dirname(__file__), "chain_thread_runtime.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
        allow_nan=False, separators=(",", ":")).encode("ascii")).hexdigest()


def _profile_disk_area(entities, radius, root, spline=False):
    """Bounded numeric profile preflight, independently of supplied volume fields."""
    points = []
    for entity in entities:
        kind = entity["kind"]
        if kind == "nurbs":
            controls, knots, weights = entity["points"], entity["knots"], entity["weights"]
            n, degree = len(controls)-1, 3
            if len(knots) != len(controls)+degree+1 or len(weights) != len(controls) or any(_number(w) != 1 for w in weights):
                raise ValueError("Invalid cubic family spline data")
            if any(_number(a) > _number(c) for a, c in zip(knots, knots[1:])) or knots[degree] >= knots[n+1]:
                raise ValueError("Invalid family spline knot domain")
            samples = []
            for j in range(257):
                t = knots[degree]+(knots[n+1]-knots[degree])*j/256
                span = n if j == 256 else next(i for i in range(degree, n+1) if knots[i] <= t < knots[i+1])
                d = [list(controls[i]) for i in range(span-degree, span+1)]
                for level in range(1, degree+1):
                    for k in range(degree, level-1, -1):
                        i = span-degree+k
                        denominator = knots[i+degree-level+1]-knots[i]
                        alpha = (t-knots[i])/denominator if denominator else 0
                        d[k] = [(1-alpha)*a+alpha*c for a, c in zip(d[k-1], d[k])]
                samples.append(d[degree])
        elif kind == "arc":
            if (not spline and entity["center"] != [0, 0]) or not isinstance(entity["direction"], bool):
                raise ValueError("Gear cap must be a centred directed arc")
            r = _number(entity["radius"])
            if r <= 0 or (not spline and r <= radius):
                raise ValueError("Gear cutter cap must lie outside the blank")
            start, end = entity["start"], entity["end"]
            center = entity["center"]
            _close(math.dist(start, center), r)
            _close(math.dist(end, center), r)
            a, c = math.atan2(start[1]-center[1], start[0]-center[0]), math.atan2(end[1]-center[1], end[0]-center[0])
            sweep = -((a-c) % (2*math.pi)) if entity["direction"] else (c-a) % (2*math.pi)
            if abs(sweep) >= math.pi:
                raise ValueError("Gear cap arc takes the wrong angular branch")
            count = 256 if spline else 64
            samples = [[center[0]+r*math.cos(a+sweep*j/count), center[1]+r*math.sin(a+sweep*j/count)] for j in range(count+1)]
        else:
            samples = [entity["start"], entity["end"]]
        if points and math.dist(points[-1], samples[0]) > LENGTH_TOL:
            raise ValueError("Gear cutter contour is disconnected")
        points.extend(samples if not points else samples[1:])
    if math.dist(points[-1], points[0]) > LENGTH_TOL:
        raise ValueError("Gear cutter contour is open")
    if any(math.hypot(*p) < root-.05 for p in points):
        raise ValueError("Gear numeric cutter invades the solid root core")
    # Signed disk/polygon intersection via segment splitting. Outside pieces
    # contribute circular-sector area, inside pieces triangular area.
    area = 0.0
    for a, c in zip(points, points[1:]):
        delta = [c[i]-a[i] for i in (0, 1)]
        aa = sum(x*x for x in delta)
        bb = 2*sum(x*y for x, y in zip(a, delta))
        cc = sum(x*x for x in a)-radius**2
        splits = [0., 1.]
        discriminant = bb*bb-4*aa*cc
        if aa and discriminant > 0:
            splits.extend(t for t in ((-bb-math.sqrt(discriminant))/(2*aa), (-bb+math.sqrt(discriminant))/(2*aa)) if 0 < t < 1)
        splits.sort()
        for lo, hi in zip(splits, splits[1:]):
            p, q = [[a[i]+t*delta[i] for i in (0, 1)] for t in (lo, hi)]
            cross, dot = p[0]*q[1]-p[1]*q[0], p[0]*q[0]+p[1]*q[1]
            midpoint = [a[i]+(lo+hi)/2*delta[i] for i in (0, 1)]
            area += cross/2 if math.hypot(*midpoint) <= radius else radius**2*math.atan2(cross, dot)/2
    return abs(area)


def _spline_guard(step, original):
    """Bounded existing shaft recipe, with independent contour/material preflight.

    Catalog resolution remains host-owned. The numeric disk intersection here
    only guards the prepared plan; native acceptance still uses the exact family
    volume, actual profile readback and each patterned material removal.
    """
    plan, ns = step["family_plan"], step["namespace"]
    label = LABELS["straight_spline"] + " [" + step["id"] + "]"
    if (plan.get("stage") != "straight_spline_cad_plan" or plan.get("plan_version") != 1 or
            plan.get("family") != "straight_spline" or plan.get("name") != label or
            plan.get("parameter_prefix") != ns or ns != "CH_" + step["id"].upper() or
            plan.get("ownership", {}).get("schema") != "geomwright.managed_spline_straight"):
        raise ValueError("Invalid namespaced straight spline family plan")
    request, g, v = plan["profile_request"], plan["geometry"], plan["verification"]
    if not _input_matches(original["parameters"], request) or plan["ownership"]["source_profile"] != request:
        raise ValueError("Spline request differs from chain recipe")
    if request.get("body") != "shaft" or g["body"] != "shaft" or request.get("standard") != "gost_1139_80":
        raise ValueError("Only GOST straight spline shaft foundations are supported")
    root, radius, width, chamfer = [_number(g[k]) for k in ("root_radius_mm", "outer_radius_mm", "length_mm", "chamfer_mm")]
    if request.get("include_tip_chamfer") is False:
        chamfer = 0
    count = g["tooth_count"]
    if isinstance(count, bool) or int(count) != count or not 4 <= count <= 40 or not 0 < root < radius or width <= 0 or not 0 <= chamfer < min(width/2, radius-root):
        raise ValueError("Invalid spline core/blank/chamfer/count")
    _close(width, request["length_mm"])
    for key in ("tooth_count", "inner_diameter_mm", "outer_diameter_mm", "tooth_width_mm"):
        if request.get(key) is not None:
            _close(g[key], request[key])
    _close(2*radius, g["outer_diameter_mm"])
    if request.get("tip_chamfer_mm") is not None and request.get("include_tip_chamfer"):
        _close(chamfer, request["tip_chamfer_mm"])
    section = step["section"]
    core = min(root, radius-chamfer)
    if section.get("carrier_role") != "solid_root_core" or len(section["segments"]) != 1:
        raise ValueError("Spline requires a single solid root core")
    for actual, expected in ((section["start_mm"], -width), (section["end_mm"], 0),
            (section["root_radius_mm"], root), (section["bounding_radius_mm"], radius),
            (section["segments"][0]["start_radius_mm"], core), (section["segments"][0]["end_radius_mm"], core)):
        _close(actual, expected)
    ops = plan["workflow"]["params"]["operations"]
    ids = ["blank"] + (["tip_chamfer_face_a", "tip_chamfer_face_b"] if chamfer else []) + ["tooth_space_sketch", "tooth_space_cut", "tooth_space_pattern"]
    kinds = ["cylindrical_blank"] + (["rotational_cut"]*2 if chamfer else []) + ["numeric_profile_sketch", "cut_extrusion", "circular_pattern"]
    if [op.get("id") for op in ops] != ids or [op.get("scenario") for op in ops] != kinds:
        raise ValueError("Only prepared straight spline shaft operations are supported")
    suffixes = [" blank"] + ([" tip chamfer A", " tip chamfer B"] if chamfer else []) + [" one tooth space", " one tooth space cut", " tooth space pattern"]
    fields = {
        "cylindrical_blank": {"name", "sketch_name", "outside_diameter", "width", "plane", "axis", "parameterize", "require_fully_defined"},
        "rotational_cut": {"name", "plane", "axis", "profile_points", "angle_degrees", "require_fully_defined"},
        "numeric_profile_sketch": {"name", "plane", "entities", "parameterize", "require_fully_defined", "profile_status"},
        "cut_extrusion": {"name", "sketch", "direction", "end_condition", "require_fully_defined"},
        "circular_pattern": {"name", "source", "axis", "count", "span_angle", "parameterize"}}
    for op, suffix in zip(ops, suffixes):
        if set(op) != {"id", "scenario", "params"} or set(op["params"]) - fields[op["scenario"]] or op["params"]["name"] != label+suffix:
            raise ValueError("Spline operation identity/fields differ")
    blank, profile, cut, pattern = [op["params"] for op in (ops[0], ops[-3], ops[-2], ops[-1])]
    if blank["plane"] != "YOZ" or blank["axis"] != "x_axis" or blank["sketch_name"] != label+" blank sketch":
        raise ValueError("Invalid spline blank frame")
    _close(blank["outside_diameter"], 2*radius)
    _close(blank["width"], width)
    if any(p.get("require_fully_defined") is not False for p in (blank, profile, cut)) or any(p.get("parameterize") is not False for p in (blank, profile, pattern)):
        raise ValueError("Existing numeric spline mode must be preserved")
    if profile["plane"] != "YOZ" or cut["sketch"] != "tooth_space_sketch.sketch" or cut["direction"] != "both" or cut["end_condition"] != "through_all":
        raise ValueError("Invalid spline profile/cut frame")
    if pattern["source"] != "tooth_space_cut.feature" or pattern["axis"] != "blank.axis":
        raise ValueError("Spline pattern has foreign supports")
    _close(pattern["count"], count)
    _close(pattern["span_angle"], 360)
    entities = profile["entities"]
    if not 4 <= len(entities) <= 16 or len(entities) != g["space_entity_count"] or _hash(entities) != step["verification"]["profile_entities_sha256"]:
        raise ValueError("Spline numeric contour size/signature differs")
    section_area = _spline_space_guard(entities, g)
    expected = section_area*width
    if chamfer:
        # Composite Simpson guard for the two conical end regions. Exact family
        # integration still owns the accepted value and native body comparison.
        n = 16
        values = []
        for i in range(n+1):
            r = radius-chamfer+chamfer*i/n
            values.append(section_area-(math.pi*r*r-count*_profile_disk_area(entities, r, root, spline=True)))
        expected -= 2*chamfer/(3*n)*sum(value*(1 if i in (0,n) else 4 if i%2 else 2) for i,value in enumerate(values))
    for op, points in zip(ops[1:-3], ([[-width,radius-chamfer],[-width+chamfer,radius],[-width,radius]], [[0,radius-chamfer],[-chamfer,radius],[0,radius]])):
        p = op["params"]
        if p["plane"] != "XOY" or p["axis"] != "blank.axis" or p["profile_points"] != points or p["angle_degrees"] != 360 or p["require_fully_defined"] is not False:
            raise ValueError("Spline chamfer plan differs")
    _close(v["expected_volume_mm3"], expected, .01, .0005)
    if not math.pi*core**2*width <= v["expected_volume_mm3"] <= math.pi*radius**2*width:
        raise ValueError("Spline expected volume outside core/blank bounds")
    for key, target in (("max_radius_mm", radius), ("length_mm", width), ("pattern_count", count)):
        _close(v[key], target)
    if not 0 < _number(v["volume_relative_tolerance"]) <= .005 or not 0 < _number(v["bounds_tolerance_mm"]) <= .05 or step["verification"].get("family_verification") != v:
        raise ValueError("Spline family tolerance/verification differs")
    return _number(v["expected_volume_mm3"])/1000


def _spline_space_guard(entities, geometry):
    """Shared bounded contour/material consistency, never a second catalog."""
    root, radius = [_number(geometry[k]) for k in ("root_radius_mm", "outer_radius_mm")]
    hub = geometry.get("body") == "hub"
    if hub:
        radius = _number(geometry["outer_diameter_mm"])/2
    count = geometry["tooth_count"]
    if not 4 <= len(entities) <= 16 or len(entities) != geometry["space_entity_count"]:
        raise ValueError("Invalid spline numeric contour size")
    for e in entities:
        allowed = {"segment": {"id", "kind", "start", "end", "style"}, "arc": {"id", "kind", "start", "end", "center", "radius", "direction", "style"}}.get(e.get("kind"))
        if allowed is None or set(e) != allowed or e["style"] != 1 or not str(e["id"]).startswith("spline_space_"):
            raise ValueError("Unsupported spline contour entity")
        for p in (e["start"], e["end"], e.get("center", [0, 0])):
            if len(p) != 2:
                raise ValueError("Spline contour must be 2D")
            for n in p:
                _number(n)
    area = _profile_disk_area(entities, radius, root, spline=True)
    _close(area, geometry["space_area_mm2"], .001, .0005)
    section_area = math.pi*(geometry["hub_outside_radius_mm"]**2-root**2)-count*area if hub else math.pi*radius**2-count*area
    _close(section_area, geometry["section_area_mm2"], .001, .0005)
    return section_area


def _gear_guard(step, original):
    """Accept only the bounded family operation recipe, never a general workflow."""
    plan, ns = step["gear_plan"], step["namespace"]
    label = LABELS["gear_spur"] + " [" + step["id"] + "]"
    if (plan.get("stage") != "gear_spur_cad_plan" or plan.get("plan_version") != 1 or
            plan.get("family") != "gear_spur" or plan.get("name") != label or
            plan.get("parameter_prefix") != ns or
            plan.get("ownership", {}).get("schema") != "geomwright.managed_gear_spur"):
        raise ValueError("Invalid namespaced gear family plan")
    if not _input_matches(original["parameters"], plan["profile_request"]):
        raise ValueError("Gear request differs from chain recipe")
    g, v = plan["geometry"], plan["verification"]
    root, radius, width = [_number(g[k]) for k in ("root_radius", "outside_radius", "face_width")]
    count = g["tooth_count"]
    if not 0 < root < radius or width <= 0 or isinstance(count, bool) or int(count) != count or not 6 <= count <= 400:
        raise ValueError("Invalid gear dimensions/count")
    _close(width, plan["profile_request"]["face_width_mm"])
    _close(count, plan["profile_request"]["tooth_count"])
    _close(g["helix_angle_deg"], plan["profile_request"].get("helix_angle_deg", 0))
    if g["hand"] != plan["profile_request"].get("hand", "right"):
        raise ValueError("Gear hand differs from request")
    section = step["section"]
    core = min(root, radius - _number(g["tip_chamfer_depth_mm"]))
    if section.get("carrier_role") != "solid_root_core" or len(section["segments"]) != 1:
        raise ValueError("Gear requires a single solid root core")
    for actual, expected in ((section["start_mm"], -width), (section["end_mm"], 0),
            (section["root_radius_mm"], root), (section["bounding_radius_mm"], radius),
            (section["segments"][0]["start_radius_mm"], core), (section["segments"][0]["end_radius_mm"], core)):
        _close(actual, expected)
    operations = plan["workflow"]["params"]["operations"]
    chamfer = g["tip_chamfer_mm"] > 0
    ids = ["blank"] + (["tip_chamfer_face_a", "tip_chamfer_face_b"] if chamfer else []) + [
        "tooth_space_sketch", "tooth_space_cut", "tooth_space_pattern"]
    scenarios = ["cylindrical_blank"] + (["rotational_cut"]*2 if chamfer else []) + [
        "numeric_profile_sketch", "helical_cut_evolution" if g["helix_angle_deg"] > 1e-9 else "cut_extrusion", "circular_pattern"]
    if [op.get("id") for op in operations] != ids or [op.get("scenario") for op in operations] != scenarios:
        raise ValueError("Only prepared gear family operations are supported")
    suffixes = [" blank"] + ([" tip chamfer A", " tip chamfer B"] if chamfer else []) + [
        " one tooth space", " one tooth space cut", " tooth space pattern"]
    for op, suffix in zip(operations, suffixes):
        if op.get("bindings") or op.get("placement") or op["params"].get("name") != label + suffix:
            raise ValueError("Gear operation identity/bindings differ")
        # No source recreation, arbitrary supports or extra executor parameters.
        allowed = {
            "cylindrical_blank": {"name", "sketch_name", "outside_diameter", "width", "plane", "axis", "parameterize", "require_fully_defined"},
            "rotational_cut": {"name", "plane", "axis", "profile_points", "angle_degrees", "require_fully_defined"},
            "numeric_profile_sketch": {"name", "plane", "entities", "parameterize", "require_fully_defined", "profile_status"},
            "cut_extrusion": {"name", "sketch", "direction", "end_condition", "require_fully_defined"},
            "helical_cut_evolution": {"name", "sketch", "axis", "reference_diameter", "anchor_radius_mm", "lead", "height", "hand", "start_x", "start_angle_deg", "building_direction", "require_fully_defined"},
            "circular_pattern": {"name", "source", "axis", "count", "span_angle", "parameterize"},
        }[op["scenario"]]
        if set(op["params"]) - allowed or set(op) - {"id", "scenario", "params"}:
            raise ValueError("Unsupported gear workflow fields")
    blank, profile, cut, pattern = operations[0]["params"], operations[-3]["params"], operations[-2]["params"], operations[-1]["params"]
    if blank["plane"] != "YOZ" or blank["axis"] != "x_axis" or blank["sketch_name"] != label + " blank sketch":
        raise ValueError("Invalid gear blank frame")
    _close(blank["outside_diameter"], 2*radius)
    _close(blank["width"], width)
    if blank.get("parameterize") is not False or blank.get("require_fully_defined") is not False or pattern.get("parameterize") is not False:
        raise ValueError("Prepared numeric family mode must be preserved")
    if profile["plane"] != "YOZ" or profile.get("parameterize") is not False or cut["sketch"] != "tooth_space_sketch.sketch":
        raise ValueError("Invalid numeric gear profile source")
    entities = profile["entities"]
    if len(entities) != 7 or [e["kind"] for e in entities] != ["nurbs", "nurbs", "segment", "arc", "segment", "nurbs", "nurbs"]:
        raise ValueError("Unsupported gear numeric contour")
    if [e.get("id") for e in entities] != ["gear_space_root_right", "gear_space_involute_right", "gear_space_cap_out",
            "gear_space_cap_arc", "gear_space_cap_in", "gear_space_involute_left", "gear_space_root_left"]:
        raise ValueError("Gear contour entity IDs must remain family-local")
    for e in entities:
        allowed = {"nurbs": {"id", "kind", "points", "weights", "knots", "degree", "order", "closed", "style"},
                   "arc": {"id", "kind", "center", "radius", "start", "end", "direction", "style"},
                   "segment": {"id", "kind", "start", "end", "style"}}[e["kind"]]
        if set(e) - allowed or e.get("style") != 1:
            raise ValueError("Unsupported gear contour entity fields/style")
        points = e.get("points", [e.get("start"), e.get("end")])
        if not 2 <= len(points) <= 128 or any(len(p) != 2 for p in points):
            raise ValueError("Unbounded gear profile")
        for p in points:
            for n in p:
                _number(n)
        if e["kind"] == "nurbs" and (e.get("degree") != 3 or e.get("order") != 4 or e.get("closed") is not False):
            raise ValueError("Gear requires open cubic spline entities (degree 3)")
    if _hash(entities) != step["verification"]["profile_entities_sha256"]:
        raise ValueError("Gear numeric profile signature differs")
    for right, left in ((entities[0], entities[6]), (entities[1], entities[5])):
        mirrored = [[-p[0], p[1]] for p in reversed(right["points"])]
        if len(mirrored) != len(left["points"]) or any(math.dist(a, c) > LENGTH_TOL for a, c in zip(mirrored, left["points"])):
            raise ValueError("Gear numeric flanks must retain family mirror symmetry")
    _close(math.hypot(*entities[0]["points"][0]), root)
    _close(math.hypot(*entities[1]["points"][-1]), radius)
    _close(_profile_disk_area(entities, radius, root), g["clipped_gap_area_mm2"], 1e-4, .002)
    if cut["require_fully_defined"] is not False:
        raise ValueError("Gear numeric tooth exception must remain local")
    if scenarios[-2] == "cut_extrusion":
        if cut["direction"] != "both" or cut["end_condition"] != "through_all":
            raise ValueError("Gear cut direction differs")
    else:
        for key, expected in (("reference_diameter", 2*g["pitch_radius"]), ("lead", g["lead_mm"]),
                ("height", width), ("anchor_radius_mm", 0), ("start_x", 0), ("start_angle_deg", 0)):
            _close(cut[key], expected)
        if cut["axis"] != "blank.axis" or cut["hand"] != g["hand"] or cut["building_direction"] is not False:
            raise ValueError("Invalid helical gear frame")
    if pattern["source"] != "tooth_space_cut.feature" or pattern["axis"] != "blank.axis":
        raise ValueError("Gear pattern has foreign supports")
    _close(pattern["count"], count)
    _close(pattern["span_angle"], 360)
    for op, face in zip(operations[1:-3], ("a", "b")):
        p = op["params"]
        expected = ([[-width, radius-g["tip_chamfer_depth_mm"]], [-width+g["tip_chamfer_mm"], radius], [-width, radius]]
                    if face == "a" else [[0, radius-g["tip_chamfer_depth_mm"]], [-g["tip_chamfer_mm"], radius], [0, radius]])
        if p["plane"] != "XOY" or p["axis"] != "blank.axis" or p["profile_points"] != expected or p["angle_degrees"] != 360:
            raise ValueError("Gear chamfer plan differs")
    expected = (math.pi*radius**2-count*_number(g["clipped_gap_area_mm2"]))*width-g["tip_chamfer_volume_mm3"]
    if not math.pi*core**2*width <= expected <= math.pi*radius**2*width:
        raise ValueError("Gear expected volume outside root/blank bounds")
    _close(v["expected_volume_mm3"], expected, 1e-6, 1e-9)
    for key, target in (("max_radius_mm", radius), ("face_width_mm", width), ("pattern_count", count)):
        _close(v[key], target)
    if not 0 < _number(v["volume_relative_tolerance"]) <= .01 or not 0 < _number(v["bounds_tolerance_mm"]) <= .05:
        raise ValueError("Gear audit tolerance cannot be relaxed")
    if step["verification"].get("family_verification") != v:
        raise ValueError("Gear family verification differs")
    return expected/1000


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("Chain numbers must be finite")
    return float(value)


def _segments(section):
    result = section["segments"]
    if not isinstance(result, list) or not 1 <= len(result) <= 100:
        raise ValueError("Invalid chain section segment count")
    for s in result + section.get("inner_segments", []):
        lo, hi, a, c = [_number(s[k]) for k in
                        ("axial_min", "axial_max", "start_radius_mm", "end_radius_mm")]
        if hi <= lo or min(a, c) <= 0:
            raise ValueError("Invalid chain section span/radius")
    return result


def _volume(segments):
    return math.fsum(math.pi * (s["axial_max"] - s["axial_min"]) *
                     (s["start_radius_mm"]**2 + s["start_radius_mm"]*s["end_radius_mm"] +
                      s["end_radius_mm"]**2) / 3000 for s in segments)


def _radius(s, x):
    return s["start_radius_mm"] + (s["end_radius_mm"] - s["start_radius_mm"]) * (
        x - s["axial_min"]) / (s["axial_max"] - s["axial_min"])


def _inner_radius(s, x):
    return _radius(dict(s, start_radius_mm=s.get("inner_start_radius_mm", 0),
                       end_radius_mm=s.get("inner_end_radius_mm", 0)), x)


def _close(actual, expected, floor=LENGTH_TOL, relative=0):
    if abs(_number(actual) - _number(expected)) > max(floor, abs(expected)*relative):
        raise RuntimeError("Chain readback differs: expected=%s actual=%s" % (expected, actual))


def _input_matches(original, normalized):
    # Legacy normalization adds resolved/index/name fields, but cannot change
    # independent inputs carried by the strict host recipe.
    if isinstance(original, dict):
        return isinstance(normalized, dict) and all(k in normalized and _input_matches(v, normalized[k])
                                                   for k, v in original.items())
    if isinstance(original, list):
        return isinstance(normalized, list) and len(original) == len(normalized) and all(
            _input_matches(a, c) for a, c in zip(original, normalized))
    return original == normalized


def _validate(plan):
    if "spline_prefix_plan" in plan:
        return _spline_runtime().validate_plan(sys.modules[__name__], plan)
    """Native semantic guard, not a second host planner or arbitrary workflow."""
    if any(step.get("module") in ("external_helical_thread", "internal_helical_thread") for step in plan.get("steps", [])):
        return _thread_runtime().validate_plan(sys.modules[__name__], plan)
    if plan.get("schema") != "geomwright.construction_chain.plan" or plan.get("version") != 1:
        raise ValueError("Construction chain plan version 1 required")
    recipe = plan["recipe"]
    if recipe.get("schema") != SCHEMA or recipe.get("version") != 1:
        raise ValueError("Invalid chain input recipe")
    steps = plan["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 32 or len(recipe["steps"]) != len(steps):
        raise ValueError("Invalid chain step count")
    ids, stock, removed, total = {}, [], [], 0.0
    allowed = {"create_sketch", "draw_axis", "draw_profile", "apply_constraints",
               "add_dimensions", "add_variables", "base_rotation", "cut_rotation"}
    for index, step in enumerate(steps):
        ident, module = step["id"], step["module"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", ident) or ident.upper() in ids or module not in LABELS:
            raise ValueError("Invalid/duplicate chain step identity")
        original = recipe["steps"][index]
        for key in ("id", "module", "material", "basis"):
            if original[key] != step[key]:
                raise ValueError("Plan differs from recipe: " + key)
        if original.get("target") != step.get("target"):
            raise ValueError("Plan target differs from recipe")
        gear = module in FOUNDATIONS
        prism = module in ("external_polygonal_step", "external_flat_step")
        holes = module == "bolt_circle_holes"
        own = module in ("stepped_shaft", "external_conical_step", "gear_spur", "straight_spline", "external_polygonal_step", "external_flat_step")
        if own:
            if step["basis"] != "own" or step["material"] != ("create" if index == 0 else "add") or step.get("target"):
                raise ValueError("Invalid constructor mode")
        elif index == 0 or step["basis"] != "input" or step["material"] != "remove" or str(step.get("target", "")).upper() not in ids:
            raise ValueError("Cut requires an earlier explicit carrier")
        if not own and ids[step["target"].upper()]["id"] != step["target"]:
            raise ValueError("Cut target must match exact earlier identity")
        placement = step["placement"]
        p0 = original.get("placement", {})
        ref = p0.get("reference")
        origin = _number(p0.get("offset_mm", 0))
        if ref:
            previous = ids.get(str(ref["step"]).upper())
            if previous is None or previous["id"] != ref["step"] or ref["anchor"] not in ("start", "end"):
                raise ValueError("Invalid earlier placement reference")
            origin += previous["section"][ref["anchor"] + "_mm"]
        elif index:
            raise ValueError("Subsequent step requires a placement reference")
        if p0.get("axis", "global_x") != "global_x" or p0.get("phase_degrees", 0) != 0 or placement["direction"] not in (-1, 1):
            raise ValueError("Only coaxial zero-phase placement is supported")
        _close(placement["origin_mm"], origin)
        if placement["direction"] != p0.get("direction", 1):
            raise ValueError("Plan direction differs from recipe")
        if gear and (index or ref or origin != 0 or placement["direction"] != 1):
            raise ValueError("Gear is only an initial identity-placement foundation")
        section = step["section"]
        segments = _segments(section)
        if section.get("axis") != "global_x" or section.get("phase_degrees") != 0 or section.get("shape") != module or section.get("material_role") != ("stock" if own else "removed"):
            raise ValueError("Invalid section semantics")
        inner = section.get("inner_segments", [])
        if bool(inner) != (module in ("face_ring_groove", "bolt_circle_holes")) or (inner and (len(inner) != 1 or len(segments) != 1)):
            raise ValueError("Invalid cutter inner section")
        lo, hi = section["axial_interval_mm"]
        _close(lo, min(s["axial_min"] for s in segments))
        _close(hi, max(s["axial_max"] for s in segments))
        if not gear:
            _close(section["start_mm"], origin)
            _close(section["end_mm"], origin + placement["direction"]*(hi-lo))
        if own and stock and steps[0]["module"] in FOUNDATIONS and (
                module != "stepped_shaft" or placement["direction"] != 1 or
                origin != max(s["axial_max"] for s in stock)):
            raise ValueError("Gear hubs must attach at exposed +X end")
        if own and stock and steps[0]["module"] == "straight_spline" and origin == 0 and max(
                max(s["start_radius_mm"], s["end_radius_mm"]) for s in segments) > steps[0]["section"]["segments"][0]["end_radius_mm"]:
            raise ValueError("Spline joining section exceeds solid core")
        if own and stock and not (abs(hi-min(s["axial_min"] for s in stock)) <= LENGTH_TOL or
                                  abs(lo-max(s["axial_max"] for s in stock)) <= LENGTH_TOL):
            raise ValueError("Addition must attach without overlap")
        if own and any(s["axial_min"] <= origin <= s["axial_max"] for s in removed):
            raise ValueError("Addition onto a processed face is unsupported")
        if not own:
            carrier = ids[step["target"].upper()]
            if carrier["material"] not in ("create", "add"):
                raise ValueError("Cut target is not stock")
            a, c = carrier["section"]["axial_interval_mm"]
            if lo < a-LENGTH_TOL or hi > c+LENGTH_TOL:
                raise ValueError("Cut extends beyond carrier")
            if inner:
                if not holes and min(abs(origin-a), abs(origin-c)) > LENGTH_TOL:
                    raise ValueError("Face groove must start at carrier end")
                for x in (lo, hi):
                    _close(inner[0]["axial_min"], lo)
                    _close(inner[0]["axial_max"], hi)
                    if _radius(inner[0], x) >= _radius(segments[0], x):
                        raise ValueError("Face groove walls cross")
            regions = [dict(s, inner_start_radius_mm=inner[i]["start_radius_mm"] if inner else 0,
                inner_end_radius_mm=inner[i]["end_radius_mm"] if inner else 0) for i, s in enumerate(segments)]
            for prior in removed:
                for cutter in regions:
                    x, y = max(prior["axial_min"], cutter["axial_min"]), min(prior["axial_max"], cutter["axial_max"])
                    if y > x and not (all(_inner_radius(cutter, t) > _radius(prior, t) for t in (x, y)) or
                            all(_inner_radius(prior, t) > _radius(cutter, t) for t in (x, y))):
                        raise ValueError("Cut overlaps earlier removed material")
            for cutter in segments:
                for s in carrier["section"]["segments"]:
                    x, y = max(s["axial_min"], cutter["axial_min"]), min(s["axial_max"], cutter["axial_max"])
                    if y > x and any(_radius(cutter, t) >= _radius(s, t) for t in (x, y)):
                        raise ValueError("Cut exceeds carrier radius")
            removed.extend(regions)
        else:
            stock.extend(segments)
        delta = _volume(segments)-_volume(section.get("inner_segments", []))
        if prism:
            delta = _prism_runtime().guard(step, original, _close)
        if holes:
            delta = _holes_runtime().guard(step, original, _close)
        if gear:
            if step["namespace"] != "CH_" + ident.upper():
                raise ValueError("Invalid gear namespace")
            delta = _spline_guard(step, original) if module == "straight_spline" else _gear_guard(step, original)
        delta *= 1 if own else -1
        total += delta
        if total <= 0 or delta == 0:
            raise ValueError("Chain must retain positive material")
        _close(step["expected_delta_cm3"], delta, VOLUME_FLOOR, 1e-9)
        _close(step["expected_total_volume_cm3"], total, VOLUME_FLOOR, 1e-9)
        if gear or prism or holes:
            ids[ident.upper()] = step
            continue
        preview, namespace = step["preview"], "CH_" + ident.upper()
        params = preview["params"]
        for key, value in original["parameters"].items():
            if not _input_matches(value, params.get(key)):
                raise ValueError("Normalized preview differs from recipe parameters: " + key)
        label = LABELS[module] + " [" + ident + "]"
        if preview["scenario"] != module or step["namespace"] != namespace or params.get("parameter_prefix") != namespace or params.get("name") != label or params.get("sketch_name") != label + " profile":
            raise ValueError("Invalid preview identity")
        if any(k in params for k in ("source_scenario", "source_params", "source_preview")) or params.get("projections"):
            raise ValueError("Source recreation/projection is forbidden in chains")
        if params.get("plane", "XOY") != "XOY" or params.get("angle_degrees", 360) != 360:
            raise ValueError("Only full XOY rotation supported")
        if params.get("rotation_axis_default_object_type", 71) != 71:
            raise ValueError("Unsupported rotation axis")
        operations = preview["operations"]
        kinds = [op["operation"] for op in operations]
        if any(k not in allowed for k in kinds) or len(set(kinds)) != len(kinds) or kinds.count("draw_profile") != 1 or kinds.count("draw_axis") != 1 or kinds.count("cut_rotation" if not own else "base_rotation") != 1 or ("base_rotation" if not own else "cut_rotation") in kinds:
            raise ValueError("Unsupported chain preview operations")
        draw = next(op for op in operations if op["operation"] == "draw_profile")
        if draw.get("profile_entities") or draw.get("construction_lines"):
            raise ValueError("Only the transformed linear chain profile is supported")
        points = draw["profile_points"]
        if not 4 <= len(points) <= 512:
            raise ValueError("Unbounded chain profile")
        for x, y in points:
            _number(x)
            _number(y)
        _close(min(p[0] for p in points), lo)
        _close(max(p[0] for p in points), hi)
        _close(max(p[1] for p in points), max(max(s["start_radius_mm"], s["end_radius_mm"]) for s in segments))
        if min(p[1] for p in points) < 0:
            raise ValueError("Chain profile must lie on positive radial half-plane")
        # First area moment about X gives the solid-of-revolution volume, even
        # for a groove away from the axis. Reject inconsistent supplied previews.
        moment = math.fsum((a[1]+c[1])*(a[0]*c[1]-c[0]*a[1])
                           for a, c in zip(points, points[1:]+points[:1])) / 6
        _close(abs(2*math.pi*moment/1000), abs(delta), VOLUME_FLOOR, 1e-9)
        axis = next(op for op in operations if op["operation"] == "draw_axis")
        for point, x in ((axis["start"], origin), (axis["end"], section["end_mm"])):
            _close(point[0], x)
            _close(point[1], 0)
        for op in operations:
            for var in op.get("variables", []):
                if not str(var["name"]).startswith(namespace + "_"):
                    raise ValueError("Variable escapes chain namespace")
                _number(var["value"])
            for item in op.get("variables", []) + op.get("dimensions", []):
                expression = item.get("expression")
                # Exponents in ordinary numeric literals are not identifiers.
                expression = re.sub(r"\b\d+(?:\.\d*)?[eE][+-]?\d+\b", "0", str(expression)) if expression is not None else None
                if expression is not None and any(not token.startswith(namespace + "_") and token not in
                        ("sin", "cos", "tan", "atan", "sqrt", "abs", "pi")
                        for token in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", str(expression))):
                    raise ValueError("Expression escapes chain namespace")
        ids[ident.upper()] = step
    _close(plan["expected_total_volume_cm3"], total, VOLUME_FLOOR, 1e-9)
    if plan.get("expected_body_count") != 1:
        raise ValueError("Chain requires one final body")
    # Existing checksum helper owns the envelope limit; reject before creating CAD.
    _bounded({"schema": SCHEMA, "version": 1, "recipe": recipe,
              "expectations": _expectations(steps), "outputs": []})
    return steps


def _bounded(value):
    if len(json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))) > 24000:
        raise ValueError("Chain persistence envelope exceeds 24000 characters")


def _expectations(steps):
    return [{k: deepcopy(s[k]) for k in ("id", "module", "namespace", "material", "basis", "target",
            "placement", "section", "expected_delta_cm3", "expected_total_volume_cm3", "verification")} for s in steps]


def _point_result(value):
    if not isinstance(value, tuple) or len(value) != 4 or not value[0]:
        raise RuntimeError("Native geometry point unavailable")
    return [_number(v) for v in value[1:]]


def _normalized(value):
    # Hash comparison uses a fixed native readback quantization, not COM refs.
    if isinstance(value, (tuple, list)):
        return [_normalized(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalized(v) for k, v in value.items()}
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        result = round(_number(value), 6)
        return 0.0 if result == 0 else result
    return value


def _tooth_face(b, face, edges, points, gear):
    """Trimmed outer lateral faces only; planar end bores/hubs may intersect ends."""
    if b.safe_get(face, "IsPlanar", False):
        # Only constant-X end planes are excluded, not planar lateral tooth walls.
        if max(p[0] for p in points)-min(p[0] for p in points) <= LENGTH_TOL:
            return None
    lo, hi = gear["section"]["axial_interval_mm"]
    root = gear["section"]["root_radius_mm"]
    face_lo, face_hi = min(p[0] for p in points), max(p[0] for p in points)
    if min(face_hi, hi)-max(face_lo, lo) <= LENGTH_TOL:
        return None
    if max(math.hypot(p[1], p[2]) for p in points) <= root+LENGTH_TOL:
        return None
    if min(p[0] for p in points) < lo-LENGTH_TOL or max(p[0] for p in points) > hi+LENGTH_TOL:
        raise RuntimeError("Tooth zone unexpectedly merged into downstream geometry")
    curves = []
    for edge in edges:
        curve = b._cast_to_com_interface(b.safe_get(edge, "MathCurve"), "IMathCurve3D")
        t0, t1 = _number(curve.ParamMin), _number(curve.ParamMax)
        samples = [_point_result(curve.GetPoint(t0+(t1-t0)*i/8)) for i in range(9)]
        start, end = _point_result(edge.GetPoint(True)), _point_result(edge.GetPoint(False))
        if min(max(math.dist(samples[0], start), math.dist(samples[-1], end)),
               max(math.dist(samples[0], end), math.dist(samples[-1], start))) > LENGTH_TOL:
            raise RuntimeError("Tooth edge samples do not cover trimmed domain")
        forward, reverse = _normalized(samples), _normalized(list(reversed(samples)))
        curve_type = b.safe_get(edge, "Curve3DType")
        if curve_type is None:
            raise RuntimeError("Tooth edge native type unavailable")
        curves.append({"type": curve_type, "length": _number(edge.GetLength(1)),
                       "samples": min(forward, reverse)})
    surface = b._cast_to_com_interface(b.safe_get(face, "MathSurface"), "IMathSurface3D")
    u0, u1, v0, v1 = [_number(b.safe_get(surface, key)) for key in
                       ("ParamUMin", "ParamUMax", "ParamVMin", "ParamVMax")]
    samples = [_point_result(surface.GetPoint(u0+(u1-u0)*u, v0+(v1-v0)*v))
               for u in (.17, .5, .83) for v in (.17, .5, .83)]
    surface_type = b.safe_get(face, "Surface3DType")
    if surface_type is None:
        raise RuntimeError("Tooth face native type unavailable")
    return _normalized({"type": surface_type,
        "area": _number(face.GetArea(1)),
        "boundary_bounds": [min(p[i] for p in points) for i in range(3)] + [max(p[i] for p in points) for i in range(3)],
        "curves": sorted(curves, key=lambda row: json.dumps(_normalized(row), sort_keys=True)),
        "surface_samples": sorted(samples)})


def _cylinder_frame(b, face):
    # READ-001: derive centres/axis from native radial normals, not Placement.
    import importlib.util
    global _GEOMETRY_RUNTIME
    if _GEOMETRY_RUNTIME is None:
        spec = importlib.util.spec_from_file_location("chain_body_geometry", os.path.join(os.path.dirname(__file__), "body_geometry_runtime.py"))
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        _GEOMETRY_RUNTIME = runtime
    surface = b._cast_to_com_interface(b.safe_get(face, "MathSurface"), "IMathSurface3D")
    return _GEOMETRY_RUNTIME.evaluated_frame(surface, "cylinder", _number(b.safe_get(face, "Radius")))


def _coaxial_surface(b, face, cylinder, radii):
    surface = b._cast_to_com_interface(b.safe_get(face, "MathSurface"), "IMathSurface3D")
    if cylinder:
        radius = _number(b.safe_get(face, "Radius"))
        frame = _cylinder_frame(b, face)
        axis, origin = frame["z_axis"], frame["origin_mm"]
        if abs(abs(axis[0])-1) > LENGTH_TOL or math.hypot(origin[1], origin[2]) > LENGTH_TOL:
            return False
        return all(abs(r-radius) <= LENGTH_TOL for r in radii)
    # Cone derivative-U is circumferential; its tangent must be perpendicular to
    # global X and the global radial vector at two noncoincident native samples.
    for fraction in (.23, .67):
        u = surface.ParamUMin+(surface.ParamUMax-surface.ParamUMin)*fraction
        v = (surface.ParamVMin+surface.ParamVMax)/2
        p = _point_result(surface.GetPoint(u, v))
        d = _point_result(surface.GetDerivativeU(u, v))
        norm = math.sqrt(sum(x*x for x in d))
        if norm <= 0 or abs(d[0])/norm > LENGTH_TOL or abs(p[1]*d[1]+p[2]*d[2])/norm > LENGTH_TOL:
            return False
    return True


def _exact_document_body_metrics(b, app, doc):
    """API5 mass properties are active-document based, unlike pinned API7 bodies."""
    ident = b.describe_runtime_document(doc, app).get("runtime_id")
    if not ident:
        raise RuntimeError("Mass readback requires an exact chain document identity")

    def is_active():
        active = b.safe_get(app, "ActiveDocument")
        return active is not None and b.describe_runtime_document(active, app).get("runtime_id") == ident

    if not is_active():
        b._cast_to_com_interface(doc, "IKompasDocument").Active = True
    if not is_active():
        raise RuntimeError("Mass readback requires exact active chain document")
    metrics = b._active_api5_primary_body_metrics()
    if not is_active():
        raise RuntimeError("Active chain document changed during mass readback; discard snapshot")
    return metrics


def _read_body(b, app, doc, part, gear=None):
    # Never retain feature.ResultBodies across a rebuild/boolean operation.
    bodies = b._ensure_dispatch_sequence(b.safe_get(b._cast_to_com_interface(part, "IFeature7"), "ResultBodies"))
    if len(bodies) != 1:
        raise RuntimeError("Chain requires exactly one current final body")
    body = b._cast_to_com_interface(bodies[0], "IBody7")
    if not bool(b.safe_get(body, "IsSolid", False)):
        raise RuntimeError("Chain final body is not solid")
    bounds = body.GetGabarit()
    if not isinstance(bounds, tuple) or len(bounds) != 7 or not bounds[0]:
        raise RuntimeError("Final body bounds unavailable")
    bounds = [_number(v) for v in bounds[1:]]
    metrics = _exact_document_body_metrics(b, app, doc)
    if metrics["body_count"] != 1 or not metrics["solid"] or _number(metrics["volume"]) <= 0:
        raise RuntimeError("Native mass readback requires one positive solid")
    faces, teeth, lateral_planes, hole_faces = [], [], [], []
    objects = b._ensure_dispatch_sequence(b._cast_to_com_interface(body, "IFeature7").ModelObjects(6))
    if len(objects) > (20000 if gear else 1024):
        raise RuntimeError("Final face readback budget exceeded")
    for obj in objects:
        face = b._cast_to_com_interface(obj, "IFace")
        cylinder = bool(b.safe_get(face, "IsCylinder", False))
        cone = bool(b.safe_get(face, "IsCone", False))
        if bool(b.safe_get(face, "IsPlanar", False)):
            surface = b._cast_to_com_interface(b.safe_get(face, "MathSurface"), "IMathSurface3D")
            u = (_number(surface.ParamUMin) + _number(surface.ParamUMax)) / 2
            v = (_number(surface.ParamVMin) + _number(surface.ParamVMax)) / 2
            normal = _point_result(surface.GetNormal(u, v))
            # Axial end planes may have hundreds of tooth boundary edges. They
            # are outside the preserved lateral tooth zone and carrier walls.
            if abs(normal[0]) > 1e-9 and math.hypot(normal[1], normal[2]) <= abs(normal[0])*1e-9:
                continue
        planar = bool(b.safe_get(face, "IsPlanar", False))
        if not cylinder and not cone and not gear and not planar:
            if not bool(b.safe_get(face, "IsPlanar", False)):
                raise RuntimeError("Unexpected final surface in coaxial chain")
            continue
        points = []
        edges = b._ensure_dispatch_sequence(b.safe_get(face, "LimitingEdges"))
        if len(edges) > 128:
            raise RuntimeError("Final face boundary budget exceeded")
        for edge in edges:
            for endpoint in (True, False):
                p = edge.GetPoint(endpoint)
                if not isinstance(p, tuple) or len(p) < 4 or not p[0]:
                    raise RuntimeError("Final trimmed boundary unavailable")
                points.append([_number(v) for v in p[1:4]])
        if not points:
            raise RuntimeError("Empty final trimmed boundary")
        if planar and not gear:
            magnitude = math.sqrt(sum(n*n for n in normal))
            if magnitude <= 0:
                raise RuntimeError("Degenerate polygon plane normal")
            normal = [n/magnitude for n in normal]
            if abs(normal[0]) > 1e-7:
                raise RuntimeError("Unsupported nonaxial polygon side plane")
            h = sum(n*p for n, p in zip(normal, points[0]))
            if h < 0:
                normal, h = [-n for n in normal], -h
            for point in points:
                _close(sum(n*p for n, p in zip(normal, point)), h)
            lateral_planes.append({"normal_yz": normal[1:], "offset_mm": h,
                "axial_min": min(p[0] for p in points), "axial_max": max(p[0] for p in points)})
        if gear:
            descriptor = _tooth_face(b, face, edges, points, gear)
            if descriptor is not None:
                teeth.append(descriptor)
        if not cylinder and not cone:
            continue
        lo, hi = min(p[0] for p in points), max(p[0] for p in points)
        if hi-lo <= LENGTH_TOL:
            if gear:
                continue
            raise RuntimeError("Degenerate final radial surface span")
        if cylinder and (not gear or descriptor is None):
            radius = _number(b.safe_get(face, "Radius"))
            # Reuse the shared evaluated frame, not MathSurface.Placement (READ-001).
            frame = _cylinder_frame(b, face)
            if abs(abs(frame["z_axis"][0])-1) <= 1e-7 and math.hypot(*frame["origin_mm"][1:]) > LENGTH_TOL:
                center = frame["origin_mm"][1:]
                for point in points:
                    _close(math.hypot(point[1]-center[0], point[2]-center[1]), radius)
                hole_faces.append({"center_yz_mm": center, "radius_mm": radius, "axial_min": lo, "axial_max": hi})
                continue
        radii = []
        for x in (lo, hi):
            values = [math.hypot(p[1], p[2]) for p in points if abs(p[0]-x) <= LENGTH_TOL]
            if not values:
                raise RuntimeError("Radial surface trimmed end is missing")
            if gear and max(values)-min(values) > LENGTH_TOL:
                break
            _close(min(values), max(values))
            radii.append(values[0])
        if gear and (len(radii) != 2 or not _coaxial_surface(b, face, cylinder, radii)):
            continue
        if cylinder:
            radius = _number(b.safe_get(face, "Radius"))
            for r in radii:
                _close(r, radius)
        faces.append({"reference": b.safe_get(face, "Reference"), "surface_type": "cylinder" if cylinder else "cone",
                      "axial_min": lo, "axial_max": hi, "start_radius_mm": radii[0], "end_radius_mm": radii[1]})
    if not faces and not lateral_planes or len(faces) > (5000 if gear else 256):
        raise RuntimeError("Unsupported final radial topology count")
    result = {"reference": b.safe_get(body, "Reference"), "body_count": 1, "solid": True,
              "volume_cm3": metrics["volume"], "bounds_mm": bounds, "faces": faces,
              "lateral_planes": lateral_planes}
    result["hole_faces"] = hole_faces
    if gear:
        if not teeth:
            raise RuntimeError("No actual outer tooth surfaces read back")
        result["tooth_zone"] = {"face_count": len(teeth), "sha256": _hash(sorted(teeth, key=lambda row: json.dumps(row, sort_keys=True))),
            "representation": "native_trimmed_edges_9_samples_surface_3x3_quantized_1e-6", "sampled": True}
    return result


def _match_sections(body, segments):
    """Coverage tolerates native merging of adjacent equal-radius faces (READ-001)."""
    for s in segments:
        intervals = []
        for f in body["faces"]:
            a, c = max(s["axial_min"], f["axial_min"]), min(s["axial_max"], f["axial_max"])
            if c > a and all(abs(_radius(s, x)-_radius(f, x)) <= LENGTH_TOL for x in (a, c)):
                intervals.append((a, c))
        cursor = s["axial_min"]
        for a, c in sorted(intervals):
            if a > cursor + LENGTH_TOL:
                break
            cursor = max(cursor, c)
        if cursor < s["axial_max"] - LENGTH_TOL:
            raise RuntimeError("Actual final section radius/span does not match carrier/plan: " + str(s))


def _verify(body, steps, previous_volume=None):
    gear = _foundation(steps)
    audit = gear["verification"].get("foundation_audit") if gear else None
    if gear and not audit:
        raise RuntimeError("Family foundation audit is required before composite verification")
    stock = [s for step in steps if step["material"] != "remove" for s in step["section"]["segments"]]
    expected = [s for step in steps if step is not gear and step["module"] not in ("external_polygonal_step", "external_flat_step", "bolt_circle_holes") for s in step["section"]["segments"] + step["section"].get("inner_segments", [])]
    expected += [dict(step["section"]["segments"][0], start_radius_mm=step["section"]["bounding_radius_mm"], end_radius_mm=step["section"]["bounding_radius_mm"])
                 for step in steps if step["module"] == "external_flat_step"]
    if not gear:
        _prism_runtime().verify(body, steps, LENGTH_TOL)
    _holes_runtime().verify(body, steps, LENGTH_TOL)
    _match_sections(body, expected)
    # No unexpected radial wall is allowed either; old roots are not final geometry.
    if not gear:
        _match_sections({"faces": expected}, body["faces"])
    else:
        core = gear["section"]["segments"][0]
        # Root/chamfer surfaces are part of the audited gear, not a cylindrical
        # approximation of its teeth. All later coaxial walls remain strict.
        extras = [f for f in body["faces"] if not (
            f["axial_min"] >= core["axial_min"]-LENGTH_TOL and f["axial_max"] <= core["axial_max"]+LENGTH_TOL and
            min(f["start_radius_mm"], f["end_radius_mm"]) >= core["start_radius_mm"]-LENGTH_TOL)]
        _match_sections({"faces": expected}, extras)
        if body.get("tooth_zone") != audit["tooth_zone"]:
            raise RuntimeError("Actual outer tooth zone changed after foundation audit")
    radius = max(step["section"].get("bounding_radius_mm", max(max(s["start_radius_mm"], s["end_radius_mm"])
        for s in step["section"]["segments"])) for step in steps if step["material"] != "remove")
    bounds = [min(s["axial_min"] for s in stock), -radius, -radius,
               max(s["axial_max"] for s in stock), radius, radius]
    if any(step["module"] in ("external_polygonal_step", "external_flat_step") for step in steps):
        y0, z0, y1, z1 = _prism_runtime().bounds(steps)
        bounds = [bounds[0], y0, z0, bounds[3], y1, z1]
    for i, (actual, target) in enumerate(zip(body["bounds_mm"], bounds)):
        if gear and i in (1, 2, 4, 5):
            # Odd-z native bounds need not touch the conservative radial envelope.
            native = audit["bounds_mm"][i]
            added_radius = max([0] + [max(s["start_radius_mm"], s["end_radius_mm"])
                for step in steps[1:] if step["material"] != "remove" for s in step["section"]["segments"]])
            target = min(native, -added_radius) if i < 3 else max(native, added_radius)
        _close(actual, target)
    total = steps[-1]["expected_total_volume_cm3"]
    if gear:
        total = audit["volume_cm3"] + math.fsum(s["expected_delta_cm3"] for s in steps[1:])
    _close(body["volume_cm3"], total, TOTAL_VOLUME_FLOOR, TOTAL_VOLUME_REL)
    delta = None if previous_volume is None else body["volume_cm3"]-previous_volume
    if delta is not None and (not gear or len(steps) > 1):
        if delta*steps[-1]["expected_delta_cm3"] <= 0:
            raise RuntimeError("Chain operation did not change material in the required direction")
        _close(delta, steps[-1]["expected_delta_cm3"], VOLUME_FLOOR, VOLUME_REL)
    return {"ok": True, "verified": True, "fresh_geometry_audit": True,
            "single_solid": True, "bounds_verified": True, "sections_verified": True,
            "volume_cm3": body["volume_cm3"], "delta_cm3": delta,
            "volume_relative_tolerance": TOTAL_VOLUME_REL, "delta_relative_tolerance": VOLUME_REL,
            "length_tolerance_mm": LENGTH_TOL, "mass_readback_channel": "native_api5_active_body",
            "expected_total_volume_cm3": total,
            "tooth_zone_preserved": True if gear else None}


def _profile_geometry(kind, geometry, planned=False):
    keys = {"circle": ("center", "radius"), "segment": ("start", "end"), "arc": ("start", "end", "center", "radius", "direction"),
            "nurbs": ("points", "weights", "knots", "degree", "closed")}[kind]
    result = {key: deepcopy(geometry[key]) for key in keys}
    if kind == "nurbs":
        if planned:
            result["degree"] = geometry["order"]
        knots = result["knots"]
        lo, span = _number(knots[0]), _number(knots[-1])-_number(knots[0])
        if span <= 0:
            raise RuntimeError("Native numeric profile knot domain is degenerate")
        result["knots"] = [(_number(k)-lo)/span for k in knots]
    return {"kind": kind, "geometry": _normalized(result)}


def _profile_readback(b, model, reference, expected=None, entity_count=7):
    read = b._inspect_sketch_full(model, {"sketch_ref": reference, "max_items": 32,
        "update_before_state": False, "include_dimensions": False, "include_constraints": False,
        "include_diagnostics": False})
    rows = read.get("entities", [])
    if len(rows) != entity_count or any(not row.get("geometry") or row["kind"] not in ("segment", "arc", "nurbs") for row in rows):
        raise RuntimeError("Actual tooth profile must retain every readable numeric entity")
    actual = sorted([_profile_geometry(row["kind"], row["geometry"]) for row in rows], key=lambda row: json.dumps(row, sort_keys=True))
    if expected is not None:
        planned = sorted([_profile_geometry(row["kind"], row, planned=True) for row in expected], key=lambda row: json.dumps(row, sort_keys=True))
        if actual != planned:
            raise RuntimeError("Actual numeric gear profile differs from prepared family geometry")
    return {"entity_count": len(actual), "sha256": _hash(actual), "readback": "inspect_sketch_full_numeric_geometry"}


def _blank_readback(b, model, reference, radius=None):
    read = b._inspect_sketch_full(model, {"sketch_ref": reference, "max_items": 32,
        "update_before_state": False, "include_dimensions": False, "include_constraints": False, "include_diagnostics": False})
    rows = read.get("entities", [])
    if len(rows) != 1 or rows[0]["kind"] != "circle":
        raise RuntimeError("Actual gear blank must retain one numeric circle")
    geometry = _profile_geometry("circle", rows[0]["geometry"])
    if radius is not None and geometry != _profile_geometry("circle", {"center": [0, 0], "radius": radius}):
        raise RuntimeError("Actual blank circle differs from gear family plan")
    return {"entity_count": 1, "sha256": _hash(geometry)}


def _root_readback(b, obj):
    kind = b.safe_get(b._cast_to_com_interface(obj, "IModelObject"), "Type")
    if kind is None:
        raise RuntimeError("Gear root native type unavailable")
    variables = [{"name": b.safe_get(v, "Name"), "note": b.safe_get(v, "ParameterNote"),
                  "value": _number(b.safe_get(v, "Value")), "expression": b.safe_get(v, "Expression")}
                 for v in b._iter_operation_variables(obj)]
    if len(variables) > 64:
        raise RuntimeError("Gear root variable readback budget exceeded")
    return {"type": kind, "variables_sha256": _hash(_normalized(sorted(variables, key=lambda row: json.dumps(row, sort_keys=True))))}


def _family_audit(b, doc, part, model, step, runtime, reports, body):
    # Same family acceptance used by the standalone wrapper; no family metadata
    # is installed into the composite part.
    plan = _family_plan(step)
    if step["module"] == "straight_spline":
        native = {"solid": body["solid"], "volume": body["volume_cm3"], "bounds_mm": body["bounds_mm"]}
        accepted = b._verify_straight_spline_metrics(plan, native, reports)
        error = accepted["relative_volume_error"]
        pattern = next(r for r in reports if r.get("id") == "tooth_space_pattern")
        radius = plan["geometry"]["outer_radius_mm"]
    else:
        native, error, pattern = b._verify_gear_spur_foundation(doc, part, plan, reports)
        radius = plan["geometry"]["outside_radius"]
    _close(native["volume"], body["volume_cm3"], TOTAL_VOLUME_FLOOR, TOTAL_VOLUME_REL)
    profile_op = next(op for op in plan["workflow"]["params"]["operations"] if op["id"] == "tooth_space_sketch")
    entities = profile_op["params"]["entities"]
    profile = _profile_readback(b, model, b.safe_get(runtime["tooth_space_sketch"]["sketch"], "Reference"), entities, len(entities))
    source = next(r for r in reports if r.get("id") == "tooth_space_cut")
    removed = _number(source["volume_removed"])
    expected = removed*(pattern["count"]-1)
    if removed <= 0 or expected <= 0:
        raise RuntimeError("Gear source cut removed no material")
    _close(pattern["additional_volume_removed"], expected, VOLUME_FLOOR, VOLUME_REL)
    blank = _blank_readback(b, model, b.safe_get(runtime["blank"]["sketch"], "Reference"), radius)
    roots = {key: _root_readback(b, entry["feature"]) for key, entry in runtime.items()
             if entry["scenario"] != "numeric_profile_sketch"}
    return {"verified": True, "volume_cm3": body["volume_cm3"], "bounds_mm": body["bounds_mm"],
        "relative_volume_error": error, "profile": profile, "blank_profile": blank, "roots": roots, "tooth_zone": body["tooth_zone"],
        "pattern_count": pattern["count"], "source_volume_removed_cm3": removed,
        "additional_volume_removed_cm3": pattern["additional_volume_removed"],
        "expected_additional_volume_removed_cm3": expected, "pattern_material_verified": True,
        "mass_readback_channel": "native_api5_active_body"}


def _ownership(b, model, outputs, strict_names=False, document=None):
    current = deepcopy(outputs)
    identity = b._cast_to_com_interface(document, "IKompasDocument1") if document is not None else None
    for out in current:
        owned = out.get("owned_objects") or [dict(out[key], collection=collection, require_fully_defined=key == "sketch")
            for key, collection in (("sketch", "Sketchs"), ("feature", "Rotateds"))]
        for saved in owned:
            collection = saved["collection"]
            old_reference = saved["reference"]
            if identity is not None and saved.get("object_id"):
                found = identity.FindObjectById(saved["object_id"], None)
                matches = [b._cast_to_com_interface(found, "IModelObject")] if found is not None else []
            else:
                matches = [obj for obj in b.iter_collection(_collection(b, model, collection))
                           if b.safe_get(obj, "Reference") == saved["reference"]]
            if len(matches) != 1:
                raise RuntimeError("Chain owned reference missing/ambiguous: " + out["id"] + "/" + collection)
            obj = matches[0]
            saved["reference"] = b.safe_get(obj, "Reference")
            if identity is not None:
                object_id = identity.GetObjectId(b._cast_to_com_interface(obj, "IKompasAPIObject"), None)
                if not isinstance(object_id, str) or not 1 <= len(object_id) <= 512:
                    raise RuntimeError("Native persistent object identity unavailable: " + out["id"])
                if saved.get("object_id") and object_id != saved["object_id"]:
                    raise RuntimeError("Native persistent object identity changed: " + out["id"])
                saved["object_id"] = object_id
            if collection in ("Sketchs", "Rotateds", "Extrusions", "Evolutions", "FeaturePatterns") and not bool(b.safe_get(b._cast_to_com_interface(obj, "IFeature7"), "Valid", False)):
                raise RuntimeError("Chain owned root invalid: " + out["id"])
            saved["current_name"] = b.safe_get(obj, "Name")
            for key in ("sketch", "feature"):
                if out[key]["reference"] == old_reference:
                    out[key]["current_name"] = saved["current_name"]
                    out[key]["reference"] = saved["reference"]
                    if saved.get("object_id"):
                        out[key]["object_id"] = saved["object_id"]
            if strict_names and saved["current_name"] != saved["name"]:
                raise RuntimeError("Chain canonical name readback differs: " + out["id"])
            if collection == "Sketchs":
                state = b._describe_constraints_state(b.safe_get(b._cast_to_com_interface(obj, "ISketch"), "ConstraintsState"))
                out["sketch_state"] = state
                if saved.get("require_fully_defined", True) and state.get("code") != b.KS_SKETCH_STATE_WELL_CONSTRAINED:
                    raise RuntimeError("Chain sketch is not fully defined: " + out["id"])
            if saved.get("role") == "first_center" and out.get("hole_pattern"):
                point = b._cast_to_com_interface(obj, "IPoint3D")
                if point.ParameterType != 1:
                    raise RuntimeError("Bolt-circle centre must use coordinate inputs, not displacement outputs")
                for variable in b._iter_operation_variables(point):
                    expression = b.safe_get(variable, "Expression")
                    if expression and bool(b.safe_get(variable, "Information", False)):
                        raise RuntimeError("Bolt-circle centre has a formula on an informational output")
                drivers = {b.safe_get(v, "ParameterNote"): v for v in b._iter_operation_variables(point)}
                for axis in ("Y", "Z"):
                    v = next((drivers[note] for note in ("Координата "+axis, "Coordinate "+axis) if note in drivers), None)
                    if v is None or out["namespace"]+"_PCD1" not in str(b.safe_get(v, "Expression") or "") or bool(b.safe_get(v, "Information", True)):
                        raise RuntimeError("Bolt-circle actual centre driver missing or informational")
            if saved.get("role") == "tooth_space_sketch.sketch" and out.get("foundation_audit"):
                if _profile_readback(b, model, saved["reference"], entity_count=out["foundation_audit"]["profile"]["entity_count"]) != out["foundation_audit"]["profile"]:
                    raise RuntimeError("Native gear profile changed: " + out["id"])
            if saved.get("role") == "blank.sketch" and out.get("foundation_audit"):
                if _blank_readback(b, model, saved["reference"]) != out["foundation_audit"]["blank_profile"]:
                    raise RuntimeError("Native gear blank profile changed")
            if saved.get("role", "").endswith(".feature") and out.get("foundation_audit"):
                role = saved["role"].split(".")[0]
                if _root_readback(b, obj) != out["foundation_audit"]["roots"][role]:
                    raise RuntimeError("Native gear operation parameters changed: " + role)
            if collection == "FeaturePatterns" and out.get("foundation_audit"):
                pattern = b._cast_to_com_interface(obj, "ICircularPattern")
                count = out["foundation_audit"]["pattern_count"]
                _close(b.safe_get(pattern, "Count2"), count)
                _close(b.safe_get(pattern, "Step2"), 360/count, 1e-7)
                sources = [b.safe_get(o, "Reference") for o in b._ensure_dispatch_sequence(pattern.InitialObjects)]
                expected_sources = [o["reference"] for o in owned if o.get("role") == "tooth_space_cut.feature"]
                if len(sources) != len(expected_sources) or set(sources) != set(expected_sources):
                    raise RuntimeError("Gear pattern source identity changed")
                axis = next(o["reference"] for o in owned if o.get("role") == "blank.axis")
                if b.safe_get(pattern.Axis, "Reference") != axis:
                    raise RuntimeError("Gear pattern axis identity changed")
            if collection == "FeaturePatterns" and out.get("hole_pattern"):
                pattern = b._cast_to_com_interface(obj, "ICircularPattern")
                _close(b.safe_get(pattern, "Count2"), out["hole_pattern"]["count"])
                _close(b.safe_get(pattern, "Step2"), out["hole_pattern"]["step_deg"], 1e-7)
                sources = [b.safe_get(o, "Reference") for o in b._ensure_dispatch_sequence(pattern.InitialObjects)]
                source = next(o["reference"] for o in owned if o["role"] == "source_cut")
                axis = next(o["reference"] for o in owned if o["role"] == "axis")
                if sources != [source] or b.safe_get(pattern.Axis, "Reference") != axis:
                    raise RuntimeError("Bolt-circle source/axis identity changed")
        if out.get("macro"):
            if identity is not None and out["macro"].get("object_id"):
                found = identity.FindObjectById(out["macro"]["object_id"], None)
                matches = [b._cast_to_com_interface(found, "IModelObject")] if found is not None else []
            else:
                matches = [obj for obj in b.iter_collection(b.safe_get(model, "MacroObjects3D"))
                           if b.safe_get(obj, "Reference") == out["macro"]["reference"]]
            # Destroy() deliberately ungroups without destroying owned roots.
            out["macro"]["grouped"] = bool(matches)
            if len(matches) > 1:
                raise RuntimeError("Chain macro reference is ambiguous: " + out["id"])
            if matches:
                macro = b._cast_to_com_interface(matches[0], "IMacroObject3D")
                out["macro"]["reference"] = b.safe_get(matches[0], "Reference")
                if identity is not None:
                    object_id = identity.GetObjectId(b._cast_to_com_interface(matches[0], "IKompasAPIObject"), None)
                    if not isinstance(object_id, str) or not 1 <= len(object_id) <= 512:
                        raise RuntimeError("Native persistent macro identity unavailable")
                    out["macro"]["object_id"] = object_id
                refs = [b.safe_get(obj, "Reference") for obj in b._ensure_dispatch_sequence(macro.Objects)]
                if len(refs) != len(owned) or set(refs) != {o["reference"] for o in owned}:
                    raise RuntimeError("Chain macro contains foreign/missing objects: " + out["id"])
    return current


def _collection(b, model, name):
    owner = b._cast_to_com_interface(model, "IAuxiliaryGeomContainer") if name in ("Axes3D", "Spirals3D", "Planes3D", "LocalCoordinateSystems") else model
    result = b.safe_get(owner, name)
    getter = b.safe_get(owner, "Get" + name)
    return result if result is not None else getter() if callable(getter) else None


def _family_owned(b, model, runtime, step):
    role_collections = {"sketch": "Sketchs", "axis": "Axes3D", "axis_start": "Points3D", "axis_end": "Points3D",
        "spiral": "Spirals3D", "spiral_start_point": "Points3D"}
    features = {"cylindrical_blank": "Extrusions", "rotational_cut": "Rotateds", "cut_extrusion": "Extrusions",
        "helical_cut_evolution": "Evolutions", "circular_pattern": "FeaturePatterns"}
    owned, objects, seen = [], [], set()
    for ident, entry in runtime.items():
        roles = dict(role_collections)
        if entry["scenario"] in features:
            roles["feature"] = features[entry["scenario"]]
        for role, collection in roles.items():
            obj = entry.get(role)
            if obj is None:
                continue
            raw = b._cast_to_com_interface(obj, "IModelObject")
            ref = b.safe_get(raw, "Reference")
            if not ref:
                raise RuntimeError("Gear owned object has no native reference")
            if ref in seen:
                continue
            seen.add(ref)
            owned.append({"collection": collection, "reference": ref, "name": b.safe_get(raw, "Name"),
                "role": ident + "." + role, "require_fully_defined": bool(entry["params"].get("require_fully_defined", True))})
            objects.append(obj)
    if not owned or len(owned) > 32:
        raise RuntimeError("Unsupported gear root ownership count")
    return owned, objects


def _thread_carrier_guard(plan, guard, params):
    """Pure semantic gate shared by pre-write context and post-cut audit."""
    steps = _validate(plan)
    blind = guard.get("scope") == "blind_external_metric_cylinder_positive_x"
    through = guard.get("scope") == "through_external_metric_cylinder_positive_x"
    ending = blind or through
    if not ending and guard.get("scope") != "complete_exposed_external_metric_cylinder_positive_x":
        raise ValueError("Unsupported thread carrier preflight scope")
    if not ending and guard.get("end_plan") is not None:
        raise ValueError("Legacy carrier scope cannot contain an explicit end plan")
    if any(s["module"] not in ("stepped_shaft", "external_conical_step") or s["material"] == "remove" for s in steps):
        raise ValueError("Thread native context requires uncut rotational stock")
    matches = [s for s in steps if s["id"] == guard.get("target_step_id")]
    if len(matches) != 1:
        raise ValueError("Thread native context needs an explicit existing constructor")
    target = matches[0]
    section = target["section"]
    if target["module"] != "stepped_shaft" or target["placement"]["direction"] != 1 or len(section["segments"]) != 1:
        raise ValueError("Thread native context requires one complete +X cylinder")
    lo, hi = [_number(v) for v in guard["working_span_mm"]]
    radius, root = _number(guard["carrier_radius_mm"]), _number(guard["root_radius_mm"])
    _close(lo, section["start_mm"])
    carrier_end = section["end_mm"]
    if ending:
        if (params.get("profile_root_shape") != "round" or
                any(params.get(key) != "auto" for key in
                    ("thread_depth_mode", "root_round_radius_mode", "profile_entry_offset_mode")) or
                params.get("profile_surface_offset_applied")):
            raise ValueError("Metric end context requires the automatic round contour")
        if blind and hi >= carrier_end-LENGTH_TOL:
            raise ValueError("Blind native context requires a positive smooth tail")
        if through:
            _close(hi, carrier_end)
        if guard.get("carrier_span_mm") != [lo, carrier_end]:
            raise ValueError("Metric end carrier span differs from stock")
        stock = [s for step in steps for s in step["section"]["segments"]]
        if guard.get("stock_envelope_segments") != stock:
            raise ValueError("Protected envelope differs from stock")
        end_plan = guard.get("end_plan", {})
        mode = "blind" if blind else "through"
        if (end_plan.get("schema") != "geomwright.metric_thread."+mode+"_end.plan" or
                end_plan.get("version") != 1 or end_plan.get("exit_mode") != mode or
                end_plan.get("requested_span_mm") != [lo, hi] or
                end_plan.get("verified") is not False or
                end_plan.get("functional_thread_length_verified") is not False or
                end_plan.get("controlled_runout") is not False or
                end_plan.get("native_end_section_audit_required") is not True):
            raise ValueError("Invalid metric native end plan")
        _close(_number(end_plan["last_cut_trace_mm"]), hi)
        width = 2*_number(params["profile_outer_half_width"])
        projection = end_plan["terminal_section_projection_mm"]
        if len(projection) != 2 or width <= 0:
            raise ValueError("Invalid cutter terminal section projection")
        _close(_number(projection[0]), hi-width if blind else hi)
        _close(_number(projection[1]), hi if blind else hi+width)
        _close(_number(end_plan["partial_terminal_projection_width_mm"]), width)
        _close(_number(end_plan["conservative_profile_projection_end_mm"]), hi-width if blind else hi)
        kernel_length = _number(params["length"])+_number(params["pitch"])/4+(-width/2 if blind else width/2)
        _close(_number(end_plan["kernel_length_mm"]), kernel_length)
        _close(_number(end_plan["spiral_length_mm"]), kernel_length+_number(params["profile_entry_offset"]))
        _close(_number(params["spiral_length"]), _number(end_plan["spiral_length_mm"]))
        height = [b for b in params["operation_variable_bindings"] if b.get("role") == "spiral_height"]
        if len(height) != 1 or height[0] != end_plan.get("height_binding"):
            raise ValueError("Spiral driver differs from end plan")
        if through:
            tangent = _number(guard["root_tangent_radius_mm"])
            _close(tangent, _number(params["profile_points"][1][1]))
            if not root < tangent < radius:
                raise ValueError("Through root-tangent radius must be inside the working shell")
    else:
        _close(hi, carrier_end)
    _close(radius, section["segments"][0]["start_radius_mm"])
    _close(radius, section["segments"][0]["end_radius_mm"])
    if not 0 < root < radius or hi <= lo:
        raise ValueError("Thread native context has invalid working shell")
    if (params.get("thread_profile_family") != "metric_v60" or params.get("internal") or
            params.get("carrier_shape") != "cylindrical" or params.get("crest_round_pass")):
        raise ValueError("Thread native context requires the initial external metric profile")
    _close(_number(params["carrier_diameter"]), 2*radius)
    _close(_number(params["diameter"]), 2*radius)
    _close(_number(params["length"]), hi-lo)
    _close(_number(params["thread_depth"])+_number(params.get("clearance") or 0), radius-root)
    pitch = _number(params["pitch"])
    if pitch <= 0 or not 2 <= (hi-lo)/pitch <= 64:
        raise ValueError("Thread native context requires 2..64 turns")
    for key, x in (("start_origin", lo), ("end_origin", hi)):
        if len(params[key]) != 3:
            raise ValueError("Thread native origin must be a 3D point")
        for value, expected in zip(params[key], (x, 0, 0)):
            _close(_number(value), expected)
    for step in steps:
        if step["id"] == target["id"]:
            continue
        for segment in step["section"]["segments"]:
            if ending and segment["axial_min"] >= carrier_end-LENGTH_TOL:
                if through and max(segment["start_radius_mm"], segment["end_radius_mm"]) >= root-LENGTH_TOL:
                    raise ValueError("Through exit stock does not clear the root core")
                continue
            if segment["axial_max"] > lo+LENGTH_TOL or max(segment["start_radius_mm"], segment["end_radius_mm"]) >= root-LENGTH_TOL:
                raise ValueError("Native thread context cannot protect stock outside the rear root core")
    _close(_number(guard["expected_blank_volume_cm3"]), steps[-1]["expected_total_volume_cm3"], floor=1e-6)
    return steps


def _straight_spline_input_carrier_guard(plan, guard, application):
    """Native semantic preflight; host retains catalog and canonical generation."""
    if application.get("schema") == "geomwright.straight_spline.input_hub.plan":
        return _spline_runtime().hub_carrier_guard(sys.modules[__name__],plan,guard,application)
    steps = _validate(plan)
    if any(s["module"] not in ("stepped_shaft", "external_conical_step") or
           s["basis"] != "own" or s["material"] not in ("create", "add") for s in steps):
        raise ValueError("Input spline requires uncut rotational stock")
    matches = [s for s in steps if s["id"] == guard.get("target")]
    if len(matches) != 1:
        raise ValueError("Input spline requires one explicit constructor target")
    target = matches[0]
    section = target["section"]
    if (target["module"] != "stepped_shaft" or target["placement"]["direction"] != 1 or
            section["axis"] != "global_x" or section["phase_degrees"] != 0 or len(section["segments"]) != 1):
        raise ValueError("Input spline target must be one +X cylinder")
    if (application.get("schema") != "geomwright.straight_spline.input_shaft.plan" or application.get("version") != 1 or
            set(application) != {"schema","version","name","profile_request","geometry","operations","inputs",
                "working_span_mm","expected_single_space_removal_cm3","expected_removal_cm3","verification","capabilities"}):
        raise ValueError("Invalid input spline plan schema/fields")
    g, request = application["geometry"], application["profile_request"]
    if (request.get("body") != "shaft" or request.get("standard") != "gost_1139_80" or
            g.get("body") != "shaft" or request.get("include_tip_chamfer") is not False):
        raise ValueError("Input spline supports only external shafts without end chamfers")
    lo, hi = [_number(v) for v in application["working_span_mm"]]
    radius = section["segments"][0]["start_radius_mm"]
    root, width = [_number(g[k]) for k in ("root_radius_mm","length_mm")]
    count = g["tooth_count"]
    if (not section["start_mm"] <= lo < hi <= section["end_mm"] or
            not 0 < root < radius or isinstance(count,bool) or not isinstance(count,int) or not 4 <= count <= 40):
        raise ValueError("Invalid spline working span/root/count")
    for actual, expected in ((hi-lo,width),(width,request["length_mm"]),(g["outer_radius_mm"],radius),
                             (g["outer_diameter_mm"],2*radius)):
        _close(actual,expected)
    for key in ("tooth_count","inner_diameter_mm","outer_diameter_mm","tooth_width_mm"):
        if request.get(key) is not None:
            _close(g[key],request[key])
    if application["inputs"] != {"profile_plane":{"axis":"global_x","origin_mm":[lo,0,0],"direction":1},
                                "axis":"global_x","carrier_diameter_mm":2*radius}:
        raise ValueError("Input spline placement/supports differ from selected cylinder")
    operations = application["operations"]
    if len(operations) != 3 or any(set(o) != {"id","scenario","params"} for o in operations):
        raise ValueError("Input spline contains hidden or extra operations")
    profile = operations[0]["params"]
    label = application["name"]
    if not isinstance(label,str) or not label.strip():
        raise ValueError("Input spline needs a nonempty canonical name")
    expected_ops = [
        {"id":"tooth_space_sketch","scenario":"numeric_profile_sketch","params":{
            "name":label+" one tooth space","plane":"input.profile_plane","entities":profile.get("entities"),
            "parameterize":False,"require_fully_defined":False,"profile_status":"nominal_straight_sided_space_numeric_profile"}},
        {"id":"tooth_space_cut","scenario":"cut_extrusion","params":{
            "name":label+" one tooth space cut","sketch":"tooth_space_sketch.sketch","direction":"normal",
            "end_condition":"length","depth":width,"require_fully_defined":False}},
        {"id":"tooth_space_pattern","scenario":"circular_pattern","params":{
            "name":label+" tooth space pattern","source":"tooth_space_cut.feature","axis":"input.axis",
            "count":count,"span_angle":360.0,"parameterize":False}}]
    if operations != expected_ops:
        raise ValueError("Input spline operations differ from bounded source-free cutter")
    _spline_space_guard(profile["entities"],g)
    single = _number(g["space_area_mm2"])*width/1000
    removed = single*count
    if not 0 < removed < math.pi*radius**2*width/1000:
        raise ValueError("Input spline removal must retain positive core")
    _close(application["expected_single_space_removal_cm3"],single,1e-9,1e-12)
    _close(application["expected_removal_cm3"],removed,1e-9,1e-12)
    if (application["capabilities"] != {"creates_blank":False,"internal_spline":False,"tip_chamfer":False,
            "tool_runout":False,"in_place_recipe_editing":False,"native_execution_implemented":False} or
            application["verification"] != {"verified":False,"native_span_audit_required":True,
                "native_pattern_removal_audit_required":True,"native_protected_stock_audit_required":True,
                "numeric_profile_readback_required":True,"functional_length_verified":False}):
        raise ValueError("Input spline plan must retain its unverified bounded capability flags")
    protected, stock = [], []
    for step in steps:
        other = step["section"]
        if other["axis"] != "global_x" or other["phase_degrees"] != 0:
            raise ValueError("Input spline stock must share global X")
        stock.extend(other["segments"])
        for row in other["segments"]:
            a, c = row["axial_min"], row["axial_max"]
            if step["id"] != target["id"]:
                if min(c,hi) > max(a,lo):
                    raise ValueError("Spline working span overlaps non-target stock")
                protected.append({"step_id":step["id"],"segment":deepcopy(row)})
            else:
                for start,end in ((a,lo),(hi,c)):
                    if start < end:
                        protected.append({"step_id":target["id"],"segment":{
                            "axial_min":start,"axial_max":end,"start_radius_mm":radius,"end_radius_mm":radius}})
    blank = _volume(stock)
    # Exact host fields use the exact family area, not the sampled guard estimate.
    removed = application["expected_removal_cm3"]
    expected = {"schema":"geomwright.straight_spline.input_carrier.guard","version":1,
        "scope":"bounded_external_spline_cylinder_positive_x","target":target["id"],
        "carrier_span_mm":section["axial_interval_mm"],"working_span_mm":[lo,hi],
        "carrier_radius_mm":radius,"root_radius_mm":root,"protected_stock":protected,
        "expected_blank_volume_cm3":blank,"expected_removed_cm3":removed,"expected_final_volume_cm3":blank-removed,
        "body_count":1,"native_carrier_verified":False,"material_preservation_verified":False}
    if guard != expected:
        raise ValueError("Native input spline guard differs from canonical stock and cutter")
    return steps


def _straight_spline_input_carrier_context(b, app, doc, plan, guard, application):
    """Read-only pre-write stock/ownership context; never audit a threaded/cut body."""
    steps = _straight_spline_input_carrier_guard(plan,guard,application)
    if b.describe_runtime_document(doc,app).get("type") != 10024:
        raise ValueError("Input spline requires an exact KOMPAS part document")
    envelope,error = b._creation_module_recipe(doc.TopPart,"construction_chain")
    if (error or not envelope or envelope.get("recipe") != plan["recipe"] or
            envelope.get("expectations") != _expectations(steps) or len(envelope.get("outputs",[])) != len(steps)):
        raise RuntimeError("Input spline saved prefix differs from the selected canonical chain")
    model = b.cast_model_container(doc.TopPart)
    prefix = _ownership(b,model,envelope["outputs"],strict_names=True,document=doc)
    body = _read_body(b,app,doc,doc.TopPart)
    _verify(body,steps)
    _close(body["volume_cm3"],guard["expected_blank_volume_cm3"],floor=1e-6)
    lo,hi = guard["carrier_span_mm"]
    hub = guard.get("scope") in ("through_internal_spline_cylinder_positive_x","blind_internal_spline_cylinder_positive_x")
    context = _resolved_cylindrical_thread_faces(b,doc.TopPart,body,prefix,lo,hi,
        guard["root_radius_mm"] if hub else guard["carrier_radius_mm"])
    context["verification"].pop("thread_executed")
    context["verification"]["spline_executed"] = False
    return context


def _internal_metric_carrier_guard(plan, guard, params):
    """Pure native preflight; no host imports or formula recalculation engine."""
    if guard.get("scope") == "blind_internal_metric_cylinder_positive_x":
        if guard.get("carrier_guard", {}).get("scope") not in ("complete_internal_metric_cylinder_positive_x", "flat_bottom_internal_metric_cylinder_positive_x"):
            raise ValueError("Internal blind guard needs the canonical full-bore carrier")
        physical = guard["carrier_guard"]["working_span_mm"]
        full = deepcopy(params)
        full.update(length=physical[1]-physical[0], end_origin=[physical[1], 0, 0],
                    spiral_length=physical[1]-physical[0]+1.3*params["pitch"]+params["profile_outer_half_width"])
        steps = _internal_metric_carrier_guard(plan, guard["carrier_guard"], full)
        lo, hi = physical
        stock_span = guard["carrier_guard"].get("stock_span_mm", physical)
        length, pitch, half = [_number(params[k]) for k in ("length", "pitch", "profile_outer_half_width")]
        if not 2 <= length/pitch <= 64 or not 0 < length < hi-lo:
            raise ValueError("Internal blind ending requires positive working span and smooth bore tail")
        end = lo+length
        height = deepcopy(next(b for b in params["operation_variable_bindings"] if b["role"] == "spiral_height"))
        height["expression"] = (params["public_length_variable_name"]+" + 1.3 * "+params["public_pitch_variable_name"]+
                                " - ("+params["profile_dimension_expressions"]["sketch_outer_half"]+")")
        expected_end = {"schema": "geomwright.internal_metric.end.plan", "version": 1, "exit_mode": "blind",
            "stock_span_mm": stock_span, "bore_span_mm": [lo, hi], "working_span_mm": [lo, end],
            "bore_diameter_mm": params["carrier_diameter"], "nominal_diameter_mm": params["diameter"],
            "kernel_frame_offset_mm": pitch/4, "profile_outer_half_width_mm": half,
            "spiral_length_mm": length+1.3*pitch-half, "height_binding": height, "last_cut_trace_mm": end,
            "terminal_section_projection_mm": [end-2*half, end], "terminal_section_is_virtual": False,
            "partial_terminal_projection_width_mm": 2*half,
            "conservative_profile_projection_end_mm": end-2*half, "smooth_bore_tail_mm": hi-end,
            "bottom_stock_thickness_mm": stock_span[1]-hi, "bore_has_bottom": stock_span[1] > hi, "verified": False,
            "native_end_section_audit_required": True, "functional_thread_length_verified": False, "controlled_runout": False}
        expected = {**guard["carrier_guard"], "scope": "blind_internal_metric_cylinder_positive_x",
            "working_span_mm": [lo, end], "carrier_span_mm": physical, "carrier_guard": guard["carrier_guard"],
            "end_plan": expected_end, "removal_upper_bound_cm3": math.pi*(guard["major_radius_mm"]**2-guard["bore_radius_mm"]**2)*length/1000}
        if guard != expected or params["end_origin"] != [end,0,0] or params["spiral_length"] != expected_end["spiral_length_mm"] or next(
                b for b in params["operation_variable_bindings"] if b["role"] == "spiral_height") != height:
            raise ValueError("Internal blind native guard/height differs from the canonical endpoint")
        return steps
    steps = _validate(plan)
    if (len(steps) != 2 or [s["module"] for s in steps] != ["stepped_shaft", "internal_cylindrical_step"] or
            steps[1].get("target") != steps[0]["id"] or
            any(len(s["section"]["segments"]) != 1 for s in steps)):
        raise ValueError("Internal native context requires one cylindrical blank and one bore")
    stock, bore = steps
    stock_span = stock["section"]["axial_interval_mm"]
    lo, hi = bore["section"]["axial_interval_mm"]
    bottom = guard.get("scope") == "flat_bottom_internal_metric_cylinder_positive_x"
    valid_span = stock_span[0] == lo and stock_span[1] > hi if bottom else stock_span == [lo, hi]
    if (not valid_span or
            any(s["section"]["end_mm"] <= s["section"]["start_mm"] for s in steps)):
        raise ValueError("Internal native context requires a complete +X through bore")
    outer, inner = [_number(s["section"]["segments"][0]["start_radius_mm"]) for s in steps]
    diameter, pitch, length = [_number(params[key]) for key in ("diameter", "pitch", "length")]
    method = {"schema": "geomwright.internal_metric_through.plan", "version": 1,
        "bore_diameter_mm": 2 * inner, "bore_policy": "immutable_input",
        "diameter_driver_semantics": "nominal_major_diameter", "profile_depth_semantics": "actual_radial_cut",
        "native_verification_required": True, "functional_thread_length_verified": False}
    if (params.get("internal_metric_method") != method or not params.get("internal") or
            params.get("thread_profile_family") != "metric_v60" or params.get("carrier_shape") != "cylindrical" or
            params.get("profile_root_shape") != "round" or not 0 < inner < diameter / 2 < outer or
            pitch <= 0 or not 2 <= length / pitch <= 64 or abs(length - (hi - lo)) > 1e-6 or
            params.get("start_origin") != [lo, 0, 0] or params.get("end_origin") != [hi, 0, 0]):
        raise ValueError("Internal native thread profile/span differs from the bore")
    _close(_number(params["carrier_diameter"]), 2 * inner, floor=1e-9)
    _close(_number(params["radial_cut_depth"]), diameter / 2 - inner, floor=1e-9)
    phase = 0 if params.get("left_thread") else 180
    if params.get("spiral_phase_degrees") != phase:
        raise ValueError("Internal thread phase differs from the verified profile frame")
    round_radius = pitch / (16 * math.cos(math.pi / 6))
    depth = diameter / 2 - inner
    tangent = depth-round_radius/2
    half = pitch/16+tangent*math.tan(math.pi/6)
    if not 0 < round_radius < depth or not 0 < half < pitch/2 or not depth+round_radius < math.sqrt(3)*pitch/2:
        raise ValueError("Internal round contour does not fit the input bore")
    for key, value in (("root_radius", round_radius), ("profile_tangent_depth", tangent),
                       ("profile_arc_center_depth", depth-round_radius), ("profile_outer_half_width", half),
                       ("profile_virtual_apex_depth", depth+round_radius),
                       ("spiral_length", length+1.3*pitch+half)):
        _close(_number(params[key]), value, floor=1e-9)
    expected = {"schema": "geomwright.internal_metric_carrier.guard", "version": 1,
        "scope": "flat_bottom_internal_metric_cylinder_positive_x" if bottom else "complete_internal_metric_cylinder_positive_x", "target": bore["id"], "stock_target": stock["id"],
        "axis": "global_x", "body_count": 1, "working_span_mm": [lo, hi], "bore_radius_mm": inner,
        "major_radius_mm": diameter / 2, "outer_radius_mm": outer,
        "root_tangent_radius_mm": diameter / 2 - pitch / (32 * math.cos(math.pi / 6)),
        "expected_blank_volume_cm3": math.pi * (outer**2 - inner**2) * length / 1000,
        "removal_upper_bound_cm3": math.pi * ((diameter / 2)**2 - inner**2) * length / 1000,
        "input_bore_immutable": True, "native_carrier_verified": False, "material_preservation_verified": False}
    if bottom:
        expected.update(stock_span_mm=stock_span, bottom_stock_thickness_mm=stock_span[1]-hi,
            expected_blank_volume_cm3=math.pi*(outer**2*(stock_span[1]-lo)-inner**2*length)/1000)
    if guard != expected:
        raise ValueError("Internal native carrier guard differs from the canonical stock")
    return steps


def _internal_metric_carrier_context(b, app, doc, plan, guard, params):
    """Read-only pre-write context. Never use it on an already threaded body."""
    steps = _internal_metric_carrier_guard(plan, guard, params)
    if b.describe_runtime_document(doc, app).get("type") != 10024:
        raise ValueError("Internal thread application requires a KOMPAS part document")
    part = doc.TopPart
    envelope, error = b._creation_module_recipe(part, "construction_chain")
    if (error or not envelope or _hash(envelope["recipe"]) != _hash(plan["recipe"]) or
            envelope["expectations"] != _expectations(steps) or len(envelope["outputs"]) != len(steps)):
        raise RuntimeError("Internal thread input prefix differs from the saved chain")
    model = b.cast_model_container(part)
    prefix = _ownership(b, model, envelope["outputs"], strict_names=True, document=doc)
    body = _read_body(b, app, doc, part)
    _verify(body, steps)
    _close(body["volume_cm3"], _number(guard["expected_blank_volume_cm3"]), floor=1e-6)
    lo, hi = guard.get("carrier_span_mm", guard["working_span_mm"])
    context = _resolved_cylindrical_thread_faces(b, part, body, prefix, lo, hi, guard["bore_radius_mm"])
    context["verification"]["input_bore_immutable"] = True
    return context


def _thread_carrier_context(b, app, doc, plan, guard, params):
    """Fresh pre-write faces; ownership and uncut stock must match saved prefix.

    COM faces expire on rebuild/cut. Post-cut auditing must not call this reader
    or pretend the threaded final body is the original rotational blank.
    """
    steps = _thread_carrier_guard(plan, guard, params)
    lo, hi = guard["working_span_mm"]
    if guard.get("scope") in ("blind_external_metric_cylinder_positive_x", "through_external_metric_cylinder_positive_x"):
        lo, hi = guard["carrier_span_mm"]  # Native boundary faces belong to stock.
    radius = guard["carrier_radius_mm"]
    if b.describe_runtime_document(doc, app).get("type") != 10024:
        raise ValueError("Thread application requires a KOMPAS part document")
    part = doc.TopPart
    envelope, error = b._creation_module_recipe(part, "construction_chain")
    if error or not envelope or _hash(envelope["recipe"]) != _hash(plan["recipe"]) or envelope["expectations"] != _expectations(steps):
        raise RuntimeError("Thread input prefix differs from the saved construction chain")
    if len(envelope["outputs"]) != len(steps):
        raise RuntimeError("Thread input prefix ownership is incomplete")
    model = b.cast_model_container(part)
    prefix = _ownership(b, model, envelope["outputs"], strict_names=True, document=doc)
    body = _read_body(b, app, doc, part)
    _verify(body, steps)
    _close(body["volume_cm3"], _number(guard["expected_blank_volume_cm3"]), floor=1e-6)
    return _resolved_cylindrical_thread_faces(b, part, body, prefix, lo, hi, radius)


def _resolved_cylindrical_thread_faces(b, part, body, prefix, lo, hi, radius):
    """Shared current-body cylindrical/end-plane readback; no writes or source edits."""
    radial = [f for f in body["faces"] if f["surface_type"] == "cylinder" and
              abs(f["axial_min"]-lo) <= LENGTH_TOL and abs(f["axial_max"]-hi) <= LENGTH_TOL and
              abs(f["start_radius_mm"]-radius) <= LENGTH_TOL and abs(f["end_radius_mm"]-radius) <= LENGTH_TOL]
    if len(radial) != 1:
        raise RuntimeError("Actual thread carrier cylinder is missing or ambiguous")
    bodies = b._ensure_dispatch_sequence(b._cast_to_com_interface(part, "IFeature7").ResultBodies)
    faces = b._ensure_dispatch_sequence(b._cast_to_com_interface(bodies[0], "IFeature7").ModelObjects(6))
    base = [b._cast_to_com_interface(obj, "IFace") for obj in faces if b.safe_get(obj, "Reference") == radial[0]["reference"]]
    if len(base) != 1:
        raise RuntimeError("Current native carrier face identity is ambiguous")
    frame = _cylinder_frame(b, base[0])
    if abs(abs(frame["z_axis"][0])-1) > 1e-7 or math.hypot(*frame["origin_mm"][1:]) > LENGTH_TOL:
        raise RuntimeError("Actual thread carrier axis is not global X")
    borders = {"start_face": [], "end_face": []}
    for obj in faces:
        face = b._cast_to_com_interface(obj, "IFace")
        if not b.safe_get(face, "IsPlanar", False):
            continue
        surface = b._cast_to_com_interface(face.MathSurface, "IMathSurface3D")
        u, v = (surface.ParamUMin+surface.ParamUMax)/2, (surface.ParamVMin+surface.ParamVMax)/2
        point, normal = _point_result(surface.GetPoint(u, v)), _point_result(surface.GetNormal(u, v))
        if abs(normal[0]) <= 1e-9 or math.hypot(*normal[1:]) > abs(normal[0])*1e-9:
            continue
        if len(b._ensure_dispatch_sequence(face.LimitingEdges)) > 128:
            raise RuntimeError("Thread boundary-face budget exceeded")
        for key, x in (("start_face", lo), ("end_face", hi)):
            if abs(point[0]-x) <= LENGTH_TOL:
                _, edge_report = b._select_face_boundary_edge(face, x, target_radius=radius)
                borders[key].append((face, edge_report))
    if any(len(rows) != 1 for rows in borders.values()):
        raise RuntimeError("Actual thread boundary faces are missing or ambiguous")
    resolved = {"base_face": base[0], **{key: rows[0][0] for key, rows in borders.items()}}
    reports = {key: {"reference": b.safe_get(face, "Reference"), "selection": "current_final_body_exact_span",
                     **({"edge": borders[key][0][1]} if key in borders else {})} for key, face in resolved.items()}
    return {**resolved, "face_reports": reports, "prefix_outputs": prefix, "body_before": body,
            "verification": {"native_carrier_verified": True, "prefix_ownership_verified": True,
                             "material_preservation_verified": False, "thread_executed": False}}


def _group_step(b, model, built, out):
    """Group only this instance's roots; input body and earlier supports stay outside."""
    import pythoncom
    import win32com.client
    macro = model.MacroObjects3D.Add()
    macro.Name = "Chain step [" + out["id"] + "]"
    macro.Objects = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
        [b._cast_to_com_interface(obj, "IModelObject") for obj in
         (built["owned_objects"] if "owned_objects" in built else [built[key] for key in ("sketch", "rotated")])])
    if not macro.Update():
        raise RuntimeError("Chain macro creation failed: " + out["id"])
    reference = b.safe_get(macro, "Reference")
    if not reference:
        raise RuntimeError("Chain macro reference unavailable: " + out["id"])
    out["macro"] = {"reference": reference, "name": macro.Name, "grouped": True}


def _continuation_preflight(payload, b, plan, steps):
    """Re-resolve and audit the exact immutable prefix inside the dispatch mutex.

    Activation is explicit for API5 readback; no rebuild, metadata or geometry
    write occurs here. Recognition alone never authorizes appending.
    """
    ident = payload.get("document_id")
    if payload.get("confirm_write") is not True:
        raise ValueError("Continuation requires confirm_write=true")
    if not isinstance(ident, str) or not ident.strip():
        raise ValueError("Exact opened document_id is required for continuation")
    app = b.make_app()
    selected = b.resolve_document_strict(app, ident)
    if selected is None:
        raise RuntimeError("Exact construction chain document is not open")
    doc = b.cast_document_3d(selected)
    if doc is None:
        raise RuntimeError("Continuation requires a saved 3D construction-chain document")
    path = b.describe_runtime_document(doc, app).get("path")
    if (not isinstance(path, str) or not os.path.isabs(path) or
            os.path.splitext(path)[1].lower() != ".m3d" or not os.path.isfile(path)):
        raise ValueError("Continuation requires an existing saved construction-chain .m3d file")
    if b.normalize_fs_path(payload.get("output_path") or "") != b.normalize_fs_path(path):
        raise ValueError("Continuation must save the same selected path; path changes are unsupported")
    part = doc.TopPart
    model = b.cast_model_container(part)
    envelope, error = b._creation_module_recipe(part, "construction_chain")
    if error or not envelope:
        raise ValueError("No valid checksummed construction-chain recipe; standalone models are unsupported")
    if envelope.get("schema") != SCHEMA or envelope.get("version") != 1:
        raise ValueError("Continuation requires runtime envelope version 1")
    old = envelope.get("recipe")
    if not old or old.get("schema") != SCHEMA or old.get("version") != 1:
        raise ValueError("Continuation requires recipe version 1")
    if old != payload.get("expected_recipe") or _hash(envelope) != payload.get("expected_recipe_checksum"):
        raise RuntimeError("Saved chain recipe changed since host inspection; inspect again before continuing")
    prefix = len(old["steps"])
    if not 1 <= prefix < len(steps) or plan["recipe"]["steps"][:prefix] != old["steps"]:
        raise ValueError("Continue accepts only new steps; old-step edits/replacement are forbidden")
    outputs, expectations = envelope.get("outputs") or [], envelope.get("expectations") or []
    if len(outputs) != prefix or len(expectations) != prefix:
        raise ValueError("Saved chain ownership/expectations are incomplete")
    for step, expected, out in zip(steps[:prefix], expectations, outputs):
        audit = expected.get("verification", {}).get("foundation_audit")
        if audit is not None:
            if step["module"] not in FOUNDATIONS or not audit.get("verified") or out.get("foundation_audit") != audit:
                raise ValueError("Saved gear foundation audit is incomplete/inconsistent")
            step["verification"]["foundation_audit"] = deepcopy(audit)
        if (_expectations([step])[0] != expected or out.get("id") != step["id"] or
                out.get("namespace") != step["namespace"] or out.get("section") != step["section"]):
            raise ValueError("Saved prefix differs from combined plan identities/parameters/sections")
    active = b.safe_get(app, "ActiveDocument")
    if active is None or b.describe_runtime_document(active, app).get("runtime_id") != b.describe_runtime_document(doc, app).get("runtime_id"):
        activate = b.safe_get(selected, "Activate")
        if callable(activate):
            activate()
        else:
            selected.Active = True
    active = b.safe_get(app, "ActiveDocument")
    if active is None or b.describe_runtime_document(active, app).get("runtime_id") != b.describe_runtime_document(doc, app).get("runtime_id"):
        raise RuntimeError("Exact continuation document activation was not confirmed")
    outputs = _ownership(b, model, outputs, strict_names=True, document=doc)
    gear = _foundation(steps)
    body = _read_body(b, app, doc, part, gear)
    _verify(body, steps[:prefix])
    # Current trimmed faces, not saved root geometry, re-resolve every carrier.
    for step in steps[:prefix]:
        if step["material"] != "remove" and step is not gear and step["module"] not in ("external_polygonal_step", "external_flat_step"):
            _match_sections(body, step["section"]["segments"])
    return app, doc, part, model, outputs, prefix, path


def create(payload, b):
    return execute(payload, b)


def _final_audit(b, app, doc, plan, steps, checkpoint=None):
    if checkpoint is not None and "spline_prefix_plan" in plan:
        terminal = steps[-1]
        checked = _spline_runtime().audit_checkpoint(b, sys.modules[__name__], app, doc,
            plan["spline_prefix_plan"], terminal["spline_guard"], terminal["spline_application"], checkpoint)
        verification = {**checked["verification"], "ok": True, "fresh_geometry_audit": True,
            "whole_inventory_verified": True, "drivers_verified": checked["drivers"]["verified"],
            "expected_total_volume_cm3": terminal["expected_total_volume_cm3"],
            "volume_cm3": checked["body"]["volume_cm3"], "delta_cm3": -checked["verification"]["removed_cm3"],
            "volume_reference": "exact_family_space_removal", "single_solid": True,
            "bounds_verified": True, "macro_grouping_verified": True}
        return checked["body"], verification
    if checkpoint is not None:
        terminal = steps[-1]
        checked = _thread_runtime().audit_checkpoint(b, sys.modules[__name__], app, doc,
            plan["thread_prefix_plan"], terminal["thread_guard"], terminal["preview"], checkpoint)
        verification = {**checked["verification"], "ok": True, "fresh_geometry_audit": True,
            "expected_total_volume_cm3": checkpoint["audited_volume_cm3"],
            "volume_cm3": checked["body"]["volume_cm3"], "delta_cm3": -checked["verification"]["removed_cm3"],
            "volume_reference": checked["volume_reference"], "single_solid": True,
            "bounds_verified": True,
            "macro_grouping_verified": all(out.get("macro", {}).get("grouped", False) for out in checked["outputs"])}
        return checked["body"], verification
    body = _read_body(b, app, doc, doc.TopPart, _foundation(steps))
    return body, _verify(body, steps)


def execute(payload, b, continuation=False):
    plan = payload.get("plan") or {}
    plan = deepcopy(plan)
    path = payload.get("output_path")
    if not continuation:
        if not isinstance(path, str) or not path.strip() or not os.path.isabs(path) or os.path.splitext(path)[1].lower() != ".m3d":
            raise ValueError("Exact absolute output_path ending in .m3d is required")
        if not os.path.isdir(os.path.dirname(path)) or os.path.exists(path):
            raise ValueError("Output parent must exist and target must be a new file")
    app, doc, outputs = None, None, []
    failed, last, stage, saved = None, None, "preflight", False
    write_started, prefix = False, 0
    try:
        full_steps = _validate(plan)
        input_spline = "spline_prefix_plan" in plan
        terminal = full_steps[-1] if input_spline or full_steps[-1]["module"] in ("external_helical_thread", "internal_helical_thread") else None
        if terminal and payload.get("confirm_write") is not True:
            raise ValueError("Terminal chain creation requires confirm_write=true")
        steps = full_steps[:-1] if terminal else full_steps
        thread_checkpoint = None
        gear = _foundation(steps)
        if continuation:
            app, doc, part, model, outputs, prefix, path = _continuation_preflight(payload, b, plan, full_steps)
            last = steps[prefix-1]["id"]
        else:
            stage = "create_document"
            app = b.make_app()
            if b._collect_open_documents_by_path(app, path):
                raise ValueError("Output target is already open")
            write_started = True
            doc, part, model = b._create_part_document(app, bool(payload.get("visible", True)))
            # NewDocument returns IKompasDocument; thread/context readers need
            # the explicit 3D interface, just like reopened/continued documents.
            doc = b.cast_document_3d(doc)
            if doc is None:
                raise RuntimeError("New chain document has no 3D interface")
            part.Name = plan["recipe"]["name"]
            if not part.Update():
                raise RuntimeError("Chain part name update failed")
        document = b.describe_runtime_document(doc, app)
        b.report_progress(5, "chain_continuation_preflight_verified" if continuation else "chain_document_created",
                          document_id=document["runtime_id"], last_verified_step=last, rollback=False)
        previous_volume = 0.0
        for index in range(prefix, len(steps)):
            step = steps[index]
            failed, stage = step["id"], "input_geometry"
            document = b.describe_runtime_document(doc, app)
            b.report_progress(5 + 80*index/len(steps), "chain_step_started", document_id=document["runtime_id"],
                              target=failed, failed_step=failed, last_verified_step=last, rollback=False)
            if index:
                before = _read_body(b, app, doc, part, gear)
                _verify(before, steps[:index])
                if step["material"] == "remove":
                    carrier = next(s for s in steps[:index] if s["id"] == step["target"])
                    if carrier is not gear and carrier["module"] not in ("external_polygonal_step", "external_flat_step"):
                        _match_sections(before, carrier["section"]["segments"])
                previous_volume = before["volume_cm3"]
            stage = "build_step"
            write_started = True
            reports = []
            runtime = None
            if step is gear:
                runtime = {}
                for operation in _family_plan(step)["workflow"]["params"]["operations"]:
                    b._execute_workflow_operation(part, model, deepcopy(operation), runtime, reports)
                owned, objects = _family_owned(b, model, runtime, step)
                primary_sketch = next(o for o in owned if o["role"] == "blank.sketch")
                primary_feature = next(o for o in owned if o["role"] == "blank.feature")
                out = {"id": step["id"], "namespace": step["namespace"], "section": deepcopy(step["section"]),
                       "sketch": deepcopy(primary_sketch), "feature": deepcopy(primary_feature),
                       "owned_objects": owned, "variable_names": [], "dimension_names": []}
                built = {"owned_objects": objects}
            elif step["module"] in ("external_polygonal_step", "external_flat_step"):
                built, out = _prism_runtime().build(b, part, model, step, reports)
            elif step["module"] == "bolt_circle_holes":
                built, out = _holes_runtime().build(b, part, model, step, reports)
            else:
                params = deepcopy(step["preview"]["params"])
                params.update(require_fully_defined=True, require_parameterization=True)
                built = b._build_stepped_shaft_feature(part, model, params, step["preview"], reports,
                        operation_kind="cut" if step["material"] == "remove" else "boss")
                kind = "cut_rotation" if step["material"] == "remove" else "base_rotation"
                name = next(op["name"] for op in step["preview"]["operations"] if op["operation"] == kind)
                built["rotated"].Name = name
                if not built["rotated"].Update():
                    raise RuntimeError("Canonical rotation name update failed")
                out = {"id": step["id"], "namespace": step["namespace"], "section": deepcopy(step["section"]),
                   "sketch": {"name": params["sketch_name"], "reference": b.safe_get(built["sketch"], "Reference")},
                   "feature": {"name": name, "reference": b.safe_get(built["rotated"], "Reference")},
                   "variable_names": [v["name"] for op in step["preview"]["operations"] for v in op.get("variables", [])],
                   "dimension_names": [d["name"] for op in step["preview"]["operations"] for d in op.get("dimensions", []) if d.get("name")]}
            if not out["sketch"]["reference"] or not out["feature"]["reference"]:
                raise RuntimeError("Chain ownership references unavailable")
            outputs.append(out)
            stage = "rebuild_verify"
            b.report_progress(5 + 80*(index+0.5)/len(steps), "chain_rebuild_started",
                              document_id=document["runtime_id"], target=failed,
                              failed_step=failed, last_verified_step=last, rollback=False)
            if not b.cast_document_3d(doc).RebuildDocument():
                raise RuntimeError("Chain rebuild failed")
            outputs = _ownership(b, model, outputs, strict_names=True, document=doc)
            b.report_progress(5 + 80*(index+0.6)/len(steps), "chain_body_readback_started",
                              document_id=document["runtime_id"], target=failed,
                              failed_step=failed, last_verified_step=last, rollback=False)
            body = _read_body(b, app, doc, part, gear)
            if step is gear:
                stage = "family_foundation_audit"
                audit = _family_audit(b, doc, part, model, step, runtime, reports, body)
                step["verification"]["foundation_audit"] = audit
                outputs[-1]["foundation_audit"] = deepcopy(audit)
            verification = _verify(body, steps[:index+1], previous_volume)
            stage = "group_step"
            _group_step(b, model, built, outputs[-1])
            if not b.cast_document_3d(doc).RebuildDocument():
                raise RuntimeError("Chain macro rebuild failed")
            outputs = _ownership(b, model, outputs, strict_names=True, document=doc)
            _verify(_read_body(b, app, doc, part, gear), steps[:index+1])
            verification["scope"] = "continuation_step" if continuation else "creation_step"
            verification["macro_grouping_verified"] = True
            outputs[-1]["verification"] = verification
            last = failed
            b.report_progress(5 + 80*(index+1)/len(steps), "chain_step_verified", document_id=document["runtime_id"],
                               target=last, last_verified_step=last, failed_step=None, rollback=False)
        if terminal:
            failed, stage = terminal["id"], "terminal_spline_context" if input_spline else "terminal_thread_context"
            prefix_plan = plan["spline_prefix_plan" if input_spline else "thread_prefix_plan"]
            # In-memory prefix checkpoint only: no intermediate saved stock file.
            prefix_envelope = {"schema": SCHEMA, "version": 1, "recipe": prefix_plan["recipe"],
                               "expectations": _expectations(steps), "outputs": outputs}
            _bounded(prefix_envelope)
            write_started = True
            b._store_creation_module_recipe(part, prefix_envelope, "construction_chain")
            stage = "terminal_spline_cut" if input_spline else "terminal_thread_cut"
            thread_runtime = _spline_runtime() if input_spline else _thread_runtime()
            guard = terminal["spline_guard" if input_spline else "thread_guard"]
            application = terminal["spline_application" if input_spline else "preview"]
            result = thread_runtime.execute(b, sys.modules[__name__], app, doc, prefix_plan,
                guard, application, terminal["id"], confirm_write=True)
            thread_checkpoint = thread_runtime.make_checkpoint(sys.modules[__name__], prefix_plan,
                guard, application, result)
            outputs = result["prefix_outputs"]+[result["output"]]
            outputs[-1]["section"] = deepcopy(terminal["section"])
            steps = full_steps
            body, verification = _final_audit(b, app, doc, plan, steps, thread_checkpoint)
            outputs[-1]["verification"] = deepcopy(verification)
            last = failed
        failed, stage = None, "persist_recipe"
        # Patterns expose unnamed derived sketch records too. They are not owned
        # editable roots; do not update/hide them as independent user sketches.
        sketch_refs = {root["reference"] for out in outputs for root in
            (out.get("owned_objects") or [dict(out["sketch"], collection="Sketchs")]) if root["collection"] == "Sketchs"}
        auxiliary = [("sketch", obj) for obj in b.iter_collection(b.safe_get(model, "Sketchs"))
                     if b.safe_get(obj, "Reference") in sketch_refs]
        for output in outputs:
            for owned in output.get("owned_objects", []):
                if owned["collection"] in ("Points3D", "Axes3D", "Spirals3D", "Planes3D", "LocalCoordinateSystems"):
                    obj = next(obj for obj in b.iter_collection(_collection(b, model, owned["collection"]))
                               if b.safe_get(obj, "Reference") == owned["reference"])
                    auxiliary.append((owned["role"], obj))
        auxiliary.extend(("default_%d" % kind, part.DefaultObject(kind)) for kind in (1, 2, 3, 71, 72, 73))
        hidden = b._hide_auxiliary_model_objects(auxiliary, hidden=True)
        if any(not obj.get("ok") for obj in hidden.get("objects", []) if not str(obj.get("role", "")).startswith("default_")):
            failures = [(obj.get("role"), obj.get("name"), obj.get("reason")) for obj in hidden.get("objects", [])
                if not obj.get("ok") and not str(obj.get("role", "")).startswith("default_")]
            raise RuntimeError("Chain owned auxiliary geometry could not be hidden: "+str(failures)[:1000])
        for out in outputs:
            # Older envelopes duplicated the full audit inside the per-step
            # verification; retain its canonical top-level copy only.
            out.get("verification", {}).pop("foundation_audit", None)
        persisted_outputs = deepcopy(outputs)
        for out in persisted_outputs:
            for root in [out.get("sketch", {}), out.get("feature", {}), out.get("macro", {})] + out.get("owned_objects", []):
                root.pop("current_name", None)
            if "verification" in out:
                out["verification"] = {key: value for key, value in out["verification"].items()
                    if key in ("scope", "verified", "macro_grouping_verified", "volume_cm3", "delta_cm3")}
        envelope = {"schema": SCHEMA, "version": 1, "recipe": deepcopy(plan["recipe"]),
                     "expectations": _expectations(steps), "outputs": persisted_outputs,
                    "verification_expectations": {"expected_body_count": 1,
                          "expected_total_volume_cm3": verification["expected_total_volume_cm3"],
                            "volume_reference": "exact_family_space_removal" if input_spline else "audited_native_terminal_thread" if terminal else "audited_native_foundation_plus_analytic_deltas" if gear else "analytic_chain_sections",
                          "require_fully_defined": not bool(gear or input_spline), "length_tolerance_mm": LENGTH_TOL,
                        "volume_relative_tolerance": TOTAL_VOLUME_REL, "delta_relative_tolerance": VOLUME_REL},
                      "capabilities": {"macro_grouping": True, "in_place_editing": False}}
        if terminal:
            envelope["spline_audit" if input_spline else "thread_audit"] = thread_checkpoint
            envelope["capabilities"]["terminal_input_spline" if input_spline else "terminal_thread"] = True
        _bounded(envelope)
        b._store_creation_module_recipe(part, envelope, "construction_chain")
        if not b.cast_document_3d(doc).RebuildDocument():
            raise RuntimeError("Chain metadata rebuild failed")
        _ownership(b, model, outputs, strict_names=True, document=doc)
        _final_audit(b, app, doc, plan, steps, thread_checkpoint)
        stage = "save_direct"
        b.report_progress(90, "chain_save_started", document_id=document["runtime_id"], target=path,
                          failed_step=None, last_verified_step=last, rollback=False)
        if continuation:
            if b.normalize_fs_path(b.describe_runtime_document(doc, app).get("path") or "") != b.normalize_fs_path(path):
                raise RuntimeError("Selected continuation document path changed; refusing save")
            result = doc.Save()
        else:
            result = doc.SaveAs(path)
        b._require_document_save_success(doc, result, path)
        saved = True
        stage = "saved_readback"
        if b._creation_module_recipe(part, "construction_chain") != (envelope, None):
            raise RuntimeError("Saved chain recipe readback differs")
        outputs = _ownership(b, model, outputs, strict_names=True, document=doc)
        body, verification = _final_audit(b, app, doc, plan, steps, thread_checkpoint)
        verification.update(saved_readback=True, recipe_reopened=False, save_reopen_deferred=True)
        if terminal:
            verification["saved_recipe_updated"] = True
        return {"ok": True, "executed": True, "saved": True, "closed": False, "output_path": path,
                "document": b.describe_runtime_document(doc, app), "recipe": plan["recipe"],
                "steps": outputs, "outputs": outputs, "body": body, "verification": verification,
                  "macro_grouping": True, "continued": continuation, "appended_step_count": len(steps)-prefix,
                  "preserved_step_count": prefix}
    except Exception as exc:
        document = None
        if doc is not None:
            try:
                document = b.describe_runtime_document(doc, app)
            except Exception as describe_error:
                document = {"unresolved": True, "error": str(describe_error)[:500]}
        elif continuation:
            document = {"runtime_id": payload.get("document_id"), "unresolved": True}
        checkpoint = {"stage": stage, "failed_step": failed, "last_verified_step": last,
                      "document": document, "steps": outputs, "output_path": path, "saved": saved,
                      "executed": write_started, "verified": False, "rollback": False, "rollback_performed": False}
        b.report_progress(100, "chain_failed", document_id=(document or {}).get("runtime_id"), target=failed,
                          failed_step=failed, last_verified_step=last, rollback=False, error=str(exc)[:500])
        return {"ok": False, "executed": write_started, "error": str(exc)[:2000],
                "partial_result": checkpoint, "checkpoint": checkpoint}


def inspect(payload, b):
    ident = payload.get("document_id")
    if not isinstance(ident, str) or not ident.strip():
        raise ValueError("Exact document_id is required")
    app = b.make_app()
    selected = b.resolve_document_strict(app, ident)
    if selected is None:
        raise RuntimeError("Exact construction chain document is not open")
    doc = b.cast_document_3d(selected)
    if doc is None:
        raise RuntimeError("Construction chain inspection requires a 3D document")
    part = doc.TopPart
    envelope, error = b._creation_module_recipe(part, "construction_chain")
    result = {"ok": True, "recognized": bool(envelope or error), "recipe": None, "recipe_error": error,
              "document": b.describe_runtime_document(doc, app), "steps": [], "outputs": [],
              "outputs_are_saved_creation_evidence": True,
              "verification": {"verified": False, "fresh_geometry_audit": False, "status": "not_requested"}}
    if envelope:
        try:
            if envelope.get("schema") != SCHEMA or envelope.get("version") != 1:
                raise ValueError("Invalid chain runtime envelope version")
            recipe = envelope["recipe"]
            if recipe.get("schema") != SCHEMA or recipe.get("version") != 1 or not 1 <= len(recipe["steps"]) <= 32:
                raise ValueError("Invalid chain envelope input recipe")
            if len(envelope["outputs"]) != len(recipe["steps"]) or len(envelope["expectations"]) != len(recipe["steps"]):
                raise ValueError("Incomplete chain envelope ownership/expectations")
            for original, expected, out in zip(recipe["steps"], envelope["expectations"], envelope["outputs"]):
                if original["id"] != expected["id"] or original["id"] != out["id"] or original["module"] != expected["module"]:
                    raise ValueError("Chain envelope identities differ")
                for key in ("sketch", "feature"):
                    if not out[key].get("reference") or not out[key].get("name"):
                        raise ValueError("Chain envelope owned reference is missing")
            if any(s["module"] in ("external_helical_thread", "internal_helical_thread") for s in recipe["steps"]):
                if (recipe["steps"][-1]["module"] not in ("external_helical_thread", "internal_helical_thread") or
                         any(s["module"] in ("external_helical_thread", "internal_helical_thread") for s in recipe["steps"][:-1]) or
                        envelope.get("thread_audit", {}).get("schema") != "geomwright.construction_chain.thread_audit"):
                    raise ValueError("Invalid terminal thread envelope/checkpoint")
            spline_steps = [s for s in recipe["steps"] if s["module"] == "straight_spline" and s["basis"] == "input"]
            if spline_steps and (len(spline_steps) != 1 or spline_steps[0] != recipe["steps"][-1] or
                    envelope.get("spline_audit", {}).get("schema") != "geomwright.construction_chain.spline_audit"):
                raise ValueError("Invalid terminal input spline envelope/checkpoint")
            result["recipe"] = recipe  # No runtime extras in the rebuild input.
            result["runtime_version"] = 1
            result["recipe_checksum"] = _hash(envelope)
            result["steps"] = result["outputs"] = envelope["outputs"]
            result["expectations"] = envelope["expectations"]
            result["verification_expectations"] = envelope.get("verification_expectations")
        except Exception as exc:
            result["recipe"] = None
            result["recipe_error"] = str(exc)
    if payload.get("verify_geometry") is True:
        try:
            if result["recipe"] is None or result["recipe_error"]:
                raise RuntimeError("Geometry audit requires a valid chain envelope")
            outputs = _ownership(b, b.cast_model_container(part), envelope["outputs"], document=doc)
            expected = envelope["expectations"]
            input_spline = expected[-1]["module"] == "straight_spline" and expected[-1]["basis"] == "input"
            if input_spline or expected[-1]["module"] in ("external_helical_thread", "internal_helical_thread"):
                plan = payload.get("plan") or {}
                checkpoint = (_spline_runtime() if input_spline else _thread_runtime()).validate_envelope(sys.modules[__name__], plan, envelope)
                body, verification = _final_audit(b, app, doc, plan, _validate(plan), checkpoint)
                result["verification"] = verification
                result["outputs_are_saved_creation_evidence"] = False
            else:
                gear = _foundation(expected)
                body = _read_body(b, app, doc, part, gear)
                result["verification"] = _verify(body, envelope["expectations"])
            result["steps"] = result["outputs"] = outputs
            result["body"] = body
        except Exception as exc:
            result["ok"] = False
            result["verification"] = {"verified": False, "fresh_geometry_audit": True, "error": str(exc)[:2000]}
    return result


def handle(action, payload, bridge):
    if action == "create_construction_chain":
        return create(payload, bridge)
    if action == "inspect_construction_chain":
        return inspect(payload, bridge)
    if action == "continue_construction_chain":
        return execute(payload, bridge, continuation=True)
    raise ValueError("Unsupported construction chain action")
