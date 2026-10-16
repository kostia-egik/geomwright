# Low-Level Runtime And Readback

This document is the map for the small KOMPAS interaction layer. It is not a
feature roadmap for large modelling modules; it exists to make live COM work
observable, bounded, and testable.

## Goal

The layer answers three questions before and after every small live operation:

- Is the KOMPAS session and selected document usable?
- What did COM return when we read the document back?
- Did the operation change the document in the expected way?

Most helpers are pure Python and are tested with fake adapters. The live COM
contract still needs manual confirmation in KOMPAS.

## CAD Work Modes

The work mode is a shared session policy, not a per-tool `visible` flag:

- `interactive` (default): attach to one selected visible KOMPAS window. Bind its
  HWND, PID and process creation time across calls. No implicit application
  creation, showing a hidden instance, or substitute-instance fallback. If
  several visible instances exist, explicitly select the target HWND; a window
  not exposed through ROT cannot be selected by guessing a PID.
- `hidden` (explicit): create a separate automation-owned process. Before hiding
  it, prove that its PID was absent from the pre-create process snapshot. Reuse
  only that bound identity. If isolation cannot be proven or ROT cannot reattach
  the owned object, stop; do not use the user's instance or create a replacement.

`get_cad_work_mode()` reads the selected mode/binding without COM.
`set_cad_work_mode(mode="hidden", confirm_switch=true)` explicitly selects a
hidden session; it does not start KOMPAS. Selecting interactive can additionally
use `target_window_handle=<HWND>`. Selection/rebinding is refused while quarantined
or in flight, and while a previously owned hidden process remains alive. A host
pins the context token: another client's mode switch between workflow steps
causes `CAD_SESSION_CHANGED`, not an automatic transition.

Mode state is stored as runtime `cad-session.json` beside the durable guard.
`KOMPAS_CAD_MODE` can explicitly request a mode for an unconfigured host; it must
not silently replace an existing selection. The legacy visible-session flag
never authorizes implicit/hidden creation. Studio is interactive-only and refuses
an incompatible shared hidden selection.

Documents.Add/Open enforce visibility for the selected mode, including legacy
tools whose `visible` arguments/defaults differ. In interactive mode, save keeps
the same document open. Automatic probe/workflow cleanup must not close it.
`close_document` remains an explicit user command; save tools now default to
`close_after_save=false`, with explicit `true` permitting user-requested closure.
Interactive shutdown may close explicitly requested documents but does not quit
the user's application. Hidden shutdown may Quit only its proven-owned process;
Quit acceptance is not proof of process exit, so ownership is retained until an
explicit new selection after exit.

Interactive save uses direct SaveAs plus target-file/path checks, without the
hidden staging Close/replace/reopen lifecycle. A retained document is not freshly
reopened: legacy module verification reports `recipe_reopened=false`,
`save_reopen_deferred=true`, scope `creation_and_visible_saved_readback`. Hidden
staged workflows may report actual save/reopen. The smoke lifecycle and legacy
SPW row creation require hidden mode; hosted native UI commands require
interactive mode. Unsupported combinations fail before CAD, never switch modes.

Visible API work does not guarantee per-entity animation or an interactive sketch
editor on screen. It guarantees the selected instance/document policy, not a
paint event after each constraint. For joint inspection, use explicit document
IDs and completed stages; do not ask the user to inspect an unconfirmed hidden
or closed result.

Evidence boundary: host and fake-COM tests protect this policy. Native separate
process creation, ROT reattachment, visible-window matching and retained direct
save (including Unicode paths) require live verification before claiming this
behavior is live-verified. Do not reset an existing quarantine to run these checks.

## Timeout And Session Recovery

MCP and Studio default to a finite 300-second budget per bridge call. Terminating
the bridge does **not** cancel work already submitted to KOMPAS. A durable marker
is written before launch. While it remains, subsequent ordinary bridge calls,
including `list_documents`, readback and `close_document`, are refused with
`CAD_DIAGNOSTICS_REQUIRED` for a settled failure or `CAD_SESSION_BLOCKED` for an
uncertain outcome. Normal successful completion removes the marker; a known
prelaunch failure does not quarantine CAD.

The production bridge publishes a token/action-bound completion receipt only
after the handler and mutex have completed. Recovery distinguishes these outcomes:

- A trusted `no_cad` receipt releases the guard when no CAD operation was submitted.
  This includes validation and read-only session-selection refusals before any
  controller activation, instance creation or model access.
- A trusted `settled` receipt for a finished handler failure retains the marker
  as `settled_failure`; this permits only the dedicated recovery audit below.
- Timeout, cancellation, malformed response, crash (including an outer watchdog
  killing the host), or a failed custom script without a trusted receipt remains strict
  `unknown_outcome`. Process exit or a progress checkpoint is not a substitute
  for a trusted completion receipt.

Successful custom scripts retain their existing response contract. They cannot
authorize automatic recovery of failures; production successes require a valid
terminal receipt too.

Call `get_cad_session_guard` first: it reads host state without COM and returns
the current token, operation, process IDs and last checkpoint. A missing marker
does not prove CAD readiness. `recover_cad_session(token, reason,
confirm_idle=False)` requires the fresh token and refuses recovery while the
bridge or its launching/in-flight host is still running. Use the branch matching
the guard state:

### Completed Handler Failure: `settled_failure`

Call `recover_cad_session(token=..., reason=...)`; explicit user idle confirmation
is not a prerequisite for this branch. It runs an exclusive, bounded 15-second
audit against the already bound **same instance**. It cannot create or substitute
an instance, activate a controller or document, edit, rebuild, save, or close.
The audit checks:

- the native application frame is responsive and enabled, and whether a visible
  standard dialog blocks it;
- COM document listing, returned as a bounded document summary;
- API5 graphical-process state, possible sketch-editor state, and in-place
  component-edit blockers.

The result reports `model_verified=False`. A passing audit removes the marker
with basis `completed_handler_and_session_audit` and
`cad_readiness_verified=False`. Before any further write, the agent must inspect
the affected document and partial changes and decide what is safe. Never blindly
retry the failed operation: completed handler execution does not imply rollback
or a correct model.

A blocker retains the `settled_failure` marker. Ask the user to handle unresolved
UI state when needed, then use a fresh guard token for another recovery attempt;
do not treat every settled failure as requiring manual idle confirmation.

If the previously bound KOMPAS process has exited, recovery can remove the settled
marker without COM, with basis `bound_session_exited`. It does not attach another
instance. Explicitly select the intended session before another CAD call.

### Uncertain Completion: `unknown_outcome`

Wait for KOMPAS and obtain a fresh, explicit user confirmation that its visible
UI is idle and partial documents have been reviewed/resolved. Do not infer this
from process exit or an API document count of zero; do not send more COM probes.
Only then call `recover_cad_session(token=..., reason=..., confirm_idle=True)`
with the fresh token. This branch removes only the marker, without COM, rollback,
closing tabs or restarting KOMPAS. Inspect session/document state before deciding
whether another write is appropriate; do not blindly retry.

Neither branch is a general asynchronous cancellation solution or a guarantee
that the UI is idle. A session audit is not model verification or CAD readiness
certification.

The marker lives under `KOMPAS_MCP_SESSION_GUARD_DIR`, or otherwise
`KOMPAS_MCP_TEMP_DIR/geomwright-session-guard` (default temp root:
`C:\Windows\Temp`). MCP and Studio controlling the same KOMPAS must share this
directory. Direct COM scripts and manual UI actions are outside this boundary.
Do not delete markers automatically or use another directory to bypass quarantine.

Failed part scenarios retain the owned partial document by default and report
`cleanup.attempted=false`, `cleanup.verified_closed=false` in progress. The intended
output path is not a verified document ID. Legacy explicit `save_partial_on_error`
remains an opt-in salvage policy; it may itself call CAD and is not a recovery
mechanism. Full diagnostic transport artifacts are retained only in diagnostic
mode; the durable guard retains bounded checkpoints in either mode.

For live probes, an outer `scripts/run_bounded.py` deadline must exceed the total
sequential bridge-call budgets plus overhead. A short outer deadline cannot be
used as evidence that KOMPAS stopped or that the next probe is safe.

## Model PNG Export

`export_model_png(document_id, output_path=None, view="current",
resolution_dpi=150, fit=true)` exports the exact opened model through native
KOMPAS raster export, without a save dialog, model rebuild or geometry operations.
This is a file-writing/view-state operation, not a read-only diagnostic or a
geometry-verification tool.

Views are `current|front|rear|top|bottom|left|right|isometric`; DPI must be an
integer from 72 to 600. Presets follow native KOMPAS orientation: `left` may show
the side of a global-X part rather than its end. Example tool arguments:

```json
{"document_id":"<exact opened document ID>","view":"left","resolution_dpi":150,"fit":true}
```

Omitting `output_path` creates a UUID-named PNG in the export directory. An explicit
destination must be an absolute new `.png` path with an existing parent; existing
files are refused, never overwritten. The result returns artifact path, dimensions
and restoration status. PNG header validation is not visual acceptance: open the
actual raster to check smooth faces, holes and grooves.

Standard-view selection and fitting are temporary. The runtime restores and checks
`Matrix3D`, `Scale` and the previously active document; exact screen pan is not
certified. No arbitrary Euler-angle interface is exposed until native units are
verified. Live Stage D gear-chain PNG review confirms the native raster and checked
restoration; export success alone does not certify geometry.

## MCP Tools

Call `get_mcp_tool_catalog` with `category="low_level_runtime"` when you need a
bounded list of the low-level tools exposed by the MCP server.

Use these tools for read-only diagnostics:

- `preflight_document_context`: checks session, active/selected document, type,
  extension, and minimal tree/items readback.
- `probe_document_readback`: builds a COM readback manifest for an active
  document or a read-only opened file. When `model_path` is used, the file is
  closed by default after probing.
- `probe_model_formulas`: walks live sketches/features for formula-bearing
  dimensions, constraints, and feature variables, and can optionally merge that
  with offline `.m3d` `Contents` extraction in one bounded report.
- `probe_model_object_collections`: probes known model-object surfaces. It keeps
  the original model-container collection summary for compatibility, and also
  reports bounded `surfaces` for top part, model container, and auxiliary
  geometry accessors. It returns counts plus bounded object previews, not full
  geometry.
- `get_active_document_state`: returns a bounded active-document summary and
  optional tree/items previews.
- `capture_document_snapshot`: captures a bounded snapshot and can write the
  full manifest JSON artifact.
- `verify_document_readback_stability`: captures two snapshots and requires
  zero added/removed/changed items. Use `ignore_paths`, `ignore_keys`, or
  `use_default_volatile_ignores` for timestamp/session noise.
- `list_sketch_dimensions` / `inspect_sketch_dimension`: read live sketch
  dimensions from an existing `sketch_ref` and return bounded selectors
  (`reference`, `collection_index`, `fingerprint`) for repair workflows.
- `list_sketch_constraints` / `inspect_sketch_constraint`: scan live sketch
  entities for exposed constraint collections and return bounded owner/selector
  diagnostics for repair workflows.
- `clear_sketch_entity_constraints`: deletes all constraints attached to one
  selected sketch entity via `IDrawingObject1.DeleteConstraints`, then returns
  before/after entity snapshots and bounded constraint-count diagnostics.
- `repair_sketch`: plans by default, or applies with `apply=true`, a bounded
  repair scenario over one existing sketch. The first supported operations are
  `clear_constraints`, `update_geometry`, and `delete_entity`.

Live note: the first KOMPAS check after creating a horizontal constraint found
`Constraints` surfaces on some line entities, but those collections reported
zero items. Treat constraint readback as a diagnostic probe until another COM
surface is confirmed; constraint repair is currently handled by clearing
constraints from the selected owner entity.

Use these tools for offline verification:

- `diff_document_snapshots`: compares two manifest/snapshot payloads or JSON
  artifacts and returns bounded added/removed/changed previews plus count deltas.
- `verify_document_snapshot_delta`: verifies expected snapshot deltas from a
  ready diff or from before/after snapshot artifacts.
- `classify_runtime_error`: maps KOMPAS/COM/preflight failures to stable error
  codes and recovery hints.
- `normalize_operation_result`: creates a bounded operation envelope from
  result payloads, checks, artifacts, readback contracts, and classified errors.

## Python Helpers

These helpers are intended for future small primitive operations:

- `operation_executor.execute_primitive_operation`: runs preflight, an operation
  callback, optional readback contract verification, and returns the common
  envelope.
- `operation_snapshot_loop.execute_snapshot_verified_operation`: captures
  before/after snapshots around an operation callback and verifies the expected
  delta.

## BridgeRunner Modes And Progress

`BridgeRunner` is the Layer 1 process boundary around the modern Windows Python
configured through `KOMPAS_PYTHON`, with `pywin32` installed. The legacy bundled
Python 3.2 cannot run the current bridge; see [setup](en/setup.md).
Its default `normal` mode uses a bounded 300-second timeout and removes
the temporary request/response files after each call. A caller can still set a
different timeout on the runner or one call.

The explicit `diagnostic` mode keeps the complete request, response, progress,
stdout, and stderr artifacts under `KOMPAS_MCP_DIAGNOSTIC_DIR` or the operating
system temporary directory. Their paths are available through
`runner.last_diagnostic_artifacts`; diagnostic mode is never selected
implicitly after a failure.

Progress callbacks receive one compatible bounded envelope with `stage`,
`operation`, `percent`, `document_id`, `target`, and host-measured `elapsed_ms`.
Legacy bridge events that only provide `operation` and `name` are normalized by
the runner. Timeout, cancellation, and bridge errors include the last progress
checkpoint when one was observed.

The bridge dispatch layer adds a bounded `action_started`, `action_completed`,
or `action_failed` checkpoint around every action, including low-level handlers
that do not yet expose their own internal milestones. Family-specific handlers
may publish additional checkpoints between these outer events.

## Readback Manifest

`document_readback.build_document_readback_manifest()` normalizes COM output
into a compact manifest. Its item index supports lookup by:

- identity fields: `id`, `name`, `type`, `role`, `reference`, `path`, `source`
- tree fields: `parent_id`, `parent_path`, `depth`, `children_count`
- state fields: `hidden`, `visible`, `active`, `changed`
- duplicate diagnostics: `duplicate_ids`, `same_source_duplicate_ids`

`DocumentReadbackContractSpec.expected_items` checks that expected objects are
present. `forbidden_items` checks that temporary or unwanted objects are absent.
Both share the same lookup criteria.

For noisy or schema-light COM payloads, item criteria also support:

- `*_contains`, such as `name_contains`, `type_contains`, `path_contains`
- `field_equals` and `field_contains` for dotted-path custom fields
- `field_exists` and `field_missing`
- `field_has` and `field_has_contains` for list membership
- `numeric_fields` with `numeric_tolerance`

Failure diagnostics stay bounded: they show key item fields and `extra_keys`
instead of dumping the full COM payload.

## Observed Live Readback

The first read-only live audit against an active KOMPAS part returned a root
`part` item with scalar fields such as `designation`, `density`, `material`,
`source_path`, and `mass`. These fields are preserved by the compact item index,
so contracts can match them with `field_equals`, `field_contains`, and
`numeric_fields` without adding a special schema for each COM property.

A follow-up audit with `--model-path sample/generated/2.m3d` verified the
open/read/close path. The generated manifest uses `tree_root` plus flattened
`tree_nodes`; it does not expose a top-level `tree` list. The same root `part`
appeared from both `tree` and `items`, producing a normal cross-source
`duplicate_ids.root` entry while keeping `same_source_duplicate_ids` empty.

Additional audits against `lcs_global_demo.m3d` and a larger BSP thread model
returned the same shape: one root `part` from `tree_root` and one matching root
item. This confirms that the current bridge readback is stable for part-level
document metadata, but it is not yet a full feature/sketch/model-object tree
reader.

`probe_model_object_collections` is the next bridge-level probe for that gap. It
does not replace the manifest yet; it reports which known KOMPAS surfaces and
collections are exposed and whether they contain sketches/features/auxiliary
objects on real documents.

The first live run of this probe against the BSP thread model found all five
known model-container collections available (`sketches`, `rotateds`,
`extrusions`, `evolutions`, `feature_patterns`) but empty. After extending the
probe across surfaces, the same file also exposed `points3d` on the model
container and `axes3d`, `planes3d`, `local_coordinate_systems` on the auxiliary
geometry container, also empty. This suggests the sample files may be saved as
final geometry without editable feature/auxiliary history, or that object
history is exposed through another KOMPAS API surface.

A fresh `create_real_kompas_sketch_runtime_task_2026_05_20.py` run produced an
operation manifest with 8 operations and 6 auxiliary objects while the saved
`.m3d` still reopened with empty sketch/feature/auxiliary collections. Treat the
operation manifest as the current source of truth for created transient objects;
the saved-document COM readback is currently verified only for root part
metadata and readback stability.

Workflow scenarios can now opt into an in-memory `runtime_object_probe` with
`params.include_runtime_object_probe=true` before save/close. That probe inspects
the transient `runtime_objects` handles created during workflow execution and
reports bounded output type/object type counts. Use it to compare live handles
against saved-document readback without trying to serialize geometry bodies.

A live point/LCS workflow with the runtime probe enabled reported two transient
outputs before save/close: one `point` handle (`IPoint3D`) and one `lcs` handle
(`CDispatch`). This confirms the in-memory workflow surface can see objects that
the saved-document model-object collections did not expose after reopen.

The probe now also records `surfaces` for `top_part`, `model_container`, and
`auxiliary_geometry_container` accessors such as `Parts`, `ModelObjects`,
`ResultBodies`, `Points3D`, `Axes3D`, `Planes3D`, and
`LocalCoordinateSystems`. This is still diagnostic data only; nonempty
collections should be promoted into the readback manifest after live evidence
shows which surface is reliable.

## Recommended Live Check Order

Use the combined read-only sample first:

```powershell
$env:PYTHONPATH='src'
python sample\audit_live_kompas_low_level_2026_05_20.py --document-id <id-or-path>
```

For a file path, the sample opens the model read-only once and closes it by
default:

```powershell
$env:PYTHONPATH='src'
python sample\audit_live_kompas_low_level_2026_05_20.py --model-path C:\path\part.m3d
```

Run only one live audit at a time against the same KOMPAS session. KOMPAS has a
process-global active document; concurrent audits can switch the active document
between `open_document` and `preflight_document_context` and produce a valid
`active_document_selected` failure.

The sample runs this sequence and writes artifacts under `sample/generated/`:

1. `get_mcp_tool_catalog(category="low_level_runtime")`
2. `preflight_document_context`
3. `probe_document_readback`
4. `probe_model_object_collections`
5. `capture_document_snapshot`
6. `verify_document_readback_stability`

Only after this read-only audit passes should snapshot delta verification be
used around write operations.

## Maintenance Checks

Keep the adapter/bridge request and response keys aligned, compile the modified
host modules with the project Python, and compile both bridge copies with the
configured CAD interpreter. The two bridge files must remain byte-identical. For CAD
behavior, use the read-only audit above and a saved-document reopen check rather
than treating a synthetic response as live evidence.
