# Conical Spring

`conical_spring` is an alias of the custom `conical_compression_spring` preview
path. It reuses the compression-spring segment contract, then maps each segment
onto the conical diameter range.

## Current Contract

Required fields:

- `wire_diameter`
- `small_diameter`
- `large_diameter`
- `height`
- `turns`

Optional fields:

- `pitch_mode`: `constant_pitch` or `constant_angle`
- `large_at_start`
- `end_turns_per_side`
- `ground_turns_per_side`
- `transition_fillet_radius`
- `transition_fillet_radius_factor`

If end/ground turns are not supplied, conical springs default to
`end_turns_per_side=0.75` and `ground_turns_per_side=0.75`, producing start-end,
working, and finish-end segments. Explicit `0` values keep the earlier single
working-segment research shape.

## Profile And End Treatment

The wire profile follows `PROFILE-001`: it is anchored to the final contour
endpoint and the sketch circle is local to that anchor plane with center
`[0, 0]`. The profile sketch no longer offsets by the conical spring radius.

Transitions between start-end, working, and finish-end conical segments use
native 3D curve fillets. The working-side result edge from the first transition
is chained into the second transition, so the working conical segment is trimmed
by native result edges at both ends. The default transition radius is chosen from
the limiting local cone radius at the segment joints, not from wire diameter:

```text
transition_fillet_radius = min(joint_radii) * transition_fillet_radius_factor
```

`transition_fillet_radius_factor` defaults to `0.875`, giving the smoothest
large transition that stays slightly below the smaller joint radius. Use explicit
`transition_fillet_radius` to override this value for a specific model.

Ground trimming is driven by the inherited compression `ground_trim_plan`. Live
bridge readback for the default three-segment conical model reports executed
`section_by_surface` operations for both `start_ground_trim` and
`finish_ground_trim`.

## Live Evidence

Current review models:

- `conical_bigradius_constant_pitch.m3d`: contour `5/5/5`, local profile center
  `[0, 0]`, two native `curve_fillet` transitions at `TFR1=7.98984375`, two
  ground surface cuts.
- `conical_bigradius_constant_angle.m3d`: contour `5/5/5`, local profile center
  `[0, 0]`, two native `curve_fillet` transitions at `TFR1=7.98984375`, two
  ground surface cuts.
