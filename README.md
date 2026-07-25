# kompas-mcp

`kompas-mcp` is a local MCP server for inspecting and automating KOMPAS-3D on
Windows. It combines a Python MCP host with an isolated bridge executed by the
Python runtime bundled with KOMPAS.

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
| Native KOMPAS module inspection and command launching | research |

Generated CAD files and live readback artifacts are local evidence. They are
stored under `sample/generated/` and `sample/live_outputs/` and are intentionally
excluded from Git.

## Requirements

- Windows;
- KOMPAS-3D v23 with its runtime components installed;
- Python 3.11 or newer for the MCP host;
- an MCP-capable client.

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

The server entry point is:

```powershell
.\.venv\Scripts\python.exe -m kompas_mcp
```

Do not copy a user-specific absolute path from another machine. Point the MCP
client at the virtual environment inside its own clone. For example:

```json
{
  "mcp": {
    "kompas": {
      "type": "local",
      "command": [
        "C:\\path\\to\\kompas-mcp\\.venv\\Scripts\\python.exe",
        "-m",
        "kompas_mcp"
      ],
      "enabled": true,
      "timeout": 600000
    }
  }
}
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
src/kompas_mcp/                 MCP host, schemas, normalizers, and tool groups
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
- [Write operations and safety](docs/write_operations.md)

`docs/archive/` is reserved for intentionally retained historical records. Raw
backlogs and uncommitted research material stay in the ignored experiment
quarantine instead of the canonical documentation tree.

## Development policy

Keep production behavior, documentation, and live readback evidence aligned.
Do not commit generated CAD binaries, local MCP paths, embedded bridge payloads,
or disposable probe scripts. Repository-specific agent rules are defined in
`.opencode/AGENTS.md`.
