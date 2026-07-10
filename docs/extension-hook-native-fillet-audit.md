# Extension Hook Native Fillet Audit

This note tracks the migration of extension-spring hook-to-body connectors from
the old trim/connect workaround to native KOMPAS 3D curve fillets.

## Connector Architectures

Old workaround:

- `Point3D` on source curves;
- trimmed source curve sections;
- `ConnectCurve` between the trimmed sections;
- chained trim/connect paths in `full_path_sequence`.

Native connector:

- `FilletCurves.Add()` via staged `create_curve_fillet_path`;
- explicit `curve1_cut_point` / `curve2_cut_point` near the hook-body joint;
- trim both curves at each hook-body connector;
- set `FilletCurve.Radius` after the first `Update()`; setting it before the
  first update leaves the readback radius at `0.0` for these legacy hook curves;
- sequence shape: native fillet result edge, native fillet result edge, chained
  body result edge, native fillet result edge, native fillet result edge.

## Current Hook Matrix

Live CAD matrix at `outer_diameter=30`, `wire_diameter=3`, `height=80`,
`turns=5`, `pitch=10`:

| Hook type | Connector builder | Live result | Contour readback |
| --- | --- | --- | --- |
| `machine_hooks` | `curve_fillet` | OK | `source_path_count=5`, `edges_count=5` |
| `v_hooks` | `curve_fillet` | OK | `source_path_count=9`, `edges_count=9` |
| `u_hooks` | `curve_fillet` | OK | `source_path_count=9`, `edges_count=9` |
| `center_loop_hooks` | `curve_fillet` | OK | `source_path_count=7`, `edges_count=7` |
| `extended_center_loop_hooks` | `curve_fillet` | OK | `source_path_count=13`, `edges_count=13` |
| `open_loop_hooks` | `curve_fillet` | OK | `source_path_count=7`, `edges_count=7` |

Native rows now use result-edge sequence entries from `FilletCurve` owner
`ModelObjects(7)`, so contour source counts and readback edge counts match.

## Open Loop Migration

`open_loop_hooks` now uses the same native `curve_fillet` connector path as the
other legacy extension hook families. The live model
`sample/live_outputs/open_loop_native_fillet.m3d` produced two native fillet
connectors and a full `7/7/7` contour.

The open-loop sketch path mapping has been corrected: `LEFT_OPEN_ARC_PATH` now
resolves to the open arc edge, not the body straight leg. The wire profile anchor
now follows the shared `PROFILE-001` contract and uses the final right/end path:

```text
profile_anchor_plane.path_name=OPEN_LOOP_NATIVE_FILLET_RIGHT_OPEN_ARC_PATH
profile_anchor_plane.vertex=end
profile_anchor_plane.point=[22.55, -13.5, 0.0]
```

The open-loop sketch also includes an explicit construction radius line from the
arc center to the free arc end (`hook_end_radius_ref`) tied into the center and
free-end helper geometry with `merge_points` constraints.

The old trim/connect fallback is no longer selected by the extension-spring
open-loop preview.

## Migration Notes

- `transition_connector_builder` records `curve_fillet` for all current legacy
  extension hook families.
- `transition_fillet_radius` / `TFR1` records the intended native hook-body
  fillet radius. The bridge now assigns the numeric `FilletCurve.Radius` after
  the first `Update()`, then binds operation parameter `Радиус` to `TFR1`.
- Binding `Радиус` before the staged radius readback produced visible KOMPAS
  expressions of the form `TFR1 - <current radius>`. With the staged order, live
  reports read back `expression_after=TFR1`.
- `TL1` and `TN1` remain in older preview metadata for legacy trim/connect
  compatibility, but current extension hook connectors use native fillets.
- The bridge transition builder registers native fillet result edges and the
  native extension hook sequence uses those edge path names directly.

## Final Extension-Hook Status

- Bent-coil center sketches now follow `CS-005` placement order.
- Mixed left/right hook composition is enabled for all eight hook families:
  `64/64` preview combinations are supported.
- `bent_coil_left_spike -> self_wrapping_hooks` deliberately does not add a
  left bent-to-body fillet. The right self-wrapping transition uses raw
  `BODY_PATH` plus the logical body end cut point (`FILLET-003`).
- The final extension-hook mechanics audit has no known open hook-family
  migration target.
