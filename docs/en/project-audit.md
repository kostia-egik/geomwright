# Project audit — 2026-10-07

[Русский](../ru/project-audit.md) · [English index](README.md)

Main conclusion: Geomwright has useful boundaries between calculation, workflow
and COM, but several paths reported success incorrectly before this audit.
Confirmed defects were fixed without replacing the architecture for a different
directory layout.

## Bevel wheel and preview

The module builds one nominal straight bevel wheel using Tredgold projection,
not a gear pair. The COM-free calculation serves MCP, Studio and the CAD plan.

Fixed:

- The end contour intersects projection rays with the back cone. Previously it
  projected the tangent plane, distorting the contour away from the pitch generator.
- Repeating a tooth period no longer draws closing chords across each tooth.
  Tip-circle intersections use the segment/circle equation.
- The axial silhouette no longer draws an internal axis edge. It dimensions
  face width `b` and full envelope `B`, including the projecting inner rim corner.
- Rejected previews display reasons and disable CAD instead of entering the
  successful-result cache. Language switching preserves bevel-specific hints.
- Volume accounts for both end cones, both flat faces and loft-section margins.
  Scale integration along rays is analytical; sampled-contour integration is numerical.
- Nonfinite inputs, tooth heights, crossings and blank feasibility are checked.
  The CAD plan no longer repeats the complete calculation.
- Schema, calculation and hints agree on the back-extension default:
  `max(2 mm, 1.2 b sin δ)`. This is a blank heuristic, not a normative rack dimension.

For `m=3, z=20, δ=45°`: `dₑ=60 mm`, `dₐₑ≈64.243 mm`, `b≈12.092 mm`,
`B≈18.205 mm`, estimated volume `≈33433.499 mm³`.
Refining angular quadrature from 720 to 2880 samples changed volume by
0.0000873%. Measured median plan time after removing duplicate calculation was
0.127 s; one earlier measurement was 0.381 s. These are local measurements,
not a latency guarantee for every machine.

## Reliability and operation

- Failed preflight stops creation and subsequent readback.
- Bridge stdout/stderr are spooled to files, preventing pipe deadlocks on large
  output. Callback errors stop the runner-owned process; a nonzero exit cannot
  publish success. Progress is read incrementally.
- Failed saves do not close changed documents. An existing old file no longer
  proves save success. Shutdown does not quit with failed saves or open documents.
- Unknown explicit IDs do not select the active document; ambiguous names are
  refused. Unsaved `runtime_id` uses API7 Reference rather than collection
  position. Old `@document:N` IDs require a workspace refresh: an intentional
  rejection of unsafe fallback behavior.
- Studio validates local Host and Origin before route execution. Browser writes
  require same-origin; local programmatic clients without browser headers remain
  supported. This is not user authentication.
- Studio admits one CAD job at a time and retains up to 100 completed records.
  Create and update share admission/pruning; refused jobs allocate no extra thread.
- MCP uses the verified dependency range `>=1.27,<2`. CI and the local quality
  gate have independent deadlines; CI installs the built package. Empty JUnit
  failure messages no longer break report summarization.

## Architecture, structure and data

The four layers, isolated COM process, create-only limits and compatibility
facades provide practical value. A new queue service, universal operation graph
or wholesale namespace migration would not improve these fixes.

The bridge (about 31.6k lines), `parametric.py` (12.6k) and adapter (3.6k) remain
maintenance concentrations. Size alone does not make splitting them safe.
Extract independently owned behavior as it develops; do not mechanically
fragment the working dispatch.

Standards tables are available offline and reconstructed profiles are labelled.
This audit does not certify normative accuracy or rights to distribute source
materials. The timing-belt source URL pointing to `main` should be pinned to a
revision when its table is next updated.

Documentation now has aligned EN/RU introduction, setup, architecture,
development and bevel guides. Topic filenames match; another language is added
as a locale directory. Not all detailed historical pages are localized yet.
README and canonical architecture documents retain their ownership roles.

## Verification and readiness limits

Focused host checks cover geometry, schemas, HTTP, save lifecycle, bridge
subprocesses and preflight: 102 tests and 59 subtests passed in 18.80 s.
Wheel installation outside the checkout, packaged
assets, MCP registration, compilation, bridge-copy parity and diff were checked.
Studio was exercised in RU/EN for accepted and rejected input; screenshots were
visually inspected, not merely captured.

API7 Reference was read for three existing documents from two independent
processes; values agreed. Neighboring-document closure was tested with fakes,
not by closing user models. Reference is session-scoped, not a persistent ID
for the next KOMPAS launch.

Live bevel creation/save/reopen was not repeated after these fixes, nor was
every CAD family exercised. Installed-package smoke does not replace GitHub CI;
existing live examples do not prove every input combination.

Conclusion: suitable for nominal preview and a controlled create-only workflow.
A fresh live CAD acceptance run of the corrected plan is needed before release.
The module is not a gear-pair, contact, strength or manufacturing-surface
certification tool; those capabilities are outside its contract.
