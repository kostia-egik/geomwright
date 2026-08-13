# Documentation index

This directory contains the current engineering contracts for Geomwright.
Documents are grouped by authority so that completed runtime behavior is not
confused with research evidence or historical implementation plans.

## Project contracts

| Document | Authority | Purpose |
| --- | --- | --- |
| [README](../README.md) | current | Installation, runtime status, and first workflow |
| [Architecture](../ARCHITECTURE.md) | current | Layer ownership and production boundaries |
| [CAD patterns](../CAD_PATTERNS.md) | current | Reusable CAD invariants backed by implementation evidence |
| [Write operations](write_operations.md) | current | Write safety and supported mutation contracts |
| [Low-level runtime](low-level-runtime.md) | experimental | Snapshot/readback and direct feature/sketch runtime |

## Sketch authoring and diagnostics

| Document | Status | Purpose |
| --- | --- | --- |
| [Sketch authoring agent protocol](sketch-authoring-agent-protocol.md) | current | Plan → Execute → Verify → Correct workflow for agents |
| [Sketch authoring geometry protocol](sketch-authoring-protocol.md) | design draft | Human geometry, constraint, and dimension planning |
| [Sketch runtime strategy](sketch-runtime-strategy.md) | current | Runtime ownership and adapter/bridge boundaries |
| [Sketch diagnostics](sketch-diagnostics.md) | experimental | Diagnostic modes and correction workflow |
| [`inspect_sketch_full` report](inspect-sketch-full-report.md) | current | Complete readback schema and interpretation |
| [Curve trimming contract](curve-trimming-contract.md) | current | Trimmed/connect-curve ownership and readback |

## Parametric parts

| Document | Status | Purpose |
| --- | --- | --- |
| [Parametric workflows](parametric-workflows.md) | current | Supported operation graph and public parameters |
| [Diaphragm spring workflow](diaphragm-spring.md) | current | Implemented workflow and S-bend cut compensation |
| [Spring workflows](spring-workflows.md) | current | Spring-family status and navigation |

## Mechanical transmissions

| Document | Status | Purpose |
| --- | --- | --- |
| [Transmission platform concept](transmission-platform-concept.md) | approved concept | Composition contract, family map, cutter-aware geometry, and delivery phases |
| [Native transmission audit](native-transmission-audit.md) | research evidence | Installed Shaft command map and interactive automation boundary |
| [V-belt groove profile and CAD builder](v-belt-groove.md) | Layers 2/3 implemented | Profile catalog, deterministic groove geometry, and verified cut-from-body workflow |
| [Poly-V groove profile and CAD builder](poly-v-groove.md) | Layers 2/3 implemented | ISO 9982 catalog, live master/dependent rounded profile, and mutation/save/reopen-verified cut workflow |
| [Geomwright Studio](geomwright-studio.md) | experimental, managed CAD creation | Local schema-driven UI that previews and creates owned V-belt and Poly-V pulleys |

## Spring-family documents

- [Compression spring](compression-spring.md)
- [Conical spring](conical-spring.md)
- [Torsion spring](torsion-spring.md)
- [Extension hook inventory](extension-hook-type-inventory.md)
- [Extension native-fillet audit](extension-hook-native-fillet-audit.md)
- [Self-wrapping hook phase 1 report](self-wrapping-hook-phase1-report.md)
- [Bent-coil coordinate system](bent-coil-sketch-coordinate-system.md)
- [Bent-coil parametrization report](bent-coil-parametrize-report.md)
- [Spring size catalogs](spring-size-catalogs.md)
- [Native spring strategy](native-spring-strategy.md) — research surface, not a
  substitute for the managed workflows

## Archive policy

`docs/archive/` is reserved for historical records intentionally retained in
Git. Archive files may explain why a decision was made, but they do not define
current behavior. Promote a result into a canonical document before using it as
a runtime contract.

Local unfinished prototypes and historical work briefs belong under the ignored
`experiments/spikes/` quarantine, not in this documentation tree.
