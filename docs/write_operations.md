# Write Operations

Write tools use the same V2 contract:

1. validate inputs and resolve the target document/sketch/plane;
2. capture a bounded snapshot before the operation;
3. run the COM mutation;
4. capture a bounded snapshot after the operation;
5. compute a delta;
6. verify the expected delta and return one normalized envelope.

Success means the operation returned `ok=true`, the before/after readback exists, the delta matches the tool expectations, and any declared artifact paths exist. A successful COM call without a readback delta is treated as a failed write contract.

## Targeting

Sketch writes support an explicit target object. To create a new sketch:

```json
{
  "mode": "create_new_sketch",
  "name": "SKETCH_BATCH_1",
  "plane": "XOY"
}
```

To append entities to an existing sketch, pass the readback `sketch_ref` from a previous write or snapshot and set `create_new_sketch=false`:

```json
{
  "sketch_ref": "12345",
  "create_new_sketch": false,
  "entities": [
    {"kind": "segment", "start": [0, 0], "end": [10, 0]}
  ]
}
```

Only explicit `sketch_ref` targeting is supported for existing sketches. Name-based matching is intentionally not used because it can be ambiguous.

## Error Classes

- `INVALID_INPUT`: malformed coordinates, empty entity lists, bad radius, or unsupported entity kind.
- `AMBIGUOUS_TARGET`: more than one target strategy was requested, or none was actionable.
- `UNSUPPORTED_COM_SHAPE`: the live COM object does not expose the required collection/method, or a reserved target mode is not implemented.
- `EMPTY_READBACK`: the operation could not produce enough readback data to verify.
- `COM_CALL_FAILED`: raw COM/Dispatch/OLE failures.

## Batch Sketch Entities

Use `create_sketch_entities` to create multiple entities in one target sketch. Supported entity kinds are currently `point`, `segment`, `polyline`, `arc`, `circle`, `ellipse`, and `rectangle`.

The same entity set is also available as single-primitive tools:
`create_sketch_point`, `create_sketch_line_segment`, `create_sketch_polyline`,
`create_sketch_arc`, `create_sketch_circle`, `create_sketch_ellipse`, and
`create_sketch_rectangle`. Single-primitive tools accept the same
`sketch_ref`/`create_new_sketch` target parameters, so they can append to a
previously created sketch without switching to the batch API.

```json
{
  "name": "SKETCH_BATCH_1",
  "plane": "XOY",
  "entities": [
    {"kind": "point", "point": [0, 0]},
    {"kind": "segment", "start": [0, 0], "end": [50, 0]},
    {"kind": "polyline", "points": [[0, 0], [20, 10], [40, 0]]},
    {"kind": "arc", "center": [25, 10], "radius": 8, "start": [33, 10], "end": [25, 18]},
    {"kind": "circle", "center": [25, 10], "radius": 5},
    {"kind": "ellipse", "center": [25, 10], "radius_x": 12, "radius_y": 5},
    {"kind": "rectangle", "corner1": [0, 0], "corner2": [50, 20]}
  ]
}
```

The tool returns per-entity results plus a shared after snapshot and delta. Batch execution is fail-fast and does not attempt rollback yet.

Batch entities may include `id` or `entity_id`. These IDs are used by optional
low-level `constraints` and `dimensions` payloads in the same call. For
multi-line entities, the bridge also exposes generated child IDs such as
`polyline_id_1` or `rectangle_id_3` in each result's `entity_ids`.

```json
{
  "name": "SKETCH_PARAM_1",
  "entities": [
    {"kind": "segment", "id": "base", "start": [0, 0], "end": [50, 0]}
  ],
  "constraints": [
    {"kind": "horizontal", "target": "base"}
  ],
  "sketch_options": {
    "readback_geometry": true
  }
}
```

Use `parameterize_sketch` when the geometry already exists. It requires
`sketch_ref`, an explicit `entities` selection map, and `constraints` or
`dimensions`. Existing entities can be selected by `reference`, collection
`index`, or exact readback `fingerprint`. Creation results include
`collection_index` to support a follow-up parameterization call when raw COM
`reference` values are renumbered after `Sketch.Update()`.

Use `list_sketches` first when the target sketch reference is unknown. It
returns bounded sketch rows with `name`, `reference`, `sketch_ref`, and
`collection_index`. Use `rename_sketch` when the selected sketch needs a
stable, agent-readable name before follow-up operations.

Use `list_sketch_entities` when the sketch was not created in the same agent
step. It returns bounded selector rows with `reference`,
`collection_index`, `fingerprint`, and `geometry` for `segment`, `circle`,
`point`, `arc`, and `ellipse` entities.

Use `inspect_sketch_entity` when one selector needs a fresh readback row before
parameterization. It accepts the same `reference`, collection `index`, or
`fingerprint` selectors and returns one entity descriptor with geometry.

Use `set_sketch_entity_style` to update the line style for one selected
existing entity without changing its geometry.

Use `delete_sketch_entity` to remove one mistaken existing entity by the same
`reference`, collection `index`, or `fingerprint` selector. The result includes
the deleted entity descriptor, before/after collection counts, and readback
snapshots around the edit.

```json
{
  "sketch_ref": "12345",
  "entities": [
    {"id": "base", "kind": "segment", "reference": "201"}
  ],
  "constraints": [
    {"kind": "horizontal", "target": "base"}
  ],
  "sketch_options": {
    "readback_geometry": true
  }
}
```

`require_no_removed` defaults to `false` for batch sketch writes. Live KOMPAS readback can renumber or reshape existing sketch entity references after edit, so the stable default contract is `min_added >= 1` plus after-snapshot readback. Set `require_no_removed=true` only for tightly controlled models where removed-item deltas are known to be stable.

## Live Audit

The manual live audit script is `sample/audit_live_kompas_write_v2_2026_05_24.py`.
It copies the requested model into `sample/generated/...`, opens the copy, runs
`create_sketch_entities`, captures an after snapshot, writes
`write_v2_audit_manifest.json`, and closes the copied document unless
`--keep-open` is passed.

Example:

```powershell
.\.venv\Scripts\python.exe sample\audit_live_kompas_write_v2_2026_05_24.py --model-path C:\path\to\part.m3d --visible
```
