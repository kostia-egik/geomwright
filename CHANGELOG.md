# Changelog

## Unreleased

- Added the `gear_internal` Studio module: an internal spur/helical ring gear
  with an explicit ring blank outside diameter, ГОСТ 19274-73 nominal geometry,
  span/constant-chord/over-pin controls, and a live-verified create-only
  managed CAD part with a checksummed recipe.
- Exposed the internal gear in the public MCP catalog with
  `preview_internal_gear`, `create_internal_gear`, and `inspect_internal_gear`.
- Added the `gear_internal` block recognition and Studio end/side views; the
  side view shows the through-bore window of the ring.
- Added the `gear_spur` Studio module: an external cylindrical spur/helical
  gear with a nominal involute/trochoid sector preview, control measurements,
  and a live-verified create-only managed CAD part.
- Extended the basic-rack catalog with ГОСТ 9587-81 (small module),
  ГОСТ Р 50531-93 (high stress), and ISO 53:1998 with ISO 54:1996 module rows,
  including module-range diagnostics.
- Cached the ГОСТ 2475-88, ГОСТ 25255-82, and ГОСТ 22696-77 wire/roller
  diameter rows and wired the over-pin input to the nearest fitting standard
  pin.
- Exposed the cylindrical gear in the public MCP catalog with
  `list_gear_standards`, `preview_cylindrical_gear`, `create_cylindrical_gear`,
  and `inspect_cylindrical_gear`.
- Separated the basic-rack standard from its contour modification: module and
  coefficient fields follow the standard selection, and free input is reserved
  for the user-defined modification.
- Built the CAD flank from smooth cubic Bézier-NURBS curves split at the form
  point instead of dense segment chains; recorded `CURVE-002` and updated
  `OP-004`.
- Added gear taxonomy, RU/EN form text, workspace block labels, and the gear
  icon.
- Persisted a checksummed chain-sprocket recipe so saved roller/bush sprocket
  blocks restore their designation, chain type, tooth count, row count and
  tooth-gap variant in Studio for a new build.
- Exposed the chain sprocket in the public MCP catalog with
  `list_chain_profiles`, `preview_chain_sprocket`, `create_chain_sprocket` and
  `inspect_chain_sprocket`.
- Aligned the silent-chain Studio descriptor with its documented preview-only
  status (`build=false`).

## 0.1.0 — initial public release

- Local MCP server for KOMPAS-3D document lifecycle, inspection, controlled
  edits, specifications, relinking, and quality workflows.
- Parametric part and spring-family workflows with previews and readback
  contracts.
- Geomwright Studio for local previews and managed pulley/sprocket workflows.
- Isolated KOMPAS bridge with explicit write confirmation and reusable CAD
  verification patterns.

This release is alpha quality. See the capability status in the README and the
specialized contracts in `docs/` before using a workflow in production.
