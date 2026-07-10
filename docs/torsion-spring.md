# Torsion Spring

`torsion_spring` is a public parametric scenario backed by the existing generic
spring bridge path. It uses one coil body plus two leg segments and does not use
the native KOMPAS torsion-spring command workflow described in the archived
native audit documents.

## Public Contract

Required fields:

- `wire_diameter`
- `mean_diameter` or `outer_diameter`
- `turns`
- `leg_length`, or separate `left_leg_length` and `right_leg_length`

Optional driving fields:

- `end_type`: `tangent_legs`, `radial_legs`, or `axial_transition_legs`
- `turn_direction`: `right` or `left`
- `gap`
- `minimum_gap` or `min_gap`
- `free_angle_degrees`
- `start_phase_degrees`
- `transition_fillet_radius` for `radial_legs` and `axial_transition_legs`

`tangent_legs` currently requires `start_phase_degrees=0`. `radial_legs` and
`axial_transition_legs` support nonzero start phase.

`gap` is clamped to at least `minimum_gap` / `min_gap`, defaulting to `0.01` mm,
so the body pitch remains `wire_diameter + G1` without giving KOMPAS touching
or self-intersecting coil turns.

`radial_legs` and `axial_transition_legs` use native 3D curve fillets for both
leg-to-body transitions. The body-side edge from the first fillet is chained
into the second fillet, so the spring body is trimmed at both ends by native
result edges rather than by legacy trimmed/connect curves. The fillet radius is
driven by `TFR1` / `transition_fillet_radius`.

Normalized previews preserve `body_turns`, `free_angle_degrees`, `gap`,
`start_phase_degrees`, `turn_direction`, and `end_type`. The profile anchor is
the final entry in `full_path_sequence`, following `PROFILE-001`.
The wire profile sketch is local to that anchor plane: its circle center is
`[0, 0]`, and the sketch no longer contains a coil-radius offset.

## Execution

The scenario is included in `SUPPORTED_PART_SCENARIOS`, public
`preview_part_scenario`, direct adapter creation, and `preview_workflow`.
The bridge builds the coil and legs through the generic spring path/contour and
evolution pipeline.

## Live Evidence

Current live CAD checks:

- tangent legs, two representative size profiles: `3/3/3` contours;
- radial legs at zero and `30` degree start phase: `5/5/5` contours with two
  native `curve_fillet` transitions;
- axial-transition legs at zero and `30` degree start phase: `5/5/5` contours
  with two native `curve_fillet` transitions;
- default `gap=0` inputs normalize to `G1=0.01` and `P1=WD1+G1`;
- profile anchors resolve to the last expected path in every case;
- profile sketches use local `[0, 0]` centers on the anchor plane in every case;
- nonzero phase for `tangent_legs` is rejected explicitly.

Local native command-105 audit notes, where maintained, are separate from this
custom parametric scenario and do not describe or limit its contract.
