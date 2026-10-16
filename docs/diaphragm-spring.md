# Diaphragm spring workflow

The diaphragm spring workflow is implemented and live-verified for flat,
single-bend, and S-bend tips, with narrow radial slots, circular or oval terminal
reliefs, through-all cuts, and circular patterns. It remains part of the
experimental `part_generation`/`spring_generation` MCP surface.

## Operation sequence

1. `diaphragm_spring`
2. select the external conical step face by radial span
3. create the tangent cut plane
4. `cut_reference_points_sketch`
5. `diaphragm_cut_profile_sketch`
6. `diaphragm_terminal_relief_sketch`
7. through-all slot and relief cuts
8. one circular pattern with both cuts as initial features

The detailed parameter and operation schema remains in
[parametric-workflows.md](parametric-workflows.md).

## Geometric invariants

- The tangent plane belongs to the main external conical step, selected by
  radial span rather than axial span.
- The slot starts from the actual final inner radius `DIA_IR1`, not the body
  radius `DIA_BODY_IR1`.
- Slot and relief cuts use through-all in both directions from the tangent plane.
- Circular and oval reliefs are separate closed sketches and cuts.
- The circular pattern owns both cuts and counts the original group in its total.
- Construction sketches, tangent planes, and projected points are hidden after
  successful execution.

## S-bend entry compensation

An S-bend moves the real central-hole lip away from the continuation of the main
cone tangent plane. A radial clearance alone therefore leaves a small uncut web.

The base sketch creates the derived variable `DIA_SLOT_ENTRY_SHIFT1`, and the
entry formula becomes:

```text
sqrt(
  (DIA_IR1 - DIA_SLOT_ENTRY_CLR1 - DIA_SLOT_ENTRY_SHIFT1)^2
  - (DIA_SLOT_START_W1 / 2)^2
)
```

The variable compensates tangent-plane normal runout from the cone geometry and
S-bend height. It is not created for flat or single-bend variants, so their slot
geometry is unchanged.

## Verification contract

For both circle and oval variants, verify after reopen:

- the slot intersects the central opening;
- one solid body remains;
- the circular pattern is valid and has the requested count;
- both slot and relief cuts are initial pattern features;
- primary variables precede derived variables;
- auxiliary geometry remains hidden.

Canonical local evidence uses the `final_module_v4` S-bend artifacts under
`sample/live_outputs/`. Those binaries are intentionally ignored by Git.

## Common module interface

`get_cad_module_contract("diaphragm_spring")` exposes the typed schema and a complete
S-bend example. `run_cad_module` supports `preview`, `plan`, create-only `create`,
and saved-recipe `inspect`. This integration reuses the finalized workflow above;
it does not introduce another geometry algorithm or a new Studio editor.

All dimensions are in millimetres. The rotation axis is global X and the base
profile is in global XOY. Supply `tip_variant`, outer diameter, normal thickness,
cone height, and explicit slot/relief dimensions and count. Variant-specific inputs
are validated, not silently ignored:

- `no_bend`: final inner diameter; bend and free-height inputs are inapplicable;
- `single_bend`: body inner diameter, bend inner radius, tip angle, and exactly one
  of `free_height` or `tip_length`; final inner diameter is calculated;
- `s_bend`: body/final/intermediate inner diameters, intermediate/free heights,
  and both bend inner radii; tip angle and tip length are inapplicable.

Circle relief has no straight-length input; oval relief requires it. Slot count
includes the original pair of cuts. The legacy height meanings remain owned by
the family generator, not by the disc-spring alias contract.

Creation requires `confirm_write: true`, saves a unique generated export, and opens
that generated document. It checks valid owned operations, one positive-volume
solid, outer diameter and axial bounds, both pattern source cuts, count/angle,
additional material removal against the source-pair volume times `count - 1`,
hidden auxiliary sketches, and unchanged native volume after save/reopen.
Pattern-volume comparison uses a 1% geometric readback tolerance (numerical floor
0.000001 cm³), capped at one quarter of a source-pair volume so one missing group
cannot be accepted at high counts. This is not a manufacturing tolerance or a
load/strength/standard-compliance claim.

`DIAPR_RECIPE_*` is versioned, checksummed creation metadata, not driving variables
or a geometry-verification stamp. Inspect requires an exact opened document ID.
Missing, corrupt or structurally invalid recipes cannot substitute default inputs
for recreation. Initial cut ownership is read through `ICircularPattern.InitialObjects`:
the complete extrusion collection also contains repeated copies with the same names.

Creation returns per-sketch constraint states in `data.diagnostics.native_workflow`.
Intermediate reports and final reopened states may differ: the S-bend base reads
as fully defined after reopen, while auxiliary/cut-sketch readback can report
degrees of freedom. Creation-time cut preflight is separate from these saved-state
diagnostics. Full definition of every saved sketch and in-place driving edits are
not certified by this integration. Changed inputs create a new part; recognition
alone is not a fresh geometry audit.

Current common-interface live checks cover no-bend in both directions,
single-bend, S-bend, circle/oval relief and an additional 9-slot size. Failures
retain partial-file/document information and a bounded native checkpoint/root
cause; no automatic retry or rollback is claimed.
