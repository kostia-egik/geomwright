# Cylindrical gear module (`gear_spur`)

Status: implemented, live-verified create-only slice for external spur and
helical gears with four basic-rack systems (G1–G2 and the cylindrical part of G4
of [gear-transmission-concept.md](gear-transmission-concept.md)); also exposed as
four MCP tools.

This is the first cylindrical-gear Studio module: one external gear with a
nominal rack-generated profile. `helix_angle_deg = 0` is a spur gear; a positive
angle turns the same module into a helical gear whose end view is the transverse
section. It is not a gear pair, not an internal, herringbone, bevel, or worm
gear, and not a strength calculation. The architectural boundaries are in
[ARCHITECTURE.md](../ARCHITECTURE.md); this page is the user-facing contract.

## Inputs

The Studio form separates the standard from its modification, then derives the
contour coefficients from that pair. Free coefficient input is available only
for the user-defined modification. The inputs sit in six bordered blocks in the
working order: standard and modification, tooth direction and angle, main
dimensions, derived coefficients, tip chamfers, and over-pin measurement. The
derived-coefficient block folds away while the named modification supplies the
coefficients; the measurement block is folded by default because the pin is a
rarely changed inspection input.

| Field | Meaning | Notes |
| --- | --- | --- |
| Standard | Basic-rack system | ГОСТ 13755-2015, ГОСТ 9587-81, ГОСТ Р 50531-93, or ISO 53:1998 |
| Contour modification | Named variant of the standard | System-specific names plus `custom` |
| `module_mm` | Normal module `m` | Ряды ГОСТ 9563-60 для ГОСТ-систем и ряды ISO 54:1996 Series I/II для ISO 53; free value for `custom` |
| `tooth_count` | Number of teeth `z` | 6–400 |
| `profile_shift` | Rack shift `x` | User input; the module does not recommend `x1/x2` yet |
| `face_width_mm` | Functional rim width `b` | Hub, bore, and keyway are separate modules |
| `helix_angle_deg` | Helix angle `β` on the reference cylinder | Enabled only for a helical direction; 0–45° |
| `hand` | Tooth direction | Studio presents one selector: **Прямозубая** (`β = 0`), **Правое направление**, **Левое направление**; the angle field unlocks only for a helical choice |
| `pin_diameter_mm` | Over-pin measurement pin | Measurement only; does not enter the profile or CAD. Empty selects the nearest cached standard pin that fits below the tips; an explicit size is used as given |
| `tip_chamfer_mm` | End chamfer width `c` on the tooth tips | 0 keeps sharp tooth ends; otherwise two full-rotation cone cuts at both faces |
| `tip_chamfer_angle_deg` | Chamfer angle `α` to the end face | 45° is the standard `c × 45°` form; 15–75° |

### Basic-rack standards

| Standard | Scope | Modifications (`α`, `h_a*`, `c*`, `ρ_f*`) |
| --- | --- | --- |
| ГОСТ 13755-2015 | large-module cylindrical gears, `m ≥ 1` | A `20°, 1.0, 0.25, 0.38`, B `20°, 1.0, 0.25, 0.30`, C `20°, 1.0, 0.25, 0.25`, D `20°, 1.0, 0.40, 0.39`, `custom` |
| ГОСТ 9587-81 | small-module gears, `0.1 ≤ m < 1` | `h1_c25` `20°, 1.0, 0.25, 0.38`; `h1_c30` `20°, 1.0, 0.30, 0.44`; `h11_c40` `20°, 1.1, 0.40` (`m < 0.5`, fillet per annex figure); `h11_c25` `20°, 1.1, 0.25` (`0.5 ≤ m < 1`, fillet per annex figure); `custom` |
| ГОСТ Р 50531-93 | high-stress gears, `m ≥ 1`, accuracy grade 7 or finer per ГОСТ 1643 | type 1 `25°, 1.0, 0.20328, 0.35208`; type 2 `28°, 0.9, 0.18438, 0.34754`; `custom` |
| ISO 53:1998 | general and heavy engineering, ISO 54 modules `1..50` | A = table 2 `20°, 1.0, 0.25, 0.38`, B `20°, 1.0, 0.25, 0.30`, C `20°, 1.0, 0.25, 0.25`, D `20°, 1.0, 0.40, 0.39`, `custom` |

An out-of-scope module is still calculated, but the report emits
`gear_standard_module_range` instead of claiming standard conformity. The module
row check uses the standard's own module system (ГОСТ 9563-60 or ISO 54:1996).
The Studio module dropdown is filtered to the selected standard and modification
range (including the per-modification ГОСТ 9587-81 split); an out-of-range value
can only be entered through the user-defined modification, where it is reported.

For `custom`, the pressure angle, addendum, clearance, and root-fillet
coefficients become editable and are required. Any custom coefficient set
removes the standard-conformity claim.

The pin diameter is a **measurement-only** input: it changes the over-pin size
`M` and its fit check, never the generated profile or the CAD body. Empty selects
the cached standard diameter nearest the nominal 1.44 m (even `z`) or 1.68 m
(odd `z`) pin that still fits below the tips. The cached rows are ГОСТ 2475-88
table 3 (involute splines) and annex 2 (measuring wires), ГОСТ 25255-82 (long
rollers), and ГОСТ 22696-77 (short rollers); every reported pin carries its
source id. Explicit sizes are never replaced.

The tool type that will manufacture the gear (червячная фреза, долбяк, дисковый
модульный инструмент) is deliberately **outside this slice**. The current module
builds the nominal profile of the standard basic rack; selecting a real tool
changes the generated root, protuberance, and undercut and belongs to the later
`generated_exact` phase with its own standards (ГОСТ 9324-80, ГОСТ 9323-79 and
related). A tool selector without tool-parameter-driven geometry would be a
non-functional control, so it is not exposed yet.

## Helical gears

A positive `helix_angle_deg` keeps the basic rack and the crown section inputs
but changes the geometry to the **transverse section** of a helical gear:

- transverse module `m_t = m_n / cos β`;
- transverse pressure angle `tan α_t = tan α_n / cos β`;
- reference diameter `d = m_n·z / cos β = m_t·z`;
- addendum and dedendum stay normal: `h_a = m_n(h_a* + x)`,
  `h_f = m_n(h_a* + c* − x)`;
- base-cylinder helix `tan β_b = tan β·cos α_t`;
- axial pitch `p_x = π·m_n / sin β`, lead `L = π·m_n·z / sin β`;
- axial overlap `ε_β = b / p_x`; the module warns below 1.0;
- minimum shift `x_min = h_a* − z·sin²α_t / (2·cos β)`;
- span measurement is a normal-plane measurement:
  `W_k = m_n·cos α_n·[π(k − 0.5) + z·inv α_t] + 2·x·m_n·sin α_n`;
- over-pin `inv α_D = inv α_t + D / (m_n·z·cos α_n) − π/(2z) + 2·x·tan α_n/z`,
  with `d_D = d·cos α_t / cos α_D`;
- the constant chord and base pitch are normal-plane values (`m_n`, `α_n`);
- the reported tip thickness check uses the normal thickness
  `s_an = s_at·cos β_b`.

The root fillet of the transverse profile uses the transverse rack with
`α_t`, the normal depths, and `ρ_t ≈ ρ_n / cos β`; the involute flanks and all
diameters are exact for the nominal model.

The hand is a separate field, not the sign of the angle: `right` maps to a
right-hand tooth trace, `left` to a left-hand one. The Studio form exposes the
direction first (**Прямозубая** / **Правое направление** / **Левое
направление**) and unlocks the helix-angle input only for a helical choice; the
angle value is kept while the direction is switched back to spur. The summary
adds `β`, `hand`, `m_t`, `α_t`, `β_b`, `p_x`, `L`, `ε_β`, and `s_an`.

## Preview

The preview has two views:

- the **end view**: a cropped sector of three teeth drawn as a single functional
  contour, in the same broken-out style as the chain sprockets and timing
  pulleys. Wavy break lines close the fragment below the root circle. Dashed
  reference arcs mark the pitch and base circles; radial dimensions mark outside
  `dₐ`, pitch `d`, and root `d_f`;
- the **side view** (`secondary_view` in the JSON): a flat side view of the rim
  (`b × d_a`, axis horizontal). Every sampled point of the real transverse
  profile is swept across the face width as a helix and projected
  orthographically as `v = r·cos(θ + twist·x)`; only the visible near-side runs
  are drawn. The drawing shows exactly one pair of bright lines per visible
  tooth: the two tip-arc ends (transitions to the involute flanks) taken from
  the analytic profile, replicated for all `z` teeth. Their vertical positions
  and slopes come from the actual tooth faces, not from a fixed schematic
  pattern; hidden (far-side) teeth produce no visible runs and disappear. There
  are no root traces and no dashed reference lines. When end chamfers are
  enabled, the silhouette corners are cut by the chamfer legs and the tip lines
  are clipped by that silhouette: lines that stay inside the outline run to the
  vertical side lines (the end faces), while lines near the top/bottom corners
  stop on the slanted chamfer edge. A spur
  gear keeps the pairs parallel to the axis; a helical gear tilts each pair by
  the real helix twist and the hand sets the direction. The view is dimensioned
  by `b` and `d_a`, annotates `β`, and the panel note repeats `β`, hand, lead
  `L`, and `ε_β`. It is an orthographic side view, not a section.

The summary and JSON response include:

- `d`, `d_b`, `d_a`, `d_f`, and the form diameter;
- tooth and space thickness at the pitch circle, tip thickness `s_a`;
- minimum shift `x_min` and the undercut flag;
- span length `W_k` with its tooth count, constant chord `s_c` and height `h_c`,
  over-pin size `M` with the pin diameter, base pitch `p_b`;
- the standard, modification, standard edition, module-row status,
  verification status, and the representation mode (`nominal`).

Diagnostics: off-row module for the selected module system, module outside the
selected contour's applicable range, user-defined contour, undercut, low tip
thickness, span or over-pin that cannot be measured on the flanks.

## CAD build

`Create in KOMPAS` creates one new unsaved part and verifies it:

1. cylindrical blank `d_a × b`;
2. optional **end chamfers** (`tip_chamfer_mm > 0`): two full-rotation cuts
   (`rotational_cut`, `Rotateds.Add(29)`) around the gear axis. The profile is
   a right triangle in the axial plane: the axial leg is the chamfer width `c`,
   the radial leg is `c·tan(α)` where `α` is the angle to the end face (45°
   default). The chamfers are cut into the blank **before** the tooth-space
   cut, so the expensive pattern rebuild stays the last feature; the final
   Boolean result is identical to chamfering the finished teeth;
3. one numeric tooth-space sketch: two smooth cubic Bézier-NURBS curves per
   flank (root transition and involute) joined at the form point, with exact
   cap and closure arcs;
4. a tooth-space cut:
   - `β = 0`: one through-all extrusion cut;
   - `β > 0`: `helical_cut_evolution` — Evolution (47) cut that sweeps the
     transverse sketch along a cylindrical 3D spiral. The spiral is anchored by
     its position point **on the gear axis**, its radius is set by `Diameter =
     d`, `Step = L`, `Height = b`, `BuildingDirection` into the face, and
     `TurnDirection` follows `hand`;
5. a full circular pattern with `z` instances.

The axis anchoring of the spiral is not cosmetic: with the position point on
the reference cylinder KOMPAS produced a deformed sweep (measured removal
dropped to 25 % of the analytic tooth-space volume at β=20°, scaling as
`1/lead`; `BySurfaceNormal` and `SketchShiftType` did not repair it). With the
anchor on the axis the removal matches the transverse-section volume to within
0.005 % on the live cases. Disposable probes for this finding are in the ignored
spike quarantine.

When chamfers are enabled the expected volume subtracts the material actually
removed by the two cone cuts, sampled from the analytic per-pitch outline; the
naive full-ring formula overestimates the removal roughly fourfold because only
the teeth, not the full circumference, lie in the cut band. The live
single-cut values match the sampler within 1.7 %.

After the final rebuild the bridge hides the construction geometry: the
helical spiral, the 3D points and axis, every sketch, and the default planes.
The step report carries the hidden count and fails if a critical object could
not be hidden; a clean model shows only the blank, the cuts, and the pattern.

The combined entity count is seven per tooth space, so the pattern stays
practical. Each flank curve is fitted to the analytic profile with a bounded
deviation (reported in the plan; typically below 0.02 mm). The bridge verifies
one solid body, the expected volume from the analytic contour clipped to the
blank, body bounds, and the pattern count. The document stores
`GW_GEAR_VERSION`, `GW_FAMILY_CODE`, the `GEAR_*` fingerprint (standard and
modification codes, plus `GEAR_BETA_DEG` and `GEAR_HAND`), and a checksummed
recipe with the Studio form values.

Reopened gear blocks are recognized as read-only. "Create a new part from these
settings" restores the form for a new build. In-place parameter editing is not
implemented in this slice; change the request and create a new part.

## Representation limits

- The root is the theoretical **sharp generating rack** trochoid, joined to the
  involute at the numerically detected intersection. ГОСТ 16532-70 `x_min`
  detects undercut and trims the flank accordingly. The selected contour fillet
  radius `ρ_f` is reported but not yet applied as a rounded cutter tip; that
  `generated_exact` envelope is a later refinement.
- The CAD flank is a smooth spline through the analytic samples; a theoretical
  tangent discontinuity at the base-circle/form join is preserved by splitting
  the flank into a root curve and an involute curve there.
- No backlash, tolerance grade, protuberance, crowning, or cutter wear is
  modelled; the end chamfer is the nominal `c × α` cone, not a tooth-by-tooth
  edge blend. `nominal` is not a manufacturing-conformity claim.
- The helical root fillet is the transverse slice of the normal rack
  (`ρ_t ≈ ρ_n / cos β`), an approximation of the exact helicoid fillet; the
  involute flanks, base helix, and all reference diameters are exact.
- Helical CAD is limited to external right/left cylindrical gears. The internal
  ring gear is a separate module with its own contract
  ([gear-internal.md](gear-internal.md)); herringbone, bevel, hypoid, and worm
  families, gear pairs, profile-shift recommendation, and strength calculations
  are separate phases.

## Verification notes

Host-side checks cover diameters, thicknesses, span/constant-chord/over-pin
formulas, undercut, tip thickness, and contour/module diagnostics. The involute
and root envelope were cross-checked against the open Apache-2.0
[py_gearworks](https://github.com/GarryBGoode/py_gearworks) reference
(`enable_undercut=True`, sharp rack): contour section areas agree within about
0.2–3 % depending on tooth count, and the module deliberately follows the same
sharp-rack envelope.

Live acceptance (KOMPAS-3D v23, 2026-10-05, smooth-spline CAD):

| Case | Result |
| --- | --- |
| `m2 z20 x0 b20` | create, volume error 0.007 %, 7-entity tooth space, pattern 20 verified; save/reopen block `verified`, recipe intact |
| `m2 z21 x0.1 b16` | create, volume error 0.0044 %, pattern 21 verified; odd-`z` bounds envelope accepted |
| `m2 z20 x0 b20 β20 right` | create, volume error 0.005 %, pattern 20 verified; save/reopen block `verified`, recipe intact |
| `m2 z21 x0.2 b16 β30 left` | create, volume error 0.0046 %, pattern 21 verified; save/reopen block `verified`, recipe intact |
| `m2 z20 x0 b20 + chamfer 0.5×45` | create, volume error 0.008 %, two chamfer cuts remove 17.15 mm³ each from the blank, 15 construction objects hidden, save/reopen `verified` |
| `m2 z20 x0 b20 β20 right + chamfer 0.5×45` | create, volume error 0.007 %, 17 construction objects hidden, save/reopen `verified` |
| Studio HTTP create job | completed and verified through the production Studio path |

The Evolution probe matrix (straight vs helical lead, section radius, plane,
`SketchShiftType`, `BySurfaceNormal`) is recorded in the ignored
`experiments/spikes/20261005-gear-spur/` quarantine; the decisive comparison is
anchor-on-axis (exact volume) versus anchor-on-reference-cylinder (25 % of the
expected removal at β=20°).

Disposable evidence and oracle scripts live in the ignored
`experiments/spikes/20261005-gear-spur/` quarantine.

## Code entry points

- Layer 2 host core: `src/kompas_mcp/gears/` (`basic_racks.py`, `modules.py`,
  `spec.py`, `involute.py`, `nurbs.py`, `measure.py`, `checks.py`, `preview.py`,
  `pins.py`);
- Layer 3 plan: `src/kompas_mcp/gears/cad.py`;
- MCP tools: `src/kompas_mcp/gear_tools.py` (`list_gear_standards`,
  `preview_cylindrical_gear`, `create_cylindrical_gear`,
  `inspect_cylindrical_gear`);
- Studio adapter: `src/geomwright/studio/registry.py` (`gear_spur`);
- bridge: `handle_create_gear_spur`, `handle_inspect_gear_spur`, and
  `_inspect_gear_spur_block` in `bridge/kompas_bridge.py`;
- standards register: [gear-standards.md](gear-standards.md).

## Verified sources

The contour and row data were taken from locally cached or publicly available
sources; only derived numeric values are stored in the repository:

- ГОСТ 9587-81 official text (local research cache);
- ГОСТ Р 50531-93 (public PDF; table on page 2, verified visually);
- ISO 53:1998 (public sample PDF; table 2 and annex A);
- ISO 54:1996 (public sample PDF; table 1, series I/II);
- ГОСТ 2475-88 (public PDF; table 3 and annex 2 table 6);
- ГОСТ 25255-82 and ГОСТ 22696-77 (public tables; nominal roller diameters).
