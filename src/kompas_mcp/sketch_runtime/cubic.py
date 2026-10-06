"""Host-only C2 cubic interpolation and bounded analytic-path fitting (Layer 2)."""
from __future__ import annotations

import bisect
import math
from typing import Callable


def interpolate_cubic(parameters: list[float], points: list[list[float]],
                      endpoint_tangents: list[list[float]]) -> list[list[list[float]]]:
    """Interpolate 2D points with a clamped C2 cubic Bezier chain.

    Endpoint tangents are derivatives with respect to the supplied parameters.
    The arithmetic order matches the original cam tridiagonal solver.
    """
    n = len(parameters)
    if n < 2 or len(points) != n or len(endpoint_tangents) != 2:
        raise ValueError("cubic interpolation requires two endpoints and matching points")
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p)
           for p in [*points, *endpoint_tangents]):
        raise ValueError("cubic points and endpoint derivatives must be finite 2D vectors")
    h = [parameters[i+1]-parameters[i] for i in range(n-1)]
    if any(not math.isfinite(step) or step <= 0 for step in h):
        raise ValueError("cubic parameters must be finite and strictly increasing")
    slopes = [[(points[i+1][k]-points[i][k])/h[i] for k in (0, 1)] for i in range(n-1)]
    tangents = endpoint_tangents
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


def evaluate_cubic(parameters: list[float], segments: list, value: float) -> list[float]:
    """Evaluate a piecewise Bezier chain at its interpolation parameter."""
    i = min(len(segments)-1, max(0, bisect.bisect_right(parameters, value)-1))
    t = (value-parameters[i])/(parameters[i+1]-parameters[i])
    u = 1.0-t
    p = segments[i]
    return [u**3*p[0][k]+3*u*u*t*p[1][k]+3*u*t*t*p[2][k]+t**3*p[3][k]
            for k in (0, 1)]


def fit_cubic_path(evaluate: Callable[[float], list[float]], lo: float, hi: float,
                   tolerance: float = 0.0005) -> dict:
    """Fit one regular analytic path to at most 400 nonrational cubic poles.

    Arc length is integrated with eight-point Gauss quadrature; fourth-order
    differences of the analytic callable supply unit endpoint tangents. Control
    intervals are bisected adaptively. Each fit is checked at 32 held-out
    midpoints per interval, independently of its interpolation nodes. Reported
    error is sampled Euclidean error at corresponding arc length, not a proof
    of a continuous bound. Failure raises; there is no polyline fallback.
    """
    if not all(math.isfinite(v) for v in (lo, hi, tolerance)) or lo == hi or tolerance <= 0:
        raise ValueError("cubic fit requires a finite nonzero interval and positive tolerance")
    span = hi-lo

    def point(t: float) -> list[float]:
        p = list(evaluate(lo+span*t))
        if len(p) != 2 or not all(math.isfinite(v) for v in p):
            raise ValueError("analytic cubic source must return finite 2D points")
        return p

    def derivative(t: float) -> list[float]:
        step = 1e-5
        if t < 2*step or t > 1-2*step:
            step = step if t < 0.5 else -step
            samples = [point(t+i*step) for i in range(5)]
            return [sum(c*p[k] for c, p in zip((-25, 48, -36, 16, -3), samples))/(12*step)
                    for k in (0, 1)]
        samples = [point(t+i*step) for i in (-2, -1, 1, 2)]
        return [sum(c*p[k] for c, p in zip((1, -8, 8, -1), samples))/(12*step)
                for k in (0, 1)]

    gauss = ((0.1834346424956498, 0.3626837833783620),
             (0.5255324099163290, 0.3137066458778873),
             (0.7966664774136267, 0.2223810344533745),
             (0.9602898564975363, 0.1012285362903763))

    def length(a: float, b: float) -> float:
        mid, half = (a+b)/2, (b-a)/2
        return half*sum(w*(math.hypot(*derivative(mid-half*x))+
                           math.hypot(*derivative(mid+half*x))) for x, w in gauss)

    tangents = []
    for t in (0.0, 1.0):
        d = derivative(t)
        speed = math.hypot(*d)
        if speed <= 1e-12:
            raise ValueError("analytic cubic source has a stationary endpoint")
        tangents.append([v/speed for v in d])
    nodes = [i/8 for i in range(9)]
    for iteration in range(12):
        points = [point(t) for t in nodes]
        parameters = [0.0]
        for a, b in zip(nodes, nodes[1:]):
            parameters.append(parameters[-1]+length(a, b))
        segments = interpolate_cubic(parameters, points, tangents)
        errors = []
        for i, (a, b) in enumerate(zip(nodes, nodes[1:])):
            error = 0.0
            for j in range(32):
                t = a+(b-a)*(j+0.5)/32
                s = parameters[i]+length(a, t)
                error = max(error, math.dist(point(t), evaluate_cubic(parameters, segments, s)))
            errors.append(error)
        maximum = max(errors)
        if maximum <= tolerance/2:
            poles = segments[0][:1]+[p for segment in segments for p in segment[1:]]
            knots = [parameters[0]]*4
            for s in parameters[1:-1]:
                knots.extend([s]*3)
            knots.extend([parameters[-1]]*4)
            return {"kind": "nurbs", "order": 4, "points": poles,
                    "weights": [1.0]*len(poles), "knots": knots,
                    "fit": {"max_error_mm": maximum, "tolerance_mm": tolerance,
                            "control_node_count": len(nodes), "pole_count": len(poles),
                            "span_count": len(segments), "validation_sample_count": 32*len(segments),
                            "iterations": iteration+1, "parameterization": "arc_length",
                            "verification": "held_out_analytic_samples"}}
        refined = [nodes[0]]
        for a, b, error in zip(nodes, nodes[1:], errors):
            if error > tolerance/2:
                refined.append((a+b)/2)
            refined.append(b)
        if 3*(len(refined)-1)+1 > 400:
            raise ValueError("analytic cubic fit exceeds 400-pole budget")
        nodes = refined
    raise ValueError("analytic cubic fit did not converge within 12 refinements")
