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
- `free_angle_degrees`
- `start_phase_degrees`

`tangent_legs` currently requires `start_phase_degrees=0`. `radial_legs` and
`axial_transition_legs` support nonzero start phase.

Normalized previews preserve `body_turns`, `free_angle_degrees`, `gap`,
`start_phase_degrees`, `turn_direction`, and `end_type`. The profile anchor is
the final entry in `full_path_sequence`, following `PROFILE-001`.

## Execution

The scenario is included in `SUPPORTED_PART_SCENARIOS`, public
`preview_part_scenario`, direct adapter creation, and `preview_workflow`.
The bridge builds the coil and legs through the generic spring path/contour and
evolution pipeline.

## Live Evidence

Current live CAD checks:

- tangent legs, two representative size profiles: `3/3/3` contours;
- radial legs at zero and `30` degree start phase: `5/5/5` contours;
- axial-transition legs at zero and `30` degree start phase: `5/5/5` contours;
- profile anchors resolve to the last expected path in every case;
- nonzero phase for `tangent_legs` is rejected explicitly.

Local native command-105 audit notes, where maintained, are separate from this
custom parametric scenario and do not describe or limit its contract.
