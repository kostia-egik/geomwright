# Spring workflows

Spring support is split between managed parametric generators and native KOMPAS
module research. Managed workflows are the supported integration path inside the
experimental `spring_generation` catalog category; native module probing remains
a research surface.

## Managed families

| Family | Public workflow | Current status | Detailed contract |
| --- | --- | --- | --- |
| Compression | `preview_compression_spring`, `create_compression_spring` | implemented and live-verified | [compression-spring.md](compression-spring.md) |
| Conical | parametric workflow operations | implemented and live-verified | [conical-spring.md](conical-spring.md) |
| Torsion | parametric workflow operations | implemented and live-verified | [torsion-spring.md](torsion-spring.md) |
| Extension | hook-family parametric scenarios | experimental family coverage | See the runtime catalog and `parametric-workflows.md` |
| Disc/Belleville | `disc_spring` | implemented in the shared workflow | [parametric-workflows.md](parametric-workflows.md) |
| Diaphragm | `diaphragm_spring` plus cut/relief/pattern operations | complete | [diaphragm-spring.md](diaphragm-spring.md) |

The runtime catalog returned by `get_mcp_tool_catalog` is authoritative for
public MCP names. Internal bridge operations documented here are composed by the
managed workflow executor and are not necessarily exposed as standalone tools.

## Common workflow

1. Resolve catalog dimensions when a family has a size catalog.
2. Preview and validate the normalized geometry.
3. Execute the managed operation sequence.
4. Inspect operation-tree structure, formulas, body count, and family-specific
   geometry.
5. Reopen the saved `.m3d` and repeat the required readback.

Generated live models belong under ignored sample output directories. The
documented contract is the source of truth; a local `.m3d` is evidence for one
parameter set, not a replacement for the workflow definition.

## Native module research

Native KOMPAS module inspection is outside the managed spring contract. If it is
needed for local investigation, enable the research-only tools explicitly as
described in the project README. They are disabled by default and are not an
unattended production path.

Raw evidence and uncommitted work briefs stay in the ignored experiment
quarantine; current family documents and this index take precedence.
