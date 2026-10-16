# Geomwright documentation

Use this index to find the right level of detail. The README is the quickest
way to install and run the project; the documents below are contracts for a
specific task, not a changelog or a dump of live CAD experiments.

## Start here

Choose a language: [English](en/README.md) / [Русский](ru/README.md).
The paired guides cover introduction, setup, architecture, development, module
development rules, the construction-chain plan, bevel gears and cams. Detailed
family references below retain their existing language.

| Document | For | What it answers |
| --- | --- | --- |
| [Project README](../README.md) | New user | What Geomwright is, requirements, install, first run |
| [Write operations](write_operations.md) | Operator or agent | Which writes need preflight/confirmation and how to verify them |
| [Geomwright Studio](geomwright-studio.md) | Studio user | How previews, managed blocks, save, and close work |
| [Low-level runtime](low-level-runtime.md) | Advanced user | Inspection and readback tools for sketches and features |
| [Finished model geometry](finished-geometry.md) | Operator or agent | Read final bodies, capture face shapes and measure selected geometry |

## Build and inspect geometry

| Document | Status | Scope |
| --- | --- | --- |
| [Sketch authoring agent protocol](sketch-authoring-agent-protocol.md) | Current | Plan → Execute → Verify → Correct for sketch changes |
| [Sketch runtime strategy](sketch-runtime-strategy.md) | Current | Ownership of host-side geometry and KOMPAS bridge calls |
| [Inspect sketch full report](inspect-sketch-full-report.md) | Current | `inspect_sketch_full` result shape and diagnostics |
| [Curve trimming contract](curve-trimming-contract.md) | Current | Trimmed and connected curve ownership |
| [Parametric workflows](parametric-workflows.md) | Experimental | Part plans, parameters, previews, and verification |
| Construction-chain plan: [English](en/construction-chains.md) / [Русский](ru/construction-chains.md) | A–D and bounded Stage E live-verified; broader plan pending | MCP-only shaft/cone/core cuts, initial gear/spline foundations, polygon/flat sections, bolt-circle holes, placement, ownership and saved-file continuation |

## Springs

| Document | Status | Scope |
| --- | --- | --- |
| [Spring workflows](spring-workflows.md) | Experimental | Family selection and common entry points |
| [Compression spring](compression-spring.md) | Current family contract | Compression spring geometry and evidence |
| [Extension spring](extension-spring.md) | Shared legacy interface | Conventional hook inputs, saved recipes, native verification and limits |
| [Conical spring](conical-spring.md) | Current family contract | Conical spring parameters and limitations |
| [Torsion spring](torsion-spring.md) | Current family contract | Torsion spring construction and readback |
| [Disc spring](disc-spring.md) | Current family contract | Normal-thickness rotational creation, readback and legacy editing limits |
| [Stepped shaft](stepped-shaft.md) | Current family contract | Legacy rotational-body constructor, native step verification and create-only boundary |
| [External cone](external-cone.md) | Current family contract | Five definition modes, standalone body and live-verification boundary |
| [External polygon](external-polygon.md) | Current family contract | Standalone prism, driving variables, coordinate frame and verification boundary |
| [External flat step](external-flat.md) | Current family contract | Cylinder with one/two flats, driving inputs and recipe/lifecycle evidence boundary |
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
| [Cylindrical gear](gear-spur.md) | Implemented, live-verified | External spur and helical cylindrical gear with four basic-rack systems (ГОСТ 13755-2015, ГОСТ 9587-81, ГОСТ Р 50531-93, ISO 53:1998), cached pin rows, optional tip chamfers; nominal preview, create-only managed part, MCP tools |
| [Internal gear](gear-internal.md) | Implemented, live-verified | Internal spur and helical ring gear with explicit blank outside diameter (ГОСТ 19274-73 nominal geometry); nominal preview, create-only managed part, MCP tools |
| [Straight bevel gear](gear-bevel.md) | Experimental, implemented; recorded live cases | Straight bevel wheel from ГОСТ 19624-74 macro geometry and the Tredgold virtual-gear projection; nominal preview, create-only managed part, MCP tools; circular teeth are reserved |
| [Gear transmission plan](gear-transmission-concept.md) | Planned, research-backed | Cylindrical, bevel, hypoid, and worm families; native baseline, CAD/Studio split, phases |
| [Gear standards register](gear-standards.md) | Reference | GOST/ISO/DIN/AGMA designations, applicability, and acquisition status |

## Shaft connections

| Document | Status | Scope |
| --- | --- | --- |
| [Straight-sided splines](spline-straight.md) | Implemented, live-verified | ГОСТ 1139-80 light/medium/heavy catalog, exact end profile, ГОСТ 25346 fits, create-only shaft and hub managed parts, Studio modules and MCP tools |
| [Connection systems plan](connection-systems-concept.md) | Planned, research-backed | Splines incl. radiused runout, keyways, face joints, and motorcycle dog clutches; native baseline, CAD/Studio split, phases |
| [Connection standards register](connection-standards.md) | Reference | GOST/ISO/DIN/ANSI designations, applicability, acquisition status, and non-standard face joints |

## Shaft features

| Document | Status | Scope |
| --- | --- | --- |
| [Grooves and undercuts plan](groove-systems-concept.md) | Planned, research-backed | Retaining-ring grooves, seal and O-ring seats, grinding exits, thread runouts, and related seats |
| [Groove standards register](groove-standards.md) | Reference | GOST/DIN/ISO designations, applicability, status conflicts, and acquisition list |

## Camshafts

- [English: camshaft calculation and CAD](en/camshaft.md)
- [Русский: расчёт и CAD кулачков](ru/camshaft.md)

## Languages and ownership

| Topic | English | Русский | Detailed owner |
| --- | --- | --- | --- |
| Introduction and navigation | [Start](en/README.md) | [Начало](ru/README.md) | Root `README.md` and this index |
| Installation and operation | [Setup](en/setup.md) | [Установка](ru/setup.md) | Root `README.md`; runtime/config source |
| Architecture overview | [Architecture](en/architecture.md) | [Архитектура](ru/architecture.md) | Root `ARCHITECTURE.md` and `CAD_PATTERNS.md` |
| Development and checks | [Development](en/development.md) | [Разработка](ru/development.md) | Root `CONTRIBUTING.md`; check scripts |
| Complete CAD module development | [Module rules](en/module-development.md) | [Регламент модулей](ru/module-development.md) | Paired full rules; new-module scope and completion criteria |
| Construction chains | [Chain plan](en/construction-chains.md) | [План цепочек](ru/construction-chains.md) | Paired agreed plan; no new runtime capability claims |
| Straight bevel wheel | [Bevel gear](en/gear-bevel.md) | [Коническое колесо](ru/gear-bevel.md) | `gear-bevel.md`; request and calculation source |
| Cam calculation and CAD | [Camshaft](en/camshaft.md) | [Кулачки](ru/camshaft.md) | Paired full family guides |

Use `docs/<language>/<topic>.md`, matching filenames, and a link to the same
topic in the other language. Each locale's `README.md` is its entry point.
Add a new locale directory and a column here when extending the language pool.
Translate the supported topic completely, keeping API identifiers unchanged.

Update a paired topic in the same change: commands, defaults, limits, status and
evidence claims must agree. Verify facts against source/config first. Concise
guides link to detailed owners instead of copying their implementation history.
The root canonical hierarchy remains authoritative; localization does not move
ownership. An untranslated detailed reference must be labeled by language in
locale navigation. These directories localize documentation; they do not imply
that Studio's interface or MCP diagnostics have a language selector.

## Maintainer references

- [Architecture](../ARCHITECTURE.md) — Layer 1–4 ownership, runtime topology,
  production boundary, and compatibility namespaces.
- [CAD patterns](../CAD_PATTERNS.md) — verified KOMPAS COM/CAD behavior and
  reusable failure-prevention rules.
- Module development rules: [English](en/module-development.md) /
  [Русский](ru/module-development.md) — shared Studio/generator/MCP delivery,
  standard/custom inputs, reconstruction labels, previews, and rational parameterization.
- [Agent navigation map](agent-navigation.yaml) — compact file/symbol/test entry
  points for bounded repository navigation.
- Agreed development plans are indexed with an explicit planned status; they do
  not announce runtime capabilities. Unagreed drafts and raw investigation notes
  remain outside the public documentation tree.

The maintainer references are intentionally more detailed than the user guides.
Start with the relevant contract above instead of reading them front to back.

## What is not in this index

Unagreed roadmaps, work-process notes, raw audits, generated CAD, and disposable
probes are development material. Unfinished local work belongs in the ignored
`experiments/spikes/` quarantine and is not included in the package or MCP tool
catalog.
