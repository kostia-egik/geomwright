# Changelog

## Unreleased

- Added the `gear_spur` Studio module: an external cylindrical spur gear with a
  nominal involute/trochoid sector preview, control measurements, and a
  live-verified create-only managed CAD part.
- Separated the basic-rack standard from its contour modification: module and
  coefficient fields follow the standard selection, and free input is reserved
  for the user-defined modification.
- Built the CAD flank from smooth cubic Bézier-NURBS curves split at the form
  point instead of dense segment chains; recorded `CURVE-002` and updated
  `OP-004`.
- Added gear taxonomy, RU/EN form text, workspace block labels, and the gear
  icon.
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
