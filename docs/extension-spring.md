# Extension spring: shared legacy interface

`module_id: extension_spring` connects the existing engineering hook generator to
`get_cad_module_contract`, `run_cad_module` and the file/stdin model CLI. No new
CAD algorithm, Studio block, general composition or in-place editing is added.
The existing scenario/catalog tools retain their behavior.

The typed input requires `wire_diameter`, `outer_diameter` and `turns`.
`hook_type` selects the fallback hook for both ends: `machine_hooks`,
`v_hooks`, `u_hooks`, `open_loop_hooks`, `center_loop_hooks` or
`extended_center_loop_hooks`, `self_wrapping_hooks`, or `bent_coil_left_spike`.
`left_hook_type` and `right_hook_type` independently override this fallback.
The historical `spike` name denotes final bent-ring geometry, not an unfinished
prototype. The existing composer owns side fragments; no new geometry algorithm
is introduced. Hook-family dimensions are shared if both ends use the same family.
The schema exposes the corresponding independent
hook dimensions; dimensions belonging to another hook are refused rather than
ignored. Deprecated construction-length/angle aliases remain outside this interface.
Bent-ring inputs include turns and angle. Self-wrapping height/width/fillet/tail
inputs map to existing driving SH1/SW1/SFR1/HT1 variables; defaults remain those
of the legacy generator, not an assertion of standardized dimensions.

`gap` is an axial pitch increment, not a certified minimum surface distance.
It and `minimum_gap` default to0.01 mm. Unlike the old legacy path, this interface
requires `gap >= minimum_gap > 0`; it does not silently increase a supplied gap.
The existing driving expressions remain `P1=WD1+G1`, `H1=P1*N1` and hook-specific
relations. The coil axis is global X at the global origin. `height` in the plan
means coil span only; actual body bounds include both hooks.

Creation follows `saved_unique_export_then_open`: a unique `.m3d` is written in
`KOMPAS_EXPORT_DIR` and returned opened. It verifies the valid native sweep,
one positive-volume solid, native coil diameter/pitch/height/hand, the wire
parameter and coil-spanning bounds. Volume and recipe/owned profile-sweep roots
are checked again after save/reopen. Hook contact loading, initial tension,
stiffness, strength and standards conformity are not certified.

`ESPR_RECIPE_*` retains bounded, checksummed version-1 creation inputs separately
from compression's `CSPR_RECIPE_*`. Ordinary inspect recognizes ownership and
the saved recipe; it does not rebuild or perform a fresh geometry/formula audit.
An incomplete recipe returns no recreate parameters rather than defaults. Old
models without this recipe cannot recover missing inputs through the shared
interface. Manual driving edits require separate verification and are not an
in-place editing capability of the common contract.

Live control cases cover all six conventional forms with right-hand six-turn
coils, both hands with machine hooks, and a custom left U-hook spring with
5.5 turns and changed hook dimensions. All retain valid bodies, exact recipes
and unchanged bounds through a further readonly reopen. This is verified shared
generator integration, not completion of a three-component Studio module.

```json
{
  "module_id": "extension_spring",
  "action": "plan",
  "parameters": {
    "wire_diameter": 2,
    "outer_diameter": 22,
    "turns": 6,
    "gap": 0.01,
    "hook_type": "machine_hooks",
    "turn_direction": "right"
  }
}
```

Use the same request with `action: create` and `confirm_write: true` to build a
new saved part. Failures can retain a partial file/document; inspect its exact
identity before another create. No automatic retry or rollback is promised.

Independent ends were finalized in the legacy generator: the current planner
supports64/64 combinations and archived reports contain representative live
mixed cases. The common adapter now passes fresh machine→V, self-wrapping→bent
and bent→self-wrapping creation/save/reopen. A duplicate final bent normalization
was corrected so it cannot discard an already-composed opposite hook. Symmetric
self-wrapping and bent-ring controls now pass, including changed self-wrapping
height/width/fillet/tail dimensions. An earlier self-wrapping sketch Update failed
and session readback temporarily disagreed with the visible documents. The
partial sketch was subsequently read as valid; separate diagnostic and common
creation/save/reopen checks passed without restarting KOMPAS. The original cause
is not established and no automatic retry workaround is added. Do not infer that
every parameter set or all64 pairs have been freshly CAD-verified.

See [architecture](../ARCHITECTURE.md), [CAD patterns](../CAD_PATTERNS.md) and
[legacy workflows](parametric-workflows.md).
