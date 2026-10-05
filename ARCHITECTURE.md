# Архитектура Geomwright

Этот документ определяет владельцев runtime-логики и границу между рабочим MCP,
CAD-side bridge, параметрическими модулями и исследовательскими прототипами.

## Runtime-топология

```text
MCP client
    │ JSON/MCP
    ▼
src/geomwright/server.py
    │ default application facade
    ▼
src/geomwright/kompas/server.py
    │ tool registration
    ▼
src/kompas_mcp/*_tools.py + KompasAdapter implementation
    │ JSON request/result files
    ▼
BridgeRunner
    │ launches the KOMPAS-bundled Python runtime
    ▼
bridge/kompas_bridge.py
    │ API7/API5 COM
    ▼
KOMPAS-3D document/model
```

MCP host работает на Python, указанном в `pyproject.toml`. Bridge запускается
отдельным интерпретатором из `KOMPAS_PYTHON` с `pywin32` и доступом к KOMPAS COM.
Его синтаксис должен поддерживаться выбранным интерпретатором. Старый встроенный
Python 3.2 не поддерживает текущий bridge; настройка современного runtime описана
в README. `KOMPAS_REQUIRE_VISIBLE=1` задаёт attach-only режим для MCP так же, как
Studio: отсутствие работающего КОМПАС — ошибка подключения, не создание скрытой копии.

Продукт, Python distribution и публичный application namespace называются
Geomwright. `geomwright.server` предоставляет MCP entry point,
`geomwright.kompas.server` владеет KOMPAS MCP bootstrap и единым реестром
инструментов, а `geomwright.studio` владеет presentation layer. Публичные фасады
адаптера и tool catalog находятся в `geomwright.kompas`; остальные
KOMPAS-specific implementation modules временно сохраняются в namespace
`kompas_mcp`. Их массовая замена затронула бы внутренние импорты, packaged bridge
и пользовательские интеграции без добавления runtime-возможностей.
`kompas_mcp.server` делегирует каноническому bootstrap и возвращает те же объекты
`mcp` и `adapter`; старые CLI и import aliases остаются доступными на переходный
период.

Экспериментальный Geomwright Studio — отдельный host-side presentation adapter.
Entry point `geomwright.studio` вызывает существующие Layer 2
preview-функции и адаптирует их результат для HTML5 Canvas. Он не регистрируется
в MCP tool catalog. Preview-only модули не запускают bridge; managed-CAD модули
вызывают ограниченные workflows адаптера с явным подтверждением записи.
Старые entry points `kompas_mcp.studio` и `kompas_mcp.mechanics.ui` сохранены
только как compatibility aliases.

Канонический исходник bridge находится в `bridge/kompas_bridge.py`. Его packaged
копия — `src/kompas_mcp/assets/bridge/kompas_bridge.py`. Эти файлы обязаны быть
byte-identical.

`BridgeRunner` является Layer 1 process boundary. Штатный `normal` режим имеет
ограниченный timeout и удаляет временный transport state; явный `diagnostic`
режим сохраняет request/response/progress/stdout/stderr как внешние артефакты.
Progress callbacks получают единый компактный envelope, а timeout/cancellation
ошибки содержат последний доступный checkpoint. Это реализует `SESSION-002` без
изменения публичных CAD-result schemas. Bridge dispatch дополнительно публикует
bounded start/completed/failed checkpoints вокруг каждой action.

## Четыре слоя

### Layer 1 — атомарные инструменты и readback

Один вызов выполняет одну ограниченную операцию или чтение состояния.

Владельцы:

- `*_tools.py` — MCP schemas и регистрация инструментов;
- `adapter.py` — host-side orchestration и нормализация ответа;
- `bridge_runner.py` — изолированный запуск bridge;
- `bridge/kompas_bridge.py` — COM-вызов и непосредственный CAD readback.

Примеры: открыть документ, получить список features, создать sketch entity,
прочитать ограничения, сохранить модель.

Layer 1 не выбирает семейство детали и не строит длинную последовательность.

### Layer 2 — детерминированная геометрия и проверки

Этот слой переводит пользовательские размеры в однозначную геометрию и
проверяет локальные инварианты до COM-вызова.

Владельцы:

- `sketch_runtime/` — сущности, frame mapping, topology, constraints и
  diagnostics;
- `sketch.py` — параметрические sketch plans и variable/dimension plans;
- `connect_curve.py` и `trimmed_curve.py` — правила составных кривых;
- `parametric.py` и `parametric_extension_legacy.py` — schema normalization,
  preview и геометрические ограничения;
- `rules/default.json` — текущие статические правила для существующих batch и
  quality workflows, но не универсальный Rule Engine.

Layer 2 не владеет документом КОМПАС и не должен сам выполнять COM.

`kompas_mcp/cams/` owns host-only lift laws, fixed-arm rocker kinematics,
contact envelopes, timing conversion, and sampled geometric diagnostics.
Its contact-aware `curvature_spline` is a direct-flat-only Layer 2 synthesis:
positive piecewise-linear curvature integrates the support ODE analytically,
enforcing C2 flank/nose matching and a bounded monotone family search with
optional analytic acceleration/jerk limits. Tappet
edge reach is a separate finite-face check; no dynamics optimizer or COM is involved.
Its separate `motion_spline` family integrates piecewise-linear valve acceleration
into cubic C2 spans, solving lift/velocity endpoint conditions with a shared nose
acceleration. A fixed 48-shape budget is filtered by exact angular derivative
limits, then by the actual follower/contact geometry; promising candidates receive
a denser sampled contact check. This is bounded host-only synthesis, not a global
optimizer or an application of the flat support ODE to rockers. `bounded_auto`
compares standard laws and these eligible synthesis families without relaxing inputs.
`geomwright/studio/camshaft.py` owns the three-step presentation adapter.
The kinematics view is an explicitly labelled illustrative layout, not the
calculated manufacturing contour. The separate Cam view uses the Layer 2
profile. Its create-only Layer 4 CAD family uses the same Layer 2 calculation
for Studio and the public `create_cam` tool. Host-side `cams/cad.py` owns
preflight, arc-length cubic interpolation and verification; the bridge owns only
the native NURBS/base arc, extrusion and actual curve/body readback. It creates
one new part, not a shaft assembly, and exports sketch/feature references for
subsequent standard operations. The numeric profile is not sketch-parameterized;
changed inputs require a new build. Studio recognizes a persisted `GW_CAM_VERSION`
and `CAM_*` fingerprint with the two root operations as a read-only block.
Version-2 metadata retains a bounded, checksum-verified calculation recipe and
optional Studio form; Studio restores it only into a new-part draft. Read-only
`inspect_cam` exposes the recipe to MCP. Legacy version-1 blocks remain readable
without pretending their original recipe or verification stamp can be recovered. Native creation leaves
`CAM_VERIFIED=0`; after host checks, a strictly targeted finalization verifies curve
identity and body bounds again before publishing `CAM_VERIFIED=1`. Errors carry
owned-document partial-result diagnostics; cancellation is not a rollback.
The final curve is checked against held-out contact samples, base tangency,
cubic stationary curvature points, sampled self-intersection and global
flat/roller contact recovery at sampled follower positions. Contact extrema use
the continuous cubic/base curve; pressure angles use all source-grid positions.
Bounds, extrusion direction, positive single-solid volume and rebuild are read
from KOMPAS; save/reopen acceptance covers direct C2 and rocker examples.
Engineering limits are strict with independent numerical comparison floors;
CAD tolerance only bounds profile/contact accuracy, not curvature or finite-face
slack. Contact-angle and topology checks are sampled rather than a global
manufacturing proof. Studio's Cam view
and CAD preflight use the same 10-samples-per-degree synthesis density.
The Layer 2 preview also returns a complete `motion_chart` command curve including
lash ramps, with sampled S/V/A/J, separate net valve lift, stage windows and
derivative-break metadata. Studio renders it without numerical differentiation;
the chart coordinate is valve-side lift for rockers, not roller-centre motion.
Its graphical view never launches bridge and labels stale data after input errors.
Its user contract and verification limits are in [English](docs/en/camshaft.md) and
[Russian](docs/ru/camshaft.md).

### Layer 3 — управляемые workflows

Layer 3 собирает атомарные операции в последовательность с явными references,
preflight, snapshot/readback и fail-fast поведением.

Владельцы:

- `workflow.py`, `workflow_tools.py`, `composition.py`;
- managed parametric workflow в `parametric.py` и bridge executor;
- `spring_tools.py`, `spring_catalog.py`, `size_catalog.py`;
- scenario-specific orchestration в adapter/bridge.

Базовый цикл:

```text
Plan → Execute → Verify → Correct
```

`Correct` означает ограниченную детерминированную коррекцию либо остановку с
диагностикой. Универсального OperationGraph, транзакционного rollback между MCP
вызовами и автоматической компенсации сейчас нет.

### Layer 4 — законченные семейства деталей

Layer 4 задаёт публичный контракт целого CAD-модуля: параметры, дерево операций,
формулы, readback и канонические варианты.

Текущие семейства:

- ступенчатые/конические и thread-related parametric parts;
- compression, conical, torsion и extension springs;
- disc/Belleville springs;
- diaphragm spring: flat, single-bend и S-bend, circle/oval relief, through-all
  cuts и multi-source circular pattern.

Mechanical transmissions have an approved Layer 4 managed-pulley workflow in
progress. Its architecture is defined in
`docs/transmission-platform-concept.md`: functional members compose with generic
hub/bore/keyway modules through semantic references, while native Shaft/GEARS
commands remain black-box research oracles.
The implemented V-belt Layer 3 member may append an optional post-cut `IFillet`
manufacturing feature for upper groove edges; the functional cut sketch and its
sharp-profile analytical verification remain separate from that feature.
Its Layer 2 catalog keeps `din_iso` and `gost_20889_88` as independent standard
systems; dimensions, angle schedules, and standard fillet radii are never mixed
implicitly across systems.
The separate Poly-V Layer 2/3 member owns ISO 9982:2021 PH/PJ/PK/PL/PM data and
builds nominal `rt` plus deterministic maximum-`rb` rounded profiles directly in
one fully defined master/dependent cut sketch. Pitch, both radii, angle, linked
blank radius/width, axial center, and closure overshoot are live dimensions;
dependent grooves use equal/parallel/tangent contracts rather than fixed copied
points. Its CAD closure overshoots the blank only outside the material envelope
so the operational contour remains one simple component; the functional rim
geometry is unchanged. V-belt and Poly-V schemas and catalogs must not be merged
into one implicit family.
The Layer 4 pulley workflow creates a new owned rotational blank and applies the
existing family-specific Layer 3 groove builder inside the same unsaved KOMPAS
document. Arbitrary pre-existing bodies are intentionally outside this product
contract. Recognition scans the complete part-variable, sketch, and rotational
feature collections for a compound ownership fingerprint; it does not require
the managed groove to remain the last model-tree feature.
Recognized version-1 blocks support complete profile editing through the same
Layer 4 plan used for creation. Parameter-only edits update existing
`PULLEY_*` and family `VB_*`/`PV_*` variables and rebuild in place. Changes to
groove count, V-belt designation or standard, and standard-fillet presence or
radius use an owned topology replacement: strict preflight rejects any
non-owned downstream modeling operation, the bridge deletes only the managed
fillet/cut/sketch branch, reapplies the existing family-specific Layer 3 builder,
then verifies ownership, profile readback, and a positive-volume single body.
The original plan is supplied as rollback data; failed replacement removes a
partial new branch and recreates the prior managed branch. CUSTOM V-belt fields
and catalog overrides are stored as managed metadata so save/reopen inspection
can reconstruct the editable profile without relying on display names.
The flat-belt Layer 4 family is a separate owned rotational rim rather than a
groove cut over a cylindrical blank. It supports cylindrical and explicit
circular-crown profiles, uses `PULLEY_D1`, `PULLEY_L1`, and `FP_*` ownership
variables, and reuses the managed topology-replacement/rollback boundary for
profile edits. Belt routes, belts, and tensioners remain outside this family.
Its initial body is closed to the rotation axis and contains no bore; the rim
thickness, hub, bore, keyway, and shaft interfaces belong to separate generic
modeling modules. Its cylindrical and circular-crown sketches carry formula-bound
driving dimensions and must read back as fully defined. Studio bounds each
isolated bridge call and can cancel that child process without terminating
KOMPAS, so a stalled COM operation cannot retain the single CAD-job lock forever.
The trapezoidal timing-belt family is an approved managed Layer 4 Studio module.
Its internal Layer 3 construction covers numeric and parameterized T/AT mechanics:
a cylindrical blank, one closed groove sketch with six primary segments
and four true-radius arcs (two retained-tooth transitions tangent to the outside
circle plus two groove-root fillets),
a through-all cut, and a full circular pattern. The parameterized mode adds 15
semantic `TB_*` variables, eight auxiliary datum entities, 45 geometric
constraints, eight formula-bound sketch dimensions, blank-width binding, and
tooth-count/angular-step pattern bindings. The numeric mode remains available as
the accepted geometry baseline. Trapezoidal T/AT and curvilinear HTD profiles
remain separate Studio modules because their groove sketches have different
entity and constraint mechanics.
Each preview is a cropped end-view fragment of three grooves and two teeth with
a short tooth-tip reference arc, a closed lower/side break boundary, tangent
profile fillets, and distributed outside/root diameter plus groove width/depth
and fillet-radius dimensions;
both timing descriptors report `build=true`. Their Layer 4 blocks own a `TB_*`
and `GW_*` fingerprint,
two sketches, blank/cut extrusions, and circular pattern. Generated pattern
copies participate in the owned set and topology preflight, but only the five
root objects define the stable block identity. Parameter updates rebind and
read back blank width, pattern count, and angular step; failure restores the
previous variables and rebuilds the recognized block. Live create, designation,
tooth-count and width update, save/reopen, and rollback are accepted for both
T/AT and HTD. The HTD Layer 3 contour uses two true-radius outside-circle
transitions and one central root arc, 37 geometric constraints, and seven
formula-bound dimensions. Studio module
descriptors carry stable group/subgroup/family taxonomy so staged selectors can
separate a family path from modules without coupling identity to display structure.

The roller/bush-chain sprocket family has an initial create-only Layer 4 vertical
slice for single-row ISO 606 and GOST 591 profiles. Layer 2 supplies the exact
tangent-circle tooth-space contour and a standard-derived functional tooth width.
Catalog rows within the supported engagement-ratio range use the detailed KOMPAS-compatible GOST 591 working
construction: six arcs, two common-tangent segments, the unchanged `r`, `r1`,
and `r2` formula set, and a user-selectable offset or non-offset pair of
roller-seat arc centers. A separate three-segment cap closes the cut contour
outside the functional profile. In the
offset construction the physical right seat center is at `+e/2` and the physical
left seat center is at `-e/2`; the secondary-flank centers are translated from
their corresponding seat centers before tangent construction. ISO 606 and
GOST chain dimensions remain separate from the shared tooth-construction
algorithm; selecting the construction variant does not rewrite catalog pitch,
roller diameter, or inner width.

Layer 2 rejects ordinary tooth construction outside
`1.4 <= pitch / engagement_diameter <= 2.0` before CAD writes: GOST 591-69
limits its scope to lambda <= 2 and its Table 1 starts at 1.40. ПРИ rows above
that range use a separately labelled native-KOMPAS compatibility profile with
`K=0.532`. Five measured diameters for ПРИ-78.1-360 and one `z=60` diameter for
each remaining ПРИ row reproduce that rule to the displayed 0.01 mm. Layer 2
also verifies that the outside circle precedes the intersection of neighboring
`r2` branches, so the full circular pattern retains a blunt outside arc rather
than a pointed overlap. This policy is not presented as normative GOST 591 geometry.
`ISO_08A` (and its row-count variants) carries ISO 606:1994 dimensions from
GOST 13568-97, mandatory Annex A, Table A.1; it is not an alias for the existing
`ISO_40A` reference-catalog entry. The supplied ISO 606:2015 sample does not
establish dimensional equivalence between those entries. The root diameter is
`pitch_diameter - 2 * seating_radius`, per GOST 591-69 Table 1.

The KOMPAS application catalog's special B-1 rows `081` through `085` are
dimensionally separate from `08B-1` and carry their local provenance as
`Таблица ГВС 005-2015`; they are not presented as additional normative ISO 606
designations. These five simplex-only rows use the native
`0.93*Bvn-0.15` tooth-width formula. The public request field retains its
historical `gost_profile_variant` name for client compatibility, but Studio
labels and applies the selector to both ISO and GOST chains.
Layer 3 creates one cylindrical blank, one through-all tooth-space cut, and a full
circular pattern. Live ISO and GOST creation verifies a fully defined closed arc
sketch, pattern count, rebuild, and one positive-volume solid. In-place editing
remains outside this slice. Workspace readback does
recognize the create-only block from `GW_FAMILY_CODE=6`, the complete `CH_*`
fingerprint, and five root objects; generated pattern copies are owned but do not
participate in stable block identity. Because designation and profile variant are
not yet persisted as reconstructable metadata, reopened chain blocks remain
read-only.

Multi-row creation is available for catalog rows with both transverse pitch and
plate height. ISO 606:1994 A/B rows through 32A/32B are sourced from GOST
13568-97 Annex A Table A.1; missing old-ISO A rows such as 10A were added as
distinct profiles rather than aliased to ANSI-numbered entries. Axial data is
attached only after pitch, roller diameter, and inner width all match, preventing
the existing ANSI-derived `ISO_40A` key from being mistaken for old ISO 40A.
ANSI-numbered A-series rows 25A through 240A carry a separate ANSI B29.1
transverse-pitch and plate-height schedule converted with the exact 25.4 mm/in
factor. For narrow catalog gaps such as 05B, the normal GOST 591 `r4` remains
the preferred radius; when two such arcs cannot fit, the plan uses the largest
equal fitted radius while preserving a ten-percent central land and records the
selection policy in readback.
GOST 13568 PR/PV multi-row rows use their own Table 2 dimensions. A shared
Layer 2 axial layout supplies preview and CAD tooth width, pitch, total width,
and connecting-rim diameter. Multi-row widths use GOST 591-69 Table 2;
GOST 21834-87 NP/TP rows use the corresponding catalogue transverse-pitch and
plate-height schedule, so all three published chain-standard branches have
multi-row representatives in the same plan contract.
`Dc=floor(t*cot(pi/z)-1.3*h)` uses its maximum rim diameter and clause 1.5 rounding.
The first row is built at its own width, including both axial roundings. A
type-528 `ILinearPattern` copies the evaluated whole body along negative X;
`CH_N` and `CH_A` bind its count and pitch. After explicit rebuild, every row's
bounding box and the temporary body count must match the plan. A separate,
parameterized connecting-rim revolution then unites the rows. Final verification
checks one solid, total width, and volume against N finished rows plus cylindrical
gap material. Ownership includes the body pattern and rim but preserves the five
original identity references. Reopened models recover `row_count` from `CH_N`;
legacy models without that variable remain single-row. Missing catalog data is
a preflight error, not permission to estimate row pitch. Two- and three-row 08B
Z25 have live create/save/reopen and pattern-expression readback evidence. For
three rows the total width is 34.665 mm and the rim sketch reads fully defined
after reopen. In the two-row sample the rim sketch read
fully defined at creation and code 1 after reopen; that solver state still needs
UI confirmation. The connecting rim receives one circular-edge fillet feature
on all `2*(row_count-1)` internal ring junctions. GOST 591-69 Table 2 sets
`r4=1.6 mm` for pitch <=35 mm and `2.5 mm` above it. Preflight requires room
between adjacent fillets and below the root/rounding envelope. Edge resolution
uses unique circular body edges at the planned axial positions/rim radius, not
collection indexes. The concave fillets must add the analytically expected stock
and preserve overall bounds and one solid. The circular-edge helper is shared
with V-belt finishing, whose convex fillets retain their material-removal check.
Three-row 08B Z25 has create/save/reopen evidence for all four r4 junctions and
their radius, persisted ownership and body volume.
Three-row 10A Z25 and four-row 4PR-38.1 Z25 also have live create/save/reopen
evidence; the latter verifies six junction edges and the `r4=2.5 mm` branch.

Creation also appends two axial tooth-end cut revolutions, using GOST 591-69
Fig. 3/Table 2: minimum `r3 = 1.7 * engagement_diameter` and centre drop
`h3 = 0.8 * engagement_diameter`. These are functional axial profiles, not
constant-radius edge fillets. Each has a closed arc/three-line sketch with
constraints applied before its formula-bound dimensions. The owned YOZ blank
occupies global X `[-CH_B, 0]`; the two profiles enter that interval from its
opposite ends. Every cut must remove material and preserve a single solid.
The new sketches/rotations are owned, but the original five root references
remain the identity for both new and older chain blocks. Radius selection keeps
at least 20% of the face width as a flat tooth-tip land: this is an explicit
generator policy, not a GOST-prescribed dimension. It retains `r3=1.7D` when
`b >= 0.5D`; otherwise `r3=h3*h3/(0.8b)+0.2b`, derived from circular sag
`s=0.4b`. Both radii meet the normative minimum; width and h3 remain unchanged.
The selection is formula-bound in CAD, including the branch condition.
ISO 081 Z25 has live create/save/reopen evidence with b=2.919 mm,
r3=17.044916820829 mm and a 0.5838 mm tip land; both axial sketches read fully
defined after reopen. ISO 08A-1 Z25 has live create/save/reopen evidence
for both cuts and their radii, end placement, closed topology and ownership.
Both axial sketches read fully defined during creation; after reopen one read
code 1 and the other code 2, so the former still needs UI state confirmation.

The tooth-space sketch now exposes its independent construction through named
datum circles, centre spans, geometric constraints, and formula-linked dimensions.
The offset construction applies 41 in-sketch constraints and 17 sketch
dimensions; the degenerate `e=0` construction applies 35 and 14 respectively.
Both receive one additional post-build type-2 `point_on_curve`, so their final
constraint totals are 42 and 36. In the offset variant, one horizontal common
lower tangent joins the two trimmed roller-seat arcs, replacing their intersecting
bottom endpoints. Its length follows the centre span `CH_E`; two tangencies and
the existing centre/radius dimensions own it without another driving length.
This gives 12 contour entities (six arcs, six segments); the non-offset variant
retains 11 and never creates a zero-length bottom segment. Master
roller-seat, flank, and head arcs carry formula-bound driving radii `CH_R`,
`CH_R1`, and `CH_R2`; their mirrored dependents inherit equal radii. Six tangent
relations determine the working branch junctions in addition to the contour's
merge topology. The production workflow adds one `point_on_curve` from the start
of the right technical side line to the outside datum after blank, sketch, cut,
and pattern creation. This call is isolated and followed by independent readback
of the exact entity-reference pair, closed topology, gaps, and
self-intersections. A timeout is accepted only when that readback proves the
relation. The user confirmed both the saved and unsaved candidate sketches fully
defined in visible KOMPAS. API `ConstraintsState` may still report code 1 outside
that UI context and is therefore returned as diagnostics rather than used as the
sole verdict. The
non-working outer branch is deliberately linear: two equal
vertical `CH_CO` overshoots raise the horizontal closure to exactly
`CH_RA + 0.5 mm`, guaranteeing 0.5 mm radial clearance from the blank even for
small diameters. The horizontal line carries a visible reference width dimension
`CH_CW`; making that dimension driving creates a redundant closed-loop ownership
cycle in KOMPAS. The branch has no closure arc, auxiliary closure circle, or
intermediate top node. Both variants require exact initial applied counts,
post-build relation readback, radial-dimension readback, closed topology, full
feature completion, positive body, rebuild, and save/reopen evidence.

The `gear_spur` Studio module is the first cylindrical-gear family slice. Layer 2
`src/kompas_mcp/gears/` owns the ГОСТ 13755-2015 basic-rack standard with its
A–D modifications, the ГОСТ 9563-60 module rows, the analytic involute flank,
the theoretical sharp-rack trochoid root with undercut trimming, control
measurements (span length, constant chord, over-pin), and a structured check
report; the representation is `nominal`, not `generated_exact`. The Studio form
separates the standard from the contour modification and derives the profile
coefficients from that pair; only the user-defined modification exposes them as
inputs. Layer 3 `gears/cad.py` builds a create-only numeric plan: cylindrical
blank, one through-all cut whose flanks are smooth cubic Bézier-NURBS curves
split at the form point (root curve plus involute curve, seven entities per
tooth space), and a full circular pattern. The bridge
adds `GW_GEAR_VERSION=1`, `GW_FAMILY_CODE=8`, a `GEAR_*` readback fingerprint
with standard/modification codes, and a checksummed recipe; reopened blocks are
read-only and can recreate a new part from the persisted Studio profile. Live
create, volume/bounds/pattern verification, save/reopen recognition, and an
odd-tooth-count profile-shift case are accepted. Rounded cutter-tip
`generated_exact` roots, internal and helical families, pairs, and ISO
small-module contours remain outside this slice.

`silent_chain_sprocket` Studio preview adapts separate host-side GOST, DIN and
ASME-compatible profile mechanics plus their axial layout metadata into two
canvas views. Its catalogs cover GOST 13552-81/13576-81, secondary DIN 8190 A/B
rows, and ASME-compatible open-reconstruction pitch/guide metadata. DIN/ASME
choices retain explicit provenance and no-conformity warnings. The
descriptor advertises `preview=true`, `build=true` with a create-only Layer 4
functional-rim contract.
Its Layer 2 completion owner `studio/silent_chain_completion.py` separates source
data from explicit user construction choices. It exports a bounded completeness
report and a validated functional-rim geometry specification for CAD
planning, never a COM action. Construction intent is inferred from actual input
values; no mode selector or confirmation checkbox is required. Missing values
and unresolved radial conflicts cannot become CAD-planning-ready; this is not conformity,
strength, native sketch or B-Rep verification.
`transmissions/silent_chain.py` consumes that specification without importing
Studio or COM. Its numeric Layer 3 plan revolves the completed axial outline,
cuts a radial profile and patterns it around global X. Exact circular sample
runs become native arcs; other runs have bounded 0.0005 mm source-point
simplification. The bridge owns execution and actual profile/body readback,
including a source-cut-volume multiplier check for every pattern instance.
Missing construction inputs and unresolved source conflicts fail before document
creation. The `GW_SILENT_VERSION`/`SC_*` fingerprint recognizes five stable root
objects; generated copies are owned but excluded from identity. A persisted form
restores a new-part draft, not an in-place editor. Failures retain a structured
partial-document result; cancellation does not roll back KOMPAS operations.
DIN/ASME provenance warnings remain in force after CAD creation.

Geomwright Studio owns document/session navigation above Layer 4 modules. Its
workspace discovers open KOMPAS documents, opens saved files, presents managed
blocks together with surrounding unmanaged KOMPAS operations, and routes a
recognized block to its fixed-family editor. File selection, active-document
following, safe Save/Discard/Cancel closure, mixed-tree navigation, and editor routing belong to Studio rather
than to an individual pulley module. The first workspace slice supports one
managed block per document; multi-block cascade authoring is deliberately
deferred, while workspace data structures remain lists and carry stable block
identity so that future cascades do not require another navigation redesign.
Studio bridge calls attach through the COM Running Object Table to an already
running KOMPAS application and never create a COM server. If that registered
instance is hidden, Studio makes it visible and verifies visibility before any
document operation. If no application is registered, workspace reports a
recoverable disconnected state and retries after KOMPAS starts; file and CAD
writes remain unavailable until attachment succeeds.
Document activation and lifecycle writes resolve the exact current runtime ID;
they fail on stale IDs and never fall back to another active document. Changed
untitled documents require an explicit Save As path before close. Save and Save
As are document-level commands independent of block rebuild. Successful Layer 4
creation is followed by workspace readback; Studio enters the recognized new
block's editor only after matching the returned runtime document ID and module.

Подробные контракты находятся в `docs/`; runtime tool catalog остаётся источником
истины для фактически зарегистрированных MCP names.

## Сквозные оси

### Данные

Публичная граница использует JSON-совместимые dictionaries/lists/scalars.
Внутренние dataclasses и typed specs допустимы внутри владельца слоя, но нельзя
создавать второй публичный schema-contract для того же MCP tool.

Единый глобальный `EntitySpec` для всего проекта пока не является production
контрактом. Экспериментальные реализации не должны оборачивать существующие tool
responses или менять их shape без отдельной миграции.

### Состояние документа

Документ адресуется стабильным `document_id`; операции записи сопровождаются
snapshot/readback там, где это поддержано. KOMPAS остаётся stateful, но MCP не
предоставляет универсальную multi-call transaction/session abstraction.

Правила безопасности:

- preflight перед записью;
- явный target document/feature/sketch;
- fail-fast при невалидном COM-результате;
- сохранение и reopen-readback для законченного workflow;
- отсутствие скрытого fallback на другой документ или entity.

### Верификация

Уровень проверки выбирается по риску:

- нормализованный preview и инварианты Layer 2;
- operation/model-object readback;
- snapshot delta;
- body/topology/formula inspection;
- reopen-readback сохранённой модели;
- визуальная проверка только там, где B-Rep и COM readback не выражают нужный
  критерий.

## Production boundary

Production surface состоит только из модулей, импортируемых зарегистрированным
MCP server и описанных канонической документацией. Research-only native-module
tools регистрируются только при явном `GEOMWRIGHT_ENABLE_RESEARCH_TOOLS=1` и не
входят в обычную публичную MCP-сессию.

Опциональные presentation adapters могут поставляться в том же Python package,
но не становятся частью MCP production surface автоматически. Их capability
contract и граница с CAD runtime должны быть описаны отдельно.

Незаконченные OperationGraph, universal rule engine, template library, session
tracking и spring-readback prototypes помещаются в ignored-зону
`experiments/spikes/`. Они не являются частью package, tool catalog или roadmap,
пока не выполнены одновременно:

- один явный owner layer;
- package-data contract;
- корректная propagation ошибок и зависимостей;
- schemas, выведенные из реальных MCP tools;
- Verify/Correct semantics;
- документация публичной миграции.

Исторические task briefs также не являются roadmap.

## Текущее состояние

| Компонент | Слой | Статус |
| --- | --- | --- |
| session/document lifecycle | L1 | stable |
| specifications, relinking, composition | L1–L3 | stable |
| low-level sketch/feature runtime | L1–L2 | experimental |
| `sketch_runtime/` | L2 | current deterministic core |
| parametric part workflows | L2–L4 | experimental, family-specific live evidence |
| managed spring families | L2–L4 | implemented, see family contracts |
| cam profiles | L2–L4 | create-only single cam, shared Studio/MCP plan, actual curve/contact/body verification |
| diaphragm module | L2–L4 | complete and live-verified |
| mechanical-transmission platform | L2–L4 | managed V-belt, Poly-V, timing and flat-belt pulley workflows plus live-verified create-only single-row ISO/GOST chain sprockets and external spur gears |
| Geomwright Studio | presentation over L2–L4 | experimental; create-only completed silent-chain rims and gear blocks, managed pulley previews/build, and no arbitrary-body write path |
| native module inspection/launch | L1–L3 | research, explicit opt-in for registration and launch |
| universal OperationGraph/Rule Engine/templates | — | not production; quarantined prototype |

## Документационная иерархия

1. `README.md` — установка, runtime status и первый workflow;
2. этот файл — ownership и production boundaries;
3. `CAD_PATTERNS.md` — переносимые CAD-инварианты;
4. `docs/README.md` — индекс тематических контрактов;
5. `experiments/spikes/` — локальная ignored-зона для исторических и незавершённых
   материалов, не входящих в публичный runtime.

## Связанные документы

- [Documentation index](docs/README.md)
- [Reusable CAD patterns](CAD_PATTERNS.md)
- [Low-level runtime](docs/low-level-runtime.md)
- [Write operations](docs/write_operations.md)
- [Sketch authoring agent protocol](docs/sketch-authoring-agent-protocol.md)
- [Parametric workflows](docs/parametric-workflows.md)
- [Spring workflows](docs/spring-workflows.md)
- [Diaphragm spring](docs/diaphragm-spring.md)
- [Geomwright Studio](docs/geomwright-studio.md)
