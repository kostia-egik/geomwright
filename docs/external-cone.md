# External cone common-interface contract

`external_conical_step` connects the existing standalone solid-frustum generator
to `get_cad_module_contract` and `run_cad_module`. Actions are host-only `preview`/
`plan`, create-only `create`, and saved-recipe `inspect`. Internal cones, threads,
and operations on an external body are deferred to construction-chain work.

## Input definition

Select `definition_mode` explicitly. Supply only the independent inputs of that
mode; extra or missing dimensions are rejected, not silently ignored.

| Mode | Independent inputs |
| --- | --- |
| `diameters_length` | `start_diameter`, `end_diameter`, `length` |
| `diameters_angle` | Both diameters and `cone_angle_degrees` |
| `diameters_conicity` | Both diameters and `conicity` |
| `one_diameter_length_angle` | Exactly one end diameter, length, half-angle, explicit `slope_direction` |
| `one_diameter_length_conicity` | Exactly one end diameter, length, conicity, explicit `slope_direction` |

Lengths/diameters are positive millimetres. Cone angle is the half-angle between
the generator and rotation axis, strictly between 0° and 90°. Conicity is positive
`abs(end_diameter - start_diameter) / length`, not the radius slope. One-diameter
modes require `inward` (end smaller) or `outward` (end larger); two-diameter modes
derive direction. Equal diameters/cylinders and zero-diameter tips are refused.

```json
{"module_id":"external_conical_step","action":"plan","parameters":{"definition_mode":"diameters_length","start_diameter":40,"end_diameter":20,"length":30}}
```

The body is a full rotation about global X with the profile in global XOY.
The start end is at X=0, the other end at X=resolved length. Arbitrary placement,
partial rotation, bores and finishing are not exposed by this typed adapter.
Existing legacy API options are unchanged.

## Creation and verification

Creation requires `confirm_write: true`. It saves a unique generated export and
opens that file. Readback checks the valid owned rotation, one positive-volume
solid, native conical surface, actual trimmed radii at both ends, axial/radial
bounds, a fully defined reopened profile, and volume against
`pi * length * (Dstart² + Dstart*Dend + Dend²) / 12` (mm³ converted to cm³).
Supporting-surface length is not used as the finished body's length. Verification
tolerances are not manufacturing tolerances or standard/strength certification.

The adapter reuses the shaft's saved-create lifecycle and the legacy cone builder.
It enables existing sketch-placement fixing without fixing entity geometry, and
replaces the legacy axial `circle_diameter` dimension on a straight axis with a
formula-bound `line_length`. This local adapter correction preserves old scenario
behavior while making resolved `CONE_L1` drive the actual length.

`CONE_D1`, `CONE_D2` and `CONE_L1` drive the resolved CAD dimensions. Input angle
and conicity modes calculate those values before construction; they are not
independently linked CAD angle/conicity variables. The original input mode and its
independent dimensions are retained in the versioned checksummed `ECON_RECIPE_*`.
Recipes are metadata, not driving parameters or verification stamps.

Inspect requires an exact opened document ID and recognizes the recipe/owned
roots. It restores inputs for a new build, not a fresh geometry audit or an
in-place edit. Missing or corrupt recipes cannot substitute defaults.

## Evidence and editing boundary

Solver-state caveat: earlier reports used the reversed API7 sketch-state decoder.
The shared decoder and strict gate are corrected to native 1=well-constrained,
2=under-constrained. Older full-definition claims need a fresh live review;
geometric and driving evidence below is separate. See
[SKETCH-011](../CAD_PATTERNS.md#sketch-011-decode-sketch-state-from-the-native-enum-not-an-assumed-numeric-scale).

All five input modes pass creation and save/reopen with the corrected axial
dimension, including the final one-diameter conicity check after restarting
KOMPAS. Changing resolved diameters40/20→44/22 and
length30→35 gave volume31.044171405223146 cm³, correct end radii22/11 and length35;
the separate saved/reopened copy retained its geometry; the historical solver-state
label is subject to the caveat above.

The common interface remains create-only, without a new Studio block or
certified in-place editing. The driving probe verifies the resolved diameter/
length relationships, not every possible manual change or independently linked
angle/conicity variables. Failures retain partial-file/document information and
no automatic retry/rollback is claimed.
# Construction chains

The standalone constructor remains create-only. The separate
[construction-chain interface](en/construction-chains.md) can create or append
an external cone at a free axial end in the same part. The chain reuses the
corrected legacy profile and dimension plans. Coaxial ±X and axial offsets are
supported; arbitrary orientation and in-place editing remain unsupported.
