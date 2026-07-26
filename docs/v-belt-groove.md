# V-belt groove profile and preview

Status: Layer 2 catalog/preview implemented. No COM/CAD builder is exposed yet.

This module defines deterministic functional V-groove geometry without hubs,
bores, keyways, threads, or generic finishing features.

## Public MCP tools

All three tools accept one strict `request` object. Unknown request fields are
rejected rather than ignored.

### `list_v_belt_profiles`

Lists all built-in profiles or filters by:

```text
classical
narrow_wedge
```

### `resolve_v_belt_profile`

Resolves one built-in profile and, when `datum_diameter` is supplied, applies the
catalog minimum diameter and diameter-dependent groove-angle rule.

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

## Built-in catalog

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

Preferred future CAD mode:

```text
cut_from_body
```

The target blank must provide:

- a stable axis reference;
- the previewed outer-cylinder diameter;
- at least the previewed face width;
- material below the previewed root radius.

Planned semantic outputs:

```text
member.body
member.axis
member.left_face
member.right_face
member.outer_rim
member.pitch_surface
member.functional_feature
```

These references are not produced until the Layer 3 CAD builder exists.

## Explicit limitations

- root rounding is not modeled;
- outer groove-edge rounding is not modeled;
- tolerances are reported by provenance but not applied to nominal geometry;
- no hub, bore, keyway, thread, or generic chamfer is created;
- no power/rating or belt-selection calculation exists yet;
- no KOMPAS model is created by the preview.

## Next implementation gate

The Layer 3 builder may be added only after review of this nominal profile. It
will:

1. preflight the target cylindrical blank;
2. create one meridional cut sketch or one managed multi-groove sketch;
3. cut by rotation around the supplied axis;
4. name the functional feature and variables;
5. return actual semantic references;
6. verify body count, diameters, groove count, hidden auxiliaries, save, and
   reopen readback.
