# Development and validation

[Русский](../ru/development.md) · [English index](README.md) · [Contribution policy](../../CONTRIBUTING.md)

## Prepare a change

Read [architecture](architecture.md), the relevant [CAD patterns](../../CAD_PATTERNS.md)
and the family contract. Assign the change to L1–L4 and keep geometry, workflow,
bridge and presentation ownership distinct. Inspect `git status` before editing
and preserve unrelated changes. Keep disposable probes in ignored
`experiments/spikes/`; do not expose unfinished modules through MCP.

For a new or substantially extended complete CAD module, follow the
[module development rules](module-development.md) before implementation. They
define the shared Studio/generator/MCP contract and completion criteria, including
custom inputs, reconstruction labels, technical previews, and rational parameterization.

From PowerShell in the clone:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui]" pytest
```

CAD checks also need the interpreter/session configuration in [setup](setup.md).

## Focused checks

Select the tests affected by the change; this bridge test is an example:

```powershell
.\scripts\check_change.ps1 -TestPath tests/test_bridge_runner.py -TimeoutSeconds 60
```

The gate checks `git diff --check`, bridge-copy parity, selected module compilation,
tracked machine-path/key markers and focused tests. `-Keyword` narrows pytest;
`-Packaging` builds a wheel. `-Full` opts into the full suite when justified and
writes summaries under `test-results/`. The default per-subprocess deadline is
600 seconds, overridden by `-TimeoutSeconds`; it is not a total gate deadline.

For another finite command:

```powershell
.\.venv\Scripts\python.exe scripts/run_bounded.py --timeout 60 -- .\.venv\Scripts\python.exe -m pytest tests/test_bridge_runner.py -q
```

The watchdog closes stdin, captures output and stops owned descendants; timeout
returns 124. Never wrap a persistent background server in it. For Studio use
`python -m geomwright.studio --background --no-browser` as described in setup.

## Evidence appropriate to the change

Deterministic host logic needs focused tests for meaningful contracts: formulas,
normalization, topology, schemas and error propagation. Consolidate existing
coverage; avoid generated samples and broad combinatorial matrices.

Host pytest must not access live CAD. The guard in `tests/conftest.py` blocks real
bridge calls, including background jobs. Inject fake adapters for Studio routes
and wait for their jobs to complete. COM behavior needs separate live checks:
compile/import, explicit target and write confirmation, snapshot/readback,
save/reopen and visual evidence where the contract needs it. Label evidence as
source-backed, host-tested or live-verified; never infer live success from pytest.

## Documentation and packaging

Update the detailed owning contract and both EN/RU guides in the same change.
Follow [locale ownership](../README.md#languages-and-ownership); keep API names,
defaults, limitations and evidence levels synchronized. Link to long references
instead of translating their entire implementation history.

Keep `bridge/kompas_bridge.py` and its packaged copy byte-identical. Verify assets
when changing packaging. Exclude generated CAD, readback dumps, credentials,
machine-specific `opencode.json` and disposable scripts from commits. Review the
final diff and report verification gaps explicitly.
