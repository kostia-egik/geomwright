# Geomwright

[English guides](docs/en/README.md) · [Русская документация](docs/ru/README.md)

Local-first CAD automation for KOMPAS-3D, exposed as an MCP server and a small
browser-based Studio. Geomwright lets an AI agent or a local operator inspect a
model, plan a change, execute a bounded operation, and verify the result without
turning KOMPAS into an uncontrolled scripting target.

> Geomwright is an independent project. It is not affiliated with or endorsed
> by ASCON or the KOMPAS-3D product team.

## What you can do

- inspect KOMPAS documents, model trees, sketches, features, dimensions, and
  constraints;
- create and edit selected sketch and feature entities with explicit targets;
- inspect and measure [finished bodies and face shapes](docs/finished-geometry.md),
  including user-built parts and assembly components, independently of construction history;
- preview and build supported parametric parts and spring families;
- preview and build managed V-belt, Poly-V, flat-belt, timing-belt, selected
  roller/bush-chain transmission geometry, an external cylindrical gear
  (spur or helical) with a nominal rack-generated profile, and an internal
  ring gear with an explicit blank outside diameter, and a straight bevel wheel
  with a nominal Tredgold profile;
- preview and build straight-sided spline shafts and hubs per ГОСТ 1139-80
  with the standard size catalog, centering methods, and ГОСТ 25346 fits;
- create specifications, relink assembly paths, run quality checks, and export
  safe working copies;
- use Geomwright Studio to preview transmission geometry and edit recognized
  managed blocks, or calculate and build one create-only cam without shaft/hub/bore.
  Cam recipes persist in new models: restore a Studio form for a new build or read
  the recipe through MCP `inspect_cam`; engineering limits do not inherit CAD slack.

The public MCP surface is discovered at runtime. Call `get_mcp_tool_catalog`
from an MCP client instead of relying on an unversioned list copied into a
prompt.

## CAD work modes

CAD defaults to `interactive`: attach to a selected visible KOMPAS window, retain
documents, and never create a substitute instance. `hidden` is an explicit
alternative that requires a separately created, proven-owned process; it must not
hide documents inside the user's session. Mode changes and window rebinding are
explicit and cannot bypass quarantine. See [mode selection and visibility](docs/low-level-runtime.md#cad-work-modes)
for the operational contract and live-verification limits. Visible API work does
not guarantee animation of every sketch edit.

## Current status

Version `0.1.0` is an alpha release. The core session, document, composition,
specification, relinking, and batch operations are the most stable parts. The
parametric, spring, sketch-write, and transmission families are usable only
within the scope stated by their contracts and live verification evidence.

| Area | Status | Notes |
| --- | --- | --- |
| Session and document lifecycle | Stable | Open, inspect, save, export, and close explicit documents |
| Composition, specifications, relinking, quality | Stable | Preview/apply workflows with bounded changes |
| Sketch and feature runtime | Experimental | Low-level tools; inspect before writing |
| Finished model geometry | Experimental, live-verified | Read-only bodies, faces, edges, shape snapshots and explicit geometry measurements |
| Parametric parts and springs | Experimental | Family-specific parameters and verification |
| Geomwright Studio | Experimental | Local UI; no arbitrary-body write path |
| Cylindrical gear | Experimental, live-verified | External spur/helical gear; ГОСТ 13755-2015, ГОСТ 9587-81, ГОСТ Р 50531-93 and ISO 53:1998 contours; nominal preview, create-only managed part, MCP tools |
| Internal gear | Experimental, live-verified | Internal spur/helical ring gear; explicit blank outside diameter, ГОСТ 19274-73 nominal geometry, create-only managed part, MCP tools |
| Straight bevel gear | Experimental | Nominal Tredgold projection, create-only dish blank and saved recipe; see the family contract for recorded live cases and limits |
| Straight-sided splines | Experimental, live-verified | ГОСТ 1139-80 light/medium/heavy catalog, exact end profile and ГОСТ 25346 fits; create-only managed shaft and hub parts, Studio modules and MCP tools |
| Cam profiles | Experimental | Shared Studio/MCP create-only build, native curve/contact and solid readback |
| Silent-chain sprockets | Experimental, live-verified | Shared Studio/MCP calculation and new-part creation; solid blank, DIN NURBS, saved recipe inspection |
| Native KOMPAS module inspection | Research-only | Disabled by default; explicit opt-in for local investigation |

An experimental status is a contract boundary, not a promise that every catalog
entry or CAD combination is supported. Missing standard data and failed
verification stop the operation before an unsafe write where possible.

## Requirements

- Windows;
- KOMPAS-3D v23 with its runtime components installed;
- Python 3.11 or newer for the host;
- an MCP-capable client for the agent interface.

The host Python and the KOMPAS bridge can use separate interpreters. The bridge
needs a modern Windows Python with `pywin32`; the old bundled Python 3.2 cannot
run the current source. Prefer a standard Python installation for the CAD runtime.

## Install

From PowerShell in a clone:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui]"
```

Configure the CAD interpreter before starting Studio or MCP. If the project
interpreter is a standard Windows Python, it can run both host and bridge:

```powershell
.\.venv\Scripts\python.exe -m pip install pywin32
$env:KOMPAS_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
$env:KOMPAS_REQUIRE_VISIBLE = "1"
```

Alternatively point `KOMPAS_PYTHON` at a separate Python with `pywin32` installed.
Without an explicit setting, a source checkout prefers its existing
`.venv/cad-bridge/Scripts/python.exe`; installed packages still need a compatible
runtime configured explicitly if the KOMPAS SDK fallback is too old. Studio does
not inherit environment settings stored only in an MCP client's configuration.
Production bridge calls first compile the selected sources and check `pywin32`
in a bounded, COM-free preflight. `CAD_RUNTIME_INVALID` identifies a local setup
failure before CAD launch; it does not by itself quarantine the session.
Use an actual interpreter path rather than a bare execution alias.
`KOMPAS_REQUIRE_VISIBLE=1` makes
MCP attach to the already running visible KOMPAS instead of starting a COM server.
Cam creation requires this running session. For an MCP client, put these variables
in the local server's `environment` configuration so a restart preserves them.

The UI dependency group is optional. For MCP-only use:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

The package currently requires `mcp>=1.27,<2`. Installing the package resolves
this dependency; do not substitute MCP 2.x without a compatibility migration.
For setup checks and common failures, see [English](docs/en/setup.md) /
[Русский](docs/ru/setup.md).

Research-only native-module tools are intentionally absent from the default MCP
session. Enable them only in a disposable local investigation:

```powershell
$env:GEOMWRIGHT_ENABLE_RESEARCH_TOOLS = "1"
.\.venv\Scripts\python.exe -m geomwright
```

They are not covered by the stable product contract and can inspect installed
KOMPAS modules or launch explicitly requested commands.

## Run Studio

The easiest Windows path is:

```powershell
.\start-geomwright-studio.cmd
```

Or run it in a terminal you control (foreground; keep that terminal open):

```powershell
.\.venv\Scripts\python.exe -m geomwright.studio --port 8765
```

For an agent or an unattended session, use the bounded background launcher:

```powershell
.\.venv\Scripts\python.exe -m geomwright.studio --background --no-browser --startup-timeout 15
```

It launches without a console window, closes stdin, redirects output to unique
log files, checks the new instance's `/health`, and returns its URL and PIDs.
Logs default to local Geomwright state (`%LOCALAPPDATA%\Geomwright\studio` on
Windows); override with `--log-dir`. Startup failure reports the stderr path
and stops only the newly launched process tree. Do not use PowerShell
`Start-Process` to launch Studio through an agent terminal tool.

For potentially blocking **finite** commands, use the independent watchdog:

```powershell
.\.venv\Scripts\python.exe scripts/run_bounded.py --timeout 30 -- .\.venv\Scripts\python.exe -m pytest tests/test_bridge_runner.py -q
```

The watchdog returns exit code `124` on timeout, closes stdin, captures bounded
output through files, and stops owned descendants. On Windows it uses a Job
Object plus cleanup of the launcher tree; it does not rely on the terminal tool's
timeout message. Never wrap Studio `--background` or another persistent server
in this watchdog: it cleans descendants even when the command finishes normally.

Studio opens `http://127.0.0.1:8765` unless `--no-browser` is supplied. Start
KOMPAS first and keep it visible: Studio attaches to the already running
KOMPAS instance and never creates a hidden substitute session. It previews
geometry before a CAD job and only edits recognized managed blocks.

## Run the MCP server

```powershell
.\.venv\Scripts\python.exe -m geomwright
```

For an MCP client, use the Python executable inside that clone. The tracked
[`opencode.example.json`](opencode.example.json) shows the portable shape:

```json
{
  "mcp": {
    "geomwright": {
      "type": "local",
      "command": [
        "C:\\path\\to\\geomwright\\.venv\\Scripts\\python.exe",
        "-m",
        "geomwright"
      ],
      "enabled": true,
      "environment": {
        "KOMPAS_PYTHON": "C:\\path\\to\\geomwright\\.venv\\Scripts\\python.exe",
        "KOMPAS_REQUIRE_VISIBLE": "1"
      },
      "timeout": 600000
    }
  }
}
```

Do not commit a machine-specific copy of this file. The legacy commands
`kompas-mcp` and `kompas-mechanics-ui`, and the `kompas_mcp` import namespace,
remain as compatibility aliases. New integrations should use `geomwright` and
`geomwright.kompas`.

## CAD module pilot: MCP and CLI

The shared contract exposes `gear_spur` (external cylindrical), `gear_internal`
(internal cylindrical), `gear_bevel` (straight bevel), `chain_sprocket`
(roller/bush chain sprocket), `cam` (direct or roller-rocker cam lobe) and
`silent_chain_sprocket` (GOST and DIN/ASME open reconstructions), plus the five
managed pulley families: `v_belt`, `poly_v`, `flat_belt`, `timing_trapezoidal`,
`timing_curvilinear`. In MCP, call
`get_cad_module_contract()` (or `module_id: null`) to list descriptors;
`get_cad_module_contract(module_id="gear_spur")` returns the input/result
schemas, defaults, examples, units/frame and limitations. Use the existing
`list_gear_standards` tool to select rack standards and modifications. For
sprockets, use `list_chain_profiles`; the catalog is not repeated in module results.
Restart the MCP client after upgrading so a fresh session discovers
`get_cad_module_contract` and `run_cad_module`.

The CLI uses the same dispatcher without an MCP server:

```powershell
python -m geomwright.model list
python -m geomwright.model describe gear_spur
python -m geomwright.model run request.json
```

The installed `geomwright-model` command accepts the same arguments;
`run -` reads a JSON request from stdin. Stdout is JSON. Exit codes are
`0` for success, `1` for operation failure, and `2` for an invalid file/envelope.
CAD actions still require the normal KOMPAS environment.

Example `request.json` (also the `request` argument of `run_cad_module`):

```json
{
  "contract_version": 1,
  "module_id": "gear_spur",
  "action": "preview",
  "parameters": {"module_mm": 2, "tooth_count": 24, "face_width_mm": 20}
}
```

For a two-row sprocket, use `module_id: "chain_sprocket"` with parameters such as
`{"designation":"ISO_08B_2","chain_type":"roller","tooth_count":25,"row_count":2}`.
The row count must match a multi-row designation, and the selected catalog entry
must contain the required axial data. Tooth width is catalog-derived, not a free
`face_width_mm` field. `gost_profile_variant` selects `offset` or `non_offset`
construction for both ISO and GOST chains.

For `cam`, `parameters` contains the typed calculation `request`, plus `width`,
`rotation_deg` and `tolerance`, matching the existing `create_cam` inputs.
Preview/plan use the same strict CAD preflight at 10 samples per cam degree and
omit curve and motion-chart arrays. There is no standard catalog for this engineering
module. See the [cam contract](docs/en/camshaft.md#shared-module-interface).

`silent_chain_sprocket` reuses its existing selection schema and
`list_silent_chain_profiles` catalog. Its designation and physical tooth count are
required, so discovery defaults are partial, not a complete request. Preview returns
`data.summary.completion`; plan/create return `error.code: "INPUT_REQUIRED"` with
`data.completion` until required engineering inputs are supplied explicitly.
Suggestions are not silently accepted. Source/reconstruction warnings are retained
in plan/create and inspection (`data.source_summary`). The rim occupies positive
global X, `[0, functional_width_mm]`, unlike the gear/cam negative-X interval.
Inspection has `verification.stored_verified: null`, not a persisted geometry stamp.

Pulley inputs reuse the existing family schemas. `v_belt` additionally accepts
`top_edge_fillet_radius` and `include_standard_top_edge_fillet` in `parameters`.
Use `list_v_belt_profiles` or `list_poly_v_profiles` for selection; timing profile
choices are in the schema, and custom dimensions require `designation: "CUSTOM"`.
Poly-V currently supports catalog geometry only. Flat crown height is explicit
circular-arc geometry, not a standards-derived default.
V/Poly-V/flat rims occupy positive X; timing pulleys occupy `[-face_width, 0]`.
Create verifies one positive-volume solid, bounds and ownership; timing creation
also compares repeated removed material with source-cut volume times tooth count.
New pulley creation stores a versioned checksummed full recipe, including finishing
and custom-source inputs. Inspect returns that **creation recipe**, not a geometry
audit; detected driving-input changes invalidate it. Old blocks lacking a full
recipe remain recognizable with `parameters: null`. Existing dedicated apply and
Studio editing paths remain separate from this create-only interface.

`module_id` and `action` are required; actions are `preview`, `plan`, `create`
and `inspect`. Defaults: `contract_version: 1`, `parameters: {}`,
`name: null`, `confirm_write: false`, `visible: true`; an omitted/null name uses
the selected module's `default_name` (unchanged for `gear_spur`).
`document_id` is optional except for `inspect`, which requires the explicit
exact opened document ID. `parameters` is validated by the selected family's schema;
runtime flags belong in the envelope, never inside `parameters`.

`create` requires `confirm_write: true`. Check descriptor `creation_policy`:
most modules create a new unsaved part; legacy compression springs retain their
saved construction/finalization path described below.
`inspect` recognizes the saved recipe; it is **not a fresh geometry audit**.
To recreate, require `data.recreatable: true`, then pass its returned parameters
to a new `create` request. Without a recoverable recipe, `parameters` is `null`;
do not substitute `{}`, which would select a default part.
For bevel gears, face width is along the pitch cone; axial extents come from
the plan/readback, not `[-face_width_mm, 0]`. The module contract describes this frame.
There is no `update`/`apply`, general composition or new Studio block in this pilot.

The bounded result contains `contract_version`, `module_id`, `action`, `ok`,
`stage`, `executed`, `verified`, `parameters`, `data`, `verification`, `error`
and `partial_result`. `executed` is `false`/`true`, or `null` when execution is
unknown after runtime failure. `verified` is `false` for preview/plan/inspect;
create reports `true` only after actual verification. See the
[gear contract](docs/gear-spur.md#shared-contract-usage--общий-контракт).
`data.geometry` contains calculated geometry; `data.body` contains actual CAD
readback. `data.owned_references` identifies the recognized root operations.
For sprocket inspection, `verification.stored_verified` is `null`: the saved
block has no geometry-verification stamp. Creation includes the existing
transition-constraint check in `verification.transition_constraint`, including
any solver-state warning that requires UI confirmation.

### Legacy compression-spring integration (experimental)

`compression_spring` adds a typed interface over the existing cylinder, two-zone
variable-pitch and conical generators (`variant: cylindrical|two_zone|conical`).
Use `get_cad_module_contract("compression_spring")` for the schema and restrictions;
wire diameter and geometry are explicit, not defaulted. Exactly one cylinder
diameter representation is accepted; cones use small/large mean diameters.
The old `create_compression_spring`, scenario and catalog tools remain available.
Arbitrary legacy placement/workflow expressions are not part of the new schema.

Unlike the recent rim modules, `creation_policy: saved_unique_export_then_open`
creates a unique `.m3d` in `KOMPAS_EXPORT_DIR`, runs the established post-save anchor
binding, and opens the saved result. The response has `saved: true`, `closed: false`
and its exact path in `data.document`. This is not an unsaved-create promise.
Checks cover native rebuild, positive single-solid volume, radial envelope,
owned profile/sweep roots and volume preservation through saving/finalization.
The axis is global X. Inputs and bounds survive a further reopen.
`CSPR_RECIPE_*` stores a versioned checksummed creation recipe, not driving formulas
or a geometry-verification stamp. Inspect does not certify manual edits.

Live control cases cover an open cylinder, grounded right/left two-zone cylinders
(including left-hand start phase30), and cones with constant pitch/constant angle.
The left-hand segment phase mismatch is fixed; both native fillets now return
their edges. `end_pitch_gap` defaults to0.01 mm in the shared module: end pitch is
wire diameter plus this axial increment, without reducing the wire diameter.
`EG1` drives derived `EP1`; end spans, grinding planes and length formulas use it.
Legacy calls without this field and earlier recipes retain zero gap. Explicit
zero is not clamped: invalid contact returns `CAD_SELF_INTERSECTION` before saving,
even with a positive cached volume. The increment is not a certified minimum
surface clearance. Both hands and asymmetric ends pass save/reopen; changing
`EG1` to0.02 retains native validity and wire diameter. `height` and legacy
`free_length` mean centreline span; `standard_length` means the legacy physical
end-to-end length. These length inputs are mutually exclusive. No new Studio
spring editor is added; this is a shared-generator integration, not a complete
three-component Studio module.

`extension_spring` now connects the existing eight engineering hook
forms to the same shared interface. It requires wire/outer diameter and turns;
`gap >= minimum_gap > 0` is explicit and never silently increased. Creation uses
a unique saved export, verifies the native coil and valid solid, and restores
the `ESPR_RECIPE_*` inputs after reopening. Independent `left_hook_type` and
`right_hook_type` include the finalized self-wrapping and bent-ring families;
historical `spike` names are retained. Current runtime verification limits are
explicit in the family contract. No new Studio block is added. See the
[extension-spring contract](docs/extension-spring.md).

`torsion_spring` likewise exposes the existing tangent, radial and axial-transition
leg generator through the common interface. It retains separate `TSPR_RECIPE_*`
inputs and verifies native coil/leg geometry and save/reopen. Existing legacy
tools are unchanged; no new Studio block or torque/strength certification is
added. See the [torsion-spring contract](docs/torsion-spring.md).

`disc_spring` connects the legacy normal-thickness conical-ring generator to the
same create-only interface, with `DSPR_RECIPE_*`, native diameter/bounds checks,
analytical volume comparison and save/reopen verification. Legacy radius/height
variable edits are not reliably driving; recreate from inputs instead. The
`free_height` alias is not the finished axial span. See the
[disc-spring contract](docs/disc-spring.md).

`diaphragm_spring` reuses the finalized flat/single/S-bend workflow with radial
slots, circle/oval reliefs and a two-source circular pattern. The common interface
checks repeated material removal, owned roots and recipe/volume persistence using
`DIAPR_RECIPE_*`. Per-sketch constraint states are returned after reopening;
complete saved-sketch definition and in-place driving edits are not certified.
See the [diaphragm-spring contract](docs/diaphragm-spring.md).

`stepped_shaft` connects the existing full rotational-body constructor, with
per-step native radius/axial-span checks, analytical volume, a fully defined
creation profile and saved `SHFT_RECIPE_*`. It is create-only and contains no
operations on an external body. See the [stepped-shaft contract](docs/stepped-shaft.md).
The separate construction-chain interface supports explicit axial-bore, face-groove
and bolt-circle cuts on supported chain carriers, plus terminal external metric
threads on a complete exposed +X cylinder. Arbitrary external-body processing and
broader thread modes remain deferred; see the [chain contract](docs/en/construction-chains.md).

`external_conical_step` adds the existing standalone frustum with five explicit
definition modes. Native verification checks both trimmed end radii, axial bounds,
analytical volume and the fully defined reopened profile. The original input mode
is restored from `ECON_RECIPE_*`; resolved diameter/length variables drive CAD.
See the [external-cone contract](docs/external-cone.md).

## Construction chains and model images

`get_construction_chain_contract` discovers the current MCP-only composition
contract. `run_construction_chain` supports `plan|create|inspect|rebuild|continue`:
create/rebuild make a new saved part; inspect recognizes its recipe, not fresh
geometry. Continue requires the exact opened saved chain ID, `confirm_write=true`
and only new steps, audits the immutable prefix/current geometry, then saves the
same file. Old-step edits and arbitrary standalone models are refused.

Stages A–C (shaft/cone/bore/groove) and D (initial `gear_spur`, cylindrical hub,
continuous bore and saved-chain continuation) are live-verified within the
documented limits. Stage E now includes regular polygon sections (`own/create`
and `own/add`), one/two-flat sections with an inscribed-core carrier, and explicit
`input/remove` bolt-circle holes. Actual planes/cylinders, pattern roots and
saved-chain continuation are verified. An initial `straight_spline` shaft now reuses
the GOST 1139-80 numeric family plan, with +X cylindrical continuation, core cuts,
native tooth-zone preservation and same-file continue/reopen checks. Terminal
`input/remove` splines on an explicit uncut +X cylinder now support bounded working
length with smooth margins at both ends, without chamfers/runout; create, continue,
fresh inspect/reopen and source-preserving rebuild are live-verified. Terminal metric
threads are also available within their documented limits. Terminal `body=hub`
splines now cut the entire explicit through bore of one cylindrical stock, using
the corrected nominal counterpart profile and inherited outside diameter;
create/continue/inspect/rebuild/reopen are verified. Explicit `exit_mode=blind`
also supports a shorter cut from open entry in a flat-bottom bore, with positive
smooth tail and stock behind the bottom; lifecycle and native length20→22→20
checks passed. Arbitrary partial spans, tool runout, broader input-stock processing
and chain Studio integration remain pending. See
[English examples and limits](docs/en/construction-chains.md) /
[русские примеры и ограничения](docs/ru/construction-chains.md).

For visual review, use `export_model_png` with an exact open `document_id`, optional
new `output_path`, `view` (default `current`), `resolution_dpi=150` and `fit=true`.
For example: `{"document_id":"<exact open ID>","view":"left"}`. Native views
follow KOMPAS orientation; `left` may be a side view for global-X parts. Export
writes an actual PNG without rebuilding/editing geometry, restores and checks
matrix/scale and previous active document, but does not certify exact screen pan.
Existing files are never overwritten; omitted paths get UUID filenames. See
[PNG export and supported views](docs/low-level-runtime.md#model-png-export).

## First safe workflow

1. Call `get_mcp_tool_catalog` and choose a category whose status matches the
   task.
2. Call `get_session_state` and `list_documents`; always name the target
   document explicitly.
3. Use inspection, preview, and preflight tools before a write.
4. Follow **Plan → Execute → Verify → Correct**. A successful COM `Update()` is
   not, by itself, proof that geometry or direction is correct.
5. Save and reopen a model when the workflow contract requires persistence
   evidence. Keep generated files under ignored local output directories.

For sketch work, begin with `inspect_sketch_full`. For a parametric family,
begin with its preview operation and then read the family contract in `docs/`.

## Repository map

```text
src/geomwright/                 public application namespace and Studio
src/kompas_mcp/                 KOMPAS implementation and compatibility APIs
bridge/kompas_bridge.py         KOMPAS-side COM bridge
rules/                          tracked runtime rule data
docs/                           current user and maintainer contracts
sample/                         small runnable examples and request payloads
tests/                          deterministic host-side and contract tests
experiments/spikes/              ignored local quarantine for unfinished work
```

The root bridge and packaged bridge copy must remain byte-identical. Generated
CAD files, live readback dumps, local configuration, and disposable probes are
not part of the public repository.

## Documentation

- [Documentation index](docs/README.md) — choose a guide by task and audience;
- [Camshaft calculation and CAD](docs/en/camshaft.md) / [Кулачки ГРМ](docs/ru/camshaft.md) —
  timing conventions, strict CAD checks, recipe reuse, recovery, and reference data;
- [Write operations and safety](docs/write_operations.md) — mutation rules;
- [Geomwright Studio](docs/geomwright-studio.md) — UI workflow and HTTP contract;
- [Parametric workflows](docs/parametric-workflows.md) — supported part families;
- Construction chains: [English](docs/en/construction-chains.md) /
  [Русский](docs/ru/construction-chains.md) — implemented A–D limits and Stage E roadmap;
- [Model PNG export](docs/low-level-runtime.md#model-png-export) — native raster review
  with temporary standard views and checked restoration;
- [Spring workflows](docs/spring-workflows.md) — spring-family navigation;
- [Transmission contracts](docs/transmission-platform-concept.md) — pulley,
  sprocket, and gear boundaries;
- [Cylindrical gear](docs/gear-spur.md) — inputs, rack standards, pin rows,
  nominal representation, create-only CAD, and live evidence;
- [Internal gear](docs/gear-internal.md) — ring blank input, ГОСТ 19274-73
  geometry, controls, create-only CAD, and live evidence;
- [Straight bevel gear](docs/gear-bevel.md) — nominal projection, dish blank,
  create-only CAD and recipe; [English guide](docs/en/gear-bevel.md) /
  [русское руководство](docs/ru/gear-bevel.md);
- [Architecture](ARCHITECTURE.md) — layer ownership for maintainers;
- Module development rules: [English](docs/en/module-development.md) /
  [Русский](docs/ru/module-development.md) — design and completion criteria;
- [CAD patterns](CAD_PATTERNS.md) — verified KOMPAS-specific invariants.

## License

Geomwright is released under the [MIT License](LICENSE).

See [CONTRIBUTING.md](CONTRIBUTING.md) for development boundaries and
[SECURITY.md](SECURITY.md) for safe local operation and vulnerability reports.
