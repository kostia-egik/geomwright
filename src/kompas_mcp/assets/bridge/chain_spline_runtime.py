"""Bounded terminal input-shaft spline execution and checkpoint audit.

The caller owns save/checkpoint. The family owns the exact numeric contour;
construction_chain_runtime owns input preflight and persistent root readback.
Boundary containment is sampled, not an exact BREP preservation certificate.
"""
import json
import math
import re
from copy import deepcopy


def hub_carrier_guard(r, plan, guard, application):
    """Independent native through-bore/profile gate; no second catalog or COM."""
    steps = r._validate(plan)
    if (len(steps)!=2 or steps[0]["module"]!="stepped_shaft" or steps[0]["material"]!="create" or
            steps[1]["module"]!="internal_cylindrical_step" or steps[1]["id"]!=guard.get("target") or
            steps[1]["target"]!=steps[0]["id"] or any(len(s["section"]["segments"])!=1 or
            s["placement"]["direction"]!=1 for s in steps)):
        raise ValueError("Input hub requires one cylindrical stock and its explicit +X through bore")
    stock,bore = [s["section"] for s in steps]
    g,request = application["geometry"],application["profile_request"]
    if (set(application)!={"schema","version","profile_geometry_revision","name","profile_request","geometry",
            "operations","inputs","working_span_mm","expected_single_space_removal_cm3","expected_removal_cm3","verification","capabilities"} or
            application.get("version")!=1 or application.get("profile_geometry_revision")!=2 or
            request.get("body")!="hub" or g.get("body")!="hub" or request.get("standard")!="gost_1139_80" or
            request.get("include_tip_chamfer") is not False):
        raise ValueError("Input hub requires corrected revision-2 nominal profile without chamfers")
    lo,hi = application["working_span_mm"]
    scope = guard.get("scope")
    blind = scope == "blind_internal_spline_cylinder_positive_x"
    if blind:
        if (lo!=stock["start_mm"] or lo!=bore["start_mm"] or
                not lo < hi < bore["end_mm"]-1e-5 < stock["end_mm"]-2e-5):
            raise ValueError("Blind input hub requires open entry, positive smooth tail and stock behind its flat bottom")
    elif scope!="through_internal_spline_cylinder_positive_x" or stock["axial_interval_mm"]!=bore["axial_interval_mm"] or [lo,hi]!=bore["axial_interval_mm"]:
        raise ValueError("Input hub spline must cover the entire through bore")
    radius = stock["segments"][0]["start_radius_mm"]
    root = bore["segments"][0]["start_radius_mm"]
    floor = r._number(g["outer_diameter_mm"])/2
    width = r._number(g["length_mm"])
    count = g["tooth_count"]
    if isinstance(count,bool) or not isinstance(count,int) or not 4<=count<=40 or not 0<root<floor<radius:
        raise ValueError("Invalid input hub radii/count")
    for a,c in ((hi-lo,width),(request["length_mm"],width),(g["inner_diameter_mm"],root*2),
            (g["root_radius_mm"],root),(g["outer_radius_mm"],floor),(g["hub_outside_radius_mm"],radius),
            (request["hub_outside_diameter_mm"],2*radius)):
        r._close(a,c)
    for key in ("tooth_count","inner_diameter_mm","outer_diameter_mm","tooth_width_mm"):
        if request.get(key) is not None:r._close(g[key],request[key])
    if application["inputs"]!={"profile_plane":{"axis":"global_x","origin_mm":[lo,0,0],"direction":1},
            "axis":"global_x","carrier_outside_diameter_mm":radius*2,"bore_diameter_mm":root*2}:
        raise ValueError("Input hub supports/diameters differ from selected stock/bore")
    label = application["name"]
    ops = application["operations"]
    if len(ops)!=3 or any(set(o)!={"id","scenario","params"} for o in ops):
        raise ValueError("Input hub contains hidden operations")
    entities = ops[0]["params"].get("entities")
    expected_ops = [
        {"id":"tooth_space_sketch","scenario":"numeric_profile_sketch","params":{"name":label+" one tooth space",
            "plane":"input.profile_plane","entities":entities,"parameterize":False,"require_fully_defined":False,
            "profile_status":"nominal_straight_sided_space_numeric_profile"}},
        {"id":"tooth_space_cut","scenario":"cut_extrusion","params":{"name":label+" one tooth space cut",
            "sketch":"tooth_space_sketch.sketch","direction":"normal","end_condition":"length","depth":width,"require_fully_defined":False}},
        {"id":"tooth_space_pattern","scenario":"circular_pattern","params":{"name":label+" tooth space pattern",
            "source":"tooth_space_cut.feature","axis":"input.axis","count":count,"span_angle":360.0,"parameterize":False}}]
    if ops!=expected_ops or len(entities)!=6:
        raise ValueError("Input hub differs from source-free finite cutter")
    r._spline_space_guard(entities,g)
    # Check the actual nominal tooth counterpart, not merely an equal-area sector.
    half,fillet = r._number(g["tooth_width_mm"])/2,r._number(g["fillet_mm"])
    y = math.sqrt((root+fillet)**2-(half+fillet)**2)
    cm = [-half-fillet,y];fm = [-half,y];bm = [v*root/(root+fillet) for v in cm]
    tm = [-half,math.sqrt(floor**2-half**2)]
    mirror = lambda p:[-p[0],p[1]]
    cp,fp,bp,tp = map(mirror,(cm,fm,bm,tm))
    cosine,sine = math.cos(math.pi/count),math.sin(math.pi/count)
    rotate = lambda p:[p[0]*cosine+p[1]*sine,p[1]*cosine-p[0]*sine]
    expected = [("arc",bp,fp,cp,fillet),("segment",fp,tp,None,None),("arc",tp,tm,[0,0],floor),
        ("segment",tm,fm,None,None),("arc",fm,bm,cm,fillet),("arc",bm,bp,[0,0],root)]
    for entity,(kind,start,end,centre,rad) in zip(entities,expected):
        if entity["kind"]!=kind:raise ValueError("Wrong internal spline contour kind")
        positions = [("start",start),("end",end)]
        if centre is not None:positions.append(("center",centre))
        for key,p in positions:
            for a,c in zip(entity[key],rotate(p)):r._close(a,c)
        if rad is not None:r._close(entity["radius"],rad)
    single = r._number(g["space_area_mm2"])*width/1000
    removed = single*count
    r._close(application["expected_single_space_removal_cm3"],single,1e-9)
    r._close(application["expected_removal_cm3"],removed,1e-9)
    blank = r._volume(stock["segments"])-r._volume(bore["segments"])
    if not 0<removed<blank:raise ValueError("Input hub must retain a positive wall")
    if application["capabilities"]!={"creates_blank":False,"internal_spline":True,"tip_chamfer":False,
            "tool_runout":False,"in_place_recipe_editing":False,"native_execution_implemented":False} or application["verification"]!={
            "verified":False,"native_span_audit_required":True,"native_pattern_removal_audit_required":True,
            "native_protected_stock_audit_required":True,"numeric_profile_readback_required":True,"functional_length_verified":False}:
        raise ValueError("Input hub must retain unverified preflight capabilities")
    expected_guard = {"schema":"geomwright.straight_spline.input_carrier.guard","version":1,
        "scope":"through_internal_spline_cylinder_positive_x","target":steps[1]["id"],"stock_target":steps[0]["id"],
        "carrier_span_mm":bore["axial_interval_mm"],"working_span_mm":[lo,hi],"carrier_radius_mm":floor,"root_radius_mm":root,
        "stock_outer_radius_mm":radius,"bore_length_expression":steps[1]["namespace"]+"_L1","protected_stock":[],
        "expected_blank_volume_cm3":blank,"expected_removed_cm3":application["expected_removal_cm3"],
        "expected_final_volume_cm3":blank-application["expected_removal_cm3"],"body_count":1,
        "native_carrier_verified":False,"material_preservation_verified":False}
    if blind:
        expected_guard["scope"]=scope
        expected_guard["bore_depth_expression"]=expected_guard.pop("bore_length_expression")
        expected_guard.update(stock_span_mm=stock["axial_interval_mm"],smooth_tail_span_mm=[hi,bore["end_mm"]],
            bottom_stock_mm=stock["end_mm"]-bore["end_mm"],terminal_end_policy="flat_numeric_cutter_without_runout")
    if guard!=expected_guard:raise ValueError("Input hub guard differs from original stock/bore")
    return steps


def validate_plan(r, plan):
    """Validate the public wrapper before COM; family guard owns cutter semantics."""
    if plan.get("schema") != "geomwright.construction_chain.plan" or plan.get("version") != 1:
        raise ValueError("Invalid input spline chain plan version")
    steps, recipe = plan["steps"], plan["recipe"]
    if not 2 <= len(steps) <= 32 or recipe.get("schema") != r.SCHEMA or recipe.get("version") != 1:
        raise ValueError("Invalid input spline chain recipe")
    prefix, step, original = plan["spline_prefix_plan"], steps[-1], recipe["steps"][-1]
    if prefix["recipe"] != {**recipe, "steps": recipe["steps"][:-1]} or prefix["steps"] != steps[:-1]:
        raise ValueError("Input spline prefix differs from combined plan")
    if (step["module"] != "straight_spline" or original["module"] != "straight_spline" or
            step["basis"] != "input" or step["material"] != "remove" or
            original["basis"] != "input" or original["material"] != "remove" or
            step["id"] != original["id"] or step["target"] != original["target"] or
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", step["id"]) or
            step["id"].upper() in {s["id"].upper() for s in steps[:-1]} or
            step["namespace"] != "CH_"+step["id"].upper()):
        raise ValueError("Invalid terminal input spline identity/mode")
    application, guard = step["spline_application"], step["spline_guard"]
    r._straight_spline_input_carrier_guard(prefix, guard, application)
    if (application["name"] != "Straight spline input ["+step["id"]+"]" or
            {k:v for k,v in original["parameters"].items() if k!="exit_mode"} != application["profile_request"] or guard["target"] != step["target"]):
        raise ValueError("Input spline family parameters/target differ from recipe")
    placement = original["placement"]
    lo, hi = guard["working_span_mm"]
    start, end = guard["carrier_span_mm"]
    blind = guard.get("scope") == "blind_internal_spline_cylinder_positive_x"
    hub = blind or guard.get("scope") == "through_internal_spline_cylinder_positive_x"
    mode = original["parameters"].get("exit_mode","through")
    if (hub and mode != ("blind" if blind else "through") or
            not hub and "exit_mode" in original["parameters"]):
        raise ValueError("Spline exit_mode differs from native carrier scope")
    if (placement.get("reference") != {"step":step["target"], "anchor":"start"} or
            placement.get("direction") != 1 or placement.get("axis") != "global_x" or
            placement.get("phase_degrees") != 0 or step["placement"] != {"origin_mm":lo,"direction":1} or
            not (lo==start and (hi<end-1e-5 if blind else hi==end) if hub else start+1e-5 < lo < hi < end-1e-5)):
        raise ValueError("Input spline requires +X placement and positive smooth margins")
    r._close(r._number(placement["offset_mm"]), lo-start)
    radius, root = guard["carrier_radius_mm"], guard["root_radius_mm"]
    segment = lambda value: {"axial_min":lo,"axial_max":hi,"start_radius_mm":value,"end_radius_mm":value}
    expected_section = {"axis":"global_x","phase_degrees":0,"axial_interval_mm":[lo,hi],
        "start_mm":lo,"end_mm":hi,"shape":"blind_input_spline_hub" if blind else "through_input_spline_hub" if hub else "bounded_input_spline","material_role":"removed",
        "segments":[segment(radius)],"inner_segments":[segment(root)]}
    if step["section"] != expected_section or plan.get("expected_body_count") != 1:
        raise ValueError("Input spline working section differs from carrier")
    r._close(step["expected_delta_cm3"], -guard["expected_removed_cm3"], 1e-6)
    for value in (step["expected_total_volume_cm3"], plan["expected_total_volume_cm3"]):
        r._close(value, guard["expected_final_volume_cm3"], 1e-6)
    r._bounded({"schema":r.SCHEMA,"version":1,"recipe":recipe,"expectations":r._expectations(steps),"outputs":[]})
    return steps


def validate_envelope(r, plan, envelope):
    steps = validate_plan(r, plan)
    if envelope["recipe"] != plan["recipe"] or envelope["expectations"] != r._expectations(steps):
        raise ValueError("Saved input spline recipe/expectations differ from host plan")
    checkpoint = envelope["spline_audit"]
    terminal = steps[-1]
    saved = _validate_checkpoint(r, plan["spline_prefix_plan"], terminal["spline_guard"], terminal["spline_application"], checkpoint)
    if len(envelope["outputs"]) != len(saved):
        raise ValueError("Saved spline envelope ownership is incomplete")
    for out, recorded, step in zip(envelope["outputs"], saved, steps):
        if (out["id"],out["namespace"],out["section"]) != (recorded["id"],recorded["namespace"],step["section"]):
            raise ValueError("Saved spline envelope identity/section differs")
        for key in ("sketch","feature","macro"):
            if (out[key]["object_id"],out[key]["name"]) != (recorded[key]["object_id"],recorded[key]["name"]):
                raise ValueError("Saved spline envelope primary ownership differs")
        signature = lambda row: sorted((o["collection"],o["object_id"],o["name"],o.get("require_fully_defined",True)) for o in row.get("owned_objects",[]))
        if signature(out) != signature(recorded):
            raise ValueError("Saved spline envelope owned roots differ")
    return checkpoint


def snapshot(b, r, app, doc, plan, guard):
    metrics = r._exact_document_body_metrics(b, app, doc)
    bodies = b._ensure_dispatch_sequence(b._cast_to_com_interface(doc.TopPart,"IFeature7").ResultBodies)
    if len(bodies) != 1 or metrics["body_count"] != 1 or not metrics["solid"]:
        raise RuntimeError("Input spline requires one solid final body")
    body = b._cast_to_com_interface(bodies[0],"IBody7")
    box = body.GetGabarit()
    if not isinstance(box,tuple) or len(box) != 7 or not box[0]:
        raise RuntimeError("Input spline native bounds unavailable")
    lo,hi = guard["working_span_mm"]
    root,outer = guard["root_radius_mm"],guard["carrier_radius_mm"]
    blind = guard.get("scope") == "blind_internal_spline_cylinder_positive_x"
    hub = blind or guard.get("scope") == "through_internal_spline_cylinder_positive_x"
    stock = [row for step in plan["steps"] for row in step["section"]["segments"]]
    ends = {row[key] for row in stock for key in ("axial_min","axial_max")}
    faces = b._ensure_dispatch_sequence(b._cast_to_com_interface(body,"IFeature7").ModelObjects(6))
    if not 1 <= len(faces) <= 256:
        raise RuntimeError("Spline face budget exceeded")
    protected,inner,zone = [],[],[]
    tail,terminal_faces = [],[]
    point_count = 0
    for obj in faces:
        face = b._cast_to_com_interface(obj,"IFace")
        cylinder = bool(b.safe_get(face,"IsCylinder",False))
        cone = bool(b.safe_get(face,"IsCone",False))
        plane = bool(b.safe_get(face,"IsPlanar",False))
        axial = False
        if plane:
            surface = b._cast_to_com_interface(face.MathSurface,"IMathSurface3D")
            normal = r._point_result(surface.GetNormal((surface.ParamUMin+surface.ParamUMax)/2,
                                                       (surface.ParamVMin+surface.ParamVMax)/2))
            axial = abs(normal[0]) > 1e-9 and math.hypot(*normal[1:]) <= abs(normal[0])*1e-9
        edges = b._ensure_dispatch_sequence(face.LimitingEdges)
        if len(edges) > 128:
            raise RuntimeError("Spline face-edge budget exceeded")
        coords = []
        for edge in edges:
            curve = b._cast_to_com_interface(edge.MathCurve,"IMathCurve3D")
            a,c = r._number(curve.ParamMin),r._number(curve.ParamMax)
            point_count += 33
            if point_count > 65536:
                raise RuntimeError("Spline boundary sample budget exceeded")
            coords.extend(r._point_result(curve.GetPoint(a+(c-a)*i/32)) for i in range(33))
        if not coords:
            raise RuntimeError("Spline face has no trimmed boundary")
        for q in coords:
            radius = math.hypot(q[1],q[2])
            working = lo-1e-5 <= q[0] <= hi+1e-5 and root-1e-5 <= radius <= outer+1e-5
            if working and (hub or radius < outer-1e-5):
                inner.append(q)
            original = False
            for row in stock:
                if row["axial_min"]-1e-5 <= q[0] <= row["axial_max"]+1e-5:
                    x = min(row["axial_max"],max(row["axial_min"],q[0]))
                    rad = r._radius(row,x)
                    original = original or ((cylinder or cone) and abs(radius-rad) <= 1e-5)
                    original = original or (axial and any(abs(q[0]-end) <= 1e-5 for end in ends) and radius <= rad+1e-5)
            if not working and not original:
                raise RuntimeError("Spline boundary escapes working shell or original stock")
            if hub and radius < root-1e-5:
                raise RuntimeError("Internal spline boundary escaped immutable bore core")
        xs = [q[0] for q in coords]
        radii = [math.hypot(q[1],q[2]) for q in coords]
        x0,x1 = min(xs),max(xs)
        if blind and cylinder and abs(r._number(b.safe_get(face,"Radius"))-root)<=1e-5:
            if not r._coaxial_surface(b,face,True,[root]):
                raise RuntimeError("Smooth blind bore tail lost its original coaxial cylinder")
            tail.extend(q for q in coords if hi-1e-5<=q[0]<=guard["carrier_span_mm"][1]+1e-5)
        if blind and axial and abs(x0-hi)<=1e-5 and abs(x1-hi)<=1e-5:
            terminal_faces.append({"x_span_mm":[x0,x1],"radius_bounds_mm":[min(radii),max(radii)],
                "area_mm2":r._number(face.GetArea(1))})
        if x0 <= hi+1e-5 and x1 >= lo-1e-5:
            zone.append({"points":sorted(r._normalized(q) for q in coords),
                "area_mm2":round(r._number(face.GetArea(1)),5),
                "kind":"cylinder" if cylinder else "cone" if cone else "plane" if plane else "other"})
        # A cylinder spanning the work zone is trimmed, not a protected whole face.
        old_end = axial and abs(x1-x0) <= 1e-5 and any(abs(x0-end) <= 1e-5 for end in ends)
        protected_hub_wall = hub and cylinder and all(abs(value-guard["stock_outer_radius_mm"])<=1e-5 for value in radii)
        protect = (protected_hub_wall or blind and old_end and x0>hi+1e-5) if hub else old_end or x1 < lo-1e-5 or x0 > hi+1e-5
        if protect:
            if not (plane or cone or cylinder):
                raise RuntimeError("Protected spline stock has an unsupported curved face")
            protected.append({"kind":"cylinder" if cylinder else "cone" if cone else "plane",
                "x_span_mm":[round(x0,6),round(x1,6)],
                "radius_bounds_mm":[round(min(radii),6),round(max(radii),6)],
                "area_mm2":round(r._number(face.GetArea(1)),5)})
    return {"body_count":1,"solid":True,"volume_cm3":r._number(metrics["volume"]),
        "bounds_mm":list(box[1:]),"protected_faces":sorted(protected,key=lambda row:json.dumps(row,sort_keys=True)),
        "inner_boundary_span_mm":[min(q[0] for q in inner),max(q[0] for q in inner)] if inner else None,
        "minimum_working_radius_mm":min(math.hypot(q[1],q[2]) for q in inner) if inner else None,
        **({"maximum_working_radius_mm":max(math.hypot(q[1],q[2]) for q in inner) if inner else None} if hub else {}),
        **({"smooth_bore_tail_span_mm":[min(q[0] for q in tail),max(q[0] for q in tail)] if tail else None,
            "terminal_faces":terminal_faces} if blind else {}),
        "sampled_geometry":True,"native_point_count":point_count,
        "working_geometry_hash":r._hash(sorted(zone,key=lambda row:json.dumps(row,sort_keys=True)))}


def verify(r, before, after, guard, application, single=False):
    r._close(before["volume_cm3"],guard["expected_blank_volume_cm3"],1e-6)
    for body in (before,after):
        if body.get("body_count") != 1 or body.get("solid") is not True or len(body.get("bounds_mm",[])) != 6:
            raise ValueError("Spline audit requires one solid and six bounds")
        if r._number(body["volume_cm3"]) <= 0:
            raise ValueError("Spline body must have positive native volume")
    for a,c in zip(before["bounds_mm"],after["bounds_mm"]):
        r._close(a,c)
    if not before.get("protected_faces") or after["protected_faces"] != before["protected_faces"]:
        raise RuntimeError("Input spline changed protected stock faces")
    span = after.get("inner_boundary_span_mm")
    if not isinstance(span,list) or len(span) != 2:
        raise RuntimeError("Spline working boundary span unavailable")
    for a,c in zip(span,guard["working_span_mm"]):
        r._close(a,c)
    r._close(after["minimum_working_radius_mm"],guard["root_radius_mm"])
    blind = guard.get("scope") == "blind_internal_spline_cylinder_positive_x"
    if blind or guard.get("scope") == "through_internal_spline_cylinder_positive_x":
        r._close(after.get("maximum_working_radius_mm"),guard["carrier_radius_mm"])
    if blind:
        tail = after.get("smooth_bore_tail_span_mm")
        if not isinstance(tail,list) or len(tail)!=2:raise RuntimeError("Blind spline smooth tail readback unavailable")
        for a,c in zip(tail,guard["smooth_tail_span_mm"]):r._close(a,c)
        terminal = after.get("terminal_faces",[])
        expected_count = 1 if single else application["geometry"]["tooth_count"]
        if len(terminal)!=expected_count:raise RuntimeError("Blind spline requires one flat terminal face per cut")
        for face in terminal:
            for value in face["x_span_mm"]:r._close(value,guard["working_span_mm"][1])
            r._close(face["radius_bounds_mm"][0],guard["root_radius_mm"])
            r._close(face["radius_bounds_mm"][1],guard["carrier_radius_mm"])
            r._close(face["area_mm2"],application["geometry"]["space_area_mm2"],.001,.0005)
    one = application["expected_single_space_removal_cm3"]
    expected = one if single else application["expected_removal_cm3"]
    removed = r._number(before["volume_cm3"])-r._number(after["volume_cm3"])
    tolerance = min(max(1e-6,expected*.0005),one/2)
    if removed <= 0 or abs(removed-expected) > tolerance:
        raise RuntimeError("Spline actual removal differs from exact family space area/length/count")
    return {"verified":True,"removed_cm3":removed,"expected_removed_cm3":expected,
        "working_span_mm":guard["working_span_mm"],"protected_face_count":len(after["protected_faces"]),
        "sampled_geometry":True,"saved_recipe_updated":False,
        **({"smooth_tail_verified":True,"flat_terminal_faces_verified":True,"bottom_stock_mm":guard["bottom_stock_mm"],
            "terminal_end_policy":guard["terminal_end_policy"],"functional_length_verified":False} if blind else {})}


def _independent_length_expression(r, expression, width):
    """AddVariable installs a numeric Expression even for an independent Value."""
    literal = str(expression or "").strip()
    if literal:
        try:
            r._close(float(literal.replace(",",".")),width)
        except (ValueError,RuntimeError) as exc:
            raise RuntimeError("Blind spline requires an independent numeric working-length input") from exc


def audit(b, r, doc, plan, guard, application, outputs):
    """Current owned roots/profile/driver/pattern at supplied inputs; no writes."""
    r._straight_spline_input_carrier_guard(plan,guard,application)
    model = b.cast_model_container(doc.TopPart)
    outputs = r._ownership(b,model,outputs,strict_names=True,document=doc)
    out = outputs[-1]
    by_role = {row["role"]:row for row in out["owned_objects"]}
    collections = {"origin":"Points3D","plane":"Planes3D","profile":"Sketchs","axis_end":"Points3D",
                   "axis":"Axes3D","source_cut":"Extrusions","pattern":"FeaturePatterns"}
    ids = [row.get("object_id") for row in out["owned_objects"]]
    if (len(ids) != 7 or not all(ids) or len(set(ids)) != 7 or set(by_role) != set(collections) or
            any(row["collection"] != collections[role] for role,row in by_role.items()) or
            out["sketch"]["reference"] != by_role["profile"]["reference"] or
            out["feature"]["reference"] != by_role["pattern"]["reference"]):
        raise ValueError("Spline ownership needs its seven explicit created roots")
    def obj(role, interface):
        row = by_role[role]
        found = b._cast_to_com_interface(doc,"IKompasDocument1").FindObjectById(row["object_id"],None)
        if found is None:
            raise RuntimeError("Owned spline object missing")
        return b._cast_to_com_interface(found,interface)
    cut = obj("source_cut","IExtrusion")
    if int(cut.Direction) != 0 or (cut.ExtrusionType(True),cut.ExtrusionType(False)) != (0,0):
        raise RuntimeError("Spline cut ending/direction changed")
    ns = out["namespace"]
    variables = {b.safe_get(v,"Name"):v for v in b._iter_operation_variables(doc.TopPart)}
    length = variables.get(ns+"_L1")
    if length is None or b.safe_get(length,"Information",True) or b.safe_get(length,"ReadOnly",True):
        raise RuntimeError("Spline length input must be writable and driving")
    width = application["geometry"]["length_mm"]
    r._close(b.safe_get(length,"Value"),width)
    if guard.get("scope") == "through_internal_spline_cylinder_positive_x":
        if str(b.safe_get(length,"Expression") or "").strip().casefold()!=guard["bore_length_expression"].casefold():
            raise RuntimeError("Internal spline depth input is not linked to immutable bore length")
        bore_length = variables.get(guard["bore_length_expression"])
        if bore_length is None:raise RuntimeError("Input hub bore length driver is missing")
        r._close(b.safe_get(bore_length,"Value"),width)
    elif guard.get("scope") == "blind_internal_spline_cylinder_positive_x":
        _independent_length_expression(r,b.safe_get(length,"Expression"),width)
        bore_depth = variables.get(guard["bore_depth_expression"])
        if bore_depth is None:raise RuntimeError("Blind input bore depth driver is missing")
        r._close(b.safe_get(bore_depth,"Value"),guard["carrier_span_mm"][1]-guard["carrier_span_mm"][0])
    depths = list(b._iter_operation_variables(cut))
    active = [v for v in depths if b.safe_get(v,"ParameterNote") in ("Distance 1","Расстояние 1")]
    inactive = [v for v in depths if b.safe_get(v,"ParameterNote") in ("Distance 2","Расстояние 2")]
    if len(active) != 1 or len(inactive) != 1 or b.safe_get(active[0],"Information",True) or b.safe_get(active[0],"ReadOnly",True):
        raise RuntimeError("Spline native depth driver unavailable")
    if str(b.safe_get(active[0],"Expression") or "").strip().casefold() != (ns+"_L1").casefold():
        raise RuntimeError("Spline native depth is not bound to its owned length input")
    r._close(b.safe_get(active[0],"Value"),width)
    r._close(b.safe_get(inactive[0],"Value"),0)
    pattern = obj("pattern","ICircularPattern")
    count = application["geometry"]["tooth_count"]
    r._close(pattern.Count2,count)
    r._close(pattern.Step2,360/count,1e-7)
    sources = [b.safe_get(o,"Reference") for o in b._ensure_dispatch_sequence(pattern.InitialObjects)]
    if sources != [by_role["source_cut"]["reference"]] or b.safe_get(pattern.Axis,"Reference") != by_role["axis"]["reference"]:
        raise RuntimeError("Spline pattern source/axis ownership changed")
    profile = r._profile_readback(b,model,by_role["profile"]["reference"],
        application["operations"][0]["params"]["entities"],application["geometry"]["space_entity_count"])
    return {"verified":True,"outputs":outputs,"profile":profile,
        "drivers":{"verified":True,"length_mm":width,"expression":ns+"_L1"},"pattern_count":count}


def execute(b, r, app, doc, plan, guard, application, step_id, confirm_write=False):
    if confirm_write is not True:
        raise ValueError("Input spline application requires explicit write confirmation")
    if (not isinstance(step_id,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}",step_id) or
            step_id.upper() in {s["id"].upper() for s in plan["steps"]} or
            application["name"] != "Straight spline input ["+step_id+"]"):
        raise ValueError("Input spline requires a new canonical instance identity")
    ns = "CH_"+step_id.upper()
    context = r._straight_spline_input_carrier_context(b,app,doc,plan,guard,application)
    model,part = b.cast_model_container(doc.TopPart),doc.TopPart
    if ns+"_L1" in {str(b.safe_get(v,"Name") or "").upper() for v in b._iter_operation_variables(part)}:
        raise ValueError("Input spline driver namespace already exists")
    before = snapshot(b,r,app,doc,plan,guard)
    r._close(before["volume_cm3"],guard["expected_blank_volume_cm3"],1e-6)
    inventory = r._thread_runtime()._inventory(b,r,model)
    width = application["geometry"]["length_mm"]
    installed = b._apply_part_variables(part,[{"name":ns+"_L1","expression":guard.get("bore_length_expression",""),"value":width,
        "unit_category":"linear","precision":6}])
    if not installed.get("ok"):
        raise RuntimeError("Spline length driver installation failed")
    label = application["name"]
    lo = guard["working_span_mm"][0]
    origin = b._create_point3d(model,label+" origin",[lo,0,0])
    plane = b._create_plane_parallel_by_point(part,label+" profile plane",part.DefaultObject(3),origin)
    sketch = model.Sketchs.Add()
    sketch.CoordinateSystem = plane
    sketch.Plane = plane
    sketch.Name = application["operations"][0]["params"]["name"]
    sketch.Fixed = True
    if not sketch.Update():
        raise RuntimeError("Spline input sketch placement failed")
    b._create_sketch_entities(model,part,{"create_new_sketch":False,
        "sketch_ref":str(b.safe_get(sketch,"Reference")),"entities":application["operations"][0]["params"]["entities"]})
    axis_end = b._create_point3d(model,label+" axis end",[lo+1,0,0])
    axis = b._create_axis3d_by_2_points(part,label+" axis",origin,axis_end)
    runtime = {"input":{"scenario":"cylindrical_blank","axis":axis},
        "tooth_space_sketch":{"scenario":"numeric_profile_sketch","sketch":sketch,"feature":sketch}}
    reports = []
    b._execute_workflow_operation(part,model,application["operations"][1],runtime,reports,bounded_cut_depth=width)
    cut = runtime["tooth_space_cut"]["feature"]
    binding = b._bind_extrusion_operation_variables(cut,{"operation_variable_bindings":[{
        "target":"extrusion","parameter_note":"Distance 1","parameter_note_aliases":["Distance 1","Расстояние 1"],
        "expression":ns+"_L1","role":"working_depth"}]},"cut_extrusion")
    source = snapshot(b,r,app,doc,plan,guard)
    verify(r,before,source,guard,application,single=True)
    b._execute_workflow_operation(part,model,application["operations"][2],runtime,reports)
    pattern = runtime["tooth_space_pattern"]["feature"]
    roots = [("origin","Points3D",origin),("plane","Planes3D",plane),("profile","Sketchs",sketch),
        ("axis_end","Points3D",axis_end),("axis","Axes3D",axis),("source_cut","Extrusions",cut),
        ("pattern","FeaturePatterns",pattern)]
    current = r._thread_runtime()._inventory(b,r,model)
    if any(not set(inventory[k]) <= set(current[k]) for k in inventory):
        raise RuntimeError("Spline application removed earlier root identities")
    owned = [{"role":role,"collection":collection,"reference":b.safe_get(obj,"Reference"),
        "name":b.safe_get(obj,"Name"),"require_fully_defined":False} for role,collection,obj in roots]
    refs = [row["reference"] for row in owned]
    if not all(refs) or len(set(refs)) != 7 or any(row["reference"] in inventory[row["collection"]] for row in owned):
        raise RuntimeError("Spline ownership must contain exactly newly created explicit roots")
    out = {"id":step_id,"namespace":ns,"owned_objects":owned,
        "sketch":owned[2].copy(),"feature":owned[6].copy()}
    r._group_step(b,model,{"owned_objects":[obj for _,_,obj in roots]},out)
    outputs = r._ownership(b,model,context["prefix_outputs"]+[out],strict_names=True,document=doc)
    hidden = b._hide_auxiliary_model_objects([(role,obj) for role,_,obj in roots if role not in ("source_cut","pattern")],hidden=True)
    if any(not row.get("ok") for row in hidden.get("objects",[])):
        raise RuntimeError("Hiding exact owned spline supports failed")
    after = snapshot(b,r,app,doc,plan,guard)
    verification = verify(r,before,after,guard,application)
    # The exact source-cut mass plus complete final mass defeats omitted copies.
    single = before["volume_cm3"]-source["volume_cm3"]
    r._close(verification["removed_cm3"],single*application["geometry"]["tooth_count"],
             min(max(1e-6,verification["removed_cm3"]*.0005),single/2))
    audited = audit(b,r,doc,plan,guard,application,outputs)
    complete_inventory = inventory_snapshot(b,r,doc,application,audited["outputs"])
    return {"ok":True,"spline_executed":True,"verification":verification,"drivers":audited["drivers"],
        "profile":audited["profile"],"body_before":before,"body_after":after,"body_source":source,
        "prefix_outputs":audited["outputs"][:-1],"output":audited["outputs"][-1],
        "binding":binding,"hidden":hidden,"reports":reports,"whole_inventory_verified":True,
        "inventory":complete_inventory}


CHECKPOINT_SCHEMA = "geomwright.construction_chain.spline_audit"
ARRAY_POLICY = {"Step1":0,"StepByAxis":0,"BuildingType":0,
    "BoundaryInstancesStepFactor1":False,"BoundaryInstancesStepFactor2":False,
    "ReverseDirection":False,"SaveInitialOrientation":False}


def _root_counts(r, outputs):
    counts = {key:0 for key in r._thread_runtime().COLLECTIONS}
    for out in outputs:
        roots = out.get("owned_objects") or [dict(out[key],collection=collection)
            for key,collection in (("sketch","Sketchs"),("feature","Rotateds"))]
        for row in roots:
            counts[row["collection"]] += 1
        if out.get("macro",{}).get("grouped"):
            counts["MacroObjects3D"] += 1
    return counts


def inventory_snapshot(b, r, doc, application, outputs):
    """Exact root set plus native-linked copies and bounded unaddressable records.

    Cache points are not adopted as owned roots and receive no invented IDs.
    This version deliberately supports one single-row circular array only.
    """
    model = b.cast_model_container(doc.TopPart)
    current = r._thread_runtime()._inventory(b,r,model)
    expected = {key:set() for key in current}
    for out in outputs:
        roots = out.get("owned_objects") or [dict(out[key],collection=collection)
            for key,collection in (("sketch","Sketchs"),("feature","Rotateds"))]
        for row in roots:
            expected[row["collection"]].add(row["reference"])
        if out.get("macro",{}).get("grouped"):
            expected["MacroObjects3D"].add(out["macro"]["reference"])
    if any(not refs <= set(current[key]) for key,refs in expected.items()):
        raise RuntimeError("Spline final inventory lost explicit owned roots")
    extras = {key:set(current[key])-expected[key] for key in current}
    if any(refs for key,refs in extras.items() if key not in ("Extrusions","Points3D")):
        raise RuntimeError("Spline final inventory contains unrelated roots")
    count = application["geometry"]["tooth_count"]
    if len(extras["Extrusions"]) != count-1 or len(extras["Points3D"]) != count-1:
        raise RuntimeError("Spline generated copy/cache count differs from the circular array")
    identity = b._cast_to_com_interface(doc,"IKompasDocument1")
    roles = {row["role"]:row for row in outputs[-1]["owned_objects"]}
    pattern = b._cast_to_com_interface(identity.FindObjectById(roles["pattern"]["object_id"],None),"ICircularPattern")
    dimensions = pattern.GetExemplarsCounts()
    if not dimensions or not dimensions[0] or tuple(dimensions[1:]) != (1,count) or pattern.Count1 != 1:
        raise RuntimeError("Spline inventory requires the complete single-row circular array")
    # The workflow explicitly rotates tooth-space copies with the array.
    # Its override is False, unlike the low-level factory's default True.
    for field,expected_value in ARRAY_POLICY.items():
        if b.safe_get(pattern,field) != expected_value:
            raise RuntimeError("Spline array placement policy changed: "+field)
    instances = {b.safe_get(pattern.Exemplar(1,index),"Reference"):index for index in range(2,count+1)}
    if None in instances or len(instances) != count-1:
        raise RuntimeError("Spline native array instance identities unavailable")
    copies = []
    for ref in extras["Extrusions"]:
        obj = current["Extrusions"][ref]
        owner = b.safe_get(b._cast_to_com_interface(obj,"IFeature7"),"OwnerFeature")
        owner_ref = b.safe_get(b._cast_to_com_interface(owner,"IModelObject"),"Reference") if owner is not None else None
        array = b.safe_get(b._cast_to_com_interface(owner,"IFeature7"),"OwnerFeature") if owner is not None else None
        array_ref = b.safe_get(b._cast_to_com_interface(array,"IModelObject"),"Reference") if array is not None else None
        if owner_ref not in instances or array_ref != roles["pattern"]["reference"]:
            raise RuntimeError("Unowned extrusion is not a child of our native circular array")
        if b.safe_get(b._cast_to_com_interface(obj,"IExtrusion").Sketch,"Reference") != roles["profile"]["reference"]:
            raise RuntimeError("Native spline copy uses a foreign profile")
        pid = identity.GetObjectId(b._cast_to_com_interface(obj,"IKompasAPIObject"),None)
        if not isinstance(pid,str) or not 1 <= len(pid) <= 512:
            raise RuntimeError("Native spline copy persistent identity unavailable")
        copies.append({"index":instances[owner_ref],"object_id":pid})
    if len({row["index"] for row in copies}) != count-1 or len({row["object_id"] for row in copies}) != count-1:
        raise RuntimeError("Native spline copy identities are duplicated")
    part_ref = b.safe_get(b._cast_to_com_interface(doc.TopPart,"IModelObject"),"Reference")
    for ref in extras["Points3D"]:
        obj = current["Points3D"][ref]
        point = b._cast_to_com_interface(obj,"IPoint3D")
        pid = identity.GetObjectId(b._cast_to_com_interface(obj,"IKompasAPIObject"),None)
        parent = b.safe_get(point,"Parent")
        parent_ref = b.safe_get(b._cast_to_com_interface(parent,"IModelObject"),"Reference") if parent is not None else None
        if (pid != "" or b.safe_get(point,"Name") != "" or point.Type != 11014 or point.ModelObjectType != 70 or
                point.ParameterType != 1 or point.AssociationObject is not None or parent_ref != part_ref or
                b.safe_get(b._cast_to_com_interface(point.Owner,"IModelObject"),"Reference") != ref or
                any(r._number(value) != 0 for value in (point.X,point.Y,point.Z))):
            raise RuntimeError("Unowned point is not a supported unaddressable coordinate record")
    return {"counts":{key:len(rows) for key,rows in current.items()},
        "copies":sorted(copies,key=lambda row:row["index"]),
        "ephemeral_points":{"count":count-1,"policy":"empty_id_zero_coordinate_self_owned_top_part_records_v1"}}


def _protected_baseline(plan, guard):
    blind = guard.get("scope") == "blind_internal_spline_cylinder_positive_x"
    if blind or guard.get("scope") == "through_internal_spline_cylinder_positive_x":
        lo,hi = guard["stock_span_mm"] if blind else guard["working_span_mm"]
        radius = guard["stock_outer_radius_mm"]
        result = [{"kind":"cylinder","x_span_mm":[round(lo,6),round(hi,6)],
            "radius_bounds_mm":[round(radius,6),round(radius,6)],"area_mm2":round(2*math.pi*radius*(hi-lo),5)}]
        if blind:
            for x,rad in ((guard["carrier_span_mm"][1],guard["root_radius_mm"]),(hi,radius)):
                result.append({"kind":"plane","x_span_mm":[round(x,6),round(x,6)],
                    "radius_bounds_mm":[round(rad,6),round(rad,6)],"area_mm2":round(math.pi*rad*rad,5)})
        return sorted(result,key=lambda row:json.dumps(row,sort_keys=True))
    stock = [row for step in plan["steps"] for row in step["section"]["segments"]]
    lo,hi = guard["working_span_mm"]
    result = []
    for row in stock:
        a,c = row["axial_min"],row["axial_max"]
        if c < lo-1e-5 or a > hi+1e-5:
            ra,rc = row["start_radius_mm"],row["end_radius_mm"]
            result.append({"kind":"cylinder" if ra == rc else "cone","x_span_mm":[round(a,6),round(c,6)],
                "radius_bounds_mm":[round(min(ra,rc),6),round(max(ra,rc),6)],
                "area_mm2":round(math.pi*(ra+rc)*math.hypot(c-a,rc-ra),5)})
    for x in {row[key] for row in stock for key in ("axial_min","axial_max")}:
        left = max([row["end_radius_mm"] for row in stock if row["axial_max"] == x] or [0])
        right = max([row["start_radius_mm"] for row in stock if row["axial_min"] == x] or [0])
        if left != right:
            radii = [min(left,right),max(left,right)] if min(left,right) else [max(left,right)]*2
            result.append({"kind":"plane","x_span_mm":[round(x,6)]*2,
                "radius_bounds_mm":[round(v,6) for v in radii],"area_mm2":round(math.pi*abs(left**2-right**2),5)})
    return sorted(result,key=lambda row:json.dumps(row,sort_keys=True))


def _profile_stamp(r, application):
    entities = application["operations"][0]["params"]["entities"]
    rows = sorted([r._profile_geometry(e["kind"],e,planned=True) for e in entities],key=lambda row:json.dumps(row,sort_keys=True))
    return {"entity_count":len(rows),"sha256":r._hash(rows),"readback":"inspect_sketch_full_numeric_geometry"}


def _validate_checkpoint(r, plan, guard, application, checkpoint):
    r._straight_spline_input_carrier_guard(plan,guard,application)
    r._bounded(checkpoint)
    if checkpoint.get("schema") != CHECKPOINT_SCHEMA or checkpoint.get("version") != 1:
        raise ValueError("Invalid spline checkpoint version")
    hashes = {"prefix_recipe_hash":r._hash(plan["recipe"]),"prefix_expectations_hash":r._hash(r._expectations(plan["steps"])),
              "application_hash":r._hash(application),"guard_hash":r._hash(guard)}
    if any(checkpoint.get(key) != value for key,value in hashes.items()):
        raise ValueError("Spline checkpoint differs from its original prefix or inputs")
    outputs = checkpoint["outputs"]
    ident = checkpoint["step_id"]
    if (not isinstance(ident,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}",ident) or
            ident.upper() in {s["id"].upper() for s in plan["steps"]} or
            len(outputs) != len(plan["steps"])+1 or [o["id"] for o in outputs] != [s["id"] for s in plan["steps"]]+[ident] or
            [o["namespace"] for o in outputs] != [s["namespace"] for s in plan["steps"]]+["CH_"+ident.upper()] or
            application["name"] != "Straight spline input ["+ident+"]"):
        raise ValueError("Spline checkpoint instance/prefix identity differs")
    ids = []
    for out in outputs:
        roots = out.get("owned_objects") or [out[key] for key in ("sketch","feature")]
        ids.extend(row.get("object_id") for row in roots)
        ids.append(out.get("macro",{}).get("object_id"))
    if not all(isinstance(v,str) and 1 <= len(v) <= 512 for v in ids) or len(set(ids)) != len(ids):
        raise ValueError("Spline checkpoint root IDs must be complete and unique")
    owned = outputs[-1].get("owned_objects",[])
    roles = {row["role"]:row for row in owned}
    collections = {"origin":"Points3D","plane":"Planes3D","profile":"Sketchs","axis_end":"Points3D",
        "axis":"Axes3D","source_cut":"Extrusions","pattern":"FeaturePatterns"}
    names = {"origin":application["name"]+" origin","plane":application["name"]+" profile plane",
        "profile":application["operations"][0]["params"]["name"],"axis_end":application["name"]+" axis end",
        "axis":application["name"]+" axis","source_cut":application["operations"][1]["params"]["name"],
        "pattern":application["operations"][2]["params"]["name"]}
    if len(owned) != 7 or set(roles) != set(collections) or any(
            row["collection"] != collections[role] or row["name"] != names[role] for role,row in roles.items()):
        raise ValueError("Spline checkpoint has foreign or missing owned roots")
    for field,role in (("sketch","profile"),("feature","pattern")):
        if outputs[-1][field]["object_id"] != roles[role]["object_id"]:
            raise ValueError("Spline checkpoint primary identity differs from its owned root")
    if checkpoint.get("profile") != _profile_stamp(r,application):
        raise ValueError("Spline checkpoint profile differs from its exact family contour")
    if not re.fullmatch(r"[0-9a-f]{64}",str(checkpoint.get("working_geometry_hash",""))):
        raise ValueError("Spline checkpoint requires a sampled working geometry fingerprint")
    baseline = checkpoint["baseline"]
    stock = [row for s in plan["steps"] for row in s["section"]["segments"]]
    radius = max(max(row["start_radius_mm"],row["end_radius_mm"]) for row in stock)
    expected_bounds = [min(row["axial_min"] for row in stock),-radius,-radius,max(row["axial_max"] for row in stock),radius,radius]
    if baseline.get("body_count") != 1 or baseline.get("solid") is not True or len(baseline.get("bounds_mm",[])) != 6:
        raise ValueError("Invalid spline checkpoint original stock baseline")
    for a,c in zip(baseline["bounds_mm"],expected_bounds):
        r._close(a,c)
    r._close(baseline["volume_cm3"],guard["expected_blank_volume_cm3"],1e-6)
    if baseline.get("protected_faces") != _protected_baseline(plan,guard):
        raise ValueError("Spline checkpoint protected baseline differs from original stock")
    removed = r._number(baseline["volume_cm3"])-r._number(checkpoint["audited_volume_cm3"])
    tolerance = min(max(1e-6,application["expected_removal_cm3"]*.0005),application["expected_single_space_removal_cm3"]/2)
    if removed <= 0 or abs(removed-application["expected_removal_cm3"]) > tolerance:
        raise ValueError("Spline checkpoint audited volume is outside exact space removal expectation")
    r._close(checkpoint["removed_cm3"],removed,1e-6)
    inventory = checkpoint["inventory"]
    count = application["geometry"]["tooth_count"]
    expected = _root_counts(r,outputs)
    expected["Extrusions"] += count-1
    expected["Points3D"] += count-1
    copies = inventory["copies"]
    copy_ids = [row.get("object_id") for row in copies]
    if (inventory["counts"] != expected or [row.get("index") for row in copies] != list(range(2,count+1)) or
            not all(isinstance(v,str) and 1 <= len(v) <= 512 for v in copy_ids) or len(set(copy_ids)) != count-1 or set(copy_ids)&set(ids) or
            inventory["ephemeral_points"] != {"count":count-1,"policy":"empty_id_zero_coordinate_self_owned_top_part_records_v1"}):
        raise ValueError("Spline checkpoint inventory differs from owned roots and native-derived records")
    return outputs


def make_checkpoint(r, plan, guard, application, result):
    """Pure compact creation/readback evidence; does not save or recognize a recipe."""
    if (result.get("ok") is not True or result.get("spline_executed") is not True or
            result.get("verification",{}).get("verified") is not True or
            result.get("drivers",{}).get("verified") is not True or result.get("whole_inventory_verified") is not True):
        raise ValueError("Spline checkpoint needs complete geometry/driver/inventory evidence")
    verified = verify(r,result["body_before"],result["body_after"],guard,application)
    outputs = r._thread_runtime()._compact_outputs(result["prefix_outputs"]+[result["output"]])
    checkpoint = {"schema":CHECKPOINT_SCHEMA,"version":1,"step_id":outputs[-1]["id"],
        "prefix_recipe_hash":r._hash(plan["recipe"]),"prefix_expectations_hash":r._hash(r._expectations(plan["steps"])),
        "application_hash":r._hash(application),"guard_hash":r._hash(guard),"outputs":outputs,
        "baseline":{key:deepcopy(result["body_before"][key]) for key in ("body_count","solid","volume_cm3","bounds_mm","protected_faces")},
        "audited_volume_cm3":result["body_after"]["volume_cm3"],"removed_cm3":verified["removed_cm3"],
        "profile":deepcopy(result["profile"]),"working_geometry_hash":result["body_after"]["working_geometry_hash"],
        "inventory":deepcopy(result["inventory"])}
    _validate_checkpoint(r,plan,guard,application,checkpoint)
    return checkpoint


def audit_checkpoint(b, r, app, doc, plan, guard, application, checkpoint):
    outputs = _validate_checkpoint(r,plan,guard,application,checkpoint)
    if b.describe_runtime_document(doc,app).get("type") != 10024:
        raise ValueError("Spline checkpoint audit requires an exact part document")
    current = audit(b,r,doc,plan,guard,application,outputs)
    body = snapshot(b,r,app,doc,plan,guard)
    verified = verify(r,checkpoint["baseline"],body,guard,application)
    r._close(body["volume_cm3"],checkpoint["audited_volume_cm3"],1e-6)
    inventory = inventory_snapshot(b,r,doc,application,current["outputs"])
    if (inventory != checkpoint["inventory"] or body["working_geometry_hash"] != checkpoint["working_geometry_hash"] or
            current["profile"] != checkpoint["profile"]):
        raise RuntimeError("Spline inventory/profile/working geometry changed since checkpoint")
    return {"verified":True,"whole_inventory_verified":True,"verification":verified,
            "drivers":current["drivers"],"inventory_counts":inventory["counts"],"body":body}
