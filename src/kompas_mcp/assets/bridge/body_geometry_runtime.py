"""COM-only final-body readback, shared by checkout and packaged bridge.

No document activation, Update, tessellation rebuild, entity creation or save.
All topology comes from final ResultBodies, never a historical feature's faces.
"""

import math

import win32com.client as com


KINDS = {"face": (6, "IFace"), "edge": (7, "IEdge"), "vertex": (8, "IVertex")}
SURFACES = (("plane", "IsPlanar"), ("cylinder", "IsCylinder"), ("cone", "IsCone"),
            ("sphere", "IsSphere"), ("torus", "IsTorus"), ("nurbs", "IsNurbsSurface"),
            ("revolved", "IsRevolved"), ("swept", "IsSwept"))
RELATIONS = {1: "axes_coaxial", 2: "axes_parallel", 3: "axes_intersecting", 4: "axes_distant",
             5: "axis_on_surface", 6: "axis_parallel_surface", 7: "axis_intersects_surface",
             8: "axis_distant_surface", 9: "surfaces_coincident", 10: "surfaces_parallel",
             11: "surfaces_intersecting", 12: "arc_centres", 13: "from_arc_centre", -1: "calculated"}


def get(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def sequence(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def number(value):
    if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def outs(value, count):
    """pywin32 BOOL + output parameters. Never accept failed/non-finite output."""
    if not isinstance(value, (tuple, list)) or len(value) != count + 1 or not value[0]:
        raise RuntimeError("KOMPAS returned no valid geometric result")
    result = [number(x) for x in value[1:]]
    if any(x is None for x in result):
        raise RuntimeError("KOMPAS returned non-finite geometric coordinates")
    return result


def optional(fn, diagnostics, field):
    try:
        return fn()
    except Exception as exc:
        diagnostics.append({"field": field, "status": "unavailable", "message": str(exc)[:240]})
        return None


def reference(obj):
    value = get(obj, "Reference")
    return int(value) if value is not None else None


def frame(placement):
    return {"origin_mm": outs(placement.GetOrigin(), 3),
            "x_axis": outs(placement.GetVector(71), 3),
            "y_axis": outs(placement.GetVector(72), 3),
            "z_axis": outs(placement.GetVector(73), 3)}


def normalize(vector):
    length = math.sqrt(sum(x*x for x in vector))
    if length < 1e-12:
        raise RuntimeError("Degenerate surface direction")
    return [x/length for x in vector]


def cross(a, c):
    return [a[1]*c[2]-a[2]*c[1], a[2]*c[0]-a[0]*c[2], a[0]*c[1]-a[1]*c[0]]


def evaluated_frame(surface, kind, radius):
    """Trimmed MathSurface.Placement can be identity: evaluate the actual surface."""
    lo, hi = float(surface.ParamUMin), float(surface.ParamUMax)
    v = (float(surface.ParamVMin)+float(surface.ParamVMax))/2
    u = lo + (hi-lo)*0.37
    point = outs(surface.GetPoint(u, v), 3)
    normal = normalize(outs(surface.GetNormal(u, v), 3))
    if kind == "plane":
        x = normalize(outs(surface.GetDerivativeU(u, v), 3))
        return {"origin_mm": point, "x_axis": x, "y_axis": normalize(cross(normal, x)), "z_axis": normal}
    if kind != "cylinder" or radius is None:
        raise RuntimeError("Analytical frame evaluation is unavailable for this surface type")
    derivative_v = outs(surface.GetDerivativeV(u, v), 3)
    p2 = outs(surface.GetPoint(lo+(hi-lo)*0.73, v), 3)
    n2 = normalize(outs(surface.GetNormal(lo+(hi-lo)*0.73, v), 3))
    axis = normalize(cross(normal, n2))
    if sum(a*d for a, d in zip(axis, derivative_v)) < 0:
        axis = [-a for a in axis]
    centres = []
    for sign in (-1, 1):
        c1 = [p+sign*radius*n for p, n in zip(point, normal)]
        c2 = [p+sign*radius*n for p, n in zip(p2, n2)]
        delta = [y-x for x, y in zip(c1, c2)]
        perpendicular = cross(delta, axis)
        centres.append((math.sqrt(sum(x*x for x in perpendicular)), c1, sign))
    residual, centre, sign = min(centres)
    if residual > max(1e-6, radius*1e-8):
        raise RuntimeError("Cylinder centre/axis evaluation is inconsistent")
    radial = [-sign*n for n in normal]
    return {"origin_mm": centre, "x_axis": radial, "y_axis": normalize(cross(axis, radial)),
            "z_axis": axis, "verification_residual_mm": residual}


def topology(body, kind):
    code, interface = KINDS[kind]
    return [com.CastTo(obj, interface) for obj in sequence(com.CastTo(body, "IFeature7").ModelObjects(code))]


def components(b, part, path="root", depth=0, budget=None):
    budget = budget if budget is not None else [5000]
    budget[0] -= 1
    if depth > 32 or budget[0] < 0:
        raise RuntimeError("Assembly traversal exceeds 32 levels/5000 components; inspect a smaller assembly")
    yield path, part
    for index, child in enumerate(b.iter_collection(get(part, "Parts"))):
        yield from components(b, child, path + "/" + str(index), depth + 1, budget)


def resolve_part(b, root, path):
    part = root
    for segment in path.split("/")[1:]:
        index = int(segment)
        children = get(part, "Parts")
        if index >= b.collection_count(children):
            raise RuntimeError("Component selector is stale/not found; run list_model_bodies again")
        part = b.get_collection_item(children, index)
    return part


def component_matrix(b, root, path):
    """KOMPAS uses row vectors; nested local-to-parent placements compose child*parent."""
    result = [float(i == j) for i in range(4) for j in range(4)]
    part = root
    for segment in path.split("/")[1:]:
        part = b.get_collection_item(part.Parts, int(segment))
        child = list(part.Placement.GetMatrix3D())
        if len(child) != 16 or any(number(x) is None for x in child):
            raise RuntimeError("Component placement matrix is unreadable; no document-coordinate result available")
        if any(abs(sum(child[i*4+k]*child[j*4+k] for k in range(3)) - int(i == j)) > 1e-8
               for i in range(3) for j in range(3)) or any(abs(child[i]) > 1e-8 for i in (3, 7, 11)) or abs(child[15]-1) > 1e-8:
            raise RuntimeError("Non-rigid component placement cannot be treated as an mm-preserving frame; geometry readback is unsupported for this transform")
        result = [sum(child[i*4+k]*result[k*4+j] for k in range(4)) for i in range(4) for j in range(4)]
    return result


def transformed(vector, matrix, point=True):
    return [sum(vector[i]*matrix[i*4+j] for i in range(3)) + (matrix[12+j] if point else 0) for j in range(3)]


def in_document(value, matrix):
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in {"origin_mm", "point_mm", "centre_mm", "start_mm", "end_mm"} and item is not None:
            result[key] = transformed(item, matrix)
        elif key in {"x_axis", "y_axis", "z_axis"} and item is not None:
            result[key] = transformed(item, matrix, False)
        elif key in {"points_mm", "normals"} and item is not None:
            result[key] = [transformed(point, matrix, key != "normals") for point in item]
        elif isinstance(item, dict):
            result[key] = in_document(item, matrix)
        elif isinstance(item, list):
            result[key] = [in_document(child, matrix) for child in item]
        else:
            result[key] = item
    return result


def final_bodies(part):
    return [com.CastTo(obj, "IBody7") for obj in sequence(com.CastTo(part, "IFeature7").ResultBodies)]


def select(objects, selector, label):
    matches = [(i, obj) for i, obj in enumerate(objects)
               if ("index" not in selector or i == selector["index"])
               and ("reference" not in selector or reference(obj) == selector["reference"])]
    if len(matches) != 1:
        raise RuntimeError(label + " selector is stale, conflicting or absent; re-list final geometry")
    return matches[0]


def resolve_body(b, root, selector):
    document_stamp = int(com.CastTo(root, "IFeature7").UpdateStamp)
    if "document_stamp" in selector and document_stamp != selector["document_stamp"]:
        raise RuntimeError("Body geometry changed or assembly placement changed; re-list geometry before measuring")
    part = resolve_part(b, root, selector.get("component", "root"))
    index, body = select(final_bodies(part), selector, "Body")
    stamp = int(com.CastTo(part, "IFeature7").UpdateStamp)
    if "update_stamp" in selector and stamp != selector["update_stamp"]:
        raise RuntimeError("Body geometry changed; re-list geometry before measuring")
    return part, index, body


def body_row(part, path, index, body, matrix=None, document_stamp=None):
    diagnostics = []
    bounds = optional(lambda: outs(body.GetGabarit(), 6), diagnostics, "bounds_mm")
    stamp = int(com.CastTo(part, "IFeature7").UpdateStamp)
    selector = {"component": path, "index": index, "reference": reference(body), "update_stamp": stamp}
    if document_stamp is not None:
        selector["document_stamp"] = int(document_stamp)
    local_bounds = bounds
    if bounds and matrix:
        corners = [transformed([bounds[3*x], bounds[1+3*y], bounds[2+3*z]], matrix)
                   for x in (0, 1) for y in (0, 1) for z in (0, 1)]
        bounds = [min(p[i] for p in corners) for i in range(3)] + [max(p[i] for p in corners) for i in range(3)]
    return {"selector": selector,
            "name": get(body, "Name", ""), "solid": bool(get(body, "IsSolid", False)),
            "component_name": get(part, "Name", ""), "component_source": get(part, "FileName", ""),
            "bounds_mm": bounds, "size_mm": [bounds[i + 3] - bounds[i] for i in range(3)] if bounds else None,
            "local_bounds_mm": local_bounds, "local_size_mm": [local_bounds[i+3]-local_bounds[i] for i in range(3)] if local_bounds else None,
            "bounds_kind": "native_body_aabb" if path == "root" else "transformed_local_aabb_conservative",
            "diagnostics": diagnostics}


def surface_type(face):
    for name, prop in SURFACES:
        if get(face, prop) is True:
            return name
    return "other"


def surface_row(face):
    diagnostics = []
    kind = surface_type(face)
    math_surface = get(face, "MathSurface")
    math_surface = com.CastTo(math_surface, "IMathSurface3D") if math_surface is not None else None
    radius = number(get(math_surface, "Radius")) if kind in ("cylinder", "sphere") else None
    reported = optional(lambda: frame(math_surface.Placement), diagnostics, "reported_surface_frame")
    placement = optional(lambda: evaluated_frame(math_surface, kind, radius), diagnostics, "surface_frame") if kind in ("plane", "cylinder") else reported
    result = {"type": kind, "surface_type_code": get(face, "Surface3DType"),
              "base_surface_type_code": get(face, "BaseSurface3DType"),
              "frame": placement if kind in ("plane", "cylinder") else None,
              "frame_verified": kind in ("plane", "cylinder") and placement is not None,
              "reported_frame": reported, "frame_source": "evaluated_surface" if kind in ("plane", "cylinder") else "unverified_surface_placement",
              "radius_mm": radius, "diameter_mm": radius * 2 if radius is not None else None,
              "normal_orientation": get(face, "NormalOrientation"),
              "uv_domain": {"u_min": number(get(math_surface, "ParamUMin")),
                            "u_max": number(get(math_surface, "ParamUMax")),
                            "v_min": number(get(math_surface, "ParamVMin")),
                            "v_max": number(get(math_surface, "ParamVMax"))},
              "diagnostics": diagnostics}
    if kind == "cone":
        params = optional(lambda: outs(face.GetConeParam(), 3), diagnostics, "cone_parameters")
        if params:
            result["cone"] = {"support_height_mm": params[0], "angle_radians": params[1], "radius_mm": params[2],
                              "height_is_trimmed_face_length": False}
    elif kind == "torus":
        params = optional(lambda: outs(math_surface.GetTorusParam(), 2), diagnostics, "torus_parameters")
        if params:
            result["torus"] = {"major_radius_mm": params[0], "minor_radius_mm": params[1]}
    return result


def face_row(index, face):
    diagnostics = []
    area = optional(lambda: number(face.GetArea(1)), diagnostics, "area_mm2")
    return {"selector": {"index": index, "reference": reference(face)}, "surface": surface_row(face),
            "area_mm2": area, "valid": bool(get(face, "Valid", False)), "diagnostics": diagnostics}


def edge_row(index, edge, sample_count=0):
    diagnostics = []
    curve = com.CastTo(edge.MathCurve, "IMathCurve3D")
    kind = next((name for name, prop in (("circle", "IsCircle"), ("arc", "IsArc"), ("line", "IsStraight"),
                                        ("ellipse", "IsEllipse"), ("nurbs", "IsNurbs")) if get(edge, prop) is True), "other")
    start = optional(lambda: outs(edge.GetPoint(True), 3), diagnostics, "start_mm")
    end = optional(lambda: outs(edge.GetPoint(False), 3), diagnostics, "end_mm")
    selector = {"reference": reference(edge)}
    if index is not None:
        selector["index"] = index
    result = {"selector": selector, "curve_type": kind,
              "curve_type_code": get(edge, "Curve3DType"),
              "length_mm": optional(lambda: number(edge.GetLength(1)), diagnostics, "length_mm"),
              "start_mm": start, "end_mm": end, "diagnostics": diagnostics}
    result["vertices"] = []
    for is_start in (True, False):
        vertex = optional(lambda: edge.Vertex(is_start), diagnostics, "vertex")
        if vertex is not None:
            result["vertices"].append({"reference": reference(vertex), "point_mm": start if is_start else end})
    if kind in ("circle", "arc", "ellipse"):
        result["centre_mm"] = optional(lambda: outs(curve.GetCentre(), 3), diagnostics, "centre_mm")
        result["radius_mm"] = number(get(curve, "Radius")) if kind in ("circle", "arc") else None
    result["adjacent_face_references"] = []
    for side in (True, False):
        adjacent = optional(lambda: edge.AdjacentFace(side), diagnostics, "adjacent_face")
        if adjacent is not None:
            result["adjacent_face_references"].append(reference(adjacent))
    if sample_count:
        t_min, t_max = number(get(curve, "ParamMin")), number(get(curve, "ParamMax"))
        if t_min is not None and t_max is not None:
            points = optional(lambda: [outs(curve.GetPoint(t_min + (t_max-t_min)*i/(sample_count-1)), 3)
                                        for i in range(sample_count)], diagnostics, "curve_samples")
            # Samples must use the trimmed edge domain, not an extended mathematical curve.
            agrees = points and start and end and max(
                math.dist(points[0], start), math.dist(points[-1], end)) <= 1e-6
            if not agrees and points and start and end:
                agrees = max(math.dist(points[0], end), math.dist(points[-1], start)) <= 1e-6
            result["samples"] = {"status": "sampled" if agrees else "unverified_domain",
                                 "points_mm": points if agrees else [], "parameter_range": [t_min, t_max],
                                 "error_bound_mm": None, "not_for_exact_measurements": True}
    return result


def page(items, offset, limit):
    stop = min(len(items), offset + limit)
    return {"total": len(items), "offset": offset, "limit": limit,
            "returned": max(0, stop-offset), "next_offset": stop if stop < len(items) else None}


def mesh_snapshot(face, maximum):
    tessellation = com.CastTo(face.Tessellation, "ITessellation7")
    data = tessellation.GetFacetPoints()
    if not data or len(data) != 4 or not data[0]:
        return {"status": "unavailable", "reason": "No cached tessellation; no rebuild attempted"}
    points, indexes, normals = data[1:]
    points, indexes, normals = list(points or []), list(indexes or []), list(normals or [])
    if len(points) % 3 or len(indexes) % 3:
        return {"status": "unavailable", "reason": "Unsupported native mesh layout"}
    count = len(points) // 3
    settings = {"facet_sag_mm": number(get(tessellation, "FacetSag")),
                "facet_angle_native": number(get(tessellation, "FacetAngle")),
                "facet_size_mm": number(get(tessellation, "FacetSize"))}
    result = {"status": "approximate", "vertex_count": count, "triangle_count": len(indexes)//3,
              "settings": settings, "error_bound_verified": False, "rebuilt": False}
    if count > maximum or len(indexes)//3 > maximum * 4:
        result.update(status="omitted_size_limit", max_mesh_points=maximum)
        return result
    if any(i < 0 or i >= count for i in indexes) or any(number(x) is None for x in points):
        return {"status": "unavailable", "reason": "Invalid mesh coordinates/indexes"}
    result["points_mm"] = [points[i:i+3] for i in range(0, len(points), 3)]
    result["triangles"] = [indexes[i:i+3] for i in range(0, len(indexes), 3)]
    if len(normals) == len(points) and all(number(x) is not None for x in normals):
        result["normals"] = [normals[i:i+3] for i in range(0, len(normals), 3)]
    return result


def face_snapshot(body, index, face, payload):
    row = face_row(index, face)
    all_edges = topology(body, "edge")
    edge_indexes = {reference(edge): i for i, edge in enumerate(all_edges)}
    raw_edges = [com.CastTo(e, "IEdge") for e in sequence(face.LimitingEdges)]
    maximum = payload["max_edges"]
    row["boundaries"] = {"total_edges": len(raw_edges), "complete": len(raw_edges) <= maximum,
        "edges": [edge_row(edge_indexes.get(reference(e)), e, payload["curve_samples"]) for e in raw_edges[:maximum]]}
    adjacent = sequence(face.ConnectedFaces)
    row["adjacent_face_references"] = [reference(f) for f in adjacent][:maximum]
    row["adjacency_complete"] = len(adjacent) <= maximum
    loops = sequence(face.Loops)
    row["loop_count"] = len(loops)
    row["loops"] = []
    loop_budget = maximum
    for raw_loop in loops[:maximum]:
        loop = com.CastTo(raw_loop, "ILoop7")
        oriented = sequence(loop.OrientedEdges)
        entries = []
        for raw in oriented[:loop_budget]:
            item = com.CastTo(raw, "IOrientedEdge7")
            entries.append({"edge_reference": reference(item.Edge), "orientation": get(item, "Orientation"),
                            "same_sense": get(item, "SameSense"), "is_seam": get(item, "IsSeam")})
        row["loops"].append({"outer": get(loop, "IsOuter"), "edge_count": len(oriented),
                             "complete": len(entries) == len(oriented), "edges": entries})
        loop_budget -= len(entries)
    row["representation"] = "analytic_surface_and_trimmed_boundary_samples"
    row["exact_brep_export"] = False
    partial = (not row["boundaries"]["complete"] or row["surface"]["diagnostics"] or
               any(edge["diagnostics"] or edge.get("samples", {}).get("status") != "sampled"
                   for edge in row["boundaries"]["edges"]) or len(row["loops"]) < len(loops) or
               any(not loop["complete"] for loop in row["loops"]))
    row["status"] = "partial" if partial else "read"
    if payload["include_mesh"]:
        row["mesh"] = optional(lambda: mesh_snapshot(face, payload["max_mesh_points"]), row["diagnostics"], "mesh")
    return row


def resolve_target(b, root, target):
    if target["kind"] == "point":
        return None, target
    part, index, body = resolve_body(b, root, target["body"])
    if target["kind"] == "body":
        return body, {"kind": "body", "selector": body_row(part, target["body"].get("component", "root"), index, body,
                      document_stamp=int(com.CastTo(root, "IFeature7").UpdateStamp))["selector"]}
    entity_index, entity = select(topology(body, target["kind"]), target["entity"], target["kind"])
    row = {"kind": target["kind"], "body": target["body"],
           "entity": {"index": entity_index, "reference": reference(entity)}}
    if target["kind"] == "face":
        row["surface"] = surface_row(entity)
    elif target["kind"] == "vertex":
        row["point_mm"] = outs(entity.GetPoint(), 3)
    return entity, in_document(row, component_matrix(b, root, target["body"].get("component", "root")))


def witness_on_target(b, root, obj, target, point, epsilon):
    """Confirm native witnesses belong to the chosen trimmed topology, not its support axes."""
    path = target["body"].get("component", "root")
    part = resolve_part(b, root, path)
    matrix = component_matrix(b, root, path)
    shifted = [point[j]-matrix[12+j] for j in range(3)]
    local = [sum(shifted[j]*matrix[i*4+j] for j in range(3)) for i in range(3)]
    if target["kind"] == "vertex":
        return math.dist(local, outs(obj.GetPoint(), 3)) <= epsilon
    wanted = {reference(obj)}
    if target["kind"] == "face":
        wanted.update(reference(edge) for edge in sequence(obj.LimitingEdges))
    elif target["kind"] == "edge":
        wanted.update(reference(obj.Vertex(side)) for side in (True, False) if obj.Vertex(side) is not None)
    elif target["kind"] == "body":
        wanted.update(reference(item) for item in sequence(com.CastTo(obj, "IFeature7").ModelObjects(0)))
    found = sequence(part.FindObjectsByPointEx(local[0], local[1], local[2], True, epsilon))
    return bool(wanted.intersection(reference(item) for item in found))


def measure(b, root, payload):
    first, a = resolve_target(b, root, payload["first"])
    second, c = resolve_target(b, root, payload["second"])
    kind = payload["measurement"]
    result = {"measurement": kind, "first": a, "second": c}
    if kind in ("axis_distance", "plane_distance", "point_distance"):
        result["analytic_inputs"] = True
        return result
    if kind == "minimum_distance" and a["kind"] == c["kind"] == "body" and (
        payload["first"]["body"].get("component", "root") == payload["second"]["body"].get("component", "root")
    ):
        intersections = sequence(first.CheckIntersectionWithBody(second, True))
        codes = sorted(set(intersections))
        if codes and all(isinstance(code, int) and code in (1, 2, 3, 4) for code in codes):
            result.update(value=0.0, units="mm", status="native", source="KOMPAS IBody7.CheckIntersectionWithBody",
                          relation="volume_overlap" if 4 in codes else "contact", intersection_type_codes=codes,
                          witnesses_mm=None, semantics="zero_body_separation_confirmed_by_native_intersection",
                          penetration_depth_mm=None)
            return result
    native = com.CastTo(root.Measurement3D, "IMeasurement3D")
    # This is an ephemeral calculator, not a model measurement feature.
    saved = (native.Object1, native.Object2, native.Gap, native.Briefly)
    try:
        native.Object1 = com.CastTo(first, "IKompasAPIObject")
        native.Object2 = com.CastTo(second, "IKompasAPIObject")
        native.Gap = True
        native.Briefly = False
        code = int(native.Calculate())
        if code == 0 or code not in RELATIONS:
            raise RuntimeError("Native measurement is unavailable for this pair; select other final faces/edges")
        result.update(source="KOMPAS IMeasurement3D", relation=RELATIONS[code], native_result_code=code)
        if kind == "angle":
            if not native.IsAngleValid:
                raise RuntimeError("Angle is not applicable to these objects; no zero angle was inferred")
            angle = number(native.Angle)
            if angle is None:
                raise RuntimeError("Native angle is non-finite; measurement is unverified")
            result.update(value=angle, units="degrees", status="native")
        else:
            value = number(native.Lmin)
            p1, p2 = outs(native.GetMinPoint1(), 3), outs(native.GetMinPoint2(), 3)
            if value is None or value < 0 or abs(math.dist(p1, p2)-value) > max(1e-6, value*1e-8):
                raise RuntimeError("Native distance and witness points disagree; measurement is unverified")
            verified = [witness_on_target(b, root, first, payload["first"], p1, 1e-6),
                        witness_on_target(b, root, second, payload["second"], p2, 1e-6)]
            if not all(verified):
                raise RuntimeError("Native witnesses do not belong to the selected trimmed geometry; do not interpret supporting axes/centres as surface clearance. Select boundary edges or other final objects.")
            result.update(value=value, units="mm", status="native", witnesses_mm=[p1, p2],
                          witness_distance_mm=math.dist(p1, p2), witnesses_on_selected_geometry=verified,
                          witness_tolerance_mm=1e-6,
                          semantics="minimum_trimmed_geometry_distance_with_gap_enabled")
    finally:
        native.Object1 = saved[0] if saved[0] is not None else com.VARIANT(9, None)
        native.Object2 = saved[1] if saved[1] is not None else com.VARIANT(9, None)
        native.Gap, native.Briefly = saved[2:]
    return result


def handle(action, payload, b):
    app = b.make_app()
    document_id = payload.get("document_id")
    if document_id:
        document = b.resolve_document_strict(app, document_id)
    else:
        document = b.cast_document_3d(get(app, "ActiveDocument"))
    if document is None:
        raise RuntimeError("Exact 3D document not found; open a model and use its returned document_id")
    root = get(document, "TopPart")
    if root is None:
        raise RuntimeError("Document has no 3D model TopPart")
    changed_before = get(document, "Changed")
    root_stamp = get(com.CastTo(root, "IFeature7"), "UpdateStamp")
    result = {"ok": True, "schema_version": 1, "read_only": True, "coordinate_space": "document",
              "length_units": "mm", "document": b.describe_document(document, app)}
    result["model_state"] = {"valid": get(com.CastTo(root, "IFeature7"), "Valid"),
                             "geometry_update_stamp": root_stamp, "rebuilt_by_reader": False}
    if action == "list_model_bodies":
        rows = []
        for path, part in components(b, root):
            for index, body in enumerate(final_bodies(part)):
                rows.append((part, path, index, body))
        offset, limit = payload["offset"], payload["limit"]
        result["items"] = [body_row(*args, matrix=component_matrix(b, root, args[1]), document_stamp=root_stamp)
                           for args in rows[offset:offset+limit]]
        result["pagination"] = page(rows, offset, limit)
    elif action in ("list_body_faces", "list_body_edges", "inspect_body_face"):
        part, index, body = resolve_body(b, root, payload["body"])
        path = payload["body"].get("component", "root")
        matrix = component_matrix(b, root, path)
        result["body"] = body_row(part, path, index, body, matrix=matrix, document_stamp=root_stamp)
        objects = topology(body, "face" if action != "list_body_edges" else "edge")
        if action == "inspect_body_face":
            face_index, face = select(objects, payload["face"], "Face")
            result["face"] = in_document(face_snapshot(body, face_index, face, payload), matrix)
        else:
            rows = [(i, obj) for i, obj in enumerate(objects)
                    if not payload.get("surface_type") or surface_type(obj) == payload["surface_type"]]
            offset, limit = payload["offset"], payload["limit"]
            reader = face_row if action == "list_body_faces" else edge_row
            result["items"] = [in_document(reader(i, obj), matrix) for i, obj in rows[offset:offset+limit]]
            result["pagination"] = page(rows, offset, limit)
            result["total_unfiltered"] = len(objects)
    elif action == "measure_model_geometry":
        result["result"] = measure(b, root, payload)
    else:
        raise RuntimeError("Unknown body geometry action: " + action)
    result["readback_check"] = {"changed_before": changed_before, "changed_after": get(document, "Changed"),
                               "geometry_stamp_before": root_stamp,
                               "geometry_stamp_after": get(com.CastTo(root, "IFeature7"), "UpdateStamp")}
    result["readback_check"]["unchanged"] = (result["readback_check"]["changed_after"] == changed_before and
        result["readback_check"]["geometry_stamp_after"] == root_stamp)
    if not result["readback_check"]["unchanged"]:
        raise RuntimeError("Model state changed during geometry readback; discard result and re-list geometry")
    return result
