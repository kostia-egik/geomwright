# Spring Size Catalogs

Spring catalogs are a selection layer above the existing parametric spring
generators. A catalog entry resolves to ordinary scenario params and then uses
the same preview/create path as manually supplied parameters.

## Current Catalogs

### `compression_metric_preferred_v1`

- `spring_type`: `compression_spring`
- `source_kind`: `project_seed_catalog`
- `standard_family`: `metric_preferred_stock_grid`
- entries: `16`

This catalog is a compact preferred metric stock-size seed for CAD selection and
workflow integration. It is intentionally not labelled as an official GOST/DIN
table. Before production release against a specific standard or supplier,
replace or extend the entries with sourced rows and keep the source metadata
attached to the catalog.

Each entry resolves to these generator fields:

- `wire_diameter`
- `outer_diameter`
- `standard_length`
- `working_turns`
- `end_turns_per_side`
- `ground_turns_per_side`
- `catalog_id`
- `catalog_entry_id`

The compression spring normalizer derives construction height, pitch, total
turns, end contracts, variables, and operation plans from the same code path used
by `preview_compression_spring`.

### `extension_metric_preferred_v1`

- `spring_type`: `extension_spring`
- `source_kind`: `project_seed_catalog`
- `standard_family`: `metric_preferred_stock_grid`
- entries: `13`

This catalog covers the stabilized extension spring generator and uses symmetric
hook selections from the completed hook mechanics work. It includes common
machine/open/center-loop entries plus two mechanics-coverage entries for
`self_wrapping_hooks` and `bent_coil_left_spike`.

Each entry resolves to these generator fields:

- `wire_diameter`
- `outer_diameter`
- `height`
- `turns`
- `pitch`
- `hook_type`
- `catalog_id`
- `catalog_entry_id`

The extension spring preview/create path still owns all hook construction,
side-selection metadata, native fillets, profile anchors, and live CAD readback.
Catalog rows only choose parameter sets.

## Tools

Use the catalog tools in this order:

1. `list_spring_size_catalogs`
2. `validate_spring_size_catalogs`
3. `find_spring_sizes`
4. `recommend_spring_sizes`
5. `resolve_spring_size`
6. `preview_spring_from_size` for a catalog-to-preview check.
7. `create_spring_from_size` for direct CAD creation, or use the returned
   `scenario` and `params` with the matching preview/create tool or generic
   part-scenario path.

`resolve_spring_size` can also return `include_preview=True` for a one-step
catalog-to-preview check.

`find_spring_sizes` is an exact filter. `recommend_spring_sizes` ranks nearest
entries by normalized dimensional deltas. A score of `0.0` is an exact match;
larger scores mean a larger average relative mismatch across the requested
target fields. Use `target_length` as a generic length target, or
`target_standard_length` / `target_height` when the spring type is already known.

Example recommendation query:

```json
{
  "spring_type": "extension_spring",
  "target_wire_diameter": 2.0,
  "target_outer_diameter": 24.0,
  "target_length": 90.0,
  "hook_type": "self_wrapping_hooks",
  "limit": 3
}
```

Example resolved params:

Compression spring:

```json
{
  "wire_diameter": 3.0,
  "outer_diameter": 30.0,
  "standard_length": 100.0,
  "working_turns": 9.0,
  "end_turns_per_side": 0.75,
  "ground_turns_per_side": 0.75,
  "catalog_id": "compression_metric_preferred_v1",
  "catalog_entry_id": "cmp-metric-030-300-100-medium"
}
```

Extension spring:

```json
{
  "wire_diameter": 2.0,
  "outer_diameter": 24.0,
  "height": 90.0,
  "turns": 7.0,
  "pitch": 10.0,
  "hook_type": "self_wrapping_hooks",
  "catalog_id": "extension_metric_preferred_v1",
  "catalog_entry_id": "ext-metric-020-240-090-self-wrapping-medium"
}
```

## Verification

Current non-test verification checks:

- `validate_spring_size_catalogs(include_preview=True)` returns `ok=True`;
- all `29` catalog entries resolve and preview through their existing scenario
  generator;
- `recommend_spring_sizes` ranks exact and nearest dimensional matches with
  deterministic score ordering;
- external supplier-style JSON example merges with built-ins as `3` catalogs / `30`
  entries and resolves through the same preview path;
- direct `create_spring_from_size` call for `cmp-metric-016-160-050-medium`
  builds live CAD with contour `5/5/5`;
- compression sample `cmp-metric-030-300-100-medium` builds live CAD with
  contour `5/5/5`;
- extension samples `ext-metric-020-200-080-machine-medium`,
  `ext-metric-020-240-090-bent-coil-medium`, and
  `ext-metric-020-240-090-self-wrapping-medium` build live CAD with contours
  `5/5/5`, `3/3/3`, and `17/17/17` respectively.

## Extension Points

Add new catalog families by extending `spring_catalog.py` with another
`SpringCatalog` and entries. Keep these fields explicit:

- `spring_type`: generator scenario name.
- `standard_family`: standard or supplier family identifier.
- `source_kind`: `official_standard`, `supplier_catalog`, `project_seed_catalog`,
  or another explicit source class.
- `source_note`: where the data came from and any limitations.

Do not encode official-standard rows without source metadata. Catalog rows should
be auditable independently from the CAD mechanics.

## External JSON Catalogs

Load sourced catalogs from either:

- `KOMPAS_MCP_SPRING_CATALOG_DIR` environment variable; or
- `catalog_dir` argument accepted by all catalog tools.

The loader reads `*.json` files from that directory and merges them with the
built-in catalogs. It rejects duplicate catalog or entry ids and exposes parse or
schema errors through `errors`; external rows never silently override built-ins.

Use [spring-catalog-supplier-example.json](examples/spring-catalog-supplier-example.json)
as the file-shape reference. A file can contain one catalog object or an envelope
with a `catalogs` array. Each catalog requires `id`, `spring_type`, `title`,
`standard_family`, `source_kind`, `source_note`, and non-empty `entries`.

Each entry requires `id`, `title`, `load_class`, and `params`. The loader assigns
`catalog_id` and `catalog_entry_id` to resolved params, so catalog provenance
survives preview and create calls.
