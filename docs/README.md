# Geomwright documentation

Use this index to find the right level of detail. The README is the quickest
way to install and run the project; the documents below are contracts for a
specific task, not a changelog or a dump of live CAD experiments.

## Start here

| Document | For | What it answers |
| --- | --- | --- |
| [Project README](../README.md) | New user | What Geomwright is, requirements, install, first run |
| [Write operations](write_operations.md) | Operator or agent | Which writes need preflight/confirmation and how to verify them |
| [Geomwright Studio](geomwright-studio.md) | Studio user | How previews, managed blocks, save, and close work |
| [Low-level runtime](low-level-runtime.md) | Advanced user | Inspection and readback tools for sketches and features |

## Build and inspect geometry

| Document | Status | Scope |
| --- | --- | --- |
| [Sketch authoring agent protocol](sketch-authoring-agent-protocol.md) | Current | Plan → Execute → Verify → Correct for sketch changes |
| [Sketch runtime strategy](sketch-runtime-strategy.md) | Current | Ownership of host-side geometry and KOMPAS bridge calls |
| [Inspect sketch full report](inspect-sketch-full-report.md) | Current | `inspect_sketch_full` result shape and diagnostics |
| [Curve trimming contract](curve-trimming-contract.md) | Current | Trimmed and connected curve ownership |
| [Parametric workflows](parametric-workflows.md) | Experimental | Part plans, parameters, previews, and verification |

## Springs

| Document | Status | Scope |
| --- | --- | --- |
| [Spring workflows](spring-workflows.md) | Experimental | Family selection and common entry points |
| [Compression spring](compression-spring.md) | Current family contract | Compression spring geometry and evidence |
| [Conical spring](conical-spring.md) | Current family contract | Conical spring parameters and limitations |
| [Torsion spring](torsion-spring.md) | Current family contract | Torsion spring construction and readback |
| [Diaphragm spring](diaphragm-spring.md) | Live-verified | Flat, bent, S-bend, relief, and cut workflow |
| [Spring size catalogs](spring-size-catalogs.md) | Current | Catalog selection and validation |

## Transmissions

| Document | Status | Scope |
| --- | --- | --- |
| [Transmission platform](transmission-platform-concept.md) | Approved architecture | Shared boundaries and composition rules |
| [V-belt grooves](v-belt-groove.md) | Implemented, live-verified | DIN/ISO and GOST functional groove profiles |
| [Poly-V grooves](poly-v-groove.md) | Implemented, live-verified | ISO 9982 rounded profiles and managed cuts |
| [Flat-belt pulley](flat-belt-pulley.md) | Implemented, live-verified | Cylindrical/crowned managed rim |
| [Timing-belt pulley](timing-belt-pulley.md) | Experimental | T/AT and HTD preview and managed Studio path |
| [Chain transmission](chain-transmission-concept.md) | Experimental, create-verified | ISO/GOST roller and bush sprocket profiles; create-only family slice |

## Maintainer references

- [Architecture](../ARCHITECTURE.md) — Layer 1–4 ownership, runtime topology,
  production boundary, and compatibility namespaces.
- [CAD patterns](../CAD_PATTERNS.md) — verified KOMPAS COM/CAD behavior and
  reusable failure-prevention rules.
- [Agent navigation map](agent-navigation.yaml) — compact file/symbol/test entry
  points for bounded repository navigation.
- Human planning drafts and raw investigation notes are kept outside the public
  documentation tree until they become stable runtime contracts.

The maintainer references are intentionally more detailed than the user guides.
Start with the relevant contract above instead of reading them front to back.

## What is not in this index

Roadmaps, work-process notes, raw audits, generated CAD, and disposable probes are
development material. Unfinished local work belongs in the ignored
`experiments/spikes/` quarantine and is not included in the package or MCP tool
catalog.
