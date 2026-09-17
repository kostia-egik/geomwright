# Security policy

Geomwright is designed to run locally and can modify KOMPAS-3D documents. Treat
the MCP client, the local host, and the KOMPAS session as one trusted boundary.
Do not expose the server to an untrusted network without adding an explicit
authentication and authorization layer.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository when it
is available. Do not open a public issue containing credentials, local paths,
model files, or a working exploit.

When reporting, include the affected version or commit, the smallest
reproduction, the expected and actual behavior, and whether a live KOMPAS
document can be modified without an explicit write confirmation.

## Operational safeguards

- Keep `opencode.json` and other machine-specific configuration untracked.
- Never place tokens, passwords, or model files in issues, logs, or examples.
- Prefer preview, preflight, and readback operations before CAD writes.
- Keep research-only native-module commands disabled unless they are explicitly
  needed for local investigation.
