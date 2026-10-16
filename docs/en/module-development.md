# CAD module development rules

[Русский](../ru/module-development.md) · [English index](README.md) · [Development](development.md)

Read these rules before creating a new complete Geomwright CAD module or
substantially extending an existing one. They define functional boundaries,
module components, and completion criteria. References to specific families below
are examples of applying the rules, not an exhaustive list of capabilities.

These rules govern new work. Existing family contracts still define current
capabilities; this document does not add parametrization, custom inputs, or
editing support to existing modules.

## 1. Define the function first

Before implementation, record a brief contract: purpose, variants, minimal output,
independent inputs, excluded functions, behavior after input changes, and
verification criteria. Assign calculation, CAD planning, execution, and interfaces
to owners using the [architecture](../../ARCHITECTURE.md) layers. The work description
can hold this note; each stage does not need a separate file.

Include only parameters and operations required to create the functional element.
Other modules supply general construction features. Boundaries must allow a part
to be built from successive blocks without duplicating functions. Do not split
shared calculations into tiny modules without distinct responsibilities.

**Example:** an external gear module creates the body carrying its toothed rim.
Mounting bores, hubs, splines, and shafts belong to other modules.

The minimal body follows its function, not a universal solid-blank requirement.
Functionally necessary cavities, end shapes, and fillets belong in the module
with an explicit purpose. Do not add general finishing merely for convenience.

**Example:** the internal cavity of a ring gear is necessary for internal meshing;
it is not a separate mounting bore.

## 2. Deliver three coordinated components

A complete module includes:

- a Studio user block;
- shared calculation, validation, CAD planning, and KOMPAS model generation;
- an MCP interface that uses the generator independently of Studio.

Studio and MCP normalize inputs into one contract and use the same formulas,
limits, and CAD plan. MCP works without a running Studio and does not import its
presentation code. Studio works without an AI agent. Preview and preflight do not
require COM unless they need to read an existing model.

A shared host-side owner holds calculation logic. Studio owns presentation and
interaction; MCP owns the public schema and calls shared logic. COM follows the
existing CAD boundary. Reuse suitable project data types and mechanisms; new
layers or infrastructure require a concrete reason.

MCP exposes the necessary parameter selection/description, preview or preflight,
creation, and result inspection. Claimed editing capabilities must also be
available independently of Studio. Each step need not have a separate tool if
an existing public contract already covers it.

A standalone preview or generator may be an intermediate deliverable, but must
not be presented as a complete module.

The agreed [construction-chain plan](construction-chains.md) starts with MCP-only
integration. Studio support is deferred for that stage; this does not relax the
completion criteria above or imply that existing modules are chain-ready.

## 3. Separate engineering and standards-based inputs

An engineering module accepts freely specified independent inputs and validates
them. Do not invent a standard selector for an engineering method.

A standards-based module must provide both:

- selection of standard parameters;
- custom dimensions for an equivalent functional element.

Custom mode exposes every independent input required for the nonstandard
equivalent within the supported geometric method. Adjusting one coefficient is
insufficient if other necessary dimensions remain inaccessible. Arbitrary geometry
outside the method is not required.

Both routes use shared calculations, CAD planning, and validation. Custom values
must not be designated as compliant with the standard. The recipe retains the mode.

## 4. Control normative data and fields

In standard mode, all available discrete normative values come from selection
lists. Dependent lists contain compatible options only. Values determined by a
selected row or normative formula are calculated and displayed without unrestricted
editing.

Free entry is used for inputs not standardized by the selected standard and for
custom mode. Editing a normative value must visibly switch the form into a custom
state. Shared validation enforces these rules as well as the Studio form.

Retain the source, edition, and applicability of normative data. Do not implicitly
mix standard systems. A shared catalog owns tables and admissible options; do not
maintain separate copies in Studio, MCP, and documentation.

Incomplete sources do not prohibit a module: a **reconstruction based on a standard**
is allowed. Clearly separate supported information from reconstructed dimensions,
formulas, and assumptions. State sources, gaps, and applicability limits. A missing
dimension needs an explainable reconstruction method or explicit user input;
arbitrary hidden substitution is prohibited. Reject variants that cannot be built.

The “reconstruction” label is required during selection, in Studio previews and
results, in MCP descriptions and responses, in saved recipes, and in the family
contract. It remains visible after model restoration. A normative designation may
identify the source, but must not imply a complete authoritative implementation or
full compliance. CAD geometry verification does not establish reconstruction fidelity.

Changing a standard or restoring a recipe requires explicit correction of invalid
values. Silent substitution of the nearest available value is prohibited.

## 5. Group related variants

Group variants in one Studio block where they serve the same user task and share
similar mechanics. Separate CAD execution paths within the block are allowed.

**Example:** spur and helical cylindrical gears can be selected in one block even
when their CAD plans use different operations.

Separate user modules require a meaningful difference in purpose, geometric method,
or substantially incompatible inputs. A shared interface does not justify mixing
normative tables or building a universal generator for unrelated families. Fields
for an inapplicable variant must not obstruct the user.

## 6. Describe the contract for subsequent construction

Specify units, coordinate frame, construction axis and direction, independent and
derived inputs, ranges, and method limitations.

Return the document identifier, references to created root operations and geometry,
functional extents, verification status, and necessary diagnostics. Describe
orientation and available attachment interfaces so subsequent modules can continue
without guessing. Reuse existing references and selectors; do not introduce a
separate identity system for one module.

Block identity must not rely solely on display names or the last position in the
model tree. Follow canonical operation names and dependency ordering from
[CAD patterns](../../CAD_PATTERNS.md) (`OP-003`).

New-document creation, existing-body application, and owned-branch editing are
distinct capabilities. Declare and verify each separately. Future block composition
must not be presented as an implemented capability.

## 7. Make technical previews faithful

Use the smallest sufficient set of views to explain overall dimensions and the
body's principal characteristics. Start from the standard or generally accepted
technical representation. Add views, enlarged details, or schematics when they
provide useful information. Simplification must preserve geometric meaning.

Required conventions:

- distinguish views, sections, and schematics; hatch sectioned material;
- show real contours, axes, characteristic dimensions, and directions;
- distinguish construction geometry from body boundaries;
- mark breaks so they cannot be mistaken for physical surfaces;
- do not introduce fictitious closing contours;
- show the whole body's extents, including projecting portions;
- use calculation geometry shared with the generator and label illustrative layouts.

Display and CAD discretization accuracy may differ; the engineering model remains
shared. An approximation tolerance must not relax engineering limits.

**Example:** an axial sector view, axial section, and enlarged tooth-end view can
complement a bevel-gear preview. The end view is not a section; wavy breaks are not
part edges. Three views are not mandatory for other families: choose the count
according to the information needed.

Invalid inputs disable creation and visibly mark previous previews as stale.
Inspect the rendered result for readable dimensions, overlaps, alignment, spacing,
narrow layouts, warnings, and recovery from invalid inputs. A successful UI build
does not replace viewing the image.

## 8. Parametrize everything that is rational to parametrize

Parametrize every dimension, relationship, and operation where complexity, rebuild
reliability, and maintenance cost make it reasonable. Assess each part separately:
a complex numeric profile does not exempt the rest of the model from parametrization.

**Example:** even with a numerically calculated tooth profile, assess blank width,
simple dimensions, and pattern parameters separately for parametrization. This
example establishes a development principle, not a claim about current family support.

Full sketch definition and parametrization are distinct requirements: fixing
numeric geometry does not create editable driving relationships. Parameterized
operational sketches must be fully defined. A numeric sketch that cannot reasonably
be parameterized or fully defined may have a justified local exception; that
exception does not justify unconstrained simple geometry.

Identify the specific sketch or operation, reason for the exception, editing limits,
and alternative verification in the contract. Require actual geometry readback,
direction checks, rebuild, and save/reopen stability. Do not exempt an entire
family merely because of its name.

Explicitly distinguish generator inputs, actual CAD driving dimensions/variables,
calculated values, and metadata. A saved recipe is not parametrization. Verify
driving relationships through expression readback, parameter changes, and rebuild
checks. Do not add decorative variables without a construction role.

Declare whether changed inputs rebuild existing operations, replace an owned branch,
or create a new model. Partial parametrization does not mean all engineering inputs
can be edited without recreation.

Studio creation finishes only after the new block is recognized (`SESSION-003`).
New complete modules retain a versioned recipe and sufficient data to restore
original inputs after saving and reopening. Restoring a form for a new build must
not be described as editing the existing model.

## 9. Verify execution and failure state

Shared validation and geometric preflight run before writes. Invalid inputs do not
initiate construction. Do not relax engineering limits to obtain a body.

Use Plan → Execute → Verify → Correct and the existing
[write-operation rules](../write_operations.md). Bound CAD calls by time
(`SESSION-002`). Errors identify the stopping stage, target document, and state of
any partially created model. Cancellation must not be described as rollback.
Owned-branch changes must not damage non-owned downstream operations.

Confirm success through geometry and operation state: expected body count, extents,
direction, control dimensions, positive volume where applicable, and material
addition/removal. An operation's presence in the tree is insufficient. Verify
Studio block recognition separately.

Verify standard and custom routes, materially different variants, valid parameter
boundaries, invalid inputs, saving, and reopening. Test claimed editing capabilities
separately. For reconstructions, also check that labels and assumptions survive
across all interfaces.

Focused host tests protect important formulas, schemas, normalization, topology,
and error propagation. Live CAD and readback verify COM behavior; host tests must
not access live KOMPAS. Follow the [development rules](development.md), including
bridge-copy parity and packaging checks when shipped assets change.

Document API workarounds for the specific case; they do not authorize generally
skipping verification. Prefer informative checks over broad combinatorial matrices
or repeated complete model reads.

## 10. Documentation and completion criteria

The family contract explains purpose, input modes, minimal outputs, method limits,
normative provenance or reconstruction, behavior after input changes, and significant
failures. Label all references to particular modules used to illustrate rules as
“Example”. Actual supported-capability inventories in family contracts remain factual
inventories.

ENG and RU follow the same semantic structure and are updated together. Parameter
tables come from their data owner without independent manual duplication. These
rules own new-module completion criteria; [architecture](../../ARCHITECTURE.md)
owns layers, [CAD patterns](../../CAD_PATTERNS.md) owns CAD techniques, and
[CONTRIBUTING](../../CONTRIBUTING.md) owns general development policy.

A module is complete when:

- [ ] Studio, the shared generator, and independent MCP use one contract;
- [ ] the required standard and custom routes are implemented;
- [ ] the functional-body boundary is respected and related variants are grouped with reason;
- [ ] data provenance and reconstructions are explicitly labeled and retained;
- [ ] the preview is faithful and visually checked;
- [ ] everything rationally parameterizable is parameterized; local exceptions are justified;
- [ ] creation is confirmed by CAD readback and block recognition;
- [ ] saving, restoration, and claimed editing behavior are verified;
- [ ] interfaces and documentation state limitations and unsupported variants;
- [ ] applicable focused checks and delivery-content checks have passed.

Unverified capabilities must not be marked as verified. Temporary investigations,
probe scripts, CAD files, and raw readback artifacts are excluded from delivery;
use the ignored `experiments/spikes/` area for unfinished work.
