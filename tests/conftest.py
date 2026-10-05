"""Host tests must never launch the real KOMPAS bridge, including in threads."""
from __future__ import annotations

import os
import threading
from functools import wraps
from pathlib import Path

import pytest

from kompas_mcp.bridge_runner import (
    BridgeError, BridgeRunner, CHECKOUT_BRIDGE_SCRIPT,
    DEFAULT_KOMPAS_PYTHON, PACKAGED_BRIDGE_SCRIPT,
)


@pytest.fixture(scope="session", autouse=True)
def block_live_kompas_bridge():
    protected_scripts = {CHECKOUT_BRIDGE_SCRIPT.resolve(), PACKAGED_BRIDGE_SCRIPT.resolve()}
    protected_python = {DEFAULT_KOMPAS_PYTHON.resolve()}
    if os.environ.get("KOMPAS_BRIDGE_SCRIPT"):
        protected_scripts.add(Path(os.environ["KOMPAS_BRIDGE_SCRIPT"]).resolve())
    if os.environ.get("KOMPAS_PYTHON"):
        protected_python.add(Path(os.environ["KOMPAS_PYTHON"]).resolve())
    attempts: list[str] = []
    lock = threading.Lock()
    original = BridgeRunner.call

    @wraps(original)
    def guarded_call(self, action, *args, **kwargs):
        if (self.bridge_script.resolve() in protected_scripts
                or self.kompas_python.resolve() in protected_python):
            with lock:
                attempts.append(str(action))
            raise BridgeError(
                f"Live KOMPAS bridge is forbidden in host tests: {action}. "
                "Inject a fake adapter/runner; run live CAD verification separately."
            )
        return original(self, action, *args, **kwargs)

    BridgeRunner.call = guarded_call
    yield
    # Deliberately retain the guard until interpreter exit: a daemon CAD job
    # must not regain live access during fixture teardown or finalization.
    if attempts:
        pytest.fail(f"Host tests attempted live KOMPAS calls: {sorted(set(attempts))}")
