# CAD Patterns

This file is the operational memory for KOMPAS-3D / `kompas-mcp` CAD automation.
It stores rules that were verified on live models and should be checked before
guessing COM API behavior.

## How To Use This File

1. Start with `Quick Index` and choose rules that match the current task.
2. Apply the matching `Rules` before implementing or debugging.
3. Use `Case Studies` only for context and known working chains.
4. After a repeated live failure or reusable fix, add a new rule or update an
   existing one. Do not hide failed approaches if they prevent future loops.
5. In work notes and prompts, reference stable IDs like `CS-004` or `VAR-001`,
   not old section numbers.

## Quick Index

| Task / symptom | Read |
|---|---|
| Arc through 3 points is mirrored or goes the long way | `ARC-001`, `VERIFY-001` |
| COM field rejects a formula or silently resets it | `PARAM-001`, `VAR-001` |
| Need formula-driven CAD parameters | `PARAM-001`, `VAR-001` |
| Need a local coordinate system for parameterization | `CS-001` |
| Axis direction changes after switching CS / plane | `CS-002`, `DIR-001`, `VERIFY-001` |
| Changing an early CS breaks dependent geometry | `CS-003` |
| Sketch on angled plane has unstable origin | `CS-004` |
| Sketch moves after rebuild or parameter change | `SKETCH-001`, `CS-004` |
| Reference sketch projection constraints need source confirmation | `SKETCH-002` |
| Projected sketch entities need style changes | `SKETCH-003` |
| Need to create a constrained sketch without losing COM handles | `SKETCH-004`, `SKETCH-005` |
| Need to project sketch geometry and constrain to it | `SKETCH-004`, `SKETCH-006`, `SKETCH-003` |
| Need visible projection of a 3D point in a sketch | `SKETCH-006`, `SKETCH-005` |
| Need to edit or inspect an existing sketch after reopening | `SKETCH-007`, `SKETCH-002` |
| Generated model file misses late-created sketches | `SKETCH-008` |
| Sketch arc, line, axis, or curve has wrong direction | `VERIFY-001`, `ARC-001`, `CS-002` |
| Direction flag works but result is inverted | `DIR-001`, `VERIFY-001` |
| Spiral direction is confused with spiral construction side | `DIR-001`, `SPIRAL-001`, `VERIFY-001` |
| Solid body self-intersects at zero gap | `GAP-001` |
| 2D sketch point cannot be used as 3D operation reference | `EDGE-001` |
| Composite path mixes sketch edges and 3D edges | `EDGE-002` |
| Sketch cannot be assigned to extrude/revolve/evolution | `OP-001` |
| Bent coil / hook spiral phase is wrong | `SPIRAL-001`, `VAR-001` |
| Native curve fillet needs a source cut point but raw spiral endpoints cannot be read | `FILLET-003` |
| Need full bent-coil construction chain | `CASE-001` |

## Rules

### ARC-001: Arc Through Three Points Requires Direction Verification

Applies when:
- building an arc through 3 points;
- reproducing a sketch from sampled geometry;
- KOMPAS accepts the arc but the result is visually opposite.

Symptom:
- The arc passes through expected points but uses the wrong sweep direction.
- The body is valid, but the geometry is mirrored, goes the long way, or does
  not match the reference model.

Cause:
- A 3-point arc definition is geometrically ambiguous in CAD APIs. The API can
  choose the opposite orientation without raising an error.

Rule:
- After creating a 3-point arc, verify direction against the expected midpoint,
  tangent, or reference geometry.
- If the direction is wrong, swap arc endpoints or explicitly rebuild the arc
  with the opposite orientation.

Implementation:
```python
# Prefer an explicit direction check after arc creation.
arc = sketch.AddArcBy3Points(p1, p2, p3)
actual_mid = read_arc_midpoint(arc)

if distance(actual_mid, expected_mid) > tolerance:
    arc = sketch.AddArcBy3Points(p3, p2, p1)
```

Verification:
- Read back a point on the arc or compare generated geometry with a live model.
- For reliable arc/curve direction checks, use `VERIFY-001` and create a
  temporary point on the curve.
- Do not treat successful `Update()` as proof that the arc direction is correct.

Known examples:
- Reproduction of reference sketches from existing KOMPAS models.

Related:
- `VERIFY-001`

---

### VERIFY-001: Verify Geometry Direction With Temporary Probe Geometry

Applies when:
- operation, sketch, axis, line, curve, arc, or spiral direction is uncertain;
- the geometry is valid but appears mirrored, reversed, or built on the wrong
  side;
- API readback gives object existence but not enough semantic direction data.

Symptom:
- `Update()` and rebuild succeed, but the result is oriented incorrectly.
- Sketch geometry follows the wrong local axis direction.
- Arc/curve direction is ambiguous even though points lie on the curve.
- A direction flag works for one model state and fails after parameter changes.

Cause:
- KOMPAS often accepts multiple geometrically valid directions. This applies not
  only to 3D operations, but also to sketches, arcs, local axes, and curve-based
  constructions.

Rule:
- Verify direction by constructing temporary helper geometry, reading its
  coordinates, comparing them with the expected geometric relation, and then
  deleting the helper geometry.
- Prefer temporary points. For curves, arcs, lines, and axes, a point on the
  investigated object is usually the most reliable probe.
- When direction is relative, create two or more probe points and compare their
  order against each other and against nearby reference objects.

Algorithm:
```text
1. Build temporary helper geometry near/on the object under investigation.
   Usually use points. For curves and lines, use points on curve.

2. Read helper coordinates. If one coordinate is insufficient, read a group of
   coordinates: start/end points, midpoints, or points at two curve parameters.

3. Compare readback against the expected design relation:
   - expected side of a body/end plane;
   - increasing/decreasing axis coordinate;
   - start point before end point;
   - midpoint on expected arc side;
   - relative position to another reference object.

4. Decide whether direction/orientation is correct.

5. Delete temporary helper geometry after the investigation.
```

Implementation example:
```python
# Probe a curve direction with two temporary points.
probe_a = create_point_on_curve(curve, parameter=0.1)
probe_b = create_point_on_curve(curve, parameter=0.9)

coords_a = read_point_coordinates(probe_a)
coords_b = read_point_coordinates(probe_b)

is_expected_direction = coords_b.z > coords_a.z

delete_object(probe_a)
delete_object(probe_b)

if not is_expected_direction:
    reverse_or_rebuild_geometry()
```

Verification:
- Store or log the read coordinates while debugging.
- If automatic comparison is uncertain, ask the user to confirm the expected
  relation in the KOMPAS UI.

Known examples:
- Arc direction checks after `AddArcBy3Points`.
- Local axis direction checks after switching CS or angled plane.
- Bent coil spiral direction and construction side checks.

Related:
- `ARC-001`
- `CS-002`
- `DIR-001`
- `SPIRAL-001`

---

### PARAM-001: COM Fields Have Different Formula Semantics

Applies when:
- assigning numeric values, strings, expressions, or variables to COM fields;
- a field accepts a value in UI but rejects the same value through COM;
- formula strings work in one field and fail in another.

Symptom:
- COM raises a type error.
- Formula assignment is silently ignored.
- The model updates once but does not remain parametrized.

Cause:
- KOMPAS COM fields are not uniform. Some accept only numbers, some accept text
  formulas, and some require operation variables after object creation.

Rule:
- Classify the target field before assignment.
- Do not assume that a UI formula field accepts a string formula through COM.

Field classes:

| Field class | Accepts | Typical handling |
|---|---|---|
| Numeric-only COM property | number | assign fallback number, then use operation variable if needed |
| Formula-capable property | number or expression string | assign expression directly and read back |
| Operation-variable-backed property | variable expression after `Update()` | create object with number, then bind expression through property parameter |

Implementation:
```python
# Good default pattern for uncertain fields:
param.SomeDistance = 10.0
obj.Update()

# If the field must be parametrized and direct strings fail,
# switch to VAR-001 operation-variable binding.
```

Verification:
- Read back the value and expression when possible.
- Change the driving variable and rebuild the model.

Related:
- `VAR-001`

---

### CS-001: Use Coordinate Systems As Parameterization Tools

Applies when:
- geometry must follow a local direction;
- sketches, planes, or spirals should move together;
- global coordinates would require repeated manual transforms.

Symptom:
- Geometry works for one parameter set but breaks after size or angle changes.
- Formulas become complex because every point is defined in global coordinates.

Cause:
- The geometry is defined in the wrong coordinate context. KOMPAS operations
  often behave more predictably when the local coordinate system encodes the
  design intent.

Rule:
- Use local coordinate systems, planes, and projected references to express the
  intended construction frame.
- Keep formulas local where possible; avoid baking global offsets unless the
  reference model requires them.

Implementation:
```python
# Typical sequence:
# 1. create/reference CS or plane;
# 2. create sketch in that context;
# 3. project required 3D references into the sketch;
# 4. constrain sketch geometry to projections and local axes.
```

Verification:
- Change a driving diameter/length/angle and rebuild.
- Confirm that dependent sketches and operations remain attached to the design
  reference, not to an accidental global coordinate.

Known examples:
- `CASE-001`

---

### CS-002: Verify Axis Direction After Switching Coordinate Systems

Applies when:
- creating angled planes;
- using `BaseLine`, `Direction`, `LeadAxis`, or local axes;
- switching from global geometry to sketch/plane-local geometry;
- sketch lines, axes, arcs, or local coordinates appear reversed.

Symptom:
- A plane, spiral, or operation is created on the correct reference but points
  in the opposite direction.
- A model is valid but mirrored across the expected axis.
- A sketch is geometrically valid, but its local axis direction or curve
  direction does not match the intended construction logic.

Cause:
- KOMPAS local axes depend on reference object direction, plane normal, and API
  defaults. The same visual reference can produce different local axis signs.

Rule:
- After creating a local CS, plane, or operation direction, verify the effective
  axis direction by readback or live geometry.
- Apply the same rule to sketch geometry created in local coordinates. Sketches
  can have reversed line, arc, and axis directions even when constraints and
  dimensions look correct.
- Do not infer direction only from object names like `left`, `right`, `top`, or
  `base`.

Implementation:
```python
# Preferred: create a test/reference point or read operation direction.
expected_side = body_end_z + 1.0
actual_point = read_probe_point(operation)

if actual_point.z < expected_side:
    flip_direction(operation)
```

Verification:
- Use readback if the API exposes the property.
- If readback is unavailable or ambiguous, use `VERIFY-001`: create temporary
  probe points, read coordinates, compare expected relations, then delete probes.

Related:
- `VERIFY-001`
- `DIR-001`
- `SPIRAL-001`

---

### CS-003: Early Coordinate-System Changes Cascade Through The Model

Applies when:
- changing a baseline, plane, or sketch coordinate system that later operations
  depend on;
- fixing an early construction element in a working model.

Symptom:
- A local change appears correct but downstream geometry moves, flips, or
  becomes invalid.

Cause:
- KOMPAS operations store references to earlier coordinate systems, planes,
  sketches, and edges. Changing one early object changes every dependent object.

Rule:
- Treat early CS/plane/sketch changes as high blast-radius edits.
- After changing an early coordinate object, rebuild and verify every dependent
  operation.

Implementation:
```python
# Keep a short dependency list in the generator when changing early geometry.
affected = [angle_plane, center_sketch, bent_spiral, profile, evolution]

for obj in affected:
    obj.Update()
part.Rebuild()
```

Verification:
- Rebuild the full part, not only the changed object.
- Inspect dependent operations in creation order.

Known examples:
- `CASE-001`

---

### CS-004: Do Not Rely On Sketch Origin On API-Created Angled Planes

Applies when:
- creating `ISketch` on `IPlane3DByAngle`;
- a sketch must start from a known 3D point;
- geometry on an angled plane shifts after rebuild.

Symptom:
- The sketch is on the right plane but local `(0, 0)` is not where expected.
- A bent hook or auxiliary axis starts from an unstable or wrong point.

Cause:
- `IPlane3DByAngle` through API does not provide reliable control over the
  sketch local origin. In this context, `OriginPoint`, `BasePoint`, and `Point`
  properties for `ISketch` are unavailable or ineffective. Rebuild/recompute
  does not reproduce UI correction behavior.

Failed approaches:
- Explicitly setting `sketch.OriginPoint`.
- Calling `Part.Rebuild()` after plane creation.
- Replacing a sketch edge with a 3D axis in `BaseLine`.
- Reversing baseline edge direction as a stable origin fix.

Rule:
- Do not build important geometry from sketch `(0, 0)` on API-created angled
  planes.
- Project a known external 3D point into the sketch and build from that
  projection.

Implementation:
```python
center_sketch.AddProjectionOf(body_start_point)
proj_x, proj_y = center_sketch.GetPointProjectionToXY(body_start_point)

axis_start = (proj_x, proj_y)
axis_end = (proj_x, proj_y + 15.0)

axis_line = center_sketch.AddLine(axis_start, axis_end)
axis_start_point = center_sketch.AddPoint(*axis_start)
projected_point = center_sketch.GetObject("projected_point")

center_sketch.AddConstraint("vertical", [axis_line])
center_sketch.AddConstraint("merge_points", [axis_start_point, projected_point])
```

Verification:
- Rebuild after changing driving parameters.
- Confirm projected point and sketch geometry remain merged/constrained.

Known examples:
- `CASE-001`
- Report: `docs/bent-coil-sketch-coordinate-system.md`

---

### CS-005: Assign Sketch Coordinate System Before Plane

Applies when:
- an `ISketch` must use the coordinate system of a custom plane;
- a generated sketch is created through COM rather than the KOMPAS UI;
- UI placement fields show unexpected `Offset X`, `Offset Y`, rotation, or axis
  direction after assigning `Sketch.CoordinateSystem`.

Symptom:
- The sketch is on the correct base plane, but the placement dialog shows
  non-zero offset or orientation fields.
- Projecting geometry into the sketch produces a visible shift relative to the
  source object.
- Values from sketch geometry or endpoint coordinates appear in sketch placement
  settings.

Cause:
- Setting `Sketch.CoordinateSystem` after `Sketch.Plane` makes KOMPAS preserve
  the current sketch placement by writing the delta into placement fields. This
  differs from the UI default for creating a new sketch on a plane.

Rule:
- If a sketch must use a plane's coordinate system, assign
  `Sketch.CoordinateSystem` before `Sketch.Plane`.
- Do not "fix" placement by adding compensating sketch coordinates or auxiliary
  geometry; correct the sketch placement order first.
- If a sketch should not use a custom coordinate system, do not set
  `Sketch.CoordinateSystem` at all.

Implementation:
```python
sketch = sketchs.Add()
sketch.Name = name

# Correct order for plane-local sketch coordinates.
sketch.CoordinateSystem = plane_object
sketch.Plane = plane_object
sketch.Angle = 0.0
sketch.LeftHandedCS = False
sketch.Update()
```

Verification:
- Open the sketch placement settings in KOMPAS.
- Confirm the base plane and coordinate system are selected, while offset,
  rotation, guide objects, and Z-axis direction fields are empty or zero.
- Project a known source object and confirm the projection is not shifted relative
  to the object.

Known examples:
- Extension spring self-wrapping right hook sketches.

---

### SKETCH-001: Finished Sketches Must Be Fully Constrained

Applies when:
- a generated sketch drives a 3D operation;
- geometry changes unexpectedly after rebuild;
- a spring/coil/profile moves when parameters change.

Symptom:
- Sketch remains under-defined after dimensions are added.
- Regeneration moves geometry unexpectedly or fails.
- KOMPAS shows a misleading green fully-defined state on a complex sketch.

Cause:
- Dimensions are not the same as constraints. KOMPAS considers a sketch fully
  defined only when all geometric degrees of freedom are fixed. Some versions
  can also report a false positive fully-defined UI status.

Rule:
- Every production sketch must be fully constrained.
- Create sketch constraints inside the original `BeginEdit()` block, directly
  after creating the relevant geometry. `AddConstraint` after `EndEdit()` can
  return `None` without applying anything.

Implementation:
```python
sketch.BeginEdit()
line = sketch.AddLine(...)
point = sketch.AddPoint(...)

sketch.AddConstraint("merge_points", [point, projected_point])
sketch.AddConstraint("vertical", [line])
sketch.AddConstraint("fixed_length", [line], value=radius)

sketch.EndEdit()
```

Status check:
```python
status = ksSketchDef.GetStatus()
# 0 = not defined, 1 = under-defined, 2 = fully defined, 3 = over-defined
if status == 2:
    success = ksPart.Rebuild()
```

Verification:
- Rebuild after dimensions and constraints.
- If over-defined, remove the last dimension/constraint and try the next most
  explicit one.
- If the API status is unavailable, verify by rebuild and by changing driving
  parameters.

Known examples:
- `compression_spring/v7`: the coil sketch was under-defined and moved when the
  outer diameter changed.
- `CASE-001`

---

### SKETCH-002: Projection Constraint References May Need UI Confirmation

Applies when:
- inspecting a known-good reference sketch;
- trying to reproduce constraints from an existing `.m3d` model;
- `inspect_sketch_full` identifies projection constraints but cannot identify
  what projected object they reference.

Symptom:
- Most sketch geometry, dimensions, and constraints are visible through the
  inspection tool.
- Projection constraints are identified, but the referenced source object is
  missing or ambiguous.

Cause:
- The sketch inspection tool has been expanded and can now capture almost all
  information available in a sketch. The remaining known gap is resolving the
  source object referenced by projection constraints.

Rule:
- Use `inspect_sketch_full` as the primary source for sketch geometry,
  dimensions, and constraints.
- When projection constraints are present, ask the user to inspect the sketch in
  the KOMPAS UI and identify which external objects the projections reference.
- Do not guess projection references from nearby geometry unless the relation is
  confirmed by coordinates or UI inspection.

Implementation:
```python
# Use full sketch inspection first.
sketch_info = inspect_sketch_full(reference_sketch)

for constraint in sketch_info.constraints:
    if constraint.type == "projection" and constraint.source is None:
        ask_user_to_check_projection_source_in_ui(constraint)
```

Verification:
- Compare inspected constraints with the KOMPAS UI when projection references are
  missing.
- For inferred projection sources, verify coordinates before generating code.

Known examples:
- Reference sketch inspection can identify projection constraints, but the user
  may still need to confirm what they project from in the UI.

Related:
- `SKETCH-003`

---

### SKETCH-003: Change Projected Sketch Entity Style Through API5 Hit-Test Refs

Applies when:
- a sketch entity was created by projecting another sketch edge with
  `ISketch.AddProjectionOf`;
- the projected result must become auxiliary/construction geometry;
- direct API7 style edits appear to work temporarily but revert after
  `EndEdit()` / `Update()`.

Symptom:
- `ILineSegment.Style = 6` on a projected line changes the value in the active
  edit session, but the line returns to style `1` after regeneration.
- `ksGetObjParam` / `ksSetObjParam` with `ko_LineSegParam = 11` does not read the
  projected entity by its API7 `Reference`.
- `ksSetObjectStyle(api7_reference, 6)` returns false or has no effect.

Cause:
- Projected sketch lines expose temporary drawing result objects through API7.
  The style persisted by the UI is applied through the 2D editor hit-test/object
  layer, not through the temporary `ILineSegment` or the API7 `Reference`.

Rule:
- Treat this like the UI does: hit-test the projected entity at a point on the
  line, get the internal API5 object reference, then change that object's style.
- Use a point away from intersections where possible, usually the line midpoint.
- Clean up the editor state after changing style.

Implementation:
```python
# target_sketch is the sketch containing projected entities.
# segment_geometry comes from inspect/readback of the projected segment.
target_sketch.BeginEdit()
doc2d = get_api5_active_document2d()

mx = (segment_geometry["start"][0] + segment_geometry["end"][0]) * 0.5
my = (segment_geometry["start"][1] + segment_geometry["end"][1]) * 0.5

found_ref = 0
for tolerance in (0.001, 0.01, 0.1, 1.0, 5.0, 20.0):
    found_ref = doc2d.ksFindObj(mx, my, tolerance)
    if found_ref:
        break

if not found_ref:
    raise RuntimeError("Projected object was not found by hit-test")

doc2d.ksSetObjectStyle(found_ref, 6)  # 6 = auxiliary/construction style.

# Conservative cleanup mirroring exit from UI-style object interaction.
doc2d.ksLightObj(found_ref, 0)
doc2d.ksEndObj()

target_sketch.EndEdit()
target_sketch.Update()
```

Verification:
- Inspect the sketch after `EndEdit()` / `Update()` and confirm `Style == 6`.
- Do not trust the in-session value before regeneration.
- Check `ksSetObjectStyle` and final readback; successful live examples changed
  both projected diagonal and projected shelf from style `1` to style `6`.

Known examples:
- `self_wrapping_phase2_first_and_projected_sketch1_v24`: projected diagonal and
  projected shelf in `SELF_WRAPPING_PHASE2_LEFT_SKETCH1_PROJECTED` were changed to
  auxiliary style through `ksFindObj` + `ksSetObjectStyle`.

Related:
- `SKETCH-002`
- `EDGE-002`

---

### SKETCH-004: Sketch Edit Session Lifecycle

Applies when:
- creating a sketch that will contain dimensions, constraints, projected entities,
  or helper construction geometry;
- adding geometry that later 3D operations depend on;
- changing an existing sketch through automation.

Symptom:
- Geometry is created, but later constraints silently fail.
- Projected objects are visible in KOMPAS but cannot be found through ordinary
  API7 collections after reopening the sketch.
- The same operation works in the UI but not through a direct object call.

Cause:
- KOMPAS exposes different object layers at different moments: model API7
  objects, active 2D-editor API5 hit-test refs, and temporary objects returned
  during `BeginEdit()`.
- Some handles are only reliable while the sketch edit session that created them
  is still open.

Rule:
- Treat a sketch edit as a transaction. Create geometry, keep returned COM
  objects, add constraints/dimensions that need those objects, then `EndEdit()`
  and `Update()`.
- Do not throw away returned geometry handles if the next step must constrain to
  that geometry.
- Reopen/readback is for verification and UI-like edits, not for guessing the
  original creation handles.

Implementation order:
```python
target_sketch = create_or_find_sketch(part, plane)
edit_doc = target_sketch.BeginEdit()
drawing = get_sketch_drawing_container(edit_doc)

created = {}
created["base"] = add_line(drawing, p1, p2, style=6)
created["axis"] = add_line(drawing, p3, p4, style=3)
created["point"] = add_point(drawing, p4, style=127)

add_constraints(created)
add_dimensions(drawing, created)

target_sketch.EndEdit()
target_sketch.Update()
part.Update()

snapshot = inspect_sketch_full(target_sketch)
assert snapshot.constraints_state == "fully_defined"
```

Verification:
- Use `inspect_sketch_full` after `EndEdit()` / `Update()`.
- Verify entity count, styles, dimensions, dimension expressions, constraint
  count, and `constraints_state`.
- Reopen the saved file for final proof when the model is meant to be inspected
  later.

Known examples:
- `self_wrapping_phase2_first_and_projected_sketch1_v48`: constraints and
  dimension were reliable after being created before the edit session ended.

Related:
- `SKETCH-001`
- `SKETCH-005`
- `SKETCH-008`

---

### SKETCH-005: Add Constraints While The Required Handles Are Still Live

Applies when:
- constraining generated lines, points, projected geometry, or helper axes;
- a later `BeginEdit()` cannot see entities through `LineSegments` / `Points`;
- `NewConstraint()` or `Create()` returns false after a sketch was closed.

Symptom:
- A constraint can be described geometrically, but KOMPAS does not create it.
- API7 collections are empty or incomplete after reopening a generated/projected
  sketch.
- API5 `ksFindObj` finds a visible object, but `ksSetObjConstraint` still returns
  `0`.

Cause:
- Visibility in the UI and suitability as a COM constraint partner are not the
  same thing.
- The safest constraint partners are the COM objects returned by geometry
  creation calls in the active edit session.

Rule:
- Add ordinary geometric constraints immediately after creating the affected
  entities.
- For projected geometry, add constraints to projected result objects in the same
  `BeginEdit()` session as `AddProjectionOf` when possible.
- Use API7 `NewConstraint()` / object-specific constraint helpers for live API7
  geometry. Use API5 hit-test refs for UI-like style/selection operations, not as
  the first choice for geometric constraints.

Implementation:
```python
edit_doc = sketch.BeginEdit()
drawing = get_sketch_drawing_container(edit_doc)

line_a = add_line(drawing, a1, a2, style=6)
line_b = add_line(drawing, b1, b2, style=6)
axis = add_line(drawing, x1, x2, style=3)

add_constraint(line_a, "vertical")
add_constraint(line_a, "merge_points", index=1, partner=line_b, partner_index=0)
add_constraint(axis, "point_on_curve", index=0, partner=line_a)
add_constraint(axis, "point_on_curve", index=0, partner=line_b)

sketch.EndEdit()
```

Verification:
- Inspect readback constraints after rebuild.
- Verify intended owner/partner geometry, not only raw count.
- A created constraint with the right count but wrong endpoint is still wrong.

Known examples:
- In the self-wrapping sketch, post-factum constraints on reopened projected
  geometry failed, while creation-time constraints produced a fully defined
  sketch.

Related:
- `SKETCH-004`
- `SKETCH-006`
- `SKETCH-007`

---

### SKETCH-006: Project Geometry First, Then Constrain To The Projection Results

Applies when:
- a sketch must reference geometry from another sketch;
- projected geometry is used as a stable construction base;
- a projected point is unavailable and a projected edge is used as fallback.
- a visible projected `IPoint3D` is required in the sketch, not just projected XY
  coordinates.

Symptom:
- Projection appears in the sketch, but dependent helper geometry is not fully
  fixed.
- Constraints to projected entities fail when added in a later bridge call.
- A fallback projected line adds more degrees of freedom than a point-like
  reference would.
- `GetPointProjectionToXY(point3d)` returns correct XY coordinates, but the
  sketch contains no visible projection point.
- `AddProjectionOf(point3d)` returns `None` when called outside the active sketch
  edit session.

Cause:
- `ISketch.AddProjectionOf` returns result objects that are most useful while the
  current edit session is still active.
- For `IPoint3D`, `AddProjectionOf(point3d)` may only create/return the visible
  projected `IPoint` when called inside `sketch.BeginEdit()`.
- Projection constraints bind projected entities to their sources; extra manual
  fixation of the projected entities is usually wrong. Helper geometry should be
  constrained to the projection results instead.

Rule:
- Open the target sketch once.
- Call `source_sketch.Edges(...)` to get source `IEdge` objects.
- Call `target_sketch.AddProjectionOf(edge)` inside the active target sketch edit
  session.
- For a 3D point, call `target_sketch.AddProjectionOf(point3d)` inside the same
  `BeginEdit()` session where possible. Calling it before edit may still allow
  XY readback, but can fail to create a visible projection object.
- Keep the returned projected result objects and use them immediately as partners
  for helper-geometry constraints.
- Normalize the `AddProjectionOf` return value before use: KOMPAS may return a
  single COM object, a Python list/tuple, or a COM collection depending on the
  source edge and API wrapper state.
- Do not add dimensions or duplicate formulas to projected geometry just to mimic
  the source; the projection link is the source of truth.

Implementation:
```python
edit_doc = target_sketch.BeginEdit()
drawing = get_sketch_drawing_container(edit_doc)

projected_diagonal = target_sketch.AddProjectionOf(source_diagonal_edge)[0]
projected_shelf = target_sketch.AddProjectionOf(source_shelf_edge)[0]

vertical_base = add_line(drawing, top, bottom, style=6)
mirror_diagonal = add_line(drawing, bottom, shelf_free, style=6)
axis = add_line(drawing, intersection_hint, shelf_free, style=3)

add_constraint(vertical_base, "merge_points", index=0,
               partner=projected_diagonal, partner_index=projected_top_index)
add_constraint(mirror_diagonal, "merge_points", index=1,
               partner=projected_shelf, partner_index=projected_free_index)
add_constraint(axis, "point_on_curve", index=0, partner=projected_diagonal)
add_constraint(axis, "point_on_curve", index=0, partner=mirror_diagonal)
```

For `IPoint3D`, do not replace the projection with a manually drawn sketch point:

```python
edit_doc = target_sketch.BeginEdit()
drawing = get_sketch_drawing_container(edit_doc)

projected_point = normalize_projection_result(
    target_sketch.AddProjectionOf(source_point3d)
)

vertical_base = add_line(drawing, projected_xy, bottom, style=6)
work_diagonal = add_line(drawing, projected_xy, diagonal_end, style=1)

add_constraint(vertical_base, "merge_points", index=0,
               partner=projected_point, partner_index=0)
add_constraint(work_diagonal, "merge_points", index=0,
               partner=projected_point, partner_index=0)

target_sketch.EndEdit()
```

Verification:
- `inspect_sketch_full` should show projection constraints and the helper
  constraints that depend on them.
- For projected 3D points, `inspect_sketch_full` should show a projected point
  object, typically with style `127`, parent projection chain, and the UI
  projection constraint.
- Confirm projected entities remain projected after rebuild.
- If a whole projected edge was used as fallback for a point, inspect the final
  constraint state carefully; a true projected point/vertex is preferable when
  available.

Known examples:
- `self_wrapping_phase2_first_and_projected_sketch1_v48` uses projected diagonal
  and shelf references as construction bases, then constrains helper geometry to
  them before closing the sketch.
- `right_first_sketch_endpoint_v15` creates a visible projection of the right
  spiral endpoint point and uses it as the anchor for the first right
  self-wrapping sketch.

Related:
- `SKETCH-002`
- `SKETCH-003`
- `SKETCH-005`

---

### SKETCH-007: Reading Or Editing An Existing Sketch Requires UI-Like State

Applies when:
- changing a sketch after it already exists;
- inspecting a saved/reopened model;
- a visible UI object is not available through ordinary API7 collections.

Symptom:
- KOMPAS UI can edit or select an object, but automation cannot find it through
  `LineSegments`, `Points`, or a stored API7 reference.
- Direct COM calls work on newly created objects but fail after reopening.

Cause:
- KOMPAS UI operations often go through the active 2D editor selection/hit-test
  layer. Direct API7 model collections are not always the same surface.

Rule:
- For readback, use `inspect_sketch_full` first.
- For UI-like edits, activate/open the target document and sketch, then use API5
  active-document operations such as `ksFindObj` when a direct API7 object is not
  available.
- Treat hit-test refs as editor-layer refs. They are proven useful for style and
  selection-like edits; do not assume they are valid partners for all geometric
  constraints.

Implementation:
```python
snapshot = inspect_sketch_full(sketch)

sketch.BeginEdit()
doc2d = get_api5_active_document2d()
ref = doc2d.ksFindObj(x_on_entity, y_on_entity, tolerance)
if not ref:
    raise RuntimeError("Object is visible but not found by editor hit-test")

# Use the editor-layer operation that matches the UI action.
doc2d.ksSetObjectStyle(ref, 6)
doc2d.ksLightObj(ref, 0)
doc2d.ksEndObj()
sketch.EndEdit()
```

Verification:
- Re-inspect after `EndEdit()` / `Update()`.
- For saved artifacts, close and reopen the file, then inspect again.

Known examples:
- Projected style changes require API5 hit-test refs (`SKETCH-003`).
- A reopened projected sketch can be visible but not expose the same editable
  API7 line collection as during creation.

Related:
- `SKETCH-003`
- `SKETCH-005`

---

### SKETCH-008: Save After Late Sketch Edits And Verify From Disk

Applies when:
- a script creates a model, then adds sketches/projections/constraints in later
  bridge calls;
- KOMPAS remains open with unsaved changes;
- a user needs to inspect the resulting `.m3d` file later.

Symptom:
- The live KOMPAS session shows the expected sketches, but the saved file misses
  late-created sketches after KOMPAS is closed.
- Reports/snapshots show geometry that is not present in the reopened `.m3d`.

Cause:
- An early save during base model creation does not include later sketch edits.
- Closing KOMPAS without a final save discards those late edits.

Rule:
- Always save after the last sketch/projection/constraint/dimension operation.
- For important artifacts, close or reopen the document and verify the saved file
  from disk.
- Do not treat a JSON snapshot from a live session as proof that the `.m3d` file
  contains the same state.

Implementation:
```python
build_base_model()
add_sketches_and_constraints()
snapshot = inspect_sketch_full(target_sketch)

save_document(document_id=document_id, path=output_path, close_after_save=True)

opened = open_document(output_path)
saved_snapshot = inspect_sketch_full(opened_target_sketch)
assert saved_snapshot.summary == snapshot.summary
```

Verification:
- Reopen the saved `.m3d` and list sketches by name.
- Inspect the important sketch and confirm entity counts, styles, constraints,
  dimensions, and state.

Known examples:
- `self_wrapping_phase2_first_and_projected_sketch1_v47` was the first artifact
  verified to save both sketches after final edits.
- `self_wrapping_phase2_first_and_projected_sketch1_v48` was verified from disk
  as fully defined with auxiliary projected/reference geometry.

Related:
- `SKETCH-004`
- `VERIFY-001`

---

### DIR-001: Direction Parameters And Sketch Directions Require Verification

Applies when:
- setting operation direction flags;
- creating extrusions, cuts, offset planes, chamfers, or spirals;
- creating sketch geometry whose direction matters;
- the result is valid but on the wrong side or reversed along a local axis.

Symptom:
- Operation succeeds, but the result is mirrored or built in the opposite
  direction.
- Sketch line, arc, or curve direction is reversed relative to the intended
  construction axis.
- KOMPAS does not report an error.

Cause:
- The API accepts direction as numbers, enums, or booleans but does not check
  whether the result matches the intended geometry context.
- Sketch entities and curves can also be direction-sensitive. A valid entity can
  still have the opposite start/end order, arc sweep, or local-axis relation.

Rule:
- After any operation with a direction parameter, verify it.
- After creating direction-sensitive sketch geometry, verify start/end order,
  arc sweep, and relation to local axes.
- For spirals, keep winding direction and construction direction separate.

Known direction fields:

| Operation | Parameter | Values | Note |
|---|---|---|---|
| Extrude | `directionType` | `True` forward, `False` backward | relative to sketch normal |
| Cut | `directionType` | `True` forward, `False` backward | relative to sketch normal |
| Offset plane | `direction` | `1` normal, `-1` opposite | |
| Spiral winding | `buildDirection` | `-1` left, `1` right | enum may also be used |
| Spiral construction side | distance sign / placement | positive or negative side | separate from winding |
| Chamfer | `direction` | `True` along, `False` across | operation-specific |

Verification:
- Prefer readback of operation parameters.
- If readback is unavailable or insufficient, use `VERIFY-001`: create temporary
  probe points, read coordinates, compare expected relations, then delete probes.

Known examples:
- `extension_spring/bent_coil_left_spike_v33`: hook spiral built downward because
  construction direction was wrong; winding direction was a separate parameter.

Related:
- `VERIFY-001`
- `SPIRAL-001`

---

### GAP-001: Zero Gap Can Produce Solid Self-Intersection

Applies when:
- generating springs or coils;
- requested gap is zero or effectively zero;
- adjacent turns touch exactly.

Symptom:
- KOMPAS reports a self-intersecting body.
- The geometry looks mathematically valid but solid creation fails.

Cause:
- At exactly zero clearance, adjacent coil surfaces meet at the same point/line.
  The solid modeler can classify this as self-intersection.

Rule:
- Always keep gap strictly greater than zero.
- Use `0.01 mm` as a safe minimum unless a task-specific tolerance says
  otherwise.

Implementation:
```python
gap = max(requested_gap, 0.01)
```

Known examples:
- `compression_spring`: models with no clearance between turns produced
  self-intersection errors.

---

### EDGE-001: Sketch 2D Points Cannot Be Passed Directly As 3D References

Applies when:
- a 3D operation asks for a reference point;
- the natural source point exists only inside a sketch;
- UI accepts a sketch point but COM does not.

Symptom:
- Passing a 2D sketch point to a field like `reference_point` fails.
- The API expects a 3D object even though the UI can select the sketch point.

Cause:
- KOMPAS COM API does not directly accept a 2D sketch point as a 3D operation
  reference. It accepts 3D points created in the model container.

Rule:
- Create a model-level 3D point tied to geometry, instead of extracting and
  passing a sketch point.

Implementation: point on curve
```python
point3d = model_container.Points.Add()
param = point3d.Parameter
param.Reference = curve_object
param.Offset = 50.0
param.Direction = 1.0
point3d.Parameter = param
point3d.Update()
```

Implementation: displacement from existing 3D point
```python
point3d = model_container.Points.Add()
param = point3d.Parameter
param.Reference = existing_3d_point
param.Offset = 20.0
param.Direction = 1.0
point3d.Parameter = param
point3d.Update()
```

Known examples:
- `CASE-001`: UI could use a 2D sketch point as spiral base, but API required a
  3D point created through `model_container.Points.Add()`.

---

### EDGE-002: CompositeCurve3D Accepts A Mixed Array Of Edges

Applies when:
- building a composite trajectory from sketch geometry and 3D geometry;
- an operation needs one path made from multiple sources;
- passing a whole sketch as a path segment fails.

Symptom:
- Composite trajectory cannot be built from a sketch object directly.
- Evolution/path operation needs individual edges.

Cause:
- `CompositeCurve3D` expects an array of edge COM objects. Sketch edges and 3D
  edges have different COM interfaces, but can still be placed in one `Edges`
  array.

Rule:
- Extract individual sketch edges with `GetObject(...)` and combine them with
  3D edges in the composite curve.

Implementation:
```python
path_edges = []

# 3D edge
law_curve = model_container.CurvesEx.Add("LawCurve3D")
path_edges.append(law_curve.Edge)

# Sketch edge
drawing_container = sketch.GetObject("ksLineSeg:2")
sketch_edge = drawing_container.Segments[0]
path_edges.append(sketch_edge)

composite = model_container.CurvesEx.Add("CompositeCurve3D")
composite.Edges = path_edges
composite.Update()
```

Known examples:
- `kompas_bridge.py` around the bent-coil path construction used extracted
  `ksLineSeg:N` edges together with 3D edges.
- `CASE-001`

---

### OP-001: Assign Sketches To 3D Operations Through SetSketch/SetProfile Fallbacks

Applies when:
- assigning a sketch/profile to extrude, revolve, or evolution;
- direct `.Sketch = ...` does not work;
- different KOMPAS versions expose different assignment methods.

Symptom:
- Direct sketch assignment raises an error.
- Operation is created but has no profile/sketch.

Cause:
- KOMPAS COM versions differ. Some expose `SetSketch`, some `SetProfile`, and
  some accept direct property assignment.

Rule:
- Try method assignment first, then property assignment fallback.
- Raise a clear error if none of the compatible APIs are present.

Implementation:
```python
assigned = False

for method_name in ("SetSketch", "SetProfile"):
    setter = safe_get(operation, method_name)
    if callable(setter):
        setter(sketch)
        assigned = True
        break

if not assigned:
    for attr in ("Sketch", "Profile"):
        try:
            setattr(operation, attr, sketch)
            assigned = True
            break
        except Exception:
            pass

if not assigned:
    raise RuntimeError("Cannot assign sketch/profile: no compatible KOMPAS API")
```

Known examples:
- `kompas_bridge.py` evolution/extrusion assignment paths.

---

### SPIRAL-001: InitialAngle Is Not Positioning Orientation

Applies when:
- controlling spiral phase;
- joining bent coil / hook spirals to body geometry;
- working with `ICylindricSpiral3D` positioning.

Symptom:
- Spiral starts at the wrong phase.
- Changing variables does not move the spiral as expected.
- Agent changes local CS rotation instead of spiral initial angle.

Cause:
- `ICylindricSpiral3D` has two independent angular mechanisms:

| Mechanism | Initial angle | Positioning orientation |
|---|---|---|
| Meaning | phase of the first turn | rotation of local CS relative to guide |
| API surface | `spiral.InitialAngle` or spiral parameter | `ILocalCSAxesDirectionParam`, Euler readback, object orientation modes |
| Formula support | yes, when field supports it | not a formula field; COM derives absolute orientation from placement mode |
| Use in bent coil | phase of the helical curve | placement of the spiral's local coordinate system |

Rule:
- Control spiral phase through `InitialAngle`, not through positioning CS
  rotation.
- Do not treat visible nutation/precession/rotation fields as disposable
  garbage. KOMPAS shows absolute orientation values for the positioned local CS;
  they can appear regardless of the placement mode.
- The physical phase at the connection point is the sum of positioning
  orientation and the spiral's own initial angle. Debug bent-coil connection
  failures by checking both components together.
- `OrientationType=2` / `ILocalCSOrientByObjectParam.SetOrientationObject(...)`
  is not accepted as a bent-coil fix: it can produce a full contour count while
  placing the spiral incorrectly.

Verification:
- Check the positioning mode, the visible absolute orientation, and the spiral
  initial angle together.
- Verify geometry visually/live; a full contour count alone is not sufficient for
  bent-coil spirals.

Known examples:
- `CASE-001`: `_apply_spiral_turning_angle` changed positioning orientation,
  not spiral phase. Stable left hook used numeric initial angle `90`.
- `bent_coil_left_spike`: orient-by-object was re-tested and rejected because it
  gives an incorrect physical placement despite the correct orientation object.
- `bent_coil_left_spike` right hook: with axis-direction positioning, KOMPAS can
  show a `90` degree absolute rotation for the position. The right spiral uses
  internal initial angle `270` so the effective phase is `360`, not `180`.

Related:
- `DIR-001`
- `VAR-001`

---

### PROFILE-001: Place Wire Profile At Final Path Sequence End

Applies when:
- building extension spring sweep/evolution profiles;
- building compression spring sweep/evolution profiles;
- building torsion spring sweep/evolution profiles;
- building conical spring sweep/evolution profiles;
- adding independent left/right hook composition;
- choosing `profile_anchor_plane` for a multi-segment `full_path_sequence`.

Symptom:
- Some hook types place the wire profile at the left/start side, while others
  place it at the right/end side.
- A mixed left/right hook generator changes profile placement depending on which
  hook type owns the anchor.

Cause:
- Old hook previews chose the profile anchor from hook-specific paths. This was
  harmless when both sides used the same hook type, but it is not a stable
  contract for independent side composition.

Rule:
- Treat `full_path_sequence` as the canonical left-to-right final contour order.
- Always set the wire profile anchor to `full_path_sequence[-1]` with
  `vertex = "end"`.
- Do not choose the profile anchor from a hook-type-specific left segment.
- Once the profile is anchored to a point on the final contour, keep the profile
  sketch local: `profile_path_offset = [0, 0, 0]`,
  `profile_sketch_center = [0, 0]`, and constrain/dimension the profile circle
  itself. Do not keep an old in-sketch offset by coil radius.

Verification:
- Preview: `profile_anchor_plane.path_name == full_path_sequence[-1]` and
  `profile_anchor_plane.vertex == "end"` for every extension hook type.
- Live CAD: `select_profile_anchor_plane.profile_anchor_path_ref` should match
  the last resolved sequence path.
- Live CAD: `create_wire_profile.profile_center` should be `[0.0, 0.0]` for
  anchor-plane-based spring profiles.

Known examples:
- `machine_hooks`, `v_hooks`, `u_hooks`, `center_loop_hooks`,
  `extended_center_loop_hooks`, and `open_loop_hooks` now use the right/end side
  of their final sequence.
- `self_wrapping_hooks` and `bent_coil_left_spike` use the same helper instead of
  hand-written anchor paths.
- `torsion_spring` uses local profile sketches for tangent, radial, and
  axial-transition legs; radial and axial transition fillets no longer require a
  sketch-level coil-radius offset.
- `conical_spring` uses local profile sketches on the final contour endpoint;
  start/end conical segments, native curve-fillet transitions, and ground surface
  cuts must not reintroduce a profile sketch offset.
- `compression_spring` uses the same final endpoint anchor and local profile
  sketch. Cylindrical segment transitions use native result edges for both
  right-hand and left-hand turns; the legacy trimmed-connect path is now an
  explicit fallback, not the auto mode.
- Conical transition fillet defaults should be based on the limiting local cone
  radius at segment joints, not wire diameter. Keep the default just below that
  radius and allow explicit override for model-specific tuning.

---

### VAR-001: Bind Formulas Through Operation Variables After Object Creation

Applies when:
- a COM field accepts only a number during object creation;
- the UI accepts a formula but direct COM string assignment fails;
- a generated point/plane/spiral must remain parametrized.

Symptom:
- Assigning a string expression like `"(D1 - WD1) / 2"` raises a type error.
- Formula assignment silently resets.
- The object keeps a numeric fallback and does not update when variables change.

Cause:
- Some COM fields accept only numeric values before the first `Update()`. The
  formula must be attached later through an operation variable/property
  parameter that points at the created object field.

Rule:
- Use the pattern: numeric fallback -> `Update()` -> operation-variable binding
  -> `Update()`.

Implementation:
```python
# 1. Create object with numeric fallback.
point3d = container.Points.Add()
point3d_param = point3d.Parameter

disp_param = CastTo(point3d_param, "IPoint3DParamDisplace")
disp_param.Distance = 15.0
point3d.Update()

# 2. Bind formula after creation.
op_var = part.PropertyParameter("Distance", point3d)
op_var.Expression = "(D1 - WD1) / 2"
point3d.Update()
```

Known fields:
- `IPoint3DParamDisplace.Distance`: bent spiral center offset.
- `IPlane3DByAngle.Angle`: bend angle plane.
- `IFilletCurve.Radius`: native 3D curve fillet radius. Use the staged
  `FILLET-002` order below; assigning `Radius` before the first `Update()` can
  leave the saved operation radius at `0.0`.

Verification:
- Change `D1`, `WD1`, or the driving variable and rebuild.
- Confirm the dependent object moves, not just the first numeric fallback.

Known examples:
- `CASE-001`: center of bent spiral stayed at `15.0` until the offset was bound
  through operation variable expression `(D1 - WD1) / 2`.
- `sample/live_self_wrapping_phase2_sketch.py`: v60 native curve fillets keep
  operation variable `Радиус = SFR1` after save and reopen.

### FILLET-001: Use Native Curve-Fillet Result Edges In Final Contours

Native `FilletCurve` operations are feature containers in KOMPAS. Do not put the
whole `IFilletCurve` object into a final sweep/evolution contour. It may appear
valid through API creation and then fail after UI rebuild.

For contour membership, use the feature result edges:

1. Create and update the native `IFilletCurve`.
2. Bind operation variable `Радиус` if required.
3. Get the owner feature: `fillet.Owner`.
4. Read `fillet.Owner.ModelObjects(7)`. It returns the three selectable result
   `IEdge` objects shown under the fillet container in the KOMPAS tree:
   trimmed source curve 1, fillet curve, trimmed source curve 2.
5. Use those result edges, not the `IFilletCurve`, in the final `Contour3D`.

Known example:
- `self_wrapping_hooks` left hook: using whole `FilletCurve` gave a false-positive
  API build, but `RebuildDocument()` invalidated the contour/body. Replacing it
  with `Owner.ModelObjects(7)` result edges fixed rebuild stability.

### FILLET-002: Assign Native Curve-Fillet Radius After First Update

For native 3D `IFilletCurve` operations, do not set `Radius` before the first
`Update()`. On legacy extension-hook connector curves this produced visually
valid-looking operations whose saved radius read back as `0.0`.

Use this order:

1. Create the `IFilletCurve` and assign `Curve1`, `Curve2`, trim flags, and cut
   points.
2. Call `Update()` once to materialize the operation topology.
3. Assign numeric `FilletCurve.Radius`.
4. Call `Update()` again and verify `FilletCurve.Radius` readback.
5. Bind operation variable `ParameterNote == "Радиус"` to the driving expression
   such as `TFR1` or `SFR1`.
6. Call `Update()` again and verify the expression reads back exactly as the
   driving variable, not as `TFR1 - <offset>`.
7. Read `fillet.Owner.ModelObjects(7)` and use the result edges in the final
   contour, per `FILLET-001`.

Verification example for legacy extension hooks:

```text
radius=3.0
radius_readback=3.0
staged_updates=[True, True]
expression_after=TFR1
source_path_count == expected_edges_count == edges_count
```

### FILLET-003: Use Logical Cut Points For Raw Spiral Fillet Sources

Native `FilletCurve` can accept a raw spiral/path object as `Curve1` even when
the same COM object does not expose usable endpoint readback through `GetPoint`.
Do not add an extra connector or auxiliary fillet only to get a selectable source
edge. That changes the model topology.

When the intended geometry is an unfilleted joint followed by a right-side native
fillet, keep the raw source curve and provide the cut point from generator
metadata:

1. Resolve `Curve1` to the raw body path.
2. Read the logical body end from `segment_plan`.
3. Use that point as `Curve1CutPoint`.
4. Compute `Curve2CutPoint` from the target curve endpoints near the same logical
   point.
5. Continue with the staged `FILLET-002` update/radius/binding order.

Known example:
- `bent_coil_left_spike -> self_wrapping_hooks`: the bent-coil-to-body joint must
  remain unfilleted. The right self-wrapping transition fillet uses raw
  `BODY_PATH` plus the logical body end point, producing a stable `10/10/10`
  contour without a synthetic left bent-to-body fillet.
- `compression_spring` native transitions use cut points slightly inside the
  adjacent spiral segments, not the exact shared endpoint. For cylindrical
  springs, create those cut points on the actual COM curve with
  `Point3DParamCurve`; analytic preview coordinates can pick the wrong selectable
  side on left-hand spirals even when the preview phase gap is zero.
- The default cylindrical native radius is `min(0.4 * mean_radius,
  1.5 * wire_diameter)` (`TFR1 = min(0.2 * (D1 - WD1), 1.5 * WD1)` for the
  standard outside-diameter variable). Stage native fillets in UI-like order:
  create/update topology, optionally update at a smaller seed radius, then update
  at the target radius and bind `Радиус = TFR1`.

### CONTOUR-001: Build KOMPAS Contours In Continuous UI Order

KOMPAS contour assembly follows UI-like continuity rules. If an added element does
not share an endpoint with the current contour end, that element and subsequent
elements may be ignored or collapsed even when API assignment succeeds.

For generated path contours:

- inspect candidate `IEdge.GetPoint(True/False)` endpoints;
- order result edges and sketch edges by actual endpoint continuity, not collection
  index alone;
- verify `source_path_count` and `EdgesCount` immediately after contour creation;
- reopen and call `RebuildDocument()` before declaring the contour stable.

For self-wrapping hooks, the final left-side path has 9 elements. The profile
anchor must stay at the physical end of that path. Do not move the profile anchor
to compensate for a broken or incomplete contour.

For variable-pitch compression springs, KOMPAS can build a visually correct
seven-edge `Contour3D` and still reject it as `IEvolution.Edges`. Keep the
contour as readback evidence, but if the first evolution `Update()` fails, retry
with the direct list of path parts in the same UI order. Record the selected
`edge_input_mode` so it is clear whether the body used `path_contour` or the
`direct_path_list` fallback.

### REBUILD-001: Materialize Newly Created CAD Features Before Capturing Result Edges

Some KOMPAS feature result objects are not stable immediately after API creation.
When later operations depend on selectable result edges, perform an explicit
materialization step before reading them.

For `self_wrapping_hooks`:

- create Sketch2;
- call `RebuildDocument()`;
- create native `FilletCurve` operations against the materialized sketch edges;
- call `RebuildDocument()` again before reading `FilletCurve.Owner.ModelObjects(7)`;
- then create the final 9-edge `Contour3D` and `IEvolution` body.

## Case Studies

### CASE-001: Bent Coil / Hook Construction Chain

Recorded:
- 2026-06-18.
- Covers tasks 14-20 and 9 live model iterations.

Problem:
- Build left/right bent coil hooks for `extension_spring` so that spirals leave
  the body at an angle, remain parametrized, and use fully constrained sketches.

Construction chain:
```text
1. Body end plane
   -> tangent sketch in global CS
   -> auxiliary axis used as baseline for angled plane

2. Angled plane (IPlane3DByAngle)
   -> center sketch on the angled plane
   -> project external 3D body point with AddProjectionOf
   -> axis line from projection to bent spiral center
   -> displaced 3D center point with operation-variable binding

3. Bent spiral (ICylindricSpiral3D)
   -> positioning: point via SetAssociationObject
   -> directing plane/object via SetDirectingObject
   -> CS from angled plane
   -> diameter/pitch/turns formulas through operation-variable binding
   -> initial angle: left = 90, right = selected by live verification

4. Wire profile
   -> path: RIGHT_BENT_COIL -> BODY -> LEFT_BENT_COIL
   -> IEvolution(sketch=profile, edges=path)
   -> hide auxiliary geometry
```

Rules used:
- `CS-002`: axis direction verification.
- `CS-003`: coordinate-system cascade.
- `CS-004`: unstable sketch origin on angled plane.
- `SKETCH-001`: fully constrained sketch.
- `DIR-001`: direction verification.
- `EDGE-001`: 2D sketch point cannot be used directly as 3D reference.
- `EDGE-002`: mixed sketch/3D edge composite curve.
- `OP-001`: sketch assignment fallback.
- `SPIRAL-001`: initial angle is not positioning orientation.
- `VAR-001`: operation-variable binding.

Result:
- Both bent spirals leave the body under angle.
- Sketches are constrained through projections instead of unstable origins.
- Offset and bend parameters are formula-driven.
- Reports: `docs/bent-coil-sketch-coordinate-system.md`,
  `docs/bent-coil-parametrize-report.md`.

### CASE-002: Compression Spring Fully-Constrained Sketch Drift

Problem:
- In `compression_spring/v7`, changing outer diameter moved the spiral relative
  to the axis.

Cause:
- Sketch dimensions existed, but geometric degrees of freedom were not fully
  constrained.

Rules:
- `SKETCH-001`
- `GAP-001`

Result:
- Sketches must be constrained and then rebuilt under changed parameters.

### CASE-003: Reference Sketch Constraint Inspection

Problem:
- `inspect_sketch_full` must be used to reproduce a known reference sketch, but
  projection constraints may not include the referenced external object.

Cause:
- The current inspection tool can capture almost all available sketch data,
  including projection constraints. The known remaining gap is identifying what
  object a projection constraint references.

Rules:
- `SKETCH-002`

Result:
- Use inspected geometry, dimensions, and constraints as the primary source.
- When projection constraint references are missing, ask the user to inspect the
  sketch in KOMPAS UI and name the referenced objects.

## Adding New Rules

Add a rule after a live failure or reusable fix. Prefer updating an existing
rule when the new knowledge changes its scope.

Template:
~~~markdown
### AREA-001: Short Rule Name

Applies when:
- ...

Symptom:
- ...

Cause:
- ...

Rule:
- ...

Implementation:
```python
...
```

Verification:
- ...

Known examples:
- `CASE-...`
~~~

ID prefixes:
- `ARC`: arcs and curve direction.
- `PARAM`: parameter and COM field semantics.
- `CS`: coordinate systems, planes, local axes.
- `SKETCH`: sketch constraints and inspection.
- `DIR`: direction flags and readback.
- `VERIFY`: temporary helper geometry and coordinate-based verification.
- `GAP`: modeling tolerances and clearance.
- `EDGE`: 2D/3D geometry bridge and edge extraction.
- `OP`: operation setup and assignment.
- `SPIRAL`: spiral-specific behavior.
- `VAR`: operation-variable binding.
- `CASE`: longer live case studies.

## Principles

1. Rule is not law. Always verify live when KOMPAS behavior is uncertain.
2. A rule belongs here only after live confirmation or repeated failure.
3. Every rule should name at least one known example, report, or file region when
   possible.
4. Preserve failed approaches when they prevent future repeated debugging.
5. This document must grow during the cycle: build -> observe failure -> record
   reusable lesson.
