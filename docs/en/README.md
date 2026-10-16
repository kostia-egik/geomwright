# Geomwright — English documentation

[Русский](../ru/README.md) · [All contracts](../README.md) · [Project](../../README.md)

Geomwright automates KOMPAS-3D locally through an MCP server for AI agents and
a browser-based Studio for operators. It supports model inspection, bounded
changes, selected parametric families, specifications and assembly relinking.
It is an independent project, unaffiliated with ASCON.

Version 0.1.0 is alpha. Document lifecycle and specification/relink workflows
have the most mature contracts. Sketch writes, generated families and Studio
are experimental; a recorded live case supports that case, not every input
combination. Preview geometry is not a strength or manufacturing certification.

## Choose a guide

| Task | Guide |
| --- | --- |
| Install, connect KOMPAS, start Studio or MCP | [Setup](setup.md) |
| Understand ownership and extension boundaries | [Architecture](architecture.md) |
| Develop and validate a change | [Development](development.md) |
| Design and deliver a complete CAD module | [Module development rules](module-development.md) |
| Plan integration of modules into one part | [Construction chains — agreed plan](construction-chains.md) |
| Calculate and create a straight bevel wheel | [Bevel gear](gear-bevel.md) |
| Calculate and create a cam | [Camshaft](camshaft.md) |
| Review audit findings and readiness limits | [Project audit](project-audit.md) |

## First model workflow

1. Start visible KOMPAS and configure the bridge interpreter as described in setup.
2. Discover the tools with `get_mcp_tool_catalog`; inspect `get_session_state`
   and `list_documents` before choosing an explicit `document_id`.
3. Inspect the target, then preview/preflight the proposed operation.
4. Execute only the supported write, verify readback, and correct a failed result.
5. Save/reopen when the family contract requires persistence verification.

Use `inspect_sketch_full` for sketch work. For finished solids, start with
`list_model_bodies`; re-list geometry selectors after rebuilding or reopening.
For generated families, read the family contract before creating the part.

## Detailed references

These references are primarily English unless indicated otherwise:

- [Write operations](../write_operations.md), [Studio](../geomwright-studio.md)
  and [finished geometry](../finished-geometry.md).
- [Parametric parts](../parametric-workflows.md), [springs](../spring-workflows.md)
  and [transmissions](../transmission-platform-concept.md).
- [Cylindrical gears](../gear-spur.md), [internal gears](../gear-internal.md)
  and [detailed bevel contract](../gear-bevel.md).
- [Canonical architecture](../../ARCHITECTURE.md) (primarily Russian),
  [CAD patterns](../../CAD_PATTERNS.md) and [contribution policy](../../CONTRIBUTING.md).

The [root index](../README.md#languages-and-ownership) defines language ownership
and how to add another locale. Documentation languages do not imply a translated
Studio interface or translated MCP diagnostics.
