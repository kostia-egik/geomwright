# Contributing to Geomwright

Thanks for helping improve Geomwright. The project is a Windows-first CAD
integration, so contributions are most useful when they include a clear
contract, a bounded failure mode, and evidence for any KOMPAS-specific claim.

Practical development guides: [English](docs/en/development.md) /
[Русский](docs/ru/development.md). This file owns contribution policy.

## Before opening a change

1. Read [the architecture](ARCHITECTURE.md) and the relevant [CAD pattern](CAD_PATTERNS.md).
2. Decide whether the change is a Layer 1 tool, Layer 2 rule, Layer 3 workflow,
   or Layer 4 model family.
3. Before creating or substantially extending a complete CAD module, follow the
   [module development rules](docs/en/module-development.md)
   ([Русский](docs/ru/module-development.md)) and the family contract. The rules
   own delivery criteria, custom inputs, reconstruction labels, previews, and
   rational parameterization; existing capabilities remain family-specific.
4. Keep experimental work in `experiments/spikes/`. That directory is ignored
   and is not part of the package or MCP catalog.

## Local checks

Create an environment and install the package with its optional Studio
dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui]" pytest
.\scripts\check_change.ps1 -TestPath tests/test_bridge_runner.py -TimeoutSeconds 60
```

Choose the test file affected by your change; the bridge runner above is an
example. The gate checks diff whitespace, bridge parity, compilation and tracked
machine paths, and runs the selected tests through `scripts/run_bounded.py`.
Use `-Keyword` to narrow the test selection and `-Packaging` for a wheel check.
Run `-Full` only when the change has a documented need for the entire suite.
Each finite subprocess receives the `-TimeoutSeconds` deadline (default 600).
Run a persistent Studio server with `--background --no-browser`, outside this
watchdog; see [setup](docs/en/setup.md).

The test suite covers deterministic host-side behavior. KOMPAS COM behavior
also needs a live KOMPAS-3D v23 check, including readback and save/reopen when
the affected workflow claims that level of support.

Host tests must not touch the running CAD session. `tests/conftest.py` blocks
the real bridge for the entire pytest process, including background jobs. A
swallowed bridge exception still fails the session. Inject a fake adapter into
`create_app` before testing confirmed CAD-job routes, and wait for the fake job
to finish. Live KOMPAS checks run separately and must name the target and obtain
write confirmation; they are not part of the default test suite.

## Pull requests

- Explain the user-facing behavior and the affected MCP/Studio contract.
- Update the canonical documentation when a status, parameter, or workflow
  changes.
- Update both EN/RU guides when a shared topic changes; use the locale ownership
  rules in [the documentation index](docs/README.md).
- Do not commit `.m3d` files, live readback dumps, local paths, credentials, or
  disposable probe scripts.
- Keep the two bridge copies byte-identical:
  `bridge/kompas_bridge.py` and
  `src/kompas_mcp/assets/bridge/kompas_bridge.py`.
- Keep research-only native-module tools behind the explicit
  `GEOMWRIGHT_ENABLE_RESEARCH_TOOLS=1` opt-in.
- Add or update focused tests for deterministic logic; avoid generated or
  combinatorial test matrices.

## Scope of the public repository

The repository contains the Geomwright runtime, KOMPAS bridge, maintained
examples, tests, and current contracts. Local operator configuration, agent
instructions, roadmaps, raw research notes, and live CAD evidence are
development material and stay outside the public tree.
