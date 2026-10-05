"""Bounded launcher for a persistent Studio, without terminal-owned streams."""
from __future__ import annotations

import json
import ctypes
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Any


def _stop_owned_startup(process: subprocess.Popen) -> None:
    """Only the new process tree; never kill by image name or listening port."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=2,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            pass
    elif process.poll() is None:
        import signal
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def launch_background(*, port: int, expected_version: str, timeout: float,
                      health: Callable[[str], dict[str, Any] | None],
                      log_dir: Path | None = None) -> dict[str, Any]:
    base_url = f"http://127.0.0.1:{port}/"
    if log_dir is None:
        root = Path(os.environ.get("LOCALAPPDATA", Path.home()/".local/state"))
        log_dir = root/"Geomwright"/"studio"
    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    stdout_path = log_dir/f"studio-{port}-{run_id}.stdout.log"
    stderr_path = log_dir/f"studio-{port}-{run_id}.stderr.log"
    command = [sys.executable, "-m", "geomwright.studio", "--port", str(port), "--no-browser"]
    env = {**os.environ,"GEOMWRIGHT_STUDIO_LAUNCH_ID":run_id}
    options: dict[str, Any] = {}
    if os.name == "nt":
        from ctypes import wintypes as w
        kernel = ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.GetModuleFileNameW.argtypes = [w.HMODULE,w.LPWSTR,w.DWORD]
        path = ctypes.create_unicode_buffer(32768)
        if not kernel.GetModuleFileNameW(None,path,len(path)):
            raise ctypes.WinError(ctypes.get_last_error())
        command[0] = path.value
        env["__PYVENV_LAUNCHER__"] = sys.executable
        # NO_WINDOW is deliberately not combined with DETACHED_PROCESS, which
        # would make Windows ignore it. All three standard handles are explicit.
        options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout,
                                   stderr=stderr, close_fds=True,
                                   env=env,**options)
    deadline = time.monotonic()+timeout
    try:
        while time.monotonic()<deadline:
            exit_code = process.poll()
            if exit_code is not None:
                raise RuntimeError(f"Studio exited during startup (code {exit_code}); stderr: {stderr_path}")
            snapshot = health(base_url)
            if (snapshot and snapshot.get("ok") is True
                    and snapshot.get("product") == "geomwright_studio"
                    and snapshot.get("launch_id") == run_id
                    and snapshot.get("studio_version") == expected_version):
                result = {"ok":True,"pid":process.pid,"url":base_url,
                          "server_pid":snapshot.get("pid"),"launch_id":run_id,
                          "stdout":str(stdout_path),"stderr":str(stderr_path)}
                (log_dir/f"studio-{port}-{run_id}.json").write_text(json.dumps(result),encoding="utf-8")
                return result
            time.sleep(min(0.1,max(0,deadline-time.monotonic())))
        raise RuntimeError(f"Studio did not become ready within {timeout:g}s; stderr: {stderr_path}")
    except BaseException:
        _stop_owned_startup(process)
        raise
