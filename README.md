# Geomwright

Geomwright is a local-first system for inspecting, creating, and rebuilding CAD
models through deterministic modules, a standalone Studio UI, and an optional
MCP interface for AI agents. Its first CAD adapter targets KOMPAS-3D on Windows
through an isolated bridge executed by the Python runtime bundled with KOMPAS.

The project supports document lifecycle operations, model-tree and sketch
inspection, controlled sketch/feature edits, specifications, parametric part
workflows, spring families, and live CAD verification. Native KOMPAS module
inspection is available as a separate research surface.

## Status

The runtime catalog is the source of truth for the exposed MCP surface. Call
`get_mcp_tool_catalog` to discover current tools and their stability level.

| Area | Status |
| --- | --- |
| Session/document lifecycle, composition, specifications, relinking | stable |
| Low-level sketch and feature runtime | experimental |
| Parametric part and spring generation | experimental |
| Geomwright Studio (V-belt and Poly-V) | experimental, managed CAD creation |
| Native KOMPAS module inspection and command launching | research |

Generated CAD files and live readback artifacts are local evidence. They are
stored under `sample/generated/` and `sample/live_outputs/` and are intentionally
excluded from Git.

## Requirements

- Windows;
- KOMPAS-3D v23 with its runtime components installed;
- Python 3.11 or newer for the MCP host;
- an MCP-capable client when using the agent interface.

Building or inspecting native modules additionally requires the matching KOMPAS
SDK/toolchain; ordinary managed workflows do not.

The host package and the KOMPAS bridge have different compatibility constraints:
ordinary package code may use the Python version declared in `pyproject.toml`,
while `bridge/kompas_bridge.py` must remain compatible with the Python runtime
bundled with KOMPAS-3D v23.

## Installation

From a PowerShell prompt in a local clone:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

For a one-click local launch, double-click `start-geomwright-studio.cmd` in the
repository root. On its first run the launcher creates `.venv`, installs the UI
dependencies, starts the localhost server, and opens the browser automatically.
Keep the launcher window open while using Geomwright Studio.

For a manual or developer installation:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ui]"
.\.venv\Scripts\python.exe -m geomwright.studio --port 8765
```

The command also opens `http://127.0.0.1:8765` automatically; pass
`--no-browser` when running it under a supervisor. Studio attaches to an already
running visible KOMPAS instance, previews V-belt and Poly-V profiles, creates
owned managed pulleys, and rebuilds recognized blocks through confirmed CAD
jobs. It never starts a hidden KOMPAS process.

The server entry point is:

```powershell
.\.venv\Scripts\python.exe -m geomwright
```

Do not copy a user-specific absolute path from another machine. Point the MCP
client at the virtual environment inside its own clone. For example:

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

The distribution, product, and public application namespace are named
`geomwright`. The canonical KOMPAS MCP bootstrap and public adapter/catalog
facades live under `geomwright.kompas`; implementation modules remain under
`kompas_mcp` during the compatibility migration. Legacy `kompas-mcp`,
`kompas-mechanics-ui`, `kompas_mcp.server`, `kompas_mcp.studio`, and
`kompas_mcp.mechanics.ui` entry points continue to work and share the canonical
MCP registry. New integrations should use `geomwright-mcp`,
`geomwright-studio`, `python -m geomwright`, `geomwright.kompas`, or
`geomwright.studio`.

An existing development environment may still list the former distribution
after the first Geomwright install. It can be removed and the editable package
refreshed without changing the `kompas_mcp` import namespace:

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y kompas-mcp
.\.venv\Scripts\python.exe -m pip install -e ".[ui]"
```

Keep machine-specific MCP configuration and absolute paths out of commits.
[`opencode.example.json`](opencode.example.json) is the tracked template; copy it
to `opencode.json`, replace the placeholder path, and restart OpenCode so the
project configuration is reloaded.

## First workflow

1. Call `get_mcp_tool_catalog` and select tools by stability and purpose.
2. Use `get_session_state` and `list_documents` before opening or modifying a
   model.
3. Prefer readback and preview tools before write operations.
4. Use the Plan → Execute → Verify → Correct pattern for geometry changes.
5. Save generated evidence to the ignored sample output directories, not beside
   source files.

For sketch authoring, start with `inspect_sketch_full`; for parametric generation,
start from the preview operation for the relevant workflow or spring family.

## Repository layout

```text
src/geomwright/                 public app namespace, KOMPAS bootstrap, and Studio UI
src/kompas_mcp/                 KOMPAS implementation modules and compatibility APIs
bridge/kompas_bridge.py         KOMPAS-side bridge source
src/kompas_mcp/assets/bridge/   packaged bridge copy; must match the root bridge
docs/                           canonical contracts, workflows, and research notes
sample/                         maintained examples plus ignored local evidence
rules/                          tracked runtime rule data
experiments/spikes/             ignored local quarantine for unfinished prototypes
```

## Documentation

- [Documentation index](docs/README.md)
- [Architecture and ownership](ARCHITECTURE.md)
- [Reusable CAD patterns](CAD_PATTERNS.md)
- [Parametric workflows](docs/parametric-workflows.md)
- [Sketch authoring protocol](docs/sketch-authoring-agent-protocol.md)
- [Spring workflows](docs/spring-workflows.md)
- [Geomwright Studio](docs/geomwright-studio.md)
- [Write operations and safety](docs/write_operations.md)

`docs/archive/` is reserved for intentionally retained historical records. Raw
backlogs and uncommitted research material stay in the ignored experiment
quarantine instead of the canonical documentation tree.

## Development policy

Keep production behavior, documentation, and live readback evidence aligned.
Do not commit generated CAD binaries, local MCP paths, embedded bridge payloads,
or disposable probe scripts. Repository-specific agent rules are defined in
`.opencode/AGENTS.md`.
