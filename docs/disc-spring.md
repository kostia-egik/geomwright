# Disc spring common-interface contract

`disc_spring` connects the existing legacy normal-thickness conical-ring generator
to `get_cad_module_contract` and `run_cad_module`. It supports `preview`, `plan`,
create-only `create`, and saved-recipe `inspect`; it does not add a Studio editor.

## Inputs and geometry

Supply positive `outer_diameter`, `inner_diameter`, and `thickness`, in millimetres,
with inner diameter smaller than outer diameter. Thickness is measured normal to
the sloping profile. Supply exactly one positive height input:

- `cone_height`: axial rise of the profile;
- `free_height`: legacy alias, converted as `cone_height = free_height - thickness`.

The legacy alias is not the finished body's exact axial span. `cone_direction`
is `up` or `down` (default `up`). The existing profile rotates about global X;
no stack, hub, load curve, strength calculation, or standard certification is added.

Example common request:

```json
{"module_id":"disc_spring","action":"plan","parameters":{"outer_diameter":50,"inner_diameter":25,"thickness":2,"cone_height":3,"cone_direction":"up"}}
```

Creation requires `action: "create"` and `confirm_write: true`. It saves a unique
export and opens that generated file. Verification checks native feature validity,
one solid, positive volume against the analytical rotated profile, inner/outer
circular-edge diameters, axial bounds, and unchanged volume after save/reopen.
Geometric verification tolerances are not manufacturing tolerances.

## Persistence and editing boundary

`DSPR_RECIPE_*` stores a versioned checksummed creation recipe and owned sketch/
rotation names. `inspect` requires the exact opened document ID and returns the
recoverable input parameters. Recognition is not a fresh geometry audit or proof
that manually edited geometry still matches the recipe.

Legacy radius/height driving associations are not reliable for in-place editing:
cone-height variable edits alone did not rebuild the profile, and coupled size
edits did not preserve nominal radii in live checks. Recreate a new part from the
input parameters through this interface. Repairing these legacy driving links is
a separate task; the saved recipe must not be presented as CAD-driving certification.

Live create/save/reopen checks cover both directions, an additional size, and the
legacy height alias. For diameter 50/25, normal thickness 2 and cone height 3,
the analytical/native volume is approximately 2.917999 cm³ and the axial span
is approximately 4.940432 mm, not the legacy `free_height` value 5 mm.
