from __future__ import annotations

from typing import Any


def register_sketch_tools(mcp: Any, adapter: Any) -> None:
    """Register sketch primitive, sketch readback, and feature repair tools."""

    @mcp.tool()
    def create_point3d(
        document_id: str | None = None,
        name: str = "PT1",
        origin: list[float] | None = None,
        min_added: int = 1,
        require_no_removed: bool = True,
        require_no_changed: bool = False,
        max_items: int = 25,
    ) -> dict:
        """Create a 3D point in the active part and verify the before/after snapshot delta."""
        return adapter.create_point3d(
            document_id=document_id,
            name=name,
            origin=origin,
            min_added=min_added,
            require_no_removed=require_no_removed,
            require_no_changed=require_no_changed,
            max_items=max_items,
        )

    @mcp.tool()
    def create_sketch_line_segment(
        document_id: str | None = None,
        name: str = "SKETCH_LINE_1",
        plane: str = "XOY",
        start: list[float] | None = None,
        end: list[float] | None = None,
        sketch_ref: str | None = None,
        create_new_sketch: bool = True,
        line_style: int = 1,
        min_added: int = 1,
        require_no_removed: bool = True,
        require_no_changed: bool = False,
        max_items: int = 25,
    ) -> dict:
        """Create a sketch with one 2D line segment and verify the before/after snapshot delta."""
        return adapter.create_sketch_line_segment(
            document_id=document_id,
            name=name,
            plane=plane,
            start=start,
            end=end,
            sketch_ref=sketch_ref,
            create_new_sketch=create_new_sketch,
            line_style=line_style,
            min_added=min_added,
            require_no_removed=require_no_removed,
            require_no_changed=require_no_changed,
            max_items=max_items,
        )

    @mcp.tool()
    def create_sketch_circle(
        document_id: str | None = None,
        name: str = "SKETCH_CIRCLE_1",
        plane: str = "XOY",
        center: list[float] | None = None,
        radius: float = 10.0,
        sketch_ref: str | None = None,
        create_new_sketch: bool = True,
        line_style: int = 1,
        min_added: int = 1,
        require_no_removed: bool = True,
        require_no_changed: bool = False,
        max_items: int = 25,
    ) -> dict:
        """Create a sketch with one 2D circle and verify the before/after snapshot delta."""
        return adapter.create_sketch_circle(
            document_id=document_id,
            name=name,
            plane=plane,
            center=center,
            radius=radius,
            sketch_ref=sketch_ref,
            create_new_sketch=create_new_sketch,
            line_style=line_style,
            min_added=min_added,
            require_no_removed=require_no_removed,
            require_no_changed=require_no_changed,
            max_items=max_items,
        )

    @mcp.tool()
    def create_sketch_rectangle(
        document_id: str | None = None,
        name: str = "SKETCH_RECTANGLE_1",
        plane: str = "XOY",
        corner1: list[float] | None = None,
        corner2: list[float] | None = None,
        sketch_ref: str | None = None,
        create_new_sketch: bool = True,
        line_style: int = 1,
        min_added: int = 1,
        require_no_removed: bool = True,
        require_no_changed: bool = False,
        max_items: int = 25,
    ) -> dict:
        """Create a sketch rectangle from two corners and verify the before/after snapshot delta."""
        return adapter.create_sketch_rectangle(
            document_id=document_id,
            name=name,
            plane=plane,
            corner1=corner1,
            corner2=corner2,
            sketch_ref=sketch_ref,
            create_new_sketch=create_new_sketch,
            line_style=line_style,
            min_added=min_added,
            require_no_removed=require_no_removed,
            require_no_changed=require_no_changed,
            max_items=max_items,
        )

    @mcp.tool()
    def create_sketch_point(
        document_id: str | None = None,
        name: str = "SKETCH_POINT_1",
        plane: str = "XOY",
        point: list[float] | None = None,
        sketch_ref: str | None = None,
        create_new_sketch: bool = True,
        line_style: int = 1,
        min_added: int = 1,
        require_no_removed: bool = False,
        require_no_changed: bool = False,
        max_items: int = 25,
    ) -> dict:
        """Create one 2D sketch point in a new or existing sketch and verify the snapshot delta."""
        return adapter.create_sketch_point(
            document_id=document_id,
            name=name,
            plane=plane,
            point=point,
            sketch_ref=sketch_ref,
            create_new_sketch=create_new_sketch,
            line_style=line_style,
            min_added=min_added,
            require_no_removed=require_no_removed,
            require_no_changed=require_no_changed,
            max_items=max_items,
        )

    @mcp.tool()
    def create_sketch_polyline(
        document_id: str | None = None,
        name: str = "SKETCH_POLYLINE_1",
        plane: str = "XOY",
        points: list[list[float]] | None = None,
        closed: bool = False,
        sketch_ref: str | None = None,
        create_new_sketch: bool = True,
        line_style: int = 1,
        min_added: int = 1,
        require_no_removed: bool = False,
        require_no_changed: bool = False,
        max_items: int = 25,
    ) -> dict:
        """Create one 2D sketch polyline in a new or existing sketch and verify the snapshot delta."""
        return adapter.create_sketch_polyline(
            document_id=document_id,
            name=name,
            plane=plane,
            points=points,
            closed=closed,
            sketch_ref=sketch_ref,
            create_new_sketch=create_new_sketch,
            line_style=line_style,
            min_added=min_added,
            require_no_removed=require_no_removed,
            require_no_changed=require_no_changed,
            max_items=max_items,
        )

    @mcp.tool()
    def create_sketch_arc(
        document_id: str | None = None,
        name: str = "SKETCH_ARC_1",
        plane: str = "XOY",
        center: list[float] | None = None,
        radius: float = 10.0,
        start: list[float] | None = None,
        end: list[float] | None = None,
        direction: bool = True,
        sketch_ref: str | None = None,
        create_new_sketch: bool = True,
        line_style: int = 1,
        min_added: int = 1,
        require_no_removed: bool = False,
        require_no_changed: bool = False,
        max_items: int = 25,
    ) -> dict:
        """Create one 2D sketch arc in a new or existing sketch and verify the snapshot delta."""
        return adapter.create_sketch_arc(
            document_id=document_id,
            name=name,
            plane=plane,
            center=center,
            radius=radius,
            start=start,
            end=end,
            direction=direction,
            sketch_ref=sketch_ref,
            create_new_sketch=create_new_sketch,
            line_style=line_style,
            min_added=min_added,
            require_no_removed=require_no_removed,
            require_no_changed=require_no_changed,
            max_items=max_items,
        )

    @mcp.tool()
    def create_sketch_ellipse(
        document_id: str | None = None,
        name: str = "SKETCH_ELLIPSE_1",
        plane: str = "XOY",
        center: list[float] | None = None,
        radius_x: float = 10.0,
        radius_y: float = 5.0,
        angle: float = 0.0,
        sketch_ref: str | None = None,
        create_new_sketch: bool = True,
        line_style: int = 1,
        min_added: int = 1,
        require_no_removed: bool = False,
        require_no_changed: bool = False,
        max_items: int = 25,
    ) -> dict:
        """Create one 2D sketch ellipse in a new or existing sketch and verify the snapshot delta."""
        return adapter.create_sketch_ellipse(
            document_id=document_id,
            name=name,
            plane=plane,
            center=center,
            radius_x=radius_x,
            radius_y=radius_y,
            angle=angle,
            sketch_ref=sketch_ref,
            create_new_sketch=create_new_sketch,
            line_style=line_style,
            min_added=min_added,
            require_no_removed=require_no_removed,
            require_no_changed=require_no_changed,
            max_items=max_items,
        )

    @mcp.tool()
    def create_sketch_entities(
        document_id: str | None = None,
        name: str = "SKETCH_BATCH_1",
        plane: str = "XOY",
        entities: list[dict] | None = None,
        sketch_ref: str | None = None,
        create_new_sketch: bool = True,
        constraints: list[dict] | None = None,
        dimensions: list[dict] | None = None,
        sketch_options: dict | None = None,
        min_added: int = 1,
        require_no_removed: bool = False,
        require_no_changed: bool = False,
        max_items: int = 25,
    ) -> dict:
        """Create several 2D sketch entities in one target sketch and verify the snapshot delta."""
        return adapter.create_sketch_entities(
            document_id=document_id,
            name=name,
            plane=plane,
            entities=entities,
            sketch_ref=sketch_ref,
            create_new_sketch=create_new_sketch,
            constraints=constraints,
            dimensions=dimensions,
            sketch_options=sketch_options,
            min_added=min_added,
            require_no_removed=require_no_removed,
            require_no_changed=require_no_changed,
            max_items=max_items,
        )

    @mcp.tool()
    def parameterize_sketch(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        entities: list[dict] | None = None,
        constraints: list[dict] | None = None,
        dimensions: list[dict] | None = None,
        sketch_options: dict | None = None,
        require_no_removed: bool = False,
        require_no_changed: bool = False,
        max_items: int = 25,
    ) -> dict:
        """Apply constraints/dimensions to existing sketch entities selected by reference, index, or fingerprint."""
        return adapter.parameterize_sketch(
            document_id=document_id,
            sketch_ref=sketch_ref,
            entities=entities,
            constraints=constraints,
            dimensions=dimensions,
            sketch_options=sketch_options,
            require_no_removed=require_no_removed,
            require_no_changed=require_no_changed,
            max_items=max_items,
        )

    @mcp.tool()
    def list_sketches(
        document_id: str | None = None,
        name_contains: str | None = None,
        max_items: int = 100,
        include_entity_counts: bool = False,
    ) -> dict:
        """List sketches with their stable sketch_ref values for follow-up entity tools."""
        return adapter.list_sketches(
            document_id=document_id,
            name_contains=name_contains,
            max_items=max_items,
            include_entity_counts=include_entity_counts,
        )

    @mcp.tool()
    def rename_sketch(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        name: str = "",
    ) -> dict:
        """Rename an existing sketch selected by sketch_ref."""
        return adapter.rename_sketch(document_id=document_id, sketch_ref=sketch_ref, name=name)

    @mcp.tool()
    def set_sketch_entity_style(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        entity: dict | None = None,
        line_style: int = 1,
    ) -> dict:
        """Set line style on one existing sketch entity selected by reference, index, or fingerprint."""
        return adapter.set_sketch_entity_style(
            document_id=document_id,
            sketch_ref=sketch_ref,
            entity=entity,
            line_style=line_style,
        )

    @mcp.tool()
    def delete_sketch_entity(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        entity: dict | None = None,
    ) -> dict:
        """Delete one existing sketch entity selected by reference, index, or fingerprint."""
        return adapter.delete_sketch_entity(
            document_id=document_id,
            sketch_ref=sketch_ref,
            entity=entity,
        )

    @mcp.tool()
    def update_sketch_entity_geometry(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        entity: dict | None = None,
        geometry: dict | None = None,
    ) -> dict:
        """Update geometry for one existing point, segment, circle, or arc selected by reference, index, or fingerprint."""
        return adapter.update_sketch_entity_geometry(
            document_id=document_id,
            sketch_ref=sketch_ref,
            entity=entity,
            geometry=geometry,
        )

    @mcp.tool()
    def list_sketch_dimensions(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        kinds: list[str] | str | None = None,
        max_items: int = 100,
    ) -> dict:
        """List existing sketch dimensions with reference, index, fingerprint, and placement fields."""
        return adapter.list_sketch_dimensions(
            document_id=document_id,
            sketch_ref=sketch_ref,
            kinds=kinds,
            max_items=max_items,
        )

    @mcp.tool()
    def inspect_sketch_dimension(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        dimension: dict | None = None,
    ) -> dict:
        """Inspect one existing sketch dimension selected by reference, index, or fingerprint."""
        return adapter.inspect_sketch_dimension(
            document_id=document_id,
            sketch_ref=sketch_ref,
            dimension=dimension,
        )

    @mcp.tool()
    def list_sketch_constraints(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        kinds: list[str] | str | None = None,
        max_items: int = 100,
    ) -> dict:
        """List existing sketch constraints with reference, index, fingerprint, and owner entity fields."""
        return adapter.list_sketch_constraints(
            document_id=document_id,
            sketch_ref=sketch_ref,
            kinds=kinds,
            max_items=max_items,
        )

    @mcp.tool()
    def inspect_sketch_constraint(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        constraint: dict | None = None,
    ) -> dict:
        """Inspect one existing sketch constraint selected by reference, index, or fingerprint."""
        return adapter.inspect_sketch_constraint(
            document_id=document_id,
            sketch_ref=sketch_ref,
            constraint=constraint,
        )

    @mcp.tool()
    def clear_sketch_entity_constraints(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        entity: dict | None = None,
    ) -> dict:
        """Delete all constraints attached to one existing sketch entity."""
        return adapter.clear_sketch_entity_constraints(
            document_id=document_id,
            sketch_ref=sketch_ref,
            entity=entity,
        )

    @mcp.tool()
    def repair_sketch(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        operations: list[dict] | None = None,
        apply: bool = False,
    ) -> dict:
        """Plan or apply a bounded repair scenario for one existing sketch."""
        return adapter.repair_sketch(
            document_id=document_id,
            sketch_ref=sketch_ref,
            operations=operations,
            apply=apply,
        )

    @mcp.tool()
    def list_features(
        document_id: str | None = None,
        kinds: list[str] | str | None = None,
        max_items: int = 100,
    ) -> dict:
        """List existing 3D features with reference, index, fingerprint, and state fields."""
        return adapter.list_features(
            document_id=document_id,
            kinds=kinds,
            max_items=max_items,
        )

    @mcp.tool()
    def inspect_feature(
        document_id: str | None = None,
        feature: dict | None = None,
    ) -> dict:
        """Inspect one existing 3D feature selected by reference, index, fingerprint, or name."""
        return adapter.inspect_feature(
            document_id=document_id,
            feature=feature,
        )

    @mcp.tool()
    def repair_feature(
        document_id: str | None = None,
        operations: list[dict] | None = None,
        apply: bool = False,
    ) -> dict:
        """Plan or apply bounded repairs to existing 3D features: rename, suppress, or delete."""
        return adapter.repair_feature(
            document_id=document_id,
            operations=operations,
            apply=apply,
        )

    @mcp.tool()
    def list_sketch_entities(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        kinds: list[str] | str | None = None,
        max_items: int = 100,
    ) -> dict:
        """List existing sketch entities with reference, index, fingerprint, and geometry selectors."""
        return adapter.list_sketch_entities(
            document_id=document_id,
            sketch_ref=sketch_ref,
            kinds=kinds,
            max_items=max_items,
        )

    @mcp.tool()
    def inspect_sketch_entity(
        document_id: str | None = None,
        sketch_ref: str | None = None,
        entity: dict | None = None,
    ) -> dict:
        """Inspect one existing sketch entity selected by reference, index, or fingerprint."""
        return adapter.inspect_sketch_entity(
            document_id=document_id,
            sketch_ref=sketch_ref,
            entity=entity,
        )
