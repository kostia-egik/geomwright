# Repository agent rules

- Tests are allowed when they protect a stable production contract at reasonable
  maintenance cost. Prefer consolidating or replacing existing coverage over
  adding another file or parameter matrix.
- Do not add generated sample/dossier tests, one-test-per-helper coverage, or
  broad combinatorial suites. Run only the affected focused tests by default;
  require an explicit reason for a full-suite run.
- Use tests for deterministic host-side logic such as normalization, formulas,
  schemas, topology, and failure propagation. Verify COM/CAD behavior with
  compile, import, live KOMPAS, snapshot, and reopen/readback checks.
- Read `ARCHITECTURE.md` and `CAD_PATTERNS.md` before changing CAD runtime code.
- Keep `bridge/kompas_bridge.py` and
  `src/kompas_mcp/assets/bridge/kompas_bridge.py` byte-identical.
- Treat `README.md`, `ARCHITECTURE.md`, `CAD_PATTERNS.md`, and `docs/README.md` as
  the canonical documentation hierarchy. `docs/archive/` is historical only.
- Keep unfinished prototypes and one-off work briefs under the ignored
  `experiments/spikes/` quarantine. Do not expose them through the MCP server or
  tool catalog.
- Keep generated CAD files, local readback evidence, and disposable probe scripts
  out of commits. Canonical `.m3d` examples remain local under ignored sample
  output directories.
- Do not commit machine-specific `opencode.json` paths. Maintain
  `opencode.example.json` as the portable template.
- On Windows, use the Unicode-safe project path helper when shell tooling fails
  under the Cyrillic workspace path.
