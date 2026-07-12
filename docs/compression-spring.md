# Compression Spring

`compression_spring` builds a segmented cylindrical spring path, then sweeps one
wire profile along the composed path. `compression_spring_variable_pitch` is a
public scenario alias for the same builder with `pitch_mode = "two_zone"`; it is
a compression-spring modification, not a separate module.

## Current Contract

Required diameter input is one of:

- `mean_diameter`
- `outer_diameter`
- `inner_diameter`

Required base inputs:

- `wire_diameter`
- `free_length`
- `turns` or `working_turns`

Common optional fields:

- `end_turns_per_side`
- `ground_turns_per_side`
- `turn_direction`: `right` or `left`
- `transition_fillet_radius`
- `transition_connector_builder`: `auto`, `curve_fillet`, or `trimmed_connect_curve`

With start/end segments enabled, the normal cylindrical preview produces
`start_end`, `working`, and `finish_end`. The final path has five elements when
both transitions are present.

Variable-pitch compression requires explicit working zones:

- `working_turns_1`, `pitch_1`
- `working_turns_2`, `pitch_2`

For `pitch_mode = "two_zone"`, `free_length` must match the two working spans
plus end spans. The preview produces `start_end`, `working_1`, `working_2`, and
`finish_end`; the final path has seven elements when all transitions are present.

## Profile And Transitions

The wire profile follows `PROFILE-001`: it is anchored to
`full_path_sequence[-1]` at `vertex = "end"`, with `profile_path_offset = [0, 0,
0]` and `profile_sketch_center = [0, 0]`. The profile sketch dimensions only
drive the wire diameter.

Cylindrical transitions now use native 3D `curve_fillet` in `auto` mode for both
right-hand and left-hand turns. The legacy trimmed-connect path remains available
only through `transition_connector_builder = "trimmed_connect_curve"`.

The default native transition radius is:

```text
transition_fillet_radius = min(0.4 * mean_radius, 1.5 * wire_diameter)
```

The variable plan binds this default to the mean-diameter and wire-diameter
expressions, for example `TFR1 = min(0.2 * (D1 - WD1), 1.5 * WD1)` when `D1` is
the outside diameter variable.

Native cylindrical transition cut points are created on the actual COM curve via
`Point3DParamCurve`, then passed to `SetCurve*CutPoint`. Do not rely on analytic
preview coordinates for left-hand spirals; they can describe the intended phase
but still pick the wrong selectable side in KOMPAS.

Native fillets are staged in a UI-like order: create and update the fillet with
curves/cut points, optionally update at a smaller seed radius, then update at the
target radius and bind the operation variable. The result edges from
`FilletCurve.Owner.ModelObjects(7)` are used in the final path.
In auto mode the seed radius is based on local pitch spacing, currently
`0.02 * min(adjacent local pitch)`, capped by the target radius. This keeps the
first selectable fillet well below the spacing to neighboring turns.

For variable-pitch paths, KOMPAS can build a visually correct seven-edge
`Contour3D` but reject that contour as `IEvolution.Edges`. The bridge therefore
tries the contour first and falls back to the direct list of path parts when the
initial evolution update fails.

## Live Evidence

Current review models:

- `cyl_23_left_native_full_com_cutpoints_default_r6.m3d`: left-hand native
  cylindrical compression, two native fillets, contour `5/5`, sweep ok.
- `cyl_variable_pitch_right_two_zone_direct_path_body.m3d`: right-hand
  variable-pitch compression, three native fillets, contour `7/7`, sweep ok via
  `direct_path_list` fallback.
- `cyl_variable_pitch_left_two_zone_direct_path_body.m3d`: left-hand
  variable-pitch compression, three native fillets, contour `7/7`, sweep ok via
  `direct_path_list` fallback.

Obsolete diagnostic files in the same review folder, especially `cyl_10` through
`cyl_20`, captured failed experiments and should not be used as current evidence.
