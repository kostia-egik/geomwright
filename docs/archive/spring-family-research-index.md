# Spring Family Research Index

This file is only a navigation layer for the current spring-family work.

It does not define new contracts by itself.

## Current family map

| Family | State | Main docs | Main executable prep |
| --- | --- | --- | --- |
| `compression_spring` | implemented in public parametric surface; cylindrical ground trimming live-checked | `compression-spring-contract-freeze.md`, `compression-spring-ground-trim-contract.md`, `compression-spring-v2-implementation-cut-plan.md`, `compression-spring-live-acceptance.md` | `sample/prepare_compression_spring_v2_live_readback_matrix_2026_06_01.py` |
| `extension_spring` | implemented in public parametric surface; hook mechanics live-checked | [`../extension-hook-type-inventory.md`](../extension-hook-type-inventory.md), [`../extension-hook-native-fillet-audit.md`](../extension-hook-native-fillet-audit.md) | extension hook live outputs under `sample/live_outputs/` |
| `torsion_spring` | implemented in public parametric surface; tangent/radial/axial leg families live-checked | [`../torsion-spring.md`](../torsion-spring.md) | torsion live outputs under `sample/live_outputs/` |
| `conical_spring` | research lane, no public geometry API yet | `conical-spring-contract-freeze.md`, `conical-spring-live-audit-matrix.md` | `sample/prepare_conical_spring_native_dossier_2026_06_01.py`, `sample/prepare_conical_spring_live_audit_matrix_2026_06_01.py` |
| `disc_spring` | research lane, no public geometry API yet | `disc-spring-contract-freeze.md`, `disc-spring-live-audit-matrix.md` | `sample/prepare_disc_spring_native_dossier_2026_06_01.py`, `sample/prepare_disc_spring_live_audit_matrix_2026_06_01.py` |

## Shared entry points

Use these first before choosing a family-specific path:

- [`native-spring-strategy.md`](native-spring-strategy.md)
- [`native-spring-live-evidence.md`](native-spring-live-evidence.md)
- [`research-spring-live-run-backlog.md`](research-spring-live-run-backlog.md)
- MCP tool `inspect_native_spring_workflow(...)`

## Practical routing

Choose one of these lanes:

1. Public scenario lane:
   `compression_spring`, `extension_spring`, and `torsion_spring` are available
   through `src/kompas_mcp/parametric.py`.
2. Research lane:
   `conical_spring` and `disc_spring` should stay in native dossier + live audit
   mode until a manual run proves what persists after save/reopen.
3. Live verification lane:
   after offline prep, run the generated sample matrices and then execute the
   bounded manual checks in the matching `*-live-audit-matrix.md` file or the
   shared [`research-spring-live-run-backlog.md`](research-spring-live-run-backlog.md).

## Recommended next order

1. Run one live verification session for `compression_spring` V2.
2. Use [`research-spring-live-run-backlog.md`](research-spring-live-run-backlog.md)
   for the next cross-family native campaign: `conical_spring`, `disc_spring`.
3. Compare which families actually expose stable readback/formula evidence.
4. Open the next public spring scenario only after one family clears that
   evidence gate.
