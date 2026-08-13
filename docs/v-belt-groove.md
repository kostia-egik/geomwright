# V-belt groove profile, preview, and CAD builder

Status: Layer 2 catalog/preview and the focused Layer 3 cut-from-body builder are
implemented and live-verified in KOMPAS-3D. The user-facing Layer 4 pulley
workflow is defined to create and own a new blank; applying grooves to an
arbitrary existing body is not a supported product workflow.

This module defines deterministic functional V-groove geometry without hubs,
bores, keyways, or threads. Upper groove-edge rounding is an optional managed
post-cut fillet feature.

## Public MCP tools

All four tools accept one strict `request` object. Unknown request fields are
rejected rather than ignored.

### `list_v_belt_profiles`

Lists profiles for one explicit `standard_system` and optionally filters by:

```text
classical
narrow_wedge
```

Supported standard systems:

```text
din_iso          # default; manufacturer table based on DIN 2211 / ISO context
gost_20889_88    # classical Z/A/B/C/D/E profiles and standard top-edge radii
```

### `resolve_v_belt_profile`

Resolves one built-in profile inside the selected standard system and, when
`datum_diameter` is supplied, applies that catalog's minimum diameter and
diameter-dependent groove-angle rule.

### `preview_v_belt_groove`

Returns:

- normalized profile data;
- derived outer/root diameters;
- total face width;
- axial groove centers;
- closed cut polygons in axial/radial coordinates;
- datum points for each groove;
- outer-surface segments between grooves;
- target-blank requirements;
- planned composition references;
- assumptions, warnings, and provenance.

It does not create a KOMPAS document or claim that CAD references already exist.

### `apply_v_belt_grooves`

Applies the previewed sharp V-grooves to an existing cylindrical blank. The
tool defaults to `execute=false`; a write requires both `execute=true` and
`confirm_write=true`.

The request must identify an exact open `document_id` and declare the target
blank contract:

- one solid body in the top part;
- `axis=global_x`;
- outer diameter equal to the previewed outer diameter;
- an axial interval exactly matching the previewed origin-based pulley face
  interval.

`axial_center` positions the groove set on the existing blank. The tool creates
one managed sketch with one closed component per groove, performs a rotational
cut, hides the sketch, and returns actual feature/sketch references plus
analytic pitch and outer-rim references. It does not save the document; use the
normal explicit save workflow after checking the result.

This tool remains the internal Layer 3 composition primitive and a focused
acceptance surface. Geomwright Studio and the Layer 4 pulley family do not ask a
user to describe an arbitrary target blank. They create a known parameterized
blank first and invoke this builder against that owned result.

For `gost_20889_88`, `include_standard_top_edge_fillet=true` (the default)
automatically applies the catalog radius as a separate 3D fillet. Set the flag to
`false` for a sharp GOST cut, or provide `top_edge_fillet_radius` to override the
standard/default behavior explicitly.

## Built-in catalog

### `din_iso`

| Profile | Family | Minimum datum diameter, mm | `b_d`, mm | `b₁ ≈`, mm | `c`, mm | `e`, mm | `f`, mm | `t min`, mm | Angle rule |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Z | classical | 50 | 8.5 | 9.7 | 2.0 | 12.0 | 8.0 | 11.0 | 34° through 80 mm, then 38° |
| A | classical | 71 | 11.0 | 12.7 | 2.8 | 15.0 | 10.0 | 14.0 | 34° through 118 mm, then 38° |
| B | classical | 112 | 14.0 | 16.3 | 3.5 | 19.0 | 12.5 | 18.0 | 34° through 190 mm, then 38° |
| C | classical | 180 | 19.0 | 22.0 | 4.8 | 25.5 | 17.0 | 24.0 | 34° through 315 mm, then 38° |
| D | classical | 355 | 27.0 | 32.0 | 8.1 | 37.0 | 24.0 | 28.0 | 36° through 500 mm, then 38° |
| E | classical | 500 | 32.0 | 40.0 | 12.0 | 44.5 | 29.0 | 33.0 | 36° through 630 mm, then 38° |
| SPZ | narrow wedge | 63 | 8.5 | 9.7 | 2.0 | 12.0 | 8.0 | 11.0 | 34° through 80 mm, then 38° |
| SPA | narrow wedge | 90 | 11.0 | 12.7 | 2.8 | 15.0 | 10.0 | 14.0 | 34° through 118 mm, then 38° |
| SPB | narrow wedge | 140 | 14.0 | 16.3 | 3.5 | 19.0 | 12.5 | 18.0 | 34° through 190 mm, then 38° |
| SPC | narrow wedge | 224 | 19.0 | 22.0 | 4.8 | 25.5 | 17.0 | 24.0 | 34° through 315 mm, then 38° |

Source:

- Optibelt, *Technical Manual: V-Belt Drives*;
- table *Groove dimensions according to DIN 2211*;
- printed page 49 / PDF page 51;
- contextual references in the manual: DIN 2217 and ISO 4183;
- [public manufacturer PDF](https://a.storyblok.com/f/192292/x/6c78e81d5a/optibelt-tm-v-belt-drives.pdf), retrieved 2026-07-26.

The values are manufacturer-reference facts, not a redistributed licensed
standard. Certified drawings must be checked against the applicable licensed
standard edition.

### `gost_20889_88`

| Profile | Minimum datum diameter, mm | `b_p`, mm | Above datum, mm | Below datum, mm | `e`, mm | `f`, mm | Top radius, mm | Angle schedule |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Z | 50 | 8.5 | 2.5 | 7.0 | 12.0 | 8.0 | 0.5 | 34°: 50–71; 36°: 80–100; 38°: 112–160; 40°: ≥180 |
| A | 75 | 11.0 | 3.3 | 8.7 | 15.0 | 10.0 | 1.0 | 34°: 75–112; 36°: 125–160; 38°: 180–400; 40°: ≥450 |
| B | 125 | 14.0 | 4.2 | 10.8 | 19.0 | 12.5 | 1.0 | 34°: 125–160; 36°: 180–224; 38°: 250–500; 40°: ≥560 |
| C | 200 | 19.0 | 5.7 | 14.3 | 25.5 | 17.0 | 1.5 | 36°: 200–315; 38°: 355–630; 40°: ≥710 |
| D | 315 | 27.0 | 8.1 | 19.9 | 37.0 | 24.0 | 2.0 | 36°: 315–450; 38°: 500–900; 40°: ≥1000 |
| E | 500 | 32.0 | 9.6 | 23.4 | 44.5 | 29.0 | 2.0 | 36°: 500–560; 38°: 630–1120; 40°: ≥1250 |

Source: GOST 20889-88, clauses 2.1 and 2.4, Tables 1/2 and Drawing 10;
[public standard reproduction](https://allgosts.ru/21/220/gost_20889-88).
GOST dimensions are stored as an independent catalog and are never mixed with
the DIN/ISO-derived records.

## Geometry

Coordinate convention:

```text
x = pulley axial direction
y = radius from pulley axis
```

For datum diameter `d_d`, groove angle `α`, datum offset `c`, datum width `b_d`,
and minimum groove depth `t`:

```text
r_datum = d_d / 2
r_outer = r_datum + c
r_root  = r_outer - t

b_top  = b_d + 2*c*tan(α/2)
b_root = b_d - 2*(t-c)*tan(α/2)
```

The catalog `b₁` value is marked approximate and is reported as a comparison
value. It is not used to move the side walls away from the exact `b_d/c/α`
construction.

For `n` grooves, pitch `e`, and edge distance `f`:

```text
face_width = (n - 1)*e + 2*f
```

Grooves are centered symmetrically about `x=0`.

## Example

```text
profile        A
datum diameter 100 mm
grooves        2
```

Preview result:

```text
angle          34°
outer diameter 105.6 mm
root diameter  77.6 mm
face width     35 mm
groove centers -7.5 / +7.5 mm
```

## Custom and overridden profiles

`designation=CUSTOM` accepts an explicit profile with required:

- datum width;
- datum offset;
- groove pitch;
- edge distance;
- groove depth;
- groove angle.

Built-in profiles may be overridden only for geometry fields. Catalog minimum
diameter cannot be lowered by an override; use `CUSTOM` for nonstandard work.

Any override is reported as non-catalog geometry.

## Composition contract

Implemented CAD mode:

```text
cut_from_body
```

The target blank must provide:

- a stable axis reference;
- the previewed outer-cylinder diameter;
- exactly the previewed face interval, starting at the global origin;
- material below the previewed root radius.
- `parameter_base.outer_radius_variable` and
  `parameter_base.face_width_variable` for associative origin-mode datums.

The current composed blank uses `R1` and `L1`. The groove sketch links
`VB_OR=R1` and `VB_FACE_W=L1`; it does not copy body coordinates or lock a chain
of profile points. Native `ISketch.AddProjectionOf(...)` was not selected for the
final contract because a clean cylinder exposes no stable materialized straight
silhouette edge through that API. The global axis is fixed; origin and outer
datums are attached to it through pre-merge constraints rather than fixed datum
or profile points.

Current semantic outputs:

```text
member.axis
member.outer_rim
member.pitch_surface
member.functional_feature
member.profile_sketch
member.edge_fillet_feature  # when a standard or explicit fillet is active
```

The operation and sketch are actual KOMPAS model-object references. The axis,
pitch surface, and outer rim remain explicit analytic references. Stable body
and end-face references are reserved for the broader pulley-family builder.

## Model-tree names and variable order

The Layer 2 plan owns the exact KOMPAS entity names; the bridge applies those
names without reconstructing them. Default groove operations use:

```text
V-belt grooves {designation} x{count} profile
V-belt grooves {designation} x{count} cut rotation
V-belt grooves {designation} x{count} top edge fillets R{radius}  # only when the fillet is active
```

The optional request `name` is a semantic suffix, not a replacement for the
canonical operation descriptor. For example, `name="drive pulley"` produces
`V-belt grooves A x2 cut rotation - drive pulley`. Run labels such as `FINAL`
or timestamps do not belong in canonical model-tree names.

The canonical final-example fixture also names its base entities
`Pulley blank profile` and `Pulley blank rotation`; these names
come from the generic stepped-shaft `sketch_name` and `name` parameters rather
than from a post-generation patch.

Operation variables are emitted in dependency-reading order:

```text
external links       VB_OR, VB_FACE_W
independent layout   VB_EDGE, VB_PITCH (multi-groove only)
independent groove   VB_TOP_W, VB_DEPTH, VB_ANGLE
derived master       VB_RR, VB_ROOT_W
dependent copies     VB_G2_TOP_W, VB_G3_TOP_W, ...
```

This order is part of the Layer 2 plan contract and is verified exactly in
host-side tests. It keeps source parameters above formulas that consume them and
omits `VB_PITCH` when only one groove is present.

## Optional post-cut top-edge fillet

`apply_v_belt_grooves` accepts optional `top_edge_fillet_radius` and
`include_standard_top_edge_fillet`. DIN/ISO catalog records have no numeric
standard radius, so their default remains sharp. GOST records apply their catalog
radius automatically while `include_standard_top_edge_fillet=true`; set it to
`false` for a sharp GOST cut. A positive explicit radius overrides either
catalog. In every case the rounding is one separate KOMPAS 3D fillet after the
rotational cut; the operational sketch is not modified.

The host plan computes two semantic top-edge probe points per groove. After the
sharp cut passes topology, rebuild, body-count, and analytical-volume checks, the
bridge requires exactly one valid circular `IEdge` at every point, rejects
duplicate references, and assigns all resolved edges to one `IFillet` operation.
The fillet must rebuild successfully, retain one body, and remove measurable
additional material.

For GOST profile A the catalog radius is `1.0 mm`. Because dimensions and radius
come from the same `gost_20889_88` record, the default does not create a hybrid
profile. Cross-system or manufacturing-specific behavior remains possible only
through the explicit radius override.

## Explicit limitations

- root rounding is not modeled;
- upper groove-edge rounding is optional and currently uses one constant-radius
  post-cut fillet feature;
- tolerances are reported by provenance but not applied to nominal geometry;
- no hub, bore, keyway, thread, or generic chamfer is created;
- no power/rating or belt-selection calculation exists yet;
- the preview remains read-only; only `apply_v_belt_grooves` changes CAD;
- only a global-X cylindrical blank with one top-part body is supported;
- the target diameter and axial interval are declared by the caller; independent
  measurement of those dimensions is not yet implemented;
- parameter-base variable names must come from the blank builder's semantic
  output; arbitrary global variable names are not inferred;
- failed execution can leave an unsaved partial sketch/feature in the disposable
  document; discard or reopen without saving before retrying.

## Execution verification

The bridge verifies:

1. exact document activation and 3D/top-part/single-body preflight;
2. the expected number of closed, unbranched, non-self-intersecting sketch
   components;
3. a fully defined operational sketch after one bounded solver-settle retry;
4. one axis-style line, four construction-style lines, and profile-only topology
   audit after settled readback;
5. valid rotational-cut creation and successful part rebuild;
6. unchanged body count and decreased body volume;
7. actual removed volume against the sharp-profile analytical estimate, with a
   hard failure above 25% relative error;
8. when requested, exactly `2 × groove_count` unique circular top edges, valid
   fillet update/rebuild, unchanged body count, and additional volume decrease;
9. hidden sketch status unless diagnostic visibility is explicitly requested.

The live acceptance case used profile A, datum diameter 100 mm, two grooves, and
a Ø105.6 × 35 mm disposable blank. The cut changed volume from
306.5390182185 cm³ to 236.8417682919 cm³. Removed volume matched the analytical
69.6972499266 cm³ estimate within floating-point precision. Save/reopen readback
preserved one body, two closed sketch components, zero gaps/branches/self
intersections, the named rotational cut, `ConstraintsState=2`, 8 dimensions,
and 8 dimension-variable links. Display-only diameter/angle dimensions and the
non-driving datum construction were removed; every remaining dimension is a
driving dimension whose expression resolves through a semantic `VB_*` variable.

The post-cut acceptance used the same case with
`top_edge_fillet_radius=1.0 mm`. Four unique circular edges were selected and one
valid fillet feature was created. Volume changed from the sharp-cut
236.841768291568 cm³ to 236.705591230913 cm³; the fillet removed an additional
0.136177060655 cm³. Save/reopen preserved one fillet feature with
`Radius1=Radius2=1.0`, one body, and the original fully-defined 8-dimension sketch.

## Final local example matrix

The following ignored acceptance artifacts were generated under
`sample/live_outputs/`. They are intentionally not committed as binary CAD
samples; the adjacent JSON manifest records the exact build/readback evidence.

| Example | Standard/profile | Datum diameter | Grooves | Outer/root diameter | Face width | Angle | Fillet | Sharp/final volume, cm³ |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- | --- |
| `final_vbelt_01_din_iso_Z_d80_g1_2026_08_11_011257.m3d` | DIN/ISO Z | 80 | 1 | 84 / 62 | 16 | 34° | none | 72.198102 / 72.198102 |
| `final_vbelt_02_din_iso_SPB_d200_g2_2026_08_11_011257.m3d` | DIN/ISO SPB | 200 | 2 | 207 / 171 | 44 | 38° | none | 1258.255328 / 1258.255328 |
| `final_vbelt_03_gost_20889_88_A_d100_g3_2026_08_11_011257.m3d` | GOST A | 100 | 3 | 106.6 / 82.6 | 50 | 34° | 1.0 mm | 344.560640 / 344.354434 |
| `final_vbelt_04_gost_20889_88_C_d315_g4_2026_08_11_011257.m3d` | GOST C | 315 | 4 | 326.4 / 286.4 | 110.5 | 36° | 1.5 mm | 7987.134337 / 7985.323837 |

Reopen checks reported `ConstraintsState=2`, zero gaps/branches/self
intersections, and respectively 1/2/3/4 closed profile components. Exact
canonical sketch/cut/fillet names survived reopen, and the manifest records the
dependency-ordered variable list for every example. GOST examples preserved
exactly one valid fillet feature with the catalog radius. Evidence:
`final_vbelt_examples_verified_2026_08_11_011257.json`.
