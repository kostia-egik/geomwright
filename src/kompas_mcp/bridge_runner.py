from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_KOMPAS_PYTHON = Path(r"C:\ProgramData\ASCON\KOMPAS-3D\23\Python 3\App\python.exe")
CHECKOUT_BRIDGE_SCRIPT = Path(__file__).resolve().parents[2] / "bridge" / "kompas_bridge.py"
PACKAGED_BRIDGE_SCRIPT = Path(__file__).resolve().parent / "assets" / "bridge" / "kompas_bridge.py"


def default_bridge_script_path() -> Path:
    if CHECKOUT_BRIDGE_SCRIPT.exists():
        return CHECKOUT_BRIDGE_SCRIPT
    return PACKAGED_BRIDGE_SCRIPT


DEFAULT_BRIDGE_SCRIPT = default_bridge_script_path()


class BridgeError(RuntimeError):
    pass


class BridgeRunner:
    def __init__(
        self,
        kompas_python: str | None = None,
        bridge_script: str | None = None,
    ) -> None:
        self.kompas_python = Path(kompas_python or os.environ.get("KOMPAS_PYTHON") or DEFAULT_KOMPAS_PYTHON)
        self.bridge_script = Path(bridge_script or os.environ.get("KOMPAS_BRIDGE_SCRIPT") or default_bridge_script_path())

    def call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}

        if not self.kompas_python.exists():
            raise BridgeError(f"KOMPAS Python not found: {self.kompas_python}")
        if not self.bridge_script.exists():
            raise BridgeError(f"Bridge script not found: {self.bridge_script}")

        temp_root = os.environ.get("KOMPAS_MCP_TEMP_DIR", r"C:\Windows\Temp")
        with tempfile.TemporaryDirectory(prefix="kompas-mcp-", dir=temp_root) as temp_dir:
            request_path = Path(temp_dir) / "request.json"
            response_path = Path(temp_dir) / "response.json"
            request_path.write_text(
                json.dumps({"action": action, "payload": payload}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            env = os.environ.copy()
            kompas_python_dir = str(self.kompas_python.parent)
            env["PATH"] = kompas_python_dir + os.pathsep + env.get("PATH", "")

            completed = subprocess.run(
                [str(self.kompas_python), str(self.bridge_script), str(request_path), str(response_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                check=False,
            )

            if not response_path.exists():
                raise BridgeError(completed.stderr.strip() or "Bridge did not produce a response file")

            try:
                envelope = json.loads(response_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise BridgeError(f"Invalid bridge response JSON: {exc}") from exc
            if not isinstance(envelope, dict):
                raise BridgeError(f"Bridge response must be an object, got {type(envelope).__name__}")
            if envelope.get("ok"):
                if "data" not in envelope:
                    raise BridgeError("Bridge response missing data")
                data = envelope["data"]
                if not isinstance(data, dict):
                    raise BridgeError(f"Bridge response data must be an object, got {type(data).__name__}")
                return data

            error = envelope.get("error") or {}
            message = (
                error.get("message")
                if isinstance(error, dict)
                else str(error)
            ) or completed.stderr.strip() or "Unknown bridge error"
            raise BridgeError(message)
