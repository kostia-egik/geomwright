"""Agent-facing tools for finished bodies, not construction recipes."""

from typing import Any

from mcp.types import ToolAnnotations


def register_body_geometry_tools(mcp: Any, adapter: Any) -> None:
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

    @mcp.tool(annotations=read_only)
    def list_model_bodies(document_id: str | None = None, offset: int = 0, limit: int = 50) -> dict:
        """List final bodies across part/assembly components, with bounds and reusable selectors.

        Does not rebuild, activate, save or read construction history. Pagination is global.
        Explicit document IDs are strict. Re-list after rebuild/reopen; selectors are not permanent IDs.
        """
        return adapter.list_model_bodies(document_id, offset=offset, limit=limit)

    @mcp.tool(annotations=read_only)
    def list_body_faces(body: dict, document_id: str | None = None, surface_type: str | None = None,
                        offset: int = 0, limit: int = 50) -> dict:
        """List final-body faces with analytical type/radius, frame and area (mm²).

        Pass body.selector from list_model_bodies. Types: plane/cylinder/cone/sphere/torus/nurbs/
        revolved/swept/other. Returns face.selector for inspection/measurement; paginates filtered faces.
        """
        return adapter.list_body_faces(document_id, body=body, surface_type=surface_type, offset=offset, limit=limit)

    @mcp.tool(annotations=read_only)
    def list_body_edges(body: dict, document_id: str | None = None, offset: int = 0, limit: int = 50) -> dict:
        """List trimmed final edges: length (mm), endpoints, circle radius/centre and adjacent faces.

        Pass body.selector from list_model_bodies. Edge selectors can be used for native distances/angles.
        """
        return adapter.list_body_edges(document_id, body=body, offset=offset, limit=limit)

    @mcp.tool(annotations=read_only)
    def inspect_body_face(body: dict, face: dict, document_id: str | None = None,
                          max_edges: int = 64, curve_samples: int = 9,
                          include_mesh: bool = False, max_mesh_points: int = 6000) -> dict:
        """Capture a final face's analytical surface and trimmed boundaries, optionally its cached mesh.

        Pass selectors from list_model_bodies/list_body_faces. Includes adjacency and boundary curves.
        Samples/mesh are explicitly approximate, not an exact BREP export or a manufacturing tolerance.
        No tessellation rebuild. Oversized mesh is omitted with counts; missing geometry is marked partial.
        """
        return adapter.inspect_body_face(document_id, body=body, face=face, max_edges=max_edges,
                                         curve_samples=curve_samples, include_mesh=include_mesh,
                                         max_mesh_points=max_mesh_points)

    @mcp.tool(annotations=read_only)
    def measure_model_geometry(first: dict, second: dict, document_id: str | None = None,
                               measurement: str = "minimum_distance") -> dict:
        """Measure final geometry with explicit meaning and witnesses (mm/degrees), without model writes.

        Targets: {kind:face|edge|vertex, body:<body.selector>, entity:<face/edge/vertex selector>},
        or {kind:body, body:<body.selector>}. minimum_distance uses native trimmed-object measurement;
        unsupported/native axis-centre interpretations are refused, not labelled surface clearance.
        axis_distance uses cylinder infinite axes; plane_distance uses parallel infinite planes.
        angle uses KOMPAS IsAngleValid. point_distance accepts two {kind:point, point_mm:[x,y,z]} targets.
        """
        return adapter.measure_model_geometry(document_id, first=first, second=second, measurement=measurement)
