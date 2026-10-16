# Stepped shaft common-interface contract

`stepped_shaft` connects the existing legacy rotational generator to
`get_cad_module_contract` and `run_cad_module`. It supports host-only `preview`/
`plan`, create-only `create`, and saved-recipe `inspect`. No new Studio block or
operation on an external body is added.

## Inputs and body

Supply `steps`, an ordered list of positive `length` and `diameter` values in mm.
There are 1–100 steps. Adjacent equal diameters are rejected by legacy validation:
combine their lengths into one cylinder. Nonadjacent repeated diameters are valid.
The 100-step limit bounds metadata and geometry readback; it is not a certified
engineering limit or a live-verified maximum-size claim.

```json
{"module_id":"stepped_shaft","action":"plan","parameters":{"steps":[{"length":20,"diameter":30},{"length":35,"diameter":40},{"length":15,"diameter":25}]}}
```

The body starts at global origin and occupies X from zero to the sum of lengths.
It is a full 360° rotation about global X, with its profile in global XOY. This
typed adapter excludes arbitrary placement and partial-angle rotation, while
preserving those separate legacy API capabilities. Holes, chamfers, fillets,
threads and other external-body operations remain outside this constructor.

## Creation and persistence

Creation requires `confirm_write: true`, saves a unique generated export, and
opens that file. It verifies a valid rotational feature, one solid, actual bounds,
every cylindrical face radius and trimmed axial interval, and positive native
volume against `sum(pi * diameter² * length / 4)` (mm³ converted to cm³).
Native dimensions are read from trimmed boundaries, not supporting-surface lengths.
The reopened sketch must be fully defined (API7 native code 1); the adapter enables the existing
`fix_sketch_placement` and `require_fully_defined` modes without fixing entity
geometry. Volume and the creation recipe must survive save/reopen.

`SHFT_RECIPE_*` stores a versioned checksummed creation recipe. `SHAFT_Dn` and
`SHAFT_Ln` are existing generator driving variables, not recipe metadata. Inspect
requires the exact opened document ID, recognizes the recipe and owned sketch/
rotation roots, and restores inputs for a new build. It is not a fresh geometry
audit; old files without a recipe cannot substitute default inputs.

Historical solver-state labels used the reversed 1/2 decoder. This is now fixed,
but old creation/edit full-definition claims require new live review; see
[SKETCH-011](../CAD_PATTERNS.md#sketch-011-decode-sketch-state-from-the-native-enum-not-an-assumed-numeric-scale).

Live geometry checks cover one step, three steps, and four steps with repeated diameters.
A separate diameter30→34 / length20→24 driving probe changes native radii, axial
intervals and volume as expected and survives saving a separate copy. The sketch
state after that manual change was historically labelled under-constrained by
the old decoder; that label cannot certify or disprove definition. In-place edits
and preservation of full definition after manual edits are not certified by this
create-only interface; recreate from inputs. Original creation files are preserved.

Failed creation reports a partial document/file and stopping stage, without
automatic retry or claimed rollback. Geometry tolerances are verification bounds,
not manufacturing tolerances. No strength or standard conformity is certified.
# Construction chains

The standalone constructor remains create-only. The separate
[construction-chain interface](en/construction-chains.md) can create or append
a stepped shaft in one coaxial part with independent instance variables and
native macro grouping. It supports ±X and axial offsets; placement changes
require recreation. This does not add in-place editing to the standalone tool.
