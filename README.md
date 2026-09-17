# Geomwright

Local-first CAD automation for KOMPAS-3D, exposed as an MCP server and a small
browser-based Studio. Geomwright lets an AI agent or a local operator inspect a
model, plan a change, execute a bounded operation, and verify the result without
turning KOMPAS into an uncontrolled scripting target.

> Geomwright is an independent project. It is not affiliated with or endorsed
> by ASCON or the KOMPAS-3D product team.

## What you can do

- inspect KOMPAS documents, model trees, sketches, features, dimensions, and
  constraints;
- create and edit selected sketch and feature entities with explicit targets;
- preview and build supported parametric parts and spring families;
- preview and build managed V-belt, Poly-V, flat-belt, timing-belt, and selected
  roller/bush-chain transmission geometry;
- create specifications, relink assembly paths, run quality checks, and export
  safe working copies;
- use Geomwright Studio to preview transmission geometry and edit recognized
  managed blocks.

The public MCP surface is discovered at runtime. Call `get_mcp_tool_catalog`
from an MCP client instead of relying on an unversioned list copied into a
prompt.

## Current status

Version `0.1.0` is an alpha release. The core session, document, composition,
specification, relinking, and batch operations are the most stable parts. The
parametric, spring, sketch-write, and transmission families are usable only
within the scope stated by their contracts and live verification evidence.

| Area | Status | Notes |
| --- | --- | --- |
| Session and document lifecycle | Stable | Open, inspect, save, export, and close explicit documents |
| Composition, specifications, relinking, quality | Stable | Preview/apply workflows with bounded changes |
| Sketch and feature runtime | Experimental | Low-level tools; inspect before writing |
| Parametric parts and springs | Experimental | Family-specific parameters and verification |
| Geomwright Studio | Experimental | Local UI; no arbitrary-body write path |
| Native KOMPAS module inspection | Research-only | Disabled by default; explicit opt-in for local investigation |

An experimental status is a contract boundary, not a promise that every catalog
entry or CAD combination is supported. Missing standard data and failed
verification stop the operation before an unsafe write where possible.

## Requirements

- Windows;
- KOMPAS-3D v23 with its runtime components installed;
- Python 3.11 or newer for the host;
- an MCP-capable client for the agent interface.

The host Python and the KOMPAS bridge have separate compatibility constraints.
Normal package code follows `pyproject.toml`; the bridge must also run in the
Python runtime bundled with KOMPAS-3D v23.

## Install

From PowerShell in a clone:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui]"
```

The UI dependency group is optional. For MCP-only use:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Research-only native-module tools are intentionally absent from the default MCP
session. Enable them only in a disposable local investigation:

```powershell
$env:GEOMWRIGHT_ENABLE_RESEARCH_TOOLS = "1"
.\.venv\Scripts\python.exe -m geomwright
```

They are not covered by the stable product contract and can inspect installed
KOMPAS modules or launch explicitly requested commands.

## Run Studio

The easiest Windows path is:

```powershell
.\start-geomwright-studio.cmd
```

Or run it directly:

```powershell
.\.venv\Scripts\python.exe -m geomwright.studio --port 8765
```

Studio opens `http://127.0.0.1:8765` unless `--no-browser` is supplied. Start
KOMPAS first and keep it visible: Studio attaches to the already running
KOMPAS instance and never creates a hidden substitute session. It previews
geometry before a CAD job and only edits recognized managed blocks.

## Run the MCP server

```powershell
.\.venv\Scripts\python.exe -m geomwright
```

For an MCP client, use the Python executable inside that clone. The tracked
[`opencode.example.json`](opencode.example.json) shows the portable shape:

```json
{
  "mcp": {
    "geomwright": {
      "type": "local",
      "command": [
        "C:\\path\\to\\geomwright\\.venv\\Scripts\\python.exe",
        "-m",
        "geomwright"
      ],
      "enabled": true,
      "timeout": 600000
    }
  }
}
```

Do not commit a machine-specific copy of this file. The legacy commands
`kompas-mcp` and `kompas-mechanics-ui`, and the `kompas_mcp` import namespace,
remain as compatibility aliases. New integrations should use `geomwright` and
`geomwright.kompas`.

## First safe workflow

1. Call `get_mcp_tool_catalog` and choose a category whose status matches the
   task.
2. Call `get_session_state` and `list_documents`; always name the target
   document explicitly.
3. Use inspection, preview, and preflight tools before a write.
4. Follow **Plan → Execute → Verify → Correct**. A successful COM `Update()` is
   not, by itself, proof that geometry or direction is correct.
5. Save and reopen a model when the workflow contract requires persistence
   evidence. Keep generated files under ignored local output directories.

For sketch work, begin with `inspect_sketch_full`. For a parametric family,
begin with its preview operation and then read the family contract in `docs/`.

## Repository map

```text
src/geomwright/                 public application namespace and Studio
src/kompas_mcp/                 KOMPAS implementation and compatibility APIs
bridge/kompas_bridge.py         KOMPAS-side COM bridge
rules/                          tracked runtime rule data
docs/                           current user and maintainer contracts
sample/                         small runnable examples and request payloads
tests/                          deterministic host-side and contract tests
experiments/spikes/              ignored local quarantine for unfinished work
```

The root bridge and packaged bridge copy must remain byte-identical. Generated
CAD files, live readback dumps, local configuration, and disposable probes are
not part of the public repository.

## Documentation

- [Documentation index](docs/README.md) — choose a guide by task and audience;
- [Write operations and safety](docs/write_operations.md) — mutation rules;
- [Geomwright Studio](docs/geomwright-studio.md) — UI workflow and HTTP contract;
- [Parametric workflows](docs/parametric-workflows.md) — supported part families;
- [Spring workflows](docs/spring-workflows.md) — spring-family navigation;
- [Transmission contracts](docs/transmission-platform-concept.md) — pulley and
  sprocket boundaries;
- [Architecture](ARCHITECTURE.md) — layer ownership for maintainers;
- [CAD patterns](CAD_PATTERNS.md) — verified KOMPAS-specific invariants.

## License

Geomwright is released under the [MIT License](LICENSE).

See [CONTRIBUTING.md](CONTRIBUTING.md) for development boundaries and
[SECURITY.md](SECURITY.md) for safe local operation and vulnerability reports.
