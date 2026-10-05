"""Create-only cam plan and verification; no COM and no Studio dependency."""
from __future__ import annotations

import bisect
import math
import json
import hashlib
from typing import Any

from .preview import preview_cam_profile, _selection_issues
from .analyze import self_intersection


class CamBuildError(RuntimeError):
    """A failed owned build, never an instruction to modify the active document."""
    def __init__(self, message: str, partial_result: dict | None = None):
        self.partial_result = partial_result or {"status":"unknown", "verified":False}
        super().__init__(message+" | partial_result="+json.dumps(self.partial_result,ensure_ascii=False))


def _point(segment: list[list[float]], t: float) -> list[float]:
    u = 1.0 - t
    return [u**3 * segment[0][k] + 3*u*u*t*segment[1][k]
            + 3*u*t*t*segment[2][k] + t**3*segment[3][k] for k in (0, 1)]


def _spline(parameters: list[float], points: list[list[float]]) -> list[list[list[float]]]:
    """C2 cubic interpolation, with exact base-circle tangent directions."""
    n = len(parameters)
    h = [parameters[i+1]-parameters[i] for i in range(n-1)]
    slopes = [[(points[i+1][k]-points[i][k])/h[i] for k in (0, 1)] for i in range(n-1)]
    tangents = []
    for index in (0, n-1):
        p = points[index]
        radius = math.hypot(*p)
        direction = [-p[1]/radius, p[0]/radius]
        # Arc-length parameter removes tangential acceleration jumps at the
        # piecewise motion knots. The endpoints have unit circle tangents.
        tangents.append(direction)
    second = []
    for k in (0, 1):
        lower = [0.0]+h[:-1]+[h[-1]]
        upper = [h[0]]+h[1:]+[0.0]
        diag = [2*h[0]]+[2*(h[i-1]+h[i]) for i in range(1,n-1)]+[2*h[-1]]
        rhs = [6*(slopes[0][k]-tangents[0][k])]
        rhs += [6*(slopes[i][k]-slopes[i-1][k]) for i in range(1,n-1)]
        rhs += [6*(tangents[1][k]-slopes[-1][k])]
        for i in range(1,n):
            factor = lower[i]/diag[i-1]
            diag[i] -= factor*upper[i-1]
            rhs[i] -= factor*rhs[i-1]
        values = [0.0]*n
        values[-1] = rhs[-1]/diag[-1]
        for i in range(n-2,-1,-1):
            values[i] = (rhs[i]-upper[i]*values[i+1])/diag[i]
        second.append(values)
    segments = []
    for i, step in enumerate(h):
        d0 = [slopes[i][k]-step*(2*second[k][i]+second[k][i+1])/6 for k in (0,1)]
        d1 = [slopes[i][k]+step*(second[k][i]+2*second[k][i+1])/6 for k in (0,1)]
        segments.append([points[i], [points[i][k]+step*d0[k]/3 for k in (0,1)],
                         [points[i+1][k]-step*d1[k]/3 for k in (0,1)], points[i+1]])
    return segments


def _evaluate(parameters: list[float], segments: list, value: float) -> list[float]:
    i = min(len(segments)-1, max(0, bisect.bisect_right(parameters, value)-1))
    return _point(segments[i], (value-parameters[i])/(parameters[i+1]-parameters[i]))


def _rotate(p: list[float], angle: float) -> list[float]:
    c, s = math.cos(angle), math.sin(angle)
    return [c*p[0]-s*p[1], s*p[0]+c*p[1]]


def _sketch(p: list[float]) -> list[float]:
    # Live-verified YOZ basis: sketch (u,v) maps to global (0,-v,-u).
    # Present the mathematical profile in global (Y,Z), not mirrored in CAD.
    return [-p[1], -p[0]]


def _length_parameters(points: list) -> list[float]:
    parameters = [0.0]
    for a,b in zip(points,points[1:]):
        distance = math.dist(a,b)
        if distance <= 1e-10:
            raise ValueError("cam working profile has repeated or stationary points")
        parameters.append(parameters[-1]+distance)
    return parameters


def _derivatives(segment: list, t: float) -> tuple[list[float], list[float]]:
    u = 1-t
    d = [3*(u*u*(segment[1][k]-segment[0][k])+2*u*t*(segment[2][k]-segment[1][k])+t*t*(segment[3][k]-segment[2][k])) for k in (0,1)]
    dd = [6*(u*(segment[2][k]-2*segment[1][k]+segment[0][k])+t*(segment[3][k]-2*segment[2][k]+segment[1][k])) for k in (0,1)]
    return d,dd


def _radius(segment: list, t: float, *, clockwise: bool = False) -> float:
    d,dd = _derivatives(segment,t)
    speed = math.hypot(*d)
    if speed < 1e-10:
        raise ValueError("actual cam curve has a stationary/cusp point")
    cross = d[0]*dd[1]-d[1]*dd[0]
    if clockwise and cross > 1e-12:
        raise ValueError("actual flat-cam contour contains a concave/undercut region")
    return speed**3/abs(cross) if abs(cross)>1e-12 else math.inf


def _poly_value(coefficients: list[float], t: float) -> float:
    value = 0.0
    for coefficient in reversed(coefficients):
        value = value*t+coefficient
    return value


def _poly_derivative(a: list[float]) -> list[float]:
    return [i*a[i] for i in range(1,len(a))] or [0.0]


def _poly_product(a: list[float], b: list[float]) -> list[float]:
    result = [0.0]*(len(a)+len(b)-1)
    for i,x in enumerate(a):
        for j,y in enumerate(b):
            result[i+j] += x*y
    return result


def _poly_sum(a: list[float], b: list[float], factor: float = 1.0) -> list[float]:
    result = a[:]+[0.0]*max(0,len(b)-len(a))
    for i,x in enumerate(b):
        result[i] += factor*x
    return result


def _unit_roots(coefficients: list[float]) -> list[float]:
    """Isolate real polynomial roots using derivative partitions, including tangencies.

    Degrees are at most five. Normalize before evaluating so tiny CAD spans do
    not disappear behind an absolute coefficient threshold. No external solver.
    """
    scale = max(map(abs,coefficients),default=0.0)
    if scale == 0:
        return []
    a = [x/scale for x in coefficients]
    while len(a)>1 and abs(a[-1])<1e-14:
        a.pop()
    if len(a)==1:
        return []
    if len(a)==2:
        root = -a[0]/a[1]
        return [min(1.0,max(0.0,root))] if -1e-12<=root<=1+1e-12 else []
    boundaries = [0.0]+_unit_roots(_poly_derivative(a))+[1.0]
    roots = [t for t in boundaries if abs(_poly_value(a,t))<=1e-12]
    for lo,hi in zip(boundaries,boundaries[1:]):
        left,right = _poly_value(a,lo),_poly_value(a,hi)
        if left*right >= 0:
            continue
        for _ in range(45):
            mid = (lo+hi)/2
            value = _poly_value(a,mid)
            if left*value <= 0:
                hi = mid
            else:
                lo,left = mid,value
        roots.append((lo+hi)/2)
    return sorted(set(round(t,13) for t in roots))


def _power(segment: list) -> list[list[float]]:
    return [[segment[0][k],3*(segment[1][k]-segment[0][k]),
             3*(segment[2][k]-2*segment[1][k]+segment[0][k]),
             segment[3][k]-3*segment[2][k]+3*segment[1][k]-segment[0][k]] for k in (0,1)]


def _curvature_parameters(segment: list) -> list[float]:
    x,y = map(_poly_derivative,_power(segment))
    xx,yy = _poly_derivative(x),_poly_derivative(y)
    speed2 = _poly_sum(_poly_product(x,x),_poly_product(y,y))
    cross = _poly_sum(_poly_product(x,yy),_poly_product(y,xx),-1)
    # Extrema of radius: 3 Q' C - 2 Q C' = 0, Q=|p'|^2.
    stationary = _poly_sum(_poly_product(_poly_derivative(speed2),cross),
                           _poly_product(speed2,_poly_derivative(cross)),-2/3)
    return sorted(set([0.0,1.0]+_unit_roots(stationary)
                      +_unit_roots(_poly_derivative(speed2))+_unit_roots(cross)
                      +_unit_roots(_poly_derivative(cross))))


def _minimum_radius(segments: list, *, clockwise: bool = False) -> float:
    return min(_radius(segment,t,clockwise=clockwise)
               for segment in segments for t in _curvature_parameters(segment))


def _support(segments: list, base: dict, c: float, s: float) -> list[float]:
    candidates = [base["start"],base["end"]]
    angle = math.atan2(s,c)
    if (base["start_angle"]-angle)%(2*math.pi) <= base["span"]:
        candidates.append([base["radius"]*c,base["radius"]*s])
    for segment in segments:
        x,y = _power(segment)
        projection = _poly_sum([c*v for v in x],[s*v for v in y])
        candidates.extend(_point(segment,t) for t in [0.0,1.0]+_unit_roots(_poly_derivative(projection)))
    return max(candidates,key=lambda p:p[0]*c+p[1]*s)


def _roller_distance(segments: list, base: dict, center: list[float]) -> float:
    distance = min(math.dist(center,base["start"]),math.dist(center,base["end"]))
    angle = math.atan2(center[1],center[0])
    if (base["start_angle"]-angle)%(2*math.pi) <= base["span"]:
        distance = min(distance,abs(math.hypot(*center)-base["radius"]))
    for segment in segments:
        # A Bezier lies inside its control-point hull; prune only with a lower bound.
        lower2 = sum(max(min(p[k] for p in segment)-center[k],0,
                         center[k]-max(p[k] for p in segment))**2 for k in (0,1))
        if lower2>distance*distance:
            continue
        x,y = _power(segment)
        x[0] -= center[0]; y[0] -= center[1]
        stationary = _poly_sum(_poly_product(x,_poly_derivative(x)),_poly_product(y,_poly_derivative(y)))
        distance = min(distance,*(math.dist(_point(segment,t),center)
                                  for t in [0.0,1.0]+_unit_roots(stationary)))
    return distance


def build_cam_plan(request: dict[str, Any], *, width: float = 12.0,
                    rotation_deg: float = 0.0, tolerance: float = 0.01,
                    name: str = "Geomwright cam", studio_profile: dict | None = None) -> dict[str, Any]:
    for key, value, low, high in (("width",width,0,10000), ("tolerance",tolerance,0.0001,0.1)):
        if not math.isfinite(value) or not low < value <= high:
            raise ValueError(f"{key} must be finite and in ({low}, {high}]")
    if not math.isfinite(rotation_deg):
        raise ValueError("rotation_deg must be finite")
    preview = preview_cam_profile({**request, "samples_per_degree": 10.0})
    issues = _selection_issues(preview, preview["spec"])
    if issues:
        raise ValueError("cam build rejected: " + ", ".join(sorted(set(issues))))
    profile = preview["profile"]
    count = profile["active_count"]
    points = [list(p) for p in zip(profile["x"][:count], profile["y"][:count])]
    angles = list(preview["follower"]["theta_deg"])
    if len(angles) != count or angles[-1]-angles[0] >= 359.999:
        raise ValueError("CAD cam requires a nonzero base-circle interval")
    parameters = _length_parameters(points)
    radius = preview["spec"]["base_radius"]
    if any(abs(math.hypot(*p)-radius)>1e-6 for p in (points[0], points[-1])):
        raise ValueError("cam active endpoints do not meet the base circle")
    # Fit at successively denser knots; held-out dense contact samples remain
    # independent from interpolation nodes. Never fall back to a faceted contour.
    for stride in (10, 5, 2):
        indices = list(range(0, count-1, stride))+[count-1]
        fit_parameters = [parameters[i] for i in indices]
        segments = _spline(fit_parameters, [points[i] for i in indices])
        error = max(math.dist(p, _evaluate(fit_parameters, segments, t)) for p,t in zip(points,parameters))
        fit_radius = min(radius,_minimum_radius(segments))
        if error <= tolerance/4 and fit_radius+1e-8 >= preview["spec"]["min_curvature_radius"]:
            break
    else:
        raise ValueError("cam curve cannot meet profile accuracy and strict curvature limit; revise motion or curvature requirement")
    angle = math.radians(rotation_deg % 360)
    segments = [[_sketch(_rotate(p, angle)) for p in segment] for segment in segments]
    poles = segments[0][:]
    for segment in segments[1:]:
        poles.extend(segment[1:])
    knots = [fit_parameters[0]]*4
    for t in fit_parameters[1:-1]:
        knots.extend([t]*3)
    knots += [fit_parameters[-1]]*4
    start = _sketch(_rotate(points[-1], angle))
    end = _sketch(_rotate(points[0], angle))
    base_start = math.atan2(start[1],start[0])
    span = (base_start-math.atan2(end[1],end[0])) % (2*math.pi)
    base = {"radius": radius, "start": start, "end": end, "center": [0.0,0.0],
            "direction": True, "start_angle": base_start, "span": span}
    recipe = {"schema":"geomwright.cam.recipe", "version":1,
              "request":preview["spec"],"width":width,"rotation_deg":rotation_deg%360,
              "tolerance":tolerance,"name":name[:120]}
    if studio_profile is not None:
        recipe["studio_profile"] = studio_profile
    # Bounded JSON metadata only: no pickles, external paths or curve arrays.
    encoded = json.dumps(recipe,ensure_ascii=True,allow_nan=False,separators=(",",":"))
    if len(encoded)>24000:
        raise ValueError("cam recipe exceeds 24000 characters")
    plan = {"stage": "cam_plan", "plan_version": 1, "name": name[:120], "recipe":recipe,
            "source_request": preview["spec"], "width": width,
            "rotation_deg": rotation_deg % 360, "tolerance_mm": tolerance,
            "axis": "global_x", "plane": "YOZ", "axial_interval": [-width,0.0],
            "parameterization": "create_only_numeric_profile",
            "curve": {"order": 4, "points": poles, "weights": [1.0]*len(poles), "knots": knots},
            "base": base, "fit": {"max_sampled_error_mm": error, "segment_count": len(segments),
                                       "reference_samples_per_degree": 10},
            "calculation": {"law": preview["law"], "selection": preview.get("selection"),
                            "synthesis": preview.get("synthesis"), "summary": preview["summary"]},
            "warnings": preview["warnings"]}
    plan["verification"] = verify_cam_geometry(plan, plan["curve"], plan["base"], preview)
    return plan


def verify_cam_geometry(plan: dict, curve: dict, base: dict, preview: dict | None = None) -> dict:
    """Verify actual NURBS parameters, not echoed inputs; sampled contact checks."""
    numbers = ([v for p in curve["points"] for v in p]+curve["weights"]+curve["knots"]
               +base["start"]+base["end"]+base["center"]
               +[base["radius"],base["start_angle"],base["span"]])
    if not all(math.isfinite(value) for value in numbers):
        raise ValueError("cam readback must contain finite geometry")
    if (len(curve["points"])<4 or (len(curve["points"])-1)%3
            or any(len(p)!=2 for p in curve["points"])
            or len(curve["weights"])!=len(curve["points"])):
        raise ValueError("cam readback control-point topology differs")
    if curve["order"] != 4 or any(abs(w-1)>1e-10 for w in curve["weights"]):
        raise ValueError("cam readback is not the expected cubic non-rational curve")
    poles = curve["points"]
    segments = [poles[i:i+4] for i in range(0,len(poles)-1,3)]
    knot_parameters = [curve["knots"][0]]+curve["knots"][4:-4:3]+[curve["knots"][-1]]
    if len(knot_parameters) != len(segments)+1:
        raise ValueError("cam readback knot topology differs")
    tol = plan["tolerance_mm"]
    gap = max(math.dist(poles[-1],base["start"]), math.dist(poles[0],base["end"]))
    if (gap > 1e-7 or abs(base["radius"]-plan["base"]["radius"])>1e-7
            or math.hypot(*base["center"])>1e-7 or base["direction"] != plan["base"]["direction"]):
        raise ValueError("cam readback contour is open or has a wrong base radius")
    rotation = math.radians(plan["rotation_deg"])
    if preview is None:
        preview = preview_cam_profile(plan["source_request"])
    count = preview["profile"]["active_count"]
    source = list(zip(preview["profile"]["x"][:count],preview["profile"]["y"][:count]))
    parameters = _length_parameters(source)
    times = preview["follower"]["theta_deg"]
    error = max(math.dist(_sketch(_rotate(list(p),rotation)),_evaluate(knot_parameters,segments,t)) for p,t in zip(source,parameters))
    if error > tol/2:
        raise ValueError("actual cam curve exceeds sampled profile tolerance")
    sampled = []
    min_radius = min(base["radius"],_minimum_radius(segments,clockwise=preview["spec"]["contact"] == "flat"))
    for segment in segments:
        for j in range(9):
            t = j/8
            sampled.append(_point(segment,t))
    for segment, endpoint in ((segments[0],0),(segments[-1],1)):
        p = segment[0] if endpoint == 0 else segment[-1]
        d = [segment[1][k]-segment[0][k] for k in (0,1)] if endpoint == 0 else [segment[3][k]-segment[2][k] for k in (0,1)]
        if abs(p[0]*d[0]+p[1]*d[1])/(math.hypot(*p)*math.hypot(*d))>1e-6:
            raise ValueError("actual cam curve is not tangent to its base")
    if min_radius+1e-8 < preview["spec"]["min_curvature_radius"]:
        raise ValueError("actual interpolated cam violates the minimum curvature radius")
    base_step = 2*math.acos(max(-1,1-tol/8/base["radius"]))
    if base_step <= 0:
        raise ValueError("base circle is too large for the requested numerical accuracy")
    base_steps = max(16, math.ceil(base["span"]/base_step))
    if base_steps > 4096:
        raise ValueError("base-circle verification exceeds 4096 samples; increase tolerance or reduce the base radius")
    sampled += [[base["radius"]*math.cos(base["start_angle"]-base["span"]*j/base_steps),
                 base["radius"]*math.sin(base["start_angle"]-base["span"]*j/base_steps)] for j in range(base_steps+1)]
    if self_intersection(tuple(p[0] for p in sampled), tuple(p[1] for p in sampled)):
        raise ValueError("actual interpolated cam contour self-intersects")
    unrotated_segments = [[_rotate(_sketch(p),-rotation) for p in segment] for segment in segments]
    contact_base = {**base,"start":_rotate(_sketch(base["start"]),-rotation),
                    "end":_rotate(_sketch(base["end"]),-rotation)}
    # Sketch->profile reflects orientation: the physical base arc is CCW.
    # Reverse its endpoints to reuse the clockwise arc helpers.
    contact_base["start"],contact_base["end"] = contact_base["end"],contact_base["start"]
    contact_base["start_angle"] = math.atan2(contact_base["start"][1],contact_base["start"][0])
    # Independent contact recovery: all profile points must stay behind each
    # flat support plane, or outside each roller disk. This catches remote contact.
    penetration = 0.0
    recovery_error = 0.0
    pressure_angle = None
    contact_offset = 0.0
    follower = preview["follower"]
    contact_indices = set(range(0,count,max(1,count//480))) | {count-1}
    for i in range(count):
        if preview["spec"]["contact"] == "flat":
            t = math.radians(times[i]); c,s = math.cos(t),math.sin(t)
            # Dense local contact checks protect finite-face reach at motion knots.
            local = _evaluate(knot_parameters,unrotated_segments,parameters[i])
            contact_offset = max(contact_offset,abs(-local[0]*s+local[1]*c-preview["spec"]["offset"]))
            if i not in contact_indices:
                continue
            contact = _support(unrotated_segments,contact_base,c,s)
            support = contact[0]*c+contact[1]*s
            contact_offset = max(contact_offset,abs(-contact[0]*s+contact[1]*c-preview["spec"]["offset"]))
            expected = base["radius"]+follower["lift"][i]
            penetration = max(penetration,support-expected)
            recovery_error = max(recovery_error,abs(support-expected))
        else:
            center = [follower["center_x"][i], follower["center_y"][i]]
            distance = _roller_distance(unrotated_segments,contact_base,center) if i in contact_indices else None
            expected = preview["spec"]["roller_radius"]
            if distance is not None:
                penetration = max(penetration,expected-distance)
                recovery_error = max(recovery_error,abs(distance-expected))
            parameter = parameters[i]
            index = min(len(segments)-1, max(0, bisect.bisect_right(knot_parameters,parameter)-1))
            t = (parameter-knot_parameters[index])/(knot_parameters[index+1]-knot_parameters[index])
            derivative, _ = _derivatives(segments[index],t)
            dx,dy = _rotate(_sketch(derivative),-rotation)
            if preview["spec"]["mechanism"] == "rocker":
                flow = [follower["flow_x"][i],follower["flow_y"][i]]
            else:
                angle = math.radians(times[i])
                flow = [math.cos(angle),math.sin(angle)]
            flow_length = math.hypot(*flow)
            if flow_length > 1e-12:
                cosine = abs(dy*flow[0]-dx*flow[1])/(math.hypot(dx,dy)*flow_length)
                value = math.degrees(math.acos(min(1.0,cosine)))
                pressure_angle = max(pressure_angle or 0.0,value)
    if penetration > tol or recovery_error > tol:
        raise ValueError("actual cam fails global follower contact recovery")
    if pressure_angle is not None and pressure_angle > preview["spec"]["pressure_angle_limit_deg"]+1e-6:
        raise ValueError("actual cam exceeds the pressure-angle limit; tighten curve tolerance or revise geometry")
    required_tappet = None
    if preview["spec"]["contact"] == "flat":
        required_tappet = 2*(contact_offset+preview["spec"]["tappet_edge_margin"])
        diameter = preview["spec"]["tappet_diameter"]
        if diameter is not None and required_tappet > diameter+1e-8:
            raise ValueError("actual cam contact reaches the specified tappet edge")
    integral = -base["radius"]**2*base["span"]
    # Three-point Gauss integrates cubic x*y'-y*x' exactly (degree <= 5).
    for segment in segments:
        for t, weight in ((0.5-math.sqrt(15)/10,5/18),(0.5,4/9),(0.5+math.sqrt(15)/10,5/18)):
            p = _point(segment,t)
            d,_ = _derivatives(segment,t)
            integral += weight*(p[0]*d[1]-p[1]*d[0])
    area = abs(integral)/2
    return {"ok": True, "mode": "sampled_curve_and_global_contact", "profile_error_mm": error,
            "closure_gap_mm": gap, "min_sampled_curvature_radius_mm": min_radius,
            "min_curvature_radius_mm": min_radius,
            "curvature_shortfall_mm": max(0.0, preview["spec"]["min_curvature_radius"]-min_radius),
            "curvature_tolerance_mm": 1e-8, "engineering_limits": "strict",
            "curvature_check": "cubic_stationary_roots_and_base_arc",
            "contact_check": "exact_curve_extrema_at_sampled_follower_angles",
            "contact_angle_count": len(contact_indices), "pressure_angle_count": count,
            "contact_recovery_error_mm": recovery_error, "penetration_mm": penetration,
            "max_sampled_pressure_angle_deg": pressure_angle,
            "required_sampled_tappet_diameter_mm": required_tappet,
            "area_mm2": area, "expected_volume_cm3": area*plan["width"]/1000,
            "bounds_2d": [min(p[0] for p in sampled),min(p[1] for p in sampled),
                          max(p[0] for p in sampled),max(p[1] for p in sampled)]}


def create_cam(adapter: Any, request: dict, *, width: float = 12.0,
               rotation_deg: float = 0.0, tolerance: float = 0.01,
               name: str = "Geomwright cam", execute: bool = False,
               confirm_write: bool = False, visible: bool = True,
                progress_callback: Any = None, studio_profile: dict | None = None) -> dict:
    plan = build_cam_plan(request,width=width,rotation_deg=rotation_deg,tolerance=tolerance,name=name,
                          studio_profile=studio_profile)
    if not execute:
        return {k:v for k,v in plan.items() if k not in {"curve","base","source_request"}}
    if confirm_write is not True:
        raise ValueError("confirm_write=true is required when execute=true")
    cancellation = getattr(adapter.runner,"cancel_event",None)
    if cancellation is not None and cancellation.is_set():
        raise CamBuildError("Cam creation was cancelled before CAD access",{"status":"not_started","verified":False})
    checkpoint: dict = {}
    def progress(event: dict) -> None:
        checkpoint.update({key:value for key,value in event.items() if value is not None})
        if progress_callback:
            progress_callback(event)
    try:
        result = adapter.runner.call("create_cam", {"plan":plan,"execute":True,"confirm_write":True,"visible":visible,
                                                    "_require_visible_kompas": True},progress_callback=progress)
    except Exception as exc:
        raise CamBuildError(str(exc),{"status":"interrupted", "verified":False,
                            "document_id":checkpoint.get("document_id"), "stage":checkpoint.get("stage"),
                            "part_reference":checkpoint.get("part_reference"),
                            "action":"inspect_owned_document_before_retry"}) from exc
    if not result.get("ok"):
        partial = result.get("partial_result") or {"status":"partial","verified":False}
        partial.setdefault("stage",checkpoint.get("stage"))
        partial.setdefault("part_reference",checkpoint.get("part_reference"))
        raise CamBuildError(result.get("error","Cam native build failed"),partial)
    try:
        checkpoint["stage"] = "host_verification"
        return _verify_created_cam(adapter,plan,result,progress)
    except Exception as exc:
        raise CamBuildError(str(exc),{"status":"unverified", "verified":False,
                            "document":result.get("document"),"stage":checkpoint.get("stage"),
                            "part_reference":checkpoint.get("part_reference"),"exports":result.get("exports"),
                            "action":"inspect_owned_document_before_retry"}) from exc


def _verify_created_cam(adapter: Any, plan: dict, result: dict, progress: Any) -> dict:
    actual = result.pop("curve_readback")
    verification = verify_cam_geometry(plan,actual["curve"],actual["base"])
    body = result["body"]
    if (not math.isfinite(body["volume"]) or body["volume"]<=0
            or len(body["bounds"])!=6 or not all(math.isfinite(v) for v in body["bounds"])):
        raise RuntimeError("actual cam body must have finite positive volume and bounds")
    expected = verification["expected_volume_cm3"]
    if abs(body["volume"]-expected)>max(1e-7,expected*1e-5):
        raise RuntimeError("actual cam body volume differs from verified profile extrusion")
    box = body["bounds"]
    bounds = verification["bounds_2d"]
    expected_box = [-plan["width"],-bounds[3],-bounds[2],0,-bounds[1],-bounds[0]]
    if max(abs(a-b) for a,b in zip(box,expected_box))>plan["tolerance_mm"]:
        raise RuntimeError("actual cam body bounds or extrusion direction differ")
    result["verification"].update(verification)
    result["calculation"] = plan["calculation"]
    result["warnings"] = plan["warnings"]
    progress({"stage":"cam_finalization","operation":"cam_finalization","name":plan["name"],
              "percent":98,"document_id":result["document"]["runtime_id"]})
    cancellation = getattr(adapter.runner,"cancel_event",None)
    if cancellation is not None and cancellation.is_set():
        raise RuntimeError("Cam creation was cancelled before finalization; new document remains unverified")
    finalized = adapter.runner.call("finalize_cam",{"document_id":result["document"]["runtime_id"],
                         "sketch_ref":result["exports"]["sketch_ref"],
                         "feature_ref":result["exports"]["feature_ref"],
                         "curve_digest":hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(",",":")).encode("ascii")).hexdigest(),
                         "body_bounds":body["bounds"],
                         "confirm_write":True,"_require_visible_kompas":True},progress_callback=progress)
    if not finalized.get("ok"):
        raise RuntimeError("Cam final verification marker was not confirmed")
    result["recipe"] = plan["recipe"]
    return result
