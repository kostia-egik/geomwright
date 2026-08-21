# Timing-belt pulley

Status: managed Studio create/inspect/update accepted for trapezoidal T/AT and
curvilinear HTD.

## Current boundary

The module describes the toothed functional rim only. Hub, bore, keyway,
flanges, belt route, and tensioning remain separate modules or later composition
steps.

Studio exposes separate trapezoidal and curvilinear modules because their
one-groove CAD sketches require different entity and constraint mechanics.
Both render a cropped end-view fragment containing exactly three grooves and two
complete teeth. The profile, two rising side breaks, and the lower wavy break
form one bounded hypothetical cut-out. A short tooth-tip reference arc replaces
the misleading full-wheel and pitch-circle outlines. Dimensions are distributed
between grooves: radial leaders stop near the wavy break and show outside and
root diameters, the center groove carries mouth width `s` and radial depth `h`,
and separate leaders show tooth-tip and groove-root radii. Tooth pitch remains a
profile/summary parameter rather than a misleading straight chord dimension.

The trapezoidal module includes `T2.5`, `T5`, `T10`, and `AT5`; the curvilinear
module includes `HTD 3M`, `HTD 5M`, and `HTD 8M`. Each module has a shape-locked
`CUSTOM` profile accepting pitch, groove depth/width, pitch-line offset, and
optional explicit tip/root radii (conservative preview radii are derived when
they are omitted). The
unified MCP preview tool retains an explicit custom shape for API compatibility. These
constants support geometry exploration and are not presented as a licensed
manufacturing-standard claim. Source provenance is returned with the preview.

`GT`/PowerGrip and automotive timing profiles are not silently approximated as
universal catalog entries. Their geometry depends on supplier/profile-generation
data that is often proprietary or vehicle-specific. They can be added through
the custom contract or as named presets after a primary supplier table or
reference model is supplied. Catalog tip/root radii are circular fits recovered
from the cited open profile coordinates; they remain preview references rather
than licensed-standard inspection values.

## Staged CAD workflow

The target Layer 4 workflow is not a rotation cut:

```text
cylindrical functional blank
  -> end-face sketch of one groove
  -> through-all cut extrusion
  -> 360° circular pattern around the pulley axis
  -> rebuild, ownership, count/angle, volume, save/reopen readback
```

The accepted T/AT Layer 3 mechanics are implemented internally as:

- a numeric circle and boss extrusion for the cylindrical blank;
- one closed trapezoidal cut contour with six primary segments and four true-radius
  arcs: two outside-circle-tangent transitions that round the retained tooth
  faces and two internal groove-root fillets, with no dimensions or constraints;
- a through-all cut with fully-defined-sketch enforcement deliberately disabled;
- a 360-degree circular pattern.

The cut contour closes outside the blank so the removed region reaches the
cylindrical boundary without depending on a coincident outer-circle edge. Its
tooth-face transitions and root fillets use the same accepted numeric seed
geometry in both modes. The mouth arcs are
deliberately not ordinary internal corner fillets of the cutter contour, because
those would round the removed region on the opposite side of the final tooth.

Parameterized mode adds 15 semantic `TB_*` part variables, eight auxiliary datum
entities, 45 geometric constraints, and eight driving dimensions. One
outside-material closure point is located by the leg length `TB_CO` and an
aligned center-distance dimension `TB_OR + TB_CO`; the opposite leg inherits
its length and the closing bridge is horizontal. This local closure contract removes their
remaining freedom without re-merging either primary-contour endpoint. `TB_B` binds
the blank extrusion width; `TB_Z` and `TB_STEP` bind the circular-pattern count
and angular step. Numeric mode remains available as the unparameterized baseline.

The generic operations now support both stages:

- `cut_extrusion` supports a through-all cut and an explicit numeric-sketch mode;
- `circular_pattern` supports one or more feature sources, an axis reference,
  integer count, 360-degree span, optional operation-variable binding, validity/count/
  step/axis readback, body-count preservation, and removed-volume verification.

Live T5 acceptance verified one solid body, a valid through cut, 20 instances at
18 degrees, positive removed volume, a closed ten-entity primary contour (six
segments and four arcs), zero
sketch dimensions/ordinary constraints in numeric mode, and successful
save/reopen readback. Parameterized acceptance additionally changed `TB_H`,
rebuilt the model, and confirmed the root datum/profile moved after reopen while
all four fillet radii and primary-contour topology remained stable.

Managed Layer 4 adds a compound ownership fingerprint: schema/family/designation
metadata variables, the complete `TB_*` parameter set, two root sketches, the
blank and source-cut extrusions, and the circular pattern. Pattern-generated cut
copies remain owned for safety checks, while five root references define stable
block identity. Live update changed T5/Z20/B12 to AT5/Z24/B15, confirmed
`N 2 = TB_Z`, `Step 2 = TB_STEP`, actual 24-by-15-degree pattern readback, one
positive-volume body, and a fully defined sketch. Save/reopen preserved the
fingerprint. An intentionally invalid pattern binding failed and restored the
previous profile and valid 24-tooth pattern through rollback.

The HTD Layer 3 contour contains five primary segments, two outside-circle
transition arcs, and one central root arc. Parameterized mode adds seven datum
entities, 37 geometric constraints, seven formula-bound dimensions, and the same
face-width/count/angular-step operation bindings. Live create, HTD-5M to HTD-3M
designation/Z/B update, save/reopen readback, and partial-binding rollback are
accepted. Studio therefore advertises `build=true` for both timing modules.

## Studio taxonomy

Module descriptors now carry three stable catalog axes:

```text
Mechanical transmissions
  Belt drives
    Wedge pulleys       V-belt, Poly-V
    Friction pulleys    flat belt
    Synchronous pulleys trapezoidal and curvilinear timing pulleys
```

The current compact navigation uses a first selector for the full family path and
a second selector for modules within that family. The same metadata can later
back a deeper tree or searchable catalog without changing module identifiers.

## Reference

The initial profile constants and sampled tooth-shape reference originate from
the open-source multi-profile pulley generator:

- <https://github.com/JustCuzRobotics/Pulley_Generator/blob/main/Pulley_T-MXL-XL-HTD-GT2_N-tooth.scad>

The preview dimension selection and the distinction between outside, root, and
pitch diameters were cross-checked against the current BRECOflex pulley catalog:

- <https://brecoflex-co-llc.dcatalog.com/v/B212-Polyurethane-Timing-Belts-and-Pulleys/?page=163>

Vendor catalogs and licensed standards remain the authority for production
drawings and inspection limits.
