# Architecture overview

[Русский](../ru/architecture.md) · [English index](README.md) · [Detailed owner](../../ARCHITECTURE.md)

Geomwright separates deterministic geometry from stateful KOMPAS operations.
The root architecture owns detailed runtime decisions; this page is a compact
extension guide, not a second implementation history.

## Runtime path

```text
MCP client → geomwright.server → geomwright.kompas.server
           → *_tools.py / KompasAdapter → BridgeRunner
           → configured Windows Python + pywin32 → bridge → KOMPAS API7/API5
Studio     → registry / preview → bounded adapter workflow → same bridge
```

`geomwright` is the public application namespace. Most KOMPAS implementation
modules remain under `kompas_mcp` for compatibility. Preview-only Studio paths
calculate on the host; CAD jobs use the adapter and attach to visible KOMPAS.

## Ownership

| Layer | Responsibility | Typical owner |
| --- | --- | --- |
| L1 | One bounded operation or readback | Tool registration, adapter, runner, COM bridge |
| L2 | Deterministic geometry, normalization and checks | `sketch_runtime/`, family request/calculation modules |
| L3 | Ordered operations and verification | Workflow orchestration and verified runners |
| L4 | Complete supported part family | Parts, springs, cams, transmission families |

Studio is a presentation adapter over these layers. It does not own another
geometry core or register its preview modules as MCP tools. A family-specific
plan belongs on the host; reusable CAD primitives belong in the bridge.

## Contracts and state

Public requests/results use JSON-compatible values. Internal typed specs are
allowed; a universal `EntitySpec` or operation graph is not an established public
contract. Extend the existing owner instead of creating a competing schema.

Use explicit document/sketch/feature targets and preflight before a write.
Apply **Plan → Execute → Verify → Correct**. Verification may include snapshot
deltas, operation readback, body/topology/formula inspection, save/reopen and
visual inspection when necessary. COM `Update()` alone proves none of these.
There is no universal transaction across multiple MCP calls.

The bridge's named Windows mutex refuses overlapping calls with `CAD_BUSY`;
it does not serialize a complete multi-call workflow or manual KOMPAS edits.
Final-body selectors are temporary: re-list after rebuild/reopen. Read-only
geometry inspection does not silently rebuild or repair a model.

## Runtime and packaging boundaries

`BridgeRunner` defaults to a 300-second normal timeout. Normal transport files
are temporary; explicit diagnostic mode preserves artifacts and reports their
paths. Errors carry the last available progress checkpoint. Use a modern bridge
interpreter configured with `KOMPAS_PYTHON`.

`bridge/kompas_bridge.py` owns the bridge source; its packaged copy under
`src/kompas_mcp/assets/bridge/` must remain byte-identical. Shared bridge runtime
assets must be included in package data. Research-only native tools require
`GEOMWRIGHT_ENABLE_RESEARCH_TOOLS=1`; unfinished prototypes and live evidence
stay under ignored `experiments/spikes/`.

Read the [CAD patterns](../../CAD_PATTERNS.md), [low-level contract](../low-level-runtime.md)
and [development guide](development.md) before extending a CAD workflow.
