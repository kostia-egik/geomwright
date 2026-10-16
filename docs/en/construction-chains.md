# CAD module construction-chain plan

[Русский](../ru/construction-chains.md) · [Index](README.md) · [Architecture](../../ARCHITECTURE.md)

> Agreed direction as of 2026-10-11. The first shaft chain in stages A–C is
> implemented within the limits below; Stage D (initial gear foundation and saved-chain
> continuation) is also live-verified. Stage E now includes polygon sections;
> flat sections, bolt-circle holes, an initial straight spline shaft and terminal
> external metric threads, plus bounded terminal spline cuts on an explicit uncut
> input cylinder and full-through internal cuts on one cylindrical stock/bore.
> Explicit blind spline-hub cuts in a flat-bottom bore are also verified; arbitrary
> partial spans and broader input-stock modes remain roadmap work. A chain builds one part
> from existing modules in a shared KOMPAS document. The first stage is MCP-only:
> prepare a blank or resolve an input region, perform the functional operation,
> pass anchors onward and verify the result. Broader plan requirements do not imply
> additional API capabilities beyond the implemented interface below.

This document guides developers and agents adapting existing generators.
Actual capabilities remain in the registry and family contracts. It defines
scope, requirements and sequencing. `get_construction_chain_contract` returns
the current public schemas.

## Available MCP interface

`get_construction_chain_contract` describes inputs and limits.
`run_construction_chain` accepts `action=plan|create|inspect|rebuild|continue`.
Planning never accesses CAD; creation requires `confirm_write=true` and saves
a new part. `inspect` recognizes the recipe in an exact opened `document_id`,
without claiming a fresh geometry audit. `rebuild` reads that recipe and creates
a new part, preserving its source. Use ordinary `create` for modified inputs.
`continue` requires `confirm_write=true`, an exact opened saved chain document and
a recipe containing only new steps; it appends and saves the same selected file.

Supported modules are stepped shaft, external cone, axial cylindrical bore and
face ring groove, regular polygon/flat sections and bolt-circle holes, plus initial
`gear_spur` and `straight_spline` foundations (`own/create`), plus terminal
`straight_spline` input/remove on an explicit uncut cylinder.
Rotational constructors use `own/create` first and `own/add` thereafter;
cuts use `input/remove` with an explicit earlier `target`. Placement supports
coaxial ±X, axial offsets and phase 0. Placement is numeric and recreate-only;
inter-module driving expressions are not supported. Additions attach at an
exposed axial end without overlap.

Example `run_construction_chain` call:

```json
{
  "action": "create", "confirm_write": true,
  "chain": {"name": "Shaft with cone", "steps": [
    {"id": "shaft", "module": "stepped_shaft", "basis": "own", "material": "create",
     "parameters": {"steps": [{"length": 20, "diameter": 40}, {"length": 15, "diameter": 30}]}},
    {"id": "cone", "module": "external_conical_step", "basis": "own", "material": "add",
     "parameters": {"definition_mode": "diameters_length", "start_diameter": 30, "end_diameter": 20, "length": 12},
     "placement": {"reference": {"step": "shaft", "anchor": "end"}}},
    {"id": "bore", "module": "internal_cylindrical_step", "basis": "input", "material": "remove", "target": "shaft",
     "parameters": {"steps": [{"length": 35, "diameter": 10}]},
     "placement": {"reference": {"step": "shaft", "anchor": "start"}}},
    {"id": "groove", "module": "face_ring_groove", "basis": "input", "material": "remove", "target": "shaft",
     "parameters": {"inner_diameter": 20, "outer_diameter": 30, "depth": 2},
     "placement": {"reference": {"step": "shaft", "anchor": "start"}}}
  ]}
}
```

Use the same inputs with `action=plan` for preflight.
Read with `{"action":"inspect","document_id":"<result identifier>"}`;
rebuild with `{"action":"rebuild","document_id":"<result identifier>","confirm_write":true}`.

Live KOMPAS verification confirms one 47×40×40 mm solid, volume
38.170350741 cm³ and four fully defined sketches. Reverse direction with an
offset, independent repeated blocks, macro grouping, rebuild, save/reopen and
ungroup were checked. Each macro contains only its own sketch and operation;
recipe/root references retain identity after ungrouping. Changing the first
repeated block's diameter leaves the second variable unchanged. This does not
certify arbitrary manual edits to the entire chain.

The executor checks the current final body, radii, axial spans, volume and
material delta after each step. Incompatible inputs fail before CAD. Errors
retain the partial document and last verified step, without retry. Checksummed
metadata is bounded; its budget can limit step count before the maximum 32.
Nonzero groove wall angles are host-planned; current live chain acceptance
covers straight walls.

### Stage D: gear foundation and saved-chain continuation

The initial `gear_spur` uses the registered family plan and its mathematical C2
interpolating flank splines, with explicit native order 4 and single interior
knots. Root transition and involute remain separate curves at the form point;
C2 does not imply continuity across that theoretical join. The previous order-3
payload silently reset native knots; the subsequent repeated-knot Bézier workaround
fragmented the faces. The corrected interpolation retains the same deviation cap
and produces smooth native PNGs. See the [gear contract](../gear-spur.md).

The gear starts at origin 0, direction +1, with native interval `[-b, 0]`.
Its processing carrier is the solid root core, not the teeth. Cylindrical hubs
use `stepped_shaft` at the exposed +X end; a continuous rim/hub bore uses two
explicit nonoverlapping cuts. Subsequent rotational steps support ±X and phase 0
within their placement limits; this does not permit a relocated/reversed gear base.
Host discovery exposes family profile parameters, but live chain acceptance covers
only `m2 z20 x0 b20`, spur without tip chamfers. Helical/chamfer variants are
host-planned, not live chain-certified.

Live KOMPAS evidence confirms a root-core radius of 17.5 mm, 100 tooth-zone faces
(`tooth_zone.face_count`), a Ø24×12 mm hub and continuous Ø10 mm bore.
The four-step chain has one body and volume 27.53642813 cm³. Appending a face
groove (ID 14, OD 20, depth 2 mm) at the hub end in direction −X preserves all
four earlier steps, saves the same file and yields 27.21598568 cm³. Save/reopen
readback confirms the appended recipe and geometry.

Example continuation of that saved chain (the `hub` ID must already exist):

```json
{
  "action": "continue", "document_id": "<exact opened saved chain ID>",
  "confirm_write": true,
  "chain": {"steps": [
    {"id": "hub_groove", "module": "face_ring_groove", "basis": "input",
     "material": "remove", "target": "hub",
     "parameters": {"inner_diameter": 14, "outer_diameter": 20, "depth": 2},
     "placement": {"reference": {"step": "hub", "anchor": "end"}, "direction": -1}}
  ]}
}
```

Do not resend or edit old steps. An optional chain `name` labels the combined
recipe; it does not authorize renaming existing native roots. Inside the bounded
write job, continuation rereads the full saved envelope and audits the immutable
prefix, ownership, native gear profile, current final geometry and carriers before
writing. Changed old geometry/parameters are refused. Arbitrary standalone models
cannot be continued. Recipe recognition by `inspect` is not this geometry audit.

API7 `GetObjectId`/`FindObjectById` recover roots and macro-elements after reopen:
runtime `Reference` numbers can change. Saved IDs and ownership, not name-only
guessing, establish identity. Continuation still checks canonical names strictly;
arbitrary manual renames are not accepted as a supported workflow. Reused recipe
slots explicitly update `.Value` and `.Note`, then verify decoded metadata.
Failures retain partial-document evidence; there is no rollback or automatic retry.

### Native PNG review

Use the separate [image export tool](../low-level-runtime.md#model-png-export)
after a completed build or continuation:

```json
{"document_id":"<exact opened document ID>","view":"left","resolution_dpi":150,"fit":true}
```

These are `export_model_png` arguments. Native `left` can show the side rather
than the end of a global-X model; inspect an isometric view for holes and grooves.
The actual raster was visually reviewed, not inferred from export success.
Export does not rebuild or edit geometry; matrix/scale and previous activation are
restored and checked, but exact screen pan is not certified.

Nonzero angular phase, broader thread modes, arbitrary partial spline-hub spans/input stock
and Studio integration remain excluded.

### Stage E: bounded spline cut on an input shaft

Use `straight_spline`, `basis=input`, `material=remove` as the sole terminal cut.
The prefix must contain only uncut shaft/cone constructors; `target` selects one
explicit single-cylinder +X `stepped_shaft` section at spline D. Placement references
that target's `start`, with a positive `offset_mm`; `length_mm` must leave positive
smooth stock at the far end too. Set `include_tip_chamfer=false`. No hub, open ends,
tool runout, reverse placement, prior cuts or subsequent steps are supported.

For a Ø40×50 carrier, a standard request is `series=light`, `designation=8x36x40`,
`length_mm=20`, `include_tip_chamfer=false`, placed at offset10: working X=[10,30].
Standard and explicit custom dimensions use the existing exact family contour.
Length drives native finite Distance1; the cross-profile and placement are numeric
and recreate-only. The saved `spline_audit` binds original inputs, protected stock,
root IDs, exact profile and full inventory. Copies are linked to native array
exemplars; ID-less coordinate records use a separate structural policy, not invented ownership.

Create, continue from a separately saved/reopened shaft, fresh inspect after actual
close/reopen and source-preserving rebuild passed on this standard example. A custom
z8/d35/D40/b6/r0.3 cut also passed create/reopen. Continue preserved prior root IDs;
rebuild preserved source bytes. Inspect this terminal mode performs a fresh
geometry/ownership/driver audit at creation inputs. The standalone internal-sector
defect is fixed by hub profile revision2 (nominal shaft-tooth complement).
Initial spline foundations are unchanged.

### Stage E: through or blind internal splines on an input hub

Use the same terminal `straight_spline` input/remove step with `body=hub`.
The prefix is exactly one +X cylindrical `stepped_shaft` stock and its explicit
full through `internal_cylindrical_step` bore at d. `target` selects that bore;
placement references its start with zero offset and `length_mm` equals its entire
length. Set `include_tip_chamfer=false`. The outside diameter is inherited from
stock and recorded in the normalized recipe; a conflicting explicit value is
rejected. No default-wall heuristic or implicit bore resizing is applied.

Example: Ø55×20 stock, Ø36×20 through bore, `series=light`, `designation=8x36x40`,
`body=hub`, `length_mm=20`. Native six-entity revision2 geometry is reused without
another blank or bore. Cut length links to the existing bore-length driver.
The full outer cylinder is protected; end annuli change intentionally. Audit
min/max working radii, exact source/all removal and full inventory independently.

Standard create, continue from a separately saved/reopened bore, inspect after
actual reopen and source-preserving rebuild passed. Custom z8/d35/D40/b6/r0.3
create/reopen passed, and the previously saved external spline passed a fresh
regression audit. Omit `exit_mode` or use `through` for this unchanged contract.

Explicit `exit_mode="blind"` uses a flat-bottom bore shorter than the stock and
a working length shorter than the bore depth. Start at open entry with zero
offset; require positive smooth tail before the bottom and stock behind it.
Example: Ø55×30 stock, Ø36 bore depth25, `8x36x40`, `body=hub`, `length_mm=20`,
`include_tip_chamfer=false`: smooth tail5 and bottom stock5. The finite cut length
has an independent native driver, not a link to the immutable bore-depth driver.
Audit the outer wall, original bottom/rear disks, smooth-tail cylindrical witnesses,
flat terminal faces, exact source/all removal and complete inventory separately.
Standard create/continue/rebuild/actual reopen, custom create/reopen and native
length20→22→20/save/reopen with original checkpoint restoration passed. Previously
saved through-hub and external-spline recipes passed fresh regression audits.
Arbitrary partial/interior spans, extra stock sections, later steps and arbitrary
input bodies remain excluded. Flat numeric termination is not tool runout,
manufacturing functional-length certification or a tolerance-stack certification.

### Stage E: terminal external metric thread

`external_helical_thread` is supported as the last input/remove step. Select an
explicit +X cylindrical `stepped_shaft` target and its start with zero offset.
Inputs are `diameter`, `pitch`, `length` and `direction` (`right`/`left`); the
diameter must match the target. The profile uses an automatic round root and
2–64 turns. Prior stock must be rotational and uncut; entry-side stock must be
strictly behind the start and inside the thread root core.

Optional `entry_mode="through"` names this free-face/root-clear entry condition.
Optional `exit_mode="blind"` ends the cut at `start + length`, before the actual
carrier end, with a strictly positive smooth tail. Rotational exit-side stock,
including a larger shoulder, is protected. `length` is the last-cut-trace span,
not a certified functional full-profile length. For example, a Ø20×20 carrier
with `length=18`, `pitch=2.5` leaves a 2 mm tail; the terminal section projects
over 2.1875 mm. The audit returns this projection, last trace and smooth tail.
There is no controlled gradual runout or exit groove.

`exit_mode="through"` instead requires length to match the entire carrier. The
exit is a free face or adjoining rotational stock strictly inside the root core;
a larger exit shoulder is refused before writing. The cutter's terminal section
is placed outside the carrier so both outer boundaries and both root-tangent
boundaries reach the end. The audit requires all four full-span witnesses and no
material terminal section. Its virtual cutter projection is explicitly marked
as planned, not measured material geometry or a functional-thread certificate.

Omitting the ending fields preserves the legacy recipe and complete exposed
carrier behavior: length must match the target and all other stock must be
behind its start inside the root core. This is not an alias for explicit through
exit: legacy one-witness coverage and cutter placement stay unchanged. Blind entries,
arbitrary internal starts, other families and any later step are unsupported.

The existing family executor cuts the current stock without recreating it, owns
seven new roots and groups only those roots. The plan returns null for predicted
thread delta/total volume: a saved native checkpoint records actual volume and
protected-face evidence. Inspect freshly verifies ownership, whole root inventory,
span/depth, protected material and drivers at creation inputs. Changed native
drivers must be restored; use a new recipe/create for changed inputs.

Live M20×2.5 evidence on Ø12×12 + Ø20×20 covers left-hand saved-file continuation,
actual reopen/fresh inspect and source-preserving rebuild into a new part, plus
right-hand creation and actual reopen/fresh inspect. The first stopped
stock prefix was audited, saved and continued rather than recreated. Read-only
sketch inspection uses an exported fragment and preserves code1/dirty state.
Old pending diagnostic copies remain unsupported and are not promoted. Geometry
evidence is sampled/analytical, not exact BREP or a manufacturing certificate.
The blind variant is live-verified on Ø12×12 + Ø20×20 + Ø30×12: left creation,
right saved-file continuation, actual reopen/fresh inspect, and left rebuild into
a new part with the source unchanged. Endpoint characteristics are bound to the
saved native checkpoint; inspect verifies them at creation inputs.
The explicit through variant is live-verified for left creation with a Ø12×12
exit neck, right saved-file continuation at a free face, actual reopen/fresh
inspect and left source-preserving rebuild. Carrier and thread are Ø20×20,
M20×2.5; both cases retain the Ø12×12 entry neck.
The other Stage E families and broader future requirements below remain the agreed roadmap.

### Stage E: terminal internal metric thread

`internal_helical_thread` is supported as the last input/remove step, targeting
the explicit `internal_cylindrical_step` bore, not the outside cylinder. The prefix
must contain exactly one single-cylinder `stepped_shaft` and one cylindrical
bore on +X, sharing the stock start. Through exit requires identical
complete spans; blind exit accepts a through bore or a shorter flat-bottom bore.
Place the thread at the bore start,
with zero offset and direction +1. No other cuts or later operations are accepted.

Inputs are nominal major `diameter`, `pitch`, `length` and
`direction` (`right`/`left`). `method_version=1`, `entry_mode="through"` and
`exit_mode="through"|"blind"` are stored explicitly; through remains the default.
Through length equals the full bore depth. Blind length is the distance from entry
to the last cut trace and must be strictly shorter than the bore depth.
The existing bore remains immutable. Nominal diameter must exceed
the bore diameter and leave a positive wall to the outside cylinder; the automatic
round contour must fit the pitch. Cost is bounded to 2–64 turns.

For M20×2.5, a Ø36×20 blank with a Ø17.29367061317363×20 through bore is the verified
example. The round cutter separates actual cut depth from its virtual flank apex.
Native verification requires two bore-radius and two root-tangent boundaries over
the full span, maximum cut radius matching nominal diameter, positive removal
within the inner shell, no material terminal section and an unchanged outer
cylinder. Only seven new thread roots are grouped; prior roots stay outside.

Blind example: M20×2.5 with `length=18`, `exit_mode="blind"` in the same depth20
bore inside a Ø36×24 blank. Last trace is18, the partial terminal section projects
over [16.22916667,18], the gap to bottom is2 and stock behind the bottom is4 mm.
The audit protects the outer cylinder, bottom disk and rear disk; the checkpoint
binds gap and thickness separately. A through bore instead protects its exit
annulus. Full-profile boundary coverage stops at the conservative projection end;
`length` is not a certified functional thread length.

Plans return null predicted thread delta/total volume. Saved checkpoints hold
measured volume, protected surfaces and persistent ownership. Inspect performs a
fresh geometry/root-inventory/driver audit at original recipe inputs. Private driver
experiments confirmed pitch2.5→2, diameter20→20.2 and restoration with the bore fixed;
this is not public in-place recipe editing or renewed standard conformity for the
changed pitch. For changed construction inputs, use a new recipe/create.

Public lifecycle evidence covers left create, actual reopen/fresh inspect and
source-preserving rebuild into a new part, plus right same-file continue and actual
reopen/fresh inspect. Old pending diagnostic files remain unsupported. Blind lifecycle
also passed left create/reopen/inspect/source-preserving rebuild and right same-file
continue/reopen/inspect in a flat-bottom bore, plus right create/reopen/inspect with
a blind ending inside a through bore. Drill points, controlled runout, grooves,
multi-section stock/bores and other families are excluded.
Geometry evidence is analytical/sampled, not a manufacturing or functional-length
certificate. The legacy standalone internal scenario is not silently changed.

### Stage E: regular polygon sections

`external_polygonal_step` reuses the existing family plan with `diameter`, `length`,
`side_count`, `diameter_mode` and `rotation_angle_degrees`. Shared placement owns
axial direction (global-X ±X), offset and the earlier start/end reference. Shared
phase remains 0; family profile orientation retains YOZ u→Z/v→Y semantics.
Use own/create initially or own/add at an exposed axial end. Gear foundations still
allow only cylindrical shaft hubs as additions.

The carrier is the solid inscribed core, not a cylindrical final surface. Bores and
face grooves must stay strictly inside it; corner/side finishing is unsupported.
Native verification matches lateral planes/spans, exact transverse bounds, volume
and fully defined sketches. Plane normals are not hash-quantized. Each macro owns
its origin point, parallel plane, sketch and extrusion; persistent native IDs
restore them after reopen.

Live evidence: D40/L20 shaft, incircle D30/L10 hexagon and D8 axial bore through the
hexagon; actual close/reopen followed by continue adds an ID12/OD20/depth2 end groove
along −X in the same file, preserving all three earlier steps. The four-step body
is 30×40×40 mm, 32.022191179 cm³ and passes another real reopen; native PNG was visually
reviewed. A separate incircle D32/L22 pentagon at 17 degrees, origin X=7/direction−1,
with D20/L8 shaft addition passes actual reopen at 22.972711712 cm³ and native state 1
for both sketches. This representative evidence does not certify every polygon
count, angle or manual edit. Broader thread and spline modes remain pending.

### Stage E: flats and bolt-circle holes

`external_flat_step` uses `diameter`, `length`, `flat_depth`, `flats_count=1|2` and
own/create or own/add at an exposed axial end. 0<F<D/2; D/L/F are native drivers.
Shared placement owns ±X and axial offset. The first flat lies at Y=−(D/2−F), with
the optional second flat on the opposite side. Core cuts use the inscribed solid
carrier. Actual lateral planes, trimmed cylinders, bounds and volume are verified.
Live evidence includes D30/L10/F4 one-flat reverse creation at X7 and D30/L12/F4
two-flat addition after a D40/L15 shaft with a D8 bore, including actual reopen.

`bolt_circle_holes` requires input/remove and an explicit constructor target.
Inputs: `hole_diameter`, `depth`, `bolt_circle_diameter`, `count=2..64`,
`start_angle_degrees`, `clockwise`. Count64 is a cost bound, not a standard.
Depth must stay inside that target; it is not automatically through the whole
part. Holes must not touch/intersect each other or the inscribed carrier boundary.
Prior cuts are checked using conservative radial exclusion envelopes; overlapping
rings are refused even when angular phases could separate them. A central bore
inside the free core is allowed before or after the pattern.

Diameter/depth/PCD/count are native drivers and angle step derives as 360/count.
Start angle and placement require recreation. The first centre uses genuine
coordinate-point inputs, not informational displacement outputs. Informational
or read-only operation variables cannot receive driving formulas. Verification
matches actual off-axis cylinder centres/radii/spans and removed volume, Count2/
Step2, source cut, axis and owned roots after reopen. Unnamed derived pattern
records exposed in Sketchs are not edited, hidden as independent roots, or grouped into the macro.

Live evidence: four D5 holes on PCD40 at 17 degrees in a D60/L12 foundation; a reverse
X7/direction−1 three-hole 31-degree clockwise chain with a central D8 bore; and
same-file continue of a saved shaft/flat/bore chain with four D3/PCD28/11-degree/
depth15 holes. All pass actual reopen. The continued four-step body is 24.959882103 cm³
and preserves its three earlier steps, fully defined sketches and native drivers.
This is representative geometry evidence, not exhaustive manual-edit certification.
An additional fresh flange D60/L12 + two-flat D30/L10/F4 + D8 bore + four D5/PCD40
hole chain passes PCD40→42 and count4→5 driver changes: actual centres move, five
holes are measured, and angle step derives to72degrees via `360 / CH_HOLES_N1`.
Restoring40/4 preserves the original recipe and38.432090521cm³ volume, with save
and actual reopen audit passed. This diagnostic driver proof adds no public editor.

### Stage E: straight spline shaft foundation

`straight_spline` reuses the [GOST 1139-80 family](../spline-straight.md) calculation,
catalog/custom-size inputs and exact segment/arc tooth-space plan. Only `body=shaft`
and initial `own/create` at origin 0/direction +1 are accepted; native span is
`[-length_mm,0]`. This is not an application to an existing shaft or a spline hub.
The family's through-all cut runs only while this new foundation exists; later
sections are appended after its native audit, without rebuilding the tooth cutter.

Further additions use `stepped_shaft` at the exposed +X end. The first appended
section stays entirely within the solid root-core radius so no tooth surface joins
or extends into it. Bore/groove targets use the solid core, never the teeth; a
continuous spline/shaft bore uses two explicit nonoverlapping carrier cuts.
Numeric tooth, blank and chamfer profiles remain recreate-only local exceptions,
with actual entity/direction, volume, bounds, source/pattern removal and persistent
root/axis/source checks. Family inputs and saved recipes are not CAD drivers.
After every step and saved-file continuation the sampled native lateral tooth-zone
fingerprint must match the audited foundation. End planes are excluded because
core holes and appended sections legitimately change them; this is not exact BREP
equivalence or a manufacturing tolerance. Existing fully-defined rules still
apply to subsequent rotational sketches. Inspect recognizes the recipe, not a
fresh geometry audit. Hub splines, arbitrary foundation placement and old-step
editing remain unsupported.
Tip chamfers must neither meet nor enter the solid root core; these cases fail in
host planning before CAD. Nominal geometry is not a standard-conformity or machining claim.

Live reference: light `8x36x40`, length 30 mm, inner-diameter centering and standard
tip chamfers; appended Ø30×12 shaft and continuous Ø10 bore (two carrier cuts).
The four-step solid is 39.095903060 cm³. After actual reopen, continue adds an
ID14/OD22/depth2 end groove along −X in the same file: five steps, 38.643513718 cm³.
Another actual reopen confirms roots, recipe and all 56 preserved lateral tooth
faces; isometric and rear PNGs were visually reviewed. Representative acceptance
does not certify arbitrary catalog sizes or manual edits.
Fresh MCP also creates a custom `z8/d35/D40/b6/r0.3`, length20, no-chamfer foundation
with a Ø20×8 cylindrical continuation: 24.169923525 cm³, 40 preserved tooth faces,
actual reopen and visually reviewed PNG. Rebuild of the five-step standard chain
creates another file and preserves the original file bytes, then passes actual reopen.

Sections 1–9 retain the accepted full design and transition requirements. Read
them against the implemented scope above, not as a second runtime capability list.

## 1. First-stage scope

Prioritize shafts, hubs, gear rims and similar parts with a shared primary axis.
One sequence works in one document and retains one final body. Start with creating
a chain; introduce continuation in an explicitly selected existing document after
the first end-to-end build has passed verification.

The initial structure is an ordered list of steps referencing earlier results only.
No new CAD engine, universal graph, rule engine or separate database is needed.
Reuse existing family calculations, plans, executor and recipe metadata.

Studio, assemblies, arbitrary multibody models and safe branch replacement are
outside the first stage. Springs retain standalone part creation. MCP-only
integration is an intermediate deliverable, not a complete module under the
[development rules](module-development.md). Shared logic remains independent of
Studio and suitable for its later integration.

## 2. Baseline and classification

The legacy `workflow` already builds in one new document and passes references
between steps. The common `run_cad_module` supports `preview|plan|create|inspect`,
but not application to an existing body. Family plans use the shared low-level
executor, whose operation set is broader than the public workflow's.

Important limitations: public workflow normalization rejects thread steps;
some cuts using `source_scenario/source_params` recreate their source geometry.
That blank stays in the model; it is not an automatically removed temporary body.
An executor branch alone does not establish MCP support.

| Family | Geometric role | Adaptation concern |
| --- | --- | --- |
| Springs | Complete parts | Exclude from the first shaft chain |
| Cylindrical blank, stepped shaft | Base and added sections | Separate document lifecycle from geometry; verify joining |
| External cone, polygon | New sections or material addition | Confirm placement and interaction with the shared body |
| External section with flats | Pre-shaped section | Currently creates the section; machining flats on an existing cylinder needs a different cut |
| Internal cylindrical, conical, polygonal and flat-sided sections | Material removal | Replace source reconstruction with an explicit input reference |
| Face ring groove, bolt-circle holes | Material removal | Explicit target rather than an implicitly existing body |
| Native thread | Surface designation | Do not count it as physical material removal |
| Physical thread | Cylinder or bore processing | Extract application without creating the source section |
| Gears, sprockets, pulleys, cam | Functional part bases | Initially use as the first block; do not promise processing of an arbitrary blank |
| Straight-sided splines | Shaft or bore-region processing | Terminal input-shaft, through input-hub and bounded flat-bottom blind input-hub cuts implemented; broader processing remains pending |
| Points, axes, LCS, planes, sketches, patterns | Anchors and supporting steps | Explicit inputs, outputs and ownership |

This is an initial classification, not a readiness table. Before adaptation,
record a capability profile for each selected family with two independent assessments:

- **Compliance with current rules:** checked against current criteria, partial
  integration, or legacy with specific refactoring needs and verification gaps.
- **Chain capabilities:** source modes, material effects, placement, independent
  naming, readback, persistence and change behavior.

A modern create-only module is not necessarily chain-ready. A new MCP adapter
does not modernize a legacy generator. Shaft, cone, polygon and flat-section
adapters retain legacy builders; their corrections and verification must not be
lost when moving to shared execution. A keyway belongs to separate development,
not integration of an already available module.

## 3. Two ways to obtain the base

For functional processing that needs both options:

1. **Owned blank:** calculate and create the required section, then process it.
2. **Input region:** resolve existing geometry, check suitability, then perform
   the same functional processing.

Do not duplicate processing calculations. Creating a blank inside a chain does
not create a new document. A standalone part-creation tool remains a wrapper
around the same construction.

Source mode and material effect are separate decisions. A step declares only
supported actions: create a body, add material, remove material or add a
designation. Joining must retain one final body; disconnected sections are
refused rather than silently leaving a second body.

Do not require both modes from every family. Declare owned-branch editing
separately: application to an input body does not imply editing support.

## 4. Region data and step dependencies

Pass a selected working region, not just a body. The minimum contract is:

| Data | Purpose |
| --- | --- |
| Step identity, module version and semantic reference | Recover a dependency independently of tree labels |
| Current body, region and required surfaces | Unambiguous processing target |
| Origin, directed axis and angular reference | Complete placement, including phase |
| Region boundaries, usable length, shape and dimensions | Check cylinder, cone or bore suitability |
| Required input and derived parameters | Planning and explicit driving dependencies |
| Owned operations, variables and verification status | Readback and diagnostics |

Processing parameters and base dimensions are distinct. A nominal thread size
does not substitute for the required carrier diameter; external and internal
splines have different preparation requirements. Calculate an owned blank from
family requirements. Validate an input region and report required versus actual
values on mismatch. Never silently resize an earlier step: preparation or a
parameter dependency must be explicit.

A fixed value, a linked parameter and a geometric attachment are distinct inputs.
Copying a number does not create a dependency. Simple links use KOMPAS driving
expressions; numeric profiles may require recalculation. Do not introduce a new
global `EntitySpec` merely for chains; extend suitable existing structures and
describe legacy adaptation explicitly.

A reference means “this step's section end,” not a permanent COM number.
After joining, rebuild or reopen, resolve the body and necessary faces again.
Ambiguous resolution stops the write. Planned data assists preflight but does
not replace targeted checks of the actual base after manual edits or reopening.

## 5. Placement and independent naming

Represent placement internally as an origin and a right-handed orthonormal basis.
The user or agent selects an earlier anchor, the new section's own attachment
point, offset and phase. The offset frame is explicit; reflection is not hidden
in a sign change. Connecting points, axes and planes are ordinary steps when needed.

An LCS is a candidate native mechanism, not proof of correct placement.
Current modules differ in axial interval signs and sketch-local coordinates.
Sketch LCS, plane and operation axis can be assigned separately. A common
`global_x` label does not establish compatibility.

The current verified placement set is a shared axis, axial offset, both directions
and phase 0; nonzero angular phase is a future requirement. Before claiming arbitrary orientation, check translation and
rotation of a revolution, polygon extrusion and helical processing. Apply
`CS-002`, `CS-003` and `VERIFY-001` from [CAD patterns](../../CAD_PATTERNS.md).

Each step instance receives a stable namespace for variables and objects.
A display label is not identity. Matching dimension names do not create links;
cross-module expressions are explicit. Preserve canonical operation descriptors
under `OP-003`, adding instance identity without breaking family recognition.
Two instances of the same family are a mandatory early example.

## 6. Macro-elements and ownership

The tree-presentation goal is one 3D macro-element per module instance, containing
its operations, sketches and owned supporting geometry. Do not include the input
body or anchors of earlier steps. Shared anchors belong to their own step.

The SDK documents [IMacroObject3D](https://help.ascon.ru/KOMPAS_SDK/23/ru-RU/imacroobject3d.html),
its [Objects property](https://help.ascon.ru/KOMPAS_SDK/23/ru-RU/imacroobject3d_objects.html)
and [creation through Add](https://help.ascon.ru/KOMPAS_SDK/23/ru-RU/imacroobjects3d_add.html).
Grouping is verified and enabled for the first rotational chain. For other families,
do not assume it is neutral to all
dependencies, object collections and existing inspectors.

Before making grouping mandatory, verify a small live chain: unchanged geometry,
external references of the next step, parameter change/rebuild, save/reopen,
readback access to members and ungrouping. Recipe and ownership remain the identity
source after dismantling the group. Supporting arbitrary renaming remains a
future requirement; current continuation enforces canonical root names. A macro-element is not a
substitute for parameterization, a body or a recipe.

## 7. Execution, verification and persistence

Layer 2 owns normalization, geometry and compatibility; Layer 3 owns sequencing,
dependencies, placement, document lifecycle and results. Family generators own
functional geometry; the existing Layer 1 boundary owns COM and readback.
A module inside a chain does not open or save documents independently.

Planning does not write to CAD. Execution requires explicit confirmation and an
exact target. One chain is one bounded CAD job under the existing write gate,
not independent calls with unprotected gaps.

Retain standalone-body checks for an owned blank. For an input region, verify
base suitability, placement and working dimensions, expected material change and
preservation of geometry outside the working region. Do not compare an isolated
module's full volume with the composed part's volume. Use targeted readback/delta
checks; request full snapshots and meshes separately or on failure. Verify
patterns by processing results, not just their counter (`PATTERN-001`).

The recipe stores order and identities, module/calculation and catalog-data
versions, parameters, links, placement, source and material modes, namespaces,
ownership and semantic outputs. Reuse the existing bounded/checksummed metadata
foundation. Recognition after reopening is not a fresh geometry audit; expose
disagreement with manual changes explicitly.

Failure stops later steps and reports the last verified step, target document
and partial result. Cancellation/timeout is not rollback. For an unknown outcome,
first recover the session guard through the existing
[procedure](../low-level-runtime.md#timeout-and-session-recovery), then inspect state;
do not bypass the guard for diagnostics or automatically retry the write.

Initially, recipe changes use a fresh build in a new document while preserving
the original. Declare genuine driving edits separately. Later consider recreation
from the changed step to the sequence end; do not promise migration of manual
operations or safe branch replacement without separate verification.

## 8. Stages and transition gates

| Stage | Deliverable | Transition gate |
| --- | --- | --- |
| A. Capability profiles and contract | Selected families classified; region, modes, references and naming defined | No hidden blank or implicit target; public schemas agreed |
| B. Placement and macro-elements | Limited placement set and small-chain grouping verified | Readback, dependencies and persistence preserved; limitations explicit |
| C. First shaft chain | Stepped base → cone → axial bore → face ring groove | One body, correct regions, no duplicate base; repeated blocks independent |
| D. Gear base and continuation (implemented within the limits above) | Cylindrical rim → cylindrical hub → mounting bore; continuation of a selected saved model | Family verification before downstream changes, step verification afterward; reference recovery |
| E. Expansion (partly implemented) | Polygon/flat sections, bolt-circle holes, initial spline shaft and terminal external metric threads; broader modes remain ahead | Each mode and working region verified independently |

The first hub uses existing cylindrical construction. A keyway, cutting teeth
on an arbitrary shaft and arbitrary orientation are not hidden acceptance
requirements for stages C/D.

The first MCP release needs capability discovery, planning, execution, recipe/result
inspection and rebuilding from the recipe. Do not create a tool for every module
combination. Choose exact names and schemas in stage A while preserving compatibility
of standalone tools.

## 9. Completion criteria and documentation

This checklist retains the full agreed future requirements, not a blanket claim
that every family, input mode or placement is already implemented.

- [ ] Both end-to-end chains produce one verified final body.
- [ ] Owned and input bases use the same processing without a hidden duplicate.
- [ ] Incompatible regions are refused before processing with an actionable reason.
- [ ] Repeated blocks have independent names, variables and ownership.
- [ ] Claimed placements are confirmed by actual geometry.
- [ ] Macro-elements pass dependency, readback and persistence checks.
- [ ] Recipe and references recover after reopening; continuation is explicitly targeted.
- [ ] Mid-chain failure leaves a clear partial result without automatic retry.
- [ ] Host tests protect schemas, links and errors; live CAD verifies COM, rebuild and reopen.
- [ ] MCP, family contracts and ENG/RU describe only verified modes.

This paired plan owns the general construction-chain topic. Architecture defines
owners, CAD patterns record verified API behavior, and family contracts define
specific modes and limitations. Obtain capabilities and parameters from their code
owners rather than maintaining independent manual catalogs. The examples above
cover implemented MCP calls; later design requirements are not additional runtime capabilities.

Live CAD files, probes and raw reports remain local ignored artifacts.
Unverified capabilities do not receive ready status.
