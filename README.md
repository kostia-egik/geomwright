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
- preview and build managed V-belt, Poly-V, flat-belt, timing-belt, selected
  roller/bush-chain transmission geometry, an external cylindrical gear
  (spur or helical) with a nominal rack-generated profile, and an internal
  ring gear with an explicit blank outside diameter;
- preview and build straight-sided spline shafts and hubs per ГОСТ 1139-80
  with the standard size catalog, centering methods, and ГОСТ 25346 fits;
- create specifications, relink assembly paths, run quality checks, and export
  safe working copies;
- use Geomwright Studio to preview transmission geometry and edit recognized
  managed blocks, or calculate and build one create-only cam without shaft/hub/bore.
  Cam recipes persist in new models: restore a Studio form for a new build or read
  the recipe through MCP `inspect_cam`; engineering limits do not inherit CAD slack.

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
| Cylindrical gear | Experimental, live-verified | External spur/helical gear; ГОСТ 13755-2015, ГОСТ 9587-81, ГОСТ Р 50531-93 and ISO 53:1998 contours; nominal preview, create-only managed part, MCP tools |
| Internal gear | Experimental, live-verified | Internal spur/helical ring gear; explicit blank outside diameter, ГОСТ 19274-73 nominal geometry, create-only managed part, MCP tools |
| Straight-sided splines | Experimental, live-verified | ГОСТ 1139-80 light/medium/heavy catalog, exact end profile and ГОСТ 25346 fits; create-only managed shaft and hub parts, Studio modules and MCP tools |
| Cam profiles | Experimental | Shared Studio/MCP create-only build, native curve/contact and solid readback |
| Silent-chain sprockets | Experimental, live-verified | Shared Studio/MCP calculation and new-part creation; solid blank, DIN NURBS, saved recipe inspection |
| Native KOMPAS module inspection | Research-only | Disabled by default; explicit opt-in for local investigation |

An experimental status is a contract boundary, not a promise that every catalog
entry or CAD combination is supported. Missing standard data and failed
verification stop the operation before an unsafe write where possible.

## Requirements

- Windows;
- KOMPAS-3D v23 with its runtime components installed;
- Python 3.11 or newer for the host;
- an MCP-capable client for the agent interface.

The host Python and the KOMPAS bridge can use separate interpreters. The bridge
needs a modern Windows Python with `pywin32`; the old bundled Python 3.2 cannot
run the current source. Prefer a standard Python installation for the CAD runtime.

## Install

From PowerShell in a clone:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui]"
```

Configure the CAD interpreter before starting Studio or MCP. If the project
interpreter is a standard Windows Python, it can run both host and bridge:

```powershell
.\.venv\Scripts\python.exe -m pip install pywin32
$env:KOMPAS_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
$env:KOMPAS_REQUIRE_VISIBLE = "1"
```

Alternatively point `KOMPAS_PYTHON` at a separate Python with `pywin32` installed.
Use an actual interpreter path rather than a bare execution alias.
`KOMPAS_REQUIRE_VISIBLE=1` makes
MCP attach to the already running visible KOMPAS instead of starting a COM server.
Cam creation requires this running session. For an MCP client, put these variables
in the local server's `environment` configuration so a restart preserves them.

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

Or run it in a terminal you control (foreground; keep that terminal open):

```powershell
.\.venv\Scripts\python.exe -m geomwright.studio --port 8765
```

For an agent or an unattended session, use the bounded background launcher:

```powershell
.\.venv\Scripts\python.exe -m geomwright.studio --background --no-browser --startup-timeout 15
```

It launches without a console window, closes stdin, redirects output to unique
log files, checks the new instance's `/health`, and returns its URL and PIDs.
Logs default to local Geomwright state (`%LOCALAPPDATA%\Geomwright\studio` on
Windows); override with `--log-dir`. Startup failure reports the stderr path
and stops only the newly launched process tree. Do not use PowerShell
`Start-Process` to launch Studio through an agent terminal tool.

For potentially blocking **finite** commands, use the independent watchdog:

```powershell
.\.venv\Scripts\python.exe scripts/run_bounded.py --timeout 30 -- .\.venv\Scripts\python.exe -m pytest tests/test_bridge_runner.py -q
```

The watchdog returns exit code `124` on timeout, closes stdin, captures bounded
output through files, and stops owned descendants. On Windows it uses a Job
Object plus cleanup of the launcher tree; it does not rely on the terminal tool's
timeout message. Never wrap Studio `--background` or another persistent server
in this watchdog: it cleans descendants even when the command finishes normally.

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
      "environment": {
        "KOMPAS_PYTHON": "C:\\path\\to\\geomwright\\.venv\\Scripts\\python.exe",
        "KOMPAS_REQUIRE_VISIBLE": "1"
      },
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
- [Camshaft calculation and CAD](docs/en/camshaft.md) / [Кулачки ГРМ](docs/ru/camshaft.md) —
  timing conventions, strict CAD checks, recipe reuse, recovery, and reference data;
- [Write operations and safety](docs/write_operations.md) — mutation rules;
- [Geomwright Studio](docs/geomwright-studio.md) — UI workflow and HTTP contract;
- [Parametric workflows](docs/parametric-workflows.md) — supported part families;
- [Spring workflows](docs/spring-workflows.md) — spring-family navigation;
- [Transmission contracts](docs/transmission-platform-concept.md) — pulley,
  sprocket, and gear boundaries;
- [Cylindrical gear](docs/gear-spur.md) — inputs, rack standards, pin rows,
  nominal representation, create-only CAD, and live evidence;
- [Internal gear](docs/gear-internal.md) — ring blank input, ГОСТ 19274-73
  geometry, controls, create-only CAD, and live evidence;
- [Architecture](ARCHITECTURE.md) — layer ownership for maintainers;
- [CAD patterns](CAD_PATTERNS.md) — verified KOMPAS-specific invariants.

## License

Geomwright is released under the [MIT License](LICENSE).

See [CONTRIBUTING.md](CONTRIBUTING.md) for development boundaries and
[SECURITY.md](SECURITY.md) for safe local operation and vulnerability reports.
