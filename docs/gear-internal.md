# Internal cylindrical gear module (`gear_internal`)

Status: implemented, live-verified create-only slice for internal spur and
helical gears with the same four basic-rack systems as the external gear
(GOST 19274-73 geometry; G4 subfamily of
[gear-transmission-concept.md](gear-transmission-concept.md)); exposed as three
MCP tools.

This module builds one internal cylindrical gear — a ring gear — from an
explicit ring blank. The teeth are cut from the inner surface of the ring; the
blank outside diameter is an operator input and is never invented by the module.
It is not a gear pair, not a housing or hub, and not a strength calculation. The
architectural boundaries are in [ARCHITECTURE.md](../ARCHITECTURE.md); this page
is the user-facing contract.

## Inputs

The Studio form reuses the external gear blocks: standard and modification,
tooth direction and angle, main dimensions, derived coefficients, and over-pin
measurement. The internal module adds the ring outside diameter and has no tip
chamfers yet.

| Field | Meaning | Notes |
| --- | --- | --- |
| Standard | Basic-rack system | ГОСТ 13755-2015, ГОСТ 9587-81, ГОСТ Р 50531-93, or ISO 53:1998 |
| Contour modification | Named variant of the standard | System-specific names plus `custom` |
| `module_mm` | Normal module `m` | Standard module rows; free value for `custom` |
| `tooth_count` | Number of internal teeth `z` | 8–400 |
| `profile_shift` | Rack shift `x2` of the wheel | Positive values thin the internal tooth (ГОСТ 19274-73) |
| `face_width_mm` | Functional ring width `b` | The tip-diameter bore is part of this module |
| `ring_outside_diameter_mm` | Ring blank outside diameter `D` | Must exceed the internal root diameter |
| `helix_angle_deg` | Helix angle `β` on the reference cylinder | 0–45°; the end view is the transverse section |
| `hand` | Tooth direction | Right or left; ignored for `β = 0` |
| `pin_diameter_mm` | Over-pin measurement pin | Measurement only; nominal 1.5 m for the wheel |
| Derived coefficients | `α`, `h_a*`, `c*`, `ρ_f*` | Editable only for the user-defined modification |

The ring wall above the roots is checked: a wall thinner than
`max(1.5 mm, m)` is reported, and an outside diameter at or below the root
diameter is rejected before any CAD work.

## Geometry

The nominal diameters follow ГОСТ 19274-73, table 2, item 13:

- reference diameter `d2 = m_t z`, base diameter `d_b2 = d2 cos α_t`;
- tip diameter `d_a2 = d2 - 2 (h_a* - x2 - 0.2) m`;
- root diameter `d_f2 = d2 + 2 (h_a* + c* + x2) m`.

The `0.2 m` term is the standard's additional tip offset for the wheel. The
tooth thickness at the reference circle is `s2 = (π/2 - 2 x2 tan α) m`, and the
mating space width carries the opposite sign. One space is bounded by two
involute flanks that narrow toward the root circle and is closed by the root
arc; toward the bore the space opens into the central hole, which is cut at the
tip diameter.

The representation is `nominal`. When the tip circle lies inside the base
circle (small tooth counts), the involute is extended radially to the tip and
the report carries `gear_internal_tip_below_base`. A pinion-cutter (долбяк)
envelope, its protuberance, and the real generated root remain a separate
`generated_exact` block; the module does not claim them. Root-fillet metadata
from the contour is reported, not generated.

## Measurements

The report carries the controls that GOST 19274-73 defines for the wheel:

- span length measured across the internal tooth spaces; the contact radius
  must stay between the tip and root circles;
- constant chord `s_c2 = (π/2 cos²α - x2 sin 2α) m` and its height;
- chordal tooth thickness at the reference circle;
- normal tooth thickness and base pitch;
- over-pin size for spur gears, with the pin in the tooth space:
  `inv α_D2 = inv α + D/(m z cos α) - π/(2 z) - 2 x2 tan α / z`,
  `d_D2 = d cos α / cos α_D2`, `M2 = d_D2 - D` for even `z` and
  `M2 = d_D2 cos(π/(2 z)) - D` for odd `z`.

Over-pin control is **not performed** for helical internal gears; the standard
excludes it, and the report says so instead of showing a number.

## CAD plan

`build_internal_gear_plan` produces a create-only numeric plan:

1. a ring blank cylinder with the explicit outside diameter and face width;
2. a central bore at the internal tip diameter, cut with a full-rotation
   rectangular profile around the gear axis;
3. one internal tooth-space sketch: an involute flank spline per side, bore
   closure segments and arc, and the root arc;
4. a through-all cut (or a helical cut evolution for `β > 0`);
5. a circular pattern of the space cut, `z` instances over 360°.

The expected volume is the analytic ring section: outer disc minus the tip
bore minus `z` tooth spaces, multiplied by the face width. The bridge verifies
one positive-volume solid, the expected bounds `[-b, -D/2, -D/2, 0, D/2, D/2]`,
the pattern count, and the relative volume error against the plan before the
part variables and the checksummed recipe are written.

## Verification

The live acceptance cases are stored under `experiments/spikes/`
(local, ignored):

- internal spur gear `m2 z40`, ring `D100 × 20`: one solid, relative volume
  error 0.013 %, save/reopen returns the verified recreatable block;
- internal helical gear `m2 z40`, `β = 20°` left, ring `D100 × 20`: one solid,
  relative volume error 0.006 %, save/reopen returns the verified recreatable
  block.

These checks cover the solid, its bounds, the physical tooth count and the
managed-block recipe. They do not certify the pinion-cutter root shape,
strength, or the mesh with a mating gear.

## Studio and MCP

Studio exposes the module under **Механические передачи → Зубчатые передачи**;
the end view shows the full ring with internal teeth and the `D`, `d`, `d_a2`,
`d_f2` dimensions, and the side view shows the ring width with the bore window.
The persisted block is read-only and recreatable from its recipe.

MCP tools:

- `preview_internal_gear` — Layer 2 analysis, no COM;
- `create_internal_gear` — plan with `execute=false`, write only with
  `confirm_write=true`;
- `inspect_internal_gear` — read the managed block and its recipe.

## Out of scope

Hub, keyway, retaining rings, housing, end chamfers, internal herringbone
teeth, gear pairs and meshing synthesis, generated-exact pinion-cutter roots,
and strength or lifecycle calculations are separate modules. Applying the
internal teeth to an arbitrary pre-existing body is also outside this slice:
the module creates its own ring blank.
