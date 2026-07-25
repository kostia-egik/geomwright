# Native Spring Strategy

Status: research. Native inspection/launch is not a replacement for managed
spring workflows and requires explicit operator control.

Loader probes require `confirm_load=true` and reject DLL paths outside KOMPAS
installations under `Program Files/ASCON`. Static ABI inspection remains the
default because loading a DLL can execute its initialization code even when no
export is called.

This document is the working strategy for one narrow question:

How far should `kompas-mcp` go in trying to reuse the native KOMPAS Spring
module, and where should we stop and continue with our own geometry path?

The current answer is pragmatic:

- keep the supported KOMPAS automation surfaces as the main production path;
- keep native Spring work in the "research and evidence" lane until a stable
  non-interactive contract is proven;
- do not block the custom spring generator on reverse-engineering success.

## Current position

What is already true in the repository:

- the project already has a stable supported path for session, documents,
  sketches, readback, snapshots, and parametric geometry through the regular
  KOMPAS automation bridge;
- the project already has a read-only native-module dossier layer in
  `native_modules.py`:
  `list_native_modules`, `inspect_native_module`,
  `inspect_native_spring_workflow`,
  `probe_native_module_programmatic_access`,
  `inspect_native_entrypoint_static_abi`,
  `probe_native_entrypoint_loader`,
  `probe_native_entrypoint_loader_hosted`,
  `preview_native_module_launch`;
- the custom `compression_spring` path exists, but it is still only the first
  slice of the real spring scope: cylindrical compression spring only, partial
  end-style coverage, no catalogs, no other spring families.

What is still unproven:

- whether native Spring has a stable parameter API outside the interactive UI;
- whether Spring writes a stable job/session artifact that can be driven
  instead of the UI;
- whether the private DLL exports are useful enough to justify a production
  integration path.

## Channel map

These are the real interaction channels worth tracking.

| Channel | Status | Production value | Current conclusion |
| --- | --- | --- | --- |
| Automation API 7 / 3D COM | Supported and already used | High | Mainline path for `kompas-mcp` |
| Legacy Automation API 5 surfaces | Supported but legacy | Medium | Use only where API 7 is missing |
| Registered procedures libraries via library manager | Supported for discovery/launch | Medium | Good for command discovery and manual launch, not yet a parameter API |
| Native module manifest + DB inspection | Read-only and already implemented | High for research | Best source for command map, catalogs, and workflow hints |
| Private DLL export inspection | Research-only | Low to medium | Useful for evidence, not a default integration path |
| Interactive UI/manual module execution with result capture | Works as an audit path | Medium | Best way to learn side effects when live access is available |
| Offline `.m3d` `Contents` extraction and formula probes | Already useful | High | Keep using as a readback and reverse-engineering aid |

## Recommended strategy

### 1. Keep one strict rule

Until a stable external Spring contract is proven, native Spring stays in the
"assistive/oracle" role, not in the critical production path.

That means:

- production automation should continue to rely on supported COM and our own
  geometry modules;
- native Spring research may inform catalogs, parameter naming, validation
  ranges, and UX, but should not become a hard dependency;
- loader-level or export-level experiments must remain opt-in and clearly
  marked as exploratory.

### 2. Rank the Spring research tracks

Priority order should be:

1. static dossier and command mapping;
2. manual live workflow capture and result diffing;
3. search for stable job/session artifacts;
4. only then DLL/export-level probing.

This order matters because DLL probing is the most expensive path and the least
likely to become a clean production contract.

### 3. Define the decision gate early

Native Spring should be promoted only if at least one of these becomes true:

- a stable parameter file or job/session artifact is found and can be generated
  deterministically;
- the registered library surface exposes an actually usable non-interactive
  call contract;
- the private export path shows a repeatable, low-risk contract that can be
  wrapped safely.

If none of those happens, the correct decision is not "try harder forever".
The correct decision is to keep the research notes and continue the custom
spring engine.

## Research plan while live verification is unavailable

This is the useful work that does not require sitting in front of KOMPAS.

### Phase A. Freeze feature expansion

Do not add new spring families or large geometry modules right now.

Instead:

- cleanly separate "production path" from "research path";
- document the missing acceptance criteria for springs;
- prepare small audit scripts and runbooks for the next live session.

### Phase B. Build the native Spring dossier

Use the existing read-only probes to assemble one repeatable dossier:

- list installed libraries and resolve the Spring manifest;
- map Spring commands from the manifest;
- inspect Spring runtime files and databases;
- classify reference tables: standards, dimensions, materials, metadata,
  localized help;
- inspect static ABI evidence for candidate exports;
- keep all outputs as bounded JSON artifacts.

Expected outcome:

- one versioned artifact folder per audit run;
- one short summary saying whether Spring looks like:
  "interactive only",
  "artifact-driven candidate",
  or "private-export candidate".

### Phase C. Prepare the manual live audit path

Before touching more geometry, prepare the exact live runbook for the next time
manual verification is possible:

1. run the static dossier audit;
2. start native result probing for Spring;
3. launch the native Spring command interactively;
4. manually create one representative compression spring;
5. capture before/after result artifacts and document deltas;
6. probe the produced document with readback, formulas, and snapshots;
7. inspect whether any sidecar files changed outside the document itself.

Expected outcome:

- either we find a stable artifact or side effect worth automating;
- or we prove that the module remains UI-only and should not drive design.

### Phase D. Convert findings into a hard branch decision

After one or two good live audits, choose one branch:

- Branch 1: artifact-driven native integration.
  Use only if Spring writes a stable external contract.
- Branch 2: interactive-only helper.
  Keep only for manual operator assistance and result capture.
- Branch 3: abandon native automation path.
  Keep only the research dossier and continue the custom engine.

## Detailed live runbook for the next session

When live verification becomes possible again, run in this order.

### Step 1. Static audit

```powershell
$env:PYTHONPATH='src'
python sample\audit_native_spring_channels_2026_05_24.py
```

Use this to refresh:

- manifest commands;
- database inventory;
- programmatic-access evidence;
- launch preview;
- static ABI evidence.

### Step 2. Interactive launch preview

Use the existing MCP/native path only in preview mode first:

- `launch_native_module_command(module="Spring", allow_interactive=false)`

Confirm that the expected command id/title still resolves before any manual
run.

### Step 3. Manual result capture

Use the existing result probe path around one manual Spring build:

- `start_native_module_result_probe`
- interactive Spring launch
- `capture_native_module_result`
- `diff_native_module_results`

The goal is not to automate the build immediately. The goal is to learn what
the module actually mutates:

- active document only;
- external files;
- database rows;
- temporary job/session artifacts;
- hidden feature names or formulas.

For the filesystem side of that step, use a bounded before/after watcher and
store its raw output under ignored local evidence. The previous raw Spring-run
report was quarantined with other uncommitted research material and is not a
runtime contract.

### Step 4. Post-run document inspection

Immediately after the manual Spring run:

- capture a snapshot;
- run readback stability checks if reopening is involved;
- run `probe_model_formulas`;
- inspect tree/items/model-object collections.

This step matters because even if Spring has no public parameter API, the
resulting model may still expose a stable formula or feature fingerprint that
can help our own generator.

## Custom spring roadmap after the research gate

Regardless of what native Spring reveals, the custom engine should evolve in a
specific order.

### Stage 1. Finish the cylindrical compression spring properly

Close the remaining gaps before adding new families:

- normalize the contract for free length, body length, solid length, and active
  coils;
- complete end-style coverage and document exact semantics;
- make handedness, start phase, and support-segment behavior explicit;
- ensure preview exposes enough diagnostics to compare against native output.

Current spring-family work is indexed in
[`spring-workflows.md`](spring-workflows.md). Historical backlogs do not define
the active roadmap.

### Stage 2. Separate geometry from catalogs

Do not hard-wire catalogs into the geometry builder.

Create a clean split:

- geometric kernel;
- parameter normalization layer;
- catalog lookup layer;
- output comparison fixtures.

That separation will let us reuse the same kernel for both:

- exact manual parameters;
- standard-based preset generation.

### Stage 3. Add catalogs only after the geometry contract is stable

Catalog support should come after the cylindrical base is closed, not before.

First target:

- standard compression springs with deterministic parameter normalization.

Only after that:

- extension springs;
- torsion springs;
- special end forms;
- non-cylindrical variants.

## What not to do

Avoid these traps:

- do not spend long cycles trying to call private DLL exports before the
  artifact path is exhausted;
- do not bind the project architecture to native Spring unless the contract is
  reproducible without UI guessing;
- do not add many new spring families while the first one still lacks a fully
  locked parameter contract;
- do not treat manifest presence or export presence as proof of automatable
  behavior.

## Immediate repo tasks

These are the next practical tasks that fit the current constraint set.

1. Keep this strategy doc current as live evidence appears.
2. Use the new sample audit script to standardize native Spring dossier capture.
3. Use the runtime-evidence watcher to standardize before/after filesystem
   capture around manual Spring runs.
4. When live access returns, collect one or two high-quality manual result
   captures before writing more spring geometry.
5. After that, make a hard branch decision:
   native artifact path or custom-only path.

## Primary references

Official KOMPAS SDK pages that define the supported automation surfaces:

- KOMPAS SDK overview:
  https://help.ascon.ru/KOMPAS_SDK/22/ru-RU/index.html
- `IApplication` / application automation surface:
  https://help.ascon.ru/KOMPAS_SDK/22/ru-RU/iapplication.html
- legacy/bridge application acquisition (`ksGetApplication7` family):
  https://help.ascon.ru/KOMPAS_SDK/22/ru-RU/ksgetapplication7.html
- application libraries / procedures libraries:
  https://help.ascon.ru/KOMPAS_SDK/22/ru-RU/iapplication_libraries.html
- attach/open a procedures library:
  https://help.ascon.ru/KOMPAS_SDK/22/ru-RU/iprocedureslibraries_attach.html
- execute a procedures-library command:
  https://help.ascon.ru/KOMPAS_SDK/22/ru-RU/iprocedureslibrary_execute.html
- general command execution surface:
  https://help.ascon.ru/KOMPAS_SDK/22/ru-RU/iapplication_executekompascommand.html

Use forum/community material only as secondary evidence, not as the contract.
