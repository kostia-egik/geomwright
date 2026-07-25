# Bent Coil Sketch Coordinate System Investigation

## Summary

The `bent_coil_left_spike` extension spring workflow exposed unstable coordinate-system behavior when creating an angled construction plane through the KOMPAS API.

The visible symptom was that the second construction axis for the bent coil sometimes started from an endpoint of the first tangent axis instead of the intended spring body start point. Touching a related parameter in the KOMPAS UI caused the operation to rebuild and appear correct, which suggested a dependency/recompute or plane coordinate-system issue rather than a simple coordinate typo.

The current mitigation no longer trusts the angled plane sketch origin. Instead, the second sketch explicitly projects the 3D body start point into the sketch and constrains the center axis to that projected point.

## Affected Workflow

- Scenario: `extension_spring`
- Hook type: `bent_coil_left_spike`
- Bridge area: `create_bent_coil_auxiliary_construction`
- Files touched:
  - `bridge/kompas_bridge.py`
  - `src/kompas_mcp/assets/bridge/kompas_bridge.py`

## What Was Observed

1. The first tangent sketch was originally created on the body start plane without explicitly assigning the sketch coordinate system.
2. After assigning `tangent_sketch.CoordinateSystem = body_start_plane`, the first sketch became anchored and rotated with the spring end as expected.
3. That coordinate-system change also swapped the effective local axis direction. A line through local X became radial, not tangent.
4. The tangent axis was corrected to use local Y:
   - `x1 = 0`
   - `y1 = -radius`
   - `x2 = 0`
   - `y2 = radius`
5. Even after the first sketch was correct, the second angled-plane sketch still had unstable origin behavior.
6. Manual UI interaction with a related variable caused the operation to rebuild and appear correct, but direct API updates did not reproduce the same behavior reliably.

## Failed Or Insufficient Approaches

### Explicit Origin On The Second Sketch

Attempted to assign the second sketch origin to the body start point using properties such as:

- `OriginPoint`
- `BasePoint`
- `Point`

Result: these properties are not accepted by the KOMPAS `ISketch` COM object in this context.

### Recompute/Touch Calls

Attempted best-effort dependency refresh through methods such as:

- `Update`
- `Rebuild`
- `Recalculate`
- `Refresh`

Targets included the tangent sketch, tangent edge, body start plane, part object, angle plane, and same-value variable touch on `BA1`.

Result: these calls were useful for diagnostics, but did not reproduce the corrective UI behavior.

### PlaneByAngle Axis Variants

Investigated whether the wrong origin came from how the axis was assigned to `IPlane3DByAngle`.

Tested variants:

- `BaseLine` plus all known axis properties/methods
- no `BaseLine`
- `BaseLine` only
- `SetAxis` / `Axis` only
- `SetEdge` / `Edge` only
- auxiliary `Axis3DBy2Points` passed as `BaseLine`

Result:

- `IPlane3DByAngle` effectively requires `BaseLine`.
- Replacing a sketch edge with a 3D axis object did not fix the coordinate-system origin behavior.
- `Direction` only changes angle side.
- Reversing the source edge changes which endpoint the API treats as origin, but this is not a UI-level option and is not stable enough as a fix.

## Working Mitigation

The robust workaround is to stop depending on the origin of the angled sketch coordinate system.

In the second sketch:

1. Project the 3D spring body start point into the angled sketch:
   - `center_sketch.AddProjectionOf(body_start_point)`
2. Read the projected point coordinates:
   - `center_sketch.GetPointProjectionToXY(...)`
3. Build the center axis from that projected point.
4. Add constraints:
   - `vertical` on the center axis
   - `merge_points` between the axis start point and the projected point

The live report confirmed:

- projection was created
- projected XY was found
- vertical constraint was created
- coincident/merge-points constraint was created

This means the second axis is tied to the projected body start point instead of to the drifting sketch origin.

## Live Models Produced During Investigation

These models were generated for visual comparison:

- `sample/live_outputs/cs_origin_bug_h1_axis_fixed_bent_coil.m3d`
- `sample/live_outputs/cs_origin_bug_h1_tangent_axis_y_bent_coil.m3d`
- `sample/live_outputs/angle_plane_variant_flip0_dir0_v2.m3d`
- `sample/live_outputs/angle_plane_variant_flip0_dir1_v2.m3d`
- `sample/live_outputs/angle_plane_variant_flip1_dir0_v2.m3d`
- `sample/live_outputs/angle_plane_variant_flip1_dir1_v2.m3d`
- `sample/live_outputs/angle_plane_axis_2points.m3d`
- `sample/live_outputs/projected_body_start_center_axis_bent_coil_v2.m3d`
- `sample/live_outputs/projected_body_start_center_axis_constrained.m3d`

The final relevant model is:

- `sample/live_outputs/projected_body_start_center_axis_constrained.m3d`

## Final Live Diagnostic Snapshot

For `projected_body_start_center_axis_constrained.m3d`:

- `projection_created = true`
- `center_point_projection.ok = true`
- projected XY approximately: `[12.2872806643, 0]`
- center axis starts at projected point:
  - `x1 = 12.2872806643`
  - `y1 ~= 0`
  - `x2 = 12.2872806643`
  - `y2 = 15.0`
- constraints:
  - `vertical.created = true`
  - `merge_points.created = true`
  - `created_count = 2`

## Guidance For Future Work

Do not assume that a sketch created on an API-created angled plane has a UI-equivalent local coordinate system.

For geometry that must be anchored to a 3D point:

1. Project the 3D point into the sketch.
2. Use the projected object as the geometric anchor.
3. Add explicit sketch constraints to tie sketch geometry to that projection.

Avoid using edge direction reversal as a fix. It changes which endpoint `PlaneByAngle` uses as origin, but this is not exposed as a stable user-facing behavior and does not match the UI model.

If future KOMPAS API documentation reveals a supported way to create an angled plane with explicit local coordinate-system origin and axes, that should replace the projection workaround. Until then, projection plus constraints is the safer contract.

## Verification

Compile the modified normalization modules, compare the normalized scenario
against this coordinate contract, and verify the generated bent-coil sketch in a
live KOMPAS document. The saved artifact must be reopened before accepting frame,
axis, or point-order changes.
