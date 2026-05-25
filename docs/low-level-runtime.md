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

## MCP Tools

Call `get_mcp_tool_catalog` with `category="low_level_runtime"` when you need a
bounded list of the low-level tools exposed by the MCP server.

Use these tools for read-only diagnostics:

- `preflight_document_context`: checks session, active/selected document, type,
  extension, and minimal tree/items readback.
- `probe_document_readback`: builds a COM readback manifest for an active
  document or a read-only opened file. When `model_path` is used, the file is
  closed by default after probing.
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

## Test Commands

From a source checkout without editable install:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests
```

After `python -m pip install -e .`, `PYTHONPATH` is not required.
