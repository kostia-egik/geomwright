"""Source-free terminal metric thread application and persisted native audit.

The chain runtime owns prefix/context and grouping. The family bridge owns the
profile and sweep. This adapter verifies actual removal and only newly created
roots; the owning chain runtime saves the accepted envelope and document.
"""
import json
import math
import re
from copy import deepcopy


COLLECTIONS = ("Sketchs", "Rotateds", "Extrusions", "Evolutions", "FeaturePatterns",
               "Points3D", "Axes3D", "Spirals3D", "Planes3D", "LocalCoordinateSystems", "MacroObjects3D")


def _inventory(b, runtime, model):
    result = {}
    for name in COLLECTIONS:
        rows = list(b.iter_collection(runtime._collection(b, model, name)))
        if len(rows) > 256:
            raise RuntimeError("Thread root inventory budget exceeded")
        result[name] = {b.safe_get(obj, "Reference"): obj for obj in rows}
        if None in result[name] or len(result[name]) != len(rows):
            raise RuntimeError("Thread root inventory has missing/duplicate identities")
    return result


def snapshot(b, runtime, app, doc, guard, params):
    """Bounded native trimmed-edge and analytical protected-face evidence."""
    metrics = runtime._exact_document_body_metrics(b, app, doc)
    bodies = b._ensure_dispatch_sequence(b._cast_to_com_interface(doc.TopPart, "IFeature7").ResultBodies)
    if len(bodies) != 1:
        raise RuntimeError("Thread result requires one final body")
    body = b._cast_to_com_interface(bodies[0], "IBody7")
    box = body.GetGabarit()
    if not isinstance(box, tuple) or len(box) != 7 or not box[0]:
        raise RuntimeError("Thread final body bounds unavailable")
    if metrics["body_count"] != 1 or not metrics["solid"] or runtime._number(metrics["volume"]) <= 0:
        raise RuntimeError("Thread result is not one positive solid")
    lo, hi = guard["working_span_mm"]
    blind = guard.get("scope") == "blind_external_metric_cylinder_positive_x"
    through = guard.get("scope") == "through_external_metric_cylinder_positive_x"
    internal_blind = guard.get("scope") == "blind_internal_metric_cylinder_positive_x"
    internal = internal_blind or guard.get("scope") == "complete_internal_metric_cylinder_positive_x"
    physical_end = guard["carrier_span_mm"][1] if internal_blind else hi
    stock_end = guard.get("stock_span_mm", [lo, physical_end])[1]
    bottom = internal_blind and guard["end_plan"]["bore_has_bottom"]
    ending = blind or through or internal
    radius, root = ((guard["major_radius_mm"], guard["bore_radius_mm"]) if internal else
                    (guard["carrier_radius_mm"], guard["root_radius_mm"]))
    tolerance = 1e-5
    count = max(65, int(math.ceil((hi-lo)/params["pitch"]))*16+1)
    protected, helices, root_radii, seen = [], [], [], set()
    terminal_sections = []
    faces = b._ensure_dispatch_sequence(b._cast_to_com_interface(body, "IFeature7").ModelObjects(6))
    if not 1 <= len(faces) <= 256:
        raise RuntimeError("Thread face readback budget exceeded")
    point_budget = 0
    for obj in faces:
        face = b._cast_to_com_interface(obj, "IFace")
        cylinder = bool(b.safe_get(face, "IsCylinder", False))
        cone = bool(b.safe_get(face, "IsCone", False))
        plane = bool(b.safe_get(face, "IsPlanar", False))
        axial_plane = False
        if ending and plane:
            surface = b._cast_to_com_interface(face.MathSurface, "IMathSurface3D")
            normal = runtime._point_result(surface.GetNormal((surface.ParamUMin+surface.ParamUMax)/2,
                                                             (surface.ParamVMin+surface.ParamVMax)/2))
            axial_plane = abs(normal[0]) > 1e-9 and math.hypot(*normal[1:]) <= abs(normal[0])*1e-9
        # Rear cylinders/cones are unthreaded. Fine angular sampling is required
        # for helix witnesses, not their closed circular boundaries.
        n = 9 if cone or cylinder and float(face.Radius) < root-tolerance else count
        edges = b._ensure_dispatch_sequence(face.LimitingEdges)
        if len(edges) > 64:
            raise RuntimeError("Thread face boundary budget exceeded")
        coords = []
        for edge in edges:
            curve = b._cast_to_com_interface(edge.MathCurve, "IMathCurve3D")
            a, c = runtime._number(curve.ParamMin), runtime._number(curve.ParamMax)
            point_budget += n
            if point_budget > 65536:
                raise RuntimeError("Thread native sample budget exceeded")
            points = [runtime._point_result(curve.GetPoint(a+(c-a)*i/(n-1))) for i in range(n)]
            coords.extend(points)
            for point in points:
                r = math.hypot(point[1], point[2])
                working = lo-tolerance <= point[0] <= hi+tolerance and root-tolerance <= r <= radius+tolerance
                rear = point[0] <= lo+tolerance and r < root-tolerance
                protected_point = False
                if internal and not working:
                    protected_point = lo-tolerance <= point[0] <= stock_end+tolerance and (
                        cylinder and abs(r-guard["outer_radius_mm"]) <= tolerance or
                        internal_blind and cylinder and hi-tolerance <= point[0] <= physical_end+tolerance and abs(r-root) <= tolerance or
                        axial_plane and abs(point[0]-lo) <= tolerance and root-tolerance <= r <= guard["outer_radius_mm"]+tolerance or
                        axial_plane and abs(point[0]-physical_end) <= tolerance and
                        (abs(r-root) <= tolerance if bottom else root-tolerance <= r <= guard["outer_radius_mm"]+tolerance) or
                        bottom and axial_plane and abs(point[0]-stock_end) <= tolerance and abs(r-guard["outer_radius_mm"]) <= tolerance)
                elif ending and not working:
                    for segment in guard["stock_envelope_segments"]:
                        a0, a1 = segment["axial_min"], segment["axial_max"]
                        if a0-tolerance <= point[0] <= a1+tolerance:
                            t = min(1, max(0, (point[0]-a0)/(a1-a0)))
                            expected_r = segment["start_radius_mm"]+t*(segment["end_radius_mm"]-segment["start_radius_mm"])
                            protected_point = protected_point or ((cylinder or cone) and abs(r-expected_r) <= tolerance)
                            protected_point = protected_point or (axial_plane and min(abs(point[0]-a0), abs(point[0]-a1)) <= tolerance and r <= expected_r+tolerance)
                if not working and not (protected_point if ending else rear):
                    raise RuntimeError("Thread boundary escapes working shell or protected rear stock")
            ref = b.safe_get(edge, "Reference")
            if not ref or ref in seen:
                continue
            seen.add(ref)
            if len(seen) > 512:
                raise RuntimeError("Thread unique edge budget exceeded")
            if all(lo-tolerance <= p[0] <= hi+tolerance and math.hypot(p[1], p[2]) >= root-tolerance and
                   (not internal or math.hypot(p[1], p[2]) <= radius+tolerance) for p in points):
                root_radii.extend(math.hypot(p[1], p[2]) for p in points)
                evidence = b._metric_helix_edge_evidence(points, params["pitch"], params["left_thread"])
                if evidence is not None:
                    if internal:
                        evidence["reference"] = ref
                    helices.append(evidence)
        if not coords:
            raise RuntimeError("Thread final face has no trimmed boundaries")
        x0, x1 = min(p[0] for p in coords), max(p[0] for p in coords)
        r0, r1 = min(math.hypot(p[1], p[2]) for p in coords), max(math.hypot(p[1], p[2]) for p in coords)
        if ending and plane and not axial_plane:
            terminal_sections.append({"x_span_mm": [x0, x1], "radius_bounds_mm": [r0, r1],
                                      "area_mm2": runtime._number(face.GetArea(1))})
        protect_internal = internal and cylinder and abs(r0-guard["outer_radius_mm"]) <= tolerance and abs(r1-guard["outer_radius_mm"]) <= tolerance
        if internal_blind and axial_plane and any(abs(x0-end) <= tolerance and abs(x1-end) <= tolerance
                for end in ((physical_end, stock_end) if bottom else (physical_end,))):
            protect_internal = True
        if protect_internal or (not internal and ((x1 <= lo+tolerance and r1 < root-tolerance) or
                (ending and x0 >= hi-tolerance and (blind or r1 < root-tolerance)))):
            if not (cylinder or cone or plane):
                raise RuntimeError("Protected stock contains an unexpected curved surface")
            protected.append({"kind": "cylinder" if cylinder else "cone" if cone else "plane",
                              "x_span_mm": [round(x0, 6), round(x1, 6)],
                              "radius_bounds_mm": [round(r0, 6), round(r1, 6)],
                              "area_mm2": round(runtime._number(face.GetArea(1)), 5)})
    result = {"body_count": 1, "volume_cm3": metrics["volume"], "bounds_mm": list(box[1:]),
            "protected_faces": sorted(protected, key=lambda row: json.dumps(row, sort_keys=True)),
            "helix_edges": helices, "minimum_working_radius_mm": min(root_radii) if root_radii else None,
            "sampled_geometry": True, "native_point_count": point_budget,
             "protected_representation": "analytical_face_area_rounded_1e-5_mm2_bounds_1e-6_mm"}
    if ending:
        result["terminal_sections"] = terminal_sections
    if internal:
        result["maximum_working_radius_mm"] = max(root_radii) if root_radii else None
    return result


def verify(runtime, before, after, guard):
    for body in (before, after):
        if body.get("body_count") != 1 or len(body.get("bounds_mm", [])) != 6:
            raise ValueError("Thread audit requires one body and six finite bounds")
        if runtime._number(body["volume_cm3"]) <= 0:
            raise ValueError("Thread audit requires positive finite volume")
        for value in body["bounds_mm"]:
            runtime._number(value)
    for a, c in zip(after["bounds_mm"], before["bounds_mm"]):
        runtime._close(a, c, floor=1e-5)
    if after["protected_faces"] != before["protected_faces"]:
        raise RuntimeError("Physical thread changed protected stock")
    if guard.get("scope") in ("complete_internal_metric_cylinder_positive_x", "blind_internal_metric_cylinder_positive_x"):
        return _verify_internal(runtime, before, after, guard)
    lo, hi = guard["working_span_mm"]
    radius, root = guard["carrier_radius_mm"], guard["root_radius_mm"]
    helices = after["helix_edges"]
    blind = guard.get("scope") == "blind_external_metric_cylinder_positive_x"
    through = guard.get("scope") == "through_external_metric_cylinder_positive_x"
    coverage_end = guard["end_plan"]["conservative_profile_projection_end_mm"] if blind else hi
    if len(helices) < 2 or not any(e["axial_min_mm"] <= lo+1e-5 and e["axial_max_mm"] >= coverage_end-1e-5 for e in helices):
        raise RuntimeError("Thread helical boundaries do not cover selected carrier")
    if after["minimum_working_radius_mm"] is None:
        raise RuntimeError("Thread root depth readback unavailable")
    runtime._close(after["minimum_working_radius_mm"], root, floor=1e-4)
    removed = runtime._number(before["volume_cm3"])-runtime._number(after["volume_cm3"])
    upper = math.pi*(radius*radius-root*root)*(hi-lo)/1000
    if not 1e-6 < removed <= upper+1e-6:
        raise RuntimeError("Thread removal is outside the selected outer-shell volume bound")
    result = {"verified": True, "removed_cm3": removed, "outer_shell_upper_bound_cm3": upper,
            "working_span_mm": [lo, hi], "protected_face_count": len(after["protected_faces"]),
              "sampled_geometry": True, "saved_recipe_updated": False}
    if blind:
        sections = after.get("terminal_sections", [])
        if len(sections) != 1:
            raise RuntimeError("Blind thread needs exactly one native terminal section")
        actual = sections[0]
        if len(actual.get("x_span_mm", [])) != 2 or len(actual.get("radius_bounds_mm", [])) != 2:
            raise ValueError("Invalid blind terminal section evidence")
        for a, expected in zip(actual["x_span_mm"], guard["end_plan"]["terminal_section_projection_mm"]):
            runtime._close(runtime._number(a), expected, floor=1e-5)
        runtime._close(runtime._number(actual["radius_bounds_mm"][0]), root, floor=1e-4)
        runtime._close(runtime._number(actual["radius_bounds_mm"][1]), radius, floor=1e-4)
        if runtime._number(actual["area_mm2"]) <= 0:
            raise ValueError("Blind terminal section area must be positive")
        result["end_characteristics"] = {
            "exit_mode": "blind", "last_cut_trace_mm": actual["x_span_mm"][1],
            "terminal_section_projection_mm": list(actual["x_span_mm"]),
            "partial_terminal_projection_width_mm": actual["x_span_mm"][1]-actual["x_span_mm"][0],
            "smooth_tail_mm": guard["carrier_span_mm"][1]-actual["x_span_mm"][1],
            "functional_thread_length_verified": False, "controlled_runout": False}
    if through:
        if after.get("terminal_sections") != []:
            raise RuntimeError("Through thread must not retain a material terminal section")
        full = [e for e in helices if e["axial_min_mm"] <= lo+1e-5 and e["axial_max_mm"] >= hi-1e-5]
        top = [e for e in full if abs(runtime._number(e["radius_mm"])-radius) <= 1e-5]
        tangent = [e for e in full if abs(runtime._number(e["radius_mm"])-guard["root_tangent_radius_mm"]) <= 1e-5]
        if len(top) < 2 or len(tangent) < 2:
            raise RuntimeError("Through exit requires two full-span top and two root-tangent boundaries")
        result["end_characteristics"] = {
            "exit_mode": "through", "last_cut_trace_mm": max(e["axial_max_mm"] for e in top+tangent),
            "cutter_terminal_section_projection_mm": list(guard["end_plan"]["terminal_section_projection_mm"]),
            "cutter_projection_is_planned": True, "material_terminal_section_present": False,
            "partial_terminal_projection_width_mm": 0,
            "full_contour_boundary_coverage_verified": True,
            "full_top_boundary_count": len(top), "full_root_tangent_boundary_count": len(tangent),
            "functional_thread_length_verified": False, "controlled_runout": False}
    return result


def _verify_internal(runtime, before, after, guard):
    """Internal shell and four-boundary audit, not a manufacturing certificate."""
    lo, hi = guard["working_span_mm"]
    inner, major = guard["bore_radius_mm"], guard["major_radius_mm"]
    blind = guard.get("scope") == "blind_internal_metric_cylinder_positive_x"
    physical_end = guard["carrier_span_mm"][1] if blind else hi
    protected = before["protected_faces"]
    _validate_internal_protected(runtime, protected, guard)
    runtime._close(runtime._number(after["minimum_working_radius_mm"]), inner, floor=1e-4)
    runtime._close(runtime._number(after["maximum_working_radius_mm"]), major, floor=1e-4)
    if not blind and after.get("terminal_sections") != []:
        raise RuntimeError("Internal through thread retains a material terminal section")
    helices = after["helix_edges"]
    for edge in helices:
        for key in ("axial_min_mm", "axial_max_mm", "radius_mm", "signed_lead_mm"):
            runtime._number(edge[key])
        if not lo-1e-5 <= edge["axial_min_mm"] < edge["axial_max_mm"] <= hi+1e-5 or not inner-1e-5 <= edge["radius_mm"] <= major+1e-5:
            raise RuntimeError("Internal helical boundary escapes the working shell/span")
    coverage_end = guard["end_plan"]["conservative_profile_projection_end_mm"] if blind else hi
    full = [e for e in helices if e["axial_min_mm"] <= lo+1e-5 and e["axial_max_mm"] >= coverage_end-1e-5]
    bore = [e for e in full if abs(e["radius_mm"]-inner) <= 1e-5]
    tangent = [e for e in full if abs(e["radius_mm"]-guard["root_tangent_radius_mm"]) <= 1e-5]
    refs = [e.get("reference") for e in bore+tangent]
    if len(bore) != 2 or len(tangent) != 2 or not all(refs) or len(set(refs)) != 4:
        raise RuntimeError("Internal through thread requires four distinct full-span boundaries")
    removed = runtime._number(before["volume_cm3"])-runtime._number(after["volume_cm3"])
    if not 1e-6 < removed <= guard["removal_upper_bound_cm3"]+1e-6:
        raise RuntimeError("Internal thread removal escapes the allowed inner shell")
    result = {"verified": True, "removed_cm3": removed, "inner_shell_upper_bound_cm3": guard["removal_upper_bound_cm3"],
        "working_span_mm": [lo, hi], "protected_face_count": len(protected), "sampled_geometry": True,
        "full_bore_boundary_count": 2, "full_root_tangent_boundary_count": 2,
        "material_terminal_section_present": False, "functional_thread_length_verified": False,
        "controlled_runout": False, "saved_recipe_updated": False}
    if blind:
        sections = after.get("terminal_sections", [])
        if len(sections) != 1:
            raise RuntimeError("Blind internal thread requires one material terminal section")
        actual = sections[0]
        if len(actual.get("x_span_mm", [])) != 2 or len(actual.get("radius_bounds_mm", [])) != 2:
            raise ValueError("Invalid internal terminal section readback")
        for value, expected in zip(actual["x_span_mm"], guard["end_plan"]["terminal_section_projection_mm"]):
            runtime._close(runtime._number(value), expected, floor=1e-5)
        for value, expected in zip(actual["radius_bounds_mm"], (inner, major)):
            runtime._close(runtime._number(value), expected, floor=1e-4)
        if runtime._number(actual["area_mm2"]) <= 0:
            raise ValueError("Internal terminal section must have positive area")
        result["material_terminal_section_present"] = True
        result["end_characteristics"] = {"exit_mode": "blind", "last_cut_trace_mm": actual["x_span_mm"][1],
            "terminal_section_projection_mm": list(actual["x_span_mm"]),
            "partial_terminal_projection_width_mm": actual["x_span_mm"][1]-actual["x_span_mm"][0],
            "smooth_tail_mm": physical_end-actual["x_span_mm"][1],
            "functional_thread_length_verified": False, "controlled_runout": False}
        if guard["end_plan"]["bore_has_bottom"]:
            result["end_characteristics"].update(bore_has_bottom=True,
                gap_to_bottom_mm=physical_end-actual["x_span_mm"][1],
                bottom_stock_thickness_mm=guard["stock_span_mm"][1]-physical_end)
    return result


def _validate_internal_protected(runtime, protected, guard):
    blind = guard.get("scope") == "blind_internal_metric_cylinder_positive_x"
    bottom = blind and guard["end_plan"]["bore_has_bottom"]
    physical = guard.get("stock_span_mm", guard.get("carrier_span_mm", guard["working_span_mm"]))
    cylinders = [f for f in protected if f.get("kind") == "cylinder"]
    if (len(protected) != (3 if bottom else 2 if blind else 1) or len(cylinders) != 1 or
            len(cylinders[0].get("x_span_mm", [])) != 2 or len(cylinders[0].get("radius_bounds_mm", [])) != 2):
        raise ValueError("Internal audit needs the complete protected stock baseline")
    for value, expected in zip(cylinders[0]["x_span_mm"], physical):
        runtime._close(runtime._number(value), expected, floor=1e-5)
    for value in cylinders[0]["radius_bounds_mm"]:
        runtime._close(runtime._number(value), guard["outer_radius_mm"], floor=1e-5)
    runtime._close(runtime._number(cylinders[0]["area_mm2"]),
                   2*math.pi*guard["outer_radius_mm"]*(physical[1]-physical[0]), floor=1e-4)
    if blind:
        _validate_internal_exit_face(runtime, protected, guard)


def _validate_internal_exit_face(runtime, protected, guard):
    planes = [f for f in protected if f.get("kind") == "plane"]
    if guard["end_plan"]["bore_has_bottom"]:
        if len(planes) != 2 or any(len(f.get("x_span_mm", [])) != 2 or
                                  len(f.get("radius_bounds_mm", [])) != 2 for f in planes):
            raise ValueError("Flat-bottom checkpoint needs both bottom and rear disks")
        planes = sorted(planes, key=lambda f: runtime._number(f["x_span_mm"][0]))
        for face, x, radius in zip(planes, (guard["carrier_span_mm"][1], guard["stock_span_mm"][1]),
                                   (guard["bore_radius_mm"], guard["outer_radius_mm"])):
            for value in face["x_span_mm"]:
                runtime._close(runtime._number(value), x, floor=1e-5)
            # Trimmed disk boundaries lie on the rim, not at its filled centre.
            for value in face["radius_bounds_mm"]:
                runtime._close(runtime._number(value), radius, floor=1e-5)
            runtime._close(runtime._number(face["area_mm2"]), math.pi*radius**2, floor=1e-4)
        return
    if len(planes) != 1 or len(planes[0].get("x_span_mm", [])) != 2 or len(planes[0].get("radius_bounds_mm", [])) != 2:
        raise ValueError("Blind internal checkpoint needs the protected bore exit annulus")
    for value in planes[0]["x_span_mm"]:
        runtime._close(runtime._number(value), guard["carrier_span_mm"][1], floor=1e-5)
    for value, expected in zip(planes[0]["radius_bounds_mm"], (guard["bore_radius_mm"], guard["outer_radius_mm"])):
        runtime._close(runtime._number(value), expected, floor=1e-5)
    runtime._close(runtime._number(planes[0]["area_mm2"]),
                   math.pi*(guard["outer_radius_mm"]**2-guard["bore_radius_mm"]**2), floor=1e-4)


CHECKPOINT_SCHEMA = "geomwright.construction_chain.thread_audit"


def _validate_end_characteristics(runtime, guard, actual):
    """Bind compact native endpoint evidence to the planned projection."""
    plan = guard["end_plan"]
    if (actual.get("exit_mode") != plan["exit_mode"] or actual.get("controlled_runout") is not False or
            actual.get("functional_thread_length_verified") is not False):
        raise ValueError("Invalid checkpoint end characteristics")
    if plan["exit_mode"] == "through":
        if (actual.get("cutter_projection_is_planned") is not True or
                actual.get("material_terminal_section_present") is not False or
                actual.get("full_contour_boundary_coverage_verified") is not True or
                runtime._number(actual["full_top_boundary_count"]) < 2 or
                runtime._number(actual["full_root_tangent_boundary_count"]) < 2):
            raise ValueError("Invalid through checkpoint full-contour evidence")
        projection = actual.get("cutter_terminal_section_projection_mm", [])
        if len(projection) != 2:
            raise ValueError("Invalid through checkpoint cutter projection")
        for value, expected in zip(projection, plan["terminal_section_projection_mm"]):
            runtime._close(runtime._number(value), expected, floor=1e-5)
        runtime._close(runtime._number(actual["last_cut_trace_mm"]), plan["last_cut_trace_mm"], floor=1e-5)
        runtime._close(runtime._number(actual["partial_terminal_projection_width_mm"]), 0, floor=1e-5)
        return
    span = actual.get("terminal_section_projection_mm", [])
    if len(span) != 2:
        raise ValueError("Invalid blind checkpoint terminal projection")
    for value, expected in zip(span, plan["terminal_section_projection_mm"]):
        runtime._close(runtime._number(value), expected, floor=1e-5)
    for key, expected in (("last_cut_trace_mm", plan["last_cut_trace_mm"]),
                          ("partial_terminal_projection_width_mm", plan["partial_terminal_projection_width_mm"]),
                          ("smooth_tail_mm", guard["carrier_span_mm"][1]-plan["last_cut_trace_mm"])):
        runtime._close(runtime._number(actual[key]), expected, floor=1e-5)
    if guard.get("scope") == "blind_internal_metric_cylinder_positive_x" and plan["bore_has_bottom"]:
        if actual.get("bore_has_bottom") is not True:
            raise ValueError("Flat-bottom checkpoint lacks bottom evidence")
        for key, expected in (("gap_to_bottom_mm", plan["smooth_bore_tail_mm"]),
                              ("bottom_stock_thickness_mm", plan["bottom_stock_thickness_mm"])):
            if runtime._number(actual[key]) <= 0:
                raise ValueError("Flat-bottom gap and rear stock must remain positive")
            runtime._close(actual[key], expected, floor=1e-5)


def validate_plan(runtime, plan):
    """Terminal-only thread wrapper around the unchanged analytic prefix gate."""
    if plan.get("schema") != "geomwright.construction_chain.plan" or plan.get("version") != 1:
        raise ValueError("Invalid thread chain plan version")
    steps, recipe = plan["steps"], plan["recipe"]
    modules = ("external_helical_thread", "internal_helical_thread")
    if not 2 <= len(steps) <= 32 or steps[-1]["module"] not in modules or any(s["module"] in modules for s in steps[:-1]):
        raise ValueError("Metric thread must be the sole terminal step")
    prefix = plan["thread_prefix_plan"]
    if recipe.get("schema") != runtime.SCHEMA or recipe.get("version") != 1:
        raise ValueError("Invalid thread chain recipe")
    if prefix["recipe"] != {**recipe, "steps": recipe["steps"][:-1]} or prefix["steps"] != steps[:-1]:
        raise ValueError("Thread analytic prefix differs from combined plan")
    step, original = steps[-1], recipe["steps"][-1]
    if (step["id"] != original["id"] or step["module"] != original["module"] or
            step["basis"] != "input" or step["material"] != "remove" or
            original["basis"] != "input" or original["material"] != "remove" or
            step["target"] != original["target"] or step["namespace"] != "CH_"+step["id"].upper() or
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", step["id"]) or
            step["id"].upper() in {s["id"].upper() for s in steps[:-1]}):
        raise ValueError("Invalid terminal thread identity/mode")
    preview, guard = step["preview"], step["thread_guard"]
    params, request = preview["params"], original["parameters"]
    internal = step["module"] == "internal_helical_thread"
    required = {"diameter", "pitch", "length", "direction"}
    if (not required <= set(request) or set(request)-required-{"entry_mode", "exit_mode"}-({"method_version"} if internal else set()) or
            request["direction"] not in ("right", "left") or
            "entry_mode" in request and request["entry_mode"] != "through" or
            "exit_mode" in request and request["exit_mode"] not in ("blind", "through")):
        raise ValueError("Unsupported terminal metric thread inputs")
    if internal and (request.get("method_version") != 1 or request.get("entry_mode") != "through" or request.get("exit_mode") not in ("through", "blind")):
        raise ValueError("Internal metric thread requires version-1 through entry and explicit through/blind exit")
    scope = (("blind_internal_metric_cylinder_positive_x" if request["exit_mode"] == "blind" else "complete_internal_metric_cylinder_positive_x") if internal else request["exit_mode"]+"_external_metric_cylinder_positive_x" if "exit_mode" in request else "complete_exposed_external_metric_cylinder_positive_x")
    if guard.get("scope") != scope:
        raise ValueError("Public thread chain still requires the carrier scope selected by exit_mode")
    (runtime._internal_metric_carrier_guard if internal else runtime._thread_carrier_guard)(prefix, guard, params)
    for key in ("diameter", "pitch", "length"):
        runtime._close(runtime._number(request[key]), params[key])
    if bool(params["left_thread"]) != (request["direction"] == "left"):
        raise ValueError("Thread family hand differs from recipe")
    placement = original["placement"]
    if (placement.get("reference") != {"step": step["target"], "anchor": "start"} or
            placement.get("direction") != 1 or placement.get("offset_mm") != 0 or
            placement.get("axis") != "global_x" or placement.get("phase_degrees") != 0):
        raise ValueError("Thread placement must use target start on +X without offset")
    lo, hi = guard["working_span_mm"]
    if step["placement"] != {"origin_mm": lo, "direction": 1} or guard["target" if internal else "target_step_id"] != step["target"]:
        raise ValueError("Thread target/placement differs from carrier guard")
    if preview.get("scenario") != step["module"] or params.get("profile_root_shape") != "round" or params.get("parameter_prefix") != step["namespace"]:
        raise ValueError("Thread requires the namespaced round metric family selected by its module")
    if any(key in params for key in ("source_scenario", "source_params", "source_preview", "source_variable_bindings")):
        raise ValueError("Thread chain plan must not contain source construction")
    label = "Physical thread ["+step["id"]+"]"
    for key, suffix in (("feature_display_name", " cut"), ("profile_display_name", " profile"),
                        ("path_display_name", " spiral"), ("axis_display_name", " axis"),
                        ("start_center_name", " start centre"), ("profile_origin_name", " profile origin")):
        if params[key] != label+suffix:
            raise ValueError("Thread canonical names differ from instance identity")
    section = step["section"]
    expected = {"axis": "global_x", "phase_degrees": 0, "axial_interval_mm": [lo, hi],
                "start_mm": lo, "end_mm": hi, "shape": step["module"], "material_role": "removed"}
    for key, value in expected.items():
        if section.get(key) != value:
            raise ValueError("Thread working section differs from carrier guard")
    radii = (("segments", guard["major_radius_mm"]), ("inner_segments", guard["bore_radius_mm"])) if internal else (("segments", guard["carrier_radius_mm"]), ("inner_segments", guard["root_radius_mm"]))
    for key, radius in radii:
        rows = runtime._segments({"segments": section[key]})
        if len(rows) != 1:
            raise ValueError("Thread working section requires one radial shell")
        for key2, value in (("axial_min", lo), ("axial_max", hi), ("start_radius_mm", radius), ("end_radius_mm", radius)):
            runtime._close(rows[0][key2], value)
    if any(value is not None for value in (step["expected_delta_cm3"], step["expected_total_volume_cm3"], plan["expected_total_volume_cm3"])):
        raise ValueError("Thread volume must be audited natively, not predicted analytically")
    if plan.get("expected_body_count") != 1:
        raise ValueError("Thread chain requires one body")
    runtime._bounded({"schema": runtime.SCHEMA, "version": 1, "recipe": recipe,
                      "expectations": runtime._expectations(steps), "outputs": []})
    return steps


def _compact_outputs(outputs):
    """Persist native identities, not transient COM reports or sampled curves."""
    result = []
    for out in outputs:
        row = {key: deepcopy(out[key]) for key in ("id", "namespace", "sketch", "feature", "macro", "owned_objects") if key in out}
        roots = [row.get(key, {}) for key in ("sketch", "feature", "macro")] + row.get("owned_objects", [])
        for root in roots:
            root.pop("current_name", None)
        result.append(row)
    return result


def _validate_checkpoint(runtime, plan, guard, preview, checkpoint):
    """Reject incompatible evidence before touching CAD. Not a chain recipe."""
    internal = guard.get("scope") in ("complete_internal_metric_cylinder_positive_x", "blind_internal_metric_cylinder_positive_x")
    steps = (runtime._internal_metric_carrier_guard if internal else runtime._thread_carrier_guard)(plan, guard, preview["params"])
    if preview.get("scenario") != ("internal_helical_thread" if internal else "external_helical_thread") or preview["params"].get("profile_root_shape") != "round":
        raise ValueError("Thread audit requires the external round metric profile")
    runtime._bounded(checkpoint)
    if checkpoint.get("schema") != CHECKPOINT_SCHEMA or checkpoint.get("version") != 1:
        raise ValueError("Invalid thread audit checkpoint version")
    fingerprints = {"prefix_recipe_hash": runtime._hash(plan["recipe"]),
                    "prefix_expectations_hash": runtime._hash(runtime._expectations(steps)),
                    "preview_hash": runtime._hash(preview), "guard_hash": runtime._hash(guard)}
    if any(checkpoint.get(key) != value for key, value in fingerprints.items()):
        raise ValueError("Thread audit checkpoint differs from prefix or family plan")
    outputs = checkpoint["outputs"]
    ident = checkpoint["step_id"]
    if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", ident):
        raise ValueError("Invalid thread audit step identity")
    if ident.upper() in {step["id"].upper() for step in steps} or len(outputs) != len(steps)+1:
        raise ValueError("Thread audit prefix ownership is incomplete or duplicated")
    if [out["id"] for out in outputs] != [step["id"] for step in steps]+[ident]:
        raise ValueError("Thread audit ownership order differs from prefix")
    namespaces = [step["namespace"] for step in steps]+["CH_"+ident.upper()]
    if [out["namespace"] for out in outputs] != namespaces or preview["params"].get("parameter_prefix") != namespaces[-1]:
        raise ValueError("Thread audit instance namespace differs")
    persistent = []
    for out in outputs:
        roots = out.get("owned_objects") or [out[key] for key in ("sketch", "feature")]
        if not out.get("macro"):
            raise ValueError("Thread audit requires saved macro identity")
        for root in roots+[out["macro"]]:
            value = root.get("object_id")
            if not isinstance(value, str) or not 1 <= len(value) <= 512:
                raise ValueError("Thread audit requires persistent root identities")
            persistent.append(value)
    if len(persistent) != len(set(persistent)):
        raise ValueError("Thread audit roots share persistent identities")
    thread = outputs[-1]
    owned = thread.get("owned_objects", [])
    expected = {"Sketchs": 1, "Evolutions": 1, "Points3D": 2, "Axes3D": 1,
                "Spirals3D": 1, "LocalCoordinateSystems": 1}
    counts = {key: sum(o["collection"] == key for o in owned) for key in {o["collection"] for o in owned}}
    if counts != expected or any(o.get("require_fully_defined") is not True for o in owned):
        raise ValueError("Thread audit requires exactly seven verified owned roots")
    params = preview["params"]
    names = {params[key] for key in ("feature_display_name", "profile_display_name", "path_display_name",
                                   "axis_display_name", "start_center_name", "profile_origin_name")}
    names.add(params["profile_display_name"]+"_LCS")
    if {o["name"] for o in owned} != names:
        raise ValueError("Thread audit root names differ from family plan")
    for key, collection, name in (("sketch", "Sketchs", params["profile_display_name"]),
                                   ("feature", "Evolutions", params["feature_display_name"])):
        matches = [o for o in owned if o["collection"] == collection]
        if thread[key].get("object_id") != matches[0]["object_id"] or thread[key].get("name") != name:
            raise ValueError("Thread audit primary root differs from owned identity")
    baseline = checkpoint["baseline"]
    stock = [segment for step in steps for segment in step["section"]["segments"]]
    radius = max(max(s["start_radius_mm"], s["end_radius_mm"]) for s in stock)
    bounds = [min(s["axial_min"] for s in stock), -radius, -radius,
              max(s["axial_max"] for s in stock), radius, radius]
    if baseline.get("body_count") != 1 or len(baseline.get("bounds_mm", [])) != 6:
        raise ValueError("Invalid thread audit baseline bounds")
    for actual, target in zip(baseline["bounds_mm"], bounds):
        runtime._close(runtime._number(actual), target)
    runtime._close(runtime._number(baseline["volume_cm3"]), guard["expected_blank_volume_cm3"], floor=1e-6)
    if not isinstance(baseline.get("protected_faces"), list) or len(baseline["protected_faces"]) > 256:
        raise ValueError("Invalid thread audit protected-face baseline")
    if internal:
        protected = baseline["protected_faces"]
        _validate_internal_protected(runtime, protected, guard)
    after_volume = runtime._number(checkpoint["audited_volume_cm3"])
    removed = runtime._number(checkpoint["removed_cm3"])
    upper = guard["removal_upper_bound_cm3"] if internal else math.pi*(guard["carrier_radius_mm"]**2-guard["root_radius_mm"]**2)*float(params["length"])/1000
    if after_volume <= 0 or not 1e-6 < removed <= upper+1e-6:
        raise ValueError("Invalid thread audited-native volume expectation")
    runtime._close(baseline["volume_cm3"]-after_volume, removed, floor=1e-6)
    if guard.get("end_plan"):
        _validate_end_characteristics(runtime, guard, checkpoint.get("end_characteristics", {}))
    return outputs


def make_checkpoint(runtime, plan, guard, preview, result):
    """Compact creation evidence for future persistence; never saves/promotes."""
    if result.get("ok") is not True or result.get("thread_executed") is not True or result.get("verification", {}).get("verified") is not True or result.get("drivers", {}).get("verified") is not True:
        raise ValueError("Thread checkpoint requires completed geometry and driver audits")
    verification = verify(runtime, result["body_before"], result["body_after"], guard)
    before = result["body_before"]
    checkpoint = {"schema": CHECKPOINT_SCHEMA, "version": 1, "step_id": result["output"]["id"],
                  "prefix_recipe_hash": runtime._hash(plan["recipe"]),
                  "prefix_expectations_hash": runtime._hash(runtime._expectations(plan["steps"])),
                  "preview_hash": runtime._hash(preview), "guard_hash": runtime._hash(guard),
                  "baseline": {key: deepcopy(before[key]) for key in ("body_count", "volume_cm3", "bounds_mm", "protected_faces")},
                  "audited_volume_cm3": result["body_after"]["volume_cm3"], "removed_cm3": verification["removed_cm3"],
                   "outputs": _compact_outputs(result["prefix_outputs"]+[result["output"]])}
    if guard.get("end_plan"):
        checkpoint["end_characteristics"] = deepcopy(verification["end_characteristics"])
    _validate_checkpoint(runtime, plan, guard, preview, checkpoint)
    return checkpoint


def audit_checkpoint(b, runtime, app, doc, plan, guard, preview, checkpoint):
    """Fresh read-only native audit at creation inputs, including after reopen.

    The caller supplies the stored checkpoint; this does not recognize or update
    a supported chain recipe, regenerate stock, or accept changed inputs.
    """
    saved = _validate_checkpoint(runtime, plan, guard, preview, checkpoint)
    if b.describe_runtime_document(doc, app).get("type") != 10024:
        raise ValueError("Thread audit requires a KOMPAS part document")
    model = b.cast_model_container(doc.TopPart)
    outputs = runtime._ownership(b, model, saved, strict_names=True, document=doc)
    expected = {key: set() for key in COLLECTIONS}
    for out in outputs:
        roots = out.get("owned_objects") or [dict(out[key], collection=collection)
            for key, collection in (("sketch", "Sketchs"), ("feature", "Rotateds"))]
        for root in roots:
            expected[root["collection"]].add(root["reference"])
        if out["macro"].get("grouped"):
            expected["MacroObjects3D"].add(out["macro"]["reference"])
    inventory = _inventory(b, runtime, model)
    if any(set(inventory[key]) != refs for key, refs in expected.items()):
        raise RuntimeError("Thread terminal checkpoint has extra or missing construction roots")
    body = snapshot(b, runtime, app, doc, guard, preview["params"])
    verification = verify(runtime, checkpoint["baseline"], body, guard)
    if guard.get("end_plan"):
        _validate_end_characteristics(runtime, guard, verification["end_characteristics"])
    runtime._close(body["volume_cm3"], checkpoint["audited_volume_cm3"], floor=1e-6)
    drivers = audit_drivers(b, runtime, doc, outputs[-1], preview["params"])
    return {"verified": True, "fresh_geometry_audit": True, "outputs": outputs,
            "body": body, "verification": verification, "drivers": drivers,
            "volume_reference": "audited_native_thread_creation", "saved_recipe_updated": False}


def validate_envelope(runtime, plan, envelope):
    """Bind stored native evidence to the supported recipe, not runtime refs."""
    steps = validate_plan(runtime, plan)
    if envelope["recipe"] != plan["recipe"] or envelope["expectations"] != runtime._expectations(steps):
        raise ValueError("Saved terminal thread recipe/expectations differ from host plan")
    checkpoint = envelope["thread_audit"]
    terminal = steps[-1]
    saved = _validate_checkpoint(runtime, plan["thread_prefix_plan"], terminal["thread_guard"], terminal["preview"], checkpoint)
    if len(envelope["outputs"]) != len(saved):
        raise ValueError("Saved thread envelope ownership is incomplete")
    for out, recorded in zip(envelope["outputs"], saved):
        if (out["id"], out["namespace"]) != (recorded["id"], recorded["namespace"]):
            raise ValueError("Saved thread envelope step identities differ")
        for key in ("sketch", "feature", "macro"):
            if (out[key]["object_id"], out[key]["name"]) != (recorded[key]["object_id"], recorded[key]["name"]):
                raise ValueError("Saved thread envelope primary identities differ")
        signature = lambda row: sorted((o["collection"], o["object_id"], o["name"], o.get("require_fully_defined", True)) for o in row.get("owned_objects", []))
        if signature(out) != signature(recorded):
            raise ValueError("Saved thread envelope owned identities differ")
    return checkpoint


def audit_drivers(b, runtime, doc, output, params):
    """Read actual input values and spiral bindings, including after reopen."""
    variables = {b.safe_get(v, "Name"): v for v in b._iter_operation_variables(doc.TopPart)}
    for key in ("diameter", "pitch", "length"):
        variable = variables.get(params["public_"+key+"_variable_name"])
        if variable is None or b.safe_get(variable, "Information", True) or b.safe_get(variable, "ReadOnly", True):
            raise RuntimeError("Thread public driver is missing or informational")
        runtime._close(b.safe_get(variable, "Value"), params[key])
    owned = [o for o in output["owned_objects"] if o["collection"] == "Spirals3D"]
    if len(owned) != 1:
        raise RuntimeError("Thread owned spiral identity is ambiguous")
    model = b.cast_model_container(doc.TopPart)
    matches = [obj for obj in b.iter_collection(runtime._collection(b, model, "Spirals3D"))
               if b.safe_get(obj, "Reference") == owned[0]["reference"]]
    if len(matches) != 1:
        raise RuntimeError("Current owned thread spiral is missing")
    spiral = b._cast_to_com_interface(matches[0], "ICylindricSpiral3D")
    runtime._close(spiral.Step, params["pitch"])
    runtime._close(spiral.Height, params["spiral_length"])
    phase = (0 if params["left_thread"] else 180) if params.get("internal_metric_method") else (180 if params["left_thread"] else 0)
    runtime._close(spiral.TurningAngle, phase, floor=1e-7)
    if not spiral.BuildingDirection or bool(spiral.TurnDirection) == bool(params["left_thread"]):
        raise RuntimeError("Thread spiral direction differs from requested carrier/hand")
    live = list(b._iter_operation_variables(spiral))
    for binding in params["operation_variable_bindings"]:
        aliases = [binding.get("parameter_note"), *(binding.get("parameter_note_aliases") or [])]
        matches = [v for v in live if b.safe_get(v, "ParameterNote") in aliases]
        if len(matches) != 1 or b.safe_get(matches[0], "Information", True) or b.safe_get(matches[0], "ReadOnly", True):
            raise RuntimeError("Thread spiral binding is missing or on an output")
        normalize = lambda text: "".join(str(text or "").split()).casefold()
        if normalize(b.safe_get(matches[0], "Expression")) != normalize(binding["expression"]):
            raise RuntimeError("Thread spiral driving expression differs from family plan")
    return {"verified": True, "pitch_mm": float(spiral.Step), "height_mm": float(spiral.Height),
            "phase_degrees": float(spiral.TurningAngle), "binding_count": len(params["operation_variable_bindings"])}


def execute(b, runtime, app, doc, plan, guard, preview, step_id, confirm_write=False):
    if confirm_write is not True:
        raise ValueError("Thread application requires explicit write confirmation")
    if not isinstance(step_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", step_id):
        raise ValueError("Invalid thread step identity")
    if step_id.upper() in {s["id"].upper() for s in plan["steps"]}:
        raise ValueError("Thread step identity already belongs to input prefix")
    params = preview["params"]
    namespace = "CH_"+step_id.upper()
    if params.get("parameter_prefix") != namespace or any(key in params for key in ("source_scenario", "source_params", "source_preview", "source_variable_bindings")):
        raise ValueError("Thread application requires namespaced source-free family parameters")
    internal = preview.get("scenario") == "internal_helical_thread" and params.get("internal_metric_method")
    if (preview.get("scenario") != "external_helical_thread" and not internal) or params.get("profile_root_shape") != "round":
        raise ValueError("Initial chain application requires the external round metric profile")
    variables = params["profile_variables"]
    names = [v["name"] for v in variables]
    expected = [params["public_"+key+"_variable_name"] for key in ("diameter", "pitch", "length")]
    if len(names) != 3 or set(names) != set(expected) or len(set(names)) != 3 or any(not name.startswith(namespace+"_") for name in names):
        raise ValueError("Thread variables must have three independent instance-owned names")
    resolve = runtime._internal_metric_carrier_context if internal else runtime._thread_carrier_context
    context = resolve(b, app, doc, plan, guard, params)
    model = b.cast_model_container(doc.TopPart)
    existing = [str(b.safe_get(v, "Name") or "").upper() for v in b._iter_operation_variables(doc.TopPart)]
    if any(name.startswith(namespace.upper()+"_") for name in existing):
        raise RuntimeError("Thread namespace collides with existing model variables")
    before_roots = _inventory(b, runtime, model)
    planned_names = {params[key] for key in ("feature_display_name", "profile_display_name", "path_display_name",
                                            "axis_display_name", "start_center_name", "profile_origin_name")}
    planned_names.add(params["profile_display_name"]+"_LCS")
    if len(planned_names) != 7 or any(b.safe_get(obj, "Name") in planned_names for rows in before_roots.values() for obj in rows.values()):
        raise RuntimeError("Thread root names collide with the incoming model")
    reports = [b._apply_part_variables(doc.TopPart, variables)]
    if not reports[0]["ok"]:
        raise RuntimeError("Thread instance variables could not be installed")
    installed = {b.safe_get(v, "Name"): v for v in b._iter_operation_variables(doc.TopPart)}
    for variable in variables:
        live = installed.get(variable["name"])
        if live is None or b.safe_get(live, "Information", True) or b.safe_get(live, "ReadOnly", True):
            raise RuntimeError("Thread variable is not a writable model input")
        runtime._close(b.safe_get(live, "Value"), variable["value"])
    # Reacquire after installing variables; never carry stale faces into a write.
    context = resolve(b, app, doc, plan, guard, params)
    before = snapshot(b, runtime, app, doc, guard, params)
    built = b._apply_helical_thread_feature(doc.TopPart, model, params, preview, reports,
        scenario=preview["scenario"], **{key: context[key] for key in ("base_face", "start_face", "end_face", "face_reports")})
    after_roots = _inventory(b, runtime, model)
    new = {}
    for collection, rows in before_roots.items():
        if not set(rows).issubset(after_roots[collection]):
            raise RuntimeError("Thread application removed or replaced an incoming root")
        new[collection] = [obj for ref, obj in after_roots[collection].items() if ref not in rows]
    expected_counts = {"Sketchs": 1, "Evolutions": 1, "Points3D": 2, "Axes3D": 1,
                       "Spirals3D": 1, "LocalCoordinateSystems": 1}
    if {key: len(rows) for key, rows in new.items() if rows} != expected_counts:
        raise RuntimeError("Thread application created unexpected or unowned roots")
    owned = [{"collection": collection, "reference": b.safe_get(obj, "Reference"),
              "name": b.safe_get(obj, "Name"), "role": "thread."+collection, "require_fully_defined": True}
             for collection, rows in new.items() for obj in rows]
    if {o["name"] for o in owned} != planned_names:
        raise RuntimeError("Thread actual root names differ from the instance contract")
    out = {"id": step_id, "namespace": namespace,
           "sketch": {"reference": b.safe_get(built["profile_sketch"], "Reference"), "name": params["profile_display_name"]},
           "feature": {"reference": b.safe_get(built["thread"], "Reference"), "name": params["feature_display_name"]},
           "owned_objects": owned}
    prefix = runtime._ownership(b, model, context["prefix_outputs"], strict_names=True, document=doc)
    after = snapshot(b, runtime, app, doc, guard, params)
    verification = verify(runtime, before, after, guard)
    runtime._group_step(b, model, {"owned_objects": [obj for rows in new.values() for obj in rows]}, out)
    outputs = runtime._ownership(b, model, [out], strict_names=True, document=doc)
    prefix = runtime._ownership(b, model, prefix, strict_names=True, document=doc)
    grouped = snapshot(b, runtime, app, doc, guard, params)
    verify(runtime, before, grouped, guard)
    runtime._close(grouped["volume_cm3"], after["volume_cm3"], floor=1e-6)
    drivers = audit_drivers(b, runtime, doc, outputs[0], params)
    return {"ok": True, "output": outputs[0], "prefix_outputs": prefix, "body_before": before,
            "body_after": grouped, "verification": verification, "reports": reports,
            "drivers": drivers, "saved_recipe_updated": False, "thread_executed": True}
