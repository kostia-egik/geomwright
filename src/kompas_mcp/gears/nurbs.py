"""Interpolating cubic B-spline builder for smooth gear flank curves.

KOMPAS spline entities are NURBS. Building a flank from line segments creates a
visibly faceted contour, so the CAD plan fits one interpolating cubic B-spline
per flank and passes its control points/knots to the bridge. The implementation
follows the clamped interpolation scheme from *The NURBS Book* (A2.2/A2.3,
eq. 9.8) and needs no third-party dependency.
"""
from __future__ import annotations

import math


def _chord_parameters(points: list[list[float]]) -> list[float]:
    parameters = [0.0]
    for first, second in zip(points, points[1:]):
        parameters.append(parameters[-1] + math.dist(first, second))
    total = parameters[-1]
    if total <= 1e-12:
        raise ValueError("Spline points are coincident")
    return [value / total for value in parameters]


def _averaging_knots(parameters: list[float], degree: int) -> list[float]:
    count = len(parameters)
    knots = [0.0] * (degree + 1)
    for index in range(1, count - degree):
        knots.append(sum(parameters[index:index + degree]) / degree)
    knots.extend([1.0] * (degree + 1))
    return knots


def _find_span(count: int, degree: int, value: float, knots: list[float]) -> int:
    last = count - 1
    if value >= knots[last + 1]:
        return last
    if value <= knots[degree]:
        return degree
    low, high = degree, last + 1
    middle = (low + high) // 2
    while value < knots[middle] or value >= knots[middle + 1]:
        if value < knots[middle]:
            high = middle
        else:
            low = middle
        middle = (low + high) // 2
    return middle


def _basis_functions(span: int, value: float, degree: int, knots: list[float]) -> list[float]:
    basis = [0.0] * (degree + 1)
    left = [0.0] * (degree + 1)
    right = [0.0] * (degree + 1)
    basis[0] = 1.0
    for index in range(1, degree + 1):
        left[index] = value - knots[span + 1 - index]
        right[index] = knots[span + index] - value
        saved = 0.0
        for other in range(index):
            denominator = right[other + 1] + left[index - other]
            temp = basis[other] / denominator if denominator > 1e-15 else 0.0
            basis[other] = saved + right[other + 1] * temp
            saved = left[index - other] * temp
        basis[index] = saved
    return basis


def _solve(matrix: list[list[float]], values: list[float]) -> list[float]:
    size = len(matrix)
    augmented = [list(row) + [values[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-14:
            raise ValueError("Spline interpolation matrix is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for index in range(column, size + 1):
            augmented[column][index] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for index in range(column, size + 1):
                augmented[row][index] -= factor * augmented[column][index]
    return [augmented[row][size] for row in range(size)]


def interpolating_spline(points: list[list[float]], degree: int = 3) -> dict:
    """Return a clamped interpolating B-spline through `points`."""
    unique: list[list[float]] = []
    for point in points:
        candidate = [float(point[0]), float(point[1])]
        if not unique or math.dist(unique[-1], candidate) > 1e-9:
            unique.append(candidate)
    if len(unique) < 2:
        raise ValueError("A spline needs at least two distinct points")
    degree = max(1, min(int(degree), len(unique) - 1))
    parameters = _chord_parameters(unique)
    knots = _averaging_knots(parameters, degree)
    count = len(unique)
    matrix: list[list[float]] = []
    for value in parameters:
        span = _find_span(count, degree, value, knots)
        row = [0.0] * count
        basis = _basis_functions(span, value, degree, knots)
        for offset, weight in enumerate(basis):
            row[span - degree + offset] = weight
        matrix.append(row)
    control_x = _solve(matrix, [point[0] for point in unique])
    control_y = _solve(matrix, [point[1] for point in unique])
    return {
        "degree": degree,
        "points": [[control_x[index], control_y[index]] for index in range(count)],
        "weights": [1.0] * count,
        "knots": knots,
    }


def bezier_chain(points: list[list[float]]) -> dict:
    """One smooth cubic Bezier chain through `points` (KOMPAS-proven form).

    Uses the same knot convention as the accepted cam path: interior knots are
    repeated three times, so the single KOMPAS spline is a C1 chain of cubic
    Bezier segments that interpolates every input point.
    """
    unique: list[list[float]] = []
    for point in points:
        candidate = [float(point[0]), float(point[1])]
        if not unique or math.dist(unique[-1], candidate) > 1e-9:
            unique.append(candidate)
    if len(unique) < 2:
        raise ValueError("A spline needs at least two distinct points")

    tangents: list[list[float]] = []
    for index in range(len(unique)):
        if index == 0:
            tangent = [unique[1][0] - unique[0][0], unique[1][1] - unique[0][1]]
        elif index == len(unique) - 1:
            tangent = [unique[-1][0] - unique[-2][0], unique[-1][1] - unique[-2][1]]
        else:
            tangent = [
                (unique[index + 1][0] - unique[index - 1][0]) / 2.0,
                (unique[index + 1][1] - unique[index - 1][1]) / 2.0,
            ]
        tangents.append(tangent)

    control = [unique[0]]
    for index in range(len(unique) - 1):
        start = unique[index]
        end = unique[index + 1]
        control.append([start[0] + tangents[index][0] / 3.0, start[1] + tangents[index][1] / 3.0])
        control.append([end[0] - tangents[index + 1][0] / 3.0, end[1] - tangents[index + 1][1] / 3.0])
        control.append(list(end))

    parameters = [0.0]
    for start, end in zip(unique, unique[1:]):
        parameters.append(parameters[-1] + math.dist(start, end))
    if parameters[-1] <= 1e-12:
        raise ValueError("Spline points are coincident")
    knots = [parameters[0]] * 4
    for value in parameters[1:-1]:
        knots.extend([value] * 3)
    knots.extend([parameters[-1]] * 4)
    return {
        "degree": 3,
        "points": control,
        "weights": [1.0] * len(control),
        "knots": knots,
    }


def evaluate_spline(spline: dict, value: float) -> list[float]:
    """Evaluate a spline description at a normalized parameter (for checks)."""
    control = spline["points"]
    degree = int(spline["degree"])
    knots = spline["knots"]
    span = _find_span(len(control), degree, value, knots)
    basis = _basis_functions(span, value, degree, knots)
    x = 0.0
    y = 0.0
    for offset, weight in enumerate(basis):
        index = span - degree + offset
        if index >= len(control):
            continue
        x += weight * control[index][0]
        y += weight * control[index][1]
    return [x, y]


def spline_max_deviation(spline: dict, path: list[list[float]], samples: int = 240) -> float:
    """One-sided maximum deviation of the spline from a dense reference path."""
    if len(path) < 2:
        return float("inf")
    knots = spline["knots"]
    degree = int(spline["degree"])
    domain_start = knots[degree]
    domain_end = knots[len(knots) - degree - 1]
    if domain_end <= domain_start:
        return float("inf")
    worst = 0.0
    for index in range(samples + 1):
        fraction = min(1.0, index / samples)
        value = domain_start + (domain_end - domain_start) * fraction
        point = evaluate_spline(spline, value)
        best = float("inf")
        for first, second in zip(path, path[1:]):
            dx = second[0] - first[0]
            dy = second[1] - first[1]
            length2 = dx * dx + dy * dy
            if length2 <= 1e-18:
                continue
            t = max(0.0, min(1.0, ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / length2))
            best = min(best, math.hypot(point[0] - (first[0] + t * dx), point[1] - (first[1] + t * dy)))
        worst = max(worst, best)
    return worst
