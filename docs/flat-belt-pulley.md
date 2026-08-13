# Flat-belt pulley

Status: complete and live-verified at Layers 2/4, including fully constrained
cylindrical and circular-crown sketches.

## Scope

`flat_belt` creates one owned functional rim as a rotational body. It does not
create a belt, route, tensioner, hub, bore, keyway, or shaft feature.

Supported profiles:

- `cylindrical` — constant outside diameter across the face;
- `crowned` — a symmetric circular-arc outside surface with an explicitly
  supplied radial crown height.

The crowned form is parameterized geometry, not an implicit standards table.
Geomwright does not claim a standard crown default until a redistributable
primary source and applicability rules are available.

## Public parameters

```text
outer_diameter   maximum diameter; at the face center for crowned rims
face_width       axial width
crown_height     center rise over the edge radius; zero selects cylindrical,
                 a positive value selects crowned
```

For a crowned face of width `B` and rise `h`, the circular crown radius is:

```text
R = (B² / 4 + h²) / (2h)
```

The first managed member is a solid functional blank closed to the rotation
axis; it intentionally creates no bore. The edge radius is
`outer_diameter / 2 - crown_height`. Rim thickness, hub, bore, keyway, and shaft
interfaces belong to separate generic modeling modules and are not parameters of
the transmission member.

## Managed CAD contract

The member is one closed axial/radial sketch extending to the rotation axis and
revolved 360 degrees about global X. Closing a new boss to the axis follows the
same stable owned-blank topology used by the existing pulley workflow and avoids
an ambiguous annular new-body boss.
The managed variables are:

```text
PULLEY_D1    maximum outside diameter
PULLEY_L1    face width
FP_OR        maximum radius, expression PULLEY_D1/2
FP_CROWN     crown height
FP_PROFILE   1 cylindrical, 2 crowned
FP_ARC_R     circular crown radius, crowned profile only
FP_CENTER_Y  crown arc center offset, crowned profile only
```

The cylindrical sketch has driving dimensions linked to `PULLEY_L1` and
`FP_OR`. The crowned sketch additionally drives its circular arc through
`FP_ARC_R = (PULLEY_L1²/4 + FP_CROWN²)/(2·FP_CROWN)` and
`FP_CENTER_Y = FP_ARC_R - FP_OR`. Geometry, constraints, and dimensions are
created in one sketch edit session; creation fails unless KOMPAS reports the
finished sketch as fully defined.

The Studio ownership inspector recognizes the `FP_*` fingerprint together with
the canonical flat-pulley sketch and rotation names. Editing performs an owned
topology replacement with the existing rollback contract, because the circular
arc and cylindrical line are different sketch topologies.

## Verification

Host-side verification covers input invariants, analytical dimensions, crown
radius, preview contour, CAD-plan entities, managed ownership variables, and
Studio HTTP registration. The bridge requires complete constraint/dimension
application, a fully defined sketch, valid rotation, successful document
rebuild, one recognized owned feature/sketch pair, and exact managed-variable
readback. The flat-pulley write path does not call the legacy API5 active-body
volume probe: live KOMPAS evidence showed that call can block indefinitely after
a valid new rotation even though workspace readback recognizes the finished body.

Live acceptance confirmed both profiles as fully defined, crowned create/update,
and save/reopen readback. The module is accepted as complete; topology updates
reuse the shared managed-pulley rollback contract.
Studio CAD jobs expose a Stop action. It cancels the isolated bridge subprocess
without closing KOMPAS or deleting a partially created unsaved document; a
180-second hard timeout prevents one stalled COM call from holding the global
CAD queue indefinitely.
