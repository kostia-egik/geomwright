# Spur gear module (`gear_spur`)

Status: implemented, live-verified create-only slice (G1–G2 of
[gear-transmission-concept.md](gear-transmission-concept.md)).

This is the first cylindrical-gear Studio module: one external spur gear with a
nominal rack-generated profile. It is not a gear pair, not an internal or
helical gear, and not a strength calculation. The architectural boundaries are
in [ARCHITECTURE.md](../ARCHITECTURE.md); this page is the user-facing contract.

## Inputs

| Field | Meaning | Notes |
| --- | --- | --- |
| `contour` | Basic rack type | ГОСТ 13755-2015 types A–D or `custom` |
| `module_mm` | Normal module `m` | Off-row values are calculated and reported as non-standard |
| `tooth_count` | Number of teeth `z` | 6–400 |
| `pressure_angle_deg` | Profile angle `α` | 20° for the standard A–D contours |
| `profile_shift` | Rack shift `x` | User input; the module does not recommend `x1/x2` yet |
| `face_width_mm` | Functional rim width `b` | Hub, bore, and keyway are separate modules |
| `pin_diameter_mm` | Over-pin measurement pin | Empty selects a nominal 1.44 m (even `z`) or 1.68 m (odd `z`) pin that fits below the tips |

Contour types choose the coefficient set:

| Type | `α` | `h_a*` | `c*` | `ρ_f*` |
| --- | --- | --- | --- | --- |
| A | 20° | 1.0 | 0.25 | 0.38 |
| B | 20° | 1.0 | 0.25 | 0.30 |
| C | 20° | 1.0 | 0.25 | 0.25 |
| D | 20° | 1.0 | 0.40 | 0.39 |

`custom` requires explicit addendum/clearance coefficients; any override marks
the result as a modified contour without a standard-conformity claim.
`addendum_coefficient` and `clearance_coefficient` are optional overrides for
the named contours.

## Preview

The end view shows the complete wheel: analytic involute flanks, the root
trochoid, and the outside circle. The first tooth space is highlighted. Radial
dimensions mark outside `dₐ`, pitch `d`, and root `d_f`; dashed reference
circles mark the pitch and base circles.

The summary and JSON response include:

- `d`, `d_b`, `d_a`, `d_f`, and the form diameter;
- tooth and space thickness at the pitch circle, tip thickness `s_a`;
- minimum shift `x_min` and the undercut flag;
- span length `W_k` with its tooth count, constant chord `s_c` and height `h_c`,
  over-pin size `M` with the pin diameter, base pitch `p_b`;
- the standard edition, module row status, verification status, and the
  representation mode (`nominal`).

Diagnostics: off-row module, small-module contour (ГОСТ 9587-81 not
implemented), modified contour, undercut, low tip thickness, span or over-pin
that cannot be measured on the flanks.

## CAD build

`Create in KOMPAS` creates one new unsaved part and verifies it:

1. cylindrical blank `d_a × b`;
2. one numeric tooth-space sketch: involute + trochoid contour with an overshoot
   cap, simplified to a documented chord tolerance;
3. one through-all cut;
4. a full circular pattern with `z` instances.

The bridge verifies one solid body, the expected volume from the simplified
contour clipped to the blank, body bounds, and the pattern count. The document
stores `GW_GEAR_VERSION`, `GW_FAMILY_CODE`, the `GEAR_*` fingerprint, and a
checksummed recipe with the Studio form values.

Reopened gear blocks are recognized as read-only. "Create a new part from these
settings" restores the form for a new build. In-place parameter editing is not
implemented in this slice; change the request and create a new part.

## Representation limits

- The root is the theoretical **sharp generating rack** trochoid, joined to the
  involute at the numerically detected intersection. GOST 16532-70
  `x_min` detects undercut and trims the flank accordingly. The selected contour
  fillet radius `ρ_f` is reported but not yet applied as a rounded cutter tip;
  that `generated_exact` envelope is a later refinement.
- Flanks are analytic involutes; the CAD sketch approximates them with bounded
  segments and exact arcs (0.01 mm default chord tolerance).
- No backlash, tolerance grade, tip chamfer, protuberance, crowning, or cutter
  wear is modelled. `nominal` is not a manufacturing-conformity claim.
- Helical, herringbone, internal, bevel, hypoid, and worm families, gear pairs,
  profile-shift recommendation, and strength calculations are separate phases.

## Verification notes

Host-side checks cover diameters, thicknesses, span/constant-chord/over-pin
formulas, undercut, tip thickness, and contour/module diagnostics. The involute
and root envelope were cross-checked against the open Apache-2.0
[py_gearworks](https://github.com/GarryBGoode/py_gearworks) reference
(`enable_undercut=True`, sharp rack): contour section areas agree within about
0.2–3 % depending on tooth count, and the module deliberately follows the same
sharp-rack envelope.

Live acceptance (KOMPAS-3D v23, 2026-10-05):

| Case | Result |
| --- | --- |
| `m2 z20 x0 b20` | create, volume error 0.0012 %, bounds and pattern 20 verified; save/reopen block `verified`, recipe intact |
| `m2 z21 x0.1 b16` | create, volume error 0.0013 %, pattern 21 verified; odd-`z` bounds envelope accepted |

Disposable evidence and oracle scripts live in the ignored
`experiments/spikes/20261005-gear-spur/` quarantine.

## Code entry points

- Layer 2 host core: `src/kompas_mcp/gears/` (`basic_racks.py`, `modules.py`,
  `involute.py`, `measure.py`, `checks.py`, `spec.py`, `preview.py`);
- Layer 3 plan: `src/kompas_mcp/gears/cad.py`;
- Studio adapter: `src/geomwright/studio/registry.py` (`gear_spur`);
- bridge: `handle_create_gear_spur` and `_inspect_gear_spur_block` in
  `bridge/kompas_bridge.py`;
- standards register: [gear-standards.md](gear-standards.md).
