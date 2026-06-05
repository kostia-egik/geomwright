# Compression Spring Ground Trim Contract

This note records the current live-checked contract for cylindrical
`compression_spring` end grinding.

## Length variables

- `L1` is the standard/full spring length between the final end planes.
- `H1` is the internal centerline construction height used by the segmented
  spiral path.
- When ground cuts are active, `H1` is derived from `L1`:

```text
H1 = L1 - WD1 + ((N31 + N32) * WD1)
```

When no ground cuts are requested, `L1` maps to the outer extreme length:

```text
H1 = L1 - WD1
```

Existing `free_length`/`height` inputs still drive `H1` directly. Use `L`,
`standard_length`, `full_length`, or `overall_length` when the input should be
the final spring length.

## End variables

- `N21` is the start end-turn count.
- `N22` is the finish end-turn count.
- `N31` is the start ground depth in turns.
- `N32` is the finish ground depth in turns.
- `WD1` is wire diameter.

`N31 = 0` disables the start cut. `N32 = 0` disables the finish cut. This
matches the native Spring module behavior where zero-depth grinding is gated by
a condition rather than represented by a harmless outside cut plane.

## Section surfaces

Ground cuts are implemented with KOMPAS `ICut` surface sections. For each active
side the bridge builds:

1. a `Point3DDisplace` from the corresponding segment joint;
2. the spring axis as the direction object;
3. the offset formula in the point distance field;
4. a plane through that point perpendicular to the axis;
5. an `ICut` using that plane as the section surface.

The current offsets are:

```text
start  = -((N21 - N31 + 0.5) * WD1)
finish =  ((N22 - N32 + 0.5) * WD1)
```

The extra `0.5 * WD1` places the zero/depth reference consistently with the
visible live geometry: without it, the cuts are half a turn deeper than intended.

## Live sample files

The current reference files in `sample/generated` are:

- `compression_trim_surface_depth0_no_cut_v5.m3d`
- `compression_trim_surface_depth1_full_turn_v5.m3d`
- `compression_trim_surface_depth_asymmetric_025_075_v5.m3d`
- `compression_trim_surface_depth1_left_hand_v5.m3d`
