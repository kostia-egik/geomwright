# CAD Patterns

This file is the operational memory for Geomwright's KOMPAS-3D CAD automation.
It stores rules that were verified on live models and should be checked before
guessing COM API behavior.

Only reusable behavior belongs here. A one-model observation stays in its family
document or local evidence until it has survived rebuild/reopen and applies to at
least one broader class of operations. Historical implementation plans belong in
`docs/archive/`, and unfinished prototypes belong in `experiments/spikes/`.

Evidence levels used by this file:

- **live-verified** — confirmed through KOMPAS creation plus readback/reopen;
- **implementation-backed** — enforced by current source but not yet promoted by
  repeated family evidence;
- **provisional** — a warning or hypothesis that must remain explicitly marked
  and must not be treated as a production invariant.

## How To Use This File

1. Start with `Quick Index` and choose rules that match the current task.
2. Apply the matching `Rules` before implementing or debugging.
3. Use `Case Studies` only for context and known working chains.
4. After a repeated live failure or reusable fix, add a new rule or update an
   existing one. Do not hide failed approaches if they prevent future loops.
5. In work notes and prompts, reference stable IDs like `CS-004` or `VAR-001`,
   not old section numbers.

## Quick Index

| Task / symptom | Read |
|---|---|
| Arc through 3 points is mirrored or goes the long way | `ARC-001`, `VERIFY-001` |
| COM field rejects a formula or silently resets it | `PARAM-001`, `VAR-001` |
| Need formula-driven CAD parameters | `PARAM-001`, `VAR-001` |
| Text supplied to AddVariable disappears from metadata readback | `VAR-002` |
| Need a local coordinate system for parameterization | `CS-001` |
| Axis direction changes after switching CS / plane | `CS-002`, `DIR-001`, `VERIFY-001` |
| Changing an early CS breaks dependent geometry | `CS-003` |
| Sketch on angled plane has unstable origin | `CS-004` |
| Sketch moves after rebuild or parameter change | `SKETCH-001`, `CS-004` |
| Reference sketch projection constraints need source confirmation | `SKETCH-002` |
| Projected sketch entities need style changes | `SKETCH-003` |
| Need to create a constrained sketch without losing COM handles | `SKETCH-004`, `SKETCH-005` |
| Need to project sketch geometry and constrain to it | `SKETCH-004`, `SKETCH-006`, `SKETCH-003` |
| Need visible projection of a 3D point in a sketch | `SKETCH-006`, `SKETCH-005` |
| Need to edit or inspect an existing sketch after reopening | `SKETCH-007`, `SKETCH-002` |
| UI shows a fully defined sketch but the host calls native code 1 under-constrained | `SKETCH-011` |
| Generated model file misses late-created sketches | `SKETCH-008` |
| Symmetric/repeated copies accumulate duplicate dimensions or skipped constraints | `SKETCH-009`, `VAR-001` |
| Sketch solver stalls after attaching auxiliary geometry to an already merged profile node | `SKETCH-010`, `SKETCH-005` |
| Sketch arc, line, axis, or curve has wrong direction | `VERIFY-001`, `ARC-001`, `CS-002` |
| Direction flag works but result is inverted | `DIR-001`, `VERIFY-001` |
| Spiral direction is confused with spiral construction side | `DIR-001`, `SPIRAL-001`, `VERIFY-001` |
| Physical thread has the requested hand but misses a working-span end | `SPIRAL-002`, `VERIFY-001` |
| Internal round thread sketch solves but its root depth differs from the planned contour | `THREAD-001`, `SPIRAL-002` |
| Solid body self-intersects at zero gap | `GAP-001` |
| Resolve a 2D sketch point as a persistent 3D reference | `EDGE-001` |
| Composite path mixes sketch edges and 3D edges | `EDGE-002` |
| Sketch cannot be assigned to extrude/revolve/evolution | `OP-001` |
| Operation uses wrong sketch contour or rejects a valid-looking sketch | `OP-002`, `OP-001` |
| A lone circle sketch is rejected as a non-closed bore profile | `OP-006`, `OP-002` |
| Numeric cam NURBS fails creation or silently changes its order | `CURVE-001`, `VERIFY-001` |
| KOMPAS spline accepts parameters but readback is empty, renormalized, or reads as closed | `CURVE-002` |
| Bent coil / hook spiral phase is wrong | `SPIRAL-001`, `VAR-001` |
| Native curve fillet needs a source cut point but raw spiral endpoints cannot be read | `FILLET-003` |
| Cut sketch rounds the cutter when the retained body edge must be rounded | `FILLET-004`, `OP-002`, `VERIFY-001` |
| Need full bent-coil construction chain | `CASE-001` |
| UI opens files in a hidden or different KOMPAS instance | `SESSION-001` |
| CAD job remains queued after a completed-looking operation | `SESSION-002` |
| CAD model is created but Studio reports that the managed block is missing | `SESSION-003` |
| Circular pattern reports the right count but leaves one uncut tooth space | `PATTERN-001` |
| Internal straight-spline slots do not match the retained shaft teeth | `SPLINE-001`, `PATTERN-001` |
| Host tests create duplicate CAD models during unrelated work | `SESSION-004` |
| Bridge fails with `SyntaxError` although the project venv accepts the file | `BRIDGE-001` |
| API7 attach returns a function or misses CLSID maps in gen_py | `BRIDGE-002` |
| Numeric sketch creation times out with hundreds of entities | `OP-004`, `BRIDGE-001` |
| Need a variable-section cut without a loft/loft-cut primitive | `LOFT-001`, `LOFT-002` |
| An API-created plane's sketch 2D frame is unknown or mirrored | `FRAME-001`, `CS-004` |
| Need final-body surfaces or assembly-coordinate measurements | `READ-001` |

## Rules

### THREAD-001: Check Round Internal Cutter Geometry Before Solver Acceptance

Evidence: live-verified private M20×2.5 cylindrical internal cutter, both hands,
20 mm through bore in a Ø36 carrier, followed by actual save/close/reopen and
read-only sketch inspection. This is not a public construction-chain capability
or a thread-standard conformity claim.

Symptom: a fully defined sketch and correct native signed lead coexist with a
root radius different from the requested radial depth. An inconsistent numeric
arc centre is moved by the solver to satisfy flank tangency. Solver success does
not prove agreement with the planned contour.

Rule: first validate that both arc endpoints lie on their declared circle and
that the circle is tangent to the flank lines. Distinguish the deepest material
cut from the virtual sharp apex of those lines. For the cylindrical symmetric
round cutter with half-angle α, desired radial depth d and circle radius r:

- tangent depth = d − r(1 − sin α);
- circle centre depth = d − r;
- tangent half-width = r cos α;
- outer half-width = tangent half-width + tangent depth tan α;
- virtual apex depth = d + r(1/sin α − 1).

Use the virtual apex, not d, for the theoretical flank reference. The internal
Layer 2 `_prepare_internal_metric_through_preview` holds these relations and
nominal-diameter expressions with an immutable input bore; legacy standalone
normalization does not select it. The version-1 public internal chain step now
uses this method under its strict through-carrier and persisted native audit
contract. A depth label and a stored recipe alone are not evidence of actual
CAD driving relationships.

Verification: the former default M20×2.5 round contour had native maximum radius
9.819578 mm instead of 10 mm. A consistent corrected contour has circle centre
radius 9.819578 mm, circle radius 0.180422 mm, tangent radius 9.909789 mm and actual
maximum radius 10 mm. Read-only exported-fragment inspection matches the planned
arc and preserves fully defined state/code1 and Changed=False after reopen.
The private through-end proof also requires four distinct full-span trimmed
helix boundaries, no material terminal section, positive shell removal and an
unchanged outer cylindrical surface. Its negative-Y internal profile uses phase
180° for right and 0° for left, unlike the verified positive-Y external profile;
do not copy the external phase branch without checking actual native coverage.
The phase and cutter overtravel remain family/frame-specific empirical evidence,
not normative thread dimensions or general permission to relax carrier guards.

Driver verification: fresh private right/left models built from the shared
Layer 2 adapter pass pitch2.5→2, nominal diameter20→20.2 and restoration to
20/2.5 while keeping the Ø17.29367 input bore unchanged. At every state, native
Step/Height agree with the expressions, the profile remains fully defined, two
bore-radius and two root-tangent boundaries cover [0,20], and the outer cylinder
is unchanged. Save/actual close/reopen preserves restored volume, nominal input
values and non-informational/non-read-only Step/Height expressions with
Changed=False. Editing pitch in a fixed bore is engineering geometry, not a
claim that its minor diameter matches the standard for the new pitch. These
private driver checks do not establish public chain ownership or checkpoint
support. The subsequent shared native executor proof separately verified seven
new instance roots, grouping, persistent prefix/thread ownership and fresh saved
checkpoint auditing after actual close/reopen on both hands. Compact diagnostic
metadata keeps hashes plus checkpoint within the existing size budget; pending
models still do not constitute supported public chain recipes. New supported
recipes subsequently passed public left create/reopen/inspect/rebuild and right
same-file continue/reopen/inspect. Source-preserving rebuild and old external
blind/through/omitted recipe audits were independently checked.

Private blind-end evidence: with automatic entry1.05P, frame allowanceP/4 and
actual contour outer half-width a, Height=L+1.3P−a places the last cut trace at L;
the partial terminal section projects over [L−2a,L]. M20×2.5 with L18 in a length20
bore passes both hands, actual save/reopen, native cap depth and signed lead,
two bore plus two tangent boundaries up to the conservative complete projection,
and protected outer/exit faces. The same cutter in a flat-bottom length20 bore
inside a length24 blank preserves the bottom at20 and rear face at24. For this
profile a=0.88541667, Height20.36458333 and terminal projection[16.22916667,18].
Keep last-cut length, bore depth and stock behind the bottom separate; no controlled
runout or functional full-profile certification follows from this projection.
This is bounded private evidence, not public blind-mode acceptance, a drill-point
model or permission to loosen the current through-carrier guard.
`_plan_internal_metric_end` now holds the pure relations and distinct stock/bore/
working intervals. Its through Height value and binding match the existing method
exactly; it does not mutate that preview or its recipe. A host-only comparison of
all four retained create/reopen cases matches the native terminal projection to
within 2e-10 mm (observed residual, not a manufacturing tolerance). Native blind
guards/checkpoint integration and public blind-mode acceptance remain separate.
The subsequent private full-through-bore blind guard binds the physical carrier
and endpoint plan. Shared native snapshot/checkpoint verifies the cap and smooth
tail, unchanged outer cylinder/exit annulus, persistent root inventory and drivers.
Two existing private cuts were freshly read, given compact checkpoints, saved and
actually reopened without another sweep; saved checkpoint auditing passed clean.
The private flat-bottom guard now binds the complete stock and shorter bore
separately; it does not broaden the public through-carrier gate. Shared snapshot
and checkpoint preserve the outer cylinder, bottom disk and rear disk. Validate
disk area and rim radius: sampled trimmed disk boundaries do not include the
filled centre. Bind both positive gap-to-bottom and stock thickness behind it,
not merely the working length. Both existing flat-bottom cuts passed fresh audit,
checkpoint save and actual close/reopen without another sweep. The public blind
mode subsequently reused this endpoint/guard/checkpoint contract: left creation
and source-preserving rebuild, right same-file continuation in flat-bottom stock,
and actual reopen/fresh inspection passed. Right blind-ending creation inside a
through bore also passed. Existing through and external recipes remain unchanged;
pending diagnostic files are never automatically promoted.

### SPIRAL-002: Verify Physical Thread Hand And Axial Coverage Separately

Evidence: live-verified readback and reopen of external metric M20×2.5 on a
complete Ø20×20 carrier; not a general thread-family acceptance claim.

Symptom: `Step`, `Height`, `TurnDirection` and successful evolution creation look
correct, but the final helical boundaries do not reach a requested span end.
Changing hand alone is not proof that the cutter placement/envelope is correct.
The path initially starts on −Z for either hand, while the profile stays in XY
on +Y. `TurnDirection` reflects the path in Y, not across that profile plane.
The verified left external cylindrical metric +X fix uses `TurningAngle=180`
to give the required Z reflection. Other phase branches remain unchanged.

Rule: sample bounded trimmed native edge curves, unwrap `atan2(Z,Y)`, compare
signed `2π ΔX / Δangle` and interior constant-lead/radius residuals, and check
axial coverage independently. Ignore end/profile trims as helix witnesses.
Also compare final body bounds, native removed volume and the allowed radial
shell. These are sampled geometric checks, not exact BREP or manufacturing
tolerances. Spiral height includes entry allowance; do not infer cutter limits
from nominal thread length or silently permit changes to adjacent smooth stock.

Implementation: internal `_metric_helix_edge_evidence` and
`_verify_external_metric_thread_geometry`. The latter initially requires a
complete +X external metric cylinder with 2–64 turns and one full-span helix
witness; partial/compound carriers remain unsupported. Do not relax this gate
to accept a short span merely because handedness or positive removal passes.

Verification: right-hand M20×2.5 has native lead +2.5 and a full [0,20] witness;
left-hand native lead −2.5 is correct, but all long helical edges end at or before
18.46875 rather than 20. Native volumes are respectively 5.37495107149 and
5.43286770775 cm³. The left rejection and volume persist after actual reopen.
The original short-span file remains a retained negative example.
New right/left builds pass full-span, depth, profile code1, pitch2.5→2→2.5 and
reopen. Automatic external root radius is now the normalization tangent-circle
relation in current width/depth expressions, not a frozen initial number;
explicit radii remain constant. Changed volume/code1 alone would miss this bug.

Compound protection prerequisite: select the complete exposed +X cylindrical
constructor explicitly and keep all other rotational stock strictly inside the
thread root core and behind its start. Do not infer cutter limits from nominal
length or accept root tangency. The initial host guard excludes prior cuts and
virtual gear/spline/polygon carriers. A left M20×2.5 on the second step of
Ø12×12 + Ø20×20 preserves the neck's native cylindrical/end-plane radius, axial
bounds and areas through cut/reopen; one original rotation remains. This is
bounded analytical/sampled evidence, not persistent chain ownership or exact
BREP preservation. Resolve actual native faces again before every write.
For saved chain input, `_thread_carrier_context` verifies the saved recipe and
expectations, existing persistent ownership/names/groups and current body before
resolving the carrier and end planes. It rejects a mismatched input prefix without
writing. The live two-step chain has four stable root IDs and two audited groups
after reopen, with unchanged dirty state. This is pre-write verification only:
fresh COM faces expire on rebuild/cut; it does not certify new thread-root
ownership, install variables or update the saved chain recipe.
Internal execution now reuses that context, installs a collision-free instance
namespace, reacquires the faces and calls the existing source-free family sweep.
Compare whole root inventories: the verified metric round mode creates exactly
one sketch, evolution, axis, spiral, local CS and two points. Group only those
seven roots; never include the input body, face references or prefix supports.
For persistence, keep a compact creation checkpoint with persistent root IDs,
the protected-face/bounds baseline and the actual audited native thread volume.
The radial shell is only a removal upper bound, not an analytic thread-volume
prediction. Reopen auditing uses the pure carrier gate and current ownership,
root inventory, trimmed geometry and drivers; never send the already-threaded
body through the uncut-stock reader. The internal checkpoint passed actual
save/close/reopen in both pending right/left diagnostic copies with Changed=False.
The accepted terminal-thread chain now stores this evidence in its final recipe;
old pending prototypes are still not promoted automatically.
Check protected analytical face areas/bounds, shell removal and trimmed helix
witnesses both before and after grouping. Then reuse persistent ownership for
the prefix and new group. Right/left M20×2.5 on the real two-step stock pass
pitch2.5→2→2.5, profile code1, driver expression/input-flag readback and reopen.
The original file remains byte-identical. The diagnostic copies use a pending
recipe marker that prevents supported-chain recognition/rebuild/continue; this
does not itself establish the public saved thread-step contract. That contract
was subsequently verified through normal create, same-file continue, fresh
inspect after actual reopen and source-preserving rebuild on both hands.
NewDocument returns the base IKompasDocument: explicitly cast to the 3D interface
before passing it to readers requiring TopPart. The stopped stock prefix was
audited and continued, not blindly recreated. Evidence remains sampled/analytical,
not exact BREP or a standard-conformity certificate.

### GROUP-001: Group Only Instance-Owned Roots In A 3D Macro

Evidence: live-verified on the shaft/cone/bore/face-groove chain and two independent
shaft instances, including rebuild, driver restoration, save/reopen and Destroy.

Use `IModelContainer.MacroObjects3D.Add`, assign `Objects` as a typed
`VT_ARRAY | VT_DISPATCH` of this instance's sketch and operation, then `Update`.
Keep incoming bodies and earlier supports outside the group. Verify member
references, current final geometry and downstream operations after grouping.
`IMacroObject3D.Destroy()` ungroups while retaining the roots; the checksummed
recipe and root references retain instance identity. Collection items may expose
only `IModelObject`: cast explicitly before reading interface-specific properties.
Stage D gear/hub/bore continuation also verifies grouping. Persist root and macro
IDs through API7 `GetObjectId`/`FindObjectById`: runtime `Reference` can change on
reopen. Never guess identity by name alone; continuation still enforces canonical
root names and does not promise arbitrary rename acceptance. Reused checksummed
recipe slots explicitly replace `.Value` and `.Note`, then verify decoded metadata.
This evidence applies to the supported rotational chain, not arbitrary families.
Do not diagnose a grouped operation as suppressed merely from its own
`IFeature7.Excluded=True`, `State=4` or empty `ResultBodies`. These were observed
on the accepted metric-thread member while its owner macro was included and the
part's final body contained the verified thread. An unthreaded experimental part
showed the same member flags. Read owner context and final part geometry/material
delta; neither member flags nor successful Update alone establish the result.

### VISUAL-001: Export A Native Model Raster Without The UI Dialog

Evidence: live-verified PNG export of the construction chain in interactive v23.

API5 `ksDocument3D.RasterFormatParam()` and `SaveAsToRasterFormat(path, params)`
export the active model without a save dialog. Initialize parameters; PNG uses
`ksRasterFormatPNG=3`, with explicit colour depth and resolution. Select and check
the exact active document before using API5. Hide owned auxiliary sketches and
default planes during construction for a readable result. The public
`export_model_png` selects an exact opened document and supports native
current/front/rear/top/bottom/left/right/isometric views, DPI 150 and fit by default.
It performs no geometry operation or rebuild. Temporary orientation/fit restores
and checks `Matrix3D`, `Scale` and previous activation; exact screen pan is not
certified. Native `left` may show a global-X part's side, not its end. Default UUID
PNG paths and explicit new destinations never overwrite existing files. Arbitrary
Euler angles are not exposed until native units are verified. Stage D gear PNGs
were visually reviewed for smooth tooth faces, bore and face groove.
For an inactive document, cast to `IKompasDocument` and assign `Active=True`;
the typed API7 wrappers do not expose `Activate()`. Apply the same property when
restoring the prior tab and verify both runtime identities. Live inactive-tab
exports of the polygon control and shaft/polygon/bore/groove chain preserve
Matrix3D, Scale, prior activation and the document's unchanged flag.
Inspect the image with vision; an export success flag alone does not verify appearance.

### READ-001: Measure Final Trimmed Geometry In The Document Frame

Evidence: live-verified on ordinary user-built washer, multibody gear and gearbox
assembly, including independent reopen readback with unchanged source hashes.

Symptom: cylinder placement appears to be identity, two assembly shaft axes
incorrectly coincide, or a cylinder height exceeds the finished shaft length.

Cause: a trimmed mathematical surface can return an unhelpful placement; body
geometry is component-local, and supporting-surface extent is not a trimmed
boundary dimension.

Rule: enumerate final `IFeature7.ResultBodies`, then their `ModelObjects` faces/
edges/vertices. Recover a cylinder axis from two radial normals; use the V
derivative only to orient it, not to assume an axial parameterization. Verify
the radial centres lie on that axis. Compose
nested component placements child*parent for KOMPAS row-vector matrices. Transform
points, axes and meshes into document coordinates. Preserve conservative AABB
status; do not call a transformed box exact geometry bounds.

Implementation: shared `assets/bridge/body_geometry_runtime.py`; read-only
`finished_geometry` tools. Radius/area/edge length come from native geometry;
infinite axes/planes and sampled meshes have explicit distinct meanings. Native
minimum-distance witness points must agree with the reported scalar; native
axis/centre interpretations cannot be labelled surface clearance.

Verification: washer OD32/ID22 and 0.6 mm face distance; two-body primary sixth
gear, 202 tooth-body faces/590 edges; transformed gearbox shaft spacing58.49 mm.
Document Changed/update stamps and original file hashes remain unchanged. Public
sketch inspection exports with `WriteToFragment`, reads a separate read-only
fragment and includes Beziers, without opening the source definition.

Known limits: no universal BREP export, manufacturing tolerances or construction
recipe recovery. The process gate returns `CAD_BUSY` for overlapping bridge
dispatches; direct COM scripts and manual UI actions remain outside the gate.

### PATTERN-001: Verify Material Removal, Not Only The Circular Pattern Counter

Evidence: live-verified on the silent-chain GOST II rim; corrected creation and
save/reopen retain the expected volume and radial profile.

Symptom: `ICircularPattern` is valid and reports `Count2=23` and the correct
angular step, but the final rim contains the material of only 22 cuts.

Cause: a full-period cutter included the zero-stock outside-circle tooth-tip
arc. Adjacent cutters had coincident boundaries; the native pattern silently
omitted a material-removing instance without failing `Update()`.

Rule: for a rotationally symmetric blank and repeated identical cuts, compare
total removed volume with source-cut volume times physical instance count.
The silent-chain builder uses 0.05% of expected removed volume, with a
0.001 mm³ numerical floor. This is a mass-property comparison bound, not a
manufacturing tolerance. A valid counter cannot override a failed comparison.
The solid ASME rounded-tip/side-guide case showed 0.0214% native mass-property
non-additivity despite passing independent volume and geometry checks. Keep the
reported relative error; the 0.05% bound is still below a single missing cut at
the supported maximum 114 teeth (about 0.88%). Do not increase it to accept a
missing instance. The independent full-body volume check remains mandatory.

Implementation: circular-tip GOST/DIN profiles cut only the tooth space; the
tip circle already belongs to the rim. ASME rounded tips partition their
full-period cutter at a source-defined outside-radius tip maximum, so adjacent
cutter boundaries meet outside material. Preserve the functional contour.

Verification: check the source cut and final mass properties, count/step/axis,
actual profile entities and arc directions, bounds, rebuild and save/reopen.
Known example: `transmissions/silent_chain.py` and
`handle_create_silent_chain_sprocket`.

The straight-sided spline foundation follows the same rule through
`_verify_straight_spline_metrics`: explicit bound candidates and actual pattern
removal are mandatory, not merely a radial envelope and Count2. Live shaft/hub
`8x36x40` and a custom shaft pass source-profile/direction readback and actual
reopen. In construction chains, audit the spline before adding other material:
its inherited through-all cutter must not be rebuilt to process later sections.
Subsequent core cuts preserve the audited lateral tooth-zone fingerprint; it is
sampled geometry evidence, not exact BREP equivalence.

Private bounded-input shaft evidence: an `8x36x40` space cut over X=[10,30]
inside a Ø40×50 cylinder with a Ø30×10 continuation passes exact single/all-space
mass comparisons, unchanged end/shoulder faces and sampled boundary containment
before save and after actual reopen. Both extrusion ends must use finite-depth
type0, the inactive side depth must be zero, and the active depth is read back
from the native operation variable. Ordinary workflow calls retain through-all.
With `CoordinateSystem=parallel_plane` assigned before `Plane`, normal cuts +X;
the reverse proof instead cut toward X=0 and changed that protected end face.
Its readable depth20 and correct array count did not imply correct working span.
Preserve that negative example; do not infer the input-plane normal from the
standalone default-YOZ blank direction. Strict input-chain ownership/checkpoint
and public acceptance remain separate from this primitive geometry proof.

The later private input executor uses the verified uncut prefix context, owns
seven explicit roots and preserves prior root identities. Pattern sources come
from the returned source cut, not name-matching generated copies. Its length
input drives the active native Distance1; both extrusion ending types remain0
and the inactive Distance2 remains0. Length20→22→20 changes only the bounded
working length and passes geometry/profile/protected-face/driver audits through
save/actual reopen. Numeric profile readback and persistent source/axis identities
are checked independently. Group/hide exact owned roots only. This evidence does
not certify whole inventory/checkpoint acceptance or public recipe recognition;
pending metadata remains deliberately unsupported.

Read-only inventory discovery identifies each extra extrusion through its native
`OwnerFeature` (array exemplar), then that exemplar's `OwnerFeature` (the owned
pattern). `ICircularPattern.Exemplar(1,index)` resolves the same exemplar; do not
classify copies by repeated display names. The observed seven extra coordinate
records have empty persistent IDs and names, type11014/model-type70, self ownership,
TopPart parent and zero coordinates; they need a separate bounded record policy,
not invented persistent ownership. On the same cut specimen, checkpoint preparation,
metadata-only save and actual close/reopen passed with unchanged inventory and
`Changed=False`; ownership/profile/driver/protected-stock audits passed without
replaying cuts. This verifies the private checkpoint, not public recipe support.
For this workflow `SaveInitialOrientation` is explicitly False so copies rotate
with the array. The low-level pattern factory defaults True: copying that default
into a checkpoint guard caused a read-only false rejection and quarantine. Bind
the policy to the actual workflow call, not the helper default; never change the
already verified model merely to satisfy that mistaken guard.

Public input/remove acceptance reuses this executor/checkpoint as a sole terminal
cut on uncut rotational stock. Require positive smooth margins at both cylinder
ends: the current bounds/protected-face contract does not certify open ends.
An in-memory prefix envelope precedes the cut; only the final supported recipe
and `spline_audit` are saved. Standard `8x36x40` creation, same-file continue after
reopen, fresh inspect/reopen and source-preserving rebuild passed. Custom
z8/d35/D40/b6/r0.3 creation/reopen passed too. Historical pending recipes remain
unsupported; never convert them implicitly or replay cuts on their evidence models.

For grouped cuts, read actual sources from `ICircularPattern.InitialObjects`.
The final extrusion collection can contain patterned copies with the same names;
display-name uniqueness across that collection is not source ownership. Compare
additional removal with the original group removal times `count - 1`, and cap any
relative/numerical tolerance below the volume of one missing group. This is also
live-verified on diaphragm circle/oval relief groups at 12 instances and a custom
9-instance part. Use `IModelObject`/raw-object references; an `IFeature7` cast does
not expose their `Reference` property in this path.

### SPLINE-001: Verify Mating Complement, Not Two Independent Spline Volumes

Symptom: a shaft and hub each pass their own volume/pattern/save checks, but their
straight-sided sectors do not mate. The old hub reused the external inter-tooth
gap construction with neighbouring tooth axes; rotating by half a pitch cannot
repair the wrong flank directions/width. Its inward floor fillet at D also
occupies the square corner of a nominal shaft tooth.

Rule: for the nominal counterpart, cut the retained shaft tooth, not its gap.
Use two parallel b-spaced flanks, phase the hub slot at the shaft tooth centre
(pi/z from the external gap), and repeat the mating shaft-root transition at d.
Do not add an inward floor rounding at D without a matching tip relief. This
analytic counterpart is not a cutter reconstruction or tolerance-stack certification.

Implementation: `connections/splines/straight.py` shares `_shaft_fillet` and builds
the hub's six-entity complementary cutter. Period closure derives from actual
boundary points and includes every flank/fillet. Full outlines repeat with the
same negative angular direction as the period; opposite repetition creates
crossing diagonals in a misleading display.

Verification: exact shared side/root boundaries plus Green-integral area complement
for standard/custom inputs; an offline diagnostic passed all53 catalog rows.
New standard hub and shaft and a custom hub passed native create/save/actual
reopen, exact sketch readback and mass checks. Native hub PNG and shared paired
section were visually reviewed. New hub recipes carry `profile_geometry_revision=2`;
legacy hubs are recognized but flagged `legacy_hub_profile`, verified=false.
Retain their inputs for recreation; never silently migrate existing geometry.

Input-hub chain acceptance uses a sole terminal full-through cut on one explicit
cylinder plus its explicit bore. Do not reuse the external smooth-margin policy:
a smaller smooth bore collar would obstruct a mating tooth at entry. Require the
full bore span, zero offset, immutable d and inherited outside diameter. Bind the
cut's length input to the existing native bore-length variable. Protect the full
outer cylinder; end annuli change intentionally. Verify both working-radius
extremes, exact source/all removal, profile/persistent IDs and complete inventory.
Standard create/continue/actual reopen/source-preserving rebuild and custom
create/reopen passed using the shared executor/checkpoint. The explicit blind
variant below is separate; arbitrary partial spans, subsequent operations and
arbitrary stock remain unsupported.

Blind-hub acceptance: a finite cut from open entry leaves a positive
smooth tail before a flat-bottom bore and positive stock behind that bottom.
Audit both original bottom/rear disks, outer cylinder, smooth-tail witnesses and
flat terminal faces separately. The first live job stopped after construction
at a false independent-input check; that partial model remains diagnostic.
New corrected standard create/continue/source-preserving rebuild/actual reopen and
custom create/reopen passed. Native length20→22→20 restored geometry and the original
checkpoint, then save/actual reopen passed. This is flat numeric termination,
not tool runout or a manufacturing functional-length certificate.
`_apply_part_variables` converts an empty planned expression plus numeric Value
into a numeric Expression. Thus independent does not mean Expression is empty:
accept an equivalent numeric constant, reject another variable or derived formula.
Keep the active cut binding to its owned length input; never change correct
geometry or reapply a cut merely to satisfy a mistaken expression predicate.
An `IVariable7` is not an operation and has no `Update()` method. Assign its
Expression and rebuild the owning document; verify actual geometry, native depth
binding and restored checkpoint, not merely the input scalar. A scratch proof
that called variable.Update stopped before rebuild; after closing without saving,
the clean saved model passed the corrected proof. Exact-document inspection also
requires opening the target first; a closed-file path is not an open document ID.

### BRIDGE-001: Compile The Bridge With The Configured CAD Interpreter

Evidence: implementation-backed runtime requirement; historical failures below
explain why a host compile alone cannot verify a separately configured bridge.

Applies when:
- editing `bridge/kompas_bridge.py` or its packaged copy;
- changing bridge syntax or its interpreter configuration;
- debugging a bridge that fails before any handler runs.

Symptom:
- every bridge call fails at import time with an error such as
  `SyntaxError: can use starred expression only as assignment target`;
- the Studio workspace returns HTTP 502 and no action executes;
- the same file imports and compiles cleanly in the project `.venv`.

Cause:
- `BridgeRunner` launches a separate interpreter. Constructor arguments and
  `KOMPAS_PYTHON` override the checkout-owned `.venv/cad-bridge` default. Without
  that venv, its final fallback names the KOMPAS installation's Python; an old installation
  can select Python 3.2.5. The current bridge uses modern Python syntax and
  cannot run under that interpreter. Compiling with the host venv does not check
  a different configured runtime or whether that runtime has `pywin32`.

Rule:
- Configure an actual modern Windows Python executable with `pywin32` through
  `KOMPAS_PYTHON`; using the host Python 3.11+ for both is the simplest supported
  setup. See [English](docs/en/setup.md) / [Русский](docs/ru/setup.md).
- Compile the bridge and changed runtime assets with that interpreter. Keep the
  root and packaged bridge copies byte-identical.
- Production calls now preflight selected source syntax plus `pywin32` import,
  without loading the bridge or calling KOMPAS, under a five-second deadline.
  A local failure is `CAD_RUNTIME_INVALID` before the tracked CAD launch and must
  not turn into unknown-outcome quarantine. Actual CAD failures remain guarded.
- Studio does not read the private MCP-client config. Explicitly configure its
  launch environment or use the existing checkout-owned CAD venv; do not assume
  variables from `opencode.json` exist in the standalone Studio process.
- Do not infer interpreter compatibility from string/AST syntax guards. The
  existing Studio test still contains legacy 3.2 commentary and syntax guards;
  they do not establish current runtime support.

Example finite check after setting `KOMPAS_PYTHON`:

```powershell
.\.venv\Scripts\python.exe scripts/run_bounded.py --timeout 30 -- $env:KOMPAS_PYTHON -m py_compile bridge/kompas_bridge.py src/kompas_mcp/assets/bridge/kompas_bridge.py
```

Verification:
- A clean `py_compile` exit under the configured CAD interpreter before any live run.
- COM-free preflight accepted the owned Python 3.11 runtime and rejected the
  installed SDK Python 3.2.5 with unchanged shared guard. Focused tests cover
  selection priority, failure/timeout without CAD launch and source-cache invalidation.
- One live action through the production Studio path.

Historical examples under the old bundled runtime:
- `_inspect_gear_spur_block` used `(blank, gap, *cuts, pattern)`; the host venv
  compiled it, and the Studio workspace failed until it was rewritten as a list
  concatenation.
- `handle_create_gear_internal` then reintroduced
  `["blank", *ring_chamfer_ids, ...]`; the venv compiled it, and the Studio
  "Создать в КОМПАС" job failed with the same `SyntaxError` until it was
  rewritten as list concatenation. These cases explain the old workaround;
  they do not make Python 3.2 a current requirement.

Related:
- `SESSION-002`
- `OP-004`

---

### BRIDGE-002: Repair Only The Broken Generated COM Library

Evidence: live-verified during extension-family integration; subsequent creation
and save/reopen of conventional hooks and a compression control case passed.

Symptom: the bridge reaches a function instead of API7 and reports no `Documents`.
A direct `ksGetApplication7()` call reveals missing `CLSIDToClassMap` or
`CLSIDToPackageMap`. The API7 `win32com.gen_py` package has no `__file__` because
its generated `__init__.py` is missing, despite existing interface modules.

Rule: diagnose the raw attach exception before changing CAD geometry. Under the
configured CAD interpreter, regenerate only the installed SDK's `kAPI7.tlb` with
`win32com.client.makepy.GenerateFromTypeLibSpec(library_path, bForDemand=True)`.
Do not delete unrelated caches, restart KOMPAS or close user documents to repair
Python's generated library. Verify both Application5→API7 and direct Application7
attach, then one bounded live action with unchanged existing-document count.
This recovery applies to an evidenced missing generated package, not every COM
failure or a busy/modal KOMPAS session.

---

### CURVE-001: Native NURBS Uses Order And Typed Numeric Arrays

Evidence: live-verified on direct C2 and roller-rocker cam profiles, including
rebuild and save/reopen curve readback; DIN silent sprocket curves also verified
with 15, 23 and 114 teeth.
Stage D external gear also uses mathematical C2 interpolation with simple interior
knots: m2/z20/b20 readback has 100 tooth-zone faces and a smooth native PNG.

Symptom:
- `INurbs.SetNurbsParams` returns false with ordinary Python arrays or the
  mathematical degree; no usable curve reaches the extrusion.
- `Nurbses.Item` sometimes exposes only `IDrawingObject`, so readback methods
  disappear between calls.

Cause:
- API7 expects `SAFEARRAY | VT_R8`; coordinates are flat `(x0,y0,x1,y1,...)`.
- Its `Degree` field denotes **order**: a cubic Bezier/NURBS uses `4`, not `3`.
- Indexed collection items require an explicit interface cast for stable methods.

Rule and implementation:
- Pass explicit `win32com.client.VARIANT(VT_ARRAY | VT_R8, values)` for points,
  weights and knots; use order 4 for a cubic curve.
- Cast indexed items to `INurbs`/`IArc` before calling their readback methods.
- Read all poles, weights and knots after rebuild. Do not count `Update()` as
  proof of curve accuracy or correct base-arc direction.
- Preserve an explicit native `order` during section-frame conversion. If the
  section plan supplies mathematical `degree`, pass `degree + 1` to API7.
  Order 3 with cubic poles/knots can be accepted while KOMPAS silently replaces
  the knot vector; the resulting loft may fail instead of reporting a spline error.
  In external gears this also led to an incorrect profile; a repeated-knot Bézier
  workaround fragmented faces. `gears/cad.py` now uses `interpolating_spline` for
  the external root/involute curves, single interior knots and explicit order 4,
  retaining the existing deviation cap. Verify native knots and the actual raster;
  C2 within a curve does not remove the theoretical join between separate curves.
- Sample the evaluated rational curve for topology checks, not its control
  polygon. `GetNurbsParams`' first return value is success, not curve closure;
  read the native `Closed` property separately.
- For sampled motion envelopes, arc-length interpolation avoids tangential
  acceleration jumps corrupting curvature at piecewise motion knots. Keep a true
  circular base arc separate and verify global contact and final solid volume.

Verification:
- Compare native NURBS parameters with the checked plan and held-out profile
  samples, then verify actual bounds, extrusion direction and integrated volume.
- Reopen the saved part and repeat the curve/contact and body checks.
- A valid extrusion with the wrong base-arc branch can still be the wrong cam;
  volume/bounds verification must reject it.

Known examples: `kompas_mcp/sketch_runtime/cubic.py`, `kompas_mcp/cams/cad.py`,
`transmissions/silent_geometry/silent_chain_din.py`, and bridge `_sample_curve_points`.
The default bevel wheel (`m3 z20 delta45`) was accepted through the shared MCP
contract on 2026-10-09 after `_section_entities_to_sketch_2d` retained native order 4.
Both sections preserved knots/weights and pole distances, with successful body
verification and save/reopen. Native order alone did not prevent loft-face
fragmentation: the Bezier-chain plan produced 743 faces in about 92 seconds,
whereas the simple-knot C2 plan produced 183 faces in about 30 seconds locally
(see `CURVE-002`). Cancellation of the bridge does not mean that an in-flight
native operation has stopped.

### VAR-002: Read AddVariable Text From Note, Not ParameterNote

Evidence: live-verified on direct and rocker cam recipes and roller/bush-chain
sprocket recipes (including a two-row sprocket), including save/reopen.

Symptom:
- numeric variables exist, but a saved recipe checksum fails because all text
  fragments read back as empty strings.

Cause:
- API7 `IVariable7` exposes both `Note` and `ParameterNote`. Text passed as the
  third `AddVariable(name, value, note)` argument appears in `Note`; on the
  verified runtime `ParameterNote` is empty.

Rule and implementation:
- read the actual `Note` property for AddVariable text metadata; do not substitute
  a planned-note fallback and call that persistence verification;
- keep structured text bounded, versioned and checksum-verified;
- metadata is not a geometry-driving formula or evidence of a fresh audit.

Verification:
- compare decoded actual text with the complete recipe at creation and after
  save/reopen. Direct and rocker recipes, including Studio form settings, match.

Known example: `_inspect_cam_block`, `_execute_create_cam`, and
`handle_inspect_managed_pulley`. Do not prefer an empty `ParameterNote` over `Note`.

### SESSION-004: Host Tests Must Not Reach the Live CAD Adapter

Evidence: implementation-backed; unintended repeated sprocket creation reported
in the interactive session and explained by the confirmed source path.

Symptom:
- running ordinary Studio tests creates repeated roller-chain sprockets in the
  user's running KOMPAS, including while another module is being developed.

Cause:
- a `TestClient(create_app())` used the default live `KompasAdapter` and submitted
  a confirmed `/modules/chain_sprocket/cad/jobs` request;
- checking only HTTP 202 or accepting a failed job did not isolate the executor
  or wait for its background thread, so a nominal host test performed a CAD write.

Rule:
- host HTTP tests inject a fake adapter before any write-route request;
- background fake jobs must finish before the test exits;
- the pytest process must reject the real bridge, even if an application layer
  catches the exception. Live verification runs separately with an explicit target.

Implementation and verification:
- `tests/conftest.py` installs a session-wide `BridgeRunner.call` guard for the
  production/configured bridge and KOMPAS interpreter; it remains active through
  interpreter shutdown and fails the session on blocked attempts;
- `test_http_api_serves_ui_catalog_preview_and_structured_errors` injects a fake
  creator, checks its single chain call and waits for the fake job to complete;
- focused HTTP and fake-process bridge tests pass without calling KOMPAS. Do not
  reproduce this failure by creating or deleting live models.

### SESSION-001: Interactive Hosts Must Attach to a Visible Running KOMPAS

Applies when:
- a user-facing host such as Geomwright Studio operates on documents the user
  expects to see in the KOMPAS window;
- bridge calls run in short-lived external Python processes.

Symptom:
- Studio starts before KOMPAS and later opens documents in an invisible session;
- opening the same file in the visible KOMPAS reports that it is already in use;
- restarting Studio and KOMPAS changes which document collection is observed.

Cause:
- `Dispatch("KOMPAS.Application.5")` may create a COM server when no running
  object is registered. A later visible KOMPAS process is then a different
  application instance.

Rule:
- Interactive hosts use registered `.5`/`.7` objects but must not make a hidden
  instance visible or create a substitute application. Match MainWindowHandle,
  owning PID and process creation time to a persistent selected binding before
  document reads/writes. Multiple visible processes require explicit HWND
  selection; enumeration detects ambiguity but cannot make an unregistered
  COM object selectable.
- In KOMPAS v23, `IApplication.MainWindowHandle` can identify an invisible
  controller window owned by the visible application frame. `Visible=true`
  plus `IsWindowVisible(MainWindowHandle)=false` does not prove a hidden instance.
  Resolve the native root/owner chain, checking that every link has the same PID;
  bind the resolved presentation HWND plus PID and process creation time. Reject
  cycles, excessive depth and cross-process ownership. Do not search an arbitrary
  visible window by PID as a substitute for a proven ownership relationship.
- KOMPAS v23 can expose the visible interactive controller only as
  `KOMPAS.Application.7`. Interactive bridge code must try the active `.7`
  object after `.5` and use that API7 object directly; it must not fall back to
  `Dispatch("KOMPAS.Application.5")`, because that creates a second hidden
  process and a separate document collection.
- Absence of a running object is a recoverable disconnected state, not
  permission to create an application.
- `interactive` is the shared MCP/Studio default. `hidden` is explicit and may
  use only a separately created process proven absent from the pre-create PID
  snapshot. A successful DispatchEx call alone does not prove isolation. Keep
  its owned identity across calls; if ROT cannot reattach it, refuse instead of
  creating another instance or using the visible user's process.
- Legacy `visible=false` is not a mode selector. The session policy enforces
  document visibility in Add/Open. Interactive documents remain open by default;
  staged Close/replace/reopen is reserved for hidden workflows. Do not report
  fresh reopen verification when the open document was merely reused.
- Bind a context token per host so another client's explicit mode switch between
  workflow steps is detected before the next COM call. Quarantine recovery and
  mode selection are separate operations; neither proves CAD readiness.
- API5 `ActiveDocument3D` may be exposed as a method or as an already-resolved
  dispatch document. A dispatch object is also callable, so `callable()` alone
  is insufficient: if it exposes `GetPart`, use it directly. Invoking its default
  member instead fails with DISP_E_MEMBERNOTFOUND during body verification.

Verification:
- Deterministic host/fake-COM tests cover instance substitution, preexisting
  hidden-process reuse, document visibility, identity loss, stale context tokens
   and retained interactive save. The owned hidden creation/ROT policy remains
   implementation-backed pending live isolation verification.
- Start the host before KOMPAS and confirm no KOMPAS process is created.
- A bounded native discovery probe confirmed `.5` and `.7` return the same hidden
  controller HWND while its native owner is the user's visible frame in the same
   process. Corrected ownership resolution passed native COM attachment and
   repeated short-lived bridge reattachment during creation of a 30/20 x 25 mm
   cone, direct save and geometry/recipe readback. The same presentation HWND,
   PID and creation time were retained; one active saved document remained open,
   with fully defined sketch and exact analytic/native volume agreement. This
   is visible saved readback, not fresh reopen or proof of per-action animation;
   user-side visual confirmation and hidden isolation are separate checks. Keep
  per-ProgID discovery stages/errors so a conversion failure is not misreported
  as absent visible UI.
- Start visible KOMPAS afterwards and confirm the host discovers its documents
  without restarting.
- Open/create from the host and confirm the document appears in that same window.

---

### SESSION-002: Isolate And Bound Stateful Bridge Calls

Applies when:
- a user-facing host serializes write operations through one CAD lock;
- a short-lived bridge subprocess performs a blocking COM call;
- KOMPAS may finish the visible operation while a later legacy readback call
  does not return.

Symptom:
- the body and model-tree operation are visible and valid in KOMPAS, but Studio
  never reports completion;
- all later jobs remain at “waiting for KOMPAS access”.

Cause:
- an unbounded child bridge process retains the host-side CAD lock after a COM
  or legacy API5 readback blocks. Successful visible geometry does not prove
  that every later verification channel will return.

Rule:
- run every Studio bridge write in an isolated child process with a hard timeout
  and a user-visible cancellation event;
- set that child's stdin to `subprocess.DEVNULL`: the bridge reads request files,
  not the MCP transport. Inheriting a Windows async MCP pipe can stall Python
  startup before even the first progress checkpoint; changing Python alone does
  not fix this. Live stdio-MCP creation/save and read-only session calls verify
  the isolated-input path;
- cancellation terminates only the child bridge, never KOMPAS or the document;
- child exit does not cancel an outstanding COM operation. Persist a host-side
  in-flight marker before launch. Only a production token/action-bound completion
  receipt published after handler and mutex completion can distinguish `no_cad`
  (rejection before any controller activation, instance creation or model access;
  release guard) from a finished `settled` failure
  (`settled_failure`). Timeout/cancellation/malformed response/crash/failed custom scripts
  without a trusted receipt remain `unknown_outcome`; reject further ordinary COM
  calls, including document counts, while guarded;
- recover `settled_failure` through the exclusive 15-second same-bound-instance
  audit: native responsive/enabled frame and visible standard dialogs, COM
  document listing, API5 graphical process, possible sketch editor and in-place
  component edit blockers. No instance creation, controller/document activation,
  edit/rebuild/save/close. A blocker retains the settled marker; the user handles
  unresolved UI state. A pass clears it with basis
  `completed_handler_and_session_audit`, but returns `model_verified=False` and
  `cad_readiness_verified=False`. Inspect the affected document and partial
  changes before writing; never blindly retry;
- if the previously bound server process exited, settled recovery may remove the
  marker without COM (`bound_session_exited`). Explicitly select a session before
  any further CAD call; never attach a replacement as part of recovery;
- `recover_cad_session(token, reason, confirm_idle=False)` uses a fresh guard
  token. Actual `unknown_outcome` still requires fresh explicit user
  `confirm_idle=True` after idle UI and partial-document resolution; that branch
  does not call COM. A zero API document count is not proof that visible tabs
  were closed. Recovery is neither general asynchronous cancellation nor an
  idle-UI guarantee;
- use the shared 300-second bridge default for MCP and Studio. An outer watchdog
  must exceed the complete workflow budget (the sum of sequential call budgets
  plus host/cleanup overhead), not interrupt one 300-second call after 45 seconds;
- retain the owned partial document on a failed scenario by default. Do not
  issue automatic Close after an ambiguous CAD failure or hide its failure;
- queued jobs must observe cancellation before entering COM;
- place progress checkpoints around risky post-operation rebuild/readback steps;
- if one readback channel is proven to block after a valid operation, replace it
  with bounded operation validity, rebuild, ownership, and variable readback for
  that family, and document the verification gap explicitly.

Verification:
- deterministic fake-bridge timeout/cancellation and external host-kill checks
  confirm the durable marker survives and later calls cannot launch another
  ordinary bridge; verify trusted receipt binding and completion ordering, and
  distinguish settled-failure audit recovery from host-only unknown-outcome
  recovery. Neither branch closes documents or certifies idle UI/model validity;
- live owned-hidden checks pass with zero documents and a saved shaft: a disabled
  frame refuses recovery, an enabled frame permits audit, active document state
  is unchanged, and actual close/reopen readback succeeds. Refreshed stdio MCP
  separately passes a missing-document rejection and automatic recovery;
- create a managed flat-belt pulley and confirm `completed / verified` without
  calling the blocking API5 active-body volume probe.

Known example:
- flat-belt pulley rotation completed and was recognized by workspace readback,
  while `_active_api5_primary_body_metrics()` blocked indefinitely immediately
  after `RebuildDocument()`.

---

### SESSION-003: Studio Creation Completes Only After Managed-Block Readback

Applies when:
- a Studio CAD job creates a valid document and reports successful bridge
  verification;
- the UI then waits for the new document to appear as a managed block.

Symptom:
- the part and its operations are visible in KOMPAS, but Studio reports that the
  created managed block was not found and does not enter the result view.

Cause:
- creation metadata and workspace recognition have diverged: the bridge writes a
  new family fingerprint, but `handle_inspect_managed_pulley` does not recognize
  that family and `/workspace` consequently returns an empty `blocks` list.

Rule:
- every Studio-createable Layer 4 family must have workspace recognition in the
  same delivery slice;
- recognition must verify family metadata, the required parameter set, root
  sketches/features, and a stable root-object identity;
- generated pattern copies may be owned for topology purposes, but must not
  participate in block identity;
- create-only families may return an uneditable recognized block when their full
  profile request cannot yet be reconstructed after reopen.

Verification:
- complete the CAD job and record its runtime document ID;
- query `/workspace` and require exactly one block with the expected module and
  schema under that runtime ID;
- repeat inspection after save/reopen when the family claims reopen support.

Known example:
- single-row chain sprockets use `GW_FAMILY_CODE=6`, `CH_*` variables, two root
  sketches, blank/cut extrusions, and one tooth-space pattern. Recognition uses
  five root references and a checksummed `geomwright.chain.recipe`; a valid recipe
  restores the Studio profile and exposes the block as recreatable, while in-place
  branch replacement remains unsupported.

---

### ARC-001: Arc Through Three Points Requires Direction Verification

Applies when:
- building an arc through 3 points;
- reproducing a sketch from sampled geometry;
- KOMPAS accepts the arc but the result is visually opposite.

Symptom:
- The arc passes through expected points but uses the wrong sweep direction.
- The body is valid, but the geometry is mirrored, goes the long way, or does
  not match the reference model.

Cause:
- A 3-point arc definition is geometrically ambiguous in CAD APIs. The API can
  choose the opposite orientation without raising an error.

Rule:
- After creating a 3-point arc, verify direction against the expected midpoint,
  tangent, or reference geometry.
- If the direction is wrong, swap arc endpoints or explicitly rebuild the arc
  with the opposite orientation.

Implementation:
```python
# Prefer an explicit direction check after arc creation.
arc = sketch.AddArcBy3Points(p1, p2, p3)
actual_mid = read_arc_midpoint(arc)

if distance(actual_mid, expected_mid) > tolerance:
    arc = sketch.AddArcBy3Points(p3, p2, p1)
```

Verification:
- Read back a point on the arc or compare generated geometry with a live model.
- For reliable arc/curve direction checks, use `VERIFY-001` and create a
  temporary point on the curve.
- Do not treat successful `Update()` as proof that the arc direction is correct.

Known examples:
- Reproduction of reference sketches from existing KOMPAS models.

Related:
- `VERIFY-001`

---

### VERIFY-001: Verify Geometry Direction With Temporary Probe Geometry

Applies when:
- operation, sketch, axis, line, curve, arc, or spiral direction is uncertain;
- the geometry is valid but appears mirrored, reversed, or built on the wrong
  side;
- API readback gives object existence but not enough semantic direction data.

Symptom:
- `Update()` and rebuild succeed, but the result is oriented incorrectly.
- Sketch geometry follows the wrong local axis direction.
- Arc/curve direction is ambiguous even though points lie on the curve.
- A boolean arc direction flag is easy to read backwards: for KOMPAS
  `ICircleArc.Direction`, `false` means counterclockwise start->end and `true`
  means clockwise start->end.
- A direction flag works for one model state and fails after parameter changes.

Cause:
- KOMPAS often accepts multiple geometrically valid directions. This applies not
  only to 3D operations, but also to sketches, arcs, local axes, and curve-based
  constructions.

Rule:
- Verify direction by constructing temporary helper geometry, reading its
  coordinates, comparing them with the expected geometric relation, and then
  deleting the helper geometry.
- Prefer temporary points. For curves, arcs, lines, and axes, a point on the
  investigated object is usually the most reliable probe.
- When direction is relative, create two or more probe points and compare their
  order against each other and against nearby reference objects.

Algorithm:
```text
1. Build temporary helper geometry near/on the object under investigation.
   Usually use points. For curves and lines, use points on curve.

2. Read helper coordinates. If one coordinate is insufficient, read a group of
   coordinates: start/end points, midpoints, or points at two curve parameters.

3. Compare readback against the expected design relation:
   - expected side of a body/end plane;
   - increasing/decreasing axis coordinate;
   - start point before end point;
   - midpoint on expected arc side;
   - relative position to another reference object.

4. Decide whether direction/orientation is correct.

5. Delete temporary helper geometry after the investigation.
```

Implementation example:
```python
# Probe a curve direction with two temporary points.
probe_a = create_point_on_curve(curve, parameter=0.1)
probe_b = create_point_on_curve(curve, parameter=0.9)

coords_a = read_point_coordinates(probe_a)
coords_b = read_point_coordinates(probe_b)

is_expected_direction = coords_b.z > coords_a.z

delete_object(probe_a)
delete_object(probe_b)

if not is_expected_direction:
    reverse_or_rebuild_geometry()
```

Verification:
- Store or log the read coordinates while debugging.
- If automatic comparison is uncertain, ask the user to confirm the expected
  relation in the KOMPAS UI.

Known examples:
- Arc direction checks after `AddArcBy3Points`.
- `diaphragm_spring`: inverted `ICircleArc.Direction` values produced a closed
  endpoint graph that KOMPAS rejected for revolve; fixing the flag semantics made
  the geometry-only operation pass.
- Local axis direction checks after switching CS or angled plane.
- Bent coil spiral direction and construction side checks.

Related:
- `ARC-001`
- `CS-002`
- `DIR-001`
- `SPIRAL-001`

---

### PARAM-001: COM Fields Have Different Formula Semantics

Applies when:
- assigning numeric values, strings, expressions, or variables to COM fields;
- a field accepts a value in UI but rejects the same value through COM;
- formula strings work in one field and fail in another.

Symptom:
- COM raises a type error.
- Formula assignment is silently ignored.
- The model updates once but does not remain parametrized.

Cause:
- KOMPAS COM fields are not uniform. Some accept only numbers, some accept text
  formulas, and some require operation variables after object creation.

Rule:
- Classify the target field before assignment.
- Do not assume that a UI formula field accepts a string formula through COM.
- Before binding an operation variable, reject `Information=True` and
  `ReadOnly=True`; matching ParameterNote and successful Update do not establish
  that it is a driving input. Never clear Information merely to force a binding.

Known example: `IPoint3DParamDisplace.DX/DY/DZ` accept numbers, not strings.
The generated `Перенос Y/Z` variables are informational in the tested v23 mode;
assigning expressions creates “attempt to override output parameters”/redundancy
errors even when body volume, feature Valid and stored Expression look correct.
The bolt-circle chain instead uses a coordinate point (ParameterType1) with
non-informational `Координата Y/Z` inputs and a numeric recreate-only X placement.
PCD drives those coordinates; actual centre/radius/span, input Information flags,
pattern ownership and real reopen are checked. This does not certify arbitrary
relative-point formula modes. Preserve the rejected attempts as diagnostics,
not as accepted models or grounds to relax the output-variable gate.

Field classes:

| Field class | Accepts | Typical handling |
|---|---|---|
| Numeric-only COM property | number | assign fallback number, then use operation variable if needed |
| Formula-capable property | number or expression string | assign expression directly and read back |
| Operation-variable-backed property | variable expression after `Update()` | create object with number, then bind expression through property parameter |

Implementation:
```python
# Good default pattern for uncertain fields:
param.SomeDistance = 10.0
obj.Update()

# If the field must be parametrized and direct strings fail,
# switch to VAR-001 operation-variable binding.
```

Verification:
- Read back the value and expression when possible.
- Change the driving variable and rebuild the model.

Related:
- `VAR-001`

---

### CS-001: Use Coordinate Systems As Parameterization Tools

Applies when:
- geometry must follow a local direction;
- sketches, planes, or spirals should move together;
- global coordinates would require repeated manual transforms.

Symptom:
- Geometry works for one parameter set but breaks after size or angle changes.
- Formulas become complex because every point is defined in global coordinates.

Cause:
- The geometry is defined in the wrong coordinate context. KOMPAS operations
  often behave more predictably when the local coordinate system encodes the
  design intent.

Rule:
- Use local coordinate systems, planes, and projected references to express the
  intended construction frame.
- Keep formulas local where possible; avoid baking global offsets unless the
  reference model requires them.

Implementation:
```python
# Typical sequence:
# 1. create/reference CS or plane;
# 2. create sketch in that context;
# 3. project required 3D references into the sketch;
# 4. constrain sketch geometry to projections and local axes.
```

Verification:
- Change a driving diameter/length/angle and rebuild.
- Confirm that dependent sketches and operations remain attached to the design
  reference, not to an accidental global coordinate.

Known examples:
- `CASE-001`

---

### CS-002: Verify Axis Direction After Switching Coordinate Systems

Applies when:
- creating angled planes;
- using `BaseLine`, `Direction`, `LeadAxis`, or local axes;
- switching from global geometry to sketch/plane-local geometry;
- sketch lines, axes, arcs, or local coordinates appear reversed.

Symptom:
- A plane, spiral, or operation is created on the correct reference but points
  in the opposite direction.
- A model is valid but mirrored across the expected axis.
- A sketch is geometrically valid, but its local axis direction or curve
  direction does not match the intended construction logic.

Cause:
- KOMPAS local axes depend on reference object direction, plane normal, and API
  defaults. The same visual reference can produce different local axis signs.

Rule:
- After creating a local CS, plane, or operation direction, verify the effective
  axis direction by readback or live geometry.
- Apply the same rule to sketch geometry created in local coordinates. Sketches
  can have reversed line, arc, and axis directions even when constraints and
  dimensions look correct.
- Do not infer direction only from object names like `left`, `right`, `top`, or
  `base`.

Implementation:
```python
# Preferred: create a test/reference point or read operation direction.
expected_side = body_end_z + 1.0
actual_point = read_probe_point(operation)

if actual_point.z < expected_side:
    flip_direction(operation)
```

Verification:
- Use readback if the API exposes the property.
- If readback is unavailable or ambiguous, use `VERIFY-001`: create temporary
  probe points, read coordinates, compare expected relations, then delete probes.

Related:
- `VERIFY-001`
- `DIR-001`
- `SPIRAL-001`

---

### CS-003: Early Coordinate-System Changes Cascade Through The Model

For chain row replication use `IFeaturePatterns.Add(528)` / `ILinearPattern`
(body mesh pattern), not type 35 (operation mesh pattern). Copy the evaluated
part body obtained from `IFeature7(part).ResultBodies` after rebuild: an individual
cut's ResultBodies can be empty. Along default X, `Direction1=False` copies toward
negative X. Rebuild after the pattern before counting or inspecting copied bodies;
Update/Valid/Count alone can report success while body readback still shows only
the original. Verify row bounding boxes, then unite them with the rim revolution
and verify one body plus expected added gap volume.
For the subsequent concave rim/row fillets, resolve the unique circular edges
at the two axial boundaries of each gap and the connecting-rim radius. These
fillets add material; do not apply a convex edge-fillet volume-removal test.
With radial clearance below the tooth roots, each full ring adds
`2*pi*(Rc*r4^2*(1-pi/4) + r4^3*(5/6-pi/4))` in cubic millimetres.
Verify all `2*(n-1)` edge references, both radius properties, unchanged bounds,
one solid, and persistence after reopen.

Chain axial tooth-end cuts provide a concrete direction check: the owned blank
extruded from default YOZ occupies global X `[-CH_B, 0]`, not `[0, CH_B]`.
Its XOY rounding profiles must enter that interval from both end planes.
Mirroring the X coordinates also reverses each arc's `Direction`. A closed,
fully constrained sketch on the outside of the end face removes no material;
verify actual volume decrease for each cut and read back both arc endpoints.

Applies when:
- changing a baseline, plane, or sketch coordinate system that later operations
  depend on;
- fixing an early construction element in a working model.

Symptom:
- A local change appears correct but downstream geometry moves, flips, or
  becomes invalid.

Cause:
- KOMPAS operations store references to earlier coordinate systems, planes,
  sketches, and edges. Changing one early object changes every dependent object.

Rule:
- Treat early CS/plane/sketch changes as high blast-radius edits.
- After changing an early coordinate object, rebuild and verify every dependent
  operation.

Implementation:
```python
# Keep a short dependency list in the generator when changing early geometry.
affected = [angle_plane, center_sketch, bent_spiral, profile, evolution]

for obj in affected:
    obj.Update()
part.Rebuild()
```

Verification:
- Rebuild the full part, not only the changed object.
- Inspect dependent operations in creation order.

Known examples:
- `CASE-001`

---

### CS-004: Do Not Rely On Sketch Origin On API-Created Angled Planes

Applies when:
- creating `ISketch` on `IPlane3DByAngle`;
- a sketch must start from a known 3D point;
- geometry on an angled plane shifts after rebuild.

Symptom:
- The sketch is on the right plane but local `(0, 0)` is not where expected.
- A bent hook or auxiliary axis starts from an unstable or wrong point.

Cause:
- `IPlane3DByAngle` through API does not provide reliable control over the
  sketch local origin. In this context, `OriginPoint`, `BasePoint`, and `Point`
  properties for `ISketch` are unavailable or ineffective. Rebuild/recompute
  does not reproduce UI correction behavior.

Failed approaches:
- Explicitly setting `sketch.OriginPoint`.
- Calling `Part.Rebuild()` after plane creation.
- Replacing a sketch edge with a 3D axis in `BaseLine`.
- Reversing baseline edge direction as a stable origin fix.

Rule:
- Do not build important geometry from sketch `(0, 0)` on API-created angled
  planes.
- Project a known external 3D point into the sketch and build from that
  projection.

Implementation:
```python
center_sketch.AddProjectionOf(body_start_point)
proj_x, proj_y = center_sketch.GetPointProjectionToXY(body_start_point)

axis_start = (proj_x, proj_y)
axis_end = (proj_x, proj_y + 15.0)

axis_line = center_sketch.AddLine(axis_start, axis_end)
axis_start_point = center_sketch.AddPoint(*axis_start)
projected_point = center_sketch.GetObject("projected_point")

center_sketch.AddConstraint("vertical", [axis_line])
center_sketch.AddConstraint("merge_points", [axis_start_point, projected_point])
```

Verification:
- Rebuild after changing driving parameters.
- Confirm projected point and sketch geometry remain merged/constrained.

Known examples:
- `CASE-001`
- Local bent-coil investigation evidence (kept outside the public contract).

---

### CS-005: Assign Sketch Coordinate System Before Plane

Applies when:
- an `ISketch` must use the coordinate system of a custom plane;
- a generated sketch is created through COM rather than the KOMPAS UI;
- UI placement fields show unexpected `Offset X`, `Offset Y`, rotation, or axis
  direction after assigning `Sketch.CoordinateSystem`.

Symptom:
- The sketch is on the correct base plane, but the placement dialog shows
  non-zero offset or orientation fields.
- Projecting geometry into the sketch produces a visible shift relative to the
  source object.
- Values from sketch geometry or endpoint coordinates appear in sketch placement
  settings.

Cause:
- Setting `Sketch.CoordinateSystem` after `Sketch.Plane` makes KOMPAS preserve
  the current sketch placement by writing the delta into placement fields. This
  differs from the UI default for creating a new sketch on a plane.

Rule:
- If a sketch must use a plane's coordinate system, assign
  `Sketch.CoordinateSystem` before `Sketch.Plane`.
- Do not "fix" placement by adding compensating sketch coordinates or auxiliary
  geometry; correct the sketch placement order first.
- If a sketch should not use a custom coordinate system, do not set
  `Sketch.CoordinateSystem` at all.

Implementation:
```python
sketch = sketchs.Add()
sketch.Name = name

# Correct order for plane-local sketch coordinates.
sketch.CoordinateSystem = plane_object
sketch.Plane = plane_object
sketch.Angle = 0.0
sketch.LeftHandedCS = False
sketch.Update()
```

Verification:
- Open the sketch placement settings in KOMPAS.
- Confirm the base plane and coordinate system are selected, while offset,
  rotation, guide objects, and Z-axis direction fields are empty or zero.
- Project a known source object and confirm the projection is not shifted relative
  to the object.

Known examples:
- Extension spring self-wrapping right hook sketches.

---

### SKETCH-001: Fully Define Parameterized Sketches; Justify Numeric Exceptions

Applies when:
- a generated sketch drives a 3D operation;
- geometry changes unexpectedly after rebuild;
- a spring/coil/profile moves when parameters change.

Symptom:
- Sketch remains under-defined after dimensions are added.
- Regeneration moves geometry unexpectedly or fails.
- KOMPAS shows a misleading green fully-defined state on a complex sketch.

Cause:
- Dimensions are not the same as constraints. KOMPAS considers a sketch fully
  defined only when all geometric degrees of freedom are fixed. Some versions
  can also report a false positive fully-defined UI status.

Rule:
- Parameterize every dimension, relationship, and operation where complexity,
  rebuild reliability, and maintenance cost make it rational. Assess each sketch
  and operation separately; a numeric profile does not exempt simple blank,
  extrusion, placement, or pattern parameters from that assessment.
- Parameterized operational sketches must be fully constrained. Full definition
  and parameterization are distinct: fixing numeric geometry does not establish
  editable driving relationships.
- A numeric sketch that cannot reasonably be parameterized or fully constrained
  may have a local exception. Record the specific sketch, reason, editing limits,
  and alternative verification in its family contract. This is not a blanket
  exception for an entire module or permission to leave simple geometry free.
- Verify excepted geometry through actual curve/profile readback, direction,
  rebuild, and save/reopen stability rather than claiming a fully-defined solver
  state. Do not label the numeric profile parameterized or turn source metadata
  into driving variables. Example: a calculated cam profile can need numeric
  construction while its simple extrusion is assessed separately for parameterization.
- For the full module contract, see [English](docs/en/module-development.md) /
  [Русский](docs/ru/module-development.md), section 8. These are development
  requirements, not a claim that existing numeric generators already have driving bindings.
- Create sketch constraints inside the original `BeginEdit()` block, directly
  after creating the relevant geometry. `AddConstraint` after `EndEdit()` can
  return `None` without applying anything.

Implementation:
```python
sketch.BeginEdit()
line = sketch.AddLine(...)
point = sketch.AddPoint(...)

sketch.AddConstraint("merge_points", [point, projected_point])
sketch.AddConstraint("vertical", [line])
sketch.AddConstraint("fixed_length", [line], value=radius)

sketch.EndEdit()
```

Status check (API7 `ISketch`, verified v23 enum; see `SKETCH-011`):
```python
status = sketch.ConstraintsState  # ksConstraintsStateEnum
if status == 1:  # ksStateWellConstrained; 2 is ksStateUnderConstrained
    success = document.RebuildDocument()
```
Do not transfer this mapping to an API5 `GetStatus()` or drawing-object property
without checking its declared enum. A positive status is necessary on the strict
path, but not sufficient proof of driving relationships or geometric correctness.

Verification:
- Rebuild after dimensions and constraints.
- If over-defined, remove the last dimension/constraint and try the next most
  explicit one.
- If the API status is unavailable, verify by rebuild and by changing driving
  parameters.

Known examples:
- `compression_spring/v7`: the coil sketch was under-defined and moved when the
  outer diameter changed.
- `CASE-001`

---

### SKETCH-002: Projection Constraint References May Need UI Confirmation

Applies when:
- inspecting a known-good reference sketch;
- trying to reproduce constraints from an existing `.m3d` model;
- `inspect_sketch_full` identifies projection constraints but cannot identify
  what projected object they reference.

Symptom:
- Most sketch geometry, dimensions, and constraints are visible through the
  inspection tool.
- Projection constraints are identified, but the referenced source object is
  missing or ambiguous.

Cause:
- The sketch inspection tool has been expanded and can now capture almost all
  information available in a sketch. The remaining known gap is resolving the
  source object referenced by projection constraints.

Rule:
- Use `inspect_sketch_full` as the primary source for sketch geometry,
  dimensions, and constraints.
- When projection constraints are present, ask the user to inspect the sketch in
  the KOMPAS UI and identify which external objects the projections reference.
- Do not guess projection references from nearby geometry unless the relation is
  confirmed by coordinates or UI inspection.

Implementation:
```python
# Use full sketch inspection first.
sketch_info = inspect_sketch_full(reference_sketch)

for constraint in sketch_info.constraints:
    if constraint.type == "projection" and constraint.source is None:
        ask_user_to_check_projection_source_in_ui(constraint)
```

Verification:
- Compare inspected constraints with the KOMPAS UI when projection references are
  missing.
- For inferred projection sources, verify coordinates before generating code.

Known examples:
- Reference sketch inspection can identify projection constraints, but the user
  may still need to confirm what they project from in the UI.

Related:
- `SKETCH-003`

---

### SKETCH-003: Change Projected Sketch Entity Style Through API5 Hit-Test Refs

Applies when:
- a sketch entity was created by projecting another sketch edge with
  `ISketch.AddProjectionOf`;
- the projected result must become auxiliary/construction geometry;
- direct API7 style edits appear to work temporarily but revert after
  `EndEdit()` / `Update()`.

Symptom:
- `ILineSegment.Style = 6` on a projected line changes the value in the active
  edit session, but the line returns to style `1` after regeneration.
- `ksGetObjParam` / `ksSetObjParam` with `ko_LineSegParam = 11` does not read the
  projected entity by its API7 `Reference`.
- `ksSetObjectStyle(api7_reference, 6)` returns false or has no effect.

Cause:
- Projected sketch lines expose temporary drawing result objects through API7.
  The style persisted by the UI is applied through the 2D editor hit-test/object
  layer, not through the temporary `ILineSegment` or the API7 `Reference`.

Rule:
- Treat this like the UI does: hit-test the projected entity at a point on the
  line, get the internal API5 object reference, then change that object's style.
- Use a point away from intersections where possible, usually the line midpoint.
- Clean up the editor state after changing style.

Implementation:
```python
# target_sketch is the sketch containing projected entities.
# segment_geometry comes from inspect/readback of the projected segment.
target_sketch.BeginEdit()
doc2d = get_api5_active_document2d()

mx = (segment_geometry["start"][0] + segment_geometry["end"][0]) * 0.5
my = (segment_geometry["start"][1] + segment_geometry["end"][1]) * 0.5

found_ref = 0
for tolerance in (0.001, 0.01, 0.1, 1.0, 5.0, 20.0):
    found_ref = doc2d.ksFindObj(mx, my, tolerance)
    if found_ref:
        break

if not found_ref:
    raise RuntimeError("Projected object was not found by hit-test")

doc2d.ksSetObjectStyle(found_ref, 6)  # 6 = auxiliary/construction style.

# Conservative cleanup mirroring exit from UI-style object interaction.
doc2d.ksLightObj(found_ref, 0)
doc2d.ksEndObj()

target_sketch.EndEdit()
target_sketch.Update()
```

Verification:
- Inspect the sketch after `EndEdit()` / `Update()` and confirm `Style == 6`.
- Do not trust the in-session value before regeneration.
- Check `ksSetObjectStyle` and final readback; successful live examples changed
  both projected diagonal and projected shelf from style `1` to style `6`.

Known examples:
- `self_wrapping_phase2_first_and_projected_sketch1_v24`: projected diagonal and
  projected shelf in `SELF_WRAPPING_PHASE2_LEFT_SKETCH1_PROJECTED` were changed to
  auxiliary style through `ksFindObj` + `ksSetObjectStyle`.

Related:
- `SKETCH-002`
- `EDGE-002`

---

### SKETCH-004: Sketch Edit Session Lifecycle

Applies when:
- creating a sketch that will contain dimensions, constraints, projected entities,
  or helper construction geometry;
- adding geometry that later 3D operations depend on;
- changing an existing sketch through automation.

Symptom:
- Geometry is created, but later constraints silently fail.
- Projected objects are visible in KOMPAS but cannot be found through ordinary
  API7 collections after reopening the sketch.
- The same operation works in the UI but not through a direct object call.

Cause:
- KOMPAS exposes different object layers at different moments: model API7
  objects, active 2D-editor API5 hit-test refs, and temporary objects returned
  during `BeginEdit()`.
- Some handles are only reliable while the sketch edit session that created them
  is still open.

Rule:
- Treat a sketch edit as a transaction. Create geometry, keep returned COM
  objects, add constraints/dimensions that need those objects, then `EndEdit()`
  and `Update()`.
- Do not throw away returned geometry handles if the next step must constrain to
  that geometry.
- Reopen/readback is for verification and UI-like edits, not for guessing the
  original creation handles.

Implementation order:
```python
target_sketch = create_or_find_sketch(part, plane)
edit_doc = target_sketch.BeginEdit()
drawing = get_sketch_drawing_container(edit_doc)

created = {}
created["base"] = add_line(drawing, p1, p2, style=6)
created["axis"] = add_line(drawing, p3, p4, style=3)
created["point"] = add_point(drawing, p4, style=127)

add_constraints(created)
add_dimensions(drawing, created)

target_sketch.EndEdit()
target_sketch.Update()
part.Update()

snapshot = inspect_sketch_full(target_sketch)
assert snapshot.constraints_state == "fully_defined"
```

Verification:
- Use `inspect_sketch_full` after `EndEdit()` / `Update()`.
- Verify entity count, styles, dimensions, dimension expressions, constraint
  count, and `constraints_state`.
- Reopen the saved file for final proof when the model is meant to be inspected
  later.

Known examples:
- `self_wrapping_phase2_first_and_projected_sketch1_v48`: constraints and
  dimension were reliable after being created before the edit session ended.

Related:
- `SKETCH-001`
- `SKETCH-005`
- `SKETCH-008`

---

### SKETCH-005: Add Constraints While The Required Handles Are Still Live

Applies when:
- constraining generated lines, points, projected geometry, or helper axes;
- a later `BeginEdit()` cannot see entities through `LineSegments` / `Points`;
- `NewConstraint()` or `Create()` returns false after a sketch was closed.

Symptom:
- A constraint can be described geometrically, but KOMPAS does not create it.
- API7 collections are empty or incomplete after reopening a generated/projected
  sketch.
- API5 `ksFindObj` finds a visible object, but `ksSetObjConstraint` still returns
  `0`.

Cause:
- Visibility in the UI and suitability as a COM constraint partner are not the
  same thing.
- The safest constraint partners are the COM objects returned by geometry
  creation calls in the active edit session.

Rule:
- Add ordinary geometric constraints immediately after creating the affected
  entities.
- For projected geometry, add constraints to projected result objects in the same
  `BeginEdit()` session as `AddProjectionOf` when possible.
- Use API7 `NewConstraint()` / object-specific constraint helpers for live API7
  geometry. Use API5 hit-test refs for UI-like style/selection operations, not as
  the first choice for geometric constraints.

Implementation:
```python
edit_doc = sketch.BeginEdit()
drawing = get_sketch_drawing_container(edit_doc)

line_a = add_line(drawing, a1, a2, style=6)
line_b = add_line(drawing, b1, b2, style=6)
axis = add_line(drawing, x1, x2, style=3)

add_constraint(line_a, "vertical")
add_constraint(line_a, "merge_points", index=1, partner=line_b, partner_index=0)
add_constraint(axis, "point_on_curve", index=0, partner=line_a)
add_constraint(axis, "point_on_curve", index=0, partner=line_b)

sketch.EndEdit()
```

Verification:
- Inspect readback constraints after rebuild.
- Verify intended owner/partner geometry, not only raw count.
- A created constraint with the right count but wrong endpoint is still wrong.

Known examples:
- In the self-wrapping sketch, post-factum constraints on reopened projected
  geometry failed, while creation-time constraints produced a fully defined
  sketch.

Related:
- `SKETCH-004`
- `SKETCH-006`
- `SKETCH-007`

---

### SKETCH-006: Project Geometry First, Then Constrain To The Projection Results

Applies when:
- a sketch must reference geometry from another sketch;
- projected geometry is used as a stable construction base;
- a projected point is unavailable and a projected edge is used as fallback.
- a visible projected `IPoint3D` is required in the sketch, not just projected XY
  coordinates.

Symptom:
- Projection appears in the sketch, but dependent helper geometry is not fully
  fixed.
- Constraints to projected entities fail when added in a later bridge call.
- A fallback projected line adds more degrees of freedom than a point-like
  reference would.
- `GetPointProjectionToXY(point3d)` returns correct XY coordinates, but the
  sketch contains no visible projection point.
- `AddProjectionOf(point3d)` returns `None` when called outside the active sketch
  edit session.

Cause:
- `ISketch.AddProjectionOf` returns result objects that are most useful while the
  current edit session is still active.
- For `IPoint3D`, `AddProjectionOf(point3d)` may only create/return the visible
  projected `IPoint` when called inside `sketch.BeginEdit()`.
- Projection constraints bind projected entities to their sources; extra manual
  fixation of the projected entities is usually wrong. Helper geometry should be
  constrained to the projection results instead.

Rule:
- Open the target sketch once.
- Call `source_sketch.Edges(...)` to get source `IEdge` objects.
- Call `target_sketch.AddProjectionOf(edge)` inside the active target sketch edit
  session.
- For a 3D point, call `target_sketch.AddProjectionOf(point3d)` inside the same
  `BeginEdit()` session where possible. Calling it before edit may still allow
  XY readback, but can fail to create a visible projection object.
- Keep the returned projected result objects and use them immediately as partners
  for helper-geometry constraints.
- Normalize the `AddProjectionOf` return value before use: KOMPAS may return a
  single COM object, a Python list/tuple, or a COM collection depending on the
  source edge and API wrapper state.
- Do not add dimensions or duplicate formulas to projected geometry just to mimic
  the source; the projection link is the source of truth.

Implementation:
```python
edit_doc = target_sketch.BeginEdit()
drawing = get_sketch_drawing_container(edit_doc)

projected_diagonal = target_sketch.AddProjectionOf(source_diagonal_edge)[0]
projected_shelf = target_sketch.AddProjectionOf(source_shelf_edge)[0]

vertical_base = add_line(drawing, top, bottom, style=6)
mirror_diagonal = add_line(drawing, bottom, shelf_free, style=6)
axis = add_line(drawing, intersection_hint, shelf_free, style=3)

add_constraint(vertical_base, "merge_points", index=0,
               partner=projected_diagonal, partner_index=projected_top_index)
add_constraint(mirror_diagonal, "merge_points", index=1,
               partner=projected_shelf, partner_index=projected_free_index)
add_constraint(axis, "point_on_curve", index=0, partner=projected_diagonal)
add_constraint(axis, "point_on_curve", index=0, partner=mirror_diagonal)
```

For `IPoint3D`, do not replace the projection with a manually drawn sketch point:

```python
edit_doc = target_sketch.BeginEdit()
drawing = get_sketch_drawing_container(edit_doc)

projected_point = normalize_projection_result(
    target_sketch.AddProjectionOf(source_point3d)
)

vertical_base = add_line(drawing, projected_xy, bottom, style=6)
work_diagonal = add_line(drawing, projected_xy, diagonal_end, style=1)

add_constraint(vertical_base, "merge_points", index=0,
               partner=projected_point, partner_index=0)
add_constraint(work_diagonal, "merge_points", index=0,
               partner=projected_point, partner_index=0)

target_sketch.EndEdit()
```

Verification:
- `inspect_sketch_full` should show projection constraints and the helper
  constraints that depend on them.
- For projected 3D points, `inspect_sketch_full` should show a projected point
  object, typically with style `127`, parent projection chain, and the UI
  projection constraint.
- Confirm projected entities remain projected after rebuild.
- If a whole projected edge was used as fallback for a point, inspect the final
  constraint state carefully; a true projected point/vertex is preferable when
  available.

Known examples:
- `self_wrapping_phase2_first_and_projected_sketch1_v48` uses projected diagonal
  and shelf references as construction bases, then constrains helper geometry to
  them before closing the sketch.
- `right_first_sketch_endpoint_v15` creates a visible projection of the right
  spiral endpoint point and uses it as the anchor for the first right
  self-wrapping sketch.

Related:
- `SKETCH-002`
- `SKETCH-003`
- `SKETCH-005`

---

### SKETCH-007: Reading Or Editing An Existing Sketch Requires UI-Like State

Applies when:
- changing a sketch after it already exists;
- inspecting a saved/reopened model;
- a visible UI object is not available through ordinary API7 collections.

Symptom:
- KOMPAS UI can edit or select an object, but automation cannot find it through
  `LineSegments`, `Points`, or a stored API7 reference.
- Direct COM calls work on newly created objects but fail after reopening.

Cause:
- KOMPAS UI operations often go through the active 2D editor selection/hit-test
  layer. Direct API7 model collections are not always the same surface.

Rule:
- For readback, use `inspect_sketch_full` first.
- Public read-only inspection uses `WriteToFragment` and does not activate the
  API5 editor. An empty constraint list with `coverage.api5_constraints_available`
  false is unavailable evidence, not proof that constraints are absent. Creation
  finalizers that must verify an actual API5 constraint explicitly pass
  `update_before_state=True` on their owned newly created sketch; do not change the
  public reader's non-mutating default.
- `BeginEditEx(True)` is not state-neutral: live M20×2.5 changed native
  ConstraintsState1→2 at BeginEditEx while Changed remained false. Closing its
  fragment, EndEdit, Refresh and Rebuild did not restore state; editing the actual
  parametric definition exposed151links/7dimensions and returned code1, but marked
  Changed. Do not compensate by adding duplicate constraints or resetting flags.
  Read a separately exported `.frw`, close it and delete only that owned temporary
  file. KOMPAS may hold its parent-directory handle: use a unique file in an
  existing temp directory, not a disposable directory whose rmdir can fail.
  Exported entity references are fragment-local, not source-edit selectors. Source
  ConstraintsState/Changed and previous active document must remain unchanged.
  This is verified on metric thread driver/reopen and gear/spline/polygon/flat-hole
  chain geometry regressions. Empty fragment API5 data stays unavailable evidence.
- For UI-like edits, activate/open the target document and sketch, then use API5
  active-document operations such as `ksFindObj` when a direct API7 object is not
  available.
- Treat hit-test refs as editor-layer refs. They are proven useful for style and
  selection-like edits; do not assume they are valid partners for all geometric
  constraints.

Implementation:
```python
snapshot = inspect_sketch_full(sketch)

sketch.BeginEdit()
doc2d = get_api5_active_document2d()
ref = doc2d.ksFindObj(x_on_entity, y_on_entity, tolerance)
if not ref:
    raise RuntimeError("Object is visible but not found by editor hit-test")

# Use the editor-layer operation that matches the UI action.
doc2d.ksSetObjectStyle(ref, 6)
doc2d.ksLightObj(ref, 0)
doc2d.ksEndObj()
sketch.EndEdit()
```

Verification:
- Re-inspect after `EndEdit()` / `Update()`.
- For saved artifacts, close and reopen the file, then inspect again.

Known examples:
- Projected style changes require API5 hit-test refs (`SKETCH-003`).
- A reopened projected sketch can be visible but not expose the same editable
  API7 line collection as during creation.
- Chain-sprocket finalization: the read-only fragment reported zero API5
  constraints, while editor-backed readback found the actual segment-to-datum
  `point_on_curve` pair and a closed contour. Roller single/two-row and bush
  creation plus recipe save/reopen pass with explicit editor-backed verification.

Related:
- `SKETCH-003`
- `SKETCH-005`

---

### SKETCH-008: Save After Late Sketch Edits And Verify From Disk

Applies when:
- a script creates a model, then adds sketches/projections/constraints in later
  bridge calls;
- KOMPAS remains open with unsaved changes;
- a user needs to inspect the resulting `.m3d` file later.

Symptom:
- The live KOMPAS session shows the expected sketches, but the saved file misses
  late-created sketches after KOMPAS is closed.
- Reports/snapshots show geometry that is not present in the reopened `.m3d`.

Cause:
- An early save during base model creation does not include later sketch edits.
- Closing KOMPAS without a final save discards those late edits.

Rule:
- Always save after the last sketch/projection/constraint/dimension operation.
- For important artifacts, close or reopen the document and verify the saved file
  from disk.
- Do not treat a JSON snapshot from a live session as proof that the `.m3d` file
  contains the same state.

Implementation:
```python
build_base_model()
add_sketches_and_constraints()
snapshot = inspect_sketch_full(target_sketch)

save_document(document_id=document_id, path=output_path, close_after_save=True)

opened = open_document(output_path)
saved_snapshot = inspect_sketch_full(opened_target_sketch)
assert saved_snapshot.summary == snapshot.summary
```

Verification:
- Reopen the saved `.m3d` and list sketches by name.
- Inspect the important sketch and confirm entity counts, styles, constraints,
  dimensions, and state.

Known examples:
- `self_wrapping_phase2_first_and_projected_sketch1_v47` was the first artifact
  verified to save both sketches after final edits.
- `self_wrapping_phase2_first_and_projected_sketch1_v48` was verified from disk
  as fully defined with auxiliary projected/reference geometry.

Related:
- `SKETCH-004`
- `VERIFY-001`

---

### SKETCH-009: Model Symmetric And Repeated Elements As Master/Dependent Families

Applies when:
- a sketch contains mirrored features, repeated grooves, holes, teeth, slots, or
  other equal-shape elements;
- multiple elements share center axes, radial/axial levels, widths, radii, or
  edge/pitch spacing;
- copied geometry looks correct but should remain associative after parameter
  changes.

Symptom:
- every copy has its own duplicate dimensions and variables;
- the sketch contains display-only dimensions or helper geometry that does not
  influence the consumer profile;
- an equal/merge/symmetry relation is planned but reported as skipped or
  redundant;
- dependent copies drift independently or remain visually equal only because
  their seed coordinates were copied.

Cause:
- copies were treated as independent profiles instead of one parametric family;
- master ownership and symmetry/repetition axes were not declared before
  constraints/dimensions;
- initially coincident/equal seed geometry made the intended family relation a
  no-op for the solver;
- compatibility fallback dimensions were numeric rather than formula-linked to
  a master variable.

Rule:
- Choose one master element and dimension its independent shape parameters.
- Position dependents through named midpoint/symmetry, edge-offset, and pitch
  relations.
- Inherit dependent shape through equal length/radius, parallel, collinear, and
  shared-level constraints.
- An explicitly declared graphical symmetry axis may use axis style when no
  consumer ambiguity exists. Keep multiple family center/symmetry lines
  auxiliary inside an operational sketch; a revolve sketch still has exactly
  one axis-style consumer axis.
- A dependent driving dimension is allowed only when independently meaningful or
  when KOMPAS rejects the native family relation. In the latter case its
  expression must reference the master semantic variable.
- Use a bounded seed offset when necessary so an intended merge/equal relation is
  actually created, then verify that the final readback contains the exact
  relation and no seed offset.
- Do not accept skipped family constraints. Remove a truly redundant relation or
  move it to a pre-constraint phase where it owns the intended datum.
- Keep no orphan per-copy variables: every published variable binds a surviving
  dimension or is consumed by another kept formula.

Implementation shape:
```text
declare master profile and dependent family
create auxiliary center/symmetry axes
anchor global/base datum
apply master topology and shape constraints
apply edge/pitch placement and midpoint relations
apply equal/collinear/shared-level inheritance
dimension master
if native inheritance is unstable:
    bind dependent_dimension.Expression = master_variable_name
assert applied_pre == planned_pre and skipped_pre == 0
assert applied_final == planned_final and skipped_final == 0
assert applied_dimensions == planned_dimensions
assert every surviving dimension has a valid semantic expression
```

Verification:
- `ConstraintsState == 1` (`ksStateWellConstrained`) after solver settle and
  save/reopen. Earlier code-2 evidence needs reassessment under `SKETCH-011`.
- Intended component count and profile topology are unchanged.
- Master/dependent centers and shared levels match readback.
- Applied counts equal planned counts; skipped/failed counts are zero.
- No duplicate reference-only dimensions, unused helper constructions, or orphan
  family variables remain.

Known example:
- The two-groove V-belt cut uses one dimensioned master groove, auxiliary groove
  axes, midpoint/shared-level relations, edge/pitch placement, and one
  formula-linked dependent top-width dimension. Cleanup reduced the operational
  sketch from 13 to 8 dimensions and from 20 to 10 semantic variables while
  preserving exact volume and fully-defined readback.

Related:
- `SKETCH-001`
- `SKETCH-005`
- `VAR-001`
- `OP-002`

---

### SKETCH-011: Decode Sketch State From The Native Enum, Not An Assumed Numeric Scale

Evidence: live type-library readback of KOMPAS v23 `ISketch.ConstraintsState`
and active-editor object inspection on the standalone flat-step probes.

Symptom: the user sees a fully defined profile and every inspected drawing object
is fully defined, while a host check rejects sketch code 1. A temporary code 2
after placement/rebuild is incorrectly reported as success.

Cause: the existing `_describe_constraints_state` decoder reverses the two native
values. `ISketch.ConstraintsState` returns `ksConstraintsStateEnum`:

| Native value | Type-library constant | Meaning |
| --- | --- | --- |
| 0 | `ksStateUnknown` | Unknown |
| 1 | `ksStateWellConstrained` | Fully defined |
| 2 | `ksStateUnderConstrained` | Has degrees of freedom |
| 3 | `ksStateUnresolvedRedundancy` | Conflicting constraints |

Rule: inspect the property's declared return enum and use its named constants.
Do not confuse sketch state with drawing-object state or treat a stored label as
fresh verification. Full definition still requires driving geometry and rebuild/
save/reopen evidence; do not numerically fix entities to satisfy a wrong predicate.

Implementation: the shared decoder and sketch-state gates now use the verified
mapping in both bridge copies and host consumers. Drawing-object decoding remains
separate. The flat-step probe passes separate D/L/F driver changes, restoration
and actual reopen for one and two flats. Earlier family claims based only on code
2 are not evidence of full definition and need new live review; correcting host
logic does not revalidate those models or invalidate their geometric readback.

Verification: retain bounded type-info evidence of the enum names/values; inspect
the exact active editor; reject native under-constrained code 2; verify real
diameter/length/profile drivers and actual save/reopen on the corrected path.

Fresh read-only review of retained legacy controls confirms the distinction:
the control cone reads native sketch code 1 with all four drawing objects full;
the saved angle-driver pentagon, hexagon and triangle each read native sketch
code 2, despite closed geometric contours and earlier successful driver/volume
checks. Document identities, paths and changed flags remain unchanged. This is
current open-state evidence, not a fresh driver/save/reopen certification or a
claim about every input mode. A read-only fragment may expose ordinary object
state 0 and no API5 constraint channel; those incomplete diagnostics do not prove
that constraints were lost or identify a particular missing degree of freedom.
Diagnose in the actual owned editor context before choosing any correction.

An editor follow-up on separate disk copies of these three polygon controls
reads 37/43/21 API5 constraint records (pentagon/hexagon/triangle). The existing
`Update` then `BeginEdit`/`EndEdit` inspection cycle changes the subsequent native
sketch readback from code 2 to code 1, without adding constraints or changing the
read-back entity coordinates. The inspection's own state field is captured
before that editor cycle finishes; read the native sketch again afterwards.
This proves a reproducible state-refresh effect, not a particular missing
constraint or persistent repair. Source files and documents remain unchanged;
the copies are not saved. Require driver changes and actual save/reopen before
certifying stable full definition, and do not introduce numeric fixing merely
to turn a pre-editor state into success.

A subsequent driver/reopen preflight on the same triangle diagnostic copy reads
native `ISketch.ConstraintsState=2` again and stops before any variable write,
save or close. A separate same-reference interface comparison confirms that
`IModelObject` does not expose this property, while the explicit `ISketch` returns
2. The earlier post-editor code 1 is therefore not stable full-definition proof.
Do not infer another enum reversal, missing constraints, or a certified repair
from this transition; require a consistent typed readback before driver testing.

The user then manually activated the triangle diagnostic sketch and confirmed
the UI changed to fully defined, identifying a known KOMPAS status-refresh issue
on API-created sketches. An activation-aware driver audit subsequently verifies
D/L/angle changes to 36/26/31 degrees, restoration to 24/17/23 degrees, exact
vertices/volume, and actual save/close/reopen on that copy. Changed/restored states
and the first native read after reopen are code 1. An additional programmatic
`BeginEdit`/`EndEdit` after reopening changes that status to code 2 without changing
the read-back geometry. Thus editor activation is not an unconditional repair:
record typed states before/inside/after it, preserve independent driver/geometry
evidence, and do not add freezing or missing-constraint claims from the flag alone.
The complete activation-aware probe remains failed at its final status gate;
do not conflate passing driver/reopen geometry with stable status certification.

Separate geometry-audit runs on the hexagon and pentagon copies also pass
diameter/length/angle changes to 36/26/31 degrees, restoration, exact vertices,
one-body volumes and actual save/close/reopen. Original source files, saved
recipes and foreign document states are preserved. Native code 2 remains at all
logged stages for these two controls, including programmatic activation; their
results explicitly separate `geometry_verified=true` from
`fully_defined_verified=false`. This mode is an evidence-gathering diagnostic,
not a relaxation of production full-definition gates or proof of every input.

A fresh saved-file review on separate read-only copies of three shaft and five
diaphragm controls preserves native geometry, recipes, source/copy file hashes
and pre-existing documents. Shaft profiles read code 2 before/after primary
inspection. Each diaphragm base reads code 2; the three other named roots read
code 1 initially and code 2 after primary read-only inspections, with unchanged
volume/recipe/disk files. Keep these transient status observations separate from
geometric preservation and driver certification. Diaphragm enumeration is bounded
to20 entries and also returns unnamed state0 records; those are not identified or
certified, and this is not exhaustive sketch coverage or proof of lost constraints.

A subsequent independent D1/L1 audit on a new writable three-step shaft copy
verifies diameter 30 to34 and back, then length 20 to24 and back, every trimmed
cylinder radius/span, analytical volume and actual save/close/reopen. Native code2
remains separate from this successful geometric/driving evidence. An owned-editor
audit of a no-bend diaphragm copy finds all12dimension-variable links across its
four named sketches, including base radius/thickness/cone-height formulas and
slot/relief drivers. API5 constraint records are available in that editor context.
These links are real readback, not proof that every diaphragm driver rebuilds
correctly; no diaphragm parameter changes or saved edits are performed in that
association audit. Sources and foreign documents remain unchanged.

The no-bend diaphragm follow-up subsequently verifies cone height6 to7 and back
using actual body bounds, then slot-entry width4 to5 and back using transverse
sketch geometry, the coupled start radius and increased material removal. The
restored copy passes actual save/close/reopen with its recipe, CH6/W4, bounds and
volume preserved. A measured restored-volume difference of about3.54e-6cm3 is
inside the existing production criterion max(1e-7,reference*1e-5); an earlier
diagnostic absolute1e-6 gate was unnecessarily stricter. Preserve measured deltas
before rejecting restoration, and do not loosen unrelated geometric checks.
This is representative no-bend driver evidence, not every-parameter/bent-variant
or full-definition certification. Sources and foreign documents remain unchanged.

Bent controls subsequently pass owned-editor association readback(15/18/19
dimension links for single-bend/S-circle/S-oval) and independent first bend
radius8 to9 and back; both S-controls also pass second radius7 to8 and back.
Actual inner/outerarc radii follow normal thickness3, bodyvolume responds while
protected bounds remain stable, and complete original profile geometry is
restored. All three pass actualsave/close/reopen, recipe/source/foreign preservation
and the existing volume tolerance. Nativebasecode2 remains separate from this
representative geometric driver proof; neither all-parameter coverage nor full
sketch-definition certification is implied. No public in-place editing is added.

For the current legacy review, the user accepts the API/UI full-definition flag
instability as a KOMPAS limitation and closes further attempts to repair that
indicator. Retain its raw meaning; do not relabel code2 as code1 or freeze geometry
to satisfy it. Continue independent body, parameter-link, rebuild and saved-file
verification. This review decision does not silently change production gates or
override genuine operation/geometry errors; functional driving limitations remain
separate from the indicator issue.

### SKETCH-010: Do Not Re-Merge An Already Owned Profile Node Through Auxiliary Geometry

Applies when an operational contour endpoint is already joined to its neighbor
and an auxiliary locator is added to the same solved point.

Symptom:
- all entities and constraints are individually valid, but KOMPAS spends minutes
  inside sketch parameterization or never returns from the solve;
- removing one auxiliary `merge_points` relation makes the same dimensions and
  production contour settle immediately.

Cause:
- the auxiliary entity creates a redundant cyclic ownership path through a node
  already owned by the primary contour topology;
- the cycle is especially expensive when tangent arcs, datum circles, and
  formula-bound radii also meet at that node.

Rule:
- merge every primary contour junction exactly once;
- constrain auxiliary geometry to independent datums, midpoints, or curves;
- do not attach an auxiliary endpoint to a primary node merely to restate a
  direction that is already implied by tangent/closure constraints;
- isolate cumulative constraint groups with bounded live probes when solve time
  changes abruptly.

Verification:
- all planned constraints and dimensions apply without skips or failures;
- `ConstraintsState == 1` (`ksStateWellConstrained`), primary-contour preflight passes, and save/reopen is
  stable;
- change one driving variable and confirm the intended geometry moves while the
  contour remains closed.

Known example:
- the parameterized T/AT timing-pulley groove stalled when left/right auxiliary
  radial lines were merged into tip-arc endpoints already joined to closure
  segments. Removing those duplicate radial ownership links and locating one
  outside-material closure point by its leg length plus a
  formula-bound aligned distance from the fixed datum center, and making the
  opposite leg equal, retained a fully defined profile without the ownership
  cycle. Geometric `vertical`, deferred-angle, and X/Y coordinate variants all
  stalled; the two ordinary linear dimensions removed the same freedom without
  another curve-relation cycle.
- the chain-sprocket tooth space uses independent centre spans and coordinates as
  sketch dimensions. Its master roller-seat, flank, and head arcs require
  formula-bound driving radii; mirrored working arcs inherit equal radius, and
  the six working branch junctions carry tangent relations in addition to their
  single topology merge. A green solver state produced only by fixed centers and
  merged seed endpoints is not accepted as engineering parameterization. Apply
  these relations in staged groups and require exact counts, radial-dimension
  readback, a fully defined sketch, contour preflight, and save/reopen stability.
  For the offset variant, classify a seat by its physical branch endpoints rather
  than collection order: the right seat center must read back at `+e/2`, the left
  at `-e/2`, and each secondary-flank center must preserve its specified vector
  from that same seat center. A successful solve alone does not detect an inward,
  side-swapped construction.
- keep the chain sprocket's non-working closure linear, but never locate its top
  line by a fixed overshoot from the side intersection. Set the line level to
  `outside_radius + 0.5 mm`; its closest point to the axis then has a guaranteed
  0.5 mm clearance from every supported blank. Two equal vertical overshoots of
  driving length `CH_CO` connect that line to the working profile. Show the line
  length as reference dimension `CH_CW`; a driving width dimension closes another
  ownership loop and stalls numeric profile parameterization. A pair of mirrored
  closure arcs introduced an unnecessary intermediate node, while every tested
  single-arc constraint network also stalled in KOMPAS. Treat the
  GOST/KOMPAS-derived `r`, `r1`, `r2`, offset, and tangent construction as the
  functional profile; the outside cap is host-owned technical geometry.
- For offset chain seats, trim each arc at its lower tangent point and join the
  two points by one horizontal segment. Joining the circles at their intersection
  leaves a central bump of `r - sqrt(r*r - (e/2)*(e/2))`. Native-model readback
  confirmed two collinear half-segments totaling `e=0.381 mm`, tangent to both
  `r=4.326275 mm` seats. Our parametric sketch uses one segment, two endpoint
  merges, horizontal orientation, and two tangencies; its length is dependent on
  the centre span, not separately dimensioned. Omit this segment when `e=0`.
  Keep the seat-centre height at the pitch radius in both variants. The former
  correction `sqrt(r*r-(e/2)*(e/2))-r` preserved an obsolete circle-intersection
  root and shifted all offset working branches inward after adding the tangent
  bottom. Bounded comparison against native PR/PV/NP/TP/08B examples confirms
  centres, radii and internal junctions within 0.000001 mm after removing it.
  This is native-reference evidence, not independent normative certification.
- A chain tooth-head endpoint constrained to the outside datum must be seeded
  on that exact circle. Intersecting `r2` with a larger technical closure circle
  makes Studio draw a radial bridge and asks KOMPAS to repair the contour during
  the final `point_on_curve`; at high tooth counts that relation can be
  impossible and leave pointed teeth. Keep the three-segment cap outside the
  body, but compute the working head endpoint on the functional outside circle.
  Checking one head arc is not sufficient: compare the outside radius with the
  outer intersection of that branch and the rotated opposite `r2` branch from
  the neighboring tooth space. If the outside circle comes later, the circular
  pattern overlaps the cuts and leaves a pointed tooth although every seed
  sketch is closed. For PRI with `lambda > 2`, the measured native KOMPAS rule
  `K=0.532` keeps a positive radial margin through `z=6..200`; report that rule
  as compatibility behavior rather than normative GOST 591 geometry.
- do not classify a bridge timeout as a failed CAD constraint without preserving
  and inspecting the live document. For the chain sketch, a final type-2
  `point_on_curve` from point 0 of the right technical side line to the outside
  datum did not return within 90 seconds, yet independent `inspect_sketch_full`
  found the relation applied and the sketch `fully_defined`, closed, gap-free,
  and free of self-intersections. Saving and reopening this candidate preserved
  the type-2 relation but reported `under_constrained` in one automated readback.
  The user then confirmed both saved and unsaved sketches fully defined in visible KOMPAS;
  the probe had not required a visible session (see `SESSION-001`). Do not infer
  constraint loss from that conflicting readback. The production chain workflow
  now creates all features first, applies this one relation in an isolated bridge
  call, and independently verifies the exact reference pair and contour topology.
  Preserve both the unsaved live state and a saved artifact when investigating
   future solver discrepancies. This historical label conflict may also involve
   the reversed sketch-state decoder (`SKETCH-011`); the original raw codes and
   declared interface must be checked before attributing it to KOMPAS unreliability.

---

### DIR-001: Direction Parameters And Sketch Directions Require Verification

Applies when:
- setting operation direction flags;
- creating extrusions, cuts, offset planes, chamfers, or spirals;
- creating sketch geometry whose direction matters;
- the result is valid but on the wrong side or reversed along a local axis.

Symptom:
- Operation succeeds, but the result is mirrored or built in the opposite
  direction.
- Sketch line, arc, or curve direction is reversed relative to the intended
  construction axis.
- KOMPAS does not report an error.

Cause:
- The API accepts direction as numbers, enums, or booleans but does not check
  whether the result matches the intended geometry context.
- Sketch entities and curves can also be direction-sensitive. A valid entity can
  still have the opposite start/end order, arc sweep, or local-axis relation.

Rule:
- After any operation with a direction parameter, verify it.
- After creating direction-sensitive sketch geometry, verify start/end order,
  arc sweep, and relation to local axes.
- For spirals, keep winding direction and construction direction separate.

Known direction fields:

| Operation | Parameter | Values | Note |
|---|---|---|---|
| Extrude | `directionType` | `True` forward, `False` backward | relative to sketch normal |
| Cut | `directionType` | `True` forward, `False` backward | relative to sketch normal |
| Offset plane | `direction` | `1` normal, `-1` opposite | |
| Spiral winding | `buildDirection` | `-1` left, `1` right | enum may also be used |
| Spiral construction side | distance sign / placement | positive or negative side | separate from winding |
| Chamfer | `direction` | `True` along, `False` across | operation-specific |

Verification:
- Prefer readback of operation parameters.
- If readback is unavailable or insufficient, use `VERIFY-001`: create temporary
  probe points, read coordinates, compare expected relations, then delete probes.

Known examples:
- `extension_spring/bent_coil_left_spike_v33`: hook spiral built downward because
  construction direction was wrong; winding direction was a separate parameter.

Related:
- `VERIFY-001`
- `SPIRAL-001`

---

### GAP-001: Zero Gap Can Produce Solid Self-Intersection

Applies when:
- generating springs or coils;
- requested gap is zero or effectively zero;
- adjacent turns touch exactly.

Symptom:
- KOMPAS reports a self-intersecting body.
- The geometry looks mathematically valid but solid creation fails.

Cause:
- At exactly zero clearance, adjacent coil surfaces meet at the same point/line.
  The solid modeler can classify this as self-intersection.

Rule:
- Use an explicit positive clearance policy when non-touching CAD turns are
  required. Preserve requested nominal wire dimensions.
- `0.01 mm` is a verified starting axial increment for the compression control
  cases below, not a universal minimum surface clearance or manufacturing tolerance.
- Do not silently clamp an explicit zero. Report contact/self-intersection when
  the native solid is invalid, and let the caller choose an increment.

Implementation:
```python
gap = 0.01 if requested_gap is None else requested_gap
```

Known examples:
- `compression_spring`: models with no clearance between turns produced
  self-intersection errors.
- Compression integration (2026-10): mean30, wire4, height48, working turns5,
  closed ends1, ground ends0.5 failed for both hands with `IFeature7.Valid=False`
  and `ObjectError=31` (SDK `ErrorType3d.et3dError31`: object self-intersects),
  despite successful evolution Update and positive cached volume. A diagnostic
  profile diameter3.98 on unchanged pitch4 helices removed the error before ground
  cuts and through save/reopen. This is not permission to shrink nominal wire or
  silently clamp engineering inputs: an explicit clearance policy is required.
  The shared compression interface refuses an invalid native sweep before saving.
  Its explicit `end_pitch_gap` now defaults to0.01 mm (legacy absence remains0),
  driving `EG1` and `EP1=WD1+EG1`. Both cylinder hands pass with nominal wire4 and
  end pitch4.01; changing EG1 to0.02 yields4.02 and survives rebuild/save/reopen.
  This is an axial pitch increment, not a certified minimum surface distance.
  Explicit zero is preserved and may be refused; no hidden wire shrink is used.

---

### EDGE-001: Resolve Sketch Points Through IFeature7.ModelObjects

Applies when:
- a 3D operation asks for a reference point;
- the natural source point exists only inside a sketch;
- UI accepts a sketch point as a 3D reference.

Symptom:
- Passing the transient `IPoint` or `CastTo(point, "IModelObject")` to
  `IPoint3DParamProjection.SetAssociationVertex(...)` is accepted by the
  setter, but `Point3D.Update()` returns `False`.

Cause:
- An `IPoint` obtained inside `BeginEdit()` is a transient drawing wrapper. Its
  reference becomes invalid after `EndEdit()`.
- The persistent UI-selectable object is a result vertex owned by the sketch:
  `IModelObject.Type=11279`, `ModelObjectType=8`.
- The owner sketch exposes these objects through
  `IFeature7.ModelObjects(8)`, where `8` selects result vertices.

Rule:
- Create the 2D point normally, finish and update the sketch, then cast the
  sketch itself to `IFeature7`.
- Enumerate `ModelObjects(8)` and identify the required `IVertex` by
  `IVertex.GetPoint()` world coordinates. Do not rely on array order.
- Pass that `IVertex` directly to `SetAssociationVertex(...)`.
- Do not create a coordinate-copy `Point3D` or point-on-curve intermediary when
  the intended source is an explicit sketch point.
- Verify after reopen that the projection point source has `Type=11279`, its
  `Owner` is the reference sketch, and its reference matches one of
  `sketch_feature.ModelObjects(8)`.

Implementation: direct sketch point to projection point
```python
# Add IPoint objects while the sketch is open, then EndEdit()/Update().
sketch_feature = win32com.client.CastTo(sketch, "IFeature7")
vertices = list(sketch_feature.ModelObjects(8))
source_vertex = min(
    vertices,
    key=lambda vertex: distance(vertex.GetPoint()[1:4], expected_world_point),
)

projection = model_container.Points3D.Add()
projection.ParameterType = 7
param = win32com.client.CastTo(projection.Parameters, "IPoint3DParamProjection")
param.SetAssociationVertex(source_vertex)
param.SetSurfaceObject(tangent_plane)
param.SetGuidingObject(axis_edge)
assert projection.Update()
```

For a revolve sketch with one axis line, a verified way to recover the actual
3D-capable axis edge is:

```python
profile_edges = {edge.Reference for edge in sketch.Edges(1)}
axis_candidates = [
    edge for edge in sketch.Edges(2)
    if edge.Reference not in profile_edges
]
assert len(axis_candidates) == 1
axis_edge = axis_candidates[0]
assert all(abs(value) < 1e-7 for point in (0, 1) for value in axis_edge.GetPoint(point)[2:4])
```

Pass this `IEdge`, not the original 2D drawing line wrapper, to
`IPoint3DParamProjection.SetGuidingObject(...)`.

Known examples:
- `diaphragm_spring` cut anchors: two explicit points in a `YOZ` reference
  sketch drive two `ParameterType=7` projection points directly. No source
  `Point3D` features are created. Radius variables rebuild the sketch vertices
  and both projection points through the same references.

---

### EDGE-002: CompositeCurve3D Accepts A Mixed Array Of Edges

Applies when:
- building a composite trajectory from sketch geometry and 3D geometry;
- an operation needs one path made from multiple sources;
- passing a whole sketch as a path segment fails.

Symptom:
- Composite trajectory cannot be built from a sketch object directly.
- Evolution/path operation needs individual edges.

Cause:
- `CompositeCurve3D` expects an array of edge COM objects. Sketch edges and 3D
  edges have different COM interfaces, but can still be placed in one `Edges`
  array.

Rule:
- Extract individual sketch edges with `GetObject(...)` and combine them with
  3D edges in the composite curve.

Implementation:
```python
path_edges = []

# 3D edge
law_curve = model_container.CurvesEx.Add("LawCurve3D")
path_edges.append(law_curve.Edge)

# Sketch edge
drawing_container = sketch.GetObject("ksLineSeg:2")
sketch_edge = drawing_container.Segments[0]
path_edges.append(sketch_edge)

composite = model_container.CurvesEx.Add("CompositeCurve3D")
composite.Edges = path_edges
composite.Update()
```

Known examples:
- `kompas_bridge.py` around the bent-coil path construction used extracted
  `ksLineSeg:N` edges together with 3D edges.
- `CASE-001`

---

### OP-001: Assign Sketches To 3D Operations Through SetSketch/SetProfile Fallbacks

Applies when:
- assigning a sketch/profile to extrude, revolve, or evolution;
- direct `.Sketch = ...` does not work;
- different KOMPAS versions expose different assignment methods.

Symptom:
- Direct sketch assignment raises an error.
- Operation is created but has no profile/sketch.

Cause:
- KOMPAS COM versions differ. Some expose `SetSketch`, some `SetProfile`, and
  some accept direct property assignment.

Rule:
- Try method assignment first, then property assignment fallback.
- Raise a clear error if none of the compatible APIs are present.

Implementation:
```python
assigned = False

for method_name in ("SetSketch", "SetProfile"):
    setter = safe_get(operation, method_name)
    if callable(setter):
        setter(sketch)
        assigned = True
        break

if not assigned:
    for attr in ("Sketch", "Profile"):
        try:
            setattr(operation, attr, sketch)
            assigned = True
            break
        except Exception:
            pass

if not assigned:
    raise RuntimeError("Cannot assign sketch/profile: no compatible KOMPAS API")
```

Known examples:
- `kompas_bridge.py` evolution/extrusion assignment paths.

---

### OP-002: Bound Every Operational Contour Explicitly

Applies when:
- generating sketches for extrude, revolve, cut, or evolution operations;
- the sketch contains helper geometry, multiple contours, or multiple axis-like
  lines;
- a human could select the intended region manually, but automation must assign
  the sketch/profile programmatically.

Symptom:
- KOMPAS accepts the sketch and constraints, but the 3D operation returns false
  or selects the wrong contour/region.
- A revolve sketch looks correct, but the operation fails because helper lines
  are typed as axes or intersect/confuse the intended profile region.
- The model works manually only after selecting a specific region, face, or
  contour in the UI.

Cause:
- KOMPAS can handle complex human-authored sketches with several contours and
  axes because a user can choose the exact region interactively. Programmatic
  sketch assignment is much more fragile: the operation may interpret all
  axis-type lines, construction lines, and all contours in the sketch, not the
  intended subset.

Rule:
- Prefer one sketch per operation.
- Prefer one operational contour per operation sketch. Multiple disjoint closed
  contours are allowed only when that exact operation has live evidence for
  consuming them together and the builder declares and preflights the expected
  component count.
- For revolve operations, keep exactly one axis-type line in the sketch: the
  actual axis of revolution.
- Helper, anchor, gauge, and construction lines must use construction/helper
  line styles, not axis styles.
- If `operation.Profile = sketch` is used and helper geometry intersects or lies
  inside the candidate region, prefer removing the helper geometry for the
  operation sketch or assigning an explicit contour/profile object.
- Parameterize fragile revolve sketches progressively: variables and driving
  dimensions can be safe while geometric constraints still break automatic
  region recognition. Enable geometric constraints only after a live probe, or
  after the operation receives an explicit profile/contour object.
- Treat "dimension applied" as insufficient for operation sketches. A driving
  dimension can be syntactically created and still move unconstrained endpoints
  into a broken contour. Run a primary-profile preflight after parameterization
  and before `Rotated.Update`.
- If a part needs multiple unrelated operations or ambiguous regions, split
  them into separate sketches/operations instead of relying on UI-style contour
  selection.

Implementation:
```python
# Good: one axis line and helper lines with construction style.
axis_line_style = LINE_STYLES["axis"]          # true revolve axis only
helper_line_style = LINE_STYLES["construction"]

draw_axis(axis_start, axis_end, style=axis_line_style)
draw_profile(profile_points, style=LINE_STYLES["solid"])
draw_helper(anchor_start, anchor_end, style=helper_line_style)

operation.Profile = sketch
```

Verification:
- Inspect generated sketches in KOMPAS: a revolve sketch should show only one
  axis-type line.
- Run the live operation directly against the constrained sketch. Avoid a clean
  profile-copy fallback unless the API truly cannot consume the operational
  sketch.
- Read back the result and confirm operation success, nonzero body mass, and the
  expected contour behavior.

Known examples:
- `V-belt groove`: one rotational cut safely consumes one closed component per
  groove after exact component-count, gap, branch, and self-intersection
  preflight; this is the bounded multi-contour exception to the default rule.
- `V-belt groove`: standard/native upper-edge rounding is a separate post-cut
  `IFillet` feature, not sketch arcs. Resolve exactly two circular top edges per
  groove from semantic probe points, verify uniqueness, rebuild, and require one
  body plus a measurable additional volume decrease. Keep the sharp-cut volume
  check separate from fillet volume.
- `V-belt groove`: select a named standard system before resolving dimensions.
  Keep DIN/ISO manufacturer data and GOST 20889-88 geometry/angle/radius tables
  in separate catalogs; an explicit radius override may cross systems, but a
  default resolver must never create a hybrid profile silently.
- `V-belt groove`: a clean revolved cylinder does not expose a stable straight
  silhouette source for `ISketch.AddProjectionOf(...)`. The accepted composed
  workflow therefore uses origin mode linked to the blank's operation variables
  (`VB_OR=R1`, `VB_FACE_W=L1`), a fixed global axis, and pre-merge datum anchors
  with no copied/fixed profile-point chain. Audit settled style-1 profile entities
  only; `Sketch.Edges(1)` may also return style-2/3 helper geometry.
- `V-belt groove`: keep only driving dimensions with semantic expressions. The
  accepted two-groove sketch has 8 dimensions/8 links; diameter and angle
  annotations without geometric influence, plus their datum-only construction,
  are omitted from the operational sketch.
- `Poly-V groove`: build the periodic functional boundary from nominal tip
  transition arcs, tangent flanks, and deterministic root arcs in one sketch.
  A top closure at the blank radius intersects every intermediate tip and makes
  a non-simple region. Close the operation profile above the blank with two
  bounded radial overshoots; the target body clips that non-functional material.
- `Poly-V groove`: keep nominal `rt` and selected `rb` as independent driving
  sketch-arc radii, not a post-cut full-round/edge-fillet feature. Drive one
  master groove by pitch, both radii, and one flank angle; derive its opposite
  flank by equal length, and derive repeated grooves through equal pitch/radius,
  parallel-flank, and tangent contracts. Fix only the global-axis endpoints.
  For the generic stepped-shaft blank, link `PV_OR=D1/2` and `PV_FACE_W=L1`.
- `Poly-V groove`: after direct COM mutation of operation variables, settle the
  solver with sketch update, one edit cycle, another update, and document
  rebuild before reading `ConstraintsState`; save/reopen mutation of `PV_E`,
  `PV_RT`, and `PV_ALPHA` retained a fully defined closed PH profile.
- `Poly-V groove`: require exactly one closed component, zero gaps, branches,
   and self-intersections, raw `ConstraintsState=2` (historical, not full-definition proof; `SKETCH-011`), one unchanged body, and an
  actual/analytical removed-volume check. The PH/PJ/PK/PL/PM live matrix retained
  these properties after save/reopen.
- `disc_spring`: the constrained profile was fully defined, but the revolve
  operation only accepted it directly after helper anchor lines were changed
  from axis style to construction style.
- `diaphragm_spring`: the geometry-only profile rotated after arc directions
  were corrected, but the constrained sketch failed again when helper lines were
  added to the same sketch and `operation.Profile = sketch` relied on automatic
  region selection.
- `diaphragm_spring`: variables plus 5 driving dimensions (thickness, lip
  length, inner/outer bend radii) rotated cleanly; adding the current geometric
  constraint set made the same operation fail, so constraints remain staged for
  a later explicit-profile pass.
- `diaphragm_spring`: adding axis-distance/angle dimensions for outer/inner/body
  radii and cone/lip angles applied successfully, but later readback showed the
  profile had 4 gaps and 2 sampled self-intersections. The opt-in
  `profile_preflight` guard now catches that before rotation.
- `diaphragm_spring`: full parameterization required the actual current contour
  order (`tip_inner -> outer_bend -> main_inner -> outer_normal -> main_outer ->
  inner_bend -> tip_outer -> tip_end`) and KOMPAS arc constraint point indices
  `1=start`, `2=end`. Bend arcs are solver-stable when constrained through their
  common center helper and endpoints/tangencies; API-created radial dimensions on
  those arcs were not reliable as persisted solver dimensions.

Related:
- `OP-001`
- `SKETCH-004`
- `SKETCH-005`

---

### OP-003: Keep English Operation Descriptors In Canonical Model-Tree Names

Applies when:
- a Layer 2 plan creates named sketches and 3D features;
- a request accepts a user label for an operation;
- downstream verification must find exact model-tree entities after reopen.

Symptom:
- model trees contain build-run markers such as `FINAL`, timestamps, or an
  arbitrary request label instead of the operation type;
- the bridge reconstructs sketch or child-feature names differently from the
  host plan;
- two successful operations are difficult to distinguish in readback.

Rule:
- Use English canonical names that combine a short semantic object description
  with its native KOMPAS operation descriptor.
- Name sketches by the geometry they define, not by the script or build run that
  created them.
- Treat a user-supplied label as an optional suffix; it must not replace the
  canonical operation descriptor.
- Compute exact sketch/feature/dependent-feature names in Layer 2 and carry them
  through the execution plan. The bridge applies those names verbatim.
- Assign a sketch's canonical name before its initial Update and parameterization
  when constructing a new owned branch. Verify its persistence and solver state
  from disk; a matching in-memory Name alone is not proof of saved identity.
- Do not include `FINAL`, dates, timestamps, UUIDs, or output filenames in model
  tree names. Keep run identity in the artifact manifest.

Verification:
- Assert exact planned names in deterministic host-side tests.
- After save/reopen, inspect the model tree and operation readback by exact name.
- For operation variables, preserve dependency-reading order: external links,
  independent inputs, derived formulas, then dependent copies.

Known example:
- `V-belt groove`: `V-belt grooves A x2 profile`,
  `V-belt grooves A x2 cut rotation`, and
  `V-belt grooves A x2 top edge fillets R1`.
- `Poly-V groove`: `Poly-V grooves PJ x6 profile` and
  `Poly-V grooves PJ x6 cut rotation`.
- `external_flat_step`: late `ISketch.Name` assignment appeared correct before save,
  but reopen restored the initial request-derived name and EFLT owned-root recognition
  failed. A late explicit Update persisted the name but returned under-constrained
  native state 2, including after reopen. Honoring `params.sketch_name` before the
  first Update/BeginEdit fixed the common path; fresh one-flat forward and two-flat
  backward stdio-MCP create/inspect plus actual reopen retained both roots, checksum
  recipe, geometry and full native state 1. This family evidence does not authorize
  renaming an arbitrary existing user sketch or interpreting state 2 as success.
- `external_polygonal_step`: assign the planned canonical name and fixed sketch
  placement before the initial Update/parameterization as well. The previous
  common adapter renamed and fixed the sketch afterwards and unconditionally
  reopened its editor to settle the solver. Remove that late mutation/edit cycle;
  it is not a reliable state-refresh repair (`SKETCH-011`). Fresh common-module
  hexagon D30/L10, backward pentagon D32/L22/17 degrees and circumcircle triangle
  D24/L17/23 degrees pass strict native state1 and geometry checks without manual
  activation. Actual close/reopen also preserves state1 on the hexagon/pentagon.
  This representative construction evidence does not certify arbitrary editor
  cycles or manual driver changes and does not weaken the native state gate.

Related:
- `OP-001`
- `VAR-001`

---

### OP-004: Bound Numeric Sketch Entity Count Before Patterning

Applies when:
- a create-only numeric profile is repeated by a circular or linear pattern;
- the contour is sampled from analytic curves rather than built from true arcs;
- a bridge create call approaches the timeout without reporting an error.

Symptom:
- a few hundred sketch entities do not finish inside the 300 s bridge timeout;
- the partial document contains the sketch with all entities but no cut or
  pattern;
- the same geometry with tens of entities completes in seconds.

Cause:
- `_create_sketch_entities` adds one COM entity at a time, so creation cost
  scales with the entity count; the circular pattern then copies that cost
  implicitly. A dense preview-quality sampling is not a CAD-quality plan.

Rule:
- Keep separate sampling densities: high resolution for host-side preview and
  analysis, a documented tolerance for the CAD contour.
- Prefer one smooth KOMPAS spline per analytic curve (`CURVE-002`) over a dense
  segment chain; fit the spline through Ramer-Douglas-Peucker-decimated samples
  and record the measured deviation.
- If the contour must remain polyline entities, simplify it first and compact
  exact circular runs into single arcs.
- Verify the expected volume from the analytic contour clipped to the blank,
  not from a coarsely decimated preview polygon.

Verification:
- Record entity count, maximum curve deviation, create time, and the live body
  volume error.
- The spur-gear default contour first used 264 segment entities and timed out;
  the final version uses seven entities (two smooth curves per flank plus exact
  cap and closure arcs), creates in about six seconds, and the live volume
  error is below 0.01 %.

Known example:
- `gear_spur` G2 slice: one tooth-space contour repeated 20 times; the dense
  segment attempt timed out, the bounded smooth-spline contour passed create
  and reopen.

Related:
- `OP-002`
- `CURVE-002`
- `SESSION-002`
- `BRIDGE-001`

---

### EVO-001: Anchor A Guide Spiral On The Axis, Not On The Reference Cylinder

Applies when:
- sweeping a section along an `ICylindricSpiral3D` with `IEvolution` (types 46/47);
- building helical gears, worm grooves, or any cut/boss whose section is large
  relative to the helix radius;
- choosing the spiral position association point.

Symptom:
- The sweep builds and is `Valid`, but the removed/added volume is wrong; in the
  helical-gear probe it was 25 % of the analytic tooth-space volume at β=20°
  and scaled roughly as `1/lead`.
- A straight path (huge lead) produced the exact volume, so the section contour
  and the Evolution binding were fine.

Cause:
- When the spiral position point is associated with a point on the reference
  cylinder (radius ≈ profile radius), KOMPAS builds a deformed spiral/sweep.
  The `Diameter` property already defines the winding radius; the position point
  should be the axis anchor, mirroring the working helical-thread pattern
  (`start_center_point` on the axis plus `DiameterBaseObject`).
- `BySurfaceNormal` and `SketchShiftType` do not repair the deformation.

Rule:
- Anchor `spiral.Position` on the gear/part axis (`SetAssociationObject(center)`)
  and set `spiral.Diameter` to the reference cylinder; keep `Step = lead`,
  `Height = swept length`, and `TurnDirection` from the hand.
- Verify the sweep by volume against the analytic section (`≤ 0.01 %` live
  tolerance) before exposing the operation in a module.

Verification:
- Helical-gear live cases: `m2 z20 b20 β20 right` → volume error 0.005 %;
  `m2 z21 b16 β30 left` → 0.0046 %; both save/reopen as `verified`.
- Probe matrix (straight vs helical, section radius 0/10/21.3 mm, XOZ/XOY/YOZ,
  `SketchShiftType` 0/1/2, `BySurfaceNormal` on/off) is in the ignored
  `experiments/spikes/20261005-gear-spur/` quarantine.

Related:
- `SPIRAL-001`
- `OP-004`
- `CURVE-002`

---

### OP-005: Chamfer Symmetric Ends Before The Expensive Pattern

Applies when:
- cutting symmetric end chamfers (gear tooth tips, thread ends, rim edges);
- the same body also carries an expensive pattern or sweep feature;
- the chamfer is defined by a small closed profile revolved 360°.

Symptom:
- Chamfering the finished patterned body forces KOMPAS to rebuild the whole
  pattern tree and can multiply the create time severalfold (helical gear with
  chamfers: ~99 s versus ~23 s without).

Cause:
- Feature order in the tree. A rotation cut after the pattern must re-evaluate
  the patterned body; the same cut on the plain blank is trivial.

Rule:
- Subtract a symmetric end chamfer from the blank **before** the tooth-space
  cut or pattern. Subtracting a set is order-independent, so the final Boolean
  body is identical.
- Verify the volume from the material actually removed, not the full ring:
  sample the per-pitch analytic outline at the cut radii, because only the
  teeth (not the gaps) lie in the chamfer band. The full-ring formula
  overestimates the removal about fourfold for `m2 z20` at `c = 0.5 mm`.

Verification:
- `m2 z20 x0 b20 + chamfer 0.5 x 45`: volume error 0.008 %, each blank cut
  removes 17.15 mm³, save/reopen `verified`.
- `m2 z20 x0 b20 β20 right + chamfer 0.5 x 45`: volume error 0.007 %,
  save/reopen `verified`.

Related:
- `EVO-001`
- `OP-004`

---

### OP-006: Use The Existing Revolved Cut For A Central Bore, Not A Lone Circle Sketch

Evidence: live-verified on the internal gear `gear_internal` `m2 z40 D100 × 20`
(spur and `β20` left). The `rotational_cut` scenario already existed and is
already used for relief and chamfer rings; the internal-gear slice reuses it
for the central bore. The earlier plan that routed a lone circle through
`numeric_profile_sketch` failed before any cut.

Symptom:
- A `numeric_profile_sketch` containing one circle (`kind: "circle"`) is rejected
  by the sketch preflight: `primary contour is not closed`, `0 component(s);
  expected 1`, although the circle itself is a valid closed entity.
- The later `cut_extrusion` executor has a single-primary-circle fallback, but
  the sketch operation's own closure audit runs first and aborts the workflow.

Cause:
- The numeric-profile closure audit reads style-1 curves; a `circle` entity is
  not returned through the curve collection and therefore counts as zero
  curves.

Rule:
- Reuse the existing `rotational_cut` scenario for a through bore. Its profile
  is a rectangle spanning the full blank width on one side of the gear axis,
  for example
  `[[-b-1, 0], [1, 0], [1, r_bore], [-b-1, r_bore]]` on plane `XOY`, revolved
  360° about the part axis. The segment on the axis is a normal revolved-bore
  profile.
- Keep the bore cut before the tooth-space cut and the pattern, so the
  expensive pattern stays the last feature.

Verification:
- Internal gear spur `m2 z40 D100 × 20`, rounded roots, ring chamfer
  0.5 × 45°: one solid, relative volume error 0.003 %, bounds
  `[-20, -50, -50, 0, 50, 50]`, 40 pattern instances, save/reopen `verified`.
- Internal gear helical `m2 z40 β20 left`: relative volume error 0.004 %,
  save/reopen `verified`.
- The same spur gear with ring and tooth-tip chamfers: relative volume error
  0.0005 %, save/reopen `verified`.

Related:
- `OP-002`
- `OP-005`
- `PATTERN-001`

---

### OP-007: Inner-Edge Chamfers Open At The End Face

Applies when:
- cutting a symmetric chamfer on a bore or internal tooth-tip edge with a
  revolved triangular profile;
- adapting an outside-edge chamfer profile to internal geometry.

Symptom:
- the chamfer narrows the opening at the end face or slopes like an external
  gear-tip chamfer;
- the side preview and the CAD cut agree with each other but both point inward.

Cause:
- reusing the outside-edge triangle without reversing its radial placement.
  For an internal edge the material is at `r > r_bore`: the face opening must
  be larger than the nominal inner radius.

Rule:
- at face `x=x0`, use the cut triangle `(x0,r)`, `(x0,r+d)`,
  `(x0+c,r)`, where `c` is axial chamfer width and `d=c tan(alpha)`;
- mirror the axial coordinate for the opposite face, but do not invert the
  radial rule;
- draw the side-view bevel from `r+d` at the face to `r` inside the width.

Verification:
- inspect the planned profile points before COM;
- verify from the radial point ordering that the face opening is larger than
  the nominal internal tip/bore diameter;
- live-build and verify two valid revolved cuts and one positive solid.

Known example:
- internal gear `m2 z40 D100 x 20`, tooth-tip chamfers `0.5 x 45 deg`: KOMPAS
  accepted both revolved cuts and the cubic-NURBS tooth-space pattern; readback
  mass was `436.1621575 g` for steel density `7.856 g/cm3`.

Related:
- `OP-005`
- `OP-006`
- `VERIFY-001`

---

### SPIRAL-001: InitialAngle Is Not Positioning Orientation

Applies when:
- controlling spiral phase;
- joining bent coil / hook spirals to body geometry;
- working with `ICylindricSpiral3D` positioning.

Symptom:
- Spiral starts at the wrong phase.
- Changing variables does not move the spiral as expected.
- Agent changes local CS rotation instead of spiral initial angle.

Cause:
- `ICylindricSpiral3D` has two independent angular mechanisms:

| Mechanism | Initial angle | Positioning orientation |
|---|---|---|
| Meaning | phase of the first turn | rotation of local CS relative to guide |
| API surface | `spiral.TurningAngle` in verified v23 `ICylindricSpiral3D` | `ILocalCSAxesDirectionParam`, Euler readback, object orientation modes |
| Formula support | yes, when field supports it | not a formula field; COM derives absolute orientation from placement mode |
| Use in bent coil | phase of the helical curve | placement of the spiral's local coordinate system |

Rule:
- Control spiral phase through the native phase field, not through positioning CS
  rotation. The v23 interface exposes `TurningAngle`; the thread trace found no
  `InitialAngle` property. Do not infer an API property from the conceptual name
  or assume that an unverified legacy fallback setter is authoritative.
- Do not treat visible nutation/precession/rotation fields as disposable
  garbage. KOMPAS shows absolute orientation values for the positioned local CS;
  they can appear regardless of the placement mode.
- The physical phase at the connection point is the sum of positioning
  orientation and the spiral's own initial angle. Debug bent-coil connection
  failures by checking both components together.
- `OrientationType=2` / `ILocalCSOrientByObjectParam.SetOrientationObject(...)`
  is not accepted as a bent-coil fix: it can produce a full contour count while
  placing the spiral incorrectly.

Verification:
- Check the positioning mode, the visible absolute orientation, and the spiral
  initial angle together.
- Verify geometry visually/live; a full contour count alone is not sufficient for
  bent-coil spirals.

Known examples:
- `CASE-001`: `_apply_spiral_turning_angle` changed positioning orientation,
  not spiral phase. Stable left hook used numeric initial angle `90`.
- Compression integration (2026-10): native point-on-curve probes found first
  left-hand segment angle0, subsequent segment angle90 and a quarter-turn gap.
  Aligning the first and subsequent left-hand angle formulas fixes the missing
  second fillet edges. A left two-zone spring with phase30 survives save/reopen.
  This phase defect is separate from zero-clearance solid contact (`GAP-001`).
- `bent_coil_left_spike`: orient-by-object was re-tested and rejected because it
  gives an incorrect physical placement despite the correct orientation object.
- `bent_coil_left_spike` right hook: with axis-direction positioning, KOMPAS can
  show a `90` degree absolute rotation for the position. The right spiral uses
  internal initial angle `270` so the effective phase is `360`, not `180`.

Related:
- `DIR-001`
- `VAR-001`

---

### CURVE-002: Preserve Spline Shape With Family-Specific Knots

Applies when:
- an analytic curve must become one smooth KOMPAS spline entity;
- a numeric profile is fitted through sampled points;
- the sketch closure audit or the cut ignores a spline that was just created.

Symptom:
- `SetNurbsParams` returns true and the spline appears in the tree, but
  `GetNurbsParams` returns `degree = null` or no points;
- the closure audit counts a gap where the spline should be (planned five
  entities, settled three);
- a general interpolating B-spline knot vector comes back renormalized to
  integer knots with `closed = true`, and the cut extrusion update fails.

Cause:
- The sketch readback requires casting the entity to `INurbs` before
  `GetNurbsParams`; the raw dispatch object exposes neither `Degree` nor the
  method, so the geometry reads empty and the entity is skipped.
- Passing mathematical degree where API7 expects order can silently alter the
  knot vector (`CURVE-001`). This is not proof that simple knots are unsupported.
- Triple interior knots in the accepted piecewise-Bezier representation expose
  separate spans to a loft. A nominally tangent chain can fragment the final
  surface and make circular patterns substantially more expensive.

Rule:
- Retain the family's verified representation. Existing cam and cylindrical-gear
  paths use cubic Bezier chains with clamped ends and triple interior knots.
- Bevel loft sections use the existing interpolating cubic B-spline with simple
  interior knots (C2 within each curve), weights 1 and native order 4. This avoids
  unnecessary loft seams. Keep real root/involute discontinuities separate.
- Do not change a family's knots based only on `Update()` success: compare native
  order, poles, weights, knots, body bounds/volume and save/reopen readback.
- Cast to `INurbs` in `_inspect_sketch_full_entity` and read `values[1]` points,
  `values[2]` weights, `values[3]` knots, degree from `Degree`.
- Split a profile at a real tangent discontinuity (for example the gear form
  point) into separate smooth curves instead of rounding the corner.

Verification:
- The closure preflight must report the full curve count and zero gaps.
- The cut extrusion update succeeds and the live body volume matches the
  analytic expected volume.
- Evaluate the fitted chain host-side and record its maximum deviation from the
  analytic samples.

Known example:
- Cam: `cams/cad.py` piecewise-Bezier knots; gear `gear_spur`: root and
  involute curves per flank, seven tooth-space entities, live cut accepted with
  0.007 % volume error.
- Bevel `m3 z20 delta45`: simple-knot C2 splines retained all native parameters,
  reduced faces from 743 to 183 and creation from 91.58 to 30.03 seconds locally;
  the single-solid volume error was 0.0121%, with identical bounds and recipe
  restoration after save/reopen.

Related:
- `CURVE-001`
- `OP-002`
- `BRIDGE-001`

---

### PROFILE-001: Place Wire Profile At Final Path Sequence End

Applies when:
- building extension spring sweep/evolution profiles;
- building compression spring sweep/evolution profiles;
- building torsion spring sweep/evolution profiles;
- building conical spring sweep/evolution profiles;
- adding independent left/right hook composition;
- choosing `profile_anchor_plane` for a multi-segment `full_path_sequence`.

Symptom:
- Some hook types place the wire profile at the left/start side, while others
  place it at the right/end side.
- A mixed left/right hook generator changes profile placement depending on which
  hook type owns the anchor.

Cause:
- Old hook previews chose the profile anchor from hook-specific paths. This was
  harmless when both sides used the same hook type, but it is not a stable
  contract for independent side composition.

Rule:
- Treat `full_path_sequence` as the canonical left-to-right final contour order.
- Always set the wire profile anchor to `full_path_sequence[-1]` with
  `vertex = "end"`.
- Do not choose the profile anchor from a hook-type-specific left segment.
- Once the profile is anchored to a point on the final contour, keep the profile
  sketch local: `profile_path_offset = [0, 0, 0]`,
  `profile_sketch_center = [0, 0]`, and constrain/dimension the profile circle
  itself. Do not keep an old in-sketch offset by coil radius.

Verification:
- Preview: `profile_anchor_plane.path_name == full_path_sequence[-1]` and
  `profile_anchor_plane.vertex == "end"` for every extension hook type.
- Live CAD: `select_profile_anchor_plane.profile_anchor_path_ref` should match
  the last resolved sequence path.
- Live CAD: `create_wire_profile.profile_center` should be `[0.0, 0.0]` for
  anchor-plane-based spring profiles.

Known examples:
- `machine_hooks`, `v_hooks`, `u_hooks`, `center_loop_hooks`,
  `extended_center_loop_hooks`, and `open_loop_hooks` now use the right/end side
  of their final sequence.
- `self_wrapping_hooks` and `bent_coil_left_spike` use the same helper instead of
  hand-written anchor paths.
- `torsion_spring` uses local profile sketches for tangent, radial, and
  axial-transition legs; radial and axial transition fillets no longer require a
  sketch-level coil-radius offset.
- `conical_spring` uses local profile sketches on the final contour endpoint;
  start/end conical segments, native curve-fillet transitions, and ground surface
  cuts must not reintroduce a profile sketch offset. Use the original final
  `finish_end` spiral edge for the profile anchor plane when the physical
  endpoint is unchanged; native fillet result edges can be valid contour members
  but fail as `IPlane3DPerpendicularByEdge` inputs.
- `compression_spring` uses the same final endpoint anchor and local profile
  sketch. Cylindrical segment transitions use native result edges for both
  right-hand and left-hand turns; the legacy trimmed-connect path is now an
  explicit fallback, not the auto mode.
- Conical transition fillet defaults should be based on the limiting local cone
  radius at segment joints, not wire diameter. Keep the default just below that
  radius and allow explicit override for model-specific tuning.

---

### VAR-001: Bind Formulas Through Operation Variables After Object Creation

Applies when:
- a COM field accepts only a number during object creation;
- the UI accepts a formula but direct COM string assignment fails;
- a generated point/plane/spiral must remain parametrized.

Symptom:
- Assigning a string expression like `"(D1 - WD1) / 2"` raises a type error.
- Formula assignment silently resets.
- The object keeps a numeric fallback and does not update when variables change.

Cause:
- Some COM fields accept only numeric values before the first `Update()`. The
  formula must be attached later through an operation variable/property
  parameter that points at the created object field.

Rule:
- Use the pattern: numeric fallback -> `Update()` -> operation-variable binding
  -> `Update()`.

Implementation:
```python
# 1. Create object with numeric fallback.
point3d = container.Points.Add()
point3d_param = point3d.Parameter

disp_param = CastTo(point3d_param, "IPoint3DParamDisplace")
disp_param.Distance = 15.0
point3d.Update()

# 2. Bind formula after creation.
op_var = part.PropertyParameter("Distance", point3d)
op_var.Expression = "(D1 - WD1) / 2"
point3d.Update()
```

Known fields:
- `IPoint3DParamDisplace.Distance`: bent spiral center offset.
- `IPlane3DByAngle.Angle`: bend angle plane.
- `IFilletCurve.Radius`: native 3D curve fillet radius. Use the staged
  `FILLET-002` order below; assigning `Radius` before the first `Update()` can
  leave the saved operation radius at `0.0`.

Verification:
- Change `D1`, `WD1`, or the driving variable and rebuild.
- Confirm the dependent object moves, not just the first numeric fallback.

Known examples:
- `CASE-001`: center of bent spiral stayed at `15.0` until the offset was bound
  through operation variable expression `(D1 - WD1) / 2`.
- local v60 live evidence confirmed that native curve fillets keep operation
  variable `Радиус = SFR1` after save and reopen; the one-off probe is retained
  only in the ignored experiment quarantine.

### FILLET-001: Use Native Curve-Fillet Result Edges In Final Contours

Native `FilletCurve` operations are feature containers in KOMPAS. Do not put the
whole `IFilletCurve` object into a final sweep/evolution contour. It may appear
valid through API creation and then fail after UI rebuild.

For contour membership, use the feature result edges:

1. Create and update the native `IFilletCurve`.
2. Bind operation variable `Радиус` if required.
3. Get the owner feature: `fillet.Owner`.
4. Read `fillet.Owner.ModelObjects(7)`. It returns the three selectable result
   `IEdge` objects shown under the fillet container in the KOMPAS tree:
   trimmed source curve 1, fillet curve, trimmed source curve 2.
5. Use those result edges, not the `IFilletCurve`, in the final `Contour3D`.

Known example:
- `self_wrapping_hooks` left hook: using whole `FilletCurve` gave a false-positive
  API build, but `RebuildDocument()` invalidated the contour/body. Replacing it
  with `Owner.ModelObjects(7)` result edges fixed rebuild stability.

### FILLET-002: Assign Native Curve-Fillet Radius After First Update

For native 3D `IFilletCurve` operations, do not set `Radius` before the first
`Update()`. On legacy extension-hook connector curves this produced visually
valid-looking operations whose saved radius read back as `0.0`.

Use this order:

1. Create the `IFilletCurve` and assign `Curve1`, `Curve2`, trim flags, and cut
   points.
2. Call `Update()` once to materialize the operation topology.
3. If the fillet is between spiral-derived spring curves, assign a small seed
   radius based on local pitch spacing, not wire or spring diameter. Use a value
   such as `0.02 * min(adjacent local pitch)`, capped by the target radius.
4. Call `Update()` again and verify the seed radius readback.
5. Assign the target numeric `FilletCurve.Radius`.
6. Call `Update()` again and verify target radius readback.
7. Bind operation variable `ParameterNote == "Радиус"` to the driving expression
   such as `TFR1` or `SFR1`.
8. Call `Update()` again and verify the expression reads back exactly as the
   driving variable, not as `TFR1 - <offset>`.
9. Read `fillet.Owner.ModelObjects(7)` and use the result edges in the final
   contour, per `FILLET-001`.

Verification example for legacy extension hooks:

```text
radius=3.0
radius_readback=3.0
staged_updates=[True, True]
expression_after=TFR1
source_path_count == expected_edges_count == edges_count
```

### FILLET-003: Use Logical Cut Points For Raw Spiral Fillet Sources

Native `FilletCurve` can accept a raw spiral/path object as `Curve1` even when
the same COM object does not expose usable endpoint readback through `GetPoint`.
Do not add an extra connector or auxiliary fillet only to get a selectable source
edge. That changes the model topology.

When the intended geometry is an unfilleted joint followed by a right-side native
fillet, keep the raw source curve and provide the cut point from generator
metadata:

1. Resolve `Curve1` to the raw body path.
2. Read the logical body end from `segment_plan`.
3. Use that point as `Curve1CutPoint`.
4. Compute `Curve2CutPoint` from the target curve endpoints near the same logical
   point.
5. Continue with the staged `FILLET-002` update/radius/binding order.

Known example:
- `bent_coil_left_spike -> self_wrapping_hooks`: the bent-coil-to-body joint must
  remain unfilleted. The right self-wrapping transition fillet uses raw
  `BODY_PATH` plus the logical body end point, producing a stable `10/10/10`
  contour without a synthetic left bent-to-body fillet.
- `compression_spring` native transitions use cut points slightly inside the
  adjacent spiral segments, not the exact shared endpoint. For cylindrical
  springs, create those cut points on the actual COM curve with
  `Point3DParamCurve`; analytic preview coordinates can pick the wrong selectable
  side on left-hand spirals even when the preview phase gap is zero.
- `conical_spring` uses the same COM-curve cut-point pattern. Its target fillet
  radius can be larger than the spacing to the neighboring turn, so the native
  fillet must be staged from a seed radius derived from local pitch spacing before
  applying the target radius.
- Hide generated `Point3DParamCurve` cut-point helpers immediately after creation;
  they are selection aids for `SetCurve*CutPoint`, not user-facing construction
  geometry.
- The default cylindrical target radius is `min(0.4 * mean_radius,
  1.5 * wire_diameter)` (`TFR1 = min(0.2 * (D1 - WD1), 1.5 * WD1)` for the
  standard outside-diameter variable). The initial seed radius is separate from
  that target and follows the local-pitch rule above.

### FILLET-004: Construct Cut Fillets From The Retained-Body Side

A corner fillet inside a closed cut contour rounds the cutter region. That is not
equivalent to rounding the edge that remains on the solid after the cut; at a
groove mouth the two arcs have opposite corner sense.

For a rounded tooth face adjoining an outside circle of radius `R`:

1. Keep ordinary internal contour fillets only where the removed groove itself
   must be rounded, such as the groove root.
2. Construct each mouth transition as a circle of radius `r` whose center lies on
   radius `R - r` from the part axis.
3. Make that circle tangent to the tooth flank and use its radial contact point on
   the radius-`R` circle as the other arc endpoint.
4. Extend the closing cut boundary outward from that contact point; do not reuse
   an internal polygon-corner fillet at the sharp groove-mouth intersection.
5. Verify the center radius `R - r`, the outer endpoint radius `R`, flank
   tangency, contour closure, and the live KOMPAS arc direction after readback.

Known example:
- the numeric T/AT timing-pulley groove uses retained-body mouth transitions plus
  ordinary groove-root fillets. Applying the generic internal fillet at all four
  trapezoid corners produced a valid cut but rounded the cutter body on the wrong
  side of each tooth face.

### CONTOUR-001: Build KOMPAS Contours In Continuous UI Order

KOMPAS contour assembly follows UI-like continuity rules. If an added element does
not share an endpoint with the current contour end, that element and subsequent
elements may be ignored or collapsed even when API assignment succeeds.

For generated path contours:

- inspect candidate `IEdge.GetPoint(True/False)` endpoints;
- order result edges and sketch edges by actual endpoint continuity, not collection
  index alone;
- verify `source_path_count` and `EdgesCount` immediately after contour creation;
- reopen and call `RebuildDocument()` before declaring the contour stable.

For self-wrapping hooks, the final left-side path has 9 elements. The profile
anchor must stay at the physical end of that path. Do not move the profile anchor
to compensate for a broken or incomplete contour.

For variable-pitch compression springs, KOMPAS can build a visually correct
seven-edge `Contour3D` and still reject it as `IEvolution.Edges`. Keep the
contour as readback evidence, but if the first evolution `Update()` fails, retry
with the direct list of path parts in the same UI order. Record the selected
`edge_input_mode` so it is clear whether the body used `path_contour` or the
`direct_path_list` fallback.

### REBUILD-001: Materialize Newly Created CAD Features Before Capturing Result Edges

Some KOMPAS feature result objects are not stable immediately after API creation.
When later operations depend on selectable result edges, perform an explicit
materialization step before reading them.

For `self_wrapping_hooks`:

- create Sketch2;
- call `RebuildDocument()`;
- create native `FilletCurve` operations against the materialized sketch edges;
- call `RebuildDocument()` again before reading `FilletCurve.Owner.ModelObjects(7)`;
- then create the final 9-edge `Contour3D` and `IEvolution` body.

### REBUILD-002: Recreate Timing Groove Branch After Tooth-Count Changes

For managed timing pulleys, changing tooth count changes the blank diameter,
the groove profile radius, and the groove-pattern count. KOMPAS can accept the
updated part and operation variables while leaving the existing `one groove`
sketch at the previous radius. The first edit may appear correct; subsequent
edits can leave the profile at the previous radius and report that the sketch
has no solution.

Use this sequence for both trapezoidal and curvilinear timing profiles:

- treat a tooth-count change as a managed groove-branch topology replacement;
- remove the owned pattern, groove cut, and `one groove` sketch while retaining
  the blank and its axis;
- rebuild the groove sketch, cut, and circular pattern from the new workflow
  plan;
- rebuild the document and verify the pattern variable readback, groove-sketch
  geometry readback, and managed ownership fingerprint.

Failed approach: updating only the blank sketch, or repeatedly calling
`Update()` on the existing groove sketch, does not reliably move the profile on
the second and later edits. Do not use a `BeginEdit()` geometry readback as the
refresh mechanism during the active transaction; on some KOMPAS builds it can
block while the new feature tree is still resolving.

### LOFT-001: Use `ILoft` For Variable-Section Cuts

Applies when: a body must be cut with a contour whose cross-section scales or
changes along a path, and no extrusion/evolution primitive expresses it (for
example a straight bevel-gear tooth space).

Verified on KOMPAS v23 through API7:

- `IModelContainer.Lofts.Add(32)` creates a cut loft (`o3d_cutLoft`);
- `ILoft.OperationResult = 2` (`ksOperationResultEnum::ksOperationCut`) makes
  it subtractive;
- `ILoft.Sketchs` takes a VARIANT array of sketch objects. A
  `win32com.client.VARIANT(VT_ARRAY | VT_DISPATCH, [...])` payload works with
  dynamic dispatch; a plain Python list is the fallback attempt, not the
  primary one;
- `ILoft.Update()` then `part.Update()` and the same body-count / material-
  removal checks used by `cut_extrusion` keep the operation verifiable.

For a bevel tooth space, two sections are enough when both are exact central
projections of the same contour from the wheel apex: the inner section is a
uniform 3D scaling of the outer one, so a ruled loft between corresponding
points reproduces the projected cone surface exactly. Prefer the two
**cone-normal** Tredgold planes (perpendicular to the pitch cone) over axial
planes: the cut then forms the tooth ends on the same back/front cone surfaces
as the blank rim, so the teeth stay square instead of being pointed by an
oblique axial cut. Do not fit the two sections independently; scale the fitted
control points of the outer section. When the blank is a dish, the expected
volume must clip each cone-normal station by the face cone and by the blank's
flat back face as well; the back face cuts the root side of the tooth space and
accounts for several percent of the removed volume.

### LOFT-002: A Cut Loft Sees Pattern Copies In Its Own Collection

`FeaturePatterns` copies of a loft cut appear as additional `ILoft` objects in
`IModelContainer.Lofts` with the source feature's name. Managed-block
recognition must accept `len(lofts) >= 1` and use the first (root) feature for
owned references, as the extrusion-based gear inspection already does with
`Extrusions`. Requiring exactly one loft silently rejects every patterned cut.

### FRAME-001: Measure An API-Created Plane's Sketch Frame With Probe Points

Applies when: a profile must be written in 2D sketch coordinates on a plane
created through the API (offset/angled/custom planes), and the plane's local
axis order or sign is unknown (see also `CS-004`).

Do not assume the frame. Create a small probe sketch on the plane with points at
`(0,0)`, `(1,0)`, `(2,0)`, `(0,1)` (and optionally `(1,1)`), finish and update
it, then read the persistent vertices through `IFeature7.ModelObjects(8)`
(`EDGE-001`). The world coordinates of the probe points give the affine
2D-to-3D frame of that plane: origin, U vector, V vector, and scale. The point
at `(2,0)` disambiguates the U axis from the V axis. Invert that measured frame
to convert host 3D points into the exact 2D sketch coordinates, and validate
that the U/V vectors are orthogonal, have equal lengths, and are parallel to the
requested base plane. Reuse the same measured frame for every sketch created on
that plane.

Verified live: on a `YOZ`-parallel offset plane KOMPAS mapped sketch U to
global -Z and sketch V to global -Y; writing untransformed host coordinates
would have produced a mirrored, axis-swapped section. The same probe works on
a plane created perpendicular to an explicit axis line
(`IPlane3DPerpendicularByEdge`): create the axis from two 3D points, pass the
anchor point and the axis, then measure the frame. Keep the anchor on the axis
segment (extend the segment beyond the outer section); an anchor off the axis
edge made KOMPAS fail the call and corrupt the session, which then surfaced as
`RPC_S_CALL_FAILED` and a document that no longer matched the strict runtime
identifier.

## Case Studies

### CASE-001: Bent Coil / Hook Construction Chain

Recorded:
- 2026-06-18.
- Covers tasks 14-20 and 9 live model iterations.

Problem:
- Build left/right bent coil hooks for `extension_spring` so that spirals leave
  the body at an angle, remain parametrized, and use fully constrained sketches.

Construction chain:
```text
1. Body end plane
   -> tangent sketch in global CS
   -> auxiliary axis used as baseline for angled plane

2. Angled plane (IPlane3DByAngle)
   -> center sketch on the angled plane
   -> project external 3D body point with AddProjectionOf
   -> axis line from projection to bent spiral center
   -> displaced 3D center point with operation-variable binding

3. Bent spiral (ICylindricSpiral3D)
   -> positioning: point via SetAssociationObject
   -> directing plane/object via SetDirectingObject
   -> CS from angled plane
   -> diameter/pitch/turns formulas through operation-variable binding
   -> initial angle: left = 90, right = selected by live verification

4. Wire profile
   -> path: RIGHT_BENT_COIL -> BODY -> LEFT_BENT_COIL
   -> IEvolution(sketch=profile, edges=path)
   -> hide auxiliary geometry
```

Rules used:
- `CS-002`: axis direction verification.
- `CS-003`: coordinate-system cascade.
- `CS-004`: unstable sketch origin on angled plane.
- `SKETCH-001`: fully constrained sketch.
- `DIR-001`: direction verification.
- `EDGE-001`: resolve a sketch point through `IFeature7.ModelObjects(8)` before using it as a 3D reference.
- `EDGE-002`: mixed sketch/3D edge composite curve.
- `OP-001`: sketch assignment fallback.
- `SPIRAL-001`: initial angle is not positioning orientation.
- `VAR-001`: operation-variable binding.

Result:
- Both bent spirals leave the body under angle.
- Sketches are constrained through projections instead of unstable origins.
- Offset and bend parameters are formula-driven.
- Reports: local bent-coil investigation evidence (kept outside the public
  contract).

### CASE-002: Compression Spring Fully-Constrained Sketch Drift

Problem:
- In `compression_spring/v7`, changing outer diameter moved the spiral relative
  to the axis.

Cause:
- Sketch dimensions existed, but geometric degrees of freedom were not fully
  constrained.

Rules:
- `SKETCH-001`
- `GAP-001`

Result:
- Sketches must be constrained and then rebuilt under changed parameters.

### CASE-003: Reference Sketch Constraint Inspection

Problem:
- `inspect_sketch_full` must be used to reproduce a known reference sketch, but
  projection constraints may not include the referenced external object.

Cause:
- The current inspection tool can capture almost all available sketch data,
  including projection constraints. The known remaining gap is identifying what
  object a projection constraint references.

Rules:
- `SKETCH-002`

Result:
- Use inspected geometry, dimensions, and constraints as the primary source.
- When projection constraint references are missing, ask the user to inspect the
  sketch in KOMPAS UI and name the referenced objects.

## Adding New Rules

Add a rule after a live failure or reusable fix. Prefer updating an existing
rule when the new knowledge changes its scope.

Template:
~~~markdown
### AREA-001: Short Rule Name

Applies when:
- ...

Symptom:
- ...

Cause:
- ...

Rule:
- ...

Implementation:
```python
...
```

Verification:
- ...

Known examples:
- `CASE-...`
~~~

ID prefixes:
- `ARC`: arcs and curve direction.
- `PARAM`: parameter and COM field semantics.
- `CS`: coordinate systems, planes, local axes.
- `SKETCH`: sketch constraints and inspection.
- `DIR`: direction flags and readback.
- `VERIFY`: temporary helper geometry and coordinate-based verification.
- `GAP`: modeling tolerances and clearance.
- `EDGE`: 2D/3D geometry bridge and edge extraction.
- `OP`: operation setup and assignment.
- `SPIRAL`: spiral-specific behavior.
- `VAR`: operation-variable binding.
- `CASE`: longer live case studies.

## Principles

1. Rule is not law. Always verify live when KOMPAS behavior is uncertain.
2. A rule belongs here only after live confirmation or repeated failure.
3. Every rule should name at least one known example, report, or file region when
   possible.
4. Preserve failed approaches when they prevent future repeated debugging.
5. This document must grow during the cycle: build -> observe failure -> record
   reusable lesson.
