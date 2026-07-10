# Extension Hook Type Inventory

This inventory tracks the extension-spring hook styles that must be stabilized
before independent left/right hook selection.

## Runtime Hook Types

| Hook type | Current runtime status | Connector strategy | Notes |
| --- | --- | --- | --- |
| `machine_hooks` | Builds body | native `curve_fillet` | `5/5/5` contour readback |
| `v_hooks` | Builds body | native `curve_fillet` | `9/9/9` contour readback |
| `u_hooks` | Builds body | native `curve_fillet` | `9/9/9` contour readback |
| `center_loop_hooks` | Builds body | native `curve_fillet` | `7/7/7` contour readback |
| `extended_center_loop_hooks` | Builds body | native `curve_fillet` | `13/13/13` contour readback |
| `open_loop_hooks` | Builds body | native `curve_fillet` | left arc mapping fixed; profile anchor follows final sequence end; `7/7/7` contour readback |
| `self_wrapping_hooks` | Builds body | native fillet result edges | verified earlier for integer/fractional turns |
| `bent_coil_left_spike` | Builds body | no connector plan; left bent coil + body + right bent coil | likely the "bent rings" hook style; `BA1=90`; left/right initial angles `90/270` |

## Open Loop Fixes Applied

`open_loop_hooks` previously mapped `LEFT_OPEN_ARC_PATH` to the wrong tuple edge.
The left sketch mapping now uses the arc edge. The wire profile anchor has since
been unified for all hook types and is no longer chosen from the left hook.
Open-loop hook-to-body connectors now use native `curve_fillet` instead of the
old trim/connect fallback.
Preview/readback contract:

```text
profile_anchor_plane.path_name=<full_path_sequence[-1]>
profile_anchor_plane.vertex=end
source_path_count=7
expected_edges_count=7
edges_count=7
```

The sketch also now includes `hook_end_radius_ref`, a construction line from arc
center to free arc end, constrained into the existing center/free-end helper
geometry.

## Bent Coil Notes

`bent_coil_left_spike` is the currently implemented bent-ring style. Current
preview/runtime shape:

```text
segment_plan = [body, bent_coil_left, bent_coil_right]
full_path_sequence = [BENT_COIL_LEFT_SPIKE_PATH, BODY_PATH, RIGHT_BENT_COIL_PATH]
profile_anchor_plane = RIGHT_BENT_COIL_PATH/end
```

All extension hook types now use the same profile-anchor rule:
`profile_anchor_plane.path_name == full_path_sequence[-1]` and
`profile_anchor_plane.vertex == end`.

Live readback covered all current hook families:

```text
machine_hooks: 5/5/5
v_hooks: 9/9/9
u_hooks: 9/9/9
center_loop_hooks: 7/7/7
extended_center_loop_hooks: 13/13/13
open_loop_hooks: 7/7/7
self_wrapping_hooks: 17/17/17
bent_coil_left_spike: 3/3/3
```

`OrientByObject` positioning was re-tested and rejected: the orientation object
is accepted, but the physical spiral position is wrong. Current bent-coil state:

- `bent_coil_left` and `bent_coil_right` metadata has been corrected to
  `construction_only=False` because both are final contour segments;
- default `bent_coil_angle_degrees` is now `90.0`, so generated bent-ring hooks
  are visibly bent when the user does not provide an angle;
- right bent-coil initial angle defaults to `270.0` to compensate the `90`
  degree position orientation readout and align the spiral start phase;
- bent-coil center-axis sketches now get verticality plus an anchor point and
  fixed length. When projection merge fails, the bridge applies a fixed-point
  fallback to the axis start point;
- bent-coil sketch creation has been corrected to follow `CS-005` for center
  sketches, but auxiliary visibility/readback rules still need a focused cleanup.

## Mixed Hook Composition Status

Independent left/right hook composition is enabled for the legacy native-fillet
families:

```text
machine_hooks
v_hooks
u_hooks
center_loop_hooks
extended_center_loop_hooks
open_loop_hooks
```

The composer builds a mixed preview from donor side fragments:

- left side segments and the left hook-to-body native fillet come from
  `left_hook_type`;
- right side segments and the body-to-right hook native fillet come from
  `right_hook_type`;
- `full_path_sequence` is stitched from the left donor prefix and right donor
  suffix;
- `profile_anchor_plane` remains `full_path_sequence[-1]/end`.

Preview matrix coverage: all `6 x 6` legacy combinations satisfy the mixed
contract and clear `requires_side_specific_hook_builders`.

`bent_coil_left_spike` is also enabled on the left side when the right side is a
legacy native-fillet family. This side has no hook-to-body connector; the right
legacy connector is stitched to the body source after the left bent-coil segment.

`self_wrapping_hooks` are enabled on either side when the opposite side is a
legacy native-fillet family. The bridge now builds only the requested
self-wrapping side and preserves the opposite legacy hook plane/segment for the
connector.

Live readback samples:

```text
machine_hooks -> v_hooks: 7/7/7
open_loop_hooks -> u_hooks: 8/8/8
center_loop_hooks -> extended_center_loop_hooks: 10/10/10
v_hooks -> open_loop_hooks: 8/8/8
bent_coil_left_spike -> v_hooks: 6/6/6
machine_hooks -> bent_coil_left_spike: 4/4/4
self_wrapping_hooks -> v_hooks: 13/13/13
v_hooks -> self_wrapping_hooks: 13/13/13
self_wrapping_hooks -> bent_coil_left_spike: 10/10/10
bent_coil_left_spike -> self_wrapping_hooks: 10/10/10
```

Right-side `bent_coil_left_spike` after a legacy left hook is enabled. Its spiral
height `BuildingDirection` is explicitly preserved as `True` in mixed
composition; turn direction and initial angle stay unchanged. This path does not
add an extra body-to-bent native connector: the final sequence is the left
connector result edge followed by the right bent-coil spiral.
The bridge skips the unused left bent-coil auxiliary construction in this
right-only mixed case, so the operation tree should not contain the left ring
start/center construction chain.

The full preview matrix currently supports `64/64` left/right hook combinations.
`bent_coil_left_spike -> self_wrapping_hooks` keeps the bent-coil-to-body joint
unfilleted. The right self-wrapping transition fillet uses the raw body path as
its source and receives the logical body end point from `segment_plan` as the
native curve-fillet cut point.
