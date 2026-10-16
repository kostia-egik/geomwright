"""Polygon/flat-prism adapter for the bounded chain runtime; no CAD engine.

Conservative inscribed-core carriers are not cylindrical final surfaces.
Verify the actual lateral planes and exact transverse footprint instead.
"""
import math
import re


def vertices(parameters):
    n = parameters["side_count"]
    if isinstance(n, bool) or not isinstance(n, int) or not 3 <= n <= 64:
        raise ValueError("Polygon side count outside bounded range")
    d, length, angle = (float(parameters[k]) for k in ("diameter", "length", "rotation_angle_degrees"))
    if not all(math.isfinite(x) for x in (d, length, angle)) or min(d, length) <= 0:
        raise ValueError("Invalid polygon dimensions")
    mode = parameters["diameter_mode"]
    if mode not in ("inscribed_circle", "circumscribed_circle"):
        raise ValueError("Invalid polygon diameter interpretation")
    r = d/2 if mode == "circumscribed_circle" else d/(2*math.cos(math.pi/n))
    base = math.radians(angle) + math.pi/2 - math.pi/n
    return [[r*math.sin(base+2*math.pi*j/n), r*math.cos(base+2*math.pi*j/n)] for j in range(n)]


def guard(step, original, close):
    p = original["parameters"]
    flat = step["module"] == "external_flat_step"
    points = [] if flat else vertices(p)
    section = step["section"]
    actual = section.get("polygon_vertices_yz_mm", [])
    if len(actual) != len(points) or len(section.get("segments", [])) != 1 or section.get("carrier_role") != "inscribed_core":
        raise ValueError("Polygon footprint/carrier missing")
    for a, c in zip(actual, points):
        if len(a) != 2:
            raise ValueError("Invalid polygon footprint")
        for x, y in zip(a, c):
            close(x, y)
    radius = p["diameter"]/2 if flat else math.hypot(*points[0])
    if flat:
        depth, count = p["flat_depth"], p["flats_count"]
        if not 0 < depth < radius or count not in (1, 2):
            raise ValueError("Invalid flat dimensions/count")
        core = radius-depth
        levels = [-core] if count == 1 else [-core, core]
        if section.get("flat_levels_y_mm") != levels:
            raise ValueError("Flat levels differ from recipe")
        expected_bounds = [-core, -radius, radius if count == 1 else core, radius]
        if len(section.get("transverse_bounds_yz_mm", [])) != 4:
            raise ValueError("Flat footprint missing")
        for a, c in zip(section["transverse_bounds_yz_mm"], expected_bounds):
            close(a, c)
        chord = math.sqrt(depth*(2*radius-depth))
        half = core*chord+radius**2*math.asin(core/radius)
        volume = (math.pi*radius**2/2+half if count == 1 else 2*half)*p["length"]/1000
    else:
        core = radius*math.cos(math.pi/len(points))
        volume = len(points)*radius**2*math.sin(2*math.pi/len(points))*p["length"]/2000
    close(section["bounding_radius_mm"], radius)
    close(section["segments"][0]["start_radius_mm"], core)
    close(section["segments"][0]["end_radius_mm"], core)
    close(section["axial_interval_mm"][1]-section["axial_interval_mm"][0], p["length"])
    preview, namespace = step["preview"], step["namespace"]
    if namespace != "CH_"+step["id"].upper() or preview.get("scenario") != step["module"]:
        raise ValueError("Invalid polygon namespace/scenario")
    params = preview["params"]
    for key, value in p.items():
        if params.get(key) != value:
            raise ValueError("Polygon preview differs from recipe: " + key)
    if params.get("plane") != "YOZ" or params.get("axial_direction") != ("backward" if step["placement"]["direction"] == 1 else "forward"):
        raise ValueError("Invalid polygon plane/direction")
    close(params["flat_offset"] if flat else params["polygon_radius"], core if flat else radius)
    bindings = params.get("operation_variable_bindings", [])
    note = "Distance 2" if step["placement"]["direction"] == 1 else "Distance 1"
    if len(bindings) != 1 or bindings[0].get("expression") != namespace+"_L1" or bindings[0].get("parameter_note") != note:
        raise ValueError("Polygon extrusion driver binding differs from placement")
    label = "External flat" if flat else "External polygon"
    if params.get("name") != label+" ["+step["id"]+"]" or params.get("sketch_name") != params["name"]+" profile" or params.get("parameter_prefix") != namespace or not params.get("fix_sketch_placement"):
        raise ValueError("Invalid polygon identity/placement")
    kinds = [op["operation"] for op in preview["operations"]]
    draw = "draw_flat_profile" if flat else "draw_regular_polygon"
    expected = {"create_sketch", draw, "apply_constraints", "add_dimensions", "add_variables", "boss_extrusion"}
    if set(kinds) != expected or len(kinds) != len(expected):
        raise ValueError("Unsupported polygon chain operations")
    profile = next(op for op in preview["operations"] if op["operation"] == draw)
    drawn = [] if flat else profile["vertices"]
    if len(drawn) != len(points):
        raise ValueError("Polygon profile differs from section")
    for local, global_yz in zip(drawn, points):
        close(local[0], global_yz[1])
        close(local[1], global_yz[0])
    if any(k in params for k in ("source_scenario", "source_preview", "source_params")) or params.get("projections") or preview.get("interface"):
        raise ValueError("Hidden polygon source forbidden")
    for op in preview["operations"]:
        for var in op.get("variables", []):
            if not str(var["name"]).startswith(namespace+"_") or not math.isfinite(float(var["value"])):
                raise ValueError("Polygon variable escapes namespace")
        for row in op.get("variables", []) + op.get("dimensions", []) + op.get("operation_variable_bindings", []):
            expression = row.get("expression")
            if expression is not None and any(not token.startswith(namespace+"_") for token in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", str(expression))):
                raise ValueError("Polygon expression escapes namespace")
    variables = {v["name"]: v["value"] for op in preview["operations"] for v in op.get("variables", [])}
    suffixes = ("D1", "L1", "F1" if flat else "A1")
    if set(variables) != {namespace+"_"+suffix for suffix in suffixes}:
        raise ValueError("Polygon requires isolated diameter/length/orientation drivers")
    for suffix, field in (("D1", "diameter"), ("L1", "length"), ("F1", "flat_depth") if flat else ("A1", "rotation_angle_degrees")):
        close(variables[namespace+"_"+suffix], p[field])
    return volume


def build(b, part, model, step, reports):
    origin = step["placement"]["origin_mm"]
    name = step["preview"]["params"]["name"]
    point = b._create_point3d(model, name+" origin", [origin, 0, 0])
    plane = b._create_plane_parallel_by_point(part, name+" profile plane", part.DefaultObject(3), point)
    builder = b._build_flat_step_feature if step["module"] == "external_flat_step" else b._build_polygonal_step_feature
    built = builder(part, model, step["preview"]["params"], step["preview"], reports, plane_override=plane)
    feature = built["extrusion"]
    feature.Name = name+" extrusion"
    if not feature.Update():
        raise RuntimeError("Polygon canonical extrusion name update failed")
    objects = [("origin", "Points3D", point), ("plane", "Planes3D", plane),
               ("sketch", "Sketchs", built["sketch"]), ("feature", "Extrusions", feature)]
    owned = [{"role": role, "collection": collection, "name": b.safe_get(obj, "Name"),
              "reference": b.safe_get(obj, "Reference"), "require_fully_defined": True}
             for role, collection, obj in objects]
    built["owned_objects"] = [obj for _, _, obj in objects]
    out = {"id": step["id"], "namespace": step["namespace"], "section": step["section"],
           "owned_objects": owned, "sketch": dict(owned[2]), "feature": dict(owned[3]),
           "variable_names": [v["name"] for op in step["preview"]["operations"] for v in op.get("variables", [])],
           "dimension_names": []}
    return built, out


def planes(points):
    result = []
    for a, c in zip(points, points[1:]+points[:1]):
        dy, dz = c[0]-a[0], c[1]-a[1]
        length = math.hypot(dy, dz)
        normal = [dz/length, -dy/length]
        h = sum(x*y for x, y in zip(normal, a))
        if h < 0:
            normal, h = [-x for x in normal], -h
        result.append({"normal_yz": normal, "offset_mm": h})
    return result


def verify(body, steps, tolerance):
    expected = []
    for step in steps:
        section = step["section"]
        sides = (planes(section["polygon_vertices_yz_mm"]) if "polygon_vertices_yz_mm" in section else
            [{"normal_yz": [-1 if level < 0 else 1, 0], "offset_mm": abs(level)} for level in section.get("flat_levels_y_mm", [])])
        for plane in sides:
            expected.append(dict(plane, axial_min=section["axial_interval_mm"][0], axial_max=section["axial_interval_mm"][1]))
    actual = body.get("lateral_planes", [])
    def covers(required, available):
        for p in required:
            intervals = []
            for f in available:
                if abs(p["offset_mm"]-f["offset_mm"]) <= tolerance and max(abs(a-c) for a, c in zip(p["normal_yz"], f["normal_yz"])) <= 1e-7:
                    intervals.append((f["axial_min"], f["axial_max"]))
            cursor = p["axial_min"]
            for a, c in sorted(intervals):
                if a > cursor+tolerance:
                    break
                cursor = max(cursor, c)
            if cursor < p["axial_max"]-tolerance:
                raise RuntimeError("Polygon lateral plane/span mismatch")
    covers(expected, actual)
    covers(actual, expected)


def bounds(steps):
    footprints = []
    for step in steps:
        if step["material"] == "remove":
            continue
        s = step["section"]
        if "polygon_vertices_yz_mm" in s:
            p = s["polygon_vertices_yz_mm"]
            footprints.append([min(v[0] for v in p), min(v[1] for v in p), max(v[0] for v in p), max(v[1] for v in p)])
        elif "transverse_bounds_yz_mm" in s:
            footprints.append(s["transverse_bounds_yz_mm"])
        else:
            r = max(max(v["start_radius_mm"], v["end_radius_mm"]) for v in s["segments"])
            footprints.append([-r, -r, r, r])
    return [min(p[0] for p in footprints), min(p[1] for p in footprints), max(p[2] for p in footprints), max(p[3] for p in footprints)]
