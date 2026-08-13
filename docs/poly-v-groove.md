# Poly-V groove profile, preview, and CAD builder

Status: Layer 2 ISO catalog/preview and the focused Layer 3 cut-from-body builder
are implemented and live-verified in KOMPAS-3D for PH, PJ, PK, PL, and PM. The
user-facing Layer 4 pulley workflow is defined to create and own a new blank;
applying grooves to an arbitrary existing body is not a supported product
workflow.

The module owns only the functional Poly-V rim geometry. It does not create a
hub, bore, keyway, thread, chamfer, belt body, route, or rating calculation.
Poly-V remains a separate family from the straight-sided V-belt module.

## Public MCP tools

The request schemas reject unknown fields.

### `list_poly_v_profiles`

Lists the five built-in ISO 9982:2021 pulley profiles and their provenance.

### `resolve_poly_v_profile`

Resolves one `PH`, `PJ`, `PK`, `PL`, or `PM` record.

### `preview_poly_v_groove`

Required inputs:

```text
designation         PH | PJ | PK | PL | PM
effective_diameter  de, mm
groove_count        1..64
```

The JSON-compatible result includes the normalized catalog record, checking,
outer and root diameters, face width, groove centers, exact line/arc entities,
one closed operation profile, expected removed volume, target-body requirements,
assumptions, warnings, and source metadata. Preview does not access COM.

### `apply_poly_v_grooves`

Preflights or creates one managed rotational cut in an existing cylindrical
blank. It defaults to `execute=false`; writes require both `execute=true` and
`confirm_write=true`.

The target contract requires:

- an exact open `document_id`;
- one top-part solid body;
- `axis=global_x`;
- outer diameter equal to the previewed `do`;
- an axial interval containing the complete previewed face width;
- the blank's outer-radius and face-width operation-variable names.

The operation does not save the document. Save explicitly after validating the
returned execution evidence.

This tool remains the internal Layer 3 composition primitive and a focused
acceptance surface. Geomwright Studio and the Layer 4 pulley family create a
known parameterized blank first, then invoke this builder with the blank's
semantic dimensions and variable links.

## ISO 9982:2021 catalog

Dimensions are millimetres. Every profile uses `α = 40° ± 0.5°`; cumulative
pitch deviation between the first and last groove is limited to ±0.3 mm.

| Profile | Pitch `e` | Pitch tol. | `rt` nominal | `rt` tol. | `rb` max | Checking `dB` | `2x` nominal | `2N` max | `f` min |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PH | 1.60 | ±0.03 | 0.25 | ±0.05 | 0.30 | 1.00 | 0.11 | 0.69 | 1.30 |
| PJ | 2.34 | ±0.03 | 0.30 | ±0.05 | 0.40 | 1.50 | 0.23 | 0.81 | 1.80 |
| PK | 3.56 | ±0.05 | 0.35 | ±0.10 | 0.50 | 2.50 | 0.99 | 1.68 | 2.50 |
| PL | 4.70 | ±0.05 | 0.55 | ±0.15 | 0.40 | 3.50 | 2.36 | 3.50 | 3.30 |
| PM | 9.40 | ±0.08 | 0.90 | ±0.15 | 0.75 | 7.00 | 4.53 | 5.92 | 6.40 |

Source: ISO 9982:2021, clause 5.1, Figures 1/2 and Table 2;
[official ISO record](https://www.iso.org/standard/82249.html). The public
standard preview was retrieved on 2026-08-11. Certified drawings must be checked
against a licensed copy of the applicable edition.

## Deterministic geometry policy

ISO permits a bounded range of tip configurations and leaves the groove-bottom
configuration below `rb` optional. A CAD generator therefore needs an explicit
nominal policy. This module selects:

```text
tip transition radius = tabulated nominal rt
root radius           = tabulated maximum rb
edge distance         = tabulated minimum f
```

These choices are reported in `assumptions`; they are not presented as the only
ISO-compliant configuration.

Coordinate convention:

```text
x = pulley axial direction
y = radius from pulley axis
θ = α / 2 = 20°
c = 1/sin(θ) - 1
```

For checking diameter over balls or rods `K`:

```text
K  = de + 2x
do = K - 2N
```

The selected rounded geometry determines its actual `2N`:

```text
2N = dB/sin(θ) + dB - e/tan(θ) + 2*rt*c
```

Preview rejects the profile if this exceeds the tabulated `2N maximum`. The
outer diameter follows directly:

```text
do = de + 2x - 2N
```

The rounded radial depth is:

```text
depth = e/(2*tan(θ)) - (rt + rb)*c
root_diameter = do - 2*depth
```

Each groove wave is built in this order:

```text
half tip-transition arc
left tangent flank
root arc
right tangent flank
half tip-transition arc
```

Adjacent grooves share the same tip point, so the functional wave is continuous.
For `n` grooves:

```text
face_width = (n - 1)*e + 2*f
```

Groove centers are symmetric about the requested `axial_center`.

## CAD operation profile

A closure line placed at `do/2` would pass through every intermediate tip. That
creates a non-simple region even though the functional wave itself is correct.
The executable profile therefore adds two bounded radial lines and closes above
the blank by:

```text
overshoot = max(0.10 mm, 0.05*e)
```

This overshoot exists only in empty space and is clipped by the target body. It
does not alter the final rim. The operational sketch contains one simple closed
component rather than touching per-groove cells.

The profile is a dimension-driven master/dependent sketch; only the two global
axis endpoints are fixed. Groove 1 owns the driving pitch, transition radius,
root radius, and left-flank angle. Its two flanks have equal length. Every other
groove inherits equal pitch length and radii plus parallel flanks. All four
line/arc joins in every groove are tangent, and construction centerlines keep the
set symmetric about `PV_CENTER`. The bridge requires `ConstraintsState=2` after
the staged parameterization and rebuild.

The eight driving dimensions are:

```text
blank face width       PV_FACE_W
blank outer radius     PV_OR
groove-set center      PV_CENTER - PV_AXIS_X0
master pitch           PV_E
master tip radius      PV_RT
master root radius     PV_RB
closure overshoot      PV_CLOSURE
master flank angle     90 - PV_ALPHA/2
```

Part variables retain both the drivers and the derived ISO/composition values:

```text
PV_DE, PV_DO, PV_OR, PV_ROOT_D, PV_DEPTH, PV_CLOSURE
PV_E, PV_F, PV_FACE_W, PV_RT, PV_RB
PV_DB, PV_2X, PV_2N, PV_ALPHA, PV_COUNT, PV_CENTER, PV_AXIS_X0
```

`PV_OR` and `PV_FACE_W` link to the target blank's declared operation variables.
The current generic stepped-shaft blank uses `PV_OR=D1/2` and `PV_FACE_W=L1`.
`PV_COUNT` records the discrete generated family size; changing the number of
grooves still requires regenerating the sketch.

The nominal `rt` and selected `rb` remain tangent arcs in the operational sketch.
They are two independent, profile-forming ISO values, so a post-cut edge fillet
or full-round feature would obscure the dimensional contract and introduce
topology-dependent edge selection. Keeping the arcs in the sketch lets `PV_RT`
and `PV_RB` rebuild the profile directly.

When operation variables are changed through direct COM automation, settle the
solver with `Sketch.Update()`, one `BeginEdit()`/`EndEdit()` cycle, another
`Sketch.Update()`, and `RebuildDocument()`. The managed creation path already
uses this staged settle sequence.

## Model-tree names

Layer 2 owns exact English names and the bridge applies them verbatim:

```text
Poly-V grooves {designation} x{count} profile
Poly-V grooves {designation} x{count} cut rotation
```

An optional `name` is appended as a semantic suffix. Run labels, timestamps, and
file names do not belong in the model tree.

## Execution verification

The bridge checks:

1. exact document resolution and activation;
2. one 3D top-part body before execution;
3. matching target diameter, axial interval, axis, and parameter-base links;
4. one exact sketch-arc profile component;
5. all planned constraints applied and `ConstraintsState=2`;
6. valid rotational cut and successful rebuild;
7. unchanged body count and decreased volume;
8. actual removed volume within 5% of the sampled analytical revolution;
9. exact model-tree names and hidden operational sketch, with a warning if
   hidden-state readback cannot be confirmed;
10. save/reopen validity in the acceptance workflow.

The body readback reactivates and rechecks the target document immediately before
API5 volume inspection. This prevents a long operation from validating a
different document if the active KOMPAS window changes during execution.

## Live acceptance matrix

Ignored local artifacts and the readback manifest are under
`sample/live_outputs/`. The verified manifest is
`final_poly_v_examples_verified_2026_08_11_173947.json`.

| Profile | `de`, mm | Grooves | `do`, mm | Root diameter, mm | Face width, mm | Reopened arcs | Relative volume error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PH | 40 | 4 | 39.620257 | 37.340478 | 7.4 | 12 | 0.01587% |
| PJ | 80 | 6 | 79.619108 | 75.883337 | 15.3 | 18 | 0.01217% |
| PK | 120 | 5 | 119.614846 | 113.104293 | 19.24 | 15 | 0.00727% |
| PL | 180 | 4 | 179.423644 | 170.165728 | 20.7 | 12 | 0.00158% |
| PM | 350 | 3 | 349.426809 | 329.949076 | 31.6 | 9 | 0.00158% |

Every reopened sketch had one closed component, zero gaps, branches, or sampled
self-intersections, and `ConstraintsState=2`. Every model retained one valid
body and one valid named rotational cut.

A separate mutation/reopen check changed an existing PH model from
`PV_E=1.60`, `PV_RT=0.25`, `PV_ALPHA=40` to `PV_E=1.62`, `PV_RT=0.27`,
`PV_ALPHA=39`. After rebuild and reopen, all eight tip-transition arcs read
`0.27 mm`, the three measured root-center intervals read `1.62 mm`, all four
root arcs remained `0.30 mm`, and all eight flank inclinations changed from
`70.0°` to `70.5°`. The contour stayed closed, the cut stayed valid, and the
sketch remained `ConstraintsState=2`.

## Explicit limitations

- only the ISO 9982:2021 PH/PJ/PK/PL/PM nominal catalog is implemented;
- tolerances are reported but no tolerance-stack or manufacturing allowance is
  synthesized;
- the deterministic maximum-`rb` root is one valid policy, not a claim that all
  compliant pulleys must use it;
- only one global-X cylindrical top-part body is supported;
- target diameter and axial span are caller-declared and checked against the
  plan, not independently measured from arbitrary B-Rep;
- continuous profile dimensions are live variables, but changing the discrete
  groove count requires regeneration rather than an in-place sketch edit;
- no full pulley, belt, route, tension, power, life, or strength calculation is
  included;
- failed writes may leave unsaved partial geometry in the target document; retry
  from a clean/reopened disposable file.

The JSON preview/plan/result boundary is intentionally suitable for a future
`DesignRecipe` UI layer, but no external UI or new shared schema is introduced by
this module.
