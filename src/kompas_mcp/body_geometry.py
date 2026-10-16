"""Host-side contracts for read-only inspection of finished model geometry."""

from __future__ import annotations

import math
from typing import Any


SURFACE_TYPES = {"plane", "cylinder", "cone", "sphere", "torus", "nurbs", "revolved", "swept", "other"}
MEASUREMENTS = {"minimum_distance", "axis_distance", "plane_distance", "angle", "point_distance"}


def bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def body_selector(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("body must be a selector returned by list_model_bodies")
    allowed = {"component", "index", "reference", "update_stamp", "document_stamp"}
    if set(value) - allowed:
        raise ValueError(f"Unknown body selector keys: {sorted(set(value) - allowed)}")
    result = dict(value)
    component = result.setdefault("component", "root")
    if not isinstance(component, str) or component.split("/")[0] != "root" or any(
        not segment.isdecimal() for segment in component.split("/")[1:]
    ):
        raise ValueError("body.component must be root or a component path such as root/0/2")
    if "index" not in result and "reference" not in result:
        raise ValueError("body needs index or reference; use list_model_bodies")
    for key in ("index", "reference", "update_stamp", "document_stamp"):
        if key in result:
            bounded_int(result[key], f"body.{key}", 0, 2**63 - 1)
    return result


def entity_selector(value: dict[str, Any], name: str = "entity") -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {"index", "reference"} or not value:
        raise ValueError(f"{name} needs index or reference, obtained from a geometry list")
    for key, item in value.items():
        bounded_int(item, f"{name}.{key}", 0, 2**63 - 1)
    return dict(value)


def geometry_target(value: dict[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a geometry target")
    kind = value.get("kind")
    if kind == "point":
        if set(value) != {"kind", "point_mm"}:
            raise ValueError(f"{name}: point target needs only kind and point_mm")
        coords = value["point_mm"]
        if not isinstance(coords, (list, tuple)) or len(coords) != 3 or any(
            isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in coords
        ):
            raise ValueError(f"{name}.point_mm must contain three finite numbers")
        return {"kind": kind, "point_mm": [float(x) for x in coords]}
    if kind not in {"body", "face", "edge", "vertex"}:
        raise ValueError(f"{name}.kind must be body, face, edge, vertex or point")
    if set(value) - {"kind", "body", "entity"}:
        raise ValueError(f"{name}: unknown geometry target keys")
    result = {"kind": kind, "body": body_selector(value.get("body"))}
    if kind != "body":
        result["entity"] = entity_selector(value.get("entity"), f"{name}.entity")
    elif "entity" in value:
        raise ValueError(f"{name}: body target must not include entity")
    return result


def geometry_payload(action: str, document_id: str | None, **values: Any) -> dict[str, Any]:
    if document_id is not None and (not isinstance(document_id, str) or not document_id.strip()):
        raise ValueError("document_id must be an exact open document ID or omitted for the active document")
    result = {"document_id": document_id, **values}
    if "body" in result:
        result["body"] = body_selector(result["body"])
    for name in ("face", "edge"):
        if name in result:
            result[name] = entity_selector(result[name], name)
    for name in ("offset",):
        if name in result:
            bounded_int(result[name], name, 0, 10_000_000)
    for name, maximum in (("limit", 200), ("max_edges", 200), ("curve_samples", 65), ("max_mesh_points", 20000)):
        if name in result:
            bounded_int(result[name], name, 2 if name == "curve_samples" else 1, maximum)
    if "surface_type" in result and result["surface_type"] is not None and (
        not isinstance(result["surface_type"], str) or result["surface_type"] not in SURFACE_TYPES
    ):
        raise ValueError(f"surface_type must be one of {sorted(SURFACE_TYPES)}")
    if "include_mesh" in result and not isinstance(result["include_mesh"], bool):
        raise ValueError("include_mesh must be a boolean")
    if "measurement" in result:
        if result["measurement"] not in MEASUREMENTS:
            raise ValueError(f"measurement must be one of {sorted(MEASUREMENTS)}")
        for name in ("first", "second"):
            result[name] = geometry_target(result.get(name), name)
        kinds = {result[name]["kind"] for name in ("first", "second")}
        if result["measurement"] == "point_distance" and kinds != {"point"}:
            raise ValueError("point_distance requires two point targets")
        if result["measurement"] != "point_distance" and "point" in kinds:
            raise ValueError("Virtual points are supported only by point_distance; use a vertex for native measurements")
        if result["measurement"] in {"axis_distance", "plane_distance"} and kinds != {"face"}:
            raise ValueError("axis_distance and plane_distance require two face targets")
    return result


def finish_measurement(payload: dict[str, Any]) -> dict[str, Any]:
    """Derive explicit infinite-axis/plane measurements outside the COM runtime."""
    result = payload.get("result", {})
    if not result.pop("analytic_inputs", False):
        return payload
    first, second = result["first"], result["second"]
    kind = result["measurement"]

    def dot(a: list[float], b: list[float]) -> float:
        return sum(x*y for x, y in zip(a, b))

    def sub(a: list[float], b: list[float]) -> list[float]:
        return [x-y for x, y in zip(a, b)]

    def add_scaled(a: list[float], u: list[float], scale: float) -> list[float]:
        return [x+scale*y for x, y in zip(a, u)]

    def cross(a: list[float], b: list[float]) -> list[float]:
        return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]

    def unit(a: list[float]) -> list[float]:
        length = math.sqrt(dot(a, a))
        if length < 1e-12:
            raise ValueError("Surface has a degenerate axis/normal; measurement is unavailable")
        return [x/length for x in a]

    if kind == "point_distance":
        p, q = first["point_mm"], second["point_mm"]
        semantics = "distance_between_supplied_document_coordinates"
    else:
        allowed = {"plane"} if kind == "plane_distance" else {"cylinder"}
        surfaces = [first["surface"], second["surface"]]
        if any(s["type"] not in allowed or not s.get("frame") for s in surfaces):
            raise ValueError(f"{kind} requires two {sorted(allowed)} surfaces with readable frames")
        p, q = [s["frame"]["origin_mm"] for s in surfaces]
        u, v = [unit(s["frame"]["z_axis"]) for s in surfaces]
        w = sub(p, q)
        normal = cross(u, v)
        den = dot(normal, normal)
        parallel = den < 1e-24
        if kind == "plane_distance":
            if not parallel:
                raise ValueError("plane_distance requires parallel planes; use minimum_distance or angle")
            q = add_scaled(p, u, -dot(w, u))
            semantics = "distance_between_infinite_supporting_planes_not_trimmed_face_clearance"
        else:
            if parallel:
                q = add_scaled(q, v, dot(w, v))
            else:
                t, s = dot(cross(sub(q, p), v), normal)/den, dot(cross(sub(q, p), u), normal)/den
                p, q = add_scaled(p, u, t), add_scaled(q, v, s)
            semantics = "shortest_distance_between_infinite_surface_axes_not_surface_clearance"
        result["parallel"] = parallel
    value = math.dist(p, q)
    if not math.isfinite(value) or any(not math.isfinite(x) for point in (p, q) for x in point):
        raise ValueError("Measurement exceeds finite numeric range")
    result.update(value=value, units="mm", witnesses_mm=[p, q], status="analytic",
                  source="read_final_geometry" if kind != "point_distance" else "supplied_coordinates",
                  semantics=semantics)
    return payload
