"""Explicit-carrier bolt-circle adapter and off-axis wall verification."""
import math
import re


def guard(step, original, close):
    p, s = original["parameters"], step["section"]
    n, r, pitch = p["count"], p["hole_diameter"]/2, p["bolt_circle_diameter"]/2
    if isinstance(n, bool) or not isinstance(n, int) or not 2 <= n <= 64 or min(r, p["depth"]) <= 0 or pitch*math.sin(math.pi/n) <= r:
        raise ValueError("Invalid or intersecting bolt-circle holes")
    if len(s["segments"]) != 1 or len(s.get("inner_segments", [])) != 1:
        raise ValueError("Bolt-circle radial exclusion envelope missing")
    for key in ("start_radius_mm", "end_radius_mm"):
        close(s["segments"][0][key], pitch+r)
        close(s["inner_segments"][0][key], pitch-r)
    close(s["hole_radius_mm"], r)
    close(s["axial_interval_mm"][1]-s["axial_interval_mm"][0], p["depth"])
    centres = s.get("hole_centers_yz_mm", [])
    if len(centres) != n:
        raise ValueError("Bolt-circle expected centre count differs")
    for j, point in enumerate(centres):
        if len(point) != 2:
            raise ValueError("Invalid hole centre")
        angle = math.radians(p["start_angle_degrees"])+2*math.pi*j/n
        close(point[0], pitch*math.cos(angle))
        close(point[1], pitch*math.sin(angle))
    preview, ns = step["preview"], "CH_"+step["id"].upper()
    params = preview["params"]
    name = "Bolt circle holes ["+step["id"]+"]"
    if step["namespace"] != ns or preview.get("scenario") != "bolt_circle_holes" or params.get("name") != name or params.get("parameter_prefix") != ns:
        raise ValueError("Bolt-circle identity differs")
    if any(k in params for k in ("source_scenario", "source_params", "source_preview")) or params.get("projections"):
        raise ValueError("Hidden bolt-circle carrier forbidden")
    for key, value in p.items():
        if params.get(key) != value:
            raise ValueError("Bolt-circle preview differs from recipe: "+key)
    for key in ("origin", "effective_origin"):
        if params.get("placement", {}).get(key) != [step["placement"]["origin_mm"], 0]:
            raise ValueError("Bolt-circle origin differs")
    operations = preview["operations"]
    allowed = {"add_variables", "create_pattern_axis_reference", "create_first_hole_lcs", "create_base_hole", "create_circular_pattern", "hide_auxiliary_geometry"}
    if len(operations) != len(allowed) or {o["operation"] for o in operations} != allowed:
        raise ValueError("Unsupported bolt-circle operations")
    hp = preview["base_hole_preview"]
    if hp.get("scenario") != "internal_cylindrical_step" or hp["params"].get("name") != name+" base hole" or hp["params"].get("parameter_prefix") != ns or not hp["params"].get("require_fully_defined"):
        raise ValueError("Invalid parameterized base hole")
    if hp["params"].get("rotation_axis_default_object_type") is not None or hp["params"].get("angle_degrees", 360) != 360 or any(k in hp["params"] for k in ("source_scenario", "source_params", "source_preview")):
        raise ValueError("Base hole must use its own local drawn axis without source recreation")
    kinds = {o["operation"] for o in hp["operations"]}
    if len(hp["operations"]) != 7 or kinds != {"create_sketch", "add_variables", "draw_axis", "draw_profile", "apply_constraints", "add_dimensions", "cut_rotation"}:
        raise ValueError("Unsupported base-hole operation")
    profile = next(o for o in hp["operations"] if o["operation"] == "draw_profile")
    expected = [[0, 0], [0, r], [step["placement"]["direction"]*p["depth"], r], [step["placement"]["direction"]*p["depth"], 0], [0, 0]]
    if len(profile["profile_points"]) != len(expected) or profile.get("profile_entities") or profile.get("construction_lines"):
        raise ValueError("Invalid base-hole profile")
    for a, c in zip(profile["profile_points"], expected):
        for x, y in zip(a, c):
            close(x, y)
    variables = {v["name"]: v["value"] for o in operations for v in o.get("variables", [])}
    drivers = {ns+"_D1": p["hole_diameter"], ns+"_L1": p["depth"], ns+"_PCD1": p["bolt_circle_diameter"], ns+"_N1": n, ns+"_A1": 360/n}
    if set(variables) != set(drivers):
        raise ValueError("Bolt-circle drivers differ")
    for key in variables:
        close(variables[key], drivers[key])
    for o in operations+hp["operations"]+[{"dimensions": [{"expression": e} for e in params.get("first_hole_offset_expressions", []) if e]}]:
        for row in o.get("dimensions", [])+o.get("variables", []):
            expression = str(row.get("expression") or "")
            expression = re.sub(r"\b\d+(?:\.\d*)?[eE][+-]?\d+\b", "0", expression)
            if any(not token.startswith(ns+"_") for token in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", expression)):
                raise ValueError("Bolt-circle expression escapes namespace")
    if params.get("pattern_count_expression") != ns+"_N1" or params.get("pattern_step_expression") != ns+"_A1":
        raise ValueError("Bolt-circle pattern driver differs")
    return n*math.pi*r*r*p["depth"]/1000


def build(b, part, model, step, reports):
    result = b._build_bolt_circle_holes_feature(part, model, step["preview"]["params"], step["preview"], reports, chain_mode=True)
    hole = result["base_hole"]
    objects = [("center", "Points3D", result["center_point"]), ("axis_tip", "Points3D", result["axis_tip_point"]),
        ("first_center", "Points3D", result["first_hole_center"]), ("lcs", "LocalCoordinateSystems", result["first_hole_lcs"]),
        ("axis", "Axes3D", result["pattern_axis"]), ("plane", "Planes3D", result["hole_plane"]),
        ("sketch", "Sketchs", hole["sketch"]), ("source_cut", "Rotateds", hole["rotated"]),
        ("pattern", "FeaturePatterns", result["pattern"])]
    owned = [{"role": role, "collection": collection, "name": b.safe_get(obj, "Name"), "reference": b.safe_get(obj, "Reference"),
              "require_fully_defined": True} for role, collection, obj in objects]
    out = {"id": step["id"], "namespace": step["namespace"], "section": step["section"],
        "sketch": dict(owned[6]), "feature": dict(owned[8]), "owned_objects": owned,
        "hole_pattern": {"count": len(step["section"]["hole_centers_yz_mm"]), "step_deg": 360/len(step["section"]["hole_centers_yz_mm"])},
        "variable_names": [v["name"] for o in step["preview"]["operations"] for v in o.get("variables", [])], "dimension_names": []}
    return {"owned_objects": [obj for _, _, obj in objects]}, out


def verify(body, steps, tolerance):
    expected = [dict(center_yz_mm=point, radius_mm=step["section"]["hole_radius_mm"],
        axial_min=step["section"]["axial_interval_mm"][0], axial_max=step["section"]["axial_interval_mm"][1])
        for step in steps if step["module"] == "bolt_circle_holes" for point in step["section"]["hole_centers_yz_mm"]]
    def covers(required, available):
        for p in required:
            spans = [(f["axial_min"], f["axial_max"]) for f in available
                if abs(f["radius_mm"]-p["radius_mm"]) <= tolerance and
                max(abs(a-c) for a, c in zip(p["center_yz_mm"], f["center_yz_mm"])) <= tolerance]
            cursor = p["axial_min"]
            for a, c in sorted(spans):
                if a > cursor+tolerance:
                    break
                cursor = max(cursor, c)
            if cursor < p["axial_max"]-tolerance:
                raise RuntimeError("Actual hole centre/radius/trimmed span differs from pattern")
    covers(expected, body.get("hole_faces", []))
    covers(body.get("hole_faces", []), expected)
