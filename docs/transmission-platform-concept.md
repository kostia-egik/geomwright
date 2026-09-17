# Transmission platform concept

Status: approved architecture concept. No transmission family is exposed as a
production MCP module until its family contract and live KOMPAS evidence are
complete.

Current implementation status: focused Layer 2 catalogs and Layer 3
cut-from-body builders are available for V-belt and Poly-V grooves as documented
in `v-belt-groove.md` and `poly-v-groove.md`. The first Layer 4 vertical slice
creates a new owned blank and applies and verifies both V-belt and Poly-V grooves.
The flat-belt family adds a standalone cylindrical or explicitly crowned owned
rim without introducing belt-route or tensioner scope.
Its ownership inspector recognizes a managed pulley independently of its
position in the model tree. Flat-belt create, inspect, update, save, and reopen
have live KOMPAS evidence; remaining Layer 4 work belongs to other transmission
families.

This document defines the planned mechanical-transmission platform for
Geomwright. The goal is not to copy one native KOMPAS application as a
monolith. The platform separates catalogs, deterministic geometry, pair
synthesis, manufacturing-tool envelopes, CAD execution, and optional
engineering calculations.

## 1. Scope and principles

The platform follows these rules:

1. Transmission modules own only functional transmission geometry.
2. Hubs, bores, keyways, threads, chamfers, and generic shaft features remain
   separate reusable modules.
3. Every result publishes semantic references for later composition.
4. Geometry generation and strength/life calculations are separate products.
5. Native KOMPAS applications are black-box oracles, not runtime dependencies.
6. Complex families are split by real geometric method, not hidden behind one
   large `type` parameter.
7. Catalog values carry standard edition and provenance.
8. `preview → execute → verify → reopen` is mandatory for each Layer 4 family.
9. Pulley families create and own a new parameterized rotational blank; they do
   not cut grooves into an arbitrary pre-existing body.
10. Recognition and editing use persistent module ownership plus managed
    variables and operations. User features created later in the model tree are
    downstream consumers and must survive a managed pulley rebuild whenever
    KOMPAS can rebuild that dependency cascade.

Relevant existing CAD rules are `GEOM-006`, `GEOM-009`, `GEOM-010`,
`GEOM-012`, `GEOM-014`, `EXEC-003`, and `EXEC-004` in `CAD_PATTERNS.md`:
closed revolved contours, non-overlapping primary geometry, explicit seam
handling, stable references, and readback-oriented execution.

## 2. Layer ownership

### Layer 1 — atomic CAD operations

Existing sketch, rotation, extrusion, cut, evolution, pattern, plane, local-axis,
composition, and readback tools remain the only COM owners.

Transmission code must not add a parallel COM path.

### Layer 2 — deterministic transmission mathematics

Planned owners:

- catalog normalization;
- pitch geometry;
- profile curves;
- generating-tool geometry;
- tool-envelope calculation;
- interference and undercut checks;
- profile-shift feasible regions and selection;
- belt-route and pair-placement mathematics;
- family-specific parameter validation.

Layer 2 returns JSON-compatible numbers, points, segments, curves, factors, and
warnings. It does not access KOMPAS.

### Layer 3 — managed CAD plans

Layer 3 converts a normalized transmission plan into operations such as:

- revolve functional rim;
- sketch one groove/tooth space;
- cut or add one periodic element;
- circular pattern;
- sweep or loft a helical member;
- attach to an existing body;
- append verified fillet/chamfer manufacturing features to semantic edges;
- name variables and semantic references;
- hide auxiliary geometry;
- collect snapshot and readback evidence.

### Layer 4 — user-visible transmission families

Each family has its own public schema, build plan, acceptance criteria, and
canonical live artifacts.

## 3. Composition contract

Transmission families must not duplicate hubs, bores, or other generic details.

### Input

```text
target_body_ref       existing body or null
axis_ref              rotation/member axis
origin_ref            member origin/frame
mounting_plane_ref    axial placement plane
axial_offset          displacement from mounting plane
combine_mode          new_body | add_to_body | cut_from_body
parameter_prefix      variable namespace
```

The family-specific input contains only functional geometry: groove profile,
tooth system, width, pitch dimensions, hand, representation mode, and relevant
manufacturing data.

The generic composition contract above remains applicable to transmission
families as a whole, but the V-belt and Poly-V pulley families deliberately use
only `new_body`. Their Layer 4 workflow creates the known cylindrical rim blank
and then applies the managed groove operation to that owned blank. Arbitrary
`add_to_body` and `cut_from_body` targets are not part of the pulley product
contract; the existing focused cut builders remain internal composition steps
and acceptance fixtures.

The owned blank is the stable root of later pulley development. Hub, bore,
keyway, chamfer, relief, and other operations may be appended by separate
modules or by the user. Recognition must therefore locate the owned blank,
groove feature, ownership metadata, and variable namespace without assuming
that the groove feature is the final item in the model tree.

### Output

`TransmissionBuildResult` must provide semantic references rather than forcing
downstream modules to rediscover anonymous COM objects:

```text
member.body
member.axis
member.origin
member.left_face
member.right_face
member.rim_root
member.outer_rim
member.pitch_surface
member.functional_feature
member.pattern_feature
member.mounting_plane
```

It also provides:

- inner attachment radius and reserved root zone;
- usable axial attachment interval;
- interference envelope;
- variable/formula map;
- operation ownership map;
- body count and topology summary;
- hidden auxiliary objects;
- snapshot/readback report;
- warnings and incomplete checks.

Generic hub, bore, keyway, spline, thread, and finishing modules consume these
references afterwards.

## 4. Core data contracts

### `CatalogEntry`

```text
family
designation
standard
standard_edition
source
license_or_provenance
dimensions
applicability
notes
```

Copied standards tables cannot be committed without redistribution rights.
Manufacturer data must retain its source and applicability limits.

### `PitchGeometrySpec`

Describes the kinematic reference geometry:

- pitch circles/cylinders/cones;
- member axes;
- shaft angle and axis offset;
- center distance;
- ratio;
- reference planes;
- phase and mesh orientation.

### `GeneratingToolSpec`

```text
tool_type
profile_source
module_or_pitch
pressure_angle
addendum
dedendum
tip_radius
protuberance
profile_shift
cutter_tooth_count
lead_and_starts
modifications
```

Confirmed native KOMPAS tool families include hobs for involute cylindrical
gears, Novikov gears, roller/bush sprockets, splines and worm wheels, plus
gear-shaper cutters for involute cylindrical gears. A universal arbitrary cutter
API is not assumed.

### `ProfileShiftPlan`

```text
x1
x2
sum_x
selection_method
feasible_region
blocking_contour
criteria
contact_ratio
tip_thickness
undercut
interference
warnings
```

Supported conceptual modes:

1. fixed `x1/x2`;
2. manual point inside the feasible region;
3. multicriteria selection;
4. joint rack-contour and shift optimization.

### `RepresentationMode`

```text
envelope          bounding solid only
nominal_teeth     analytical nominal profile
generated_exact   flank/root generated from a manufacturing-tool envelope
```

`generated_exact` is accepted only after family-specific comparison against a
trusted oracle or licensed worked example.

## 5. Native KOMPAS baseline

Official ASCON documentation and the installed Shaft manifest describe two host
workflows plus one standalone calculation path.

```text
2D drawing/fragment
    ↓ command 201: Shaft 3D+2D model designer
2D shaft/transmission assembly model
    ↓ select a calculated member
GEARS calculation backend
    ↓ result returns to the Shaft owner
updated 2D mechanical model
    ↓
3D member/model generation
```

```text
3D part
    ↓ command 206: Shaft 3D model designer
select a concrete member
    ↓ GEARS when that member requires calculation
calculation result returns to the 3D host
    ↓
one 3D member is generated in the part context
```

```text
command 202: standalone GEARS
    ↓
calculation UI/result file
    ↓
no Shaft owner, therefore no automatic drawing or 3D result
```

In the first workflow, the visible drawing is not the complete source of truth.
Internal model data stores calculation objects, generation settings, hierarchy,
and update links. GEARS is the calculation backend; Shaft 3D+2D or Shaft 3D owns
the generated CAD result.

Officially documented families include:

- external/internal involute cylindrical gears;
- helical, crossed-helical, rack, face/crown, arched and Novikov variants;
- straight, circular-tooth, tangential and internal straight bevel gears;
- hypoid pairs;
- cylindrical and globoid worm families and worm-rack variants;
- V-belt, timing-belt and flat-belt drives;
- roller, bush and toothed drive chains;
- straight-sided, involute and triangular splines;
- planetary, pin/roller, lantern, clock and gear-pump mechanisms;
- gear couplings and gear-cutting tools.

Availability may depend on license and application package.

Official sources:

- [KOMPAS-GEARS, April 2025](https://kompas.ru/source/info_materials/2025/Gears.pdf)
- [Shaft 2D/3D, April 2025](https://kompas.ru/source/info_materials/2025/Shaft-3d.pdf)
- [Shaft 2D/3D product page](https://kompas.ru/kompas-3d/application/machinery/shafts-3d/)
- [Gear-cutting tool application](https://kompas.ru/kompas-3d/application/machinery/gear-cutting/)

No public headless calculation API or documented COM object model for GEARS was
found. Command dispatch is available through the registered native application,
but the caller context is essential. Direct command 202 dispatch is useful only
for standalone calculations or saved calculation files; it is not a model-build
workflow. Native KOMPAS command inspection is a separate research-only surface
and is not required for the managed workflow.

Native UI experiments are never run in a shared working KOMPAS session. Command
206 successfully opened the Shaft 3D host during the first pulley audit, but the
manual workflow produced repeated native errors and required an operator restart.
Future experiments therefore require a dedicated disposable process with all
user documents saved and closed.

## 6. Belt-drive modules

### Near-term functional members

1. `v_belt_groove`
2. `poly_v_groove`
3. `flat_belt_pulley`
4. `timing_pulley`

These modules either cut functional grooves into an existing rotational body or
create only the functional rim. They do not create hubs or bores.

V and Poly-V are separate families. Poly-V PH, PJ, PK, PL, and PM profiles are
implemented from ISO 9982:2021 Table 2 evidence. The managed profile uses nominal
`rt`, maximum `rb`, one exact rounded sketch boundary, and a body-clipped closure
overshoot. Its master groove drives pitch, radii, and angle while repeated grooves
inherit equal/parallel/tangent relations; it does not reuse straight-sided V-belt
geometry or fixed copies of the profile points.

Timing-pulley construction uses a blank plus one tooth-space cut and a circular
pattern. Profile families remain separate catalog entries because some shapes
are manufacturer-specific.

### Belt route and static body

Separate planned modules:

1. `belt_pitch_route`
2. `v_belt_static`
3. `poly_v_belt_static`
4. `flat_belt_static`
5. `timing_belt_static`

The first level models an ideal taut belt using tangent branches, wrap arcs,
pitch length, open/crossed topology, and optional idlers/tensioners. Elastic
deformation, centrifugal effects, and force-dependent sag are later calculation
modules.

## 7. Cylindrical gear platform

Planned progression:

1. `involute_profile`
2. `rack_cutter_profile`
3. `profile_shift_feasible_region`
4. `profile_shift_selector`
5. `generated_root_trochoid`
6. `spur_external_gear`
7. `spur_internal_gear`
8. `rack_gear`
9. `spur_gear_pair`
10. `helical_gear`
11. `herringbone_gear`
12. `crossed_helical_pair`
13. `planetary_layout`
14. `planetary_tooth_synthesis`

The initial calculation product is geometric synthesis and profile-shift
selection, not a complete certified strength-rating package.

## 8. Bevel and hypoid families

These are independent Layer 4 modules:

- `straight_bevel_pair`;
- `circular_bevel_pair`;
- `tangential_bevel_pair`;
- `internal_straight_bevel`;
- `hypoid_pair`;
- `crown_face_pair`.

Hypoid geometry has non-intersecting axes and a separate pitch/contact model; it
is not a bevel flag. Circular-tooth native pair generation is stateful: the
wheel is generated first and the pinion is derived from the same/latest
calculation. That ordering must become an explicit workflow dependency.

## 9. Worm families

Independent planned modules:

- `cylindrical_worm_pair`;
- `worm_helical_wheel_pair`;
- `globoid_worm_pair`;
- `worm_rack_pair`;
- `worm_wormrack_pair`.

Each supports `envelope` first. Tool-envelope/generated wheel geometry is a later
acceptance gate.

## 10. Chains — deferred

Chain implementation is postponed until assembly manipulation is reliable.

Two representation strategies remain open:

1. assembly of reusable links, rollers, pins, and plates;
2. one static part/body for layout-only use.

Future families include roller, bush, toothed-drive, and silent/inverted-tooth
chains. Sprocket profiles and catalog contracts may be researched independently,
but no chain Layer 4 module is scheduled before the assembly decision.

## 11. Calculation scope

### First calculation product

- pitch geometry;
- feasible profile-shift region;
- blocking contour;
- undercut and tip-point checks;
- contact ratio;
- geometric interference;
- multicriteria `x1/x2` selection;
- generating-tool profile and root envelope;
- factor-by-factor explanation.

### Later optional products

- forces and bearing reactions;
- contact and bending rating;
- load spectra and fatigue life;
- wear/scuffing factors;
- lubrication and thermal checks.

Strength/life calculations require a licensed standard edition, traceable
materials, worked-example validation, and a separate disclaimer/accuracy
contract. Geometry does not silently depend on an unvalidated rating engine.

## 12. Logical extensions beyond native KOMPAS

Practical extensions:

- automatic integer planetary synthesis;
- transmission ratio distribution across multiple stages;
- reducer layout and shaft placement;
- reverse engineering from tooth count, diameters, span, and over-pin measures;
- manufacturing inspection dimensions;
- geometric line-of-action/contact-path visualization;
- automatic belt routing and tensioner placement;
- cycloidal reducer geometry.

Research-only extensions:

- non-circular gears;
- harmonic/strain-wave drives;
- general face gears;
- spiroid and exact globoid contact;
- physically accurate toothed-chain contact;
- traction/CVT mechanics.

## 13. Open-source references

Permissive mathematical references:

- [py_gearworks](https://github.com/GarryBGoode/py_gearworks), Apache-2.0;
- [BOSL2](https://github.com/BelfrySCAD/BOSL2), BSD-2-Clause;
- [cq_gears](https://github.com/meadiode/cq_gears), Apache-2.0;
- [bd_warehouse](https://github.com/gumyr/bd_warehouse), Apache-2.0.

GPL reference/oracle only:

- [FreeCAD Gears](https://github.com/looooo/freecad.gears), GPL-3.0;
- [NopSCADlib](https://github.com/nophead/NopSCADlib), GPL-3.0-or-later.

Open-source code is a mathematical reference, not proof of compliance with a
standard or manufacturing process.

## 14. Delivery sequence

### Phase 0 — contracts and pulley-oriented native audit

- composition contract;
- catalog provenance;
- pitch/tool/profile-shift schemas;
- native Shaft command/context map;
- one V-belt pulley through the normal manual Shaft 3D UI in a dedicated process;
- command 206 comparison only after the manual route is understood;
- the same pulley through command 201 in a disposable 2D mechanical model;
- comparison of catalog parameters, operation trees, and generated geometry.

### Phase 1 — belt feature modules

- V-belt groove — Layer 2 catalog/preview and focused Layer 3 cut-from-body
  builder implemented and live-verified;
- poly-V groove;
- flat pulley — cylindrical and explicit circular-crown Layer 2/4 workflow complete and live-verified;
- timing pulley.

### Phase 2 — belt routes and static bodies

- common pitch route;
- V/poly-V/flat/timing bodies;
- idler/tensioner support;
- timing-tooth closure.

### Phase 3 — cylindrical gears

- involute/cutter kernel;
- profile-shift synthesis;
- external pair;
- internal/rack;
- helical/herringbone.

### Phase 4 — placement and synthesis

- pair phase/placement;
- planetary synthesis;
- reducer layout;
- inspection dimensions.

### Phase 5 — bevel/hypoid

- straight;
- circular;
- tangential;
- internal;
- hypoid;
- crown/face.

### Phase 6 — worm families

- cylindrical;
- globoid;
- racks;
- generated wheel geometry.

### Phase 7 — validated rating

Only after the geometry kernel and comparison corpus are stable.

### Phase 8 — chains

Only after an explicit assembly/single-part architecture decision.

## 15. Acceptance policy

Every family must provide:

- normalized preview;
- explicit build plan and owned references;
- preflight and collision/interference checks;
- deterministic variable names;
- one functional member without duplicated hub/bore logic;
- body/topology/formula readback;
- hidden auxiliary verification;
- save and reopen evidence;
- catalog provenance;
- comparison against analytical points and at least one trusted external oracle.

No module is promoted from concept to experimental runtime solely because a
visually plausible solid was created.
