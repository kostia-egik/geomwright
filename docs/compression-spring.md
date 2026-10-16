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

The experimental shared interface registers `module_id: compression_spring` with
typed `variant: cylindrical|two_zone|conical`. Existing scenario/catalog APIs are
preserved; `get_cad_module_contract` describes the supported engineering inputs.
This adapter retains saved creation and post-save anchor bindings: it writes a
unique export, opens it, and returns `saved=true`, `closed=false`. Global X is the
spring axis. Creation verifies one positive-volume solid, radial envelope, owned
roots, checksum recipe readback and volume preservation after save/reopen.
Recipe inspection does not audit geometry or driving formulas and has no stored
verification stamp. No new Studio spring block is implemented by this integration.

Current-runtime control cases pass for an open cylinder, grounded right/left
two-zone cylinders (left start phase30), and cones with constant pitch/constant
angle. Native point probes identified a quarter-turn gap in the old left-hand
plan: its first segment used angle0 while later segments used90. First and later
angle formulas now use the same left-hand phase convention; both fillets produce
three result edges. The original segmented cylinder (mean diameter30, wire4,
centreline height48, working turns5, end turns1, ground turns0.5) still has native
`ObjectError=31`: the sweep self-intersects at zero-clearance end turns. The same
dimensions also fail right-handed. Shrinking only the diagnostic wire profile by
0.02 mm, keeping the centreline helices unchanged, produces a valid sweep before
ground cuts and through save/finalization/reopen. This is diagnostic evidence, not
a changed engineering dimension or a production fallback. The shared creation
interface checks native sweep validity before saving and reports
`CAD_SELF_INTERSECTION` instead of blaming recipe/reopen.

The shared module now exposes `end_pitch_gap` (default0.01 mm): end pitch equals
wire diameter plus this axial increment. `EG1` is driving; `EP1=WD1+EG1` drives
end spiral steps, turn spans, working-span derivation and grinding offsets. The
nominal wire remains unchanged. Explicit zero is not clamped; negative/nonfinite
inputs are refused. Legacy requests without the field retain their old zero gap,
as do earlier saved version-1 recipes during recognition. New recipes retain the
exact requested increment. This parameter is not a certified minimum distance
between helical surfaces, and it does not guarantee every arbitrary spring input.

Both hands of the original cylinder now pass native sweep validity, positive
single-solid volume and save/reopen with gap0.01. Two-zone left phase30 and both
cone pitch modes pass as well. A live change of EG1 from0.01 to0.02 changes native
end steps4.01→4.02 with WD1=4, retaining valid body and positive volume through
save/reopen. Asymmetric end/ground counts were checked with physical length50 mm.
`height` and legacy `free_length` mean centreline span; `standard_length` means
physical end-to-end length in the legacy ground/extreme-plane model. Only one
length input is accepted. Optional `pitch` is a consistency check against the
length/turn-derived working pitch, not an ignored override. No new Studio block
is implemented; the shared-generator integration is not a complete Studio module.

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
