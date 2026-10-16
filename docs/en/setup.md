# Install and run Geomwright

[Русский](../ru/setup.md) · [English index](README.md) · [Canonical README](../../README.md)

## Requirements

Use Windows, KOMPAS-3D v23 and Python 3.11 or newer. MCP requires an MCP-capable
client; Studio additionally requires the `ui` dependency group. The package is
alpha and currently depends on `mcp>=1.27,<2`.

Run the following in PowerShell from the clone:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui]" pywin32
$env:KOMPAS_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
$env:KOMPAS_REQUIRE_VISIBLE = "1"
```

For MCP only, replace `".[ui]"` with `.`. Host and bridge may use separate
interpreters: `KOMPAS_PYTHON` must name a modern Windows Python executable with
`pywin32`. The legacy bundled Python 3.2 cannot parse the current bridge. Set the
path explicitly for a portable installation. The priority is constructor argument,
`KOMPAS_PYTHON`, an existing checkout-owned `.venv/cad-bridge/Scripts/python.exe`,
then the KOMPAS SDK fallback. The last option may be too old and is not silently
replaced when an explicit setting is invalid.

Production bridge calls use a COM-free compile/import preflight with a five-second
deadline before the CAD process launches. Only successful validation is cached;
changed interpreter/bridge/runtime-file signatures invalidate it. A local
`CAD_RUNTIME_INVALID` failure does not quarantine the CAD session. Custom bridge
scripts retain their independent execution contract.

Open KOMPAS first and keep it visible. `KOMPAS_REQUIRE_VISIBLE=1` makes MCP
attach to that instance; Studio always requires a visible session for CAD jobs.
Preview-only calculation does not require COM.

## Studio

Environment set only in an MCP client's configuration does not reach a separately
launched Studio. Set `KOMPAS_PYTHON` in Studio's launching terminal/service, or use
the checkout-owned CAD venv above. Runtime selection code participates in Studio's
content fingerprint along with the selected interpreter path, so an old server
is not reused after a runner-code or launch-environment change.

For a terminal you control, use `start-geomwright-studio.cmd` or:

```powershell
.\.venv\Scripts\python.exe -m geomwright.studio --port 8765
```

For an agent or unattended launch:

```powershell
.\.venv\Scripts\python.exe -m geomwright.studio --background --no-browser --startup-timeout 15
```

The background launcher checks `/health`, returns URL/PIDs and writes logs under
`%LOCALAPPDATA%\Geomwright\studio` by default (`--log-dir` overrides it).
The default URL is `http://127.0.0.1:8765`. Inspect the reported stderr log after
startup failure. Do not launch through an agent's PowerShell `Start-Process` or
wrap this persistent server in `scripts/run_bounded.py`.

## MCP

Configure the client to run the clone's Python with `-m geomwright` over stdio.
Use [opencode.example.json](../../opencode.example.json) for the OpenCode local
server shape; replace its placeholder paths and persist both environment
variables in `environment`. Other clients may use different configuration keys.
Keep machine-specific configuration local. A stdio server waits for its client;
it does not serve a browser page.

After connecting, call `get_mcp_tool_catalog`, `get_session_state` and
`list_documents`. Select the document explicitly before model operations.
Legacy CLI/import aliases remain available; new integrations use `geomwright`
and `geomwright.kompas`. Research tools require the explicit
`GEOMWRIGHT_ENABLE_RESEARCH_TOOLS=1` opt-in before server startup.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Bridge Python missing, `SyntaxError` or `CAD_RUNTIME_INVALID` | Absolute `KOMPAS_PYTHON` path, modern interpreter, `pywin32` in that interpreter; preflight does not access CAD |
| No visible KOMPAS session | Start v23 before the CAD job; check session state |
| Studio import fails | Install `.[ui]` using the same Python that launches Studio |
| Client keeps the old environment | Save variables in client configuration and restart the MCP server |
| `CAD_BUSY` | Let the current bridge call finish before retrying; overlapping bridge calls are refused |
| Job times out | Read the reported checkpoint/logs and inspect the document before retrying a write |

Use the [development guide](development.md) for bounded finite checks and
the [Studio contract](../geomwright-studio.md) for job/save/close behavior.
