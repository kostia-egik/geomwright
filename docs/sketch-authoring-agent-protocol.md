# Sketch Authoring Agent Protocol

Status: current agent workflow contract for staged sketch generation and
readback. Geometry-design guidance remains in the companion draft.

Machine-oriented companion to [`sketch-authoring-protocol.md`](sketch-authoring-protocol.md).

Audience: coding agent working on KOMPAS sketches in Geomwright.

Purpose: force a complex sketch to pass through an explicit contract and staged
verification before implementation grows into debugging by accident.

This document is agent-executable. Prefer this file during implementation. Use
the human protocol when deciding whether the rules themselves need to change.

## Required references

Before creating or changing a complex sketch, consult these project rules:

- `CAD_PATTERNS.md`, especially `SKETCH-001`, `SKETCH-002`, `SKETCH-003`,
  `SKETCH-004`, `SKETCH-005`, `SKETCH-006`, `SKETCH-008`, `SKETCH-009`,
  `OP-001`, `OP-002`,
  `PROFILE-001`, `VAR-001`, `VERIFY-001`.
- `docs/sketch-authoring-protocol.md` for human rationale.
- `docs/sketch-diagnostics.md` and `docs/inspect-sketch-full-report.md` for
  diagnostics/readback vocabulary.

Do not treat successful `Update()` as proof of correctness. Sketch success must
be supported by style/contour checks, constraints/dimensions state, operation
success, and readback appropriate to the task.

Do not create ordinary tests for sketch work. Verification for this repo is CAD
probe/live creation/readback unless the user explicitly authorizes a central
critical integration test.

## Use this protocol when

Use this protocol before code if any condition is true:

- sketch has arcs, fillets, tangency, projections, helper geometry, or multiple
  semantic zones;
- sketch feeds revolve, extrude/cut, sweep/evolution, pattern, or any operation
  that can choose a wrong contour/region/path;
- sketch has variables, formulas, named dimensions, or must survive parameter
  changes;
- sketch depends on external geometry/projection references;
- prior implementation attempts required live debugging or readback.

Skip only for trivial, local sketches with one obvious contour, no helper
geometry, no formulas, and no known KOMPAS risk.

## Mandatory output before implementation

Before writing or changing generator code for a complex sketch, produce a Sketch
Contract in work notes. If the contract cannot be filled, stop and ask the user
or run a bounded probe. Do not fill unknown fields with guesses.

```text
Sketch Contract
Name:
Consumer operation:
Operation class: revolve | extrude/cut | sweep-profile | sweep-path | auxiliary | other
Contour class: closed-profile | open-path | auxiliary-contour
Expected contour count: 1 unless explicitly justified
Line style map:
  main:
  axis:
  auxiliary/thin:
Base mode: origin/axis/plane | circle-center | projection-anchor | hybrid
Base anchor:
Projection sources:
Projection results:
Projection constraints/readback plan:
Coordinate system / plane assumptions:
Semantic points:
Symmetry/repetition class: none | mirror pair | repeated family | shared-level family
Master element:
Symmetry/repetition axes (auxiliary unless they are the consumer axis):
Inherited relations: midpoint | symmetric | equal | parallel | collinear | shared level | pitch chain | formula-linked dimension
Dependent elements and allowed independent dimensions:
Primary contour order:
Open path start/end/direction:
Axis ownership:
Auxiliary geometry:
Driving variables:
Derived variables kept:
Variables deliberately not exposed:
Constraint plan:
Dimension target plan:
Formula binding plan:
Full-definition target or exception:
Geometry-only gate:
Post-constraint gate:
Post-dimension/preflight gate:
Operation gate:
Save/reopen/readback gate:
Known risky assumptions:
Decision: proceed | ask user | run probe | split sketches | simplify
```

## Non-negotiable definitions

Line styles define operational categories.

- Main style: source of the operation's primary closed profile or open path.
- Axis style: actual revolve axis, or explicitly declared graphical/symmetry
  axis. Do not use axis style for ordinary helper geometry.
- Auxiliary/thin style: construction geometry only. It must not be consumed as
  profile, path, or operation axis.

Contour classes are distinct.

- Closed profile: one closed main-style contour that defines an operation region
  or sweep cross-section. Default rule: one operation sketch, one closed profile.
- Open path: one directed main-style open chain with one start and one end. It is
  not a profile and does not define a region.
- Auxiliary contour: reference/construction geometry. It must not be consumed by
  the operation unless reclassified in the contract.

Base modes are distinct.

- Origin/axis/plane: a semantic element is attached to local origin, coordinate
  axis, or base plane.
- Circle-center: local origin is at the center of circular/radial geometry.
- Projection-anchor: geometry is based on projected external objects. Projection
  source/result/constraints are part of the contract.
- Hybrid: allowed only when each base responsibility is named.

Variables are interface elements, not debug dumps.

- Driving variable: controlled by user/scenario and changes model intent.
- Derived variable: computed from other variables and exposed only when it helps
  formulas, readability, or verification.
- Hidden calculation: internal generator value; do not expose as a KOMPAS
  variable only because it was convenient to compute.

Symmetric and repeated geometry is a family, not a set of independently
dimensioned copies.

- Select one master element and dimension its independent shape parameters.
- Place each dependent element through named family relations: symmetry about a
  declared axis, midpoint-to-axis, equal length/radius, parallel/collinear or
  shared-level constraints, and edge/pitch chains.
- A declared graphical symmetry axis may use axis style when it cannot be
  confused with a consumer-operation axis. When several family axes share an
  operational sketch, keep them auxiliary/thin. A revolve sketch still has
  exactly one axis-style operation axis.
- Do not repeat the same independent driving dimension on every copy. If KOMPAS
  rejects a native equal/symmetric relation as redundant, a dependent dimension
  is allowed only as a formula-linked fallback whose expression references the
  master semantic variable.
- Seed initially coincident/equal helper geometry with a bounded non-degenerate
  offset when needed so the intended merge/equal relation is actually created.
  The final readback must show the intended exact relation, not the seed offset.
- Planned family constraints must be applied, not merely skipped as redundant.
  Remove a truly redundant relation or move it to an earlier pre-constraint
  phase where it carries the intended ownership.
- Every family variable must either bind a surviving driving dimension or be
  referenced by another published formula. Do not keep per-copy coordinate,
  count, datum-display, or debug variables with no downstream consumer.

## State machine

Follow phases in order. Do not advance with a failed gate unless the exception is
explicitly recorded in the Sketch Contract.

### Phase 0: scope and decomposition

Decide whether the geometry belongs in one sketch.

Pass criteria:

- one sketch has one consumer operation or one clearly declared auxiliary role;
- operation does not need to guess between several unrelated regions;
- profile and path are not mixed unless the operation/API explicitly requires it;
- multiple profiles/paths are explicitly justified.

Stop if:

- sketch would contain several independent operation regions;
- helper geometry is required only to make region selection possible;
- profile/path ownership is unclear.

Required action on stop: split sketches, simplify operation sequence, or ask the
user.

### Phase 1: topology contract

Define semantic points, contour order, styles, base mode, and operation consumer.

Pass criteria:

- closed profile has ordered loop `A -> ... -> A`;
- open path has ordered `start -> ... -> end` and direction;
- every axis/helper element has declared style and purpose;
- base anchor is one of the named base modes;
- projection-based sketch declares source/result/constraint plan.
- symmetric/repeated geometry declares its master, family axes, inherited
  relations, and any justified independent dependent-element dimensions.

Stop if:

- contour order is unknown;
- line style category is unknown;
- base anchor is “whatever coordinates work”;
- projection source is inferred only from nearby coordinates.

### Phase 2: geometry-only build

Build minimal sketch geometry before constraints, dimensions, and variables.

Pass criteria for closed profile:

- one closed main-style component;
- no gaps, branches, extra main-style components, or self-intersections;
- auxiliary/thin geometry does not pollute main profile;
- revolve sketches have exactly one declared axis-style operation axis.
- repeated elements are present as the intended number of clean components, but
  no family relation is assumed merely from equal seed coordinates.

Pass criteria for open path:

- one start and one end;
- expected direction is verified or probe-planned;
- no branches, unintended components, or gaps;
- path is not accidentally closed unless explicitly required.

Stop if operation cannot consume geometry-only sketch. Do not add constraints to
hide a topology/style problem.

### Phase 3: constraints

Add constraints after the geometry-only contract is clean.

Pass criteria:

- each constraint expresses a named engineering relation;
- projection constraints are created while required handles are live
  (`SKETCH-005`, `SKETCH-006`);
- constraint application does not change contour class or operation target;
- `ConstraintsState`/`sketch_state` is read when available.
- master constraints are applied before dependent-family inheritance;
- midpoint/symmetry/equal/collinear/pitch relations use semantic element names;
- applied count equals planned count and skipped family constraints equal zero.

Stop if:

- a constraint exists only “to calm solver” with no named relation;
- projection source cannot be confirmed and matters to model intent;
- constraints move the contour into a different semantic state.
- a repeated element is positioned by copied coordinates or duplicate fixed
  points instead of a named family relation.

### Phase 4: dimensions

Add dimensions only to named targets.

Pass criteria:

- every dimension target has semantic name;
- applied count equals expected count;
- no failed dimensions;
- closed profile remains closed and clean;
- open path keeps expected start/end/direction;
- readback/preflight confirms no hidden contour damage.
- master dimensions are created once; every dependent dimension is either
  independently meaningful or formula-linked to a named master variable;
- every surviving driving dimension reports a valid variable expression.

Stop if:

- dimension target is a fragile index without semantic alias;
- applied dimension creates gap, branch, extra component, self-intersection, or
  wrong direction;
- a dimension formula needs a variable that is not in the variable policy.
- the same family parameter is independently driven on multiple copies without
  an explicit engineering reason.

### Phase 5: full definition

Default target for parameterized sketches: fully defined (`SKETCH-001`).

Pass criteria:

- `ConstraintsState`/`sketch_state` reports fully defined after update/readback;
  or
- an explicit exception documents why KOMPAS state is unreliable and lists
  alternative evidence.

Acceptable alternative evidence may include:

- clean profile/path preflight;
- all dimensions applied;
- operation succeeds;
- saved/reopened model readback matches intent;
- known KOMPAS `ConstraintsState` instability is documented for this sketch.

Stop if sketch is under-defined and no exception exists.

### Phase 6: variables and formulas

Create the variable table after geometry, constraints, and dimensions are known.

Pass criteria:

- driving variables are minimal and user/scenario meaningful;
- derived variables have a named purpose;
- decorative/debug variables are excluded;
- complex formulas are verified or hidden inside generator;
- formula binding uses known project pattern when COM rejects direct formula
  fields (`VAR-001`).
- no family variable is orphaned: each binds a surviving dimension or is used by
  another kept formula.

Stop if:

- a published variable has no user/debug/formula purpose;
- formula is mathematically plausible but not verified in KOMPAS expression
  parser;
- variable makes a hidden geometric assumption look authoritative.

### Phase 7: operation assignment

Assign sketch to the consuming operation.

Pass criteria:

- operation consumes declared contour/path/profile, not helper geometry;
- operation assignment uses established fallbacks where needed (`OP-001`);
- one operation sketch / one operational contour principle holds unless an
  exception is declared (`OP-002`);
- sweep profile is placed at canonical path end when applicable (`PROFILE-001`).

Stop if operation succeeds visually but selection/ownership is ambiguous.

### Phase 8: save, reopen, readback

Finalize with live CAD verification proportional to risk.

Pass criteria:

- model builds live;
- file is saved after late sketch/projection/constraint edits (`SKETCH-008`);
- reopened/readback geometry agrees with contract when required;
- diagnostics show no profile/path failures relevant to the operation.

Stop if live state and readback disagree. Prefer readback/live facts over API
assumptions.

## Operation-specific branches

### Revolve

Required:

- one closed main-style profile;
- one axis-style operation axis;
- helper geometry auxiliary/thin, not axis;
- radii and heights measured from named semantic points;
- geometry-only revolve before dimensions/variables.

Stop if:

- more than one axis-style candidate exists;
- helper geometry can be interpreted as profile or axis;
- OD/ID/base height/body radius are not tied to named points.

### Extrude or cut

Required:

- one intended closed main-style region unless multiple regions are explicitly
  justified;
- no helper lines crossing the region as operation geometry;
- region selection is deterministic for automation.

Stop if UI-like manual region choice would be required.

### Sweep/evolution profile

Required:

- closed local cross-section profile;
- profile position tied to canonical path endpoint or declared anchor;
- profile does not carry old/global offsets unless justified.

Stop if profile compensates for path placement errors.

### Sweep/evolution path

Required:

- open directed path with start/end;
- final path sequence is canonical;
- generated/intermediate/result edges are not confused;
- local CS/phase/direction assumptions are verified when uncertain.

Stop if path direction, phase, or selectable result edge is guessed. Use
`VERIFY-001` probe/readback.

### Projection-based sketch

Required:

- projected source named;
- projected result named;
- style of projected result set intentionally (`SKETCH-003` when needed);
- constraints attach sketch geometry to projection results, not copied
  coordinates (`SKETCH-006`);
- missing projection source is escalated to user/UI confirmation (`SKETCH-002`).

Stop if projection relation is inferred only from coincident coordinates.

### Symmetric or repeated profile family

Required:

- one named master profile/feature element;
- one declared auxiliary axis per symmetry center or repeated-element center as
  needed;
- dependent placement through midpoint/symmetry and edge/pitch relations;
- dependent shape inherited through equal, parallel, collinear, shared-level, or
  formula-linked dimensions;
- no duplicate display-only dimensions or datum constructions in the operational
  sketch;
- exact readback: all planned pre/final constraints and dimensions applied,
  skipped count zero, intended component count preserved.

Preferred order:

1. anchor the global/base datum;
2. constrain and dimension the master element;
3. place dependent axes/centers through edge and pitch chains;
4. apply midpoint/symmetry and shared-level relations;
5. inherit dependent shape through equal/collinear relations;
6. use a formula-linked dependent dimension only when the native relation is
   unstable or rejected by KOMPAS;
7. update, settle once if required, then verify full definition and family
   topology from readback.

Stop if a visually symmetric result is produced by independently fixed copies,
duplicate numeric dimensions, or skipped family constraints.

### Auxiliary/reference sketch

Required:

- declared non-operation role;
- all geometry style and downstream consumer documented;
- no accidental operation consumption.

Stop if auxiliary sketch becomes an undeclared second operation sketch.

## Direction and arc uncertainty

When direction matters and is not proven, apply `VERIFY-001`.

Use probe/readback for:

- arc clockwise/counterclockwise semantics;
- path start/end and sweep direction;
- local coordinate axes and angled planes;
- spiral phase and construction side;
- result edge ownership after trimming/fillet.

Do not rely on visual intuition for direction-sensitive geometry.

## Stop and ask the user when

Ask instead of guessing if any condition is true:

- two or more base anchors are plausible and change model meaning;
- operation may require multiple profiles or region selection strategy;
- projection source cannot be identified and affects model intent;
- fully defined state cannot be reached and no known KOMPAS instability explains
  it;
- a derived variable would expose a questionable engineering meaning;
- user-facing parameter semantics are ambiguous.

## Required work-note report

When handing off a complex sketch change, report these items:

```text
Sketch protocol report
Contract status: complete | partial | exception
Consumer operation:
Contour class:
Line styles verified:
Base mode:
Projection status:
Symmetry/repetition status:
Geometry-only gate:
Constraints gate:
Dimensions gate:
Full-definition status:
Variables kept/removed:
Operation/live result:
Readback/preflight result:
Known exceptions:
Files changed:
Artifacts saved:
```

Do not claim a sketch is done if the report has an unresolved failed gate.

## Minimal pre-code checklist

Use this compact checklist when the task is moving fast:

```text
[ ] Human intent understood
[ ] Sketch Contract filled
[ ] One sketch vs multiple sketches decided
[ ] Contour class declared
[ ] Line style map declared
[ ] Base mode declared
[ ] Projection sources/results declared or N/A
[ ] Semantic points named
[ ] Master/dependent symmetry or repetition plan declared or N/A
[ ] Symmetry/repetition axes use intentional line styles
[ ] No duplicate family dimensions; any fallback is formula-linked
[ ] Driving variables named
[ ] Derived variables justified
[ ] Geometry-only gate planned
[ ] Full-definition target/exception planned
[ ] Live/readback gate planned
```

If any unchecked item is relevant and unknown, do not proceed directly to
implementation.
