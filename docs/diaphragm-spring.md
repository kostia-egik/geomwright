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
